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
mechanical checks have caught all of it, so there are three, all of them run
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
3. **A box-disposition partition.** Every box in the tree is laid out or
   deferred for exactly one named reason, and the reasons sum.

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
from mayshay.cssparse.values import AUTO, Length, Percent
from mayshay.layout.boxtree import Box

# Floating-point slack for the constraint assertions. Every number here is a
# sum of a handful of terms, so a real violation is orders of magnitude
# larger than this and a rounding artefact is orders of magnitude smaller.
EPSILON = 1e-6

# The displays whose *inner* layout is block layout. Everything else that is
# block-level -- flex, the table family -- has its own inner algorithm in
# Task E or Task F; Task C lays their children out as block flow and counts
# it, exactly as Task B counts `display: grid` falling back to `block`.
BLOCK_CONTAINER_DISPLAYS: frozenset[str] = frozenset({"block", "list-item"})

# Inline-level and atomic: an inline-level box on the outside, a block
# container on the inside. Its width is shrink-to-fit, so it cannot be
# resolved without Task D.
ATOMIC_INLINE_DISPLAYS: frozenset[str] = frozenset(
    {"inline-block", "inline-flex", "inline-table"}
)

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
    "widths_deferred_shrink_to_fit",
    "widths_not_applicable_inline_level",
    "widths_deferred_other",
    # heights
    "heights_specified",
    "heights_from_children",
    "heights_deferred_inline_content",
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
    "parent_child_edges_seen",
    "parent_child_edges_open",
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
    "layout_table_box_margins_applied",
    "layout_length_unit_unresolved",
    "layout_boxes_deferred_subtree",
)

# The style an anonymous box is laid out with. Anonymous boxes have no
# declarations of their own -- CSS 2.1 section 9.2.1.1 gives them the
# initial value of every non-inherited property -- so one shared instance is
# correct as long as nothing mutates it, and nothing here does.
_ANONYMOUS_STYLE = ComputedStyle(display="block")

# The computed initial value of every margin longhand, for the one place
# that needs to know whether a margin was *declared* rather than what it
# resolves to.
_ZERO = ComputedStyle().margin_top


# --------------------------------------------------------------------------
# Geometry
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Rect:
    """`x, y, width, height` in CSS pixels, per the Phase 3 comparison
    contract. Not a quad: CDP's quads carry a transform capability this
    engine does not implement, and converting between the two is one
    function on the harness side."""

    x: float
    y: float
    width: float
    height: float

    @property
    def right(self) -> float:
        return self.x + self.width

    @property
    def bottom(self) -> float:
        return self.y + self.height


@dataclass(frozen=True)
class Edges:
    top: float
    right: float
    bottom: float
    left: float


@dataclass
class BoxGeometry:
    """All four box edges, plus the used values they were built from.

    The rectangles are relative to the containing block's content origin
    while layout runs and absolute document coordinates afterwards, with the
    origin at the document's top-left and y increasing downward -- the
    Phase 3 contract's requirement, and what `DOM.getBoxModel` reports.

    The **margin box uses the box's own used margins, not the collapsed
    ones.** A collapsed margin is shared between two boxes, so it belongs to
    neither margin box; the margin boxes of two vertically adjacent siblings
    with collapsing margins genuinely overlap, which is what Chrome reports
    too. `collapsed_margin_top` and `collapsed_margin_bottom` record what was
    actually applied in the flow, because that is the number a margin-
    collapsing test needs and it is not recoverable from the rectangles.
    """

    content: Rect
    padding: Rect
    border: Rect
    margin: Rect
    used_margin: Edges
    used_padding: Edges
    used_border: Edges
    containing_block_width: float
    collapsed_margin_top: float = 0.0
    collapsed_margin_bottom: float = 0.0


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


