# Corpus widening — 80 pages, two populations, one decision

Between Phase 3 and Phase 4. Not a phase: one task, whose output is a
number that scopes the next phase rather than any engine code.

Read `CLAUDE.md`, then `docs/corpus.md`, then
`docs/synthetic-only-coverage.md` — the register this task is supposed to
move — then `docs/measurement-hazards.md`.

## Why now, and why before the float/paint decision

Phase 3 shipped block layout, inline layout, tables and a flex subset
against **three pages**. What that corpus can say is bounded, and the
bound is now the loudest thing in the register:

* **19 of the 23 Task F register rows read zero.** Not "small" — zero.
* **All 233 flex elements are on one page.** Hacker News and example.com
  contribute none.
* **`flex-direction: column` has zero occurrences anywhere in the corpus.**
  Six `column` declarations exist and not one wins. That is half of Task
  F's scope, and specifically the half whose main size is a *height* and
  therefore runs a second code path that no corpus page has ever entered.
* **29 of 233 flex containers reach the algorithm.** The other 172 are
  behind floats and absolute positioning.

Nothing in that set can scope Phase 4 or price floats. The float question
in particular is currently answerable only as "172 of 201 boxes on
Wikipedia", which is one page's design language, not a fact about the web.

`scripts/collect.py` already exists and already does the hard parts
(robots, rate limiting, `@import` one level deep, an attributable
manifest). This is a URL list, three collector fixes, and a re-run — not
Phase 5's crawler, which still does not exist and is still not being
written here.

## The decision this buys, pre-registered

The thresholds go in **before** the numbers, so the rule cannot be fitted
to the answer it produces. Recorded here to be argued with now, not after.

**Metric.** Per page: the share of element boxes that are inside a float
or an absolutely-positioned subtree, and therefore never laid out. Report
the **distribution across pages** — median, quartiles, max, and the count
of pages above each threshold. Never the mean: one Wikipedia in a sample
of 80 moves a mean and does not move a median, and the whole reason for
this task is that a single page has been standing in for the web.

| median page has | ruling |
|---|---|
| **≥ 10%** of boxes gated | floats are Phase 3's real remaining work; paint waits |
| **< 3%** gated, and the mean is carried by ≤ 3 pages | Wikipedia artifact; **paint goes next** |
| 3–10% | no auto-ruling. Report it and decide by hand |

**Per stratum, and the ruling reads the strata before the pool.** If
government sites sit at 15% and everything else at 2%, that is not a 3%
median to be waved through — it is a finding that floats gate one site
type, and the ruling is made on that shape rather than on the pooled
number. A pooled median that no stratum resembles is reported as such.

**Second gate, reported alongside:** the share of *pages* on which at least
one flex container or table is gated behind a float or absolute ancestor.
A low box share with a high page share means floats block a little content
on most sites, which is a different problem from blocking a lot on one.

**A third number that is not a gate but will be quoted:** how many pages
lay out at all — see "SPA shells are a finding" below.

## Pre-flight: three defects that only fire above three URLs

All three confirmed by execution, not by reading. Each is invisible at
three hand-picked URLs and near-certain at eighty.

### 1. Slug collisions silently overwrite a page

`slug_for` builds the directory name from netloc + path, and **drops the
query string entirely**. Executed:

    example.com-a-b      <- https://example.com/a/b
    example.com-a-b      <- https://example.com/a/b/
    shop.example.com-p   <- https://shop.example.com/p?id=1
    shop.example.com-p   <- https://shop.example.com/p?id=2

The second fetch overwrites the first, manifest included, so nothing on
disk records that a page was lost. You ask for 80 and get 78, with no
error and no line in any report. E-commerce and forums — two of the strata
below — are exactly the query-string-bearing site types.

Also: a long path produces a **185-character** slug, under APFS's 255 but
not by much, and a longer one truncates or fails depending on the
filesystem.

**Fix.** Include the query in the slug's input. Cap the readable part at
100 characters. Append a 7-hex-character digest of the **full URL** to
every slug, always — not only on collision, so slugs are stable and one
scheme covers both cases. Then, before writing, if the directory exists
with a manifest whose `source_url` differs, **fail the URL loudly** rather
than overwrite: the digest makes that unreachable, which is the point of
keeping the check.

### 2. A robots-disallowed page writes a loadable manifest with no HTML

`collect_page` writes a manifest and returns when robots disallows. That
manifest has `html.file = "page.html"` and no `page.html` on disk.
Executed against the loader:

    load_pages returned: ['disallowed-page']
      html() raised: FileNotFoundError ... /disallowed-page/page.html

