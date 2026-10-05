#!/usr/bin/env python3
"""The hunt aimed at _linalg_svd_reorth: A with its largest entry near DBL_MAX and singular
values near (or below) DBL_MIN, n >= 4 -- the inputs whose columns are all subnormal in the
scaled-down working copy.
Oracle-free: status, vo, U orthonormality over EVERY non-zero sigma (u_all) and over normal
sigma (u_orth, check.py's), Vt, recon vs returned sigma_1, desc (sigma descending, no NaN),
NaN/inf, zero-column rule.  A NaN in U or Vt makes its metric +inf (quick.py); recon is undefined
where a returned sigma is +inf and counts as 0 there, but a NaN or -inf sigma makes it +inf.
Then the non-finite output, matrix by matrix: how many sigma are +inf and whether they are the
leading ones, any other non-finite sigma, non-finite U or Vt; and, for each +inf sigma, whether
it is the correctly rounded value: numpy's sigma of A*2^-64 (no overflow there; a tiny entry that
underflows moves sigma by far less than the margin) above the rounding threshold DBL_MAX + ulp/2
by more than MARGIN*sigma_1 (+inf right), below it by more (+inf wrong), or within (undecided).
Finite sigma that numpy puts above the threshold by more than the margin are counted too.  That
is numpy's verdict, not an exact oracle's, but the margin is 2^12 u, far above numpy's error.

usage: d1hunt.py LABEL   runs $SVDH_WORK/build/driver_LABEL (built by run.sh <tree> LABEL; an
aarch64 driver_X_a64, from run.sh <tree> X aarch64, runs under qemu-aarch64) on 2,275 matrices
generated here (seeded; no oracle needed).  Exits with status 2 on a usage error, a label not
usable in file names (README.md) or a missing driver, and 1 when the driver fails."""
import os
import random
import sys
from collections import defaultdict

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))
import quick             # noqa: E402
import check as CK       # noqa: E402
import corpus as C       # noqa: E402

USAGE = 'usage: d1hunt.py LABEL   (driver: $SVDH_WORK/build/driver_LABEL, from run.sh <tree> LABEL)'
# A sigma rounds to +inf from DBL_MAX + ulp/2 = 2^1024 - 2^970 up; numpy sees A * 2^-64, where that
# threshold is 2^960 to within 2^906, far inside the margin.
SCALE = -64
THRESH = 2.0 ** (1024 + SCALE)
MARGIN = 2.0 ** -40                                               # of sigma_1: 2^12 u


def bits(A):
    return np.ascontiguousarray(A, dtype=np.float64).view(np.uint64).ravel().tolist()


def blockdiag(rng, m, n, nb, es_lo, es_hi, cond=0):
    A = np.zeros((m, n))
    for i in range(nb):
        for j in range(nb):
            A[i, j] = C.rfull(rng, 1021, 1023)
    ns = n - nb
    Bs = np.array([[C.rfull(rng, es_lo, es_hi) for _ in range(ns)] for _ in range(ns)])
    if cond:
        Bs[-1] = Bs[0] + np.array([C.rfull(rng, es_lo - cond, es_lo - cond) for _ in range(ns)])
    A[nb:n, nb:n] = Bs
    if m > n:
        for i in range(ns):
            r = rng.randrange(n, m)
            A[[nb + i, r]] = A[[r, nb + i]]
    return A


