# `ganita_binomial` returns −1 for C(n, k) that fit in i64: every one above `i64_MAX / min(k, n−k)`

> ✅ **RESOLVED in ganita 1.2.11** (2026-10-01). `ganita_binomial` returns −1 **exactly**
> when C(n, k) > i64_MAX, as its contract always said. The proposed fix shipped as written.
>
> - **How.** While `C(n, i)·(n − i)` fits, it multiplies first, the same arithmetic as
>   1.2.10, so C(61, 30) costs what it did. Otherwise it divides through
>   g = gcd(C(n, i), i + 1) first (private `_gn_gcd`), so the only product it forms is
>   C(n, i + 1) itself, and it refuses only if that does not fit. The source comment
>   carries the four-step exactness argument. The CWE-834 bound still holds: for
>   k′ ≥ 34 it refuses by the 34th iteration.
> - **The repro exits 0** (was 9) on x86_64 and on aarch64 (qemu). It stays in
>   `repros/` as the regression witness.
> - **Checked against Python's exact `math.comb`** on 30,040 cases (every n ≤ 200 with
>   k from −2 to n + 2, plus 8,931 cases at each k's fit boundary and random large n).
>   0 mismatches on either architecture; 1.2.10 misses 3,848 of them, every one a
>   refusal. In a step-by-step model over 220,100 inputs, every intermediate is
>   ≤ i64_MAX, every gcd-branch division is exact, and no input takes more than 33
>   iterations.
> - **Suite.** The 1.2.3 row that pinned the refusal now asserts C(62, 30) exactly. A new
>   group (37 assertions) holds the 8 rows of the table below, the controls, mirrors,
>   the k = 2/3/4 boundaries, direct `_gn_gcd` rows, and an in-suite Pascal sweep of
>   every n ≤ 70 (0 of 2,556 cells wrong; 113 under the 1.2.10 body). Mutation-checked.
> - **Cost** (`tests/ganita.bcyr`): C(61, 30) ~128 ns, unchanged. C(66, 33) ~230 ns,
>   where 1.2.10 took 99 ns to refuse it.

**Status:** ✅ **RESOLVED in ganita 1.2.11** — found by abaco 2.4.8; abaco works around it from 2.4.9.
**Placement:** unpinned.
**Discovered:** 2026-09-30, abaco 2.4.8. Its evaluator began reporting ganita's −1 as a math
error, so `binomial(62, 31)` became an error even though the value fits. abaco 2.4.9 stopped
calling ganita's `binomial`.
**Severity:** Medium. A public function refuses valid input, against its own documented
contract, across a wide band of inputs. A consumer has a working replacement. It never returns a
wrong value.
**Affects:** ganita 1.2.3 – 1.2.10. Measured on 1.2.10 (HEAD `97e922b`). `git show` of each tag
from 1.2.3 to 1.2.10 gives a byte-identical `ganita_binomial`. Through 1.2.2 the same inputs
wrapped i64 silently instead; 1.2.3 fixed that. The stdlib bundle `lib/ganita.cyr` (1.2.9, as
abaco vendors it on cyrius 6.6.12) has the same body.

## Summary

The comment above `ganita_binomial` (`src/math_advanced.cyr:848-849`) says it is "exact in i64"
and returns −1 "when the true value does not fit in i64". It actually returns −1 whenever
k′·C(n, k) > i64_MAX, where k′ = min(k, n − k). So for each k the usable range is
i64_MAX / k′, not i64_MAX. Every value it does return is exact; the failure is a refusal.

| call | exact value (fits in i64) | ganita 1.2.10 |
|---|---|---|
| `binomial(62, 28)` | 349615716557887465 | **−1** |
| `binomial(62, 31)` | 465428353255261088 | **−1** |
| `binomial(66, 33)` | 7219428434016265740 | **−1** |
| `binomial(67, 29)` | 7886597962249166160 | **−1** |
| `binomial(3037000501, 2)` | 4611686020018625250 | **−1** |
| `binomial(2^32, 2)` | 9223372034707292160 = 2^63 − 2^31 | **−1** |
| `binomial(3810779, 3)` | 9223371416043870029 | **−1** |
| `binomial(121977, 4)` | 9223148185681446450 | **−1** |

