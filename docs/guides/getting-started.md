# Getting started with ganita

ganita is a **library**, not an application. Its product is
`dist/ganita.cyr` — a single bundled file that cyrius folds into its stdlib as
`lib/ganita.cyr` (the sandhi pattern), and that any Cyrius project can vendor
directly. `src/main.cyr` exists only as a compile smoke test; it exits 42 and
computes nothing.

## Build and test

```sh
cyrius deps                               # resolve stdlib deps
cyrius build src/main.cyr build/ganita    # the smoke — exits 42
cyrius test                               # [build].test + every tests/*.tcyr
cyrius bench                              # tests/ganita.bcyr
cyrius distlib --all                      # regenerate dist/ganita.cyr
```

## Layout

| Path | What it is |
|---|---|
| `src/matrix.cyr` | storage layer — row-major dense f64 matrix, the `ganita_mat_new` guard |
| `src/linalg.cyr` | decompositions and solvers, built on `matrix.cyr` |
| `src/math_advanced.cyr` | f64 transcendental + number theory, self-contained over f64 builtins |
| `src/math_f32.cyr` | the single-precision scalar tier |
| `src/_compat.cyr` | 54 back-compat aliases — **must stay last**, it references every `ganita_*` symbol |
| `src/main.cyr` | full-bundle compile smoke (exits 42) |
| `src/test.cyr` | the `[build].test` entry |
| `tests/ganita.tcyr` | the suite — its current assertion count is in [`state.md`](../development/state.md) |
| `tests/ganita.bcyr` | benchmarks |
| `tests/ganita.fcyr` | fuzz harness |
| `dist/ganita.cyr` | the bundled fold artifact — generated, but committed |
| `docs/examples/*.cyr` | runnable programs, built and run by CI |

**Include order matters.** The compiler is single pass, so a function must be
defined before it is called. `cyrius.cyml`'s `[lib].modules` fixes the order:
matrix → linalg → math_advanced → math_f32 → `_compat`. Any file that carries its
own includes (tests, benchmarks, examples) must follow the same order — and note
that once a file has *any* include of its own, cyrius skips the manifest's
auto-prepend entirely, so it must also list the stdlib leaves it needs.

## Using ganita from your own project

```cyrius
include "lib/math.cyr"      # the f64 polyfills ganita's transcendentals lower to
include "lib/ganita.cyr"
```

Keep `math` in scope alongside ganita: `ganita_f64_sinh` and friends lower
`f64_exp` / `f64_ln` to software polyfills that live in stdlib `math.cyr`, and the
`F64_*` constants live there too.

Start from [`docs/examples/`](../examples/) — five runnable programs covering the
matrix basics, the three routes to a square solve, least-squares fitting, the
decompositions, and the f32 bit-pattern contract.

## Adding a feature

1. **Pick the module.** New matrix storage operations go in `matrix.cyr`; anything
   that decomposes or solves goes in `linalg.cyr`; f64 scalar math in
   `math_advanced.cyr`; f32 in `math_f32.cyr`. Never add to `_compat.cyr` — it is
   a migration shim that only shrinks.
2. **Name it `ganita_*`.** The prefix is the whole point of the carve: these
   symbols land in cyrius's stdlib namespace via the fold, so they must not
   collide.
3. **Write the doc comment on the line immediately above `fn`.** A section banner
   documents only the first function beneath it; `cyrius audit` counts the rest as
   undocumented, and it audits `tests/` as well as `src/`.
4. **State the failure return in that comment.** Every function has one — see the
   table in [`docs/examples/README.md`](../examples/README.md). A doc comment that
   says only "Returns 0 on success" is a defect a caller acts on.
5. **Check every allocation you make.** `alloc` and `ganita_mat_new` both return
   `0` on failure, and there is no `free` — the allocator is a bump allocator.
6. **Add assertions to `tests/ganita.tcyr`** that pin a *property* rather than a
   transcribed number (`A·A⁻¹ = I`, `Qᵀ·Q = I`, `Σλ = trace`), so they survive a
   reimplementation. Where practical, mutate the code the assertion covers and
   confirm it fails — an assertion that passes either way is not a test.
7. **Run the gate**, all of it. `cyrius fmt --check` per file, `lint`, `vet`,
   `build` with zero warnings, `test`, `fuzz`, `bench`, both coverage floors,
   `distlib --all --check`, `consumer-check.sh`, and `cyrius audit` exiting 0.
   [`CONTRIBUTING.md`](../../CONTRIBUTING.md) has the commands.
8. **Regenerate `dist/`** with `cyrius distlib --all` and commit it, or CI fails on
   the tree diff.
9. **Bump `VERSION`**, add the CHANGELOG entry, and refresh
   [`state.md`](../development/state.md).

See [`../adr/template.md`](../adr/template.md) when a design choice deserves an ADR —
"why X over Y", as opposed to an architecture note, which records what is true
about the code.
