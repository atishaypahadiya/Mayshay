"""Block layout -- Phase 3 Task C.

Every fixture here is **synthetic, from CSS 2.1 section 8.3.1's and section
10.3.3's own cases**, and every expected number was measured against
**Chrome 151.0.7922.174** over CDP before it was written down. The corpus is
not the instrument: Task B measured 28 anonymous-box sites in 8,593 elements
and would have passed any implementation, and margin collapsing is worse --
the common shape on a real page is two siblings with margins, and every
interesting rule is an edge case the corpus exercises once or not at all.
`test_the_corpus_barely_exercises_any_of_this` puts a number on that instead
of a hope.

Three test shapes are fixed rather than left open, because the shape of the
*wrong* test is already known on this project:

* **Margin signs.** A test using only positive margins passes under
  `max()`, under `sum()` when an operand is zero, and under several other
  wrong rules. Positive/positive, negative/negative and mixed, every time.
* **`margin: auto`.** The assertions are on the resulting `margin-left` and
  `margin-right` *values*, not on the box position. "Over-constrained,
  margin-right ignored" and "centred" are indistinguishable by position
  whenever the numbers coincide.
* **Percentages.** The containing block is 400x800, so resolving a vertical
  percentage against the height gives 80 where the right answer is 40. A
  400x400 container cannot tell the two rules apart.

Every barrier gets a **negative** test, because over-collapsing produces a
plausible, slightly-too-tight page that nothing else catches.

Where this engine and Chrome deliberately disagree, the test says so and
says why -- there are exactly three places, all of them deferred work with a
counter: an inline formatting context has no measured height until Task D,
out-of-flow boxes are not laid out at all, and CSS 2.1 section 17.6's rule
that margins do not apply to table-internal boxes is Task E's.
"""

from __future__ import annotations

import pytest

from mayshay.cssparse.cascade import style_document
from mayshay.cssparse.media import Viewport
from mayshay.dom.node import Element
from mayshay.htmlparse.treebuilder import parse
from mayshay.layout.block import (
    COUNTER_NAMES,
    COLLAPSE_BARRIERS,
    MarginGroup,
    layout_document,
)
from mayshay.layout.boxtree import build_box_tree

VIEWPORT = Viewport(1280, 1024)

# `html, body { margin: 0; padding: 0 }` on every fixture: the UA sheet gives
# `body` an 8px margin, which would shift every number below by 8 and make
# the Chrome comparison a comparison of two UA sheets.
RESET = "html,body{margin:0;padding:0}"


def laid_out(body, css="", viewport=VIEWPORT):
    """`(root box, metrics)` for one synthetic fixture.

    `viewport` matters more than it looks. Several tests below assert a
    *counter* rather than a geometry, and a `<div style="width:400px">`
    wrapper inside a 1280px body is itself over-constrained -- 0 + 400 + 0
    is not 1280, so its own `margin-right` is ignored and recomputed to 880,
    exactly as Chrome does. That is correct behaviour and it would make the
    counter assertions read the wrapper as well as the box under test, so
    those fixtures use a 400px viewport and no wrapper instead.
    """
    document = parse(f"<style>{RESET}{css}</style>{body}")
    style_document(document, [], viewport=viewport)
    root, _ = build_box_tree(document)
    metrics = layout_document(root, viewport)
    return root, metrics


# A viewport exactly as wide as the containing block the section 10.3.3
# fixtures want, so the box under test sits directly in `body` and no
# wrapper contributes to the counters.
NARROW = Viewport(400, 800)


def boxes(root):
    found = {}
    for box in root.walk():
        if box.origin == "element" and isinstance(box.node, Element):
            ident = box.node.attrs.get("id")
            if ident:
                found[ident] = box
    return found


def geometry(root, ident):
    box = boxes(root)[ident]
    assert box.geometry is not None, f"#{ident} was not laid out"
    return box.geometry


def top(root, ident):
    """The y of a box's **border** edge, in absolute document coordinates --
    the same edge `DOM.getBoxModel`'s border quad reports."""
    return geometry(root, ident).border.y


def bottom(root, ident):
    return geometry(root, ident).border.bottom


def gap(root, first, second):
    """The distance between one box's border-bottom and the next one's
    border-top: the collapsed margin, read off the geometry."""
    return top(root, second) - bottom(root, first)


# A 400px containing block, and two 20px-tall siblings around a middle box.
# This is section 8.3.1's own shape and most of the collapsing tests use it.
def between(middle, *, before="margin-bottom:30px", after="margin-top:30px"):
    return (
        '<div id=cb style="width:400px">'
        f'<div id=a style="height:20px;{before}"></div>'
        f"{middle}"
        f'<div id=b style="height:20px;{after}"></div>'
        "</div>"
    )


# --------------------------------------------------------------------------
# Width: CSS 2.1 section 10.3.3
# --------------------------------------------------------------------------
#
# Four cases that must disagree with each other. An implementation that
# always centres passes the first; one that always absorbs into
# `margin-right` passes the first and the fourth. Each asserts the resulting
# MARGIN VALUES, not the position.


def test_both_margins_auto_centres_the_box():
    root, metrics = laid_out(
        '<div id=c style="width:200px;margin:0 auto;height:10px"></div>',
        viewport=NARROW,
    )
    used = geometry(root, "c").used_margin
    assert (used.left, used.right) == (100.0, 100.0)
    assert geometry(root, "c").border.x == 100.0
    assert metrics["width_margins_centred"] == 1
    assert metrics["width_over_constrained_margin_right_ignored"] == 0


def test_one_auto_margin_absorbs_the_whole_remainder():
    """`margin-left: auto; margin-right: 50px` puts 150 on the left, not 100
    on each side. Both directions, because a resolver that always fed the
    remainder to `margin-right` would pass the left-auto case by accident if
    only one were tested."""
    root, metrics = laid_out(
        '<div style="width:400px">'
        '<div id=l style="width:200px;margin-left:auto;margin-right:50px;'
        'height:10px"></div>'
        '<div id=r style="width:200px;margin-left:50px;margin-right:auto;'
        'height:10px"></div></div>'
    )
    left = geometry(root, "l").used_margin
    assert (left.left, left.right) == (150.0, 50.0)
    right = geometry(root, "r").used_margin
    assert (right.left, right.right) == (50.0, 150.0)
    assert metrics["width_margin_left_auto"] == 1
    assert metrics["width_margin_right_auto"] == 1
    assert metrics["width_margins_centred"] == 0


