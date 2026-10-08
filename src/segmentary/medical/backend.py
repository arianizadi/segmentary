"""Isolated, version-bound orchestration of the optional nnU-Net 2.8.1 backend.

The public functions return JSON-serializable records. ``dry_run=True`` validates
inputs and returns a proposed action without creating files or starting a child.
Only development cases enter nnU-Net's raw/planning directories. As in standard
nnU-Net, planning uses train + validation; this is not train-only fold planning.

Official interfaces were checked against the 2.8.1 wheel: ``get_trainer_from_args``,
``plan_and_preprocess_entry``, and ``nnUNetPredictor``. This module delegates the
network, preprocessing, augmentation, optimizer, losses, and training loop to
that release. It adds experiment guards and atomic checkpoint/RNG sidecars.

Two opt-in variants keep the frozen reference preprocessing. ``output_mode:
regions`` trains nnU-Net region heads that decode to the same native label map
(``nnunet_regions``). ``backend_runtime: nnunet-master-nnssl`` runs a separate
nnU-Net master environment, bound by its ``pip freeze`` hash and nnU-Net commit,
for nnFoundation-style pretrained encoders (``nnunet_pretrained``).
``architecture: starc`` (``star_completion``) trains ``nnUNetTrainerStarC`` on
sha256-bound full-volume ray targets kept outside ``nnUNet_preprocessed`` and
predicts with the two-pass ``StarCPredictor`` (``nnunet_star_trainer``).
Resume recovers at the saved epoch; it does not reproduce discarded prefetched
batches or an interrupted epoch bit for bit.
"""

from __future__ import annotations

import contextlib
import dataclasses
import hashlib
import json
import os
import re
import signal
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

NNUNET_VERSION = "2.8.1"
_CASE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
# Bound trainer allowlist: nnU-Net's own classes are found by name; Segmentary's
# are constructed directly and need manual predictor initialization.
BUILTIN_TRAINERS = frozenset({"nnUNetTrainer"})
PRETRAINED_TRAINER = "nnUNetTrainerPretrainedDS"
STARC_TRAINER = "nnUNetTrainerStarC"
STARC_FINETUNE_TRAINER = "nnUNetTrainerStarCFinetune"
STARC_TRAINERS = frozenset({STARC_TRAINER, STARC_FINETUNE_TRAINER})
# Their defaults (lr 1e-3, 150 epochs) are a fine-tuning recipe, never a baseline.
FINETUNE_TRAINERS = frozenset({"nnUNetTrainerFinetune", STARC_FINETUNE_TRAINER})
SEGMENTARY_TRAINERS = frozenset({"nnUNetTrainerFinetune", PRETRAINED_TRAINER}) | STARC_TRAINERS
TRAINERS = BUILTIN_TRAINERS | SEGMENTARY_TRAINERS
INITIALIZATIONS = ("scratch", "warm_start", "pretrained")
# ``finetune``: a pretrained-encoder recipe; like ``pilot`` it may change only num_epochs.
PURPOSES = ("baseline", "smoke", "overfit", "pilot", "finetune")
OFFICIAL_RUNTIME = "nnunet-2.8.1"
NNSSL_RUNTIME = "nnunet-master-nnssl"
BACKEND_RUNTIMES = (OFFICIAL_RUNTIME, NNSSL_RUNTIME)
TASK07_ONTOLOGY = {"background": 0, "pancreas": 1, "mass": 2}


