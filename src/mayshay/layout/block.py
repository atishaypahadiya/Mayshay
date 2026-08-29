"""Block layout -- Phase 3 Task C.

Positions and sizes for block-level boxes in a block formatting context, on
the box tree Task B builds. Two areas get most of the code because they are
where hand-rolled block layout is quietly wrong, and both are invisible in a
screenshot: **margin collapsing** (CSS 2.1 section 8.3.1) and the
**over-constrained width** rule (section 10.3.3).

## What is resolved here and what is not

`width: auto` on a block-level box resolves *here*, from the constraint
equation against the containing block, and has nothing to do with content --
measured against Chrome 151 in a 600px containing block, a `width: auto`
block is 600px wide with two characters of text in it and 600px wide with
forty-seven. A block-level box still carrying a symbolic width when this
module finishes is a defect, not a handoff.

Three things genuinely cannot finalise until Task D measures text, and each
is counted under its own name rather than lumped into one "deferred":

* **`height: auto` on a box with inline content** -- the height is the
  number of line boxes the text produces. `heights_deferred_inline_content`.
* **Shrink-to-fit widths** -- `inline-block` and friends, floats and
  absolutely positioned boxes need the max-content and min-content sizes of
  their contents. Same probe: a float, an `inline-block` and an
  absolutely-positioned box all measured 19.27px for the two characters that
  gave a block 600px. `widths_deferred_shrink_to_fit`.
* **Inline-level boxes**, which have no independent width at all.
  `widths_not_applicable_inline_level`.

A fourth bucket, `widths_deferred_other`, exists and should always read
zero. It is where a box that fits none of the three categories lands, so
that case arrives as a named number rather than as a surprise, and
`assert_layout_constraints` fails if the four do not sum to the boxes seen.

## The mechanical checks

Vigilance has caught none of this class of defect on this project and
mechanical checks have caught all of it, so there are four, all of them run
on every layout rather than only under test:

1. **The section 10.3.3 constraint equation, read off the geometry.** For
   every in-flow block-level box, the *margin box* must exactly span the
   containing block's content width, and start at its left edge. That is the
   equation restated, and it is checked against the rectangles produced by
   the absolutization pass rather than against the scalars the width
   resolver computed -- so a child laid out against the wrong containing
   block, or a rectangle assembled with the wrong offset, fails it.
2. **A margin-edge partition.** Every vertical margin edge is either merged
   into a collapsing group with at least one other edge or stands alone:
   `margin_edges_seen == margin_edges_collapsed + margin_edges_alone`. Task
   A2's `seen == kept + dropped`, applied to the thing that over-collapses.
3. **A collapse-barrier partition.** Every laid-out block box has two
   vertical edges, and each is either open to collapsing or closed for
   exactly one named reason: `collapse_barrier_edges_seen ==
   collapse_barrier_edges_open + sum(margin_collapse_blocked_*)`. This is
   the one that fails the moment a barrier joins the rule set and is
   forgotten in the counting -- verified by injecting exactly that.
4. **A box-disposition partition.** Every box in the tree is laid out or
   deferred for exactly one named reason, and the reasons sum.

Each was verified by injection rather than assumed to fire: laying a child
out against its parent's *border* width instead of its content width, and
skipping the offset composition in `_absolutize`, are both caught by check
1 and by nothing else in the suite.

## Not implemented, each counted

`float`, `position` other than `static`/`relative`, `overflow` scrolling and
clipping (the property is read for its formatting-context effect only),
`min-`/`max-width`/`height` (not parsed at all -- they never reach a
`ComputedStyle`), and `direction: rtl`, which is what decides *which* margin
the over-constrained rule ignores.
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass, replace

from mayshay.cssparse.cascade import ComputedStyle
from mayshay.cssparse.media import Viewport
from mayshay.cssparse.values import AUTO, Percent
from mayshay.layout import inline as inline_module
from mayshay.layout import intrinsic as intrinsic_module
from mayshay.layout import linebox as linebox_module
from mayshay.layout import table as table_module
from mayshay.layout.boxtree import ATOMIC_INLINE_DISPLAYS, Box
from mayshay.layout.geometry import EPSILON, BoxGeometry, Edges, Rect
from mayshay.layout.text import is_white_space_only
from mayshay.layout.used import px as _px
from mayshay.layout.used import px_or_zero as _px_or_zero
from mayshay.layout.used import style_of as _style_of

# The displays whose *inner* layout is block layout. Everything else that is
# block-level -- flex, the table family -- has its own inner algorithm in
# Task E or Task F; Task C lays their children out as block flow and counts
# it, exactly as Task B counts `display: grid` falling back to `block`.
BLOCK_CONTAINER_DISPLAYS: frozenset[str] = frozenset({"block", "list-item"})

# Block-level, but with a non-block inner formatting context. Each
# establishes a new formatting context, which is what makes it a
# margin-collapsing barrier.
# The table-internal displays, which CSS 2.1 section 17.6 says the margin
# properties do not apply to. Task E's rule; named here so the deviation is
# a counter rather than a surprise.
_TABLE_INTERNAL_DISPLAYS: frozenset[str] = frozenset({
    "table-row",
    "table-row-group",
    "table-header-group",
    "table-footer-group",
    "table-cell",
    "table-column",
    "table-column-group",
})

NON_BLOCK_INNER_DISPLAYS: frozenset[str] = frozenset({
    "flex",
    "table",
    "table-row",
    "table-row-group",
    "table-header-group",
    "table-footer-group",
    "table-cell",
    "table-caption",
    "table-column",
    "table-column-group",
})

# Every counter this module emits, seeded to zero so a page with no
# collapsing emits `margins_collapsed,0` rather than no row at all. Absence
# and zero must stay distinguishable in the CSV.
COUNTER_NAMES: tuple[str, ...] = (
    # boxes and their disposition -- these five partition the tree
    "layout_boxes_seen",
    "widths_resolved",
    "widths_shrink_to_fit_resolved",
    "widths_deferred_shrink_to_fit",
    "widths_shrink_to_fit_specified",
    "widths_not_applicable_inline_level",
    "widths_deferred_other",
    # heights
    "heights_specified",
    "heights_from_children",
    "heights_deferred_inline_content",
    "heights_from_line_boxes",
    "heights_percentage_fallback_auto",
    # section 10.3.3
    "width_auto_absorbed_remainder",
    "width_margins_centred",
    "width_margin_left_auto",
    "width_margin_right_auto",
    "width_auto_margins_zeroed_by_overflow",
    "width_over_constrained_margin_right_ignored",
    "width_clamped_to_zero",
    "box_sizing_border_box",
    # section 8.3.1
    "margins_collapsed",
    "margins_collapsed_through_empty",
    "margin_edges_seen",
    "margin_edges_collapsed",
    "margin_edges_alone",
    "collapse_barrier_edges_seen",
    "collapse_barrier_edges_open",
    "margin_collapse_blocked_root",
    "margin_collapse_blocked_padding_top",
    "margin_collapse_blocked_border_top",
    "margin_collapse_blocked_padding_bottom",
    "margin_collapse_blocked_border_bottom",
    "margin_collapse_blocked_parent_height",
    "margin_collapse_blocked_new_formatting_context",
    "margin_collapse_blocked_line_box",
    "margin_collapse_blocked_out_of_flow",
    # deferred and not implemented, each named
    "layout_float_skipped",
    "layout_absolute_skipped",
    "layout_position_relative_unoffset",
    "layout_inner_fallback_block",
    "layout_viewport_unit_unresolved",
    "layout_length_unit_unexpected",
    "layout_boxes_deferred_subtree",
) + linebox_module.COUNTER_NAMES

# The computed initial value of every margin longhand, for the one place
# that needs to know whether a margin was *declared* rather than what it
# resolves to.
_ZERO = ComputedStyle().margin_top


# --------------------------------------------------------------------------
# Geometry
# --------------------------------------------------------------------------


# `Rect`, `Edges` and `BoxGeometry` live in `layout.geometry` since Task D2:
# `layout.linebox` needs them and this module imports `linebox`, so they
# cannot stay here. Re-exported under their old names because they are part
# of this module's published surface -- `tests/layout/test_block.py` and
# `scripts/layout_report.py` both name them.


# --------------------------------------------------------------------------
# Margin collapsing
# --------------------------------------------------------------------------


class MarginGroup:
    """A set of adjoining margins, and their collapsed value.

    The sign rules of CSS 2.1 section 8.3.1 are not `max()`: two positive
    margins collapse to the larger, two negative to the *most negative*, and
    a mixed pair to their **sum**. The general rule for any number of them is
    `max(positives) + min(negatives)`, and keeping the two extremes rather
    than a running scalar is what makes that true for three or more without
    a special case.

    A test using only positive margins passes under `max()`, under `sum()`
    when one operand is zero, and under several other wrong rules, which is
    why `tests/layout/test_block.py` tests all three sign combinations.

    Groups merge by union-find rather than by copying, so that after layout
    every margin edge can be traced to the one group it ended up in. That is
    what makes `margin_edges_seen == margin_edges_collapsed +
    margin_edges_alone` a real partition rather than a restatement: an edge
    counted twice, or never, changes one side and not the other.
    """

    __slots__ = ("_largest_positive", "_most_negative", "_count", "_parent")

    def __init__(self) -> None:
        self._largest_positive = 0.0
        self._most_negative = 0.0
        self._count = 0
        self._parent: "MarginGroup | None" = None

    def root(self) -> "MarginGroup":
        group = self
        while group._parent is not None:
            group = group._parent
        node = self
        while node._parent is not None:  # path compression
            node._parent, node = group, node._parent
        return group

    @property
    def count(self) -> int:
        return self.root()._count

    def add(self, margin: float) -> None:
        root = self.root()
        if margin > root._largest_positive:
            root._largest_positive = margin
        if margin < root._most_negative:
            root._most_negative = margin
        root._count += 1

    def merge(self, other: "MarginGroup") -> bool:
        """Join `other` into this group. True when a join actually happened
        between two non-empty groups -- which is one collapse event."""
        mine = self.root()
        theirs = other.root()
        if mine is theirs:
            return False
        joined = bool(mine._count and theirs._count)
        if theirs._largest_positive > mine._largest_positive:
            mine._largest_positive = theirs._largest_positive
        if theirs._most_negative < mine._most_negative:
            mine._most_negative = theirs._most_negative
        mine._count += theirs._count
        theirs._parent = mine
        return joined

    def value(self) -> float:
        root = self.root()
        return root._largest_positive + root._most_negative

    def __repr__(self) -> str:  # pragma: no cover - diagnostic
        root = self.root()
        return (
            f"MarginGroup(+{root._largest_positive}, {root._most_negative}, "
            f"n={root._count})"
        )


def _new_group(groups: list[MarginGroup]) -> MarginGroup:
    """Every group is registered, so the edge partition at the end can walk
    all of them. A group created and forgotten is exactly the defect the
    partition exists to catch, so the registry cannot be optional."""
    group = MarginGroup()
    groups.append(group)
    return group


def _partition_margin_edges(
    groups: list[MarginGroup], metrics: Counter[str]
) -> None:
    """Classify every margin edge by the group it finally ended up in.

    Computed from the union-find roots after layout rather than incremented
    during merging: an incremental count is a second implementation of the
    merging, and two implementations of the same thing agree with each other
    while both being wrong. This one reads the result.
    """
    roots: dict[int, MarginGroup] = {}
    for group in groups:
        root = group.root()
        roots[id(root)] = root
    for root in roots.values():
        if root.count >= 2:
            metrics["margin_edges_collapsed"] += root.count
        elif root.count == 1:
            metrics["margin_edges_alone"] += 1


@dataclass
class _Result:
    """What laying out one in-flow block-level box tells its parent."""

    top: MarginGroup
    bottom: MarginGroup
    collapsed_through: bool
    border_height: float


# --------------------------------------------------------------------------
# Value resolution
# --------------------------------------------------------------------------


def _is_out_of_flow(style: ComputedStyle) -> str | None:
    """`"float"`, `"absolute"`, or None. Out-of-flow boxes never collapse
    their margins with in-flow siblings and contribute nothing to their
    parent's height."""
    if style.float_ != "none":
        return "float"
    if style.position in ("absolute", "fixed"):
        return "absolute"
    return None


