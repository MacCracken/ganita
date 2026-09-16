# Performance backlog, and the `GANITA_MAT_MAX_ELEMS` raise

> ✅ **RESOLVED in ganita 1.2.6** (2026-09-16). The three items 1.2.4 left open are
> closed, and the two it expected to need a public API change needed none: no
> public signature changed.
>
> - **`mat_inv`'s per-column scratch.** `ganita_mat_inv` no longer calls
>   `ganita_mat_lu_solve` once per column. One scratch column serves all n solves.
>   Forward substitution starts at the row where `P·e_k` keeps its 1, since every
>   entry above it is exactly zero, and back substitution runs in place. **1.17–1.20×**
>   faster at 60×60 and 120×120, **8n² fewer bytes** per call (348,512 → 233,312 at
>   120×120), and results bit-identical. It also closes a quiet defect: the old loop
>   ignored `lu_solve`'s return, so a failed scratch allocation copied a stale
>   solution into the inverse and reported success. `lu_solve` itself is untouched.
> - **Transposes materialised and discarded.** No `ganita_mat_transpose` call is
>   left in `linalg.cyr`. `qr` transposes its square Q in place: 116,176 → 960 bytes
>   per call at 120×120, and the reflector is the only allocation left. `pseudo_inv`
>   scales V^T's rows and has the multiply kernel store `(U·Σ⁺V^T)^T` directly, 26–28%
>   fewer bytes. Both fixes are to memory, which the bump allocator never gets back;
>   time is unchanged to within 1%, and so are the results, bit for bit. The
>   multiply's pointer arithmetic still exists exactly once, now as
>   `_ganita_mat_mul_into` with a `transposed` flag, and `ganita_mat_mul` is
>   unchanged to within 1%.
> - **Raising `GANITA_MAT_MAX_ELEMS`.** Decided rather than deferred: it **stays at
>   33,554,430 as a policy limit**, recorded in
>   [ADR 0002](../../../adr/0002-element-cap-is-policy.md) with the conditions for
>   revisiting it. The value, and the fact that it sits at or below what one
>   allocation can hold, are pinned by assertions.
>
> Old and new ran side by side on 400 random cases — square, tall, singular and
> rank-deficient — with **0 bit differences** across `inv`, `qr`, `pseudo_inv` and
> `mul`, and each comparison was mutation-verified. The 1.2.4 banner this replaces
> is kept below for the record.
>
> <details><summary>The 1.2.4 status (superseded)</summary>
>
> ⚠️ **PARTIALLY RESOLVED — THIS FILING STAYS OPEN.** Five of six items landed in
> ganita 1.2.4 (2026-09-08) and are measured below; what remains is one policy
> decision and two items that need a public API change, so the file is kept in
> `issues/` rather than `archived/` — an open item in an archived folder is how
> a backlog quietly disappears.
>
> **Done:**
> - **`mat_get`/`_set` in the hot loop** — `ganita_mat_mul`'s accumulation loop
>   uses raw row/column pointers. **3.34x at 120x120**, matching the predicted
>   2–3.7x. Deliberately confined to that one loop: it is the only O(m·n·k) one,
>   and a per-element saving nobody can measure is not worth an off-by-one that
>   writes out of bounds.
> - **`pseudo_inv`'s dense Sigma_inv is gone** — V's columns are scaled in
>   place, O(n²) instead of a full O(n³) multiply by a diagonal.
> - **`mat_new`'s redundant zero fill** — `_ganita_mat_new_raw` keeps the
>   CWE-190 guard and skips only the fill, used by the callers that provably
>   overwrite every element.
> - **`rank`/`condition` values-only** — a flagged SVD path skips the V
>   accumulation and U construction. **1.61x at 40x40.**
> - **`qr`'s reflector allocation** is hoisted out of the k-loop; it used to leak
>   O(m·n) of bump-allocator scratch per factorisation.
> - **`sinh`/`cosh` evaluate one exp**, using `exp(-x) = 1/exp(x)`, bounded at
>   |x| <= 500 so the reciprocal stays in the normal range.
>
> **Still open, and why:**
> - **`mat_inv`'s per-column scratch.** The allocation is inside
>   `ganita_mat_lu_solve`, which `mat_inv` calls n times. Hoisting it means
>   changing `lu_solve`'s signature to accept a caller-provided buffer — a
>   public API change for what is, with a bump allocator, memory growth rather
>   than time. Not worth it alone; worth folding into any future API revision.
> - **Transposes materialised once and discarded.** Inherent to
>   `ganita_mat_transpose` returning a new matrix. Removing them needs in-place
>   or fused variants, i.e. new public API.
> - **Raising `GANITA_MAT_MAX_ELEMS`** — STILL DEFERRED, for the reasons in the
>   1.2.3 audit, which have not changed: one 268M-element matrix is 2 GiB, the
>   entire ALLOC_MAX, so allocating it leaves nothing for the working factors;
>   and it multiplies by 8 the memory a single call can demand of every existing
>   consumer. This is a policy question about whether ganita should cap below the
>   allocator, not a defect.
>
> </details>


