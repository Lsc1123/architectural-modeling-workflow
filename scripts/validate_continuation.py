"""Continue the original table fixture without changing its source, then import into SU."""
import argparse
import asyncio
from pathlib import Path
import numpy as np
from _harness import Harness
from amw import checks
from amw.io import atomic, sha


async def run(root, label):
    directory='continuation/'+label
    source='asset-rounds/'+label+'/table.blend'
    digest=sha(root/source)
    specification=dict(asset_id='table_sample',source=source,expected_source_sha256=digest,
        **{key:directory+'/table.'+ext for key,ext in dict(blend='blend',glb='glb',dae='dae',preview='png').items()},
        parts=[dict(type='transform',name='Top',scale=[1.1,1,1])])
    async with Harness(root,directory,'continuation-'+label) as h:
        oid=h.prefix+'-build'
        await h.call('asset_build',specification=specification,operation_id=oid)
        for _ in range(180):
            job=await h.call('asset_job_status',operation_id=oid)
            if job['status']=='completed':break
            await asyncio.sleep(1)
        else:raise TimeoutError('Continuation still running; query the original operation')
        assert sha(root/source)==digest
        result=job['result']
        assert result['verification']['blend_reopened']
        assert any(p['name']=='Top' and 'BEVEL' in p['modifiers'] for p in result['components'])
        assert np.max(np.abs(np.array(result['bounds']['dimensions_m'])-[1.32,.7,.74]))<1e-5
        await h.blank(directory+'/roundtrip.skp')
        floor=await h.box('Floor',[-2,-2,-.2],[4,4,.2],kind='floor')
        imported=await h.write('sketchup_import','import',path=specification['dae'],asset_id='continued_table',expect_solid=True)
        asset=imported['result']['created_ids'][0]
        await h.write('sketchup_save','save',path=directory+'/roundtrip.skp')
        saved=await h.snapshot('saved')
        selected=[o for o in saved['objects'] if o['id']==asset or o['id'].startswith(asset+'/')]
        points=np.concatenate([o['vertices'] for o in selected]);dimensions=points.max(axis=0)-points.min(axis=0)
        assert np.max(np.abs(dimensions-[1.32,.7,.74]))<1e-5
        assert checks.support(saved,[dict(name='continued-feet',contact_ids=[o['id'] for o in selected],host_ids=[floor],z_m=0)])['status']=='passed'
        await h.write('sketchup_reopen','reopen')
        assert checks.scope_diff(saved,await h.snapshot('reopened'),[])['status']=='passed'
        atomic(root/directory/'validation.json',dict(status='passed',source_sha256=digest,source_unchanged=True,
            blender=result,native_model=dict(path=directory+'/roundtrip.skp',sha256=sha(root/directory/'roundtrip.skp')),
            dimensions_m=dimensions.tolist(),scope='Original table continuation, retained bevel, independent Blender reopen and SU import/support/reopen'))
    print('Continuation acceptance passed:',label)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--workspace',required=True);parser.add_argument('--round',required=True)
    args=parser.parse_args();asyncio.run(run(Path(args.workspace).resolve(),args.round))