C(62, 28) is the first refusal in (n, k) order and the smallest refused value with n ≤ 70.
C(62, 31) is the value the comment at `src/math_advanced.cyr:854` gives as one "which fits".
C(66, 33) is the largest central coefficient in i64. C(67, 29) = C(67, 38) is the largest
refused value with n ≤ 70.

**Exhaustive, n ≤ 70.** All 2556 pairs (0 ≤ k ≤ n ≤ 70) were compared with Python's exact
`math.comb`. 2500 of the values fit in i64. ganita returns the exact value for 2387, refuses 113
that fit, and correctly refuses the 56 that do not. **No value it returns is wrong.** The 113
fall in n = 62 … 70, with 7, 12, 15, 18, 19, 14, 10, 10 and 8 per n. The largest value ganita
returns for any n ≤ 70 is C(68, 22) = 400978991944396320, about 4.3 % of i64_MAX.

**Large n, small k.** Each row below was checked directly on ganita at four points: the last n
it answers, the first n it refuses, the last n that fits, and the first n that overflows.

| k | ganita answers through | refuses although it fits | first n that overflows | n wrongly refused |
|---|---|---|---|---|
| 2 | n = 3037000500 | n = 3037000501 … 4294967296 | 4294967297 | 1,257,966,796 |
| 3 | n = 2642246 | n = 2642247 … 3810779 | 3810780 | 1,168,533 |
| 4 | n = 86251 | n = 86252 … 121977 | 121978 | 35,726 |

The mirror `binomial(2^32, 2^32 − 2)` is refused the same way. The counts in the last column
come from the rule "refuses iff k′·C(n, k) > i64_MAX". That rule matched every one of the 2556
n ≤ 70 cells, and 2024 boundary and random cases (k′ from 1 to 40, n up to 2^63 − 1), with no
mismatch.

## Reproduction

`repros/2026-09-30-binomial-refuses-representable-values.cyr` checks the eight rows in the
first table and ten controls by exact integer value. A final row then checks every C(n, k) with
n ≤ 70 against Pascal's triangle, built by addition alone with −1 marking a sum above i64_MAX.
That oracle is independent of the function under test. The exit code is the number of wrong
rows.

```
cyrius build docs/development/issues/repros/2026-09-30-binomial-refuses-representable-values.cyr /tmp/binomr
/tmp/binomr; echo "exit=$?"      # -> 9 on 1.2.10: the 8 rows above + the n <= 70 sweep (113 cells)
```

The ten controls pass today: `binomial(52, 5)`, `(61, 30)`, `(3037000500, 2)` and
`(i64_MAX, 1)` are exact. `(67, 33)`, `(2^32 + 1, 2)`, `(3810780, 3)`, `(i64_MAX, 2)` and
`(2^62, 2^61)` are above i64_MAX and correctly −1. `(−3, 2)` is −1 for the negative argument.

## How this relates to earlier filings

There is no duplicate in this directory or in `archived/`. This filing is about the part of the
1.2.3 fix that went too far.

`docs/audit/2026-09-07-v1.2.3-audit.md` and CHANGELOG 1.2.3 record the wrap from n = 62. The
fix added "`result > INT64_MAX / factor` before each multiply". The audit then records the
result as behaviour: "`binomial(62,31)` refuses". That contradicts the function's own contract at
`src/math_advanced.cyr:848-849`, which says it returns −1 only when the true value does not fit.
`tests/ganita.tcyr:860-861` pins the refusal:
`assert_eq(ganita_binomial(62, 31), 0 - 1, "... the intermediate does not fit, so it refuses rather than wrapping")`.
That assertion has to change with the fix.

`archived/2026-09-07-f64-transcendental-accuracy.md` mentions `binomial` only as already fixed
in 1.2.3.

## What a consumer sees

