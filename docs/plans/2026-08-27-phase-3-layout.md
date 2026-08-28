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

  **Vindicated on the first real page it saw.** Wikipedia ships a genuinely
  self-referential custom property in production CSS --
  `--font-size-medium: var(--font-size-medium, 1rem)` -- which accounts for
  59 of that page's `var_depth_exceeded` hits and would have been an
  infinite substitution loop without the cap. Not a pathological input
  constructed for a test; one of three pages in the corpus. That is the
  argument for choosing a bounded approximation over the complete algorithm
  when the two differ only in cases nobody can name: the case turned out to
  be nameable, common, and already present.
* `var()` in a custom property's own value beyond one level of indirection
* the guaranteed-invalid-value rules of Custom Properties 1 section 3, in
  their full generality

That is 233 of 257 dropped colour declarations recovered. Wikipedia's
custom-property count depends on the population measured -- 313 declared
and 353 consuming are the cascade-visible figures at 1280x1024, which is
the number this task moves; see docs/measurement-hazards.md on why three
different correct answers exist.

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
  text nodes (34.8%) are whitespace-only, and those nodes hold 5,671 of
  117,378 characters (4.8%).

  **Two corrections to the reasoning that figure was used for.** First, 4.8%
  is the share of characters living *inside whitespace-only nodes* — the
  share of characters that *are* whitespace is 17,426 (14.8%), three times
  larger, because most whitespace is the ordinary spaces between words
  inside content nodes. Using the first number to argue that whitespace is a
  small part of the text is reasoning about one population from another.

  Second, and measured by Task D1: **"most collapse away entirely" is
  false.** Of the 1,287 whitespace-only boxes that reach the collapser,
  169 (13.1%) collapse away, **1,065 (82.8%) survive as a single separating
  space**, and 53 are preserved verbatim. The collapsing-away case had
  already been taken by Task B's blank-run rule before D1 ever saw them.

  They must not each produce a line box, and they must not be dropped at
  parse time either, because a whitespace text node between two inline
  elements is a real space that separates two words.
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

**8a. Percentages resolve against three different things, not one.**
`font-size: 50%` and `line-height: 50%` must be resolved at cascade time
(the reference is a font size, which the cascade knows); `width: 50%` and
`margin-top: 5%` must not (the reference is a containing-block dimension);
`vertical-align: 50%` is resolvable only when `line-height` is a number or
a length, and needs font metrics when it is `normal`. Task C resolves the
second category and Task D the remainder of the third. The full rule,
the current audit, and the traps -- `margin-top` resolving against
*width*, and a unitless `line-height` inheriting as a number -- are in
`docs/percentage-resolution.md`. Read it before adding any
percentage-accepting property.

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

## Intrinsic sizing is one capability, not three accommodations

Decided before Task D writes its measurement code, for the same reason the
stylesheet ordering was fixed at the chokepoint rather than at the symptom:
three tasks need this and would otherwise each discover it separately and
build a local workaround.

**The Task C/D boundary does not fall along `display` values. It falls
along whether a box's used size depends on the intrinsic dimensions of its
contents** — its max-content and min-content sizes. A block-level box's
`width: auto` comes from the containing block and needs nothing from its
content. Everything below needs both.

Measured against Chrome 151, containing block 900px, the same two-character
and forty-one-character contents in each case:

| case | short | long | driven by |
|---|---:|---:|---|
| block, `width: auto` | 900.00 | 900.00 | the containing block |
| table cell, `width: auto` | **19.27** | **394.95** | its content |
| flex item, `flex-basis: auto` | **19.27** | **394.95** | its content |
| `inline-block` | **19.27** | **394.95** | its content |

The three content-driven rows are not merely similar, they are
**identical to the hundredth of a pixel**. It is one computation reached by
three routes:

* **Task C** — shrink-to-fit for `inline-block` (90 on the corpus), and for
  floats and absolute positioning when those arrive.
* **Task E** — automatic table layout, where column widths come from the
  min-content and max-content widths of the cells.
* **Task F** — `flex-basis: auto` resolving to the item's content size.

### Where it lives

`src/mayshay/layout/intrinsic.py`, with two functions over a box subtree:

    min_content_width(box) -> float     # the widest unbreakable unit
    max_content_width(box) -> float     # no wrapping at all

