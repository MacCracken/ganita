# ganita

> **Linear-algebra & advanced-math distfile for the AGNOS-lineage Cyrius
> ecosystem** — dense `matrix` ops, a `linalg` decomposition/solver suite
> (LU / QR / Cholesky / SVD / eigensolver / least-squares / pseudo-inverse),
> and the advanced `math` functions (transcendental + number theory) carved
> out of the Cyrius stdlib. Foldable into stdlib byte-identical per the
> sandhi pattern.

**ganita** (Sanskrit गणित — *calculation, mathematics*) is the home for the
math-domain modules that don't belong in the primitives-only stdlib floor.
Written in [Cyrius](https://github.com/MacCracken/cyrius).

## Status

**1.0.0** — initial carve out of cyrius stdlib (cyrius v6.1.26). matrix +
linalg (the `mat_*` linear-algebra API) move whole; the **advanced** half of
`lib/math.cyr` (transcendental + fibonacci/binomial) splits out. Stdlib
`math.cyr` keeps the primitives (F64 constants, basic ops, gcd/lcm, f64_parse).

## Modules

| Module | Public prefix | Surface |
|--------|---------------|---------|
| `matrix` | `ganita_mat_*` | dense matrix: new / get / set / identity / add / sub / scale / mul / transpose / dot |
| `linalg` | `ganita_mat_*` | LU / det / inverse / Cholesky / QR / Gaussian-elim / least-squares / eigen-sym / SVD / pseudo-inverse / rank / condition |
| `math_advanced` | `ganita_f64_*`, `ganita_fibonacci`/`ganita_binomial` | transcendental (sinh/cosh/tanh/pow/asin/acos/atan2/asinh/acosh/atanh/hypot) + number theory |

### Back-compat aliases

`src/_compat.cyr` forwards the legacy names (`mat_mul`, `f64_pow`,
`binomial`, …) to the canonical `ganita_*` API for the migration window.
Deprecated; removed once the ecosystem re-pins.

## Build

```sh
cyrius deps                               # resolve stdlib deps (incl. math)
cyrius build src/main.cyr build/ganita    # compile the smoke (exits 42)
cyrius test                               # run tests/ganita.tcyr
cyrius distlib                            # regenerate dist/ganita.cyr (the fold artifact)
```

## Consuming

```cyrius
include "lib/math.cyr"     # f64 builtin polyfills (_f64_exp_polyfill, …) + F64 constants
include "lib/ganita.cyr"
```

The transcendental functions lower `f64_exp`/`f64_ln` to software polyfills
that live in stdlib `math.cyr` — keep it in scope alongside ganita.

## License

GPL-3.0-only
