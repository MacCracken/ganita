# ganita — Current State

> Refreshed every release. CLAUDE.md is preferences/process/procedures
> (durable); this file is **state** (volatile).
> Last refreshed: 2026-09-08 (the P(-1) backlog, repaired).

## Version

**1.2.4** — **the P(-1) backlog, repaired.** Four of the five 1.2.3 filings
closed, plus five of six items in the fifth. **`LINALG_EPS` is a RELATIVE factor**
now, so singularity verdicts no longer depend on the caller's units — a 2×2
identity scaled by 1e-20 read *singular / null / cond −1.0* from `det`/`inv`/
`condition` while `rank` said full rank, i.e. the library contradicted itself.
**SVD is one-sided Jacobi** and never forms AᵀA: on `[[1,1],[1,1+e]]` the
invariant σ₁σ₂ = |det| was *exactly 0* at e=1e-9 and is now 1.000000. **`pow` on
an integral exponent is exact** (`pow(7,2)` was 48.999… and floored to 48).
`hypot` scales before squaring; `acos` uses the half-angle form; sinh/tanh/atanh
get small-|x| series; f32 min/max are IEEE minNum/maxNum and the tier finally
ships `lt`/`le`/`gt`/`ge`. Measured: **mat_mul 3.34×**, rank 1.61×. 433
assertions (was 322).

**1.2.3** — **P(-1) hardening sweep.** Seven audit lenses over `src/`, each
adversarially verified, every finding reproduced by a program that was built and
run: **90 confirmed**, 0 refuted. The profile was uniform — *a function derives
its loop bounds from one argument and never looks at the others* — and it
produced out-of-bounds reads and writes across roughly twenty functions, all on
matrices `ganita_mat_new` had accepted. Closed the class. Also: `mat_eq`
reported NaN as **equal**, and it is the suite's own oracle; `cholesky` accepted
semi-definite input and then produced NaN through `cholesky_solve` while
reporting success; `asinh` was wrong in **sign** for large negative x; `binomial`
wrapped i64 from n=62 and could loop for 560 years; `f32_sin`/`_cos` returned
their argument above 2^63. `eigen_sym` is now **O(n³), was O(n⁴)** — 6.5× at
n=200 with bit-identical eigenvalues. One failure vocabulary
([ADR 0001](../adr/0001-failure-vocabulary.md)); `eigen_sym`'s non-convergence
code moved -1 → -3. 322 assertions (was 260). Full report:
[`docs/audit/2026-09-07-v1.2.3-audit.md`](../audit/2026-09-07-v1.2.3-audit.md).

**1.2.2** — the two open filings, closed. **`ganita_mat_least_squares` no longer
forms an `m × m` Q**: it reached the solution through `ganita_mat_qr`, whose
contract is an explicit square Q, so an ordinary `5793 × 3` design (0.05% of the
element cap) asked for a 33,558,849-element Q just *over* it — `mat_new` returned
0, nothing checked it, and qr stored through the null. **High severity: a null
write reachable from a public API with in-contract arguments.** The reflectors are
now applied to `b` in the same sweep that reduces A to R, which *is* `Q^T·b`, so
peak memory is O(m·n) and the ≈5792 ceiling is gone rather than reported. Every
internal allocation across `matrix.cyr` + `linalg.cyr` is now checked (20 fns),
each reporting in its own vocabulary — **NaN for `det` and `condition`**, whose
`0.0` and `-1.0` are real answers about the matrix. The `fmt_float` filing closed
with no ganita change: cyrius fixed it at 6.5.30 and 1.2.1's re-vendor brought it
in. 260 assertions (was 243).

**1.2.1** — toolchain. Cyrius pin 6.5.36 → **6.6.0**, `lib/` re-vendored to an
exact match (108 → **109** files, `hashseed.cyr` is new), `dist/` regenerated at
1.2.1. **No `src/` change, no behavioural change** — the same 243 assertions,
green on 6.6.0. One repair the bump forced: 6.6.0 applies the docs check across
the whole audit scope (`src` **and** `tests`), so `cyrius audit` went from green
to `15 undocumented public fns`, all test-harness helpers. The rule is
positional — the doc comment must sit on the line *immediately* above `fn`, so a
section banner documents only the first fn beneath it. All 15 now carry their
own line and audit exits 0 again.

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

