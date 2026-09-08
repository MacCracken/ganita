#!/usr/bin/env bash
# bench-history.sh — run ganita's Cyrius benchmark suite and append the results
# to a CSV history with the measurement regime recorded alongside each row.
#
# Usage:
#   ./scripts/bench-history.sh                       # tests/ganita.bcyr -> bench-history.csv
#   ./scripts/bench-history.sh results.csv           # custom output
#   ./scripts/bench-history.sh "" tests/other.bcyr   # a different suite
#
# Added at 1.2.3 for the P(-1) sweep, which requires a baseline before the
# refactor pass and a comparison after it (steps 3 and 8). Adapted from naad's
# script of the same name; the regime/floor_ns discipline below is its work.
set -euo pipefail

cd "$(dirname "$0")/.."

HISTORY_FILE="${1:-bench-history.csv}"
SUITES="${2:-tests/ganita.bcyr}"
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
COMMIT=$(git rev-parse --short HEAD 2>/dev/null || echo "uncommitted")
BRANCH=$(git branch --show-current 2>/dev/null || echo "unknown")

# Every `cyrius` call re-resolves deps; concurrent runs can race. Serialize.
LOCK="${GANITA_BUILD_LOCK:-${TMPDIR:-/tmp}/ganita-build.lock}"

# Schema. `stat` names WHICH statistic estimate_ns holds; `regime` names what the
# INSTRUMENT was doing when it was taken. They are independent, and the second is
# the one that silently invalidates cross-run comparison.
#
# Since cyrius 6.5.19 lib/bench.cyr calibrates one clock read on the host and
# subtracts it from every sample. That matters more here than almost anywhere:
# ganita's f32 rows report 2-5 ns against a measured floor of ~1.3 us, i.e. the
# floor is ~300x the quantity being reported. Those rows are only meaningful
# because each is batched over 1,000,000 iterations AND has the floor removed.
# A row taken under the pre-6.5.19 instrument is not a smaller version of the
# same measurement; it is a measurement of the clock.
#
# regime is DERIVED, not declared — read from whether this run's harness printed
# its own measured floor — so it cannot go stale the way a hand-maintained
# constant does. floor_ns records what the clock cost on THIS host, THIS boot:
# lib/bench.cyr records a single machine producing both ~400 ns and ~1,700 ns
# across reboots. It is not a property of the code, so it must travel with the row.
CSV_HEADER="timestamp,commit,branch,suite,benchmark,estimate_ns,stat,avg_ns,min_ns,max_ns,iters,regime,floor_ns"
if [ ! -f "$HISTORY_FILE" ]; then
    echo "$CSV_HEADER" > "$HISTORY_FILE"
elif ! head -1 "$HISTORY_FILE" | grep -q ',regime,'; then
    sed -i "1s/.*/${CSV_HEADER}/" "$HISTORY_FILE"
    echo "note: bench-history header widened with regime/floor_ns; earlier rows read back as regime=''"
fi

echo "=== ganita benchmark run ==="
echo "  commit:    $COMMIT"
echo "  branch:    $BRANCH"
echo "  timestamp: $TIMESTAMP"
echo "  suites:    $SUITES"
echo ""

normalize_to_ns() {
    awk -v v="$1" -v u="$2" 'BEGIN{
        if (u == "ps")                   printf "%.4f", v / 1000;
        else if (u == "ns")              printf "%s",   v;
        else if (u == "us" || u == "µs") printf "%.4f", v * 1000;
        else if (u == "ms")              printf "%.4f", v * 1000000;
        else if (u == "s")               printf "%.4f", v * 1000000000;
        else                             printf "%s",   v;
    }'
}

TOTAL=0
SKIPPED=0

