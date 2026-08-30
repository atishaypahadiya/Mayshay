# Synthetic-only coverage

Code paths this engine implements and tests, but which **no page in the
corpus exercises**. They are correct as far as the tests go and have never
been run against real input.

The register exists because "6,735 tests pass and the corpus renders" would
otherwise read as validation of them, and it is not. It is validation of
everything else.

It also accumulates into a finding in its own right: **the gap between what
the specs require and what the web actually uses.** Every row is a feature
the CSS specifications treat as ordinary and that three real pages never
reach for. A test suite written from CSS 2.1 alone would weight these
exactly backwards — which is measurable here, and is one of the better
things the analysis half of this project can say.

## How to use it

* Add a row when a task implements something the corpus does not exercise.
* Give the **corpus count**, with its population named, not "rare".
* Remove a row only when a re-collected or widened corpus exercises it —
  and say which page did, because that is the interesting event.
* A count of 1 or 2 is barely better than 0: it is one edit away from
  returning to 0, and it cannot discriminate between implementations.

## Occurrence count is not the question that matters

"Is this feature exercised by the corpus?" and "would a wrong implementation
of it be visible?" are different questions, and the second is the one a
reader actually wants answered. A feature can occur 54 times and still hide
a defect; a feature occurring twice can be load-bearing.

Task E measured both for `colspan`, using **shadow builds**: implement the
rule wrongly in a copy of `src/`, run the corpus, diff the output. Two
plausible wrong rules, both of which render every page without complaint:

| wrong rule | tables whose columns move (of 27) |
|---|---:|
| spanning cell attributed wholly to its **starting column** | **12** |
| spanning cell contributes to **nothing** | 2 |

The first collapses a Wikipedia column from 592px to zero. The second moves
two tables, one of them by 21px. Same feature, same 52 corpus occurrences,
and a factor of six between how visible the two mistakes are — which no
occurrence count could have told anyone.

**Where it is cheap, record discriminating power beside the count.** Shadow
builds are the instrument and they are inexpensive: a copy of `src/`, one
edited rule, one corpus run, one diff. They also answer the question the
occurrence count only gestures at — *if this were wrong, would we find out?*

The honest default when no shadow build has been run is to say so, rather
than letting an occurrence count stand in for an answer it cannot give.

## Register

Corpus at 2026-08-27: three pages, 8,593 DOM elements, 7,639 producing a
box, viewport 1280x1024, `@media` evaluated, external sheets applied.

Task E's rows are in a section of their own below, because they need three
populations of their own and mixing them into this table would put four
different denominators under one heading.