def _establishes_formatting_context(box: Box, style: ComputedStyle) -> str | None:
    """Why this box establishes a new block formatting context, or None.

    A box that does establishes one is a margin-collapsing barrier in both
    directions: its children's margins do not escape through its edges and
    its own margins do not reach in. The reason is returned rather than a
    bool so the barrier counter can say *which* rule fired -- the same
    reason Task A2 partitions drops by cause. "We correctly did not
    collapse" and "we never tried" are different facts.
    """
    if style.overflow != "visible":
        return "new_formatting_context"
    if box.table_wrapper:
        # CSS 2.1 section 17.4's table wrapper box. Its display is `block`,
        # so none of the tests below sees it, and without this line a
        # caption's margin collapses out through the wrapper's top edge and
        # moves the whole table. The flag rather than the display, because
        # the display is deliberately indistinguishable from any other
        # block's -- that is what makes the wrapper transparent to the rest
        # of block layout.
        return "new_formatting_context"
    if box.display in ATOMIC_INLINE_DISPLAYS:
        return "new_formatting_context"
    if box.display in NON_BLOCK_INNER_DISPLAYS:
        return "new_formatting_context"
    return None


def _is_blank_text_box(box: Box) -> bool:
    """Is this a text box made only of CSS white space?

    `layout.text.is_white_space_only`, not `str.strip()`: the two disagree
    on U+00A0 and six other Unicode spaces that CSS Text 3 does not treat
    as white space. A block whose only inline content is `&nbsp;` has a
    line box and must not collapse through, and `str.strip()` says it has
    none. Zero corpus occurrences -- 707 calls, none of them a
    disagreement -- so this is a latent defect fixed rather than a
    behaviour change, and it is a row in
    `docs/synthetic-only-coverage.md` for that reason.
    """
    return (
        box.origin == "text"
        and box.node is not None
        and is_white_space_only(box.node.data)
    )


def _has_line_boxes(box: Box) -> bool:
    """Does this box establish an inline formatting context with content in
    it?

    Section 8.3.1's collapse-through condition names *in-flow line boxes*,
    and white space that collapses away produces none. A box whose only
    inline children are collapsible whitespace is still empty, which is why
    this is not `any(child.is_inline_level ...)`.
    """
    return any(
        child.is_inline_level and not _is_blank_text_box(child)
        for child in box.children
    )


# --------------------------------------------------------------------------
# Width: CSS 2.1 section 10.3.3
# --------------------------------------------------------------------------


@dataclass
class _Horizontal:
    margin_left: float
    margin_right: float
    border_left: float
    border_right: float
    padding_left: float
    padding_right: float
    content_width: float

    @property
    def border_box_width(self) -> float:
        return (
            self.border_left
            + self.padding_left
            + self.content_width
            + self.padding_right
            + self.border_right
        )


