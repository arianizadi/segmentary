# Task07: what we can learn from stronger training recipes

Reviewed September 14, 2026. This is a source and configuration audit, not a new training result.

**The first sweep measures architectures under a small common starting recipe. It does not reproduce the papers' complete systems.** Differences in preprocessing, sampling, augmentation, model capacity, supervision, training budget and inference are large enough that the score gap cannot be assigned to architecture alone. These are hypotheses to test, not proven causes of our lower Dice.

Read this page first, then the [proposed controlled experiments](experiments.md). [Evidence JSON](evidence.json) records our resolved recipes, the actual HDRFS nnU-Net plan, artifact hashes and upstream code revisions. [Link verification](link-checks.json) records the URLs checked for this audit.

```text
recipe-comparison-20260914/
├── README.md          # Verified differences, interpretation and sources
├── experiments.md     # Transferable ideas and a staged experiment plan
├── evidence.json      # Sanitized recipe evidence and source revisions
└── link-checks.json    # Link-check results
```

The original [scratch results](../scratch-screen-20260913/README.md) and [performance continuation](../performance-continuation-20260914/README.md) retain their original identities. The latter repeated prediction from the existing checkpoints; it did not add optimizer updates.

## 1. Our actual recipe versus the nnU-Net running on HDRFS

Our Torch column describes the dense 3D models such as DynUNet, Swin UNETR and U-Mamba. Query-based models have their own objectives, and 2.5D models use a different input shape. Values come from resolved run records and frozen source `9f7615bd1f6035d65aca3f848a263b67c49f531f`, not the smaller example YAMLs.

| Ingredient | Our dense 3D sweep | Our official-backend nnU-Net ResEnc L |
| --- | --- | --- |
| Data | Task07: 197 train, 42 validation, 42 reserved test | Same explicit split; planning uses train + validation, excluding reserved test |
| Initialization | Random, including encoders | Random |
| Spatial resolution, x/y/z | 1.5 / 1.5 / 2.5 mm | 0.8125 / 0.8125 / 2.5 mm |
| Patch tensor, z/y/x | 96 × 96 × 96 | 56 × 320 × 256 |
| Approximate physical coverage, x/y/z | 144 × 144 × 240 mm | 208 × 260 × 140 mm |
| CT intensities | Clip −100 to 240 HU, linearly map to [0,1] | CT normalization: clip to estimated 0.5th/99.5th percentiles, then standardize; actual bounds −92 / 215 HU, mean 79.774, SD 71.162 |
| Patch selection | 50% uniform-volume center; 50% choose a present foreground class uniformly, then a voxel in that class | Configured foreground fraction 0.33; deterministic batch allocation rounds this to 1 of 2 patches for this batch size |
| Augmentation | Independent flips, probability 0.5 per spatial axis | Spatial rotation/scaling, noise, blur, brightness, contrast, simulated low resolution, gamma, mirroring; anisotropy-aware spatial augmentation |
| Optimizer | AdamW, LR 0.0003, weight decay 0.00001 | SGD, LR 0.01, Nesterov momentum 0.99, weight decay 0.00003 |
| LR schedule | Polynomial decay, power 0.9, updated each optimizer step, no warmup | Polynomial decay, power 0.9, updated by epoch |
| Loss | Unweighted CE + foreground soft Dice; Dice aggregated across the batch | CE + foreground soft Dice; plan specifies per-sample Dice (`batch_dice=false`) |
| Deep supervision | Disabled for these common dense-model adapters | Enabled: losses at multiple decoder resolutions |
| Budget | 100 × 100 = 10,000 optimizer updates | 1,000 × 250 = 250,000 optimizer updates |
| Batch | 8 patches | 2 patches |
| Checkpoint selection | Highest mean per-case native validation mass Dice, checked every 1,000 updates | Official EMA foreground patch Dice; full native metrics computed separately |
| Inference | 50% window overlap; uniform probability blending; no mirroring/ensemble | 50% tile step; Gaussian blending; this run explicitly disables mirroring and uses only fold 0 |

