# Outside the SVD family, linalg has no finite check: eigen_sym, qr, least_squares, the triangular solvers, cholesky, det and max_norm return success or a finite answer for NaN or infinite input, and eq / is_symmetric accept anything under a NaN or +inf tolerance

> ✅ **RESOLVED in ganita 1.2.12** (2026-10-04), as proposed below, and recorded as
> [ADR 0004](../../../adr/0004-non-finite-input.md): **every function that judges a matrix refuses a
> NaN or infinite entry in its own failure shape, before it writes anything; every function that
> only carries values propagates it.**
>
> - **How.** One private helper, `_linalg_all_finite(p, n)`, on the exponent bits, called after
>   each function's shape checks: eigen_sym, qr, least_squares (A and b), lu and inv (no longer
>   by the `LINALG_EPS > 0` accident), det (NaN), gaussian_elim (the whole augmented matrix),
>   cholesky, lu_solve and cholesky_solve (the factor and b). `_linalg_tol_ok` refuses a NaN,
>   infinite or negative tolerance in eq and is_symmetric, which also fail closed on infinities
>   and, in is_symmetric's case, now read the diagonal, as its doc always said. max_norm, a
>   carrier, no longer drops a NaN row. frobenius falls back to the scaled `_linalg_norm2` only
>   when the plain sum overflows or drops below 2^-969, so every other input keeps its bits, and
>   [[1e200, 1e200]] has a finite norm. `ganita_mat_print` shows NaN, inf and -inf.
> - **The related findings.** `lu_solve` refuses a pivot index outside [0, n), a zero pivot and a
>   non-square factor (the first and last read out of bounds); `cholesky_solve` refuses a
>   non-square factor and checks before its `alloc`; `eigen_sym` returns −1, not −2, when its
>   working copy cannot be allocated, as its doc and ADR 0001 say. ADR 0001 now lists cholesky
>   and gaussian_elim as 1/0 exceptions next to lu (its 1.2.12 amendment). The two false
>   comments are corrected. Not taken up: qr and least_squares near DBL_MAX (finite input,
>   visibly non-finite output) stays a known gap.
> - **The repro exits 0** on x86_64 and on aarch64 (was 22). It stays as the regression witness.
> - **Suite.** "linalg: every function that judges a matrix refuses a NaN or infinity (1.2.12)",
>   87 assertions: every case of the repro, the finite controls, the related findings, and the two
>   predicates called directly. A mutation run deleted each new guard in turn: 27 of 29 mutants
>   fail the suite; the two survivors are an equivalent pair in eq (either check alone refuses the
>   case, and deleting both fails).

**Status:** ✅ **RESOLVED in ganita 1.2.12** — found by the non-finite audit that followed the SVD family's fix.
**Placement:** unpinned.
**Discovered:** 2026-10-03. Every function in `src/matrix.cyr` and `src/linalg.cyr` was probed with
quiet, negative and signalling NaN and ±∞ in the first entry, the last entry, a diagonal (pivot)
entry, an off-diagonal entry, and every second operand (b, a right-hand side, a tolerance, a scalar).
Each function group was probed by one agent and re-probed by an independent verifier with its own
programs and inputs. Every finding below was reproduced by both.
**Severity:** Medium, the same class as the SVD filing
([`2026-10-03-mat-svd-accepts-non-finite-input`](2026-10-03-mat-svd-accepts-non-finite-input.md)).
Public functions report success with finite, plausible answers for input that has none. Two cases
throw away *finite* data as well: eigen_sym discards an O(1) coupling, and least_squares ignores
whole rows of A and b.
**Affects:** measured on 1.2.11 (git HEAD) and on the 1.2.12 working tree, which has the SVD fix.
The repro gives the same output on both, on x86_64 and on aarch64 (qemu). cyrius 6.6.14 and 6.6.15
ship 1.2.11 as `lib/ganita.cyr`, so abaco and hisab reach these functions through the fold. Not
bisected further back.

## Summary

Two mechanisms account for nearly everything:

