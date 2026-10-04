# `ganita_mat_svd` returns −1 ("did not converge") for finite matrices that have an SVD — square matrices with a zero or repeated row, column pairs that need a very small rotation, and a rounding two-cycle

**Status:** 🟡 **OPEN** — found by hisab 3.3.3; re-measured on ganita 1.2.11 as folded into cyrius 6.6.14.
**Placement:** unpinned.
**Discovered:** 2026-10-01, hisab 3.3.3 (a scale scan of `ganita_mat_svd` behind hisab's `svd_compute`
and `svd_truncated`). Measured again for this filing on 2026-10-03.
**Severity:** High. No wrong value is returned, but a public function refuses matrices that have an
SVD, across wide classes of input, and reports it with `-1`, the code ADR 0001 reserves for an
allocation failure. One class is ordinary input: 499 or 500 of 500 random n×n matrices with one zero
row or one repeated row fail, for n = 3, 4, 6 and 10. `ganita_mat_rank`, `ganita_mat_condition` and
`ganita_mat_pseudo_inv` inherit it, so the functions that exist to judge singular matrices answer
−1, NaN and null for textbook singular input such as [[1, 2, 3], [1, 2, 3], [4, 5, 6]].
**Affects:** ganita 1.2.4 – 1.2.11. `ganita_mat_svd`, `_linalg_svd_impl` and `_linalg_mat_scale` are
byte-identical in every cyrius tag from 6.6.1 (ganita 1.2.4) to 6.6.14 (ganita 1.2.11), and identical
to this repo's `src/linalg.cyr` at 1.2.11. The repro gives the same output under cyrius 6.6.3
(ganita 1.2.5) and 6.6.14.

## Summary

`_linalg_svd_impl` (`src/linalg.cyr:1351`) is a one-sided Jacobi SVD. For each column pair it forms
α = |w_p|², β = |w_q|² and γ = w_p · w_q as plain sums of products of the scaled matrix W = A / max|a_ij|.
It then computes the rotation from ζ = (β − α) / (2γ) (`:1436`). Four things leave the sweep unable
to finish, so it runs its 60 sweeps and returns −1 (`:1470`):

1. **ζ² overflows.** t = 1 / (|ζ| + sqrt(1 + ζ²)) is formed with ζ·ζ. For |ζ| ≥ 2^512 that product is
   +∞, so t = 0, c = 1 and s = 0. The rotation is the identity, nothing changes, `rotated` stays 1,
   and the next sweep finds the same pair. Below about |γ| = 2^-1025 · |β − α|, ζ itself is ±∞,
   with the same result.
2. **α·β underflows, and the threshold with it.** The orthogonality test is
   |γ| > 2^-52 · sqrt(α·β) (`:1432`). A column whose scaled norm is below about 2^-537 has α = 0, so
   the threshold is exactly 0. For the two witnesses below (B1, B2), the columns are already
   orthogonal to working precision and γ is a rounding residue. That residue is still > 0, so every
   sweep rotates again. Once branch 1 is repaired, the matrix the 60 sweeps leave behind is a correct
   SVD for both: they fail only because the test cannot pass.
3. **A null column stays parallel.** In a rank-deficient A, the rotations wear one column of W down
   toward zero. For the zero-row witness Z below, what is left of column 0 is rounding residue nearly
   parallel to the column it is paired with, not orthogonal to it: |γ| / sqrt(α·β) is above 0.9999 in
   every sweep from 2 to 11, so the pair always rotates. Each sweep leaves a residue 2^-52 to 2^-57
   times smaller, still parallel. From sweep 12, α is 0 and so is the threshold, while each γ stays
   fixed (`0x9DE12376203B13D8` for the pair (0, 1)) and ζ² overflows. Both pairs are then stuck in
   branches 1 and 2 at once.
4. **A two-cycle at rounding level.** For the full-rank 5×4 witness below, α ≈ 0.61 and β ≈ 0.86 are
   normal and ζ² is finite, so neither branch 1 nor branch 2 applies. From sweep 3 to 59 only the
   pair (0, 1) rotates. γ alternates between ±`0x3CA8000000000000` (1.5 · 2^-53) against a threshold
   of `0x3CA725BAACD58D30` (about 1.45 · 2^-53). Each rotation flips γ's sign but not its magnitude.

### The family hisab found: A = [[1, t], [t, t], [t, −t]]

Here α = 1, β = 3t² and γ = t, so ζ ≈ −1/(2t), and ζ² overflows for t ≤ 2^-513. The exact singular
values are about (1, √2·t), representable down to t = 2^-1074.

