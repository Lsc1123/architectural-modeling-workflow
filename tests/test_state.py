import json
from pathlib import Path
import pytest
from amw.project import Project
from amw.io import atomic,sha,within
from amw.native import Native
from amw.jobs import adapter_path


def test_facts_conflicts_do_not_overwrite_user_work(tmp_path):
    p=Project(tmp_path); p.init('house')
    p.update(0,{'brief':'new user requirement'},'user changed brief')
    with pytest.raises(ValueError,match='revision conflict'):p.update(0,{'brief':'old'},'stale')
    assert p.get()['brief']=='new user requirement'


def test_semantic_graph_and_superseded_decisions(tmp_path):
    p=Project(tmp_path); p.init('house')
    with pytest.raises(ValueError,match='unknown region'):
        p.update(0,{'relations':[dict(a='A',b='B',kind='passage')]},'bad endpoint')
    p.decide(0,'constraint','keep courtyard','test user turn 1')
    old=p.get()['decisions'][0]['id']
    p.decide(1,'constraint','change courtyard','test user turn 2',[old])
    assert p.get()['decisions'][0]['status']=='superseded'


def test_stage_requires_actual_current_evidence_and_user_choice(tmp_path):
    p=Project(tmp_path);p.init('house');(tmp_path/'brief.txt').write_text('fixed benchmark brief')
    for kind in ['intent_review','candidate_comparison']:
        path=f'{kind}.json'
        atomic(tmp_path/path,dict(schema_version=1,kind=kind,status='passed',scope=['candidate-A'],sources=[dict(path='brief.txt',sha256=sha(tmp_path/'brief.txt'))],method='Fixed benchmark user review fixture'))
        p.evidence(p.get()['revision'],path)
    assert not p.gate('selection')['ready']
    p.decide(p.get()['revision'],'choose_scheme','select A','Fixed benchmark decision, not a real user approval')
    assert p.gate('selection')['ready']
    (tmp_path/'brief.txt').write_text('user changed the requirements')
    assert not p.gate('selection')['ready']


def test_report_hash_cannot_be_refreshed_into_geometry_proof(tmp_path):
    p=Project(tmp_path);p.init('house');(tmp_path/'model.skp').write_bytes(b'fixture')
    atomic(tmp_path/'report.json',dict(schema_version=1,kind='geometry',status='passed',scope=['wall'],sources=[dict(path='model.skp',sha256='0'*64)],method='stale fixture'))
    with pytest.raises(ValueError,match='source changed'):p.evidence(0,'report.json')


def test_native_request_replay_and_unknown_receipt(tmp_path):
    n=Native(tmp_path)
    atomic(n.runtime/'session.json',dict(heartbeat_unix=10**12,revision='doc:1',bridge_sha256=sha(adapter_path('sketchup/amw_bridge.rb'))))
    a=n.submit('apply',{'operations':[]},'doc:1','same')
    b=n.submit('apply',{'operations':[]},'doc:1','same')
    assert a['operation_id']==b['operation_id']=='same'
    assert len(list((n.runtime/'queue').glob('*.json')))==1
    with pytest.raises(ValueError,match='different arguments'):n.submit('apply',{'operations':[1]},'doc:1','same')
    atomic(n.runtime/'operations/same/status.json',{'status':'running'})
    atomic(n.runtime/'session.json',{'heartbeat_unix':0})
    assert n.poll('same')['status']=='unknown'


def test_workspace_symlink_cannot_redirect_outputs(tmp_path):
    outside=tmp_path.parent/'outside';outside.mkdir(exist_ok=True)
    (tmp_path/'alias').symlink_to(outside,target_is_directory=True)
    with pytest.raises(ValueError,match='escapes'):within(tmp_path,'alias/output.json')


def test_existing_authority_remains_the_only_semantic_table(tmp_path):
    p=Project(tmp_path);p.init('handoff')
    atomic(tmp_path/'facts.json',{'regions':[{'id':'P03','function':'bedroom'}]})
    p.link_authority(0,'facts.json','read existing user facts')
    with pytest.raises(ValueError,match='authoritative'):p.update(1,{'regions':[]},'would compete')
    atomic(tmp_path/'facts.json',{'regions':[{'id':'P03','function':'studio'}]})
    assert p.view()['authority_changed']
    assert 'authoritative_context_changed' in p.gate('refinement')['missing']
    p.link_authority(1,'facts.json','reviewed changed user function')
    assert p.view()['external_context']['regions'][0]['function']=='studio'


def test_compiled_native_replay_is_checked_before_snapshot(tmp_path):
    n=Native(tmp_path);atomic(n.runtime/'session.json',dict(heartbeat_unix=10**12,bridge_sha256=sha(adapter_path('sketchup/amw_bridge.rb'))))
    args=dict(tool='opening',host_ids=['root/1'],expected_revision='doc:1')
    n.submit('apply',{'client_request_sha256':n.client_digest(args)},'doc:1','cut')
    atomic(n.runtime/'operations/cut/result.json',dict(status='completed',operation_id='cut'))
    assert n.recover('cut',args)['status']=='completed'
    with pytest.raises(ValueError,match='different client'):n.recover('cut',dict(args,host_ids=['root/2']))


def test_one_variant_and_one_route_cannot_pass_the_other_variant(tmp_path):
    from amw.project import GATES
    p=Project(tmp_path);p.init('two variants',stage='refinement',entry_evidence='fixed test handoff')
    for variant in ['A','B']:(tmp_path/(variant+'.skp')).write_text('fixed test file '+variant)
    models={v:dict(path=v+'.skp',sha256=sha(tmp_path/(v+'.skp'))) for v in ['A','B']}
    requirements={'handoff':{v:{kind:['entry','terrace'] for kind in GATES['handoff']} for v in models}}
    p.update(0,dict(models=models,requirements=requirements),'fixed acceptance task card')
    p.decide(p.get()['revision'],'accept_handoff','fixture accepts only after both route scopes','fixed test decision')
    for kind in GATES['handoff']:
        for v in models:
            path=f'{v}-{kind}.json';scope=['entry','terrace'] if v=='A' else ['entry']
            atomic(tmp_path/path,dict(schema_version=1,kind=kind,status='passed',scope=scope,sources=[models[v]],method='State machine fixture, not real native validation'))
            p.evidence(p.get()['revision'],path)
    gate=p.gate('handoff')
    assert not gate['ready']
    assert all(':B:' in item and 'terrace' in item for item in gate['missing'])


def test_pending_proposal_does_not_supersede_confirmed_decision(tmp_path):
    p=Project(tmp_path);p.init('house');p.decide(0,'constraint','keep opening','user turn')
    old=p.get()['decisions'][0]['id']
    with pytest.raises(ValueError,match='pending proposal'):p.decide(1,'constraint','maybe close it','proposal',[old],status='pending')
    assert p.get()['decisions'][0]['status']=='current'
    assert (tmp_path/'.amw/project_history'/p.get()['id']/'000000.json').is_file()


def test_mismatched_installed_bridge_refuses_writes_before_queueing(tmp_path):
    n=Native(tmp_path)
    atomic(n.runtime/'session.json',dict(heartbeat_unix=10**12,revision='doc:1',bridge_sha256='old-native-code'))
    with pytest.raises(ConnectionError,match='does not match'):
        n.submit('apply',dict(operations=[]),'doc:1','must-not-write')
    assert not list((n.runtime/'queue').glob('*.json'))
