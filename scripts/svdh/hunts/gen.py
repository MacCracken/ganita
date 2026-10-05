#!/usr/bin/env python3
"""Hunt sets with an exact oracle: families of matrices aimed at specific edges of an SVD.

Writes corpus.bin / corpus_meta.json / oracle.json into the directory given by --out (same
formats as ../corpus.py), using ../corpus.py's exact oracle where possible and exact structural
oracles (block union, known sigma^2, exact Gram + eigsy) where the generic one is too slow.  Where
mpmath.svd_r does not converge (a RuntimeError from corpus.oracle_one), the generic oracle falls
back to the Gram one (method 'gram') and says so on stderr, naming the matrix by corpus id and
label; in the five sets of README.md that happens once, in s2 (id 478, hadamard dup-row 32x32
e=-1020).  The three files are written under temporary names and renamed together at the end.

usage: gen.py --out DIR --set NAME[,NAME...] [--procs N] [--seed 20261004]
A DIR without '/' is a name under $SVDH_WORK/hunts.  NAMEs are the families in FAMS below; each
draws from random.Random(seed + sum of the name's character codes), so a family's matrices do not
depend on which others are in the set, but their order in the corpus follows --set (a family
given twice is refused).  --procs: oracle processes, default every CPU (no output byte depends on
it).  boundary scales by numpy's sigma_1, which depends on numpy's BLAS kernels
(corpus.blas_setup, README.md).
"""
import argparse
import json
import math
import os
import random
import struct
import sys
import time
from fractions import Fraction
import multiprocessing as mproc

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import corpus as C   # noqa: E402
import mpmath        # noqa: E402

bits_of, f_of, mkf, rfull = C.bits_of, C.f_of, C.mkf, C.rfull
DBL_MAX = float.fromhex('0x1.fffffffffffffp+1023')


# ------------------------------------------------------------------ oracle kinds
_JOB = None   # (corpus id, label, rows, cols) of the matrix run_oracle works on, for messages


def orc_generic(m, n, bl):
    """corpus.py's oracle; the Gram one where mpmath.svd_r does not converge."""
    try:
        return C.oracle_one({'rows': m, 'cols': n, 'bits': bl})
    except RuntimeError as e:
        k, lab, jm, jn = _JOB or (-1, '?', m, n)
        part = '' if (m, n) == (jm, jn) else ' on a %dx%d part of it' % (m, n)
        print('%s: id %d (%s): the generic oracle failed%s (%s); using the Gram oracle'
              % (os.path.basename(sys.argv[0]) or 'gen.py', k, lab, part, e), file=sys.stderr, flush=True)
        return orc_gram(m, n, bl)


def strip_zero_rows(m, n, bl):
    rows = [bl[i * n:(i + 1) * n] for i in range(m)]
    keep = [r for r in rows if any((b & 0x7FFFFFFFFFFFFFFF) != 0 for b in r)]
    if len(keep) < n:
        keep += [[0] * n] * (n - len(keep))
    return len(keep), [b for r in keep for b in r]


def orc_strip(m, n, bl):
    m2, bl2 = strip_zero_rows(m, n, bl)
    if m2 * n > 20000 and n >= 3:
        return orc_gram(m2, n, bl2)
    return orc_generic(m2, n, bl2)


def orc_blocks(blocks, n):
    """blocks: list of (mb, nb, bits) whose sigma union (+ zeros to n) is A's sigma."""
    sig, ok = [], []
    for (mb, nb, bl) in blocks:
        r = orc_generic(mb, nb, bl)
        sig += r['sigma']
        ok += r['rel_ok']
    while len(sig) < n:
        sig.append(Fraction(0))
        ok.append(True)
    order = sorted(range(len(sig)), key=lambda i: -sig[i])
    sig = [sig[i] for i in order][:n]
    ok = [ok[i] for i in order][:n]
    bits = [C.round_frac_bits(f) for f in sig]
    return {'reject': False, 'sigma': sig, 'bits': bits, 'rel_ok': ok,
            'rank': sum(1 for f in sig if f != 0), 'method': 'blocks', 'prec': 0}


def orc_lams(lams, n):
    lams = sorted(lams, reverse=True)
    return C._from_lambdas_exact(lams, n, 'lams', None, rank=sum(1 for x in lams if x != 0))