- **Cyrius pin**: `6.6.0` (`cyrius.cyml [package].cyrius`, since 1.2.1).
  `cyrius version` reports `manifest-pin: 6.6.0` with no drift line, and no
  `./lib/ shadows version-pinned ...` warning — `cyrius lib sync --full`
  re-copied all 109 files from the 6.6.0 snapshot.
- **`lib/` matches the pin exactly**: 109 files, 0 differ. Verify by comparing
  the trees against `~/.cyrius/versions/<pin>/lib`, not by trusting
  `cyrius lib sync --full`'s exit code.
- ⚠ **6.6.0 audits docs in `tests/` too.** The docs check used to reach only
  `src/`; at 6.6.0 it covers the whole audit scope, which the tool prints as
  `scope: src tests`. The pin bump alone therefore turns a green `cyrius audit`
  red on any repo whose harness helpers are undocumented — 15 of them here. The
  rule is **positional**: the comment must be the line immediately above `fn`, so
  a `# --- section banner ---` documents only the first fn under it. `ci.yml`
  does not run `cyrius audit`, so this surfaces locally, not in CI.
- ✅ **The 1.1.4 CI blocker is retired.** The pin is published, so the install step
  resolves. The paragraph below is kept as the record of what 1.1.4 shipped into.
- ⛔ **(1.1.4, historical) 6.5.29 was not published as a GitHub release.** CI hands the pin to
  `scripts/install.sh`, which downloads
  `cyrius-<pin>-x86_64-linux.tar.gz`; that asset 404s today, so **CI fails at
  the install step until the release ships**. 1.1.4 was verified against the
  locally installed 6.5.29. Re-verify against the tarball when it lands — a
  local install and a release can differ, which is exactly what bit bayan 1.4.2.
- **`lib/` grew 98 → 108 files** at 1.1.1's 6.5.28 bump (`unicode/`, 7 files,
  plus the macOS `async`/`thread` variants) and **108 → 109** at 1.2.1's 6.6.0
  bump (`hashseed.cyr`). None is in `[deps].stdlib`; they ride along because
  `--full` vendors the whole snapshot.
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
functions prefixed `ganita_`. Regenerated from the tree 2026-09-07:

**Allocation-failure contract (1.2.2).** Every internal `ganita_mat_new` / `alloc`
is checked, and each function reports in its own return vocabulary: **null** for
the matrix- and array-returning fns, **-1** for the status ones (**-2** for
`eigen_sym`, whose `-1` means max-iterations), **-1** for `rank`, and **NaN** for
`det` and `condition` — `0.0` and `-1.0` are answers those two already give about
the *matrix* and must not be overloaded to mean the run failed. Failures are
reachable with inputs well inside the cap whenever the working factor is derived
and larger: `det`/`inv` take n from the **row** count, `rank`/`condition`/
`pseudo_inv` build `cols × cols` factors, and `mat_mul` can be handed two legal
operands whose product is not.


| Module | Lines | Public fns | Canonical prefix |
|--------|-------|-----------|------------------|
| `src/linalg.cyr`        | 1404 | 26 | `ganita_mat_*` (extends matrix) |
| `src/matrix.cyr`        | 268 | 14 | `ganita_mat_*` |
| `src/math_advanced.cyr` | 281 | 13 | `ganita_f64_*` / `ganita_fibonacci` / `ganita_binomial` |
| `src/math_f32.cyr`      | 239 | 27 | `ganita_f32_*` |

- `src/_compat.cyr` — 53 back-compat aliases (legacy names → `ganita_*`).
  Single-pass order: matrix → linalg → math_advanced → math_f32 → `_compat`
  last, since its aliases reference every `ganita_*` symbol.
- `dist/ganita.cyr` — regenerated via `cyrius distlib` at 1.2.3 on 6.6.0. This is the artifact folded into `cyrius/lib/ganita.cyr`. Regeneration
  is idempotent.
- `dist/ganita.deps` — 10 stdlib leaves: `syscalls string alloc fmt vec str math
  io assert bench`. Verified sufficient by `scripts/consumer-check.sh` (`str` is
  over-declared but harmless).

## Tests

