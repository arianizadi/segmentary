# Star-convex lesion completion (STAR-C)

STAR-C is nnU-Net's ResEnc L with an object-level lesion decoder. Two small heads read decoder level 2. One finds lesion centres. The other regresses, from every lesion voxel, the lesion's extent in mm along 96 fixed directions. From each detected centre the rays are rendered differentiably into a soft star-shaped occupancy at full resolution. A learned gate adds that occupancy to the lesion and host logits, so a lesion that is found but partly absorbed into the host organ can be completed to its full extent. Read the [HRC guide](medical-hrc.md) first; STAR-C uses the same frozen plan, folds, initialization rules and checkpoint policy.

The claim being tested is narrow. Each lesion gets an explicit shape hypothesis with few degrees of freedom (a centre and 96 radii), rendered differentiably and fused through a gate into dense logits. The thesis claim is that this fixes the "lesion found but partly absorbed into the host" failure, and that logit calibration, post-hoc shape completion or auxiliary shape supervision alone do not reach the same gain. The star decoder itself is StarDist-3D plus CenterNet and is not claimed as new.

## Evidence that motivates it (S0, CPU, train and validation labels only)

Results are in `/data/izadia1/projects/segmentary-runs/pancreas/analysis-20261007/S0-premise/results/starc/starc_summary.json`.

| Test | Result | Kill rule |
| --- | --- | --- |
| Representability (240 mass components, inner centre, first-exit rays, star polyhedron) | median Dice 0.911 / **0.930** / 0.946 at R = 64 / **96** / 128; Dice < 0.80 for 1.7% / **1.3%** / 0.8% | median >= 0.90 and <= 20% below 0.80: passes at every R |
| Visibility from the inner centre | median 99.9% of component voxels visible; 81% of components >= 99% | |
| Centre validity (ResEnc L validation predictions, 35 matched lesions) | predicted inner point inside the reference lesion for 34/35; median 3.5 mm from the reference centre | >= 70%: passes |
| Upper bound: prediction ∪ GT-ray star from the predicted centre | +8.9 mass Dice points (95% CI 5.9 to 12.2) | >= +5: passes |
| Same from the GT centre (ceiling) | +20.3 points | |
| Post-hoc star completion of the prediction itself (no GT, LOO-tuned) | **-0.85** points (CI -1.5 to -0.3) | cheap baseline (b) |
| Grow predicted mass into predicted pancreas by d mm (LOO-tuned) | +0.34 points (CI -0.6 to +1.3) | cheap baseline (a) proxy |

R = 96 is chosen because 64 rays lose about 2 Dice points of representability and 128 gain only 1.5 points for 33% more ray outputs and targets. The two cheap baselines don't come near the +8.9 ceiling, so the gain has to come from learned rays, not from reshaping the existing prediction. The stage-0 gate passed, so the design below is implemented.

## Architecture

Notation: axes are the nnU-Net array axes (z, y, x). Spacing `s` is the plan's 3d_fullres spacing (2.5 x 0.8125 x 0.8125 mm for Task07). Positions are voxel indices; the physical position of index `i` is `i * s`. Every geometric quantity (directions, radii, Gaussians, box margins, temperature) is in mm, so anisotropy is handled by construction.

### Base network

`StarCResEncUNet` subclasses `ResidualEncoderUNet`, the same way `HRCResEncUNet` does. It keeps every ResEnc module name, the deep-supervision list and its order. New modules live under `starc.*`, so a ResEnc L state dict (or an nnFoundationCNN encoder) loads with only `starc.*` missing. The forward pass reimplements the decoder loop so it can keep two decoder outputs: level 2 (stride (2, 4, 4), 128 channels, a 28 x 80 x 64 grid at the full 56 x 320 x 256 patch) for the heads, and level 0 (32 channels, full resolution) for the gate.

### Heads at decoder level 2 (`starc_level`)

The level-2 cell `j` covers full-resolution voxels `[j*t, (j+1)*t)` with stride `t`. Its centre is voxel `j*t + (t-1)/2`, and this convention is used everywhere.

