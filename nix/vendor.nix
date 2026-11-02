# SPDX-License-Identifier: MIT
{
  lib,
  runCommand,
  fetchgit,
  purifier,
}:
{
  lock,
  fetchers ? { },
}:
let
  checked = purifier.checkLock lock;
  sources = purifier.tree (
    {
      name = "jb-sources";
      entries = checked.entries;
      inherit runCommand fetchgit;
    }
    // fetchers
  );
  aliases = map (d: d.alias) lock.dependencies;
  unique = builtins.length (lib.unique aliases) == builtins.length aliases;
in
assert
  (!lock.legacyImports || unique)
  || throw "jb-purifier: duplicate legacy aliases; set legacyImports=false and run jb-purifier lock";
runCommand "jb-vendor" { } (
  ''
    mkdir -p "$out"
  ''
  + lib.concatMapStringsSep "\n" (dep: ''
    mkdir -p "$out/$(dirname ${lib.escapeShellArg dep.name})"
    test -d ${lib.escapeShellArg "${sources}/.sources/${dep.name}${lib.optionalString (dep.subdir != "") "/${dep.subdir}"}"}
    ln -s ${lib.escapeShellArg "${sources}/.sources/${dep.name}${lib.optionalString (dep.subdir != "") "/${dep.subdir}"}"} "$out/"${lib.escapeShellArg dep.name}
    ${lib.optionalString lock.legacyImports ''
      if [ -e "$out/"${lib.escapeShellArg dep.alias} ]; then
        echo 'jb-purifier: legacy alias collides with a vendor path' >&2
        exit 1
      fi
      ln -s ${lib.escapeShellArg dep.name} "$out/"${lib.escapeShellArg dep.alias}
    ''}
  '') lock.dependencies
)
