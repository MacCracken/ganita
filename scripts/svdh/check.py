#!/usr/bin/env python3
"""Score a driver results file against the exact oracle.

usage: check.py [--corpus corpus.bin] [--meta corpus_meta.json] [--oracle oracle.json]
                [--baseline results_base.bin] [--json out.json] [--top N] [--sub] results.bin
       check.py results.bin --diff other.bin [--corpus corpus.bin] [--meta corpus_meta.json] [--top N]
corpus / meta / oracle default to $SVDH_WORK (default <repo>/build/svdh).  The meta file must
list the corpus's matrices in order (its ids and shapes are checked).  The oracle must have one
entry per matrix with as many sigma as columns, reject exactly the matrices with a NaN or
infinite entry, have sigma^2 that sum to ||A||_F^2, and record the meta file's class counts where
it records any (Oracle.fit).  Binary files must be whole 8-byte words.  A results file is bound
to the corpus only by its length: the results of another corpus with the same shapes in the same
order are scored (and fail), not refused.  --diff takes no --oracle, --baseline, --json or --sub.
Exit status: 0; with --diff, 0 when the two results files are bit-identical and 1 when they differ
(as cmp); 2 when an input is missing or does not fit, or the arguments are wrong.

Metrics (u = 2^-52; hat = exact oracle value, hp = 64-bit significand of the exact sigma):
  sig_nw    max_i |s_i - shat_i| / (u*shat_1 + 2^-1074)            [u units]
  sig_rel   max over rel_ok i with shat_i > 0 of |s_i - shat_i| / ulp(shat_i)   [ulps]
  desc      s descending, non-negative, no NaN
  vt_orth   max |Vt Vt^T - I| / u
  u_orth    max |U_J^T U_J - I| / u over the columns J whose returned s_j >= 2^-1022
  u0col     every column j with returned s_j == 0 is all-zero in U (ganita's convention)
  recon     max_ij |A - U diag(s) Vt|_ij / (u*shat_1 + 2^-1074)  (n/a when a returned s is not
            finite and the exact s_1 itself rounds to +inf)
  vo        values-only status and sigma bits identical to the full path
All arithmetic in numpy longdouble (x87 80-bit: 64-bit significand, 15-bit exponent), so the
metric itself carries < 2^-10 u of error.  A returned exact match (same bits as the correctly
rounded oracle) counts as error 0 even when that double is +inf.

PASS (status 0 matrices): sig_nw <= 4*max(1, sqrt(mn)/2), u_orth <= 256, vt_orth <= 256,
  recon <= 16*max(1, sqrt(mn)) (or n/a as above), desc.   class `nonfinite`: PASS = both
  statuses < 0.

The scoring needs a numpy longdouble with a 64-bit (or wider) significand and a wider exponent
than double: x87 80-bit (x86_64 Linux) or binary128 (aarch64 Linux).  Elsewhere it refuses to run.
This module also holds the helpers the other scoring tools share (file checks, the runner of
an aarch64 driver).
"""
import argparse
import json
import math
import os
import platform
import re
import sys
import traceback

try:
    import numpy as np
except ImportError as _e:
    print('svdh: %s cannot import %s: pip install -r scripts/svdh/requirements.txt, or use another '
          'python (PY=... for the shell scripts)' % (sys.executable, _e.name), file=sys.stderr)
    sys.exit(2)

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
WORK = os.path.abspath(os.environ.get('SVDH_WORK') or os.path.join(REPO, 'build', 'svdh'))
LD = np.longdouble
U = LD(2.0) ** -52
TINY = LD(2.0) ** -1074
DBL_MIN = 2.0 ** -1022
POISON = 0x7FF4000000000BAD
INF_BITS = 0x7FF0000000000000
METRICS = ['sig_nw', 'sig_rel', 'u_orth', 'vt_orth', 'recon']
CLASS_ORDER = ['fam', 'rand2', 'sqdef', 'talldef', 'outer', 'wit', 'randwell', 'graded',
               'extreme', 'rankdef', 'cluster', 'nonfinite']


def subkey(cls, label):
    """Sub-class key derived from the corpus label (shape / edit / spread, no sample index)."""
    if cls == 'wit':
        return 'wit ' + label
    if cls == 'nonfinite':
        return 'nonfinite'
    if cls == 'fam':
        return label.split(' e=')[0]
    s = re.sub(r' #\d+.*$', '', label)
    s = re.sub(r' (r|c)=\d+$', '', s)
    s = re.sub(r' span=2\^-\d+', '', s)
    s = re.sub(r' s=\(.*\)$', '', s)
    s = re.sub(r' (dup-col|ulp-col) c\d+=c\d+.*$', r' \1', s)
    return s


def die(msg):
    """Exit with status 2 and 'program: msg' on stderr (status 1 is check.py --diff's 'differ')."""
    print('%s: %s' % (os.path.basename(sys.argv[0] or 'svdh'), msg), file=sys.stderr)
    sys.exit(2)


