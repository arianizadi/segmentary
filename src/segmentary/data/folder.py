"""Generic paired image/mask folders for arbitrary semantic-segmentation data.

The default layout is intentionally boring and portable::

    <root>/images/<split>/<key>.jpg
    <root>/masks/<split>/<key>.png

Nested directories are supported with ``recursive=True``.  A mask keeps the
image's relative path and stem, replacing only its extension.  Masks must be
single-channel integer-index images; class meanings live in the taxonomy YAML,
not in this loader.

An optional split manifest uses the same compact JSON contract as the grouped
split tool::

    {"train": ["run1/frame001"], "val": ["run2/frame001"],
     "groups": {"run1/frame001": "run1", "run2/frame001": "run2"}}

When present, the manifest is checked against the files on disk and groups must
not cross splits.  For independent still images it may be omitted.  For video
frames, set ``require_groups=True`` so accidental frame-level leakage is fatal.
"""

from __future__ import annotations

import json
import string
from pathlib import Path
from typing import Any

from albumentations import Compose

from ..taxonomy import DatasetMapping
from .base import Sample, SegDataset

DEFAULT_IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp")


class FolderSegmentationDataset(SegDataset):
    """Paired image and indexed-mask folders with optional group-safe splits."""

    def __init__(
        self,
        root: Path | str,
        split: str,
        mapping: DatasetMapping,
        transform: Compose,
        limit: int | None = None,
        *,
        image_dir: str = "images/{split}",
        mask_dir: str = "masks/{split}",
        image_extensions: list[str] | tuple[str, ...] = DEFAULT_IMAGE_EXTENSIONS,
        mask_extension: str = ".png",
        recursive: bool = True,
        split_file: str | Path | None = None,
        require_groups: bool = False,
    ) -> None:
        self.image_dir_template = image_dir
        self.mask_dir_template = mask_dir
        self.image_extensions = self._extensions(image_extensions, "image_extensions")
        self.mask_extension = self._extensions((mask_extension,), "mask_extension")[0]
        self.recursive = recursive
        self.split_file = Path(split_file) if split_file is not None else None
        self.require_groups = require_groups
        self._groups: dict[str, str] = {}
        super().__init__(root, split, mapping, transform, limit)

    @staticmethod
    def _extensions(values: list[str] | tuple[str, ...], field: str) -> tuple[str, ...]:
        if not values or not all(isinstance(value, str) and value for value in values):
            raise ValueError(f"folder loader {field} must contain non-empty strings")
        normalised = tuple(
            value.lower() if value.startswith(".") else f".{value.lower()}" for value in values
        )
        if len(set(normalised)) != len(normalised):
            raise ValueError(f"folder loader {field} contains duplicate extensions {normalised}")
        return normalised

    def _directory(self, template: str, kind: str) -> Path:
        fields = [
            (name, spec, conversion)
            for _, name, spec, conversion in string.Formatter().parse(template)
            if name is not None
        ]
        if any(name != "split" or spec or conversion for name, spec, conversion in fields):
            raise ValueError(
                f"folder loader {kind}={template!r} may contain only the {{split}} placeholder"
            )
        try:
            rendered = template.format(split=self.split)
        except (IndexError, KeyError, ValueError) as exc:
            raise ValueError(
                f"folder loader {kind}={template!r} may contain only the {{split}} placeholder"
            ) from exc
        path = Path(rendered)
        if not path.is_absolute():
            path = self.root / path
        if not path.is_dir():
            raise FileNotFoundError(
                f"folder dataset expected {kind} directory {path}. Configure "
                f"loader_options.{kind} if your layout differs."
            )
        return path

    def _manifest_path(self) -> Path | None:
        if self.split_file is not None:
            return self.split_file if self.split_file.is_absolute() else self.root / self.split_file
        conventional = self.root / "splits.json"
        return conventional if conventional.is_file() else None

    def _load_manifest(self, keys: set[str]) -> dict[str, str]:
        path = self._manifest_path()
        if path is None:
            if self.require_groups:
                raise FileNotFoundError(
                    "folder loader require_groups=true needs split_file or <root>/splits.json; "
                    "video frames must be split by recording rather than by frame"
                )
            return {}
        if not path.is_file():
            raise FileNotFoundError(f"folder dataset split manifest not found: {path}")
        try:
            payload: Any = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"folder dataset cannot read valid JSON from {path}: {exc}") from exc
        if not isinstance(payload, dict):
            raise ValueError(f"folder dataset {path} must contain a JSON object")
        raw_groups = payload.get("groups", {})
        if not isinstance(raw_groups, dict) or not all(
            isinstance(key, str) and isinstance(value, str) and value.strip()
            for key, value in raw_groups.items()
        ):
            raise ValueError(f"folder dataset {path}: groups must map string keys to group names")
        # Treat cosmetic whitespace consistently with make_split. Otherwise
        # ``"run-7"`` and ``" run-7 "`` can evade the cross-split leak check.
        # The isinstance check above already proved both sides are str; state it
        # so the split-leak comparison below is checked against real string sets.
        groups: dict[str, str] = {key: value.strip() for key, value in raw_groups.items()}

        members: dict[str, set[str]] = {}
        split_keys: dict[str, set[str]] = {}
        for name, values in payload.items():
            if name == "groups" or name.startswith("_"):
                continue
            if not isinstance(values, list) or not all(isinstance(value, str) for value in values):
                raise ValueError(f"folder dataset {path}: split {name!r} must be a list of keys")
            # The check above proves these are strings; binding them to a typed
            # name keeps the group lookup below a str -> str mapping.
            entries: list[str] = list(values)
            if len(entries) != len(set(entries)):
                raise ValueError(f"folder dataset {path}: split {name!r} contains duplicate keys")
            split_keys[name] = set(entries)
            members[name] = {groups.get(entry, entry) for entry in entries}

        names = sorted(members)
        for index, left in enumerate(names):
            for right in names[index + 1 :]:
                overlap = members[left] & members[right]
                if overlap:
                    raise ValueError(
                        f"folder dataset {path}: splits {left!r} and {right!r} share groups "
                        f"{sorted(overlap)[:5]}; this leaks related samples across evaluation"
                    )
        if self.split not in split_keys:
            raise ValueError(
                f"folder dataset {path}: requested split {self.split!r} is absent; "
                f"available splits are {sorted(split_keys)}"
            )
        if self.split in split_keys and split_keys[self.split] != keys:
            missing = sorted(split_keys[self.split] - keys)
            extra = sorted(keys - split_keys[self.split])
            raise ValueError(
                f"folder dataset {path}: split {self.split!r} does not match disk; "
                f"missing={missing[:5]}, extra={extra[:5]}"
            )
        if self.require_groups:
            all_manifest_keys = set().union(*split_keys.values()) if split_keys else set()
            absent = sorted(all_manifest_keys - set(groups))
            if absent:
                raise ValueError(
                    f"folder dataset {path}: require_groups=true but {len(absent)} manifest "
                    f"keys have no group (first {absent[0]!r})"
                )
        return {str(key): str(value) for key, value in groups.items()}

    def index(self) -> list[Sample]:
        image_root = self._directory(self.image_dir_template, "image_dir")
        mask_root = self._directory(self.mask_dir_template, "mask_dir")
        images = self._files_by_key(image_root, self.image_extensions, "images")
        masks = self._files_by_key(mask_root, (self.mask_extension,), "masks")
        missing = sorted(set(images) - set(masks))
        orphaned = sorted(set(masks) - set(images))
        if missing or orphaned:
            raise FileNotFoundError(
                f"folder dataset {self.split!r} is not one-to-one: {len(missing)} images have "
                f"no mask (first {missing[0] if missing else '<none>'!r}); {len(orphaned)} "
                f"masks have no image (first {orphaned[0] if orphaned else '<none>'!r})"
            )
        samples = [
            Sample(image=images[key], label=masks[key], key=key, group=key)
            for key in sorted(images)
        ]
        groups = self._load_manifest({sample.key for sample in samples})
        self._groups = groups
        return [
            Sample(
                image=sample.image,
                label=sample.label,
                key=sample.key,
                group=groups.get(sample.key, sample.key),
            )
            for sample in samples
        ]

    def _files_by_key(self, root: Path, extensions: tuple[str, ...], kind: str) -> dict[str, Path]:
        iterator = root.rglob("*") if self.recursive else root.iterdir()
        found: dict[str, Path] = {}
        for path in sorted(
            candidate
            for candidate in iterator
            if candidate.is_file() and candidate.suffix.lower() in extensions
        ):
            key = path.relative_to(root).with_suffix("").as_posix()
            if key in found:
                raise ValueError(
                    f"folder dataset {self.split!r}: multiple {kind} resolve to key {key!r}; "
                    "remove duplicate extensions or use distinct relative stems"
                )
            found[key] = path
        return found

    def group_counts(self) -> dict[str, int]:
        """Return sorted frame counts per group for split-composition reporting."""
        counts: dict[str, int] = {}
        for sample in self.samples:
            counts[sample.group] = counts.get(sample.group, 0) + 1
        return dict(sorted(counts.items()))