def _px(value: object, *, basis: float, metrics: Counter[str]) -> float | None:
    """A computed length or percentage as pixels, or None for `auto`.

    `basis` is the containing block's **width** for every percentage this
    module resolves, vertical margins and vertical padding included --
    CSS 2.1 sections 8.3 and 8.4, and `docs/percentage-resolution.md`.
    Measured against Chrome 151 rather than taken from the spec text: a
    `margin-top: 10%` in a 400x800 containing block is 40px, not 80px.
    """
    if value is AUTO:
        return None
    if isinstance(value, Percent):
        return float(value.value) / 100.0 * basis
    if isinstance(value, Length):
        if value.unit != "px":
            # The cascade converts every absolute and font-relative unit to
            # px; a survivor is one it could not resolve (a viewport unit
            # cascaded with no viewport). Counted rather than guessed.
            metrics["layout_length_unit_unresolved"] += 1
            return 0.0
        return float(value.value)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    metrics["layout_length_unit_unresolved"] += 1
    return 0.0


def _px_or_zero(value: object, *, basis: float, metrics: Counter[str]) -> float:
    resolved = _px(value, basis=basis, metrics=metrics)
    return 0.0 if resolved is None else resolved


def _style_of(box: Box) -> ComputedStyle:
    if box.origin == "element" and box.node is not None:
        style = box.node.computed_style
        if style is not None:
            return style
    return _ANONYMOUS_STYLE


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
    if box.display in ATOMIC_INLINE_DISPLAYS:
        return "new_formatting_context"
    if box.display in NON_BLOCK_INNER_DISPLAYS:
        return "new_formatting_context"
    return None


def _has_in_flow_block_children(box: Box) -> bool:
    """Is there anything here for a parent/child margin collapse to happen
    *to*? A barrier on a box with no in-flow block-level child blocked
    nothing, and counting it would turn every leaf `<div>` with padding into
    a margin-collapsing event."""
    for child in box.children:
        if child.is_inline_level:
            continue
        if _is_out_of_flow(_style_of(child)) is not None:
            continue
        return True
    return False


