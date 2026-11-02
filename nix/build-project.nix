# SPDX-License-Identifier: MIT
# callPackage builder: override dependencies here or across the purifier scope.
{
  lib,
  stdenvNoCC,
  runCommand,
  fetchgit,
  jsonnet,
  gnutar,
  gzip,
  purifier,
}:
{
  src,
  lockFile ? src + "/jb-purifier.lock.json",
  jsonnetLock ? src + "/jsonnetfile.lock.json",
  fetchers ? { },
  srcFilter ?
    path: type:
    !(builtins.elem (baseNameOf path) [
      ".git"
      "vendor"
      ".jb-purifier"
      "result"
      "jb-purifier.lock.json"
      "jsonnetfile.lock.json"
    ]),
  testFiles ? [ ],
}:
let
  readLock = import ./read-lock.nix { inherit lib; };
  lock = purifier.checkLock (readLock {
    inherit src lockFile jsonnetLock;
  });
  vendor =
    (import ./vendor.nix {
      inherit
        lib
        runCommand
        fetchgit
        purifier
        ;
    })
      { inherit lock fetchers; };
  source = builtins.path {
    path = src;
    name = "jb-project-source";
    filter = srcFilter;
  };
  packages = lib.mapAttrs (
    name: output:
    stdenvNoCC.mkDerivation {
      name = "jsonnet-${name}";
      src = source;
      nativeBuildInputs = [ jsonnet ];
      dontConfigure = true;
      dontFixup = true;
      buildPhase = ''
        runHook preBuild
        jsonnet -J ${vendor} ${lib.escapeShellArg output.file} > "$TMPDIR/output.json"
        runHook postBuild
      '';
      installPhase = ''
        mkdir -p "$out"
        cp "$TMPDIR/output.json" "$out/${name}.json"
      '';
    }
  ) lock.outputs;
  tests = runCommand "jb-project-tests" { nativeBuildInputs = [ jsonnet ]; } (
    ''
      cd ${source}
    ''
    + lib.concatMapStringsSep "\n" (
      file: "jsonnet -J ${vendor} ${lib.escapeShellArg file} > /dev/null"
    ) (if testFiles == [ ] then map (o: o.file) (builtins.attrValues lock.outputs) else testFiles)
    + "\n"
    + ''
      touch "$out"
    ''
  );
  release =
    runCommand "jb-project-release"
      {
        nativeBuildInputs = [
          gnutar
          gzip
        ];
      }
      ''
        test -e ${tests}
        mkdir -p "$out" "$TMPDIR/release"
        cp -r --no-preserve=mode ${source}/. "$TMPDIR/release/"
        cp ${jsonnetLock} "$TMPDIR/release/jsonnetfile.lock.json"
        cp ${lockFile} "$TMPDIR/release/jb-purifier.lock.json"
        tar --sort=name --mtime=@1 --owner=0 --group=0 --numeric-owner \
          -C "$TMPDIR/release" -cf - . | gzip -n > "$out/project.tar.gz"
      '';
in
builtins.seq lock {
  inherit packages tests release;
  fetches = lock.entries;
}
