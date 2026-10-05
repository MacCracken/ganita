#!/usr/bin/env python3
"""U orthonormality on tall matrices (oracle-free): u_orth = max|U_J^T U_J - I|/u over columns
with returned sigma >= 2^-1022, vt_orth, and status, for each tree.

usage: tall_study.py --labels L1[,L2...] [SEED [MS [NS [REPS [KINDS]]]]]
  defaults: SEED 9, MS 1000,4096,16384, NS 2,3,4,8, REPS 2, KINDS rand,int-rankdef,rand-rankdef,int-full
  (more kinds: design-poly, design-pos, counts, int-corr, small-int, pos).  Each label's driver is
  $SVDH_WORK/build/drv_<L> (build.sh; an aarch64 one runs under qemu-aarch64).
  int-rankdef sets the last column to 3*c0 - 2*c1 (for n = 2: 3*c0), and rand-rankdef copies
  column 0 into the last column, so for n >= 2 their exact rank is n - 1; for n = 1 both leave the
  matrix as drawn, of full rank 1.
Exits with status 2 on a usage error, a label not usable in file names (README.md), a missing
driver or an unusable scratch directory, and 1 when a driver fails; scratch files go to
$SVDH_WORK/scratch and are removed, also when it fails or is stopped by SIGINT or SIGTERM, which
stop the running driver too."""
import os
import random
import shlex
import struct
import subprocess
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import corpus as C   # noqa: E402
import check as CK   # noqa: E402

LD = np.longdouble
U = 2.0 ** -52
USAGE = 'usage: tall_study.py --labels L1[,L2...] [SEED [MS [NS [REPS [KINDS]]]]]'
ALL_KINDS = ('rand', 'rand-rankdef', 'int-rankdef', 'int-full', 'design-poly', 'design-pos', 'counts',
             'int-corr', 'small-int', 'pos')
argv = sys.argv[1:]
if '-h' in argv or '--help' in argv:
    print(__doc__)
    sys.exit(0)
if '--labels' not in argv or argv.index('--labels') + 1 >= len(argv) or len(argv) > 7:
    C.input_error(USAGE)
_i = argv.index('--labels')
labels = [L for L in argv[_i + 1].split(',') if L]
del argv[_i:_i + 2]
if not labels:
    C.input_error(USAGE)
if len(set(labels)) != len(labels):
    C.input_error('tall_study.py: --labels names a tree more than once')
for L in labels:
    CK.check_label(L)
    if not os.access(os.path.join(C.WORK, 'build', 'drv_%s' % L), os.X_OK):
        C.input_error('tall_study.py: no driver for %s: run scripts/svdh/adv/build.sh %s first'
                      % (L, ('%s <tree> aarch64' % L[:-4]) if L.endswith('_a64') else '%s [<tree>]' % L))
try:
    rng = random.Random(int(argv[0]) if len(argv) > 0 else 9)
    ms = [int(x) for x in (argv[1] if len(argv) > 1 else '1000,4096,16384').split(',')]
    ns = [int(x) for x in (argv[2] if len(argv) > 2 else '2,3,4,8').split(',')]
    reps = int(argv[3]) if len(argv) > 3 else 2
except ValueError:
    C.input_error(USAGE + '\n  SEED and REPS are integers, MS and NS comma-separated integers')
KINDS = (argv[4] if len(argv) > 4 else 'rand,int-rankdef,rand-rankdef,int-full').split(',')
bad = [k for k in KINDS if k not in ALL_KINDS]
if bad:
    C.input_error('tall_study.py: unknown kind(s) %s; known: %s' % (','.join(bad), ','.join(ALL_KINDS)))
bad = [(m, n) for m in ms for n in ns if not (m >= n >= 1)]
if bad:
    C.input_error('tall_study.py: need MS >= NS >= 1 (got %s)' % bad[:3])
