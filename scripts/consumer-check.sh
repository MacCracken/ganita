#!/usr/bin/env bash
#
# consumer-check.sh — compile a throwaway consumer against every dist bundle.
#
# ganita's product is `dist/ganita.cyr`, not `build/ganita`.
# `cyrius distlib --check` proves the bundle is regenerable from `src/`; this
# proves the other half of the contract — that a DOWNSTREAM repo can actually
# use it, supplying only the stdlib leaves the `.deps` sidecar declares and
# nothing more.
#
# The distinction matters because `distlib` strips includes. A bundle that
# quietly depends on a module outside its sidecar still builds inside ganita
# (ganita's own `lib/` holds the whole snapshot, and `cyrius build`
# auto-prepends everything in `[deps].stdlib`) while failing in a consumer that
# vendored only the declared leaves. Hence `--no-deps`: the consumer's explicit
# includes are the ONLY stdlib in scope, which is the consumer's real situation.
#
# ganita's sidecar names `math` — the F64_* constants, the f64-builtin polyfills
# the transcendental functions rely on, and (from 1.2.11) the `_f64_rem_pio2`
# reducer behind ganita_f64_tan. Every target needs it at build time.
#
# Usage: scripts/consumer-check.sh [workdir]   (default: build/.consumer-check)
#
set -euo pipefail

OUT="${1:-build/.consumer-check}"
mkdir -p "$OUT"

# Canonical single-pass include order. cyrius is a single-pass compiler, so a
# module may only reference symbols defined earlier — the sidecar says WHICH
# leaves are needed, this list fixes the ORDER they go in.
ORDER="syscalls string alloc io vec str fmt tagged result fnptr math assert bench"

# Bundles known to fail for a reason tracked elsewhere. Empty is the goal: the
# loop below FAILS if a listed bundle starts passing, so an entry cannot
# outlive the bug it stands for.
EXPECTED_FAIL=""

rc=0
for bundle in dist/ganita.cyr dist/ganita-*.cyr; do
    [ -e "$bundle" ] || continue
    name=$(basename "$bundle" .cyr)
    deps="dist/${name}.deps"
    src="$OUT/consume_${name}.cyr"

    # syscalls is unconditional — the consumer body below exits via SYS_EXIT.
    echo 'include "lib/syscalls.cyr"' > "$src"
    if [ -f "$deps" ]; then
        for m in $ORDER; do
            [ "$m" = syscalls ] && continue
            grep -qx "$m" "$deps" && echo "include \"lib/${m}.cyr\"" >> "$src"
        done
        # Any declared leaf this script has no canonical position for still
        # gets included — better a wrong-order compile error than a silent skip.
        while read -r m; do
            case "$m" in ''|'#'*) continue ;; esac
            echo " $ORDER " | grep -q " $m " || echo "include \"lib/${m}.cyr\"" >> "$src"
        done < "$deps"
    fi
    echo "include \"${bundle}\"" >> "$src"
    cat >> "$src" <<'BODY'

fn main(): i64 { return 0; }
var r = main();
syscall(SYS_EXIT, r);
BODY

    # grep -c exits 1 when the count is zero, which under `set -e` would abort
    # the sweep on a legitimately empty sidecar.
    leaves="no sidecar"
    if [ -f "$deps" ]; then
        n=$(grep -cve '^#' -e '^$' "$deps" || true)
        leaves="${n:-0} declared leaf(s)"
    fi

    ok=1
    problems=""
    if out=$(cyrius build --no-deps "$src" "$OUT/${name}.bin" 2>&1); then
        if echo "$out" | grep -q '^warning:'; then
            ok=0; problems=$(echo "$out" | grep '^warning:')
        fi
    else
        ok=0; problems=$(echo "$out" | tail -20)
    fi

    expected=0
    [ -n "$EXPECTED_FAIL" ] && echo " $EXPECTED_FAIL " | grep -q " $name " && expected=1

    if [ "$ok" -eq 1 ] && [ "$expected" -eq 0 ]; then
        echo "ok      ${name} — clean from ${leaves}"
    elif [ "$ok" -eq 1 ] && [ "$expected" -eq 1 ]; then
        echo "FIXED   ${name} — now clean from ${leaves}."
        echo "        Drop it from EXPECTED_FAIL in this script."
        rc=1
    elif [ "$expected" -eq 1 ]; then
        echo "known   ${name} — under-declared sidecar (${leaves}), see EXPECTED_FAIL:"
        echo "$problems" | sed 's/^/          /'
    else
        echo "FAIL    ${name} — does not compile from ${leaves}:"
        echo "$problems" | sed 's/^/          /'
        rc=1
    fi
done

if [ "$rc" -ne 0 ]; then
    echo
    echo "A bundle does not compile from the leaves its .deps sidecar declares."
    echo "Either the sidecar under-declares, or a module gained a dependency it"
    echo "should not have. Regenerate with 'cyrius distlib --all' and re-check."
fi
exit "$rc"
