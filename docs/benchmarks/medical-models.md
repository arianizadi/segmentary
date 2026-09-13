# Scratch CT architecture verification

All **27 Torch architectures passed** a real-data forward, backward, clipped SGD
update and inference check on an NVIDIA L40S. Every trainable parameter had a
finite gradient and an optimizer update changed model weights. Models used their
**standard/default capacities**, with explicit small patches and batch size two.
The 16 2D models received five adjacent CT slices as channels; 3D models received
one volumetric CT channel. No pretrained weights were loaded.

This is execution evidence. It does not measure convergence, segmentation quality,
cancer detection, external generalization, or comparative inference speed. One
audited training examination supplied the patches. All recipes require independent
training/validation and a frozen external/held-out evaluation before research claims.

The [machine-readable summary](medical-model-matrix.json) is generated from the
server evidence. Original artifacts stay outside Git at the reproduction-profile
path `/data/izadia1/datasets/pancreas/verification/model-matrix-20260913/`.

| Model | Parameters | Input patch | Peak allocated GiB | Check wall seconds |
|---|---:|---|---:|---:|
| `unet_2d` | 24,442,931 | `64×64` | 0.201 | 1.78 |
| `unet_plus_plus` | 26,085,171 | `64×64` | 0.213 | 0.40 |
| `fpn` | 23,161,923 | `64×64` | 0.193 | 1.97 |
| `deeplabv3_plus` | 26,684,371 | `64×64` | 0.220 | 0.43 |
| `hrnet_ocr` | 34,919,750 | `64×64` | 0.296 | 0.79 |
| `convnext_upernet` | 60,132,518 | `64×64` | 0.558 | 4.91 |
| `segformer_b0` | 3,718,051 | `64×64` | 0.050 | 1.52 |
| `segformer_b2` | 27,355,203 | `64×64` | 0.239 | 1.74 |
| `swin_upernet` | 59,831,744 | `64×64` | 0.555 | 0.76 |
| `dpt` | 110,509,766 | `64×64` | 0.885 | 2.17 |
| `maskformer` | 41,722,302 | `64×64` | 0.347 | 0.68 |
| `mask2former` | 47,404,926 | `64×64` | 0.388 | 0.80 |
| `bisenetv2` | 5,194,703 | `64×64` | 0.065 | 0.32 |
| `ddrnet` | 5,732,838 | `64×64` | 0.065 | 0.27 |
| `pidnet` | 7,717,383 | `64×64` | 0.080 | 0.30 |
| `lraspp` | 3,218,766 | `64×64` | 0.046 | 0.30 |
| `unet_3d` | 7,914,603 | `32×32×32` | 0.102 | 2.46 |
| `dynunet` | 16,543,683 | `32×32×32` | 0.232 | 0.36 |
| `segresnet` | 18,796,035 | `32×32×32` | 0.243 | 0.30 |
| `mednext_v1` | 5,550,947 | `32×32×32` | 0.510 | 0.32 |
| `swin_unetr` | 15,703,029 | `64×64×64` | 2.429 | 0.46 |
| `unetr` | 92,624,115 | `32×32×32` | 0.763 | 0.72 |
| `medformer` | 39,591,555 | `32×32×32` | 0.544 | 0.56 |
| `transunet_3d` | 102,119,424 | `32×32×32` | 0.863 | 2.42 |
| `umamba_bot` | 22,570,531 | `8×8×8` | 0.405 | 0.40 |
| `umamba_enc` | 22,088,259 | `8×8×8` | 1.052 | 1.03 |
| `segmamba` | 67,362,723 | `32×32×32` | 1.211 | 1.16 |

Memory includes this single verification step, not AdamW training or a full-volume
inference workload. Wall time includes construction and checks; these values are
not a controlled architecture speed ranking. The test uses SGD lr=0.001 and the
training harness's gradient norm cap of 12. PIDNet required that cap for finite
post-update outputs on this case; the verifier now records clipping explicitly.

CPU tests independently cover geometry (axis permutations, flips, anisotropic
spacing and integer-HU interpolation), same-patient context, native query losses,
all architecture mechanisms, cached-weight rejection, immutable cache membership,
checkpoint publication failure, and optimizer/RNG resume equivalence.

Use the [model guide](../guides/medical-models.md) and [27 recipe files](../../configs/medical/torch/README.md)
for execution. The [earlier nnU-Net validation](medical-ct.md) is a separate
backend verification. Additional end-to-end GPU evidence is recorded below.

## Complete GPU workflow checks

Three additional reduced-capacity recipes passed prepare, train-only preprocessing,
AdamW training, bound resume, native-volume prediction and the shared evaluator.
They used one train and one validation examination, fixed spacing [4,4,5] mm,
and tiny budgets. Every expected validation volume was evaluated successfully.

| Model | Committed updates | Resume check | Native prediction/evaluation |
|---|---:|---|---|
| Mask2Former, five-slice context | 16 | Cancelled a live worker after an epoch checkpoint, then completed the remaining budget | Passed |
| Swin UNETR | 4 | Restored the completed checkpoint; no extra updates requested | Passed |
| U-Mamba Bot, portable Torch scan | 4 | Restored the completed checkpoint; no extra updates requested | Passed |

The [workflow summary](medical-model-workflows.json) records evidence digests,
coverage, spacing, patches, time and peak training allocations. These smoke
models have not converged; their metrics must not be presented as research
performance. No held-out test examinations were used. Checkpoint interruption
fault injection and exact optimizer/RNG continuation are additionally covered
by CPU tests. Native Mamba CUDA kernels are optional and were not installed or
validated in this run; the actual portable selective recurrence was tested.

## Local release checks

The complete CPU-only CI-equivalent suite passed (1,862 tests, three skips and
39 intentionally deselected hardware/data tests), followed by the additional
JSON-number regression. Ruff, formatting, mypy and dependency consistency passed.
The wheel includes all 27 YAML recipes and third-party licenses/notices. GitHub
Actions runs the full suite plus the optional medical-model dependencies on
each source push; its final run status is linked in the release handoff.
