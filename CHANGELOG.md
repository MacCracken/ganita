# Changelog

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

## [1.2.12] — 2026-10-04 — the SVD rewritten; NaN and infinite input refused across linalg; toolchain 6.6.15

Three filings closed: two from hisab 3.3.3 and one from the audit that followed them. Each
repro now exits 0 on x86_64 and on aarch64 (qemu), and stays in
`docs/development/issues/repros/` as a regression witness. **`ganita_mat_svd` is a new
algorithm** — one-sided Jacobi on a column- and row-pivoted QR — so every SVD's bits change
([ADR 0005](docs/adr/0005-svd-is-jacobi-on-a-pivoted-qr.md)). **Return codes a caller can see
change:**
- the SVD's non-convergence is −3, not −1;
- a NaN or infinite input is refused across linalg
  ([ADR 0004](docs/adr/0004-non-finite-input.md));
- `rank` passes the SVD's −2 and −3 through;
- `eigen_sym`'s allocation failure is −1, not −2.

No public signature changed and no public function was added. Toolchain **6.6.12 → 6.6.15**.
**1,235 assertions** (was 844).

### Fixed — `ganita_mat_svd` refused finite matrices that have an SVD

Through 1.2.11 the SVD was one-sided Jacobi on A divided by its largest entry. hisab 3.3.3 found
it returning −1, "did not converge", for three classes of finite input:
- square matrices with a zero or a repeated row: 499 or 500 of 500 random ones at every n from 3
  to 10;
- column pairs that needed a very small rotation: A(t) = [[1, t], [t, t], [t, −t]] for every
  t ≤ 2^-513;
- a full-rank 5×4 that two-cycled at rounding level.

rank, condition and pseudo_inv inherited it, answering −1 ("allocation failed"), NaN and null for
[[1, 2, 3], [1, 2, 3], [4, 5, 6]]. The filing traced four branches. Patching them one by one could
not reach the null column, which unpreconditioned Jacobi wears down to a residue still parallel to
its partner. The SVD is now Drmač and Veselić's preconditioned Jacobi (LAPACK dgejsv / dgesvj):
1. A is scaled by a power of two so its largest entry sits near the top of the range (exact).
2. Householder QR with column pivoting and Powell–Reid row pivoting: A·P1 = Q1·R1.
3. For n ≥ 4 the same factorisation of R1ᵀ, and X = R2ᵀ; for n ≤ 3, X = R1ᵀ.
4. One-sided Jacobi on X's columns. Each column is scaled by the power of two of its own largest
   entry, so the test is a cosine at every magnitude, against tol = √n·2^-52, with DGESVJ's second
   stopping test. The test gains an absolute floor near the subnormal range. t = 1/(2ζ) replaces
   squaring ζ past 2^27, and a pair more than 500 binades apart is a projection.

Every sum over m rows is pairwise. After the 60-sweep cap the status is −3. −1 is the single
allocation. Nothing is written to an out-param on any non-zero status. `ganita_mat_svd`'s comment
lists every deviation from the reference, each measured.

Measured against an exact oracle (Python `Fraction` and mpmath, every σ certified correctly
rounded):
- **No finite input is known to reach −3.** This is a measurement, not a proof, so the cap stays.
  - A 20,622-matrix corpus built for the filing passes 20,622/20,622, the 18 non-finite ones as
    −2, in at most 7 sweeps (mean 2.3).
  - 3,809 adversarial matrices built against three candidate repairs pass, in at most 10 sweeps.
  - 819,998 hunted matrices are all status 0.
- **Accuracy** on the corpus:
  - σ within 7.8 u·σ₁ of exact, and U·Σ·Vᵀ = A to 6.9 u·σ₁;
  - U orthonormal to 5.9 u over every non-zero σ, and Vᵀ to 17.7 u;
  - graded matrices (spans up to 600 binades) have every σ within 25 ulps relatively. 1.2.11 was
    off by up to 4.4e19 ulps, and returned one graded 5×4 with two U columns at cosine 0.99999999.
- **x86_64 and aarch64 are bit-identical** on every set.
- **Faster from 8×8 up.** Medians of three interleaved runs pinned to one core, against 1.2.11:
  - 20×20 takes 0.40× the time, 40×40 0.36×, rank 40×40 0.41×;
  - a zero-row 10×10 takes 70 µs, where 1.2.11 spent 726 µs returning −1;
  - 3×3 is unchanged in full (1.00×), and 1.15× in values-only (rank, condition).

The design was chosen by a panel. Three independent repairs ran on a shared harness, an adversary
built inputs against each, and two judges with different lenses scored them. Both judges chose
this one. The other two still returned −3 on inputs that have an SVD: a DGESVJ port without the
QR, and 1.2.11 kept bit for bit with a robust fallback phase. ADR 0005 records why.

**Found by the final verification, and fixed before release.** When A's largest entry is near
DBL_MAX the working copy is scaled down. A column of X whose σ lies within a few binades above
2^-1022 then becomes all subnormal, and the subnormal floor leaves it orthogonal to the others only
to its absolute rounding. For n ≥ 4, U is built from X's columns. It came out 530 u from
orthonormal on a 4096×4 that 1.2.11 passed (by returning σ₂..σ₄ = 0), and 5e4 u on a 2^20×5.

Such a column is now made orthonormal to the others: two Gram–Schmidt passes, with a
coordinate-axis restart if it collapses (private `_linalg_svd_reorth`). Those U columns now come
out to 1.4 u. The fix changes no σ, no V and no other U column:
- the corpus and adv2 are bit-identical with and without it;
- on 12 adversarial matrices the U columns of subnormal σ go from up to 1.7e6 u to 1.3 u;
- a 2,275-matrix hunt aimed at it goes from up to 3.2e15 u to 5.2 u.

The comments' measured numbers that the verifiers re-measured (a floor count, a sweep bound,
descriptions of three adversarial matrices) are corrected.

### Fixed — the SVD family accepted NaN and infinite input

`_linalg_svd_impl` never asked whether A was finite, and a NaN disappeared on the way. The scale
and the column norms are ordered maxima, which a NaN never wins. A NaN cosine fails the
orthogonality test, so its pair counted as converged. An all-NaN 2×2 came back as status 0 with
σ = (0, 0); [[NaN, 0], [0, 2]] as status 0 with the finite σ = (2, 0). rank, condition and
pseudo_inv followed with rank 0 or 1, −1.0 ("singular") and a matrix of zeros.

Now one exponent-bit scan (`_linalg_all_finite`) refuses a NaN or infinite entry with −2 before
any work. rank passes the −2 through, condition gives NaN and pseudo_inv null. The repro goes from
18 to 0.

### Fixed — the rest of linalg accepted NaN and infinite input

The audit that followed found the same defect in 22 silent cases across eigen_sym, qr,
least_squares, lu_solve, cholesky_solve, cholesky, det, max_norm, eq and is_symmetric. Two
mechanisms caused nearly all of them:
- an infinite entry made every relative threshold +∞, so qr returned Q = I and R = A, and
  eigen_sym the raw diagonal, with status 0;
- an ordered comparison dropped a NaN. least_squares fitted x from a single row of A, and eq
  accepted any two matrices under a NaN tolerance.

lu, inv and gaussian_elim refused an infinity only through the same accident, and only while
`LINALG_EPS > 0`.

[ADR 0004](docs/adr/0004-non-finite-input.md) records the rule now applied. **Every function that
judges a matrix refuses a NaN or infinite entry in its own failure shape, before it writes
anything. Every function that only carries values propagates it.**
- `_linalg_all_finite` guards eigen_sym, qr, least_squares (A and b), lu and inv, det (NaN, not
  +0.0), gaussian_elim (the whole augmented matrix, so a NaN right-hand side refuses too),
  cholesky, lu_solve and cholesky_solve (the factor and b).
- `_linalg_tol_ok` refuses a NaN, infinite or negative tolerance in eq and is_symmetric. Both
  fail closed on infinities, which compared equal only because |∞ − ∞| is NaN. is_symmetric also
  reads the diagonal now, as its doc always said.
- max_norm, a carrier, no longer drops a row whose sum is NaN.
- frobenius recomputes with the largest magnitude scaled out only when the plain sum is +∞ or
  below 2^-969, so [[1e200, 1e200]] has a finite norm and every other input keeps its bits.
- `ganita_mat_print` shows NaN, inf and -inf (was 0/100 and ±INT64_MAX/100).

Also fixed, outside the 22 cases:
- lu_solve refuses a pivot index outside [0, n), a zero pivot and a non-square factor (the index
  and the shape read out of bounds);
- cholesky_solve refuses a non-square factor, and checks before its `alloc`;
- eigen_sym returns −1, not −2, when its working copy cannot be allocated.

The repro goes from 22 to 0. Each scan costs one O(m·n) pass ahead of an O(n³) function.

### Changed — the failure codes follow ADR 0001 (amended)

- **cholesky and gaussian_elim are listed as exceptions next to lu.** They return 1 on success
  and 0 on any failure. The rule is `< 0` on every status function except those three, and
  `== 0` on them. They stay 1/0 so that no caller's `== 0` test breaks.
- **SVD non-convergence is −3**, not −1, which ADR 0001 reserves for allocation failure. No finite
  input is known to reach it.
- **rank passes the SVD's status through.** It mapped every SVD failure to −1, which is how a
  singular matrix read as "out of memory".

### Tests

**844 → 1,235 assertions**, green on x86_64 and on aarch64 (qemu), with output byte-identical.
Four new groups:
- SVD family, non-finite input: 19;
- linalg, non-finite input: 87, including the two predicates called directly;
- the SVD: 225. Every row is checked against the exact σ under bounds about twice what 1.2.12
  measures; the measures use TwoSum and TwoProduct, so the test's own rounding does not count.
  The rows:
  - A(t) at four t, B1 and B2;
  - the zero- and repeated-row squares, and W54 at two scales;
  - graded and row-graded matrices, asked for relative accuracy;
  - the tall 512×2, and the 8×4 and 4096×4 of the U fix;
  - every special branch end to end;
  - rank, condition and pseudo_inv on the textbook singular matrices;
  - the guards no input reaches, tested on the helpers directly.

  The U check covers every non-zero σ, not only normal ones.
- the SVD's building blocks, called directly: 60.

Mutation runs against the suite:
- 22 of 25 SVD mutants fail it. The 3 survivors are equivalent.
- 27 of 29 non-finite guard mutants fail it. The survivors are an equivalent pair in eq: either
  check alone refuses the case.
- 4 of 5 mutants of the U re-orthonormalisation fail it. The survivor, one Gram–Schmidt pass
  instead of two, stays within about 2 u because only a column that keeps half its length is
  accepted.

Word-boundary coverage is 173/190 (91 %; was 152/170): every new helper is called by name. CI's
floor for it rises **89 → 91**. Tool coverage is 142/142. Bench: four `mat_svd` rows in
`tests/ganita.bcyr` (3×3, 20×20, 40×40, and a 10×10 with a zero row).

### Added — `scripts/svdh/`, the SVD's evaluation harness

The measurements above come from a harness that now ships with the repo: the corpus generator
and its exact oracle (Python `Fraction` and mpmath, every σ certified correctly rounded), the
scorer, the Cyrius drivers (full and values-only SVD; rank, condition and pseudo_inv), the
adversarial sets, both hunts, the D1-family hunt, and a bench. Every generator rebuilds its data
byte for byte, and its README lists the reference checksums and scores for 1.2.12 and for 1.2.11
(`tree-at.sh` exports any revision's `src/`), so a later change to the SVD can be measured the
same way. It is a manual tool, not a CI step: it needs Python with mpmath and numpy
(`scripts/svdh/requirements.txt`), and it writes only under `build/svdh/`. The sweep and branch
counts quoted in the source comments came from temporary instrumentation, and the row-graded
study and the 2^20×5 run from one-off scripts; neither is carried.

### Changed

- **Toolchain pin 6.6.12 → 6.6.15**, moved and gated before any `src/` change (844/844 on the
  1.2.11 source). `lib/` was re-vendored with `cyrius lib sync --full`: 112 files, 16 changed and
  `tls_hostid.cyr` new, `diff -rq` clean against the published 6.6.15 tarball. That tarball was
  the source, not the local install: on 2026-10-03 the local `~/.cyrius/versions/6.6.15` was an
  in-flight build reporting the same version, with a different `cycc` and 6 different `lib/`
  files. `cyrius.lock` re-locked, `dist/` regenerated.
  - In `lib/math.cyr`, `f64_le`, `f64_ge` and `f64_trunc` became compiler builtins at 6.6.13,
    and NaN still gives 0 for the two comparisons. ganita's nine `f64_le` / `f64_ge` call sites
    compile to them unchanged. `_f64_rem_pio2`, behind tan, is byte-identical.
  - `lib/ganita.cyr`, ganita's own fold vendored back, is 1.2.11 at this pin (6.6.12 carried
    1.2.9).
- ADR 0001 is amended, and ADRs 0004 and 0005 are new. README, the examples' failure table,
  `docs/development/state.md` and the roadmap are refreshed. Two archived filings, from 1.2.11
  and 1.2.4, linked to the ADR and audit folders one directory short; fixed.

### Known

- **σ₁ within a few ulps of DBL_MAX can come back +∞.** 7 of 563 matrices built for it do; 1.2.11
  kept 4 of those finite. The cause is the final rounding, which any floating-point SVD has. It is
  documented at `ganita_mat_svd`.
