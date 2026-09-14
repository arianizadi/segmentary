# Completed fit and inference diagnostics

Both diagnostics completed successfully on HDRFS on 2026-09-14. The pipeline can fit the two selected training scans well. Gaussian blending improved this checkpoint's average validation Dice modestly, with uncertainty around the mass improvement. Neither finding establishes independent test performance.

The [aggregate numerical evidence](aggregate-summary.json) contains the exact values. Scientific source is `d072beb8e04a1bbcdf360cb50f3df3901d9fa08d`; its [checks passed on the self-hosted segmentary-linux runner](https://github.com/arianizadi/segmentary/actions/runs/34893652724). Original checkpoints, predictions and labels were preserved. No external pretrained weights or reserved-test payloads were used.

## Can the model fit known anatomy?

The original best DynUNet control checkpoint scored **76.08% mass Dice and 73.34% pancreas union Dice** on four fixed training examinations, selected by native image size before inspecting predictions. These four examples are too few to estimate the training-set average or a population generalization gap.

A separate scratch initialization trained on two of those scans for 2,000 updates, with augmentation disabled. All numbers below come from native full-volume reconstruction of those same two training scans, not sampled training patches.

| Update | Mass Dice | Pancreas union Dice |
| --- | ---: | ---: |
| 0 | 0.06% | 0.13% |
| 100 | 0.00% | 69.19% |
| 500 | 87.20% | 88.54% |
| 1,000 | **90.40%** | 91.54% |
| 2,000 (final) | 90.00% | **92.48%** |

Best mass Dice occurred at update 1,000; the final checkpoint is reported separately. Training completed its full budget with finite loss and no early stop. Latest/best checkpoint retention was verified; obsolete middle generations were removed.

This is evidence that the model, loss, sampling and native reconstruction can learn these examples. It makes a fundamental inability to fit labels less likely, but does not certify every preprocessing path or annotation. Memorization is intentionally evaluated on training data and is not a benchmark result. See the [fit protocol](../../../../guides/medical-training-fit-diagnostic.md).

## Does Gaussian window blending help?

Both modes used the identical original best DynUNet control checkpoint on all 42 validation examinations. Training, checkpoint selection, images, masks and inference settings were held fixed except for the window weighting. Gaussian weighting was applied to softmax probabilities before native resampling and argmax; the model was not retrained or reselected.

| Region | Uniform | Gaussian | Gaussian minus uniform | Paired 95% bootstrap interval |
| --- | ---: | ---: | ---: | ---: |
| Mass | 32.98% | 34.96% | +1.97 percentage points | -0.17 to +4.08 points |
| Pancreas union | 75.59% | 77.72% | +2.13 percentage points | +0.72 to +3.64 points |

The bootstrap uses 10,000 resamples of the recorded patient groups, with 42 groups here. Dataset case grouping has not independently established patient identity. The mass interval includes zero: this is a promising small improvement, not conclusive evidence of a mass benefit. The pancreas interval is positive within this exploratory comparison; it is not adjusted for the wider recipe search.

All 42 uniform predictions reproduced the historical native NIfTI files byte for byte, and the strict per-case Dice reproduction check passed. This supports attributing the observed difference to window blending under this protocol. Coverage was complete in both modes. The original checkpoint was selected using uniform validation, so this is not a comparison of separately optimized inference pipelines.

Measured summed inference time was 263.26 seconds for uniform and 255.76 seconds for Gaussian. These totals include preprocessing, prediction, native reconstruction and NIfTI export, excluding warmup and metric calculation. Mode order alternated by case. This single run does not establish a speed improvement; caching and concurrent workload can affect timing. See the [inference protocol](../../../../guides/medical-inference-blending.md).

## What this changes

- Prioritize the [fresh longer-schedule and finer-grid experiments](../followup-20260914/README.md) to investigate the remaining validation shortfall. Keep the declared uniform inference setting in those arms so their planned contrasts remain interpretable.
- Retain Gaussian blending as an inference candidate for a later frozen protocol; do not silently replace existing reported scores or select a new checkpoint from this result.
- Continue the [annotation review](../annotation-review-20260914/README.md) with the radiology mentor. These diagnostics do not show that difficult annotations impose a ceiling on performance.
- Keep these results separate from the [official hidden-test comparison](../official-benchmark-20260914/README.md) and from the two-case memorization numbers.

Detailed diagnostic status, source/checkpoint hashes, per-case metrics and predictions remain outside Git at `/data/izadia1/projects/segmentary-diagnostics-followup-20260914/`. Only the allowlisted aggregate export is committed here. The finite diagnostic supervisor exited and its owned tmux session was removed after completion.
