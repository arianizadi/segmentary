"""Label ontologies of the supported CT datasets and the regions scored on each.

A manifest stores its ontology, and the profile is resolved from that exact
mapping, so Task07 and PanTS manifests (which carry the pancreas/mass ontology)
keep their original bytes and identities. Every profile has a host region (the
whole organ including its lesions, scorable on organ-only references) and a
lesion region (used for split stratification and lesion detection). Labels are
exclusive voxel classes; regions are unions of them.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .geometry import MedicalDataError


@dataclass(frozen=True)
class DatasetProfile:
    """One dataset's label ontology, evaluation regions and reporting language."""

    name: str
    dataset: str
    ontology: Mapping[str, int]
    source_labels: Mapping[str, str]
    host: str
    lesion: str
    # Ordered (name, labels) evaluation regions; the host region comes first.
    regions: tuple[tuple[str, tuple[int, ...]], ...]
    # Ordered nnU-Net region heads and their decode order (see ``nnunet_regions``).
    nnunet_regions: tuple[tuple[str, tuple[int, ...]], ...]
    nnunet_regions_class_order: tuple[int, ...]
    clinical_label_note: str
    limitations: tuple[str, ...]
    overlay_colors: tuple[tuple[int, tuple[int, int, int]], ...]
    overlay_legend: str
    # The exclusive organ label name when the host region is a union (KiTS23).
    organ: str | None = None
    # Official per-region surface-Dice tolerances (mm), when the benchmark defines them.
    official_surface_tolerances_mm: tuple[tuple[str, float], ...] = ()
    # Lesion-detection wording in reports.
    lesion_interpretation: str = (
        "connected-component agreement with annotated lesion masks; not a diagnosis"
    )

    @property
    def region_labels(self) -> dict[str, tuple[int, ...]]:
        return dict(self.regions)

    @property
    def lesion_labels(self) -> tuple[int, ...]:
        return self.region_labels[self.lesion]

    @property
    def host_labels(self) -> tuple[int, ...]:
        return self.region_labels[self.host]

    @property
    def host_label(self) -> int:
        """The exclusive organ label, the only foreground of an organ-only reference."""
        name = self.organ or self.host
        if name not in self.ontology:
            raise MedicalDataError(f"{self.name} has no exclusive organ label {name!r}")
        return self.ontology[name]

    def label_regions(self) -> list[list[Any]]:
        """nnU-Net ``label_regions`` in the ordered ``[[name, [labels]], ...]`` form."""
        return [[name, list(labels)] for name, labels in self.nnunet_regions]


PANCREAS = DatasetProfile(
    name="task07",
    dataset="Task07_Pancreas",
    ontology={"background": 0, "pancreas": 1, "mass": 2},
    source_labels={"0": "background", "1": "pancreas", "2": "cancer"},
    host="pancreas",
    lesion="mass",
    regions=(("pancreas", (1, 2)), ("mass", (2,))),
    nnunet_regions=(("pancreas", (1, 2)), ("mass", (2,))),
    nnunet_regions_class_order=(1, 2),
    clinical_label_note="Mass masks do not establish PDAC diagnosis. Unlabeled scans are not negative cases.",
    limitations=(
        "Mass-mask agreement does not establish PDAC diagnosis, screening performance or clinical utility.",
        "Organ-only annotations cannot establish absence of a mass; their mass metrics are unknown.",
    ),
    overlay_colors=((1, (0, 220, 90)), (2, (255, 60, 70))),
    overlay_legend="Green: pancreas   Red: annotated/predicted mass   Axial RAS review",
    lesion_interpretation="connected-component agreement with annotated masses; not PDAC diagnosis",
)
LIVER = DatasetProfile(
    name="lits",
    dataset="Task03_Liver",
    ontology={"background": 0, "liver": 1, "tumor": 2},
    source_labels={"0": "background", "1": "liver", "2": "cancer"},
    host="liver",
    lesion="tumor",
    regions=(("liver", (1, 2)), ("tumor", (2,))),
    nnunet_regions=(("liver", (1, 2)), ("tumor", (2,))),
    nnunet_regions_class_order=(1, 2),
    clinical_label_note="Tumor masks are reference delineations, not a diagnosis. Unlabeled scans are not negative cases.",
    limitations=(
        "Tumor-mask agreement does not establish diagnosis, screening performance or clinical utility.",
        "Organ-only annotations cannot establish absence of a tumor; their tumor metrics are unknown.",
    ),
    overlay_colors=((1, (0, 220, 90)), (2, (255, 60, 70))),
    overlay_legend="Green: liver   Red: annotated/predicted tumor   Axial RAS review",
)
KIDNEY = DatasetProfile(
    name="kits23",
    dataset="KiTS23",
    ontology={"background": 0, "kidney": 1, "tumor": 2, "cyst": 3},
    source_labels={"0": "background", "1": "kidney", "2": "tumor", "3": "cyst"},
    host="kidney_and_masses",
    lesion="tumor",
    # The KiTS23 hierarchical evaluation regions.
    regions=(("kidney_and_masses", (1, 2, 3)), ("masses", (2, 3)), ("tumor", (2,))),
    nnunet_regions=(("kidney_and_masses", (1, 2, 3)), ("masses", (2, 3)), ("tumor", (2,))),
    nnunet_regions_class_order=(1, 3, 2),
    clinical_label_note="Tumor and cyst masks are reference delineations, not a diagnosis.",
    limitations=(
        "Tumor-mask agreement does not establish diagnosis, malignancy or clinical utility.",
        "KiTS23 NIfTI spatial units are undeclared; they are read as millimetres per the dataset documentation.",
    ),
    overlay_colors=((1, (0, 220, 90)), (2, (255, 60, 70)), (3, (60, 140, 255))),
    overlay_legend="Green: kidney   Red: tumor   Blue: cyst   Axial RAS review",
    organ="kidney",
    # kits23/configuration/labels.py HEC_SD_TOLERANCES_MM (repo c1088353), mapped to our
    # region names (kidney_and_mass, mass, tumor there).
    official_surface_tolerances_mm=(
        ("kidney_and_masses", 1.0330772532390826),
        ("masses", 1.1328796488598762),
        ("tumor", 1.1498198361434828),
    ),
)
PROFILES = {profile.name: profile for profile in (PANCREAS, LIVER, KIDNEY)}


def profile_named(name: str) -> DatasetProfile:
    if name not in PROFILES:
        raise MedicalDataError(f"unknown dataset profile {name!r}; use one of {sorted(PROFILES)}")
    return PROFILES[name]


def profile_for_ontology(ontology: Any) -> DatasetProfile:
    """The profile whose ontology is exactly this mapping (names and integer values)."""
    if isinstance(ontology, Mapping) and all(type(value) is int for value in ontology.values()):
        for profile in PROFILES.values():
            if dict(ontology) == dict(profile.ontology):
                return profile
    raise MedicalDataError("unsupported manifest schema or label ontology")
