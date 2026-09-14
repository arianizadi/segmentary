"""Separate medical-volume commands; importing help needs no medical extras."""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from pathlib import Path
from typing import Any


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("models", help="List scratch CT architectures, options, and provenance")
    p = commands.add_parser("doctor", help="Check optional packages and GPU visibility")
    p.add_argument("--require-training", action="store_true")
    p.add_argument("--backend-python", help="Dedicated nnU-Net environment interpreter")
    p = commands.add_parser("audit", help="Fully audit Task07 volumes and write a manifest")
    p.add_argument("--dataset-root", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--groups", type=Path)
    p = commands.add_parser(
        "audit-pants", help="Audit PanTS binary masks and preserve official partitions"
    )
    p.add_argument("--dataset-root", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--metadata", type=Path)
    p.add_argument(
        "--audit-report",
        type=Path,
        help="Collect per-case failures and preserve successful journals; no manifest on any failure",
    )
    p.add_argument("--prepared-root", type=Path)
    p.add_argument("--groups", type=Path)
    p.add_argument(
        "--exclude-cases", type=Path, help="JSON exclusions with case ID, reason and source URL"
    )
    p.add_argument(
        "--case-id", action="append", help="Explicit official-training-only smoke subset"
    )
    p.add_argument(
        "--allow-missing-negative-lesion",
        action="store_true",
        help="Explicitly allow absent lesion masks only when metadata tumor? is 0",
    )
    p.add_argument(
        "--normalize-unknown-units-from-metadata",
        action="store_true",
        help="Create derived mm-unit copies only when unknown-unit grids agree with metadata spacing",
    )
    p.add_argument(
        "--normalize-binary-roundoff",
        action="store_true",
        help="Create derived binary uint8 masks only for finite values within absolute 1e-6 of zero or one",
    )
    p = commands.add_parser(
        "split-pants", help="Split PanTS official training groups; reserve official test"
    )
    p.add_argument("--manifest", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--val-fraction", type=float, default=0.15)
    p.add_argument("--seed", type=int, default=0)
    p = commands.add_parser("subset", help="Make a traceable subset for a separate smoke run")
    p.add_argument("--manifest", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--case-id", action="append", required=True)
    p = commands.add_parser("split", help="Write immutable patient/group-disjoint splits")
    p.add_argument("--manifest", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--train-fraction", type=float, default=0.7)
    p.add_argument("--val-fraction", type=float, default=0.15)
    p.add_argument("--seed", type=int, default=0)
    p = commands.add_parser("convert-dicom", help="Convert one regular CT series to NIfTI")
    p.add_argument("--series", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--mask", type=Path)
    for stage in ("prepare", "preprocess", "train", "resume", "predict", "cancel"):
        p = commands.add_parser(stage, help=f"Medical backend {stage} stage")
        p.add_argument("--config", type=Path, required=True)
        if stage != "cancel":
            p.add_argument("--dry-run", action="store_true")
        if stage == "prepare":
            p.add_argument("--manifest", type=Path, required=True)
            p.add_argument("--splits", type=Path, required=True)
        if stage == "resume":
            p.add_argument(
                "--checkpoint",
                choices=("checkpoint_latest.pth", "checkpoint_best.pth", "checkpoint_final.pth"),
            )
        if stage == "predict":
            p.add_argument(
                "--partition", choices=("train", "val", "test", "unlabeled"), default="val"
            )
            p.add_argument("--final-test", action="store_true")
            p.add_argument("--checkpoint", default="checkpoint_best.pth")
    p = commands.add_parser(
        "continue-scratch",
        help="Create an audited new-workspace continuation from own scratch checkpoints",
    )
    p.add_argument("--source-workspace", type=Path, required=True)
    p.add_argument("--config", type=Path, required=True)
    p.add_argument(
        "--source-code-root",
        type=Path,
        required=True,
        help="Original frozen medical source directory",
    )
    p.add_argument(
        "--policy", type=Path, required=True, help="Reviewed exact source-map and evidence policy"
    )
    p.add_argument("--action", choices=("predict", "resume"), required=True)
    p.add_argument("--dry-run", action="store_true")
    p = commands.add_parser("evaluate", help="Score saved native-space volume predictions")
    p.add_argument("--manifest", type=Path, required=True)
    p.add_argument("--predictions", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--splits", type=Path, required=True)
    p.add_argument("--partition", choices=("train", "val", "test"), default="val")
    p.add_argument("--final-test", action="store_true")
    p.add_argument(
        "--pancreas-exclusive", action="store_true", help="Score label 1 instead of union 1+2"
    )
    p.add_argument("--surface-tolerance-mm", type=float)
    p.add_argument("--bootstrap-samples", type=int, default=1000)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--review-overlays", action="store_true")
    p.add_argument("--lesion-iou-threshold", type=float)
    p = commands.add_parser("compare", help="Paired patient-level comparison of saved reports")
    p.add_argument("--left", type=Path, required=True)
    p.add_argument("--right", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--region", choices=("pancreas", "mass"), default="mass")
    p.add_argument("--metric", choices=("dice", "surface_dice", "hd95_mm"), default="dice")
    p.add_argument("--bootstrap-samples", type=int, default=1000)
    p.add_argument("--seed", type=int, default=0)
    p = commands.add_parser("report", help="Render saved evaluation evidence as Markdown")
    p.add_argument("--input", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    return parser


def _config(path: Path) -> Any:
    import yaml

    from .backend import NNUNetConfig
    from .torch_config import TorchConfig

    # PyYAML's YAML 1.1 resolver treats valid JSON exponent numbers such as
    # 1e-05 as strings. JSON run records must retain their numeric types.
    raw = (
        json.loads(path.read_text())
        if path.suffix.lower() == ".json"
        else yaml.safe_load(path.read_text())
    )
    if not isinstance(raw, dict):
        raise ValueError("Medical configuration must be a mapping")
    backend = raw.get("backend", "nnunet")
    if backend not in {"nnunet", "torch"}:
        raise ValueError("backend must be nnunet or torch")
    config_type = TorchConfig if backend == "torch" else NNUNetConfig
    if backend == "nnunet":
        raw.pop("backend", None)
    allowed = {field.name for field in dataclasses.fields(config_type)}
    unknown = set(raw) - allowed
    if unknown:
        raise ValueError(f"Unknown medical configuration keys: {sorted(unknown)}")
    if "workspace" not in raw or not isinstance(raw["workspace"], str):
        raise ValueError("workspace must be an explicit path string")
    workspace = Path(raw["workspace"]).expanduser()
    raw["workspace"] = workspace if workspace.is_absolute() else (path.parent / workspace).resolve()
    return config_type(**raw)


def dispatch(args: argparse.Namespace) -> Any:
    command = args.command
    if command == "models":
        from .model_registry import catalog

        return {
            "backend": "torch",
            "initialization": "scratch",
            "models": catalog(),
            "nnunet": "Official ResEnc M/L/XL remain available through backend: nnunet",
        }
    if command == "doctor":
        from .runtime import doctor

        return doctor(require_training=args.require_training, backend_python=args.backend_python)
    if command == "audit":
        from .data import audit_task07

        return audit_task07(args.dataset_root, args.output, groups_path=args.groups)
    if command == "audit-pants":
        from .pants import audit_pants

        return audit_pants(
            args.dataset_root,
            args.output,
            metadata_path=args.metadata,
            prepared_root=args.prepared_root,
            groups_path=args.groups,
            exclude_cases_path=args.exclude_cases,
            audit_report_path=args.audit_report,
            case_ids=args.case_id,
            allow_missing_negative_lesion=args.allow_missing_negative_lesion,
            normalize_unknown_units_from_metadata=args.normalize_unknown_units_from_metadata,
            normalize_binary_roundoff=args.normalize_binary_roundoff,
        )
    if command == "split-pants":
        from .pants import make_pants_splits

        return make_pants_splits(
            args.manifest, args.output, val_fraction=args.val_fraction, seed=args.seed
        )
    if command == "subset":
        from .data import subset_manifest

        return subset_manifest(args.manifest, args.output, args.case_id)
    if command == "split":
        from .data import make_splits

        return make_splits(
            args.manifest,
            args.output,
            train_fraction=args.train_fraction,
            val_fraction=args.val_fraction,
            seed=args.seed,
        )
    if command == "convert-dicom":
        from .geometry import convert_dicom_series

        return convert_dicom_series(args.series, args.output, mask_path=args.mask)
    if command == "compare":
        from .evaluation import paired_comparison

        if args.output.exists():
            raise FileExistsError(f"Comparison output already exists: {args.output}")
        result = paired_comparison(
            json.loads(args.left.read_text()),
            json.loads(args.right.read_text()),
            region=args.region,
            metric=args.metric,
            bootstrap_samples=args.bootstrap_samples,
            seed=args.seed,
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x") as stream:
            json.dump(result, stream, indent=2, allow_nan=False)
        return result
    if command == "report":
        from .runtime import write_report

        return write_report(str(args.input), str(args.output))
    if command == "evaluate":
        from .data import load_manifest, validate_splits
        from .evaluation import evaluate_predictions

        if args.partition == "test" and not args.final_test:
            raise ValueError("Test evaluation requires explicit --final-test")
        if args.final_test and args.partition != "test":
            raise ValueError("--final-test is only valid for the test partition")
        manifest = load_manifest(args.manifest)
        splits = json.loads(args.splits.read_text())
        validate_splits(manifest, splits)
        return evaluate_predictions(
            args.manifest,
            args.predictions,
            args.output,
            case_ids=splits[args.partition],
            pancreas_include_mass=not args.pancreas_exclusive,
            surface_tolerance_mm=args.surface_tolerance_mm,
            bootstrap_samples=args.bootstrap_samples,
            seed=args.seed,
            review_overlays=args.review_overlays,
            lesion_iou_threshold=args.lesion_iou_threshold,
        )
    from . import backend, torch_backend
    from .torch_config import TorchConfig

    config = _config(args.config)
    implementation: Any = torch_backend if isinstance(config, TorchConfig) else backend
    if command == "continue-scratch":
        from .continuation import create_continuation

        if not isinstance(config, TorchConfig):
            raise ValueError("Performance continuation currently supports the Torch backend only")
        return create_continuation(
            args.source_workspace,
            config,
            source_code_root=args.source_code_root,
            policy=args.policy,
            action=args.action,
            dry_run=args.dry_run,
        )
    if command == "prepare":
        return implementation.prepare_dataset(
            args.manifest, args.splits, config, dry_run=args.dry_run
        )
    if command == "preprocess":
        return implementation.plan_and_preprocess(config, dry_run=args.dry_run)
    if command in ("train", "resume"):
        return implementation.train(
            config,
            resume=command == "resume",
            resume_checkpoint=getattr(args, "checkpoint", None),
            dry_run=args.dry_run,
        )
    if command == "predict":
        return implementation.predict(
            config,
            partition=args.partition,
            final_test=args.final_test,
            checkpoint=args.checkpoint,
            dry_run=args.dry_run,
        )
    if command == "cancel":
        return implementation.cancel(config)
    raise ValueError(f"Unknown command: {command}")


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        result = dispatch(args)
        visible = result
        if isinstance(result, dict) and isinstance(result.get("cases"), list):
            visible = {key: value for key, value in result.items() if key != "cases"}
            visible["case_count"] = len(result["cases"])
            visible["output"] = str(getattr(args, "output", ""))
        print(json.dumps(visible, indent=2, allow_nan=False, default=str))
        return 1 if args.command == "doctor" and not result["passed"] else 0
    except (ValueError, TypeError, OSError, RuntimeError, ImportError, KeyError) as exc:
        print(f"segmentary-medical: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
