# Phase 3 — Layout

Dated 2026-08-27. Task A (corpus collection and `@media` evaluation) is
done and merged; see `2026-08-27-phase-3-task-a-media-queries.md`. This
plan covers the rest: box tree, block layout, inline layout, tables, and a
flex subset.

No code yet. This is the plan.

## What the corpus says, and what it does not

Display census at 1280x1024, after Task A, over 8,593 elements:

| display | count | share |
|---|---:|---:|
| inline | 5,829 | 67.8% |
| block | 1,242 | 14.5% |
| none | 519 | 6.0% |
| table-cell | 401 | 4.7% |
| table-row | 218 | 2.5% |
| flex | 205 | 2.4% |
| inline-block | 90 | 1.0% |
| table / row-group / caption | 57 | 0.7% |
| inline-flex | 28 | 0.3% |
| grid | 2 | 0.02% |
| list-item | 2 | 0.02% |

**Scope: block + inline + tables + a flex subset. Grid is not implemented,
and gets a counter** so the day a corpus page needs it, the number says so
instead of the render silently being wrong.

**The caveat, kept visible on purpose.** Wikipedia supplies 7,778 of the
8,593 elements — 90.5% of the corpus. Every percentage above is
substantially a fact about one page. That is sufficient to scope Phase 3,
because the shapes it has to handle are real shapes; it is not sufficient
to say anything about the web, and no figure here should appear in the
analysis half without the denominator beside it. Widening the corpus is
Phase 5's job, not a prerequisite for building layout.

Two counts that matter more than their share suggests:

* **`flex` is 2.4% of elements and far more than 2.4% of the work.** Those
  205 elements are Wikipedia's header, sidebar, tab bar and portlets — the
  structural containers everything else nests inside. Block layout alone
  does not place them, and getting them wrong misplaces their subtrees.
* **`display: none` prunes 954 elements, not 519.** The census counts
  elements whose own computed `display` is `none`; the 519 roots carry 435
  descendants that never produce a box either. That is 11.1% of the corpus
  removed before any layout runs.

## Task order

### Task A2 — cascade repair

Before box-tree construction, not as cleanup. At a 70% declaration drop
rate a layout bug and a cascade bug are indistinguishable, and Phase 3
would spend its budget telling them apart.

**`var()`, common case only.** Custom properties (`--x`) inherit like any
inherited property. `var(--x)` and `var(--x, fallback)` resolve at
computed-value time. Deliberately out of scope, each with a counter:

* `var()` nested inside another `var()`'s fallback --
  `var_nested_fallback_skipped`
* cycles, handled by a **substitution depth cap** rather than real cycle
  detection -- `var_depth_exceeded`. A cap is O(1) and cannot be wrong in
  the dangerous direction; full detection is a phase, not a task.
* `var()` in a custom property's own value beyond one level of indirection
* the guaranteed-invalid-value rules of Custom Properties 1 section 3, in
  their full generality

That is 233 of 257 dropped colour declarations recovered, and 557 Wikipedia
declarations that currently evaluate to nothing.

**Box-model longhands.** `margin-left`, `padding-top`, `border-color`,
`border-left-width` and the other 24. `ComputedStyle` already carries every
field; the gap is `values.py`'s property table alone. 395 declarations.

**`ComputedStyle` additions** that Task D cannot start without:
`white-space`, `line-height`, `font-family`, `font-weight`, `font-style`,
`text-align`, `vertical-align`. Plus `box-sizing`, which changes what every
width in Task C means and is cheaper to add now than to retrofit.

**`INHERITED` expansion**, from two properties to nine: `color`,
`font-size`, `font-family`, `font-weight`, `font-style`, `line-height`,
`white-space`, `text-align`, `list-style-type`. One test per property. A
property that silently fails to inherit produces plausible-looking wrong
output, which is the hardest kind to notice and the reason this is one
deliberate change rather than nine incidental ones.

**`inherit` / `initial` / `unset`** accepted rather than dropped
(`values.py` deviation 3). `revert` stays unsupported and counted -- it
needs origin-level rollback the cascade does not model.

