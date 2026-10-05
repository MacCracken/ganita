# `pseudo_inv` and `condition` go wrong at the two ends of the double range — NaN entries when a kept σ is below 2^-1024, "singular" and a zero pseudo-inverse when σ₁ overflows

**Status:** 🟡 **OPEN** — found by the 1.2.12 verification of the SVD rewrite.
**Placement:** unpinned.
**Discovered:** 2026-10-04, while verifying the 1.2.12 SVD (`ganita_mat_svd` is not at fault: its σ, U
and Vᵀ are right on every input below, and +∞ is the correctly rounded σ₁ in the overflow rows).
**Severity:** Low. Only finite matrices whose singular values reach the ends of the range: a kept σ
below 2^-1024, or σ₁ above DBL_MAX. One of the two answers is silent and finite (a condition number
of −1.0, "singular", for a matrix whose condition number is 1).
**Affects:** ganita 1.2.4 – 1.2.12. Every check of the repro gives the same verdict on 1.2.11 and on
1.2.12. 1.2.12 reaches the overflow rows from more inputs, because its SVD decomposes matrices that
1.2.11 refused: [[1, 2, 3], [1, 2, 3], [4, 5, 6]]·2^1021 was −1 (and so pseudo_inv null) on 1.2.11,
and is now status 0 with σ₁ = +∞ and a pseudo-inverse of zeros.

## Summary

Both functions take the singular values from `_linalg_svd_impl` already unscaled to A's own
magnitude, and then do arithmetic on them that the working scale would have kept in range.

**1. A kept σ below 2^-1024: `pseudo_inv` returns NaN entries.** It keeps every σ above
`LINALG_EPS · σ₁` = 1e-12·σ₁ (`src/linalg.cyr`, `ganita_mat_pseudo_inv`) and scales row j of Vᵀ by
1/σ_j. When σ_j < 2^-1024 that reciprocal is +∞, and +∞ · 0 is NaN wherever Vᵀ has a zero. A tiny
σ_j is kept whenever σ₁ is tiny too:

| input | σ | `pseudo_inv` today | exact pseudo-inverse |
|---|---|---|---|
| diag(2^-1060, 2^-1060) | (2^-1060, 2^-1060) | all four entries NaN | diag(2^1060, 2^1060): overflows |
| diag(2^-1000, 2^-1030) | (2^-1000, 2^-1030), ratio 2^-30 | 3 of 4 entries NaN | diag(2^1000, 2^1030): one entry overflows |

**2. σ₁ above DBL_MAX: the relative tolerances become +∞.** σ₁ comes back +∞, the correctly
rounded value, and every threshold built from it, `LINALG_EPS · σ₁`, is +∞ as well:
- `condition` tests σ_n ≤ 1e-12·σ₁, which is now always true, and returns −1.0 ("singular");
- `pseudo_inv` treats every σ as negligible and returns a matrix of zeros.

| input | exact σ | `condition` today | exact | `pseudo_inv` today | exact |
|---|---|---|---|---|---|
| DBL_MAX·[[1, 1], [1, −1]] | (√2·DBL_MAX, √2·DBL_MAX), both overflow | **−1.0** | **1** | all zeros | [[1, 1], [1, −1]]/(2·DBL_MAX), entries ±2.8e-309 |
| DBL_MAX·[[1, 1], [1, ½]] | (1.78·DBL_MAX, 0.28·DBL_MAX), σ₁ overflows | **−1.0** | **6.3423292192132454** | — | — |

The condition number is scale-invariant, so both are well-conditioned matrices that only *look*
singular through an overflowed σ₁.

## Reproduction

`repros/2026-10-04-svd-derived-functions-at-the-range-ends.cyr` runs the five witnesses above and a
control, diag(2, 3). The exit code is the number of wrong checks:
- `pseudo_inv` is right when it returns null, or a matrix with no NaN entry and not all zeros
  (every witness has a non-zero exact pseudo-inverse);
- `condition` is right within 4 ulps of the exact value, computed with mpmath and rounded once.

```
cyrius build docs/development/issues/repros/2026-10-04-svd-derived-functions-at-the-range-ends.cyr /tmp/svdends
/tmp/svdends; echo "exit=$?"      # -> 5 on 1.2.11 and 1.2.12
```

Measured from 1.2.11's `src/` and from 1.2.12's, on x86_64 and on aarch64 (qemu), with the published
cyrius 6.6.15: exit 5 every time and the same verdicts. The two NaN rows print x86's default NaN,
`0xFFF8000000000000`, on x86_64 and `0x7FF8000000000000` on aarch64; nothing else differs.

## What a consumer sees

Only matrices at the two ends of the range are affected. cyrius's `tests/tcyr/math/linalg.tcyr`,
which exercises the fold, uses moderate matrices.

## Proposed fix (not prototyped)

Derive both answers from the singular values in the SVD's **working scale**, where none of this
arithmetic leaves the range. `_linalg_svd_impl` computes σ_j = |x_j|·2^-sh from columns scaled near
the top of the range; the derived functions would take |x_j| and sh instead (an internal variant
that returns them, or an out-param for sh):
- `condition` = σ₁'/σ_n', with the scale cancelling: exact for every representable A. The
  "singular" test compares σ_n' with 1e-12·σ₁', both finite.
- `pseudo_inv` compares σ_j' with 1e-12·σ₁', and forms each 1/σ_j as 2^sh/σ_j' applied once to the
  product. An entry of the exact pseudo-inverse above DBL_MAX then overflows to ±∞, as IEEE
  arithmetic would, and nothing becomes NaN. Whether a pseudo-inverse that overflows should instead
  be refused (null, the ADR 0001 failure shape) is a decision for the fix, and an ADR 0004 question:
  the input is finite, the answer is not representable.

## Related

- **`rank` accepts a tolerance of +∞** (it refuses NaN and negatives only), so the caller-side idiom
  `rank(A, 1e-12·σ₁)` with an overflowed σ₁ answers 0. `eq` and `is_symmetric` refuse +∞ through
  `_linalg_tol_ok` since 1.2.12, and their docs say why: an infinite tolerance is far likelier an
  overflowed scale than a deliberate "everything". `rank` could follow, or stay as it is because
  "count the σ above +∞" has the answer 0.
- **σ₁ itself can round to +∞ when its exact value is a few ulps below DBL_MAX** (1.2.12; see
  `ganita_mat_svd`'s doc). That is the SVD's own edge, inherent to a final rounding, and it feeds
  this filing's second branch from slightly below the overflow threshold.

## Consumer-side workaround

Scale A by a power of two before calling, so its largest entry is near 1, and scale back:
condition(2^k·A) = condition(A) exactly, and pseudo_inv(A) = 2^k·pseudo_inv(2^k·A), with the last
multiply overflowing only where the exact entry does.
