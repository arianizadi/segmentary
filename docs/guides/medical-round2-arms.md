# Region labels and nnFoundation pretraining (round-2 arms)

Two opt-in recipe variants share the frozen Wave 1 reference plan: its spacing (2.5 x 0.8125 x 0.8125 mm), patch (56 x 320 x 256), CT normalisation and preprocessed arrays. Neither changes evaluation.

## Region-based labels (Z2)

```json
{"output_mode": "regions",
 "label_regions": [["pancreas", [1, 2]], ["mass", [2]]],
 "regions_class_order": [1, 2]}
```

`output_mode: regions` with no regions given binds exactly this Task07 recipe. `label_regions` is an ordered list of `[name, labels]` pairs in output-head order. It is a list, not a mapping, because nnU-Net orders region heads by the order of the `labels` in `dataset.json`, and Segmentary writes its records with sorted keys. The backend writes a region `dataset.json` without sorting, and compares the label order whenever it checks one.

A recipe is accepted only if nnU-Net's decode, `seg[p_i > 0.5] = regions_class_order[i]` in head order, maps each label's own region memberships back to that label. Predictions are therefore native 0/1/2 label maps, and every metric keeps its label-mode definition. `nnunet_regions.decode_regions` reproduces nnU-Net's decode for probability exports. `predict_medical_probabilities.py` records whether the `.npz` channels are softmax classes or sigmoid regions, and refuses to ensemble members that mix the two.

**Reusing the reference arrays (nnU-Net 2.8.1).** `DefaultPreprocessor.run_case_npy` stores the same image and segmentation arrays in both modes. The training transforms convert labels to regions on the fly, and `modify_seg_fn` is the identity. Only the per-case `class_locations` in the `.pkl` differ:

- label mode uses keys `1` (non-mass pancreas) and `2` (mass);
- region mode uses keys `(1, 2)` (all pancreas) and `(2,)` (mass).

`nnUNetDataLoader.get_bbox` picks a nonempty key uniformly and never checks the keys against the label manager. Reused label-mode pickles would therefore train with a different foreground oversampling distribution, without any error.

The plan stage therefore:

1. Copies the reference cache.
2. Writes the region `dataset.json`.
3. In a backend worker, recomputes the label-mode `class_locations` of every case with nnU-Net's own sampler from the copied segmentation. These must equal the reference pickle exactly.
4. Writes the region-mode keys.

The orchestrator then checks that every `.b2nd` array and ground-truth file still has its reference hash, and that only the pickles and `dataset.json` changed. `tests/test_medical_regions.py` checks this path against a full region preprocess of a real case. Arrays, the other properties and `class_locations` match exactly.

HRC in region mode uses `hrc_options` `{"output_mode": "regions", "host_channels": [0], "lesion_channels": [1]}`. The backend requires the HRC output mode to match the run's `output_mode`.

