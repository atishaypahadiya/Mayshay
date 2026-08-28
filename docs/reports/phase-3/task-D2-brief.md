# Task D2 — line boxes, breaking, baseline alignment

Read `CLAUDE.md`, then
`docs/plans/2026-08-27-phase-3-task-d-inline-layout.md`, then
`docs/measurement-hazards.md` (especially instance fourteen — **it is about
the specification you are implementing**), then `docs/fonts.md`, then
`docs/synthetic-only-coverage.md`.

## Scope

D1 delivered `measure()`, white-space collapsing and intrinsic sizing. D2
is what sits on them:

* Line breaking at the opportunities UAX #14 provides, greedy.
* Line box construction; inline boxes fragmenting across breaks.
* Baseline alignment and `vertical-align`.
* `height: auto` on blocks containing inline content — Task C's 687
  deferred heights.
* CSS Text 3 Phase II trimming, hanging, `pre-wrap` vs `break-spaces`,
  which D1 explicitly left because they need a line box.

## The specification you are standing on defers, and that has already bitten

CSS Text 3 does not define line break opportunities. It **points at UAX
#14**, and D1 lost a number to exactly this: `min-content` for
`a<inline-block>b` came out 57.81 where Chrome gives 40.00, because there is
a break opportunity either side of an atomic inline. Reading CSS Text 3
carefully *supports the wrong answer*; the rule is UAX #14's LB20, where
U+FFFC is class CB.

> A specification that defers to another is a pointer, not a summary.
> Reading the citing layer carefully produces a confident wrong answer,
> which is worse than reading it carelessly.

You will hit this repeatedly. **When a rule turns out to be delegated, read
the delegate or measure against Chrome — do not read the CSS text more
carefully.**

## Baseline alignment: the corpus discriminates nothing

Measured, and it is the worst coverage gap in the phase.
`vertical-align` values present across all element boxes:

    baseline     7,533      <- the INITIAL value
    middle          43
    top             30
    text-top         1
    text-bottom      1
    sub, super, bottom, <percentage>, <length>      all 0

`baseline` at 7,533 is **not** reassurance. It is the initial value, so that
count is a census of boxes that never set the property. The corpus does not
exercise baseline alignment 7,533 times; it declines to exercise it 7,533
times.

So: **a green suite and a clean corpus render mean almost nothing here.**
Plan these tests from CSS 2.1 §10.8 and §10.8.1 directly, and expect the
corpus to find nothing. State that in your report rather than citing a clean
render as evidence.

The failure mode is the invisible kind: a mis-aligned baseline moves text a
few pixels inside a correctly-sized line box, which renders as a page and
reads as fine. Numeric comparison against Chrome is the only thing that will
catch it — `getContentQuads`, one quad per fragment.

Cases worth constructing, none of which the corpus has: a line box mixing
two font sizes (the line box height is not any single child's); `sub` and
`super`; a percentage `vertical-align` against a numeric `line-height`,
against a length one, and against `normal` (Task C resolves the first two
and defers the third — see `docs/percentage-resolution.md`); `text-top` and
`text-bottom` against a font whose ascent and text-ascent differ.

## `line-height` — do not undo A2

A unitless `line-height` inherits **as a number** and multiplies by the
element's **own** font size at use time. Resolving it at cascade time is a
defect Task A2 deliberately avoided and Task C preserved. The corpus does
cover this well — unitless 3,544, lengths 2,679, `normal` 1,385, all three
paths live.

`normal` resolves from the font: `(hhea.ascent - hhea.descent +
hhea.lineGap) / unitsPerEm` = 1.1499 em = 18.398438px at 16px. All four
candidate vertical-metric interpretations are tabulated in `docs/fonts.md`;
if a Chrome comparison comes back off by roughly 3%, 5% or 18%, that table
names which one the other engine used.

## No floats, so no line shortening

Per the partial-implementation principle in the Phase 3 plan: this engine
lays out no floats, so **lines are full width**. Implementing float
avoidance with nothing to avoid is the `clear` trap that Task C caught —
it would make us disagree with a browser on every case we can reach in
order to agree on one we cannot.

## Whitespace, already decided

D1 measured the disposition of the 1,287 whitespace-only boxes: 169 collapse
away, 1,065 (82.8%) survive as a separator, 53 preserved verbatim. **Do not
re-derive this.** Phase II trimming is yours, but the Phase I decisions are
made and their conservation is asserted mechanically — if your work changes
those counts, something is wrong.

Note that `str.strip()` is **not** CSS Text 3's whitespace set. U+00A0 is
content: real advance, never collapses, never a wrap opportunity. That
distinction was a live latent defect in Tasks B and C, invisible because the
corpus contains zero NBSP-only runs.

## Discipline

* **Injection testing mandatory.** Shadow verified by printing
  `module.__file__`, real defects, no-ops discarded and replaced rather than
  reported. D1 found three no-ops on its first pass and wrote tests for
  them.
* A **mechanical check** in the shape of Task C's constraint assertion and
  D1's character conservation: something that fails loudly when a line box's
  contents do not account for its extent, or when a `vertical-align` value
  is added and forgotten.
* Counters seeded at zero; every number reported with its population named.
* Non-ASCII in test data as escapes, never literals.
* Add rows to `docs/synthetic-only-coverage.md` for anything you implement
  that the corpus does not exercise. Expect several — baseline alignment
  alone will produce many.

## Environment

* Do NOT modify `.venv/`. Do NOT uninstall anything.
* Never import `tinycss2`, `webcolors`, `cssutils`, `cssselect` or
  `matplotlib` from `src/` or a committed test. `fontTools` is permitted in
  `layout/` for font metrics; Pillow is **not** — rasterization is Phase 4.
* `.venv/bin/pytest` with **no** `-q`.
* Never `git submodule update --remote`.
* Scratch in `/Users/atishaypahadiya/.claude/jobs/604b9f51/tmp`.
* **Stage explicit paths. Never `git add -A`** — the coordinator edits docs
  in this tree while you work.
* Scripts here put the repo's own `src/` ahead of `PYTHONPATH`, so a shadow
  import can silently not take. Print `__file__`.
* Baseline: **6886 passed, 7 skipped, 72 xfailed**. Verify it yourself.

## Done when

* Lines break at UAX #14 opportunities; inline boxes fragment across them
  with one `fragment` index each, per the Chrome contract.
* Baseline alignment and `vertical-align` implemented, tested from §10.8
  synthetically, and reported as corpus-unvalidated.
* Task C's 687 deferred heights resolve.
* Full suite green. Report includes the injection table, the line-box
  census with populations named, new register rows, and every defect you
  find in this brief or the plan.
