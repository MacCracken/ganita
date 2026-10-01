# `ganita_f64_atan2` answers NaN when both arguments are infinite

> ✅ **RESOLVED in ganita 1.2.11** (2026-10-01), together with its companion
> [`2026-09-30-f64-atan2-signed-zero-and-nan`](2026-09-30-f64-atan2-signed-zero-and-nan.md),
> by the merged patch below. The companion's banner covers the shared parts and the
> one departure (a NaN argument returns the NaN operand).
>
> - **How.** When both arguments are infinite, the answer comes from the sign bits
>   before the quotient is formed: ±π/4 (`0x3FE921FB54442D18`) for x = +∞ and ±3π/4
>   (`_F64_3PI_4` = `0x4002D97C7F3321D2`) for x = −∞. `atan2(−0, −∞)` is −π, through the
>   companion's fix.
> - **The repro exits 0** (was 4) on x86_64 and on aarch64 (qemu). It is the
>   regression witness.
> - **One-infinite sweep.** 400,000 pairs with exactly one argument infinite, 0 wrong.
>   1.2.10 got 6,195 of them wrong, every one (−0, −∞).
> - **f32.** `ganita_f32_atan2(±inf, ±inf)` returns `0x3F490FDB` / `0xBF490FDB` /
>   `0x4016CBE4` / `0xC016CBE4` on both architectures.
> - **Suite.** All 20 rows of this repro are in the shared group (65 assertions).
> - **Records corrected.** Addenda were added to
>   `archived/2026-09-07-f64-transcendental-accuracy.md` (§4 was never closed, though
>   its banner says it was) and `archived/2026-09-07-f32-nan-inf-edges.md` (§2 blamed
>   `exp`).

**Status:** ✅ **RESOLVED in ganita 1.2.11** — found by abaco 2.4.9's project audit.
**Placement:** unpinned.
**Discovered:** 2026-09-30, abaco 2.4.9 project audit (finding `eval-functions-atan2-nan-signed-zero-inf`:
`atan2` in abaco's expression evaluator. abaco fixed the NaN-input half on its side and deferred the
signed-zero and (±∞, ±∞) rows to ganita.)
**Severity:** Low. Four inputs of a public function return NaN where C99 Annex F defines an exact
angle. The NaN is visible and propagates, so no caller gets a plausible wrong number. The archived
filing that first named this row rated it Low too.
**Affects:** ganita 1.0.0 – 1.2.10. `ganita_f64_atan2` is byte-identical at every tag in that range.
Measured at 1.2.10 (HEAD `97e922b`) on cyrius 6.6.11, on x86_64 and on aarch64 under qemu. Also
measured through stdlib `lib/ganita.cyr` 1.2.9 as vendored by cyrius 6.6.12 (abaco 2.4.9).
`ganita_f32_atan2` forwards to this function and has the same four wrong rows.

## Summary

`ganita_f64_atan2(y, x)` special-cases only `x == 0`. Every other input goes through
`atan(y / x)`. When both arguments are infinite, `y / x` is `∞ / ∞`, which is NaN, and the NaN
survives the quadrant correction:

| call | C99 F.10.1.4 | ganita 1.2.10 |
|---|---|---|
| `atan2(+∞, +∞)` | +π/4 `0x3FE921FB54442D18` | **NaN** `0xFFF8000000000000` |
| `atan2(−∞, +∞)` | −π/4 `0xBFE921FB54442D18` | **NaN** `0xFFF8000000000000` |
| `atan2(+∞, −∞)` | +3π/4 `0x4002D97C7F3321D2` | **NaN** `0xFFF8000000000000` |
| `atan2(−∞, −∞)` | −3π/4 `0xC002D97C7F3321D2` | **NaN** `0xFFF8000000000000` |

The NaN bits are x86's default NaN. On aarch64 the same four rows return `0x7FF8000000000000`.

The other infinite rows of the C99 table are already right, except for the one signed-zero row
described below. `atan2(±∞, finite x)` gives ±π/2. For finite `y > 0`, `atan2(±y, +∞)` gives ±0
and `atan2(±y, −∞)` gives ±π. All of these are bit-exact. The repro keeps them as controls.

The expected values are the doubles nearest π/4 and 3π/4, computed with mpmath at 300 bits. They
sit 0.276 ulp and 0.207 ulp from the exact values. `3 · fl(π/4)` and `fl(π/2) + fl(π/4)` both round
to the same `0x4002D97C7F3321D2`.

## How this relates to other filings

