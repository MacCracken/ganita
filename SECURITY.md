# Security Policy

## Scope

ganita is a pure-computation library. It opens no files, binds no sockets, spawns no
processes, parses no argv, and issues no syscall other than `write(2)` to stdout from
`ganita_mat_print`. There is no path traversal surface and no command-injection surface
here, and a finding that claims one has misread the library.

**The entire attack surface is the arguments a caller passes to a public function.**
Concretely:

- **Dimensions** — `rows`, `cols`, `n`, and the `r0/c0/r1/c1` of `ganita_mat_submatrix`.
  `ganita_mat_new` carries the CWE-190 guard that keeps `16 + rows*cols*8` from wrapping
  i64 (see `GANITA_MAT_MAX_ELEMS` in `src/matrix.cyr`), and every internal allocation
  checks its result. Dimensions that reach the library from untrusted input should still
  be validated by the caller, because a legal dimension can still name a derived working
  factor that is not — `ganita_mat_det` takes `n` from the row count, so a wide
  non-square asks for an `n × n` factor the caller's own matrix never implied.
- **Indices** — `ganita_mat_get` and `ganita_mat_set` are the raw accessors. They compute
  `m + 16 + (r * cols + c) * 8` and dereference it. **They do not bounds-check**, by
  design: they sit inside every inner loop in `src/linalg.cyr`, and the library's own
  callers have already established the bounds. A caller that indexes from untrusted input
  must check `0 <= r < rows` and `0 <= c < cols` first.
- **Pointers** — the out-params (`out_x`, `out_vals`, `out_q`, …) and the flat `b` arrays
  are raw heap pointers the caller allocates, at a length the doc comment states. ganita
  writes the documented number of elements and cannot tell whether the buffer is that
  large.

## Contract violations are not vulnerabilities in the library

Functions document their contracts (`m >= n` for the least-squares and SVD family,
symmetric input for `ganita_mat_eigen_sym`, positive-definite for
`ganita_mat_cholesky`). Passing input outside a stated contract is a caller defect. A
*silently wrong result* where the contract says the input is supported **is** a ganita
defect, and is what the audit sweeps look for.

## Reporting

Report vulnerabilities to robert.maccracken@gmail.com. Please include a minimal
Cyrius program that reproduces the issue, the `cyrius` version, and the ganita `VERSION`.

## Audit history

Security sweeps are filed in [`docs/audit/`](docs/audit/) as
`YYYY-MM-DD-vX.Y.Z-audit.md`, per the AGNOS first-party standards' P(-1) process.
Resolved defect filings live in
[`docs/development/issues/archived/`](docs/development/issues/archived/) with their
repros in [`repros/`](docs/development/issues/repros/).
