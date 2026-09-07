# Reviewing annotation audits

The annotation audit writes `index.html`, `review-ranked.csv`, and `review-summary.json` alongside its complete JSON evidence and previews. Open `index.html` in your browser, or serve the output directory with `python -m http.server 8765 --directory /path/to/audit` and visit `http://localhost:8765`.

Select a focus class when generating the audit to prioritize that class. The queue puts integrity failures first, then focus candidates, other object losses, background/coverage context, provenance notices, and images without current flags. Search by image name or flag. All original flags remain available in each image's evidence panel.

Focus review candidates include original class unions covering at least 98% of the image, final labels covering at least 50%, individual objects losing at least half their class coverage, and source classes disappearing entirely. These thresholds are transparent review heuristics, not probabilities of annotation errors. Coverage counts the union of source shapes, so overlapping objects are counted once. Background overlap can be expected; foreground geometry frequently carves broad background polygons.

Use the original image and labeled comparisons to decide whether a candidate represents expected occlusion, an unclear class definition, or a correction. Class-pair overwrite events record intermediate painting transitions and can differ from final class loss when later layers repaint a region. Full evidence is retained to explain this distinction.

Verdicts and notes are saved locally in the browser under the audit fingerprint. Export decisions regularly: browser storage may be unavailable for local files or cleared by the browser. The JSON export includes sample keys, splits, annotation and mask hashes, evidence, and review timestamps. It does not modify labels or constitute an automated correction patch. Any approved correction must produce a separate dataset version with provenance; preserve current training inputs and splits.

Review candidates are not confirmed errors. A zero native/training mismatch establishes that the current conversion is reproduced; it does not establish that the original annotations are correct. Missing historical annotation hashes are provenance limitations, not evidence that labels changed.
