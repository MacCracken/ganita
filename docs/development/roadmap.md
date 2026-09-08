# ganita — Roadmap

> Milestone plan through v1.0. State lives in [`state.md`](state.md);
> this file is the sequencing — what ships, in what order, against
> what dependency gates.

ganita is past 1.0 as a *version number* (1.0.0 was the carve out of cyrius
stdlib on 2026-06-10) but has never had a **frozen API**. That is what the
milestones below are for: the deprecated `_compat` surface has to go, and the
canonical surface has to be worth freezing before the ecosystem re-pins onto it.

## v1.0-freeze criteria

The point at which `ganita_*` becomes load-bearing and cannot change.

- [x] Public API documented — every exported fn has a doc comment (`cyrius audit` exits 0)
- [x] Security audit pass filed in [`docs/audit/`](../audit/)
- [x] Runnable examples for the public surface, gated by CI ([`docs/examples/`](../examples/))
- [x] At least one downstream consumer green (cyrius, via the `dist/ganita.cyr` fold)
- [x] CHANGELOG complete from 1.0.0 onward
- [x] Benchmark baseline captured (`scripts/bench-history.sh` → `bench-history.csv`)
- [ ] **Test coverage adequate for the surface area** — `cyrius coverage` is at the
      80 % floor, but `math_advanced.cyr` is 4/13 and `matrix.cyr` 10/14. The floor
      is a floor, not the target.
- [ ] **`_compat.cyr` removed** — 53 deprecated aliases still ship, and they are
      exported into cyrius's stdlib namespace by the fold. Needs the consumers to
      re-pin first.
- [ ] **The fuzz harness does something** — `tests/ganita.fcyr` is a `cyrius init`
      scaffold that fuzzes nothing, so the CI gate that runs it is vacuous.
- [ ] **`ganita_mat_get`/`_set` bounds policy decided and recorded as an ADR** —
      they are unchecked by design (they sit in every inner loop), which is a
      defensible choice, but freezing the API means freezing that choice.

## Milestones

### M0 — Carve (1.0.0) — ✅ shipped 2026-06-10

`matrix` + `linalg` moved whole out of cyrius stdlib; the advanced half of
`lib/math.cyr` split out as `math_advanced`. `mat_*` → `ganita_mat_*`, with
`_compat.cyr` bridging the legacy names. cyrius v6.1.26.

### M1 — The f32 tier (1.1.0 – 1.2.0) — ✅ shipped 2026-09-01

27 `ganita_f32_*` helpers so f32 consumers (the *ranga* image-processing port)
stop paying a widen-op-narrow round trip, ending with native single-precision
`add`/`sub`/`mul`/`div` at 1.2.0. Along the way: test suites for the f32 and
linalg tiers (0/23 and 2/26 referenced, respectively, before), and the
`ganita_f64_pow` domain fix.

### M2 — Hardening (1.2.1 – 1.2.3) — ✅ shipped 2026-09-07

Toolchain 6.6.0; the `mat_least_squares` null write closed and every internal
allocation checked (1.2.2); then the full P(-1) sweep — audit, refactor,
optimization, security policy, runnable examples, benchmark baseline. Both open
filings in `docs/development/issues/` closed. See
[`docs/audit/`](../audit/) for the findings.

### M3 — Coverage to the surface area (1.3.0)

_Gate: nothing external._

Close the two real coverage gaps rather than the reported percentage.
`math_advanced.cyr` at 4/13 is the largest untested public surface in the repo,
and it is exactly the module whose defects have historically been *silent* —
`f64_pow` returned NaN for every non-positive base for four releases. Also
replace `tests/ganita.fcyr` with a harness that drives the real input surface:
ganita takes no external input, so the thing to fuzz is the argument space —
dimensions, indices, and bit patterns.

### M4 — Freeze the surface (1.4.0 → v1.0-freeze)

_Gate: consumers re-pinned off the legacy names._

Delete `_compat.cyr`. Record the `mat_get`/`mat_set` bounds policy as an ADR.
Re-fold into cyrius and confirm the stdlib namespace carries only `ganita_*`.

## Out of scope

Deliberately not in ganita, so that nobody adds them by accident:

- **Sparse matrices.** ganita is dense, row-major, one heap block. A sparse tier
  is a different data structure with a different API and belongs in its own carve.
- **Complex numbers.** Every value here is an f64 or f32 bit pattern. Complex
  eigenvalues are the reason `ganita_mat_eigen_sym` is *symmetric*-only.
- **Iterative solvers** (CG, GMRES) and **preconditioners**. Direct methods only.
- **Threading or SIMD.** stdlib has `simd.cyr` and `thread.cyr`; a consumer that
  needs them can build on ganita rather than ganita depending on them.
- **Complete pivoting.** Partial pivoting only — the O(n³) column search per step
  buys nothing for the use cases in the ecosystem.
- **Arbitrary precision.** f64 and f32, nothing else.
