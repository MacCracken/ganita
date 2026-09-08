# `ganita_mat_least_squares` never checks its own `mat_new`, and forms an `m × m` Q it does not need

> ✅ **RESOLVED in ganita 1.2.2** (2026-09-07). Both defects are closed, and the
> sweep the report asked for was done in the same pass.
>
> - **The square Q is gone.** `ganita_mat_least_squares` no longer calls
>   `ganita_mat_qr`. The Householder reflectors are applied to `b` in the same
>   sweep that reduces A to R, which *is* `Q^T·b` — so peak memory is O(m·n),
>   not O(m²), and the ~5792 ceiling is gone entirely rather than reported. The
>   repro exits **0**; a degree-2 fit over **100,000** samples, impossible before
>   at any cap, now costs about 4 MB and returns the exact coefficients.
> - **Not thin MGS.** The report preferred thin modified Gram-Schmidt (as ported
>   by hisab 1.4.0). Householder-applied-to-`b` reaches the same O(m·n) bound and
>   was chosen instead because it is unconditionally stable where MGS is not, and
>   because it is the same arithmetic ganita already shipped — only the
>   accumulation of Q and its transpose are removed. Results are strictly more
>   accurate, the reflectors now reaching `b` directly rather than through a
>   materialised Q.
> - **Every internal allocation is checked.** Not just the three named here:
>   `mat_add`/`sub`/`scale`/`mul`/`transpose`/`copy`/`neg`/`row`/`col`/`submatrix`,
>   `lu_solve`, `det`, `inv`, `cholesky_solve`, `qr`, `eigen_sym`, `svd`,
>   `pseudo_inv`, `rank` and `condition`. Failure is reported in each function's
>   own vocabulary — null for the matrix- and array-returning ones, `-1` for the
>   status ones (`-2` for `eigen_sym`, whose `-1` was taken), and **NaN for `det`
>   and `condition`**, because `0.0` and `-1.0` are real answers those two already
>   give about the matrix and must not be overloaded to mean "the run failed".
> - **Pinned by tests.** 17 new assertions: the 5793×3 fit that used to SIGSEGV
>   now solves to its exact coefficients, plus the reachable allocation failures —
>   the ones a caller hits with matrices that are themselves well inside the cap
>   because the working factor is derived and larger. Mutation-verified: restoring
>   the m×m Q kills the suite with the report's own SIGSEGV, and removing any one
>   null check does the same.
>
> `ganita_mat_qr` keeps its explicit m×m `out_q` — that is its documented
> contract and a caller who wants Q must still budget for it. What changed is
> that solving no longer goes through it.


