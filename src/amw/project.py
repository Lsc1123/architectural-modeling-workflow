"""Project facts, explicit design decisions and evidence-bound stage changes."""
import copy
import uuid
import hashlib
import json
from pathlib import Path
from .io import atomic, read, sha, utc, within, lock
from .evidence import sources_current, evidence_current

STAGES = ('exploration', 'selection', 'development', 'refinement', 'handoff')
GATES = {
    'selection': ('intent_review', 'candidate_comparison'),
    'development': ('selected_baseline',),
    'refinement': ('layout_review', 'circulation', 'native_editability'),
    'handoff': ('geometry', 'usage', 'scope_diff', 'file_readback', 'native_editability', 'display'),
}


def validate(data):
    if data.get('schema_version') != 1 or data.get('stage') not in STAGES:
        raise ValueError('Unsupported project schema or stage')
    rows = data.get('regions', [])
    ids = [r['id'] for r in rows]
    if len(set(ids)) != len(ids):
        raise ValueError('Duplicate region IDs')
    for r in rows:
        if not r.get('function') or not r.get('source'):
            raise ValueError('Each region needs its current function and source')
    for edge in data.get('relations', []):
        if edge.get('kind') not in ('passage', 'sight', 'privacy', 'support', 'adjacency'):
            raise ValueError('Keep passage, sight, privacy and support relations separate')
        if edge['a'] not in ids or edge['b'] not in ids:
            raise ValueError('Relation references an unknown region')
    decisions = {d['id']: d for d in data.get('decisions', [])}
    for stage,models in data.get('requirements',{}).items():
        if stage not in GATES or not isinstance(models,dict):raise ValueError('Requirements use a gated stage and model-label map')
        for label,kinds in models.items():
            if not isinstance(label,str) or not isinstance(kinds,dict) or set(kinds)-set(GATES[stage]):raise ValueError('Unknown required stage evidence kind')
            if any(not isinstance(scopes,list) or not scopes for scopes in kinds.values()):raise ValueError('Required check scopes must be explicit nonempty lists')
    for d in decisions.values():
        if d['status'] not in ('current', 'pending', 'superseded'):
            raise ValueError('Unknown decision status')
        if d['status'] == 'superseded' and d.get('superseded_by') not in decisions:
            raise ValueError('Superseded decision needs an existing replacement')


