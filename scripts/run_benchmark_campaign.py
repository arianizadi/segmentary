#!/usr/bin/env python3
"""Launch and report the all-model Cityscapes/RailSem19 benchmark campaign.

Long-running workers are always created as named tmux sessions. A worker refuses
to run outside tmux, and each lane receives exactly one physical GPU through
``CUDA_VISIBLE_DEVICES``. Re-running ``launch`` resumes an interrupted training
attempt from its newest complete periodic checkpoint, including optimizer,
scheduler, EMA, callback, and global-step state. Validated successes are skipped;
a fresh attempt directory is created only when no recovery checkpoint exists.

The campaign manifest fixes three distinct protocols:

* Cityscapes training/evaluation in the standard Cityscapes-19 space;
* RailSem19-only training/evaluation in ``rail_union``;
* staged Cityscapes -> RailSem19 training and RailSem19 evaluation.

No command silently launches work. ``plan`` and ``launch --dry-run`` are
read-only. ``launch`` requires an explicit full git SHA, dataset roots, GPU list,
and tmux prefix.
"""

from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import io
import json
import math
import os
import pickletools
import re
import shlex
import socket
import statistics
import subprocess
import sys
import tempfile
import time
import zipfile
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

_HASH_CACHE: dict[tuple[str, int, int], str] = {}

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from segmentary.checkpoints import TRAINING_RESUME_KEY, read_checkpoint
from segmentary.config import (
    ExperimentConfig,
    config_hash,
    deep_merge,
    from_dict,
    load_yaml,
    to_dict,
)
from segmentary.curriculum import stage_optim_config
from segmentary.taxonomy import load_space
from segmentary.utils.results import load_results

DEFAULT_MANIFEST = Path("configs/campaigns/all_models_cityscapes_railsem19.yaml")
REQUIRED_PROTOCOLS = ("cityscapes", "railsem19", "cityscapes_to_railsem19")
STATUS_SCHEMA_VERSION = 1
CAMPAIGN_SCHEMA_VERSION = 1
COMPLETED_STATUSES = {"succeeded", "reused"}
REPORT_START = "<!-- segmentary:generated-city-rail-benchmark:start -->"
REPORT_END = "<!-- segmentary:generated-city-rail-benchmark:end -->"
AGGREGATE_METRICS = (
    ("miou", "mIoU"),
    ("macc", "mean accuracy"),
    ("mprecision", "mean precision"),
    ("mdice", "mean Dice"),
    ("mspecificity", "mean specificity"),
    ("pixel_accuracy", "pixel accuracy"),
    ("freqw_iou", "frequency-weighted IoU"),
)
RECORD_METRICS = (*AGGREGATE_METRICS, ("boundary_macro_f1", "boundary F1"))
ENV_KEYS = (
    "PL_GLOBAL_SEED",
    "CUDA_DEVICE_ORDER",
    "CUDA_VISIBLE_DEVICES",
    "HF_HOME",
    "PYTHONPATH",
    "MASTER_ADDR",
    "MASTER_PORT",
)

# Relative one-step costs measured by the clean 1024-pixel admission probes.
# They are used only to balance long jobs across lanes; they are not quality or
# production-throughput claims.  Longest-processing-time assignment avoids a
# slow tail while keeping every job on one isolated L40S.
MODEL_COST_WEIGHTS = {
    "smp_unetplusplus_efficientnet_b0": 69.903008,
    "smp_manet_efficientnet_b0": 68.238564,
    "smp_linknet_mobilenet_v2": 50.058847,
    "hf_auto_mobilevit_xxs_deeplabv3": 46.658298,
    "smp_pan_resnext50": 45.291785,
    "upernet_convnext": 39.480023,
    "smp_upernet_resnet101": 38.119629,
    "hf_auto_mobilevitv2_deeplabv3": 34.977712,
    "native_convnext_tiny_uper": 33.769692,
    "smp_fpn_resnet50": 33.441272,
    "native_mobilenetv3_large_deeplabv3plus": 33.168230,
    "hf_auto_mobilenetv2_deeplabv3": 32.924750,
    "native_efficientnet_b0_deeplabv3plus": 31.956622,
    "smp_upernet_mit_b0": 31.691813,
    "smp_pspnet_mobilenet_v2": 31.167704,
    "native_mobilenetv3_large_lraspp": 29.516749,
    "native_convnext_tiny_channelmapper_dpt": 29.236932,
    "hrnet_w48_ocr": 29.063581,
    "hf_auto_beit_base_ade": 27.161277,
    "smp_deeplabv3_resnet50": 26.988280,
    "smp_deeplabv3plus_resnet101": 26.667036,
    "native_resnet101_uper": 26.661503,
    "smp_unet_resnet34": 24.503910,
    "native_resnet50_fpn_ocr": 23.483125,
    "native_resnet18_fpn_segformer_aux": 21.627387,
    "native_resnet50_psp": 20.865928,
    "native_resnet50_deeplabv3plus": 20.773808,
    "hf_auto_upernet_swin_tiny": 20.259855,
    "native_resnet50_aspp": 18.074904,
    "native_resnet18_fpn_fcn": 17.678613,
    "segformer_b5": 6.686036,
    "eomt_dinov3_large": 6.277517,
    "eomt_large": 6.212480,
    "segformer_b2": 6.086527,
    "segformer_b0": 5.826159,
    "hf_auto_segformer_b0": 5.333861,
}


class CampaignError(RuntimeError):
    """A fail-closed campaign contract violation."""


@dataclass(frozen=True)
class ProtocolSpec:
    id: str
    label: str
    curriculum: Path
    final_stage: str
    evaluation_dataset: str
    evaluation_mapping: str
    evaluation_split: str
    evaluation_space: str
    evaluation_split_file: Path | None = None
    evaluation_milestones: tuple[int, ...] = ()


@dataclass(frozen=True)
class ModelSpec:
    id: str
    config: Path
    readme: Path
    alias_of: str | None = None
    campaign_config: Path | None = None


@dataclass(frozen=True)
class CampaignManifest:
    path: Path
    name: str
    protocols: dict[str, ProtocolSpec]
    models: tuple[ModelSpec, ...]
    priority_order: tuple[str, ...]


@dataclass(frozen=True)
class Job:
    model: ModelSpec
    protocol: ProtocolSpec
    seed: int

    @property
    def id(self) -> str:
        return f"{self.model.id}--{self.protocol.id}--seed-{self.seed}"

    @property
    def experiment_name(self) -> str:
        return f"{self.model.id}--{self.protocol.id}"


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _full_sha(value: str) -> str:
    if not re.fullmatch(r"[0-9a-fA-F]{40}", value):
        raise argparse.ArgumentTypeError("expected a full 40-character hexadecimal git SHA")
    return value.lower()


def _positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected an integer") from exc
    if parsed < 1:
        raise argparse.ArgumentTypeError("value must be at least 1")
    return parsed


def _seed_list(value: str) -> tuple[int, ...]:
    try:
        seeds = tuple(int(item.strip()) for item in value.split(","))
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "seeds must be comma-separated non-negative integers"
        ) from exc
    if not seeds or len(set(seeds)) != len(seeds) or any(item < 0 for item in seeds):
        raise argparse.ArgumentTypeError("seeds must be distinct non-negative integers")
    return seeds


def _gpu_list(value: str) -> tuple[int, ...]:
    try:
        gpus = tuple(int(item.strip()) for item in value.split(","))
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "GPUs must be comma-separated non-negative indices"
        ) from exc
    if not gpus or len(set(gpus)) != len(gpus) or any(item < 0 for item in gpus):
        raise argparse.ArgumentTypeError("GPUs must be distinct non-negative indices")
    return gpus


