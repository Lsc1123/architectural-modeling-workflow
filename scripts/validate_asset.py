"""Real Blender → DAE → SketchUp native edit/save/reopen fixture.

Use a disposable connected workspace. The fixture is original/CC0.
"""
import argparse
import asyncio
import json
import sys
from pathlib import Path
import numpy as np
from mcp import Client, StdioServerParameters
from amw.io import atomic, read, sha
from amw import checks


async def run(root, label, blender):
    prefix='asset-'+label;directory='asset-rounds/'+label;logs=[];revision=None
    source=Path(__file__).resolve().parents[1]/'examples/fixtures/table.json'
    spec=read(source)
    for key,ext in dict(blend='blend',glb='glb',dae='dae',preview='png').items():spec[key]=f'{directory}/table.{ext}'
    script=Path(__file__).resolve().parents[1]/'examples/fixtures/table_texture.py'
    target=root/f'{directory}/table_texture.py';target.parent.mkdir(parents=True,exist_ok=True)
    target.write_bytes(script.read_bytes());spec['script']=str(target.relative_to(root))
    params=StdioServerParameters(command=sys.executable,args=['-m','amw.cli','serve','--workspace',str(root),'--blender',blender])
    async with Client(params) as client:
        async def call(tool,**args):
            nonlocal revision
            reply=await client.call_tool(tool,args);data=reply.structured_content
            if reply.is_error or not data or data.get('status') in ('failed','unknown'):
                raise RuntimeError(f'{tool}: {data or reply.content}')
            if data.get('state') and not data.get('replayed'):revision=data['state']['revision']
            logs.append(dict(tool=tool,result=data));atomic(root/f'{directory}/operation_log.json',logs)
            return data
        async def write(tool,suffix,**args):
            return await call(tool,**args,expected_revision=revision,operation_id=prefix+'-'+suffix)
        await call('asset_build',specification=spec,operation_id=prefix+'-build')
        for _ in range(180):
            job=await call('asset_job_status',operation_id=prefix+'-build')
            if job['status']=='completed':break
            await asyncio.sleep(1)
        else:raise TimeoutError('Asset worker still running; query the same operation')
        replay=await call('asset_build',specification=spec,operation_id=prefix+'-build')
        assert replay['status']=='completed'
        state=await call('sketchup_state');revision=state['revision']
        if not state.get('connected') or state['modified']:raise RuntimeError('Preserve current native edits first')
        await write('sketchup_new','new',path=f'{directory}/roundtrip.skp')
        initial=await call('sketchup_query')
        ids=[o['id'] for o in initial['result']['objects'] if o['id'].count('/')==1]
        if ids:await write('sketchup_delete','empty-template',ids=ids,functional_reason='Remove factory person from original test fixture')
        floor=await write('sketchup_create','floor',name='Asset test floor',kind='floor',shape=dict(type='box',origin=[0,0,-.2],size=[5,5,.2]))
        floor_id=floor['result']['created_ids'][0]
        imported=await write('sketchup_import','import',path=spec['dae'],asset_id=spec['asset_id'],expect_solid=True);asset_id=imported['result']['created_ids'][0]
        assert imported['result']['created_ids']
        matrix=np.eye(4);matrix[:3,3]=[2,2,0]
        await write('sketchup_transform','place',ids=[asset_id],matrix=matrix.flatten(order='F').tolist())
        await call('sketchup_export',path=f'{directory}/placed.json');placed=read(root/f'{directory}/placed.json')
        selected=[o for o in placed['objects'] if o['id']==asset_id or o['id'].startswith(asset_id+'/')]
        points=np.concatenate([o['vertices'] for o in selected]);dimensions=points.max(axis=0)-points.min(axis=0)
        assert np.max(np.abs(dimensions-np.array([1.2,.7,.74])))<1e-5
        assert abs(points.min(axis=0)[2])<1e-5
        assert any(f.get('uv_front') and f.get('resolved_front_material',{}).get('texture') for o in selected for f in o.get('faces',[]))
        contact_ids=[o['id'] for o in selected]
        assert checks.support(placed,[dict(name='table-feet',contact_ids=contact_ids,host_ids=[floor_id],z_m=0)])['status']=='passed'
        await write('sketchup_probe_pushpull','edit',id=contact_ids[0],distance_m=.01)
        await write('sketchup_undo','undo')
        await call('sketchup_export',path=f'{directory}/undo.json')
        assert checks.scope_diff(placed,read(root/f'{directory}/undo.json'),[])['status']=='passed'
        await write('sketchup_scene','scene',name='Asset roundtrip',camera=dict(eye=[5,-3,3],target=[2,2,.4],up=[0,0,1],perspective=False,height_m=3))
        await write('sketchup_save','save',path=f'{directory}/roundtrip.skp')
        await call('sketchup_export',path=f'{directory}/saved.json')
        opened=await write('sketchup_reopen','reopen');assert opened['result']['native_document_event']=='open'
        await call('sketchup_export',path=f'{directory}/reopened.json')
        assert checks.scope_diff(read(root/f'{directory}/saved.json'),read(root/f'{directory}/reopened.json'),[])['status']=='passed'
        await write('sketchup_scene','select-saved-view',select='Asset roundtrip')
        current=await call('sketchup_state')
        assert np.max(np.abs(np.array(current['current_view_camera']['target'])-[2,2,.4]))<1e-8
        assert not current['modified']
        await call('sketchup_capture',path=f'{directory}/native.png')
        atomic(root/f'{directory}/validation.json',dict(status='passed',scope='Original five-part table, direct base-color texture, metre scale, floor placement, native pushpull/undo and real close/reopen',
            blender=job['result'],native_model=dict(path=f'{directory}/roundtrip.skp',sha256=sha(root/f'{directory}/roundtrip.skp')),
            dimensions_m=dimensions.tolist(),contact='actual bottom faces supported',limits='No general shading-equivalence, arbitrary downloaded-asset or whole-room certification'))
    print(json.dumps(dict(status='passed',round=label)))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--workspace',required=True);p.add_argument('--round',required=True);p.add_argument('--blender',default='/Applications/Blender.app/Contents/MacOS/Blender')
    a=p.parse_args();asyncio.run(run(Path(a.workspace).resolve(),a.round,a.blender))
