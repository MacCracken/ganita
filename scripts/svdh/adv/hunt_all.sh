#!/usr/bin/env bash
# hunt_all.sh <label>
#   The oracle-free hunt behind the 1.2.12 claim, 819,998 matrices (2 of the 820,000 drawn are
#   skipped as non-finite): seeds 101-116 x 20000 and 201-206 x 30000 over all families,
#   301-308 x 20000 --fam eqn, 401-408 x 20000 --fam subrow, 10 hunt.py at a time.
#   Needs $SVDH_WORK/build/drv_<label> (build.sh). Logs: $SVDH_WORK/hunt_logs/s<seed>.log, each
#   ending in the line 'hunt.py exit N'; hits: $SVDH_WORK/hunt_hits/seed<seed>.json (hunt.py adds
#   to the files already there).
#   Exits 1, naming the seeds, when a seed's hunt.py did not exit 0 (a driver failed, or hunt.py
#   itself did), or its log has no 'status {' line or has a 'DRIVER FAILED' line.
set -euo pipefail
for a in "$@"; do case "$a" in -h | --help)          # print the header comment above
    awk 'NR == 1 { next } /^#/ { sub(/^# ?/, NR == 2 ? "usage: " : ""); print; next } { exit }' "$0"
    exit 0 ;; esac; done
H="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
[ $# -eq 1 ] || { echo "usage: $0 <label>" >&2; exit 2; }
# shellcheck source=SCRIPTDIR/../env.sh
source "$H/../env.sh"
L="$1"
svdh_check_label hunt_all.sh "$L"
case "$L" in *_a64) how="${L%_a64} <tree> aarch64" ;; *) how="$L [<tree>]" ;; esac
[ -x "$SVDH_WORK/build/drv_$L" ] || { echo "hunt_all.sh: no driver for $L: run build.sh $how first" >&2; exit 2; }
LOGS="$SVDH_WORK/hunt_logs"
mkdir -p "$LOGS"
# run SEED ARGS...: one hunt.py, its exit status appended to its log (as the last line).
run() {
    local s=$1 rc=0
    shift
    "$PY" "$H/hunt.py" "$s" "$@" --labels "$L" > "$LOGS/s$s.log" 2>&1 || rc=$?
    echo "hunt.py exit $rc" >> "$LOGS/s$s.log"
    return "$rc"
}
export -f run; export H PY L LOGS
schedule() {
    for s in $(seq 101 116); do echo "$s 20000"; done
    for s in $(seq 201 206); do echo "$s 30000"; done
    for s in $(seq 301 308); do echo "$s 20000 --fam eqn"; done
    for s in $(seq 401 408); do echo "$s 20000 --fam subrow"; done
}
for s in $(schedule | awk '{ print $1 }'); do rm -f "$LOGS/s$s.log"; done    # no stale log counts
# xargs exits non-zero when a hunt.py does; each seed is judged from its own log below instead.
schedule | xargs -P 10 -L 1 bash -c 'run "$@"' _ || true
BAD=()
for s in $(schedule | awk '{ print $1 }'); do
    log="$LOGS/s$s.log"
    if [ ! -f "$log" ] || [ "$(tail -n 1 "$log")" != "hunt.py exit 0" ] || ! grep -q 'status {' "$log" ||
        grep -q 'DRIVER FAILED' "$log"; then
        BAD+=("$s")
    fi
done
if [ ${#BAD[@]} -gt 0 ]; then
    echo "hunt_all.sh: FAILED seeds: ${BAD[*]} (see $LOGS/s<seed>.log)" >&2
    exit 1
fi
echo "hunt_all.sh: done, $(schedule | wc -l) seeds, logs in $LOGS"
