#!/usr/bin/env python3
"""Adversarial SVD sets: inputs built to break one-sided Jacobi SVD designs (graded and nearly
dependent columns, thresholds where a rotation's formulas change, exact rank deficiency, ties,
underflow, very tall input, slow convergence).  Same file formats as ../corpus.py; the oracle is
../corpus.py's own (imported, not re-derived).

usage: gen.py [--out DIR] [--classes a,b,c] [--procs N] [--hits DIR]
Writes DIR/corpus.bin, DIR/corpus_meta.json (with an optional per-matrix 'kappa' = condition number
of the row- or column-normalised matrix, for the relative-accuracy check), DIR/oracle.json, under
temporary names renamed together at the end.
Defaults: --out $SVDH_WORK/adv (a DIR without '/' is a name under $SVDH_WORK); --classes every
class except bm3,reprows,rgfail, i.e. the set `adv`.  The set `adv2` is
--classes bm3,reprows,rgfail.  --procs: oracle processes, default every CPU (no output byte
depends on it).  The class `cycle` reads the hunt hits snapshot hunt_hits.json next to this
file, or with --hits DIR the files DIR/*.json that hunt.py writes ($SVDH_WORK/hunt_hits): at
most 400 hits, with a warning when there are more.  To score a hunt's hits alone:
  gen.py --classes cycle --hits $SVDH_WORK/hunt_hits --out NAME
hunt.py adds its hits to the seed files already there, from every earlier hunt and label, so
remove $SVDH_WORK/hunt_hits before that hunt (or run it in a fresh SVDH_WORK).
The entries of bunder, brestart and atall2, the kappa values and the numpy sigma of bigdef go
through numpy's BLAS and LAPACK, so they depend on its kernels, and those of atall2 and bigdef on
its thread count, which corpus.blas_setup sets in this process and in each oracle process.

Some hit labels and `tree` fields in hunt_hits.json and b_m3_small.json name the draft trees the
hunt ran on; they are kept as recorded, since the `cycle` labels are part of adv/corpus_meta.json's
reference checksum.
"""
import argparse
import glob
import json
import math
import os
import random
import struct
import sys
import time
from fractions import Fraction
import multiprocessing as mproc

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
SVDH = os.path.dirname(HERE)
sys.path.insert(0, SVDH)
import corpus as C   # noqa: E402  (oracle_worker, bits_of, f_of, mkf, rfull, rmat, ...)

bits_of, f_of, mkf, rfull, rmat = C.bits_of, C.f_of, C.mkf, C.rfull, C.rmat
DMAX = float.fromhex('0x1.fffffffffffffp+1023')
TINY = 5e-324
U52 = 2.0 ** -52


def ld(x, k):
    """x * 2^k correctly rounded (subnormal results via Fraction)."""
    if x == 0:
        return 0.0
    r = Fraction(x) * (Fraction(2) ** k)
    try:
        return float(r)
    except OverflowError:
        return math.copysign(math.inf, x)


def scale_mat(A, k):
    return [[ld(x, k) for x in r] for r in A]


def exact_scale_ok(A, k):
    """True when every non-zero entry of A*2^k is exact (no rounding, no overflow)."""
    for r in A:
        for x in r:
            if x != 0:
                y = ld(x, k)
                if y == 0 or math.isinf(y) or Fraction(y) != Fraction(x) * Fraction(2) ** k:
                    return False
    return True


def rint_(rng, bits):
    v = rng.randrange(1, 1 << bits)
    return float(-v if rng.getrandbits(1) else v)


def _pow2_normalise(v):
    """v scaled exactly by a power of two so its largest |entry| is in [1, 2) (no under/overflow)."""
    mx = max(abs(x) for x in v)
    if mx == 0:
        return None
    e = math.frexp(mx)[1] - 1
    return [ld(x, -e) for x in v]


def kappa_cols(A):
    """Condition number of A with columns scaled to unit norm (exact power-of-two pre-scaling, so
    tiny or huge columns do not under/overflow in the norm)."""
    m, n = len(A), len(A[0])
    cols = []
    for j in range(n):
        c = _pow2_normalise([A[i][j] for i in range(m)])
        if c is None:
            continue
        c = np.array(c)
        cols.append(c / np.linalg.norm(c))
    if not cols:
        return None
    b = np.stack(cols, axis=1)
    s = np.linalg.svd(b, compute_uv=False)
    return float(s[0] / s[-1]) if s[-1] > 0 else float('inf')


def kappa_rows(A):
    return kappa_cols([list(r) for r in zip(*A)]) if len(A) >= 1 else None


# ======================================================================= classes
# Each returns a list of (class, label, A, extra) with A a list of row lists of floats.

def cls_bdill():
    """Column-graded B*D, B ill-conditioned by construction (columns nearly parallel to column 0),
    D = 2^-e_j, gaps of 0 to 980 binades (1.2.11 fails from 513 on).  A rotation between columns
    this far apart must neither deflate the small column too early nor lose it to underflow.  The
    small sigma are relatively determined to about kappa(B_colnormalised)*u."""
    rng = random.Random(7001)
    out = []
    for (m, n) in ((3, 2), (4, 3), (6, 4), (8, 5)):
        for kap in (8, 16, 19, 21, 24, 30, 40):
            for gap in (0, 300, 530, 700, 980):
                for k in range(4):
                    b0 = [rfull(rng, -1, 0) for _ in range(m)]
                    cols = [b0]
                    for j in range(1, n):
                        r = [rfull(rng, -1, 0) for _ in range(m)]
                        kj = kap + rng.randint(-2, 2)
                        cols.append([b0[i] + math.ldexp(r[i], -kj) for i in range(m)])
                    # exponents: column j scaled by 2^-(j*gap) (total span capped to keep normal)
                    ex = [min(j * gap, 1000) for j in range(n)]
                    A = [[math.ldexp(cols[j][i], -ex[j]) for j in range(n)] for i in range(m)]
                    out.append(('bdill', 'bdill %dx%d kap=2^-%d gap=%d #%d' % (m, n, kap, gap, k), A,
                                {'kappa': kappa_cols(A), 'grading': 'col'}))
    return out