- **Centre head:** `Conv3d(128->64, 3^3) - InstanceNorm - LeakyReLU - Conv3d(64->1, 1)`. The logit `h` gives the heatmap `H = sigmoid(h)`. The last convolution starts with zero weights and bias `log(pi/(1-pi))` with `pi = 0.01`, so the heatmap is flat at 0.01. Nothing reaches the 0.15 proposal threshold before training, and the focal loss of an empty Task07 patch is 0.14. CenterNet's own bias of -2.19 would give about 150, which would dominate nnU-Net's gradient clip of 12.
- **Ray head (per voxel, StarDist-style):** `Conv3d(128->128, 3^3) - InstanceNorm - LeakyReLU - Conv3d(128->96, 1)`. It outputs `L`, the log-distance in mm to the lesion boundary along each of the 96 rays, measured from that cell. The last convolution starts with zero weights and bias `log(10 mm)`, so every star starts as a 10 mm polyhedral sphere rather than a random spiky star. The head is dense because then every core cell of a lesion is a training sample, and rays read at a centre a few mm off the inner point (the S0 median offset is 3.5 mm) are still trained values. Per-centre-only supervision would give about one sample per lesion per patch.
- **Rays:** 96 Fibonacci-sphere unit vectors in physical (z, y, x), the same set S0 used. The star surface is the polyhedron on these points (a convex-hull triangulation, 188 facets).

### Proposals

At inference, and in training steps without teacher forcing, proposals come from the heatmap:

1. Non-maximum suppression: a cell is a peak if `H == maxpool3d(H, 3, stride 1)` and `H >= centre_threshold` (0.15). The top `max_instances` peaks per sample are kept (8 for Task07, 16 to 32 for LiTS). The output shape is static, padded with score 0.
2. Sub-cell centre: a soft-argmax of `H` over the 3 x 3 x 3 neighbourhood gives the centre, converted to full-resolution voxels.
3. Rays: `L` is sampled trilinearly at that sub-cell position, giving `r_k = exp(clamp(L, log 0.5, log 90))` mm. Gradients reach the ray head through this sample.
4. Score `s_k = H(peak)`. The centre and the score are detached, so the segmentation loss never moves the heatmap.

**Teacher forcing.** In 50% of training steps (`teacher_probability`), the proposals are the ground-truth inner centres in this patch, each jittered by N(0, 2 mm) per axis in patch mm, with score 1. At most `max_instances` of them are rendered per sample (the largest first, as the targets list them), the same cap as proposals, so a teacher step never renders more stars than an inference step. Their rays still come from the predicted `L`, sampled at the jittered centre. This lets the gate and fusion learn to use a good prior before the centre head is reliable; the other 50% of steps match inference.

### Differentiable star rendering (full resolution)

For instance `k` with centre `c_k` (voxels), radii `r_k` (mm) and score `s_k`:

- **Box:** `c_k +- (max_r r_kr + box_margin_mm) / s`, clipped to the patch. `box_margin_mm` is 5. The rendering runs only inside the box.
- **Polar coordinates:** for voxel `x` in the box, `v = (x - c_k) * s`, `rho = |v|`, `u = v / rho`.
- **Star radius:** a precomputed 256 x 512 equirectangular table lists, for each direction bin, up to 6 candidate facets: those containing the bin's centre, edge midpoints or corners. The candidate with the largest minimum cone coordinate `lambda = M_f^-1 u` contains `u`; `lambda` is clamped to >= 0. Against an exact facet search, 1 in 200,000 random directions differs, by 0.012 mm on a smooth 10 mm star. The polyhedron radius is the weighted harmonic mean `R_k(u) = 1 / sum_a (lambda_a / r_ka)`, which is exactly the intersection of the ray with the facet plane. It is smooth in `r` and uses gathers only. S0 used the same polyhedron (`star_radius`); the test suite checks the two agree.
- **Occupancy logit:** `o_k(x) = (R_k(u) - rho) / tau`. The temperature is `tau = 0.5 + 4.5 * sigmoid(theta)`, so it is bounded in [0.5, 5] mm by construction and starts at 1.5 mm. The bounds stop the occupancy from becoming uniformly soft, or the boundary gradient from vanishing. The boundary is a continuous mm quantity, sub-voxel even in z at 2.5 mm.
- **Per-instance prior:** `P_k(x) = s_k * 6 * tanh(o_k(x) / 6)`. The score scales the magnitude and never flips the sign. A weak detection contributes almost nothing; it does not suppress its own interior.
- **Union:** `P(x) = max_k P_k(x)` over the instances whose box contains `x`. **Outside every box, `P = 0` and the box mask `B = 0`.** Areas without a detection get no prior, so a missed lesion or a tile without its centre is never suppressed (prior-art fix 2). Inside a box but outside the star, `P < 0`, which allows suppression of attached over-segmentation only in the ring around a detected lesion.
- **Memory and precision:** the facet lookup runs in chunks of `RADIUS_CHUNK` (2^18) directions, so its (N, 6, 3, 3) temporary stays near 56 MB even when a box spans the whole patch. Rendering runs with autocast disabled, so the geometry stays in fp32 (fp64 for fp64 radii) under mixed-precision training and inference. What autograd keeps is about 90 B per box voxel per star: on CPU, one saturated star (90 mm rays, a box covering the full 56 x 320 x 256 patch) peaked at 0.9 GB and eight at 2.8 GB, so the worst case is about 0.27 GB per star, at most `max_instances` (8) per sample.
- **Optional direction transform:** each instance can carry a 3 x 3 matrix `T` (default identity). Directions are looked up as `T u / |T u|` and radii divided by `|T u|`. This renders a star given in another frame exactly: a mirrored test-time-augmentation copy (diagonal +/-1), or ground-truth rays in an augmented patch.