STAR-C region arms (`--arm NAME=starc[:aux_only]` with `--starc-targets` and `--starc-targets-sha256`) use `starc_options` `{"fusion_channels": [0, 1], "lesion_labels": [2]}`. They train `nnUNetTrainerStarC` from scratch at the same budget. The nnFoundation command refuses STAR-C. See the [STAR-C guide](medical-star-completion.md#running-star-c-through-the-backend).

## nnFoundation pretrained encoders (Z4, Z4+HRC)

These runs use a separate nnU-Net master environment:

```json
{"backend_runtime": "nnunet-master-nnssl",
 "backend_python": "/data/izadia1/envs/pancreas-nnssl-20261007/bin/python",
 "runtime_freeze_sha256": "6e257d91...4040", "nnunet_commit": "47766ae3...",
 "pretrained_plan_name": "nnFoundationCNN_8edba046",
 "trainer": "nnUNetTrainerPretrainedDS", "purpose": "finetune",
 "initialization": "pretrained", "init_checkpoint": ".../checkpoint_final.pth",
 "init_checkpoint_sha256": "ac262d3e...",
 "init_allowed_missing_prefixes": ["decoder.", "encoder.stages.6."],
 "num_epochs": 300, "initial_lr": 0.001}
```

**Runtime binding.** nnU-Net master still reports version 2.8.1, so the version alone does not identify it. Every runtime probe therefore records two more things:

- the SHA256 of `python -m pip freeze`;
- the source of the installed `nnunetv2`.

A local-checkout install must come from a clean git checkout whose `.py` tree hashes equal to the installed tree. The commit and the freeze hash must equal the bound values. The dynamic-network-architectures tree hash is recorded in the runtime identity.

**Plan stage.** The plan stage takes these steps:

1. Copies the Wave 1 arrays (and applies the HRC plan transfer for HRC runs).
2. Runs `nnUNetv2_extract_sampling_locations` on the copy.
3. Runs `nnUNetv2_plan_like_dynamic -pl nnUNetResEncUNetLPlans`.

The orchestrator then checks two things:

- Every array, pickle and ground-truth file still has its reference hash, and the only new files are the sampling store and `ptPlans_dynamic__<name>.json`.
- That plan equals the frozen plan apart from its name and `pretrain_info`, and names the bound checkpoint.

**Trainer.** `nnUNetTrainerPretrainedDS` subclasses `DynamicPretrainedTrainer`. It differs from the vendor trainer in five ways:

- It turns deep supervision back on and restores the official toggle.
- It builds any plan class (ResEnc L or `HRCResEncUNet`) through the official `build_network_architecture` signature, which the predictor also uses.
- It takes `num_epochs` and `initial_lr` from the config.
- It keeps the vendor's whole-network warm-up ratio (50 of 1000 epochs, so 15 of 300).
- It does not load weights during `initialize()`.

After `initialize()`, the backend runs the vendor dynamic loader on the SHA256-verified checkpoint bytes, on CPU. It then classifies every tensor independently:

- **Copied:** equals the checkpoint tensor.
- **Adapted:** equals the vendor's z-mean of a 3x3x3 kernel.
- **Random:** unchanged since construction, and under an allowed prefix.

Aliases such as `decoder.encoder.*` and `all_modules.0` are classified once. Anything else fails. `initialization-origin.json` lists every tensor in each category, with parameter counts and the unused checkpoint tensors.

On the real checkpoint and the Task07 plan the counts match P0, for both ResEnc L and HRC:

| Category | Parameters |
| --- | --- |
| Copied | 90,240,416 |
| Adapted (stem and stage-0 kernels) | 18,720 |
| Random encoder (stage 6) | 33,189,120 |

The HRC modules are now built without drawing from the global RNG. With one seed, a plain ResEnc L and an HRC network therefore get identical ResEnc weights, and the paired arms differ only by `hrc.*`.

Resume restores the saved learning-rate scheduler state only into a scheduler of the same class. The pretrained trainers switch from a linear warm-up scheduler to a poly scheduler, and loading one into the other would corrupt the schedule.

## Planning

`scripts/plan_medical_round2_arms.py` reuses the seed/fold planner's frozen inputs. It pins every `GPU:FOLD:SEED:ARM` run to a GPU in 2-9.

```bash
python scripts/plan_medical_round2_arms.py regions <common args> \
  --arm Z2=resenc [--arm Z2HRC=hrc] --run 2:0:0:Z2 ...
python scripts/plan_medical_round2_arms.py pretrained <common args> \
  --nnunet-python /data/izadia1/envs/pancreas-nnssl-20261007/bin/python \
  --arm Z4=resenc --arm Z4HRC=hrc --run 2:0:0:Z4 --run 3:0:0:Z4HRC ...
```

The common arguments are `--source-root`, `--campaign-dir`, `--python`, `--nnunet-python`, `--manifest`, `--splits`, `--cv-splits` and `--reference-workspace`.

Comparison groups:

- Z2 runs use `regions_fold<k>_seed<s>_scratch_250000_steps`.
- Z4 and Z4+HRC runs use `pretrained-nnfoundation_fold<k>_seed<s>_<steps>_steps`. They are never ranked against scratch runs.

The `pretrained` planner probes the interpreter. It refuses to plan unless the freeze hash and the nnU-Net commit equal `--runtime-freeze-sha256` and `--nnunet-commit`, which default to the P0 environment. The campaign runner re-checks both presets when it loads the spec, including the checkpoint hash.
