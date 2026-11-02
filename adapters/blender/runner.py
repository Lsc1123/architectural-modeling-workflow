# SPDX-License-Identifier: GPL-3.0-or-later
"""Independent Blender process; never connects to or resets an existing GUI."""
import bpy
import hashlib
import json
import math
import runpy
import sys
import traceback
import xml.etree.ElementTree as ET
from pathlib import Path
from mathutils import Vector


def output(root, value):
    p = (root / value).resolve()
    if not p.is_relative_to(root): raise ValueError('Output escapes workspace')
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def digest(p): return hashlib.sha256(p.read_bytes()).hexdigest()


def objects():
    return [o for o in bpy.context.scene.objects if o.type in {'MESH', 'CURVE', 'SURFACE', 'FONT'}]


def bounds(items):
    points = [o.matrix_world @ Vector(p) for o in items for p in o.evaluated_get(bpy.context.evaluated_depsgraph_get()).bound_box]
    if not points: raise ValueError('No exportable asset geometry')
    lo = [min(p[i] for p in points) for i in range(3)]
    hi = [max(p[i] for p in points) for i in range(3)]
    return dict(min=lo, max=hi, dimensions_m=[b - a for a, b in zip(lo, hi)])


def material(row):
    m = bpy.data.materials.get(row['name']) or bpy.data.materials.new(row['name'])
    m.use_nodes = True
    p = m.node_tree.nodes.get('Principled BSDF')
    color = tuple(row.get('color', [.65, .65, .65, 1]))
    if len(color) == 3: color += (1,)
    m.diffuse_color = color; p.inputs['Base Color'].default_value = color
    p.inputs['Roughness'].default_value = row.get('roughness', .5)
    p.inputs['Metallic'].default_value = row.get('metallic', 0)
    m['amw_license'] = row.get('license', 'UNSPECIFIED')
    return m