**Filed by**: ganita's 1.2.3 P(-1) sweep (performance lens — every claim below was
benchmarked, not asserted)
**Against**: `src/matrix.cyr`, `src/linalg.cyr`, `src/math_advanced.cyr`
**Date**: 2026-09-07
**Version**: ganita 1.2.3
**Severity**: **Medium** / **Low**

`ganita_mat_eigen_sym`'s O(n⁴) pivot search was the one worth fixing in 1.2.3 —
6.5× at n = 200, with bit-identical results. These are the rest, in the order they
are worth doing.

## 1. `ganita_mat_get` / `_set` in inner loops cost 2–3.7× (MEDIUM)

Every `ganita_mat_get(m, i, j)` re-reads `load64(m + 8)` for the column count and
recomputes the full offset. In the triple loop of `ganita_mat_mul`, and in the
rotation loops of `eigen_sym`, a hoisted row base pointer measured **2× to 3.7×**
faster.

The catch, and why it is not a trivial change: the accessors are what make the
code readable, and hoisting means open-coding pointer arithmetic in exactly the
places where an off-by-one is an out-of-bounds write. Worth doing in the two or
three hottest loops with a comment at each site, not as a sweeping edit.

## 2. `ganita_mat_pseudo_inv` spends O(n³) on an O(n²) job (MEDIUM)

It builds a dense `Sigma_inv` matrix and calls `ganita_mat_mul` with it. That is a
full matrix multiply to apply a **diagonal scaling** — scaling V's columns in place
is O(n²).

## 3. `ganita_mat_new` zero-fills buffers nine callers immediately overwrite (MEDIUM)

`mat_copy`, `mat_neg`, `mat_add`, `mat_sub`, `mat_scale`, `mat_transpose`,
`mat_from` and others fill every element right after allocating. The zero-fill is
load-bearing for `mat_new`'s *public* contract (a fresh matrix is zero) — so the
fix is an internal `_ganita_mat_new_raw` that skips it, used only where the caller
provably writes every element. Keep the guard; skip only the fill.

## 4. `rank` and `condition` run a full SVD to read the singular values (LOW)

Both construct U and accumulate V, then read only `sigma`. A values-only path
through `eigen_sym` would skip the O(n) eigenvector update on every rotation.
Overlaps with [`2026-09-07-svd-via-ata-squares-condition.md`](2026-09-07-svd-via-ata-squares-condition.md)
— do them together.

## 5. Smaller items (LOW)

- `ganita_mat_inv` allocates `n*8` fresh scratch per column and forward-substitutes
  densely against a unit vector whose leading entries are known zero.
- `ganita_mat_qr` allocates the reflector inside its k-loop (the allocator is a
  bump allocator with no free, so this is O(m·n) of garbage per call) and
  materialises a whole extra matrix to transpose a square Q in place.
- Every `ganita_mat_transpose` inside `linalg.cyr` materialises a matrix that is
  consumed once and discarded.
- `ganita_f64_sinh` and `_cosh` evaluate `f64_exp` twice where one exp and a
  reciprocal suffice.

## 6. Raising `GANITA_MAT_MAX_ELEMS`

Separate from the above, and deliberately deferred at 1.2.3.

The constant is `33,554,430`, derived from `ALLOC_MAX = 0x10000000` (256 MiB).
**cyrius v6.4.51 raised `ALLOC_MAX` to `0x80000000` (2 GiB)** and the constant did
not follow — so until 1.2.3 the comment's "kept in step with alloc.cyr's
ALLOC_MAX" was false. The re-derived value is `(0x80000000 - 16) / 8 =
268,435,454`.

The drift had a real consequence: it is why `ganita_mat_least_squares`' internal
`m × m` Q hit the cap at `m = 5793` rather than `m = 16383` — the SIGSEGV 1.2.2
fixed.

**It was not raised**, because at 1.2.3 that is a capability change wearing a
hardening change's clothes:

- one 268M-element matrix is 2 GiB, i.e. the **entire** `ALLOC_MAX`, so allocating
  it succeeds only by leaving nothing for the working factors every decomposition
  needs;
- `eigen_sym` is O(n³), so matrices within an order of magnitude of the cap are
  computationally out of reach regardless;
- it silently multiplies by 8 the memory a single call can demand of every
  existing consumer.

*The raise was attempted during the sweep and reverted*: it turned three of the
1.2.2 allocation-failure assertions into real 268–512 MB allocations, one of which
fed a 6000 × 6000 matrix to the Jacobi eigensolver and hung the suite. That is
worth knowing before trying again — raising the cap requires revisiting those
assertions, and it wants a decision about whether ganita should have a *policy*
limit below the allocator's, which is what the comment now says it has.