1. **An infinity becomes the tolerance.** `_linalg_mat_scale` (`src/linalg.cyr:67`) is the largest
   |a_ij|, so one ±∞ entry makes it +∞. Each relative threshold `LINALG_EPS · scale` is then +∞, and
   every "is there anything left to do?" test fails at the first step. eigen_sym (`:1136`, `:1194`),
   qr (`:724`, `:769`) and least_squares (`:970`, `:1009`) return status 0 with their input
   unreduced. lu, inv and gaussian_elim do *refuse* an infinity, but only through the same accident:
   the "singular pivot" test `f64_le(max_val, +∞)` happens to be true. With `LINALG_EPS = 0` (a
   public `var`), lu returns 1 and inv returns a finite matrix.
2. **An ordered comparison drops a NaN.** `f64_gt` / `f64_lt` are false against a NaN, so a NaN never
   wins a max and never fails a "greater than tolerance" test:
   - `_linalg_mat_scale` and `_linalg_norm2`'s max skip it;
   - eigen_sym's pivot search never selects it (`:1097`, `:1185`);
   - a NaN column norm fails qr's and least_squares' reflector gate, so that column is treated as
     already reduced;
   - `max_norm` drops a NaN row (`:276`);
   - `eq` and `is_symmetric` accept every entry under a NaN tolerance (`:333`, `:297`).

### Silent cases (all in the repro)

| function | input | today | ADR 0001 shape |
|---|---|---|---|
| `eigen_sym` | [[2, +∞], [+∞, 3]] | 0 rotations; values (2, 3), the raw diagonal; vectors I | −2 |
| `eigen_sym` | [[1, NaN, 5], [NaN, 2, 0], [5, 0, 3]] | 0; values **(1, 2, 3)**. The NaN at (0, 1) becomes row 0's recorded max, so the finite 5 at (0, 2) is never rotated either. The control without the NaN gives (−3.10, 2, 7.10). | −2 |
| `eigen_sym` | [[2, NaN], [NaN, 3]] | 0; (2, 3) | −2 |
| `qr` | [[1, 2], [3, 4], [5, +∞]] | 0; **Q = I, R = A**: R is not triangular, and the ∞ sits below the diagonal where a caller reading R's upper triangle never sees it | −2 |
| `qr` | [[1, 2], [3, 4], [NaN, 6]] | 0; Q finite; column 0's reflector skipped, so the NaN stays below the diagonal | −2 |
| `least_squares` | A = [[1, 1], [1, 2], [1, +∞]], b = (1, 2, 2) | 0; x = (0, 1). The top 2×2 triangle of the *unreduced* A is solved against b[0..1]; row 2 is never read, whatever b[2] holds | −2 |
| `least_squares` | A = [[1, 1], [NaN, 2], [1, 3]], b = (1, 2, 2) | 0; x finite | −2 |
| `least_squares` | A = (2, NaN, 1)ᵀ, b = (4, 1, 1) | 0; x = **2 = b₀/a₀₀**, from row 0 alone. The finite control (2, 1, 1)ᵀ gives 1.67 | −2 |
| `det` | [[NaN, 0], [0, 2]], [[+∞, 1], [1, 1]] | **+0.0**, the "singular" answer, for every non-finite input (1800 random cases up to 6×6) | NaN |
| `lu_solve` | factors of [[4, 3], [6, 3]] with U[1][1] = +∞ | 0; x all finite. A finite sum divided by ±∞ is ±0, which decouples x_i | −2 |
| `cholesky_solve` | L = [[2, 0], [1, +∞]] | 0; x all finite, for the same reason | −2 |
| `cholesky` | [[+∞, 2], [2, 3]] | **1** ("positive definite"); L = [[+∞, 0], [0, 1.73]]: the coupling L₁₀ = 1 becomes 0 | 0 (its failure) |
| `gaussian_elim` | [[2, 1 \| NaN], [1, 3 \| 4]] | **1**, x = (NaN, NaN). A NaN in the coefficient part, or an ∞ anywhere, refuses with 0; a NaN in the right-hand side does not | 0 (its failure) |
| `inv` with `LINALG_EPS = 0` | [[+∞, 1], [1, 1]] | a finite matrix [[0, −0], [0, 1]] | null |
| `max_norm` | [[NaN, 1], [2, 3]] | 5, row 1's sum | NaN |
| `max_norm` | [[NaN]], or all-NaN | **0.0**, the zero matrix's norm | NaN |
| `eq` | tol = NaN | 1 for any two NaN-free matrices of the same shape | 0 |
| `eq` | a = [[+∞, 2], [3, 4]], tol = `LINALG_EPS · frobenius(a)` | 1 against [[5, 0], [6, 1]]. The doc at `:308-310` recommends exactly this `f64_mul(LINALG_EPS, scale)` idiom, and an ∞ entry makes the tolerance +∞ | 0 |
| `is_symmetric` | tol = NaN | 1 for [[1, 2], [3, 4]] | 0 |
| `is_symmetric` | [[NaN, 1], [1, 2]], tol 1e-9 | 1. The loop starts at j = i + 1 (`:291`), so the diagonal is never read. Its doc says "0 … for one containing ANY NaN" | 0 |
| `is_symmetric` | [[NaN, 1], [4, 2]], tol = `LINALG_EPS · frobenius(m)` | **1 for an asymmetric matrix**: the unseen diagonal NaN makes the tolerance NaN. eigen_sym's and cholesky's docs tell callers to run this check first | 0 |