def _resolve_width(
    style: ComputedStyle,
    cb_width: float,
    metrics: Counter[str],
    *,
    override_content_width: float | None = None,
    used_content_width: float | None = None,
) -> _Horizontal:
    """The constraint equation for a block-level, non-replaced, in-flow box:

        margin-left + border-left + padding-left + width
          + padding-right + border-right + margin-right
          = containing block width

    Four outcomes that must disagree with each other, or a wrong
    implementation passes the tests that a right one passes:

    * both margins `auto`, `width` set -> equal margins, box centred;
    * one margin `auto` -> that margin absorbs the remainder;
    * `width: auto` -> the width absorbs and any `auto` margin becomes
      **0**, so `margin: 0 auto` with no width centres nothing;
    * none of the three `auto` -> **over-constrained**, and CSS 2.1 resolves
      it by ignoring `margin-right` in a left-to-right containing block. Not
      by scaling both, and not by ignoring `margin-left`.

    An implementation that always centres passes the first; one that always
    absorbs into `margin-right` passes the first and the fourth. The tests
    assert the resulting margin *values*, because "ignored margin" and
    "centred" are indistinguishable by position whenever the numbers happen
    to coincide.
    """
    border_left = _px_or_zero(style.border_left_width, basis=cb_width, metrics=metrics)
    border_right = _px_or_zero(
        style.border_right_width, basis=cb_width, metrics=metrics
    )
    padding_left = _px_or_zero(style.padding_left, basis=cb_width, metrics=metrics)
    padding_right = _px_or_zero(style.padding_right, basis=cb_width, metrics=metrics)
    edges = border_left + border_right + padding_left + padding_right

    margin_left = _px(style.margin_left, basis=cb_width, metrics=metrics)
    margin_right = _px(style.margin_right, basis=cb_width, metrics=metrics)
    if override_content_width is not None:
        # An atomic inline. Its width is shrink-to-fit and was resolved
        # before line breaking -- section 10.3.3's constraint equation does
        # not apply to it at all, so it is bypassed rather than fed a
        # containing block it does not have. `auto` margins on an atomic
        # inline compute to zero (section 10.3.2), which is what `or 0.0`
        # says here.
        return _Horizontal(
            margin_left=margin_left or 0.0,
            margin_right=margin_right or 0.0,
            border_left=border_left,
            border_right=border_right,
            padding_left=padding_left,
            padding_right=padding_right,
            content_width=override_content_width,
        )
    left_auto = margin_left is None
    right_auto = margin_right is None
    margin_left = 0.0 if left_auto else margin_left
    margin_right = 0.0 if right_auto else margin_right

    declared_width = _px(style.width, basis=cb_width, metrics=metrics)
    border_box_sizing = style.box_sizing == "border-box"
    if border_box_sizing and declared_width is not None:
        metrics["box_sizing_border_box"] += 1
    if used_content_width is not None:
        # A table wrapper box (CSS 2.1 section 17.4). Its width is neither
        # declared nor absorbed from the containing block: it is "the
        # border-edge width of the table box inside it", already computed.
        #
        # Fed in as though it had been declared, rather than through the
        # `override_content_width` bypass an atomic inline uses, and the
        # difference is what section 17.5.2 asks for in as many words:
        # "once the calculated value of 'width' for the table is found ...
        # then the other parts of section 10.3 do apply. Therefore a table
        # can be centered using left and right 'auto' margins." Measured --
        # Chrome 151 puts a 17.7969px auto-width table with `margin: 0 auto`
        # at x=291.09 in a 600px block, which is centred and not left.
        declared_width = used_content_width
        border_box_sizing = False

    if declared_width is None:
        # `width: auto` absorbs the remainder, and any `auto` margin is 0.
        content_width = cb_width - margin_left - margin_right - edges
        if content_width < 0:
            content_width = 0.0
            metrics["width_clamped_to_zero"] += 1
        metrics["width_auto_absorbed_remainder"] += 1
        left_auto = right_auto = False
    else:
        if border_box_sizing:
            content_width = declared_width - edges
        else:
            content_width = declared_width
        if content_width < 0:
            content_width = 0.0
            metrics["width_clamped_to_zero"] += 1

    used = content_width + edges
    if declared_width is not None and (left_auto or right_auto):
        # Section 10.3.3, and the sentence that is easy to miss: if `width`
        # is not `auto` and the box is already wider than its containing
        # block, any `auto` margin is treated as **zero** for the rules
        # below -- which then makes the equation over-constrained and sends
        # it through the margin-right branch. Chrome 151 agrees: a 500px
        # box with `margin: 0 auto` in a 400px containing block gets
        # margin-left 0 and margin-right -100, not -50 and -50.
        if used + margin_left + margin_right > cb_width:
            metrics["width_auto_margins_zeroed_by_overflow"] += 1
            left_auto = right_auto = False

    remainder = cb_width - used
    if left_auto and right_auto:
        margin_left = margin_right = remainder / 2.0
        metrics["width_margins_centred"] += 1
    elif left_auto:
        margin_left = remainder - margin_right
        metrics["width_margin_left_auto"] += 1
    elif right_auto:
        margin_right = remainder - margin_left
        metrics["width_margin_right_auto"] += 1
    else:
        recomputed = remainder - margin_left
        if abs(recomputed - margin_right) > EPSILON:
            # Over-constrained. LTR only: `direction: rtl` would ignore
            # `margin-left` instead, and `direction` is not parsed.
            #
            # A shrink-wrapped table is over-constrained by construction --
            # its width came from its columns and owes the containing block
            # nothing -- so it gets its own counter. Folding it into the
            # one above would put 32 corpus tables into a bucket that is
            # supposed to mean "the author wrote three conflicting values".
            metrics[
                "table_width_remainder_to_margin_right"
                if used_content_width is not None
                else "width_over_constrained_margin_right_ignored"
            ] += 1
        margin_right = recomputed

    return _Horizontal(
        margin_left=margin_left,
        margin_right=margin_right,
        border_left=border_left,
        border_right=border_right,
        padding_left=padding_left,
        padding_right=padding_right,
        content_width=content_width,
    )


# --------------------------------------------------------------------------
# Laying out one box
# --------------------------------------------------------------------------


def _defer_subtree(box: Box, metrics: Counter[str], *, reason: str) -> None:
    """Record a box and everything under it as not laid out.

    `reason` names the bucket the box itself falls in; its descendants go to
    `layout_boxes_deferred_subtree` whatever they are, because a box whose
    containing block was never sized has no width question of its own yet.
    """
    metrics["layout_boxes_seen"] += 1
    metrics[reason] += 1
    for child in box.children:
        for descendant in child.walk():
            metrics["layout_boxes_seen"] += 1
            metrics["layout_boxes_deferred_subtree"] += 1