def orc_gram(m, n, bl):
    """Exact Gram matrix, rank by Bareiss on it, eigenvalues by mp.eigsy at adaptive precision."""
    F = [Fraction(f_of(b)) for b in bl]
    if all(x == 0 for x in F):
        return C.oracle_one({'rows': m, 'cols': n, 'bits': bl})
    G = [[Fraction(0)] * n for _ in range(n)]
    for i in range(m):
        row = F[i * n:(i + 1) * n]
        if not any(row):
            continue
        for a in range(n):
            if row[a] == 0:
                continue
            for b in range(a, n):
                G[a][b] += row[a] * row[b]
    for a in range(n):
        for b in range(a):
            G[a][b] = G[b][a]
    K = 0
    for a in range(n):
        for b in range(n):
            if G[a][b] != 0:
                K = max(K, G[a][b].denominator.bit_length() - 1)
    Gi = [[int(G[a][b] * (1 << K)) for b in range(n)] for a in range(n)]
    rank, _ = C._bareiss_rank_det(Gi)
    P = 256
    while True:
        mpmath.mp.prec = P
        M = mpmath.matrix(n, n)
        for a in range(n):
            for b in range(n):
                M[a, b] = mpmath.mpf(G[a][b].numerator) / G[a][b].denominator
        E = mpmath.eigsy(M, eigvals_only=True)
        lam = sorted([E[i] for i in range(n)], reverse=True)
        l1 = lam[0]
        need = 200
        if rank > 0 and lam[rank - 1] > 0:
            need = 200 + math.ceil(float(mpmath.log(l1 / lam[rank - 1], 2)))
        else:
            need = P * 2
        if need > P and P < 30000:
            P = max(need + 32, P * 2 if rank > 0 and lam[rank - 1] <= 0 else need + 32)
            continue
        rad_l = l1 * mpmath.mpf(2) ** (-P + 20)
        sig, bits, ok = [], [], []
        for i in range(n):
            if i >= rank:
                sig.append(Fraction(0))
                bits.append(0)
                ok.append(True)
                continue
            s = mpmath.sqrt(lam[i])
            f = C.mpf_to_frac(s)
            rad = C.mpf_to_frac(rad_l / (2 * s))
            b = C._certify(f, rad)
            sig.append(f)
            bits.append(b if b is not None else C.round_frac_bits(f))
            ok.append(b is not None)
        if all(ok) or P >= 30000:
            return {'reject': False, 'sigma': sig, 'bits': bits, 'rel_ok': ok, 'rank': rank,
                    'method': 'gram', 'prec': P}
        P *= 2


def run_oracle(job):
    """job: (corpus id, oracle kind, payload, rows, cols, bits[, label]); returns (id, oracle)."""
    global _JOB
    k, kind, payload, m, n, bl = job[:6]
    _JOB = (k, job[6] if len(job) > 6 else '?', m, n)
    if kind == 'generic':
        r = orc_generic(m, n, bl)
    elif kind == 'strip':
        r = orc_strip(m, n, bl)
    elif kind == 'blocks':
        r = orc_blocks(payload, n)
    elif kind == 'lams':
        r = orc_lams(payload, n)
    elif kind == 'gram':
        r = orc_gram(m, n, bl)
    else:
        raise ValueError(kind)
    if not r['reject']:
        r['hp'] = [C.frac_m64e(f) for f in r['sigma']]
        del r['sigma']
    return k, r


# ------------------------------------------------------------------ helpers
def B(A):
    return [bits_of(float(x)) for row in A for x in row]


def perm_rows_cols(rng, A, signs=True):
    m, n = len(A), len(A[0])
    pr = list(range(m))
    rng.shuffle(pr)
    pc = list(range(n))
    rng.shuffle(pc)
    sr = [(-1 if (signs and rng.getrandbits(1)) else 1) for _ in range(m)]
    sc = [(-1 if (signs and rng.getrandbits(1)) else 1) for _ in range(n)]
    return [[sr[i] * sc[j] * A[pr[i]][pc[j]] for j in range(n)] for i in range(m)]


def hadamard(n):
    H = [[1]]
    while len(H) < n:
        H = [r + r for r in H] + [r + [-x for x in r] for r in H]
    return H


# ------------------------------------------------------------------ families
def fam_blockdiag(rng, out):
    """Block-diagonal with wildly different block scales, rows/cols permuted and signed."""
    for k in range(240):
        nb = rng.randint(2, 5)
        sizes = [rng.choice([1, 1, 2, 2, 3, 4]) for _ in range(nb)]
        n = sum(sizes)
        extra = rng.choice([0, 0, 1, 3, n])
        m = n + extra
        exps = [rng.randint(-1060, 1000) for _ in range(nb)]
        if k % 3 == 0:
            exps = [rng.choice([-1070, -1040, -1000, -600, 0, 600, 1000, 1015]) for _ in range(nb)]
        A = [[0.0] * n for _ in range(m)]
        blocks = []
        r0 = c0 = 0
        for sz, e in zip(sizes, exps):
            Bk = [[rfull(rng, e - 3, e) for _ in range(sz)] for _ in range(sz)]
            if rng.random() < 0.25 and sz >= 2:
                Bk[-1] = list(Bk[0])           # rank-deficient block
            for i in range(sz):
                for j in range(sz):
                    A[r0 + i][c0 + j] = Bk[i][j]
            blocks.append((sz, sz, B(Bk)))
            r0 += sz
            c0 += sz
        A = perm_rows_cols(rng, A)
        out.append(('blockdiag', 'blockdiag %dx%d sizes=%s exps=%s #%d' % (m, n, sizes, exps, k), m, n, B(A),
                    'blocks', blocks))