**Companion: `2026-09-30-f64-atan2-signed-zero-and-nan.md`** (open, filed today by hisab). That
filing covers the signed-zero and NaN rows. It ends with "The remaining C99 rows, the ±∞ cases, are
not checked by the repro and are worth adding to the suite alongside it." This filing covers those
rows. Its repro does not repeat the companion's rows, and the companion's rows are not counted here.

One ±∞ row of the C99 table is the companion's defect. `atan2(−0, −∞)` returns
`0x400921FB54442D18` (+π) where C99 says −π. That is the companion's `atan2(−0, x < 0)` defect with
`x = −∞`. The companion's sign-bit fix repairs it: after the combined fix below it returns
`0xC00921FB54442D18`. It is not counted here. The other three `(±0, ±∞)` rows are right today.

**Archived: `archived/2026-09-07-f64-transcendental-accuracy.md` §4** listed `atan2(inf, inf)` among
the infinite arguments that return NaN. The filing is marked **RESOLVED in ganita 1.2.4**, "all four
groups closed". The resolution's item 6 names `sinh`, `cosh` and `_f64_is_int`, and not `atan2`.
`ganita_f64_atan2` has not changed since 1.0.0, so this row was never closed. The companion found
the same gap for that section's branch-cut sentence.

**Archived: `archived/2026-09-07-f32-nan-inf-edges.md` §2** says `pow` and `atan2` inherit
`exp(±inf) = NaN` through the f32 wrappers. `atan2` calls no `exp`. The f32 NaN for these rows comes
from this defect, through the widening wrapper `ganita_f32_atan2` (`src/math_f32.cyr:285`). At
1.2.10, `ganita_f32_atan2(±inf, ±inf)` returns `0xFFC00000` on x86_64 (`0x7FC00000` on aarch64) for
all four sign combinations. After the fix it returns `0x3F490FDB`, `0xBF490FDB`, `0x4016CBE4` and
`0xC016CBE4` on both, the nearest floats to ±π/4 and ±3π/4.

## Reproduction

`repros/2026-09-30-f64-atan2-infinite-arguments.cyr` checks 20 rows by bit pattern:

- the 4 rows where both arguments are infinite;
- 6 rows with infinite `y` and finite `x`: `x = ±1` with both signs of `y`, plus `(+∞, −0)` and
  `(−∞, +0)`;
- 6 rows with finite non-zero `y` and infinite `x`: `y = ±1` with both signs of `x`, plus
  `(DBL_MAX, −∞)` and `(−4.9e-324, +∞)`;
- 4 finite controls in the same quadrants as the failing rows: `(±1, ±1)`.

The exit code is the number of wrong rows.

```
cyrius build docs/development/issues/repros/2026-09-30-f64-atan2-infinite-arguments.cyr /tmp/atan2inf
/tmp/atan2inf; echo "exit=$?"      # -> 4 on 1.2.10: the four rows in the table above
```

`cyrius build --aarch64` of the same file, run under `qemu-aarch64`, also exits 4.

The 12 infinite rows that pass are there so a fix cannot break them unseen. The `(±∞, ±0)` rows go
through the `x == 0` branch, and the companion's fix rewrites that branch.

## What a consumer sees

In abaco 2.4.9 (cyrius 6.6.12, stdlib ganita 1.2.9), `1e200*1e200` evaluates to `+Inf`. Each of
`atan2(1e200*1e200, 1e200*1e200)` and its three sign variants evaluates to `0xFFF8000000000000` with
error code `ABACO_ERR_NONE`. In the same build, `atan2(1e200*1e200, 1)` is π/2 and
`atan2(1, 0-1e200*1e200)` is π, both right.

## Root cause

`src/math_advanced.cyr:709-720`, `ganita_f64_atan2`:

- Line 710 special-cases `x == 0` and nothing else.
- Line 715 is `var q = f64_atan(f64_div(y, x));`. For two infinities, `f64_div` is the IEEE 754
  invalid operation `∞ / ∞`. It returns NaN, measured as `0xFFF8000000000000` on x86_64 for
  `(+∞, +∞)` and `(−∞, −∞)`.
- `f64_atan(NaN)` is NaN.
- Lines 716-719 return `q`, `q − π` or `q + π`. All three are NaN.

The other infinite rows pass because the quotient is exact. `y/x` is ±0 or ±∞, `f64_atan(±∞)` is
exactly ±π/2 (`0x3FF921FB54442D18`), and `π − π/2` is exact because the two constants share a
significand. Over 400,000 random pairs with one infinite argument and one finite non-zero argument,
1.2.10 returned the C99 value every time, on both x86_64 and aarch64.

## Proposed fix

