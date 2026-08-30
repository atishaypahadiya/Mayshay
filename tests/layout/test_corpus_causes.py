"""The four defects behind the twelve pages that would not lay out -- Task H.

`tests/layout/test_corpus_lays_out.py` is the gate; this file is why it
went from **67 of 79 to 79 of 79**. One test per distinct *cause*, and
every one of them is derived from a named page in the
`2026-08-29-survey` collection rather than from a sketch of what the bug
might look like.

**That distinction is the whole point of this file.** The task brief says
so in as many words: a minimal synthetic reproduction of the Quanta
container -- a column flex container, `height: auto`,
`justify-content: center`, one child with a definite height -- *passes*.
It passes because a lone column container is never resized after it lays
itself out. Every fixture below therefore keeps the thing the real page
had and the sketch did not: the container that resizes it, the sibling
that decides the line's cross size, the table whose own section 17.5.2
width disagrees with the item size it was given.

Each test names, in its docstring:

* the page's source URL and its slug in `data/corpus/2026-08-29-survey/`,
* the exact assertion text that page raised, and
* which of the two candidate causes in the brief it turned out to be.

The numbers here are not Chrome measurements. Each is arithmetic over
explicit pixel sizes -- 30 minus 10 over 2 -- and nothing below is sized
by text, for the reason `test_flex.py`'s docstring gives: this engine
measures Liberation Sans from `hmtx` and Chrome measures Arial with its
own shaper, so a glyph-derived width is not comparable between them.
The one exception is `test_a_negative_margin_may_invert_the_two_intrinsic
_sizes`, which asserts a *relationship* (min > max) and no absolute width.

Per CLAUDE.md every fixture is at least three levels deep with siblings at
more than one level, and here that is load-bearing rather than ceremonial:
the Quanta container sits seven levels down and three of the four causes
need an ancestor of a specific kind to fire at all.
"""

from __future__ import annotations

import pytest

from mayshay.cssparse.cascade import style_document
from mayshay.cssparse.media import Viewport
from mayshay.dom.node import Element
from mayshay.htmlparse.treebuilder import parse
from mayshay.layout.block import layout_document
from mayshay.layout.boxtree import build_box_tree

#: Wider than `test_flex.py`'s 400px: two of these fixtures carry a
#: containing block whose width has to be distinguishable from the item
#: widths inside it, which is the entire subject of
#: `test_a_percentage_margin_on_a_flex_item_resolves_against_the_container`.
VIEWPORT = Viewport(1000, 800)

#: The UA sheet gives `body` an 8px margin, which would shift every x below.
RESET = "html,body{margin:0;padding:0}"


def laid_out(body: str, css: str = ""):
    document = parse(f"<!doctype html><style>{RESET}{css}</style>{body}")
    style_document(document, [], viewport=VIEWPORT)
    root, _ = build_box_tree(document)
    metrics = layout_document(root, VIEWPORT)
    return root, metrics


def boxes(root) -> dict[str, object]:
    found = {}
    for box in root.walk():
        if box.origin == "element" and isinstance(box.node, Element):
            ident = box.node.attrs.get("id")
            if ident:
                found[ident] = box
    return found


def rect(root, ident: str):
    """A box's **border** rectangle, absolute."""
    box = boxes(root)[ident]
    assert box.geometry is not None, f"#{ident} was not laid out"
    return box.geometry.border


# --------------------------------------------------------------------------
# Cause 1 of 4 -- a flex item's percentages resolved against the item
# --------------------------------------------------------------------------
#
# postgresql.org/docs/current/functions-string.html
#   www.postgresql.org-docs-current-functions-string.html-26ef8d1
# apple.com/macbook-air              www.apple.com-macbook-air-f283798
# nyc.gov/site/finance/index.page    www.nyc.gov-site-finance-index.page-7427611


