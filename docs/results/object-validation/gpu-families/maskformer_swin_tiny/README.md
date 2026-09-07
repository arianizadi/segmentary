# maskformer_swin_tiny: real-image CUDA execution check

This is a **small random architecture** from this family, not the full pretrained model named by the catalog key. It verifies execution and finite gradients, not accuracy or throughput rankings. Exact dimensions are recorded in the linked JSON files.

| Task | Precision | Optimizer steps | Attempts | Last loss | Peak allocated GiB | Peak reserved GiB |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| instance | float16 | 2 | 15 | 37.434725 | 1.306 | 1.465 |
| panoptic | bfloat16 | 2 | 2 | 39.330479 | 2.105 | 2.371 |

Both tasks used two real Cityscapes train images and two distinct official validation images, two microbatches per optimizer update, and native target masks. Float16 overflow attempts lower the scaler and do not count as successful updates. Reserved memory can include cache from earlier models in the same harness. NVIDIA L40S; shared GPU; Torch 2.11.0+cu128.

Complete architecture, source image/annotation hashes, gradient norms, losses, checkpoint SHA-256 and exact arguments: [instance record](../../gpu-instance.json), [panoptic record](../../gpu-panoptic.json). The records contain all four families; select this page's `family` key.