def test_auto_width_absorbs_and_auto_margins_become_zero():
    """`margin: 0 auto` with no width centres nothing -- the width takes the
    whole containing block and both margins are 0. This is the case that
    surprises people, and it is a different outcome from the first test with
    the same `margin` declaration."""
    root, metrics = laid_out(
        '<div style="width:400px">'
        '<div id=c style="margin:0 auto;height:10px"></div></div>'
    )
    geo = geometry(root, "c")
    assert geo.content.width == 400.0
    assert (geo.used_margin.left, geo.used_margin.right) == (0.0, 0.0)
    assert geo.border.x == 0.0
    assert metrics["width_auto_absorbed_remainder"] >= 1
    assert metrics["width_margins_centred"] == 0


def test_over_constrained_ignores_margin_right_not_margin_left():
    """None of `width`, `margin-left`, `margin-right` is `auto` and they do
    not add up: CSS 2.1 section 10.3.3 resolves it by **ignoring
    `margin-right`** in a left-to-right containing block. Not by scaling
    both, and not by ignoring `margin-left`.

    The margin values are what discriminates. By position this box sits at
    x=50, and so would a box whose `margin-left` had been ignored and
    recomputed to 50 -- which is why the position alone proves nothing.
    """
    root, metrics = laid_out(
        '<div id=c style="width:200px;margin-left:50px;margin-right:50px;'
        'height:10px"></div>',
        viewport=NARROW,
    )
    used = geometry(root, "c").used_margin
    assert used.left == 50.0, "margin-left is the one that survives"
    assert used.right == 150.0, "margin-right is ignored and recomputed"
    assert geometry(root, "c").border.x == 50.0
    assert metrics["width_over_constrained_margin_right_ignored"] == 1
    assert metrics["width_margins_centred"] == 0


def test_a_balanced_equation_is_not_counted_as_over_constrained():
    """The negative half of the test above. `50 + 200 + 150 == 400` already
    balances, so nothing is ignored and the counter stays at zero -- which
    is what stops `width_over_constrained_margin_right_ignored` from
    counting every box on the page."""
    root, metrics = laid_out(
        '<div id=c style="width:200px;margin-left:50px;margin-right:150px;'
        'height:10px"></div>',
        viewport=NARROW,
    )
    used = geometry(root, "c").used_margin
    assert (used.left, used.right) == (50.0, 150.0)
    assert metrics["width_over_constrained_margin_right_ignored"] == 0


def test_auto_margins_are_zeroed_when_the_box_overflows_its_container():
    """Section 10.3.3's easily-missed sentence: when `width` is not `auto`
    and the box is already wider than its containing block, `auto` margins
    are treated as **zero** -- which then makes the equation over-constrained
    and sends it through the margin-right branch.

    Chrome 151 agrees, and the two candidate rules give different answers: a
    500px box centred in 400px would be at x=-50 with margins of -50 each;
    the right answer is x=0, margin-left 0, margin-right -100.
    """
    root, metrics = laid_out(
        '<div style="width:400px">'
        '<div id=c style="width:500px;margin:0 auto;height:10px"></div></div>'
    )
    geo = geometry(root, "c")
    assert (geo.used_margin.left, geo.used_margin.right) == (0.0, -100.0)
    assert geo.border.x == 0.0
    assert geo.border.width == 500.0
    assert metrics["width_auto_margins_zeroed_by_overflow"] == 1
    assert metrics["width_margins_centred"] == 0


def test_auto_width_takes_the_remainder_after_fixed_margins():
    root, _ = laid_out(
        '<div style="width:400px">'
        '<div id=c style="margin-left:30px;margin-right:70px;height:10px">'
        "</div></div>"
    )
    geo = geometry(root, "c")
    assert geo.content.width == 300.0
    assert geo.border.x == 30.0


def test_a_negative_margin_left_moves_the_box_out_of_its_container():
    root, _ = laid_out(
        '<div style="width:400px">'
        '<div id=c style="width:200px;margin-left:-50px;height:10px"></div></div>'
    )
    geo = geometry(root, "c")
    assert geo.border.x == -50.0
    assert geo.used_margin.left == -50.0
    # Over-constrained again, so margin-right absorbs: -50 + 200 + 250 == 400.
    assert geo.used_margin.right == 250.0


def test_block_level_auto_width_does_not_wait_for_text_measurement():
    """A block-level `width: auto` resolves here, from the constraint
    equation, and has nothing to do with content. Measured against Chrome
    151 in a 600px containing block: two characters of text give 600.00, and
    forty-seven give 600.00.

    A block-level box still carrying a symbolic width when Task C finishes
    would be a defect, not a handoff, so this asserts a float rather than
    "not AUTO".
    """
    root, _ = laid_out(
        '<div style="width:600px">'
        '<div id=short>ab</div>'
        '<div id=long>abcdefghijklmnopqrstuvwxyzabcdefghijklmnopqrstu</div>'
        "</div>"
    )
    assert geometry(root, "short").content.width == 600.0
    assert geometry(root, "long").content.width == 600.0


def test_percentage_widths_resolve_against_the_containing_block_and_nest():
    root, _ = laid_out(
        '<div id=cb style="width:400px">'
        '<div id=p style="width:50%"><div id=c style="width:50%;height:10px">'
        "</div></div></div>"
    )
    assert geometry(root, "p").content.width == 200.0
    assert geometry(root, "c").content.width == 100.0


# --------------------------------------------------------------------------
# box-sizing
# --------------------------------------------------------------------------


def test_border_box_sizing_subtracts_padding_and_border_from_the_width():
    root, metrics = laid_out(
        '<div style="width:400px">'
        '<div id=c style="box-sizing:border-box;width:200px;padding:10px;'
        'border:5px solid;height:80px"></div></div>'
    )
    geo = geometry(root, "c")
    assert geo.border.width == 200.0
    assert geo.content.width == 170.0
    assert geo.border.height == 80.0
    assert geo.content.height == 50.0
    assert metrics["box_sizing_border_box"] == 1


def test_content_box_sizing_is_the_default_and_gives_a_different_answer():
    """The negative half: the same declarations without `box-sizing` give a
    230px border box, not a 200px one. Without this pair, an implementation
    that ignored `box-sizing` entirely would still pass a single assertion
    on the content width."""
    root, metrics = laid_out(
        '<div style="width:400px">'
        '<div id=c style="width:200px;padding:10px;border:5px solid;'
        'height:80px"></div></div>'
    )
    geo = geometry(root, "c")
    assert geo.content.width == 200.0
    assert geo.border.width == 230.0
    assert geo.border.height == 110.0
    assert metrics["box_sizing_border_box"] == 0