def cls_dbill():
    """Row-graded D*B with B's rows ill-conditioned / B's columns nearly dependent, D = 2^-e_i."""
    rng = random.Random(7002)
    out = []
    for (m, n) in ((3, 3), (4, 3), (5, 4), (8, 6)):
        for kap in (8, 20, 30):
            for span in (0, 600, 1000):
                for k in range(5):
                    b0 = [rfull(rng, -1, 0) for _ in range(m)]
                    cols = [b0]
                    for j in range(1, n):
                        r = [rfull(rng, -1, 0) for _ in range(m)]
                        cols.append([b0[i] + math.ldexp(r[i], -kap) for i in range(m)])
                    B = [[cols[j][i] for j in range(n)] for i in range(m)]
                    ex = sorted([0, span] + [rng.randint(0, span) for _ in range(m - 2)])
                    rng.shuffle(ex)
                    A = [[math.ldexp(B[i][j], -ex[i]) for j in range(n)] for i in range(m)]
                    out.append(('dbill', 'dbill %dx%d kap=2^-%d span=%d #%d' % (m, n, kap, span, k), A,
                                {'kappa': kappa_rows(A), 'grading': 'row'}))
    return out


def cls_tinypar():
    """A tiny genuine column nearly parallel to a large one: [c, eps*(c + delta*r)] (+ a third
    generic column for n = 3).  eps and delta straddle the thresholds where a rotation's formulas
    change: a column ratio of 2^-970, cosines of 2^-13 and 2^-52, exponent gaps of 400, and
    1.2.11's zeta^2 = 2^1024 overflow edge."""
    rng = random.Random(7003)
    out = []
    for m in (2, 3, 5, 10):
        for le in (0, 30, 60, 300, 470, 513, 520, 600, 960, 969, 970, 971, 975, 1000):
            for ld_ in (10, 12, 13, 14, 19, 20, 21, 26, 40, 52):
                for n in (2, 3):
                    if n > m:
                        continue
                    c = [rfull(rng, -1, 0) for _ in range(m)]
                    r = [rfull(rng, -1, 0) for _ in range(m)]
                    s = [math.ldexp(c[i] + math.ldexp(r[i], -ld_), -le) for i in range(m)]
                    if n == 2:
                        A = [[c[i], s[i]] for i in range(m)]
                    else:
                        g = [rfull(rng, -3, 0) for _ in range(m)]
                        A = [[c[i], g[i], s[i]] for i in range(m)]
                    out.append(('tinypar', 'tinypar %dx%d eps=2^-%d delta=2^-%d' % (m, n, le, ld_), A,
                                {'kappa': kappa_cols(A), 'grading': 'col'}))
    return out


def _exact_lowrank(rng, m, n, r, bits=6):
    X = [[rint_(rng, bits) for _ in range(r)] for _ in range(m)]
    Y = [[rint_(rng, bits) for _ in range(n)] for _ in range(r)]
    return [[float(sum(X[i][k] * Y[k][j] for k in range(r))) for j in range(n)] for i in range(m)]


