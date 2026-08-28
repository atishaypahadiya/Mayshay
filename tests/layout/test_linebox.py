"""Line boxes, fragments and baseline alignment -- Phase 3 Task D2.

**Every fixture here is synthetic and every expected number was measured
against Chrome 151.0.7922.174 before it was written down.** That is not a
formality on this task: the corpus validates almost none of it. Measured
over the three collected pages at 1280x1024, `vertical-align` on element
boxes is

    baseline 7,533   middle 43   top 30   text-top 1   text-bottom 1

with `sub`, `super`, `bottom`, `<percentage>` and `<length>` all **zero** --
and `baseline` at 7,533 is the *initial* value, so it counts boxes that
never set the property rather than boxes that exercise it. Narrowed to the
boxes that actually reach a line box, the corpus applies `middle` 8 times,
`text-top` once, `text-bottom` once and every other non-default rule zero
times.

So a green run of this file and a clean corpus render are **not** evidence
that baseline alignment works. The Chrome numbers are.

## How the Chrome numbers were taken, and why at 2048px

Chrome rounds this font's `hhea` metrics to whole pixels -- ascent 14,
descent 3, line gap 1 at a 16px font, where the font's own values give
14.484375, 3.390625 and 0.523438. Comparing vertical positions at 16px
therefore measures Chrome's rounding as much as anything else.

At **`font-size: 2048px`** -- the unitsPerEm of this font -- ascent 1854,
descent 434 and line gap 67 are all whole pixels and there is nothing to
round. Every vertical fixture below is stated at 2048px for that reason,
with the 16px consequence noted where it is interesting. Widths are
compared at 16px instead, where `docs/fonts.md` gives the tolerance as
`runs / 64` px, Chrome's LayoutUnit.

## The residual disagreements, named

After that, three remain and all three are explained:

* **half a pixel of half-leading.** CSS 2.1 section 10.8.1 puts half the
  leading above the content area and half below; Chrome floors the top
  half, so a 67px leading is 33.5/33.5 here and 33/34 there. Every
  `vertical-align` fixture below is off by exactly 0.5px for this reason
  and no other.
* **`middle`'s x-height, 9px at 2048px and 0.07px at 16px.** Chrome
  reports `1ex` as 1062 font units for this font; `OS/2.sxHeight` says
  1082, and `docs/fonts.md` takes the font's own metric because CSS Values
  4 section 5.1.2 says to.
* **bold.** This engine ships one face, so `<b>` measures at the regular
  advances. Chrome's `<b>beta gamma delta epsilon</b>` fragment is 93.375px
  where ours is 88.9375. Recorded in `docs/fonts.md`, not fixed here.
"""

from __future__ import annotations

import pytest

from mayshay.cssparse.cascade import style_document
from mayshay.cssparse.media import Viewport
from mayshay.dom.node import Element
from mayshay.htmlparse.treebuilder import parse
from mayshay.layout.block import layout_document
from mayshay.layout.boxtree import build_box_tree

VIEWPORT = Viewport(1280, 1024)

NBSP = "\u00a0"
EM_DASH = "\u2014"

def reset(size: int = 16) -> str:
    """The stylesheet every fixture starts from.

    Arial is named explicitly because that is the whole reason this font was
    chosen -- Liberation Sans is metric-compatible with it, so a number from
    Chrome and a number from here are about the same glyphs.

    It is applied to `html, body` **only**, and that is not a detail. An
    earlier draft set `font-size` and `line-height` on `div, span, p, b` as
    well, which quietly broke inheritance: a `line-height: 1.5` on a `<div>`
    could not reach the `<span>` inside it, because the span had a
    declaration of its own. Two of the tests below exist specifically to
    check that a unitless `line-height` inherits as a number, and both
    passed against the wrong reason until the numbers were re-derived.
    """
    return (
        "html,body{margin:0;padding:0}"
        f"html,body{{font-family:Arial;font-size:{size}px;line-height:normal}}"
    )


def laid_out(body: str, *, size: int = 16, css: str = ""):
    document = parse(f"<style>{reset(size)}{css}</style>{body}")
    style_document(document, [], viewport=VIEWPORT)
    root, metrics = build_box_tree(document)
    # Both counters, merged: the box-tree ones say what Task B built and the
    # layout ones say what Task D2 did with it, and at least one test below
    # needs to assert across the seam.
    metrics.update(layout_document(root, VIEWPORT))
    return root, metrics


def marked(root) -> dict[str, object]:
    out: dict[str, object] = {}
    for box in root.walk():
        if box.origin == "element" and isinstance(box.node, Element):
            key = box.node.attrs.get("id")
            if key:
                out[key] = box
    return out