According to abaco's CHANGELOG, its evaluator called ganita's `binomial` through 2.4.8. Up to
2.4.7 a −1 passed through as the answer. 2.4.8 turned it into `ABACO_ERR_MATH`, so
`binomial(62, 31)` was an error. The comment at `abaco/tests/test_eval.tcyr:1374-1375` records
this: "2.4.8 answered ABACO_ERR_MATH and 2.4.7 -1". A caller who reads −1 as "too large for i64"
gets the wrong answer for every value in that band.

## Root cause

`src/math_advanced.cyr:868-880`. The loop keeps `result` = C(n, i) and forms C(n, i + 1) as
C(n, i)·(n − i)/(i + 1). Line 874 checks, before the multiply at line 877, whether
C(n, i)·(n − i) fits:

```
        if (result > 0x7FFFFFFFFFFFFFFF / factor) { return 0 - 1; }
        ...
        result = result * factor / (i + 1);
```

The check is exact for what it tests: for positive integers, r > ⌊M/f⌋ ⟺ r·f > M. The problem
is the quantity it tests. C(n, i)·(n − i) = C(n, i + 1)·(i + 1), which is the next coefficient
times i + 1, and at the last step that is k′·C(n, k). After the fold k′ ≤ n/2 at line 867, this
intermediate equals n·C(n − 1, i) and never decreases with i. So the last step decides, and the
function refuses exactly when k′·C(n, k) > i64_MAX.

## Proposed fix

When the product fits, keep multiplying first. That path is exact and cheapest. When it does
not fit, divide first using a gcd, so that the only product formed is C(n, i + 1) itself. This
is the method abaco 2.4.9 shipped as `abaco_binomial` (see below). The recurrence and the
symmetry fold are from Knuth, *TAOCP* Vol. 1 (3rd ed.), §1.2.6.

```
fn _gn_gcd(a, b): i64 {
    while (b != 0) {
        var t = a % b;
        a = b;
        b = t;
    }
    return a;
}

fn ganita_binomial(n, k): i64 {
    if (n < 0 || k < 0) { return 0 - 1; }
    if (k > n) { return 0; }
    if (k > n - k) { k = n - k; }
    var result = 1;
    var i = 0;
    while (i < k) {
        # result is C(n, i). factor >= 1 because i < k <= n - k <= n.
        var factor = n - i;
        if (result <= 0x7FFFFFFFFFFFFFFF / factor) {
            # The product fits, and the running product of j consecutive
            # integers is divisible by j!, so this division has no remainder.
            result = result * factor / (i + 1);
        } else {
            var g = _gn_gcd(result, i + 1);
            var a = result / g;
            var f = factor / ((i + 1) / g);
            # a * f is C(n, i + 1) itself: refuse only when the result does not fit.
            if (a > 0x7FFFFFFFFFFFFFFF / f) { return 0 - 1; }
            result = a * f;
        }
        i = i + 1;
    }
    return result;
}
```

**Why both divisions in the second branch are exact.** Write c = C(n, i), m = i + 1 and
p = n − i.

1. From the factorial form, c·p = C(n, i + 1)·m.
2. g = gcd(c, m) divides both c and m, so a = c/g and d = m/g are integers. Dividing two
   numbers by their gcd leaves coprime quotients, so gcd(a, d) = 1.