def test_a_border_box_width_smaller_than_its_own_edges_clamps_to_zero():
    """`width: 10px` with 20px of padding and 10px of border cannot be
    honoured; the content width is 0 and the border box is 30. Chrome 151
    reports 30 x 30 for exactly this box."""
    root, metrics = laid_out(
        '<div style="width:400px">'
        '<div id=c style="box-sizing:border-box;width:10px;padding:10px;'
        'border:5px solid;height:5px"></div></div>'
    )
    geo = geometry(root, "c")
    assert geo.content.width == 0.0
    assert geo.border.width == 30.0
    assert geo.border.height == 30.0
    assert metrics["width_clamped_to_zero"] == 1


# --------------------------------------------------------------------------
# Percentages resolve against the containing block's WIDTH
# --------------------------------------------------------------------------


def test_a_vertical_percentage_margin_resolves_against_the_width():
    """400x800 on purpose. `margin-top: 10%` is 40px -- ten percent of the
    *width* -- and the wrong rule gives 80. A 400x400 containing block
    cannot distinguish the two, which is the non-discriminating-test shape
    this project keeps meeting.

    Measured against Chrome 151 via `DOM.getBoxModel` rather than derived
    from the spec text.
    """
    root, _ = laid_out(
        '<div id=cb style="width:400px;height:800px">'
        '<div id=c style="height:20px;margin-top:10%"></div></div>'
    )
    assert geometry(root, "c").used_margin.top == 40.0
    assert geometry(root, "c").used_margin.top != 80.0


def test_every_side_of_margin_and_padding_uses_the_width():
    """The rule is a class, not one property: all four margins and all four
    paddings resolve against the containing block's width. Fixing the one
    property that raised the question and leaving the rest is the defect
    shape `docs/percentage-resolution.md` names."""
    root, _ = laid_out(
        '<div id=cb style="width:400px;height:800px">'
        '<div id=c style="height:20px;margin:10%;padding:5%"></div></div>'
    )
    geo = geometry(root, "c")
    assert (
        geo.used_margin.top,
        geo.used_margin.right,
        geo.used_margin.bottom,
        geo.used_margin.left,
    ) == (40.0, 40.0, 40.0, 40.0)
    assert (
        geo.used_padding.top,
        geo.used_padding.right,
        geo.used_padding.bottom,
        geo.used_padding.left,
    ) == (20.0, 20.0, 20.0, 20.0)


# --------------------------------------------------------------------------
# Height: CSS 2.1 section 10.6.3
# --------------------------------------------------------------------------


def test_auto_height_comes_from_the_in_flow_children():
    """Chrome 151 on this exact markup: the parent is 90 tall -- 2 border +
    3 padding + 10 collapsed margin + 20 + 10 + 30 + 10 + 3 + 2 -- and the
    children are 390 wide and at x=5."""
    root, metrics = laid_out(
        '<div id=cb style="width:400px">'
        '<div id=p style="border:2px solid;padding:3px">'
        '<div id=c1 style="height:20px;margin:10px 0"></div>'
        '<div id=c2 style="height:30px;margin:10px 0"></div></div></div>'
    )
    assert geometry(root, "p").border.height == 90.0
    assert geometry(root, "c1").border.x == 5.0
    assert geometry(root, "c1").border.width == 390.0
    assert top(root, "c1") == 15.0
    assert top(root, "c2") == 45.0
    assert metrics["heights_from_children"] >= 1


def test_a_percentage_height_resolves_against_a_definite_containing_block():
    root, metrics = laid_out(
        '<div id=cb style="width:400px;height:800px">'
        '<div id=c style="width:50%;height:25%"></div></div>'
    )
    assert geometry(root, "c").content.height == 200.0
    assert metrics["heights_percentage_fallback_auto"] == 0


def test_a_percentage_height_falls_back_to_auto_when_the_parent_is_auto():
    """The negative half. Chrome 151 gives 0 for `height: 25%` inside an
    auto-height parent -- the percentage does not resolve against the
    viewport, and it does not resolve against the parent's eventual
    content height either."""
    root, metrics = laid_out(
        '<div id=cb style="width:400px">'
        '<div id=c style="width:50%;height:25%"></div></div>'
    )
    assert geometry(root, "c").content.height == 0.0
    assert metrics["heights_percentage_fallback_auto"] == 1


# --------------------------------------------------------------------------
# Margin collapsing: the sign rules
# --------------------------------------------------------------------------


def test_two_positive_margins_collapse_to_the_larger():
    root, metrics = laid_out(
        '<div style="width:400px">'
        '<div id=a style="height:20px;margin-bottom:30px"></div>'
        '<div id=b style="height:20px;margin-top:10px"></div></div>'
    )
    assert gap(root, "a", "b") == 30.0
    assert metrics["margins_collapsed"] >= 1


def test_two_negative_margins_collapse_to_the_most_negative():
    """Chrome 151: `margin-bottom: -30px` above `margin-top: -10px` puts the
    second box at y=-10, which is 20 (the first box's bottom) minus 30. Not
    -40, which is what a sum would give, and not -10, which is what a
    max-of-absolute-values would give."""
    root, _ = laid_out(
        '<div style="width:400px">'
        '<div id=a style="height:20px;margin-bottom:-30px"></div>'
        '<div id=b style="height:20px;margin-top:-10px"></div></div>'
    )
    assert gap(root, "a", "b") == -30.0
    assert top(root, "b") == -10.0


def test_a_positive_and_a_negative_margin_collapse_to_their_sum():
    """The case that separates the rule from `max()`. 30 and -10 give 20 --
    not 30, which is what `max()` gives, and not -10."""
    root, _ = laid_out(
        '<div style="width:400px">'
        '<div id=a style="height:20px;margin-bottom:30px"></div>'
        '<div id=b style="height:20px;margin-top:-10px"></div></div>'
    )
    assert gap(root, "a", "b") == 20.0
    assert top(root, "b") == 40.0


def test_three_or_more_margins_are_max_positive_plus_min_negative():
    """An empty box between the two siblings puts four margins in one group:
    30, -10, -10 and 20. `max(30, 20) + min(-10) == 20`."""
    root, _ = laid_out(between('<div id=m style="margin:-10px 0"></div>',
                               after="margin-top:20px"))
    assert gap(root, "a", "b") == 20.0
    assert top(root, "m") == 40.0