def fragments(root, ident: str):
    """`[(x, y, width, height)]` per fragment, the border box of each.

    The border box because that is what `getClientRects()` reports for an
    inline element, measured: a `<span>` with `padding: 0 10px` comes back
    20px wider than its text.
    """
    return [
        (
            f.geometry.border.x,
            f.geometry.border.y,
            f.geometry.border.width,
            f.geometry.border.height,
        )
        for f in marked(root)[ident].fragments
    ]


def lines(root, ident: str):
    return marked(root)[ident].line_boxes


APPROX = dict(abs=1e-6)


# --------------------------------------------------------------------------
# Line breaking and fragments
# --------------------------------------------------------------------------


def test_an_inline_that_wraps_produces_one_fragment_per_line():
    """The shape the whole Chrome comparison contract was designed around,
    and the one the corpus has **zero** instances of.

    Chrome 151, `getClientRects()` on the span in a 200px div:

        [0]  x 0, w 186.7500
        [1]  x 0, w 178.7813
        [2]  x 0, w  88.9375

    `DOM.getBoxModel` answers the same question with one rectangle -- the
    union, 0..194.80 -- which matches none of the three. That is
    `docs/measurement-hazards.md` instance 3, and it is why this engine
    stores fragments and leaves `geometry` as None on an inline box.
    """
    root, metrics = laid_out(
        '<div style="width:200px"><span id=s>Hello world this is a longer '
        "sentence that wraps onto several lines</span></div>"
    )
    got = fragments(root, "s")
    # Chrome reports 178.7813 for the middle line; the last two bits are
    # its LayoutUnit quantisation of the same number.
    assert [round(f[2], 4) for f in got] == [186.75, 178.7812, 88.9297]
    assert [f[0] for f in got] == [0.0, 0.0, 0.0]
    assert marked(root)["s"].geometry is None
    assert metrics["line_breaks_soft"] == 2
    assert metrics["line_fragments_text"] == 3


def test_fragment_indices_are_continuous_across_the_node():
    """One `fragment` index each, numbered per DOM node in document order,
    because that is what `getContentQuads` returns one quad per."""
    root, _ = laid_out(
        '<div style="width:200px"><span id=s>Hello world this is a longer '
        "sentence that wraps onto several lines</span></div>"
    )
    span = marked(root)["s"]
    assert [f.index for f in span.fragments] == [0, 1, 2]
    assert [f.line for f in span.fragments] == [0, 1, 2]
    assert [f.identity()[2] for f in span.fragments] == [0, 1, 2]
    # ...and the other two identifiers are the same node every time.
    assert len({f.identity()[:2] for f in span.fragments}) == 1


def test_fragment_numbering_survives_an_inline_split_around_a_block():
    """The case injection testing found undefended, and the fix it forced.

    Task B splits `<span>a <div>b</div> c</span>` into **two** boxes for one
    DOM node, and each of them can then wrap into several fragments. Chrome
    answers `getContentQuads` for that node with one quad per fragment
    across the whole split, so the indices have to run 0, 1, 2, 3 and not
    0, 1 then 0, 1 again.

    Before the fix the counter was created per inline formatting context,
    which is per split half, so the second half restarted at 0 -- and there
    is no way to tell two fragments numbered 0 from one fragment measured
    twice. Every existing fixture had one box per node, so a defect keyed
    on `id(box)` instead of `id(box.node)` changed nothing and the suite
    stayed green.

    The corpus has **zero** genuinely split inlines -- all 31 candidates are
    dissolved atomics -- so this is synthetic-only and always will be
    without a wider corpus.
    """
    root, metrics = laid_out(
        '<div style="width:60px"><span id=s>alpha beta '
        "<div>block</div> gamma delta</span></div>"
    )
    pieces = [
        box
        for box in root.walk()
        if box.origin == "element"
        and isinstance(box.node, Element)
        and box.node.attrs.get("id") == "s"
    ]
    assert metrics["boxes_inline_split"] == 1
    assert len(pieces) == 2
    indices = [f.index for piece in pieces for f in piece.fragments]
    assert indices == sorted(indices)
    assert indices == list(range(len(indices)))
    assert len(indices) >= 4


def test_a_split_inline_puts_its_padding_on_the_first_and_last_fragment_only():
    """CSS 2.1 section 9.2.1.1's split rule, which section 16 restates for
    line breaks: the horizontal margin, border and padding are drawn where
    the box begins and ends, not on every line.

    Chrome 151 with `padding: 0 10px` in a 160px div: fragment 0 is
    x 0..141.6094 and fragment 1 is x 0..108.5469. Adding the padding on
    both lines instead would widen the second by 10px, which reads as a
    slightly wrong font rather than as a layout bug.
    """
    root, _ = laid_out(
        '<div style="width:160px"><span id=s style="padding:0 10px">'
        "aaaa bbbb cccc dddd eeee</span></div>"
    )
    got = fragments(root, "s")
    assert len(got) == 2
    assert got[0][0] == 0.0 and got[1][0] == 0.0
    # The left padding is on fragment 0 and the right on fragment 1; the
    # total of the two fragments' widths exceeds the text by exactly 20.
    text_only, _ = laid_out(
        '<div style="width:160px"><span id=s>aaaa bbbb cccc dddd eeee'
        "</span></div>"
    )
    bare = fragments(text_only, "s")
    assert sum(f[2] for f in got) == pytest.approx(
        sum(f[2] for f in bare) + 20.0, **APPROX
    )


