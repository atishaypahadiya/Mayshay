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
| 3. Layout | done (`phase-3`), including Task H: the 12 corpus pages that crashed were four defects, fixed in `dd31839` |
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

## How it's checked

- **The suite.** 7,158 tests pass on every push. The 72 expected failures are
  strict xfails, each naming the feature it waits on, so a fix that lands turns
  the suite red until its entry is deleted. The 11 skips need the collected
  corpus, which is gitignored, and run locally.
- **HTML conformance.** Of the html5lib tokenizer cases it runs (character
  references, doctypes, raw text), 5,691 of 5,707 pass. Tree construction is
  scoped to `tests1.dat`: 64 of 112 pass, and the other 48 wait on table modes
  (16), the adoption agency (14), rules missing inside the modes it has (11),
  select and frameset modes (5) and the tokenizer (2).
- **Text widths.** Advances come from the font's own `hmtx` table, and against
  Chrome 151 they agree to within one LayoutUnit (1/64 px), except where
  Chrome kerns. The table is in `docs/fonts.md`.
- **The merge gate.** Every page of the 79-page corpus must lay out without
  raising (`tests/layout/test_corpus_lays_out.py`). It checks termination, not
  correctness; the first run found 12 crashes that no unit test could.
- **Measurements that looked right.** `docs/measurement-hazards.md` records
  each figure on this project that was wrong while looking plausible, and the
  second measurement, taken a different way, that caught it.

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

The fixtures now live in web-platform-tests, under
`html/syntax/parsing/resources/`, where they are still edited. Checked on
7 Nov 2026 (wpt `0602407`): 9 of the 60 files differ from the pin, among them
`template.dat` and `search-element.dat`, and two are new,
`processing-instructions.dat` and `scripted_foster01.dat` (the `scripted/`
files are flattened to a `scripted_` prefix there). The conformance numbers
above are against the pin, the June 2026 state.
