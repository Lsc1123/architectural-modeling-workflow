"""Fixed real-software five-stage acceptance; not a real user's design approval.

Run --prepare, inspect the generated native images, write the scoped display
review, then run --finish. Use only an isolated disposable workspace.
"""
import argparse
import asyncio
import itertools
import json
import shutil
from pathlib import Path
import numpy as np
from shapely.geometry import Polygon
from _harness import Harness
from amw import checks,shapes
from amw.io import atomic,read,sha,lock
from amw.project import Project


def report(root,path,kind,scope,sources,method,**details):
    return checks.bind_report(root,path,kind,dict(status='passed',scope=scope),sources,method,
        semantic_basis_sha256=Project(root).semantic_digest(),coverage='fresh',**details)


def archive_owned_project(root):
    current=root/'.amw/project.json';registry=root/'.amw/acceptance_project_ids.json'
    owned=read(registry) if registry.exists() else []
    with lock(root/'.amw/project.lock'):
        if current.exists():
            previous=read(current)
            if previous['id'] not in owned or previous['stage']!='handoff':
                raise RuntimeError('Preserve the existing project; this harness only archives its own completed benchmark')
            target=root/'.amw/acceptance_archives'/(previous['id']+'.json');target.parent.mkdir(parents=True,exist_ok=True)
            if target.exists():raise FileExistsError('Benchmark state archive already exists')
            current.rename(target)
    return registry,owned


