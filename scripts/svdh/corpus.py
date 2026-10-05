#!/usr/bin/env python3
"""SVD evaluation corpus + exact oracle for ganita_mat_svd.

usage: corpus.py [--out DIR] [--procs N]
Writes into $SVDH_WORK (default <repo>/build/svdh), or into --out DIR:
  corpus.bin        u64 count, then per matrix: u64 rows, u64 cols, rows*cols u64 f64 bits (row-major)
  corpus_meta.json  [{id, class, label, rows, cols}, ...]
  oracle.json       {"matrices": [{id, reject, sigma_bits[hex], hp[[m64,e]], rel_ok[bool], rank,
                                   method, prec}, ...], "info": {...}}
The three files are written under temporary names and renamed together at the end, so a failed
or interrupted run (also by SIGTERM) leaves the previous set as it was.  When the oracle's
self-checks (verify(), below) fail, the new files are kept as corpus.bin.failed,
corpus_meta.json.failed and oracle.json.failed for inspection, the previous set stays in place,
and corpus.py exits with status 1.

Deterministic: every class draws from its own random.Random(seed).  Needs mpmath + numpy
(requirements.txt; other versions only warn).  The oracle runs on a pool of --procs processes
(default: every CPU); the number of processes changes no output byte.

Oracle (see README.md for the full argument):
  n == 1 : sigma^2 = sum a_i^2 exactly (Fraction), sqrt at high precision.
  n == 2 : G = A^T A exactly; disc = (g11-g22)^2 + 4 g12^2 and det = g11 g22 - g12^2 exactly;
           lmax = (tr + sqrt(disc))/2 (no cancellation), lmin = det/lmax; sigma = sqrt.
           Relative error <= 2^(-P+3) at mpmath precision P.
  n >= 3 : exact rank r by fraction-free (Bareiss) elimination on the integer-scaled matrix; the
           n-r smallest sigma are exactly 0.  The r non-zero sigma come from mpmath.svd_r at
           precision P >= 140 + log2(sigma_1/sigma_r) bits, recomputed at P+64; the two runs must
           agree to the a-priori bound 2^(-P+20) sigma_1 (backward stability + Weyl), and each
           sigma is accepted only when the whole interval sigma +- 2^(-P-44) sigma_1 rounds to
           the same double.  Cross-checks: sum sigma^2 == ||A||_F^2 exactly-ish and, for square
           full-rank A, prod sigma == |det A| (exact det) to 2^-80 relative.
  Every sigma is rounded ONCE, correctly (ties-to-even, subnormals, overflow to +inf) from an
  exact Fraction.  rel_ok[i] = that certification succeeded (the double is the correctly rounded
  exact sigma_i, hence relative-accurate); exact zeros are rel_ok too.
"""
import argparse
import ctypes
import json
import math
import os
import random
import re
import signal
import struct
import sys
import time
from fractions import Fraction
import multiprocessing as mproc

try:
    import mpmath
    import numpy as np
except ImportError as _e:
    print('svdh: %s cannot import %s: pip install -r scripts/svdh/requirements.txt, or use another '
          'python (PY=... for the shell scripts)' % (sys.executable, _e.name), file=sys.stderr)
    sys.exit(2)

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
WORK = os.path.abspath(os.environ.get('SVDH_WORK') or os.path.join(REPO, 'build', 'svdh'))
TWO52 = 1 << 52
INF_BITS = 0x7FF0000000000000
DBL_MAX_F = Fraction(float.fromhex('0x1.fffffffffffffp+1023'))


# ----------------------------------------------------------------- environment, output files
def input_error(msg):
    """Exit with status 2 and msg on stderr: a usage or input error (a missing or malformed file,
    an unusable output directory, a missing driver).  Status 1 is kept for a negative answer: a
    disagreement, a failed self-check, a driver that failed."""
    try:
        sys.stdout.flush()              # what was printed first comes first in a shared log
    except (OSError, ValueError):
        pass
    print(msg, file=sys.stderr)
    sys.exit(2)


def _requirements():
    """What requirements.txt pins: ({package: version}, python version, (OpenBLAS kernel set,
    thread count)); the last two are None when it does not say."""
    want, py, blas = {}, None, None
    with open(os.path.join(HERE, 'requirements.txt')) as fh:
        for line in fh:
            line = line.strip()
            m = re.match(r'#\s*python\s+(\S+)', line, re.IGNORECASE)
            b = re.match(r'#\s*openblas\s+(\w+)\s+(\d+)', line, re.IGNORECASE)
            if m:
                py = m.group(1)
            elif b:
                blas = (b.group(1), int(b.group(2)))
            elif '==' in line and not line.startswith('#'):
                k, v = line.split('==', 1)
                want[k.strip()] = v.strip()
    return want, py, blas


def check_versions():
    """Warn on stderr when mpmath, numpy or the Python minor version differ from the ones in
    requirements.txt, which made the reference files: a regenerated set may then differ from
    them.  Every generator calls this from its main()."""
    want, py, _ = _requirements()
    have = {'mpmath': mpmath.__version__, 'numpy': np.__version__}
    for k, v in sorted(want.items()):
        if have.get(k) != v:
            print('svdh: warning: %s %s; the reference files were made with %s, so a regenerated '
                  'set may not match them byte for byte' % (k, have.get(k), v), file=sys.stderr)
    if py and py.split('.')[:2] != [str(x) for x in sys.version_info[:2]]:
        print('svdh: warning: python %s; the reference files were made with python %s'
              % (sys.version.split()[0], py), file=sys.stderr)


def _openblas():
    """ctypes handles of the OpenBLAS libraries loaded in this process, numpy's (Linux: from
    /proc/self/maps); [] where there is none, or no /proc."""
    try:
        with open('/proc/self/maps') as fh:
            paths = sorted({line.split()[-1] for line in fh if 'openblas' in line.rsplit('/', 1)[-1].lower()})
    except OSError:
        return []
    libs = []
    for p in paths:
        try:
            libs.append(ctypes.CDLL(p))
        except OSError:
            pass
    return libs


