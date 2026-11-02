#!/usr/bin/env sh
# SPDX-License-Identifier: MIT
set -eu
cd "$(dirname "$0")/.."
system=$(nix eval --impure --raw --expr builtins.currentSystem)
nix build ".#checks.$system.fixture" ".#checks.$system.release" --no-link
nix build ".#checks.$system.fixture" ".#checks.$system.release" --no-link --rebuild