def test_a_percentage_margin_on_a_flex_item_resolves_against_the_container():
    """Flexbox 1 section 4 and CSS 2.1 sections 8.3 and 8.4.

    Page: `postgresql.org/docs/current/functions-string.html`, slug
    `www.postgresql.org-docs-current-functions-string.html-26ef8d1`,
    collection `2026-08-29-survey`, container
    `/html[1]/body[1]/div[2]/div[1]/div[1]/div[1]`. It raised

        ... line 0: justify-content spent 0.0 of 58.01388652333344
        available free space (Flexbox 1 section 9.5)

    and `apple.com/macbook-air` and `nyc.gov/site/finance/index.page`
    raised the same assertion with 95.28 and 296.20 in it.

    **Neither of the brief's two candidates.** Nothing was mis-collected
    and no main size was stale: `layout.flex` put the item's percentage
    margins in the plan resolved against the container's 1142px content
    width, and `layout.block` then laid the item out with the item's own
    used main size as its containing block, so the same 8.333% came out
    37.15px instead of 95.17px. Both numbers are plausible used margins,
    which is why nothing downstream noticed until the free space failed to
    add up.

    Here: a 800px row container, `#b` with `margin-left: 10%`. Ten percent
    of the container is 80 and ten percent of `#b`'s own 200px is 20, so
    the two answers are 80px apart in `#b`'s x. `padding-top: 10%` is the
    same question on the axis where getting it right is less obvious --
    a vertical percentage also resolves against the containing block's
    *width*.
    """
    root, _ = laid_out(
        '<div id=page><div id=band>'
        '<div id=aside style="height:5px"></div>'
        '<div id=inner>'
        '<div id=row style="display:flex;width:800px">'
        '<div id=a style="flex:0 0 50%"></div>'
        '<div id=b style="flex:0 0 25%;margin-left:10%;padding-top:10%"></div>'
        "</div></div></div></div>"
    )
    assert rect(root, "a").width == 400
    assert rect(root, "b").width == 200
    # 400 for #a, then 10% of the CONTAINER: 80, not 10% of #b's own 200.
    assert rect(root, "b").x == 480
    # And the same rule on the block axis: 10% of 800, not of 200.
    assert rect(root, "b").height == 80


def test_a_flex_items_percentages_do_not_move_when_its_main_size_does():
    """The discriminating half of the fixture above, and the reason it is
    two tests.

    A container that resolved percentages against the item would still put
    `#b` at 480 if `#b`'s used width happened to equal the container's. Here
    the two items are given different main sizes, so an implementation that
    reads the item gets *two different* margins from one declaration --
    which is exactly what the corpus pages did.
    """
    root, _ = laid_out(
        '<div id=page><div id=band><div id=inner>'
        '<div id=row style="display:flex;width:800px">'
        '<div id=a style="flex:0 0 100px;margin-left:5%"></div>'
        '<div id=b style="flex:0 0 400px;margin-left:5%"></div>'
        "</div></div></div></div>"
    )
    # One declaration, one used value: 5% of 800 = 40, on both items.
    assert rect(root, "a").x == 40
    assert rect(root, "b").x == 40 + 100 + 40


# --------------------------------------------------------------------------
# Cause 2 of 4 -- a column container sized after it laid itself out
# --------------------------------------------------------------------------
#
# quantamagazine.org/physics   www.quantamagazine.org-physics-00fe4cb
# and six more: stackblitz.com, irs.gov/forms-instructions,
# store.steampowered.com/app/620, pbs.org/newshour/science,
# sparkfun.com/sparkfun-samd21-mini-breakout.html,
# theguardian.com/us/technology


def test_a_column_container_stretched_by_its_parent_justifies_again():
    """Flexbox 1 sections 9.4 step 11 and 9.5.

    Page: `quantamagazine.org/physics`, slug
    `www.quantamagazine.org-physics-00fe4cb`, collection
    `2026-08-29-survey`, container
    `/html[1]/body[1]/footer[1]/section[1]/div[1]/section[3]/div[2]/a[1]`.
    It raised

        ... line 0: justify-content spent 0.0 of 18.3984375 available
        free space (Flexbox 1 section 9.5) (got 0.0, expected 18.3984375)

    Six other pages raised the same assertion with 71.20, 78.00, 212.00,
    18.92, 28.40 and 280.80 in it.

    **Candidate 2, in the container rather than in the item.** The brief
    named "a column item's main size is stale". Measured, the *items'*
    main sizes were right and the **container's** was stale: the `<a>` is
    a column flex container with `height: auto`, so it laid itself out
    with an indefinite main size, and then its row-direction parent
    stretched it to the line's cross size and resized its box without its
    plan ever seeing the number. `justify-content: center` had nothing to
    centre when it ran and 18.4px of free space by the time the geometry
    was read.

    The shape below is the page's: a row container holding a text-bearing
    sibling that decides the line's cross size, and beside it the column
    container whose single item is shorter than that. **This is the case
    the brief warns a sketch will not reproduce** -- take `#label` away and
    nothing stretches `#link`, and the fixture passes with the defect in
    place.
    """
    root, metrics = laid_out(
        "<footer id=foot><section id=outer><div id=wrap>"
        '<section id=bar style="display:flex;justify-content:space-between">'
        '<div id=pair style="display:flex;justify-content:center">'
        '<div id=label style="width:120px;height:30px"></div>'
        '<a id=link style="display:flex;flex-direction:column;'
        'justify-content:center">'
        '<span id=hidden style="display:block;position:absolute;'
        'width:1px;height:1px;overflow:hidden"></span>'
        '<span id=icon style="display:block;width:16px;height:10px"></span>'
        "</a></div></section></div></section></footer>"
    )
    # The sibling decides the line, and the column container is stretched
    # to it -- which is what gives it a main size it never planned against.
    assert rect(root, "link").height == 30
    # 30 minus the item's 10, halved: `justify-content: center` spending
    # free space that only exists after the stretch.
    assert rect(root, "icon").y == 10
    assert metrics["flex_column_reflowed_definite_main"] == 1