When both arguments are infinite, answer from the sign bits before the quotient is formed. Below,
that block is merged with the companion filing's sketch into one function. This is the tested
patch:

```
# 3π/4, the double nearest it (C99 atan2(±∞, −∞) = ±3π/4).
var _F64_3PI_4 = 0x4002D97C7F3321D2;

fn ganita_f64_atan2(y, x): i64 {
    if ((_f64_is_nan_pat(y) == 1) || (_f64_is_nan_pat(x) == 1)) { return f64_div(_F64_ZERO, _F64_ZERO); }
    var ysign = y & 0x8000000000000000;
    var xneg = (x >> 63) & 1;
    if ((y & 0x7FFFFFFFFFFFFFFF) == 0) {
        if (xneg == 1) { return F64_PI | ysign; }
        return y;
    }
    if ((x & 0x7FFFFFFFFFFFFFFF) == 0) { return F64_PI_2 | ysign; }
    if ((_f64_is_inf(y) == 1) && (_f64_is_inf(x) == 1)) {      # this filing
        if (xneg == 1) { return _F64_3PI_4 | ysign; }
        return F64_PI_4 | ysign;
    }
    var q = f64_atan(f64_div(y, x));
    if (xneg == 0) { return q; }
    if (ysign != 0) { return f64_sub(q, F64_PI); }
    return f64_add(q, F64_PI);
}
```

The four-line `_f64_is_inf` block is this filing's part. Everything else is the companion's sketch,
with three edits that do not change behaviour:

- parentheses made explicit;
- the sign of `x` read once into `xneg`;
- `f64_div(0, 0)` written as `f64_div(_F64_ZERO, _F64_ZERO)`, which has the same bits.

The block can go anywhere before the quotient, because an infinity is neither a NaN nor a zero.
`_f64_is_inf` (line 37) and `F64_PI_4` (stdlib `lib/math.cyr`) already exist. The patch also
rewrites the doc comment above the function and the stale `(0, 0)` note at lines 660-661 so that
both state the C99 table.

Verified on private copies of 1.2.10, with cyrius 6.6.11:

- **Both repros pass with the fix.** This repro exits 0 and the companion's exits 0, on x86_64 and
  on aarch64 (qemu). On the unmodified copy they exit 4 and 5.
- **The fix composes with the companion's sketch.** The sketch verbatim, with the block inserted,
  also passes both repros.
- **The block works alone.** Applied on its own to 1.2.10, after the `x == 0` test, it takes this
  repro to 0 and leaves the companion's at 5.
- **No finite result changes.** Over 1,000,000 random finite non-zero pairs, half of them with equal
  exponents, the patched function is bit-identical to 1.2.10 on both arches. Over 400,000
  one-infinite pairs it still returns the C99 value every time.
- **The suite and CI gates pass.** `cyrius test` gives 597 passed, 0 failed (597 total), the file
  summary 1 passed, 0 failed, and no warnings, the same as on the unmodified copy.
  `cyrius fmt --check` and `cyrius lint` are clean. `cyrius coverage --min 100` gives 139/139, and
  `scripts/coverage-honest.sh 88` gives 144/162. `cyrius fuzz` gives 1 passed. After `cyrius distlib`,
  `cyrius distlib --all --check` passes.

The patch adds no rows to `tests/ganita.tcyr`. The suite has no infinite `atan2` rows today. The
repro's 16 infinite rows are the candidates to add, alongside the companion's. `dist/ganita.cyr` has
to be regenerated with the change. Consumers get the fix only when the stdlib re-vendors ganita:
cyrius 6.6.11 and 6.6.12 both ship `lib/ganita.cyr` 1.2.9.

## Consumer-side workaround

abaco has none for these rows. In abaco 2.4.9, `src/eval.cyr`, function `call_function`, the
two-argument block (lines 1665-1752) handles `atan2` in two steps:

- Lines 1670-1675 (added in 2.4.9) return the NaN argument when either argument of `atan2` is NaN.
- Line 1683 then returns `f64_atan2(a, b)`. That is the `_compat.cyr` alias for
  `ganita_f64_atan2`.

So the four (±∞, ±∞) rows reach abaco users unchanged, as NaN with no error. abaco tracks them in
`docs/development/roadmap.md` under "Upstream (ganita)" and in
`docs/audit/2026-09-30-audit.md`, where the finding is deferred as "ganita upstream". Until the fix
lands, a consumer that needs these rows can test both arguments for infinity before calling `atan2`.
That is the bit test `(v & 0x7FFFFFFFFFFFFFFF) == 0x7FF0000000000000` that ganita's private
`_f64_is_inf` does.
