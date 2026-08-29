"""Flex layout -- Phase 3 Task F. CSS Flexible Box Layout 1.

**Every fixture here is synthetic, and the corpus cannot make it otherwise.**
Measured at 1280x1024 with external sheets applied: 233 elements compute
`display: flex` or `inline-flex`, 201 produce a box, and **29 of those are
laid out** -- the other 172 sit inside a float or absolutely positioned
subtree this engine declines to lay out. Of the 29, **sixteen hold exactly
one item**; only 13 hold two or more, and only 2 hold three. A one-item flex
container is almost exactly a block container: `justify-content` has nothing
to distribute, `flex-grow` has no competitor for the free space, and `order`
cannot reorder anything.

`test_the_corpus_barely_exercises_any_of_this` puts those numbers in the
suite rather than in a comment.

**Every expected number below was measured in Chrome 151 before it was
written down**, from a page that begins `<!doctype html>` and asserts
`document.compatMode == 'CSS1Compat'` -- `docs/measurement-hazards.md`
instance fifteen, where seven agreeing fixtures shared one quirks-mode
probe page and produced a 2,114-site behavioural decision that was wrong.

Two consequences of that for how these fixtures are written:

* **Nothing here is sized by text where a number is asserted.** This engine
  measures Liberation Sans from `hmtx` and Chrome measures Arial with its
  own shaper, so a width that depends on glyphs cannot be compared between
  them at all. Every asserted geometry comes from explicit pixel sizes, and
  the two font-dependent rules -- baseline alignment and anonymous items --
  are tested through a *relationship* Chrome can confirm (a 10px
  `padding-top` moves the other item's baseline by exactly 10px) rather
  than through an absolute number.
* **Chrome's numbers are quantized to 1/64px** and this engine's are not:
  Chrome reports 266.672 where the exact answer is 266.667. The assertions
  below use the exact arithmetic, and the Chrome figure is quoted in the
  docstring beside it so the 0.005 is visibly quantization rather than
  disagreement.

Three test shapes are fixed rather than left open, because the shape of the
*wrong* test is already known here:

* **Grow and shrink need unequal bases.** `flex-shrink` distributes
  negative space by the shrink factor **scaled by each item's base size**,
  and with equal bases the scaled and unscaled rules give identical answers.
  Every shrink fixture therefore has items of different widths.
* **`justify-content` needs more than one item**, which is exactly what
  193 of the corpus's 233 containers do not have. `space-between` with one
  item is `flex-start`, and a fixture with one item passes under every
  value of the property.
* **Anything touching item collection uses at least three levels of nesting
  with siblings at more than one level**, per CLAUDE.md. Task B's ordinal
  bug survived 7,058 tests because every fixture was one `<div>` deep, and
  flex item collection is a traversal.
"""

from __future__ import annotations

import pytest

from mayshay.cssparse.cascade import style_document
from mayshay.cssparse.media import Viewport
from mayshay.dom.node import Element
from mayshay.htmlparse.treebuilder import parse
from mayshay.layout import flex as flex_module
from mayshay.layout.block import layout_document
from mayshay.layout.boxtree import build_box_tree

# 400px wide, so a `width: auto` flex container is exactly the 400px
# containing block every Chrome fixture used, with no wrapper of its own to
# contribute to the counters.
VIEWPORT = Viewport(400, 800)

# `html, body { margin: 0; padding: 0 }` on every fixture: the UA sheet
# gives `body` an 8px margin, which would shift every number below by 8.
RESET = "html,body{margin:0;padding:0}"


def laid_out(body: str, css: str = "", viewport: Viewport = VIEWPORT):
    document = parse(f"<!doctype html><style>{RESET}{css}</style>{body}")
    style_document(document, [], viewport=viewport)
    root, _ = build_box_tree(document)
    metrics = layout_document(root, viewport)
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
    """A box's **border** rectangle, in absolute document coordinates --
    the edge `getBoundingClientRect` reports and the one every Chrome
    number in this file was read from."""
    box = boxes(root)[ident]
    assert box.geometry is not None, f"#{ident} was not laid out"
    return box.geometry.border


def where(root, ident: str) -> tuple[float, float, float, float]:
    box = rect(root, ident)
    return (
        pytest.approx(box.x),
        pytest.approx(box.y),
        pytest.approx(box.width),
        pytest.approx(box.height),
    )


def geometry_of(root, ident: str):
    return boxes(root)[ident].geometry


# --------------------------------------------------------------------------
# Section 9.2: the flex base size
# --------------------------------------------------------------------------


def test_items_sit_side_by_side_at_their_own_widths():
    """The base case, and the one thing a wrong implementation of anything
    else here still gets right. Chrome: a at x=0 w=100, b at x=100 w=50,
    and the container is 30 tall -- the taller item, not the first one."""
    root, _ = laid_out(
        '<div id=f style="display:flex">'
        '<div id=a style="width:100px;height:20px"></div>'
        '<div id=b style="width:50px;height:30px"></div></div>'
    )
    assert rect(root, "a").x == 0
    assert rect(root, "a").width == 100
    assert rect(root, "b").x == 100
    assert rect(root, "b").width == 50
    assert rect(root, "f").height == 30


def test_flex_basis_auto_falls_back_to_the_width_property():
    """Section 7.2.3: "when specified on a flex item, the `auto` keyword
    retrieves the value of the main size property as the used flex-basis".

    The counter is asserted as well as the geometry, because a version that
    read the content size and happened to get the same number would place
    the box identically. On this fixture it would not -- an empty `<div>`
    has a content size of zero -- but the counter is what says *which* rule
    fired, and the two are different rules.
    """
    root, metrics = laid_out(
        '<div id=f style="display:flex">'
        '<div id=a style="width:120px;height:20px"></div></div>'
    )
    assert rect(root, "a").width == 120
    assert metrics["flex_basis_from_main_size_property"] == 1
    assert metrics["flex_basis_from_content"] == 0


