#!/usr/bin/env python3
"""Build a small exact-oracle set from explicit bit lists.

usage: mkwit.py wshift|wshift2|FILE.json [--out DIR]
       mkwit.py wshift|wshift2 --rank LABEL
  wshift     four matrices of 5 to 8 rows whose largest entry is near DBL_MAX, over a block near
             DBL_MIN, so a column of the scaled-down working copy is all subnormal.  The generator
             (random.Random(11)) makes 2,800 such matrices, 400 at each of 4x4, 5x4, 5x5, 6x4, 6x5,
             8x4 and 8x5; without _linalg_svd_reorth, these four are among the worst by check.py's
             u_orth (columns with sigma >= 2^-1022): 329, 261, 228 and 204 u (1st, 3rd, 5th and
             8th), one each at 8x5, 8x4, 6x4 and 5x5.  Over every non-zero sigma the generator's
             worst reaches 17,277 u without the repair; see tools/d1hunt.py.
  wshift2    two 4096x4 matrices of the same kind (random.Random(31), 40 matrices): the two worst
             by u_orth without _linalg_svd_reorth (529 and 516 u); over every non-zero sigma the
             worst of the 40 reaches 5,359 u.
  FILE.json  a list of {"label", "rows", "cols", "bits": [16-hex-digit strings, row-major]}, the
             format of adv/hunt.py's hits; other keys are ignored.
DIR defaults to $SVDH_WORK/hunts/<name> (a DIR without '/' is a name under $SVDH_WORK/hunts).
The generators are re-run here and the witnesses picked by label, so no driver is needed.
corpus.bin, corpus_meta.json and oracle.json are written under temporary names and renamed
together at the end.  Then: scripts/svdh/hunts/run.sh <name> <label> scores them.
--rank LABEL writes no set: it runs $SVDH_WORK/build/driver_LABEL (from ../run.sh <tree> LABEL)
on every matrix of the generator, oracle-free (tools/quick.py), and prints the worst by u_orth
(check.py's: columns with sigma >= 2^-1022) and by u_all (every sigma != 0), and where each
witness ranks.  The figures above come from a tree without the _linalg_svd_reorth call (README.md
gives the recipe).  LABEL must be usable in file names (README.md).
Exits with status 2 on a usage or input error (a missing driver, a malformed FILE.json, an
unusable DIR), and 1 when the driver of --rank fails.
"""
import argparse
import json
import os
import random
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))
import gen                # noqa: E402  (hunts/gen.py)
import corpus as C        # noqa: E402


def build(out, items):
    outm = []
    for k, (lab, m, n, bl) in enumerate(items):
        _, r = gen.run_oracle((k, 'strip', None, m, n, bl, lab))
        outm.append({'id': k, 'reject': False, 'sigma_bits': ['%016x' % b for b in r['bits']],
                     'hp': [list(x) for x in r['hp']], 'rel_ok': r['rel_ok'], 'rank': r['rank'],
                     'method': r['method'], 'prec': r['prec']})
    try:
        with open(C.tmp_path(out, 'corpus.bin'), 'wb') as fh:
            fh.write(struct.pack('<Q', len(items)))
            for (lab, m, n, bl) in items:
                fh.write(struct.pack('<QQ', m, n))
                fh.write(struct.pack('<%dQ' % (m * n), *bl))
        with open(C.tmp_path(out, 'corpus_meta.json'), 'w') as fh:
            json.dump([{'id': k, 'class': 'wit', 'label': it[0], 'rows': it[1], 'cols': it[2]}
                       for k, it in enumerate(items)], fh)
        with open(C.tmp_path(out, 'oracle.json'), 'w') as fh:
            json.dump({'info': {}, 'matrices': outm}, fh)
        C.publish(out)
    except BaseException:
        C.discard_tmp(out)
        raise


def _wshift_items():
    """The block family: rows 0..nb-1 / cols 0..nb-1 near 2^1022, the next ns x ns block near
    2^-1021 (random.Random(11), m in 4,5,6,8, n in 4,5, 400 each)."""
    rng = random.Random(11)
    items = []
    for m in (4, 5, 6, 8):
        for n in (4, 5):
            if m < n:
                continue
            for rep in range(400):
                nb = rng.choice([1, 2])
                ns = n - nb
                Bb = [[C.rfull(rng, 1021, 1023) for _ in range(nb)] for _ in range(nb)]
                es = rng.choice([-1022, -1021, -1020])
                Bs = [[C.rfull(rng, es - 1, es) for _ in range(ns)] for _ in range(ns)]
                A = [[0.0] * n for _ in range(m)]
                for i in range(nb):
                    for j in range(nb):
                        A[i][j] = Bb[i][j]
                for i in range(ns):
                    for j in range(ns):
                        A[nb + i][nb + j] = Bs[i][j]
                items.append(('m=%d n=%d nb=%d es=%d #%d' % (m, n, nb, es, rep), m, n,
                              [C.bits_of(x) for row in A for x in row]))
    return items


