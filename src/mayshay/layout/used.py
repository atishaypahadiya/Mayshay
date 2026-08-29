"""Computed value -> used value, for the two modules that both need it.

Task C put `_px`, `_px_or_zero` and `_style_of` in `layout.block` because it
was the only caller. Task D1 adds a second: `layout.intrinsic` resolves the
margins, borders and padding of a box's descendants to turn an inner
min-content size into an outer min-content *contribution*, and `block`
imports `intrinsic` for the shrink-to-fit formula -- so `intrinsic` cannot
import `block` back.

Moved rather than duplicated. Two copies of a percentage-resolution rule is
exactly the shape `intrinsic.py`'s own docstring argues against for
shrink-to-fit: one implementation, three consumers.

Nothing here decides anything. It reads a `ComputedStyle` and returns a
number, and every behavioural comment stays with the code it describes.
"""

from __future__ import annotations

from collections import Counter

from mayshay.cssparse.cascade import VIEWPORT_UNITS, ComputedStyle
from mayshay.cssparse.values import AUTO, Length, Percent
from mayshay.layout.boxtree import Box

# The style an anonymous box is laid out with. Anonymous boxes have no
# declarations of their own -- CSS 2.1 section 9.2.1.1 gives them the
# initial value of every non-inherited property -- so one shared instance is
# correct as long as nothing mutates it, and nothing here does.
ANONYMOUS_STYLE = ComputedStyle(display="block")


def px(value: object, *, basis: float, metrics: Counter[str]) -> float | None:
    """A computed length or percentage as pixels, or None for `auto`.

    `basis` is the containing block's **width** for every percentage layout
    resolves, vertical margins and vertical padding included -- CSS 2.1
    sections 8.3 and 8.4, and `docs/percentage-resolution.md`. Measured
    against Chrome 151 rather than taken from the spec text: a
    `margin-top: 10%` in a 400x800 containing block is 40px, not 80px.
    """
    if value is AUTO:
        return None
    if isinstance(value, Percent):
        return float(value.value) / 100.0 * basis
    if isinstance(value, Length):
        if value.unit in VIEWPORT_UNITS:
            # `cascade._length_to_px` returns None for `vw`/`vh`/`vmin`/
            # `vmax` and the value survives symbolically. Resolving it *here*
            # would give two answers for the same unit -- a `vw` box-model
            # length would resolve and a `vw` font-size would not -- so it
            # stays where it belongs: `_length_to_px` needs a viewport
            # threaded through its two call sites, which is a cascade change
            # and not a layout one. Counted, and treated as zero.
            #
            # Three occurrences on the corpus, all on example.com
            # (`60vw` once, `15vh` twice) and all box-model.
            metrics["layout_viewport_unit_unresolved"] += 1
            return 0.0
        if value.unit != "px":
            metrics["layout_length_unit_unexpected"] += 1
            return 0.0
        return float(value.value)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    metrics["layout_length_unit_unexpected"] += 1
    return 0.0


def px_or_zero(value: object, *, basis: float, metrics: Counter[str]) -> float:
    resolved = px(value, basis=basis, metrics=metrics)
    return 0.0 if resolved is None else resolved


def style_of(box: Box) -> ComputedStyle:
    """The style this box is laid out with.

    `box.style` wins over the DOM node's, and the order matters: Task E's
    table wrapper box **keeps its element's identity** -- it is the box
    `DOM.getBoxModel` answers for the `<table>` -- while carrying only the
    half of that element's style CSS 2.1 section 17.4 assigns to it. Reading
    `node.computed_style` first would give it the borders and padding as
    well, and they are already on the table box inside it.
    """
    if box.style is not None:
        return box.style
    if box.origin == "element" and box.node is not None:
        style = box.node.computed_style
        if style is not None:
            return style
    return ANONYMOUS_STYLE


def text_style_of(box: Box) -> ComputedStyle:
    """The style a **text** box is measured with: its parent element's.

    A text node has no computed style of its own -- every inherited property
    a text run needs (`font-size`, `white-space`, `line-height`) lives on
    the element containing it. Resolved through the **DOM** parent chain
    rather than the box tree, for two reasons. `Box` carries no
    back-pointer, and more importantly an anonymous box sits between a text
    box and its element wherever Task B wrapped an inline run -- an
    anonymous box has the *initial* value of every non-inherited property,
    so reading `white-space` off it would silently reset an inherited value
    to `normal` on exactly the mixed-content containers where it matters.
    """
    node = box.node.parent if box.node is not None else None
    while node is not None:
        style = getattr(node, "computed_style", None)
        if style is not None:
            return style
        node = node.parent
    return ANONYMOUS_STYLE
