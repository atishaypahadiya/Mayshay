# The flex census, re-measured after Task H

`docs/reports/corpus-2026-08-29/report.txt` carries a `FLEX CENSUS` table
whose every column is over **67 laid-out pages of 79**, because twelve
pages raised during layout. Task H fixed the twelve. The census is
therefore re-measured here rather than adjusted — and re-measured on two
populations, not one, because two things changed at once.

Measured at 1280x1024 with the collected external sheets applied, on
`data/corpus/2026-08-29-survey/`.

## Three columns, because "the number moved" has two possible causes

| column | pages | engine |
|---|---:|---|
| **A** | 67 | before Task H — the committed `report.txt` figures |
| **B** | the same 67 | after Task H |
| **C** | all 79 | after Task H |

`B - A` is what the four fixes changed on pages that already laid out.
`C - B` is what the twelve recovered pages add. Reporting only `C` against
`A` would fold the two together and make every row unreadable, which is
the same unstated-denominator shape `docs/measurement-hazards.md` records
against `boxes_inline_split` and the `var()` counts.

| counter | A: 67 pre | B: 67 post | C: 79 post | B-A | C-B |
|---|---:|---:|---:|---:|---:|
| `flex_containers_laid_out` | 2560 | 2560 | **3724** | 0 | +1164 |
| `flex_containers_row` | 2207 | 2207 | **3009** | 0 | +802 |
| `flex_containers_column` | 353 | 353 | **715** | 0 | +362 |
| `flex_lines` | 2665 | 2665 | **3855** | 0 | +1190 |
| `flex_lines_wrapped` | 105 | 105 | **131** | 0 | +26 |
| `flex_items_placed` | 4561 | 4561 | **6802** | 0 | +2241 |
| `flex_items_grown` | 142 | 142 | **344** | 0 | +202 |
| `flex_items_shrunk` | 213 | 213 | **356** | 0 | +143 |
| `flex_items_clamped_to_min_content` | 131 | 138 | **271** | **+7** | +133 |
| `flex_basis_definite` | 239 | 239 | **428** | 0 | +189 |
| `flex_items_aligned_baseline` | 51 | 51 | **66** | 0 | +15 |
| `flex_anonymous_items` | 547 | 547 | **772** | 0 | +225 |
| `flex_main_gap_applied` | 665 | 665 | **774** | 0 | +109 |
| `flex_order_ignored` | 28 | 28 | **38** | 0 | +10 |
| `flex_align_content_ignored` | 0 | 0 | **0** | 0 | 0 |
| `flex_direction_reverse_as_forward` | 1 | 1 | **27** | 0 | +26 |
| `flex_wrap_reverse_as_wrap` | 8 | 8 | **8** | 0 | 0 |
| `flex_item_auto_margin_zeroed` | 35 | 35 | **109** | 0 | +74 |
| `flex_baseline_in_column_as_start` | 0 | 0 | **0** | 0 | 0 |
| `flex_basis_content_keyword` | 0 | 0 | **0** | 0 | 0 |
| `flex_percentage_gap_as_zero` | 0 | 0 | **0** | 0 | 0 |
| `flex_column_reflowed_definite_main` | — | 1 | **78** | new | +77 |
| `layout_table_wrapper_width_wins` | 0* | 2 | **4** | **+2** | +2 |
| `flex_items_stretched` | 249* | 249 | **371** | 0 | +122 |
| `flex_free_space_positive` | 978* | 978 | **1441** | 0 | +463 |
| `flex_free_space_negative` | 161* | 162 | **300** | **+1** | +138 |

`*` — `report.txt`'s table does not carry these rows; the A figure is
from `survey.json`, which records all 228 counters per page. The other
rows agree between the two sources.

**`B - A`, measured over every counter and not only the flex ones.**
Re-running the same 67 pages and diffing all **228** counters
`survey.json` records against the post-Task-H run, exactly **four** moved:

| counter | pre | post |
|---|---:|---:|
| `flex_items_clamped_to_min_content` | 131 | 138 |
| `layout_table_wrapper_width_wins` | 0 | 2 |
| `flex_column_reflowed_definite_main` | 0 | 1 |
| `flex_free_space_negative` | 161 | 162 |

