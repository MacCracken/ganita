# Changelog

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

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
