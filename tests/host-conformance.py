#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Networked conformance checks; sandboxed checks live in default.nix."""
import json
import os
import shutil
import sys
import subprocess
import tempfile
from pathlib import Path

mode = sys.argv[1] if len(sys.argv) > 1 else 'all'
assert mode in ('all', 'relock', 'update', 'external')
repository = Path(__file__).resolve().parents[1]
cli = Path(subprocess.check_output(['nix', 'build', str(repository), '--no-link', '--print-out-paths'], text=True).strip())
env = {**os.environ, 'PATH': str(cli / 'bin') + ':' + os.environ['PATH']}
for key in ['JB_PURIFIER_LOCKFILE', 'JB_PURIFIER_TOOL_LOCKFILE']:
    env.pop(key, None)


def command(*args, cwd, **kwargs):
    return subprocess.run(args, cwd=cwd, env=env, check=True, **kwargs)


def copy_fixture(destination):
    shutil.copytree(repository / 'examples/ascii', destination, copy_function=shutil.copyfile, ignore=shutil.ignore_patterns('vendor', '.jb-purifier'))


with tempfile.TemporaryDirectory(prefix='jb-conformance-') as temp:
    root = Path(temp)
    project = root / 'project'
    copy_fixture(project)
    native = project / 'jsonnetfile.lock.json'
    sidecar = project / 'jb-purifier.lock.json'
    before = native.read_bytes(), sidecar.read_bytes()
    if mode in ('all', 'relock'):
        command('jb-purifier', 'lock', cwd=project)
        command('jb-purifier', 'lock', cwd=project)
        assert before == (native.read_bytes(), sidecar.read_bytes()), 'relock changed fixture bytes'
        print('conformance-relock: byte-identical', flush=True)
    if mode in ('all', 'external'):
        command('jb-purifier', 'prefetch', cwd=project)
        command('jb', 'install', cwd=project)
        command('jsonnet', '-J', 'vendor', 'main.jsonnet', cwd=project)
        command('jb', '--version', cwd=project)
        assert not list(project.glob('*.nix')), 'generated project Nix files'
        assert (project / 'vendor').resolve().is_relative_to('/nix/store')
        runtime = list((project / '.jb-purifier').glob('*/runtime'))
        assert runtime and (runtime[0] / 'bin/jsonnet-language-server').exists()
        # Keep source locks unchanged while resolving and preparing external ones.
        external = root / 'locks'
        external.mkdir()
        env['JB_PURIFIER_LOCKFILE'] = str(external / 'jb-purifier.lock.json')
        env['JB_PURIFIER_TOOL_LOCKFILE'] = str(external / 'jsonnetfile.lock.json')
        command('jb-purifier', 'lock', cwd=project)
        command('jb-purifier', 'prefetch', cwd=project)
        assert before == (native.read_bytes(), sidecar.read_bytes())
        assert before == ((external / 'jsonnetfile.lock.json').read_bytes(), (external / 'jb-purifier.lock.json').read_bytes())
        assert list((external / '.jb-purifier').glob('*/runtime'))
        print('conformance-external: source locks unchanged and external GC roots prepared', flush=True)
        for key in ['JB_PURIFIER_LOCKFILE', 'JB_PURIFIER_TOOL_LOCKFILE']:
            env.pop(key, None)
    if mode in ('all', 'update'):
        # Seed an old upstream commit, then exercise jb's named native update.
        update = root / 'update'
        copy_fixture(update)
        (update / 'jsonnetfile.lock.json').unlink()
        (update / 'jb-purifier.lock.json').unlink()
        manifest_path = update / 'jsonnetfile.json'
        manifest = json.loads(manifest_path.read_text())
        previous = 'ed544d72f3afd3c9568bb35af70d1814038812a4'
        manifest['dependencies'][0]['version'] = previous
        manifest_path.write_text(json.dumps(manifest, indent=2) + '\n')
        command('jb-purifier', 'lock', cwd=update)
        manifest['dependencies'][0]['version'] = 'master'
        manifest_path.write_text(json.dumps(manifest, indent=2) + '\n')
        command('jb-purifier', 'lock', cwd=update)
        locked = json.loads((update / 'jsonnetfile.lock.json').read_text())
        assert locked['dependencies'][0]['version'] == previous
        old_sidecar = (update / 'jb-purifier.lock.json').read_bytes()
        command('jb-purifier', 'update', 'github.com/jsonnet-libs/xtd', cwd=update)
        locked = json.loads((update / 'jsonnetfile.lock.json').read_text())
        assert locked['dependencies'][0]['version'] != previous, 'native update did not move old commit'
        assert (update / 'jb-purifier.lock.json').read_bytes() != old_sidecar
        command('jb-purifier', 'prefetch', cwd=update)
        command('jsonnet', '-J', 'vendor', 'main.jsonnet', cwd=update)
        print('conformance-update: named update moved the native pin and refreshed the companion lock', flush=True)
