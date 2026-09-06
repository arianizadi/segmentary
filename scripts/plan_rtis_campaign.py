"""Prepare RTIS configs and provenance without starting training or a publisher."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import yaml

from segmentary.config import load_experiment, to_dict
from segmentary.curriculum import validate_training_contract


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--manifest", type=Path, default=Path("configs/campaigns/paul-test-rtis.yaml"))
    ap.add_argument("--checkpoints", type=Path, required=True)
    ap.add_argument("--dataset-root", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    spec = yaml.safe_load(args.manifest.read_text())
    catalog = yaml.safe_load(Path(spec["model_catalog"]).read_text())
    sources = json.loads(args.checkpoints.read_text())
    lookup = {(r["model"], r["protocol"]): r for r in sources}
    if len(lookup) != len(sources):
        raise ValueError("Ambiguous duplicate source checkpoints")
    root = args.dataset_root.resolve()
    split_hash = hashlib.sha256((root / "splits.json").read_bytes()).hexdigest()
    args.out.mkdir(parents=True, exist_ok=False)
    jobs = []
    for model in catalog["models"]:
        if "alias_of" in model:
            continue
        layers = [Path("configs/base.yaml"), Path(model["config"])]
        if model.get("campaign_config"):
            layers.append(Path(model["campaign_config"]))
        layers.append(Path(spec["dataset_config"]))
        for protocol, settings in spec["protocols"].items():
            source = None
            if settings["source_protocol"] is not None:
                source = lookup.get((model["id"], settings["source_protocol"]))
                if source is None or not Path(source["checkpoint"]).is_file():
                    raise ValueError(f"Missing source endpoint: {model['id']} / {protocol}")
            for seed in spec["seeds"]:
                name = f"{model['id']}--{protocol}--seed-{seed}"
                cfg = load_experiment(layers)
                cfg.name = name
                cfg.taxonomy_root = str(Path("taxonomy").resolve())
                cfg.output_root = str(args.out.resolve() / "future-runs")
                cfg.train.seed = seed
                cfg.train.iters = spec["target_steps"]
                cfg.train.batch_size = spec["batch_size"]
                cfg.train.accum = spec["accumulation"]
                cfg.train.val_every = spec["validation_interval"]
                cfg.train.ckpt_every = spec["validation_interval"]
                cfg.train.devices = 1
                stage = cfg.stages[0]
                stage.data[0].root = str(root)
                stage.init_from = "pretrained" if source is None else source["checkpoint"]
                # RailUnion and RTIS both have 21 channels but different meanings.
                # Never inherit their classifiers just because shapes match.
                stage.reset_head = source is not None
                stage.lr_scale = 1.0 if source is None else 0.1
                stage.head_group_lr_scale = 1.0
                validate_training_contract(cfg)
                target = args.out / "configs" / (name + ".yaml")
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
    result = {
        "dataset": "paul-test-rtis",
        "split_sha256": split_hash,
        "grouping_status": json.loads((root / "splits.json").read_text())["_grouping_status"],
        "target_steps_per_job": spec["target_steps"],
        "publisher": None,
        "launch_status": "not_launched",
        "jobs": jobs,
        "caveats": [
            "Original recording groups need confirmation.",
            "Only FPN-ResNet50 and SegFormer-B2 have RTIS diagnostics so far.",
            "Source checkpoint existence checked here; hashes must be verified before launch.",
            "Transfer uses the existing raw/EMA-safe warm-start policy; inference diagnostics use raw.",
        ],
    }
    (args.out / "plan.json").write_text(json.dumps(result, indent=2) + "\n")
    print(f"Prepared {len(jobs)} configs. Training and publisher processes started: 0.")


if __name__ == "__main__":
    main()
