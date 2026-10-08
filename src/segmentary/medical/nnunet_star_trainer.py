"""STAR-C trainer, data loader and two-pass predictor for nnU-Net 2.8.1.

Imported only inside the backend interpreter. ``nnUNetTrainerStarC`` keeps
every element of ``nnUNetTrainer`` (SGD, poly schedule, DC+CE with deep
supervision, sampling, augmentation) and adds the STAR-C centre and ray losses
on targets built from the full-volume tables of ``star_completion``:

- the top-level ``SpatialTransform`` and ``MirrorTransform`` of the training
  pipeline are swapped for subclasses that record their exact output-to-input
  maps, and ``StarCDataLoader`` composes them with the crop into one affine
  frame per sample, then builds the patch targets in the augmentation worker;
- ``train_step`` adds ``centre_weight * focal + ray_weight * L1`` and, in a
  ``teacher_probability`` share of steps, renders the ground-truth centres;
- ``StarCPredictor`` detects centres in every tile, merges them with case-level
  NMS and renders the case-level stars in every tile and mirrored copy.

nnU-Net cannot find these classes by name, so the backend constructs the
trainer directly and loads the predictor with ``manual_initialization``.
"""

from __future__ import annotations

import itertools
import math
from pathlib import Path
from typing import Any

import numpy as np
import torch
from acvl_utils.cropping_and_padding.bounding_boxes import crop_and_pad_nd
from batchgenerators.dataloading.nondet_multi_threaded_augmenter import (
    NonDetMultiThreadedAugmenter,
)
from batchgenerators.dataloading.single_threaded_augmenter import SingleThreadedAugmenter
from batchgeneratorsv2.transforms.spatial.mirroring import MirrorTransform
from batchgeneratorsv2.transforms.spatial.spatial import SpatialTransform
from batchgeneratorsv2.transforms.utils.compose import ComposeTransforms
from nnunetv2.inference.predict_from_raw_data import nnUNetPredictor
from nnunetv2.inference.sliding_window_prediction import compute_gaussian
from nnunetv2.training.dataloading.data_loader import nnUNetDataLoader
from nnunetv2.training.dataloading.nnunet_dataset import infer_dataset_class
from nnunetv2.training.nnUNetTrainer.nnUNetTrainer import nnUNetTrainer
from nnunetv2.utilities.default_n_proc_DA import get_allowed_n_proc_DA
from nnunetv2.utilities.helpers import dummy_context, empty_cache
from threadpoolctl import threadpool_limits
from torch import autocast

from .nnunet_trainers import FINETUNE_EPOCHS, FINETUNE_INITIAL_LR
from .star_completion import (
    CaseDetection,
    StarInstances,
    StarTargetBuilder,
    centre_focal_loss,
    collate_star_targets,
    compose_patch_frame,
    frame_record,
    merge_tile_detections,
    mirror_record,
    ray_l1_loss,
    star_geometry,
    training_options,
    validate_starc_options,
    verify_star_targets,
)

FRAMES_KEY = "starc_frames"


def spatial_frame_record(
    transform: SpatialTransform, params: dict[str, Any], input_shape: tuple[int, ...]
) -> dict[str, Any]:
    """Output-to-input voxel map of one ``SpatialTransform`` call (2D acts on y, x)."""
    patch = [int(v) for v in transform.patch_size]
    ndim = len(patch)
    axes = tuple(range(3 - ndim, 3))
    if params["grid"] is None:
        # crop_tensor starts at floor(centre) - patch // 2.
        offset = [
            math.floor(centre) - size // 2
            for centre, size in zip(params["center_location_in_pixels"], patch, strict=True)
        ]
        return frame_record(axes, np.eye(ndim), np.asarray(offset, np.float64))
    if params.get("elastic_offsets") is not None:
        raise ValueError("STAR-C frames need an affine spatial transform (no elastic deformation)")
    grid = params["grid"]
    size = np.asarray(input_shape, np.float64)

    def source(index: tuple[int, ...]) -> np.ndarray:
        # grid_sample coordinates are normalised and in reversed axis order.
        g = grid[index].double().flip(-1).numpy()
        if transform.align_corners:
            return (g + 1) / 2 * (size - 1)
        return ((g + 1) * size - 1) / 2

    origin = source((0,) * ndim)
    columns = []
    for axis in range(ndim):
        far = [0] * ndim
        far[axis] = patch[axis] - 1
        columns.append((source(tuple(far)) - origin) / max(patch[axis] - 1, 1))
    return frame_record(axes, np.stack(columns, 1), origin)