def test_the_sign_rules_hold_on_the_group_itself():
    """The same three cases against `MarginGroup` directly, so a failure
    points at the rule rather than at the layout that used it."""
    for margins, expected in (
        ((30.0, 10.0), 30.0),
        ((-30.0, -10.0), -30.0),
        ((30.0, -10.0), 20.0),
        ((30.0, 20.0, -10.0, -5.0), 20.0),
        ((0.0, 0.0), 0.0),
    ):
        group = MarginGroup()
        for margin in margins:
            group.add(margin)
        assert group.value() == expected, margins


# --------------------------------------------------------------------------
# Margin collapsing: the four adjoining rules
# --------------------------------------------------------------------------


def test_a_parents_top_margin_collapses_with_its_first_childs():
    """The collapsed margin lands **outside** the parent, so the parent
    moves: Chrome 151 puts both the parent and the child at y=40, with
    `max(10, 40)` above them."""
    root, _ = laid_out(
        '<div style="width:400px"><div id=p style="margin-top:10px">'
        '<div id=c style="height:20px;margin-top:40px"></div></div></div>'
    )
    assert top(root, "p") == 40.0
    assert top(root, "c") == 40.0
    assert geometry(root, "p").border.height == 20.0


def test_a_parents_bottom_margin_collapses_with_its_last_childs():
    """Same at the bottom, and the parent's height excludes the escaping
    margin: Chrome 151 gives the parent a height of 20 and puts the next
    sibling at 60, which is 20 + max(40, 10)."""
    root, _ = laid_out(
        '<div style="width:400px"><div id=p style="margin-bottom:10px">'
        '<div id=c style="height:20px;margin-bottom:40px"></div></div>'
        '<div id=n style="height:20px"></div></div>'
    )
    assert geometry(root, "p").border.height == 20.0
    assert top(root, "n") == 60.0


def test_a_parent_and_child_collapse_at_both_ends_at_once():
    """Chrome 151, in one fixture, with content either side so both
    directions are visible: the parent's 20px margins both lose to the
    child's 50s, the parent lands at 60 and the box after it at 130."""
    root, _ = laid_out(
        '<div style="width:400px"><div id=x style="height:10px"></div>'
        '<div id=p style="margin:20px 0">'
        '<div id=c style="height:20px;margin:50px 0"></div></div>'
        '<div id=y style="height:10px"></div></div>'
    )
    assert top(root, "p") == 60.0
    assert top(root, "c") == 60.0
    assert top(root, "y") == 130.0


def test_an_empty_block_collapses_through_itself():
    """Section 8.3.1's fourth rule and the one most implementations miss.
    The empty box's own 40px margins join the siblings' 30s in a single
    group, so the gap is 40 -- not 30 + 40, and not 40 + 40."""
    root, metrics = laid_out(between('<div id=m style="margin:10%"></div>'))
    assert gap(root, "a", "b") == 40.0
    assert geometry(root, "m").border.height == 0.0
    assert metrics["margins_collapsed_through_empty"] == 1


def test_collapse_through_ignores_the_boxs_own_margins():
    """Measured against Chrome 151, and it corrects the obvious assumption:
    **no declared margin, `margin: 0` and `margin: 0%` behave identically**.
    Section 8.3.1's collapse-through condition names borders, padding,
    height and line boxes -- not the box's own margins -- so a zero margin
    does not make a block non-empty.

    Three empty boxes in a row here, and the gap stays 30. An implementation
    that treated a declared zero margin as content would give 30 + 0 + 0 +
    0 + 30 for at least two of them.
    """
    root, metrics = laid_out(
        between(
            '<div id=m1></div><div id=m2 style="margin:0"></div>'
            '<div id=m3 style="margin:0%"></div>'
        )
    )
    assert gap(root, "a", "b") == 30.0
    assert top(root, "m1") == top(root, "m2") == top(root, "m3") == 50.0
    assert metrics["margins_collapsed_through_empty"] == 3


def test_collapse_through_chains_across_several_empty_blocks():
    """Three empty boxes between two siblings collapse to a **single**
    margin, and each one's border edge sits at the group's value as it
    stands when that box is reached.

    The margins increase on purpose -- 5, then 10, 20, 30, then 8. Chrome
    151 puts the three empty boxes at 30, 40 and 50, not all at the final
    50: the position of a collapsed-through box uses the margins up to and
    including its own, which is section 8.3.1's "as it would have been if
    the element had a non-zero bottom border". A chain that placed them all
    at the same y would pass a test written with equal margins.
    """
    root, metrics = laid_out(
        '<div style="width:400px">'
        '<div id=a style="height:20px;margin-bottom:5px"></div>'
        '<div id=m1 style="margin:10px 0"></div>'
        '<div id=m2 style="margin:20px 0"></div>'
        '<div id=m3 style="margin:30px 0"></div>'
        '<div id=b style="height:20px;margin-top:8px"></div></div>'
    )
    assert (top(root, "m1"), top(root, "m2"), top(root, "m3")) == (30.0, 40.0, 50.0)
    assert top(root, "b") == 50.0
    assert gap(root, "a", "b") == 30.0
    assert metrics["margins_collapsed_through_empty"] == 3


def test_collapse_through_chains_through_nesting_as_well_as_sequence():
    """An empty box inside an empty box: Chrome 151 puts both at 65, which
    is 20 + max(30, 15, 45). The chain is not only between siblings."""
    root, metrics = laid_out(
        between(
            '<div id=o style="margin:15px 0">'
            '<div id=i style="margin:45px 0"></div></div>',
            after="margin-top:20px",
        )
    )
    assert top(root, "o") == top(root, "i") == 65.0
    assert top(root, "b") == 65.0
    assert metrics["margins_collapsed_through_empty"] == 2


def test_an_explicit_zero_height_still_collapses_through():
    """Section 8.3.1 says "zero or auto" height, and Chrome 151 agrees: an
    empty box with `height: 0` and 40px margins between two 30px siblings
    still gives a 40px gap.

    This one caught a real defect in this module: the flag that closes the
    bottom edge for rule 3 (which needs `height: auto`) had been reused for
    collapse-through (which accepts a zero height too), and the gap came out
    as 80.
    """
    root, metrics = laid_out(
        between('<div id=m style="margin:40px 0;height:0"></div>')
    )
    assert gap(root, "a", "b") == 40.0
    assert top(root, "b") == 60.0
    assert metrics["margins_collapsed_through_empty"] == 1


# --------------------------------------------------------------------------
# The barriers -- every one with a negative test
# --------------------------------------------------------------------------
#
# Over-collapsing produces a plausible, slightly-too-tight page. Only a
# negative test catches it, so each barrier is asserted to STOP a collapse
# that the paired positive test shows happening.


