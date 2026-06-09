# Getting started with ganita

## Build

```sh
cyrius deps                              # resolve dependencies
cyrius build src/main.cyr build/ganita    # compile
cyrius test                              # run [build].test + tests/*.tcyr
```

## Layout

- `src/main.cyr` — entry point. Top-level `var r = main(); syscall(SYS_EXIT, r);`.
- `src/test.cyr` — top-level test entry referenced by `cyrius.cyml [build].test`. Add unit cases here or in `tests/ganita.tcyr`.
- `tests/ganita.tcyr` — primary test suite (`cyrius test` auto-discovers).
- `tests/ganita.bcyr` — benchmarks (`cyrius bench`).
- `tests/ganita.fcyr` — fuzz harness (`cyrius fuzz`).

## Adding a feature

1. Edit `src/main.cyr` (or add a new module and `include` it).
2. Add a test case to `tests/ganita.tcyr`.
3. Run `cyrius test`.
4. Bump `VERSION` and add a CHANGELOG entry before tagging.

See [`../adr/template.md`](../adr/template.md) when a non-trivial design choice deserves an ADR.