def cut(label, width):
    """label in at most `width` characters, ending in '...' where it was cut."""
    return label if len(label) <= width else label[:width - 3] + '...'


def nonneg_arg(s):
    """argparse type of an integer >= 0 (--top, --show)."""
    try:
        v = int(s)
    except ValueError:
        raise argparse.ArgumentTypeError('%r is not an integer' % s)
    if v < 0:
        raise argparse.ArgumentTypeError('must be at least 0')
    return v


def need_file(path, what, hint=''):
    """Exit with a message when path is not an existing file."""
    if not os.path.isfile(path):
        die('%s %s %s%s' % (what, path, 'is not a file' if os.path.exists(path) else 'not found', hint))
    return path


def read_words(path, what, hint='', dtype='<u8'):
    """The 8-byte words of a binary file (corpus, results, times, rcp).  Exits with a message when
    the file is missing or cannot be read, or its size is not a whole number of words, which
    np.fromfile would otherwise accept by dropping the partial word at the end."""
    need_file(path, what, hint)
    try:
        size = os.path.getsize(path)
        if size % 8:
            die('%s %s has %d bytes, not a whole number of 8-byte words' % (what, path, size))
        return np.fromfile(path, dtype=dtype)
    except OSError as e:
        die('cannot read %s %s: %s' % (what, path, e.strerror or e))


def read_json(path, what):
    """The JSON value in a file; exits with a message when it cannot be read or is not JSON."""
    need_file(path, what)
    try:
        with open(path) as fh:
            return json.load(fh)
    except OSError as e:
        die('cannot read %s %s: %s' % (what, path, e.strerror or e))
    except ValueError as e:
        die('%s %s is not JSON: %s' % (what, path, e))


LABEL_RE = re.compile(r'[A-Za-z0-9._+-]+')


def check_label(label):
    """Exit with a message unless label is usable in file names (env.sh's svdh_check_label):
    letters, digits, '.', '_', '+' and '-' only, and not starting with '-'."""
    if not LABEL_RE.fullmatch(label) or label.startswith('-'):
        die("label '%s' must be non-empty, must not start with '-', and may use only letters, digits, "
            "'.', '_', '+' and '-'" % label)
    return label


def require_longdouble():
    """Exit unless numpy's longdouble carries at least a 64-bit significand and a wider exponent
    range than double, which the metrics (and an exact sigma above DBL_MAX) need."""
    fi = np.finfo(np.longdouble)
    if fi.nmant < 63 or fi.maxexp <= 1024:
        die('numpy longdouble on this host has a %d-bit significand and max exponent %d; the svdh '
            'metrics need x87 80-bit or binary128 (x86_64 or aarch64 Linux)' % (fi.nmant + 1, fi.maxexp))


def runner_for(binary):
    """The command prefix that runs a driver binary on this machine: ['qemu-aarch64'] for an
    aarch64 ELF on a machine that is not aarch64 (as run.sh's aarch64 mode), else []."""
    try:
        with open(binary, 'rb') as fh:
            h = fh.read(20)
    except OSError:
        return []
    if (len(h) == 20 and h[:4] == b'\x7fELF' and int.from_bytes(h[18:20], 'little') == 183
            and platform.machine() not in ('aarch64', 'arm64')):
        return ['qemu-aarch64']
    return []


def load_corpus(path):
    w = read_words(path, 'corpus', ' (corpus.py, adv/gen.py, hunts/gen.py and hunts/mkwit.py write them)')
    if len(w) == 0:
        die('corpus %s is empty' % path)
    N = int(w[0])
    if N > len(w):
        die('%s is not a corpus file: it would hold %d matrices in %d words' % (path, N, len(w)))
    rows = np.empty(N, np.int64)
    cols = np.empty(N, np.int64)
    off = np.empty(N, np.int64)
    p = 1
    for k in range(N):
        if p + 2 > len(w):
            die('corpus %s is truncated at matrix %d of %d' % (path, k, N))
        r, c = int(w[p]), int(w[p + 1])
        if not (r >= c >= 1) or p + 2 + r * c > len(w):
            die('corpus %s: matrix %d has a bad shape %dx%d or is truncated' % (path, k, r, c))
        rows[k] = r
        cols[k] = c
        off[k] = p + 2
        p += 2 + r * c
    if p != len(w):
        die('corpus %s has %d words, its %d matrices take %d' % (path, len(w), N, p))
    return w, rows, cols, off


