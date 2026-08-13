#!/usr/bin/env python
"""Source-checkout compatibility wrapper for ``segmentary-make-split``."""

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from segmentary.make_split import main

if __name__ == "__main__":
    raise SystemExit(main())
