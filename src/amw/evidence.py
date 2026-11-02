"""Shared source freshness checks; validity never implies a report passed."""
from .io import sha, within


def sources_current(root, sources):
    if not sources:
        return False
    try:
        return all(sha(within(root, s['path'])) == s['sha256'] for s in sources)
    except (OSError, KeyError, ValueError):
        return False


def evidence_current(root, record, semantic, authority=None):
    """Accept a raw report or registered record, with the same freshness rules."""
    sources = list(record.get('sources', []))
    if 'report' in record:
        sources.append(dict(path=record['report'], sha256=record.get('sha256')))
    if record.get('semantic_basis_sha256') != semantic or not semantic:
        return False
    if authority:
        if record.get('context_sha256') != authority['sha256']:
            return False
        sources.append(authority)
    return sources_current(root, sources)
