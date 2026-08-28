"""Intrinsic sizing and the inline formatting context -- Phase 3 Task D1.

**Every expected number here was measured against Chrome 151**, headless,
using `width: min-content` and `width: max-content` on identical markup with
`font-family: Arial`. Liberation Sans is metric-compatible with Arial, which
is the entire reason `docs/fonts.md` picked it, and Task D1 is the first
thing on this project to actually test that claim rather than assert it.

Chrome quantises layout to 1/64 px per separately shaped text run, so the
tolerance below is `runs / 64` and not a round number chosen to make things
pass. `<i>a</i> <i>b</i>` is three runs and legitimately differs by three of
them; `<div>alpha beta gamma</div>` is one run and agrees to the last bit.

The comparison caught a real defect that reading the spec did not: **there
is a soft wrap opportunity on both sides of an atomic inline.**
`a<span style="display:inline-block;width:40px"></span>b` has a min-content
width of 40.00 in Chrome, not 57.81. UAX #14 gives U+FFFC line-break class
CB and rule LB20 breaks either side of it. This engine had it wrong, the
number was plausible, and only the second measurement found it --
`test_an_atomic_inline_offers_a_wrap_opportunity_on_both_sides` is that
case, pinned.
"""

from __future__ import annotations

from collections import Counter

import pytest

from mayshay.cssparse.cascade import ComputedStyle, style_document
from mayshay.cssparse.media import Viewport
from mayshay.dom.node import Element
from mayshay.htmlparse.treebuilder import parse
from mayshay.layout import intrinsic as I
from mayshay.layout import text as T
from mayshay.layout.block import layout_document
from mayshay.layout.boxtree import build_box_tree

VIEWPORT = Viewport(1280, 1024)
RESET = "html,body{margin:0;padding:0}"

#: Chrome's LayoutUnit. See the module docstring: the budget is per
#: separately shaped run, so a fixture's tolerance is `runs * LAYOUT_UNIT`.
LAYOUT_UNIT = 1.0 / 64.0

LF = "\u000a"
NBSP = "\u00a0"


def laid_out(body, css=""):
    document = parse(f"<style>{RESET}{css}</style>{body}")
    style_document(document, [], viewport=VIEWPORT)
    root, _ = build_box_tree(document)
    metrics = layout_document(root, VIEWPORT)
    return root, metrics


def find(root, ident):
    for box in root.walk():
        if (
            box.origin == "element"
            and isinstance(box.node, Element)
            and box.node.attrs.get("id") == ident
        ):
            return box
    raise AssertionError(f"no box for #{ident}")


def sizes(body, ident="t", css=""):
    root, metrics = laid_out(body, css)
    return I.intrinsic_sizes(find(root, ident), metrics=metrics)


def advance(text, font_size=16):
    """The same number `measure()` produces, derived from the font units
    rather than by calling it -- so a fixture's expectation and the code
    under test do not share the multiply."""
    return T.advance_units(text) * font_size / 2048


# --------------------------------------------------------------------------
# The two sizes, against Chrome
# --------------------------------------------------------------------------


def test_min_content_is_the_widest_word_and_max_content_is_the_whole_run():
    """Chrome 151: min 53.3438, max 132.5313 for `alpha beta gamma`. One
    shaped run, so the tolerance is one LayoutUnit."""
    got = sizes("<div id=t>alpha beta gamma</div>")
    assert got.min_content == pytest.approx(53.3438, abs=LAYOUT_UNIT)
    assert got.max_content == pytest.approx(132.5313, abs=LAYOUT_UNIT)
    # And derived independently of Chrome, from the font units: the widest
    # word, and the whole collapsed run including its two spaces.
    assert got.min_content == pytest.approx(advance("gamma"), abs=1e-9)
    assert got.max_content == pytest.approx(advance("alpha beta gamma"), abs=1e-9)


def test_nowrap_makes_the_two_sizes_equal():
    """The single most consequential rule on this corpus: `nowrap` is on
    24% of element boxes and `pre` is on none, so an implementation that
    split on spaces regardless would be wrong 1,909 times and right about
    a case that never occurs. Chrome 151: min 132.5313, max 132.5313."""
    got = sizes('<div id=t style="white-space:nowrap">alpha beta gamma</div>')
    assert got.min_content == got.max_content
    assert got.min_content == pytest.approx(132.5313, abs=LAYOUT_UNIT)


