# Could the split underrepresent different mass types?

**Yes. Our current split preserves known groups but does not stratify by lesion subtype.** We cannot currently measure subtype coverage because the inspected Task07 release and our manifest do not provide a trustworthy per-case subtype or histology field. This is a plausible source of variation in generalization, not a demonstrated explanation for the whole performance gap.

The official challenge paper describes the mass target as including cysts or tumors. The shared mass label is therefore not a diagnosis of PDAC or a separate label for each disease subtype. [Medical Segmentation Decathlon paper](https://www.nature.com/articles/s41467-022-30695-9) ([open-access record](https://pmc.ncbi.nlm.nih.gov/articles/PMC9287542/)).

## What the actual split does

`make_splits` forms connected groups from known patient/duplicate relationships, sorts those groups, shuffles them with seed 0, and allocates 70/15/15 percent of groups. It does not balance subtype, size, CT appearance, lesion location, or acquisition characteristics. Replaying this grouped shuffle reproduces the frozen memberships exactly.

| Partition | Scans | Connected groups | Use in this investigation |
| --- | ---: | ---: | --- |
| Training | 197 | 196 | Complete training-fit and input audits |
| Validation | 42 | 42 | Model development and native-volume evaluation |
| Reserved test | 42 | 42 | Membership metadata only; image and label payloads unopened |

The extra training scan belongs to a duplicate-image pair: both CT file hashes and decoded image hashes match, and both scans remain exclusively in training. Their supplied annotations differ. Native comparison verifies matching geometry and substantial overlap, with differences in extent and boundaries. This is a source of inconsistent training targets; it does not establish that either annotation is clinically wrong or explain the full model gap. Detailed measurements and CT panels stay in the private review package. The grouping prevents this known pair from leaking across partitions; it does not resolve annotation consistency. Independent patient identity is still unverified (`dataset_case_unverified`).

The release's `dataset.json` literally names its labels background, pancreas and cancer (0/1/2); our evaluation calls label 2 mass to avoid treating the label name as verified histology. It supplies image/label paths. The frozen manifest adds geometry, label counts, hashes and grouping information, but no case-level histology or subtype mapping. This finding concerns the metadata inspected here, not a claim that additional metadata cannot exist elsewhere.

## What the existing evidence can and cannot tell us

Central mass-size distributions are similar: training median 6.04 mL versus validation 5.82 mL, with similar quartiles. Their extreme tails differ: maximum 732.39 mL in training versus 91.47 mL in validation. **Size does not establish histology**, and matching size distributions does not establish subtype balance.

A rare appearance or subtype could be absent or sparsely represented in training or validation under this random allocation. We do not have verified subtype labels to count such cases. We also cannot infer subtype from the fact that several models miss the same scans.

The stronger nnU-Net system scores 54.68–55.90% mass Dice on these same 42 validation scans versus 32.98% for the common DynUNet control. Thus this split permits substantially better performance; subtype imbalance could contribute to the gap or its variability, but it does not impose a universal 30% limit.

The observable metadata also shows sparse tails: only two training scans and one validation scan have a mass smaller than 1 mL. Training has no 7.5 mm superior–inferior voxel spacing, while validation has one such scan. These are acquisition/size coverage findings, not clinical subtype labels or proof that they caused failures. Exact counts, ranges and provenance are in the [aggregate split audit](split-coverage.json).

## Next study design

1. Obtain a trustworthy case-to-diagnosis mapping if available from the source investigators. Separately ask the radiology team to annotate observable appearance, lesion location and annotation uncertainty. A CT impression should not be presented as pathology-confirmed histology; retain an explicit unknown category.
2. Audit counts and performance by these prespecified groups, with uncertainty and subgroup denominators. Keep difficult cases and unknown subtypes visible.
3. For a later robustness study, use group-preserving cross-validation within the 239 development scans and balance verified categories where counts permit. Apply the same folds to every compared model. Very rare categories cannot be guaranteed in every fold.
4. Preserve the existing 42-case test reservation. Do not repeatedly reshuffle the current validation set to find a higher score. The new two-seed loss experiment holds the split fixed and tests training randomness, not split sensitivity.

[Back to the full investigation](README.md)