def _blas_fn(libs, stem):
    """The first of OpenBLAS's names for `stem` (get_corename, set_num_threads) that a lib has:
    numpy's wheels prefix them with scipy_ and add a 64_ suffix for their 64-bit integers."""
    for lib in libs:
        for name in ('scipy_openblas_%s64_' % stem, 'scipy_openblas_%s' % stem, 'openblas_%s64_' % stem,
                     'openblas_%s' % stem):
            f = getattr(lib, name, None)
            if f is not None:
                return f
    return None


def blas_setup(quiet=False):
    """Set numpy's OpenBLAS to the thread count the reference files were made with
    (requirements.txt), and (unless quiet) warn on stderr when it runs another kernel set than
    they were made with, or when there is no OpenBLAS to ask.  Some generated bytes go through
    numpy's BLAS and LAPACK (README.md, Requirements).  Each CPU family has its own kernels, and
    the result of some calls depends on how many threads OpenBLAS splits them between: in
    adv/gen.py, the entries of atall2 (16,384 rows and more, built with dot products) and the
    numpy sigma of the two big bigdef matrices change with the thread count, the entries of
    bunder and brestart (4,096 rows at most) do not.  OPENBLAS_CORETYPE (an environment
    variable, read when numpy loads OpenBLAS) chooses the kernels; the thread count is set here,
    since OPENBLAS_NUM_THREADS cannot go above the CPUs the process may run on.  The generators
    that use numpy's BLAS (corpus.py, adv/gen.py, hunts/gen.py) and adv/hunt.py call this from
    their main(), and adv/gen.py from each oracle process too (quiet)."""
    _, _, blas = _requirements()
    if blas is None:
        return
    core, threads = blas
    libs = _openblas()
    getname, setthreads = _blas_fn(libs, 'get_corename'), _blas_fn(libs, 'set_num_threads')
    if getname is None or setthreads is None:
        if not quiet:
            print('svdh: warning: cannot find the OpenBLAS numpy uses; the reference files were made '
                  'with its %s kernels and %d threads, so a regenerated set may not match them byte for '
                  'byte' % (core, threads), file=sys.stderr)
        return
    setthreads(ctypes.c_int(threads))
    if quiet:
        return
    getname.restype = ctypes.c_char_p
    have = (getname() or b'?').decode(errors='replace')
    if have.lower() != core.lower():
        print("svdh: warning: numpy's OpenBLAS runs its %s kernels; the reference files were made with "
              'its %s kernels, so a regenerated set may not match them byte for byte (on an x86_64 CPU '
              'with AVX2 and FMA, OPENBLAS_CORETYPE=%s selects those)' % (have, core, core), file=sys.stderr)


def procs_arg(s):
    """argparse type of an integer >= 1 (--procs; hunt.py's COUNT)."""
    try:
        v = int(s)
    except ValueError:
        raise argparse.ArgumentTypeError('%r is not an integer' % s)
    if v < 1:
        raise argparse.ArgumentTypeError('must be at least 1')
    return v


SET_FILES = ('corpus.bin', 'corpus_meta.json', 'oracle.json')


def tmp_path(outdir, name):
    """Where a set file is written before publish() moves it into place."""
    return os.path.join(outdir, name + '.tmp')


def publish(outdir, names=SET_FILES):
    """Rename every DIR/<name>.tmp to DIR/<name>.  Called once all the files of a set are
    written, so a failed or interrupted run never leaves a new corpus beside an old oracle."""
    for name in names:
        os.replace(tmp_path(outdir, name), os.path.join(outdir, name))


def discard_tmp(outdir, names=SET_FILES):
    """Remove the temporary files of a run that did not finish."""
    for name in names:
        try:
            os.remove(tmp_path(outdir, name))
        except OSError:
            pass


def make_outdir(prog, path):
    """os.makedirs(path), or exit with a message when it cannot be (a file, no permission)."""
    try:
        os.makedirs(path, exist_ok=True)
    except OSError as e:
        input_error('%s: cannot create the output directory %s: %s' % (prog, path, e.strerror or e))


def term_as_exit():
    """Make SIGTERM raise SystemExit(143) in this process, so that a generator's
    `except BaseException: discard_tmp(...)` also runs when it is terminated.  Worker
    processes keep the default action."""
    pid = os.getpid()

    def handler(signum, frame):
        if os.getpid() != pid:
            signal.signal(signum, signal.SIG_DFL)
            os.kill(os.getpid(), signum)
            return
        raise SystemExit(128 + signum)
    signal.signal(signal.SIGTERM, handler)


HEX16 = re.compile(r'[0-9a-fA-F]{16}')


def read_hits(path, allow_empty=True):
    """The entries of a hunt-hit JSON list (adv/hunt.py's format: {label, rows, cols, tree, why,
    bits}), as read, each checked: a non-empty string label, integer rows and cols with
    rows >= cols >= 1, rows*cols bits that are 16-digit hex strings without a NaN or infinite
    entry, and, where present, a string tree and a list of strings why.  Raises
    ValueError with a message when the file cannot be read, is not such a list, or an entry is
    not such."""
    try:
        with open(path) as fh:
            hits = json.load(fh)
    except ValueError as e:
        raise ValueError('%s is not JSON: %s' % (path, e))
    except OSError as e:
        raise ValueError('cannot read %s: %s' % (path, e.strerror or e))
    if not isinstance(hits, list) or not (hits or allow_empty):
        raise ValueError('%s: need a %slist of {"label", "rows", "cols", "bits"}'
                         % (path, '' if allow_empty else 'non-empty '))
    for k, h in enumerate(hits):
        if not isinstance(h, dict) or not isinstance(h.get('label'), str) or not h['label'].strip():
            raise ValueError('%s: entry %d: need an object with a non-empty string label' % (path, k))
        lab = h['label']
        if 'tree' in h and not isinstance(h['tree'], str):
            raise ValueError('%s: %s: tree is not a string' % (path, lab))
        why = h.get('why', [])
        if not isinstance(why, list) or not all(isinstance(w, str) for w in why):
            raise ValueError('%s: %s: why is not a list of strings' % (path, lab))
        m, n, bl = h.get('rows'), h.get('cols'), h.get('bits')
        if type(m) is not int or type(n) is not int or not isinstance(bl, list):
            raise ValueError('%s: %s: need integer rows and cols and a list of bits' % (path, lab))
        if not (m >= n >= 1 and len(bl) == m * n):
            raise ValueError('%s: %s: need rows >= cols >= 1 and rows*cols bits' % (path, lab))
        if not all(isinstance(b, str) and HEX16.fullmatch(b) for b in bl):
            raise ValueError('%s: %s: a bit pattern is not a 16-digit hex string' % (path, lab))
        if any((int(b, 16) >> 52) & 0x7FF == 0x7FF for b in bl):
            raise ValueError('%s: %s: a NaN or infinite entry has no SVD (and no oracle)' % (path, lab))
    return hits


