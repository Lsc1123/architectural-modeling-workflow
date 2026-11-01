"""Checks on saved, bound geometry. Every result states its actual scope."""
import hashlib
import json
import numpy as np
import trimesh
from shapely.geometry import Polygon, LineString, MultiLineString
from shapely.ops import unary_union, linemerge
from . import shapes
from .io import read, sha, atomic, within, utc


def geometry(path):
    g = read(path)
    if g.get('schema_version') != 1 or g.get('units') != 'm':
        raise ValueError('Expected AMW geometry schema 1 in metres')
    if len({o['id'] for o in g['objects']}) != len(g['objects']):
        raise ValueError('Duplicate object instance IDs')
    return g


def select(g, ids=None):
    by_id = {o['id']: o for o in g['objects']}
    if ids is not None:
        missing = set(ids) - by_id.keys()
        if missing:
            raise ValueError('Unknown objects: ' + ', '.join(sorted(missing)))
    return [by_id[i] for i in ids] if ids is not None else [o for o in g['objects'] if o.get('active', True)]


def topology(g, ids=None):
    rows = []; problems = [];unclassified=[]
    for o in select(g, ids):
        if not o.get('triangles'):
            continue
        m = shapes.mesh(o)
        bad = []
        if not np.isfinite(m.vertices).all():
            bad.append('non-finite coordinates')
        if o.get('expect_solid'):bad.extend(shapes.solid_problems(m))
        if o.get('expect_solid') is None:unclassified.append(o['id'])
        if len(m.faces) and float(m.area_faces.min()) <= 0:
            bad.append('degenerate triangles')
        rows.append(dict(id=o['id'], watertight=bool(m.is_watertight),
                         volume_m3=float(m.volume), triangles=len(m.faces), problems=bad))
        problems.extend(dict(id=o['id'], issue=b) for b in bad)
    return dict(status='failed' if problems else 'unverified' if unclassified else 'passed', scope=[x['id'] for x in rows],
                objects=rows, problems=problems,unclassified_solid_expectations=unclassified)


def collisions(g, pairs, intentional=(), volume_tolerance_m3=1e-9):
    allowed = {frozenset(p) for p in intentional}
    rows = []; unknown = [];meshes={};problems={}
    for pair in pairs:
        if len(pair) != 2 or pair[0] == pair[1]:
            raise ValueError('Collision pairs require two distinct instance IDs')
        a, b = select(g, pair)
        for o in (a,b):
            if o['id'] not in meshes:
                meshes[o['id']]=shapes.mesh(o);problems[o['id']]=shapes.solid_problems(meshes[o['id']])
        ma, mb = meshes[a['id']],meshes[b['id']]
        if not len(ma.faces) or not len(mb.faces):
            unknown.append(dict(pair=pair, reason='no solid geometry')); continue
        if problems[a['id']] or problems[b['id']]:
            unknown.append(dict(pair=pair, reason='Invalid shell geometry; solid overlap not proved',details=problems[a['id']]+problems[b['id']])); continue
        if np.any(ma.bounds[1] < mb.bounds[0]) or np.any(mb.bounds[1] < ma.bounds[0]):
            volume = 0.0
        else:
            volume = float(trimesh.boolean.intersection([ma, mb], engine='manifold').volume)
        rows.append(dict(pair=pair, overlap_m3=volume, intentional=frozenset(pair) in allowed,
                         collision=volume > volume_tolerance_m3 and frozenset(pair) not in allowed))
    return dict(status='failed' if unknown or any(x['collision'] for x in rows) else 'passed',
                scope=pairs, pairs=rows, unverified=unknown)


def horizontal_surfaces(g, ids, z, tolerance_m):
    result = []
    for o in select(g, ids):
        v = np.asarray(o.get('vertices', []), dtype=float)
        for f in o.get('faces', []):
            outer = v[f['outer']]
            if len(outer) < 3 or np.max(np.abs(outer[:, 2] - z)) > tolerance_m:
                continue
            holes = [v[ring][:, :2] for ring in f.get('holes', [])]
            p = Polygon(outer[:, :2], holes)
            if p.is_valid and p.area > 0:
                result.append(p)
        if not o.get('faces'):
            # Tessellated input remains usable, with the same actual Z test.
            for tri in o.get('triangles', []):
                p3 = v[tri]
                if np.max(np.abs(p3[:, 2] - z)) <= tolerance_m:
                    p = Polygon(p3[:, :2])
                    if p.area > 0: result.append(p)
    return unary_union(result)


