# SPDX-License-Identifier: MIT
{
  lib,
  stdenvNoCC,
  makeWrapper,
  python3,
  nix,
  nix-prefetch-git,
  git,
  gh,
  jsonnet-bundler,
  jsonnet,
  jsonnet-language-server,
  nixpkgsSrc,
  purifierSrc,
}:
stdenvNoCC.mkDerivation {
  pname = "jb-purifier";
  version = "0.1.0";
  src = ../..;
  nativeBuildInputs = [ makeWrapper ];
  dontBuild = true;
  installPhase = ''
    mkdir -p "$out/bin" "$out/lib/jb-purifier"
    cp -r jb_purifier pkgs lib-overlays "$out/lib/jb-purifier/"
    install -m755 bin/jb-purifier "$out/bin/jb-purifier"
    substituteInPlace "$out/lib/jb-purifier/pkgs/build-jb-project/realize.nix" \
      --replace-fail '@nixpkgs@' '${nixpkgsSrc}' \
      --replace-fail '@purifier@' '${purifierSrc}' \
      --replace-fail '@runtime@' "$out"
    wrapProgram "$out/bin/jb-purifier" \
      --prefix PATH : ${
        lib.makeBinPath [
          python3
          nix
          nix-prefetch-git
          git
          gh
          jsonnet-bundler
          jsonnet
          jsonnet-language-server
        ]
      } \
      --prefix PYTHONPATH : "$out/lib/jb-purifier" \
      --set JB_PURIFIER_JB ${jsonnet-bundler}/bin/jb \
      --set JB_PURIFIER_REALIZE "$out/lib/jb-purifier/pkgs/build-jb-project/realize.nix"
    makeWrapper "$out/bin/jb-purifier" "$out/bin/jb" --add-flags "native --"
    ln -s ${jsonnet}/bin/jsonnet "$out/bin/jsonnet"
    ln -s ${jsonnet-language-server}/bin/jsonnet-language-server "$out/bin/jsonnet-language-server"
  '';
  meta = {
    description = "Jsonnet Bundler dependencies resolved and retained by Nix";
    license = lib.licenses.mit;
    platforms = lib.platforms.linux;
    mainProgram = "jb-purifier";
    homepage = "https://nix-purifiers.github.io/";
  };
}
