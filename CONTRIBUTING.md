# Contributing to ganita

## Development

1. Install the Cyrius toolchain. The pin in `cyrius.cyml` (`[package].cyrius`) is the
   single source of truth — CI reads it from there and no version is hardcoded in YAML.
2. `cyrius deps` — resolve dependencies (ganita declares stdlib leaves only).
3. `cyrius build src/main.cyr build/ganita` — the smoke entry point; it exits **42**.
4. `cyrius test` — runs `[build].test` plus every `tests/*.tcyr`.

## What the gate checks

`.github/workflows/ci.yml` is the contract. Before opening a PR, run it locally:

```sh
cyrius fmt <file> --check     # per file — cyrfmt reads only argv[1]
cyrius lint src/*.cyr         # always exits 0; gate on the reported counts
cyrius vet src/main.cyr
cyrius build src/main.cyr build/ganita   # must emit zero `warning:` lines
cyrius test && cyrius fuzz && cyrius bench
cyrius coverage --min 80
cyrius distlib --all --check && cyrius distlib --all
./scripts/consumer-check.sh /tmp/consumer-check
cyrius audit                  # must exit 0 — it audits docs in tests/ too
```

`dist/ganita.cyr` is a build artifact that is nonetheless committed: it is what cyrius
folds into its stdlib as `lib/ganita.cyr` (the sandhi pattern). Regenerate it with
`cyrius distlib --all` and commit the result, or CI fails on the tree diff.

## House rules

- **One change at a time.** Do not bundle unrelated fixes into one commit.
- **Every buffer declaration is a contract**: `var buf[N]` is N *bytes*, not N entries.
- **Test after every change**, not after the feature is done.
- **Do not modify `lib/`** — it is a vendored copy of the pinned stdlib snapshot, and CI
  compares it tree-for-tree against `~/.cyrius/versions/<pin>/lib`. Change the pin and
  re-run `cyrius lib sync --full` instead.
- **New public functions need a doc comment on the line immediately above `fn`.** A
  section banner documents only the first function beneath it; `cyrius audit` counts the
  rest as undocumented, and it audits `tests/` as well as `src/`.
- Assertions should pin **properties** (`A·A⁻¹ = I`, `Qᵀ·Q = I`, `Σλ = trace`) rather than
  transcribed output, so they survive a reimplementation. Where practical, verify a new
  assertion discriminates by mutating the code it covers and watching it fail.

## Versioning

`VERSION` at the repo root is the source of truth. `cyrius.cyml` interpolates it, the
CHANGELOG heading must match it, and every `dist/*.cyr` header must match it — CI checks
all four agree.

## License

GPL-3.0-only.
