final: prev: {
  jb-purifier = {
    readLock = import ./read-lock.nix { lib = final; };
  };
}
