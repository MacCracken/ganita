#!/usr/bin/env bash
# build.sh <label> [<tree_root> [aarch64]]
#   Builds driver_adv.cyr and driver_rcp.cyr from <tree_root> (as cwd, like ../run.sh; default:
#   the repository) into $SVDH_WORK/build/drv_<label> and rcp_<label>, after removing the old
#   ones.  With "aarch64": cross-builds them (cyrius build --aarch64) as drv_<label>_a64 and
#   rcp_<label>_a64; run.sh, hunt.py and tall_study.py run those under qemu-aarch64.  A label of
#   its own may not end in _a64, which only the aarch64 mode appends.
#   Extra build flags (e.g. -D SVDH_NO_RESET) can be passed in DRIVER_FLAGS.
set -euo pipefail
for a in "$@"; do case "$a" in -h | --help)          # print the header comment above
    awk 'NR == 1 { next } /^#/ { sub(/^# ?/, NR == 2 ? "usage: " : ""); print; next } { exit }' "$0"
    exit 0 ;; esac; done
H="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
[ $# -ge 1 ] && [ $# -le 3 ] || { echo "usage: $0 <label> [<tree_root> [aarch64]]" >&2; exit 2; }
ARCH="${3:-x86_64}"
[ "$ARCH" = x86_64 ] || [ "$ARCH" = aarch64 ] || {
    echo "build.sh: third argument must be aarch64 (or omitted)" >&2; exit 2; }
SVDH_NEED_PY=0
# shellcheck source=SCRIPTDIR/../env.sh
source "$H/../env.sh"
L="$1"
svdh_check_label build.sh "$L"
case "$L" in *_a64)
    echo "build.sh: label '$L' ends in _a64, which the aarch64 mode appends:" \
         "use build.sh ${L%_a64} <tree> aarch64" >&2
    exit 2 ;;
esac
T="${2:-$REPO}"
case "$T" in -*) T="./$T" ;; esac            # a path, never an option of cd
[ -d "$T" ] || { echo "build.sh: $2 is not a directory" >&2; exit 2; }
T="$(cd "$T" && pwd)"
[ -d "$T/src" ] && [ -e "$T/lib" ] || { echo "build.sh: $T must contain src/ and lib/" >&2; exit 2; }
BFLAGS=()
if [ "$ARCH" = aarch64 ]; then
    L="${L}_a64"
    BFLAGS=(--aarch64)
fi
read -r -a DFLAGS <<< "${DRIVER_FLAGS:-}"
B="$SVDH_WORK/build"
mkdir -p "$B"
rm -f "$B/drv_$L" "$B/rcp_$L"
echo "== build ($(svdh_cyrius_version), $ARCH) from $T"
for d in adv rcp; do
    ( cd "$T" && cyrius build "${BFLAGS[@]}" "${DFLAGS[@]}" "$H/driver_$d.cyr" "$B/${d/adv/drv}_$L" ) 2>&1 |
        grep -v "unreachable fns" || true
done
[ -x "$B/drv_$L" ] && [ -x "$B/rcp_$L" ] || { echo "build.sh: build failed" >&2; exit 1; }
ls -la "$B/drv_$L" "$B/rcp_$L"
