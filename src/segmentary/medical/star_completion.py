"""STAR-C: star-convex lesion completion with gated logit fusion.

Geometry, targets and the network-side operators live here; the ResEnc
subclass is ``nnunet_architectures.StarCResEncUNet`` and the trainer, data
loader and two-pass predictor are in ``nnunet_star_trainer``. This module
needs only NumPy, SciPy and Torch, so it is tested without nnU-Net.

Conventions. Axes are nnU-Net array axes (z, y, x). ``spacing`` is the plan's
3d_fullres spacing in mm, and the physical position of voxel index ``i`` is
``i * spacing``. Rays are ``R`` Fibonacci unit vectors in physical (z, y, x).
A star is the polyhedron on the ray end points, a convex-hull triangulation of
the directions; in direction ``u`` inside facet (a, b, c) with cone coordinates
``lambda = M_f^-1 u`` its radius is the weighted harmonic mean
``1 / sum(lambda_a / r_a)``. Decoder cell ``j`` of a level with stride ``t``
covers full-resolution voxels ``[j t, (j + 1) t)`` and is centred at voxel
``j t + (t - 1) / 2``.

Ray targets are never taken from a training patch. ``compute_case_targets``
runs offline on the full preprocessed segmentation; ``StarTargetBuilder`` maps
each augmented patch back to the volume with the exact affine frame recorded
during augmentation and marches through the case's full instance map.
"""

from __future__ import annotations

import functools
import hashlib
import io
import math
from collections import OrderedDict
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

import numpy as np
import torch
from torch import nn
from torch.nn import functional as F

from . import recipe_plan as _recipe_plan

# Options and plan transfer live in the Torch-free ``recipe_plan``, so the
# orchestration interpreter validates recipes without Torch; re-exported here.
FUSION_MODES = _recipe_plan.FUSION_MODES
STARC_CLASS = _recipe_plan.STARC_CLASS
STARC_DEFAULTS = _recipe_plan.STARC_DEFAULTS
STARC_NETWORK_DEFAULTS = _recipe_plan.STARC_NETWORK_DEFAULTS
STARC_TRAINING_DEFAULTS = _recipe_plan.STARC_TRAINING_DEFAULTS
check_starc_dataset = _recipe_plan.check_starc_dataset
network_options = _recipe_plan.network_options
starc_plan_kwargs = _recipe_plan.starc_plan_kwargs
training_options = _recipe_plan.training_options
transfer_starc_plan = _recipe_plan.transfer_starc_plan
validate_starc_options = _recipe_plan.validate_starc_options

TARGET_SCHEMA = _recipe_plan.STARC_TARGET_SCHEMA
_EPS = 1e-6
# Directions per chunk in StarRenderer.facet_weights (about 56 MB of fp32 temporaries).
RADIUS_CHUNK = 1 << 18


# ---------------------------------------------------------------------------
# Ray geometry (NumPy)
# ---------------------------------------------------------------------------


def fibonacci_directions(count: int) -> np.ndarray:
    """``count`` unit vectors in physical (z, y, x), the set S0 measured."""
    index = np.arange(count, dtype=np.float64) + 0.5
    polar = np.arccos(1 - 2 * index / count)
    azimuth = np.pi * (1 + 5**0.5) * index
    return np.stack(
        [np.cos(polar), np.sin(polar) * np.sin(azimuth), np.sin(polar) * np.cos(azimuth)], 1
    )


def _bins(directions: np.ndarray, shape: tuple[int, int]) -> tuple[np.ndarray, np.ndarray]:
    polar = np.arccos(np.clip(directions[..., 0], -1.0, 1.0))
    azimuth = np.arctan2(directions[..., 1], directions[..., 2])
    rows = np.clip((polar / np.pi * shape[0]).astype(np.int64), 0, shape[0] - 1)
    cols = ((azimuth + np.pi) / (2 * np.pi) * shape[1]).astype(np.int64) % shape[1]
    return rows, cols