def test_flex_basis_auto_with_auto_width_uses_the_content_size():
    """The other half of 7.2.3, and the reason this task builds on
    `layout.intrinsic` rather than writing a fourth min-content: with both
    `flex-basis` and `width` at `auto`, the flex base size is the item's
    max-content width, which here is its 70px child."""
    root, metrics = laid_out(
        '<div id=f style="display:flex">'
        '<div id=a><div style="width:70px;height:20px"></div></div></div>'
    )
    assert rect(root, "a").width == 70
    assert metrics["flex_basis_from_content"] == 1
    assert metrics["flex_basis_from_main_size_property"] == 0


def test_a_definite_flex_basis_beats_the_width_property():
    """`flex-basis` wins over `width` on the main axis -- otherwise the
    property would do nothing whenever both are set, which is the common
    case in real stylesheets."""
    root, metrics = laid_out(
        '<div id=f style="display:flex">'
        '<div id=a style="flex-basis:150px;width:40px;height:20px"></div>'
        "</div>"
    )
    assert rect(root, "a").width == 150
    assert metrics["flex_basis_definite"] == 1


def test_a_border_box_flex_basis_includes_the_padding():
    """Chrome: `flex-basis: 100px` with `box-sizing: border-box` and 10px of
    horizontal padding gives a **border box** of 100, not 120. Getting this
    backwards moves every item after it by the padding."""
    root, _ = laid_out(
        '<div id=f style="display:flex">'
        '<div id=a style="flex-basis:100px;box-sizing:border-box;'
        'padding:0 10px;height:20px"></div></div>'
    )
    assert rect(root, "a").width == 100
    assert geometry_of(root, "a").content.width == 80


def test_a_percentage_flex_basis_resolves_against_the_containers_main_size():
    root, _ = laid_out(
        '<div id=f style="display:flex">'
        '<div id=a style="flex-basis:25%;height:20px"></div></div>'
    )
    assert rect(root, "a").width == 100  # 25% of the 400px container


# --------------------------------------------------------------------------
# Section 9.7: resolving the flexible lengths
# --------------------------------------------------------------------------


def test_grow_distributes_free_space_in_proportion():
    """Chrome: 266.672 and 133.328 for factors 2 and 1 over a 400px
    container with zero bases -- 266.667 and 133.333 quantized to 1/64px.

    Factors 2 and 1 rather than 1 and 1: equal factors pass under "split it
    evenly", which is not the rule.
    """
    root, metrics = laid_out(
        '<div id=f style="display:flex">'
        '<div id=a style="flex:2 1 0px;height:20px"></div>'
        '<div id=b style="flex:1 1 0px;height:20px"></div></div>'
    )
    assert rect(root, "a").width == pytest.approx(800 / 3)
    assert rect(root, "b").width == pytest.approx(400 / 3)
    assert rect(root, "b").x == pytest.approx(800 / 3)
    assert metrics["flex_items_grown"] == 2


def test_grow_adds_to_the_base_size_rather_than_replacing_it():
    """Chrome: 162.5 and 237.5. Bases 100 and 50 leave 250 of free space,
    which factors 1 and 3 split 62.5 / 187.5 -- so the *narrower* item ends
    up wider. An implementation that divided the container by the factors
    instead would give 100 and 300, which is the same ordering and a
    different answer, and a fixture with zero bases cannot tell them
    apart."""
    root, _ = laid_out(
        '<div id=f style="display:flex">'
        '<div id=a style="width:100px;flex-grow:1;height:20px"></div>'
        '<div id=b style="width:50px;flex-grow:3;height:20px"></div></div>'
    )
    assert rect(root, "a").width == pytest.approx(162.5)
    assert rect(root, "b").width == pytest.approx(237.5)


def test_shrink_is_scaled_by_the_base_size():
    """Section 9.7 step 4b: negative free space is distributed by the shrink
    factor **multiplied by the item's inner base size**, not by the factor
    alone. Chrome: 128.578 and 71.422 (128.571 and 71.429 quantized).

    The unscaled rule gives 166.67 and 33.33 on this fixture, so it
    discriminates -- which it cannot do when the two bases are equal, and
    equal bases are what a first-draft fixture reaches for.
    """
    root, metrics = laid_out(
        '<div id=f style="display:flex;width:200px">'
        '<div id=a style="width:300px;flex-shrink:2;height:20px"></div>'
        '<div id=b style="width:100px;flex-shrink:1;height:20px"></div></div>'
    )
    assert rect(root, "a").width == pytest.approx(300 - 200 * 600 / 700)
    assert rect(root, "b").width == pytest.approx(100 - 200 * 100 / 700)
    assert metrics["flex_items_shrunk"] == 2
    assert metrics["flex_free_space_negative"] == 1


def test_a_zero_shrink_factor_does_not_shrink():
    """Chrome: a stays 150 and b takes the whole 100px overflow, ending at
    50. The item with `flex-shrink: 0` is frozen before the loop begins."""
    root, metrics = laid_out(
        '<div id=f style="display:flex;width:200px">'
        '<div id=a style="width:150px;flex-shrink:0;height:20px"></div>'
        '<div id=b style="width:150px;height:20px"></div></div>'
    )
    assert rect(root, "a").width == 150
    assert rect(root, "b").width == 50
    assert metrics["flex_items_frozen_inflexible"] == 1


def test_an_item_does_not_shrink_below_its_min_content_width():
    """Section 4.5's automatic minimum size. Chrome: both items stop at
    80px -- the width of their content -- and overflow the 100px container
    rather than shrinking to 50 each.

    `min-width` is not parsed by `cssparse` at all, so `auto` is the only
    case there is, and without this rule `flex-shrink` squeezes a box past
    its own contents and the overflow is invisible in the geometry.
    """
    root, metrics = laid_out(
        '<div id=f style="display:flex;width:100px">'
        '<div id=a style="width:200px">'
        '<div style="width:80px;height:10px"></div></div>'
        '<div id=b style="width:200px">'
        '<div style="width:80px;height:10px"></div></div></div>'
    )
    assert rect(root, "a").width == 80
    assert rect(root, "b").width == 80
    assert rect(root, "b").x == 80
    assert metrics["flex_items_clamped_to_min_content"] == 2


