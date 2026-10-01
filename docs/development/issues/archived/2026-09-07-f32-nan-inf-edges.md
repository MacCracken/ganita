# f32 tier: NaN and infinity edges, and the missing comparators

> ✅ **RESOLVED in ganita 1.2.4** (2026-09-08). All five items closed.
>
> 1. **min/max are IEEE-754 minNum/maxNum**: a NaN operand is ignored, and NaN
>    comes back only when both are. The filing left this as a decision between
>    three options; the choice made was (b) — an explicit NaN test — because the
>    previous behaviour was not a defensible trade but an accident: whether a NaN
>    won or lost depended on its SIGN BIT.
> 2. **clamp propagates a NaN x** rather than ignoring it, deliberately unlike
>    min/max: clamp transforms ONE value and a NaN has no clamped form, whereas
>    min/max choose between two and skipping an absent one is meaningful.
>    Composing min and max would have quietly returned `hi`.
> 3. **`exp`/`exp2` handle infinities** — `+inf` and `0` respectively.
> 4. **`sign(NaN)` returns NaN**; **`cbrt(±inf)` returns ±inf**.
> 5. **The comparators exist**: `ganita_f32_lt` / `_le` / `_gt` / `_ge`, all
>    false on a NaN operand. They normalise the ZEROS, which `_f32_key` alone
>    does not — the key is a total order that ranks -0.0 below +0.0, correct for
>    sorting and wrong for comparison, where IEEE says the zeros are equal.
>    That distinction is why these are four functions rather than an exported
>    `_f32_key`, and it was caught by a failing assertion, not by inspection.
>
> ⚠ **Addendum (ganita 1.2.11):** §2's "`pow` and `atan2` inherit it by forwarding
> through the same path" was half wrong. `atan2` calls no `exp`. Its f32 NaN for
> `(±inf, ±inf)` came from `ganita_f64_atan2` forming `inf / inf`, a defect of its
> own, which item 3 here could not reach. 1.2.11 closed it
> ([`2026-09-30-f64-atan2-infinite-arguments`](2026-09-30-f64-atan2-infinite-arguments.md)).
> `ganita_f32_atan2` now gives `0x3F490FDB` / `0xBF490FDB` / `0x4016CBE4` / `0xC016CBE4`,
> and the signed-zero rows are right too: `atan2(-0, -1) = 0xC0490FDB`.


**Filed by**: ganita's 1.2.3 P(-1) sweep (math-f32 lens)
**Against**: `src/math_f32.cyr`
**Date**: 2026-09-07
**Version**: ganita 1.2.3
**Severity**: **Medium** / **Low**. All reproduced with raw bit patterns printed.

`ganita_f32_sin` / `_cos` returning their argument for `|x| >= 2^63` was serious
enough to fix in 1.2.3. These are the rest. The tier's core — the sign-magnitude
`_f32_key` transform, the native arithmetic, the half-to-even rounding — was
checked and found **correct**; see the audit's "checked and found clean".

## 1. `min` / `max` / `clamp` impose a total order on NaN (MEDIUM)

`_f32_key` maps every pattern to a signed integer, NaNs included. So a NaN is kept
or silently dropped **purely by its sign bit**: a negative NaN sorts below every
finite value and wins `min`; a positive NaN sorts above and wins `max`. Neither is
IEEE-754's `minNum`/`maxNum`, which return the *non*-NaN operand.

The trade is real and should be decided explicitly rather than inherited: the
total order is what makes one signed compare correct across the whole finite
range, which is the property the tier exists for. Options are (a) document the
current behaviour as intentional, (b) add an explicit NaN test, at a branch per
call in a function whose whole point is being branch-cheap, or (c) ship both
(`ganita_f32_min` and `ganita_f32_min_num`).

## 2. `exp` / `exp2` return NaN for infinite arguments (MEDIUM)

`exp(+inf)` should be `+inf` and `exp(-inf)` should be `0`. Both return NaN, and
`pow` and `atan2` inherit it by forwarding through the same path.

## 3. `sign(NaN)` returns ±1.0f (LOW)

It turns a NaN into a finite value — the one thing a NaN must not silently become,
because it ends the propagation that makes NaN useful as a signal.

## 4. `cbrt(±inf)` returns a negative quiet NaN (LOW)

Should be `±inf`. The sign split added at 1.1.2 handles zero and negatives
correctly; infinity was not considered.

## 5. The tier ships no comparators (LOW, and the most consequential)

`_f32_key` — the *only* correct way to compare two f32 patterns — is **private**.
The tier has no `lt`/`le`/`gt`/`ge`, so a consumer who needs to compare f32 values
falls back to the raw integer compare that the module header explicitly calls a
trap:

> IEEE-754 is SIGN-MAGNITUDE, not two's complement. Raw patterns order correctly
> only among NON-NEGATIVE values […] pixel data *is* non-negative, which is
> exactly why a naive min/max passes every plausible test and breaks the first
> time a consumer subtracts.

The module documents the trap at length and then leaves the only tool that avoids
it inaccessible. Exporting `ganita_f32_lt` / `_le` / `_gt` / `_ge` over `_f32_key`
is four one-line functions and closes it.

## Why none of this is fixed in 1.2.3

Items 1–4 are contract *decisions* about NaN and infinity semantics, not bugs with
one correct answer — the right move is to settle them as a group, against a stated
policy (follow C? follow IEEE-754 `minNum`? propagate?), and pin the whole domain
in one test group. Item 5 is new public API, which a hardening patch should not
add unilaterally. `sin`/`cos` were fixed because returning `2^70` from a function
bounded to `[-1, 1]` is not a semantic question.