3. Dividing (1) by g gives a·p = C(n, i + 1)·d. So d divides a·p. Since d shares no factor
   with a, d divides p (Euclid's lemma), and f = p/d is an integer, with f ≥ 1.
4. a·f = a·p/d = C(n, i + 1). The check `a > i64_MAX / f` is therefore true, and the step
   refuses, exactly when the next coefficient does not fit.

After the fold, C(n, i) never decreases in i, so no C(n, i) on the way exceeds C(n, k). The
multiply-first branch forms its product only when that product fits. The function returns −1
exactly when C(n, k) > i64_MAX, as its comment says. The 1.2.3 loop bound
(CWE-834) still holds. For k′ ≥ 34, n ≥ 68 and C(n, 34) ≥ C(68, 34) = 28453041475240576740 >
i64_MAX, so the loop returns −1 by its 34th iteration for any n. For k′ ≤ 33 it runs at most 33
iterations. `binomial(2^62, 2^61)` still returns −1 at once, and the existing test for it
passes.

The helper is a private Euclid loop rather than stdlib `gcd`. `math_advanced` describes itself
as self-contained, and the helper keeps it from making a new call into `lib/math.cyr`. Calling
`gcd` would also work, since `math` is in ganita's `[deps]`.

**Tested** in a patched copy of 1.2.10, on cyrius 6.6.11 (the manifest pin) on x86_64:

- The repro exits **0**; the unpatched copy exits **9**.
- All 2556 cells with n ≤ 70 match Python's `math.comb`: the value when it fits, −1 when it
  does not. The 2024 large-n stress cases also match, with 0 differences; unpatched, they show
  1272 refusals of values that fit.
- `cyrius test`: **605 passed, 0 failed**. Unpatched, the suite is 597 passed. The patch
  changes the C(62, 31) assertion at `tests/ganita.tcyr:860` from −1 to 465428353255261088 and
  adds eight assertions: C(66, 33), C(2^32, 2) and its mirror, C(67, 33) → −1,
  C(2^32 + 1, 2) → −1, C(i64_MAX, 2) → −1, C(i64_MAX, 1), and a Pascal sweep for n ≤ 70.
  Run against the unpatched source, five rows fail: the changed C(62, 31), C(66, 33),
  C(2^32, 2), its mirror, and the sweep, which counts 113 cells.
- The other CI gates also pass on the patched copy:
  - `cyrius fmt --check` and `cyrius lint` are clean.
  - `cyrius vet` reports 12 deps, 0 untrusted, 0 missing.
  - The build has 0 warnings, and the smoke binary exits 42.
  - `cyrius fuzz` passes, and `cyrius bench` runs.
  - `cyrius coverage --min 100` gives 139/139.
  - `scripts/coverage-honest.sh 88` gives 144/163 (88.3 %). Unpatched it is 144/162 (88.9 %).
    The difference is the new `_gn_gcd`: it adds one function, the suites reach it only
    through `ganita_binomial`, and so the script does not count it.
  - `dist/ganita.cyr` has to be regenerated with `cyrius distlib --all`. After that,
    `distlib --all --check` passes.

**Cost.** Measured with `lib/bench.cyr` on x86_64: 1,000,000 calls per row, three runs each.

| call | unpatched | patched |
|---|---|---|
| `binomial(52, 5)` | 20 ns | 21 ns |
| `binomial(61, 30)` | 117–118 ns | 121–122 ns |
| `binomial(62, 31)` | 106–108 ns (−1) | 160–161 ns (value) |
| `binomial(66, 33)` | 90–91 ns (−1) | 215–216 ns (value) |
| `binomial(2^32, 2)` | 9 ns (−1) | 16 ns (value) |

Inputs that never take the gcd branch do the same arithmetic as before. The 1 ns and 4 ns
differences on those rows are noise: a second set of builds measured them 0 to 3 ns apart. The
slower rows are the ones that used to give up partway.

## Consumer-side workaround

abaco 2.4.9 stopped calling ganita's `binomial` from its evaluator. It uses its own
`abaco_binomial` in `abaco/src/ntheory.cyr:221`, which returns `Ok(C(n, k))` or `Err(0)`. It
has the same multiply-first branch, the same gcd branch (using stdlib `gcd`) and the same
overflow check on C(n, i + 1). The comment at `abaco/src/ntheory.cyr:204-220` and `abaco/docs/sources.md`
cite Knuth §1.2.6. The evaluator's `binomial` / `choose` branch is `abaco/src/eval.cyr:1728-1749`.

abaco's other calls to ganita's `binomial` alias are in `abaco/tests/test_ntheory.tcyr:176-189`,
all with n ≤ 20. ganita answers those correctly today, and the fix does not change them.
abaco's record is CHANGELOG 2.4.9 ("Fixed — `binomial` past ganita's limit"). Its roadmap
lists the upstream fix as moot for abaco but still worth making.
