"""Intrinsic sizing -- one capability, three consumers. Not implemented yet.

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

* Task C -- shrink-to-fit for `inline-block`, floats and absolutely
  positioned boxes. Those boxes are laid out nowhere today; Task C counts
  them in `widths_deferred_shrink_to_fit` and leaves them without geometry.
* Task E -- automatic table layout's column widths.
* Task F -- `flex-basis: auto` resolution on the main axis.

Three independent implementations would disagree on the same page with no
single place to fix it. That is the same argument as fixing stylesheet
cascade ordering at the chokepoint rather than at each symptom.

**Blocked on Task D**, not on a decision. Both functions bottom out in
`measure(text, style) -> width` over the vendored font's `hmtx` advances,
which does not exist yet. Everything above that seam -- white-space
collapsing to find the widest unbreakable run for min-content, and the
no-break-anywhere sum for max-content -- is this module's own work and is
hand-rolled like the rest.
"""

from __future__ import annotations

from mayshay.layout.boxtree import Box


def min_content_width(box: Box) -> float:
    """The narrowest this box's contents can be without overflowing: the
    width of its widest unbreakable run, after white-space collapsing.

    Needs Task D's `measure()`.
    """
    raise NotImplementedError(
        "intrinsic sizing needs Task D's text measurement; Task C counts the "
        "boxes that want it in widths_deferred_shrink_to_fit"
    )


def max_content_width(box: Box) -> float:
    """The width this box's contents would take with no line breaking at
    all.

    Needs Task D's `measure()`.
    """
    raise NotImplementedError(
        "intrinsic sizing needs Task D's text measurement; Task C counts the "
        "boxes that want it in widths_deferred_shrink_to_fit"
    )


def shrink_to_fit(box: Box, available_width: float) -> float:
    """CSS 2.1 section 10.3.5, the one place the formula is written down.

    `min(max(min-content, available), max-content)`.
    """
    return min(
        max(min_content_width(box), available_width), max_content_width(box)
    )
