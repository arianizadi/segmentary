# Scratch CT model recipes

These **27 recipes** run the actual named architectures through the shared
`backend: torch` medical workflow. Every encoder, decoder and backbone starts
without learned weights. See the [model guide](../../../docs/guides/medical-models.md)
for installation, commands, objectives and comparison limits.

For the implemented six-arm DynUNet sampling/augmentation experiment, read the
[controlled recipe guide](../../../docs/guides/medical-recipe-ablation.md). It
explains the planner, training-only input audit, fresh run identities and shared
dashboard; creating a plan does not start training.

| Group | Recipes |
|---|---|
| General 2D CNNs | [U-Net](unet_2d.yaml), [U-Net++](unet_plus_plus.yaml), [FPN](fpn.yaml), [DeepLabV3+](deeplabv3_plus.yaml), [HRNet+OCR](hrnet_ocr.yaml) |
| Modern 2D CNNs/transformers | [ConvNeXt+UPerNet](convnext_upernet.yaml), [SegFormer B0](segformer_b0.yaml), [SegFormer B2](segformer_b2.yaml), [Swin+UPerNet](swin_upernet.yaml), [DPT](dpt.yaml) |
| Query models | [MaskFormer](maskformer.yaml), [Mask2Former](mask2former.yaml) |
| Efficient 2D models | [BiSeNetV2](bisenetv2.yaml), [DDRNet](ddrnet.yaml), [PIDNet](pidnet.yaml), [LR-ASPP](lraspp.yaml) |
| 3D CNNs | [3D U-Net](unet_3d.yaml), [DynUNet](dynunet.yaml), [SegResNet](segresnet.yaml), [MedNeXt v1](mednext_v1.yaml) |
| 3D attention | [Swin UNETR](swin_unetr.yaml), [UNETR](unetr.yaml), [MedFormer](medformer.yaml), [3D TransUNet](transunet_3d.yaml) |
| 3D state-space models | [U-Mamba bottleneck](umamba_bot.yaml), [U-Mamba encoder](umamba_enc.yaml), [SegMamba](segmamba.yaml) |

The separate [official nnU-Net ResEnc recipe](../../examples/medical-pancreas.yaml)
continues to use its own planner, trainer and environment. It is an additional
comparator, outside these 27 Torch recipes.

## Choose and copy a recipe

Copy one YAML to an experiment configuration directory, then set `workspace` to
an explicit artifact location and `gpu` to one available device. Relative
workspace paths resolve from the copied configuration file. Keep datasets and
run directories outside version control. Omit `backend_python` to use the CLI's
current interpreter, or set an explicit compatible medical-models interpreter.

The recipes use 128×128 single-slice inputs for 2D models and 64×64×64 patches for
3D models, with explicitly fixed HU clipping and physical resampling. These
choices are starting settings. Tune them using development data with a declared
budget; they are not measured best settings for Task07. `epochs: 100` and
`steps_per_epoch: 100` are 10,000 optimizer updates, not 100 complete dataset
passes. A validation pass reconstructs every validation volume after each epoch.

All 16 2D architectures also support 2.5D: copy the recipe, set `mode: '2.5d'`,
`context_slices: 5`, and choose a new workspace. `patch_size` remains `[y, x]`;
the five neighboring slices become input channels and the target is the center
slice. An architecture name such as `unet_2d` remains unchanged because its
convolutions are still two-dimensional.

Run a separate smoke/overfit experiment before allocating the baseline budget.
Metadata from `segmentary-medical models` supplies explicitly reduced smoke
options and compatible patch sizes. A smoke profile is a different capacity and
must not be reported as a standard-size baseline.

## Files created by a run

The workspace contains bound configuration/source/environment provenance,
training-only preprocessing cache, checkpoints, per-epoch metrics, stage logs,
and native-volume predictions. The [model guide](../../../docs/guides/medical-models.md)
shows the complete prepare → preprocess → train → predict → evaluate sequence.

Models share AdamW and a declared learning-rate schedule, but query, auxiliary
and boundary heads retain their documented objectives. State-space recipes use
the portable exact Torch scan by default, which can be much slower than fused
CUDA. GPU memory, time, model capacity, physical context and loss must accompany
an accuracy comparison.

For a controlled dense-loss experiment, `dice_reduction: per_sample` changes
foreground Dice from batch pooling to equal weighting of sampled patches. The
default remains `batch`; model-native objectives are preserved. See the
[Dice reduction guide](../../../docs/guides/medical-dice-reduction.md) for supported
combinations, empty-class behavior, and fresh-workspace requirements.