| feature | corpus count | population | added |
|---|---:|---|---|
| `vertical-align: <percentage>` | **0** | element boxes with a computed `vertical-align` | Task A2 / C |
| `vertical-align: <length>` | **0** | same | Task A2 / C |
| `vertical-align: sub`, `super`, `bottom` | **0** | same | Task C |
| `vertical-align: text-top` | 1 | same | Task C |
| `vertical-align: text-bottom` | 1 | same | Task C |
| genuinely split inline boxes | **0** | inline boxes with a block-level child; all 31 are dissolved atomics | Task B / C |
| `white-space: pre` | **0** | element boxes with a computed `white-space` | Task D1 |
| `white-space: pre-line` | **0** | same | Task D1 |
| `white-space: break-spaces` | **0** | same | Task D1 |
| two-negative adjacent margin pair | **0** | adjacent in-flow block sibling pairs (840) | Task C |
| percentage vertical margin | **0** | block boxes with a vertical margin | Task C |
| one-sided `auto` margin | **0** | block boxes with an `auto` margin; 9 are `margin: 0 auto` | Task C |
| `grid` / `inline-grid` | 2 | element boxes | Task B |
| `list-item` | 2 | element boxes | Task B |
| NBSP-only run reaching the blank-text predicate | **0** | calls to `_is_blank_text` (832) and `_is_blank_text_box` (707) | Task D1 |
| whitespace-only box preserved as a forced break | **0** | white-space-only text boxes (1,287) | Task D1 |
| collapsible spaces removed around a preserved break | **0** | characters in text boxes (80,580) | Task D1 |
| preserved tab measured at `tab-size` | **0** | same | Task D1 |
| CR or CRLF normalised to LF | **0** | same | Task D1 |
| percentage margin or padding in an intrinsic contribution | **0** | intrinsic size computations (45) | Task D1 |
| percentage `width` treated as `auto` for an intrinsic size | 1 | same | Task D1 |
| definite `width` short-circuiting shrink-to-fit | 5 | boxes whose width is shrink-to-fit (50) | Task D1 |
| atomic inline nested inside another atomic inline | 3 | atomic inline boxes (51) | Task D1 |
| CSS Text 3's East Asian segment-break removal | **0** | collapsible segment breaks in text boxes (1,086) | Task D1 |
| `vertical-align: sub` **on a line box** | **0** | boxes aligned on a line box (5,383) | Task D2 |
| `vertical-align: super` on a line box | **0** | same | Task D2 |
| `vertical-align: top` on a line box | **0** | same; 30 element boxes compute it and none is inline-level | Task D2 |
| `vertical-align: bottom` on a line box | **0** | same | Task D2 |
| `vertical-align: <length>` on a line box | **0** | same | Task D2 |
| `vertical-align: <percentage>` on a line box | **0** | same | Task D2 |
| `vertical-align: text-top` on a line box | 1 | same | Task D2 |
| `vertical-align: text-bottom` on a line box | **0** | same; the one element that computes it is inside a float, which is not laid out | Task D2 |
| `vertical-align: middle` on a line box | 7 | same; 43 element boxes compute it | Task D2 |
| a `<percentage>` `vertical-align` resolved at layout time | **0** | Task A2's `vertical_align_percent_deferred` | Task D2 |
| `top`/`bottom` alignment growing the line box | **0** | line boxes (985) | Task D2 |
| a preserved space **hanging** past a line end | **0** | runs of white space at a line end (254) | Task D2 |
| `break-spaces` splitting a run of preserved spaces | **0** | same | Task D2 |
| collapsible white space trimmed at a line **start** | **0** | line boxes (985) | Task D2 |
| an inline box fragmented across a Task B split | **0** | boxes that crossed a line break (322); `boxes_inline_split` is 0 | Task D2 |
| UAX #14 LB9 (a combining mark) reaching line layout | **0** | 58 marks in text boxes, every one inside an out-of-flow subtree | Task D2 |
| `text-align: justify` | **0** | lines aligned (986) | Task D2 |
| the `no break after \|` tailoring firing | **0** | 73 U+007C characters in text boxes | Task D2 |
| U+00AD soft hyphen, where this engine and Chrome differ | **0** | characters in text boxes (80,580) | Task D2 |
| U+200B ZWSP and U+2060 WORD JOINER | **0** | same | Task D2 |
| a viewport-unit `line-height` reaching layout | **0** | line boxes (985) | Task D2 |

### Task E: CSS 2.1 chapter 17

Population for the fixup rows: `fix_up_tables` over the three pages at
1280x1024 with external sheets applied. Population for everything else: the
**27 table boxes that are laid out** -- of the 32 in the tree, 5 sit inside
float or absolutely positioned subtrees this engine declines to lay out --
and the **351 cells** inside them, of 401 in the display census.

