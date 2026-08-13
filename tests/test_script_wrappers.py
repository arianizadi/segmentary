"""Legacy source-checkout scripts must execute this checkout, not site-packages."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    "script",
    ["verify_dataset.py", "overfit_check.py", "make_custom_split.py", "make_results_table.py"],
)
def test_source_wrapper_help_works_without_pythonpath(script: str) -> None:
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    proc = subprocess.run(
        [sys.executable, str(REPO / "scripts" / script), "--help"],
        cwd=REPO,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert "usage:" in proc.stdout.lower()
