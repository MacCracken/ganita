# `fmt_float` drops the carry when the fraction rounds up to 1.0

> ✅ **RESOLVED UPSTREAM in cyrius 6.5.30**, and reached ganita at **1.2.1**
> (2026-09-07) when the pin moved 6.5.36 → 6.6.0 and `lib/` was re-vendored.
> The fix is the one proposed below, applied verbatim: the fraction is computed
> BEFORE the integer part is emitted, and the carry is folded into `whole`
> (`lib/fmt.cyr:301-308`, where the reasoning is now recorded in place, credited
> to this filing). Verified against 6.6.0 — every row of the table below now
> prints its expected value, `-2.9999999` included, and `10 - 1e-7` prints
> `10.000000`, which is the case that proves the carry propagates through a
> change in integer digit count. Closed at ganita 1.2.2 with nothing to change
> in ganita itself.


**Filed by**: ganita (1.1.3 linalg test pass — every near-integer result printed
wrong while being numerically correct)
**Against**: cyrius stdlib `lib/fmt.cyr` — vendored, so ganita cannot fix it
**Filed upstream**: ✅ `cyrius/docs/development/issues/2026-08-19-fmt-float-missing-carry-on-round-up.md`
(with repro `repros/2026-08-19-fmt-float-carry.cyr` and a verified fix). That is the
authoritative report — this file is ganita's consumer-side record; close it when the
upstream one is resolved and ganita re-pins.
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

Root-caused to `lib/fmt.cyr:255` `fmt_float_buf`: the integer part is emitted at
line 281, *before* the fraction is computed at line 287, so a carry has nowhere
to go. The zero-pad block cannot rescue it either — `pad = decimals - flen`
goes negative when the fraction has one digit too many, so the padding branch is
skipped and `1000000` is written verbatim.

Fix (verified against the released 6.5.28 toolchain by running a patched copy
side by side with the stock one): compute the fraction first, then
`if (frac >= f64_to(scale)) { frac = 0; whole = whole + 1; }` before emitting
the integer part. Every broken case is corrected, every already-correct case is
byte-identical, and the non-finite path is untouched. `9.9999999 -> 10.000000`
confirms the carry propagates through a change in integer digit count. Full
detail and the before/after table are in the upstream filing.

## Note for consumers

Until this lands, do not read `fmt_float` output as authoritative when a value
sits just below an integer — compare numerically. ganita's own test suite
asserts with `f64_abs(f64_sub(a, b)) < tol` rather than on printed text, so it
is unaffected.