def load_meta(path, rows, cols):
    """corpus_meta.json of the corpus whose shapes are rows, cols (load_corpus): a list of one
    {id, class, label, rows, cols} per matrix, in corpus order, with class and label strings and
    id, rows and cols integers.  Exits with a message unless every entry is such and its id is its
    index and its rows and cols are the corpus matrix's, so that the meta file of another set (or
    a reordered one) is refused rather than mislabelling the classes."""
    meta = read_json(path, 'meta file')
    if not isinstance(meta, list) or not all(isinstance(m, dict) for m in meta):
        die('%s is not a corpus_meta.json (a list of {id, class, label, rows, cols})' % path)
    N = len(rows)
    if len(meta) != N:
        die('meta file %s has %d entries, the corpus %d matrices' % (path, len(meta), N))
    for k, m in enumerate(meta):
        bad = [f for f in ('class', 'label') if not isinstance(m.get(f), str)]
        bad += [f for f in ('id', 'rows', 'cols') if type(m.get(f)) is not int]    # bool is not one
        if bad:
            die('meta file %s: entry %d: %s missing or of the wrong type (class and label must be '
                'strings; id, rows and cols integers)' % (path, k, ', '.join(bad)))
        if m['id'] != k or m['rows'] != int(rows[k]) or m['cols'] != int(cols[k]):
            die('meta file %s does not fit the corpus: entry %d has id %d and shape %dx%d, matrix %d of '
                'the corpus is %dx%d (a meta file of another set?)'
                % (path, k, m['id'], m['rows'], m['cols'], k, rows[k], cols[k]))
    return meta


def results_offsets(rows, cols):
    sz = 1 + cols + rows * cols + cols * cols + 1 + cols
    off = np.zeros(len(rows), np.int64)
    off[1:] = np.cumsum(sz)[:-1]
    return off, int(sz.sum())


def load_results(path, total, what='results file'):
    """A driver results file as u64 words; exits unless it is exactly `total` words long."""
    w = read_words(path, what)
    if len(w) != total:
        die('%s %s has %d words, expected %d (results of another corpus, or a driver that failed?)'
            % (what, path, len(w), total))
    return w


def to_ld_hp(hp):
    m = np.array([h[0] for h in hp], dtype=object)
    e = np.array([h[1] for h in hp], dtype=np.int64)
    mh = np.array([int(x) >> 32 for x in m], dtype=np.float64).astype(LD)
    ml = np.array([int(x) & 0xFFFFFFFF for x in m], dtype=np.float64).astype(LD)
    return np.ldexp(mh * LD(4294967296.0) + ml, e.astype(np.int32))


FRO_TOL = LD(2.0) ** -24          # Oracle.fit: |sum sigma^2 - ||A||_F^2| <= FRO_TOL * ||A||_F^2
EXP_BITS = np.uint64(0x7FF0000000000000)


class Oracle:
    """oracle.json of a corpus of N matrices.  With meta (load_meta), the class counts the oracle
    records in its info (corpus.py and adv/gen.py write them) must be the meta file's.  fit()
    binds it to the corpus itself."""

    def __init__(self, path, N, meta=None):
        self.path = path
        self.fitted = False
        o = read_json(path, 'oracle')
        mats = o.get('matrices') if isinstance(o, dict) else None
        if not isinstance(mats, list) or not all(isinstance(m, dict) and 'reject' in m for m in mats):
            die('%s is not an oracle.json (no "matrices" list of {id, reject, ...})' % path)
        if len(mats) != N:
            die('oracle %s has %d matrices, the corpus %d' % (path, len(mats), N))
        self.matrices = mats            # the entries as read (method, prec, ... for report.py, orcstat.py)
        self.reject = np.array([bool(m['reject']) for m in mats], dtype=bool)
        self.bits = [None] * N
        self.hp = [None] * N
        self.relok = [None] * N
        self.rank = [None] * N
        for k, m in enumerate(mats):
            if m['reject']:
                continue
            try:
                self.bits[k] = np.array([int(b, 16) for b in m['sigma_bits']], dtype=np.uint64)
                self.hp[k] = to_ld_hp(m['hp'])
                self.relok[k] = np.array(m['rel_ok'], dtype=bool)
                self.rank[k] = int(m['rank'])
            except (KeyError, TypeError, ValueError, IndexError, OverflowError) as e:
                die('oracle %s: matrix %d is malformed (%s: %s)' % (path, k, type(e).__name__, e))
        self.info = o.get('info', {})
        if not isinstance(self.info, dict):
            die('oracle %s: "info" is not an object' % path)
        if 'count' in self.info and self.info['count'] != N:
            die('oracle %s records %s matrices in its info, the corpus has %d' % (path, self.info['count'], N))
        if meta is not None and isinstance(self.info.get('classes'), dict):
            have = {}
            for m in meta:
                have[m['class']] = have.get(m['class'], 0) + 1
            if have != self.info['classes']:
                die('oracle %s was made for the classes %s, the meta file has %s (files of different sets?)'
                    % (path, sorted(self.info['classes'].items()), sorted(have.items())))
        if self.info.get('verification_failures'):
            print('%s: warning: oracle %s failed %s of corpus.py\'s self-checks (see its '
                  'info.verification_log); its scores cannot be trusted'
                  % (os.path.basename(sys.argv[0] or 'svdh'), path, self.info['verification_failures']),
                  file=sys.stderr)

    def fit(self, cw, crow, ccol, coff):
        """Exit with a message unless this oracle belongs to the corpus (load_corpus): one sigma per
        column, `reject` exactly on the matrices with a NaN or infinite entry, and, where numpy's
        longdouble is wide enough (the scorers need it anyway), the sum of the exact sigma^2 equal
        to ||A||_F^2 to FRO_TOL.  That refuses an oracle of another set of the same shapes, unless
        its matrices happen to have the same Frobenius norms.  Checks once per Oracle."""
        if self.fitted:
            return
        fi = np.finfo(LD)
        wide = fi.nmant >= 63 and fi.maxexp > 1024
        for k in range(len(crow)):
            m, n, o = int(crow[k]), int(ccol[k]), int(coff[k])
            a = cw[o:o + m * n]
            nonfin = bool(np.any((a & EXP_BITS) == EXP_BITS))
            if bool(self.reject[k]) != nonfin:
                die('oracle %s does not fit the corpus: matrix %d %s, and the oracle %s it (an oracle of '
                    'another set?)' % (self.path, k, 'has a NaN or infinite entry' if nonfin else 'is finite',
                                       'accepts' if nonfin else 'rejects'))
            if nonfin:
                continue
            if not (len(self.bits[k]) == len(self.hp[k]) == len(self.relok[k]) == n):
                die('oracle %s does not fit the corpus: matrix %d has %d columns, the oracle %d sigma'
                    % (self.path, k, n, len(self.bits[k])))
            if wide:
                x = a.view(np.float64).astype(LD)
                fro = np.sum(x * x)
                ss = np.sum(self.hp[k] * self.hp[k])
                if not abs(ss - fro) <= FRO_TOL * fro:
                    die('oracle %s does not fit the corpus: matrix %d has ||A||_F^2 = %s, its oracle '
                        'sigma^2 sum to %s (an oracle of another set?)'
                        % (self.path, k, np.format_float_scientific(fro, precision=6),
                           np.format_float_scientific(ss, precision=6)))
        self.fitted = True


