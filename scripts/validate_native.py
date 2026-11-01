"""Opt-in real SketchUp/MCP regression. Only use an isolated connected workspace.

Run with --workspace /absolute/disposable/workspace --round r01.
Starts a real stdio client; never substitutes mocks for the native application.
"""
import argparse
import asyncio
import json
import sys
from pathlib import Path
from mcp import Client, StdioServerParameters
from amw.io import atomic, read, sha
from amw import checks, shapes


async def run(root, round_id):
    prefix = 'native-' + round_id
    model = f'{round_id}/model.skp'
    results = []
    params = StdioServerParameters(command=sys.executable,
        args=['-m', 'amw.cli', 'serve', '--workspace', str(root)])
    async with Client(params) as client:
        revision = None
        async def call(tool, **args):
            nonlocal revision
            reply = await client.call_tool(tool, args)
            data = reply.structured_content
            if reply.is_error:
                raise RuntimeError(f'{tool}: {reply.content}')
            if data is None:
                raise RuntimeError(f'No structured result from {tool}: {reply.content}')
            if data.get('status') in ('failed', 'unknown'):
                raise RuntimeError(f'{tool}: {data}')
            if data.get('state'):
                revision = data['state']['revision']
            results.append(dict(tool=tool, result=data))
            atomic(root/f'{round_id}/operation_log.json',results)
            return data
        async def write(tool, suffix, **args):
            return await call(tool, **args, expected_revision=revision,
                              operation_id=prefix+'-'+suffix)
        state = await call('sketchup_state')
        if not state.get('connected') or state['modified']:
            raise RuntimeError('Connect a disposable saved/empty document and preserve unsaved edits first')
        revision = state['revision']
        new=await write('sketchup_new', 'new', path=model)
        assert new['result']['native_document_event']=='new'
        # Factory templates can include a person. Remove it explicitly in this test only.
        initial = await call('sketchup_query')
        ids = [o['id'] for o in initial['result']['objects'] if o['id'].count('/')==1]
        if ids:
            await write('sketchup_delete', 'empty-template', ids=ids,
                        functional_reason='Disposable test template; remove factory scale figure')
        floor = await write('sketchup_create','floor',name='Floor',kind='floor',
            shape=dict(type='prism',outline=[[0,0],[6,0],[6,5],[0,5]],holes=[],z=-.2,height=.2))
        floor_id = floor['result']['created_ids'][0]
        wall = await write('sketchup_create','wall',name='Wall',kind='wall',
            shape=dict(type='box',origin=[0,0,0],size=[6,.2,3]))
        wall_id = wall['result']['created_ids'][0]
        await write('sketchup_material','material',ids=[wall_id],name='Warm wall',
                    color_rgb_255=[225,220,210],opacity=1)
        await write('sketchup_create','stairs',name='Stair',kind='stair',
            shape=dict(type='stairs',origin=[4,1,0],width=.9,rise=.18,tread=.28,risers=4))
        before = await call('sketchup_export',path=f'{round_id}/before.json')
        cutter=dict(type='box',origin=[1,-.1,0],size=[.9,.4,2.1])
        await write('sketchup_opening','door',host_ids=[wall_id],void=cutter)
        await call('sketchup_export',path=f'{round_id}/open.json')
        opened = read(root/f'{round_id}/open.json')
        wall_open = checks.select(opened,[wall_id])[0]
        assert abs(shapes.mesh(wall_open).volume - (3.6-.9*.2*2.1)) < 1e-5
        assert checks.topology(opened)['status']=='passed'
        # Edit a native face, then restore across a separate event-loop turn.
        pre_probe = opened
        await write('sketchup_probe_pushpull','probe',id=wall_id,distance_m=.02)
        await write('sketchup_undo','undo')
        await call('sketchup_export',path=f'{round_id}/after_undo.json')
        undo = read(root/f'{round_id}/after_undo.json')
        assert checks.scope_diff(pre_probe,undo,allowed_ids=[])['status']=='passed'
        await write('sketchup_save','save',path=model)
        await call('sketchup_export',path=f'{round_id}/saved.json')
        reopened_receipt=await write('sketchup_reopen','reopen')
        assert reopened_receipt['result']['native_document_event']=='open'
        await call('sketchup_export',path=f'{round_id}/reopened.json')
        saved=read(root/f'{round_id}/saved.json'); reopened=read(root/f'{round_id}/reopened.json')
        assert saved['document']['document_id']!=reopened['document']['document_id']
        assert checks.scope_diff(saved,reopened,allowed_ids=[])['status']=='passed'
        await call('sketchup_capture',path=f'{round_id}/native.png',zoom_extents=True)
    atomic(root/f'{round_id}/validation.json',dict(status='passed',scope='Fixed wall/floor/stair fixture; not whole-building certification',
        model=dict(path=model,sha256=sha(root/model)),operations=results))
    print(json.dumps(dict(status='passed',round=round_id,model=model)))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--workspace',required=True);p.add_argument('--round',required=True)
    a=p.parse_args();asyncio.run(run(Path(a.workspace).resolve(),a.round))