def test_a_forced_break_ends_a_line_and_a_trailing_one_adds_none():
    """`<br>` is a forced break, and a trailing one produces no extra line
    box. Chrome: `x<br>` in a 300px div is 18px tall, not 36."""
    root, metrics = laid_out('<div id=d style="width:300px">one<br>two<br>three</div>')
    assert len(lines(root, "d")) == 3
    assert metrics["line_breaks_forced_br"] == 2

    trailing, _ = laid_out('<div id=d style="width:300px">x<br></div>')
    assert len(lines(trailing, "d")) == 1
    assert marked(trailing, )["d"].geometry.content.height == pytest.approx(
        18.3984375, **APPROX
    )


def test_nowrap_masks_every_opportunity_inside_it():
    """`white-space: nowrap` is on 24% of the corpus's element boxes and
    `pre` is on none, which is the reverse of what a suite written from
    CSS 2.1 would assume. One fragment, overflowing its 60px container."""
    root, metrics = laid_out(
        '<div style="width:60px"><span id=s style="white-space:nowrap">'
        "alpha beta gamma</span></div>"
    )
    assert len(fragments(root, "s")) == 1
    assert metrics["line_break_opportunities_masked_nowrap"] == 2
    assert metrics["line_overflow_unbreakable"] == 1


def test_nbsp_is_content_and_never_a_wrap_opportunity():
    """`str.strip()` is not CSS Text 3's white space and U+00A0 is the
    character that proves it: real advance, never collapses, never a break.

    The same three words with ordinary spaces break onto three lines in a
    60px div; joined by NBSP they are one unbreakable run.
    """
    spaced, _ = laid_out(
        '<div style="width:60px"><span id=s>alpha beta gamma</span></div>'
    )
    joined, _ = laid_out(
        f'<div style="width:60px"><span id=s>alpha{NBSP}beta{NBSP}gamma'
        "</span></div>"
    )
    assert len(fragments(spaced, "s")) == 3
    assert len(fragments(joined, "s")) == 1


def test_a_hyphen_is_a_break_opportunity_and_a_slash_is_not():
    """Both are delegated to UAX #14 and Chrome tailors one of them.
    Measured in a 60px div: `alpha-beta-gamma` breaks into three lines
    after each hyphen; `alpha/beta/gamma` does not break at all."""
    hyphenated, _ = laid_out(
        '<div style="width:60px"><span id=s>alpha-beta-gamma</span></div>'
    )
    slashed, _ = laid_out(
        '<div style="width:60px"><span id=s>alpha/beta/gamma</span></div>'
    )
    assert [round(f[2], 4) for f in fragments(hyphenated, "s")] == [
        44.4766, 36.4688, 53.3516
    ]
    assert len(fragments(slashed, "s")) == 1


def test_an_atomic_inline_breaks_on_both_sides_of_itself():
    """UAX #14 LB20 again, this time through the layout rather than the
    classifier. In a 45px div the `inline-block` takes a line of its own,
    which it could not do if it were glued to the letters beside it."""
    root, _ = laid_out(
        '<div id=d style="width:45px">a<span id=ib style="display:inline-block;'
        'width:40px;height:10px"></span>b</div>'
    )
    assert len(lines(root, "d")) == 3


# --------------------------------------------------------------------------
# CSS Text 3 Phase II -- trimming and hanging
# --------------------------------------------------------------------------


def test_a_trailing_space_is_trimmed_and_does_not_push_a_word_off_the_line():
    """The space between two words is inside the line; the one at the end
    of it is not. If a trailing space counted toward the used width, a line
    that exactly fits would wrap one word early -- an error of one space in
    a direction nothing else would catch.
    """
    root, metrics = laid_out(
        '<div style="width:60px"><span id=s>alpha beta</span></div>'
    )
    got = fragments(root, "s")
    assert len(got) == 2
    # "alpha" is 39.1484 and "alpha " is 43.5938; the fragment is the
    # former, so the trailing space contributed nothing.
    assert got[0][2] == pytest.approx(39.1484375, **APPROX)
    assert metrics["text_line_trailing_space_trimmed"] == 1
    assert metrics["text_line_trailing_space_hung"] == 0