def ulp_of(x):
    """ulp of the double nearest x (x >= 0 longdouble array): 2^(floor(log2 x)-52), >= 2^-1074."""
    f, e = np.frexp(x)
    u = np.ldexp(np.ones_like(x), (e - 53).astype(np.int32))
    return np.maximum(u, TINY)


def nan_to_inf(a):
    a = np.array(a, dtype=np.float64)
    a[np.isnan(a)] = np.inf
    return a


def score(cw, crow, ccol, coff, orc, res_path, what='results file'):
    """Compute per-matrix metrics for one results file."""
    require_longdouble()
    N = len(crow)
    roff, total = results_offsets(crow, ccol)
    rw = load_results(res_path, total, what)
    orc.fit(cw, crow, ccol, coff)
    out = {
        'status': np.zeros(N, np.int64), 'status_vo': np.zeros(N, np.int64),
        'vo_match': np.zeros(N, bool), 'desc': np.ones(N, bool), 'u0col': np.ones(N, bool),
        'untouched': np.zeros(N, bool), 'pass': np.zeros(N, bool), 'recon_na': np.zeros(N, bool),
    }
    for m in METRICS:
        out[m] = np.full(N, np.nan)
    out['S_bits'] = [None] * N
    out['U_bits'] = [None] * N
    out['V_bits'] = [None] * N
    # status / raw pieces
    shapes = {}
    for k in range(N):
        m, n, o = int(crow[k]), int(ccol[k]), int(roff[k])
        st = int(np.int64(rw[o].astype(np.int64)))
        S = rw[o + 1:o + 1 + n]
        Ub = rw[o + 1 + n:o + 1 + n + m * n]
        Vb = rw[o + 1 + n + m * n:o + 1 + n + m * n + n * n]
        o2 = o + 1 + n + m * n + n * n
        st2 = int(np.int64(rw[o2].astype(np.int64)))
        S2 = rw[o2 + 1:o2 + 1 + n]
        out['status'][k] = st
        out['status_vo'][k] = st2
        out['vo_match'][k] = (st == st2) and bool(np.all(S == S2))
        out['S_bits'][k] = S
        out['U_bits'][k] = Ub
        out['V_bits'][k] = Vb
        out['untouched'][k] = bool(np.all(S == POISON) and np.all(Ub == POISON) and np.all(Vb == POISON)
                                   and np.all(S2 == POISON))
        if orc.reject[k]:
            out['pass'][k] = (st < 0) and (st2 < 0)
            continue
        if st != 0:
            continue
        shapes.setdefault((m, n), []).append(k)
    for (m, n), ks in shapes.items():
        ks = np.array(ks)
        G = len(ks)
        A = np.stack([cw[coff[k]:coff[k] + m * n] for k in ks]).view(np.float64).reshape(G, m, n)
        S = np.stack([out['S_bits'][k] for k in ks])
        Sf = S.view(np.float64)
        Uf = np.stack([out['U_bits'][k] for k in ks]).view(np.float64).reshape(G, m, n)
        Vf = np.stack([out['V_bits'][k] for k in ks]).view(np.float64).reshape(G, n, n)
        Sh = np.stack([orc.hp[k] for k in ks])                  # LD exact
        Shb = np.stack([orc.bits[k] for k in ks])
        RO = np.stack([orc.relok[k] for k in ks])
        SL = Sf.astype(LD)
        with np.errstate(all='ignore'):
            d = np.abs(SL - Sh)
            d[S == Shb] = 0
            denom = U * Sh[:, 0] + TINY
            nw = np.max(d, axis=1) / denom
            # relative error in ulps
            ulp = ulp_of(Sh)
            rel = d / ulp
            relmask = RO & (Sh > 0)
            rel_m = np.where(relmask, rel, LD(-1))
            relmax = np.max(rel_m, axis=1)
            relmax = np.where(relmax < 0, LD(np.nan), relmax)
            relmax = np.where(np.any(relmask & np.isnan(rel), axis=1), LD(np.inf), relmax)
            # descending, non-negative, no NaN
            desc = np.all(~np.isnan(Sf), axis=1) & np.all(Sf >= 0, axis=1)
            if n > 1:
                desc &= np.all(Sf[:, :-1] >= Sf[:, 1:], axis=1)
            # Vt orthonormality
            VL = Vf.astype(LD)
            I_n = np.eye(n, dtype=LD)
            vv = np.matmul(VL, np.swapaxes(VL, 1, 2)) - I_n
            vt_orth = np.max(np.abs(vv).reshape(G, -1), axis=1) / U
            # U orthonormality over normal sigma columns
            UL = Uf.astype(LD)
            uu = np.matmul(np.swapaxes(UL, 1, 2), UL) - I_n
            J = Sf >= DBL_MIN
            M = J[:, :, None] & J[:, None, :]
            uu = np.where(M, np.abs(uu), LD(0))
            uu = np.where(M & np.isnan(uu), LD(np.inf), uu)
            u_orth = np.max(uu.reshape(G, -1), axis=1) / U
            # zero-sigma columns of U must be zero
            Z = (Sf == 0)
            colnz = np.any(Uf != 0, axis=1)        # (G, n): column j has a non-zero (or NaN)
            u0 = ~np.any(Z & colnz, axis=1)
            # reconstruction
            R = A.astype(LD) - np.matmul(UL * SL[:, None, :], VL)
            recon = np.max(np.abs(R).reshape(G, -1), axis=1) / denom
            fin = np.all(np.isfinite(Sf), axis=1)
            ovf = Shb[:, 0] == INF_BITS
            recon_na = (~fin) & ovf
            recon = np.where(recon_na, LD(np.nan), recon)
        nw = nan_to_inf(nw.astype(np.float64))
        vt_orth = nan_to_inf(vt_orth.astype(np.float64))
        u_orth = nan_to_inf(u_orth.astype(np.float64))
        rec = recon.astype(np.float64)
        rec[np.isnan(rec) & ~recon_na] = np.inf
        with np.errstate(all='ignore'):
            relmax = relmax.astype(np.float64)
        mn = m * n
        thr_nw = 4.0 * max(1.0, math.sqrt(mn) / 2.0)
        thr_rec = 16.0 * max(1.0, math.sqrt(mn))
        ok = (nw <= thr_nw) & (u_orth <= 256) & (vt_orth <= 256) & desc
        ok &= recon_na | (rec <= thr_rec)
        out['sig_nw'][ks] = nw
        out['sig_rel'][ks] = relmax
        out['u_orth'][ks] = u_orth
        out['vt_orth'][ks] = vt_orth
        out['recon'][ks] = rec
        out['recon_na'][ks] = recon_na
        out['desc'][ks] = desc
        out['u0col'][ks] = u0
        out['pass'][ks] = ok
    return out