- **pseudo_inv and condition go wrong at the two ends of the range** (pre-existing). A kept σ
  below 2^-1024 gives NaN entries. A σ₁ that overflows makes condition call DBL_MAX·[[1, 1], [1,
  −1]] singular, and pseudo_inv return zeros. Filed as
  [`2026-10-04-svd-derived-functions-at-the-range-ends`](docs/development/issues/2026-10-04-svd-derived-functions-at-the-range-ends.md);
  its repro gives 5 on both 1.2.11 and 1.2.12.

### Consumers

cyrius 6.6.15 carries ganita 1.2.11. 1.2.12 is built and gated on cyrius 6.6.15 for the next
cyrius fold, and changes no public signature. A caller that pinned SVD bits, or read −1 from the
SVD as "did not converge", sees the changes above.

## [1.2.11] — 2026-10-01 — the six 2026-09-30 filings closed; `tan` in f64 and f32; toolchain 6.6.12

Six filings closed: four from abaco (2.4.8 – 2.4.11), one from hisab, one from abaco's final
review. Each one's repro now exits 0 on x86_64 and on aarch64 (qemu), and stays in
`docs/development/issues/repros/` as a regression witness. **New public functions:**
`ganita_f64_tan`, `ganita_f32_tan` and the alias `f64_tan`. **Requirement:** the three tangent
functions need stdlib `math` from cyrius **6.6.9** or later
([ADR 0003](docs/adr/0003-tan-uses-stdlib-rem-pio2.md)). Toolchain **6.6.11 → 6.6.12**.
**844 assertions** (was 597).

All accuracy figures below are worst errors against mpmath (≥ 320 bits, worst points rechecked at
1000), on dense grids plus targeted hunts, on both architectures. "Bit-identical across targets"
is claimed only for the new kernels and for tan. sinh/cosh from 22, asinh/acosh from 2, asin
and atan2 call target builtins, and those differed by target before 1.2.11 too.

### Fixed — `ganita_binomial` refused C(n, k) that fit in i64

Its contract says −1 means "the true value does not fit in i64". Since 1.2.3 it actually meant
"`min(k, n−k)·C(n, k)` does not fit". So `binomial(62, 31)`, `(66, 33)`,
`(2^32, 2)` and every other value above `i64_MAX / min(k, n−k)` came back −1. Every value it did
return was exact; abaco 2.4.8 hit the refusals. Now it multiplies first while `C(n, i)·(n − i)`
fits, the 1.2.10 arithmetic. Otherwise it divides through `gcd(C(n, i), i + 1)` first
(private `_gn_gcd`), so the only product formed is `C(n, i + 1)` itself. It returns −1
**exactly** when C(n, k) > i64_MAX. Over 30,040 cases against Python's exact `math.comb` there
are 0 mismatches on either architecture; 1.2.10 misses 3,848. The CWE-834 loop bound still
holds: it refuses by the 34th iteration. `binomial(66, 33)` now takes ~230 ns to answer, where
1.2.10 took 99 ns to refuse; `(61, 30)` is unchanged at ~128 ns.

### Fixed — `ganita_f64_atan2`: signed zeros, a NaN `y` at `x = ±0`, and two infinities

`atan2` decided its quadrant with `f64_eq` / `f64_gt`, which cannot see the sign of a zero. It
tested nothing for infinity, so:
- `atan2(−0, +0)`, `(+0, −0)`, `(−0, −0)` and `(−0, x < 0)` lost the sign or the ±π;
- `atan2(NaN, ±0)` fell through to −π/2;
- all four `(±∞, ±∞)` were `∞/∞ = NaN`.

hisab found the signed-zero rows through `cx_arg(cx_conj(z))`, which cyrius 6.6.8's IEEE
`f64_neg` made reachable. abaco found the NaN and infinity rows.

Now NaN is handled first, zeros are decided on their sign bits, and both-infinite returns
±π/4 or ±3π/4. On the full C99 F.10.1.4 table (289 pairs from 17 values) every special row
is bit-exact; 1.2.10 fails 19. Every finite non-zero pair keeps the 1.2.10 arithmetic **bit for
bit** (1,000,000 random pairs, both architectures). Cost: about 4 ns per call (57 vs 53 ns).

**One deliberate choice:** a NaN argument returns **the NaN operand** (y first), payload kept,
as `ganita_f64_hypot` and every one-argument function in the module do. C99 asks only for a NaN.
`ganita_f32_atan2` follows: `(±inf, ±inf)` gives `0x3F490FDB` / `0xBF490FDB` /
`0x4016CBE4` / `0xC016CBE4`, and `atan2(−0, −1)` gives `0xC0490FDB`.

### Fixed — sinh / tanh / atanh / asinh / acosh / asin cancelled just above their cutoffs

1.2.4's small-|x| guards return `x` below 2^-26 (1e-8 for asinh). Just above the guard, each
function still evaluated a form that differences two numbers near 1, losing about eps/|x|
relative. acosh lost the same way in x − 1 near 1, and asin near ±1 formed `1 − x·x`.
Two private fdlibm 5.3 ports now carry the band: `_gn_expm1` (`s_expm1.c`) and `_gn_log1p`
(`s_log1p.c`). Each was re-checked constant by constant; their worst errors are 0.83 and
0.84 ulp, bit-identical on both architectures. The reroutes:
- sinh, for |x| < 22, and tanh, for 2^-26 ≤ |x| ≤ 20, go through expm1;
- atanh, asinh (1e-8 ≤ |x| < 2) and acosh (1 ≤ x < 2) go through log1p;
- asin forms `1 − x²` as `(1 − |x|)(1 + |x|)` from |x| = ½ up.

sinh, tanh and atanh now compute on |x| and re-sign, so all five odd functions are **odd bit for
bit**. Worst error, 1.2.10 → 1.2.11:

| function | band | 1.2.10 | 1.2.11 |
|---|---|---|---|
| sinh | 2^-26 ≤ \|x\| < 1 | 3.98e7 ulp | 1.77 |
| tanh | 2^-26 ≤ \|x\| < 1 | 3.36e7 | **2.18** (see below) |
| atanh | 2^-26 ≤ \|x\| < 1 | 3.17e7 | 1.70 |
| asinh | 1e-8 ≤ \|x\| < 1 | 1.33e8 | 1.61 |
| acosh | 1 < x < 2 | 2.52e7 | 2.12 |
| asin | ½ ≤ \|x\| < 1 | 1,021 | 1.38 |
| tanh | 1 ≤ \|x\| ≤ 20 | 2.43 | 0.81 |
| sinh | 1 ≤ \|x\| < 22 | 1.86 | 1.17 |

The new code has the lower worst error in every sub-window of every band. **tanh and acosh are
not within 2 ulp:** fdlibm's forms reach 2.18 and 2.12. About 0.08% of tanh on [0.21, 0.26] is
over 2 ulp, and 3 of 200,000 dense acosh points. None is more than 2 bit patterns from correctly
rounded. No bound is proven. Cost: about 20–25 ns more per call in the band (sinh(1e-3)
56 → ~80 ns), and sinh / tanh roughly double at 1 ≤ |x| < 22 (55 → ~110 ns).

### Fixed — sinh / cosh were up to 496 ulp off for 709 < |x| ≤ 710.4759

Past exp's overflow, both returned `exp(|x| − ln 2)`. Rounding `|x| − ln 2` near 709 cost up to
half an ulp of 709, and exp amplified that to ~500 ulp. The filing's `(w/2)·w`, w = exp(|x|/2),
was still 3 bit patterns off on aarch64, so a different form shipped: the private
`_gn_exp_half`.
- Up to exp's own threshold it is 0.5·exp(|x|).
- Above it, it is FreeBSD `k_exp.c`'s exp(|x| − c)·2^1023·2^1019, with c the double nearest
  2043·ln 2. |x| − c is exact, and the multiplies can only overflow.
- 2043 is the k in 512..2047 whose k·ln 2 lies nearest a double.

Over 242,000 band points the worst is 1.04 ulp on x86_64 and 0.96 on aarch64, never more than
1 bit pattern from correctly rounded. The largest finite argument still gives
`0x7FEFFFFFFFFFFD3B`.

### Fixed — `cosh` was not even

`ganita_f64_cosh` evaluated `exp(x)` on the signed argument, so a negative x formed e^|x| as the
rounded `1/exp(x)`. About one argument in six came back an ulp from its mirror, the same defect
this release fixes in sinh. It now computes on |x|. Found by the merged-tree mutation review.

### Added — `ganita_f64_tan`, `f64_tan`, `ganita_f32_tan`

There was no tangent, so consumers divided `f64_sin(x)` by `f64_cos(x)`: up to 2 ulp off,
correctly rounded at ~68% of arguments. abaco 2.4.10 carried its own kernel.

`ganita_f64_tan` ports fdlibm 5.3 `s_tan.c` + `k_tan.c`
(private `_gn_k_tan`) and reduces through stdlib math's `_f64_rem_pio2`, the reducer
`f64_sin` / `f64_cos` use. It is within 1 ulp everywhere measured (worst found 0.940 ulp). On
[−π/2, π/2] the worst is 0.77 ulp with 96.4% correctly rounded; the quotient gives 1.84 ulp
and 68.4%. It is 5–24% faster than the quotient.

`ganita_f32_tan` widens onto it and is **correctly rounded for every f32**. All 2^31
non-negative finite f32 values were scanned on both architectures. 45 lie within 16 double-ulps
of an f32 midpoint, and every one rounds correctly by mpmath.

`f64_tan` joins `_compat` (55 aliases), as `f64_cbrt` did at 1.2.6: under the
stdlib-style name the consumer reaches for.

⚠ `_f64_rem_pio2` is stdlib-private and first shipped in **cyrius 6.6.9**. On a 6.6.0 – 6.6.8
stdlib, the bundle still builds and every other function is unchanged. x86_64 builds print
`warning: undefined function '_f64_rem_pio2'`, and calling a tangent function is a
compile-time error. [ADR 0003](docs/adr/0003-tan-uses-stdlib-rem-pio2.md) records why.

### Tests

**597 → 844 assertions**, green on x86_64 and on aarch64 (qemu). Five new groups:
- binomial: 37, including an in-suite Pascal sweep of every n ≤ 70;
- atan2's C99 table: 65;
- the cancellation band: 58;
- the overflow band: 13;
- tan in f64 and f32: 73.

There is also one row in the alias group. Every expected f64/f32 value is a correctly rounded
bit pattern.

Each unit was verified by an independent adversarial agent: its own oracle sweeps on both
architectures, and mutation tests. A 180-mutant campaign on the merged tree then left 45 real
survivors, among them sinh's 22 cut, which could move down to 5 and give 1.4e11 ulp at
sinh(5.5) with the suite green. 30 rows were added and every survivor now fails. The 53 that
remain are equivalent, by proof or exhaustive check.

Tool coverage is 142/142. Word-boundary coverage is 152/170 (89.4%; was 144/162), so CI's floor
for it rises **88 → 89**. Bench: 16 new rows in `tests/ganita.bcyr` (binomial, atan2, the
hyperbolic band, tan versus sin/cos).

### Changed

- **Toolchain pin 6.6.11 → 6.6.12**, moved and gated before any `src/` change. `lib/` was
  re-vendored with `cyrius lib sync --full`: 111 files, 22 changed, `lib/math.cyr` not among them,
  `diff -rq` clean against the snapshot. `cyrius.lock` re-locked, `dist/` regenerated. Verified
  against the published 6.6.12 tarball in an isolated `CYRIUS_HOME`.
- **`cyrius audit` docs are complete again.** The 1.2.8 pow helper `t_pw1` had no doc comment,
  so audit reported one undocumented fn. CI does not run audit.
- `cyrius.cyml`, `scripts/consumer-check.sh` and the module header no longer say x86_64 needs no
  `math` at build time. That was already false in 1.2.10 (`F64_LN2`).
- **Records corrected.** `archived/2026-09-07-f64-transcendental-accuracy.md` said "all four
  groups closed" at 1.2.4. Its §1 band, §2 overflow accuracy, §3 acosh near 1 and §4 atan2
  stayed open until now, and an addendum says so. `archived/2026-09-07-f32-nan-inf-edges.md` §2
  blamed `exp` for f32 atan2's NaN.
- README, getting-started, roadmap and `docs/development/state.md` are refreshed. ADR 0003 is new.

### Consumers

abaco and hisab get these fixes when cyrius next folds ganita: 6.6.12 ships `lib/ganita.cyr`
1.2.9. abaco can then drop `abaco_binomial` and `_eval_k_tan`, and hisab can test `cx_arg` on
the signed-zero branch cut.

## [1.2.10] — 2026-09-30 — toolchain 6.6.11; the tool coverage floor is 100

CI only. Toolchain **6.6.10 → 6.6.11** (the vendored `lib/` is the full 6.6.11 snapshot).
No source or public signature changed; **597 assertions**, unchanged.

### Changed — `cyrius coverage --min 98` → `--min 100`

The floor sat at 98 because the ≤ 6.6.10 tool counted the two entry points —
`src/main.cyr` and `src/test.cyr` `main` — which nothing can call: 139/141. cyrius 6.6.11
excludes an entry point from the count, and at that pin ganita is 139/139 (100 %). The rise
lands in the same commit as the pin move, because the wrapper runs the manifest-pinned CLI:
with this `ci.yml` and the pin left at 6.6.10 the step fails (`coverage gate FAILED: 98% <
--min 100%`, the two `main`s listed as unreferenced). The comment above the step is
rewritten to say so. The word-boundary floor (`scripts/coverage-honest.sh 88`) is a separate
count and is unchanged.

### Changed