@dataclass(frozen=True)
class NNUNetConfig:
    """Frozen recipe. Runtime overrides are explicitly non-baseline experiments."""

    workspace: str
    backend_python: str | None = None
    dataset_id: int = 707
    dataset_name: str = "Pancreas"
    resenc: str = "L"
    configuration: str = "3d_fullres"
    fold: int = 0
    gpu: str = "0"
    seed: int = 0
    workers: int = 2
    nnunet_version: str = NNUNET_VERSION
    deterministic: bool = False
    purpose: str = "baseline"
    num_epochs: int | None = None
    num_iterations_per_epoch: int | None = None
    num_val_iterations_per_epoch: int | None = None
    save_probabilities: bool = False
    use_mirroring: bool = False
    tile_step_size: float = 0.5
    architecture: str = "resenc"
    reference_workspace: str | None = None
    reference_plan_binding_sha256: str | None = None
    cv_splits: str | None = None
    cv_splits_sha256: str | None = None
    trainer: str = "nnUNetTrainer"
    initial_lr: float | None = None
    initialization: str = "scratch"
    init_checkpoint: str | None = None
    init_checkpoint_sha256: str | None = None
    init_allowed_missing_prefixes: list[str] | None = None
    hrc_options: dict[str, Any] | None = None
    backend_runtime: str = OFFICIAL_RUNTIME
    runtime_freeze_sha256: str | None = None
    nnunet_commit: str | None = None
    pretrained_plan_name: str | None = None
    output_mode: str = "labels"
    # Ordered [[name, [labels]], ...]: nnU-Net orders region heads by dataset.json labels.
    label_regions: list[list[Any]] | None = None
    regions_class_order: list[int] | None = None
    # architecture=starc: complete options, an external ray-target folder bound by
    # its manifest sha256, and the two-pass predictor settings.
    starc_options: dict[str, Any] | None = None
    starc_targets: str | None = None
    starc_targets_manifest_sha256: str | None = None
    starc_inference: dict[str, Any] | None = None

    def __post_init__(self):
        for name in ("dataset_id", "fold", "seed", "workers"):
            if type(getattr(self, name)) is not int:
                raise ValueError(f"{name} must be an integer, not a boolean or float")
        for name in ("deterministic", "save_probabilities", "use_mirroring"):
            if type(getattr(self, name)) is not bool:
                raise ValueError(f"{name} must be a boolean")
        object.__setattr__(self, "workspace", str(Path(self.workspace).expanduser().resolve()))
        if self.backend_python is not None and not isinstance(self.backend_python, str):
            raise ValueError("backend_python must be an interpreter path string")
        object.__setattr__(
            self,
            "backend_python",
            str(Path(self.backend_python or sys.executable).expanduser().absolute()),
        )
        if isinstance(self.gpu, bool) or not re.fullmatch(r"[0-9]+", str(self.gpu)):
            raise ValueError("gpu must identify one numeric device")
        object.__setattr__(self, "gpu", str(int(self.gpu)))
        if not 1 <= self.dataset_id <= 999 or not re.fullmatch(
            r"[A-Za-z][A-Za-z0-9_]*", self.dataset_name
        ):
            raise ValueError("Use dataset_id 1..999 and an alphanumeric dataset_name")
        if self.resenc not in {"M", "L", "XL"} or self.configuration not in {"3d_fullres", "2d"}:
            raise ValueError("Supported recipes are ResEnc M/L/XL, 3d_fullres or 2d")
        if self.architecture not in {"resenc", "plainconv", "dynunet", "hrc", "starc"}:
            raise ValueError("architecture must be resenc, plainconv, dynunet, hrc, or starc")
        if self.architecture == "hrc":
            from .recipe_plan import validate_hrc_options

            # Bind the complete option set so defaults cannot drift silently.
            object.__setattr__(self, "hrc_options", validate_hrc_options(self.hrc_options))
            if self.deterministic is True:
                # HRC differentiates through avg_pool3d and trilinear interpolation,
                # which have no deterministic CUDA backward in PyTorch.
                raise ValueError("architecture=hrc cannot train with deterministic=true")
        elif self.hrc_options is not None:
            raise ValueError("hrc_options requires architecture=hrc")
        self._validate_trainer_and_initialization()
        self._validate_runtime_and_outputs()
        if self.reference_workspace is not None:
            if not isinstance(self.reference_workspace, str) or not self.reference_workspace:
                raise ValueError("reference_workspace must be a workspace path string")
            reference = str(Path(self.reference_workspace).expanduser().resolve())
            if reference == self.workspace:
                raise ValueError("Reference and destination workspaces must differ")
            object.__setattr__(self, "reference_workspace", reference)
            if not isinstance(self.reference_plan_binding_sha256, str) or not re.fullmatch(
                r"[0-9a-f]{64}", self.reference_plan_binding_sha256
            ):
                raise ValueError("A reference workspace requires its frozen plan-binding SHA256")
        elif self.reference_plan_binding_sha256 is not None:
            raise ValueError("reference_plan_binding_sha256 requires reference_workspace")
        self._validate_starc()
        if self.architecture != "resenc" and (
            self.reference_workspace is None or self.configuration != "3d_fullres"
        ):
            raise ValueError("Architecture transfer requires a reference workspace and 3d_fullres")
        if self.cv_splits is not None:
            if not isinstance(self.cv_splits, str) or not self.cv_splits:
                raise ValueError("cv_splits must be a cross-validation manifest path string")
            object.__setattr__(self, "cv_splits", str(Path(self.cv_splits).expanduser().resolve()))
            if not isinstance(self.cv_splits_sha256, str) or not re.fullmatch(
                r"[0-9a-f]{64}", self.cv_splits_sha256
            ):
                raise ValueError("cv_splits requires its frozen SHA256 in cv_splits_sha256")
            from .cv_splits import MAX_FOLDS

            # The bound manifest's own fold count is enforced before any write.
            if not 0 <= self.fold < MAX_FOLDS:
                raise ValueError(f"Cross-validation folds are 0 to {MAX_FOLDS - 1}")
        elif self.cv_splits_sha256 is not None:
            raise ValueError("cv_splits_sha256 requires cv_splits")
        elif self.fold != 0:
            raise ValueError(
                "This explicit train/val split is fold 0; set cv_splits for other folds"
            )
        if not re.fullmatch(r"[0-9]+", self.gpu) or self.workers < 1 or not 0 <= self.seed < 2**32:
            raise ValueError("Specify one numeric GPU, positive workers, and a uint32 seed")
        if self.nnunet_version != NNUNET_VERSION:
            raise ValueError(f"This adapter is verified for nnunetv2=={NNUNET_VERSION} only")
        if self.purpose not in PURPOSES:
            raise ValueError("purpose must be baseline, smoke, overfit, or pilot")
        overrides = [
            self.num_epochs,
            self.num_iterations_per_epoch,
            self.num_val_iterations_per_epoch,
        ]
        if any(
            x is not None and (not isinstance(x, int) or isinstance(x, bool) or x < 1)
            for x in overrides
        ):
            raise ValueError("Runtime overrides must be positive integers")
        if self.purpose == "baseline" and any(x is not None for x in overrides):
            raise ValueError("Runtime overrides require purpose=smoke, overfit, or pilot")
        if self.purpose in {"pilot", "finetune"} and any(x is not None for x in overrides[1:]):
            # A pilot changes only the epoch count; every epoch keeps 250 updates.
            raise ValueError(f"A {self.purpose} run may override num_epochs only")
        if (
            isinstance(self.tile_step_size, bool)
            or not isinstance(self.tile_step_size, (int, float))
            or not 0 < self.tile_step_size <= 1
        ):
            raise ValueError("tile_step_size must be in (0, 1]")

    def _validate_trainer_and_initialization(self) -> None:
        if self.trainer not in TRAINERS:
            raise ValueError(f"trainer must be one of {sorted(TRAINERS)}")
        if self.initial_lr is not None:
            if (
                isinstance(self.initial_lr, bool)
                or not isinstance(self.initial_lr, (int, float))
                or not 0 < self.initial_lr <= 1
            ):
                raise ValueError("initial_lr must be a positive number no larger than 1")
            if self.trainer not in SEGMENTARY_TRAINERS:
                raise ValueError("initial_lr is a fine-tuning trainer setting")
            object.__setattr__(self, "initial_lr", float(self.initial_lr))
        if self.initialization not in INITIALIZATIONS:
            raise ValueError(f"initialization must be one of {INITIALIZATIONS}")
        if self.trainer in FINETUNE_TRAINERS and (
            self.initialization == "scratch" or self.purpose not in {"pilot", "smoke"}
        ):
            # Its defaults (lr 1e-3, 150 epochs) are a fine-tuning recipe, never a baseline.
            raise ValueError(f"{self.trainer} needs a non-scratch pilot or smoke run")
        if self.trainer == PRETRAINED_TRAINER and (
            self.initialization != "pretrained" or self.purpose not in {"finetune", "smoke"}
        ):
            raise ValueError(f"{self.trainer} needs a pretrained finetune or smoke run")
        if self.purpose == "finetune" and self.trainer != PRETRAINED_TRAINER:
            raise ValueError(f"purpose=finetune is the {PRETRAINED_TRAINER} recipe")
        # STAR-C's own trainer is nnUNetTrainer plus its auxiliary losses, so a
        # full-budget STAR-C baseline keeps every official recipe setting.
        if self.purpose == "baseline" and not (
            self.trainer == "nnUNetTrainer"
            or (self.trainer == STARC_TRAINER and self.architecture == "starc")
        ):
            raise ValueError("A baseline uses the official nnUNetTrainer recipe")
        if self.purpose == "baseline" and self.initial_lr is not None:
            raise ValueError("A baseline keeps the official initial learning rate")
        prefixes = self.init_allowed_missing_prefixes
        if prefixes is None:
            prefixes = []
        if not isinstance(prefixes, (list, tuple)) or any(
            not isinstance(prefix, str) or not re.fullmatch(r"[A-Za-z0-9_.]+\.", prefix)
            for prefix in prefixes
        ):
            raise ValueError("init_allowed_missing_prefixes must be module prefixes ending in '.'")
        object.__setattr__(self, "init_allowed_missing_prefixes", sorted(set(prefixes)))
        if self.initialization == "scratch":
            if (
                self.init_checkpoint is not None
                or self.init_checkpoint_sha256 is not None
                or self.init_allowed_missing_prefixes
            ):
                raise ValueError("Scratch initialization takes no initial checkpoint")
            return
        if (
            not isinstance(self.init_checkpoint, str)
            or not Path(self.init_checkpoint).is_absolute()
        ):
            raise ValueError("Non-scratch initialization needs an absolute init_checkpoint")
        if not isinstance(self.init_checkpoint_sha256, str) or not re.fullmatch(
            r"[0-9a-f]{64}", self.init_checkpoint_sha256
        ):
            raise ValueError("Non-scratch initialization needs init_checkpoint_sha256")
        checkpoint = Path(self.init_checkpoint).resolve()
        if checkpoint.is_relative_to(self.workspace):
            raise ValueError("The initial checkpoint must live outside this workspace")
        object.__setattr__(self, "init_checkpoint", str(checkpoint))

    def _validate_runtime_and_outputs(self) -> None:
        """Bind the backend environment and the label mode; both fail closed."""
        if self.backend_runtime not in BACKEND_RUNTIMES:
            raise ValueError(f"backend_runtime must be one of {BACKEND_RUNTIMES}")
        nnssl = self.backend_runtime == NNSSL_RUNTIME
        if nnssl:
            if not isinstance(self.runtime_freeze_sha256, str) or not re.fullmatch(
                r"[0-9a-f]{64}", self.runtime_freeze_sha256
            ):
                raise ValueError("The nnssl runtime needs its pip-freeze runtime_freeze_sha256")
            if not isinstance(self.nnunet_commit, str) or not re.fullmatch(
                r"[0-9a-f]{40}", self.nnunet_commit
            ):
                raise ValueError("The nnssl runtime needs the full nnU-Net source nnunet_commit")
            if not isinstance(self.pretrained_plan_name, str) or not re.fullmatch(
                r"[A-Za-z0-9][A-Za-z0-9_]*", self.pretrained_plan_name
            ):
                raise ValueError("The nnssl runtime needs an identifier pretrained_plan_name")
            if self.trainer != PRETRAINED_TRAINER or self.initialization != "pretrained":
                raise ValueError(f"The nnssl runtime runs {PRETRAINED_TRAINER} from pretrained")
            if self.reference_workspace is None or self.configuration != "3d_fullres":
                # Wave 1 arrays are copied, never re-preprocessed by a different nnU-Net.
                raise ValueError("The nnssl runtime needs a reference workspace and 3d_fullres")
            if self.output_mode != "labels":
                raise ValueError("Region mode is verified for the nnU-Net 2.8.1 runtime only")
        elif (
            self.runtime_freeze_sha256 is not None
            or self.nnunet_commit is not None
            or self.pretrained_plan_name is not None
        ):
            raise ValueError("Runtime freeze, commit and pretrained plan bind the nnssl runtime")
        elif self.trainer == PRETRAINED_TRAINER:
            raise ValueError(f"{PRETRAINED_TRAINER} exists only in the nnssl runtime")
        if self.output_mode not in ("labels", "regions"):
            raise ValueError("output_mode must be labels or regions")
        if self.output_mode == "labels":
            if self.label_regions is not None or self.regions_class_order is not None:
                raise ValueError(
                    "label_regions and regions_class_order require output_mode=regions"
                )
        else:
            from .nnunet_regions import regions_ontology, validate_regions

            # Without a recipe the Task07 regions apply; an explicit recipe (for
            # example KiTS23's) is rechecked against the manifest at prepare.
            ontology = (
                TASK07_ONTOLOGY
                if self.label_regions is None
                else regions_ontology(self.label_regions)
            )
            regions, order = validate_regions(
                ontology, self.label_regions, self.regions_class_order
            )
            object.__setattr__(self, "label_regions", regions)
            object.__setattr__(self, "regions_class_order", order)
        if self.hrc_options is not None:
            expected = "regions" if self.output_mode == "regions" else "softmax"
            if self.hrc_options["output_mode"] != expected:
                raise ValueError(
                    f"HRC output_mode must be {expected} for output_mode={self.output_mode}"
                )

    def _validate_starc(self) -> None:
        """Bind STAR-C's options, targets and predictor; refuse them for other models."""
        fields = (
            self.starc_options,
            self.starc_targets,
            self.starc_targets_manifest_sha256,
            self.starc_inference,
        )
        if self.architecture != "starc":
            if any(value is not None for value in fields):
                raise ValueError("starc_options, starc_targets and starc_inference need starc")
            if self.trainer in STARC_TRAINERS:
                raise ValueError(f"{self.trainer} trains architecture=starc only")
            return
        from .recipe_plan import validate_starc_inference, validate_starc_options

        if self.trainer not in STARC_TRAINERS:
            raise ValueError(f"architecture=starc trains with one of {sorted(STARC_TRAINERS)}")
        if self.deterministic is True:
            # grid_sample, gather and index_put backward passes have no deterministic CUDA kernels.
            raise ValueError("architecture=starc cannot train with deterministic=true")
        if self.output_mode == "regions" and "fusion_channels" not in (self.starc_options or {}):
            # The softmax defaults [1, 2] name other heads in region mode; never assume them.
            raise ValueError("Region-mode STAR-C must declare its fusion_channels")
        options = validate_starc_options(self.starc_options)
        object.__setattr__(self, "starc_options", options)
        object.__setattr__(self, "starc_inference", validate_starc_inference(self.starc_inference))
        if options["freeze_backbone"] and (
            self.initialization == "scratch" or options["fusion"] == "aux_only"
        ):
            # A frozen random backbone, or frozen logits with no fusion, trains nothing useful.
            raise ValueError("freeze_backbone needs a non-scratch backbone and gated fusion")
        if not isinstance(self.starc_targets, str) or not Path(self.starc_targets).is_absolute():
            raise ValueError("architecture=starc needs an absolute starc_targets folder")
        targets = Path(self.starc_targets).resolve()
        # The workspace's nnUNet_preprocessed is hashed whole, and the reference is frozen.
        for owner in (self.workspace, self.reference_workspace):
            if owner is not None and targets.is_relative_to(Path(owner).expanduser().resolve()):
                raise ValueError(
                    "STAR-C targets must live outside this and the reference workspace"
                )
        object.__setattr__(self, "starc_targets", str(targets))
        if not isinstance(self.starc_targets_manifest_sha256, str) or not re.fullmatch(
            r"[0-9a-f]{64}", self.starc_targets_manifest_sha256
        ):
            raise ValueError("architecture=starc needs starc_targets_manifest_sha256")

    @property
    def architecture_options(self) -> dict[str, Any] | None:
        """The bound network options of an architecture transfer, if any."""
        return self.starc_options if self.architecture == "starc" else self.hrc_options

    @property
    def dataset(self) -> str:
        return f"Dataset{self.dataset_id:03d}_{self.dataset_name}"

    @property
    def reference_plans(self) -> str:
        """The ResEnc planner's identifier, shared with any reference workspace."""
        return f"nnUNetResEncUNet{self.resenc}Plans"

    @property
    def plans(self) -> str:
        """The plans identifier this run trains with (nnssl: nnU-Net's plan_like_dynamic)."""
        if self.backend_runtime == NNSSL_RUNTIME:
            return f"ptPlans_dynamic__{self.pretrained_plan_name}"
        return self.reference_plans

    @property
    def model(self) -> str:
        return (
            f"nnunet_resenc_{self.resenc.lower()}"
            if self.architecture == "resenc"
            else f"nnunet_planned_{self.architecture}"
        )

    @property
    def root(self) -> Path:
        return Path(self.workspace)

    @property
    def preprocessed(self) -> Path:
        return self.root / "nnUNet_preprocessed" / self.dataset

    @property
    def model_folder(self) -> Path:
        return (
            self.root
            / "nnUNet_results"
            / self.dataset
            / f"{self.trainer}__{self.plans}__{self.configuration}"
        )

    @property
    def fold_folder(self) -> Path:
        return self.model_folder / f"fold_{self.fold}"


