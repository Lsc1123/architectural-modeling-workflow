"""Build deterministic RBZ and skill archives; build the Python wheel separately."""
import argparse
import hashlib
import json
import zipfile
from pathlib import Path


def archive(path, entries):
    with zipfile.ZipFile(path,'w',compression=zipfile.ZIP_DEFLATED) as z:
        for name,source in sorted(entries):
            info=zipfile.ZipInfo(name,(2026,1,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED
            info.external_attr=0o100644<<16;z.writestr(info,source.read_bytes())


def main():
    p=argparse.ArgumentParser();p.add_argument('--out',default='dist');a=p.parse_args()
    root=Path(__file__).resolve().parents[1];out=Path(a.out).resolve();out.mkdir(parents=True,exist_ok=True)
    archive(out/'amw-sketchup-0.1.0.rbz',[
        ('amw.rb',root/'adapters/sketchup/amw.rb'),
        ('amw/amw_bridge.rb',root/'adapters/sketchup/amw_bridge.rb'),('amw/LICENSE',root/'LICENSE')])
    skill=root/'skills/architectural-modeling-workflow'
    archive(out/'architectural-modeling-workflow-skill-0.1.0.zip',[
        ('architectural-modeling-workflow/'+str(f.relative_to(skill)),f) for f in skill.rglob('*')
        if f.is_file() and '__pycache__' not in f.parts])
    manifest={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in out.iterdir() if p.is_file() and p.suffix in {'.whl','.gz','.rbz','.zip'}}
    (out/'SHA256SUMS.json').write_text(json.dumps(manifest,indent=2)+'\n');print(json.dumps(manifest,indent=2))


if __name__=='__main__':main()
