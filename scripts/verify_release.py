"""Check portable public packages and all embedded manifest hashes offline."""
import argparse
import hashlib
import json
import tarfile
import zipfile
from pathlib import Path,PurePosixPath
from amw.io import sha


def main():
    p=argparse.ArgumentParser();p.add_argument('--dist',type=Path,default=Path('dist'));a=p.parse_args()
    manifest=json.loads((a.dist/'SHA256SUMS.json').read_text())
    private_prefix=str(Path.home()).encode()+b'/'
    for name,digest in manifest.items():assert sha(a.dist/name)==digest,name
    for path in a.dist.iterdir():
        if path.suffix not in ['.zip','.whl','.rbz']:continue
        with zipfile.ZipFile(path) as z:
            digests={}
            for entry in z.infolist():
                n=PurePosixPath(entry.filename)
                assert not n.is_absolute() and '..' not in n.parts,entry.filename
                assert 'operation_log.json' not in n.parts and 'validation/local' not in entry.filename,entry.filename
                if entry.is_dir():continue
                h=hashlib.sha256();previous=b''
                with z.open(entry) as f:
                    while block:=f.read(1024**2):
                        h.update(block)
                        if n.suffix in ['.json','.md','.py','.rb','.dae','.txt']:
                            assert private_prefix not in previous+block,entry.filename
                            assert b'gh'+b'o_' not in previous+block,entry.filename
                            previous=block[-100:]
                digests[entry.filename]=h.hexdigest()
            for name in digests:
                if name.endswith('/FILES.json'):
                    for target,digest in json.loads(z.read(name)).items():assert digests[target]==digest,target
                if name.endswith('/handoff/manifest.json'):
                    prefix=name.removesuffix('manifest.json')
                    for target,digest in json.loads(z.read(name))['files'].items():assert digests[prefix+target]==digest,target
                if name.endswith('/asset-manifest.json'):
                    for record in json.loads(z.read(name))['files'].values():assert digests[record['path']]==record['sha256'],record
            print('Verified',path.name,'files',len(digests),flush=True)
    for path in a.dist.glob('*.tar.gz'):
        with tarfile.open(path) as t:
            for member in t.getmembers():
                assert 'validation/local' not in member.name and not member.name.startswith('/'),member.name
        print('Verified source archive',path.name)


if __name__=='__main__':main()
