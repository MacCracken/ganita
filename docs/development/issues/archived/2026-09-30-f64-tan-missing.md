# No f64 tangent: `f64_sin(x) / f64_cos(x)`, the only stand-in, is up to 2 ulp off

> ✅ **RESOLVED in ganita 1.2.11** (2026-10-01). New: `ganita_f64_tan`, the `f64_tan` alias,
> and `ganita_f32_tan`. The f32 one is the consumer request "please don't leave f32_tan
> in the cold".
>
> - **How.**
>   - A port of fdlibm 5.3 `s_tan.c` + `k_tan.c` (private `_gn_k_tan`), checked line by
>     line against fdlibm and against abaco 2.4.10's `_eval_k_tan`.
>   - It reduces through stdlib math's `_f64_rem_pio2`, as this filing suggested,
>     which is the reducer `f64_sin` / `f64_cos` use. That symbol is private, and
>     stdlib has carried it only since **cyrius 6.6.9**. The decision and its cost on
>     older pins (a compile error if tan is called, a warning otherwise on x86_64)
>     are recorded in [ADR 0003](../../../adr/0003-tan-uses-stdlib-rem-pio2.md).
>   - `ganita_f32_tan` widens onto it.
> - **Measured** against mpmath:
>   - Within 1 ulp everywhere measured. The worst found is 0.940 ulp, at
>     x = 0x4725D8E500000000.
>   - On [−π/2, π/2]: 0.77 ulp worst, 96.4% correctly rounded. The sin/cos quotient
>     on the same inputs: 1.84 ulp, 68.4%.
>   - On [1, 1e300]: 0.81 ulp, 96.4% (sin/cos 1.82, 67.7%).
>   - Every f32 value as an argument: 98.1% correctly rounded, the same bits on x86_64
>     and aarch64.
> - **`ganita_f32_tan` is correctly rounded for every f32.** All 2,139,095,040
>   non-negative finite f32 values were scanned on both architectures. 45 lie within
>   16 double-ulps of an f32 rounding midpoint (7 within 2, one exactly on one), and
>   every one rounds correctly by mpmath. Negative arguments follow by bit-exact
>   oddness.
> - **The repro exits 0**, with `candidate_tan` swapped to `ganita_f64_tan` exactly as
>   specified. With the sin/cos quotient as the candidate it exits 6. It is the
>   regression witness.
> - **Suite.** The tan group (73 assertions) covers the 8 repro rows, ±0, ±inf, NaN,
>   odd symmetry, the 2^-27 guard pinned from both sides, both sides of the 0.6744
>   fold, the coefficients, the odd-quadrant −1/tan path, large arguments up to
>   DBL_MAX, f32 rows, and `f64_tan` in the alias group.
> - **Cost.** Faster than the quotient it replaces: 5% to 24% across runs, not 2×.
>   tan's kernel alone costs about 2.4× sin's.

**Status:** ✅ **RESOLVED in ganita 1.2.11** — feature request from abaco 2.4.11; abaco ships its own kernel from 2.4.10.
**Placement:** unpinned.
**Discovered:** 2026-09-30, abaco 2.4.10 (replacing its evaluator's `sin / cos` tangent).
**Severity:** Low — a missing primitive. The stand-in is finite and close, but it is correctly
rounded at only ~70% of arguments and up to 2 ulp off elsewhere.
**Affects:** ganita 1.2.10 and stdlib `math` at cyrius 6.6.11: neither defines `tan` / `f64_tan`
(`grep -rn "fn [a-z0-9_]*_tan(" src lib/math.cyr` finds nothing). Measured on 1.2.10, cyrius 6.6.11.

## Summary

ganita has the rest of the trig family (`asin`, `acos`, `atan2` on top of stdlib `f64_atan`), and
stdlib `math` has `f64_sin` / `f64_cos` as fdlibm ports on `_f64_rem_pio2`. There is no tangent, so
a consumer divides: two results, each within 1 ulp, then a rounded division. Over 6,000 sampled
points (4,000 in [−1.6, 1.6], 2,000 in [−100, 100]) against a 120-digit oracle:

| | correctly rounded | 1 ulp | 2 ulp |
|---|---|---|---|
| `f64_sin(x) / f64_cos(x)` | 4,095 (68.3%) | 1,895 | 10 |
| fdlibm `k_tan` on `_f64_rem_pio2` | 5,796 (96.6%) | 204 | 0 |

abaco's own measurement for 2.4.10 (30,008 points) agrees: 97.6% against 69.7%, at most 1 ulp
against 2 ulp.

## Reproduction

`repros/2026-09-30-f64-tan-missing.cyr` (exit = rows more than 1 ulp from the correctly rounded
tan, from Python `Fraction`/`Decimal` at 120 digits with π by Machin's formula. The last two rows,
0.5 and 3.0, are controls):

```
cyrius build docs/development/issues/repros/2026-09-30-f64-tan-missing.cyr /tmp/tanm
/tmp/tanm; echo "exit=$?"      # -> 6 on 1.2.10 (also 6 on aarch64 under qemu)
```

```
  WRONG tan(0.770994674674816)  got 0x3fef1759205e500e  want 0x3fef1759205e500c  off 2 ulp
  WRONG tan(-40.07147885594231)  got 0x3feefb395bd7179b  want 0x3feefb395bd7179d  off 2 ulp
  ...
rows wrong: 6
```

## Proposed fix (tested downstream)

Add `ganita_f64_tan(x)` to `src/math_advanced.cyr`, with `f64_tan` in `_compat`, as a port of
fdlibm 5.3 `s_tan.c` + `k_tan.c` (FreeBSD msun) on stdlib `math`'s `_f64_rem_pio2`, the same reducer
`f64_sin` / `f64_cos` use:

```
if (ix <= 0x3FE921FB) {                          # |x| <= ~pi/4
    if (ix < 0x3E400000) { return x; }           # |x| < 2^-27: tan x = x, -0 kept
    return k_tan(x, 0, 1);
}
if (ix >= 0x7FF00000) { return f64_sub(x, x); }  # +-inf, NaN -> NaN
var y: i64[2];
var n = _f64_rem_pio2(x, &y);
return k_tan(load64(&y), load64(&y + 8), 1 - ((n & 1) << 1));
```

A tested port already exists: abaco 2.4.10 `src/eval.cyr`, `_eval_k_tan` / `_eval_tan`. It is plain
f64 arithmetic with the 13 coefficients T0–T12 and π/4 hi/lo written inline, so it has no table,
no global state and the same bits on every target. With `candidate_tan` swapped to it, the repro
exits 0. Suggested tests: odd symmetry, `tan(−0) = −0`, `tan(±inf)` and `tan(NaN)` are NaN, and the
six repro rows.

ganita already lists `math` in `[deps].stdlib`, so it can call `_f64_rem_pio2`. That function is
private to `lib/math.cyr`, though. If depending on it from ganita is unwanted, the alternative is
`f64_tan` in `lib/math.cyr`, next to `f64_sin` / `f64_cos`.

## Consumer-side workaround

abaco carries the kernel above privately from 2.4.10. Once a stdlib tangent exists, it can delete
that kernel and stop calling the private `_f64_rem_pio2`.