- **Toolchain pin 6.6.10 → 6.6.11.** `lib/` re-vendored with `cyrius lib sync --full`
  (111 files, `diff -rq` clean against the 6.6.11 snapshot; 21 files changed, including the
  `lib/ganita.cyr` fold of 1.2.9); `cyrius.lock` re-locked; `dist/` regenerated with
  `cyrius distlib --all` (version header only; the `.deps` sidecar is unchanged).
- README, `docs/development/state.md` and `docs/development/roadmap.md` name the 6.6.11 pin
  and the 100 % floor.

## [1.2.9] — 2026-09-29 — f32 `sin` / `cos` are correct past 2^63

Toolchain **6.6.9 → 6.6.10** (the vendored `lib/` is the full 6.6.10 snapshot). No
public signature changed. **597 assertions** (was 589). Reported by cyrius 6.6.11 bite 14;
re-vendored into cyrius 6.6.11 as `lib/ganita.cyr`.

### Fixed — `ganita_f32_sin` / `ganita_f32_cos` returned NaN for |x| ≥ 2^63

The 1.2.x guard returned NaN at and above 2^63 because stdlib's `f64_sin` / `f64_cos`
used to reduce only within the i64 range and returned the argument past it. cyrius
6.6.9 made both within 1 ulp for every finite argument on every target, so the guard
now threw away a correct value: `ganita_f32_sin(2^70)` was NaN where the answer is
-0.99817944 (`0xBF7F88AF`). The guard (`_F32_TRIG_LIMIT`, `_f32_trig_limit`) is gone and
both are `f32_from(f64_sin|cos(f32_to(x)))` again. Roughly a quarter of the finite f32
exponent range is above 2^63. ±inf and NaN still give NaN.

### Changed — the matrix / linalg headers named retired stdlib files

