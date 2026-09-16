# No f64 cube root — the `pow(x, 1/3)` stand-in is wrong on perfect cubes and far from 1

**Filed by**: tanmatra (math audit ahead of its Rust → Cyrius port)
**Against**: `src/math_advanced.cyr` (new function), `src/_compat.cyr` (alias),
`src/math_f32.cyr` (`ganita_f32_cbrt` re-point)
**Date**: 2026-09-16
**Version**: ganita 1.2.5 / cyrius 6.6.4 (current). It reproduces identically under
ganita's own pin, 6.6.2: `lib/math.cyr` is byte-identical between the two, and 6.6.4's
folded `lib/ganita.cyr` (1.2.5) carries the same `pow`.
**Severity**: **Medium** — a missing primitive with a port waiting on it. The only
substitute is silently inexact: wrong on 88% of perfect cubes (the same failure
class as `pow(7,2) → 48.99…`, fixed in 1.2.4) and off by up to 137 ulps at the
ends of the double range. No crash, no diagnostic.
**Repro**: [`repros/2026-09-16-f64-cbrt-missing.cyr`](repros/2026-09-16-f64-cbrt-missing.cyr)
— exits with the number of failing groups: **2 today, 0 when fixed.**
**Upstream**: not filed. The function belongs here; cyrius gains it through
`lib/ganita.cyr` on the next fold, as `f64_pow` did.

## What is missing

There is no f64 cube root in ganita or the stdlib — `src/math_f32.cyr:328` says so,
and builds `ganita_f32_cbrt` on `ganita_f64_pow(|x|, 1/3)` with a sign split and
±0 / ±inf / NaN guards around it. An f64 caller has to rebuild all of that by hand,
and even when they do, the core `exp(ln(x)/3)` is not a cube root to f64 precision.

## Why tanmatra needs it

tanmatra (atomic and nuclear physics) takes cube roots in its hottest formulas, all
through Rust's `libm::cbrt`:

| Site | Use |
|---|---|
| `nucleus.rs:243` | `A^(1/3)` and `A^(2/3)` in the Bethe–Weizsäcker binding energy |
| `nucleus.rs:324` | nuclear radius `R = r₀·A^(1/3)` — also feeds `reaction.rs` Coulomb barrier and geometric cross-section |
| `scattering.rs:228` | Thomas–Fermi screening length `0.8853·a₀·Z^(-1/3)` |
| `scattering.rs:371` | form-factor radius `1.2·A^(1/3)` |
| `integration/soorat.rs:91,102` | f32 layout radii |

The port is going to use the Rust crate as its oracle: golden values generated from
Rust, asserted in Cyrius. Rust's `libm::cbrt` (a musl port) returns the correctly
rounded result for **all 300** nucleon counts `n = 1..300`; `pow(n, 1/3)` does so
for **134**. Every formula above would diverge from its golden value in the last
bits, so the port would either loosen every tolerance or carry its own cube root —
a second copy of what `ganita_f32_cbrt` already half-does.

In physics terms the error at nucleon counts is ≤ 2 ulps (~4e-16 relative), harmless
for tanmatra's answers. It matters for exact cubes, for the ends of the range, for
parity testing, and because every consumer otherwise re-rolls the guards.

## What happens

Measured on ganita 1.2.5 source under cyrius 6.6.4, x86_64. Every count and ulp figure
below is bit-identical under 6.6.2. "Guarded" is the f64 twin of
`ganita_f32_cbrt`: special values passed through, sign split, `pow(|x|, 1/3)`.

| Group | Guarded workaround | Bare `pow(x, 1/3)` |
|---|---|---|
| A: ±0, ±inf, NaN (sign-exact) | 0 / 5 wrong | **3 / 5** wrong: −0 → +0, ±inf → NaN |
| B: `cbrt(±k³) = ±k`, k = 1..1000 | **1752 / 2000** wrong | **1876 / 2000** wrong (every negative is NaN) |
| C: correctly rounded values | **6 / 12** wrong | **6 / 12** wrong |

**Perfect cubes miss low.** `1/3` rounds *down* to `0x3FD5555555555555`, so the
result is biased below the root: `cbrt(8) = 1.9999999999999998` (−1 ulp),
`cbrt(64) = 3.999999999999999` (−2), `cbrt(1728) = 11.999999999999995` (−3). A
caller who floors, or compares against an integer, gets the wrong answer. Over
k = 1..200 000, **187 877 of 200 000** perfect cubes come back wrong.

**Mid-range is 1-in-2 correctly rounded.** Over n = 1..300: 134 exact,
138 at ±1 ulp, **28 at −2 ulp** (worst: n = 286 → `6.588532274527863`, correct
`…865`).

