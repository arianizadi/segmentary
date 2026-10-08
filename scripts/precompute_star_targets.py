#!/usr/bin/env python3
"""Precompute STAR-C full-volume lesion instances and centre rays for a preprocessed dataset.

Reads nnU-Net's preprocessed segmentations (``<case>_seg.b2nd`` or
``<case>_seg.npy``) at the plan's 3d_fullres spacing and writes one
``<case>.npz`` per case plus ``manifest.json`` into a fresh ``--output``
directory outside every workspace, for example a new campaign-level
``/data/.../<campaign>-inputs/starc-targets-r96``. The script never writes
anywhere else and refuses an existing output, and any output under an
``nnUNet_preprocessed``/``nnUNet_raw``/``nnUNet_results`` folder or under a
directory holding ``binding.json``, ``plan-binding.json`` or ``campaign.json``:
writing into a frozen reference cache would break every later import of that
reference, and the backend refuses targets inside a run or reference workspace.

The manifest binds the schema, plans file, configuration, spacing, lesion
labels, ray set, march parameters and the sha256 of this script and of
``star_completion.py``, and lists every case's source-segmentation and
``.npz`` hashes. ``nnUNetTrainerStarC`` verifies all of them before training.
``--forbid-cases-from`` names a split file whose ``--forbid-key`` list (for
example the frozen test cases) must not overlap the cases; the check runs
before any segmentation is opened. Run with ``nice`` and at most 48 workers.
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import platform
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np

from segmentary.medical import star_completion
from segmentary.medical.recipe_plan import STARC_TARGET_METHOD
from segmentary.medical.star_completion import (
    TARGET_SCHEMA,
    compute_case_targets,
    save_case_targets,
    sha256_file,
    star_geometry,
)

MAX_WORKERS = 48
BORDER = STARC_TARGET_METHOD["crop_border_voxels"]
STEP_FRACTION = STARC_TARGET_METHOD["march"]["step_fraction_of_min_spacing"]
REFINE = STARC_TARGET_METHOD["march"]["bisections"]


def segmentation_path(folder: Path, case: str) -> Path:
    found = [p for p in (folder / f"{case}_seg.b2nd", folder / f"{case}_seg.npy") if p.is_file()]
    if len(found) != 1:
        raise FileNotFoundError(f"Expected exactly one preprocessed segmentation for {case}")
    return found[0]


def load_segmentation(path: Path) -> np.ndarray:
    if path.suffix == ".b2nd":
        import blosc2

        return np.asarray(blosc2.open(urlpath=str(path), mode="r")[:])
    return np.load(path, mmap_mode="r")[:]


def list_cases(folder: Path) -> list[str]:
    cases = set()
    for path in folder.iterdir():
        for suffix in ("_seg.b2nd", "_seg.npy"):
            if path.name.endswith(suffix):
                cases.add(path.name[: -len(suffix)])
    return sorted(cases)


NNUNET_FOLDERS = frozenset({"nnUNet_preprocessed", "nnUNet_raw", "nnUNet_results"})
WORKSPACE_MARKERS = ("binding.json", "plan-binding.json", "campaign.json")


def workspace_conflict(output: Path) -> str | None:
    """Why ``output`` (resolved) lies inside an nnU-Net tree or a workspace, else None."""
    for folder in (output, *output.parents):
        if folder.name in NNUNET_FOLDERS:
            return f"{folder} is an nnU-Net {folder.name} folder"
        for marker in WORKSPACE_MARKERS:
            if (folder / marker).exists():
                return f"{folder} holds {marker}"
    return None


def forbidden_cases(path: Path, key: str) -> set[str]:
    values = json.loads(path.read_text())[key]
    if not isinstance(values, list):
        raise ValueError(f"{path}:{key} is not a list")
    return {v["case_id"] if isinstance(v, dict) else str(v) for v in values}


def _work(job: tuple[str, str, str, list[float], list[int], int]) -> dict[str, Any]:
    case, source, output, spacing, labels, rays = job
    started = time.monotonic()
    source_path = Path(source)
    source_sha = sha256_file(source_path)
    segmentation = load_segmentation(source_path)
    targets = compute_case_targets(
        segmentation,
        spacing,
        labels,
        star_geometry(rays),
        border=BORDER,
        step_fraction=STEP_FRACTION,
        refine=REFINE,
    )
    if tuple(targets.shape) != tuple(segmentation.shape[-3:]):
        raise ValueError(f"{case}: unexpected segmentation shape")
    if sha256_file(source_path) != source_sha:
        raise RuntimeError(f"{case}: segmentation changed while it was read")
    digest = save_case_targets(Path(output) / f"{case}.npz", targets)
    return {
        "case": case,
        "segmentation": source_path.name,
        "segmentation_sha256": source_sha,
        "sha256": digest,
        "components": targets.count,
        "volume_mm3": [round(float(v), 3) for v in targets.volume_mm3],
        "max_edt_mm": [round(float(v), 4) for v in targets.max_edt_mm],
        "seconds": round(time.monotonic() - started, 3),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--preprocessed", type=Path, required=True, help="nnU-Net data folder")
    parser.add_argument("--plans", type=Path, required=True, help="plans JSON of that folder")
    parser.add_argument("--configuration", default="3d_fullres")
    parser.add_argument("--lesion-labels", type=int, nargs="+", default=[2])
    parser.add_argument("--rays", type=int, default=96)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cases", type=Path, help="optional JSON list of case ids")
    parser.add_argument("--forbid-cases-from", type=Path, help="split JSON with forbidden ids")
    parser.add_argument("--forbid-key", default="test")
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args(argv)

    if not 1 <= args.workers <= MAX_WORKERS:
        parser.error(f"--workers must be between 1 and {MAX_WORKERS}")
    if any(label < 1 for label in args.lesion_labels) or len(set(args.lesion_labels)) != len(
        args.lesion_labels
    ):
        parser.error("--lesion-labels must be distinct foreground labels")
    output = args.output.resolve()
    preprocessed = args.preprocessed.resolve()
    if output.exists():
        parser.error(f"--output exists: {output}")
    if output == preprocessed or preprocessed in output.parents:
        parser.error("--output must not be inside the preprocessed data folder")
    conflict = workspace_conflict(output)
    if conflict is not None:
        parser.error(f"--output must be outside every workspace and nnU-Net folder: {conflict}")
    plans = json.loads(args.plans.read_text())
    configuration = plans["configurations"][args.configuration]
    spacing = [float(v) for v in configuration["spacing"]]
    if len(spacing) != 3:
        parser.error("STAR-C targets need a 3D configuration")
    if configuration.get("data_identifier") not in (None, preprocessed.name):
        parser.error("--preprocessed is not this configuration's data folder")
    cases = sorted(json.loads(args.cases.read_text())) if args.cases else list_cases(preprocessed)
    if not cases:
        parser.error("No preprocessed segmentations found")
    if args.forbid_cases_from is not None:
        overlap = sorted(set(cases) & forbidden_cases(args.forbid_cases_from, args.forbid_key))
        if overlap:
            parser.error(f"Refusing forbidden cases: {overlap[:5]}")
    sources = {case: segmentation_path(preprocessed, case) for case in cases}

    output.mkdir(parents=True)
    jobs = [
        (case, str(sources[case]), str(output), spacing, list(args.lesion_labels), args.rays)
        for case in cases
    ]
    star_geometry(args.rays)
    started = time.monotonic()
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        rows = list(pool.map(_work, jobs, chunksize=1))
    geometry = star_geometry(args.rays)
    manifest = {
        "schema": TARGET_SCHEMA,
        "created_unix": time.time(),
        "plans": str(args.plans.resolve()),
        "plans_sha256": sha256_file(args.plans),
        "configuration": args.configuration,
        "data_identifier": preprocessed.name,
        "preprocessed": str(preprocessed),
        "spacing": spacing,
        "lesion_labels": list(args.lesion_labels),
        **copy.deepcopy(STARC_TARGET_METHOD),
        "rays": args.rays,
        "directions_sha256": geometry.digest(),
        "code": {
            "star_completion.py": sha256_file(Path(star_completion.__file__)),
            "precompute_star_targets.py": sha256_file(Path(__file__).resolve()),
        },
        "environment": {
            "python": platform.python_version(),
            "numpy": np.__version__,
            "scipy": __import__("scipy").__version__,
        },
        "forbidden_cases_checked": None
        if args.forbid_cases_from is None
        else {
            "file": str(args.forbid_cases_from.resolve()),
            "sha256": sha256_file(args.forbid_cases_from),
            "key": args.forbid_key,
        },
        "seconds": round(time.monotonic() - started, 1),
        "cases": {row.pop("case"): row for row in rows},
    }
    temporary = output / ".manifest.json.tmp"
    temporary.write_text(json.dumps(manifest, indent=1, sort_keys=True))
    os.replace(temporary, output / "manifest.json")
    components = sum(row["components"] for row in manifest["cases"].values())
    print(
        json.dumps(
            {
                "output": str(output),
                "cases": len(cases),
                "components": components,
                "manifest_sha256": sha256_file(output / "manifest.json"),
                "seconds": manifest["seconds"],
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