def _layout_block(
    box: Box,
    *,
    cb_width: float,
    cb_height: float | None,
    metrics: Counter[str],
    groups: list[MarginGroup],
    fragment_counts: dict[int, int],
    is_root: bool = False,
    override_content_width: float | None = None,
    already_counted: bool = False,
) -> _Result:
    """Lay out one in-flow block-level box and everything under it.

    Geometry is written relative to the containing block's content origin;
    `_absolutize` converts the whole tree once at the end. The box's own y is
    left at zero here and set by the caller with `_shift`, because the y
    depends on a collapsed margin the caller computes from this result --
    and shifting a box is O(1) precisely because its children's coordinates
    are relative to *it*.
    """
    if not already_counted:
        metrics["layout_boxes_seen"] += 1
        metrics["widths_resolved"] += 1
    style = _drop_table_internal_margins(box, cb_width, metrics)
    if style.position == "relative":
        # In flow and laid out at its static position. `top`/`left` are not
        # in `ComputedStyle` at all, so a relative box cannot be offset even
        # in principle yet; counted so the gap is a number.
        metrics["layout_position_relative_unoffset"] += 1

    plan = None
    used_content_width = None
    if box.table_wrapper:
        # Section 17.4 in the order it has to happen: the wrapper's width is
        # the table box's border-edge width, so the whole of 17.5.2 runs
        # here, before this box has a rectangle. It reads intrinsic sizes
        # and computed styles only -- nothing inside the table is laid out
        # yet, and nothing needs to be.
        inner = next(
            (c for c in box.children if c.display in table_module.TABLE_DISPLAYS),
            None,
        )
        assert inner is not None, (
            f"a table wrapper box with no table box inside it: {box!r}"
        )
        plan = table_module.plan_table(
            box, inner, cb_width=cb_width, metrics=metrics
        )
        inner.table_plan = plan
        used_content_width = plan.border_width

    horizontal = _resolve_width(
        style,
        cb_width,
        metrics,
        override_content_width=override_content_width,
        used_content_width=used_content_width,
    )

    margin_top = _px_or_zero(style.margin_top, basis=cb_width, metrics=metrics)
    margin_bottom = _px_or_zero(style.margin_bottom, basis=cb_width, metrics=metrics)
    padding_top = _px_or_zero(style.padding_top, basis=cb_width, metrics=metrics)
    padding_bottom = _px_or_zero(style.padding_bottom, basis=cb_width, metrics=metrics)
    border_top = _px_or_zero(style.border_top_width, basis=cb_width, metrics=metrics)
    border_bottom = _px_or_zero(
        style.border_bottom_width, basis=cb_width, metrics=metrics
    )
    metrics["margin_edges_seen"] += 2

    height = _resolve_height(style, cb_height, cb_width, metrics)
    if height is not None and style.box_sizing == "border-box":
        height = max(
            0.0, height - padding_top - padding_bottom - border_top - border_bottom
        )

    formatting_context = _establishes_formatting_context(box, style)

    # --- which of this box's own edges are open to collapsing -------------
    #
    # Each edge is closed by at most one reason and the reason is recorded,
    # not just the fact: "we correctly did not collapse" and "we never
    # tried" are different facts, and only the per-reason breakdown tells
    # them apart. Counting happens after the children are known, because a
    # barrier on a box with no in-flow block-level child blocked nothing --
    # counting it there would inflate every leaf `<div>` with padding into a
    # margin-collapsing event.
    top_closed_by: str | None = None
    bottom_closed_by: str | None = None
    if is_root:
        # The root element's margins never collapse with anything.
        top_closed_by = bottom_closed_by = "root"
    elif formatting_context is not None:
        top_closed_by = bottom_closed_by = formatting_context
    else:
        if padding_top != 0:
            top_closed_by = "padding_top"
        elif border_top != 0:
            top_closed_by = "border_top"
        if padding_bottom != 0:
            bottom_closed_by = "padding_bottom"
        elif border_bottom != 0:
            bottom_closed_by = "border_bottom"

    top_open = top_closed_by is None
    # The bottom edge is open to *this box's own* margins collapsing through
    # it whenever height is `auto` **or 0** -- section 8.3.1's
    # collapse-through condition says "zero or auto height", and Chrome
    # agrees: an empty box with `margin: 40px 0; height: 0` between two
    # 30px-margined siblings still gives a 40px gap, not 40 + 0 + 40.
    #
    # Rule 3 -- a parent's bottom margin collapsing with its *last child's*
    # -- is stricter and needs `height: auto`, so the two flags are separate.
    # Collapsing them into one is the bug this pair of names exists to
    # prevent, and it was in this file until Chrome disagreed with it.
    bottom_edges_open = bottom_closed_by is None
    bottom_open_for_children = bottom_edges_open and height is None
    if bottom_edges_open and height is not None:
        bottom_closed_by = "parent_height"

    top_group = _new_group(groups)
    top_group.add(margin_top)
    bottom_group = _new_group(groups)
    bottom_group.add(margin_bottom)

    # --- children ---------------------------------------------------------
    inner_x = horizontal.margin_left + horizontal.border_left + horizontal.padding_left
    inner_y = border_top + padding_top

    has_line_boxes = _has_line_boxes(box)
    if (
        has_line_boxes
        and top_open
        and bottom_edges_open
        and (height is None or height == 0)
    ):
        # It would collapse through on every other test; the line boxes are
        # what stop it. Counted separately from the structural barriers
        # because this is the one that Task D will make load-bearing -- the
        # box's height is 0 here and will not be then.
        metrics["margin_collapse_blocked_line_box"] += 1
    if has_line_boxes:
        # An inline formatting context. Task D measures it; here the box is
        # known to be non-empty (line boxes block collapse-through) and its
        # auto height is deferred rather than guessed at zero silently.
        content_height, trailing = _layout_inline_content(
            box,
            metrics,
            groups=groups,
            fragment_counts=fragment_counts,
            cb_width=horizontal.content_width,
        )
        collapsed_through = False
    else:
        if (
            box.display not in BLOCK_CONTAINER_DISPLAYS
            and box.children
            and not is_root
        ):
            # Flex and the table family: block-level with a non-block inner
            # layout that Task E and Task F own. Laid out as block flow and
            # counted, in the shape of Task B's `boxes_grid_fallback` -- a
            # fallback that misplaces rather than crashes, and says so.
            metrics["layout_inner_fallback_block"] += 1
        if box.display in table_module.TABLE_DISPLAYS:
            content_height = _layout_table_contents(
                box,
                metrics=metrics,
                groups=groups,
                fragment_counts=fragment_counts,
            )
            trailing, all_collapsed_through = None, False
        else:
            content_height, trailing, all_collapsed_through = _layout_children(
                box,
                metrics=metrics,
                groups=groups,
                fragment_counts=fragment_counts,
                cb_width=horizontal.content_width,
                cb_height=height,
                top_group=top_group if top_open else None,
                bottom_open=bottom_open_for_children,
            )
        collapsed_through = (
            top_open
            and bottom_edges_open
            and all_collapsed_through
            and (height is None or height == 0)
        )

    # Both of this box's vertical edges, classified open or closed with one
    # named reason each, for every laid-out block box. The partition over
    # them is asserted in `assert_layout_constraints` and is the check that
    # fails the moment a barrier joins the rule set and is forgotten in the
    # counting.
    #
    # Counted for every box, not only for parents: an edge closes the
    # parent/first-child collapse *and* the box's own collapse-through, and
    # both are real. An empty `<div style="padding:1px">` between two
    # margined siblings blocks a collapse that a bare one does not, so the
    # barrier event is there even with no children to have it with.
    #
    # An edge can be structurally open and still collapse nothing, when line
    # boxes are what stop it. That is `margin_collapse_blocked_line_box`,
    # which is deliberately outside this partition -- it is a fact about the
    # content, not about the edge.
    metrics["collapse_barrier_edges_seen"] += 2
    for closed_by in (top_closed_by, bottom_closed_by):
        if closed_by is None:
            metrics["collapse_barrier_edges_open"] += 1
        else:
            metrics[f"margin_collapse_blocked_{closed_by}"] += 1

    if height is None:
        used_height = content_height
        if not has_line_boxes:
            metrics["heights_from_children"] += 1
    else:
        used_height = height

    if trailing is not None:
        _merge_and_count(bottom_group, trailing, metrics)

    if collapsed_through:
        # The box's own top and bottom margins are adjoining: one group, and
        # it participates in whatever the parent is collecting. Its own
        # margins are *not* what makes it empty -- section 8.3.1's condition
        # names borders, padding, height and line boxes, and Chrome agrees:
        # no declared margin, `margin: 0` and `margin: 0%` all collapse
        # through identically.
        _merge_and_count(top_group, bottom_group, metrics)
        bottom_group = top_group
        metrics["margins_collapsed_through_empty"] += 1

    _assign_geometry(
        box,
        collapsed_through=collapsed_through,
        horizontal=horizontal,
        margin_top=margin_top,
        margin_bottom=margin_bottom,
        padding_top=padding_top,
        padding_bottom=padding_bottom,
        border_top=border_top,
        border_bottom=border_bottom,
        content_height=used_height,
        inner_x=inner_x,
        inner_y=inner_y,
        cb_width=cb_width,
    )

    border_height = border_top + padding_top + used_height + padding_bottom + border_bottom
    return _Result(
        top=top_group,
        bottom=bottom_group,
        collapsed_through=collapsed_through,
        border_height=border_height,
    )


