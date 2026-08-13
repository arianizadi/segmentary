# Legacy custom rail dataset

`loader: custom` preserves the repository's original flat custom-rail format.
For a new general-purpose dataset, prefer the more flexible
[`folder` loader](../folder/README.md).

## Beginner choice

Use this loader only when an existing dataset already follows the legacy layout
and masks use the bundled rail-union semantics. For any new dataset, start with
`loader: folder`, which has stricter manifest-to-disk checks and configurable
directories.

## Required layout

```text
<root>/images/train/<key>.png|jpg|jpeg
<root>/images/val/<key>.png|jpg|jpeg
<root>/masks/train/<key>.png
<root>/masks/val/<key>.png
<root>/splits.json
```

Files are scanned only in each split directory, not recursively. Every image
needs a same-stem PNG mask.

## Mandatory split file and safe groups

`splits.json` itself is mandatory. For video/sequence safety, it must contain
split lists and a complete `groups` mapping from frame key to recording/run. Any
declared group appearing in two splits is fatal. The legacy loader permits an
absent group entry by treating that frame key as its own group; that preserves
old still-image manifests but cannot prove adjacent video frames are separated.
Use the split tool to generate a complete safe tree from unsplit sources:

```bash
segmentary-make-split \
  --images capture/images \
  --masks capture/masks \
  --groups capture/groups.json \
  --out-root data/custom_rail
```

The split utility partitions whole groups, records seed/count/hash metadata,
and refuses to overwrite an existing output root. It can produce symlinks,
hardlinks, or copies according to its CLI options.

## Taxonomy and config

The bundled `rail_union/custom.yaml` is an identity template because legacy
masks are expected to be authored directly in canonical IDs 0 through 20 (plus
255 ignore):

```yaml
data:
  - name: custom
    root: data/custom_rail
```

If an annotation tool emits another indexed schema, edit the mapping YAML. Do
not hide a remap in preprocessing code. A new logical dataset can reuse this
loader with an explicit `mapping`, but the legacy loader still requires
`<root>/splits.json`.

## Pros and cons

Pros:

- strict overlap rejection for groups actually declared in the manifest;
- simple flat files and canonical identity mapping;
- compatible with the shipped custom-stage curricula.

Cons:

- blocked until real custom images, masks, and run groups exist;
- flat, nonrecursive layout and PNG-only masks;
- missing group entries fall back to per-frame identity, and the loader is less
  strict than the generic folder manifest about matching split lists to disk,
  so verification remains essential;
- domain-specific name/layout makes it a compatibility loader, not the best
  public-library default.

## Runnable status and evidence

The `direct`, `rs_custom`, `cs_rs_custom`, and `joint` curricula remain blocked
until this dataset exists at the configured root with a valid manifest. Unit
tests cover required-manifest and cross-split group rejection, but no real custom
dataset size or accuracy benchmark exists. Do not present placeholder configs or
synthetic smoke checks as custom-data evidence.

## Related documentation

- [Dataset catalog](../README.md)
- [Generic folder loader](../folder/README.md)
- [`rail_union` custom mapping](../../../../taxonomy/rail_union/README.md)
- [Custom-data guide](../../../guides/custom-data.md)
- [Curricula requiring custom data](../../curricula/README.md)
