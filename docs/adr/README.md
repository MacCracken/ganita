# Architecture Decision Records

Decisions about ganita — what we chose, the context, and the consequences we accept. Use these when a future reader would reasonably ask *"why did we do it this way?"*

## Conventions

- **Filename**: `NNNN-kebab-case-title.md`, zero-padded to four digits. Never renumber.
- **One decision per ADR.** If a decision supersedes a prior one, add a new ADR and set the old one's status to `Superseded by NNNN`.
- **Status lifecycle**: `Proposed` → `Accepted` → (optionally) `Superseded` or `Deprecated`.
- Use [`template.md`](template.md) as the starting point.

## ADR vs. architecture note vs. guide

| Kind | Lives in | Answers |
|---|---|---|
| ADR | `docs/adr/` | *Why did we choose X over Y?* |
| Architecture note | `docs/architecture/` | *What non-obvious constraint is true about the code?* |
| Guide | `docs/guides/` | *How do I do X?* |

## Index

| ADR | Title | Status |
|---|---|---|
| [0001](0001-failure-vocabulary.md) | One failure vocabulary across the matrix and linalg surface | Accepted (amended 1.2.12) |
| [0002](0002-element-cap-is-policy.md) | `GANITA_MAT_MAX_ELEMS` is a policy limit, kept below the allocator's | Accepted |
| [0003](0003-tan-uses-stdlib-rem-pio2.md) | `ganita_f64_tan` reduces through stdlib math's private `_f64_rem_pio2` | Accepted |
| [0004](0004-non-finite-input.md) | NaN and infinite input: refuse where a function judges the matrix, propagate where it carries values | Accepted |
| [0005](0005-svd-is-jacobi-on-a-pivoted-qr.md) | The SVD is one-sided Jacobi on a column- and row-pivoted QR | Accepted |
