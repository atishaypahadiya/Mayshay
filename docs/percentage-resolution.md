# When a percentage resolves

A percentage in CSS is not one thing. `width: 50%` and `line-height: 50%`
are the same token type and obey opposite rules, and getting the
distinction wrong produces output that is correctly proportioned and
subtly the wrong size -- which is the failure mode
`docs/measurement-hazards.md` exists to name.

Phase 2 established, correctly, that computed values are not used values
and that percentages survive symbolically. That principle is right for the
properties it was written for and wrong for others, and the discriminator
is a single question.

## The rule

> **What does the percentage resolve against, and is that quantity known
> when the cascade runs?**

There are three answers, not two.

### 1. Known at cascade time -- resolve now

The reference quantity is a font size, which the cascade computes for every
element as it walks the tree.

| property | resolves against | status |
|---|---|---|
| `font-size` | the **parent's** computed font-size | correct since Phase 2 |
| `line-height` | the **element's own** computed font-size | fixed in Task A2 |

Leaving these symbolic is a defect. A `line-height: 150%` left as
`Percent(150)` inherits to a child, which then resolves it against *its
own* font-size -- a different number from the one the author wrote, with
nothing in the output to show it.

Note the two rows resolve against *different* font sizes. That is the same
asymmetry `cascade.py` already documents for `em`, and it is why
`_compute_font_size` and `_compute_rest` are separate functions.

### 2. Not known until layout -- stay symbolic

The reference quantity is a containing-block dimension, which does not
exist until layout runs.

| property | resolves against |
|---|---|
| `width`, `height` | the containing block's width / height |
| `margin-*`, `padding-*` | the containing block's **width** -- all four sides, including top and bottom |
| `text-indent` | the containing block's width |
| `background-position` | the box's own painted area minus the image size |

Resolving these at cascade time is impossible, not merely early. The
`margin-top: 5%` case is worth knowing: it resolves against the containing
block's *width*, not its height, which surprises people who assume vertical
percentages use vertical dimensions.

### 3. Known at cascade time *sometimes* -- the honest third case

`vertical-align: <percentage>` resolves against the element's own **used**
`line-height`. Whether that is known depends on what `line-height` is:

| `line-height` | used value | `vertical-align: 50%` |
|---|---|---|
| `2` (number) | 2 x own font-size | known at cascade -- 20px at font-size 20px |
| `24px` (length) | 24px | known at cascade -- 12px |
| `normal` | **needs font metrics** | not known until Task D |

So it cannot be forced into either bucket. The handling is: resolve it when
`line-height` is a number or a length, leave it symbolic and **count** it
when `line-height` is `normal`, and let Task D resolve the remainder once
`hhea` metrics are available. A property that is resolvable in two cases
out of three should not be deferred wholesale, and it should not pretend to
be resolvable in the third.

## Auditing

The rule applies to a **class**, not to the properties that happened to
prompt it. Fixing one member of a silent class while leaving the others is
the same defect shape as the `declarations_dropped` two-call-site problem
in Task A2, and this class is defined by failing quietly.

When a percentage-accepting property is added, place it in one of the three
categories above and say which in a comment at the parse site. When a batch
of properties is added -- Task C's `float`/`position` set, Task D's text
properties -- audit the whole batch against this table rather than the one
property that raised the question.

Current audit, executed 2026-08-27 against the Task A2 branch (the
`vertical-align` row was `INCOMPLETE` when this file was written and is now
handled -- `_resolve_vertical_align_percentage` in `cascade.py`):

    font-size        %  -> resolved at cascade      correct
    line-height      %  -> resolved at cascade      correct (fixed in A2)
    width, height    %  -> symbolic                 correct
    margin-*         %  -> symbolic                 correct
    padding-*        %  -> symbolic                 correct
    vertical-align   %  -> resolved when line-height is a number or a px
                           length; symbolic and counted in
                           vertical_align_percent_deferred when it is
                           `normal` or a viewport unit   correct (fixed in A2)
    text-indent      %  -> not yet supported
    background-position % -> not yet supported

## For Task C and Task D

Task C resolves category 2 against the containing block it establishes.
Task D resolves the `line-height: normal` remainder of category 3 once font
metrics exist, and must treat a unitless `line-height` number as a
*number* -- multiplying by the element's own font-size at use time, never
at cascade time, because the number itself is what inherits.