- `tests/ganita.tcyr` — matrix dims + identity + **CWE-190 dimension guard** +
  binomial/fibonacci + `f64_tanh` saturation + alias parity + **the full f32
  tier** (1.1.2) + **the full linalg surface** (1.1.3) + **the least-squares
  regression and the allocation-failure contract** (1.2.2) + **the shape/range
  preconditions, NaN-fails-closed, and the math domain fixes** (1.2.3).
  **322 assertions, green** on 6.6.0.

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

  **The 1.2.2 linalg additions are mutation-verified too.** The least-squares
  assertion is on the *fitted coefficients* of a 5793-sample quadratic that lies
  exactly in the column space, not on "did not crash" — restoring the `m × m` Q
  kills the suite with the filed SIGSEGV, and removing any single null check from
  the allocation sweep does the same. Each allocation-failure assertion is paired
  with one that the **input** was legal, which is the whole content of the report:
  the caller's matrix was never the problem.

  Also pinned: signed zeros and infinities through min/max/sign/abs/neg;
  high-32 hygiene (a dirty high half must not leak into a result);
  floor/ceil/trunc at `±2.5` where all three differ; `sqrt(2) = 0x3FB504F3`,
  the correctly-rounded single; and that **`round` is half-to-EVEN**, unlike
  C's `roundf` — a porting hazard worth a standing assertion.
- `src/main.cyr` — full-bundle compile smoke (exits 42).
- Deep per-module coverage stays in cyrius's `matrix`/`linalg`/`math` `.tcyr`
  suite.

### Coverage

⚠ **`cyrius coverage` over-reports, and the CI gate used to sit on it.** The tool
credits a function whose name appears as a raw **substring** anywhere in the
scanned text, **comments included**. Every `_compat.cyr` alias name is a proper
substring of the canonical name it forwards to, so exercising `ganita_mat_sub`
silently credits `mat_sub` and `ganita_mat_submatrix` credits both. Reproduced
during the 1.2.3 sweep: appending **one comment line** naming `ganita_mat_print(`
— called nowhere in the repo — moved the reported total from 109/135 (80 %) to
111/135 (82 %). At 1.2.2 `ci.yml` gated on `--min 80` against a reported 80:
**zero margin, held up by the artifact.**

Two figures are now tracked, and CI gates on **both**:

| | 1.2.2 | 1.2.3 | gate |
|---|---|---|---|
| `cyrius coverage` (substring) | 109/135 (80 %) | **131/139 (94 %)** | `--min 94` |
| `scripts/coverage-honest.sh` (word boundary, comments stripped) | 72/135 (**53 %**) | **87/153 (56 %)** | `56` |

The honest count is the one to plan against. The tool's is kept as a ratchet
because it sees things a regex does not — but it is not the only gate, because it
is a number a comment can move.

Per module, honest count at 1.2.3 (the denominator now includes the private
helpers added by the sweep):

| Module | Referenced |
|---|---|
| `math_f32.cyr`      | 31/35 |
| `linalg.cyr`        | 26/31 |
| `matrix.cyr`        | 12/15 |
| `math_advanced.cyr` | 11/17 |
| `_compat.cyr`       | **5/53** |

`math_advanced.cyr` went 5/15 → 11/17 at 1.2.4: the accuracy repairs came with
assertions, which is where most of that came from.

**`_compat.cyr` was published as 40/53 and is really 5/53.** Anyone planning the
alias removal against "75 % exercised" was planning against nothing. All 53 were
re-verified by hand during the sweep to forward verbatim with matching arity and
argument order, so the risk is low — but it is untested, not tested.
`math_advanced.cyr` at 5/15 remains the largest genuinely dark public surface,
and it is exactly the module whose defects have historically been *silent*.

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

Gates (20 steps as of 1.2.3): pin-drift · version consistency · `lib/` vs
snapshot · format (src, tests **and examples**) · lint · vet · build with 0
warnings · smoke exits 42 · test · fuzz · bench · `coverage --min 85` ·
**`coverage-honest.sh 54`** · `distlib --all --check` · regeneration leaves no
tree diff · consumer-check · **examples build and run**.

Two of those are new at 1.2.3 and both exist because a gate was measuring the
wrong thing:

- **`coverage-honest.sh`** — `cyrius coverage` counts substrings including
  comments, so one comment line moved the old `--min 80` gate from 80 % to 82 %.
  Both figures are now gated; see Coverage above.
