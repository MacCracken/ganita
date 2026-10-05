#!/usr/bin/env bash
# run.sh <tree_root> <label> [aarch64]
#   Builds driver.cyr FROM <tree_root> (which must hold src/ and lib/), runs it on the corpus,
#   writes $SVDH_WORK/results_<label>.bin, and scores it: summary_<label>.txt / summary_<label>.json.
#   Compares against $SVDH_WORK/results_base.bin when it exists and the label is not "base".
#   With "aarch64": cross-builds (cyrius build --aarch64), runs under qemu-aarch64, label += _a64,
#   and diffs the results bit for bit against the x86_64 results_<label>.bin when that exists
#   (it says so when it does not).  A label of its own may not end in _a64.
#   Extra build flags (e.g. -D SVDH_NO_RESET) can be passed in DRIVER_FLAGS.
#   $SVDH_WORK defaults to <repo>/build/svdh (see env.sh); the corpus comes from corpus.py.
#   It first removes the label's old driver, results, time and summary, so that none is left from
#   an earlier run: a failed build leaves none of them, a driver that fails only the driver, and
#   a scoring that fails the driver, results and time, without a summary.  Exits non-zero, with a
#   message, when the build, the driver or the scoring fails, when the driver reports a call that
#   modified A (or no count of them), or when the aarch64 results differ from the x86_64 ones.
set -euo pipefail
for a in "$@"; do case "$a" in -h | --help)          # print the header comment above
    awk 'NR == 1 { next } /^#/ { sub(/^# ?/, NR == 2 ? "usage: " : ""); print; next } { exit }' "$0"
    exit 0 ;; esac; done
H="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
[ $# -ge 2 ] && [ $# -le 3 ] || { echo "usage: $0 <tree_root> <label> [aarch64]" >&2; exit 2; }
ARCH="${3:-x86_64}"
[ "$ARCH" = x86_64 ] || [ "$ARCH" = aarch64 ] || {
    echo "run.sh: third argument must be aarch64 (or omitted)" >&2; exit 2; }
T="$1"
case "$T" in -*) T="./$T" ;; esac            # a path, never an option of cd
[ -d "$T" ] || { echo "run.sh: $1 is not a directory" >&2; exit 2; }
# shellcheck source=SCRIPTDIR/env.sh
source "$H/env.sh"
W="$SVDH_WORK"
TREE="$(cd "$T" && pwd)"
LABEL="$2"
svdh_check_label run.sh "$LABEL"
case "$LABEL" in *_a64)
    echo "run.sh: label '$LABEL' ends in _a64, which the aarch64 mode appends:" \
         "use run.sh <tree> ${LABEL%_a64} aarch64" >&2
    exit 2 ;;
esac
[ -d "$TREE/src" ] && [ -e "$TREE/lib" ] || { echo "run.sh: $TREE must contain src/ and lib/" >&2; exit 2; }
for f in corpus.bin corpus_meta.json oracle.json; do
    [ -f "$W/$f" ] || { echo "run.sh: $W/$f missing: run corpus.py first" >&2; exit 2; }
done
XLABEL="$LABEL"
BFLAGS=()
if [ "$ARCH" = "aarch64" ]; then
    LABEL="${LABEL}_a64"
    BFLAGS=(--aarch64)
fi
read -r -a DFLAGS <<< "${DRIVER_FLAGS:-}"
mkdir -p "$W/build"
BIN="$W/build/driver_$LABEL"
OUT="$W/results_$LABEL.bin"
ERR="$W/build/driver_$LABEL.stderr"
TIME="$W/time_$LABEL.txt"
rm -f "$BIN" "$ERR" "$OUT" "$TIME" "$W/summary_$LABEL.txt" "$W/summary_$LABEL.json"
echo "== build ($(svdh_cyrius_version), $ARCH) from $TREE"
( cd "$TREE" && cyrius build "${BFLAGS[@]}" "${DFLAGS[@]}" "$H/driver.cyr" "$BIN" ) 2>&1 |
    grep -v "unreachable fns" || true
[ -x "$BIN" ] || { echo "run.sh: build failed" >&2; exit 1; }
read -r -a RUNNER <<< "$(svdh_runner "$BIN")"     # qemu-aarch64 for an aarch64 driver off aarch64
echo "== run"
t0=$EPOCHREALTIME
if ! "${RUNNER[@]}" "$BIN" < "$W/corpus.bin" > "$OUT" 2> "$ERR"; then
    cat "$ERR" >&2
    rm -f "$OUT" "$ERR"
    echo "run.sh: the driver failed; no results written" >&2
    exit 1
fi
t1=$EPOCHREALTIME
MODIFIED=0
svdh_driver_stderr "$ERR" "driver_$LABEL" || MODIFIED=$?
rm -f "$ERR"
awk -v a="$t0" -v b="$t1" 'BEGIN { printf "driver wall time: %.2f s\n", b - a }' | tee "$TIME"
CHK=("$PY" "$H/check.py" "$OUT" --sub --json "$W/summary_$LABEL.json")
if [ -f "$W/results_base.bin" ] && [ "$XLABEL" != "base" ]; then
    CHK+=(--baseline "$W/results_base.bin")
fi
if ! "${CHK[@]}" | tee "$W/summary_$LABEL.txt"; then
    rm -f "$W/summary_$LABEL.txt" "$W/summary_$LABEL.json"
    echo "run.sh: check.py failed (message above); results_$LABEL.bin and time_$LABEL.txt kept, no summary" >&2
    exit 1
fi
DIFFERS=0
if [ "$ARCH" = "aarch64" ]; then
    if [ -f "$W/results_$XLABEL.bin" ]; then
        echo "== aarch64 vs x86_64 (results_$XLABEL.bin)" | tee -a "$W/summary_$LABEL.txt"
        rc=0
        "$PY" "$H/check.py" "$OUT" --diff "$W/results_$XLABEL.bin" | tee -a "$W/summary_$LABEL.txt" || rc=$?
        case $rc in
            0) ;;
            1) DIFFERS=1 ;;
            *) echo "run.sh: check.py --diff failed (message above)" >&2; exit 1 ;;
        esac
    else
        echo "== aarch64: no results_$XLABEL.bin to compare against (run.sh <tree> $XLABEL first);" \
             "aarch64 results not compared" | tee -a "$W/summary_$LABEL.txt"
    fi
fi
case $MODIFIED in
    0) ;;
    1) echo "run.sh: driver_$LABEL modified A in some call (see its stderr above; results and score kept)" >&2 ;;
    *) echo "run.sh: driver_$LABEL printed no count of modified A (see its stderr above; results and" \
            "score kept)" >&2 ;;
esac
if [ $DIFFERS = 1 ]; then
    echo "run.sh: results_$LABEL.bin is not bit-identical to results_$XLABEL.bin (see the diff above)" >&2
fi
[ $MODIFIED = 0 ] && [ $DIFFERS = 0 ] || exit 1