for SUITE in $SUITES; do
    [ -f "$SUITE" ] || { echo "ERROR: no such suite: $SUITE" >&2; exit 1; }
    OUTPUT=$(flock "$LOCK" cyrius bench "$SUITE" 2>&1 | sed 's/\x1b\[[0-9;]*m//g')
    echo "$OUTPUT"
    echo ""

    # Regime, read off the harness's own output rather than declared here. Since
    # 6.5.19 bench_report prints, once per process:
    #   [timer floor 1.349us per clock read, measured; subtracted from every sample]
    # Presence of that line IS the marker. Absent -> the pre-6.5.19 instrument,
    # whose numbers include the clock. The two populations must never be averaged.
    REGIME=""
    FLOOR_NS=""
    if [[ "$OUTPUT" =~ \[timer\ floor\ ([0-9]+(\.[0-9]+)?)(ps|ns|µs|us|ms|s)\ per\ clock\ read ]]; then
        REGIME="net"
        FLOOR_NS=$(normalize_to_ns "${BASH_REMATCH[1]}" "${BASH_REMATCH[3]}")
        echo "  regime: net (timer floor ${FLOOR_NS} ns, measured on this host/boot, subtracted per sample)"
    else
        REGIME="raw"
        echo "  regime: raw (no measured floor reported — pre-6.5.19 instrument)"
    fi
    echo ""

    # Anchored on the harness's own field names, NOT by scavenging the last number
    # in the line — that trick records the max= field. ganita's benchmark names
    # contain spaces, parens and '=' ("least_squares m=5793 n=3 (was SIGSEGV)"),
    # so the name group is permissive and the line is disambiguated by the literal
    # " avg (min=" that follows it. A line that looks like a result but does not
    # parse is COUNTED and fails the run: a format change upstream must be loud,
    # not quietly halve the history.
    while IFS= read -r line; do
        if [[ "$line" =~ ^[[:space:]]*([A-Za-z_][^:]*):[[:space:]]+([0-9]+(\.[0-9]+)?)(ps|ns|µs|us|ms|s)[[:space:]]+avg[[:space:]]+\(min=([0-9]+(\.[0-9]+)?)(ps|ns|µs|us|ms|s)[[:space:]]+max=([0-9]+(\.[0-9]+)?)(ps|ns|µs|us|ms|s)\)([[:space:]]+\[([0-9]+)[[:space:]]+iters\])? ]]; then
            NAME="${BASH_REMATCH[1]}"
            AVG_NS=$(normalize_to_ns "${BASH_REMATCH[2]}"  "${BASH_REMATCH[4]}")
            MIN_NS=$(normalize_to_ns "${BASH_REMATCH[5]}"  "${BASH_REMATCH[7]}")
            MAX_NS=$(normalize_to_ns "${BASH_REMATCH[8]}"  "${BASH_REMATCH[10]}")
            ITERS="${BASH_REMATCH[12]:-}"
            printf '%s,%s,%s,%s,"%s",%s,avg,%s,%s,%s,%s,%s,%s\n' \
                "$TIMESTAMP" "$COMMIT" "$BRANCH" "$SUITE" "$NAME" \
                "$AVG_NS" "$AVG_NS" "$MIN_NS" "$MAX_NS" "$ITERS" \
                "$REGIME" "$FLOOR_NS" >> "$HISTORY_FILE"
            TOTAL=$((TOTAL + 1))
        elif echo "$line" | grep -qE '^[[:space:]]+[A-Za-z_].*:[[:space:]]+[0-9.]+(ps|ns|us|ms|s)' \
             && ! echo "$line" | grep -q 'timer floor'; then
            SKIPPED=$((SKIPPED + 1))
            echo "::warning:: unparsed benchmark line (format drift?): $line" >&2
        fi
    done <<< "$OUTPUT"
done

if [ "$SKIPPED" -gt 0 ]; then
    echo "ERROR: $SKIPPED benchmark line(s) did not match the expected format;" >&2
    echo "       lib/bench.cyr's output shape has changed — fix the parser." >&2
    exit 1
fi
if [ "$TOTAL" -eq 0 ]; then
    echo "ERROR: no benchmarks parsed — refusing to write an empty history." >&2
    exit 1
fi

echo "=== $TOTAL row(s) appended to $HISTORY_FILE ==="
echo ""
echo "Trend comparison MUST filter on regime: rows either side of the 6.5.19"
echo "instrument boundary are all stat=avg, so comparing them on stat alone"
echo "reports pure artefact as improvement. Never compare a 'raw' row to a"
echo "'net' one, and treat floor_ns as part of a row's identity — the floor"
echo "moves between reboots on a single host, by as much as 4x."
