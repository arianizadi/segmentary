"""Opt-in nnU-Net region-based training labels that decode to the native label map.

nnU-Net trains one sigmoid head per region (a set of label values) and exports
``segmentation[p_i > 0.5] = regions_class_order[i]`` in region order. A region
recipe is accepted only if that decode maps every label's own region membership
back to the label itself, so predicted label maps, evaluation and every metric
keep exactly the label-mode definition (pancreas = {1, 2}, mass = {2}).

Reference preprocessing reuse (nnU-Net 2.8.1, ``DefaultPreprocessor.run_case_npy``
and ``nnUNetDataLoader.get_bbox``): the stored image and segmentation arrays do
not depend on the label mode. Labels are converted to regions on the fly by the
training transforms, and ``modify_seg_fn`` is the identity. The per-case
``class_locations`` in the ``.pkl`` do depend on it: label mode samples keys
``1`` and ``2`` (non-mass pancreas voxels, mass voxels); region mode samples
``(1, 2)`` and ``(2,)`` (all pancreas voxels, mass voxels). The loader picks a
nonempty key uniformly and never checks the keys, so reusing label-mode pickles
would silently train with a different foreground oversampling distribution.
The workspace therefore keeps the reference arrays byte for byte and recomputes
only ``class_locations`` with nnU-Net's own sampler on the copied segmentation,
which is the array that sampler read during preprocessing. Before rewriting a
case, the label-mode keys are recomputed the same way and must equal the
reference pickle exactly, which proves the copy reproduces the original sampling.
"""

from __future__ import annotations

import copy
import os
import uuid
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np

OUTPUT_MODES = ("labels", "regions")
# Task07 pancreas/mass: the pancreas region contains the mass region. Regions are an
# ordered list of [name, labels] pairs: nnU-Net orders its region heads by the order
# of dataset.json ``labels``, and every Segmentary record is written with sorted keys,
# so a mapping would silently reorder the heads against ``regions_class_order``.
TASK07_REGIONS: list[list[Any]] = [["pancreas", [1, 2]], ["mass", [2]]]
TASK07_REGIONS_CLASS_ORDER = [1, 2]
Regions = Sequence[Sequence[Any]] | Mapping[str, Any]


def _labels(value: Any, name: str) -> list[int]:
    if (
        not isinstance(value, list)
        or not value
        or any(type(item) is not int or item < 1 for item in value)
        or len(set(value)) != len(value)
    ):
        raise ValueError(f"Region {name!r} must be a nonempty list of distinct foreground labels")
    return sorted(value)


def regions_ontology(regions: Regions) -> dict[str, int]:
    """The smallest ontology a recipe can describe: background plus every label it uses.

    A configuration is checked against this before any manifest is read; the
    manifest's own ontology is checked again when a dataset is prepared.
    """
    used: set[int] = set()
    for name, value in _pairs(regions):
        if not isinstance(value, (list, tuple)):
            raise ValueError("Each region needs a list of labels")
        used.update(_labels(list(value), name))
    return {"background": 0, **{f"label_{value}": value for value in sorted(used)}}


def decode_label(membership: Sequence[bool], regions_class_order: Sequence[int]) -> int:
    """nnU-Net's region decode for one voxel: the last region it belongs to wins."""
    label = 0
    for inside, value in zip(membership, regions_class_order, strict=True):
        if inside:
            label = value
    return label


def _pairs(regions: Any) -> list[tuple[Any, Any]]:
    if isinstance(regions, Mapping):
        return list(regions.items())
    if not isinstance(regions, (list, tuple)) or any(
        not isinstance(pair, (list, tuple)) or len(pair) != 2 for pair in regions
    ):
        raise ValueError("label_regions must be an ordered list of [name, labels] pairs")
    return [(pair[0], pair[1]) for pair in regions]