def test_a_long_word_dominates_the_min_content_width():
    """Chrome 151: min 126.2656, max 139.6094. The negative of the first
    test -- here the widest word is the first, not the last, so an
    implementation that kept the wrong end of the run passes one and fails
    the other."""
    got = sizes("<div id=t>supercalifragilistic a</div>")
    assert got.min_content == pytest.approx(126.2656, abs=LAYOUT_UNIT)
    assert got.max_content == pytest.approx(139.6094, abs=LAYOUT_UNIT)


def test_a_forced_break_ends_the_line_for_max_content_too():
    """`pre-line` preserves the break and collapses the spaces, so
    max-content is the widest *line* rather than the whole text. Chrome
    151: min 53.3438, max 88.9375 -- and 88.9375 is `beta gamma`, not
    `alpha beta gamma`, which is what says the break was honoured."""
    got = sizes(
        '<div id=t style="white-space:pre-line">alpha' + LF + "beta gamma</div>"
    )
    assert got.min_content == pytest.approx(53.3438, abs=2 * LAYOUT_UNIT)
    assert got.max_content == pytest.approx(88.9375, abs=2 * LAYOUT_UNIT)
    assert got.max_content == pytest.approx(advance("beta gamma"), abs=1e-9)


def test_an_inline_boxs_padding_widens_the_run_it_sits_in():
    """No wrap opportunity at an inline box's edge, so its horizontal
    padding is part of the unbreakable run and both sizes carry it. Chrome
    151: min 44.7031, max 44.7031 for `<span style="padding:0 5px">ab</span>cd`."""
    got = sizes('<div id=t><span style="padding:0 5px">ab</span>cd</div>')
    assert got.min_content == got.max_content
    assert got.min_content == pytest.approx(44.7031, abs=2 * LAYOUT_UNIT)
    assert got.min_content == pytest.approx(advance("abcd") + 10.0, abs=1e-9)


def test_an_atomic_inline_offers_a_wrap_opportunity_on_both_sides():
    """The defect the Chrome comparison caught, pinned.

    `a<inline-block 40px>b` has a min-content width of **40**, not
    `a + 40 + b`. Reading CSS Text 3 suggests the opposite -- nothing
    separates the box from the letters -- and 57.80 is a perfectly
    plausible number. UAX #14 rule LB20 is the rule: an atomic inline is
    U+FFFC, line-break class CB, and CB breaks on both sides.

    Chrome 151: min 40.0000, max 57.8125.
    """
    body = (
        '<div id=t>a<span style="display:inline-block;width:40px">'
        "&nbsp;</span>b</div>"
    )
    got = sizes(body)
    assert got.min_content == pytest.approx(40.0, abs=3 * LAYOUT_UNIT)
    assert got.max_content == pytest.approx(57.8125, abs=3 * LAYOUT_UNIT)
    assert got.min_content < advance("a") + 40.0 + advance("b")


def test_nowrap_removes_the_atomic_inlines_wrap_opportunity_as_well():
    """The negative of the previous test. Under `nowrap` there is no soft
    wrap opportunity anywhere, so the letters and the box are one run and
    the two sizes coincide again."""
    body = (
        '<div id=t style="white-space:nowrap">a'
        '<span style="display:inline-block;width:40px">&nbsp;</span>b</div>'
    )
    got = sizes(body)
    assert got.min_content == got.max_content
    assert got.min_content == pytest.approx(
        advance("a") + 40.0 + advance("b"), abs=1e-9
    )


# --------------------------------------------------------------------------
# White space, through the box tree
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("body", "expected", "runs"),
    [
        # Chrome 151 `width: max-content`, in the same order.
        ("<div id=t><i>a</i> <i>b</i></div>", 22.2656, 3),
        ("<div id=t><i>a</i>   <i>b</i></div>", 22.2656, 3),
        ("<div id=t><i>a</i>" + LF + "    <i>b</i></div>", 22.2656, 3),
        ("<div id=t> <i>a</i> </div>", 8.9063, 1),
    ],
)
def test_collapsing_across_inline_boundaries_matches_chrome(body, expected, runs):
    """Three spaces, one newline plus indentation, and one space all give
    the same width -- and the leading and trailing ones give none at all.
    That is the whole of Phase I, measured rather than asserted."""
    got = sizes(body)
    assert got.max_content == pytest.approx(expected, abs=runs * LAYOUT_UNIT)


def test_nbsp_does_not_collapse_and_is_wider_than_the_collapsed_case():
    """Two NBSPs between the same two letters, against one collapsed space
    in the test above. Chrome 151: 26.7031 against 22.2656. If NBSP were
    treated as white space the two would be equal, which is exactly the
    failure a terminal cannot show."""
    got = sizes("<div id=t><i>a</i>&#xa0;&#xa0;<i>b</i></div>")
    assert got.max_content == pytest.approx(26.7031, abs=3 * LAYOUT_UNIT)
    assert got.max_content == pytest.approx(
        advance("a") + 2 * advance(NBSP) + advance("b"), abs=1e-9
    )


