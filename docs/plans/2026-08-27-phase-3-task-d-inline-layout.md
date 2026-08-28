# Task D — inline layout and line breaking

Phase 3, after Task C (block layout, merged). **This is the largest task in
the phase** and the plan recommends splitting it into **two dispatches**.

## Why it is the largest

11,041 inline-level boxes against 1,395 block-level ones. Measured over the
corpus at 1280x1024, population = boxes surviving `display:none` pruning:

| | |
|---|---:|
| text boxes | 6,194 |
| of those, whitespace-only | 1,323 |
| words | 13,876 |
| characters | 80,580 |

Task C resolved 1,395 widths. Task D determines the geometry of roughly
eight times as many boxes, and every block's `height: auto` depends on it —
687 boxes currently have height 0 pending this task.

## Split into two dispatches

The seam is clean and it is **not** where a naive split would put it.

### D1 — measurement, white-space, intrinsic sizing

* `measure(text, style) -> float` over `hmtx`, the single font seam.
* White-space collapsing per CSS Text 3.
* `intrinsic.py`: `min_content_width` and `max_content_width`, implemented
  against the stubs Task C left, plus §10.3.5's shrink-to-fit formula.

### D2 — line boxes

* Line breaking, line box construction, inline fragments.
* Baseline alignment and `vertical-align`.
* Block `height: auto` over inline content.

### Why here

**D1 unblocks Tasks E and F; D2 does not.** Automatic table layout needs
min-content and max-content of cells; `flex-basis: auto` needs the same of
flex items. Neither needs a line box. Splitting here means E and F can be
planned against a finished D1 while D2 is still running, instead of the
whole phase queueing behind line breaking.

D1 is also independently testable: a width for a text run and a min/max
content size are numbers that can be compared against Chrome without any
line box existing. D2 is where the wall-clock risk sits, so it should not
carry work that has no dependency on it.

Task C's own deferrals partition the same way: `widths_deferred_shrink_to_fit`
(50) is D1's, and `heights_deferred_inline_content` (687) is D2's.

## Where the corpus cannot discriminate

Measured, so the coverage gap is a number rather than a hope. Same
discipline as Tasks B and C, where the corpus would have passed any
implementation.

**`vertical-align` — the worst gap in the phase.** Values present:

    baseline 7,533   middle 43   top 30   text-bottom 1   text-top 1

`sub`, `super`, `bottom`, and — critically — **every `<percentage>` and
`<length>` value appear zero times**. Task A2 built percentage resolution
against the used `line-height`, and Task C's deferral counter for it reads
0 because nothing in the corpus exercises it. That code path has **never
been run against real input** and cannot be. Synthetic tests are the only
coverage it will ever have, and `text-bottom` and `text-top` at one
occurrence each are a single Wikipedia element away from being untested too.

**`white-space`.** Present: `normal` 5,480, `nowrap` 1,909, `pre-wrap` 219.
Absent: `pre`, `pre-line`, `break-spaces` — all zero. `nowrap` at 24% of
elements is heavily exercised and `pre` is not exercised at all, which is
the reverse of what a test suite written from the spec would assume.

**Line-height kinds are the one thing the corpus does cover well**: unitless
numbers 3,544, lengths 2,679, `normal` 1,385. All three paths are live, and
the unitless-inherits-as-a-number rule is genuinely exercised.

**Deep inline nesting is thin.** Text boxes by inline nesting depth:
1,853 / 1,272 / 1,946 / 597 / 512 at depths 0-4, then **10** at depth 5 and
**4** beyond. Fragmenting a deeply nested inline across a line break is
where the fragment representation earns its keep, and 14 boxes will not
find a bug in it.

**Nothing to compare fragments against.** After Task C's correction there
are **0 genuinely split inlines in the corpus** — every one of the 31 is a
dissolved atomic box. So the fragment machinery, which the Chrome contract
was designed around, has no corpus instance at all. Synthetic only.

**No floats, so no line shortening.** Per the partial-implementation
principle in the Phase 3 plan: lines must be full width, because clearance
and float avoidance need floats this engine does not lay out. Implementing
line shortening with nothing to shorten against is the `clear` trap again.

## What D2 must get right that is invisible

* **Whitespace-only text boxes.** 1,323 of 6,194. Most collapse away
  entirely; a text node between two inline elements is a real word
  separator and must not. Task B already declines to wrap all-blank runs in
  anonymous blocks — D2's collapsing must agree with that decision rather
  than re-deriving it.
* **`line-height` is a number, not a length.** A unitless value inherits as
  the number and multiplies by the element's **own** font size at use time.
  Resolving it at cascade time is a defect A2 deliberately avoided; D2 must
  not undo it.
* **Baseline alignment across differing font sizes.** The corpus has all
  three line-height kinds but the interesting case is a line box containing
  boxes of different font sizes, where the line box's height is not any
  single child's.

## The Chrome comparison harness

D2's deliverable, because it is what needs numeric comparison at scale.
Task C already compared 34 fixtures against Chrome 151 ad hoc; that code
should become the harness rather than being rewritten.

It must honour the contract in the Phase 3 plan: `getContentQuads` for
inline boxes (one quad per fragment), `getBoxModel` for block-level, the
startup assertion pinning `model.width` to the border box, the two-identifier
scheme, and the `non_comparable` list — 31 dissolved inlines, which CDP will
answer for and we have no box for.

## Testing discipline

Unchanged, and now with three tasks of evidence behind it: injection
testing mandatory with the shadow verified and no-op injections discarded;
counters seeded at zero; every reported number carrying its population; and
mechanical checks rather than vigilance — a line-box invariant in the shape
of Task C's constraint assertion, asserted on every line box rather than
only under test.
