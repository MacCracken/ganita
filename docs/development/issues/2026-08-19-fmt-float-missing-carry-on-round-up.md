# `fmt_float` drops the carry when the fraction rounds up to 1.0

**Filed by**: ganita (1.1.3 linalg test pass — every near-integer result printed
wrong while being numerically correct)
**Against**: cyrius stdlib `lib/fmt.cyr` — vendored, so ganita cannot fix it
**Date**: 2026-08-19
**Version**: cyrius 6.5.28 (released tarball)
**Severity**: Low — display only, no wrong computation. But it misreports values
during exactly the debugging where a float's last digits matter, and it reads as
a numerical bug in the caller.

## What happens

When the fractional part rounds up to `10^decimals`, the carry into the integer
part is dropped and the fraction is printed with one digit too many:

| value | `fmt_float(v, 6)` | expected |
|---|---|---|
| `3.0` | `3.000000` ✅ | `3.000000` |
| `2.9999999` | **`2.1000000`** | `3.000000` |
| `1.9999999` | **`1.1000000`** | `2.000000` |
| `0.99999999` | **`0.1000000`** | `1.000000` |
| `-2.9999999` | **`-2.1000000`** | `-3.000000` |
| `0.5` | `0.500000` ✅ | `0.500000` |
| `2.1` | `2.100000` ✅ | `2.100000` |

The tell is the digit count: the fraction field prints **seven** digits for
`decimals = 6`. The rounded fraction reaches `1000000`, which is emitted
verbatim instead of resetting to `000000` and incrementing the integer part.

## Why it looks like a numerics bug

A correct result one ulp below an integer — routine after any decomposition —
prints as if it were off by nearly 0.9. During the ganita 1.1.3 linalg pass,
`cholesky_solve` returning exactly `3.0` (to within 1e-9) printed as
`2.1000000`, and `least_squares` returning `1.0` printed as `0.1000000`. Both
were verified correct by numeric comparison; only the printer was wrong. Anyone
reading the output alone would go hunting in the solver.

## Reproduction

```cyrius
# with lib/fmt.cyr + lib/math.cyr in scope
fmt_float(f64_sub(f64_from(3), f64_div(f64_from(1), f64_from(10000000))), 6);
# prints 2.1000000, want 3.000000
```

## Asked for

After rounding the fractional part, detect `frac == 10^decimals`: reset it to
zero and increment the integer part (propagating the sign correctly, so
`-2.9999999` becomes `-3.000000`). The zero-padding path then emits the right
number of digits on its own.

## Note for consumers

Until this lands, do not read `fmt_float` output as authoritative when a value
sits just below an integer — compare numerically. ganita's own test suite
asserts with `f64_abs(f64_sub(a, b)) < tol` rather than on printed text, so it
is unaffected.
