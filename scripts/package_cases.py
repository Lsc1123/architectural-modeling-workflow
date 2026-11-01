"""Package verified, owner-authorized cases without private runtime logs."""
import argparse
import json
import shutil
import zipfile
from pathlib import Path
from amw.io import atomic,read,sha


def archive(destination,entries):
    with zipfile.ZipFile(destination,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for name,path in sorted(entries):z.write(path,name)
    print(destination.name,round(destination.stat().st_size/1024**2,1),'MiB',flush=True)


def main():
    p=argparse.ArgumentParser();p.add_argument('--workspace',type=Path,required=True);p.add_argument('--out',type=Path,default=Path('dist'));a=p.parse_args()
    root=Path(__file__).resolve().parents[1];work=a.workspace.resolve();a.out.mkdir(parents=True,exist_ok=True)
    case=work/'plan-e-public/r02'
    assert read(case/'case-manifest.json')['design_changes']=='none'
    for label in ['Unified','Split']:
        v=read(case/label/'verification.json');assert sha(case/label/(label+'.skp'))==v['original_sha256']
    for source,target in [(root/'examples/plan-e/README.md',case/'START_HERE.md'),(root/'THIRD_PARTY.md',case/'THIRD_PARTY.md'),(root/'LICENSES/CC0-1.0.txt',case/'CC0-1.0.txt'),(root/'examples/plan-e/asset-provenance.json',case/'asset-provenance.json'),(root/'docs/history-lessons.json',case/'history-lessons.json'),(root/'examples/plan-e/finish-provenance.json',case/'finish-provenance.json')]:shutil.copy2(source,target)
    (case/'START_HERE.md').write_text('''# Plan E case workspace

Both SKP files are unchanged owner-authorized R10 refined architectural models. Start from Unified/context.json or Split/context.json, then verification.json and case-manifest.json. geometry.json contains actual world-metre native rings, instances, materials/UV, scenes and sections. semantic-index.json maps current regions to native IDs. drawing/ contains section-segment interface samples, not finished drawings.

Fresh checks are file reopens, native data export and drawing-reader compatibility. Historical evidence stays historical and scoped. Read all uncertainties; no structural, lighting, MEP, fire, accessibility or arbitrary-action certificate is made. Original geometry CC0; external sources retain their licenses in THIRD_PARTY.md and asset-provenance.json. Raw chats are excluded.

Extract the ZIP preserving plan-e-public/r02/ inside a new workspace. Its geometry source paths and FILES.json are relative to that workspace root. Repository documentation: https://github.com/Lsc1123/architectural-modeling-workflow .
''')
    credits=case/'THIRD_PARTY.md'
    credits.write_text(credits.read_text().replace('(examples/plan-e/asset-provenance.json)','(asset-provenance.json)').replace('(docs/history-lessons.json)','(history-lessons.json)').replace('(examples/plan-e/finish-provenance.json)','(finish-provenance.json)'))
    atomic(case/'FILES.json',{str(f.relative_to(work)):sha(f) for f in case.rglob('*') if f.is_file() and f.name!='FILES.json'})
    archive(a.out/'plan-e-unified-split-0.1.0.zip',[(str(f.relative_to(work)),f) for f in case.rglob('*') if f.is_file()])
    entries=[]
    for label in ['r08','r09','r10']:
        folder=work/'e2e'/label;assert read(folder/'validation.json')['status']=='passed'
        manifest=read(folder/'handoff/manifest.json');assert all(sha(folder/'handoff'/name)==digest for name,digest in manifest['files'].items())
        entries += [(str(f.relative_to(work)),f) for f in folder.rglob('*') if f.is_file() and f.name!='operation_log.json']
    archive(a.out/'pavilion-three-rounds-0.1.0.zip',entries)
    folder=work/'asset-rounds/r09';v=read(folder/'validation.json');assert v['status']=='passed'
    summary=dict(status='passed',scope=v['scope'],dimensions_m=v['dimensions_m'],contact=v['contact'],limits=v['limits'],original_local_report_sha256=sha(folder/'validation.json'))
    atomic(work/'asset-example/validation.json',summary)
    entries=[('asset-example/validation.json',work/'asset-example/validation.json')]
    allowed={'table.blend','table.glb','table.dae','table.png','table_texture.py','roundtrip.skp','native.png'}
    entries += [('asset-example/'+str(f.relative_to(folder)),f) for f in folder.rglob('*') if f.is_file() and (f.name in allowed or 'table_textures' in f.parts)]
    asset=read(folder/'validation.json')['blender']
    manifest={k:asset[k] for k in ['asset_id','bounds','anchor','components','sources','files']}
    manifest['files']={k:dict(v,path='asset-example/'+str(Path(v['path']).relative_to('asset-rounds/r09'))) for k,v in asset['files'].items()}
    atomic(work/'asset-example/asset-manifest.json',manifest)
    entries += [('asset-example/asset-manifest.json',work/'asset-example/asset-manifest.json')]
    entries += [('asset-example/CC0-1.0.txt',root/'LICENSES/CC0-1.0.txt'),('asset-example/GPL-3.0-or-later.txt',root/'LICENSES/GPL-3.0-or-later.txt')]
    archive(a.out/'editable-table-roundtrip-0.1.0.zip',entries)
    atomic(a.out/'SHA256SUMS.json',{f.name:sha(f) for f in a.out.iterdir() if f.is_file() and f.suffix in ['.whl','.gz','.zip','.rbz']})


if __name__=='__main__':main()