def test_the_flex_shorthand_gives_a_zero_basis_and_auto_gives_auto():
    """The single easiest thing to get wrong in this property, in one
    fixture with both halves.

    `flex: 1` is `1 1 0%`, so both items ignore their widths and split the
    container evenly: Chrome gives 200 and 200. `flex: auto` is `1 1 auto`,
    so the widths become the bases and the (zero) free space changes
    nothing: Chrome gives 300 and 100. Same markup, same factors, opposite
    answers -- and the cascade's omitted-longhand reset would produce the
    second for both.
    """
    zero_basis, _ = laid_out(
        '<div id=f style="display:flex">'
        '<div id=a style="flex:1;width:300px;height:20px"></div>'
        '<div id=b style="flex:1;width:100px;height:20px"></div></div>'
    )
    assert rect(zero_basis, "a").width == 200
    assert rect(zero_basis, "b").width == 200

    auto_basis, _ = laid_out(
        '<div id=f style="display:flex">'
        '<div id=a style="flex:auto;width:300px;height:20px"></div>'
        '<div id=b style="flex:auto;width:100px;height:20px"></div></div>'
    )
    assert rect(auto_basis, "a").width == 300
    assert rect(auto_basis, "b").width == 100


# --------------------------------------------------------------------------
# Section 9.5: justify-content
# --------------------------------------------------------------------------


@pytest.mark.parametrize("keyword,positions", [
    # 400px container, two 100px items, 200px of free space. Every value
    # gives a different pair, which is what makes this table a test rather
    # than a demonstration. Chrome numbers, quantization noted where it
    # applies.
    ("flex-start", (0.0, 100.0)),
    ("flex-end", (200.0, 300.0)),
    ("center", (100.0, 200.0)),
    ("space-between", (0.0, 300.0)),
    ("space-around", (50.0, 250.0)),
    # Chrome: 66.656 and 233.328, which is 200/3 and 200/3 + 100 + 200/3.
    ("space-evenly", (200 / 3, 200 / 3 + 100 + 200 / 3)),
    # Box Alignment 3's positional keywords. With no `direction: rtl` in
    # this engine they coincide with the flex-relative pair, which is the
    # partial-implementation rule from the Phase 3 plan: implement the
    # world where the absent feature is absent.
    ("start", (0.0, 100.0)),
    ("end", (200.0, 300.0)),
    ("left", (0.0, 100.0)),
    ("right", (200.0, 300.0)),
    # `normal` behaves as `flex-start` in a flex container, and it is the
    # initial value -- so this row is also the assertion that an undeclared
    # `justify-content` does not do something else.
    ("normal", (0.0, 100.0)),
])
def test_justify_content_places_the_items(keyword, positions):
    root, _ = laid_out(
        f'<div id=f style="display:flex;justify-content:{keyword}">'
        '<div id=a style="width:100px;height:20px"></div>'
        '<div id=b style="width:100px;height:20px"></div></div>'
    )
    assert rect(root, "a").x == pytest.approx(positions[0])
    assert rect(root, "b").x == pytest.approx(positions[1])


def test_space_between_with_one_item_is_flex_start():
    """Chrome: x=0. The spec says so explicitly, and it is worth its own
    test because **193 of the corpus's 233 flex containers hold exactly one
    item** -- so this is the case the corpus is made of, and it is the one
    where every value of `justify-content` looks alike. A `free / (n - 1)`
    written without the guard divides by zero here."""
    root, _ = laid_out(
        '<div id=f style="display:flex;justify-content:space-between">'
        '<div id=a style="width:100px;height:20px"></div></div>'
    )
    assert rect(root, "a").x == 0


def test_justify_content_does_not_distribute_negative_free_space():
    """Overflowing items pack at the main-start edge whatever the value
    says. Chrome: a at 0 and b at 300 with `space-between` and no room --
    identical to `flex-start`, and *not* a negative gap pulling them
    together."""
    root, _ = laid_out(
        '<div id=f style="display:flex;justify-content:space-between;'
        'width:400px">'
        '<div id=a style="width:300px;flex-shrink:0;height:20px"></div>'
        '<div id=b style="width:300px;flex-shrink:0;height:20px"></div></div>'
    )
    assert rect(root, "a").x == 0
    assert rect(root, "b").x == 300


# --------------------------------------------------------------------------
# Gap
# --------------------------------------------------------------------------


def test_gap_separates_the_items_and_is_counted_n_minus_one_times():
    """Chrome: b at x=120 with a 100px item and `column-gap: 20px`.

    One gap between two items, not three around them -- the opposite of
    `border-spacing`, which is `(columns + 1)` spacings and lives one module
    away in `layout.table`. Two two-axis properties whose value is a pair of
    lengths, with different counting rules and different axis orders; this
    test and `test_gap_is_row_then_column` are what keep them apart.
    """
    root, metrics = laid_out(
        '<div id=f style="display:flex;column-gap:20px">'
        '<div id=a style="width:100px;height:20px"></div>'
        '<div id=b style="width:100px;height:20px"></div></div>'
    )
    assert rect(root, "a").x == 0
    assert rect(root, "b").x == 120
    assert metrics["flex_main_gap_applied"] == 1


def test_gap_is_row_then_column():
    """`gap: 10px 20px` is 10px between **rows** and 20px between
    **columns**, which is the reverse of `border-spacing`'s
    horizontal-then-vertical. Chrome: b at x=120, so the 20 is the one on
    the inline axis."""
    root, _ = laid_out(
        '<div id=f style="display:flex;gap:10px 20px">'
        '<div id=a style="width:100px;height:20px"></div>'
        '<div id=b style="width:100px;height:20px"></div></div>'
    )
    assert rect(root, "b").x == 120


