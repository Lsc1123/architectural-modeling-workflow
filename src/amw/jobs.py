"""Owned Blender subprocesses with durable exit receipts and immutable inputs."""
import os
import signal
import subprocess
import sys
import uuid
import hashlib
import json
from pathlib import Path
from .io import atomic, read, sha, within, token, utc, lock


def adapter_path(name):
    source = Path(__file__).resolve().parents[2] / 'adapters' / name
    return source if source.exists() else Path(__file__).parent / 'bundled/adapters' / name


class Jobs:
    def __init__(self, workspace):
        self.root = Path(workspace).expanduser().resolve()
        self.base = self.root / '.amw/jobs'

    def start(self, specification, blender, operation_id=None):
        oid = token(operation_id or uuid.uuid4().hex)
        directory = self.base / oid
        spec = dict(specification)
        client_digest = hashlib.sha256(json.dumps(dict(spec=spec,blender=str(Path(blender).resolve())), sort_keys=True).encode()).hexdigest()
        with lock(self.base / 'submission.lock'):
            if directory.exists():
                old = read(directory / 'job.json')
                if old.get('client_request_sha256',old['request_sha256']) != client_digest:
                    raise ValueError('Operation ID belongs to another asset request')
                return self.status(oid)
            if not spec.get('asset_id') or not spec.get('blend') or not (spec.get('parts') or spec.get('script') or spec.get('source') or spec.get('imports')):
                raise ValueError('Provide asset_id, new blend output and geometry/source/script')
            if not 1<=spec.get('timeout_seconds',600)<=3600:raise ValueError('Asset timeout_seconds must be 1–3600')
            for entry in spec.get('imports',[]):
                if not entry.get('license') or not entry.get('source'):raise ValueError('Imported asset needs provenance and original license')
                if sha(within(self.root,entry['path']))!=entry['sha256']:raise ValueError('Imported asset source changed')
            if spec.get('source'):
                p = within(self.root, spec['source'])
                if sha(p) != spec.get('expected_source_sha256'):
                    raise ValueError('Asset source changed; inspect the user edits first')
            reservation_file=self.base/'output_reservations.json'
            reservations=read(reservation_file) if reservation_file.exists() else {}
            outputs=[str(within(self.root,spec[k])) for k in ('blend','glb','dae','preview') if spec.get(k)]
            if spec.get('dae'):outputs.append(str(within(self.root,str(Path(spec['dae']).with_suffix(''))+'_textures')))
            if len(outputs)!=len(set(outputs)):raise ValueError('Each asset output needs a distinct path')
            for path in outputs:
                if Path(path).exists() or path in reservations:
                    raise FileExistsError('Asset output exists or is reserved; choose a new revision')
            if spec.get('script'):
                spec['script_sha256']=sha(within(self.root,spec['script']))
            digest=hashlib.sha256(json.dumps(spec,sort_keys=True).encode()).hexdigest()
            directory.mkdir(parents=True)
            runner=adapter_path('blender/runner.py');snapshot=directory/'runner.py';snapshot.write_bytes(runner.read_bytes())
            job = dict(operation_id=oid, status='queued', specification=spec,
                       request_sha256=digest, client_request_sha256=client_digest, adapter_sha256=sha(snapshot),workspace=str(self.root), blender=str(Path(blender).resolve()), at=utc())
            atomic(directory / 'job.json', job)
            reservations.update({path:oid for path in outputs});atomic(reservation_file,reservations)
            with (directory / 'worker.log').open('wb') as log:
                process = subprocess.Popen([sys.executable, '-m', 'amw.worker', str(directory)],
                                           stdout=log, stderr=log, start_new_session=True)
            job['worker_pid'] = process.pid
            atomic(directory / 'job.json', job)
        return dict(operation_id=oid, status='queued', worker_pid=process.pid)

    def status(self, operation_id):
        d = self.base / token(operation_id)
        if (d / 'result.json').exists():
            return read(d / 'result.json')
        j = read(d / 'job.json')
        pid = j.get('worker_pid')
        try:
            alive = pid is not None and os.kill(pid, 0) is None
        except ProcessLookupError:
            alive = False
        return dict(operation_id=operation_id, status='running' if alive else 'unknown',
                    recovery='Read this job and its log; do not repeat an unknown write', log=str(d / 'worker.log'))

    def cancel(self, operation_id):
        d = self.base / token(operation_id)
        with lock(d / 'result.lock'):
            if (d / 'result.json').exists(): return read(d / 'result.json')
            j = read(d / 'job.json'); pid = j.get('worker_pid')
            if pid:
                try:
                    if os.getpgid(pid) != pid: raise RuntimeError('Owned worker process group no longer matches')
                    command=subprocess.check_output(['/bin/ps','-p',str(pid),'-o','command='],text=True)
                    if 'amw.worker' not in command or str(d) not in command:raise RuntimeError('Worker identity no longer matches; refusing to signal this PID')
                    atomic(d / 'cancel.json', {'requested_at': utc()})
                    os.killpg(pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
            result = dict(operation_id=operation_id, status='canceled', outputs_valid=False)
            atomic(d / 'result.json', result)
            return result