def test_pre_wrap_hangs_its_trailing_spaces_instead_of_trimming_them():
    """`pre-wrap` preserves the spaces, so they are not *removed* -- they
    hang past the end of the line. Same position, different counter, and
    the counter is the only way to tell the two apart from the geometry.

    Zero corpus occurrences: 268 text boxes are `pre-wrap` and none of them
    ends a line in a preserved space. A `docs/synthetic-only-coverage.md`
    row.

    Chrome 151, `alpha   beta` in a 60px div, returns **three** rects for
    the span: `alpha` at 39.1563, the three hanging spaces at x 39.1563
    width 13.3438 on the same line, and `beta` at 31.1406 on the next. The
    line positions agree exactly; this engine does not emit a fragment for
    the hung run, which is a difference in what a fragment *is* rather than
    in where anything sits.
    """
    root, metrics = laid_out(
        '<div style="width:60px"><span id=s style="white-space:pre-wrap">'
        "alpha   beta</span></div>"
    )
    got = fragments(root, "s")
    assert len(got) == 2
    assert got[0][2] == pytest.approx(39.1484375, **APPROX)
    assert metrics["text_line_trailing_space_hung"] == 3
    assert metrics["text_line_trailing_space_trimmed"] == 0


def test_break_spaces_neither_trims_nor_hangs_and_wraps_in_the_run():
    """The one thing that separates `break-spaces` from `pre-wrap`, and the
    reason Task D1 recorded them as two rows in its behaviour table rather
    than merging the identical Phase I halves.

    CSS Text 3: under `break-spaces` every preserved space keeps its
    advance *and* gains a soft wrap opportunity after it, so a run of
    spaces can be broken inside. Zero corpus occurrences -- `break-spaces`
    is on no element on any of the three pages, so this and the Chrome
    numbers below are the only coverage it will ever have.

    Chrome 151, `alpha   beta` in a 45px div: two lines, `alpha ` at
    43.5938 and `  beta` at 40.0313. The break falls **inside** the run of
    spaces, which is the whole difference from `pre-wrap` -- there the run
    stays whole and hangs.
    """
    root, metrics = laid_out(
        '<div style="width:45px"><span id=s style="white-space:break-spaces">'
        "alpha   beta</span></div>"
    )
    # Two *extra*: UAX #14 already offers one after the run of three
    # spaces, and `break-spaces` adds one after each of the other two.
    assert metrics["line_break_spaces_extra_opportunity"] == 2
    assert metrics["text_line_trailing_space_hung"] == 0
    assert metrics["text_line_trailing_space_trimmed"] == 0
    got = fragments(root, "s")
    assert [round(f[2], 4) for f in got] == [43.5938, 40.0312]


# --------------------------------------------------------------------------
# Baseline alignment -- CSS 2.1 sections 10.8 and 10.8.1
# --------------------------------------------------------------------------
#
# Every number in this block is at font-size 2048px, where this font's
# `hhea` ascent 1854, descent 434 and line gap 67 are whole pixels and
# Chrome has nothing to round. `line-height: normal` is 2355 and the
# content area is 2288.

FONT_SIZE = 2048
ASCENT = 1854.0
DESCENT = 434.0
LINE_HEIGHT = 2355.0
CONTENT = ASCENT + DESCENT
HALF_LEADING = (LINE_HEIGHT - CONTENT) / 2.0   # 33.5; Chrome floors to 33


def aligned(inner: str):
    """One line, everything on it, nothing wrapping.

    `white-space: nowrap` and an absurd width are both needed: at 2048px a
    single word is wider than any real container, and a fixture whose child
    ends up alone on a wrapped line is measuring a different rule -- see
    `vertical_align_text_edge_against_empty_parent`.
    """
    return laid_out(
        f'<div id=d style="width:99999px;white-space:nowrap">base {inner}'
        " base</div>",
        size=FONT_SIZE,
    )


def child_top(root) -> float:
    """The aligned span's content-area top, relative to the line box top."""
    return fragments(root, "s")[0][1] - marked(root)["d"].geometry.content.y


BASELINE_TOP = HALF_LEADING   # an unshifted child's content top: 33.5


def test_baseline_is_the_default_and_leaves_the_child_where_it_is():
    root, metrics = aligned('<span id=s>mid</span>')
    assert child_top(root) == pytest.approx(BASELINE_TOP, **APPROX)
    assert marked(root)["d"].geometry.content.height == pytest.approx(
        LINE_HEIGHT, **APPROX
    )
    assert metrics["vertical_align_applied_baseline"] >= 1


