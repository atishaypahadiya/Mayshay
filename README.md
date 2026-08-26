# Mayshay

A browser engine written from scratch in Python, plus a structural analysis
of the real web built from metrics the engine emits.

## Pipeline
fetch -> tokenize -> tree build -> style -> layout -> paint

## Status
Phase 1: HTML tokenizer and tree builder.

## Test corpus

Conformance tests run against [html5lib-tests](https://github.com/html5lib/html5lib-tests),
vendored as a submodule under `tests/html5lib-tests`:

    git submodule update --init

The submodule is **pinned to `9329e64`**, not tracking `master`. Upstream moved
its tree-construction fixtures to web-platform-tests and deleted them in
`224991e`; `9329e64` is the last commit that still carries all 60 `.dat` files.
Do not advance the pin with `git submodule update --remote` — it will empty the
corpus, and the conformance suite will skip rather than fail, so the loss is
easy to miss.