| t | `ganita_mat_svd` | exact σ (correctly rounded) |
|---|---|---|
| 2^-512 | 0, S = (1, `0x1FF6A09E667F3BCD`) | (1, `0x1FF6A09E667F3BCD`) |
| next double above 2^-513 | 0, S = (1, `0x1FE6A09E667F3BCE`) | (1, `0x1FE6A09E667F3BCE`) |
| **2^-513** | **−1** | (1, `0x1FE6A09E667F3BCD`) |
| **1.72 · 2^-543** | **−1** | (1, `0x1E137CC152F76F67`) |
| **1.6e-308 (subnormal)** | **−1** | (1, `0x001058E43F6FA300`) |
| **2^-1074** | **−1** | (1, `0x0000000000000001`) |

The boundary is exact: 2^-513 is the largest t that fails, and the next double up decomposes.

**Scan.** For t = m · 2^e, with e = −1074 … −1 and four mantissas (1 and three full ones), 2245 of the
4296 matrices return −1:
- for m = 1, all 562 from e = −1074 to −513;
- for each full mantissa, all 561 from e = −1074 to −514.

Every matrix that does decompose has both singular values within 2 ulp of the exact value.

### Random 2×2 and 3×2 matrices

6000 random 2×2 and 3×2 matrices were tested, with full mantissas, random signs and 10% exact zeros.
Each matrix's exponents spread around a random base by ±4, ±60, ±600 or ±2100 binades, 1500 per
spread. Of these, 468 return −1. None is at ±4 or ±60; 263 are at ±600 and 205 at ±2100. 463 of
them decompose once branch 1 is repaired (below). The other 5 fail through branch 2, and two of
those five are rows B1 and B2 of the repro.

Instrumented at the 60th sweep, all five show the same state: one column has α (or β) exactly 0,
the threshold is 0, and γ is a rounding residue. The residues are `0x0000000000000593`,
`0x8000000000000001`, `0x04D0000000000000`, `0x14F0000000000000` and `0x83670AA8E6C01E5C`.

### Square matrices with a zero or repeated row

The entries are random, with full mantissas, |a| < 2 and random signs. Then one row is zeroed, or the
last row is set to a copy of the first. 500 matrices per shape and edit:

| n×n | zero row: −1 | repeated row: −1 |
|---|---|---|
| 2×2 | 8 | 2 |
| 3×3 | 499 | 500 |
| 4×4 | 500 | 500 |
| 6×6 | 500 | 500 |
| 10×10 | 500 | 500 |

The same edits on the tall 3×2, 5×4 and 8×5 shapes, which keep full column rank, fail 0 of 500, and
so do rounded outer products x·yᵀ at all eight shapes. Not every rank-deficient matrix fails:
[[1, 2, 3], [4, 5, 6], [7, 8, 9]], of rank 2, decomposes, and `rank` gives 2 and `condition` −1.0.

The witness Z = [[1.3, 2.7, 0.4], [0, 0, 0], [0.9, 1.1, 2.3]] (each entry the nearest double) has
exact σ = (3.6560995985065308, 1.7558290707812039, 0), that is `0x400D3FB1257408C4`,
`0x3FFC17E03945F102` and 0. `ganita_mat_svd` returns −1, `ganita_mat_rank` (tol 1e-12) −1,
`ganita_mat_condition` NaN (`0xFFF8000000000000`) and `ganita_mat_pseudo_inv` null. So does
[[1, 2, 3], [1, 2, 3], [4, 5, 6]].

### A full-rank 5×4 that two-cycles

Condition number 11.12, exact σ = (13.166199101181938, 11.788740275814376, 9.8679004436648459,
1.183645125577899). It returns −1 at its own scale and scaled by 2^-827, 2^-327 and 2^173, and
`rank`, `condition` and `pseudo_inv` give −1, NaN and null. Its row-major bits:

```
bfc2cacd2bba2bfc 3ff436f97395fc68 c00807f8a62bf805 3ff337df0357c8c9
3fefd315acc77fe7 bfa1614b40ea6cc2 c0295cebbfddbb61 bfc32af6f3470282
bfd6269dc8658203 c025b46bf0a392b4 3fc03ff652eed9bf 0000000000000000
3fdf9160669d391a 3fcc98b730a0d724 bfbc46376ff5e5c4 3fc92a56372a02bb
c02551acec11860f 400130c3519e4f30 3fc6d251f22a1e9b 3fe9e1efc1aeb952
```

These results are the same under cyrius 6.6.3 and 6.6.14. The exact σ come from python3 `Fraction`
and `Decimal`, rounded once.

### What else returns the code

