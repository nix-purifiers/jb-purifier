# jb-purifier

Locked, Nix-resolved dependencies for Jsonnet Bundler.

## Quickstart

From a project with `jsonnetfile.json` and a Jsonnet entry point:

```sh
nix shell 'github:nix-purifiers/jb-purifier'
jb-purifier lock
jb-purifier prefetch
jsonnet -J vendor main.jsonnet
```

`lock` uses jb's native resolution. `prefetch` realizes the locked sources
with Nix and links `vendor` to the store. These commands run in your working
tree. No project Nix files are needed. Persistent installation is optional;
use your usual Nix configuration if you want it.

The shell provides a `jb` wrapper because jb has no plugin interface.
With a purifier lock, `jb install` prepares the locked vendor tree. Without
one, it prints a warning and runs ordinary jb, preserving its arguments
and exit status. `jsonnet` itself is the normal compiler.

An existing vendor directory is never deleted automatically. Move it aside
before the first prefetch. Ignore `vendor/` and `.jb-purifier/` in Git.

## Development loop

```sh
jsonnet -J vendor main.jsonnet
jb-purifier update
jb install
```

`lock` preserves existing native pins; `update` runs `jb update` and then
refreshes the companion lock. Pass package names to update only those
packages. After editing `jsonnetfile.json`, run `jb-purifier lock` and
`jb-purifier prefetch`. Commit both lockfiles.

Root-level `*.jsonnet` files become named outputs. For another layout:

```sh
jb-purifier lock \
  --entry dashboard=src/dashboard.jsonnet
```

The output declarations persist on subsequent locks.

External lockfiles are supported without changing the native lock in the
source tree:

```sh
export JB_PURIFIER_LOCKFILE="$PWD/../locks/jb-purifier.lock.json"
export JB_PURIFIER_TOOL_LOCKFILE="$PWD/../locks/jsonnetfile.lock.json"
jb-purifier lock
jb-purifier prefetch
```

The global flags `--lockfile` and `--tool-lockfile` override those variables;
put them before the subcommand. A missing external native lock is seeded
from the source's native lock when available.

## Working offline

Run `jb-purifier prefetch` while online. It realizes and roots the dependency
sources, compiler, jb and language server beside the companion lock. Then
`jb install`, `jsonnet -J vendor …` and the language server use local store
paths. Commands that change dependencies intentionally need network access.
An invalid or stale lock fails with a command to repair it.

## Editor

Use the packaged language server with the same import directory:

```sh
jsonnet-language-server -J vendor --eval-diags
```

Configure your editor to start that command from the project root. After
prefetch, evaluating imports needs no network. The compiler still needs
`-J vendor`, as in jb's ordinary workflow.

## Troubleshooting

- **Stale, malformed or edited lock:** run `jb-purifier lock`.
- **Missing import:** add it through jb's native manifest, relock and
  prefetch. Dependencies not declared by an upstream library still need
  to appear in your native dependency graph.
- **Existing vendor directory:** move it aside before prefetch. A vendor
  symlink into the Nix store is refreshed automatically.
- **Duplicate legacy aliases:** set `legacyImports` to `false`, use full
  import paths, and relock.
- **Local or single-file source:** these jb source types are currently
  rejected explicitly. Git sources and repository subdirectories work.

## Supported language repositories

Git repositories reachable through HTTPS or SSH, pinned to full commits in
version-1 `jsonnetfile.lock.json`. Credentials remain in the user's native
Git/Nix configuration. All fetch entries pass through the shared purifier
library; builders accept `fetchers.fetchgit` for a mirror or credentials.

The packaged tools come from the pinned nixpkgs. The overlay also works
with a supplied compatible package set containing Jsonnet 0.21, jb 0.6,
Python 3.11 or later, and jsonnet-language-server.

## Examples

[`examples/ascii`](examples/ascii) evaluates an assertion and a value using
an actual locked library. It contains no project Nix files:

```sh
cd examples/ascii
jb-purifier prefetch
jsonnet -J vendor main.jsonnet
```

### Building the project with Nix

For a sandboxed project build, add a flake or keep the packaging definition
in another repository. Apply `overlays.default` to your chosen nixpkgs:

```nix
let
  pkgs = import nixpkgs {
    inherit system;
    overlays = [ jb-purifier.overlays.default ];
  };
  project = pkgs.jb-purifier.buildJbProject {
    src = ./.;
  };
in project.packages.main
```

`buildJbProject` returns `packages`, `tests`, `release`, and `fetches`.
`tests` evaluates the declared entry points, including their Jsonnet
assertions; pass `testFiles` for additional test programs. `release` is a
deterministic source archive. `lockFile` and `jsonnetLock` accept paths
outside `src`, replacing any lockfiles in the source. `fetchers` passes
through to the shared library unchanged. `srcFilter` customizes source
filtering. Output names are known at evaluation time without IFD.

Use `buildJbProject.override` or `jb-purifier.overrideScope` to replace
build tools. The overlay can also be applied to ambient `<nixpkgs>`.
`lib.jb-purifier.readLock` reads the shared in-memory lock shape for
inspection and SBOM tooling.

Publish a Nix-built source archive to your GitHub repository explicitly:

```sh
jb-purifier publish \
  --repository OWNER/REPO \
  --tag v1.0.0
```

Jsonnet Bundler consumes Git repositories directly; it has no package
registry or native plugin package requiring a Pages repository.

## Credits

The purifier idea was inspired by nixcloud's
[cargo (libnix)](https://github.com/nixcloud/cargo).
