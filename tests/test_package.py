"""Distribution artifacts contain the runnable YAML resources users need."""

from __future__ import annotations

import os
import subprocess
import tarfile
import zipfile
from pathlib import Path

import pytest


def _archive_names(path: Path) -> set[str]:
    if path.suffix == ".whl":
        with zipfile.ZipFile(path) as archive:
            return set(archive.namelist())
    with tarfile.open(path) as archive:
        return set(archive.getnames())


def _archive_text(path: Path, suffix: str) -> str:
    names = _archive_names(path)
    matches = [name for name in names if name.endswith(suffix)]
    assert len(matches) == 1, (suffix, matches)
    name = matches[0]
    if path.suffix == ".whl":
        with zipfile.ZipFile(path) as archive:
            return archive.read(name).decode("utf-8")
    with tarfile.open(path) as archive:
        member = archive.extractfile(name)
        assert member is not None
        return member.read().decode("utf-8")


@pytest.mark.parametrize(
    "suffix",
    [
        ".dist-info/licenses/LICENSE",
        "share/segmentary/configs/base.yaml",
        "share/segmentary/configs/models/README.md",
        "share/segmentary/configs/models/hf_auto_segformer_b0.yaml",
        "share/segmentary/configs/models/smp_upernet_resnet101.yaml",
        "share/segmentary/configs/curricula/README.md",
        "share/segmentary/configs/examples/folder_dataset.yaml",
        "share/segmentary/taxonomy/README.md",
        "share/segmentary/taxonomy/cityscapes19/README.md",
        "share/segmentary/taxonomy/rail_union/README.md",
        "share/segmentary/taxonomy/example/README.md",
        "share/segmentary/taxonomy/example/canonical.yaml",
        "share/segmentary/taxonomy/example/my_dataset.yaml",
        "share/segmentary/splits/railsem19_seed0.json",
    ],
)
def test_built_distribution_contains_runnable_resources(built_distribution: Path, suffix: str):
    names = _archive_names(built_distribution)
    assert any(name.endswith(suffix) for name in names), suffix


def test_built_wheel_contains_only_the_segmentary_python_namespace(
    built_distribution: Path,
) -> None:
    names = _archive_names(built_distribution)
    assert any(name.startswith("segmentary/") for name in names)
    legacy_namespace = "rail" + "yard"
    assert not any(name.startswith(f"{legacy_namespace}/") for name in names)
    assert not any(f"share/{legacy_namespace}/" in name for name in names)


@pytest.mark.parametrize(
    "suffix",
    [
        "share/segmentary/configs/models/README.md",
        "share/segmentary/configs/curricula/README.md",
        "share/segmentary/taxonomy/README.md",
        "share/segmentary/taxonomy/cityscapes19/README.md",
        "share/segmentary/taxonomy/rail_union/README.md",
        "share/segmentary/taxonomy/example/README.md",
    ],
)
def test_packaged_indexes_do_not_link_to_an_unshipped_docs_tree(
    built_distribution: Path, suffix: str
) -> None:
    text = _archive_text(built_distribution, suffix)
    assert "](../docs/" not in text
    assert "](../../docs/" not in text


@pytest.mark.parametrize(
    "command",
    [
        "segmentary-init",
        "segmentary-verify",
        "segmentary-overfit",
        "segmentary-train",
        "segmentary-eval",
        "segmentary-export",
        "segmentary-make-split",
        "segmentary-table",
        "segmentary-models",
        "segmentary-progress",
        "segmentary-scene",
    ],
)
def test_installed_wheel_console_help(
    installed_wheel_bin: Path, tmp_path: Path, command: str
) -> None:
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    proc = subprocess.run(
        [str(installed_wheel_bin / command), "--help"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert "usage:" in proc.stdout.lower()
