#!/usr/bin/env bash
# coverage-honest.sh — reference coverage counted on WORD BOUNDARIES, with
# comments stripped.
#
# Why this exists (added 1.2.3, P(-1) sweep). `cyrius coverage` credits a
# function when its name appears as a raw SUBSTRING anywhere in the scanned
# text, comments included. Two consequences, both reproduced:
#
#   1. Every _compat.cyr alias name is a proper substring of the canonical name
#      it forwards to, so exercising `ganita_mat_sub` silently credits
#      `mat_sub`, and `ganita_mat_submatrix` credits both. That is how
#      _compat.cyr read as 40/53 when the honest figure was 4/53.
#   2. A bare COMMENT moves the gate. Appending one line naming
#      `ganita_mat_print(` — which is called nowhere in the repo — to
#      tests/ganita.tcyr moved the reported total from 109/135 (80%) to
#      111/135 (82%).
#
# At 1.2.2 the tool said 80% with the CI gate at --min 80: zero margin, held up
# by the artifact. The honest count was 53%.
#
# This script does NOT replace `cyrius coverage` in CI — the tool's figure is
# still a ratchet, and it sees things a regex does not. This runs alongside it so
# the number that can be moved by a comment is not the only number being gated.
#
# Usage:  ./scripts/coverage-honest.sh [min_percent]
set -euo pipefail
cd "$(dirname "$0")/.."

MIN="${1:-0}"

python3 - "$MIN" <<'PY'
import re, sys, glob

min_pct = int(sys.argv[1])

# Everything that can legitimately REFERENCE a public function: the suites, the
# entry points, and the examples (which CI builds and runs, so a call there is a
# real exercise of the function, not a mention of it).
scanned = []
for pat in ("tests/*.tcyr", "tests/*.bcyr", "tests/*.fcyr",
            "src/main.cyr", "src/test.cyr", "docs/examples/*.cyr"):
    for f in sorted(glob.glob(pat)):
        scanned.append(open(f).read())

# Strip whole-line comments: a name in prose is not a call.
text = "\n".join(
    "\n".join(l for l in blob.split("\n") if not l.lstrip().startswith("#"))
    for blob in scanned
)

total = 0
referenced = 0
rows = []
for src in sorted(glob.glob("src/*.cyr")):
    names = re.findall(r'^fn (\w+)', open(src).read(), re.M)
    if not names:
        continue
    # A reference is the name followed by '(' and NOT preceded by an identifier
    # character — which is exactly what the substring match fails to require.
    hit = [n for n in names
           if re.search(r'(?<![A-Za-z0-9_])' + re.escape(n) + r'\s*\(', text)]
    rows.append((src, len(hit), len(names)))
    total += len(names)
    referenced += len(hit)

pct = (100 * referenced) // total if total else 0

print("  mode: word-boundary reference coverage (comments stripped)")
print("  scope: src/*.cyr referenced from tests/, entry points, and docs/examples/")
print()
for src, h, n in rows:
    flag = "  " if h == n else "<-"
    print(f"  {src:26} {h:3}/{n:3} fns  {flag}")
print()
print(f"  Functions referenced: {referenced}/{total} ({pct}%)")

if min_pct:
    if pct < min_pct:
        print(f"::error::honest coverage {pct}% is below the --min {min_pct}% floor")
        sys.exit(1)
    print(f"  gate OK: {pct}% >= {min_pct}%")
PY
