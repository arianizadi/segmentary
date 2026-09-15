# Cascade validation failure and recovery

Final verification found both original crop experiments had failed in their first validation pass, after 100 optimizer updates. The last durable checkpoints were still at step 0. This was an execution error, not a measured segmentation result.

The inference cache had reduced an audited case to only its image path. The frozen crop lookup also requires `case_id` and `image_sha256`, so it raised `KeyError: 'case_id'`. The corrected implementation retains an explicit allowlist of image identity and geometry fields. It still excludes all reference-label fields during inference. A related handoff in the native inference profiler was corrected too.

ROI cache keys now include case identity in addition to image and pipeline hashes: identical image bytes must not share a cropped cache entry when two manifest aliases have different fixed boxes. Cached and uncached predictions are tested on the full native grid, including background outside the crop.

## Evidence

- Corrected source: `993e6413341dbc5c39ec46cdf5f846e246215b4f`.
- All 96 focused viewer, inference-cache and profiler tests passed; lint, formatting and types passed.
- The corrected source passed the complete [GitHub Actions checks](https://github.com/arianizadi/segmentary/actions/runs/34920147942) on `segmentary-linux`; the [CI receipt](followup-ci.json) pins the tested commit and completion time.
- One real validation CT was preprocessed using each of the existing 20 mm and 40 mm predicted crops. Cached arrays and affines matched direct preprocessing exactly, including a reopened disk-cache read. No reference-label payload was read for this check.
- All three replacement runs subsequently completed their first 100 updates, validated all 42 full native volumes and committed checkpoints. The [first-validation receipt](recovery-first-validation.json) records complete coverage and cache verification counts for each run.
- The complete earlier crop audit retained all 42 validation cases: neither margin completely excluded a lesion; each partly excluded one lesion. That audit does not establish stage-two segmentation accuracy.
- The original failed workspaces, checkpoint bytes, source snapshot, ROI manifests and records were retained.

## Replacement experiment

The [replacement cascade campaign](../cascade-recovery-20260914/README.md) starts three fresh seed-0 runs on GPUs 2, 3 and 4: full-CT control, ROI +20 mm and ROI +40 mm. Its new matching control preserves the registered three-arm comparison under the corrected source. The scientific recipes, original split and frozen predicted crop manifests remain the same.

This is a restart from scratch, not a resume of the lost first 100 updates. Each run keeps its own 10,000-update schedule, checkpoint lineage and normal dashboard/reporting behavior. The active Swin and nnU-Net jobs retain their original frozen source.

The recovery dashboard is available on HDRFS with `tmux attach -t state-controller-6d4943f172`. Its owned training panes are removed when the campaign reaches a terminal state.

The review-page follow-up starts on a case with exported panels and adds a **Has image panels** filter while keeping all 42 cases available. The local `review-ready.html` uses the original report evidence; no real reviewer decisions or annotations were entered during browser checks.
