# First controlled recipe round

Launched on HDRFS on September 14, 2026. These are six fresh scratch DynUNet runs, each with its own immutable workspace. Read the [live comparison](README.md) for current progress and scores; this page records the launch protocol and completed checks.

The question is whether patch selection or simple augmentation improves our starting recipe. This is an ingredient screen, not a reproduction of any paper or a claim of clinical performance.

## What is being compared

| Arm | Change from the same-seed control |
| --- | --- |
| control | Legacy uniform-volume/foreground center sampling and flips |
| mass50 | Uniform-volume/pancreas/mass center probabilities 0.25/0.25/0.50 |
| class111 | Exact background/pancreas/mass class-center weights 1:1:1 |
| class115 | Exact background/pancreas/mass class-center weights 1:1:5 |
| rotation | Legacy sampler/flips plus axial rotation, probability 0.25, from −15° to +15° |
| intensity | Legacy sampler/flips plus normalized-image scaling, probability 0.5, factor 0.9–1.1 without further clipping |

The class111/class115 pair isolates class weights. Either class-center arm also changes background selection relative to control, because a uniform-volume center may lie on any class. All runs start at seed 0. Added sampling/augmentation draws can change the subsequent crop sequence; this is not a test using identical patches under every arm.

Fixed across all six: 197 training scans, 42 validation scans, 42 reserved test scans; 96³ patches; 1.5/1.5/2.5 mm xyz spacing; HU [−100,240] mapped to [0,1]; batch 8; BF16; DynUNet with 16,543,683 parameters; AdamW learning rate 0.0003, weight decay 0.00001, polynomial decay; dense cross entropy plus foreground Dice; 10,000 updates / 80,000 sampled patches. Native validation is at 100 updates, then every 1,000. The highest mean per-case validation mass Dice selects the best checkpoint. Inference batch 8 and 50% sliding-window overlap stay fixed.

The new campaign uses GPU lanes 1–6. The original nnU-Net run remains a separate comparator on GPU 0. The shared training cache avoids making one volume copy per recipe.

## Training-only input audit

The audit processed all **197 training scans**, drawing 8 crops per scan per arm (1,576 per arm). Validation and reserved-test image/label payloads were not opened by this audit. These are equal-per-case diagnostics, not a log of every optimizer crop.

| Arm | Selected mass centers | Patches containing mass | Mean mass voxel fraction |
| --- | ---: | ---: | ---: |
| control | 24.81% | 56.73% | 0.130% |
| mass50 | 49.94% | 76.02% | 0.198% |
| class111 | 33.76% | 70.05% | 0.168% |
| class115 | 71.64% | 87.37% | 0.239% |
| rotation | 23.67% | 58.63% | 0.122% |
| intensity | 25.25% | 57.36% | 0.117% |

Native mass-positive training scans: **197**. Entire positive cases losing all mass voxels during resampling: **0**. Native 26-connected mass components: **198**; components with no surviving resampled voxels: **0**. Components are voxel-connectivity proxies, not independently annotated tumors.

See [input-audit.json](input-audit.json) for aggregate crop counts, physical-volume ratios, execution/package/source hashes and complete recipe settings. Per-case ordinal diagnostics remain on HDRFS; no CTs, masks or scan identifiers are published here.

## Full-size GPU feasibility checks

Every arm passed raw-versus-cache sample and RNG parity on three training scans chosen by native volume size, then completed three warmup and five measured full-capacity optimizer updates with finite losses. These diagnostic weights were discarded. Every arm used about 7.61 GiB peak allocated and 10.50 GiB peak reserved CUDA memory.

| Arm | CPU sample time / batch, seconds | Synchronized whole-step time, seconds |
| --- | ---: | ---: |
| control | 0.0085 | 0.2441 |
| mass50 | 0.0084 | 0.2443 |
| class111 | 0.0088 | 0.2458 |
| class115 | 0.0085 | 0.2442 |
| rotation | 0.0816 | 0.3186 |
| intensity | 0.0093 | 0.2451 |

