#!/usr/bin/env python3
"""Write and validate a future architecture protocol, without creating a campaign."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from segmentary.medical.data import atomic_write_json, load_manifest, validate_splits
from segmentary.medical.geometry import sha256_file
from segmentary.medical.research_design import (
    build_architecture_study,
    document_sha256,
    validate_architecture_study,
)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--validate", type=Path, help="Validate an existing protocol and exit")
    parser.add_argument("--base-recipe", type=Path)
    parser.add_argument("--definition", type=Path, help="JSON hypothesis, arms and optional seeds")
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--splits", type=Path)
    parser.add_argument(
        "--cohort-report", type=Path, help="Existing validation failure-analysis report"
    )
    parser.add_argument("--source-commit")
    parser.add_argument("--workspace-root", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    if args.validate:
        validate_architecture_study(json.loads(args.validate.read_text()))
        print("Architecture protocol validated; no training was launched.")
        return
    if any(
        getattr(args, name) is None
        for name in (
            "base_recipe",
            "definition",
            "manifest",
            "splits",
            "cohort_report",
            "source_commit",
            "workspace_root",
            "output",
        )
    ):
        parser.error("Planning requires all input, source, workspace and output arguments")
    if args.output.exists() or args.output.is_symlink():
        raise FileExistsError("Study output must be a new directory")
    manifest = load_manifest(args.manifest)
    splits = json.loads(args.splits.read_text())
    validate_splits(manifest, splits)
    report = json.loads(args.cohort_report.read_text())
    cohort = report.get("cohort", {})
    selected = {
        case["case_id"]: case for case in manifest["cases"] if case["case_id"] in splits["val"]
    }
    reference_fingerprint = document_sha256(
        [
            [
                key,
                selected[key]["patient_id"],
                selected[key]["image_sha256"],
                selected[key]["label_sha256"],
            ]
            for key in sorted(selected)
        ]
    )
    if (
        report.get("kind", report.get("schema_kind")) != "medical_failure_analysis"
        or cohort.get("manifest_sha256") != sha256_file(args.manifest)
        or cohort.get("splits_sha256") != sha256_file(args.splits)
        or cohort.get("partition") != "val"
        or cohort.get("reference_fingerprint") != reference_fingerprint
        or len(report.get("cases", [])) != len(splits["val"])
    ):
        raise ValueError(
            "Failure report must bind to the full validation partition of these inputs"
        )
    definition = json.loads(args.definition.read_text())
    if set(definition) - {"hypothesis", "arms", "seeds", "primary_endpoint"}:
        raise ValueError("Unknown study definition fields")
    recipe_text = args.base_recipe.read_text()
    try:
        base_recipe = json.loads(recipe_text)
    except json.JSONDecodeError:
        base_recipe = yaml.safe_load(recipe_text)
    study = build_architecture_study(
        base_recipe=base_recipe,
        source_commit=args.source_commit,
        workspace_root=str(args.workspace_root),
        cohort=cohort,
        **definition,
    )
    validate_architecture_study(study)
    # Dedicated create-only output. Source experiments and workspaces are never opened.
    args.output.mkdir(parents=True)
    atomic_write_json(args.output / "study.json", study)
    atomic_write_json(
        args.output / "inputs.json",
        {
            name: {"path": str(path.resolve()), "sha256": sha256_file(path)}
            for name, path in {
                "base_recipe": args.base_recipe,
                "definition": args.definition,
                "manifest": args.manifest,
                "splits": args.splits,
                "cohort_report": args.cohort_report,
            }.items()
        },
    )
    recipes = args.output / "recipes"
    recipes.mkdir()
    for run_id, run in study["runs"].items():
        atomic_write_json(recipes / f"{run_id}.json", run["recipe"])
    lines = [
        "# Planned architecture study",
        "",
        study["hypothesis"],
        "",
        "**Status: plan only. No models were launched or performance claims established.**",
        "",
        f"Primary endpoint: `{study['primary_endpoint']}` on validation; seeds: {study['seeds']}.",
        "",
        "| Role | Exact changed fields | Nonarchitecture changes |",
        "|---|---|---|",
    ]
    for role, arm in study["arms"].items():
        lines.append(
            f"| {role} | {', '.join(arm['changes']) or 'none'} | {', '.join(arm['nonarchitecture_changes']) or 'none'} |"
        )
    lines.extend(
        [
            "",
            "Before launch:",
            "",
            *(f"- {item}" for item in study["launch_gates"]),
            "",
            "Interpretation:",
            "",
            *(f"- {item}" for item in study["limitations"]),
            "",
        ]
    )
    (args.output / "README.md").write_text("\n".join(lines))
    print(
        json.dumps(
            {
                "status": "planned_not_launched",
                "output": str(args.output.resolve()),
                "runs": len(study["runs"]),
            }
        )
    )


if __name__ == "__main__":
    main()
