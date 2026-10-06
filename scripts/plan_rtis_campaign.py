"""Prepare RTIS configs and provenance without starting training or a publisher."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import yaml

from segmentary import gpu_policy
from segmentary.config import load_experiment, to_dict
from segmentary.curriculum import validate_training_contract

DEFAULT_CAVEATS = [
    "Original recording groups need confirmation.",
    "Only FPN-ResNet50 and SegFormer-B2 have RTIS diagnostics so far.",
    "Source checkpoint existence checked here; hashes must be verified before launch.",
    "Transfer uses the existing raw/EMA-safe warm-start policy; inference diagnostics use raw.",
]


def dataset_name(spec) -> str:
    """Manifest ``dataset`` wins; otherwise the data name in the dataset config."""
    if spec.get("dataset"):
        return str(spec["dataset"])
    config = yaml.safe_load(Path(spec["dataset_config"]).read_text())
    return str(config["stages"][0]["data"][0]["name"])


PRIMARY_CHECKPOINTS = ("best", "final")


CV_KEYS = (
    "scheme",
    "folds",
    "seed",
    "restarts",
    "stratify",
    "pool",
    "holdout",
    "val_min_side",
    "primary_checkpoint",
    "run_folds",
)


def primary_checkpoint(spec):
    """``final`` scores the fixed-budget endpoint, so nothing may stop or select on val.

    Cross-validation defaults to ``final``: the held-out fold must not choose the result."""
    cv = spec.get("cross_validation") or {}
    values = {spec.get("primary_checkpoint"), cv.get("primary_checkpoint")} - {None}
    if len(values) > 1:
        raise ValueError(f"Conflicting primary_checkpoint values: {sorted(values)}")
    value = values.pop() if values else ("final" if cv else "best")
    if value not in PRIMARY_CHECKPOINTS:
        raise ValueError(f"primary_checkpoint must be one of {PRIMARY_CHECKPOINTS}: {value!r}")
    if value == "final" and spec.get("early_stopping_patience") is not None:
        raise ValueError("primary_checkpoint: final requires early_stopping_patience to be unset")
    return value


def _names(value):
    return sorted([value] if isinstance(value, str) else value)


def cross_validation(spec, root):
    """Fold views of ``root`` (``cv-spec.json`` + ``fold-<k>/``) checked against the manifest.

    Returns ``None`` without a ``cross_validation`` block; otherwise the plan's record of the
    spec and of each planned fold dataset (root and split hash)."""
    cv = spec.get("cross_validation")
    if cv is None:
        return None
    unknown = sorted(set(cv) - set(CV_KEYS))
    if unknown:
        raise ValueError(f"Unknown cross_validation keys: {unknown}")
    spec_path = root / "cv-spec.json"
    if not spec_path.is_file():
        raise ValueError(f"{root} has no cv-spec.json; make folds with segmentary-make-split")
    folds_spec = json.loads(spec_path.read_text())
    method = folds_spec["method"]
    actual = {
        "scheme": folds_spec["scheme"],
        "folds": method["folds"],
        "seed": method["seed"],
        "restarts": method["restarts"],
        "stratify": {
            "anomaly_classes": sorted(method["anomaly_classes"]),
            "rare_threshold": method["rare_threshold"],
        },
        "pool": sorted(method["pool_splits"]),
        "holdout": sorted(method["holdout_splits"]),
        "val_min_side": method["val_min_side"],
    }
    wanted = dict(cv)
    if "stratify" in wanted:
        wanted["stratify"] = dict(wanted["stratify"])
        if "anomaly_classes" in wanted["stratify"]:
            wanted["stratify"]["anomaly_classes"] = _names(wanted["stratify"]["anomaly_classes"])
    for key in ("pool", "holdout"):
        if key in wanted:
            wanted[key] = _names(wanted[key])
    missing = [key for key in ("scheme", "folds") if key not in cv]
    if missing:
        raise ValueError(f"cross_validation needs {missing}")
    if "stratify" in wanted:  # compare only the stratify keys the manifest names
        actual["stratify"] = {k: actual["stratify"].get(k) for k in wanted["stratify"]}
    differ = {k: (wanted[k], v) for k, v in actual.items() if k in wanted and wanted[k] != v}
    if differ:
        raise ValueError(f"cross_validation differs from {spec_path} (manifest, spec): {differ}")
    planned = sorted(cv.get("run_folds", range(method["folds"])))
    if not planned or not set(planned) <= set(range(method["folds"])):
        raise ValueError(f"run_folds {planned} outside 0..{method['folds'] - 1}")
    spec_sha = hashlib.sha256(spec_path.read_bytes()).hexdigest()
    fold_datasets = {}
    for k in planned:
        fold_root = root / f"fold-{k}"
        splits = json.loads((fold_root / "splits.json").read_text())
        if splits.get("_cv_fold") != k or splits.get("_cv_spec_sha256") != spec_sha:
            raise ValueError(f"{fold_root} is not fold {k} of {spec_path}")
        fold_datasets[str(k)] = {
            "root": str(fold_root),
            "split_sha256": hashlib.sha256((fold_root / "splits.json").read_bytes()).hexdigest(),
        }
    return {
        "scheme": folds_spec["scheme"],
        "folds": method["folds"],
        "planned_folds": planned,
        "spec": str(spec_path),
        "spec_sha256": spec_sha,
        "grouping_status": folds_spec["source"]["grouping_status"],
        "fold_datasets": fold_datasets,
    }


def select_models(catalog, spec):
    models = [m for m in catalog["models"] if "alias_of" not in m]
    wanted = spec.get("models")
    if wanted is None:
        return models
    known = {m["id"]: m for m in models}
    unknown = [m for m in wanted if m not in known]
    if unknown or len(set(wanted)) != len(wanted):
        raise ValueError(f"Manifest models unknown to the catalog or duplicated: {unknown}")
    return [known[m] for m in wanted]


def build_jobs(models, spec, lookup, root, out, folds=None):
    """One job per model x protocol x seed; with ``folds`` ({fold: root}) also per fold."""
    targets = [(None, root)] if folds is None else sorted(folds.items())
    jobs = []
    for model in models:
        layers = [Path("configs/base.yaml"), Path(model["config"])]
        if model.get("campaign_config"):
            layers.append(Path(model["campaign_config"]))
        layers.append(Path(spec["dataset_config"]))
        for protocol, settings in spec["protocols"].items():
            allowed = (spec.get("model_protocols") or {}).get(model["id"])
            if allowed is not None and protocol not in allowed:
                continue
            source = None
            if settings["source_protocol"] is not None:
                source = lookup.get((model["id"], settings["source_protocol"]))
                if source is None or not Path(source["checkpoint"]).is_file():
                    raise ValueError(f"Missing source endpoint: {model['id']} / {protocol}")
            for seed, fold, data_root in [(s, f, r) for s in spec["seeds"] for f, r in targets]:
                name = (
                    f"{model['id']}--{protocol}--seed-{seed}"
                    if fold is None
                    else f"{model['id']}--{protocol}--fold-{fold}--seed-{seed}"
                )
                cfg = load_experiment(layers)
                cfg.name = name
                cfg.taxonomy_root = str(Path("taxonomy").resolve())
                cfg.output_root = str(out.resolve() / "future-runs")
                cfg.train.seed = seed
                cfg.train.iters = spec["target_steps"]
                cfg.train.batch_size = spec["batch_size"]
                cfg.train.accum = spec["accumulation"]
                cfg.train.val_every = spec["validation_interval"]
                cfg.train.ckpt_every = spec.get("checkpoint_interval", spec["validation_interval"])
                cfg.train.selection_metric = spec.get("selection_metric", "val/miou")
                cfg.train.early_stopping_patience = spec.get("early_stopping_patience")
                cfg.train.early_stopping_min_delta = spec.get("early_stopping_min_delta", 0.0)
                cfg.train.devices = 1
                cfg.train.num_workers = spec.get("num_workers", 2)
                cfg.eval.num_workers = spec.get("num_workers", 2)
                stage = cfg.stages[0]
                stage.data[0].root = str(data_root)
                stage.init_from = "pretrained" if source is None else source["checkpoint"]
                # RailUnion and RTIS both have 21 channels but different meanings.
                # Never inherit their classifiers just because shapes match.
                stage.reset_head = source is not None
                stage.lr_scale = 1.0 if source is None else 0.1
                stage.head_group_lr_scale = 1.0
                validate_training_contract(cfg)
                target = out / "configs" / (name + ".yaml")
                target.parent.mkdir(exist_ok=True)
                target.write_text(yaml.safe_dump(to_dict(cfg), sort_keys=False))
                # Parse the serialized final config, not only the input layers.
                validate_training_contract(load_experiment([target]))
                jobs.append(
                    {
                        "name": name,
                        "model": model["id"],
                        "protocol": protocol,
                        "seed": seed,
                        "config": str(target.resolve()),
                        "config_sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
                        "source_checkpoint": source,
                        "reset_head": stage.reset_head,
                        "status": "prepared_not_launched",
                    }
                )
                if fold is not None:
                    jobs[-1]["fold"] = fold
    return jobs


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--manifest", type=Path, required=True)
    ap.add_argument("--checkpoints", type=Path, required=True)
    ap.add_argument("--dataset-root", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument(
        "--gpus",
        required=True,
        type=gpu_policy.parse_gpus,
        help="GPU indices this campaign may ever use, e.g. 2,3,4,5,6,7,8,9; frozen into plan.json",
    )
    args = ap.parse_args()
    spec = yaml.safe_load(args.manifest.read_text())
    catalog = yaml.safe_load(Path(spec["model_catalog"]).read_text())
    sources = json.loads(args.checkpoints.read_text())
    lookup = {(r["model"], r["protocol"]): r for r in sources}
    if len(lookup) != len(sources):
        raise ValueError("Ambiguous duplicate source checkpoints")
    root = args.dataset_root.resolve()
    dataset = dataset_name(spec)
    primary = primary_checkpoint(spec)
    cv = cross_validation(spec, root)
    if cv is None:
        split_hash = hashlib.sha256((root / "splits.json").read_bytes()).hexdigest()
        grouping = json.loads((root / "splits.json").read_text())["_grouping_status"]
    else:
        # The whole design's identity; each job is checked against its own fold's split.
        split_hash, grouping = cv["spec_sha256"], cv["grouping_status"]
    models = select_models(catalog, spec)
    restrict = spec.get("model_protocols") or {}
    unknown = sorted(set(restrict) - {m["id"] for m in models}) + sorted(
        {p for v in restrict.values() for p in v} - set(spec["protocols"])
    )
    if unknown:
        raise ValueError(f"model_protocols names unknown models or protocols: {unknown}")
    args.out.mkdir(parents=True, exist_ok=False)
    if cv is None:
        jobs = build_jobs(models, spec, lookup, root, args.out)
    else:
        fold_roots = {int(k): Path(v["root"]) for k, v in cv["fold_datasets"].items()}
        jobs = build_jobs(models, spec, lookup, root, args.out, folds=fold_roots)
    result = {
        "dataset": dataset,
        "collection_contract": spec.get("collection_contract"),
        "selection_metric": spec.get("selection_metric", "val/miou"),
        "smoke": bool(spec.get("smoke", False)),
        "gpu_allowlist": sorted(args.gpus),
        "split_sha256": split_hash,
        "grouping_status": grouping,
        "target_steps_per_job": spec["target_steps"],
        "publisher": None,
        "launch_status": "not_launched",
        "jobs": jobs,
        "caveats": list(spec.get("caveats", DEFAULT_CAVEATS)),
    }
    if "primary_checkpoint" in spec or cv is not None:
        # Only recorded when the manifest asks, so existing plans stay byte-identical.
        result["primary_checkpoint"] = primary
    if cv is not None:
        result["cross_validation"] = cv
    (args.out / "plan.json").write_text(json.dumps(result, indent=2) + "\n")
    print(f"Prepared {len(jobs)} configs. Training and publisher processes started: 0.")


if __name__ == "__main__":
    main()