Done when: the drop **reasons** are reported alongside the rate, per page,
before and after. A rate alone is ambiguous -- it falls when the parser
improves and it also falls when validation loosens, and those are opposite
outcomes. So the report is a breakdown by cause, in the shape of Phase 2's
curated error-code set:

    unsupported-property     the property is not in values.py's table
    unsupported-value        the property is known, the value is not
    var-unresolved           var() we chose not to substitute, by sub-reason
    invalid                  genuinely malformed, a browser would drop it too

`invalid` must not shrink. If it does, validation loosened and something
that should have been dropped is now being accepted -- which is a
regression wearing an improvement's clothes. The number to move is
Wikipedia's 70%, via `unsupported-property` and `var-unresolved`.

### Task B — box tree construction

The tree layout walks, built once from the styled DOM, so no later task
re-derives it.

* **`display: none` pruning happens here, first.** It is subtree removal,
  not per-node skipping: a `none` element contributes no box and neither
  does anything beneath it, whatever those descendants computed. Doing it
  at box-tree time is the cheapest correctness win in the phase — 954
  elements, 11.1% of the corpus, that later stages then never see.
* Block/inline/table/flex container classification from computed `display`.
* Anonymous box generation: block containers with mixed block and inline
  children wrap the inline runs in anonymous block boxes. Wikipedia is full
  of this shape and it is the thing that makes block and inline layout
  composable rather than mutually recursive special cases.
* `grid` and `inline-grid` fall back to `block` and `inline-block`
  respectively, and increment `boxes_grid_fallback`. A counter, not a
  silent substitution.

Tests: a `none` subtree contributes zero boxes and its children are never
visited (assert on a visit counter, not on the output tree — an unvisited
node and a discarded one look identical downstream); anonymous block
wrapping for `<div>text<p>x</p>text</div>`; grid falls back *and* counts.

### Task C — block layout

Block formatting context, top to bottom.

* Widths: the `width: auto` constraint equation, `margin: auto` centring,
  percentages resolved against the containing block.
* Heights: `auto` from in-flow children; percentages against the containing
  block, which is `auto` in the common case and therefore falls back.
* Vertical margin collapsing between siblings, and parent/first-child.
  Collapsing is where hand-rolled block layout usually goes wrong, so it
  gets its own tests rather than riding along with the width tests.
* Not in scope: `float`, `position: absolute/fixed`, `overflow` scrolling.
  Counted, not implemented — see the deferred list.

### Task D — inline layout and line breaking

**This is the centre of gravity, not a follow-on to Task C.** 67.8% of
elements are inline; a block layout that stubs line boxes has not rendered
these pages, it has drawn their skeleton.

* **Text measurement: real font metrics from a vendored font.** Not an
  approximation table. Three reasons, in the order they matter: Phase 4
  rasterizes with Pillow regardless, and a table in layout with FreeType in
  paint is two sources of truth that disagree until text overflows its own
  boxes; forcing Chrome to the same font with a test stylesheet makes box
  positions directly comparable, which is what turns "position error
  against a reference renderer" into a Phase 6 chart rather than an
  aspiration; and line breaking, baseline alignment and white-space
  collapsing all stay hand-rolled, because glyph rasterization is a
  separate discipline in the way TCP is.

  **Metrics come from the font's `hmtx` table via `fontTools`, not from
  `PIL.ImageFont.getlength`.** Measured, not assumed: Pillow returns
  integer-rounded advances at 16px -- `"Hello world"` is 89.0 where the
  font's own metrics give 89.6953 -- and setting `layout_engine=BASIC` or
  `mode="L"` does not change it. A 0.7px error over eleven characters
  compounds per glyph and per line, and it would make the Chrome comparison
  measure our rounding rather than our layout. Reading `hmtx` directly is
  exact, deterministic, linear in font size (one multiply), and involves no
  rasterizer. This is also what a browser does: unhinted fractional
  advances for layout, hinted rendering for paint. Pillow still owns
  rasterization in Phase 4, over the same vendored file, so there is one
  font and one metric definition.

  Everything downstream treats width as opaque, behind one
  `measure(text, style) -> width` interface.