That is the expected shape rather than a hoped-for one. Three of the four
defects need a page that crashed; the fourth — a flex item's percentages
resolved against the item instead of against the container — moves item
widths, and seven of those crossed section 4.5's automatic minimum, which
also flipped one line's free space negative.

`layout_table_wrapper_width_wins` moving from 0 to 2 on those pages is a
count of the *branch*, not of any change: measured at the call, all four
table wrappers that reach it are listed below and the two on
already-laid-out pages agree to the pixel, so nothing about them moved.

    DIFFER  override= 538.0000  17.4= 630.3906  used to crash   stackblitz.com
    DIFFER  override=   0.0000  17.4= 469.0547  used to crash   tonsky.me/blog/unicode
    EQUAL   override=   8.8984  17.4=   8.8984  already laid out  docs.python.org/3/library/stdtypes.html
    EQUAL   override=  40.0000  17.4=  40.0000  already laid out  stripe.com/payments

`forum.qt.io` is the one page that genuinely rendered differently before:
it was justifying a column container against the wrong main size and not
tripping section 9.5's check while doing it. **No figure previously
published about those 67 pages is wrong except those four**, and the 224
that did not move are the evidence for it.

**The item census was not undercounting.** The task brief's first
candidate cause was that a child which should have been a flex item was
never collected, in which case `flex_items_placed` had been wrong wherever
a column container appeared. It was not that: on the Quanta container the
uncollected child is `position: absolute`, and Flexbox 1 section 4 says an
absolutely positioned child of a flex container is not a flex item. The
counter was right; `A` and `B` agreeing on it is that claim executed.

## The second derivation

Per CLAUDE.md, the totals above are not verified by the counters agreeing
with themselves. Each is derived a second time by walking the box trees
and counting `box.flex_plan`'s lines and items directly, which shares no
code with the counters:

    from the box trees:  containers 3724   lines 3855   items 6802
    from the counters:   containers 3724   lines 3855   items 6802

That check matters more here than usual, because `flex_column_reflowed_
definite_main` means sections 9.3 to 9.6 ran **twice** on 78 containers.
The counters they emit are kept on the plan and subtracted before the
re-run adds its own; a mistake in that bookkeeping produces exactly the
call-count-wearing-an-item-count defect
`docs/measurement-hazards.md` instance twenty describes. No counter is
negative on any of the 79 pages, which is the other half of the same
check.

## The new counters, and where they fire

* **`flex_column_reflowed_definite_main` — 78, on 8 of 79 pages.** A
  column flex container whose main size was decided by the box containing
  it, after it had already laid itself out. Seven of the eight are pages
  that used to crash; the eighth, `forum.qt.io`, laid out before and was
  quietly justifying against the wrong container size.

  | stratum | count | page |
  |---|---:|---|
  | news | 52 | theguardian.com/us/technology |
  | gov | 14 | irs.gov/forms-instructions |
  | news | 4 | pbs.org/newshour/science |
  | spa | 3 | stackblitz.com |
  | ecommerce | 2 | sparkfun.com/sparkfun-samd21-mini-breakout.html |
  | ecommerce | 1 | store.steampowered.com/app/620 |
  | news | 1 | quantamagazine.org/physics |
  | forum | 1 | forum.qt.io/category/4/general-and-desktop |

* **`layout_table_wrapper_width_wins` — 4, on 4 pages.** A table wrapper
  box whose width came from CSS 2.1 section 17.4 rather than from the
  `override_content_width` bypass a flex item takes. Counts the branch,
  not the disagreement: it fires whether or not the two widths differ.

* **`intrinsic_inverted_by_negative_margin` — 58, on 1 page**
  (keychron.com/collections/all-products). **One per intrinsic walk, not
  per box**: this module has no cache and every consumer asks it again, so
  a subtree measured three times counts three, exactly as
  `intrinsic_uax14_break_inside_a_run` does. It is *not* a count of
  inline formatting contexts.

## What is now stale

`docs/reports/corpus-2026-08-29/survey.json` holds per-page counters for
**67 pages**. It is the pre-Task-H record and is left as it is — it is
what the crashes were found in. Any figure taken from it is over 67 pages
and over the pre-Task-H engine, and the table above is the current one.
