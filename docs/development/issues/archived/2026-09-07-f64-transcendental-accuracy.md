# `math_advanced` accuracy: cancellation, overflow, and infinity handling

> ✅ **RESOLVED in ganita 1.2.4** (2026-09-08). All four groups closed, in the
> priority order this filing set:
>
> 1. **hypot** scales out the larger leg before squaring, so `hypot(3e116,
>    4e116) = 5e116` and `hypot(3e-116, 4e-116) = 5e-116` are now exact where
>    they were `+inf` and `0`. `hypot(inf, NaN) = +inf` — infinity outranks NaN
>    propagation, which is ordering-sensitive and now pinned by a test.
> 2. **acos** is no longer `pi/2 - asin(x)`. The half-angle form
>    `2·atan(sqrt((1-x)/(1+x)))` has no cancellation at the ends, and the branch
>    splits at 0 so both ends are covered. Measured on exactly-representable
>    arguments, the error now SHRINKS toward x = 1 where the old form's grew:
>    at 1 - 2^-50, ~0 against 1.3e-9.
> 3. **Small-|x| series** for sinh, tanh and atanh (asinh was done at 1.2.3).
>    Below 2^-26 each returns x, which IS the correctly-rounded answer; they
>    used to return exactly 0.0 below ~1e-17.
> 4. **Overflow bands**: `acosh` uses `ln(x) + ln 2` above 2^26 so it is finite
>    at 1e192 where it used to be `+inf`; `sinh`/`cosh` use `exp(|x| - ln 2)`
>    above 709 to cover the band that used to overflow.
> 5. **pow on an integral exponent** is binary exponentiation, not
>    `exp(y·ln x)`. `pow(7,2)` is exactly 49 (was 48.99999999999999296, which
>    floored to 48) and `pow(10,15)` is exactly 1e15 (was ...005.875). It also
>    gets infinite bases right for free, since it takes no logarithm.
> 6. **Infinite arguments**: `sinh(±inf) = ±inf`, `cosh(±inf) = +inf`, handled
>    in ganita because stdlib's `f64_exp` returns NaN for them. `_f64_is_int` no
>    longer calls an infinity an integer. **The underlying `f64_exp(±inf) = NaN`
>    is a stdlib defect and is NOT fixed here** — ganita only guards around it.
>
>    ✅ **Filed upstream 2026-09-08**:
>    `cyrius/docs/development/issues/2026-09-08-f64-exp-nan-for-infinite-argument.md`,
>    with a repro that exits with the number of wrong answers — 4 today, 0 when
>    fixed. Scope confirmed there as **exactly `f64_exp` and `f64_exp2`, both
>    signs of infinity**: every other f64 builtin already matches C, and
>    `f64_atan(±inf)` is bit-exactly ±π/2. Root cause is the range reduction
>    computing `inf − inf`, in the x87 native path AND `_f64_exp_polyfill`, plus
>    a second break where the `2^n` bit-pack reads `f64_to(inf) = i64::MIN` as an
>    exponent. ganita's guards can come out when that lands and ganita re-pins.
>
> Also closed: `acos`, `acosh` and `atanh` now return NaN outside their domains
> instead of whatever the formula produced.
>
> ⚠ **Addendum (ganita 1.2.11, 2026-10-01): "all four groups closed" was not true.**
> Four parts of this filing stayed open after 1.2.4. Consumers found them on
> 2026-09-30, and 1.2.11 closed them:
>
> - **§1.** Item 3's series fixed only |x| < 2^-26 (1e-8 for asinh). That is where
>   `x` alone becomes the correctly rounded answer, not where the direct forms
>   become accurate. Just above it they still lost about eps/|x|, up to 4e7 ulp for
>   sinh and 1.3e8 for asinh. Closed by fdlibm `expm1` / `log1p` forms, filed as
>   [`2026-09-30-f64-hyperbolic-and-asin-cancellation-band`](2026-09-30-f64-hyperbolic-and-asin-cancellation-band.md).
> - **§2.** Item 4's `exp(|x| - ln 2)` removed the `+inf`, but rounding `|x| - ln 2`
>   near 709 left the band up to ~495 ulp off. Closed by `_gn_exp_half`, filed as
>   [`2026-09-30-f64-sinh-cosh-overflow-band`](2026-09-30-f64-sinh-cosh-overflow-band.md).
> - **§3.** `acosh` near 1 ("~9 digits") was never addressed: `acosh(1 + 2^-52)` was
>   2.5e7 ulp off through 1.2.10. Closed in the same cancellation-band filing,
>   by log1p(t + √(2t + t²)), t = x − 1.
> - **§4.** `atan2(inf, inf) = NaN` and the inverted branch cut at −0 were never
>   closed. `ganita_f64_atan2` was byte-identical from 1.0.0 to 1.2.10. Closed by
>   [`2026-09-30-f64-atan2-signed-zero-and-nan`](2026-09-30-f64-atan2-signed-zero-and-nan.md)
>   and [`2026-09-30-f64-atan2-infinite-arguments`](2026-09-30-f64-atan2-infinite-arguments.md),
>   together with a row this filing did not have: `atan2(NaN, ±0)` returned −π/2.
>
> Not in this filing, but fixed alongside it: `asin` near ±1 (up to 1,024 ulp)
> now forms 1 − x² as (1 − |x|)(1 + |x|).


