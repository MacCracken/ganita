# `ganita_f64_sinh`, `tanh`, `atanh` and `asinh` still cancel just above their small-|x| cutoffs; `acosh` near 1 and `asin` near ±1 cancel the same way

**Status:** 🟡 **OPEN** — found by abaco 2.4.9's project audit; not repaired.
**Placement:** unpinned.
**Discovered:** 2026-09-30, abaco 2.4.9 project audit (finding `eval-functions-hyperbolic-cancellation`,
and the aarch64 gap probe `gap-aarch64-cross-target-hyperbolic-cancellation`; both deferred to ganita.
abaco's `sinh` / `tanh` / `asinh` / `acosh` / `atanh` / `asin` builtins pass ganita's values through.)
**Severity:** Medium — six public functions silently lose up to ~8 significant digits on ordinary
arguments: |x| from 2⁻²⁶ to about 1/2, x − 1 below about 0.1, 1 − |x| between about 2⁻³⁴ and 2⁻⁹.
No crash, no error, and no workaround in the consumer.
**Affects:** ganita 1.2.4 – 1.2.10. Each function's body was diffed tag by tag, and the arithmetic of
all six is unchanged in that range (sinh's one change, at 1.2.7, is a comment). Measured on 1.2.10,
on x86_64 and on aarch64 under qemu. `asin` has had the same body since 1.0.0, and `asinh` since
1.2.3. The cyrius 6.6.12 stdlib's `lib/ganita.cyr` (ganita 1.2.9) has the same bodies, and that copy
is the one abaco runs.

## Summary

1.2.4 gave `sinh`, `tanh` and `atanh` a guard that returns `x` below `_F64_TINY` = 2⁻²⁶. `asinh`
has had a similar guard at 1e-8 since 1.2.3. Below the guard the answer is right. Above it, each
function still evaluates its cancelling form:

- `sinh`: (eˣ − e⁻ˣ)/2
- `tanh`: (eˣ − e⁻ˣ)/(eˣ + e⁻ˣ)
- `atanh`: ½·ln((1+x)/(1−x))
- `asinh`: ln(x + √(x²+1))

Each form first builds a number near 1. That number carries an absolute rounding error of about
2⁻⁵³, and a small answer cannot absorb it. The relative error is about 2⁻⁵³/|x| (ε/2|x|), which
is on the order of 1/|x| ulp: tens of millions of ulp at 2⁻²⁶. It halves with every binade and is
still above 2 ulp at |x| ≈ 0.4. `acosh` has the same shape in x − 1, through x·x − 1 and then
ln(x + small). `asin` near ±1 evaluates 1 − x·x, and its error peaks at 1,024 ulp at x = 1 − 2⁻²⁷.

One example: `ganita_f64_sinh(1e-6)` returns 9.999999999732445e-07. That is 127,136 ulp below the
correctly rounded 1.0000000000001666e-06, and it is smaller than its argument, although
sinh(x) > x for every x > 0.

The next table gives the worst point on a log-spaced grid, measured against a correctly rounded
reference (method below). "Points > 2 ulp" counts the grid points in the band that are more than
2 ulp off.

| function | band sampled | points | worst input | error, 1.2.10 | points > 2 ulp | with the proposed fix |
|---|---|---|---|---|---|---|
| `sinh` | 2⁻²⁶ ≤ \|x\| < 1 | 8,914 | 1.9706785678861335e-8 (`0x3E5528F5C28F5993`) | **4.09e7 ulp** | 7,755 | 1.43 ulp |
| `tanh` | 2⁻²⁶ ≤ \|x\| < 1 | 8,914 | 1.9706785678861335e-8 (`0x3E5528F5C28F5993`) | **2.42e7 ulp** | 7,548 | 2.05 ulp (2 points > 2) |
| `atanh` | 2⁻²⁶ ≤ \|x\| < 1 | 22,402 | 2.339482307433937e-8 (`0x3E591EB851EB8368`) | **2.99e7 ulp** | 8,960 | 1.31 ulp |
| `asinh` | 1e-8 ≤ \|x\| < 1 | 9,140 | 1.4783193667728686e-8 (`0x3E4FBF258BF2565D`) | **1.32e8 ulp** | 8,200 | 1.50 ulp |
| `acosh` | 1 < x < 2 | 5,474 | 1 + 2⁻⁵² (`0x3FF0000000000001`) | **2.52e7 ulp** | 4,839 | 2.03 ulp (1 point > 2) |
| `asin` | 1/2 ≤ \|x\| < 1 | 12,004 | 1 − 2⁻²⁷ (`0x3FEFFFFFFC000000`) | **1,024 ulp** | 4,880 | 1.03 ulp |

`asinh`'s worst point is below 2⁻²⁶. Its guard is at 1e-8, so [1e-8, 2⁻²⁶) is inside the band
for `asinh` alone. abaco's audit recorded "up to 3.7e7 ulp". This grid is denser, and its worst
point is the 1.32e8 ulp `asinh` row.

Worst error per binade of |x| on 1.2.10, in ulp:

| \|x\| in [2ᵏ, 2ᵏ⁺¹), k = | −26 | −20 | −13 | −7 | −4 | −3 | −2 | −1 |
|---|---|---|---|---|---|---|---|---|
| `sinh` | 4.1e7 | 5.7e5 | 4,900 | 75 | 8.8 | 4.2 | 2.5 | 1.9 |
| `tanh` | 2.4e7 | 3.4e5 | 2,900 | 45 | 5.7 | 2.9 | 2.0 | 2.1 |
| `atanh` | 3.0e7 | 5.0e5 | 3,800 | 63 | 7.5 | 3.5 | 1.2 | 0.94 |
| `asinh` | 7.9e7 | 1.2e6 | 8,200 | 141 | 15 | 7.9 | 3.7 | 2.0 |

`acosh` by x − 1 in [2ᵏ, 2ᵏ⁺¹): k = −52: 2.5e7, −40: 5.3e5, −26: 1.0e7, −13: 975, −7: 15, −4:
2.3, −3: 1.3. `asin` by 1 − |x| in [2ᵏ, 2ᵏ⁺¹): k = −53: 0.28, −40: 0.50, −34: 2.4, −30: 128, −27:
1,024, −20: 85, −13: 7.9, −9: 2.3, −8: 1.6.

**How this was measured.** Each band was sampled at 6,001 inputs equally spaced in bit pattern,
which makes them log-spaced at about 170 to 200 per binade. Odd functions were sampled at both
signs. `atanh` and `asin` got a second set of 6,001 at 1 − d, with d from 2⁻⁵³ to 1/2. `acosh` was
sampled at 1 + d, with d from 2⁻⁵² to 32. Each input was run through ganita on 1.2.10. The error is
|got − f(x)| / ulp(f(x)), where f(x) comes from mpmath at 256 bits. The same sweep run under
qemu-aarch64 gives the same maxima for all six functions. On the same grid, `cosh` stays within
1.61 ulp, and `acos` within 1.62 ulp (1.35 for 1/2 ≤ |x| < 1). `cosh` uses the same `f64_exp` and
`acos` the same `f64_atan`, so the error comes from the forms and not from the builtins.

**The source comments say otherwise.** Above the inverse-hyperbolic block,
`src/math_advanced.cyr:725-731` says those functions are "accurate enough for most consumers,
loses ~1-2 ulp at small |x| for asinh and near ±1 for atanh". Measured, `asinh` at small |x| is up
to 1.32e8 ulp off. `atanh` near ±1 is fine: at most 0.94 ulp for 1/2 ≤ |x| < 1, sampled down to
1 − |x| = 2⁻⁵³. `atanh`'s loss is at small |x|, and the comment does not mention it. `asinh`'s regime
comment at `:757` calls the direct form "accurate on the positive side", but that holds only from
about |x| = 1/2 up. The module's ACCURACY POLICY at `:7-11` lists CANCELLATION as "Closed with a
series expansion below a threshold".

## This is the unfinished part of an earlier filing

`archived/2026-09-07-f64-transcendental-accuracy.md` §1, "Cancellation for small |x| — sinh, tanh,
atanh", reported "44 % error at 1e-16, and exactly `0.0` below 1e-17", and proposed a series below a
threshold. 1.2.4 shipped that series (resolution item 3), which fixed everything below 2⁻²⁶. But
2⁻²⁶ is where `x` alone becomes the correctly rounded answer. It is not where the direct form
becomes accurate, and nothing above the threshold changed.

§3 of the same filing reported that `acosh` loses "~9" significant digits "near `x = 1`". The
resolution banner says "All four groups closed" and lists `acos`'s half-angle form (item 2) and
`acosh`'s overflow band (item 4). It lists nothing for `acosh` near 1, and that case is unchanged:
`acosh(1 + 2⁻⁵²)` is 2.5e7 ulp off, with 8.4 correct digits.

The 2026-09-07 filing did not cover `asin` near ±1. In 1.2.4, `acos` stopped using π/2 − asin(x)
and switched to a half-angle form, because 1 − x is exact near 1. `asin` still uses 1 − x·x.

The problem is older than the 2026-09-07 filing. The inverse hyperbolics came into the stdlib at
cyrius 4.8.5-alpha6 from abaco's recommendation P2-1, recorded in cyrius's
`docs/development/issues/archived/stdlib-math-recommendations-from-abaco.md`. That recommendation
already said the formulas "lose precision for small `x` (in `asinh`) and near `x = 1` (in `atanh` /
`acosh`)", and it asked for "a precision guard at small-argument branches". The "~1-2 ulp at small
|x| for asinh and near ±1 for atanh" wording that ganita still carries comes from the 4.8.5-alpha6
CHANGELOG entry. Both sources have the same mix-up: `atanh` is accurate near ±1 and loses at small
|x|. The cyrius queue has no other filing on the accuracy of these functions, open or archived.
(`archived/2026-07-08-aarch64-ganita-inverse-trig-unguard.md`, on `asin` being compiled out on
aarch64, and `archived/2026-09-08-f64-exp-nan-for-infinite-argument.md`, on `sinh(±inf)`, are about
other defects.)