`src/matrix.cyr` said `Usage: include "lib/matrix.cyr"` and `src/linalg.cyr` said
`include "lib/linalg.cyr"` / `Requires: … matrix.cyr`. Neither file has existed in
cyrius's `lib/` since the carve; a consumer gets both layers through `lib/ganita.cyr`.
The headers say so now. Comment only (the text is carried into the fold, which is why
it is fixed here and not in cyrius's copy).

### Tests

- The two rows that pinned NaN for `sin` / `cos` of 2^70 now assert the correctly rounded
  f32 (reference: libm on the exact f32 input, rounded to f32), plus rows for -2^70, the
  old boundary 2^63 and `FLT_MAX`, an in-[-1, 1] row, and ±inf → NaN. Against 1.2.8's
  `math_f32.cyr` 8 of them fail. Same results on aarch64 (qemu).

### Changed

- **Toolchain pin 6.6.9 → 6.6.10.** `lib/` re-vendored with `cyrius lib sync --full`
  (111 files, `diff -rq` clean against the 6.6.10 snapshot); `dist/` regenerated with
  `cyrius distlib --all` (reproducible; the `.deps` sidecar is unchanged).

## [1.2.8] — 2026-09-28 — `pow` is within 1 ulp everywhere

Toolchain **6.6.7 → 6.6.9** (the vendored `lib/` is the full 6.6.9 snapshot). No
public signature changed. **531 assertions** (was 521; one of the new ones folds 108
reference rows).

### Fixed — `ganita_f64_pow` (and `f64_pow`, `ganita_f32_pow`) was hundreds of ulp out

Both finite paths lost accuracy, silently:

- the general path `exp(y·ln x)` turns the rounding of `y·ln x` into a relative error
  of about |y·ln x| ulp — **909 ulp** at |y·ln x| = 667, and only 46 % of 20,000
  log-uniform inputs came back correctly rounded;
- the 1.2.4 binary-exponentiation path (integral |y| ≤ 1024) doubles its relative
  error at every squaring — **772 ulp** for `pow(1.0000144, -916)`, 1 % correctly
  rounded. It was exact only when every intermediate square was.

Every finite case now goes through `_gn_pow_pos`, a port of fdlibm's `e_pow.c` core:
`log2(x)` and `y·log2(x)` carried in about 70 bits, then `2^(p_h + p_l)` by an integer
plus a rational approximation, with subnormal results scaled in one rounding. Measured
against a correctly rounded reference: **≤ 1 ulp** on both 20,000-input premise sweeps
(was 909 / 772; 94 % / 90 % exact), with bit-identical results on x86_64 and aarch64 (qemu);
a bit-exact model of the same algorithm is ≤ 1 ulp on 200,000 inputs over the whole exponent
range, subnormals included. An integer power that is representable is
still exact (`pow(7, 2)`, `pow(10, 15)`, `pow(10, 22)`, `pow(3, 33)`, `pow(2, -1074)`).
The C99 Annex F special cases (1.2.7) are answered first, unchanged.

Every f64 operation in the new code is an `f64_*` call and every word manipulation is
integer arithmetic on bit patterns: no builtin's result is an operand of `+ - * /`,
because cyrius 6.6.10 makes that a float operation, and the fold must mean the same on
every toolchain.

### Tests

- `math: f64 pow — within 1 ulp of the correctly rounded value, everywhere (1.2.8)`:
  108 reference rows (glibc `pow`, each re-checked against an 80-digit decimal power) —
  56 across the exponent range, 12 with `x` within 1e-7 of 1 and |y| up to 3e9, 10
  subnormal bases, 10 subnormal results, and the 20 worst inputs of the two old paths —
  plus 8 exactness / range rows. **1.2.7 fails 94 of the 108.**

### Changed

- **Toolchain pin 6.6.7 → 6.6.9.** `lib/` re-vendored with `cyrius lib sync --full`
  (111 files, `diff -rq` clean against the 6.6.9 snapshot); `dist/` regenerated with
  `cyrius distlib --all` (`--check` current, `consumer-check.sh` clean).

### Tests — every back-compat alias is exercised (CI coverage floor)

- cyrius 6.6.8's `cyrius coverage` counts a REFERENCE, not a substring, and every `_compat` alias name
  is a substring of the canonical it forwards to — so the old counter credited all 54 aliases while
  this suite called five. Under the 6.6.9 pin the real figure was **60%** against CI's **94%** floor,
  and CI went red. The floor was not lowered: a new group checks every alias against its `ganita_*`
  twin on the same inputs (which also pins that each forwards to the right function), and a second
  covers the five canonicals no row called (`ganita_mat_scale` / `_dot` / `_print`,
  `ganita_f64_asin` / `_atan2`). Suite **589/0** (was 531). Coverage **98%** (139/141; the two
  unreferenced are `main` entry points); the word-boundary count **88%**. Both CI floors were
  RAISED to the measured values (94 -> 98, 58 -> 88). No `src/` or `dist/` change.

## [1.2.7] — 2026-09-27 — `pow` follows the C99 Annex F table

Toolchain **6.6.4 → 6.6.7** (the vendored `lib/` is the full 6.6.7 snapshot). No
public signature changed. **521 assertions** (was 491).

### Fixed — `ganita_f64_pow` (and `f64_pow`, `ganita_f32_pow`) on infinities, NaN and ±0

`pow` returned NaN for every infinite base or exponent that missed the integral fast
path, and the NaN check ran ahead of the `pow(1, y) = 1` rule. Silently: a defined
IEEE-754 result replaced by NaN, no diagnostic. Found by the cyrius 6.6.8 audit
(filed there as `audit:ganita-pow-infinity-and-nan-semantics`).

| call | before | C99 Annex F |
|---|---|---|
| `pow(+inf, 0.5)`, `pow(-inf, 0.5)` | NaN | +inf |
| `pow(2, +inf)`, `pow(0.5, -inf)` | NaN | +inf |
| `pow(0.5, +inf)`, `pow(2, -inf)`, `pow(inf, -0.5)` | NaN | +0 |
| `pow(1, NaN)`, `pow(1, ±inf)`, `pow(-1, ±inf)` | NaN | 1 |
| `pow(-0, 3)` / `pow(-0, -3)` | +0 / +inf | -0 / -inf |

`ganita_f64_pow` now answers the whole table explicitly before the `exp(y·ln x)`
path: `pow(x, ±0) = 1` and `pow(+1, y) = 1` for every x and y (NaN included), then
NaN, then a zero base (its sign survives an odd integral exponent), an infinite
exponent (only `|x|` against 1 matters), and an infinite base (the sign of `y` picks
inf or 0; an odd integral `y` keeps `-inf`'s sign). The 1.1.4 comment that called
the `-0` rows untestable was wrong: a bit-pattern literal always produced `-0`.

On aarch64, `pow(2, 1100)` returned **-1.5e-285** and `pow(2, -1100)` -2^948: past
the integral path's 1024 bound the general path calls `f64_exp`, whose aarch64
polyfill wrapped the `2^n` exponent into the sign bit. That half is fixed in the
toolchain (cyrius 6.6.8's fdlibm `exp`/`ln`); the rows here pin it on x86, and
cyrius's `tests/tcyr/crossos/f64_pow_domain.tcyr` pins it on the ARM hosts.

### Changed

- Three stale comments said the stdlib's `f64_exp` returns NaN for an infinite
  argument (the `math_advanced` header's INFINITY policy, sinh, `ganita_f32_exp`),
  the header calling its guards "a workaround, not a fix". It has not since cyrius
  6.6.1; the guards stay, the comments now say why.

## [1.2.6] — 2026-09-16 — a correctly rounded cube root, and the backlog closed

Closes both open filings. tanmatra's filing asked for an f64 cube root. The 1.2.3
performance backlog had carried three items since 1.2.4, two thought to need a
public API change and one a policy decision. Toolchain **6.6.2 → 6.6.4**. No public
signature changed. **491 assertions** (was 433).

### Added — `ganita_f64_cbrt`, correctly rounded for every f64

⭐ ganita and the stdlib had no f64 cube root, so a consumer wrote `pow(x, 1/3)`,
which is wrong in the last bits for structural reasons. `1/3` rounds **down**, so
perfect cubes came back low: `cbrt(8) = 1.9999999999999998`, `cbrt(1728) =
11.999999999999995`. And `exp(y·ln x)` turns half an ulp of error in the exponent
into a relative error that grows with `|ln x|`: 137 ulps at 1e-300. Filed by
**tanmatra** ahead of its Rust → Cyrius port, whose golden values come from Rust's
`libm::cbrt`. The filing's repro, run with its candidate swapped as it specified:

| Group | guarded `pow` workaround | `ganita_f64_cbrt` |
|---|---|---|
| A: ±0, ±inf, NaN, sign-exact | 0 / 5 wrong | 0 / 5 |
| B: `cbrt(±k³) = ±k`, k = 1..1000 | **1752 / 2000** wrong | **0 / 2000** |
| C: correctly rounded rows | **6 / 12** wrong | **0 / 12** |

The filing's contract allowed "correctly rounded, or a stated bound under 1 ulp".
This delivers the first. The result is odd and sign-exact, handles `±0`, `±inf` and
NaN, and never forms an intermediate that can overflow or underflow:

- **Split** — `|x| = m·2^(3k)` with `m` in `[1, 8)`, a subnormal scaled by 2^54
  first. The `2^k` is a bit operation, which is the whole far-from-1 error class
  gone.
- **Approximate** — a Chebyshev line for `cbrt` on `[1, 2)`, then two Halley steps
  on `y³ = m`. That lands within 1.17 ulp.
- **Round, exactly** — the root is above the midpoint `(2Y+1)·2^-53` iff
  `(2Y+1)³ < mant·2^(107+r)`. Both sides are integers, compared in 26-bit limbs
  (`_f64_cbrt_cmp`). The approximation only decides *how many* comparisons run: two
  for ~92% of inputs, three for the rest. The walk is capped and hands over to
  bisection (`_f64_cbrt_bisect`), so termination does not rest on the bound either.

Checked against an exact integer oracle on **5,838,393 inputs**: every perfect cube
below 2^53 with its ±1 neighbours, every power of two with its neighbours,
3,000,000 random bit patterns, 1,000,000 random subnormals and 1,000,000 random
significands in `[1, 8)`. **0 mismatches.**
Cost: ~105 ns per call, **1.1–1.15×** the guarded `pow` form it replaces.
`f64_cbrt` joins `_compat.cyr` beside `f64_pow`, as the filing asked.

### Changed — `ganita_f32_cbrt` widens onto `ganita_f64_cbrt`

It was `sign(x)·pow(|x|, 1/3)`. It is now the narrowed f64 root, and so **correctly
rounded for every f32**. That was checked **exhaustively**: over all 2,139,095,039
positive finite f32 values, no f64 result lands exactly on an f32 midpoint, so
narrowing cannot misround, and every negative input mirrors its positive bit for bit.
The filing expected the f32 tests to stay green, and they did — its perfect cubes
never moved. The same sweep found the pow form **one ulp out on exactly 13 inputs**
(26 with negatives), all at the small and large ends where pow's error grows. Those
are the only f32 results that change, and four of them are now assertions. The
guards for zero, NaN and infinity stay; they are cheaper than the call.

### Optimized — the performance backlog, closed without an API change

Measured against 1.2.5 in one process on identical inputs. Old and new ran side by
side on 400 random cases — square, tall, singular and rank-deficient — with **0 bit
differences** in any result, and each comparison was mutation-verified.

| | time | bytes taken from the allocator per call |
|---|---|---|
| `mat_inv` 60×60 | **1.17–1.20×** | 87,872 → 59,072 |
| `mat_inv` 120×120 | **1.18×** | 348,512 → 233,312 |
| `mat_qr` 120×120 | unchanged (±1%) | **116,176 → 960** |
| `mat_qr` 200×40 | unchanged | **321,616 → 1,600** |
| `pseudo_inv` 40×40 | unchanged | 90,352 → 64,720 |
| `pseudo_inv` 200×40 | unchanged | 296,432 → 219,600 |
| `mat_mul` 120×120 | unchanged (±1%) | unchanged |

The allocator never frees, so bytes a call throws away are bytes the process never
gets back. That is the whole cost `qr` and `pseudo_inv` were paying.

- **`ganita_mat_inv`** no longer calls `ganita_mat_lu_solve` n times, each call
  allocating its own scratch — 8n² bytes discarded per inverse. One scratch column
  serves every column. Forward substitution starts at the row where `P·e_k` keeps its
  1, since every entry above it is exactly zero; the old code substituted densely
  against the unit vector. Back substitution runs in place. **Also fixed:** the old
  loop ignored `lu_solve`'s return, so a failed scratch allocation copied a stale
  solution into the inverse and returned success.
- **`ganita_mat_qr`** transposes its square Q **in place**. It used to build a whole
  transposed copy, copy it back and discard it — a second m×m allocation, and an
  allocation-failure return for what is only a permutation.
- **`ganita_mat_pseudo_inv`** forms neither V nor Uᵀ. It scales V^T's rows, which are
  V's columns, and the multiply kernel stores `(U·Σ⁺V^T)^T` directly. The products
  and their summation order match the old path's exactly.
- `ganita_mat_mul`'s pointer walk moved into **`_ganita_mat_mul_into(a, b, c,
  transposed)`**, so the library's one open-coded row-and-column pointer walk still
  exists exactly once. The output stride is chosen per row, and the plain
  multiply pays nothing per element for the transposed form.

No `ganita_mat_transpose` call is left in `linalg.cyr`.

### Decided — `GANITA_MAT_MAX_ELEMS` stays a policy limit (ADR 0002)

The third backlog item was a policy question, and
[ADR 0002](docs/adr/0002-element-cap-is-policy.md) answers it. The cap **stays at
33,554,430** (256 MiB of elements), one eighth of what one allocation can hold.
Nothing here can finish on a matrix that size anyway: a square at the cap is ~9.5
minutes of `mat_mul` and ~11 hours of `eigen_sym`. The allocator never frees, so a
decomposition's working set is a multiple of it. And no consumer has asked for
more. Two assertions pin it: the value, and `GANITA_MAT_MAX_ELEMS <= (ALLOC_MAX -
16) / 8`, so a future stdlib that shrinks the allocator fails the pin bump instead
of silently becoming the binding limit. The ADR also says when to revisit it.

### Changed — toolchain 6.6.2 → 6.6.4

`lib/` re-vendored with `cyrius lib sync --full`: 110 files, 22 changed, 0 differ from
the snapshot. The pin bump alone was green before any source change. The finished
release was then gated twice: once on the installed toolchain, and once on the
published 6.6.4 release tarball (sha256 matching its `.sha256`), unpacked into an
isolated `CYRIUS_HOME`. Both runs were green, the second on the whole gate including
`lib/` against the tarball's snapshot.

The `f64_exp(±inf) = NaN` defect ganita filed upstream was fixed at cyrius 6.6.1. The
guards in `sinh`/`cosh` and the f32 `exp`/`exp2` stay: they cost one compare, and
`dist/ganita.cyr` is also consumed under stdlib pins older than the fix.

### Tests and gates

- **433 → 491 assertions**: the filing's groups A–C; the ends of the range; the carry
  that rounds `cbrt(8 − ulp)` up to exactly 2.0; bit-exact oddness over 4096 patterns;
  direct checks of the limb comparison (both signs, equality, top of contract) and
  the bisection fallback; every f32 cube; the f32 rows the pow form misrounded; and,
  for the backlog, `inv(P) = P^T` bit for bit, the bytes `inv` and `qr` take,
  `pseudo_inv` bit-identical to the old composition, and the kernel's transposed
  mode.
- **Mutation-verified**: 15 mutations across cube root, f32 root, inverse, QR,
  pseudo-inverse and kernel, and **14 caught**. The survivor is equivalent by design:
  forcing the bisection fallback returns the same answers.
- Word-boundary coverage **56% → 58%** (92/158) and the CI floor ratchets with it;
  the tool's figure is 94% (133/141).
- `tests/ganita.bcyr` gains `mat_inv 60x60` and a cube-root pair: the new function
  against the pow baseline.

### Closed

Both filings moved to `docs/development/issues/archived/` with resolution banners,
and `docs/development/issues/` has no open items. The cbrt repro stays in `repros/`
as a regression witness: it exits 0, and still reports the guarded and bare `pow`
forms for the record.

## [1.2.5] - 2026-09-12

### Changed

- **Toolchain `6.6.0` → `6.6.2`.** No source change: this repo was already on the
  value form, so the flip cost it nothing. Re-verified on every surface it ships —
  build, tests, and any bench/fuzz/distlib target, including every
  `[lib.<profile>]` bundle.

## [1.2.4] — 2026-09-08 — the P(-1) backlog, repaired

Closes four of the five filings the 1.2.3 sweep opened, and five of six items in
the fifth. Everything here was deferred from 1.2.3 because it needed a design
decision, an algorithm replacement, or a consumer-visible change that a hardening
patch should not make unilaterally. **433 assertions** (was 322).

### Fixed — tolerances are RELATIVE, so verdicts are scale-invariant

⭐ `LINALG_EPS` was compared **directly** against pivots, norms and singular
values, so "is this matrix singular?" depended on the caller's **units**. A 2×2
identity scaled by 1e-20 is still perfectly conditioned — cond = 1 — but:

| | 1.2.3 | 1.2.4 |
|---|---|---|
| `det(I·1e-20)` | **0.0 (singular)** | not singular |
| `inv(I·1e-20)` | **null** | succeeds |
| `condition(I·1e-20)` | **−1.0 (singular)** | 1.0 |
| `rank(I·1e-20)` | 2 | 2 |

The library contradicted **itself** about one matrix. `LINALG_EPS` is now a
relative *factor*, multiplied by a magnitude taken from the data at each site:
the matrix scale for the pivot tests, the input's largest entry for the reflector
tests, the initial off-diagonal magnitude for Jacobi convergence, the largest
singular value for the rank tests. Verified in **both** directions — a
well-conditioned matrix is not called singular at any scale, and `[1 2; 2 4]`
stays singular scaled up by 1e9.

It is also **eager** — a literal bit pattern, not a lazily-initialised global — so
no call depends on what ran before it. That was a real hazard: `mat_eq`'s doc told
callers to pass `LINALG_EPS`, which read `0` until some decomposition had run.

- **The two-norm is scaled.** `qr` and `least_squares` summed squares directly, so
  a large-magnitude matrix produced a **NaN norm** and both still returned
  success. `_linalg_norm2` scales out the largest magnitude first.
- **The reflector skip test is relative.** Against an absolute 1e-12, a matrix
  whose entries were merely *small* had every Householder reflector skipped,
  leaving R non-triangular and a plausible-looking wrong answer with `rc = 0`.

### Fixed — SVD no longer forms AᵀA

⭐ `ganita_mat_svd` is now a **one-sided Jacobi** SVD: it orthogonalises A's
columns in place, accumulating V, and never squares A. Forming AᵀA squares the
condition number, spending half the available precision before the eigensolver
starts.

On `A = [[1, 1], [1, 1+e]]` — entries all O(1), det = e — the invariant
`σ₁·σ₂ = |det A|` gives:

| e | 1.2.3 | 1.2.4 |
|---|---|---|
| 1e-6 | 1.000045 | **1.000000** |
| 1e-9 | **0.000000 — σ₂ collapsed to exactly zero** | **1.000000** |
| 1e-11 | **0.000000** | 1.000008 |

At e=1e-9 the old path reported σ₂ = 0 for a matrix `det` and `inv` handle
correctly, so `rank` said 1 and `condition` said "singular" for an invertible
matrix. A **diagonal** matrix does not discriminate here — AᵀA is exact for one —
which is why this was easy to under-read.

### Fixed — f64 transcendental accuracy

- ⭐ **`hypot` scales before squaring.** `hypot(3e116, 4e116) = 5e116` and
  `hypot(3e-116, 4e-116) = 5e-116` are now exact; they were `+inf` and `0`. Not
  overflowing is the entire reason this function exists rather than callers
  writing `sqrt(x*x + y*y)`. `hypot(inf, NaN) = +inf` — infinity outranks NaN
  propagation, which is ordering-sensitive and pinned by a test.
- ⭐ **`acos` is no longer `π/2 − asin(x)`.** That differences two quantities near
  π/2 to produce an answer near 0, losing ~6 digits exactly where `acos(dot)` for
  near-parallel unit vectors lands. The half-angle form's error now **shrinks**
  toward the ends where the old one's grew: at 1 − 2⁻⁵⁰, ~0 against 1.3e-9.
- ⭐ **`pow` on an integral exponent is binary exponentiation.** `pow(7,2)` is
  exactly **49** — it was 48.99999999999999296, which *floors to 48* — and
  `pow(10,15)` is exactly 1e15, not ...005.875. It gets infinite bases right for
  free, because it takes no logarithm.
- **Small-|x| series** for `sinh`, `tanh`, `atanh`: below 2⁻²⁶ each returns `x`,
  which *is* the correctly-rounded answer. They returned exactly `0.0` below
  ~1e-17.
- **Overflow bands**: `acosh` is finite at 1e192 (was `+inf`); `sinh`/`cosh` cover
  the (709.783, 710.476] band.
- **Infinities**: `sinh(±inf) = ±inf`, `cosh(±inf) = +inf`. ⚠ These are *guards* —
  the root cause is stdlib's `f64_exp(±inf) = NaN`, which is not ganita's to fix.
  **Filed upstream 2026-09-08** as
  `cyrius/docs/development/issues/2026-09-08-f64-exp-nan-for-infinite-argument.md`
  with a repro. Scope there is exactly `f64_exp` and `f64_exp2` at both signs of
  infinity — every other f64 builtin already matches C. The guards come out when
  it lands and ganita re-pins.
- **Domains**: `acos`, `acosh`, `atanh` return NaN outside their domains.
  `_f64_is_int` no longer calls an infinity an integer.

### Fixed — f32 NaN and infinity semantics

- ⭐ **`min`/`max` are IEEE-754 minNum/maxNum**: a NaN operand is ignored, NaN
  returns only if both are. Previously `_f32_key` ordered NaNs like any other
  pattern, so whether a NaN won or lost depended on its **sign bit**.
- **`clamp` propagates a NaN x**, deliberately unlike min/max: it transforms one
  value and a NaN has no clamped form, where min/max choose between two and
  skipping an absent one is meaningful. Composing them returned `hi`.
- **`sign(NaN)` is NaN** (was ±1.0f — turning a NaN into a finite value);
  **`cbrt(±inf)` is ±inf**; **`exp`/`exp2`** handle infinities.

### Added — `ganita_f32_lt` / `_le` / `_gt` / `_ge`

The only correct f32 comparator (`_f32_key`) was **private**, so a consumer
needing to compare fell back to the raw integer compare the module's own header
spends a paragraph calling a trap. All four are false on a NaN operand, and they
**normalise the zeros** — `_f32_key` is a *total order* that ranks −0.0 below
+0.0, correct for sorting and wrong for comparison, where IEEE says the zeros are
equal. That distinction is why these are four functions rather than an exported
`_f32_key`, and it was caught by a failing assertion rather than by inspection.

### Optimized — all measured against 1.2.3 in one process

| | speedup |
|---|---|
| `mat_mul` 120×120 — raw row/column pointers in the accumulation loop | **3.34×** |
| `rank` 40×40 — values-only SVD path | **1.61×** |
| `pseudo_inv` 40×40 — column scaling instead of a dense diagonal multiply | 1.12× |

`ganita_mat_get` re-reads the header and recomputes the offset on every call, and
`mat_mul`'s loop calls it *twice per multiply-accumulate*. The pointer rewrite is
deliberately confined to that one loop — it is the only O(m·n·k) one, and a
per-element saving nobody can measure is not worth an off-by-one that writes out
of bounds. Also: `_ganita_mat_new_raw` keeps the CWE-190 guard and skips only the
zero fill for callers that overwrite every element; `qr`'s reflector allocation is
hoisted out of its k-loop; `sinh`/`cosh` evaluate one `exp` instead of two.

### Still open

[`performance-backlog`](docs/development/issues/archived/2026-09-07-performance-backlog.md)
stays in `issues/` rather than `archived/` — an open item in an archived folder is
how a backlog quietly disappears. What remains: `mat_inv`'s per-column scratch and
the discarded transposes both need a **public API change**, and raising
`GANITA_MAT_MAX_ELEMS` is still the policy question the 1.2.3 audit deferred, for
reasons that have not changed.


## [1.2.3] — 2026-09-07 — P(-1) hardening sweep

A full audit / refactor / hardening / optimization / security pass per the AGNOS
first-party P(-1) process. Seven independent audit lenses over `src/`, each
adversarially verified by a second pass whose default posture was *refuted*, and
**every finding reproduced by a program that was built and run**: 90 confirmed,
0 refuted outright, 6 downgraded, 3 upgraded. The full report, including
everything deliberately NOT fixed and why, is
[`docs/audit/2026-09-07-v1.2.3-audit.md`](docs/audit/2026-09-07-v1.2.3-audit.md).

**260 → 322 assertions.** No public signature changed. Two return codes moved
(below), and roughly twenty functions that used to accept an illegal argument now
reject it.

### Fixed — the out-of-bounds class

ganita's defect profile turned out to be one sentence repeated across the API:
**a function derives its loop bounds from one argument and never looks at the
others.** In every case both arguments were matrices `ganita_mat_new` had
accepted. At small sizes the result was a well-formed matrix containing a
neighbouring allocation's bytes reinterpreted as f64 — no null, no error code,
nothing to notice. At large sizes, SIGSEGV. That combination does not fail in
testing and does fail in production.

- **`ganita_mat_mul`** took its inner dimension from `cols(A)` and never read
  `rows(B)`. Now `0` when they disagree.
- **`ganita_mat_add` / `_sub`** took their shape from A and read B for
  `rows(a)*cols(a)` words regardless of B's real size. Now `0` on a mismatch.
- **`ganita_mat_set_row` / `_set_col`** accepted any index — an out-of-bounds
  **write**: `r == rows` landed on the next allocation's `{rows, cols}` header,
  and a negative index walked back into the target's own. Now `-2`.
- **`ganita_mat_row` / `_col`** likewise, for reads. Now `0`.
- **`ganita_mat_submatrix`** checked the *sign* of the extent but never the window
  against the source. Now `0` for a window past the end or a negative origin.
- **`ganita_mat_trace` / `_lu` / `_det` / `_inv` / `_cholesky`** took `n` from the
  **row** count and indexed an `n × n` region of a store holding `rows*cols`. All
  now require square input.
- **`ganita_mat_gaussian_elim`** indexes column `n`; an `n × n` argument — the
  shape a caller most plausibly reaches for, since every other solver here takes
  one — wrote one element past the store on every row and returned `1`. Now
  requires `n × (n+1)`.
- **`ganita_mat_least_squares`** back-substitutes from row `cols-1`, so a wide
  design read past `qtb` and `R` and returned **0 (success) with `out_x` full of
  NaN**. Now `-2` for `m < n`.
- **`ganita_mat_eigen_sym`** wrote `rows - cols` elements past its working copy for
  a non-square input. Now `-2`.
- **`ganita_mat_svd` / `_rank` / `_condition` / `_pseudo_inv`** documented
  `m >= n` and enforced nothing. All now enforce it.
- Null arguments were dereferenced throughout. Gated everywhere.

Adding these preconditions makes most of 1.2.2's cap-driven allocation failures
*structurally unreachable* — the only inputs that produced them are exactly the
inputs now rejected. The allocation checks remain and still guard genuine OOM.

### Fixed — correctness

- ⭐ **`ganita_mat_eq` reported NaN as EQUAL, and it is the test suite's own
  oracle.** Every f64 comparison is false against a NaN, so `if (diff > tol)
  return 0;` never fired and the loop fell through to `return 1`: an all-NaN matrix
  compared **equal to the identity**. A solver that returned NaN would have been
  certified correct by the suite that exists to catch it. `ganita_mat_is_symmetric`
  had the same shape. Both now fail closed.
- ⭐ **`ganita_mat_cholesky` accepted positive-*semi*-definite input.** The guard
  was `diag < 0`, strictly less than, so a zero pivot passed, `sqrt(0)` went onto
  L's diagonal, and every later off-diagonal divided by it. `[1 2; 2 4]` returned
  `1`, produced `L = [1 0; 2 0]`, and `cholesky_solve` then returned **0 (success)
  having written NaN into every slot**. Now `<= 0`, NaN rejected explicitly, and
  `cholesky_solve` additionally refuses a factor with a zero diagonal.
- ⭐ **`ganita_f64_asinh` was only correct for `x >= 0`.** asinh is odd, but
  `ln(x + sqrt(x²+1))` at negative `x` cancels catastrophically. Below `-2^26` it
  returned `-inf`; below `-1.34e154` the `x*x` overflowed first and it returned
  **`+inf` — wrong in sign as well as magnitude**. It also returned exactly `0.0`
  for `|x| <= 1e-17`. Now computed on `|x|` and re-signed, with small- and
  large-argument regimes; oddness holds **bit-exactly** in all three.
- ⭐ **`ganita_binomial` wrapped i64 silently from `n = 62`**, while its own comment
  claimed to "avoid overflow". Now returns `-1` rather than a plausible wrong
  count; `binomial(61,30)` is exact. The same test bounds the loop —
  `binomial(2^62, 2^61)` used to iterate 2.3 × 10¹⁸ times, about **560 years**
  (CWE-834). `binomial` and `ganita_fibonacci` also rejected negative arguments,
  which used to return `1`.
- ⭐ **`ganita_f32_sin` / `_cos` returned their argument for `|x| >= 2^63`** —
  roughly a quarter of the finite f32 exponent range. Sine is bounded to `[-1,1]`
  by definition, so that is a category error, not an approximation. Now NaN.
- **`ganita_mat_svd` discarded a non-convergent eigendecomposition** and reported
  success on singular values from a matrix that was never diagonalised.
- **`ganita_mat_rank`** rejects a negative or NaN tolerance.

### Changed — one failure vocabulary

Stated once at the top of `linalg.cyr` and recorded in
[ADR 0001](docs/adr/0001-failure-vocabulary.md): null for matrix/array returns;
negative for status returns (`-1` allocation, `-2` contract violation, `-3`
non-convergence); **NaN** for f64 returns, because `det`'s `0.0` and
`condition`'s `-1.0` are real answers about the matrix. `ganita_mat_lu` is the
documented exception — its successes are `+1`/`-1`, so it has no negative to
spend.

⚠ **`ganita_mat_eigen_sym`'s non-convergence code moved `-1` → `-3`.** Safe to do
now: the `-2` allocation code was itself only introduced at 1.2.2, the idiom
everywhere is `>= 0` rather than a specific code, and the `dist/` fold had not yet
been refolded downstream.

### Optimized

- ⚡ **`ganita_mat_eigen_sym` is O(n³), was O(n⁴).** It rescanned the whole upper
  triangle before **every** rotation. A per-row maximum index makes the global
  search one O(n) pass, with rows `p` and `q` recomputed after a rotation and
  every other row repaired from its two changed entries. Ties break identically,
  so the **pivot sequence is unchanged** — verified by running both
  implementations in one process on identical matrices: same rotation count,
  **bit-identical eigenvalues**, at every size.

  | n | 1.2.2 | 1.2.3 | |
  |---|---|---|---|
  | 8 | 109 µs | 118 µs | 0.9× — bookkeeping exceeds the scan below n ≈ 20 |
  | 40 | 25.4 ms | 13.7 ms | 1.9× |
  | 120 | 1.55 s | 0.36 s | 4.3× |
  | 200 | 11.53 s | 1.76 s | **6.5×** |

  `rank`, `condition` and `pseudo_inv` all route through it, so the win is not
  confined to callers who wanted eigenvalues.

### Fixed — contracts and hygiene

- **`ganita_mat_dot`'s doc blessed a shape it cannot read** — "Nx1 matrices or
  flat arrays", while the body reads the pointer directly, so an `N×1` matrix had
  its 16-byte header read as data. Doc corrected.
- **`src/main.cyr` omitted `src/math_f32.cyr`** while calling itself the full
  bundle, so the build gate and `cyrius vet` never saw 27 public functions. `vet`
  now reports 12 deps, was 11.
- **`GANITA_MAT_MAX_ELEMS`'s derivation comment was false** — it claimed to track
  `ALLOC_MAX`, which cyrius v6.4.51 raised from 256 MiB to **2 GiB**. That drift is
  why `least_squares`' internal Q hit the cap at `m = 5793` rather than 16383. The
  cap was **not** raised (see the audit for why, including what happened when the
  sweep tried); the comment now says it is a policy limit, not a derivation.
- **`ganita_mat_eq`'s doc told callers to pass `LINALG_EPS`**, which reads `0`
  until some decomposition lazily initialises it — so the same call answered
  differently depending on history.
- **`ganita_mat_get` / `_set` are now documented as unchecked by design**, with the
  consequences named (CWE-125, CWE-787, and `r*cols + c` can itself wrap).

### ⚠ The coverage figure was inflated and CI gated on it

`cyrius coverage` credits a function whose name appears as a raw **substring**
anywhere in the scanned text, **comments included**. Every `_compat` alias name is
a substring of the canonical name it forwards to. Reproduced: appending **one
comment line** naming an uncalled function moved the reported figure from
**80 % to 82 %** — and `ci.yml` gated on `--min 80` with zero margin. The honest
word-boundary count at 1.2.2 was **72/135 (53 %)**, and `_compat.cyr` was **4/53**,
not the published 40/53.

`scripts/coverage-honest.sh` now counts on word boundaries with comments
stripped, and CI gates on **both** numbers — the tool's as a ratchet, the honest
one as the figure to plan against. Neither was lowered to make a build green.

### Added

- **Five runnable examples** in [`docs/examples/`](docs/examples/), built and run
  by CI on every push, so documentation that stops being true fails the gate
  instead of quietly becoming a lie. Writing them found two of the findings above
  independently.
- `SECURITY.md`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md` — required by the
  first-party layout, all absent.
- `scripts/bench-history.sh` and the first `bench-history.csv` rows, with the
  regime/floor discipline that keeps pre- and post-6.5.19 instrument readings from
  being averaged together — which matters here, where f32 rows report 2–5 ns
  against a ~1.3 µs measured timer floor.
- Three `eigen_sym` sizes in `tests/ganita.bcyr`, so a regression to O(n⁴) shows up
  as the largest size pulling away.
- [ADR 0001](docs/adr/0001-failure-vocabulary.md), the audit report, and five issue
  filings for what was deliberately deferred.

### Documentation

`README.md` claimed **"Status: 1.0.0"** and omitted the entire 27-function f32
tier, so its documented consumption path pointed at a fold that SIGSEGVs on the
case 1.2.2 fixed. `docs/guides/getting-started.md` told readers to add features by
editing `src/main.cyr`, a 38-line smoke test. `docs/development/roadmap.md` was
untouched `cyrius init` scaffold (`M1 — _Title_ (v0.2.0)`) at version 1.2.2. All
three rewritten; the roadmap now carries real M0–M4 milestones, a v1.0-freeze
checklist, and an explicit out-of-scope list.

### Deferred, with reasons — see the audit

`LINALG_EPS`'s absolute tolerance (HIGH — the library contradicts itself about
whether a scaled matrix is singular); SVD via `AᵀA` squaring the condition number;
QR skipping reflectors on small-magnitude matrices; f64 transcendental accuracy;
f32 NaN/infinity semantics; the remaining performance items; and raising
`GANITA_MAT_MAX_ELEMS`. Each is filed in
[`docs/development/issues/`](docs/development/issues/) with its reproduction.


## [1.2.2] — 2026-09-07 — the least-squares SIGSEGV, and every unchecked allocation behind it

Closes both open filings in `docs/development/issues/`. One was a **High**-severity
null-pointer write reachable from a public API with in-contract arguments; the other
turned out to be already fixed by 1.2.1's toolchain bump. 260 assertions (was 243).

### Fixed

- **`ganita_mat_least_squares` no longer forms an `m × m` Q — the SIGSEGV is gone,
  and so is the ceiling.** Filed by naad's 2.1.3 hardening sweep after a public DSP
  function faulted on ordinary input.

  A degree-2 fit over 5793 samples is a `5793 × 3` design: 17,379 elements, **0.05 %**
  of `GANITA_MAT_MAX_ELEMS`, which `ganita_mat_new` accepts without complaint. But the
  function reached the solution through `ganita_mat_qr`, whose contract is an *explicit
  `m × m` orthogonal Q* — and `5793² = 33,558,849` is just **over** the cap. `mat_new`
  returned `0`, nothing checked it, and `ganita_mat_qr`'s Q-initialisation loop stored
  through the null. Nothing in the signature, the doc comment or the guard's own error
  surface said that `m` was bounded at ≈ 5792, and it was bounded there by a square
  matrix the algorithm never needed.

  ⚠ **The 1.0.4 CWE-190 guard is not the bug — the unchecked caller is.** Giving a
  constructor a failure return converts every unchecked call site from "allocates and
  works" to "nulls and faults". That is what happened, and it is why the sweep below
  matters more than this one function.

  The reflectors are now applied to `b` in the same sweep that reduces A to R, which
  **is** `Q^T·b`: `R = H_{n-1}···H_0·A`, so `Q^T = H_{n-1}···H_0`, and each `H` is its
  own inverse. Peak memory is **O(m·n)** instead of **O(m²)** — an `m × n` working copy
  plus two length-`m` vectors. The 5793 case needs **231 KB** where it needed 268 MB,
  and a degree-2 fit over **100,000 samples** — impossible before at any cap — costs
  4 MB and returns its coefficients exactly.

  **Not thin Gram-Schmidt.** The report preferred thin MGS, as ported by hisab 1.4.0.
  Householder-applied-to-`b` reaches the same O(m·n) bound and is kept instead because
  it is unconditionally stable where MGS is not, and because it is the *same arithmetic
  1.1.4 through 1.2.1 already shipped* — only the accumulation of Q and its transpose
  are gone. Results are strictly more accurate: the reflectors now reach `b` directly
  rather than through a materialised Q.

  `ganita_mat_qr` is unchanged and keeps its explicit `m × m` `out_q`. That is its
  documented contract, and a caller who wants Q must still budget for it. What changed
  is that *solving* no longer goes through it.

- **Every internal allocation in `matrix.cyr` and `linalg.cyr` is now checked** — the
  sweep the report asked for, and the durable half of the fix. Twenty functions:
  `mat_add` · `mat_sub` · `mat_scale` · `mat_mul` · `mat_transpose` · `mat_copy` ·
  `mat_neg` · `mat_row` · `mat_col` · `mat_submatrix` · `mat_lu_solve` · `mat_det` ·
  `mat_inv` · `mat_cholesky_solve` · `mat_qr` · `mat_least_squares` · `mat_eigen_sym` ·
  `mat_svd` · `mat_pseudo_inv` · `mat_rank` · `mat_condition`.

  Failure is reported in **each function's own vocabulary**, which is the part worth
  reading before upgrading:

  | Return shape | On allocation failure | Functions |
  |---|---|---|
  | matrix | `0` (null), as `ganita_mat_new` already did | `copy` `neg` `submatrix` `add` `sub` `scale` `mul` `transpose` `inv` `pseudo_inv` |
  | flat array | `0` | `row` `col` |
  | status | `-1` | `lu_solve` `cholesky_solve` `qr` `least_squares` `svd` |
  | status, `-1` taken | `-2` | `eigen_sym` (`-1` still means max-iterations) |
  | count | `-1` | `rank` — a rank is never negative |
  | **f64** | **NaN** | `det` `condition` |

  The f64 row is the one that is not merely bookkeeping. `det` already returns `0.0`
  for a singular matrix and `condition` already returns `-1.0` for one — both are real
  answers *about the matrix*. Overloading either to also mean "the run failed" would
  report a perfectly invertible matrix as singular. NaN says the thing that is true.

  Several of these failures are reachable with matrices that are themselves well inside
  the cap, because the working factor is *derived and larger* — the same shape as the
  original report. `det` and `inv` take `n` from the **row** count, so a tall non-square
  asks for an `n × n` factor; `rank`, `condition` and `pseudo_inv` build `cols × cols`
  factors, so a wide input does it; and `mat_mul` can be handed two legal operands whose
  product is not (`8000×1 · 1×8000` is 64 M elements).

- **`fmt_float`'s dropped carry — closed, fixed upstream.** ganita filed it from the
  1.1.3 linalg pass, where every near-integer solver result printed wrong while being
  numerically correct. cyrius fixed it at **6.5.30** with the exact change proposed
  (compute the fraction first, fold the carry into `whole`), and it reached ganita at
  1.2.1 with the 6.6.0 re-vendor. Verified against 6.6.0: every row of the filing's
  table now prints its expected value, and `10 - 1e-7` prints `10.000000` — the case
  that proves the carry propagates through a change in integer digit count. No ganita
  change was needed.

### Added

- **17 assertions** (243 → **260**), in two groups.

  The regression itself: the `5793 × 3` fit that used to SIGSEGV now solves, and is
  asserted on the *fitted coefficients* rather than on not-crashing — the design samples
  `2 + 3x - 4x²`, which lies exactly in the column space, so the least-squares answer is
  the exact one at any `m`. **Mutation-verified**: restoring the `m × m` Q kills the
  suite with the report's own SIGSEGV.

  And the reachable allocation failures, one per return shape above, each paired with an
  assertion that the *input* was legal — which is the whole point of the filing.
  Mutation-verified: removing any single null check kills the suite with a SIGSEGV.

### Changed

- Both filings moved to `docs/development/issues/archived/` with resolution banners.
  `docs/development/issues/` is now empty of open items.
  `repros/2026-08-23-least-squares-unchecked-q-alloc.cyr` stays as a regression witness —
  it exits 139 on 1.1.4 … 1.2.1 and 0 from 1.2.2 on.


### Fixed

- **`cyrius bench` runs with zero warnings again.** Every run printed
  `warning: undefined function 'ganita_f64_pow' / 'ganita_f64_atan2' /
  'ganita_f64_hypot'`. `tests/ganita.bcyr` carries its own include list — the
  auto-prepend is skipped once a file has includes — and it included
  `src/math_f32.cyr` **without** `src/math_advanced.cyr`, but `math_f32`'s
  `pow` / `atan2` / `hypot` / `cbrt` forward to the `ganita_f64_*` fns that live
  there. Fixed by adding `include "src/math_advanced.cyr"` ahead of the
  `math_f32` include, matching the order `tests/ganita.tcyr` already uses (the
  compiler is single-pass, so definition order matters).

  Harmless until now only because no benchmark called those four — the first one
  that did would have linked against nothing. No `src/` change, no behavioural
  change: 243/243 assertions, `audit` exits 0, `fmt --check` clean.

## [1.2.1] — 2026-09-07 — toolchain 6.6.0, and the docs audit that came with it

Maintenance. Cyrius pin `6.5.36` → **6.6.0**, `lib/` re-vendored to an exact match
(108 → 109 files), `dist/` regenerated. **No `src/` change and no behavioural
change** — the 243 assertions are the same 243, green on 6.6.0.

### Changed

- **Cyrius pin `6.5.36` → `6.6.0`.** `cyrius version` reports
  `manifest-pin: 6.6.0` with no drift line. The whole CI gate was re-run locally
  against it: format · lint · `vet` (11 deps, 0 untrusted, 0 missing) · build with
  zero compiler warnings · smoke exits 42 · **243/243 assertions** · fuzz · bench ·
  `coverage --min 80` (109/135 fns, 7/7 files) · `distlib --all --check` ·
  regeneration byte-identical · consumer-check clean from 10 declared leaves.

- **`lib/` re-synced to the 6.6.0 snapshot — 109 files, 0 differ** (was 108).
  37 files changed and one is new: `hashseed.cyr`. None of them is in
  `[deps].stdlib`; they ride along because `cyrius lib sync --full` vendors the
  whole snapshot. Verified by comparing the trees against
  `~/.cyrius/versions/6.6.0/lib`, not by trusting the sync's exit code.

- **`dist/ganita.cyr` regenerated** — 1,690 lines, header `Version: 1.2.1`. The
  bundle is otherwise byte-identical to 1.2.0's: only the version line moves,
  because `src/` did not change.

### Fixed

- **`cyrius audit` exits 0 again.** 6.6.0 applies the docs check across the whole
  audit scope — which is `src` **and** `tests` — so the bump turned 1.2.0's green
  audit into `15 undocumented public fns`. Every one is a test-harness helper that
  had simply never been in scope before: 10 in `tests/ganita.tcyr` (`t_tol`,
  `t_dclose`, `t_m2`, `t_m3`, `t_arr2`, `t_arr3`, `t_f32div`, `t_f64_is_nan`,
  `t_f64_is_pos_inf`, `t_is_nan`), 3 in `tests/ganita.bcyr` (`bench_noop`,
  `bench_f32_lerp_widened`, `main`) and 2 in `tests/ganita.fcyr` (`fuzz_main`,
  `main`).

  **The rule is positional**: the doc comment must sit on the line *immediately*
  above `fn`. A section banner (`# --- linalg test helpers ---`) documents only the
  first fn beneath it, which is why files that read as thoroughly commented still
  counted 15 — `t_d` and `t_f32` passed solely because they happened to be first
  under their banners. Each of the 15 now carries its own line. No test logic
  changed: 243 assertions before, 243 after.

  This was never a CI failure — `ci.yml` does not run `cyrius audit`. It is a
  regression against what 1.2.0 recorded as shipped, which is why it is fixed here
  rather than deferred.


## [1.2.0] — 2026-09-01 — the f32 arithmetic tier that 1.1.0 said could not be written

Adds `ganita_f32_add` / `_sub` / `_mul` / `_div` in **native single precision**, and
rewrites `ganita_f32_lerp` to use them. Minor, not patch: four new public functions.
243 assertions (was 227); `cyrius audit` exits 0 for the first time (docs were the
blocker — see below).

### Added

- **TIER 0 — `ganita_f32_add`, `ganita_f32_sub`, `ganita_f32_mul`, `ganita_f32_div`.**
  Real `addss` / `subss` / `mulss` / `divss`: **one rounding, in f32, per operation.**

  1.1.0 shipped tiers 1-3 and recorded that this tier was impossible. The module
  header said so, `ganita_f32_lerp`'s comment said so, and the closing note on
  [the filing](https://github.com/MacCracken/cyrius) listed it as a remaining
  cyrius-side gap: *"there is no callable `f32_add`/`f32_sub`/`f32_mul`, so no f32
  tier can be written in native single-precision arithmetic today."*

  **The reasoning had one wrong clause.** It is true that `f32_add(...)` is not a
  builtin and that cyrius reaches f32 arithmetic only through the operators on an
  `F32_TYID`-typed value. The wrong part was the conclusion drawn from *"and these
  params arrive as untyped i64 bit patterns"* — a parameter can simply **be typed**:

  ```
  fn ganita_f32_mul(a: f32, b: f32): i64 {
      var s: f32 = a * b;
      return s;
  }
  ```

  The typed params put the incoming patterns in xmm lanes as singles, the `var s: f32`
  binding emits the single-precision op, and returning `s` as `i64` hands the pattern
  back. Callers pass and receive exactly the same bit patterns as the rest of the tier —
  no signature change to anything that already existed.

  Only the **return** type is still barred (`fn f(): f32` is rejected with *"fn return
  type must be struct or i8/i16/i32/i64/Result/Option/Tagged/cstring/f64/f64v2/f64v4"*),
  and that costs nothing here because the bit pattern is the interchange form anyway.
  That one remains a genuine cyrius-side gap, as does the `sqrtss` intrinsic.

### Fixed

- **`ganita_f32_lerp` no longer widens.** It computed `a + (b - a) * t` as a single f64
  expression rounded once at the end; it now rounds three times, in single, exactly as
  the same expression does in Rust or C. **Results can differ from 1.1.x by 1 ULP — the
  new ones are the single-precision answers.** A new assertion pins
  `lerp(a,b,t) == add(a, mul(sub(b,a), t))` rounding for rounding, which the widened
  form did not guarantee.

### Fixed (docs)

- **`cyrius audit` now exits 0.** It was failing on `70 undocumented public fns` —
  every one of `_compat.cyr`'s 53 deprecated aliases, 15 of `math_f32.cyr`'s own tier
  (including three the change above had just added), and both `main` entry points.
  All 70 now carry a doc line, so the gate is green rather than permanently red, and
  a genuinely new undocumented function will be visible instead of lost in the count.

### Changed (toolchain)

- **Cyrius pin `6.5.29` → `6.5.36`**, with `cyrius lib sync --full` (108 files). This
  clears the drift warning *and* the `./lib/ shadows version-pinned .../6.5.29/lib — 7
  bundled lib(s) differ` warning that 1.1.4 shipped with. It also retires 1.1.4's
  blocker: that release pinned a version whose GitHub tarball did not exist, so CI
  failed at the install step. 6.5.36 is published.

### Notes on what this is NOT

- **It is not a speedup, and the benchmark says so.** `tests/ganita.bcyr` now measures
  the native tier against the 1.1.x widen-compute-narrow shape at 1M iterations:
  `f32_mul` 3 ns vs 3 ns, `f32_lerp` 5 ns vs 4 ns — indistinguishable, and on the
  `lerp` row the widened shape came out marginally *ahead* on one run, which is the
  spread rather than a result. The `cvtss2sd`/`cvtsd2ss` pair is free at this
  granularity. **The tier is about semantics, not cost — do not sell it as a speedup.**
- **For a SINGLE operation the old shape was already correct.** f64 carries 53 mantissa
  bits against f32's 24, more than 2·24+2, so widen-compute-narrow is correctly rounded
  for one `+ - * /` and double rounding cannot bite. The difference appears when a
  consumer **chains** operations and an f64 intermediate keeps precision f32 does not
  have. `add(add(2^24, 1), 1)` is 2^24 natively and 2^24+2 through an f64 accumulator;
  that pair is the test that pins these as native.
- `ganita_f32_sqrt` still widens — `sqrtss` needs a new cyrius intrinsic, which is a
  compiler change. It is correctly rounded, per the same 53-bit argument.


## [1.1.4] — 2026-08-19 — `f64_pow` domain

### Changed (toolchain)

- **Cyrius pin `6.5.28` → `6.5.29`**, with `cyrius lib sync --full` run against
  it; `lib/` matches the snapshot exactly (108 files, 0 differ). 6.5.29 carries
  the `distlib` profile-sidecar fix that made ganita's own artifacts
  irreproducible on CI at 1.1.1 — ganita's single-bundle sidecar is unchanged by
  it (`syscalls string alloc fmt vec str math`), since the defect only bit
  `[lib.X]` profiles.

  ⚠ **The 6.5.29 GitHub release is not published yet.** Both workflows install
  by handing the pin to the upstream `scripts/install.sh`, which downloads
  `cyrius-<pin>-x86_64-linux.tar.gz` — that asset currently 404s, so CI fails at
  the install step until the release goes out. Everything below was verified
  against the **locally installed** 6.5.29, not a release tarball; re-verify
  once it ships, per the standing rule in `state.md`.

### Fixed

- **`ganita_f64_pow` returned NaN for a zero or negative base.** It was
  `exp(y · ln base)` and nothing else, and that identity only holds for
  `base > 0` — `ln(0)` is `-inf`, `ln(negative)` is NaN, and the NaN propagated
  out silently. `pow(0, 2)` and `pow(-2, 3)` are ordinary defined operations;
  both came back NaN with no diagnostic. Filed at 1.1.2, fixed here.

  The domain is now handled ahead of the exp/ln path, following C's `pow`:

  | call | before | after |
  |---|---|---|
  | `pow(0, 2)` / `pow(0, 3)` / `pow(0, 0.5)` | NaN | `0.0` |
  | `pow(0, -2)` | NaN | `+inf` |
  | `pow(0, 0)` | `1.0` ✅ | `1.0` |
  | `pow(-2, 2)` | NaN | `4.0` |
  | `pow(-2, 3)` | NaN | `-8.0` |
  | `pow(-2, 10)` | NaN | `1024.0` |
  | `pow(-3, 0.5)` | NaN | **NaN, deliberately** |
  | `pow(2, 10)` / `pow(9, 0.5)` / `pow(2, -2)` | correct | unchanged |

  **A non-integral exponent on a negative base stays NaN** — there is no real
  result, so NaN is the right answer and is left alone rather than papered over.
  That is also why `ganita_f32_cbrt` keeps its sign split: `cbrt` needs
  `pow(x, 1/3)`, which remains out of domain for negative `x`.

  Sign comes from the exponent's parity, computed on the magnitude, so
  `pow(-x, odd)` is **bit-identical** to `-pow(x, odd)` — the negative path adds
  no error of its own. Parity treats every `|y| >= 2^53` as even, which is not a
  shortcut: at that magnitude consecutive f64 values are 2 apart, so no odd
  integer is representable.

  **Deliberately not done:** C distinguishes `pow(-0, odd) = -0` from
  `pow(+0, odd) = +0`. cyrius's `f64_neg(f64_from(0))` yields `+0`, so a negative
  zero cannot be produced or asserted against through the f64 helper surface —
  a branch for it would have been untestable dead code. Zero of either sign
  returns `+0`, and the reasoning is recorded at the call site.

- **`ganita_f32_pow` inherits the fix**, being a widen-compute-narrow wrapper.
  f32 rounding absorbs the exp/ln core's ~2e-15 error, so `f32_pow(-2, 3)` is
  now exactly `-8.0f`.

### Changed — tests

The **self-expiring** `f32: known domain gaps` group added at 1.1.2 did exactly
what it was for: it asserted the old NaN behaviour, failed the moment the gap
closed, and has been rewritten to the real answers. 227 assertions (was 210),
including a new f64-level `pow` domain group covering zero, negative, integral
and non-integral exponents, `+inf`, `x^0`, the bit-identity of the negative
path, and the positive-path regressions.

**Mutation-verified**: deleting the zero-base branch fails 5 assertions,
dropping the parity sign flip fails 3, and treating every negative-base exponent
as integral fails 3 — the last being the check that a genuinely undefined
operation is still reported as NaN.

### Note for cyrius

cyrius ships this defect under the plain stdlib name `f64_pow` (the `_compat`
alias in the folded `lib/ganita.cyr:1538`), so a consumer who never heard of
ganita hits it. cyrius's fold is at **1.1.1**; a refold picks up this fix plus
1.1.2's `cbrt(±0)` guard and the 1.1.2/1.1.3 test suites. Upstream filing:
`cyrius/docs/development/issues/2026-08-19-f64-pow-nan-for-zero-and-negative-base.md`.

### Verified on 6.5.29 (local install — see the toolchain note above)

All 15 CI gates green. `cyrius test` — **227 passed, 0 failed**. Build clean
with zero warnings, smoke exits 42, fmt + lint clean, `distlib --all --check`
current and idempotent, consumer-check clean, coverage 80%.

## [1.1.3] — 2026-08-19 — linalg gets a test suite

`linalg.cyr` was the largest untested surface in the repo at **2/26** — every
decomposition and solver (LU, Cholesky, QR, SVD, Jacobi eigen, least squares,
pseudo-inverse) shipped unverified. Now **26/26**, with 90 new assertions.
Repo-wide reference coverage 37% → **80%** (105/131), and the exercise pulled
`matrix.cyr` to 10/14 and `_compat.cyr` to 40/53 along the way.

### Added — `tests/ganita.tcyr`

Assertions are **properties**, not transcribed outputs, so they stay valid if an
algorithm is reimplemented and they cannot be satisfied by a plausible-looking
wrong answer:

| Routine | Pinned by |
|---|---|
| `lu` / `det` | pivot sign after one swap; `det = -6` and `-306` by hand; `det(A^T) = det(A)`; singular → `lu` returns 0 and `det` is 0 |
| `lu_solve` | 2x2 and a 3x3 round trip (solve `M·[1,2,3]`, recover `[1,2,3]`) |
| `inv` | `A·A⁻¹ = I` **and** `A⁻¹·A = I`; `inv(inv(A)) = A`; singular → returns 0, not garbage |
| `cholesky` | `L·Lᵀ = A`; `L` lower triangular; rejects a symmetric **non**-positive-definite matrix |
| `qr` | `Q·R = A`; **`Qᵀ·Q = I`**; `R` upper triangular — square *and* 3x2 |
| `gaussian_elim` | solution in the last column, agreeing with `lu_solve` on the same system; singular → 0 |
| `least_squares` | consistent overdetermined system, so the exact answer is assertable |
| `eigen_sym` | eigenvalues; **Σλ = trace** and **Πλ = det**; `A·v = λ·v`; eigenvectors orthonormal; diagonal input left alone |
| `svd` | `U·Σ·Vᵀ = A` (diagonal and non-diagonal); σ sorted descending; **Πσ = \|det\|** |
| `pseudo_inv` | equals `inv` when invertible; Moore–Penrose `A·A⁺·A = A` |
| `rank` / `condition` | rank of full-rank vs rank-deficient; `cond(I) = 1`; `cond ≥ 1`; singular → the documented `-1` sentinel |

`mat_eq` is the comparison tool for most of the above, so **both its polarities
are pinned first** — an `eq` that always returned 1 would make the rest vacuous.
Utilities (`copy` deep-not-aliased, `neg` involution, row/col accessors,
`set_row`/`set_col` isolation, half-open `submatrix`, Frobenius, max-norm as max
*row sum*, trace, symmetry incl. non-square) are covered too.

**Mutation-verified.** Forcing the LU pivot sign to `+1` fails 2 assertions;
deleting Cholesky's positive-definite check fails 1; making QR return an
identity `Q` fails 6, including both least-squares assertions — which is the
suite noticing that `least_squares` is built on QR.

### Changed

- CI coverage floor raised `37` → **`80`**.

### Found, not fixed — `fmt_float` drops the carry when a fraction rounds to 1.0

`fmt_float(2.9999999, 6)` prints `2.1000000` — seven fraction digits, carry
dropped — and `1.0 - 1e-8` prints `0.1000000`. Display only; the values are
correct. It surfaced here because near-integer results are routine after a
decomposition: a correct `cholesky_solve` result of `3.0` printed as `2.1000000`
and a correct `least_squares` result of `1.0` printed as `0.1000000`, both of
which read as solver bugs. This is cyrius stdlib (`lib/fmt.cyr`), vendored, so
it is **filed rather than changed**:
[2026-08-19](docs/development/issues/archived/2026-08-19-fmt-float-missing-carry-on-round-up.md).
The suite is unaffected — it asserts numerically, never on printed text.

### Verified on released 6.5.28

`cyrius test` — **210 passed, 0 failed** (was 120). Build clean with zero
warnings, smoke exits 42, `distlib --all --check` current, consumer-check clean.

## [1.1.2] — 2026-08-19 — f32 tier gets a test suite, and it found two bugs

1.1.0 shipped 23 `ganita_f32_*` helpers with **no test at all** (`math_f32.cyr`
was 0/23 referenced — the module was never even included by
`tests/ganita.tcyr`). This closes that: **23/23 functions covered, 95 new
assertions**, and overall reference coverage 16% → **37%** with 7/7 files
referenced.

### Fixed

- **`ganita_f32_cbrt(0)` returned NaN.** Zero fell through to `pow`, `pow` is
  `exp(y·ln x)`, and `ln(0)` is `-inf` — so the cube root of zero was NaN.
  Guarded explicitly, `±0 -> ±0`, preserving the sign of zero. The failure was
  invisible to any test that only tried positive non-zero inputs.

### Added — `tests/ganita.tcyr`

**The `_f32_key` sign-magnitude story is now pinned, and mutation-verified.**
1.1.0 called it "the whole correctness story" and named the trap precisely:
IEEE-754 is sign-magnitude, so raw bit patterns order correctly only among
non-negatives — and pixel data *is* non-negative, so a naive unsigned compare
passes every plausible test. The suite states the trap as an assertion
(`-1.0f` sorts *below* `-2.0f`; every negative sorts *above* every positive),
then checks the cases that discriminate:

| Case | Correct | A bare unsigned compare gives |
|---|---|---|
| `min(-1,-2)` | `-2` | `-1` |
| `max(-1,-2)` | `-1` | `-2` |
| `min(-1, 1)` | `-1` | `1` |
| `max(-1, 1)` | `1` | `-1` |

Replacing `_f32_key` with the naive `b & 0xFFFFFFFF` fails **12** assertions
across min/max/clamp and the hygiene group. Removing `cbrt`'s sign split fails
exactly 2 — both negative-input cases, while every positive still passes, which
is the shape of bug a positives-only suite misses.

Also covered: signed zeros (`min(+0,-0) = -0`), infinities, commutativity;
`clamp` including an all-negative range; `abs`/`neg`/`sign` on zeros and
infinities with their involution and idempotence laws; **high-32 hygiene** —
every entry point masks, so an operand with a dirty high half still yields a
clean 32-bit result; `floor`/`ceil`/`trunc` at `±2.5` where all three differ,
plus `trunc(-0.5) = -0`; `lerp` endpoints and a sign-spanning midpoint;
`sqrt(2) = 0x3FB504F3`, the correctly-rounded single (f64's 53 mantissa bits
exceed 2·24+2, so double-rounding cannot bite); and exact identities for every
tier-3 function.

**`round` is half-to-EVEN, not half-away-from-zero** — pinned explicitly with a
note, because C's `roundf(2.5)` is `3.0` while this gives `2.0`. A consumer
porting from C is otherwise quietly off by one on every tie.

### Found, not fixed — `ganita_f64_pow` domain gap

`pow` is `exp(y·ln base)`, valid only for `base > 0`. So `pow(0, 2)` is NaN
(should be `0`) and `pow(-2, 2)` is NaN (should be `4`); `ganita_f32_pow`
inherits both. This is the f64 tier, out of scope for an f32 test pass, so it is
**filed rather than changed**:
[2026-08-19](docs/development/issues/archived/2026-08-19-f64-pow-zero-and-negative-base.md).

The suite carries a **self-expiring** `f32: known domain gaps` group asserting
the current NaN behaviour, so the gap is measured rather than merely known —
those two assertions **fail when the issue is fixed**, which is the signal to
rewrite them to the correct answers.

### Changed

- CI coverage floor raised `16` → **`37`**, matching the new measurement. It
  ratchets up, never down.

### Verified on released 6.5.28

`cyrius test` — **120 passed, 0 failed** (was 25). Build clean with zero
warnings, smoke exits 42, `distlib --all --check` current, consumer-check clean.

## [1.1.1] — 2026-08-19

Toolchain + CI release. No behavioural change — the only `src/` edits are
whitespace and one comment. What changed is that the project now *checks*
considerably more of itself.

### Changed (toolchain)

- **Cyrius pin `6.5.23` → `6.5.28`**, with `cyrius lib sync --full` run against
  it. `lib/` matches the pinned snapshot **exactly — 0 of 108 files differ**,
  confirmed by comparing the trees rather than trusting the sync's exit code.
  `lib/` had been left in a half-bumped state: seventeen `[deps].stdlib`
  modules already carried 6.5.28 content (from a `cyrius deps` run) while the
  pin still said `6.5.23`. The full sync completes it.
- **`lib/` grew 98 → 108 files** — the 6.5.28 snapshot adds `unicode/` (7 files)
  plus the macOS `async`/`thread` variants. None is in `[deps].stdlib`; they
  ride along because `--full` vendors the whole snapshot.

### Fixed

- **`src/linalg.cyr` and `tests/ganita.tcyr` are canonically formatted.**
  Continuation lines sat at column 0; `cyrius fmt` indents them to 2.
  Whitespace only — still 25 assertions, still green. It had gone unnoticed
  because there was no format gate.
- **Lint is clean across all `src/` files.** `linalg.cyr:9` carried an untracked
  deferral: the header prose "Complete pivoting is out of scope" reads to the
  scanner as a deferral marker, when it is a permanent design boundary rather
  than deferred work. Reworded to "deliberately excluded" — no `#skip-lint`
  needed, and the sentence says what it means.

### Added — CI now confirms the whole project

`.github/workflows/ci.yml` went from 4 steps (install / deps / build / test) to
a full gate: toolchain-pin drift · version consistency across
`VERSION` / manifest / CHANGELOG / dist header · `lib/`-vs-snapshot tree diff ·
format (`src/` **and** `tests/`) · lint (0 warnings, 0 untracked deferrals) ·
`cyrius vet` · build with **zero compiler warnings** · smoke exits 42 · test ·
fuzz · bench · `cyrius coverage --min 16` · and three distribution checks.

`release.yml` gains a CHANGELOG-entry check alongside the existing tag/VERSION
check.

**Both workflows now install via the upstream installer** rather than untarring
a release by hand:

```sh
curl -sSf .../cyrius/main/scripts/install.sh | CYRIUS_VERSION="$pin" sh
```

The hand-rolled step laid the toolchain down at `~/.cyrius/{bin,lib}` as real
directories. 6.5.28's `cyrius deps` requires the snapshot at
`~/.cyrius/versions/<pin>/lib` specifically and errors with *"pins version
6.5.28 but it is not installed"*. The installer creates
`versions/<pin>/{bin,lib}` and symlinks `~/.cyrius/{bin,lib}` at them; the
`lib/`-vs-snapshot gate compares against `versions/<pin>/lib` for the same
reason. The pipe carries `set -eo pipefail` — without it a failed download
pipes empty input to `sh`, `sh` exits 0, and the install silently no-ops.
(Same defect and same fix as bayan 1.4.2.)

Three gate mechanics worth knowing before editing the workflow, each verified
against a deliberately broken input rather than assumed:

- `cyrius lint` **always exits 0** — the step parses its `N warnings` /
  `N untracked deferrals` lines.
- `cyrfmt` reads only `argv[1]`, so `cyrius fmt src/*.cyr --check` checks one
  file and exits 0. The step is a per-file loop.
- `cyrius build` only *warns* on bad pointer typing, `lib/` shadowing and pin
  drift, and `--strict` does not promote them — so the step greps `^warning:`.

**`scripts/consumer-check.sh`** (new) compiles a throwaway consumer against
`dist/ganita.cyr` using **only** the seven leaves its `.deps` sidecar declares
(`syscalls string alloc fmt vec str math`). It builds with `cyrius build
--no-deps` — without that, `cyrius build` auto-prepends everything in
`[deps].stdlib` and the check passes vacuously. Verified by deleting leaves one
at a time: dropping `math`, `vec`, `fmt`, `string` or `alloc` fails the check as
it should. **ganita's sidecar is correct** — the bundle compiles clean from its
declared leaves. (`str` turns out to be over-declared, which is harmless: a
consumer including one module more than it needs still builds.)

### Verified on released 6.5.28

Checked against the **release tarball** in an isolated `CYRIUS_HOME`, not the
local `~/.cyrius` — a machine that also develops cyrius can hold an in-flight
build reporting the same version string, and artifacts generated with it are
not reproducible on CI (bayan 1.4.2 hit exactly that).

| Gate | Result |
|---|---|
| `cyrius build src/main.cyr` | OK, **0 warnings**; smoke exits 42 |
| `cyrius test` | **25 passed, 0 failed** (+ 1/1 `[build].test`) |
| `cyrius fmt --check` (src + tests) | clean |
| `cyrius lint` | 0 warnings, 0 untracked deferrals |
| `cyrius vet src/main.cyr` | 11 deps, 0 untrusted, 0 missing |
| `cyrius distlib --all --check` | current; regeneration stable across runs |
| `scripts/consumer-check.sh` | clean from 7 declared leaves |
| `cyrius fuzz` · `cyrius bench` | 1/1 · 1/1 |
| `cyrius coverage` | 22/131 fns (16%) reference coverage |

### Known, not fixed here

- `tests/ganita.fcyr` and `tests/ganita.bcyr` are still `cyrius init` scaffolds
  — the fuzz harness does no fuzzing and the bench measures a no-op. Both report
  PASS, so the two CI gates that run them are currently vacuous.
- **`src/math_f32.cyr` has no test at all** (0/23 fns referenced) — the whole
  1.1.0 f32 tier is untested in-repo, including the `_f32_key` sign-magnitude
  transform that 1.1.0 called "the whole correctness story". `linalg.cyr` is
  2/26. Reference coverage is 16% overall; the floor is set there and should
  ratchet up.
- `docs/development/state.md` had been stale since 1.0.4 (it did not mention the
  1.1.0 f32 tier); refreshed with this release.

## [1.1.0] — 2026-08-17 — f32 scalar tier (ALL THREE TIERS)

**MINOR, not a patch: new public API.** **Twenty-three** `ganita_f32_*` helpers — the FULL surface the filing enumerated, all three tiers, so f32 consumers stop
paying a widen-op-narrow round trip for shape-level operations. Requested from the ranga
(image processing) Rust->Cyrius port, whose pixel loops are f32 throughout — `f32_abs` was
`f32_from(f64_abs(f32_to(x)))`, three ops for a bit-clear.

### Added — `src/math_f32.cyr`

* Pure bit ops, exact, no widening: `ganita_f32_abs`, `_neg`, `_sign`.
* One signed compare on a monotone key: `ganita_f32_min`, `_max`, `_clamp`.
* `ganita_f32_lerp` — widens, and NOT by choice: there is no callable `f32_add`/`f32_sub`/
  `f32_mul`. cyrius dispatches f32 arithmetic through the OPERATORS on an `F32_TYID`-typed
  value (`EMIT_F32_BINOP`), reachable only from a `var x: f32` binding, and these params
  arrive as untyped bit patterns. A first cut called `f32_add(...)` as a builtin and
  `cyrius distlib` caught it (`undefined function`). Widening is exact on the inputs.
* Exact widening (see below): `ganita_f32_floor`, `_ceil`, `_trunc`.

⚠ **min/max/clamp are NOT a bare unsigned compare, and that distinction is the whole
correctness story.** IEEE-754 is SIGN-MAGNITUDE. Raw patterns order correctly only among
NON-NEGATIVE values: for two negatives the order REVERSES (-2.0 has the larger magnitude
field), and any negative compares HIGH against every positive because bit 31 is set. The
filing observed that "for non-negative finite f32 the raw pattern orders identically to an
unsigned integer" — true, and exactly the trap, because pixel data IS non-negative, so a
naive version passes every plausible test and breaks the first time a consumer subtracts.
`_f32_key` applies the standard monotone transform (invert all bits when negative, else set
the sign bit) so one signed compare is correct across the full range. Verified on the
both-negative and mixed-sign cases, not just the easy one.

⭐ **floor/ceil/trunc widen deliberately, and it costs no accuracy.** f32 -> f64 is exact
(every f32 is representable), the f64 rounding intrinsic is exact on it, and an
integer-valued result narrows back exactly. Hand-rolled exponent twiddling would need NaN
and infinity special-cases for zero accuracy gain; the win this tier is about is
min/max/clamp/abs/neg becoming branch-and-mask.

### Changed

* Toolchain pin `cyrius` **6.4.69 -> 6.5.23** (was 15 patches behind; the drift warning
  was live).

### Added — tier 2: `ganita_f32_sqrt`

⚠ The filing asks for `sqrtss` (direct single-precision, no widening). That needs a NEW
cyrius intrinsic — a compiler change, not a library one — so this widens instead, and it
is **correctly rounded rather than approximate**: f64 carries 53 mantissa bits against
f32's 24, more than 2*24 + 2, so computing in double and rounding once to single yields
exactly the single-precision result. Double-rounding cannot bite. The `sqrtss` intrinsic
is recorded as a cyrius-side follow-up.

### Added — tier 3: transcendentals

`ganita_f32_exp`, `_ln`, `_log2`, `_exp2`, `_sin`, `_cos`, `_atan`, `_round`, `_pow`,
`_atan2`, `_hypot`, `_cbrt`. Widen-compute-narrow, which the filing explicitly blesses
here: the win is that the conversions stop being the consumer's problem and the naming
stays symmetric with the f64 tier.

⚠ **`ganita_f32_cbrt` splits on sign, and that is required rather than decorative.** There
is no f64 cbrt in ganita or the stdlib, so it is built from `pow` — which routes through
`exp(y * ln x)`, and `ln` of a negative is undefined. A bare `pow` returns garbage for
every negative input while looking correct for the positives a naive test would use.
Verified on -8 -> -2.

### Process note

An earlier cut of this release shipped **tier 1 only** and recorded tiers 2-3 as "interleaved
fold-ins". That was a silent deferral of a consumer filing's enumerated surface, not a plan —
the filing's tiering was labelled *suggested, cheapest first*, not an instruction to ship a
third. Corrected before release: all three tiers are in this version.

## [1.0.4] — 2026-07-21

### Changed

- **Toolchain pin `6.4.26` → `6.4.69`.** Ecosystem sweep onto the current Cyrius;
  ganita compiles and tests clean on the new pin (25/25, full-bundle smoke exits
  42) with no source change beyond the security fix below, and `dist/ganita.cyr`
  is byte-identical bar that fix. Re-vendored `lib/` to the 6.4.69 full snapshot
  (`cyrius lib sync --full`) so the committed `lib/` is byte-identical to the
  pinned snapshot (99 files) — clearing the stale-6.4.26 shadow/drift build
  warnings — and pruned 10 vendored modules the old snapshot carried that 6.4.69
  no longer ships and ganita never referenced (incl. the standalone
  `matrix`/`linalg`, superseded upstream by the folded `ganita.cyr`).

### Security

- **`ganita_mat_new` integer overflow → heap overflow (CWE-190).** The size
  computation `16 + rows*cols*8` was unguarded: a large `rows*cols` wraps i64 to
  a small (or negative) value, so `alloc` handed back an undersized buffer while
  the following zero-fill loop still ran the full `rows*cols` iterations —
  writing far past the allocation. With attacker-influenced dimensions that is a
  heap-corruption primitive. `ganita_mat_new` now validates dimensions **before**
  allocating: it returns `0` (null) for non-positive dims, for an element count
  above the largest allocatable matrix (`GANITA_MAT_MAX_ELEMS = (ALLOC_MAX − 16)
  / 8 = 33_554_430`, checked via a division that cannot itself overflow), and on
  `alloc` failure. The derived dimension-taking constructors `ganita_mat_identity`
  and `ganita_mat_from` — and their `_compat` aliases `mat_new` / `mat_identity`
  / `mat_from` — propagate the null. **Contract change:** these constructors may
  now return null, so a caller sizing a matrix from untrusted input MUST check
  the result; the fast path is byte-for-byte unchanged for valid dimensions, and
  every internal caller passes dims from already-allocated matrices. Regression
  tests added (`tests/ganita.tcyr`: negative/zero dims, wrap-inducing dims,
  over-cap rejection, valid-8×8 control → 16 → **25** assertions). Downstream
  hisab has shipped a `mat_new_guarded` work-around for this since its 2.5.3;
  this upstream fix lets that fold back into a plain `mat_new` once the cyrius
  pin picks up this ganita.

## [1.0.3] — 2026-07-08

### Fixed

- **Inverse trig (`ganita_f64_asin`/`acos`/`atan2`) un-guarded on aarch64.** They were
  `#ifdef CYRIUS_ARCH_X86` in `src/math_advanced.cyr` because they build on `f64_atan`,
  which was x86-only — while the `_compat.cyr` `f64_asin`/`acos`/`atan2` wrappers sat
  OUTSIDE the guard (a latent undefined-fn on aarch64). Cyrius v6.4.25 added
  `_f64_atan_polyfill`, so the guard is removed; the family now works on x86 (native x87
  `fpatan`) and aarch64 (an aarch64 consumer must `include "lib/math.cyr"` for the
  polyfill). Verified: `ganita_f64_atan2(1,1)` = π/4 on both arches (aarch64 via qemu).

## [1.0.2] — 2026-07-02

### Fixed

- **`ganita_f64_tanh` no longer returns NaN for large |x|.** The
  `(e^x − e^-x)/(e^x + e^-x)` form overflowed to `inf/inf = NaN` once
  `f64_exp(x)` hit +inf (|x| > ~709). Now saturates to ±1 for |x| > 20 — which is
  **bit-exact** (for |x| ≥ ~19, `tanh(x)` already rounds to exactly ±1.0 in f64,
  so no correctly-computed value changes) and NaN-safe. Surfaced by importing a
  real GPT-2-small checkpoint: its GELU `tanh(c·(x + a·x³))` overflows on the
  model's massive-activation outliers, NaN-poisoning the forward. Fixes GELU for
  every downstream consumer (rupantara `ru_gelu_fwd`, attn11 `gelu_fwd`, …).
  Regression tests added (`tests/ganita.tcyr`: `tanh(±1000)` → ±1, boundary
  bit-exactness). No API change.

## [1.0.1] — 2026-06-12

### Changed

- `cyrius` pin bumped 6.1.25 → 6.2.1 (ecosystem-wide stdlib pin sweep onto the
  current toolchain). No source changes — ganita's `[deps]` carries no carved-out
  modules. Verified green on 6.2.1: `cyrius deps` resolves cleanly, `.tcyr` suite
  11/11, bench 1/1, `dist/ganita.cyr` regenerated via `cyrius distlib`.

## [1.0.0] — 2026-06-10

**Initial carve out of the Cyrius stdlib** (cyrius v6.1.26, second half of
Phase E — the bayan/ganita data/math split). ganita becomes the upstream
source of truth for the linear-algebra & advanced-math modules; cyrius folds
`dist/ganita.cyr` byte-identical into `lib/ganita.cyr` (sandhi pattern).

### Added
- **`matrix` + `linalg` carved whole from cyrius stdlib** — the `mat_*`
  dense-matrix base API (14 fns) + the decomposition/solver suite (26 fns:
  LU / det / inverse / Cholesky / QR / Gaussian-elim / least-squares /
  eigen-sym / SVD / pseudo-inverse / rank / condition). Renamed `mat_*` →
  `ganita_mat_*`.
- **`math_advanced`** — the 13 advanced fns SPLIT out of `lib/math.cyr`:
  transcendental (`sinh`/`cosh`/`tanh`/`pow`/`asin`/`acos`/`atan2`/`asinh`/
  `acosh`/`atanh`/`hypot`) + `fibonacci`/`binomial`. Renamed `ganita_*`.
  Self-contained over f64 builtins; the `f64_exp`/`f64_ln` polyfills + F64
  constants stay in stdlib `math.cyr` (primitives), supplied by the consumer.
- **`src/_compat.cyr`** — 53 forwarding aliases exporting the legacy names
  (`mat_mul`, `f64_pow`, `binomial`, …). Deprecated; migration window only.
- **`[lib]` distlib config** — `cyrius distlib` bundles matrix + linalg +
  math_advanced + aliases into `dist/ganita.cyr` (1,358 lines), for the fold.
- Smoke entry (`src/main.cyr`, exits 42) + `tests/ganita.tcyr` (matrix +
  advanced-math + alias parity). Deep coverage stays in cyrius's
  matrix/linalg/math `.tcyr` suite.
- CI: `ci.yml` made reusable (`workflow_call`) so `release.yml` parses
  (the scaffold-template fix from cyrius v6.1.25).
