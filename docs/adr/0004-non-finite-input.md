# ADR 0004 — NaN and infinite input: refuse where a function judges the matrix, propagate where it carries values

**Status**: Accepted
**Date**: 2026-10-03
**Version**: 1.2.12

## Context

[ADR 0001](0001-failure-vocabulary.md) settled *how* each function reports failure. It did not
say whether a NaN or an infinity in the input *is* a failure, so each function answered by
accident. hisab 3.3.3 found that `ganita_mat_svd` returned status 0 and the finite singular
values (2, 0) for [[NaN, 0], [0, 2]]
([`2026-10-03-mat-svd-accepts-non-finite-input`](../development/issues/archived/2026-10-03-mat-svd-accepts-non-finite-input.md)).
The audit that followed found the same defect across the rest of linalg
([`2026-10-03-linalg-non-finite-input`](../development/issues/archived/2026-10-03-linalg-non-finite-input.md)):
22 silent cases in eigen_sym, qr, least_squares, lu_solve, cholesky_solve, cholesky, det,
max_norm, eq and is_symmetric. Two mechanisms accounted for nearly all of them:

- **An infinity becomes the tolerance.** The relative thresholds are `LINALG_EPS` times the
  largest |a_ij|. One infinite entry makes every threshold +∞, every "is there anything left to
  do?" test fails at the first step, and the function returns its input as if it were already
  reduced: qr returned Q = I and R = A, and eigen_sym returned the raw diagonal.
- **An ordered comparison drops a NaN.** `f64_gt` and `f64_lt` are false against a NaN, so a NaN
  never wins a max and never fails a "greater than tolerance" test. eigen_sym never pivoted on
  one, max_norm dropped its row, and eq accepted everything under a NaN tolerance.

Where a function did refuse (lu, inv, the gaussian_elim cases), it was through the same accident:
an infinity reached the "singular pivot" test, which holds only while `LINALG_EPS > 0`.

## Decision

**Every function that judges a matrix refuses a NaN or infinite entry, in its own ADR 0001
failure shape, before it writes anything. Every function that only carries values propagates
them, as IEEE arithmetic does.**

| kind | functions | non-finite input |
|---|---|---|
| judges | `svd`, `rank`, `condition`, `pseudo_inv`, `eigen_sym`, `qr`, `least_squares`, `lu`, `lu_solve`, `det`, `inv`, `cholesky`, `cholesky_solve`, `gaussian_elim`, `eq`, `is_symmetric` | refused: −2, null, NaN, or 0 for `lu` / `cholesky` / `gaussian_elim` and false for `eq` / `is_symmetric` |
| carries | `add`, `sub`, `scale`, `mul`, `neg`, `transpose`, `copy`, `row`, `col`, `set_row`, `set_col`, `submatrix`, `from`, `dot`, `trace`, `frobenius`, `max_norm` | propagated: a NaN gives NaN, an infinity gives the infinity IEEE gives |

- "Input" includes every operand a function reasons from: `b` for the solvers, the
  caller-supplied factors for `lu_solve` and `cholesky_solve`, and the tolerance for `eq` and
  `is_symmetric`. A tolerance must be finite and non-negative; −0.0 counts as zero.
- The test is one private helper, `_linalg_all_finite(p, n)`, on the exponent bits
  (`(x & 0x7FF0000000000000) == 0x7FF0000000000000`). It does not depend on how a target compares
  a NaN, which the x86 backend got wrong before cyrius 6.2.41.
- `max_norm` is a carrier, so it must not *drop* a NaN: a row holding a NaN now makes the result
  NaN rather than losing the row.
- In `eq` and `is_symmetric`, an infinity fails closed like a NaN. Two identical infinities used to
  compare equal only because |∞ − ∞| is NaN, which fails `diff > tol`.

## Consequences

- **Positive.** A success status means the factors and answers are about the matrix the caller
  passed, and a caller no longer needs its own scan. The `LINALG_EPS = 0` accident is gone, because no refusal depends
  on tolerance arithmetic any more.
- **Negative.** Each judging call pays one O(m·n) pass, against its own O(n³), or O(n²) for the
  solvers. A caller that relied on qr or eigen_sym "working" on infinite input now gets −2. That
  input never had a meaningful answer.
- **Neutral.** Two adjacent defects were fixed alongside: `lu_solve` now rejects a pivot index
  outside [0, n) and a non-square factor, both of which read out of bounds, and `frobenius` no
  longer overflows on finite entries above ~1.3e154. Finite input can still produce non-finite
  output where an intermediate overflows (qr near DBL_MAX); that is visible and stays a known gap.

## Alternatives considered

**Propagate everywhere.** Rejected. Propagation needs the NaN to reach the output, and the
judging functions' thresholds and pivot searches are exactly where it does not: qr's skipped
reflector left R non-triangular with every visible entry finite, and least_squares fitted x from
a single row of A.

**Check the outputs instead of the inputs.** Rejected. The outputs were often entirely finite (the
dangerous case), and by then the out-params are already overwritten.

**Fix each mechanism where it bites** (NaN-aware maxima, a finite-threshold guard). Rejected as
the primary defence. It is scattered and fragile, as the `LINALG_EPS = 0` demonstration showed,
and every new comparison would need the same care. One scan at the boundary is auditable in one
line per function.

**`f64_lt(f64_abs(x), +inf) == 0`** as the test. Equivalent on current targets, but it leans on
NaN comparison semantics. The bit test does not.
