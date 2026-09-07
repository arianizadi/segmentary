"""Opt-in instance/panoptic commands; never schedules semantic campaign jobs."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from .config import load_config
from .runner import (
    check_split_overlap,
    dataset,
    evaluate,
    file_digest,
    load_checkpoint,
    predict,
    train,
    write_json,
)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Train, evaluate and export instance/panoptic masks"
    )
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("validate", "train", "eval", "predict"):
        command = commands.add_parser(name)
        command.add_argument("config", type=Path)
        if name in ("eval", "predict"):
            command.add_argument("--checkpoint", type=Path, required=True)
            command.add_argument("--out", type=Path, required=True)
        if name == "train":
            command.add_argument(
                "--resume", type=Path, help="Continue a trusted full last.pt checkpoint"
            )
        if name == "predict":
            command.add_argument("--images", type=Path, required=True)
    args = parser.parse_args(argv)
    config = load_config(args.config)
    if args.command == "train":
        result = train(config, resume=args.resume)
        print(json.dumps({k: result[k] for k in ("status", "steps", "best_metric", "best_step")}))
    elif args.command == "validate":
        training = dataset(config, config.train, training=True)
        validation = dataset(config, config.val, categories=training.categories)
        check_split_overlap(config, training, validation)
        for data in (training, validation):
            for _ in data:
                pass
        print(
            json.dumps(
                {
                    "task": config.task,
                    "train_images": len(training),
                    "val_images": len(validation),
                    "categories": training.categories,
                }
            )
        )
    elif args.command == "eval":
        if args.out.exists():
            raise FileExistsError(args.out)
        model = load_checkpoint(config, args.checkpoint)
        data = dataset(config, config.val, categories=model.object_categories)
        result = evaluate(model, config, data)
        result.update(
            task=config.task,
            config=asdict(config),
            checkpoint_sha256=file_digest(args.checkpoint),
            annotations_sha256=file_digest(Path(config.val.annotations)),
        )
        write_json(args.out, result)
        print(json.dumps(result))
    else:
        result = predict(config, args.checkpoint, args.images, args.out)
        print(json.dumps({"images": len(result["images"]), "output": str(args.out)}))


if __name__ == "__main__":
    main()