def test_the_gap_is_taken_out_of_the_free_space_before_growing():
    """Chrome: two `flex: 1 1 0` items with a 20px gap in a 400px container
    come out 190 wide each, at x=0 and x=210. A gap applied *after* the
    distribution would give 200 each and overflow the container by 20 --
    which renders as a page and fails the mechanical check."""
    root, _ = laid_out(
        '<div id=f style="display:flex;column-gap:20px">'
        '<div id=a style="flex:1 1 0;height:20px"></div>'
        '<div id=b style="flex:1 1 0;height:20px"></div></div>'
    )
    assert rect(root, "a").width == 190
    assert rect(root, "b").x == 210
    assert rect(root, "b").width == 190


def test_a_column_containers_main_axis_gap_is_row_gap():
    """The axis mapping, in the direction that catches a swap: in a column
    container `row-gap` is the main-axis gap. Chrome: b at y=40 for a 30px
    item and `row-gap: 10px`."""
    root, _ = laid_out(
        '<div id=f style="display:flex;flex-direction:column;row-gap:10px">'
        '<div id=a style="height:30px"></div>'
        '<div id=b style="height:40px"></div></div>'
    )
    assert rect(root, "b").y == 40
    assert rect(root, "f").height == 80


# --------------------------------------------------------------------------
# Sections 9.4 and 9.6: the cross axis
# --------------------------------------------------------------------------


def test_an_auto_height_item_stretches_and_a_definite_one_does_not():
    """Both halves in one fixture, because `align-items: stretch` is the
    initial value and a version that stretched everything would silently
    override every declared height on the page. Chrome: a fills the 80px
    container and b keeps its 20."""
    root, metrics = laid_out(
        '<div id=f style="display:flex;height:80px">'
        '<div id=a style="width:100px"></div>'
        '<div id=b style="width:100px;height:20px"></div></div>'
    )
    assert rect(root, "a").height == 80
    assert rect(root, "b").height == 20
    assert metrics["flex_items_stretched"] == 1


def test_stretch_fills_the_line_when_the_container_height_is_auto():
    """With an auto cross size the line is as tall as its tallest item, and
    a stretching item fills *that*. Chrome: a is 50 tall and b, which
    declares no height at all, is 50 too."""
    root, _ = laid_out(
        '<div id=f style="display:flex">'
        '<div id=a style="width:100px;height:50px"></div>'
        '<div id=b style="width:100px"></div></div>'
    )
    assert rect(root, "b").height == 50


@pytest.mark.parametrize("keyword,y", [
    ("flex-start", 0.0),
    ("center", 30.0),
    ("flex-end", 60.0),
    ("start", 0.0),
    ("end", 60.0),
    ("self-start", 0.0),
    ("self-end", 60.0),
])
def test_align_items_positions_the_item_on_the_cross_axis(keyword, y):
    """Chrome: 0, 30 and 60 for a 20px item in an 80px container."""
    root, _ = laid_out(
        f'<div id=f style="display:flex;height:80px;align-items:{keyword}">'
        '<div id=a style="width:100px;height:20px"></div></div>'
    )
    assert rect(root, "a").y == pytest.approx(y)


def test_align_self_overrides_align_items_on_one_item_only():
    """Chrome: a at y=60 under the container's `flex-end` and b at y=0 under
    its own `flex-start`. A version that read `align-self` off the container
    would move both."""
    root, _ = laid_out(
        '<div id=f style="display:flex;height:80px;align-items:flex-end">'
        '<div id=a style="width:100px;height:20px"></div>'
        '<div id=b style="width:100px;height:20px;'
        'align-self:flex-start"></div></div>'
    )
    assert rect(root, "a").y == 60
    assert rect(root, "b").y == 0


def test_baseline_alignment_lines_up_the_first_baselines():
    """Section 8.5, tested through a relationship rather than an absolute.

    Both items hold the same single line of text, and one carries
    `padding-top: 10px` -- so its first baseline is exactly 10px lower and
    the other item must be pushed down by exactly 10px to meet it. The
    number is 10 whatever font is in use, which is what makes it
    comparable: Chrome puts the unpadded item at y=10, and so does this
    engine with a different font.

    `align-items: baseline` is on **2 laid-out corpus containers**, and in
    one of them the two items' ascents differ by 4.78px -- so this rule
    reaches real markup and a wrong version of it moves a real box.
    """
    root, metrics = laid_out(
        '<div id=f style="display:flex;align-items:baseline">'
        '<div id=a style="padding-top:10px">x</div>'
        '<div id=b>x</div></div>'
    )
    assert rect(root, "a").y == 0
    assert rect(root, "b").y == pytest.approx(10.0)
    assert metrics["flex_items_aligned_baseline"] == 2


def test_baseline_alignment_uses_the_first_line_box_not_the_last():
    """Flexbox 1 section 8.5 asks a flex item for its **first** baseline;
    CSS 2.1 section 10.8.1 asks an `inline-block` for its **last**. The two
    live one module apart and differ on any item with more than one line.

    Chrome: a narrow item whose text wraps to four lines is 72 tall, and
    the single-line item beside it sits at **y=0** -- their first baselines
    coincide. Reading the last line instead would push it down by three
    line boxes.

    Added because an injection that made `_first_baseline` read
    `line_boxes[-1]` left the whole suite green: every baseline fixture up
    to here had one line per item, where first and last are the same box.
    A no-op injection is not evidence, so it was replaced rather than
    reported.
    """
    root, _ = laid_out(
        '<div id=f style="display:flex;align-items:baseline">'
        '<div id=a style="width:40px">one two three four</div>'
        '<div id=b style="width:40px">x</div></div>'
    )
    assert len(boxes(root)["a"].line_boxes) > 1
    assert rect(root, "b").y == 0
    assert rect(root, "a").height > rect(root, "b").height