class Project:
    def __init__(self, workspace):
        self.root = Path(workspace).expanduser().resolve()
        self.path = self.root / '.amw/project.json'

    def init(self, name, brief='', stage='exploration', entry_evidence=''):
        with lock(self.root / '.amw/project.lock'):
            if self.path.exists():
                raise FileExistsError('Project already exists; read it before updating')
            if stage != 'exploration' and not entry_evidence.strip():
                raise ValueError('Entering an existing stage requires an actual handoff/source reference')
            data = dict(schema_version=1, id=str(uuid.uuid4()), name=name, brief=brief,
                        revision=0, stage=stage, entry_evidence=entry_evidence,
                        coordinates={'units': 'm', 'zero_model_z_m': None},
                        regions=[], relations=[], decisions=[], evidence=[],
                        models={}, authority=None, requirements={}, pending=[], history=[])
            validate(data)
            atomic(self.path, data)
            return data

    def get(self):
        data = read(self.path)
        validate(data)
        return data

    def update(self, expected_revision, changes, reason):
        allowed = {'brief', 'coordinates', 'regions', 'relations', 'models', 'pending', 'requirements'}
        if set(changes) - allowed:
            raise ValueError('Use decision/evidence/stage operations for protected records')
        if self.get().get('authority') and {'regions','relations','coordinates'} & changes.keys():
            raise ValueError('Existing fact table is authoritative; update it, then refresh the link instead of creating a second table')
        return self._mutate(expected_revision, reason, lambda d: d.update(copy.deepcopy(changes)))

    def view(self):
        data=self.get();authority=data.get('authority')
        if authority:
            path=within(self.root,authority['path'])
            data['external_context']=read(path)
            data['external_context_sha256']=sha(path)
            data['authority_changed']=data['external_context_sha256']!=authority['sha256']
        return data

    def semantic_digest(self):
        data=self.view()
        basis={k:data.get(k) for k in ['brief','coordinates','regions','relations','decisions','external_context']}
        basis['decisions']=[d for d in data['decisions'] if d['kind'] in ('constraint','spatial_change') and d['status']=='current']
        return hashlib.sha256(json.dumps(basis,sort_keys=True,ensure_ascii=False).encode()).hexdigest()

    def same_model_lineage(self, before_path, after_path):
        """Different files need a recorded common model label, never a guessed variant."""
        before = within(self.root, before_path)
        after = within(self.root, after_path)
        if before == after:
            return True
        data = self.get()
        records = [data]
        for entry in data.get('history', []):
            records.append(read(within(self.root, entry['parent_snapshot'])))
        def labels(path):
            return {label for record in records for label, model in record['models'].items()
                    if within(self.root, model['path']) == path}
        a, b = labels(before), labels(after)
        return len(a) == len(b) == 1 and a == b

    def link_authority(self,expected_revision,path,reason):
        source=within(self.root,path);content=read(source);digest=sha(source)
        data=self.get()
        if data['regions'] or data['relations']:
            raise ValueError('Resolve the existing internal fact table before linking another authority')
        snapshot=self.root/'.amw/authority_snapshots'/(digest+'.json');atomic(snapshot,content)
        record=dict(path=str(source.relative_to(self.root)),sha256=digest,snapshot=str(snapshot.relative_to(self.root)))
        return self._mutate(expected_revision,reason,lambda d:d.update(authority=record))

    def _mutate(self, expected_revision, reason, action):
        if not reason.strip():
            raise ValueError('Record the reason/source for this change')
        with lock(self.root / '.amw/project.lock'):
            data = self.get()
            if data['revision'] != expected_revision:
                raise ValueError('Project revision conflict; reread the latest facts, never restore old data')
            previous=copy.deepcopy(data)
            action(data)
            validate(data)
            snapshot=self.root/'.amw/project_history'/previous['id']/f'{previous["revision"]:06d}.json'
            if snapshot.exists():raise FileExistsError('Immutable project history already exists; inspect concurrent/corrupt state')
            atomic(snapshot,previous)
            data['revision'] += 1
            data['history'].append(dict(at=utc(), revision=data['revision'], reason=reason,parent_snapshot=str(snapshot.relative_to(self.root))))
            atomic(self.path, data)
            return data

    def decide(self, expected_revision, kind, statement, user_source, supersedes=(), status='current'):
        if kind not in ('choose_scheme', 'spatial_change', 'accept_handoff', 'constraint', 'other'):
            raise ValueError('Unknown decision kind')
        if not statement.strip() or not user_source.strip():
            raise ValueError('A decision needs the actual user statement and its source')
        if status=='pending' and supersedes:raise ValueError('A pending proposal cannot supersede a current user decision')
        # The host supplies provenance. This record is not cryptographic proof of user approval.
        record = dict(id=str(uuid.uuid4()), kind=kind, statement=statement,
                      user_source=user_source, status=status, at=utc())
        def action(d):
            by_id = {x['id']: x for x in d['decisions']}
            for old in supersedes:
                if old not in by_id:
                    raise ValueError('Unknown superseded decision')
                by_id[old].update(status='superseded', superseded_by=record['id'])
            d['decisions'].append(record)
        return self._mutate(expected_revision, statement, action)

    def evidence(self, expected_revision, report):
        path = within(self.root, report)
        row = read(path)
        required = {'schema_version', 'kind', 'status', 'scope', 'sources', 'method'}
        if required - row.keys() or row['schema_version']!=1 or row['status'] not in ('passed', 'failed', 'unverified'):
            raise ValueError('Evidence requires kind, status, explicit scope, method and bound sources')
        if not row['scope'] or not row['sources']:
            raise ValueError('Empty scope or unbound evidence cannot pass a stage')
        if not sources_current(self.root, row['sources']):
            raise ValueError('Evidence source changed; rerun the actual check')
        record = dict(id=str(uuid.uuid4()), report=str(path.relative_to(self.root)),
                      sha256=sha(path), kind=row['kind'], status=row['status'],
                      scope=row['scope'], sources=row['sources'], coverage=row.get('coverage','fresh'), at=utc())
        record['semantic_basis_sha256']=self.semantic_digest()
        if row.get('semantic_basis_sha256') and row['semantic_basis_sha256']!=record['semantic_basis_sha256']:
            raise ValueError('Design facts changed after this report; rerun or review its actual scope')
        if self.get().get('authority'):
            authority=self.get()['authority']
            if sha(within(self.root,authority['path']))!=authority['sha256']:raise ValueError('Read and reconcile changed authoritative context before registering checks')
            record['context_sha256']=authority['sha256']
        return self._mutate(expected_revision, 'Register ' + row['kind'], lambda d: d['evidence'].append(record))

    def gate(self, target):
        data = self.get()
        if target not in STAGES:
            raise ValueError('Unknown target stage')
        required = GATES.get(target, ())
        missing = []
        authority=data.get('authority')
        if authority:
            try:
                if sha(within(self.root,authority['path']))!=authority['sha256']:missing.append('authoritative_context_changed')
            except OSError:missing.append('authoritative_context_missing')
        if target in ('development','refinement','handoff'):
            if not data['models']: missing.append('current_model_baseline')
            for label,model in data['models'].items():
                try:
                    if sha(within(self.root,model['path']))!=model['sha256']: missing.append('model_changed:'+label)
                except (OSError,KeyError): missing.append('model_missing:'+label)
        semantic=self.semantic_digest();cache={}
        def valid(e):
            if e['id'] in cache:return cache[e['id']]
            result = e['status'] == 'passed' and evidence_current(self.root, e, semantic, authority)
            cache[e['id']]=result;return result
        labels=data['models'] if target in ('development','refinement','handoff') and data['models'] else {'project':None}
        for label,model in labels.items():
            contract=data.get('requirements',{}).get(target,{}).get(label,{})
            for kind in required:
                candidates=[e for e in data['evidence'] if e['kind']==kind and (not model or any(s['path']==model['path'] for s in e['sources']))]
                wanted=contract.get(kind)
                if target in ('refinement','handoff') and not wanted:
                    missing.append(f'{kind}:{label}:required_scope_not_declared');continue
                if wanted:
                    key=lambda value:json.dumps(value,sort_keys=True,ensure_ascii=False)
                    for scope in wanted:
                        matching=[e for e in candidates if key(scope) in {key(s) for s in e['scope']}]
                        if not matching or not valid(matching[-1]):missing.append(f'{kind}:{label}:missing_or_stale_scope:{key(scope)}')
                elif not candidates or not valid(candidates[-1]):missing.append(f'{kind}:{label}:missing_or_stale')
        decision = 'choose_scheme' if target in ('selection', 'development') else 'accept_handoff' if target == 'handoff' else None
        if decision and not any(d['kind'] == decision and d['status'] == 'current' for d in data['decisions']):
            missing.append('user_decision:' + decision)
        return dict(target=target, ready=not missing, missing=missing,
                    note='Evidence covers its declared scope, not the whole building automatically')

    def advance(self, expected_revision, target, reason):
        data = self.get()
        if STAGES.index(target) != STAGES.index(data['stage']) + 1:
            raise ValueError('Advance one stage; use reopen for a scoped return')
        gate = self.gate(target)
        if not gate['ready']:
            raise ValueError('Stage conditions missing: ' + ', '.join(gate['missing']))
        return self._mutate(expected_revision, reason, lambda d: d.update(stage=target))

    def reopen(self, expected_revision, target, reason):
        if target not in STAGES or STAGES.index(target) >= STAGES.index(self.get()['stage']):
            raise ValueError('Reopen an earlier affected stage')
        return self._mutate(expected_revision, reason, lambda d: d.update(stage=target))
