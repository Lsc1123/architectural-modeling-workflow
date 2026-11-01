"""MCP v2 tools. Geometry/state tools remain usable without an LLM vendor API."""
import copy
import hashlib
import json
import math
from pathlib import Path
from typing import Literal, Any
from pydantic import BaseModel, ConfigDict
from mcp.server import MCPServer
from . import __version__, shapes, checks
from .io import read, sha, atomic, within, token, utc
from .project import Project
from .native import Native
from .jobs import Jobs,adapter_path
from .handoff import export_handoff


class Box(BaseModel):
    model_config = ConfigDict(extra='forbid')
    type: Literal['box']
    origin: list[float]
    size: list[float]


class Prism(BaseModel):
    model_config = ConfigDict(extra='forbid')
    type: Literal['prism']
    outline: list[list[float]]
    holes: list[list[list[float]]] = []
    z: float
    height: float


class Stairs(BaseModel):
    model_config = ConfigDict(extra='forbid')
    type: Literal['stairs']
    origin: list[float]
    width: float
    rise: float
    tread: float
    risers: int
    rotation_degrees: float = 0


def shape_data(spec):
    row = spec.model_dump() if isinstance(spec, BaseModel) else dict(spec)
    kind = row.pop('type')
    return {'box': shapes.box, 'prism': shapes.prism, 'stairs': shapes.stairs}[kind](**row)


