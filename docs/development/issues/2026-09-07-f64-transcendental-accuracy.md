# `math_advanced` accuracy: cancellation, overflow, and infinity handling

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
