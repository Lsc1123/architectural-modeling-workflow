import asyncio
import base64
import copy
import pytest
from amw import checks, shapes
from amw.evidence import evidence_current
from amw.io import atomic, sha
from amw.native import Native
from amw.project import Project
from amw.server import create_server


def test_registered_and_raw_evidence_share_freshness(tmp_path):
    p = Project(tmp_path); p.init('fixture')
    (tmp_path / 'model.skp').write_text('fixture')
    report = dict(schema_version=1, kind='geometry', status='passed', scope=['wall'],
                  sources=[dict(path='model.skp', sha256=sha(tmp_path/'model.skp'))],
                  method='fixture', semantic_basis_sha256=p.semantic_digest())
    atomic(tmp_path/'report.json', report)
    p.evidence(0, 'report.json'); record = p.get()['evidence'][0]
    assert all(evidence_current(tmp_path, r, p.semantic_digest()) for r in [report, record])
    (tmp_path/'model.skp').write_text('changed')
    assert not any(evidence_current(tmp_path, r, p.semantic_digest()) for r in [report, record])
    assert not evidence_current(tmp_path, report, 'changed semantics')


def test_changed_report_invalidates_registered_evidence(tmp_path):
    (tmp_path/'source').write_text('source')
    (tmp_path/'report').write_text('old')
    record = dict(report='report', sha256=sha(tmp_path/'report'),
                  semantic_basis_sha256='same', sources=[dict(path='source', sha256=sha(tmp_path/'source'))])
    assert evidence_current(tmp_path, record, 'same')
    (tmp_path/'report').write_text('new claim')
    assert not evidence_current(tmp_path, record, 'same')


@pytest.mark.parametrize('kind', ['circulation', 'support', 'actions', 'protection', 'collisions', 'floor'])
def test_new_neighbor_invalidates_spatial_inheritance(kind):
    before = dict(objects=[dict(id='floor', **shapes.box([-1,-1,-.2],[2,4,.2]))])
    after = copy.deepcopy(before)
    after['objects'].append(dict(id='new-wall', **shapes.box([-.2,.5,0],[.4,.2,3])))
    route = dict(name='door', path_xy=[[0,0],[0,2]], width_m=.75, height_m=2,
                 floor_z_m=0, floor_ids=['floor'], obstacle_ids=[])
    assert checks.passage(before,[route])['status']=='passed'
    # Reusing only the old list would miss this newly introduced real obstacle.
    assert checks.passage(after,[dict(route,obstacle_ids=['new-wall'])])['status']=='failed'
    assert checks.inheritance_diff(before,after,['floor'],kind)['status']=='failed'
    assert checks.inheritance_diff(before,after,['floor'],'topology')['status']=='passed'
    assert checks.inheritance_diff(before,after,['floor'],'geometry')['status']=='failed'


def test_variant_lineage_needs_recorded_history(tmp_path):
    p=Project(tmp_path); p.init('variants')
    p.update(0,dict(models={'A':dict(path='A-r1.skp'), 'B':dict(path='B.skp')}),'initial versions')
    assert not p.same_model_lineage('A-r1.skp','B.skp')
    assert not p.same_model_lineage('A-r1.skp','unknown.skp')
    p.update(1,dict(models={'A':dict(path='A-r2.skp'), 'B':dict(path='B.skp')}),'new A revision')
    assert p.same_model_lineage('A-r1.skp','A-r2.skp')
    assert not p.same_model_lineage('A-r2.skp','B.skp')


def test_prepare_geometry_recovers_before_snapshot_and_rejects_conflict(tmp_path, monkeypatch):
    native = Native(tmp_path); calls = []
    monkeypatch.setattr(native,'recover',lambda *args: dict(status='completed',operation_id='same'))
    monkeypatch.setattr(native,'snapshot',lambda *args: calls.append('snapshot'))
    receipt, snapshot = native.prepare_geometry('same',{},'old')
    assert receipt['operation_id']=='same' and snapshot is None and not calls
    monkeypatch.setattr(native,'recover',lambda *args: None)
    monkeypatch.setattr(native,'snapshot',lambda *args: dict(document=dict(revision='new')))
    with pytest.raises(ValueError,match='revision changed'):
        native.prepare_geometry('new-operation',{},'old')


def test_timeout_retains_original_id_and_recovery(tmp_path, monkeypatch):
    native = Native(tmp_path)
    monkeypatch.setattr(native,'poll',lambda oid: dict(status='running'))
    assert native.wait('original',0)==dict(status='running',operation_id='original')


