# ganita — Current State

> Refreshed every release. CLAUDE.md is preferences/process/procedures
> (durable); this file is **state** (volatile).
> Last refreshed: 2026-09-01.

## Version

**1.2.0** — the f32 arithmetic tier (`ganita_f32_add` / `_sub` / `_mul` / `_div`) in
native single precision, `ganita_f32_lerp` de-widened onto it, and every public fn
documented so `cyrius audit` exits 0. Toolchain pin 6.5.29 → **6.5.36**. 243 assertions
(was 227).

**1.1.4** — `ganita_f64_pow`'s domain. It was `exp(y·ln base)` and nothing
else, so every base ≤ 0 returned NaN: `pow(0,2)` and `pow(-2,3)` are ordinary
defined operations and both came back NaN silently. Zero, negative-with-integral
-exponent, and `x^0` are now handled ahead of the exp/ln path; a non-integral
exponent on a negative base stays NaN because that is correct. 227 assertions.

**1.1.3** — `linalg.cyr` gets a test suite. It was the largest untested surface
in the repo at **2/26** — every decomposition and solver shipped unverified —
and is now **26/26** with 90 new assertions. Repo coverage 37% → **80%**.
Found and filed, not fixed: `fmt_float` drops the carry when a fraction rounds
up to 1.0, so a correct near-integer result prints as if it were wrong.

**1.1.2** — the f32 tier gets a test suite, and it found two bugs.
`math_f32.cyr` was **0/23 referenced** — `tests/ganita.tcyr` never even included
it. Now 23/23, with 95 new assertions; overall coverage 16% → **37%**, 7/7 files
referenced. Fixed: `ganita_f32_cbrt(0)` returned NaN (zero reached `pow`, and
`ln(0)` is `-inf`). Found and filed, not fixed: `ganita_f64_pow` is NaN for a
zero or negative base.

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

- **Cyrius pin**: `6.5.36` (`cyrius.cyml [package].cyrius`, since 1.2.0).
  `cyrius version` reports `manifest-pin: 6.5.36` with no drift line, and the
  `./lib/ shadows version-pinned ...` warning 1.1.4 shipped with is gone —
  `cyrius lib sync --full` re-copied all 108 files from the 6.5.36 snapshot.
- **`lib/` matches the pin exactly**: 108 files, 0 differ. Verify by comparing
  the trees, not by trusting `cyrius lib sync --full`'s exit code.
- ✅ **The 1.1.4 CI blocker is retired.** 6.5.36 is published, so the install step
  resolves. The paragraph below is kept as the record of what 1.1.4 shipped into.
- ⛔ **(1.1.4, historical) 6.5.29 was not published as a GitHub release.** CI hands the pin to
  `scripts/install.sh`, which downloads
  `cyrius-<pin>-x86_64-linux.tar.gz`; that asset 404s today, so **CI fails at
  the install step until the release ships**. 1.1.4 was verified against the
  locally installed 6.5.29. Re-verify against the tarball when it lands — a
  local install and a release can differ, which is exactly what bit bayan 1.4.2.
- **`lib/` grew 98 → 108 files** at 1.1.1's 6.5.28 bump: `unicode/` (7 files)
  plus the macOS `async`/`thread` variants. None is in `[deps].stdlib`; they
  ride along because `--full` vendors the whole snapshot.
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
- `dist/ganita.cyr` — regenerated via `cyrius distlib` at 1.2.0 on released
  6.5.28. This is the artifact folded into
  `cyrius/lib/ganita.cyr`.
- `dist/ganita.deps` — 7 stdlib leaves: `syscalls string alloc fmt vec str math`.
  Verified sufficient by `scripts/consumer-check.sh` (`str` is over-declared but
  harmless).

## Tests

- `tests/ganita.tcyr` — matrix dims + identity + **CWE-190 dimension guard** +
  binomial/fibonacci + `f64_tanh` saturation + alias parity + **the full f32
  tier** (1.1.2) + **the full linalg surface** (1.1.3). **227 assertions,
  green** on released 6.5.28.

  The linalg block asserts **properties**, not transcribed outputs — `A·A⁻¹ = I`,
  `Qᵀ·Q = I`, `L·Lᵀ = A`, `U·Σ·Vᵀ = A`, `Σλ = trace`, `Πλ = det`, `Πσ = |det|`,
  Moore–Penrose `A·A⁺·A = A` — so they survive a reimplementation and cannot be
  satisfied by a plausible-looking wrong answer. `mat_eq` is the comparison tool
  for most of them, so both its polarities are pinned first; an `eq` that always
  returned 1 would make the rest vacuous. Mutation-verified: forcing the LU
  pivot sign fails 2, deleting Cholesky's positive-definite check fails 1, and
  making QR return an identity `Q` fails 6 — including both least-squares
  assertions, the suite noticing that `least_squares` is built on QR.

  **The f32 block is mutation-verified**, which matters because 1.1.0 named the
  exact trap: IEEE-754 is sign-magnitude, so raw patterns order correctly only
  among non-negatives, and pixel data *is* non-negative — a naive unsigned
  compare passes every plausible test. Replacing `_f32_key` with the naive
  `b & 0xFFFFFFFF` fails **12** assertions; removing `cbrt`'s sign split fails
  exactly 2, both negative-input, while every positive still passes. The suite
  also states the trap directly (`-1.0f` sorts *below* `-2.0f`; negatives sort
  *above* positives) so a reader sees why those cases discriminate.

  Also pinned: signed zeros and infinities through min/max/sign/abs/neg;
  high-32 hygiene (a dirty high half must not leak into a result);
  floor/ceil/trunc at `±2.5` where all three differ; `sqrt(2) = 0x3FB504F3`,
  the correctly-rounded single; and that **`round` is half-to-EVEN**, unlike
  C's `roundf` — a porting hazard worth a standing assertion.
