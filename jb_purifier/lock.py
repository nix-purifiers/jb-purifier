# SPDX-License-Identifier: MIT
"""Read native jb coordinates; store only Nix hashes and output declarations."""
import hashlib
import json
import re
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit

ADVICE = 'run jb-purifier lock (with --lockfile/--tool-lockfile for external locks)'


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'))


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def seal(data):
    data = {k: v for k, v in data.items() if k != 'contentHash'}
    return {**data, 'contentHash': digest(data)}


def relative_path(value):
    if not isinstance(value, str) or not value or '\\' in value or '\x00' in value or value.startswith('/') or any(p in ('', '.', '..') for p in value.split('/')):
        raise ValueError(f'unsafe relative path: {value!r}')
    return value


def git_dependency(dep):
    source = dep.get('source', {})
    if set(source) != {'git'}:
        raise ValueError('only Git dependencies are currently supported; local dependencies must be supplied as project source')
    git = source['git']
    url = git['remote']
    parsed = urlsplit(url)
    if parsed.scheme not in ('https', 'ssh') or not parsed.hostname or parsed.query or parsed.fragment or (parsed.scheme == 'https' and parsed.username) or (parsed.scheme == 'ssh' and parsed.username != 'git') or parsed.password or parsed.port:
        raise ValueError(f'unsupported Git URL: {url!r}')
    remote_path = relative_path(parsed.path.lstrip('/').removesuffix('.git'))
    subdir = git.get('subdir', '')
    if subdir:
        relative_path(subdir)
    name = relative_path(f'{parsed.hostname}/{remote_path}' + (f'/{subdir}' if subdir else ''))
    rev = dep['version']
    if not isinstance(rev, str) or not re.fullmatch('[0-9a-f]{40}|[0-9a-f]{64}', rev):
        raise ValueError(f'{name}: native lock must pin a full Git commit')
    if dep.get('single', False):
        raise ValueError(f'{name}: single-file dependencies are not yet supported')
    alias = dep.get('name') or name.rsplit('/', 1)[-1]
    relative_path(alias)
    if '/' in alias:
        raise ValueError('legacy alias must be a single path component')
    return {'name': name, 'url': url, 'rev': rev, 'subdir': subdir, 'alias': alias}


def dependencies(native):
    if not isinstance(native, dict) or native.get('version') != 1 or not isinstance(native.get('dependencies'), list):
        raise ValueError('expected a version 1 jsonnetfile.lock.json')
    result = [git_dependency(d) for d in native['dependencies']]
    names = [d['name'] for d in result]
    if len(set(names)) != len(names):
        raise ValueError('duplicate dependency in native lock')
    for a in names:
        if any(b.startswith(a + '/') for b in names):
            raise ValueError(f'overlapping vendor paths: {a}')
    return result


def make_lock(root, native_path, hashes, outputs):
    return seal({'version': 1, 'inputs': {'jsonnetfile.json': file_hash(root / 'jsonnetfile.json'), 'jsonnetfile.lock.json': file_hash(native_path)}, 'hashes': hashes, 'outputs': outputs})


def problems(root, native_path, data):
    """Return actionable errors rather than permitting impure fallback."""
    try:
        if not isinstance(data, dict) or data.get('version') != 1:
            raise ValueError('unsupported lock format version')
        if data.get('contentHash') != digest({k: v for k, v in data.items() if k != 'contentHash'}):
            raise ValueError('contentHash mismatch (lock was edited)')
        for name, path in [('jsonnetfile.json', root / 'jsonnetfile.json'), ('jsonnetfile.lock.json', native_path)]:
            if data.get('inputs', {}).get(name) != file_hash(path):
                raise ValueError(f'{name} changed after locking')
        deps = dependencies(json.loads(native_path.read_text()))
        hashes = data.get('hashes')
        if not isinstance(hashes, dict):
            raise ValueError('hashes must be an object')
        for dep in deps:
            if not isinstance(hashes.get(dep['name']), str) or not re.fullmatch(r'sha256-[A-Za-z0-9+/]{43}=', hashes[dep['name']]):
                raise ValueError(f'missing or invalid Nix hash for {dep["name"]}')
        if set(hashes) != {d['name'] for d in deps}:
            raise ValueError('hashes contain dependencies absent from native lock')
        outputs = data.get('outputs')
        if not isinstance(outputs, dict) or not outputs:
            raise ValueError('outputs must name at least one Jsonnet entry point; use lock --entry NAME=FILE')
        for name, output in outputs.items():
            if not re.fullmatch('[A-Za-z0-9][A-Za-z0-9_-]*', name) or not isinstance(output, dict):
                raise ValueError('invalid output declaration')
            path = relative_path(output.get('file'))
            if not (root / path).is_file() or not (root / path).resolve().is_relative_to(root.resolve()):
                raise ValueError(f'missing or unsafe output file {path}')
        return []
    except (ValueError, KeyError, TypeError, AttributeError, OSError) as error:
        return [f'jb-purifier: {error}; {ADVICE}']