def floor_interface(g, floor_ids, outline, holes, finish_z, thickness, tolerance_m):
    if tolerance_m <= 0 or thickness <= 0:
        raise ValueError('Use explicit positive measurement tolerance and design thickness')
    expected = Polygon(outline, holes)
    if not expected.is_valid or expected.area <= 0:
        raise ValueError('Invalid expected floor contour')
    top = horizontal_surfaces(g, floor_ids, finish_z, tolerance_m)
    bottom = horizontal_surfaces(g, floor_ids, finish_z - thickness, tolerance_m)
    missing_top = expected.difference(top.buffer(tolerance_m)).area
    missing_bottom = expected.difference(bottom.buffer(tolerance_m)).area
    extra_top = top.difference(expected.buffer(tolerance_m)).area
    # A geometric measurement tolerance is not a permission to relax design dimensions.
    failed = max(missing_top, missing_bottom, extra_top) > tolerance_m ** 2
    return dict(status='failed' if failed else 'passed', scope=floor_ids,
                missing_top_m2=missing_top, missing_bottom_m2=missing_bottom,
                unexpected_top_m2=extra_top, finish_z_m=finish_z, thickness_m=thickness)


def passage(g, cases, tolerance_m=1e-6):
    rows = []
    for c in cases:
        width, height = c['width_m'], c['height_m']
        if width <= 0 or height <= 0 or len(c['path_xy']) < 2:
            raise ValueError('A route needs a positive body size and a real path')
        # Circumscribed polygon approximation covers the requested circular body,
        # including arrival/start disks and turns; flat caps can miss a bad landing.
        segments=32;radius=width/2/np.cos(np.pi/(4*segments))
        swept = LineString(c['path_xy']).buffer(radius,quad_segs=segments,cap_style='round',join_style='round')
        floors = horizontal_surfaces(g, c['floor_ids'], c['floor_z_m'], tolerance_m)
        unsupported = swept.difference(floors.buffer(tolerance_m)).area
        body = shapes.prism(list(swept.exterior.coords)[:-1],
                            [list(r.coords)[:-1] for r in swept.interiors],
                            c['floor_z_m'] + tolerance_m, height - tolerance_m)
        objects = dict(id='__body__', **body)
        subset = dict(g, objects=g['objects'] + [objects])
        result = collisions(subset, [['__body__', i] for i in c['obstacle_ids']])
        rows.append(dict(name=c['name'], unsupported_m2=unsupported, body=result,
                         width_m=width, height_m=height,endpoint_disks_checked=True,
                         status='passed' if unsupported <= tolerance_m ** 2 and result['status'] == 'passed' else 'failed'))
    return dict(status='passed' if rows and all(r['status'] == 'passed' for r in rows) else 'failed',
                scope=[c['name'] for c in cases], routes=rows,
                unverified_scope='Only declared level route segments and door/object states; add separate segments for every tread and turn')


def treads(g,cases,tolerance_m=1e-6):
    """Actual sampled foot support and vertical headroom per tread/arrival.

    This checks declared vertical prisms, not human gait or a continuous stair sweep.
    """
    rows=[]
    for case in cases:
        steps=case['treads'];levels=[s['z_m'] for s in steps];n=case['risers']
        if n<1 or len(levels)!=n+1:raise ValueError('Declare every rise, including start and arrival levels')
        expected=(case['arrival_z_m']-case['start_z_m'])/n
        endpoints=abs(levels[0]-case['start_z_m'])<=tolerance_m and abs(levels[-1]-case['arrival_z_m'])<=tolerance_m
        uniform=bool(np.all(np.abs(np.diff(levels)-expected)<=tolerance_m)) and abs(expected)>tolerance_m
        states=[]
        for step in steps:
            footprint=Polygon(step['outline'],step.get('holes',[]))
            if not footprint.is_valid or footprint.area<=0:raise ValueError('Each sampled foot/headroom footprint must be valid')
            surfaces=horizontal_surfaces(g,step['floor_ids'],step['z_m'],tolerance_m)
            missing=footprint.difference(surfaces.buffer(tolerance_m)).area
            body=dict(id='__tread_body__',**shapes.prism(step['outline'],step.get('holes',[]),step['z_m']+tolerance_m,case['height_m']-tolerance_m))
            collision=collisions(dict(g,objects=g['objects']+[body]),[['__tread_body__',i] for i in case['obstacle_ids']])
            states.append(dict(name=step['name'],z_m=step['z_m'],unsupported_m2=missing,headroom=collision,
                status='passed' if missing<=tolerance_m**2 and collision['status']=='passed' else 'failed'))
        rows.append(dict(name=case['name'],rise_m=expected,risers=n,endpoints_match=endpoints,uniform=uniform,states=states,
            status='passed' if endpoints and uniform and all(s['status']=='passed' for s in states) else 'failed'))
    return dict(status='passed' if rows and all(r['status']=='passed' for r in rows) else 'failed',scope=[c['name'] for c in cases],stairs=rows,
        unverified_scope='Declared foot-support and vertical headroom samples, start/arrival and rise counts only; not continuous human gait, loads or code compliance')