Both are built on Task D's single `measure(text, style) -> float` seam and
on nothing else. That is not only about avoiding duplicate code: every
decision in `docs/fonts.md` lands at that seam and nowhere else — `hmtx`
rather than `PIL.getlength`, `hhea` rather than the two `OS/2` conventions
for line boxes, and kerning deliberately omitted at a measured +0.137%.
Three call sites would mean three places for one of those to drift, and a
drifted vertical-metric choice is a systematic offset that looks like a
layout bug. CSS 2.1 §10.3.5's
shrink-to-fit formula then has one implementation that all three consumers
call:

    used = min(max(min_content, available), max_content)

**Task D implements this as a named capability, not as an inline-block
accommodation.** Task C cannot — it has no text measurement — so Task C
leaves these boxes symbolic, counts them in
`widths_deferred_shrink_to_fit`, and leaves the seam named rather than
inventing a local approximation. Tasks E and F consume the same two
functions rather than growing their own.

Getting this wrong is cheap to avoid now and expensive later: three
independent implementations of min-content would disagree on the same page,
and the disagreement would show up as a layout error with no single place
to fix it.

## The Chrome comparison contract

Decided before Task D, because it constrains Task D's output format and
retrofitting a serializer is expensive.

**Numeric per-element comparison over CDP, not screenshot diffing.** A
pixel diff says something is wrong; it does not say what or where, and it
cannot produce a position-error distribution. CDP gives box geometry per
node, which can.

Everything below was verified against **Chrome 151.0.7922.174** with a
probe, not read from documentation.

### What CDP actually returns

`DOM.getBoxModel` returns all four box edges as quads, in CSS pixels. For a
`div` with `margin:10px 20px; border:3px; padding:5px 7px; width:400px;
height:50px`:

| edge | x | y | w x h |
|---|---|---|---|
| content | 30.00 .. 430.00 | 18.00 .. 68.00 | 400 x 50 |
| padding | 23.00 .. 437.00 | 13.00 .. 73.00 | 414 x 60 |
| border | 20.00 .. 440.00 | 10.00 .. 76.00 | 420 x 66 |
| margin | 0.00 .. 460.00 | 0.00 .. 86.00 | 460 x 86 |

Three properties to match, each measured:

* **Quad order is TL, TR, BR, BL** -- eight floats, `x1 y1 x2 y2 x3 y3 x4
  y4`. A rectangle's extent is `x[0]..x[2]` and `y[1]..y[5]`.
* **`model.width`/`model.height` describe the BORDER box** (420 x 66
  above), not the content box. Reading them as content dimensions is a
  silent 20px error on a 400px div -- exactly the shape that produces a
  consistent offset nobody questions, because a uniformly-wrong comparison
  still looks like a working comparison.

  **This must be an assertion in the harness, not a comment.** On startup,
  against a fixture page with known geometry, the harness asserts that
  every edge relation holds before it compares anything:

      content.width + padding.left + padding.right      == padding.width
      padding.width + border.left  + border.right       == border.width
      border.width  + margin.left  + margin.right       == margin.width
      model.width                                       == border.width

  The last line is the load-bearing one: it pins which edge `model.width`
  names, so a Chrome release that changed the convention -- or a
  misreading of it on our side -- fails loudly at startup rather than
  shifting every number by a constant. The fixture's expected values are
  written out explicitly (content 400 x 50, padding 414 x 60, border
  420 x 66, margin 460 x 86 for the div above), so the assertion checks
  against measured ground truth rather than against itself.
* **Coordinates are document-relative, and scrolling does not move them.**
  Verified directly: adding 800px of `padding-top` and scrolling down 300px
  moved a box's `y` by exactly +800, not +500.

### The finding that changes Task D's output

`DOM.getBoxModel` is **not sufficient**, and using it alone would silently
break the comparison for the majority of the corpus.

For an inline `<span>` wrapping across three lines, `getBoxModel` returns
one box -- x 0.00..194.80, y 89.00..154.00, 195 x 65 -- which is the
**union** of the fragments and matches none of them. `DOM.getContentQuads`
returns the three real fragments:

| fragment | x | y | w x h |
|---|---|---|---|
| 0 | 78.25 .. 184.09 | 89 .. 106 | 105.84 x 17 |
| 1 | 0.00 .. 194.80 | 113 .. 130 | 194.80 x 17 |
| 2 | 0.00 .. 188.53 | 137 .. 154 | 188.53 x 17 |

Inline is **67.8% of the corpus**. Comparing our per-line fragments against
a union bounding box would make the comparison meaningless for exactly the
case Task D exists to get right -- and it would look like it was working,
because the union box is a plausible-shaped rectangle.