def _drop_table_internal_margins(
    box: Box, cb_width: float, metrics: Counter[str]
) -> ComputedStyle:
    """This box's style, with the margins removed if it is table-internal.

    **CSS 2.1 section 17.5, not 17.6.** "Internal table elements generate
    rectangular boxes with content and borders. Cells have padding as well.
    Internal table elements do not have margins." Section 17.6 is the two
    border models and says nothing about margins; the citation in Task C's
    comment, in this task's brief and in `tests/layout/test_block.py`'s
    docstring was wrong in all three places and is corrected in all three.

    Two counters, because the one this replaces conflated them.
    `layout_table_box_margins_applied` tested `is not _ZERO` -- an identity
    check against the initial value -- so it counted a *declaration*, not an
    effect. It read 2 on the corpus and, executed, both are `margin: 0` on a
    Wikipedia `<td>`: **no table-internal box on the corpus has a non-zero
    margin**, so this fix moves exactly zero corpus pixels. That is worth
    knowing and was not knowable from a counter whose name said "applied".

    A returned copy, never a mutation: the `ComputedStyle` belongs to the
    DOM element and is shared with the cascade's own tests.

    Section 17.4 puts `table-caption` outside this rule on purpose -- a
    caption box "retains its own content, padding, margin, and border
    areas" -- so `_TABLE_INTERNAL_DISPLAYS` does not contain it.
    """
    style = _style_of(box)
    if box.display not in _TABLE_INTERNAL_DISPLAYS:
        return style
    declared = (
        style.margin_top,
        style.margin_right,
        style.margin_bottom,
        style.margin_left,
    )
    if all(value is _ZERO for value in declared):
        return style
    nonzero = any(
        _px_or_zero(value, basis=cb_width, metrics=metrics) != 0.0
        for value in declared
    )
    metrics[
        "table_internal_margin_dropped"
        if nonzero
        else "table_internal_margin_declared_zero"
    ] += 1
    return replace(
        style,
        margin_top=_ZERO,
        margin_right=_ZERO,
        margin_bottom=_ZERO,
        margin_left=_ZERO,
    )


def _layout_table_contents(
    box: Box,
    *,
    metrics: Counter[str],
    groups: list[MarginGroup],
    fragment_counts: dict[int, int],
) -> float:
    """A table box's inner layout, delegated to `layout.table`.

    Two callbacks go out and a height comes back. `layout.table` decides
    *where* every row, row group and cell goes; `_layout_block` is still
    what lays a **cell** out, because a cell is an ordinary block container
    and there is no second block layout in this engine.

    `account` is the other half of that bargain. A row and a row-group box
    are sized by the grid, so they never reach `_layout_block` -- and every
    box in the tree has to be counted by exactly one bucket or
    `_assert_box_partition` fails. This is that bucket, spelled out here
    beside the counters it feeds rather than duplicated in `layout.table`.
    """
    plan = box.table_plan
    assert plan is not None, f"a table box laid out with no plan: {box!r}"

    def layout_cell(cell: Box, content_width: float) -> float:
        result = _layout_block(
            cell,
            cb_width=content_width,
            cb_height=None,
            metrics=metrics,
            groups=groups,
            fragment_counts=fragment_counts,
            override_content_width=content_width,
        )
        return result.border_height

    def account(internal: Box) -> None:
        # Rows and row groups get the same section 17.5 margin treatment as
        # cells, and they have to get it HERE: they never reach
        # `_layout_block`, so without this a `margin` on a `<tr>` would be
        # dropped silently instead of dropped and counted.
        _drop_table_internal_margins(internal, plan.content_width, metrics)
        metrics["layout_boxes_seen"] += 1
        metrics["widths_resolved"] += 1
        # Two vertical margin edges that cannot collapse with anything --
        # section 17.5 gives internal table elements no margins at all --
        # registered as two singleton groups so `_partition_margin_edges`
        # sees the same number of edges this claims.
        metrics["margin_edges_seen"] += 2
        _new_group(groups).add(0.0)
        _new_group(groups).add(0.0)
        metrics["collapse_barrier_edges_seen"] += 2
        metrics["margin_collapse_blocked_new_formatting_context"] += 2

    height = table_module.layout_table_contents(
        box, plan, metrics=metrics, layout_cell=layout_cell, account=account
    )
    table_module.assert_table_constraints(box, plan)
    return height


def _resolve_shrink_to_fit(box: Box, *, cb_width: float, metrics: Counter[str]) -> float:
    """CSS 2.1 section 10.3.5 for one box, stored on the box.

    Task D1's answer to Task C's largest deferral. The **width** of a
    float, an absolutely positioned box or an `inline-block` resolves here;
    its **position** does not, and floats are not placed at all. So this
    writes `shrink_to_fit_width` and leaves `geometry` as None, which is
    the honest pair -- giving these boxes a rectangle would put them at the
    static position and make `_assert_geometry`'s section 10.3.3 tiling
    fail, correctly, because a float's margin box does not span its
    containing block.

    `available` is the containing block's content width less this box's own
    horizontal edges, per the section: the formula sizes the *content* box.
    A specified `width` short-circuits the whole thing -- shrink-to-fit is
    what `width: auto` means on these boxes, not what they always do.
    """
    style = _style_of(box)
    edges = (
        _px_or_zero(style.border_left_width, basis=cb_width, metrics=metrics)
        + _px_or_zero(style.border_right_width, basis=cb_width, metrics=metrics)
        + _px_or_zero(style.padding_left, basis=cb_width, metrics=metrics)
        + _px_or_zero(style.padding_right, basis=cb_width, metrics=metrics)
    )
    margins = _px_or_zero(
        style.margin_left, basis=cb_width, metrics=metrics
    ) + _px_or_zero(style.margin_right, basis=cb_width, metrics=metrics)
    available = max(0.0, cb_width - edges - margins)

    declared = _px(style.width, basis=cb_width, metrics=metrics)
    if declared is None:
        content = intrinsic_module.shrink_to_fit(box, available, metrics=metrics)
    else:
        metrics["widths_shrink_to_fit_specified"] += 1
        content = declared - edges if style.box_sizing == "border-box" else declared
    box.shrink_to_fit_width = max(0.0, content)
    return box.shrink_to_fit_width


def _layout_inline_content(
    box: Box,
    metrics: Counter[str],
    *,
    groups: list[MarginGroup],
    fragment_counts: dict[int, int],
    cb_width: float,
) -> tuple[float, MarginGroup | None]:
    """Lay out an inline formatting context and return its height.

    Task C's largest deferral, and the reason `heights_deferred_inline_content`
    read 687 on the corpus: a block container whose content is inline has a
    `height: auto` equal to the sum of its line box heights, and there were
    no line boxes. There are now.

    Two passes, in this order and not the other, because the second needs
    the first:

    1. every atomic inline in the context gets its shrink-to-fit width,
       from `intrinsic`, against this containing block;
    2. the context is broken into lines, which needs those widths to know
       what fits.

    `None` comes back as the trailing margin group in every case: an inline
    formatting context's line boxes are a collapse barrier, so nothing
    escapes downward out of one.
    """
    for child in box.children:
        _account_inline_box(child, metrics, cb_width=cb_width)

    def layout_atomic(atomic: Box) -> tuple[float, float | None]:
        return _layout_atomic(
            atomic, metrics=metrics, groups=groups,
            fragment_counts=fragment_counts,
        )

    height, lines = linebox_module.layout_inline_content(
        box,
        available_width=cb_width,
        metrics=metrics,
        layout_atomic=layout_atomic,
        fragment_counts=fragment_counts,
    )
    box.line_boxes = lines
    metrics["heights_from_line_boxes"] += 1
    return height, None


def _layout_atomic(
    box: Box,
    *,
    metrics: Counter[str],
    groups: list[MarginGroup],
    fragment_counts: dict[int, int],
) -> tuple[float, float | None]:
    """Lay out one atomic inline's contents. `(border height, baseline)`.

    The baseline is the offset of the **last line box's** baseline from the
    box's top border edge, or `None` when there is none -- CSS 2.1 section
    10.8.1 then uses the bottom margin edge, and `layout.linebox` counts the
    two branches separately so "it had none" and "we did not look" stay
    distinguishable.

    `already_counted=True` because `_account_inline_box` has already put
    this box in `widths_shrink_to_fit_resolved`; counting it again as
    `widths_resolved` would break the box partition, which is exactly what
    that partition is for.

    The margin groups are the **same** registry as the surrounding layout's,
    not a fresh one. An atomic inline establishes a new formatting context,
    so `_establishes_formatting_context` closes both its edges and nothing
    collapses across them anyway; giving it its own list would leave those
    edges out of `_partition_margin_edges` and fail the edge partition for a
    reason that has nothing to do with collapsing.
    """
    width = box.shrink_to_fit_width
    assert width is not None, (
        "an atomic inline reached line layout without a shrink-to-fit "
        f"width: {box!r}"
    )
    result = _layout_block(
        box,
        cb_width=width,
        cb_height=None,
        metrics=metrics,
        groups=groups,
        fragment_counts=fragment_counts,
        override_content_width=width,
        already_counted=True,
    )
    style = _style_of(box)
    baseline = None
    if style.overflow == "visible":
        baseline = _last_line_baseline(box)
    return result.border_height, baseline


