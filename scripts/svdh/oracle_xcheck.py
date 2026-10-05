#!/usr/bin/env python3
"""Independent cross-check of the oracle on 492 matrices with n >= 3.

usage: oracle_xcheck.py [--dir DIR] [--procs N]
Reads corpus.bin, corpus_meta.json and oracle.json from DIR (default $SVDH_WORK, else
<repo>/build/svdh; corpus.py writes them; check.py's loaders check that they belong together)
and recomputes sampled entries by other routes than corpus.py's (Bareiss elimination for the
rank, mpmath.svd_r for the sigma):
  - the exact rank r, by Gaussian elimination of the integer-scaled matrix modulo the primes
    2^61-1, 2^89-1 and 2^107-1 (the largest of the three ranks, each a lower bound that is exact
    unless the prime divides every r x r minor), which must equal the oracle's rank;
  - the eigenvalues of the EXACT Gram matrix (mpmath.eigsy at P = 2*log2(sigma_1/sigma_r) + 200
    bits): the n - r smallest must lie within 2^(-P+20)*sigma_1^2 of 0, the r-th must be more
    than 2^64 times that, and the square roots of the r largest, each rounded once, must be the
    oracle's sigma, bit for bit (the other n - r are 0).
The sample is up to 60 matrices of each of sqdef, talldef, outer, randwell, graded, extreme,
rankdef and cluster, and the witnesses with n >= 3 (random.Random(7)).
Exits with status 1 when any entry disagrees, and 2 on a usage or input error (a missing file,
or files that do not belong together).
"""
import argparse
import math
import multiprocessing as mproc
import os
import random
import sys
from fractions import Fraction

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import corpus as C   # noqa: E402  (exits with a message when mpmath or numpy is missing)
import check as CK   # noqa: E402
import mpmath        # noqa: E402

CLASSES = ('sqdef', 'talldef', 'outer', 'randwell', 'graded', 'extreme', 'rankdef', 'cluster', 'wit')
PRIMES = ((1 << 61) - 1, (1 << 89) - 1, (1 << 107) - 1)     # Mersenne primes
_D = {}


def load(d):
    """(oracle, meta, corpus words, data offsets) of the set in d; exits with status 2 when a file
    is missing or malformed, or the three do not belong together."""
    for f in C.SET_FILES:
        if not os.path.isfile(os.path.join(d, f)):
            C.input_error('oracle_xcheck.py: %s not found: run corpus.py first' % os.path.join(d, f))
    w, crow, ccol, coff = CK.load_corpus(os.path.join(d, 'corpus.bin'))
    meta = CK.load_meta(os.path.join(d, 'corpus_meta.json'), crow, ccol)
    orc = CK.Oracle(os.path.join(d, 'oracle.json'), len(crow), meta)
    orc.fit(w, crow, ccol, coff)
    return orc, meta, w, coff


def _init(d):
    _D['orc'], _D['meta'], _D['w'], _D['offs'] = load(d)


def rank_mod(M, p):
    """Rank over GF(p) of the integer matrix M (a list of rows), by Gaussian elimination."""
    A = [[x % p for x in row] for row in M]
    m, n = len(A), len(A[0])
    r = 0
    for c in range(n):
        piv = next((i for i in range(r, m) if A[i][c]), None)
        if piv is None:
            continue
        A[r], A[piv] = A[piv], A[r]
        inv = pow(A[r][c], -1, p)
        for i in range(r + 1, m):
            if A[i][c]:
                f = A[i][c] * inv % p
                A[i] = [(a - f * b) % p for a, b in zip(A[i], A[r])]
        r += 1
        if r == m:
            break
    return r


def exact_rank(F, m, n):
    """The rank over Q of the m x n matrix of dyadic Fractions F (row major): every entry times
    2^K is an integer, and the rank modulo a prime is at most the rank over Q."""
    K = max((x.denominator.bit_length() - 1 for x in F if x != 0), default=0)
    M = [[int(F[i * n + j] * (1 << K)) for j in range(n)] for i in range(m)]
    return max(rank_mod(M, p) for p in PRIMES)


def job(k):
    orc, meta, w, offs = _D['orc'], _D['meta'], _D['w'], _D['offs']
    m, n = meta[k]['rows'], meta[k]['cols']
    F = [Fraction(C.f_of(int(b))) for b in w[offs[k]:offs[k] + m * n]]
    bits = [int(x) for x in orc.bits[k]]
    why = []
    r = exact_rank(F, m, n)
    if r != orc.rank[k]:
        why.append('rank %d, the oracle %d' % (r, orc.rank[k]))
    if r == 0:
        return k, why or ([] if bits == [0] * n else ['sigma']), 0
    G = [[sum(F[i * n + a] * F[i * n + b] for i in range(m)) for b in range(n)] for a in range(n)]
    s = [C.f_of(b) for b in bits]
    lr = (math.log2(s[0]) - math.log2(s[r - 1])) if s[r - 1] > 0 else 1100.0
    P = int(2 * max(lr, 0.0) + 200)
    mpmath.mp.prec = P
    Gm = mpmath.matrix(n, n)
    for a in range(n):
        for b in range(n):
            Gm[a, b] = mpmath.mpf(G[a][b].numerator) / G[a][b].denominator
    ev = mpmath.eigsy(Gm, eigvals_only=True)
    ev = sorted([ev[i] for i in range(n)], reverse=True)
    tiny = ev[0] * mpmath.mpf(2) ** (-P + 20)
    if any(abs(ev[i]) > tiny for i in range(r, n)):
        why.append('an eigenvalue past the rank is not 0')
    if not ev[r - 1] > tiny * mpmath.mpf(2) ** 64:
        why.append('eigenvalue %d is not clearly above 0' % r)
    got = [C.round_frac_bits(C.mpf_to_frac(mpmath.sqrt(ev[i]))) if i < r else 0 for i in range(n)]
    if got != bits:
        why.append('sigma')
    return k, why, P


def main():
    ap = argparse.ArgumentParser(description='Recompute 492 oracle entries (n >= 3): the rank modulo '
                                 'three primes, the sigma by eigsy of the exact Gram matrix.')
    ap.add_argument('--dir', default=C.WORK, metavar='DIR',
                    help='the set to check (default $SVDH_WORK, else <repo>/build/svdh)')
    ap.add_argument('--procs', type=C.procs_arg, default=os.cpu_count() or 1, metavar='N',
                    help='processes (default: every CPU)')
    a = ap.parse_args()
    C.check_versions()
    orc, meta, _, _ = load(a.dir)
    rng = random.Random(7)
    pick = []
    for c in CLASSES:
        ids = [k for k in range(len(meta))
               if meta[k]['class'] == c and meta[k]['cols'] >= 3 and not orc.reject[k]]
        pick += rng.sample(ids, min(len(ids), 60))
    if not pick:
        C.input_error('oracle_xcheck.py: no matrix with n >= 3 of the classes %s in %s'
                      % (','.join(CLASSES), a.dir))
    with mproc.Pool(a.procs, initializer=_init, initargs=(a.dir,)) as pool:
        res = pool.map(job, pick, chunksize=2)
    bad = [(k, meta[k]['label'], why) for k, why, P in res if why]
    print('independent cross-check (rank modulo 3 primes, eigsy of the exact Gram matrix): %d matrices '
          '(n>=3), %d disagree; max prec %d' % (len(res), len(bad), max(P for _, _, P in res)))
    for b in bad[:20]:
        print('   id %d %s: %s' % (b[0], b[1], '; '.join(b[2])))
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