class RecordingSpatialTransform(SpatialTransform):
    """``SpatialTransform`` that appends its frame to ``data_dict['starc_frames']``."""

    def apply(self, data_dict: dict, **params: Any) -> dict:
        frames = data_dict.get(FRAMES_KEY)
        shape = tuple(int(v) for v in data_dict["image"].shape[1:])
        result = super().apply(data_dict, **params)
        if frames is not None:
            frames.append(spatial_frame_record(self, params, shape))
        return result


class RecordingMirrorTransform(MirrorTransform):
    """``MirrorTransform`` that appends its flips to ``data_dict['starc_frames']``."""

    def apply(self, data_dict: dict, **params: Any) -> dict:
        frames = data_dict.get(FRAMES_KEY)
        result = super().apply(data_dict, **params)
        if frames is not None and params["axes"]:
            frames.append(mirror_record(params["axes"], result["image"].shape[1:]))
        return result


def _contains_geometry(transform: Any) -> bool:
    if isinstance(transform, (SpatialTransform, MirrorTransform)):
        return True
    children: list[Any] = []
    for name in ("transform", "transforms", "list_of_transforms"):
        value = getattr(transform, name, None)
        if value is not None:
            children.extend(value if isinstance(value, (list, tuple)) else [value])
    return any(_contains_geometry(child) for child in children)


def enable_frame_recording(transforms: ComposeTransforms) -> ComposeTransforms:
    """Swap the top-level spatial and mirror transforms for recording subclasses.

    A geometric transform nested inside a random wrapper, or elastic
    deformation, would make the recorded frame incomplete, so both fail.
    """
    if not isinstance(transforms, ComposeTransforms):
        raise ValueError("STAR-C expects nnU-Net's ComposeTransforms pipeline")
    for transform in transforms.transforms:
        if type(transform) is SpatialTransform:
            if transform.p_elastic_deform > 0:
                raise ValueError("STAR-C frames do not support elastic deformation")
            transform.__class__ = RecordingSpatialTransform
        elif type(transform) is MirrorTransform:
            transform.__class__ = RecordingMirrorTransform
        elif not isinstance(
            transform, (RecordingSpatialTransform, RecordingMirrorTransform)
        ) and _contains_geometry(transform):
            raise ValueError("STAR-C cannot record a nested spatial or mirror transform")
    return transforms


def target_rng(state: Any) -> np.random.Generator:
    """Target sampler seeded from a legacy NumPy state (key array and position).

    The Mersenne Twister key array changes only once every 624 draws, so the
    position is mixed in; otherwise consecutive batches would reuse one stream.
    """
    return np.random.default_rng([*np.asarray(state[1]).tolist(), int(state[2])])


