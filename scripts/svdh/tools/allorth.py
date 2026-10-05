#!/usr/bin/env python3
"""allorth.py RESULTS [--corpus C --meta M]: U orthonormality over EVERY column with sigma != 0
(not only normal sigma, as check.py's u_orth), per class, and the zero-column rule: the count of
columns whose returned sigma is 0 but whose U column is not all zero (ganita returns those
columns as zero).  Only status-0 results are measured: the matrices with another status are
counted, per class, on a line of their own (a class where every matrix has one has no worst line).
corpus / meta default to $SVDH_WORK (default <repo>/build/svdh)."""
import argparse
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import check as CK   # noqa: E402

LD = np.longdouble
U = LD(2.0) ** -52


def main():
    ap = argparse.ArgumentParser(description='U orthonormality over every non-zero sigma, per class.')
    ap.add_argument('res', metavar='RESULTS')
    ap.add_argument('--corpus', default=os.path.join(CK.WORK, 'corpus.bin'))
    ap.add_argument('--meta', default=os.path.join(CK.WORK, 'corpus_meta.json'))
    a = ap.parse_args()
    CK.require_longdouble()
    CK.need_file(a.res, 'results file')
    cw, crow, ccol, coff = CK.load_corpus(a.corpus)
    meta = CK.load_meta(a.meta, crow, ccol)
    roff, total = CK.results_offsets(crow, ccol)
    w = CK.load_results(a.res, total)
    worst = {}
    skipped = {}
    bad0 = 0
    for k in range(len(crow)):
        m, n = int(crow[k]), int(ccol[k])
        p = int(roff[k])
        if int(np.int64(w[p])) != 0:
            skipped[meta[k]['class']] = skipped.get(meta[k]['class'], 0) + 1
            continue
        S = w[p + 1:p + 1 + n].view(np.float64)
        Uf = w[p + 1 + n:p + 1 + n + m * n].view(np.float64).reshape(m, n)
        J = S != 0
        bad0 += int(np.sum((~J) & np.any(Uf != 0, axis=0)))
        if J.sum() == 0:
            continue
        UL = Uf[:, J].astype(LD)
        e = float(np.max(np.abs(UL.T @ UL - np.eye(int(J.sum()), dtype=LD))) / U)
        if e != e:
            e = float('inf')                  # NaN in U counts as +inf, as in check.py
        c = meta[k]['class']
        if e > worst.get(c, (-1, 0))[0]:
            worst[c] = (e, k)
    for c, (e, k) in sorted(worst.items(), key=lambda t: -t[1][0]):
        print('  %-12s worst %9.3g u  (id %d, %s)' % (c, e, k, CK.cut(meta[k]['label'], 50)))
    print('  U columns of a zero sigma that are not all zero: %d' % bad0)
    parts = ', '.join('%s %d' % (c, v) for c, v in sorted(skipped.items()))
    print('  status != 0, not measured: %d%s' % (sum(skipped.values()), ' (%s)' % parts if parts else ''))


if __name__ == '__main__':
    main()
