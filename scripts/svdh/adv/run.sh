#!/usr/bin/env bash
# run.sh <corpus_dir> <label>...
#   Runs each label's drivers (build.sh) on <corpus_dir>/corpus.bin: <corpus_dir>/results_<L>.bin,
#   times_<L>.bin (ns per call: full, values-only) and rcp_<L>.bin.
#   <corpus_dir> is a directory; without a '/' it names one under $SVDH_WORK (adv, adv2).  A label
#   given twice is refused.
#   A label <X>_a64 names the aarch64 drivers of `build.sh <X> <tree> aarch64`, which must be
#   aarch64 binaries; they run under qemu-aarch64.  After every label has run, their files are
#   compared with those of <X> when these exist (from this run when <X> is among the labels,
#   whatever the order; else from an earlier one): the results must be bit-identical, and the rcp
#   files identical up to the sign of NaN entries of pseudo_inv (rcpcmp.py, which needs $PY with
#   numpy; run.sh checks $PY, as the other scripts do, only when a label ends in _a64).
#   A driver that fails is reported and its partial output removed; run.sh still runs the other
#   drivers, then exits 1.  It also exits 1 when a driver reports a call that modified A (or no
#   count of them), or when an aarch64 comparison fails.
set -euo pipefail
for a in "$@"; do case "$a" in -h | --help)          # print the header comment above
    awk 'NR == 1 { next } /^#/ { sub(/^# ?/, NR == 2 ? "usage: " : ""); print; next } { exit }' "$0"
    exit 0 ;; esac; done
H="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
[ $# -ge 2 ] || { echo "usage: $0 <corpus_dir> <label>..." >&2; exit 2; }
SVDH_NEED_PY=0                                # Python runs only for an _a64 label (rcpcmp.py)
for a in "${@:2}"; do case "$a" in *_a64) SVDH_NEED_PY=1 ;; esac; done
# shellcheck source=SCRIPTDIR/../env.sh
source "$H/../env.sh"
D="$SVDH_WORK/build"
C="$1"; shift
case "$C" in */*) ;; *) C="$SVDH_WORK/$C" ;; esac
case "$C" in -*) C="./$C" ;; esac            # a path, never an option of rcpcmp.py
[ -f "$C/corpus.bin" ] || { echo "run.sh: $C/corpus.bin missing: run gen.py first" >&2; exit 2; }
SEEN=" "
for L in "$@"; do
  svdh_check_label run.sh "$L"
  case "$SEEN" in *" $L "*) echo "run.sh: label $L given twice" >&2; exit 2 ;; esac
  SEEN="$SEEN$L "
  case "$L" in *_a64) how="${L%_a64} <tree> aarch64" ;; *) how="$L [<tree>]" ;; esac
  [ -x "$D/drv_$L" ] && [ -x "$D/rcp_$L" ] || {
    echo "run.sh: no drivers for $L: run build.sh $how first" >&2; exit 2; }
  case "$L" in *_a64)
    for b in drv rcp; do
      svdh_is_aarch64 "$D/${b}_$L" || {
        echo "run.sh: $D/${b}_$L is not an aarch64 binary: rebuild it with build.sh $how" >&2; exit 2; }
    done ;;
  esac
done
FAILED=()
ERR="$D/run_adv.$$.stderr"
trap 'rm -f "$ERR"' EXIT
# stderr_check NAME: svdh_driver_stderr on $ERR, adding NAME to FAILED when the count is not 0.
stderr_check() {
  local rc=0
  svdh_driver_stderr "$ERR" "$1" || rc=$?
  case $rc in
    0) ;;
    1) FAILED+=("$1 (modified A)") ;;
    *) FAILED+=("$1 (no modified-A count)") ;;
  esac
}
for L in "$@"; do
  read -r -a RUN <<< "$(svdh_runner "$D/drv_$L")"
  t0=$EPOCHREALTIME
  if ! "${RUN[@]}" "$D/drv_$L" < "$C/corpus.bin" > "$C/results_$L.bin" 3> "$C/times_$L.bin" 2> "$ERR"; then
    cat "$ERR" >&2
    echo "run.sh: drv_$L failed; removed its partial results_$L.bin and times_$L.bin" >&2
    rm -f "$C/results_$L.bin" "$C/times_$L.bin"
    FAILED+=("drv_$L")
  else
    stderr_check "drv_$L"
  fi
  t1=$EPOCHREALTIME
  read -r -a RUN <<< "$(svdh_runner "$D/rcp_$L")"
  if ! "${RUN[@]}" "$D/rcp_$L" < "$C/corpus.bin" > "$C/rcp_$L.bin" 2> "$ERR"; then
    cat "$ERR" >&2
    echo "run.sh: rcp_$L failed; removed its partial rcp_$L.bin" >&2
    rm -f "$C/rcp_$L.bin"
    FAILED+=("rcp_$L")
  else
    stderr_check "rcp_$L"
  fi
  t2=$EPOCHREALTIME
  awk -v a="$t0" -v b="$t1" -v c="$t2" -v l="$L" \
    'BEGIN { printf "%s: driver wall %.2f s, rcp wall %.2f s\n", l, b - a, c - b }'
done
# The aarch64 comparisons, once every label has run.
for L in "$@"; do
  case "$L" in *_a64) ;; *) continue ;; esac
  X="${L%_a64}"
  if [ -f "$C/results_$L.bin" ] && [ -f "$C/results_$X.bin" ]; then
    if cmp -s "$C/results_$L.bin" "$C/results_$X.bin"; then
      echo "$L: results_$L.bin is bit-identical to results_$X.bin"
    else
      echo "$L: results_$L.bin DIFFERS from results_$X.bin"
      FAILED+=("results_$L.bin (differs from results_$X.bin)")
    fi
  else
    echo "$L: results_$L.bin or results_$X.bin missing: aarch64 results not compared"
  fi
  if [ -f "$C/rcp_$L.bin" ] && [ -f "$C/rcp_$X.bin" ]; then
    if cmp -s "$C/rcp_$L.bin" "$C/rcp_$X.bin"; then
      echo "$L: rcp_$L.bin is bit-identical to rcp_$X.bin"
    else
      rc=0
      "$PY" "$H/rcpcmp.py" "$C/rcp_$L.bin" "$C/rcp_$X.bin" --corpus "$C/corpus.bin" || rc=$?
      case $rc in
        0) ;;
        1) FAILED+=("rcp_$L.bin (differs from rcp_$X.bin)") ;;
        *) FAILED+=("rcpcmp.py on rcp_$L.bin (message above)") ;;
      esac
    fi
  else
    echo "$L: rcp_$L.bin or rcp_$X.bin missing: aarch64 rcp files not compared"
  fi
done
if [ ${#FAILED[@]} -gt 0 ]; then
  echo "run.sh: failed: ${FAILED[*]}" >&2
  exit 1
fi