def fam_hadamard(rng, out):
    for n in (2, 4, 8, 16, 32, 64):
        H = hadamard(n)
        for e in (0, 1, 500, 1000, 1015, -500, -1000, -1020, -1060, -1074 + 1):
            if e + 0.5 * math.log2(n) > 1023.9:
                continue
            for var in ('plain', 'zero-row', 'tall-zero', 'dup-row', 'stack'):
                if var == 'stack' and n > 32:
                    continue
                A = [[math.ldexp(float(x), e) for x in r] for r in H]
                A = perm_rows_cols(rng, A)
                m = n
                lams = None
                if var == 'plain':
                    lams = [Fraction(n) * Fraction(2) ** (2 * e)] * n
                elif var == 'zero-row':
                    r = rng.randrange(n)
                    A[r] = [0.0] * n
                    lams = [Fraction(n) * Fraction(2) ** (2 * e)] * (n - 1) + [Fraction(0)]
                elif var == 'tall-zero':
                    A = A + [[0.0] * n for _ in range(3)]
                    m = n + 3
                    lams = [Fraction(n) * Fraction(2) ** (2 * e)] * n
                elif var == 'dup-row':
                    r, s = rng.sample(range(n), 2)
                    A[r] = list(A[s])
                elif var == 'stack':
                    A = A + perm_rows_cols(rng, [[math.ldexp(float(x), e) for x in r] for r in H], signs=False)
                    m = 2 * n
                    # [P1 H Q1; P2 H Q2]: Gram = H^T H + Q^T H^T H Q... column perms differ -> generic
                    lams = None
                lab = 'hadamard %s %dx%d e=%d' % (var, m, n, e)
                if lams is not None:
                    out.append(('hadamard', lab, m, n, B(A), 'lams', lams))
                elif m * n <= 1200:
                    out.append(('hadamard', lab, m, n, B(A), 'generic', None))
                else:
                    out.append(('hadamard', lab, m, n, B(A), 'gram', None))


def fam_signedperm(rng, out):
    """Exact repeated sigma (signed permutations, [I;I]) with zero rows / dup rows."""
    for n in (2, 3, 4, 5, 8, 12, 20):
        for e in (0, -1074, -1022, 1023, -537, 512):
            for var in ('perm', 'perm-zero', 'perm-dup', 'IoverI', 'IoverI-zero'):
                base = [[0.0] * n for _ in range(n)]
                for i in range(n):
                    base[i][i] = math.ldexp(1.0, e)
                A = perm_rows_cols(rng, base)
                m = n
                if var == 'perm':
                    lams = [Fraction(2) ** (2 * e)] * n
                elif var == 'perm-zero':
                    A[rng.randrange(n)] = [0.0] * n
                    lams = [Fraction(2) ** (2 * e)] * (n - 1) + [Fraction(0)]
                elif var == 'perm-dup':
                    r, s = rng.sample(range(n), 2)
                    A[r] = list(A[s])
                    lams = [Fraction(2) ** (2 * e)] * (n - 2) + [Fraction(2) * Fraction(2) ** (2 * e), Fraction(0)]
                elif var == 'IoverI':
                    A = A + perm_rows_cols(rng, base)
                    m = 2 * n
                    lams = None
                else:
                    A = A + perm_rows_cols(rng, base)
                    A[rng.randrange(2 * n)] = [0.0] * n
                    m = 2 * n
                    lams = None
                lab = 'sperm %s %dx%d e=%d' % (var, m, n, e)
                if lams is not None:
                    out.append(('sperm', lab, m, n, B(A), 'lams', lams))
                else:
                    out.append(('sperm', lab, m, n, B(A), 'gram', None))


