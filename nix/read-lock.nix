# SPDX-License-Identifier: MIT
{ lib }:
{
  src,
  lockFile ? src + "/jb-purifier.lock.json",
  jsonnetLock ? src + "/jsonnetfile.lock.json",
}:
let
  problem =
    message:
    "jb-purifier: ${message}; run jb-purifier lock (use --lockfile and --tool-lockfile for external locks)";
  read =
    path:
    builtins.addErrorContext (problem "cannot parse ${toString path}") (
      builtins.fromJSON (builtins.readFile path)
    );
  exists =
    builtins.pathExists lockFile
    && builtins.pathExists jsonnetLock
    && builtins.pathExists (src + "/jsonnetfile.json");
  data = if exists then read lockFile else { };
  native = if exists then read jsonnetLock else { };
  isObject = builtins.isAttrs;
  pathOK =
    path:
    builtins.isString path
    && path != ""
    && !(lib.hasPrefix "/" path)
    && builtins.all (part: part != "" && part != "." && part != ".." && !(lib.hasInfix "\\" part)) (
      lib.splitString "/" path
    );
  deps =
    if isObject native && builtins.isList (native.dependencies or null) then
      native.dependencies
    else
      [ ];
  decode =
    dep:
    let
      git = dep.source.git or { };
      parts =
        if builtins.isString (git.remote or null) then
          builtins.match "(https://|ssh://git@)([^/]+)/(.+)" git.remote
        else
          null;
      subdir = git.subdir or "";
      base =
        if parts == null then
          ""
        else
          "${builtins.elemAt parts 1}/${lib.removeSuffix ".git" (builtins.elemAt parts 2)}";
      name = base + lib.optionalString (subdir != "") "/${subdir}";
      alias = if (dep.name or "") != "" then dep.name else baseNameOf name;
    in
    {
      inherit name subdir alias;
      url = git.remote or "";
      rev = dep.version or "";
      valid =
        isObject dep
        && isObject (dep.source or null)
        && builtins.attrNames dep.source == [ "git" ]
        && parts != null
        && pathOK name
        && (subdir == "" || pathOK subdir)
        && pathOK alias
        && !(lib.hasInfix "/" alias)
        && builtins.isString (dep.version or null)
        && builtins.match "([0-9a-f]{40}|[0-9a-f]{64})" dep.version != null
        && !(dep.single or false);
    };
  decoded = map decode deps;
  names = map (d: d.name) decoded;
  outputs = data.outputs or { };
  hashes = data.hashes or { };
  digest = builtins.hashString "sha256" (builtins.toJSON (removeAttrs data [ "contentHash" ]));
  problems = map problem (
    if !exists then
      [ "missing lockfile or jsonnetfile.json" ]
    else if !isObject data || (data.version or null) != 1 then
      [ "unsupported purifier lock format" ]
    else if (data.contentHash or null) != digest then
      [ "contentHash mismatch (lock was edited)" ]
    else if !isObject (data.inputs or null) then
      [ "missing input fingerprints" ]
    else if
      (data.inputs."jsonnetfile.json" or null) != builtins.hashFile "sha256" (src + "/jsonnetfile.json")
    then
      [ "jsonnetfile.json changed after locking" ]
    else if (data.inputs."jsonnetfile.lock.json" or null) != builtins.hashFile "sha256" jsonnetLock then
      [ "jsonnetfile.lock.json changed after locking" ]
    else if
      !isObject native || (native.version or null) != 1 || !builtins.isList (native.dependencies or null)
    then
      [ "invalid native lock format" ]
    else if !(builtins.all (d: d.valid) decoded) then
      [ "native lock needs supported Git sources pinned to full commits and safe paths" ]
    else if builtins.length (lib.unique names) != builtins.length names then
      [ "duplicate native dependencies" ]
    else if builtins.any (a: builtins.any (b: lib.hasPrefix (a + "/") b) names) names then
      [ "overlapping vendor paths" ]
    else if !isObject hashes then
      [ "hashes must be an object" ]
    else if builtins.sort builtins.lessThan names != builtins.attrNames hashes then
      [ "missing or extra dependency hashes" ]
    else if
      !(builtins.all (
        hash: builtins.isString hash && builtins.match "sha256-[A-Za-z0-9+/]{43}=" hash != null
      ) (builtins.attrValues hashes))
    then
      [ "invalid dependency hash" ]
    else if !isObject outputs || outputs == { } then
      [ "outputs must name a Jsonnet entry point" ]
    else if
      !(lib.all (
        name:
        builtins.match "[A-Za-z0-9][A-Za-z0-9_-]*" name != null
        && isObject outputs.${name}
        && pathOK (outputs.${name}.file or null)
        && builtins.pathExists (src + "/${outputs.${name}.file}")
      ) (builtins.attrNames outputs))
    then
      [ "invalid or missing Jsonnet entry point" ]
    else
      [ ]
  );
  usable = problems == [ ];
in
{
  purifier = "jb-purifier";
  inherit problems;
  entries =
    if !usable then
      [ ]
    else
      map (dep: {
        path = ".sources/${dep.name}";
        git = {
          inherit (dep) url rev;
          submodules = false;
          leaveDotGit = false;
          commitObject = null;
        };
        hash = hashes.${dep.name};
      }) decoded;
  outputs = if usable then outputs else { };
  # Additional data for constructing jb's native vendor layout.
  dependencies = if usable then decoded else [ ];
  legacyImports = (read (src + "/jsonnetfile.json")).legacyImports or false;
}