* **White-space collapsing**, per CSS Text 3: runs of spaces/tabs/newlines
  collapse to one space, leading/trailing collapse at line boundaries.
  This is where the Phase 1 whitespace measurement lands: 2,781 of 7,985
  text nodes (34.8%) are whitespace-only, but they are only 4.8% of text
  *characters* — inter-tag indentation, not content. Most collapse away
  entirely. They must not each produce a line box, and they must not be
  dropped at parse time either, because a whitespace text node between two
  inline elements is a real space that separates two words.
  `white-space: pre`/`nowrap` are in scope; `pre-wrap`/`break-spaces` are
  counted and treated as `pre`.
* **Line breaking**: greedy, at collapsed break opportunities. Not
  UAX #14 — a space-and-hyphen approximation, with the deviation named.
* **Baseline alignment** within a line box: ascent, descent and line gap
  from the font's `hhea`/`OS/2` tables, `vertical-align: baseline` and
  `top`/`bottom`/`middle`; the rest counted.
* **`ex` and `ch` stop being approximations.** Phase 2 uses 0.5em for both.
  The real values for DejaVu Sans at 16px are 8.75px (`ex`, from the `x`
  glyph's bounding box -- DejaVu 2.35 ships OS/2 version 1 with no
  `sxHeight` field, so the glyph is the source) and 10.1797px (`ch`, the
  `0` advance). Both are 9% and 27% off respectively, which is enough to
  move a line break.
* Inline boxes that span a line break split into fragments. This is the
  part that makes inline layout structurally different from block, and it
  needs its own model in the box tree rather than an afterthought.

### Task E — table layout

7.9% of elements across the corpus (table, row, row-group, cell, caption),
and Hacker News is *structurally a table* — 32% of its elements.

* Fixed and auto table layout, column width resolution from cell content.
* Anonymous table box fixup: a `table-cell` with no `table-row` ancestor
  gets wrapped. Real markup relies on this constantly.
* Not in scope: `border-collapse: collapse` (counted), `colspan`/`rowspan`
  beyond simple spanning, vertical alignment beyond `top`/`middle`.

### Task F — flex subset

205 elements, all structural containers.

* Single-line only (`flex-wrap: nowrap`); `wrap` counted and laid out as
  `nowrap`, which misplaces rather than crashes and says so.
* `flex-direction` row and column, `justify-content`, `align-items`.
* `flex-grow`/`flex-shrink`/`flex-basis` resolution on the main axis.
* Not in scope: `order`, `align-self`, `align-content`, wrapping, nested
  flex sizing subtleties. Each counted.

### Task G — metrics and the layout report

`layout` becomes a stage in `data/metrics/stages.csv` alongside
`tokenize`, `treebuild` and `cssparse`: box counts by type, boxes pruned,
line boxes produced, layout time, and every "counted, not implemented"
number above. A `scripts/layout_report.py` driver, in the shape of
`display_report.py` — the library builds `Counter`s, the driver writes
them.

## What Phase 2's output makes harder than it needs to be

Measured, not recalled. All figures at 1280x1024 over the current corpus.

**1. 67% of declarations that reach the cascade are dropped.** Per page:
example 9%, Hacker News 32%, Wikipedia 70% (2,296 of 3,299). Layout cannot
be more correct than its input, and at a 70% drop rate the risk is that
Phase 3 gets blamed for what the cascade discarded. The next three items
are the bulk of it.

**2. `var()` is unsupported, and Wikipedia is built on it.** 420 custom
properties defined, 557 declarations consuming them — 15.4% of that page's
declarations. 233 of the 257 dropped `color`/`background-color`
declarations are `var()` alone. This is the single largest gap, and unlike
the others it is not a layout feature: custom-property substitution belongs
in the cascade, before Phase 3 can consume anything.

**3. Every box-model longhand is dropped.** `margin-left`, `padding-top`,
`border-color`, `border-left-width` — `parse_declaration_value` accepts the
`margin`/`padding`/`border` shorthands and nothing else. 395 declarations
across the corpus, 28 distinct properties, 14.1% of all drops. These are
properties the engine *already models* — `ComputedStyle` has all four
`margin_*` fields — so the gap is purely in the value parser's property
table. `margin-left: auto` centring is unreachable until this is fixed,
and centring is not optional for these pages.