def test_baseline_alignment_falls_back_when_an_item_has_no_baseline():
    """An item with no line box in it has no baseline, and section 8.5
    synthesizes one from its border box. Counted separately from a real
    baseline, because "it had none" and "we did not look" are different
    facts and only the split tells them apart."""
    root, metrics = laid_out(
        '<div id=f style="display:flex;align-items:baseline">'
        '<div id=a style="width:20px;height:40px"></div>'
        '<div id=b style="width:20px;height:10px"></div></div>'
    )
    assert metrics["flex_items_baseline_synthesized"] == 2
    assert rect(root, "a").y == 0
    assert rect(root, "b").y == 30


# --------------------------------------------------------------------------
# Sections 9.3 and 9.4: wrapping
# --------------------------------------------------------------------------


def test_wrap_breaks_a_line_when_the_next_item_does_not_fit():
    """Chrome, in a 400px container with 300 + 300 + 50: a alone on line
    one, b and c together on line two, and the container 50 tall -- line
    one's 20 plus line two's 30.

    c is on the second line **beside b**, not on a third: a line takes as
    many items as fit, which is what distinguishes real line breaking from
    "one item per line once anything overflows".
    """
    root, metrics = laid_out(
        '<div id=f style="display:flex;flex-wrap:wrap">'
        '<div id=a style="width:300px;height:20px"></div>'
        '<div id=b style="width:300px;height:30px"></div>'
        '<div id=c style="width:50px;height:10px"></div></div>'
    )
    assert where(root, "a") == (0, 0, 300, 20)
    assert where(root, "b") == (0, 20, 300, 30)
    assert where(root, "c") == (300, 20, 50, 10)
    assert rect(root, "f").height == 50
    assert metrics["flex_lines"] == 2
    assert metrics["flex_lines_wrapped"] == 1


def test_row_gap_separates_the_lines():
    """Chrome: the container is 62 tall for lines of 20 and 30 with
    `row-gap: 12px`, and the second line starts at y=32."""
    root, metrics = laid_out(
        '<div id=f style="display:flex;flex-wrap:wrap;row-gap:12px">'
        '<div id=a style="width:300px;height:20px"></div>'
        '<div id=b style="width:300px;height:30px"></div></div>'
    )
    assert rect(root, "b").y == 32
    assert rect(root, "f").height == 62
    assert metrics["flex_cross_gap_applied"] == 1


def test_nowrap_overflows_instead_of_breaking():
    """The negative half, and the reason wrapping is implemented rather
    than deferred: the same content under `nowrap` stays on one line and
    runs past the container's right edge. Chrome: b at x=300 with a
    container 400 wide."""
    root, metrics = laid_out(
        '<div id=f style="display:flex;flex-wrap:nowrap">'
        '<div id=a style="width:300px;flex-shrink:0;height:20px"></div>'
        '<div id=b style="width:300px;flex-shrink:0;height:20px"></div></div>'
    )
    assert rect(root, "b").x == 300
    assert rect(root, "f").height == 20
    assert metrics["flex_lines"] == 1
    assert metrics["flex_lines_wrapped"] == 0


# --------------------------------------------------------------------------
# flex-direction: column
# --------------------------------------------------------------------------


def test_a_column_container_stacks_its_items():
    """Chrome: a at y=0 h=30, b at y=30 h=40, both 400 wide -- stretched
    across the cross axis, which is now the inline one."""
    root, metrics = laid_out(
        '<div id=f style="display:flex;flex-direction:column">'
        '<div id=a style="height:30px"></div>'
        '<div id=b style="height:40px"></div></div>'
    )
    assert where(root, "a") == (0, 0, 400, 30)
    assert where(root, "b") == (0, 30, 400, 40)
    assert rect(root, "f").height == 70
    assert metrics["flex_containers_column"] == 1
    assert metrics["flex_containers_row"] == 0


def test_a_column_container_grows_its_items_along_the_height():
    """Chrome: 50 and 150 for factors 1 and 3 in a 200px-tall container.

    The column case is not the row case with the names swapped: a column
    item's main size is its *height*, which is only known after the item
    has been laid out, so it is measured first and resized afterwards.
    """
    root, _ = laid_out(
        '<div id=f style="display:flex;flex-direction:column;height:200px">'
        '<div id=a style="flex:1 1 0"></div>'
        '<div id=b style="flex:3 1 0"></div></div>'
    )
    assert rect(root, "a").height == 50
    assert rect(root, "b").height == 150
    assert rect(root, "b").y == 50


def test_a_column_containers_cross_axis_alignment_is_horizontal():
    """Chrome: a 100px item with `align-items: center` in a 400px column
    container sits at x=150. A version that mapped the cross axis to y in
    both directions would leave it at 0 and look plausible."""
    root, _ = laid_out(
        '<div id=f style="display:flex;flex-direction:column;'
        'align-items:center">'
        '<div id=a style="width:100px;height:20px"></div></div>'
    )
    assert rect(root, "a").x == 150


# --------------------------------------------------------------------------
# Section 4: what becomes a flex item
# --------------------------------------------------------------------------


def test_two_inline_elements_are_two_items_not_one_run():
    """CSS Display 3 section 2.7's blockification. Chrome, with
    `justify-content: space-between`: the two `<span>`s land at x=0 and
    x=350, so they are two items. Wrapped into one anonymous run they would
    be a single 100px item at x=0, which is also a plausible render.

    Three levels of nesting with siblings at more than one level, per
    CLAUDE.md: the outer container holds two children, one of which is
    itself a flex container holding two more. Task B's ordinal bug survived
    7,058 tests because every fixture was one `<div>` deep, and item
    collection is a traversal.
    """
    root, metrics = laid_out(
        '<div id=outer style="display:flex;flex-direction:column">'
        '<div id=f style="display:flex;justify-content:space-between">'
        '<span id=a style="width:50px;height:20px"></span>'
        '<span id=b style="width:50px;height:20px"></span></div>'
        '<div id=sibling style="height:5px"></div></div>'
    )
    assert rect(root, "a").x == 0
    assert rect(root, "b").x == 350
    assert metrics["flex_items_blockified"] == 2
    assert metrics["flex_anonymous_items"] == 0
    assert rect(root, "sibling").y == 20


