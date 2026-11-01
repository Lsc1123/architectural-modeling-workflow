#!/usr/bin/env python3
"""File lineage only. Never edits models and never certifies geometry or design."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
from datetime import datetime, timezone


def now():
    return datetime.now(timezone.utc).isoformat()


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def write_json(path, data, expected=None):
    """Atomic replacement; refuse an observed concurrent manifest edit."""
    text = json.dumps(data, ensure_ascii=False, indent=2) + '\n'
    if expected is None:
        with path.open('x', encoding='utf-8') as stream:
            stream.write(text)
        return
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
                                     prefix='.manifest-', delete=False) as stream:
        tmp = Path(stream.name)
        stream.write(text)
    try:
        if sha(path) != expected:
            raise ValueError('manifest changed during registration; reread before retrying')
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def load(path):
    data = json.loads(path.read_text(encoding='utf-8'))
    if data.get('schema_version') != 1:
        raise ValueError('unsupported manifest schema')
    rows = [data['source'], *data['artifacts']]
    if data['source']['id'] != 'source':
        raise ValueError('source id must be source')
    ids = [row['id'] for row in rows]
    if len(ids) != len(set(ids)):
        raise ValueError('duplicate artifact id')
    for row in rows:
        if not Path(row['path']).is_absolute():
            raise ValueError('manifest paths must be absolute')
        if not re.fullmatch(r'[0-9a-f]{64}', row['sha256']):
            raise ValueError('invalid sha256 for ' + row['id'])
        if row['id'] != 'source' and not row.get('dependencies'):
            raise ValueError('artifact has no declared dependency: ' + row['id'])
    return data


def audit(data):
    rows = {r['id']: r for r in [data['source'], *data['artifacts']]}
    results, visiting = {}, set()

    def visit(identifier):
        if identifier in results:
            return results[identifier]
        if identifier in visiting:
            raise ValueError('dependency cycle at ' + identifier)
        visiting.add(identifier)
        row = rows[identifier]
        path = Path(row['path'])
        issues = []
        if not path.is_file():
            issues.append('missing_file')
            actual = None
        else:
            actual = sha(path)
            if actual != row['sha256']:
                issues.append('file_changed')
        for dep in row.get('dependencies', []):
            target = rows.get(dep['id'])
            if target is None:
                issues.append('missing_dependency:' + dep['id'])
                continue
            if dep['sha256'] != target['sha256']:
                issues.append('dependency_baseline_changed:' + dep['id'])
            if visit(dep['id'])['status'] != 'consistent':
                issues.append('stale_dependency:' + dep['id'])
        visiting.remove(identifier)
        results[identifier] = {'id': identifier, 'path': str(path),
                               'status': 'stale' if issues else 'consistent',
                               'issues': issues, 'actual_sha256': actual}
        return results[identifier]

    for identifier in rows:
        visit(identifier)
    return list(results.values())


def init(args):
    source = Path(args.source).resolve(strict=True)
    if not source.is_file():
        raise ValueError('source must be a regular file')
    out = Path(args.out).resolve()
    assets = Path(__file__).resolve().parents[1] / 'assets'
    names = ['project-brief.md', 'iteration.md', 'release.md']
    for name in ['manifest.json', *names]:
        if (out / name).exists():
            raise ValueError('refusing to overwrite existing file: ' + str(out / name))
    for name in names:
        if not (assets / name).is_file():
            raise ValueError('missing template: ' + name)
    out.mkdir(parents=True, exist_ok=True)
    data = {'schema_version': 1, 'project': args.name, 'created_at_utc': now(),
            'scope': 'file_lineage_only_not_geometry_validation',
            'source': {'id': 'source', 'path': str(source), 'sha256': sha(source)},
            'artifacts': []}
    write_json(out / 'manifest.json', data)
    for name in names:
        with (assets / name).open('rb') as src, (out / name).open('xb') as dst:
            shutil.copyfileobj(src, dst)
    return {'manifest': str(out / 'manifest.json'), 'source_sha256': data['source']['sha256'],
            'model_modified': False}, 0


def register(args):
    path = Path(args.manifest).resolve(strict=True)
    before = sha(path)
    data = load(path)
    rows = {r['id']: r for r in [data['source'], *data['artifacts']]}
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', args.id):
        raise ValueError('id must use letters, digits, underscores or hyphens')
    if args.id in rows:
        raise ValueError('id already registered; use a new revision, never overwrite evidence')
    depends = list(dict.fromkeys(args.depends or ['source']))
    unknown = set(depends) - set(rows)
    if unknown:
        raise ValueError('unknown dependencies: ' + ', '.join(sorted(unknown)))
    results = {r['id']: r for r in audit(data)}
    # Source is always required, even when an intermediate artifact is the direct dependency.
    if any(results[i]['status'] != 'consistent' for i in ['source', *depends]):
        raise ValueError('source or dependency changed; verify work and initialize a new revision')
    artifact = Path(args.file).resolve(strict=True)
    if not artifact.is_file() or artifact == path or any(artifact == Path(r['path']) for r in rows.values()):
        raise ValueError('artifact must be a distinct regular output file')
    record = {'id': args.id, 'kind': args.kind, 'path': str(artifact), 'sha256': sha(artifact),
              'registered_at_utc': now(), 'note': args.note,
              'dependencies': [{'id': i, 'sha256': rows[i]['sha256']} for i in depends],
              'provenance': 'operator_declared_not_content_verified'}
    data['artifacts'].append(record)
    # Catch changes while hashing/reading inputs before publishing the registration.
    if any(r['status'] != 'consistent' for r in audit(data) if r['id'] in ['source', args.id]):
        raise ValueError('input or output changed during registration; retry after inspecting state')
    write_json(path, data, expected=before)
    return {'registered': record, 'model_modified': False}, 0


def check(args):
    data = load(Path(args.manifest))
    results = audit(data)
    ok = all(r['status'] == 'consistent' for r in results)
    return {'project': data['project'], 'file_lineage_consistent': ok,
            'design_and_geometry': 'not_evaluated',
            'dependency_provenance': 'operator_declared_not_content_verified',
            'artifacts': results}, 0 if ok else 2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('init', help='Create revision manifest and working templates')
    p.add_argument('--source', required=True)
    p.add_argument('--out', required=True)
    p.add_argument('--name', required=True)
    p.set_defaults(run=init)
    p = sub.add_parser('register', help='Declare an output and its verified source dependencies')
    p.add_argument('--manifest', required=True)
    p.add_argument('--id', required=True)
    p.add_argument('--file', required=True)
    p.add_argument('--kind', choices=['data','report','drawing','render','walk','print','preview','other'], required=True)
    p.add_argument('--depends', action='append')
    p.add_argument('--note', default='')
    p.set_defaults(run=register)
    p = sub.add_parser('check', help='Check file identity and dependency staleness only')
    p.add_argument('--manifest', required=True)
    p.set_defaults(run=check)
    args = parser.parse_args()
    try:
        result, code = args.run(args)
    except (ValueError, OSError, KeyError, TypeError) as exc:
        result, code = {'error': str(exc), 'design_and_geometry': 'not_evaluated'}, 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return code


if __name__ == '__main__':
    sys.exit(main())
