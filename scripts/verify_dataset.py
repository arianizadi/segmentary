#!/usr/bin/env python
"""Source-checkout compatibility wrapper for ``segmentary-verify``."""

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from segmentary.verify import main

if __name__ == "__main__":
    argv = sys.argv[1:]
    if "--space" not in argv:
        argv += ["--space", "rail_union"]
    if "--taxonomy" not in argv:
        argv += ["--taxonomy", str(REPO / "taxonomy")]
    raise SystemExit(main(argv))
