#!/usr/bin/env bash
# bench.sh <tree_root> <label>
#   Builds bench.cyr from <tree_root> (which must hold src/ and lib/) into
#   $SVDH_WORK/build/bench_<label>, runs it, and prints and saves its timings in
#   $SVDH_WORK/bench_<label>.txt ($SVDH_WORK defaults to <repo>/build/svdh, see env.sh).
#   It first removes the label's old binary and timings; exits non-zero when the build fails.
set -euo pipefail
for a in "$@"; do case "$a" in -h | --help)          # print the header comment above
    awk 'NR == 1 { next } /^#/ { sub(/^# ?/, NR == 2 ? "usage: " : ""); print; next } { exit }' "$0"
    exit 0 ;; esac; done
H="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
[ $# -eq 2 ] || { echo "usage: $0 <tree_root> <label>" >&2; exit 2; }
T="$1"
case "$T" in -*) T="./$T" ;; esac            # a path, never an option of cd
[ -d "$T" ] || { echo "bench.sh: $1 is not a directory" >&2; exit 2; }
SVDH_NEED_PY=0
# shellcheck source=SCRIPTDIR/env.sh
source "$H/env.sh"
W="$SVDH_WORK"
TREE="$(cd "$T" && pwd)"
LABEL="$2"
svdh_check_label bench.sh "$LABEL"
[ -d "$TREE/src" ] && [ -e "$TREE/lib" ] || { echo "bench.sh: $TREE must contain src/ and lib/" >&2; exit 2; }
mkdir -p "$W/build"
BIN="$W/build/bench_$LABEL"
rm -f "$BIN" "$W/bench_$LABEL.txt"
( cd "$TREE" && cyrius build "$H/bench.cyr" "$BIN" ) 2>&1 | grep -v "unreachable fns" || true
[ -x "$BIN" ] || { echo "bench.sh: build failed" >&2; exit 1; }
{ echo "bench $LABEL  tree=$TREE  $(svdh_cyrius_version)  $(date -Is)"; "$BIN"; } | tee "$W/bench_$LABEL.txt"
