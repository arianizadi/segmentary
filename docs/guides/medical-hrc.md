# Host-referenced calibration (HRC-ResEnc)

HRC-ResEnc is nnU-Net's ResEnc L with a small, zero-initialised module in the decoder. The module compares each voxel with this patient's own host tissue (pancreas for Task07, liver or kidney for the transfer benchmarks), so the lesion decision is made relative to the patient instead of to a fixed intensity scale. Read the [cross-validation guide](medical-cross-validation.md) and the [strong recipe guide](medical-strong-recipe.md) first; HRC runs use the same frozen plan, cache import, folds and checkpoint policy.

## What the module computes

All statistics use the CT-normalised input, so one unit is one plan foreground standard deviation (71.16 HU for Task07).

1. **Host weights.** The network's own coarse deep-supervision logits are detached and turned into probabilities on the statistics grid G (`stats_level`, default level 2 = 5 x 3.25 x 3.25 mm for Task07). G is fixed whichever blocks run, so box sizes always count level-2 cells. The host weight is `w = p_host^2 * (1 - p_lesion)`. In region mode, `p_host = sigmoid(R) * (1 - sigmoid(M))`. `host_channels` and `lesion_channels` choose the output channels.
2. **Gland reference.** A per-patch weighted location and variance, refined by three IRLS iterations with Huber weights (k = 1.5) on residuals scaled by `sqrt(var + sigma0^2)`. Ten prior cells at the dataset foreground mean (0) with a parenchymal-scale variance (`gland_prior_sd_hu`, 15 HU) keep the estimate defined when a patch contains no predicted gland. The prior is not part of the plan's specification. A foreground-scale prior variance (71 HU) would inflate a 12 HU gland's sigma by 21% at full coverage and by about 2.6 times at 100 cells; at 15 HU the inflation stays below 10%.
3. **Annular local reference.** The robust weights `w * psi(r)/r` are summed in a 9 x 17 x 17-cell box minus a 3 x 7 x 7-cell core (45 x 55 x 55 mm minus 15 x 23 x 23 mm), with separable fp32 box sums that count only voxels inside the patch. The local mean and variance shrink toward the gland values with 50 prior cells.
4. **Deviation tensor X (24 channels)** at each HRC level: local z, |local z|, smoothed local z and its absolute value, gland z, |gland z|, support `Box(w)/Box(1)`, log local variance, and 16 channels of feature deviation from a learned 1x1 projection of the decoder features. `sigma0` is 5 HU divided by the plan foreground std.
5. **FiLM injection.** `F' = F * (1 + gamma) + beta`, with `(gamma, beta)` from `Conv1x1(LeakyReLU(IN(Conv3x3x3(X))))`. The last convolution starts at zero, so at initialisation HRC-ResEnc computes exactly what ResEnc L computes.

Blocks run at levels 2, 1 and 0, after each decoder stage and before its segmentation head. The level-2 block reads the level-3 head; levels 1 and 0 read the post-HRC level-2 head (the plain level-2 head when `levels` omits 2). These two heads always run, also with deep supervision off. Everything else is ResEnc L: the same module names (the state dict is a superset), the same deep-supervision list, and the same loss, sampler, augmentation and optimiser.

Reference statistics are computed per sliding-window tile at inference. A case-level two-pass reference is not implemented.

## Plans and recipes

`transfer_plan(plan, "hrc", options)` keeps every ResEnc keyword, sets the network class to `segmentary.medical.nnunet_architectures.HRCResEncUNet`, and adds `hrc_*` keywords. A recipe selects it with:

```json
{
  "architecture": "hrc",
  "hrc_options": {"reference_mode": "robust"},
  "reference_workspace": "/frozen/resenc-l-reference",
  "reference_plan_binding_sha256": "<sha256>"
}
```