This filing does not overlap with the other open ganita filing,
`2026-09-30-f64-atan2-signed-zero-and-nan.md`, which covers a different function and a different
defect. `archived/2026-09-07-performance-backlog.md` gave `sinh` and `cosh` their one-exp form; the
proposed fix keeps that form for `sinh` at |x| ≥ 22 and leaves `cosh` alone.

## Reproduction

`repros/2026-09-30-f64-hyperbolic-and-asin-cancellation-band.cyr` checks 16 rows in the band and 3
controls, using bit patterns for both the inputs and the wanted results. The wanted result is the
correctly rounded value (mpmath at 300 bits, rounded once to 53). A row is wrong if the result is
more than 2 ulp from it, measured as the difference of the bit patterns, or if the result is NaN or
has the wrong sign. The exit code is the number of wrong rows.

```
cyrius build docs/development/issues/repros/2026-09-30-f64-hyperbolic-and-asin-cancellation-band.cyr /tmp/hypcanc
/tmp/hypcanc; echo "exit=$?"      # -> 16 on 1.2.10
```

Output on 1.2.10 (x86_64):

```
sinh / tanh / atanh / asinh just above the 2^-26 cutoff, and on toward |x| = 1
  WRONG sinh(1.9706785678861335e-8)    got 0x3e5528f5c5000000  want 0x3e5528f5c28f5993  off 40937069 ulp
  WRONG sinh(1e-6)                     got 0x3eb0c6f7a0b40000  want 0x3eb0c6f7a0b5f0a0  off 127136 ulp
  WRONG sinh(-0.01)                    got 0xbf847af7a654e9c0  want 0xbf847af7a654e9ef  off 47 ulp
  WRONG tanh(1.9706785678861335e-8)    got 0x3e5528f5c3ffffff  want 0x3e5528f5c28f5992  off 24159853 ulp
  WRONG tanh(1e-7)                     got 0x3e7ad7f29a7fffdb  want 0x3e7ad7f29abcaf2f  off 3977044 ulp
  WRONG tanh(-2^-12)                   got 0xbf2ffffff5555005  want 0xbf2ffffff555555a  off 1365 ulp
  WRONG atanh(2.339482307433937e-8)    got 0x3e591eb85023f140  want 0x3e591eb851eb8369  off 29856297 ulp
  WRONG atanh(-2^-20)                  got 0xbeafffffffffeaab  want 0xbeb0000000000555  off 6826 ulp
  WRONG atanh(0.001)                   got 0x3f50624e2e91ecaf  want 0x3f50624e2e91ed17  off 104 ulp
  WRONG asinh(1.4783193667728686e-8)   got 0x3e4fbf2584102631  want 0x3e4fbf258bf2565d  off 132263980 ulp
  WRONG asinh(1e-7)                    got 0x3e7ad7f29a7b646d  want 0x3e7ad7f29abcaf3b  off 4278990 ulp
  WRONG asinh(-0.05)                   got 0xbfa996df55a826c7  want 0xbfa996df55a826bb  off 12 ulp
acosh near x = 1
  WRONG acosh(1 + 2^-52)               got 0x3e56a09e67ffffff  want 0x3e56a09e667f3bcc  off 25216051 ulp
  WRONG acosh(1 + 2^-40)               got 0x3eb6a09e667ff875  want 0x3eb6a09e667f39ea  off 48779 ulp
asin near |x| = 1
  WRONG asin(1 - 2^-27)                got 0x3ff9217b544427c3  want 0x3ff9217b54442bc3  off 1024 ulp
  WRONG asin(-(1 - 2^-27))             got 0xbff9217b544427c3  want 0xbff9217b54442bc3  off 1024 ulp
controls -- right today, must stay right
  ok    sinh(2^-27)    (below cutoff)  got 0x3e40000000000000  want 0x3e40000000000000  off 0 ulp
  ok    asin(0.5)                      got 0x3fe0c152382d7366  want 0x3fe0c152382d7366  off 0 ulp
  ok    acosh(2.5)                     got 0x3ff9119c13a31baf  want 0x3ff9119c13a31bb0  off 1 ulp
rows wrong: 16
```

