# Task H — floats, and everything that assumed they did not exist

Phase 3's last large layout feature, and the one the three-page corpus made
look deferrable. Sequenced **after Task G** (the twelve crashing pages): a
float diff landing on a corpus where 15% of pages do not lay out cannot be
measured.

Read `CLAUDE.md`, then `docs/plans/2026-08-27-phase-3-layout.md` (the
partial-implementation principle), then `docs/measurement-hazards.md`
instances 24 and 25 — both are about this decision.

## Why this is not deferrable, measured

Share of a page's boxes inside a float or absolutely-positioned subtree, and
therefore never laid out. Per stratum, aggregate last:

| stratum | pages | median | mean | max | ≥10% |
|---|---:|---:|---:|---:|---:|
| forum | 8 | 0.0% | 2.8% | 21.9% | 1 |
| news | 6 | 0.3% | 6.6% | 23.9% | 2 |
| docs | 9 | 0.9% | 13.7% | 98.5% | 2 |
| personal | 9 | 1.5% | 22.7% | 99.1% | 2 |
| ecommerce | 7 | 10.5% | 23.5% | 56.0% | 5 |
| spa | 7 | 11.9% | 41.7% | 93.3% | 5 |
| marketing | 7 | 15.7% | 20.2% | 54.6% | 4 |
| gov | 8 | **30.3%** | 33.8% | 97.9% | 5 |
| nonlatin | 6 | **31.0%** | 45.0% | 95.6% | 6 |
| **all** | **67** | **6.5%** | **22.8%** | **99.1%** | **32** |
| *the three Phase 3 pages* | *3* | *0.0%* | *3.5%* | *10.6%* | *0* |

**The pooled median describes no stratum.** The distribution is bimodal —
four strata at 0.0–1.5%, five at 10.5–31.0% — so a single 6.5% figure is
the average of two populations rather than a description of either. Five of
nine strata sit at or above the pre-registered 10% threshold, 32 of 67 pages
do, and 72% of pages have some gated content.

The last row is the finding worth keeping in view: the corpus that made this
work look deferrable sat at the floor of the distribution it stood in for.

## Where the existing code assumes floats do not exist

Each of these is a decision that was correct under "no floats" and becomes
wrong the moment one is placed. They are listed because a float
implementation that fixes only `block.py` will leave a green suite and a
wrong page.

### 1. Lines are full width (`layout/linebox.py`, module docstring)

> "This engine lays out no floats, so nothing shortens a line."

The central one. Line boxes are laid out at the full content width of their
containing block. With floats, a line box's available width is the content
width minus the float bands that intersect its vertical extent — and that
is a per-line quantity, not a per-block one, so it changes the shape of the
line-breaking loop rather than one number fed into it.

Two consequences that are easy to miss:

* **Line height feeds back into which floats intersect.** A line's height
  is known only after its content is measured, but which floats it must
  avoid depends on its vertical extent. CSS 2.1 §9.5 resolves this by
  placing the line, then re-testing; the loop must be written expecting to
  re-run, not as a single pass.
* **A line that cannot fit any content beside a float moves down** rather
  than overflowing. That is not an error path — it is ordinary layout.

### 2. `clear` has never been reachable (`layout/block.py`)

`clear` is parsed and cascaded and does nothing, deliberately: Task C called
implementing it "the `clear` trap" — disagreeing with a browser on every
reachable case in order to agree on one unreachable one. **Floats make it
reachable**, and it stops being a trap and becomes required. Expect it in
the same diff; a float implementation that leaves `clear` inert is worse
than one that never shipped, because it silently mis-stacks.

### 3. Intrinsic sizing treats a float as in-flow (`layout/intrinsic.py`)

> "a float inside a box contributes to that box's intrinsic sizes as though
> it were in flow."