### What is already right

| behaviour | functions |
|---|---|
| propagate visibly, which is correct | `frobenius`, `trace` (it reads only the diagonal), `ganita_mat_dot`, `add`, `sub`, `scale`, `mul` (no skip-if-zero shortcut; NaN·0 and ∞·0 reach the result), `neg` |
| pure data movement, no judgement | `transpose`, `from`, `copy`, `row`, `col`, `set_row`, `set_col`, `submatrix` |
| refuse, but by the tolerance accident above | `lu` (0) and `inv` (null) |
| refuse | `eq` with a NaN entry (since 1.2.3); `svd`, `rank`, `condition` and `pseudo_inv` (since 1.2.12) |

Other inputs propagate visibly but get no refusal: a NaN or ∞ in least_squares' `b`, in lu_solve's
`b`, or anywhere in L for cholesky_solve except the diagonal. Under the fix below they would refuse,
so the whole Ax = b family follows one rule.

## Related findings (not in the repro)

- **`eq` and `is_symmetric` call two identical infinities equal by accident.** |∞ − ∞| is NaN, and
  `f64_gt(NaN, tol)` is false, so the entry passes, for any tol, including a negative one. Two
  identical NaNs compare unequal. Pick a policy and implement it as an explicit test.
- **Undocumented exceptions to ADR 0001.** `cholesky` (`:606`) and `gaussian_elim` (`:852`) return 1
  on success and 0 on failure. ADR 0001 and the module header name `lu` as the *one* function whose
  failure is not negative, so a caller using the documented universal `< 0` test reads every
  cholesky and gaussian_elim refusal as success.
- **`cholesky_solve`'s doc** (`:662`) lists 0 and −1 but not its −2 returns (null arguments, a zero
  diagonal). The zero-diagonal check also runs after its scratch `alloc`.
- **`lu_solve` uses `piv[i]` as an index into `b` unchecked** (`:468-469`), so a caller-supplied,
  out-of-range pivot vector reads out of bounds. This is a bounds defect, not a non-finite one.
- **`frobenius` is not scaled** (`:255-260`): a finite [[1e200, 1e200]] gives +∞, so the documented
  tolerance idiom turns finite input into an +∞ tolerance. `eq([[1e200, 1], [2, 3]], [[−1, 1],
  [2, 3]], LINALG_EPS · frobenius(a))` returns 1.
- **qr and least_squares near DBL_MAX** (finite input, out of scope): [[1e308, 0], [1e308, 1]] gives
  status 0 with ±∞ and NaN in Q, R and x. `_linalg_norm2` overflows to +∞, and that +∞ passes the
  reflector gate. The output is visibly non-finite, so this is not the silent class.
- **`ganita_mat_print`** (`matrix.cyr:322-324`) prints NaN as `0/100` and ±∞ as `±INT64_MAX/100`,
  because `f64_to` saturates. This affects display only, and nothing in the repo calls it.
