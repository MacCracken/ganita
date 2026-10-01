# ADR 0003 — `ganita_f64_tan` reduces through stdlib math's private `_f64_rem_pio2`

**Status**: Accepted
**Date**: 2026-10-01
**Version**: 1.2.11

## Context

abaco asked for an f64 tangent (filing
[`2026-09-30-f64-tan-missing`](../development/issues/archived/2026-09-30-f64-tan-missing.md)).
Neither ganita nor stdlib `math` had one, so every consumer divided `f64_sin(x)` by
`f64_cos(x)`. That is two results within 1 ulp each and then a rounded division: up
to 2 ulp off, and correctly rounded at only about 68% of arguments.

A tangent that matches sin and cos everywhere needs their **argument reduction**:
`x = n·(π/2) + y` with `y` carried in two words, exact for every finite double up to
`DBL_MAX`. Past about 2^20·(π/2) that takes Payne–Hanek reduction against a table of
2/π bits. Stdlib `math` already has fdlibm's: `_f64_rem_pio2(x, yp)` in
`lib/math.cyr`, which `f64_sin` and `f64_cos` lower to on every target. It is
underscore-prefixed, so it is private by convention, and it first shipped in
**cyrius 6.6.9**. It is absent from 6.6.0–6.6.8.

ganita's bundle (`dist/ganita.cyr`) is consumed in two ways. cyrius folds it into
its own `lib/ganita.cyr`, which always ships next to a `lib/math.cyr` from the same
release. A few repos also vendor it directly on older stdlib pins (amuzesh, for
example, pins ganita 1.1.0 on cyrius 6.6.2).

## Decision

`ganita_f64_tan` (with its `f64_tan` alias and `ganita_f32_tan`, which widens onto it)
calls stdlib's `_f64_rem_pio2` for every argument above about π/4. It ports fdlibm's
`s_tan.c` / `k_tan.c` on top of it. **ganita now requires stdlib `math` from cyrius
6.6.9 or later for its tangent functions.** Every other function is unaffected.

## Consequences

- **Positive.** tan reduces exactly as sin and cos do, bit for bit. It is within
  1 ulp everywhere measured, and on every target with no table of its own. The
  1.2.11 sweep of every f32 value as an argument shows x86_64 and aarch64 agreeing
  on every result. ganita carries a kernel of about 60 lines, not a second copy of
  a 200-line reducer plus a 2/π table.
- **Negative: the dependency is on a private name.** If cyrius renames or reshapes
  `_f64_rem_pio2`, ganita's tangent stops compiling. The failure is at compile
  time, not a wrong answer at run time, and ganita's CI builds against the pinned
  snapshot, so a toolchain bump that breaks it shows up in CI first.
- **Negative: older stdlib pins.** Measured with the 6.6.0–6.6.8 toolchains and
  their own `lib/` (1.2.11 merged-tree review):
  - A consumer that never calls tan still builds and runs. Every other result is
    bit-identical to 6.6.9+. On x86_64, though, the build prints
    `warning: undefined function '_f64_rem_pio2'`. A CI that fails on any
    `^warning:` needs the pin moved to ≥ 6.6.9.
  - A consumer that calls any of the three tangent functions fails to compile:
    `refusing to emit binary with 1 reachable undefined function(s)`, naming
    `_f64_rem_pio2`. Forcing past it with `--allow-undef` gives a binary that traps
    (SIGILL) on the first argument with |x| > π/4. Do not do that.
- **Neutral.** The cyrius compiler has no version macro, so ganita cannot guard the
  call on the stdlib version. The requirement is documented in the README, the
  `math_advanced.cyr` header, `cyrius.cyml` and the CHANGELOG.

## Alternatives considered

- **Put `f64_tan` in stdlib `lib/math.cyr`**, next to `f64_sin` / `f64_cos`. The
  filing offered this as the alternative, and it is the cleaner long-term home.
  But it is a cyrius change, outside ganita's tree, and it would not reach any
  consumer before the next toolchain release. If stdlib gains a public tangent or a
  public reducer, ganita should forward to it and this ADR is superseded.
- **Carry ganita's own reducer** (a copy of fdlibm's `__ieee754_rem_pio2` and
  `__kernel_rem_pio2`, with the 2/π table). This makes ganita self-contained on every
  pin, but it duplicates the most intricate code in stdlib math, and the copy could
  drift from the one sin and cos use. A tan and a sin/cos that reduce differently
  disagree, past 2^20·(π/2), on which period an argument falls in. Rejected.
- **Reduce only for small arguments (Cody–Waite) and return NaN above a bound.**
  This is the 1.2.x f32 sin/cos mistake again: a guard that throws away correct
  answers. 1.2.9 removed exactly that. Rejected.
- **Keep the sin/cos quotient.** It is up to 2 ulp off, which is what the filing was
  about. Rejected.