def fam_tall(rng, out):
    for m in (1000, 10000, 100000):
        # n = 1
        for var in ('rand', 'const', 'spread', 'onebig', 'sub', 'dblmax'):
            if var == 'rand':
                col = [rfull(rng, -3, 0) for _ in range(m)]
            elif var == 'const':
                col = [0.1] * m
            elif var == 'spread':
                col = [rfull(rng, -1074, 1000) for _ in range(m)]
            elif var == 'onebig':
                col = [rfull(rng, -1074, -1000) for _ in range(m)]
                col[rng.randrange(m)] = 1.5
            elif var == 'sub':
                col = [f_of(rng.randrange(1, 1 << 52)) for _ in range(m)]
            else:
                col = [DBL_MAX * (1 - 2 * rng.getrandbits(1)) * (0.5 + rng.random() / 2) for _ in range(m)]
            out.append(('tall1', 'tall1 %s %dx1' % (var, m), m, 1, [bits_of(x) for x in col], 'generic', None))
        # n = 2
        for var in ('rand', 'par', 'near-par', 'near-par2', 'antipar', 'rows12', 'graded', 'subcol', 'dblmax',
                    'rank1-rand', 'orth'):
            A = []
            if var == 'rand':
                A = [[rfull(rng, -3, 0), rfull(rng, -3, 0)] for _ in range(m)]
            elif var == 'par':
                for _ in range(m):
                    x = rfull(rng, -3, 0)
                    A.append([x, x])
            elif var == 'near-par':
                for _ in range(m):
                    x = rfull(rng, -3, 0)
                    A.append([x, x * (1 + 2.0 ** -40)])
            elif var == 'near-par2':
                for i in range(m):
                    x = rfull(rng, -3, 0)
                    y = x if i != m // 2 else math.nextafter(x, math.inf)
                    A.append([x, y])
            elif var == 'antipar':
                for _ in range(m):
                    x = rfull(rng, -3, 0)
                    A.append([x, -3 * x])
            elif var == 'rows12':
                A = [[1.0, 2.0] for _ in range(m)]
            elif var == 'graded':
                A = [[rfull(rng, -3, 0), rfull(rng, -1074, -1000)] for _ in range(m)]
            elif var == 'subcol':
                A = [[rfull(rng, 990, 1000), f_of(rng.randrange(1, 1 << 52))] for _ in range(m)]
            elif var == 'dblmax':
                A = [[DBL_MAX * (0.5 + rng.random() / 2), -DBL_MAX * (0.5 + rng.random() / 2)] for _ in range(m)]
            elif var == 'rank1-rand':
                a, b = rfull(rng, -3, 0), rfull(rng, -3, 0)
                for _ in range(m):
                    x = rng.choice([1.0, 2.0, 0.5, 4.0, -1.0, 0.25])
                    A.append([a * x, b * x])
            elif var == 'orth':
                for i in range(m):
                    A.append([1.0, 1.0 if i % 2 == 0 else -1.0])
            out.append(('tall2', 'tall2 %s %dx2' % (var, m), m, 2, B(A), 'generic', None))
        if m <= 10000:
            for n in (3, 4, 6):
                for var in ('rand', 'par2', 'rows', 'zero-ish'):
                    if var == 'rand':
                        A = [[rfull(rng, -3, 0) for _ in range(n)] for _ in range(m)]
                    elif var == 'par2':
                        A = []
                        for _ in range(m):
                            r = [rfull(rng, -3, 0) for _ in range(n)]
                            r[1] = r[0]
                            A.append(r)
                    elif var == 'rows':
                        base = [rfull(rng, -3, 0) for _ in range(n)]
                        A = [list(base) for _ in range(m)]
                        A[0][n - 1] = A[0][n - 1] * 2
                    else:
                        A = [[rfull(rng, -3, 0) for _ in range(n)] for _ in range(m)]
                        for i in range(m):
                            A[i][n - 1] = A[i][0] + A[i][1] if abs(A[i][0] + A[i][1]) < 4 else 0.0
                    out.append(('tallN', 'tallN %s %dx%d' % (var, m, n), m, n, B(A), 'gram', None))


def fam_dblmax(rng, out):
    for n in (1, 2, 3, 4, 5, 6, 10, 20):
        for mm in (n, 2 * n):
            for var in ('rand', 'allmax', 'checker', 'mixed', 'rowsmax', 'tri'):
                if var == 'rand':
                    A = [[DBL_MAX * (0.5 + rng.random() / 2) * (1 - 2 * rng.getrandbits(1)) for _ in range(n)]
                         for _ in range(mm)]
                elif var == 'allmax':
                    A = [[DBL_MAX] * n for _ in range(mm)]
                elif var == 'checker':
                    A = [[DBL_MAX * (1 if (i + j) % 2 == 0 else -1) for j in range(n)] for i in range(mm)]
                elif var == 'mixed':
                    A = [[rfull(rng, 1015, 1023) if rng.random() < .5 else rfull(rng, -1074, -1000)
                          for _ in range(n)] for _ in range(mm)]
                elif var == 'rowsmax':
                    A = [[DBL_MAX * (0.5 + rng.random() / 2) for _ in range(n)] for _ in range(mm)]
                    A[-1] = list(A[0])
                else:
                    A = [[(DBL_MAX * (0.5 + rng.random() / 2) if j >= i else 0.0) for j in range(n)] for i in range(mm)]
                kind = 'generic' if mm * n <= 400 else 'gram'
                out.append(('dblmax', 'dblmax %s %dx%d' % (var, mm, n), mm, n, B(A), kind, None))