async def prepare(root,label):
    root=Path(root).resolve();directory='e2e/'+label;prefix='e2e-'+label
    registry,owned=archive_owned_project(root)
    card=read(Path(__file__).resolve().parents[1]/'examples/fixtures/pavilion-task.json')
    task=directory+'/task.json';atomic(root/task,card)
    ids={};probes=[]
    async with Harness(root,directory,prefix) as h:
        p=await h.call('project_init',name='AMW fixed acceptance '+label,brief=card['brief'])
        atomic(registry,owned+[p['id']])
        await h.call('get_capabilities')
        # Exploration: actual different native floor models, no refinement detail.
        for candidate in ('A','B'):
            await h.blank(directory+'/candidate_'+candidate+'.skp')
            shape=dict(type='prism',outline=[[0,0],[6,0],[6,5],[0,5]],
                holes=[] if candidate=='A' else [[[2,1.5],[2,3.5],[4,3.5],[4,1.5]]],z=-.2,height=.2)
            floor=await h.write('sketchup_create','candidate-'+candidate+'-floor',name='Ground floor',kind='floor',shape=shape,semantic_id='GROUND-FLOOR')
            front=await h.box('front-'+candidate,[0,0,0],[6,.2,3],kind='wall',semantic_id='FRONT-WALL')
            if candidate=='A':ids.update(floor=floor['result']['created_ids'][0],front=front)
            await h.write('sketchup_save','candidate-'+candidate+'-save',path=directory+'/candidate_'+candidate+'.skp')
            g=await h.snapshot('candidate_'+candidate)
            measured=checks.horizontal_surfaces(g,[floor['result']['created_ids'][0]],0,1e-6).area
            assert abs(measured-(30 if candidate=='A' else 26))<1e-5
        candidate_sources=[task]+[directory+'/candidate_'+c+ext for c in ('A','B') for ext in ('.skp','.json')]
        for kind in ['intent_review','candidate_comparison']:
            relative=directory+'/reports/'+kind+'.json'
            report(root,relative,kind,['candidate-A','candidate-B'],candidate_sources,
                'Fixed benchmark task-card review plus actual saved floor contours: 30m2 continuous vs 26m2 with a 4m2 courtyard; not a live client decision')
            await h.register(relative)
        p=await h.call('project_get')
        await h.call('decision_record',expected_revision=p['revision'],kind='choose_scheme',statement=card['fixed_user_decisions'][0]['statement'],user_source=task+' (predefined benchmark decision)')
        await h.stage('selection')
        await h.write('sketchup_open','select-A',path=directory+'/candidate_A.skp')
        await h.update(dict(models={'main':dict(path=directory+'/candidate_A.skp',sha256=sha(root/directory/'candidate_A.skp'))}),'Selected A from the fixed task card')
        relative=directory+'/reports/selected_baseline.json'
        report(root,relative,'selected_baseline',['candidate-A'],[task,directory+'/candidate_A.skp',directory+'/candidate_A.json'],'Selected native file and preserved continuous-floor/raised-platform strategy')
        await h.register(relative);await h.stage('development')
        # Development: native enclosure, real openings, stair, support and occupancy.
        for name,origin,size,kind in [
            ('pad',[0,-1,-.2],[3,1,.2],'floor'),('rear',[0,4.8,0],[6,.2,3],'wall'),
            ('west',[0,.2,0],[.2,4.6,3],'wall'),('east',[5.8,.2,0],[.2,4.6,3],'wall'),
            ('roof',[0,0,3],[6,5,.15],'roof'),('landing',[4,1.84,0],[.9,1,.70],'floor'),
            ('finish',[4,1.84,.70],[.9,1,.02],'finish'),
            ('guard-left',[4,1.84,.72],[.06,.94,1.1],'guard'),('guard-right',[4.84,1.84,.72],[.06,.94,1.1],'guard'),
            ('guard-back',[4,2.78,.72],[.9,.06,1.1],'guard'),
            ('door-leaf',[1.05,.2,.01],[.035,.86,2.13],'door'),
            ('table-placeholder',[1.4,2.65,0],[1.2,.7,.74],'placeholder')]:
            ids[name]=await h.box(name,origin,size,kind,semantic_id=name.upper())
        stair=await h.write('sketchup_create','stair',name='Four-rise stair',kind='stair',semantic_id='STAIR-01',
            shape=dict(type='stairs',origin=[4,1,0],width=.9,rise=.18,tread=.28,risers=4))
        ids['stair']=stair['result']['created_ids'][0]
        await h.write('sketchup_opening','entry-opening',host_ids=[ids['front']],void=dict(type='box',origin=[1,-.1,0],size=[1,.4,2.2]))
        await h.write('sketchup_opening','window-opening',host_ids=[ids['east']],void=dict(type='box',origin=[5.7,3,1],size=[.4,1,1.2]))
        code="m=Sketchup.active_model;[4.0,4.84].each_with_index do |x,i|;g=m.entities.add_group;g.name='Stair guard '+i.to_s;g.set_attribute('AMW','semantic_id','STAIR-GUARD-'+i.to_s);g.set_attribute('AMW','kind','guard');g.set_attribute('AMW','expect_solid',true);f=g.entities.add_face([[x,1,0],[x,1.84,0],[x,1.84,1.82],[x,1,1.28]].map{|p|p.map{|v|v/0.0254}});f.reverse! if f.normal.x<0;f.pushpull(0.06/0.0254);end"
        guard=await h.script('sloped-guards',code,new_roots=True);ids['stair-guards']=guard['result']['created_ids']
        await h.update(dict(coordinates=dict(units='m',zero_model_z_m=0,up='+Z',north='+Y'),
            regions=[dict(id='GROUND',function='Benchmark pavilion ground floor',source=task,model_locator=ids['floor']),dict(id='UPPER',function='Benchmark raised platform',source=task,model_locator=ids['finish'])],
            relations=[dict(a='GROUND',b='UPPER',kind='passage')],pending=card['limits']), 'Record fixed benchmark meanings and keep professional/continuous-gait limits explicit')
        async def save_readback(stem):
            path=directory+'/'+stem+'.skp';await h.write('sketchup_save',stem+'-save',path=path)
            saved=await h.snapshot(stem+'-saved');opened=await h.write('sketchup_reopen',stem+'-reopen');g=await h.snapshot(stem+'-readback')
            assert saved['document']['document_id']!=g['document']['document_id']
            assert checks.scope_diff(saved,g,[])['status']=='passed'
            await h.update(dict(models={'main':dict(path=path,sha256=sha(root/path))}), 'Saved and actually reopened '+stem)
            return path,directory+'/'+stem+'-readback.json',g,opened
        async def probe(entities,tag):
            before=await h.snapshot(tag+'-probe-before')
            for index,entity in enumerate(entities):
                await h.write('sketchup_probe_pushpull',tag+'-probe-'+str(index),id=entity,distance_m=.005)
                await h.write('sketchup_undo',tag+'-undo-'+str(index))
            after=await h.snapshot(tag+'-probe-undo');assert checks.scope_diff(before,after,[])['status']=='passed'
            return [directory+'/'+tag+'-probe-before.json',directory+'/'+tag+'-probe-undo.json']
        def circulation(g):
            all_ids=[o['id'] for o in g['objects']]
            routes=[dict(name='entry-and-room',path_xy=[[1.55,-.6],[1.55,1.2],[3,1.2],[3,4.2]],width_m=.75,height_m=1.95,floor_z_m=0,floor_ids=[ids['floor'],ids['pad']],obstacle_ids=all_ids),
                dict(name='upper-landing',path_xy=[[4.45,2.23],[4.45,2.35]],width_m=.75,height_m=1.95,floor_z_m=.72,floor_ids=[ids['finish']],obstacle_ids=all_ids)]
            steps=[]
            for i,(y,z,floor) in enumerate(zip([.70,1.14,1.42,1.70,2.25],[0,.18,.36,.54,.72],[ids['floor'],ids['stair'],ids['stair'],ids['stair'],ids['finish']])):
                steps.append(dict(name='support-'+str(i),z_m=z,outline=[[4.08,y-.12],[4.82,y-.12],[4.82,y+.12],[4.08,y+.12]],floor_ids=[floor]))
            tread_case=dict(name='stair-start-treads-arrival',start_z_m=0,arrival_z_m=.72,risers=4,height_m=1.95,treads=steps,obstacle_ids=all_ids)
            return routes,[tread_case]
        async def runcheck(kind,geometry,parameters,suffix,register=True):
            path=directory+'/reports/'+suffix+'.json'
            result=await h.call('checks_run',kind=kind,geometry_path=geometry,parameters=parameters,report_path=path)
            if result['status']!='passed':raise AssertionError((kind,result))
            if register:await h.register(path)
            return path,result
        probes=await probe([ids['floor'],ids['stair']],'development')
        dev_model,dev_geometry,dev,opened=await save_readback('development')
        required={'refinement':{'main':dict(layout_review=['pavilion-layout'],circulation=['entry-and-room','upper-landing','stair-start-treads-arrival'],native_editability=[ids['floor'],ids['stair']])}}
        await h.update(dict(requirements=required),'Declare every required development scope before progressing')
        for kind,scope,method,sources in [('layout_review',['pavilion-layout'],'Actual enclosure/openings/raised platform satisfy the fixed task card; not a real client design approval',[task,dev_geometry,dev_model]),('native_editability',[ids['floor'],ids['stair']],'Actual native pushpull and separate event-loop undo restored the tested floor and stair',probes+[dev_geometry,dev_model])]:
            path=directory+'/reports/development-'+kind+'.json';report(root,path,kind,scope,sources,method);await h.register(path)
        routes,tread_cases=circulation(dev)
        await runcheck('passage',dev_geometry,dict(cases=routes),'development-passage')
        await runcheck('treads',dev_geometry,dict(cases=tread_cases),'development-treads')
        await h.stage('refinement')
        # Refinement is deliberately later: frames, hardware, light and real asset.
        for name,origin,size,kind in [
            ('jamb-left',[1,0,0],[.05,.2,2.15],'frame'),('jamb-right',[1.95,0,0],[.05,.2,2.15],'frame'),
            ('door-head',[1,0,2.15],[1,.2,.05],'frame'),('handle-plate',[1.085,.90,1],[.02,.1,.04],'hardware'),
            ('handle-lever',[1.105,.90,1.0125],[.02,.11,.015],'hardware'),
            ('window-bottom',[5.8,3,1],[.2,1,.04],'frame'),('window-top',[5.8,3,2.16],[.2,1,.04],'frame'),
            ('window-left',[5.8,3,1.04],[.2,.04,1.12],'frame'),('window-right',[5.8,3.96,1.04],[.2,.04,1.12],'frame'),
            ('glass',[5.89,3.04,1.04],[.02,.92,1.12],'glass'),
            ('lamp-body',[2.4,2.4,2.90],[.6,.2,.06],'light'),('lamp-mount',[2.685,2.485,2.96],[.03,.03,.04],'fixing')]:
            ids[name]=await h.box(name,origin,size,kind,semantic_id=name.upper())
        await h.write('sketchup_delete','replace-occupancy',ids=[ids['table-placeholder']],functional_reason='Replace the benchmark table occupancy with its verified editable asset at the same position')
        # Use the independently validated stock table, retaining source provenance.
        asset_dir=directory+'/assets';(root/asset_dir).mkdir(parents=True,exist_ok=True)
        for extension in ('blend','glb','dae','png'):shutil.copy2(root/'asset-rounds/r06'/('table.'+extension),root/asset_dir/('table.'+extension))
        shutil.copytree(root/'asset-rounds/r06/table_textures',root/asset_dir/'table_textures')
        imported=await h.write('sketchup_import','table',path=asset_dir+'/table.dae',asset_id='table_sample',semantic_id='TABLE-01',expect_solid=True)
        ids['table']=imported['result']['created_ids'][0];matrix=np.eye(4);matrix[:3,3]=[2,3,0]
        await h.write('sketchup_transform','place-table',ids=[ids['table']],matrix=matrix.flatten(order='F').tolist())
        white=[ids[k] for k in ['front','rear','west','east','roof','landing','guard-left','guard-right','guard-back','lamp-body','lamp-mount']]+ids['stair-guards']
        await h.write('sketchup_material','white',ids=white,name='Warm white',color_rgb_255=[228,225,216],opacity=1)
        await h.write('sketchup_material','floor-color',ids=[ids['floor'],ids['pad'],ids['finish'],ids['stair']],name='Warm grey floor',color_rgb_255=[168,165,155],opacity=1)
        frames=[ids[k] for k in ['jamb-left','jamb-right','door-head','handle-plate','handle-lever','window-bottom','window-top','window-left','window-right']]
        await h.write('sketchup_material','frames',ids=frames,name='Graphite',color_rgb_255=[65,70,73],opacity=1)
        await h.write('sketchup_material','glass',ids=[ids['glass']],name='Clear glass schematic',color_rgb_255=[185,212,220],opacity=.3)
        # Real native section entity and three useful views; full geometry retained.
        section=await h.script('plan-section',"m=Sketchup.active_model;p=m.entities.add_section_plane([0,0,1.2/0.0254],[0,0,-1]);p.name='Plan cut 1.2m';p.activate",new_roots=True)
        ids['plan-section']=section['result']['created_ids'][0]
        await h.write('sketchup_scene','plan-scene',name='Plan cut',camera=dict(eye=[3,2.5,10],target=[3,2.5,0],up=[0,1,0],perspective=False,height_m=7))
        await h.script('deactivate-cut',"Sketchup.active_model.entities.active_section_plane=nil",scope=[ids['plan-section']])
        await h.write('sketchup_scene','interior-scene',name='Interior',camera=dict(eye=[3.3,4.1,1.65],target=[3,1.6,1],up=[0,0,1],perspective=True,fov=65))
        await h.write('sketchup_scene','full-scene',name='Complete',camera=dict(eye=[10,-10,7],target=[3,2,1.2],up=[0,0,1],perspective=False,height_m=8))
        final_probes=await probe([ids['floor'],ids['stair'],ids['table']],'refinement')
        model,geometry,g,opened=await save_readback('model')
        all_ids=[o['id'] for o in g['objects']]
        # Native views are captured, then actually reviewed before the final gate.
        images=[]
        for name in ['Complete','Interior','Plan cut']:
            await h.write('sketchup_scene','view-'+name.replace(' ','-'),select=name)
            path=directory+'/views/'+name.replace(' ','_')+'.png';await h.call('sketchup_capture',path=path);images.append(path)
        await h.write('sketchup_scene','restore-complete',select='Complete')
        current=await h.call('sketchup_state');assert not current['modified'] and current['disk_sha256']==sha(root/model)
        # Keep the final native read data in the complete display state.
        g=await h.snapshot('final-geometry');geometry=directory+'/final-geometry.json'
        requirements=required
        requirements['handoff']={'main':dict(geometry=all_ids,usage=['entry-and-room','upper-landing','stair-start-treads-arrival','table-support','lamp-support','door-states'],
            scope_diff=['development-core-preserved'],file_readback=['main-model'],native_editability=[ids['floor'],ids['stair'],ids['table']],display=['Complete','Interior','Plan cut'])}
        await h.update(dict(requirements=requirements),'Declare all final variant and scope requirements; keep stated limits')
        await runcheck('topology',geometry,dict(ids=all_ids),'topology')
        route_parameters,tread_cases=circulation(g)
        passage_path,passage=await runcheck('passage',geometry,dict(cases=route_parameters),'final-passage')
        tread_path,tread=await runcheck('treads',geometry,dict(cases=tread_cases),'final-treads')
        support_cases=[dict(name='table-support',contact_ids=[ids['table']],host_ids=[ids['floor']],z_m=0),dict(name='lamp-support',contact_ids=[ids['lamp-mount']],host_ids=[ids['roof']],z_m=3)]
        support_path,support=await runcheck('support',geometry,dict(cases=support_cases),'support')
        guards=[dict(name='left',line_xy=[[4.03,1.84],[4.03,2.78]],base_z_m=.72,height_m=1.1,guard_ids=[ids['guard-left']]),dict(name='right',line_xy=[[4.87,1.84],[4.87,2.78]],base_z_m=.72,height_m=1.1,guard_ids=[ids['guard-right']]),dict(name='back',line_xy=[[4,2.81],[4.9,2.81]],base_z_m=.72,height_m=1.1,guard_ids=[ids['guard-back']])]
        guard_path,_=await runcheck('protection',geometry,dict(cases=guards),'guards')
        await runcheck('floor',geometry,dict(floor_ids=[ids['floor']],outline=[[0,0],[6,0],[6,5],[0,5]],holes=[],finish_z=0,thickness=.2,tolerance_m=1e-6),'main-floor')
        await runcheck('floor',geometry,dict(floor_ids=[ids['landing'],ids['finish']],outline=[[4,1.84],[4.9,1.84],[4.9,2.84],[4,2.84]],holes=[],finish_z=.72,thickness=.72,tolerance_m=1e-6),'arrival-finish')
        states=[]
        for angle in [0,-45,-90]:
            matrix=np.eye(4);r=np.deg2rad(angle);matrix[:2,:2]=[[np.cos(r),-np.sin(r)],[np.sin(r),np.cos(r)]];pivot=np.array([1.05,.2,0]);matrix[:3,3]=pivot-matrix[:3,:3]@pivot
            states.append(dict(name=str(angle)+' degrees from open',matrix=matrix.flatten(order='F').tolist()))
        moving=[ids[k] for k in ['door-leaf','handle-plate','handle-lever']]
        action_path,_=await runcheck('actions',geometry,dict(cases=[dict(name='door-states',moving_ids=moving,obstacle_ids=[i for i in all_ids if i not in moving],states=states)]),'door-states')
        usage=directory+'/reports/usage.json'
        report(root,usage,'usage',['entry-and-room','upper-landing','stair-start-treads-arrival','table-support','lamp-support','door-states'],[model,geometry,passage_path,tread_path,support_path,guard_path,action_path],
            'Actual saved geometry for declared level routes, start/each-tread/arrival vertical samples, support and three rigid door states; continuous human gait and intermediate door angles remain unverified')
        await h.register(usage)
        # Scope preservation includes geometry, not just a broad material exemption.
        discrepancy=[]
        for old in dev['objects']:
            if old['id']==ids['table-placeholder']:continue
            actual=checks.select(g,[old['id']])[0]
            a=shapes.boolean(old,actual,'difference');b=shapes.boolean(actual,old,'difference')
            value=sum(abs(shapes.mesh(x).volume) for x in [a,b] if x['triangles'])
            assert value<1e-8,(old['id'],value);discrepancy.append(dict(id=old['id'],symmetric_difference_m3=value))
        raw=checks.scope_diff(dev,g,allowed_ids=list({o['id'] for o in dev['objects']}|{o['id'] for o in g['objects']}|{o['id'] for o in g.get('sections',[])}|{'scene:'+s['name'] for s in g['scenes']}))
        assert raw['status']=='passed'
        for kind,scope,sources,method,extra in [
            ('scope_diff',['development-core-preserved'],[dev_model,dev_geometry,model,geometry],'Actual symmetric difference of every retained development solid, with declared new detail/material/scene changes',dict(core_comparison=discrepancy,metadata_comparison=raw)),
            ('file_readback',['main-model'],[model,directory+'/model-saved.json',directory+'/model-readback.json',geometry],'Native close/open event with a new document ID; actual geometry, materials, instances and scenes compared',dict(native_document_event=opened['result'])),
            ('native_editability',[ids['floor'],ids['stair'],ids['table']],[model,geometry]+final_probes,'Native floor, stair and imported asset face pushpull/undo restored actual geometry before final save',{})]:
            path=directory+'/reports/'+kind+'.json';report(root,path,kind,scope,sources,method,**extra);await h.register(path)
        # Attach editable asset sources; source creation/readback is inherited,
        # current native placement/support above is freshly checked.
        asset_sources=[str(p.relative_to(root)) for p in (root/asset_dir).rglob('*') if p.is_file()]
        asset_report=directory+'/reports/asset-source.json'
        report(root,asset_report,'asset_source',['table_source'],asset_sources+[model,geometry],'Original verified table fixture source retained; Blender source creation/readback inherited from the separate asset acceptance; current placement checked separately',origin='asset-rounds/r06/validation.json')
        await h.register(asset_report)
        for filename,origin,normal,x_axis in [('plan',[0,0,1.2],[0,0,1],[1,0,0]),('section',[4.45,0,0],[1,0,0],[0,1,0])]:
            result=await h.call('drawing_read_slice',geometry_path=geometry,output_path=directory+'/drawing/'+filename+'.json',origin_m=origin,normal=normal,x_axis=x_axis)
            assert result['objects']>0 and result['native_face_rings']>0
        atomic(root/directory/'prepared.json',dict(status='awaiting_actual_visual_review',model=model,geometry=geometry,images=images,ids=ids,project_id=p['id'],limits=card['limits']))
    print('Prepared real five-stage fixture; inspect images and finish:',label)


