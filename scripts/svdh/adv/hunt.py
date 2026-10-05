#!/usr/bin/env python3
"""Oracle-free hunt for non-convergence (-3/-1) and gross failures of one or more trees.

usage: hunt.py SEED COUNT --labels L1[,L2...] [--fam name,...]
Generates COUNT matrices from the families below (seeded), runs each tree's driver
($SVDH_WORK/build/drv_<L>, from build.sh; an aarch64 one runs under qemu-aarch64), and reports
status != 0 and, for status 0, U / Vt orthonormality, reconstruction and sigma against numpy
(normwise, with numpy's own error as slack).  Hits are appended to
$SVDH_WORK/hunt_hits/seed<SEED>.json (bits), so gen.py's `cycle` class picks them up for the
oracle corpus with --hits $SVDH_WORK/hunt_hits; that file keeps the hits of every earlier hunt of
the seed, of every label.  hunt.py reads it again and adds its hits under a lock on that
directory, so hunts of the same seed that run at the same time keep each other's hits.  Scratch
files go to $SVDH_WORK/hunt, named by process id, and are removed at the end, also when hunt.py
fails or is stopped by SIGINT or SIGTERM, which stop the running driver too.  The matrices of
tall2 and eqn and the numpy sigma go through numpy's BLAS and LAPACK (corpus.blas_setup).

A driver that exits non-zero or writes other output than the matrices' records is reported as
'DRIVER FAILED' with the number of matrices it completed, and hunt.py exits with status 1; the
first matrix from there on that makes it fail on its own is saved as a hit (only the first matrix
is tried when every record was written: the failure is then at the driver's exit or past the
records).  A label must be usable in file names (README.md), and a missing driver, a malformed
hit file or a hit directory it cannot write stops hunt.py with status 2.
"""
import argparse
import fcntl
import json
import math
import os
import random
import shlex
import struct
import subprocess
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import corpus as C   # noqa: E402
import check as CK   # noqa: E402

WORK = C.WORK

LD = np.longdouble
U = 2.0 ** -52


def rf(rng, lo, hi):
    return C.rfull(rng, lo, hi)


def fam_cyc(rng):
    """W54-like: small dense, moderate exponent spread, then a random overall power of two."""
    m, n = rng.choice([(5, 4), (8, 6), (4, 4), (6, 5), (7, 3), (12, 8)])
    A = np.array([[rf(rng, -8, 4) if rng.random() > 0.05 else 0.0 for _ in range(n)] for _ in range(m)])
    k = rng.choice([0, 0, rng.randint(-1000, 1000)])
    return 'cyc %dx%d k=%d' % (m, n, k), np.ldexp(A, k) if abs(k) < 900 else _ldexp_exact(A, k)


def _ldexp_exact(A, k):
    from fractions import Fraction
    out = np.empty_like(A)
    for idx, x in np.ndenumerate(A):
        out[idx] = (C.f_of(C.round_frac_bits(abs(Fraction(float(x)) * Fraction(2) ** k))) * (1 if x > 0 else -1)
                    if x != 0 else 0.0)
    return out


def fam_int(rng):
    """Small-integer matrices: exact ties, exact cancellations, rank deficiency."""
    n = rng.randint(3, 10)
    m = n + rng.choice([0, 0, 1, 3])
    A = np.array([[float(rng.randint(-2, 2)) for _ in range(n)] for _ in range(m)])
    return 'int %dx%d' % (m, n), A


def fam_tall2(rng):
    """Tall n = 2 with rounding-heavy dot products (sign-sorted products), near-orthogonal."""
    m = rng.choice([50, 100, 300, 1000, 3000])
    x = np.array([rf(rng, -1, 0) for _ in range(m)])
    x = np.abs(x)
    y = np.array([rf(rng, -1, 0) for _ in range(m)])
    y = np.abs(y)
    h = m // 2
    y[h:] = -y[h:]
    # make exactly-ish orthogonal: scale the negative half
    p = float(x[:h] @ y[:h])
    q = float(-(x[h:] @ y[h:]))
    y[h:] *= p / q
    k = rng.choice([0, rng.randint(-1000, 1000)])
    A = np.stack([x, y], axis=1)
    return 'tall2 %dx2 k=%d' % (m, k), np.ldexp(A, k) if abs(k) < 900 else _ldexp_exact(A, k)