def _tmux_prefix(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", value):
        raise argparse.ArgumentTypeError(
            "tmux prefix must be 1-64 letters, digits, underscores, or hyphens"
        )
    return value


def _repo_path(raw: object, *, field: str, must_exist: bool = True) -> Path:
    if not isinstance(raw, str) or not raw:
        raise CampaignError(f"{field} must be a non-empty repository-relative path")
    relative = Path(raw)
    if relative.is_absolute() or ".." in relative.parts:
        raise CampaignError(f"{field} must stay inside the repository: {raw!r}")
    path = (REPO_ROOT / relative).resolve()
    if not path.is_relative_to(REPO_ROOT):
        raise CampaignError(f"{field} resolves outside the repository: {raw!r}")
    if must_exist and not path.exists():
        raise CampaignError(f"{field} does not exist: {relative}")
    return relative


def _mapping(value: object, *, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise CampaignError(f"{field} must be a mapping")
    return value


def load_campaign_manifest(path: Path | str = DEFAULT_MANIFEST) -> CampaignManifest:
    manifest_path = _repo_path(str(path), field="manifest")
    absolute = REPO_ROOT / manifest_path
    try:
        raw = yaml.safe_load(absolute.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise CampaignError(f"cannot read campaign manifest {manifest_path}: {exc}") from exc
    root = _mapping(raw, field="manifest")
    if root.get("schema_version") != 1:
        raise CampaignError("campaign manifest schema_version must be 1")
    name = root.get("name")
    if not isinstance(name, str) or not re.fullmatch(r"[a-z0-9_]+", name):
        raise CampaignError(
            "campaign manifest name must use lowercase letters, digits, underscores"
        )

    protocol_rows = _mapping(root.get("protocols"), field="manifest.protocols")
    if tuple(protocol_rows) != REQUIRED_PROTOCOLS:
        raise CampaignError(
            f"manifest.protocols must be exactly {list(REQUIRED_PROTOCOLS)}, got {list(protocol_rows)}"
        )
    protocols: dict[str, ProtocolSpec] = {}
    for protocol_id, value in protocol_rows.items():
        row = _mapping(value, field=f"protocols.{protocol_id}")
        label = row.get("label")
        final_stage = row.get("final_stage")
        dataset = row.get("evaluation_dataset")
        mapping = row.get("evaluation_mapping")
        split = row.get("evaluation_split")
        space = row.get("evaluation_space")
        for field_name, field_value in (
            ("label", label),
            ("final_stage", final_stage),
            ("evaluation_dataset", dataset),
            ("evaluation_mapping", mapping),
            ("evaluation_split", split),
            ("evaluation_space", space),
        ):
            if not isinstance(field_value, str) or not field_value:
                raise CampaignError(f"protocols.{protocol_id}.{field_name} must be non-empty")
        split_file = row.get("evaluation_split_file")
        milestone_values = row.get("evaluation_milestones", [])
        if (
            not isinstance(milestone_values, list)
            or any(
                isinstance(step, bool) or not isinstance(step, int) or step < 1
                for step in milestone_values
            )
            or len(set(milestone_values)) != len(milestone_values)
            or milestone_values != sorted(milestone_values)
        ):
            raise CampaignError(
                f"protocols.{protocol_id}.evaluation_milestones must be sorted distinct "
                "positive integers"
            )
        protocols[protocol_id] = ProtocolSpec(
            id=protocol_id,
            label=label,
            curriculum=_repo_path(
                row.get("curriculum"), field=f"protocols.{protocol_id}.curriculum"
            ),
            final_stage=final_stage,
            evaluation_dataset=dataset,
            evaluation_mapping=mapping,
            evaluation_split=split,
            evaluation_space=space,
            evaluation_split_file=(
                _repo_path(split_file, field=f"protocols.{protocol_id}.evaluation_split_file")
                if split_file is not None
                else None
            ),
            evaluation_milestones=tuple(milestone_values),
        )

    model_rows = root.get("models")
    if not isinstance(model_rows, list) or not model_rows:
        raise CampaignError("manifest.models must be a non-empty list")
    models: list[ModelSpec] = []
    for index, value in enumerate(model_rows):
        row = _mapping(value, field=f"models[{index}]")
        model_id = row.get("id")
        if not isinstance(model_id, str) or not re.fullmatch(r"[a-z0-9_]+", model_id):
            raise CampaignError(
                f"models[{index}].id must use lowercase letters, digits, underscores"
            )
        config = _repo_path(row.get("config"), field=f"models[{index}].config")
        readme = _repo_path(row.get("readme"), field=f"models[{index}].readme")
        if config.stem != model_id:
            raise CampaignError(
                f"models[{index}] id {model_id!r} does not match config stem {config.stem!r}"
            )
        if readme.name != "README.md":
            raise CampaignError(f"models[{index}].readme must point to a README.md")
        alias_of = row.get("alias_of")
        if alias_of is not None and (
            not isinstance(alias_of, str) or not re.fullmatch(r"[a-z0-9_]+", alias_of)
        ):
            raise CampaignError(f"models[{index}].alias_of must be a model id")
        raw_campaign_config = row.get("campaign_config")
        campaign_config = (
            _repo_path(raw_campaign_config, field=f"models[{index}].campaign_config")
            if raw_campaign_config is not None
            else None
        )
        models.append(ModelSpec(model_id, config, readme, alias_of, campaign_config))

    if len({model.id for model in models}) != len(models):
        raise CampaignError("manifest model ids are not unique")
    if len({model.config for model in models}) != len(models):
        raise CampaignError("manifest model config paths are not unique")
    catalog = {
        path.relative_to(REPO_ROOT) for path in (REPO_ROOT / "configs/models").glob("*.yaml")
    }
    manifested = {model.config for model in models}
    if manifested != catalog:
        missing = sorted(str(path) for path in catalog - manifested)
        extra = sorted(str(path) for path in manifested - catalog)
        raise CampaignError(
            f"manifest must cover every model recipe exactly once; missing={missing}, extra={extra}"
        )
    raw_priority = root.get("priority_order")
    if not isinstance(raw_priority, list) or any(
        not isinstance(item, str) for item in raw_priority
    ):
        raise CampaignError("manifest.priority_order must be a list of model ids")
    priority_order = tuple(raw_priority)
    model_ids = {model.id for model in models}
    if len(priority_order) != len(set(priority_order)) or set(priority_order) != model_ids:
        raise CampaignError("manifest.priority_order must contain every model id exactly once")
    for model in models:
        if model.alias_of is not None:
            if model.alias_of == model.id or model.alias_of not in model_ids:
                raise CampaignError(f"model {model.id} has invalid alias_of={model.alias_of!r}")
            target = next(item for item in models if item.id == model.alias_of)
            if target.alias_of is not None:
                raise CampaignError(f"model {model.id} aliases another alias {target.id}")
            alias_model = load_yaml(REPO_ROOT / model.config).get("model")
            target_model = load_yaml(REPO_ROOT / target.config).get("model")
            if _canonical_model_config(alias_model) != _canonical_model_config(target_model):
                raise CampaignError(
                    f"model {model.id} alias_of={target.id} does not resolve an equivalent model"
                )

    # Compose each model/protocol once without touching datasets or model weights.
    # This catches a wrong label space or final-stage name before a 111-job plan exists.
    base = load_yaml(REPO_ROOT / "configs/base.yaml")
    for model in models:
        model_layer = load_yaml(REPO_ROOT / model.config)
        for protocol in protocols.values():
            merged = deep_merge(copy.deepcopy(base), model_layer)
            merged = deep_merge(merged, load_yaml(REPO_ROOT / protocol.curriculum))
            if model.campaign_config is not None:
                merged = deep_merge(merged, load_yaml(REPO_ROOT / model.campaign_config))
            cfg = from_dict(ExperimentConfig, merged)
            if cfg.space != protocol.evaluation_space:
                raise CampaignError(
                    f"{model.id}/{protocol.id} resolves space={cfg.space!r}, expected "
                    f"{protocol.evaluation_space!r}"
                )
            if not cfg.stages or cfg.stages[-1].name != protocol.final_stage:
                actual = cfg.stages[-1].name if cfg.stages else None
                raise CampaignError(
                    f"{model.id}/{protocol.id} final stage={actual!r}, expected "
                    f"{protocol.final_stage!r}"
                )

    return CampaignManifest(manifest_path, name, protocols, tuple(models), priority_order)


def campaign_jobs(
    manifest: CampaignManifest, seeds: Sequence[int], *, include_aliases: bool = True
) -> tuple[Job, ...]:
    by_id = {model.id: model for model in manifest.models}
    return tuple(
        Job(by_id[model_id], manifest.protocols[protocol_id], seed)
        for model_id in manifest.priority_order
        if include_aliases or by_id[model_id].alias_of is None
        for protocol_id in REQUIRED_PROTOCOLS
        for seed in seeds
    )


def _job_cost(job: Job) -> float:
    # Every physical protocol now contains 40k optimizer steps. Transfer reuses
    # the ordinary City checkpoint, so only its 40k Rail target stage is priced.
    return MODEL_COST_WEIGHTS[job.model.id]


def partition_jobs(jobs: Sequence[Job], gpus: Sequence[int]) -> dict[int, tuple[Job, ...]]:
    """Balance jobs while keeping every City source immediately before its transfer."""
    if not gpus:
        raise CampaignError("at least one GPU is required")
    unknown = sorted({job.model.id for job in jobs} - MODEL_COST_WEIGHTS.keys())
    if unknown:
        raise CampaignError(f"missing admission cost weights for models: {unknown}")
    lane_units: dict[int, list[tuple[Job, ...]]] = {gpu: [] for gpu in gpus}
    loads = {gpu: 0.0 for gpu in gpus}
    input_order = {job.id: index for index, job in enumerate(jobs)}
    indexed = {(job.model.id, job.seed, job.protocol.id): job for job in jobs}
    units: list[tuple[Job, ...]] = []
    consumed: set[str] = set()
    for job in jobs:
        if job.id in consumed:
            continue
        if job.protocol.id == "cityscapes":
            transfer = indexed.get((job.model.id, job.seed, "cityscapes_to_railsem19"))
            if transfer is None:
                raise CampaignError(f"{job.id} has no City-to-Rail dependency consumer")
            units.append((job, transfer))
            consumed.update((job.id, transfer.id))
        elif job.protocol.id == "cityscapes_to_railsem19":
            continue
        else:
            units.append((job,))
            consumed.add(job.id)
    if consumed != {job.id for job in jobs}:
        raise CampaignError("dependency-aware partition did not consume every physical job")

    units.sort(
        key=lambda unit: (
            -sum(_job_cost(job) for job in unit),
            min(input_order[job.id] for job in unit),
        )
    )
    for unit in units:
        gpu = min(gpus, key=lambda item: (loads[item], gpus.index(item)))
        lane_units[gpu].append(unit)
        loads[gpu] += sum(_job_cost(job) for job in unit)
    # Assignment above is LPT-balanced for minimum makespan. Reordering units
    # within an already assigned lane cannot change that lane's total work, so
    # use the manifest's explicit quality priority for start order. City and
    # transfer remain an indivisible adjacent pair.
    return {
        gpu: tuple(
            job
            for unit in sorted(
                assigned,
                key=lambda value: min(input_order[job.id] for job in value),
            )
            for job in unit
        )
        for gpu, assigned in lane_units.items()
    }


def _git(arguments: Sequence[str]) -> str:
    completed = subprocess.run(
        ["git", *arguments],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        raise CampaignError(f"git {' '.join(arguments)} failed: {detail or completed.returncode}")
    return completed.stdout.strip()


def check_source_provenance(expected_sha: str) -> str:
    actual = _git(["rev-parse", "--verify", "HEAD"]).lower()
    if actual != expected_sha.lower():
        raise CampaignError(f"HEAD is {actual}, expected {expected_sha.lower()}")
    dirty = _git(["status", "--porcelain=v1", "--untracked-files=all"])
    if dirty:
        raise CampaignError(f"worktree is dirty:\n{dirty}")
    return actual


def _sha256(path: Path) -> str:
    stat = path.stat()
    key = (str(path.resolve()), stat.st_size, stat.st_mtime_ns)
    cached = _HASH_CACHE.get(key)
    if cached is not None:
        return cached
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    value = digest.hexdigest()
    _HASH_CACHE[key] = value
    return value


def atomic_write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True, allow_nan=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o644)
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


def atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o644)
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


def _source_file_hashes(manifest: CampaignManifest) -> dict[str, str]:
    paths = {
        Path("configs/base.yaml"),
        manifest.path,
        *(model.config for model in manifest.models),
        *(model.campaign_config for model in manifest.models if model.campaign_config is not None),
        *(protocol.curriculum for protocol in manifest.protocols.values()),
        *(
            protocol.evaluation_split_file
            for protocol in manifest.protocols.values()
            if protocol.evaluation_split_file is not None
        ),
        *(
            Path("taxonomy") / protocol.evaluation_space / "canonical.yaml"
            for protocol in manifest.protocols.values()
        ),
        *(
            Path("taxonomy") / protocol.evaluation_space / f"{protocol.evaluation_mapping}.yaml"
            for protocol in manifest.protocols.values()
        ),
    }
    return {str(path): _sha256(REPO_ROOT / path) for path in sorted(paths)}


def _dataset_roots(cityscapes_root: Path, railsem19_root: Path) -> dict[str, str]:
    roots = {
        "cityscapes": str(cityscapes_root.expanduser().resolve()),
        "railsem19": str(railsem19_root.expanduser().resolve()),
    }
    for name, raw in roots.items():
        path = Path(raw)
        if not path.is_dir():
            raise CampaignError(f"{name} dataset root is not a directory: {path}")
    return roots


def _job_spec(job: Job, lane: str) -> dict[str, Any]:
    spec = {
        "id": job.id,
        "model": job.model.id,
        "model_config": str(job.model.config),
        "model_readme": str(job.model.readme),
        "campaign_config": (
            str(job.model.campaign_config) if job.model.campaign_config is not None else None
        ),
        "protocol": job.protocol.id,
        "protocol_label": job.protocol.label,
        "curriculum": job.protocol.id,
        "curriculum_config": str(job.protocol.curriculum),
        "final_stage": job.protocol.final_stage,
        "evaluation_dataset": job.protocol.evaluation_dataset,
        "evaluation_mapping": job.protocol.evaluation_mapping,
        "evaluation_split": job.protocol.evaluation_split,
        "evaluation_split_file": (
            str(job.protocol.evaluation_split_file)
            if job.protocol.evaluation_split_file is not None
            else None
        ),
        "evaluation_space": job.protocol.evaluation_space,
        "evaluation_milestones": list(job.protocol.evaluation_milestones),
        "seed": job.seed,
        "experiment_name": job.experiment_name,
        "lane": lane,
        "performance_owner": False,
    }
    if job.protocol.id == "cityscapes_to_railsem19" and job.model.alias_of is None:
        spec["depends_on"] = f"{job.model.id}--cityscapes--seed-{job.seed}"
        spec["checkpoint_reuse"] = "all compatible City weights; unified classifier reset"
    return spec


def build_campaign_record(
    *,
    manifest: CampaignManifest,
    campaign: Path,
    expected_sha: str,
    datasets: dict[str, str],
    seeds: Sequence[int],
    gpus: Sequence[int],
    tmux_prefix: str,
    python: Path,
    hf_home: Path | None,
    batch_size: int,
    accum: int,
    train_workers: int,
    eval_workers: int,
    deterministic: bool,
    reuse_roots: Sequence[Path],
    allowed_reuse_shas: Sequence[str],
    publisher_root: Path | None,
    publish_remote: str,
    publish_branch: str,
    publish_interval: int,
) -> dict[str, Any]:
    logical_jobs = campaign_jobs(manifest, seeds)
    jobs = campaign_jobs(manifest, seeds, include_aliases=False)
    protocol_configs = {
        protocol.id: deep_merge(
            load_yaml(REPO_ROOT / "configs/base.yaml"),
            load_yaml(REPO_ROOT / protocol.curriculum),
        )
        for protocol in manifest.protocols.values()
    }
    protocol_iterations = {
        protocol_id: _iteration_plan(config)["total_target_iterations"]
        for protocol_id, config in protocol_configs.items()
    }
    for protocol in manifest.protocols.values():
        config = protocol_configs[protocol.id]
        final_step = _expected_final_step(config, protocol.final_stage)
        checkpoint_every = config.get("train", {}).get("ckpt_every")
        if (
            isinstance(checkpoint_every, bool)
            or not isinstance(checkpoint_every, int)
            or checkpoint_every < 1
        ):
            raise CampaignError(
                f"protocol {protocol.id} has invalid checkpoint cadence {checkpoint_every!r}"
            )
        for milestone in protocol.evaluation_milestones:
            if milestone >= final_step:
                raise CampaignError(
                    f"protocol {protocol.id} milestone {milestone} must precede final "
                    f"step {final_step}"
                )
            if milestone % checkpoint_every:
                raise CampaignError(
                    f"protocol {protocol.id} milestone {milestone} is not aligned to "
                    f"checkpoint cadence {checkpoint_every}"
                )
    assignments = partition_jobs(jobs, gpus)
    lane_records = []
    all_jobs = []
    for lane_index, gpu in enumerate(gpus):
        lane = f"gpu{gpu}"
        session = f"{tmux_prefix}-{lane}"
        lane_jobs = assignments[gpu]
        all_jobs.extend(_job_spec(job, lane) for job in lane_jobs)
        lane_records.append(
            {
                "index": lane_index,
                "id": lane,
                "gpu": gpu,
                "master_port": 29600 + lane_index,
                "tmux_session": session,
                "job_ids": [job.id for job in lane_jobs],
            }
        )
    # Alias rows are logical report cells, not GPU work. They inherit the exact
    # canonical result at report time after the canonical cell validates.
    for job in logical_jobs:
        if job.model.alias_of is None:
            continue
        spec = _job_spec(job, "alias")
        spec["alias_of"] = f"{job.model.alias_of}--{job.protocol.id}--seed-{job.seed}"
        all_jobs.append(spec)

    owner_seed = min(seeds)
    for spec in all_jobs:
        spec["performance_owner"] = bool(
            not spec.get("alias_of")
            and spec["protocol"] == "railsem19"
            and spec["seed"] == owner_seed
        )

    return {
        "schema_version": CAMPAIGN_SCHEMA_VERSION,
        "name": manifest.name,
        "campaign": str(campaign),
        "created_at": _now(),
        "host": socket.gethostname(),
        "source": {
            "repository": _git(["config", "--get", "remote.origin.url"]),
            "expected_git_sha": expected_sha,
            "manifest": str(manifest.path),
            "files_sha256": _source_file_hashes(manifest),
        },
        "datasets": datasets,
        "execution": {
            "seeds": list(seeds),
            "gpus": list(gpus),
            "tmux_prefix": tmux_prefix,
            "python": str(python.expanduser().resolve()),
            "hf_home": str(hf_home.expanduser().resolve()) if hf_home is not None else None,
            "batch_size_per_gpu": batch_size,
            "gradient_accumulation": accum,
            "effective_batch_size": batch_size * accum,
            "train_workers": train_workers,
            "eval_workers": eval_workers,
            "deterministic": deterministic,
            "scheduler": "dependency_aware_lpt_static_lanes",
            "resume_policy": (
                "same-attempt full-state resume from newest validated periodic checkpoint; "
                "fresh attempt only when no recovery checkpoint exists"
            ),
            "planned_optimizer_iterations": sum(
                protocol_iterations[job.protocol.id] for job in jobs
            ),
            "avoided_duplicate_city_iterations": sum(
                40_000 for job in jobs if job.protocol.id == "cityscapes_to_railsem19"
            ),
        },
        "reuse_policy": {
            "roots": [str(path.expanduser().resolve()) for path in reuse_roots],
            "allowed_git_shas": sorted({expected_sha, *allowed_reuse_shas}),
            "selection": (
                "exact compatible config and seed; standalone common evaluation preferred; "
                "expected campaign SHA preferred; conflicting top-ranked candidates rejected"
            ),
        },
        "publisher": (
            {
                "worktree": str(publisher_root.expanduser().resolve()),
                "remote": publish_remote,
                "branch": publish_branch,
                "interval_seconds": publish_interval,
                "tmux_session": f"{tmux_prefix}-publisher",
            }
            if publisher_root is not None
            else None
        ),
        "progress": {
            "tmux_session": f"{tmux_prefix}-progress",
            # Match segmentary-progress's own default. The dashboard only polls
            # files training already writes, and its AGE column has to tick every
            # second to distinguish a quiet lane from a stalled one.
            "refresh_seconds": 1,
        },
        "preflight": {
            "tmux_session": f"{tmux_prefix}-reused-performance",
            "purpose": "benchmark reused RailSem19 owners before any new training",
        },
        "lanes": lane_records,
        "jobs": all_jobs,
        "logical_cell_count": len(logical_jobs),
        "physical_job_count": len(jobs),
    }


def _new_job_status(spec: dict[str, Any], accepted: dict[str, Any] | None = None) -> dict[str, Any]:
    status = {
        **spec,
        "status": "pending",
        "attempt": 0,
        "attempts": [],
        "started_at": None,
        "finished_at": None,
        "run_dir": None,
        "checkpoint": None,
        "training_results": None,
        "common_results": None,
        "performance": None,
        "log": None,
        "failure": None,
    }
    if accepted is not None:
        status.update(
            {
                "status": "reused",
                "attempt": 0,
                "attempts": [
                    {
                        "number": 0,
                        "kind": "reused",
                        "status": "reused",
                        "started_at": accepted["finished_at"],
                        "finished_at": accepted["finished_at"],
                        "failure": None,
                        "paths": {
                            "common_results": accepted["bundle_result"],
                            "stage_results": (
                                {spec["final_stage"]: accepted["bundle_training_result"]}
                                if accepted.get("bundle_training_result")
                                else {}
                            ),
                            "checkpoint": accepted["checkpoint"],
                            "source_results": accepted["source_result"],
                            "source_training_results": accepted.get("training_source_result"),
                            "config": accepted["bundle_config"],
                            "performance": accepted["bundle_performance"],
                            "milestone_results": {
                                step: milestone["bundle_result"]
                                for step, milestone in accepted.get("milestones", {}).items()
                            },
                            "milestone_checkpoints": {
                                step: milestone["checkpoint"]
                                for step, milestone in accepted.get("milestones", {}).items()
                            },
                        },
                        "sha256": {
                            "common_results": accepted["result_sha256"],
                            "stage_results": (
                                {spec["final_stage"]: accepted["training_result_sha256"]}
                                if accepted.get("training_result_sha256")
                                else {}
                            ),
                            "checkpoint": accepted["checkpoint_sha256"],
                            "milestone_results": {
                                step: milestone["result_sha256"]
                                for step, milestone in accepted.get("milestones", {}).items()
                            },
                            "milestone_checkpoints": {
                                step: milestone["checkpoint_sha256"]
                                for step, milestone in accepted.get("milestones", {}).items()
                            },
                        },
                        "record_kind": accepted["record_kind"],
                        "source_git_sha": accepted["source_git_sha"],
                        "compatibility_sha256": accepted["compatibility_sha256"],
                        "checkpoint_available": accepted["checkpoint_available"],
                        "checkpoint_step": accepted["checkpoint_step"],
                        "iteration_plan": accepted["iteration_plan"],
                        "caveat": accepted["caveat"],
                    }
                ],
                "finished_at": accepted["finished_at"],
                "run_dir": (
                    str(Path(accepted["checkpoint"]).parent.parent)
                    if accepted["checkpoint"] is not None
                    else None
                ),
                "checkpoint": accepted["checkpoint"],
                "training_results": (
                    accepted["bundle_result"] if accepted["record_kind"] == "training" else None
                ),
                "common_results": accepted["bundle_result"],
                "performance": accepted["bundle_performance"],
                "log": None,
                "reused_from": accepted["source_result"],
            }
        )
    return status


def _lane_status(record: dict[str, Any], lane_spec: dict[str, Any]) -> dict[str, Any]:
    by_id = {job["id"]: job for job in record["jobs"]}
    accepted = {item["job_id"]: item for item in (record.get("reuse") or {}).get("accepted", [])}
    job_ids = sorted(
        lane_spec["job_ids"],
        key=lambda job_id: (
            0 if job_id in accepted and by_id[job_id].get("performance_owner") else 1,
            lane_spec["job_ids"].index(job_id),
        ),
    )
    return {
        "schema_version": STATUS_SCHEMA_VERSION,
        "campaign": record["campaign"],
        "campaign_name": record["name"],
        "expected_git_sha": record["source"]["expected_git_sha"],
        "lane": lane_spec["id"],
        "gpu_visibility": str(lane_spec["gpu"]),
        "master_addr": "127.0.0.1",
        "master_port": lane_spec["master_port"],
        "tmux_session": lane_spec["tmux_session"],
        "effective_batch_size": record["execution"]["effective_batch_size"],
        "status": "pending",
        "started_at": None,
        "updated_at": _now(),
        "finished_at": None,
        "failure": None,
        "jobs": [_new_job_status(by_id[job_id], accepted.get(job_id)) for job_id in job_ids],
    }


def _status_path(campaign: Path, lane: str) -> Path:
    return campaign / f"lane_{lane}_status.json"


def _persist_status(path: Path, status: dict[str, Any]) -> None:
    status["updated_at"] = _now()
    atomic_write_json(path, status)


def _load_json_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise CampaignError(f"missing campaign file: {path}") from exc
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CampaignError(f"cannot read valid JSON object {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise CampaignError(f"{path} is not a JSON object")
    return value


def _same_campaign(existing: dict[str, Any], requested: dict[str, Any]) -> bool:
    # created_at is observational; all other fields define the immutable run.
    left = copy.deepcopy(existing)
    right = copy.deepcopy(requested)
    left.pop("created_at", None)
    right.pop("created_at", None)
    return left == right


def _immutable_request(record: dict[str, Any]) -> dict[str, Any]:
    """Return only user-selected fields that must not drift after preparation."""
    return {
        "name": record.get("name"),
        "campaign": record.get("campaign"),
        "source": record.get("source"),
        "datasets": record.get("datasets"),
        "execution": record.get("execution"),
        "reuse_policy": record.get("reuse_policy"),
        "publisher": record.get("publisher"),
        "progress": record.get("progress"),
        "preflight": record.get("preflight"),
        "lanes": record.get("lanes"),
        "jobs": record.get("jobs"),
        "logical_cell_count": record.get("logical_cell_count"),
        "physical_job_count": record.get("physical_job_count"),
    }


def validate_prepared_request(existing: dict[str, Any], requested: dict[str, Any]) -> None:
    if _immutable_request(existing) != _immutable_request(requested):
        raise CampaignError(
            "launch options differ from the prepared immutable campaign; use the exact "
            "same datasets, GPUs, seeds, tmux/publisher settings, and reuse policy"
        )


def _materialize_reused_results(record: dict[str, Any], campaign: Path) -> None:
    """Copy small accepted result records into the campaign evidence bundle.

    Checkpoints remain at their validated source locations and are represented by
    path plus SHA-256. Copying multi-gigabyte checkpoints just to prove reuse
    would waste storage without adding provenance.
    """
    for accepted in (record.get("reuse") or {}).get("accepted", []):
        source = Path(accepted["source_result"])
        checkpoint = Path(accepted["checkpoint"]) if accepted["checkpoint"] is not None else None
        if _sha256(source) != accepted["result_sha256"]:
            raise CampaignError(f"accepted result changed after preflight: {source}")
        if checkpoint is not None and _sha256(checkpoint) != accepted["checkpoint_sha256"]:
            raise CampaignError(f"accepted checkpoint changed after preflight: {checkpoint}")
        destination = Path(accepted["bundle_result"])
        atomic_write_text(destination, source.read_text(encoding="utf-8"))
        training_source_raw = accepted.get("training_source_result")
        training_destination_raw = accepted.get("bundle_training_result")
        if isinstance(training_source_raw, str) and isinstance(training_destination_raw, str):
            training_source = Path(training_source_raw)
            if _sha256(training_source) != accepted.get("training_result_sha256"):
                raise CampaignError(
                    f"accepted training result changed after preflight: {training_source}"
                )
            atomic_write_text(
                Path(training_destination_raw), training_source.read_text(encoding="utf-8")
            )
        for milestone in accepted.get("milestones", {}).values():
            milestone_source = Path(milestone["source_result"])
            milestone_checkpoint = Path(milestone["checkpoint"])
            if _sha256(milestone_source) != milestone["result_sha256"]:
                raise CampaignError(
                    f"accepted milestone result changed after preflight: {milestone_source}"
                )
            if _sha256(milestone_checkpoint) != milestone["checkpoint_sha256"]:
                raise CampaignError(
                    f"accepted milestone checkpoint changed after preflight: {milestone_checkpoint}"
                )
            milestone_destination = Path(milestone["bundle_result"])
            atomic_write_text(milestone_destination, milestone_source.read_text(encoding="utf-8"))
        job = _job_by_id(record, accepted["job_id"])
        _, resolved = _resolved_config(record, job, destination.parent)
        config_path = destination.parent / "resolved-config.yaml"
        performance_path = destination.parent / "performance.json"
        atomic_write_text(config_path, yaml.safe_dump(resolved, sort_keys=False))
        accepted["bundle_config"] = str(config_path)
        accepted["bundle_performance"] = str(performance_path)
        atomic_write_json(
            destination.parent / "provenance.json",
            {
                "job_id": accepted["job_id"],
                "source_result": str(source),
                "source_result_sha256": accepted["result_sha256"],
                "training_source_result": training_source_raw,
                "training_result_sha256": accepted.get("training_result_sha256"),
                "checkpoint": str(checkpoint) if checkpoint is not None else None,
                "checkpoint_sha256": accepted["checkpoint_sha256"],
                "checkpoint_available": accepted["checkpoint_available"],
                "checkpoint_step": accepted["checkpoint_step"],
                "iteration_plan": accepted["iteration_plan"],
                "caveat": accepted["caveat"],
                "source_git_sha": accepted["source_git_sha"],
                "record_kind": accepted["record_kind"],
                "compatibility_sha256": accepted["compatibility_sha256"],
                "milestones": accepted.get("milestones", {}),
                "accepted_at": accepted["accepted_at"],
            },
        )


def _tmux_exists(session: str) -> bool:
    result = subprocess.run(
        ["tmux", "has-session", "-t", session],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return result.returncode == 0


def _worker_command(campaign: Path, lane: str) -> list[str]:
    return [
        str(Path(sys.executable).resolve()),
        str(Path(__file__).resolve()),
        "worker",
        "--campaign",
        str(campaign),
        "--lane",
        lane,
    ]


def _tmux_shell_command(
    campaign: Path,
    lane_spec: dict[str, Any],
    execution: dict[str, Any],
) -> str:
    python = execution["python"]
    command = [
        "env",
        "CUDA_DEVICE_ORDER=PCI_BUS_ID",
        f"CUDA_VISIBLE_DEVICES={lane_spec['gpu']}",
        "MASTER_ADDR=127.0.0.1",
        f"MASTER_PORT={lane_spec['master_port']}",
        f"PYTHONPATH={SRC_ROOT}",
    ]
    if execution.get("hf_home"):
        command.append(f"HF_HOME={execution['hf_home']}")
    command.extend(
        [
            python,
            str(Path(__file__).resolve()),
            "worker",
            "--campaign",
            str(campaign),
            "--lane",
            lane_spec["id"],
        ]
    )
    lane_log = campaign / f"lane_{lane_spec['id']}.console.log"
    return _tee_shell(command, lane_log)


def _tee_shell(command: Sequence[str], log_path: Path) -> str:
    """Show a persistent tmux pane while retaining the identical console log."""
    return f"set -o pipefail; {shlex.join(command)} 2>&1 | tee -a {shlex.quote(str(log_path))}"


def launch_campaign(
    record: dict[str, Any],
    *,
    dry_run: bool,
    prepare_only: bool = False,
    skip_reused_preflight: bool = False,
) -> int:
    campaign = Path(record["campaign"])
    campaign_file = campaign / "campaign.json"
    if dry_run:
        print(
            f"dry-run: {record.get('physical_job_count', len(record['jobs']))} jobs, "
            f"{record.get('logical_cell_count', len(record['jobs']))} report cells, "
            f"{len(record['lanes'])} tmux lanes, "
            "no files or sessions will be created"
        )
    else:
        if campaign_file.exists():
            existing = _load_json_object(campaign_file)
            if not _same_campaign(existing, record):
                raise CampaignError(
                    f"{campaign_file} describes a different immutable campaign; use a new path"
                )
            record = existing
        else:
            if campaign.exists() and any(campaign.iterdir()):
                raise CampaignError(
                    f"campaign path exists and is not empty but has no campaign.json: {campaign}"
                )
            campaign.mkdir(parents=True, exist_ok=True)
            _materialize_reused_results(record, campaign)
            atomic_write_json(campaign_file, record)
            for lane_spec in record["lanes"]:
                _persist_status(
                    _status_path(campaign, lane_spec["id"]), _lane_status(record, lane_spec)
                )

    if prepare_only and not dry_run:
        accepted_ids = {item["job_id"] for item in (record.get("reuse") or {}).get("accepted", [])}
        reused_owners = [
            job["id"]
            for job in record["jobs"]
            if job.get("performance_owner") and job["id"] in accepted_ids
        ]
        print(
            f"prepared immutable campaign without starting tmux: {campaign_file}\n"
            f"accepted={record.get('reuse', {}).get('accepted_cells', 0)} "
            f"queued={record.get('reuse', {}).get('queued_cells', record['physical_job_count'])}\n"
            f"reused performance preflight: {', '.join(reused_owners) or 'none'}"
        )
        return 0

    if not dry_run and not skip_reused_preflight and _pending_reused_performance(record):
        preflight = record["preflight"]
        session = preflight["tmux_session"]
        command = [
            record["execution"]["python"],
            str(Path(__file__).resolve()),
            "bootstrap",
            "--campaign",
            str(campaign),
        ]
        shell_command = _tee_shell(
            ["env", f"PYTHONPATH={SRC_ROOT}", *command],
            campaign / "reused-performance.console.log",
        )
        print(f"{session}: {shell_command}")
        if _tmux_exists(session):
            print(f"{session}: already alive; workers remain gated behind it")
            return 0
        invocation = [
            "tmux",
            "new-session",
            "-d",
            "-s",
            session,
            "-c",
            str(REPO_ROOT),
            shell_command,
        ]
        completed = subprocess.run(invocation, capture_output=True, text=True, check=False)
        if completed.returncode != 0 or not _tmux_exists(session):
            detail = (completed.stderr or completed.stdout).strip()
            raise CampaignError(f"could not start reused-performance tmux {session}: {detail}")
        print(
            f"started {session}; it will start all worker/publisher/progress sessions only "
            "after reused performance validates"
        )
        return 0

    started = 0
    for lane_spec in record["lanes"]:
        session = lane_spec["tmux_session"]
        shell_command = _tmux_shell_command(campaign, lane_spec, record["execution"])
        invocation = [
            "tmux",
            "new-session",
            "-d",
            "-s",
            session,
            "-c",
            str(REPO_ROOT),
            shell_command,
        ]
        print(f"{session}: {shell_command}")
        if dry_run:
            continue
        if _tmux_exists(session):
            print(f"{session}: already alive; left unchanged")
            continue
        completed = subprocess.run(invocation, capture_output=True, text=True, check=False)
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout).strip()
            raise CampaignError(f"could not start tmux session {session}: {detail}")
        if not _tmux_exists(session):
            raise CampaignError(f"tmux reported success but session is not alive: {session}")
        started += 1
    publisher = record.get("publisher")
    if publisher is not None:
        session = publisher["tmux_session"]
        command = [
            record["execution"]["python"],
            str(Path(__file__).resolve()),
            "publisher",
            "--campaign",
            str(campaign),
        ]
        shell_command = _tee_shell(
            ["env", f"PYTHONPATH={SRC_ROOT}", *command],
            campaign / "publisher.console.log",
        )
        print(f"{session}: {shell_command}")
        if not dry_run:
            if _tmux_exists(session):
                print(f"{session}: already alive; left unchanged")
            else:
                invocation = [
                    "tmux",
                    "new-session",
                    "-d",
                    "-s",
                    session,
                    "-c",
                    publisher["worktree"],
                    shell_command,
                ]
                completed = subprocess.run(invocation, capture_output=True, text=True, check=False)
                if completed.returncode != 0 or not _tmux_exists(session):
                    detail = (completed.stderr or completed.stdout).strip()
                    raise CampaignError(
                        f"could not start publisher tmux session {session}: {detail}"
                    )
                started += 1
    progress = record.get("progress")
    if isinstance(progress, dict):
        session = progress["tmux_session"]
        command = [
            record["execution"]["python"],
            "-m",
            "segmentary.progress",
            str(campaign),
            "--refresh",
            str(progress["refresh_seconds"]),
            "--timezone",
            "America/Los_Angeles",
        ]
        shell_command = f"exec env PYTHONPATH={shlex.quote(str(SRC_ROOT))} {shlex.join(command)}"
        print(f"{session}: {shell_command}")
        if not dry_run and not _tmux_exists(session):
            invocation = [
                "tmux",
                "new-session",
                "-d",
                "-s",
                session,
                "-c",
                str(REPO_ROOT),
                shell_command,
            ]
            completed = subprocess.run(invocation, capture_output=True, text=True, check=False)
            if completed.returncode != 0 or not _tmux_exists(session):
                detail = (completed.stderr or completed.stdout).strip()
                print(
                    f"warning: progress tmux {session} could not start: {detail}",
                    file=sys.stderr,
                )
            else:
                started += 1
    if not dry_run:
        print(f"started {started} named tmux session(s); campaign: {campaign_file}")
    return 0


def _write_console(chunk: bytes) -> None:
    stream = getattr(sys.stdout, "buffer", None)
    if stream is None:
        sys.stdout.write(chunk.decode("utf-8", errors="replace"))
        sys.stdout.flush()
    else:
        stream.write(chunk)
        stream.flush()


def run_logged(command: Sequence[str], env: dict[str, str], log_path: Path) -> int:
    shown_env = " ".join(f"{key}={shlex.quote(env[key])}" for key in ENV_KEYS if key in env)
    invocation = f"{shown_env} {shlex.join(command)}"
    print(f"$ {invocation}", flush=True)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("ab") as log:
        log.write(f"\n$ {invocation}\n".encode())
        log.flush()
        try:
            process = subprocess.Popen(
                list(command),
                cwd=REPO_ROOT,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
            )
        except OSError as exc:
            message = f"launcher could not start command: {exc}\n".encode()
            log.write(message)
            log.flush()
            _write_console(message)
            return 127
        assert process.stdout is not None
        while chunk := process.stdout.read1(8192):
            log.write(chunk)
            log.flush()
            _write_console(chunk)
        return process.wait()


def _job_by_id(record: dict[str, Any], job_id: str) -> dict[str, Any]:
    matches = [job for job in record["jobs"] if job.get("id") == job_id]
    if len(matches) != 1:
        raise CampaignError(f"campaign has {len(matches)} records for job id {job_id!r}")
    return matches[0]


def _next_attempt(job: dict[str, Any], campaign: Path) -> tuple[int, Path]:
    index = (
        max(
            [
                int(item.get("number", 0))
                for item in job.get("attempts", [])
                if isinstance(item, dict)
            ],
            default=0,
        )
        + 1
    )
    root = campaign / "jobs" / job["id"]
    while (root / f"attempt-{index:03d}").exists():
        index += 1
    return index, root / f"attempt-{index:03d}"


def _resolved_config(
    record: dict[str, Any],
    job: dict[str, Any],
    attempt: Path,
    dependency_checkpoint: Path | None = None,
) -> tuple[ExperimentConfig, dict[str, Any]]:
    merged: dict[str, Any] = {}
    campaign_overrides: dict[str, Any] = {}
    layers = [
        Path("configs/base.yaml"),
        Path(job["model_config"]),
        Path(job["curriculum_config"]),
    ]
    if job.get("campaign_config"):
        campaign_overrides = load_yaml(REPO_ROOT / Path(job["campaign_config"]))
    for relative in layers:
        merged = deep_merge(merged, load_yaml(REPO_ROOT / relative))
    merged = deep_merge(merged, campaign_overrides)
    merged["name"] = job["experiment_name"]
    merged["output_root"] = str(attempt / "train")
    merged["train"] = {
        **merged.get("train", {}),
        "seed": job["seed"],
        "devices": 1,
        "batch_size": record["execution"]["batch_size_per_gpu"],
        "accum": record["execution"]["gradient_accumulation"],
        "num_workers": record["execution"]["train_workers"],
    }
    # A reviewed model-specific campaign overlay may trade batch size against
    # accumulation for throughput, but it must retain the campaign's effective
    # batch so optimization semantics remain comparable.
    override_train = campaign_overrides.get("train", {})
    if isinstance(override_train, dict):
        for field in ("batch_size", "accum"):
            if field in override_train:
                merged["train"][field] = override_train[field]
    merged["eval"] = {
        **merged.get("eval", {}),
        "num_workers": record["execution"]["eval_workers"],
    }
    stages = merged.get("stages")
    if not isinstance(stages, list) or not stages:
        raise CampaignError(f"{job['id']} resolved no curriculum stages")
    if job.get("depends_on"):
        if len(stages) != 1 or stages[0].get("name") != "railsem19":
            raise CampaignError(f"{job['id']} dependency transfer must contain only RailSem19")
        source = dependency_checkpoint or Path("/dependency") / job["depends_on"] / "last.ckpt"
        stages[0]["init_from"] = str(source)
        stages[0]["reset_head"] = True
    for stage in stages:
        if not isinstance(stage, dict) or not isinstance(stage.get("data"), list):
            raise CampaignError(f"{job['id']} has a malformed stage data list")
        for data in stage["data"]:
            if not isinstance(data, dict) or data.get("name") not in record["datasets"]:
                raise CampaignError(
                    f"{job['id']} uses unsupported dataset {data.get('name') if isinstance(data, dict) else data!r}"
                )
            data["root"] = record["datasets"][data["name"]]
            if data["name"] == "railsem19" and data.get("split_file"):
                data["split_file"] = str((REPO_ROOT / data["split_file"]).resolve())
    cfg = from_dict(ExperimentConfig, merged)
    effective_batch = cfg.train.batch_size * cfg.train.accum
    if effective_batch != record["execution"]["effective_batch_size"]:
        raise CampaignError(
            f"{job['id']} model-specific runtime override changed effective batch "
            f"to {effective_batch}; expected {record['execution']['effective_batch_size']}"
        )
    if cfg.space != job["evaluation_space"]:
        raise CampaignError(f"{job['id']} resolved unexpected space {cfg.space!r}")
    if cfg.stages[-1].name != job["final_stage"]:
        raise CampaignError(f"{job['id']} resolved unexpected final stage {cfg.stages[-1].name!r}")
    return cfg, to_dict(cfg)


def _canonical_model_config(raw: object) -> object:
    """Collapse reviewed compatibility aliases to their explicit model contract."""
    if not isinstance(raw, dict):
        return raw
    model = copy.deepcopy(raw)
    if model.get("arch") == "deeplabv3plus_r101":
        model["arch"] = "smp"
        model["smp_arch"] = "DeepLabV3Plus"
        model["encoder_name"] = "resnet101"
        model["encoder_weights"] = "imagenet"
    return model


def _normalised_compatibility_config(
    config: dict[str, Any], *, runtime_device_count: int | None = None
) -> dict[str, Any]:
    """Return the training/evaluation semantics used to decide safe reuse.

    Paths, process topology, seed, and worker counts are execution details. The
    effective batch size is retained because it changes optimisation. Everything
    else—including model, losses, schedule, augmentations, label space, stage
    ordering, and inference protocol—must match exactly.
    """
    value = copy.deepcopy(config)
    value.pop("evaluation", None)
    value.pop("name", None)
    value.pop("output_root", None)
    value["model"] = _canonical_model_config(value.get("model"))
    model = value.get("model")
    if isinstance(model, dict):
        for field, default in {
            "backbone_path": None,
            "batch_norm_momentum": None,
            "classifier_path": None,
            "encoder_name": None,
            "encoder_weights": None,
            "head_paths": [],
            "inactive_parameter_paths": [],
            "local_files_only": False,
            "native": None,
            "revision": None,
            "smp_arch": None,
            "subfolder": None,
            "trust_remote_code": False,
        }.items():
            if model.get(field) == default:
                model.pop(field, None)
    loss = value.get("loss")
    if isinstance(loss, dict):
        for field, default in {
            "activation": "auto",
            "class_weights": None,
            "query": None,
            "task": "multiclass",
            "terms": [],
        }.items():
            if loss.get(field) == default:
                loss.pop(field, None)
    train = value.get("train")
    if not isinstance(train, dict):
        raise CampaignError("compatible config has no train mapping")
    devices = train.get("devices", 1)
    if isinstance(devices, int) and not isinstance(devices, bool):
        device_count = devices
    elif isinstance(devices, list) and all(
        isinstance(item, int) and not isinstance(item, bool) for item in devices
    ):
        device_count = len(devices)
    elif devices == "auto" and runtime_device_count is not None and runtime_device_count >= 1:
        device_count = runtime_device_count
    else:
        raise CampaignError(f"cannot derive effective batch from train.devices={devices!r}")
    batch = train.get("batch_size")
    accum = train.get("accum")
    if any(
        isinstance(item, bool) or not isinstance(item, int) or item < 1
        for item in (device_count, batch, accum)
    ):
        raise CampaignError(
            f"cannot derive effective batch from devices={devices!r}, batch_size={batch!r}, accum={accum!r}"
        )
    for field in ("seed", "devices", "batch_size", "accum", "num_workers"):
        train.pop(field, None)
    train["effective_batch_size"] = device_count * batch * accum
    evaluation = value.get("eval")
    if isinstance(evaluation, dict):
        evaluation.pop("num_workers", None)
        if loss is None or loss.get("task", "multiclass") != "binary":
            evaluation.pop("threshold", None)
    stages = value.get("stages")
    if not isinstance(stages, list):
        raise CampaignError("compatible config has no stages list")
    for stage in stages:
        if not isinstance(stage, dict) or not isinstance(stage.get("data"), list):
            raise CampaignError("compatible config contains malformed stage data")
        if stage.get("head_group_lr_scale") is None:
            # An omitted head-group scale inherits lr_scale. Removing its serialized
            # null preserves compatibility with results written before the
            # independent group-scale field existed.
            stage.pop("head_group_lr_scale", None)
        for data in stage["data"]:
            if not isinstance(data, dict) or not isinstance(data.get("name"), str):
                raise CampaignError("compatible config contains malformed dataset config")
            data["root"] = f"<dataset:{data['name']}>"
            if data.get("split_file"):
                data["split_file"] = Path(str(data["split_file"])).name
            for field, default in {
                "loader": None,
                "loader_options": {},
                "mapping": None,
            }.items():
                if data.get(field) == default:
                    data.pop(field, None)
        init_from = stage.get("init_from")
        if isinstance(init_from, str) and init_from not in {"pretrained", "previous"}:
            stage["init_from"] = "<dependency-checkpoint>"
    return value


def compatibility_sha256(config: dict[str, Any], *, runtime_device_count: int | None = None) -> str:
    encoded = json.dumps(
        _normalised_compatibility_config(config, runtime_device_count=runtime_device_count),
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _checkpoint_index(roots: Sequence[Path]) -> dict[Path, Path]:
    """Index explicit result->checkpoint links from lane status records."""
    index: dict[Path, Path] = {}
    for root in roots:
        for path in root.rglob("lane_*_status.json"):
            try:
                status = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError):
                continue
            if not isinstance(status, dict) or not isinstance(status.get("jobs"), list):
                continue
            for job in status["jobs"]:
                if not isinstance(job, dict) or not job.get("checkpoint"):
                    continue
                checkpoint = Path(str(job["checkpoint"])).expanduser()
                for key in ("common_results", "training_results"):
                    if job.get(key):
                        index[Path(str(job[key])).expanduser().resolve()] = checkpoint.resolve()
    return index


def _checkpoint_for_result(
    path: Path, result: dict[str, Any], indexed: dict[Path, Path]
) -> Path | None:
    resolved = path.resolve()
    if resolved in indexed:
        return indexed[resolved]
    if result.get("stage") and not str(result["stage"]).startswith("eval:"):
        sibling = path.parent / "last.ckpt"
        if sibling.is_file():
            return sibling.resolve()
    notes = result.get("notes")
    if isinstance(notes, str):
        match = re.search(r"(?:^|\s)checkpoint=(.+?)(?:\s+ema=|$)", notes)
        if match:
            candidate = Path(match.group(1)).expanduser()
            if not candidate.is_absolute():
                candidate = (REPO_ROOT / candidate).resolve()
            legacy_project = "/projects/" + "rail" + "yard/"
            if not candidate.is_file() and legacy_project in str(candidate):
                candidate = Path(str(candidate).replace(legacy_project, "/projects/segmentary/"))
            if candidate.is_file():
                return candidate
    return None


def _checkpoint_global_step(path: Path) -> int | None:
    """Read Lightning's scalar global_step without unpickling executable objects."""
    try:
        with zipfile.ZipFile(path) as archive:
            payload_name = next(name for name in archive.namelist() if name.endswith("/data.pkl"))
            payload = archive.read(payload_name)
    except (OSError, KeyError, StopIteration, zipfile.BadZipFile):
        return None
    found_key = False
    try:
        for opcode, argument, _ in pickletools.genops(payload):
            if argument == "global_step":
                found_key = True
                continue
            if (
                found_key
                and opcode.name in {"INT", "BININT", "BININT1", "BININT2", "LONG"}
                and isinstance(argument, int)
                and not isinstance(argument, bool)
            ):
                return argument
    except ValueError:
        return None
    return None


def _expected_final_step(config: dict[str, Any], final_stage: str) -> int:
    stages = config.get("stages")
    train = config.get("train")
    if not isinstance(stages, list) or not isinstance(train, dict):
        raise CampaignError("result config has no stages/train mapping")
    matches = [
        stage for stage in stages if isinstance(stage, dict) and stage.get("name") == final_stage
    ]
    if len(matches) != 1:
        raise CampaignError(f"result config has {len(matches)} stages named {final_stage!r}")
    value = matches[0].get("iters")
    if value is None:
        value = train.get("iters")
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise CampaignError(f"result config final iteration budget is invalid: {value!r}")
    return value


def _iteration_plan(config: dict[str, Any]) -> dict[str, Any]:
    stages = config.get("stages")
    train = config.get("train")
    if not isinstance(stages, list) or not isinstance(train, dict):
        raise CampaignError("result config has no stages/train mapping for iteration plan")
    default = train.get("iters")
    rows = []
    total = 0
    for index, stage in enumerate(stages):
        if not isinstance(stage, dict) or not isinstance(stage.get("name"), str):
            raise CampaignError(f"result config stage {index} is malformed")
        target = stage.get("iters")
        if target is None:
            target = default
        if isinstance(target, bool) or not isinstance(target, int) or target < 1:
            raise CampaignError(
                f"stage {stage.get('name')!r} has invalid target iterations {target!r}"
            )
        rows.append(
            {
                "stage": stage["name"],
                "target_iterations": target,
                "learning_rate_scale": stage.get("lr_scale", 1.0),
                "head_group_learning_rate_scale": (
                    stage.get("lr_scale", 1.0)
                    if stage.get("head_group_lr_scale") is None
                    else stage["head_group_lr_scale"]
                ),
            }
        )
        total += target
    return {"stages": rows, "total_target_iterations": total}


def _result_kind(stage: object, job: dict[str, Any]) -> str | None:
    if stage == f"eval:{job['evaluation_dataset']}:{job['evaluation_split']}":
        return "evaluation"
    if stage == job["final_stage"]:
        return "training"
    return None


def scan_reusable_cells(record: dict[str, Any]) -> dict[str, Any]:
    """Find exact compatible existing cells and produce a machine-readable audit."""
    roots = [Path(path) for path in record["reuse_policy"]["roots"]]
    for root in roots:
        if not root.is_dir():
            raise CampaignError(f"reuse root is not a directory: {root}")
    allowed_shas = set(record["reuse_policy"]["allowed_git_shas"])
    expected_sha = record["source"]["expected_git_sha"]

    prototypes: dict[tuple[str, int], tuple[dict[str, Any], dict[str, Any]]] = {}
    for job in record["jobs"]:
        if job.get("alias_of"):
            continue
        _, config = _resolved_config(record, job, Path(record["campaign"]) / ".prototype")
        signature = compatibility_sha256(config)
        key = (signature, job["seed"])
        if key in prototypes:
            raise CampaignError(
                f"jobs {prototypes[key][0]['id']} and {job['id']} have the same compatibility signature"
            )
        prototypes[key] = (job, config)

    checkpoint_index = _checkpoint_index(roots)
    result_paths = sorted(
        {path.resolve() for root in roots for path in root.rglob("results.json") if path.is_file()}
    )
    candidates: dict[str, list[dict[str, Any]]] = defaultdict(list)
    counts: dict[str, int] = defaultdict(int)
    rejected: list[dict[str, str]] = []
    for path in result_paths:
        try:
            result = load_results(path).to_dict()
        except (OSError, TypeError, ValueError) as exc:
            counts["invalid_result"] += 1
            rejected.append({"path": str(path), "reason": f"invalid result: {exc}"})
            continue
        if result.get("git_dirty") is not False:
            counts["dirty_source"] += 1
            continue
        if result.get("git_sha") not in allowed_shas:
            counts["unapproved_git_sha"] += 1
            continue
        config = result.get("config")
        if not isinstance(config, dict):
            counts["invalid_config"] += 1
            continue
        if result.get("config_hash") != config_hash(config):
            counts["invalid_config_hash"] += 1
            rejected.append({"path": str(path), "reason": "config_hash mismatch"})
            continue
        try:
            env = result.get("env")
            gpu_count = env.get("gpu_count") if isinstance(env, dict) else None
            signature = compatibility_sha256(
                config,
                runtime_device_count=(
                    gpu_count
                    if isinstance(gpu_count, int) and not isinstance(gpu_count, bool)
                    else None
                ),
            )
        except CampaignError:
            counts["incompatible_config"] += 1
            continue
        seed = result.get("seed")
        prototype = (
            prototypes.get((signature, seed))
            if isinstance(seed, int) and not isinstance(seed, bool)
            else None
        )
        if prototype is None:
            counts["not_campaign_cell"] += 1
            continue
        job, expected_config = prototype
        kind = _result_kind(result.get("stage"), job)
        if kind is None:
            counts["wrong_result_stage"] += 1
            continue
        checkpoint = _checkpoint_for_result(path, result, checkpoint_index)
        checkpoint_available = bool(
            checkpoint is not None and checkpoint.is_file() and checkpoint.stat().st_size > 0
        )
        checkpoint_caveat: str | None = None
        if checkpoint_available:
            expected_step = _expected_final_step(config, job["final_stage"])
            actual_step = _checkpoint_global_step(checkpoint)
            if actual_step != expected_step:
                checkpoint_available = False
                checkpoint_caveat = (
                    f"The nearby checkpoint records global_step={actual_step!r}, but the valid "
                    f"result was reported after {expected_step} iterations; the exact evaluated "
                    "checkpoint is unavailable and the cell is not retrained."
                )
        if not checkpoint_available:
            checkpoint = None
            counts["reporting_only_candidates"] += 1
        try:
            validate_result(
                path,
                expected_sha=result["git_sha"],
                job=job,
                expected_config=expected_config,
                evaluation=kind == "evaluation",
                require_campaign_name=False,
            )
        except CampaignError as exc:
            counts["metric_or_schema_failure"] += 1
            rejected.append({"path": str(path), "reason": str(exc)})
            continue
        milestones: dict[str, dict[str, Any]] = {}
        if job.get("evaluation_milestones"):
            if kind != "evaluation" or checkpoint is None:
                counts["missing_milestone_evidence"] += 1
                continue
            evaluation_root = path.parent.parent
            milestone_failed = False
            for step in job["evaluation_milestones"]:
                step_key = str(step)
                milestone_checkpoint = checkpoint.parent / f"step-{step:08d}.ckpt"
                milestone_result = (
                    evaluation_root / f"{job['evaluation_dataset']}-step{step}" / "results.json"
                )
                try:
                    if (
                        not milestone_checkpoint.is_file()
                        or _checkpoint_global_step(milestone_checkpoint) != step
                    ):
                        raise CampaignError(
                            f"missing exact step-{step} checkpoint {milestone_checkpoint}"
                        )
                    milestone_record = validate_result(
                        milestone_result,
                        expected_sha=result["git_sha"],
                        job=job,
                        expected_config=expected_config,
                        evaluation=True,
                        require_campaign_name=False,
                    )
                    if str(milestone_checkpoint) not in str(milestone_record.get("notes", "")):
                        raise CampaignError(
                            f"{milestone_result}: notes do not identify {milestone_checkpoint}"
                        )
                except CampaignError as exc:
                    counts["missing_milestone_evidence"] += 1
                    rejected.append({"path": str(path), "reason": str(exc)})
                    milestone_failed = True
                    break
                milestones[step_key] = {
                    "source_result": str(milestone_result),
                    "result_sha256": _sha256(milestone_result),
                    "checkpoint": str(milestone_checkpoint),
                    "checkpoint_sha256": _sha256(milestone_checkpoint),
                    "checkpoint_step": step,
                }
            if milestone_failed:
                continue
        candidates[job["id"]].append(
            {
                "job_id": job["id"],
                "source_result": str(path),
                "checkpoint": str(checkpoint) if checkpoint is not None else None,
                "checkpoint_available": checkpoint_available,
                "caveat": (
                    None
                    if checkpoint_available
                    else checkpoint_caveat
                    or "Validated result is reporting-complete, but its exact evaluated checkpoint is unavailable; the cell is not retrained."
                ),
                "record_kind": kind,
                "source_git_sha": result["git_sha"],
                "finished_at": result.get("finished_at") or _now(),
                "miou": result["metrics"]["miou"],
                "compatibility_sha256": signature,
                "result_sha256": _sha256(path),
                "checkpoint_sha256": _sha256(checkpoint) if checkpoint is not None else None,
                "checkpoint_step": (
                    _checkpoint_global_step(checkpoint) if checkpoint is not None else None
                ),
                "iteration_plan": _iteration_plan(config),
                "milestones": milestones,
            }
        )
        counts["compatible_candidates"] += 1

    accepted: list[dict[str, Any]] = []
    ambiguous: list[dict[str, Any]] = []
    for job_id, items in sorted(candidates.items()):

        def rank(item: dict[str, Any]) -> tuple[int, int, int]:
            return (
                0 if item["record_kind"] == "evaluation" else 1,
                0 if item["source_git_sha"] == expected_sha else 1,
                0 if item["checkpoint_available"] else 1,
            )

        best_rank = min(map(rank, items))
        top = [item for item in items if rank(item) == best_rank]
        unique = {
            (
                item["result_sha256"],
                item["checkpoint_sha256"],
                tuple(
                    (step, value["result_sha256"], value["checkpoint_sha256"])
                    for step, value in sorted(item.get("milestones", {}).items())
                ),
            )
            for item in top
        }
        if len(unique) != 1:
            ambiguous.append(
                {
                    "job_id": job_id,
                    "reason": "multiple equally preferred compatible candidates differ",
                    "candidates": [item["source_result"] for item in top],
                }
            )
            continue
        chosen = copy.deepcopy(sorted(top, key=lambda item: item["source_result"])[0])
        # Headline quality comes from the standalone common evaluation. If that
        # compact record has no adjacent checkpoint, attach a separately proven
        # compatible exact-step checkpoint from the same logical cell.
        if not chosen["checkpoint_available"]:
            checkpoint_sources = sorted(
                (item for item in items if item["checkpoint_available"]),
                key=lambda item: (
                    0 if item["source_git_sha"] == chosen["source_git_sha"] else 1,
                    item["source_result"],
                ),
            )
            if checkpoint_sources:
                checkpoint_source = checkpoint_sources[0]
                for key in (
                    "checkpoint",
                    "checkpoint_available",
                    "checkpoint_sha256",
                    "checkpoint_step",
                ):
                    chosen[key] = checkpoint_source[key]
                chosen["checkpoint_source_result"] = checkpoint_source["source_result"]
                chosen["caveat"] = None
        # A standalone evaluation is the preferred quality record, but its
        # wall clock measures evaluation rather than training. Preserve the
        # compatible stage result alongside it so reused cells retain their
        # training-time and peak-memory evidence.
        training_sources = sorted(
            (
                item
                for item in items
                if item["record_kind"] == "training"
                and item["source_git_sha"] == chosen["source_git_sha"]
                and item["checkpoint_sha256"] == chosen["checkpoint_sha256"]
            ),
            key=lambda item: item["source_result"],
        )
        if training_sources:
            training_source = training_sources[0]
            chosen["training_source_result"] = training_source["source_result"]
            chosen["training_result_sha256"] = training_source["result_sha256"]
        dependent_jobs = [item["id"] for item in record["jobs"] if item.get("depends_on") == job_id]
        if dependent_jobs and not chosen["checkpoint_available"]:
            # A reporting-only City result cannot warm-start the transfer cell.
            # Queue the City source again instead of later failing the dependent
            # job or silently falling back to upstream pretrained weights.
            counts["dependency_source_without_checkpoint"] += 1
            rejected.append(
                {
                    "path": chosen["source_result"],
                    "reason": (
                        f"{job_id} is the source for {', '.join(dependent_jobs)} but has no "
                        "exact final checkpoint; source training remains queued"
                    ),
                }
            )
            continue
        chosen["accepted_at"] = _now()
        chosen["bundle_result"] = str(
            Path(record["campaign"]) / "accepted" / job_id / "results.json"
        )
        chosen["bundle_training_result"] = (
            str(Path(record["campaign"]) / "accepted" / job_id / "training-results.json")
            if chosen.get("training_source_result")
            else None
        )
        for step, milestone in chosen.get("milestones", {}).items():
            milestone["bundle_result"] = str(
                Path(record["campaign"])
                / "accepted"
                / job_id
                / "milestones"
                / step
                / "results.json"
            )
        accepted.append(chosen)

    accepted_ids = {item["job_id"] for item in accepted}
    return {
        "scanned_at": _now(),
        "roots": [str(root) for root in roots],
        "result_files_scanned": len(result_paths),
        "counts": dict(sorted(counts.items())),
        "accepted": accepted,
        "ambiguous": ambiguous,
        "rejected_examples": rejected[:100],
        "accepted_cells": len(accepted),
        "queued_cells": record["physical_job_count"] - len(accepted_ids),
    }


def _attempt_paths(
    job: dict[str, Any], attempt: Path, config: dict[str, Any] | None = None
) -> dict[str, Any]:
    run_dir = attempt / "train" / f"{job['experiment_name']}_seed{job['seed']}"
    checkpoint = run_dir / job["final_stage"] / "last.ckpt"
    training_results = run_dir / job["final_stage"] / "results.json"
    common_results = attempt / "evaluation" / job["evaluation_dataset"] / "results.json"
    stages = config.get("stages") if isinstance(config, dict) else None
    stage_results = (
        {
            stage["name"]: run_dir / stage["name"] / "results.json"
            for stage in stages
            if isinstance(stage, dict) and isinstance(stage.get("name"), str)
        }
        if isinstance(stages, list)
        else {job["final_stage"]: training_results}
    )
    milestone_checkpoints = {
        str(step): run_dir / job["final_stage"] / f"step-{step:08d}.ckpt"
        for step in job.get("evaluation_milestones", [])
    }
    milestone_results = {
        str(step): attempt
        / "evaluation"
        / f"{job['evaluation_dataset']}-step{step}"
        / "results.json"
        for step in job.get("evaluation_milestones", [])
    }
    return {
        "attempt_dir": attempt,
        "config": attempt / "resolved-config.yaml",
        "run_dir": run_dir,
        "checkpoint": checkpoint,
        "training_results": training_results,
        "common_results": common_results,
        "stage_results": stage_results,
        "milestone_checkpoints": milestone_checkpoints,
        "milestone_results": milestone_results,
        "performance": attempt / "performance.json",
        "log": attempt / "job.log",
    }


def _latest_resume_checkpoint(
    paths: dict[str, Any], config: dict[str, Any]
) -> tuple[Path, int, str] | None:
    """Return the newest complete stage checkpoint created by this attempt."""
    stages = config.get("stages")
    if not isinstance(stages, list):
        raise CampaignError("resolved training config has no stage list")
    run_dir = Path(paths["run_dir"])
    ranked: list[tuple[int, int, Path]] = []
    for stage_index, stage in enumerate(stages):
        if not isinstance(stage, dict) or not isinstance(stage.get("name"), str):
            raise CampaignError("resolved training config contains a malformed stage")
        stage_name = stage["name"]
        expected = _expected_final_step(config, stage_name)
        stage_dir = run_dir / stage_name
        candidates = [*stage_dir.glob("step-*.ckpt")]
        last = stage_dir / "last.ckpt"
        if last.is_file():
            candidates.append(last)
        for checkpoint in candidates:
            if not checkpoint.is_file() or checkpoint.stat().st_size == 0:
                continue
            step = _checkpoint_global_step(checkpoint)
            if step is not None and 0 < step <= expected:
                ranked.append((stage_index, step, checkpoint))
    if not ranked:
        return None
    _, step, checkpoint = max(ranked, key=lambda item: (item[0], item[1], item[2].name))
    state = read_checkpoint(checkpoint)
    metadata = state.get(TRAINING_RESUME_KEY)
    if not isinstance(metadata, dict) or metadata.get("stage_name") != checkpoint.parent.name:
        raise CampaignError(f"checkpoint is not a compatible Segmentary resume state: {checkpoint}")
    try:
        cfg = from_dict(ExperimentConfig, config)
    except (TypeError, ValueError) as exc:
        raise CampaignError(f"resolved training config is invalid for resume: {exc}") from exc
    matching_stages = [stage for stage in cfg.stages if stage.name == checkpoint.parent.name]
    if len(matching_stages) != 1:
        raise CampaignError(
            f"resume checkpoint stage {checkpoint.parent.name!r} matches "
            f"{len(matching_stages)} resolved stages"
        )
    stage = matching_stages[0]
    expected_optim = asdict(stage_optim_config(cfg.optim, stage, stage.iters or cfg.train.iters))
    if metadata.get("optim") != expected_optim:
        raise CampaignError(
            "checkpoint optimizer configuration does not match the resolved stage; "
            "refusing to resume with different learning-rate or schedule settings"
        )
    return checkpoint, step, _sha256(checkpoint)


def migrate_campaign_source(
    campaign: Path,
    *,
    from_sha: str,
    to_sha: str,
    reason: str,
) -> dict[str, Any]:
    """Move an interrupted pre-result campaign to a descendant source revision.

    This is deliberately narrower than a general campaign rewrite. Every worker
    must be stopped, no job may have completed, and every active lane must have a
    validated full-state periodic checkpoint. The next ordinary ``launch`` then
    resumes the same attempts with optimiser, scheduler, EMA, callback, and
    global-step state intact.
    """
    if not os.environ.get("TMUX"):
        raise CampaignError("source migration must run inside a named tmux session")
    campaign = campaign.expanduser().resolve()
    if from_sha == to_sha:
        raise CampaignError("source migration needs two different revisions")
    check_source_provenance(to_sha)
    ancestry = subprocess.run(
        ["git", "merge-base", "--is-ancestor", from_sha, to_sha],
        cwd=REPO_ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if ancestry.returncode != 0:
        raise CampaignError(f"target revision {to_sha} does not descend from {from_sha}")

    campaign_path = campaign / "campaign.json"
    record = _load_json_object(campaign_path)
    if record.get("schema_version") != CAMPAIGN_SCHEMA_VERSION:
        raise CampaignError("unsupported campaign.json schema")
    actual_source = record.get("source", {}).get("expected_git_sha")
    if actual_source != from_sha:
        raise CampaignError(
            f"campaign source is {actual_source!r}, expected migration source {from_sha!r}"
        )
    if not isinstance(reason, str) or not reason.strip() or reason != reason.strip():
        raise CampaignError("migration reason must be a non-empty trimmed string")

    changed_inputs = [
        relative
        for relative, expected in record.get("source", {}).get("files_sha256", {}).items()
        if _sha256(REPO_ROOT / relative) != expected
    ]
    if changed_inputs:
        raise CampaignError(
            "campaign config/taxonomy inputs changed across source migration: "
            f"{sorted(changed_inputs)}"
        )

    managed_sessions = [lane["tmux_session"] for lane in record["lanes"]]
    for section in ("publisher", "progress", "preflight"):
        value = record.get(section)
        if isinstance(value, dict) and isinstance(value.get("tmux_session"), str):
            managed_sessions.append(value["tmux_session"])
    alive = sorted(session for session in managed_sessions if _tmux_exists(session))
    if alive:
        raise CampaignError(f"stop every managed tmux session before migration: {alive}")

    statuses: list[tuple[Path, dict[str, Any]]] = []
    checkpoints: list[dict[str, Any]] = []
    for lane in record["lanes"]:
        status_path = _status_path(campaign, lane["id"])
        status = _load_json_object(status_path)
        if status.get("expected_git_sha") != from_sha:
            raise CampaignError(f"{status_path}: expected_git_sha does not match {from_sha}")
        jobs = status.get("jobs")
        if not isinstance(jobs, list):
            raise CampaignError(f"{status_path}: jobs must be a list")
        completed = [job.get("id") for job in jobs if job.get("status") in COMPLETED_STATUSES]
        if completed:
            raise CampaignError(
                "source migration is restricted to campaigns with no completed jobs; "
                f"{status_path} has {completed}"
            )
        active = [job for job in jobs if job.get("status") in {"training", "train_failed"}]
        unexpected = [
            (job.get("id"), job.get("status"))
            for job in jobs
            if job.get("status") not in {"pending", "training", "train_failed"}
        ]
        if len(active) != 1 or unexpected:
            raise CampaignError(
                f"{status_path}: expected one interrupted training job and otherwise pending "
                f"jobs, got active={len(active)} unexpected={unexpected}"
            )
        job = active[0]
        attempts = job.get("attempts")
        if not isinstance(attempts, list) or not attempts or not isinstance(attempts[-1], dict):
            raise CampaignError(f"{status_path}: active job has no attempt")
        attempt = attempts[-1]
        paths, _ = _attempt_path_objects(attempt)
        try:
            config = load_yaml(paths["config"])
        except (OSError, ValueError, yaml.YAMLError) as exc:
            raise CampaignError(f"cannot inspect interrupted {job.get('id')}: {exc}") from exc
        latest = _latest_resume_checkpoint(paths, config)
        if latest is None:
            raise CampaignError(f"{job.get('id')} has no validated periodic resume checkpoint")
        checkpoint, step, digest = latest
        checkpoints.append(
            {
                "lane": lane["id"],
                "job_id": job.get("id"),
                "checkpoint": str(checkpoint),
                "checkpoint_sha256": digest,
                "global_step": step,
            }
        )
        statuses.append((status_path, status))

    migration = {
        "from_git_sha": from_sha,
        "to_git_sha": to_sha,
        "migrated_at": _now(),
        "reason": reason,
        "resume_checkpoints": checkpoints,
    }
    for status_path, status in statuses:
        status["expected_git_sha"] = to_sha
        status.setdefault("source_migrations", []).append(copy.deepcopy(migration))
        _persist_status(status_path, status)
    record["source"]["expected_git_sha"] = to_sha
    allowed = set(record["reuse_policy"]["allowed_git_shas"])
    allowed.update((from_sha, to_sha))
    record["reuse_policy"]["allowed_git_shas"] = sorted(allowed)
    record.setdefault("source_migrations", []).append(migration)
    atomic_write_json(campaign_path, record)
    return migration


def _evaluation_command(
    record: dict[str, Any],
    job: dict[str, Any],
    *,
    config: Path | str,
    checkpoint: Path | str,
    output: Path | str,
) -> list[str]:
    command = [
        record["execution"]["python"],
        "-m",
        "segmentary.eval",
        str(config),
        "--ckpt",
        str(checkpoint),
        "--auto-weights",
        "--seed",
        str(job["seed"]),
        "--dataset",
        job["evaluation_dataset"],
        "--mapping",
        job["evaluation_mapping"],
        "--root",
        record["datasets"][job["evaluation_dataset"]],
        "--split",
        job["evaluation_split"],
        "--out",
        str(output),
        "--device",
        "cuda:0",
        "--num-workers",
        str(record["execution"]["eval_workers"]),
    ]
    if job.get("evaluation_split_file"):
        command.extend(["--split-file", str((REPO_ROOT / job["evaluation_split_file"]).resolve())])
    return command


def _milestone_evaluation_commands(
    record: dict[str, Any], job: dict[str, Any], paths: dict[str, Any]
) -> dict[str, list[str]]:
    checkpoints = paths.get("milestone_checkpoints", {})
    results = paths.get("milestone_results", {})
    if set(checkpoints) != set(results):
        raise CampaignError(f"{job['id']} milestone checkpoint/result keys differ")
    return {
        step: _evaluation_command(
            record,
            job,
            config=paths["config"],
            checkpoint=checkpoints[step],
            output=results[step],
        )
        for step in checkpoints
    }


def _commands(
    record: dict[str, Any],
    job: dict[str, Any],
    paths: dict[str, Any],
    *,
    result_git_sha: str | None = None,
    result_stage: str | None = None,
    resume_checkpoint: Path | None = None,
) -> tuple[list[str], list[str], list[str]]:
    python = record["execution"]["python"]
    config = str(paths["config"])
    train = [python, "-m", "segmentary.train", config, "--devices", "1"]
    if resume_checkpoint is not None:
        train.extend(["--resume-checkpoint", str(resume_checkpoint)])
    if record["execution"]["deterministic"]:
        train.append("--deterministic")
    evaluate = _evaluation_command(
        record,
        job,
        config=config,
        checkpoint=paths["checkpoint"],
        output=paths["common_results"],
    )
    applies_to = _performance_applies_to(record, job)
    benchmark = [
        python,
        "-m",
        "segmentary.performance",
        config,
        "--model-id",
        job["model"],
        "--measured-job-id",
        job["id"],
        "--applies-to",
        *applies_to,
        "--ckpt",
        str(paths["checkpoint"]),
        "--result",
        str(paths["common_results"]),
        "--out",
        str(paths["performance"]),
        "--expected-git-sha",
        record["source"]["expected_git_sha"],
        "--expected-result-git-sha",
        result_git_sha or record["source"]["expected_git_sha"],
        "--expected-result-stage",
        result_stage or f"eval:{job['evaluation_dataset']}:{job['evaluation_split']}",
        "--expected-seed",
        str(job["seed"]),
        "--checkpoint-global-step",
        str(_expected_final_step(load_yaml(paths["config"]), job["final_stage"])),
        "--auto-weights",
        "--device",
        "cuda:0",
    ]
    if not job.get("performance_owner"):
        benchmark = []
    return train, evaluate, benchmark


def _performance_applies_to(record: dict[str, Any], job: dict[str, Any]) -> list[str]:
    canonical = job["model"]
    ids = []
    for item in record["jobs"]:
        alias_target = item.get("alias_of")
        if item.get("seed") != job.get("seed"):
            continue
        if item.get("model") == canonical or (
            isinstance(alias_target, str) and alias_target.startswith(f"{canonical}--")
        ):
            ids.append(item["id"])
    return ids


def _job_environment(
    record: dict[str, Any], job: dict[str, Any], lane: dict[str, Any]
) -> dict[str, str]:
    env = os.environ.copy()
    env.update(
        {
            "PL_GLOBAL_SEED": str(job["seed"]),
            "CUDA_DEVICE_ORDER": "PCI_BUS_ID",
            "CUDA_VISIBLE_DEVICES": str(lane["gpu"]),
            "PYTHONPATH": str(SRC_ROOT),
            "MASTER_ADDR": "127.0.0.1",
            "MASTER_PORT": str(lane["master_port"]),
        }
    )
    if record["execution"].get("hf_home"):
        env["HF_HOME"] = record["execution"]["hf_home"]
    return env


def _finite_unit(value: object, *, label: str, optional: bool = False) -> None:
    if value is None and optional:
        return
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise CampaignError(f"{label} must be a number in [0, 1], got {value!r}")
    if not math.isfinite(float(value)) or not 0.0 <= float(value) <= 1.0:
        raise CampaignError(f"{label} must be finite and in [0, 1], got {value!r}")


def validate_result(
    path: Path,
    *,
    expected_sha: str,
    job: dict[str, Any],
    expected_config: dict[str, Any],
    evaluation: bool,
    require_campaign_name: bool = True,
    expected_training_stage: str | None = None,
) -> dict[str, Any]:
    try:
        record = load_results(path).to_dict()
    except (OSError, TypeError, ValueError) as exc:
        raise CampaignError(f"invalid result record {path}: {exc}") from exc
    expected_stage = (
        f"eval:{job['evaluation_dataset']}:{job['evaluation_split']}"
        if evaluation
        else expected_training_stage or job["final_stage"]
    )
    checks = {
        "stage": (record.get("stage"), expected_stage),
        "git_sha": (record.get("git_sha"), expected_sha),
        "git_dirty": (record.get("git_dirty"), False),
        "seed": (record.get("seed"), job["seed"]),
    }
    if require_campaign_name:
        checks["name"] = (record.get("name"), job["experiment_name"])
    wrong = [
        f"{key}={actual!r}, expected {wanted!r}"
        for key, (actual, wanted) in checks.items()
        if actual != wanted
    ]
    if wrong:
        raise CampaignError(f"untrusted result record {path}: {'; '.join(wrong)}")
    config = record.get("config")
    if not isinstance(config, dict):
        raise CampaignError(f"{path}: config must be a mapping")
    if require_campaign_name and config.get("model") != expected_config.get("model"):
        raise CampaignError(f"{path}: embedded model config differs from resolved config")
    train = config.get("train")
    if not isinstance(train, dict) or train.get("seed") != job["seed"]:
        raise CampaignError(f"{path}: config.train.seed does not match the job")
    if record.get("config_hash") != config_hash(config):
        raise CampaignError(f"{path}: config_hash does not match the embedded config")
    expected_plan = _iteration_plan(expected_config)
    actual_plan = _iteration_plan(config)
    if actual_plan != expected_plan:
        raise CampaignError(
            f"{path}: iteration plan {actual_plan!r} does not match expected {expected_plan!r}"
        )

    metrics = record.get("metrics")
    if not isinstance(metrics, dict):
        raise CampaignError(f"{path}: metrics must be a mapping")
    for metric in ("miou", "macc", "pixel_accuracy", "freqw_iou"):
        _finite_unit(metrics.get(metric), label=f"{path}: metrics.{metric}")
    for metric in ("mprecision", "mdice", "mspecificity"):
        if metric in metrics:
            _finite_unit(metrics.get(metric), label=f"{path}: metrics.{metric}")
    boundary = metrics.get("boundary")
    if not isinstance(boundary, dict):
        raise CampaignError(f"{path}: metrics.boundary must be a mapping")
    for metric in ("macro_f1", "macro_precision", "macro_recall"):
        _finite_unit(boundary.get(metric), label=f"{path}: metrics.boundary.{metric}")

    space = load_space(REPO_ROOT / "taxonomy", job["evaluation_space"])
    names = list(space.names)
    for metric in ("per_class_iou", "per_class_acc"):
        values = metrics.get(metric)
        if not isinstance(values, dict) or set(values) != set(names):
            raise CampaignError(f"{path}: metrics.{metric} must contain exactly {names}")
        for name in names:
            _finite_unit(values[name], label=f"{path}: metrics.{metric}.{name}", optional=True)
    for metric in (
        "per_class_precision",
        "per_class_recall",
        "per_class_dice",
        "per_class_specificity",
    ):
        if metric not in metrics:
            continue
        values = metrics[metric]
        if not isinstance(values, dict) or set(values) != set(names):
            raise CampaignError(f"{path}: metrics.{metric} must contain exactly {names}")
        for name in names:
            _finite_unit(values[name], label=f"{path}: metrics.{metric}.{name}", optional=True)
    support = metrics.get("support")
    if not isinstance(support, dict) or set(support) != set(names):
        raise CampaignError(f"{path}: metrics.support must contain exactly {names}")
    if any(
        isinstance(value, bool) or not isinstance(value, int) or value < 0
        for value in support.values()
    ):
        raise CampaignError(f"{path}: metrics.support values must be non-negative integers")
    return record


def _attempt_path_objects(attempt: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Path]]:
    raw_paths = attempt["paths"]
    if not isinstance(raw_paths, dict):
        raise CampaignError("attempt paths must be a mapping")
    paths = {
        key: Path(value)
        for key, value in raw_paths.items()
        if value is not None and not isinstance(value, dict)
    }
    for key in ("milestone_checkpoints", "milestone_results"):
        raw_named = raw_paths.get(key)
        paths[key] = (
            {name: Path(path) for name, path in raw_named.items()}
            if isinstance(raw_named, dict)
            and all(
                isinstance(name, str) and isinstance(path, str) for name, path in raw_named.items()
            )
            else {}
        )
    raw_stages = raw_paths.get("stage_results")
    stage_paths = (
        {name: Path(path) for name, path in raw_stages.items()}
        if isinstance(raw_stages, dict)
        and all(
            isinstance(name, str) and isinstance(path, str) for name, path in raw_stages.items()
        )
        else {}
    )
    return paths, stage_paths


def validate_training_artifacts(
    record: dict[str, Any], job: dict[str, Any], attempt: dict[str, Any]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    paths, stage_paths = _attempt_path_objects(attempt)
    checkpoint = paths["checkpoint"]
    if not checkpoint.is_file() or checkpoint.stat().st_size == 0:
        raise CampaignError(f"missing or empty final checkpoint: {checkpoint}")
    try:
        resolved = yaml.safe_load(paths["config"].read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise CampaignError(f"cannot read resolved config {paths['config']}: {exc}") from exc
    if not isinstance(resolved, dict):
        raise CampaignError(f"resolved config is not a mapping: {paths['config']}")
    if not stage_paths:
        raise CampaignError(f"{job['id']} attempt has no per-stage result paths")
    stage_names = [item["stage"] for item in _iteration_plan(resolved)["stages"]]
    if list(stage_paths) != stage_names:
        raise CampaignError(f"{job['id']} stage result paths {list(stage_paths)} != {stage_names}")
    stage_records = []
    for stage_name in stage_names:
        stage_records.append(
            validate_result(
                stage_paths[stage_name],
                expected_sha=record["source"]["expected_git_sha"],
                job=job,
                expected_config=resolved,
                evaluation=False,
                expected_training_stage=stage_name,
            )
        )
    expected_step = _expected_final_step(resolved, job["final_stage"])
    actual_step = _checkpoint_global_step(checkpoint)
    if actual_step != expected_step:
        raise CampaignError(f"{checkpoint}: global_step={actual_step!r}, expected {expected_step}")
    return resolved, stage_records


def validate_evaluation_artifact(
    record: dict[str, Any],
    job: dict[str, Any],
    attempt: dict[str, Any],
    resolved: dict[str, Any],
) -> dict[str, Any]:
    paths, _ = _attempt_path_objects(attempt)
    return validate_result(
        paths["common_results"],
        expected_sha=record["source"]["expected_git_sha"],
        job=job,
        expected_config=resolved,
        evaluation=True,
    )


def validate_milestone_evaluation_artifact(
    record: dict[str, Any],
    job: dict[str, Any],
    attempt: dict[str, Any],
    resolved: dict[str, Any],
    raw_step: str,
) -> dict[str, Any]:
    paths, _ = _attempt_path_objects(attempt)
    checkpoints = paths.get("milestone_checkpoints", {})
    results = paths.get("milestone_results", {})
    expected = {str(step) for step in job.get("evaluation_milestones", [])}
    if set(checkpoints) != expected or set(results) != expected:
        raise CampaignError(
            f"{job['id']} milestone paths differ from the declared steps {sorted(expected)}"
        )
    if raw_step not in expected:
        raise CampaignError(f"{job['id']} has no declared evaluation milestone {raw_step}")
    final_step = _expected_final_step(resolved, job["final_stage"])
    step = int(raw_step)
    if step >= final_step:
        raise CampaignError(
            f"{job['id']} evaluation milestone {step} must precede final step {final_step}"
        )
    checkpoint = checkpoints[raw_step]
    result_path = results[raw_step]
    if not checkpoint.is_file() or checkpoint.stat().st_size == 0:
        raise CampaignError(f"missing milestone checkpoint: {checkpoint}")
    if _checkpoint_global_step(checkpoint) != step:
        raise CampaignError(f"{checkpoint}: expected global_step={step}")
    result = validate_result(
        result_path,
        expected_sha=record["source"]["expected_git_sha"],
        job=job,
        expected_config=resolved,
        evaluation=True,
    )
    if str(checkpoint) not in str(result.get("notes", "")):
        raise CampaignError(f"{result_path}: notes do not identify {checkpoint}")
    return result


def validate_milestone_evaluation_artifacts(
    record: dict[str, Any],
    job: dict[str, Any],
    attempt: dict[str, Any],
    resolved: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    return {
        str(step): validate_milestone_evaluation_artifact(record, job, attempt, resolved, str(step))
        for step in job.get("evaluation_milestones", [])
    }


def _normalised_success_hashes(value: dict[str, Any]) -> dict[str, Any]:
    """Add empty milestone maps omitted by pre-milestone campaign records."""
    normalised = copy.deepcopy(value)
    normalised.setdefault("milestone_checkpoints", {})
    normalised.setdefault("milestone_results", {})
    return normalised


def validate_success(
    record: dict[str, Any], job: dict[str, Any], attempt: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    paths, _ = _attempt_path_objects(attempt)
    _validate_attempt_dependency(attempt)
    resolved, stage_records = validate_training_artifacts(record, job, attempt)
    validate_milestone_evaluation_artifacts(record, job, attempt, resolved)
    evaluation = validate_evaluation_artifact(record, job, attempt, resolved)
    if job.get("performance_owner"):
        validate_performance(
            paths["performance"],
            record=record,
            job=job,
            checkpoint=paths["checkpoint"],
            common_results=paths["common_results"],
            resolved_config=paths["config"],
        )
    expected_hashes = attempt.get("sha256")
    if not isinstance(expected_hashes, dict):
        raise CampaignError(f"successful attempt for {job['id']} has no artifact hashes")
    expected_hashes = _normalised_success_hashes(expected_hashes)
    actual_hashes: dict[str, Any] = {
        "resolved_config": _sha256(paths["config"]),
        "checkpoint": _sha256(paths["checkpoint"]),
        "stage_results": {
            name: _sha256(path) for name, path in _attempt_path_objects(attempt)[1].items()
        },
        "milestone_checkpoints": {
            name: _sha256(path) for name, path in paths.get("milestone_checkpoints", {}).items()
        },
        "milestone_results": {
            name: _sha256(path) for name, path in paths.get("milestone_results", {}).items()
        },
        "common_results": _sha256(paths["common_results"]),
        "performance": _sha256(paths["performance"]) if job.get("performance_owner") else None,
        "dependency_checkpoint": (
            attempt.get("dependency", {}).get("checkpoint_sha256")
            if attempt.get("dependency")
            else None
        ),
    }
    if actual_hashes != expected_hashes:
        raise CampaignError(f"successful attempt artifacts changed for {job['id']}")
    return stage_records[-1], evaluation


def validate_performance(
    path: Path,
    *,
    record: dict[str, Any],
    job: dict[str, Any],
    checkpoint: Path,
    common_results: Path,
    resolved_config: Path,
) -> dict[str, Any]:
    payload = _load_json_object(path)
    source = payload.get("source")
    hardware = payload.get("hardware")
    contract = payload.get("contract")
    model = payload.get("model")
    measurements = payload.get("measurements")
    latency = measurements.get("latency") if isinstance(measurements, dict) else None
    environment = payload.get("environment")
    applies_to = _performance_applies_to(record, job)
    evaluation_result = load_results(common_results).to_dict()
    result_config = evaluation_result.get("config")
    evaluation_config = result_config.get("evaluation") if isinstance(result_config, dict) else None
    expected_weights = (
        evaluation_config.get("weights") if isinstance(evaluation_config, dict) else None
    )
    if expected_weights not in ("raw", "ema"):
        raise CampaignError(
            f"evaluation result {common_results} records no trusted raw/ema weight source"
        )
    expected = {
        "schema_version": (payload.get("schema_version"), 1),
        "status": (payload.get("status"), "complete"),
        "model_id": (payload.get("model_id"), job["model"]),
        "benchmark_scope": (
            payload.get("benchmark_scope"),
            "model_level_railsem19_proxy",
        ),
        "applies_to": (payload.get("applies_to"), applies_to),
        "source.git_sha": (
            source.get("campaign_git_sha") if isinstance(source, dict) else None,
            record["source"]["expected_git_sha"],
        ),
        "source.git_dirty": (
            source.get("git_dirty") if isinstance(source, dict) else None,
            False,
        ),
        "source.config_sha256": (
            source.get("config_sha256") if isinstance(source, dict) else None,
            _sha256(resolved_config),
        ),
        "source.config_hash": (
            source.get("config_hash") if isinstance(source, dict) else None,
            config_hash(load_yaml(resolved_config)),
        ),
        "source.checkpoint_sha256": (
            source.get("checkpoint_sha256") if isinstance(source, dict) else None,
            _sha256(checkpoint),
        ),
        "source.result_sha256": (
            source.get("result_sha256") if isinstance(source, dict) else None,
            _sha256(common_results),
        ),
        "source.checkpoint_bytes": (
            source.get("checkpoint_bytes") if isinstance(source, dict) else None,
            checkpoint.stat().st_size,
        ),
        "source.checkpoint_step": (
            source.get("checkpoint_global_step") if isinstance(source, dict) else None,
            _checkpoint_global_step(checkpoint),
        ),
        "source.measured_checkpoint_job_id": (
            source.get("measured_checkpoint_job_id") if isinstance(source, dict) else None,
            job["id"],
        ),
        "source.result_git_sha": (
            source.get("result_git_sha") if isinstance(source, dict) else None,
            evaluation_result["git_sha"],
        ),
        "source.result_stage": (
            source.get("result_stage") if isinstance(source, dict) else None,
            f"eval:{job['evaluation_dataset']}:{job['evaluation_split']}",
        ),
        "source.result_seed": (
            source.get("result_seed") if isinstance(source, dict) else None,
            job["seed"],
        ),
        "source.weights": (
            source.get("weights") if isinstance(source, dict) else None,
            expected_weights,
        ),
        "hardware.gpu_name": (
            hardware.get("gpu_name") if isinstance(hardware, dict) else None,
            "NVIDIA L40S",
        ),
        "hardware.logical_device": (
            hardware.get("logical_device") if isinstance(hardware, dict) else None,
            "cuda:0",
        ),
        "hardware.physical_visibility_token": (
            hardware.get("physical_visibility_token") if isinstance(hardware, dict) else None,
            str(_lane_spec(record, job["lane"])["gpu"]),
        ),
        "environment.gpu_count": (
            environment.get("gpu_count") if isinstance(environment, dict) else None,
            1,
        ),
        "contract.precision": (
            contract.get("precision") if isinstance(contract, dict) else None,
            "bf16_autocast",
        ),
        "contract.backend": (
            contract.get("backend") if isinstance(contract, dict) else None,
            "pytorch",
        ),
        "contract.batch_size": (
            contract.get("batch_size") if isinstance(contract, dict) else None,
            1,
        ),
        "contract.model_only": (
            contract.get("model_only") if isinstance(contract, dict) else None,
            True,
        ),
        "contract.input_shape": (
            contract.get("input_shape_nchw") if isinstance(contract, dict) else None,
            [1, 3, 1024, 1024],
        ),
        "contract.warmup": (
            contract.get("warmup_iterations") if isinstance(contract, dict) else None,
            20,
        ),
        "contract.iterations": (
            contract.get("measured_iterations") if isinstance(contract, dict) else None,
            100,
        ),
        "measurements.memory_kind": (
            measurements.get("memory_kind") if isinstance(measurements, dict) else None,
            "pytorch_cuda_allocator_peak_reserved_excluding_context",
        ),
    }
    wrong = [
        f"{name}={actual!r}, expected {wanted!r}"
        for name, (actual, wanted) in expected.items()
        if actual != wanted
    ]
    if wrong:
        raise CampaignError(f"untrusted performance record {path}: {'; '.join(wrong)}")
    for label, value in {
        "parameter_count": model.get("parameter_count") if isinstance(model, dict) else None,
        "peak_reserved_bytes": (
            measurements.get("peak_reserved_bytes") if isinstance(measurements, dict) else None
        ),
    }.items():
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise CampaignError(f"{path}: {label} must be a positive integer")
    if not isinstance(latency, dict) or not isinstance(latency.get("raw_ms"), list):
        raise CampaignError(f"{path}: latency raw samples are missing")
    raw = latency["raw_ms"]
    if len(raw) != 100 or any(
        isinstance(value, bool)
        or not isinstance(value, int | float)
        or not math.isfinite(float(value))
        or value <= 0
        for value in raw
    ):
        raise CampaignError(f"{path}: latency must contain 100 finite positive samples")
    mean = statistics.fmean(float(value) for value in raw)
    if not math.isclose(float(latency.get("mean_ms", -1)), mean, rel_tol=1e-9):
        raise CampaignError(f"{path}: latency mean does not match raw samples")
    if not math.isclose(float(latency.get("fps", -1)), 1000.0 / mean, rel_tol=1e-9):
        raise CampaignError(f"{path}: FPS is not 1000 / mean latency")
    if not 0 < float(latency.get("p50_ms", 0)) <= float(latency.get("p95_ms", 0)):
        raise CampaignError(f"{path}: invalid p50/p95 latency")
    ordered = sorted(float(value) for value in raw)

    # Match numpy's default linear percentile without importing it into the launcher.
    def percentile(percent: float) -> float:
        index = (len(ordered) - 1) * percent / 100
        lower = math.floor(index)
        upper = math.ceil(index)
        return ordered[lower] + (ordered[upper] - ordered[lower]) * (index - lower)

    if not math.isclose(float(latency["p50_ms"]), percentile(50), rel_tol=1e-9):
        raise CampaignError(f"{path}: p50 latency does not match raw samples")
    if not math.isclose(float(latency["p95_ms"]), percentile(95), rel_tol=1e-9):
        raise CampaignError(f"{path}: p95 latency does not match raw samples")
    if (
        not isinstance(hardware, dict)
        or not isinstance(hardware.get("gpu_uuid"), str)
        or not hardware["gpu_uuid"]
    ):
        raise CampaignError(f"{path}: hardware.gpu_uuid must be non-empty private evidence")
    return payload


def validate_reused(
    record: dict[str, Any], job: dict[str, Any], attempt: dict[str, Any]
) -> dict[str, Any]:
    paths, _ = _attempt_path_objects(attempt)
    result_path = paths["common_results"]
    source_path = paths["source_results"]
    checkpoint = paths.get("checkpoint")
    expected_hashes = attempt.get("sha256") or {}
    if _sha256(result_path) != expected_hashes.get("common_results"):
        raise CampaignError(f"reused bundle result changed: {result_path}")
    if _sha256(source_path) != expected_hashes.get("common_results"):
        raise CampaignError(f"reused source result changed: {source_path}")
    stage_paths = _attempt_path_objects(attempt)[1]
    expected_stage_hashes = expected_hashes.get("stage_results") or {}
    if set(stage_paths) != set(expected_stage_hashes):
        raise CampaignError(f"reused training-stage evidence is incomplete for {job['id']}")
    for stage, stage_path in stage_paths.items():
        if _sha256(stage_path) != expected_stage_hashes[stage]:
            raise CampaignError(f"reused training result changed: {stage_path}")
    source_training = paths.get("source_training_results")
    if source_training is not None:
        expected_training_hash = expected_stage_hashes.get(job["final_stage"])
        if _sha256(source_training) != expected_training_hash:
            raise CampaignError(f"reused source training result changed: {source_training}")
    if attempt.get("checkpoint_available"):
        if checkpoint is None or _sha256(checkpoint) != expected_hashes.get("checkpoint"):
            raise CampaignError(f"reused checkpoint changed: {checkpoint}")
    elif checkpoint is not None or expected_hashes.get("checkpoint") is not None:
        raise CampaignError(
            f"reporting-only reused cell unexpectedly names a checkpoint: {checkpoint}"
        )
    _, expected_config = _resolved_config(record, job, Path(record["campaign"]) / ".prototype")
    source_record = load_results(result_path).to_dict()
    env = source_record.get("env")
    gpu_count = env.get("gpu_count") if isinstance(env, dict) else None
    actual_signature = compatibility_sha256(
        source_record["config"],
        runtime_device_count=(
            gpu_count if isinstance(gpu_count, int) and not isinstance(gpu_count, bool) else None
        ),
    )
    if actual_signature != attempt.get("compatibility_sha256"):
        raise CampaignError(f"reused result compatibility signature changed: {result_path}")
    expected_signature = compatibility_sha256(expected_config)
    if actual_signature != expected_signature:
        raise CampaignError(f"reused result no longer matches campaign job {job['id']}")
    milestone_results = paths.get("milestone_results", {})
    milestone_checkpoints = paths.get("milestone_checkpoints", {})
    expected_milestones = {str(step) for step in job.get("evaluation_milestones", [])}
    if (
        set(milestone_results) != expected_milestones
        or set(milestone_checkpoints) != expected_milestones
    ):
        raise CampaignError(f"reused milestone evidence is incomplete for {job['id']}")
    for step in sorted(expected_milestones, key=int):
        milestone_result = milestone_results[step]
        milestone_checkpoint = milestone_checkpoints[step]
        if _sha256(milestone_result) != expected_hashes.get("milestone_results", {}).get(step):
            raise CampaignError(f"reused milestone result changed: {milestone_result}")
        if _sha256(milestone_checkpoint) != expected_hashes.get("milestone_checkpoints", {}).get(
            step
        ):
            raise CampaignError(f"reused milestone checkpoint changed: {milestone_checkpoint}")
        if _checkpoint_global_step(milestone_checkpoint) != int(step):
            raise CampaignError(
                f"reused milestone checkpoint has wrong step: {milestone_checkpoint}"
            )
        milestone_record = validate_result(
            milestone_result,
            expected_sha=attempt["source_git_sha"],
            job=job,
            expected_config=expected_config,
            evaluation=True,
            require_campaign_name=False,
        )
        if str(milestone_checkpoint) not in str(milestone_record.get("notes", "")):
            raise CampaignError(
                f"reused milestone result does not name its checkpoint: {milestone_result}"
            )
    return validate_result(
        result_path,
        expected_sha=attempt["source_git_sha"],
        job=job,
        expected_config=expected_config,
        evaluation=attempt["record_kind"] == "evaluation",
        require_campaign_name=False,
    )


def _run_reused_performance(
    record: dict[str, Any],
    job: dict[str, Any],
    attempt: dict[str, Any],
    env: dict[str, str],
    status_path: Path,
    status: dict[str, Any],
) -> None:
    """Benchmark a reused Rail owner without training or re-evaluation."""
    if not job.get("performance_owner") or not attempt.get("checkpoint_available"):
        return
    paths, _ = _attempt_path_objects(attempt)
    result = validate_reused(record, job, attempt)
    performance_path = paths["performance"]
    if performance_path.is_file():
        validate_performance(
            performance_path,
            record=record,
            job=job,
            checkpoint=paths["checkpoint"],
            common_results=paths["common_results"],
            resolved_config=paths["config"],
        )
        return
    _, _, benchmark = _commands(
        record,
        job,
        paths,
        result_git_sha=attempt["source_git_sha"],
        result_stage=str(result["stage"]),
    )
    if not benchmark:
        raise CampaignError(f"reused performance owner {job['id']} resolved no command")
    job["status"] = attempt["status"] = "benchmarking"
    job["failure"] = attempt["failure"] = None
    _persist_status(status_path, status)
    code = run_logged(benchmark, env, Path(job.get("log") or performance_path.with_suffix(".log")))
    attempt["performance_returncode"] = code
    if code != 0:
        raise CampaignError(f"performance benchmark exited with status {code}")
    validate_performance(
        performance_path,
        record=record,
        job=job,
        checkpoint=paths["checkpoint"],
        common_results=paths["common_results"],
        resolved_config=paths["config"],
    )
    check_source_provenance(record["source"]["expected_git_sha"])
    # Revalidate the reused result/checkpoint after GPU work so a concurrent
    # mutation cannot be hidden behind the performance artifact.
    validate_reused(record, job, attempt)
    attempt.setdefault("sha256", {})["performance"] = _sha256(performance_path)
    job["status"] = attempt["status"] = "reused"
    job["failure"] = attempt["failure"] = None
    _persist_status(status_path, status)


def _pending_reused_performance(record: dict[str, Any]) -> list[str]:
    pending: list[str] = []
    campaign = Path(record["campaign"])
    for lane in record["lanes"]:
        status = _load_json_object(_status_path(campaign, lane["id"]))
        for job in status.get("jobs", []):
            source = _job_by_id(record, job["id"])
            attempts = job.get("attempts") if isinstance(job, dict) else None
            latest = attempts[-1] if isinstance(attempts, list) and attempts else None
            if not (
                source.get("performance_owner")
                and isinstance(latest, dict)
                and latest.get("kind") == "reused"
                and latest.get("checkpoint_available")
            ):
                continue
            raw = latest.get("paths", {}).get("performance")
            if not isinstance(raw, str) or not Path(raw).is_file():
                pending.append(job["id"])
                continue
            try:
                paths, _ = _attempt_path_objects(latest)
                validate_reused(record, job, latest)
                validate_performance(
                    paths["performance"],
                    record=record,
                    job=job,
                    checkpoint=paths["checkpoint"],
                    common_results=paths["common_results"],
                    resolved_config=paths["config"],
                )
            except CampaignError:
                pending.append(job["id"])
    return pending


def run_bootstrap(campaign: Path) -> int:
    """Backfill reused performance in tmux, then release every long-running session."""
    if not os.environ.get("TMUX"):
        raise CampaignError("reused-performance bootstrap must run inside named tmux")
    campaign = campaign.expanduser().resolve()
    record = _load_json_object(campaign / "campaign.json")
    check_source_provenance(record["source"]["expected_git_sha"])
    failures = 0
    for lane in record["lanes"]:
        status_path = _status_path(campaign, lane["id"])
        status = _load_json_object(status_path)
        for job in status.get("jobs", []):
            attempts = job.get("attempts") if isinstance(job, dict) else None
            latest = attempts[-1] if isinstance(attempts, list) and attempts else None
            source = _job_by_id(record, job["id"])
            if not (
                source.get("performance_owner")
                and isinstance(latest, dict)
                and latest.get("kind") == "reused"
            ):
                continue
            try:
                _run_reused_performance(
                    record,
                    job,
                    latest,
                    _job_environment(record, job, lane),
                    status_path,
                    status,
                )
            except CampaignError as exc:
                failures += 1
                job["status"] = latest["status"] = "performance_failed"
                job["failure"] = latest["failure"] = str(exc)
                _persist_status(status_path, status)
    if failures:
        raise CampaignError(
            f"{failures} reused performance benchmark(s) failed; new training remains gated"
        )
    if _pending_reused_performance(record):
        raise CampaignError("reused performance remains incomplete; new training remains gated")
    return launch_campaign(record, dry_run=False, skip_reused_preflight=True)


def _lane_spec(record: dict[str, Any], lane_id: str) -> dict[str, Any]:
    matches = [lane for lane in record["lanes"] if lane.get("id") == lane_id]
    if len(matches) != 1:
        raise CampaignError(f"campaign has {len(matches)} lane records for {lane_id!r}")
    return matches[0]


def _attempt_record(
    number: int,
    paths: dict[str, Any],
    train: list[str],
    evaluate: list[str],
    benchmark: list[str],
    env: dict[str, str],
) -> dict[str, Any]:
    serialized_paths = {
        key: (
            {name: str(path) for name, path in value.items()}
            if isinstance(value, dict)
            else str(value)
        )
        for key, value in paths.items()
    }
    return {
        "number": number,
        "status": "pending",
        "started_at": _now(),
        "finished_at": None,
        "failure": None,
        "train_returncode": None,
        "eval_returncode": None,
        "performance_returncode": None,
        "resume": None,
        "resumes": [],
        "train_command": train,
        "eval_command": evaluate,
        "performance_command": benchmark,
        "environment": {key: env[key] for key in ENV_KEYS if key in env},
        "paths": serialized_paths,
        "sha256": {},
    }


def _dependency_checkpoint(
    status: dict[str, Any], job: dict[str, Any]
) -> tuple[Path | None, dict[str, Any] | None]:
    dependency_id = job.get("depends_on")
    if not dependency_id:
        return None, None
    matches = [item for item in status.get("jobs", []) if item.get("id") == dependency_id]
    if len(matches) != 1:
        raise CampaignError(
            f"{job['id']} requires one same-lane dependency {dependency_id!r}, found {len(matches)}"
        )
    source = matches[0]
    if source.get("status") not in COMPLETED_STATUSES:
        raise CampaignError(
            f"{job['id']} cannot start before {dependency_id} completes successfully"
        )
    attempts = source.get("attempts")
    if not isinstance(attempts, list) or not attempts or not isinstance(attempts[-1], dict):
        raise CampaignError(f"dependency {dependency_id} has no completed attempt")
    source_attempt = attempts[-1]
    raw_checkpoint = source_attempt.get("paths", {}).get("checkpoint")
    expected_hash = source_attempt.get("sha256", {}).get("checkpoint")
    if not isinstance(raw_checkpoint, str) or not isinstance(expected_hash, str):
        raise CampaignError(f"dependency {dependency_id} has no hashed checkpoint")
    checkpoint = Path(raw_checkpoint)
    if not checkpoint.is_file() or _sha256(checkpoint) != expected_hash:
        raise CampaignError(f"dependency checkpoint is missing or changed: {checkpoint}")
    return checkpoint, {
        "job_id": dependency_id,
        "checkpoint": str(checkpoint),
        "checkpoint_sha256": expected_hash,
        "classifier_policy": "reset incompatible target classifier only",
    }


def _validate_attempt_dependency(attempt: dict[str, Any]) -> None:
    dependency = attempt.get("dependency")
    if dependency is None:
        return
    if not isinstance(dependency, dict):
        raise CampaignError("attempt dependency provenance is malformed")
    raw = dependency.get("checkpoint")
    expected = dependency.get("checkpoint_sha256")
    if not isinstance(raw, str) or not isinstance(expected, str):
        raise CampaignError("attempt dependency lacks checkpoint provenance")
    checkpoint = Path(raw)
    if not checkpoint.is_file() or _sha256(checkpoint) != expected:
        raise CampaignError(f"attempt dependency checkpoint changed: {checkpoint}")


def run_worker(campaign: Path, lane_id: str) -> int:
    if not os.environ.get("TMUX"):
        raise CampaignError("campaign workers must run inside a named tmux session")
    campaign = campaign.expanduser().resolve()
    record = _load_json_object(campaign / "campaign.json")
    if record.get("schema_version") != CAMPAIGN_SCHEMA_VERSION:
        raise CampaignError("unsupported campaign.json schema")
    lane = _lane_spec(record, lane_id)
    if os.environ.get("CUDA_VISIBLE_DEVICES") != str(lane["gpu"]):
        raise CampaignError(
            f"lane {lane_id} requires CUDA_VISIBLE_DEVICES={lane['gpu']}, got "
            f"{os.environ.get('CUDA_VISIBLE_DEVICES')!r}"
        )
    expected_sha = record["source"]["expected_git_sha"]
    check_source_provenance(expected_sha)
    status_path = _status_path(campaign, lane_id)
    status = _load_json_object(status_path)
    if status.get("tmux_session") != lane["tmux_session"]:
        raise CampaignError(f"{status_path} does not belong to tmux session {lane['tmux_session']}")
    status["status"] = "running"
    status["started_at"] = status.get("started_at") or _now()
    status["finished_at"] = None
    status["failure"] = None
    _persist_status(status_path, status)
    failures = 0

    for job in status["jobs"]:
        source_job = _job_by_id(record, job["id"])
        if any(
            source_job.get(key) != job.get(key) for key in ("model", "protocol", "seed", "lane")
        ):
            raise CampaignError(f"lane status metadata drifted for {job['id']}")
        attempts = job.get("attempts")
        reused_attempt = (
            attempts[-1]
            if isinstance(attempts, list)
            and attempts
            and isinstance(attempts[-1], dict)
            and attempts[-1].get("kind") == "reused"
            else None
        )
        if reused_attempt is not None:
            if not isinstance(attempts, list) or not attempts:
                raise CampaignError(f"reused job {job['id']} has no attempt record")
            try:
                _run_reused_performance(
                    record,
                    job,
                    reused_attempt,
                    _job_environment(record, job, lane),
                    status_path,
                    status,
                )
                validate_reused(record, job, reused_attempt)
            except CampaignError as exc:
                failures += 1
                job["status"] = reused_attempt["status"] = "performance_failed"
                job["failure"] = reused_attempt["failure"] = str(exc)
                _persist_status(status_path, status)
            else:
                job["status"] = reused_attempt["status"] = "reused"
                job["failure"] = reused_attempt["failure"] = None
                _persist_status(status_path, status)
                print(f"skip validated reused: {job['id']}")
            continue
        if job.get("status") == "succeeded":
            attempts = job.get("attempts")
            if not isinstance(attempts, list) or not attempts:
                raise CampaignError(f"successful job {job['id']} has no attempt record")
            validate_success(record, job, attempts[-1])
            job["failure"] = attempts[-1]["failure"] = None
            print(f"skip validated {job['status']}: {job['id']}")
            continue

        check_source_provenance(expected_sha)
        env = _job_environment(record, job, lane)
        resumable = (
            attempts[-1]
            if isinstance(attempts, list)
            and attempts
            and job.get("status")
            in {
                "milestone_evaluating",
                "milestone_eval_failed",
                "milestone_eval_artifact_failed",
                "evaluating",
                "eval_failed",
                "eval_artifact_failed",
                "benchmarking",
                "performance_failed",
                "performance_artifact_failed",
            }
            else None
        )
        training_resume: (
            tuple[dict[str, Any], dict[str, Any], dict[str, Path], Path, int, str] | None
        ) = None
        if (
            resumable is None
            and isinstance(attempts, list)
            and attempts
            and isinstance(attempts[-1], dict)
            and job.get("status") in {"training", "train_failed"}
        ):
            interrupted = attempts[-1]
            _validate_attempt_dependency(interrupted)
            interrupted_paths, _ = _attempt_path_objects(interrupted)
            try:
                interrupted_config = load_yaml(interrupted_paths["config"])
            except (OSError, ValueError, yaml.YAMLError) as exc:
                raise CampaignError(f"cannot inspect interrupted {job['id']}: {exc}") from exc
            latest = _latest_resume_checkpoint(interrupted_paths, interrupted_config)
            if latest is not None:
                checkpoint, step, checkpoint_sha256 = latest
                training_resume = (
                    interrupted,
                    interrupted_config,
                    interrupted_paths,
                    checkpoint,
                    step,
                    checkpoint_sha256,
                )

        if resumable is None and training_resume is None:
            dependency_checkpoint, dependency = _dependency_checkpoint(status, job)
            number, attempt_dir = _next_attempt(job, campaign)
            attempt_dir.mkdir(parents=True, exist_ok=False)
            _, config_dict = _resolved_config(
                record,
                job,
                attempt_dir,
                dependency_checkpoint=dependency_checkpoint,
            )
            paths = _attempt_paths(job, attempt_dir, config_dict)
            atomic_write_text(paths["config"], yaml.safe_dump(config_dict, sort_keys=False))
            train, evaluate, benchmark = _commands(record, job, paths)
            attempt = _attempt_record(number, paths, train, evaluate, benchmark, env)
            milestone_commands = _milestone_evaluation_commands(record, job, paths)
            attempt["milestone_eval_commands"] = milestone_commands
            attempt["milestone_eval_returncodes"] = {step: None for step in milestone_commands}
            if dependency is not None:
                attempt["dependency"] = dependency
            job["attempt"] = number
            job.setdefault("attempts", []).append(attempt)
            job.update(
                {
                    "status": "training",
                    "started_at": _now(),
                    "finished_at": None,
                    "failure": None,
                    "run_dir": str(paths["run_dir"]),
                    "checkpoint": str(paths["checkpoint"]),
                    "training_results": str(paths["training_results"]),
                    "common_results": str(paths["common_results"]),
                    "performance": str(paths["performance"]),
                    "log": str(paths["log"]),
                    "resolved_config_hash": config_hash(config_dict),
                }
            )
            attempt["status"] = "training"
            _persist_status(status_path, status)

            train_code = run_logged(train, env, paths["log"])
            attempt["train_returncode"] = train_code
        elif training_resume is not None:
            attempt, config_dict, paths, checkpoint, step, checkpoint_sha256 = training_resume
            train, evaluate, benchmark = _commands(
                record,
                job,
                paths,
                resume_checkpoint=checkpoint,
            )
            resume_record = {
                "checkpoint": str(checkpoint),
                "checkpoint_sha256": checkpoint_sha256,
                "global_step": step,
                "resumed_at": _now(),
            }
            attempt["resume"] = resume_record
            attempt.setdefault("resumes", []).append(resume_record)
            attempt["train_command"] = train
            attempt["eval_command"] = evaluate
            attempt["performance_command"] = benchmark
            milestone_commands = _milestone_evaluation_commands(record, job, paths)
            attempt["milestone_eval_commands"] = milestone_commands
            attempt.setdefault(
                "milestone_eval_returncodes", {step: None for step in milestone_commands}
            )
            attempt["status"] = job["status"] = "training"
            attempt["failure"] = job["failure"] = None
            attempt["finished_at"] = job["finished_at"] = None
            _persist_status(status_path, status)
            print(f"resume {job['id']} from optimizer step {step}: {checkpoint}")
            train_code = run_logged(train, env, paths["log"])
            attempt["train_returncode"] = train_code
        else:
            attempt = resumable
            _validate_attempt_dependency(attempt)
            paths, _ = _attempt_path_objects(attempt)
            try:
                config_dict = load_yaml(paths["config"])
            except (OSError, ValueError, yaml.YAMLError) as exc:
                raise CampaignError(f"cannot resume {job['id']}: {exc}") from exc
            train, evaluate, benchmark = _commands(record, job, paths)
            milestone_commands = _milestone_evaluation_commands(record, job, paths)
            attempt["milestone_eval_commands"] = milestone_commands
            attempt.setdefault(
                "milestone_eval_returncodes", {step: None for step in milestone_commands}
            )
            train_code = 0
        try:
            check_source_provenance(expected_sha)
        except CampaignError as exc:
            attempt["status"] = job["status"] = "provenance_failed"
            attempt["failure"] = job["failure"] = str(exc)
            attempt["finished_at"] = job["finished_at"] = _now()
            status["status"] = "failed_provenance"
            status["failure"] = str(exc)
            status["finished_at"] = _now()
            _persist_status(status_path, status)
            return 2
        if train_code != 0:
            failures += 1
            message = f"training exited with status {train_code}"
            attempt["status"] = job["status"] = "train_failed"
            attempt["failure"] = job["failure"] = message
            attempt["finished_at"] = job["finished_at"] = _now()
            _persist_status(status_path, status)
            continue
        try:
            resolved, _ = validate_training_artifacts(record, job, attempt)
        except CampaignError as exc:
            failures += 1
            attempt["status"] = job["status"] = "train_artifact_failed"
            attempt["failure"] = job["failure"] = str(exc)
            attempt["finished_at"] = job["finished_at"] = _now()
            _persist_status(status_path, status)
            continue

        milestone_failed = False
        for milestone_step, milestone_command in milestone_commands.items():
            try:
                validate_milestone_evaluation_artifact(
                    record, job, attempt, resolved, milestone_step
                )
                milestone_code = 0
            except CampaignError:
                attempt["status"] = job["status"] = "milestone_evaluating"
                _persist_status(status_path, status)
                milestone_code = run_logged(milestone_command, env, paths["log"])
                attempt["milestone_eval_returncodes"][milestone_step] = milestone_code
            if milestone_code != 0:
                failures += 1
                message = (
                    f"milestone evaluation at step {milestone_step} exited with "
                    f"status {milestone_code}"
                )
                attempt["status"] = job["status"] = "milestone_eval_failed"
                attempt["failure"] = job["failure"] = message
                attempt["finished_at"] = job["finished_at"] = _now()
                _persist_status(status_path, status)
                milestone_failed = True
                break
            try:
                validate_milestone_evaluation_artifact(
                    record, job, attempt, resolved, milestone_step
                )
                check_source_provenance(expected_sha)
            except CampaignError as exc:
                failures += 1
                attempt["status"] = job["status"] = "milestone_eval_artifact_failed"
                attempt["failure"] = job["failure"] = str(exc)
                attempt["finished_at"] = job["finished_at"] = _now()
                _persist_status(status_path, status)
                milestone_failed = True
                break
        if milestone_failed:
            continue

        try:
            validate_evaluation_artifact(record, job, attempt, resolved)
            eval_code = 0
        except CampaignError:
            attempt["status"] = job["status"] = "evaluating"
            _persist_status(status_path, status)
            eval_code = run_logged(evaluate, env, paths["log"])
            attempt["eval_returncode"] = eval_code
        try:
            check_source_provenance(expected_sha)
        except CampaignError as exc:
            attempt["status"] = job["status"] = "provenance_failed"
            attempt["failure"] = job["failure"] = str(exc)
            attempt["finished_at"] = job["finished_at"] = _now()
            status["status"] = "failed_provenance"
            status["failure"] = str(exc)
            status["finished_at"] = _now()
            _persist_status(status_path, status)
            return 2
        if eval_code != 0:
            failures += 1
            message = f"evaluation exited with status {eval_code}"
            attempt["status"] = job["status"] = "eval_failed"
            attempt["failure"] = job["failure"] = message
            attempt["finished_at"] = job["finished_at"] = _now()
            _persist_status(status_path, status)
            continue
        try:
            validate_evaluation_artifact(record, job, attempt, resolved)
        except CampaignError as exc:
            failures += 1
            attempt["status"] = job["status"] = "eval_artifact_failed"
            attempt["failure"] = job["failure"] = str(exc)
            attempt["finished_at"] = job["finished_at"] = _now()
            _persist_status(status_path, status)
            continue

        if job.get("performance_owner"):
            attempt["status"] = job["status"] = "benchmarking"
            _persist_status(status_path, status)
            try:
                validate_performance(
                    paths["performance"],
                    record=record,
                    job=job,
                    checkpoint=paths["checkpoint"],
                    common_results=paths["common_results"],
                    resolved_config=paths["config"],
                )
            except CampaignError:
                performance_code = run_logged(benchmark, env, paths["log"])
                attempt["performance_returncode"] = performance_code
                if performance_code != 0:
                    failures += 1
                    message = f"performance benchmark exited with status {performance_code}"
                    attempt["status"] = job["status"] = "performance_failed"
                    attempt["failure"] = job["failure"] = message
                    _persist_status(status_path, status)
                    continue
                try:
                    validate_performance(
                        paths["performance"],
                        record=record,
                        job=job,
                        checkpoint=paths["checkpoint"],
                        common_results=paths["common_results"],
                        resolved_config=paths["config"],
                    )
                    check_source_provenance(expected_sha)
                except CampaignError as exc:
                    failures += 1
                    attempt["status"] = job["status"] = "performance_artifact_failed"
                    attempt["failure"] = job["failure"] = str(exc)
                    _persist_status(status_path, status)
                    continue

        attempt["sha256"] = {
            "resolved_config": _sha256(paths["config"]),
            "checkpoint": _sha256(paths["checkpoint"]),
            "stage_results": {
                name: _sha256(path) for name, path in _attempt_path_objects(attempt)[1].items()
            },
            "milestone_checkpoints": {
                name: _sha256(path) for name, path in paths.get("milestone_checkpoints", {}).items()
            },
            "milestone_results": {
                name: _sha256(path) for name, path in paths.get("milestone_results", {}).items()
            },
            "common_results": _sha256(paths["common_results"]),
            "performance": (
                _sha256(paths["performance"]) if job.get("performance_owner") else None
            ),
            "dependency_checkpoint": (
                attempt.get("dependency", {}).get("checkpoint_sha256")
                if attempt.get("dependency")
                else None
            ),
        }
        attempt["status"] = job["status"] = "succeeded"
        attempt["finished_at"] = job["finished_at"] = _now()
        attempt["failure"] = job["failure"] = None
        _persist_status(status_path, status)

    status["status"] = "complete" if failures == 0 else "complete_with_failures"
    status["finished_at"] = _now()
    _persist_status(status_path, status)
    print(f"lane {lane_id} {status['status']}; status: {status_path}")
    return 0 if failures == 0 else 1


def _aggregate(values: Iterable[object]) -> tuple[float, float, int]:
    clean = [
        float(value)
        for value in values
        if isinstance(value, int | float)
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    ]
    if not clean:
        return math.nan, math.nan, 0
    return (
        statistics.fmean(clean),
        statistics.stdev(clean) if len(clean) > 1 else 0.0,
        len(clean),
    )


def _percent(values: Iterable[object]) -> str:
    mean, _, count = _aggregate(values)
    if count == 0:
        return "—"
    return f"{100 * mean:.2f}"


def _available_job_records(
    record: dict[str, Any],
) -> dict[str, tuple[dict[str, Any], dict[str, Any]]]:
    """Validate and return every currently reportable cell."""
    campaign = Path(record["campaign"])
    by_id: dict[str, tuple[dict[str, Any], dict[str, Any]]] = {}
    for lane in record["lanes"]:
        status = _load_json_object(_status_path(campaign, lane["id"]))
        for job in status.get("jobs", []):
            if not isinstance(job, dict) or job.get("id") in by_id:
                raise CampaignError(f"duplicate or malformed job in {lane['id']} status")
            attempts = job.get("attempts")
            if job.get("status") not in {"succeeded", "reused"}:
                continue
            if not isinstance(attempts, list) or not attempts:
                raise CampaignError(f"reportable job {job.get('id')} has no attempt record")
            if job["status"] == "reused":
                result = validate_reused(record, job, attempts[-1])
            else:
                _, result = validate_success(record, job, attempts[-1])
            by_id[job["id"]] = (job, result)
    for alias in (job for job in record["jobs"] if job.get("alias_of")):
        canonical_id = alias["alias_of"]
        if canonical_id not in by_id:
            continue
        canonical_job, result = by_id[canonical_id]
        alias_job = {
            **alias,
            "status": "alias",
            "attempt": canonical_job.get("attempt"),
            "attempts": [
                {
                    "kind": "alias",
                    "status": "alias",
                    "alias_of": canonical_id,
                    "caveat": (
                        "No duplicate training was run: this compatibility alias uses the "
                        "validated canonical SMP DeepLabV3+/ResNet-101 cell."
                    ),
                }
            ],
            "started_at": canonical_job.get("started_at"),
            "finished_at": canonical_job.get("finished_at"),
            "checkpoint": canonical_job.get("checkpoint"),
            "common_results": canonical_job.get("common_results"),
        }
        by_id[alias["id"]] = (alias_job, result)
    return by_id


def _summary(values: Iterable[object]) -> dict[str, Any]:
    clean = [
        float(value)
        for value in values
        if isinstance(value, int | float)
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    ]
    return {
        "mean": statistics.fmean(clean) if clean else None,
        "sample_std": statistics.stdev(clean) if len(clean) > 1 else None,
        "count": len(clean),
    }


def _complete_metrics(metrics: dict[str, Any], names: Sequence[str]) -> dict[str, Any]:
    """Normalize old and new result schemas without inventing unavailable values."""
    completed = copy.deepcopy(metrics)
    confusion = completed.get("confusion")
    if any(completed.get(key) is None for key in ("mprecision", "mdice", "mspecificity")):
        if not (
            isinstance(confusion, list)
            and len(confusion) == len(names)
            and all(isinstance(row, list) and len(row) == len(names) for row in confusion)
        ):
            raise CampaignError("legacy metrics need a square confusion matrix for derivation")
        matrix = [[int(value) for value in row] for row in confusion]
        total = sum(map(sum, matrix))
        precision: list[float] = []
        dice: list[float] = []
        specificity: list[float] = []
        per_iou = completed["per_class_iou"]
        for index, name in enumerate(names):
            active = per_iou.get(name) is not None
            tp = matrix[index][index]
            gt = sum(matrix[index])
            predicted = sum(row[index] for row in matrix)
            union = gt + predicted - tp
            if active and union > 0:
                precision.append(tp / max(predicted, 1))
                dice.append(2 * tp / max(gt + predicted, 1))
            negative = total - gt
            if active and negative > 0:
                fp = predicted - tp
                specificity.append((negative - fp) / negative)
        completed["mprecision"] = statistics.fmean(precision) if precision else None
        completed["mdice"] = statistics.fmean(dice) if dice else None
        completed["mspecificity"] = statistics.fmean(specificity) if specificity else None
    return completed


def _iteration_progress(
    plan: dict[str, Any], *, checkpoint_available: bool, checkpoint_step: int | None
) -> dict[str, Any]:
    stages = [
        {
            "stage": row["stage"],
            "dataset": "Cityscapes" if row["stage"] == "cityscapes" else "RailSem19",
            "target_iterations": row["target_iterations"],
            "current_iterations": row["target_iterations"],
        }
        for row in plan["stages"]
    ]
    total = plan["total_target_iterations"]
    final = stages[-1]["target_iterations"]
    verified_checkpoint = checkpoint_available and checkpoint_step == final
    return {
        "target_iterations": total,
        "current_iterations": total,
        "stages": stages,
        "final_verification": {
            "result_verified": True,
            "result_total_iterations": total,
            "result_final_stage_iteration": final,
            "checkpoint_available": checkpoint_available,
            "checkpoint_verified": verified_checkpoint,
            "checkpoint_global_step": checkpoint_step if verified_checkpoint else None,
        },
    }


def _training_stage_evidence(attempt: dict[str, Any]) -> list[dict[str, Any]]:
    _, stage_paths = _attempt_path_objects(attempt)
    resumes = attempt.get("resumes")
    resume_steps = (
        [row.get("global_step") for row in resumes if isinstance(row, dict)]
        if isinstance(resumes, list)
        else []
    )
    rows = []
    for stage, path in stage_paths.items():
        value = load_results(path).to_dict()
        wall = value.get("wall_clock_s")
        environment = value.get("env")
        devices = environment.get("gpu_count") if isinstance(environment, dict) else None
        peaks = value.get("peak_vram_bytes")
        peak = (
            max((item for item in peaks.values() if isinstance(item, int)), default=None)
            if isinstance(peaks, dict)
            else None
        )
        if not isinstance(wall, int | float) or isinstance(wall, bool) or wall <= 0:
            raise CampaignError(f"{path}: stage wall_clock_s must be positive")
        if not isinstance(devices, int) or isinstance(devices, bool) or devices < 1:
            raise CampaignError(f"{path}: env.gpu_count must be positive")
        row = {
            "stage": stage,
            "wall_clock_s": float(wall),
            "gpu_count": devices,
            "gpu_hours": float(wall) * devices / 3600,
            "peak_vram_bytes_per_device": peak,
            "result_sha256": _sha256(path),
        }
        if resume_steps:
            row["timing_scope"] = "post_resume_segment_only"
            row["resume_checkpoint_steps"] = resume_steps
        rows.append(row)
    return rows


def _normalised_individual(
    job: dict[str, Any], result: dict[str, Any], attempt: dict[str, Any]
) -> dict[str, Any]:
    # Result JSON is emitted with sorted mapping keys, while the confusion matrix
    # always follows canonical class-id order.  Legacy precision/Dice/specificity
    # derivation must therefore use the taxonomy, not dictionary insertion order.
    names = list(load_space(REPO_ROOT / "taxonomy", job["evaluation_space"]).names)
    metrics = _complete_metrics(result["metrics"], names)
    boundary = metrics["boundary"]
    source_result = Path(attempt["paths"]["common_results"])
    checkpoint_raw = attempt["paths"].get("checkpoint")
    checkpoint = Path(checkpoint_raw) if isinstance(checkpoint_raw, str) else None
    checkpoint_available = bool(
        attempt.get("checkpoint_available", checkpoint is not None)
        and checkpoint is not None
        and checkpoint.is_file()
    )
    checkpoint_step = (
        attempt.get("checkpoint_step")
        if attempt.get("kind") == "reused"
        else _checkpoint_global_step(checkpoint)
        if checkpoint_available
        else None
    )
    source_hashes = attempt.get("sha256") or {}
    result_hash = source_hashes.get("common_results") or _sha256(source_result)
    checkpoint_hash = (
        source_hashes.get("checkpoint") or _sha256(checkpoint) if checkpoint_available else None
    )
    _, stage_paths = _attempt_path_objects(attempt)
    training_stages = _training_stage_evidence(attempt) if stage_paths else []
    raw_milestone_results = attempt.get("paths", {}).get("milestone_results", {})
    raw_milestone_checkpoints = attempt.get("paths", {}).get("milestone_checkpoints", {})
    milestone_hashes = source_hashes.get("milestone_results", {})
    milestone_checkpoint_hashes = source_hashes.get("milestone_checkpoints", {})
    milestones: dict[str, Any] = {}
    if isinstance(raw_milestone_results, dict) and isinstance(raw_milestone_checkpoints, dict):
        for step, raw_result in sorted(
            raw_milestone_results.items(), key=lambda item: int(item[0])
        ):
            raw_checkpoint = raw_milestone_checkpoints.get(step)
            if not isinstance(raw_result, str) or not isinstance(raw_checkpoint, str):
                raise CampaignError(f"{job['id']}: malformed milestone paths for step {step}")
            milestone_result_path = Path(raw_result)
            milestone_checkpoint = Path(raw_checkpoint)
            milestone_record = load_results(milestone_result_path).to_dict()
            milestone_metrics = _complete_metrics(milestone_record["metrics"], names)
            milestones[step] = {
                "target_stage_iterations": int(step),
                "cumulative_iterations": 40_000 + int(step),
                "metrics": {
                    **{key: milestone_metrics.get(key) for key, _ in AGGREGATE_METRICS},
                    "boundary_macro_f1": milestone_metrics["boundary"].get("macro_f1"),
                },
                "source": {
                    "result_sha256": milestone_hashes.get(step) or _sha256(milestone_result_path),
                    "checkpoint_sha256": milestone_checkpoint_hashes.get(step)
                    or _sha256(milestone_checkpoint),
                    "checkpoint_size_bytes": milestone_checkpoint.stat().st_size,
                },
            }
    evaluation_wall = result.get("wall_clock_s")
    sizes = result.get("dataset_sizes")
    evaluation_images = sizes.get("eval") if isinstance(sizes, dict) else None
    pipeline = None
    if str(result.get("stage", "")).startswith("eval:"):
        if (
            not isinstance(evaluation_wall, int | float)
            or isinstance(evaluation_wall, bool)
            or evaluation_wall <= 0
            or not isinstance(evaluation_images, int)
            or isinstance(evaluation_images, bool)
            or evaluation_images < 1
        ):
            raise CampaignError(f"{source_result}: full evaluation timing is invalid")
        pipeline = {
            "images": evaluation_images,
            "wall_clock_s": float(evaluation_wall),
            "images_per_s": evaluation_images / float(evaluation_wall),
            "scope": "loader, sliding-window inference, and metrics",
        }
    return {
        "seed": job["seed"],
        "metrics": {
            **{key: metrics.get(key) for key, _ in AGGREGATE_METRICS},
            "boundary_macro_f1": boundary.get("macro_f1"),
            "per_class_iou": {name: metrics["per_class_iou"].get(name) for name in names},
            "support": {name: metrics["support"].get(name) for name in names},
        },
        "source": {
            "result_sha256": result_hash,
            "git_sha": result["git_sha"],
            "git_dirty": False,
            "checkpoint_available": checkpoint_available,
            "checkpoint_sha256": checkpoint_hash,
            "checkpoint_step": checkpoint_step,
            "checkpoint_size_bytes": checkpoint.stat().st_size if checkpoint_available else None,
            "training_stages": training_stages,
            "full_validation_pipeline": pipeline,
        },
        "milestones": milestones,
    }


def _aggregate_protocol(protocol: dict[str, Any]) -> None:
    individuals = sorted(protocol["individual"], key=lambda item: item["seed"])
    protocol["individual"] = individuals
    protocol["seeds"] = [item["seed"] for item in individuals]
    protocol["seed_count"] = len(individuals)
    aggregate = {
        key: _summary(item["metrics"].get(key) for item in individuals) for key, _ in RECORD_METRICS
    }
    names = list(individuals[0]["metrics"]["per_class_iou"])
    aggregate["per_class_iou"] = {
        name: _summary(item["metrics"]["per_class_iou"].get(name) for item in individuals)
        for name in names
    }
    supports = [item["metrics"]["support"] for item in individuals]
    if any(value != supports[0] for value in supports[1:]):
        raise CampaignError("retained seed records disagree on validation class support")
    protocol["aggregate"] = aggregate
    protocol["support"] = supports[0]
    milestone_steps = sorted(
        {step for item in individuals for step in item.get("milestones", {})}, key=int
    )
    protocol["milestones"] = {}
    for step in milestone_steps:
        rows = [item["milestones"].get(step) for item in individuals]
        if any(row is None for row in rows):
            raise CampaignError(f"retained seed records disagree on milestone step {step}")
        concrete = [row for row in rows if isinstance(row, dict)]
        protocol["milestones"][step] = {
            "target_stage_iterations": int(step),
            "cumulative_iterations": concrete[0]["cumulative_iterations"],
            "aggregate": {
                key: _summary(row["metrics"].get(key) for row in concrete)
                for key, _ in RECORD_METRICS
            },
            "individual": [
                {
                    "seed": item["seed"],
                    "metrics": row["metrics"],
                    "source": row["source"],
                }
                for item, row in zip(individuals, concrete, strict=True)
            ],
        }


def _protocol_resource_evidence(
    individuals: list[dict[str, Any]], *, parameter_count: int | None
) -> dict[str, Any]:
    checkpoints = [item["source"] for item in individuals]
    sizes = [item.get("checkpoint_size_bytes") for item in checkpoints]
    available_sizes = [item for item in sizes if isinstance(item, int)]
    stage_sets = [item.get("training_stages") or [] for item in checkpoints]
    partial_runs = [
        rows
        for rows in stage_sets
        if any(row.get("timing_scope") == "post_resume_segment_only" for row in rows)
    ]
    training_runs = [rows for rows in stage_sets if rows and rows not in partial_runs]
    if partial_runs:
        training_runs = []
    training: dict[str, Any] = {
        "seed_count": len(training_runs),
        "gpu_model": "NVIDIA L40S" if training_runs else None,
        "gpus_per_run": (training_runs[0][0]["gpu_count"] if training_runs else None),
        "wall_clock_s_mean": (
            statistics.fmean(sum(row["wall_clock_s"] for row in run) for run in training_runs)
            if training_runs
            else None
        ),
        "gpu_hours_mean": (
            statistics.fmean(sum(row["gpu_hours"] for row in run) for run in training_runs)
            if training_runs
            else None
        ),
        "peak_vram_bytes_per_device": (
            max(
                row["peak_vram_bytes_per_device"]
                for run in training_runs
                for row in run
                if isinstance(row["peak_vram_bytes_per_device"], int)
            )
            if training_runs
            and any(
                isinstance(row["peak_vram_bytes_per_device"], int)
                for run in training_runs
                for row in run
            )
            else None
        ),
    }
    if partial_runs:
        training["total_timing_status"] = "not_retained_due_to_resume"
        training["post_resume_segments"] = [
            {
                "stages": copy.deepcopy(run),
                "note": "These values cover only the final post-resume segment, not the total.",
            }
            for run in partial_runs
        ]
    if training_runs and len(training_runs[0]) > 1:
        names = [row["stage"] for row in training_runs[0]]
        training["stages"] = [
            {
                "stage": name,
                "wall_clock_s_mean": statistics.fmean(
                    next(row["wall_clock_s"] for row in run if row["stage"] == name)
                    for run in training_runs
                ),
                "peak_vram_bytes_per_device": max(
                    next(row["peak_vram_bytes_per_device"] for row in run if row["stage"] == name)
                    for run in training_runs
                ),
            }
            for name in names
        ]
    pipelines = [item.get("full_validation_pipeline") for item in checkpoints]
    pipeline_rows = [item for item in pipelines if isinstance(item, dict)]
    return {
        "parameter_count": parameter_count,
        "final_checkpoint": {
            "available": bool(available_sizes),
            "size_bytes": available_sizes[0] if available_sizes else None,
        },
        "training": training,
        "full_validation_pipeline": {
            "seed_count": len(pipeline_rows),
            "images": pipeline_rows[0]["images"] if pipeline_rows else None,
            "wall_clock_s_mean": (
                statistics.fmean(item["wall_clock_s"] for item in pipeline_rows)
                if pipeline_rows
                else None
            ),
            "images_per_s_mean": (
                statistics.fmean(item["images_per_s"] for item in pipeline_rows)
                if pipeline_rows
                else None
            ),
            "scope": "loader, sliding-window inference, and metrics",
        },
    }


def _new_protocol(
    job: dict[str, Any], result: dict[str, Any], attempt: dict[str, Any]
) -> dict[str, Any]:
    plan = attempt.get("iteration_plan") or _iteration_plan(result["config"])
    checkpoint_available = bool(attempt.get("checkpoint_available", True))
    checkpoint_step = attempt.get("checkpoint_step")
    if attempt.get("kind") != "reused":
        raw = attempt["paths"].get("checkpoint")
        checkpoint_step = _checkpoint_global_step(Path(raw)) if isinstance(raw, str) else None
    images = result.get("dataset_sizes", {}).get("eval")
    dependency = attempt.get("dependency")
    public_dependency = (
        {
            "job_id": dependency.get("job_id"),
            "checkpoint_sha256": dependency.get("checkpoint_sha256"),
            "classifier_policy": dependency.get("classifier_policy"),
        }
        if isinstance(dependency, dict)
        else None
    )
    target_iterations = plan["stages"][-1]["target_iterations"]
    milestone_text = ", ".join(f"{step:,}" for step in job.get("evaluation_milestones", []))
    result_config = result.get("config")
    evaluation_config = result_config.get("evaluation") if isinstance(result_config, dict) else None
    evaluation_weights = (
        evaluation_config.get("weights") if isinstance(evaluation_config, dict) else None
    )
    if evaluation_weights not in ("raw", "ema"):
        raise CampaignError(
            f"validated result for {job['id']} records no trusted raw/ema weight source"
        )
    caveats = [attempt["caveat"]] if attempt.get("caveat") else []
    if attempt.get("resumes"):
        caveats.append(
            "The exact total training wall time, GPU-hours, and whole-run peak VRAM were not "
            "retained across interruption recovery; the final post-resume segment remains in "
            "the machine record but is not presented as the total."
        )
    raw_correction = attempt.get("evaluation_correction")
    public_correction = None
    if (
        isinstance(raw_correction, dict)
        and raw_correction.get("kind") == "batchnorm_running_statistics_recalibration"
        and raw_correction.get("parameters_changed") == 0
    ):
        keys = (
            "kind",
            "reason",
            "parameters_changed",
            "bn_modules",
            "recalibration_batches",
            "recalibration_images",
            "old_miou",
            "corrected_miou",
            "source_checkpoint_sha256",
            "corrected_checkpoint_sha256",
            "source_result_sha256",
            "corrected_result_sha256",
            "corrected_performance_sha256",
        )
        public_correction = {
            key: raw_correction[key] for key in keys if raw_correction.get(key) is not None
        }
        public_correction["data_scope"] = "training split only; no validation images"
        caveats.append(
            "Before evaluation, BatchNorm running-statistics buffers were recalibrated on the "
            "training split to correct an imported momentum-convention error; no learned "
            "parameter or validation image was used."
        )
    return {
        "status": "complete",
        "label": job["protocol_label"],
        "dataset": f"{'Cityscapes' if job['protocol'] == 'cityscapes' else 'RailSem19'} val",
        "taxonomy": job["evaluation_space"],
        "training": (
            "reused matching 40,000-step Cityscapes checkpoint; "
            f"{target_iterations:,} RailSem19 steps"
            + (f"; retained evaluations at {milestone_text} and final" if milestone_text else "")
            if job["protocol"] == "cityscapes_to_railsem19"
            else "40,000 steps from pretrained weights"
        ),
        "source_checkpoint": public_dependency,
        "iteration_progress": _iteration_progress(
            plan,
            checkpoint_available=checkpoint_available,
            checkpoint_step=checkpoint_step,
        ),
        "resource_evidence": {},
        "evaluation": {
            "split": "val",
            "images": images,
            "weights": evaluation_weights,
            "sliding_window": [1024, 1024],
            "stride": [768, 768],
            "tta": False,
        },
        "seed_count": 0,
        "seeds": [],
        "aggregate": {},
        "support": {},
        "individual": [],
        "milestones": {},
        "derived_metrics": ["mprecision", "mdice", "mspecificity"],
        "derivation": (
            "Derived from each retained confusion matrix when absent; all other metrics "
            "come directly from validated result records."
        ),
        "caveats": caveats,
        **({"evaluation_correction": public_correction} if public_correction else {}),
    }


def _sanitised_performance(payload: dict[str, Any]) -> dict[str, Any]:
    latency = payload["measurements"]["latency"]
    source = payload["source"]
    contract = payload["contract"]
    return {
        "status": "complete",
        "fps": latency["fps"],
        "latency_ms": {
            "mean": latency["mean_ms"],
            "p50": latency["p50_ms"],
            "p95": latency["p95_ms"],
        },
        "peak_vram_bytes": payload["measurements"]["peak_reserved_bytes"],
        "peak_reserved_bytes": payload["measurements"]["peak_reserved_bytes"],
        "resident_parameter_bytes": payload["model"]["resident_parameter_bytes"],
        "parameter_dtype_counts": payload["model"]["parameter_dtype_counts"],
        "memory_kind": payload["measurements"]["memory_kind"],
        "note": (
            "Model-only public forward measured once from the RailSem19-only 21-class "
            f"{source['weights']} endpoint and linked across this model's quality protocols."
        ),
        "protocol": {
            "gpu_model": payload["hardware"]["gpu_name"],
            "backend": contract["backend"],
            "precision": contract["precision"],
            "input_shape_nchw": contract["input_shape_nchw"],
            "warmup_iterations": contract["warmup_iterations"],
            "measured_iterations": contract["measured_iterations"],
            "entrypoint": contract["entrypoint"],
        },
        "provenance": {
            "measured_job_id": source["measured_checkpoint_job_id"],
            "campaign_git_sha": source["campaign_git_sha"],
            "config_hash": source["config_hash"],
            "config_sha256": source["config_sha256"],
            "checkpoint_sha256": source["checkpoint_sha256"],
            "checkpoint_global_step": source["checkpoint_global_step"],
            "checkpoint_bytes": source["checkpoint_bytes"],
            "result_sha256": source["result_sha256"],
            "result_git_sha": source["result_git_sha"],
            "result_stage": source["result_stage"],
            "result_seed": source["result_seed"],
            "weights": source["weights"],
        },
    }


def _load_existing_records(root: Path) -> dict[str, dict[str, Any]]:
    directory = root / "docs/results/model-comparison/records"
    records: dict[str, dict[str, Any]] = {}
    for path in sorted(directory.glob("*.json")):
        record = _load_json_object(path)
        model_id = record.get("model_id")
        if not isinstance(model_id, str) or model_id in records:
            raise CampaignError(f"invalid or duplicate normalized record {path}")
        records[model_id] = record
    return records


def _is_trusted_weight_source_correction(
    protocol: dict[str, Any],
    existing: dict[str, Any],
    candidate: dict[str, Any],
    result: dict[str, Any],
    attempt: dict[str, Any],
) -> bool:
    """Admit only a provenance-identical EMA-to-raw BatchNorm correction."""
    existing_weights = protocol.get("evaluation", {}).get("weights")
    result_config = result.get("config")
    evaluation = result_config.get("evaluation") if isinstance(result_config, dict) else None
    candidate_weights = evaluation.get("weights") if isinstance(evaluation, dict) else None
    if str(existing_weights).lower() != "ema" or candidate_weights != "raw":
        return False
    if attempt.get("kind") != "reused" or attempt.get("record_kind") != "evaluation":
        return False
    if "raw-weight" not in str(attempt.get("caveat", "")).lower():
        return False
    source = existing.get("source")
    candidate_source = candidate.get("source")
    if not isinstance(source, dict) or not isinstance(candidate_source, dict):
        return False
    for key in ("git_sha", "checkpoint_sha256", "checkpoint_step"):
        if source.get(key) is None or candidate_source.get(key) != source.get(key):
            return False
    return bool(source.get("result_sha256")) and bool(candidate_source.get("result_sha256"))


def _is_trusted_bn_recalibration_correction(
    existing: dict[str, Any],
    candidate: dict[str, Any],
    result: dict[str, Any],
    attempt: dict[str, Any],
) -> bool:
    """Admit an explicit zero-parameter BatchNorm-buffer recalibration."""
    correction = attempt.get("evaluation_correction")
    if not isinstance(correction, dict):
        return False
    if correction.get("kind") != "batchnorm_running_statistics_recalibration":
        return False
    if correction.get("parameters_changed") != 0:
        return False
    for key in ("bn_modules", "recalibration_batches", "recalibration_images"):
        value = correction.get(key)
        if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            return False
    result_config = result.get("config")
    evaluation = result_config.get("evaluation") if isinstance(result_config, dict) else None
    if not isinstance(evaluation, dict) or evaluation.get("weights") != "raw":
        return False
    source = existing.get("source")
    candidate_source = candidate.get("source")
    existing_metrics = existing.get("metrics")
    candidate_metrics = candidate.get("metrics")
    if not all(
        isinstance(value, dict)
        for value in (source, candidate_source, existing_metrics, candidate_metrics)
    ):
        return False
    if source.get("git_sha") != candidate_source.get("git_sha"):
        return False
    if source.get("checkpoint_step") != candidate_source.get("checkpoint_step"):
        return False
    if source.get("checkpoint_sha256") != correction.get("source_checkpoint_sha256"):
        return False
    if source.get("result_sha256") != correction.get("source_result_sha256"):
        return False
    if candidate_source.get("checkpoint_sha256") != correction.get("corrected_checkpoint_sha256"):
        return False
    if candidate_source.get("result_sha256") != correction.get("corrected_result_sha256"):
        return False
    if attempt.get("sha256", {}).get("checkpoint") != candidate_source.get("checkpoint_sha256"):
        return False
    if attempt.get("sha256", {}).get("common_results") != candidate_source.get("result_sha256"):
        return False
    if not source.get("result_sha256") or not candidate_source.get("result_sha256"):
        return False
    if source.get("result_sha256") == candidate_source.get("result_sha256"):
        return False
    try:
        old_miou = float(existing_metrics["miou"])
        candidate_miou = float(candidate_metrics["miou"])
        correction_old_miou = float(correction["old_miou"])
        correction_new_miou = float(correction["corrected_miou"])
    except (KeyError, TypeError, ValueError):
        return False
    return math.isclose(old_miou, correction_old_miou, abs_tol=1e-12) and math.isclose(
        candidate_miou, correction_new_miou, abs_tol=1e-12
    )


def _comparison_records(
    publish_root: Path,
    manifest: CampaignManifest,
    cells: dict[str, tuple[dict[str, Any], dict[str, Any]]],
    campaign_record: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    records = _load_existing_records(publish_root)
    for existing in records.values():
        existing.pop("historical_protocols", None)
        existing.get("protocols", {}).pop("cityscapes_to_railsem19", None)
    by_model = {model.id: model for model in manifest.models}
    for job_id, (job, result) in sorted(cells.items()):
        if job.get("status") == "alias":
            continue
        attempt = job["attempts"][-1]
        model = by_model[job["model"]]
        record = records.setdefault(
            model.id,
            {
                "schema_version": 2,
                "model_id": model.id,
                "model_config": str(model.config),
                "status": "queued",
                "model_profile": {
                    "parameter_count": {"cityscapes19": None, "rail_union": None},
                    "standardized_inference": {
                        "status": "pending",
                        "fps": None,
                        "latency_ms": None,
                        "peak_vram_bytes": None,
                        "note": "Pending the fixed RailSem19-only model benchmark.",
                    },
                },
                "protocols": {},
            },
        )
        if record.get("schema_version") != 2:
            raise CampaignError(f"{model.id} normalized record is not schema version 2")
        if job["protocol"] == "cityscapes_to_railsem19":
            plan = _iteration_plan(result["config"])
            stage = plan["stages"][-1]
            if (
                plan["total_target_iterations"] != 20_000
                or stage["learning_rate_scale"] != 0.1
                or stage["head_group_learning_rate_scale"] != 1.0
            ):
                continue
        protocol = record["protocols"].get(job["protocol"])
        if protocol is None:
            protocol = _new_protocol(job, result, attempt)
            record["protocols"][job["protocol"]] = protocol
        existing_by_seed = {item["seed"]: item for item in protocol["individual"]}
        existing_seeds = set(existing_by_seed)
        if job["seed"] not in existing_seeds:
            previous_resources = copy.deepcopy(protocol.get("resource_evidence", {}))
            protocol["individual"].append(_normalised_individual(job, result, attempt))
            _aggregate_protocol(protocol)
            taxonomy_key = "cityscapes19" if job["protocol"] == "cityscapes" else "rail_union"
            parameter_count = record["model_profile"]["parameter_count"].get(taxonomy_key)
            protocol["resource_evidence"] = _protocol_resource_evidence(
                protocol["individual"], parameter_count=parameter_count
            )
            for key, value in previous_resources.items():
                if not protocol["resource_evidence"].get(key) and value:
                    protocol["resource_evidence"][key] = value
        else:
            candidate = _normalised_individual(job, result, attempt)
            existing = existing_by_seed[job["seed"]]
            if existing.get("metrics") != candidate.get("metrics"):
                trusted_correction = _is_trusted_weight_source_correction(
                    protocol, existing, candidate, result, attempt
                ) or _is_trusted_bn_recalibration_correction(existing, candidate, result, attempt)
                if not trusted_correction:
                    raise CampaignError(
                        f"normalized seed {job_id} conflicts with preserved public metrics"
                    )
                previous_resources = copy.deepcopy(protocol.get("resource_evidence", {}))
                protocol = _new_protocol(job, result, attempt)
                protocol["individual"].append(candidate)
                _aggregate_protocol(protocol)
                taxonomy_key = "cityscapes19" if job["protocol"] == "cityscapes" else "rail_union"
                parameter_count = record["model_profile"]["parameter_count"].get(taxonomy_key)
                protocol["resource_evidence"] = _protocol_resource_evidence(
                    protocol["individual"], parameter_count=parameter_count
                )
                for key, value in previous_resources.items():
                    if not protocol["resource_evidence"].get(key) and value:
                        protocol["resource_evidence"][key] = value
                record["protocols"][job["protocol"]] = protocol
                existing = candidate
            source = existing.get("source", {})
            candidate_source = candidate.get("source", {})
            for key in ("result_sha256", "git_sha", "checkpoint_sha256", "checkpoint_step"):
                if source.get(key) is not None and candidate_source.get(key) != source.get(key):
                    raise CampaignError(
                        f"normalized seed {job_id} conflicts with preserved {key} provenance"
                    )
        # A reused common-evaluation result can safely add full-pipeline timing
        # while preserving the historical normalized metric/provenance payload.
        if attempt.get("record_kind") == "evaluation":
            wall = result.get("wall_clock_s")
            images = result.get("dataset_sizes", {}).get("eval")
            if (
                isinstance(wall, int | float)
                and wall > 0
                and isinstance(images, int)
                and images > 0
            ):
                protocol.setdefault("resource_evidence", {})["full_validation_pipeline"] = {
                    "seed_count": 1,
                    "images": images,
                    "wall_clock_s_mean": float(wall),
                    "images_per_s_mean": images / float(wall),
                    "scope": "loader, sliding-window inference, and metrics",
                }
        if job.get("performance_owner"):
            paths, _ = _attempt_path_objects(attempt)
            if paths.get("performance", Path()).is_file():
                performance = validate_performance(
                    paths["performance"],
                    record=campaign_record,
                    job=job,
                    checkpoint=paths["checkpoint"],
                    common_results=paths["common_results"],
                    resolved_config=paths["config"],
                )
                record["model_profile"]["parameter_count"]["rail_union"] = performance["model"][
                    "parameter_count"
                ]
                record["model_profile"]["standardized_inference"] = _sanitised_performance(
                    performance
                )
                for protocol_id, protocol_record in record["protocols"].items():
                    if protocol_id != "cityscapes":
                        protocol_record["resource_evidence"]["parameter_count"] = performance[
                            "model"
                        ]["parameter_count"]
    # Performance validation needs the immutable campaign record; it is applied
    # in report_campaign after this preservation-first metric merge.
    for record in records.values():
        record["status"] = _model_record_status(record)
    # Synthesize aliases only after the canonical record is complete/partial.
    for model in manifest.models:
        if model.alias_of is None or model.alias_of not in records:
            continue
        alias = copy.deepcopy(records[model.alias_of])
        alias["model_id"] = model.id
        alias["model_config"] = str(model.config)
        alias["alias_of"] = model.alias_of
        alias["alias_provenance"] = (
            "No duplicate training or performance benchmark: this reviewed compatibility "
            "alias inherits the canonical SMP recipe's validated evidence."
        )
        records[model.id] = alias
    return records


def _number(value: object, *, decimals: int = 2) -> str:
    return (
        "—"
        if not isinstance(value, int | float) or isinstance(value, bool) or not math.isfinite(value)
        else f"{float(value):.{decimals}f}"
    )


def _scientific(value: object) -> str:
    if not isinstance(value, int | float) or isinstance(value, bool) or not math.isfinite(value):
        return "—"
    return f"{float(value):.1e}".replace("e-0", "e-").replace("e+0", "e+")


def _duration(value: object) -> str:
    if not isinstance(value, int | float) or isinstance(value, bool) or value < 0:
        return "—"
    seconds = round(float(value))
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours}h {minutes:02d}m {seconds:02d}s"


def _mib(value: object) -> str:
    return (
        "—" if not isinstance(value, int) or isinstance(value, bool) else f"{value / 2**20:.1f} MiB"
    )


def _gib(value: object) -> str:
    return (
        "—" if not isinstance(value, int) or isinstance(value, bool) else f"{value / 2**30:.2f} GiB"
    )


def _primary_protocols(record: dict[str, Any] | None) -> dict[str, Any]:
    """Return paper-primary raw protocols without discarding deployment endpoints."""
    if not isinstance(record, dict):
        return {}
    protocols = dict(record.get("protocols", {}))
    raw_overrides = record.get("paper_raw_protocols")
    if isinstance(raw_overrides, dict):
        for protocol_id, protocol in raw_overrides.items():
            baseline = protocols.get(protocol_id)
            baseline_hashes = (
                {
                    item.get("source", {}).get("checkpoint_sha256")
                    for item in baseline.get("individual", [])
                }
                if isinstance(baseline, dict)
                else set()
            )
            override_hashes = (
                {
                    item.get("source", {}).get("checkpoint_sha256")
                    for item in protocol.get("individual", [])
                }
                if isinstance(protocol, dict)
                else set()
            )
            if (
                protocol_id in REQUIRED_PROTOCOLS
                and isinstance(protocol, dict)
                and baseline_hashes
                and baseline_hashes == override_hashes
                and None not in baseline_hashes
            ):
                protocols[protocol_id] = protocol
    return protocols


def _record_metric(record: dict[str, Any], protocol: str, metric: str) -> object:
    return (
        _primary_protocols(record)
        .get(protocol, {})
        .get("aggregate", {})
        .get(metric, {})
        .get("mean")
    )


RAIL_MIOU_QUALITY_FLOOR = 0.60
RAIL_RECOMMENDATION_ACCURACY_WEIGHT = 0.85


def _competition_ranks(rows: list[dict[str, Any]], key: str) -> dict[str, int]:
    """Return 1-based descending ranks while assigning equal values equal ranks."""
    ordered = sorted(rows, key=lambda item: (-item[key], item["model"]))
    ranks: dict[str, int] = {}
    previous: float | None = None
    rank = 0
    for index, item in enumerate(ordered, start=1):
        value = item[key]
        if previous is None or value != previous:
            rank = index
            previous = value
        ranks[item["model"]] = rank
    return ranks


def _rail_accuracy_speed_leaderboard(
    manifest: CampaignManifest,
    records: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """List every shipped recipe, ranking rows with complete quality and speed evidence."""
    rows: list[dict[str, Any]] = []
    priority = {model_id: index for index, model_id in enumerate(manifest.priority_order)}
    for model in manifest.models:
        # An alias is a separately shipped recipe name but intentionally shares the
        # canonical model's weights and measurements. Keep it visible in the public
        # ranking while sourcing its evidence from the canonical record.
        record = records.get(model.alias_of or model.id)
        if not isinstance(record, dict):
            record = records.get(model.id, {})
        if not isinstance(record, dict):
            record = {}
        miou_value = _record_metric(record, "railsem19", "miou")
        miou = (
            float(miou_value)
            if isinstance(miou_value, int | float)
            and not isinstance(miou_value, bool)
            and math.isfinite(miou_value)
            and 0 < miou_value <= 1
            else None
        )
        inference_value = record.get("model_profile", {}).get("standardized_inference", {})
        inference = inference_value if isinstance(inference_value, dict) else {}
        fps = inference.get("fps")
        fps = (
            float(fps)
            if (
                isinstance(fps, int | float)
                and not isinstance(fps, bool)
                and math.isfinite(fps)
                and fps > 0
            )
            else None
        )
        complete = inference.get("status") == "complete" and miou is not None and fps is not None
        latency = inference.get("latency_ms") or {}
        rows.append(
            {
                "model": model.id,
                "alias_of": model.alias_of,
                "status": "complete" if complete else "pending",
                "miou": miou,
                "fps": fps,
                "p50_ms": latency.get("p50"),
                "weights": inference.get("provenance", {}).get("weights"),
                "resident_parameter_bytes": inference.get("resident_parameter_bytes"),
                "peak_vram_bytes": inference.get("peak_reserved_bytes")
                or inference.get("peak_vram_bytes"),
                "priority": priority.get(model.id, len(priority)),
            }
        )
    completed = [item for item in rows if item["status"] == "complete"]
    if completed:
        accuracy_ranks = _competition_ranks(completed, "miou")
        speed_ranks = _competition_ranks(completed, "fps")
        qualified = [item for item in completed if item["miou"] >= RAIL_MIOU_QUALITY_FLOOR]
        best_miou = max(item["miou"] for item in completed)
        best_qualified_fps = max(item["fps"] for item in qualified) if qualified else None
        for item in completed:
            item["accuracy_rank"] = accuracy_ranks[item["model"]]
            item["speed_rank"] = speed_ranks[item["model"]]
            item["quality_gate"] = (
                "qualified" if item["miou"] >= RAIL_MIOU_QUALITY_FLOOR else "below 60% mIoU"
            )
            if best_qualified_fps is None or item["quality_gate"] != "qualified":
                continue
            quality = item["miou"] / best_miou
            # Throughput has strongly diminishing practical value at high FPS. Log
            # scaling prevents an extremely fast but less accurate model from
            # overwhelming the recommendation score.
            speed = math.log1p(item["fps"]) / math.log1p(best_qualified_fps)
            accuracy_weight = RAIL_RECOMMENDATION_ACCURACY_WEIGHT
            item["recommendation_score"] = (
                100 * (quality**accuracy_weight) * (speed ** (1 - accuracy_weight))
            )
    rows.sort(
        key=lambda item: (
            item["status"] != "complete",
            item.get("quality_gate") != "qualified",
            -item.get("recommendation_score", -math.inf),
            -(item["miou"] if item["miou"] is not None else -math.inf),
            -(item["fps"] if item["fps"] is not None else -math.inf),
            item["priority"],
            item["model"],
        )
    )
    return rows


def _transfer_final(record: dict[str, Any] | None) -> dict[str, Any]:
    """Return only a verified 20k Rail adaptation result."""
    if not isinstance(record, dict):
        return {}
    transfer = _primary_protocols(record).get("cityscapes_to_railsem19")
    if not isinstance(transfer, dict):
        return {}
    progress = transfer.get("iteration_progress")
    if not isinstance(progress, dict):
        return {}
    verification = progress.get("final_verification")
    if not isinstance(verification, dict):
        return {}
    if (
        progress.get("target_iterations") != 20_000
        or progress.get("current_iterations") != 20_000
        or verification.get("result_verified") is not True
        or verification.get("result_total_iterations") != 20_000
        or verification.get("result_final_stage_iteration") != 20_000
    ):
        return {}
    return transfer


def _model_record_status(record: dict[str, Any]) -> str:
    protocols = _primary_protocols(record)
    if not protocols:
        return "queued"
    return (
        "complete"
        if all(protocol in protocols for protocol in ("cityscapes", "railsem19"))
        and bool(_transfer_final(record))
        else "running"
    )


def _recorded_evaluation_weights(protocol: dict[str, Any]) -> str | None:
    weights = protocol.get("evaluation", {}).get("weights")
    return weights if weights in ("raw", "ema") else None


def _cumulative_transfer_training(protocols: dict[str, Any]) -> dict[str, Any]:
    """Combine the reused City40 cost with the Rail20 adaptation cost when retained."""
    city = protocols.get("cityscapes", {}).get("resource_evidence", {}).get("training", {})
    adaptation = (
        protocols.get("cityscapes_to_railsem19", {})
        .get("resource_evidence", {})
        .get("training", {})
    )
    required = ("wall_clock_s_mean", "gpu_hours_mean")
    if any(
        not isinstance(row.get(key), int | float) for row in (city, adaptation) for key in required
    ):
        return {}
    peaks = [
        row.get("peak_vram_bytes_per_device")
        for row in (city, adaptation)
        if isinstance(row.get("peak_vram_bytes_per_device"), int)
    ]
    return {
        "wall_clock_s": city["wall_clock_s_mean"] + adaptation["wall_clock_s_mean"],
        "gpu_hours": city["gpu_hours_mean"] + adaptation["gpu_hours_mean"],
        "peak_vram_bytes_per_device": max(peaks) if len(peaks) == 2 else None,
        "iterations": 60_000,
        "scope": "reused City40 training plus Rail20 adaptation",
    }


def _model_generated_section(record: dict[str, Any]) -> str:
    protocols = _primary_protocols(record)
    visible_protocols = dict(protocols)
    if not _transfer_final(record):
        visible_protocols.pop("cityscapes_to_railsem19", None)
    uniform_raw = bool(visible_protocols) and all(
        _recorded_evaluation_weights(protocol) == "raw" for protocol in visible_protocols.values()
    )
    lines = [
        REPORT_START,
        "## Cityscapes and RailSem19 benchmark results",
        "",
        "Values are validated percentages, shown as one clean number. Detailed machine "
        "records retain every contributing seed. `—` means evidence is unavailable, not zero.",
        "Each quality cell is one retained seed (seed 0). It has no error bar and should not "
        "be used to claim that a sub-one-point difference is statistically meaningful.",
        *(
            ["All quality values use raw checkpoint weights under the uniform paper policy."]
            if uniform_raw
            else []
        ),
        "",
        "| protocol | iterations | mIoU | mean accuracy | mean precision | mean Dice | mean specificity | pixel accuracy | fwIoU | boundary F1 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    labels = {
        "cityscapes": "Cityscapes",
        "railsem19": "RailSem19",
        "cityscapes_to_railsem19": "Cityscapes → RailSem19",
    }
    for protocol_id in REQUIRED_PROTOCOLS:
        protocol = visible_protocols.get(protocol_id)
        if not isinstance(protocol, dict):
            progress = _empty_progress(protocol_id)
            values = [labels[protocol_id], f"0 / {progress['target_iterations']:,}", *(["—"] * 8)]
            lines.append("| " + " | ".join(values) + " |")
            continue
        progress = protocol["iteration_progress"]
        metrics = protocol["aggregate"]
        values = [
            labels[protocol_id],
            f"{progress['current_iterations']:,} / {progress['target_iterations']:,}",
            *[
                _number(metrics[key]["mean"] * 100 if metrics[key]["mean"] is not None else None)
                for key, _ in RECORD_METRICS
            ],
        ]
        lines.append("| " + " | ".join(values) + " |")

    performance = record.get("model_profile", {}).get("standardized_inference", {})
    latency = performance.get("latency_ms") or {}
    performance_weights = performance.get("provenance", {}).get("weights")
    performance_endpoint = (
        f"{performance_weights} endpoint"
        if performance_weights in ("raw", "ema")
        else "recorded raw/EMA endpoint"
    )
    lines.extend(
        [
            "",
            "### Standardized model-only inference",
            "",
            (
                f"Measured once from this model's RailSem19-only 21-class {performance_endpoint} on an "
                if performance.get("status") == "complete"
                else "Pending one measurement from this model's RailSem19-only 21-class recorded raw/EMA endpoint on an "
            )
            + "NVIDIA L40S: PyTorch eager public forward, BF16 autocast, batch 1, 1024x1024, "
            "20 warmup and 100 CUDA-event-timed iterations. It includes all model-internal "
            "conversion to dense logits, including query collapse where applicable, and "
            "excludes I/O, preprocessing, sliding windows, argmax, and metrics.",
            "",
            "| parameters (Rail 21-class) | model weight memory | resume checkpoint | FPS | p50 | p95 | peak inference VRAM (reserved, excl. context) |",
            "|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    rail = protocols.get("railsem19", {})
    resource = rail.get("resource_evidence", {}) if isinstance(rail, dict) else {}
    checkpoint = resource.get("final_checkpoint", {})
    lines.append(
        "| "
        + " | ".join(
            [
                (
                    f"{resource['parameter_count']:,}"
                    if isinstance(resource.get("parameter_count"), int)
                    else "—"
                ),
                _mib(performance.get("resident_parameter_bytes")),
                _mib(checkpoint.get("size_bytes")),
                _number(performance.get("fps")),
                f"{_number(latency.get('p50'))} ms" if latency else "—",
                f"{_number(latency.get('p95'))} ms" if latency else "—",
                _gib(performance.get("peak_reserved_bytes")),
            ]
        )
        + " |"
    )

    lines.extend(
        [
            "",
            "### Training and full-pipeline evaluation cost",
            "",
            "Standalone rows report their own training cost. The transfer adaptation row reports "
            "only Rail20 because it reuses City40; the cumulative row adds the retained City40 "
            "and Rail20 costs. Peak training VRAM is the maximum per-device allocator-reserved "
            "high-water mark. Full-pipeline throughput includes the loader, sliding-window "
            "inference, and metrics.",
            "",
            "| protocol | cost scope | train wall / run | GPU-hours / run | peak train VRAM / GPU | full validation images/s |",
            "|---|---|---:|---:|---:|---:|",
        ]
    )
    scopes = {
        "cityscapes": "City40 standalone",
        "railsem19": "Rail40 standalone",
        "cityscapes_to_railsem19": "Rail20 adaptation only; excludes reused City40",
    }
    for protocol_id in REQUIRED_PROTOCOLS:
        protocol = visible_protocols.get(protocol_id)
        evidence = protocol.get("resource_evidence", {}) if isinstance(protocol, dict) else {}
        training = evidence.get("training", {})
        pipeline = evidence.get("full_validation_pipeline", {})
        retained_training = training.get("wall_clock_s_mean") is not None
        missing_training = "not retained" if isinstance(protocol, dict) else "—"
        lines.append(
            f"| {labels[protocol_id]} | {scopes[protocol_id]} | "
            f"{_duration(training.get('wall_clock_s_mean')) if retained_training else missing_training} | "
            f"{_number(training.get('gpu_hours_mean')) if retained_training else missing_training} | "
            f"{_gib(training.get('peak_vram_bytes_per_device')) if retained_training else missing_training} | "
            f"{_number(pipeline.get('images_per_s_mean'), decimals=3)} |"
        )
    cumulative = _cumulative_transfer_training(visible_protocols)
    cumulative_available = bool(cumulative)
    lines.append(
        "| Cityscapes → RailSem19, cumulative | City40 training + Rail20 adaptation | "
        f"{_duration(cumulative.get('wall_clock_s')) if cumulative_available else 'not retained'} | "
        f"{_number(cumulative.get('gpu_hours')) if cumulative_available else 'not retained'} | "
        f"{_gib(cumulative.get('peak_vram_bytes_per_device')) if cumulative_available else 'not retained'} | — |"
    )
    if any(
        isinstance(visible_protocols.get(protocol_id), dict)
        and visible_protocols[protocol_id]
        .get("resource_evidence", {})
        .get("training", {})
        .get("wall_clock_s_mean")
        is None
        for protocol_id in REQUIRED_PROTOCOLS
    ):
        lines.extend(
            [
                "",
                "`not retained` means the exact original training-duration record is no "
                "longer available. The validated quality result, final checkpoint, iteration "
                "count, and inference evidence are still complete; the model is not retrained "
                "only to recreate timing metadata.",
            ]
        )

    city = visible_protocols.get("cityscapes")
    if isinstance(city, dict):
        lines.extend(["", "### Cityscapes class IoU", "", "| class | IoU |", "|---|---:|"])
        for name, summary in city["aggregate"]["per_class_iou"].items():
            value = summary["mean"]
            lines.append(f"| {name} | {_number(value * 100 if value is not None else None)} |")
    rail = visible_protocols.get("railsem19")
    transfer = _transfer_final(record) or None
    if isinstance(rail, dict) or isinstance(transfer, dict):
        source = rail or transfer
        lines.extend(
            [
                "",
                "### RailSem19 class IoU",
                "",
                "| class | RailSem19 | Cityscapes → RailSem19 |",
                "|---|---:|---:|",
            ]
        )
        for name in source["aggregate"]["per_class_iou"]:
            left = rail["aggregate"]["per_class_iou"][name]["mean"] if rail else None
            right = transfer["aggregate"]["per_class_iou"][name]["mean"] if transfer else None
            lines.append(
                f"| {name} | {_number(left * 100 if left is not None else None)} | "
                f"{_number(right * 100 if right is not None else None)} |"
            )
    revisions = sorted(
        {
            individual["source"]["git_sha"]
            for protocol in visible_protocols.values()
            for individual in protocol["individual"]
        }
    )
    caveats = sorted(
        {
            caveat
            for protocol in visible_protocols.values()
            for caveat in protocol.get("caveats", [])
        }
    )
    retained_seeds = "; ".join(
        f"{labels[protocol_id]}: {', '.join(map(str, protocol['seeds']))}"
        for protocol_id, protocol in visible_protocols.items()
        if protocol_id in labels and protocol.get("seeds")
    )
    derivations = sorted(
        {
            protocol.get("derivation")
            for protocol in visible_protocols.values()
            if isinstance(protocol.get("derivation"), str)
        }
    )
    evaluation_weights = "; ".join(
        f"{labels[protocol_id]}: {_recorded_evaluation_weights(protocol) or '—'}"
        for protocol_id, protocol in visible_protocols.items()
        if protocol_id in labels
    )
    lines.extend(
        [
            "",
            "### Provenance",
            "",
            f"- Model recipe: `{record['model_config']}`",
            f"- Source revisions: `{', '.join(revisions)}`",
            f"- Retained seeds: {retained_seeds or 'none yet'}.",
            f"- Quality evaluation weights: {evaluation_weights or 'none yet'}.",
            "- Evaluation uses 1024x1024 sliding windows, stride 768, and no TTA.",
            *(f"- Metric derivation: {derivation}" for derivation in derivations),
            *(f"- Caveat: {caveat}" for caveat in caveats),
            "",
            REPORT_END,
        ]
    )
    return "\n".join(lines)


def _replace_generated_section(original: str, section: str) -> str:
    starts = original.count(REPORT_START)
    ends = original.count(REPORT_END)
    if starts != ends or starts > 1:
        raise CampaignError("README contains malformed or duplicate generated benchmark markers")
    if starts == 0:
        return original.rstrip() + "\n\n" + section + "\n"
    before, remainder = original.split(REPORT_START, 1)
    _, after = remainder.split(REPORT_END, 1)
    return before.rstrip() + "\n\n" + section + after.rstrip() + "\n"


def _empty_progress(protocol_id: str) -> dict[str, Any]:
    targets = {
        "cityscapes": [("cityscapes", "Cityscapes", 40_000)],
        "railsem19": [("railsem19", "RailSem19", 40_000)],
        "cityscapes_to_railsem19": [
            ("railsem19", "RailSem19 adaptation", 20_000),
        ],
    }[protocol_id]
    total = sum(item[2] for item in targets)
    return {
        "target_iterations": total,
        "current_iterations": 0,
        "stages": [
            {
                "stage": stage,
                "dataset": dataset,
                "target_iterations": target,
                "current_iterations": 0,
            }
            for stage, dataset, target in targets
        ],
        "final_verification": {
            "result_verified": False,
            "result_total_iterations": None,
            "result_final_stage_iteration": None,
            "checkpoint_available": False,
            "checkpoint_verified": False,
            "checkpoint_global_step": None,
        },
    }


def _status_label(record: dict[str, Any] | None, model: ModelSpec) -> str:
    if record is None:
        return "queued"
    return _model_record_status(record)


def _model_execution_states(campaign_record: dict[str, Any] | None) -> dict[str, str]:
    if campaign_record is None:
        return {}
    raw: dict[str, list[str]] = defaultdict(list)
    campaign = Path(campaign_record["campaign"])
    for lane in campaign_record["lanes"]:
        status = _load_json_object(_status_path(campaign, lane["id"]))
        for job in status.get("jobs", []):
            if isinstance(job, dict):
                raw[str(job.get("model"))].append(str(job.get("status")))
    failed = {
        "train_failed",
        "train_artifact_failed",
        "eval_failed",
        "eval_artifact_failed",
        "performance_failed",
        "performance_artifact_failed",
        "provenance_failed",
    }
    active = {"training", "evaluating", "benchmarking"}
    completed = {"succeeded", "reused"}
    output = {}
    for model, states in raw.items():
        output[model] = (
            "failed"
            if any(state in failed for state in states)
            else "running"
            if any(state in active | completed for state in states)
            else "queued"
        )
    return output


def _model_training_specifications(
    manifest: CampaignManifest,
    campaign_record: dict[str, Any] | None,
) -> dict[str, dict[str, Any]]:
    """Resolve the exact planned City-stage runtime contract for every model.

    Runtime batch/worker overrides live in ``campaign.json`` while crop, learning
    rate, LLRD, precision, EMA, cadence, and objective semantics are layered from
    the committed configuration files.  Reusing ``_resolved_config`` keeps the
    public comparison synchronized with the configuration actually launched.
    """

    if campaign_record is None:
        return {}
    city_jobs = {
        str(job["model"]): job
        for job in campaign_record["jobs"]
        if job.get("protocol") == "cityscapes"
    }
    specifications: dict[str, dict[str, Any]] = {}
    prototype_root = Path(campaign_record["campaign"]) / ".report-training-specification"
    for model in manifest.models:
        owner = model.alias_of or model.id
        job = city_jobs.get(owner)
        if job is None:
            raise CampaignError(f"campaign is missing the Cityscapes specification for {owner}")
        config, _ = _resolved_config(
            campaign_record,
            job,
            prototype_root / model.id,
        )
        objective = "hungarian_query" if config.loss.query is not None else "dense_semantic"
        specifications[model.id] = {
            "gpu_count": 1,
            "crop_height": config.aug.crop[0],
            "crop_width": config.aug.crop[1],
            "batch_size_per_gpu": config.train.batch_size,
            "gradient_accumulation": config.train.accum,
            "effective_batch_size": config.train.batch_size * config.train.accum,
            "train_workers": config.train.num_workers,
            "precision": config.train.precision,
            "optimizer": "AdamW",
            "backbone_lr": config.optim.backbone_lr,
            "fresh_component_lr": config.optim.backbone_lr * config.optim.head_lr_mult,
            "head_lr_multiplier": config.optim.head_lr_mult,
            "weight_decay": config.optim.weight_decay,
            "betas": list(config.optim.betas),
            "llrd": config.optim.llrd,
            "warmup_iterations": config.optim.warmup_iters,
            "warmup_ratio": config.optim.warmup_ratio,
            "poly_power": config.optim.poly_power,
            "gradient_clip": config.optim.grad_clip,
            "ema_decay": config.train.ema_decay,
            "validation_interval": config.train.val_every,
            "checkpoint_interval": config.train.ckpt_every,
            "objective": objective,
        }
    return specifications


def _comparison_status(
    manifest: CampaignManifest,
    records: dict[str, dict[str, Any]],
    campaign_record: dict[str, Any] | None = None,
) -> dict[str, Any]:
    execution_states = _model_execution_states(campaign_record)
    training_specifications = _model_training_specifications(manifest, campaign_record)
    expected_performance = sum(model.alias_of is None for model in manifest.models)
    completed_performance = sum(
        record.get("model_profile", {}).get("standardized_inference", {}).get("status")
        == "complete"
        for model_id, record in records.items()
        if not next(item for item in manifest.models if item.id == model_id).alias_of
    )
    rows = []
    complete_cells = 0
    for priority, model_id in enumerate(manifest.priority_order, start=1):
        model = next(item for item in manifest.models if item.id == model_id)
        record = records.get(model_id)
        protocols = _primary_protocols(record)
        if record and not _transfer_final(record):
            protocols.pop("cityscapes_to_railsem19", None)
        complete_cells += len(protocols)
        progress = {
            protocol_id: (
                protocols[protocol_id]["iteration_progress"]
                if protocol_id in protocols
                else _empty_progress(protocol_id)
            )
            for protocol_id in REQUIRED_PROTOCOLS
        }
        profile = record.get("model_profile", {}) if record else {}
        inference = profile.get("standardized_inference") or {
            "status": "pending",
            "fps": None,
            "latency_ms": None,
            "peak_vram_bytes": None,
        }
        canonical_state = execution_states.get(model.alias_of or model_id, "queued")
        public_status = (
            "complete"
            if all(protocol in protocols for protocol in REQUIRED_PROTOCOLS)
            else canonical_state
            if canonical_state in {"queued", "running", "failed"}
            else "running"
        )
        rows.append(
            {
                "priority": priority,
                "model": model_id,
                "status": public_status,
                "result_origin": (
                    "alias"
                    if model.alias_of
                    else "reused"
                    if model.id == "segformer_b2"
                    else "trained"
                ),
                "alias_of": model.alias_of,
                **{
                    f"{protocol_id}_miou": (
                        _percent([_record_metric(record, protocol_id, "miou")])
                        if record and protocol_id in protocols
                        else "—"
                    )
                    for protocol_id in REQUIRED_PROTOCOLS
                },
                "iteration_progress": progress,
                "parameter_count": profile.get("parameter_count", {}),
                "standardized_inference": inference,
                "training_specification": training_specifications.get(model_id, {}),
            }
        )
    specifications = list(training_specifications.values())
    precisions = sorted({str(item["precision"]) for item in specifications})
    effective_batches = sorted({int(item["effective_batch_size"]) for item in specifications})
    train_workers = sorted({int(item["train_workers"]) for item in specifications})
    return {
        "schema_version": 2,
        "scope": {
            "model_recipes": len(manifest.models),
            "unique_training_choices": sum(model.alias_of is None for model in manifest.models),
            "protocols": list(REQUIRED_PROTOCOLS),
            "protocol_targets": {
                protocol: {
                    "target_iterations": _empty_progress(protocol)["target_iterations"],
                    "stages": [
                        {
                            "stage": item["stage"],
                            "dataset": item["dataset"],
                            "target_iterations": item["target_iterations"],
                        }
                        for item in _empty_progress(protocol)["stages"]
                    ],
                }
                for protocol in REQUIRED_PROTOCOLS
            },
            "seed_policy": "missing cells use seed 0; compatible retained seeds are preserved",
            "training": {
                "hardware": "one NVIDIA L40S per physical job",
                "gpu_count_per_job": 1,
                "seeds": (
                    list(campaign_record["execution"]["seeds"])
                    if campaign_record is not None
                    else []
                ),
                "deterministic_algorithms": (
                    bool(campaign_record["execution"]["deterministic"])
                    if campaign_record is not None
                    else None
                ),
                "precisions": precisions,
                "effective_batch_sizes": effective_batches,
                "train_workers": train_workers,
                "optimizer": "AdamW",
                "schedule": "linear warmup followed by per-iteration polynomial decay",
                "augmentation": (
                    "random scale 0.5-2.0, crop, horizontal flip p=0.5, and color jitter p=0.5"
                ),
                "dense_objective": (
                    "standalone Cityscapes CE; RailSem19-only and transfer adaptation "
                    "CE + 0.5 Lovasz"
                ),
                "query_objective": (
                    "Hungarian class/mask assignment with class/mask-BCE/Dice weights 2/5/5 "
                    "and 8,192 matching points"
                ),
                "transfer": (
                    "reuse the matching 40,000-iteration Cityscapes checkpoint, reset only "
                    "the incompatible classifier, and train RailSem19 for 20,000 iterations; "
                    "use 0.1x for backbone groups and 1.0x for model-declared head groups; "
                    "retain the final common evaluation at Rail 20,000"
                ),
                "evaluation": (
                    "paper-primary raw checkpoint weights for every model, batch 1, "
                    "1024x1024 sliding window, stride 768, no TTA"
                ),
                "resume_policy": (
                    campaign_record["execution"]["resume_policy"]
                    if campaign_record is not None
                    else None
                ),
            },
            "standardized_inference": {
                "status": (
                    "complete"
                    if completed_performance == expected_performance
                    else "running"
                    if completed_performance
                    else "queued"
                ),
                "owner": (
                    "RailSem19-only 21-class recorded endpoint, seed 0; raw for running-stat "
                    "BatchNorm and EMA otherwise"
                ),
                "contract": "L40S, PyTorch eager BF16, batch 1, 1024x1024, 20 warmup, 100 timed",
            },
        },
        "counts": {
            "complete_cells": complete_cells,
            "reported_cells": complete_cells,
            "complete_models": sum(
                record.get("status") == "complete" for record in records.values()
            ),
            "total_reported_cells": len(manifest.models) * len(REQUIRED_PROTOCOLS),
            "physical_training_cells": sum(model.alias_of is None for model in manifest.models)
            * len(REQUIRED_PROTOCOLS),
            "physical_performance_benchmarks": sum(
                model.alias_of is None for model in manifest.models
            ),
            "complete_performance_benchmarks": completed_performance,
        },
        "models": rows,
    }


def _comparison_csv(status: dict[str, Any], records: dict[str, dict[str, Any]]) -> str:
    protocol_columns = []
    for protocol in REQUIRED_PROTOCOLS:
        protocol_columns.extend(
            [
                f"{protocol}_miou_mean",
                f"{protocol}_evaluation_weights",
                f"{protocol}_seeds",
                f"{protocol}_iterations_current",
                f"{protocol}_iterations_target",
                f"{protocol}_parameters",
                f"{protocol}_final_checkpoint_bytes",
                f"{protocol}_train_wall_clock_s_mean",
                f"{protocol}_gpu_hours_mean",
                f"{protocol}_train_peak_vram_bytes_per_device",
                f"{protocol}_full_validation_images_per_s_mean",
            ]
        )
    fields = [
        "priority",
        "model",
        "status",
        "training_crop_height",
        "training_crop_width",
        "training_gpu_count",
        "training_batch_size_per_gpu",
        "training_gradient_accumulation",
        "training_effective_batch_size",
        "training_workers",
        "training_precision",
        "training_optimizer",
        "training_backbone_lr",
        "training_fresh_component_lr",
        "training_head_lr_multiplier",
        "training_weight_decay",
        "training_llrd",
        "training_warmup_iterations",
        "training_warmup_ratio",
        "training_poly_power",
        "training_gradient_clip",
        "training_ema_decay",
        "training_validation_interval",
        "training_checkpoint_interval",
        "training_objective",
        *protocol_columns,
        "cityscapes_to_railsem19_training_cost_scope",
        "cityscapes_to_railsem19_cumulative_iterations",
        "cityscapes_to_railsem19_cumulative_wall_clock_s",
        "cityscapes_to_railsem19_cumulative_gpu_hours",
        "cityscapes_to_railsem19_cumulative_peak_vram_bytes_per_device",
        "standardized_inference_fps",
        "standardized_inference_resident_parameter_bytes",
        "standardized_inference_latency_ms",
        "standardized_inference_latency_p50_ms",
        "standardized_inference_latency_p95_ms",
        "standardized_inference_peak_vram_bytes",
        "standardized_inference_status",
    ]
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    for row in status["models"]:
        record = records.get(row["model"])
        protocols = _primary_protocols(record)
        if not _transfer_final(record):
            protocols.pop("cityscapes_to_railsem19", None)
        output: dict[str, Any] = {
            "priority": row["priority"],
            "model": row["model"],
            "status": row["status"],
        }
        training = row.get("training_specification", {})
        output.update(
            {
                "training_crop_height": training.get("crop_height", ""),
                "training_crop_width": training.get("crop_width", ""),
                "training_gpu_count": training.get("gpu_count", ""),
                "training_batch_size_per_gpu": training.get("batch_size_per_gpu", ""),
                "training_gradient_accumulation": training.get("gradient_accumulation", ""),
                "training_effective_batch_size": training.get("effective_batch_size", ""),
                "training_workers": training.get("train_workers", ""),
                "training_precision": training.get("precision", ""),
                "training_optimizer": training.get("optimizer", ""),
                "training_backbone_lr": training.get("backbone_lr", ""),
                "training_fresh_component_lr": training.get("fresh_component_lr", ""),
                "training_head_lr_multiplier": training.get("head_lr_multiplier", ""),
                "training_weight_decay": training.get("weight_decay", ""),
                "training_llrd": training.get("llrd", ""),
                "training_warmup_iterations": training.get("warmup_iterations", ""),
                "training_warmup_ratio": training.get("warmup_ratio", ""),
                "training_poly_power": training.get("poly_power", ""),
                "training_gradient_clip": training.get("gradient_clip", ""),
                "training_ema_decay": training.get("ema_decay", ""),
                "training_validation_interval": training.get("validation_interval", ""),
                "training_checkpoint_interval": training.get("checkpoint_interval", ""),
                "training_objective": training.get("objective", ""),
            }
        )
        for protocol_id in REQUIRED_PROTOCOLS:
            protocol = protocols.get(protocol_id)
            progress = row["iteration_progress"][protocol_id]
            resource = protocol.get("resource_evidence", {}) if protocol else {}
            training = resource.get("training", {})
            pipeline = resource.get("full_validation_pipeline", {})
            checkpoint = resource.get("final_checkpoint", {})
            output.update(
                {
                    f"{protocol_id}_miou_mean": (
                        protocol["aggregate"]["miou"]["mean"] if protocol else ""
                    ),
                    f"{protocol_id}_evaluation_weights": (
                        _recorded_evaluation_weights(protocol) if protocol else ""
                    ),
                    f"{protocol_id}_seeds": protocol["seed_count"] if protocol else 0,
                    f"{protocol_id}_iterations_current": progress["current_iterations"],
                    f"{protocol_id}_iterations_target": progress["target_iterations"],
                    f"{protocol_id}_parameters": resource.get("parameter_count") or "",
                    f"{protocol_id}_final_checkpoint_bytes": checkpoint.get("size_bytes") or "",
                    f"{protocol_id}_train_wall_clock_s_mean": training.get("wall_clock_s_mean")
                    or "",
                    f"{protocol_id}_gpu_hours_mean": training.get("gpu_hours_mean") or "",
                    f"{protocol_id}_train_peak_vram_bytes_per_device": training.get(
                        "peak_vram_bytes_per_device"
                    )
                    or "",
                    f"{protocol_id}_full_validation_images_per_s_mean": pipeline.get(
                        "images_per_s_mean"
                    )
                    or "",
                }
            )
        cumulative = _cumulative_transfer_training(protocols)
        output.update(
            {
                "cityscapes_to_railsem19_training_cost_scope": (
                    "Rail20 adaptation only; excludes reused City40"
                ),
                "cityscapes_to_railsem19_cumulative_iterations": 60_000,
                "cityscapes_to_railsem19_cumulative_wall_clock_s": cumulative.get(
                    "wall_clock_s", ""
                ),
                "cityscapes_to_railsem19_cumulative_gpu_hours": cumulative.get("gpu_hours", ""),
                "cityscapes_to_railsem19_cumulative_peak_vram_bytes_per_device": cumulative.get(
                    "peak_vram_bytes_per_device", ""
                ),
            }
        )
        inference = row["standardized_inference"]
        latency = inference.get("latency_ms") or {}
        output.update(
            {
                "standardized_inference_fps": inference.get("fps") or "",
                "standardized_inference_resident_parameter_bytes": inference.get(
                    "resident_parameter_bytes"
                )
                or "",
                "standardized_inference_latency_ms": latency.get("mean") or "",
                "standardized_inference_latency_p50_ms": latency.get("p50") or "",
                "standardized_inference_latency_p95_ms": latency.get("p95") or "",
                "standardized_inference_peak_vram_bytes": inference.get("peak_reserved_bytes")
                or inference.get("peak_vram_bytes")
                or "",
                "standardized_inference_status": inference.get("status", "pending"),
            }
        )
        writer.writerow(output)
    value = stream.getvalue()
    if "sample_std" in value or "±" in value:
        raise CampaignError("human-facing CSV accidentally includes dispersion display")
    return value


def _central_readme(
    manifest: CampaignManifest,
    status: dict[str, Any],
    records: dict[str, dict[str, Any]],
    source_sha: str,
) -> str:
    models = {model.id: model for model in manifest.models}
    training_contract = status["scope"]["training"]
    seeds = ", ".join(str(seed) for seed in training_contract["seeds"])
    deterministic = (
        "forced"
        if training_contract["deterministic_algorithms"]
        else "not forced; fixed seeds and full provenance are retained"
    )
    performance_complete = (
        status.get("counts", {}).get("complete_performance_benchmarks")
        == status.get("counts", {}).get("physical_performance_benchmarks")
        and status.get("counts", {}).get("physical_performance_benchmarks", 0) > 0
    )
    performance_note = (
        "All unique physical models now have the standardized inference benchmark."
        if performance_complete
        else "During an active campaign, FPS can remain pending while Cityscapes mIoU is already available."
    )
    lines = [
        "# Model comparison: Cityscapes and RailSem19",
        "",
        "This live comparison covers every shipped model recipe. Compatible results are reused "
        "instead of retrained. `—` means evidence is unavailable, not zero or failure. Quality "
        "tables use raw checkpoint weights for every model and show one clean value; individual "
        "seeds remain in machine records. The separate [raw versus EMA analysis](RAW_VS_EMA.md) "
        "quantifies cells that were also evaluated with EMA weights.",
        "",
        "## How to read the labels",
        "",
        "- **Complete:** all required quality and inference evidence exists. Some complete "
        "results were verified as compatible and reused instead of retrained, avoiding "
        "unnecessary compute and electricity while retaining result and checkpoint provenance.",
        "- **Not retained:** only the exact original training-duration or GPU-hour record is "
        "no longer available. The quality result, final checkpoint, iteration count, and "
        "inference evidence remain complete; the model is not retrained solely to recreate "
        "timing metadata.",
        "- **Not eligible:** the model completed successfully and its results are valid, but "
        "its RailSem19 mIoU is below the leaderboard's 60% quality floor. Its raw accuracy "
        "and speed remain visible, but it receives no recommendation score.",
        "",
        "## Training specification",
        "",
        "These are the resolved settings used by this campaign, not generic model defaults. "
        "Each physical job occupies one L40S and performs one optimizer update after the "
        "listed number of accumulated micro-batches.",
        "",
        "| aspect | campaign setting |",
        "|---|---|",
        f"| GPU topology | {training_contract['hardware']} |",
        f"| seed and determinism | seed {seeds}; deterministic algorithms {deterministic} |",
        f"| precision | {', '.join(training_contract['precisions'])} |",
        f"| input pipeline | {', '.join(str(value) for value in training_contract['train_workers'])} "
        "CPU data-loader workers per job; model-specific crop and batching are below |",
        "| optimizer | AdamW, betas 0.9/0.999, weight decay 0.05; backbone LR and "
        "layer-wise decay are model-specific below; fresh task components use 10x LR |",
        "| LR schedule | 1,500-iteration linear warmup from ratio 1e-6, then per-iteration "
        "polynomial decay with power 0.9; gradient clipping 1.0 |",
        "| EMA and cadence | EMA decay 0.9998; validation and periodic checkpoint every "
        "4,000 optimizer iterations |",
        f"| augmentation | {training_contract['augmentation']}; crop size is model-specific below |",
        f"| dense objectives | {training_contract['dense_objective']} |",
        f"| EoMT query objective | {training_contract['query_objective']} |",
        "| protocol budgets | Cityscapes 40,000; RailSem19 40,000; transfer reuses City40 "
        "and trains RailSem19 for 20,000 iterations (60,000 cumulative) |",
        f"| transfer initialization | {training_contract['transfer']} |",
        f"| interruption recovery | {training_contract['resume_policy']} |",
        f"| final quality evaluation | {training_contract['evaluation']} |",
        "",
        "### Model-specific optimizer and batching settings",
        "",
        "The fresh-component LR is the initial LR for newly initialized heads or adapters. "
        "Transfer adaptation applies 0.1x to backbone groups and 1.0x to the "
        "model-declared decoder/head groups.",
        "",
        "| model | train crop | batch/GPU | accumulation | effective batch | backbone LR | fresh-component LR | LLRD | objective |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for row in status["models"]:
        model = models[row["model"]]
        link = "../../" + str(model.readme).removeprefix("docs/")
        spec = row["training_specification"]
        objective = (
            "Hungarian query" if spec["objective"] == "hungarian_query" else "dense semantic"
        )
        lines.append(
            f"| [{row['model']}]({link}) | {spec['crop_height']}x{spec['crop_width']} | "
            f"{spec['batch_size_per_gpu']} | {spec['gradient_accumulation']} | "
            f"{spec['effective_batch_size']} | {_scientific(spec['backbone_lr'])} | "
            f"{_scientific(spec['fresh_component_lr'])} | "
            f"{_number(spec['llrd'], decimals=2)} | {objective} |"
        )
    lines.extend(
        [
            "",
            "## Quality",
            "",
            "Every quality value below uses raw checkpoint weights. This uniform paper policy "
            "avoids architecture-dependent endpoint selection.",
            "All 111 quality cells use seed 0. A single-seed value has no error bar, so rankings "
            "and sub-one-point differences are descriptive and are not claims of statistical "
            "significance.",
            "The imported Hugging Face MobileNetV2 recipe required a documented training-split "
            "BatchNorm running-statistics recalibration after an upstream momentum-convention "
            "error; no learned parameter or validation image was used by that correction.",
            "",
            "| priority | model | status | City mIoU (40k) | Rail mIoU (40k) | City → Rail mIoU (Rail20 / total60) |",
            "|---:|---|---|---:|---:|---:|",
        ]
    )
    for row in status["models"]:
        model = models[row["model"]]
        link = "../../" + str(model.readme).removeprefix("docs/")
        values = [
            row["cityscapes_miou"],
            row["railsem19_miou"],
            row["cityscapes_to_railsem19_miou"],
        ]
        lines.append(
            f"| {row['priority']} | [{row['model']}]({link}) | {row['status']} | "
            + " | ".join(values)
            + " |"
        )
    lines.extend(
        [
            "",
            "## Standardized model-only inference",
            "",
            "Each unique physical model is measured exactly once from its RailSem19-only "
            "21-class recorded final endpoint (raw for running-stat BatchNorm; EMA otherwise). "
            "Raw and EMA weights have the same graph and tensor shapes, so this standardized "
            "speed and memory evidence remains comparable while the quality table is raw-only. "
            "Contract: NVIDIA L40S, PyTorch eager public "
            "forward, BF16 autocast, batch 1, 1024x1024, 20 warmup and 100 CUDA-event-timed "
            "iterations. It includes internal query-to-dense collapse and excludes I/O, "
            "preprocessing, sliding windows, argmax, and metrics.",
            performance_note,
            "",
            "Weight memory is the resident parameter tensors; the resume checkpoint also "
            "contains optimizer and EMA state; peak VRAM is allocator-reserved memory excluding "
            "the CUDA context.",
            "",
            "| model | weights | parameters (Rail 21-class) | model weight memory | resume checkpoint | FPS | p50 | p95 | peak VRAM (reserved, excl. context) |",
            "|---|---|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for row in status["models"]:
        record = records.get(row["model"])
        protocols = _primary_protocols(record)
        rail = protocols.get("railsem19", {})
        resource = rail.get("resource_evidence", {}) if isinstance(rail, dict) else {}
        checkpoint = resource.get("final_checkpoint", {})
        inference = row["standardized_inference"]
        latency = inference.get("latency_ms") or {}
        inference_weights = inference.get("provenance", {}).get("weights")
        weights_text = inference_weights if inference_weights in ("raw", "ema") else "—"
        link = "../../" + str(models[row["model"]].readme).removeprefix("docs/")
        parameter_count = resource.get("parameter_count")
        parameter_text = f"{parameter_count:,}" if isinstance(parameter_count, int) else "—"
        lines.append(
            f"| [{row['model']}]({link}) | {weights_text} | "
            f"{parameter_text} | {_mib(inference.get('resident_parameter_bytes'))} | "
            f"{_mib(checkpoint.get('size_bytes'))} | {_number(inference.get('fps'))} | "
            f"{_number(latency.get('p50'))} | {_number(latency.get('p95'))} | "
            f"{_gib(inference.get('peak_reserved_bytes') or inference.get('peak_vram_bytes'))} |"
        )
    lines.extend(
        [
            "",
            "## Training cost",
            "",
            "City and Rail columns report standalone training. Transfer adaptation reports only "
            "Rail20 and excludes the reused City40 stage; transfer cumulative adds City40 and "
            "Rail20 when both exact totals were retained. Peak is per-device allocator-reserved "
            "training VRAM; the final column is the maximum retained peak.",
            "",
            "| model | Cityscapes wall / GPU-h | RailSem19 wall / GPU-h | transfer adaptation wall / GPU-h | transfer cumulative wall / GPU-h | max retained peak train VRAM |",
            "|---|---:|---:|---:|---:|---:|",
        ]
    )
    for row in status["models"]:
        record = records.get(row["model"])
        protocols = _primary_protocols(record)
        cells = []
        peaks = []
        for protocol in REQUIRED_PROTOCOLS:
            training = protocols.get(protocol, {}).get("resource_evidence", {}).get("training", {})
            cells.append(
                (
                    f"{_duration(training.get('wall_clock_s_mean'))} / "
                    f"{_number(training.get('gpu_hours_mean'))}"
                )
                if training.get("wall_clock_s_mean") is not None
                else "not retained"
                if row["status"] == "complete"
                else "— / —"
            )
            if isinstance(training.get("peak_vram_bytes_per_device"), int):
                peaks.append(training["peak_vram_bytes_per_device"])
        cumulative = _cumulative_transfer_training(protocols)
        cumulative_cell = (
            f"{_duration(cumulative.get('wall_clock_s'))} / {_number(cumulative.get('gpu_hours'))}"
            if cumulative
            else "not retained"
        )
        link = "../../" + str(models[row["model"]].readme).removeprefix("docs/")
        lines.append(
            f"| [{row['model']}]({link}) | {' | '.join(cells)} | {cumulative_cell} | "
            f"{_gib(max(peaks) if peaks else None)} |"
        )
    lines.extend(
        [
            "",
            "## Fixed protocol and files",
            "",
            "- Cityscapes: 40,000 iterations, standard 19-class 500-image validation.",
            "- RailSem19: 40,000 iterations, `rail_union`, fixed 850-image validation.",
            "- RailSem19's disjoint 850-image test split remains reserved and unused; this "
            "comparison reports the validation split for every model.",
            "- Transfer: reuse the matching 40,000-iteration Cityscapes checkpoint and train "
            "RailSem19 for 20,000 iterations (60,000 cumulative); Cityscapes is never "
            "trained twice.",
            "- Transfer cost tables label Rail20 adaptation-only cost separately from cumulative "
            "City40 + Rail20 cost.",
            "- Transfer warm-starts every compatible learned tensor and reinitialises only the "
            "19-class to `rail_union` classifier mismatch.",
            "- Primary quality evaluation: raw checkpoint weights for every protocol, "
            "1024x1024 sliding window, stride 768, no TTA.",
            "- [`RAW_VS_EMA.md`](RAW_VS_EMA.md): paired raw-versus-EMA quality analysis for "
            "the same checkpoints and validation protocols.",
            "- [`results.csv`](results.csv): spreadsheet-friendly mean metrics, iterations, and resources.",
            "- [`status.json`](status.json): machine-readable scope and completion state.",
            "- [`records/`](records/): full class IoUs, retained seeds, resources, and provenance.",
            "- [`paper-review-corrections.json`](paper-review-corrections.json): resumed-run "
            "timing disclosures and exceptional BatchNorm correction provenance.",
            "",
            f"Training campaign source SHA: `{source_sha}`.",
            "Quality evaluation revisions are retained per cell and model page. The metric, "
            "inference, boundary, taxonomy, and transform implementations used by the mixed "
            "revisions are byte-identical for this comparison.",
            "",
        ]
    )
    leaderboard = _rail_accuracy_speed_leaderboard(manifest, records)
    lines.extend(
        [
            "## RailSem19 accuracy-speed leaderboard",
            "",
            "This lists and sorts all shipped model recipes. Models with both a final RailSem19-only "
            "mIoU and standardized L40S inference benchmark are ranked first; pending models "
            "remain visible below them until their evidence is complete. The recommendation "
            "score is accuracy-first: models must reach 60% RailSem19 mIoU to qualify, then "
            "the score weights normalized mIoU at 85% and log-scaled FPS at 15%. The quality "
            "gate prevents a weak but extremely fast model from taking over the leaderboard; "
            "log scaling also gives diminishing credit to already-high FPS. Below-floor models "
            "remain listed after qualified models, with their raw accuracy and speed ranks. "
            "This is a convenience recommendation rather than a universal deployment choice. "
            "Because every quality cell is seed 0, ranks separated by less than one mIoU point "
            "should be treated as practically unresolved rather than statistically ordered. "
            "Compatibility aliases remain visible and are labelled; they share the canonical "
            "recipe's weights and measurements.",
            "",
            "| rank | model | status | quality gate | recommendation score | RailSem19 mIoU | accuracy rank | FPS | speed rank | p50 latency | weights | model memory | peak inference VRAM |",
            "|---:|---|---|---|---:|---:|---:|---:|---:|---:|---|---:|---:|",
        ]
    )
    rank = 0
    for item in leaderboard:
        if item["status"] == "complete":
            rank += 1
        model = models[item["model"]]
        link = "../../" + str(model.readme).removeprefix("docs/")
        model_display = f"[{item['model']}]({link})"
        if item["alias_of"] is not None:
            model_display += f" *(alias of `{item['alias_of']}`)*"
        weights = item["weights"] if item["weights"] in ("raw", "ema") else "—"
        rank_display = str(rank) if item["status"] == "complete" else "—"
        score = (
            "not eligible"
            if item.get("quality_gate") == "below 60% mIoU"
            else _number(item.get("recommendation_score"))
        )
        miou = _number(item["miou"] * 100) if item["miou"] is not None else "—"
        latency = f"{_number(item['p50_ms'])} ms" if item["p50_ms"] is not None else "—"
        quality_gate = item.get("quality_gate", "—")
        accuracy_rank = item.get("accuracy_rank", "—")
        speed_rank = item.get("speed_rank", "—")
        lines.append(
            f"| {rank_display} | {model_display} | {item['status']} | "
            f"{quality_gate} | {score} | {miou} | {accuracy_rank} | "
            f"{_number(item['fps'])} | {speed_rank} | {latency} | {weights} | "
            f"{_mib(item['resident_parameter_bytes'])} | {_gib(item['peak_vram_bytes'])} |"
        )
    lines.append("")
    output = "\n".join(lines)
    if "±" in output:
        raise CampaignError("central README accidentally includes dispersion display")
    return output


def _public_privacy_check(planned: dict[Path, str]) -> None:
    forbidden = ("/data/", "/scr/", "/Users/", "gpu_uuid", "physical_visibility_token")
    leaks = [
        f"{path}: {token}"
        for path, content in planned.items()
        for token in forbidden
        if token in content
    ]
    if leaks:
        raise CampaignError("private infrastructure leaked into public output: " + "; ".join(leaks))


def report_campaign(campaign: Path, *, write: bool, publisher_root: Path | None = None) -> int:
    campaign = campaign.expanduser().resolve()
    record = _load_json_object(campaign / "campaign.json")
    publish_root = (
        publisher_root.expanduser().resolve() if publisher_root is not None else REPO_ROOT
    )
    if not (publish_root / ".git").exists():
        raise CampaignError(f"publisher root is not a Git worktree: {publish_root}")
    manifest = load_campaign_manifest(
        Path("configs/campaigns") / Path(record["source"]["manifest"]).name
    )
    if publish_root == REPO_ROOT and write:
        raise CampaignError(
            "refusing to edit the frozen training worktree; pass --publisher-root to a "
            "separate clean documentation checkout"
        )
    publisher_status = subprocess.run(
        ["git", "status", "--porcelain=v1", "--untracked-files=all"],
        cwd=publish_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if publisher_status.returncode != 0:
        raise CampaignError(f"cannot inspect publisher worktree: {publisher_status.stderr.strip()}")
    if write and publisher_status.stdout.strip():
        raise CampaignError("publisher worktree is dirty before report generation")
    ancestor = subprocess.run(
        [
            "git",
            "merge-base",
            "--is-ancestor",
            record["source"]["expected_git_sha"],
            "HEAD",
        ],
        cwd=publish_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if ancestor.returncode != 0:
        raise CampaignError(
            "publisher HEAD must descend from the frozen training SHA so generated docs "
            "cannot describe unrelated code"
        )
    cells = _available_job_records(record)
    records = _comparison_records(publish_root, manifest, cells, record)
    status = _comparison_status(manifest, records, record)
    comparison = publish_root / "docs/results/model-comparison"
    planned_writes: dict[Path, str] = {
        comparison / "README.md": _central_readme(
            manifest, status, records, record["source"]["expected_git_sha"]
        ),
        comparison / "results.csv": _comparison_csv(status, records),
        comparison / "status.json": json.dumps(status, indent=2, sort_keys=True, allow_nan=False)
        + "\n",
    }
    for model_id, normalized in records.items():
        planned_writes[comparison / "records" / f"{model_id}.json"] = (
            json.dumps(normalized, indent=2, sort_keys=False, allow_nan=False) + "\n"
        )
        model = next(item for item in manifest.models if item.id == model_id)
        readme = publish_root / model.readme
        if not readme.is_file():
            raise CampaignError(f"publisher worktree is missing model README: {readme}")
        planned_writes[readme] = _replace_generated_section(
            readme.read_text(encoding="utf-8"), _model_generated_section(normalized)
        )
    _public_privacy_check(planned_writes)

    if not write:
        print(
            f"report preflight passed: {len(cells)} campaign cells merged into "
            f"{len(records)} preserved model records and {len(planned_writes)} public files"
        )
        return 0
    for path, content in planned_writes.items():
        atomic_write_text(path, content)
    print(f"wrote {len(planned_writes)} preservation-checked report files")
    return 0


def _run_checked(command: Sequence[str], *, cwd: Path, env: dict[str, str] | None = None) -> str:
    completed = subprocess.run(
        list(command), cwd=cwd, env=env, capture_output=True, text=True, check=False
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        raise CampaignError(f"command failed ({shlex.join(command)}): {detail}")
    return completed.stdout.strip()


def _git_status_porcelain(root: Path) -> str:
    """Return porcelain output without stripping its leading XY status column."""
    completed = subprocess.run(
        ["git", "status", "--porcelain=v1", "--untracked-files=all"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        raise CampaignError(f"cannot inspect publisher worktree: {detail}")
    return completed.stdout.rstrip("\n")


def _publisher_status(campaign: Path, **updates: object) -> dict[str, Any]:
    path = campaign / "publisher_status.json"
    if path.is_file():
        status = _load_json_object(path)
    else:
        status = {
            "schema_version": 1,
            "status": "pending",
            "started_at": _now(),
            "updated_at": None,
            "finished_at": None,
            "last_published_cell_count": 0,
            "last_published_performance_count": 0,
            "last_snapshot_fingerprint": None,
            "last_commit": None,
            "failure": None,
        }
    status.update(updates)
    status["updated_at"] = _now()
    atomic_write_json(path, status)
    return status


def _publisher_snapshot(record: dict[str, Any]) -> tuple[int, int, str]:
    cells = _available_job_records(record)
    campaign = Path(record["campaign"])
    performance_hashes: dict[str, str] = {}
    artifact_state: dict[str, Any] = {}
    for lane in record["lanes"]:
        lane_status = _load_json_object(_status_path(campaign, lane["id"]))
        for job in lane_status.get("jobs", []):
            attempts = job.get("attempts") if isinstance(job, dict) else None
            latest = attempts[-1] if isinstance(attempts, list) and attempts else None
            if not isinstance(latest, dict):
                continue
            artifact_state[job["id"]] = {
                "status": job.get("status"),
                "sha256": latest.get("sha256", {}),
            }
            source_job = _job_by_id(record, job["id"])
            if not source_job.get("performance_owner"):
                continue
            raw_path = latest.get("paths", {}).get("performance")
            if isinstance(raw_path, str) and Path(raw_path).is_file():
                digest = _sha256(Path(raw_path))
                recorded = (latest.get("sha256") or {}).get("performance")
                if recorded is not None and digest != recorded:
                    raise CampaignError(f"performance artifact changed for {job['id']}")
                performance_hashes[job["id"]] = digest
    fingerprint_payload = {
        "cells": sorted(cells),
        "artifacts": artifact_state,
        "performance": performance_hashes,
    }
    fingerprint = hashlib.sha256(
        json.dumps(fingerprint_payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return len(cells), len(performance_hashes), fingerprint


def _publish_snapshot(record: dict[str, Any], campaign: Path, count: int) -> str | None:
    publisher = record["publisher"]
    root = Path(publisher["worktree"])
    remote = publisher["remote"]
    branch = publisher["branch"]
    if not root.is_dir():
        raise CampaignError(f"publisher worktree does not exist: {root}")
    if _git_status_porcelain(root):
        raise CampaignError("publisher worktree is dirty before synchronization")
    _run_checked(["git", "fetch", remote, branch], cwd=root)
    local_head = _run_checked(["git", "rev-parse", "HEAD"], cwd=root)
    remote_head = _run_checked(["git", "rev-parse", f"{remote}/{branch}"], cwd=root)
    if local_head != remote_head:
        remote_is_ancestor = (
            subprocess.run(
                ["git", "merge-base", "--is-ancestor", remote_head, local_head],
                cwd=root,
                check=False,
            ).returncode
            == 0
        )
        local_is_ancestor = (
            subprocess.run(
                ["git", "merge-base", "--is-ancestor", local_head, remote_head],
                cwd=root,
                check=False,
            ).returncode
            == 0
        )
        if remote_is_ancestor:
            _run_checked(["git", "push", remote, f"HEAD:{branch}"], cwd=root)
            _run_checked(["git", "fetch", remote, branch], cwd=root)
            confirmed = _run_checked(["git", "rev-parse", f"{remote}/{branch}"], cwd=root)
            if confirmed != local_head:
                raise CampaignError("publisher push was not confirmed on the remote branch")
        elif local_is_ancestor:
            _run_checked(["git", "merge", "--ff-only", f"{remote}/{branch}"], cwd=root)
        else:
            raise CampaignError("publisher worktree and remote branch have diverged")
    # The public repository intentionally starts without a placeholder quality
    # bundle. Wait for the first validated cell so the first published table is
    # useful and includes at least one machine record plus a real records/
    # target for the README link.
    if count == 0:
        return None
    report_campaign(campaign, write=True, publisher_root=root)
    changed = _git_status_porcelain(root)
    if not changed:
        return None
    unexpected = []
    for line in changed.splitlines():
        path = line[3:]
        comparison_file = path in {
            "docs/results/model-comparison/README.md",
            "docs/results/model-comparison/results.csv",
            "docs/results/model-comparison/status.json",
        } or (path.startswith("docs/results/model-comparison/records/") and path.endswith(".json"))
        if not comparison_file and not (
            path.startswith("docs/catalog/models/") and path.endswith("/README.md")
        ):
            unexpected.append(line)
    if unexpected:
        raise CampaignError(
            "reporter changed files outside its documentation scope: " + ", ".join(unexpected)
        )
    _run_checked(["git", "diff", "--check"], cwd=root)
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(root / "src")
    python = record["execution"]["python"]
    _run_checked(
        [
            python,
            "-m",
            "pytest",
            "-q",
            "tests/test_documentation.py",
            "tests/test_benchmark_campaign.py",
            "tests/test_model_comparison_results.py",
        ],
        cwd=root,
        env=environment,
    )
    _run_checked(
        ["git", "add", "docs/results/model-comparison", "docs/catalog/models"],
        cwd=root,
    )
    logical = record["logical_cell_count"]
    message = f"Update model comparison results ({count}/{logical} cells)"
    _run_checked(["git", "commit", "-m", message], cwd=root)
    commit = _run_checked(["git", "rev-parse", "HEAD"], cwd=root)
    _run_checked(["git", "push", remote, f"HEAD:{branch}"], cwd=root)
    _run_checked(["git", "fetch", remote, branch], cwd=root)
    confirmed = _run_checked(["git", "rev-parse", f"{remote}/{branch}"], cwd=root)
    if confirmed != commit:
        raise CampaignError("publisher commit was not confirmed on the remote branch")
    return commit


def run_publisher(campaign: Path, *, once: bool = False) -> int:
    if not os.environ.get("TMUX"):
        raise CampaignError("publisher must run inside its named tmux session")
    campaign = campaign.expanduser().resolve()
    record = _load_json_object(campaign / "campaign.json")
    publisher = record.get("publisher")
    if not isinstance(publisher, dict):
        raise CampaignError("campaign has no publisher configuration")
    status = _publisher_status(campaign, status="running", failure=None)
    try:
        while True:
            count, performance_count, fingerprint = _publisher_snapshot(record)
            if fingerprint != status.get("last_snapshot_fingerprint"):
                commit = _publish_snapshot(record, campaign, count)
                status = _publisher_status(
                    campaign,
                    status="running",
                    last_published_cell_count=count,
                    last_published_performance_count=performance_count,
                    last_snapshot_fingerprint=fingerprint,
                    last_commit=commit or status.get("last_commit"),
                    failure=None,
                )
            expected_performance = sum(bool(job.get("performance_owner")) for job in record["jobs"])
            if count >= record["logical_cell_count"] and performance_count >= expected_performance:
                _publisher_status(campaign, status="complete", finished_at=_now())
                return 0
            if once:
                return 0
            time.sleep(publisher["interval_seconds"])
    except BaseException as exc:
        _publisher_status(
            campaign,
            status="failed",
            finished_at=_now(),
            failure=f"{type(exc).__name__}: {exc}",
        )
        raise


def _add_manifest_and_seeds(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--seeds", type=_seed_list, default=(0,), metavar="0,1,2")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    plan = subparsers.add_parser("plan", help="validate and print the immutable job matrix")
    _add_manifest_and_seeds(plan)

    launch = subparsers.add_parser(
        "launch", help="scan reusable cells and start missing jobs in named tmux sessions"
    )
    _add_manifest_and_seeds(launch)
    launch.add_argument("--campaign", required=True, type=Path)
    launch.add_argument("--expected-sha", required=True, type=_full_sha)
    launch.add_argument("--cityscapes-root", required=True, type=Path)
    launch.add_argument("--railsem19-root", required=True, type=Path)
    launch.add_argument("--gpus", required=True, type=_gpu_list, metavar="0,1,2,3")
    launch.add_argument("--tmux-prefix", type=_tmux_prefix, default="segmentary-cityrail")
    launch.add_argument("--python", type=Path, default=Path(sys.executable))
    launch.add_argument("--hf-home", type=Path, default=os.environ.get("HF_HOME"))
    launch.add_argument(
        "--batch-size",
        type=_positive_int,
        default=2,
        help="per-GPU batch size (default: 2; required by pooled BatchNorm recipes)",
    )
    launch.add_argument("--accum", type=_positive_int, default=8)
    launch.add_argument("--train-workers", type=int, default=8)
    launch.add_argument("--eval-workers", type=int, default=4)
    launch.add_argument("--deterministic", action="store_true")
    launch.add_argument(
        "--publisher-root",
        type=Path,
        help="separate clean checkout used by an incremental publisher tmux session",
    )
    launch.add_argument("--publish-remote", default="origin")
    launch.add_argument("--publish-branch", default="main")
    launch.add_argument("--publish-interval", type=_positive_int, default=30)
    launch.add_argument(
        "--reuse-root",
        action="append",
        default=[],
        type=Path,
        help="existing run root to scan before queueing (repeatable)",
    )
    launch.add_argument(
        "--reuse-sha",
        action="append",
        default=[],
        type=_full_sha,
        help="additional clean source revision explicitly approved for compatible reuse",
    )
    launch.add_argument("--dry-run", action="store_true")
    launch.add_argument(
        "--prepare-only",
        action="store_true",
        help="persist the immutable campaign and lane statuses but start zero tmux sessions",
    )

    worker = subparsers.add_parser("worker", help=argparse.SUPPRESS)
    worker.add_argument("--campaign", required=True, type=Path)
    worker.add_argument("--lane", required=True)

    bootstrap = subparsers.add_parser("bootstrap", help=argparse.SUPPRESS)
    bootstrap.add_argument("--campaign", required=True, type=Path)

    publisher = subparsers.add_parser("publisher", help=argparse.SUPPRESS)
    publisher.add_argument("--campaign", required=True, type=Path)
    publisher.add_argument("--once", action="store_true")

    migrate = subparsers.add_parser(
        "migrate-source",
        help="resume a stopped pre-result campaign on a descendant source revision",
    )
    migrate.add_argument("--campaign", required=True, type=Path)
    migrate.add_argument("--from-sha", required=True, type=_full_sha)
    migrate.add_argument("--to-sha", required=True, type=_full_sha)
    migrate.add_argument("--reason", required=True)

    report = subparsers.add_parser(
        "report", help="validate all cells and generate the central and per-model README tables"
    )
    report.add_argument("--campaign", required=True, type=Path)
    report.add_argument("--write", action="store_true", help="write checked README updates")
    report.add_argument(
        "--publisher-root",
        type=Path,
        help="separate clean Git checkout for incremental docs updates",
    )
    return parser


def _print_plan(manifest: CampaignManifest, seeds: Sequence[int]) -> None:
    jobs = campaign_jobs(manifest, seeds)
    physical = campaign_jobs(manifest, seeds, include_aliases=False)
    print(f"campaign : {manifest.name}")
    print(f"models   : {len(manifest.models)}")
    print(f"protocols: {', '.join(REQUIRED_PROTOCOLS)}")
    print(f"seeds    : {', '.join(map(str, seeds))}")
    print(f"cells    : {len(jobs)} logical reports")
    print(f"GPU jobs : {len(physical)} ({len(jobs) - len(physical)} alias cells reused)")
    print("best-first model order:")
    for index, model_id in enumerate(manifest.priority_order, start=1):
        print(f"  {index:>2}. {model_id}")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "worker":
            return run_worker(args.campaign, args.lane)
        if args.command == "bootstrap":
            return run_bootstrap(args.campaign)
        if args.command == "publisher":
            return run_publisher(args.campaign, once=args.once)
        if args.command == "migrate-source":
            migration = migrate_campaign_source(
                args.campaign,
                from_sha=args.from_sha,
                to_sha=args.to_sha,
                reason=args.reason,
            )
            print(
                f"migrated {len(migration['resume_checkpoints'])} interrupted lanes from "
                f"{args.from_sha} to {args.to_sha}; rerun the original launch command with "
                f"--expected-sha {args.to_sha} and --reuse-sha {args.from_sha}"
            )
            return 0
        if args.command == "report":
            return report_campaign(
                args.campaign,
                write=args.write,
                publisher_root=args.publisher_root,
            )

        manifest = load_campaign_manifest(args.manifest)
        if args.command == "plan":
            _print_plan(manifest, args.seeds)
            return 0

        if args.train_workers < 0 or args.eval_workers < 0:
            raise CampaignError("worker counts cannot be negative")
        expected_sha = check_source_provenance(args.expected_sha)
        datasets = _dataset_roots(args.cityscapes_root, args.railsem19_root)
        python = args.python.expanduser().resolve()
        if not python.is_file():
            raise CampaignError(f"Python interpreter is not a file: {python}")
        campaign = args.campaign.expanduser().resolve()
        requested = build_campaign_record(
            manifest=manifest,
            campaign=campaign,
            expected_sha=expected_sha,
            datasets=datasets,
            seeds=args.seeds,
            gpus=args.gpus,
            tmux_prefix=args.tmux_prefix,
            python=python,
            hf_home=args.hf_home,
            batch_size=args.batch_size,
            accum=args.accum,
            train_workers=args.train_workers,
            eval_workers=args.eval_workers,
            deterministic=args.deterministic,
            reuse_roots=args.reuse_root,
            allowed_reuse_shas=args.reuse_sha,
            publisher_root=args.publisher_root,
            publish_remote=args.publish_remote,
            publish_branch=args.publish_branch,
            publish_interval=args.publish_interval,
        )
        existing_path = campaign / "campaign.json"
        if existing_path.is_file():
            record = _load_json_object(existing_path)
            validate_prepared_request(record, requested)
            print(
                f"resume existing campaign: accepted={record.get('reuse', {}).get('accepted_cells', 0)} "
                f"queued={record.get('reuse', {}).get('queued_cells', len(record.get('jobs', [])))}"
            )
        else:
            record = requested
            record["reuse"] = (
                scan_reusable_cells(record)
                if args.reuse_root
                else {
                    "scanned_at": _now(),
                    "roots": [],
                    "result_files_scanned": 0,
                    "counts": {},
                    "accepted": [],
                    "ambiguous": [],
                    "rejected_examples": [],
                    "accepted_cells": 0,
                    "queued_cells": record["physical_job_count"],
                }
            )
            print(
                f"reuse preflight: accepted={record['reuse']['accepted_cells']} "
                f"queued={record['reuse']['queued_cells']} "
                f"ambiguous={len(record['reuse']['ambiguous'])}"
            )
        if args.dry_run and args.prepare_only:
            raise CampaignError("--dry-run and --prepare-only are mutually exclusive")
        return launch_campaign(record, dry_run=args.dry_run, prepare_only=args.prepare_only)
    except (CampaignError, OSError) as exc:
        print(f"campaign error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
