# `ganita_f64_atan2` ignores the sign of a zero, and answers a NaN `y` at `x = ±0` with −π/2

> ✅ **RESOLVED in ganita 1.2.11** (2026-10-01), together with its companion
> [`2026-09-30-f64-atan2-infinite-arguments`](2026-09-30-f64-atan2-infinite-arguments.md):
> one rewrite of `ganita_f64_atan2`, the merged patch from that filing.
>
> - **How.** NaN is handled first. Zeros are decided on their sign bits, never with
>   `f64_eq` / `f64_gt`: atan2(±0, x > 0 or +0) = ±0, atan2(±0, x < 0 or −0) = ±π,
>   and atan2(y ≠ 0, ±0) = ±π/2. Every finite non-zero pair keeps the 1.2.10
>   arithmetic, **bit for bit** (1,000,000 random pairs, x86_64 and aarch64). The
>   special-case tests are inline on the magnitude bits, about 4 ns per call; written
>   as helper calls they cost 12.
> - **One deliberate departure from the sketch.** A NaN argument returns **the NaN
>   operand** (y if y is NaN, else x), payload kept, rather than the default NaN
>   `0/0`. That is the convention `ganita_f64_hypot` and every one-argument function in
>   the module follow, and C99 asks only for a NaN.
> - **The repro exits 0** (was 5) on both architectures. It is the regression witness.
> - **Checked against the full C99 F.10.1.4 table**: 289 pairs built from 17 values
>   (±0, ±denormal_min, ±1e-300, ±1, ±1e300, ±DBL_MAX, ±inf, three NaNs). All 189
>   special rows are bit-exact on both architectures, including the signs of zero;
>   1.2.10 fails 19.
> - **Suite.** One group serves both filings, with 65 assertions: all 12 rows of this
>   repro, the companion's 20, NaN-ness and NaN-payload rows, and 15 f32 rows
>   (`ganita_f32_atan2` widens onto this function). The doc comment and the
>   inverse-trig banner now state the C99 table, and the "(0, 0) ... convention — C
>   libm matches" note is gone.
> - **Consumer impact.** hisab's `cx_arg(cx_conj(-1 + 0i))` is now −π, and atan2's range
>   is [−π, π].

**Status:** ✅ **RESOLVED in ganita 1.2.11** — found by hisab on its cyrius 6.6.6 → 6.6.12 bump.
**Placement:** unpinned.
**Discovered:** 2026-09-30, hisab 3.2.2 (verifying what cyrius 6.6.8's IEEE `f64_neg` changed)
**Severity:** Medium — a wrong branch of a public function (C99 Annex F conformance), and one
fabricated plausible answer for NaN input.
**Affects:** ganita 1.2.4 – 1.2.10 (the function is unchanged in that range); reachable through
`f64_neg` from cyrius **6.6.8**, which made `f64_neg(+0)` return −0 on x86.

## Summary

`ganita_f64_atan2(y, x)` decides its quadrant with IEEE comparisons (`f64_eq`, `f64_gt`,
`f64_lt`), and those cannot see the sign of a zero. So:

| call | C99 F.10.1.4 | ganita 1.2.10 |
|---|---|---|
| `atan2(-0, +0)` | −0 | **+0** |
| `atan2(+0, -0)` | +π | **+0** |
| `atan2(-0, -0)` | −π | **+0** |
| `atan2(-0, x<0)` | −π | **+π** |
| `atan2(NaN, ±0)` | NaN | **−π/2** |

The first four are the branch cut on the negative real axis. The comment above the function
says the `(0, 0)` case follows a "convention — C libm matches". C libm returns ±0 or ±π there,
by the signs.

The last row is a separate defect with the same root. With `x = ±0` the function asks
`f64_eq(y, 0)` and then `f64_gt(y, 0)`. Both are false for NaN, so it falls through to
`return f64_neg(F64_PI_2)`. That is a plausible finite angle for an input that has none.

## This is the unfinished part of an earlier filing

`archived/2026-09-07-f64-transcendental-accuracy.md` §4 named the branch-cut half:
"`ganita_f64_atan2` also inverts the branch cut at negative zero." The filing is marked
**RESOLVED in ganita 1.2.4**, "all four groups closed". But `ganita_f64_atan2` is
byte-identical from 1.2.4 through 1.2.10, so this item was not closed with the rest.

It went unnoticed because nothing could reach it. Before cyrius 6.6.8, x86's `f64_neg` computed
`0.0 - x`, so `f64_neg(+0)` was +0. A −0 came only from a multiplication, such as `0 * -1`, or
from a literal bit pattern. From 6.6.8 on, `f64_neg` flips the sign bit, and 1.2.7 changed
`ganita_f64_pow`'s ±0 rows for that reason. `atan2` did not get the same change.

## Reproduction

`repros/2026-09-30-f64-atan2-signed-zero-and-nan.cyr` checks 12 rows of the C99 table by bit
pattern. `f64_eq` would treat −0 and +0 as equal, and the sign is the point of each row. The
exit code is the number of wrong rows.

```
cyrius build docs/development/issues/repros/2026-09-30-f64-atan2-signed-zero-and-nan.cyr /tmp/atan2z
/tmp/atan2z; echo "exit=$?"      # -> 5 on 1.2.10: the five rows in the table above
```

The other seven rows pass today and are there as controls: `atan2(±0, +1)`, `atan2(+0, -1)`,
`atan2(±1, ±0)` and `atan2(1, NaN)`.

## What a consumer sees

In hisab, `cx_arg(cx_conj(cx_new(-1, 0)))` is `atan2(-0, -1)` and returns +π. By
`carg(conj z) = -carg(z)` it should be −π. `cx_sqrt` and `cx_ln` go through `cx_arg`, so they
land on the wrong side of their cuts too. `cx_arg(cx_new(0, NaN))` returns −π/2.

## Proposed fix

Decide the zero cases on the sign bits, not with comparisons, and let a NaN through before any
quadrant test:

```
fn ganita_f64_atan2(y, x): i64 {
    if (_f64_is_nan_pat(y) == 1 || _f64_is_nan_pat(x) == 1) { return f64_div(0, 0); }
    var ysign = y & 0x8000000000000000;
    if ((y & 0x7FFFFFFFFFFFFFFF) == 0) {            # y = +-0
        if ((x >> 63) & 1 == 1) { return F64_PI | ysign; }   # x < 0 or x = -0
        return y;                                    # x > 0 or x = +0
    }
    if ((x & 0x7FFFFFFFFFFFFFFF) == 0) { return F64_PI_2 | ysign; }
    var q = f64_atan(f64_div(y, x));
    if ((x >> 63) & 1 == 0) { return q; }
    if (ysign != 0) { return f64_sub(q, F64_PI); }
    return f64_add(q, F64_PI);
}
```

This is a sketch. It keeps the existing arithmetic for every non-zero, non-NaN input. The
remaining C99 rows, the ±∞ cases, are not checked by the repro and are worth adding to the
suite alongside it.

## Consumer-side workaround

None taken. hisab reaches this only through `cx_arg` and its callers. It keeps its tests off the
signed-zero branch cut until the fix lands. Its record is
`hisab/docs/development/issues/2026-09-30-ganita-atan2-signed-zero-and-nan.md`.
