# ganita — Current State

> Refreshed every release. CLAUDE.md is preferences/process/procedures
> (durable); this file is **state** (volatile).
> Last refreshed: 2026-08-19.

## Version

**1.1.1** — toolchain + CI. Cyrius pin `6.5.23` → `6.5.28`, `lib/` re-synced to
an exact match, `dist/` regenerated. No behavioural change: the only `src/`
edits are whitespace and one reworded comment. CI went from 4 steps to a full
gate, including three distribution checks.

Before that: **1.1.0** (2026-08-17) added the **f32 scalar tier** — 23
`ganita_f32_*` helpers across all three tiers, so f32 consumers (the *ranga*
image-processing port) stop paying a widen-op-narrow round trip. The correctness
story there is `_f32_key`: IEEE-754 is sign-magnitude, so raw bit patterns order
correctly only among non-negatives — and pixel data *is* non-negative, which is
exactly why a naive min/max passes every plausible test and breaks the first time
a consumer subtracts. 1.0.4 added the `ganita_mat_new` CWE-190 overflow guard;
1.0.3 an inverse-trig aarch64 guard; 1.0.2 `f64_tanh` saturation; 1.0.0 the
initial carve out of cyrius stdlib (2026-06-10, cyrius v6.1.26).

## Toolchain

- **Cyrius pin**: `6.5.28` (`cyrius.cyml [package].cyrius`). `cyrius version`
  reports `manifest-pin: 6.5.28` with no drift line.
- **`lib/` matches the pin exactly**: 108 files, 0 differ. Verify by comparing
  the trees, not by trusting `cyrius lib sync --full`'s exit code.
- **`lib/` grew 98 → 108 files** at this pin: `unicode/` (7 files) plus the
  macOS `async`/`thread` variants. None is in `[deps].stdlib`; they ride along
  because `--full` vendors the whole snapshot.
- ⚠ **Verify against the RELEASE TARBALL, not `~/.cyrius`.** A machine that also
  develops cyrius can hold an in-flight build reporting the same version string;
  artifacts generated with it are not reproducible on CI. Install the release
  into an isolated `CYRIUS_HOME` and put its `bin` on `PATH`:

  ```sh
  curl -sfLO https://github.com/MacCracken/cyrius/releases/download/<pin>/cyrius-<pin>-x86_64-linux.tar.gz
  tar xzf cyrius-<pin>-x86_64-linux.tar.gz
  H=/tmp/cy<pin>; mkdir -p "$H/versions/<pin>"
  cp -R cyrius-<pin>-x86_64-linux/bin cyrius-<pin>-x86_64-linux/lib "$H/versions/<pin>/"
  ln -sfn "$H/versions/<pin>/bin" "$H/bin"; ln -sfn "$H/versions/<pin>/lib" "$H/lib"
  CYRIUS_HOME=$H PATH="$H/bin:$PATH" cyrius distlib --all --check
  ```

## Source

Linear-algebra & advanced-math modules carved from cyrius stdlib, public
functions prefixed `ganita_`. Regenerated from the tree 2026-08-19:

| Module | Lines | Public fns | Canonical prefix |
|--------|-------|-----------|------------------|
| `src/linalg.cyr`        | 957 | 26 | `ganita_mat_*` (extends matrix) |
| `src/matrix.cyr`        | 197 | 14 | `ganita_mat_*` |
| `src/math_advanced.cyr` | 174 | 13 | `ganita_f64_*` / `ganita_fibonacci` / `ganita_binomial` |
| `src/math_f32.cyr`      | 143 | 23 | `ganita_f32_*` |

- `src/_compat.cyr` — 53 back-compat aliases (legacy names → `ganita_*`).
  Single-pass order: matrix → linalg → math_advanced → math_f32 → `_compat`
  last, since its aliases reference every `ganita_*` symbol.
- `dist/ganita.cyr` — **1,547**-line bundle, regenerated via `cyrius distlib`
  at 1.1.1 on released 6.5.28. This is the artifact folded into
  `cyrius/lib/ganita.cyr`.
- `dist/ganita.deps` — 7 stdlib leaves: `syscalls string alloc fmt vec str math`.
  Verified sufficient by `scripts/consumer-check.sh` (`str` is over-declared but
  harmless).

## Tests

- `tests/ganita.tcyr` — matrix dims + identity + **CWE-190 dimension guard** +
  binomial/fibonacci + `f64_tanh` saturation + alias parity. **25 assertions,
  green** on released 6.5.28.