def scope_diff(before, after, allowed_ids):
    def signature(o):
        # Includes inherited materials, UV, actual world coordinates and instance transforms.
        row={k:v for k,v in o.items() if k not in ('vertices','triangles','faces','locator')}
        # Session identity changes on a fresh open; persistent instance paths do not.
        row['locator']={k:v for k,v in o.get('locator',{}).items() if k!='document_id'}
        vertices=(np.round(np.asarray(o.get('vertices',[]),dtype=float),9)+0.).tolist()
        def cycle(values):
            values=[tuple(v) for v in values]
            if not values:return ()
            first=min(range(len(values)),key=lambda i:values[i])
            return tuple(values[first:]+values[:first])
        if o.get('faces'):
            faces=[]
            for f in o['faces']:
                face={k:v for k,v in f.items() if k not in ('outer','holes','persistent_id','uv_front','uv_back','uv_front_holes','uv_back_holes')}
                def ring(indices,hole_index=None):
                    values=[]
                    for index,vi in enumerate(indices):
                        point=list(vertices[vi])
                        for side in ('front','back'):
                            material=f.get('resolved_'+side+'_material') or {}
                            uv=f.get('uv_'+side) if hole_index is None else (f.get('uv_'+side+'_holes') or [])[hole_index] if f.get('uv_'+side+'_holes') else None
                            if material.get('texture') and uv:point.extend((np.round(uv[index],9)+0.).tolist())
                        values.append(point)
                    return cycle(values)
                face['outer']=ring(f['outer'])
                face['holes']=sorted(ring(hole,index) for index,hole in enumerate(f.get('holes',[])))
                faces.append(json.dumps(face,sort_keys=True,ensure_ascii=False))
            row['faces']=sorted(faces)
        else:
            row['triangles']=sorted(cycle([vertices[i] for i in tri]) for tri in o.get('triangles',[]))
        return hashlib.sha256(json.dumps(row, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    def signatures(g):
        rows={}
        for o in g['objects']+g.get('instances',[])+g.get('sections',[]):rows.setdefault(o['id'],[]).append(signature(o))
        def normalize(value):
            if isinstance(value,float):return round(value,9)+0.
            if isinstance(value,dict):return {k:normalize(v) for k,v in value.items()}
            if isinstance(value,list):return [normalize(v) for v in value]
            return value
        for scene in g.get('scenes',[]):
            row=normalize(scene)
            for field in ['hidden_persistent_ids','layer_visibility_overrides','active_section_persistent_ids','hidden_layer_folders']:
                if field in row:row[field]=sorted(row[field])
            if 'layer_defaults' in row:row['layer_defaults']=sorted(row['layer_defaults'],key=lambda x:x['name'])
            rows['scene:'+scene['name']]=[json.dumps(row,sort_keys=True,ensure_ascii=False)]
        return {i:tuple(sorted(v)) for i,v in rows.items()}
    a,b=signatures(before),signatures(after)
    def allowed(i): return any(i == k or i.startswith(k + '/') for k in allowed_ids)
    changed = [i for i in a.keys() | b.keys() if a.get(i) != b.get(i)]
    unexpected = [i for i in changed if not allowed(i)]
    return dict(status='failed' if unexpected else 'passed', scope=sorted(a.keys() | b.keys()),
                changed=sorted(changed), unexpected=sorted(unexpected), allowed=allowed_ids,
                coordinate_precision_m=1e-9,comparison='Canonical oriented face rings and applied UV/material; ignores session IDs, face enumeration and unused untextured UV')


def support(g, cases, tolerance_m=1e-5):
    """Actual horizontal contact faces, including separate furniture feet."""
    rows=[]
    for case in cases:
        contact=horizontal_surfaces(g,case['contact_ids'],case['z_m'],tolerance_m)
        host=horizontal_surfaces(g,case['host_ids'],case['z_m'],tolerance_m)
        missing=contact.difference(host.buffer(tolerance_m)).area
        rows.append(dict(name=case['name'],contact_area_m2=contact.area,unsupported_m2=missing,
            status='passed' if contact.area>tolerance_m**2 and missing<=tolerance_m**2 else 'failed'))
    return dict(status='passed' if rows and all(r['status']=='passed' for r in rows) else 'failed',
        scope=[c['name'] for c in cases],contacts=rows,unverified_scope='Horizontal declared contacts only; no structural capacity or wall fixing certification')


def actions(g, cases):
    """Evaluate actual rigid parts at explicitly declared operation states.

    State samples are deliberately not described as a continuous swept proof.
    Declared body/operation envelopes can be supplied as additional geometry.
    """
    rows=[]
    for case in cases:
        moving=select(g,case['moving_ids']);obstacles=select(g,case['obstacle_ids'])
        if not moving or not case['states']:raise ValueError('Declare moving parts and operation states')
        states=[]
        for state in case['states']:
            matrix=np.asarray(state['matrix'],dtype=float).reshape((4,4),order='F')
            if not np.isfinite(matrix).all() or not np.allclose(matrix[3],[0,0,0,1]):raise ValueError('Finite affine matrix in metres required')
            moved=[]
            for o in moving:
                m=shapes.mesh(o);m.apply_transform(matrix)
                moved.append(dict(o,vertices=m.vertices.tolist(),triangles=m.faces.tolist()))
            sub=dict(g,objects=moved+obstacles)
            result=collisions(sub,[[a['id'],b['id']] for a in moved for b in obstacles])
            states.append(dict(name=state['name'],**result))
        rows.append(dict(name=case['name'],status='passed' if all(s['status']=='passed' for s in states) else 'failed',states=states))
    return dict(status='passed' if rows and all(r['status']=='passed' for r in rows) else 'failed',
        scope=[c['name'] for c in cases],actions=rows,unverified_scope='Only explicit rigid states; intermediate motion and undeclared human actions remain unchecked')


def protection(g, cases, tolerance_m=1e-5):
    """Section coverage of declared solid-panel protection along straight edges."""
    rows=[]
    for case in cases:
        a,b=np.asarray(case['line_xy'],dtype=float);direction=b-a;length=np.linalg.norm(direction)
        if length<=0 or case['height_m']<=0:raise ValueError('Protection needs a real edge and positive design height')
        tangent=np.array([direction[0]/length,direction[1]/length,0.]);normal=np.cross(tangent,[0,0,1.])
        origin=np.array([a[0],a[1],case['base_z_m']]);polygons=[]
        for o in select(g,case['guard_ids']):
            segments=trimesh.intersections.mesh_plane(shapes.mesh(o),normal,origin)
            if len(segments):
                region=Polygon()
                local=segments-origin;xy=np.stack((local@tangent,local[:,:,2]),axis=-1)
                merged=linemerge(MultiLineString(np.round(xy,10).tolist()))
                for loop in getattr(merged,'geoms',[merged]):
                    if not loop.is_ring:raise ValueError('Protection section is open or branched; repair actual topology')
                    p=Polygon(loop.coords)
                    if p.is_valid:region=region.symmetric_difference(p)
                polygons.append(region)
        expected=Polygon([[0,0],[length,0],[length,case['height_m']],[0,case['height_m']]])
        actual=unary_union(polygons);missing=expected.difference(actual.buffer(tolerance_m)).area
        rows.append(dict(name=case['name'],missing_panel_m2=missing,status='passed' if missing<=tolerance_m**2 else 'failed'))
    return dict(status='passed' if rows and all(r['status']=='passed' for r in rows) else 'failed',
        scope=[c['name'] for c in cases],edges=rows,unverified_scope='Declared straight solid-panel sections only; open baluster spacing, fixings and loads need separate checks')


def bind_report(workspace, relative_path, kind, result, sources, method, **extra):
    root = within(workspace, '.')
    bound = [dict(path=str(within(root, p).relative_to(root)), sha256=sha(within(root, p))) for p in sources]
    report = dict(schema_version=1, kind=kind, at=utc(), sources=bound, method=method,
                  **result, **extra)
    atomic(within(root, relative_path), report)
    return report