def load_hits(path, allow_empty=True):
    """(label, rows, cols, bits, why) of each entry of a hunt-hit JSON list (read_hits checks
    them; bits as integers, why [] where it is absent)."""
    return [(h['label'], h['rows'], h['cols'], [int(b, 16) for b in h['bits']], h.get('why', []))
            for h in read_hits(path, allow_empty)]


# ----------------------------------------------------------------- bit helpers
def bits_of(x):
    return struct.unpack('<Q', struct.pack('<d', x))[0]


def f_of(b):
    return struct.unpack('<d', struct.pack('<Q', b & 0xFFFFFFFFFFFFFFFF))[0]


def mkf(frac, e):
    """(1 + frac/2^52) * 2^e, correctly rounded (subnormal results allowed)."""
    if e >= -1022:
        return math.ldexp(1.0 + frac / TWO52, e)
    return float(Fraction(TWO52 + frac, 1 << (52 - e)))


def rfull(rng, e_lo, e_hi, zero_p=0.0):
    """Random full-mantissa double, exponent uniform in [e_lo, e_hi], random sign."""
    if zero_p and rng.random() < zero_p:
        return 0.0
    e = rng.randint(e_lo, e_hi)
    v = mkf(rng.getrandbits(52), e)
    return -v if rng.getrandbits(1) else v


def rmat(rng, m, n, e_lo=-4, e_hi=-1):
    return [[rfull(rng, e_lo, e_hi) for _ in range(n)] for _ in range(m)]


def round_frac_bits(f):
    """Correctly rounded double bits of a NON-NEGATIVE Fraction (overflow -> +inf)."""
    if f == 0:
        return 0
    try:
        return bits_of(float(f))      # int/int true division: correctly rounded in CPython
    except OverflowError:
        return INF_BITS


def mpf_to_frac(x):
    man, exp = x.man_exp if hasattr(x, 'man_exp') else mpmath.mpf(x).man_exp
    man = int(man)
    if exp >= 0:
        return Fraction(man << exp)
    return Fraction(man, 1 << (-exp))


def frac_m64e(f):
    """f ~= m * 2^e with 2^63 <= m < 2^64 (round-half-even); (0,0) for 0."""
    if f == 0:
        return (0, 0)
    num, den = f.numerator, f.denominator
    e = num.bit_length() - den.bit_length() - 64
    while True:
        q = Fraction(num, den) / (Fraction(2) ** e)
        m = round(q)
        if m >= (1 << 64):
            e += 1
            continue
        if m < (1 << 63):
            e -= 1
            continue
        return (int(m), int(e))


# ----------------------------------------------------------------- matrix classes
def mat_fam():
    out = []
    mants = [('m=1', 0), ('m=0xB8F2A4C1D3E57', 0xB8F2A4C1D3E57),
             ('m=0x6A09E667F3BCD', 0x6A09E667F3BCD), ('m=0x921FB54442D18', 0x921FB54442D18)]
    for mlab, frac in mants:
        for e in range(-1074, 0):
            t = mkf(frac, e)
            A = [[1.0, t], [t, t], [t, -t]]
            out.append(('fam', 'fam %s e=%d t=%s' % (mlab, e, hex(bits_of(t))), A))
    return out


def mat_rand2():
    rng = random.Random(20261003)
    out = []
    for S in (4, 60, 600, 2100):
        for shape in ((2, 2), (3, 2)):
            for k in range(750):
                base = rng.randint(-1074, 1023)
                m, n = shape
                A = []
                for i in range(m):
                    row = []
                    for j in range(n):
                        if rng.random() < 0.10:
                            row.append(0.0)
                            continue
                        e = min(1023, max(-1074, base + rng.randint(-S, S)))
                        v = mkf(rng.getrandbits(52), e)
                        row.append(-v if rng.getrandbits(1) else v)
                    A.append(row)
                out.append(('rand2', 'rand2 %dx%d spread=%d #%d base=%d' % (m, n, S, k, base), A))
    return out


def _edit(rng, A, edit):
    m = len(A)
    if edit == 'zero-row':
        r = rng.randrange(m)
        A[r] = [0.0] * len(A[0])
        return 'zero-row r=%d' % r
    A[m - 1] = list(A[0])
    return 'repeat-row'


def mat_sqdef():
    rng = random.Random(4242)
    out = []
    for n in (2, 3, 4, 6, 10):
        for edit in ('zero-row', 'repeat-row'):
            for k in range(500):
                A = rmat(rng, n, n, -3, 0)
                lab = _edit(rng, A, edit)
                out.append(('sqdef', 'sqdef %dx%d %s #%d' % (n, n, lab, k), A))
    return out


def mat_talldef():
    rng = random.Random(5151)
    out = []
    for (m, n) in ((3, 2), (5, 4), (8, 5)):
        for edit in ('zero-row', 'repeat-row'):
            for k in range(300):
                A = rmat(rng, m, n, -3, 0)
                lab = _edit(rng, A, edit)
                out.append(('talldef', 'talldef %dx%d %s #%d' % (m, n, lab, k), A))
    return out


def mat_outer():
    rng = random.Random(777)
    out = []
    for (m, n) in ((2, 2), (3, 3), (4, 4), (6, 6), (10, 10), (3, 2), (5, 4), (8, 5)):
        for k in range(150):
            x = [rfull(rng, -3, 0) for _ in range(m)]
            y = [rfull(rng, -3, 0) for _ in range(n)]
            A = [[x[i] * y[j] for j in range(n)] for i in range(m)]
            out.append(('outer', 'outer %dx%d #%d' % (m, n, k), A))
    return out