def build(request):
    root = Path(request['workspace']).resolve()
    inherited_sources=[]
    if request.get('source'):
        source = output(root, request['source'])
        if digest(source) != request['expected_source_sha256']: raise ValueError('Source fingerprint changed')
        bpy.ops.wm.open_mainfile(filepath=str(source),load_ui=False,use_scripts=False)
        if digest(source)!=request['expected_source_sha256']:raise ValueError('Source changed while opening')
        inherited_sources=json.loads(bpy.context.scene.get('amw_sources','[]'))
        bpy.ops.file.pack_all()
        working=output(root,request['working_blend'])
        if working.exists():raise FileExistsError('Private working copy already exists')
        bpy.ops.wm.save_as_mainfile(filepath=str(working))
        scale = bpy.context.scene.unit_settings.scale_length
        if abs(scale - 1) > 1e-9:
            if request.get('source_scale_to_m') != scale: raise ValueError('Declare source_scale_to_m to normalize this source')
            for o in bpy.context.scene.objects:
                if o.parent is None: o.location *= scale; o.scale *= scale
    else:
        bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.context.scene.unit_settings.system = 'METRIC'
    bpy.context.scene.unit_settings.scale_length = 1
    provenance=[];seen=set()
    for entry in inherited_sources+request.get('sources',[])+request.get('imports',[]):
        if not isinstance(entry,dict) or not entry.get('license'):raise ValueError('Every asset source needs an explicit license/status')
        key=json.dumps(entry,sort_keys=True)
        if key not in seen:seen.add(key);provenance.append(entry)
    if not provenance:raise ValueError('Record original authorship or external provenance/license; use an explicit private status when rights are unresolved')
    for entry in request.get('imports',[]):
        path=output(root,entry['path'])
        if digest(path)!=entry['sha256']: raise ValueError('Imported asset source changed')
        if not entry.get('license') or not entry.get('source'): raise ValueError('Imported assets need original license and source')
        previous=set(bpy.data.objects)
        suffix=path.suffix.lower()
        if suffix in {'.glb','.gltf'}: bpy.ops.import_scene.gltf(filepath=str(path))
        elif suffix=='.obj': bpy.ops.wm.obj_import(filepath=str(path))
        elif suffix=='.fbx': bpy.ops.import_scene.fbx(filepath=str(path))
        else:raise ValueError('Import GLB/glTF, OBJ or FBX; continue .blend via source')
        added=set(bpy.data.objects)-previous
        factor=entry.get('scale_to_m',1)
        if not isinstance(factor,(float,int)) or factor<=0:raise ValueError('Positive scale_to_m required')
        for o in added:
            if o.parent not in added:
                o.location*=factor;o.scale*=factor
            o['amw_source']=entry['source'];o['amw_license']=entry['license']
    for row in request.get('materials', []): material(row)
    for row in request.get('parts', []):
        kind = row['type']
        if kind == 'box':
            bpy.ops.mesh.primitive_cube_add(size=1, location=row['location'])
            o = bpy.context.object; o.dimensions = row['size']
            bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
        elif kind == 'cylinder':
            bpy.ops.mesh.primitive_cylinder_add(vertices=row.get('segments', 32), radius=row['radius'], depth=row['depth'], location=row['location'])
            o = bpy.context.object
        elif kind == 'tube':
            curve = bpy.data.curves.new(row['name'], 'CURVE'); curve.dimensions = '3D'
            curve.bevel_depth = row['radius']; curve.bevel_resolution = row.get('resolution', 3); curve.use_fill_caps = True
            spline = curve.splines.new('POLY'); spline.points.add(len(row['points']) - 1)
            for p, xyz in zip(spline.points, row['points']): p.co = (*xyz, 1)
            o = bpy.data.objects.new(row['name'], curve); bpy.context.collection.objects.link(o)
        elif kind == 'transform':
            o = bpy.data.objects.get(row['name'])
            if o is None: raise ValueError('Unknown source component: ' + row['name'])
            if 'location' in row: o.location = row['location']
            if 'rotation_degrees' in row: o.rotation_euler = [math.radians(v) for v in row['rotation_degrees']]
            if 'scale' in row: o.scale = row['scale']
        elif kind == 'delete':
            o = bpy.data.objects.get(row['name'])
            if o is None: raise ValueError('Unknown source component: ' + row['name'])
            bpy.data.objects.remove(o, do_unlink=True); continue
        else: raise ValueError('Unsupported part type: ' + kind)
        o.name = row['name']; o['amw_component_id'] = row.get('id', row['name'])
        if row.get('material'):
            m = bpy.data.materials.get(row['material'])
            if m is None: raise ValueError('Unknown material')
            o.data.materials.clear(); o.data.materials.append(m)
        if row.get('bevel_m'):
            b = o.modifiers.new('Editable bevel', 'BEVEL'); b.width = row['bevel_m']; b.segments = row.get('bevel_segments', 2)
    if request.get('script'):
        p = output(root, request['script'])
        if digest(p) != request['script_sha256']: raise ValueError('Script changed')
        runpy.run_path(str(p), init_globals={'AMW_REQUEST': request})
    bpy.context.view_layer.update()
    items = objects(); measured = bounds(items)
    anchor = request.get('anchor', {'kind': 'floor', 'front': [0, -1, 0], 'up': [0, 0, 1]})
    if anchor['kind'] == 'floor' and abs(measured['min'][2]) > request.get('anchor_tolerance_m', 1e-5):
        raise ValueError('Floor asset bottom is not at its declared Z=0 anchor')
    for image in bpy.data.images:
        if image.source == 'FILE' and not image.packed_file and not Path(bpy.path.abspath(image.filepath)).exists():
            raise FileNotFoundError('Missing source image: ' + image.name)
    bpy.context.scene['amw_asset_id'] = request['asset_id']
    bpy.context.scene['amw_anchor'] = json.dumps(anchor)
    bpy.context.scene['amw_sources'] = json.dumps(provenance)
    bpy.ops.file.pack_all()
    blend = output(root, request['blend'])
    if blend.exists(): raise FileExistsError('Asset revision output exists')
    bpy.ops.wm.save_as_mainfile(filepath=str(blend))
    files = {'blend': {'path': str(blend.relative_to(root)), 'sha256': digest(blend)}}
    if request.get('glb'):
        glb = output(root, request['glb'])
        bpy.ops.export_scene.gltf(filepath=str(glb), export_format='GLB', use_selection=False,
                                  export_cameras=False, export_lights=False)
        files['glb'] = {'path': str(glb.relative_to(root)), 'sha256': digest(glb)}
    if request.get('dae'):
        dae = output(root, request['dae']); textures=export_dae(items, dae)
        files['dae'] = {'path': str(dae.relative_to(root)), 'sha256': digest(dae)}
        for i,path in enumerate(textures):files['texture_'+str(i)]={'path':str(path.relative_to(root)),'sha256':digest(path)}
    result = dict(status='completed', asset_id=request['asset_id'], bounds=measured, anchor=anchor,
                  components=[dict(name=o.name, type=o.type, id=o.get('amw_component_id'), modifiers=[m.type for m in o.modifiers]) for o in items],
                  sources=provenance, files=files,
                  parent_source=dict(path=request['source'],sha256=request['expected_source_sha256'],working_copy=request['working_blend']) if request.get('source') else None,
                  unverified=['Real room placement and installation', 'Native GUI edit/undo unless separately recorded'])
    if request.get('preview'):
        preview = output(root, request['preview']); render_preview(measured, preview)
        result['files']['preview'] = {'path': str(preview.relative_to(root)), 'sha256': digest(preview)}
    return result


