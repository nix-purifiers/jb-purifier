# SPDX-License-Identifier: MIT
{ pkgs, self }:
let
  fixture = ../examples/ascii;
  result = pkgs.jb-purifier.buildJbProject { src = fixture; };
  lock = self.lib.jb-purifier.readLock { src = fixture; };
  # Use the same library source that the overlay's builder carries.
  shared = import (self.inputs.purifier + "/nix/lib") { inherit (pkgs) lib; };
  vendor = pkgs.callPackage ../pkgs/build-jb-project/vendor.nix { purifier = shared; } {
    inherit lock;
  };
  mkErrorCheck =
    case:
    pkgs.runCommand "jb-conformance-${case}"
      {
        nativeBuildInputs = [
          pkgs.python3
          pkgs.nix
        ];
        SOURCE = self;
        NIXPKGS_LIB = "${pkgs.path}/lib";
        PURIFIER = self.inputs.purifier;
        PYTHONPATH = self;
      }
      ''
        export HOME="$TMPDIR/home"
        mkdir -p "$HOME"
        python ${./eval-errors.py} ${case}
        touch "$out"
      '';
  externalSource = builtins.path {
    path = fixture;
    name = "jb-external-source";
    filter =
      path: type:
      !(builtins.elem (baseNameOf path) [
        "jb-purifier.lock.json"
        "jsonnetfile.lock.json"
        "vendor"
        ".jb-purifier"
      ]);
  };
  external = pkgs.jb-purifier.buildJbProject {
    src = externalSource;
    lockFile = fixture + "/jb-purifier.lock.json";
    jsonnetLock = fixture + "/jsonnetfile.lock.json";
  };
in
{
  json-projection = import shared.testFixtures.jsonConsumer {
    inherit pkgs;
    producer = result.packages.default or (builtins.head (builtins.attrValues result.packages));
    expectedKey = "purified";
    expectedValue = true;
  };
  formatting =
    pkgs.runCommand "jb-formatting"
      {
        nativeBuildInputs = [
          pkgs.nixfmt
          pkgs.findutils
        ];
      }
      ''
        find ${self} -name '*.nix' -print0 | xargs -0 nixfmt --check
        touch "$out"
      '';
  unit = pkgs.runCommand "jb-purifier-unit" { nativeBuildInputs = [ pkgs.python3 ]; } ''
    cp -r ${self} source
    chmod -R u+w source
    cd source
    python -m unittest discover -s tests -v
    touch "$out"
  '';
  conformance-stale = mkErrorCheck "stale";
  conformance-tampered = mkErrorCheck "tampered";
  conformance-missing = mkErrorCheck "missing";
  conformance-malformed = mkErrorCheck "malformed";
  conformance-external = pkgs.runCommand "jb-conformance-external" { } ''
    test ! -e ${externalSource}/jb-purifier.lock.json
    test ! -e ${externalSource}/jsonnetfile.lock.json
    cmp ${result.packages.main}/main.json ${external.packages.main}/main.json
    touch "$out"
  '';
  fixture = result.packages.main;
  fixture-tests = result.tests;
  release = result.release;
  conformance-offline =
    pkgs.runCommand "jb-conformance-offline"
      {
        nativeBuildInputs = [
          pkgs.jsonnet
          pkgs.jsonnet-language-server
          pkgs.python3
        ];
      }
      ''
        cp -r ${fixture} project
        chmod -R u+w project
        cd project
        rm -rf vendor .jb-purifier
        ln -s ${vendor} vendor
        jsonnet -J vendor main.jsonnet > actual.json
        cmp actual.json ${result.packages.main}/main.json
        python ${./editor.py}
        touch "$out"
      '';
}