def test_every_text_box_carries_its_collapsed_text_after_layout():
    root, metrics = laid_out("<div id=t>  hello   world  </div>")
    texts = [box.text for box in root.walk() if box.origin == "text"]
    assert "hello world" in texts
    assert metrics["text_boxes_seen"] == len([t for t in texts if t is not None])


# --------------------------------------------------------------------------
# The partitions
# --------------------------------------------------------------------------


def test_the_text_box_partition_holds():
    root, metrics = laid_out(
        "<div><p>one two</p><p> </p><p><i>a</i> <i>b</i></p></div>"
    )
    assert metrics["text_boxes_seen"] == (
        metrics["text_boxes_content"] + metrics["text_boxes_whitespace_only"]
    )
    assert metrics["text_boxes_whitespace_only"] == sum(
        metrics["text_whitespace_" + name] for name in T.WHITESPACE_DISPOSITIONS
    )
    assert metrics["text_chars_in"] == (
        metrics["text_chars_kept"]
        + metrics["text_chars_transformed"]
        + metrics["text_chars_removed"]
    )
    assert metrics["text_whitespace_other"] == 0


def test_the_partitions_fail_loudly_when_a_category_is_forgotten():
    """The check must be shown to fire, or it is decorative.

    A `white-space` value handled in the collapser but missing from the
    census counters is exactly the shape of defect that has slipped through
    on this project before, so the assert is fed a counter set with one
    box unaccounted for.
    """
    from mayshay.layout.inline import assert_text_partitions

    metrics = Counter({"text_boxes_seen": 3, "text_boxes_content": 2})
    with pytest.raises(AssertionError, match="white-space-only or it is content"):
        assert_text_partitions(metrics)

    metrics = Counter(
        {
            "text_boxes_seen": 1,
            "text_boxes_content": 0,
            "text_boxes_whitespace_only": 1,
            "text_boxes_white_space_normal": 1,
        }
    )
    with pytest.raises(AssertionError, match="exactly one named disposition"):
        assert_text_partitions(metrics)

    metrics = Counter(
        {
            "text_boxes_seen": 1,
            "text_boxes_content": 1,
            "text_boxes_white_space_normal": 1,
            "text_chars_in": 5,
            "text_chars_kept": 4,
        }
    )
    with pytest.raises(AssertionError, match="kept, transformed or removed"):
        assert_text_partitions(metrics)

    metrics = Counter({"text_boxes_seen": 1, "text_boxes_content": 1})
    with pytest.raises(AssertionError, match="exactly one `white-space` value"):
        assert_text_partitions(metrics)


def test_min_content_may_not_exceed_max_content():
    with pytest.raises(AssertionError, match="counted into the wrong size"):
        I.IntrinsicSizes(10.0, 5.0)


# --------------------------------------------------------------------------
# Shrink-to-fit: CSS 2.1 section 10.3.5
# --------------------------------------------------------------------------


def test_the_shrink_to_fit_formula_in_its_three_regimes():
    """`min(max(min-content, available), max-content)` has three outcomes
    and a wrong formula reproduces at least one of them. All three, on the
    same box, so no single clamp can pass."""
    root, metrics = laid_out("<div id=t>alpha beta gamma</div>")
    box = find(root, "t")
    got = I.intrinsic_sizes(box, metrics=metrics)
    narrow = I.shrink_to_fit(box, 10.0, metrics=metrics)
    middle = I.shrink_to_fit(box, 80.0, metrics=metrics)
    wide = I.shrink_to_fit(box, 1000.0, metrics=metrics)
    assert narrow == got.min_content  # available below min-content
    assert middle == 80.0  # available between the two
    assert wide == got.max_content  # available above max-content


def test_a_float_gets_a_width_but_still_no_geometry():
    """Task D1 resolves the width Task C deferred and does **not** place
    the box: floats are not laid out at all. The pair -- a number and a
    None -- is the honest state, and asserting both is what stops a later
    reader from assuming either half."""
    root, metrics = laid_out(
        '<div style="width:400px">'
        '<div id=f style="float:left">alpha beta gamma</div></div>'
    )
    box = find(root, "f")
    assert box.geometry is None
    assert box.shrink_to_fit_width == pytest.approx(132.5313, abs=LAYOUT_UNIT)
    assert metrics["widths_shrink_to_fit_resolved"] == 1
    assert metrics["widths_deferred_shrink_to_fit"] == 0


