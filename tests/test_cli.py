# SPDX-License-Identifier: MIT
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class WrapperTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.tool = self.root / 'upstream'
        self.tool.write_text('#!' + sys.executable + '\nimport sys,json\nprint(json.dumps(sys.argv[1:]))\nsys.exit(23)\n')
        self.tool.chmod(0o755)
        self.env = {**os.environ, 'PYTHONPATH': str(ROOT), 'JB_PURIFIER_JB': str(self.tool)}
        self.env.pop('JB_PURIFIER_LOCKFILE', None)
        self.env.pop('JB_PURIFIER_TOOL_LOCKFILE', None)

    def call(self, *args):
        return subprocess.run([sys.executable, '-m', 'jb_purifier.cli', *args], cwd=self.root, env=self.env, capture_output=True, text=True)

    def test_unlocked_delegation_preserves_args_and_status(self):
        result = self.call('native', 'install', 'argument with spaces')
        self.assertEqual(result.returncode, 23)
        self.assertEqual(json.loads(result.stdout), ['install', 'argument with spaces'])
        self.assertIn('warning', result.stderr)
        self.assertIn('impure', result.stderr)
        self.assertFalse((self.root / 'jb-purifier.lock.json').exists())

    def test_invalid_lock_never_delegates(self):
        (self.root / 'jb-purifier.lock.json').write_text('not json')
        result = self.call('native', 'install')
        self.assertEqual(result.returncode, 1)
        self.assertNotIn('impure', result.stderr)
        self.assertIn('jb-purifier lock', result.stderr)
        self.assertEqual(result.stdout, '')

    def test_external_lock_selected(self):
        external = self.root / 'external.json'
        external.write_text('{}')
        self.env['JB_PURIFIER_LOCKFILE'] = str(external)
        result = self.call('native', 'install')
        self.assertEqual(result.returncode, 1)
        self.assertNotIn('impure', result.stderr)

    def test_explicit_external_lock_has_precedence(self):
        self.env['JB_PURIFIER_LOCKFILE'] = str(self.root / 'absent')
        (self.root / 'external.json').write_text('{}')
        result = self.call('--lockfile', 'external.json', 'native', 'install')
        self.assertEqual(result.returncode, 1)
        self.assertNotIn('impure', result.stderr)

if __name__ == '__main__':
    unittest.main()