CK.require_longdouble()
C.term_as_exit()                       # SIGTERM, too, removes the scratch corpus (finally, below)
mats = []
for m in ms:
    for n in ns:
        for r in range(reps):
            for kind in KINDS:
                if kind == 'rand':
                    A = np.array(C.rmat(rng, m, n, -1, 0))
                elif kind == 'rand-rankdef':
                    A = np.array(C.rmat(rng, m, n, -1, 0))
                    A[:, n - 1] = A[:, 0]          # exact duplicate: exact rank n-1 (for n >= 2)
                elif kind == 'int-rankdef':
                    A = np.array([[float(rng.randrange(-(1 << 20), 1 << 20)) for _ in range(n)] for _ in range(m)])
                    if n >= 3:
                        A[:, n - 1] = 3 * A[:, 0] - 2 * A[:, 1]
                    elif n == 2:
                        A[:, 1] = 3 * A[:, 0]
                elif kind == 'int-full':
                    A = np.array([[float(rng.randrange(-(1 << 20), 1 << 20)) for _ in range(n)] for _ in range(m)])
                elif kind == 'design-poly':
                    x = np.array([rng.random() for _ in range(m)]) + 0.5
                    A = np.stack([x ** j for j in range(n)], axis=1)
                elif kind == 'design-pos':
                    A = np.array([[1.0] + [rng.random() + 0.5 for _ in range(n - 1)] for _ in range(m)])
                elif kind == 'counts':
                    A = np.array([[1.0] + [float(rng.randrange(0, 10 ** (1 + j))) for j in range(n - 1)]
                                  for _ in range(m)])
                elif kind == 'int-corr':
                    c0 = np.array([float(rng.randrange(-(1 << 20), 1 << 20)) for _ in range(m)])
                    A = np.stack([c0] + [3 * c0 - 2 * np.array([float(rng.randrange(-(1 << 20), 1 << 20))
                                                                for _ in range(m)])
                                         for _ in range(n - 1)], axis=1)
                elif kind == 'small-int':
                    A = np.array([[float(rng.randrange(-3, 4)) for _ in range(n)] for _ in range(m)])
                elif kind == 'pos':
                    A = np.array([[rng.random() for _ in range(n)] for _ in range(m)])
                mats.append(('%dx%d %s #%d' % (m, n, kind, r), A))
C.make_outdir('tall_study.py', os.path.join(C.WORK, 'scratch'))
path = os.path.join(C.WORK, 'scratch', 'tall_%d.bin' % os.getpid())
res = {}
want = sum(2 + 2 * A.shape[1] + A.shape[0] * A.shape[1] + A.shape[1] ** 2 for _, A in mats)
try:
    try:
        with open(path, 'wb') as fh:
            fh.write(struct.pack('<Q', len(mats)))
            for lab, A in mats:
                fh.write(struct.pack('<QQ', *A.shape))
                fh.write(A.astype('<f8').tobytes())
    except OSError as e:
        C.input_error('tall_study.py: cannot write the scratch corpus %s: %s' % (path, e.strerror or e))
    for L in labels:
        drv = os.path.join(C.WORK, 'build', 'drv_%s' % L)
        # exec: the process that subprocess.run kills when this script is stopped is the driver (or
        # qemu-aarch64) itself, not a shell that would leave it running
        cmd = 'exec ' + ' '.join(shlex.quote(x) for x in CK.runner_for(drv) + [drv]) + ' 3>/dev/null'
        with open(path, 'rb') as fi:
            p = subprocess.run(cmd, shell=True, stdin=fi, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if p.returncode != 0 or len(p.stdout) != 8 * want:
            sys.exit('tall_study.py: driver %s failed (exit %d, %d of %d bytes): %s' % (
                drv, p.returncode, len(p.stdout), 8 * want, p.stderr.decode(errors='replace').strip()[-300:]))
        res[L] = np.frombuffer(p.stdout, dtype='<u8')
finally:
    if os.path.exists(path):
        os.remove(path)
print('%-28s ' % 'matrix' + ' '.join('%-26s' % L for L in labels))
offs = {L: 0 for L in labels}
for lab, A in mats:
    m, n = A.shape
    sz = 2 + 2 * n + m * n + n * n
    cells = []
    for L in labels:
        w = res[L][offs[L]:offs[L] + sz]
        offs[L] += sz
        st = int(np.int64(w[0]))
        if st != 0:
            cells.append('st %d' % st)
            continue
        S = w[1:1 + n].view(np.float64)
        Uq = w[1 + n:1 + n + m * n].view(np.float64).reshape(m, n).astype(LD)
        Vt = w[1 + n + m * n:1 + n + m * n + n * n].view(np.float64).reshape(n, n).astype(LD)
        J = S >= 2.0 ** -1022
        uo = float(np.max(np.abs(Uq[:, J].T @ Uq[:, J] - np.eye(int(J.sum()), dtype=LD))) / U)
        vo = float(np.max(np.abs(Vt @ Vt.T - np.eye(n, dtype=LD))) / U)
        cells.append('uo %7.1f vo %5.1f s_n/s1 %.0e' % (uo, vo, S[-1] / S[0]))
    print('%-28s ' % lab + ' '.join('%-26s' % c for c in cells), flush=True)