`cyrius build --aarch64` under qemu-aarch64 also exits 16, and the 16 band rows have the same bits.
The only difference is the `acosh(2.5)` control, which lands 0 ulp off instead of 1. That is the
x87 `ln` against the polyfill, and both are within the stdlib's 1-ulp contract.

## What a consumer sees

These are abaco 2.4.9 results (cyrius 6.6.12, vendored ganita 1.2.9), from a scratch copy of the
tree evaluating each expression with `Evaluator_eval`:

| expression | abaco 2.4.9 | correctly rounded | off by |
|---|---|---|---|
| `sinh(1e-6)` | `0x3EB0C6F7A0B40000` (9.999999999732445e-07) | `0x3EB0C6F7A0B5F0A0` | 127,136 ulp |
| `tanh(1e-7)` | `0x3E7AD7F29A7FFFDB` | `0x3E7AD7F29ABCAF2F` | 3,977,044 ulp |
| `atanh(0.001)` | `0x3F50624E2E91ECAF` | `0x3F50624E2E91ED17` | 104 ulp |
| `asinh(-0.05)` | `0xBFA996DF55A826C7` | `0xBFA996DF55A826BB` | 12 ulp |
| `acosh(1.001)` | `0x3FA6E53ACBCDEB1E` | `0x3FA6E53ACBCDEBA3` | 133 ulp |
| `asin(0.99999999)` | `0x3FF9216709C28BE0` | `0x3FF9216709C28B31` | 175 ulp |

The first four are bit-identical to the repro's rows on ganita 1.2.10. abaco's own assertions on
these functions (`abaco/tests/test_eval.tcyr:1198-1225`) use arguments where the error is at most
a few ulp today (|x| ≥ 0.389 for the odd functions, x ≥ 1.88 for `acosh`) and an absolute
tolerance of 1e-9, so they pass.

## Root cause

All line numbers are in `src/math_advanced.cyr` at 1.2.10:

- **`sinh`, `:74-81`** computes `ex = f64_exp(x)` and `enx = 1/ex`, then returns
  `(ex − enx)/2`. When |x| ≪ 1, both terms are ≈ 1.
- **`tanh`, `:118-122`** has the same numerator, `f64_sub(ex, enx)`.
- **`atanh`, `:800-802`** rounds `(1 + x)/(1 − x)` to a double near 1 before `f64_ln` sees it.
- **`asinh`, `:767`** rounds `a + √(a² + 1)` to a double near 1 before `f64_ln` sees it.
- **`acosh`, `:785-786`**: `x·x − 1` cancels, and then `x + √(…)` is again a double near 1
  before `f64_ln` sees it.
- **`asin`, `:665`** computes `1 − x·x`. With d = 1 − |x|, the exact x·x is 1 − 2d + d², and
  1 − 2d is representable, so rounding `x·x` loses part of d², up to 2⁻⁵⁴. That rounding error is
  all that is left of a small difference. It peaks near d = 2⁻²⁷, where d² reaches 2⁻⁵⁴. Closer
  to 1, d² is smaller and `x·x` is nearly exact.

The guards at `:57`, `:115`, `:798` and `:761` return `x` below the cutoff and fall through to
these forms above it.

For the five hyperbolic functions the absolute error is about one rounding of a number near 1, so
the relative error is about 2⁻⁵³/|f(x)|. `f64_exp`, `f64_ln` and `f64_atan` are within 1 ulp
(stdlib contract, cyrius 6.6.8 and 6.6.9), which the `cosh` and `acos` controls above confirm. The
fix needs `expm1` and `log1p`, and neither exists: there is no `expm1` or `log1p` in the vendored
`lib/math.cyr` or in ganita's `src/`. The only match is a comment.

## Proposed fix

This has been tested; it is not a sketch. The fix adds two private kernels and routes the band
through them, using fdlibm's own forms for each function:

- `_gn_expm1(x)` is a port of fdlibm 5.3 `s_expm1.c` (FreeBSD msun). It reduces x = k·ln2 + r
  with a two-word ln2, applies the Q1..Q5 rational, and restores 2ᵏ.
- `_gn_log1p(x)` is a port of `s_log1p.c`. It writes 1 + x = 2ᵏ·(1 + f), with a correction term
  for the rounding of 1 + x, then applies the Lp1..Lp7 kernel. These are the same constants as
  the stdlib's `_f64_log_R` (Lg1..Lg7).

| function | range rerouted | new form | source |
|---|---|---|---|
| `sinh` | \|x\| < 22 | E = expm1(\|x\|); ½(2E − E²/(E+1)) below 1, ½(E + E/(E+1)) from 1 | fdlibm `e_sinh.c` |
| `tanh` | 2⁻²⁶ ≤ \|x\| ≤ 20 | E = expm1(−2\|x\|), −E/(E+2) below 1; E = expm1(2\|x\|), 1 − 2/(E+2) from 1 | fdlibm `s_tanh.c` |
| `atanh` | 2⁻²⁶ ≤ \|x\| ≤ 1 | ½·log1p(2\|x\| + 2\|x\|·\|x\|/(1−\|x\|)) below ½; ½·log1p(2\|x\|/(1−\|x\|)) from ½ | fdlibm `e_atanh.c` |
| `asinh` | 1e-8 ≤ \|x\| < 2 | log1p(\|x\| + x²/(1 + √(1+x²))) | fdlibm `s_asinh.c` |
| `acosh` | 1 ≤ x < 2 | log1p(t + √(2t + t²)), t = x − 1 (exact) | fdlibm `e_acosh.c` |
| `asin` | \|x\| ≥ ½ | 1 − x² computed as (1 − \|x\|)(1 + \|x\|); 1 − \|x\| is exact there | ganita's `acos` reasoning, not fdlibm's `e_asin.c` |

