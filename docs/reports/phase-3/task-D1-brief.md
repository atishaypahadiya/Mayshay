# Task D1 — text measurement, white-space collapsing, intrinsic sizing

Read `CLAUDE.md`, then
`docs/plans/2026-08-27-phase-3-task-d-inline-layout.md` (your spec — you
are **D1 only**, not D2), then `docs/fonts.md`, then
`docs/measurement-hazards.md`, then `docs/synthetic-only-coverage.md`.

## Scope — D1 only

1. **`measure(text, style) -> float`**, the single font seam. Advances from
   the vendored font's `hmtx` table via `fontTools`. Not
   `PIL.ImageFont.getlength`, which returns integer-rounded advances — see
   `docs/fonts.md` for the measurement that settled it.
2. **White-space collapsing** per CSS Text 3.
3. **`src/mayshay/layout/intrinsic.py`** — implement the
   `min_content_width` / `max_content_width` stubs Task C left, plus CSS 2.1
   §10.3.5's shrink-to-fit formula, and wire Task C's 50
   `widths_deferred_shrink_to_fit` boxes to it.

**Not D1:** line breaking, line boxes, baseline alignment, `vertical-align`,
block heights over inline content. Leave them. D1 exists as a separate
dispatch because Tasks E and F depend on intrinsic sizing and not on line
boxes; adding line-box work here defeats the split.

## The font

`data/fonts/LiberationSans-Regular.ttf`, Liberation Sans 2.1.5, SHA-256 in
`docs/fonts.md`. Every metric decision in that file lands at your `measure()`
seam and nowhere else: `hmtx` not `getlength`, `hhea` not either `OS/2`
convention, kerning deliberately omitted at a measured +0.137%. Three call
sites would be three places for one to drift. Keep it one function.

`fontTools` is permitted in `layout/` for exactly this, per CLAUDE.md. It
must not make layout decisions.

## Report the whitespace disposition — this closes a Phase 1 loop

Phase 1 measured whitespace-only text and nothing has resolved it since.
D1 is where each such node either collapses away entirely or survives as a
word separator. **Report the disposition with populations named**, because
there are at least three correct denominators here and they differ a lot:

    all text nodes in the DOM        7,985   whitespace-only 2,781  (34.8%)
    all characters                 117,378   whitespace      5,671  ( 4.8%)
    text BOXES after pruning         6,194   whitespace-only 1,323  (21.4%)

The third is your population: 1,458 of the 2,781 are already gone before
you run — pruned by `display:none` or discarded by Task B's blank-run rule.
**You decide the fate of 1,323, not 2,781.** Do not report the Phase 1
figure as though D1 resolved it.

Split your 1,323 into: collapsed away entirely; preserved as a single
separating space between inline content; preserved verbatim under a
preserving `white-space` value. That split is a Phase 6 number.

## Add to the synthetic-only register

`docs/synthetic-only-coverage.md` is a standing list of paths implemented,
tested, and never exercised by real input. It already names `white-space:
pre`, `pre-line` and `break-spaces` at zero corpus occurrences.

**Add every further one you find**, with its corpus count and the
population named. A count of 1 or 2 belongs in the register too: it is one
edit from zero and cannot discriminate between implementations.

The inverse reading matters as much: `nowrap` is on 24% of element boxes
while `pre` is on none, so a suite written from CSS 2.1 would weight these
exactly backwards. If your measurements produce more of that shape, record
it in the same file.

## Discipline

* **Injection testing mandatory.** Shadow onto `PYTHONPATH`, print
  `module.__file__` to prove the shadow imports, inject a real defect,
  confirm a test fails. Discard no-ops rather than reporting them.
* **Counters seeded at zero.** Every reported number carries its
  population.
* A **mechanical check**, in the shape of Task C's constraint assertion:
  something that fails loudly when a white-space value is added and
  forgotten, or when collapsed and preserved characters do not account for
  the input. Vigilance has caught none of this class on this project;
  mechanical checks have caught all of it.
* Non-ASCII in test data as escapes, never literals. You will be handling
  NBSP (U+00A0), which **does not collapse**, and it is indistinguishable
  from a space in a terminal.

## Environment

* Do NOT modify `.venv/`. Do NOT uninstall anything.
* Never import `tinycss2`, `webcolors`, `cssutils`, `cssselect` or
  `matplotlib` from `src/` or a committed test.
* `.venv/bin/pytest` with **no** `-q`.
* Never `git submodule update --remote`.
* Scratch in `/Users/atishaypahadiya/.claude/jobs/604b9f51/tmp`.
* **Stage explicit paths. Never `git add -A`.**
* Baseline: **6735 passed, 7 skipped, 72 xfailed**. Verify it yourself.
* Beware: scripts here put the repo's own `src/` ahead of `PYTHONPATH`, so a
  shadow import can silently not take. Task C hit this and read an
  exactly-unchanged result as a finding. Print `__file__`.

## Done when

* `measure()` exists, reads `hmtx`, and its numbers match `docs/fonts.md`'s
  recorded sample advances exactly.
* White-space collapsing is implemented and the 1,323 dispositions are
  reported with populations named.
* `intrinsic.py` is implemented and Task C's 50 deferred shrink-to-fit
  widths resolve.
* `docs/synthetic-only-coverage.md` has any new rows you found.
* Full suite green. Report includes the injection table, the whitespace
  disposition, the corpus numbers with populations, and every defect you
  find in this brief or the plan.
