# SPDX-License-Identifier: MIT
# Distributed with the CLI; no generated Nix files in the user's project.
{
  project,
  lockFile,
  jsonnetLock,
  target,
}:
let
  pkgs = import (builtins.toPath "@nixpkgs@") { };
  purifier = import (builtins.toPath "@purifier@/nix/lib") { inherit (pkgs) lib; };
  src = builtins.toPath project;
  args = {
    inherit src;
    lockFile = builtins.toPath lockFile;
    jsonnetLock = builtins.toPath jsonnetLock;
  };
  lock = (import ./read-lock.nix { inherit (pkgs) lib; }) args;
in
if target == "vendor" then
  pkgs.callPackage ./vendor.nix { inherit purifier; } { inherit lock; }
else if target == "runtime" then
  pkgs.runCommand "jb-runtime" { } ''ln -s @runtime@ "$out"''
else if target == "release" then
  (pkgs.callPackage ./build-project.nix { inherit purifier; } args).release
else
  throw "jb-purifier: unknown realization target ${target}"