def fam_allsub(rng, out):
    for n in (1, 2, 3, 4, 5, 6, 8, 10):
        for mm in (n, n + 2, 3 * n):
            for var in ('rand', 'tiny-int', 'ones', 'rankdef', 'mix-norm'):
                for rep in range(3):
                    if var == 'rand':
                        A = [[f_of(rng.randrange(0, 1 << 52) | (rng.getrandbits(1) << 63)) for _ in range(n)]
                             for _ in range(mm)]
                    elif var == 'tiny-int':
                        A = [[rng.choice([-3, -2, -1, 0, 1, 2, 3]) * 5e-324 for _ in range(n)] for _ in range(mm)]
                    elif var == 'ones':
                        A = [[(1 - 2 * rng.getrandbits(1)) * 5e-324 for _ in range(n)] for _ in range(mm)]
                    elif var == 'rankdef':
                        X = [[rng.randint(-7, 7) for _ in range(2)] for _ in range(mm)]
                        Y = [[rng.randint(-7, 7) for _ in range(n)] for _ in range(2)]
                        A = [[sum(X[i][l] * Y[l][j] for l in range(2)) * 5e-324 for j in range(n)] for i in range(mm)]
                    else:
                        A = [[f_of(rng.randrange(0, 1 << 52)) for _ in range(n)] for _ in range(mm)]
                        A[rng.randrange(mm)][rng.randrange(n)] = 2.2250738585072014e-308 * (1 + rng.random())
                    out.append(('allsub', 'allsub %s %dx%d #%d' % (var, mm, n, rep), mm, n, B(A), 'generic', None))


def fam_checker(rng, out):
    for n in (2, 3, 4, 5, 6, 8, 12):
        for mm in (n, n + 1, 2 * n):
            for var in ('rand', 'const', 'const-pert', 'scaled-sub', 'scaled-big'):
                for rep in range(2):
                    if var == 'rand':
                        A = [[abs(rfull(rng, -3, 0)) * (1 if (i + j) % 2 == 0 else -1) for j in range(n)]
                             for i in range(mm)]
                    elif var == 'const':
                        A = [[(1.0 if (i + j) % 2 == 0 else -1.0) for j in range(n)] for i in range(mm)]
                    elif var == 'const-pert':
                        A = [[(1.0 if (i + j) % 2 == 0 else -1.0) for j in range(n)] for i in range(mm)]
                        i0, j0 = rng.randrange(mm), rng.randrange(n)
                        A[i0][j0] = math.nextafter(A[i0][j0], math.inf)
                    elif var == 'scaled-sub':
                        A = [[(5e-324 if (i + j) % 2 == 0 else -5e-324) * rng.randint(1, 3) for j in range(n)]
                             for i in range(mm)]
                    else:
                        A = [[(DBL_MAX if (i + j) % 2 == 0 else -DBL_MAX) / rng.randint(1, 3) for j in range(n)]
                             for i in range(mm)]
                    out.append(('checker', 'checker %s %dx%d #%d' % (var, mm, n, rep), mm, n, B(A), 'generic', None))


def fam_tri(rng, out):
    for n in (2, 3, 4, 6, 10, 20):
        for d in (1.0, 2.0 ** -30, 2.0 ** -300, 2.0 ** -1000, 5e-324, 0.0, 2.0 ** -1022):
            for low in (0, 1):
                for var in ('ones', 'rand'):
                    A = [[0.0] * n for _ in range(n)]
                    for i in range(n):
                        for j in range(i + 1, n):
                            A[i][j] = 1.0 if var == 'ones' else rfull(rng, -3, 0)
                        A[i][i] = d
                    if low:
                        A = [[A[j][i] for j in range(n)] for i in range(n)]
                    out.append(('tri', 'tri %s %s d=%r %dx%d' % ('low' if low else 'up', var, d, n, n), n, n, B(A),
                                'generic', None))
    # graded diagonal upper triangular
    for n in (4, 8, 16):
        for rep in range(4):
            A = [[0.0] * n for _ in range(n)]
            for i in range(n):
                e = -int(i * (1074 / (n - 1)))
                A[i][i] = mkf(rng.getrandbits(52), max(e, -1074)) if e >= -1022 else 5e-324 * rng.randint(1, 1000)
                for j in range(i + 1, n):
                    A[i][j] = rfull(rng, -3, 0) if rep % 2 == 0 else A[i][i]
            out.append(('tri', 'tri graded %dx%d #%d' % (n, n, rep), n, n, B(A), 'generic', None))
    # Wilkinson-ish: unit upper with -1 above (cond ~ 2^n)
    for n in (10, 20, 40):
        A = [[(1.0 if i == j else (-1.0 if j > i else 0.0)) for j in range(n)] for i in range(n)]
        out.append(('tri', 'tri wilk %dx%d' % (n, n), n, n, B(A), 'generic', None))


