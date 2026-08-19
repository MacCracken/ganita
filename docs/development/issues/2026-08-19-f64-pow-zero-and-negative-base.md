# `ganita_f64_pow` returns NaN for a zero or negative base

**Filed by**: ganita (1.1.2 f32-tier test pass — the gap surfaced through
`ganita_f32_pow` / `ganita_f32_cbrt`)
**Date**: 2026-08-19
**Version**: ganita 1.1.2 / cyrius 6.5.28
**Severity**: Medium — silently wrong (NaN) for inputs a caller has every reason
to expect to work. No crash, no diagnostic.

## What happens

```cyrius
fn ganita_f64_pow(base, exp): i64 {
    return f64_exp(f64_mul(exp, f64_ln(base)));
}
```

The identity `x^y = e^(y·ln x)` is only valid for `x > 0`. Everything else falls
out of the domain of `ln`:

| Call | Returns | Should be |
|---|---|---|
| `pow(0, 2)` | NaN | `0.0` |
| `pow(0, y)` for any `y > 0` | NaN | `0.0` |
| `pow(-2, 2)` | NaN | `4.0` |
| `pow(-2, 3)` | NaN | `-8.0` |
| `pow(x, 0)` | `1.0` ✅ | `1.0` |
| `pow(2, 10)` | `1024.0` ✅ | `1024.0` |

`ln(0)` is `-inf` and `ln(negative)` is NaN, so NaN propagates out through `exp`.
Verified at 1.1.2 on released cyrius 6.5.28.

## Blast radius

`ganita_f32_pow` is a thin widen-compute-narrow wrapper, so it inherits the whole
gap. `ganita_f32_cbrt` did too, in two separate ways:

- **Negative inputs** — handled. The sign split (`cbrt(x) = -(|x|^(1/3))` for
  `x < 0`) exists precisely because of this defect, and the 1.1.2 tests pin it:
  removing the split turns `cbrt(-8)` into NaN while every positive input still
  passes, which is exactly the shape of bug a positives-only test misses.
- **Zero** — was NOT handled. `cbrt(0)` returned NaN until 1.1.2 added an
  explicit `±0 -> ±0` guard. That guard is a workaround at the f32 layer for an
  f64 defect; it should stay even after this issue is fixed, since it is also
  the cheaper path.

## Reproduction

```cyrius
# with lib/math.cyr + src/math_advanced.cyr + src/math_f32.cyr in scope
ganita_f32_pow(f32_from(f64_from(0)), f32_from(f64_from(2)));   # NaN, want 0.0f
ganita_f32_pow(f32_from(f64_from(0-2)), f32_from(f64_from(2))); # NaN, want 4.0f
```

## Asked for

Special-case the domain in `ganita_f64_pow` ahead of the exp/ln path:

- `exp == 0`: return `1.0` (already correct; keep it first).
- `base == 0`: `0.0` for `exp > 0`, `+inf` for `exp < 0`.
- `base < 0` with an **integral** `exp`: compute `|base|^exp`, negate when `exp`
  is odd. A non-integral `exp` on a negative base is genuinely undefined in the
  reals — NaN is correct there and should stay.

## Test status

`tests/ganita.tcyr` carries a **self-expiring** group, `f32: known domain gaps`,
asserting the *current* NaN behaviour so the gap is measured rather than merely
known. Those two assertions **fail when this issue is fixed** — that is
intended. Rewrite them to the correct answers (`0.0f` and `4.0f`) as part of the
fix, and delete this file.
