# Changelog

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

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
