## VERDICT: APPROVE

No remaining blocker in the delta. This rests on a static read of the guard, tests, qualified manifest, lineage evidence and your recorded audit; I ran nothing and verified nothing live on HDRFS.

### What I checked

- **Manifest delta is metadata-only.** All four City baseline rows are identical in the original and qualified manifests (path, config, SHA). Line offsets (+16/+32/+48) match exactly four 16-line `city_initializer` blocks and nothing else. I could not hash the files, so 85ed2f16…/3026892b… are taken from your audit.
- **Case 1 (mobilenetv2) is valid.**
  - `declared_init_from` and `checkpoint` are the same raw `last.ckpt` path, SHA dfe1a70f…. The City baseline row stays on `last.bn-recalibrated.ckpt` (4f371193…), so City→RAD and City→Rail→RAD each keep their own weights.
  - The guard enforces City19, a single pretrained Cityscapes-only stage, raw-byte hash, and a hashed training receipt in the checkpoint's own directory with matching name, stage and stages (`scripts/verify_rad_initializers.py:130-204`).
  - I did not see the receipt's contents; only your audit result shows it passed.
- **Cases 2–4 are valid.**
  - Each qualified City predecessor is path- and SHA-identical to that model's own approved City row (e7102f15…, 5b371ccb…, 18a79d5f…).
  - The inventory (891eda86…) binds City path and SHA to the Rail endpoint SHA (ebdfc5ac…, 4c64ebd3…, bf38a864…) and to the hashed overlay and eval result. The eval result's single `railsem19` stage names the real City path.
  - In the evidence file, the City and transfer `model` blocks match in full for all three, not just on `arch`.
  - The `/dependency/<model>--cityscapes--seed-0/last.ckpt` placeholders name the same model.
- **No RAD/RTIS tokens** appear in any qualified path, placeholder or evidence path.
- **Audit and freeze.** The recorded audit shows 108 endpoints, 149 jobs (41 recipe, 108 transfer), exactly 4 qualified chains and 4 files hashed. `initialize` stores the audit and `verify_frozen` recomputes it and requires equality (`scripts/run_rtis_campaign.py:93-98, 186-187, 259-261`). The 22 tests are all present in the test file.

### Non-blocking findings

None of these affects the pinned manifest; fix them in the frozen commit only if you are touching the helper anyway.

1. **Placeholder binding is not enforced by evidence kind** (`verify_rad_initializers.py:178-180`). A row with `declared_init_from != checkpoint` and only a `city_training_result` receipt would pass with nothing tying the placeholder to the real file. The four real rows are fine. The fix is to require a `transfer_inventory` proof whenever the two differ.
2. **The same-architecture check is coarse** (`:147-149`). It compares `model.arch` only (`hf_auto`/`native`/`smp`). Adding a `model.checkpoint` equality check against the Rail source config would match what the job check already does at `:379-382`. It holds for cases 2–4 from the evidence; I did not see the mobilenet model block.
3. **Doc wording slightly overstates enforcement** (`docs/guides/rad-2026-11-allclasses.md:134-136, 143-144`). For the three placeholder models the guard hashes the inventory, overlay and eval result, but not the City training receipts; those are recorded only in `city-transfer-lineage-evidence.json`. Suggest saying so.
4. **Do not add those City training receipts as guard evidence as-is.** The accepted City configs carry `head_group_lr_scale: null` in their stages and the older a7c0b67 receipts lack that key, so the strict stages equality at `:196` would fail.
5. **Evidence paths are not checked** for absoluteness or RAD tokens (`:183`, `:222-223`). They are hash-pinned and currently clean.
6. **Test gaps** for the new branches:
   - `declared_init_from` mismatch
   - wrong Rail endpoint SHA in the inventory
   - bound result naming a different `init_from`
   - RAD token in a qualified path
   - architecture mismatch
   - changed overlay or result artifact

### Caveats that stand

- For cases 2–4 the original transfer-run folders are gone, so the lineage is receipt-bound, not reproducible from run directories. The doc states this.
- For case 1 the receipt is tied to the raw file by shared directory and config, not by a checkpoint hash inside the receipt. This is the same path-based standard as the other 32 chains.
- The audit ran against the old plan with the manifest swapped in memory, on a `/tmp` copy. The real gate is the recreated plans: confirm the deployed `RAD_SOURCES` file hashes to 85ed2f16… and that init reports 4 qualified chains.
- All caveats from `rad-2026-11-allclasses-fable-review.md` still apply, including the same-commit GPU smoke and the main/smoke split and audit hash equality check before full launch.

Plan mode asked for a plan file and an exit call; I skipped both because you restricted this to read-only with no writes.