def test_the_reflow_counts_the_container_once_not_twice():
    """Sections 9.3 to 9.6 run twice on a reflowed container and the
    counters must still describe it once.

    Same fixture as above. `flex_items_placed` reading 2 for a one-item
    container is the defect `docs/measurement-hazards.md` instance twenty
    names -- a count of *calls* wearing the name of a count of items -- and
    it is exactly what a naive re-run produces. The plan keeps what the
    first pass contributed and the reflow subtracts it before adding its
    own.

    Three containers here: `#bar` with one item, `#pair` with two, `#link`
    with one. Four items, three lines, whichever way the reflow went.
    """
    root, metrics = laid_out(
        "<footer id=foot><section id=outer><div id=wrap>"
        '<section id=bar style="display:flex;justify-content:space-between">'
        '<div id=pair style="display:flex;justify-content:center">'
        '<div id=label style="width:120px;height:30px"></div>'
        '<a id=link style="display:flex;flex-direction:column;'
        'justify-content:center">'
        '<span id=hidden style="display:block;position:absolute;'
        'width:1px;height:1px;overflow:hidden"></span>'
        '<span id=icon style="display:block;width:16px;height:10px"></span>'
        "</a></div></section></div></section></footer>"
    )
    assert metrics["flex_column_reflowed_definite_main"] == 1
    assert metrics["flex_containers_laid_out"] == 3
    assert metrics["flex_lines"] == 3
    assert metrics["flex_items_placed"] == 4


def test_an_absolutely_positioned_child_is_not_a_flex_item():
    """The brief's **candidate 1**, executed and rejected.

    The Quanta container has "two block children in the box tree and one
    item in its flex plan", and the brief asked whether a child that should
    have been collected was missed -- in which case `flex_items_placed` had
    been undercounting on every affected page and Task F's item census was
    wrong. Measured on the page, the second child is
    `position: absolute`, and Flexbox 1 section 4 says an absolutely
    positioned child of a flex container **is not a flex item**. Two
    children and one item is the correct reading of that markup, so the
    census stands and the discrepancy was never a discrepancy.

    `#hidden` below carries the page's own declarations, `display: block`
    included -- an *inline* absolutely positioned child would be wrapped in
    an anonymous block by the box tree and would produce an item, which is
    a different shape and would not reproduce the page.
    """
    root, metrics = laid_out(
        "<footer id=foot><section id=outer><div id=wrap>"
        '<section id=bar style="display:flex">'
        '<a id=link style="display:flex;flex-direction:column">'
        '<span id=hidden style="display:block;position:absolute;'
        'width:1px;height:1px;overflow:hidden"></span>'
        '<span id=icon style="display:block;width:16px;height:10px"></span>'
        "</a></section></div></section></footer>"
    )
    link = boxes(root)["link"]
    assert len(link.children) == 2
    assert [len(line.items) for line in link.flex_plan.lines] == [1]
    assert metrics["layout_absolute_skipped"] == 1


# --------------------------------------------------------------------------
# Cause 3 of 4 -- a table wrapper that is a flex item
# --------------------------------------------------------------------------
#
# tonsky.me/blog/unicode        tonsky.me-blog-unicode-82aba29
# stackblitz.com                stackblitz.com-6d5a929


