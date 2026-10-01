# `ganita_f64_sinh` / `ganita_f64_cosh` are up to ~500 ulp off for 709 < |x| ≤ 710.47

**Status:** 🟡 **OPEN** — found during abaco 2.4.9's final review; not repaired.
**Placement:** unpinned.
**Discovered:** 2026-09-30, while verifying the cancellation-band filing
(`2026-09-30-f64-hyperbolic-and-asin-cancellation-band.md`) for abaco 2.4.9.
**Severity:** Low — finite, plausible values that are wrong in the last ~9 bits (up to 496 ulp),
on a narrow band of large arguments.
**Affects:** ganita 1.2.4 – 1.2.10 (the branch was added in 1.2.4). Measured on 1.2.10, cyrius 6.6.11.

## Summary

For |x| > 709 (`_F64_EXP_BIG`, `src/math_advanced.cyr:31`) `f64_exp(|x|)` overflows, so `sinh`
(`:62-66`) and `cosh` (`:91`) switch to `exp(|x| − ln 2)`. That is the right identity, but
`|x| − ln 2` is rounded to a double near 709, losing up to half an ulp of 709 (~5.7e-14 absolute),
and `exp` turns an absolute argument error into the same relative error: ~5.7e-14 / 2^-52 ≈ 256
ulp per half-ulp, so up to ~500 ulp. Every one of 4,001 inputs sampled across
[709.78, 710.4759] was more than 2 ulp off; the worst is 496 ulp at 710.4755135003535.

## Reproduction

`repros/2026-09-30-f64-sinh-cosh-overflow-band.cyr` (exit = rows more than 2 ulp from the
correctly rounded value, mpmath at 300 bits; |x| = 708 rows are controls):

```
cyrius build docs/development/issues/repros/2026-09-30-f64-sinh-cosh-overflow-band.cyr /tmp/shband
/tmp/shband; echo "exit=$?"      # -> 8 on 1.2.10
```

```
  WRONG sinh(709.5)  got 0x7fd81e9b4b52d23e  want 0x7fd81e9b4b52d0c9  off 373 ulp
  WRONG sinh(710.4755135003535)  got 0x7feffd294ef599c8  want 0x7feffd294ef597d8  off 496 ulp
  WRONG cosh(710.0)  got 0x7fe3e21a4645092d  want 0x7fe3e21a464507f9  off 308 ulp
  ...
rows wrong: 8
```

## Proposed fix (tested)

fdlibm's form (`e_sinh.c` / `e_cosh.c`, the [log(DBL_MAX), overflow threshold] case): halve the
argument instead of subtracting ln 2 — `|x|/2` is exact — and square through the result:

```
var w = f64_exp(f64_mul(a, F64_HALF));
var h = f64_mul(f64_mul(w, F64_HALF), w);      # sinh: negate for x < 0; cosh: return h
```

On a copy of 1.2.10: worst error over the same 4,001 points drops from 496 to 2 ulp for both
functions (0 points above 2 ulp), the repro exits 0, and `cyrius test` stays at 597 passed,
0 failed. `w·½` is exact and `w` stays finite (≤ e^355.3), so the product cannot overflow
before the true result does.

## Consumer-side workaround

None in abaco: its evaluator's `sinh` / `cosh` pass ganita's values through.