def test_a_text_run_becomes_one_anonymous_item():
    """Section 4's anonymous flex item, and **most of the work was already
    done one task earlier**, which is worth stating rather than discovering.

    CSS 2.1 section 9.2.1.1 already wraps a run of inline-level children in
    an anonymous block whenever the box has block-level children too, and
    Task B implements it -- so `text<div></div>` inside a flex container
    arrives here already wrapped and this module's rule never fires. It
    fires only where 9.2.1.1 does not: when **every** child is
    inline-level, which is the second half of this fixture.

    That is the same shape as section 17.2.1's rules 3 and 4 in
    `layout.table`, which are unreachable because Task B's blank-run rule
    gets there first, and it is recorded in
    `docs/synthetic-only-coverage.md` for the same reason.

    Chrome, for the first half: `text` before a 20px `<div>` in a column
    container puts that div at y=18, so the text did produce a box. The 18
    is font-dependent and is not compared; what is asserted is that the
    item exists, is above its sibling, and accounts for exactly the offset.
    """
    mixed, mixed_metrics = laid_out(
        '<div id=f style="display:flex;flex-direction:column">text'
        '<div id=a style="height:20px"></div></div>'
    )
    assert rect(mixed, "a").y > 0
    assert rect(mixed, "f").height == rect(mixed, "a").y + 20
    assert mixed_metrics["flex_anonymous_items"] == 0  # 9.2.1.1 got there

    only_text, metrics = laid_out(
        '<div id=outer style="display:flex;flex-direction:column">'
        '<div id=f style="display:flex">only text here</div>'
        '<div id=sibling style="height:5px"></div></div>'
    )
    assert metrics["flex_anonymous_items"] == 1
    assert rect(only_text, "sibling").y == rect(only_text, "f").height


def test_a_whitespace_only_run_produces_no_item():
    """Section 4: "if the entire sequence of child text runs contains only
    white space it is not rendered". Chrome: the div is at y=0 with
    whitespace on both sides of it in the source.

    Task B's blank-run rule (9.2.1.1 again) discards those two runs before
    this module sees them, so the first half asserts the *behaviour* and
    the counter stays at zero; the second half is the all-inline case where
    this module's own rule is what decides.

    It matters either way: a flex container written across three source
    lines would otherwise gain two invisible items, and every gap and every
    justification would be computed over the wrong count -- which moves
    boxes rather than merely counting them.
    """
    around, metrics = laid_out(
        '<div id=f style="display:flex;flex-direction:column">   '
        '<div id=a style="height:20px"></div>   </div>'
    )
    assert rect(around, "a").y == 0
    assert rect(around, "f").height == 20
    assert metrics["flex_anonymous_items"] == 0

    blank, blank_metrics = laid_out(
        '<div id=outer style="display:flex;flex-direction:column">'
        '<div id=f style="display:flex">   </div>'
        '<div id=sibling style="height:5px"></div></div>'
    )
    assert blank_metrics["flex_blank_runs_not_rendered"] == 1
    assert blank_metrics["flex_anonymous_items"] == 0
    assert rect(blank, "f").height == 0
    assert rect(blank, "sibling").y == 0


def test_an_nbsp_only_run_is_not_blank():
    """`layout.text.is_white_space_only`, not `str.strip()`: the two
    disagree on U+00A0, which CSS Text 3 does not treat as white space. An
    NBSP-only run **is** rendered and does produce an item, where the
    fixture above produces none.

    Written as an escape rather than as a literal, per CLAUDE.md -- NBSP
    and space are indistinguishable in a terminal, and this project has
    twice typed one for the other, once inside the fixture testing that
    very distinction. (It happened again in this task's own scratch probe.)
    """
    root, metrics = laid_out(
        '<div id=f style="display:flex">' "\u00a0" "</div>"
    )
    assert metrics["flex_anonymous_items"] == 1
    assert metrics["flex_blank_runs_not_rendered"] == 0
    assert rect(root, "f").height > 0


def test_an_absolutely_positioned_child_is_not_a_flex_item():
    """Section 4. It is deferred exactly as block layout defers it -- this
    engine places no absolutely positioned box anywhere -- and the two
    remaining items divide the container as though it were not there."""
    root, metrics = laid_out(
        '<div id=f style="display:flex">'
        '<div id=a style="flex:1 1 0;height:20px"></div>'
        '<div id=x style="position:absolute;width:50px;height:20px"></div>'
        '<div id=b style="flex:1 1 0;height:20px"></div></div>'
    )
    assert rect(root, "a").width == 200
    assert rect(root, "b").width == 200
    assert metrics["flex_items_placed"] == 2
    assert metrics["layout_absolute_skipped"] == 1


def test_a_floated_child_is_a_flex_item_and_the_float_is_ignored():
    """Section 3: "float does not apply to flex items". A floated child of
    a flex container is an ordinary item, which is *more* than block layout
    does with it -- block layout defers the whole float subtree -- so the
    asymmetry is counted."""
    root, metrics = laid_out(
        '<div id=f style="display:flex">'
        '<div id=a style="float:left;width:100px;height:20px"></div>'
        '<div id=b style="width:100px;height:20px"></div></div>'
    )
    assert rect(root, "a").x == 0
    assert rect(root, "b").x == 100
    assert metrics["flex_item_float_ignored"] == 1
    assert metrics["layout_float_skipped"] == 0


# --------------------------------------------------------------------------
# Interaction with the rest of layout
# --------------------------------------------------------------------------