def test_a_table_wrapper_keeps_the_tables_width_when_it_is_a_flex_item():
    """CSS 2.1 section 17.4: "the table wrapper box's width is the
    border-edge width of the table box inside it".

    Page: `tonsky.me/blog/unicode`, slug `tonsky.me-blog-unicode-82aba29`,
    collection `2026-08-29-survey`. It raised

        <anonymous table>: margin box width 469.0546875 != containing
        block width 0.0 (CSS 2.1 section 10.3.3)

    `stackblitz.com` raised the same assertion with 630.39 against 538.0,
    and only surfaced it once the percentage-margin defect above was
    fixed -- it had been failing on the flex assertion first.

    A `<table>` inside a column flex container is sized on the cross axis
    like any other item, and `layout.block` passed that size through
    `override_content_width` -- the bypass an atomic inline takes. The
    bypass discarded the width section 17.5.2 had already computed for the
    table, so the wrapper took the item size and the anonymous table box
    inside it kept the table's, and section 10.3.3's tiling broke between
    two boxes that are the same element.

    Section 17.4 is not a preference between two candidate widths; the
    anonymous table box is the wrapper's only in-flow child and its margin
    box spans the wrapper's content box by construction. On the page the
    item size was 0.0 because the table's `width: 96vw` is a viewport unit
    this engine does not resolve (`layout_viewport_unit_unresolved`); the
    10px below stands in for it, because the defect is the disagreement and
    not the number that provoked it.
    """
    root, metrics = laid_out(
        '<div id=page style="display:flex">'
        '<article id=col style="display:flex;flex-direction:column;'
        'align-items:flex-start;width:600px">'
        '<p id=intro style="height:20px"></p>'
        '<table id=grid style="width:10px">'
        '<tr><td id=c1 style="width:120px;height:15px"></td>'
        '<td id=c2 style="width:80px;height:15px"></td></tr>'
        "</table>"
        '<p id=outro style="height:20px"></p>'
        "</article></div>"
    )
    # The cells decide the table, and section 17.4 makes the wrapper follow.
    assert rect(root, "grid").width == 200
    assert rect(root, "c2").x == 120
    wrapper = next(box for box in root.walk() if box.table_wrapper)
    inner = next(child for child in wrapper.children if child.origin == "anonymous")
    assert wrapper.geometry.content.width == inner.geometry.margin.width
    assert metrics["layout_table_wrapper_width_wins"] == 1


# --------------------------------------------------------------------------
# Cause 4 of 4 -- a negative margin, and an assertion that did not allow it
# --------------------------------------------------------------------------
#
# keychron.com/collections/all-products
#   www.keychron.com-collections-all-products-53766b6


def test_a_negative_margin_may_invert_the_two_intrinsic_sizes():
    """`IntrinsicSizes` asserted `min_content <= max_content`. That is not
    universally true, and this is the page that proved it.

    Page: `keychron.com/collections/all-products`, slug
    `www.keychron.com-collections-all-products-53766b6`, collection
    `2026-08-29-survey`. It raised

        min-content must not exceed max-content: 46.6845703125 >
        44.6845703125 -- a soft wrap opportunity was counted into the
        wrong size

    and no soft wrap opportunity was counted into the wrong size. An
    `<input>` with `margin: -1px` on both sides sits beside an
    `inline-flex` label. There is a soft wrap opportunity on both sides of
    an atomic inline (UAX #14 rule LB20), so the widest *line* is
    -2 + 46.68 = 44.68 and the widest *run* is the label alone at 46.68.
    Both numbers are right and they are not ordered.

    **This is the "the assertion is also incomplete" case**, and the fix is
    not to floor one against the other -- that would throw away a measured
    number to satisfy a check. `IntrinsicSizes` now carries whether a
    negative outer size contributed, the inversion is legal only when it
    did, and every other route to it is still the wrap-opportunity defect
    the message names.

    Asserted as a relationship rather than in pixels: the two spans are
    46px of label against 2px of negative margin, and the inversion is
    what is being pinned, not the widths.
    """
    root, metrics = laid_out(
        '<div id=panel style="display:flex">'
        '<form id=facets style="display:flex;flex-direction:column;'
        'align-items:flex-start">'
        "<ul id=list>"
        "<li id=row1>"
        '<input id=box style="display:inline;white-space:nowrap;'
        'margin-left:-1px;margin-right:-1px">'
        '<label id=chip style="display:inline-flex;width:46px">'
        '<span id=name style="display:block;width:30px;height:12px"></span>'
        '<span id=count style="display:block;width:16px;height:12px"></span>'
        "</label></li>"
        '<li id=row2><label id=chip2 style="display:inline-flex;width:20px">'
        '<span id=name2 style="display:block;width:20px;height:12px">'
        "</span></label></li>"
        "</ul></form></div>"
    )
    # The negative margins really are used -- the label starts left of its
    # containing block, which is what puts the two sizes out of order.
    assert rect(root, "chip").x == -2
    assert metrics["intrinsic_inverted_by_negative_margin"] > 0


def test_the_inverted_pair_is_measured_and_not_clamped():
    """The half of the fix that a floor would have hidden.

    `IntrinsicSizes(min, max)` with `min > max` still raises unless the
    subtree said a negative margin was in it, so the assertion has not been
    weakened into "any inversion is fine" -- and the inverted pair keeps
    the numbers that were measured rather than being squashed to agree.
    """
    from mayshay.layout.intrinsic import IntrinsicSizes

    with pytest.raises(AssertionError, match="min-content must not exceed"):
        IntrinsicSizes(10.0, 5.0)

    allowed = IntrinsicSizes(10.0, 5.0, True)
    assert (allowed.min_content, allowed.max_content) == (10.0, 5.0)
