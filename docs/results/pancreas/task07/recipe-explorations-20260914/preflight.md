# GPU feasibility before training

[Recipe guide](../../../../guides/medical-recipe-experiments.md) · [Model comparison](README.md) · [Machine-readable measurements](preflight-summary.json)

All nine arms completed five measured full-batch GPU optimizer steps with finite loss and matching raw/cache samples and RNG state. These are scratch diagnostic models, **not trained study results**. The diagnostic uses a constant AdamW learning rate and explicit CUDA synchronization; it does not estimate convergence or steady-state training throughput. Native inference is checked separately by the campaign and its post-run benchmarks.

| Arm | Parameters | Peak allocated GiB | Peak reserved GiB | Mean forward + backward seconds per batch |
|---|---:|---:|---:|---:|
| dynunet-control10k-seed0 | 16,543,683 | 7.61 | 10.50 | 0.220 |
| dynunet-deep10k-seed0 | 16,544,265 | 7.74 | 10.92 | 0.224 |
| dynunet-focal05-seed0 | 16,543,683 | 7.61 | 10.50 | 0.222 |
| dynunet-focal10-seed0 | 16,543,683 | 7.61 | 10.50 | 0.222 |
| dynunet-window-seed0 | 16,543,683 | 7.61 | 10.50 | 0.222 |
| dynunet-minmax-seed0 | 16,543,683 | 7.61 | 10.50 | 0.223 |
| dynunet-isotropic-seed0 | 16,543,683 | 12.53 | 17.41 | 0.375 |
| swin_unetr-swin24-seed0 | 15,703,029 | 24.69 | 37.37 | 0.605 |
| swin_unetr-swin48-seed0 | 62,186,757 | 16.82 | 26.64 | 1.051 |

Batch size is 8 and precision is BF16 throughout. Swin48 uses activation checkpointing; Swin24 does not. This explains why the larger model can reserve less memory while taking longer. Deep supervision adds 582 training-only parameters in this implementation.

The 197-case training input/component audits are separate launch gates. Passing a five-step GPU profile does not certify the whole dataset or mean an arm has begun its 10,000-update training schedule.

Frozen training source: `52bb2cd90780989546d5e3f2e5734bdf952d72f2`. [Checks passed on the self-hosted Runner](https://github.com/arianizadi/segmentary/actions/runs/34909597818). Raw profile receipts are retained on HDRFS and bound by the hashes in the JSON.