@pytest.mark.parametrize(
    "declaration,counter",
    [
        ("padding-top:1px", "margin_collapse_blocked_padding_top"),
        ("border-top:1px solid", "margin_collapse_blocked_border_top"),
    ],
)
def test_padding_or_border_blocks_the_parent_first_child_collapse(
    declaration, counter
):
    """Even 1px. Chrome 151: the parent stays at its own 10px margin and is
    61 tall (1 + 40 + 20), and the child sits at 51.

    The positive case is `test_a_parents_top_margin_collapses_with_its_first_childs`
    above, where the same markup without the 1px puts both at 40.
    """
    root, metrics = laid_out(
        f'<div style="width:400px"><div id=p style="margin-top:10px;{declaration}">'
        '<div id=c style="height:20px;margin-top:40px"></div></div></div>'
    )
    assert top(root, "p") == 10.0, "the parent did not move: no collapse"
    assert top(root, "c") == 51.0
    assert geometry(root, "p").border.height == 61.0
    assert metrics[counter] == 1


@pytest.mark.parametrize(
    "declaration,counter",
    [
        ("padding-bottom:1px", "margin_collapse_blocked_padding_bottom"),
        ("height:60px", "margin_collapse_blocked_parent_height"),
    ],
)
def test_padding_or_a_fixed_height_blocks_the_parent_last_child_collapse(
    declaration, counter
):
    """Rule 3 applies only when the parent's height is `auto`. Chrome 151
    puts the following sibling at 71 with the 1px padding and at 70 with the
    fixed height; the positive case above puts it at 60."""
    markup = (
        '<div style="width:400px"><div id=p style="margin-bottom:10px;{extra}">'
        '<div id=c style="height:20px;margin-bottom:40px"></div></div>'
        '<div id=n style="height:20px"></div></div>'
    )
    root, metrics = laid_out(markup.format(extra=declaration))
    assert top(root, "n") != 60.0, "the child's 40px margin escaped the parent"
    assert top(root, "n") == (71.0 if "padding" in declaration else 70.0)

    # Asserted as a *delta* against the same fixture without the barrier.
    # The absolute count is a page-wide number -- every box with a fixed
    # height closes its own bottom edge to collapse-through, so `#c` and
    # `#n` contribute to `margin_collapse_blocked_parent_height` too -- and
    # only the delta is a statement about the barrier under test.
    _, baseline = laid_out(markup.format(extra=""))
    assert metrics[counter] == baseline[counter] + 1


@pytest.mark.parametrize(
    "declaration",
    ["overflow:hidden", "overflow:auto", "overflow:scroll", "display:flex"],
)
def test_a_new_formatting_context_blocks_the_parent_child_collapse(declaration):
    """`overflow` other than `visible`, and the non-block inner displays,
    establish a new block formatting context: the child's margin does not
    escape. Chrome 151 puts the parent at 10 and the child at 50, and the
    parent is 60 tall because the 40px margin is now *inside* it.

    The negative half is the same markup with the declaration removed, which
    the parent/first-child test above shows collapsing to 40.
    """
    root, metrics = laid_out(
        f'<div style="width:400px"><div id=p style="margin-top:10px;{declaration}">'
        '<div id=c style="height:20px;margin-top:40px"></div></div></div>'
    )
    assert top(root, "p") == 10.0
    assert top(root, "c") == 50.0
    assert geometry(root, "p").border.height == 60.0
    assert metrics["margin_collapse_blocked_new_formatting_context"] == 2


def test_overflow_visible_is_not_a_barrier():
    """The negative test for the negative test: `overflow: visible` is the
    initial value and must not establish anything. Without this, a barrier
    keyed on "the property was declared" rather than on its value would pass
    the four cases above."""
    root, metrics = laid_out(
        '<div style="width:400px">'
        '<div id=p style="margin-top:10px;overflow:visible">'
        '<div id=c style="height:20px;margin-top:40px"></div></div></div>'
    )
    assert top(root, "p") == 40.0
    assert metrics["margin_collapse_blocked_new_formatting_context"] == 0


def test_the_root_elements_margins_never_collapse():
    """`html` has a 20px top margin, `body` a 30px one, and the `div` inside
    5px. Chrome 151 puts the div at 50: the root's 20 does **not** collapse
    with the body's 30, so they add; the body's 30 and the div's 5 do
    collapse, to 30.

    A layout that collapsed everything would put the div at 30, and one that
    collapsed nothing would put it at 55. Both are plausible page-shaped
    answers.
    """
    root, metrics = laid_out(
        '<div id=c style="height:20px;margin-top:5px"></div>',
        css="html{margin-top:20px}body{margin-top:30px}",
    )
    assert top(root, "c") == 50.0
    assert metrics["margin_collapse_blocked_root"] == 2


def test_an_out_of_flow_sibling_never_joins_the_collapsing_group():
    """A float and an absolutely positioned box are out of flow: their
    margins never collapse with an in-flow sibling's and never contribute to
    the flow. Chrome 151 leaves the gap at 30 despite the 100px margin in
    the middle.

    Deliberate divergence from Chrome: neither box is laid out here at all
    -- floats and absolute positioning are Phase 3's named deferrals -- so
    they carry no geometry and are counted instead. The in-flow numbers are
    the ones being asserted, and they match.
    """
    for declaration, counter in (
        ("float:left;width:50px", "layout_float_skipped"),
        ("position:absolute", "layout_absolute_skipped"),
    ):
        root, metrics = laid_out(
            '<div style="width:400px">'
            '<div id=a style="height:20px;margin-bottom:30px"></div>'
            f'<div id=x style="{declaration};height:10px;margin-top:100px"></div>'
            '<div id=b style="height:20px;margin-top:10px"></div></div>'
        )
        assert gap(root, "a", "b") == 30.0, declaration
        assert boxes(root)["x"].geometry is None
        assert metrics[counter] == 1
        assert metrics["margin_collapse_blocked_out_of_flow"] == 1
        # Task D1 resolves the *width* of an out-of-flow box and still
        # refuses to place it, which is why the geometry above is None
        # while this counter has moved out of the deferred bucket.
        assert metrics["widths_shrink_to_fit_resolved"] == 1
        assert metrics["widths_deferred_shrink_to_fit"] == 0
        assert boxes(root)["x"].shrink_to_fit_width is not None


