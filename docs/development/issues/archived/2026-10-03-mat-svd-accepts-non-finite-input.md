# `ganita_mat_svd` accepts a NaN or infinite entry and reports success — an all-NaN matrix comes back with singular values (0, 0)

> ✅ **RESOLVED in ganita 1.2.12** (2026-10-04), as proposed below: one scan at the top of
> `_linalg_svd_impl`, after the shape checks.
>
> - **How.** `_linalg_all_finite(m + 16, rows·cols)` refuses a NaN or infinite entry with −2
>   before any work, so nothing is written to an out-param. It tests the exponent bits, not
>   `f64_lt(|x|, +∞)`, so it does not lean on how a target compares a NaN. `rank` now passes the
>   SVD's status through (−2 here; it mapped every failure to −1), `condition` maps it to NaN and
>   `pseudo_inv` to null: each function refuses in its own ADR 0001 shape. The rule was then
>   applied to the whole of linalg, recorded as [ADR 0004](../../../adr/0004-non-finite-input.md),
>   with the companion filing [`2026-10-03-linalg-non-finite-input`](2026-10-03-linalg-non-finite-input.md).
> - **The repro exits 0** on x86_64 and on aarch64 (was 18). It stays as the regression witness.
> - **Suite.** "SVD family: a NaN or infinite entry is refused, not decomposed (1.2.12)", 19
>   assertions: every input of the repro, the last-entry NaN, a negative and a signalling NaN, a
>   tall 3×2 with −∞ last, sigma, U and Vᵀ checked untouched after the −2, and DBL_MAX and
>   2^-1074 still decomposing.
> - **Corpus.** The 18 non-finite matrices of the 20,622-matrix svdh corpus built for the two
>   SVD filings are −2 from both the full and the values-only path, every out-param still
>   holding its poison.
> - **Cost.** One pass over m·n entries ahead of an O(m·n²) decomposition.

**Status:** ✅ **RESOLVED in ganita 1.2.12** — found by hisab 3.3.3.
**Placement:** unpinned.
**Discovered:** 2026-10-01, hisab 3.3.3, while giving `svd_compute` and `svd_truncated` a contract.
Measured again for this filing on 2026-10-03.
**Severity:** Medium. A public function returns success with plausible, finite answers for input that
has no SVD. Three siblings repeat it: `ganita_mat_rank` (rank 0), `ganita_mat_condition` (−1.0,
"singular") and `ganita_mat_pseudo_inv` (a matrix of zeros).
**Affects:** ganita 1.2.4 – 1.2.11. `ganita_mat_svd`, `_linalg_svd_impl`, `_linalg_mat_scale`,
`_linalg_norm2`, `ganita_mat_rank` and `ganita_mat_condition` are byte-identical in every cyrius tag
from 6.6.1 (ganita 1.2.4) to 6.6.14 (ganita 1.2.11). `ganita_mat_pseudo_inv` changed at 1.2.6
(cyrius 6.6.5), and the repro gives the same output on every fold from cyrius 6.6.1 to 6.6.14.

## Summary

`_linalg_svd_impl` (`src/linalg.cyr:1351`) never asks whether A is finite, and three steps then
drop a NaN quietly:
- The scale is `_linalg_mat_scale` (`:67`), an ordered max that `f64_gt` never lets a NaN win. An
  all-NaN A therefore has scale 0, and takes the "matrix of zeros" branch (`:1363`): status 0,
  every σ = 0, U = 0, V = I.
- In the sweep, a NaN in α, β or γ makes the orthogonality test `|γ| > thresh` false. The pair
  counts as orthogonal and the sweep "converges".
- At the end, σ_j is `_linalg_norm2` of column j (`:86`). That is another ordered max, and it
  returns 0 for a column whose only non-zero entries are NaN.

| input (2×2) | `ganita_mat_svd` | `rank(tol 1e-12)` | `condition` | `pseudo_inv` [0][0] |
|---|---|---|---|---|
| all NaN | **0**, S = **(0, 0)** | **0** | **−1.0** | **0** |
| [[NaN, 0], [0, 2]] | **0**, S = **(2, 0)** | **1** | **−1.0** | **0** |
| [[+Inf, 0], [0, 2]] | **0**, S = (NaN, NaN) | **0** | NaN | **0** |
| [[−Inf, 0], [0, 2]] | **0**, S = (NaN, NaN) | **0** | NaN | **0** |
| [[3, NaN], [0, 2]] | **0**, S = (3, NaN) | **1** | NaN | NaN |
| [[1, 2], [3, +Inf]] | **0**, S = (NaN, NaN) | **0** | NaN | **0** |
| [[3, 0], [0, NaN]] | **0**, S = **(3, 0)** | **1** | **−1.0** | **1/3** |
| diag(3, 2), control | 0, S = (3, 2) | 2 | 1.5 | 1/3 |

