import copy
import numpy as np
import pytest
import trimesh
from amw import shapes, checks


def document(*items):
    return dict(schema_version=1,units='m',objects=[dict(id=name,**body) for name,body in items])


def test_polygon_hole_is_a_real_void_and_solid():
    slab=shapes.prism([[0,0],[4,0],[4,4],[0,4]],[[[1,1],[1,3],[3,3],[3,1]]],-.2,.2)
    assert shapes.mesh(slab).is_volume
    assert shapes.mesh(slab).volume==pytest.approx(2.4)
    g=document(('slab',slab))
    actual=checks.horizontal_surfaces(g,['slab'],0,1e-6)
    assert actual.area==pytest.approx(12)


def test_old_stair_slot_fails_floor_and_restoration_passes():
    full=shapes.box([0,0,-.2],[4,4,.2])
    broken=shapes.boolean(full,shapes.box([1,1,-.105],[1,1,.105]),'difference')
    args=dict(floor_ids=['slab'],outline=[[0,0],[4,0],[4,4],[0,4]],holes=[],finish_z=0,thickness=.2,tolerance_m=1e-6)
    assert checks.floor_interface(document(('slab',broken)),**args)['status']=='failed'
    assert checks.floor_interface(document(('slab',full)),**args)['status']=='passed'


def test_door_passage_requires_actual_floor_and_body_clearance():
    route=dict(name='door-turn',path_xy=[[0,0],[0,2]],width_m=.75,height_m=2,
               floor_z_m=0,floor_ids=['floor'],obstacle_ids=['wall'])
    floor=shapes.box([-1,-1,-.2],[2,4,.2])
    wall=shapes.box([1,-1,0],[.2,4,3])
    g=document(('floor',floor),('wall',wall))
    assert checks.passage(g,[route])['status']=='passed'
    g['objects'][0].update(shapes.boolean(floor,shapes.box([-.5,.5,-.2],[1,.5,.2]),'difference'))
    assert checks.passage(g,[route])['routes'][0]['unsupported_m2']>.1
    g=document(('floor',floor),('wall',shapes.box([-.2,.5,0],[.4,.2,3])))
    assert checks.passage(g,[route])['status']=='failed'


def test_open_objects_are_not_silently_zero_collision():
    a=shapes.box([0,0,0],[1,1,1]); a['triangles']=a['triangles'][:-2]
    g=document(('open',a),('solid',shapes.box([0,0,0],[1,1,1])))
    r=checks.collisions(g,[['open','solid']])
    assert r['status']=='failed' and r['unverified']


def test_intentional_contacts_are_pair_specific():
    g=document(('a',shapes.box([0,0,0],[1,1,1])),('b',shapes.box([.5,0,0],[1,1,1])),('c',shapes.box([.75,0,0],[1,1,1])))
    r=checks.collisions(g,[['a','b'],['a','c']],intentional=[['a','b']])
    assert not r['pairs'][0]['collision'] and r['pairs'][1]['collision']


def test_native_scope_comparison_includes_material_and_uv():
    a=document(('inside',shapes.box([0,0,0],[1,1,1])),('outside',shapes.box([3,0,0],[1,1,1])))
    b=copy.deepcopy(a);b['objects'][0]['vertices'][0][0]+=.1
    assert checks.scope_diff(a,b,['inside'])['status']=='passed'
    b['objects'][1]['resolved_front_material']={'color':[255,0,0]}
    assert checks.scope_diff(a,b,['inside'])['unexpected']==['outside']


def test_stair_has_integer_risers_and_correct_tread_levels():
    data=shapes.stairs([0,0,0],.9,.17,.28,12)
    m=shapes.mesh(data)
    assert m.is_volume
    assert m.bounds[1].tolist()==pytest.approx([.9,3.08,1.87])
    with pytest.raises(ValueError):shapes.stairs([0,0,0],0,.17,.28,12)


def test_floating_furniture_and_missing_host_are_detected():
    g=document(('foot',shapes.box([0,0,0],[.1,.1,.2])),('floor',shapes.box([-1,-1,-.2],[2,2,.2])))
    case=dict(name='chair-foot',contact_ids=['foot'],host_ids=['floor'],z_m=0)
    assert checks.support(g,[case])['status']=='passed'
    g['objects'][0]=dict(id='foot',**shapes.box([0,0,.01],[.1,.1,.2]))
    assert checks.support(g,[case])['status']=='failed'


