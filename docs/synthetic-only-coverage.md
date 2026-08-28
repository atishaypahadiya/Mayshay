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