class StarCDataLoader(nnUNetDataLoader):
    """nnU-Net's loader plus per-sample frames and STAR-C targets.

    ``generate_train_batch`` repeats the official body (crop, transforms,
    stacking) of nnU-Net 2.8.1 and of master 47766ae3, which differ only in
    ``load_case``/``get_bbox``, and adds the recorded frame and the targets as
    ``batch['starc']``.
    The target sampler is seeded from NumPy's state without advancing it, so
    data and segmentation equal the official loader's for the same seed.
    """

    def __init__(self, *args: Any, star_builder: StarTargetBuilder | None = None, **kwargs: Any):
        super().__init__(*args, **kwargs)
        if self.patch_size_was_2d:
            raise ValueError("STAR-C is volumetric")
        self.star_builder = star_builder

    def generate_train_batch(self) -> dict:
        selected_keys = self.get_indices()
        data_all = None
        seg_all: Any = None
        samples = []
        # Seeded from the legacy state without advancing it, so crops and transforms match.
        rng = target_rng(np.random.get_state())
        with torch.no_grad(), threadpool_limits(limits=1, user_api=None):
            for j, key in enumerate(selected_keys):
                force_fg = self.get_do_oversample(j)
                loaded = self._data.load_case(key)
                shape = loaded[0].shape[1:]
                if len(loaded) == 4:  # nnU-Net 2.8.1: properties carry class_locations
                    data, seg, seg_prev, properties = loaded
                    bbox_lbs, bbox_ubs = self.get_bbox(
                        shape, force_fg, properties["class_locations"]
                    )
                else:  # nnU-Net master (47766ae3): lazily indexed sampling locations
                    data, seg, seg_prev = loaded
                    bbox_lbs, bbox_ubs = self.get_bbox(key, shape, force_fg)
                if seg_prev is not None:
                    raise ValueError("STAR-C does not support cascades")
                bbox = [[a, b] for a, b in zip(bbox_lbs, bbox_ubs, strict=True)]
                data_cropped = torch.from_numpy(crop_and_pad_nd(data, bbox, 0)).float()
                seg_cropped = torch.from_numpy(
                    crop_and_pad_nd(seg, bbox, -1, cast_cropped_to=np.int16)
                ).to(torch.int16)
                records: list[dict[str, Any]] = []
                if self.transforms is not None:
                    transformed = self.transforms(
                        **{"image": data_cropped, "segmentation": seg_cropped, FRAMES_KEY: records}
                    )
                    if self.star_builder is not None and transformed.get(FRAMES_KEY) is not records:
                        # A recording transform skips quietly when the key is gone, which
                        # would misalign the targets; refuse instead.
                        raise ValueError(
                            "An augmentation transform dropped the STAR-C frame record"
                        )
                    data_sample = transformed["image"]
                    seg_sample = transformed["segmentation"]
                else:
                    data_sample, seg_sample = data_cropped, seg_cropped
                if self.star_builder is not None:
                    frame = compose_patch_frame(bbox_lbs, records)
                    samples.append(self.star_builder.build(key, frame, rng))
                if data_all is None:
                    data_all = torch.empty(
                        (self.batch_size, *data_sample.shape), dtype=torch.float32
                    )
                data_all[j] = data_sample
                if isinstance(seg_sample, list):
                    if seg_all is None:
                        seg_all = [
                            torch.empty((self.batch_size, *s.shape), dtype=s.dtype)
                            for s in seg_sample
                        ]
                    for index, s in enumerate(seg_sample):
                        seg_all[index][j] = s
                else:
                    if seg_all is None:
                        seg_all = torch.empty(
                            (self.batch_size, *seg_sample.shape), dtype=seg_sample.dtype
                        )
                    seg_all[j] = seg_sample
        batch = {"data": data_all, "target": seg_all, "keys": selected_keys}
        if samples:
            batch["starc"] = collate_star_targets(samples)
        return batch


def _unwrap(network: Any) -> Any:
    module = getattr(network, "module", network)
    return getattr(module, "_orig_mod", module)


