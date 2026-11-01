"""Real native hand-edit continuation, scope rollback, grouping and replay."""
import argparse
import asyncio
import numpy as np
from pathlib import Path
from _harness import Harness
from amw import checks,shapes
from amw.io import atomic,sha


async def run(root,label):
    directory='recovery/'+label
    async with Harness(root,directory,'recovery-'+label) as h:
        await h.blank(directory+'/model.skp')
        a=await h.box('A',[0,0,0],[1,1,1]);b=await h.box('B',[3,0,0],[1,1,1])
        await h.write('sketchup_save','initial-save',path=directory+'/model.skp')
        before=await h.snapshot('before-hand-edit');old_revision=h.revision
        await h.script('simulated-user-edit',f"e,_,_=AMW::Bridge.find('{b}');e.transform!(Geom::Transformation.translation([0,0.3/0.0254,0]))",scope=[b])
        hand=await h.snapshot('after-hand-edit')
        matrix=np.eye(4);matrix[2,3]=.1
        await h.write('sketchup_transform','stale-write',ids=[a],matrix=matrix.flatten(order='F').tolist(),expected_revision=old_revision,expect_failure=True)
        refused=await h.snapshot('after-stale-refusal');assert checks.scope_diff(hand,refused,[])['status']=='passed'
        path=directory+'/scripts/illegal.rb';p=h.root/path
        p.write_text(f"e,_,_=AMW::Bridge.find('{b}');e.name='UNAUTHORIZED';e.transform!(Geom::Transformation.translation([0,1/0.0254,0]))")
        await h.write('sketchup_script','scope-violation',script=path,scope_ids=[a],purpose='Acceptance: deliberate out-of-scope edit',expect_failure=True)
        restored=await h.snapshot('after-scope-rollback');assert checks.scope_diff(hand,restored,[])['status']=='passed'
        c=await h.script('custom-native-cube',"m=Sketchup.active_model;g=m.entities.add_group;g.name='C';g.set_attribute('AMW','semantic_id','custom-cube-C');g.set_attribute('AMW','expect_solid',true);f=g.entities.add_face([[5,3,0],[6,3,0],[6,4,0],[5,4,0]].map{|p|p.map{|v|v/0.0254}});f.pushpull(1/0.0254)",new_roots=True)
        c=c['result']['created_ids'][0]
        pre_group=await h.snapshot('before-group')
        await h.write('sketchup_group','group',ids=[a,c],name='Native assembly')
        grouped=await h.snapshot('grouped');assert len(grouped['instances'])==4
        await h.write('sketchup_undo','undo-group')
        assert checks.scope_diff(pre_group,await h.snapshot('after-group-undo'),[])['status']=='passed'
        d=await h.box('D-inside-total-bounds',[2,1.5,0],[1,1,1])
        union=await h.write('sketchup_combine','three-body-union',ids=[a,c,d],name='Three retained bodies')
        union_id=union['result']['created_ids'][0]
        combined=await h.snapshot('combined')
        assert abs(shapes.mesh(checks.select(combined,[union_id])[0]).volume-3)<1e-6
        # The edited B remains outside every subsequent target scope.
        assert checks.scope_diff(dict(hand,objects=checks.select(hand,[b]),instances=[i for i in hand['instances'] if i['id']==b]),dict(combined,objects=checks.select(combined,[b]),instances=[i for i in combined['instances'] if i['id']==b]),[])['status']=='passed'
        before_open_revision=h.revision
        void=dict(type='box',origin=[.25,.25,-.1],size=[.5,.5,1.2])
        opened=await h.write('sketchup_opening','opening',host_ids=[union_id],void=void)
        after_open=await h.snapshot('after-opening');assert abs(shapes.mesh(checks.select(after_open,[union_id])[0]).volume-2.75)<1e-6
        await h.write('sketchup_restore_opening','restore',opening_id=h.prefix+'-opening')
        after_restore=await h.snapshot('after-restoration')
        assert abs(shapes.mesh(checks.select(after_restore,[union_id])[0]).volume-3)<1e-6
        replay=await h.call('sketchup_opening',host_ids=[union_id],void=void,expected_revision=before_open_revision,operation_id=h.prefix+'-opening')
        assert replay['replayed']
        await h.call('sketchup_query')
        assert checks.scope_diff(after_restore,await h.snapshot('after-replay'),[])['status']=='passed'
        await h.write('sketchup_save','save',path=directory+'/model.skp')
        saved=await h.snapshot('saved');await h.write('sketchup_reopen','reopen');reread=await h.snapshot('readback')
        assert saved['document']['document_id']!=reread['document']['document_id']
        assert checks.scope_diff(saved,reread,[])['status']=='passed'
        atomic(h.root/directory/'validation.json',dict(status='passed',model=dict(path=directory+'/model.skp',sha256=sha(h.root/directory/'model.skp')),
            scope=['simulated native user edit retained','stale revision refused','scope violation rolled back','custom native creation','native grouping/undo','third body inside aggregate bounds retained','opening/restoration','same-ID replay','real close/open'],
            limits='Simulated hand edit uses native Ruby. Actual GUI undo is separately recorded in gui/r01.'))
    print('Recovery acceptance passed:',label)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--workspace',required=True);p.add_argument('--round',required=True)
    a=p.parse_args();asyncio.run(run(Path(a.workspace),a.round))
