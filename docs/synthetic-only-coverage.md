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

## Register

Corpus at 2026-08-27: three pages, 8,593 DOM elements, 7,639 producing a
box, viewport 1280x1024, `@media` evaluated, external sheets applied.

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
| `vertical-align: text-bottom` on a line box | 1 | same | Task D2 |
| `vertical-align: middle` on a line box | 8 | same; 43 element boxes compute it | Task D2 |
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
    baseline    7,533                        5,383
    middle         43                            8
    top            30                            0
    text-top        1                            1
    text-bottom     1                            1
    sub/super/bottom/<length>/<percentage>   0    0

`top` is the sharp one: 30 element boxes compute it and **not one of them is
inline-level**, so the rule that aligns a box to the top of its line box
runs zero times on this corpus. A reader of the first table would have
counted `top` as covered.

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
