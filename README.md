# Mayshay

A browser engine written from scratch in Python, plus a structural analysis
of the real web built from metrics the engine emits.

## Pipeline
fetch -> tokenize -> tree build -> style -> layout -> paint

## Status

| phase | state |
|---|---|
| 1. HTML to DOM | done (`phase-1`) |
| 2. CSS to a styled tree | done (`phase-2`) |
| 3. Layout | done (`phase-3`) except Task H, 12 corpus pages that crash |
| — floats | **deferred indefinitely**, with the cost measured |
| 4. Paint | not started — `src/mayshay/paint/` is empty |
| 5. Crawler | not started — `src/mayshay/net/` is empty |
| 6. The analysis | not started — the actual deliverable |

Layout covers block, inline and line boxes, text measured against a pinned
Liberation Sans, CSS 2.1 tables and a Flexbox 1 subset. Floats are not
implemented and are not scheduled: they gate a median 6.5% of boxes across
the 79-page corpus, and about a third on government and non-Latin pages,
which therefore render with missing content. See
`docs/plans/2026-08-29-phase-3-task-i-floats.md`.

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
