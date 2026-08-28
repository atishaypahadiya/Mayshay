"""Box geometry -- the rectangles every laid-out box carries.

Moved out of `layout.block` in Task D2 for the same reason `layout.used`
was moved out in Task D1: two modules need it and one of them cannot import
the other. `layout.block` lays out inline content by calling
`layout.linebox`, so `linebox` cannot import `block` back for `Rect`.

Nothing here decides anything -- these are the shapes, and every rule about
how they are filled stays with the code that fills them.

The **fragment** distinction is the one thing worth stating here rather than
at a call site. A block-level box has exactly one `BoxGeometry`. An inline
box that crosses a line break has **one per line**, and the union of them is
not a box: `DOM.getBoxModel` returns that union for a wrapping inline and it
matches none of the fragments (`docs/measurement-hazards.md` instance 3), so
an inline box carries `Box.fragments` and leaves `Box.geometry` as `None`
rather than storing a plausible rectangle nothing agrees with.
"""

from __future__ import annotations

from dataclasses import dataclass

# Floating-point slack for the constraint assertions. Every number here is a
# sum of a handful of terms, so a real violation is orders of magnitude
# larger than this and a rounding artefact is orders of magnitude smaller.
EPSILON = 1e-6


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
    # Whether this box's own top and bottom margins ended up adjoining --
    # section 8.3.1's collapse-through. Recorded rather than inferred: a
    # zero-height box with no children looks identical from the outside
    # whether it collapsed through or was stopped by a line box or a new
    # formatting context, and a census that guesses from the geometry counts
    # 78 where the layout counted 58.
    collapsed_through: bool = False