- `src/main.cyr` — full-bundle compile smoke (exits 42).
- Deep per-module coverage stays in cyrius's `matrix`/`linalg`/`math` `.tcyr`
  suite.

### Coverage

`cyrius coverage` — **105/131 fns (80%)**, 7/7 files referenced (22/131 and 4/7
before 1.1.2). A floor, not a correctness proof, but the two carved tiers are
now fully exercised in-repo:

| Module | Referenced |
|---|---|
| `linalg.cyr`        | **26/26** |
| `math_f32.cyr`      | **23/23** |
| `matrix.cyr`        | 10/14 |
| `_compat.cyr`       | 40/53 |
| `math_advanced.cyr` | 4/13 |

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
bench · `coverage --min 80` · `distlib --all --check` · regeneration leaves no
tree diff · consumer-check.

## Known gaps

1. **`tests/ganita.fcyr` and `tests/ganita.bcyr` are `cyrius init` scaffolds** —
   the fuzz harness does no fuzzing, the bench measures a no-op. Both report
   PASS, so the two CI gates that run them are vacuous until the harnesses are
   real.
2. **`fmt_float` drops the carry when a fraction rounds up to 1.0** —
   `fmt_float(2.9999999, 6)` prints `2.1000000` (seven fraction digits). Display
   only, but near-integer results are routine after a decomposition, so correct
   answers read as wrong ones. cyrius stdlib, vendored. Filed:
   [2026-08-19](issues/2026-08-19-fmt-float-missing-carry-on-round-up.md).
   ganita's tests assert numerically, never on printed text, so they are
   unaffected.
3. **`math_advanced.cyr` is 4/13** — the remaining in-repo coverage gap now that
   the f32 and linalg tiers are done. Its deep coverage lives upstream in
   cyrius's `math` `.tcyr` suite.
4. **`lib/ganita.cyr` is ganita's own fold vendored back into ganita's own
   `lib/`** — new at this pin, because `lib sync --full` copies the whole
   snapshot and cyrius now carries the ganita fold. Nothing in `src/`,
   `tests/`, or `cyrius.cyml` includes it, so it is inert, but it defines the
   same symbols as `src/`: a last-definition-wins hazard waiting for someone to
   include it. Deleting it is not durable (`--full` re-adds it on every bump);
   the durable fix is upstream, a `lib sync` self-exclusion. bayan carries the
   identical gap.
5. **`README.md` is stale** — still describes the pre-1.1.0 surface.

## Dependencies

Direct (`cyrius.cyml [deps].stdlib`): string, fmt, alloc, io, vec, str,
syscalls, assert, bench, **math**. The transcendental fns lower `f64_exp` /
`f64_ln` to software polyfills (`_f64_exp_polyfill`, …) that live in stdlib
`math.cyr` — consumers must keep `math` in scope alongside ganita.

No sibling `[deps.NAME]` entries, so `cyrius deps` writes no `cyrius.lock`.

## Consumers

- **cyrius** — folds `dist/ganita.cyr` → `lib/ganita.cyr`. The 6.5.28 snapshot
  carries ganita **1.1.0**; 1.1.1 (toolchain/CI), 1.1.2 (f32 tests + the
  `cbrt(0)` fix), 1.1.3 (linalg tests) and 1.1.4 (the `f64_pow` domain fix) are
  not folded yet. **cyrius ships the `f64_pow` NaN defect under that plain name**
  via the fold's `_compat` alias, so the refold is worth scheduling.
- **ranga** (image-processing port) — drove the 1.1.0 f32 tier.
- Downstream repos using matrix/linalg/advanced-math migrate to `ganita_*` on
  re-pin (aliases bridge the window).

## Next

See [`roadmap.md`](roadmap.md). bayan (data formats) is the sibling carve, at
**1.4.2** on the same 6.5.28 pin; Phase E (the stdlib data/math carve) closes
with ganita.
