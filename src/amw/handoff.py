"""Immutable, source-bound handoff packages for the next drawing workflow."""
import shutil
from pathlib import Path
from .io import within, sha, atomic, utc
from .project import Project
from .checks import geometry
from .evidence import evidence_current


def export_handoff(workspace, destination, geometry_path, model_paths):
    root=Path(workspace).resolve();project=Project(root);data=project.get()
    gate=project.gate('handoff')
    if data['stage']!='handoff' or not gate['ready']:
        raise ValueError('Final handoff needs accepted stage, required scopes and current evidence: '+str(gate))
    out=within(root,destination)
    if out.exists():raise FileExistsError('Create a new immutable handoff revision')
    gp=within(root,geometry_path);g=geometry(gp)
    if not g['source']['saved']:raise ValueError('Geometry is not from a saved source')
    source=within(root,g['source']['path'])
    if sha(source)!=g['source']['sha256']:raise ValueError('Geometry source changed')
    inputs=[within(root,p) for p in model_paths]
    if source not in inputs:raise ValueError('Include actual geometry source in model_paths')
    expected={}
    def bind(relative,digest=None):
        p=within(root,relative);name=str(p.relative_to(root));value=digest or sha(p)
        if name in expected and expected[name]!=value:raise ValueError('Conflicting evidence source revisions: '+name)
        if name in ('manifest.json','START_HERE.md','INCOMPLETE.json'):raise ValueError('Source collides with reserved handoff entry: '+name)
        if sha(p)!=value:raise ValueError('Source changed during handoff preparation: '+name)
        expected[name]=value
    for p in inputs+[gp]:bind(p)
    for material in g.get('materials',[]):
        texture=material.get('texture') or {}
        if texture.get('path'):bind(texture['path'],texture['sha256'])
    active=[];stale=[];semantic=project.semantic_digest()
    for e in data['evidence']:
        current = evidence_current(root, e, semantic, data.get('authority'))
        if current:
            bind(e['report'],e['sha256'])
            for s in e['sources']:bind(s['path'],s['sha256'])
            active.append(e)
        else:stale.append(dict(id=e['id'],kind=e['kind'],scope=e['scope'],availability='stale historical reference; not inherited as a current pass'))
    if data.get('authority'):
        for key in ['path','snapshot']:bind(data['authority'][key],data['authority']['sha256'])
    for entry in data.get('history',[]):
        bind(entry['parent_snapshot'])
    if '.amw/project.json' in expected:raise ValueError('Evidence must not depend on the mutable runtime state file')
    files={};out.mkdir(parents=True)
    try:
        for relative,digest in expected.items():
            p=within(root,relative);target=out/relative;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,target)
            if sha(target)!=digest:raise ValueError('Source changed during copy: '+relative)
            files[relative]=digest
        state=out/'.amw/project.json';atomic(state,dict(data,evidence=active))
        files['.amw/project.json']=sha(state)
        for relative,digest in expected.items():
            if sha(within(root,relative))!=digest:raise ValueError('Source changed before final freeze: '+relative)
        if project.get()['revision']!=data['revision']:raise ValueError('Project state changed during freeze')
        manifest=dict(schema_version=1,created_at=utc(),project_id=data['id'],stage=data['stage'],
            units='m',files=files,geometry=str(gp.relative_to(root)),models=[str(p.relative_to(root)) for p in inputs],
            coordinates=data['coordinates'],regions=data['regions'],relations=data['relations'],pending=data['pending'],
            evidence=active,stale_evidence=stale,required_scopes=data.get('requirements',{}),
            limits='Only declared objects, routes, states and variants; no professional structural/code certification.')
        if data.get('authority'):
            manifest.update(authority=data['authority'],coordinates=None,semantic_context=data['authority']['path'])
        atomic(out/'manifest.json',manifest)
        (out/'START_HERE.md').write_text('# Model handoff\n\nRead manifest.json for source hashes, model paths, actual geometry, coordinates, current scoped evidence and pending issues. Scene/camera/section and material indices are in the geometry file. Historical stale evidence is explicitly excluded from current passes.\n\nDrawing-only clipping/explosions and graphic simplification remain separate from architectural changes.\n')
        return dict(path=str(out.relative_to(root)),manifest_sha256=sha(out/'manifest.json'),files=len(files))
    except Exception as error:
        atomic(out/'INCOMPLETE.json',dict(status='failed',error=str(error),instruction='Do not use as an accepted handoff'))
        raise