def test_capture_returns_image_and_preserves_structured_receipt(tmp_path, monkeypatch):
    png = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=')
    (tmp_path/'capture.png').write_bytes(png)
    receipt = dict(status='completed',operation_id='image',result=dict(path='capture.png'))
    monkeypatch.setattr(Native,'call',lambda *args,**kwargs: receipt)
    server=create_server(tmp_path)
    result=asyncio.run(server.call_tool('sketchup_capture',dict(path='capture.png')))
    assert result.structured_content==receipt
    image=next(c for c in result.content if c.type=='image')
    assert base64.b64decode(image.data)==png and image.mime_type=='image/png'
    receipt=dict(status='failed',operation_id='failed-image',error='native capture failed')
    result=asyncio.run(server.call_tool('sketchup_capture',dict(path='missing.png')))
    assert result.is_error and result.structured_content['operation_id']=='failed-image'
    assert all(c.type!='image' for c in result.content)


def test_tool_annotations_cover_scripts_and_file_outputs(tmp_path):
    tools={t.name:t for t in asyncio.run(create_server(tmp_path).list_tools())}
    assert all(t.annotations is not None for t in tools.values())
    assert tools['project_get'].annotations.read_only_hint
    for name in ['sketchup_export','sketchup_capture','checks_run']:
        assert not tools[name].annotations.read_only_hint
    for name in ['sketchup_script','asset_build']:
        assert tools[name].annotations.open_world_hint


def test_expected_refusal_exposes_id_state_and_cause(tmp_path):
    result=asyncio.run(create_server(tmp_path).call_tool('sketchup_transform',
        dict(ids=['wall'],matrix=[0],expected_revision='old',operation_id='original')))
    assert result.is_error
    assert result.structured_content['operation_id']=='original'
    assert result.structured_content['execution_status']=='not_submitted'
    assert 'affine' in result.structured_content['error']
    assert not list(tmp_path.glob('.amw/runtime/sketchup/queue/*'))


def test_snapshot_timeout_does_not_hide_pending_operation(tmp_path, monkeypatch):
    monkeypatch.setattr(Native,'call',lambda *args,**kwargs: dict(status='running',operation_id='snapshot-id'))
    result=asyncio.run(create_server(tmp_path).call_tool('sketchup_combine',
        dict(ids=['a','b'],name='union',expected_revision='old',operation_id='union-id')))
    data=result.structured_content
    assert result.is_error and data['operation_id']=='union-id'
    assert data['execution_status']=='not_submitted'
    assert data['snapshot_operation']==dict(status='running',operation_id='snapshot-id')


def test_inheritance_tool_rejects_new_neighbor_and_keeps_valid_local_scope(tmp_path):
    p=Project(tmp_path);p.init('fixture')
    for path in ['before.skp','after.skp']:(tmp_path/path).write_text(path)
    p.update(0,dict(models={'main':dict(path='before.skp')}),'baseline')
    before=dict(schema_version=1,units='m',objects=[dict(id='floor',**shapes.box([-1,-1,-.2],[2,4,.2]))],
                source=dict(path='before.skp',sha256=sha(tmp_path/'before.skp'),saved=True))
    after=copy.deepcopy(before);after['source']=dict(path='after.skp',sha256=sha(tmp_path/'after.skp'),saved=True)
    after['objects'].append(dict(id='new-wall',**shapes.box([-.2,.5,0],[.4,.2,3])))
    atomic(tmp_path/'before.json',before);atomic(tmp_path/'after.json',after)
    server=create_server(tmp_path)
    async def run():
        route=dict(name='entry',path_xy=[[0,0],[0,2]],width_m=.75,height_m=2,floor_z_m=0,floor_ids=['floor'],obstacle_ids=[])
        passage=await server.call_tool('checks_run',dict(kind='passage',geometry_path='before.json',parameters=dict(cases=[route]),report_path='passage.json'))
        assert passage.structured_content['status']=='passed'
        await server.call_tool('checks_run',dict(kind='topology',geometry_path='before.json',parameters=dict(ids=['floor']),report_path='topology.json'))
        p.update(p.get()['revision'],dict(models={'main':dict(path='after.skp')}),'new revision')
        args=dict(before_geometry_path='before.json',after_geometry_path='after.json',report_path='inherit.json')
        rejected=await server.call_tool('evidence_inherit',dict(args,old_report_path='passage.json'))
        assert rejected.is_error and 'neighbors' in rejected.structured_content['error']
        inherited=await server.call_tool('evidence_inherit',dict(args,old_report_path='topology.json'))
        assert not inherited.is_error and inherited.structured_content['scope']==['floor']
        (tmp_path/'before.skp').write_text('changed old source')
        stale=await server.call_tool('evidence_inherit',dict(args,old_report_path='topology.json'))
        assert stale.is_error and 'source' in stale.structured_content['error']
    asyncio.run(run())
