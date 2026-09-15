#!/usr/bin/env python3
"""Paired patient comparison of complete failure reports, optionally across seeds."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from segmentary.medical.data import atomic_write_json
from segmentary.medical.research_design import compare_failure_reports


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--pairs", type=Path, required=True, help="JSON list of report/model/seed pair declarations"
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--metric", choices=("mass_dice", "pancreas_dice"), default="mass_dice")
    parser.add_argument("--bootstrap-samples", type=int, default=10000)
    parser.add_argument("--bootstrap-seed", type=int, default=0)
    args = parser.parse_args(argv)
    if args.output.exists() or args.output.is_symlink():
        raise FileExistsError("Comparison output must be a new directory")
    pairs = json.loads(args.pairs.read_text())
    if not isinstance(pairs, list):
        raise ValueError("Pairs document must be a list")
    for pair in pairs:
        if not isinstance(pair, dict) or set(pair) != {
            "baseline_report",
            "candidate_report",
            "baseline_model",
            "candidate_model",
            "training_seed",
        }:
            raise ValueError(
                "Each pair needs exactly two report paths, two model IDs and training_seed"
            )
        for side in ("baseline", "candidate"):
            path = Path(pair[f"{side}_report"])
            if not path.is_absolute():
                path = args.pairs.resolve().parent / path
            pair[f"{side}_report"] = json.loads(path.read_text())
    result = compare_failure_reports(
        pairs,
        metric=args.metric,
        bootstrap_samples=args.bootstrap_samples,
        bootstrap_seed=args.bootstrap_seed,
    )
    args.output.mkdir(parents=True)
    atomic_write_json(args.output / "comparison.json", result)
    lines = [
        "# Paired failure comparison",
        "",
        f"Status: **{result['status']}**.",
        "",
        f"Metric: {result['metric']}; differences are candidate minus baseline on the 0-1 scale.",
        f"Complete pairs: {result['complete_pairs']}/{result['expected_pairs']}; training seeds: {result['training_seeds']}.",
        "",
    ]
    aggregate = result["conditional_patient_bootstrap"]
    if aggregate:
        lines.append(
            f"Equal-weight patient mean difference: {aggregate['mean']:.6f}; conditional 95% patient interval: {aggregate['ci']}."
        )
        lines.append(
            f"Across-seed sample SD of patient mean difference: {result['training_seed_variation']['sample_sd_of_patient_mean_delta']} (descriptive, not a confidence interval)."
        )
    else:
        lines.append(
            "Inference withheld: missing/failed/undefined outcomes remain listed in comparison.json. No complete-case result is substituted."
        )
    lines.extend(["", *(f"- {item}" for item in result["limitations"]), ""])
    (args.output / "README.md").write_text("\n".join(lines))
    print(json.dumps({"status": result["status"], "output": str(args.output.resolve())}))


if __name__ == "__main__":
    main()
