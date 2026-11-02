"""Check portable public packages and all embedded manifest hashes offline."""
import argparse
import hashlib
import json
import tarfile
import zipfile
from pathlib import Path,PurePosixPath
from amw.io import sha


def member_name(name):
    path=PurePosixPath(name)
    assert not path.is_absolute() and '..' not in path.parts and '\\' not in name,name
    assert 'operation_log.json' not in path.parts and 'validation/local' not in name,name
    return path


def content_digest(name, stream):
    path=member_name(name);h=hashlib.sha256();previous=b''
    private_prefix=str(Path.home()).encode()+b'/'
    while block:=stream.read(1024**2):
        h.update(block)
        if path.suffix in ['.json','.md','.py','.rb','.dae','.txt','.toml','.yml','.yaml']:
            assert private_prefix not in previous+block,name
            assert b'gh'+b'o_' not in previous+block,name
            previous=block[-max(100,len(private_prefix)):]
    return h.hexdigest()


def main():
    p=argparse.ArgumentParser();p.add_argument('--dist',type=Path,default=Path('dist'));a=p.parse_args()
    manifest=json.loads((a.dist/'SHA256SUMS.json').read_text())
    artifacts={f.name for f in a.dist.iterdir() if f.is_file() and f.suffix in {'.whl','.gz','.rbz','.zip'}}
    assert set(manifest)==artifacts,'Manifest must cover every distribution artifact exactly'
    for name,digest in manifest.items():
        assert PurePosixPath(name).name==name,name
        member_name(name)
        assert sha(a.dist/name)==digest,name
    for path in a.dist.iterdir():
        if path.suffix not in ['.zip','.whl','.rbz']:continue
        with zipfile.ZipFile(path) as z:
            digests={}
            for entry in z.infolist():
                member_name(entry.filename)
                if entry.is_dir():continue
                with z.open(entry) as f:
                    digests[entry.filename]=content_digest(entry.filename,f)
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
                member_name(member.name)
                assert member.isfile() or member.isdir(),member.name
                if member.isfile():
                    with t.extractfile(member) as f:content_digest(member.name,f)
        print('Verified source archive',path.name)


if __name__=='__main__':main()