def test_an_in_flow_sibling_with_the_same_margin_does_join_it():
    """The negative half of the out-of-flow test: remove `float`/`position`
    and the 100px margin does reach the group, moving the gap from 30 to
    100. Without this, an implementation that dropped *every* middle sibling
    would pass the test above."""
    root, metrics = laid_out(
        '<div style="width:400px">'
        '<div id=a style="height:20px;margin-bottom:30px"></div>'
        '<div id=x style="height:10px;margin-top:100px"></div>'
        '<div id=b style="height:20px;margin-top:10px"></div></div>'
    )
    assert top(root, "x") == 120.0
    assert metrics["margin_collapse_blocked_out_of_flow"] == 0
    assert metrics["layout_float_skipped"] == 0


def test_clear_alone_is_not_a_barrier_when_there_is_no_float():
    """The Task C plan lists `clear` among the barriers. Measured against
    Chrome 151, that is only true when there is a float to clear:
    **clearance**, not the `clear` property, is what separates the margins.

    With no float in the fixture, `clear: both` collapses exactly like any
    other sibling -- gap 30, not 40 -- and Chrome agrees. With a 60px-tall
    float above them Chrome moves the box to y=60 instead of y=50, which is
    clearance; floats are not implemented here, so no clearance is ever
    generated and treating `clear` as an unconditional barrier would make
    this engine disagree with a browser on the common case in order to agree
    with it on a case it cannot reach.

    `clear` is therefore parsed, cascaded, and deliberately not acted on.
    """
    markup = (
        '<div style="width:400px">'
        '<div id=a style="height:20px;margin-bottom:30px"></div>'
        '<div id=b style="{extra}height:20px;margin-top:10px"></div></div>'
    )
    root, metrics = laid_out(markup.format(extra="clear:both;"))
    assert gap(root, "a", "b") == 30.0
    assert top(root, "b") == 50.0
    assert metrics["margins_collapsed"] >= 1

    # Byte-for-byte the same geometry and the same barrier counts as the
    # fixture without `clear`, which is the strongest form of "it changed
    # nothing".
    plain, baseline = laid_out(markup.format(extra=""))
    assert top(plain, "b") == top(root, "b")
    for reason in COLLAPSE_BARRIERS:
        key = f"margin_collapse_blocked_{reason}"
        assert metrics[key] == baseline[key], reason


def test_line_boxes_block_collapse_through_and_whitespace_does_not():
    """Section 8.3.1's collapse-through condition names *in-flow line
    boxes*, and white space that collapses away produces none.

    Both halves measured against Chrome 151. The whitespace-only box
    collapses through and the gap stays 40, with the box itself 0 tall. The
    box with real text does not: Chrome puts it at 60, 20 tall, and the
    following sibling at 120.

    Deliberate divergence, and the only one in this fixture: this engine has
    no measured line-box height until Task D, so the middle box is 0 tall
    here and the following sibling lands at 100 rather than 120. The
    *barrier* is what is being asserted -- the box did not collapse through,
    so its two 40px margins stayed separate and the total is 40 + 0 + 40
    rather than 40.
    """
    empty, metrics_empty = laid_out(
        between('<div id=m style="margin:40px 0">   </div>')
    )
    assert gap(empty, "a", "b") == 40.0
    assert geometry(empty, "m").border.height == 0.0
    assert metrics_empty["margins_collapsed_through_empty"] == 1
    assert metrics_empty["margin_collapse_blocked_line_box"] == 0

    filled, metrics_filled = laid_out(
        between('<div id=m style="margin:40px 0">x</div>')
    )
    assert top(filled, "m") == 60.0
    assert top(filled, "b") == 100.0
    assert metrics_filled["margins_collapsed_through_empty"] == 0
    assert metrics_filled["margin_collapse_blocked_line_box"] == 1
    assert metrics_filled["heights_deferred_inline_content"] >= 1


def test_an_atomic_inline_child_blocks_collapse_through_too():
    """An `inline-block` inside the middle box is inline content, so the box
    has a line box and cannot collapse through. Chrome 151 agrees; the same
    Task D height caveat as above applies to the absolute numbers, and the
    barrier is what is asserted.

    The `inline-block`'s own width is shrink-to-fit and is deferred rather
    than guessed -- `layout/intrinsic.py` names the seam.
    """
    root, metrics = laid_out(
        between(
            '<div id=m style="margin:40px 0">'
            '<span id=ib style="display:inline-block;width:10px;height:10px">'
            "</span></div>"
        )
    )
    assert metrics["margins_collapsed_through_empty"] == 0
    assert metrics["margin_collapse_blocked_line_box"] == 1
    assert boxes(root)["ib"].geometry is None
    assert metrics["widths_shrink_to_fit_resolved"] == 1
    assert metrics["widths_deferred_shrink_to_fit"] == 0
    # `width: 10px` is specified, so shrink-to-fit does not run: the
    # formula is what `width: auto` means on these boxes, not what they
    # always do.
    assert boxes(root)["ib"].shrink_to_fit_width == 10.0
    assert metrics["widths_shrink_to_fit_specified"] == 1


def test_a_table_internal_box_keeps_the_barrier_and_records_the_deviation():
    """`display: table-cell` establishes a formatting context, so the
    child's margin does not escape -- asserted, and matching Chrome.

    CSS 2.1 section 17.6 also says the margin properties do not apply to
    table-internal boxes, which Task E owns: Chrome puts this cell at y=0
    and this engine puts it at y=10, having applied the 10px margin. That is
    the one place in this file where the two disagree on purpose, and it is
    counted rather than left as a surprise.
    """
    root, metrics = laid_out(
        '<div style="width:400px">'
        '<div id=p style="display:table-cell;margin-top:10px">'
        '<div id=c style="height:20px;margin-top:40px"></div></div></div>'
    )
    assert geometry(root, "p").border.height == 60.0, "the margin did not escape"
    assert top(root, "c") == 50.0
    assert metrics["margin_collapse_blocked_new_formatting_context"] == 2
    assert metrics["layout_table_box_margins_applied"] == 1
    assert top(root, "p") == 10.0  # Chrome: 0. See the docstring.


# --------------------------------------------------------------------------
# Percentage margins and collapse-through together
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "middle,expected_gap",
    [
        ('style="margin:10%"', 40.0),
        ('style="margin:0"', 30.0),
        ('style="margin:10%;padding:1px"', 82.0),
        ('style="margin:10%;height:1px"', 81.0),
    ],
)
def test_the_four_measured_collapse_through_cases(middle, expected_gap):
    """All four measured against Chrome 151 in a 400px container between two
    siblings with `margin: 30px 0`. The last two are the negative cases and
    they are what catch an implementation that collapses through everything:
    1px of padding turns 40 into 40 + 2 + 40, and 1px of height turns it
    into 40 + 1 + 40.

    Each needs the percentage resolution and the collapse-through chain to
    be right at the same time, which is why the percentage form is used
    rather than a plain `40px`.
    """
    root, _ = laid_out(between(f"<div id=m {middle}></div>"))
    assert gap(root, "a", "b") == expected_gap


