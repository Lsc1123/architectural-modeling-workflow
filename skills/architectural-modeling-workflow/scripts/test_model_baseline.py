"""Behavior tests with synthetic files; never touches a real model."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).with_name('model_baseline.py')


class BaselineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.source = self.root / '用户模型.skp'
        self.source.write_bytes(b'original-model')
        self.out = self.root / 'R01'
        self.manifest = self.out / 'manifest.json'
        self.call('init', '--source', self.source, '--out', self.out, '--name', '测试')

    def tearDown(self):
        self.tmp.cleanup()

    def call(self, *args, expected=0):
        result = subprocess.run([sys.executable, str(SCRIPT), *map(str, args)],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, expected, result.stderr + result.stdout)
        return json.loads(result.stdout)

    def add(self, identifier, dependency='source'):
        p = self.root / (identifier + '.json')
        p.write_text('{}')
        self.call('register', '--manifest', self.manifest, '--id', identifier,
                  '--file', p, '--kind', 'report', '--depends', dependency)
        return p

    def test_source_is_read_only_and_templates_are_created(self):
        self.assertEqual(self.source.read_bytes(), b'original-model')
        self.assertTrue((self.out / 'iteration.md').is_file())
        result = self.call('check', '--manifest', self.manifest)
        self.assertTrue(result['file_lineage_consistent'])
        self.assertEqual(result['design_and_geometry'], 'not_evaluated')

    def test_init_cannot_overwrite_prior_revision(self):
        old = self.manifest.read_bytes()
        self.call('init', '--source', self.source, '--out', self.out, '--name', '重复', expected=1)
        self.assertEqual(self.manifest.read_bytes(), old)

    def test_source_change_invalidates_transitive_outputs(self):
        self.add('geometry')
        self.add('drawing', 'geometry')
        self.source.write_bytes(b'user-manual-edit')
        result = self.call('check', '--manifest', self.manifest, expected=2)
        self.assertTrue(all(x['status'] == 'stale' for x in result['artifacts']))
        self.assertEqual(self.source.read_bytes(), b'user-manual-edit')

    def test_output_change_invalidates_only_its_dependents(self):
        geo = self.add('geometry')
        self.add('drawing', 'geometry')
        self.add('independent')
        geo.write_text('{"changed":true}')
        result = self.call('check', '--manifest', self.manifest, expected=2)
        states = {x['id']: x['status'] for x in result['artifacts']}
        self.assertEqual(states, {'source':'consistent', 'geometry':'stale',
                                  'drawing':'stale', 'independent':'consistent'})

    def test_missing_output_is_stale(self):
        self.add('report').unlink()
        result = self.call('check', '--manifest', self.manifest, expected=2)
        self.assertIn('missing_file', result['artifacts'][-1]['issues'])

    def test_register_cannot_bless_changed_source(self):
        p = self.root / 'new.json'
        p.write_text('{}')
        self.source.write_bytes(b'changed')
        old = self.manifest.read_bytes()
        self.call('register', '--manifest', self.manifest, '--id', 'new',
                  '--file', p, '--kind', 'report', expected=1)
        self.assertEqual(self.manifest.read_bytes(), old)

    def test_duplicate_id_cannot_replace_evidence(self):
        p = self.add('report')
        old = self.manifest.read_bytes()
        self.call('register', '--manifest', self.manifest, '--id', 'report',
                  '--file', p, '--kind', 'report', expected=1)
        self.assertEqual(self.manifest.read_bytes(), old)

    def test_cycle_is_an_error_not_a_false_pass(self):
        self.add('a')
        self.add('b', 'a')
        d = json.loads(self.manifest.read_text())
        d['artifacts'][0]['dependencies'] = [{'id':'b','sha256':d['artifacts'][1]['sha256']}]
        self.manifest.write_text(json.dumps(d))
        self.call('check', '--manifest', self.manifest, expected=1)


if __name__ == '__main__':
    unittest.main()
