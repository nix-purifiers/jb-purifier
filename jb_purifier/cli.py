# SPDX-License-Identifier: MIT
"""Native jb workflow backed by a Nix-realized vendor directory."""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from . import lock


def read_json(path):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError) as error:
        raise ValueError(f'cannot read {path}: {error}; {lock.ADVICE}') from error


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, sort_keys=True, ensure_ascii=False, indent=2) + '\n'
    with tempfile.NamedTemporaryFile(mode='w', dir=path.parent, delete=False) as out:
        temporary = Path(out.name)
        out.write(text)
    temporary.replace(path)


def run(args, **kwargs):
    return subprocess.run(args, check=True, **kwargs)


def paths(args):
    root = Path.cwd()
    sidecar = Path(args.lockfile or os.environ.get('JB_PURIFIER_LOCKFILE', root / 'jb-purifier.lock.json')).resolve()
    native = Path(args.tool_lockfile or os.environ.get('JB_PURIFIER_TOOL_LOCKFILE', root / 'jsonnetfile.lock.json')).resolve()
    return root, sidecar, native


def checked(root, sidecar, native):
    data = read_json(sidecar)
    errors = lock.problems(root, native, data)
    if errors:
        raise ValueError('\n'.join(errors))
    return data


def realize(root, sidecar, native, target):
    args = ['nix', 'build', '--impure', '--file', os.environ['JB_PURIFIER_REALIZE'], '--argstr', 'project', str(root), '--argstr', 'lockFile', str(sidecar), '--argstr', 'jsonnetLock', str(native), '--argstr', 'target', target]
    state = sidecar.parent / '.jb-purifier' / lock.digest(str(root))[:12]
    state.mkdir(parents=True, exist_ok=True)
    profile = state / target
    run(args + ['--out-link', str(profile)])
    return profile.resolve()


def prepare(root, sidecar, native):
    checked(root, sidecar, native)
    vendor = realize(root, sidecar, native, 'vendor')
    # Keep the CLI/toolchain (including the language server) alive as well.
    realize(root, sidecar, native, 'runtime')
    target = root / 'vendor'
    if target.is_symlink():
        existing = target.resolve()
        if not str(existing).startswith('/nix/store/'):
            raise ValueError('vendor is a user-owned symlink; move it aside before jb-purifier prefetch')
        target.unlink()
    elif target.exists():
        raise ValueError('vendor already exists; move it aside before jb-purifier prefetch (it is never deleted automatically)')
    target.symlink_to(vendor, target_is_directory=True)


def do_lock(args, root, sidecar, native, update=False):
    try:
        old = read_json(sidecar) if sidecar.exists() else None
    except ValueError:
        old = None
    entries = args.entry or []
    outputs = {}
    if entries:
        for entry in entries:
            if '=' not in entry:
                raise ValueError('--entry must be NAME=FILE')
            name, path = entry.split('=', 1)
            outputs[name] = {'file': lock.relative_path(path)}
    elif isinstance(old, dict) and isinstance(old.get('outputs'), dict):
        outputs = old['outputs']
    else:
        outputs = {p.stem: {'file': p.name} for p in sorted(root.glob('*.jsonnet'))}
    # Run upstream resolution away from the working vendor symlink and write
    # external native locks without touching the source's native lockfile.
    with tempfile.TemporaryDirectory(prefix='jb-purifier-lock-') as work:
        stage = Path(work)
        shutil.copyfile(root / 'jsonnetfile.json', stage / 'jsonnetfile.json')
        seed = native if native.exists() else root / 'jsonnetfile.lock.json'
        try:
            seed_data = json.loads(seed.read_bytes()) if seed.exists() else None
        except ValueError:
            seed_data = None
        if seed_data is not None:
            shutil.copyfile(seed, stage / 'jsonnetfile.lock.json')
        run([os.environ.get('JB_PURIFIER_JB', 'jb'), 'update' if update else 'install', *args.packages], cwd=stage)
        resolved_path = stage / 'jsonnetfile.lock.json'
        resolved = read_json(resolved_path)
        hashes = {}
        for dep in lock.dependencies(resolved):
            result = run(['nix-prefetch-git', '--quiet', '--url', dep['url'], '--rev', dep['rev']], capture_output=True, text=True)
            fetched = json.loads(result.stdout)
            value = fetched.get('hash')
            if value is None:
                value = run(['nix', 'hash', 'convert', '--hash-algo', 'sha256', '--to', 'sri', fetched['sha256']], capture_output=True, text=True).stdout.strip()
            hashes[dep['name']] = value
        # Native install may change formatting; preserve bytes when its
        # semantic resolution is unchanged.
        original = seed.read_bytes() if seed_data is not None else None
        native_bytes = original if original is not None and json.loads(original) == resolved else resolved_path.read_bytes()
        candidate = stage / 'candidate-native.json'
        candidate.write_bytes(native_bytes)
        data = lock.make_lock(root, candidate, hashes, outputs)
        errors = lock.problems(root, candidate, data)
        if errors:
            raise ValueError('\n'.join(errors))
        native.parent.mkdir(parents=True, exist_ok=True)
        if not native.exists() or native.read_bytes() != native_bytes:
            with tempfile.NamedTemporaryFile(dir=native.parent, delete=False) as stream:
                stream.write(native_bytes)
                staged_native = Path(stream.name)
            staged_native.replace(native)
        write_json(sidecar, data)
    print(f'Locked {len(hashes)} Git dependencies in {sidecar}')