def _last_line_baseline(box: Box) -> float | None:
    """The last line box baseline inside `box`, from its top border edge.

    Recursive, because CSS 2.1 says "the baseline of its last line box" and
    that line box can be several block levels down -- an `inline-block`
    containing a `<div>` containing a paragraph takes the paragraph's last
    line. The **maximum** candidate is returned rather than the last one
    found in tree order: with no floats and no out-of-flow boxes placed, the
    two agree, and taking the maximum is the one that stays right when they
    stop agreeing.
    """
    geometry = box.geometry
    if geometry is None:
        return None
    content_offset = geometry.content.y - geometry.border.y
    best: float | None = None
    if box.line_boxes:
        line = box.line_boxes[-1]
        best = content_offset + line.y + line.baseline
    for child in box.children:
        child_geometry = child.geometry
        if child_geometry is None:
            continue
        inner = _last_line_baseline(child)
        if inner is None:
            continue
        candidate = content_offset + child_geometry.border.y + inner
        best = candidate if best is None else max(best, candidate)
    return best


def _account_inline_box(box: Box, metrics: Counter[str], *, cb_width: float) -> None:
    """One box inside an inline formatting context, and its descendants.

    Recursive rather than `walk()`-flat for one reason: an atomic inline's
    own content width is the containing block for anything nested inside
    it, so the shrink-to-fit basis changes as the walk descends. Flattening
    would size a nested `inline-block` against its grandparent.

    An atomic inline is counted here and **not descended into**: it is a
    block container on the inside, so its subtree is counted when
    `_layout_atomic` lays it out. Descending here as well is how a box gets
    counted twice, which the box partition would then report as a failure
    with no obvious cause.
    """
    metrics["layout_boxes_seen"] += 1
    style = _style_of(box)
    out_of_flow = _is_out_of_flow(style)
    if out_of_flow is not None:
        # A float or an absolutely positioned box **inside** an inline
        # formatting context. Task C takes these out of the block flow and
        # Task D2 has to take them out of the inline flow for the same
        # reason: neither is laid out, and leaving one in the line would
        # push every word after it along by a width Chrome does not put
        # there. That is the `clear` trap from the other end -- disagreeing
        # with a browser on the case we can reach in order to half-handle
        # one we cannot.
        #
        # Found by the character-conservation check, not by reading: the
        # float's text was reaching a fragment and the count of characters
        # never laid out was 0 where it should have been the float's.
        metrics[
            "layout_float_skipped"
            if out_of_flow == "float"
            else "layout_absolute_skipped"
        ] += 1
        metrics["widths_shrink_to_fit_resolved"] += 1
        _resolve_shrink_to_fit(box, cb_width=cb_width, metrics=metrics)
        for child in box.children:
            for descendant in child.walk():
                metrics["layout_boxes_seen"] += 1
                metrics["layout_boxes_deferred_subtree"] += 1
        return
    if box.display in ATOMIC_INLINE_DISPLAYS:
        metrics["widths_shrink_to_fit_resolved"] += 1
        _resolve_shrink_to_fit(box, cb_width=cb_width, metrics=metrics)
        return
    if box.is_inline_level:
        metrics["widths_not_applicable_inline_level"] += 1
    else:
        metrics["layout_boxes_deferred_subtree"] += 1
    for child in box.children:
        _account_inline_box(child, metrics, cb_width=cb_width)


def _layout_children(
    box: Box,
    *,
    metrics: Counter[str],
    groups: list[MarginGroup],
    fragment_counts: dict[int, int],
    cb_width: float,
    cb_height: float | None,
    top_group: MarginGroup | None,
    bottom_open: bool,
) -> tuple[float, MarginGroup | None, bool]:
    """Lay out the in-flow block-level children, collapsing as it goes.

    Returns `(content_height, trailing_margin_group, all_collapsed_through)`.

    `top_group` is the parent's own top-margin group when the parent's top
    edge is open -- passing it in is how a parent's top margin collapses
    *through* its own top border edge with its first child's, which is what
    moves the parent rather than the child. While that group is still the
    open one, a child sits at the parent's content top and the collapsed
    margin is exported upward instead of consumed here.

    `trailing_margin_group` is the still-open group at the bottom when
    `bottom_open`, for the parent to merge with its own bottom margin; when
    the bottom is closed the trailing margins are consumed inside the
    parent's height instead, and None comes back.
    """
    collector = top_group if top_group is not None else _new_group(groups)
    exporting_top = top_group is not None
    flow_y = 0.0
    all_collapsed_through = True

    for child in box.children:
        style = _style_of(child)
        out_of_flow = _is_out_of_flow(style)
        if out_of_flow is not None:
            # Never collapses with an in-flow sibling and contributes
            # nothing to the parent's height. Not implemented, so the whole
            # subtree is deferred rather than mispositioned.
            metrics["margin_collapse_blocked_out_of_flow"] += 1
            metrics[
                "layout_float_skipped"
                if out_of_flow == "float"
                else "layout_absolute_skipped"
            ] += 1
            _resolve_shrink_to_fit(child, cb_width=cb_width, metrics=metrics)
            _defer_subtree(
                child, metrics, reason="widths_shrink_to_fit_resolved"
            )
            continue
        if child.is_inline_level:
            # Reached, and measured rather than assumed. Task B leaves a
            # block container's children alone when they are *all*
            # inline-level, so a container holding nothing but collapsible
            # white space arrives here: `_has_line_boxes` correctly says it
            # has no line boxes (white space that collapses away produces
            # none, which is why it still collapses through), and then its
            # blank text children turn up in the block-flow loop.
            #
            # Seven of them on the corpus, all on Wikipedia, all blank text.
            # An earlier version of this comment claimed the branch was
            # unreachable for a well-formed tree and sent every case to
            # `widths_deferred_other`; the fourth bucket read 7 instead of 0
            # and that is what the bucket is for.
            _defer_subtree(
                child,
                metrics,
                reason=(
                    "widths_not_applicable_inline_level"
                    if _is_blank_text_box(child)
                    else "widths_deferred_other"
                ),
            )
            continue

        override = None
        if box.table_wrapper and child.display in table_module.TABLE_DISPLAYS:
            # The table box's width came from section 17.5.2, not from the
            # constraint equation. `Box.table_plan` carries it the one
            # level down, from the wrapper that computed it to the table box
            # that consumes it.
            override = child.table_plan.content_width
        result = _layout_block(
            child,
            cb_width=cb_width,
            cb_height=cb_height,
            metrics=metrics,
            groups=groups,
            fragment_counts=fragment_counts,
            override_content_width=override,
        )
        _merge_and_count(collector, result.top, metrics)

        if result.collapsed_through:
            # A zero-height box whose margins all collapse into one group.
            # Its border edge sits at the flow position plus the group as it
            # stands *including* its own margins -- measured against Chrome
            # 151 with a deliberately increasing chain (siblings 5, then
            # empty boxes of 10, 20, 30): the three empty boxes landed at
            # +10, +20 and +30, not all at the final collapsed value.
            offset = flow_y if exporting_top else flow_y + collector.value()
            _shift(child, offset)
            continue

        all_collapsed_through = False
        child_y = flow_y if exporting_top else flow_y + collector.value()
        _shift(child, child_y)
        _record_collapsed_margins(child, collector, top=True)
        flow_y = child_y + result.border_height
        collector = result.bottom
        exporting_top = False

    if exporting_top:
        # No in-flow block-level child closed the group: everything inside
        # collapsed through, so nothing was consumed here.
        return 0.0, (collector if bottom_open else None), True

    if bottom_open:
        _record_collapsed_margins_bottom(box, collector)
        return flow_y, collector, all_collapsed_through

    # The trailing margins cannot escape, so they take up space inside.
    return flow_y + collector.value(), None, all_collapsed_through