def test_pull_chair_state_hits_a_real_obstacle():
    g=document(('chair',shapes.box([0,0,0],[.4,.4,.8])),('wall',shapes.box([0,1,0],[1,.2,2])))
    matrix=np.eye(4);matrix[1,3]=.8
    case=dict(name='pull chair',moving_ids=['chair'],obstacle_ids=['wall'],states=[dict(name='pulled',matrix=matrix.flatten(order='F').tolist())])
    assert checks.actions(g,[case])['status']=='failed'
    case['states'][0]['matrix']=np.eye(4).flatten(order='F').tolist()
    assert checks.actions(g,[case])['status']=='passed'


def test_guard_gap_is_not_erased_by_collision_cleanup():
    g=document(('guard',shapes.box([0,-.05,0],[2,.1,1.1])))
    case=dict(name='terrace-edge',line_xy=[[0,0],[2,0]],base_z_m=0,height_m=1.1,guard_ids=['guard'])
    assert checks.protection(g,[case])['status']=='passed'
    g['objects'][0].update(shapes.boolean(g['objects'][0],shapes.box([.9,-.1,0],[.2,.2,1.2]),'difference'))
    assert checks.protection(g,[case])['status']=='failed'


def test_handoff_plan_reader_preserves_hole_boundary():
    from amw.drawing import slice_geometry
    g=document(('floor',shapes.prism([[0,0],[4,0],[4,4],[0,4]],[[[1,1],[1,3],[3,3],[3,1]]],-.2,.2)))
    r=slice_geometry(g,[0,0,-.1],[0,0,1],[1,0,0])
    segments=np.array(r['objects'][0]['segments_m'])
    assert np.linalg.norm(segments[:,1]-segments[:,0],axis=1).sum()==pytest.approx(24)


def test_face_order_and_float_negative_zero_do_not_mask_real_uv_changes():
    a=document(('panel',dict(vertices=[[0,0,0],[1,0,0],[1,1,0]],triangles=[[0,1,2]],faces=[dict(outer=[0,1,2],holes=[],persistent_id='17',resolved_front_material={'texture':{'pixel_sha256':'original'}},uv_front=[[0.,0.],[1.,0.],[1.,1.]])])))
    b=copy.deepcopy(a);b['objects'][0]['faces'][0].update(persistent_id='18',uv_front=[[-0.,-1e-17],[1.,0.],[1.,1.]])
    assert checks.scope_diff(a,b,[])['status']=='passed'
    b['objects'][0]['faces'][0]['uv_front'][1][0]=.9
    assert checks.scope_diff(a,b,[])['status']=='failed'


def test_positive_total_volume_cannot_hide_an_inverted_third_body():
    a=shapes.mesh(shapes.box([0,0,0],[1,1,1]));b=shapes.mesh(shapes.box([5,3,0],[1,1,1]));c=shapes.mesh(shapes.box([2,1.5,0],[1,1,1]));c.invert()
    mixed=trimesh.util.concatenate([a,b,c])
    assert mixed.is_volume and mixed.volume==pytest.approx(1)
    assert shapes.solid_problems(mixed)
    with pytest.raises(ValueError,match='closed solids'):shapes.boolean(dict(vertices=mixed.vertices.tolist(),triangles=mixed.faces.tolist()),shapes.box([10,0,0],[1,1,1]),'union')


def test_legitimate_closed_cavity_keeps_its_negative_inner_shell():
    hollow=shapes.boolean(shapes.box([0,0,0],[4,4,4]),shapes.box([1,1,1],[2,2,2]),'difference')
    assert shapes.mesh(hollow).volume==pytest.approx(56)
    assert not shapes.solid_problems(shapes.mesh(hollow))
    combined=shapes.boolean(hollow,shapes.box([5,0,0],[1,1,1]),'union')
    assert shapes.mesh(combined).volume==pytest.approx(57)


def test_arrival_disk_cannot_overhang_a_flat_capped_route_end():
    floor=shapes.box([-1,-1,-.2],[2,3,.2])
    case=dict(name='arrival',path_xy=[[0,0],[0,2]],width_m=.75,height_m=2,floor_z_m=0,floor_ids=['floor'],obstacle_ids=[])
    assert checks.passage(document(('floor',floor)),[case])['status']=='failed'
    assert checks.passage(document(('floor',shapes.box([-1,-1,-.2],[2,3.5,.2]))),[case])['status']=='passed'