**4. `ComputedStyle` has 26 fields and layout needs about a dozen more.**
Absent today: `white-space`, `line-height`, `font-family`, `font-weight`,
`font-style`, `text-align`, `vertical-align`, `position`, `float`, `clear`,
`box-sizing`, `overflow`, `list-style-type`. Task D cannot start without
the first four — `white-space` and `line-height` in particular are not
optional for line boxes. Dropped counts confirm authors set them:
`line-height` 61, `float` 60, `position` 49, `text-align` 44,
`vertical-align` 42, `clear` 40, `overflow` 33, `font-family` 30,
`font-weight` 64.

**5. `INHERITED` contains two properties: `color` and `font-size`.** Every
property Task D adds is inherited — `white-space`, `line-height`,
`text-align`, `font-family`, `font-weight`, `font-style` — so the
inheritance set roughly quadruples. Worth doing as one deliberate change
with a test per property rather than one at a time, because a property that
silently fails to inherit produces plausible-looking wrong output, which is
the hardest kind to notice.

**6. `inherit` / `initial` / `unset` / `revert` are rejected outright.**
`values.py` deviation 3. Any declaration using one is dropped and counted.
Cheap to add, and it interacts with item 5.

**7. `ex` and `ch` are 0.5em approximations, and `vw`/`vh` stay symbolic.**
Both are correct decisions for Phase 2 and both become Task D's problem:
`ex`/`ch` want real font metrics, and the viewport units now have a
`Viewport` to resolve against — `media.py` has one, and `_length_to_px`
should take it rather than returning `None`.

**8. Computed values are not used values, deliberately.** Percentages and
`auto` survive symbolically, which is exactly right and is the single most
helpful thing Phase 2 did for this phase. Noted so it is not "fixed".

### Where each one is handled

Items 2, 3, 4, 5 and 6 are **Task A2**, above — prerequisites rather than
cleanup, because Task D cannot be written against a `ComputedStyle` with no
`white-space`, and at a 70% drop rate a layout bug and a cascade bug are
indistinguishable. Item 7 is resolved by Task D's font and Task C's
viewport. Item 8 is not a problem to fix; it is recorded so it is not
"fixed".

## Deferred, with counters

Named here so each is a number rather than an absence: `grid`,
`float`, `position` other than `static`/`relative`, `overflow` scrolling,
`border-collapse`, `flex-wrap`, `order`, `align-self`, `align-content`,
`@supports`, `prefers-*` media features, UAX #14 line breaking, kerning and
ligatures (`hmtx` advances only, no `GPOS`/`GSUB`), font fallback and the
full `font-family` list (one vendored face), bidi and vertical writing
modes, and `revert`.

## The font, and why the version is recorded

Task D's text measurement is the one place where a wrong choice is
expensive to undo. A metrics table keeps the phase self-contained and
hand-rolled, consistent with the project's rules; the cost is that every
width in the output is approximate, so layout cannot be validated against a
browser by comparing numbers — only by comparing structure. If numeric
comparison against a reference render is wanted later, that decision has to
be made before Task D, not after.

## A rule that needs amending before Task D

CLAUDE.md forbids browser libraries for core parsing and names
`tinycss2`/`cssutils`/`cssselect` outright, with one recorded exception:
`html.entities.html5`, permitted because it is *data* -- the WHATWG named
reference list -- and every matching rule around it is hand-rolled.

`fontTools` in `src/mayshay/` is the same shape of decision and deserves
the same explicit treatment rather than being smuggled in. It reads a
binary font file into glyph advances and vertical metrics; it makes no
layout decision. Line breaking, white-space collapsing, baseline alignment
and every box position stay hand-rolled. The alternative -- hand-rolling a
TrueType table parser -- would be writing a binary deserializer, which is
not what this project is for and would still produce the same numbers.

Proposed amendment, to be agreed before Task D rather than after:

> `fontTools` is permitted in `src/mayshay/layout/` for reading font
> metrics -- glyph advances from `hmtx`, vertical metrics from `hhea` and
> `OS/2`. It is a binary format reader over vendored data, in the same
> category as `html.entities.html5`. It must not make layout decisions:
> text measurement is the only thing it is asked for, behind a single
> `measure()` interface. Pillow is permitted in `paint/` for rasterization
> only. Neither may be imported by `htmlparse` or `cssparse`.