def fam_full(rng):
    """Entries over the whole double range, subnormals included."""
    n = rng.randint(2, 10)
    m = n + rng.choice([0, 0, 1, 2, 5])

    def fr():
        if rng.random() < 0.1:
            return 0.0
        e = rng.randint(-1074, 1023)
        if e < -1022:
            v = float(rng.randrange(1, 1 << (e + 1075))) * 2.0 ** -1074
        else:
            v = C.mkf(rng.getrandbits(52), e)
        return -v if rng.getrandbits(1) else v
    A = np.array([[fr() for _ in range(n)] for _ in range(m)])
    return 'full %dx%d' % (m, n), A


def fam_def(rng):
    """Square/tall with zero rows, repeated rows, duplicated columns, random power-of-two scale."""
    n = rng.randint(3, 14)
    m = n + rng.choice([0, 0, 0, 1])
    A = np.array([[rf(rng, -3, 0) for _ in range(n)] for _ in range(m)])
    for _ in range(rng.randint(1, max(1, n // 3))):
        kind = rng.random()
        i, j = rng.randrange(m), rng.randrange(m)
        if kind < 0.4:
            A[i] = 0
        elif kind < 0.8:
            A[i] = A[j] * rng.choice([1.0, -1.0, 2.0, 0.5])
        else:
            c1, c2 = rng.randrange(n), rng.randrange(n)
            A[:, c1] = A[:, c2] * rng.choice([1.0, -1.0, 2.0 ** rng.randint(-40, 40)])
    k = rng.choice([0, rng.randint(-1060, 1000)])
    return 'def %dx%d k=%d' % (m, n, k), np.ldexp(A, k) if -1000 < k < 900 else _ldexp_exact(A, k)


def fam_grad(rng):
    """Row / column / both graded random, spans up to 2000 binades."""
    n = rng.randint(2, 12)
    m = n + rng.choice([0, 0, 1, 4])
    A = np.array([[rf(rng, -1, 0) for _ in range(n)] for _ in range(m)])
    span = rng.choice([100, 500, 600, 1000, 1500, 2000])
    top = rng.randint(-1000 + span, 1000) if span <= 2000 else 0
    top = min(top, 1000)
    g = rng.choice(['row', 'col', 'both'])
    if g in ('row', 'both'):
        e = np.array([top - rng.randint(0, span) for _ in range(m)])
        A = A * np.ldexp(1.0, e)[:, None] if True else A
    if g in ('col', 'both'):
        e2 = np.array([-rng.randint(0, span // (2 if g == 'both' else 1)) for _ in range(n)])
        A = _ldexp_cols(A, e2)
    return 'grad %s %dx%d span=%d' % (g, m, n, span), A


def _ldexp_cols(A, e2):
    out = A.copy()
    for j in range(A.shape[1]):
        col = A[:, j]
        if np.all((np.abs(col) == 0) | (np.abs(np.ldexp(col, int(e2[j]))) >= 2.0 ** -1022)):
            out[:, j] = np.ldexp(col, int(e2[j]))
        else:
            out[:, j] = _ldexp_exact(col[:, None], int(e2[j]))[:, 0]
    return out


def fam_nearpar(rng):
    """A tiny column nearly parallel to a big one, inside a random matrix."""
    n = rng.randint(2, 6)
    m = n + rng.choice([0, 1, 3])
    A = np.array([[rf(rng, -1, 0) for _ in range(n)] for _ in range(m)])
    j = rng.randrange(1, n)
    d = rng.randint(5, 52)
    eps = rng.randint(0, 1000)
    col = A[:, 0] + np.ldexp(np.array([rf(rng, -1, 0) for _ in range(m)]), -d)
    A[:, j] = np.ldexp(col, -eps)
    return 'nearpar %dx%d d=%d eps=%d' % (m, n, d, eps), A


def fam_hadp(rng):
    """Hadamard-like: exactly or nearly orthogonal equal-norm columns, 1-ulp perturbations, random
    exact column scalings by 2^0 or 2^-1 (ties and near ties), random overall scale."""
    n = rng.choice([2, 4, 8, 16, 32])
    m = n * rng.choice([1, 1, 2])
    H = np.array([[1.0]])
    while H.shape[0] < m:
        H = np.block([[H, H], [H, -H]])
    H = H[:, rng.sample(range(m), n)] * rng.choice([1.0, 3.0, 0.7])
    for _ in range(rng.randint(0, 4)):
        i, j = rng.randrange(m), rng.randrange(n)
        H[i, j] = np.nextafter(H[i, j], np.inf if rng.getrandbits(1) else -np.inf)
    if rng.random() < 0.3:
        H[:, rng.randrange(n)] *= 0.5
    k = rng.choice([0, rng.randint(-1000, 1000)])
    return 'hadp %dx%d k=%d' % (m, n, k), np.ldexp(H, k) if -1000 < k < 900 else _ldexp_exact(H, k)


def fam_eqn(rng):
    """Tall, equal-norm columns with cosines of a few u (rotations near 45 degrees)."""
    n = rng.choice([2, 3, 4])
    m = rng.choice([4, 8, 30, 100, 500, 2000])
    Q, _ = np.linalg.qr(np.array([[rf(rng, -1, 0) for _ in range(n)] for _ in range(m)]))
    E = np.array([[rf(rng, -1, 0) for _ in range(n)] for _ in range(m)]) * (rng.randint(0, 64) * 2.0 ** -52)
    A = Q + E
    k = rng.choice([0, rng.randint(-1000, 1000)])
    return 'eqn %dx%d k=%d' % (m, n, k), np.ldexp(A, k) if -1000 < k < 900 else _ldexp_exact(A, k)


def fam_subrow(rng):
    """One or two normal rows over subnormal rows (small-integer mantissas): row grading into
    the subnormal range, where rotations meet underflow and a sweep budget can run out."""
    n = rng.randint(2, 6)
    m = n + rng.choice([0, 0, 1, 2])
    A = np.zeros((m, n))
    nn = rng.choice([1, 1, 2])
    for i in range(m):
        if i < nn:
            A[i] = [rf(rng, -2, 1) for _ in range(n)]
        else:
            b = rng.randint(1, 40)
            A[i] = [float(rng.randrange(0, 1 << b) * (1 if rng.getrandbits(1) else -1)) * 2.0 ** -1074
                    for _ in range(n)]
    A = A[rng.sample(range(m), m)]
    k = rng.choice([0, 0, rng.randint(0, 1000)])
    return 'subrow %dx%d k=%d' % (m, n, k), np.ldexp(A, k)


FAMS = {'cyc': fam_cyc, 'int': fam_int, 'tall2': fam_tall2, 'full': fam_full, 'def': fam_def,
        'grad': fam_grad, 'nearpar': fam_nearpar, 'hadp': fam_hadp, 'eqn': fam_eqn, 'subrow': fam_subrow}


def record_words(mats):
    """Words of each matrix's record in a driver's output."""
    return [2 + 2 * A.shape[1] + A.shape[0] * A.shape[1] + A.shape[1] ** 2 for _, A in mats]


def write_corpus(path, mats):
    with open(path, 'wb') as fh:
        fh.write(struct.pack('<Q', len(mats)))
        for lab, A in mats:
            fh.write(struct.pack('<QQ', *A.shape))
            fh.write(A.astype('<f8').tobytes())


def run_driver(drv, path, tpath):
    """Run drv on the corpus at path, times to tpath (fd 3).  (returncode, out words, stderr,
    bytes written: the words leave out a partial word at the end, which only the byte count shows).
    The shell execs the driver (or qemu-aarch64), so that the process subprocess.run kills when
    hunt.py is interrupted or terminated is the driver itself, not a shell that would leave it
    running."""
    cmd = 'exec ' + ' '.join(shlex.quote(x) for x in CK.runner_for(drv) + [drv]) + ' 3>' + shlex.quote(tpath)
    with open(path, 'rb') as fi:
        p = subprocess.run(cmd, shell=True, stdin=fi, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    out = p.stdout[:len(p.stdout) // 8 * 8]
    return (p.returncode, np.frombuffer(out, dtype='<u8'), p.stderr.decode(errors='replace').strip(),
            len(p.stdout))


def first_failing(drv, mats, k0, wd):
    """The first matrix from k0 on that makes drv fail when run on its own: (its index, why), why
    being 'driver exit N', or 'driver output B bytes, E expected' when it exits 0; (None, None)
    when none does."""
    path = os.path.join(wd, 'one_%d.bin' % os.getpid())
    try:
        for j in range(k0, len(mats)):
            write_corpus(path, [mats[j]])
            rc, _, _, nbytes = run_driver(drv, path, os.devnull)
            want = 8 * record_words([mats[j]])[0]
            if rc != 0:
                return j, 'driver exit %d' % rc
            if nbytes != want:
                return j, 'driver output %d bytes, %d expected' % (nbytes, want)
    finally:
        if os.path.exists(path):
            os.remove(path)
    return None, None


def check_hit_file(hp):
    """Exit with status 2 when the hit file hp exists and is not a list of hits."""
    if os.path.exists(hp):
        try:
            C.load_hits(hp)
        except ValueError as e:
            C.input_error('hunt.py: %s (remove or fix it; hunt.py adds its hits to it)' % e)


def hit_dir(hp):
    """Create the directory of the hit file hp, or exit with status 2 when it cannot be created or
    written."""
    d = os.path.dirname(hp)
    C.make_outdir('hunt.py', d)
    if not os.access(d, os.W_OK | os.X_OK):
        C.input_error('hunt.py: cannot write to the hit directory %s' % d)


def merge_hits(hp, hits):
    """Add hits (by label) to the hit file hp.  Under an exclusive lock on its directory the file
    is read again, so that a hunt of the same seed that ran at the same time keeps its hits, then
    written under a temporary name of this process and renamed.  Exits with status 2 when that
    cannot be done."""
    hit_dir(hp)
    tmp = '%s.%d.tmp' % (hp, os.getpid())
    fd = None
    try:
        fd = os.open(os.path.dirname(hp), os.O_RDONLY)
        fcntl.flock(fd, fcntl.LOCK_EX)
        old = C.read_hits(hp) if os.path.exists(hp) else []
        seen = set(h['label'] for h in old)
        old += [h for h in hits if h['label'] not in seen]
        with open(tmp, 'w') as fh:      # renamed into place: never a half-written hit file
            json.dump(old, fh)
        os.replace(tmp, hp)
    except ValueError as e:
        C.input_error('hunt.py: %s (remove or fix it; hunt.py adds its hits to it)' % e)
    except OSError as e:
        C.input_error('hunt.py: cannot write the hits to %s: %s' % (
            hp, '%s (%s)' % (e.strerror, e.filename) if e.filename and e.strerror else e))
    finally:
        if os.path.isfile(tmp):
            os.remove(tmp)
        if fd is not None:
            os.close(fd)                # and with it the lock


def main():
    ap = argparse.ArgumentParser(description='Oracle-free SVD hunt over seeded matrix families.')
    ap.add_argument('seed', type=int, metavar='SEED')
    ap.add_argument('count', type=C.procs_arg, metavar='COUNT', help='matrices to draw (at least 1)')
    ap.add_argument('--labels', required=True, metavar='L1[,L2...]',
                    help='trees: $SVDH_WORK/build/drv_<L> from build.sh')
    ap.add_argument('--fam', metavar='F1[,F2...]', help='families (default all): ' + ','.join(FAMS))
    a = ap.parse_args()
    seed, count = a.seed, a.count
    labels = [L for L in a.labels.split(',') if L]
    if not labels:
        ap.error('--labels names no tree')
    if len(set(labels)) != len(labels):
        ap.error('--labels names a tree more than once')
    for L in labels:
        CK.check_label(L)
        if not os.access(os.path.join(WORK, 'build', 'drv_%s' % L), os.X_OK):
            how = ('%s <tree> aarch64' % L[:-4]) if L.endswith('_a64') else '%s [<tree>]' % L
            C.input_error('hunt.py: %s missing: run scripts/svdh/adv/build.sh %s first'
                          % (os.path.join(WORK, 'build', 'drv_%s' % L), how))
    fams = list(FAMS)
    if a.fam is not None:
        fams = a.fam.split(',')
        unknown = [f for f in fams if f not in FAMS]
        if unknown:
            ap.error('unknown famil%s %s; known: %s' % ('y' if len(unknown) == 1 else 'ies',
                                                        ','.join(unknown), ','.join(FAMS)))
    CK.require_longdouble()
    C.check_versions()
    C.blas_setup()
    C.term_as_exit()
    hp = os.path.join(WORK, 'hunt_hits', 'seed%d.json' % seed)
    hit_dir(hp)                        # fail now, not after the drivers ran
    check_hit_file(hp)
    rng = random.Random(seed)
    mats = []
    for k in range(count):
        f = fams[k % len(fams)]
        lab, A = FAMS[f](rng)
        A = np.asarray(A, dtype=np.float64)
        if not np.all(np.isfinite(A)):
            continue
        mats.append((lab, A))
    wd = os.path.join(WORK, 'hunt')
    C.make_outdir('hunt.py', wd)
    path = os.path.join(wd, 'h%d.%d.bin' % (seed, os.getpid()))
    # The scratch corpus and the drivers' times go, whatever happens (merge_hits removes its own).
    scratch = [path] + [path + '.' + L + '.t' for L in labels]
    try:
        try:
            write_corpus(path, mats)
        except OSError as e:
            C.input_error('hunt.py: cannot write the scratch corpus %s: %s' % (path, e.strerror or e))
        sizes = record_words(mats)
        hits = []
        t0 = time.time()
        res = {}
        done = {}          # matrices whose records a tree's driver wrote in full
        failed = {}        # L -> (exit status, k0, bytes written, matrix failing alone, its why, stderr)
        for L in labels:
            drv = os.path.join(WORK, 'build', 'drv_%s' % L)
            tpath = path + '.' + L + '.t'
            rc, w, err, nbytes = run_driver(drv, path, tpath)
            t = np.fromfile(tpath, dtype='<i8') if os.path.exists(tpath) else np.zeros(0, '<i8')
            res[L] = (w, t)
            k0, o = 0, 0
            while k0 < len(mats) and o + sizes[k0] <= len(w):
                o += sizes[k0]
                k0 += 1
            done[L] = k0
            if rc != 0 or nbytes != 8 * sum(sizes):
                if k0 < len(mats):
                    j, whyj = first_failing(drv, mats, k0, wd)
                else:
                    # Every record written: the failure is at the driver's exit or in output past
                    # the records, which no one matrix is to blame for; try the first one alone.
                    j, whyj = first_failing(drv, mats[:1], 0, wd)
                failed[L] = (rc, k0, nbytes, j, whyj, err)
                if j is not None:
                    lab, A = mats[j]
                    m, n = A.shape
                    why = [whyj]
                    hits.append({'label': '%s seed%d #%d [%s: %s]' % (lab, seed, j, L, '; '.join(why)),
                                 'rows': m, 'cols': n, 'tree': L, 'why': why,
                                 'bits': ['%016x' % b for b in A.reshape(-1).view('<u8')]})
        tdrv = time.time() - t0
        stats = {L: {'st': {}, 'bad': 0, 'tmax': 0} for L in labels}
        offs = {L: 0 for L in labels}
        for k, (lab, A) in enumerate(mats):
            m, n = A.shape
            sz = sizes[k]
            snp = None
            for L in labels:
                if k >= done[L]:
                    continue
                w = res[L][0][offs[L]:offs[L] + sz]
                offs[L] += sz
                st = int(np.int64(w[0]))
                stv = int(np.int64(w[1 + n + m * n + n * n]))
                tt = res[L][1][2 * k] if len(res[L][1]) > 2 * k else 0
                stats[L]['st'][st] = stats[L]['st'].get(st, 0) + 1
                stats[L]['tmax'] = max(stats[L]['tmax'], int(tt))
                why = []
                if st != 0 or stv != st:
                    why.append('status %d / vo %d' % (st, stv))
                else:
                    S = w[1:1 + n].view(np.float64)
                    Uq = w[1 + n:1 + n + m * n].view(np.float64).reshape(m, n)
                    Vt = w[1 + n + m * n:1 + n + m * n + n * n].view(np.float64).reshape(n, n)
                    if snp is None:
                        # numpy sigma on the exactly power-of-two-normalised matrix
                        mx = np.max(np.abs(A))
                        e = math.frexp(mx)[1] if mx > 0 else 0
                        An = np.ldexp(A.astype(LD), -e).astype(np.float64)
                        snp = (np.linalg.svd(An, compute_uv=False), e)
                    sv, e = snp
                    Sl = np.ldexp(S.astype(LD), -e)
                    s1 = LD(sv[0]) if len(sv) else LD(0)
                    den = U * s1 + np.ldexp(LD(1), -1074 - e)
                    nw = float(np.max(np.abs(Sl - sv.astype(LD))) / den) if s1 > 0 else 0.0
                    VL = Vt.astype(LD)
                    vo = float(np.max(np.abs(VL @ VL.T - np.eye(n, dtype=LD))) / U)
                    J = S >= 2.0 ** -1022
                    UL = Uq.astype(LD)
                    uo = (float(np.max(np.abs(UL[:, J].T @ UL[:, J] - np.eye(int(J.sum()), dtype=LD))) / U)
                          if J.any() else 0.0)
                    Al = np.ldexp(A.astype(LD), -e)
                    rec = float(np.max(np.abs(Al - (UL * Sl[None, :]) @ VL)) / den) if s1 > 0 else 0.0
                    mn = m * n
                    if not np.all(np.isfinite(S)):
                        why.append('nonfinite S')
                    if not (np.all(S[:-1] >= S[1:]) and np.all(S >= 0)):
                        why.append('not desc')
                    if nw > 4 * max(1, math.sqrt(mn) / 2) + 8:
                        why.append('nw %.3g' % nw)
                    if uo > 256:
                        why.append('uo %.3g' % uo)
                    if vo > 256:
                        why.append('vo %.3g' % vo)
                    if rec > 16 * max(1, math.sqrt(mn)):
                        why.append('rec %.3g' % rec)
                if why:
                    stats[L]['bad'] += 1
                    hits.append({'label': '%s seed%d #%d [%s: %s]' % (lab, seed, k, L, '; '.join(why)),
                                 'rows': m, 'cols': n, 'tree': L, 'why': why,
                                 'bits': ['%016x' % b for b in A.reshape(-1).view('<u8')]})
        print('seed %d: %d matrices, drivers %.1fs' % (seed, len(mats), tdrv))
        for L in labels:
            if L in failed:
                rc, k0, nbytes, j, whyj, err = failed[L]
                if k0 < len(mats):
                    what = 'exit %d after %d of %d matrices' % (rc, k0, len(mats))
                    alone = 'no matrix from #%d on fails on its own' % k0
                else:
                    what = ('exit %d, %d bytes for the %d bytes of all %d records: the failure is at its exit or '
                            'in output past the records' % (rc, nbytes, 8 * sum(sizes), len(mats)))
                    alone = 'matrix #0 does not fail on its own' if mats else 'there is no matrix to try alone'
                print('  %s: DRIVER FAILED: %s; %s%s' % (
                    L, what, ('matrix #%d fails on its own (%s), saved as a hit' % (j, whyj)) if j is not None
                    else alone, ('; stderr: ' + err[-200:]) if err else ''))
            print('  %s: status %s; flagged %d; max full-call %.1f ms' % (
                L, stats[L]['st'], stats[L]['bad'], stats[L]['tmax'] / 1e6))
        for h in hits[:40]:
            print('   HIT', h['label'][:150])
        merge_hits(hp, hits)
        return 1 if failed else 0
    finally:
        for f in scratch:
            if os.path.isfile(f):
                os.remove(f)


if __name__ == '__main__':
    sys.exit(main())
