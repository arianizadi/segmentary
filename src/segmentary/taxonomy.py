"""Canonical label spaces and vectorised native -> canonical id mapping.

This module is the single place where a dataset's native label ids become
canonical training ids. Every dataset goes through it, including the custom one,
so the validation guarantees below hold uniformly:

  * mapping is applied as a 256-entry uint8 lookup table, never a Python loop;
  * every native id lands on exactly one canonical id or on ``ignore_index``;
  * a canonical id reachable from two native ids is a hard error unless the
    mapping file declares the merge with a written reason.

The last rule is the important one: a silent many-to-one collapse is invisible in
the loss curve and shows up months later as an unexplainable per-class IoU.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import yaml

LUT_SIZE = 256


class TaxonomyError(ValueError):
    """Raised when a label space or mapping file is internally inconsistent."""


@dataclass(frozen=True)
class CanonicalClass:
    id: int
    name: str
    color: tuple[int, int, int]


@dataclass(frozen=True)
class LabelSpace:
    """A canonical class list shared by every dataset in an experiment."""

    name: str
    description: str
    ignore_index: int
    classes: tuple[CanonicalClass, ...]
    thin_classes: tuple[int, ...]

    @property
    def num_classes(self) -> int:
        return len(self.classes)

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(c.name for c in self.classes)

    @property
    def palette(self) -> np.ndarray:
        """(256, 3) uint8 colour table; ``ignore_index`` renders black."""
        lut = np.zeros((LUT_SIZE, 3), dtype=np.uint8)
        for c in self.classes:
            lut[c.id] = c.color
        return lut


# eq=False: the dataclass holds a numpy array, and the generated __eq__ would
# raise "truth value of an array is ambiguous" on any comparison.
@dataclass(frozen=True, eq=False)
class DatasetMapping:
    """A validated native-id -> canonical-id lookup table for one dataset."""

    space: LabelSpace
    dataset: str
    source: str
    variant: str | None
    lut: np.ndarray  # (256,) uint8
    active_ids: tuple[int, ...]
    merges: Mapping[int, str]

    def apply(self, native: np.ndarray) -> np.ndarray:
        """Map a native label array to canonical ids. Vectorised, allocation-light."""
        if native.dtype != np.uint8:
            if native.min() < 0 or native.max() >= LUT_SIZE:
                raise TaxonomyError(
                    f"{self.dataset}: label ids outside [0, {LUT_SIZE}) cannot use a "
                    f"uint8 LUT (observed min={native.min()}, max={native.max()})"
                )
            native = native.astype(np.uint8)
        return self.lut[native]

    @property
    def inactive_ids(self) -> tuple[int, ...]:
        """Canonical ids this dataset can never produce (masked under unified_head)."""
        active = set(self.active_ids)
        return tuple(i for i in range(self.space.num_classes) if i not in active)

    def active_mask(self) -> np.ndarray:
        """(num_classes,) bool; True where this dataset supervises the class."""
        mask = np.zeros(self.space.num_classes, dtype=bool)
        mask[list(self.active_ids)] = True
        return mask

    def assert_covers(self, observed: Iterable[int]) -> None:
        """Fail if a mask contains a native id the mapping never declared.

        Called by ``verify_dataset.py`` against real files. Static validation
        cannot know which ids a dataset actually emits; this closes that gap.
        """
        undeclared = sorted(set(int(i) for i in observed) - self._declared)
        if undeclared:
            raise TaxonomyError(
                f"{self.dataset} ({self.space.name}): masks contain native ids "
                f"{undeclared} that the mapping does not declare. They would "
                f"silently fall through to default. Add them to "
                f"taxonomy/{self.space.name}/{self._filename}."
            )

    # populated by the loader; kept private so the dataclass stays comparable
    _declared: frozenset[int] = frozenset()
    _filename: str = ""


def _require(cond: object, msg: str) -> None:
    if not cond:
        raise TaxonomyError(msg)


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise TaxonomyError(f"taxonomy file not found: {path}")
    with path.open() as fh:
        data = yaml.safe_load(fh)
    _require(isinstance(data, dict), f"{path}: expected a YAML mapping at top level")
    return data


def load_space(root: Path | str, name: str) -> LabelSpace:
    """Load and validate a canonical label space from ``<root>/<name>/canonical.yaml``."""
    path = Path(root) / name / "canonical.yaml"
    data = _load_yaml(path)

    ignore_index = int(data.get("ignore_index", 255))
    _require(
        ignore_index == 255,
        f"{path}: ignore_index must be 255 so masks stay uint8 (got {ignore_index})",
    )

    raw = data.get("classes")
    if not isinstance(raw, list) or not raw:
        raise TaxonomyError(f"{path}: `classes` must be a non-empty list")

    classes: list[CanonicalClass] = []
    for entry in raw:
        _require(
            isinstance(entry, dict) and {"id", "name"} <= entry.keys(),
            f"{path}: each class needs at least `id` and `name`, got {entry!r}",
        )
        color = tuple(int(c) for c in entry.get("color", (0, 0, 0)))
        _require(
            len(color) == 3 and all(0 <= c < 256 for c in color),
            f"{path}: class {entry['name']!r} has a malformed colour {color!r}",
        )
        rgb = (color[0], color[1], color[2])
        classes.append(CanonicalClass(int(entry["id"]), str(entry["name"]), rgb))

    ids = [c.id for c in classes]
    _require(
        ids == list(range(len(ids))),
        f"{path}: class ids must be contiguous and start at 0, got {ids}",
    )
    names = [c.name for c in classes]
    _require(len(set(names)) == len(names), f"{path}: duplicate class names in {names}")
    _require(
        len(classes) < ignore_index,
        f"{path}: {len(classes)} classes would collide with ignore_index={ignore_index}",
    )

    thin = tuple(int(i) for i in data.get("thin_classes", ()))
    unknown = [i for i in thin if not 0 <= i < len(classes)]
    _require(not unknown, f"{path}: thin_classes references unknown ids {unknown}")

    return LabelSpace(
        name=str(data.get("name", name)),
        description=str(data.get("description", "")).strip(),
        ignore_index=ignore_index,
        classes=tuple(classes),
        thin_classes=thin,
    )


def load_mapping(
    root: Path | str,
    space: LabelSpace | str,
    dataset: str,
    variant: str | None = None,
) -> DatasetMapping:
    """Load and validate ``<root>/<space>/<dataset>[_<variant>].yaml`` into a LUT."""
    root = Path(root)
    if isinstance(space, str):
        space = load_space(root, space)

    stem = dataset if variant is None else f"{dataset}_{variant}"
    filename = f"{stem}.yaml"
    path = root / space.name / filename
    data = _load_yaml(path)

    declared_space = str(data.get("space", space.name))
    _require(
        declared_space == space.name,
        f"{path}: declares space {declared_space!r} but was loaded as {space.name!r}",
    )

    default = int(data.get("default", space.ignore_index))
    _require(
        default == space.ignore_index,
        f"{path}: `default` must be ignore_index ({space.ignore_index}). Any other "
        f"value turns an unmapped native id into real supervision, which is the "
        f"exact failure this layer exists to prevent (got {default}).",
    )

    raw_map = data.get("map")
    if not isinstance(raw_map, dict) or not raw_map:
        raise TaxonomyError(f"{path}: `map` must be a non-empty mapping")

    valid = set(range(space.num_classes)) | {space.ignore_index}
    lut = np.full(LUT_SIZE, space.ignore_index, dtype=np.uint8)
    sources: dict[int, list[int]] = {}

    for k, v in raw_map.items():
        native, canonical = int(k), int(v)
        _require(
            0 <= native < LUT_SIZE,
            f"{path}: native id {native} is outside [0, {LUT_SIZE})",
        )
        _require(
            canonical in valid,
            f"{path}: native id {native} maps to {canonical}, which is neither a class "
            f"of {space.name} (0..{space.num_classes - 1}) nor ignore_index "
            f"({space.ignore_index})",
        )
        lut[native] = canonical
        if canonical != space.ignore_index:
            sources.setdefault(canonical, []).append(native)

    merges = {int(k): str(v).strip() for k, v in (data.get("allow_merge") or {}).items()}

    collisions = {c: n for c, n in sources.items() if len(n) > 1}
    undeclared = sorted(set(collisions) - set(merges))
    if undeclared:
        detail = "; ".join(
            f"{space.classes[c].name!r} (id {c}) <- native ids {sorted(collisions[c])}"
            for c in undeclared
        )
        raise TaxonomyError(
            f"{path}: undeclared many-to-one merges: {detail}. If the merge is "
            f"intended, add the canonical id to `allow_merge` with a reason."
        )

    stale = sorted(set(merges) - set(collisions))
    _require(
        not stale,
        f"{path}: `allow_merge` declares {stale} but nothing merges into them. "
        f"Stale entries hide real merges added later.",
    )
    for cid, reason in merges.items():
        _require(reason, f"{path}: allow_merge[{cid}] needs a written reason, not an empty string")

    mapping = DatasetMapping(
        space=space,
        dataset=str(data.get("dataset", dataset)),
        source=str(data.get("source", "")).strip(),
        variant=variant,
        lut=lut,
        active_ids=tuple(sorted(sources)),
        merges=merges,
    )
    object.__setattr__(mapping, "_declared", frozenset(int(k) for k in raw_map))
    object.__setattr__(mapping, "_filename", filename)
    return mapping


def colorize(canonical: np.ndarray, space: LabelSpace) -> np.ndarray:
    """Render canonical ids to an RGB image for visual inspection."""
    return space.palette[canonical]
