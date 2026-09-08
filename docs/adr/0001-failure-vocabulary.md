# ADR 0001 — One failure vocabulary across the matrix and linalg surface

**Status**: Accepted
**Date**: 2026-09-07
**Version**: 1.2.3

## Context

By 1.2.2 ganita had accumulated failure returns one function at a time. `mat_new`
returned null. `lu` returned 0 for singular. `cholesky` returned 0 for
not-positive-definite. `eigen_sym` returned -1 for max-iterations, and 1.2.2 added
-2 there for allocation failure. `det` returned 0.0 for singular and, as of 1.2.2,
NaN for allocation failure. Nothing said any of this in one place, so each function
had to be read individually to find out how it fails.

The P(-1) sweep then added a second *kind* of failure — the contract violation.
Twenty functions gained shape, range and null preconditions, and every one needed
a way to say "your argument was wrong" that a caller could tell apart from "I ran
out of memory" and from a real answer about the matrix.

Without a rule, that would have been twenty more local decisions.

## Decision

One vocabulary, stated once at the top of `src/linalg.cyr`:

| The function returns | Success | Failure |
|---|---|---|
| a matrix or a flat array | the pointer | `0` |
| a status | `0` or a positive count | **negative**: `-1` allocation · `-2` contract violation · `-3` non-convergence |
| an f64 | the value | **NaN** |

A caller that only wants "did it work" tests `< 0` on every status function and
`== 0` on every constructor.

Two consequences worth stating explicitly:

**f64-returning functions must use NaN, not a sentinel value.** `det` already
returns `0.0` to mean *singular* and `condition` returns `-1.0` to mean *singular*.
Both are real answers about the matrix. Overloading either to also mean "the run
failed" would report a perfectly invertible matrix as singular — a wrong answer
dressed as a right one.

**`ganita_mat_lu` is the one exception.** Its successful returns are the
permutation sign `+1` and `-1`, so it has no negative to spend. It folds a
contract violation into its existing `0` ("cannot decompose"), which is what a
caller already tests for.

`eigen_sym`'s non-convergence code moved from `-1` to `-3` to fit. That is a
consumer-visible change, and it is safe to make now because the `-2` allocation
code was itself only three days old (1.2.2), the existing idiom in both the test
suite and the internal callers is `>= 0` rather than a specific code, and ganita's
only downstream consumer takes it through the `dist/` fold, which had not yet been
refolded.

## Alternatives considered

**A Result/Option type.** cyrius has `Result` and `Tagged` in stdlib. Rejected:
ganita's whole surface is untyped i64 by convention, matching the stdlib modules it
was carved from and the fold target it must remain byte-compatible with. Changing
the return representation of 40 public functions is a different project from
hardening them, and it would break every existing consumer at once.

**A single `ganita_errno` global.** Rejected: it is not thread-safe, and stdlib has
`thread.cyr`. It also separates the error from the call that produced it, which is
exactly the property that made the original defects hard to see.

**Distinct positive error codes.** Rejected: several of these functions return a
meaningful count (`rank`, `eigen_sym`'s rotations), so positive values are taken.

  ## Consequences

  - Callers get one rule instead of forty.
  - `< 0` is a valid universal failure test on status functions — `mat_lu` excepted,
  and that exception is documented at both sites.
  - Adding a new failure kind means adding `-4`, not inventing a local convention.
  - NaN-returning failures require callers to test with a NaN predicate rather than
  `==`, because NaN compares false against everything including itself. That is a
  real cost, and it is the reason `_linalg_is_nan` is now a shared helper rather
  than something each caller reinvents.