def kahan(n, c, pert):
    s = math.sqrt(1 - c * c)
    A = [[0.0] * n for _ in range(n)]
    for i in range(n):
        si = s ** i
        for j in range(n):
            if j == i:
                A[i][j] = si * (1 - pert * i) if pert else si
            elif j > i:
                A[i][j] = -c * si
    return A


def fam_kahan(rng, out):
    for n in (10, 20, 40):
        for c in (0.285, 0.2, 0.5, 0.1):
            for pert in (0.0, 100 * 2.0 ** -52):
                A = kahan(n, c, pert)
                out.append(('kahan', 'kahan n=%d c=%g pert=%g' % (n, c, pert), n, n, B(A), 'generic', None))
                if n == 40:
                    T = [list(r) for r in A] + [[0.0] * n for _ in range(n)]
                    out.append(('kahan', 'kahan tall-zero n=%d c=%g pert=%g' % (n, c, pert), 2 * n, n, B(T),
                                'strip', None))


def fam_ties(rng, out):
    for n in (2, 3, 4, 5, 6, 8, 10, 16):
        for e in (0, -1060, 1000):
            ones = [[math.ldexp(1.0, e)] * n for _ in range(n)]
            out.append(('ties', 'ties ones %dx%d e=%d' % (n, n, e), n, n, B(ones), 'lams',
                        [Fraction(n * n) * Fraction(2) ** (2 * e)] + [Fraction(0)] * (n - 1)))
            JI = [[(0.0 if i == j else math.ldexp(1.0, e)) for j in range(n)] for i in range(n)]
            # J - I: eigen n-1 (once), -1 (n-1 times) -> sigma n-1, 1 x (n-1)
            out.append(('ties', 'ties J-I %dx%d e=%d' % (n, n, e), n, n, B(JI), 'lams',
                        [Fraction((n - 1) ** 2) * Fraction(2) ** (2 * e)] + [Fraction(2) ** (2 * e)] * (n - 1)))
        # circulant of (1, 2, 3, ...) and magic-ish
        cir = [[float((j - i) % n + 1) for j in range(n)] for i in range(n)]
        out.append(('ties', 'ties circ %dx%d' % (n, n), n, n, B(cir), 'generic', None))
        sym = [[float(min(i, j) + 1) for j in range(n)] for i in range(n)]
        out.append(('ties', 'ties minij %dx%d' % (n, n), n, n, B(sym), 'generic', None))
    for n in (4, 6, 8):
        # magic squares (even: rank deficient)
        M = magic(n)
        out.append(('ties', 'ties magic %d' % n, n, n, B([[float(x) for x in r] for r in M]), 'generic', None))
    # 3-4-5 rotations exactly representable after scaling? 0.6, 0.8 are not exact; use rounded
    for k in range(12):
        n = rng.choice([2, 3, 4])
        Q = C._householder_Q(rng, n, n)
        A = [[float(Q[i][j]) for j in range(n)] for i in range(n)]
        A = A + [[0.0] * n]
        out.append(('ties', 'ties orth+zero %dx%d #%d' % (n + 1, n, k), n + 1, n, B(A), 'generic', None))


def magic(n):
    if n % 4 == 0:
        M = [[n * i + j + 1 for j in range(n)] for i in range(n)]
        for i in range(n):
            for j in range(n):
                if (i % 4 in (0, 3)) == (j % 4 in (0, 3)):
                    M[i][j] = n * n + 1 - M[i][j]
        return M
    # singly even via LUX-free simple method: Strachey
    h = n // 2
    sub = magic_odd(h)
    M = [[0] * n for _ in range(n)]
    for i in range(h):
        for j in range(h):
            M[i][j] = sub[i][j]
            M[i + h][j + h] = sub[i][j] + h * h
            M[i][j + h] = sub[i][j] + 2 * h * h
            M[i + h][j] = sub[i][j] + 3 * h * h
    k = (n - 2) // 4
    for i in range(h):
        for j in range(n):
            swap = (j < k) or (j >= n - k + 1)
            if i == h // 2:
                swap = (k <= j < 2 * k) or (j >= n - k + 1)
            if swap:
                M[i][j], M[i + h][j] = M[i + h][j], M[i][j]
    return M


