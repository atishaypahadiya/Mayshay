# Phase 3, Task A — corpus collection and `@media` evaluation

Dated 2026-08-27. Task A runs **before** any layout work, for a measured
reason recorded below.

## Why this came first

Phase 2 ended with a display census that looked finished and was not
measuring the pages. Two gaps, found in sequence:

1. **No external CSS had ever been fetched.** `data/corpus/` held three
   hand-saved HTML files and no stylesheets, so every figure through Phase 2
   reflected the UA sheet plus in-document `<style>` blocks. Hacker News
   ships *zero* in-document CSS, so its entire display distribution was our
   own UA sheet.
2. **At-rules were counted and skipped.** Once the stylesheets were
   collected, Hacker News still showed a display delta of exactly zero — and
   the reason was that all six `display` declarations in `news.css` sit
   inside `@media` blocks. Measured by byte volume, 51% of that page's CSS
   and 46% of Wikipedia's was inside at-rules the cascade never entered.

Either gap alone would have made "how much `flex` is on real pages?"
unanswerable, and both were invisible from the census output.

## What the at-rules actually were

Counted across all three pages, recursing into nested at-rules:

| at-rule          | count | bytes   | share of that page's CSS |
|------------------|------:|--------:|--------------------------|
| `@media` (HN)    |    12 |   3,745 | 51.0%                    |
| `@media` (wiki)  |   102 | 115,939 | 46.4%                    |
| `@supports` (wiki) |  73 |  29,978 | 12.0%                    |
| `@counter-style` |     3 |     398 | 0.2%                     |

**Zero `@keyframes` and zero `@font-face`.** Nothing in the skipped volume
was animation or font loading — it was all layout-relevant, which is what
made evaluating `@media` worth doing before writing a layout engine.

## Scope

Evaluated: media types `all` / `screen`, the `only` and `not` keywords,
`and`, comma-separated lists, `width` / `min-width` / `max-width`,
`height` / `min-height` / `max-height`, `orientation`, and lengths in
absolute units plus `em`/`rem` against the initial 16px.

Recorded and **not** evaluated, per the `link_stylesheets_skipped`
discipline — counted by name, never silently dropped:

* `print` and every other media type (`media_types_skipped`,
  `media_type_<name>`)
* `hover`, `pointer`, `prefers-*`, `device-*`, resolution — anything needing
  device state (`media_queries_unsupported`, `media_feature_<name>`)
* `calc()` in a feature value, MQ4 range syntax, `or`
* `@supports`, which stays skipped (`at_rules_skipped`, `at_rule_supports`)

One deliberate spec deviation: a query naming an unsupported feature is
false **even under `not`**. The spec makes an *unknown* feature false, so
`not (unknown)` is true — but ours is "unsupported", not "unknown".
`prefers-color-scheme` is a feature real browsers support, and inverting our
ignorance of it would *apply* CSS meant for a state we cannot observe.
False in both directions never over-applies.

The viewport is opt-in: `style_document(document, css)` with no viewport
behaves exactly as it did in Phase 2. That is what keeps pre-`@media`
figures reproducible rather than silently restated.

## `calc()`, priced and then taken

`calc()` appears in 25 of 114 `@media` preludes in the corpus, all
breakpoints of the shape `calc(1120px - 1px)`. The cost of skipping it was
measured first, in a shadow build, before deciding:

|                          | without `calc()` | with |
|--------------------------|-----------------:|-----:|
| queries not evaluated    |               40 |   15 |
| `@media` blocks matched  |               43 |   46 |
| Wikipedia `flex` elements|              204 |  205 |

Three blocks and about ten elements — small, but the better reason to take
it is that it makes the remaining 15 unevaluated queries a clean "these
need device state" (`prefers-color-scheme` x14, `prefers-reduced-motion`
x1) rather than a mix of two unrelated causes.

Only the additive length form is evaluated: `calc(A + B - C)`. Nesting,
`*`, `/`, percentages, bare numbers, and malformed operator runs are all
recorded unsupported, because a wrong breakpoint silently applies or
withholds a whole block of CSS.

## Results

Display census at 1280x1024, all three pages, 8,593 elements. `ua` is the
UA sheet alone; `ext` adds the collected stylesheets with at-rules still
skipped; `media` adds `@media` evaluation.

| display        |   ua |  ext | media | share |
|----------------|-----:|-----:|------:|------:|
| inline         | 6306 | 6155 |  5829 | 67.8% |
| block          | 1324 | 1320 |  1242 | 14.5% |
| none           |  267 |  385 |   519 |  6.0% |
| table-cell     |  401 |  401 |   401 |  4.7% |
| table-row      |  218 |  218 |   218 |  2.5% |
| flex           |    2 |    4 |   205 |  2.4% |
| inline-block   |   22 |   24 |    90 |  1.0% |
| table          |   26 |   29 |    29 |  0.3% |
| inline-flex    |    0 |   27 |    28 |  0.3% |
| table-row-group|   24 |   24 |    24 |  0.3% |
| table-caption  |    1 |    4 |     4 |  0.0% |
| grid           |    0 |    0 |     2 |  0.0% |
| list-item      |    2 |    2 |     2 |  0.0% |

**flex family 233 (2.71%), grid family 2 (0.02%).**

Wikipedia's `flex` count went 2 → 4 → 205: a 51x increase from evaluating
`@media` alone, and the single strongest argument for having done this
before planning layout. `grid` exists only inside a `@media` block.

Hacker News still shows a zero delta at this viewport, and that is now the
*correct* answer rather than an artifact: its `display` rules live in
`@media only screen and (min-width:300px) and (max-width:750px)`, which a
1280px viewport genuinely does not match.

## Stylesheet ordering

External sheets now enter the cascade at the position their `<link>`
occupies, via `style_document(..., external_css=...)`. They previously all
cascaded before every in-document `<style>`, whatever the markup said —
and source order is the cascade's last tiebreak, so that silently picked
the winner for any two declarations of equal origin, importance and
specificity, which in real CSS is common rather than a corner case.

The corpus does **not** exercise the fix: all three pages happen to place
every `<link>` before every `<style>` (Wikipedia is `LLSSSSSSSSSSSSSSSSSS`),
so the old and new orders coincide and every figure above is unchanged by
it. That is a verified coincidence, not evidence the change is inert — the
unit tests in `test_cascade.py` are what stand behind it.

## Reproducing

    .venv/bin/python scripts/collect.py \
        https://example.com/ https://news.ycombinator.com/ \
        https://en.wikipedia.org/wiki/HTML
    .venv/bin/python scripts/display_report.py
    .venv/bin/python scripts/style_report.py

See `docs/corpus.md` for the corpus layout and the snapshot boundary.