And because `html_bytes` defaults to `0` and `load_pages` sorts smallest
first, the unloadable page sorts **first** — so one disallowed host
crashes every report script on its first iteration. At three
hand-chosen URLs this never fired.

**Fix.** Record the disallowed page in the manifest with `html.file: null`,
and have `load_page` refuse to construct a `CorpusPage` without HTML —
returning it instead on a new `Corpus.unfetched` list carrying the reason.
Reports then say "78 of 80 pages, 2 not fetched (robots)" rather than
crashing or, worse, quietly measuring 78 and printing 80.

### 3. A failed fetch leaves no trace at all

`page_dir.mkdir()` runs *before* `response.raise_for_status()`, so a 404
leaves an empty directory and no manifest. `load_pages` skips directories
without a manifest. Executed: two directories on disk, one a failed fetch,
`load_pages` returns one page and the attempt is invisible.

This is the unstated-denominator hazard at the corpus boundary: every
downstream percentage would be over "pages that happened to fetch", while
every doc would say "the corpus".

**Fix.** `collect.py` writes a **collection manifest** for the whole run —
`data/corpus/<collection>/collection.json` — with one row per URL
attempted: url, stratum, selection reason, status (`ok`,
`robots-disallowed`, `http-NNN`, `error-<Type>`), slug, bytes. `corpus.py`
exposes it as `attempted`, and **every report prints "N of M attempted"**
in its header. The denominator becomes impossible to omit.

## Two populations, never merged

Your constraint, and the part most likely to rot quietly, so it gets
structure rather than a note.

Today every directory under `data/corpus/` with a manifest is one corpus.
Dropping 80 directories in there merges an August 27 fetch with an August
29 one, and every figure in `docs/` silently changes meaning.

**Restructure to `data/corpus/<collection>/<slug>/`:**

    data/corpus/
      2026-08-27-phase-3/          <- the existing three, moved unchanged
        en.wikipedia.org-wiki-html-<digest>/
        news.ycombinator.com-<digest>/
        example.com-<digest>/
        collection.json            <- backfilled from the existing manifests
      2026-08-29-survey/           <- the new pages
        ...
        collection.json
      2026-08-26-snapshot/         <- unchanged; still has no manifest,
                                      still skipped, still provenance only

`CorpusPage` gains `collection` and already carries `fetched_at`.
`load_pages(collection=...)` takes an **explicit** collection and has **no
default**. `--collection all` is legal and prints a banner naming every
collection in the union with its fetch-date range, so a mixed number is
always labelled as one at the point of use.

Making it required breaks the existing invocations in `docs/corpus.md`
(×3), `docs/synthetic-only-coverage.md`, and the four report script
docstrings. Those get updated to name `2026-08-27-phase-3` explicitly, so
**every number currently cited in the docs still reproduces with the
command written next to it** — which is the actual requirement. Nothing
in `docs/` gets its figures rewritten by this task.

## The sample: 80 URLs across nine strata

Target **80**, floor **60** after failures. Not a top-sites list: those
skew to one design language and one budget for engineering, which is the
bias this task exists to escape.

| stratum | n | what it is there to reach |
|---|---:|---|
| news / magazine | 10 | dense floats, figures, multi-column, ads |
| documentation / reference | 10 | long flow content, tables, code blocks, sidebars |
| e-commerce | 10 | grid and flex product lists, the densest flex on the web |
| SPA shells | 8 | near-empty DOM: a finding, see below |
| government / public sector | 10 | old markup, tables used for layout, poor CSS |
| personal sites / blogs | 10 | hand-written HTML, minimal CSS, static generators |
| forums / community | 8 | deeply nested, query-string URLs, tables |
| marketing / landing pages | 8 | **my addition**: highest flex and grid density anywhere |
| non-Latin script | 6 | **my addition**: see the caveat below |

Two strata I added and why:

**Marketing / landing pages** because that is where `flex-direction:
column`, `align-content`, `order` and multi-line wrapping actually live —
the hero/feature-grid idiom. If the goal is to move register rows off
zero, this is the stratum most likely to do it, and none of the seven you
named covers it.

**Non-Latin script** because the layout stage carries
`characters classified AL by default: must be 0` and a `vertical-align`
census, and 80 English pages leave those at zero permanently while looking
like coverage. Caveat, stated up front: the vendored Liberation Sans has
no CJK, Arabic or Devanagari coverage, so these pages will produce
*measurement* rather than correct layout — missing-glyph counts and
script-classification counts, not box positions to trust. That is still
worth having, and it is worth having **before** Phase 4 rather than
discovering it in paint. If you would rather not spend 6 of 80 slots on
pages the font cannot render, drop the stratum and redistribute; say so
and I will.