W54_BITS = [
    0xbfc2cacd2bba2bfc, 0x3ff436f97395fc68, 0xc00807f8a62bf805, 0x3ff337df0357c8c9,
    0x3fefd315acc77fe7, 0xbfa1614b40ea6cc2, 0xc0295cebbfddbb61, 0xbfc32af6f3470282,
    0xbfd6269dc8658203, 0xc025b46bf0a392b4, 0x3fc03ff652eed9bf, 0x0000000000000000,
    0x3fdf9160669d391a, 0x3fcc98b730a0d724, 0xbfbc46376ff5e5c4, 0x3fc92a56372a02bb,
    0xc02551acec11860f, 0x400130c3519e4f30, 0x3fc6d251f22a1e9b, 0x3fe9e1efc1aeb952,
]


def _bm(rows, cols, bl):
    return [[f_of(bl[i * cols + j]) for j in range(cols)] for i in range(rows)]


def _fam_t(tb):
    t = f_of(tb)
    return [[1.0, t], [t, t], [t, -t]]


# expected oracle bits quoted in the filings (checked by verify())
EXPECT_BITS = {
    'A1': [0x3FF0000000000000, 0x1FE6A09E667F3BCD],
    'A2': [0x3FF0000000000000, 0x1FE6A09E667F3BCE],
    'A3': [0x3FF0000000000000, 0x1FF6A09E667F3BCD],
    'A4': [0x3FF0000000000000, 0x1E137CC152F76F67],
    'A5': [0x3FF0000000000000, 0x0000000000000001],
    'A6': [0x3FF0000000000000, 0x001058E43F6FA300],
    'B1': [0x6FCB799CC80A713E, 0x4B3326815FE2FA41],
    'B2': [0x35DAC74898CD0527, 0x0C56594A23EF8276],
    'C': [0x4005D534C62740B5, 0x3FFA27692399E1D9],
    'Z': [0x400D3FB1257408C4, 0x3FFC17E03945F102, 0],
}
EXPECT_DEC = {'W54': ['13.166199101181938', '11.788740275814376', '9.8679004436648459',
                      '1.183645125577899']}


def mat_wit():
    W = []

    def add(label, A):
        W.append(('wit', label, A))

    add('Z', [[1.3, 2.7, 0.4], [0.0, 0.0, 0.0], [0.9, 1.1, 2.3]])
    add('R123 [[1,2,3],[1,2,3],[4,5,6]]', [[1.0, 2.0, 3.0], [1.0, 2.0, 3.0], [4.0, 5.0, 6.0]])
    add('M789 [[1,2,3],[4,5,6],[7,8,9]]', [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0], [7.0, 8.0, 9.0]])
    w54 = _bm(5, 4, W54_BITS)
    add('W54', w54)
    for k in (-827, -327, 173):
        add('W54*2^%d' % k, [[math.ldexp(x, k) for x in r] for r in w54])
    add('B1', _bm(3, 2, [0xCB3326815FE2FA41, 0x6C7B1009E69DC636, 0x0000000000000000,
                         0x6FCB799CC80A713E, 0xC78D2DAD93DD5D23, 0x5B82A0E6E26B85A5]))
    add('B2', _bm(3, 2, [0x89F0481668FD9259, 0xB5DAC74898CD0527, 0x03B8DFFBAEE26112,
                         0x29858E6E791CDEE9, 0x0C56594A23EF8276, 0x1CE65B0EE8C8430C]))
    add('C', _bm(3, 2, [0x3FF4CCCCCCCCCCCD, 0x3FE6666666666666, 0x4000CCCCCCCCCCCD,
                        0xBFD999999999999A, 0x3FECCCCCCCCCCCCD, 0x3FF999999999999A]))
    add('A1', _fam_t(0x1FE0000000000000))
    add('A2', _fam_t(0x1FE0000000000001))
    add('A3', _fam_t(0x1FF0000000000000))
    add('A4', _fam_t(0x1E0B8F2A4C1D3E57))
    add('A5', _fam_t(0x0000000000000001))
    add('A6', _fam_t(0x000B8F2A4C1D3E57))
    add('near1e-9 [[1,1],[1,1+1e-9]]', [[1.0, 1.0], [1.0, 1.0 + 1e-9]])
    add('near1e-6 [[1,1],[1,1+1e-6]]', [[1.0, 1.0], [1.0, 1.0 + 1e-6]])
    add('zero2x2', [[0.0, 0.0], [0.0, 0.0]])
    add('zero3x3', [[0.0] * 3 for _ in range(3)])
    add('I3', [[1.0 if i == j else 0.0 for j in range(3)] for i in range(3)])
    add('diag(3,2)', [[3.0, 0.0], [0.0, 2.0]])
    add('[[1,2],[3,4],[5,6]]', [[1.0, 2.0], [3.0, 4.0], [5.0, 6.0]])
    add('PINV_A 5x3 rank2', [[float(i + 1), float((i * i) % 7 - 3), 0.0] for i in range(5)])
    add('1x1 [[5]]', [[5.0]])
    add('4x1 [1,-2,3,-4]', [[1.0], [-2.0], [3.0], [-4.0]])
    add('3x3 zero col1', [[1.5, 0.0, -2.25], [0.5, 0.0, 3.0], [4.0, 0.0, 1.0]])
    add('4x3 cols0==2', [[1.0, 2.0, 1.0], [3.0, 4.0, 3.0], [5.0, 6.0, 5.0], [7.0, 8.0, 7.0]])
    return W


def mat_randwell():
    rng = random.Random(9090)
    out = []
    for (m, n) in ((2, 2), (3, 3), (5, 3), (8, 8), (12, 7), (20, 15), (16, 16)):
        for k in range(60):
            out.append(('randwell', 'randwell %dx%d #%d' % (m, n, k), rmat(rng, m, n, -4, -1)))
    return out


