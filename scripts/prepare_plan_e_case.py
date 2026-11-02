"""Owner-authorized case extraction. Only independent copies enter SketchUp.

Not a generic project generator and never edits the production design.
"""
import argparse
import re
import shutil
import time
from pathlib import Path
from amw.native import Native
from amw.io import read,atomic,sha
from amw.drawing import write_slice


def public_text(value,project):
    if isinstance(value,dict):return {k:public_text(v,project) for k,v in value.items()}
    if isinstance(value,list):return [public_text(v,project) for v in value]
    if isinstance(value,str):
        value=value.replace(str(project)+'/', 'project-history/')
        return re.sub(r'/Users/[^\s\"\']+', '[historical-local-path]',value)
    return value


def run(project,workspace,destination,resume=False):
    project=project.resolve();workspace=workspace.resolve();out=workspace/destination
    if out.exists() and not resume:raise FileExistsError('Choose a new case revision or explicitly resume the same interrupted copy')
    if (out/'case-manifest.json').exists():raise FileExistsError('The case is already frozen')
    out.mkdir(parents=True,exist_ok=True)
    facts=read(project/'项目上下文/PlanE事实底表.json');n=Native(workspace);records={}
    def call(op,args=None,oid=None):
        receipt=n.runtime/'operations'/oid/'request.json'
        if receipt.exists():
            old=read(receipt)
            assert old['operation']==op and old['arguments']==(args or {})
            r=n.poll(oid)
        else:
            ready=time.monotonic()+180
            while not n.state().get('connected') and time.monotonic()<ready:time.sleep(.25)
            s=n.call('status')['state']
            r=n.call(op,args,s['revision'] if op in ['open','reopen'] else None,oid,timeout=25)
        deadline=time.monotonic()+180
        while r['status'] in ('queued','running','unknown') and time.monotonic()<deadline:
            time.sleep(.25);r=n.poll(oid)
        if r['status']!='completed':raise RuntimeError(r)
        return r
    for label,baseline in [('Unified',facts['version_baselines']['Unified']),('Split',facts)]:
        model=baseline['model'];source=project/model['path']
        assert sha(source)==model['sha256'],'Current source changed; reconcile facts first'
        folder=out/label;folder.mkdir(exist_ok=True);target=folder/(label+'.skp')
        if target.exists():assert resume and sha(target)==model['sha256']
        else:shutil.copy2(source,target)
        if resume and (folder/'verification.json').exists():
            records[label]=read(folder/'verification.json');continue
        relative=str(target.relative_to(workspace))
        prefix='case-'+Path(destination).name+'-'+label
        opened=call('open',{'path':relative},prefix+'-open')
        reopened=call('reopen',{},prefix+'-reopen')
        assert opened['state']['document_id']!=reopened['state']['document_id']
        geom=str((folder/'geometry.json').relative_to(workspace));call('export',{'path':geom},prefix+'-geometry')
        g=read(workspace/geom)
        assert g['source']['saved'] and g['source']['sha256']==model['sha256']==sha(target)==sha(source)
        # Variant semantics come from their own authority rows, never from the
        # current Split state as a fallback for Unified.
        context=public_text({k:baseline[k] for k in ['regions','connections','chains','decisions','scenes','state','historical_split_intentions','historical_split_intentions_note','chain_labels','circulation_note'] if k in baseline},project)
        context.update(coordinates=facts['coordinates'],variant=label,source_sha256=model['sha256'],
            uncertainties=baseline.get('uncertainties',facts['uncertainties']),historical_verification_scope=model['verification_scope'],
            source_fact_table_sha256=sha(project/'项目上下文/PlanE事实底表.json'),
            source_index=public_text({k:{field:value for field,value in row.items() if field!='quote'} for k,row in facts['sources'].items()},project),
            source_index_availability='Historical local references; not all source artifacts are redistributed. This is a publication snapshot, not a second current project authority.')
        atomic(folder/'context.json',context)
        index=[]
        for region in context.get('regions',[]):
            locator=region.get('model_locator') or {};leaf=str(locator.get('persistent_id',''))
            index.append(dict(region=region['id'],function=region['function'],historical_locator=locator,
                native_matches=[o['id'] for o in g['instances'] if leaf and o['id'].split('/')[-1]==leaf]))
        atomic(folder/'semantic-index.json',index);atomic(folder/'material-index.json',g['materials'])
        counts=dict(object_count=len(g['objects']),instance_count=len(g['instances']),scene_count=len(g['scenes']),materials=len(g['materials']))
        all_geometry_ids=[o['id'] for o in g['objects']]
        texture_rows=[m['texture'] for m in g['materials'] if m.get('texture')]
        assert all(sha(workspace/t['path'])==t['sha256'] for t in texture_rows)
        counts['native_texture_files']=len(texture_rows)
        del g  # The reader reloads the large geometry; do not retain two copies.
        reports={}
        for key in ['verification_path','circulation_verification','native_edit_verification','scene_verification','guard_verification']:
            if model.get(key) and (project/model[key]).is_file():
                p=project/model[key];value=read(p);name='history/'+key+'.json'
                atomic(folder/name,dict(availability='Historical scoped evidence; not a fresh whole-model pass',original_sha256=sha(p),historical_project_relative_path=model[key],content=public_text(value,project)))
                reports[key]=name
        readers=[]
        for name,origin,normal,x in [('complex-plan',[0,0,5.4],[0,0,1],[1,0,0]),('key-section',[4.0,0,0],[1,0,0],[0,1,0])]:
            path=str((folder/'drawing'/(name+'.json')).relative_to(workspace))
            r=write_slice(workspace,geom,path,origin,normal,x,ids=all_geometry_ids)
            assert len(r['objects'])>10 and r['native_face_rings']>100
            readers.append(dict(path=path,intersected_objects=len(r['objects']),native_face_rings=r['native_face_rings'],scope='All exported native geometry, including any hidden by saved views'))
        records[label]=dict(model=relative,original_sha256=model['sha256'],geometry=geom,
            **counts,native_document_event=reopened['result'],reader=readers,history=reports,
            fresh_checks=['Source preserved byte-for-byte','Native file actually reopened with new document identity','Native rings/instances/materials/scenes and actual texture files exported','Complex plan and key section read'],
            unverified=['No new global geometry/actions compliance check','Legacy objects without solid classification remain unverified','Structural/lighting/material/MEP details listed in context'])
        atomic(folder/'verification.json',records[label])
    atomic(out/'case-manifest.json',dict(schema_version=1,license='CC0-1.0 for owner contribution; see third-party provenance',variants=records,source_fact_table_sha256=sha(project/'项目上下文/PlanE事实底表.json'),design_changes='none'))
    print('Prepared two unchanged Plan E case copies and actual native drawing readers',flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--project-root',type=Path,required=True);p.add_argument('--workspace',type=Path,required=True);p.add_argument('--destination',default='plan-e-public/r01');p.add_argument('--resume',action='store_true');a=p.parse_args()
    run(a.project_root,a.workspace,a.destination,a.resume)