### Gated logit fusion

```
h(x)   = LeakyReLU( Conv_1x3x3( concat(F0, P, B, z0) ) )     16 channels
g(x)   = sigmoid( Conv_1x1(h(x)) )
z_c(x) = z0_c(x) + w_c * g(x) * P(x)        for c in fusion_channels
```

- `F0` is the level-0 decoder features (32 channels). `z0` is ResEnc's own full-resolution logits, and the gate reads them detached.
- **Gate bias -2** (prior-art fix: -4 gives almost no gradient), with the last gate convolution's weights at zero, so `g = 0.119` everywhere at initialisation.
- **`w` is zero-initialised**, one scalar per fusion channel. With `w = 0`, `z = z0 + 0`, so STAR-C computes exactly what ResEnc L computes at initialisation, bit for bit on CPU, with or without deep supervision. `w` receives gradient `g * P * dL/dz` immediately, and the gate, `tau` and the ray head receive gradient through the fusion once `w` moves.
- **Fusion channels:** the lesion and host channels. For Task07 softmax these are mass (2) and pancreas (1); background is left out because softmax is shift-invariant. For KiTS23 regions they are `masses` and `tumor`, and for LiTS `tumor` and `liver`. Learning `w` per channel lets the network both add mass and remove pancreas inside the star, and do the reverse in the ring.
- Only the full-resolution output is fused. The deep-supervision outputs at coarser levels are ResEnc's.
- `fusion: aux_only` keeps the heads and losses but sets `P = 0`. This is cheap baseline (c), auxiliary shape supervision without fusion.

## Losses

`L = L_seg + lambda_c * L_centre + lambda_r * L_ray`, with `lambda_c = 1` and `lambda_r = 0.5`.

- `L_seg`: nnU-Net's DC+CE with deep supervision on the fused output. The recipe is otherwise unchanged.
- `L_centre`: the CenterNet penalty-reduced focal loss (alpha 2, beta 4) on `h` at level 2, in fp32. It is normalised by the number of positive cells in the batch, with a minimum of 1.
  - The target is the maximum over lesion components of a Gaussian at the component's inner centre (the mm-EDT argmax, as in S0), with `sigma = max(3 mm, 0.25 * equivalent radius)`, scaled into the augmented patch frame.
  - The cell containing an in-patch centre is exactly 1. A centre outside the patch contributes only its Gaussian tail and no positive.
- `L_ray`: L1 on log-distance over the valid rays of up to `ray_samples` (64) core cells per sample, plus every ground-truth centre in the patch (sampled from `L` at its exact sub-cell position, the same operation inference uses).
  - Core cells are cells whose centre maps into a lesion component with EDT >= 0.3 x that component's maximum. Each component present gets an equal share.
  - A ray is invalid, and masked out, if the true distance exceeds `max_ray_mm` (90).

## Full-volume ray targets

The prior-art review found that targets taken from the patch are wrong: a lesion cut by the patch edge gets the wrong centre, and its rays stop at the edge, which biases distances short. STAR-C never derives targets from the patch.

### Offline precompute (once per preprocessed dataset)

`scripts/precompute_star_targets.py` reads nnU-Net's preprocessed segmentations (`<case>_seg.b2nd`, or `_seg.npy`) at the plan spacing and writes one `<case>.npz` per case plus `manifest.json`. The trainer has no default folder: `configure_star(targets_dir=...)` must bind one, and backend runs bind a folder outside both workspaces (see [Running STAR-C through the backend](#running-star-c-through-the-backend)), because the backend hashes every file under `nnUNet_preprocessed`. The script refuses an existing output directory, an output inside the data folder, and any output under an `nnUNet_preprocessed`, `nnUNet_raw` or `nnUNet_results` folder or under a directory that holds `binding.json`, `plan-binding.json` or `campaign.json`. Writing into a frozen reference's cache would make every later import of that reference fail. The script only reads its inputs.