def test_a_specified_width_short_circuits_the_formula():
    root, metrics = laid_out(
        '<div style="width:400px">'
        '<div id=f style="float:left;width:37px">alpha beta gamma</div></div>'
    )
    assert find(root, "f").shrink_to_fit_width == 37.0
    assert metrics["widths_shrink_to_fit_specified"] == 1


def test_a_percentage_width_on_a_descendant_behaves_as_auto():
    """CSS Sizing 3 section 5.2.1. The containing block has no definite
    size -- that is why intrinsic sizing is being asked for -- so a
    percentage of it is not a number. Resolving it against a zero basis
    would give 0px, which is a different answer that looks identical in a
    counter."""
    root, metrics = laid_out(
        '<div style="width:400px"><div id=f style="float:left">'
        '<div style="width:50%">alpha beta gamma</div></div></div>'
    )
    assert metrics["intrinsic_percentage_width_as_auto"] == 1
    assert find(root, "f").shrink_to_fit_width == pytest.approx(
        132.5313, abs=LAYOUT_UNIT
    )


def test_a_block_container_takes_the_widest_of_its_block_children():
    """Block children stack, so both intrinsic sizes are a `max` over the
    children rather than a sum. A `sum` implementation would give 258.80
    here."""
    root, metrics = laid_out(
        '<div style="width:400px"><div id=f style="float:left">'
        "<div>alpha beta gamma</div><div>x</div></div></div>"
    )
    assert find(root, "f").shrink_to_fit_width == pytest.approx(
        advance("alpha beta gamma"), abs=1e-9
    )


def test_a_childs_horizontal_edges_are_part_of_its_contribution():
    root, metrics = laid_out(
        '<div style="width:400px"><div id=f style="float:left">'
        '<div style="padding:0 7px;margin:0 3px;border:0">x</div></div></div>'
    )
    assert find(root, "f").shrink_to_fit_width == pytest.approx(
        advance("x") + 14.0 + 6.0, abs=1e-9
    )


def test_intrinsic_sizing_works_on_a_tree_that_never_saw_the_text_pass():
    """`intrinsic.py` is Task E's and Task F's too, and they may size a box
    without a full `layout_document` behind them. The fallback collapses on
    demand and says so, so that `intrinsic_text_collapsed_on_demand` reading
    non-zero on a real page is a defect report rather than a mystery."""
    document = parse(f"<style>{RESET}</style><div id=t>  a   b  </div>")
    style_document(document, [], viewport=VIEWPORT)
    root, _ = build_box_tree(document)
    metrics = Counter()
    got = I.intrinsic_sizes(find(root, "t"), metrics=metrics)
    assert metrics["intrinsic_text_collapsed_on_demand"] == 1
    assert got.max_content == pytest.approx(advance("a b"), abs=1e-9)


def test_an_empty_box_has_zero_intrinsic_sizes():
    root, metrics = laid_out('<div style="width:400px"><div id=t></div></div>')
    got = I.intrinsic_sizes(find(root, "t"), metrics=metrics)
    assert (got.min_content, got.max_content) == (0.0, 0.0)


def test_the_stub_entry_points_agree_with_the_single_walk():
    """`min_content_width` and `max_content_width` are the names Task C's
    stubs promised and Tasks E and F will import. They must not be able to
    drift from `intrinsic_sizes`, which is what `shrink_to_fit` uses."""
    root, metrics = laid_out("<div id=t>alpha beta gamma</div>")
    box = find(root, "t")
    both = I.intrinsic_sizes(box, metrics=metrics)
    assert I.min_content_width(box, metrics=metrics) == both.min_content
    assert I.max_content_width(box, metrics=metrics) == both.max_content


def test_measure_is_reached_through_the_single_seam():
    """`docs/fonts.md`: three call sites would be three places for one
    metric decision to drift. Intrinsic sizing must go through
    `layout.text.measure` rather than reading `hmtx` itself, and the way to
    show that is to replace the seam and watch the answer move."""
    root, metrics = laid_out("<div id=t>alpha</div>")
    box = find(root, "t")
    before = I.max_content_width(box, metrics=metrics)
    original = T.measure
    try:
        T.measure = lambda text, style, **kw: original(text, style, **kw) * 2
        after = I.max_content_width(box, metrics=metrics)
    finally:
        T.measure = original
    assert after == pytest.approx(2 * before, abs=1e-9)
    assert I.max_content_width(box, metrics=metrics) == before