def validate_regions(
    ontology: Mapping[str, int],
    regions: Regions | None,
    regions_class_order: Sequence[int] | None,
) -> tuple[list[list[Any]], list[int]]:
    """Resolve a region recipe; refuse one that cannot reproduce the native label map.

    Regions are ``[[name, [labels]], ...]`` in output-head order (an ordered
    mapping is accepted and converted). The decode must be
    lossless: for each ontology label (background included), applying nnU-Net's
    ``regions_class_order`` decode to that label's region memberships must give
    the label back. This is exactly the condition under which a perfect region
    prediction decodes to the reference label map.
    """
    if regions is None:
        regions = copy.deepcopy(TASK07_REGIONS)
    if regions_class_order is None:
        regions_class_order = list(TASK07_REGIONS_CLASS_ORDER)
    pairs = _pairs(regions)
    if not pairs:
        raise ValueError("label_regions must be a nonempty ordered list of regions")
    if not isinstance(regions_class_order, (list, tuple)):
        raise ValueError("regions_class_order must be a list of label values")
    names = [name for name, _ in pairs]
    if any(not isinstance(name, str) or not name.isidentifier() for name in names):
        raise ValueError("Region names must be identifiers")
    if len(set(names)) != len(names):
        raise ValueError("Region names must be distinct")
    if "background" in names or "ignore" in names:
        raise ValueError("Region names 'background' and 'ignore' are reserved by nnU-Net")
    if any(not isinstance(value, (list, tuple)) for _, value in pairs):
        raise ValueError("Each region needs a list of labels")
    resolved = {name: _labels(list(value), name) for name, value in pairs}
    if len({tuple(value) for value in resolved.values()}) != len(resolved):
        raise ValueError("Regions must be distinct label sets")
    order = list(regions_class_order)
    foreground = {value for name, value in ontology.items() if name != "background"}
    if ontology.get("background") != 0 or 0 in foreground:
        raise ValueError("The ontology must map background to 0")
    if len(order) != len(resolved) or any(type(v) is not int or v not in foreground for v in order):
        raise ValueError("regions_class_order needs one foreground label value per region")
    used = set().union(*(set(value) for value in resolved.values()))
    if not used <= foreground:
        raise ValueError(f"Regions use labels outside the ontology: {sorted(used - foreground)}")
    for label in [0, *sorted(foreground)]:
        membership = [label in value for value in resolved.values()]
        if decode_label(membership, order) != label:
            raise ValueError(
                f"Region decode does not reproduce label {label}; the native label map, and so "
                "every metric, would change"
            )
    return [[name, value] for name, value in resolved.items()], order


def region_dataset_json(
    ontology: Mapping[str, int],
    regions: Regions,
    regions_class_order: Sequence[int],
    base: Mapping[str, Any],
) -> dict[str, Any]:
    """The nnU-Net ``dataset.json`` for region training, from the label-mode one.

    The ``labels`` entries are in head order; write it without sorting keys.
    """
    resolved, order = validate_regions(ontology, regions, regions_class_order)
    labels: dict[str, Any] = {"background": 0}
    labels.update({name: list(value) for name, value in resolved})
    return {**copy.deepcopy(dict(base)), "labels": labels, "regions_class_order": order}


def same_dataset_json(actual: Mapping[str, Any], expected: Mapping[str, Any]) -> bool:
    """Equal content; for a region dataset also equal ``labels`` order (the head order).

    Label-mode heads are the sorted label values, so their key order is irrelevant.
    """
    if dict(actual) != dict(expected):
        return False
    if "regions_class_order" not in expected:
        return True
    return list(actual.get("labels", {})) == list(expected.get("labels", {}))


def encode_regions(labels: np.ndarray, regions: Regions) -> np.ndarray:
    """Boolean region masks, head-first: ``out[i] = isin(labels, region_i)``."""
    return np.stack([np.isin(labels, list(value)) for _, value in _pairs(regions)])


