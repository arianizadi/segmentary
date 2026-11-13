## VERDICT: APPROVE — launch as an explicitly provisional scene-grouped benchmark

I found no blocking defect in the code, configs, split proposal or input manifests. I ran nothing: the "13 CPU tests pass" claim is unobserved (I counted 13 cases in the file), and HDRFS source configs, live GPUs and the materialized dataset are unverified. I wrote no files, including no plan file.

## What I confirmed by reading

- **Split (candidate 0):** block sizes sum to 187 / 68 / 59 (11 / 5 / 4 blocks). Every documented look-alike (0252, 0183↔0228, 0250, 0251/0253–0261) sits inside the 51-image validation block or in train. No documented relation crosses train↔test.
- **Builder:** enforces source-audit hash, exact ordered taxonomy, mask pixels and dimensions, encoded and decoded duplicates, annotation bytes, must-link, train pins, small-image census, block count and dominance, mask-derived support equal to the candidate, and refuses to overwrite.
- **Loader compatibility:** the new `splits.json` metadata keys are skipped by `src/segmentary/data/folder.py:143`, and groups are disjoint across splits.
- **Launch gates:** allowlist and queue order are validated before GPU inventory at init and again before every job. Host locks are held for the worker's life and match `scripts/run_rad_test.py:144-151`. A busy GPU leaves the job queued, and the launcher restarts the worker within 30 s.
- **Initializers:** `model.checkpoint` (allowlisted) and `init_from` (exact match) are the only weight-loading routes in `ModelConfig`/stage config. All 10 HF IDs in the 41 model configs are in the approved set. The manifest has 108 rows with no RAD/RTIS path.
- **Priority file:** 149 jobs. Four rows I spot-checked against `rad-comparison.csv` match (fixed-grouped, final, all, 18 classes).
- **Final checkpoint:** standalone eval, diagnostics match, profile and collection check all key on `last.ckpt`. `curriculum.py:658-665` emits `budget_complete`. No inference on test; test files are only hashed for integrity.

## Non-blocking findings

1. **Smoke dataset is not bound to main.** `scripts/validate_rtis_launch.py:145-175` checks code SHA and GPU subset only. Fix: also require equal `split_sha256` and `dataset_audit_sha256`, or compare the two `campaign.json` files by hand.
2. **Smoke skips two main-only paths.** These are the runtime queue-priority check and the full-split exact confusion match (`collect_rtis_statistics.py:407-410`; smoke passes `--limit-per-split 2` at `run_rtis_full_campaign.py:113-114`). A mismatch would surface only after the first 4000-step jobs, as terminal `failed`. Check the first completed job before leaving the fleet unattended.
3. **Input file placement.** Init needs a fully clean tree (`run_rtis_campaign.py:179`) and `tmp/` is not ignored.
   - Use the tracked `configs/campaigns/rad_2026_11_allclasses.priority.json` and `configs/datasets/rad_2026_11_allclasses.split.json`; confirm they are byte-identical to the `tmp/` files (I could not hash them).
   - Keep `source-checkpoints.json` outside the checkout and outside `--out`.
   - Both paths are frozen and re-hashed before every job, so moving them stops workers.
4. **Manifest identity and count are not asserted.** `plan_rtis_campaign.py:283-287` pins whatever file is passed, and `verify_rad_initializers.py:183-190` only reports counts. Confirm `initializer_verification` shows 108 endpoints, 108 transfer jobs, 41 recipe jobs and the reviewed manifest SHA.
5. **City→Rail chain check is string equality.** `verify_rad_initializers.py:114-119` compares paths, while City configs come from `rail20-b9eb3e1/accepted/` and City checkpoints from `a7c0b67/jobs/`. If it fails on HDRFS, compare file SHA-256 rather than relaxing it.
6. **Foreign-workload attribution may fail closed.** `validate_rtis_launch.py:122-126` accepts only absolute tokens with `/projects/`, `/.venv/` or `.py`. A VFS job started as `python -m …` from a conda env would block validation. Do not bypass it; add affirmative evidence instead.
7. **Idle gate is cooperative and strict.** `launch_requirements.py:187` needs 0% utilisation and ≤64 MiB. A higher host baseline starts nothing, which the smoke will show. Non-cooperating processes can still race the check.
8. **Builder gaps.** The reviewed proposal hash is not pinned, and constraints apply only if present in the proposal (`prepare_rad_allclasses.py:93-134`; all are present now). There are no negative tests for the miscellaneous/mud pins, small-image census or duplicate images.
9. **Stale text.** Draft comments in both YAMLs, the "pretrained initializer" label on transfer jobs in the priority file, and `docs/guides/rad-2026-11-allclasses.md:161-165`. Update before the frozen commit.

## Caveats that must accompany reporting

- **Grouping:** scene groups are visual inference; no recording IDs.
- **Validation concentration:** 51 of 68 images are one block, exactly at the 75% cap, and one of the five blocks is a single image. Initialization choice is largely a one-recording-family decision.
- **Validation independence:** the Vmax overlay appears in `sunny-mainline-cab-view` (train) and the validation block. `overcast-mountain-stations` (test) may share a line with the validation block; that is my inference.
- **Unknown train recordings:** 22 miscellaneous train images have unknown recordings, so overlap with test cannot be excluded.
- **Thin held-out classes:**

  | Class | Test | Validation |
  |---|---|---|
  | mud-pumping | 17 images, all from `rural-overcast-cab-view` | 12 images, 359k px (train has 63.6M px) |
  | standing-water | 5 images, one scene | 7 images |
  | person | 5 images, 24k px | 20 images |
  | vegetation-overgrowth | 8 images | 30 images |

  These classes weigh equally in the 21-class mIoU, so rank gaps of a few points across 41 models are not resolvable. Report per-class support.
- **Not a pristine holdout:** the historical test was already inspected and 119 images changed split.
- **Scheduling evidence only:** queue order comes from old 18-class scores.
- **Protocol:** single seed, fixed 4000 steps, final checkpoint primary, best-on-val secondary.
- **Selection:** one initialization per model by final positive-image mIoU over 21 validation classes, frozen and hash-pinned before any test scoring. False alarms on class-negative images are reported separately. I did not review the selection or test-phase scripts.
- **Initializers:** five models are recipe-only. Recipe weights can include public segmentation pretraining (ADE/VOC).
