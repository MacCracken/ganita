#!/usr/bin/env bash
# run.sh <setdir> <label>
#   Runs $SVDH_WORK/build/driver_<label> (built by ../run.sh <tree> <label>) on <setdir>/corpus.bin
#   and scores it with ../check.py against the set's own oracle: <setdir>/res_<label>.bin,
#   summary_<label>.txt, summary_<label>.json (the old summary is removed first).
#   <setdir> is a directory; without a '/' it names one under $SVDH_WORK/hunts (gen.py / mkwit.py).
#   A label <X>_a64 names the aarch64 driver of `../run.sh <tree> <X> aarch64`, which must be an
#   aarch64 binary; it runs under qemu-aarch64, and its results are compared bit for bit with
#   res_<X>.bin when that exists (it says so when it does not).
#   Exits non-zero, with a message, when the driver or the scoring fails, when the driver reports
#   a call that modified A (or no count of them), or when the aarch64 results differ from
#   res_<X>.bin.  A driver that fails leaves no res_<label>.bin; a scoring that fails (check.py
#   refuses results of the wrong length, for one) keeps res_<label>.bin, without a summary.
set -euo pipefail
for a in "$@"; do case "$a" in -h | --help)          # print the header comment above
    awk 'NR == 1 { next } /^#/ { sub(/^# ?/, NR == 2 ? "usage: " : ""); print; next } { exit }' "$0"
    exit 0 ;; esac; done
H="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
[ $# -eq 2 ] || { echo "usage: $0 <setdir> <label>" >&2; exit 2; }
# shellcheck source=SCRIPTDIR/../env.sh
source "$H/../env.sh"
D="$1"
L="$2"
svdh_check_label run.sh "$L"
case "$D" in */*) ;; *) D="$SVDH_WORK/hunts/$D" ;; esac
case "$D" in -*) D="./$D" ;; esac            # a path, never an option of check.py
DRV="$SVDH_WORK/build/driver_$L"
for f in corpus.bin corpus_meta.json oracle.json; do
    [ -f "$D/$f" ] || { echo "run.sh: $D/$f missing: run gen.py or mkwit.py first" >&2; exit 2; }
done
case "$L" in *_a64) how="<tree> ${L%_a64} aarch64" ;; *) how="<tree> $L" ;; esac
if [ ! -x "$DRV" ]; then
    echo "run.sh: $DRV missing: run scripts/svdh/run.sh $how first" >&2
    exit 2
fi
case "$L" in *_a64)
    svdh_is_aarch64 "$DRV" || {
        echo "run.sh: $DRV is not an aarch64 binary: rebuild it with scripts/svdh/run.sh $how" >&2; exit 2; } ;;
esac
read -r -a RUN <<< "$(svdh_runner "$DRV")"
ERR="$D/driver_$L.stderr"
rm -f "$D/summary_$L.txt" "$D/summary_$L.json" "$ERR"
if ! "${RUN[@]}" "$DRV" < "$D/corpus.bin" > "$D/res_$L.bin" 2> "$ERR"; then
    cat "$ERR" >&2
    rm -f "$D/res_$L.bin" "$ERR"
    echo "run.sh: driver_$L failed; no results written" >&2
    exit 1
fi
MODIFIED=0
svdh_driver_stderr "$ERR" "driver_$L" || MODIFIED=$?
rm -f "$ERR"
SET=(--corpus "$D/corpus.bin" --meta "$D/corpus_meta.json")
if ! "$PY" "$H/../check.py" "$D/res_$L.bin" "${SET[@]}" --oracle "$D/oracle.json" \
        --sub --top 30 --json "$D/summary_$L.json" > "$D/summary_$L.txt"; then
    rm -f "$D/summary_$L.txt" "$D/summary_$L.json"
    echo "run.sh: check.py failed (message above); res_$L.bin kept, no summary" >&2
    exit 1
fi
cat "$D/summary_$L.txt"
DIFFERS=0
case "$L" in
    *_a64)
        X="${L%_a64}"
        if [ -f "$D/res_$X.bin" ]; then
            echo "== aarch64 vs x86_64 (res_$X.bin)" | tee -a "$D/summary_$L.txt"
            rc=0
            "$PY" "$H/../check.py" "$D/res_$L.bin" "${SET[@]}" --diff "$D/res_$X.bin" |
                tee -a "$D/summary_$L.txt" || rc=$?
            case $rc in
                0) ;;
                1) DIFFERS=1 ;;
                *) echo "run.sh: check.py --diff failed (message above)" >&2; exit 1 ;;
            esac
        else
            echo "== aarch64: no res_$X.bin to compare against (run.sh <set> $X first);" \
                 "aarch64 results not compared" | tee -a "$D/summary_$L.txt"
        fi ;;
esac
case $MODIFIED in
    0) ;;
    1) echo "run.sh: driver_$L modified A in some call (see its stderr above; results and score kept)" >&2 ;;
    *) echo "run.sh: driver_$L printed no count of modified A (see its stderr above; results and" \
            "score kept)" >&2 ;;
esac
if [ $DIFFERS = 1 ]; then
    echo "run.sh: res_$L.bin is not bit-identical to res_$X.bin (see the diff above)" >&2
fi
[ $MODIFIED = 0 ] && [ $DIFFERS = 0 ] || exit 1
