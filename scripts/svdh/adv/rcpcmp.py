#!/usr/bin/env python3
"""Compare two rank / condition / pseudo_inv files (driver_rcp.cyr) of the same corpus.

usage: rcpcmp.py A.bin B.bin --corpus corpus.bin
The one difference allowed is the sign bit of a NaN entry of pseudo_inv: a NaN produced by the
hardware has the architecture's default sign (0xfff8... on x86_64, 0x7ff8... on aarch64).
Prints whether the files are bit-identical, identical up to such NaN signs, or differ otherwise.
Exits 0 in the first two cases, 1 in the third, and 2 when a file is missing or does not fit
the corpus (both files are checked against its layout first, identical or not; a size that is
not a whole number of 8-byte words does not fit).
"""
import argparse
import os
import sys
import traceback

try:
    import numpy as np
except ImportError as _e:
    print('rcpcmp.py: %s cannot import %s: pip install -r scripts/svdh/requirements.txt'
          % (sys.executable, _e.name), file=sys.stderr)
    sys.exit(2)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import check as CK   # noqa: E402

SIGN = np.uint64(1 << 63)
EXP = np.uint64(0x7FF0000000000000)
MANT = np.uint64(0x000FFFFFFFFFFFFF)
HEAD = 7   # values-only status, S[0], rank(A, 0), tol, rank(A, tol), condition, has-pinv flag


def check_layout(w, crow, ccol, path):
    """Exit with status 2 unless w is an rcp file of the corpus: per matrix HEAD words, the last a
    pseudo_inv flag of 0 or 1, and after a 1 the matrix's m*n pseudo_inv entries; nothing more."""
    o = 0
    for k in range(len(crow)):
        if o + HEAD > len(w):
            CK.die('rcp file %s is truncated at matrix %d of %d (or of another corpus)' % (path, k, len(crow)))
        has = int(w[o + HEAD - 1])
        if has not in (0, 1):
            CK.die('rcp file %s: matrix %d: pseudo_inv flag %d, not 0 or 1: not an rcp file of this corpus'
                   % (path, k, has))
        o += HEAD + (int(crow[k]) * int(ccol[k]) if has else 0)
    if o != len(w):
        CK.die('rcp file %s has %d words, its %d matrices take %d (an rcp file of another corpus?)'
               % (path, len(w), len(crow), o))


def main():
    ap = argparse.ArgumentParser(description='Compare two rcp files, allowing NaN signs in pseudo_inv.')
    ap.add_argument('a', metavar='A.bin')
    ap.add_argument('b', metavar='B.bin')
    ap.add_argument('--corpus', required=True)
    a = ap.parse_args()
    _, crow, ccol, _ = CK.load_corpus(a.corpus)
    x = CK.read_words(a.a, 'rcp file')
    y = CK.read_words(a.b, 'rcp file')
    check_layout(x, crow, ccol, a.a)
    check_layout(y, crow, ccol, a.b)
    if len(x) == len(y) and np.array_equal(x, y):
        print('rcpcmp: %s is bit-identical to %s' % (a.a, a.b))
        return 0
    o = 0
    nan_words, nan_mats, bad_words, bad_mats = 0, 0, 0, []
    for k in range(len(crow)):
        m, n = int(crow[k]), int(ccol[k])
        hx, hy = x[o:o + HEAD], y[o:o + HEAD]
        has = int(hx[HEAD - 1])
        o += HEAD
        nb = int(np.sum(hx != hy))
        if hx[HEAD - 1] != hy[HEAD - 1]:
            bad_mats.append(k)
            print('rcpcmp: matrix %d: one file has a pseudo_inv and the other not; stopped there' % k)
            bad_words += nb
            break
        if has:
            px, py = x[o:o + m * n], y[o:o + m * n]
            o += m * n
            d = px != py
            if d.any():
                dx, dy = px[d], py[d]
                isnan = ((dx & EXP) == EXP) & ((dx & MANT) != 0)
                ok = ((dx ^ dy) == SIGN) & isnan
                nb += int(np.sum(~ok))
                if ok.any():
                    nan_words += int(np.sum(ok))
                    nan_mats += 1
        if nb:
            bad_words += nb
            bad_mats.append(k)
    if bad_mats:
        print('rcpcmp: %s DIFFERS from %s: %d words that are not a NaN sign of pseudo_inv, in %d '
              'matrices (first ids %s)' % (a.a, a.b, bad_words, len(bad_mats), bad_mats[:8]))
        return 1
    print('rcpcmp: %s is identical to %s up to the sign of %d NaN words of pseudo_inv in %d matrices'
          % (a.a, a.b, nan_words, nan_mats))
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception:                 # status 1 means "differ": any other failure is 2
        traceback.print_exc()
        sys.exit(2)