Wrong once floats exist: a float's contribution to min-content and
max-content follows different rules from an in-flow box's. This one is
load-bearing for shrink-to-fit, which is already implemented — so it is a
change to code that currently passes its tests, and a place where the
regression risk is highest.

### 4. Baseline search takes the maximum, not tree order (`block.py:1231`)

> "with no floats and no out-of-flow boxes placed, the two agree, and taking
> the maximum is the one that stays right when they stop agreeing."

Written in anticipation. **Verify it, do not trust it.** The comment is an
unexecuted claim about a state that has never existed, which is exactly the
category CLAUDE.md's assert-from-reading rule covers.

### 5. Margin collapsing does not model a float barrier (`block.py`)

A float establishes a new block formatting context, and margins do not
collapse through one. The BFC-barrier machinery exists (Task C's
`margin_collapse_blocked_new_formatting_context`), so this is likely a
matter of adding floats to the barrier set — likely, not certainly, and the
census counters are the way to tell rather than reading.

### 6. Flex counts a floated child as an item (`flex.py:546`)

`flex_item_float_ignored` reads **1** on the survey. Correct per Flexbox 1
§4 — `float` has no effect on a flex item — so this is a counter to keep
reading zero-ish rather than a defect to fix. Named here so it is not
"fixed" by mistake while floats are on the mind.

### 7. `boxtree.py:186` gives a float a position it cannot honour

Recorded there already. Worth re-reading before starting.

## Scope

In:

* `float: left | right` on block-level boxes, CSS 2.1 §9.5.1's nine rules.
* Float placement against the current line box and previously placed floats.
* Line-box shortening, including the re-test loop and the move-down case.
* `clear: left | right | both`.
* Floats' effect on intrinsic sizes, and therefore on shrink-to-fit.
* Floats as a margin-collapsing barrier.
* Float overflow out of the bottom of its containing block (ordinary, not
  an error).

Counted, not implemented — each with a counter and a register row:

* `float` inside an inline formatting context that has already wrapped.
* Floats interacting with `overflow` other than `visible` (a BFC root that
  contains its floats).
* `shape-outside` and anything from CSS Shapes.

## Discipline

**Measure discriminating power before implementing**, the way Tasks E and F
did, and keep the instruments' own defects in view: key rectangles by walk
index rather than DOM path (instance 19 — the corpus's float subtrees are
full of anonymous boxes), and state each counter's population in its name
(instance 20).

**Name the population in every figure.** There are at least four here and
they are not interchangeable: elements with `float` other than `none`; boxes
those produce; boxes *inside* a float subtree; and line boxes shortened.
`layout_float_skipped` counts subtree **roots** and
`layout_boxes_deferred_subtree` counts boxes **inside** them — reading the
first where the plan says the second is how this task nearly went out with
the opposite ruling (instance 25).

**Both collections, one commit**, as the survey did. The three Phase 3 pages
have a 0.0% median, so they will show almost nothing; that is the point of
running them, not a reason to skip them.

**The success measure is not a green suite.** It is:

1. `67 -> 79` pages laying out is Task G's measure, and must already hold.
2. The gated share falls from a 6.5% pooled median toward zero, reported
   **per stratum**, with government and non-Latin — at 30.3% and 31.0% —
   the two that decide whether this worked.
3. `layout_boxes_deferred_subtree` becomes a residual that must read zero
   for `float`, with absolute positioning still legitimately in it. Say
   which is which in the counter's name, or it is instance seventeen again.

## Done when

1. All seven assumptions above are either fixed or re-verified with a
   number, and the ones only re-verified say so explicitly.
2. `clear` works, with tests, in this diff.
3. The float census is reported per stratum over both collections at one
   commit, aggregate last.
4. Discriminating power measured, keyed by walk index, with a no-injection
   control diffing to zero.
5. `docs/synthetic-only-coverage.md` gains a Task H section, including which
   rules the corpus still cannot discriminate — there will be some, and
   naming them is the house convention.
6. Full suite green.
