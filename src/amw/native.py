"""Correlated, replay-safe file IPC to the SketchUp main-thread extension."""
import hashlib
import json
import time
import uuid
from pathlib import Path
from .io import atomic, read, within, token, lock, sha
from .jobs import adapter_path


class Native:
    def __init__(self, workspace):
        self.root = Path(workspace).expanduser().resolve()
        self.runtime = self.root / '.amw/runtime/sketchup'

    def state(self):
        p = self.runtime / 'session.json'
        if not p.exists():
            return dict(connected=False, instruction='In SketchUp choose Extensions → AMW → Connect project and select this workspace')
        data = read(p)
        data['connected'] = time.time() - data.get('heartbeat_unix', 0) < 5
        return data

    def submit(self, operation, arguments=None, expected_revision=None, operation_id=None):
        oid = token(operation_id or uuid.uuid4().hex)
        body = dict(id=oid, operation=operation, arguments=arguments or {}, expected_revision=expected_revision)
        digest = hashlib.sha256(json.dumps(body, sort_keys=True, allow_nan=False).encode()).hexdigest()
        body['request_sha256'] = digest
        base = self.runtime / 'operations' / oid
        with lock(self.runtime / 'submission.lock'):
            if (base / 'request.json').exists():
                old = read(base / 'request.json')
                if old['request_sha256'] != digest:
                    raise ValueError('Operation ID already belongs to different arguments')
                return dict(self.poll(oid),operation_id=oid,replayed=True)
            live=self.state()
            if not live.get('connected'):
                raise ConnectionError('SketchUp bridge is not connected to this workspace')
            if expected_revision is not None and live.get('bridge_sha256')!=sha(adapter_path('sketchup/amw_bridge.rb')):
                raise ConnectionError('Installed SketchUp bridge does not match this service; preserve work and install/restart the matching RBZ before writing')
            atomic(base / 'request.json', body)
            atomic(base / 'status.json', dict(status='queued', request_sha256=digest))
            atomic(self.runtime / 'queue' / (oid + '.json'), body)
        return dict(operation_id=oid, status='queued')

    @staticmethod
    def client_digest(arguments):
        return hashlib.sha256(json.dumps(arguments,sort_keys=True,allow_nan=False).encode()).hexdigest()

    def recover(self, operation_id, client_arguments):
        """Check a compiled geometry request before taking another changing snapshot."""
        request=self.runtime/'operations'/token(operation_id)/'request.json'
        if not request.exists(): return None
        old=read(request)
        if old['arguments'].get('client_request_sha256')!=self.client_digest(client_arguments):
            raise ValueError('Operation ID belongs to different client arguments')
        return dict(self.poll(operation_id),operation_id=operation_id,replayed=True)

    def poll(self, operation_id):
        base = self.runtime / 'operations' / token(operation_id)
        if not base.exists():
            raise FileNotFoundError('Unknown native operation')
        result = base / 'result.json'
        if result.exists():
            return read(result)
        state = read(base / 'status.json')
        if state['status'] == 'running' and not self.state().get('connected'):
            return dict(state, operation_id=operation_id, status='unknown', recovery='Reconnect and inspect the same operation. Never resend a write with a new ID.')
        return dict(state,operation_id=operation_id)

    def wait(self, operation_id, timeout=25):
        deadline = time.monotonic() + min(max(timeout, 0), 55)
        while True:
            result = self.poll(operation_id)
            if result['status'] not in ('queued', 'running') or time.monotonic() >= deadline:
                return dict(result, operation_id=operation_id)
            time.sleep(.1)

    def call(self, operation, arguments=None, expected_revision=None, operation_id=None, timeout=25):
        job = self.submit(operation, arguments, expected_revision, operation_id)
        result=self.wait(job['operation_id'], timeout)
        if job.get('replayed'):result['replayed']=True
        return result

    def cancel(self, operation_id):
        base = self.runtime / 'operations' / token(operation_id)
        state = self.poll(operation_id)
        if state['status'] == 'queued':
            atomic(base / 'cancel.json', dict(requested=True))
            return dict(status='cancel_requested', operation_id=operation_id)
        return dict(status=state['status'], instruction='A running SketchUp transaction is atomic; await its result, then undo if needed')

    def snapshot(self, relative_path='.amw/geometry/current.json'):
        result = self.call('export', {'path': relative_path})
        if result['status'] != 'completed':
            raise RuntimeError(result)
        return read(within(self.root, relative_path))