So the harness uses **both**: `getBoxModel` for block-level boxes, where
all four edges matter, and `getContentQuads` for inline boxes, one quad per
line fragment.

### What Task D must therefore emit

* **Fragments are first-class.** An inline box that spans a line break
  serialises as N fragments with their own geometry, not as one box with a
  bounding rectangle. This was already the plan; it is now a hard
  requirement with a consumer.
* **All four box edges per box** -- content, padding, border, margin -- as
  absolute document coordinates with the origin at the document's top-left,
  y increasing downward. Not relative to the parent, and not
  viewport-relative.
* **Rectangles as `x, y, width, height`** in CSS pixels as floats.
  Converting to and from CDP's quad form is one function, and quads carry
  a transform capability we do not implement.
* **Known non-comparables, recorded before Task D runs.** Some DOM nodes
  produce no box on our side while CDP still answers `getBoxModel` for
  them. `build_box_tree(document, non_comparable=[...])` collects them by
  identity -- currently the 32 dissolved inlines on the corpus, an inline
  whose children are all block-level and which therefore contributes no box
  at all. Unrecorded, those read as 32 layout failures. This is the same
  shape as the two-identifier scheme: distinguishing "we differ" from "the
  question does not apply". Derived from the tree rather than hard-coded,
  so it stays correct when the corpus is re-collected.
* **A node identity matchable across engines.** CDP's `nodeId` and
  `backendNodeId` are Chrome-internal and meaningless to us. The contract
  is a **document-order element ordinal** plus a **structural path**
  (`/html/body/div[2]/span[1]`), both computed the same way on each side.
  Two identifiers rather than one on purpose: when the ordinals line up but
  the paths disagree, the trees diverged, and that is an `htmlparse`
  finding, not a layout one. **Tree divergence must be reported separately
  from position divergence** -- otherwise a parser bug reads as thousands of
  layout errors, which is precisely the confusion Task A2 exists to prevent
  one layer down.

### Comparison conditions

The reference page is served with a stylesheet forcing `Arial` (which
Liberation Sans is metric-compatible with), a fixed 1280x1024 viewport,
`--force-device-scale-factor=1`, and `--hide-scrollbars` -- a scrollbar
narrows the containing block and shifts every box in it.

Chrome must be launched with `--remote-allow-origins='*'`, and
`--headless=new` starts with no page target, so the harness attaches to the
browser endpoint and calls `Target.createTarget` rather than expecting a
tab in `/json`. Both cost a debugging round in the probe; recorded so they
do not cost another.

## Partial implementations of out-of-scope features

**An out-of-scope feature must not get a partial implementation that is
wrong in the direction we can reach.** Found in Task C, and it will recur in
every remaining task.

The case: CSS 2.1 lists `clear` among the things that prevent margin
collapsing, and the Task C plan copied that. Measured against Chrome 151
with no float present, a `clear: both` sibling collapses its margins exactly
like an uncleared one -- `margin-bottom: 30px` above `margin-top: 10px`
gives 30, not 40. What actually moves a box is **clearance**, which is
generated only when there is a float to clear.

Floats are out of scope, so this engine never generates clearance. Treating
`clear` as an unconditional barrier would therefore have made it **disagree
with a browser on every case it can reach**, in order to agree on a case it
cannot reach at all. Strictly worse than not implementing it.

The general rule:

> When feature X is out of scope and feature Y's behaviour depends on X,
> implement Y for the world where X is absent -- which is the world this
> engine is in -- and count the divergence. Do not implement Y as though X
> were present.

Where this recurs:

* **Task D** — `float` affects line box geometry (shortening lines that run
  beside a float). With no floats laid out, lines must be full width. A
  line-shortening implementation with nothing to shorten against is the
  same trap.
* **Task D / E** — `vertical-align` percentages against a `line-height` of
  `normal`, already handled this way: resolved where the input exists,
  counted where it does not.
* **Anywhere** — `position: absolute` affects the static position of
  siblings only through being *removed* from flow, which Task C does
  correctly. Its own geometry stays unimplemented rather than approximated.
* **Phase 4** — `z-index` and stacking contexts. Painting in document order
  is correct for the subset we build; a partial stacking implementation
  would reorder cases we handle in order to half-handle cases we do not.

The counter is what makes this honest rather than a shortcut:
`layout_float_skipped`, `layout_absolute_skipped` and their kin say how
often the divergence is reachable, so "we do not implement X" is a number
rather than an absence.

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
