# Task C — block layout

Phase 3, after Task B (box tree, merged). Positions and sizes for
block-level boxes in a block formatting context. Inline content is measured
by Task D; Task C establishes the containing blocks it will run inside.

Two areas get disproportionate space here because they are where hand-rolled
block layout is quietly wrong: **margin collapsing** and **over-constrained
widths**. Both are invisible in a screenshot — the page looks laid out, the
numbers are off — which is the failure mode this project keeps meeting.

## Scope

* Width resolution: the CSS 2.1 §10.3.3 constraint equation, `auto`
  handling, `margin: auto` centring, percentages against the containing
  block.
* Height resolution: §10.6.3, `auto` from in-flow children, percentages
  that fall back when the containing block's height is `auto`.
* Vertical margin collapsing: §8.3.1, in full.
* `box-sizing: border-box` (Task A2 added the property).
* Not implemented, each counted: `float`, `position` other than `static`,
  `overflow` scrolling, `min-`/`max-width`/`height`.

## Margin collapsing — the hard part

**Plan the tests from CSS 2.1 §8.3.1's own cases, not from the corpus.**
Task B established why: the corpus had 28 anonymous-box sites in 8,593
elements and would have passed any implementation. Margin collapsing will
be worse — the common case on real pages is two siblings with margins, and
every interesting rule is an edge case the corpus exercises once or not at
all. **Measure how many of each shape the corpus actually contains and
report it, so the coverage claim is a number rather than a hope.**

### The rules, each needing its own test

Two margins are **adjoining** only if all of these hold. Each condition is
a separate test, because each is a separate way to be wrong:

1. **Adjacent siblings.** The bottom margin of a box and the top margin of
   its next in-flow sibling collapse.
2. **Parent and first child.** A parent's top margin collapses with its
   first in-flow child's top margin — *through* the parent's top edge, so
   the parent moves.
3. **Parent and last child.** Same at the bottom, but only when the
   parent's height is `auto`.
4. **Empty blocks collapse through themselves.** A box with no content, no
   padding, no border and `height: 0` or `auto` collapses its own top and
   bottom margins together, and that result then participates in further
   collapsing. This is the rule most implementations miss, and it chains:
   three empty divs between two paragraphs collapse to a single margin.

### The barriers — every one of these prevents collapse

Each is a separate test, and a negative one. The failure mode is
over-collapsing, which produces a plausible, slightly-too-tight page:

* **Padding or border on the parent** between the two margins. Even 1px.
* **`overflow` other than `visible`** — establishes a new block formatting
  context, so parent/child margins do not collapse through.
* **`float`** and **absolute positioning** — out of flow, margins never
  collapse with in-flow siblings.
* **`display: inline-block`, `flex`, `grid`, `table-cell`** — a new
  formatting context; margins of children do not escape.
* **The root element's margins never collapse** with anything.
* **`clear`** — a cleared box's top margin does not collapse with the
  preceding sibling's bottom margin.

### Percentage margins and padding resolve against WIDTH

Including the vertical ones. `margin-top: 10%` in a 400px-wide container is
**40px**, not a percentage of the height. Same for `margin-bottom`,
`padding-top`, `padding-bottom`.

This is the first place Task A2's symbolic percentages actually get
resolved, and resolving the vertical ones against height would be plausible,
wrong, and invisible on any container whose width and height are close.

**Verified against Chrome 151**, not taken from the spec text: a `10%` top
margin in a 400x800 container measured 40px via `DOM.getBoxModel`.

The test must use a container whose width and height differ enough that the
two rules disagree obviously — 400x800 makes it 40 against 80. A 400x400
container cannot distinguish them, which is the non-discriminating-test
shape again.

### A percentage margin still collapses through an empty block

Also measured against Chrome, and the result corrects an assumption worth
recording. Three things behave **identically** for collapse-through:
no declared margin, `margin: 0`, and `margin: 0%`. All three collapse
through, because §8.3.1's collapse-through condition names borders,
padding, height and line boxes — **not** the box's own margins. A zero
margin does not make a block "non-empty".

What *does* interact with the chaining is a **non-zero** percentage margin
on the empty block, and that is the test worth having, because it needs the
percentage resolution and the collapse-through chain to be right at the
same time. Between two siblings each with `margin: 30px 0`, in a 400px
container:

| middle block | gap | why |
|---|---:|---|
| empty, `margin: 10%` | **40px** | collapses through; its 40 beats the siblings' 30 |
| empty, `margin: 0` | 30px | collapses through; 30 wins |
| `margin: 10%; padding: 1px` | 82px | padding blocks collapse-through: 40 + 2 + 40 |
| `margin: 10%; height: 1px` | 81px | height blocks it: 40 + 1 + 40 |

All four measured. The last two are the negative cases and they are what
catch an implementation that collapses through everything.

### The sign rules

Two positive margins collapse to the **larger**. Two negative collapse to
the **most negative**. A positive and a negative collapse to their **sum**.
Three or more collapse to `max(positives) + min(negatives)`. Get this wrong
and pages with negative margins — a common layout idiom — go subtly wrong
while everything else looks right.

Test both signs and the mixed case. A test using only positive margins
passes under `max()`, under `sum()` when one operand is zero, and under
several other wrong rules.

**Why these tests are shaped this way.** The margin-sign requirement and
the assert-margins-not-positions requirement below are both the
non-discriminating-test failure caught *before* it happens rather than in
review. At least ten tests on this project have asserted less than their
names implied, and the only reliable detector has been injection. These two
are cases where the shape of the wrong test is already known, so the brief
specifies the discriminating shape instead of leaving it to be found later.
Do not simplify them into single-case tests that happen to pass.

### Counters

`margins_collapsed`, `margins_collapsed_through_empty`,
`margin_collapse_blocked_<reason>` per barrier, all seeded at zero. The
per-barrier breakdown is what distinguishes "we correctly did not collapse"
from "we never tried" — the same reason Task A2 partitions drops by cause.

## Over-constrained widths and `margin: auto`

The §10.3.3 constraint for a block-level, non-replaced box in normal flow:

    margin-left + border-left + padding-left + width
      + padding-right + border-right + margin-right
      = containing block width

If none of `width`, `margin-left`, `margin-right` is `auto`, the equation is
**over-constrained**, and CSS 2.1 resolves it by ignoring one margin —
**`margin-right` in a left-to-right containing block**, `margin-left` in
RTL. It does *not* scale both, and it does *not* ignore `margin-left`.

This is the second place block layout goes quietly wrong, and it interacts
with `margin: auto` centring:

* Both margins `auto`, `width` set → equal margins, box centred.
* One margin `auto`, `width` set → that margin absorbs the remainder.
* `width: auto` → `width` absorbs the remainder and any `auto` margins
  become **0**, which surprises people expecting centring. `margin: 0 auto`
  with no width does nothing.
* Over-constrained → `margin-right` is ignored and recomputed.

Four cases, four tests, and they must disagree with each other: an
implementation that always centres passes the first, and one that always
absorbs into `margin-right` passes the first and the fourth. Assert the
resulting `margin-left` and `margin-right` values, not just the box
position, or the "ignored margin" case is indistinguishable from centring
when the numbers happen to match.

The corpus uses `margin: 0 auto` widely, so the *centring* path will be
exercised; the over-constrained path almost certainly will not. Count both.

## Testing discipline

Same as Task B, and for the same measured reason:

* Tests are **synthetic**, from the spec's cases. The corpus run is a smoke
  test. Report the corpus counts per shape so the coverage gap is explicit.
* Every rule gets a **positive and a negative** test. Over-collapsing and
  under-collapsing are both wrong, and only the negative test catches the
  first.
* **Injection testing mandatory**, shadow verified, no-op injections
  discarded rather than reported.
* Counters seeded at zero; every reported number carries its population.
* An assertion that the constraint equation balances after layout, run on
  every box, in the shape of Task A2's `seen == kept + dropped`. It is the
  one check that fails loudly the moment a case is added and forgotten.

## Chrome comparison

Task C is the first task whose output is numerically comparable. The
harness is Task D's deliverable, but Task C should already emit boxes with
all four edges in absolute document coordinates, per the contract in the
Phase 3 plan, and honour the `non_comparable` list Task B produces.

Margin collapsing is worth an early spot-check against Chrome precisely
because it is invisible: a page whose margins all collapse wrongly still
renders as a page. A handful of §8.3.1 fixtures, compared numerically
against `DOM.getBoxModel`, would catch a systematic error before Task D
builds on it.