def _sha(path: str | Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def _digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def _json(path: Path) -> dict:
    return json.loads(path.read_text())


def _atomic_json(path: Path, value: Any, *, sort_keys: bool = True):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with tmp.open("x") as f:
            json.dump(value, f, indent=2, sort_keys=sort_keys, allow_nan=False)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def _check_hash(path: str | Path, expected: str):
    if not expected or _sha(path) != expected:
        raise ValueError(f"Content hash changed or missing: {path}")


def _write_dataset_json(config: NNUNetConfig, path: Path, value: dict) -> None:
    # Region heads follow the order of ``labels``; never sort a region dataset.json.
    _atomic_json(path, value, sort_keys=config.output_mode != "regions")


def _same_dataset_json(actual: dict, expected: dict) -> bool:
    from .nnunet_regions import same_dataset_json

    return same_dataset_json(actual, expected)


def _dataset_json(config: NNUNetConfig, ontology: dict, cases: int) -> dict:
    """The nnU-Net dataset.json this config trains with (region form when opted in)."""
    base = {
        "channel_names": {"0": "CT"},
        "labels": ontology,
        "numTraining": cases,
        "file_ending": ".nii.gz",
        "overwrite_image_reader_writer": "NibabelIO",
    }
    if config.output_mode != "regions":
        return base
    from .nnunet_regions import region_dataset_json

    assert config.label_regions is not None and config.regions_class_order is not None
    return region_dataset_json(ontology, config.label_regions, config.regions_class_order, base)


def _code_identity() -> dict:
    identity = {p.name: _sha(p) for p in sorted(Path(__file__).parent.glob("*.py"))}
    # Workers enforce the shared-host GPU guard, so it is part of the code identity.
    identity["../gpu_policy.py"] = _sha(Path(__file__).parents[1] / "gpu_policy.py")
    return identity


def _documents(manifest_path: str | Path, splits_path: str | Path) -> tuple[dict, dict]:
    from segmentary.medical.data import load_manifest, validate_splits

    # Loading manifest metadata must not open held-out image or label payloads.
    manifest = load_manifest(manifest_path, verify_files=False)
    splits = _json(Path(splits_path))
    validate_splits(manifest, splits)
    if not manifest.get("audit", {}).get("passed"):
        raise ValueError("An audited manifest with audit.passed=true is required")
    from segmentary.medical.dataset_profiles import profile_for_ontology

    # Task07/PanTS pancreas/mass, MSD Task03 liver/tumor or KiTS23 kidney/tumor/cyst.
    profile_for_ontology(manifest["ontology"])
    if not splits["train"] or not splits["val"]:
        raise ValueError("Nonempty train and validation groups are required")
    for case in manifest["cases"]:
        if not _CASE_ID.fullmatch(case["case_id"]):
            raise ValueError(f"Unsafe case identifier: {case['case_id']}")
    return manifest, splits


def _cross_validation(
    config: NNUNetConfig, manifest: dict, splits: dict, splits_path
) -> dict | None:
    """The bound CV manifest for this config, verified against the frozen split."""
    if config.cv_splits is None:
        return None
    from .cv_splits import validate_cv_splits

    _check_hash(config.cv_splits, config.cv_splits_sha256 or "")
    cv = _json(Path(config.cv_splits))
    if cv.get("base_splits_sha256") != _sha(splits_path):
        raise ValueError("Cross-validation manifest was derived from a different split file")
    validate_cv_splits(manifest, splits, cv)
    if not config.fold < len(cv["folds"]):
        raise ValueError(f"Fold {config.fold} is outside the {len(cv['folds'])}-fold manifest")
    return cv


def _nnunet_folds(cv: dict | None, splits: dict) -> list[dict]:
    from .cv_splits import nnunet_splits

    return [{"train": splits["train"], "val": splits["val"]}] if cv is None else nnunet_splits(cv)


def _fold_cases(config: NNUNetConfig, binding: dict, partition: str) -> list[str]:
    """Training/validation case IDs for this config's fold; other partitions are unchanged."""
    if config.cv_splits is None or partition not in {"train", "val"}:
        return list(_json(Path(binding["splits_path"]))[partition])
    manifest, splits = _documents(binding["manifest_path"], binding["splits_path"])
    cv = _cross_validation(config, manifest, splits, binding["splits_path"])
    assert cv is not None
    return list(cv["folds"][config.fold][partition])


def _check_ontology_defaults(config: NNUNetConfig, ontology: dict[str, int]) -> None:
    """Refuse Task07 defaults that validate structurally on another dataset's labels.

    Region recipes must decode losslessly to the manifest's label map and, outside
    Task07, name that dataset's own regions (the Task07 default would otherwise
    train LiTS liver/tumor heads named pancreas/mass). Label-mode HRC host and
    lesion channels must be foreground labels that together cover every one
    (the defaults [1]/[2] would silently ignore KiTS23 cysts).
    """
    from .dataset_profiles import PANCREAS, profile_for_ontology

    profile = profile_for_ontology(ontology)
    if config.output_mode == "regions":
        from .nnunet_regions import validate_regions

        # The recipe must decode losslessly to this manifest's own label map.
        regions, _ = validate_regions(ontology, config.label_regions, config.regions_class_order)
        allowed = {name for name, _ in profile.nnunet_regions}
        if profile is not PANCREAS and not {name for name, _ in regions} <= allowed:
            raise ValueError(
                f"Region names must be {profile.name} regions {sorted(allowed)}; "
                "the Task07 default recipe does not apply"
            )
    if config.hrc_options is not None and config.output_mode == "labels":
        foreground = {value for name, value in ontology.items() if name != "background"}
        host = set(config.hrc_options["host_channels"])
        lesion = set(config.hrc_options["lesion_channels"])
        if host | lesion != foreground:
            raise ValueError(
                "HRC host_channels and lesion_channels must be foreground labels that "
                f"together cover {sorted(foreground)} for this manifest"
            )


def prepare_dataset(
    manifest_path: str | Path,
    splits_path: str | Path,
    config: NNUNetConfig,
    *,
    dry_run: bool = False,
) -> dict:
    """Create a fresh isolated nnU-Net dataset; source files are read-only symlinks.

    Validation contributes to the dataset fingerprint/planner, matching ordinary
    nnU-Net development-set preprocessing. Test data is absent from this layout.
    No overwrite/automatic reuse is allowed, including after partial preparation.
    """
    manifest_path, splits_path = Path(manifest_path).resolve(), Path(splits_path).resolve()
    manifest, splits = _documents(manifest_path, splits_path)
    cv = _cross_validation(config, manifest, splits, splits_path)
    folds = _nnunet_folds(cv, splits)
    _check_ontology_defaults(config, manifest["ontology"])
    if config.root.exists() and any(config.root.iterdir()):
        raise FileExistsError(f"Use an empty workspace: {config.root}")
    initial = _initial_checkpoint_record(
        config, manifest_sha256=_sha(manifest_path), splits_sha256=_sha(splits_path)
    )
    starc_targets = _starc_targets_binding(config)
    lookup = {c["case_id"]: c for c in manifest["cases"]}
    development = [lookup[x] for x in splits["train"] + splits["val"]]
    for case in development:
        if case["annotation_status"] != "labeled" or not case.get("label"):
            raise ValueError("Joint organ/lesion training requires fully labeled development cases")
        for key in ("image", "label"):
            if not str(case[key]).endswith(".nii.gz"):
                raise ValueError("The nnU-Net adapter currently stages .nii.gz files only")
            _check_hash(case[key], case[f"{key}_sha256"])
    binding = {
        "schema_version": 1,
        "config": dataclasses.asdict(config),
        "manifest_path": str(manifest_path),
        "splits_path": str(splits_path),
        "manifest_sha256": _sha(manifest_path),
        "splits_sha256": _sha(splits_path),
        "manifest_fingerprint": manifest["fingerprint"],
        "split_fingerprint": splits["fingerprint"],
        "ontology": manifest["ontology"],
        "code": _code_identity(),
        "planning_scope": "train_and_val_only",
        "development_cases": [c["case_id"] for c in development],
        "held_out_cases": list(splits["test"]),
        "initialization": config.initialization,
        "checkpoint_selection": "official_ema_foreground_dice",
    }
    if initial is not None:
        binding["initial_checkpoint"] = initial
    if starc_targets is not None:
        binding["starc_targets"] = starc_targets
    if cv is not None:
        binding["cross_validation"] = {
            "path": config.cv_splits,
            "sha256": config.cv_splits_sha256,
            "fingerprint": cv["fingerprint"],
            "fold": config.fold,
            "fold_count": len(cv["folds"]),
        }
    result = {
        "action": "prepare",
        "dry_run": dry_run,
        "workspace": config.workspace,
        "fold": config.fold,
        "train_cases": len(folds[config.fold]["train"]),
        "val_cases": len(folds[config.fold]["val"]),
        "test_cases_excluded": len(splits["test"]),
        "identity": _digest(binding),
    }
    if dry_run:
        return result
    config.root.mkdir(parents=True, exist_ok=True)
    raw = config.root / "nnUNet_raw" / config.dataset
    for directory in (
        raw / "imagesTr",
        raw / "labelsTr",
        config.preprocessed,
        config.root / "nnUNet_results",
    ):
        directory.mkdir(parents=True, exist_ok=True)
    for case in development:
        (raw / "imagesTr" / f"{case['case_id']}_0000.nii.gz").symlink_to(
            Path(case["image"]).resolve()
        )
        (raw / "labelsTr" / f"{case['case_id']}.nii.gz").symlink_to(Path(case["label"]).resolve())
    _write_dataset_json(
        config, raw / "dataset.json", _dataset_json(config, manifest["ontology"], len(development))
    )
    _atomic_json(config.preprocessed / "splits_final.json", folds)
    _atomic_json(config.root / "binding.json", binding)
    _atomic_json(config.root / "resolved-config.json", dataclasses.asdict(config))
    _atomic_json(config.root / "preparation.json", result)
    return result


def _starc_targets_binding(config: NNUNetConfig) -> dict[str, str] | None:
    """The bound STAR-C target folder; its manifest must still hash to the bound value."""
    if config.architecture != "starc":
        return None
    from .recipe_plan import STARC_TARGET_MANIFEST

    assert config.starc_targets is not None and config.starc_targets_manifest_sha256 is not None
    _check_hash(
        Path(config.starc_targets) / STARC_TARGET_MANIFEST, config.starc_targets_manifest_sha256
    )
    return {
        "path": config.starc_targets,
        "manifest_sha256": config.starc_targets_manifest_sha256,
    }


def verify_starc_target_manifest(
    folder: str | Path,
    manifest_sha256: str,
    *,
    options: dict[str, Any],
    configuration: str,
    plan_configuration: dict[str, Any],
    plans_sha256: str | None,
    splits_sha256: str,
    development: list[str],
    held_out: list[str],
    segmentations: dict[str, tuple[str, str]],
) -> dict[str, Any]:
    """Prove a STAR-C target folder was computed from these development labels (Torch-free).

    The manifest must hash to the bound value and name the frozen ResEnc plan
    (``plans_sha256``), its spacing and data folder, the bound rays and lesion
    labels, and a held-out check against this split file (``--forbid-cases-from``
    with key ``test``). It must list exactly the development cases. Each case's
    source segmentation must be ``segmentations[case]`` (file name and sha256),
    and each target file must hash to its manifest entry. The trainer
    re-verifies the manifest, the ray set and every hash before training.
    """
    from .recipe_plan import (
        STARC_TARGET_MANIFEST,
        STARC_TARGET_SCHEMA,
        starc_target_method_problems,
    )

    folder = Path(folder)
    _check_hash(folder / STARC_TARGET_MANIFEST, manifest_sha256)
    manifest = _json(folder / STARC_TARGET_MANIFEST)
    spacing = manifest.get("spacing")
    expected_spacing = plan_configuration["spacing"]
    forbidden = manifest.get("forbidden_cases_checked") or {}
    problems = [
        name
        for name, ok in (
            ("schema", manifest.get("schema") == STARC_TARGET_SCHEMA),
            ("rays", manifest.get("rays") == options["rays"]),
            ("lesion_labels", manifest.get("lesion_labels") == options["lesion_labels"]),
            ("configuration", manifest.get("configuration") == configuration),
            (
                "data_identifier",
                manifest.get("data_identifier") == plan_configuration["data_identifier"],
            ),
            (
                "spacing",
                isinstance(spacing, list)
                and len(spacing) == len(expected_spacing)
                and all(
                    abs(float(a) - float(b)) <= 1e-6
                    for a, b in zip(spacing, expected_spacing, strict=True)
                ),
            ),
            (
                "plans_sha256",
                plans_sha256 is not None and manifest.get("plans_sha256") == plans_sha256,
            ),
            (
                "forbidden_cases_checked",
                forbidden.get("sha256") == splits_sha256 and forbidden.get("key") == "test",
            ),
        )
        if not ok
    ]
    problems += starc_target_method_problems(manifest)
    if problems:
        raise ValueError(f"STAR-C targets do not match this experiment: {problems}")
    entries = manifest.get("cases")
    if not isinstance(entries, dict) or set(entries) != set(development):
        raise ValueError("STAR-C targets must cover exactly the development cases")
    if set(entries) & set(held_out):
        raise ValueError("STAR-C targets include held-out cases")
    for case in development:
        entry = entries[case]
        if case not in segmentations or (
            entry.get("segmentation"),
            entry.get("segmentation_sha256"),
        ) != tuple(segmentations[case]):
            raise ValueError(f"STAR-C targets were computed from another segmentation: {case}")
        _check_hash(folder / f"{case}.npz", entry.get("sha256", ""))
    code = manifest.get("code", {})
    return {
        "path": str(folder),
        "manifest_sha256": manifest_sha256,
        "cases": len(development),
        "components": sum(int(entries[case].get("components", 0)) for case in development),
        "rays": manifest["rays"],
        "lesion_labels": manifest["lesion_labels"],
        "spacing": spacing,
        "plans_sha256": manifest["plans_sha256"],
        "forbidden_cases_checked": forbidden,
        "code": code,
        # The method fields are enforced above; the code hash is a record only
        # (a refactor of star_completion.py does not change the targets).
        "method": {key: manifest[key] for key in ("connectivity", "directions", "march")},
        "computed_with_current_star_completion": code.get("star_completion.py")
        == _sha(Path(__file__).with_name("star_completion.py")),
    }


def _check_starc_targets(config: NNUNetConfig, binding: dict, plan: dict) -> dict[str, Any]:
    """The bound targets against this workspace's own copied segmentations."""
    assert config.starc_options is not None and config.starc_targets is not None
    selected = plan["configurations"][config.configuration]
    folder = config.preprocessed / selected["data_identifier"]
    segmentations = {}
    for case in binding["development_cases"]:
        found = [
            name for name in (f"{case}_seg.b2nd", f"{case}_seg.npy") if (folder / name).is_file()
        ]
        if len(found) != 1:
            raise ValueError(f"Cannot identify the preprocessed segmentation of {case}")
        segmentations[case] = (found[0], _sha(folder / found[0]))
    record = verify_starc_target_manifest(
        config.starc_targets,
        config.starc_targets_manifest_sha256 or "",
        options=config.starc_options,
        configuration=config.configuration,
        plan_configuration=selected,
        plans_sha256=_reference_index(config).get(f"{config.reference_plans}.json"),
        splits_sha256=binding["splits_sha256"],
        development=list(binding["development_cases"]),
        held_out=list(binding["held_out_cases"]),
        segmentations=segmentations,
    )
    return {**record, "segmentations_equal_workspace": True}


def _segmentary_workspace(checkpoint: Path) -> Path | None:
    """The Segmentary workspace that wrote an nnU-Net checkpoint, if any."""
    for parent in checkpoint.parents:
        if (parent / "binding.json").is_file():
            return parent
    return None


def _warm_start_source(
    config: NNUNetConfig, *, manifest_sha256: str, splits_sha256: str
) -> dict[str, Any]:
    """Prove a warm start never saw this fold's validation cases.

    The checkpoint must be one indexed by a Segmentary nnU-Net workspace that
    trained the same dataset, cohort, CV manifest and fold. Without this, a
    hand-written recipe could initialise fold k from a fold-j checkpoint whose
    training set contains fold k's validation cases.
    """
    checkpoint = Path(str(config.init_checkpoint))
    workspace = _segmentary_workspace(checkpoint)
    if (
        workspace is None
        or len(checkpoint.relative_to(workspace).parts) != 5
        or checkpoint.relative_to(workspace).parts[0] != "nnUNet_results"
    ):
        raise ValueError("A warm start must use a checkpoint from a Segmentary nnU-Net workspace")
    binding = _json(workspace / "binding.json")
    source = binding.get("config", {})
    index = _json(workspace / "checkpoint-index.json")
    if index.get(checkpoint.name, {}).get("sha256") != config.init_checkpoint_sha256:
        raise ValueError("The initial checkpoint is not the one its workspace indexed")
    if (
        Path(str(source.get("workspace"))).resolve() != workspace.resolve()
        or source.get("dataset_id") != config.dataset_id
        or source.get("configuration") != config.configuration
        or source.get("fold") != config.fold
        or source.get("cv_splits_sha256") != config.cv_splits_sha256
        or binding.get("manifest_sha256") != manifest_sha256
        or binding.get("splits_sha256") != splits_sha256
    ):
        raise ValueError(
            "A warm start must come from the same dataset, cohort, CV manifest and fold"
        )
    return {
        "source_workspace": str(workspace),
        "source_binding_sha256": _sha(workspace / "binding.json"),
        "source_fold": source.get("fold"),
        "source_seed": source.get("seed"),
        "source_initialization": binding.get("initialization", "scratch"),
        "source_cv_splits_sha256": source.get("cv_splits_sha256"),
    }


def _initial_checkpoint_record(
    config: NNUNetConfig, *, manifest_sha256: str, splits_sha256: str
) -> dict | None:
    """Verify a non-scratch initial checkpoint against its bound SHA256 and origin."""
    if config.initialization == "scratch":
        return None
    assert config.init_checkpoint is not None and config.init_checkpoint_sha256 is not None
    _check_hash(config.init_checkpoint, config.init_checkpoint_sha256)
    record: dict[str, Any] = {
        "path": config.init_checkpoint,
        "sha256": config.init_checkpoint_sha256,
        "allowed_missing_prefixes": list(config.init_allowed_missing_prefixes or []),
    }
    if config.initialization == "warm_start":
        record["source"] = _warm_start_source(
            config, manifest_sha256=manifest_sha256, splits_sha256=splits_sha256
        )
    elif _segmentary_workspace(Path(config.init_checkpoint)) is not None:
        # Segmentary checkpoints saw development cases; only warm_start proves the fold.
        raise ValueError("Checkpoints from a Segmentary workspace need initialization=warm_start")
    return record


def _binding(config: NNUNetConfig, *, verify_development: bool = True) -> dict:
    binding = _json(config.root / "binding.json")
    if binding["config"] != dataclasses.asdict(config) or binding["code"] != _code_identity():
        raise ValueError(
            "Configuration or backend source changed; create a new experiment workspace"
        )
    _check_hash(binding["manifest_path"], binding["manifest_sha256"])
    _check_hash(binding["splits_path"], binding["splits_sha256"])
    if verify_development:
        manifest, splits = _documents(binding["manifest_path"], binding["splits_path"])
        cv = _cross_validation(config, manifest, splits, binding["splits_path"])
        expected = _nnunet_folds(cv, splits)
        if json.loads((config.preprocessed / "splits_final.json").read_text()) != expected:
            raise ValueError("nnU-Net development split changed")
        raw = config.root / "nnUNet_raw" / config.dataset
        if {p.name for p in (raw / "imagesTr").iterdir()} != {
            f"{x}_0000.nii.gz" for x in binding["development_cases"]
        }:
            raise ValueError("Raw image membership changed (possible held-out contamination)")
        if {p.name for p in (raw / "labelsTr").iterdir()} != {
            f"{x}.nii.gz" for x in binding["development_cases"]
        }:
            raise ValueError("Raw label membership changed")
        for case in manifest["cases"]:
            if case["case_id"] in binding["development_cases"]:
                _check_hash(
                    raw / "imagesTr" / f"{case['case_id']}_0000.nii.gz", case["image_sha256"]
                )
                _check_hash(raw / "labelsTr" / f"{case['case_id']}.nii.gz", case["label_sha256"])
        expected_json = _dataset_json(
            config, binding["ontology"], len(binding["development_cases"])
        )
        if not _same_dataset_json(_json(raw / "dataset.json"), expected_json):
            raise ValueError("Raw dataset ontology or modality configuration changed")
    return binding


def _runtime(config: NNUNetConfig, *, environment: dict[str, str] | None = None) -> dict:
    """Probe the worker interpreter, independently of the RGB harness environment.

    nnU-Net's dynamic-network-architectures dependency constrains packages
    differently from Segmentary's RGB stack. Only lightweight medical modules
    cross that interpreter boundary through PYTHONPATH.
    """
    code = (
        "import importlib.metadata as m,json,sys; "
        "packages=dict(sorted((d.metadata['Name'],d.version) for d in m.distributions() if 'Name' in d.metadata)); "
        "print(json.dumps({'python':sys.version,'executable':sys.executable,'packages':packages}))"
    )
    completed = subprocess.run(
        [str(config.backend_python), "-c", code],
        env=_environment(config) if environment is None else environment,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if completed.returncode:
        raise RuntimeError(f"Cannot inspect backend interpreter: {completed.stderr.strip()}")
    try:
        runtime = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Backend interpreter did not return runtime metadata") from exc
    installed = runtime["packages"].get("nnunetv2")
    if installed != NNUNET_VERSION:
        raise RuntimeError(
            f"Expected nnunetv2=={NNUNET_VERSION} in {config.backend_python}, found {installed}; use a separate nnU-Net environment"
        )
    if config.backend_runtime == NNSSL_RUNTIME:
        from .nnunet_pretrained import runtime_identity

        # nnU-Net master also reports 2.8.1: bind the exact environment and source.
        identity = runtime_identity(
            str(config.backend_python),
            _environment(config) if environment is None else environment,
        )
        if identity["pip_freeze_sha256"] != config.runtime_freeze_sha256:
            raise RuntimeError("The nnssl environment's pip freeze differs from the bound hash")
        if identity["nnunetv2_commit"] != config.nnunet_commit:
            raise RuntimeError(
                "The nnssl environment's nnU-Net source differs from the bound commit"
            )
        runtime["nnssl"] = identity
    return runtime


@contextlib.contextmanager
def _lock(path: Path):
    import fcntl

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError(f"Resource is already in use: {path}") from exc
        try:
            yield handle.fileno()
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def _gpu_lock(config: NNUNetConfig) -> Path:
    root = Path(
        os.environ.get(
            "SEGMENTARY_MEDICAL_LOCK_DIR",
            str(Path(tempfile.gettempdir()) / f"segmentary-medical-{os.getuid()}"),
        )
    )
    return root / f"gpu-{config.gpu}.lock"


def _refuse_forbidden_gpu(*gpus: str) -> None:
    """Fail closed before exposing a GPU reserved for other users (see gpu_policy)."""
    from segmentary.gpu_policy import GpuPolicyError, refuse_forbidden

    try:
        refuse_forbidden(gpus)
    except GpuPolicyError as exc:
        raise ValueError(str(exc)) from exc


def _require_worker_devices(gpu: str) -> None:
    """Fail closed unless the launcher exposed exactly ``gpu`` in PCI bus order.

    Launchers always set both variables. A worker started by hand with
    ``CUDA_VISIBLE_DEVICES`` unset would otherwise see every GPU, and
    ``cuda:0`` would be physical GPU 0. ``gpu == "cpu"`` requires an empty list.
    """
    visible = os.environ.get("CUDA_VISIBLE_DEVICES")
    if visible is None:
        raise ValueError("Worker requires CUDA_VISIBLE_DEVICES from its launcher; refusing")
    tokens = [token.strip() for token in visible.split(",") if token.strip()]
    _refuse_forbidden_gpu(*tokens)
    if tokens != ([] if gpu == "cpu" else [gpu]):
        raise ValueError(
            f"Worker CUDA_VISIBLE_DEVICES={visible!r} does not expose exactly GPU {gpu!r}"
        )
    if os.environ.get("CUDA_DEVICE_ORDER") != "PCI_BUS_ID":
        raise ValueError("Worker requires CUDA_DEVICE_ORDER=PCI_BUS_ID")


def _environment(config: NNUNetConfig, *, action: str | None = None) -> dict[str, str]:
    """Zero workers selects synchronous augmentation only in the training stage.

    nnU-Net 2.8.1 also uses nnUNet_n_proc_DA as the planner's Torch thread count,
    where zero is invalid. Planning, prediction and metadata probes use positive
    worker counts. The trainer explicitly supports zero augmentation workers.
    """
    env = dict(os.environ)
    inherited_devices = env.get("CUDA_VISIBLE_DEVICES")
    if inherited_devices is not None:
        tokens = [value.strip() for value in inherited_devices.split(",")]
        if not all(re.fullmatch(r"[0-9]+", value) for value in tokens):
            raise ValueError(
                "Inherited CUDA_VISIBLE_DEVICES is disabled or uses unsupported UUID/MIG identifiers"
            )
        if config.gpu not in {str(int(value)) for value in tokens}:
            raise ValueError("Requested GPU is outside inherited CUDA_VISIBLE_DEVICES")
    _refuse_forbidden_gpu(config.gpu)
    env.update(
        {
            name: str(config.root / name)
            for name in ("nnUNet_raw", "nnUNet_preprocessed", "nnUNet_results")
        }
    )
    env.update(
        {
            "CUDA_VISIBLE_DEVICES": config.gpu,
            "CUDA_DEVICE_ORDER": "PCI_BUS_ID",
            "PYTHONHASHSEED": str(config.seed),
            "nnUNet_n_proc_DA": "0"
            if action == "train" and config.deterministic
            else str(config.workers),
            "nnUNet_compile": "false",
            "OMP_NUM_THREADS": str(config.workers),
            "MKL_NUM_THREADS": str(config.workers),
            "PYTHONUNBUFFERED": "1",
            "CUBLAS_WORKSPACE_CONFIG": ":4096:8",
            "HF_HUB_OFFLINE": "1",
            "WANDB_MODE": "disabled",
            "PYTHONPATH": str(Path(__file__).resolve().parents[2]),
            "PYTHONNOUSERSITE": "1",
        }
    )
    return env


def _stop_child(process):
    if process is None or process.poll() is not None:
        return
    with contextlib.suppress(ProcessLookupError):
        os.killpg(process.pid, signal.SIGTERM)
    try:
        process.wait(timeout=30)
    except subprocess.TimeoutExpired:
        with contextlib.suppress(ProcessLookupError):
            os.killpg(process.pid, signal.SIGKILL)
        process.wait()


def _run(config: NNUNetConfig, action: str, payload: dict, *, gpu: bool = False) -> dict:
    """Synchronous child lifecycle. Terminal outcomes are persisted even on failure."""
    runtime = _runtime(config)
    identity = _digest({"binding": _binding(config, verify_development=False), "runtime": runtime})
    action_id = f"{action}-{time.time_ns()}"
    directory = config.root / "stages" / action_id
    with contextlib.ExitStack() as stack:
        lock_fds = [stack.enter_context(_lock(config.root / ".stage.lock"))]
        if gpu:
            lock_fds.append(stack.enter_context(_lock(_gpu_lock(config))))
        directory.mkdir(parents=True)
        request = {
            "config": dataclasses.asdict(config),
            "action": action,
            "payload": payload,
            "identity": identity,
        }
        _atomic_json(directory / "request.json", request)
        _atomic_json(directory / "runtime.json", runtime)
        argv = [
            str(config.backend_python),
            "-m",
            "segmentary.medical.backend",
            "_worker",
            str(directory / "request.json"),
        ]
        state: dict[str, Any] = {
            "action": action,
            "action_id": action_id,
            "status": "starting",
            "started_at": time.time(),
            "argv": argv,
            "identity": identity,
            "log": str(directory / "subprocess.log"),
        }
        state_path = config.root / "active-stage.json"
        _atomic_json(state_path, state)
        process = None
        previous_sigterm = None
        if threading.current_thread() is threading.main_thread():
            previous_sigterm = signal.getsignal(signal.SIGTERM)

            def terminate_parent(_signum, _frame):
                raise KeyboardInterrupt("Termination requested")

            signal.signal(signal.SIGTERM, terminate_parent)
        try:
            with (directory / "subprocess.log").open("wb") as log:
                process = subprocess.Popen(
                    argv,
                    env=_environment(config, action=action),
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                    pass_fds=tuple(lock_fds),
                )
                state.update(status="running", pid=process.pid)
                _atomic_json(state_path, state)
                returncode = process.wait()
            state.update(returncode=returncode, status="completed" if returncode == 0 else "failed")
            if returncode in (-signal.SIGTERM, -signal.SIGINT, 130, 143):
                state["status"] = "cancelled"
            if returncode:
                raise RuntimeError(
                    f"{action} {state['status']} (exit {returncode}); see {state['log']}"
                )
        except KeyboardInterrupt:
            _stop_child(process)
            state["status"] = "cancelled"
            raise
        except BaseException as exc:
            _stop_child(process)
            if state["status"] not in {"failed", "cancelled"}:
                state["status"] = "failed"
            state["error"] = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            if previous_sigterm is not None:
                signal.signal(signal.SIGTERM, previous_sigterm)
            state["finished_at"] = time.time()
            state["wall_seconds"] = state["finished_at"] - state["started_at"]
            state["allocated_gpu_hours"] = state["wall_seconds"] / 3600 if gpu else 0
            _atomic_json(state_path, state)
            _atomic_json(directory / "outcome.json", state)
    return state


def cancel(config: NNUNetConfig) -> dict:
    """Terminate this workspace's live worker process group, with PID reuse checks."""
    state = _json(config.root / "active-stage.json")
    if state["status"] != "running":
        raise ValueError("There is no running stage to cancel")
    pid = state["pid"]
    proc = Path(f"/proc/{pid}/cmdline")
    if not proc.exists():
        raise RuntimeError("Safe cancellation requires a live Linux /proc process record")
    cmdline = proc.read_bytes().split(b"\0")
    if state["argv"][-1].encode() not in cmdline or os.getpgid(pid) != pid:
        raise RuntimeError("Process identity changed; refusing to signal a reused PID")
    os.killpg(pid, signal.SIGTERM)
    return {"status": "cancellation_requested", "pid": pid, "action": state["action"]}


def _plan_binding(config: NNUNetConfig) -> dict:
    record = _json(config.root / "plan-binding.json")
    if record["binding_digest"] != _digest(_binding(config)):
        raise ValueError("Prepared data/configuration identity changed")
    if record["runtime"] != _runtime(config):
        raise ValueError("Environment changed since planning; use a new experiment")
    for relative, expected in record["files"].items():
        _check_hash(config.preprocessed / relative, expected)
    actual = {
        str(p.relative_to(config.preprocessed))
        for p in config.preprocessed.rglob("*")
        if p.is_file()
    }
    if actual != set(record["files"]):
        raise ValueError("Preprocessing cache membership changed")
    return record


def plan_and_preprocess(config: NNUNetConfig, *, dry_run: bool = False) -> dict:
    binding = _binding(config)
    if (config.root / "plan-binding.json").exists():
        raise FileExistsError("Planning is frozen; use a new workspace for a new plan")
    result = {
        "action": "plan",
        "dry_run": dry_run,
        "planner": f"nnUNetPlannerResEnc{config.resenc}",
        "plans": config.plans,
        "configuration": config.configuration,
        "planning_scope": "train_and_val_only",
        "test_cases_excluded": len(binding["held_out_cases"]),
    }
    if dry_run:
        return result
    # Refuse stale partial caches; never let nnU-Net reuse an unbound fingerprint.
    if set(p.name for p in config.preprocessed.iterdir()) != {"splits_final.json"}:
        raise FileExistsError("Unbound preprocessing outputs exist; create a fresh workspace")
    if config.reference_workspace is None:
        state = _run(config, "plan", {})
    else:
        from .nnunet_reference import import_reference
        from .recipe_plan import check_hrc_dataset, check_starc_dataset, transfer_plan

        with _lock(config.root / ".stage.lock"):
            reference = import_reference(config)
            if config.output_mode == "regions":
                # Same arrays; nnU-Net reads the label mode from the preprocessed dataset.json.
                _write_dataset_json(
                    config,
                    config.preprocessed / "dataset.json",
                    _dataset_json(config, binding["ontology"], len(binding["development_cases"])),
                )
            plan_path = config.preprocessed / f"{config.reference_plans}.json"
            transferred, changes = transfer_plan(
                _json(plan_path), config.architecture, config.architecture_options
            )
            if config.hrc_options is not None:
                # Fail closed unless the bound channels mean host and lesion here.
                changes["hrc_outputs"] = check_hrc_dataset(
                    config.hrc_options, _json(config.preprocessed / "dataset.json")
                )
            if config.starc_options is not None:
                # Lesion labels and fusion channels must mean lesion and host here,
                # and the bound targets must come from these development labels.
                changes["starc_outputs"] = check_starc_dataset(
                    config.starc_options, _json(config.preprocessed / "dataset.json")
                )
                changes["starc_targets"] = _check_starc_targets(config, binding, transferred)
            _atomic_json(plan_path, transferred)
            _atomic_json(
                config.root / "recipe-transfer.json",
                {
                    "reference": reference,
                    "architecture": config.architecture,
                    "output_mode": config.output_mode,
                    "changes": changes,
                },
            )
        state = {"action": "import_reference", "status": "completed"}
        if config.output_mode == "regions" or config.backend_runtime == NNSSL_RUNTIME:
            state = _run(config, "plan", {"adapt_reference": True})
            _check_reference_adaptation(config, transferred)
    plan = _json(config.preprocessed / f"{config.plans}.json")
    if config.configuration not in plan["configurations"]:
        raise ValueError("Requested configuration was not produced by the planner")
    if config.output_mode == "regions" and not _same_dataset_json(
        _json(config.preprocessed / "dataset.json"),
        _dataset_json(config, binding["ontology"], len(binding["development_cases"])),
    ):
        # nnU-Net derives the region head order from this file's label order.
        raise ValueError("The preprocessed region dataset.json differs from the bound regions")
    files = {
        str(p.relative_to(config.preprocessed)): _sha(p)
        for p in sorted(config.preprocessed.rglob("*"))
        if p.is_file()
    }
    _atomic_json(
        config.root / "plan-binding.json",
        {"binding_digest": _digest(binding), "runtime": _runtime(config), "files": files},
    )
    return {**result, "stage": state, "plan_sha256": files[f"{config.plans}.json"]}


def _reference_index(config: NNUNetConfig) -> dict[str, str]:
    """The frozen reference cache's file hashes, from its bound plan-binding record."""
    assert config.reference_workspace is not None
    record_path = Path(config.reference_workspace) / "plan-binding.json"
    _check_hash(record_path, config.reference_plan_binding_sha256 or "")
    return dict(_json(record_path)["files"])


def _check_reference_adaptation(config: NNUNetConfig, transferred: dict) -> dict:
    """Prove the worker changed only what its mode allows; arrays stay the reference's bytes.

    Region mode may rewrite only the per-case ``.pkl`` (``class_locations``)
    and the preprocessed ``dataset.json``. The nnssl runtime may add only the
    foreground sampling store inside the data folder and the plan_like_dynamic
    plan, which must equal the frozen plan apart from its name and pretrain_info.
    """
    index = _reference_index(config)
    data_id = transferred["configurations"][config.configuration]["data_identifier"]
    rewritten = {f"{config.reference_plans}.json", "splits_final.json"}
    if config.output_mode == "regions":
        rewritten |= {"dataset.json"} | {name for name in index if name.endswith(".pkl")}
    for relative, digest in index.items():
        if relative not in rewritten:
            _check_hash(config.preprocessed / relative, digest)
    actual = {
        str(p.relative_to(config.preprocessed))
        for p in config.preprocessed.rglob("*")
        if p.is_file()
    }
    added = actual - set(index)
    allowed: set[str] = set()
    record: dict[str, Any] = {"arrays_and_ground_truth_equal_reference": True}
    if config.backend_runtime == NNSSL_RUNTIME:
        store = f"{data_id}/fg_sampling/"
        allowed = {f"{config.plans}.json"} | {name for name in added if name.startswith(store)}
        if not any(name.endswith("meta.json") for name in allowed):
            raise ValueError("nnU-Net master did not complete the foreground sampling store")
        pretrained = _json(config.preprocessed / f"{config.plans}.json")
        info = pretrained.pop("pretrain_info", None)
        frozen = {k: v for k, v in transferred.items() if k != "plans_name"}
        # plan_like_dynamic keeps only the 3d_fullres configuration, unchanged.
        frozen["configurations"] = {
            config.configuration: transferred["configurations"][config.configuration]
        }
        if (
            not isinstance(info, dict)
            or info.get("checkpoint_path") != config.init_checkpoint
            or pretrained.pop("plans_name", None) != config.plans
            or frozen != pretrained
        ):
            raise ValueError(
                "plan_like_dynamic changed the frozen plan or names another checkpoint"
            )
        record["pretrain_info"] = {k: v for k, v in info.items() if k != "citations"}
        record["sampling_store_files"] = len(allowed) - 1
    if added - allowed or set(index) - actual:
        raise ValueError(
            f"Reference adaptation changed cache membership: added={sorted(added - allowed)[:5]} "
            f"missing={sorted(set(index) - actual)[:5]}"
        )
    worker = _json(config.root / "reference-adaptation-worker.json")
    binding = _json(config.root / "binding.json")
    expected = _dataset_json(config, binding["ontology"], len(binding["development_cases"]))
    if not _same_dataset_json(_json(config.preprocessed / "dataset.json"), expected):
        raise ValueError("The preprocessed dataset.json differs from the bound label mode")
    if config.output_mode == "regions":
        cases = len(binding["development_cases"])
        if worker.get("regions", {}).get("label_mode_reference_reproduced") != cases:
            raise ValueError("Region class locations were not regenerated for every case")
    record["worker"] = worker
    _atomic_json(config.root / "reference-adaptation.json", record)
    return record


def _adapt_reference_worker(config: NNUNetConfig) -> None:
    """Backend interpreter: region sampling keys and/or nnU-Net master metadata on the copy."""
    binding = _binding(config, verify_development=False)
    plan = _json(config.preprocessed / f"{config.reference_plans}.json")
    folder = config.preprocessed / plan["configurations"][config.configuration]["data_identifier"]
    report: dict[str, Any] = {}
    if config.output_mode == "regions":
        from .nnunet_regions import regenerate_class_locations

        labels = _json(config.preprocessed / "dataset.json")
        labels = {k: v for k, v in labels.items() if k != "regions_class_order"}
        labels["labels"] = binding["ontology"]
        report["regions"] = regenerate_class_locations(
            folder,
            binding["development_cases"],
            label_dataset_json=labels,
            region_dataset_json=_json(config.preprocessed / "dataset.json"),
            plans=plan,
            workers=config.workers,
        )
    if config.backend_runtime == NNSSL_RUNTIME:
        from nnunetv2.experiment_planning.like_nnssl import plan_like_dynamic
        from nnunetv2.preprocessing.sampling_locations.extract_sampling_locations import (
            extract_sampling_locations_dataset,
        )

        assert config.init_checkpoint is not None and config.pretrained_plan_name is not None
        _check_hash(config.init_checkpoint, config.init_checkpoint_sha256 or "")
        extract_sampling_locations_dataset(
            config.dataset_id,
            config.reference_plans,
            (config.configuration,),
            num_processes=config.workers,
            overwrite=True,
            show_progress_bar=False,
        )
        plan_like_dynamic(
            config.dataset_id,
            config.pretrained_plan_name,
            config.init_checkpoint,
            plans_identifier=config.reference_plans,
            num_processes=config.workers,
        )
        report["nnssl"] = {
            "sampling_locations": "nnUNetv2_extract_sampling_locations on the copied arrays",
            "plan": f"nnUNetv2_plan_like_dynamic -pl {config.reference_plans} "
            f"-n {config.pretrained_plan_name}",
        }
    _atomic_json(config.root / "reference-adaptation-worker.json", report)


def _checkpoint(config: NNUNetConfig, name: str) -> dict:
    if name not in {"checkpoint_latest.pth", "checkpoint_best.pth", "checkpoint_final.pth"}:
        raise ValueError("Select a named checkpoint created by this experiment")
    index = _json(config.root / "checkpoint-index.json")
    if name not in index:
        raise ValueError(
            f"No bound checkpoint exists: {name}; resume never falls back to a fresh run"
        )
    item = index[name]
    identity = _digest(
        {"binding": _binding(config, verify_development=False), "runtime": _runtime(config)}
    )
    if item["identity"] != identity:
        raise ValueError("Checkpoint belongs to different data, code, or environment")
    _check_hash(config.fold_folder / name, item["sha256"])
    _check_hash(config.fold_folder / f"{name}.rng.pt", item["rng_sha256"])
    return item


def train(
    config: NNUNetConfig,
    *,
    resume: bool = False,
    resume_checkpoint: str | None = None,
    dry_run: bool = False,
) -> dict:
    """Train one direct GPU job, or explicitly recover an identity-bound checkpoint."""
    _plan_binding(config)
    checkpoint = None
    if resume:
        if resume_checkpoint is None:
            index_path = config.root / "checkpoint-index.json"
            if not index_path.exists():
                raise ValueError(
                    "No checkpoint index exists; resume cannot start a fresh training run"
                )
            index = _json(index_path)
            candidates = [
                n
                for n in ("checkpoint_final.pth", "checkpoint_latest.pth", "checkpoint_best.pth")
                if n in index and (config.fold_folder / n).exists()
            ]
            if not candidates:
                raise ValueError("No recovery checkpoint exists")
            resume_checkpoint = max(
                candidates, key=lambda n: (index[n]["epoch"], index[n]["saved_at"])
            )
        checkpoint = _checkpoint(config, resume_checkpoint)
    elif resume_checkpoint is not None:
        raise ValueError("resume_checkpoint requires resume=True")
    elif config.fold_folder.exists():
        raise FileExistsError("Training output exists; explicitly resume or use a new workspace")
    prepared = _json(config.root / "binding.json")
    if prepared.get("starc_targets") != _starc_targets_binding(config):
        raise ValueError("STAR-C target binding changed since preparation")
    initial = (
        None
        if resume
        else _initial_checkpoint_record(
            config,
            manifest_sha256=prepared["manifest_sha256"],
            splits_sha256=prepared["splits_sha256"],
        )
    )
    result = {
        "action": "train",
        "dry_run": dry_run,
        "gpu": config.gpu,
        "resume": resume,
        "resume_checkpoint": resume_checkpoint,
        "checkpoint_sha256": checkpoint["sha256"] if checkpoint else None,
        "purpose": config.purpose,
        "trainer": config.trainer,
        "initialization": config.initialization,
        "init_checkpoint_sha256": initial["sha256"] if initial else None,
        "resume_granularity": "saved_epoch_not_bitwise_mid_epoch",
        "deterministic": config.deterministic,
        "augmentation_workers": 0 if config.deterministic else config.workers,
    }
    if dry_run:
        return result
    state = _run(config, "train", {"resume_checkpoint": resume_checkpoint}, gpu=True)
    _checkpoint(config, "checkpoint_final.pth")
    return {**result, "stage": state}


def validate_prediction_geometry(
    image: str | Path, prediction: str | Path, labels: tuple[int, ...] = (0, 1, 2)
) -> dict:
    """Check a native-space output using image geometry only, never annotations.

    ``labels`` are the manifest ontology's values (Task07 0/1/2 by default).
    """
    import nibabel as nib
    import numpy as np

    src: Any = nib.load(str(image))
    pred: Any = nib.load(str(prediction))
    if (
        len(src.shape) != 3
        or pred.shape != src.shape
        or not np.allclose(pred.affine, src.affine, atol=1e-4, rtol=0)
    ):
        raise ValueError(f"Prediction does not match native CT geometry: {prediction}")
    values = np.asanyarray(pred.dataobj)
    if not np.isfinite(values).all() or not np.isin(values, labels).all():
        raise ValueError(f"Prediction contains invalid class values: {prediction}")
    return {"shape": list(pred.shape), "affine": pred.affine.tolist(), "sha256": _sha(prediction)}


def _finalize_native_prediction(
    image: str | Path,
    prediction: str | Path,
    *,
    labels: tuple[int, ...] = (0, 1, 2),
    unknown_units_as_mm: bool = False,
) -> dict:
    """Restore verified spatial header metadata dropped by nnU-Net's NibabelIO.

    First verify the predicted voxel grid and affine. Never repair a geometric
    mismatch by replacing its affine. Only a validated output receives source
    units and coded spatial forms, and the change is recorded with both hashes.
    Undeclared source units (KiTS23) are copied unchanged, and only when the
    manifest's geometry policy reads them as mm.
    """
    import nibabel as nib
    import numpy as np

    before = validate_prediction_geometry(image, prediction, labels)
    source: Any = nib.load(str(image))
    predicted: Any = nib.load(str(prediction))
    units = source.header.get_xyzt_units()
    if units[0] != "mm" and not (units[0] == "unknown" and unknown_units_as_mm):
        raise ValueError("Native CT must explicitly declare millimeter spatial units")
    labels = np.asanyarray(predicted.dataobj)
    header = predicted.header.copy()
    header.set_xyzt_units(*units)
    restored = nib.Nifti1Image(labels, source.affine, header)
    for form in ("qform", "sform"):
        matrix, code = getattr(source, f"get_{form}")(coded=True)
        getattr(restored, f"set_{form}")(matrix, code=int(code))
    destination = Path(prediction)
    temporary = destination.with_name(f".{destination.stem}.{uuid.uuid4().hex}.nii.gz")
    try:
        nib.save(restored, temporary)
        validated = validate_prediction_geometry(image, temporary, labels)
        checked_volume: Any = nib.load(temporary)
        if not np.array_equal(np.asanyarray(checked_volume.dataobj), labels):
            raise ValueError("Spatial-header restoration unexpectedly changed predicted labels")
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    return {
        **validated,
        "backend_output_sha256": before["sha256"],
        "header_action": "copied_source_spatial_units_and_coded_forms_after_affine_validation",
    }


def predict(
    config: NNUNetConfig,
    *,
    partition: str = "val",
    final_test: bool = False,
    checkpoint: str = "checkpoint_best.pth",
    dry_run: bool = False,
) -> dict:
    """Image-only inference. Test requires an explicit, separately invoked flag.

    Output completion is subject to native image geometry validation. Test use is
    recorded durably. Repeated testing does not authorize changing model choices.
    """
    if partition not in {"train", "val", "test", "unlabeled"} or final_test != (
        partition == "test"
    ):
        raise ValueError(
            "Use train/val/unlabeled, or explicitly partition=test and final_test=True"
        )
    binding = _binding(config, verify_development=False)
    checkpoint_item = _checkpoint(config, checkpoint)
    manifest = _json(Path(binding["manifest_path"]))
    labels = tuple(sorted(binding["ontology"].values()))
    geometry = manifest.get("geometry_policy") or {}
    lookup = {c["case_id"]: c for c in manifest["cases"]}
    excluded_duplicates: list[str] = []
    if partition == "unlabeled":
        from segmentary.medical.data import predictable_unlabeled_cases

        identifiers, excluded_duplicates = predictable_unlabeled_cases(manifest)
    else:
        identifiers = _fold_cases(config, binding, partition)
    cases = [
        {"case_id": x, "image": lookup[x]["image"], "image_sha256": lookup[x]["image_sha256"]}
        for x in identifiers
    ]
    if not cases:
        raise ValueError(f"No {partition} images were declared")
    for case in cases:
        _check_hash(case["image"], case["image_sha256"])
    # Predictor loads plans.json and dataset.json from the trained model folder.
    plan_record = _json(config.root / "plan-binding.json")
    for model_name, original_name in (
        ("plans.json", f"{config.plans}.json"),
        ("dataset.json", "dataset.json"),
    ):
        original = config.preprocessed / original_name
        _check_hash(original, plan_record["files"][original_name])
        trained_metadata = _json(config.model_folder / model_name)
        # nnU-Net's CLI injects this runtime-only flag before the trainer saves
        # plans.json. It does not alter architecture or preprocessing.
        if (
            model_name == "plans.json"
            and "continue_training" in trained_metadata
            and type(trained_metadata.pop("continue_training")) is not bool
        ):
            raise ValueError("Invalid nnU-Net continue_training metadata")
        if trained_metadata != _json(original) or (
            model_name == "dataset.json"
            and not _same_dataset_json(trained_metadata, _json(original))
        ):
            raise ValueError(f"Trained model metadata changed: {model_name}")
    output = config.root / "predictions" / f"{partition}-{time.time_ns()}"
    result = {
        "action": "predict",
        "partition": partition,
        "final_test": final_test,
        "dry_run": dry_run,
        "output": str(output),
        "cases": len(cases),
        "fold": config.fold,
        "checkpoint": checkpoint,
        "checkpoint_sha256": checkpoint_item["sha256"],
    }
    if partition == "unlabeled":
        result["excluded_duplicates_of_labeled_cases"] = excluded_duplicates
    if dry_run:
        return result
    payload = {
        "cases": cases,
        "output": str(output),
        "checkpoint": checkpoint,
        "partition": partition,
        "labels": list(labels),
        "unknown_units_as_mm": bool(geometry.get("unknown_spatial_units_as_mm", False)),
    }
    state = _run(config, "predict", payload, gpu=True)
    expected = {f"{c['case_id']}.nii.gz" for c in cases}
    if {p.name for p in output.glob("*.nii.gz")} != expected:
        raise ValueError("Prediction coverage is incomplete or includes unexpected cases")
    checks = {
        c["case_id"]: validate_prediction_geometry(
            c["image"], output / f"{c['case_id']}.nii.gz", labels
        )
        for c in cases
    }
    _atomic_json(output / "geometry-validation.json", checks)
    _atomic_json(
        output / "prediction-record.json", {**result, "stage": state, "status": "validated"}
    )
    return {**result, "stage": state, "status": "validated"}


def _seed_runtime(config: NNUNetConfig):
    import random

    import numpy as np
    import torch

    random.seed(config.seed)
    np.random.seed(config.seed)
    torch.manual_seed(config.seed)
    torch.cuda.manual_seed_all(config.seed)
    torch.backends.cudnn.benchmark = not config.deterministic
    torch.backends.cudnn.deterministic = config.deterministic
    torch.use_deterministic_algorithms(config.deterministic)


def _guard_trainer_split(trainer, fold: int, expected: tuple[list[str], list[str]]) -> None:
    """Make every ``trainer.do_split()`` call prove it returns the bound fold.

    nnU-Net silently falls back to a random 80:20 split when the requested fold
    is missing from ``splits_final.json``; this turns any such drift into an error.
    """
    original = trainer.do_split

    def do_split():
        train_keys, val_keys = original()
        if (list(train_keys), list(val_keys)) != (list(expected[0]), list(expected[1])):
            raise ValueError(f"nnU-Net trainer split differs from bound fold {fold}")
        return train_keys, val_keys

    trainer.do_split = do_split


def _trainer_class(name: str) -> Any:
    """Resolve an allowlisted trainer class inside the backend interpreter."""
    if name in BUILTIN_TRAINERS:
        from nnunetv2.utilities.find_objects import recursive_find_trainer_class_by_name

        return recursive_find_trainer_class_by_name(name)
    if name == PRETRAINED_TRAINER:
        from . import nnunet_pretrained

        return getattr(nnunet_pretrained, name)
    if name in STARC_TRAINERS:
        from . import nnunet_star_trainer

        return getattr(nnunet_star_trainer, name)
    if name in SEGMENTARY_TRAINERS:
        from . import nnunet_trainers

        return getattr(nnunet_trainers, name)
    raise ValueError(f"Trainer is not allowlisted: {name}")


def _build_trainer(config: NNUNetConfig, *, continue_training: bool, device: Any) -> Any:
    if config.trainer in BUILTIN_TRAINERS:
        from nnunetv2.run.run_training import get_trainer_from_args

        return get_trainer_from_args(
            config.dataset,
            config.configuration,
            config.fold,
            trainer_name=config.trainer,
            plans_identifier=config.plans,
            continue_training=continue_training,
            device=device,
        )
    # The same steps as nnU-Net's get_trainer_from_args, without its by-name
    # class search, which only looks inside the nnunetv2 package.
    plans = _json(config.preprocessed / f"{config.plans}.json")
    plans["continue_training"] = continue_training
    dataset_json = _json(config.preprocessed / "dataset.json")
    return _trainer_class(config.trainer)(
        plans=plans,
        configuration=config.configuration,
        fold=config.fold,
        dataset_json=dataset_json,
        device=device,
    )


def _state_digest(state: dict) -> str:
    """SHA256 over a state dict's names, dtypes, shapes and raw bytes."""
    import torch

    digest = hashlib.sha256()
    for key in sorted(state):
        tensor = state[key].detach().cpu().contiguous()
        digest.update(f"{key}|{tensor.dtype}|{tuple(tensor.shape)}|".encode())
        digest.update(tensor.reshape(-1).view(torch.uint8).numpy().tobytes())
    return digest.hexdigest()


def _load_initial_weights(network: Any, config: NNUNetConfig) -> dict:
    """Load a sha-bound nnU-Net checkpoint's weights; only allowlisted keys may be new.

    The checkpoint bytes are hashed and deserialized from the same buffer.
    Optimizer state, epoch counter and logs are not loaded: training restarts
    at epoch 0 with this trainer's optimizer and schedule.
    """
    import io

    import torch

    assert config.init_checkpoint is not None
    data = Path(config.init_checkpoint).read_bytes()
    if hashlib.sha256(data).hexdigest() != config.init_checkpoint_sha256:
        raise ValueError(f"Initial checkpoint hash changed: {config.init_checkpoint}")
    checkpoint = torch.load(io.BytesIO(data), map_location="cpu", weights_only=False)
    del data
    source = checkpoint.get("network_weights") if isinstance(checkpoint, dict) else None
    if not isinstance(source, dict) or not source:
        raise ValueError("Initial checkpoint has no nnU-Net network_weights")
    module = getattr(network, "_orig_mod", network)
    target = module.state_dict()
    prefixes = tuple(config.init_allowed_missing_prefixes or ())
    missing = sorted(set(target) - set(source))
    unexpected = sorted(set(source) - set(target))
    disallowed = [key for key in missing if not prefixes or not key.startswith(prefixes)]
    mismatched = sorted(
        key for key in set(source) & set(target) if source[key].shape != target[key].shape
    )
    if unexpected or disallowed or mismatched:
        raise ValueError(
            "Initial checkpoint does not match this network: "
            f"unexpected={unexpected[:5]} missing_outside_allowlist={disallowed[:5]} "
            f"shape_mismatch={mismatched[:5]}"
        )
    module.load_state_dict({key: source.get(key, target[key]) for key in target}, strict=True)
    return {
        "initialization": config.initialization,
        "external_weight_loads": 1,
        "init_checkpoint": config.init_checkpoint,
        "init_checkpoint_sha256": config.init_checkpoint_sha256,
        "source_trainer_name": checkpoint.get("trainer_name"),
        "source_epoch": checkpoint.get("current_epoch"),
        "loaded_keys": len(source),
        "missing_keys": missing,
        "allowed_missing_prefixes": list(prefixes),
        "unexpected_keys": [],
        "initial_weights_sha256": _state_digest(module.state_dict()),
        "optimizer_state_loaded": False,
        "epoch_counter": "restarts_at_0",
    }


def _origin_path(config: NNUNetConfig) -> Path:
    name = (
        "scratch-origin.json"
        if config.initialization == "scratch"
        else "initialization-origin.json"
    )
    return config.root / name


def _check_resume_origin(config: NNUNetConfig, identity: str) -> dict:
    """Resume only on top of this experiment's own scratch or initial-weight record."""
    path = _origin_path(config)
    origin = _json(path) if path.is_file() else {}
    if (
        origin.get("identity") != identity
        or origin.get("initialization") != config.initialization
        or origin.get("init_checkpoint_sha256") != config.init_checkpoint_sha256
    ):
        raise ValueError("Resume requires the matching initialization-origin record")
    return origin


def _restore_scheduler(scheduler: Any, rng: dict) -> None:
    """Restore the saved schedule state unless the trainer rebuilt a different scheduler.

    Pretrained trainers switch from a linear warm-up scheduler to a poly one.
    Loading one scheduler's attributes into the other would corrupt the
    schedule; both compute the learning rate from the explicit epoch anyway.
    """
    saved = rng.get("scheduler_class")
    if saved is None or saved == type(scheduler).__name__:
        scheduler.load_state_dict(rng["scheduler"])


def _train_worker(config: NNUNetConfig, payload: dict, identity: str):
    import random

    import numpy as np
    import torch

    # Match the official CUDA training CLI's Torch thread limits. The separate
    # nnUNet_n_proc_DA=0 switch controls synchronous augmentation, not Torch.
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    _seed_runtime(config)
    trainer = _build_trainer(
        config,
        continue_training=payload["resume_checkpoint"] is not None,
        device=torch.device("cuda", 0),
    )
    if type(trainer).__name__ != config.trainer:
        raise ValueError("Constructed trainer differs from the bound trainer")
    for name in ("num_epochs", "num_iterations_per_epoch", "num_val_iterations_per_epoch"):
        value = getattr(config, name)
        if value is not None:
            setattr(trainer, name, value)
    if config.initial_lr is not None:
        # initialize() builds the optimizer and schedule from this value.
        trainer.initial_lr = config.initial_lr
    if config.architecture == "starc":
        from .recipe_plan import training_options

        # Losses, teacher forcing and the bound target folder; the trainer
        # re-verifies the manifest, ray set and every case hash before loading.
        assert config.starc_options is not None
        trainer.configure_star(
            training_options(config.starc_options),
            targets_dir=config.starc_targets,
            manifest_sha256=config.starc_targets_manifest_sha256,
        )
    split_binding = _binding(config, verify_development=False)
    expected_split = (
        _fold_cases(config, split_binding, "train"),
        _fold_cases(config, split_binding, "val"),
    )
    _guard_trainer_split(trainer, config.fold, expected_split)
    # Record actual initialized capacity before any optimization. The official
    # trainer initializes only once; on_train_start reuses this same network.
    trainer.initialize()
    origin_path = _origin_path(config)
    if payload["resume_checkpoint"] is None:
        if config.initialization == "scratch":
            initial = {"initialization": "scratch", "external_weight_loads": 0}
        elif config.trainer == PRETRAINED_TRAINER:
            from .nnunet_pretrained import load_pretrained_encoder

            initial = load_pretrained_encoder(trainer, config)
        else:
            initial = _load_initial_weights(trainer.network, config)
        _atomic_json(
            origin_path,
            {
                **initial,
                "identity": identity,
                "architecture": config.architecture,
                "network_class": type(trainer.network).__module__
                + "."
                + type(trainer.network).__name__,
                "parameters": sum(p.numel() for p in trainer.network.parameters()),
                "trainable_parameters": sum(
                    p.numel() for p in trainer.network.parameters() if p.requires_grad
                ),
                "plan_sha256": _sha(config.preprocessed / f"{config.plans}.json"),
            },
        )
    else:
        _check_resume_origin(config, identity)
    original_save = trainer.save_checkpoint

    def save_checkpoint(filename: str):
        destination = Path(filename)
        temporary = destination.with_name(f".{destination.name}.{uuid.uuid4().hex}.tmp")
        rng_path = destination.with_name(destination.name + ".rng.pt")
        rng_tmp = rng_path.with_name(f".{rng_path.name}.{uuid.uuid4().hex}.tmp")
        try:
            original_save(str(temporary))
            torch.save(
                {
                    "python": random.getstate(),
                    "numpy": np.random.get_state(),
                    "torch_cpu": torch.get_rng_state(),
                    "torch_cuda": torch.cuda.get_rng_state_all(),
                    "scheduler": trainer.lr_scheduler.state_dict(),
                    "scheduler_class": type(trainer.lr_scheduler).__name__,
                },
                rng_tmp,
            )
            os.replace(temporary, destination)
            os.replace(rng_tmp, rng_path)
            index_path = config.root / "checkpoint-index.json"
            index = _json(index_path) if index_path.exists() else {}
            index[destination.name] = {
                "sha256": _sha(destination),
                "rng_sha256": _sha(rng_path),
                "identity": identity,
                "epoch": trainer.current_epoch + 1,
                "saved_at": time.time(),
            }
            _atomic_json(index_path, index)
        finally:
            temporary.unlink(missing_ok=True)
            rng_tmp.unlink(missing_ok=True)

    trainer.save_checkpoint = save_checkpoint
    resume = payload["resume_checkpoint"]
    if resume is not None:
        _checkpoint(config, resume)
        trainer.load_checkpoint(str(config.fold_folder / resume))
        rng = torch.load(
            config.fold_folder / f"{resume}.rng.pt", map_location="cpu", weights_only=False
        )
        random.setstate(rng["python"])
        np.random.set_state(rng["numpy"])
        torch.set_rng_state(rng["torch_cpu"])
        torch.cuda.set_rng_state_all(rng["torch_cuda"])
        _restore_scheduler(trainer.lr_scheduler, rng)
    original_step = trainer.train_step

    def train_step(batch):
        result = original_step(batch)
        if not np.isfinite(result["loss"]).all():
            raise FloatingPointError(
                "Non-finite training loss; stopping without changing the recipe"
            )
        return result

    trainer.train_step = train_step
    _atomic_json(
        config.root / "trainer-settings.json",
        {
            "purpose": config.purpose,
            "trainer": config.trainer,
            "initialization": config.initialization,
            "num_epochs": trainer.num_epochs,
            "num_iterations_per_epoch": trainer.num_iterations_per_epoch,
            "num_val_iterations_per_epoch": trainer.num_val_iterations_per_epoch,
            "initial_lr": trainer.initial_lr,
            "weight_decay": trainer.weight_decay,
            "oversample_foreground_percent": trainer.oversample_foreground_percent,
            "deep_supervision": trainer.enable_deep_supervision,
            "warmup_epochs": getattr(trainer, "warmup_duration_whole_net", None),
            "batch_size": trainer.batch_size,
            "backend_runtime": config.backend_runtime,
            "output_mode": config.output_mode,
            "starc": None
            if config.architecture != "starc"
            else {
                "training_options": dict(trainer.star_options),
                "targets": str(trainer.star_targets_folder()),
                "targets_manifest_sha256": trainer.star_targets_manifest_sha256,
                "inference": config.starc_inference,
            },
            "checkpoint_selection": "official_ema_foreground_dice",
            "fold": config.fold,
            "fold_cases": {"train": len(expected_split[0]), "val": len(expected_split[1])},
            "split_guard": "trainer.do_split must equal the bound fold lists exactly",
            "seed": config.seed,
            "deterministic": config.deterministic,
            "reproducibility": "strict_deterministic_algorithms"
            if config.deterministic
            else "seeded_initialization_with_upstream_nondeterministic_cuda_and_augmentation",
            "resume_granularity": "saved_epoch_no_bitwise_prefetch_or_mid_epoch_guarantee",
            "torch": torch.__version__,
            "cuda": torch.version.cuda,
            "gpu_name": torch.cuda.get_device_name(0),
        },
    )
    torch.cuda.reset_peak_memory_stats(0)
    telemetry: dict[str, Any] = {
        "status": "running",
        "training_seconds": None,
        "validation_seconds": None,
        "peak_allocated_gpu_bytes": None,
        "peak_reserved_gpu_bytes": None,
    }
    training_started = time.monotonic()
    try:
        trainer.run_training()
        telemetry["status"] = "training_complete"
        _atomic_json(
            config.root / "training-result.json",
            {
                "completed": trainer.current_epoch == trainer.num_epochs,
                "epochs": trainer.current_epoch,
                "steps": trainer.current_epoch * trainer.num_iterations_per_epoch,
                "budget_steps": trainer.num_epochs * trainer.num_iterations_per_epoch,
                "checkpoint_selection": "official_ema_foreground_dice",
                "identity": identity,
            },
        )
    except BaseException as exc:
        telemetry["status"] = "training_failed"
        if (
            config.deterministic
            and isinstance(exc, RuntimeError)
            and "deterministic" in str(exc).lower()
        ):
            raise RuntimeError(
                "Strict deterministic execution failed because a required backend kernel has no "
                "deterministic implementation. This experiment was stopped without changing its "
                "recipe. To use standard nnU-Net GPU execution, explicitly set deterministic=false "
                "in a new experiment workspace. Original error: " + str(exc)
            ) from exc
        raise
    finally:
        telemetry["training_seconds"] = time.monotonic() - training_started
        telemetry["peak_allocated_gpu_bytes"] = torch.cuda.max_memory_allocated(0)
        telemetry["peak_reserved_gpu_bytes"] = torch.cuda.max_memory_reserved(0)
        _atomic_json(config.root / "training-telemetry.json", telemetry)
    # Keep full-volume export separate from patch-level checkpoint selection.
    # The official perform_actual_validation hardcodes mirror TTA and its own
    # process count; invoke the official predictor with our frozen settings.
    _checkpoint(config, "checkpoint_best.pth")
    _checkpoint(config, "checkpoint_final.pth")
    binding = _binding(config, verify_development=False)
    manifest = _json(Path(binding["manifest_path"]))
    validation_cases = _fold_cases(config, binding, "val")
    lookup = {c["case_id"]: c for c in manifest["cases"]}
    # Free training state before constructing an independent inference network.
    original_save = original_step = trainer = None
    import gc

    gc.collect()
    torch.cuda.empty_cache()
    validation_output = config.fold_folder / f"validation-{time.time_ns()}"
    validation_started = time.monotonic()
    try:
        _predict_worker(
            config,
            {
                "cases": [{"case_id": x, "image": lookup[x]["image"]} for x in validation_cases],
                "checkpoint": "checkpoint_best.pth",
                "output": str(validation_output),
            },
        )
        telemetry["status"] = "completed"
    except BaseException:
        telemetry["status"] = "validation_failed"
        raise
    finally:
        telemetry["validation_seconds"] = time.monotonic() - validation_started
        _atomic_json(config.root / "training-telemetry.json", telemetry)
    _atomic_json(
        config.root / "training-validation.json",
        {
            "output": str(validation_output),
            "cases": validation_cases,
            "fold": config.fold,
            "checkpoint": "checkpoint_best.pth",
            "selection": "official_ema_foreground_dice",
            "use_mirroring": config.use_mirroring,
            "metrics": "Run the separate medical evaluator; patch Dice is not full-volume Dice",
        },
    )


def initialize_predictor(
    predictor: Any, model_folder: Path, fold: int, checkpoint_name: str, trainer: str
) -> None:
    """Load one trained fold into an nnU-Net 2.8.1 predictor (read-only).

    Built-in trainers use the official ``initialize_from_trained_model_folder``.
    nnU-Net cannot find Segmentary trainers by name, so for those this repeats
    its steps and hands the network to ``manual_initialization``, the API the
    official trainer itself uses for final validation.
    """
    if trainer not in TRAINERS:
        raise ValueError(f"Trainer is not allowlisted: {trainer}")
    if trainer in BUILTIN_TRAINERS:
        predictor.initialize_from_trained_model_folder(
            str(model_folder), use_folds=(fold,), checkpoint_name=checkpoint_name
        )
        return
    import torch
    from nnunetv2.utilities.label_handling.label_handling import determine_num_input_channels
    from nnunetv2.utilities.plans_handling.plans_handler import PlansManager

    dataset_json = _json(model_folder / "dataset.json")
    plans_manager = PlansManager(_json(model_folder / "plans.json"))
    checkpoint = torch.load(
        model_folder / f"fold_{fold}" / checkpoint_name,
        map_location=torch.device("cpu"),
        weights_only=False,
    )
    if checkpoint.get("trainer_name") != trainer:
        raise ValueError("Checkpoint was written by a different trainer")
    configuration_manager = plans_manager.get_configuration(
        checkpoint["init_args"]["configuration"]
    )
    network = _trainer_class(trainer).build_network_architecture(
        plans_manager,
        configuration_manager,
        determine_num_input_channels(plans_manager, configuration_manager, dataset_json),
        plans_manager.get_label_manager(dataset_json).num_segmentation_heads,
        enable_deep_supervision=False,
    )
    network.load_state_dict(checkpoint["network_weights"])
    predictor.manual_initialization(
        network,
        plans_manager,
        configuration_manager,
        [checkpoint["network_weights"]],
        dataset_json,
        trainer,
        checkpoint.get("inference_allowed_mirroring_axes"),
    )


def build_predictor(
    architecture: str, starc_inference: dict[str, Any] | None = None, **kwargs: Any
) -> Any:
    """nnU-Net's predictor, or STAR-C's two-pass ``StarCPredictor`` for ``starc``.

    ``kwargs`` are ``nnUNetPredictor``'s own arguments, passed unchanged.
    """
    if architecture != "starc":
        if starc_inference is not None:
            raise ValueError("starc_inference applies to architecture=starc only")
        from nnunetv2.inference.predict_from_raw_data import nnUNetPredictor

        return nnUNetPredictor(**kwargs)
    from .nnunet_star_trainer import StarCPredictor
    from .recipe_plan import validate_starc_inference

    settings = validate_starc_inference(starc_inference)
    return StarCPredictor(
        **kwargs,
        star_two_pass=settings["two_pass"],
        nms_radius_mm=settings["nms_radius_mm"],
        max_case_instances=settings["max_case_instances"],
    )


def _predict_worker(config: NNUNetConfig, payload: dict):
    import torch

    # This also runs after training inside the same worker process.
    os.environ["nnUNet_n_proc_DA"] = str(config.workers)  # noqa: SIM112 - upstream variable name
    _seed_runtime(config)
    output = Path(payload["output"])
    output.mkdir(parents=True, exist_ok=False)
    predictor = build_predictor(
        config.architecture,
        config.starc_inference,
        tile_step_size=config.tile_step_size,
        use_gaussian=True,
        use_mirroring=config.use_mirroring,
        device=torch.device("cuda", 0),
    )
    # Predictor enables benchmarking in its constructor; restore the frozen setting.
    torch.backends.cudnn.benchmark = not config.deterministic
    initialize_predictor(
        predictor, config.model_folder, config.fold, payload["checkpoint"], config.trainer
    )
    predictor.predict_from_files(
        [[c["image"]] for c in payload["cases"]],
        [str(output / c["case_id"]) for c in payload["cases"]],
        save_probabilities=config.save_probabilities,
        overwrite=False,
        num_processes_preprocessing=config.workers,
        num_processes_segmentation_export=config.workers,
    )
    expected = {f"{c['case_id']}.nii.gz" for c in payload["cases"]}
    if {p.name for p in output.glob("*.nii.gz")} != expected:
        raise ValueError("Prediction coverage is incomplete or contains unexpected cases")
    native_checks = {
        case["case_id"]: _finalize_native_prediction(
            case["image"],
            output / f"{case['case_id']}.nii.gz",
            labels=tuple(payload.get("labels", (0, 1, 2))),
            unknown_units_as_mm=payload.get("unknown_units_as_mm", False),
        )
        for case in payload["cases"]
    }
    _atomic_json(output / "native-spatial-metadata.json", native_checks)


def _worker(request_path: str):
    request = _json(Path(request_path))
    config = NNUNetConfig(**request["config"])
    _require_worker_devices(config.gpu)
    if (
        _digest(
            {"binding": _binding(config, verify_development=False), "runtime": _runtime(config)}
        )
        != request["identity"]
    ):
        raise ValueError("Worker code/configuration/environment changed after launch")
    action, payload = request["action"], request["payload"]
    if action == "plan" and payload.get("adapt_reference"):
        _adapt_reference_worker(config)
    elif action == "plan":
        from nnunetv2.experiment_planning.plan_and_preprocess_entrypoints import (
            plan_and_preprocess_entry,
        )

        sys.argv = [
            "nnUNetv2_plan_and_preprocess",
            "-d",
            str(config.dataset_id),
            "-pl",
            f"nnUNetPlannerResEnc{config.resenc}",
            "-c",
            config.configuration,
            "-npfp",
            str(config.workers),
            "-np",
            str(config.workers),
            "--verify_dataset_integrity",
        ]
        plan_and_preprocess_entry()
    elif action == "train":
        _train_worker(config, payload, request["identity"])
    elif action == "predict":
        _predict_worker(config, payload)
    else:
        raise ValueError(f"Unknown worker action: {action}")


if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[1] != "_worker":
        raise SystemExit("Use segmentary-medical; this module is an internal subprocess worker")
    _worker(sys.argv[2])
