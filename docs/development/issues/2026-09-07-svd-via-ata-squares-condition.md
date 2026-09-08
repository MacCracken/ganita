# SVD is computed from the eigendecomposition of AᵀA, which squares the condition number

**Filed by**: ganita's 1.2.3 P(-1) sweep (linalg-advanced lens; DOWNGRADED from
HIGH by the verifier, which reproduced the exact crossover)
**Against**: `src/linalg.cyr` — `ganita_mat_svd`, and everything routed through it
**Date**: 2026-09-07
**Version**: ganita 1.2.3
**Severity**: **Medium** — accurate for well-conditioned input, silently wrong
above cond ≈ 4e8.

## What happens

`ganita_mat_svd` forms `AᵀA` and eigendecomposes it. That is the textbook
easy construction, and it has the textbook cost: **`cond(AᵀA) = cond(A)²`**. Half
the available precision is spent before the eigensolver starts.

Consequences, in increasing order of how much they will annoy someone:

- `ganita_mat_rank` and `ganita_mat_condition` start lying above cond ≈ 4e8 —
  while `ganita_mat_det` and `ganita_mat_inv`, which go through LU and never form
  `AᵀA`, get the *same matrix* right. The library disagrees with itself.
- `ganita_mat_condition` returns **NaN** — its documented allocation-failure
  sentinel — for a perfectly conditioned matrix whose entries merely overflow when
  squared. A caller cannot distinguish "out of memory" from "your entries are
  large".
- `ganita_mat_pseudo_inv` returned something that was **not the Moore-Penrose
  pseudoinverse at all** for a wide matrix: 57 % relative error on a matrix of
  one-digit integers. *(1.2.3 closed the wide-input path by enforcing `m >= n`;
  the precision loss on tall input remains.)*

## Why it is not fixed in 1.2.3

This is a replacement, not a repair. The fix is a **one-sided Jacobi SVD** (which
reuses the rotation machinery `ganita_mat_eigen_sym` already has, and whose
indexed pivot search 1.2.3 just made O(n³)) or a Golub–Kahan bidiagonalisation.
Either is a new algorithm with its own convergence behaviour, its own test suite,
and its own accuracy claims to verify — a feature-sized piece of work that a
hardening patch has no business smuggling in.

One-sided Jacobi is the better fit here: it works on `A` directly so it never
squares the condition number, it is accurate for the graded matrices this library
sees, and it shares structure with code already in the repo.

## Related

`ganita_mat_rank`'s and `ganita_mat_condition`'s LOW-severity companion finding —
both run a **full SVD** (including the U construction and the V accumulation) and
then read only the singular values. A values-only path through the eigensolver
would skip the O(n) eigenvector update on every rotation. Worth doing in the same
pass, since it touches the same code. See
[`2026-09-07-performance-backlog.md`](2026-09-07-performance-backlog.md).