- `src/main.cyr` — full-bundle compile smoke (exits 42).
- Deep per-module coverage stays in cyrius's `matrix`/`linalg`/`math` `.tcyr`
  suite.

### Coverage

`cyrius coverage` — **22/131 fns (16%)**, 4/7 files referenced. A floor, not a
correctness proof, and the deep suite still lives upstream — but the gaps are
worth naming:

| Module | Referenced |
|---|---|
| `matrix.cyr`        | 6/14 |
| `_compat.cyr`       | 11/53 |
| `math_advanced.cyr` | 3/13 |
| `linalg.cyr`        | **2/26** |
| `math_f32.cyr`      | **0/23** |

## CI

`.github/workflows/ci.yml` is the gate; `release.yml` calls it via
`workflow_call` before publishing. Rewritten at 1.1.1 from 4 steps to a full
sweep. Three properties worth remembering when editing it:

- **Install via the upstream `scripts/install.sh`, never a hand-rolled tar.**
  `cyrius deps` requires the snapshot at `~/.cyrius/versions/<pin>/lib`; a
  hand-untar into `~/.cyrius/{bin,lib}` satisfies the compiler but not `deps`,
  which fails with *"pins version X but it is not installed"*. Compare `lib/`
  against `versions/<pin>/lib`, not the symlink.
- **`cyrius lint` always exits 0** — the step parses its `N warnings` /
  `N untracked deferrals` lines. `cyrius build` exits non-zero on errors but
  only *warns* on bad pointer typing, `lib/` shadowing and pin drift, and
  `--strict` does not promote them — so that step greps `^warning:`.

  The format step must stay a **per-file loop**. `cyrfmt` reads only `argv[1]`
  and silently ignores the rest, so `cyrius fmt src/*.cyr --check` checks the
  first file and exits 0.
- **`scripts/consumer-check.sh` must build with `--no-deps`.** `cyrius build`
  auto-prepends everything in `[deps].stdlib`, so a consumer missing a declared
  leaf still compiles and the check passes vacuously.

Gates: pin-drift · version consistency · `lib/` vs snapshot · format (src and
tests) · lint · vet · build with 0 warnings · smoke exits 42 · test · fuzz ·
bench · `coverage --min 16` · `distlib --all --check` · regeneration leaves no
tree diff · consumer-check.

## Known gaps

1. **`tests/ganita.fcyr` and `tests/ganita.bcyr` are `cyrius init` scaffolds** —
   the fuzz harness does no fuzzing, the bench measures a no-op. Both report
   PASS, so the two CI gates that run them are vacuous until the harnesses are
   real.
2. **The 1.1.0 f32 tier has no test** (`math_f32.cyr` 0/23), including the
   `_f32_key` sign-magnitude transform that 1.1.0 itself called "the whole
   correctness story" — and whose failure mode is precisely one that passes
   naive testing. `linalg.cyr` is 2/26.
3. **`lib/ganita.cyr` is ganita's own fold vendored back into ganita's own
   `lib/`** — new at this pin, because `lib sync --full` copies the whole
   snapshot and cyrius now carries the ganita fold. Nothing in `src/`,
   `tests/`, or `cyrius.cyml` includes it, so it is inert, but it defines the
   same symbols as `src/`: a last-definition-wins hazard waiting for someone to
   include it. Deleting it is not durable (`--full` re-adds it on every bump);
   the durable fix is upstream, a `lib sync` self-exclusion. bayan carries the
   identical gap.
4. **`README.md` is stale** — still describes the pre-1.1.0 surface.

## Dependencies

Direct (`cyrius.cyml [deps].stdlib`): string, fmt, alloc, io, vec, str,
syscalls, assert, bench, **math**. The transcendental fns lower `f64_exp` /
`f64_ln` to software polyfills (`_f64_exp_polyfill`, …) that live in stdlib
`math.cyr` — consumers must keep `math` in scope alongside ganita.

No sibling `[deps.NAME]` entries, so `cyrius deps` writes no `cyrius.lock`.

## Consumers

- **cyrius** — folds `dist/ganita.cyr` → `lib/ganita.cyr`. The 6.5.28 snapshot
  carries ganita **1.1.0**; 1.1.1 is a toolchain/CI release with no API change.
- **ranga** (image-processing port) — drove the 1.1.0 f32 tier.
- Downstream repos using matrix/linalg/advanced-math migrate to `ganita_*` on
  re-pin (aliases bridge the window).

## Next

See [`roadmap.md`](roadmap.md). bayan (data formats) is the sibling carve, at
**1.4.2** on the same 6.5.28 pin; Phase E (the stdlib data/math carve) closes
with ganita.