The backend validates `hrc_options` and binds the complete option set, defaults included, in the workspace binding. Unknown options fail. The options are `levels`, `stats_level`, `reference_mode`, `output_mode` (`softmax` or `regions`), `host_channels`, `lesion_channels`, `image_channel`, `feature_channels`, `hidden_channels`, `outer_box`, `inner_box`, `smoothing_box`, `stats_smoothing_box`, `shrinkage_cells`, `gland_prior_cells`, `gland_prior_sd_hu`, `robust_loss` (`huber`, or `tukey` with an explicit `robust_k`, for example 4.685), `robust_k`, `irls_iterations` and `sigma0_hu`.

When planning, the backend checks the channels against the dataset's `dataset.json` and records the result as `hrc_outputs` in `recipe-transfer.json`. Softmax mode needs a label dataset, and the channels must be foreground labels. Region mode needs nnU-Net regions (`regions_class_order`), explicit `host_channels` and `lesion_channels` with one region each, and a host region that strictly contains the lesion region. For KiTS23 that means host `masses` (channel 1) and lesion `tumor` (channel 2).

HRC refuses `deterministic: true`, because its feature path differentiates through `avg_pool3d` and trilinear interpolation, and PyTorch has no deterministic CUDA backward for either. HRC gradients are therefore nondeterministic, like standard nnU-Net GPU training.

`reference_mode` is the ablation switch:

| Mode | Reference |
| --- | --- |
| `robust` | Default: robust gland and shrunk annulus |
| `masked_mean` | Plain weighted mean and variance, no robust reweighting |
| `gland_only` | Local reference replaced by the gland reference |
| `local_only` | Gland-level deviation channels set to zero |
| `unmasked_lcn` | All weights 1: generic local contrast normalisation (pilot arm C) |
| `features_only` | Intensity channels set to zero |
| `hu_only` | Feature-deviation channels set to zero |
| `none` | X = 0; FiLM can learn only a per-channel affine |

For the reference-swap and zeroing tests, set `network.capture_reference = True` to keep the last references (`coarse` and `refined`) and `network.reference_override = fn(name, reference)` to replace them. Both refuse to run in training mode.

## Trainer, initialization and pilot budget

New recipe fields, all bound in the workspace binding:

- `trainer`: `nnUNetTrainer` (default) or `nnUNetTrainerFinetune`. The fine-tuning trainer keeps the full nnU-Net recipe and changes only its defaults to learning rate 1e-3 and 150 epochs; `initial_lr` overrides the rate and is accepted only for this trainer. It requires a non-scratch `pilot` or `smoke` run, and a `baseline` always uses `nnUNetTrainer`. The seed/fold preset also pins the scratch trainer, initialization and options. nnU-Net cannot find a Segmentary trainer by name, so the backend constructs it directly and loads it for prediction through `nnUNetPredictor.manual_initialization`. The model folder is `<trainer>__<plans>__<configuration>`.
- `purpose: pilot` allows a `num_epochs` override and nothing else; every epoch keeps 250 updates. `baseline` still allows no overrides.
- `initialization`: `scratch` (default), `warm_start` or `pretrained`. Non-scratch runs need an absolute `init_checkpoint` outside the workspace and its `init_checkpoint_sha256`. `init_allowed_missing_prefixes` (for example `["hrc."]`) lists the only modules that may be absent from the checkpoint. Prepare and train verify the hash. The worker hashes and deserialises the same bytes after `trainer.initialize()`, refuses unexpected keys, missing keys outside the allowlist and shape mismatches, loads with `strict=True`, and writes `initialization-origin.json` with the missing keys and a hash of the initial weights. The optimiser state is not loaded: the epoch counter and poly schedule restart at 0. Resume requires the run's own origin record.
- A `warm_start` checkpoint must be one listed in the checkpoint index of a Segmentary nnU-Net workspace that trained the same dataset, manifest, split, CV manifest and fold. Prepare and train enforce this, so a hand-written recipe cannot start fold k from a checkpoint that trained on fold k's validation cases. The source workspace, fold and seed are recorded in `binding.json` under `initial_checkpoint.source`. A `pretrained` checkpoint must not come from a Segmentary workspace.

## Warm-start pilot campaigns

