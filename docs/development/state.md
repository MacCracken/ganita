# ganita — Current State

> Refreshed every release. CLAUDE.md is preferences/process/procedures
> (durable); this file is **state** (volatile).

## Version

**1.0.0** — initial carve out of cyrius stdlib (2026-06-10, cyrius v6.1.26).

## Toolchain

- **Cyrius pin**: `6.1.25` (in `cyrius.cyml [package].cyrius`)

## Source

Linear-algebra & advanced-math modules carved from cyrius stdlib, public
functions prefixed `ganita_`:

| Module | Public fns | Canonical prefix |
|--------|-----------|------------------|
| `src/matrix.cyr` | 14 | `ganita_mat_*` |
| `src/linalg.cyr` | 26 | `ganita_mat_*` (extends matrix) |
| `src/math_advanced.cyr` | 13 | `ganita_f64_*` / `ganita_fibonacci` / `ganita_binomial` |

- `src/_compat.cyr` — 53 back-compat aliases (legacy names → `ganita_*`).
- `dist/ganita.cyr` — 1,358-line bundle (53 canonical + 53 alias fns),
  regenerated via `cyrius distlib`. Folded into `cyrius/lib/ganita.cyr`.

## Tests

- `tests/ganita.tcyr` — matrix dims + identity + binomial/fibonacci + alias
  parity (11 assertions).
- `src/main.cyr` — full-bundle compile smoke (exits 42).
- Deep per-module coverage stays in cyrius's `matrix`/`linalg`/`math` `.tcyr` suite.

## Dependencies

Direct (`cyrius.cyml [deps].stdlib`): string, fmt, alloc, io, vec, str,
syscalls, assert, bench, **math**. The transcendental fns lower `f64_exp`/
`f64_ln` to software polyfills (`_f64_exp_polyfill`, …) that live in stdlib
`math.cyr` — consumers must keep `math` in scope alongside ganita.

## Consumers

- **cyrius** — folds `dist/ganita.cyr` → `lib/ganita.cyr` (v6.1.26).
- Downstream repos using matrix/linalg/advanced-math migrate to `ganita_*`
  on re-pin (aliases bridge the window).

## Next

See [`roadmap.md`](roadmap.md). bayan (data formats) was the sibling carve
(cyrius v6.1.25); Phase E (the stdlib data/math carve) closes with ganita.
