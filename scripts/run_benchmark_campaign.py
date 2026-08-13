#!/usr/bin/env python3
"""Launch and report the all-model Cityscapes/RailSem19 benchmark campaign.

Long-running workers are always created as named tmux sessions. A worker refuses
to run outside tmux, and each lane receives exactly one physical GPU through
``CUDA_VISIBLE_DEVICES``. Re-running ``launch`` resumes at job boundaries:
validated successes are skipped, while an interrupted or failed job receives a
new attempt directory so earlier evidence is never overwritten.

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
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

_HASH_CACHE: dict[tuple[str, int, int], str] = {}

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from segmentary.config import (
    ExperimentConfig,
    config_hash,
    deep_merge,
    from_dict,
    load_yaml,
    to_dict,
)
from segmentary.taxonomy import load_space
from segmentary.utils.results import load_results

DEFAULT_MANIFEST = Path("configs/campaigns/all_models_cityscapes_railsem19.yaml")
REQUIRED_PROTOCOLS = ("cityscapes", "railsem19", "cityscapes_to_railsem19")
STATUS_SCHEMA_VERSION = 1
CAMPAIGN_SCHEMA_VERSION = 1
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


def partition_jobs(jobs: Sequence[Job], gpus: Sequence[int]) -> dict[int, tuple[Job, ...]]:
    """Balance jobs with deterministic longest-processing-time scheduling."""
    if not gpus:
        raise CampaignError("at least one GPU is required")
    unknown = sorted({job.model.id for job in jobs} - MODEL_COST_WEIGHTS.keys())
    if unknown:
        raise CampaignError(f"missing admission cost weights for models: {unknown}")
    lanes = {gpu: [] for gpu in gpus}
    loads = {gpu: 0.0 for gpu in gpus}
    input_order = {job.id: index for index, job in enumerate(jobs)}

    def cost(job: Job) -> float:
        protocol_scale = 1.5 if job.protocol.id == "cityscapes_to_railsem19" else 1.0
        return MODEL_COST_WEIGHTS[job.model.id] * protocol_scale

    for job in sorted(jobs, key=lambda item: (-cost(item), input_order[item.id])):
        gpu = min(gpus, key=lambda item: (loads[item], gpus.index(item)))
        lanes[gpu].append(job)
        loads[gpu] += cost(job)
    return {gpu: tuple(items) for gpu, items in lanes.items()}


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
    return {
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
        "seed": job.seed,
        "experiment_name": job.experiment_name,
        "lane": lane,
        "performance_owner": False,
    }


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
            "scheduler": "measured_cost_lpt_static_lanes",
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
            "refresh_seconds": 10,
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
                            "checkpoint": accepted["checkpoint"],
                            "source_results": accepted["source_result"],
                            "config": accepted["bundle_config"],
                            "performance": accepted["bundle_performance"],
                        },
                        "sha256": {
                            "common_results": accepted["result_sha256"],
                            "checkpoint": accepted["checkpoint_sha256"],
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
                "checkpoint": str(checkpoint) if checkpoint is not None else None,
                "checkpoint_sha256": accepted["checkpoint_sha256"],
                "checkpoint_available": accepted["checkpoint_available"],
                "checkpoint_step": accepted["checkpoint_step"],
                "iteration_plan": accepted["iteration_plan"],
                "caveat": accepted["caveat"],
                "source_git_sha": accepted["source_git_sha"],
                "record_kind": accepted["record_kind"],
                "compatibility_sha256": accepted["compatibility_sha256"],
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
    return f"exec {shlex.join(command)} >> {shlex.quote(str(lane_log))} 2>&1"


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
        shell_command = (
            f"exec env PYTHONPATH={shlex.quote(str(SRC_ROOT))} {shlex.join(command)} "
            f">> {shlex.quote(str(campaign / 'reused-performance.console.log'))} 2>&1"
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
        shell_command = (
            f"exec env PYTHONPATH={shlex.quote(str(SRC_ROOT))} {shlex.join(command)} "
            f">> {shlex.quote(str(campaign / 'publisher.console.log'))} 2>&1"
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
    record: dict[str, Any], job: dict[str, Any], attempt: Path
) -> tuple[ExperimentConfig, dict[str, Any]]:
    merged: dict[str, Any] = {}
    layers = [
        Path("configs/base.yaml"),
        Path(job["model_config"]),
        Path(job["curriculum_config"]),
    ]
    if job.get("campaign_config"):
        layers.append(Path(job["campaign_config"]))
    for relative in layers:
        merged = deep_merge(merged, load_yaml(REPO_ROOT / relative))
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
    merged["eval"] = {
        **merged.get("eval", {}),
        "num_workers": record["execution"]["eval_workers"],
    }
    stages = merged.get("stages")
    if not isinstance(stages, list) or not stages:
        raise CampaignError(f"{job['id']} resolved no curriculum stages")
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
        unique = {(item["result_sha256"], item["checkpoint_sha256"]) for item in top}
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
        chosen["accepted_at"] = _now()
        chosen["bundle_result"] = str(
            Path(record["campaign"]) / "accepted" / job_id / "results.json"
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
    return {
        "attempt_dir": attempt,
        "config": attempt / "resolved-config.yaml",
        "run_dir": run_dir,
        "checkpoint": checkpoint,
        "training_results": training_results,
        "common_results": common_results,
        "stage_results": stage_results,
        "performance": attempt / "performance.json",
        "log": attempt / "job.log",
    }


def _commands(
    record: dict[str, Any],
    job: dict[str, Any],
    paths: dict[str, Any],
    *,
    result_git_sha: str | None = None,
    result_stage: str | None = None,
) -> tuple[list[str], list[str], list[str]]:
    python = record["execution"]["python"]
    config = str(paths["config"])
    train = [python, "-m", "segmentary.train", config, "--devices", "1"]
    if record["execution"]["deterministic"]:
        train.append("--deterministic")
    evaluate = [
        python,
        "-m",
        "segmentary.eval",
        config,
        "--ckpt",
        str(paths["checkpoint"]),
        "--ema",
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
        str(paths["common_results"]),
        "--device",
        "cuda:0",
        "--num-workers",
        str(record["execution"]["eval_workers"]),
    ]
    if job.get("evaluation_split_file"):
        evaluate.extend(["--split-file", str((REPO_ROOT / job["evaluation_split_file"]).resolve())])
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
        "--ema",
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


def _attempt_path_objects(attempt: dict[str, Any]) -> tuple[dict[str, Path], dict[str, Path]]:
    raw_paths = attempt["paths"]
    if not isinstance(raw_paths, dict):
        raise CampaignError("attempt paths must be a mapping")
    paths = {
        key: Path(value)
        for key, value in raw_paths.items()
        if value is not None and not isinstance(value, dict)
    }
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


def validate_success(
    record: dict[str, Any], job: dict[str, Any], attempt: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    paths, _ = _attempt_path_objects(attempt)
    resolved, stage_records = validate_training_artifacts(record, job, attempt)
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
    actual_hashes: dict[str, Any] = {
        "resolved_config": _sha256(paths["config"]),
        "checkpoint": _sha256(paths["checkpoint"]),
        "stage_results": {
            name: _sha256(path) for name, path in _attempt_path_objects(attempt)[1].items()
        },
        "common_results": _sha256(paths["common_results"]),
        "performance": _sha256(paths["performance"]) if job.get("performance_owner") else None,
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
            load_results(common_results).to_dict()["git_sha"],
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
            "ema",
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
    paths = {key: Path(value) for key, value in attempt["paths"].items() if value is not None}
    result_path = paths["common_results"]
    source_path = paths["source_results"]
    checkpoint = paths.get("checkpoint")
    expected_hashes = attempt.get("sha256") or {}
    if _sha256(result_path) != expected_hashes.get("common_results"):
        raise CampaignError(f"reused bundle result changed: {result_path}")
    if _sha256(source_path) != expected_hashes.get("common_results"):
        raise CampaignError(f"reused source result changed: {source_path}")
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
        "train_command": train,
        "eval_command": evaluate,
        "performance_command": benchmark,
        "environment": {key: env[key] for key in ENV_KEYS if key in env},
        "paths": serialized_paths,
        "sha256": {},
    }


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
                "evaluating",
                "eval_failed",
                "eval_artifact_failed",
                "benchmarking",
                "performance_failed",
                "performance_artifact_failed",
            }
            else None
        )
        if resumable is None:
            number, attempt_dir = _next_attempt(job, campaign)
            attempt_dir.mkdir(parents=True, exist_ok=False)
            _, config_dict = _resolved_config(record, job, attempt_dir)
            paths = _attempt_paths(job, attempt_dir, config_dict)
            atomic_write_text(paths["config"], yaml.safe_dump(config_dict, sort_keys=False))
            train, evaluate, benchmark = _commands(record, job, paths)
            attempt = _attempt_record(number, paths, train, evaluate, benchmark, env)
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
        else:
            attempt = resumable
            paths, _ = _attempt_path_objects(attempt)
            try:
                config_dict = load_yaml(paths["config"])
            except (OSError, ValueError, yaml.YAMLError) as exc:
                raise CampaignError(f"cannot resume {job['id']}: {exc}") from exc
            train, evaluate, benchmark = _commands(record, job, paths)
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
            "common_results": _sha256(paths["common_results"]),
            "performance": (
                _sha256(paths["performance"]) if job.get("performance_owner") else None
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
        rows.append(
            {
                "stage": stage,
                "wall_clock_s": float(wall),
                "gpu_count": devices,
                "gpu_hours": float(wall) * devices / 3600,
                "peak_vram_bytes_per_device": peak,
                "result_sha256": _sha256(path),
            }
        )
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
    training_stages = _training_stage_evidence(attempt) if attempt.get("kind") != "reused" else []
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


def _protocol_resource_evidence(
    individuals: list[dict[str, Any]], *, parameter_count: int | None
) -> dict[str, Any]:
    checkpoints = [item["source"] for item in individuals]
    sizes = [item.get("checkpoint_size_bytes") for item in checkpoints]
    available_sizes = [item for item in sizes if isinstance(item, int)]
    stage_sets = [item.get("training_stages") or [] for item in checkpoints]
    training_runs = [rows for rows in stage_sets if rows]
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
    return {
        "status": "complete",
        "label": job["protocol_label"],
        "dataset": f"{'Cityscapes' if job['protocol'] == 'cityscapes' else 'RailSem19'} val",
        "taxonomy": job["evaluation_space"],
        "training": (
            "40,000 Cityscapes steps, then 20,000 RailSem19 steps"
            if job["protocol"] == "cityscapes_to_railsem19"
            else "40,000 steps from pretrained weights"
        ),
        "iteration_progress": _iteration_progress(
            plan,
            checkpoint_available=checkpoint_available,
            checkpoint_step=checkpoint_step,
        ),
        "resource_evidence": {},
        "evaluation": {
            "split": "val",
            "images": images,
            "weights": "EMA",
            "sliding_window": [1024, 1024],
            "stride": [768, 768],
            "tta": False,
        },
        "seed_count": 0,
        "seeds": [],
        "aggregate": {},
        "support": {},
        "individual": [],
        "derived_metrics": ["mprecision", "mdice", "mspecificity"],
        "derivation": (
            "Derived from each retained confusion matrix when absent; all other metrics "
            "come directly from validated result records."
        ),
        "caveats": ([attempt["caveat"]] if attempt.get("caveat") else []),
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
            "Model-only public forward measured once from the RailSem19-only 21-class EMA "
            "checkpoint and linked across this model's quality protocols."
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


def _comparison_records(
    publish_root: Path,
    manifest: CampaignManifest,
    cells: dict[str, tuple[dict[str, Any], dict[str, Any]]],
    campaign_record: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    records = _load_existing_records(publish_root)
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
                raise CampaignError(
                    f"normalized seed {job_id} conflicts with preserved public metrics"
                )
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
        record["status"] = (
            "complete"
            if all(protocol in record.get("protocols", {}) for protocol in REQUIRED_PROTOCOLS)
            else "running"
            if record.get("protocols")
            else "queued"
        )
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


def _record_metric(record: dict[str, Any], protocol: str, metric: str) -> object:
    return (
        record.get("protocols", {})
        .get(protocol, {})
        .get("aggregate", {})
        .get(metric, {})
        .get("mean")
    )


def _model_generated_section(record: dict[str, Any]) -> str:
    protocols = record.get("protocols", {})
    lines = [
        REPORT_START,
        "## Cityscapes and RailSem19 benchmark results",
        "",
        "Values are validated mean percentages, shown as one clean number. Detailed machine "
        "records retain every contributing seed. `—` means evidence is unavailable, not zero.",
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
        protocol = protocols.get(protocol_id)
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
    lines.extend(
        [
            "",
            "### Standardized model-only inference",
            "",
            (
                "Measured once from this model's RailSem19-only 21-class EMA checkpoint on an "
                if performance.get("status") == "complete"
                else "Pending one measurement from this model's RailSem19-only 21-class EMA checkpoint on an "
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
            "Training wall time and GPU-hours sum every curriculum stage. Peak training VRAM "
            "is the maximum per-device allocator-reserved high-water mark. Full-pipeline "
            "throughput includes the loader, sliding-window inference, and metrics.",
            "",
            "| protocol | train wall / run | GPU-hours / run | peak train VRAM / GPU | full validation images/s |",
            "|---|---:|---:|---:|---:|",
        ]
    )
    for protocol_id in REQUIRED_PROTOCOLS:
        protocol = protocols.get(protocol_id)
        evidence = protocol.get("resource_evidence", {}) if isinstance(protocol, dict) else {}
        training = evidence.get("training", {})
        pipeline = evidence.get("full_validation_pipeline", {})
        lines.append(
            f"| {labels[protocol_id]} | {_duration(training.get('wall_clock_s_mean'))} | "
            f"{_number(training.get('gpu_hours_mean'))} | "
            f"{_gib(training.get('peak_vram_bytes_per_device'))} | "
            f"{_number(pipeline.get('images_per_s_mean'), decimals=3)} |"
        )

    city = protocols.get("cityscapes")
    if isinstance(city, dict):
        lines.extend(["", "### Cityscapes class IoU", "", "| class | IoU |", "|---|---:|"])
        for name, summary in city["aggregate"]["per_class_iou"].items():
            value = summary["mean"]
            lines.append(f"| {name} | {_number(value * 100 if value is not None else None)} |")
    rail = protocols.get("railsem19")
    transfer = protocols.get("cityscapes_to_railsem19")
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
            for protocol in protocols.values()
            for individual in protocol["individual"]
        }
    )
    caveats = sorted(
        {caveat for protocol in protocols.values() for caveat in protocol.get("caveats", [])}
    )
    retained_seeds = "; ".join(
        f"{labels[protocol_id]}: {', '.join(map(str, protocol['seeds']))}"
        for protocol_id, protocol in protocols.items()
        if protocol_id in labels and protocol.get("seeds")
    )
    derivations = sorted(
        {
            protocol.get("derivation")
            for protocol in protocols.values()
            if isinstance(protocol.get("derivation"), str)
        }
    )
    lines.extend(
        [
            "",
            "### Provenance",
            "",
            f"- Model recipe: `{record['model_config']}`",
            f"- Source revisions: `{', '.join(revisions)}`",
            f"- Retained seeds: {retained_seeds or 'none yet'}.",
            "- EMA quality evaluation uses 1024x1024 sliding windows, stride 768, no TTA.",
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
            ("cityscapes", "Cityscapes", 40_000),
            ("railsem19", "RailSem19", 20_000),
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
    return "complete" if record.get("status") == "complete" else "running"


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


def _comparison_status(
    manifest: CampaignManifest,
    records: dict[str, dict[str, Any]],
    campaign_record: dict[str, Any] | None = None,
) -> dict[str, Any]:
    execution_states = _model_execution_states(campaign_record)
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
        protocols = record.get("protocols", {}) if record else {}
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
            if record and record.get("status") == "complete"
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
            }
        )
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
            "standardized_inference": {
                "status": (
                    "complete"
                    if completed_performance == expected_performance
                    else "running"
                    if completed_performance
                    else "queued"
                ),
                "owner": "RailSem19-only 21-class EMA checkpoint, seed 0",
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
        *protocol_columns,
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
        protocols = record.get("protocols", {}) if record else {}
        output: dict[str, Any] = {
            "priority": row["priority"],
            "model": row["model"],
            "status": row["status"],
        }
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
    lines = [
        "# Model comparison: Cityscapes and RailSem19",
        "",
        "This live comparison covers every shipped model recipe. Compatible results are reused "
        "instead of retrained. `—` means evidence is unavailable, not zero or failure. Quality "
        "tables show one clean mean; individual seeds remain in machine records.",
        "",
        "## Quality",
        "",
        "| priority | model | status | Cityscapes mIoU (iterations) | RailSem19 mIoU (iterations) | Cityscapes → RailSem19 mIoU (iterations) |",
        "|---:|---|---|---:|---:|---:|",
    ]
    for row in status["models"]:
        model = models[row["model"]]
        link = "../../" + str(model.readme).removeprefix("docs/")
        values = []
        for protocol_id in REQUIRED_PROTOCOLS:
            progress = row["iteration_progress"][protocol_id]
            metric = row[f"{protocol_id}_miou"]
            values.append(
                "—"
                if metric == "—"
                else f"{metric} ({progress['current_iterations']:,}/{progress['target_iterations']:,})"
            )
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
            "21-class final EMA checkpoint. Contract: NVIDIA L40S, PyTorch eager public "
            "forward, BF16 autocast, batch 1, 1024x1024, 20 warmup and 100 CUDA-event-timed "
            "iterations. It includes internal query-to-dense collapse and excludes I/O, "
            "preprocessing, sliding windows, argmax, and metrics.",
            "",
            "Weight memory is the resident parameter tensors; the resume checkpoint also "
            "contains optimizer and EMA state; peak VRAM is allocator-reserved memory excluding "
            "the CUDA context.",
            "",
            "| model | parameters (Rail 21-class) | model weight memory | resume checkpoint | FPS | p50 | p95 | peak VRAM (reserved, excl. context) |",
            "|---|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for row in status["models"]:
        record = records.get(row["model"])
        protocols = record.get("protocols", {}) if record else {}
        rail = protocols.get("railsem19", {})
        resource = rail.get("resource_evidence", {}) if isinstance(rail, dict) else {}
        checkpoint = resource.get("final_checkpoint", {})
        inference = row["standardized_inference"]
        latency = inference.get("latency_ms") or {}
        link = "../../" + str(models[row["model"]].readme).removeprefix("docs/")
        parameter_count = resource.get("parameter_count")
        parameter_text = f"{parameter_count:,}" if isinstance(parameter_count, int) else "—"
        lines.append(
            f"| [{row['model']}]({link}) | "
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
            "Wall time and GPU-hours include every curriculum stage; peak is per-device "
            "allocator-reserved training VRAM.",
            "",
            "| model | Cityscapes wall / GPU-h | RailSem19 wall / GPU-h | transfer wall / GPU-h | peak train VRAM |",
            "|---|---:|---:|---:|---:|",
        ]
    )
    for row in status["models"]:
        record = records.get(row["model"])
        protocols = record.get("protocols", {}) if record else {}
        cells = []
        peaks = []
        for protocol in REQUIRED_PROTOCOLS:
            training = protocols.get(protocol, {}).get("resource_evidence", {}).get("training", {})
            cells.append(
                f"{_duration(training.get('wall_clock_s_mean'))} / "
                f"{_number(training.get('gpu_hours_mean'))}"
            )
            if isinstance(training.get("peak_vram_bytes_per_device"), int):
                peaks.append(training["peak_vram_bytes_per_device"])
        link = "../../" + str(models[row["model"]].readme).removeprefix("docs/")
        lines.append(
            f"| [{row['model']}]({link}) | {' | '.join(cells)} | {_gib(max(peaks) if peaks else None)} |"
        )
    lines.extend(
        [
            "",
            "## Fixed protocol and files",
            "",
            "- Cityscapes: 40,000 iterations, standard 19-class 500-image validation.",
            "- RailSem19: 40,000 iterations, `rail_union`, fixed 850-image validation.",
            "- Transfer: 40,000 Cityscapes + 20,000 RailSem19 iterations; total 60,000.",
            "- Quality evaluation: EMA, 1024x1024 sliding window, stride 768, no TTA.",
            "- [`results.csv`](results.csv): spreadsheet-friendly mean metrics, iterations, and resources.",
            "- [`status.json`](status.json): machine-readable scope and completion state.",
            "- [`records/`](records/): full class IoUs, retained seeds, resources, and provenance.",
            "",
            f"Campaign source SHA: `{source_sha}`.",
            "",
        ]
    )
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
    manifest = load_campaign_manifest(Path(record["source"]["manifest"]))
    publish_root = (
        publisher_root.expanduser().resolve() if publisher_root is not None else REPO_ROOT
    )
    if not (publish_root / ".git").exists():
        raise CampaignError(f"publisher root is not a Git worktree: {publish_root}")
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
