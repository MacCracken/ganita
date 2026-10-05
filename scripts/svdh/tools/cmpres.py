#!/usr/bin/env python3
"""cmpres.py NEW.bin OLD.bin [--corpus C --meta M --oracle O] [--show N]: the metrics of every
matrix whose result bits differ between two results files of the same corpus.
corpus / meta / oracle default to $SVDH_WORK (default <repo>/build/svdh).

Metrics come from check.py's score(), which leaves a metric NaN where the status is not 0 (and
recon NaN where it is n/a).  Status changes are counted on their own.  better / worse / same
compare u_orth only where both are numbers and both results pass `desc` (sigma descending, no
NaN): u_orth leaves out the column of a NaN sigma, so a result that turned a sigma into NaN could
otherwise count as better.  The matrices where `desc` fails in one result or both are counted on
their own (desc lost, gained, failed in both).  The worst lines ignore NaN; the listing puts the
matrices that lost PASS first, then the rest by the larger of the two u_orth, NaN last; a label
longer than its column ends in '...'.
"""
import argparse
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import check as CK   # noqa: E402


def num(v):
    """v, or -inf where it is NaN (for ranking)."""
    return -math.inf if math.isnan(v) else v


def main():
    ap = argparse.ArgumentParser(description='Metrics of the matrices whose bits differ between two '
                                 'results files.')
    ap.add_argument('new', metavar='NEW.bin')
    ap.add_argument('old', metavar='OLD.bin')
    ap.add_argument('--corpus', default=os.path.join(CK.WORK, 'corpus.bin'))
    ap.add_argument('--meta', default=os.path.join(CK.WORK, 'corpus_meta.json'))
    ap.add_argument('--oracle', default=os.path.join(CK.WORK, 'oracle.json'))
    ap.add_argument('--show', type=CK.nonneg_arg, default=40, metavar='N', help='matrices to list (default 40)')
    a = ap.parse_args()
    CK.need_file(a.new, 'results file')
    CK.need_file(a.old, 'results file')
    cw, crow, ccol, coff = CK.load_corpus(a.corpus)
    N = len(crow)
    meta = CK.load_meta(a.meta, crow, ccol)
    orc = CK.Oracle(a.oracle, N, meta)
    R1 = CK.score(cw, crow, ccol, coff, orc, a.new)
    R0 = CK.score(cw, crow, ccol, coff, orc, a.old)
    roff, total = CK.results_offsets(crow, ccol)
    x = CK.load_results(a.new, total)
    y = CK.load_results(a.old, total)
    dw = np.nonzero(x != y)[0]
    ks = sorted(set((np.searchsorted(roff, dw, side='right') - 1).tolist()))
    print('changed matrices: %d of %d' % (len(ks), N))
    s1, s0 = R1['status'], R0['status']
    print('status: 0 -> non-zero %d; non-zero -> 0 %d; non-zero -> other non-zero %d'
          % (sum(1 for k in ks if s0[k] == 0 and s1[k] != 0), sum(1 for k in ks if s0[k] != 0 and s1[k] == 0),
             sum(1 for k in ks if s0[k] != 0 and s1[k] != 0 and s0[k] != s1[k])))
    better = worse = same = na = 0
    desc = {'lost': 0, 'gained': 0, 'both': 0}
    for k in ks:
        u1, u0 = R1['u_orth'][k], R0['u_orth'][k]
        if math.isnan(u1) or math.isnan(u0):
            na += 1
            continue
        if not (R1['desc'][k] and R0['desc'][k]):
            desc['lost' if R0['desc'][k] else 'gained' if R1['desc'][k] else 'both'] += 1
            continue
        d = u1 - u0
        if d < -1e-9:
            better += 1
        elif d > 1e-9:
            worse += 1
        else:
            same += 1
    print('u_orth (where both are numbers, and sigma descending with no NaN in both): better %d, worse %d, '
          'same %d; n/a %d (a status != 0); desc lost %d, gained %d, failed in both %d'
          % (better, worse, same, na, desc['lost'], desc['gained'], desc['both']))
    print('PASS new/old on changed: %d / %d; lost PASS %d, gained PASS %d' % (
        sum(R1['pass'][k] for k in ks), sum(R0['pass'][k] for k in ks),
        sum(1 for k in ks if R0['pass'][k] and not R1['pass'][k]),
        sum(1 for k in ks if R1['pass'][k] and not R0['pass'][k])))
    if ks:
        ids = np.array(ks)
        for m in CK.METRICS:
            w1, i1 = CK.worst(R1[m][ids], ids)
            w0, i0 = CK.worst(R0[m][ids], ids)
            print('  worst %-8s new %-10s %-9s old %-10s %s' % (
                m, CK.fmtv(w1), '@%d' % i1 if i1 is not None else '', CK.fmtv(w0),
                '@%d' % i0 if i0 is not None else ''))

    def key(k):
        lost = R0['pass'][k] and not R1['pass'][k]
        return (0 if lost else 1, -max(num(R1['u_orth'][k]), num(R0['u_orth'][k])))
    ks.sort(key=key)
    for k in ks[:a.show]:
        print('  id %5d %-44s st %d/%d  pass %d/%d  u_orth %8s -> %-8s vt %6s -> %-6s recon %6s -> %-6s '
              'nw %6s -> %s' % (
                  k, CK.cut(meta[k]['label'], 44), s0[k], s1[k], R0['pass'][k], R1['pass'][k],
                  CK.fmtv(R0['u_orth'][k]), CK.fmtv(R1['u_orth'][k]), CK.fmtv(R0['vt_orth'][k]),
                  CK.fmtv(R1['vt_orth'][k]), CK.fmtv(R0['recon'][k]), CK.fmtv(R1['recon'][k]),
                  CK.fmtv(R0['sig_nw'][k]), CK.fmtv(R1['sig_nw'][k])))


if __name__ == '__main__':
    main()