def export_dae(items, path):
    """COLLADA evaluated mesh with per-face materials and UV; source stays editable."""
    ns = 'http://www.collada.org/2005/11/COLLADASchema'
    ET.register_namespace('', ns)
    def add(parent, tag, text=None, **attrs):
        node = ET.SubElement(parent, '{' + ns + '}' + tag, {k: str(v) for k, v in attrs.items()})
        if text is not None: node.text = str(text)
        return node
    doc = ET.Element('{' + ns + '}COLLADA', version='1.4.1')
    asset = add(doc, 'asset'); add(asset, 'unit', name='meter', meter='1'); add(asset, 'up_axis', 'Z_UP')
    effects = add(doc, 'library_effects'); materials = add(doc, 'library_materials'); geometries = add(doc, 'library_geometries')
    images=add(doc,'library_images');texture_paths=[];image_ids={}
    visual = add(add(doc, 'library_visual_scenes'), 'visual_scene', id='AssetScene', name='AssetScene')
    mats = list({m.name: m for o in items for m in o.data.materials if m}.values())
    material_ids = {}
    for i, m in enumerate(mats):
        mid = 'mat_' + str(i); material_ids[m.name] = mid
        effect = add(effects, 'effect', id=mid + '_fx'); profile = add(effect, 'profile_COMMON')
        image=None
        if m.use_nodes:
            shader=m.node_tree.nodes.get('Principled BSDF')
            links=shader.inputs['Base Color'].links if shader else []
            if links and links[0].from_node.type=='TEX_IMAGE':image=links[0].from_node.image
            elif links:raise ValueError('DAE requires a baked image or direct image Base Color: '+m.name)
        if image:
            if image.name not in image_ids:
                iid='image_'+str(len(image_ids));image_ids[image.name]=iid
                directory=path.parent/(path.stem+'_textures');directory.mkdir(exist_ok=True)
                target=directory/(iid+'.png')
                if target.exists():raise FileExistsError('Texture output already exists')
                image.save_render(filepath=str(target));texture_paths.append(target)
                add(add(images,'image',id=iid,name=iid),'init_from',target.relative_to(path.parent).as_posix())
            iid=image_ids[image.name]
            add(add(add(profile,'newparam',sid=mid+'_surface'),'surface',type='2D'),'init_from',iid)
            sampler=add(add(profile,'newparam',sid=mid+'_sampler'),'sampler2D');add(sampler,'source',mid+'_surface')
        tech = add(profile, 'technique', sid='common'); phong = add(tech, 'phong')
        diffuse=add(phong,'diffuse')
        if image:add(diffuse,'texture',texture=mid+'_sampler',texcoord='UVMap')
        else:add(diffuse, 'color', ' '.join(str(v) for v in m.diffuse_color))
        add(add(phong, 'transparency'), 'float', m.diffuse_color[3])
        add(add(materials, 'material', id=mid, name=m.name), 'instance_effect', url='#' + mid + '_fx')
    deps = bpy.context.evaluated_depsgraph_get()
    for i, o in enumerate(items):
        evaluated = o.evaluated_get(deps); me = evaluated.to_mesh(); me.calc_loop_triangles()
        try:
            gid = 'geometry_' + str(i); geom = add(geometries, 'geometry', id=gid, name=o.name); mesh = add(geom, 'mesh')
            coords = [v for p in me.vertices for v in (o.matrix_world @ p.co)]
            source = add(mesh, 'source', id=gid + '_pos'); add(source, 'float_array', ' '.join(map(str, coords)), id=gid + '_array', count=len(coords))
            accessor = add(add(source, 'technique_common'), 'accessor', source='#' + gid + '_array', count=len(me.vertices), stride=3)
            for n in ['X', 'Y', 'Z']: add(accessor, 'param', name=n, type='float')
            verts = add(mesh, 'vertices', id=gid + '_vertices'); add(verts, 'input', semantic='POSITION', source='#' + gid + '_pos')
            uv = me.uv_layers.active
            if uv:
                source = add(mesh, 'source', id=gid + '_uv'); values = [v for loop in uv.data for v in loop.uv]
                add(source, 'float_array', ' '.join(map(str, values)), id=gid + '_uv_array', count=len(values))
                accessor = add(add(source, 'technique_common'), 'accessor', source='#' + gid + '_uv_array', count=len(uv.data), stride=2)
                for n in ['S', 'T']: add(accessor, 'param', name=n, type='float')
            slots = list(me.materials)
            for mi in sorted({t.material_index for t in me.loop_triangles}):
                tris = [t for t in me.loop_triangles if t.material_index == mi]
                m = slots[mi] if mi < len(slots) else None; mid = material_ids.get(m.name) if m else None
                attrs = {'count': len(tris)}
                if mid: attrs['material'] = mid
                node = add(mesh, 'triangles', **attrs); add(node, 'input', semantic='VERTEX', source='#' + gid + '_vertices', offset=0)
                if uv: add(node, 'input', semantic='TEXCOORD', source='#' + gid + '_uv', offset=1, set=0)
                values = []
                for t in tris:
                    for vi, li in zip(t.vertices, t.loops):
                        values.append(str(vi))
                        if uv: values.append(str(li))
                add(node, 'p', ' '.join(values))
            n = add(visual, 'node', id='node_' + str(i), name=o.name); inst = add(n, 'instance_geometry', url='#' + gid)
            bind = add(add(inst, 'bind_material'), 'technique_common')
            for m in slots:
                if m:
                    mid = material_ids[m.name]; node = add(bind, 'instance_material', symbol=mid, target='#' + mid)
                    if uv: add(node, 'bind_vertex_input', semantic='UVMap', input_semantic='TEXCOORD', input_set=0)
        finally: evaluated.to_mesh_clear()
    add(add(doc, 'scene'), 'instance_visual_scene', url='#AssetScene')
    ET.ElementTree(doc).write(path, encoding='utf-8', xml_declaration=True)
    return texture_paths