def create_server(workspace, blender='/Applications/Blender.app/Contents/MacOS/Blender'):
    root = Path(workspace).expanduser().resolve()
    project = Project(root); native = Native(root); jobs = Jobs(root)
    server = MCPServer('architectural-modeling-workflow', version=__version__,
        instructions='Read project and active document state first. User chooses schemes and major spatial changes. Never interpret a file fingerprint as a geometry or whole-building certificate. All exchange coordinates are metres.')

    @server.tool(structured_output=True)
    def get_capabilities() -> dict[str, Any]:
        """Inspect actual software connection, units, stages and validation limits."""
        state=native.state();expected=sha(adapter_path('sketchup/amw_bridge.rb'))
        return dict(version=__version__, workspace=str(root), native=state,
                    expected_bridge_sha256=expected,bridge_code_matches=state.get('bridge_sha256')==expected,
                    blender_available=Path(blender).is_file(), units='m',
                    geometry=['box', 'polygon_with_holes', 'straight_stair', 'boolean_opening', 'transforms'],
                    checks=['topology', 'collisions', 'floor', 'passage', 'treads', 'scope_diff', 'support', 'actions', 'protection'],
                    unverified=['Professional structural/code compliance', 'Undeclared routes/states', 'Other OS versions unless separately tested'])

    @server.tool(structured_output=True)
    def project_init(name: str, brief: str = '', stage: Literal['exploration','selection','development','refinement','handoff'] = 'exploration', entry_evidence: str = '') -> dict[str, Any]:
        """Create one current fact record; existing projects are never overwritten."""
        return project.init(name, brief, stage, entry_evidence)

    @server.tool(structured_output=True)
    def project_get() -> dict[str, Any]:
        """Read current facts, decisions, checks, pending issues and revision."""
        return project.view()

    @server.tool(structured_output=True)
    def project_link_authority(expected_revision:int,path:str,change_summary:str) -> dict[str,Any]:
        """Link an existing JSON fact table as sole semantic authority. Refresh only after reading/reconciling its actual changes."""
        return project.link_authority(expected_revision,path,change_summary)

    @server.tool(structured_output=True)
    def project_update(expected_revision: int, changes: dict, reason: str) -> dict[str, Any]:
        """Update current regions/relations/models, retaining revision history. Dimensions use metres."""
        return project.update(expected_revision, changes, reason)

    @server.tool(structured_output=True)
    def decision_record(expected_revision: int, kind: Literal['choose_scheme','spatial_change','accept_handoff','constraint','other'], statement: str, user_source: str, supersedes: list[str] = [], status: Literal['current','pending'] = 'current') -> dict[str, Any]:
        """Record the actual user decision with a retrievable source; never invent user approval."""
        return project.decide(expected_revision, kind, statement, user_source, supersedes, status)

    @server.tool(structured_output=True)
    def stage_check(target: Literal['exploration','selection','development','refinement','handoff']) -> dict[str, Any]:
        """List stage conditions, stale evidence and required user decisions."""
        result = project.gate(target)
        s = native.state()
        if s.get('connected') and (s.get('modified') or s.get('external_disk_change')):
            result['missing'].append('live_document_not_frozen'); result['ready'] = False
        return result

    @server.tool(structured_output=True)
    def stage_advance(expected_revision: int, target: Literal['selection','development','refinement','handoff'], reason: str) -> dict[str, Any]:
        """Advance one stage only after evidence and design decision conditions are met."""
        result = stage_check(target)
        if not result['ready']: raise ValueError(result)
        return project.advance(expected_revision, target, reason)

    @server.tool(structured_output=True)
    def stage_reopen(expected_revision: int, target: Literal['exploration','selection','development','refinement'], reason: str) -> dict[str, Any]:
        """Return to an affected earlier stage without erasing facts or old evidence."""
        return project.reopen(expected_revision, target, reason)

    @server.tool(structured_output=True)
    def evidence_register(expected_revision: int, report: str) -> dict[str, Any]:
        """Read and bind a real scoped report and its current source files. Does not prove its assertions."""
        return project.evidence(expected_revision, report)

    @server.tool(structured_output=True)
    def sketchup_state() -> dict[str, Any]:
        """Inspect actual document identity, unsaved changes, disk drift, scene and live revision."""
        return native.state()

    @server.tool(structured_output=True)
    def sketchup_new(path: str, expected_revision: str, operation_id: str) -> dict[str, Any]:
        """Create a new saved workspace document only after preserving any current unsaved work."""
        return native.call('new',{'path':path},expected_revision,operation_id)

    @server.tool(structured_output=True)
    def sketchup_open(path: str, expected_revision: str, operation_id: str) -> dict[str, Any]:
        """Open a saved workspace document; refuses to switch away from unsaved work."""
        return native.call('open',{'path':path},expected_revision,operation_id)

    @server.tool(structured_output=True)
    def sketchup_query(ids: list[str] | None = None, name_contains: str | None = None, offset: int = 0, limit: int = 50) -> dict[str, Any]:
        """Find native instances and identities without dumping all geometry. Use IDs for editing."""
        if offset < 0 or not 1 <= limit <= 200: raise ValueError('Invalid page')
        args = dict(offset=offset, limit=limit)
        if ids is not None: args['ids'] = ids
        if name_contains is not None: args['name_contains'] = name_contains
        return native.call('query', args)

    @server.tool(structured_output=True)
    def sketchup_create(name: str, shape: Box | Prism | Stairs, expected_revision: str, operation_id: str, kind: str = 'solid',semantic_id:str|None=None) -> dict[str, Any]:
        """Create one editable native solid. Floor polygon Z is its structural bottom; choose finished-face conventions explicitly."""
        op=dict(type='create_mesh',name=name,kind=kind,geometry=shape_data(shape))
        if semantic_id is not None:op['semantic_id']=semantic_id
        return native.call('apply', dict(label='create ' + name, scope_ids=[],operations=[op]), expected_revision, operation_id)

    @server.tool(structured_output=True)
    def sketchup_transform(ids: list[str], matrix: list[float], expected_revision: str, operation_id: str) -> dict[str, Any]:
        """Apply a world-space column-major affine matrix once; translation is metres."""
        if len(matrix) != 16 or not all(math.isfinite(v) for v in matrix) or any(abs(matrix[i]) > 1e-12 for i in [3,7,11]) or abs(matrix[15]-1)>1e-12:
            raise ValueError('Expected a finite affine column-major 4×4 matrix')
        import numpy as np
        if abs(np.linalg.det(np.asarray(matrix).reshape(4,4,order='F')[:3,:3]))<1e-12:
            raise ValueError('Transform must be invertible; a collapsed solid is not an editable architectural body')
        return native.call('apply', dict(label='transform', scope_ids=ids,
            operations=[dict(type='transform', id=i, matrix=matrix) for i in ids]), expected_revision, operation_id)

    @server.tool(structured_output=True)
    def sketchup_delete(ids: list[str], expected_revision: str, operation_id: str, functional_reason: str,scene_names:list[str]=[]) -> dict[str, Any]:
        """Delete declared objects. Explain preserved/replaced enclosure, support and protection; recheck old openings and finishes."""
        if not ids or not functional_reason.strip(): raise ValueError('Provide target IDs and functional disposition')
        return native.call('apply', dict(label=functional_reason, scope_ids=ids,scene_names=scene_names,
            operations=[dict(type='delete', id=i) for i in ids]), expected_revision, operation_id)

    @server.tool(structured_output=True)
    def sketchup_material(ids: list[str], name: str, color_rgb_255: list[int], opacity: float, expected_revision: str, operation_id: str) -> dict[str, Any]:
        """Assign a local material without recoloring unrelated users of an existing material."""
        if len(color_rgb_255)!=3 or not all(0<=x<=255 for x in color_rgb_255) or not 0<=opacity<=1: raise ValueError('Invalid color or opacity')
        return native.call('apply', dict(label='material', scope_ids=ids, operations=[dict(type='material', id=i, name=name, color=color_rgb_255, opacity=opacity) for i in ids]), expected_revision, operation_id)

    @server.tool(structured_output=True)
    def sketchup_opening(host_ids: list[str], void: Box | Prism, expected_revision: str, operation_id: str) -> dict[str, Any]:
        """Cut only specified actual hosts. Stores original hosts and post-state for guarded restoration."""
        client_args=dict(tool='opening',host_ids=host_ids,void=void.model_dump(),expected_revision=expected_revision)
        recovered=native.recover(operation_id,client_args)
        if recovered:return recovered
        snapshot = native.snapshot('.amw/geometry/' + token(operation_id) + '_before.json')
        if snapshot['document']['revision'] != expected_revision: raise ValueError('Snapshot revision changed')
        hosts = checks.select(snapshot, host_ids)
        cutter = shape_data(void)
        replacements = [dict(type='replace_mesh', id=o['id'], geometry=shapes.boolean(o, cutter, 'difference')) for o in hosts]
        if any(not o['geometry']['triangles'] for o in replacements): raise ValueError('Opening would remove an entire host')
        atomic(within(root, '.amw/openings/' + token(operation_id) + '.json'), dict(hosts=hosts, replacements=replacements))
        receipt = native.call('apply', dict(label='host-scoped opening', scope_ids=host_ids, operations=replacements,client_request_sha256=native.client_digest(client_args)), expected_revision, operation_id)
        atomic(within(root, '.amw/openings/' + token(operation_id) + '.json'), dict(hosts=hosts, replacements=replacements, receipt=receipt))
        return receipt

    @server.tool(structured_output=True)
    def sketchup_restore_opening(opening_id: str, expected_revision: str, operation_id: str) -> dict[str, Any]:
        """Restore recorded host geometry only if the post-cut host has not changed."""
        client_args=dict(tool='restore_opening',opening_id=opening_id,expected_revision=expected_revision)
        recovered=native.recover(operation_id,client_args)
        if recovered:return recovered
        if native.poll(opening_id)['status']!='completed':raise ValueError('Opening did not complete; inspect its original operation first')
        record = read(within(root, '.amw/openings/' + token(opening_id) + '.json'))
        current = native.snapshot('.amw/geometry/' + token(operation_id) + '_before.json')
        old = {x['id']: x for x in record['hosts']}
        now = {x['id']: x for x in checks.select(current, list(old))}
        # Native coplanar reconstruction can reorder vertices: compare actual solid volumes via symmetric difference.
        for replacement in record['replacements']:
            actual = now[replacement['id']]
            a = shapes.boolean(actual, replacement['geometry'], 'difference')
            b = shapes.boolean(replacement['geometry'], actual, 'difference')
            if (a['triangles'] and abs(shapes.mesh(a).volume)>1e-9) or (b['triangles'] and abs(shapes.mesh(b).volume)>1e-9):
                raise ValueError('Host changed since opening; use a scoped new repair, not full rollback')
        return native.call('apply', dict(label='restore opening and host', scope_ids=list(old),client_request_sha256=native.client_digest(client_args), operations=[dict(type='replace_mesh', id=i, geometry=old[i]) for i in old]), expected_revision, operation_id)

    @server.tool(structured_output=True)
    def sketchup_combine(ids: list[str], name: str, expected_revision: str, operation_id: str) -> dict[str, Any]:
        """Union explicit solid instances; preserves actual cavities. Inputs are replaced transactionally."""
        if len(ids)<2: raise ValueError('Choose at least two explicit solids')
        client_args=dict(tool='combine',ids=ids,name=name,expected_revision=expected_revision)
        recovered=native.recover(operation_id,client_args)
        if recovered:return recovered
        g = native.snapshot('.amw/geometry/' + token(operation_id) + '_before.json')
        selected = checks.select(g, ids); result = selected[0]
        materials={json.dumps([f.get('resolved_front_material'),f.get('resolved_back_material')],sort_keys=True) for o in selected for f in o.get('faces',[])}
        if len(materials)>1 or any(f.get('resolved_front_material') or f.get('resolved_back_material') for o in selected for f in o.get('faces',[])):
            raise ValueError('Typed union currently requires unpainted solids; preserve material/UV with a scoped native script')
        for o in selected[1:]: result = shapes.boolean(result, o, 'union')
        return native.call('apply', dict(label='combine', scope_ids=ids,client_request_sha256=native.client_digest(client_args), operations=[dict(type='create_mesh', name=name, geometry=result)] + [dict(type='delete', id=i) for i in ids]), expected_revision, operation_id)

    @server.tool(structured_output=True)
    def sketchup_group(ids:list[str],name:str,expected_revision:str,operation_id:str)->dict[str,Any]:
        """Group explicit root-level sibling instances without boolean rebuilding their geometry/materials."""
        if not ids:raise ValueError('Choose root-level instances to group')
        return native.call('apply',dict(label='group '+name,scope_ids=ids,operations=[dict(type='group',ids=ids,name=name)]),expected_revision,operation_id)

    @server.tool(structured_output=True)
    def sketchup_script(script: str, scope_ids: list[str], expected_revision: str, operation_id: str, purpose: str, allow_new_root_entities:bool=False,scene_names:list[str]=[]) -> dict[str, Any]:
        """Run trusted workspace Ruby inside a native transaction. Do not manage transactions or change documents/edit context in scripts. Declare existing geometry scopes, any new roots and scene names. This is code execution, not an OS sandbox."""
        path = within(root, script)
        return native.call('apply', dict(label=purpose, scope_ids=scope_ids, operations=[], script=script, script_sha256=sha(path),allow_new_root_entities=allow_new_root_entities,scene_names=scene_names), expected_revision, operation_id)

    @server.tool(structured_output=True)
    def sketchup_save(path: str, expected_revision: str, operation_id: str) -> dict[str, Any]:
        """Save the authoritative current document; another existing output is never overwritten."""
        return native.call('save', {'path': path}, expected_revision, operation_id)

    @server.tool(structured_output=True)
    def sketchup_edit_context(expected_revision:str,operation_id:str,id:str|None=None)->dict[str,Any]:
        """Enter a native instance editing path, or exit to the model when id is null. Finish any current GUI gesture before changing context; final save requires the root context."""
        return native.call('edit_context',{'id':id},expected_revision,operation_id)

    @server.tool(structured_output=True)
    def sketchup_undo(expected_revision: str, operation_id: str) -> dict[str, Any]:
        """Undo across a distinct native event-loop turn, then query/compare the result."""
        return native.call('undo', {}, expected_revision, operation_id)

    @server.tool(structured_output=True)
    def sketchup_reopen(expected_revision: str, operation_id: str) -> dict[str, Any]:
        """Reopen a saved workspace model only when the native window has no unsaved edits, then export and compare."""
        return native.call('reopen', {}, expected_revision, operation_id)

    @server.tool(structured_output=True)
    def sketchup_probe_pushpull(id: str, distance_m: float, expected_revision: str, operation_id: str) -> dict[str, Any]:
        """Temporarily push/pull a real upward native face. Undo in a separate call and verify restoration before saving."""
        if not 0 < abs(distance_m) <= .1: raise ValueError('Use a small, nonzero temporary edit')
        return native.call('apply',dict(label='temporary native edit probe',scope_ids=[id],operations=[dict(type='probe_pushpull',id=id,distance_m=distance_m)]),expected_revision,operation_id)

    @server.tool(structured_output=True)
    def sketchup_export(path: str = '.amw/geometry/current.json') -> dict[str, Any]:
        """Export actual world geometry, native face rings, UV, materials, instance paths and scenes."""
        return native.call('export', {'path': path})

    @server.tool(structured_output=True)
    def sketchup_capture(path: str, width: int = 1600, height: int = 1000, zoom_extents: bool = False) -> dict[str, Any]:
        """Capture the actual current native view for visual review; an image is not a geometry certificate."""
        return native.call('capture', dict(path=path, width=width, height=height, zoom_extents=zoom_extents))

    @server.tool(structured_output=True)
    def sketchup_scene(expected_revision: str, operation_id: str, select: str | None = None, name: str | None = None, camera: dict | None = None) -> dict[str, Any]:
        """Select an existing scene or save one explicitly requested camera; does not create diagnostic scene clutter."""
        args = dict(select=select) if select else dict(name=name, camera=camera)
        return native.call('scene', args, expected_revision, operation_id)

    @server.tool(structured_output=True)
    def sketchup_import(path: str, expected_revision: str, operation_id: str,asset_id:str|None=None,semantic_id:str|None=None,expect_solid:bool|None=None) -> dict[str, Any]:
        """Import a workspace asset through SketchUp's native importer; inspect units and editability afterwards."""
        args={'path':path,'source_sha256':sha(within(root,path))}
        for key,value in dict(asset_id=asset_id,semantic_id=semantic_id,expect_solid=expect_solid).items():
            if value is not None:args[key]=value
        return native.call('import',args, expected_revision, operation_id)

    @server.tool(structured_output=True)
    def native_job_status(operation_id: str, wait_seconds: float = 0) -> dict[str, Any]:
        """Resume the same native operation; never create a second write after a timeout."""
        return native.wait(operation_id, wait_seconds)

    @server.tool(structured_output=True)
    def native_job_cancel(operation_id: str) -> dict[str, Any]:
        """Cancel a queued operation. Running native transactions finish atomically."""
        return native.cancel(operation_id)

    @server.tool(structured_output=True)
    def asset_build(specification: dict, operation_id: str) -> dict[str, Any]:
        """Create/continue an independent editable Blender asset. Supply asset_id, new blend/glb/dae/preview paths, parts or trusted script, anchor and license sources."""
        return jobs.start(specification, blender, operation_id)

    @server.tool(structured_output=True)
    def asset_job_status(operation_id: str) -> dict[str, Any]:
        """Return durable worker status, Blender exit code and saved/reimport verification."""
        return jobs.status(operation_id)

    @server.tool(structured_output=True)
    def asset_job_cancel(operation_id: str) -> dict[str, Any]:
        """Cancel only this server-owned Blender worker group; incomplete outputs are invalid."""
        return jobs.cancel(operation_id)

    @server.tool(structured_output=True)
    def checks_run(kind: Literal['topology','collisions','floor','passage','treads','scope_diff','support','actions','protection'], geometry_path: str, parameters: dict, report_path: str) -> dict[str, Any]:
        """Compute actual geometry checks. Inputs are IDs/contours/routes and project dimensions, not preset compliance rules."""
        parameters=copy.deepcopy(parameters); requested_parameters=copy.deepcopy(parameters)
        path = within(root, geometry_path); g = checks.geometry(path)
        sources = [geometry_path]
        if g.get('source',{}).get('saved'):
            source = within(root, g['source']['path'])
            if sha(source)!=g['source']['sha256']: raise ValueError('Native source changed after export')
            sources.append(str(source.relative_to(root)))
        else:
            raise ValueError('Save and reread the actual model before registering final checks; candidate calculations are not final evidence')
        if kind=='topology': result=checks.topology(g, **parameters)
        elif kind=='collisions': result=checks.collisions(g, **parameters)
        elif kind=='floor': result=checks.floor_interface(g, **parameters)
        elif kind=='passage': result=checks.passage(g, **parameters)
        elif kind in ('support','actions','protection','treads'):result=getattr(checks,kind)(g,**parameters)
        else:
            before=parameters.pop('before_geometry_path'); sources.append(before)
            result=checks.scope_diff(checks.geometry(within(root,before)),g,**parameters)
        evidence_kind={'topology':'geometry','passage':'circulation','treads':'circulation','scope_diff':'scope_diff'}.get(kind,kind)
        if kind=='topology':dependencies=[o['id'] for o in checks.select(g,parameters.get('ids'))]
        elif kind=='collisions':dependencies=sorted({i for pair in parameters['pairs'] for i in pair})
        elif kind=='floor':dependencies=parameters['floor_ids']
        elif kind=='scope_diff':dependencies=[]
        elif kind=='treads':dependencies=sorted({i for c in parameters['cases'] for s in c['treads'] for i in s['floor_ids']}|{i for c in parameters['cases'] for i in c['obstacle_ids']})
        else:dependencies=sorted({i for c in parameters['cases'] for key,value in c.items() if key.endswith('_ids') for i in value})
        semantic=project.semantic_digest() if project.path.exists() else None
        return checks.bind_report(root,report_path,evidence_kind,result,sources,'Actual saved geometry: '+kind,
            dependency_ids=dependencies,semantic_basis_sha256=semantic,coverage='fresh',parameters=requested_parameters)

    @server.tool(structured_output=True)
    def evidence_inherit(old_report_path:str,before_geometry_path:str,after_geometry_path:str,report_path:str)->dict[str,Any]:
        """Inherit only a check whose declared dependencies are actually unchanged and semantic basis is unchanged. Missing dependencies cannot be guessed."""
        old=read(within(root,old_report_path));deps=old.get('dependency_ids')
        if old.get('status')!='passed' or not deps:raise ValueError('Only a passed report with explicit complete dependency IDs can be inherited')
        if not old.get('semantic_basis_sha256') or old['semantic_basis_sha256']!=project.semantic_digest():raise ValueError('Semantic basis missing or changed; rerun the actual check')
        for s in old['sources']:
            if sha(within(root,s['path']))!=s['sha256']:raise ValueError('Original report source changed')
        if not any(s['path']==before_geometry_path and s['sha256']==sha(within(root,before_geometry_path)) for s in old['sources']):raise ValueError('Original report is not bound to the before geometry')
        before=checks.geometry(within(root,before_geometry_path));after=checks.geometry(within(root,after_geometry_path))
        if not after['source']['saved'] or sha(within(root,after['source']['path']))!=after['source']['sha256']:raise ValueError('Save and reread the actual after model')
        comparison=checks.scope_diff(dict(before,objects=checks.select(before,deps),instances=[i for i in before.get('instances',[]) if i['id'] in deps],scenes=[],sections=[]),dict(after,objects=checks.select(after,deps),instances=[i for i in after.get('instances',[]) if i['id'] in deps],scenes=[],sections=[]),[])
        if comparison['status']!='passed':raise ValueError('Checked dependencies changed; rerun the check')
        sources=list(dict.fromkeys([old_report_path,before_geometry_path,after_geometry_path,after['source']['path']]+[s['path'] for s in old['sources']]))
        return checks.bind_report(root,report_path,old['kind'],dict(status='passed',scope=old['scope']),sources,
            'Inherited original scoped check after actual dependency comparison',coverage='inherited',dependency_ids=deps,
            semantic_basis_sha256=old['semantic_basis_sha256'],original_report=old_report_path,comparison=comparison,
            limits='Original check scope and limitations still apply; this is not a fresh whole-building check')

    @server.tool(structured_output=True)
    def drawing_read_slice(geometry_path:str,output_path:str,origin_m:list[float],normal:list[float],x_axis:list[float],ids:list[str]|None=None)->dict[str,Any]:
        """Read handoff geometry into a plan/section cut-segment draft; final drawing stays in the next workflow."""
        from .drawing import write_slice
        result=write_slice(root,geometry_path,output_path,origin_m,normal,x_axis,ids)
        return dict(path=output_path,objects=len(result['objects']),native_face_rings=result['native_face_rings'],limits=result['limits'])

    @server.tool(structured_output=True)
    def handoff_export(destination: str, geometry_path: str, model_paths: list[str]) -> dict[str, Any]:
        """Freeze a stage-approved handoff with source hashes, actual geometry and explicit unverified scope."""
        return export_handoff(root,destination,geometry_path,model_paths)

    @server.resource('amw://project')
    def current_project() -> str:
        return json.dumps(project.view(),ensure_ascii=False)

    return server