### Selection rules, so the bias is stated rather than inherited

* No two pages from the same registrable domain, except one deliberate
  pair (an article and an index on the same site) recorded as such.
* Pages, not homepages, wherever a site has both — homepages are
  systematically more flex-dense and less content-dense than the pages
  people actually read.
* Server-rendered *and* client-rendered both admitted. Excluding SPA
  shells because they measure badly is the selection bias.
* No login walls, no paywalls, no cookie interstitials that replace the
  document.
* Every URL carries a one-line **selection reason** in the list. "Chosen
  because" is the field that turns a hand-picked sample into a documented
  one.

### The list is tracked; the corpus is not

`data/corpus/` stays gitignored — it is someone else's copyrighted HTML
and it is reproducible. What gets tracked is
`data/corpus-lists/2026-08-29-survey.tsv`:

    url <TAB> stratum <TAB> risk <TAB> selection_reason

with `#` comments. `collect.py` gains `--urls-from FILE` reading it, and
carries all three metadata columns through into `collection.json` so a
report can break any figure down by stratum without a second lookup table
that can drift.

`risk` is a **prediction written before fetching** — `ok`, `rot`,
`robots`, `bot`, `js`, `homepage`, `paywall` — and `collection.json`
records what actually happened beside it. Two reasons it earns a column
rather than a comment. It makes the sample's fragility legible in advance
instead of arriving as a pile of failures, and comparing predicted risk
against actual outcome is itself a cheap check on whether the sample was
picked with any judgment at all. **No URL in the list has been fetched**;
the deep paths were written from memory against a May 2026 cutoff, so the
`rot` rows are the expected casualties and the 60-page floor is what
absorbs them.

The file also carries a **reserve block**, commented out and marked
`#RESERVE`, concentrated in the two strata most likely to be refused
(e-commerce, forums). A reserve is collected only to replace a failed
primary in the same stratum, and every substitution is recorded in
`collection.json` — so the sample stays documented rather than quietly
repaired to look complete.

Expected on-disk size: roughly 60–120 MB. Fetch time at the default 1s
delay, with ~5 sheets per page plus robots: **25–40 minutes**. Every
report script runs the three-page corpus in 2.4s, so 80 pages is on the
order of a minute — the runtime is entirely fetch, as you said.

### SPA shells are a finding, not a failure

A React shell parses to ~15 elements and lays out an empty page. That is
not a collection failure and must not be dropped, or the corpus quietly
becomes "the subset of the web that server-renders" while claiming to be
the web. Report a named count: **pages whose DOM has fewer than 50
elements**, with their URLs. If it is 8 of 80 that is a fact about the web
worth one sentence in the writeup; if it is 30 of 80 the sample is wrong
and needs re-picking.

## The measurement set to re-run

Each against `2026-08-29-survey`, and **each also re-run against
`2026-08-27-phase-3` at the same commit**.

**Every figure is reported per stratum, not only in aggregate.** This is
the point of stratifying and the easiest thing to lose: an aggregate
median across nine deliberately different populations hides exactly what
the nine were built to separate. A register row that leaves zero only on
marketing pages is a different fact from one that moves everywhere, and
the float distribution is expected to differ sharply between government
sites laying out with tables and news sites floating figures — averaging
those two into one number describes no page in the sample.

So every table below carries one column per stratum plus an `all` column,
in that order, and the aggregate is the last column rather than the
headline. Where a figure is a distribution, report the per-stratum median
and the range across strata; the pooled median is reported too and is
never the one quoted alone. The `nonlatin` stratum is additionally broken
down **per script**, because script is that stratum's independent variable
in the way site type is everywhere else. That second half is not
optional, and it is the whole reason this section is longer than "run the
scripts":

> Comparing today's 80-page numbers against figures written into the docs
> during Phase 2 would attribute **code changes to corpus changes**. Six
> months of engine work sits between those two numbers. Every comparison
> in the output carries two identifiers — collection and commit — and a
> row whose three-page value differs from the docs is reported as *the
> engine moved*, separately from anything the widening shows.

That is CLAUDE.md's cross-stage rule applied to a corpus swap: carry two
identifiers, and when they disagree, say which one moved.

1. **Display census** — `display_report.py`, all three columns (`ua`,
   `ext`, `media`). The `ua`/`ext` gap is the measure of how much of the
   web our UA sheet was inventing; on three pages it was large and on one
   page it was total.
2. **The synthetic-only register** — `docs/synthetic-only-coverage.md`,
   every row, both the Task E and Task F blocks.
