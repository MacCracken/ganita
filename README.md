# ganita

> **Linear-algebra & advanced-math distfile for the AGNOS-lineage Cyrius
> ecosystem** — dense `matrix` ops, a `linalg` decomposition/solver suite
> (LU / QR / Cholesky / SVD / eigensolver / least-squares / pseudo-inverse),
> the advanced `math` functions (transcendental + number theory), and a
> native single-precision `f32` scalar tier. Foldable into stdlib
> byte-identical per the sandhi pattern.

**ganita** (Sanskrit गणित — *calculation, mathematics*) is the home for the
math-domain modules that don't belong in the primitives-only stdlib floor.
Written in [Cyrius](https://github.com/MacCracken/cyrius).

## Status

**1.2.14** — toolchain 6.6.18; `dist/` regenerated with a compile-verified requires block, so
`include "dist/ganita.cyr"` alone compiles, and a three-leaf sidecar (`math alloc fmt`). See
[`CHANGELOG.md`](CHANGELOG.md) for the full history and
[`docs/development/state.md`](docs/development/state.md) for the live snapshot.
Recent releases in brief:

| | |
|---|---|
| **1.2.14** | toolchain 6.6.18; `dist/ganita.cyr` carries a compile-verified `# Requires` block (raw-includable); `dist/ganita.deps` 10 leaves → `math alloc fmt` |
| **1.2.13** | `pseudo_inv` / `condition` work in the SVD's working scale: no NaN entries for a σ below 2^-1024, and condition(DBL_MAX·[[1, 1], [1, −1]]) is 1, not −1.0 |
| **1.2.12** | SVD rewritten as Jacobi on a column- and row-pivoted QR ([ADR 0005](docs/adr/0005-svd-is-jacobi-on-a-pivoted-qr.md)): no finite input known to reach non-convergence, now `-3`; 2.5–2.8× faster at 20×20 and 40×40; non-finite input refused across linalg ([ADR 0004](docs/adr/0004-non-finite-input.md)); toolchain 6.6.15 |
| **1.2.11** | `ganita_f64_tan` / `ganita_f32_tan` (fdlibm `k_tan`; tan needs stdlib math ≥ 6.6.9, [ADR 0003](docs/adr/0003-tan-uses-stdlib-rem-pio2.md)); `binomial` refuses only past i64_MAX; `atan2` signed zeros / NaN / (±∞, ±∞); sinh/tanh/atanh/asinh/acosh/asin up to 1.3e8 ulp → ~2; sinh/cosh overflow band 495 → 1 ulp; toolchain 6.6.12 |
| **1.2.10** | toolchain 6.6.11; `cyrius coverage --min 100` (6.6.11 no longer counts the uncallable `main`) |
| **1.2.9** | f32 `sin` / `cos` correct past 2^63 (the NaN guard dropped — stdlib's `f64_sin` reduces every finite argument since cyrius 6.6.9); toolchain 6.6.10 |
| **1.2.8** | `pow` within 1 ulp everywhere — an fdlibm `e_pow` core replaces `exp(y·ln x)` (909 ulp) and the squaring path (772 ulp); toolchain 6.6.9 |
| **1.2.7** | `pow` answers the C99 Annex F special values (was NaN for every infinite base/exponent off the integral path, and for `pow(1, NaN)`); toolchain 6.6.7 |
| **1.2.6** | `ganita_f64_cbrt`, correctly rounded for every f64 (and so every f32); `inv`/`qr`/`pseudo_inv` stop discarding scratch; element cap settled by ADR 0002; toolchain 6.6.4 |
| **1.2.5** | toolchain 6.6.0 → 6.6.2 |
| **1.2.4** | relative tolerances, one-sided Jacobi SVD, exact integer `pow`, f32 comparators; mat_mul 3.34× |
| **1.2.3** | P(-1) sweep: audit, hardening, optimization, runnable examples, security policy |
| **1.2.2** | `mat_least_squares` forms no Q at all (was a SIGSEGV at m ≈ 5793); every internal allocation checked |
| **1.2.1** | toolchain 6.5.36 → 6.6.0 |
| **1.2.0** | native f32 arithmetic (`add`/`sub`/`mul`/`div`), `lerp` de-widened onto it |
| **1.1.x** | the f32 scalar tier; linalg and f32 test suites; the `f64_pow` domain fix |
| **1.0.0** | initial carve out of cyrius stdlib (v6.1.26) |

## Modules

| Module | Public prefix | Surface |
|--------|---------------|---------|
| `matrix` | `ganita_mat_*` | dense f64 matrix: new / from / identity / get / set / add / sub / scale / mul / transpose / dot / print |
| `linalg` | `ganita_mat_*` | copy / neg / row / col / set_row / set_col / submatrix / trace / eq / is_symmetric / frobenius / max_norm · LU / det / inverse / Cholesky / QR / Gaussian-elim / least-squares / eigen-sym / SVD / pseudo-inverse / rank / condition |
| `math_advanced` | `ganita_f64_*`, `ganita_fibonacci`/`ganita_binomial` | transcendental (sinh/cosh/tanh/pow/cbrt/tan/asin/acos/atan2/asinh/acosh/atanh/hypot) + number theory |
| `math_f32` | `ganita_f32_*` | single-precision scalar tier: native arithmetic (add/sub/mul/div), comparators (lt/le/gt/ge), shape (abs/neg/sign/min/max/clamp/floor/ceil/trunc/round/lerp), sqrt, and transcendental forwarders |

### Back-compat aliases

`src/_compat.cyr` forwards 55 names (`mat_mul`, `f64_pow`, `binomial`, …)
to the canonical `ganita_*` API for the migration window. Deprecated; removed
once the ecosystem re-pins. Two of them, `f64_cbrt` (1.2.6) and `f64_tan`
(1.2.11), are not legacy names: they arrived with their functions, under the
stdlib-style name the requesting consumer reaches for.

## Two contracts worth knowing before you call anything

**Constructors return null, they do not abort.** `ganita_mat_new` returns `0` for
a non-positive dimension, for an element count past `GANITA_MAT_MAX_ELEMS`
(33,554,430 — the CWE-190 guard that keeps `16 + rows*cols*8` from wrapping i64,
and a deliberate per-matrix memory limit, [ADR 0002](docs/adr/0002-element-cap-is-policy.md)),
and for an allocation failure. Every function that builds a matrix propagates
that null. **Check it.** ganita 1.2.2 fixed a SIGSEGV that existed only because
one internal caller did not, on a caller's matrix that was 0.05 % of the cap.

**Failure is reported in each function's own vocabulary**, settled in
[ADR 0001](docs/adr/0001-failure-vocabulary.md): null for the matrix- and
array-returning functions; **negative** for the status ones (`-1` allocation,
`-2` contract violation, `-3` non-convergence), so `< 0` is a universal failure
test; and **NaN** for `det` and `condition` — because `0.0` and `-1.0` are real
answers *about the matrix* there, and overloading either would report an
invertible matrix as singular. Three functions fail with `0` instead of a
negative: `ganita_mat_lu`, whose successes are the permutation signs `+1`/`-1`,
and `ganita_mat_cholesky` and `ganita_mat_gaussian_elim`, which return `1` on
success. A NaN or infinite input is refused by every function that judges a
matrix ([ADR 0004](docs/adr/0004-non-finite-input.md)). The full table is in
[`docs/examples/README.md`](docs/examples/README.md).

## Build

```sh
cyrius deps                               # resolve stdlib deps (incl. math)
cyrius build src/main.cyr build/ganita    # compile the smoke (exits 42)
cyrius test                               # run tests/ganita.tcyr
cyrius distlib --all                      # regenerate dist/ganita.cyr (the fold artifact)
```

## Consuming

```cyrius
include "lib/math.cyr"     # f64 builtin polyfills (_f64_exp_polyfill, …) + F64 constants
include "lib/ganita.cyr"
```

Stdlib `math.cyr` is needed on every target: the `F64_*` constants, the software
polyfills `f64_exp`/`f64_ln` lower to, and — for `ganita_f64_tan`, `f64_tan` and
`ganita_f32_tan` — its fdlibm argument reduction `_f64_rem_pio2`, which stdlib math
has carried **since cyrius 6.6.9**. On an older stdlib everything else still builds
and behaves the same (x86_64 builds print one `undefined function '_f64_rem_pio2'`
warning), and a call to tan is a compile-time error.
See [ADR 0003](docs/adr/0003-tan-uses-stdlib-rem-pio2.md).

## Examples

Five runnable programs in [`docs/examples/`](docs/examples/), covering matrix
basics, the three routes to a square solve, least-squares fitting, the
decompositions, and the f32 bit-pattern contract. CI builds and runs every one,
so they cannot rot.

```sh
cyrius build docs/examples/01-matrix-basics.cyr /tmp/ex01 && /tmp/ex01
```

## Documentation

- [`docs/examples/`](docs/examples/) — runnable programs, gated by CI
- [`docs/guides/`](docs/guides/) — task-oriented how-tos
- [`docs/adr/`](docs/adr/) — architecture decision records (*why X over Y?*)
- [`docs/architecture/`](docs/architecture/) — non-obvious constraints (*what's true about the code?*)
- [`docs/audit/`](docs/audit/) — security and hardening sweeps
- [`docs/development/state.md`](docs/development/state.md) — live state snapshot
- [`docs/development/roadmap.md`](docs/development/roadmap.md) — milestones through v1.0
- [`SECURITY.md`](SECURITY.md) — attack surface and reporting
- [`CONTRIBUTING.md`](CONTRIBUTING.md) — the gate, and the house rules

## License

GPL-3.0-only
