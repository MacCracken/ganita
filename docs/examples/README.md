# ganita examples

Five runnable programs covering the public API. Each is a real Cyrius program that
compiles and runs — CI builds and runs every one on each push, so an example that
stopped being true would fail the gate rather than quietly become a lie.

Build and run any of them from the repo root:

```sh
cyrius build docs/examples/01-matrix-basics.cyr /tmp/ex01 && /tmp/ex01
```

| | File | Covers |
|---|---|---|
| 01 | [`01-matrix-basics.cyr`](01-matrix-basics.cyr) | construction, the CWE-190 dimension guard, element access, arithmetic, norms, rows/cols/submatrix |
| 02 | [`02-solving-systems.cyr`](02-solving-systems.cyr) | LU · Cholesky · Gaussian elimination on one system, cross-checked; determinant and inverse; what each route does with a singular matrix |
| 03 | [`03-least-squares.cyr`](03-least-squares.cyr) | over-determined fits, consistent and inconsistent; polynomial fitting at 1,000 / 5,793 / 20,000 samples |
| 04 | [`04-decompositions.cyr`](04-decompositions.cyr) | QR, symmetric eigendecomposition, SVD, rank, condition number, pseudo-inverse — all checked as *properties* |
| 05 | [`05-f32-tier.cyr`](05-f32-tier.cyr) | the single-precision bit-pattern contract, native f32 arithmetic, the sign-magnitude trap, half-to-even rounding |

## Three things every example does, that your code should too

**Carry your own includes.** cyrius skips the manifest's auto-prepend the moment a
file has any `include` of its own, so each example lists the stdlib leaves it needs
and then the ganita modules in `[lib].modules` order — matrix, linalg, math_advanced,
math_f32. The compiler is single pass, and linalg calls into matrix.

**Check every constructor.** `ganita_mat_new` returns **0** for a non-positive
dimension, for an element count past `GANITA_MAT_MAX_ELEMS`, and for an allocation
failure — it does not abort. So does every function that builds a matrix for you.
ganita 1.2.2 fixed a SIGSEGV that existed only because one *internal* caller skipped
this check, on a caller's matrix that was 0.05 % of the cap.

**Read the failure return, not just the value.** Each function reports failure in its
own vocabulary, and the ones that already used a sentinel for a real answer needed a
different one:

| Returns | Success | Failure |
|---|---|---|
| a matrix (`copy`, `inv`, `transpose`, `mul`, `pseudo_inv`, …) | pointer | `0` |
| a flat array (`row`, `col`) | pointer | `0` |
| a status (`lu_solve`, `cholesky_solve`, `qr`, `least_squares`, `svd`) | `0` | `-1` |
| `eigen_sym` | iteration count ≥ 0 | `-1` max iterations · `-2` allocation |
| `rank` | count ≥ 0 | `-1` |
| `det` | the determinant, `0.0` if singular | **NaN** |
| `condition` | the ratio, `-1.0` if singular | **NaN** |
| `lu` | permutation sign ±1 | `0` if singular |
| `cholesky` | `1` | `0` if not positive-definite |
| `gaussian_elim` | `1` | `0` if singular |

`det` and `condition` return NaN rather than `0.0` / `-1.0` because those two values
are real answers *about the matrix*. Overloading either to also mean "the run failed"
would report a perfectly invertible matrix as singular.

## Contracts the examples rely on

- **`ganita_mat_get` / `ganita_mat_set` do not bounds-check.** They compute
  `m + 16 + (r*cols + c)*8` and dereference it, because they sit inside every inner
  loop in `linalg.cyr`. If your indices come from untrusted input, check them first.
  See [`SECURITY.md`](../../SECURITY.md).
- **`ganita_mat_qr`'s `out_q` is m × m** by contract, which bounds `m` at roughly 5792
  for anyone who needs Q explicitly. If you only want to *solve*, `ganita_mat_least_squares`
  forms no Q at all and is O(m·n) — example 03 fits 20,000 samples, which was
  impossible at any cap before 1.2.2.
- **`ganita_mat_max_norm` is the infinity norm** — the largest absolute *row sum*, not
  the largest absolute element. The name reads the other way round.
- **`ganita_f32_*` speaks bit patterns**, not f64 values: an f32 is its IEEE-754 single
  pattern in the low 32 bits with the high 32 clear. `f32_to` before you print.