- **Two false comments.** eigen_sym's doc says "only the upper triangle is read" (`:1118`), but the
  rotations read the lower triangle too (`:1232-1233`). `_linalg_mat_scale`'s comment (`:62-66`)
  says NaN is skipped because "the decompositions have their own NaN handling", which qr,
  least_squares and eigen_sym do not have.
- **The SVD witness again**: a finite 5×3 of small integers with DBL_MAX in its last entry returns
  svd −1, rank −1. This is the open
  [`2026-10-03-mat-svd-no-convergence-on-tiny-columns`](2026-10-03-mat-svd-no-convergence-on-tiny-columns.md)
  (branch 2), reached through scaling by DBL_MAX, not a new defect.

## Reproduction

`repros/2026-10-03-linalg-non-finite-input.cyr` checks the 22 silent cases in the table above, each in
its function's ADR 0001 failure shape, plus 6 finite controls. The exit code is the number of wrong
checks.

```
cyrius build docs/development/issues/repros/2026-10-03-linalg-non-finite-input.cyr /tmp/linf
/tmp/linf; echo "exit=$?"      # -> 22 on 1.2.11 and on the 1.2.12 working tree
```

It was measured four ways, all exit 22 with the same output: from 1.2.11's `src/` (git HEAD) and from
the 1.2.12 working tree, each on x86_64 and on aarch64 (qemu), with the published cyrius 6.6.15. The
controls pass in all four.

## What a consumer sees

eigen_sym's and qr's success statuses invite a caller to use the factors. hisab's `svd_compute`
needed its own finite scan for the SVD family since 3.3.3, and every other decomposition would need
the same. least_squares is the sharpest case: one NaN in a design column is enough to give a fit
computed from a single row, with status 0.

## Proposed fix

One private helper, `_linalg_all_finite(p, n)`: an exponent-bit scan,
`(x & 0x7FF0000000000000) == 0x7FF0000000000000`, as `_linalg_svd_impl` already open-codes. Call it
after each function's shape checks and before any out-param is written:

| function | refusal | scope of the scan |
|---|---|---|
| `eigen_sym` | −2 | all n² entries (both triangles are read) |
| `qr` | −2 | m·n |
| `least_squares` | −2 | A's m·n and b's m, before the allocations |
| `det` | NaN | n² (or an internal lu that returns −2, mapped to NaN, keeping 0.0 for singular) |
| `lu` / `inv` | 0 / null, explicitly | n². This removes the dependence on `LINALG_EPS > 0` |
| `gaussian_elim` | its failure | the n·(n+1) augmented matrix, so a NaN in the right-hand side refuses like an ∞ does |
| `cholesky` | 0 | a finite test at the pivot (`:646`), in place of the NaN-only test. Every entry it reads feeds some pivot. The prober tested it: 65 of 85 cases refused, the other 20 being the never-read upper triangle, and the suite still passes 863/863. A full n² scan would refuse those too |
| `lu_solve` | −2 | U's diagonal (a zero or non-finite pivot, O(n), like cholesky_solve's zero test) and b |
| `cholesky_solve` | −2 | L's diagonal (non-finite as well as zero) and b, hoisted above its `alloc` |
| `max_norm` | NaN | `_linalg_is_nan(rsum)` before the compare at `:276` |
| `eq` / `is_symmetric` | 0 | refuse a tol that is NaN, negative or +∞, before the loops. `is_symmetric` also tests the diagonal for NaN, as its doc already promises |

Each scan costs O(m·n) against the function's O(n³). The prober prototyped the scans for qr and
least_squares on a copy of the tree: 95 of 95 and 181 of 181 non-finite cases were refused, the
controls were unchanged, and the suite passed 863/863. ADR 0001 should then list cholesky and
gaussian_elim as 1/0 exceptions next to lu, or the two should move to negative codes. Each doc comment
gains "a NaN or infinite entry" in its failure list, and the two false comments above get fixed.

## Consumer-side workaround

Scan the input before calling, as hisab does for the SVD family since 3.3.3:
`(x & 0x7FF0000000000000) == 0x7FF0000000000000` on every entry, and on b and on any tolerance built
from a norm.
