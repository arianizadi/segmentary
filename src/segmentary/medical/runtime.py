"""Read-only environment discovery for the optional medical backend."""

from __future__ import annotations

import importlib.metadata
import json
import platform
import shutil
import subprocess
import sys
from typing import Any


def doctor(*, require_training: bool = False, backend_python: str | None = None) -> dict[str, Any]:
    """Inspect dependencies and driver visibility without allocating GPU memory."""
    required = ["nibabel", "pydicom", "surface-distance", "numpy", "scipy"]
    if require_training and backend_python is None:
        required.extend(["nnunetv2", "torch"])
    packages: dict[str, str | None] = {}
    for name in required:
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = None
    gpu: dict[str, Any] = {"available": False, "devices": [], "error": None}
    executable = shutil.which("nvidia-smi")
    if executable:
        try:
            result = subprocess.run(
                [
                    executable,
                    "--query-gpu=index,uuid,name,memory.total,memory.used,utilization.gpu",
                    "--format=csv,noheader,nounits",
                ],
                check=False,
                capture_output=True,
                text=True,
                timeout=15,
            )
            if result.returncode:
                gpu["error"] = result.stderr.strip()
            else:
                for line in result.stdout.splitlines():
                    values = [value.strip() for value in line.split(",")]
                    if len(values) != 6:
                        raise ValueError("Unexpected nvidia-smi CSV fields")
                    gpu["devices"].append(
                        dict(
                            zip(
                                [
                                    "index",
                                    "uuid",
                                    "name",
                                    "memory_total_mib",
                                    "memory_used_mib",
                                    "utilization_percent",
                                ],
                                values,
                                strict=True,
                            )
                        )
                    )
                gpu["available"] = bool(gpu["devices"])
        except (OSError, subprocess.TimeoutExpired, ValueError) as exc:
            gpu["error"] = str(exc)
    backend: dict[str, Any] | None = None
    if backend_python is not None:
        script = (
            "import importlib.metadata as m,json,sys; "
            "print(json.dumps({'executable':sys.executable, 'packages':"
            "{p:m.version(p) for p in ['nnunetv2','torch','nibabel','pydicom','surface-distance']}}))"
        )
        try:
            result = subprocess.run(
                [backend_python, "-c", script],
                check=True,
                capture_output=True,
                text=True,
                timeout=30,
            )
            backend = json.loads(result.stdout)
            backend["passed"] = backend["packages"]["nnunetv2"] == "2.8.1"
        except (OSError, ValueError, subprocess.SubprocessError) as exc:
            backend = {"passed": False, "error": str(exc)}
    missing = [name for name, version in packages.items() if version is None]
    return {
        "schema_version": 1,
        "python": sys.version.split()[0],
        "executable": sys.executable,
        "platform": platform.platform(),
        "packages": packages,
        "missing_packages": missing,
        "gpu": gpu,
        "scheduling": "direct user processes with GPU locks; no Slurm or sudo",
        "require_training": require_training,
        "backend": backend,
        "passed": not missing
        and (backend is None or backend["passed"])
        and (not require_training or gpu["available"]),
        "limitations": [
            "GPU enumeration is not a CUDA tensor/training smoke test.",
            "Idle devices are not reserved by this check.",
        ],
    }


def write_report(report_path: str, output_path: str) -> dict[str, Any]:
    """Render saved evaluation evidence without changing or recomputing metrics."""
    from pathlib import Path

    source = Path(report_path)
    destination = Path(output_path)
    if destination.exists():
        raise FileExistsError(f"Report output already exists: {destination}")
    report = json.loads(source.read_text())
    if not isinstance(report, dict) or "schema_version" not in report:
        raise ValueError("Expected a versioned medical evaluation report")
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Preserve the evaluator's explicit nulls, denominators, and coverage. A JSON
    # evidence block avoids inventing a new aggregation during Markdown export.
    evidence = {key: value for key, value in report.items() if key != "cases"}
    table = ""
    if "regions" in report:
        table = "| Region | Mean Dice | 95% CI | Patients | Failed predictions |\n|---|---:|---|---:|---:|\n"
        for region, summary in report["regions"].items():
            metric = summary["dice"]
            mean = "undefined" if metric["mean"] is None else f"{metric['mean']:.4f}"
            ci = (
                "not estimated"
                if metric["ci"] is None
                else f"{metric['ci'][0]:.4f} to {metric['ci'][1]:.4f}"
            )
            table += f"| {region} | {mean} | {ci} | {metric['patients']} | {summary['prediction_failed_cases']} |\n"
        table += "\n"
    rendered = (
        "# Medical segmentation evaluation\n\n"
        "Generated from the saved evaluation report. Values and missingness are preserved.\n\n"
        "Mass segmentation is not a validated PDAC diagnosis. Confidence intervals describe "
        "the recorded patient/group sampling unit.\n\n"
        + table
        + "```json\n"
        + json.dumps(evidence, indent=2, allow_nan=False)
        + "\n```\n"
    )
    with destination.open("x") as stream:
        stream.write(rendered)
    return {"output": str(destination), "source": str(source)}
