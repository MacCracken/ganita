# Changelog

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Fixed

- **`cyrius bench` runs with zero warnings again.** Every run printed
  `warning: undefined function 'ganita_f64_pow' / 'ganita_f64_atan2' /
  'ganita_f64_hypot'`. `tests/ganita.bcyr` carries its own include list — the
  auto-prepend is skipped once a file has includes — and it included
  `src/math_f32.cyr` **without** `src/math_advanced.cyr`, but `math_f32`'s
  `pow` / `atan2` / `hypot` / `cbrt` forward to the `ganita_f64_*` fns that live
  there. Fixed by adding `include "src/math_advanced.cyr"` ahead of the
  `math_f32` include, matching the order `tests/ganita.tcyr` already uses (the
  compiler is single-pass, so definition order matters).

  Harmless until now only because no benchmark called those four — the first one
  that did would have linked against nothing. No `src/` change, no behavioural
  change: 243/243 assertions, `audit` exits 0, `fmt --check` clean.

## [1.2.1] — 2026-09-07 — toolchain 6.6.0, and the docs audit that came with it

Maintenance. Cyrius pin `6.5.36` → **6.6.0**, `lib/` re-vendored to an exact match
(108 → 109 files), `dist/` regenerated. **No `src/` change and no behavioural
change** — the 243 assertions are the same 243, green on 6.6.0.

### Changed

- **Cyrius pin `6.5.36` → `6.6.0`.** `cyrius version` reports
  `manifest-pin: 6.6.0` with no drift line. The whole CI gate was re-run locally
  against it: format · lint · `vet` (11 deps, 0 untrusted, 0 missing) · build with
  zero compiler warnings · smoke exits 42 · **243/243 assertions** · fuzz · bench ·
  `coverage --min 80` (109/135 fns, 7/7 files) · `distlib --all --check` ·
  regeneration byte-identical · consumer-check clean from 10 declared leaves.

- **`lib/` re-synced to the 6.6.0 snapshot — 109 files, 0 differ** (was 108).
  37 files changed and one is new: `hashseed.cyr`. None of them is in
  `[deps].stdlib`; they ride along because `cyrius lib sync --full` vendors the
  whole snapshot. Verified by comparing the trees against
  `~/.cyrius/versions/6.6.0/lib`, not by trusting the sync's exit code.

- **`dist/ganita.cyr` regenerated** — 1,690 lines, header `Version: 1.2.1`. The
  bundle is otherwise byte-identical to 1.2.0's: only the version line moves,
  because `src/` did not change.

### Fixed

- **`cyrius audit` exits 0 again.** 6.6.0 applies the docs check across the whole
  audit scope — which is `src` **and** `tests` — so the bump turned 1.2.0's green
  audit into `15 undocumented public fns`. Every one is a test-harness helper that
  had simply never been in scope before: 10 in `tests/ganita.tcyr` (`t_tol`,
  `t_dclose`, `t_m2`, `t_m3`, `t_arr2`, `t_arr3`, `t_f32div`, `t_f64_is_nan`,
  `t_f64_is_pos_inf`, `t_is_nan`), 3 in `tests/ganita.bcyr` (`bench_noop`,
  `bench_f32_lerp_widened`, `main`) and 2 in `tests/ganita.fcyr` (`fuzz_main`,
  `main`).

  **The rule is positional**: the doc comment must sit on the line *immediately*
  above `fn`. A section banner (`# --- linalg test helpers ---`) documents only the
  first fn beneath it, which is why files that read as thoroughly commented still
  counted 15 — `t_d` and `t_f32` passed solely because they happened to be first
  under their banners. Each of the 15 now carries its own line. No test logic
  changed: 243 assertions before, 243 after.

  This was never a CI failure — `ci.yml` does not run `cyrius audit`. It is a
  regression against what 1.2.0 recorded as shipped, which is why it is fixed here
  rather than deferred.


## [1.2.0] — 2026-09-01 — the f32 arithmetic tier that 1.1.0 said could not be written

Adds `ganita_f32_add` / `_sub` / `_mul` / `_div` in **native single precision**, and
rewrites `ganita_f32_lerp` to use them. Minor, not patch: four new public functions.
243 assertions (was 227); `cyrius audit` exits 0 for the first time (docs were the
blocker — see below).

### Added