def cls_nullmix():
    """Square rank-deficient: zero rows AND repeated rows AND duplicated columns together, exact
    low-rank integer products (rank 1, n/2, n-1), n up to 30; scaled 2^-1000 / 2^1000 / 2^-1060."""
    rng = random.Random(7004)
    out = []
    for n in (5, 8, 12, 20, 30):
        reps = 4 if n <= 12 else 2
        for k in range(reps):
            for kind in ('z+r', 'z+r+d', 'rank1', 'rankhalf', 'rankn-1', 'neg+z'):
                if kind in ('rank1', 'rankhalf', 'rankn-1'):
                    r = {'rank1': 1, 'rankhalf': n // 2, 'rankn-1': n - 1}[kind]
                    A = _exact_lowrank(rng, n, n, r)
                else:
                    A = rmat(rng, n, n, -3, 0)
                    nz = max(1, n // 6)
                    rows = rng.sample(range(n), 2 * nz + 1)
                    for t in range(nz):
                        A[rows[t]] = [0.0] * n                       # zero rows
                    for t in range(nz, 2 * nz):
                        src = rows[2 * nz]
                        A[rows[t]] = list(A[src]) if kind != 'neg+z' else [-x for x in A[src]]
                    if kind == 'z+r+d':
                        for t in range(max(1, n // 6)):
                            j1, j2 = rng.sample(range(n), 2)
                            for i in range(n):
                                A[i][j2] = A[i][j1]
                for sc in (0, -1000, 1000, -1060):
                    if sc == -1060 and not exact_scale_ok(A, sc):
                        continue
                    if sc == 1000 and kind in ('rank1', 'rankhalf', 'rankn-1'):
                        sc2 = 1000 - 40
                    else:
                        sc2 = sc
                    if sc2 == 1000 or sc2 == 960:
                        if not exact_scale_ok(A, sc2):
                            continue
                    As = scale_mat(A, sc2)
                    out.append(('nullmix', 'nullmix %dx%d %s sc=2^%d #%d' % (n, n, kind, sc2, k), As, {}))
    return out


def cls_tallnull():
    """Tall rank-deficient with exact dependencies: null direction confined to a 2-D span (n=3,
    c3 = a c1 + b c2), exactly parallel pairs (n=2), two dependencies (n=4); m up to 4096."""
    rng = random.Random(7005)
    out = []
    for m in (8, 50, 200, 1000, 4096):
        reps = 3 if m <= 200 else 1
        for k in range(reps):
            for kind in ('n2 c2=3c1', 'n2 c2=-2^-30c1', 'n3 c3=c1+c2', 'n3 c3=3c1-2c2', 'n4 c3=c1+c2 c4=c1-c2',
                         'n3 c3=c1+c2 zero rows'):
                c1 = [rint_(rng, 20) for _ in range(m)]
                c2 = [rint_(rng, 20) for _ in range(m)]
                if kind == 'n2 c2=3c1':
                    A = [[c1[i], 3 * c1[i]] for i in range(m)]
                elif kind == 'n2 c2=-2^-30c1':
                    A = [[c1[i], -math.ldexp(c1[i], -30)] for i in range(m)]
                elif kind == 'n3 c3=c1+c2':
                    A = [[c1[i], c2[i], c1[i] + c2[i]] for i in range(m)]
                elif kind == 'n3 c3=3c1-2c2':
                    A = [[c1[i], c2[i], 3 * c1[i] - 2 * c2[i]] for i in range(m)]
                elif kind == 'n4 c3=c1+c2 c4=c1-c2':
                    A = [[c1[i], c2[i], c1[i] + c2[i], c1[i] - c2[i]] for i in range(m)]
                else:
                    A = [[c1[i], c2[i], c1[i] + c2[i]] for i in range(m)]
                    for i in rng.sample(range(m), max(1, m // 3)):
                        A[i] = [0.0, 0.0, 0.0]
                for sc in (0, -1040, 990):
                    if not exact_scale_ok(A, sc):
                        continue
                    out.append(('tallnull', 'tallnull %dx%d %s sc=2^%d #%d' % (m, len(A[0]), kind, sc, k),
                                scale_mat(A, sc), {}))
    return out


def cls_ulpcols():
    """Columns that differ from column 0 by 1 ulp in one to three entries; several such copies."""
    rng = random.Random(7006)
    out = []
    for (m, n) in ((2, 2), (3, 2), (3, 3), (4, 4), (6, 3), (6, 6), (8, 8), (12, 4)):
        for k in range(6):
            for sc in (0, -1000, 1000):
                base = [rfull(rng, -1, 0) for _ in range(m)]
                A = [[base[i] for _ in range(n)] for i in range(m)]
                for j in range(1, n):
                    for t in rng.sample(range(m), min(m, 1 + (j + k) % 3)):
                        A[t][j] = math.nextafter(A[t][j], math.inf if rng.getrandbits(1) else -math.inf)
                As = scale_mat(A, sc)
                out.append(('ulpcols', 'ulpcols %dx%d sc=2^%d #%d' % (m, n, sc, k), As, {}))
            # subnormal: base ints * 2^-1074, +-1 (one subnormal step) changes
            base = [rint_(rng, 30) for _ in range(m)]
            A = [[base[i] for _ in range(n)] for i in range(m)]
            for j in range(1, n):
                t = rng.randrange(m)
                A[t][j] += 1.0 if rng.getrandbits(1) else -1.0
            out.append(('ulpcols', 'ulpcols %dx%d subnormal #%d' % (m, n, k), scale_mat(A, -1074), {}))
    return out


def _hadamard(n):
    H = np.array([[1.0]])
    while H.shape[0] < n:
        H = np.block([[H, H], [H, -H]])
    return H


def cls_ties():
    """Exactly tied singular values (and 1-ulp near ties), scaled 2^+-1000 / subnormal."""
    rng = random.Random(7007)
    out = []
    items = []
    for k in range(6):
        a, b = rfull(rng, -1, 0), rfull(rng, -1, 0)
        items.append(('rot2 [[a,-b],[b,a]]', [[a, -b], [b, a]]))
        items.append(('rot4x2 [[a,-b],[b,a],[c,-d],[d,c]]', [[a, -b], [b, a], [rfull(rng, -1, 0), 0.0], [0.0, 0.0]]))
        c, d = rfull(rng, -1, 0), rfull(rng, -1, 0)
        items.append(('quat4x2', [[a, -b], [b, a], [c, -d], [d, c]]))
    for n in (2, 4, 8, 16):
        for k in range(3):
            H = _hadamard(n)
            H = H * np.where(np.array([rng.getrandbits(1) for _ in range(n)]) == 1, -1.0, 1.0)[:, None]
            H = H[:, rng.sample(range(n), n)]
            items.append(('hadamard%d' % n, H.tolist()))
            if n >= 4:
                Hs = (H * np.array([2.0 ** -rng.randint(0, 3) for _ in range(n)])[None, :])
                items.append(('hadamard%d colscaled' % n, Hs.tolist()))
    for k in range(4):
        Bm = rmat(rng, 2, 2, -1, 0)
        items.append(('diag(B,B)', [[Bm[0][0], Bm[0][1], 0, 0], [Bm[1][0], Bm[1][1], 0, 0],
                                    [0, 0, Bm[0][0], Bm[0][1]], [0, 0, Bm[1][0], Bm[1][1]]]))
        items.append(('[[B,B],[B,-B]]', [[Bm[0][0], Bm[0][1], Bm[0][0], Bm[0][1]],
                                         [Bm[1][0], Bm[1][1], Bm[1][0], Bm[1][1]],
                                         [Bm[0][0], Bm[0][1], -Bm[0][0], -Bm[0][1]],
                                         [Bm[1][0], Bm[1][1], -Bm[1][0], -Bm[1][1]]]))
        x = rfull(rng, -1, 0)
        items.append(('diag(x,x+ulp)', [[x, 0.0], [0.0, math.nextafter(x, 2)]]))
        items.append(('[[x,x],[x,-x]]', [[x, x], [x, -x]]))
        items.append(('[[x,x+ulp],[x+ulp,-x]]', [[x, math.nextafter(x, 2)], [math.nextafter(x, 2), -x]]))
    for lab, A in items:
        for sc in (0, -1000, 1000, -1070):
            if not exact_scale_ok(A, sc):
                continue
            out.append(('ties', 'ties %s sc=2^%d' % (lab, sc), scale_mat(A, sc), {}))
    return out


def cls_subonly():
    """All entries subnormal (ints * 2^-1074), including rank-deficient and mixed with 2^-1000."""
    rng = random.Random(7008)
    out = []
    for (m, n) in ((2, 2), (3, 2), (3, 3), (4, 4), (6, 3), (8, 6)):
        for bits in (1, 3, 10, 20, 40, 52):
            for kind in ('rand', 'zero-row', 'repeat-row', 'rank1'):
                if kind == 'rank1':
                    hb = max(1, bits // 2)
                    x = [rint_(rng, hb) for _ in range(m)]
                    y = [rint_(rng, hb) for _ in range(n)]
                    A = [[x[i] * y[j] for j in range(n)] for i in range(m)]
                else:
                    A = [[rint_(rng, bits) for _ in range(n)] for _ in range(m)]
                    if kind == 'zero-row':
                        A[rng.randrange(m)] = [0.0] * n
                    elif kind == 'repeat-row':
                        A[m - 1] = list(A[0])
                A = scale_mat(A, -1074)
                out.append(('subonly', 'subonly %dx%d bits=%d %s' % (m, n, bits, kind), A, {}))
        for k in range(3):
            A = [[rint_(rng, 20) * 2.0 ** -1074 if rng.getrandbits(1) else math.ldexp(rfull(rng, 0, 0), -1000)
                  for _ in range(n)] for _ in range(m)]
            out.append(('subonly', 'subonly %dx%d mixed-2^-1000 #%d' % (m, n, k), A, {}))
    return out


def cls_n1():
    rng = random.Random(7009)
    out = []
    for v in (0.0, -0.0, 5.0, -TINY, TINY, DMAX, -DMAX, 2.0 ** -1022, 1.0 / 3):
        out.append(('n1', 'n1 1x1 %r' % v, [[v]], {}))
    for m in (2, 3, 10, 1000):
        for kind in ('rand', 'dmax', 'tiny', 'mix', 'one-nonzero'):
            if kind == 'rand':
                A = [[rfull(rng, -3, 0)] for _ in range(m)]
            elif kind == 'dmax':
                A = [[DMAX if rng.getrandbits(1) else -DMAX] for _ in range(m)]
            elif kind == 'tiny':
                A = [[TINY * rng.randint(1, 3)] for _ in range(m)]
            elif kind == 'mix':
                A = [[rfull(rng, -1074 if False else -1000, 1000)] for _ in range(m)]
            else:
                A = [[0.0] for _ in range(m)]
                A[rng.randrange(m)] = [TINY]
            out.append(('n1', 'n1 %dx1 %s' % (m, kind), A, {}))
    return out


def cls_bigrand():
    """Larger random: convergence within the cap, sweep counts / time."""
    rng = random.Random(7010)
    out = []
    for (m, n, cnt) in ((40, 40, 4), (60, 30, 4), (60, 60, 3), (80, 80, 2), (100, 100, 2), (120, 60, 2)):
        for k in range(cnt):
            out.append(('bigrand', 'bigrand %dx%d well #%d' % (m, n, k), rmat(rng, m, n, -4, -1), {}))
    for (m, n) in ((40, 40), (60, 60)):
        out.append(('bigrand', 'bigrand %dx%d spread60' % (m, n), rmat(rng, m, n, -60, 0), {}))
        out.append(('bigrand', 'bigrand %dx%d rank%d exact' % (m, n, n // 2), _exact_lowrank(rng, m, n, n // 2), {}))
        out.append(('bigrand', 'bigrand %dx%d rank1 exact' % (m, n), _exact_lowrank(rng, m, n, 1, bits=12), {}))
        Ah = [[x for x in r] for r in rmat(rng, m, n, -3, 0)]
        for i in range(0, m, 2):
            Ah[i] = [0.0] * n                  # half the rows zero
        out.append(('bigrand', 'bigrand %dx%d half rows zero' % (m, n), Ah, {}))
        Ad = rmat(rng, m, n // 2, -3, 0)
        Ad = [r + r for r in Ad]               # n/2 identical column pairs
        out.append(('bigrand', 'bigrand %dx%d n/2 dup cols' % (m, n), Ad, {}))
    return out


def _kahan(n, theta, pert):
    s, c = math.sin(theta), math.cos(theta)
    K = [[0.0] * n for _ in range(n)]
    for i in range(n):
        si = s ** i
        for j in range(n):
            if j == i:
                K[i][j] = si * (1 - pert * 100 * U52 * i) if pert else si
            elif j > i:
                K[i][j] = -c * si
    return K


def cls_classic():
    out = []
    for n in (10, 20, 30, 40):
        for theta in (1.2, 0.5, 0.25):
            for pert in (0, 1):
                K = _kahan(n, theta, pert)
                # Kahan is upper-triangular; give it transposed too (lower), both square
                out.append(('classic', 'kahan n=%d theta=%g pert=%d' % (n, theta, pert), K, {}))
                if n == 20:
                    out.append(('classic', 'kahan^T n=%d theta=%g pert=%d' % (n, theta, pert),
                                [list(r) for r in zip(*K)], {}))
                    out.append(('classic', 'kahan*2^-1000 n=%d theta=%g pert=%d' % (n, theta, pert),
                                scale_mat(K, -1000), {}))
    for n in (6, 8, 10, 12, 14):
        out.append(('classic', 'hilbert n=%d' % n, [[1.0 / (i + j + 1) for j in range(n)] for i in range(n)], {}))
    for n in (10, 15, 20):
        P = [[float(math.comb(i + j, i)) for j in range(n)] for i in range(n)]
        out.append(('classic', 'pascal n=%d' % n, P, {}))
    for n in (8, 12, 16):
        V = [[float((i + 1) ** j) for j in range(n)] for i in range(n)]
        out.append(('classic', 'vander n=%d' % n, V, {}))
    for n in (4, 6, 8, 10, 12, 16, 20):
        out.append(('classic', 'magic n=%d' % n, _magic(n), {}))
    for n in (10, 21):
        W = [[0.0] * n for _ in range(n)]
        for i in range(n):
            W[i][i] = float(abs(i - n // 2))
            if i + 1 < n:
                W[i][i + 1] = W[i + 1][i] = 1.0
        out.append(('classic', 'wilkinson n=%d' % n, W, {}))
    for n in (8, 12, 20):
        F = [[float(n + 1 - max(i, j)) if j >= i - 1 else 0.0 for j in range(n)] for i in range(n)]
        out.append(('classic', 'frank n=%d' % n, F, {}))
    return out


def _magic(n):
    import numpy as _np
    if n % 2 == 1:
        M = _np.zeros((n, n))
        i, j = 0, n // 2
        for k in range(1, n * n + 1):
            M[i, j] = k
            i2, j2 = (i - 1) % n, (j + 1) % n
            if M[i2, j2]:
                i2, j2 = (i + 1) % n, j
            i, j = i2, j2
        return M.tolist()
    if n % 4 == 0:
        M = _np.arange(1, n * n + 1).reshape(n, n).astype(float)
        I, J = _np.meshgrid(_np.arange(n), _np.arange(n), indexing='ij')
        mask = ((I % 4) // 2) == ((J % 4) // 2)
        M[mask] = n * n + 1 - M[mask]
        return M.tolist()
    # singly even (LUX-free Strachey)
    h = n // 2
    A = _np.array(_magic(h))
    M = _np.block([[A, A + 2 * h * h], [A + 3 * h * h, A + h * h]])
    k = (n - 2) // 4
    cols = list(range(k)) + list(range(n - k + 1, n))
    for i in range(h):
        for j in cols:
            M[i, j], M[i + h, j] = M[i + h, j], M[i, j]
    M[k, 0], M[k + h, 0] = M[k + h, 0], M[k, 0]
    M[k, k], M[k + h, k] = M[k + h, k], M[k, k]
    return M.tolist()


def cls_rowgradbig():
    """Strongly row-graded (and column-graded) larger matrices: sweep budgets, sweep counts and
    time."""
    rng = random.Random(7011)
    out = []
    for (m, n, span, g) in ((20, 20, 1000, 'row'), (40, 40, 600, 'row'), (40, 40, 1000, 'row'),
                            (40, 40, 1500, 'row'), (60, 60, 1000, 'row'), (80, 40, 1000, 'row'),
                            (40, 40, 1000, 'col'), (60, 60, 1000, 'col'), (40, 40, 1000, 'both'),
                            (30, 30, 1900, 'row'), (30, 30, 1900, 'col')):
        B = rmat(rng, m, n, -1, 0)
        top = 0 if span < 1900 else 950
        if g in ('row', 'both'):
            ex = [top - round(span * i / (m - 1)) for i in range(m)]
            rng.shuffle(ex)
            B = [[math.ldexp(B[i][j], ex[i]) for j in range(n)] for i in range(m)]
        if g in ('col', 'both'):
            ex = [top - round(span * j / (n - 1)) for j in range(n)]
            rng.shuffle(ex)
            B = [[math.ldexp(B[i][j], ex[j]) for j in range(n)] for i in range(m)]
        kap = kappa_rows(B) if g == 'row' else (kappa_cols(B) if g == 'col' else None)
        out.append(('rowgradbig', 'rowgradbig %dx%d %s span=%d' % (m, n, g, span), B,
                    {'kappa': kap, 'grading': g}))
    return out


def cls_fullrange():
    """Entries spread over the whole double range (incl. subnormal), rank-deficient variants, and
    2-column graded matrices whose small column starts near 2^-1074 against a 2^1023 one."""
    rng = random.Random(7012)
    out = []

    def fr():
        e = rng.randint(-1074, 1023)
        if e < -1022:
            v = float(rng.randrange(1, 1 << (e + 1075))) * 2.0 ** -1074
        else:
            v = mkf(rng.getrandbits(52), e)
        return -v if rng.getrandbits(1) else v
    for (m, n) in ((2, 2), (3, 2), (3, 3), (4, 4), (6, 3), (7, 6), (8, 8)):
        for k in range(10):
            A = [[fr() for _ in range(n)] for _ in range(m)]
            out.append(('fullrange', 'fullrange %dx%d rand #%d' % (m, n, k), A, {}))
            if n >= 2:
                A2 = [list(r) for r in A]
                A2[rng.randrange(m)] = [0.0] * n
                if m == n:
                    out.append(('fullrange', 'fullrange %dx%d zero-row #%d' % (m, n, k), A2, {}))
                A3 = [list(r) for r in A]
                j1, j2 = rng.sample(range(n), 2)
                for i in range(m):
                    A3[i][j2] = A3[i][j1]
                out.append(('fullrange', 'fullrange %dx%d dup-col #%d' % (m, n, k), A3, {}))
    # graded 2-col / 3-col: well-conditioned B, columns at 2^1000 and 2^-1000..-1060 (exact)
    for (m, n) in ((3, 2), (4, 3)):
        for lo in (-1000, -1030, -1050, -1060):
            for k in range(4):
                hb = 52 if lo >= -1022 else max(1, 52 - (-1022 - lo) - 2)
                B = [[float(rng.randrange(1 << (hb - 1), 1 << hb)) * (1 if rng.getrandbits(1) else -1)
                      for _ in range(n)] for _ in range(m)]
                ex = [1000 - hb] + [lo - hb + 1 + 0 * j for j in range(1, n)]
                if n == 3:
                    ex[1] = 0 - hb
                A = [[math.ldexp(B[i][j], ex[j] + 1) for j in range(n)] for i in range(m)]
                if not all(Fraction(A[i][j]) == Fraction(B[i][j]) * Fraction(2) ** (ex[j] + 1)
                           for i in range(m) for j in range(n)):
                    continue
                out.append(('fullrange', 'fullrange %dx%d graded 2^1000..2^%d #%d' % (m, n, lo, k), A,
                            {'kappa': kappa_cols([[B[i][j] for j in range(n)] for i in range(m)]),
                             'grading': 'col'}))
    return out


def cls_bunder():
    """Underflowing dot products: two tiny columns (entries ~2^-560 of the largest) on rows the
    big column does not touch, with exact cosine c from 8 u to 2^20 u.  Formed unscaled, their
    dot products underflow (1.2.11 'converges' on them with alpha*beta = gamma = 0), and a
    convergence tolerance of 16*max(2^-52, m*2^-53) leaves the smaller cosines unrotated."""
    rng = random.Random(7013)
    out = []
    for m in (16, 64, 200, 1000):
        for cu in (8, 100, 300, 600, 1000, 4000, 2 ** 20):
            for eq in (0, 1):
                k = max(2, m // 4)
                big = [rfull(rng, -1, 0) for _ in range(k)] + [0.0] * (m - k)
                t = m - k
                x = np.array([rfull(rng, -1, 0) for _ in range(t)])
                y = np.array([rfull(rng, -1, 0) for _ in range(t)])
                x /= np.linalg.norm(x)
                y -= (y @ x) * x
                y /= np.linalg.norm(y)
                c = cu * U52
                y2 = c * x + math.sqrt(1 - c * c) * y
                if not eq:
                    y2 = y2 * 0.75
                col2 = [0.0] * k + [math.ldexp(float(v), -560) for v in x]
                col3 = [0.0] * k + [math.ldexp(float(v), -560) for v in y2]
                A = [[big[i], col2[i], col3[i]] for i in range(m)]
                out.append(('bunder', 'bunder %dx3 cos=%du eqnorm=%d' % (m, cu, eq), A, {}))
    return out


def cls_brestart():
    """A tall block whose two columns have exact cosine c between 256u and m*2^-53 (a tolerance
    of m*2^-53 leaves them unrotated, and U then fails the 256 u bound), next to a square block
    with several null directions (which 1.2.11 cannot finish)."""
    rng = random.Random(7014)
    out = []
    for m in (1200, 2100, 4096):
        for cu in (300, 500, 1024, 2900):
            if cu * 2.0 ** -52 >= m * 2.0 ** -53:
                continue
            for blk in ('6x6 2zero', '8x8 z+r', '8x8 z+r', '8x8 z+r', '10x10 z+r+d', 'sqdef 4x4'):
                bn = int(blk.split('x')[0].split()[-1])
                Bk = rmat(rng, bn, bn, -3, 0)
                if blk == '6x6 2zero':
                    Bk[1] = [0.0] * bn
                    Bk[4] = [0.0] * bn
                elif blk == '8x8 z+r':
                    Bk[2] = [0.0] * bn
                    Bk[5] = list(Bk[0])
                    Bk[7] = [-v for v in Bk[3]]
                elif blk == '10x10 z+r+d':
                    Bk[1] = [0.0] * bn
                    Bk[6] = list(Bk[2])
                    for i in range(bn):
                        Bk[i][9] = Bk[i][4]
                else:
                    Bk[0] = [0.0] * bn
                t = m - bn
                x = np.array([rfull(rng, -1, 0) for _ in range(t)])
                y = np.array([rfull(rng, -1, 0) for _ in range(t)])
                x /= np.linalg.norm(x)
                y -= (y @ x) * x
                y /= np.linalg.norm(y)
                c = cu * U52
                y2 = c * x + math.sqrt(1 - c * c) * y
                n = 2 + bn
                A = []
                for i in range(t):
                    A.append([float(x[i]) * 4, float(y2[i]) * 4] + [0.0] * bn)
                for i in range(bn):
                    A.append([0.0, 0.0] + list(Bk[i]))
                out.append(('brestart', 'brestart %dx%d cos=%du block=%s' % (m, n, cu, blk), A, {}))
    return out


def cls_atall2():
    """Very tall 2-column input with equal-norm columns at an exact cosine between 256u and
    sqrt(m)u: a convergence tolerance of sqrt(m)*2^-52 leaves them unrotated, and U then fails
    the 256 u bound."""
    rng = random.Random(7015)
    out = []
    for (m, cu) in ((262144, 300), (262144, 450), (70000, 258), (16384, 100)):
        x = np.array([rfull(rng, -1, 0) for _ in range(m)])
        y = np.array([rfull(rng, -1, 0) for _ in range(m)])
        x /= np.linalg.norm(x)
        y -= (y @ x) * x
        y /= np.linalg.norm(y)
        c = cu * U52
        y2 = c * x + math.sqrt(1 - c * c) * y
        A = [[float(x[i]), float(y2[i])] for i in range(m)]
        out.append(('atall2', 'atall2 %dx2 cos=%du' % (m, cu), A, {}))
    return out


def cls_thresh():
    """Column pairs across exponent gaps of 398 to 1020 binades, straddling the thresholds where a
    rotation's formulas change (a column ratio of 2^-970, an exponent gap of 400, 1.2.11's
    zeta^2 = 2^1024 edge at 512), with cosines from 0.5 to 1 - 2^-30."""
    rng = random.Random(7016)
    out = []
    for m in (2, 3, 6):
        for g in (398, 400, 402, 511, 512, 513, 514, 968, 969, 970, 971, 972, 1020):
            for cosk in ('0.5', '1-2^-10', '1-2^-30', '2^-30'):
                c = [rfull(rng, -1, 0) for _ in range(m)]
                r = [rfull(rng, -1, 0) for _ in range(m)]
                if cosk == '0.5':
                    s = [c[i] + r[i] for i in range(m)]
                elif cosk == '1-2^-10':
                    s = [c[i] + math.ldexp(r[i], -5) for i in range(m)]
                elif cosk == '1-2^-30':
                    s = [c[i] + math.ldexp(r[i], -15) for i in range(m)]
                else:
                    cc = np.array(c)
                    rr = np.array(r) - (np.array(r) @ cc) / (cc @ cc) * cc
                    s = list(rr + 2.0 ** -30 * cc)
                lo = -g
                top = 0 if g <= 1000 else 1000 - 0
                A = [[math.ldexp(c[i], top), math.ldexp(float(s[i]), top + lo)] for i in range(m)]
                if m >= 3:
                    for i in range(m):
                        A[i] = A[i] + [math.ldexp(rfull(rng, -1, 0), top - g // 2)]
                out.append(('thresh', 'thresh %dx%d gap=%d cos=%s' % (m, len(A[0]), g, cosk), A,
                            {'kappa': kappa_cols(A), 'grading': 'col'}))
    return out


HITS = None   # --hits DIR


def cls_cycle():
    """Inputs from the oracle-free hunt (hunt.py) that some tree failed (status != 0 or a gross
    metric); read from hunt_hits.json (the snapshot the adv set was made from) or, with
    --hits DIR, from DIR/*.json; de-duplicated by bits, at most 400."""
    out = []
    seen = set()
    paths = [os.path.join(HERE, 'hunt_hits.json')]
    if HITS:
        paths = sorted(glob.glob(os.path.join(HITS, '*.json')))
    for p in paths:
        try:
            hits = C.load_hits(p)
        except ValueError as e:
            C.input_error('gen.py: %s' % e)
        for lab, m, n, bl, why in hits:
            key = tuple(bl)
            # numpy-referenced 'nw' alone is not trusted (dgesdd is off by up to ~80 u on clusters);
            # a hit without a `why` is kept
            if why and all(w.startswith('nw') for w in why):
                continue
            if key in seen:
                continue
            if len(out) >= 400:
                print('gen.py: warning: more than 400 usable hits; the class cycle keeps the first 400',
                      file=sys.stderr)
                return out
            seen.add(key)
            out.append(('cycle', 'cycle %s' % lab, ('bits', m, n, bl), {}))
    return out


def cls_subgrad():
    """Row-graded matrices whose small rows are subnormal (exact small-integer mantissas), or whose
    rows span 2^1000 .. 2^-1000 (beyond any single power-of-two pre-scaling into [1, 2)).  B is
    well conditioned, so every sigma is relatively determined (to the subnormal grid's 2^-1074
    absolute resolution for the first kind).  Column-graded counterparts too."""
    rng = random.Random(7017)
    out = []
    for (m, n) in ((2, 2), (3, 2), (3, 3), (4, 3), (5, 4)):
        for lo in (-1000, -1030, -1050, -1060):
            for top in (0, 1000):
                for g in ('row', 'col'):
                    for k in range(3):
                        A = None
                        for _try in range(50):
                            mm, nn = (m, n) if g == 'row' else (n, m)   # build rows, transpose for col
                            ex = [top] + [rng.randint(lo, lo + 10) for _ in range(mm - 1)]
                            rows = []
                            for i in range(mm):
                                bits = 52 if ex[i] >= -1022 + 52 else max(3, ex[i] + 1074)
                                rows.append([float(rng.randrange(1 << (bits - 1), 1 << bits)
                                                   * (1 if rng.getrandbits(1) else -1))
                                             * 2.0 ** 0 for _ in range(nn)])
                                sc = ex[i] - bits + 1
                                rows[-1] = [float(Fraction(int(v)) * Fraction(2) ** sc) for v in rows[-1]]
                            B = [[ld(rows[i][j], -(ex[i])) for j in range(nn)] for i in range(mm)]
                            kb = kappa_cols([list(r) for r in zip(*B)])
                            if kb is not None and kb < 50:
                                A = rows if g == 'row' else [list(r) for r in zip(*rows)]
                                break
                        if A is None:
                            continue
                        kap = kappa_rows(A) if g == 'row' else kappa_cols(A)
                        out.append(('subgrad', 'subgrad %dx%d %s top=2^%d lo=2^%d #%d' % (m, n, g, top, lo, k), A,
                                    {'kappa': kap, 'grading': g}))
    return out


def cls_bigdef():
    """Large rank-deficient squares (many null directions at size: the cost of deflating them and
    the sweep budget) and large random (orthogonality that grows with n)."""
    rng = random.Random(7018)
    out = []
    out.append(('bigdef', 'bigdef 100x100 rank50 exact', _exact_lowrank(rng, 100, 100, 50), {}))
    A = rmat(rng, 100, 100, -3, 0)
    for i in rng.sample(range(100), 50):
        A[i] = [0.0] * 100
    out.append(('bigdef', 'bigdef 100x100 50 zero rows', A, {}))
    A = rmat(rng, 80, 40, -3, 0)
    out.append(('bigdef', 'bigdef 80x80 40 dup col pairs', [r + r for r in A], {}))
    A = rmat(rng, 60, 60, -3, 0)
    for i in range(1, 60, 2):
        A[i] = list(A[i - 1])
    out.append(('bigdef', 'bigdef 60x60 30 repeated rows', A, {}))
    out.append(('bigdef', 'bigdef 120x60 rank30 exact', _exact_lowrank(rng, 120, 60, 30), {}))
    out.append(('bigdef', 'bigdef 60x60 rank59 exact', _exact_lowrank(rng, 60, 60, 59, bits=4), {}))
    out.append(('bigdef', 'bigdef 150x150 random', rmat(rng, 150, 150, -4, -1), {}))
    out.append(('bigdef', 'bigdef 200x200 random', rmat(rng, 200, 200, -4, -1), {}))
    out.append(('bigdef', 'bigdef 300x300 random', rmat(rng, 300, 300, -4, -1), {}))
    out.append(('bigdef', 'bigdef 400x200 random', rmat(rng, 400, 200, -4, -1), {}))
    return out


def cls_bm3():
    """From b_m3_small.json, 40 small inputs of hunt.py's subrow family: one or two normal rows
    over rows with short mantissas 2^1000 or more below (some scaled so every entry is normal),
    on which a sweep budget can run out (status -3)."""
    p = os.path.join(HERE, 'b_m3_small.json')
    out = []
    if not os.path.exists(p):
        return out
    for h in json.load(open(p))[:40]:
        out.append(('bm3', 'bm3 %s' % h['label'].split(' [')[0], ('bits', h['rows'], h['cols'],
                                                                   [int(x, 16) for x in h['bits']]), {}))
    return out


def cls_reprows():
    """Tall matrices made of a few repeated rows (and a constant column): the column norms and
    Householder norms are recursive sums of m equal terms, whose rounding error is biased."""
    rng = random.Random(3)
    out = []
    for m in (1024, 4096, 8192, 16384, 65536):
        out.append(('reprows', 'reprows %dx2 rows (1,2)' % m, [[1.0, 2.0]] * m, {}))
        out.append(('reprows', 'reprows %dx2 rows (0.1,0.7)' % m, [[0.1, 0.7]] * m, {}))
        out.append(('reprows', 'reprows %dx2 rows (1,k) k=i%%10' % m, [[1.0, float(i % 10)] for i in range(m)], {}))
        a = [rfull(rng, -1, 0) for _ in range(4)]
        out.append(('reprows', 'reprows %dx2 two rows alternating' % m,
                    [[a[0], a[1]] if i % 2 else [a[2], a[3]] for i in range(m)], {}))
        out.append(('reprows', 'reprows %dx1 all 0.1' % m, [[0.1]] * m, {}))
    for m in (4096, 8192):
        out.append(('reprows', 'reprows %dx3 rows (1,k,k^2) k=i%%7, +zero rows' % m,
                    [[1.0, float(i % 7), float((i % 7) ** 2)] if i % 5 else [0.0, 0.0, 0.0] for i in range(m)], {}))
    return out


def cls_rgfail():
    """Row-graded D*B (B random, rows spread linearly over `span` binades, shuffled), at sizes
    where a cap of 60 sweeps can be reached."""
    out = []
    for (n, mm, span, seed) in ((50, 50, 600, 1), (60, 60, 450, 2), (60, 60, 600, 3), (80, 80, 300, 4),
                                (80, 80, 450, 5), (100, 100, 200, 6), (100, 100, 300, 7), (60, 120, 1000, 8)):
        rng = random.Random(9000 + seed)
        B = rmat(rng, mm, n, -1, 0)
        ex = [-round(span * i / (mm - 1)) for i in range(mm)]
        rng.shuffle(ex)
        A = [[math.ldexp(B[i][j], ex[i]) for j in range(n)] for i in range(mm)]
        out.append(('rgfail', 'rgfail %dx%d row span=%d seed=%d' % (mm, n, span, seed), A,
                    {'kappa': kappa_rows(A), 'grading': 'row'}))
    return out


CLASSES = [
    ('bdill', cls_bdill), ('dbill', cls_dbill), ('tinypar', cls_tinypar), ('thresh', cls_thresh),
    ('nullmix', cls_nullmix), ('tallnull', cls_tallnull), ('ulpcols', cls_ulpcols), ('ties', cls_ties),
    ('subonly', cls_subonly), ('n1', cls_n1), ('bigrand', cls_bigrand), ('classic', cls_classic),
    ('rowgradbig', cls_rowgradbig), ('fullrange', cls_fullrange), ('bunder', cls_bunder),
    ('brestart', cls_brestart), ('atall2', cls_atall2), ('subgrad', cls_subgrad), ('bigdef', cls_bigdef),
    ('cycle', cls_cycle), ('bm3', cls_bm3), ('reprows', cls_reprows), ('rgfail', cls_rgfail),
]


def _np_oracle(item):
    """Fallback for matrices too big for mpmath: numpy sigma (normwise to a few u), rel_ok False."""
    m, n, bl = item['rows'], item['cols'], item['bits']
    A = np.array([f_of(b) for b in bl]).reshape(m, n)
    s = np.linalg.svd(A, compute_uv=False)
    fs = [Fraction(float(x)) for x in s]
    return {'reject': False, 'bits': [bits_of(float(x)) for x in s], 'rel_ok': [False] * n,
            'rank': int(np.sum(s > s[0] * n * 2.0 ** -52)), 'method': 'numpy', 'prec': 53,
            'hp': [C.frac_m64e(f) for f in fs]}


def worker(args):
    idx, item = args
    t0 = time.time()
    if item['rows'] * item['cols'] > 50000:
        if item['cols'] <= 2:
            r = C.oracle_worker((idx, item))[1]
        else:
            r = _np_oracle(item)
    else:
        r = C.oracle_worker((idx, item))[1]
    r['secs'] = time.time() - t0
    return idx, r


ADV2 = ['bm3', 'reprows', 'rgfail']
ADV = [name for name, _ in CLASSES if name not in ADV2]


def main():
    global HITS
    ap = argparse.ArgumentParser(description='Build an adversarial set (adv by default) and its exact '
                                 'oracle.')
    ap.add_argument('--out', default='adv', metavar='DIR',
                    help="output directory; without a '/' a name under $SVDH_WORK (default adv)")
    ap.add_argument('--classes', metavar='A,B,...',
                    help='classes to build (default: every class except %s, the set adv; adv2 is '
                    '--classes %s)' % (','.join(ADV2), ','.join(ADV2)))
    ap.add_argument('--procs', type=C.procs_arg, default=os.cpu_count() or 1, metavar='N',
                    help='oracle processes (default: every CPU)')
    ap.add_argument('--hits', metavar='DIR', help="the class cycle reads DIR/*.json (hunt.py's hits) "
                    'instead of hunt_hits.json')
    a = ap.parse_args()
    out = a.out
    if '/' not in out:
        out = os.path.join(C.WORK, out)
    want = ADV
    if a.classes is not None:
        want = a.classes.split(',')
        unknown = [w for w in want if w not in dict(CLASSES)]
        if unknown:
            ap.error('unknown class(es) %s; known: %s' % (','.join(unknown), ','.join(dict(CLASSES))))
    if a.hits is not None:
        if not os.path.isdir(a.hits):
            ap.error('--hits %s is not a directory' % a.hits)
        HITS = a.hits
    C.check_versions()
    C.blas_setup()
    C.term_as_exit()
    _build(out, want, a.procs)


def _build(out, want, procs):
    t0 = time.time()
    items = []
    for name, fn in CLASSES:
        if want and name not in want:
            continue
        for cls, label, A, extra in fn():
            if isinstance(A, tuple) and A[0] == 'bits':
                _, m, n, bl = A
            else:
                m, n = len(A), len(A[0])
                bl = [bits_of(float(A[i][j])) for i in range(m) for j in range(n)]
            assert m >= n >= 1 and len(bl) == m * n, label
            for b in bl:
                assert (b & 0x7FF0000000000000) != 0x7FF0000000000000, label
            items.append({'class': cls, 'label': label, 'rows': m, 'cols': n, 'bits': bl, 'extra': extra})
    N = len(items)
    counts = {}
    for it in items:
        counts[it['class']] = counts.get(it['class'], 0) + 1
    print('corpus: %d matrices (%.1fs)' % (N, time.time() - t0), counts, flush=True)
    if N == 0:
        C.input_error('gen.py: no matrices (an empty class selection, or no usable hits)')
    C.make_outdir('gen.py', out)
    try:
        _write(out, items, counts, procs, t0)
    except BaseException:
        C.discard_tmp(out)
        raise


def _write(out, items, counts, procs, t0):
    N = len(items)
    with open(C.tmp_path(out, 'corpus.bin'), 'wb') as fh:
        fh.write(struct.pack('<Q', N))
        for it in items:
            fh.write(struct.pack('<QQ', it['rows'], it['cols']))
            fh.write(struct.pack('<%dQ' % len(it['bits']), *it['bits']))
    meta = [{'id': k, 'class': it['class'], 'label': it['label'], 'rows': it['rows'], 'cols': it['cols'],
             **it['extra']} for k, it in enumerate(items)]
    with open(C.tmp_path(out, 'corpus_meta.json'), 'w') as fh:
        json.dump(meta, fh, indent=0)
    order = sorted(range(N), key=lambda k: -(items[k]['rows'] * items[k]['cols'] ** 2))
    orc = [None] * N
    t1 = time.time()
    # The numpy sigma of bigdef (_np_oracle) depends on OpenBLAS's thread count: set it here too.
    with mproc.Pool(procs, initializer=C.blas_setup, initargs=(True,)) as pool:
        done = 0
        for idx, r in pool.imap_unordered(worker, ((k, items[k]) for k in order), chunksize=1):
            orc[idx] = r
            done += 1
            if done % 500 == 0:
                print('  oracle %d/%d (%.0fs)' % (done, N, time.time() - t1), flush=True)
    print('oracle: %.1fs; slowest %.1fs' % (time.time() - t1, max(r['secs'] for r in orc)), flush=True)
    nrel = sum(1 for r in orc for x in r['rel_ok'] if not x)
    print('oracle: uncertified sigma %d; methods %s; max prec %d' % (
        nrel, sorted(set(r['method'] for r in orc)), max(r['prec'] for r in orc)))
    mats = []
    for k, r in enumerate(orc):
        mats.append({'id': k, 'reject': False, 'sigma_bits': ['%016x' % b for b in r['bits']],
                     'hp': [list(x) for x in r['hp']], 'rel_ok': r['rel_ok'], 'rank': r['rank'],
                     'method': r['method'], 'prec': r['prec']})
    with open(C.tmp_path(out, 'oracle.json'), 'w') as fh:
        json.dump({'info': {'count': N, 'classes': counts, 'uncertified_sigma': nrel}, 'matrices': mats}, fh)
    C.publish(out)
    print('wrote %s in %.1fs' % (out, time.time() - t0))


if __name__ == '__main__':
    main()
