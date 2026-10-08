# LiTS and KiTS23 transfer benchmarks

Audit, split, cross-validation, the nnU-Net backend, probability export and evaluation run on three label ontologies. Campaign reports (`scripts/report_medical_campaign.py`) and the planners still cover Task07 only: a report on a LiTS or KiTS23 campaign is refused, and no planner preset writes a LiTS or KiTS23 arm yet. A manifest stores its ontology, and every stage resolves the dataset profile from that exact mapping (`segmentary.medical.dataset_profiles`):

| Profile | Manifest `dataset` | Ontology | Scored regions (first = host) | Lesion (stratification, detection) |
|---|---|---|---|---|
| `task07` | `Task07_Pancreas` (also PanTS) | 0 background, 1 pancreas, 2 mass | pancreas {1,2}, mass {2} | mass {2} |
| `lits` | `Task03_Liver` | 0 background, 1 liver, 2 tumor | liver {1,2}, tumor {2} | tumor {2} |
| `kits23` | `KiTS23` | 0 background, 1 kidney, 2 tumor, 3 cyst | kidney_and_masses {1,2,3}, masses {2,3}, tumor {2} | tumor {2} |

Task07 behaviour is unchanged: with no new option, the audit, split and `cv-split` write the same bytes as before (`tests/test_medical_transfer_datasets.py` compares them against the base-commit sources). That includes a pancreas/mass manifest whose training cases lack a mass count (PanTS-style): its CV still falls back to the seeded shuffle, as before.

## Audit

```bash
# MSD Task03 (dataset.json layout). Labels must be named background/liver/cancer.
python -m segmentary.medical.cli audit --dataset lits \
  --dataset-root /path/to/Task03_Liver --output task03-manifest.json \
  --duplicate-links task03-duplicate-links.json --qform-sform-atol-mm 1e-3

# KiTS23 (repository dataset/ directory with kits23.json and case_*/).
python -m segmentary.medical.cli audit-kits23 \
  --dataset-root /path/to/kits23/dataset --output kits23-manifest.json --unknown-units-as-mm
```

- **Geometry relaxations are opt-in and recorded.** `--qform-sform-atol-mm` (at most 1e-3) accepts float32 qform/sform rounding; 83 of 131 Task03 labels differ by up to 9.8e-4 mm. `--unknown-units-as-mm` reads undeclared NIfTI units as mm, as the KiTS23 documentation states; any other unit is still refused. The manifest stores the policy under `geometry_policy`, and each case lists which relaxation each file needed under `geometry_relaxations` (an empty list means the strict check passed). Prediction (`backend.predict`), probability export and evaluation apply only the policy and label values stored in the manifest. Manifest validation also refuses a per-file relaxation that the stored policy does not allow.
- **Duplicate links group scans whose bytes differ.** The links file is `{"links": [{"cases": [a, b], "evidence": "..."}]}`. Linked cases (and anything joined through them) get one `duplicate_group`, recorded under `duplicate_links` with the links file's SHA-256. Splits treat the group like a patient: it never spans two partitions. Unlabeled `imagesTs` scans are audited so that such a link is visible, but they never enter a split. Predicting the `unlabeled` partition (`backend.predict`, `predict_medical_probabilities.py`) skips any unlabeled scan that shares a patient, file, voxel or duplicate identity with a labelled case, such as LiTS `liver_137` (a copy of training case `liver_74`); `backend.predict` lists the skipped IDs under `excluded_duplicates_of_labeled_cases`. Note that LiTS `imagesTs` is the official challenge test set.
- **KiTS23** uses only the consensus `segmentation.nii.gz`; per-annotator `instances/` files are ignored. The case directories must match `kits23.json` exactly, and each must hold exactly `imaging.nii.gz` and `segmentation.nii.gz`.

## Split and cross-validation ("Variant B")

```bash
python -m segmentary.medical.cli split --manifest m.json --output splits.json \
  --train-fraction 0.64 --val-fraction 0.16 --seed 0 --stratify-lesion-volume
python -m segmentary.medical.cli cv-split --manifest m.json --splits splits.json \
  --output cv5.json --folds 5 --seed 0
```

This holds out a 20% test set and makes 5 development folds whose fold 0 is the frozen validation partition. It is not the published protocol: the nnU-Net Revisited LiTS anchor (ResEnc L 81.60) is a 5-fold CV over all 131 cases, while Variant B CV covers the 105 development cases. Fractions that sum to 1 up to float rounding (0.7 + 0.3) request no test set. `--stratify-lesion-volume` sorts connected groups by summed lesion volume (label 2 voxels × voxel volume; lesion-free cases count as zero), cuts them into blocks of about one smallest-partition group, fills each block by sequential apportionment and shuffles labels within the block with the seed. The split records this under `assignment`. `cv-split` stratifies folds 1–4 by the same lesion volume. Without the flag, `split` is the original seeded shuffle.

## nnU-Net backend

`prepare` accepts all three ontologies. Label mode writes the manifest ontology to `dataset.json`. For KiTS23 region training, give the recipe explicitly; it is checked again against the manifest at prepare:

```json
{"output_mode": "regions",
 "label_regions": [["kidney_and_masses", [1, 2, 3]], ["masses", [2, 3]], ["tumor", [2]]],
 "regions_class_order": [1, 3, 2]}
```

The default region recipe is still Task07's. Prepare refuses it outside Task07: for KiTS23 it cannot reproduce label 3, and for LiTS its heads would be named pancreas/mass, so a LiTS region run must name the `liver`/`tumor` regions. In label mode, HRC's host and lesion channels must together cover every foreground label, so the defaults ([1] and [2]) are refused on KiTS23 until cysts are assigned (for example `"lesion_channels": [2, 3]`). Prediction checks outputs against the manifest's label values and copies undeclared source units only when the manifest policy allows them. The scratch Torch backend stays pancreas/mass only.

## Evaluation

`evaluate` scores the profile's regions in order; organ-only references score the host region only. `--pancreas-exclusive` exists for Task07 only. `compare --region` defaults to the reports' lesion region. Reports for LiTS and KiTS23 record `protocol.regions`, `protocol.lesion_region` and `protocol.geometry_policy`. Lesion-detection rows use the profile's wording (not "PDAC").

**Comparing with published numbers.**
- The headline region Dice is an equal-weight patient mean over reference-positive cases, so false positives on lesion-free scans (13 LiTS cases) never lower it. Each region summary also has `dice_nnunet_convention`: nnU-Net's `summary.json` case mean, in which a reference-empty case with a nonempty prediction scores 0 and only both-empty cases are dropped. Quote that value next to nnU-Net-based LiTS and KiTS23 numbers.
- `--surface-tolerance-mm official` uses the benchmark's per-region surface-Dice tolerances. Only KiTS23 defines them (`HEC_SD_TOLERANCES_MM` from the kits23 repository: kidney_and_masses 1.0331, masses 1.1329, tumor 1.1498 mm), and they are recorded under `protocol.surface_tolerances_mm`. Our region names `kidney_and_masses`/`masses` are the official `kidney_and_mass`/`mass`. A single number applies one tolerance to every region.
