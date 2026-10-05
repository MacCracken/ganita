#!/usr/bin/env python3
"""Per-tree report on an adversarial corpus directory, using ../check.py's own scoring.

usage: report.py DIR --labels L1[,L2...] [--top N] [--json out.json]
DIR is a corpus directory; without a '/' it names one under $SVDH_WORK (adv, adv2).  It must hold
results_<L>.bin and may hold times_<L>.bin and rcp_<L>.bin for each label (run.sh writes them).

For each tree: status counts and PASS per class, worst inputs with metrics, non-convergence,
wrongly zeroed / relatively-wrong sigma, U orthonormality failures, u0col, vo, time outliers,
and (from rcp_<L>.bin) rank / condition / pseudo_inv checks.  The rank, condition and sigma
checks look at status-0 matrices only.  The relatively wrong sigma end with their range of
relative errors and their matrices grouped by label (shape and #index dropped).  rank(A, 0) is
counted where it is below the exact rank or above n (wrong) and where it is above the exact rank
(expected on exactly rank-deficient input: rounding leaves a zero sigma slightly positive).
rank(A, tol), tol = 1e-12*sigma_1, is compared with the count of exact sigma above tol, except
where an exact sigma lies within the error that PASS allows a returned sigma (check.py's sig_nw
bound times u*sigma_1 + 2^-1074) of tol, where a result that passes may put it on either side:
those matrices are counted apart, with how many of them disagree, how many of those have every
exact sigma subnormal or tol = 0, and how many return the count of the correctly rounded exact
sigma above tol.  The condition mismatches also say how many are in matrices whose every exact
sigma is subnormal (sigma_1 < 2^-1022): there sigma_n, a subnormal, can carry fewer significant
bits than the condition check's 1e-6 relative tolerance needs (the most significant bits of the
correctly rounded exact sigma_n among those mismatches is printed, and how many of them have
sigma_n = 2^-1074), so that check cannot be resolved there.
The pseudo_inv check skips a pseudo_inv with a
non-finite entry; it reports how many it skipped, in how many of those ||A+||_2 = 1/sigma_k
(sigma_k the smallest exact sigma above 1e-12*sigma_1) is above DBL_MAX, in how many it is above
sqrt(mn)*DBL_MAX (so that some entry of the exact A+ is beyond DBL_MAX too), in how many no entry
at all is finite, and in how many a non-finite entry sits where the exact A+ is 0 (the column of
a zero row of A, or the row of a zero column).
"""
import argparse
import json
import math
import os
import re
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import check as CK   # noqa: E402

LD = np.longdouble
U = 2.0 ** -52


def fm(x):
    return CK.fmtv(float(x)) if x is not None else '-'


def load_times(path, N):
    """times_<L>.bin as (N, 2) ns, or None when there is none; exits when it does not fit."""
    if not os.path.exists(path):
        return None
    t = CK.read_words(path, 'times file', dtype='<i8')
    if len(t) != 2 * N:
        CK.die('times file %s has %d words, expected %d (times of another corpus?)' % (path, len(t), 2 * N))
    return t.reshape(N, 2)


def thresholds(m, n):
    mn = m * n
    return 4.0 * max(1.0, math.sqrt(mn) / 2.0), 16.0 * max(1.0, math.sqrt(mn))


