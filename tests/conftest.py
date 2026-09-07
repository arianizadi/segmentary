"""Shared fixtures. Real-data tests skip cleanly when the datasets are absent."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import sysconfig
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
TAXONOMY_ROOT = REPO_ROOT / "taxonomy"

CITYSCAPES_ROOT = os.environ.get("SEGMENTARY_CITYSCAPES")
RAILSEM19_ROOT = os.environ.get("SEGMENTARY_RAILSEM19")


@pytest.fixture(scope="session")
def taxonomy_root() -> Path:
    return TAXONOMY_ROOT


@pytest.fixture(scope="session")
def cityscapes_root() -> Path:
    if CITYSCAPES_ROOT is None:
        pytest.skip("set SEGMENTARY_CITYSCAPES to run real Cityscapes tests")
    root = Path(CITYSCAPES_ROOT)
    if not (root / "gtFine").is_dir():
        pytest.skip(f"Cityscapes not found at {root}")
    return root


@pytest.fixture(scope="session")
def railsem19_root() -> Path:
    if RAILSEM19_ROOT is None:
        pytest.skip("set SEGMENTARY_RAILSEM19 to run real RailSem19 tests")
    root = Path(RAILSEM19_ROOT)
    if not (root / "uint8").is_dir():
        pytest.skip(f"RailSem19 not found at {root}")
    return root


@pytest.fixture(scope="session")
def built_distribution(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Build one wheel for package-content tests without installing it."""
    out = tmp_path_factory.mktemp("dist")
    completed = subprocess.run(
        [sys.executable, "-m", "pip", "wheel", ".", "--no-deps", "--wheel-dir", str(out)],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        pytest.fail(f"wheel build failed:\n{completed.stdout}\n{completed.stderr}")
    wheels = list(out.glob("*.whl"))
    assert len(wheels) == 1
    return wheels[0]


@pytest.fixture(scope="session")
def installed_wheel_bin(tmp_path_factory: pytest.TempPathFactory, built_distribution: Path) -> Path:
    """Install the wheel without editable/source-path help for CLI smoke tests."""
    root = tmp_path_factory.mktemp("wheel-venv")
    completed = subprocess.run(
        [sys.executable, "-m", "venv", str(root)],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        pytest.fail(f"venv creation failed:\n{completed.stdout}\n{completed.stderr}")
    bin_dir = root / "bin"
    completed = subprocess.run(
        [
            str(bin_dir / "python"),
            "-m",
            "pip",
            "install",
            "--no-deps",
            "--ignore-installed",
            str(built_distribution),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        pytest.fail(f"wheel install failed:\n{completed.stdout}\n{completed.stderr}")

    # A nested --system-site-packages venv inherits the base interpreter's
    # packages, not the active development venv's dependencies. Share those
    # dependencies as plain paths: unlike site.addsitedir(), this does not run
    # their editable-install .pth hooks or add the checkout's source directory.
    completed = subprocess.run(
        [
            str(bin_dir / "python"),
            "-I",
            "-c",
            "import sysconfig; print(sysconfig.get_path('purelib'))",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    wheel_site = Path(completed.stdout.strip())
    dependency_paths = dict.fromkeys(sysconfig.get_path(name) for name in ("purelib", "platlib"))
    (wheel_site / "segmentary-test-dependencies.pth").write_text(
        "".join(f"{path}\n" for path in dependency_paths)
    )

    # Prove that sharing third-party dependencies did not make this a source
    # checkout test in disguise. Wheel packages take precedence on sys.path.
    completed = subprocess.run(
        [
            str(bin_dir / "python"),
            "-I",
            "-c",
            "import json, segmentary, sys; "
            "print(json.dumps({'module': segmentary.__file__, 'paths': sys.path}))",
        ],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    imported = json.loads(completed.stdout)
    assert Path(imported["module"]).resolve().is_relative_to(wheel_site.resolve()), imported
    assert str(REPO_ROOT / "src") not in imported["paths"], imported
    return bin_dir


@pytest.fixture
def tmp_space(tmp_path: Path):
    """Factory writing a minimal 3-class label space plus a mapping file.

    Used to prove the validator rejects malformed taxonomies. Building them on
    disk rather than mocking keeps the tests honest about the real load path.
    """
    import yaml

    def _make(space_name: str = "toy", *, mapping: dict | None = None, classes: list | None = None):
        root = tmp_path / "taxonomy"
        (root / space_name).mkdir(parents=True, exist_ok=True)
        canonical = {
            "name": space_name,
            "description": "toy space",
            "ignore_index": 255,
            "classes": classes
            if classes is not None
            else [
                {"id": 0, "name": "a", "color": [1, 1, 1]},
                {"id": 1, "name": "b", "color": [2, 2, 2]},
                {"id": 2, "name": "c", "color": [3, 3, 3]},
            ],
        }
        (root / space_name / "canonical.yaml").write_text(yaml.safe_dump(canonical))
        if mapping is not None:
            mapping.setdefault("space", space_name)
            mapping.setdefault("dataset", "toy_ds")
            mapping.setdefault("default", 255)
            (root / space_name / "toy_ds.yaml").write_text(yaml.safe_dump(mapping))
        return root

    return _make