def test_sub_lowers_the_child_by_a_fifth_of_its_font_size_plus_one():
    """CSS 2.1 says only "the proper position for subscripts", which is
    user-agent defined -- so this was measured, not read. Chrome 151 lowers
    a `sub` child by `font-size / 5 + 1`: 410.5938 at 2048px (410.6
    quantised to Chrome's 1/64 LayoutUnit) and 4.1875 at 16px (4.2
    quantised the same way).

    The 16px row is the one that shows it is really that formula and not a
    font metric: `OS/2.ySubscriptYOffset` for this font is 283 units, which
    is 2.21px at 16px and not 4.19.
    """
    root, metrics = aligned('<span id=s style="vertical-align:sub">sub</span>')
    shift = FONT_SIZE / 5.0 + 1.0
    assert child_top(root) == pytest.approx(BASELINE_TOP + shift, **APPROX)
    assert metrics["vertical_align_applied_sub"] == 1
    # Chrome's number, and ours, differ by the half-leading floor alone.
    assert child_top(root) - 0.5 == pytest.approx(443.5938, abs=0.01)


def test_super_raises_the_child_by_a_third_of_its_font_size_plus_one():
    """Measured the same way: Chrome raises by `font-size / 3 + 1`, which
    is 683.6563 at 2048px and 6.3281 at 16px -- both `x/3 + 1` quantised to
    1/64. `OS/2.ySuperscriptYOffset` is 977 units (7.63px at 16px) and is
    **not** what Chrome uses."""
    root, metrics = aligned('<span id=s style="vertical-align:super">sup</span>')
    shift = FONT_SIZE / 3.0 + 1.0
    assert child_top(root) == pytest.approx(BASELINE_TOP, **APPROX)
    # The child does not move -- the line grows above it instead, because
    # the raised child is now the topmost thing on the line.
    assert marked(root)["d"].geometry.content.height == pytest.approx(
        LINE_HEIGHT + shift, **APPROX
    )
    assert metrics["vertical_align_applied_super"] == 1


def test_middle_puts_the_childs_midpoint_half_an_x_height_above_the_baseline():
    """CSS 2.1 section 10.8.1, and the one rule here whose *value* this
    engine and Chrome disagree on.

    The shape is exact: the child's inline box midpoint sits at the
    parent's baseline minus half the parent's x-height. The value differs
    by half the x-height difference -- Chrome reports `1ex` for this font
    as 1062 units and `OS/2.sxHeight` says 1082, so at 2048px our child
    lands 9px above Chrome's and at 16px 0.07px above it.

    `docs/fonts.md` takes the font's own metric because CSS Values 4
    section 5.1.2 says a UA should. Recorded, not tuned.
    """
    root, metrics = aligned('<span id=s style="vertical-align:middle">mid</span>')
    x_height = 1082.0
    box_ascent = ASCENT + HALF_LEADING
    box_descent = LINE_HEIGHT - box_ascent
    shift = (box_ascent - box_descent) / 2.0 - x_height / 2.0
    assert child_top(root) == pytest.approx(BASELINE_TOP + shift, **APPROX)
    assert metrics["vertical_align_applied_middle"] == 1
    # Chrome's answer, with its own x-height: 211.5 where ours is 202.5.
    assert child_top(root) + 9.0 == pytest.approx(211.5, **APPROX)


def test_text_top_aligns_the_subtree_top_with_the_parents_content_area_top():
    """The parent's **content area**, not its inline box: at 2048px the
    content area top is 1854 above the baseline and the inline box top is
    1887.5, and the 33.5 between them is exactly what this rule moves an
    equally-sized child by.

    Chrome 151 puts an 8px `text-top` child at y 33 relative to the line
    top where we put it at 33.63; the difference is the half-leading floor
    plus Chrome rounding an 8px font's metrics to whole pixels.
    """
    root, metrics = aligned(
        '<span id=s style="vertical-align:text-top;font-size:8px">tt</span>'
    )
    assert child_top(root) == pytest.approx(33.630859375, **APPROX)
    assert metrics["vertical_align_applied_text_top"] == 1


def test_text_bottom_aligns_the_subtree_bottom_with_the_content_area_bottom():
    root, metrics = aligned(
        '<span id=s style="vertical-align:text-bottom;font-size:8px">tb</span>'
    )
    assert child_top(root) == pytest.approx(2312.431640625, **APPROX)
    assert metrics["vertical_align_applied_text_bottom"] == 1