def decode_regions(
    probabilities: np.ndarray, regions_class_order: Sequence[int], threshold: float = 0.5
) -> np.ndarray:
    """Native label map from region probabilities, as nnU-Net's LabelManager exports it."""
    if probabilities.shape[0] != len(regions_class_order):
        raise ValueError("Need one probability map per region")
    segmentation = np.zeros(probabilities.shape[1:], dtype=np.uint8)
    for index, value in enumerate(regions_class_order):
        segmentation[probabilities[index] > threshold] = value
    return segmentation


def _class_key(key: Any) -> Any:
    return tuple(int(item) for item in key) if isinstance(key, (tuple, list)) else int(key)


def _same_locations(first: Mapping[Any, Any], second: Mapping[Any, Any]) -> bool:
    if {_class_key(k) for k in first} != {_class_key(k) for k in second}:
        return False
    lookup = {_class_key(k): v for k, v in second.items()}
    return all(
        np.array_equal(np.asarray(value), np.asarray(lookup[_class_key(key)]))
        for key, value in first.items()
    )


def _regenerate_case(arguments: tuple[str, str, list, list]) -> dict[str, Any]:
    """Worker: verify label-mode locations, then write region-mode locations (one case)."""
    import blosc2
    from batchgenerators.utilities.file_and_folder_operations import load_pickle, write_pickle
    from nnunetv2.preprocessing.preprocessors.default_preprocessor import DefaultPreprocessor

    folder, case, label_keys, region_keys = arguments
    pickle_path = Path(folder) / f"{case}.pkl"
    properties = load_pickle(str(pickle_path))
    seg = np.asarray(blosc2.open(urlpath=str(Path(folder) / f"{case}_seg.b2nd"), mode="r")[:])
    sample = DefaultPreprocessor._sample_foreground_locations
    if not _same_locations(sample(seg, label_keys), properties["class_locations"]):
        raise ValueError(f"{case}: copied segmentation does not reproduce the reference sampling")
    properties["class_locations"] = sample(seg, region_keys)
    temporary = pickle_path.with_name(f".{pickle_path.name}.{uuid.uuid4().hex}.tmp")
    try:
        write_pickle(properties, str(temporary))
        os.replace(temporary, pickle_path)
    finally:
        temporary.unlink(missing_ok=True)
    return {
        "case": case,
        "region_keys": [list(_class_key(key)) for key in properties["class_locations"]],
        "region_samples": [len(value) for value in properties["class_locations"].values()],
    }


def regenerate_class_locations(
    folder: Path,
    identifiers: Sequence[str],
    *,
    label_dataset_json: dict[str, Any],
    region_dataset_json: dict[str, Any],
    plans: dict[str, Any],
    workers: int,
) -> dict[str, Any]:
    """Rewrite each copied ``.pkl``'s ``class_locations`` for region training (backend only)."""
    from multiprocessing import get_context

    from nnunetv2.utilities.plans_handling.plans_handler import PlansManager

    manager = PlansManager(plans)
    labels = manager.get_label_manager(label_dataset_json)
    regions = manager.get_label_manager(region_dataset_json)
    if labels.has_regions or not regions.has_regions or labels.has_ignore_label:
        raise ValueError("Expected a label-mode reference and a region-mode destination")
    label_keys = [int(value) for value in labels.foreground_labels]
    region_keys = [tuple(int(v) for v in region) for region in regions.foreground_regions]
    arguments = [(str(folder), case, label_keys, region_keys) for case in sorted(identifiers)]
    with get_context("spawn").Pool(max(1, workers)) as pool:
        cases = pool.map(_regenerate_case, arguments, chunksize=1)
    return {
        "action": "regenerate_region_class_locations",
        "sampler": "nnunetv2 DefaultPreprocessor._sample_foreground_locations (seed 1234)",
        "label_keys": label_keys,
        "region_keys": [list(key) for key in region_keys],
        "label_mode_reference_reproduced": len(cases),
        "cases": cases,
        "arrays_rewritten": False,
    }