**Filed by**: ganita's 1.2.3 P(-1) sweep (math-advanced lens)
**Against**: `src/math_advanced.cyr`
**Date**: 2026-09-07
**Version**: ganita 1.2.3
**Severity**: **Medium** for the significance losses, **Low** for the infinity
handling. Every item below was reproduced against known values.

`ganita_f64_asinh` and `ganita_binomial` were the two in this module serious
enough to fix in 1.2.3 — see the [audit](../../audit/2026-09-07-v1.2.3-audit.md).
These are the rest.

## 1. Cancellation for small |x| — sinh, tanh, atanh (MEDIUM)

All three evaluate a form that cancels catastrophically near zero:
**44 % error at 1e-16, and exactly `0.0` below 1e-17**. `sinh(x) = (eˣ - e⁻ˣ)/2`
subtracts two quantities that are both ≈ 1; the answer is all rounding noise.

Fix: a series expansion below a threshold. `sinh(x) ≈ x + x³/6`, `tanh(x) ≈ x -
x³/3`, `atanh(x) ≈ x + x³/3`, each exact to within half a ulp well past where the
direct form fails. Same shape as the `asinh` fix already landed.

## 2. Overflow where the true value is finite (MEDIUM)

- **`ganita_f64_acosh`** returns `+inf` for `x > 1.34e154`, where the true value
  is ~355 and comfortably finite. Same `x*x` overflow `asinh` had; same fix
  (`ln(x) + ln 2` in the large regime).
- **`ganita_f64_hypot`** returns `inf` or `0` for **representable** hypotenuses,
  and silently loses 5 significant digits in the 1e-162…1e-154 band. This is the
  one function in the module whose entire reason for existing is that it must not
  overflow when the answer does not. Fix: scale by `max(|x|,|y|)` before squaring.
- **`ganita_f64_sinh` / `_cosh`** return `+inf` for `|x|` in (709.783, 710.476],
  where the true value is still finite.

## 3. Precision near the domain edges (LOW)

- **`ganita_f64_acos`** loses ~6 significant digits for `|x|` near 1, and
  **`ganita_f64_acosh`** ~9 near `x = 1`, neither with a documented bound. This
  matters more than the numbers suggest: `acos(dot)` — the angle between two unit
  vectors — is this library's headline use case, and unit vectors put the argument
  *exactly* where the precision is worst.
- **`ganita_f64_pow`** is off by up to 47 ulps on integer exponents:
  `pow(10,15) = 1000000000000005.9`, and `pow(7,2)` floors to 48. The `exp(y·ln x)`
  path cannot do better; an integer-exponent fast path (binary exponentiation)
  would be exact where it applies, which is most of where it is used.

## 4. Infinite arguments return NaN across the module (LOW)

`sinh(inf)`, `cosh(inf)`, `asinh(-inf)`, `pow(inf, y)`, `atan2(inf, inf)` all
return NaN where C returns the correct infinity. `_f64_is_int` claims `inf` and
`NaN` are integers, which is what routes `pow` into the wrong branch.
`ganita_f64_atan2` also inverts the branch cut at negative zero — and the comment
in `ganita_f64_pow` asserting that `-0.0` cannot be produced through the f64
helper surface is false, which is how the atan2 case is reachable at all.

## Why none of this is fixed in 1.2.3

Each item is a numerics work item — a series expansion, a scaled reformulation, or
a domain table — with its own accuracy claim to establish and pin. That is a
different discipline from closing an out-of-bounds write, and mixing the two in
one release makes both harder to review. `asinh` and `binomial` were fixed because
they were *wrong*, not merely imprecise: `asinh` returned `+inf` where the answer
was a finite negative number, and `binomial` returned wrapped i64 garbage.

## Priority order when this is picked up

1. `hypot` — its contract is specifically "does not overflow", and it does.
2. `acos` near `|x| = 1` — the headline use case sits there.
3. The small-|x| series for sinh/tanh/atanh.
4. `acosh`/`sinh`/`cosh` overflow bands.
5. `pow` integer fast path.
6. Infinity handling, module-wide, as one pass with a shared domain table.