| Array | Content |
| --- | --- |
| `instances` | uint16 component labels (26-connected components of the union of `lesion_labels`), cropped to the bounding box of all lesion voxels plus a 2-voxel border |
| `crop_origin`, `shape`, `spacing` | the crop's origin in the preprocessed array, the full array shape, the plan spacing |
| `edt_mm` | float16 distance to the component boundary in mm (EDT of the zero-padded crop with `sampling = spacing`), 0 outside lesions |
| `centres` | float64 inner centre of each component, the `edt_mm` maximum, taking the plateau voxel nearest the component centroid (platform-independent) |
| `max_edt_mm`, `volume_mm3`, `equivalent_radius_mm`, `bbox_diagonal_mm`, `labels` | per component |
| `rays_mm` | float32, (K, 96): first-exit distances from the inner centre along the 96 rays in volume mm. The march uses steps of 0.25 x the smallest spacing and is refined by 6 bisection steps. These are the S0 representability rays at the preprocessed spacing. |

`manifest.json` binds the schema version, the plans file sha256, the configuration and spacing, `lesion_labels`, the connectivity, R, the sha256 of the direction set, the march parameters, the sha256 of `star_completion.py` and of the script, and for every case the sha256 of its source `_seg` file and of its `.npz`. Before it builds its data loaders, the trainer verifies:
- the manifest's sha256, when one is bound;
- the schema, R and the direction-set hash;
- the spacing and `lesion_labels`;
- the target method (`STARC_TARGET_METHOD`: connectivity, ray set name, centre rule, march step and bisections, crop border), so targets computed with other march settings are refused. The code hash is recorded but not enforced, since a refactor of `star_completion.py` does not change the targets;
- every training and validation case's `.npz` hash. The builder keeps these hashes, and every later load of a case (after the 32-case cache evicts it) is checked against them, so training never reads unverified target bytes;
- the hash of the case's `_seg` file in the trainer's own preprocessed folder, so the targets provably come from the segmentations being trained on. The test split is never in the preprocessed folder (`planning_scope: train_and_val_only`), and the script also refuses any case listed in `--forbid-cases-from` (the frozen split file).

### Patch targets in the augmentation workers

nnU-Net augments in voxel space: it crops a larger patch, then applies rotation (in-plane only for Task07, whose patch triggers dummy-2D augmentation), synchronised in-plane scaling of 0.7 to 1.4, and mirroring. A ray table stored in the volume frame therefore has to be transformed exactly into each augmented patch.

1. **Recording the frame.** `nnUNetTrainerStarC` swaps the classes of the top-level `SpatialTransform` and `MirrorTransform` in its training transforms for recording subclasses.
   - Without a resampling grid, `SpatialTransform` crops at `floor(centre) - patch // 2`. Otherwise the map is read off the exact `grid` it passes to `grid_sample`, which is affine without elastic deformation, using `q = (g + 1) * N / 2 - 1/2` (align_corners false).
   - `MirrorTransform` records its axes.
   - The data loader records the crop `bbox_lbs` and composes everything into one affine frame per sample: patch voxel `p` maps to volume voxel `x = J p + o`. In dummy-2D mode, z passes through unchanged.
   - Elastic deformation, or a spatial transform nested inside a random wrapper, is refused.
2. **Physical map.** `A = S J S^-1` maps patch mm to volume mm. It is a general linear map: nnU-Net's voxel-space rotation is not a physical rotation when spacing is anisotropic, and scaling is per axis.
3. **Centres:** `p_k = J^-1 (c_k - o)`. Gaussian widths are divided by `|det A|^(1/3)`.
4. **Rays:** for a sample point `x` and patch-frame ray `u'_r`, set `w_r = A u'_r`. The worker marches through the case's full instance map (not the patch) from `x * s` along `w_r / |w_r|` to the first exit `D_r` of the sample's own component, and the target is `D_r / |w_r|` patch mm. This is exact for any linear map.
5. **Output:** the loader returns per sample the level-2 heatmap, up to 64 + 16 ray sample positions in level-2 cell coordinates with (96,) log targets and validity masks, and up to 16 ground-truth centres in patch voxels. That is about 0.6 MB per sample, collated into `batch["starc"]`.