def _well_B(rng, m, n):
    while True:
        B = rmat(rng, m, n, -4, -1)
        s = np.linalg.svd(np.array(B), compute_uv=False)
        if s[-1] > 0 and s[0] / s[-1] < 100.0:
            return B


def _grade_exps(rng, k):
    S = rng.randint(0, 600)
    mid = sorted(rng.randint(0, S) for _ in range(max(0, k - 2)))
    return S, [0] + mid + [S] if k >= 2 else [0]


def mat_graded():
    rng = random.Random(31337)
    out = []
    for (m, n) in ((3, 3), (5, 4), (8, 6)):
        for grading in ('col', 'row'):
            for k in range(60):
                B = _well_B(rng, m, n)
                if grading == 'col':
                    S, ex = _grade_exps(rng, n)
                    A = [[math.ldexp(B[i][j], -ex[j]) for j in range(n)] for i in range(m)]
                else:
                    S, ex = _grade_exps(rng, m)
                    A = [[math.ldexp(B[i][j], -ex[i]) for j in range(n)] for i in range(m)]
                out.append(('graded', 'graded %dx%d %s span=2^-%d #%d' % (m, n, grading, S, k), A))
    return out


def mat_extreme():
    rng = random.Random(1000)
    out = []
    for (m, n) in ((2, 2), (3, 2), (4, 4), (6, 3)):
        for kind in ('big', 'sub', 'mixed'):
            for k in range(50):
                if kind == 'big':
                    A = [[math.ldexp(x, 1000) for x in r] for r in rmat(rng, m, n, -4, -1)]
                elif kind == 'sub':
                    A = [[float(Fraction(x) / (Fraction(2) ** 1060)) for x in r]
                         for r in rmat(rng, m, n, -4, -1)]
                else:
                    A = [[rfull(rng, 990, 1000) if rng.getrandbits(1) else rfull(rng, -1000, -990)
                          for _ in range(n)] for _ in range(m)]
                out.append(('extreme', 'extreme %dx%d %s #%d' % (m, n, kind, k), A))
    return out


def _round_prod(X, Y):
    m, r, n = len(X), len(Y), len(Y[0])
    FX = [[Fraction(v) for v in row] for row in X]
    FY = [[Fraction(v) for v in row] for row in Y]
    return [[float(sum(FX[i][k] * FY[k][j] for k in range(r))) for j in range(n)] for i in range(m)]


def mat_rankdef():
    rng = random.Random(6060)
    out = []
    for (m, n, r) in ((4, 4, 2), (6, 5, 3), (10, 8, 4), (5, 5, 1), (8, 8, 6)):
        for k in range(60):
            A = _round_prod(rmat(rng, m, r, -4, -1), rmat(rng, r, n, -4, -1))
            out.append(('rankdef', 'rankdef %dx%d r=%d product #%d' % (m, n, r, k), A))
    shapes = ((4, 3), (6, 4), (8, 6), (5, 5))
    for kind in ('zero-col', 'dup-col', 'ulp-col'):
        for (m, n) in shapes:
            for k in range(25):
                A = rmat(rng, m, n, -4, -1)
                j = rng.randrange(n)
                if kind == 'zero-col':
                    for i in range(m):
                        A[i][j] = 0.0
                    lab = 'zero-col c=%d' % j
                else:
                    c = rng.randrange(n - 1)
                    if c >= j:
                        c += 1
                    for i in range(m):
                        A[i][j] = A[i][c]
                    lab = 'dup-col c%d=c%d' % (j, c)
                    if kind == 'ulp-col':
                        i0 = rng.randrange(m)
                        A[i0][j] = math.nextafter(A[i0][j], math.inf if rng.getrandbits(1) else -math.inf)
                        lab = 'ulp-col c%d=c%d+1ulp@r%d' % (j, c, i0)
                out.append(('rankdef', 'rankdef %dx%d %s #%d' % (m, n, lab, k), A))
    return out


def _householder_Q(rng, n, k):
    """Exact rational orthogonal n x n: product of k Householder reflectors of random vectors."""
    Q = [[Fraction(int(i == j)) for j in range(n)] for i in range(n)]
    for _ in range(k):
        v = [Fraction(rfull(rng, -2, 0)) for _ in range(n)]
        vv = sum(x * x for x in v)
        # Q <- Q (I - 2 v v^T / vv)
        Qv = [sum(Q[i][l] * v[l] for l in range(n)) for i in range(n)]
        for i in range(n):
            f = 2 * Qv[i] / vv
            for j in range(n):
                Q[i][j] -= f * v[j]
    return Q


CLUSTER_S = [
    ('1,1,1,.5', [1, 1, 1, 0.5, 0.5, 0.25]),
    ('2,2,1e-8,1e-8', [2, 2, 1e-8, 1e-8, 1e-8, 1e-8]),
    ('1,1+2^-40,1-2^-40', [1, 1 + 2.0 ** -40, 1 - 2.0 ** -40, 0.5, 0.5 + 2.0 ** -40, 0.25]),
    ('all-equal', [1.5] * 6),
    ('3,1e-5x', [3, 1e-5, 1e-5, 1e-5, 1e-5, 1e-5]),
    ('1,1,.1,.1,.01,.01', [1, 1, 0.1, 0.1, 0.01, 0.01]),
    ('1,1e-150x', [1, 1e-150, 1e-150, 1e-150, 1e-150, 1e-150]),
    ('1,1-1e-15,1e-15', [1, 1 - 1e-15, 1e-15, 1e-15, 1e-15, 0.5]),
]


def mat_cluster():
    rng = random.Random(8888)
    out = []
    for (m, n) in ((4, 4), (6, 4), (6, 6)):
        for k in range(100):
            plab, s = CLUSTER_S[k % len(CLUSTER_S)]
            s = [Fraction(x) for x in s[:n]]
            Q1 = _householder_Q(rng, m, min(m, 3))
            Q2 = _householder_Q(rng, n, min(n, 3))
            A = [[float(sum(Q1[i][l] * s[l] * Q2[j][l] for l in range(n))) for j in range(n)]
                 for i in range(m)]
            out.append(('cluster', 'cluster %dx%d s=(%s) #%d' % (m, n, plab, k), A))
    return out