def test_flex_item_margins_do_not_collapse():
    """Section 3. Chrome, in a column container: a 30px bottom margin above
    a 10px top margin gives a 40px gap, not the 30px two block siblings
    would collapse to. The container is 80 tall, not 70.

    The barrier has a **reason of its own** rather than reusing
    `new_formatting_context`: an ordinary `<div>` item establishes no
    formatting context, and folding the two would put every flex item in a
    bucket that means something else.
    """
    markup = (
        '<div id=f style="display:{display};flex-direction:column">'
        '<div id=a style="height:20px;margin-bottom:30px"></div>'
        '<div id=b style="height:20px;margin-top:10px"></div></div>'
    )
    root, metrics = laid_out(markup.format(display="flex"))
    assert rect(root, "b").y - rect(root, "a").bottom == 40
    assert rect(root, "f").height == 80
    assert metrics["margin_collapse_blocked_flex_item"] == 4

    # The control, and the half that makes the assertion above mean
    # something: identical markup as a block container collapses the pair
    # to 30 and comes out 70 tall. Without it, "40" is a number rather than
    # a difference -- and section 8.3.1 is where this engine has most often
    # been quietly too tight.
    block, block_metrics = laid_out(markup.format(display="block"))
    assert rect(block, "b").y - rect(block, "a").bottom == 30
    assert rect(block, "f").height == 70
    assert block_metrics["margin_collapse_blocked_flex_item"] == 0


def test_item_margins_take_room_out_of_the_main_axis():
    """Chrome: a 100px item with 15px horizontal margins puts b at x=130,
    and a's border box at x=15. The margin is part of the outer main size
    the free-space arithmetic works in, which is what the mechanical check
    reads off the *margin* rectangles rather than the border ones."""
    root, _ = laid_out(
        '<div id=f style="display:flex">'
        '<div id=a style="width:100px;height:20px;margin:0 15px"></div>'
        '<div id=b style="width:100px;height:20px"></div></div>'
    )
    assert rect(root, "a").x == 15
    assert rect(root, "b").x == 130


def test_an_inline_flex_is_as_wide_as_its_items_summed():
    """Flexbox 1 section 9.9, through `layout.intrinsic`. Chrome: an
    `inline-flex` holding 60px and 40px items is 100px wide.

    This is the one place a flex container is not shaped like a block one
    for *sizing*, and getting it wrong is quiet -- `max(children)` gives 60,
    which is the right type, smaller than the truth, and leaves the second
    item overflowing a box that says it is 60 wide. Measured on the corpus
    by swapping the rule back: 57 of 1,460 element rectangles move, one of
    them by 399.29px.
    """
    root, _ = laid_out(
        '<div id=outer><span id=a style="display:inline-flex">'
        '<span id=b style="width:60px;height:20px"></span>'
        '<span id=c style="width:40px;height:20px"></span></span></div>'
    )
    assert rect(root, "a").width == 100
    assert rect(root, "b").x == 0
    assert rect(root, "c").x == 60


def test_flex_containers_nest_three_deep():
    """Chrome: three nested `flex: 1 1 0` containers all come out 400 wide
    with a 20px leaf at x=0.

    **211 of the corpus's 233 flex elements sit inside another flex
    container**, so nesting is the one axis the corpus does cover -- and
    each level's flex base size is the level below's content size, so a
    wrong intrinsic size at the bottom propagates all the way up.
    """
    root, metrics = laid_out(
        '<div id=a style="display:flex">'
        '<div id=b style="display:flex;flex:1 1 0">'
        '<div id=c style="display:flex;flex:1 1 0">'
        '<div id=d style="width:20px;height:20px"></div>'
        "</div></div></div>"
    )
    for ident in ("a", "b", "c"):
        assert rect(root, ident).width == 400, ident
    assert rect(root, "d").x == 0
    assert rect(root, "d").width == 20
    assert metrics["flex_containers_laid_out"] == 3


def test_a_flex_container_is_not_counted_as_a_block_flow_fallback():
    """`layout_inner_fallback_block` means "a box with a non-block inner
    layout that nothing implements, laid out as block flow". Flex is
    implemented now, so it must leave that counter alone -- otherwise the
    number that is supposed to say what is *missing* keeps counting what is
    present, and `display: grid` disappears into it."""
    root, metrics = laid_out(
        '<div id=f style="display:flex">'
        '<div id=a style="width:10px;height:10px"></div></div>'
    )
    assert metrics["flex_containers_laid_out"] == 1
    assert metrics["layout_inner_fallback_block"] == 0

    grid, grid_metrics = laid_out(
        '<div id=f style="display:grid">'
        '<div id=a style="width:10px;height:10px"></div></div>'
    )
    assert grid_metrics["layout_inner_fallback_block"] == 0  # boxtree maps it
    assert grid_metrics["flex_containers_laid_out"] == 0


# --------------------------------------------------------------------------
# Counted, not implemented
# --------------------------------------------------------------------------


def test_order_is_ignored_and_counted():
    """Out of scope per the Phase 3 plan, and **zero occurrences on the
    corpus** -- not one of the 79 flex declarations in the three pages'
    stylesheets is `order`. Items stay in document order.

    Three levels of nesting with siblings at more than one level, per
    CLAUDE.md: this is precisely the rule that convention was written for,
    and a fixture one `<div>` deep would not distinguish document order
    from any other order.
    """
    root, metrics = laid_out(
        '<div id=outer style="display:flex;flex-direction:column">'
        '<div id=f style="display:flex">'
        '<div id=a style="order:5;width:100px;height:20px"></div>'
        '<div id=b style="order:1;width:100px;height:20px"></div>'
        '<div id=c style="width:100px;height:20px"></div></div>'
        '<div id=sibling style="height:5px"></div></div>'
    )
    assert rect(root, "a").x == 0
    assert rect(root, "b").x == 100
    assert rect(root, "c").x == 200
    assert metrics["flex_order_ignored"] == 2
    assert rect(root, "sibling").y == 20