def magic_odd(n):
    M = [[0] * n for _ in range(n)]
    i, j = 0, n // 2
    for k in range(1, n * n + 1):
        M[i][j] = k
        i2, j2 = (i - 1) % n, (j + 1) % n
        if M[i2][j2]:
            i2, j2 = (i + 1) % n, j
        i, j = i2, j2
    return M


def fam_illcond(rng, out):
    for n in (6, 8, 10, 12, 14):
        H = [[1.0 / (i + j + 1) for j in range(n)] for i in range(n)]
        out.append(('illcond', 'hilbert %d' % n, n, n, B(H), 'generic', None))
    for n in (8, 12, 16, 20):
        xs = [i / (n - 1) for i in range(n)]
        V = [[x ** j for j in range(n)] for x in xs]
        out.append(('illcond', 'vander01 %d' % n, n, n, B(V), 'generic', None))
        V2 = [[x ** j for j in range(n // 2)] for x in xs]
        out.append(('illcond', 'vander01 tall %dx%d' % (n, n // 2), n, n // 2, B(V2), 'generic', None))


def fam_shiftdown(rng, out):
    """A's max near DBL_MAX: the working copy is scaled DOWN, so blocks near 2^-1022 become
    subnormal there while their sigma is still normal (the known 'few bits' case)."""
    for (m_extra, nsmall, ebig, esmall) in [(0, 2, 1022, -1021), (0, 2, 1023, -1020), (12, 2, 1023, -1021),
                                            (60, 2, 1023, -1021), (252, 2, 1023, -1021),
                                            (1020, 2, 1023, -1021), (4092, 2, 1023, -1021),
                                            (60, 3, 1023, -1018), (252, 3, 1023, -1016),
                                            (0, 1, 1023, -1021), (60, 1, 1023, -1021)]:
        for rep in range(3):
            nb = 2
            Bb = [[rfull(rng, ebig - 1, ebig) for _ in range(nb)] for _ in range(nb)]
            Bs = [[rfull(rng, esmall - 1, esmall) for _ in range(nsmall)] for _ in range(nsmall)]
            n = nb + nsmall
            m = n + m_extra
            A = [[0.0] * n for _ in range(m)]
            for i in range(nb):
                for j in range(nb):
                    A[i][j] = Bb[i][j]
            for i in range(nsmall):
                for j in range(nsmall):
                    A[nb + i][nb + j] = Bs[i][j]
            A2 = perm_rows_cols(rng, A[:n])
            A = A2 + A[n:]
            out.append(('shiftdown', 'shiftdown %dx%d small=%d esmall=%d #%d' % (m, n, nsmall, esmall, rep), m, n,
                        B(A), 'blocks', [(nb, nb, B(Bb)), (nsmall, nsmall, B(Bs))]))
    # n <= 3 version: 3x3 with one big 2x2 and a normal-but-tiny 1x1 (pure scaling)
    for rep in range(6):
        Bb = [[rfull(rng, 1022, 1023) for _ in range(2)] for _ in range(2)]
        t = rfull(rng, -1022, -1015)
        A = [[Bb[0][0], Bb[0][1], 0.0], [Bb[1][0], Bb[1][1], 0.0], [0.0, 0.0, t]]
        out.append(('shiftdown', 'shiftdown 3x3 tiny #%d' % rep, 3, 3, B(A), 'blocks',
                    [(2, 2, B(Bb)), (1, 1, [bits_of(t)])]))


def fam_mixedrange(rng, out):
    """Dense matrices whose entries are drawn from the whole range (log-uniform), small n."""
    for n in (2, 3, 4, 5, 6):
        for mm in (n, n + 1, 2 * n):
            for rep in range(12):
                A = [[rfull(rng, -1074, 1023, zero_p=0.1) for _ in range(n)] for _ in range(mm)]
                out.append(('mixedrange', 'mixedrange %dx%d #%d' % (mm, n, rep), mm, n, B(A), 'generic', None))


def fam_randtall(rng, out):
    for (m, n) in ((500, 8), (2000, 12), (4096, 16), (300, 30)):
        for rep in range(2):
            A = [[rfull(rng, -3, 0) for _ in range(n)] for _ in range(m)]
            out.append(('randtall', 'randtall %dx%d #%d' % (m, n, rep), m, n, B(A), 'gram', None))


FAMS = {
    'blockdiag': fam_blockdiag, 'hadamard': fam_hadamard, 'sperm': fam_signedperm, 'tall': fam_tall,
    'dblmax': fam_dblmax, 'allsub': fam_allsub, 'checker': fam_checker, 'tri': fam_tri, 'kahan': fam_kahan,
    'ties': fam_ties, 'illcond': fam_illcond, 'shiftdown': fam_shiftdown, 'mixedrange': fam_mixedrange,
    'randtall': fam_randtall,
}


def main():
    ap = argparse.ArgumentParser(description='Build a hunt set with an exact oracle.')
    ap.add_argument('--out', required=True, metavar='DIR',
                    help="output directory; without a '/' a name under $SVDH_WORK/hunts")
    ap.add_argument('--set', required=True, metavar='F1,F2,...',
                    help='families: ' + ','.join(sorted(FAMS)))
    ap.add_argument('--procs', type=C.procs_arg, default=os.cpu_count() or 1, metavar='N',
                    help='oracle processes (default: every CPU)')
    ap.add_argument('--seed', type=int, default=20261004)
    a = ap.parse_args()
    if '/' not in a.out:
        a.out = os.path.join(C.WORK, 'hunts', a.out)
    names = a.set.split(',')
    unknown = [name for name in names if name not in FAMS]
    if unknown:
        ap.error('unknown family %s; known: %s' % (','.join(unknown), ','.join(FAMS)))
    twice = sorted({name for name in names if names.count(name) > 1})
    if twice:
        ap.error('family %s given twice' % ','.join(twice))
    C.check_versions()
    C.blas_setup()
    C.make_outdir('gen.py', a.out)
    C.term_as_exit()
    try:
        _build(a)
    except BaseException:
        C.discard_tmp(a.out)
        raise


def _build(a):
    items = []
    for name in a.set.split(','):
        rng = random.Random(a.seed + sum(map(ord, name)))
        FAMS[name](rng, items)
    N = len(items)
    print('items: %d' % N, flush=True)
    with open(C.tmp_path(a.out, 'corpus.bin'), 'wb') as fh:
        fh.write(struct.pack('<Q', N))
        for (cls, lab, m, n, bl, kind, pay) in items:
            assert len(bl) == m * n and m >= n >= 1, lab
            fh.write(struct.pack('<QQ', m, n))
            fh.write(struct.pack('<%dQ' % len(bl), *bl))
    meta = [{'id': k, 'class': it[0], 'label': it[1], 'rows': it[2], 'cols': it[3]} for k, it in enumerate(items)]
    with open(C.tmp_path(a.out, 'corpus_meta.json'), 'w') as fh:
        json.dump(meta, fh)
    jobs = [(k, it[5], it[6], it[2], it[3], it[4], it[1]) for k, it in enumerate(items)]
    jobs.sort(key=lambda j: -(j[3] * j[4] ** 2))
    orc = [None] * N
    t0 = time.time()
    with mproc.Pool(a.procs) as pool:
        for k, r in pool.imap_unordered(run_oracle, jobs, chunksize=1):
            orc[k] = r
    print('oracle %.1fs' % (time.time() - t0), flush=True)
    outm = []
    for k, r in enumerate(orc):
        outm.append({'id': k, 'reject': False, 'sigma_bits': ['%016x' % b for b in r['bits']],
                     'hp': [list(x) for x in r['hp']], 'rel_ok': r['rel_ok'], 'rank': r['rank'],
                     'method': r['method'], 'prec': r['prec']})
    nrel = sum(1 for r in orc for x in r['rel_ok'] if not x)
    with open(C.tmp_path(a.out, 'oracle.json'), 'w') as fh:
        json.dump({'info': {'count': N, 'uncertified_sigma': nrel}, 'matrices': outm}, fh)
    C.publish(a.out)
    print('uncertified sigma: %d' % nrel)


def fam_boundary(rng, out):
    """sigma_1 within a few ulps of DBL_MAX (and of the overflow threshold DBL_MAX + ulp/2)."""
    import numpy as np
    thr = Fraction(DBL_MAX) + Fraction(2) ** 970      # DBL_MAX + half ulp: rounding threshold
    for k in range(600):
        n = rng.choice([1, 2, 2, 3, 4, 5])
        m = n + rng.choice([0, 0, 1, 3])
        Bm = np.array([[rng.gauss(0, 1) for _ in range(n)] for _ in range(m)])
        s1 = np.linalg.svd(Bm, compute_uv=False)[0]
        delta = rng.uniform(-2.0 ** -49, 2.0 ** -49)
        # target sigma_1 = thr*(1+delta); entries = B * (thr/s1)*(1+delta) rounded
        fac = Fraction(thr) / Fraction(float(s1)) * (1 + Fraction(delta))
        A = []
        ok = True
        for i in range(m):
            row = []
            for j in range(n):
                f = Fraction(float(Bm[i, j])) * fac
                if abs(f) > Fraction(DBL_MAX):
                    ok = False
                    break
                row.append(float(f))
            A.append(row)
            if not ok:
                break
        if not ok:
            continue
        out.append(('boundary', 'boundary %dx%d #%d' % (m, n, k), m, n, B(A), 'generic', None))


FAMS['boundary'] = fam_boundary


if __name__ == '__main__':
    main()
