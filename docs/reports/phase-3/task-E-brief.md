# Task E — table layout

Read `CLAUDE.md`, then `docs/plans/2026-08-27-phase-3-layout.md` (Task E and
the partial-implementation principle), then `docs/measurement-hazards.md`
(instance fifteen and its two corollaries — they are about the harness you
will use), then `docs/synthetic-only-coverage.md`.

## The seam is clean

Automatic table layout needs the min-content and max-content widths of
cells. **D1 built exactly that and it is Chrome-verified**:
`layout.intrinsic.min_content_width` / `max_content_width`, plus CSS 2.1
§10.3.5's shrink-to-fit. Twelve of D1's Chrome comparisons were intrinsic
sizes and they agree.

Do not write a second min-content. Three routes to one computation was the
reason `intrinsic.py` exists — Task C's shrink-to-fit, your column widths,
and Task F's `flex-basis: auto`. If you find yourself needing something it
does not provide, extend it there rather than locally.

## What the corpus actually contains

Measured, population = styled elements at 1280x1024:

    table-cell        401        table              29
    table-row         218        table-row-group    24
                                 table-caption       4

    tables by column count (widest row, colspan counted):
        0 cols  3     1 col   2     2 cols  20     3 cols  3     6 cols  1

    table `width`:  auto 11,  percentage 16,  length 2

**`colspan` is exercised: 54 cells carry `colspan=2`.** `rowspan` greater
than 1 does not occur at all — zero. So the harder half of column
distribution has real coverage and the other half has none.

`table-layout` is **not in `ComputedStyle`** and no corpus page declares it.
You will need to add it to the cascade, as Task C added `overflow`, `float`,
`clear` and `position`. Fixed table layout then has zero corpus coverage;
say so.

## Anonymous table fixup — the coverage is uneven, not absent

The plan says the corpus will pass whatever you write. That is **half
right**, and the halves matter:

| CSS 2.1 §17.2.1 fixup | corpus occurrences |
|---|---:|
| row whose parent is a `table` — needs an anonymous row-group | **96** |

**Correction, made after Task E fetched the spec text: the first row of that
table is not a §17.2.1 rule at all.** The spec says a `table-row` is
misparented only when its parent is *neither* a row group *nor* a `table` or
`inline-table`. A row inside a table is a proper table child and needs no
fixup. The 96 are a denominator, not coverage — and with that row removed,
**every actual rule occurs four times or fewer**, which is the opposite of
what this brief told the implementer.
| row-group whose parent is a `block` — needs an anonymous table | 2 |
| row whose parent is a `table-row` — mis-nested | 2 |
| cell whose parent is not a row — needs an anonymous row | **0** |
| a table with no rows at all | 3 |

Every one of the 401 cells already has a `table-row` parent, so the fixup
rule most tutorials lead with is never exercised. The missing-row-group rule
is exercised 96 times and is genuinely covered. The two rules at 2
occurrences are one Wikipedia edit from zero and cannot discriminate between
implementations — treat them as uncovered.

**Plan the fixup tests from §17.2.1 directly**, all of them, and report which
had corpus coverage and which did not. Add the uncovered ones to
`docs/synthetic-only-coverage.md`.

## Column width distribution is the fiddly part

CSS 2.1 §17.5.2.2's automatic layout. The parts that go wrong quietly:

* A cell's min/max-content contributes to the column it starts in — but a
  **`colspan` cell contributes to no single column**. Its width constrains
  the *sum* of the columns it spans, and the excess is distributed among
  them. Getting this wrong is invisible on a table where the spanned
  columns are already wide enough, which is most of them.
* Distribution order matters: spanning cells are considered after
  non-spanning ones, so a column's width from single-cell content is
  established first and the span only widens it.
* The table's own `width` interacts: `auto` uses the max-content sum
  clamped to the available width, a percentage or length is a constraint the
  columns must be distributed into.
* 54 `colspan=2` cells means a wrong distribution **will** move real
  numbers on this corpus — unlike most of Phase 3, you have a check here.
  Use it, and report before-and-after column widths for the Wikipedia
  tables.

## Not in scope, counted

`border-collapse: collapse` (counted), `rowspan` beyond simple spanning,
`<col>`/`<colgroup>` width contributions, vertical alignment within a cell
beyond `top`/`middle`, and table margins on internal boxes — CSS 2.1 §17.5 says a browser drops those, and Task C currently applies them, counted in
`layout_table_box_margins_applied` (2 on the corpus). Fixing that is yours.

## The harness

`scripts/chrome_compare.py` exists and works. **Read instance fifteen before
using it.** Its two corollaries are directly about you:

* Seven agreeing fixtures through one harness are one observation repeated,
  not seven pieces of evidence. Vary what your fixtures *share*, not just
  their input.
* Chrome agreeing with your output is not proof unless its preconditions
  hold. The harness now asserts `document.compatMode`; a table fixture
  without a doctype would have put you in quirks mode, where table layout
  differs.

The corpus-wide comparison is declined by design — Chrome would fetch live
stylesheets while this engine applies the collected copies. Do not "fix"
that by pointing Chrome at the network.

## Discipline

Injection testing mandatory, shadow verified by printing `module.__file__`,
no-op injections discarded and replaced. Counters seeded at zero. Every
number reported with its population named. A mechanical check in the shape
of Task C's constraint assertion and D2's character conservation — column
widths summing to the table width is the obvious candidate. Non-ASCII in
test data as escapes.

## Environment

* Do NOT modify `.venv/`. Do NOT uninstall anything.
* Never import `tinycss2`, `webcolors`, `cssutils`, `cssselect`,
  `matplotlib` from `src/` or a committed test. `fontTools` is permitted in
  `layout/`; Pillow is not.
* `.venv/bin/pytest` with **no** `-q`.
* Never `git submodule update --remote`.
* **Stage explicit paths. Never `git add -A`.**
* Scratch in `/Users/atishaypahadiya/.claude/jobs/604b9f51/tmp`.
* Scripts put the repo's own `src/` ahead of `PYTHONPATH` — print
  `module.__file__` to prove a shadow took.
* Baseline: **7008 passed, 7 skipped, 72 xfailed**. Verify it yourself.

## Done when

* Automatic and fixed table layout implemented, column distribution
  including `colspan`, built on `intrinsic.py` rather than a second
  min-content.
* All of §17.2.1's fixup rules implemented and tested synthetically, with
  corpus coverage reported per rule.
* Full suite green. Report includes the injection table, the table census
  with populations named, before/after column widths for the corpus tables,
  new register rows, and every defect you find in this brief or the plan.
