# shellcheck shell=bash
# env.sh: sourced by every svdh shell script except tree-at.sh; not meant to be run on its own.
#
# Sets, from this file's own location:
#   SVDH_DIR   this directory (scripts/svdh)
#   REPO       the repository root
#   SVDH_WORK  where generated data goes: corpora, oracles, results, binaries.
#              Default $REPO/build/svdh (ignored by git); made absolute and exported.
#   PY         the python that runs the .py scripts. Default python3. It must import mpmath and
#              numpy (requirements.txt); versions other than the pinned ones are only a warning.
#              A script that runs no Python sets SVDH_NEED_PY=0 before sourcing this file, which
#              then skips the Python check (adv/run.sh does so unless a label ends in _a64, the
#              only case where it runs rcpcmp.py).
# Defines:
#   svdh_is_aarch64 BINARY   true when BINARY is an aarch64 ELF.
#   svdh_runner BINARY       prints "qemu-aarch64" when BINARY is an aarch64 ELF and this machine
#                            is not aarch64 (nothing otherwise): the prefix that runs a cross-built
#                            driver.
#   svdh_check_label PROG LABEL
#                            exits 2 with a message unless LABEL is a usable label: letters,
#                            digits, '.', '_', '+' and '-' only, and not starting with '-' (it
#                            becomes part of file names, and must not look like an option).
#   svdh_driver_stderr FILE NAME
#                            copies a driver's stderr (FILE) to stderr; returns 1, with a
#                            message, when the driver's count of modified A (calls for
#                            driver.cyr and driver_adv.cyr, matrices for driver_rcp.cyr) is not
#                            0, and 2 when it printed no such count.
# Every svdh shell script (tree-at.sh too) answers -h / --help with its header comment before
# sourcing this file.
# cyrius is whatever is on PATH, under whatever CYRIUS_HOME is set; a version other than the
# manifest pin in $REPO/cyrius.cyml is only a warning.  svdh_cyrius_version prints the first
# line of `cyrius version`.

SVDH_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$SVDH_DIR/../.." && pwd)"
SVDH_WORK="${SVDH_WORK:-$REPO/build/svdh}"
case "$SVDH_WORK" in -*) SVDH_WORK="./$SVDH_WORK" ;; esac     # a path, never an option of mkdir or cd
mkdir -p "$SVDH_WORK"
SVDH_WORK="$(cd "$SVDH_WORK" && pwd)"
export SVDH_WORK
PY="${PY:-python3}"

if [ "${SVDH_NEED_PY:-1}" != 0 ]; then
    command -v "$PY" > /dev/null || { echo "svdh: python '$PY' not found (set PY)" >&2; return 2; }
    # corpus.py exits with a message when mpmath or numpy cannot be imported, and
    # check_versions() warns when they (or python) differ from requirements.txt.
    "$PY" -B - "$SVDH_DIR" << 'EOF' || return 2
import sys
sys.path.insert(0, sys.argv[1])
import corpus
corpus.check_versions()
EOF
fi

svdh_is_aarch64() {
    local magic mach
    magic="$(head -c 4 "$1" 2> /dev/null | od -An -tx1 | tr -d ' \n')"
    mach="$(od -An -tu1 -j18 -N2 "$1" 2> /dev/null | awk '{ print $1 + 256 * $2 }')"
    [ "$magic" = 7f454c46 ] && [ "$mach" = 183 ]
}

svdh_runner() {
    if svdh_is_aarch64 "$1" && [ "$(uname -m)" != aarch64 ]; then
        echo qemu-aarch64
    fi
}

svdh_check_label() {
    case "$2" in
        '' | -* | *[!A-Za-z0-9._+-]*)
            echo "$1: label '$2' must be non-empty, must not start with '-', and may use only" \
                 "letters, digits, '.', '_', '+' and '-'" >&2
            exit 2 ;;
    esac
}

svdh_driver_stderr() {
    local mod
    cat "$1" >&2
    # awk reads all of its input (no SIGPIPE upstream under pipefail).  The count ends the line
    # "... calls that modified A: N" (driver.cyr, driver_adv.cyr) or "... matrices where a call
    # modified A: N" (driver_rcp.cyr).
    mod="$(awk -F 'modified A: ' 'NF > 1 { n = $2 + 0 } END { print n }' "$1")"
    if [ -z "$mod" ]; then
        echo "svdh: $2 printed no count of modified A on stderr" >&2
        return 2
    fi
    if [ "$mod" != 0 ]; then
        echo "svdh: $2 reports that it modified A (count $mod); it must be 0" >&2
        return 1
    fi
}

# awk, not head: head can exit before cyrius has written its second line, and the SIGPIPE that
# cyrius then gets would fail the pipeline under `set -o pipefail`.
svdh_cyrius_version() {
    cyrius version 2> /dev/null | awk 'NR == 1'
}

if command -v cyrius > /dev/null; then
    _svdh_pin="$(sed -n 's/^cyrius = "\(.*\)"$/\1/p' "$REPO/cyrius.cyml")"
    _svdh_have="$(svdh_cyrius_version | awk '{ print $2 }')"
    if [ "$_svdh_have" != "$_svdh_pin" ]; then
        echo "svdh: warning: cyrius on PATH is '$_svdh_have', $REPO/cyrius.cyml pins '$_svdh_pin'" >&2
    fi
    unset _svdh_pin _svdh_have
else
    echo "svdh: warning: cyrius is not on PATH; building a driver will fail" >&2
fi
