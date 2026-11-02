import copy
import json
import tempfile
import unittest
from pathlib import Path
from jb_purifier import lock


class LockTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.dep = {'source': {'git': {'remote': 'https://github.com/example/lib.git', 'subdir': 'jsonnet'}}, 'version': 'a' * 40, 'sum': 'native-checksum'}
        self.manifest = {'version': 1, 'dependencies': [self.dep], 'legacyImports': True}
        (self.root / 'jsonnetfile.json').write_text(json.dumps(self.manifest))
        (self.root / 'jsonnetfile.lock.json').write_text(json.dumps(self.manifest))
        (self.root / 'main.jsonnet').write_text('{answer: 42}')
        self.data = lock.make_lock(self.root, self.root / 'jsonnetfile.lock.json', {'github.com/example/lib/jsonnet': 'sha256-' + 'A' * 43 + '='}, {'main': {'file': 'main.jsonnet'}})

    def test_valid(self):
        self.assertEqual(lock.problems(self.root, self.root / 'jsonnetfile.lock.json', self.data), [])

    def test_content_hash_is_canonical(self):
        self.assertEqual(lock.digest({'z': 'é', 'a': 2}), lock.digest({'a': 2, 'z': 'é'}))
        self.assertEqual(lock.seal(copy.deepcopy(self.data)), self.data)

    def test_stale_manifest(self):
        (self.root / 'jsonnetfile.json').write_text('{}')
        self.assertIn('jsonnetfile.json', ' '.join(lock.problems(self.root, self.root / 'jsonnetfile.lock.json', self.data)))

    def test_stale_native_lock(self):
        (self.root / 'jsonnetfile.lock.json').write_text('{}')
        self.assertIn('jsonnetfile.lock.json', ' '.join(lock.problems(self.root, self.root / 'jsonnetfile.lock.json', self.data)))

    def test_tampered(self):
        self.data['outputs'] = {}
        self.assertIn('contentHash', ' '.join(lock.problems(self.root, self.root / 'jsonnetfile.lock.json', self.data)))

    def test_missing_hash_even_when_resealed(self):
        self.data['hashes'] = {}
        self.assertIn('github.com/example/lib/jsonnet', ' '.join(lock.problems(self.root, self.root / 'jsonnetfile.lock.json', lock.seal(self.data))))

    def test_no_mutable_git_revision(self):
        self.dep['version'] = 'main'
        with self.assertRaisesRegex(ValueError, 'commit'):
            lock.git_dependency(self.dep)

    def test_subdirectory_cannot_escape(self):
        self.dep['source']['git']['subdir'] = '../escape'
        with self.assertRaisesRegex(ValueError, 'path'):
            lock.git_dependency(self.dep)

    def test_remote_cannot_escape(self):
        self.dep['source']['git']['remote'] = 'https://github.com/example/../escape.git'
        with self.assertRaisesRegex(ValueError, 'path'):
            lock.git_dependency(self.dep)

    def test_unknown_sources_rejected(self):
        with self.assertRaisesRegex(ValueError, 'local'):
            lock.git_dependency({'source': {'local': {'directory': '../lib'}}})

    def test_output_path_cannot_escape(self):
        self.data['outputs']['main']['file'] = '../secret.jsonnet'
        self.assertTrue(lock.problems(self.root, self.root / 'jsonnetfile.lock.json', lock.seal(self.data)))

    def test_invalid_format(self):
        for value in ([], {}, {'version': 99}, {'version': 1, 'hashes': []}):
            self.assertTrue(lock.problems(self.root, self.root / 'jsonnetfile.lock.json', value))

    def test_duplicate_dependencies_rejected(self):
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            lock.dependencies({'version': 1, 'dependencies': [self.dep, self.dep]})

    def test_custom_alias(self):
        self.dep['name'] = 'my-lib'
        self.assertEqual(lock.git_dependency(self.dep)['alias'], 'my-lib')

    def test_alias_cannot_escape(self):
        self.dep['name'] = '../lib'
        with self.assertRaises(ValueError):
            lock.git_dependency(self.dep)

    def test_different_schemes_share_vendor_name(self):
        self.dep['source']['git']['remote'] = 'ssh://git@github.com/example/lib.git'
        self.assertEqual(lock.git_dependency(self.dep)['name'], 'github.com/example/lib/jsonnet')

    def test_hashes_do_not_duplicate_native_coordinates(self):
        self.assertNotIn('source', json.dumps(self.data))
        self.assertNotIn('version', self.data['hashes'])


if __name__ == '__main__':
    unittest.main()
