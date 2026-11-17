"""Build the sixteen-job native source-stage request from frozen source evidence.

Original checkpoint/config identities and complete source training receipts are
copied from the supplied evidence. The explicit surviving RailSem19 split is
hashed before writing the new request. This command performs CPU preparation.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "src"))
from scripts.evaluate_rad_source_stages import STAGES, digest
from scripts.prepare_rad_paper_campaign import ACCURACY, FAST

from segmentary.taxonomy import load_space


def prepare(
    *,
    qualified_sources: Path,
    source_metadata: Path,
    source_provenance: Path,
    campaign_json: Path,
    code_sha: str,
    output_root: Path,
    rail_split_file: Path,
    rail_split_sha256: str,
    out: Path,
) -> dict:
    if not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", code_sha):
        raise ValueError("A frozen code commit SHA is required")
    if (
        not re.fullmatch(r"[0-9a-f]{64}", rail_split_sha256)
        or digest(rail_split_file) != rail_split_sha256
    ):
        raise ValueError("Surviving RailSem19 split SHA-256 differs from the frozen split")
    qualified_sources, source_metadata, source_provenance, rail_split_file = (
        path.resolve(strict=True)
        for path in (qualified_sources, source_metadata, source_provenance, rail_split_file)
    )
    if not campaign_json.is_absolute() or not output_root.is_absolute():
        raise ValueError("Campaign and output paths must be absolute frozen destinations")
    if os.path.lexists(out):
        raise FileExistsError("Refusing to overwrite an existing source-stage request")
    sources = json.loads(qualified_sources.read_text())
    metadata = json.loads(source_metadata.read_text())
    provenance = json.loads(source_provenance.read_text())
    by_source = {(row["model"], row["protocol"]): row for row in sources}
    by_metadata = {
        (row["approved_manifest_row"]["model"], row["approved_manifest_row"]["protocol"]): row
        for row in metadata
    }
    if len(by_source) != len(sources) or len(by_metadata) != len(metadata):
        raise ValueError("Source evidence contains ambiguous duplicate endpoints")
    public = {row["model"]: row for row in provenance["reproducibility_table"]}
    models = ACCURACY + FAST
    wanted = {(model, stage) for model in models for stage in STAGES}
    if wanted - set(by_source) or wanted - set(by_metadata) or set(models) - set(public):
        raise ValueError(
            "Every selected model needs both qualified source stages and public provenance"
        )
    jobs = []
    for model in models:
        for stage, (dataset, count) in STAGES.items():
            source, evidence = by_source[(model, stage)], by_metadata[(model, stage)]
            approved = evidence["approved_manifest_row"]
            if any(
                source[key] != approved[key] for key in ("config", "checkpoint", "recorded_sha256")
            ):
                raise ValueError("Metadata endpoint differs from the qualified source manifest")
            cfg = evidence["config_record"]
            data = cfg["stages"][-1]["data"][0]
            if (
                cfg["train"]["seed"] != 0
                or data["name"] != dataset
                or data.get("limit") is not None
            ):
                raise ValueError("Source evidence must describe seed-0 native full validation")
            taxonomy_root = Path(cfg.get("taxonomy_root", "taxonomy"))
            if not taxonomy_root.is_absolute():
                taxonomy_root = REPO / taxonomy_root
            space = load_space(taxonomy_root, cfg["space"])
            record = evidence["complete_training_record"]
            if record.get("seed") != 0:
                raise ValueError("Every archived source receipt must record source seed 0")
            receipt = evidence["training_receipt"]
            config_sha = evidence["config"]["sha256"]
            checkpoint_sha = source["recorded_sha256"]
            if any(
                not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value)
                for value in (receipt["sha256"], config_sha, checkpoint_sha)
            ):
                raise ValueError("Complete source file SHA-256 values are required")
            jobs.append(
                {
                    "name": f"{model}--{stage}--seed-0",
                    "model": model,
                    "stage": stage,
                    "seed": 0,
                    "dataset": dataset,
                    "expected_images": count,
                    "taxonomy": cfg["space"],
                    "class_names": list(space.names),
                    "config": source["config"],
                    "config_sha256": config_sha,
                    "checkpoint": source["checkpoint"],
                    "checkpoint_sha256": checkpoint_sha,
                    "checkpoint_global_step": evidence["checkpoint_metadata"]["global_step"],
                    "training_receipt": {
                        "path": receipt["path"],
                        "sha256": receipt["sha256"],
                        "record": record,
                    },
                    "public_pretraining": public[model],
                    "evaluation_data": {
                        "dataset": dataset,
                        "root": data["root"],
                        "split_file": str(rail_split_file)
                        if stage == "cityscapes_to_railsem19"
                        else None,
                        "split_file_sha256": rail_split_sha256
                        if stage == "cityscapes_to_railsem19"
                        else None,
                    },
                }
            )
    request = {
        "schema_version": 1,
        "source_stage_evaluation_authorized": True,
        "campaign_json": str(campaign_json),
        "code_sha": code_sha,
        "output_root": str(output_root),
        "models": models,
        "jobs": jobs,
        "source_inputs": {
            name: {"path": str(path), "sha256": digest(path)}
            for name, path in (
                ("qualified_sources", qualified_sources),
                ("source_metadata", source_metadata),
                ("source_provenance", source_provenance),
            )
        },
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".source-stage-request-", dir=out.parent)
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump(request, stream, indent=2, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, out)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return request


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for option in (
        "qualified-sources",
        "source-metadata",
        "source-provenance",
        "campaign-json",
        "output-root",
        "rail-split-file",
        "out",
    ):
        parser.add_argument("--" + option, type=Path, required=True)
    parser.add_argument("--code-sha", required=True)
    parser.add_argument("--rail-split-sha256", required=True)
    args = parser.parse_args()
    request = prepare(**vars(args))
    print(
        json.dumps(
            {
                "request": str(args.out.resolve()),
                "jobs": len(request["jobs"]),
                "sha256": digest(args.out),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