def main():
    ap = argparse.ArgumentParser(description='Per-tree report on an adversarial set.')
    ap.add_argument('dir', metavar='DIR', help="the set; without a '/' a name under $SVDH_WORK (adv, adv2)")
    ap.add_argument('--labels', required=True, metavar='L1[,L2...]',
                    help='trees: DIR/results_<L>.bin (and times_<L>.bin, rcp_<L>.bin) from run.sh')
    ap.add_argument('--top', type=CK.nonneg_arg, default=6, metavar='N')
    ap.add_argument('--json', metavar='OUT.json')
    a = ap.parse_args()
    d = a.dir
    if '/' not in d:
        d = os.path.join(CK.WORK, d)
    if not os.path.isdir(d):
        CK.die('%s is not a directory (adv/gen.py builds the sets)' % d)
    labels = [L for L in a.labels.split(',') if L]
    if not labels:
        ap.error('--labels names no tree')
    if len(set(labels)) != len(labels):
        ap.error('--labels names a tree more than once')
    for L in labels:
        CK.check_label(L)
    top = a.top
    cw, crow, ccol, coff = CK.load_corpus(os.path.join(d, 'corpus.bin'))
    N = len(crow)
    meta = CK.load_meta(os.path.join(d, 'corpus_meta.json'), crow, ccol)
    for L in labels:
        CK.need_file(os.path.join(d, 'results_%s.bin' % L), 'results file', ': run adv/run.sh %s %s first' % (a.dir, L))
    orc = CK.Oracle(os.path.join(d, 'oracle.json'), N, meta)
    ojs = orc.matrices
    cls = np.array([m['class'] for m in meta])
    classes = []
    for c in cls:
        if c not in classes:
            classes.append(c)
    R = {}
    T = {}
    for L in labels:
        R[L] = CK.score(cw, crow, ccol, coff, orc, os.path.join(d, 'results_%s.bin' % L))
        T[L] = load_times(os.path.join(d, 'times_%s.bin' % L), N)
    summary = {'labels': labels, 'classes': classes, 'per_tree': {}}

    # ------------------------------------------------------------ status / PASS table
    print('== status and PASS per class (count; st0/-1/-2/-3/other; PASS; u0col; vo) ==')
    hdr = '%-11s %5s ' % ('class', 'count') + ' '.join('%-27s' % L for L in labels)
    print(hdr)
    for c in classes + ['ALL']:
        sel = (cls == c) if c != 'ALL' else np.ones(N, bool)
        cells = []
        for L in labels:
            r = R[L]
            st = r['status'][sel]
            p = int(r['pass'][sel].sum())
            s0 = sel & (r['status'] == 0)
            u0 = int((~r['u0col'][s0]).sum())
            vo = int((~r['vo_match'][sel]).sum())
            cells.append('%4d/%d/%d/%d/%d P%-4d u%d v%d' % (
                int((st == 0).sum()), int((st == -1).sum()), int((st == -2).sum()), int((st == -3).sum()),
                int(((st != 0) & (st != -1) & (st != -2) & (st != -3)).sum()), p, u0, vo))
        print('%-11s %5d ' % (c, int(sel.sum())) + ' '.join('%-27s' % x for x in cells))

    # ------------------------------------------------------------ per tree detail
    for L in labels:
        r = R[L]
        tr = {'fails': [], 'nonconv': [], 'zeroed': [], 'relbad': [], 'uorth': [], 'u0col': [], 'vo': []}
        print('\n' + '=' * 100)
        print('TREE %s' % L)
        # worst metrics per class
        print('  worst metric per class (value @id), status-0 only:')
        for c in classes:
            sel = (cls == c) & (r['status'] == 0)
            ids = np.nonzero(sel)[0]
            parts = []
            for mname in CK.METRICS:
                w, wid = CK.worst(r[mname][sel], ids)
                if wid is not None:
                    parts.append('%s %s@%d' % (mname, fm(w), wid))
            print('    %-11s %s' % (c, '; '.join(parts)))
        exact = np.array([m.get('method') != 'numpy' for m in ojs]) & (r['status'] == 0)
        w, wid = CK.worst(r['sig_nw'][exact], np.nonzero(exact)[0])
        if wid is not None:
            print('  worst sig_nw where the oracle is exact (not numpy\'s sigma): %s @%d (%s, threshold %s)'
                  % (fm(w), wid, CK.cut(meta[wid]['label'], 40),
                     fm(thresholds(int(crow[wid]), int(ccol[wid]))[0])))
        # non-convergence / other status
        nz = np.nonzero(r['status'] != 0)[0]
        print('  status != 0: %d' % len(nz))
        for i in nz[:top * 3]:
            print('    id %5d %-60s status %d vo %d'
                  % (i, CK.cut(meta[i]['label'], 60), r['status'][i], r['status_vo'][i]))
            tr['nonconv'].append(int(i))
        # failing (status 0, not PASS)
        f0 = [i for i in range(N) if r['status'][i] == 0 and not r['pass'][i]]

        def sev(i):
            m, n = int(crow[i]), int(ccol[i])
            tnw, trc = thresholds(m, n)
            v = [r['sig_nw'][i] / tnw, r['u_orth'][i] / 256, r['vt_orth'][i] / 256,
                 (0 if r['recon_na'][i] else r['recon'][i]) / trc, 0 if r['desc'][i] else 1e300]
            v = [np.inf if (isinstance(x, float) and math.isnan(x)) else x for x in v]
            return max(v)
        f0.sort(key=lambda i: -sev(i))
        print('  status 0 but not PASS: %d' % len(f0))
        for i in f0[:top * 2]:
            print('    id %5d %-58s nw %s rel %s uo %s vt %s rec %s%s' % (
                i, CK.cut(meta[i]['label'], 58), fm(r['sig_nw'][i]), fm(r['sig_rel'][i]), fm(r['u_orth'][i]),
                fm(r['vt_orth'][i]), fm(r['recon'][i]), '' if r['desc'][i] else ' NOT-DESC'))
        tr['fails'] = [int(i) for i in f0]
        # U orthonormality failures
        uo = [i for i in range(N) if r['status'][i] == 0 and r['u_orth'][i] > 256]
        tr['uorth'] = [int(i) for i in uo]
        print('  u_orth > 256: %d %s' % (len(uo), [(int(i), fm(r['u_orth'][i])) for i in uo[:10]]))
        u0 = [i for i in range(N) if r['status'][i] == 0 and not r['u0col'][i]]
        tr['u0col'] = [int(i) for i in u0]
        print('  u0col violations: %d %s' % (len(u0), u0[:10]))
        vo = [i for i in range(N) if not r['vo_match'][i]]
        tr['vo'] = [int(i) for i in vo]
        print('  values-only mismatches: %d %s' % (len(vo), vo[:10]))
        # wrongly zeroed / relatively wrong sigma
        zer, relbad, subz = [], [], []
        for i in range(N):
            if r['status'][i] != 0:
                continue
            m, n = int(crow[i]), int(ccol[i])
            S = r['S_bits'][i].view(np.float64).astype(LD)
            Sh = orc.hp[i]
            ro = orc.relok[i]
            s1 = Sh[0]
            kap = meta[i].get('kappa')
            Sb = r['S_bits'][i]
            for j in range(n):
                if Sh[j] <= 0 or Sb[j] == orc.bits[i][j]:
                    continue
                err = abs(S[j] - Sh[j]) / Sh[j]
                if Sh[j] > n * U * s1 and (S[j] == 0 or err > 0.5) and abs(S[j] - Sh[j]) > LD(2.0) ** -1074:
                    zer.append((i, j, float(S[j]), float(Sh[j]), float(Sh[j] / s1)))
                if orc.bits[i][j] != 0 and Sh[j] < LD(2.0) ** -1022 and S[j] == 0:
                    subz.append(i)
                if kap is not None and ro[j] and kap * U < 1e-3 and kap < 1e15 and Sh[j] >= LD(2.0) ** -1022:
                    fac = float(err / (LD(kap) * LD(U)))
                    # one-sided Jacobi / pivoted-QR theory: error ~ kappa*u*O(m n); flag 64*m*n*kappa*u
                    if S[j] == 0 or fac > 64 * m * n:
                        relbad.append((i, j, float(S[j]), float(Sh[j]), float(err), fac, kap))
        tr['zeroed'] = [list(x) for x in zer]
        tr['relbad'] = [list(x) for x in relbad]
        print('  sigma > n*u*sigma1 returned 0 or > 50%% off: %d' % len(zer))
        for x in zer[:top]:
            print('    id %5d %-50s sigma_%d got %.6g want %.6g (%.3g sigma1)' % (
                x[0], CK.cut(meta[x[0]]['label'], 50), x[1] + 1, x[2], x[3], x[4]))
        print('  subnormal exact sigma (correctly rounded != 0) returned as 0: %d sigma in %d matrices'
              % (len(subz), len(set(subz))))
        relmats = sorted(set(x[0] for x in relbad))
        print('  relatively determined NORMAL sigma (kappa*u < 1e-3, sigma >= 2^-1022) off by > 64*m*n*kappa*u '
              'or zeroed: %d sigma in %d matrices'
              % (len(relbad), len(relmats)))
        shown = set()
        for x in sorted(relbad, key=lambda x: -x[5] if x[2] != 0 else -1e300):
            if x[0] in shown:
                continue
            shown.add(x[0])
            if len(shown) > top * 2:
                break
            print('    id %5d %-50s sigma_%d got %.6g want %.6g relerr %.3g = %.3g*kappa*u (kappa %.3g)' % (
                x[0], CK.cut(meta[x[0]]['label'], 50), x[1] + 1, x[2], x[3], x[4], x[5], x[6]))
        if relbad:
            kinds = {}
            for i in relmats:
                lab = re.sub(r' #\d+$', '', meta[i]['label'])
                shp = re.search(r' (\d+)x(\d+)', lab)
                key = lab.replace(shp.group(0), '', 1) if shp else lab
                kinds.setdefault(key, set()).add((int(shp.group(1)), int(shp.group(2))) if shp else (0, 0))
                tr.setdefault('relbad_kinds', {}).setdefault(key, []).append(int(i))
            print('    relative errors from %.3g%% to %.3g%%; the %d matrices by label (shape and #index '
                  'dropped):' % (100 * min(x[4] for x in relbad), 100 * max(x[4] for x in relbad), len(relmats)))
            for key, shapes in sorted(kinds.items(), key=lambda t: (-len(tr['relbad_kinds'][t[0]]), t[0])):
                print('      %4d  %s  (%s)' % (len(tr['relbad_kinds'][key]), key,
                                               ' '.join('%dx%d' % mn for mn in sorted(shapes) if mn != (0, 0))))
        summary['per_tree'][L] = tr

    # ------------------------------------------------------------ relative accuracy summary
    print('\n== relative accuracy on classes with kappa (graded): max relerr/(kappa*u) per class, status 0 ==')
    print('%-11s ' % 'class' + ' '.join('%22s' % L for L in labels))
    for c in classes:
        idx = [i for i in range(N) if cls[i] == c and meta[i].get('kappa') is not None]
        if not idx:
            continue
        cells = []
        for L in labels:
            r = R[L]
            worst, wid, nzero = 0.0, None, 0
            for i in idx:
                if r['status'][i] != 0:
                    continue
                kap = meta[i]['kappa']
                if not (kap * U < 1e-3):
                    continue
                S = r['S_bits'][i].view(np.float64).astype(LD)
                Sh = orc.hp[i]
                for j in range(int(ccol[i])):
                    if Sh[j] >= LD(2.0) ** -1022 and orc.relok[i][j]:
                        if S[j] == 0:
                            nzero += 1
                            continue
                        f = float(abs(S[j] - Sh[j]) / Sh[j] / (LD(kap) * LD(U)))
                        if f > worst:
                            worst, wid = f, i
            cells.append('%9s@%-5s z%-3d' % (fm(worst), wid if wid is not None else '-', nzero))
        print('%-11s ' % c + ' '.join('%22s' % x for x in cells))

    # ------------------------------------------------------------ timings
    if all(T[L] is not None for L in labels):
        print('\n== time per class: median / max of full-call us (values-only max) ==')
        print('%-11s ' % 'class' + ' '.join('%26s' % L for L in labels))
        for c in classes:
            sel = cls == c
            cells = []
            for L in labels:
                t = T[L][sel] / 1000.0
                cells.append('%8.1f / %9.1f (%9.1f)' % (np.median(t[:, 0]), t[:, 0].max(), t[:, 1].max()))
            print('%-11s ' % c + ' '.join('%26s' % x for x in cells))
        print('\n== time outliers: full-call time > 4x the fastest tree and > 2 ms (top per tree) ==')
        allt = np.stack([T[L][:, 0] for L in labels], axis=1).astype(float)
        best = allt.min(axis=1)
        for k, L in enumerate(labels):
            ratio = allt[:, k] / np.maximum(best, 1)
            bad = np.nonzero((ratio > 4) & (allt[:, k] > 2e6))[0]
            bad = sorted(bad, key=lambda i: -allt[i, k])
            print('  %s: %d; ' % (L, len(bad)) + '; '.join('id %d %s %.1f ms (x%.1f vs best)' % (
                i, CK.cut(meta[i]['label'], 40), allt[i, k] / 1e6, ratio[i]) for i in bad[:top]))
        print('\n== slowest 8 matrices per tree ==')
        for k, L in enumerate(labels):
            o = np.argsort(-allt[:, k])[:8]
            print('  %s: ' % L + '; '.join('id %d %s %.1f ms' % (i, CK.cut(meta[i]['label'], 36), allt[i, k] / 1e6)
                                           for i in o))

    # ------------------------------------------------------------ sweeps (instrumented copies)
    I = {}
    for L in labels:
        p = os.path.join(d, 'inst_%s.bin' % L)
        if os.path.exists(p):
            I[L] = CK.read_words(p, 'counter file', dtype='<i8')
            if len(I[L]) != 5 * N:
                CK.die('counter file %s has %d words, expected %d' % (p, len(I[L]), 5 * N))
            I[L] = I[L].reshape(N, 5)
    if I:
        print('\n== sweeps of the full call per class: max (mean) [@id of max] ==')
        print('%-11s ' % 'class' + ' '.join('%22s' % L for L in labels if L in I))
        for c in classes:
            sel = cls == c
            cells = []
            for L in labels:
                if L not in I:
                    continue
                sw = I[L][sel, 1]
                ids = np.nonzero(sel)[0]
                ok = sw >= 0
                if ok.any():
                    j = int(np.argmax(np.where(ok, sw, -1)))
                    cells.append('%4d (%5.1f) @%-6d' % (sw[j], sw[ok].mean(), ids[j]))
                else:
                    cells.append('%22s' % '-')
            print('%-11s ' % c + ' '.join('%22s' % x for x in cells))

    # ------------------------------------------------------------ rank / condition / pinv
    print('\n== rank / condition / pseudo_inv ==')
    for L in labels:
        p = os.path.join(d, 'rcp_%s.bin' % L)
        if not os.path.exists(p):
            continue
        w = CK.read_words(p, 'rcp file')
        o = 0
        bad_rank0, bad_rank1, bad_cond, null_pinv, bad_pinv, rank_neg = [], [], [], [], [], []
        nonfin_pinv, nonfin_norm, nonfin_entry, nonfin_all, nonfin_zero = [], 0, 0, 0, 0
        sub_cond, above_rank0, sub_cond_bits, sub_cond_tiny = 0, 0, 0, 0
        amb_rank1, amb_bad_rank1 = 0, []    # rank(A, tol) not checked: an exact sigma in the window
        maxpinv = (0.0, None)
        for i in range(N):
            m, n = int(crow[i]), int(ccol[i])
            if o + 7 > len(w):
                CK.die('rcp file %s is truncated at matrix %d of %d' % (p, i, N))
            st = int(np.int64(w[o]))
            r0 = int(np.int64(w[o + 2]))
            tolb = w[o + 3]
            r1 = int(np.int64(w[o + 4]))
            cnd = float(w[o + 5:o + 6].view(np.float64)[0])
            has = int(w[o + 6])
            o += 7
            X = None
            if has:
                if o + m * n > len(w):
                    CK.die('rcp file %s is truncated at matrix %d of %d' % (p, i, N))
                X = w[o:o + m * n].view(np.float64).reshape(n, m)
                o += m * n
            with np.errstate(over='ignore'):
                Sh = orc.hp[i].astype(np.float64)      # +inf where the exact sigma > DBL_MAX
            Shl = orc.hp[i]
            exact_rank = ojs[i]['rank']
            if st != 0:
                if r0 >= 0 or r1 >= 0:
                    rank_neg.append(i)
                continue
            # rank with tol 0: counts returned sigma > 0, cannot exceed n, must be >= exact rank
            if r0 < exact_rank or r0 > n:
                bad_rank0.append((i, r0, exact_rank))
            elif r0 > exact_rank:
                above_rank0 += 1
            # rank with tol = 1e-12*s1 (the tol the rcp file records, from the returned s1): against
            # the count of exact sigma above tol, unless an exact sigma lies within the error that
            # PASS allows a returned sigma, thr*(u*s1 + 2^-1074) with thr check.py's sig_nw bound,
            # of tol: a result that passes may put that sigma on either side.  Such matrices are
            # counted apart, with how many disagree and how many of those return the count of the
            # correctly rounded exact sigma above tol (the best a double result can give).
            tol = float(np.array([tolb], dtype='<u8').view(np.float64)[0])
            want = int(np.sum(Shl > LD(tol)))
            win = LD(thresholds(m, n)[0]) * (LD(U) * Shl[0] + LD(2.0) ** -1074)
            if np.any(np.abs(Shl - LD(tol)) <= win):
                amb_rank1 += 1
                if r1 != want:
                    cr = int(np.sum(orc.bits[i].view(np.float64) > tol))
                    amb_bad_rank1.append((i, r1, want, cr, bool(Shl[0] < LD(2.0) ** -1022), tol == 0))
            elif r1 != want:
                bad_rank1.append((i, r1, want))
            # condition
            if Sh[-1] <= 1e-12 * Sh[0] * (1 + 1e-6) and Sh[-1] >= 1e-12 * Sh[0] * (1 - 1e-6):
                pass
            elif Sh[0] == 0:
                pass
            elif Sh[-1] <= 1e-12 * Sh[0]:
                if not (cnd == -1.0):
                    if not (Sh[-1] > 1e-12 * Sh[0] * 0.5):
                        bad_cond.append((i, cnd, -1.0))
            else:
                want_c = float(Shl[0] / Shl[-1])
                if not (abs(cnd - want_c) <= 1e-6 * want_c + 1e3 * n * U * want_c * (Sh[0] / Sh[-1])):
                    bad_cond.append((i, cnd, want_c))
            if bad_cond and bad_cond[-1][0] == i and Shl[0] < LD(2.0) ** -1022:
                sub_cond += 1
                sn = int(orc.bits[i][-1])                 # the correctly rounded exact sigma_n, subnormal
                sub_cond_bits = max(sub_cond_bits, sn.bit_length())
                sub_cond_tiny += int(sn == 1)
            # pinv: Penrose identities in longdouble, relative to cond of the kept part
            if X is None:
                null_pinv.append(i)
                continue
            A = cw[coff[i]:coff[i] + m * n].view(np.float64).reshape(m, n)
            if not np.all(np.isfinite(X)) or not np.all(np.isfinite(A)):
                if np.all(np.isfinite(A)):
                    nonfin_pinv.append(i)
                    kk = int(np.sum(Shl > LD(1e-12) * Shl[0]))
                    big = LD(1) / Shl[kk - 1] / LD(np.finfo(np.float64).max) if kk > 0 else LD(0)
                    nonfin_norm += int(big > 1)
                    nonfin_entry += int(big > LD(math.sqrt(m * n)))
                    fin = np.isfinite(X)
                    nonfin_all += int(not fin.any())
                    zr = ~np.any(A != 0, axis=1)          # zero rows of A: zero columns of A+
                    zc = ~np.any(A != 0, axis=0)          # zero columns of A: zero rows of A+
                    nonfin_zero += int(bool((~fin[:, zr]).any() or (~fin[zc, :]).any()))
                continue
            k = int(np.sum(Sh > 1e-12 * Sh[0]))
            if k == 0 or not np.isfinite(Sh[0]) or Sh[0] == 0:
                continue
            kap = Sh[0] / Sh[k - 1]
            # rescale A to unit sigma1 so the identities are scale-free (exact power of two)
            e = math.frexp(Sh[0])[1]
            Al = np.ldexp(A.astype(LD), -e)
            Xl = np.ldexp(X.astype(LD), e)
            XA = Xl @ Al
            nA = float(np.max(np.abs(Al)))
            nX = float(np.max(np.abs(Xl))) if np.any(Xl != 0) else 1.0
            e2 = float(np.max(np.abs(XA @ Xl - Xl))) / nX
            e3 = 0.0
            if m <= 3000:
                AX = Al @ Xl
                e3 = float(np.max(np.abs(AX - AX.T)))
            e4 = float(np.max(np.abs(XA - XA.T)))
            tail = float(Sh[k] / Sh[0]) if k < n else 0.0
            e1 = max(0.0, float(np.max(np.abs(Al @ XA - Al))) / max(nA, 1e-300) - 2 * tail)
            score = max(e1, e2, e3, e4) / (U * kap * max(m, n))
            if score > maxpinv[0]:
                maxpinv = (score, i)
            if score > 64:
                bad_pinv.append((i, score))
        if o != len(w):
            CK.die('rcp file %s has %d words, its matrices take %d' % (p, len(w), o))
        print('  %s: rank(A, 0) below the exact rank: %d %s; above n: %d; above the exact rank (at most n): %d'
              % (L, sum(1 for x in bad_rank0 if x[1] < x[2]), [x for x in bad_rank0 if x[1] < x[2]][:4],
                 sum(1 for x in bad_rank0 if x[1] >= x[2]), above_rank0))

        def by_class(xs):
            n = {}
            for x in xs:
                n[cls[x[0]]] = n.get(cls[x[0]], 0) + 1
            return ', '.join('%s %d' % kv for kv in sorted(n.items(), key=lambda t: (-t[1], t[0])))
        print('    rank(A, 1e-12 s1) mismatches: %d %s; by class: %s'
              % (len(bad_rank1), bad_rank1[:4], by_class(bad_rank1) or '-'))
        print('    rank(A, 1e-12 s1) not checked (an exact sigma within 4*max(1, sqrt(mn)/2)*(u*s1 + 2^-1074) of '
              'tol): %d; of those, disagreeing with the exact count %d %s, with every exact sigma subnormal %d, '
              'with tol = 0 %d, equal to the count of correctly rounded exact sigma above tol %d; by class: %s'
              % (amb_rank1, len(amb_bad_rank1), [x[:3] for x in amb_bad_rank1[:4]],
                 sum(1 for x in amb_bad_rank1 if x[4]), sum(1 for x in amb_bad_rank1 if x[5]),
                 sum(1 for x in amb_bad_rank1 if x[1] == x[3]), by_class(amb_bad_rank1) or '-'))
        print('    condition mismatches: %d %s; with every exact sigma subnormal %d, where the exact sigma_n '
              'has at most %d significant bits and is 2^-1074 in %d; by class: %s'
              % (len(bad_cond), bad_cond[:3], sub_cond, sub_cond_bits, sub_cond_tiny, by_class(bad_cond) or '-'))
        print('    pinv null on status 0: %d %s; Penrose > 64*max(m,n)*kappa*u: %d %s; worst %.3g @%s'
              % (len(null_pinv), null_pinv[:5], len(bad_pinv), bad_pinv[:4], maxpinv[0], maxpinv[1]))
        print('    pinv with a non-finite entry (skipped): %d; exact 1/sigma_k > DBL_MAX in %d, > sqrt(mn)*DBL_MAX'
              ' in %d; no finite entry in %d; a non-finite entry where the exact A+ is 0 (zero row or column of'
              ' A) in %d' % (len(nonfin_pinv), nonfin_norm, nonfin_entry, nonfin_all, nonfin_zero))
        print('    rank >= 0 though the svd failed: %d' % len(rank_neg))
        summary['per_tree'].setdefault(L, {})['pinv_nonfinite'] = [int(i) for i in nonfin_pinv]
    if a.json:
        try:
            with open(a.json, 'w') as fh:
                json.dump(summary, fh)
        except OSError as e:
            CK.die('cannot write --json %s: %s' % (a.json, e.strerror or e))


if __name__ == '__main__':
    main()
