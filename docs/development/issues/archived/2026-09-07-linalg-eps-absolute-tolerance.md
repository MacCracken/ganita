# `LINALG_EPS` is an absolute 1e-12, so every singularity verdict depends on the caller's units

> ✅ **RESOLVED in ganita 1.2.4** (2026-09-08). `LINALG_EPS` is now a RELATIVE
> factor, multiplied by a magnitude taken from the data at each use site: the
> matrix scale for the pivot tests in `lu` and `gaussian_elim`, the input's
> largest entry for the reflector tests in `qr` and `least_squares`, the initial
> off-diagonal magnitude for Jacobi convergence, and the largest singular value
> for the rank tests in `svd`, `pseudo_inv` and `condition`. It is also EAGER —
> a literal bit pattern rather than a lazily-initialised global — so no call
> depends any more on what ran before it.
>
> The self-contradiction is closed, verified in both directions: a 2x2 identity
> scaled by 1e-20 (cond = 1) now reads *not singular, inv ok, rank 2, cond 1.0*
> where 1.2.3 said *singular, null, rank 2, -1.0*; and `[1 2; 2 4]` stays
> singular scaled up by 1e9.
>
> The QR half is closed too. The two-norm is now computed by scaling out the
> largest magnitude first (`_linalg_norm2`), so it no longer overflows to NaN
> for large-magnitude matrices, and the reflector skip test is relative, so a
> merely small-scaled matrix no longer gets every reflector skipped.
>
> The open question the filing raised — *should the tolerance become a
> parameter?* — was answered NO for now: `mat_eq`, `is_symmetric` and `rank`
> already take one, and the rest are internal judgements where a relative
> default is the right behaviour. Revisit if a consumer needs to tune it.


**Filed by**: ganita's own 1.2.3 P(-1) sweep (linalg-core and contracts lenses,
independently, then confirmed by both verifiers)
**Against**: `src/linalg.cyr:16` and every function that reads `LINALG_EPS`
**Date**: 2026-09-07
**Version**: ganita 1.2.3, cyrius 6.6.0
**Severity**: **High** — silently wrong results, in both directions, on
in-contract input. No crash, no diagnostic.

## What happens

`LINALG_EPS` is `1e-12`, absolute, and it is compared directly against pivots,
norms and singular values — quantities whose magnitude scales with the caller's
data. So the verdict "is this matrix singular?" depends on what units the caller
chose.

Scale a perfectly well-conditioned matrix down by 1e-6 and `ganita_mat_lu`,
`ganita_mat_det`, `ganita_mat_inv`, `ganita_mat_gaussian_elim` and
`ganita_mat_condition` all report it **singular** — while `ganita_mat_rank`
reports it **full rank**. The library contradicts itself about the same matrix.

Scale up, and the reverse: a genuinely singular matrix has pivots above 1e-12 and
sails through.

Two more defects are the same root cause wearing different clothes:

- **`ganita_mat_qr` and `ganita_mat_least_squares` skip reflectors.** Both compare
  a column's two-norm against `LINALG_EPS` and skip the Householder reflector when
  it is smaller. A matrix whose entries are merely *small* therefore gets a
  **non-triangular R** and a plausible-looking wrong solution, with `rc = 0`.
  `least_squares` then detects the degenerate column, skips its reflector, and
  divides by that same near-zero pivot in back-substitution — still returning
  success.
- **`ganita_mat_eigen_sym`'s convergence test is absolute too**, which makes
  `svd`, `rank`, `condition` and `pseudo_inv` silently wrong for any matrix with
  entries below ~1e-6. Reproduced: `rank(singular_matrix) = 2` and
  `condition(singular_matrix) = 2.0`.

There is also a **lazy-initialisation** wrinkle. `LINALG_EPS` starts at `0` and is
set by `_linalg_init_eps()`, which only the decompositions call. `ganita_mat_eq`'s
doc told callers to pass `LINALG_EPS` as the default tolerance — so the identical
call answered differently depending on whether some decomposition had run first.
*(The doc was corrected at 1.2.3; the underlying lazy global remains.)*

## Reproduction

Both directions, built and run during the sweep:

```
A = [[1e-7, 0], [0, 1e-7]]        # perfectly conditioned, cond = 1
  ganita_mat_det(A)      -> 0.0        (reports singular)
  ganita_mat_inv(A)      -> 0          (reports singular)
  ganita_mat_rank(A,tol) -> 2          (reports FULL RANK)
```

## Why it is not fixed in 1.2.3

The fix is a **relative** test — against the matrix norm, or a ratio of the
current pivot to the largest seen — and it changes the answer for every existing
consumer at the boundary. It is not a repair to a broken line; it is a change to
what the library means by "singular", and it touches `lu`, `det`, `inv`,
`gaussian_elim`, `cholesky`, `qr`, `least_squares`, `eigen_sym`, `svd`, `rank` and
`condition` at once.

That belongs in its own release, with its own ADR, and with a decision made first
on a question this issue does not answer: **should the tolerance become a
parameter?** Several of these functions already take a `tol` argument
(`mat_eq`, `is_symmetric`, `rank`); the rest do not, and making them consistent is
part of the same design.

## Proposed direction

1. Replace the absolute pivot test in `lu` / `gaussian_elim` with a relative one:
   scale by the largest absolute entry in the active column, or by the matrix's
   infinity norm computed once up front.
2. Scale the two-norm in `qr` / `least_squares` before squaring, which also closes
   the overflow-to-NaN reported for large-magnitude matrices.
3. Make `eigen_sym`'s convergence test relative to the initial off-diagonal norm.
4. Decide whether `LINALG_EPS` stays a module default at all, or whether every
   affected function grows a `tol` parameter with the module default as the
   documented value to pass.
5. Eagerly initialise, or make it a compile-time constant, so no call depends on
   what ran before it.

Assertions must pin **both** directions — a scaled-down well-conditioned matrix
that must NOT be called singular, and a scaled-up singular one that must be.