def _wshift2_items():
    """4096x4: A[0,0] near 2^1023, A[1..3,1..3] near 2^-1021, zero elsewhere (random.Random(31))."""
    import numpy as np
    rng = random.Random(31)
    m, n = 4096, 4
    items = []
    for rep in range(40):
        A = np.zeros((m, n))
        A[0, 0] = C.rfull(rng, 1023, 1023)
        for i in range(3):
            for j in range(3):
                A[1 + i, 1 + j] = C.rfull(rng, -1022, -1020)
        items.append(('%dx%d #%d' % (m, n, rep), m, n, A.view(np.uint64).ravel().tolist()))
    return items


WITNESSES = {
    'wshift': (_wshift_items, ['m=5 n=5 nb=1 es=-1021 #349', 'm=6 n=4 nb=1 es=-1022 #369',
                               'm=8 n=4 nb=1 es=-1020 #384', 'm=8 n=5 nb=1 es=-1022 #16']),
    'wshift2': (_wshift2_items, ['4096x4 #33', '4096x4 #30']),
}


def load_hits(ap, path):
    """(label, rows, cols, bits) of each entry of a hunt-hit JSON list; exits on a bad entry."""
    try:
        return [(lab, m, n, bl) for lab, m, n, bl, _ in C.load_hits(path, allow_empty=False)]
    except ValueError as e:
        ap.error(str(e))


def rank(name, label):
    """Run driver_<label> on every matrix of the generator of `name`; print the worst and where
    the witnesses rank, by u_orth and by u_all."""
    sys.path.insert(0, os.path.join(os.path.dirname(HERE), 'tools'))
    import quick          # noqa: E402  (tools/quick.py)
    import check as CK    # noqa: E402  (../check.py)
    CK.check_label(label)
    drv = os.path.join(C.WORK, 'build', 'driver_' + label)
    if not os.access(drv, os.X_OK):
        how = ('<tree> %s aarch64' % label[:-4]) if label.endswith('_a64') else '<tree> %s' % label
        C.input_error('mkwit.py: %s not found: run scripts/svdh/run.sh %s first' % (drv, how))
    fn, wit = WITNESSES[name]
    items = fn()
    C.term_as_exit()                  # SIGTERM, too, removes quick.run's scratch files
    try:
        res = quick.run(items, driver=drv)
    except (OSError, RuntimeError, ValueError) as e:
        sys.exit('mkwit.py: %s' % e)
    st = {}
    for r in res:
        st[r['st']] = st.get(r['st'], 0) + 1
    ok = [r for r in res if r['st'] == 0]
    by = {r['label']: r for r in ok}
    print('%s: %d matrices, driver_%s; status %s' % (name, len(res), label, st))
    for metric in ('u_orth', 'u_all'):
        top = sorted(ok, key=lambda r: -r[metric])
        print('by %s (u), worst first:' % metric)
        for i, r in enumerate(top[:10]):
            print('  %3d  %10.1f  %dx%d  %s' % (i + 1, r[metric], r['m'], r['n'], r['label']))
        for lab in wit:
            if lab not in by:
                print('  witness %s: status not 0' % lab)
                continue
            v = by[lab][metric]
            print('  witness %-28s %10.1f, rank %d of %d' % (lab, v, 1 + sum(1 for r in ok if r[metric] > v),
                                                             len(ok)))


def main():
    ap = argparse.ArgumentParser(description='Build a small exact-oracle set from explicit bit lists.')
    ap.add_argument('what', metavar='wshift|wshift2|FILE.json')
    ap.add_argument('--out', metavar='DIR',
                    help="output directory; without a '/' a name under $SVDH_WORK/hunts "
                    '(default: the name of the set or file)')
    ap.add_argument('--rank', metavar='LABEL',
                    help='wshift and wshift2 only: run driver_LABEL on all of the generator\'s matrices '
                    'and print where the witnesses rank by u_orth and u_all (writes no set)')
    a = ap.parse_args()
    if a.rank is not None:
        if a.what not in WITNESSES or a.out is not None:
            ap.error('--rank takes wshift or wshift2, and no --out')
        C.check_versions()
        rank(a.what, a.rank)
        return
    if a.what in WITNESSES:
        fn, labels = WITNESSES[a.what]
        by = {it[0]: it for it in fn()}
        items = [by[lab] for lab in labels]
        name = a.what
    elif a.what.endswith('.json') and os.path.isfile(a.what):
        items = load_hits(ap, a.what)
        name = os.path.basename(a.what)[:-5]
    else:
        ap.error('%s is neither wshift, wshift2 nor an existing .json file' % a.what)
    C.check_versions()
    out = a.out if a.out is not None else name
    if '/' not in out:
        out = os.path.join(C.WORK, 'hunts', out)
    C.make_outdir('mkwit.py', out)
    C.term_as_exit()
    build(out, items)
    print('wrote %d matrices to %s' % (len(items), out))


if __name__ == '__main__':
    main()