- **Examples build and run** — five real programs against the real API. Without
  it, an example that stopped being true would just sit there being wrong.

## Open filings

**One**, down from five. The 1.2.3 P(-1) sweep opened five; 1.2.4 closed four
outright and five of the six items in the fifth. Reasons are in each file and
summarised in [the 1.2.3 audit](../audit/2026-09-07-v1.2.3-audit.md).

| Severity | Filing | Status |
|---|---|---|
| MEDIUM | [`performance-backlog`](issues/2026-09-07-performance-backlog.md) | **Partially resolved at 1.2.4** — 5 of 6 items landed and are measured. What remains: `mat_inv`'s per-call scratch and the discarded transposes both need a public API change, and raising `GANITA_MAT_MAX_ELEMS` is still the policy question the 1.2.3 audit deferred. |

Four filings closed at 1.2.4 — the absolute `LINALG_EPS`, SVD via AᵀA, the f64
transcendental accuracy group, and the f32 NaN/inf group — all in
`issues/archived/` with resolution banners. The performance one is kept **open**
rather than archived: an open item in an archived folder is how a backlog quietly
disappears.

Closed at 1.2.2 and kept as history: the `ganita_mat_least_squares` null write and
`fmt_float`'s dropped carry (fixed upstream at cyrius 6.5.30). The repro
`repros/2026-08-23-least-squares-unchecked-q-alloc.cyr` stays as a regression
witness: exit 139 on 1.1.4 … 1.2.1, exit 0 from 1.2.2.

## Known gaps

1. **`tests/ganita.fcyr` is still a `cyrius init` scaffold** — the fuzz harness
   does no fuzzing. It reports PASS, so the CI gate that runs it is vacuous until
   the harness is real. (`tests/ganita.bcyr` grew real f32 benchmarks at 1.2.0;
   only its `bench_noop` floor is scaffold.)
2. **`math_advanced.cyr` is 4/13** — the remaining in-repo coverage gap now that
   the f32 and linalg tiers are done. Its deep coverage lives upstream in
   cyrius's `math` `.tcyr` suite.
3. **`lib/ganita.cyr` is ganita's own fold vendored back into ganita's own
   `lib/`** — new at this pin, because `lib sync --full` copies the whole
   snapshot and cyrius now carries the ganita fold. Nothing in `src/`,
   `tests/`, or `cyrius.cyml` includes it, so it is inert, but it defines the
   same symbols as `src/`: a last-definition-wins hazard waiting for someone to
   include it. Deleting it is not durable (`--full` re-adds it on every bump);
   the durable fix is upstream, a `lib sync` self-exclusion. bayan carries the
   identical gap. At the 6.6.0 pin it holds ganita **1.2.0** — one release behind
   `src/`, so it is also stale, not merely redundant.
4. **`README.md` is stale** — still describes the pre-1.1.0 surface.

## Dependencies

Direct (`cyrius.cyml [deps].stdlib`): string, fmt, alloc, io, vec, str,
syscalls, assert, bench, **math**. The transcendental fns lower `f64_exp` /
`f64_ln` to software polyfills (`_f64_exp_polyfill`, …) that live in stdlib
`math.cyr` — consumers must keep `math` in scope alongside ganita.

No sibling `[deps.NAME]` entries, so `cyrius deps` writes no `cyrius.lock`.

## Consumers

- **cyrius** — folds `dist/ganita.cyr` → `lib/ganita.cyr`. The 6.6.0 snapshot
  carries ganita **1.2.0**, so the `f64_pow` domain fix (1.1.4) and the native f32
  arithmetic tier (1.2.0) are both in. ⛔ **The refold is now worth scheduling.**
  1.2.1 was header-only, but the 1.2.0 fold ships the `mat_least_squares` null
  write under the plain `mat_least_squares` alias — so a cyrius consumer who never
  heard of ganita can SIGSEGV on an in-contract call, which is exactly how naad
  found it.
- **ranga** (image-processing port) — drove the 1.1.0 f32 tier.
- Downstream repos using matrix/linalg/advanced-math migrate to `ganita_*` on
  re-pin (aliases bridge the window).

## Next

See [`roadmap.md`](roadmap.md). bayan (data formats) is the sibling carve, at
**1.5.5** on the same **6.6.0** pin; Phase E (the stdlib data/math carve) closes
with ganita.
