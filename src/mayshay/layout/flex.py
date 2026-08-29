"""Flex layout -- Phase 3 Task F. CSS Flexible Box Layout 1.

Four things live here, in the order a flex container meets them:

1. **Section 4's anonymous flex items**, which wrap a run of text or inline
   boxes so that everything inside a flex container is a block-level item.
2. **Section 9.2's item collection and flex base sizes**, where
   `flex-basis: auto` becomes the item's content size.
3. **Section 9.7's resolve-flexible-lengths loop**, the grow/shrink
   distribution, with section 4.5's automatic minimum size as the floor.
4. **Sections 9.5 and 9.6's alignment**, which spends whatever main-axis
   free space is left and places every item on the cross axis.

## The intrinsic sizes come from `layout.intrinsic`

`flex-basis: auto` on an item whose main size property is `auto` resolves
to that item's content size -- the same `max_content_width` Task C's
shrink-to-fit and Task E's column widths call, verified against Chrome 151
in the probe recorded in `intrinsic.py`'s docstring, where a flex item, a
table cell and an `inline-block` measured 19.27/394.95 to the hundredth of
a pixel for identical content. There is no fourth min-content in this file
and there must not be.

## What is implemented and what is counted

Implemented: `flex-direction` row and column, `flex-wrap: nowrap` and
`wrap`, `justify-content`, `align-items` / `align-self` including
`baseline`, `flex-grow` / `flex-shrink` / `flex-basis` resolution, the
automatic minimum size, `row-gap` / `column-gap`, and anonymous flex
items.

Counted, not implemented -- each with a name, so the divergence is a
number rather than an absence, and **each is zero on this corpus**
(executed; see the report and `docs/synthetic-only-coverage.md`):

* `order`. Items are laid out in document order. `flex_order_ignored`.
* `align-content`. Meaningful only when a **multi-line** container has
  leftover cross-axis space, which needs a definite cross size; with an
  auto cross size the lines exactly fill it and there is nothing to
  distribute. `flex_align_content_ignored` counts the reachable case only.
* `row-reverse` / `column-reverse` / `wrap-reverse`, laid out forwards.
  `flex_direction_reverse_as_forward`, `flex_wrap_reverse_as_wrap`.
* `auto` margins on an item, which section 9.6 makes absorb free space
  before `justify-content` sees it. Treated as zero, which is what section
  10.3.2 does for an atomic inline and what `_resolve_width`'s
  `override_content_width` path already did. `flex_item_auto_margin_zeroed`.
* `min-`/`max-width`/`height`, which `cssparse` does not parse at all, so
  the only clamp here is section 4.5's automatic minimum size.

## What the corpus can and cannot say about this

**Almost nothing, and the numbers are worth stating before any green
suite is read.** Measured at 1280x1024 with external sheets applied:
233 elements compute `flex` or `inline-flex`, 201 produce a box, and
**29 of those are laid out** -- the other 172 sit inside a float (146) or
absolutely positioned (26) subtree this engine declines to lay out. Of the
29, **sixteen hold exactly one item**, eleven hold two and two hold three
-- 44 items in all. A one-item flex container is very nearly a block
container: `justify-content` has nothing to distribute, `flex-grow` has no
competitor for the free space, and `order` cannot reorder anything.

So **13 containers on the corpus can discriminate any of the main-axis
work**, all of them on Wikipedia, and the tests here are synthetic and
written from Flexbox 1 for that reason. (The task brief said 193 of 233
hold one item and 33 hold more; both figures are over the DOM elements
rather than over the boxes that reach layout, and neither is reproducible
-- see `docs/synthetic-only-coverage.md`.)

Three things the corpus reaches that the Phase 3 plan did not schedule:
`flex-wrap: wrap` on 2 laid-out containers, a non-`normal` `column-gap` on
7 of them and `row-gap` on 6, and `align-items: baseline` on 2. Gap and
baseline alignment move real boxes -- removing gap moves 15 rectangles and
treating `baseline` as `flex-start` moves 1 -- while **wrapping moves
none**, because neither `wrap` container overflows its line. Wrapping is
implemented anyway, because the alternative is a rule that is wrong
wherever the corpus grows a container that does overflow, and it is
recorded as synthetic-only coverage.

## The mechanical check

`assert_flex_constraints` runs on every layout, not only under test, and
states the equation this module could get wrong while still producing
plausible geometry:

    free space distributed == free space available

read off the **rectangles** after absolutization -- the items' outer main
sizes, plus the gaps between them, plus whatever `justify-content` spent,
must exactly fill the container's content box along the main axis. A
distribution that lost a pixel, spent a gap twice, or grew items by a
total other than the free space fails here and nowhere else.
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass, field, replace

from mayshay.cssparse.cascade import ComputedStyle
from mayshay.cssparse.values import AUTO, Keyword, Length, Percent
from mayshay.layout import intrinsic as intrinsic_module
from mayshay.layout.boxtree import FLEX_DISPLAYS, Box
from mayshay.layout.geometry import EPSILON
from mayshay.layout.text import is_white_space_only
from mayshay.layout.used import px, px_or_zero, style_of

#: The two displays whose *inner* layout is flex layout, re-exported: every
#: caller reads it from here. It is defined in `boxtree` because
#: `layout.intrinsic` needs the same test -- a row flex container's
#: max-content width is the sum of its items, not the largest of them --
#: and this module imports `intrinsic`, so the set cannot live here.

# Box Alignment 3's `normal` behaves as these inside a flex container. The
# mapping is a used-value fact and lives here rather than in the cascade,
# where `normal` is what a browser computes and what this engine stores.
_JUSTIFY_NORMAL = "flex-start"
_ALIGN_NORMAL = "stretch"

# The positional keywords Box Alignment 3 adds, mapped onto the flex-
# relative pair this module implements. `start`/`end` are writing-mode
# relative and `left`/`right` are physical; with no `direction: rtl` and no
# vertical writing mode in this engine, all four coincide with the
# flex-relative ones -- which is exactly the "implement Y for the world
# where X is absent" rule from the Phase 3 plan. A page with `direction:
# rtl` would need them to diverge, and `direction` is not parsed.
_MAIN_START_ALIASES = frozenset({"flex-start", "start", "left"})
_MAIN_END_ALIASES = frozenset({"flex-end", "end", "right"})
_CROSS_START_ALIASES = frozenset({"flex-start", "start", "self-start"})
_CROSS_END_ALIASES = frozenset({"flex-end", "end", "self-end"})

COUNTER_NAMES: tuple[str, ...] = (
    "flex_containers_laid_out",
    "flex_containers_row",
    "flex_containers_column",
    "flex_lines",
    "flex_items_placed",
    "flex_anonymous_items",
    "flex_items_blockified",
    "flex_blank_runs_not_rendered",
    # section 9.2: where each item's flex base size came from. These four
    # partition `flex_items_placed`.
    "flex_basis_from_content",
    "flex_basis_from_main_size_property",
    "flex_basis_definite",
    "flex_basis_content_keyword",
    # section 9.7
    "flex_items_grown",
    "flex_items_shrunk",
    "flex_items_frozen_inflexible",
    "flex_items_clamped_to_min_content",
    "flex_free_space_positive",
    "flex_free_space_negative",
    "flex_free_space_exhausted",
    # sections 9.4 to 9.6
    "flex_lines_wrapped",
    "flex_items_stretched",
    "flex_items_aligned_baseline",
    "flex_items_baseline_synthesized",
    "flex_main_gap_applied",
    "flex_cross_gap_applied",
    "flex_percentage_gap_as_zero",
    # counted, not implemented
    "flex_order_ignored",
    "flex_align_content_ignored",
    "flex_direction_reverse_as_forward",
    "flex_wrap_reverse_as_wrap",
    "flex_item_auto_margin_zeroed",
    "flex_item_float_ignored",
    "flex_baseline_in_column_as_start",
    "flex_wrap_without_definite_main_size",
)


# --------------------------------------------------------------------------
# Section 4: anonymous flex items
# --------------------------------------------------------------------------


def fix_up_flex_containers(root: Box | None, metrics: Counter[str]) -> None:
    """Make every child of a flex container a block-level flex item, per
    Flexbox 1 section 4.

    Two different rules, and conflating them is the defect this docstring
    exists to prevent:

    * **A text run** -- a contiguous sequence of text boxes -- is wrapped in
      an anonymous block-level box. "However, if the entire sequence of
      child text runs contains only white space it is not rendered": a
      blank run produces no item at all, which is
      `flex_blank_runs_not_rendered` rather than an empty item. Without
      that, a flex container written across three source lines gains two
      invisible items and every gap and every justification is computed
      over the wrong count.
    * **An inline-level element** is *blockified* (CSS Display 3 section
      2.7): `inline` becomes `block`, `inline-block` becomes `block`,
      `inline-flex` becomes `flex`, `inline-table` becomes `table`. It does
      **not** join the text run around it.

    The difference is visible on two `<span>`s inside a flex container:
    blockified they are two items, and wrapped as a run they would be one.
    Executed against Chrome 151, which reports two boxes side by side.

    Run **before** white-space processing, for the reason
    `table.fix_up_tables` is: this changes which boxes sit in which inline
    formatting context -- a run of text directly inside a flex container
    becomes its own context -- and collapsing the text first would decide
    those contexts against a tree that is about to change.
    """
    if root is None:
        return
    for box in list(root.walk()):
        if box.display in FLEX_DISPLAYS and box.children:
            box.children = _flex_items_of(box.children, metrics)


#: CSS Display 3 section 2.7's blockification, for the inside-inline
#: displays this engine has. `inline-flex` becomes `flex` and not `block`:
#: blockification changes the *outer* display type and leaves the inner
#: one alone, and a nested flex container that became a block container
#: would lay its own children out with the wrong algorithm.
_BLOCKIFIED: dict[str, str] = {
    "inline": "block",
    "inline-block": "block",
    "inline-flex": "flex",
    "inline-table": "table",
}


def _flex_items_of(children: list[Box], metrics: Counter[str]) -> list[Box]:
    out: list[Box] = []
    run: list[Box] = []

    def flush() -> None:
        if not run:
            return
        if all(_is_blank(child) for child in run):
            metrics["flex_blank_runs_not_rendered"] += 1
        else:
            metrics["flex_anonymous_items"] += 1
            out.append(Box(display="block", origin="anonymous", children=list(run)))
        run.clear()

    for child in children:
        if child.origin == "text":
            run.append(child)
            continue
        flush()
        blockified = _BLOCKIFIED.get(child.display)
        if blockified is not None:
            metrics["flex_items_blockified"] += 1
            child.display = blockified
        out.append(child)
    flush()
    return out


def _is_blank(box: Box) -> bool:
    """A text box made only of CSS white space.

    `layout.text.is_white_space_only`, not `str.strip()`: the two disagree
    on U+00A0 and six other Unicode spaces that CSS Text 3 does not treat
    as white space, and an `&nbsp;`-only run *is* rendered and does produce
    an item.
    """
    return box.node is None or is_white_space_only(box.node.data)


# --------------------------------------------------------------------------
# The plan
# --------------------------------------------------------------------------


@dataclass
class FlexItem:
    """One flex item, with every quantity named on the **main/cross** axes
    rather than on x and y.

    That naming is the whole reason this dataclass exists. Section 9's
    arithmetic is identical for `row` and `column`; only the mapping to
    physical axes differs, and a version that spoke in widths and heights
    would need each rule written twice -- which is two places for the
    grow/shrink loop to be subtly different.
    """

    box: Box
    style: ComputedStyle
    #: border + padding along each axis: the part inside the border box that
    #: a content size has to have added to it.
    main_inside: float
    cross_inside: float
    #: used margins, main-start/main-end and cross-start/cross-end.
    main_margin_start: float
    main_margin_end: float
    cross_margin_start: float
    cross_margin_end: float
    grow: float
    shrink: float
    #: section 9.2: the flex base size, an **inner** (content-box) size.
    base_size: float
    #: section 4.5's automatic minimum size, also inner.
    min_main: float
    #: section 9.2 step 4's hypothetical main size, inner.
    hypothetical: float
    #: section 9.7's outcome, inner. Set by `_resolve_flexible_lengths`.
    target: float = 0.0
    frozen: bool = False
    #: the item's outer cross size once it has been laid out.
    outer_cross: float = 0.0
    #: distance from the item's outer cross-start edge to its first baseline,
    #: or None when it has none and one was synthesized.
    baseline: float | None = None
    #: filled by `_place`.
    main_offset: float = 0.0
    cross_offset: float = 0.0

    @property
    def main_extra(self) -> float:
        """Everything outside the content box on the main axis."""
        return self.main_inside + self.main_margin_start + self.main_margin_end

    @property
    def outer_hypothetical(self) -> float:
        return self.hypothetical + self.main_extra

    @property
    def outer_target(self) -> float:
        return self.target + self.main_extra


@dataclass
class FlexLine:
    """One flex line. Single-line containers have exactly one."""

    items: list[FlexItem]
    #: what `justify-content` spent: before the first item, between each
    #: adjacent pair, and after the last. The three are kept separately
    #: because the mechanical check adds them back up.
    leading: float = 0.0
    between: float = 0.0
    trailing: float = 0.0
    free_space: float = 0.0
    cross_size: float = 0.0
    cross_start: float = 0.0


@dataclass
class FlexPlan:
    """Everything `assert_flex_constraints` needs to restate the equation."""

    is_row: bool
    main_size: float
    cross_size: float
    main_gap: float
    cross_gap: float
    lines: list[FlexLine] = field(default_factory=list)


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------


def layout_flex_container(
    box: Box,
    *,
    content_width: float,
    definite_height: float | None,
    metrics: Counter[str],
    layout_item,
    skip_item,
) -> float:
    """Lay out a flex container's contents. Returns its content height.

    Two callbacks rather than an import, for the reason `layout.table` takes
    a `layout_cell`: `layout.block` imports this module, so this module
    cannot call back into it by name.

    * `layout_item(item_box, content_width) -> border height`. A flex item
      is an ordinary block container once its main size is known, and there
      is no second block layout in this engine.
    * `skip_item(item_box, reason)` books an absolutely positioned child
      that is **not** a flex item (section 4: "the static position of an
      absolutely-positioned child of a flex container is determined such
      that the child is positioned as if it were the sole flex item"), so
      that every box is still counted by exactly one bucket.
    """
    style = style_of(box)
    is_row = _is_row(style, metrics)
    metrics["flex_containers_laid_out"] += 1
    metrics["flex_containers_row" if is_row else "flex_containers_column"] += 1

    main_size = content_width if is_row else definite_height
    cross_definite = definite_height if is_row else content_width
    # A column container with `height: auto` has no definite main size. Its
    # items cannot be flexed against a container size that does not exist,
    # so the free space is zero and every item keeps its base size -- which
    # is what a browser does and what section 9.2 step 2 says by treating
    # the container as infinitely tall.
    main_available = main_size if main_size is not None else math.inf

    main_gap = _gap(
        style.column_gap if is_row else style.row_gap,
        basis=content_width if is_row else definite_height,
        metrics=metrics,
    )
    cross_gap = _gap(
        style.row_gap if is_row else style.column_gap,
        basis=definite_height if is_row else content_width,
        metrics=metrics,
    )

    items = _collect_items(
        box,
        style,
        is_row=is_row,
        content_width=content_width,
        main_available=main_available,
        cross_definite=cross_definite,
        metrics=metrics,
        layout_item=layout_item,
        skip_item=skip_item,
    )

    lines = _collect_lines(
        items, style, main_available, main_gap, metrics=metrics
    )
    plan = FlexPlan(
        is_row=is_row,
        main_size=main_available if main_available != math.inf else 0.0,
        cross_size=0.0,
        main_gap=main_gap,
        cross_gap=cross_gap,
        lines=lines,
    )

    for line in lines:
        _resolve_flexible_lengths(line, main_available, main_gap, metrics)

    # Laying the items out at their final main size, and learning their
    # cross sizes, has to happen between flexing and alignment: a row item's
    # height depends on the width it was just given.
    for line in lines:
        for item in line.items:
            _lay_out_item(
                item,
                is_row=is_row,
                content_width=content_width,
                metrics=metrics,
                layout_item=layout_item,
            )

    _size_lines(lines, cross_definite, cross_gap, metrics)
    if main_available == math.inf:
        # A column container's main size is now known: the line's content.
        plan.main_size = max(
            (_line_used_main(line, main_gap) for line in lines), default=0.0
        )
    for line in lines:
        _justify(line, plan.main_size, main_gap, style, metrics)
        _align(line, style, is_row=is_row, metrics=metrics)

    cross_used = sum(line.cross_size for line in lines) + cross_gap * (
        max(0, len(lines) - 1)
    )
    plan.cross_size = cross_definite if cross_definite is not None else cross_used
    if len(lines) > 1 and (
        style.align_content != "normal"
        or (cross_definite is not None and cross_definite != cross_used)
    ):
        # **Once per container, not once per condition.** `align-content`
        # distributes leftover cross-axis space between lines, so it can
        # only act on a multi-line container that either has leftover space
        # or asked for something other than `normal`; with an auto cross
        # size the lines fill the container by construction and there is
        # nothing to distribute. Counting only the reachable case is what
        # keeps this from being a residual bucket that legitimately
        # contains something -- and counting it once is what keeps it from
        # being the call-counting defect in `docs/measurement-hazards.md`
        # instance twenty, which this task already committed once.
        metrics["flex_align_content_ignored"] += 1

    for line in lines:
        for item in line.items:
            _place(item, is_row=is_row)
            metrics["flex_items_placed"] += 1

    box.flex_plan = plan
    return plan.cross_size if is_row else plan.main_size


# --------------------------------------------------------------------------
# Section 9.2: collecting items and their base sizes
# --------------------------------------------------------------------------


def _is_row(style: ComputedStyle, metrics: Counter[str]) -> bool:
    if style.flex_direction in ("row-reverse", "column-reverse"):
        # Laid out forwards. The reverse directions also reverse the
        # *painting* order of overlapping items, which Phase 4 would have to
        # know about, so a half-implementation here would be visible in two
        # places rather than one.
        metrics["flex_direction_reverse_as_forward"] += 1
    return style.flex_direction in ("row", "row-reverse")


def _gap(value: object, *, basis: float | None, metrics: Counter[str]) -> float:
    """A used gap. `normal` is zero in a flex container -- Box Alignment 3
    section 8.3 -- and a percentage against an indefinite size is zero and
    counted rather than resolved against a guess."""
    if isinstance(value, Keyword):
        return 0.0
    if isinstance(value, Percent):
        if basis is None:
            metrics["flex_percentage_gap_as_zero"] += 1
            return 0.0
        return float(value.value) / 100.0 * basis
    return max(0.0, px_or_zero(value, basis=basis or 0.0, metrics=metrics))


def _collect_items(
    box: Box,
    container_style: ComputedStyle,
    *,
    is_row: bool,
    content_width: float,
    main_available: float,
    cross_definite: float | None,
    metrics: Counter[str],
    layout_item,
    skip_item,
) -> list[FlexItem]:
    items: list[FlexItem] = []
    for child in box.children:
        style = style_of(child)
        if style.position in ("absolute", "fixed"):
            # Not a flex item at all (section 4). Deferred exactly as block
            # layout defers it, so the box partition still holds.
            skip_item(child, "absolute")
            continue
        if style.float_ != "none":
            # "float does not apply to flex items" (section 3). A floated
            # child of a flex container IS an item, and this engine laying
            # it out is more correct than the float deferral it would get in
            # a block container -- counted so the asymmetry is a number.
            metrics["flex_item_float_ignored"] += 1
        if style.order != 0:
            metrics["flex_order_ignored"] += 1
        items.append(
            _make_item(
                child,
                style,
                container_style=container_style,
                is_row=is_row,
                content_width=content_width,
                main_available=main_available,
                cross_definite=cross_definite,
                metrics=metrics,
                layout_item=layout_item,
            )
        )
    return items


def _make_item(
    child: Box,
    style: ComputedStyle,
    *,
    container_style: ComputedStyle,
    is_row: bool,
    content_width: float,
    main_available: float,
    cross_definite: float | None,
    metrics: Counter[str],
    layout_item,
) -> FlexItem:
    """One item, sized but not yet flexed.

    **Every percentage in here resolves against the containing block's
    width**, including the vertical margins and padding of a column
    container's item -- CSS 2.1 sections 8.3 and 8.4 and
    `docs/percentage-resolution.md`. The basis for the *main size* is
    different: it is the container's inner main size, which is the height
    for a column container, and that is the one place the two differ.
    """
    horizontal_inside = (
        px_or_zero(style.border_left_width, basis=content_width, metrics=metrics)
        + px_or_zero(style.border_right_width, basis=content_width, metrics=metrics)
        + px_or_zero(style.padding_left, basis=content_width, metrics=metrics)
        + px_or_zero(style.padding_right, basis=content_width, metrics=metrics)
    )
    vertical_inside = (
        px_or_zero(style.border_top_width, basis=content_width, metrics=metrics)
        + px_or_zero(style.border_bottom_width, basis=content_width, metrics=metrics)
        + px_or_zero(style.padding_top, basis=content_width, metrics=metrics)
        + px_or_zero(style.padding_bottom, basis=content_width, metrics=metrics)
    )
    left = _margin(style.margin_left, content_width, metrics)
    right = _margin(style.margin_right, content_width, metrics)
    top = _margin(style.margin_top, content_width, metrics)
    bottom = _margin(style.margin_bottom, content_width, metrics)

    item = FlexItem(
        box=child,
        style=style,
        main_inside=horizontal_inside if is_row else vertical_inside,
        cross_inside=vertical_inside if is_row else horizontal_inside,
        main_margin_start=left if is_row else top,
        main_margin_end=right if is_row else bottom,
        cross_margin_start=top if is_row else left,
        cross_margin_end=bottom if is_row else right,
        grow=float(style.flex_grow),
        shrink=float(style.flex_shrink),
        base_size=0.0,
        min_main=0.0,
        hypothetical=0.0,
    )
    if is_row:
        _size_row_item(item, main_available, metrics)
    else:
        _size_column_item(
            item,
            alignment=_cross_align(style, container_style),
            content_width=content_width,
            cross_definite=cross_definite,
            metrics=metrics,
            layout_item=layout_item,
        )
    item.hypothetical = max(item.base_size, item.min_main)
    return item


def _margin(value: object, basis: float, metrics: Counter[str]) -> float:
    """A used margin, with `auto` as zero and counted.

    Section 9.6 makes an `auto` margin absorb free space before
    `justify-content` or `align-self` sees any, which is a distribution
    rule this task does not implement. Zero is what section 10.3.2 already
    gives an atomic inline and what `_resolve_width`'s
    `override_content_width` path -- the one a flex item goes through --
    already did, so this is the existing behaviour named rather than a new
    one invented.
    """
    resolved = px(value, basis=basis, metrics=metrics)
    if resolved is None:
        metrics["flex_item_auto_margin_zeroed"] += 1
        return 0.0
    return resolved


def _size_row_item(
    item: FlexItem, main_available: float, metrics: Counter[str]
) -> None:
    """Section 9.2 for a row item: the main axis is the inline axis, so the
    flex base size is a *width* and `layout.intrinsic` answers it directly.
    """
    style = item.style
    basis = style.flex_basis
    definite = _definite_main(basis, main_available)
    if definite is not None:
        metrics["flex_basis_definite"] += 1
        item.base_size = _debox(definite, item, style)
    elif isinstance(basis, Keyword) and basis.name == "content":
        metrics["flex_basis_content_keyword"] += 1
        item.base_size = intrinsic_module.max_content_width(item.box, metrics=metrics)
    else:
        # `flex-basis: auto` -- "when specified on a flex item, the `auto`
        # keyword retrieves the value of the main size property as the used
        # flex-basis", and only if *that* is also `auto` does the item size
        # from its content.
        width = _definite_main(style.width, main_available)
        if width is not None:
            metrics["flex_basis_from_main_size_property"] += 1
            item.base_size = _debox(width, item, style)
        else:
            metrics["flex_basis_from_content"] += 1
            item.base_size = intrinsic_module.max_content_width(
                item.box, metrics=metrics
            )
    item.min_main = _automatic_minimum(item, main_available, metrics)


def _size_column_item(
    item: FlexItem,
    *,
    alignment: str,
    content_width: float,
    cross_definite: float | None,
    metrics: Counter[str],
    layout_item,
) -> None:
    """Section 9.2 for a column item, where the main axis is the block axis.

    The base size is a **height**, and the only way to learn a block box's
    auto height is to lay it out -- so this lays the item out once at its
    cross size, keeps the height that came back, and lets
    `_lay_out_item` reuse that result rather than laying it out twice. That
    asymmetry with the row case is real and not an accident of the code: a
    row item's main size is known before layout and a column item's is a
    result of it.
    """
    style = item.style
    cross_available = content_width - item.cross_inside - (
        item.cross_margin_start + item.cross_margin_end
    )
    declared = px(style.width, basis=content_width, metrics=metrics)
    if declared is not None:
        cross_inner = max(
            0.0, declared - (item.cross_inside if _border_box(style) else 0.0)
        )
    elif alignment == "stretch":
        # A column item with `width: auto` and a stretching alignment fills
        # the container's cross size, which is what block layout would have
        # done anyway.
        cross_inner = max(0.0, cross_available)
    else:
        # Any other alignment shrink-wraps it -- section 9.4 leaves a
        # non-stretched item at its `fit-content` cross size, which is
        # section 10.3.5's formula and therefore `intrinsic.shrink_to_fit`
        # rather than a fourth spelling of it.
        cross_inner = intrinsic_module.shrink_to_fit(
            item.box, max(0.0, cross_available), metrics=metrics
        )
    item.outer_cross = cross_inner + item.cross_inside + (
        item.cross_margin_start + item.cross_margin_end
    )
    border_height = layout_item(item.box, cross_inner)
    natural = max(0.0, border_height - item.main_inside)

    basis = item.style.flex_basis
    definite = _definite_main(basis, cross_definite)
    if definite is not None:
        metrics["flex_basis_definite"] += 1
        item.base_size = _debox(definite, item, style)
    elif isinstance(basis, Keyword) and basis.name == "content":
        metrics["flex_basis_content_keyword"] += 1
        item.base_size = natural
    else:
        height = _definite_main(style.height, cross_definite)
        if height is not None:
            metrics["flex_basis_from_main_size_property"] += 1
            item.base_size = _debox(height, item, style)
        else:
            metrics["flex_basis_from_content"] += 1
            item.base_size = natural
    # The content-based minimum in the block axis is the content's own
    # height, which is what was just measured.
    item.min_main = min(item.base_size, natural)


def _definite_main(value: object, basis: float | None) -> float | None:
    """A main-size value in pixels, or None when it is `auto`, `content`, or
    a percentage of a basis that does not exist."""
    if value is AUTO or isinstance(value, Keyword):
        return None
    if isinstance(value, Percent):
        if basis is None or basis == math.inf:
            return None
        return float(value.value) / 100.0 * basis
    if isinstance(value, Length):
        return None if value.unit != "px" else float(value.value)
    return None


def _border_box(style: ComputedStyle) -> bool:
    return style.box_sizing == "border-box"


def _debox(value: float, item: FlexItem, style: ComputedStyle) -> float:
    """A specified main size as a **content-box** size.

    `box-sizing: border-box` is not a rounding detail here: it decides
    whether `flex-basis: 100px` on a padded item is 100px of content or
    100px including the padding, and getting it backwards moves every item
    in the container by the padding.
    """
    if _border_box(style):
        return max(0.0, value - item.main_inside)
    return max(0.0, value)


def _automatic_minimum(
    item: FlexItem, main_available: float, metrics: Counter[str]
) -> float:
    """Section 4.5's automatic minimum size, for a row item.

    `min-width: auto` on a flex item is **not** zero: it is the smaller of
    the item's specified size suggestion and its content size suggestion --
    the min-content width. Without it, `flex-shrink` squeezes a word past
    its own glyphs and the item's text overflows a box that says it is
    30px wide. `min-width` is not parsed by `cssparse` at all, so `auto` is
    the only case there is.
    """
    if item.style.overflow != "visible":
        # A scroll container's automatic minimum size is zero -- it can be
        # squeezed because its content scrolls. Overflow is read here and
        # nowhere else in this module.
        return 0.0
    content = intrinsic_module.min_content_width(item.box, metrics=metrics)
    specified = _definite_main(item.style.width, main_available)
    if specified is not None:
        return min(content, _debox(specified, item, item.style))
    return content


# --------------------------------------------------------------------------
# Section 9.3: collecting items into lines
# --------------------------------------------------------------------------


def _collect_lines(
    items: list[FlexItem],
    style: ComputedStyle,
    main_available: float,
    main_gap: float,
    *,
    metrics: Counter[str],
) -> list[FlexLine]:
    if style.flex_wrap == "wrap-reverse":
        # Lines stacked in reverse cross order. Wrapping happens; only the
        # stacking direction is dropped.
        metrics["flex_wrap_reverse_as_wrap"] += 1
    single_line = style.flex_wrap == "nowrap"
    if not single_line and main_available == math.inf:
        # Section 9.3 step 1: with an infinite main size every item fits on
        # one line. Not a divergence -- but worth a name, because "wrap was
        # asked for and one line came out" is otherwise indistinguishable
        # from wrapping being unimplemented.
        metrics["flex_wrap_without_definite_main_size"] += 1
        single_line = True
    if single_line or not items:
        line = FlexLine(items=list(items))
        metrics["flex_lines"] += 1
        return [line]

    lines: list[FlexLine] = []
    current: list[FlexItem] = []
    used = 0.0
    for item in items:
        addition = item.outer_hypothetical + (main_gap if current else 0.0)
        if current and used + addition > main_available + EPSILON:
            lines.append(FlexLine(items=current))
            current = [item]
            used = item.outer_hypothetical
            continue
        current.append(item)
        used += addition
    lines.append(FlexLine(items=current))
    metrics["flex_lines"] += len(lines)
    if len(lines) > 1:
        metrics["flex_lines_wrapped"] += len(lines) - 1
    return lines


# --------------------------------------------------------------------------
# Section 9.7: resolving the flexible lengths
# --------------------------------------------------------------------------


def _resolve_flexible_lengths(
    line: FlexLine, main_available: float, main_gap: float, metrics: Counter[str]
) -> None:
    """Section 9.7, as the spec writes it: freeze, distribute, clamp,
    account for the violations, repeat.

    The loop is not decoration. Distributing free space in one pass and
    clamping afterwards is the obvious implementation and it is wrong
    whenever a clamp fires: the pixels that item could not absorb have to
    go back into the pot for the others, and a single pass leaves them
    unspent -- items that do not fill their container, by an amount that
    depends on the content. Each iteration freezes at least one item, so it
    terminates in at most `len(items)` rounds.
    """
    items = line.items
    if not items:
        return
    gaps = main_gap * max(0, len(items) - 1)
    if main_available == math.inf:
        for item in items:
            item.target = item.hypothetical
            item.frozen = True
        line.free_space = 0.0
        return

    initial_free = main_available - gaps - sum(i.outer_hypothetical for i in items)
    growing = initial_free > 0
    if initial_free > EPSILON:
        metrics["flex_free_space_positive"] += 1
    elif initial_free < -EPSILON:
        metrics["flex_free_space_negative"] += 1

    for item in items:
        factor = item.grow if growing else item.shrink
        item.target = item.hypothetical
        if factor == 0 or (growing and item.base_size > item.hypothetical) or (
            not growing and item.base_size < item.hypothetical
        ):
            item.frozen = True
            metrics["flex_items_frozen_inflexible"] += 1
        else:
            item.frozen = False
            item.target = item.base_size

    while True:
        unfrozen = [item for item in items if not item.frozen]
        if not unfrozen:
            break
        used = sum(
            (item.target if not item.frozen else item.target) + item.main_extra
            for item in items
        )
        remaining = main_available - gaps - used
        if abs(remaining) <= EPSILON:
            for item in unfrozen:
                item.frozen = True
            break
        if growing:
            # Distributed from the space remaining *now*, over the unfrozen
            # items' factors -- not from the initial free space over every
            # item's. A frozen item's share has already been spent, and
            # re-dividing the original pot each round double-spends it.
            total = sum(item.grow for item in unfrozen)
            for item in unfrozen:
                item.target += remaining * (item.grow / total)
        else:
            scaled = [(item, item.shrink * item.base_size) for item in unfrozen]
            total = sum(value for _, value in scaled)
            for item, value in scaled:
                share = 0.0 if total == 0 else remaining * (value / total)
                item.target += share

        violation = 0.0
        for item in unfrozen:
            clamped = max(item.target, item.min_main)
            violation += clamped - item.target
            item.target = clamped
        if abs(violation) <= EPSILON:
            for item in unfrozen:
                item.frozen = True
        elif violation > 0:
            for item in unfrozen:
                if item.target <= item.min_main + EPSILON:
                    item.frozen = True
                    metrics["flex_items_clamped_to_min_content"] += 1
        else:  # pragma: no cover - needs a max-size clamp, which is unparsed
            for item in unfrozen:
                item.frozen = True

    for item in items:
        if item.target > item.hypothetical + EPSILON:
            metrics["flex_items_grown"] += 1
        elif item.target < item.hypothetical - EPSILON:
            metrics["flex_items_shrunk"] += 1
    line.free_space = main_available - gaps - sum(i.outer_target for i in items)
    if abs(line.free_space) <= EPSILON:
        metrics["flex_free_space_exhausted"] += 1


# --------------------------------------------------------------------------
# Laying the items out, and the cross axis
# --------------------------------------------------------------------------


def _lay_out_item(
    item: FlexItem, *, is_row: bool, content_width: float, metrics: Counter[str],
    layout_item,
) -> None:
    if is_row:
        border_height = layout_item(item.box, item.target)
        item.outer_cross = (
            border_height + item.cross_margin_start + item.cross_margin_end
        )
    else:
        # Already laid out in `_size_column_item` at its cross size; the
        # main axis is resized in `_place`, where the final target is known.
        pass
    item.baseline = _first_baseline(item.box)


def _size_lines(
    lines: list[FlexLine],
    cross_definite: float | None,
    cross_gap: float,
    metrics: Counter[str],
) -> None:
    """Section 9.4: each line's cross size is the largest outer cross size
    on it, except that a **single-line** container with a definite cross
    size takes that instead -- which is what makes `align-items: stretch`
    fill a fixed-height container rather than the tallest item."""
    for index, line in enumerate(lines):
        natural = max((item.outer_cross for item in line.items), default=0.0)
        if len(lines) == 1 and cross_definite is not None:
            line.cross_size = cross_definite
        else:
            line.cross_size = natural
    offset = 0.0
    for line in lines:
        line.cross_start = offset
        offset += line.cross_size + cross_gap
    if len(lines) > 1 and cross_gap:
        metrics["flex_cross_gap_applied"] += len(lines) - 1


def _justify(
    line: FlexLine,
    main_size: float,
    main_gap: float,
    style: ComputedStyle,
    metrics: Counter[str],
) -> None:
    """Section 9.5. Free space is spent here and nowhere else.

    Negative free space is not distributed at all: every `justify-content`
    value falls back to packing at the main-start edge when the items
    overflow, which is what a browser does and what keeps the mechanical
    check's equation exact in both directions.
    """
    count = len(line.items)
    gaps = main_gap * max(0, count - 1)
    used = sum(item.outer_target for item in line.items) + gaps
    free = main_size - used
    line.free_space = free
    if main_gap and count > 1:
        metrics["flex_main_gap_applied"] += count - 1
    keyword = style.justify_content
    if keyword == "normal":
        keyword = _JUSTIFY_NORMAL
    if free <= EPSILON or count == 0:
        # Nothing to distribute -- but the items still have to be *placed*,
        # and an early return here left every item at offset zero and every
        # one of them stacked on the container's main-start edge. Caught by
        # the mechanical check on the first real page it ran on, which is
        # what that check is for: the render was a plausible page and the
        # equation was not.
        line.leading = line.between = line.trailing = 0.0
    elif keyword in _MAIN_END_ALIASES:
        line.leading, line.between, line.trailing = free, 0.0, 0.0
    elif keyword == "center":
        line.leading = line.trailing = free / 2.0
        line.between = 0.0
    elif keyword == "space-between":
        if count == 1:
            # "If the leftover free-space is ... there is only a single flex
            # item ... this value is identical to flex-start." The one place
            # a 193-of-233 corpus of single-item containers would hide a
            # wrong implementation completely.
            line.leading = line.between = 0.0
            line.trailing = free
        else:
            line.between = free / (count - 1)
            line.leading = line.trailing = 0.0
    elif keyword == "space-around":
        line.between = free / count
        line.leading = line.trailing = line.between / 2.0
    elif keyword == "space-evenly":
        line.between = free / (count + 1)
        line.leading = line.trailing = line.between
    else:
        # `flex-start`, `start`, `left` -- and `stretch`, which behaves as
        # `flex-start` on the *main* axis of a flex container. Spelled as a
        # membership test with a fallthrough rather than as a bare `else`,
        # so that a keyword added to the cascade's set and forgotten here
        # lands on flex-start deliberately rather than by omission.
        assert keyword in _MAIN_START_ALIASES or keyword == "stretch", keyword
        line.leading = line.between = 0.0
        line.trailing = free

    offset = line.leading
    for index, item in enumerate(line.items):
        if index:
            offset += main_gap + line.between
        item.main_offset = offset
        offset += item.outer_target


def _align(
    line: FlexLine, style: ComputedStyle, *, is_row: bool, metrics: Counter[str]
) -> None:
    """Sections 9.4 and 9.6's cross-axis alignment, per item."""
    baseline_items = [
        item
        for item in line.items
        if _cross_align(item.style, style) == "baseline"
    ]
    max_ascent = 0.0
    for item in baseline_items:
        if item.baseline is None:
            metrics["flex_items_baseline_synthesized"] += 1
        max_ascent = max(max_ascent, _item_ascent(item))

    for item in line.items:
        alignment = _cross_align(item.style, style)
        free = line.cross_size - item.outer_cross
        if alignment == "stretch":
            if _cross_size_is_auto(item, is_row) and free > 0:
                item.outer_cross = line.cross_size
                metrics["flex_items_stretched"] += 1
            item.cross_offset = line.cross_start
        elif alignment == "baseline":
            if not is_row:
                # Baseline alignment in a column container aligns items by
                # their *inline*-axis baselines, which needs a baseline in
                # the cross axis this engine does not compute. Section 8.3
                # falls back to `flex-start`, which is what happens here.
                metrics["flex_baseline_in_column_as_start"] += 1
                item.cross_offset = line.cross_start
            else:
                metrics["flex_items_aligned_baseline"] += 1
                item.cross_offset = line.cross_start + (
                    max_ascent - _item_ascent(item)
                )
        elif alignment in _CROSS_END_ALIASES:
            item.cross_offset = line.cross_start + free
        elif alignment == "center":
            item.cross_offset = line.cross_start + free / 2.0
        else:
            assert alignment in _CROSS_START_ALIASES, alignment
            item.cross_offset = line.cross_start


def _cross_align(item_style: ComputedStyle, container_style: ComputedStyle) -> str:
    """`align-self`, resolved. `auto` means "whatever the container's
    `align-items` says", and `normal` behaves as `stretch` in a flex
    container -- two indirections that both have to be followed before any
    comparison, which is why no caller reads the property directly."""
    value = item_style.align_self
    if value == "auto":
        value = container_style.align_items
    if value == "normal":
        return _ALIGN_NORMAL
    return value


def _cross_size_is_auto(item: FlexItem, is_row: bool) -> bool:
    """Only an item whose cross size is `auto` stretches. A definite one
    keeps what it was given -- otherwise `align-items: stretch`, which is
    the initial value, would silently override every declared height in
    every flex container on the page."""
    value = item.style.height if is_row else item.style.width
    return value is AUTO


def _item_ascent(item: FlexItem) -> float:
    """The distance from an item's outer cross-start edge to its first
    baseline.

    Section 8.5: an item with no baseline of its own gets one synthesized
    from its border box. **No counter here**: this is called twice per item,
    once for the line's maximum and once for the item's own offset, and a
    counter inside it read 4 on a two-item fixture -- a count of calls
    wearing the name of a count of items. It is counted in `_align`, where
    each item is visited once.
    """
    if item.baseline is not None:
        return item.cross_margin_start + item.baseline
    return item.outer_cross


def _first_baseline(box: Box) -> float | None:
    """The **first** line box baseline inside `box`, from its top border
    edge.

    Deliberately not `layout.block._last_line_baseline`, and not a
    duplicate of it: CSS 2.1 section 10.8.1 asks for an `inline-block`'s
    *last* line box and Flexbox 1 section 8.5 asks a flex item for its
    *first*, so the two answer different questions and would differ on any
    box with more than one line. The minimum is taken rather than the first
    found in tree order for the same reason `_last_line_baseline` takes the
    maximum: with nothing out of flow the two agree, and the extremum is
    the one that stays right when they stop agreeing.
    """
    geometry = box.geometry
    if geometry is None:
        return None
    content_offset = geometry.content.y - geometry.border.y
    best: float | None = None
    if box.line_boxes:
        line = box.line_boxes[0]
        best = content_offset + line.y + line.baseline
    for child in box.children:
        child_geometry = child.geometry
        if child_geometry is None:
            continue
        inner = _first_baseline(child)
        if inner is None:
            continue
        candidate = content_offset + child_geometry.border.y + inner
        best = candidate if best is None else min(best, candidate)
    return best


def _line_used_main(line: FlexLine, main_gap: float) -> float:
    return sum(item.outer_target for item in line.items) + main_gap * max(
        0, len(line.items) - 1
    )


# --------------------------------------------------------------------------
# Writing the geometry
# --------------------------------------------------------------------------


def _place(item: FlexItem, *, is_row: bool) -> None:
    """Move a laid-out item to its flex position, and resize the axes the
    flex algorithm decided rather than block layout.

    A row item was laid out at its final main size already, so only the
    cross axis can need resizing (`align-items: stretch`). A column item was
    laid out before its main size was known, so its **main** axis is
    resized here -- growing the border box downward and leaving the content
    where it is, which is what `vertical-align: top` does in a table cell
    and what a stretched flex item does too.
    """
    geometry = item.box.geometry
    if geometry is None:
        return
    if is_row:
        target_border_cross = item.outer_cross - (
            item.cross_margin_start + item.cross_margin_end
        )
        _resize(geometry, height=target_border_cross)
        _move(
            geometry,
            dx=item.main_offset + item.main_margin_start - geometry.border.x,
            dy=item.cross_offset + item.cross_margin_start - geometry.border.y,
        )
    else:
        _resize(geometry, height=item.target + item.main_inside)
        _move(
            geometry,
            dx=item.cross_offset + item.cross_margin_start - geometry.border.x,
            dy=item.main_offset + item.main_margin_start - geometry.border.y,
        )


def _resize(geometry, *, height: float) -> None:
    """Set a laid-out box's **border-box** height, growing or shrinking the
    content box by the same amount and leaving the content where it is."""
    delta = height - geometry.border.height
    if abs(delta) <= EPSILON:
        return
    geometry.border = replace(geometry.border, height=height)
    geometry.margin = replace(
        geometry.margin, height=geometry.margin.height + delta
    )
    geometry.padding = replace(
        geometry.padding, height=geometry.padding.height + delta
    )
    geometry.content = replace(
        geometry.content, height=max(0.0, geometry.content.height + delta)
    )


def _move(geometry, *, dx: float, dy: float) -> None:
    """Move all four rectangles. The item's own children do not move with
    it: they are relative to its content box, and `layout.block._absolutize`
    composes the chain once at the end."""
    if abs(dx) <= EPSILON and abs(dy) <= EPSILON:
        return
    for name in ("content", "padding", "border", "margin"):
        rect = getattr(geometry, name)
        setattr(geometry, name, replace(rect, x=rect.x + dx, y=rect.y + dy))


# --------------------------------------------------------------------------
# The mechanical check
# --------------------------------------------------------------------------


def assert_flex_constraints(box: Box, plan: FlexPlan) -> None:
    """Free space distributed == free space available, read off the
    rectangles.

    For every line: the items' outer main sizes, plus one gap between each
    adjacent pair, plus everything `justify-content` spent, must exactly
    fill the container's content box along the main axis -- and each item
    must start where the sum of everything before it says it does.

    Read from the **absolute** coordinates after `_absolutize`, for the
    reason `layout.table`'s tiling is: during layout every rectangle is
    relative to its own parent, and a check that composed the offsets
    itself would agree with a wrong composition.
    """
    geometry = box.geometry
    if geometry is None:
        return
    content = geometry.content
    origin = content.x if plan.is_row else content.y
    size = content.width if plan.is_row else content.height
    where = box.path or f"<{box.origin} {box.display}>"

    for index, line in enumerate(plan.lines):
        if not line.items:
            continue
        spent = line.leading + line.between * (len(line.items) - 1) + line.trailing
        available = size - sum(
            _outer_main(item, plan.is_row) for item in line.items
        ) - plan.main_gap * (len(line.items) - 1)
        if available > EPSILON:
            _close(
                spent,
                available,
                f"{where} line {index}: justify-content spent {spent} of "
                f"{available} available free space (Flexbox 1 section 9.5)",
            )

        cursor = origin + line.leading
        for position, item in enumerate(line.items):
            if position:
                cursor += plan.main_gap + line.between
            rect = item.box.geometry.margin if item.box.geometry else None
            if rect is None:
                continue
            start = rect.x if plan.is_row else rect.y
            _close(
                start,
                cursor,
                f"{where} line {index} item {position}: main-axis start "
                f"{start} != {cursor}",
            )
            cursor += _outer_main(item, plan.is_row)


def _outer_main(item: FlexItem, is_row: bool) -> float:
    geometry = item.box.geometry
    if geometry is None:
        return item.outer_target
    return geometry.margin.width if is_row else geometry.margin.height


def _close(actual: float, expected: float, message: str) -> None:
    assert math.isclose(actual, expected, rel_tol=0.0, abs_tol=1e-5), (
        f"{message} (got {actual}, expected {expected})"
    )