These five-step spot checks synchronize each stage and do not overlap CPU prefetch with GPU compute. They measure feasibility and the added rotation cost, not campaign throughput or model quality. The actual training runs keep batch prefetch enabled; use their measured wall time and native-volume latency for comparisons.

The control also completed native-volume inference on a training scan. Batch 1 versus batch 8 differed in 1,202 of 9,699,328 argmax voxels (about 0.0124%) after only eight diagnostic updates. This does not establish numerical identity between inference batch sizes; the campaign keeps batch 8 fixed for every arm. No quality score was computed from this diagnostic scan.

Complete timings, measured losses, package/GPU metadata and parity flags are in [gpu-profiles.json](gpu-profiles.json).

## Verification and source identity

[GitHub Actions passed](https://github.com/arianizadi/segmentary/actions/runs/34873634167) for `40989e648fdaf1afbf3b2bfc215f5ad79de4a720`. The first CI run exposed only the repository documentation rule against the plus/minus symbol; the range was spelled out and CI rerun. The frozen scientific checkout remains `9714becaed028d7f0b03e1cf1782f68eb8c52853`. [Code-equivalence evidence](ci-code-equivalence.json) verifies that the CI revision differs only beneath docs/ and that source, scripts, tests, configs, workflows and project metadata are identical.

Full CI passed **2,336 tests**, with 4 skipped and 41 excluded by the GPU/slow test markers. Local targeted verification passed 148 tests with one GPU-specific skip, plus the campaign/report/dashboard suites. Interrupted-versus-uninterrupted CPU worker tests cover legacy and combined class sampling/rotation/intensity with prefetch on/off, comparing exact weights, AdamW moments, scheduler/scaler and recorded RNG state. The server GPU checks above are separate evidence.


At the 2026-09-14T17:31:45.911930+00:00 [startup snapshot](startup-status.json), all six runs had passed 200 updates with finite losses, zero external weight loads and one shared initial-weight hash. Epoch-2 training throughput was about 4.4 updates/second for every arm, including rotation, with prefetch enabled. Each retained two checkpoint generations. These early observations are not final accuracy or runtime estimates.

## Checkpoints, dashboard and reports

The ordinary campaign runner creates the shared training dashboard. Its owned panes close after successful completion; failure evidence and user-added panes are retained. Each run retains its latest and selected best checkpoint generations. A same-recipe interruption resumes full state from latest; this new recipe round imports no historical checkpoint.

After all six complete native validation prediction/evaluation, a finite post-run operator runs verified B1 inference benchmarks (10 warmup, 50 measured forwards), fixed-protocol clinical diagnostics, and ten paired Dice bootstrap contrasts against control. It publishes aggregate Markdown/JSON and exits. Existing source, dataset and checkpoint artifacts remain on HDRFS.

The generated pages report mass Dice, pancreas-union Dice, sensitivity proxies, timing, memory and inference throughput for every arm. The paired comparison page is added after post-processing finishes. P-Sen and connected-component T-Sen remain exploratory label-based measures. Specificity and patient ROC AUC are unavailable because this validation cohort contains no verified negative cases.

## How to use the result

Wait for all six complete 42-scan native evaluations before ranking the arms. A promising ingredient should be tested with additional seeds and on U-Mamba Encoder and MedFormer. Resolution, deep supervision, optimizer/schedule changes and inference changes remain separate experiments in the [research plan](../recipe-comparison-20260914/experiments.md).

One seed and repeatedly inspected validation data do not establish a general improvement. Pointwise paired confidence intervals do not account for selecting the best arm or training-seed uncertainty. Patient linkage remains unverified at the dataset-case grouping level. The reserved test stays untouched until the protocol and provenance audit are fixed.

See the [operator guide](../../../../guides/medical-recipe-ablation.md) for reproducible planning, auditing and runner commands.
