# ADR 0005 — The SVD is one-sided Jacobi on a column- and row-pivoted QR

**Status**: Accepted
**Date**: 2026-10-04
**Version**: 1.2.12

## Context

1.2.4 replaced the eigendecomposition of AᵀA, which squared the condition number, with one-sided
Jacobi on A divided by its largest entry. hisab 3.3.3 then found that it refused finite matrices
that have an SVD, across wide classes of input, and reported it as −1, the code ADR 0001 reserves
for allocation failure
([`2026-10-03-mat-svd-no-convergence-on-tiny-columns`](../development/issues/archived/2026-10-03-mat-svd-no-convergence-on-tiny-columns.md)).
The filing traced four ways the sweep could not finish:

1. ζ² overflowed, the rotation became the identity, and it counted as progress;
2. α·β underflowed, and the orthogonality threshold with it;
3. in a rank-deficient matrix the null column stayed nearly parallel to its partner (499 or 500 of
   500 random squares with one zero or repeated row failed, for every n from 3 to 10);
4. a full-rank 5×4 two-cycled at rounding level.

The filing's tested branch-1 patch kept every 1.2.11 success bit for bit, but reached neither
branch 3 nor branch 4. Branch 3 is structural: unpreconditioned Jacobi has to find a rank
deficiency by wearing a column down, and the residue it leaves is confined to the span of the
others. The 1.2.11 working copy, A / max|a_ij|, also rounded entries more than 2^1022 below the
largest to subnormals with a few bits, and returned U columns at cosine 0.99999999 with status 0
for one graded 5×4.

The repair was chosen by measurement. An exact-oracle corpus of 20,622 matrices was built for the
filing, with every σ certified correctly rounded (Python `Fraction`, then mpmath at up to 2,268
bits). It ships as `scripts/svdh/`, with the adversarial sets and hunts below. Three candidate repairs were built independently. An adversary then built 3,809 matrices
aimed at each design, and two judges scored the candidates, one for correctness and numerical
robustness, one for engineering (consumer risk, cost, maintainability). Both chose C, below.

## Decision

**`ganita_mat_svd` is Drmač and Veselić's preconditioned one-sided Jacobi (LAPACK dgejsv, whose
Jacobi is dgesvj):**

1. scale A by a power of two so its largest entry sits near the top of the range (exact);
2. Householder QR with column pivoting (dgeqp3's rule, dlaqp2's norm downdates) and row pivoting
   (Powell and Reid: the pivot column's largest entry to the diagonal), A·P1 = Q1·R1;
3. for n ≥ 4 the same factorisation of R1ᵀ, and X = R2ᵀ; for n ≤ 3, X = R1ᵀ;
4. one-sided Jacobi on the columns of X until every pair is orthogonal.

The details that differ from the reference, each measured, are listed in `ganita_mat_svd`'s comment
(`src/linalg.cyr`). The ones that carry weight:
- each column of a pair is scaled by the power of two of its own largest entry, so the test is a
  cosine at every magnitude, with an absolute floor near the subnormal range;
- tol = √n·2^-52 and dgesvj's second stopping test;
- every m-term sum is pairwise;
- a column of X that is all subnormal gets a completed V column for n ≤ 3, and a U column made
  orthonormal to the others for n ≥ 4.

Non-convergence is **−3**, as ADR 0001 always said; −1 is the one allocation, −2 a contract
violation or a NaN or infinite entry (ADR 0004). Nothing is written to an out-param on a non-zero
status. The cap stays at 60 sweeps.

## Consequences

- **Positive.**
  - **No finite input is known to reach −3** (a measurement, not a proof): the corpus passes
    20,622/20,622 in at most 7 sweeps, the adversarial set 3,809/3,809 in at most 10, and 819,998
    hunted matrices are all status 0.
  - **Accuracy**, on the corpus:
    - σ within 7.8 u·σ₁ of exact, and U·Σ·Vᵀ = A to 6.9 u·σ₁;
    - U orthonormal to 5.9 u over every non-zero σ, and Vᵀ to 17.7 u;
    - graded matrices (spans up to 600 binades) have every σ within 25 ulps relatively, where
      1.2.11 was off by up to 4.4e19 ulps.

    aarch64 is bit-identical to x86_64 on every set.
  - **Faster** from 8×8 up: 40×40 takes 0.36× 1.2.11's time, 20×20 0.40×, a zero-row 10×10 0.09×
    (1.2.11 spent that time returning −1). `rank` 40×40 is 0.41×.
  - `rank`, `condition` and `pseudo_inv` now answer the textbook singular matrices they exist to
    judge.
- **Negative.**
  - **Every SVD's bits change**, signs included: only 93 of the corpus's 13,770 1.2.11 successes
    keep identical S, U and Vᵀ, and diag(2, 3, 4) no longer gives U = I. A caller that pinned
    SVD bits, or read −1 as non-convergence, has to re-derive them.
  - Eighteen private helpers: `src/linalg.cyr` grows from 1,656 to 2,786 lines, the 1.2.12
    non-finite checks and comments included. A 3×3 values-only call (`rank` and `condition` on
    small matrices) is 1.15× slower.
  - σ₁ within a few ulps of DBL_MAX can round to +∞: 7 of 563 matrices built for it, 4 of which
    1.2.11 kept finite. That edge is inherent to a final rounding. The global power-of-two scaling
    holds about 2,050 binades, so a σ further than that below σ₁ is normwise right but not
    relatively.
- **Neutral.**
  - `pseudo_inv` and `condition` still work from σ unscaled to A's magnitude, which goes wrong at
    the ends of the range. That is pre-existing, and filed as
    [`2026-10-04-svd-derived-functions-at-the-range-ends`](../development/issues/2026-10-04-svd-derived-functions-at-the-range-ends.md).

## Alternatives considered

**Patch 1.2.11's Jacobi branch by branch.** The filing's branch-1 fix is bit-safe for every
two-column input, but branch 3 has no local fix: per-pair scaling makes the test scale-free, and a
scale-free test still rotates a null column whose cosine with its partner is near 1.

**Candidate B: keep 1.2.11 bit for bit and hand its failures to a robust phase** (fingerprints, a
restart at sweep 60, deflation). It promised bit identity and kept it on 13,726 of 13,770 corpus
successes, but the guarantee leaked: 3×3s that 1.2.11 decomposed returned −3 after 120 sweeps.
It also kept 1.2.11's non-orthonormal U at status 0 (6.1e12 u on one 4×4). Its deflation zeroed
a relatively determined σ, and its robust tolerance grew linearly in m (U 1,920 u from orthogonal
at 4096×12). And it is a second, permanent algorithm to maintain.

**Candidate A: a DGESVJ/DGSVJ0 port without the QR** (de Rijk pivoting, tracked norms). It was the
fastest and, on typical input, the most accurate: U to about √n·u, 2× faster than C at 300×300.
But it returned −3 on ordinary row-graded D·B from about n = 50–64 (16 of 60 in one judge's
study, 6 of the adversarial set). Those matrices took 15–59 sweeps even at 30×30 to 50×50, so
raising the cap would not help. That is unpreconditioned Jacobi's convergence on row-graded
input, and fixing it means adding the QR, which is this decision.

**Golub–Kahan bidiagonalisation with implicit QR (LAPACK dgesvd).** It is the standard and is
fast, but it loses relative accuracy on graded matrices where Jacobi keeps it (Demmel and Veselić,
1992).

**Eigendecomposition of AᵀA** was retired at 1.2.4 for squaring the condition number.
