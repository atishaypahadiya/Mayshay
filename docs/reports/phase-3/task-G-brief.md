# Task G — the twelve pages that crash the layout

Its own task and its own diff. Not folded into float work: ten of the twelve
are one assertion in code that shipped a week ago, in the exact path the
register said had **zero corpus coverage**, and that deserves to be
reviewable on its own.

Read `CLAUDE.md`, then `docs/plans/2026-08-29-corpus-widening.md`, then
`docs/synthetic-only-coverage.md` (the Task F section, whose
`flex-direction: column` row read **0** before the survey and reads **353
across all nine strata** after).

## The population

**12 of 79 collected pages, across 7 of 9 strata.** Not one site's markup.

| family | n | where |
|---|---:|---|
| `justify-content spent 0.0 of N available free space` (Flexbox 1 §9.5) | 10 | docs, ecommerce ×3, gov ×2, marketing, news ×3 |
| `min-content must not exceed max-content` (intrinsic sizing) | 1 | ecommerce |
| other `AssertionError` | 1 | spa |

Every figure in the survey report is over **67 laid out**, not 79, because
of these. That is a 15% hole in the corpus that the widening exists to fill.

## The assertion is right; the input is wrong

The question asked at dispatch was whether `spent 0.0 of N` is a legitimate
state the assertion forbids, or a computation gone wrong. Measured on
`quantamagazine.org/physics`:

    container   display:flex; flex-direction:column; justify-content:center
                width:auto; height:auto
    box tree    2 block children
    flex plan   1 line, **1 item**, outer main size **0.0**
    geometry    content height **18.4**

Two things cannot both be true. A column container's content height is the
sum of its items' outer main sizes plus gaps; it is 18.4 and the plan's
items sum to 0.0. **The plan does not describe the geometry**, so the
assertion is reporting a real inconsistency rather than refusing a legal
state.

Note also: two in-flow block children, one item. That is a second
discrepancy in the same container and may be the same cause or a different
one.

Two candidate causes, and the task must decide between them by measurement
rather than by picking the likelier-sounding one:

1. **A child that should be a flex item was not collected.** Two block
   children, one item. If so, `flex_items_placed` has been undercounting on
   every affected page and the item census in the register is wrong.
2. **A column item's main size is stale.** A column item's main size is a
   *height*, which is only resolved when the item is laid out — after the
   plan records its base size. A row item's main size is a width, known
   before. That asymmetry is exactly why column direction needs its own code
   path, and column direction is the feature that had zero corpus coverage
   when Task F was reviewed.

A minimal synthetic reproduction — a column container, `height: auto`,
`justify-content: center`, one child with a definite height — **passes**.
The trigger needs something the real pages have and the obvious fixture does
not, which is the whole argument for the next section.

## Fixtures: the failing pages, named

**Do not reproduce these from memory or from a simplified sketch.** The
simplified sketch already passed. Take the smallest subtree of each failing
page that still asserts, and commit it as a fixture with its source URL and
the page's collection.

* One fixture per distinct *cause*, not per failing page — but derive each
  one from a named page, and record which of the 12 it came from.
* Fixtures go in `tests/layout/fixtures/` with a header giving the URL, the
  collection (`2026-08-29-survey`), and the assertion text.
* Per CLAUDE.md's nesting rule, keep the real nesting depth. The
  Quanta container sits 7 levels down; a two-level reduction is a different
  shape and may not reproduce.

The 12 slugs are in `data/corpus/2026-08-29-survey/collection.json`; the
assertion text for each is in `docs/reports/corpus-2026-08-29/survey.json`
under `crashes`.

## Done when

1. All 12 pages lay out. The measurement is `67 -> 79`, run the same way.
2. A fixture exists for each distinct cause, derived from a named page.
3. The register's flex item and container counts are **re-measured**, not
   adjusted: if cause 1 holds, `flex_items_placed` was undercounting and the
   Task F census figures are wrong wherever a column container appears.
4. If either assertion was also incomplete — for instance if an indefinite
   main size makes free space zero by definition and the check does not say
   so — that is fixed too, and separately, and said so in the message.
5. Full suite green.

## What this is not

* **Not a float task.** If a fix here touches float or absolute handling,
  stop and say so rather than starting Phase 3's next task inside this one.
* **Not a rewrite of `flex.py`.** Ten crashes on one assertion is one defect
  family, most likely one cause. Find it before changing shape.
* **Not licence to weaken the assertion.** It found a real inconsistency on
  the first wide corpus it ever saw, which is the strongest evidence
  available that it should stay. Weakening a check to make a page pass is
  the failure this repo's whole hazards document is about.