class nnUNetTrainerStarC(nnUNetTrainer):
    """nnU-Net's trainer with STAR-C auxiliary losses and full-volume targets.

    Before ``initialize()`` the backend calls ``configure_star`` with the bound
    training options and the target folder. ``freeze_backbone`` trains only
    the ``starc.*`` modules (the Stage-1 pilot on a frozen ResEnc L).
    """

    def __init__(
        self,
        plans: dict,
        configuration: str,
        fold: int,
        dataset_json: dict,
        device: torch.device = torch.device("cuda"),
    ) -> None:
        super().__init__(plans, configuration, fold, dataset_json, device)
        self.star_options = training_options(validate_starc_options(None))
        self.star_targets_dir: Path | None = None
        self.star_targets_manifest_sha256: str | None = None
        self._star_epoch: list[dict[str, float]] = []

    def configure_star(
        self,
        options: dict[str, Any] | None = None,
        *,
        targets_dir: str | Path | None = None,
        manifest_sha256: str | None = None,
    ) -> None:
        if self.was_initialized:
            raise RuntimeError("configure_star must run before initialize()")
        unknown = set(options or {}) - set(self.star_options)
        if unknown:
            raise ValueError(f"Unknown STAR-C training options: {sorted(unknown)}")
        self.star_options = training_options(validate_starc_options(dict(options or {})))
        self.star_targets_dir = None if targets_dir is None else Path(targets_dir)
        self.star_targets_manifest_sha256 = manifest_sha256

    def star_network(self) -> Any:
        network = _unwrap(self.network)
        if not hasattr(network, "starc"):
            raise ValueError("nnUNetTrainerStarC needs a StarCResEncUNet plan")
        return network

    def configure_optimizers(self) -> tuple[Any, Any]:
        if self.is_ddp:
            raise ValueError("STAR-C supports single-GPU training only")
        network = self.star_network()
        if self.star_options["freeze_backbone"]:
            for name, parameter in network.named_parameters():
                parameter.requires_grad_(name.startswith("starc."))
        parameters = [p for p in self.network.parameters() if p.requires_grad]
        from nnunetv2.training.lr_scheduler.polylr import PolyLRScheduler

        optimizer = torch.optim.SGD(
            parameters,
            self.initial_lr,
            weight_decay=self.weight_decay,
            momentum=0.99,
            nesterov=True,
        )
        return optimizer, PolyLRScheduler(optimizer, self.initial_lr, self.num_epochs)

    def star_targets_folder(self) -> Path:
        # No default: targets live outside every workspace and are bound explicitly
        # (precompute_star_targets.py refuses nnU-Net folders, the backend workspaces).
        if self.star_targets_dir is None:
            raise ValueError("STAR-C targets are not configured; call configure_star(targets_dir=)")
        return self.star_targets_dir

    def star_builder(self, cases: list[str], patch_size: Any) -> StarTargetBuilder:
        network = self.star_network()
        folder = self.star_targets_folder()
        segmentations = {}
        for case in cases:
            candidates = [
                Path(self.preprocessed_dataset_folder) / f"{case}_seg.{suffix}"
                for suffix in ("b2nd", "npy")
            ]
            existing = [path for path in candidates if path.is_file()]
            if len(existing) != 1:
                raise ValueError(f"Cannot identify the preprocessed segmentation of {case}")
            segmentations[case] = existing[0]
        manifest = verify_star_targets(
            folder,
            cases=cases,
            spacing=network.starc_spacing,
            rays=network.starc_options["rays"],
            lesion_labels=network.starc_options["lesion_labels"],
            segmentation_files=segmentations,
            manifest_sha256=self.star_targets_manifest_sha256,
        )
        return StarTargetBuilder(
            folder,
            spacing=network.starc_spacing,
            rays=network.starc_options["rays"],
            patch_size=patch_size,
            cell_stride=network.starc_stride,
            ray_samples=self.star_options["ray_samples"],
            max_gt_instances=self.star_options["max_gt_instances"],
            core_fraction=self.star_options["core_fraction"],
            sigma_min_mm=self.star_options["sigma_min_mm"],
            sigma_fraction=self.star_options["sigma_fraction"],
            min_ray_mm=network.starc_options["min_ray_mm"],
            max_ray_mm=network.starc_options["max_ray_mm"],
            file_hashes={case: manifest["cases"][case]["sha256"] for case in cases},
        )

    def get_dataloaders(self) -> tuple[Any, Any]:
        """nnU-Net 2.8.1's ``get_dataloaders`` with STAR-C loaders and frame recording."""
        trainer: Any = self
        if trainer.dataset_class is None:
            trainer.dataset_class = infer_dataset_class(self.preprocessed_dataset_folder)
        patch_size = self.configuration_manager.patch_size
        deep_supervision_scales = self._get_deep_supervision_scales()
        (
            rotation_for_DA,
            do_dummy_2d_data_aug,
            initial_patch_size,
            mirror_axes,
        ) = self.configure_rotation_dummyDA_mirroring_and_inital_patch_size()
        tr_transforms = enable_frame_recording(
            self.get_training_transforms(
                patch_size,
                rotation_for_DA,
                deep_supervision_scales,
                mirror_axes,
                do_dummy_2d_data_aug,
                use_mask_for_norm=self.configuration_manager.use_mask_for_norm,
                is_cascaded=self.is_cascaded,
                foreground_labels=self.label_manager.foreground_labels,
                regions=self.label_manager.foreground_regions
                if self.label_manager.has_regions
                else None,
                ignore_label=self.label_manager.ignore_label,
            )
        )
        val_transforms = self.get_validation_transforms(
            deep_supervision_scales,
            is_cascaded=self.is_cascaded,
            foreground_labels=self.label_manager.foreground_labels,
            regions=self.label_manager.foreground_regions
            if self.label_manager.has_regions
            else None,
            ignore_label=self.label_manager.ignore_label,
        )
        dataset_tr, dataset_val = self.get_tr_and_val_datasets()
        builder = self.star_builder(
            list(dataset_tr.identifiers) + list(dataset_val.identifiers), patch_size
        )
        dl_tr = StarCDataLoader(
            dataset_tr,
            self.batch_size,
            initial_patch_size,
            self.configuration_manager.patch_size,
            self.label_manager,
            oversample_foreground_percent=self.oversample_foreground_percent,
            sampling_probabilities=None,
            pad_sides=None,
            transforms=tr_transforms,
            probabilistic_oversampling=self.probabilistic_oversampling,
            star_builder=builder,
        )
        dl_val = StarCDataLoader(
            dataset_val,
            self.batch_size,
            self.configuration_manager.patch_size,
            self.configuration_manager.patch_size,
            self.label_manager,
            oversample_foreground_percent=self.oversample_foreground_percent,
            sampling_probabilities=None,
            pad_sides=None,
            transforms=val_transforms,
            probabilistic_oversampling=self.probabilistic_oversampling,
            star_builder=None,
        )
        allowed_num_processes = get_allowed_n_proc_DA()
        if allowed_num_processes == 0:
            mt_gen_train: Any = SingleThreadedAugmenter(dl_tr, None)
            mt_gen_val: Any = SingleThreadedAugmenter(dl_val, None)
        else:
            mt_gen_train = NonDetMultiThreadedAugmenter(
                data_loader=dl_tr,
                transform=None,
                num_processes=allowed_num_processes,
                num_cached=max(6, allowed_num_processes // 2),
                seeds=None,
                pin_memory=self.device.type == "cuda",
                wait_time=0.002,
            )
            mt_gen_val = NonDetMultiThreadedAugmenter(
                data_loader=dl_val,
                transform=None,
                num_processes=max(1, allowed_num_processes // 2),
                num_cached=max(3, allowed_num_processes // 4),
                seeds=None,
                pin_memory=self.device.type == "cuda",
                wait_time=0.002,
            )
        _ = next(mt_gen_train)
        _ = next(mt_gen_val)
        return mt_gen_train, mt_gen_val

    def teacher_instances(self, star: dict[str, torch.Tensor]) -> StarInstances:
        """Ground-truth inner centres in the patch, jittered by N(0, jitter mm) per axis.

        At most ``max_instances`` per sample (the largest, as the targets list
        them largest first), the same cap as proposals, so teacher steps never
        render more stars than an inference step.
        """
        network = self.star_network()
        limit = int(network.starc_options["max_instances"])
        centres = star["centres"][:, :limit].float()
        spacing = torch.tensor(network.starc_spacing, device=centres.device)
        jitter = torch.randn_like(centres) * self.star_options["teacher_jitter_mm"] / spacing
        valid = star["centre_valid"][:, :limit].bool()
        return StarInstances(centres=centres + jitter, valid=valid)

    def star_losses(
        self, aux: dict[str, Any], star: dict[str, torch.Tensor]
    ) -> tuple[torch.Tensor, torch.Tensor]:
        centre = centre_focal_loss(aux["heat_logits"], star["heatmap"])
        ray = ray_l1_loss(
            aux["log_radii"], star["ray_positions"], star["ray_targets"], star["ray_mask"]
        )
        return centre, ray

    def train_step(self, batch: dict) -> dict:
        data = batch["data"].to(self.device, non_blocking=True)
        target = batch["target"]
        if isinstance(target, list):
            target = [i.to(self.device, non_blocking=True) for i in target]
        else:
            target = target.to(self.device, non_blocking=True)
        star = {k: v.to(self.device, non_blocking=True) for k, v in batch["starc"].items()}
        network = self.star_network()
        probability = self.star_options["teacher_probability"]
        if probability > 0 and torch.rand(1).item() < probability:
            network.set_star_instances(self.teacher_instances(star))
        self.optimizer.zero_grad(set_to_none=True)
        with (
            autocast(self.device.type, enabled=True)
            if self.device.type == "cuda"
            else dummy_context()
        ):
            output = self.network(data)
            seg_loss = self.loss(output, target)
        centre_loss, ray_loss = self.star_losses(network.star_aux, star)
        loss = (
            seg_loss
            + self.star_options["centre_weight"] * centre_loss
            + self.star_options["ray_weight"] * ray_loss
        )
        if self.grad_scaler is not None:
            self.grad_scaler.scale(loss).backward()
            self.grad_scaler.unscale_(self.optimizer)
            torch.nn.utils.clip_grad_norm_(self.network.parameters(), 12)
            self.grad_scaler.step(self.optimizer)
            self.grad_scaler.update()
        else:
            loss.backward()
            torch.nn.utils.clip_grad_norm_(self.network.parameters(), 12)
            self.optimizer.step()
        parts = {
            "seg_loss": float(seg_loss.detach()),
            "centre_loss": float(centre_loss.detach()),
            "ray_loss": float(ray_loss.detach()),
            "tau_mm": float(network.starc.tau().detach()),
        }
        self._star_epoch.append(parts)
        return {"loss": loss.detach().cpu().numpy()}

    def on_train_epoch_end(self, train_outputs: list[dict]) -> None:
        super().on_train_epoch_end(train_outputs)
        if self._star_epoch:
            means = {
                key: float(np.mean([row[key] for row in self._star_epoch]))
                for key in self._star_epoch[0]
            }
            weights = self.star_network().starc.fusion_weight.detach().cpu().tolist()
            self.print_to_log_file(
                "STAR-C "
                + " ".join(f"{key} {value:.4f}" for key, value in means.items())
                + f" fusion_weight {np.round(weights, 4).tolist()}"
            )
        self._star_epoch = []


class nnUNetTrainerStarCFinetune(nnUNetTrainerStarC):
    """``nnUNetTrainerStarC`` with the fine-tuning defaults of ``nnUNetTrainerFinetune``."""

    def __init__(
        self,
        plans: dict,
        configuration: str,
        fold: int,
        dataset_json: dict,
        device: torch.device = torch.device("cuda"),
    ) -> None:
        super().__init__(plans, configuration, fold, dataset_json, device)
        self.initial_lr = FINETUNE_INITIAL_LR
        self.num_epochs = FINETUNE_EPOCHS


class StarCPredictor(nnUNetPredictor):
    """Two-pass sliding window: tile detections, case-level NMS, then case-level rendering.

    Pass 1 runs every tile once without mirroring and records each tile peak in
    padded-case voxels with its rays, score and the tile's Gaussian importance
    at the peak. ``merge_tile_detections`` keeps one detection per lesion.
    Pass 2 is nnU-Net's Gaussian-blended sliding window; every forward,
    mirrored copies included, renders the case-level stars whose boxes reach
    the tile, so a lesion cut by a tile border is still completed.
    """

    def __init__(
        self,
        *args: Any,
        star_two_pass: bool = True,
        nms_radius_mm: float = 5.0,
        max_case_instances: int = 32,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.star_two_pass = star_two_pass
        self.nms_radius_mm = float(nms_radius_mm)
        self.max_case_instances = int(max_case_instances)
        self._star_tile: tuple[np.ndarray, list[CaseDetection]] | None = None
        self.star_case_detections: list[CaseDetection] = []

    def _star_network(self) -> Any:
        network = _unwrap(self.network)
        if not hasattr(network, "starc"):
            raise ValueError("StarCPredictor needs a StarCResEncUNet")
        return network

    def detect_case_instances(self, data: torch.Tensor, slicers: list) -> list[CaseDetection]:
        network = self._star_network()
        patch = tuple(int(v) for v in self.configuration_manager.patch_size)
        importance = compute_gaussian(
            patch, sigma_scale=1.0 / 8, value_scaling_factor=1, device=torch.device("cpu")
        ).float()
        importance = importance / importance.max()
        found: list[CaseDetection] = []
        for slicer in slicers:
            tile = data[slicer][None].to(self.device)
            network.set_star_instances(None)
            self.network(tile)
            instances = network.star_aux["instances"]
            origin = np.asarray([s.start for s in slicer[1:]], np.float64)
            for k in instances.valid[0].nonzero().flatten().tolist():
                centre = instances.centres[0, k].double().cpu().numpy()
                index = tuple(
                    int(np.clip(round(c), 0, n - 1)) for c, n in zip(centre, patch, strict=True)
                )
                found.append(
                    CaseDetection(
                        centre=centre + origin,
                        log_radii=instances.log_radii[0, k].double().cpu().numpy(),
                        score=float(instances.scores[0, k]),
                        weight=float(importance[index]),
                    )
                )
        options = network.starc_options
        return merge_tile_detections(
            found,
            star_geometry(options["rays"]),
            network.starc_spacing,
            threshold=options["centre_threshold"],
            nms_radius_mm=self.nms_radius_mm,
            max_instances=self.max_case_instances,
            min_ray_mm=options["min_ray_mm"],
            max_ray_mm=options["max_ray_mm"],
        )

    def tile_instances(
        self, origin: np.ndarray, shape: tuple[int, ...], flips: tuple[int, ...]
    ) -> StarInstances:
        """Case instances whose boxes reach this tile, in its (possibly mirrored) frame."""
        network = self._star_network()
        options = network.starc_options
        spacing = np.asarray(network.starc_spacing, np.float64)
        size = np.asarray(shape, np.float64)
        selected = []
        for detection in self.star_case_detections:
            centre = detection.centre - origin
            radii = np.exp(
                np.clip(
                    detection.log_radii,
                    math.log(options["min_ray_mm"]),
                    math.log(options["max_ray_mm"]),
                )
            )
            reach = (radii.max() + options["box_margin_mm"]) / spacing
            if np.all(centre + reach >= 0) and np.all(centre - reach <= size - 1):
                selected.append((detection, centre))
        selected.sort(key=lambda item: -item[0].score)
        selected = selected[: options["max_instances"]]
        transform = np.eye(3)
        centres = np.zeros((1, len(selected), 3))
        for axis in flips:
            transform[axis, axis] = -1.0
        for k, (_, centre) in enumerate(selected):
            mirrored = centre.copy()
            for axis in flips:
                mirrored[axis] = size[axis] - 1 - mirrored[axis]
            centres[0, k] = mirrored
        count = len(selected)
        log_radii = (
            np.stack([d.log_radii for d, _ in selected])
            if selected
            else np.zeros((0, options["rays"]))
        )
        return StarInstances(
            centres=torch.tensor(centres, dtype=torch.float32, device=self.device),
            valid=torch.ones((1, count), dtype=torch.bool, device=self.device),
            scores=torch.tensor([[d.score for d, _ in selected]], device=self.device),
            log_radii=torch.tensor(
                log_radii.reshape(1, count, options["rays"]),
                dtype=torch.float32,
                device=self.device,
            ),
            transforms=torch.tensor(transform, dtype=torch.float32, device=self.device).expand(
                1, count, 3, 3
            ),
        )

    @torch.inference_mode()
    def _internal_maybe_mirror_and_predict(self, x: torch.Tensor) -> torch.Tensor:
        if self._star_tile is None:
            return super()._internal_maybe_mirror_and_predict(x)
        network = self._star_network()
        origin, _ = self._star_tile
        shape = tuple(int(v) for v in x.shape[2:])
        network.set_star_instances(self.tile_instances(origin, shape, ()))
        prediction = self.network(x)
        mirror_axes = self.allowed_mirroring_axes if self.use_mirroring else None
        if mirror_axes is not None:
            if max(mirror_axes) > x.ndim - 3:
                raise ValueError("mirror_axes does not match the dimension of the input")
            axes_combinations = [
                c
                for i in range(len(mirror_axes))
                for c in itertools.combinations(mirror_axes, i + 1)
            ]
            for axes in axes_combinations:
                network.set_star_instances(self.tile_instances(origin, shape, tuple(axes)))
                flip = tuple(axis + 2 for axis in axes)
                prediction += torch.flip(self.network(torch.flip(x, flip)), flip)
            prediction /= len(axes_combinations) + 1
        return prediction

    @torch.inference_mode()
    def _internal_predict_sliding_window_return_logits(
        self, data: torch.Tensor, slicers: list, do_on_device: bool = True
    ) -> torch.Tensor:
        """nnU-Net 2.8.1's blended sliding window, sequential, with STAR-C's two passes.

        ``aux_only`` leaves the logits untouched, so it takes nnU-Net's single pass.
        """
        if not self.star_two_pass or self._star_network().starc.fusion == "aux_only":
            self.star_case_detections = []
            return super()._internal_predict_sliding_window_return_logits(
                data, slicers, do_on_device
            )
        results_device = self.device if do_on_device else torch.device("cpu")
        empty_cache(self.device)
        data = data.to(results_device)
        self.star_case_detections = self.detect_case_instances(data, slicers)
        predicted_logits = torch.zeros(
            (self.label_manager.num_segmentation_heads, *data.shape[1:]),
            dtype=torch.half,
            device=results_device,
        )
        n_predictions = torch.zeros(data.shape[1:], dtype=torch.half, device=results_device)
        gaussian: Any = (
            compute_gaussian(
                tuple(self.configuration_manager.patch_size),
                sigma_scale=1.0 / 8,
                value_scaling_factor=10,
                device=results_device,
            )
            if self.use_gaussian
            else 1
        )
        try:
            for slicer in slicers:
                workon = torch.clone(data[slicer][None], memory_format=torch.contiguous_format)
                self._star_tile = (
                    np.asarray([s.start for s in slicer[1:]], np.float64),
                    self.star_case_detections,
                )
                prediction = self._internal_maybe_mirror_and_predict(workon.to(self.device))[0].to(
                    results_device
                )
                if self.use_gaussian:
                    prediction *= gaussian
                predicted_logits[slicer] += prediction
                n_predictions[slicer[1:]] += gaussian
        finally:
            self._star_tile = None
        torch.div(predicted_logits, n_predictions, out=predicted_logits)
        if torch.any(torch.isinf(predicted_logits)):
            raise RuntimeError("Encountered inf in predicted array")
        return predicted_logits
