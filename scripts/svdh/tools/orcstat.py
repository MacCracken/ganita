#!/usr/bin/env python3
"""orcstat.py [DIR]: what an oracle holds, per class.  DIR holds corpus.bin, corpus_meta.json and
oracle.json: a directory, or else a set under $SVDH_WORK such as adv or hunts/s1 (default
$SVDH_WORK itself, the corpus; $SVDH_WORK defaults to <repo>/build/svdh).
Per class: matrices, those refused (non-finite input), the oracle methods, the precision used
(bits) over the matrices with one or two columns and over the others, the sigma not certified
(rel_ok false), the matrices whose exact rank is below n, and those whose correctly rounded
sigma_1 is +inf (exact sigma_1 above DBL_MAX + ulp/2).  The precision columns leave out the
methods that record no precision of their own (prec 0 in oracle.json): `zero`, an exact zero
matrix, and `blocks` (hunts/gen.py), whose sigma come from each block's own oracle; the last line
counts them.
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import check as CK   # noqa: E402

INF_BITS = '7ff0000000000000'
NO_PREC = ('zero', 'blocks')         # methods that record prec 0: no precision of their own


def span(v):
    return '-' if not v else ('%d' % v[0] if min(v) == max(v) else '%d..%d' % (min(v), max(v)))


def main():
    ap = argparse.ArgumentParser(description='Methods, precision, certification and rank of an oracle, '
                                 'per class.')
    ap.add_argument('dir', nargs='?', default=CK.WORK, metavar='DIR',
                    help='the set: a directory, or else a name under $SVDH_WORK (default $SVDH_WORK)')
    a = ap.parse_args()
    d = a.dir if os.path.isdir(a.dir) else os.path.join(CK.WORK, a.dir)
    cw, crow, ccol, coff = CK.load_corpus(os.path.join(d, 'corpus.bin'))
    meta = CK.load_meta(os.path.join(d, 'corpus_meta.json'), crow, ccol)
    orc = CK.Oracle(os.path.join(d, 'oracle.json'), len(crow), meta)
    orc.fit(cw, crow, ccol, coff)       # the checks that it fits, with a message
    mats = orc.matrices
    rows = {}
    order = []
    for k, (m, o) in enumerate(zip(meta, mats)):
        c = m['class']
        if c not in rows:
            rows[c] = {'n': 0, 'rej': 0, 'meth': {}, 'p12': [], 'p3': [], 'unc': 0, 'def': 0, 'inf': 0}
            order.append(c)
        r = rows[c]
        r['n'] += 1
        if o['reject']:
            r['rej'] += 1
            continue
        mth, prec = o.get('method'), o.get('prec')
        if not isinstance(mth, str) or type(prec) is not int:
            CK.die('oracle %s: matrix %d has no method (a string) and prec (an integer)' % (orc.path, k))
        r['meth'][mth] = r['meth'].get(mth, 0) + 1
        if mth not in NO_PREC:
            (r['p12'] if int(ccol[k]) <= 2 else r['p3']).append(prec)
        r['unc'] += sum(1 for x in o['rel_ok'] if not x)
        r['def'] += int(o['rank'] < int(ccol[k]))
        r['inf'] += int(o['sigma_bits'][0] == INF_BITS)
    print('%-11s %6s %7s %9s %10s %7s %6s %6s  %s' % ('class', 'count', 'refused', 'prec n<=2', 'prec n>=3',
                                                      'uncert', 'rank<n', 's1=inf', 'methods'))
    tot = {'n': 0, 'rej': 0, 'p12': [], 'p3': [], 'unc': 0, 'def': 0, 'inf': 0, 'meth': {}}
    for c in order + ['ALL']:
        r = rows[c] if c != 'ALL' else tot
        if c != 'ALL':
            for key in ('n', 'rej', 'unc', 'def', 'inf'):
                tot[key] += r[key]
            tot['p12'] += r['p12']
            tot['p3'] += r['p3']
            for mth, v in r['meth'].items():
                tot['meth'][mth] = tot['meth'].get(mth, 0) + v
        print('%-11s %6d %7d %9s %10s %7d %6d %6d  %s' % (
            c, r['n'], r['rej'], span(r['p12']), span(r['p3']), r['unc'], r['def'], r['inf'],
            ', '.join('%s %d' % kv for kv in sorted(r['meth'].items()))))
    print('left out of the precision columns (methods that record none): %s'
          % (', '.join('%s %d' % (mth, tot['meth'][mth]) for mth in NO_PREC if mth in tot['meth']) or 'none'))


if __name__ == '__main__':
    main()