NAN = f_of(0x7FF8000000000000)
INF = math.inf


def mat_nonfinite():
    """Extra class (not in the original spec list): A has no SVD; a correct svd refuses (< 0)."""
    out = []

    def add(label, rows, cols, bl):
        out.append(('nonfinite', 'nonfinite ' + label, ('bits', rows, cols, bl)))

    QN, NN, SN, PI, NI = 0x7FF8000000000000, 0xFFF8000000000000, 0x7FF4000000000001, INF_BITS, 0xFFF0000000000000
    one, two, three = bits_of(1.0), bits_of(2.0), bits_of(3.0)
    add('all-NaN 2x2', 2, 2, [QN] * 4)
    add('[[NaN,0],[0,2]]', 2, 2, [QN, 0, 0, two])
    add('[[+Inf,0],[0,2]]', 2, 2, [PI, 0, 0, two])
    add('[[-Inf,0],[0,2]]', 2, 2, [NI, 0, 0, two])
    add('[[3,NaN],[0,2]]', 2, 2, [three, QN, 0, two])
    add('[[1,2],[3,+Inf]]', 2, 2, [one, two, three, PI])
    add('[[3,0],[0,NaN]]', 2, 2, [three, 0, 0, QN])
    add('[[3,0],[0,-NaN]]', 2, 2, [three, 0, 0, NN])
    add('[[3,0],[0,sNaN]]', 2, 2, [three, 0, 0, SN])
    add('[[0,0],[0,+Inf]]', 2, 2, [0, 0, 0, PI])
    add('3x2 NaN last', 3, 2, [one, two, three, one, two, QN])
    add('3x2 Inf first', 3, 2, [PI, two, three, one, two, three])
    add('3x3 NaN center', 3, 3, [one, two, three, two, QN, one, three, one, two])
    add('5x4 W54 with -Inf at (2,1)', 5, 4, W54_BITS[:9] + [NI] + W54_BITS[10:])
    add('4x1 NaN', 4, 1, [one, QN, two, three])
    add('1x1 Inf', 1, 1, [PI])
    add('2x2 DBL_MAX + NaN', 2, 2, [0x7FEFFFFFFFFFFFFF, 0x7FEFFFFFFFFFFFFF, QN, 0x7FEFFFFFFFFFFFFF])
    add('2x2 subnormal + Inf', 2, 2, [1, PI, 1, 1])
    return out


CLASSES = [
    ('fam', mat_fam), ('rand2', mat_rand2), ('sqdef', mat_sqdef), ('talldef', mat_talldef),
    ('outer', mat_outer), ('wit', mat_wit), ('randwell', mat_randwell), ('graded', mat_graded),
    ('extreme', mat_extreme), ('rankdef', mat_rankdef), ('cluster', mat_cluster),
    ('nonfinite', mat_nonfinite),
]


def build_corpus():
    items = []
    for name, fn in CLASSES:
        for cls, label, A in fn():
            if isinstance(A, tuple) and A[0] == 'bits':
                _, m, n, bl = A
            else:
                m, n = len(A), len(A[0])
                bl = [bits_of(float(A[i][j])) for i in range(m) for j in range(n)]
            assert m >= n >= 1 and len(bl) == m * n
            items.append({'class': cls, 'label': label, 'rows': m, 'cols': n, 'bits': bl})
    return items


# ----------------------------------------------------------------- oracle
def _bareiss_rank_det(M):
    """Integer matrix (list of lists, m x n). Returns (rank, det or None). det only if square."""
    M = [row[:] for row in M]
    m, n = len(M), len(M[0])
    prev = 1
    r = 0
    sign = 1
    for c in range(n):
        piv = None
        for i in range(r, m):
            if M[i][c] != 0:
                piv = i
                break
        if piv is None:
            continue
        if piv != r:
            M[r], M[piv] = M[piv], M[r]
            sign = -sign
        prc = M[r][c]
        for i in range(r + 1, m):
            mic = M[i][c]
            row_i = M[i]
            row_r = M[r]
            for j in range(c + 1, n):
                row_i[j] = (row_i[j] * prc - mic * row_r[j]) // prev
            row_i[c] = 0
        prev = prc
        r += 1
        if r == m:
            break
    det = None
    if m == n:
        det = 0 if r < n else sign * M[n - 1][n - 1]
    return r, det


def _certify(f, rad):
    """Round Fraction f >= 0 to double bits if the interval f +- rad rounds to one double."""
    b = round_frac_bits(f)
    lo = f - rad
    if lo < 0:
        lo = Fraction(0)
    if round_frac_bits(lo) != b or round_frac_bits(f + rad) != b:
        return None
    return b


def _sq_frac(F):
    return sum(x * x for x in F)


