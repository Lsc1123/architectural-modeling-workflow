import importlib.util
import io
import json
import re
import tomllib
from pathlib import Path

import pytest
from amw import __version__

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('verify_release',ROOT/'scripts/verify_release.py')
verifier=importlib.util.module_from_spec(spec)
spec.loader.exec_module(verifier)


def test_release_versions_match():
    version=tomllib.loads((ROOT/'pyproject.toml').read_text())['project']['version']
    assert __version__==version
    assert (ROOT/'skills/architectural-modeling-workflow/LICENSE').read_bytes()==(ROOT/'LICENSE').read_bytes()
    for path,pattern in [('adapters/sketchup/amw.rb',r"extension.version = '([^']+)'"),
                         ('adapters/sketchup/amw_bridge.rb',r"bridge_version: '([^']+)'")]:
        assert re.search(pattern,(ROOT/path).read_text())[1]==version


@pytest.mark.parametrize('name',['../escape.py','/absolute.py','x/validation/local/private.json','x/operation_log.json'])
def test_distribution_rejects_private_and_escaping_members(name):
    with pytest.raises(AssertionError):verifier.member_name(name)


def test_distribution_scans_source_content():
    private=(str(Path.home())+'/secret').encode()
    with pytest.raises(AssertionError):verifier.content_digest('source/config.toml',io.BytesIO(private))
    assert verifier.content_digest('source/config.toml',io.BytesIO(b'version = "example"'))


def test_distribution_rejects_artifact_missing_from_manifest(tmp_path,monkeypatch):
    (tmp_path/'package.whl').write_bytes(b'new artifact built after the manifest')
    (tmp_path/'SHA256SUMS.json').write_text(json.dumps({}))
    monkeypatch.setattr('sys.argv',['verify_release','--dist',str(tmp_path)])
    with pytest.raises(AssertionError,match='every distribution artifact'):
        verifier.main()