@dataclass(frozen=True)
class StarGeometry:
    """Directions, hull facets, per-facet inverse cone matrices and a facet lookup table.

    ``lut`` (rows, cols, C) lists up to C candidate facets per equirectangular
    direction bin (those containing the bin's centre, edge midpoints or corners); the
    candidate with the largest minimum cone coordinate contains the direction.
    """

    directions: np.ndarray
    facets: np.ndarray
    inverse: np.ndarray
    lut: np.ndarray

    @property
    def rays(self) -> int:
        return len(self.directions)

    def digest(self) -> str:
        """SHA256 of the direction set; facets and table are derived from it."""
        return hashlib.sha256(np.ascontiguousarray(self.directions).tobytes()).hexdigest()

    def _cone(self, directions: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        rows, cols = _bins(directions, self.lut.shape[:2])
        candidates = self.lut[rows, cols]
        weights = np.einsum("nkij,nj->nki", self.inverse[candidates], directions)
        best = weights.min(2).argmax(1)
        pick = np.arange(len(directions))
        return candidates[pick, best], np.clip(weights[pick, best], 0.0, None)

    def radius(self, radii: np.ndarray, directions: np.ndarray) -> np.ndarray:
        """Polyhedron radius along unit ``directions`` (N, 3) for one star's ``radii`` (R,)."""
        facet, weights = self._cone(directions)
        corners = np.maximum(radii[self.facets[facet]], _EPS)
        return 1.0 / np.maximum((weights / corners).sum(1), _EPS)


def _facet_of(
    directions: np.ndarray, facets: np.ndarray, inverse: np.ndarray, centroids: np.ndarray
) -> np.ndarray:
    from scipy.spatial import cKDTree

    candidates = cKDTree(centroids).query(directions, k=min(8, len(facets)))[1]
    weights = np.einsum("nkij,nj->nki", inverse[candidates], directions)
    best = weights.min(2).argmax(1)
    return candidates[np.arange(len(directions)), best]


def _unit(polar: np.ndarray, azimuth: np.ndarray) -> np.ndarray:
    return np.stack(
        [np.cos(polar), np.sin(polar) * np.sin(azimuth), np.sin(polar) * np.cos(azimuth)], -1
    )


@functools.lru_cache(maxsize=8)
def star_geometry(
    rays: int = 96, lut_shape: tuple[int, int] = (256, 512), candidates: int = 6
) -> StarGeometry:
    from scipy.spatial import ConvexHull

    directions = fibonacci_directions(rays)
    facets = np.sort(ConvexHull(directions).simplices, axis=1)
    facets = facets[np.lexsort(facets.T[::-1])]
    inverse = np.linalg.inv(np.stack([directions[facets[:, i]] for i in range(3)], 2))
    centroids = directions[facets].mean(1)
    centroids /= np.linalg.norm(centroids, axis=1, keepdims=True)
    rows, cols = lut_shape
    fractions = (0.5, 0.0, 1.0)  # bin centre first, then its edges and corners
    samples = []
    for row_fraction in fractions:
        for col_fraction in fractions:
            polar = np.clip((np.arange(rows) + row_fraction) / rows, 0, 1) * np.pi
            azimuth = (np.arange(cols) + col_fraction) / cols * 2 * np.pi - np.pi
            grid_polar, grid_azimuth = np.meshgrid(polar, azimuth, indexing="ij")
            unit = _unit(grid_polar, grid_azimuth).reshape(-1, 3)
            samples.append(_facet_of(unit, facets, inverse, centroids))
    found = np.stack(samples, 1)
    repeat = np.zeros(found.shape, bool)
    for j in range(1, found.shape[1]):
        repeat[:, j] = (found[:, :j] == found[:, j : j + 1]).any(1)
    # First occurrences in sample order; short rows end with repeats, which are valid too.
    order = np.argsort(repeat, axis=1, kind="stable")[:, :candidates]
    lut = np.take_along_axis(found, order, 1).reshape(rows, cols, candidates)
    for array in (directions, facets, inverse, lut):
        array.setflags(write=False)
    return StarGeometry(directions, facets, inverse, lut)


def exact_star_radius(
    geometry: StarGeometry, radii: np.ndarray, directions: np.ndarray
) -> np.ndarray:
    """Reference polyhedron radius without the lookup table (S0's ``star_radius``)."""
    centroids = geometry.directions[geometry.facets].mean(1)
    centroids /= np.linalg.norm(centroids, axis=1, keepdims=True)
    facet = _facet_of(directions, geometry.facets, geometry.inverse, centroids)
    points = radii[geometry.facets[facet]][..., None] * geometry.directions[geometry.facets[facet]]
    normal = np.cross(points[:, 1] - points[:, 0], points[:, 2] - points[:, 0])
    height = (normal * points[:, 0]).sum(1)
    along = (normal * directions).sum(1)
    with np.errstate(divide="ignore", invalid="ignore"):
        result = np.where(np.abs(along) > 1e-12, height / along, 0.0)
    return np.clip(np.nan_to_num(result), 0, None)


def march_exit_mm(
    instances: np.ndarray,
    label: int,
    origins: np.ndarray,
    directions: np.ndarray,
    spacing: Sequence[float] | np.ndarray,
    *,
    step_mm: float,
    max_mm: float,
    refine: int = 6,
    chunk: int = 8,
) -> tuple[np.ndarray, np.ndarray]:
    """First exit distance (mm) from component ``label`` along each ray.

    ``origins`` (N, 3) are continuous voxel coordinates of ``instances``;
    ``directions`` are physical unit vectors, (R, 3) shared or (N, R, 3) per
    origin. Voxels are looked up by nearest index and everything outside the
    array is background. The exit is bracketed with ``step_mm`` and refined by
    ``refine`` bisections. Rays still inside after ``max_mm`` return ``max_mm``
    with ``exited`` false.
    """
    spacing_array = np.asarray(spacing, dtype=np.float64)
    shape = np.asarray(instances.shape)
    origins = np.asarray(origins, dtype=np.float64).reshape(-1, 3)
    directions = np.asarray(directions, dtype=np.float64)
    if directions.ndim == 2:
        directions = np.broadcast_to(directions, (len(origins), *directions.shape))
    count = math.ceil(max_mm / step_mm)
    steps = np.arange(1, count + 1, dtype=np.float64) * step_mm

    def inside(points_mm: np.ndarray) -> np.ndarray:
        index = np.rint(points_mm / spacing_array).astype(np.int64)
        valid = np.all((index >= 0) & (index < shape), axis=-1)
        index = np.clip(index, 0, shape - 1)
        return valid & (instances[index[..., 0], index[..., 1], index[..., 2]] == label)

    distances = np.empty(directions.shape[:2], dtype=np.float64)
    exited = np.empty(directions.shape[:2], dtype=bool)
    for start in range(0, len(origins), chunk):
        stop = min(start + chunk, len(origins))
        base = origins[start:stop, None, :] * spacing_array
        rays = directions[start:stop]
        points = base[:, :, None, :] + steps[None, None, :, None] * rays[:, :, None, :]
        outside = ~inside(points)
        hit = outside.any(2)
        first = np.where(hit, outside.argmax(2), count - 1)
        low = np.where(first > 0, steps[np.maximum(first - 1, 0)], 0.0)
        high = steps[first]
        for _ in range(refine):
            middle = (low + high) / 2
            inner = inside(base + middle[..., None] * rays)
            low = np.where(inner, middle, low)
            high = np.where(inner, high, middle)
        distances[start:stop] = np.where(hit, (low + high) / 2, max_mm)
        exited[start:stop] = hit
    return distances, exited


# ---------------------------------------------------------------------------
# Offline full-volume targets
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CaseTargets:
    """Full-volume lesion instances and centre rays of one preprocessed case."""

    shape: np.ndarray
    spacing: np.ndarray
    crop_origin: np.ndarray
    instances: np.ndarray
    edt_mm: np.ndarray
    centres: np.ndarray
    max_edt_mm: np.ndarray
    volume_mm3: np.ndarray
    equivalent_radius_mm: np.ndarray
    bbox_diagonal_mm: np.ndarray
    labels: np.ndarray
    rays_mm: np.ndarray

    @property
    def count(self) -> int:
        return len(self.centres)

    def arrays(self) -> dict[str, np.ndarray]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


def _plateau_centres(
    edt: np.ndarray,
    components: np.ndarray,
    max_edt: np.ndarray,
    centroids: np.ndarray,
    spacing: np.ndarray,
    tolerance_mm: float = 1e-3,
) -> np.ndarray:
    """The EDT-maximal voxel of each component that lies closest to its centroid.

    Elongated lesions have an EDT plateau along their long axis, where
    ``maximum_position`` would pick whichever voxel wins last-bit rounding
    differences between platforms. Choosing the plateau voxel nearest the
    centroid (then the lowest index) makes the centre a property of the shape.
    """
    centres = np.zeros((len(max_edt), 3), np.float64)
    for k, peak in enumerate(max_edt, start=1):
        candidates = np.argwhere((components == k) & (edt >= peak - tolerance_mm))
        distance = np.linalg.norm((candidates - centroids[k - 1]) * spacing, axis=1)
        nearest = np.flatnonzero(distance <= distance.min() + tolerance_mm)
        centres[k - 1] = candidates[nearest[0]]
    return centres


def compute_case_targets(
    segmentation: np.ndarray,
    spacing: Sequence[float],
    lesion_labels: Sequence[int],
    geometry: StarGeometry,
    *,
    border: int = 2,
    step_fraction: float = 0.25,
    refine: int = 6,
) -> CaseTargets:
    """Instances (26-connected components of the lesion labels), inner centres and rays.

    The inner centre is the maximum of the mm Euclidean distance transform of
    the zero-padded component, taking the plateau voxel nearest the centroid
    (``_plateau_centres``); the rays are first exits from it in volume mm, as in S0.
    """
    from scipy import ndimage

    segmentation = np.asarray(segmentation)
    if segmentation.ndim == 4 and segmentation.shape[0] == 1:
        segmentation = segmentation[0]
    if segmentation.ndim != 3:
        raise ValueError("STAR-C targets need one 3D segmentation")
    spacing_array = np.asarray(spacing, dtype=np.float64)
    shape = np.asarray(segmentation.shape, dtype=np.int64)
    mask = np.isin(segmentation, np.asarray(lesion_labels))
    rays = geometry.rays
    if not mask.any():
        return CaseTargets(
            shape=shape,
            spacing=spacing_array,
            crop_origin=np.zeros(3, np.int64),
            instances=np.zeros((1, 1, 1), np.uint16),
            edt_mm=np.zeros((1, 1, 1), np.float16),
            centres=np.zeros((0, 3), np.float64),
            max_edt_mm=np.zeros(0, np.float64),
            volume_mm3=np.zeros(0, np.float64),
            equivalent_radius_mm=np.zeros(0, np.float64),
            bbox_diagonal_mm=np.zeros(0, np.float64),
            labels=np.zeros(0, np.int64),
            rays_mm=np.zeros((0, rays), np.float32),
        )
    present = np.argwhere(mask)
    low = np.maximum(present.min(0) - border, 0)
    high = np.minimum(present.max(0) + 1 + border, shape)
    window = tuple(slice(a, b) for a, b in zip(low, high, strict=True))
    crop = mask[window]
    components, count = ndimage.label(crop, structure=np.ones((3, 3, 3), bool))
    if count > np.iinfo(np.uint16).max:
        raise ValueError("Too many lesion components for uint16 instances")
    # Components are separated by background, so the union's EDT is each component's EDT.
    edt = ndimage.distance_transform_edt(np.pad(crop, 1), sampling=spacing_array)[1:-1, 1:-1, 1:-1]
    edt = np.where(crop, edt, 0.0)
    index = np.arange(1, count + 1)
    max_edt = np.asarray(ndimage.maximum(edt, components, index), dtype=np.float64)
    centroids = np.asarray(ndimage.center_of_mass(crop, components, index), dtype=np.float64)
    centres = _plateau_centres(edt, components, max_edt, centroids, spacing_array)
    voxels = np.bincount(components.ravel(), minlength=count + 1)[1:]
    volume = voxels * float(np.prod(spacing_array))
    radius = (3 * volume / (4 * np.pi)) ** (1 / 3)
    seg_crop = segmentation[window]
    labels = np.zeros(count, np.int64)
    diagonal = np.zeros(count, np.float64)
    ray_table = np.zeros((count, rays), np.float32)
    step = step_fraction * float(spacing_array.min())
    for k, box in enumerate(ndimage.find_objects(components), start=1):
        assert box is not None
        values, counts = np.unique(seg_crop[box][components[box] == k], return_counts=True)
        labels[k - 1] = int(values[counts.argmax()])
        extent = np.asarray([b.stop - b.start for b in box], dtype=np.float64) * spacing_array
        diagonal[k - 1] = float(np.linalg.norm(extent))
        distances, _ = march_exit_mm(
            components,
            k,
            centres[k - 1 : k],
            geometry.directions,
            spacing_array,
            step_mm=step,
            max_mm=diagonal[k - 1] + float(spacing_array.max()),
            refine=refine,
        )
        ray_table[k - 1] = distances[0]
    return CaseTargets(
        shape=shape,
        spacing=spacing_array,
        crop_origin=low.astype(np.int64),
        instances=components.astype(np.uint16),
        edt_mm=edt.astype(np.float16),
        centres=centres + low,
        max_edt_mm=max_edt,
        volume_mm3=volume,
        equivalent_radius_mm=radius,
        bbox_diagonal_mm=diagonal,
        labels=labels,
        rays_mm=ray_table,
    )


def save_case_targets(path: Path, targets: CaseTargets) -> str:
    """Write ``targets`` as a compressed ``.npz``; return its sha256."""
    with path.open("xb") as handle:
        arrays: dict[str, Any] = targets.arrays()
        np.savez_compressed(handle, **arrays)
    return sha256_file(path)


def load_case_targets(path: Path, sha256: str | None = None) -> CaseTargets:
    """Load one case's targets; with ``sha256``, the bytes read are the bytes verified."""
    payload = Path(path).read_bytes()
    if sha256 is not None and hashlib.sha256(payload).hexdigest() != sha256:
        raise ValueError(f"STAR-C target file changed: {Path(path).stem}")
    with np.load(io.BytesIO(payload), allow_pickle=False) as data:
        arrays = {name: np.array(data[name]) for name in CaseTargets.__dataclass_fields__}
    return CaseTargets(**arrays)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def target_manifest_path(targets_dir: Path) -> Path:
    return Path(targets_dir) / _recipe_plan.STARC_TARGET_MANIFEST


def verify_star_targets(
    targets_dir: Path,
    *,
    cases: Sequence[str],
    spacing: Sequence[float],
    rays: int,
    lesion_labels: Sequence[int],
    segmentation_files: dict[str, Path] | None = None,
    manifest_sha256: str | None = None,
) -> dict[str, Any]:
    """Check a precomputed target folder against this run before any target is read.

    Verifies the manifest hash (when bound), schema, ray set, spacing and
    lesion labels, then every requested case's ``.npz`` hash and, when given,
    the hash of the segmentation it was computed from.
    """
    import json

    manifest_path = target_manifest_path(targets_dir)
    if manifest_sha256 is not None and sha256_file(manifest_path) != manifest_sha256:
        raise ValueError("STAR-C target manifest differs from the bound sha256")
    manifest = json.loads(manifest_path.read_text())
    if manifest.get("schema") != TARGET_SCHEMA:
        raise ValueError("Unknown STAR-C target schema")
    if (
        manifest.get("rays") != rays
        or manifest.get("directions_sha256") != star_geometry(rays).digest()
    ):
        raise ValueError("STAR-C targets use a different ray set")
    if not np.allclose(manifest.get("spacing"), list(spacing), rtol=0, atol=1e-6):
        raise ValueError("STAR-C targets use a different spacing")
    if list(manifest.get("lesion_labels", [])) != list(lesion_labels):
        raise ValueError("STAR-C targets use different lesion labels")
    method = _recipe_plan.starc_target_method_problems(manifest)
    if method:
        raise ValueError(f"STAR-C targets use a different target method: {method}")
    entries = manifest.get("cases", {})
    missing = sorted(set(cases) - set(entries))
    if missing:
        raise ValueError(f"STAR-C targets are missing cases: {missing[:5]}")
    for case in cases:
        entry = entries[case]
        if sha256_file(Path(targets_dir) / f"{case}.npz") != entry["sha256"]:
            raise ValueError(f"STAR-C target file changed: {case}")
        if segmentation_files is not None and (
            sha256_file(segmentation_files[case]) != entry["segmentation_sha256"]
        ):
            raise ValueError(f"STAR-C targets were computed from a different segmentation: {case}")
    return manifest


def render_star_mask(
    shape: Sequence[int],
    spacing: Sequence[float],
    centre: np.ndarray,
    radii: np.ndarray,
    geometry: StarGeometry,
) -> np.ndarray:
    """Hard star polyhedron (``rho <= R(u)``) in a volume, for representability checks."""
    spacing_array = np.asarray(spacing, dtype=np.float64)
    out = np.zeros(tuple(shape), bool)
    reach = float(radii.max()) + float(spacing_array.max())
    low = np.maximum(np.floor(centre - reach / spacing_array).astype(int), 0)
    high = np.minimum(np.ceil(centre + reach / spacing_array).astype(int) + 1, shape)
    if np.any(high <= low):
        return out
    grid = np.stack(
        np.meshgrid(*[np.arange(a, b) for a, b in zip(low, high, strict=True)], indexing="ij"),
        -1,
    ).reshape(-1, 3)
    offset = (grid - centre) * spacing_array
    rho = np.linalg.norm(offset, axis=1)
    unit = offset / np.maximum(rho, 1e-9)[:, None]
    unit[rho < 1e-9] = (1.0, 0.0, 0.0)
    inside = rho <= geometry.radius(radii.astype(np.float64), unit)
    out[tuple(slice(a, b) for a, b in zip(low, high, strict=True))] = inside.reshape(high - low)
    return out


# ---------------------------------------------------------------------------
# Augmentation frames and patch targets (augmentation workers, NumPy)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PatchFrame:
    """Affine map from final patch voxel ``p`` to preprocessed volume voxel ``J p + o``."""

    jacobian: np.ndarray
    offset: np.ndarray

    def to_volume(self, points: np.ndarray) -> np.ndarray:
        return np.asarray(points, np.float64) @ self.jacobian.T + self.offset

    def to_patch(self, points: np.ndarray) -> np.ndarray:
        return (np.asarray(points, np.float64) - self.offset) @ np.linalg.inv(self.jacobian).T

    def physical(self, spacing: Sequence[float] | np.ndarray) -> np.ndarray:
        """``A = S J S^-1``: patch mm to volume mm (a general linear map)."""
        scale = np.diag(np.asarray(spacing, np.float64))
        return scale @ self.jacobian @ np.linalg.inv(scale)


def frame_record(axes: Sequence[int], matrix: np.ndarray, offset: np.ndarray) -> dict[str, Any]:
    """One output-to-input affine step of the augmentation pipeline on ``axes``."""
    return {
        "axes": tuple(int(axis) for axis in axes),
        "matrix": np.asarray(matrix, np.float64),
        "offset": np.asarray(offset, np.float64),
    }


def mirror_record(axes: Sequence[int], shape: Sequence[int]) -> dict[str, Any]:
    axes = tuple(int(axis) for axis in axes)
    matrix = np.eye(len(axes))
    offset = np.zeros(len(axes))
    for i, axis in enumerate(axes):
        matrix[i, i] = -1.0
        offset[i] = shape[axis] - 1
    return frame_record(axes, matrix, offset)


def compose_patch_frame(bbox_lower: Sequence[int], records: Sequence[dict[str, Any]]) -> PatchFrame:
    """Compose recorded output-to-input steps (in application order) and the crop."""
    jacobian = np.eye(3)
    offset = np.zeros(3)
    for record in reversed(records):
        step = np.eye(3)
        shift = np.zeros(3)
        axes = list(record["axes"])
        step[np.ix_(axes, axes)] = record["matrix"]
        shift[axes] = record["offset"]
        jacobian, offset = step @ jacobian, step @ offset + shift
    return PatchFrame(jacobian, offset + np.asarray(bbox_lower, np.float64))


def cell_centres(cells: Sequence[int], stride: Sequence[int]) -> np.ndarray:
    """Full-resolution voxel coordinates of every cell centre, (prod(cells), 3)."""
    axes = [np.arange(n) * t + (t - 1) / 2 for n, t in zip(cells, stride, strict=True)]
    return np.stack(np.meshgrid(*axes, indexing="ij"), -1).reshape(-1, 3)


def voxel_to_cell(points: np.ndarray, stride: Sequence[int]) -> np.ndarray:
    stride_array = np.asarray(stride, np.float64)
    return (np.asarray(points, np.float64) - (stride_array - 1) / 2) / stride_array


class StarTargetBuilder:
    """Patch targets from full-volume case tables and an augmentation frame.

    Returned per sample (fixed shapes, so batches stack):

    - ``heatmap`` (1, *cells): Gaussian centre heatmap, exactly 1 at the cell
      containing each in-patch inner centre;
    - ``ray_positions`` (N, 3), level cell coordinates of the ray samples (the
      in-patch ground-truth centres first, then core cells);
    - ``ray_targets`` (N, R) log patch-mm distances and ``ray_mask`` (N, R);
    - ``centres`` (K, 3) in-patch inner centres in patch voxels, ``centre_valid`` (K,).
    """

    def __init__(
        self,
        targets_dir: Path,
        *,
        spacing: Sequence[float],
        rays: int,
        patch_size: Sequence[int],
        cell_stride: Sequence[int],
        ray_samples: int,
        max_gt_instances: int,
        core_fraction: float,
        sigma_min_mm: float,
        sigma_fraction: float,
        min_ray_mm: float,
        max_ray_mm: float,
        cache_cases: int = 32,
        file_hashes: dict[str, str] | None = None,
    ) -> None:
        self.targets_dir = Path(targets_dir)
        # Verified sha256 per case: every (re)load from disk is checked against it,
        # so an evicted case reloaded later in training is never unverified bytes.
        self.file_hashes = None if file_hashes is None else dict(file_hashes)
        self.spacing = np.asarray(spacing, np.float64)
        self.geometry = star_geometry(rays)
        self.patch_size = tuple(int(v) for v in patch_size)
        self.stride = tuple(int(v) for v in cell_stride)
        if any(p % t for p, t in zip(self.patch_size, self.stride, strict=True)):
            raise ValueError("The patch size must be divisible by the STAR-C cell stride")
        self.cells = tuple(p // t for p, t in zip(self.patch_size, self.stride, strict=True))
        self.ray_samples = ray_samples
        self.max_gt_instances = max_gt_instances
        self.core_fraction = core_fraction
        self.sigma_min_mm = sigma_min_mm
        self.sigma_fraction = sigma_fraction
        self.min_ray_mm = min_ray_mm
        self.max_ray_mm = max_ray_mm
        self.cache_cases = cache_cases
        self._cache: OrderedDict[str, CaseTargets] = OrderedDict()
        self._cell_voxels = cell_centres(self.cells, self.stride)

    @property
    def capacity(self) -> int:
        return self.ray_samples + self.max_gt_instances

    def case(self, case_id: str) -> CaseTargets:
        if case_id in self._cache:
            self._cache.move_to_end(case_id)
            return self._cache[case_id]
        expected = None
        if self.file_hashes is not None:
            if case_id not in self.file_hashes:
                raise ValueError(f"STAR-C targets for {case_id} were not verified")
            expected = self.file_hashes[case_id]
        table = load_case_targets(self.targets_dir / f"{case_id}.npz", expected)
        if not np.allclose(table.spacing, self.spacing, rtol=0, atol=1e-6):
            raise ValueError(f"STAR-C targets for {case_id} use a different spacing")
        if table.rays_mm.shape[1] != self.geometry.rays:
            raise ValueError(f"STAR-C targets for {case_id} use a different ray count")
        self._cache[case_id] = table
        while len(self._cache) > self.cache_cases:
            self._cache.popitem(last=False)
        return table

    def empty(self) -> dict[str, np.ndarray]:
        rays = self.geometry.rays
        return {
            "heatmap": np.zeros((1, *self.cells), np.float32),
            "ray_positions": np.zeros((self.capacity, 3), np.float32),
            "ray_targets": np.zeros((self.capacity, rays), np.float32),
            "ray_mask": np.zeros((self.capacity, rays), bool),
            "centres": np.zeros((self.max_gt_instances, 3), np.float32),
            "centre_valid": np.zeros(self.max_gt_instances, bool),
        }

    def build(self, case_id: str, frame: PatchFrame, rng: np.random.Generator) -> dict[str, Any]:
        out = self.empty()
        table = self.case(case_id)
        if table.count == 0:
            return out
        physical = frame.physical(self.spacing)
        determinant = abs(float(np.linalg.det(physical)))
        if not determinant > 1e-9:
            raise ValueError("Degenerate augmentation frame")
        length_scale = determinant ** (1 / 3)
        patch = np.asarray(self.patch_size, np.float64)
        stride = np.asarray(self.stride, np.float64)

        # Centres and the Gaussian heatmap (patch mm).
        centres = frame.to_patch(table.centres)
        sigma = np.maximum(self.sigma_min_mm, self.sigma_fraction * table.equivalent_radius_mm)
        sigma = sigma / length_scale
        cells = np.asarray(self.cells)
        heat = np.zeros(self.cells)
        for k in range(table.count):
            # Gaussian over the cells within 4 sigma of the centre (patch mm).
            reach = 4 * sigma[k] / self.spacing
            low = np.maximum(np.floor((centres[k] - reach + 0.5) / stride).astype(int), 0)
            high = np.minimum(np.floor((centres[k] + reach + 0.5) / stride).astype(int) + 1, cells)
            if np.any(high <= low):
                continue
            axes = [
                (np.arange(a, b) * t + (t - 1) / 2 - c) * s
                for a, b, t, c, s in zip(low, high, stride, centres[k], self.spacing, strict=True)
            ]
            squared = sum(
                np.reshape(axis**2, [-1 if i == d else 1 for i in range(3)])
                for d, axis in enumerate(axes)
            )
            window = tuple(slice(a, b) for a, b in zip(low, high, strict=True))
            heat[window] = np.maximum(heat[window], np.exp(-squared / (2 * sigma[k] ** 2)))
        cell_index = np.floor((centres + 0.5) / stride).astype(np.int64)
        in_patch = np.all((centres >= -0.5) & (centres < patch - 0.5), axis=1)
        for j in np.flatnonzero(in_patch):
            heat[tuple(np.clip(cell_index[j], 0, cells - 1))] = 1.0
        out["heatmap"][0] = heat.astype(np.float32)

        # Ground-truth centres in the patch, largest first.
        order = np.flatnonzero(in_patch)
        order = order[np.argsort(-table.volume_mm3[order], kind="stable")]
        kept = order[: self.max_gt_instances]
        out["centres"][: len(kept)] = centres[kept]
        out["centre_valid"][: len(kept)] = True

        # Ray samples: in-patch centres, then core cells with an equal share per component.
        origins: list[np.ndarray] = [table.centres[kept]]
        components: list[np.ndarray] = [kept + 1]
        positions: list[np.ndarray] = [voxel_to_cell(centres[kept], self.stride)]
        if self.ray_samples:
            volume = frame.to_volume(self._cell_voxels)
            local = np.rint(volume - table.crop_origin).astype(np.int64)
            shape = np.asarray(table.instances.shape)
            valid = np.all((local >= 0) & (local < shape), axis=1)
            label = np.zeros(len(local), np.int64)
            depth = np.zeros(len(local))
            clipped = np.clip(local[valid], 0, shape - 1)
            label[valid] = table.instances[clipped[:, 0], clipped[:, 1], clipped[:, 2]]
            depth[valid] = table.edt_mm[clipped[:, 0], clipped[:, 1], clipped[:, 2]]
            core = label > 0
            core[core] &= depth[core] >= self.core_fraction * table.max_edt_mm[label[core] - 1]
            present = np.unique(label[core])
            if len(present):
                share = math.ceil(self.ray_samples / len(present))
                chosen = []
                for component in present:
                    candidates = np.flatnonzero(core & (label == component))
                    take = min(share, len(candidates))
                    chosen.append(rng.choice(candidates, size=take, replace=False))
                picks = np.concatenate(chosen)
                if len(picks) > self.ray_samples:
                    picks = rng.choice(picks, size=self.ray_samples, replace=False)
                origins.append(volume[picks])
                components.append(label[picks])
                positions.append(voxel_to_cell(self._cell_voxels[picks], self.stride))
        origin = np.concatenate(origins)
        component = np.concatenate(components)
        position = np.concatenate(positions)
        if len(origin) == 0:
            return out

        # Patch rays u' map to volume mm directions A u'; the target is D / |A u'|.
        mapped = self.geometry.directions @ physical.T
        stretch = np.linalg.norm(mapped, axis=1)
        unit = mapped / stretch[:, None]
        targets = np.zeros((len(origin), self.geometry.rays))
        exited = np.zeros((len(origin), self.geometry.rays), bool)
        step = 0.25 * float(self.spacing.min())
        for value in np.unique(component):
            rows = np.flatnonzero(component == value)
            reach_mm = float(table.bbox_diagonal_mm[value - 1] + self.spacing.max())
            distance, hit = march_exit_mm(
                table.instances,
                int(value),
                origin[rows] - table.crop_origin,
                unit,
                self.spacing,
                step_mm=max(step, reach_mm / 512),
                max_mm=reach_mm,
            )
            targets[rows] = distance / stretch[None]
            exited[rows] = hit
        mask = exited & (targets <= self.max_ray_mm)
        count = len(origin)
        out["ray_positions"][:count] = position
        out["ray_targets"][:count] = np.log(np.maximum(targets, self.min_ray_mm))
        out["ray_mask"][:count] = mask
        return out


def collate_star_targets(samples: Sequence[dict[str, Any]]) -> dict[str, torch.Tensor]:
    return {key: torch.from_numpy(np.stack([s[key] for s in samples])) for key in samples[0]}


# ---------------------------------------------------------------------------
# Torch operators
# ---------------------------------------------------------------------------


@dataclass
class StarInstances:
    """Instances to render for a batch, in the current input's full-resolution voxels.

    ``log_radii`` None means "sample the predicted ray map at each centre".
    ``transforms`` (B, K, 3, 3) render a star given in another frame: the
    direction ``u`` is looked up as ``T u / |T u|`` and the radius divided by
    ``|T u|`` (mirrored test-time copies use a +-1 diagonal).
    """

    centres: torch.Tensor
    valid: torch.Tensor
    scores: torch.Tensor | None = None
    log_radii: torch.Tensor | None = None
    transforms: torch.Tensor | None = None
    extras: dict[str, Any] = field(default_factory=dict)


def _pads(window: Sequence[slice], shape: Sequence[int]) -> list[int]:
    """``F.pad`` widths (last axis first) that place ``window`` inside ``shape``."""
    pads: list[int] = []
    for part, size in zip(reversed(list(window)), reversed(list(shape)), strict=True):
        pads += [part.start, size - part.stop]
    return pads


class StarRenderer(nn.Module):
    """Differentiable soft star polyhedra in physical space (buffers are not persistent)."""

    directions: torch.Tensor
    facets: torch.Tensor
    inverse: torch.Tensor
    lut: torch.Tensor

    def __init__(self, rays: int, spacing: Sequence[float], lut_shape: Sequence[int]) -> None:
        super().__init__()
        geometry = star_geometry(rays, (int(lut_shape[0]), int(lut_shape[1])))
        self.rays = rays
        self.spacing = tuple(float(v) for v in spacing)
        self.lut_shape = (int(lut_shape[0]), int(lut_shape[1]))
        self.register_buffer(
            "directions", torch.tensor(geometry.directions, dtype=torch.float32), persistent=False
        )
        self.register_buffer(
            "facets", torch.tensor(geometry.facets, dtype=torch.long), persistent=False
        )
        self.register_buffer(
            "inverse", torch.tensor(geometry.inverse, dtype=torch.float32), persistent=False
        )
        self.register_buffer("lut", torch.tensor(geometry.lut, dtype=torch.long), persistent=False)

    def facet_weights(self, unit: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        """Facet index (N,) and barycentric cone weights (N, 3) of unit directions (N, 3).

        Evaluated in chunks of ``RADIUS_CHUNK`` directions: the candidate cone
        temporary is (N, 6, 3, 3), about 216 B per voxel in fp32, and a star box
        can span a whole patch.
        """
        facets, weights = [], []
        with torch.no_grad():
            for part in unit.split(RADIUS_CHUNK):
                polar = torch.acos(part[:, 0].clamp(-1.0, 1.0))
                azimuth = torch.atan2(part[:, 1], part[:, 2])
                rows = (polar / math.pi * self.lut_shape[0]).long().clamp(0, self.lut_shape[0] - 1)
                cols = ((azimuth + math.pi) / (2 * math.pi) * self.lut_shape[1]).long()
                candidates = self.lut[rows, cols % self.lut_shape[1]]
                cone = torch.einsum("nkij,nj->nki", self.inverse.to(part.dtype)[candidates], part)
                best = cone.amin(2).argmax(1, keepdim=True)
                facets.append(candidates.gather(1, best)[:, 0])
                weights.append(cone.gather(1, best[..., None].expand(-1, 1, 3))[:, 0].clamp_min(0))
        if not facets:
            return (
                torch.zeros(0, dtype=torch.long, device=unit.device),
                unit.new_zeros((0, 3)),
            )
        return torch.cat(facets), torch.cat(weights)

    def radius(self, radii: torch.Tensor, unit: torch.Tensor) -> torch.Tensor:
        """Polyhedron radius of one star (R,) along unit directions (N, 3)."""
        facet, weights = self.facet_weights(unit)
        corners = radii[self.facets[facet]].clamp_min(_EPS)
        return 1.0 / (weights / corners).sum(1).clamp_min(_EPS)

    def render(
        self,
        shape: Sequence[int],
        centres: torch.Tensor,
        radii: torch.Tensor,
        scores: torch.Tensor,
        tau: torch.Tensor,
        *,
        margin_mm: float,
        prior_scale: float,
        transforms: torch.Tensor | None = None,
    ) -> tuple[torch.Tensor, torch.Tensor]:
        """Prior ``P`` and box mask ``B``, both (1, *shape), for one sample's stars (fp32; fp64 radii render in fp64).

        ``P = max_k s_k * c * tanh(o_k / c)`` with ``o_k = (R_k(u) - rho) / tau``
        over the boxes ``centre +- (max r + margin)``; outside every box P = 0.
        Autocast is disabled inside, so the geometry stays in fp32 (or fp64)
        under mixed-precision training and inference.
        """
        with torch.autocast(device_type=radii.device.type, enabled=False):
            return self._render(
                shape,
                centres,
                radii,
                scores,
                tau,
                margin_mm=margin_mm,
                prior_scale=prior_scale,
                transforms=transforms,
            )

    def _render(
        self,
        shape: Sequence[int],
        centres: torch.Tensor,
        radii: torch.Tensor,
        scores: torch.Tensor,
        tau: torch.Tensor,
        *,
        margin_mm: float,
        prior_scale: float,
        transforms: torch.Tensor | None,
    ) -> tuple[torch.Tensor, torch.Tensor]:
        device = radii.device
        dtype = torch.float64 if radii.dtype == torch.float64 else torch.float32
        spacing = torch.tensor(self.spacing, device=device, dtype=dtype)
        size = torch.tensor(list(shape), device=device)
        boxes = []
        for k in range(len(centres)):
            longest = radii[k].detach().max()
            if transforms is not None:
                # |T u| >= sigma_min(T), so the star reaches at most max r / sigma_min.
                longest = longest * torch.linalg.matrix_norm(
                    torch.linalg.inv(transforms[k].detach().to(dtype)), ord=2
                )
            reach = (longest + margin_mm) / spacing
            low = torch.maximum(torch.floor(centres[k] - reach), torch.zeros_like(size))
            high = torch.minimum(torch.ceil(centres[k] + reach) + 1, size)
            low_i, high_i = low.long().tolist(), high.long().tolist()
            if all(a < b for a, b in zip(low_i, high_i, strict=True)):
                boxes.append((k, low_i, high_i))
        if not boxes:
            empty = torch.zeros((1, *shape), device=device, dtype=dtype)
            return empty, empty.clone()
        union_low = [min(box[1][d] for box in boxes) for d in range(3)]
        union_high = [max(box[2][d] for box in boxes) for d in range(3)]
        extent = [b - a for a, b in zip(union_low, union_high, strict=True)]
        region = torch.full(extent, -math.inf, device=device, dtype=dtype)
        inside = torch.zeros(extent, device=device, dtype=torch.bool)
        for k, low_i, high_i in boxes:
            axes = [
                torch.arange(a, b, device=device, dtype=dtype)
                for a, b in zip(low_i, high_i, strict=True)
            ]
            grid = torch.stack(torch.meshgrid(*axes, indexing="ij"), -1)
            offset = (grid - centres[k].detach().to(dtype)) * spacing
            rho = offset.norm(dim=-1)
            unit = offset / rho.clamp_min(_EPS)[..., None]
            unit = torch.where(
                rho[..., None] < _EPS, torch.tensor([1.0, 0, 0], device=device, dtype=dtype), unit
            )
            flat = unit.reshape(-1, 3)
            if transforms is not None:
                mapped = flat @ transforms[k].to(dtype).T
                stretch = mapped.norm(dim=1).clamp_min(_EPS)
                star = self.radius(radii[k].to(dtype), mapped / stretch[:, None]) / stretch
            else:
                star = self.radius(radii[k].to(dtype), flat)
            logit = (star.reshape(rho.shape) - rho) / tau.to(dtype)
            value = scores[k].to(dtype) * prior_scale * torch.tanh(logit / prior_scale)
            local = tuple(
                slice(a - u, b - u) for a, b, u in zip(low_i, high_i, union_low, strict=True)
            )
            region = torch.maximum(region, F.pad(value, _pads(local, extent), value=-math.inf))
            inside[local] = True
        region = torch.where(inside, region, torch.zeros_like(region))
        window = tuple(slice(a, b) for a, b in zip(union_low, union_high, strict=True))
        pads = _pads(window, list(shape))
        return F.pad(region, pads)[None], F.pad(inside.float(), pads)[None]


def sample_cells(maps: torch.Tensor, positions: torch.Tensor) -> torch.Tensor:
    """Trilinear sample of (B, C, d, h, w) at continuous cell coordinates (B, N, 3) -> (B, N, C)."""
    sizes = torch.tensor(maps.shape[2:], device=maps.device, dtype=torch.float32)
    scale = torch.where(sizes > 1, 2.0 / (sizes - 1).clamp_min(1), torch.zeros_like(sizes))
    normalised = positions.float() * scale - torch.where(sizes > 1, 1.0, 0.0)
    grid = normalised.flip(-1)[:, :, None, None, :]
    sampled = F.grid_sample(
        maps.float(), grid, mode="bilinear", padding_mode="border", align_corners=True
    )
    return sampled[:, :, :, 0, 0].transpose(1, 2)


def detect_peaks(
    heat_logits: torch.Tensor, threshold: float, count: int
) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
    """Heatmap NMS: top ``count`` 3x3x3 maxima >= ``threshold`` with soft-argmax refinement.

    Returns continuous cell coordinates (B, K, 3), scores (B, K) and validity
    (B, K); everything is detached.
    """
    with torch.no_grad():
        heat = torch.sigmoid(heat_logits.float())
        peaks = (heat == F.max_pool3d(heat, 3, stride=1, padding=1)) & (heat >= threshold)
        flat = torch.where(peaks, heat, torch.zeros_like(heat)).flatten(1)
        k = min(count, flat.shape[1])
        scores, index = flat.topk(k, dim=1)
        valid = scores >= max(threshold, _EPS)
        _, h, w = heat.shape[2:]
        cell = torch.stack([index // (h * w), (index // w) % h, index % w], -1)
        padded = F.pad(heat[:, 0], (1, 1, 1, 1, 1, 1))
        total = torch.zeros_like(scores)
        moment = torch.zeros((*scores.shape, 3), device=heat.device)
        batch = torch.arange(heat.shape[0], device=heat.device)[:, None].expand_as(index)
        for dz in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    value = padded[
                        batch, cell[..., 0] + 1 + dz, cell[..., 1] + 1 + dy, cell[..., 2] + 1 + dx
                    ]
                    total += value
                    moment += value[..., None] * torch.tensor([dz, dy, dx], device=heat.device)
        refined = cell.float() + moment / total.clamp_min(_EPS)[..., None]
        if count > k:
            pad = count - k
            refined = F.pad(refined, (0, 0, 0, pad))
            scores = F.pad(scores, (0, pad))
            valid = F.pad(valid, (0, pad))
    return refined, scores, valid


def centre_focal_loss(
    logits: torch.Tensor, target: torch.Tensor, *, alpha: float = 2.0, beta: float = 4.0
) -> torch.Tensor:
    """CenterNet penalty-reduced focal loss, normalised by the number of positive cells."""
    logits = logits.float()
    target = target.float()
    positive = target >= 1.0
    probability = torch.sigmoid(logits)
    positive_loss = -((1 - probability) ** alpha * F.logsigmoid(logits))
    negative_loss = -((1 - target) ** beta * probability**alpha * F.logsigmoid(-logits))
    loss = torch.where(positive, positive_loss, negative_loss).sum()
    return loss / positive.sum().clamp_min(1)


def ray_l1_loss(
    log_radii: torch.Tensor, positions: torch.Tensor, targets: torch.Tensor, mask: torch.Tensor
) -> torch.Tensor:
    """Mean L1 of predicted log-distances at sample positions over valid rays."""
    predicted = sample_cells(log_radii, positions)
    weight = mask.float()
    return ((predicted - targets.float()).abs() * weight).sum() / weight.sum().clamp_min(1)


def _head(
    in_channels: int,
    hidden: int,
    out_channels: int,
    norm_op: type[nn.Module],
    norm_kwargs: dict[str, Any],
    nonlin: type[nn.Module],
    nonlin_kwargs: dict[str, Any],
) -> nn.Sequential:
    return nn.Sequential(
        nn.Conv3d(in_channels, hidden, 3, padding=1, bias=True),
        norm_op(hidden, **norm_kwargs),
        nonlin(**nonlin_kwargs),
        nn.Conv3d(hidden, out_channels, 1, bias=True),
    )


class StarCompletion(nn.Module):
    """Centre and ray heads, star proposals, rendering and gated fusion into the logits.

    ``forward(f_level, f_full, z0, instances)`` returns the fused full-resolution
    logits and an auxiliary dict (``heat_logits``, ``log_radii``, the rendered
    instances). With the fusion weights at zero the logits equal ``z0``.
    """

    def __init__(
        self,
        level_channels: int,
        full_channels: int,
        num_classes: int,
        *,
        spacing: Sequence[float],
        stride: Sequence[int],
        rays: int,
        fusion_channels: Sequence[int],
        fusion: str,
        max_instances: int,
        centre_threshold: float,
        box_margin_mm: float,
        min_ray_mm: float,
        max_ray_mm: float,
        tau_init_mm: float,
        tau_min_mm: float,
        tau_max_mm: float,
        gate_bias: float,
        prior_scale: float,
        centre_hidden: int,
        ray_hidden: int,
        gate_hidden: int,
        ray_init_mm: float,
        centre_prior: float,
        lut_shape: Sequence[int],
        norm_op: type[nn.Module] = nn.InstanceNorm3d,
        norm_kwargs: dict[str, Any] | None = None,
        nonlin: type[nn.Module] = nn.LeakyReLU,
        nonlin_kwargs: dict[str, Any] | None = None,
    ) -> None:
        super().__init__()
        if fusion not in FUSION_MODES:
            raise ValueError(f"fusion must be one of {FUSION_MODES}")
        if any(type(c) is not int or not 0 <= c < num_classes for c in fusion_channels):
            raise ValueError("STAR-C fusion channels must index output channels")
        if len(set(fusion_channels)) != len(fusion_channels) or not fusion_channels:
            raise ValueError("STAR-C fusion channels must be distinct and nonempty")
        norm_kwargs = {"eps": 1e-5, "affine": True} if norm_kwargs is None else dict(norm_kwargs)
        nonlin_kwargs = {"inplace": True} if nonlin_kwargs is None else dict(nonlin_kwargs)
        self.spacing = tuple(float(v) for v in spacing)
        self.stride = tuple(int(v) for v in stride)
        self.rays = rays
        self.fusion_channels = list(fusion_channels)
        self.fusion = fusion
        self.max_instances = max_instances
        self.centre_threshold = float(centre_threshold)
        self.box_margin_mm = float(box_margin_mm)
        self.min_ray_mm = float(min_ray_mm)
        self.max_ray_mm = float(max_ray_mm)
        self.tau_init_mm = float(tau_init_mm)
        self.tau_min_mm = float(tau_min_mm)
        self.tau_max_mm = float(tau_max_mm)
        self.gate_bias = float(gate_bias)
        self.prior_scale = float(prior_scale)
        self.ray_init_mm = float(ray_init_mm)
        self.centre_prior = float(centre_prior)
        self.num_classes = num_classes
        self.centre_head = _head(
            level_channels, centre_hidden, 1, norm_op, norm_kwargs, nonlin, nonlin_kwargs
        )
        self.ray_head = _head(
            level_channels, ray_hidden, rays, norm_op, norm_kwargs, nonlin, nonlin_kwargs
        )
        self.gate = nn.Sequential(
            nn.Conv3d(full_channels + 2 + num_classes, gate_hidden, (1, 3, 3), padding=(0, 1, 1)),
            nonlin(**nonlin_kwargs),
            nn.Conv3d(gate_hidden, 1, 1),
        )
        self.fusion_weight = nn.Parameter(torch.zeros(len(self.fusion_channels)))
        self.tau_logit = nn.Parameter(torch.zeros(()))
        self.renderer = StarRenderer(rays, spacing, lut_shape)
        self.reset_star_parameters()

    def reset_star_parameters(self) -> None:
        """The STAR-C initial state; run after the host network's He initialisation."""
        with torch.no_grad():
            self.fusion_weight.zero_()
            fraction = (self.tau_init_mm - self.tau_min_mm) / (self.tau_max_mm - self.tau_min_mm)
            self.tau_logit.fill_(math.log(fraction / (1 - fraction)))
            last_gate = self.gate[-1]
            assert isinstance(last_gate, nn.Conv3d) and last_gate.bias is not None
            last_gate.weight.zero_()
            last_gate.bias.fill_(self.gate_bias)
            last_centre = self.centre_head[-1]
            assert isinstance(last_centre, nn.Conv3d) and last_centre.bias is not None
            # A flat heatmap at the prior: no spurious peaks before the focal loss trains it.
            last_centre.weight.zero_()
            last_centre.bias.fill_(math.log(self.centre_prior / (1 - self.centre_prior)))
            last_ray = self.ray_head[-1]
            assert isinstance(last_ray, nn.Conv3d) and last_ray.bias is not None
            # Every ray starts at ray_init_mm: a sphere, not a random spiky star.
            last_ray.weight.zero_()
            last_ray.bias.fill_(math.log(self.ray_init_mm))

    def tau(self) -> torch.Tensor:
        span = self.tau_max_mm - self.tau_min_mm
        return self.tau_min_mm + span * torch.sigmoid(self.tau_logit.float())

    def cell_to_voxel(self, cells: torch.Tensor) -> torch.Tensor:
        stride = torch.tensor(self.stride, device=cells.device, dtype=torch.float32)
        return cells.float() * stride + (stride - 1) / 2

    def voxel_to_cell(self, voxels: torch.Tensor) -> torch.Tensor:
        stride = torch.tensor(self.stride, device=voxels.device, dtype=torch.float32)
        return (voxels.float() - (stride - 1) / 2) / stride

    def propose(self, heat_logits: torch.Tensor, log_radii: torch.Tensor) -> StarInstances:
        cells, scores, valid = detect_peaks(heat_logits, self.centre_threshold, self.max_instances)
        return StarInstances(
            centres=self.cell_to_voxel(cells),
            valid=valid,
            scores=scores,
            log_radii=sample_cells(log_radii, cells),
        )

    def forward(
        self,
        level_features: torch.Tensor,
        full_features: torch.Tensor,
        logits: torch.Tensor,
        instances: StarInstances | None = None,
    ) -> tuple[torch.Tensor, dict[str, Any]]:
        heat_logits = self.centre_head(level_features)
        log_radii = self.ray_head(level_features)
        if instances is None:
            instances = self.propose(heat_logits, log_radii)
        else:
            instances = replace(
                instances,
                log_radii=sample_cells(log_radii, self.voxel_to_cell(instances.centres))
                if instances.log_radii is None
                else instances.log_radii,
                scores=instances.valid.float() if instances.scores is None else instances.scores,
            )
        aux: dict[str, Any] = {
            "heat_logits": heat_logits,
            "log_radii": log_radii,
            "instances": instances,
        }
        if self.fusion == "aux_only":
            return logits, aux
        shape = tuple(logits.shape[2:])
        priors, masks = [], []
        tau = self.tau()
        assert instances.log_radii is not None and instances.scores is not None
        for b in range(logits.shape[0]):
            keep = instances.valid[b].nonzero().flatten()
            radii = torch.exp(
                instances.log_radii[b, keep]
                .float()
                .clamp(math.log(self.min_ray_mm), math.log(self.max_ray_mm))
            )
            transforms = None if instances.transforms is None else instances.transforms[b, keep]
            prior, mask = self.renderer.render(
                shape,
                instances.centres[b, keep].detach().float(),
                radii,
                instances.scores[b, keep].detach().float(),
                tau,
                margin_mm=self.box_margin_mm,
                prior_scale=self.prior_scale,
                transforms=transforms,
            )
            priors.append(prior)
            masks.append(mask)
        prior = torch.stack(priors)
        mask = torch.stack(masks)
        gate_input = torch.cat(
            [
                full_features,
                prior.to(full_features.dtype),
                mask.to(full_features.dtype),
                logits.detach(),
            ],
            1,
        )
        gate = torch.sigmoid(self.gate(gate_input).float())
        delta = gate * prior
        aux["prior"] = prior.detach()
        aux["gate"] = gate.detach()
        pieces = []
        for channel in range(logits.shape[1]):
            piece = logits[:, channel : channel + 1]
            if channel in self.fusion_channels:
                weight = self.fusion_weight[self.fusion_channels.index(channel)]
                piece = piece + (weight * delta).to(logits.dtype)
            pieces.append(piece)
        return torch.cat(pieces, 1), aux


# ---------------------------------------------------------------------------
# Case-level inference
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CaseDetection:
    centre: np.ndarray
    log_radii: np.ndarray
    score: float
    weight: float


def merge_tile_detections(
    detections: Sequence[CaseDetection],
    geometry: StarGeometry,
    spacing: Sequence[float],
    *,
    threshold: float,
    nms_radius_mm: float,
    max_instances: int,
    min_ray_mm: float,
    max_ray_mm: float,
) -> list[CaseDetection]:
    """Case-level NMS of per-tile peaks (case voxels).

    Sorted by ``score * weight`` (``weight`` is the tile's Gaussian importance
    at the peak, 1 at the tile centre), a detection is dropped when its centre
    lies inside the star of a kept one or within ``nms_radius_mm`` of it.
    """
    spacing_array = np.asarray(spacing, np.float64)
    ranked = sorted(
        (d for d in detections if d.score >= threshold),
        key=lambda d: (-(d.score * d.weight), -d.score, tuple(d.centre)),
    )
    kept: list[CaseDetection] = []
    for candidate in ranked:
        suppressed = False
        for other in kept:
            offset = (candidate.centre - other.centre) * spacing_array
            rho = float(np.linalg.norm(offset))
            if rho <= nms_radius_mm:
                suppressed = True
                break
            radii = np.exp(np.clip(other.log_radii, math.log(min_ray_mm), math.log(max_ray_mm)))
            if rho <= float(geometry.radius(radii, (offset / rho)[None])[0]):
                suppressed = True
                break
        if not suppressed:
            kept.append(candidate)
            if len(kept) == max_instances:
                break
    return kept