Every other regime is left as it is: the guards, the saturation, the overflow branches, infinities,
NaN and the domain checks. `sinh`, `tanh` and `atanh` now compute on |x| and apply the sign at the
end, as `asinh` already does. The patch also corrects the three comments quoted above.

I applied it to a copy of 1.2.10 and got these results:

- **Repro.** The patched copy exits 0, on x86_64 and on qemu-aarch64. The pristine copy still exits
  16.
- **Grid.** See the last column of the first table. The maximum is 2.05 ulp, for `tanh` at
  x ≈ 0.2186, where 2 of 12,002 points are above 2 ulp. `acosh` reaches 2.03 ulp, with 1 of 6,001
  points above 2. Every other function stays within 1.57 ulp. aarch64 gives the same maxima,
  except `asin` (1.54 ulp below ½ against 1.57, and 1.04 from ½ up against 1.03; `f64_atan`
  differs by target).
  Nothing got worse outside the band (x86_64):

  | function | range | before → after (max ulp) |
  |---|---|---|
  | `sinh` | 1 ≤ \|x\| ≤ 32 | 1.56 → 1.30 |
  | `tanh` | 1 ≤ \|x\| ≤ 32 | 2.41 → 0.90 (the old quotient had 8 points above 2 ulp there) |
  | `asinh` | 1 ≤ \|x\| ≤ 32 | 1.26 → 1.03 |
  | `acosh` | 2 ≤ x ≤ 33 | 1.01 (unchanged) |
  | `asin` | \|x\| < ½ | 1.57 (unchanged) |

  On aarch64, where `f64_ln` is the polyfill, the `asinh` row reads 1.33 → 1.00, the `acosh` row
  1.16 (unchanged) and the `asin` row 1.54 (unchanged); the other rows are the same.

  The ~2 ulp worst cases above are measured on this grid. fdlibm documents a bound under 1 ulp
  only for the two kernels, so this filing claims no proven bound for the six functions.
- **Kernels.** `_gn_expm1` is within 0.73 ulp on 40,002 points over ±[2⁻⁶⁰, 704]. `_gn_log1p` is
  within 0.74 ulp on 70,004 points over [2⁻⁶⁰, 2⁶⁰] and [−1 + 2⁻⁵³, −2⁻⁶⁰].
- **Suite.** With the patched source and the unchanged suite, `cyrius test` reports 597 passed and
  0 failed. Adding a test group for this filing brings it to 607 passed and 0 failed on x86_64, and
  `cyrius test --aarch64` (under qemu) gives the same. The group asserts that the 16 band rows and
  11 kernel rows are within 2 ulp (all are within 1), and checks special values: `expm1(±inf)`,
  `expm1(−0)`, `log1p(−1)`, `log1p(−2)`, `log1p(−0)` and `atanh(±1)`.
- **Gates.** `cyrius fmt --check`, `cyrius lint` (0 warnings), `cyrius vet`, the build and
  `cyrius fuzz` all pass, and `cyrius coverage --min 100` reports 139/139.
  `scripts/coverage-honest.sh 88` needs the test group. That script counts private functions, so
  without the group the two new kernels make it read 144/164 = 87%, which fails. With the group it
  reads 146/164 = 89%. I did not regenerate `dist/`, which needs `cyrius distlib --all`.
- **Cost.** There are no bench rows for these functions. A loop of one million calls over
  [2⁻²⁰, ½) (DCE build, x86_64) went from 41 to 59 ns for `sinh`, 40 to 54 for `tanh`, 38 to 55 for
  `atanh` and 39 to 58 for `asinh`. `acosh(1 + x)` went from 62 to 80 ns and `asin` from 71 to 74.
  The kernels are plain f64 arithmetic, while the forms they replace call the x87-native `f64_exp`
  and `f64_ln`.

The source patch and the test group follow.

<details><summary>The patch to <code>src/math_advanced.cyr</code> (as tested against 1.2.10)</summary>

