"""Oracle-free quick scorer: write a corpus from a python generator, run a driver, report
status, NaN/inf in outputs, vo mismatch, u0col, u_orth (sigma >= 2^-1022), u_all (every sigma
!= 0), vt_orth, recon relative to the RETURNED sigma_1 (+ 2^-1074), and sweeps not available.
A metric that comes out NaN (NaN in U or Vt) is +inf, as in check.py; recon is NaN only where a
returned sigma is not finite, where it is not defined.

usage (as a module): run(items, driver) -> list of dicts
items: list of (label, m, n, bits) with m >= n >= 1 and m*n 64-bit words in bits (a ValueError,
naming the item, otherwise); driver: a binary built from driver.cyr (run.sh builds
$SVDH_WORK/build/driver_<label>; an aarch64 one runs under qemu-aarch64).  Scratch files go to
$SVDH_WORK/scratch and are removed afterwards, also when the driver fails (a RuntimeError).
inst=True reads an instrumented driver's 14 counters per matrix (not carried in the repo).
Run as a script, it prints this text for -h or --help, and otherwise says that it is a module.
"""
import os
import shutil
import struct
import subprocess
import sys
import tempfile

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import check as CK       # noqa: E402
from check import WORK   # noqa: E402

LD = np.longdouble
U = LD(2.0) ** -52
TINY = LD(2.0) ** -1074
POISON = 0x7FF4000000000BAD
V = WORK


def write_corpus(path, items):
    with open(path, 'wb') as fh:
        fh.write(struct.pack('<Q', len(items)))
        for (lab, m, n, bl) in items:
            fh.write(struct.pack('<QQ', m, n))
            fh.write(np.array(bl, dtype='<u8').tobytes())


def _inf_nan(x):
    """x, or +inf where it is NaN (a NaN in the output)."""
    return float('inf') if x != x else x


NAMES = ['sw', 'stop2', 'rot', 't2z', 'below', 'rb', 'rbc', 'flf', 'flc', 'nochg', 'ldx', 'f2', 'vc', 'subz']


def check_items(items):
    """Raise ValueError, naming the item, unless each is (label, m, n, bits) with m >= n >= 1 and
    bits m*n integers in [0, 2^64)."""
    for k, it in enumerate(items):
        try:
            lab, m, n, bl = it
            len(bl)
        except (TypeError, ValueError):
            raise ValueError('quick.run: item %d is not (label, m, n, bits)' % k)
        if not (isinstance(m, (int, np.integer)) and isinstance(n, (int, np.integer)) and m >= n >= 1):
            raise ValueError('quick.run: item %d (%s): need integers m >= n >= 1, got %r x %r' % (k, lab, m, n))
        if len(bl) != m * n:
            raise ValueError('quick.run: item %d (%s): %d bits for a %dx%d matrix' % (k, lab, len(bl), m, n))
        if not all(isinstance(b, (int, np.integer)) and 0 <= b < 1 << 64 for b in bl):
            raise ValueError('quick.run: item %d (%s): a bit pattern is not a 64-bit word' % (k, lab))


def run(items, driver, keep=None, inst=False):
    """Run `driver` on `items`; keep=DIR keeps c.bin / r.bin in DIR instead of a scratch dir."""
    check_items(items)
    CK.require_longdouble()
    if not os.access(driver, os.X_OK):
        raise FileNotFoundError('driver %s not found or not executable' % driver)
    if keep is None:
        os.makedirs(V + '/scratch', exist_ok=True)
    d = tempfile.mkdtemp(dir=V + '/scratch') if keep is None else keep
    try:
        return _run(items, driver, d, inst)
    finally:
        if keep is None:
            shutil.rmtree(d, ignore_errors=True)


def _run(items, driver, d, inst):
    cp = os.path.join(d, 'c.bin')
    rp = os.path.join(d, 'r.bin')
    write_corpus(cp, items)
    with open(cp, 'rb') as fi, open(rp, 'wb') as fo:
        p = subprocess.run(CK.runner_for(driver) + [driver], stdin=fi, stdout=fo, stderr=subprocess.PIPE)
    if p.returncode != 0:
        raise RuntimeError('driver %s exited with status %d: %s'
                           % (driver, p.returncode, p.stderr.decode(errors='replace').strip()[-500:]))
    want = sum(2 + 2 * n + m * n + n * n + (16 if inst else 0) for (lab, m, n, bl) in items)
    size = os.path.getsize(rp)
    if size != 8 * want:
        raise RuntimeError('driver %s wrote %d bytes, expected %d' % (driver, size, 8 * want))
    w = np.fromfile(rp, dtype='<u8')
    p = 0
    out = []
    for (lab, m, n, bl) in items:
        st = int(np.int64(w[p]))
        p += 1
        S = w[p:p + n]
        p += n
        Ub = w[p:p + m * n]
        p += m * n
        Vb = w[p:p + n * n]
        p += n * n
        cnt = {}
        if inst:
            cnt = dict(zip(NAMES, [int(x) for x in w[p:p + 14]]))
            p += 14
        st2 = int(np.int64(w[p]))
        p += 1
        S2 = w[p:p + n]
        p += n
        if inst:
            cnt['vo_sw'] = int(w[p])
            p += 2
        r = {'label': lab, 'm': m, 'n': n, 'st': st, 'st2': st2, 'vo': bool(st == st2 and np.all(S == S2)),
             'S': S.copy(), 'cnt': cnt}
        if st == 0:
            Sf = S.view(np.float64)
            Uf = Ub.view(np.float64).reshape(m, n)
            Vf = Vb.view(np.float64).reshape(n, n)
            r['nonfinite_uv'] = int((~np.isfinite(Uf)).sum() + (~np.isfinite(Vf)).sum())
            r['nonfinite_s'] = int((~np.isfinite(Sf)).sum())
            r['desc'] = bool(np.all(Sf >= 0) and np.all(Sf[:-1] >= Sf[1:]) and not np.any(np.isnan(Sf)))
            UL = Uf.astype(LD)
            VL = Vf.astype(LD)
            J = Sf >= 2.0 ** -1022
            uu = UL[:, J].T @ UL[:, J] - np.eye(int(J.sum()), dtype=LD)
            r['u_orth'] = _inf_nan(float(np.max(np.abs(uu)) / U)) if J.sum() else 0.0
            JA = Sf != 0
            ua = UL[:, JA].T @ UL[:, JA] - np.eye(int(JA.sum()), dtype=LD)
            r['u_all'] = _inf_nan(float(np.max(np.abs(ua)) / U)) if JA.sum() else 0.0
            vv = VL @ VL.T - np.eye(n, dtype=LD)
            r['vt_orth'] = _inf_nan(float(np.max(np.abs(vv)) / U))
            Z = Sf == 0
            r['u0col'] = bool(not np.any(Z & np.any(Uf != 0, axis=0)))
            A = np.array(bl, dtype='<u8').view(np.float64).reshape(m, n).astype(LD)
            if np.all(np.isfinite(Sf)):
                R = A - (UL * Sf.astype(LD)) @ VL
                r['recon'] = _inf_nan(float(np.max(np.abs(R)) / (U * LD(Sf[0]) + TINY)))
            else:
                r['recon'] = float('nan')
        out.append(r)
    return out


if __name__ == '__main__':
    if sys.argv[1:] in (['-h'], ['--help']):
        print(__doc__)
        sys.exit(0)
    print('quick.py is a module: import it and call quick.run(items, driver) (see tools/d1hunt.py)',
          file=sys.stderr)
    sys.exit(2)