def render_preview(measured, path):
    scene = bpy.context.scene
    size = max(measured['dimensions_m']); center = Vector([(a + b) / 2 for a, b in zip(measured['min'], measured['max'])])
    data = bpy.data.cameras.new('Preview camera'); cam = bpy.data.objects.new('Preview camera', data); scene.collection.objects.link(cam)
    cam.location = center + Vector((1.6 * size, -2 * size, 1.4 * size))
    cam.rotation_euler = (center - cam.location).to_track_quat('-Z', 'Y').to_euler(); data.type = 'ORTHO'; data.ortho_scale = size * 1.65; scene.camera = cam
    for position, energy, light_size in [((2, -3, 4), 500, 4), ((-3, -1, 2), 250, 3)]:
        light = bpy.data.lights.new('Preview area', 'AREA'); light.energy = energy * size ** 2; light.size = light_size * size
        o = bpy.data.objects.new('Preview area', light); scene.collection.objects.link(o); o.location = center + Vector(position) * size
        o.rotation_euler = (center - o.location).to_track_quat('-Z', 'Y').to_euler()
    scene.world = scene.world or bpy.data.worlds.new('Preview world'); scene.world.color = (.25, .25, .25)
    scene.render.engine = 'CYCLES'; scene.cycles.device = 'CPU'; scene.cycles.samples = 16
    scene.render.resolution_x = 1000; scene.render.resolution_y = 800; scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = 'PNG'; scene.render.filepath = str(path); bpy.ops.render.render(write_still=True)


def verify(request):
    root = Path(request['workspace']); expected = request['expected']; blend = output(root, expected['files']['blend']['path'])
    if digest(blend) != expected['files']['blend']['sha256']: raise ValueError('Saved asset changed before reread')
    bpy.ops.wm.open_mainfile(filepath=str(blend),load_ui=False,use_scripts=False); bpy.context.view_layer.update()
    measured = bounds(objects())
    error = max(abs(a-b) for a,b in zip(measured['dimensions_m'], expected['bounds']['dimensions_m']))
    if error > 1e-5: raise ValueError('Blender saved/reopened dimensions differ')
    if len(objects()) != len(expected['components']): raise ValueError('Components missing after reopen')
    actual={o.name:[m.type for m in o.modifiers] for o in objects()}
    if any(actual.get(c['name'])!=c['modifiers'] for c in expected['components']):raise ValueError('Editable component/modifier changed after reopen')
    glb_error = None
    if 'glb' in expected['files']:
        bpy.ops.wm.read_factory_settings(use_empty=True)
        bpy.ops.import_scene.gltf(filepath=str(output(root, expected['files']['glb']['path'])))
        measured_glb = bounds(objects())
        glb_error = max(abs(a-b) for key in ['min','max','dimensions_m'] for a,b in zip(measured_glb[key], expected['bounds'][key]))
        if glb_error > 1e-4: raise ValueError('GLB reimport changed asset dimensions')
    return dict(status='completed', blend_reopened=True, dimensions_error_m=error,
                glb_reimport_error_m=glb_error, scope=expected['asset_id'])


if __name__ == '__main__':
    request = json.loads(Path(sys.argv[sys.argv.index('--') + 1]).read_text())
    try:
        result = verify(request) if request.get('mode') == 'verify' else build(request)
        Path(request['result']).write_text(json.dumps(result, ensure_ascii=False, indent=2))
    except Exception as e:
        Path(request['result']).write_text(json.dumps(dict(status='failed', error=str(e), traceback=traceback.format_exc()), ensure_ascii=False, indent=2))
        raise