def pct(a, q):
    a = a[~np.isnan(a)]
    if len(a) == 0:
        return float('nan')
    return float(np.percentile(a, q, method='higher'))


def worst(a, ids):
    a2 = np.where(np.isnan(a), -np.inf, a)
    if len(a2) == 0 or np.all(a2 == -np.inf):
        return float('nan'), None
    i = int(np.argmax(a2))
    return float(a2[i]), int(ids[i])


def fmtv(x):
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return '-'
    if math.isinf(x):
        return 'inf'
    if x >= 1e6:
        return '%.2e' % x
    if x >= 100:
        return '%.0f' % x
    return '%.2f' % x


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('results')
    ap.add_argument('--corpus', default=os.path.join(WORK, 'corpus.bin'))
    ap.add_argument('--meta', default=os.path.join(WORK, 'corpus_meta.json'))
    ap.add_argument('--oracle', help='default $SVDH_WORK/oracle.json')
    ap.add_argument('--baseline')
    ap.add_argument('--json')
    ap.add_argument('--top', type=nonneg_arg, default=8, metavar='N',
                    help='failing matrices listed per class (default 8; --diff lists 3N)')
    ap.add_argument('--sub', action='store_true', help='print the per-subclass table too')
    ap.add_argument('--diff', metavar='OTHER.bin',
                    help='only compare results bit for bit with another results file, per class; '
                    'exits 1 when they differ')
    a = ap.parse_args()
    if a.diff:
        given = [o for o, v in (('--baseline', a.baseline), ('--json', a.json), ('--sub', a.sub),
                                ('--oracle', a.oracle)) if v]
        if given:
            ap.error('--diff takes no %s' % ', '.join(given))
    if a.oracle is None:
        a.oracle = os.path.join(WORK, 'oracle.json')

    need_file(a.results, 'results file')
    cw, crow, ccol, coff = load_corpus(a.corpus)
    N = len(crow)
    meta = load_meta(a.meta, crow, ccol)
    cls = np.array([m['class'] for m in meta])
    labels = [m['label'] for m in meta]
    if a.diff:
        roff, total = results_offsets(crow, ccol)
        x = load_results(a.results, total)
        y = load_results(a.diff, total, '--diff file')
        dw = np.nonzero(x != y)[0]
        ks = sorted(set((np.searchsorted(roff, dw, side='right') - 1).tolist()))
        bycls = {}
        for k in ks:
            bycls.setdefault(cls[k], []).append(k)
        if not ks:
            print('diff: %s and %s are BIT-IDENTICAL (%d matrices)' % (a.results, a.diff, N))
            return 0
        else:
            print('diff: %d words differ in %d matrices: %s' % (len(dw), len(ks), ', '.join(
                '%s %d' % (c, len(v)) for c, v in bycls.items())))
            for k in ks[:a.top * 3]:
                o = roff[k]
                sz = 1 + 2 * int(ccol[k]) + int(crow[k] * ccol[k]) + int(ccol[k] ** 2) + 1
                d = [(int(i - o), '%016x' % x[i], '%016x' % y[i]) for i in dw if o <= i < o + sz][:4]
                print('   id %5d %-40s %s' % (k, cut(labels[k], 40), d))
            return 1
    require_longdouble()
    if a.baseline:
        need_file(a.baseline, 'baseline')
    orc = Oracle(a.oracle, N, meta)
    R = score(cw, crow, ccol, coff, orc, a.results)
    B = score(cw, crow, ccol, coff, orc, a.baseline, 'baseline') if a.baseline else None

    classes = [c for c in CLASS_ORDER if c in set(cls)] + sorted(set(cls) - set(CLASS_ORDER))
    summary = {'results': os.path.abspath(a.results), 'baseline': a.baseline and os.path.abspath(a.baseline),
               'classes': {}, 'total': {}}
    print('results: %s   (%d matrices)' % (a.results, N))
    hdr = '%-10s %6s %6s %5s %5s %5s %5s %6s %6s %5s %5s %5s' % (
        'class', 'count', 'st!=0', '-1', '-2', '-3', 'other', 'PASS', 'fail', 'desc', 'u0col', 'vo!=')
    print('\n== status / verdict ==')
    print(hdr)
    for c in classes + ['ALL']:
        sel = (cls == c) if c != 'ALL' else np.ones(N, bool)
        st = R['status'][sel]
        okst = st == 0
        row = dict(count=int(sel.sum()), st_nz=int((st != 0).sum()), m1=int((st == -1).sum()),
                   m2=int((st == -2).sum()), m3=int((st == -3).sum()),
                   other=int(((st != 0) & (st != -1) & (st != -2) & (st != -3)).sum()),
                   pass_=int(R['pass'][sel].sum()),
                   desc_bad=int((~R['desc'][sel] & okst & ~orc.reject[sel]).sum()),
                   u0_bad=int((~R['u0col'][sel] & okst & ~orc.reject[sel]).sum()),
                   vo_bad=int((~R['vo_match'][sel]).sum()))
        print('%-10s %6d %6d %5d %5d %5d %5d %6d %6d %5d %5d %5d' % (
            c, row['count'], row['st_nz'], row['m1'], row['m2'], row['m3'], row['other'],
            row['pass_'], row['count'] - row['pass_'], row['desc_bad'], row['u0_bad'], row['vo_bad']))
        if c == 'ALL':
            summary['total'] = row
        else:
            summary['classes'][c] = row
    print('\n== metrics over status-0 matrices: worst / p99.9  (sig_rel in ulps, others in u) ==')
    print('%-10s %20s %20s %20s %20s %20s %6s'
          % ('class', 'sig_nw', 'sig_rel', 'u_orth', 'vt_orth', 'recon', 'rec_na'))
    for c in classes + ['ALL']:
        sel = ((cls == c) if c != 'ALL' else np.ones(N, bool)) & (R['status'] == 0) & ~orc.reject
        ids = np.nonzero(sel)[0]
        cells = []
        mrow = {}
        for mname in METRICS:
            v = R[mname][sel]
            w, wid = worst(v, ids)
            p = pct(v, 99.9)
            mrow[mname] = {'worst': w, 'worst_id': wid, 'p999': p}
            cells.append('%9s / %-8s' % (fmtv(w), fmtv(p)))
        na = int(R['recon_na'][sel].sum())
        print('%-10s %s %6d' % (c, ' '.join('%20s' % x for x in cells), na))
        tgt = summary['total'] if c == 'ALL' else summary['classes'][c]
        tgt['metrics'] = mrow
        tgt['recon_na'] = na
    # per-subclass table
    subs = [subkey(c, l) for c, l in zip(cls, labels)]
    sub_order = []
    for x in subs:
        if x not in sub_order:
            sub_order.append(x)
    subs = np.array(subs)
    sub_rows = {}
    if a.sub:
        print('\n== per subclass ==')
        print('%-44s %5s %5s %4s %4s %4s %5s %8s %8s %8s %9s' % (
            'subclass', 'count', 'st!=0', '-1', '-2', '-3', 'PASS', 'max nw', 'max rec', 'max orth',
            'max rel'))
    for sk in sub_order:
        sel = subs == sk
        st = R['status'][sel]
        s0 = sel & (R['status'] == 0) & ~orc.reject

        def mx(name):
            v = R[name][s0]
            v = v[~np.isnan(v)]
            return float(v.max()) if len(v) else float('nan')
        orth = max(mx('u_orth'), mx('vt_orth')) if s0.any() else float('nan')
        row = dict(count=int(sel.sum()), st_nz=int((st != 0).sum()), m1=int((st == -1).sum()),
                   m2=int((st == -2).sum()), m3=int((st == -3).sum()), pass_=int(R['pass'][sel].sum()),
                   max_nw=mx('sig_nw'), max_recon=mx('recon'), max_orth=orth, max_rel=mx('sig_rel'))
        sub_rows[sk] = row
        if a.sub:
            print('%-44s %5d %5d %4d %4d %4d %5d %8s %8s %8s %9s' % (
                cut(sk, 44), row['count'], row['st_nz'], row['m1'], row['m2'], row['m3'], row['pass_'],
                fmtv(row['max_nw']), fmtv(row['max_recon']), fmtv(orth), fmtv(row['max_rel'])))
    summary['subclasses'] = sub_rows
    # non-finite class extras
    nfsel = orc.reject
    if nfsel.any():
        print('\nnonfinite: %d inputs; refused (both paths < 0): %d; out-params untouched on refusal: %d'
              % (int(nfsel.sum()), int(R['pass'][nfsel].sum()),
                 int((R['untouched'] & nfsel & (R['status'] < 0)).sum())))
    # worst / failing lists
    print('\n== failing matrices (status 0 but not PASS: worst first; then status != 0 samples) ==')
    fail_ids = {}
    for c in classes:
        sel = (cls == c)
        ids = np.nonzero(sel & ~R['pass'])[0]
        fail_ids[c] = [int(i) for i in ids]
        if len(ids) == 0:
            continue
        st0 = [i for i in ids if R['status'][i] == 0 and not orc.reject[i]]

        def sev(i):
            m, n = int(crow[i]), int(ccol[i])
            mn = m * n
            r = [R['sig_nw'][i] / (4 * max(1, math.sqrt(mn) / 2)), R['u_orth'][i] / 256,
                 R['vt_orth'][i] / 256,
                 (0 if R['recon_na'][i] else R['recon'][i]) / (16 * max(1, math.sqrt(mn))),
                 0 if R['desc'][i] else 1e300]
            r = [np.inf if (isinstance(x, float) and math.isnan(x)) else x for x in r]
            return max(r)
        st0.sort(key=lambda i: -sev(i))
        stn = [i for i in ids if not (R['status'][i] == 0 and not orc.reject[i])]
        print('-- %s: %d not PASS (%d with status 0, %d with status != 0 or wrongly accepted)'
              % (c, len(ids), len(st0), len(stn)))
        for i in st0[:a.top]:
            print('   id %5d %-48s nw %s rel %s uo %s vt %s rec %s%s' % (
                i, cut(labels[i], 48), fmtv(R['sig_nw'][i]), fmtv(R['sig_rel'][i]), fmtv(R['u_orth'][i]),
                fmtv(R['vt_orth'][i]), fmtv(R['recon'][i]), '' if R['desc'][i] else ' NOT-DESC'))
        for i in stn[:max(3, a.top // 2)]:
            print('   id %5d %-48s status %d / values-only %d' % (
                i, cut(labels[i], 48), R['status'][i], R['status_vo'][i]))
    # worst per metric per class (who)
    print('\n== worst offender per metric (status-0 matrices) ==')
    for c in classes:
        mr = summary['classes'][c].get('metrics', {})
        parts = []
        for mname in METRICS:
            x = mr.get(mname, {})
            if x.get('worst_id') is not None:
                parts.append('%s %s @%d' % (mname, fmtv(x['worst']), x['worst_id']))
        if parts:
            print('  %-9s %s' % (c, '; '.join(parts)))
    summary['fail_ids'] = fail_ids
    summary['oracle_info'] = {k: v for k, v in orc.info.items() if k != 'verification_log'}

    # baseline comparison
    if B is not None:
        print('\n== vs baseline %s ==' % a.baseline)
        print('%-10s %7s %7s %7s %7s %7s %6s %6s %6s %6s' % (
            'class', 'base0', 'S=bits', 'U=bits', 'Vt=bits', 'all=', 'regr', 'b0c!0', 'fixed', 'newPASS'))
        regress = []
        bcmp = {}
        for c in classes + ['ALL']:
            sel = (cls == c) if c != 'ALL' else np.ones(N, bool)
            b0 = np.nonzero(sel & (B['status'] == 0))[0]
            sS = sU = sV = sA = 0
            for i in b0:
                eS = np.array_equal(R['S_bits'][i], B['S_bits'][i]) and R['status'][i] == 0
                eU = np.array_equal(R['U_bits'][i], B['U_bits'][i]) and R['status'][i] == 0
                eV = np.array_equal(R['V_bits'][i], B['V_bits'][i]) and R['status'][i] == 0
                sS += eS
                sU += eU
                sV += eV
                sA += (eS and eU and eV)
            b0c = int(np.sum(sel & (B['status'] == 0) & (R['status'] != 0)))
            fixed = int(np.sum(sel & (B['status'] != 0) & (R['status'] == 0)))
            newpass = int(np.sum(sel & ~B['pass'] & R['pass']))
            lostpass = np.nonzero(sel & B['pass'] & ~R['pass'])[0]
            nreg = 0
            if c != 'ALL':
                for i in np.nonzero(sel)[0]:
                    why = []
                    if B['status'][i] == 0 and R['status'][i] != 0 and not orc.reject[i]:
                        why.append('status 0 -> %d' % R['status'][i])
                    elif B['pass'][i] and not R['pass'][i]:
                        why.append('PASS -> fail')
                    if B['status'][i] == 0 and R['status'][i] == 0 and not orc.reject[i]:
                        for mname, slack in (('sig_nw', 4), ('sig_rel', 4), ('u_orth', 16),
                                             ('vt_orth', 16), ('recon', 16)):
                            bv, cv = B[mname][i], R[mname][i]
                            if math.isnan(cv) or math.isnan(bv):
                                continue
                            if cv > 4 * bv + slack:
                                why.append('%s %s -> %s' % (mname, fmtv(bv), fmtv(cv)))
                    if why:
                        nreg += 1
                        regress.append({'id': int(i), 'class': c, 'label': labels[i], 'why': why})
            else:
                nreg = len(regress)
            row = dict(base0=len(b0), S_identical=sS, U_identical=sU, Vt_identical=sV, all_identical=sA,
                       regressions=nreg, base0_cand_nonzero=b0c, fixed=fixed, new_pass=newpass,
                       lost_pass=len(lostpass))
            bcmp[c] = row
            print('%-10s %7d %7d %7d %7d %7d %6d %6d %6d %6d' % (
                c, len(b0), sS, sU, sV, sA, nreg, b0c, fixed, newpass))
        print('\nREGRESSIONS: %d' % len(regress))
        for r in regress[:60]:
            print('   id %5d %-48s %s' % (r['id'], cut(r['label'], 48), '; '.join(r['why'])))
        if len(regress) > 60:
            print('   ... %d more (see --json)' % (len(regress) - 60))
        summary['baseline_cmp'] = bcmp
        summary['regressions'] = regress

    if a.json:
        def clean(o):
            if isinstance(o, dict):
                return {k: clean(v) for k, v in o.items()}
            if isinstance(o, list):
                return [clean(v) for v in o]
            if isinstance(o, float) and (math.isnan(o) or math.isinf(o)):
                return None if math.isnan(o) else ('inf' if o > 0 else '-inf')
            if isinstance(o, (np.integer,)):
                return int(o)
            if isinstance(o, (np.floating,)):
                return clean(float(o))
            return o
        per = []
        for i in range(N):
            per.append({'id': i, 'status': int(R['status'][i]), 'status_vo': int(R['status_vo'][i]),
                        'pass': bool(R['pass'][i]), 'vo_match': bool(R['vo_match'][i]),
                        **{mname: float(R[mname][i]) for mname in METRICS}})
        summary['per_matrix'] = per
        try:
            with open(a.json, 'w') as fh:
                json.dump(clean(summary), fh)
        except OSError as e:
            die('cannot write --json %s: %s' % (a.json, e.strerror))
    print('\nPASS total: %d / %d' % (summary['total']['pass_'], N))
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception:                 # status 1 is --diff's "differ": any other failure is 2
        traceback.print_exc()
        sys.exit(2)
