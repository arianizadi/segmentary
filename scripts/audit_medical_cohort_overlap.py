#!/usr/bin/env python3
"""Audit cross-cohort overlap from audited metadata without opening CT/mask payloads.

No-hit results never establish independence: repackaging, resampling, renamed IDs,
repeated scans and absent crosswalks can hide shared patients. Keep this evidence
in approved local research storage; pseudonymization is not de-identification.
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
from collections import defaultdict
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from segmentary.medical.data import atomic_write_json, load_manifest
from segmentary.medical.geometry import sha256_file

KINDS = (
    "exact_image_file_hash",
    "exact_decoded_image_hash",
    "same_source_patient_id",
    "same_source_case_id",
    "same_source_inherited_group",
)


def _key(kind: str, value: Any) -> str:
    payload = json.dumps([kind, value], sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(payload.encode()).hexdigest()[:24]


def _prepare(document: dict[str, Any], manifest_hash: str, position: int) -> dict[str, Any]:
    identities: dict[str, dict[tuple[str, ...], list[str]]] = {
        kind: defaultdict(list) for kind in KINDS
    }
    raw_patients: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    raw_groups: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    inherited = document.get("inherited_group_assignments", {})
    for case in document["cases"]:
        source = case["source"].strip()
        case_key = _key("case", [document["fingerprint"], case["case_id"]])
        identities["exact_image_file_hash"][(case["image_sha256"],)].append(case_key)
        if case.get("image_voxel_sha256"):
            identities["exact_decoded_image_hash"][(case["image_voxel_sha256"],)].append(case_key)
        identities["same_source_patient_id"][(source, case["patient_id"])].append(case_key)
        identities["same_source_case_id"][(source, case["case_id"])].append(case_key)
        raw_patients[case["patient_id"]][source].append(case_key)
        if case["case_id"] in inherited:
            group = inherited[case["case_id"]]
            identities["same_source_inherited_group"][(source, group)].append(case_key)
            raw_groups[group][source].append(case_key)
    return {
        "cohort": f"cohort-{position + 1}",
        "manifest_sha256": manifest_hash,
        "manifest_fingerprint": document["fingerprint"],
        "dataset_key": _key("dataset", document["dataset"]),
        "case_count": len(document["cases"]),
        "patient_id_count": len({case["patient_id"] for case in document["cases"]}),
        "source_count": len({case["source"].strip() for case in document["cases"]}),
        "decoded_image_hash_cases": sum(
            bool(case.get("image_voxel_sha256")) for case in document["cases"]
        ),
        "inherited_group_cases": len(inherited),
        "patient_identity_verified_in_manifest": document["audit"].get("patient_identity_verified")
        is True,
        "dataset_case_identity_placeholders": document.get("grouping_status")
        == "dataset_case_unverified",
        "excluded_identity_records_not_compared": len(document.get("excluded_case_identities", [])),
        "_identities": identities,
        "_patients": raw_patients,
        "_groups": raw_groups,
    }


def _hits(left: dict, right: dict, kind: str) -> dict:
    left_index, right_index = left["_identities"][kind], right["_identities"][kind]
    common = sorted(left_index.keys() & right_index.keys())
    hits: list[dict[str, Any]] = [
        {
            "evidence_key": _key(kind, identity),
            "left_case_keys": sorted(left_index[identity]),
            "right_case_keys": sorted(right_index[identity]),
            "left_cases": len(left_index[identity]),
            "right_cases": len(right_index[identity]),
        }
        for identity in common
    ]
    return {
        "matching_identity_groups": len(hits),
        "left_cases_with_evidence": len({key for hit in hits for key in hit["left_case_keys"]}),
        "right_cases_with_evidence": len({key for hit in hits for key in hit["right_case_keys"]}),
        "case_pair_links": sum(hit["left_cases"] * hit["right_cases"] for hit in hits),
        "groups": hits,
    }


def _unscoped_collisions(left: dict, right: dict, field: str) -> list[dict]:
    """Same bare ID in different sources is an unresolved namespace collision."""
    lindex, rindex = left[field], right[field]
    collisions = []
    for identity in sorted(lindex.keys() & rindex.keys()):
        left_sources, right_sources = set(lindex[identity]), set(rindex[identity])
        left_ambiguous = {
            source
            for source in left_sources
            if len(right_sources) > 1 or source not in right_sources
        }
        right_ambiguous = {
            source
            for source in right_sources
            if len(left_sources) > 1 or source not in left_sources
        }
        if not left_ambiguous or not right_ambiguous:
            continue
        collisions.append(
            {
                "evidence_key": _key(f"ambiguous-{field}", identity),
                "left_case_keys": sorted(
                    {key for ls in left_ambiguous for key in lindex[identity][ls]}
                ),
                "right_case_keys": sorted(
                    {key for rs in right_ambiguous for key in rindex[identity][rs]}
                ),
                "interpretation": "Different source namespaces; shared text alone does not establish shared identity",
            }
        )
    return collisions


def audit(manifests: Sequence[Path]) -> dict[str, Any]:
    """Compare every manifest pair using existing evidence, never refreshing scans.

    Image file hashes show exact file identity. Optional decoded-image hashes are
    stronger against recompression but only cover cases where an earlier audit
    recorded them. Source-qualified IDs/group names remain documentary linkage
    evidence, not independently verified patient identity. Inherited groups are
    scoped by source because generic group IDs can collide across datasets.
    """
    if len(manifests) < 2:
        raise ValueError("At least two audited manifests are required")
    paths = [Path(path).expanduser().resolve() for path in manifests]
    if len(set(paths)) != len(paths):
        raise ValueError("Repeated manifest paths are not distinct cohorts")
    hashes = [sha256_file(path) for path in paths]
    documents = [load_manifest(path, verify_files=False) for path in paths]
    if len({document["fingerprint"] for document in documents}) != len(documents):
        raise ValueError("Identical manifest fingerprints are not distinct cohorts")
    cohorts = [
        _prepare(doc, digest, index)
        for index, (doc, digest) in enumerate(zip(documents, hashes, strict=True))
    ]
    pairs = []
    for left, right in itertools.combinations(cohorts, 2):
        evidence = {kind: _hits(left, right, kind) for kind in KINDS}
        exact = any(evidence[kind]["matching_identity_groups"] for kind in KINDS[:2])
        linkage = any(evidence[kind]["matching_identity_groups"] for kind in KINDS[2:])
        patient_collisions = _unscoped_collisions(left, right, "_patients")
        group_collisions = _unscoped_collisions(left, right, "_groups")
        pairs.append(
            {
                "left_cohort": left["cohort"],
                "right_cohort": right["cohort"],
                "status": "exact_image_overlap_found"
                if exact
                else "documented_identifier_overlap_requires_review"
                if linkage
                else "ambiguous_identifier_collision_requires_review"
                if patient_collisions or group_collisions
                else "no_overlap_found_independence_unresolved",
                "independence_established": False,
                "evidence": evidence,
                "cross_source_patient_id_text_collisions": patient_collisions,
                "cross_source_inherited_group_text_collisions": group_collisions,
                "decision": "Resolve overlap before treating these cohorts as independent evaluation sets"
                if exact or linkage or patient_collisions or group_collisions
                else "No automatic clearance; source crosswalk and near-duplicate/patient overlap review still required",
            }
        )
    if any(sha256_file(path) != digest for path, digest in zip(paths, hashes, strict=True)):
        raise ValueError("Manifest metadata changed during audit; retry with stable inputs")
    return {
        "schema_version": 1,
        "kind": "medical_cohort_overlap_metadata_audit",
        "cohorts": [{k: v for k, v in item.items() if not k.startswith("_")} for item in cohorts],
        "pairs": pairs,
        "policy": {
            "payload_reads": 0,
            "case_scope": "All included manifest cases, including unlabeled/held-out metadata; no partition payloads opened",
            "independence_established": False,
            "identifier_scope": "Exact case-sensitive source plus patient/case/inherited-group ID; no inferred aliases or crosswalks",
            "label_hashes": "Never used as overlap evidence; empty or reused labels can be identical for unrelated scans",
            "storage": "Local approved research storage only; pseudonymization is not de-identification",
            "file_content_status": "Previously audited metadata trusted; current image/mask files are not reopened or rehashed",
            "group_counts": "Evidence kinds can overlap; their counts must not be summed as unique patient totals",
            "limitations": [
                "No match is not proof of patient, institution or cohort independence.",
                "Different compression/header bytes can change image file hashes without changing the scan.",
                "Decoded hashes may be absent; resampling, cropping, changed intensity encoding and repeated acquisitions can evade exact hashing.",
                "Source-qualified identifiers and inherited groups may be placeholders or local namespaces; clinical identity needs an authoritative crosswalk.",
                "Inherited groups from renamed source namespaces are flagged as ambiguous textual collisions, not automatically merged.",
                "Previously excluded identity records are not scanned; existing inherited groups can preserve their links to included cases.",
            ],
        },
        "implementation_sha256": sha256_file(Path(__file__)),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifests", type=Path, nargs="+", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    report = audit(args.manifests)
    atomic_write_json(args.output, report)
    print(
        json.dumps(
            {
                "cohorts": len(report["cohorts"]),
                "pairs": len(report["pairs"]),
                "output": str(args.output),
            }
        )
    )


if __name__ == "__main__":
    main()