@pytest.mark.parametrize(
    "declaration,counter",
    [
        ("border-top:1px solid", "margin_collapse_blocked_border_top"),
        ("border-bottom:1px solid", "margin_collapse_blocked_border_bottom"),
        ("padding-top:1px", "margin_collapse_blocked_padding_top"),
        ("padding-bottom:1px", "margin_collapse_blocked_padding_bottom"),
    ],
)
def test_one_pixel_on_any_single_edge_stops_collapse_through(
    declaration, counter
):
    """All four edges, separately. Chrome 151 gives the same 81px gap for
    every one of them -- 40 + 1 + 40 -- against the 40 the same box gives
    with no edge at all.

    Four cases rather than one because the four are four separate places to
    forget. An injection that dropped only the `border-bottom` branch was a
    **no-op** against the earlier version of this file, which tested the
    padding cases and the `border-top` case and nothing else: the defect was
    real and no test noticed. That is the whole argument for the injection
    table.
    """
    root, metrics = laid_out(
        between(f'<div id=m style="margin:10%;{declaration}"></div>')
    )
    assert gap(root, "a", "b") == 81.0
    assert top(root, "m") == 60.0
    assert geometry(root, "m").border.height == 1.0
    assert metrics["margins_collapsed_through_empty"] == 0
    assert metrics[counter] >= 1


# --------------------------------------------------------------------------
# The mechanical checks
# --------------------------------------------------------------------------


def test_the_constraint_equation_is_asserted_on_every_box():
    """`assert_layout_constraints` runs inside `layout_document`, so every
    test in this file has already exercised it. This one proves it can
    *fail*: a box whose margin rectangle is widened by hand no longer spans
    its containing block, and the assertion says so by name.

    Without this, an assertion that never fires is indistinguishable from
    one that cannot.
    """
    from mayshay.layout.block import Rect, assert_layout_constraints

    root, metrics = laid_out(
        '<div id=cb style="width:400px">'
        '<div id=c style="width:200px;margin:0 auto;height:10px"></div></div>'
    )
    assert_layout_constraints(
        root, initial_containing_block_width=1280.0, metrics=metrics
    )
    geo = geometry(root, "c")
    geo.margin = Rect(geo.margin.x, geo.margin.y, geo.margin.width + 1.0, geo.margin.height)
    with pytest.raises(AssertionError, match="margin box width"):
        assert_layout_constraints(
            root, initial_containing_block_width=1280.0, metrics=metrics
        )


def test_a_child_laid_out_against_the_wrong_containing_block_is_caught():
    """The equation is read off the rectangles and the containing block's
    width off the *parent's content rectangle*, not off the number stored on
    the child. Widening a parent's content box therefore breaks its
    children's equation while leaving the parent's own edge identities
    intact -- which is the defect shape the check exists for, and one that a
    version comparing each box against its own stored
    `containing_block_width` would agree with itself about and miss.

    The injection keeps the parent internally consistent on purpose: its
    content, padding and border boxes all grow by 100 and its own
    `margin-right` shrinks by 100, so every nesting identity still holds and
    only the child/parent relationship is wrong.
    """
    from mayshay.layout.block import Edges, Rect, assert_layout_constraints

    root, metrics = laid_out(
        '<div id=cb style="width:400px">'
        '<div id=c style="height:10px"></div></div>'
    )
    geo = geometry(root, "cb")
    for name in ("content", "padding", "border"):
        rect = getattr(geo, name)
        setattr(geo, name, Rect(rect.x, rect.y, rect.width + 100.0, rect.height))
    used = geo.used_margin
    geo.used_margin = Edges(used.top, used.right - 100.0, used.bottom, used.left)
    with pytest.raises(AssertionError, match="margin box width"):
        assert_layout_constraints(
            root, initial_containing_block_width=1280.0, metrics=metrics
        )


def test_every_box_is_laid_out_or_deferred_for_exactly_one_named_reason():
    """The box-disposition partition, in the shape of Task A2's
    `seen == kept + dropped`. A fixture with one of everything: a block, an
    inline formatting context, a float, an absolutely positioned box and an
    `inline-block`."""
    root, metrics = laid_out(
        '<div style="width:400px">'
        '<div id=a style="height:10px"></div>'
        "<div id=t>text <span>and more</span></div>"
        '<div id=f style="float:left;width:10px"></div>'
        '<div id=x style="position:absolute"></div>'
        '<div id=ib><span style="display:inline-block"></span></div>'
        "</div>"
    )
    parts = (
        metrics["widths_resolved"]
        + metrics["widths_shrink_to_fit_resolved"]
        + metrics["widths_deferred_shrink_to_fit"]
        + metrics["widths_not_applicable_inline_level"]
        + metrics["widths_deferred_other"]
        + metrics["layout_boxes_deferred_subtree"]
    )
    assert metrics["layout_boxes_seen"] == parts
    assert metrics["layout_boxes_seen"] == len(list(root.walk()))
    # The fourth bucket is where a box that fits none of the three named
    # categories lands. It is a measurement, not a judgement, and it should
    # read zero.
    assert metrics["widths_deferred_other"] == 0
    assert metrics["widths_shrink_to_fit_resolved"] == 3  # float, abs, inline-block
    assert metrics["widths_deferred_shrink_to_fit"] == 0


def test_the_geometry_records_whether_a_box_collapsed_through():
    """Recorded, not inferred. A box that collapsed through and a
    zero-height box a barrier stopped are indistinguishable from the outside
    -- both are empty rectangles of zero height -- and a census that guessed
    from the geometry counted 78 of them on the corpus where the layout had
    decided 58.

    Both halves here: the bare empty box collapsed through, the one with a
    single pixel of border did not, and they have the same zero content
    height.
    """
    root, _ = laid_out(
        between(
            '<div id=through style="margin:10px 0"></div>'
        )
    )
    assert geometry(root, "through").collapsed_through is True

    stopped, _ = laid_out(
        between('<div id=stopped style="margin:10px 0;border-top:1px solid"></div>')
    )
    assert geometry(stopped, "stopped").collapsed_through is False
    assert geometry(stopped, "stopped").content.height == 0.0