| feature | corpus count | population | added |
|---|---:|---|---|
| 17.2.1 remove: a `table-column`'s children | **0** | fixup sites | Task E |
| 17.2.1 remove: a non-column in a `table-column-group` | **0** | same | Task E |
| 17.2.1 remove: white space between two table boxes | **0** | same; Task B's blank-run rule discards it first | Task E |
| 17.2.1 wrap: an anonymous row inside a `table` | 3 | same; all three are Wikipedia `<figure>`s | Task E |
| 17.2.1 wrap: an anonymous row inside a row group | **0** | same; all 24 corpus row groups contain only rows | Task E |
| 17.2.1 wrap: an anonymous cell inside a row | 4 | same | Task E |
| 17.2.1 parent: an anonymous row for an orphan cell | **0** | same; all 401 cells already have a `table-row` parent | Task E |
| 17.2.1 parent: an anonymous table for a misparented row | 1 | same | Task E |
| 17.2.1 parent: ...for a misparented `table-column` | **0** | same | Task E |
| 17.2.1 parent: ...for a misparented row group | 2 | same | Task E |
| 17.2.1 parent: ...for a misparented `table-column-group` | **0** | same | Task E |
| 17.2.1 parent: ...for a misparented `table-caption` | **0** | same | Task E |
| 17.2.1 parent: ...as an `inline-table` | **0** | same; Task B dissolves the inline parent first | Task E |
| `table-layout: fixed` | **0** | tables laid out (27) | Task E |
| `border-spacing` other than `0 0` | **0** | same | Task E |
| a `<col>` or `<colgroup>` in a laid-out table | **0** | same; zero column boxes reach the grid | Task E |
| a table with a caption **above** it | 1 | same | Task E |
| `caption-side: bottom` | 3 | same | Task E |
| `rowspan > 1` | **0** | cells placed (351); zero across all 401 | Task E |
| `colspan` > 2 | **0** | same; all 52 spanning cells are `colspan=2` | Task E |
| `vertical-align: top` on a laid-out cell | **0** | same; 30 cells compute it and every one is inside a float | Task E |
| `vertical-align: middle` or `bottom` on a cell | **0** | same; zero across all 401 | Task E |
| a non-zero margin on a table-internal box | **0** | same; the 2 that declare one declare `0` | Task E |
| an overlapping grid slot (17.5 leaves it undefined) | **0** | same | Task E |
| `padding` on a `table` box (separated model) | 1 | tables laid out (27) | Task E |
| `border-collapse: collapse`, counted and not implemented | 1 | same | Task E |

Four of these deserve a sentence each, because "0" means something
different in each case.