def test_top_and_bottom_align_against_the_line_box_itself():
    """The two values CSS 2.1 admits are circular -- they align to a line
    box whose height they can then change -- and does not say how far to
    iterate. One pass here, with a counter for how often the pass moved
    anything, so "we stopped early" is a number.

    Chrome puts an 8px child at the very top (y 0) and at the very bottom
    (y 2346) of a 2355-tall line; ours land at 0.13 and 2345.93, which is
    the 8px content-area rounding and nothing else.
    """
    top, metrics_top = aligned(
        '<span id=s style="vertical-align:top;font-size:8px">t</span>'
    )
    bottom, metrics_bottom = aligned(
        '<span id=s style="vertical-align:bottom;font-size:8px">b</span>'
    )
    assert child_top(top) == pytest.approx(0.130859375, **APPROX)
    assert child_top(bottom) == pytest.approx(2345.931640625, **APPROX)
    assert metrics_top["vertical_align_applied_top"] == 1
    assert metrics_bottom["vertical_align_applied_bottom"] == 1
    # Neither grew the line: an 8px child fits inside a 2355px one.
    assert metrics_top["vertical_align_top_bottom_extended_line"] == 0


def test_a_length_raises_the_child_by_exactly_that_length():
    root, metrics = aligned('<span id=s style="vertical-align:10px">len</span>')
    # The child rises 10px and the line box rises with it, so the child's
    # offset from the LINE TOP does not move -- which is what Chrome
    # reports too, and is the reading that would look like a bug if the
    # assertion were on the wrong one of the two.
    assert child_top(root) == pytest.approx(BASELINE_TOP, **APPROX)
    assert marked(root)["d"].geometry.content.height == pytest.approx(
        LINE_HEIGHT + 10.0, **APPROX
    )
    assert metrics["vertical_align_applied_length"] == 1


def test_a_percentage_resolves_against_the_used_line_height():
    """Task A2 resolved this at cascade time wherever `line-height` was a
    number or a px length. **Zero corpus occurrences**, so it had never run
    against real input and never will.

    Chrome 151, `line-height: 20px` and `vertical-align: 50%`: the line box
    grows from 20 to 30, so the shift is 10 -- half the used line-height
    and not half the font size.
    """
    root, metrics = laid_out(
        '<div id=d style="width:400px;line-height:20px">base '
        '<span id=s style="vertical-align:50%">pct</span> base</div>'
    )
    assert marked(root)["d"].geometry.content.height == pytest.approx(30.0, **APPROX)
    assert metrics["vertical_align_applied_percentage"] == 0
    assert metrics["vertical_align_applied_length"] == 1


def test_a_percentage_against_line_height_normal_resolves_here_not_in_cascade():
    """Task A2's deferral, paid off.

    `vertical-align: <percentage>` resolves against the element's *used*
    `line-height`, which the cascade knows for a number and a px length and
    cannot know for `normal` -- that needs font metrics, which arrive with
    this task. A2 counted the deferral in `vertical_align_percent_deferred`
    rather than guessing `1.2 x font-size`; this is where the count is
    consumed.
    """
    root, metrics = laid_out(
        '<div id=d style="width:400px">base '
        '<span id=s style="vertical-align:50%">pct</span> base</div>'
    )
    # `vertical_align_percent_deferred` is a *cascade* counter and does not
    # appear in the layout metrics; what this asserts is the other half of
    # the same fact, that the resolution happened here.
    assert metrics["vertical_align_percent_resolved_in_layout"] == 1
    assert metrics["vertical_align_applied_percentage"] == 1
    # 50% of the used line-height, which for `normal` is 18.398438.
    assert marked(root)["d"].geometry.content.height == pytest.approx(
        18.3984375 + 18.3984375 / 2, **APPROX
    )


def test_a_line_box_with_two_font_sizes_is_taller_than_either_alone():
    """The case the plan singled out and the corpus does not have: a line
    whose height is not any single child's.

    Chrome 151 in a 400px div, `font: 16px Arial` with a 32px span: the div
    is 37 tall -- the 32px child's line-height -- and the 16px text sits on
    the same baseline. Ours is 36.7969, which is 32 x 1.1499023.
    """
    root, _ = laid_out(
        '<div id=d style="width:400px"><span id=s style="font-size:32px">Big'
        "</span> small text</div>"
    )
    assert marked(root)["d"].geometry.content.height == pytest.approx(
        36.796875, **APPROX
    )
    assert marked(root)["d"].geometry.content.height > 18.3984375


def test_a_unitless_line_height_multiplies_by_the_childs_own_font_size():
    """Task A2 deliberately kept a unitless `line-height` as a **number**
    rather than resolving it at cascade time, and Task C preserved that.
    This is the function that would undo it.

    `line-height: 1.5` on a 16px block containing a 32px span: the block's
    strut is 24 and the span's line box is 48, so the line is 48. Resolving
    at cascade time would inherit 24px and give 24.
    """
    root, _ = laid_out(
        '<div id=d style="width:400px;line-height:1.5">x'
        '<span style="font-size:32px">Big</span></div>'
    )
    assert marked(root)["d"].geometry.content.height == pytest.approx(48.0, **APPROX)