Sources: [our preprocessing, sampling and loss](https://github.com/arianizadi/segmentary/blob/9f7615bd1f6035d65aca3f848a263b67c49f531f/src/segmentary/medical/torch_data.py), [our training loop](https://github.com/arianizadi/segmentary/blob/9f7615bd1f6035d65aca3f848a263b67c49f531f/src/segmentary/medical/torch_backend.py), [our nnU-Net adapter](https://github.com/arianizadi/segmentary/blob/9f7615bd1f6035d65aca3f848a263b67c49f531f/src/segmentary/medical/backend.py), and the live plan/settings in [evidence.json](evidence.json). The installed nnU-Net trainer and data loader were inspected directly; their SHA-256 hashes are recorded there.

**Resolution and context are separate variables.** nnU-Net retains about 1.85 times as many pixels across an in-plane distance, but its patch has shorter superior–inferior coverage. Its patch contains 4,587,520 voxels versus 884,736: 5.19 times more. Simply shrinking our spacing while keeping 96³ reduces physical context; it does not reproduce the nnU-Net plan. Resampling finer than acquisition also does not create new anatomical information.

**Training length is more than an epoch count.** At full budgets, our recipe samples 80,000 patches; nnU-Net samples 500,000, a 6.25× difference. Multiplying patches by input voxels gives about 32.41× more input-voxel exposure for nnU-Net. Neither number measures FLOPs, independent patients seen, or wall time. Architectures, augmentation and validation overhead differ.

**We already oversample masses.** When both classes exist after resampling, our explicit tumor-center probability is 0.5 × 0.5 = 25%; uniform sampling can also hit tumor. A centered crop need not contain a tumor at its exact center after boundary clamping. Likewise, a “random” patch is not a verified background-only patch. Compare observed crop composition, not just configuration names.

**Planning scope matters.** The nnU-Net intensity statistics and spatial plan use the 239-case development cohort, including validation. This is disclosed by the existing protocol, and is different from fitting preprocessing on training cases alone. Any new train-only normalization experiment needs its own identity. The 42 reserved test cases remain excluded from tuning and planning.

## 2. What the published Swin UNETR actually did

The CVPR 2022 system used a 48-channel base embedding; ours uses 24 (15,703,029 parameters in our three-class implementation). The paper used self-supervised CT pretraining and ensembled the best models from five folds. Those are substantial differences from one scratch model. [Main paper, Sections 3 and 5.2](https://openaccess.thecvf.com/content/CVPR2022/papers/Tang_Self-Supervised_Pre-Training_of_Swin_Transformers_for_3D_Medical_Image_Analysis_CVPR_2022_paper.pdf).

The pancreas-specific supplement states: intensity clipping −87 to 199 HU; 96³ crops; positive/negative sampling 1:1; random flip, rotation and intensity scaling with probabilities 0.5, 0.25 and 0.5. Its Task07 paragraph does **not** specify voxel spacing or a complete downstream optimizer/update budget. [Supplement, Section B.2, printed page 14](https://openaccess.thecvf.com/content/CVPR2022/supplemental/Tang_Self-Supervised_Pre-Training_of_CVPR_2022_supplemental.pdf).

The main paper says 450K pretraining iterations; the supplement's timing section says 45K. Neither is a verified Task07 fine-tuning budget. This inconsistency remains unresolved; do not turn either number into our training target.

The public MONAI **BTCV example** defaults to LR 0.0001, AdamW, 5,000 epochs, 50 warmup epochs then cosine decay, spacing 1.5/1.5/2.0 mm, and HU −175/250. It draws four crops per sampled scan and offers widths 12/24/48. This is useful implementation inspiration, but BTCV is a different dataset and these defaults are not proof of the historical Task07 submission command. [Pinned entry point](https://github.com/Project-MONAI/research-contributions/blob/21ed8e57c7256834d4fbaf19579ca25ad3d135ee/SwinUNETR/BTCV/main.py), [transforms](https://github.com/Project-MONAI/research-contributions/blob/21ed8e57c7256834d4fbaf19579ca25ad3d135ee/SwinUNETR/BTCV/utils/data_utils.py).

Transferable ideas: rotation/intensity augmentation, testing width 48, and a declared warmup schedule. Pretrained weights remain outside our scratch-only experiment.

## 3. Universal Model: the most interesting sampling clue

The paper combines 3,410 CTs across 14 datasets and pretrained CLIP text representations. It reports 1.5 mm isotropic spacing, HU −175/250, 96³ crops, AdamW LR 0.0004, weight decay 0.00001, warmup/cosine scheduling, and five-fold validation. Its hardware/budget wording is inconsistent: four GPUs then eight A5000s, with an unclear 50-epoch scheduler statement. We cannot reconstruct a complete historical run from that prose. [Paper, Section 4.1.2](https://www.cs.jhu.edu/~zongwei/publication/liu2024universal.pdf).

The released code contains a **Task07-specific override** that is more informative than the paper's generic foreground/background description:

- For `10_07`, it uses class crop ratios **background : pancreas : tumor = 1 : 1 : 5**, rather than the generic positive/negative crop transform. With all classes available, the nominal tumor-center share is 5/7, about 71.4%.
- It also applies random zoom (probability 0.3, range 1.3–1.5), 90° rotation (0.1), and intensity shift (0.2).
- The code's CLI defaults differ from the paper: U-Net backbone, 2,000 epochs, 100 warmup epochs, LR 0.0001. Treat these as a released implementation snapshot, not a recovered submission configuration.

Sources: [dataset routing and crop ratios](https://github.com/ljwztc/CLIP-Driven-Universal-Model/blob/43c12399cc98a40f447342a8dc2cecae5edae84c/dataset/dataloader.py), [training entry point](https://github.com/ljwztc/CLIP-Driven-Universal-Model/blob/43c12399cc98a40f447342a8dc2cecae5edae84c/train.py).

Its independent binary organ/tumor heads use a partial-label-aware Dice/BCE objective. Copying that objective into our exclusive three-class softmax task would change the label semantics. The useful near-term idea is explicit tumor-balanced sampling. Multi-dataset partial-label training belongs to the later PanTS/organ-only study. [Loss implementation](https://github.com/ljwztc/CLIP-Driven-Universal-Model/blob/43c12399cc98a40f447342a8dc2cecae5edae84c/utils/loss.py).

## 4. U-Mamba and MedNeXt reinforce the recipe lesson

**U-Mamba's official trainers inherit nnU-Net training.** The base uses 1,000 × 250 updates, SGD LR 0.01 with Nesterov momentum 0.99, weight decay 0.00003, polynomial decay, planned geometry and deep supervision. The encoder/bottleneck trainers supply the network inside that framework. Our fixed-shape AdamW/no-auxiliary-head implementation answers a different experiment. This verifies their code path, not a Task07 score reproduction. Their example inference commands explicitly disable TTA. [Base trainer](https://github.com/bowang-lab/U-Mamba/blob/28459e33ca03769800dd35e23c6e62491d1925b5/umamba/nnunetv2/training/nnUNetTrainer/nnUNetTrainer.py), [encoder trainer](https://github.com/bowang-lab/U-Mamba/blob/28459e33ca03769800dd35e23c6e62491d1925b5/umamba/nnunetv2/training/nnUNetTrainer/nnUNetTrainerUMambaEnc.py), [official instructions](https://github.com/bowang-lab/U-Mamba/blob/28459e33ca03769800dd35e23c6e62491d1925b5/README.md).

**MedNeXt has its own optimizer choices inside nnU-Net.** Its kernel-3 trainers use AdamW LR 0.001, epsilon 0.0001 and inherited weight decay 0.00003, plus deep supervision. Ours is specifically **MedNeXt S, kernel 3**, LR 0.0003, with auxiliary supervision disabled; it is not the larger L/kernel-5 variant. Test its own recipe before ranking the whole family. [MedNeXt trainers](https://github.com/MIC-DKFZ/MedNeXt/blob/0b78ed869fbd1cc2fd38754d2f8519f1b72d43ba/nnunet_mednext/training/network_training/MedNeXt/nnUNetTrainerV2_MedNeXt.py), [inherited trainer](https://github.com/MIC-DKFZ/MedNeXt/blob/0b78ed869fbd1cc2fd38754d2f8519f1b72d43ba/nnunet_mednext/training/network_training/nnUNetTrainer.py).

**Historical nnU-Net versus today's ResEnc L:** the earlier 52.78% mass Dice belongs to the published MSD benchmark, not this ongoing single-fold ResEnc L run. The retained v1 code confirms a standard 1,000-epoch SGD/poly/deep-supervision recipe, but we have not recovered the exact historical Task07 plan, selected configurations, ensemble or postprocessing. [v1 trainer](https://github.com/MIC-DKFZ/nnUNet/blob/db16c6cef5fdd5a180159184e46b58bcca670446/nnunet/training/network_training/nnUNetTrainerV2.py). The current [ResEnc guidance](https://github.com/MIC-DKFZ/nnUNet/blob/master/documentation/resenc_presets.md) is a separate reference.

## 5. What this means for our comparison

Our best completed single-seed validation mass Dice remains about 35.71% for U-Mamba Encoder. The previously cited nnU-Net 52.78%, Swin UNETR 58.21% and Universal Model 62.33% are official-test results tabulated in [Liu et al., Table 3](https://www.cs.jhu.edu/~zongwei/publication/liu2024universal.pdf). They provide context, not matched effect sizes. Our pancreas score is the union of labels 1 and 2; harmonize organ definitions before comparing organ Dice.

We should borrow and test ingredients across DynUNet, U-Mamba Encoder and MedFormer, then run an explicitly larger scratch Swin variant. Evaluate each model both under a shared controlled recipe and, later, under a bounded model-specific tuning budget. Keep those tables separate so equal settings are not confused with equal optimization opportunity.

The practical order is: verify crop content and small-mass preservation, test sampling and augmentation, test resolution/context together with compute accounting, then examine supervision and model-specific schedules. Longer training is a candidate experiment, not a guaranteed fix: several existing curves peak before 10,000 updates. See the [experiment plan](experiments.md).

No training configuration, checkpoint, active process, evaluation result or scheduled monitoring was changed by this audit.
