#!/usr/bin/env python3
"""Content digest of a patched fork working tree (standard library only).

    tree_digest.py <clone>            # print the digest
    tree_digest.py <clone> --write    # also write <clone>/PAUL_PATCHES_TREE

The digest covers every file git would show in the working tree: tracked files that exist
on disk plus untracked files that are not git-ignored, excluding ``.git``, ``__pycache__``
/ ``*.pyc`` and the two ``PAUL_PATCHES_*`` bookkeeping files. Each file contributes its
relative path, its mode's executable bit and the sha256 of its bytes (a symlink: its
target), so any edit, addition or deletion after ``apply_patches.sh`` changes it.
``write_provenance.py`` recomputes it before every launch and refuses on a mismatch.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path

EXCLUDED = {"PAUL_PATCHES_APPLIED", "PAUL_PATCHES_TREE"}
TREE_FILE = "PAUL_PATCHES_TREE"


def tree_files(src: Path) -> list[str]:
    out = subprocess.check_output(
        ["git", "-C", str(src), "ls-files", "-z", "--cached", "--others", "--exclude-standard"]
    )
    names = set()
    for raw in out.split(b"\0"):
        if not raw:
            continue
        name = raw.decode()
        parts = name.split("/")
        if name in EXCLUDED or "__pycache__" in parts or name.endswith(".pyc"):
            continue
        if os.path.lexists(src / name):  # a tracked file deleted by a patch is simply absent
            names.add(name)
    return sorted(names)


def tree_digest(src: Path) -> str:
    src = Path(src)
    digest = hashlib.sha256()
    for name in tree_files(src):
        path = src / name
        if path.is_symlink():
            content = b"link:" + os.readlink(path).encode()
            executable = False
        else:
            content = path.read_bytes()
            executable = bool(path.stat().st_mode & 0o111)
        line = f"{name}\0{int(executable)}\0{hashlib.sha256(content).hexdigest()}\n"
        digest.update(line.encode())
    return digest.hexdigest()


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    write = "--write" in args
    args = [a for a in args if a != "--write"]
    if len(args) != 1:
        print("usage: tree_digest.py <clone> [--write]", file=sys.stderr)
        return 2
    src = Path(args[0])
    value = tree_digest(src)
    if write:
        (src / TREE_FILE).write_text(f"{value}  tree_digest.py\n")
    print(value)
    return 0


if __name__ == "__main__":
    sys.exit(main())
