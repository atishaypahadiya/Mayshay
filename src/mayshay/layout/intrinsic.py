"""Intrinsic sizing -- one capability, three consumers. Phase 3 Task D1.

`min_content_width` and `max_content_width` are the two numbers that CSS
2.1's shrink-to-fit formula (section 10.3.5) is built from:

    used width = min(max(min-content, available), max-content)

Three different-looking features in this phase are the same computation
reached by three routes, measured against Chrome 151 in a 900px containing
block with identical short and long contents:

    block, width: auto           900.00   900.00   <- the containing block
    table cell, width: auto       19.27   394.95   <- the contents
    flex item, flex-basis: auto   19.27   394.95   <- the contents
    inline-block                  19.27   394.95   <- the contents

The three content-driven rows agree to the hundredth of a pixel. The first
does not depend on content at all, which is why block-level `width: auto`
resolves in Task C without any of this and the other three cannot.

**Consumers, so this module has one implementation and not three:**

* Task D1 -- shrink-to-fit for `inline-block`, floats and absolutely
  positioned boxes. 50 boxes on the corpus, which Task C counted in
  `widths_deferred_shrink_to_fit` and left without geometry.
* Task E -- automatic table layout's column widths.
* Task F -- `flex-basis: auto` resolution on the main axis.

Three independent implementations would disagree on the same page with no
single place to fix it. That is the same argument as fixing stylesheet
cascade ordering at the chokepoint rather than at each symptom.

## The two sizes, and the one thing that separates them

Both walk the same tree and measure the same glyphs. The difference is
entirely in what a **soft wrap opportunity** does:

* max-content takes no break, so a space is 4.4453px of advance like any
  other glyph;
* min-content takes every break, so a space is a boundary and contributes
  nothing.

Which is why `layout.text.tokenize` exists rather than `str.split()`.
Under `white-space: nowrap` there are no soft wrap opportunities at all,
so the two sizes are **equal** and a `nowrap` box's min-content width is
its whole run -- the single most consequential thing on this corpus, where
`nowrap` is on 24% of element boxes and `pre` is on none.

## What is approximated, and counted

* A `<percentage>` `width`, `margin` or `padding` on a descendant resolves
  against a containing block that is not yet sized. CSS Sizing 3 section
  5.2.1 says to treat such a `width` as `auto`; the percentage margins and
  padding are taken as zero. Both are counted rather than silently applied
  against a basis of 0, which would look identical in the output.
* Floats do not shorten lines, per the partial-implementation principle in
  the Phase 3 plan, so a float inside a box contributes to that box's
  intrinsic sizes as though it were in flow.
* `min-width` / `max-width` are not parsed by `cssparse` at all and so
  cannot clamp anything here.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from mayshay.cssparse.cascade import ComputedStyle
from mayshay.cssparse.values import AUTO, Length, Percent
from mayshay.layout import linebreak as linebreak_module
from mayshay.layout import text as text_module
from mayshay.layout.boxtree import ATOMIC_INLINE_DISPLAYS, FLEX_DISPLAYS, Box
from mayshay.layout.used import px, px_or_zero, style_of, text_style_of

COUNTER_NAMES: tuple[str, ...] = (
    "intrinsic_sizes_computed",
    "intrinsic_percentage_width_as_auto",
    "intrinsic_percentage_edge_as_zero",
    "intrinsic_text_collapsed_on_demand",
    "intrinsic_specified_width_used",
    "intrinsic_atomic_inline_break_opportunity",
    "intrinsic_uax14_break_inside_a_run",
    # Task F. A row flex container sized by summing its items rather than
    # by taking the largest of them -- section 9.9 rather than block flow.
    "intrinsic_flex_row_summed",
    # Task H. An inline formatting context whose min-content came out wider
    # than its max-content because a negative margin was in it. See
    # `IntrinsicSizes.__post_init__`. **One per walk, not per box**: a
    # subtree measured three times counts three, exactly as
    # `intrinsic_uax14_break_inside_a_run` does, and for the same reason --
    # this module has no cache and every consumer asks it again.
    "intrinsic_inverted_by_negative_margin",
)


@dataclass(frozen=True)
class IntrinsicSizes:
    """`(min_content, max_content)` for one box's **contents**.

    Inner sizes: the box's own margins, borders and padding are not
    included. The *contribution* -- inner size plus edges -- is what a
    parent adds up, and it is computed by `outer_sizes` where those edges
    have already been resolved.

    `min_content <= max_content` is asserted on construction. It is the
    cheapest possible check and it fails loudly the moment a soft wrap
    opportunity is counted into the wrong one of the two.

    **Except where a margin is negative, and that exception is measured
    rather than assumed.** `negative_edges` says a box in this subtree
    contributed a negative outer size, and it is the only thing that makes
    the inversion legal. On keychron.com an `<input>` with `margin: -1px`
    on both sides sits beside an `inline-flex` label: the whole line is
    -2 + 46.68 = 44.68 wide, and breaking between them -- there is a soft
    wrap opportunity on both sides of an atomic inline -- gives runs of
    -2 and 46.68, so the widest *run* is 46.68 and the widest *line* is
    44.68. Both numbers are right and min-content really does exceed
    max-content. Every other route to this state is a wrap opportunity
    counted into the wrong size, which is what the assertion still says.

    The flag propagates, because the inversion does: a parent takes the
    largest min-content and the largest max-content of its children
    independently, so a child with an inverted pair can invert its
    parent's pair without any negative margin of the parent's own.
    """

    min_content: float
    max_content: float
    #: a box in this subtree has a negative margin, so the two sizes are not
    #: ordered. Not "this pair is inverted": the flag is about what was in
    #: the input, so that a *correctly* ordered pair from the same subtree
    #: does not silently license a later inversion elsewhere.
    negative_edges: bool = False

    def __post_init__(self) -> None:
        assert self.min_content <= self.max_content + 1e-9 or self.negative_edges, (
            "min-content must not exceed max-content: "
            f"{self.min_content} > {self.max_content} -- a soft wrap "
            "opportunity was counted into the wrong size"
        )



def intrinsic_sizes(box: Box, *, metrics: Counter[str] | None = None) -> IntrinsicSizes:
    """Both intrinsic sizes of `box`'s contents, in one walk.

    One function rather than two because the traversal, the white-space
    handling and the font measurement are shared; computing them separately
    would measure every glyph twice and give two places for the tokenizer
    to be consulted differently.
    """
    metrics = Counter() if metrics is None else metrics
    metrics["intrinsic_sizes_computed"] += 1
    return _inner_sizes(box, metrics)


def min_content_width(box: Box, *, metrics: Counter[str] | None = None) -> float:
    """The narrowest this box's contents can be without overflowing: the
    width of its widest unbreakable run, after white-space collapsing."""
    return intrinsic_sizes(box, metrics=metrics).min_content


def max_content_width(box: Box, *, metrics: Counter[str] | None = None) -> float:
    """The width this box's contents would take with no line breaking at
    all."""
    return intrinsic_sizes(box, metrics=metrics).max_content


def shrink_to_fit(
    box: Box, available_width: float, *, metrics: Counter[str] | None = None
) -> float:
    """CSS 2.1 section 10.3.5, the one place the formula is written down.

    `min(max(min-content, available), max-content)`.

    Both sizes come from a single walk: calling `min_content_width` and
    `max_content_width` here would traverse and measure the subtree twice,
    and -- worse -- would let the two answers come from two different
    traversals if this module ever grows a cache.
    """
    sizes = intrinsic_sizes(box, metrics=metrics)
    return min(max(sizes.min_content, available_width), sizes.max_content)


# --------------------------------------------------------------------------
# The walk
# --------------------------------------------------------------------------


def _inner_sizes(box: Box, metrics: Counter[str]) -> IntrinsicSizes:
    if any(child.is_inline_level for child in box.children):
        return _inline_sizes(box, metrics)
    if box.display in FLEX_DISPLAYS:
        return _flex_sizes(box, metrics)
    minimum = maximum = 0.0
    negative = False
    for child in box.children:
        sizes = outer_sizes(child, metrics)
        minimum = max(minimum, sizes.min_content)
        maximum = max(maximum, sizes.max_content)
        negative = negative or sizes.negative_edges
    return IntrinsicSizes(minimum, maximum, negative)


def _flex_sizes(box: Box, metrics: Counter[str]) -> IntrinsicSizes:
    """Flexbox 1 section 9.9: a **row** flex container's intrinsic widths
    are its items laid side by side, not stacked.

    This is the one place a flex container is not shaped like a block one
    for sizing purposes, and getting it wrong is quiet: `max(children)`
    instead of `sum(children)` gives a number that is the right type, is
    smaller than the truth, and produces an `inline-flex` that is exactly
    as wide as its widest item with the rest of them overflowing it.

    A **column** container is the block case and is deliberately left to
    it: this module computes widths, which are a column container's *cross*
    axis, and the cross size of a stack of items really is the largest of
    them.

    Single-line and multi-line differ on min-content and only on
    min-content: with `nowrap` the items cannot be separated, so the
    narrowest the container can be is the sum of their min-content
    contributions; with `wrap` each item can have a line to itself and the
    largest one decides.
    """
    style = style_of(box)
    if style.flex_direction not in ("row", "row-reverse"):
        minimum = maximum = 0.0
        negative = False
        for child in box.children:
            sizes = outer_sizes(child, metrics)
            minimum = max(minimum, sizes.min_content)
            maximum = max(maximum, sizes.max_content)
            negative = negative or sizes.negative_edges
        return IntrinsicSizes(minimum, maximum, negative)

    metrics["intrinsic_flex_row_summed"] += 1
    contributions = [outer_sizes(child, metrics) for child in box.children]
    # The gap between every adjacent pair is part of the container's
    # intrinsic size; a percentage gap has no basis here, exactly as a
    # percentage width has none, so it is zero and counted by the same rule.
    gap = 0.0
    if isinstance(style.column_gap, Length) and style.column_gap.unit == "px":
        gap = float(style.column_gap.value)
    elif isinstance(style.column_gap, Percent):
        metrics["intrinsic_percentage_edge_as_zero"] += 1
    gaps = gap * max(0, len(contributions) - 1)
    summed_max = sum(sizes.max_content for sizes in contributions) + gaps
    if style.flex_wrap == "nowrap":
        summed_min = sum(sizes.min_content for sizes in contributions) + gaps
    else:
        summed_min = max(
            (sizes.min_content for sizes in contributions), default=0.0
        )
    return IntrinsicSizes(
        min(summed_min, summed_max),
        summed_max,
        any(sizes.negative_edges for sizes in contributions),
    )


def outer_sizes(
    box: Box,
    metrics: Counter[str],
    *,
    include_margins: bool = True,
    ignore_specified_width: bool = False,
) -> IntrinsicSizes:
    """A box's intrinsic **contributions**: inner sizes plus its own edges.

    `basis=0.0` on every percentage is deliberate and is the reason
    `_specified_content_width` exists separately: a percentage *width* must
    behave as `auto` and fall through to the contents, while a percentage
    *margin* or *padding* really is taken as zero. Resolving both against a
    zero basis would give a percentage width of 0px, which is a different
    and much worse answer that looks the same in a counter.

    Two keyword arguments, both added by Task E and both because CSS 2.1
    chapter 17 asks a different question from CSS Sizing 3 -- not because
    table layout wanted a variant of its own:

    * `include_margins=False`. Section 17.5: "Internal table elements do not
      have margins." A cell's contribution to its column is its content plus
      its border and padding and nothing else.
    * `ignore_specified_width=True`. For a normal box a definite `width`
      *is* the contribution, which is what the default does. Section
      17.5.2.2 says something different for a cell -- "If the specified
      'width' (W) of the cell is greater than MCW, W is the minimum cell
      width" -- so the table needs the content-driven size **and** W, and
      takes the larger. It cannot get that from a function that has already
      thrown MCW away.

    The alternative was for `layout.table` to compute a cell's min-content
    itself, and the whole reason this module exists is that there must be
    exactly one implementation of that. Two keywords here are the cheap
    half of that bargain.
    """
    style = style_of(box)
    edges = _horizontal_edges(style, metrics)
    outside = edges.inside if not include_margins else edges.total
    specified = None if ignore_specified_width else _specified_content_width(
        style, metrics
    )
    if specified is not None:
        metrics["intrinsic_specified_width_used"] += 1
        if style.box_sizing == "border-box":
            specified = max(0.0, specified - edges.inside)
        return IntrinsicSizes(
            specified + outside, specified + outside, outside < 0.0
        )
    inner = _inner_sizes(box, metrics)
    return IntrinsicSizes(
        inner.min_content + outside,
        inner.max_content + outside,
        inner.negative_edges or outside < 0.0,
    )


def horizontal_edges(style: ComputedStyle, metrics: Counter[str]) -> "_Edges":
    """`(inside, total)` horizontal edges: border+padding, and with margins.

    Public since Task E. `layout.table` needs the same resolution this
    module uses for a cell's own edges, and a second copy of "a percentage
    padding on an unsized containing block is taken as zero, and counted"
    is exactly the drift `intrinsic.py` exists to prevent.
    """
    return _horizontal_edges(style, metrics)


def specified_content_width(
    style: ComputedStyle, metrics: Counter[str]
) -> float | None:
    """A definite `width` in pixels, or None when the contents decide.

    Public since Task E for the same reason as `horizontal_edges`: section
    17.5.2.2's W is this number, and the rule that a percentage `width`
    behaves as `auto` when the containing block is not yet sized is stated
    once, here.
    """
    return _specified_content_width(style, metrics)


@dataclass(frozen=True)
class _Edges:
    #: border + padding, the part `box-sizing: border-box` subtracts.
    inside: float
    #: border + padding + margin, the part a parent must make room for.
    total: float


def _horizontal_edges(style: ComputedStyle, metrics: Counter[str]) -> _Edges:
    for value in (
        style.margin_left,
        style.margin_right,
        style.padding_left,
        style.padding_right,
    ):
        if isinstance(value, Percent):
            metrics["intrinsic_percentage_edge_as_zero"] += 1
    inside = (
        px_or_zero(style.border_left_width, basis=0.0, metrics=metrics)
        + px_or_zero(style.border_right_width, basis=0.0, metrics=metrics)
        + px_or_zero(style.padding_left, basis=0.0, metrics=metrics)
        + px_or_zero(style.padding_right, basis=0.0, metrics=metrics)
    )
    margins = px_or_zero(
        style.margin_left, basis=0.0, metrics=metrics
    ) + px_or_zero(style.margin_right, basis=0.0, metrics=metrics)
    return _Edges(inside=inside, total=inside + margins)


def _specified_content_width(
    style: ComputedStyle, metrics: Counter[str]
) -> float | None:
    """A definite `width` in pixels, or None when the contents decide.

    CSS Sizing 3 section 5.2.1: for an intrinsic contribution, a
    percentage `width` behaves as `auto`. The containing block has no
    definite size at this point -- that is the whole reason intrinsic
    sizing is being asked for -- so a percentage of it is not a number.
    """
    if style.width is AUTO:
        return None
    if isinstance(style.width, Percent):
        metrics["intrinsic_percentage_width_as_auto"] += 1
        return None
    resolved = px(style.width, basis=0.0, metrics=metrics)
    return None if resolved is None else max(0.0, resolved)


# --------------------------------------------------------------------------
# Inline content
# --------------------------------------------------------------------------


class _InlineAccumulator:
    """Runs and lines, which is the whole of intrinsic inline sizing.

    * A **run** is content with no soft wrap opportunity inside it. The
      widest run is the min-content width.
    * A **line** is everything between forced breaks. The widest line is
      the max-content width.

    Runs and lines advance by *different* amounts for the same child: an
    atomic inline contributes its own min-content width to the run and its
    max-content width to the line, because it can wrap internally when the
    line is tight and will not when it is not.
    """

    def __init__(self) -> None:
        self.min_content = 0.0
        self.max_content = 0.0
        self.run = 0.0
        self.line = 0.0
        #: something on this line contributed a negative outer size, so the
        #: two results are not ordered. See `IntrinsicSizes.__post_init__`.
        self.negative_edges = False

    def content(self, minimum: float, maximum: float) -> None:
        if minimum < 0.0 or maximum < 0.0:
            self.negative_edges = True
        self.run += minimum
        self.line += maximum

    def soft_break(self, space_width: float) -> None:
        self.min_content = max(self.min_content, self.run)
        self.run = 0.0
        self.line += space_width

    def forced_break(self) -> None:
        self.min_content = max(self.min_content, self.run)
        self.max_content = max(self.max_content, self.line)
        self.run = 0.0
        self.line = 0.0

    def finish(self) -> IntrinsicSizes:
        self.forced_break()
        return IntrinsicSizes(
            self.min_content, self.max_content, self.negative_edges
        )


def _inline_sizes(box: Box, metrics: Counter[str]) -> IntrinsicSizes:
    accumulator = _InlineAccumulator()
    _walk_inline(box, accumulator, metrics)
    sizes = accumulator.finish()
    if sizes.min_content > sizes.max_content + 1e-9:
        # Counted here and nowhere else: this is the one place the two
        # sizes are produced from a walk that can invert them. The
        # population is **walks of an inline formatting context, not
        # boxes** -- nothing here is cached and each consumer asks again,
        # so keychron.com reads 58 for one `<li>` measured 58 times. Named
        # in `COUNTER_NAMES` rather than left for a reader to infer, which
        # is what `docs/measurement-hazards.md`'s unstated-denominator
        # section asks for.
        metrics["intrinsic_inverted_by_negative_margin"] += 1
    return sizes


def _walk_inline(
    box: Box, accumulator: _InlineAccumulator, metrics: Counter[str]
) -> None:
    wraps = text_module.behaviour_of(style_of(box).white_space).wraps
    for child in box.children:
        if child.origin == "text":
            _measure_text(child, accumulator, metrics)
        elif child.display in ATOMIC_INLINE_DISPLAYS:
            # There **is** a soft wrap opportunity on both sides of an
            # atomic inline. It is easy to assume otherwise -- nothing
            # separates it from the letter beside it -- and this engine did
            # until Chrome 151 was asked: `a<span style="display:inline-
            # block;width:40px"></span>b` has a min-content width of 40.00,
            # not 57.81, so Chrome breaks either side of the box rather
            # than keeping `a`, the box and `b` on one unbreakable run.
            #
            # UAX #14 is where it comes from: an atomic inline is
            # U+FFFC OBJECT REPLACEMENT CHARACTER, line-break class CB, and
            # rule LB20 breaks before and after CB. Under `nowrap` there is
            # no soft wrap opportunity anywhere, so the flushes do not
            # happen and the run runs straight through.
            sizes = outer_sizes(child, metrics)
            accumulator.negative_edges |= sizes.negative_edges
            if wraps:
                accumulator.soft_break(0.0)
                metrics["intrinsic_atomic_inline_break_opportunity"] += 2
            accumulator.content(sizes.min_content, sizes.max_content)
            if wraps:
                accumulator.soft_break(0.0)
        elif child.is_inline_level:
            # A non-atomic inline box. Its horizontal borders, padding and
            # margins sit *inside* the line, at the two ends of its
            # content, so they widen the current run rather than starting a
            # new one -- there is no break opportunity at an inline box's
            # edge.
            edges = _horizontal_edges(style_of(child), metrics)
            accumulator.content(edges.total, edges.total)
            _walk_inline(child, accumulator, metrics)
        else:
            # Block-level inside an inline run: Task B should have wrapped
            # or split it away. Contribute it as its own line rather than
            # silently dropping it.
            sizes = outer_sizes(child, metrics)
            accumulator.negative_edges |= sizes.negative_edges
            accumulator.forced_break()
            accumulator.content(sizes.min_content, sizes.max_content)
            accumulator.forced_break()


def _measure_text(
    box: Box, accumulator: _InlineAccumulator, metrics: Counter[str]
) -> None:
    style = text_style_of(box)
    collapsed = box.text
    if collapsed is None:
        # Reached only when intrinsic sizing runs on a tree that has not
        # been through `layout.inline.process_text` -- a unit test sizing a
        # hand-built box, in practice. Collapsed here as a lone context,
        # which trims its leading and trailing white space; a real page
        # never takes this path and the counter says so.
        metrics["intrinsic_text_collapsed_on_demand"] += 1
        source = box.node.data if box.node is not None else ""
        collapsed = text_module.collapse(source, style.white_space, metrics).text
    for kind, piece in text_module.tokenize(collapsed, style.white_space):
        if kind == text_module.FORCED_BREAK:
            accumulator.forced_break()
        elif kind == text_module.BREAK_SPACE:
            accumulator.soft_break(
                text_module.measure(piece, style, metrics=metrics)
            )
        else:
            _measure_run(piece, style, accumulator, metrics)


def _measure_run(
    piece: str,
    style: ComputedStyle,
    accumulator: _InlineAccumulator,
    metrics: Counter[str],
) -> None:
    """One unbreakable-looking run, broken at UAX #14's opportunities.

    **A Task D1 defect, found by Task D2 and measured against Chrome.**
    D1 split text on white space alone, so `alpha-beta` was one unbreakable
    unit and its min-content width was the whole string. Chrome 151 in a
    `width: min-content` box gives 44.4844 for `alpha-beta` -- it breaks
    after the hyphen -- against D1's 75.6250, and 48.0469 for `alpha?beta`
    against 79.1875.

    This is the same shape as `docs/measurement-hazards.md` instance
    fourteen and it has the same cause: CSS Text 3 does not define where a
    line may break, so a min-content width built on "split on spaces" is
    reading the citing layer. `alpha/beta` and `alpha` + NBSP + `beta` stay
    whole in both engines, which is what makes this a fix rather than a
    change of taste.

    The opportunities are computed **within** the run rather than across
    the whole formatting context, so a break at a run boundary --
    `<span>alpha-</span><span>beta</span>` -- is still missed. Counted, not
    hidden: the line breaker does it properly and this is intrinsic sizing,
    which by construction has no line to be on.
    """
    if not text_module.behaviour_of(style.white_space).wraps:
        # `nowrap` and `pre` have no soft wrap opportunity **anywhere**, so
        # the run is the run. Without this test the UAX #14 pass would break
        # a `nowrap` run at its own spaces -- which are inside the run
        # precisely because nothing may break there -- and a `nowrap` box's
        # min-content would stop equalling its max-content. Caught by
        # `test_nowrap_makes_the_two_sizes_equal`, which is what that test
        # is for.
        width = text_module.measure(piece, style, metrics=metrics)
        accumulator.content(width, width)
        return
    # No `metrics=` on purpose. `linebreak_opportunities` is a census of the
    # opportunities the **line breaker** found, and intrinsic sizing walks
    # much of the same text a second time: passing the counter here would
    # add two populations under one name, which is the defect
    # `docs/measurement-hazards.md` calls the unstated denominator. What
    # this pass contributes has its own counter below.
    flags = linebreak_module.break_opportunities(piece)
    start = 0
    for index in range(1, len(piece)):
        if not flags[index]:
            continue
        metrics["intrinsic_uax14_break_inside_a_run"] += 1
        width = text_module.measure(piece[start:index], style, metrics=metrics)
        accumulator.content(width, width)
        accumulator.soft_break(0.0)
        start = index
    width = text_module.measure(piece[start:], style, metrics=metrics)
    accumulator.content(width, width)
