#!/usr/bin/env bash
# Apply the ordered Paul-fork patch series to a pristine clone.
#
#   apply_patches.sh hrnet <clone>   # pauls3/semantic-segmentation @ 5e619e6
#   apply_patches.sh sfnet <clone>   # pauls3/SFSegNets-2         @ 0bb9e59
#
# The clone must be a clean git checkout of the exact commit. The whole series is first
# dry-run (`git apply --check`, patch by patch, each on top of the previous one) in a
# scratch export of the clone; only if every patch applies is the clone itself patched.
# Afterwards <clone>/PAUL_PATCHES_APPLIED lists each patch with its sha256 (recipes copy it
# into provenance.json) and <clone>/PAUL_PATCHES_TREE holds the content digest of the
# patched working tree (tree_digest.py); write_provenance.py refuses to launch from a tree
# whose digest no longer matches. Nothing is committed in the clone.
set -euo pipefail

usage() { echo "usage: $0 hrnet|sfnet <clone-dir>" >&2; exit 2; }
[[ $# -eq 2 ]] || usage
fork=$1
target=$2
here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)

case "$fork" in
  hrnet)
    commit=5e619e64803188302c54f4d3d6bcef57de2e57e2
    series=(P0-september-baseline P1-env-paths P2-shape-matched-init P3-best-mud-checkpoint
            P4-dump-preds P5-throughput P6-resume-rng-scaler)
    ;;
  sfnet)
    commit=0bb9e59222bcf996ff8b2510a3318538706a7222
    series=(P0-september-baseline P1-env-paths P1b-rs19-loader-wiring P2-shape-matched-init
            P3-best-mud-checkpoint P4-dump-preds P5-throughput)
    ;;
  *) usage ;;
esac

[[ -d "$target/.git" ]] || { echo "REFUSING: $target is not a git clone" >&2; exit 1; }
head=$(git -C "$target" rev-parse HEAD)
[[ "$head" == "$commit" ]] || { echo "REFUSING: $target is at $head, expected $commit" >&2; exit 1; }
if [[ -n "$(git -C "$target" status --porcelain --untracked-files=all)" ]]; then
  echo "REFUSING: $target is not pristine (git status shows changes)" >&2
  exit 1
fi

patches=()
for name in "${series[@]}"; do
  p="$here/$fork/$name.patch"
  [[ -s "$p" ]] || { echo "REFUSING: missing patch $p" >&2; exit 1; }
  patches+=("$p")
done

scratch=$(mktemp -d)
trap 'rm -rf "$scratch"' EXIT
git -C "$target" archive "$commit" | tar -x -C "$scratch"
for p in "${patches[@]}"; do
  if ! (cd "$scratch" && git apply --check --whitespace=nowarn "$p"); then
    echo "REFUSING: $(basename "$p") does not apply on top of the earlier patches" >&2
    exit 1
  fi
  (cd "$scratch" && git apply --whitespace=nowarn "$p")
done

manifest="$target/PAUL_PATCHES_APPLIED"
: > "$manifest.tmp"
for p in "${patches[@]}"; do
  (cd "$target" && git apply --check --whitespace=nowarn "$p" && git apply --whitespace=nowarn "$p")
  sum=$(sha256sum "$p" 2>/dev/null || shasum -a 256 "$p")
  echo "${sum%% *}  $fork/$(basename "$p")" >> "$manifest.tmp"
  echo "applied $(basename "$p")"
done
mv "$manifest.tmp" "$manifest"
tree=$("${PYTHON:-python3}" "$here/tree_digest.py" "$target" --write)
echo "fork=$fork commit=$commit patches=${#patches[@]} manifest=$manifest tree_digest=$tree"
