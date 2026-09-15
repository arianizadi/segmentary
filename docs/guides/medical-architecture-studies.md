# Planning and comparing architecture studies

Use the failure-analysis evidence to name one problem, propose a mechanism, and freeze a comparison before training. These tools prepare reproducible studies and compare completed native predictions. They do not invent a model, establish novelty, certify cohort independence, or launch new training.

Read the [recipe experiments guide](medical-recipe-experiments.md) first. Existing runs, reserved test data, source snapshots and checkpoint lineages remain unchanged.

## What is implemented

| Tool | Input | Output |
|---|---|---|
| `scripts/plan_medical_architecture_study.py` | Base TorchConfig recipe, hypothesis/arm declaration, validated manifest and split, failure-analysis report | Frozen protocol, four roles across explicit seeds, standalone recipe JSON, readable plan |
| `scripts/plan_medical_architecture_study.py --validate` | Saved `study.json` | Rebuilds declarations and rejects recipe, seed, policy or fingerprint drift |
| `scripts/compare_medical_failure_reports.py` | Explicit report/model pair per training seed | Every case pair, missing outcomes, conditional patient bootstrap, per-seed results, descriptive training-seed variation |

Protocols use four roles: **baseline**, **candidate**, **component_off** and **capacity_control**. The default seeds are 0, 1 and 2; planning requires at least two distinct seeds. All roles receive exactly the same declared seeds. Each recipe starts from scratch. Model-options maps are replaced as complete fields, never silently merged.

The component-off arm may be identical to the baseline. In that situation the protocol records the equivalence; it does not pretend this is a distinct architectural mechanism. A capacity control is only a declared role until actual parameter, memory and compute measurements establish that it is a useful comparator.

## Declare a study

Create a JSON definition, for example this **illustration** of already supported deep-supervision options:

```json
{
  "hypothesis": "Auxiliary decoder losses reduce missed small masses under a fixed recipe.",
  "seeds": [0, 1, 2],
  "primary_endpoint": "mass_dice",
  "arms": {
    "baseline": {"description": "Existing DynUNet recipe", "changes": {}},
    "candidate": {
      "description": "Same trunk with auxiliary supervision",
      "changes": {"model_options": {"deep_supervision": true}}
    },
    "component_off": {"description": "Remove auxiliary supervision", "changes": {}},
    "capacity_control": {
      "description": "Wider ordinary DynUNet; verify capacity before launch",
      "changes": {"model_options": {"filters": [40, 80, 160, 256, 320]}}
    }
  }
}
```

Supply every required architecture option when replacing `model_options`. Adapt the example to the actual base recipe; ineffective replacements are rejected. This example is a training-method study, not a claim that deep supervision is novel or that the proposed wider model has matched capacity.

```bash
python scripts/plan_medical_architecture_study.py \
  --base-recipe /absolute/path/control.json \
  --definition /absolute/path/hypothesis.json \
  --manifest /absolute/path/manifest.json \
  --splits /absolute/path/splits.json \
  --cohort-report /absolute/path/failure-report/report.json \
  --source-commit FULL_40_CHARACTER_COMMIT \
  --workspace-root /absolute/path/future-study-workspaces \
  --output /absolute/path/new-study-plan

python scripts/plan_medical_architecture_study.py \
  --validate /absolute/path/new-study-plan/study.json
```

The output directory must not exist. The planner validates the audited manifest and group-safe split, hashes the supplied files, and binds to the failure report's full validation partition and image/reference identities. It does not open image or label payloads, create training workspaces, or allocate a GPU. Source commit is a declared pin, not proof that its checkout is clean or that model code exists.

The generated `study.json` is **not** a `run_medical_campaign.py` campaign. It deliberately records `runnable_campaign: false`. New architectures still need implementation/registration, source/runtime verification, scratch-weight inspection, model-option validation, forward/backward and small-data-fit checks, full-batch GPU profiling, native geometry checks and checkpoint-resume tests. After these gates, create a new supported frozen campaign; do not modify a running campaign's definitions.

Every scientific change is included in the recipe fingerprint and displayed as an exact top-level delta. Changes outside `model`/`model_options` are separately flagged because they confound a pure architecture comparison. Equal optimizer updates do not imply equal training compute. Parameter count, peak memory, end-to-end latency and throughput are measured outcomes, not assumptions made by the planner.

## Compare native failure reports

The input reports use `kind: medical_failure_analysis`, matching cohort bindings and protocol, and complete case inventories. Each case contains a `case_key`, grouped `patient_key`, and per-model status, mass Dice and pancreas Dice. Pancreas means the whole-pancreas union used by the failure report. Dice is on a 0–1 scale.

Create `pairs.json`. Paths are relative to that file unless absolute:

```json
[
  {
    "baseline_report": "seed0/report.json",
    "candidate_report": "seed0/report.json",
    "baseline_model": "control-seed0",
    "candidate_model": "candidate-seed0",
    "training_seed": 0
  },
  {
    "baseline_report": "seed1/report.json",
    "candidate_report": "seed1/report.json",
    "baseline_model": "control-seed1",
    "candidate_model": "candidate-seed1",
    "training_seed": 1
  }
]
```

```bash
python scripts/compare_medical_failure_reports.py \
  --pairs /absolute/path/pairs.json \
  --metric mass_dice \
  --bootstrap-samples 10000 \
  --bootstrap-seed 20260914 \
  --output /absolute/path/new-paired-comparison
```

Run the same command with `--metric pancreas_dice` and a separate output directory for the secondary endpoint. The comparator also accepts a single seed, but explicitly cannot quantify training-seed variability from it. It verifies model seed metadata when present; missing metadata remains an unverified user declaration. Reusing the same checkpoint or identical model evidence as multiple seeds is rejected.

For each metric, the tool:

1. Requires matching manifest, split, validation partition, reference fingerprint, protocol, complete case sets and patient assignments across all reports.
2. Pairs candidate minus baseline for every case and every seed. A missing prediction, failed computation or undefined Dice remains an explicit row. **Any missing required score withholds aggregate inference** instead of reporting a favorable complete-case subset. Reference-empty mass Dice may legitimately be undefined; use a separately declared detection analysis for negative cases rather than fabricating a Dice value.
3. Averages repeated scans within each patient for each seed, then averages paired deltas across seeds. It resamples independent patient groups for the percentile confidence interval. One patient has no interval.
4. Separately reports each seed's result and the sample standard deviation/range of seed-level patient means. This describes training variation; it is not a confidence interval for future training runs.

The patient interval is conditional on the trained seeds. It does not include uncertainty from training randomness, checkpoint selection, hyperparameter search, undiscovered duplicate patients or site clustering. Multiple comparisons are exploratory and uncorrected; the tool never converts an interval into an automatic SOTA or significance claim. A few seeds and 42 repeatedly inspected validation patients are not a substitute for independent confirmation.

## From a useful improvement to an architecture paper

Keep a mechanism-focused hypothesis and primary endpoint. Check that a change helps against the baseline, component-off and a credible capacity control. Inspect lesion-level false positives and misses as well as Dice. Ask the radiology collaborator to adjudicate suspicious reference regions without treating model disagreement as proof that labels are wrong.

Use training/validation evidence to choose an experiment. Before final confirmation, audit source/patient overlap, freeze model selection and evaluation rules, and reserve a suitably annotated independent cohort. NIH organ labels alone do not validate tumor performance. CT-to-CT generalization is cross-dataset rather than cross-modality. Absence of exact image/hash matches does not prove patient independence.

This workflow creates the evidence needed to evaluate an architectural idea. Novelty review, clinical interpretation and independent confirmation remain research work.