def main(argv=None):
    parser = argparse.ArgumentParser(prog='jb-purifier')
    parser.add_argument('--lockfile')
    parser.add_argument('--tool-lockfile')
    sub = parser.add_subparsers(dest='command', required=True)
    for command in ['lock', 'update']:
        p = sub.add_parser(command)
        p.add_argument('--entry', action='append')
        if command == 'update':
            p.add_argument('packages', nargs='*')
        else:
            p.set_defaults(packages=[])
    sub.add_parser('prefetch')
    publish = sub.add_parser('publish')
    publish.add_argument('--repository', required=True, help='GitHub OWNER/REPO receiving the source release')
    publish.add_argument('--tag', required=True)
    native = sub.add_parser('native', help=argparse.SUPPRESS)
    native.add_argument('args', nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    if args.command == 'native' and args.args[:1] == ['--']:
        args.args = args.args[1:]
    root, sidecar, native_path = paths(args)
    try:
        if args.command in ('lock', 'update'):
            do_lock(args, root, sidecar, native_path, args.command == 'update')
        elif args.command == 'prefetch':
            prepare(root, sidecar, native_path)
        elif args.command == 'publish':
            checked(root, sidecar, native_path)
            release = realize(root, sidecar, native_path, 'release')
            run(['gh', 'release', 'create', args.tag, '--repo', args.repository, '--generate-notes', str(release / 'project.tar.gz')])
        else:
            tool = os.environ.get('JB_PURIFIER_JB', 'jb')
            if not sidecar.exists() and not sidecar.is_symlink():
                print('jb-purifier: warning: no purifier lockfile; using ordinary, impure jb resolution. Run jb-purifier lock to lock dependencies.', file=sys.stderr)
                os.execv(tool, [tool, *args.args])
            # Explicit updates are intentionally online and refresh both locks.
            if args.args and args.args[0] == 'update':
                args.entry = None
                args.packages = args.args[1:]
                do_lock(args, root, sidecar, native_path, True)
                prepare(root, sidecar, native_path)
            elif args.args == ['install'] or not args.args:
                prepare(root, sidecar, native_path)
            elif args.args[0] in ('--help', '-h', '--version', 'help', 'init'):
                os.execv(tool, [tool, *args.args])
            else:
                raise ValueError('locked jb accepts install and update; use jb-purifier update or edit jsonnetfile.json and run jb-purifier lock')
    except (ValueError, KeyError, OSError) as error:
        print(f'jb-purifier: {error}', file=sys.stderr)
        return 1
    except subprocess.CalledProcessError as error:
        return error.returncode if error.returncode > 0 else 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
