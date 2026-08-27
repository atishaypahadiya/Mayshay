# Task C — block layout

Read `CLAUDE.md`, then
`docs/plans/2026-08-27-phase-3-task-c-block-layout.md` (your full spec),
then `docs/measurement-hazards.md`, then `docs/percentage-resolution.md`.

The plan is authoritative. This brief adds only what a plan cannot: the
discipline, the baseline, and the reason the tests are shaped as they are.

## What you are building

Positions and sizes for block-level boxes in a block formatting context, on
the box tree Task B produces (`src/mayshay/layout/boxtree.py`). Inline
content is Task D — measure nothing textual. Width and height resolution,
`margin: auto`, `box-sizing`, and margin collapsing in full.

## Why the tests are shaped the way the plan says

At least ten tests on this project have asserted less than their names
implied, and the only reliable detector has been injection testing. Three
places in the plan specify a test shape rather than leaving it open,
because the shape of the *wrong* test is already known:

* **Margin signs.** A test using only positive margins passes under
  `max()`, under `sum()` when an operand is zero, and under several other
  wrong rules. Test positive/positive, negative/negative and mixed.
* **`margin: auto`.** Assert the resulting `margin-left` and
  `margin-right` values, not the box position. "Over-constrained, margin-
  right ignored" and "centred" are indistinguishable by position whenever
  the numbers coincide.
* **Percentage margins.** Use a container whose width and height differ
  obviously — 400x800, so the two candidate rules give 40 and 80. A 400x400
  container cannot tell them apart.

Do not simplify these into single-case tests that happen to pass. That is
the failure being pre-empted.

## Measured facts you may rely on

All verified against Chrome 151 through CDP. Do not re-derive them from
spec text; do re-run them if you doubt one.

* `margin-top: 10%` in a 400x800 container is **40px** — percentages
  resolve against the containing block's **width**, vertical ones included.
* Collapse-through is unaffected by the box's own margins: no declared
  margin, `margin: 0` and `margin: 0%` behave identically.
* Between two siblings each with `margin: 30px 0` in a 400px container, an
  empty middle block gives: `margin:10%` -> 40px gap; `margin:0` -> 30px;
  `margin:10%; padding:1px` -> 82px; `margin:10%; height:1px` -> 81px.

## Discipline

* **Injection testing is mandatory.** Shadow the source onto `PYTHONPATH`,
  print `module.__file__` to prove the shadow is what imports, inject a real
  defect, confirm a test fails. Discard no-op injections rather than
  reporting them as evidence. Report the full table.
* **Tests are synthetic, from CSS 2.1 section 8.3.1's cases.** The corpus
  will not exercise the edge cases — Task B measured 28 anonymous-box sites
  in 8,593 elements and would have passed any implementation. **Measure how
  many of each collapsing shape the corpus contains and report it**, so the
  coverage gap is a number rather than a hope.
* **Every barrier gets a negative test.** Over-collapsing produces a
  plausible, slightly-too-tight page and only a negative test catches it.
* **A constraint-equation assertion on every box**, in the shape of Task
  A2's `seen == kept + dropped`. Mechanical checks are the only thing that
  has ever caught this class here; vigilance has caught none of it.
* **Counters seeded at zero**; every reported number carries its
  population named.
* Non-ASCII in test data as escapes, never literals.

## Environment

* Do NOT modify `.venv/`. Do NOT uninstall anything.
* Never import `tinycss2`, `webcolors`, `cssutils`, `cssselect` or
  `matplotlib` from `src/` or a committed test.
* `.venv/bin/pytest` with **no** `-q`.
* Never `git submodule update --remote`.
* Scratch in `/Users/atishaypahadiya/.claude/jobs/604b9f51/tmp`.
* **Stage explicit paths. Never `git add -A`** — the coordinator edits docs
  in this tree while you work; a blanket add sweeps their work into your
  commits, which happened in Task A2 and cost a history rewrite.
* Baseline: **6664 passed, 7 skipped, 72 xfailed**. Verify it yourself.

## Done when

* Widths, heights, `margin: auto` and `box-sizing` resolve per §10.3.3 and
  §10.6.3, with the over-constrained case ignoring `margin-right` in LTR.
* Margin collapsing implements every adjoining rule and every barrier in the
  plan, each with a positive and a negative test.
* The constraint equation is asserted on every box after layout.
* Boxes carry all four edges in absolute document coordinates per the Phase
  3 plan's comparison contract, and the `non_comparable` list from Task B is
  honoured.
* Full suite green. Report includes the injection table, the corpus census
  of collapsing shapes with populations named, and every defect you find in
  this brief or the plan — the author's briefs have produced defects that
  reached implementation in every phase so far, and finding one is a
  success.