def _merge_and_count(
    collector: MarginGroup, incoming: MarginGroup, metrics: Counter[str]
) -> None:
    """Join two adjoining margin groups, counting the collapse event.

    `margins_collapsed` counts *events* -- one per pair of non-empty groups
    actually joined -- which is the number a reader wants. The edge-level
    partition is computed once at the end from the union-find roots, so it
    cannot drift from the merging done here.
    """
    if collector.merge(incoming):
        metrics["margins_collapsed"] += 1


def _record_collapsed_margins(child: Box, collector: MarginGroup, *, top: bool) -> None:
    geometry = child.geometry
    if geometry is None:
        return
    if top:
        geometry.collapsed_margin_top = collector.value()


def _record_collapsed_margins_bottom(box: Box, collector: MarginGroup) -> None:
    geometry = box.geometry
    if geometry is not None:
        geometry.collapsed_margin_bottom = collector.value()


def _resolve_height(
    style: ComputedStyle,
    cb_height: float | None,
    cb_width: float,
    metrics: Counter[str],
) -> float | None:
    """CSS 2.1 section 10.6.3. None means `auto`.

    A percentage height whose containing block's height depends on its own
    content is treated as `auto` -- the spec's own fallback, and Chrome
    agrees: `height: 25%` inside an auto-height parent measured 0, not a
    quarter of anything.
    """
    if style.height is AUTO:
        return None
    if isinstance(style.height, Percent):
        if cb_height is None:
            metrics["heights_percentage_fallback_auto"] += 1
            return None
        metrics["heights_specified"] += 1
        return float(style.height.value) / 100.0 * cb_height
    metrics["heights_specified"] += 1
    return max(0.0, _px_or_zero(style.height, basis=cb_width, metrics=metrics))


def _assign_geometry(
    box: Box,
    *,
    horizontal: _Horizontal,
    margin_top: float,
    margin_bottom: float,
    padding_top: float,
    padding_bottom: float,
    border_top: float,
    border_bottom: float,
    content_height: float,
    inner_x: float,
    inner_y: float,
    cb_width: float,
    collapsed_through: bool = False,
) -> None:
    border_x = horizontal.margin_left
    padding_x = border_x + horizontal.border_left
    content_x = padding_x + horizontal.padding_left
    content_y = inner_y
    padding_height = padding_top + content_height + padding_bottom
    border_height = border_top + padding_height + border_bottom
    padding_width = (
        horizontal.padding_left + horizontal.content_width + horizontal.padding_right
    )
    border_width = horizontal.border_left + padding_width + horizontal.border_right
    box.geometry = BoxGeometry(
        content=Rect(content_x, content_y, horizontal.content_width, content_height),
        padding=Rect(padding_x, border_top, padding_width, padding_height),
        border=Rect(border_x, 0.0, border_width, border_height),
        margin=Rect(
            border_x - horizontal.margin_left,
            -margin_top,
            horizontal.margin_left + border_width + horizontal.margin_right,
            margin_top + border_height + margin_bottom,
        ),
        used_margin=Edges(
            margin_top, horizontal.margin_right, margin_bottom, horizontal.margin_left
        ),
        used_padding=Edges(
            padding_top,
            horizontal.padding_right,
            padding_bottom,
            horizontal.padding_left,
        ),
        used_border=Edges(
            border_top, horizontal.border_right, border_bottom, horizontal.border_left
        ),
        containing_block_width=cb_width,
        collapsed_through=collapsed_through,
    )


def _shift(box: Box, dy: float) -> None:
    """Move a box down by `dy`, in O(1).

    Its children's coordinates are relative to *its* content box, so they do
    not move with it here; `_absolutize` composes the chain once at the end.
    """
    geometry = box.geometry
    if geometry is None or dy == 0.0:
        return
    geometry.content = replace(geometry.content, y=geometry.content.y + dy)
    geometry.padding = replace(geometry.padding, y=geometry.padding.y + dy)
    geometry.border = replace(geometry.border, y=geometry.border.y + dy)
    geometry.margin = replace(geometry.margin, y=geometry.margin.y + dy)


def _absolutize(box: Box, origin_x: float, origin_y: float) -> None:
    """Turn containing-block-relative coordinates into absolute document
    ones, per the Phase 3 comparison contract.

    Three things move, not one. A block box moves its own rectangles and
    then becomes the origin for its children. An **inline** box has no
    rectangles of its own -- it has fragments, and they are relative to the
    inline formatting context's block container, which is *not* this box --
    so its fragments move by the origin it was handed and it passes that
    same origin down unchanged. Getting that wrong nests the offsets and
    puts every wrapped word a containing block too far right, which looks
    like a text-measurement error.
    """
    geometry = box.geometry
    child_origin = (origin_x, origin_y)
    if geometry is not None:
        geometry.content = replace(
            geometry.content,
            x=geometry.content.x + origin_x,
            y=geometry.content.y + origin_y,
        )
        geometry.padding = replace(
            geometry.padding,
            x=geometry.padding.x + origin_x,
            y=geometry.padding.y + origin_y,
        )
        geometry.border = replace(
            geometry.border,
            x=geometry.border.x + origin_x,
            y=geometry.border.y + origin_y,
        )
        geometry.margin = replace(
            geometry.margin,
            x=geometry.margin.x + origin_x,
            y=geometry.margin.y + origin_y,
        )
        child_origin = (geometry.content.x, geometry.content.y)
    for fragment in box.fragments:
        if fragment.geometry is geometry:
            # An atomic inline is one box with one rectangle that is also
            # its single fragment, so the two names point at the same
            # object and shifting it twice would put it a containing block
            # too far down. Identity, not equality: two rectangles that
            # happen to coincide are still two boxes.
            continue
        _absolutize_fragment(fragment, origin_x, origin_y)
    if box.line_boxes:
        for line in box.line_boxes:
            line.x += child_origin[0]
            line.y += child_origin[1]
    for child in box.children:
        _absolutize(child, *child_origin)


def _absolutize_fragment(fragment, origin_x: float, origin_y: float) -> None:
    geometry = fragment.geometry
    for name in ("content", "padding", "border", "margin"):
        rect = getattr(geometry, name)
        setattr(
            geometry, name, replace(rect, x=rect.x + origin_x, y=rect.y + origin_y)
        )


# --------------------------------------------------------------------------
# The mechanical checks
# --------------------------------------------------------------------------


def assert_layout_constraints(
    root: Box, *, initial_containing_block_width: float, metrics: Counter[str]
) -> None:
    """Three partitions, all failing loudly, run on every layout.

    The constraint equation is read off the **rectangles**, not off the
    scalars the width resolver produced, and the containing block's width is
    read from the parent's content rectangle rather than from the number
    stored on the child. A resolver that satisfies its own equation while
    laying a child out against the wrong containing block, or an
    absolutization pass that composes an offset wrongly, fails here; a
    version that only re-read the stored scalars would agree with itself and
    catch neither.
    """
    _assert_box_partition(metrics)
    _assert_margin_edge_partition(metrics)
    _assert_collapse_barrier_partition(metrics)
    linebox_module.assert_line_partitions(metrics)
    linebox_module.assert_text_conservation(root, metrics)
    _assert_geometry(root, cb_x=0.0, cb_width=initial_containing_block_width)


