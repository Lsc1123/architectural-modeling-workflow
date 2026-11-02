"""Supervisor writes success only after Blender has actually exited with code 0."""
import subprocess
import sys
import traceback
from pathlib import Path
from .io import atomic, read, within, sha, utc, lock


def main():
    d = Path(sys.argv[1]).resolve(); job = read(d / 'job.json')
    spec = job['specification']; root = Path(job['workspace'])
    try:
        if (d / 'cancel.json').exists(): return
        if spec.get('source') and sha(within(root, spec['source'])) != spec['expected_source_sha256']:
            raise ValueError('Asset input changed before worker start')
        if spec.get('script') and sha(within(root, spec['script'])) != spec['script_sha256']:
            raise ValueError('Asset script changed before worker start')
        for entry in spec.get('imports',[]):
            if sha(within(root,entry['path']))!=entry['sha256']:raise ValueError('Imported asset source changed before worker start')
        for kind in ['blend','glb','dae','preview']:
            if spec.get(kind) and within(root,spec[kind]).exists():raise FileExistsError('Asset output appeared after submission; preserved existing file')
        request = dict(spec, workspace=str(root), result=str(d / 'blender_result.json'),working_blend=str((d/'working.blend').relative_to(root)))
        atomic(d / 'request.json', request)
        runner=d/'runner.py'
        if sha(runner)!=job['adapter_sha256']:raise ValueError('Captured Blender adapter changed')
        command = [job['blender'], '--background', '--factory-startup', '--python-exit-code', '1',
                   '--python', str(runner), '--', str(d / 'request.json')]
        with (d / 'blender.log').open('wb') as log:
            p = subprocess.run(command, stdout=log, stderr=log,timeout=spec.get('timeout_seconds',600))
        if (d / 'cancel.json').exists(): return
        detail = read(d / 'blender_result.json') if (d / 'blender_result.json').exists() else {}
        ok = p.returncode == 0 and detail.get('status') == 'completed'
        if ok:
            verify = dict(mode='verify', workspace=str(root), expected=detail, result=str(d/'verification.json'))
            atomic(d/'verify_request.json',verify)
            verify_command = [job['blender'],'--background','--factory-startup','--python-exit-code','1',
                              '--python',str(runner),'--',str(d/'verify_request.json')]
            with (d/'verification.log').open('wb') as log:
                verified = subprocess.run(verify_command,stdout=log,stderr=log,timeout=spec.get('timeout_seconds',600))
            proof=read(d/'verification.json') if (d/'verification.json').exists() else {}
            detail['verification']=dict(exit_code=verified.returncode,**proof)
            ok=verified.returncode==0 and proof.get('status')=='completed'
        if spec.get('source') and sha(within(root,spec['source']))!=spec['expected_source_sha256']:raise ValueError('Source changed while task was running; output is not accepted')
        if spec.get('script') and sha(within(root,spec['script']))!=spec['script_sha256']:raise ValueError('Script changed while task was running')
        for entry in spec.get('imports',[]):
            if sha(within(root,entry['path']))!=entry['sha256']:raise ValueError('Imported asset source changed while task was running')
        with lock(d/'result.lock'):
            if not (d/'cancel.json').exists():
                atomic(d / 'result.json', dict(operation_id=job['operation_id'],
                       status='completed' if ok else 'failed', exit_code=p.returncode,
                       finished_at=utc(),adapter_sha256=job['adapter_sha256'], result=detail, log=str(d / 'blender.log')))
    except Exception as e:
        with lock(d/'result.lock'):
            if not (d / 'cancel.json').exists():
                atomic(d / 'result.json', dict(operation_id=job['operation_id'], status='failed',
                       error=str(e),error_type=type(e).__name__,outputs_valid=False,traceback=traceback.format_exc()))


if __name__ == '__main__': main()