def test_a_whitespace_only_block_is_counted_as_inline_level_not_as_other():
    """A block container holding nothing but collapsible white space keeps
    its blank text children -- Task B leaves an all-inline child list alone
    -- correctly reports no line boxes, and then those children arrive in
    the block-flow loop. Seven of them on the corpus, and they were landing
    in `widths_deferred_other`, the bucket that is supposed to read zero.

    The box itself still collapses through, which is the behaviour Chrome
    shows for `<div style="margin:40px 0">   </div>`.
    """
    root, metrics = laid_out(between('<div id=m style="margin:40px 0">   </div>'))
    assert metrics["widths_deferred_other"] == 0
    assert metrics["widths_not_applicable_inline_level"] >= 1
    assert geometry(root, "m").collapsed_through is True
    assert gap(root, "a", "b") == 40.0


def test_every_margin_edge_joins_a_group_or_stands_alone():
    root, metrics = laid_out(
        between('<div id=m style="margin:10%"></div>')
    )
    assert metrics["margin_edges_seen"] == (
        metrics["margin_edges_collapsed"] + metrics["margin_edges_alone"]
    )
    # Two per laid-out block box, and nothing else contributes one.
    assert metrics["margin_edges_seen"] == 2 * metrics["widths_resolved"]


def test_every_vertical_edge_is_open_or_closed_for_one_reason():
    root, metrics = laid_out(
        '<div style="width:400px">'
        '<div id=p1 style="padding-top:1px"><div id=c1 style="height:10px">'
        "</div></div>"
        '<div id=p2 style="overflow:hidden"><div id=c2 style="height:10px">'
        "</div></div>"
        '<div id=p3><div id=c3 style="height:10px"></div></div></div>'
    )
    blocked = sum(
        metrics[f"margin_collapse_blocked_{reason}"] for reason in COLLAPSE_BARRIERS
    )
    assert metrics["collapse_barrier_edges_seen"] == (
        metrics["collapse_barrier_edges_open"] + blocked
    )
    assert metrics["collapse_barrier_edges_seen"] > 0


def test_every_counter_is_seeded_at_zero():
    """Absence and zero must stay distinguishable in the CSV: a page with no
    collapsing has to emit `margins_collapsed,0`, not no row."""
    _, metrics = laid_out('<div id=c style="height:10px"></div>')
    for name in COUNTER_NAMES:
        assert name in metrics, name
    assert metrics["margins_collapsed_through_empty"] == 0
    assert metrics["layout_float_skipped"] == 0


def test_an_empty_document_lays_out_to_seeded_zeroes():
    metrics = layout_document(None, VIEWPORT)
    assert set(COUNTER_NAMES) <= set(metrics)
    assert sum(metrics.values()) == 0


# --------------------------------------------------------------------------
# All four edges, in absolute document coordinates
# --------------------------------------------------------------------------


def test_boxes_carry_all_four_edges_in_absolute_document_coordinates():
    """The Phase 3 comparison contract: content, padding, border and margin,
    absolute, origin at the document's top-left, y increasing downward. The
    numbers are the plan's own worked example, re-measured against Chrome
    151 in a 460px containing block so the margin box fits exactly.
    """
    root, _ = laid_out(
        '<div style="width:460px">'
        '<div id=c style="margin:10px 20px;border:3px solid;padding:5px 7px;'
        'width:400px;height:50px"></div></div>'
    )
    geo = geometry(root, "c")
    assert (geo.content.x, geo.content.y, geo.content.width, geo.content.height) == (
        30.0, 18.0, 400.0, 50.0,
    )
    assert (geo.padding.x, geo.padding.y, geo.padding.width, geo.padding.height) == (
        23.0, 13.0, 414.0, 60.0,
    )
    assert (geo.border.x, geo.border.y, geo.border.width, geo.border.height) == (
        20.0, 10.0, 420.0, 66.0,
    )
    assert (geo.margin.x, geo.margin.y, geo.margin.width, geo.margin.height) == (
        0.0, 0.0, 460.0, 86.0,
    )


def test_absolute_coordinates_compose_through_nesting():
    """Relative coordinates that were never composed would look correct on a
    one-level fixture. Three levels, each offset, so a missing composition
    shows up as a small plausible number instead of the right one."""
    root, _ = laid_out(
        '<div id=l1 style="width:400px;padding:10px;margin-left:5px">'
        '<div id=l2 style="padding:10px">'
        '<div id=l3 style="height:10px"></div></div></div>'
    )
    assert geometry(root, "l1").content.x == 15.0
    assert geometry(root, "l2").content.x == 25.0
    assert geometry(root, "l3").border.x == 25.0
    assert geometry(root, "l3").border.y == 20.0


# --------------------------------------------------------------------------
# The corpus, as a smoke test and as a coverage number
# --------------------------------------------------------------------------


def test_every_corpus_page_lays_out_with_the_partitions_intact():
    """The corpus as a smoke test, which is all it can be here.

    Every constraint in `assert_layout_constraints` runs inside
    `layout_document`, so this exercises all three of them over real markup
    -- 12,581 boxes on Wikipedia alone -- rather than only over the
    synthetic fixtures above. What it cannot do is exercise the *rules*:
    `scripts/layout_report.py` reports the census, and at 1280x1024 with
    external sheets applied it says the three pages between them contain
    **zero** percentage vertical margins, **zero** adjacent sibling pairs
    with two negative margins, 9 with mixed signs, and 4 collapse-through
    chains of two or more. That is the coverage gap as a number.

    In-document CSS only here; the external sheets need the manifest
    ordering that `scripts/corpus.py` owns, and a test that reached into
    `scripts/` for it would be measuring the driver.
    """
    from pathlib import Path

    corpus = Path(__file__).resolve().parents[2] / "data" / "corpus"
    pages = sorted(corpus.glob("*/page.html"))
    if not pages:  # pragma: no cover - the corpus is committed
        pytest.skip("no collected corpus pages")
    for page in pages:
        document = parse(page.read_text(encoding="utf-8", errors="replace"))
        style_document(document, [], viewport=VIEWPORT)
        root, _ = build_box_tree(document)
        metrics = layout_document(root, VIEWPORT)
        assert metrics["layout_boxes_seen"] == len(list(root.walk())), page.parent.name
        assert metrics["widths_deferred_other"] == 0, page.parent.name
        assert metrics["margin_edges_seen"] == (
            metrics["margin_edges_collapsed"] + metrics["margin_edges_alone"]
        ), page.parent.name