- **TIER 0 — `ganita_f32_add`, `ganita_f32_sub`, `ganita_f32_mul`, `ganita_f32_div`.**
  Real `addss` / `subss` / `mulss` / `divss`: **one rounding, in f32, per operation.**

  1.1.0 shipped tiers 1-3 and recorded that this tier was impossible. The module
  header said so, `ganita_f32_lerp`'s comment said so, and the closing note on
  [the filing](https://github.com/MacCracken/cyrius) listed it as a remaining
  cyrius-side gap: *"there is no callable `f32_add`/`f32_sub`/`f32_mul`, so no f32
  tier can be written in native single-precision arithmetic today."*

  **The reasoning had one wrong clause.** It is true that `f32_add(...)` is not a
  builtin and that cyrius reaches f32 arithmetic only through the operators on an
  `F32_TYID`-typed value. The wrong part was the conclusion drawn from *"and these
  params arrive as untyped i64 bit patterns"* — a parameter can simply **be typed**:

  ```
  fn ganita_f32_mul(a: f32, b: f32): i64 {
      var s: f32 = a * b;
      return s;
  }
  ```

  The typed params put the incoming patterns in xmm lanes as singles, the `var s: f32`
  binding emits the single-precision op, and returning `s` as `i64` hands the pattern
  back. Callers pass and receive exactly the same bit patterns as the rest of the tier —
  no signature change to anything that already existed.

  Only the **return** type is still barred (`fn f(): f32` is rejected with *"fn return
  type must be struct or i8/i16/i32/i64/Result/Option/Tagged/cstring/f64/f64v2/f64v4"*),
  and that costs nothing here because the bit pattern is the interchange form anyway.
  That one remains a genuine cyrius-side gap, as does the `sqrtss` intrinsic.

### Fixed

- **`ganita_f32_lerp` no longer widens.** It computed `a + (b - a) * t` as a single f64
  expression rounded once at the end; it now rounds three times, in single, exactly as
  the same expression does in Rust or C. **Results can differ from 1.1.x by 1 ULP — the
  new ones are the single-precision answers.** A new assertion pins
  `lerp(a,b,t) == add(a, mul(sub(b,a), t))` rounding for rounding, which the widened
  form did not guarantee.

### Fixed (docs)

- **`cyrius audit` now exits 0.** It was failing on `70 undocumented public fns` —
  every one of `_compat.cyr`'s 53 deprecated aliases, 15 of `math_f32.cyr`'s own tier
  (including three the change above had just added), and both `main` entry points.
  All 70 now carry a doc line, so the gate is green rather than permanently red, and
  a genuinely new undocumented function will be visible instead of lost in the count.

### Changed (toolchain)

- **Cyrius pin `6.5.29` → `6.5.36`**, with `cyrius lib sync --full` (108 files). This
  clears the drift warning *and* the `./lib/ shadows version-pinned .../6.5.29/lib — 7
  bundled lib(s) differ` warning that 1.1.4 shipped with. It also retires 1.1.4's
  blocker: that release pinned a version whose GitHub tarball did not exist, so CI
  failed at the install step. 6.5.36 is published.

### Notes on what this is NOT

- **It is not a speedup, and the benchmark says so.** `tests/ganita.bcyr` now measures
  the native tier against the 1.1.x widen-compute-narrow shape at 1M iterations:
  `f32_mul` 3 ns vs 3 ns, `f32_lerp` 5 ns vs 4 ns — indistinguishable, and on the
  `lerp` row the widened shape came out marginally *ahead* on one run, which is the
  spread rather than a result. The `cvtss2sd`/`cvtsd2ss` pair is free at this
  granularity. **The tier is about semantics, not cost — do not sell it as a speedup.**
- **For a SINGLE operation the old shape was already correct.** f64 carries 53 mantissa
  bits against f32's 24, more than 2·24+2, so widen-compute-narrow is correctly rounded
  for one `+ - * /` and double rounding cannot bite. The difference appears when a
  consumer **chains** operations and an f64 intermediate keeps precision f32 does not
  have. `add(add(2^24, 1), 1)` is 2^24 natively and 2^24+2 through an f64 accumulator;
  that pair is the test that pins these as native.
- `ganita_f32_sqrt` still widens — `sqrtss` needs a new cyrius intrinsic, which is a
  compiler change. It is correctly rounded, per the same 53-bit argument.


## [1.1.4] — 2026-08-19 — `f64_pow` domain

### Changed (toolchain)

- **Cyrius pin `6.5.28` → `6.5.29`**, with `cyrius lib sync --full` run against
  it; `lib/` matches the snapshot exactly (108 files, 0 differ). 6.5.29 carries
  the `distlib` profile-sidecar fix that made ganita's own artifacts
  irreproducible on CI at 1.1.1 — ganita's single-bundle sidecar is unchanged by
  it (`syscalls string alloc fmt vec str math`), since the defect only bit
  `[lib.X]` profiles.

  ⚠ **The 6.5.29 GitHub release is not published yet.** Both workflows install
  by handing the pin to the upstream `scripts/install.sh`, which downloads
  `cyrius-<pin>-x86_64-linux.tar.gz` — that asset currently 404s, so CI fails at
  the install step until the release goes out. Everything below was verified
  against the **locally installed** 6.5.29, not a release tarball; re-verify
  once it ships, per the standing rule in `state.md`.

### Fixed

- **`ganita_f64_pow` returned NaN for a zero or negative base.** It was
  `exp(y · ln base)` and nothing else, and that identity only holds for
  `base > 0` — `ln(0)` is `-inf`, `ln(negative)` is NaN, and the NaN propagated
  out silently. `pow(0, 2)` and `pow(-2, 3)` are ordinary defined operations;
  both came back NaN with no diagnostic. Filed at 1.1.2, fixed here.

  The domain is now handled ahead of the exp/ln path, following C's `pow`:

  | call | before | after |
  |---|---|---|
  | `pow(0, 2)` / `pow(0, 3)` / `pow(0, 0.5)` | NaN | `0.0` |
  | `pow(0, -2)` | NaN | `+inf` |
  | `pow(0, 0)` | `1.0` ✅ | `1.0` |
  | `pow(-2, 2)` | NaN | `4.0` |
  | `pow(-2, 3)` | NaN | `-8.0` |
  | `pow(-2, 10)` | NaN | `1024.0` |
  | `pow(-3, 0.5)` | NaN | **NaN, deliberately** |
  | `pow(2, 10)` / `pow(9, 0.5)` / `pow(2, -2)` | correct | unchanged |

  **A non-integral exponent on a negative base stays NaN** — there is no real
  result, so NaN is the right answer and is left alone rather than papered over.
  That is also why `ganita_f32_cbrt` keeps its sign split: `cbrt` needs
  `pow(x, 1/3)`, which remains out of domain for negative `x`.

  Sign comes from the exponent's parity, computed on the magnitude, so
  `pow(-x, odd)` is **bit-identical** to `-pow(x, odd)` — the negative path adds
  no error of its own. Parity treats every `|y| >= 2^53` as even, which is not a
  shortcut: at that magnitude consecutive f64 values are 2 apart, so no odd
  integer is representable.

  **Deliberately not done:** C distinguishes `pow(-0, odd) = -0` from
  `pow(+0, odd) = +0`. cyrius's `f64_neg(f64_from(0))` yields `+0`, so a negative
  zero cannot be produced or asserted against through the f64 helper surface —
  a branch for it would have been untestable dead code. Zero of either sign
  returns `+0`, and the reasoning is recorded at the call site.

- **`ganita_f32_pow` inherits the fix**, being a widen-compute-narrow wrapper.
  f32 rounding absorbs the exp/ln core's ~2e-15 error, so `f32_pow(-2, 3)` is
  now exactly `-8.0f`.

### Changed — tests

The **self-expiring** `f32: known domain gaps` group added at 1.1.2 did exactly
what it was for: it asserted the old NaN behaviour, failed the moment the gap
closed, and has been rewritten to the real answers. 227 assertions (was 210),
including a new f64-level `pow` domain group covering zero, negative, integral
and non-integral exponents, `+inf`, `x^0`, the bit-identity of the negative
path, and the positive-path regressions.

**Mutation-verified**: deleting the zero-base branch fails 5 assertions,
dropping the parity sign flip fails 3, and treating every negative-base exponent
as integral fails 3 — the last being the check that a genuinely undefined
operation is still reported as NaN.

### Note for cyrius

cyrius ships this defect under the plain stdlib name `f64_pow` (the `_compat`
alias in the folded `lib/ganita.cyr:1538`), so a consumer who never heard of
ganita hits it. cyrius's fold is at **1.1.1**; a refold picks up this fix plus
1.1.2's `cbrt(±0)` guard and the 1.1.2/1.1.3 test suites. Upstream filing:
`cyrius/docs/development/issues/2026-08-19-f64-pow-nan-for-zero-and-negative-base.md`.

### Verified on 6.5.29 (local install — see the toolchain note above)

All 15 CI gates green. `cyrius test` — **227 passed, 0 failed**. Build clean
with zero warnings, smoke exits 42, fmt + lint clean, `distlib --all --check`
current and idempotent, consumer-check clean, coverage 80%.

## [1.1.3] — 2026-08-19 — linalg gets a test suite

`linalg.cyr` was the largest untested surface in the repo at **2/26** — every
decomposition and solver (LU, Cholesky, QR, SVD, Jacobi eigen, least squares,
pseudo-inverse) shipped unverified. Now **26/26**, with 90 new assertions.
Repo-wide reference coverage 37% → **80%** (105/131), and the exercise pulled
`matrix.cyr` to 10/14 and `_compat.cyr` to 40/53 along the way.

### Added — `tests/ganita.tcyr`

Assertions are **properties**, not transcribed outputs, so they stay valid if an
algorithm is reimplemented and they cannot be satisfied by a plausible-looking
wrong answer:

| Routine | Pinned by |
|---|---|
| `lu` / `det` | pivot sign after one swap; `det = -6` and `-306` by hand; `det(A^T) = det(A)`; singular → `lu` returns 0 and `det` is 0 |
| `lu_solve` | 2x2 and a 3x3 round trip (solve `M·[1,2,3]`, recover `[1,2,3]`) |
| `inv` | `A·A⁻¹ = I` **and** `A⁻¹·A = I`; `inv(inv(A)) = A`; singular → returns 0, not garbage |
| `cholesky` | `L·Lᵀ = A`; `L` lower triangular; rejects a symmetric **non**-positive-definite matrix |
| `qr` | `Q·R = A`; **`Qᵀ·Q = I`**; `R` upper triangular — square *and* 3x2 |
| `gaussian_elim` | solution in the last column, agreeing with `lu_solve` on the same system; singular → 0 |
| `least_squares` | consistent overdetermined system, so the exact answer is assertable |
| `eigen_sym` | eigenvalues; **Σλ = trace** and **Πλ = det**; `A·v = λ·v`; eigenvectors orthonormal; diagonal input left alone |
| `svd` | `U·Σ·Vᵀ = A` (diagonal and non-diagonal); σ sorted descending; **Πσ = \|det\|** |
| `pseudo_inv` | equals `inv` when invertible; Moore–Penrose `A·A⁺·A = A` |
| `rank` / `condition` | rank of full-rank vs rank-deficient; `cond(I) = 1`; `cond ≥ 1`; singular → the documented `-1` sentinel |

`mat_eq` is the comparison tool for most of the above, so **both its polarities
are pinned first** — an `eq` that always returned 1 would make the rest vacuous.
Utilities (`copy` deep-not-aliased, `neg` involution, row/col accessors,
`set_row`/`set_col` isolation, half-open `submatrix`, Frobenius, max-norm as max
*row sum*, trace, symmetry incl. non-square) are covered too.

**Mutation-verified.** Forcing the LU pivot sign to `+1` fails 2 assertions;
deleting Cholesky's positive-definite check fails 1; making QR return an
identity `Q` fails 6, including both least-squares assertions — which is the
suite noticing that `least_squares` is built on QR.

### Changed

- CI coverage floor raised `37` → **`80`**.

### Found, not fixed — `fmt_float` drops the carry when a fraction rounds to 1.0

`fmt_float(2.9999999, 6)` prints `2.1000000` — seven fraction digits, carry
dropped — and `1.0 - 1e-8` prints `0.1000000`. Display only; the values are
correct. It surfaced here because near-integer results are routine after a
decomposition: a correct `cholesky_solve` result of `3.0` printed as `2.1000000`
and a correct `least_squares` result of `1.0` printed as `0.1000000`, both of
which read as solver bugs. This is cyrius stdlib (`lib/fmt.cyr`), vendored, so
it is **filed rather than changed**:
[2026-08-19](docs/development/issues/2026-08-19-fmt-float-missing-carry-on-round-up.md).
The suite is unaffected — it asserts numerically, never on printed text.

### Verified on released 6.5.28

`cyrius test` — **210 passed, 0 failed** (was 120). Build clean with zero
warnings, smoke exits 42, `distlib --all --check` current, consumer-check clean.

## [1.1.2] — 2026-08-19 — f32 tier gets a test suite, and it found two bugs

1.1.0 shipped 23 `ganita_f32_*` helpers with **no test at all** (`math_f32.cyr`
was 0/23 referenced — the module was never even included by
`tests/ganita.tcyr`). This closes that: **23/23 functions covered, 95 new
assertions**, and overall reference coverage 16% → **37%** with 7/7 files
referenced.

### Fixed

- **`ganita_f32_cbrt(0)` returned NaN.** Zero fell through to `pow`, `pow` is
  `exp(y·ln x)`, and `ln(0)` is `-inf` — so the cube root of zero was NaN.
  Guarded explicitly, `±0 -> ±0`, preserving the sign of zero. The failure was
  invisible to any test that only tried positive non-zero inputs.

### Added — `tests/ganita.tcyr`

**The `_f32_key` sign-magnitude story is now pinned, and mutation-verified.**
1.1.0 called it "the whole correctness story" and named the trap precisely:
IEEE-754 is sign-magnitude, so raw bit patterns order correctly only among
non-negatives — and pixel data *is* non-negative, so a naive unsigned compare
passes every plausible test. The suite states the trap as an assertion
(`-1.0f` sorts *below* `-2.0f`; every negative sorts *above* every positive),
then checks the cases that discriminate:

| Case | Correct | A bare unsigned compare gives |
|---|---|---|
| `min(-1,-2)` | `-2` | `-1` |
| `max(-1,-2)` | `-1` | `-2` |
| `min(-1, 1)` | `-1` | `1` |
| `max(-1, 1)` | `1` | `-1` |

Replacing `_f32_key` with the naive `b & 0xFFFFFFFF` fails **12** assertions
across min/max/clamp and the hygiene group. Removing `cbrt`'s sign split fails
exactly 2 — both negative-input cases, while every positive still passes, which
is the shape of bug a positives-only suite misses.

Also covered: signed zeros (`min(+0,-0) = -0`), infinities, commutativity;
`clamp` including an all-negative range; `abs`/`neg`/`sign` on zeros and
infinities with their involution and idempotence laws; **high-32 hygiene** —
every entry point masks, so an operand with a dirty high half still yields a
clean 32-bit result; `floor`/`ceil`/`trunc` at `±2.5` where all three differ,
plus `trunc(-0.5) = -0`; `lerp` endpoints and a sign-spanning midpoint;
`sqrt(2) = 0x3FB504F3`, the correctly-rounded single (f64's 53 mantissa bits
exceed 2·24+2, so double-rounding cannot bite); and exact identities for every
tier-3 function.

**`round` is half-to-EVEN, not half-away-from-zero** — pinned explicitly with a
note, because C's `roundf(2.5)` is `3.0` while this gives `2.0`. A consumer
porting from C is otherwise quietly off by one on every tie.

### Found, not fixed — `ganita_f64_pow` domain gap

`pow` is `exp(y·ln base)`, valid only for `base > 0`. So `pow(0, 2)` is NaN
(should be `0`) and `pow(-2, 2)` is NaN (should be `4`); `ganita_f32_pow`
inherits both. This is the f64 tier, out of scope for an f32 test pass, so it is
**filed rather than changed**:
[2026-08-19](docs/development/issues/2026-08-19-f64-pow-zero-and-negative-base.md).

The suite carries a **self-expiring** `f32: known domain gaps` group asserting
the current NaN behaviour, so the gap is measured rather than merely known —
those two assertions **fail when the issue is fixed**, which is the signal to
rewrite them to the correct answers.

### Changed

- CI coverage floor raised `16` → **`37`**, matching the new measurement. It
  ratchets up, never down.

### Verified on released 6.5.28

`cyrius test` — **120 passed, 0 failed** (was 25). Build clean with zero
warnings, smoke exits 42, `distlib --all --check` current, consumer-check clean.

## [1.1.1] — 2026-08-19

Toolchain + CI release. No behavioural change — the only `src/` edits are
whitespace and one comment. What changed is that the project now *checks*
considerably more of itself.

### Changed (toolchain)

- **Cyrius pin `6.5.23` → `6.5.28`**, with `cyrius lib sync --full` run against
  it. `lib/` matches the pinned snapshot **exactly — 0 of 108 files differ**,
  confirmed by comparing the trees rather than trusting the sync's exit code.
  `lib/` had been left in a half-bumped state: seventeen `[deps].stdlib`
  modules already carried 6.5.28 content (from a `cyrius deps` run) while the
  pin still said `6.5.23`. The full sync completes it.
- **`lib/` grew 98 → 108 files** — the 6.5.28 snapshot adds `unicode/` (7 files)
  plus the macOS `async`/`thread` variants. None is in `[deps].stdlib`; they
  ride along because `--full` vendors the whole snapshot.

### Fixed

- **`src/linalg.cyr` and `tests/ganita.tcyr` are canonically formatted.**
  Continuation lines sat at column 0; `cyrius fmt` indents them to 2.
  Whitespace only — still 25 assertions, still green. It had gone unnoticed
  because there was no format gate.
- **Lint is clean across all `src/` files.** `linalg.cyr:9` carried an untracked
  deferral: the header prose "Complete pivoting is out of scope" reads to the
  scanner as a deferral marker, when it is a permanent design boundary rather
  than deferred work. Reworded to "deliberately excluded" — no `#skip-lint`
  needed, and the sentence says what it means.

### Added — CI now confirms the whole project

`.github/workflows/ci.yml` went from 4 steps (install / deps / build / test) to
a full gate: toolchain-pin drift · version consistency across
`VERSION` / manifest / CHANGELOG / dist header · `lib/`-vs-snapshot tree diff ·
format (`src/` **and** `tests/`) · lint (0 warnings, 0 untracked deferrals) ·
`cyrius vet` · build with **zero compiler warnings** · smoke exits 42 · test ·
fuzz · bench · `cyrius coverage --min 16` · and three distribution checks.

`release.yml` gains a CHANGELOG-entry check alongside the existing tag/VERSION
check.

**Both workflows now install via the upstream installer** rather than untarring
a release by hand:

```sh
curl -sSf .../cyrius/main/scripts/install.sh | CYRIUS_VERSION="$pin" sh
```

The hand-rolled step laid the toolchain down at `~/.cyrius/{bin,lib}` as real
directories. 6.5.28's `cyrius deps` requires the snapshot at
`~/.cyrius/versions/<pin>/lib` specifically and errors with *"pins version
6.5.28 but it is not installed"*. The installer creates
`versions/<pin>/{bin,lib}` and symlinks `~/.cyrius/{bin,lib}` at them; the
`lib/`-vs-snapshot gate compares against `versions/<pin>/lib` for the same
reason. The pipe carries `set -eo pipefail` — without it a failed download
pipes empty input to `sh`, `sh` exits 0, and the install silently no-ops.
(Same defect and same fix as bayan 1.4.2.)

Three gate mechanics worth knowing before editing the workflow, each verified
against a deliberately broken input rather than assumed:

- `cyrius lint` **always exits 0** — the step parses its `N warnings` /
  `N untracked deferrals` lines.
- `cyrfmt` reads only `argv[1]`, so `cyrius fmt src/*.cyr --check` checks one
  file and exits 0. The step is a per-file loop.
- `cyrius build` only *warns* on bad pointer typing, `lib/` shadowing and pin
  drift, and `--strict` does not promote them — so the step greps `^warning:`.

**`scripts/consumer-check.sh`** (new) compiles a throwaway consumer against
`dist/ganita.cyr` using **only** the seven leaves its `.deps` sidecar declares
(`syscalls string alloc fmt vec str math`). It builds with `cyrius build
--no-deps` — without that, `cyrius build` auto-prepends everything in
`[deps].stdlib` and the check passes vacuously. Verified by deleting leaves one
at a time: dropping `math`, `vec`, `fmt`, `string` or `alloc` fails the check as
it should. **ganita's sidecar is correct** — the bundle compiles clean from its
declared leaves. (`str` turns out to be over-declared, which is harmless: a
consumer including one module more than it needs still builds.)

### Verified on released 6.5.28

Checked against the **release tarball** in an isolated `CYRIUS_HOME`, not the
local `~/.cyrius` — a machine that also develops cyrius can hold an in-flight
build reporting the same version string, and artifacts generated with it are
not reproducible on CI (bayan 1.4.2 hit exactly that).

| Gate | Result |
|---|---|
| `cyrius build src/main.cyr` | OK, **0 warnings**; smoke exits 42 |
| `cyrius test` | **25 passed, 0 failed** (+ 1/1 `[build].test`) |
| `cyrius fmt --check` (src + tests) | clean |
| `cyrius lint` | 0 warnings, 0 untracked deferrals |
| `cyrius vet src/main.cyr` | 11 deps, 0 untrusted, 0 missing |
| `cyrius distlib --all --check` | current; regeneration stable across runs |
| `scripts/consumer-check.sh` | clean from 7 declared leaves |
| `cyrius fuzz` · `cyrius bench` | 1/1 · 1/1 |
| `cyrius coverage` | 22/131 fns (16%) reference coverage |

### Known, not fixed here

- `tests/ganita.fcyr` and `tests/ganita.bcyr` are still `cyrius init` scaffolds
  — the fuzz harness does no fuzzing and the bench measures a no-op. Both report
  PASS, so the two CI gates that run them are currently vacuous.
- **`src/math_f32.cyr` has no test at all** (0/23 fns referenced) — the whole
  1.1.0 f32 tier is untested in-repo, including the `_f32_key` sign-magnitude
  transform that 1.1.0 called "the whole correctness story". `linalg.cyr` is
  2/26. Reference coverage is 16% overall; the floor is set there and should
  ratchet up.
- `docs/development/state.md` had been stale since 1.0.4 (it did not mention the
  1.1.0 f32 tier); refreshed with this release.

## [1.1.0] — 2026-08-17 — f32 scalar tier (ALL THREE TIERS)

**MINOR, not a patch: new public API.** **Twenty-three** `ganita_f32_*` helpers — the FULL surface the filing enumerated, all three tiers, so f32 consumers stop
paying a widen-op-narrow round trip for shape-level operations. Requested from the ranga
(image processing) Rust->Cyrius port, whose pixel loops are f32 throughout — `f32_abs` was
`f32_from(f64_abs(f32_to(x)))`, three ops for a bit-clear.

### Added — `src/math_f32.cyr`

* Pure bit ops, exact, no widening: `ganita_f32_abs`, `_neg`, `_sign`.
* One signed compare on a monotone key: `ganita_f32_min`, `_max`, `_clamp`.
* `ganita_f32_lerp` — widens, and NOT by choice: there is no callable `f32_add`/`f32_sub`/
  `f32_mul`. cyrius dispatches f32 arithmetic through the OPERATORS on an `F32_TYID`-typed
  value (`EMIT_F32_BINOP`), reachable only from a `var x: f32` binding, and these params
  arrive as untyped bit patterns. A first cut called `f32_add(...)` as a builtin and
  `cyrius distlib` caught it (`undefined function`). Widening is exact on the inputs.
* Exact widening (see below): `ganita_f32_floor`, `_ceil`, `_trunc`.

⚠ **min/max/clamp are NOT a bare unsigned compare, and that distinction is the whole
correctness story.** IEEE-754 is SIGN-MAGNITUDE. Raw patterns order correctly only among
NON-NEGATIVE values: for two negatives the order REVERSES (-2.0 has the larger magnitude
field), and any negative compares HIGH against every positive because bit 31 is set. The
filing observed that "for non-negative finite f32 the raw pattern orders identically to an
unsigned integer" — true, and exactly the trap, because pixel data IS non-negative, so a
naive version passes every plausible test and breaks the first time a consumer subtracts.
`_f32_key` applies the standard monotone transform (invert all bits when negative, else set
the sign bit) so one signed compare is correct across the full range. Verified on the
both-negative and mixed-sign cases, not just the easy one.

⭐ **floor/ceil/trunc widen deliberately, and it costs no accuracy.** f32 -> f64 is exact
(every f32 is representable), the f64 rounding intrinsic is exact on it, and an
integer-valued result narrows back exactly. Hand-rolled exponent twiddling would need NaN
and infinity special-cases for zero accuracy gain; the win this tier is about is
min/max/clamp/abs/neg becoming branch-and-mask.

### Changed

* Toolchain pin `cyrius` **6.4.69 -> 6.5.23** (was 15 patches behind; the drift warning
  was live).

### Added — tier 2: `ganita_f32_sqrt`

⚠ The filing asks for `sqrtss` (direct single-precision, no widening). That needs a NEW
cyrius intrinsic — a compiler change, not a library one — so this widens instead, and it
is **correctly rounded rather than approximate**: f64 carries 53 mantissa bits against
f32's 24, more than 2*24 + 2, so computing in double and rounding once to single yields
exactly the single-precision result. Double-rounding cannot bite. The `sqrtss` intrinsic
is recorded as a cyrius-side follow-up.

### Added — tier 3: transcendentals

`ganita_f32_exp`, `_ln`, `_log2`, `_exp2`, `_sin`, `_cos`, `_atan`, `_round`, `_pow`,
`_atan2`, `_hypot`, `_cbrt`. Widen-compute-narrow, which the filing explicitly blesses
here: the win is that the conversions stop being the consumer's problem and the naming
stays symmetric with the f64 tier.

⚠ **`ganita_f32_cbrt` splits on sign, and that is required rather than decorative.** There
is no f64 cbrt in ganita or the stdlib, so it is built from `pow` — which routes through
`exp(y * ln x)`, and `ln` of a negative is undefined. A bare `pow` returns garbage for
every negative input while looking correct for the positives a naive test would use.
Verified on -8 -> -2.

### Process note

An earlier cut of this release shipped **tier 1 only** and recorded tiers 2-3 as "interleaved
fold-ins". That was a silent deferral of a consumer filing's enumerated surface, not a plan —
the filing's tiering was labelled *suggested, cheapest first*, not an instruction to ship a
third. Corrected before release: all three tiers are in this version.

## [1.0.4] — 2026-07-21

### Changed

- **Toolchain pin `6.4.26` → `6.4.69`.** Ecosystem sweep onto the current Cyrius;
  ganita compiles and tests clean on the new pin (25/25, full-bundle smoke exits
  42) with no source change beyond the security fix below, and `dist/ganita.cyr`
  is byte-identical bar that fix. Re-vendored `lib/` to the 6.4.69 full snapshot
  (`cyrius lib sync --full`) so the committed `lib/` is byte-identical to the
  pinned snapshot (99 files) — clearing the stale-6.4.26 shadow/drift build
  warnings — and pruned 10 vendored modules the old snapshot carried that 6.4.69
  no longer ships and ganita never referenced (incl. the standalone
  `matrix`/`linalg`, superseded upstream by the folded `ganita.cyr`).

### Security

- **`ganita_mat_new` integer overflow → heap overflow (CWE-190).** The size
  computation `16 + rows*cols*8` was unguarded: a large `rows*cols` wraps i64 to
  a small (or negative) value, so `alloc` handed back an undersized buffer while
  the following zero-fill loop still ran the full `rows*cols` iterations —
  writing far past the allocation. With attacker-influenced dimensions that is a
  heap-corruption primitive. `ganita_mat_new` now validates dimensions **before**
  allocating: it returns `0` (null) for non-positive dims, for an element count
  above the largest allocatable matrix (`GANITA_MAT_MAX_ELEMS = (ALLOC_MAX − 16)
  / 8 = 33_554_430`, checked via a division that cannot itself overflow), and on
  `alloc` failure. The derived dimension-taking constructors `ganita_mat_identity`
  and `ganita_mat_from` — and their `_compat` aliases `mat_new` / `mat_identity`
  / `mat_from` — propagate the null. **Contract change:** these constructors may
  now return null, so a caller sizing a matrix from untrusted input MUST check
  the result; the fast path is byte-for-byte unchanged for valid dimensions, and
  every internal caller passes dims from already-allocated matrices. Regression
  tests added (`tests/ganita.tcyr`: negative/zero dims, wrap-inducing dims,
  over-cap rejection, valid-8×8 control → 16 → **25** assertions). Downstream
  hisab has shipped a `mat_new_guarded` work-around for this since its 2.5.3;
  this upstream fix lets that fold back into a plain `mat_new` once the cyrius
  pin picks up this ganita.

## [1.0.3] — 2026-07-08

### Fixed

- **Inverse trig (`ganita_f64_asin`/`acos`/`atan2`) un-guarded on aarch64.** They were
  `#ifdef CYRIUS_ARCH_X86` in `src/math_advanced.cyr` because they build on `f64_atan`,
  which was x86-only — while the `_compat.cyr` `f64_asin`/`acos`/`atan2` wrappers sat
  OUTSIDE the guard (a latent undefined-fn on aarch64). Cyrius v6.4.25 added
  `_f64_atan_polyfill`, so the guard is removed; the family now works on x86 (native x87
  `fpatan`) and aarch64 (an aarch64 consumer must `include "lib/math.cyr"` for the
  polyfill). Verified: `ganita_f64_atan2(1,1)` = π/4 on both arches (aarch64 via qemu).

## [1.0.2] — 2026-07-02

### Fixed

- **`ganita_f64_tanh` no longer returns NaN for large |x|.** The
  `(e^x − e^-x)/(e^x + e^-x)` form overflowed to `inf/inf = NaN` once
  `f64_exp(x)` hit +inf (|x| > ~709). Now saturates to ±1 for |x| > 20 — which is
  **bit-exact** (for |x| ≥ ~19, `tanh(x)` already rounds to exactly ±1.0 in f64,
  so no correctly-computed value changes) and NaN-safe. Surfaced by importing a
  real GPT-2-small checkpoint: its GELU `tanh(c·(x + a·x³))` overflows on the
  model's massive-activation outliers, NaN-poisoning the forward. Fixes GELU for
  every downstream consumer (rupantara `ru_gelu_fwd`, attn11 `gelu_fwd`, …).
  Regression tests added (`tests/ganita.tcyr`: `tanh(±1000)` → ±1, boundary
  bit-exactness). No API change.

## [1.0.1] — 2026-06-12

### Changed

- `cyrius` pin bumped 6.1.25 → 6.2.1 (ecosystem-wide stdlib pin sweep onto the
  current toolchain). No source changes — ganita's `[deps]` carries no carved-out
  modules. Verified green on 6.2.1: `cyrius deps` resolves cleanly, `.tcyr` suite
  11/11, bench 1/1, `dist/ganita.cyr` regenerated via `cyrius distlib`.

## [1.0.0] — 2026-06-10

**Initial carve out of the Cyrius stdlib** (cyrius v6.1.26, second half of
Phase E — the bayan/ganita data/math split). ganita becomes the upstream
source of truth for the linear-algebra & advanced-math modules; cyrius folds
`dist/ganita.cyr` byte-identical into `lib/ganita.cyr` (sandhi pattern).

### Added
- **`matrix` + `linalg` carved whole from cyrius stdlib** — the `mat_*`
  dense-matrix base API (14 fns) + the decomposition/solver suite (26 fns:
  LU / det / inverse / Cholesky / QR / Gaussian-elim / least-squares /
  eigen-sym / SVD / pseudo-inverse / rank / condition). Renamed `mat_*` →
  `ganita_mat_*`.
- **`math_advanced`** — the 13 advanced fns SPLIT out of `lib/math.cyr`:
  transcendental (`sinh`/`cosh`/`tanh`/`pow`/`asin`/`acos`/`atan2`/`asinh`/
  `acosh`/`atanh`/`hypot`) + `fibonacci`/`binomial`. Renamed `ganita_*`.
  Self-contained over f64 builtins; the `f64_exp`/`f64_ln` polyfills + F64
  constants stay in stdlib `math.cyr` (primitives), supplied by the consumer.
- **`src/_compat.cyr`** — 53 forwarding aliases exporting the legacy names
  (`mat_mul`, `f64_pow`, `binomial`, …). Deprecated; migration window only.
- **`[lib]` distlib config** — `cyrius distlib` bundles matrix + linalg +
  math_advanced + aliases into `dist/ganita.cyr` (1,358 lines), for the fold.
- Smoke entry (`src/main.cyr`, exits 42) + `tests/ganita.tcyr` (matrix +
  advanced-math + alias parity). Deep coverage stays in cyrius's
  matrix/linalg/math `.tcyr` suite.
- CI: `ci.yml` made reusable (`workflow_call`) so `release.yml` parses
  (the scaffold-template fix from cyrius v6.1.25).