**The fixup rules are all small, and the brief that commissioned this task
said otherwise.** It listed "row whose parent is a `table` -- needs an
anonymous row-group: **96**, genuinely covered" as the one rule with real
coverage. Section 17.2.1 contains no such rule: "A 'table-row' is
misparented if its parent is neither a row group box nor a 'table' or
'inline-table' box", so a row inside a table is correct and generating a
row group around it would add 96 boxes no browser has. The 96 are counted
as `table_rows_directly_in_a_table` (101 including Wikipedia's), and that
is a **denominator**, not a rule. Every actual rule of 17.2.1 is at four or
below.

**Two rules are unreachable rather than merely unexercised**, which is a
stronger statement and was executed rather than inferred. Section 17.2.1's
rules 3 and 4 delete collapsible white space between table boxes; Task B's
blank-run rule (9.2.1.1) already discarded it -- five runs discarded there
and zero here, on the same fixture. The `inline-table` clause needs an
internal table box whose parent box is an `inline`, and Task B's 9.2.1.1
splitting dissolves that parent first. Both are tested from hand-built box
trees, so the rule is tested rather than Task B's ordering.

**The `inline-table` case is also a measured divergence from Chrome.** For
`<span><span style="display:table-cell">x</span></span>` Chrome 151 keeps
the outer `<span>` as an inline box 8x17 and generates an anonymous
inline-table inside it; this engine dissolves the span and generates a
block-level `table`, so the cell leaves the line. Zero corpus occurrences,
and the fix belongs in Task B's splitting rule rather than here.

**`vertical-align: top` on a cell is the `text-bottom` story again.** 30
cells compute it -- and every one is inside a float, which this engine does
not lay out, so the rule fires zero times. This register's own warning that
a small count is one bug fix away from zero, arriving for the second time
by the same route.

**A `border` on a table box is NOT on this list, and nearly was.** The row
was drafted as "a `table` box with a border or padding: 0" from the fact
that `border-spacing` and `<col>` are both zero, and measured before it was
committed: **4** of the 27 laid-out tables carry a border and 1 carries
padding. The border case is genuinely exercised; only the padding is not.
Two adjacent facts about the same element, one true and one false, and the
grep that settled them took one line.

The East Asian row is the only one of the nine that is **not
implemented**. CSS Text 3 section 4.1.2 removes a collapsible segment break
rather than turning it into a space when the characters either side are of
certain East Asian classes; this engine turns every collapsible break into
a space. Measured before deciding to leave it: the corpus contains **18
CJK characters in 80,580**, and of its 1,086 segment breaks, **zero** have
CJK on both sides -- under a deliberately generous codepoint-range
approximation, so a stricter reading of the rule cannot make it more than
zero. It is listed here rather than silently omitted because the row is
what will say when a widened corpus makes it matter.

### Why three of those rows are zero for the same reason

`preserved_break`, "spaces removed around a preserved break" and
"preserved tab" are all **downstream of `white-space: pre` and `pre-line`**,
which the three rows above them already record at zero. They are listed
separately anyway, because they are separate code paths and a later corpus
that gains one `pre-line` element would light some of them and not others.
A single row saying "`pre-line` is 0" would hide that.

The NBSP row is a different shape and the more interesting one. There **are**
36 NBSP-only text boxes on the corpus and 65 boxes containing an NBSP; what
is zero is the number of times one of them reaches a predicate that would
get it wrong. Task B's `_is_blank_text` and Task C's `_is_blank_text_box`
both used `str.strip()`, which calls a run of U+00A0 blank; CSS Text 3 does
not. Both were fixed in Task D1 and **no corpus number moved**, because all
36 sit inside inline formatting contexts where neither predicate is
consulted. The defect was real, latent, and invisible to the corpus -- which
is precisely what this register is for.

## What Task D2 found when it ran

The section below was written **before** D2 was dispatched. It held up, and
the narrowing is worth recording because it makes the gap larger rather than
smaller.

`vertical-align` on **element boxes** is one population and
`vertical-align` **applied on a line box** is another, and only the second
is what baseline alignment does. Measured after D2:

    element boxes with a computed value      applied on a line box
    baseline    7,533                        5,375
    middle         43                            7
    top            30                            0
    text-top        1                            1
    text-bottom     1                            0
    sub/super/bottom/<length>/<percentage>   0    0

Two rows are sharp. **`top`**: 30 element boxes compute it and not one of
them is inline-level, so the rule that aligns a box to the top of its line
box runs zero times. **`text-bottom`**: the single element that computes it
sits inside a float, which this engine does not lay out, so it reaches no
line box either -- this register's own warning that a count of 1 is one
edit from being a count of 0, and here the edit was a bug fix elsewhere in
the same task.

A reader of the first table would have counted three of these as covered.

## Tagged for Task F, before it runs

Flex is the last layout task and has the least corpus coverage relative to
its complexity. Measured before dispatch, so a green suite is read correctly
when it arrives.

**233 flex containers — and 193 of them hold exactly one item.**

    items per container:   0 -> 7    1 -> 193    2 -> 31    3 -> 2

A single-item flex container is nearly indistinguishable from a block
container. `justify-content` has nothing to distribute, `flex-grow` and
`flex-shrink` have no competitor to divide the free space with, and
`order` cannot reorder anything. **Only 33 containers can discriminate any
of it**, and 2 of those are the only ones with a third item.

`align-items` is the exception: it acts on the cross axis and works with one
item, which is presumably why it is also the most declared (19 of 79 flex
declarations are `align-items: center`).

211 of the 233 sit inside another flex container, so nesting is the one axis
the corpus does cover well.

What the stylesheets actually declare, 79 declarations across 36 distinct
values:

    align-items 22   justify-content 12   flex 7   flex-flow 7
    flex-shrink 6    flex-wrap 6          gap 5    flex-grow 5
    column-gap 5     flex-direction 2     flex-basis 1   align-self 1

Two of those were **outside the planned scope** and should not be, or should
be recorded as known divergences rather than discovered ones:

* **`flex-wrap: wrap` occurs 5 times.** The Phase 3 plan defers wrapping and
  lays wrapped containers out as `nowrap`, which misplaces rather than
  crashes — but on five real containers, not zero.
* **`gap` and `column-gap` occur 10 times between them.** Not mentioned in
  the plan at all. Gap is straightforward and its absence moves every item
  in those containers.

Rows to expect in the register after Task F, all currently at zero corpus
occurrences: `order`, `align-content`, `flex-direction: row-reverse` /
`column-reverse`, `align-items: stretch` as an explicit declaration,
`flex-basis` in any unit other than the one occurrence, and every
justify-content value beyond `center`, `flex-end` and `flex-start`.

**None of the eleven flex properties is currently in `ComputedStyle`.** Task
F adds them, as Task C added `overflow`/`float`/`clear`/`position` and Task E
added chapter 17's four. Until it does, every flex container on the corpus
computes `display: flex` and nothing else, so the 205 `flex` boxes in the
display census have never had a flex property applied to them.

## What Task F found when it ran

The section above was written **before** F was dispatched. Its *conclusion*
held -- the corpus cannot discriminate flex layout -- and **every number in
it was over the wrong population**, which made the gap larger, not smaller.

### The populations, and why the brief's figures are not reproducible

Four different denominators, all correct, all called "flex containers"
somewhere:

| population | count | what it is |
|---|---:|---|
| elements computing `flex` or `inline-flex` | **233** | 205 + 28, all on Wikipedia |
| ...of those, producing a box | **201** | 32 sit under a `display: none` ancestor |
| ...of those, **laid out** | **29** | 146 are inside a float and 26 inside an absolutely positioned subtree, neither of which this engine lays out |
| flex **items** placed inside those 29 | **44** | the population every per-item row below counts against |

The tagging section's histogram was `0 -> 7, 1 -> 193, 2 -> 31, 3 -> 2`.
Measured five ways -- DOM children of all kinds, element children only,
element children with `display` not `none`, in-flow element children, and
box-tree children -- **none of them reproduces it**, and every one of them
finds containers with 4, 5, 7 and 11 children that the brief's histogram
has no row for. The closest is element children with `display != none`:

    0 -> 1   1 -> 182   2 -> 6   3 -> 11   4 -> 21   5 -> 8   6 -> 1   7 -> 3

The figure that matters is the one over the boxes that reach the algorithm,
and it is smaller than either:

    items per laid-out container:   1 -> 16    2 -> 11    3 -> 2

16 + 22 + 6 = 44, which is the item count the layout reports, so this
histogram multiplies out to its own population -- the check the brief's
does not pass. **13 containers on this corpus can discriminate anything
about the main axis**, not 33.

This is the unstated-denominator hazard in its ordinary form, and it cost
nothing here only because the conclusion was the same either way.

### What the corpus turned out to reach, and what it did not

`flex-direction` is the sharp one. The corpus's stylesheets contain **six
`column` declarations** (2 `flex-direction`, 4 through `flex-flow`), and
**not one of them wins on any element**: all 233 compute `row`. So column
layout -- half of this task's scope, and the half whose main size is a
height and therefore needs a second code path -- has **zero corpus
occurrences** and is tested synthetically alone.

The two things the plan deferred and the brief asked to be counted or
implemented both turned out smaller than the brief's declaration counts
suggested, and in opposite directions:

* **`flex-wrap: wrap`.** 6 declarations, 3 elements, **2 laid-out
  containers** -- and **zero of them actually wrap**: their items fit on
  one line. The brief said deferring wrapping "misplaces five real
  containers"; measured with a shadow variant that lays every wrapped
  container out as `nowrap`, **0 of 1,460 element rectangles move**.
  Wrapping is implemented anyway, and is synthetic-only coverage.
* **`gap` and `column-gap`.** 10 declarations, and they do reach: **7 of
  the 29 laid-out containers have a non-`normal` `column-gap` and 6 a
  `row-gap`**. Removing gap entirely moves 15 rectangles by up to 20px.
  This one the brief had right.

### Task F: CSS Flexible Box Layout 1

Population for the container rows: the **29 laid-out flex containers**.
Population for the item rows: the **44 items** inside them. Where a row is
about a declaration rather than a used value, the population is the **79
flex declarations** across the three pages' sheets and `<style>` blocks,
at-rules descended into.

| feature | corpus count | population | added |
|---|---:|---|---|
| `flex-direction: column` | **0** | containers laid out (29); 6 declarations exist and none wins | Task F |
| `flex-direction: row-reverse` / `column-reverse` | **0** | flex declarations (79) | Task F |
| `flex-wrap: wrap` | 2 | containers laid out (29) | Task F |
| a container that actually produces **two lines** | **0** | same; both `wrap` containers fit on one line | Task F |
| `flex-wrap: wrap-reverse` | **0** | flex declarations (79) | Task F |
| `align-content` other than `normal` | **0** | containers laid out (29) | Task F |
| `justify-content: space-around` / `space-evenly` / `stretch` | **0** | same; the four values that occur are `center` 6, `flex-end` 3, `end` 2, `space-between` 1 | Task F |
| `justify-content: space-between` with more than one item | **0** | same; the one container that declares it holds a single item | Task F |
| `align-items: baseline` | 2 | same; 3 items aligned, ascents differing by 4.78px in one | Task F |
| an item with **no** baseline reaching baseline alignment | **0** | items aligned by baseline (3) | Task F |
| `align-self` other than `auto` | **0** | items placed (44); 1 declaration exists and does not win | Task F |
| `order` other than `0` | **0** | same; zero declarations of any value | Task F |
| a definite `flex-basis` on an item | **0** | same; all 44 take `auto` | Task F |
| `flex-basis: content` | **0** | same | Task F |
| a **percentage** `flex-basis` | **0** | same; 1 declaration (`70%`) exists and does not win | Task F |
| an item stopped at its automatic minimum size (4.5) | **0** | same | Task F |
| a percentage `row-gap` / `column-gap` | **0** | same | Task F |
| an `auto` margin on a flex item | 4 | same | Task F |
| a **floated** child of a flex container (an item, not a float) | 1 | same | Task F |
| an anonymous flex item generated by *this* module | 1 | containers laid out (29); Task B's 9.2.1.1 generates the other 4 | Task F |
| a blank text run refused an item by *this* module | 4 | same; Task B's blank-run rule takes the rest | Task F |
| `box-sizing: border-box` on a flex item's main size | **0** | items placed (44) | Task F |
| an `inline-flex` reaching the summed intrinsic width | **0** | 28 elements compute `inline-flex` and every one is inside a float or absolute subtree | Task F |

Three of those deserve a sentence.

**The anonymous-item rule is mostly unreachable, and for a familiar
reason.** CSS 2.1 section 9.2.1.1 already wraps a run of inline-level
children in an anonymous block whenever the box also has block-level
children, and Task B implements it -- so `text<div></div>` inside a flex
container arrives at `layout.flex` already wrapped. Flexbox 1 section 4's
rule fires only where 9.2.1.1 does not: when *every* child is inline-level.
That is the same shape as section 17.2.1's rules 3 and 4 being unreachable
behind Task B's blank-run rule, which this register already records, and it
is the second time Task B has quietly done a later task's work.

**`inline-flex` is a count of 1 away from mattering and currently at 0.**
28 elements compute it; every one is inside a subtree this engine declines
to lay out, so the summed intrinsic width -- the largest single behavioural
change this task made to the corpus -- is exercised only through *nested*
containers, never through an inline one. This register's own warning that a
small count is one bug fix away from a different number, arriving by the
same route as `vertical-align: top` on a cell.

**Every "counted, not implemented" row above is zero.** `order`,
`align-content`, the three reverse values and `align-self` are out of scope
per the Phase 3 plan and none of them occurs. The two divergences that *do*
occur are `auto` margins on an item (4) and a floated item (1), and the
second is a case where this engine is more correct than block layout rather
than less.

### Discriminating power, measured

Eight variants, each implementing one rule wrongly, run over the corpus and
diffed against the correct output by **every box rectangle, anonymous and
text boxes included**. A control with no injection diffs to zero.

| wrong rule | element rectangles that move (of 1,460) | largest delta |
|---|---:|---:|
| a row flex container's intrinsic width **maxed** instead of summed (9.9) | **57** | 399.29px |
| `justify-content` ignored, everything at `flex-start` | 25 | 769.97px |
| `gap` ignored entirely | 15 | 20.00px |
| `align-items: baseline` treated as `flex-start` | 1 | 4.78px |
| `flex-wrap: wrap` laid out as `nowrap` (the Phase 3 plan's deferral) | **0** | -- |
| the automatic minimum size (4.5) dropped to zero | **0** | -- |
| `flex: 1` read as `1 1 auto` instead of `1 1 0%` | **0** | -- |

The three zeros are all explained by a counter rather than assumed:
`flex_lines_wrapped` is 0 (neither `wrap` container overflows its line),
`flex_items_clamped_to_min_content` is 0 (no item's flexed target ever
reaches its floor), and no laid-out item carries a non-`auto` `flex-basis`
at all, so the shorthand's famous default has nothing to be famous about
here.

The `baseline` row is the interesting one, and not because it is 1. It
first measured **0**, and the zero was a fact about the instrument: the
diff harness keyed its rectangles by DOM path and skipped every anonymous
and text box, which is exactly what the corpus's two baseline-aligned items
are. See `docs/measurement-hazards.md` instance nineteen.

## Tagged for Task D2, before it runs

`vertical-align` is what baseline alignment is steered by, and the corpus
steers it almost nowhere:

    baseline     7,533
    middle          43
    top             30
    text-top         1
    text-bottom      1
    sub, super, bottom, <percentage>, <length>   all 0

**Baseline alignment therefore has essentially no corpus coverage**, and it
is the part of D2 most likely to be subtly wrong: a mis-aligned baseline
moves text by a few pixels within a correctly-sized line box, which renders
as a page and reads as fine.

Recorded here **before D2 is dispatched**, so that when D2 reports a green
suite and a clean corpus render, the green is understood to cover
`baseline` and almost nothing else. Same reasoning as the split-inline
entry: the machinery is real, the tests are synthetic, and the corpus
cannot tell anyone whether it works.

`baseline` at 7,533 is not reassurance either — it is the default, so the
count mostly measures how many boxes never set the property.

## The inverse finding

The same measurement read the other way is more interesting than the gap
itself. `white-space` values actually present:

    normal    5,480
    nowrap    1,909   (24% of element boxes)
    pre-wrap    219
    pre             0
    pre-line        0

A suite written from CSS 2.1 would treat `pre` as the canonical
non-`normal` case — it is the one the spec introduces first and the one
every tutorial shows. On this corpus it never occurs, while `nowrap`, which
the spec presents as a minor variant, is on nearly a quarter of all element
boxes.

The corpus is three pages and 90% Wikipedia, so this is a fact about those
pages rather than about the web. Widening the corpus is what would turn it
into a claim, and it is exactly the kind of claim Phase 6 exists to make.

### The same distribution over the population that white-space actually acts on

The figures above count **element boxes with a computed `white-space`**.
Task D1's collapser runs over **text boxes**, which is a different and
smaller denominator, and the shape is the same but the numbers are not
interchangeable:

    population: 6,194 text boxes surviving pruning and blank-run discarding

    normal          4,332
    nowrap          1,594   (25.7% of text boxes)
    pre-wrap          268
    pre                 0
    pre-line            0
    break-spaces        0

Recorded beside the element-box figures rather than replacing them, per
`docs/measurement-hazards.md` on the unstated denominator: both are correct
and a reader cannot tell which one a bare "1,909 nowrap" meant.

## The whitespace disposition, Task D1 -- a Phase 6 number

Phase 1 measured whitespace-only text and nothing resolved it until D1
collapsed it. **There are at least three correct denominators** and they
differ by a factor of two, so each is named:

| population | total | whitespace-only | share |
|---|---:|---:|---:|
| DOM text nodes | 7,985 | 2,781 | 34.8% |
| ...the same, under CSS Text 3 rather than `str.strip()` | 7,985 | 2,737 | 34.3% |
| text BOXES after pruning and blank-run discarding | 6,194 | 1,323 | 21.4% |
| ...the same, under CSS Text 3 rather than `str.strip()` | 6,194 | **1,287** | 20.8% |

1,458 of the 2,781 never reach a box: `display: none` prunes some and Task
B's blank-run rule discards 810 more. **Task D1 decided the fate of 1,287,
not of 2,781** -- and the 36-box gap between 1,323 and 1,287 is the NBSP
row above, boxes that are blank to Python and content to CSS.

Of those 1,287:

| disposition | boxes | share |
|---|---:|---:|
| collapsed away entirely | 169 | 13.1% |
| preserved as one separating space | **1,065** | 82.8% |
| preserved verbatim under a preserving `white-space` (all `pre-wrap`) | 53 | 4.1% |
| preserved as a forced break | 0 | 0% |
| none of the above (the residual bucket) | 0 | 0% |

**The Task D plan's expectation was the opposite of the measurement.** It
says "Most collapse away entirely"; 82.8% survive as word separators. The
reason is that the collapsing-away case had already been taken: Task B
discards a blank run *between block siblings* before layout runs, and that
is where most source whitespace lives. What is left in the box tree is
mostly whitespace between inline elements, which is exactly the whitespace
that must not collapse away.

Derived twice, per CLAUDE.md. The second derivation never calls the
collapser: it walks each inline formatting context and asks only whether
content exists before and after each whitespace-only box. It agrees on all
three buckets exactly.

A fourth population, characters rather than boxes: **80,580 characters in
text boxes**, of which 79,270 pass through unchanged, 971 are rewritten
(tab or newline to space) and 339 are removed -- 224 trimmed at the start
of a formatting context, 76 at the end, and 39 collapsed into a preceding
space. Note that the Phase 1 figure quoted as "117,378 characters, 5,671
whitespace (4.8%)" is not a whitespace-character count: 5,671 is the
number of characters *inside whitespace-only nodes*. The whitespace
character count over the same 117,378 is **17,426 (14.8%)**.

## Floats: deferred indefinitely on 2026-08-29, with the number attached

The 79-page survey measured what Phase 3's three pages could not. Share of a
page's boxes inside a float or absolutely-positioned subtree, never laid out:

| stratum | median | pages >= 10% |
|---|---:|---:|
| forum / news / docs / personal | 0.0 - 1.5% | 7 of 32 |
| ecommerce / spa / marketing | 10.5 - 15.7% | 14 of 22 |
| **government** | **30.3%** | 5 of 8 |
| **non-Latin** | **31.0%** | 6 of 6 |
| all 67 laid-out pages | 6.5% | 32 |
| *the three Phase 3 pages* | *0.0%* | *0* |

**Roughly a third of the boxes on government and non-Latin pages are never
laid out, and will render as missing content.** That is the stated cost of
the deferral, recorded here rather than discovered later by whoever reads a
render and assumes a paint bug.

Every claim this register makes about layout coverage is now conditional on
that: a rule reported as "reachable on N pages" is reachable on the
in-flow part of N pages. The gated share is the honest error bar.

See `docs/plans/2026-08-29-phase-3-task-i-floats.md` for the plan and the
reasoning, and `docs/measurement-hazards.md` instances 24 and 25 for how the
number was nearly wrong in both directions.