`ganita_mat_rank` and `ganita_mat_condition` call `_linalg_svd_impl` and map any non-zero status to
their allocation-failure answer:
- rank returns −1 (`:1620`), and its doc lists −1 for "any working allocation fails" only;
- condition returns NaN (`:1646`), documented for "a null or wide input or if any working allocation
  fails".

`ganita_mat_pseudo_inv` returns null. The 1.2.3 vocabulary (`src/linalg.cyr:15-23`, ADR 0001) gives
non-convergence its own code, −3, which `ganita_mat_eigen_sym` uses. `ganita_mat_svd`'s doc
(`:1313`) folds it into −1 together with allocation failure.

## Reproduction

`repros/2026-10-03-mat-svd-no-convergence-on-tiny-columns.cyr`. The exit code is the number of wrong
rows. A row is right when the status is 0, both σ are within 4 · 2^-52 · σ₁ (plus one subnormal step)
of the exact values, and U's columns and Vt's rows are orthonormal to 2^-44. The σ test is
normwise, which is what a backward-stable SVD promises. The orthonormality test rejects "return 0
without converging".

The repro covers branches 1 and 2 only. Z, the repeated-row 3×3 and the 5×4 are not rows yet:
`row()` and `ortho()` are written for 3×2, and for Z the U column of the zero σ is not determined by
A, so the orthonormality check needs a rule for it. Until then their bits are given above.

```
cyrius build docs/development/issues/repros/2026-10-03-mat-svd-no-convergence-on-tiny-columns.cyr /tmp/svdtiny
/tmp/svdtiny; echo "exit=$?"      # -> 6 on 1.2.4 .. 1.2.11
```

```
  WRONG A1 t = 2^-513             rc -1  want 0x3ff0000000000000 0x1fe6a09e667f3bcd
  ok    A2 t = nextup(2^-513)     rc 0  S 0x3ff0000000000000 0x1fe6a09e667f3bce  want ...
  ok    A3 t = 2^-512             rc 0  S 0x3ff0000000000000 0x1ff6a09e667f3bcd  want ...
  WRONG A4 t = 1.72 * 2^-543      rc -1  ...
  WRONG A5 t = 2^-1074            rc -1  ...
  WRONG A6 t = 1.6e-308 (subn.)   rc -1  ...
  WRONG B1                        rc -1  want 0x6fcb799cc80a713e 0x4b3326815fe2fa41
  WRONG B2                        rc -1  want 0x35dac74898cd0527 0x0c56594a23ef8276
  ok    C  well-conditioned       rc 0  ...
rows wrong: 6
```

Measured three ways, all giving exit 6:
- from a copy of this repo's tree (cyrius 6.6.12, `src/` at 1.2.11);
- against the stdlib folds of cyrius 6.6.14 and 6.6.3, with the include lines dropped, built from
  directories pinned to each version. All 29 and 28 vendored files byte-match the cyrius tag.

The expected values come from python3 `Fraction` and 80-digit `Decimal`, rounded once.

**The checks were tested against mutants**, on a copy of `src/linalg.cyr`:
- With the `rotated == 1` return removed, so that 1.2.11 returns 0 without converging, A1, A4, A5,
  A6 and B2 still fail, on U's orthonormality: their columns were never rotated. B1 passes. The same
  mutant on top of the branch-1 repair below passes B1 and B2, whose leftover result is correct, as
  branch 2 above says.
- With σ left unscaled (`nrm` for `nrm · scale`) on top of the branch-1 repair, the control C fails.

## What a consumer sees

hisab wraps this as `svd_compute`, which passes ganita's code through, and `svd_truncated`, which
maps any non-zero status to `Err(HSB_ERR_NO_CONVERGENCE)` since 3.3.3. Through 3.3.2 it discarded the
status and copied out temporaries the SVD had never written. Its suite pins `svd_compute(A(2^-513))`
= −1 as a tripwire that fails when this is repaired. It does not test the square zero-row or
repeated-row class, which its `svd_truncated`, a low-rank tool, refuses. Outside this repo, the only
callers of the SVD family are hisab and cyrius's `tests/tcyr/math/linalg.tcyr`; none of hisab's
consumers calls it.

## Proposed fix

**Branch 1 (tested).** Form t without squaring an overflowing ζ. When ζ² is finite, keep the
existing arithmetic bit for bit. Otherwise |ζ| ≥ 2^512, sqrt(1 + ζ²) is |ζ| to working precision,
and t = 1/(2ζ) = γ / (β − α). That quotient is finite and keeps ζ's sign even when ζ itself
overflowed:

