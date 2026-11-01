"""Install the two owned extension files with a recoverable backup; restart SU."""
import argparse
import datetime
import shutil
import tempfile
import zipfile
from pathlib import Path


def main():
    p=argparse.ArgumentParser();p.add_argument('rbz',type=Path)
    p.add_argument('--plugins-dir',type=Path,default=Path.home()/'Library/Application Support/SketchUp 2026/SketchUp/Plugins')
    a=p.parse_args();plugins=a.plugins_dir.expanduser().resolve()
    if not plugins.is_dir():raise SystemExit('Plugins directory missing; locate the actual SketchUp installation first')
    allowed={'amw.rb','amw/amw_bridge.rb','amw/LICENSE'}
    with zipfile.ZipFile(a.rbz) as z:
        if set(z.namelist())!=allowed:raise SystemExit('Unexpected RBZ contents; inspect the package')
        backup=plugins/'.amw-install-backups'/datetime.datetime.now().strftime('%Y%m%dT%H%M%S%f')
        for name in sorted(allowed):
            dest=plugins/name
            if dest.is_file():
                old=backup/name;old.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(dest,old)
        with tempfile.TemporaryDirectory(prefix='amw-install-') as temporary:
            stage=Path(temporary)
            for name in sorted(allowed):
                dest=plugins/name;dest.parent.mkdir(parents=True,exist_ok=True)
                new=stage/Path(name).name;new.write_bytes(z.read(name));shutil.copy2(new,dest)
    print('Installed AMW. Restart SketchUp, then Extensions → AMW → Connect project.')
    if backup.exists():print('Previous files preserved at',backup)


if __name__=='__main__':main()