def oracle_one(item):
    m, n, bl = item['rows'], item['cols'], item['bits']
    for b in bl:
        if (b & INF_BITS) == INF_BITS:
            return {'reject': True}
    F = [Fraction(f_of(b)) for b in bl]          # exact, row-major
    col = lambda j: [F[i * n + j] for i in range(m)]
    if all(x == 0 for x in F):
        return {'reject': False, 'sigma': [Fraction(0)] * n, 'bits': [0] * n, 'rel_ok': [True] * n,
                'rank': 0, 'method': 'zero', 'prec': 0}
    if n == 1:
        lam = [_sq_frac(F)]
        return _from_lambdas_exact(lam, n, 'n1', [lam[0]], rank=1)
    if n == 2:
        c0, c1 = col(0), col(1)
        g11, g22, g12 = _sq_frac(c0), _sq_frac(c1), sum(a * b for a, b in zip(c0, c1))
        det = g11 * g22 - g12 * g12
        disc = (g11 - g22) ** 2 + 4 * g12 * g12
        tr = g11 + g22
        P = 256
        while True:
            mpmath.mp.prec = P
            to = lambda q: mpmath.mpf(q.numerator) / q.denominator
            lmax = (to(tr) + mpmath.sqrt(to(disc))) / 2
            lmin = to(det) / lmax if det != 0 else mpmath.mpf(0)
            s1, s2 = mpmath.sqrt(lmax), mpmath.sqrt(lmin)
            fs = [mpf_to_frac(s1), mpf_to_frac(s2)]
            out_bits, ok = [], []
            for f in fs:
                if f == 0:
                    out_bits.append(0)
                    ok.append(True)
                    continue
                b = _certify(f, f / (Fraction(2) ** (P - 4)))
                out_bits.append(b)
                ok.append(b is not None)
            if all(ok) or P >= 8192:
                for k in range(2):
                    if out_bits[k] is None:
                        out_bits[k] = round_frac_bits(fs[k])
                return {'reject': False, 'sigma': fs, 'bits': out_bits, 'rel_ok': ok,
                        'rank': 2 if det != 0 else 1, 'method': 'n2-closed', 'prec': P}
            P *= 2
    # n >= 3
    # integer scaling: every entry is k * 2^-K
    K = 0
    for x in F:
        if x != 0:
            d = x.denominator.bit_length() - 1
            K = max(K, d)
    Mi = [[int(F[i * n + j] * (1 << K)) for j in range(n)] for i in range(m)]
    rank, detI = _bareiss_rank_det(Mi)
    nz = [abs(x) for x in F if x != 0]
    rq = max(nz) / min(nz)
    spread = float(rq.numerator.bit_length() - rq.denominator.bit_length())
    P = int(max(192, 140 + min(spread, 4000)))
    fro2 = _sq_frac(F)
    P_CAP = 24000
    while True:
        P2 = P + 64
        sa = _svd_vals(F, m, n, P)
        sb = _svd_vals(F, m, n, P2)
        mpmath.mp.prec = P2
        s1 = sb[0]
        need = 140
        if rank > 0 and sb[rank - 1] > 0:
            need = 140 + math.ceil(float(mpmath.log(s1 / sb[rank - 1], 2)))
        elif rank > 0:
            need = P + 512
        if need > P and P < P_CAP:
            P = min(P_CAP, max(need + 16, P + 64))
            continue
        # consistency of the a-priori backward-error bound
        bound_a = s1 * mpmath.mpf(2) ** (-P + 20)
        consistent = all(abs(sa[i] - sb[i]) <= bound_a for i in range(rank))
        rad = mpf_to_frac(s1 * mpmath.mpf(2) ** (-P2 + 20))
        fs, out_bits, ok = [], [], []
        for i in range(n):
            if i >= rank:
                fs.append(Fraction(0))
                out_bits.append(0)
                ok.append(True)
                continue
            f = mpf_to_frac(sb[i])
            b = _certify(f, rad) if consistent else None
            fs.append(f)
            out_bits.append(b if b is not None else round_frac_bits(f))
            ok.append(b is not None)
        if (all(ok) and consistent) or P >= P_CAP:
            # independent sanity checks
            chk = {}
            mpmath.mp.prec = P2
            ssum = sum((sb[i] ** 2 for i in range(rank)), mpmath.mpf(0))
            fro = mpmath.mpf(fro2.numerator) / fro2.denominator
            chk['fro_rel'] = float(abs(ssum - fro) / fro)
            if m == n and rank == n:
                detF = Fraction(abs(detI), 1 << (K * n))
                prod = mpmath.fprod(sb[:n])
                dd = mpmath.mpf(detF.numerator) / detF.denominator
                chk['det_rel'] = float(abs(prod - dd) / dd)
            if m == n and rank < n:
                chk['det_zero'] = (detI == 0)
            return {'reject': False, 'sigma': fs, 'bits': out_bits, 'rel_ok': ok, 'rank': rank,
                    'method': 'mp-svd', 'prec': P2, 'check': chk, 'consistent': consistent}
        P = min(P_CAP, int(P * 1.5))


def _svd_vals(F, m, n, P):
    mpmath.mp.prec = P
    A = mpmath.matrix(m, n)
    for i in range(m):
        for j in range(n):
            x = F[i * n + j]
            A[i, j] = mpmath.mpf(x.numerator) / x.denominator   # exact: dyadic, |num| < 2^53
    s = mpmath.svd_r(A, compute_uv=False)
    v = sorted((abs(s[i]) for i in range(n)), reverse=True)
    return v


def _from_lambdas_exact(lams, n, method, _unused, rank):
    P = 256
    while True:
        mpmath.mp.prec = P
        fs, bits, ok = [], [], []
        for lam in lams:
            s = mpmath.sqrt(mpmath.mpf(lam.numerator) / lam.denominator)
            f = mpf_to_frac(s)
            b = _certify(f, f / (Fraction(2) ** (P - 4)))
            fs.append(f)
            bits.append(b)
            ok.append(b is not None)
        if all(ok) or P >= 8192:
            bits = [b if b is not None else round_frac_bits(f) for b, f in zip(bits, fs)]
            return {'reject': False, 'sigma': fs, 'bits': bits, 'rel_ok': ok, 'rank': rank,
                    'method': method, 'prec': P}
        P *= 2


def oracle_worker(args):
    idx, item = args
    r = oracle_one(item)
    if not r['reject']:
        r['hp'] = [frac_m64e(f) for f in r['sigma']]
        del r['sigma']
    return idx, r