def test_the_strut_is_suppressed_on_a_line_with_no_direct_text():
    """A deliberate divergence from CSS 2.1 section 10.8, measured.

    The spec says a line box always carries the block container's font
    metrics, so `<div><span style="font-size:8px">x</span></div>` should be
    18.40 tall at a 16px block font. **Chrome 151 makes it 9.** Seven
    shapes were measured before this rule was written down and one rule
    explains all seven; see `layout.linebox._suppress_empty_boxes`.

    Implementing the spec instead would put this engine at odds with the
    reference renderer on every line whose text sits inside a smaller-font
    inline box.
    """
    nested, metrics = laid_out(
        '<div id=d style="width:400px"><span style="font-size:8px">x</span></div>'
    )
    direct, _ = laid_out('<div id=d style="width:400px">x</div>')
    assert marked(nested)["d"].geometry.content.height == pytest.approx(
        9.19921875, **APPROX
    )
    assert marked(direct)["d"].geometry.content.height == pytest.approx(
        18.3984375, **APPROX
    )
    assert metrics["line_strut_suppressed_no_direct_text"] == 1


def test_a_line_holding_only_an_atomic_inline_gets_no_strut_either():
    """Chrome: `<div><span style="display:inline-block;width:10px;
    height:10px"></span></div>` is **10** tall, not 18.4. The same rule as
    above, reached from the other direction."""
    root, _ = laid_out(
        '<div id=d style="width:400px"><span style="display:inline-block;'
        'width:10px;height:10px"></span></div>'
    )
    assert marked(root)["d"].geometry.content.height == 10.0


def test_an_empty_inline_box_makes_a_zero_height_line_box():
    """CSS 2.1 section 9.4.2. Chrome: `<div><span></span></div>` is 0 tall
    and `<div><span style="padding:0 5px"></span></div>` is 18.

    This is load-bearing for Task C rather than cosmetic: a line box is a
    margin-collapsing barrier, so an empty one that claimed a height would
    stop a collapse that Chrome allows.
    """
    empty, metrics = laid_out('<div id=d style="width:400px"><span></span></div>')
    padded, _ = laid_out(
        '<div id=d style="width:400px"><span style="padding:0 5px"></span></div>'
    )
    assert marked(empty)["d"].geometry.content.height == 0.0
    assert metrics["line_boxes_empty_zero_height"] == 1
    assert marked(padded)["d"].geometry.content.height == pytest.approx(
        18.3984375, **APPROX
    )


# --------------------------------------------------------------------------
# Atomic inlines
# --------------------------------------------------------------------------


def test_an_inline_blocks_baseline_is_its_last_line_box():
    """CSS 2.1 section 10.8.1, and both branches of it.

    With text inside, the `inline-block`'s baseline is its last line's, so
    it sits on the outer baseline like a word. With `overflow: hidden` it
    is the bottom margin edge instead, and the box drops.
    """
    visible, metrics_visible = laid_out(
        '<div id=d style="width:400px">base <span id=s style="display:'
        'inline-block;width:60px">inner</span> base</div>'
    )
    clipped, metrics_clipped = laid_out(
        '<div id=d style="width:400px">base <span id=s style="display:'
        'inline-block;width:60px;overflow:hidden">inner</span> base</div>'
    )
    assert metrics_visible["vertical_align_atomic_baseline_from_last_line"] == 1
    assert metrics_clipped["vertical_align_atomic_baseline_from_margin_edge"] == 1
    # The clipped one hangs its whole box above the baseline, so the line
    # box is taller.
    assert (
        marked(clipped)["d"].geometry.content.height
        > marked(visible)["d"].geometry.content.height
    )


def test_an_atomic_inline_has_geometry_and_exactly_one_fragment():
    """The three-way split the box tree's docstring states: a block-level
    box has geometry and no fragments, an inline box has fragments and no
    geometry, an atomic inline has both -- and they are the same rectangle,
    by identity, so nothing can shift it twice."""
    root, _ = laid_out(
        '<div style="width:400px">base <span id=s style="display:inline-block;'
        'width:40px;height:30px"></span> base</div>'
    )
    box = marked(root)["s"]
    assert box.geometry is not None
    assert len(box.fragments) == 1
    assert box.fragments[0].geometry is box.geometry


# --------------------------------------------------------------------------
# text-align
# --------------------------------------------------------------------------