def items():
    out = []
    rng = random.Random(20261004)
    # F1: a block near DBL_MAX beside a block near DBL_MIN, m 4..12, n 4..6, small block
    # exponent -1022..-1018
    for m in (4, 5, 6, 8, 12):
        for n in (4, 5, 6):
            if m < n:
                continue
            for rep in range(120):
                nb = rng.choice([1, 2, 3]) if n > 4 else rng.choice([1, 2])
                es = rng.choice([-1022, -1021, -1020, -1019, -1018])
                out.append(('F1 %dx%d nb=%d es=%d #%d' % (m, n, nb, es, rep), m, n,
                            bits(blockdiag(rng, m, n, nb, es - 1, es))))
    # F2: deep subnormal small blocks (sigma itself subnormal), some ill-conditioned (fallback bait)
    for m in (4, 6, 8, 16):
        for n in (4, 5):
            if m < n:
                continue
            for rep in range(100):
                nb = rng.choice([1, 2])
                es = rng.choice([-1074, -1070, -1060, -1050, -1040, -1030])
                cond = rng.choice([0, 0, 2, 8, 20])
                lo = max(es - 1, -1074)
                out.append(('F2 %dx%d nb=%d es=%d cond=%d #%d' % (m, n, nb, es, cond, rep), m, n,
                            bits(blockdiag(rng, m, n, nb, lo, es, cond if es - cond > -1074 else 0))))
    # F3: tall (4096x4 like the wshift2 witnesses, and wider)
    for (m, n) in ((4096, 4), (4096, 5), (1024, 6), (300, 8)):
        for rep in range(12):
            A = np.zeros((m, n))
            A[0, 0] = C.rfull(rng, 1023, 1023)
            k = n - 1
            for i in range(k):
                for j in range(k):
                    A[1 + i, 1 + j] = C.rfull(rng, -1022, -1020)
            idx = list(range(m - 1))
            rng.shuffle(idx)
            A[1:] = A[1:][idx]
            out.append(('F3 %dx%d #%d' % (m, n, rep), m, n, bits(A)))
    # F4: dense, every entry mixed: a few columns near DBL_MAX, the rest near DBL_MIN, rotated
    for (m, n) in ((6, 4), (10, 6), (20, 10), (40, 12), (80, 10)):
        for rep in range(15):
            nb = rng.randint(1, max(1, n // 3))
            A = np.zeros((m, n))
            for j in range(n):
                lo, hi = (1015, 1020) if j < nb else (-1022, -1016)
                for i in range(m):
                    A[i, j] = C.rfull(rng, lo, hi)
            out.append(('F4 %dx%d nb=%d #%d' % (m, n, nb, rep), m, n, bits(A)))
    # F5: large n, a handful of all-subnormal-in-working-copy columns
    for n in (16, 40, 96):
        for rep in range(4):
            m = n
            A = np.zeros((m, n))
            nsmall = rng.randint(2, 4)
            for i in range(m):
                for j in range(n):
                    A[i, j] = C.rfull(rng, 1018, 1020) if j < n - nsmall else 0.0
            for i in range(n - nsmall, n):
                for j in range(n - nsmall, n):
                    A[i, j] = C.rfull(rng, -1022, -1018)
            out.append(('F5 %dx%d small=%d #%d' % (m, n, nsmall, rep), m, n, bits(A)))
    return out


def main():
    if len(sys.argv) == 2 and sys.argv[1] in ('-h', '--help'):
        print(__doc__)
        return 0
    if len(sys.argv) != 2 or sys.argv[1].startswith('-'):
        C.input_error(USAGE)
    label = CK.check_label(sys.argv[1])
    drv = os.path.join(C.WORK, 'build', 'driver_' + label)
    if not os.access(drv, os.X_OK):
        how = ('<tree> %s aarch64' % label[:-4]) if label.endswith('_a64') else '<tree> %s' % label
        C.input_error('d1hunt.py: %s not found: run scripts/svdh/run.sh %s first' % (drv, how))
    C.check_versions()
    C.term_as_exit()                  # SIGTERM, too, removes quick.run's scratch files
    items_ = items()
    try:
        res = quick.run(items_, driver=drv)
    except (OSError, RuntimeError, ValueError) as e:
        sys.exit('d1hunt.py: %s' % e)
    # per family: count, st!=0, u_orth, vt_orth, recon, u_all, vo!, nonf, u0c!, desc!
    agg = defaultdict(lambda: [0, 0, 0.0, 0.0, 0.0, 0.0, 0, 0, 0, 0])
    worst = []
    nonf = {'mats': 0, 'uv': 0, 'other_s': 0, 'lead': defaultdict(int), 'inf_ok': 0, 'inf_bad': 0,
            'inf_amb': 0, 'fin_ovf': 0}
    for it, r in zip(items_, res):
        a = agg[r['label'].split()[0]]
        a[0] += 1
        if r['st'] != 0:
            a[1] += 1
            continue
        Sf = r['S'].view(np.float64)
        bad_s = ~np.isfinite(Sf) & (Sf != np.inf)           # NaN or -inf
        a[5] = max(a[5], r['u_all'])
        a[2] = max(a[2], r['u_orth'])
        a[3] = max(a[3], r['vt_orth'])
        if r['recon'] == r['recon']:
            a[4] = max(a[4], r['recon'])
        elif bad_s.any():
            a[4] = np.inf                                   # recon of a NaN or -inf sigma
        if not r['vo']:
            a[6] += 1
        if r['nonfinite_uv'] or r['nonfinite_s']:
            a[7] += 1
        if not r['u0col']:
            a[8] += 1
        if not r['desc']:
            a[9] += 1
        worst.append((r['u_all'], r['label']))
        if r['nonfinite_uv'] or r['nonfinite_s']:
            nonf['mats'] += 1
            nonf['uv'] += int(r['nonfinite_uv'] > 0)
            inf = Sf == np.inf
            k = int(inf.sum())
            if bad_s.any() or (k and not inf[:k].all()):
                nonf['other_s'] += 1                        # NaN, -inf, or +inf below a finite sigma
            elif k:
                nonf['lead'][k] += 1
        # numpy's verdict on each sigma, where a sigma is +inf or numpy's is near the threshold
        A = np.array(it[3], dtype='<u8').view(np.float64).reshape(r['m'], r['n'])
        if np.max(np.abs(A)) < 2.0 ** 1000 and not np.isinf(Sf).any():
            continue                                        # no sigma can be near DBL_MAX
        sv = np.linalg.svd(np.ldexp(A, SCALE), compute_uv=False)
        thr, mar = THRESH, MARGIN * sv[0]
        for j in range(r['n']):
            if Sf[j] == np.inf:
                if sv[j] > thr + mar:
                    nonf['inf_ok'] += 1
                elif sv[j] < thr - mar:
                    nonf['inf_bad'] += 1
                else:
                    nonf['inf_amb'] += 1
            elif np.isfinite(Sf[j]) and sv[j] > thr + mar:
                nonf['fin_ovf'] += 1
    print('driver', label)
    print('%-4s %6s %5s %10s %10s %10s %10s %4s %5s %5s %5s' % ('fam', 'count', 'st!=0', 'u_orth', 'u_all',
                                                                'vt_orth', 'recon', 'vo!', 'nonf', 'u0c!',
                                                                'desc!'))
    for f in sorted(agg):
        a = agg[f]
        print('%-4s %6d %5d %10.3g %10.3g %10.3g %10.3g %4d %5d %5d %5d'
              % (f, a[0], a[1], a[2], a[5], a[3], a[4], a[6], a[7], a[8], a[9]))
    worst.sort(reverse=True)
    for w in worst[:6]:
        print('   u_all %.4g  %s' % w)
    print('u_all over 16 u:', sum(1 for w in worst if w[0] > 16), ' over 256 u:',
          sum(1 for w in worst if w[0] > 256), 'of', len(worst))
    print('non-finite output in %d matrices: U or Vt non-finite in %d; sigma +inf as the k largest, '
          'the rest finite: %s; other non-finite sigma (NaN, -inf, +inf below a finite one) in %d'
          % (nonf['mats'], nonf['uv'], ', '.join('k=%d in %d' % kv for kv in sorted(nonf['lead'].items()))
             or 'none', nonf['other_s']))
    print('+inf sigma against numpy (sigma of A*2^%d, threshold DBL_MAX + ulp/2, margin 2^%d sigma_1): '
          'above by more (+inf right) %d, below by more (+inf wrong) %d, within (undecided) %d; finite '
          'sigma above by more %d'
          % (SCALE, int(np.log2(MARGIN)), nonf['inf_ok'], nonf['inf_bad'], nonf['inf_amb'], nonf['fin_ovf']))
    return 0


if __name__ == '__main__':
    sys.exit(main())
