# Changelog

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

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