The validation loader has no spatial transform, so its frame is the crop. The tests push coordinate ramps through nnU-Net's own training transforms, in dummy-2D and in 3D mode and with forced rotation and scaling, and check that the recorded frame reproduces every in-bounds voxel to within 0.02 voxels. `StarCDataLoader` returns data and segmentation targets identical to the official loader for the same seed, under nnU-Net 2.8.1 and under master 47766ae3, which differ only in `load_case` and `get_bbox`.

**Measured on Task07** (HDRFS CPU, 2026-10-07, read-only strong-recipe preprocessed folder, 239 development cases):
- **Precompute:** 240 components, 2.3 s with 32 workers, 2.5 MB of targets. Manifest sha256 is `69451f75…c998`; the targets are in `/scr/izadia1/segmentary-round2-starc-20261007-logs/task07-starc-targets-r96`.
- **Representability:** rendering the stored rays back on the preprocessed grid gives median Dice 0.930 (p10 0.889), with 1.25% of components below 0.80. These are S0's numbers.
- **Loader cost:** with the real dummy-2D pipeline at the full 56 x 320 x 256 patch and batch 2, a batch takes 0.35 s instead of 0.20 s (median of 20 batches, one thread). Target building takes 0.093 s per sample (p95 0.12 s).

## Inference with sliding windows

`StarCPredictor` (in `nnunet_star_trainer.py`) replaces nnU-Net's sliding-window loop with two passes over the same tiles (`tile_step_size` 0.5, Gaussian weighting):

1. **Detect.** Every tile runs once without mirroring. Each tile peak is recorded in case voxels with its rays, its score and a centrality weight: nnU-Net's Gaussian importance at the peak, normalised to 1 at the tile centre.
2. **Case-level NMS.** Detections are sorted by `score * centrality`. A detection is dropped if its centre lies inside the star of an already-kept detection, or within `nms_radius_mm` (5 mm) of one. The survivors (at most `max_case_instances`, default 32, each with raw score >= `centre_threshold`) are the case's lesions. Each lesion is therefore described by the tile in which it is most central, and its rays come from that tile.
3. **Render.** Every tile runs again, with test-time mirroring if enabled. The network receives the case instances whose boxes intersect the tile, in tile coordinates. For each mirrored copy, the centres are mirrored and the direction transform is the matching +/-1 diagonal. A lesion cut by a tile border is still rendered completely inside each tile from its case-level centre, so tiles agree, and nnU-Net's Gaussian blending sees no seams from the prior. When more than `max_instances` boxes intersect a tile, the highest scores are kept.

