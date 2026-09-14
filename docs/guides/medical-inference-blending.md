# Compare sliding-window blending on a fixed medical checkpoint

`compare_medical_blending.py` asks whether weighting the center of each 3D prediction window improves the reconstructed segmentation. It evaluates the same saved weights twice, using uniform and Gaussian window weights. This changes inference only; it does not train, resume, or reselect a checkpoint.

The normal training and prediction APIs retain uniform blending. `TorchConfig` has no new field, so there is no silent reinterpretation of an old training configuration. The ordinary backend still requires its original source, runtime, configuration, and checkpoint identity.

## Run on HDRFS

Use the original campaign's Python interpreter and a new output directory outside the old workspace/source. Select an idle GPU; keep GPU 0 available for the existing nnU-Net job.

```bash
/data/izadia1/envs/pancreas-campaign-20260913/bin/python \
  scripts/compare_medical_blending.py \
  --campaign /data/izadia1/projects/segmentary-runs/pancreas/task07-recipe-ablation-20260914 \
  --run-id dynunet-control-seed0 \
  --gpu 6 \
  --output /data/izadia1/projects/segmentary-runs/pancreas/blending-diagnostic \
  --reference-report /data/izadia1/projects/segmentary-runs/pancreas/task07-recipe-ablation-20260914/state/evaluations/dynunet-control-seed0/report.json
```

The script requires committed, clean diagnostic source. Its historical verification subprocess imports the frozen training source and runs that source's unchanged binding, package-runtime, scratch-origin, and best-checkpoint guards. The diagnostic then loads the exact SHA-256-verified checkpoint bytes. Concurrent diagnostic readers hold shared workspace locks, which exclude ordinary training writers. The GPU lock and an idle-device check prevent accidental sharing with another campaign job. Original configuration, binding, checkpoint, manifest, split, and medical source files are verified again before completion is published.

`--reference-report` adds a strict check: every uniform pancreas/mass Dice value must reproduce the original full-scan evaluation within `1e-12`, with matching reference hashes and cohort. A discrepancy fails the diagnostic rather than being mistaken for a Gaussian benefit.

## Frozen comparison protocol

- Evaluate the complete original validation cohort. Never open training or test CT/label payloads.
- Use the checkpoint originally selected by uniform validation; Gaussian does not get its own checkpoint selection.
- Keep HU processing, physical spacing, patch shape, overlap, inference batch size, precision, native reconstruction, and model weights fixed.
- Uniform weights follow the original floating-point accumulation path exactly.
- Gaussian weights are separable across patch axes, with center `(axis_length - 1) / 2` and sigma `axis_length / 8`. Normalize the peak to one and floor weights at float32 epsilon before accumulation. This keeps corner denominators positive even when a voxel belongs to a single window.
- Weight softmax probabilities before native-space resampling and argmax. This is a declared Segmentary inference ablation, not a claim of reproducing nnU-Net's exact inference implementation.
- Alternate uniform-first and Gaussian-first order by scan after three synthetic model warmups. Record per-scan preprocessing, model, reconstruction, export, memory, and wall time. These paired per-scan runs do not overlap preprocessing across scans, so their wall time is not directly comparable to a fully pipelined campaign.
- Score native Dice, surface Dice at 2 mm, HD95, and connected-component lesion localization. Bootstrap paired patient-group differences with 10,000 samples and seed 20260914.

## Output

```text
new-output/
├── provenance.json                 # Original binding and new inference source
├── progress.json                   # Completed predictions out of twice the cohort
├── timings.json                    # Per-case paired timing and peak GPU memory
├── uniform/
│   ├── predictions/                # Native NIfTI segmentations
│   └── evaluation/                 # JSON, CSV, and review overlays
├── gaussian/
│   ├── predictions/
│   └── evaluation/
└── comparison.json                 # Paired Dice, means, timings, agreement checks
```

Keep case-level outputs in approved private research storage. They retain source case/patient identifiers for pairing and contain scan-derived review images. Publish only reviewed aggregate results in the comparison repository.

The paired intervals describe this checkpoint and validation cohort. They do not account for validation-driven checkpoint selection or establish improvement on an independent test set. Connected components are localization proxies, and a mass annotation is not necessarily a confirmed malignant tumor.

For direct Python inference, pass an explicit `InferenceBlending("gaussian")` to `tiled_probabilities`, `predict_case`, or `iter_predictions`. Leave the argument omitted for the original uniform behavior. A diagnostic using this override must record it in its own inference protocol.