# ----------------------------------------------------------------- verification
def verify(items, orc, log):
    nbad = 0
    by_label = {it['label']: k for k, it in enumerate(items) if it['class'] == 'wit'}
    for lab, want in EXPECT_BITS.items():
        k = by_label[lab]
        got = orc[k]['bits']
        ok = got == want
        nbad += (not ok)
        log('  %-4s %s  oracle %s  want %s' % (lab, 'ok ' if ok else 'BAD',
                                               ' '.join('%016x' % b for b in got),
                                               ' '.join('%016x' % b for b in want)))
    for lab, want in EXPECT_DEC.items():
        for sc_lab in [lab] + ['%s*2^%d' % (lab, s) for s in (-827, -327, 173)]:
            k = by_label[sc_lab]
            sc = 0 if sc_lab == lab else int(sc_lab.split('^')[1])
            got = [f_of(b) for b in orc[k]['bits']]
            wantf = [math.ldexp(float(x), sc) for x in want]
            ok = got == wantf
            nbad += (not ok)
            log('  %-12s %s  oracle %s' % (sc_lab, 'ok ' if ok else 'BAD', ' '.join(repr(x) for x in got)))
    # fam rows with t in the A-table must agree with A1..A6 (same matrices)
    # numpy cross-check on 200 random matrices
    rng = random.Random(55)
    cand = [k for k, it in enumerate(items) if not orc[k]['reject']
            and it['class'] in ('randwell', 'sqdef', 'talldef', 'outer', 'cluster', 'rankdef', 'rand2', 'graded')]
    pick = sorted(rng.sample(cand, 200))
    worst = 0.0
    for k in pick:
        it = items[k]
        A = np.array([f_of(b) for b in it['bits']]).reshape(it['rows'], it['cols'])
        s_np = np.linalg.svd(A, compute_uv=False)
        s_or = np.array([f_of(b) for b in orc[k]['bits']])
        if not np.all(np.isfinite(s_or)) or s_or[0] == 0:
            continue
        err = float(np.max(np.abs(s_np - s_or)) / (2.0 ** -52 * s_or[0]))
        worst = max(worst, err)
    ok = worst <= 10.0
    nbad += (not ok)
    log('  numpy cross-check: 200 matrices, worst max|s_np - s_oracle| = %.3f u*s1  %s'
        % (worst, 'ok' if ok else 'BAD'))
    return nbad


def main():
    ap = argparse.ArgumentParser(description='Build the svdh corpus and its exact oracle.')
    ap.add_argument('--out', default=WORK, metavar='DIR',
                    help='output directory (default $SVDH_WORK, else <repo>/build/svdh)')
    ap.add_argument('--procs', type=procs_arg, default=os.cpu_count() or 1, metavar='N',
                    help='oracle processes (default: every CPU)')
    a = ap.parse_args()
    check_versions()
    blas_setup()
    make_outdir('corpus.py', a.out)
    term_as_exit()
    try:
        return _build(a.out, a.procs)
    except BaseException:
        discard_tmp(a.out)
        raise


def _build(outdir, procs):
    t0 = time.time()
    items = build_corpus()
    N = len(items)
    print('corpus: %d matrices (%.1fs)' % (N, time.time() - t0))
    counts = {}
    for it in items:
        counts[it['class']] = counts.get(it['class'], 0) + 1
    for c, k in counts.items():
        print('  %-10s %6d' % (c, k))
    with open(tmp_path(outdir, 'corpus.bin'), 'wb') as fh:
        fh.write(struct.pack('<Q', N))
        for it in items:
            fh.write(struct.pack('<QQ', it['rows'], it['cols']))
            fh.write(struct.pack('<%dQ' % len(it['bits']), *it['bits']))
    meta = [{'id': k, 'class': it['class'], 'label': it['label'], 'rows': it['rows'], 'cols': it['cols']}
            for k, it in enumerate(items)]
    with open(tmp_path(outdir, 'corpus_meta.json'), 'w') as fh:
        json.dump(meta, fh, indent=0)
    # oracle: biggest jobs first for load balance
    order = sorted(range(N), key=lambda k: -(items[k]['rows'] * items[k]['cols'] ** 2))
    t1 = time.time()
    orc = [None] * N
    with mproc.Pool(procs) as pool:
        for idx, r in pool.imap_unordered(oracle_worker, ((k, items[k]) for k in order), chunksize=4):
            orc[idx] = r
    print('oracle: %.1fs' % (time.time() - t1))
    # stats
    nrel = sum(1 for r in orc if not r['reject'] for x in r['rel_ok'] if not x)
    ninc = sum(1 for r in orc if not r['reject'] and not r.get('consistent', True))
    maxprec = max((r['prec'] for r in orc if not r['reject']), default=0)
    worst_fro = max((r.get('check', {}).get('fro_rel', 0.0) for r in orc if not r['reject']), default=0)
    worst_det = max((r.get('check', {}).get('det_rel', 0.0) for r in orc if not r['reject']), default=0)
    detz_bad = sum(1 for r in orc if not r['reject'] and r.get('check', {}).get('det_zero') is False)
    print('oracle: sigma not certified (rel_ok false): %d; inconsistent mp runs: %d; max prec %d bits'
          % (nrel, ninc, maxprec))
    print('oracle: worst |sum s^2 - ||A||_F^2|/||A||_F^2 = %.3g; worst |prod s - |det||/|det| = %.3g; '
          'rank<n with det!=0: %d' % (worst_fro, worst_det, detz_bad))
    lines = []
    nbad = verify(items, orc, lambda s: (print(s), lines.append(s)))
    print('verification: %s' % ('ALL OK' if nbad == 0 else '%d FAILED' % nbad))
    out = []
    for k, r in enumerate(orc):
        if r['reject']:
            out.append({'id': k, 'reject': True})
            continue
        out.append({'id': k, 'reject': False, 'sigma_bits': ['%016x' % b for b in r['bits']],
                    'hp': [list(x) for x in r['hp']], 'rel_ok': r['rel_ok'], 'rank': r['rank'],
                    'method': r['method'], 'prec': r['prec']})
    info = {'count': N, 'classes': counts, 'uncertified_sigma': nrel, 'inconsistent': ninc,
            'max_prec_bits': maxprec, 'worst_fro_rel': worst_fro, 'worst_det_rel': worst_det,
            'verification_failures': nbad, 'verification_log': lines}
    with open(tmp_path(outdir, 'oracle.json'), 'w') as fh:
        json.dump({'info': info, 'matrices': out}, fh)
    if nbad:
        for name in SET_FILES:
            os.replace(tmp_path(outdir, name), os.path.join(outdir, name + '.failed'))
        print('corpus.py: %d self-check(s) FAILED: wrote corpus.bin.failed, corpus_meta.json.failed '
              'and oracle.json.failed to %s; the set there (if any) is unchanged' % (nbad, outdir),
              file=sys.stderr)
        return 1
    publish(outdir)
    print('wrote corpus.bin, corpus_meta.json, oracle.json to %s in %.1fs total' % (outdir, time.time() - t0))
    return 0


if __name__ == '__main__':
    sys.exit(main())