async def finish(root,label):
    root=Path(root).resolve();directory='e2e/'+label;prepared=read(root/directory/'prepared.json')
    review=directory+'/reports/display.json'
    if not (root/review).exists():raise RuntimeError('Inspect actual native images and create the scoped display report first')
    async with Harness(root,directory,'e2e-'+label+'-finish') as h:
        p=await h.call('project_get')
        if p['id']!=prepared['project_id']:raise RuntimeError('Another benchmark/project is current; preserve it')
        await h.register(review)
        p=await h.call('project_get');task=read(root/directory/'task.json')
        await h.call('decision_record',expected_revision=p['revision'],kind='accept_handoff',statement=task['fixed_user_decisions'][1]['statement'],user_source=directory+'/task.json (predefined benchmark decision, not a live client approval)')
        await h.stage('handoff')
        result=await h.call('handoff_export',destination=directory+'/handoff',geometry_path=prepared['geometry'],model_paths=[prepared['model']])
        manifest=read(root/result['path']/'manifest.json')
        assert all(sha(root/result['path']/name)==digest for name,digest in manifest['files'].items())
        atomic(root/directory/'validation.json',dict(status='passed',scope='Fixed 6x5m pavilion task: two native candidates, predefined scheme choice, development/refinement with retained core, exact declared checks, actual native visual review and frozen portable handoff',handoff=result,limits=prepared['limits']))
    print('Full five-stage handoff passed:',label)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--workspace',required=True);p.add_argument('--round',required=True);p.add_argument('--finish',action='store_true')
    a=p.parse_args();asyncio.run((finish if a.finish else prepare)(Path(a.workspace),a.round))