3. **The flex census** — `layout_report.py`'s `FLEX_HEADLINE`, over all
   four populations (elements / boxes / laid out / items), per stratum.
4. **The whitespace disposition** — the five-way split under
   `text_boxes_whitespace_only`, including the `must be 0` residual.
5. **`display: none` origins** — `boxes_pruned_roots` vs
   `boxes_pruned_total`, and the share of DOM elements producing no box.
   Currently a single-page figure doing a lot of work.
6. **Parse-error rates** — tokenizer and tree-builder error counters per
   page, per KB. New pages will find tokenizer paths three pages never
   did; that is a Phase 1 regression sweep arriving for free.
7. **The four width categories** — `widths_resolved`,
   `widths_shrink_to_fit_resolved`, `widths_not_applicable_inline_level`,
   and the two `must be 0` residuals.
8. **Every `must be 0` residual in the report.** There are nine. On three
   pages they all read zero. A residual that reads non-zero on page 44 is
   the highest-value single output of this task and the reason to run it
   before Phase 4 rather than after.

## The two findings to report, in this order

**Which rows leave zero.** For each, the count, the number of distinct
pages, and the number of distinct strata. A row that moves from 0 to 400
on one page has not left zero in any useful sense — it has acquired a
second Wikipedia.

**Which rows stay at zero across 80 pages.** The more interesting group,
and the one to lead with. A rule with zero occurrences on three pages is
an absence of evidence; a rule with zero occurrences on 80 pages across
nine strata is evidence of absence, and it says the feature can be
deferred indefinitely on measured grounds rather than by guess. Each such
row gets: still-zero, denominator 80 pages / N strata, and a one-line
reading.

Both lists go in a new section of `docs/synthetic-only-coverage.md`, in
the shape of "What Task F found when it ran", and the register's existing
rows gain a survey column rather than being overwritten. The three-page
numbers stay on the page — they are what every Phase 3 decision was
actually made on, and deleting them would make the record of those
decisions unreadable.

## Tests

The engine is not changing, so these are collector and loader tests.

* `slug_for` distinguishes: trailing slash, differing query strings, same
  path on different hosts, and a >255-character path. Assert the produced
  slug's length is capped and the digest differs, not merely that two
  strings differ.
* A robots-disallowed URL produces a `collection.json` row and **no**
  `CorpusPage`; `load_pages` over that directory returns zero pages and
  one `unfetched` entry with the reason.
* A 404 produces a `collection.json` row with `http-404` and no directory
  left behind.
* `load_pages` **raises** rather than defaulting when `collection` is
  omitted, and `--collection all` labels the union with each collection's
  date.
* The backfilled `2026-08-27-phase-3/collection.json` reproduces the
  existing three pages' slugs, byte counts and `fetched_at` values exactly
  — the migration must be provably lossless, byte-compared, not eyeballed.
* A page directory whose `manifest.json` `source_url` disagrees with its
  slug's digest fails loudly.

Per the nesting rule: the collection-loading tests use a corpus fixture of
**three collections, one with three pages and one with one**, so
per-collection and whole-corpus paths cannot coincide.

## Done when

1. `data/corpus-lists/2026-08-29-survey.tsv` is committed with 80 URLs,
   nine strata, and a risk flag and selection reason on every row.
   **Reviewed by the user before any fetch.**
2. The three collector defects are fixed, with tests, and the existing
   three pages are migrated into `2026-08-27-phase-3/` losslessly.
3. The survey is collected; `collection.json` accounts for **every URL
   attempted**, including failures.
4. All eight measurement sets are run over both collections at one commit,
   with collection and commit recorded in the output.
5. Every figure is reported **per stratum** with the aggregate last, and
   `nonlatin` is additionally broken down per script.
6. `docs/synthetic-only-coverage.md` gains the survey column and the two
   findings sections.
7. `docs/corpus.md` documents both collections, the strata, the selection
   rules, and the stated bias of the sample.
8. The float distribution is reported per stratum and pooled, and the
   pre-registered rule applied, or explicitly overridden with a reason.
9. Full suite green.

## What this deliberately does not do

* **No link discovery, no recursion, no scheduling.** Still not the Phase
  5 crawler. One-shot, explicit URL list, robots respected, 1s delay.
* **No re-fetch of the three Phase 3 pages.** They are a fixed subset with
  a date, and re-fetching would invalidate every Phase 3 figure for no
  gain.
* **No engine changes.** If the survey finds a crash, it is recorded as a
  finding with the page that produced it and fixed as its own task — not
  folded into this one, where it would be invisible in a diff full of
  corpus tooling.
* **No `must be 0` residual gets "fixed" by widening its definition.** If
  one reads non-zero, that is the finding.