def _assert_box_partition(metrics: Counter[str]) -> None:
    parts = (
        metrics["widths_resolved"]
        + metrics["widths_shrink_to_fit_resolved"]
        + metrics["widths_deferred_shrink_to_fit"]
        + metrics["widths_not_applicable_inline_level"]
        + metrics["widths_deferred_other"]
        + metrics["layout_boxes_deferred_subtree"]
    )
    assert metrics["layout_boxes_seen"] == parts, (
        "every box is laid out or deferred for exactly one named reason: "
        f"seen {metrics['layout_boxes_seen']} != {parts}"
    )


COLLAPSE_BARRIERS: tuple[str, ...] = (
    "root",
    "padding_top",
    "border_top",
    "padding_bottom",
    "border_bottom",
    "parent_height",
    "new_formatting_context",
)


def _assert_collapse_barrier_partition(metrics: Counter[str]) -> None:
    blocked = sum(
        metrics[f"margin_collapse_blocked_{reason}"]
        for reason in COLLAPSE_BARRIERS
    )
    total = metrics["collapse_barrier_edges_open"] + blocked
    assert metrics["collapse_barrier_edges_seen"] == total, (
        "every vertical edge is open to collapsing or closed for exactly one "
        f"named reason: seen {metrics['collapse_barrier_edges_seen']} != "
        f"{total}"
    )


def _assert_margin_edge_partition(metrics: Counter[str]) -> None:
    total = metrics["margin_edges_collapsed"] + metrics["margin_edges_alone"]
    assert metrics["margin_edges_seen"] == total, (
        "every vertical margin edge either joins a collapsing group or "
        f"stands alone: seen {metrics['margin_edges_seen']} != {total}"
    )


def _assert_geometry(box: Box, *, cb_x: float, cb_width: float) -> None:
    """Section 10.3.3 as a tiling, plus the edge relations, on every box.

    Two exemptions, both stated rather than achieved by returning early:

    * **A box with no geometry is not laid out**, but its descendants may
      be. An inline box carries fragments and no rectangles, and everything
      on its lines hangs below it, so the walk continues with the same
      containing block instead of stopping. Task C could stop, because
      nothing below an unlaid-out box had geometry either.
    * **The tiling is a block-level rule.** Section 10.3.3 is stated for
      "block-level, non-replaced elements in normal flow"; an atomic
      inline's margin box is its shrink-to-fit width and spans nothing.
      Its internal edge relations still hold and are still checked, which
      is the half of this that would catch a wrong `box-sizing`.
    """
    geometry = box.geometry
    if geometry is None:
        for child in box.children:
            _assert_geometry(child, cb_x=cb_x, cb_width=cb_width)
        return
    where = box.path or f"<{box.origin} {box.display}>"

    if not box.is_inline_level and box.display not in _TABLE_INTERNAL_DISPLAYS:
        # Section 10.3.3, stated as a tiling: the margin box exactly spans
        # the containing block's content width, starting at its left edge.
        #
        # A third exemption since Task E, and it is the same kind as the
        # atomic-inline one above: section 17.5.2's own words are "this
        # section overrides the rules that apply to calculating widths as
        # described in section 10.3". A cell's width is its column's and a
        # row's is the grid's, so neither spans its containing block.
        # `layout.table.assert_table_constraints` is the equation that
        # replaces this one for them, and it is stricter -- it checks the
        # cells tile the row rather than only that each one is inside it.
        _close(
            geometry.margin.width,
            cb_width,
            f"{where}: margin box width {geometry.margin.width} != containing "
            f"block width {cb_width} (CSS 2.1 section 10.3.3)",
        )
        _close(
            geometry.margin.x,
            cb_x,
            f"{where}: margin box starts at {geometry.margin.x}, containing "
            f"block content starts at {cb_x}",
        )

    margin = geometry.used_margin
    padding = geometry.used_padding
    border = geometry.used_border
    _close(geometry.border.x, geometry.margin.x + margin.left, f"{where}: border x")
    _close(geometry.padding.x, geometry.border.x + border.left, f"{where}: padding x")
    _close(
        geometry.content.x, geometry.padding.x + padding.left, f"{where}: content x"
    )
    _close(geometry.border.y, geometry.margin.y + margin.top, f"{where}: border y")
    _close(geometry.padding.y, geometry.border.y + border.top, f"{where}: padding y")
    _close(geometry.content.y, geometry.padding.y + padding.top, f"{where}: content y")
    _close(
        geometry.margin.width,
        geometry.border.width + margin.left + margin.right,
        f"{where}: margin width",
    )
    _close(
        geometry.border.width,
        geometry.padding.width + border.left + border.right,
        f"{where}: border width",
    )
    _close(
        geometry.padding.width,
        geometry.content.width + padding.left + padding.right,
        f"{where}: padding width",
    )
    _close(
        geometry.margin.height,
        geometry.border.height + margin.top + margin.bottom,
        f"{where}: margin height",
    )
    _close(
        geometry.border.height,
        geometry.padding.height + border.top + border.bottom,
        f"{where}: border height",
    )
    _close(
        geometry.padding.height,
        geometry.content.height + padding.top + padding.bottom,
        f"{where}: padding height",
    )

    for child in box.children:
        _assert_geometry(child, cb_x=geometry.content.x, cb_width=geometry.content.width)


def _close(actual: float, expected: float, message: str) -> None:
    assert math.isclose(actual, expected, rel_tol=0.0, abs_tol=EPSILON), (
        f"{message} (got {actual}, expected {expected})"
    )


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------


def layout_document(
    root: Box | None, viewport: Viewport | None = None
) -> Counter[str]:
    """Lay out a box tree. Returns the metrics; writing them is a driver's
    job, per the note at the top of `mayshay/metrics.py`.

    The initial containing block is the viewport, at the document origin.
    `root` is the box for the root element, whose margins never collapse
    with anything.
    """
    metrics: Counter[str] = Counter()
    for name in COUNTER_NAMES + inline_module.COUNTER_NAMES + (
        intrinsic_module.COUNTER_NAMES
    ) + table_module.COUNTER_NAMES:
        metrics[name] = 0

    # CSS 2.1 section 17.2.1's anonymous table objects and 17.4's wrapper
    # box, **before** white-space processing. The fixup changes which boxes
    # sit in which inline formatting context -- a run of text inside a
    # `display: table` gains an anonymous row and cell around it -- and
    # collapsing text first would decide those contexts against a tree that
    # is about to change.
    table_module.fix_up_tables(root, metrics)

    # White-space processing first, over the whole tree. Intrinsic sizing
    # reads `Box.text` and Task D2's line breaking will too; collapsing it
    # once here is what stops the two from disagreeing about a space. It
    # runs even when there is no root, so an empty document still emits a
    # seeded row rather than no row.
    inline_module.process_text(root, metrics)
    if root is None:
        return metrics

    viewport = viewport if viewport is not None else Viewport()
    groups: list[MarginGroup] = []
    # One fragment counter for the whole document, keyed by DOM node, and
    # for the same reason `groups` is one list: an inline that Task B split
    # around a block-level child contributes boxes to **two** inline
    # formatting contexts, and Chrome answers `getContentQuads` for the node
    # with one quad per fragment across the whole split. A per-context
    # counter restarts at 0 in the second half and produces two fragments
    # numbered 0 for one node -- which no comparison can tell from one
    # fragment measured twice.
    fragment_counts: dict[int, int] = {}
    result = _layout_block(
        root,
        cb_width=float(viewport.width_px),
        cb_height=float(viewport.height_px),
        metrics=metrics,
        groups=groups,
        fragment_counts=fragment_counts,
        is_root=True,
    )
    _partition_margin_edges(groups, metrics)
    # The root's own top margin is applied above its border edge: it has
    # nothing above it to collapse with.
    _shift(root, result.top.value())
    if root.geometry is not None:
        root.geometry.collapsed_margin_top = result.top.value()
        root.geometry.collapsed_margin_bottom = result.bottom.value()
    _absolutize(root, 0.0, 0.0)
    assert_layout_constraints(
        root,
        initial_containing_block_width=float(viewport.width_px),
        metrics=metrics,
    )
    return metrics
