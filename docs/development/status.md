# Expansion status

This repository implements the Jsonnet Bundler target from
`nix_purifiers_expansion_report.md`. The report supplies the target list,
not settled implementation decisions.

The CLI stages upstream resolution separately from the user's vendor
links. Native Git coordinates stay in jsonnetfile.lock.json; the companion
lock records missing Nix hashes, manifest fingerprints and output names.
The packaged Nix realization definition supplies the development vendor
tree and roots both dependencies and toolchain. No generated project Nix
files or mandatory persistent installation.

Initial scope supports version-1 Git dependencies, subdirectories and
legacy import aliases. Local-directory and single-file jb sources fail
explicitly until supported. Fixture tests exercise the real compiler and
language server without network, external locks and actionable failures.

Local checks passed: 21 unit tests, independent Nix/Python lock failures,
real compiler and language-server imports in the network-disabled sandbox,
external-lock builds, byte-identical native and companion relocks, a named
update moving an old upstream commit, project/external prefetch GC roots,
and rebuild equality of the compiled output and release.

Pending: CI on both Linux architectures and publication.