**Filed by**: naad (2.1.3 P-1 hardening sweep — a public DSP function was
SIGSEGV-ing on ordinary input)
**Against**: ganita `src/linalg.cyr:624-628` — `ganita_mat_least_squares`
**Date**: 2026-08-23
**Version**: ganita **1.1.4** (repo HEAD `fcbb9da`, and the copy vendored in
cyrius 6.5.35's stdlib snapshot — both identical)
**Repro**: [`repros/2026-08-23-least-squares-unchecked-q-alloc.cyr`](../repros/2026-08-23-least-squares-unchecked-q-alloc.cyr)
— exits **139 (SIGSEGV)**, verified
**Severity**: **High** — a null-pointer write reachable from a public API with
valid, in-contract arguments. No caller-side workaround exists other than not
calling the function.

## Summary

`ganita_mat_least_squares` allocates a **full `rows × rows` orthogonal Q**
internally and never checks the result. Since 1.1.4 gave `ganita_mat_new` a
CWE-190 guard that returns `0` for oversized designs, that null now flows
straight into `ganita_mat_qr`, which writes through it.

The caller's own matrix can be far inside every documented limit. A least-squares
fit of a degree-2 polynomial over 5793 samples is a `5793 × 3` design — **17,379
elements**, 0.05 % of `GANITA_MAT_MAX_ELEMS` (33,554,430). `mat_new` accepts it
happily. But the internal Q is `5793 × 5793` = **33,558,849 elements**, just over
the cap, so `mat_new` returns 0 and the next line stores to address `16`.

Nothing in the signature, the doc comment, or the guard's own error surface tells
a caller that `m` is bounded at ~5792 — and it is bounded by a **square matrix
the algorithm does not need**.

⚠ **The guard is not the bug; the unchecked caller is.** 1.1.4's `mat_new` guard
is correct and is directly tested (`tests/ganita.tcyr` covers
`mat_new(33554431, 1)` and the overflow case). What is untested is ganita's own
*internal* call sites checking that new return value. Adding a failure return to
a constructor converts every unchecked caller from "allocates and works" to
"nulls and faults", which is what happened here.

## Reproduction

From the ganita repo root:

```sh
cyrius build docs/development/issues/repros/2026-08-23-least-squares-unchecked-q-alloc.cyr /tmp/lsq
/tmp/lsq; echo "exit=$?"
```

```
caller matrix allocated OK (5793 x 3 = 17379 elems, cap is 33554430)
calling ganita_mat_least_squares (forms a 5793 x 5793 Q internally)...
exit=139
```

The repro builds a `5793 × 3` Vandermonde, confirms `mat_new` accepted it, then
calls `ganita_mat_least_squares`. `5793` is the exact first failing `m` for
`n = 3`: `33554430 / 5793 = 5792`, and `5793 > 5792`.

It includes `src/matrix.cyr` + `src/linalg.cyr` **directly**, not
`lib/ganita.cyr`, so it exercises the working source — note this repo's bundled
`lib/ganita.cyr` is currently **1.1.1** against a `src/` of 1.1.4, and its
`cyrius.cyml` pin (6.5.29) trails the installed toolchain (6.5.35). Neither
affects this bug; flagged only so the build warnings are not mistaken for it.

## Root cause

`src/linalg.cyr:624-628`:

```
fn ganita_mat_least_squares(a, b, out_x): i64 {
    var rows = ganita_mat_rows(a);
    var cols = ganita_mat_cols(a);
    var q = ganita_mat_new(rows, rows);      # <-- rows*rows, unchecked
    var r = ganita_mat_new(rows, cols);      # <-- also unchecked
    ganita_mat_qr(a, q, r);
```

`src/matrix.cyr:26` returns `0` when `rows > GANITA_MAT_MAX_ELEMS / cols`.
`ganita_mat_qr` then does `store64(out_q + 16 + i * 8, ...)` in its
Q-initialisation loop — the first write through the null.

Two distinct defects, and the second is the one that matters long-term:

1. **Unchecked allocations.** `q`, `r` and the later `alloc(rows * 8)` for `qtb`
   are all unchecked, and `ganita_mat_least_squares` has no way to report
   failure — it returns `0` for success and has no error code reserved. Even a
   plain out-of-memory `alloc` failure at any `m` lands on the same write.
2. **The square Q is unnecessary.** Least squares needs only the thin factor.
   For reference, the Rust `hisab` crate (1.4.0, `src/num/linalg.rs`) implements
   exactly this operation with a **thin modified-Gram-Schmidt QR**: `Q` is
   `m × n`, `R` is `n × n`, and no `m × m` allocation exists anywhere in the
   path. Peak memory is `O(m·n)` instead of `O(m²)`. For a degree-2 fit over
   100,000 samples that is **2.4 MB versus 80 TB** — the current implementation
   cannot do that fit at all, and the Rust one does it comfortably.

## Proposed fix

Either is a real improvement; the second is the better one.

**(a) Minimal — check and report.** Give `ganita_mat_least_squares` a negative
failure return, check all three allocations, and document the `m` bound:

```
    var q = ganita_mat_new(rows, rows);
    if (q == 0) { return 0 - 1; }
    var r = ganita_mat_new(rows, cols);
    if (r == 0) { return 0 - 1; }
```

This is source-compatible for callers that already test `== 0` for success, and
it closes the OOM path as well as the cap path. It leaves the `O(m²)` ceiling in
place.

**(b) Preferred — thin QR.** Compute the thin factor directly (modified
Gram-Schmidt over the columns, then back-substitution), so no square Q is ever
formed. This removes the size ceiling entirely rather than reporting it, and
makes the function usable for the large regressions it is otherwise the natural
tool for. Combine with (a) for the remaining OOM path.

A sweep of ganita's other internal `mat_new` call sites is worth doing in the
same pass — this is unlikely to be the only caller written before the guard
existed.

## Consumer-side workaround

naad shipped both, in sequence, and the history may be useful:

- **2.1.3** capped its input at the derived bound
  (`if (nx > GANITA_MAT_MAX_ELEMS / nx) { return out; }`) and recorded the cap
  as a knowing divergence from its Rust oracle in an ADR. This trades a SIGSEGV
  for a wrong-but-safe `None`, and does **not** close the OOM path.
- **2.2.0** removed the dependency: `fit_polynomial` now implements thin QR
  in-tree (a line-for-line port of hisab 1.4.0's), so naad no longer calls
  `ganita_mat_*` at all. See naad `docs/adr/0002-port-thin-qr-in-tree.md`.

naad is therefore no longer exposed, and this report is not blocking for it. It
is filed because the defect is real, reachable from ganita's public API with
in-contract arguments, and the next consumer to reach for `mat_least_squares` on
a real-sized dataset will hit it with no indication of why.
