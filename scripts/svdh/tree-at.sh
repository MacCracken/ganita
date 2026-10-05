#!/usr/bin/env bash
# tree-at.sh <git-rev> <dir>
#   Makes <dir> a tree that run.sh / bench.sh / adv/build.sh can build: src/ exported at <git-rev>
#   with 'git archive' (read-only; the working tree is not touched) and lib -> <repo>/lib, the
#   current vendored stdlib. Example, the 1.2.11 baseline (the tag 1.2.11; its src/ is the same
#   tree as commit 1805459's):
#     scripts/svdh/tree-at.sh 1.2.11 build/svdh/tree-1.2.11
#     scripts/svdh/run.sh build/svdh/tree-1.2.11 base
set -euo pipefail
for a in "$@"; do case "$a" in -h | --help)          # print the header comment above
    awk 'NR == 1 { next } /^#/ { sub(/^# ?/, NR == 2 ? "usage: " : ""); print; next } { exit }' "$0"
    exit 0 ;; esac; done
H="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$H/../.." && pwd)"
[ $# -eq 2 ] || { echo "usage: $0 <git-rev> <dir>" >&2; exit 2; }
REV="$1"
DIR="$2"
case "$DIR" in -*) DIR="./$DIR" ;; esac      # a path, never an option of mkdir, tar or ln
git -C "$REPO" rev-parse --verify --quiet "$REV^{commit}" > /dev/null || {
    echo "tree-at.sh: '$REV' is not a commit in $REPO" >&2; exit 2; }
[ ! -e "$DIR" ] || [ -d "$DIR" ] || { echo "tree-at.sh: $DIR exists and is not a directory" >&2; exit 2; }
[ ! -e "$DIR/src" ] && [ ! -e "$DIR/lib" ] || {
    echo "tree-at.sh: $DIR already holds src/ or lib/; pick a new directory" >&2; exit 2; }
mkdir -p "$DIR"
git -C "$REPO" archive "$REV" src | tar -x -C "$DIR"
ln -s "$REPO/lib" "$DIR/lib"
echo "tree-at.sh: $DIR = src/ at $(git -C "$REPO" rev-parse --short "$REV"), lib -> $REPO/lib"