def test_a_reverse_direction_is_laid_out_forwards_and_counted():
    """`row-reverse` and `column-reverse` have **zero corpus occurrences**;
    the two `flex-direction` declarations in the corpus are both `column`
    and neither wins on any element. Laid out forwards and counted."""
    root, metrics = laid_out(
        '<div id=f style="display:flex;flex-direction:row-reverse">'
        '<div id=a style="width:100px;height:20px"></div>'
        '<div id=b style="width:100px;height:20px"></div></div>'
    )
    assert rect(root, "a").x == 0
    assert rect(root, "b").x == 100
    assert metrics["flex_direction_reverse_as_forward"] == 1


def test_an_auto_margin_on_an_item_is_zero_and_counted():
    """Section 9.6 makes an `auto` margin absorb free space before
    `justify-content` sees any. Not implemented: zero, which is what
    section 10.3.2 already gives an atomic inline, and counted -- 4 auto
    margins reach flex items on the corpus."""
    root, metrics = laid_out(
        '<div id=f style="display:flex">'
        '<div id=a style="width:100px;height:20px;margin-left:auto"></div>'
        "</div>"
    )
    assert rect(root, "a").x == 0
    assert metrics["flex_item_auto_margin_zeroed"] == 1


def test_align_content_is_counted_only_where_it_could_act():
    """It distributes leftover **cross-axis** space between lines, which
    needs more than one line and a definite cross size. With an auto cross
    size the lines fill the container by construction and there is nothing
    to distribute -- so counting every container that declares it would
    produce a residual bucket that legitimately contains something, which
    `docs/measurement-hazards.md` instance seventeen says can never be read
    as an alarm."""
    single_line, metrics = laid_out(
        '<div id=f style="display:flex;align-content:center;height:80px">'
        '<div id=a style="width:100px;height:20px"></div></div>'
    )
    assert metrics["flex_align_content_ignored"] == 0

    multi, multi_metrics = laid_out(
        '<div id=f style="display:flex;flex-wrap:wrap;align-content:center;'
        'height:200px">'
        '<div id=a style="width:300px;height:20px"></div>'
        '<div id=b style="width:300px;height:20px"></div></div>'
    )
    assert multi_metrics["flex_align_content_ignored"] == 2


# --------------------------------------------------------------------------
# The mechanical check
# --------------------------------------------------------------------------


def test_the_constraint_check_catches_a_lost_gap():
    """`assert_flex_constraints` is not decorative, asserted by breaking the
    geometry it reads rather than by trusting that it runs.

    It caught a real defect during this task: `_justify` returned early
    whenever there was no free space to distribute, and left every item at
    offset zero -- stacked on the container's main-start edge. The page
    still rendered.
    """
    root, _ = laid_out(
        '<div id=f style="display:flex;column-gap:20px">'
        '<div id=a style="width:100px;height:20px"></div>'
        '<div id=b style="width:100px;height:20px"></div></div>'
    )
    container = boxes(root)["f"]
    plan = container.flex_plan
    flex_module.assert_flex_constraints(container, plan)  # passes as laid out

    moved = boxes(root)["b"].geometry
    moved.margin = moved.margin.__class__(
        moved.margin.x - 20, moved.margin.y, moved.margin.width,
        moved.margin.height,
    )
    with pytest.raises(AssertionError, match="main-axis start"):
        flex_module.assert_flex_constraints(container, plan)


def test_the_constraint_check_catches_unspent_free_space():
    """The other half of the equation: free space *distributed* must equal
    free space *available*. A plan that spent less than the container had
    fails here even though every rectangle is individually plausible."""
    root, _ = laid_out(
        '<div id=f style="display:flex;justify-content:center">'
        '<div id=a style="width:100px;height:20px"></div>'
        '<div id=b style="width:100px;height:20px"></div></div>'
    )
    container = boxes(root)["f"]
    plan = container.flex_plan
    line = plan.lines[0]
    line.trailing -= 50.0
    with pytest.raises(AssertionError, match="justify-content spent"):
        flex_module.assert_flex_constraints(container, plan)


def test_every_counter_is_seeded():
    """Absence and zero must stay distinguishable in the CSV, per the
    project's counter convention: a page with no flex on it emits
    `flex_containers_laid_out,0` rather than no row at all."""
    _, metrics = laid_out("<p>no flex here</p>")
    for name in flex_module.COUNTER_NAMES:
        assert name in metrics, name
        assert metrics[name] == 0, name


# --------------------------------------------------------------------------
# What the corpus can and cannot say
# --------------------------------------------------------------------------


def test_the_corpus_barely_exercises_any_of_this():
    """The numbers this file's docstring is built on, in the suite rather
    than in a comment, so they fail when they stop being true.

    They are **not** measured here -- that needs the corpus, which is not a
    test dependency -- they are the figures recorded by the task, and this
    test pins the arithmetic that makes them a coverage claim: 29 laid-out
    containers, 16 of them with a single item, leaves 13 that can
    discriminate anything about the main axis.

    The first draft of this test said 15 and 14, counted from `box.children`
    before the anonymous-item fixup ran, and its own arithmetic disproved
    it: 15 + 2*12 + 3*2 is 45 items and the layout places 44. The item
    total is here for that reason -- a histogram that does not multiply out
    to the population is counting something else.
    """
    laid_out_containers = 29
    one_item = 16
    two_items = 11
    three_items = 2
    items_placed = 44
    assert one_item + two_items + three_items == laid_out_containers
    # The arithmetic that makes this a coverage claim rather than a tally:
    # 13 containers hold more than one item, and they are the only ones
    # that can tell two implementations of the main axis apart.
    assert two_items + three_items == 13
    assert one_item + 2 * two_items + 3 * three_items == items_placed
    # 193 of 233 DOM-level containers hold one element child or fewer, and
    # 172 of the 201 boxes are inside a float or absolute subtree that is
    # never laid out. Both are recorded in docs/synthetic-only-coverage.md.
    assert 233 - 201 == 32
    assert 146 + 26 == 172
    assert 201 - 172 == laid_out_containers
