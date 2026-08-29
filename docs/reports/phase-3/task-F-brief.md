# Task F — flex layout subset

The last layout task in Phase 3. Read `CLAUDE.md`, then
`docs/plans/2026-08-27-phase-3-layout.md` (Task F, and the
partial-implementation principle), then `docs/measurement-hazards.md`, then
`docs/synthetic-only-coverage.md` — its "Tagged for Task F" section is
about you and was written before you started.

## First: none of the flex properties exists

`ComputedStyle` has **none** of `flex-direction`, `flex-wrap`,
`justify-content`, `align-items`, `align-self`, `align-content`,
`flex-grow`, `flex-shrink`, `flex-basis`, `order`, `gap`. Add them to the
cascade first, as Task C added `overflow`/`float`/`clear`/`position` and
Task E added chapter 17's four. Until you do, the 205 `flex` boxes in the
display census have never had a flex property applied to them.

Mind the shorthands: `flex` is `<grow> <shrink>? <basis>?` with the
famously irregular defaults (`flex: 1` means `1 1 0%`, not `1 1 auto`),
`flex-flow` is `<direction> || <wrap>`, and `gap` is `<row> <column>?`.
Seven `flex` and seven `flex-flow` declarations are in the corpus, so these
are exercised.

## The corpus cannot discriminate most of this

Measured before dispatch. **233 containers, and 193 hold exactly one item.**

    items per container:   0 -> 7    1 -> 193    2 -> 31    3 -> 2

A one-item flex container behaves almost exactly like a block container.
`justify-content` has nothing to distribute; `flex-grow` and `flex-shrink`
have no competitor to share free space with; `order` cannot reorder
anything. **Only 33 containers can discriminate any of it, and only 2 have a
third item.**

`align-items` is the exception — it acts on the cross axis and works with a
single item, which is why 19 of the 79 flex declarations in the corpus are
`align-items: center`.

So plan your tests from CSS Flexbox 1 directly, expect the corpus to confirm
almost nothing, and **say so in your report** rather than offering a clean
render as evidence. Three tasks have now done this and it is the house
convention.

211 of the 233 containers are nested inside another flex container, so
nesting is the one axis the corpus covers well. Use it.

## Two things the plan left out that the corpus uses

* **`flex-wrap: wrap` occurs 5 times.** The plan defers wrapping and lays
  wrapped containers out as `nowrap`. That is a defensible partial
  implementation, but it misplaces five real containers, not zero. Either
  implement single-axis wrapping or count it explicitly — and per the
  partial-implementation principle, do not half-implement it in a way that
  is wrong on the cases you can reach.
* **`gap` and `column-gap` occur 10 times.** The plan does not mention gap
  at all. It is straightforward and its absence moves every item in those
  containers. Implement it.

## Build on `intrinsic.py`

`flex-basis: auto` resolves to the item's content size, which is
`max_content_width` — the same computation Task C's shrink-to-fit and Task
E's column widths use. `layout.intrinsic` is Chrome-verified. **Do not write
a fourth min-content.**

## Scope

In: `flex-direction` row and column, `justify-content`, `align-items`,
`align-self`, `flex-grow` / `flex-shrink` / `flex-basis` resolution on the
main axis, `gap`, and single-line layout.

Out, each counted: `order`, `align-content`, `row-reverse` /
`column-reverse`, and — unless you implement it — wrapping. Report which of
these have zero corpus occurrences; most do.

## Discipline

* Injection testing mandatory, shadow verified by printing
  `module.__file__`, no-op injections discarded and replaced. Task E had
  three no-ops because every colspan fixture shared `border-spacing: 0` —
  vary what your fixtures *share*, not just their inputs.
* **Fixtures for anything touching traversal, ordering or identity need at
  least three levels of nesting with siblings at more than one level.** Task
  B's ordinal bug survived 7,058 tests because every fixture was one `<div>`
  deep. This is now a CLAUDE.md rule and flex `order` is exactly the kind of
  thing it exists for.
* A mechanical check in the shape of Task C's constraint assertion and Task
  E's column sum: free space distributed equalling free space available is
  the obvious candidate.
* **Where it is cheap, measure discriminating power with a shadow build**,
  not just occurrence count — see the register's new section. Task E found a
  factor of six between two plausible wrong colspan rules that an occurrence
  count could not have revealed.
* Counters seeded at zero; every number reported with its population named.
* Non-ASCII in test data as escapes.

## Environment

* Do NOT modify `.venv/`. Do NOT uninstall anything.
* Never import `tinycss2`, `webcolors`, `cssutils`, `cssselect`,
  `matplotlib` from `src/` or a committed test. `fontTools` is permitted in
  `layout/`; Pillow is not.
* `.venv/bin/pytest` with **no** `-q`.
* Never `git submodule update --remote`.
* **Stage explicit paths. Never `git add -A`.**
* Scratch in `/Users/atishaypahadiya/.claude/jobs/604b9f51/tmp`.
* **Commit more often than feels necessary.** Two agents have stalled on
  this project and a stall loses only uncommitted work.
* Baseline: **7060 passed, 7 skipped, 72 xfailed**. Verify it yourself.

## Done when

* The eleven flex properties are in the cascade with correct initial values
  and shorthand expansion.
* Single-line flex layout works: direction, justification, alignment,
  grow/shrink/basis, gap.
* Tests are synthetic, from Flexbox 1, and the report says what the corpus
  did and did not confirm.
* Full suite green. Report includes the injection table, the flex census
  with populations named, discriminating power where you measured it, new
  register rows, and every defect you find in this brief or the plan.
