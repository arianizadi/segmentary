#!/usr/bin/env python3
"""Create immutable failure diagnostics and offline CT review from completed runs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from segmentary.medical.failure_analysis import analyze, read_json
from segmentary.medical.failure_review import validate_decisions


def campaign_spec(campaign: Path, run_ids: list[str]) -> dict:
    if not run_ids or len(set(run_ids)) != len(run_ids):
        raise ValueError("Explicit unique completed run IDs are required")
    path = campaign / "campaign.json" if campaign.is_dir() else campaign
    spec = read_json(path)
    state = read_json(path.parent / "state/status.json")
    states = {r["id"]: r for r in state["runs"]}
    models = []
    for name in run_ids:
        run = next((r for r in spec["runs"] if r["id"] == name), None)
        if run is None or states.get(name, {}).get("status") != "completed":
            raise ValueError(f"Run {name} is not completed; leave active experiments untouched")
        workspace = Path(run["workspace"])
        resolved = read_json(workspace / "resolved-config.json")
        model = {
            "id": name,
            "prediction_dir": states[name]["predictions"],
            "evaluation_report": str(Path(states[name]["evaluation"]) / "report.json"),
            "seed": resolved.get("seed"),
        }
        if resolved.get("roi_manifest"):
            model.update(
                roi_manifest=resolved["roi_manifest"],
                roi_manifest_sha256=resolved["roi_manifest_sha256"],
            )
        models.append(model)
    return {
        "manifest": spec["manifest"],
        "splits": spec["splits"],
        "partition": "val",
        "models": models,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--spec", type=Path, help="Explicit manifest/splits/models JSON")
    source.add_argument("--campaign", type=Path)
    source.add_argument("--review-report", type=Path, help="Validate exported human decisions only")
    parser.add_argument("--decisions", type=Path)
    parser.add_argument("--run-ids", nargs="+")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--review-limit", type=int, default=8)
    parser.add_argument("--review-random", type=int, default=2)
    parser.add_argument(
        "--slices-per-plane", type=int, default=3, help="0 exports every slice of selected cases"
    )
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()
    if args.review_report:
        if not args.decisions:
            parser.error("--decisions is required with --review-report")
        result = validate_decisions(read_json(args.review_report), read_json(args.decisions))
        with args.output.open("x") as f:
            json.dump(result, f, indent=2, allow_nan=False)
        print(json.dumps(result.get("summary", {})))
        return
    if args.campaign and not args.run_ids:
        parser.error("--run-ids required with --campaign")
    spec = read_json(args.spec) if args.spec else campaign_spec(args.campaign, args.run_ids)
    report = analyze(
        spec,
        args.output,
        review_limit=args.review_limit,
        review_random=args.review_random,
        slices_per_plane=args.slices_per_plane,
        seed=args.seed,
    )
    print(
        json.dumps(
            {
                "report_id": report["report_id"],
                "cases": len(report["cases"]),
                "coverage": {
                    m: {k: v for k, v in x.items() if k != "buckets"}
                    for m, x in report["summaries"].items()
                },
                "output": str(args.output),
            }
        )
    )


if __name__ == "__main__":
    main()
