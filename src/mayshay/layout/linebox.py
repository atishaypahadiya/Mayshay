"""Line boxes, inline fragments and baseline alignment -- Phase 3 Task D2.

Task D1 delivered `measure()`, CSS Text 3's Phase I white-space
transformation and the two intrinsic sizes. This module is what sits on
them: it takes one inline formatting context, decides where the lines
break, builds a line box for each, fragments every inline box that crosses
a break, aligns everything vertically, and hands the block back a height.

## Where the lines break

`layout.linebreak` -- UAX #14, because that is what CSS Text 3 defers to.
The one thing worth repeating here is that a break opportunity is a
property of a **pair of characters in the whole formatting context**, not
of a text node: `<span>a</span><span>b</span>` is one word, and
`<span>a </span><span>b</span>` is two. So the opportunities are computed
once over the concatenated text of the context, exactly as D1's collapser
already computes collapsing over it.

## Lines are full width

This engine lays out no floats, so nothing shortens a line. Implementing
float avoidance with nothing to avoid is the `clear` trap Task C caught: it
would make this engine disagree with a browser on every case it can reach
in order to agree on one it cannot. `layout_float_skipped` is where the
divergence is a number.

## Baseline alignment, and what its tests are worth

CSS 2.1 sections 10.8 and 10.8.1. **The corpus validates almost none of
this**: `vertical-align` is `baseline` on 7,533 element boxes and that is
the *initial* value, so the number counts boxes that never set the
property. `middle` is 43, `top` 30, `text-top` and `text-bottom` 1 each,
and `sub`, `super`, `bottom`, `<percentage>` and `<length>` are all zero.
Every test of this code is synthetic and every row is in
`docs/synthetic-only-coverage.md`.

Three of the rules are **not** in CSS 2.1 at all -- the spec says "the
exact offset is user-agent defined" for `sub` and `super`, and it does not
say which x-height `middle` uses. Those were measured against Chrome 151 at
`font-size: 2048px`, the size at which every `hhea` metric of this font is
a whole number and Chrome's own integer rounding cannot hide the rule:

    sub          lower by  font-size / 5 + 1
    super        raise by  font-size / 3 + 1
    middle       the box's midpoint at the parent's baseline minus half
                 the parent's x-height

`sub` and `super` reproduce Chrome exactly at 16px too (4.1875 and 6.3281,
which are `16/5+1` and `16/3+1` quantised to Chrome's 1/64 LayoutUnit).
`middle` reproduces its *shape* exactly and its *value* to within half the
difference between two x-heights: Chrome reports `1ex` as 8.2969px at 16px
(1062 font units) where this font's `OS/2.sxHeight` is 8.453125px (1082
units), and `docs/fonts.md` takes the font's own metric because CSS Values
4 section 5.1.2 says to. That is a 0.078px disagreement per middle-aligned
box at 16px, and it is recorded rather than tuned away.

## The mechanical checks

Three, run on every line box rather than only under test, in the shape of
Task C's constraint assertion and Task D1's character conservation:

1. **A line box's contents account for its extent.** The height is
   recomputed from the aligned boxes' own ascents and descents and must
   equal the height that was stored, and the baseline must equal the
   topmost extent. A box aligned and then forgotten in the extent, or an
   extent taken over the wrong set, fails here.
2. **A line box's width is the sum of what is on it.** The advances placed
   along the line must add up to the used width, so a fragment given the
   wrong x, or a trailing space trimmed twice, fails.
3. **Every aligned box was aligned by exactly one named `vertical-align`
   rule**, and the per-rule counters sum to the boxes aligned. A ninth
   keyword added to `cssparse.values` and forgotten here fails at import,
   not on the first page that uses it -- `_ALIGNMENT_RULES` is asserted
   against `values` the same way `WHITE_SPACE_BEHAVIOUR` is.
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass, field, replace

from mayshay.cssparse.cascade import ComputedStyle
from mayshay.cssparse.values import (
    VERTICAL_ALIGN_KEYWORDS,
    Length,
    Percent,
)
from mayshay.layout import linebreak, text as text_module
from mayshay.layout.boxtree import ATOMIC_INLINE_DISPLAYS, Box
from mayshay.layout.geometry import EPSILON, BoxGeometry, Edges, Rect
from mayshay.layout.text import LineMetrics, line_metrics, measure
from mayshay.layout.used import px_or_zero, style_of, text_style_of

#: Tag names that generate a forced line break. `<br>` computes to
#: `display: inline` with no children, so nothing structural distinguishes
#: it from `<span></span>`; the tag name is the only signal there is.
FORCED_BREAK_TAGS: frozenset[str] = frozenset({"br"})

#: Replaced elements. This engine loads no images and has no intrinsic
#: sizes, so each one is an empty inline box: it contributes its own
#: `line-height` to the line and no width at all. Counted rather than
#: silently zero -- Chrome gives a loaded `<img>` real dimensions, so every
#: one of these is a divergence whose size is unknown to us.
REPLACED_TAGS: frozenset[str] = frozenset(
    {"img", "input", "textarea", "select", "button", "iframe", "canvas",
     "video", "audio", "embed", "object", "svg"}
)

# Escapes, never literals, per CLAUDE.md: a tab and a run of spaces are
# indistinguishable in a terminal, and so are U+FFFC and a missing glyph.
_SPACE = "\u0020"
_TAB = "\u0009"
_LF = "\u000a"
_OBJECT_REPLACEMENT = "\ufffc"

#: The white-space characters that can be trimmed or hung at a line's end.
#: Deliberately not `str.isspace()` and deliberately not including U+000A:
#: a preserved segment break is a break, not a trailing space.
_TRAILING_WHITE_SPACE = frozenset({_SPACE, _TAB})


# --------------------------------------------------------------------------
# The vertical-align rule table
# --------------------------------------------------------------------------
#
# One entry per keyword, so the drift assert below can compare it against
# the parser's own list. `<length>` and `<percentage>` are not keywords and
# are counted under their own names.

_ALIGNMENT_RULES: tuple[str, ...] = (
    "baseline",
    "sub",
    "super",
    "text-top",
    "text-bottom",
    "middle",
    "top",
    "bottom",
)

# MECHANICAL CHECK, the same shape as `layout.text`'s WHITE_SPACE_BEHAVIOUR
# assert and `cascade`'s LONGHANDS drift assert. A ninth `vertical-align`
# keyword added to the parser and forgotten here would otherwise fall
# through `_shift_of` to the `baseline` default and align *plausibly*, which
# is the worst possible failure for a property whose whole failure mode is
# "text is a few pixels off and the page looks fine". Import time, every
# run, no test needed.
assert set(_ALIGNMENT_RULES) == set(VERTICAL_ALIGN_KEYWORDS), (
    "layout.linebox and cssparse.values disagree about the `vertical-align` "
    f"keywords: {set(_ALIGNMENT_RULES) ^ set(VERTICAL_ALIGN_KEYWORDS)}"
)

_ALIGNMENT_COUNTERS: tuple[str, ...] = tuple(
    "vertical_align_applied_" + name.replace("-", "_") for name in _ALIGNMENT_RULES
) + (
    "vertical_align_applied_length",
    "vertical_align_applied_percentage",
)

COUNTER_NAMES: tuple[str, ...] = (
    "line_boxes",
    "line_boxes_empty_zero_height",
    "line_strut_suppressed_no_direct_text",
    "line_ifc_contexts_laid_out",
    "line_breaks_soft",
    "line_breaks_forced_segment",
    "line_breaks_forced_br",
    "line_overflow_unbreakable",
    "line_fragments",
    "line_fragments_text",
    "line_fragments_inline_box",
    "line_fragments_atomic",
    "line_inline_boxes_fragmented",
    "line_empty_inline_boxes",
    "line_replaced_zero_size",
    "line_break_opportunities_masked_nowrap",
    "line_break_spaces_extra_opportunity",
    "text_line_trailing_space_trimmed",
    "text_line_trailing_space_hung",
    "text_line_leading_space_trimmed",
    "text_align_start",
    "text_align_left",
    "text_align_right",
    "text_align_center",
    "text_align_justify_as_start",
    "vertical_align_boxes_aligned",
    "vertical_align_percent_resolved_in_layout",
    "vertical_align_top_bottom_extended_line",
    "vertical_align_atomic_baseline_from_last_line",
    "vertical_align_atomic_baseline_from_margin_edge",
    "line_height_unit_unresolved",
) + _ALIGNMENT_COUNTERS + linebreak.COUNTER_NAMES


# --------------------------------------------------------------------------
# Output shapes
# --------------------------------------------------------------------------


@dataclass
class InlineFragment:
    """One inline box's geometry on one line box.

    `index` is the fragment number **within the DOM node**, counted across
    every `Box` that node produced -- Task B splits an inline around a
    block-level child into several `Box`es and each of those can wrap again
    here, so the number a comparison harness needs is not the index within
    any one of them. Chrome answers `getContentQuads` with one quad per
    fragment in document order, which is what this counts.

    `text` is the slice of the box's collapsed text that landed on this
    line, or None for an element box. It exists so a fragment can be
    checked against what it claims to contain rather than only against its
    width.
    """

    box: Box
    index: int
    line: int
    geometry: BoxGeometry
    text: str | None = None

    def identity(self) -> tuple[int, str, int] | None:
        """`(ordinal, path, fragment)` -- the Phase 3 comparison contract's
        key, with the fragment index filled in for real."""
        if not self.box.is_comparable:
            return None
        if self.box.ordinal is None or self.box.path is None:
            return None
        return (self.box.ordinal, self.box.path, self.index)


@dataclass
class LineBox:
    """One line box: its extent, its baseline, and what is on it.

    Coordinates are relative to the containing block's content origin while
    layout runs, and absolute afterwards, exactly like `BoxGeometry` -- the
    same `_absolutize` pass moves both.

    `top_extent` and `bottom_extent` are the aligned boxes' extremes
    relative to the **root baseline**, kept rather than discarded because
    they are what the height and the baseline were computed from, and the
    mechanical check recomputes them from the fragments to see whether they
    still agree.
    """

    index: int
    x: float
    y: float
    width: float
    available_width: float
    height: float
    baseline: float
    top_extent: float
    bottom_extent: float
    fragments: list[InlineFragment] = field(default_factory=list)
    #: `(offset_from_root_baseline, ascent, descent)` for every box aligned
    #: on this line, including the strut. The check reads this.
    aligned: list[tuple[float, float, float]] = field(default_factory=list)
    #: Advances placed along the line, in order, for the width check.
    advances: list[float] = field(default_factory=list)


# --------------------------------------------------------------------------
# The item stream
# --------------------------------------------------------------------------

_TEXT = "text"
_ATOMIC = "atomic"
_BREAK = "break"
_EMPTY = "empty"


@dataclass
class _Item:
    """One leaf of the inline formatting context, in document order."""

    kind: str
    box: Box
    style: ComputedStyle
    ancestors: tuple[Box, ...]
    text: str = ""
    start: int = 0
    #: The ancestor inline boxes that *begin* at this item and those that
    #: *end* at it. Precomputed once, and read by both the unit measurement
    #: and the fragment walk, so the width a line was filled to and the
    #: width its fragments were laid out to cannot disagree -- which is
    #: exactly what the line-box width check would otherwise catch after the
    #: fact rather than prevent.
    opens: tuple[Box, ...] = ()
    closes: tuple[Box, ...] = ()

    @property
    def length(self) -> int:
        """How many characters this item contributes to the context's
        concatenated string. An empty inline box contributes none, which is
        why it cannot create a break opportunity beside itself."""
        if self.kind == _TEXT:
            return len(self.text)
        if self.kind in (_ATOMIC, _BREAK):
            return 1
        return 0


@dataclass
class _Piece:
    """A slice of one item that fits on one line."""

    item: _Item
    start: int
    end: int
    width: float = 0.0

    @property
    def text(self) -> str:
        return self.item.text[self.start:self.end]

    @property
    def opens_here(self) -> tuple[Box, ...]:
        """The inline boxes whose left edge belongs to this piece.

        An inline box split across lines puts its left margin, border and
        padding on its first fragment only, so the edge belongs to the
        piece that starts its first item and to no other.
        """
        return self.item.opens if self.start == 0 else ()

    @property
    def closes_here(self) -> tuple[Box, ...]:
        return self.item.closes if self.end == self.item.length else ()

    @property
    def lead_width(self) -> float:
        return sum(_leading_edges(style_of(box)) for box in self.opens_here)

    @property
    def tail_width(self) -> float:
        return sum(_trailing_edges(style_of(box)) for box in self.closes_here)


@dataclass
class _Unit:
    """The content between two consecutive break opportunities.

    A unit is what a greedy line breaker moves as a whole. It carries its
    trailing white space separately because that white space is *inside*
    the line when the unit is followed by another and *outside* it when the
    unit ends the line -- CSS Text 3 Phase II, which is exactly the part D1
    left because it needs a line box.
    """

    pieces: list[_Piece] = field(default_factory=list)
    content_width: float = 0.0
    trailing_width: float = 0.0
    trailing_chars: int = 0
    trailing_hangs: bool = False
    forced_break: bool = False


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------


def layout_inline_content(
    root: Box,
    *,
    available_width: float,
    metrics: Counter[str],
    layout_atomic,
) -> tuple[float, list[LineBox]]:
    """Lay out the inline formatting context established by `root`.

    Returns `(content_height, line_boxes)`. The height is the sum of the
    line box heights, which is CSS 2.1 section 10.6.3's `height: auto` for
    a block container with inline content -- Task C's 687 deferrals.

    `layout_atomic(box, available)` is a callback into block layout, passed
    in rather than imported: an atomic inline is a block container on the
    inside, so sizing one means running block layout, and `layout.block`
    already imports this module. One parameter is cheaper than a cycle and
    it names the dependency where a reader will see it.
    """
    metrics["line_ifc_contexts_laid_out"] += 1
    items = _flatten(root, metrics)
    if not items:
        return 0.0, []

    concatenated = _concatenate(items)
    boundaries = _boundaries(items, concatenated, metrics)
    units = _segment(items, boundaries, metrics)
    _measure_units(units, metrics)
    lines = _fill(units, available_width, metrics)

    root_style = style_of(root)
    y = 0.0
    out: list[LineBox] = []
    fragment_counts: dict[int, int] = {}
    for index, (line_units, used_width) in enumerate(lines):
        line = _place_line(
            line_units,
            index=index,
            used_width=used_width,
            y=y,
            available_width=available_width,
            root_style=root_style,
            metrics=metrics,
            layout_atomic=layout_atomic,
            fragment_counts=fragment_counts,
        )
        assert_line_box(line)
        out.append(line)
        y += line.height
    metrics["line_boxes"] += len(out)
    return y, out


# --------------------------------------------------------------------------
# Flattening
# --------------------------------------------------------------------------


def _flatten(root: Box, metrics: Counter[str]) -> list[_Item]:
    items: list[_Item] = []

    def walk(box: Box, ancestors: tuple[Box, ...]) -> int:
        produced = 0
        for child in box.children:
            if child.origin == "text":
                collapsed = child.text
                if collapsed is None:
                    # Reached only on a tree that never went through
                    # `layout.inline.process_text` -- a hand-built box in a
                    # unit test. A real page cannot take this path and the
                    # counter in `intrinsic` already says so; here the
                    # source text is used unchanged rather than collapsed a
                    # second time with a second idea of the rules.
                    collapsed = child.node.data if child.node is not None else ""
                if not collapsed:
                    continue
                items.append(
                    _Item(_TEXT, child, text_style_of(child), ancestors, collapsed)
                )
                produced += 1
            elif child.display in ATOMIC_INLINE_DISPLAYS:
                items.append(_Item(_ATOMIC, child, style_of(child), ancestors))
                produced += 1
            elif child.is_inline_level:
                tag = _tag_of(child)
                if tag in FORCED_BREAK_TAGS:
                    items.append(_Item(_BREAK, child, style_of(child), ancestors))
                    produced += 1
                    continue
                if tag in REPLACED_TAGS:
                    metrics["line_replaced_zero_size"] += 1
                inner = walk(child, ancestors + (child,))
                if inner == 0:
                    # CSS 2.1 section 10.8: an empty inline element still
                    # generates an inline box, and that box still has a
                    # line-height, so it still influences the line box. It
                    # contributes no character, so it creates no break
                    # opportunity beside itself either.
                    metrics["line_empty_inline_boxes"] += 1
                    items.append(
                        _Item(_EMPTY, child, style_of(child), ancestors + (child,))
                    )
                produced += inner or 1
            else:
                # Block-level inside an inline formatting context. Task B's
                # anonymous-box and inline-splitting rules mean this should
                # not happen; it is skipped rather than asserted, because a
                # wrong tree should still lay out, and Task C already counts
                # it in `widths_deferred_other`.
                continue
        return produced

    walk(root, ())
    offset = 0
    for item in items:
        item.start = offset
        offset += item.length
    _assign_edges(items)
    return items


def _assign_edges(items: list[_Item]) -> None:
    """Say which inline box begins and which ends at each item.

    Document order, first occurrence and last, over the whole formatting
    context rather than over one line -- because that is what CSS 2.1
    section 9.2.1.1's split rule is about: the box's edges are drawn where
    the box begins and ends, not where each line does.
    """
    first: dict[int, _Item] = {}
    last: dict[int, _Item] = {}
    boxes: dict[int, Box] = {}
    for item in items:
        for box in item.ancestors:
            boxes[id(box)] = box
            first.setdefault(id(box), item)
            last[id(box)] = item
    opens: dict[int, list[Box]] = {}
    closes: dict[int, list[Box]] = {}
    for key, box in boxes.items():
        opens.setdefault(id(first[key]), []).append(box)
        closes.setdefault(id(last[key]), []).append(box)
    for item in items:
        item.opens = tuple(opens.get(id(item), ()))
        # Closed innermost first, so the walk pops the stack in order.
        item.closes = tuple(reversed(closes.get(id(item), ())))


def _tag_of(box: Box) -> str | None:
    if box.origin != "element" or box.node is None:
        return None
    return getattr(box.node, "tag_name", None)


def _concatenate(items: list[_Item]) -> str:
    """The context's text, with one placeholder per non-text item.

    An atomic inline is U+FFFC OBJECT REPLACEMENT CHARACTER -- line-break
    class CB, which rule LB20 breaks on both sides of. That is the whole of
    `docs/measurement-hazards.md` instance fourteen, and it is the same
    encoding D1's collapser already uses, so the two passes see the same
    string.

    A `<br>` is U+000A, because a forced break is what it is.
    """
    parts: list[str] = []
    for item in items:
        if item.kind == _TEXT:
            parts.append(item.text)
        elif item.kind == _ATOMIC:
            parts.append(_OBJECT_REPLACEMENT)
        elif item.kind == _BREAK:
            parts.append(_LF)
    return "".join(parts)


def _boundaries(
    items: list[_Item], concatenated: str, metrics: Counter[str]
) -> list[bool]:
    """Where a line may break, as a flag per character of the context.

    Three things happen on top of UAX #14, each counted:

    * a break opportunity is **masked** when either side of it is inside a
      non-wrapping `white-space` value, which is what `nowrap` means;
    * a break is **forced** after every segment break, so the character
      after a preserved newline always starts a line;
    * `break-spaces` adds an opportunity after **every** preserved space,
      which is the only thing separating it from `pre-wrap`.
    """
    flags = linebreak.break_opportunities(concatenated, metrics=metrics)
    owner = _owners(items, len(concatenated))
    for index in range(1, len(flags)):
        if not flags[index]:
            continue
        before = owner[index - 1]
        after = owner[index]
        if _wraps(before) and _wraps(after):
            continue
        flags[index] = False
        metrics["line_break_opportunities_masked_nowrap"] += 1
    for index, char in enumerate(concatenated):
        item = owner[index]
        if char == _LF and index + 1 < len(flags):
            flags[index + 1] = True
        elif (
            char in _TRAILING_WHITE_SPACE
            and item is not None
            and item.style.white_space == "break-spaces"
            and index + 1 < len(flags)
            and not flags[index + 1]
        ):
            flags[index + 1] = True
            metrics["line_break_spaces_extra_opportunity"] += 1
    return flags


def _owners(items: list[_Item], length: int) -> list[_Item | None]:
    owner: list[_Item | None] = [None] * length
    for item in items:
        for offset in range(item.length):
            owner[item.start + offset] = item
    return owner


def _wraps(item: _Item | None) -> bool:
    if item is None:
        return True
    return text_module.behaviour_of(item.style.white_space).wraps


# --------------------------------------------------------------------------
# Segmentation and measurement
# --------------------------------------------------------------------------


def _segment(
    items: list[_Item], boundaries: list[bool], metrics: Counter[str]
) -> list[_Unit]:
    units: list[_Unit] = []
    current = _Unit()

    def flush() -> None:
        nonlocal current
        if current.pieces:
            units.append(current)
            current = _Unit()

    for item in items:
        length = item.length
        if length == 0:
            current.pieces.append(_Piece(item, 0, 0))
            continue
        local = 0
        for offset in range(length):
            if not boundaries[item.start + offset]:
                continue
            if offset > local:
                current.pieces.append(_Piece(item, local, offset))
                local = offset
            flush()
        if local < length:
            current.pieces.append(_Piece(item, local, length))
        if item.kind == _BREAK or (
            item.kind == _TEXT and _LF in item.text[local:length]
        ):
            current.forced_break = True
    flush()
    for unit in units:
        for piece in unit.pieces:
            if piece.item.kind == _BREAK or (
                piece.item.kind == _TEXT and _LF in piece.text
            ):
                unit.forced_break = True
    return units


def _measure_units(units: list[_Unit], metrics: Counter[str]) -> None:
    """Give every unit its content width and its trailing white space.

    The trailing run is looked for on the **last text piece** of the unit,
    skipping the zero-width pieces (`<br>`, an empty inline box) that can
    sit after it. Skipping them matters: `word <br>` must trim the space,
    and `word <inline-block>` must not, because there the space is inside
    the line rather than at its end.

    `break-spaces` is the one value where a trailing space is neither
    trimmed nor hung -- CSS Text 3 gives it a break opportunity of its own
    instead -- so its units report a trailing width of zero and keep the
    space inside `content_width`. That is the whole difference between it
    and `pre-wrap`, which D1 recorded as identical in Phase I precisely so
    that this line would be the one that separates them.
    """
    for unit in units:
        for piece in unit.pieces:
            piece.width = _piece_width(piece, metrics)
        total = sum(
            piece.width + piece.lead_width + piece.tail_width
            for piece in unit.pieces
        )
        piece = _last_trimmable_text_piece(unit.pieces)
        trailing = 0.0
        chars = 0
        hangs = False
        if piece is not None:
            tail = _trailing_white_space(piece)
            if tail:
                trailing = measure(tail, piece.item.style, metrics=metrics)
                chars = len(tail)
                hangs = not text_module.behaviour_of(
                    piece.item.style.white_space
                ).collapse_spaces
        unit.content_width = total - trailing
        unit.trailing_width = trailing
        unit.trailing_chars = chars
        unit.trailing_hangs = hangs


def _trailing_white_space(piece: _Piece) -> str:
    """The run of trimmable white space at the end of this piece, or `""`."""
    if piece.item.style.white_space == "break-spaces":
        return ""
    body = piece.text
    index = len(body)
    while index > 0 and body[index - 1] in _TRAILING_WHITE_SPACE:
        index -= 1
    return body[index:]


def _last_trimmable_text_piece(pieces: list[_Piece]) -> _Piece | None:
    """The last text piece, looking past the zero-width items after it.

    A `<br>` and an empty inline box take no space, so white space in front
    of one is still at the end of the line. An atomic inline does take
    space, so white space in front of one is not -- which is why this stops
    rather than skipping every non-text piece.
    """
    for piece in reversed(pieces):
        kind = piece.item.kind
        if kind in (_BREAK, _EMPTY):
            continue
        if kind == _TEXT:
            return piece
        return None
    return None


def _piece_width(piece: _Piece, metrics: Counter[str]) -> float:
    item = piece.item
    if item.kind == _TEXT:
        return measure(piece.text, item.style, metrics=metrics)
    return 0.0  # atomic widths are added at placement time; breaks have none


# --------------------------------------------------------------------------
# Greedy line filling
# --------------------------------------------------------------------------


def _fill(
    units: list[_Unit], available_width: float, metrics: Counter[str]
) -> list[tuple[list[_Unit], float]]:
    """Greedy, one pass, no lookahead -- which is what CSS 2.1 describes.

    The width a unit is tested against includes the **previous** unit's
    trailing white space and excludes its own: a trailing space at the end
    of a line is trimmed or hung, so it must not be what pushes the next
    word off the line.
    """
    lines: list[tuple[list[_Unit], float]] = []
    current: list[_Unit] = []
    x = 0.0
    pending = 0.0

    for unit in units:
        atomic_width = sum(
            _atomic_outer_width(piece.item)
            for piece in unit.pieces
            if piece.item.kind == _ATOMIC
        )
        content = unit.content_width + atomic_width
        if current and x + pending + content > available_width + EPSILON:
            _count_trailing(current[-1], metrics)
            lines.append((current, x))
            metrics["line_breaks_soft"] += 1
            current = []
            x = 0.0
            pending = 0.0
        elif not current and content > available_width + EPSILON:
            metrics["line_overflow_unbreakable"] += 1
        current.append(unit)
        x += pending + content
        pending = unit.trailing_width
        if unit.forced_break:
            for piece in unit.pieces:
                if piece.item.kind == _BREAK:
                    metrics["line_breaks_forced_br"] += 1
                elif piece.item.kind == _TEXT:
                    metrics["line_breaks_forced_segment"] += piece.text.count(_LF)
            _count_trailing(unit, metrics)
            lines.append((current, x))
            current = []
            x = 0.0
            pending = 0.0
    if current:
        _count_trailing(current[-1], metrics)
        lines.append((current, x))
    return lines


def _count_trailing(unit: _Unit, metrics: Counter[str]) -> None:
    """Count the white space that ends a line, and only that.

    A unit's trailing space is inside the line whenever another unit
    follows it, so counting it as trimmed on every unit measured the number
    of *words* rather than the number of *lines* -- 9,996 against 986 line
    boxes on the corpus, which is what gave it away.
    """
    if not unit.trailing_chars:
        return
    metrics[
        "text_line_trailing_space_hung"
        if unit.trailing_hangs
        else "text_line_trailing_space_trimmed"
    ] += unit.trailing_chars


def _atomic_outer_width(item: _Item) -> float:
    box = item.box
    width = box.shrink_to_fit_width
    if width is None:
        return 0.0
    style = item.style
    zero: Counter[str] = Counter()
    return (
        width
        + px_or_zero(style.margin_left, basis=0.0, metrics=zero)
        + px_or_zero(style.margin_right, basis=0.0, metrics=zero)
        + px_or_zero(style.border_left_width, basis=0.0, metrics=zero)
        + px_or_zero(style.border_right_width, basis=0.0, metrics=zero)
        + px_or_zero(style.padding_left, basis=0.0, metrics=zero)
        + px_or_zero(style.padding_right, basis=0.0, metrics=zero)
    )


# --------------------------------------------------------------------------
# Vertical alignment -- CSS 2.1 sections 10.8 and 10.8.1
# --------------------------------------------------------------------------


@dataclass
class _Aligned:
    """One box participating in a line box's vertical alignment.

    `ascent` and `descent` are the box's **own** extent above and below its
    own baseline: for an inline box that is the content area plus its half
    of the leading, and for an atomic inline it is the split of its margin
    box at its baseline. `offset` is filled in later and is the distance
    from the *root* baseline, positive downward.
    """

    box: Box | None
    style: ComputedStyle
    metrics_: LineMetrics
    ascent: float
    descent: float
    vertical_align: object
    children: list["_Aligned"] = field(default_factory=list)
    is_atomic: bool = False
    offset: float = 0.0


def _subtree_extent(node: _Aligned, metrics: Counter[str]) -> tuple[float, float]:
    """The aligned subtree's extent, relative to `node`'s own baseline.

    CSS 2.1 section 10.8.1: the aligned subtree of an inline box is the box
    plus the aligned subtrees of every child whose `vertical-align` is not
    `top` or `bottom`. Those two are excluded because they are aligned to
    the line box, which does not exist until this returns.
    """
    ascent = node.ascent
    descent = node.descent
    for child in node.children:
        if _keyword(child.vertical_align) in ("top", "bottom"):
            continue
        shift = _shift_of(child, node, metrics, count=False)
        child_ascent, child_descent = _subtree_extent(child, metrics)
        ascent = max(ascent, child_ascent - shift)
        descent = max(descent, child_descent + shift)
    return ascent, descent


def _keyword(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _shift_of(
    child: _Aligned, parent: _Aligned, metrics: Counter[str], *, count: bool
) -> float:
    """How far `child`'s baseline sits below `parent`'s, in pixels.

    Positive is downward, matching the coordinate system everywhere else in
    this engine. `count` is False while the extents are being explored --
    the same child is visited twice, once to size the subtree and once to
    place it, and counting both would double every figure.
    """
    value = child.vertical_align
    if isinstance(value, Percent):
        # Task A2 resolved this against the used `line-height` wherever the
        # line-height was a number or a px length, and deferred it where
        # `line-height: normal` needed font metrics that did not exist yet.
        # They exist here, so this is where the deferral is paid off.
        if count:
            metrics["vertical_align_percent_resolved_in_layout"] += 1
            metrics["vertical_align_applied_percentage"] += 1
        return -(float(value.value) / 100.0 * child.metrics_.line_height)
    if isinstance(value, Length):
        if count:
            metrics["vertical_align_applied_length"] += 1
        return -(float(value.value) if value.unit == "px" else 0.0)

    keyword = _keyword(value) or "baseline"
    if count:
        metrics["vertical_align_applied_" + keyword.replace("-", "_")] += 1
    if keyword == "baseline":
        return 0.0
    if keyword == "sub":
        # UA-defined in CSS 2.1. Chrome 151, measured: `font-size / 5 + 1`.
        return child.metrics_.font_size / 5.0 + 1.0
    if keyword == "super":
        return -(child.metrics_.font_size / 3.0 + 1.0)
    if keyword == "middle":
        # The box's midpoint at the parent's baseline minus half the
        # parent's x-height. `docs/fonts.md` takes x-height from
        # `OS/2.sxHeight`; Chrome reports a slightly smaller one, which is
        # a 0.078px disagreement at 16px, recorded and not tuned away.
        return (
            (child.ascent - child.descent) / 2.0 - parent.metrics_.x_height / 2.0
        )
    if keyword == "text-top":
        ascent, _ = _subtree_extent(child, metrics)
        return ascent - parent.metrics_.ascent
    if keyword == "text-bottom":
        _, descent = _subtree_extent(child, metrics)
        return parent.metrics_.descent - descent
    # `top` and `bottom` are aligned against the line box itself, which is
    # not known until every other box has been placed. Zero here, corrected
    # in `_align_top_and_bottom`.
    return 0.0


def _assign_offsets(node: _Aligned, metrics: Counter[str]) -> None:
    """Walk the alignment tree top down, giving each box its baseline offset.

    `top` and `bottom` are counted here and **not** recursed into: their own
    offset is not known until the line's extent is, so their subtrees are
    placed by `_align_top_and_bottom`. Counting them here and placing them
    there is what keeps `vertical_align_boxes_aligned` a partition -- every
    box is counted exactly once, whichever of the two paths it takes.
    """
    for child in node.children:
        keyword = _keyword(child.vertical_align)
        metrics["vertical_align_boxes_aligned"] += 1
        if keyword in ("top", "bottom"):
            metrics["vertical_align_applied_" + keyword] += 1
            continue
        child.offset = node.offset + _shift_of(child, node, metrics, count=True)
        _assign_offsets(child, metrics)


def _align_top_and_bottom(
    root: _Aligned,
    top_extent: float,
    bottom_extent: float,
    metrics: Counter[str],
) -> tuple[float, float]:
    """Place the `top`- and `bottom`-aligned subtrees, once.

    CSS 2.1 acknowledges this is circular -- these boxes are aligned to a
    line box whose height they can then increase -- and does not say how far
    to iterate. One pass, and the counter says how often the pass changed
    anything, so "we stopped early" is a number rather than an omission.
    """
    pending: list[_Aligned] = []

    def find(node: _Aligned) -> None:
        for child in node.children:
            if _keyword(child.vertical_align) in ("top", "bottom"):
                pending.append(child)
            else:
                find(child)

    find(root)
    if not pending:
        return top_extent, bottom_extent

    for node in pending:
        ascent, descent = _subtree_extent(node, metrics)
        if _keyword(node.vertical_align) == "top":
            node.offset = top_extent + ascent
        else:
            node.offset = bottom_extent - descent
        _assign_offsets(node, metrics)
        new_top = min(top_extent, node.offset - ascent)
        new_bottom = max(bottom_extent, node.offset + descent)
        if new_top != top_extent or new_bottom != bottom_extent:
            metrics["vertical_align_top_bottom_extended_line"] += 1
        top_extent, bottom_extent = new_top, new_bottom
    return top_extent, bottom_extent


# --------------------------------------------------------------------------
# Placing one line
# --------------------------------------------------------------------------


def _place_line(
    units: list[_Unit],
    *,
    index: int,
    used_width: float,
    y: float,
    available_width: float,
    root_style: ComputedStyle,
    metrics: Counter[str],
    layout_atomic,
    fragment_counts: dict[int, int],
) -> LineBox:
    pieces = _coalesce([piece for unit in units for piece in unit.pieces])
    root_metrics = line_metrics(root_style, metrics=metrics)
    root_node = _Aligned(
        box=None,
        style=root_style,
        metrics_=root_metrics,
        ascent=root_metrics.box_ascent,
        descent=root_metrics.box_descent,
        vertical_align="baseline",
    )

    nodes: dict[int, _Aligned] = {}
    for piece in pieces:
        parent = root_node
        for ancestor in piece.item.ancestors:
            node = nodes.get(id(ancestor))
            if node is None:
                node = _inline_node(ancestor, metrics)
                nodes[id(ancestor)] = node
                parent.children.append(node)
            parent = node
        if piece.item.kind == _ATOMIC:
            box = piece.item.box
            if id(box) not in nodes:
                node = _atomic_node(box, piece.item.style, metrics, layout_atomic)
                nodes[id(box)] = node
                parent.children.append(node)

    _suppress_empty_boxes(pieces, nodes, root_node, metrics)
    _assign_offsets(root_node, metrics)
    ascent, descent = _subtree_extent(root_node, metrics)
    top_extent, bottom_extent = -ascent, descent
    top_extent, bottom_extent = _align_top_and_bottom(
        root_node, top_extent, bottom_extent, metrics
    )

    height = bottom_extent - top_extent
    baseline = -top_extent
    if height == 0.0:
        # CSS 2.1 section 9.4.2's empty line box, arrived at rather than
        # special-cased: every box on it contributed nothing, so the extent
        # is nothing. That matters for Task C's
        # `margin_collapse_blocked_line_box` -- a `<div><span></span></div>`
        # must still collapse through.
        metrics["line_boxes_empty_zero_height"] += 1

    line = LineBox(
        index=index,
        x=0.0,
        y=y,
        width=used_width,
        available_width=available_width,
        height=height,
        baseline=baseline,
        top_extent=top_extent,
        bottom_extent=bottom_extent,
    )
    for node in [root_node, *_descendants(root_node)]:
        line.aligned.append((node.offset, node.ascent, node.descent))

    start_x = _align_offset(root_style, used_width, available_width, metrics)
    line.x = start_x
    _emit_fragments(
        line,
        pieces,
        nodes,
        root_node,
        start_x=start_x,
        baseline_y=y + baseline,
        metrics=metrics,
        fragment_counts=fragment_counts,
    )
    return line


def _suppress_empty_boxes(
    pieces: list[_Piece],
    nodes: dict[int, _Aligned],
    root_node: _Aligned,
    metrics: Counter[str],
) -> None:
    """Zero the extent of every inline box with nothing of its own here.

    **This is a deliberate divergence from CSS 2.1 section 10.8**, measured
    rather than assumed, and it is the single largest behavioural decision
    in this module.

    The spec says a line box always contains a *strut* -- a zero-width
    inline box with the block container's font and line height -- so
    `<div><span style="font-size:8px">x</span></div>` should be 18.40px
    tall at a 16px block font. Chrome 151 makes it **9**. Measured at
    several shapes, all in a 100px `<div>` with `font: 16px/normal Arial`
    on the body:

        <span style="font-size:8px">x</span>                     9
        <span style="font-size:8px;line-height:8px">x</span>     8
        x                                                       18
        <span style="display:inline-block;width:10px;
              height:10px"></span>                              10
        <span style="line-height:60px"><ib 10px></span>         10
        <span style="padding:0 2px"><ib 10px></span>            45  (40px font)
        <br>                                                    18
        <span></span>                                            0

    Every row is explained by one rule and no other: **an inline box
    contributes its font metrics to a line box only when it directly
    contains text or a forced break on that line, or has edges of its
    own.** The root inline box is not exempt -- row 1 is the proof, and it
    is the row a reading of the spec gets wrong.

    Implementing the spec instead would make this engine disagree with the
    reference renderer on every line whose text sits inside a smaller-font
    inline box, which on a real page is most of the small print. Counted in
    `line_strut_suppressed_no_direct_text` so the size of the divergence
    from CSS 2.1 is a number rather than a paragraph.
    """
    contributes: set[int] = set()
    for piece in pieces:
        item = piece.item
        if item.kind == _TEXT and not piece.text:
            continue
        if item.kind not in (_TEXT, _BREAK):
            continue
        owner = item.ancestors[-1] if item.ancestors else None
        contributes.add(id(owner) if owner is not None else id(root_node))
    for node in [root_node, *_descendants(root_node)]:
        if node.is_atomic:
            continue
        key = id(node.box) if node.box is not None else id(root_node)
        if key in contributes or _has_edges(node.style):
            continue
        metrics["line_strut_suppressed_no_direct_text"] += 1
        node.ascent = 0.0
        node.descent = 0.0


def _coalesce(pieces: list[_Piece]) -> list[_Piece]:
    """Rejoin the pieces of one item that ended up on the same line.

    Segmentation cuts at **every** break opportunity, because the line
    filler needs to move one word at a time. A fragment is a different
    thing: Chrome answers `getContentQuads` with **one quad per line**, not
    one per word, so a text node with ten words on one line is one fragment
    and not ten.

    Measured before it was fixed rather than reasoned about: the corpus
    reported 1,753 inline boxes as "fragmented across a line break" against
    257 soft breaks and 37 forced ones, which cannot both be true. The
    counter is what said so.
    """
    out: list[_Piece] = []
    for piece in pieces:
        if out:
            previous = out[-1]
            if previous.item is piece.item and previous.end == piece.start:
                out[-1] = _Piece(
                    piece.item,
                    previous.start,
                    piece.end,
                    previous.width + piece.width,
                )
                continue
        out.append(piece)
    return out


def _descendants(node: _Aligned) -> list[_Aligned]:
    out: list[_Aligned] = []
    for child in node.children:
        out.append(child)
        out.extend(_descendants(child))
    return out


def _inline_node(box: Box, metrics: Counter[str]) -> _Aligned:
    style = style_of(box)
    box_metrics = line_metrics(style, metrics=metrics)
    return _Aligned(
        box=box,
        style=style,
        metrics_=box_metrics,
        ascent=box_metrics.box_ascent,
        descent=box_metrics.box_descent,
        vertical_align=style.vertical_align,
    )


def _atomic_node(
    box: Box, style: ComputedStyle, metrics: Counter[str], layout_atomic
) -> _Aligned:
    """An atomic inline's own extent, and where its baseline is.

    CSS 2.1 section 10.8.1: the baseline of an `inline-block` is the
    baseline of its **last line box**, unless it has no in-flow line boxes,
    in which case it is the bottom margin edge. Both branches are counted,
    because "it had no line boxes" and "we did not look" are different
    facts and only the split says which happened.
    """
    height, last_baseline = layout_atomic(box)
    zero: Counter[str] = Counter()
    margin_top = px_or_zero(style.margin_top, basis=0.0, metrics=zero)
    margin_bottom = px_or_zero(style.margin_bottom, basis=0.0, metrics=zero)
    outer = margin_top + height + margin_bottom
    if last_baseline is None:
        metrics["vertical_align_atomic_baseline_from_margin_edge"] += 1
        ascent = outer
    else:
        metrics["vertical_align_atomic_baseline_from_last_line"] += 1
        ascent = margin_top + last_baseline
    box_metrics = line_metrics(style, metrics=metrics)
    return _Aligned(
        box=box,
        style=style,
        metrics_=box_metrics,
        ascent=ascent,
        descent=outer - ascent,
        vertical_align=style.vertical_align,
        is_atomic=True,
    )


def _has_edges(style: ComputedStyle) -> bool:
    zero: Counter[str] = Counter()
    return any(
        px_or_zero(value, basis=0.0, metrics=zero) != 0.0
        for value in (
            style.margin_left, style.margin_right,
            style.padding_left, style.padding_right,
            style.border_left_width, style.border_right_width,
            style.padding_top, style.padding_bottom,
            style.border_top_width, style.border_bottom_width,
        )
    )


def _align_offset(
    style: ComputedStyle,
    used_width: float,
    available_width: float,
    metrics: Counter[str],
) -> float:
    """CSS 2.1 section 16.2, the part that needs a line box.

    `start` is `left` here because `direction` is not parsed at all, so
    there is no right-to-left containing block for it to differ in.
    `justify` is laid out as `start` and counted: stretching a line means
    distributing the remainder across its soft wrap opportunities, and
    there are **zero** `justify` declarations on the corpus, so it would be
    an unmeasurable implementation of an unexercised path.
    """
    value = style.text_align
    remainder = available_width - used_width
    if value in ("start", "left"):
        metrics["text_align_" + value] += 1
        return 0.0
    if value == "right":
        metrics["text_align_right"] += 1
        return remainder
    if value == "center":
        metrics["text_align_center"] += 1
        return remainder / 2.0
    metrics["text_align_justify_as_start"] += 1
    return 0.0


# --------------------------------------------------------------------------
# Fragments
# --------------------------------------------------------------------------


def _emit_fragments(
    line: LineBox,
    pieces: list[_Piece],
    nodes: dict[int, _Aligned],
    root_node: _Aligned,
    *,
    start_x: float,
    baseline_y: float,
    metrics: Counter[str],
    fragment_counts: dict[int, int],
) -> None:
    """Walk the line left to right, opening and closing inline boxes.

    An inline box that is split across lines puts its left margin, border
    and padding on its **first** fragment only and its right on its **last**
    (CSS 2.1 section 9.2.1.1's split rule, restated for line breaking in
    section 16). Adding them on every line instead is the kind of error that
    reads as a slightly wrong font rather than as a layout bug.

    Every horizontal advance the walk makes is appended to `line.advances`,
    including an inline box's own edges, because the width check is a
    conservation law and an edge that moves `x` without being recorded would
    break it.
    """
    x = start_x
    open_stack: list[Box] = []
    spans: dict[int, tuple[float, bool]] = {}
    closing = {id(box) for piece in pieces for box in piece.closes_here}

    def open_box(box: Box, piece: _Piece) -> None:
        nonlocal x
        first = box in piece.opens_here
        if first:
            edges = _leading_edges(nodes[id(box)].style)
            if edges:
                x += edges
                line.advances.append(edges)
        spans[id(box)] = (x, first)

    def close(box: Box) -> None:
        nonlocal x
        node = nodes[id(box)]
        content_left, first = spans.pop(id(box))
        content_right = x
        last = id(box) in closing
        if last:
            edges = _trailing_edges(node.style)
            if edges:
                x += edges
                line.advances.append(edges)
        _add_inline_fragment(
            line, box, node, content_left, content_right, baseline_y,
            first=first, last=last, metrics=metrics,
            fragment_counts=fragment_counts,
        )

    for piece in pieces:
        wanted = list(piece.item.ancestors)
        common = 0
        while (
            common < len(open_stack)
            and common < len(wanted)
            and open_stack[common] is wanted[common]
        ):
            common += 1
        for box in reversed(open_stack[common:]):
            close(box)
        del open_stack[common:]
        for box in wanted[common:]:
            open_box(box, piece)
            open_stack.append(box)

        item = piece.item
        if item.kind == _TEXT:
            body = piece.text
            if not body:
                continue
            width = piece.width - _trim_for_line(piece, pieces, metrics)
            node = root_node
            if item.ancestors:
                node = nodes.get(id(item.ancestors[-1]), root_node)
            _add_text_fragment(
                line, item.box, node, x, width, baseline_y, body,
                metrics, fragment_counts,
            )
            line.advances.append(width)
            x += width
        elif item.kind == _ATOMIC:
            node = nodes[id(item.box)]
            width = _atomic_outer_width(item)
            _place_atomic(item.box, node, x, baseline_y, metrics)
            _add_atomic_fragment(
                line, item.box, node, metrics, fragment_counts
            )
            line.advances.append(width)
            x += width

    for box in reversed(open_stack):
        close(box)


def _leading_edges(style: ComputedStyle) -> float:
    zero: Counter[str] = Counter()
    return (
        px_or_zero(style.margin_left, basis=0.0, metrics=zero)
        + px_or_zero(style.border_left_width, basis=0.0, metrics=zero)
        + px_or_zero(style.padding_left, basis=0.0, metrics=zero)
    )


def _trailing_edges(style: ComputedStyle) -> float:
    zero: Counter[str] = Counter()
    return (
        px_or_zero(style.padding_right, basis=0.0, metrics=zero)
        + px_or_zero(style.border_right_width, basis=0.0, metrics=zero)
        + px_or_zero(style.margin_right, basis=0.0, metrics=zero)
    )


def _trim_for_line(
    piece: _Piece, pieces: list[_Piece], metrics: Counter[str]
) -> float:
    """The width of trailing white space this piece must not contribute.

    Only the line's last trimmable text piece can have any. Recomputed here
    from the line rather than carried over from `_measure_units`, because
    the unit that donated the space may have been ended by a forced break
    rather than by running out of room, and only the line knows that.
    """
    if piece is not _last_trimmable_text_piece(pieces):
        return 0.0
    tail = _trailing_white_space(piece)
    if not tail:
        return 0.0
    return measure(tail, piece.item.style, metrics=metrics)


def _is_last_piece_of(box: Box, pieces: list[_Piece]) -> bool:
    """Does this inline box end on this line, or continue onto the next?

    Answered from the box's own subtree rather than from the line: the last
    item under `box` in document order is the one that decides, and this
    line contains it or it does not.
    """
    last_item: _Item | None = None
    for piece in pieces:
        if box in piece.item.ancestors:
            last_item = piece.item
            last_end = piece.end
    if last_item is None:
        return True
    return last_end >= last_item.length


def _add_text_fragment(
    line: LineBox,
    box: Box,
    node: _Aligned,
    x: float,
    width: float,
    baseline_y: float,
    body: str,
    metrics: Counter[str],
    fragment_counts: dict[int, int],
) -> None:
    content = Rect(
        x,
        baseline_y + node.offset - node.metrics_.ascent,
        width,
        node.metrics_.content_height,
    )
    _record(
        line, box, _flat_geometry(content, line.available_width), body,
        metrics, fragment_counts, "text",
    )


def _add_inline_fragment(
    line: LineBox,
    box: Box,
    node: _Aligned,
    content_left: float,
    content_right: float,
    baseline_y: float,
    *,
    first: bool,
    last: bool,
    metrics: Counter[str],
    fragment_counts: dict[int, int],
) -> None:
    style = node.style
    zero: Counter[str] = Counter()

    def edge(value: object) -> float:
        return px_or_zero(value, basis=0.0, metrics=zero)

    content = Rect(
        content_left,
        baseline_y + node.offset - node.metrics_.ascent,
        max(0.0, content_right - content_left),
        node.metrics_.content_height,
    )
    geometry = _inline_geometry(
        content,
        padding=Edges(
            edge(style.padding_top), edge(style.padding_right),
            edge(style.padding_bottom), edge(style.padding_left),
        ),
        border=Edges(
            edge(style.border_top_width), edge(style.border_right_width),
            edge(style.border_bottom_width), edge(style.border_left_width),
        ),
        margin=Edges(0.0, edge(style.margin_right), 0.0, edge(style.margin_left)),
        first=first,
        last=last,
        available=line.available_width,
    )
    _record(line, box, geometry, None, metrics, fragment_counts, "inline_box")


def _add_atomic_fragment(
    line: LineBox,
    box: Box,
    node: _Aligned,
    metrics: Counter[str],
    fragment_counts: dict[int, int],
) -> None:
    """An atomic inline has exactly one fragment: it never splits.

    Its geometry is the one block layout already produced and `_place_atomic`
    already moved, so this records the box rather than building a rectangle
    -- two rectangles for one box is how they come to disagree.
    """
    geometry = box.geometry
    if geometry is None:
        return
    _record(line, box, geometry, None, metrics, fragment_counts, "atomic")


def _record(
    line: LineBox,
    box: Box,
    geometry: BoxGeometry,
    text: str | None,
    metrics: Counter[str],
    fragment_counts: dict[int, int],
    kind: str,
) -> None:
    index = _next_fragment_index(box, fragment_counts)
    fragment = InlineFragment(
        box=box, index=index, line=line.index, geometry=geometry, text=text
    )
    box.fragments.append(fragment)
    line.fragments.append(fragment)
    metrics["line_fragments"] += 1
    metrics["line_fragments_" + kind] += 1
    if index == 1:
        metrics["line_inline_boxes_fragmented"] += 1


def _next_fragment_index(box: Box, fragment_counts: dict[int, int]) -> int:
    """The fragment number for this node, across every `Box` it produced.

    Keyed by the DOM node rather than by the box, because Task B may have
    already split this inline around a block-level child into several
    boxes; Chrome answers `getContentQuads` for the node with one quad per
    fragment across the whole split, so the index has to be continuous.
    Keyed by `id(box)` when there is no node -- an anonymous box has no CDP
    counterpart and its index is never compared.
    """
    key = id(box.node) if box.node is not None else id(box)
    index = fragment_counts.get(key, 0)
    fragment_counts[key] = index + 1
    return index


def _flat_geometry(content: Rect, available: float) -> BoxGeometry:
    """A text fragment has no box of its own: all four edges coincide.

    A text node is not an element and CDP answers for it through a `Range`
    rather than through `getBoxModel`, so giving it padding or a border
    would be inventing a box nothing on the other side has.
    """
    return BoxGeometry(
        content=content,
        padding=content,
        border=content,
        margin=content,
        used_margin=Edges(0.0, 0.0, 0.0, 0.0),
        used_padding=Edges(0.0, 0.0, 0.0, 0.0),
        used_border=Edges(0.0, 0.0, 0.0, 0.0),
        containing_block_width=available,
    )


def _inline_geometry(
    content: Rect,
    *,
    padding: Edges,
    border: Edges,
    margin: Edges,
    first: bool,
    last: bool,
    available: float,
) -> BoxGeometry:
    """The four rectangles of one inline fragment.

    Vertical padding and border on an inline box **do not** affect line
    height -- CSS 2.1 section 10.8 -- so they grow the padding and border
    rectangles and change nothing about where the box sits. Horizontal ones
    do take space, and only on the fragment where the box actually begins
    or ends.
    """
    left_pad = padding.left if first else 0.0
    right_pad = padding.right if last else 0.0
    left_border = border.left if first else 0.0
    right_border = border.right if last else 0.0
    left_margin = margin.left if first else 0.0
    right_margin = margin.right if last else 0.0
    padding_rect = Rect(
        content.x - left_pad,
        content.y - padding.top,
        content.width + left_pad + right_pad,
        content.height + padding.top + padding.bottom,
    )
    border_rect = Rect(
        padding_rect.x - left_border,
        padding_rect.y - border.top,
        padding_rect.width + left_border + right_border,
        padding_rect.height + border.top + border.bottom,
    )
    margin_rect = Rect(
        border_rect.x - left_margin,
        border_rect.y,
        border_rect.width + left_margin + right_margin,
        border_rect.height,
    )
    return BoxGeometry(
        content=content,
        padding=padding_rect,
        border=border_rect,
        margin=margin_rect,
        used_margin=Edges(0.0, right_margin, 0.0, left_margin),
        used_padding=Edges(padding.top, right_pad, padding.bottom, left_pad),
        used_border=Edges(border.top, right_border, border.bottom, left_border),
        containing_block_width=available,
    )


def _place_atomic(
    box: Box, node: _Aligned, x: float, baseline_y: float, metrics: Counter[str]
) -> None:
    """Move an already-laid-out atomic inline onto the line.

    Block layout put its margin box at the origin of a containing block
    that does not exist; this shifts the whole subtree so that its margin
    box starts at `x` and its baseline lands where alignment put it.
    """
    geometry = box.geometry
    if geometry is None:
        return
    dy = baseline_y + node.offset - node.ascent - geometry.margin.y
    _translate(box, x - geometry.margin.x, dy)


def _translate(box: Box, dx: float, dy: float) -> None:
    geometry = box.geometry
    if geometry is not None:
        geometry.content = replace(
            geometry.content, x=geometry.content.x + dx, y=geometry.content.y + dy
        )
        geometry.padding = replace(
            geometry.padding, x=geometry.padding.x + dx, y=geometry.padding.y + dy
        )
        geometry.border = replace(
            geometry.border, x=geometry.border.x + dx, y=geometry.border.y + dy
        )
        geometry.margin = replace(
            geometry.margin, x=geometry.margin.x + dx, y=geometry.margin.y + dy
        )


# --------------------------------------------------------------------------
# The mechanical checks
# --------------------------------------------------------------------------


def assert_line_box(line: LineBox) -> None:
    """A line box's contents must account for its extent.

    Two independent recomputations, both from the stored per-box numbers
    rather than from the scalars the placement pass produced. That is the
    same discipline as Task C's constraint assertion reading the rectangles
    instead of the resolver's own variables: a version that re-read the
    stored height would agree with itself and catch nothing.

    A zero-height line box -- CSS 2.1 section 9.4.2's empty line -- is
    exempt from the vertical half, because its height is *defined* to
    disagree with its contents' extent. It is the one case where the
    invariant is deliberately broken, so it is named here rather than
    quietly tolerated by a loose tolerance.
    """
    if line.height > 0.0 and line.aligned:
        top = min(offset - ascent for offset, ascent, _ in line.aligned)
        bottom = max(offset + descent for offset, _, descent in line.aligned)
        assert math.isclose(
            line.height, bottom - top, rel_tol=0.0, abs_tol=1e-6
        ), (
            f"line box {line.index}: height {line.height} does not equal the "
            f"extent of what is on it, {bottom - top} -- a box was aligned "
            "and then left out of the extent"
        )
        assert math.isclose(line.baseline, -top, rel_tol=0.0, abs_tol=1e-6), (
            f"line box {line.index}: baseline {line.baseline} is not the "
            f"topmost extent {-top}"
        )
    total = sum(line.advances)
    assert math.isclose(line.width, total, rel_tol=0.0, abs_tol=1e-6), (
        f"line box {line.index}: used width {line.width} is not the sum of "
        f"the advances placed on it, {total}"
    )


def assert_line_partitions(metrics: Counter[str]) -> None:
    """Three partitions over a whole layout, run every time.

    Each one fails the moment a category is added and forgotten, which is
    the failure mode this project has actually had rather than the one it
    imagined: `boxes_inline_split` reported 34, then 2, then 0 for the same
    three pages because one name covered two populations.
    """
    aligned = sum(metrics[name] for name in _ALIGNMENT_COUNTERS)
    assert metrics["vertical_align_boxes_aligned"] == aligned, (
        "every box on a line box was aligned by exactly one named "
        f"`vertical-align` rule: aligned "
        f"{metrics['vertical_align_boxes_aligned']} != {aligned}"
    )

    fragments = (
        metrics["line_fragments_text"]
        + metrics["line_fragments_inline_box"]
        + metrics["line_fragments_atomic"]
    )
    assert metrics["line_fragments"] == fragments, (
        "every inline fragment is a text run, an inline box or an atomic "
        f"inline: {metrics['line_fragments']} != {fragments}"
    )

    opportunities = (
        metrics["linebreak_opportunities_at_space"]
        + metrics["linebreak_opportunities_other"]
    )
    assert metrics["linebreak_opportunities"] == opportunities, (
        "every soft wrap opportunity is at a space or it is not: "
        f"{metrics['linebreak_opportunities']} != {opportunities}"
    )
