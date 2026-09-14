"""Explicit patch-center distributions over uniform volume or anatomical classes.

Missing classes lose their weight before normalization. If no weighted branch
remains, use the already sampled uniform-volume center. Background centers are
uniform over class-0 voxels, which is different from uniform-volume sampling.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from .torch_config import TorchConfig


def _coordinates(data: dict) -> dict[int, np.ndarray]:
    coordinates = data.get("foreground_coordinates")
    if coordinates is None:
        # Non-shared NPZ and small verification inputs have no coordinate cache.
        # Build only foreground coordinates once per loader-owned case dictionary.
        coordinates = data.get("_center_coordinates")
        if coordinates is None:
            coordinates = {c: np.argwhere(data["label"] == c) for c in (1, 2)}
            data["_center_coordinates"] = coordinates
    return coordinates


def _background_center(
    data: dict, coordinates: dict[int, np.ndarray], count: int, rng: np.random.Generator
) -> list[int]:
    label = data["label"]
    # CT is predominantly background. Exact rejection sampling normally accepts
    # immediately, without a label-volume scan or a huge background-coordinate map.
    for _ in range(32):
        flat = int(rng.integers(label.size))
        if label.flat[flat] == 0:
            return [int(x) for x in np.unravel_index(flat, label.shape)]
    # Bounded fallback for synthetic/nearly all-foreground volumes: select the kth
    # missing integer in the sorted foreground positions. Storage scales only
    # with foreground, is created lazily, and is released with the bounded case LRU.
    excluded = data.get("_center_background_exclusions")
    if excluded is None:
        excluded = np.sort(
            np.concatenate([np.ravel_multi_index(coordinates[c].T, label.shape) for c in (1, 2)])
        )
        data["_center_background_exclusions"] = excluded
    rank = int(rng.integers(count))
    lo, hi = rank, rank + len(excluded)
    while lo < hi:
        middle = (lo + hi) // 2
        background_through_middle = middle + 1 - np.searchsorted(excluded, middle, side="right")
        if background_through_middle > rank:
            hi = middle
        else:
            lo = middle + 1
    return [int(x) for x in np.unravel_index(lo, label.shape)]


def explicit_center(
    data: dict,
    config: TorchConfig,
    rng: np.random.Generator,
    uniform_center: list[int],
    diagnostics: dict[str, Any] | None,
) -> list[int]:
    """Select one center; diagnostics never consume randomness or change selection."""
    coordinates = _coordinates(data)
    counts = {c: len(coordinates[c]) for c in (1, 2)}
    counts[0] = data["label"].size - counts[1] - counts[2]
    uniform_mode = config.center_probabilities is not None
    weights = config.center_probabilities if uniform_mode else config.class_center_weights
    assert weights is not None
    missing = [c for c in (0, 1, 2) if not counts[c] and (c != 0 or not uniform_mode)]
    effective = np.asarray(weights, dtype=np.float64).copy()
    effective[missing] = 0
    fallback = not bool(effective.sum())
    if fallback:
        selected, center = None, uniform_center
    else:
        effective /= effective.sum()
        selected = int(rng.choice(3, p=effective))
        if selected == 0 and uniform_mode:
            selected, center = None, uniform_center
        elif selected == 0:
            center = _background_center(data, coordinates, counts[0], rng)
        else:
            locations = coordinates[selected]
            center = locations[int(rng.integers(len(locations)))].tolist()
    if diagnostics is not None:
        diagnostics.update(
            center_mode="uniform_class_mixture" if uniform_mode else "class_center_weights",
            requested_center_branch="weighted_choice",
            requested_center_weights=list(weights),
            effective_center_probabilities=effective.tolist(),
            selected_center_branch={
                None: "uniform_volume",
                0: "background",
                1: "pancreas",
                2: "mass",
            }[selected],
            selected_center_class=selected,
            center_fallback=fallback,
            missing_center_classes=missing,
        )
    return center