```
                    var zeta = f64_div(f64_sub(beta, alpha), f64_mul(f64_from(2), gamma));
                    var zz = f64_mul(zeta, zeta);
                    var t = f64_from(0);
                    if (f64_lt(zz, 0x7FF0000000000000) == 1) {
                        t = f64_div(f64_from(1), f64_add(f64_abs(zeta), f64_sqrt(f64_add(f64_from(1), zz))));
                        if (f64_lt(zeta, f64_from(0)) == 1) { t = f64_neg(t); }
                    } else {
                        t = f64_div(gamma, f64_sub(beta, alpha));
                    }
```

The fix was tested on a copy of 1.2.11, with an old-against-new harness over the 4296-matrix scan
and the 6000 random matrices. The results were bit-identical under cyrius 6.6.3 and 6.6.14.
- **Every input that decomposes today, 7583 of them, returns bit-identical S, U and Vt.** All 7583
  have two columns, and with two columns a pair whose ζ² overflows can never converge, so a
  decomposing input never reaches the new branch.
- **With three or more columns, bits can change.** A second A/B on the 6.6.14 fold ran 4000 random
  matrices of each of six shapes. The 7411 two-column ones that decompose are bit-identical again. Of
  the 12830 3×3, 4×3, 4×4 and 5×4 that decompose, 34 change U or Vt bits and 4 of those also change
  S, all at the ±2100 spread. Each S change is below 10^-200 of σ₁, so it is normwise negligible. But
  one 5×4 σ₄ goes from 5.1144e13, relative error 1.9e-16, to 2.2478e83.
- **No input that decomposes today fails**, in either A/B.
- All 2245 scan failures decompose. So do 463 of the 468 random ones. The repro exits 2 (B1, B2).
- **It does not reach branches 3 and 4.** Z, the repeated-row 3×3 and the 5×4 still return −1. So do
  118 of the 500 random 3×3 zero-row matrices and 493 of the 500 at 10×10.
- On those 2708 inputs the answers are good:
  - σ is within 0.91 u of exact, and ‖U S Vt − A‖ within 0.81 u, where u = 2^-52 · σ₁ + 2^-1074.
  - Vt is orthonormal to 1.66 · 2^-52.
  - U's columns for normal σ are orthonormal to 3 · 2^-52. One input reaches 13.2 · 2^-52; its
    σ₁ is 1.77e308.
  - A U column for a subnormal σ cannot be unit length, since |w_j| is a few subnormal steps. It
    keeps its direction: A5's is (0, 1, −1).
  - 23 inputs return σ₁ = +∞. Every one has an exact σ₁ above DBL_MAX, the same as 364 inputs that
    decompose today.
- `tests/ganita.tcyr` passes 844 / 844, as without the patch.

**Branch 2 (not prototyped).** The threshold has to stop underflowing. That means forming the test,
and ζ, from per-pair scaled columns — the "never a naive sum of squares" rule that
`_linalg_norm2` already follows. Divide each column of the pair by a power of two near its own max
|entry| before forming α, β and γ. Then the test |γ'| > 2^-52 · sqrt(α'·β') is the cosine test,
independent of scale, and ζ follows from α', β', γ' and the two exponents.

That changes the bits of every rotation. It therefore needs its own old-against-new comparison
rather than the bit-identity argument above. LAPACK's `dgesvj` / `dgsvj0` keep column norms apart
from the columns for the same reason. A rotation whose t rounds to 0 is the identity; once branch 1
is fixed, it should not count as progress either.

**Branches 3 and 4 (not designed).** Per-pair scaling does not reach branch 3: there the null
column's cosine with its partner is about 1, so a scale-free test still rotates. That class needs a
rule for a column whose norm is negligible against the largest. Branch 4 needs headroom in the
threshold. The standard bound on the rounding error of an m-term γ is about m · 2^-53 · sqrt(α·β),
which is above the threshold 2^-52 · sqrt(α·β) once m > 2, so the test can ask for more than the
arithmetic delivers, as the 5×4 shows.

**The return code.** If non-convergence moves to −3 to match ADR 0001, `ganita_mat_rank` and
`ganita_mat_condition` should pass the status through rather than map it to their allocation
answers. hisab's `svd_compute` documents −1 for non-convergence, so it would need a doc change;
`svd_truncated` tests `!= 0` and is unaffected.

## Consumer-side workaround

hisab reports it and does not work around it. `svd_truncated` returns `Err(HSB_ERR_NO_CONVERGENCE)`.
`svd_compute` returns ganita's −1, and its doc says to compare the status with 0 and nothing else. hisab's
record is `hisab/docs/development/issues/2026-10-03-ganita-mat-svd-no-convergence-on-tiny-columns.md`.
