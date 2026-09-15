# Fixed-checkpoint inference experiments

All five settings evaluated the same selected DynUNet control checkpoint on the same 42 validation cases in native CT geometry. No training, checkpoint selection, reference-guided cropping or threshold tuning occurred. Pancreas Dice uses the union of pancreas and mass. Reserved test payloads were not opened.

| Setting | Mass Dice | Pancreas Dice |
| --- | ---: | ---: |
| Probability averaging, uniform tile weights (original) | 32.98% | 75.59% |
| Probability averaging, Gaussian tile weights | 34.96% | 77.72% |
| Raw-logit averaging, uniform tile weights | 32.27% | 75.19% |
| Raw-logit averaging, Gaussian tile weights | 34.93% | 77.81% |
| Probability/uniform with centered padding | 31.75% | 75.47% |

## What changed

Overlapping sliding-window predictions must be combined. Probability averaging first converts each tile's scores to probabilities; raw-logit averaging combines the unnormalized scores before the final class decision. Gaussian weights favor each tile's center. Centered padding changes where constant padding is added when an image dimension is shorter than the 96-voxel patch.

Raw-logit averaging with Gaussian weights differed from probability/Gaussian averaging by **-0.025 mass Dice points**, with a paired 95% bootstrap interval of **[-0.431, +0.326]**. It does not provide a meaningful mass gain. Its pancreas change was only +0.085 points. Gaussian probability weighting itself improves mass by 1.97 points versus the original uniform setting, interval [-0.12, +4.14]; this reproduces the earlier small gain rather than explaining the roughly 22-point nnU-Net gap.

Training symmetrically pads short dimensions, whereas ordinary inference pads their high end. This is a real difference, but changing inference to centered padding reduced mass Dice by **1.24 points**, interval **[-5.21, +1.23]**. Exactly 21 validation volumes require depth padding. On the other 21 cases, all prediction file hashes remained identical. Among the 21 requiring padding, mean mass Dice fell from 29.15% to 26.67%.

## Verification and decision

The original probability/uniform branch reproduced **all 42 historical prediction SHA-256 hashes and all Dice values exactly**. All four blending modes completed formal 42-case native evaluations; the separate centered-padding mode also completed all 42. CPU branch-parity tests, a real native-case parity check, and signed coordinate phantoms checked the private operators before evaluation. Historical checkpoints, source bindings and training workspaces remained unchanged.

No production inference change is warranted from the new raw-logit or padding results. The modest Gaussian effect remains an existing recipe choice. Confidence inspection of the five shared misses found mass scores far below competing labels in much of the annotated mass; these failures are not just close argmax ties. Those softmax values are not calibrated clinical probabilities, and the case-level evidence remains private.

[Exact aggregate measurements, paired intervals and provenance](inference-ablations.json) record all declared comparisons. Bootstrap units are the frozen dataset-case patient proxies (`dataset_case_unverified`), not independently verified patient identities. Intervals condition on the fixed checkpoint and repeatedly used validation cohort; they are exploratory and not adjusted for multiple comparisons.

[Back to the investigation](README.md)