def _is_blank_text_box(box: Box) -> bool:
    return (
        box.origin == "text"
        and box.node is not None
        and not box.node.data.strip()
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
    style: ComputedStyle, cb_width: float, metrics: Counter[str]
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
    left_auto = margin_left is None
    right_auto = margin_right is None
    margin_left = 0.0 if left_auto else margin_left
    margin_right = 0.0 if right_auto else margin_right

    declared_width = _px(style.width, basis=cb_width, metrics=metrics)
    border_box_sizing = style.box_sizing == "border-box"
    if border_box_sizing and declared_width is not None:
        metrics["box_sizing_border_box"] += 1

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
            metrics["width_over_constrained_margin_right_ignored"] += 1
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
    is_root: bool = False,
) -> _Result:
    """Lay out one in-flow block-level box and everything under it.

    Geometry is written relative to the containing block's content origin;
    `_absolutize` converts the whole tree once at the end. The box's own y is
    left at zero here and set by the caller with `_shift`, because the y
    depends on a collapsed margin the caller computes from this result --
    and shifting a box is O(1) precisely because its children's coordinates
    are relative to *it*.
    """
    metrics["layout_boxes_seen"] += 1
    metrics["widths_resolved"] += 1
    style = _style_of(box)
    if box.display in _TABLE_INTERNAL_DISPLAYS and (
        style.margin_top is not _ZERO
        or style.margin_bottom is not _ZERO
        or style.margin_left is not _ZERO
        or style.margin_right is not _ZERO
    ):
        # CSS 2.1 section 17.6: the margin properties do not apply to
        # table-internal boxes. Task E owns that; here the margins are
        # applied like any other block's, which is why a `table-cell` with a
        # margin sits 10px lower than Chrome puts it. Counted rather than
        # silently different -- it is the only fixture in
        # `tests/layout/test_block.py` where this engine and Chrome 151
        # disagree on purpose.
        metrics["layout_table_box_margins_applied"] += 1
    if style.position == "relative":
        # In flow and laid out at its static position. `top`/`left` are not
        # in `ComputedStyle` at all, so a relative box cannot be offset even
        # in principle yet; counted so the gap is a number.
        metrics["layout_position_relative_unoffset"] += 1

    horizontal = _resolve_width(style, cb_width, metrics)

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
        content_height, trailing = _defer_inline_content(box, metrics)
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
        content_height, trailing, all_collapsed_through = _layout_children(
            box,
            metrics=metrics,
            groups=groups,
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

    if _has_in_flow_block_children(box):
        # One reason per edge, and the two open-or-closed counts partition
        # with the per-reason ones -- asserted in `assert_layout_constraints`.
        # This is the check that fails the moment a barrier is added to the
        # rule set and forgotten in the counting.
        metrics["parent_child_edges_seen"] += 2
        for closed_by in (top_closed_by, bottom_closed_by):
            if closed_by is None:
                metrics["parent_child_edges_open"] += 1
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


def _defer_inline_content(
    box: Box, metrics: Counter[str]
) -> tuple[float, MarginGroup | None]:
    """Account for an inline formatting context without measuring it."""
    metrics["heights_deferred_inline_content"] += 1
    for child in box.children:
        for descendant in child.walk():
            metrics["layout_boxes_seen"] += 1
            if descendant.display in ATOMIC_INLINE_DISPLAYS:
                metrics["widths_deferred_shrink_to_fit"] += 1
            elif descendant.is_inline_level:
                metrics["widths_not_applicable_inline_level"] += 1
            else:
                metrics["layout_boxes_deferred_subtree"] += 1
    return 0.0, None


def _layout_children(
    box: Box,
    *,
    metrics: Counter[str],
    groups: list[MarginGroup],
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
            _defer_subtree(child, metrics, reason="widths_deferred_shrink_to_fit")
            continue
        if child.is_inline_level:
            # Task B guarantees a block container's children are either all
            # block-level or all inline-level, so this is unreachable for a
            # well-formed tree; it is here so a malformed one is a counted
            # number rather than a wrong position.
            _defer_subtree(child, metrics, reason="widths_deferred_other")
            continue

        result = _layout_block(
            child,
            cb_width=cb_width,
            cb_height=cb_height,
            metrics=metrics,
            groups=groups,
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
    ones, per the Phase 3 comparison contract."""
    geometry = box.geometry
    if geometry is None:
        return
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
    for child in box.children:
        _absolutize(child, geometry.content.x, geometry.content.y)


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
    _assert_parent_child_edge_partition(metrics)
    _assert_geometry(root, cb_x=0.0, cb_width=initial_containing_block_width)


def _assert_box_partition(metrics: Counter[str]) -> None:
    parts = (
        metrics["widths_resolved"]
        + metrics["widths_deferred_shrink_to_fit"]
        + metrics["widths_not_applicable_inline_level"]
        + metrics["widths_deferred_other"]
        + metrics["layout_boxes_deferred_subtree"]
    )
    assert metrics["layout_boxes_seen"] == parts, (
        "every box is laid out or deferred for exactly one named reason: "
        f"seen {metrics['layout_boxes_seen']} != {parts}"
    )


PARENT_CHILD_BARRIERS: tuple[str, ...] = (
    "root",
    "padding_top",
    "border_top",
    "padding_bottom",
    "border_bottom",
    "parent_height",
    "new_formatting_context",
)


def _assert_parent_child_edge_partition(metrics: Counter[str]) -> None:
    blocked = sum(
        metrics[f"margin_collapse_blocked_{reason}"]
        for reason in PARENT_CHILD_BARRIERS
    )
    total = metrics["parent_child_edges_open"] + blocked
    assert metrics["parent_child_edges_seen"] == total, (
        "every parent/child margin edge is open or closed for exactly one "
        f"named reason: seen {metrics['parent_child_edges_seen']} != {total}"
    )


def _assert_margin_edge_partition(metrics: Counter[str]) -> None:
    total = metrics["margin_edges_collapsed"] + metrics["margin_edges_alone"]
    assert metrics["margin_edges_seen"] == total, (
        "every vertical margin edge either joins a collapsing group or "
        f"stands alone: seen {metrics['margin_edges_seen']} != {total}"
    )


def _assert_geometry(box: Box, *, cb_x: float, cb_width: float) -> None:
    geometry = box.geometry
    if geometry is None:
        return
    where = box.path or f"<{box.origin} {box.display}>"

    # Section 10.3.3, stated as a tiling: the margin box exactly spans the
    # containing block's content width, starting at its left edge.
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
    for name in COUNTER_NAMES:
        metrics[name] = 0
    if root is None:
        return metrics

    viewport = viewport if viewport is not None else Viewport()
    groups: list[MarginGroup] = []
    result = _layout_block(
        root,
        cb_width=float(viewport.width_px),
        cb_height=float(viewport.height_px),
        metrics=metrics,
        groups=groups,
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