The second and seventh rows are the worst: the NaN disappears, and every answer is finite and
plausible. Where a NaN does come out of `condition` (rows 3–6), it arrives by arithmetic, not by a
check. The NaNs from Inf/Inf are x86's default NaN, `0xFFF8000000000000`.

`tests/ganita.tcyr:660-682` already has an all-NaN fixture, `NANM`, and runs `mat_eq`,
`is_symmetric` and `cholesky` on it; `cholesky` refuses it. The SVD family was never run on it.

## Reproduction

`repros/2026-10-03-mat-svd-accepts-non-finite-input.cyr` runs five non-finite inputs and one
control through all four functions. Each must report failure in its own shape (ADR 0001):
- `svd` and `rank` return a negative status. Any negative passes; the repro does not fix the code.
- `condition` returns NaN.
- `pseudo_inv` returns null.

The exit code is the number of wrong checks. The fifth input, [[3, 0], [0, NaN]], puts the NaN in
the last entry. Without it, a fix that scans only `rows`, `cols` or `rows * cols − 1` entries would
pass the repro.

```
cyrius build docs/development/issues/repros/2026-10-03-mat-svd-accepts-non-finite-input.cyr /tmp/svdnf
/tmp/svdnf; echo "exit=$?"      # -> 18 on 1.2.4 .. 1.2.11
```

Measured 15 ways, all giving exit 18 with the same output:
- from a copy of this repo's tree (cyrius 6.6.12, `src/` at 1.2.11);
- against the stdlib fold of every cyrius tag from 6.6.1 to 6.6.14, with the include lines dropped,
  each built from a directory pinned to that version.

## What a consumer sees

hisab's `svd_compute` and `svd_truncated` passed these answers on as success through 3.3.2. Since
3.3.3 they scan A themselves before calling ganita: `svd_compute` returns −2 and `svd_truncated`
returns `Err(HSB_ERR_INVALID_INPUT)`. Both leave the out-params untouched. Outside this repo, the only
callers of the SVD family are hisab and cyrius's `tests/tcyr/math/linalg.tcyr`; none of hisab's
consumers calls it.

## Proposed fix (tested)

One pass over the entries at the top of `_linalg_svd_impl`, after the shape checks. A single
`f64_lt(|x|, +Inf) == 0` catches +Inf, −Inf and NaN together. `rank` then passes the status through,
so a non-finite input is not reported as an allocation failure:

```
    if (rows < cols) { return 0 - 2; }
    var nf = 0;
    while (nf < rows * cols) {
        if (f64_lt(f64_abs(load64(m + 16 + nf * 8)), 0x7FF0000000000000) == 0) { return 0 - 2; }
        nf = nf + 1;
    }
```

```
    var src = _linalg_svd_impl(m, 0, sigma, 0, 0);       # ganita_mat_rank
    if (src != 0) { return src; }
```

Tested on a copy of 1.2.11:
- The repro exits 0. All four functions refuse through the one scan: `condition` already maps a
  non-zero status to NaN, and `pseudo_inv` to null.
- `tests/ganita.tcyr` passes 844 / 844, as without the patch.
- The companion repro, `2026-10-03-mat-svd-no-convergence-on-tiny-columns`, still exits 6.
- Partial scans are caught. A mutant that scans only `[0][0]` leaves 7 checks wrong: 3 on
  [[3, NaN], [0, 2]] and 4 on [[3, 0], [0, NaN]]. Mutants that scan `rows`, `cols` or
  `rows * cols − 1` entries leave 4 each, all on [[3, 0], [0, NaN]], so the repro reaches the last
  entry.

The scan is one pass over m·n entries, ahead of the sweeps. `rank`'s and `condition`'s doc comments
would then list a non-finite entry with the other −2 / NaN causes.

## Consumer-side workaround

hisab refuses non-finite input itself, in `svd_compute` and `svd_truncated`, from 3.3.3. Its record
is `hisab/docs/development/issues/2026-10-03-ganita-mat-svd-accepts-non-finite-input.md`.