```diff
--- a/src/math_advanced.cyr
+++ b/src/math_advanced.cyr
@@ -8,7 +8,9 @@
 #     significant digit near the point where they meet. sinh, tanh, atanh and
 #     asinh all did, returning exactly 0.0 for arguments where the answer is
 #     approximately the argument. Closed with a series expansion below a
-#     threshold where the next term is under half a ulp.
+#     threshold where the next term is under half a ulp — and, above it, with
+#     expm1 / log1p forms (fdlibm), since the direct forms still lose about
+#     eps/|x| relative there (millions of ulp just above 2^-26).
 #   OVERFLOW — squaring or exponentiating before the final scaling reaches +inf
 #     for inputs whose ANSWER is perfectly representable. hypot's entire reason
 #     for existing is not to do this, and it did. Closed by scaling out the
@@ -46,6 +48,179 @@
     return 1;
 }
 
+# expm1(x) = e^x - 1, without the cancellation of f64_exp(x) - 1 near 0.
+# Port of fdlibm 5.3 s_expm1.c (FreeBSD msun): reduce x = k·ln2 + r with a
+# two-word ln2 (c carries what hi - lo drops), then a Remez rational in r
+# (Q1..Q5), then put 2^k back. fdlibm states < 1 ulp. Used by sinh and tanh.
+fn _gn_expm1(x): i64 {
+    var hx = (x >> 32) & 0x7FFFFFFF;
+    var xsb = (x >> 63) & 1;
+    if (hx >= 0x4043687A) {                          # |x| >= 56·ln2
+        if (hx >= 0x40862E42) {                      # |x| >= 709.78
+            if (hx >= 0x7FF00000) {
+                if ((x & 0x000FFFFFFFFFFFFF) != 0) { return f64_add(x, x); }   # NaN
+                if (xsb == 0) { return x; }          # expm1(+inf) = +inf
+                return 0xBFF0000000000000;           # expm1(-inf) = -1
+            }
+            if (f64_gt(x, 0x40862E42FEFA39EF) == 1) { return 0x7FF0000000000000; }
+        }
+        if (xsb == 1) { return 0xBFF0000000000000; } # x < -56·ln2: -1 to the last bit
+    }
+    var k = 0;
+    var c = 0;
+    var hi = 0;
+    var lo = 0;
+    if (hx > 0x3FD62E42) {                           # |x| > ln2/2: reduce
+        if (hx < 0x3FF0A2B2) {                       # |x| < 1.5·ln2: k = ±1
+            if (xsb == 0) {
+                hi = f64_sub(x, 0x3FE62E42FEE00000);  # ln2_hi
+                lo = 0x3DEA39EF35793C76;             # ln2_lo
+                k = 1;
+            } else {
+                hi = f64_add(x, 0x3FE62E42FEE00000);
+                lo = 0xBDEA39EF35793C76;
+                k = 0 - 1;
+            }
+        } else {
+            var hf = F64_HALF;
+            if (xsb == 1) { hf = F64_HALF | 0x8000000000000000; }
+            k = f64_to(f64_add(f64_mul(0x3FF71547652B82FE, x), hf));   # invln2; truncates
+            var tk = f64_from(k);
+            hi = f64_sub(x, f64_mul(tk, 0x3FE62E42FEE00000));   # exact
+            lo = f64_mul(tk, 0x3DEA39EF35793C76);
+        }
+        x = f64_sub(hi, lo);
+        c = f64_sub(f64_sub(hi, x), lo);
+    } else {
+        if (hx < 0x3C900000) { return x; }           # |x| < 2^-54
+    }
+    var hfx = f64_mul(F64_HALF, x);
+    var hxs = f64_mul(x, hfx);
+    var r1 = f64_mul(hxs, 0xBE8AFDB76E09C32D);                   # Q5
+    r1 = f64_mul(hxs, f64_add(0x3ED0CFCA86E65239, r1));          # Q4
+    r1 = f64_mul(hxs, f64_add(0xBF14CE199EAADBB7, r1));          # Q3
+    r1 = f64_mul(hxs, f64_add(0x3F5A01A019FE5585, r1));          # Q2
+    r1 = f64_add(F64_ONE, f64_mul(hxs, f64_add(0xBFA11111111110F4, r1)));   # Q1
+    var t = f64_sub(0x4008000000000000, f64_mul(r1, hfx));       # 3 - r1·x/2
+    var e = f64_mul(hxs, f64_div(f64_sub(r1, t), f64_sub(0x4018000000000000, f64_mul(x, t))));
+    if (k == 0) { return f64_sub(x, f64_sub(f64_mul(x, e), hxs)); }
+    var twopk = (0x3FF + k) << 52;
+    e = f64_sub(f64_mul(x, f64_sub(e, c)), c);
+    e = f64_sub(e, hxs);
+    if (k == 0 - 1) { return f64_sub(f64_mul(F64_HALF, f64_sub(x, e)), F64_HALF); }
+    if (k == 1) {
+        if (f64_lt(x, 0xBFD0000000000000) == 1) {    # x < -0.25
+            return f64_mul(0xC000000000000000, f64_sub(e, f64_add(x, F64_HALF)));
+        }
+        return f64_add(F64_ONE, f64_mul(F64_TWO, f64_sub(x, e)));
+    }
+    var y = 0;
+    if (k <= 0 - 2 || k > 56) {                      # exp(x) - 1 is exp(x) here
+        y = f64_sub(F64_ONE, f64_sub(e, x));
+        if (k == 1024) {
+            y = f64_mul(f64_mul(y, F64_TWO), 0x7FE0000000000000);   # 2^1023
+        } else {
+            y = f64_mul(y, twopk);
+        }
+        return f64_sub(y, F64_ONE);
+    }
+    if (k < 20) {
+        t = (0x3FF00000 - (0x200000 >> k)) << 32;    # 1 - 2^-k
+        y = f64_sub(t, f64_sub(e, x));
+        return f64_mul(y, twopk);
+    }
+    t = (0x3FF - k) << 52;                           # 2^-k
+    y = f64_sub(x, f64_add(e, t));
+    y = f64_add(y, F64_ONE);
+    return f64_mul(y, twopk);
+}
+
+# log1p(x) = ln(1 + x), without the rounding of 1 + x that f64_ln(1 + x) cannot
+# see. Port of fdlibm 5.3 s_log1p.c (FreeBSD msun): 1 + x = 2^k·(1 + f) with a
+# correction term c for the rounding of 1 + x, then the e_log.c kernel
+# (Lp1..Lp7 — the same constants as stdlib's ln). fdlibm states < 1 ulp. Used by
+# atanh, asinh and acosh.
+fn _gn_log1p(x): i64 {
+    var hx = (x >> 32) & 0xFFFFFFFF;
+    if (hx >= 0x80000000) { hx = hx - 0x100000000; }   # the SIGNED high word
+    var ax = hx & 0x7FFFFFFF;
+    var k = 1;
+    var f = 0;
+    var c = 0;
+    var hu = 0;
+    var u = 0;
+    if (hx < 0x3FDA827A) {                           # 1 + x < sqrt(2), or x < 0
+        if (ax >= 0x3FF00000) {                      # x <= -1
+            if (x == 0xBFF0000000000000) { return 0xFFF0000000000000; }   # -inf
+            return 0x7FF8000000000000;               # NaN
+        }
+        if (ax < 0x3E200000) {                       # |x| < 2^-29
+            if (ax < 0x3C900000) { return x; }       # |x| < 2^-54
+            return f64_sub(x, f64_mul(f64_mul(x, x), F64_HALF));
+        }
+        if (hx > 0 || hx <= 0xBFD2BEC4 - 0x100000000) {   # sqrt(2)/2 <= 1 + x < sqrt(2)
+            k = 0;
+            f = x;
+            hu = 1;
+        }
+    }
+    if (hx >= 0x7FF00000) { return f64_add(x, x); } # +inf or NaN
+    if (k != 0) {
+        if (hx < 0x43400000) {
+            u = f64_add(F64_ONE, x);
+            hu = (u >> 32) & 0xFFFFFFFF;
+            k = (hu >> 20) - 1023;
+            if (k > 0) {
+                c = f64_sub(F64_ONE, f64_sub(u, x));
+            } else {
+                c = f64_sub(x, f64_sub(u, F64_ONE));
+            }
+            c = f64_div(c, u);
+        } else {
+            u = x;
+            hu = (u >> 32) & 0xFFFFFFFF;
+            k = (hu >> 20) - 1023;
+            c = 0;
+        }
+        hu = hu & 0x000FFFFF;
+        if (hu < 0x6A09E) {                          # u < sqrt(2): normalise u
+            u = (u & 0xFFFFFFFF) | ((hu | 0x3FF00000) << 32);
+        } else {                                     # else normalise u/2
+            k = k + 1;
+            u = (u & 0xFFFFFFFF) | ((hu | 0x3FE00000) << 32);
+            hu = (0x00100000 - hu) >> 2;
+        }
+        f = f64_sub(u, F64_ONE);
+    }
+    var hfsq = f64_mul(f64_mul(F64_HALF, f), f);
+    var dk = f64_from(k);
+    var R = 0;
+    if (hu == 0) {                                   # |f| < 2^-20
+        if ((f & 0x7FFFFFFFFFFFFFFF) == 0) {
+            if (k == 0) { return 0; }
+            c = f64_add(c, f64_mul(dk, 0x3DEA39EF35793C76));
+            return f64_add(f64_mul(dk, 0x3FE62E42FEE00000), c);
+        }
+        R = f64_mul(hfsq, f64_sub(F64_ONE, f64_mul(0x3FE5555555555555, f)));
+        if (k == 0) { return f64_sub(f, R); }
+        return f64_sub(f64_mul(dk, 0x3FE62E42FEE00000),
+          f64_sub(f64_sub(R, f64_add(f64_mul(dk, 0x3DEA39EF35793C76), c)), f));
+    }
+    var s = f64_div(f, f64_add(F64_TWO, f));
+    var z = f64_mul(s, s);
+    R = f64_mul(z, 0x3FC2F112DF3E5244);                           # Lp7
+    R = f64_mul(z, f64_add(0x3FC39A09D078C69F, R));               # Lp6
+    R = f64_mul(z, f64_add(0x3FC7466496CB03DE, R));               # Lp5
+    R = f64_mul(z, f64_add(0x3FCC71C51D8E78AF, R));               # Lp4
+    R = f64_mul(z, f64_add(0x3FD2492494229359, R));               # Lp3
+    R = f64_mul(z, f64_add(0x3FD999999997FA04, R));               # Lp2
+    R = f64_mul(z, f64_add(0x3FE5555555555593, R));               # Lp1
+    if (k == 0) { return f64_sub(f, f64_sub(hfsq, f64_mul(s, f64_add(hfsq, R)))); }
+    return f64_sub(f64_mul(dk, 0x3FE62E42FEE00000),
+      f64_sub(f64_sub(hfsq, f64_add(f64_mul(s, f64_add(hfsq, R)),
+            f64_add(f64_mul(dk, 0x3DEA39EF35793C76), c))), f));
+}
+
 # sinh(x) = (exp(x) - exp(-x)) / 2, with the small, large and infinite regimes
 # handled separately. sinh(±inf) = ±inf; sinh(NaN) = NaN.
 fn ganita_f64_sinh(x): i64 {
@@ -65,6 +240,23 @@
         if ((x >> 63) & 1 == 1) { return f64_neg(h); }
         return h;
     }
+    # CANCELLATION, |x| < 22: (e^x - e^-x)/2 differences two numbers near 1 and
+    # loses about eps/|x| relative — millions of ulp just above 2^-26. fdlibm
+    # e_sinh.c: with E = expm1(|x|), sinh|x| = (2E - E²/(E+1))/2 below 1 and
+    # (E + E/(E+1))/2 above; nothing cancels. At 22 and up e^-|x| is under half
+    # an ulp of e^|x|, so the form below is exact enough.
+    if (f64_lt(a, 0x4036000000000000) == 1) {
+        var t = _gn_expm1(a);
+        var hs = 0;
+        if (f64_lt(a, F64_ONE) == 1) {
+            hs = f64_sub(f64_mul(F64_TWO, t), f64_div(f64_mul(t, t), f64_add(t, F64_ONE)));
+        } else {
+            hs = f64_add(t, f64_div(t, f64_add(t, F64_ONE)));
+        }
+        hs = f64_mul(F64_HALF, hs);
+        if ((x >> 63) & 1 == 1) { return f64_neg(hs); }
+        return hs;
+    }
     # ⚡ ONE exp, not two: exp(-x) = 1/exp(x). Bounded at |x| <= 500 because
     # beyond it exp(x) is heading for the subnormal range at one end, where the
     # reciprocal loses precision or overflows, and the asymptotic branch above
@@ -115,11 +307,21 @@
     if (f64_lt(f64_abs(x), _F64_TINY) == 1) { return x; }
     if (f64_gt(x, f64_from(20)) == 1) { return f64_from(1); }
     if (f64_lt(x, f64_from(0 - 20)) == 1) { return f64_from(0 - 1); }
-    var ex = f64_exp(x);
-    var enx = f64_exp(f64_neg(x));
-    var s = f64_sub(ex, enx);
-    var c = f64_add(ex, enx);
-    return f64_div(s, c);
+    # CANCELLATION above 2^-26 too: (e^x - e^-x)/(e^x + e^-x) loses about eps/|x|
+    # in the numerator. fdlibm s_tanh.c: with E = expm1(-2|x|), tanh|x| =
+    # -E/(E+2) below 1; with E = expm1(2|x|), 1 - 2/(E+2) from 1 up.
+    var a = f64_abs(x);
+    var t = 0;
+    var z = 0;
+    if (f64_lt(a, F64_ONE) == 1) {
+        t = _gn_expm1(f64_mul(0xC000000000000000, a));   # -2|x|
+        z = f64_div(f64_neg(t), f64_add(t, F64_TWO));
+    } else {
+        t = _gn_expm1(f64_mul(F64_TWO, a));
+        z = f64_sub(F64_ONE, f64_div(F64_TWO, f64_add(t, F64_TWO)));
+    }
+    if ((x >> 63) & 1 == 1) { return f64_neg(z); }
+    return z;
 }
 
 # True when an f64 holds an exact integer value.
@@ -661,8 +863,19 @@
 #     by convention (matches C libm).
 
 # asin(x) = atan(x / √(1 − x²))
+#
+# CANCELLATION near ±1: 1 − x·x subtracts the rounded x·x from 1, so its
+# rounding error (up to 2^-54) is all that is left of a small difference —
+# about 1,000 ulp at 1 − 2^-27. From |x| = 1/2 up, (1 − |x|)·(1 + |x|) is used
+# instead: 1 − |x| is exact there (Sterbenz), the same reason acos is accurate.
 fn ganita_f64_asin(x): i64 {
-    var one_minus_xx = f64_sub(F64_ONE, f64_mul(x, x));
+    var a = f64_abs(x);
+    var one_minus_xx = 0;
+    if (f64_lt(a, F64_HALF) == 1) {
+        one_minus_xx = f64_sub(F64_ONE, f64_mul(x, x));
+    } else {
+        one_minus_xx = f64_mul(f64_sub(F64_ONE, a), f64_add(F64_ONE, a));
+    }
     var denom = f64_sqrt(one_minus_xx);
     return f64_atan(f64_div(x, denom));
 }
@@ -723,12 +936,11 @@
 # Inverse hyperbolic
 # ================================================================
 # Closes the symmetry with `ganita_f64_sinh` / `cosh` / `tanh` that's been
-# in this file since day one. Identity-based implementations —
-# accurate enough for most consumers, loses ~1-2 ulp at small |x|
-# for asinh and near ±1 for atanh (classic catastrophic
-# cancellation from `1 − x²` and `ln(1 + small)`). Downstream
-# crates that need sub-ulp accuracy should roll their own
-# range-reduced series; most consumers (abaco, dhvani) don't.
+# in this file since day one. Identity-based, with the `ln(1 + small)` and
+# `x² − 1` cancellations routed through `_gn_log1p` (fdlibm) where they
+# occur: asinh below 2, acosh below 2, atanh everywhere. Through 1.2.10 the
+# direct forms were used there, and lost up to ~1e8 ulp just above the
+# small-|x| cutoff (and ~2.5e7 ulp for acosh at 1 + 2^-52) — not "~1-2 ulp".
 #
 # Domains:
 #   asinh: all real x.
@@ -750,10 +962,12 @@
-# Three regimes, and the outer two exist because the middle one breaks:
+# Four regimes; the first three exist because the direct form breaks there:
 #   |x| < 1e-8      -> x. The series is x - x^3/6 + ..., and x^3/6 is below half
 #                      a ulp of x there, so x IS the correctly-rounded answer.
 #                      The general form computes ln(1 + tiny) as ln(1.0) = 0
 #                      EXACTLY, so it returned 0.0 for every |x| <= 1e-17.
 #   |x| > 2^26      -> ln(|x|) + ln 2, since sqrt(x^2+1) -> |x| to well within
 #                      an ulp there and x*x would otherwise overflow.
+#   |x| < 2         -> log1p(|x| + x²/(1 + √(1 + x²))) (fdlibm s_asinh.c): the
+#                      direct form rounds 1 + small before ln sees it.
 #   otherwise       -> the direct form, which is accurate on the positive side.
 fn ganita_f64_asinh(x): i64 {
     var a = f64_abs(x);
@@ -764,7 +978,14 @@
         if (f64_gt(a, f64_from(67108864)) == 1) {
             r = f64_add(f64_ln(a), f64_ln(f64_from(2)));
         } else {
-            r = f64_ln(f64_add(a, f64_sqrt(f64_add(f64_mul(a, a), F64_ONE))));
+            if (f64_lt(a, F64_TWO) == 1) {
+                # CANCELLATION below 2: ln(1 + small) rounds the 1 + small first.
+                # fdlibm s_asinh.c: log1p(|x| + x²/(1 + √(1 + x²))).
+                var t = f64_mul(a, a);
+                r = _gn_log1p(f64_add(a, f64_div(t, f64_add(F64_ONE, f64_sqrt(f64_add(F64_ONE, t))))));
+            } else {
+                r = f64_ln(f64_add(a, f64_sqrt(f64_add(f64_mul(a, a), F64_ONE))));
+            }
         }
     }
     if ((x >> 63) & 1 == 1) { return f64_neg(r); }
@@ -782,6 +1003,13 @@
     if (f64_lt(x, F64_ONE) == 1) { return f64_div(f64_from(0), f64_from(0)); }
     if (_f64_is_inf(x) == 1) { return x; }
     if (f64_gt(x, _F64_SQ_BIG) == 1) { return f64_add(f64_ln(x), F64_LN2); }
+    if (f64_lt(x, F64_TWO) == 1) {
+        # CANCELLATION near 1: x·x − 1 differences two numbers near 1, and
+        # ln(x + small) rounds x + small first. fdlibm e_acosh.c: with t = x − 1
+        # (exact here), log1p(t + √(2t + t²)).
+        var t = f64_sub(x, F64_ONE);
+        return _gn_log1p(f64_add(t, f64_sqrt(f64_add(f64_mul(F64_TWO, t), f64_mul(t, t)))));
+    }
     var x2_minus_1 = f64_sub(f64_mul(x, x), F64_ONE);
     return f64_ln(f64_add(x, f64_sqrt(x2_minus_1)));
 }
@@ -797,9 +1025,20 @@
     var a = f64_abs(x);
     if (f64_lt(a, _F64_TINY) == 1) { return x; }
     if (f64_gt(a, F64_ONE) == 1) { return f64_div(f64_from(0), f64_from(0)); }
-    var num = f64_add(F64_ONE, x);
-    var den = f64_sub(F64_ONE, x);
-    return f64_mul(F64_HALF, f64_ln(f64_div(num, den)));
+    # CANCELLATION above 2^-26 too: (1 + x)/(1 − x) is 1 + small, rounded before
+    # ln sees it. fdlibm e_atanh.c, on |x|: ½·log1p(2|x| + 2|x|·|x|/(1 − |x|))
+    # below 1/2, ½·log1p(2|x|/(1 − |x|)) from 1/2 up. At |x| = 1 that is
+    # log1p(+inf) = +inf, as before.
+    var t = 0;
+    if (f64_lt(a, F64_HALF) == 1) {
+        var a2 = f64_add(a, a);
+        t = _gn_log1p(f64_add(a2, f64_div(f64_mul(a2, a), f64_sub(F64_ONE, a))));
+    } else {
+        t = _gn_log1p(f64_div(f64_add(a, a), f64_sub(F64_ONE, a)));
+    }
+    t = f64_mul(F64_HALF, t);
+    if ((x >> 63) & 1 == 1) { return f64_neg(t); }
+    return t;
 }
 
 # Hypotenuse: sqrt(x^2 + y^2). No overflow protection (use for normal ranges).
```