```bash
python scripts/plan_medical_seed_folds.py \
  --source-root /frozen/checkout --campaign-dir /campaigns/task07-hrc-pilot \
  --python /envs/harness/bin/python --nnunet-python /envs/nnunet/bin/python \
  --manifest ... --splits ... --cv-splits ... --reference-workspace ... \
  --arm A=resenc --arm B=hrc --arm C=hrc:unmasked_lcn \
  --run 2:0:0:A --run 3:0:0:B --run 4:0:0:C ...
```

Each `GPU:FOLD:SEED:ARM` run starts from `--init-checkpoint-pattern` (default: the Wave 1 `nnunet_resenc_l-fold{fold}-seed{seed}` `checkpoint_final.pth`). The planner requires that checkpoint to exist and binds its sha256. It also checks that the source run is a completed scratch ResEnc L run of the same fold, seed, CV manifest and plan (the same reference plan binding, and a plan file that parses to the reference plan, because importing a reference re-serialises the plan bytes), and that its checkpoint index lists the same hash, so no fold's validation cases were seen by its initial weights. Runs use `nnUNetTrainerFinetune`, `purpose: pilot`, 150 epochs (37,500 updates) and learning rate 1e-3 by default.

The campaign runner accepts a non-scratch recipe only in a comparison group whose name carries the tag `warm_start` or `pretrained`, and refuses that tag on scratch runs. Warm-start campaigns use one group per fold and seed (`warm_start_fold<k>_seed<s>_<steps>_steps`). The runner re-checks the arms, budget and checkpoint hashes when it loads the spec, binds the checkpoints in `campaign-binding.json`, and re-hashes a run's checkpoint before its train stage. The reporter ranks only within a group, never ranks a group whose members differ in initialization or initial checkpoint, and requires each member's origin record to match its bound checkpoint.

## Out-of-fold probability export

`scripts/predict_medical_probabilities.py` exports native-space softmax probabilities from trained workspaces without writing to them:

```bash
python scripts/predict_medical_probabilities.py \
  --member /campaigns/wave1/campaign.json::nnunet_resenc_l-fold0-seed0 \
  --member /campaigns/wave1/campaign.json::nnunet_resenc_l-fold0-seed1 \
  --checkpoint checkpoint_final.pth --partition val \
  --device cuda --gpu 3 --output /analysis/oof-fold0
```

It verifies each member's binding, plan, runtime, checkpoint index and checkpoint hash. It never locks or writes the workspace: it copies the checkpoint and the trained `plans.json` and `dataset.json` into `models/<run>/`, checks the copies against the verified hashes, and predicts from the copies. A runner that is still predicting into the same workspace is therefore never blocked. It refuses test cases and any case in a member's training fold, and requires a Segmentary network's source files to match the run's training source. Each member's `.npz`, `.pkl` and `.nii.gz` go to `members/<run>/`. Two or more members on the same fold are averaged in probability space into `ensemble/`. `--mirroring` turns on nnU-Net's mirroring test-time augmentation. `provenance.json` records the members, checkpoints, settings and the hash of every output file.

## Smoke test

`scripts/hrc_gpu_smoke.py --plan <nnUNetResEncUNetLPlans.json> --gpu N --output <fresh.json>` builds both networks through nnU-Net and checks fp32 equality at the full patch with deterministic cuDNN kernels (fp16-autocast equality is reported too). It then switches to the production settings (`cudnn.benchmark` on, deterministic off), times fp16-autocast inference forwards, and trains each network for 200 updates with nnU-Net's optimiser, gradient clipping and loss on synthetic patches. It reports step time, peak memory, gradient norms per group (ResEnc base, HRC FiLM, other HRC) with the fraction of clipped steps, and the pass criteria (equality, finite loss, memory below 34 GiB, step-time overhead below 15%). It takes the backend's per-GPU lock and refuses a GPU that already holds more than 2 GiB (`--busy-limit-gib`). `--levels 2 1` measures the reduced placement. `--device cpu` with a smaller `--patch` is a functional check only.