**The ends of the range are far worse** — this is structural, not rounding luck:

| x | correct cbrt | `pow(x, 1/3)` | error |
|---|---|---|---|
| 1e300 | 1e100 | 9.999999999999827e99 | **−89 ulp** |
| 1e-300 | 1e-100 | 1.0000000000000174e-100 | **+137 ulp** |
| 2⁻¹⁰²² (DBL_MIN) | 2.812644285236262e-103 | 2.8126442852363145e-103 | **+106 ulp** |
| 2⁻¹⁰⁷⁴ (min subnormal) | 2⁻³⁵⁸ exactly | 1.7031839360032852e-108 | **+66 ulp** |

`exp(y·ln x)` rounds the product `y·ln x` to about half an ulp *of the exponent*,
and `exp` turns that into a relative error proportional to `|ln x|`. At
`|ln x| ≈ 690` that is ~1e-14 relative, i.e. ~60 ulps before `ln`'s own error is
counted. No choice of seed or constant fixes it; the scaling has to be exact.

**The f32 tests cannot see any of this.** `ganita_f32_cbrt` passes all 255 f32
perfect cubes because narrowing to f32 rounds the f64 error away. The existing
assertions (`tests/ganita.tcyr:338-345, 1050-1054`) are correct and stay green
throughout.

## Asked for

`ganita_f64_cbrt(x)`, with `f64_cbrt` in `_compat`, meeting this contract:

1. **Odd and sign-exact**: `cbrt(-x)` is `cbrt(x)` with the sign bit set, for every
   `x`. `±0 → ±0`, `±inf → ±inf`, `NaN → NaN`.
2. **Exact on perfect cubes** whose root is representable (every `k³ < 2⁵³`).
3. **Correctly rounded**, or a *stated and tested* bound **strictly below** 1 ulp,
   over the whole range — **subnormals included**. A bound under 1 ulp implies
   guarantee 2: the returned f64 cannot sit a whole ulp away from an exactly
   representable root.
4. **No intermediate overflow or underflow**: a Newton step that forms `y³` at
   `x = 1e300` overflows; at subnormal `x` it underflows.

A shape that meets all four, offered as a starting point rather than a
prescription:

- **Split the exponent exactly.** Normalise subnormals first, then write
  `|x| = m·2^(3k)` with `m ∈ [1, 8)`. `cbrt(x) = cbrt(m)·2^k`, and the `2^k` is a bit
  operation, which removes the entire far-from-1 error class above.
- **Seed** `cbrt(m)` from a short polynomial, or from the existing `pow` — on
  `[1, 8)` it is already within a few ulps.
- **Refine** with one Newton or Halley step on `m`, where `m³` cannot overflow.
- **Round** by checking the neighbours `y⁻`, `y`, `y⁺` against `m`, with their cubes
  formed exactly (two-product/FMA) — this is what buys guarantees 2 and 3.

Alternatively, port musl's `src/math/cbrt.c`, which is what Rust's `libm` crate
uses. It comes from FreeBSD `msun`'s `s_cbrt.c`, and carries SunPro's permissive
notice, which has to be preserved. It uses the same exponent split: `hx/3` plus a
bias for a 5-bit seed, then a degree-4 polynomial to 23 bits. It finishes with one
Newton step that it documents as "error < 0.667 ulps". Rust's `libm::cbrt` passes
all three repro groups: 0/5 special values wrong, 0/2000 perfect cubes wrong,
0/12 rounding rows wrong.

Then re-point `ganita_f32_cbrt` at `ganita_f64_cbrt`. Keeping its f32 guards is
harmless, and cheaper than the call.

## Test status

The repro prints per-group counts and exits with the number of failing groups for
`candidate_cbrt`, which today is the guarded workaround. **The fix is proven by
swapping `candidate_cbrt`'s body to `return ganita_f64_cbrt(x);` and seeing exit 0.**

- **Group A** pins the special values, sign of zero and of infinity included.
- **Group B** pins all 2000 perfect cubes `±k³`, k = 1..1000.
- **Group C** pins 12 correctly rounded results:
  - integers: 2, 3, 10
  - tanmatra's nucleon counts: 56, 208, 238
  - the worst mid-range row: 286
  - a fraction: 0.5
  - the ends of the range: 1e±300, DBL_MIN, the minimum subnormal

  Each expected value is the round-to-nearest f64 of the exact cube root of the exact
  binary input, computed at 120 significant digits.

Groups A–C should move into `tests/ganita.tcyr` with the fix. At that point this
file moves to `archived/` and the repro stays as a regression witness.