</details>

<details><summary>The test group (<code>tests/ganita.tcyr</code>; 10 assertions)</summary>

```diff
--- a/tests/ganita.tcyr
+++ b/tests/ganita.tcyr
@@ -1598,6 +1598,69 @@
 assert_eq(ganita_mat_eq(KT, ganita_mat_transpose(ganita_mat_mul(KA, KB)), 0), 1,
   "_ganita_mat_mul_into(transposed) == transpose(A * B), bit for bit, for a 3x4 * 4x2");
 
+test_group("f64 sinh/tanh/atanh/asinh/acosh/asin: no cancellation band above the cutoff");
+# Below 2^-26 these return x; just above it the direct forms differenced two numbers
+# near 1 and lost about eps/|x| relative (4e7 ulp for sinh, 1.3e8 for asinh). acosh
+# lost the same way near 1, asin ~1,000 ulp near +-1. Wanted bits are correctly
+# rounded (mpmath, 300 bits). Filed as
+# docs/development/issues/2026-09-30-f64-hyperbolic-and-asin-cancellation-band.md.
+var CB_BAD = 0;
+var CB_MAX = 0;
+fn t_cb1(fid, x, want): i64 {
+    var got = 0;
+    if (fid == 1) { got = ganita_f64_sinh(x); }
+    if (fid == 2) { got = ganita_f64_tanh(x); }
+    if (fid == 3) { got = ganita_f64_atanh(x); }
+    if (fid == 4) { got = ganita_f64_asinh(x); }
+    if (fid == 5) { got = ganita_f64_acosh(x); }
+    if (fid == 6) { got = ganita_f64_asin(x); }
+    if (fid == 7) { got = _gn_expm1(x); }
+    if (fid == 8) { got = _gn_log1p(x); }
+    var d = got - want;
+    if (d < 0) { d = 0 - d; }
+    if (d > CB_MAX) { CB_MAX = d; }
+    if (d > 2) { CB_BAD = CB_BAD + 1; }
+    return 0;
+}
+t_cb1(1, 0x3E5528F5C28F5993, 0x3E5528F5C28F5993);
+t_cb1(1, 0x3EB0C6F7A0B5ED8D, 0x3EB0C6F7A0B5F0A0);
+t_cb1(1, 0xBF847AE147AE147B, 0xBF847AF7A654E9EF);
+t_cb1(2, 0x3E5528F5C28F5993, 0x3E5528F5C28F5992);
+t_cb1(2, 0x3E7AD7F29ABCAF48, 0x3E7AD7F29ABCAF2F);
+t_cb1(2, 0xBF30000000000000, 0xBF2FFFFFF555555A);
+t_cb1(3, 0x3E591EB851EB8368, 0x3E591EB851EB8369);
+t_cb1(3, 0xBEB0000000000000, 0xBEB0000000000555);
+t_cb1(3, 0x3F50624DD2F1A9FC, 0x3F50624E2E91ED17);
+t_cb1(4, 0x3E4FBF258BF2565D, 0x3E4FBF258BF2565D);
+t_cb1(4, 0x3E7AD7F29ABCAF48, 0x3E7AD7F29ABCAF3B);
+t_cb1(4, 0xBFA999999999999A, 0xBFA996DF55A826BB);
+t_cb1(5, 0x3FF0000000000001, 0x3E56A09E667F3BCC);
+t_cb1(5, 0x3FF0000000001000, 0x3EB6A09E667F39EA);
+t_cb1(6, 0x3FEFFFFFFC000000, 0x3FF9217B54442BC3);
+t_cb1(6, 0xBFEFFFFFFC000000, 0xBFF9217B54442BC3);
+# The two fdlibm kernels the fix rests on.
+t_cb1(7, 0x3E10000000000000, 0x3E10000000200000);
+t_cb1(7, 0x3EE4F8B588E368F1, 0x3EE4F8BC681CDFB6);
+t_cb1(7, 0xBFE0000000000000, 0xBFD92E9A0720D3EC);
+t_cb1(7, 0x3FF0000000000000, 0x3FFB7E151628AED3);
+t_cb1(7, 0x403E000000000000, 0x42A370470AEC26ED);
+t_cb1(7, 0xC044000000000000, 0xBFF0000000000000);
+t_cb1(8, 0x3E10000000000000, 0x3E0FFFFFFFC00000);
+t_cb1(8, 0x3EE4F8B588E368F1, 0x3EE4F8AEA9AE7317);
+t_cb1(8, 0xBFE0000000000000, 0xBFE62E42FEFA39EF);
+t_cb1(8, 0x3FF0000000000000, 0x3FE62E42FEFA39EF);
+t_cb1(8, 0x4202A05F20000000, 0x4037069E2AA3184E);
+assert_eq(CB_BAD, 0, "27 band and kernel rows are within 2 ulp of the correctly rounded value");
+assert(CB_MAX <= 1, "the largest error over the 27 rows is at most 1 ulp");
+assert_eq(_gn_expm1(0xFFF0000000000000), 0xBFF0000000000000, "expm1(-inf) = -1");
+assert_eq(_gn_expm1(0x7FF0000000000000), 0x7FF0000000000000, "expm1(+inf) = +inf");
+assert_eq(_gn_expm1(0x8000000000000000), 0x8000000000000000, "expm1(-0) = -0");
+assert_eq(_gn_log1p(0xBFF0000000000000), 0xFFF0000000000000, "log1p(-1) = -inf");
+assert_eq(t_f64_is_nan(_gn_log1p(0xC000000000000000)), 1, "log1p(-2) is NaN");
+assert_eq(_gn_log1p(0x8000000000000000), 0x8000000000000000, "log1p(-0) = -0");
+assert_eq(ganita_f64_atanh(t_d(1)), 0x7FF0000000000000, "atanh(1) = +inf, as before");
+assert_eq(ganita_f64_atanh(t_d(0 - 1)), 0xFFF0000000000000, "atanh(-1) = -inf, as before");
+
 test_group("back-compat aliases");
 var a2 = mat_new(4, 5);
 assert_eq(mat_rows(a2), 4, "alias mat_rows");
```

</details>

## Consumer-side workaround

None. abaco passes ganita's values straight through. In `abaco/src/eval.cyr`, the one-argument
dispatch of `call_function` (lines 1577 and 1581–1586) returns `f64_asin(a)`, `f64_sinh(a)`,
`f64_tanh(a)`, `f64_asinh(a)`, `f64_acosh(a)` and `f64_atanh(a)` unchanged. These are `_compat`
aliases of the `ganita_f64_*` functions. abaco records the defect as an upstream item in
`abaco/docs/development/roadmap.md` ("Upstream (ganita)") and in `abaco/docs/audit/2026-09-30-audit.md`.
Until this is fixed in ganita, a consumer that needs these bands has to carry its own `expm1` and
`log1p`, the same two kernels the proposed fix adds to ganita.