Without `StarCPredictor` (for example nnU-Net's own final validation inside the trainer), each tile detects and renders its own peaks. That is consistent but less complete at tile borders. The two-pass mode costs one extra unmirrored forward per tile.

## Generality to liver and kidney lesions

- **Multiple lesions:** every component is a separate instance with its own centre, Gaussian, ray samples and box. The union is a max over instances. `max_instances` and `max_case_instances` are options; LiTS needs 16 to 32.
- **Label sets:** `lesion_labels` chooses the voxel labels that form instances: Task07 `[2]`, LiTS `[2]`, KiTS23 `[2, 3]` (masses) or `[2]` (tumour only). `fusion_channels` chooses the logits that are fused. Region datasets (KiTS23) use the region channels.
- **Spacing:** nothing assumes Task07's spacing. Isotropic plans (KiTS23 is about 0.78 mm in-plane and 1 mm in z) use full 3D rotation augmentation, which the recorded frame handles.
- **Non-star-convex lesions:** the fusion is additive and gated, so the voxel logits still cover parts that are not star-convex. S0 measures how often this matters: 1.3% of Task07 components reconstruct below 0.80 Dice. Run the same representability check on LiTS and KiTS23 training labels before their pilots.

## Options

Network options (bound into the plan as `starc_*` keywords):

| Option | Default | Meaning |
| --- | --- | --- |
| `rays` | 96 | number of Fibonacci rays |
| `level` | 2 | decoder level of the heads |
| `lesion_labels` | [2] | voxel labels forming instances (also used by the precompute) |
| `fusion_channels` | [1, 2] | logits receiving `w_c g P` |
| `fusion` | `gated` | `gated` or `aux_only` |
| `max_instances` | 8 | proposals per patch or tile |
| `centre_threshold` | 0.15 | minimum heatmap value of a peak |
| `box_margin_mm` | 5.0 | ring around the star where `P` may be negative |
| `min_ray_mm`, `max_ray_mm` | 0.5, 90.0 | ray clamp |
| `tau_init_mm`, `tau_min_mm`, `tau_max_mm` | 1.5, 0.5, 5.0 | boundary temperature |
| `gate_bias` | -2.0 | initial gate logit |
| `prior_scale` | 6.0 | tanh bound on `P` |
| `centre_hidden`, `ray_hidden`, `gate_hidden` | 64, 128, 16 | head widths |
| `ray_init_mm` | 10.0 | initial ray length |
| `centre_prior` | 0.01 | initial heatmap probability |
| `lut_shape` | [256, 512] | direction lookup table |

Training options (trainer attributes, bound by the backend): `centre_weight` 1.0, `ray_weight` 0.5, `teacher_probability` 0.5, `teacher_jitter_mm` 2.0, `ray_samples` 64, `max_gt_instances` 16, `core_fraction` 0.3, `sigma_min_mm` 3.0, `sigma_fraction` 0.25, `freeze_backbone` false.

## Cost

Only CPU has been measured. GPU memory and step time are not yet known. The GPU smoke must include the worst case, not just initialisation (10 mm rays, no peaks): saturated rays (`max_ray_mm` 90) with 8 forced proposals or teacher instances per sample, at batch 2 and the full patch.

- **Parameters:** 681,941 extra on 140,989,042 (+0.48%).
- The heads run on a 143k-cell grid.
- Rendering is bounded by `max_instances` boxes. A 20 mm lesion's box is about 16 x 56 x 56 voxels, and the worst case is the full patch.
- The gate is a 16-channel [1, 3, 3] convolution at full resolution.
- **Workers:** each sample adds one ray march, (64 + K) x 96 rays over the lesion's own extent, from a cached case table. This costs about 0.09 s per sample on one CPU thread (see above).
- **Inference:** two-pass prediction adds one unmirrored forward per tile, +12.5% with 8-way mirroring. The CPU smoke measured 53 s against 48 s.

## Required pilots and ablations (from the prior-art review)

1. **Stage 1:** freeze the Wave 1 ResEnc L checkpoint (`freeze_backbone: true`, `nnUNetTrainerStarCFinetune`), train the heads, gate and fusion, then run native validation inference. Kill if any of these holds:
   - the GT-centre ray reconstruction on validation has median Dice < 0.70;
   - the mass Dice gain is < +1.5 over the frozen backbone;
   - the median volume ratio does not move from 0.92 toward 1.0;
   - false-positive lesion components rise by more than 30%.
2. **Baselines:**
   - (a) a CV-tuned mass-versus-pancreas logit bias;
   - (b) post-hoc star completion (S0: -0.85);
   - (c) `fusion: aux_only`;
   - (d) dense SDF fusion (not implemented).
3. **Ablations:** fused versus aux-only, predicted versus ground-truth centres (`set_star_instances` with oracle centres), and teacher forcing on versus off.
4. **Mechanism metrics** per matched lesion: mass-called-pancreas fraction, pred/ref volume ratio, NSD, stratified by tumour-versus-pancreas contrast and by phenotype.

## Implementation

| File | Contents |
| --- | --- |
| `src/segmentary/medical/recipe_plan.py` | Torch-free options and plan transfer: `validate_starc_options`, `validate_starc_inference`, `transfer_starc_plan` (the `starc` branch of `transfer_plan`) and `check_starc_dataset`. `star_completion` re-exports them. |
| `src/segmentary/medical/star_completion.py` | Ray geometry (`star_geometry`, `StarGeometry.radius`). `march_exit_mm`. Offline targets (`compute_case_targets`, `save_case_targets`, `verify_star_targets`). Frames (`PatchFrame`, `compose_patch_frame`). `StarTargetBuilder`. Torch operators (`StarRenderer`, `detect_peaks`, `sample_cells`, `centre_focal_loss`, `ray_l1_loss`, `StarCompletion`). Case-level NMS (`merge_tile_detections`). Needs only NumPy, SciPy and Torch. |
| `src/segmentary/medical/nnunet_architectures.py` | `StarCResEncUNet`, defined lazily like `HRCResEncUNet`, with `set_star_instances` and `star_aux` |
| `src/segmentary/medical/nnunet_star_trainer.py` | Recording spatial and mirror transforms, `enable_frame_recording`, `StarCDataLoader`, `nnUNetTrainerStarC`, `nnUNetTrainerStarCFinetune` and `StarCPredictor`. Backend interpreter only. |
| `scripts/precompute_star_targets.py` | The offline target precompute and manifest |
| `scripts/starc_cpu_smoke.py` | End-to-end CPU check: synthetic data, targets, nnU-Net training steps and two-pass inference. Refuses to start unless `CUDA_VISIBLE_DEVICES=""` |

All new modules sit at the top level of `segmentary/medical`, so the backend's source binding (it hashes `medical/*.py`) covers them.

## Running STAR-C through the backend

STAR-C runs only on a frozen reference plan in the nnU-Net 2.8.1 runtime. The nnssl runtime has no STAR-C trainer and refuses it.

### Recipe fields

```json
{"architecture": "starc", "trainer": "nnUNetTrainerStarC",
 "reference_workspace": "...", "reference_plan_binding_sha256": "...",
 "starc_options": {},
 "starc_targets": "/data/.../task07-starc-targets-r96",
 "starc_targets_manifest_sha256": "...",
 "starc_inference": {"two_pass": true, "nms_radius_mm": 5.0, "max_case_instances": 32}}
```

- **Options.** `starc_options` and `starc_inference` are bound complete, with every default written out. Unknown keys fail. Both are refused for any other architecture.
- **Trainers.** `architecture: starc` needs `nnUNetTrainerStarC` or `nnUNetTrainerStarCFinetune`, and these trainers need `starc`.
  - `nnUNetTrainerStarC` is `nnUNetTrainer` plus the STAR-C losses, so a full-budget scratch `baseline` may use it. A baseline still takes no runtime overrides and no `initial_lr`.
  - `nnUNetTrainerStarCFinetune` keeps the rule of `nnUNetTrainerFinetune`: only a non-scratch `pilot` or `smoke` run.
- **Refused combinations:**
  - `deterministic: true`, because `grid_sample`, gather and index backward passes have no deterministic CUDA kernels;
  - `freeze_backbone` with a scratch backbone, or with `fusion: aux_only`, since neither changes the output;
  - region mode unless `fusion_channels` is declared, because the softmax defaults `[1, 2]` name other heads there.
- **Targets.** `starc_targets` is an absolute folder outside the run's own workspace and outside the reference workspace. `starc_targets_manifest_sha256` is required.
- **Warm start.** Warm-start and pretrained recipes use `init_allowed_missing_prefixes: ["starc."]`.
- **Initialisation.** The STAR-C modules are built without drawing from the global RNG. With one seed, the ResEnc modules of a STAR-C run get exactly ResEnc L's initial weights, as HRC's do.

### Targets: computed once, then bound

Compute the targets once per reference plan, on the reference workspace's own preprocessed data. The folder must be new and outside every workspace:

```bash
CUDA_VISIBLE_DEVICES="" nice -n 10 /data/izadia1/envs/pancreas-recipe-transfer-20260915/bin/python \
  scripts/precompute_star_targets.py \
  --preprocessed <reference>/nnUNet_preprocessed/Dataset707_Pancreas/nnUNetPlans_3d_fullres \
  --plans <reference>/nnUNet_preprocessed/Dataset707_Pancreas/nnUNetResEncUNetLPlans.json \
  --lesion-labels 2 --rays 96 --workers 32 \
  --forbid-cases-from <the frozen splits.json> --forbid-key test \
  --output /data/.../task07-starc-targets-r96
sha256sum /data/.../task07-starc-targets-r96/manifest.json
```

The reference's preprocessed folder holds development cases only, and `--forbid-cases-from` proves the held-out list was checked before any segmentation was opened. The backend checks the targets three times.

1. **Prepare** re-hashes the manifest and records `{path, manifest_sha256}` in `binding.json`.
2. **Plan** happens after the reference import (`recipe-transfer.json`, `changes`):
   - `starc_options` and `starc_outputs` record what the lesion labels and fusion channels mean in this dataset.json (`check_starc_dataset`).
   - `starc_targets` records `verify_starc_target_manifest`, which needs no Torch. The manifest must name:
     - the reference plan's sha256 from its frozen plan binding;
     - this plan's spacing, data identifier and configuration;
     - the bound rays and lesion labels;
     - a `--forbid-cases-from` check of this run's own split file with key `test`.
   - The manifest must list exactly the development cases. Each case's `_seg` file in the run's copy must hash to the manifest's value, and each `.npz` must hash to its entry.
   - The record also says whether the targets were computed with the current `star_completion.py`.
3. **Train** checks the binding again. Then `nnUNetTrainerStarC.get_dataloaders` runs `verify_star_targets`, which adds the ray-direction digest to the checks above.

### Train and predict

- **Before training.** The train worker calls `trainer.configure_star(training_options(starc_options), targets_dir=..., manifest_sha256=...)` before `initialize()`. `trainer-settings.json` records the training options, the target folder and hash, and the inference settings.
- **Prediction.** The backend's validation and `predict`, and `scripts/predict_medical_probabilities.py`, build the predictor with `backend.build_predictor`. For `starc` this is `StarCPredictor` with the run's bound `starc_inference`; every other architecture gets `nnUNetPredictor`. Prediction still loads the trained network through `initialize_predictor` and `manual_initialization`.
- **Source check.** For STAR-C runs, the probability exporter also requires `star_completion.py`, `nnunet_star_trainer.py` and `recipe_plan.py` to be byte-identical to the trained run's code. Other runs are checked only against the files they import, so an HRC or fine-tune run trained before STAR-C still exports.

### Planners

**Warm-start screens** use `scripts/plan_medical_seed_folds.py`:

```bash
python scripts/plan_medical_seed_folds.py ... \
  --arm A=resenc --arm S=starc --arm F=starc:frozen --arm X=starc:aux_only \
  --run 2:0:0:A --run 3:0:0:S --run 4:0:0:F --run 5:0:0:X \
  --starc-targets /data/.../task07-starc-targets-r96 --starc-targets-sha256 <manifest sha256>
```

- **Arms.** `starc` is gated and fully trainable. `starc:frozen` sets `freeze_backbone` (the Stage-1 pilot). `starc:aux_only` is cheap baseline (c).
- **Recipe.** Every STAR-C arm trains `nnUNetTrainerStarCFinetune` with the `starc.` prefix allowlist.
- **Comparison.** STAR-C arms share the fold's `warm_start` comparison group with the ResEnc L and HRC arms.

**Region arms** use `scripts/plan_medical_round2_arms.py regions`:

- **Arms.** `--arm NAME=starc[:aux_only]` adds full-budget scratch STAR-C region arms.
- **Recipe.** They train `nnUNetTrainerStarC` with `fusion_channels` [0, 1] (the pancreas and mass heads) and `lesion_labels` [2]. They take the same `--starc-targets` options.

**Checks.** Both planners check the targets against the reference workspace from its plan-binding hashes, without opening any payload. `run_medical_campaign.py` re-checks each STAR-C recipe's options, trainer, inference settings and targets, and re-hashes the manifest, every time it loads the spec.

**Not planned.** Scratch STAR-C in label mode (the counterpart of a Wave 1 run) has no preset yet, and neither does scratch HRC. Such a recipe is accepted by the backend and can run in a campaign without a preset.

## Tests

- `tests/test_medical_star_completion.py` (no nnU-Net):
  - options, plan transfer and dataset checks;
  - the lookup table against the exact polyhedron;
  - ray targets on a sphere, an ellipsoid and a non-star-convex horseshoe;
  - several lesions, file round trip and verification;
  - frame composition, and patch targets under identity, cut, scaled, rotated and mirrored frames;
  - the soft star against the hard star, zero outside boxes, and the union of instances;
  - mirrored rendering;
  - `gradcheck` of the renderer in float64;
  - peaks, losses, the identity at initialisation, fusion gradients and aux-only mode;
  - NMS and the precompute script.
- `tests/test_medical_starc_architecture.py` (dynamic-network-architectures):
  - bit-for-bit ResEnc L equality at initialisation, with and without deep supervision, with stars rendered;
  - state-dict superset and parameter overhead;
  - construction from the plan and through nnU-Net;
  - CPU forward/backward on the Task07 ResEnc L plan at 16 x 128 x 128 with star losses on augmented multi-lesion targets;
  - inference proposals rendering three lesions.
- `tests/test_medical_star_trainer.py` (nnU-Net):
  - the recorded frames against nnU-Net's transforms;
  - loader equality with nnU-Net's loader;
  - tile instances under mirroring;
  - the end-to-end CPU smoke.
- `tests/test_medical_backend_starc.py` (no nnU-Net):
  - recipe binding and every refused combination;
  - trainer resolution and the predictor factory;
  - the plan stage on a frozen reference in label and region mode;
  - target refusals: wrong rays, labels, spacing or plan, a missing held-out check, case sets, and segmentation or target hashes.
- `tests/test_medical_starc_plan.py` (no nnU-Net): warm-start and region STAR-C arms, refusals while planning, and the runner's re-checks of recipes and the target manifest.