def test_text_align_moves_the_whole_line_and_not_the_container():
    """Chrome 151 in a 200px div with `ab cd` (39.1406 wide): left at
    x 0, centred at x 80.4219 and right-aligned at x 160.8594. Ours are 0,
    80.4297 and 160.8594 -- the centred one is a LayoutUnit apart because
    the remainder is halved.

    `ab cd` rather than a single word on purpose: alignment moves a whole
    line, and a fixture with no break opportunity in it cannot tell that
    apart from moving one fragment. `start` is `left` here
    because `direction` is not parsed at all, so there is no right-to-left
    containing block for the two to differ in."""
    for align, expected, counter in (
        ("left", 0.0, "text_align_left"),
        ("center", (200 - 39.140625) / 2, "text_align_center"),
        ("right", 200 - 39.140625, "text_align_right"),
    ):
        root, metrics = laid_out(
            f'<div style="width:200px;text-align:{align}">'
            "<span id=s>ab cd</span></div>"
        )
        assert fragments(root, "s")[0][0] == pytest.approx(expected, **APPROX)
        assert metrics[counter] == 1


def test_justify_is_laid_out_as_start_and_counted():
    """Stretching a line means distributing the remainder across its soft
    wrap opportunities. There are **zero** `justify` declarations on the
    corpus, so implementing it would be an unmeasurable implementation of
    an unexercised path -- the same argument as the `clear` trap. Counted
    instead."""
    root, metrics = laid_out(
        '<div style="width:200px;text-align:justify"><span id=s>ab cd</span></div>'
    )
    assert fragments(root, "s")[0][0] == 0.0
    assert metrics["text_align_justify_as_start"] == 1


# --------------------------------------------------------------------------
# The mechanical checks
# --------------------------------------------------------------------------


def test_the_line_box_height_check_catches_a_forgotten_box():
    """Injection, in the shape of Task C's constraint assertion.

    A box that is aligned and then left out of the extent is exactly the
    defect this check exists for, and it is invisible otherwise: the text
    lands a few pixels off inside a plausible line box.
    """
    from mayshay.layout.linebox import LineBox, assert_line_box

    good = LineBox(
        index=0, x=0.0, y=0.0, width=0.0, available_width=100.0,
        height=20.0, baseline=15.0, top_extent=-15.0, bottom_extent=5.0,
        aligned=[(0.0, 15.0, 5.0)],
    )
    assert_line_box(good)

    forgotten = LineBox(
        index=0, x=0.0, y=0.0, width=0.0, available_width=100.0,
        height=20.0, baseline=15.0, top_extent=-15.0, bottom_extent=5.0,
        aligned=[(0.0, 10.0, 5.0)],
    )
    with pytest.raises(AssertionError, match="does not equal the extent"):
        assert_line_box(forgotten)


def test_the_line_box_width_check_catches_an_unaccounted_advance():
    from mayshay.layout.linebox import LineBox, assert_line_box

    line = LineBox(
        index=0, x=0.0, y=0.0, width=50.0, available_width=100.0,
        height=0.0, baseline=0.0, top_extent=0.0, bottom_extent=0.0,
        advances=[20.0, 20.0],
    )
    with pytest.raises(AssertionError, match="is not the sum of the advances"):
        assert_line_box(line)


def test_the_alignment_partition_catches_a_value_added_and_forgotten():
    from collections import Counter

    from mayshay.layout.linebox import assert_line_partitions

    metrics: Counter[str] = Counter()
    metrics["vertical_align_boxes_aligned"] = 3
    metrics["vertical_align_applied_baseline"] = 3
    metrics["line_fragments"] = 0
    metrics["linebreak_opportunities"] = 0
    assert_line_partitions(metrics)

    metrics["vertical_align_boxes_aligned"] = 4
    with pytest.raises(AssertionError, match="exactly one named"):
        assert_line_partitions(metrics)


def test_the_vertical_align_keyword_table_cannot_drift_from_the_parser():
    """The import-time assert, restated as a test so the reason is written
    down somewhere a reader will look.

    A ninth `vertical-align` keyword added to `cssparse.values` and
    forgotten here would fall through to the `baseline` default and align
    *plausibly*, which is the worst possible failure for a property whose
    entire failure mode is "the text is a few pixels off and the page looks
    fine".
    """
    from mayshay.cssparse.values import VERTICAL_ALIGN_KEYWORDS
    from mayshay.layout.linebox import _ALIGNMENT_RULES

    assert set(_ALIGNMENT_RULES) == set(VERTICAL_ALIGN_KEYWORDS)


def test_every_corpus_page_lays_out_with_the_line_partitions_intact():
    """The corpus as a smoke test, which is all it can be here.

    It exercises `baseline` 5,377 times and every other alignment rule
    between zero and eight, so a green run says the machinery does not
    crash on 986 line boxes of real markup and says **nothing** about
    whether `sub` is right. In-document CSS only, for the reason
    `test_block.py`'s corpus test gives: the external sheets need the
    manifest ordering that `scripts/corpus.py` owns.
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
        assert metrics["line_boxes"] > 0
        assert metrics["heights_deferred_inline_content"] == 0
