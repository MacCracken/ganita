# ADR 0002 — `GANITA_MAT_MAX_ELEMS` is a policy limit, kept below the allocator's

**Status**: Accepted
**Date**: 2026-09-16
**Version**: 1.2.6

## Context

`GANITA_MAT_MAX_ELEMS` caps `rows * cols` in `ganita_mat_new` and
`_ganita_mat_new_raw`. It does two jobs:

1. **The CWE-190 guard.** The check `rows > GANITA_MAT_MAX_ELEMS / cols` cannot
   overflow, and any cap below `(2^63 - 16) / 8` keeps `16 + rows*cols*8` from
   wrapping i64. This job does not care what the value is.
2. **A bound on what one call can take.** This job is entirely about the value.

The value is `33,554,430`: `(ALLOC_MAX - 16) / 8` when stdlib's `ALLOC_MAX` was
256 MiB. cyrius v6.4.51 raised `ALLOC_MAX` to 2 GiB and the constant did not
follow, while its comment went on claiming to be "kept in step". That drift is why
`ganita_mat_least_squares`' internal `m × m` Q hit the cap at `m = 5793` rather than
`m = 16383` — the SIGSEGV fixed at 1.2.2. The 1.2.3 audit corrected the comment,
declined to raise the value, and filed the question in the performance backlog,
where 1.2.4 and 1.2.5 left it open. This ADR answers it.

What was true at 1.2.6:

- **The allocator never frees.** Every working factor a decomposition allocates
  stays allocated for the life of the process, so a call's footprint is the sum of
  its allocations, not their peak. `ganita_mat_inv` keeps two `n × n` matrices;
  `ganita_mat_svd` a working copy of A and an `n × n` V on top of the caller's
  out-params; `ganita_mat_pseudo_inv` its own U, V^T and result as well.
- **The O(n³) routines cannot use a bigger matrix.** At the current cap the largest
  square is 5792 × 5792. Scaled from the 1.2.6 benchmarks on the reference host,
  one `ganita_mat_mul` of that size is about **9.5 minutes** and one
  `ganita_mat_eigen_sym` about **11 hours**. Every decomposition here is O(n³).
- **Raising it was tried once**, during the 1.2.3 sweep, and reverted: three
  allocation-failure assertions became real 268–512 MB allocations, and one of them
  fed a 6000 × 6000 matrix to the Jacobi eigensolver and hung the suite.
- **No consumer has asked for a larger matrix.** The one cap-related failure ever
  filed (naad, a 5793 × 3 least-squares design) was not a cap problem: the algorithm
  built a matrix it did not need, and 1.2.2 removed it.

## Decision

**`GANITA_MAT_MAX_ELEMS` stays at 33,554,430 as a deliberate policy limit — at most
256 MiB of element data per matrix, one eighth of what a single allocation can
hold.** It is not derived from `ALLOC_MAX` and does not follow it.

Two properties are pinned by assertions in `tests/ganita.tcyr`:

1. **The value.** Changing it is a decision recorded by superseding this ADR, not an
   edit that happens to pass the suite.
2. **`GANITA_MAT_MAX_ELEMS <= (ALLOC_MAX - 16) / 8`.** The policy, not the
   allocator, is the limit a caller meets. If a future stdlib shrinks `ALLOC_MAX`
   below the cap, this assertion fails on the pin bump and the ADR gets revisited
   then, rather than the cap quietly stopping being the binding limit.

**Revisit when** a consumer files a concrete workload the cap blocks, with its
shape; or the allocator gains a way to hand large blocks back, which removes the
accumulation argument above; or ganita takes on a sparse or out-of-core tier (out
of scope in the roadmap today).

## Consequences

- **Positive** — the most memory any single matrix can take is 256 MiB, and a
  decomposition's working set stays around a gigabyte at worst. Existing consumers
  see no change at all. Past the cap, the failure is a checked null from
  `ganita_mat_new` rather than an out-of-memory kill.
- **Negative** — there is capability a caller with the RAM for it cannot use. A
  10,000 × 10,000 dense matrix is 763 MiB and is refused, and a least-squares design
  is capped at `m · n <= 33,554,430` (about 11 million samples at three
  coefficients). Those workloads are mostly O(n) or O(m·n²), where the cap is not
  also a compute limit.
- **Neutral** — raising the cap later is one constant in code but a real review:
  every assertion that relies on the cap to produce a null has to be revisited
  first. The 1.2.3 hang is why.

## Alternatives considered

**Raise it to the re-derived 268,435,454 (2 GiB).** Rejected. It is a capability
change dressed as a hardening one: one matrix of that size is the entire
`ALLOC_MAX`, so it can be allocated only by leaving nothing for the working
factors every decomposition needs; it multiplies by eight the memory one call can
take from every existing consumer; and no O(n³) routine could finish on a matrix
anywhere near it.

**Compute it from `ALLOC_MAX` at run time.** Rejected. ganita's contract would then
change whenever the pinned stdlib did, silently — which is exactly the drift that
moved the least-squares ceiling. A policy should move only when someone decides it
should.

**Per-routine caps** (smaller for the O(n³) decompositions). Rejected. The cost of
an O(n³) call on a large matrix is time the caller can see and choose to spend, not
a safety problem, and a second limit per function would complicate the failure
vocabulary of [ADR 0001](0001-failure-vocabulary.md) for no protection it lacks.

**No ganita cap, only the allocator's.** Rejected. A cap at `(2^63 - 16) / 8` would
keep the overflow guard, but it would drop the memory bound entirely, and a caller
who sizes a matrix from untrusted input would get multi-gigabyte allocations where
today they get a null.
