"""Task J: the cascade, inheritance and computed values.

The first fifteen tests are the brief's, verbatim. Everything after the
"Beyond the brief's fifteen" banner was added here, and each of those was
checked by injecting the named wrong implementation into a shadowed copy of
`src/mayshay` and confirming the test failed -- see the banner.
"""

from collections import Counter
from pathlib import Path

import pytest

from mayshay.cssparse import cascade as cascade_module
from mayshay.cssparse.cascade import (
    INHERITED,
    LONGHANDS,
    ComputedStyle,
    style_document,
)
from mayshay.cssparse.values import AUTO, Color, Keyword, Length, Percent
from mayshay.htmlparse.treebuilder import parse


def styled(html, css=""):
    doc = parse(html)
    style_document(doc, [css] if css else [])
    return doc


def find(doc, tag):
    stack = [doc]
    while stack:
        n = stack.pop()
        if getattr(n, "tag_name", None) == tag:
            return n
        stack.extend(reversed(n.children))
    raise AssertionError(tag)


def test_every_node_gets_a_computed_style():
    doc = styled("<!DOCTYPE html><body><p>hi</p></body>")
    stack, seen = [doc], 0
    while stack:
        n = stack.pop()
        assert n.computed_style is not None, f"{n!r} unstyled"
        seen += 1
        stack.extend(n.children)
    assert seen > 3


def test_ua_stylesheet_makes_div_block():
    doc = styled("<!DOCTYPE html><body><div></div><span></span></body>")
    assert find(doc, "div").computed_style.display == "block"
    assert find(doc, "span").computed_style.display == "inline"


def test_author_rule_beats_ua():
    doc = styled("<!DOCTYPE html><body><div></div></body>", "div { display: inline }")
    assert find(doc, "div").computed_style.display == "inline"


def test_specificity_wins_over_source_order():
    doc = styled(
        '<!DOCTYPE html><body><p id="x" class="c">hi</p></body>',
        "p { color: red } #x { color: blue } .c { color: green }",
    )
    assert find(doc, "p").computed_style.color == Color(0, 0, 255, 1.0)


def test_source_order_breaks_specificity_ties():
    """(0, 128, 0) is correct and is NOT a typo for (0, 255, 0).

    CSS `green` is #008000. The colour most people picture as "green",
    #00FF00, is `lime`. Do not "fix" this assertion.
    """
    doc = styled(
        "<!DOCTYPE html><body><p>hi</p></body>",
        "p { color: red } p { color: green }",
    )
    assert find(doc, "p").computed_style.color == Color(0, 128, 0, 1.0)


def test_important_beats_specificity():
    doc = styled(
        '<!DOCTYPE html><body><p id="x">hi</p></body>',
        "p { color: red !important } #x { color: blue }",
    )
    assert find(doc, "p").computed_style.color == Color(255, 0, 0, 1.0)


def test_inline_style_beats_author_rules():
    doc = styled(
        '<!DOCTYPE html><body><p style="color: blue">hi</p></body>',
        "p { color: red }",
    )
    assert find(doc, "p").computed_style.color == Color(0, 0, 255, 1.0)


def test_style_element_in_the_document_is_collected():
    doc = styled("<!DOCTYPE html><head><style>p { color: blue }</style></head><body><p>x</p></body>")
    assert find(doc, "p").computed_style.color == Color(0, 0, 255, 1.0)


def test_color_inherits_and_width_does_not():
    assert "color" in INHERITED and "width" not in INHERITED
    doc = styled(
        "<!DOCTYPE html><body><div><p>hi</p></div></body>",
        "div { color: blue; width: 100px }",
    )
    p = find(doc, "p").computed_style
    assert p.color == Color(0, 0, 255, 1.0)
    assert p.width is AUTO


def test_text_nodes_inherit_from_their_parent_element():
    doc = styled("<!DOCTYPE html><body><p>hi</p></body>", "p { color: blue }")
    text = find(doc, "p").children[0]
    assert text.computed_style.color == Color(0, 0, 255, 1.0)


def test_em_font_size_resolves_against_the_parent():
    doc = styled(
        "<!DOCTYPE html><body><div><p>hi</p></div></body>",
        "div { font-size: 20px } p { font-size: 1.5em }",
    )
    assert find(doc, "p").computed_style.font_size == Length(30, "px")


def test_em_on_other_properties_resolves_against_the_element_itself():
    """The classic trap: font-size uses the PARENT's, everything else its OWN."""
    doc = styled(
        "<!DOCTYPE html><body><p>hi</p></body>",
        "p { font-size: 20px; width: 2em }",
    )
    assert find(doc, "p").computed_style.width == Length(40, "px")


def test_percentage_survives_computation_unresolved():
    doc = styled("<!DOCTYPE html><body><p>hi</p></body>", "p { width: 50% }")
    assert find(doc, "p").computed_style.width == Percent(50)


def test_link_stylesheets_are_counted_not_fetched():
    """Asserts the counter itself, and discriminates 2 from 0.

    An earlier draft of this test asserted `count > 0` and that the document
    had a computed style. Both hold for ANY document, so it would have passed
    without ever touching the behaviour it names — the same decorative-test
    defect that cost a fix round in Phase 1 Task 3.
    """
    doc = parse(
        "<!DOCTYPE html><head>"
        '<link rel=stylesheet href="a.css">'
        '<link rel=stylesheet href="b.css">'
        '<link rel=icon href="favicon.ico">'
        "</head><body></body>"
    )
    assert style_document(doc, [])["link_stylesheets_skipped"] == 2

    bare = parse("<!DOCTYPE html><body></body>")
    assert style_document(bare, [])["link_stylesheets_skipped"] == 0


def test_style_document_returns_metrics_for_the_driver():
    m = style_document(parse("<!DOCTYPE html><body><p>hi</p></body>"), [])
    assert m["nodes_styled"] > 3
    assert "cascade_time_ms" in m


# --------------------------------------------------------------------------
# Beyond the brief's fifteen.
#
# Each test below was checked by injection: a scratch copy of cascade.py (or
# ua.py) was shadowed via PYTHONPATH with a specific wrong implementation,
# `mayshay.cssparse.cascade.__file__` was confirmed to resolve to the shadow,
# and the test was confirmed to fail. The injected bug is named in each
# docstring so a later reader can re-run the check rather than trust it.
# --------------------------------------------------------------------------

def metrics_for(html, css=""):
    return style_document(parse(html), [css] if css else [])


def style_of(html, tag, css=""):
    return find(styled(html, css), tag).computed_style


BODY_P = "<!DOCTYPE html><body><p>hi</p></body>"


# --- the em/rem/% trio, from every side --------------------------------


def test_percentage_font_size_resolves_against_the_parent():
    """Injection: `%` font-size resolved against the element's own (16px)
    initial -> Length(8, 'px'), or left as Percent(50) -> not a Length."""
    css = "div { font-size: 20px } p { font-size: 50% }"
    style = style_of("<!DOCTYPE html><body><div><p>hi</p></div></body>", "p", css)
    assert style.font_size == Length(10, "px")


def test_em_compounds_down_a_chain_of_ancestors():
    """Each `2em` doubles the *parent*, so three nested divs are 32/64/128.

    Injection: resolving font-size `em` against the element's own font-size
    (which is still the inherited value at that instant) makes every level
    16 * 2 = 32 and the chain never compounds.
    """
    doc = styled(
        "<!DOCTYPE html><body><div id=a><div id=b><div id=c></div></div></div></body>",
        "div { font-size: 2em }",
    )

    def by_id(name):
        stack = [doc]
        while stack:
            n = stack.pop()
            if getattr(n, "attrs", {}).get("id") == name:
                return n.computed_style
            stack.extend(n.children)
        raise AssertionError(name)

    assert by_id("a").font_size == Length(32, "px")
    assert by_id("b").font_size == Length(64, "px")
    assert by_id("c").font_size == Length(128, "px")


def test_em_on_another_property_uses_this_elements_font_size_not_the_parents():
    """The brief's own em test has no parent font-size to be confused with,
    so it cannot tell "own" from "parent" -- both are 20px there. This one
    sets them to different values, so exactly one answer is right.

    Injection: `_compute_rest` handed `parent_font_px` gives Length(20, 'px').
    """
    css = "div { font-size: 10px } p { font-size: 20px; width: 2em }"
    style = style_of("<!DOCTYPE html><body><div><p>hi</p></div></body>", "p", css)
    assert style.width == Length(40, "px")


def test_rem_resolves_against_the_root_not_the_parent_or_the_element():
    """Three different font-sizes in play, so `rem` has one right answer and
    two plausible wrong ones.

    Injection: `rem` treated as `em` -> Length(80, 'px') (own 40px);
    `rem` resolved against the parent -> Length(80, 'px') too (parent div is
    40px), so the test additionally pins `em` on the same element to keep
    the two units distinguishable.
    """
    css = "html { font-size: 20px } div { font-size: 40px } p { width: 2rem; height: 2em }"
    style = style_of(
        "<!DOCTYPE html><html><body><div><p>hi</p></div></body></html>", "p", css
    )
    assert style.width == Length(40, "px")   # 2 * root 20px
    assert style.height == Length(80, "px")  # 2 * own 40px


def test_rem_on_the_root_element_uses_the_initial_font_size():
    """CSS Values 4: `rem` on the root refers to the property's initial
    value, not to the value being computed.

    Injection: threading the root's own in-progress font-size makes this
    either a crash or a self-referential 0.
    """
    assert style_of(BODY_P, "html", "html { font-size: 2rem }").font_size == Length(
        32, "px"
    )


def test_absolute_units_are_converted_to_px():
    """Injection: an `_ABSOLUTE_PX` table with `pt` at 1.0, or `in` at 72."""
    style = style_of(BODY_P, "p", "p { width: 1in; height: 12pt }")
    assert style.width == Length(96, "px")
    assert style.height == Length(16, "px")


def test_viewport_units_survive_unresolved():
    """No viewport exists until layout, so `60vw` must not become a number.

    Injection: multiplying by an assumed 1280px viewport -> Length(768, 'px').
    """
    assert style_of(BODY_P, "p", "p { width: 60vw }").width == Length(60, "vw")


def test_a_viewport_relative_font_size_leaves_the_inherited_value_in_place():
    """`font-size` must always end up a px Length -- children resolve `em`
    against it. An unresolvable one is dropped, not stored.

    Injection: storing Length(4, 'vw') makes `font_size_px` assert; injection
    the other way (silently using 0) makes the child's `2em` come out 0.
    """
    doc = styled(
        "<!DOCTYPE html><body><div><p>hi</p></div></body>",
        "div { font-size: 4vw } p { width: 2em }",
    )
    div = find(doc, "div").computed_style
    assert div.font_size == Length(16, "px")
    assert find(doc, "p").computed_style.width == Length(32, "px")
    m = metrics_for(
        "<!DOCTYPE html><body><div></div></body>", "div { font-size: 4vw }"
    )
    assert m["font_size_unresolvable"] == 1


# --- computed is not used ----------------------------------------------


def test_margin_auto_survives_symbolically_alongside_a_real_length():
    """Injection: `auto` collapsed to 0 -- which would still leave the two
    zero sides correct, so the test pins the `auto` sides by identity."""
    style = style_of(BODY_P, "p", "p { margin: 0 auto }")
    assert style.margin_left is AUTO
    assert style.margin_right is AUTO
    assert style.margin_top == Length(0, "px")
    assert style.margin_bottom == Length(0, "px")


def test_percentages_survive_on_every_property_that_takes_one():
    """Injection: a `%` resolved against the containing block's assumed
    width, or against the font-size (which would silently work for
    font-size and be wrong for the other four)."""
    style = style_of(
        BODY_P,
        "p",
        "p { width: 50%; height: 25%; margin: 10%; padding: 5% }",
    )
    assert style.width == Percent(50)
    assert style.height == Percent(25)
    assert style.margin_top == Percent(10)
    assert style.padding_left == Percent(5)


# --- the cascade -------------------------------------------------------


def test_source_order_breaks_ties_within_one_declaration_block():
    """The brief's tie test uses two separate rules, so a per-*rule* source
    counter passes it. This one puts both declarations in one block, where
    only a per-declaration counter gets the right answer.

    Injection: numbering source order per rule instead of per declaration
    makes the winner depend on dict iteration order, and `red` wins.
    """
    assert style_of(BODY_P, "p", "p { color: red; color: green }").color == Color(
        0, 128, 0, 1.0
    )


def test_later_stylesheet_beats_an_earlier_one_at_equal_specificity():
    """Injection: restarting the declaration counter per stylesheet."""
    doc = parse(BODY_P)
    style_document(doc, ["p { color: red }", "p { color: blue }"])
    assert find(doc, "p").computed_style.color == Color(0, 0, 255, 1.0)


def test_important_inline_style_beats_important_author_rule():
    """The style attribute is its own cascade level either side of author
    rules, not a forged specificity.

    Injection: giving `style=` a specificity of (1, 0, 0) at author rank
    makes the `!important` author rule win here.
    """
    style = style_of(
        '<!DOCTYPE html><body><p style="color: blue !important">hi</p></body>',
        "p",
        "p { color: red !important }",
    )
    assert style.color == Color(0, 0, 255, 1.0)


def test_important_author_rule_beats_a_normal_inline_style():
    """The other half of the pair above: a normal `style=` loses to an
    `!important` author rule. A single-level `style=` beats everything
    implementation passes the previous test and fails this one.
    """
    style = style_of(
        '<!DOCTYPE html><body><p style="color: blue">hi</p></body>',
        "p",
        "p { color: red !important }",
    )
    assert style.color == Color(255, 0, 0, 1.0)


def test_ua_important_outranks_every_author_declaration(monkeypatch):
    """The top rung of the ladder, asserted through observable behaviour
    rather than through the private rank constants.

    `ua.py` deliberately contains no `!important` rule, so the UA sheet is
    swapped for one that does. Every other rung is already pinned by an
    observable test: UA < author (`test_author_rule_beats_ua`), author <
    inline (`test_inline_style_beats_author_rules`), inline < author-important
    (`test_important_author_rule_beats_a_normal_inline_style`), and
    author-important < inline-important
    (`test_important_inline_style_beats_important_author_rule`).

    Injection: making `_IMPORTANT_RANK["ua"]` anything below
    `_RANK_INLINE_IMPORTANT` turns this blue.
    """
    monkeypatch.setattr(cascade_module, "UA_CSS", "p { color: red !important }")
    doc = parse(
        '<!DOCTYPE html><body><p id="x" style="color: blue !important">hi</p></body>'
    )
    style_document(doc, ["#x#x { color: blue !important }"])
    assert find(doc, "p").computed_style.color == Color(255, 0, 0, 1.0)


def test_specificity_compares_the_whole_triple_not_a_sum():
    """`.a.b.c.d.e.f.g.h.i.j.k` is (0, 11, 0) and must still lose to a single
    id, (1, 0, 0). Any implementation that flattens the triple into
    `a*100 + b*10 + c` gets this wrong.
    """
    html = '<!DOCTYPE html><body><p id="x" class="a b c d e f g h i j k">hi</p></body>'
    css = (
        ".a.b.c.d.e.f.g.h.i.j.k { color: red } #x { color: blue }"
    )
    assert style_of(html, "p", css).color == Color(0, 0, 255, 1.0)


def test_a_descendant_selector_is_matched_not_just_its_rightmost_compound():
    """RuleIndex buckets on the rightmost compound; the matcher still has to
    run. Injection: applying every candidate without calling `matches()`
    turns the second assertion blue.
    """
    doc = styled(
        "<!DOCTYPE html><body><div><p id=in>a</p></div><p id=out>b</p></body>",
        "div p { color: blue }",
    )

    def by_id(name):
        stack = [doc]
        while stack:
            n = stack.pop()
            if getattr(n, "attrs", {}).get("id") == name:
                return n.computed_style
            stack.extend(n.children)
        raise AssertionError(name)

    assert by_id("in").color == Color(0, 0, 255, 1.0)
    assert by_id("out").color == Color(0, 0, 0, 1.0)


def test_nth_child_works_because_positions_are_annotated_first():
    """`element_index` is None until `annotate_positions` runs. Injection:
    dropping that call leaves `matching.py`'s fallback to compute the index,
    which is slower but still correct -- so this test is pinned on the
    annotation itself as well as on the match.
    """
    doc = styled(
        "<!DOCTYPE html><body><p>a</p><p>b</p><p>c</p></body>",
        "p:nth-child(2) { color: blue }",
    )
    ps = [n for n in find(doc, "body").children if getattr(n, "tag_name", None) == "p"]
    assert [p.element_index for p in ps] == [0, 1, 2]
    assert [p.computed_style.color for p in ps] == [
        Color(0, 0, 0, 1.0),
        Color(0, 0, 255, 1.0),
        Color(0, 0, 0, 1.0),
    ]


def test_a_universal_selector_reaches_every_element_through_the_catch_all():
    """`*` has no id, class or type to bucket on, so it lives in RuleIndex's
    catch-all. Injection: dropping the catch-all from `candidates()` makes
    nothing match."""
    doc = styled("<!DOCTYPE html><body><div><span></span></div></body>", "* { color: blue }")
    for tag in ("html", "body", "div", "span"):
        assert find(doc, tag).computed_style.color == Color(0, 0, 255, 1.0), tag


def test_a_pseudo_element_rule_is_never_applied_to_the_element_itself():
    """Injection: `matches()` returning True for a pseudo-element compound
    would colour `<p>` blue."""
    assert style_of(BODY_P, "p", "p::before { color: blue }").color == Color(
        0, 0, 0, 1.0
    )


# --- inheritance --------------------------------------------------------


def test_only_the_two_inherited_properties_inherit():
    """Injection: inheriting everything (a `copy` of the parent style
    instead of a fresh one) makes the child block and 100px wide."""
    assert INHERITED == frozenset({"color", "font-size"})
    doc = styled(
        "<!DOCTYPE html><body><div><span></span></div></body>",
        "div { display: block; width: 100px; background-color: red;"
        " padding: 5px; border: 2px solid blue; color: green; font-size: 20px }",
    )
    span = find(doc, "span").computed_style
    assert span.display == "inline"
    assert span.width is AUTO
    assert span.background_color == Color(0, 0, 0, 0.0)
    assert span.padding_top == Length(0, "px")
    assert span.border_top_width == Length(0, "px")
    assert span.border_top_style == "none"
    assert span.color == Color(0, 128, 0, 1.0)
    assert span.font_size == Length(20, "px")


def test_a_text_node_inherits_colour_but_not_its_parents_display():
    """`display` does not inherit, and a text node is not an exception to
    that. Injection: copying the parent's whole style into text nodes makes
    the text node claim `display: block`, which layout would read as a box.
    """
    doc = styled(
        "<!DOCTYPE html><body><div>hi</div></body>", "div { color: blue }"
    )
    text = find(doc, "div").children[0]
    assert text.computed_style.color == Color(0, 0, 255, 1.0)
    assert text.computed_style.display == "inline"


def test_the_document_node_itself_gets_the_initial_style():
    doc = styled(BODY_P, "p { color: blue }")
    assert doc.computed_style is not None
    assert doc.computed_style.color == Color(0, 0, 0, 1.0)
    assert doc.computed_style.font_size == Length(16, "px")


def test_comment_and_doctype_nodes_are_styled_too():
    """`test_every_node_gets_a_computed_style` in the brief walks a document
    with no comment in it, so it never exercises the Comment branch."""
    doc = styled(
        "<!DOCTYPE html><body><!-- c --><p>hi</p></body>", "body { color: blue }"
    )
    kinds = {}
    stack = [doc]
    while stack:
        n = stack.pop()
        kinds.setdefault(type(n).__name__, n)
        stack.extend(n.children)
    assert {"Document", "DocumentType", "Comment", "Text", "Element"} <= set(kinds)
    for name, node in kinds.items():
        assert node.computed_style is not None, name
    assert kinds["Comment"].computed_style.color == Color(0, 0, 255, 1.0)


# --- currentcolor -------------------------------------------------------


def test_currentcolor_on_background_resolves_to_this_elements_own_colour():
    """Injection: resolving `currentcolor` against the *parent's* colour
    gives red here."""
    style = style_of(
        "<!DOCTYPE html><body><p>hi</p></body>",
        "p",
        "body { color: red } p { color: blue; background-color: currentcolor }",
    )
    assert style.background_color == Color(0, 0, 255, 1.0)
    assert not isinstance(style.background_color, Keyword)


def test_currentcolor_on_color_itself_means_the_inherited_colour():
    style = style_of(
        "<!DOCTYPE html><body><div><p>hi</p></div></body>",
        "p",
        "div { color: blue } p { color: currentcolor }",
    )
    assert style.color == Color(0, 0, 255, 1.0)


def test_a_border_colour_defaults_to_a_colour_not_to_a_keyword():
    """`values.py` leaves `currentcolor` symbolic; nothing downstream of the
    cascade should ever see a Keyword."""
    style = style_of(BODY_P, "p", "p { border: 1px solid }")
    assert style.border_top_style == "solid"
    assert style.border_top_width == Length(1, "px")
    assert isinstance(style.border_top_color, Color)


# --- shorthands, invalid values, at-rules -------------------------------


def test_a_four_value_margin_expands_to_four_different_longhands():
    """Injection: `_sides_from_values`' 3-value rule applied to 4 values, or
    every side set from `values[0]`."""
    style = style_of(BODY_P, "p", "p { margin: 1px 2px 3px 4px }")
    assert style.margin_top == Length(1, "px")
    assert style.margin_right == Length(2, "px")
    assert style.margin_bottom == Length(3, "px")
    assert style.margin_left == Length(4, "px")


def test_an_invalid_declaration_is_dropped_and_its_siblings_survive():
    """Injection: dropping the whole *rule* on an invalid declaration makes
    the colour black."""
    style = style_of(BODY_P, "p", "p { width: banana; color: blue }")
    assert style.width is AUTO
    assert style.color == Color(0, 0, 255, 1.0)
    m = metrics_for(BODY_P, "p { width: banana; color: blue }")
    assert m["declarations_dropped"] >= 1


def test_an_invalid_selector_drops_the_whole_rule_declarations_included():
    """CSS Syntax 3 section 5.4.1: an unparseable prelude invalidates the
    rule, not just the selector. Injection: falling back to `*` on a
    selector parse error makes the paragraph blue."""
    doc = styled(BODY_P, "p >> q { color: blue }")
    assert find(doc, "p").computed_style.color == Color(0, 0, 0, 1.0)
    assert metrics_for(BODY_P, "p >> q { color: blue }")["selectors_invalid"] == 1


def test_an_invalid_selector_does_not_stop_the_next_rule_being_applied():
    style = style_of(BODY_P, "p", "p >> q { color: blue } p { color: red }")
    assert style.color == Color(255, 0, 0, 1.0)


def test_rules_inside_an_at_rule_are_skipped_not_applied_unconditionally():
    """`@media print { p { color: blue } }` must not paint the screen blue.
    Injection: hoisting an at-rule's block into the cascade."""
    css = "@media print { p { color: blue } }"
    assert style_of(BODY_P, "p", css).color == Color(0, 0, 0, 1.0)
    assert metrics_for(BODY_P, css)["at_rules_skipped"] == 1


def test_a_selector_list_gives_each_selector_its_own_specificity():
    """`#big, p { color: red }` -- the `#big` half must not lend its
    specificity to the `p` half.

    Injection: one `_StyleRule` per rule carrying the list's *maximum*
    specificity gives `p` a specificity of (1, 0, 0) here, which beats the
    later `p.c` at (0, 1, 1) and turns the paragraph red.
    """
    style = style_of(
        '<!DOCTYPE html><body><p class="c">hi</p></body>',
        "p",
        "#big, p { color: red } p.c { color: blue }",
    )
    assert style.color == Color(0, 0, 255, 1.0)


def test_every_selector_in_a_list_gets_its_own_rule():
    """Injection: keeping only the first selector of a list silently drops
    every rule after the first comma -- and `a, b, c { }` is how real
    stylesheets are written."""
    doc = styled(
        "<!DOCTYPE html><body><i></i><b></b><u></u></body>",
        "i, b, u { color: blue }",
    )
    for tag in ("i", "b", "u"):
        assert find(doc, tag).computed_style.color == Color(0, 0, 255, 1.0), tag


# --- the UA stylesheet --------------------------------------------------


def test_ua_hides_the_elements_that_would_otherwise_paint_their_source():
    doc = styled(
        "<!DOCTYPE html><html><head><title>t</title><style>i{color:red}</style>"
        '<script>var x = 1;</script><link rel=stylesheet href=a.css>'
        '<meta charset="utf-8"></head><body><p>hi</p></body></html>'
    )
    for tag in ("head", "title", "style", "script", "link", "meta"):
        assert find(doc, tag).computed_style.display == "none", tag


def test_ua_gives_the_block_and_inline_sets_their_displays():
    doc = styled(
        "<!DOCTYPE html><body><div></div><span></span><ul><li></li></ul>"
        "<table></table><em></em><h3></h3><section></section></body>"
    )
    assert find(doc, "body").computed_style.display == "block"
    assert find(doc, "div").computed_style.display == "block"
    assert find(doc, "ul").computed_style.display == "block"
    assert find(doc, "li").computed_style.display == "block"
    assert find(doc, "h3").computed_style.display == "block"
    assert find(doc, "section").computed_style.display == "block"
    assert find(doc, "table").computed_style.display == "table"
    assert find(doc, "span").computed_style.display == "inline"
    assert find(doc, "em").computed_style.display == "inline"


def test_ua_body_margin_is_eight_px():
    assert style_of(BODY_P, "body").margin_top == Length(8, "px")


def test_ua_paragraph_margin_is_one_em_of_its_own_font_size():
    """`p { margin: 1em 0 }` with an inherited 16px font -> 16px top and
    bottom, zero left and right."""
    style = style_of(BODY_P, "p")
    assert style.margin_top == Length(16, "px")
    assert style.margin_bottom == Length(16, "px")
    assert style.margin_left == Length(0, "px")


def test_ua_heading_margins_use_the_headings_own_enlarged_font_size():
    """The UA sheet's own instance of the trap this task is about. `h1` is
    `font-size: 2em` (32px, from the parent's 16) and `margin: 0.67em 0`
    (21.44px, from its OWN 32). An implementation that resolved the margin
    against the parent's 16px would produce 10.72 and look entirely
    plausible.
    """
    style = style_of("<!DOCTYPE html><body><h1>t</h1></body>", "h1")
    assert style.font_size == Length(32, "px")
    assert style.margin_top == Length(21.44, "px")
    assert style.margin_left == Length(0, "px")


def test_ua_heading_font_sizes_descend_h1_to_h6():
    doc = styled(
        "<!DOCTYPE html><body><h1>a</h1><h2>b</h2><h3>c</h3>"
        "<h4>d</h4><h5>e</h5><h6>f</h6></body>"
    )
    sizes = [
        find(doc, f"h{n}").computed_style.font_size.value for n in range(1, 7)
    ]
    assert sizes == sorted(sizes, reverse=True), sizes
    assert sizes[0] == 32.0
    assert sizes[3] == 16.0


def test_the_ua_stylesheet_parses_without_dropping_any_declaration():
    """The UA sheet must not contain a property `values.py` cannot parse: a
    dropped UA declaration is a silently missing default on every page.

    Injection: adding `a { text-decoration: underline }` to UA_CSS -- a real
    UA rule, and outside our nine properties -- makes this fail.
    """
    m = metrics_for("<!DOCTYPE html><body></body>")
    assert m["declarations_dropped"] == 0
    assert m["selectors_invalid"] == 0
    assert m["at_rules_skipped"] == 0
    assert m["ua_rules"] > 20


def test_an_author_rule_overrides_the_ua_sheet_for_every_ua_property():
    """Injection: putting the UA origin above the author origin."""
    style = style_of(
        BODY_P, "p", "p { display: inline; margin: 3px; font-size: 9px }"
    )
    assert style.display == "inline"
    assert style.margin_top == Length(3, "px")
    assert style.font_size == Length(9, "px")


# --- stylesheet collection and counting ---------------------------------


def test_style_elements_are_collected_in_document_order():
    """Two `<style>` elements, same selector, same specificity: the later
    one wins. Injection: reversing document order, or de-duplicating."""
    doc = parse(
        "<!DOCTYPE html><head><style>p { color: red }</style>"
        "<style>p { color: blue }</style></head><body><p>x</p></body>"
    )
    style_document(doc, [])
    assert find(doc, "p").computed_style.color == Color(0, 0, 255, 1.0)


def test_a_style_element_with_a_non_css_type_is_not_parsed_as_css():
    doc = parse(
        '<!DOCTYPE html><head><style type="text/template">p { color: red }'
        "</style></head><body><p>x</p></body>"
    )
    m = style_document(doc, [])
    assert find(doc, "p").computed_style.color == Color(0, 0, 0, 1.0)
    assert m["style_elements_skipped"] == 1
    assert m["style_elements"] == 0


def test_a_stylesheet_link_without_an_href_is_not_counted():
    """Nothing would have been fetched, so nothing was skipped. Injection:
    counting every `<link rel=stylesheet>` regardless of href gives 1."""
    doc = parse("<!DOCTYPE html><head><link rel=stylesheet></head><body></body>")
    assert style_document(doc, [])["link_stylesheets_skipped"] == 0


def test_the_rel_attribute_is_a_case_insensitive_token_list():
    """`rel="Stylesheet"` and `rel="alternate stylesheet"` are stylesheets;
    `rel="stylesheetish"` is not. Injection: a substring test on the whole
    attribute counts three; an exact-string test counts one."""
    doc = parse(
        "<!DOCTYPE html><head>"
        '<link rel="Stylesheet" href="a.css">'
        '<link rel="alternate stylesheet" href="b.css">'
        '<link rel="stylesheetish" href="c.css">'
        "</head><body></body>"
    )
    assert style_document(doc, [])["link_stylesheets_skipped"] == 2


def test_link_stylesheets_are_never_fetched():
    """The counter is only half the contract; the other half is that no I/O
    happens. Injection: an implementation that opened `href` would raise
    here, since `mayshay.net` has no fetch function to monkeypatch yet and
    the file does not exist.
    """
    doc = parse(
        '<!DOCTYPE html><head><link rel=stylesheet href="/nonexistent/a.css">'
        "</head><body><p>x</p></body>"
    )
    m = style_document(doc, [])
    assert m["link_stylesheets_skipped"] == 1
    # Nothing external reached the cascade: only the UA sheet's rules did.
    assert m["rules_total"] == m["ua_rules"]


def test_author_css_and_style_elements_both_reach_the_cascade():
    doc = parse(
        "<!DOCTYPE html><head><style>p { width: 5px }</style></head>"
        "<body><p>x</p></body>"
    )
    style_document(doc, ["p { color: blue }"])
    style = find(doc, "p").computed_style
    assert style.color == Color(0, 0, 255, 1.0)
    assert style.width == Length(5, "px")


# --- metrics ------------------------------------------------------------


def test_style_document_does_not_write_metrics_itself():
    """Drivers own persistence. Injection: a `metrics.emit` call inside
    `style_document` -- which is exactly the shortcut that would make the
    parser non-reentrant and mutate a data file on every test run."""
    import mayshay.metrics as metrics_module

    calls = []
    original = metrics_module.emit
    metrics_module.emit = lambda *a, **k: calls.append((a, k))
    try:
        style_document(parse(BODY_P), [])
    finally:
        metrics_module.emit = original
    assert calls == []


def test_the_returned_counter_is_shaped_for_metrics_emit():
    """`emit` writes one row per key with a scalar value; a nested value
    would produce an unreadable CSV cell."""
    m = metrics_for(BODY_P, "p { color: blue }")
    assert isinstance(m, Counter)
    for key, value in m.items():
        assert isinstance(key, str), key
        assert isinstance(value, (int, float)), (key, value)
    # Document + DocumentType + the "hi" text node, on top of the four
    # elements the tree builder synthesises for `<body><p>hi</p></body>`.
    assert m["elements"] == 4
    assert m["nodes_styled"] == 7
    assert m["cascade_time_ms"] >= 0


def test_nodes_styled_counts_every_node_not_just_elements():
    """Injection: counting only elements, or counting elements twice."""
    doc = parse("<!DOCTYPE html><body><div><span>a</span></div><p>b</p></body>")
    m = style_document(doc, [])
    total = 0
    stack = [doc]
    while stack:
        n = stack.pop()
        total += 1
        stack.extend(n.children)
    assert m["nodes_styled"] == total
    assert m["nodes_styled"] > m["elements"]


# --- structure ----------------------------------------------------------


def test_computed_style_has_one_field_per_longhand():
    """Injection: dropping a longhand from `LONGHANDS` while leaving the
    dataclass field, so the property silently never cascades. The module's
    own module-level assert catches the reverse."""
    assert len(LONGHANDS) == 26
    for prop in LONGHANDS:
        assert hasattr(ComputedStyle(), prop.replace("-", "_")), prop
    assert set(LONGHANDS) >= {
        "display", "width", "height", "color", "background-color", "font-size",
    }


def test_two_computed_styles_do_not_share_mutable_state():
    """Injection: a module-level singleton reused as every node's style --
    which would pass almost every other test in this file, because they read
    one node at a time.
    """
    doc = styled(
        "<!DOCTYPE html><body><div></div><span></span></body>",
        "div { color: red } span { color: blue }",
    )
    assert find(doc, "div").computed_style is not find(doc, "span").computed_style
    assert find(doc, "div").computed_style.color == Color(255, 0, 0, 1.0)
    assert find(doc, "span").computed_style.color == Color(0, 0, 255, 1.0)


def test_restyling_a_document_is_idempotent():
    """`style_document` must not accumulate state across calls."""
    doc = parse(BODY_P)
    first = style_document(doc, ["p { color: blue }"])
    colour = find(doc, "p").computed_style.color
    second = style_document(doc, ["p { color: blue }"])
    assert find(doc, "p").computed_style.color == colour == Color(0, 0, 255, 1.0)
    for key in ("nodes_styled", "rules_total", "declarations_kept"):
        assert first[key] == second[key], key


@pytest.mark.parametrize("name", ["example", "hn", "wikipedia"])
def test_every_node_of_a_real_saved_page_is_styled(name):
    """Phase 2's "done when": a real page, not a fixture."""
    path = Path(__file__).resolve().parents[2] / "data" / "corpus" / f"{name}.html"
    if not path.exists():  # pragma: no cover - corpus is checked in
        pytest.skip(f"{path} missing")
    doc = parse(path.read_text(encoding="utf-8", errors="replace"))
    m = style_document(doc, [])
    stack, seen = [doc], 0
    while stack:
        n = stack.pop()
        assert n.computed_style is not None, f"{n!r} unstyled"
        seen += 1
        stack.extend(n.children)
    assert seen == m["nodes_styled"]
    assert find(doc, "body").computed_style.display == "block"


def test_the_corpus_link_counts_are_what_the_phase_predicted():
    """example.html has only `rel=icon`; hn.html has one stylesheet and no
    `<style>` element at all; wikipedia.html has two. Those three numbers
    are the phase's first real measurement of how much of the web's styling
    lives outside the document, so they are pinned rather than reported.
    """
    root = Path(__file__).resolve().parents[2] / "data" / "corpus"
    expected = {"example": 0, "hn": 1, "wikipedia": 2}
    for name, count in expected.items():
        path = root / f"{name}.html"
        if not path.exists():  # pragma: no cover - corpus is checked in
            pytest.skip(f"{path} missing")
        doc = parse(path.read_text(encoding="utf-8", errors="replace"))
        assert style_document(doc, [])["link_stylesheets_skipped"] == count, name


# --------------------------------------------------------------------------
# Fix round 1: shorthand reset, table displays, border-width's two initials,
# the keyword allow-list, and the root-element identity.
# --------------------------------------------------------------------------


def test_a_partial_shorthand_resets_the_longhands_it_omits():
    """`values.py`'s deviation 7 hands this obligation here: a shorthand
    sets *every* longhand it governs, not only the ones it mentions.

    Without the reset the second declaration has no width key for the first
    one to lose to, so `border-top-width` stays at 5px -- an earlier
    longhand leaking through a later partial shorthand. A browser resets it
    to `medium`. Invisible on any page that writes its shorthands in full,
    and silently wrong on the ones that do not.
    """
    style = style_of(
        BODY_P, "p", "p { border: 5px solid red } p { border: solid blue }"
    )
    assert style.border_top_width == Length(3, "px")   # medium, not 5px
    assert style.border_top_style == "solid"
    assert style.border_top_color == Color(0, 0, 255, 1.0)


def test_a_partial_shorthand_reset_reaches_every_side():
    """The reset is per longhand, not per shorthand: all four sides of all
    three components."""
    style = style_of(
        BODY_P,
        "p",
        "p { border: 7px dashed red } p { border: dotted }",
    )
    for side in ("top", "right", "bottom", "left"):
        assert style.get(f"border-{side}-width") == Length(3, "px"), side
        assert style.get(f"border-{side}-style") == "dotted", side
        # `border`'s omitted colour resets to `currentcolor`, i.e. black.
        assert style.get(f"border-{side}-color") == Color(0, 0, 0, 1.0), side


def test_the_shorthand_reset_respects_the_cascade_rather_than_overwriting():
    """The reset values enter the cascade with the *same* rank, specificity
    and source order as the shorthand that produced them, so a more specific
    earlier rule still wins.

    Injection: applying the reset directly to the ComputedStyle after the
    cascade instead of through it makes `#x`'s 5px lose to `p`'s reset.
    """
    style = style_of(
        '<!DOCTYPE html><body><p id="x">hi</p></body>',
        "p",
        "#x { border: 5px solid red } p { border: solid blue }",
    )
    assert style.border_top_width == Length(5, "px")
    assert style.border_top_color == Color(255, 0, 0, 1.0)


def test_a_margin_shorthand_reset_is_a_no_op_because_it_sets_every_side():
    """The one-to-four-value rule always produces all four sides, so the
    reset table entry for `margin` can never fire. Pinned so that stays
    true if the expansion is ever changed."""
    style = style_of(BODY_P, "p", "p { margin: 1px 2px 3px 4px } p { margin: 9px }")
    for side in ("top", "right", "bottom", "left"):
        assert style.get(f"margin-{side}") == Length(9, "px"), side


def test_border_width_falls_back_to_medium_when_a_style_is_specified():
    """`border: solid red` specifies a style and a colour and leaves the
    width to its initial value, `medium` -- 3px, which a browser paints.

    An earlier version of this module used a single `Length(0, "px")`
    initial and justified it on the grounds that the style is `none` so the
    used width is zero regardless. That reasoning is false exactly here: the
    style *is* specified.
    """
    style = style_of(BODY_P, "p", "p { border: solid red }")
    assert style.border_top_width == Length(3, "px")
    assert style.border_top_style == "solid"


def test_a_border_with_no_style_computes_to_zero_width():
    """The other half of the same rule (CSS 2.1 section 8.5.1): a width is
    zero when the style is `none` or `hidden`, whatever the width said.

    Injection: making `medium` the sole initial gives every element on the
    page a 3px border; dropping the zeroing step gives `border: 5px red` a
    5px border a browser does not paint.
    """
    assert style_of(BODY_P, "p", "p { border: 5px red }").border_top_width == Length(
        0, "px"
    )
    assert style_of(BODY_P, "p", "p { border: 5px hidden red }").border_top_width == (
        Length(0, "px")
    )
    assert style_of(BODY_P, "p", "p { border: 5px solid red }").border_top_width == (
        Length(5, "px")
    )


def test_an_element_with_no_border_has_zero_width_borders():
    """The default case, which the `medium` initial must not disturb.

    The colour is asserted too: an element that declares no border at all
    never goes through the shorthand reset, so its `border-*-color` comes
    from the `currentcolor` seeding step instead. Nothing paints it today,
    but it is the value a `getComputedStyle` equivalent would report, and
    without this assertion the seeding step has no test at all.
    """
    style = style_of(BODY_P, "p", "p { color: blue }")
    for side in ("top", "right", "bottom", "left"):
        assert style.get(f"border-{side}-width") == Length(0, "px"), side
        assert style.get(f"border-{side}-style") == "none", side
        assert style.get(f"border-{side}-color") == Color(0, 0, 255, 1.0), side


def test_a_partial_shorthand_in_a_style_attribute_resets_too():
    """The reset lives at both declaration sources, not just in stylesheets.

    Injection: dropping `_reset_omitted_longhands` from
    `_parse_inline_style` only -- which is the half of the fix most likely
    to be forgotten, since the two call sites are 40 lines apart.
    """
    style = style_of(
        '<!DOCTYPE html><body><p style="border: dotted blue">hi</p></body>',
        "p",
        "p { border: 5px solid red }",
    )
    assert style.border_top_width == Length(3, "px")
    assert style.border_top_style == "dotted"
    assert style.border_top_color == Color(0, 0, 255, 1.0)


def test_border_colour_defaults_to_the_elements_own_colour():
    """`border-*-color`'s initial value is `currentcolor`, so an element
    that declares a border without a colour borders in its own text colour
    -- not in black, and not in its parent's colour.

    Injection: seeding the border colours from `parent.color`, or leaving
    the ComputedStyle default at black, both turn this red.
    """
    style = style_of(
        "<!DOCTYPE html><body><div><p>hi</p></div></body>",
        "p",
        "div { color: red } p { color: blue; border: 1px solid }",
    )
    assert style.border_top_color == Color(0, 0, 255, 1.0)
    assert isinstance(style.border_top_color, Color)


def test_an_explicit_border_colour_still_beats_the_currentcolor_default():
    style = style_of(BODY_P, "p", "p { color: blue; border: 1px solid red }")
    assert style.border_top_color == Color(255, 0, 0, 1.0)


def test_ua_gives_every_table_element_its_table_display():
    """A UA sheet that makes `<table>` a table and leaves `<tr>`/`<td>`
    inline is worse than one that says nothing: the container establishes a
    formatting context its own children then ignore.

    Injection: removing any one line of the Tables block leaves that element
    at the initial `inline`.
    """
    doc = styled(
        "<!DOCTYPE html><body><table><caption>c</caption>"
        "<colgroup><col></colgroup>"
        "<thead><tr><th>h</th></tr></thead>"
        "<tbody><tr><td>d</td></tr></tbody>"
        "<tfoot><tr><td>f</td></tr></tfoot></table></body>"
    )
    expected = {
        "table": "table",
        "caption": "table-caption",
        "colgroup": "table-column-group",
        "col": "table-column",
        "thead": "table-header-group",
        "tbody": "table-row-group",
        "tfoot": "table-footer-group",
        "tr": "table-row",
        "td": "table-cell",
        "th": "table-cell",
    }
    for tag, display in expected.items():
        assert find(doc, tag).computed_style.display == display, tag


@pytest.mark.parametrize("name", ["hn", "wikipedia"])
def test_the_corpus_tables_are_not_inline_runs(name):
    """The corpus is why this matters: hn.html has 4 tables, 98 `tr` and 159
    `td`; wikipedia.html has 24, 120 and 159. All of them would collapse
    into inline runs in Phase 3 without the Tables block."""
    path = Path(__file__).resolve().parents[2] / "data" / "corpus" / f"{name}.html"
    if not path.exists():  # pragma: no cover - corpus is checked in
        pytest.skip(f"{path} missing")
    doc = parse(path.read_text(encoding="utf-8", errors="replace"))
    style_document(doc, [])
    seen = Counter()
    stack = [doc]
    while stack:
        n = stack.pop()
        tag = getattr(n, "tag_name", None)
        if tag in ("table", "tr", "td", "th"):
            seen[tag] += 1
            assert n.computed_style.display != "inline", (tag, n.computed_style.display)
        stack.extend(n.children)
    assert seen["table"] > 0 and seen["tr"] > 50 and seen["td"] > 50, seen


def test_a_keyword_with_no_computed_value_rule_is_an_error_not_a_string():
    """`_computed_value` unwraps a Keyword to `str` only for the properties
    whose computed value *is* the keyword. A keyword on any other property
    means a property was added to `values.py` without a computed-value
    decision here, and stringifying it silently is how a property ends up
    half-implemented.

    Nothing a stylesheet can contain reaches this today -- the nine
    properties' only keyword producers are `display`, `border-*-style` and
    `currentcolor` -- so it can only fire on a code change.
    """
    kwargs = dict(font_px=16.0, root_px=16.0, own_color=Color(0, 0, 0, 1.0))
    assert cascade_module._computed_value("display", Keyword("block"), **kwargs) == "block"
    assert (
        cascade_module._computed_value("border-top-style", Keyword("solid"), **kwargs)
        == "solid"
    )
    assert cascade_module._computed_value(
        "background-color", Keyword("currentcolor"), **kwargs
    ) == Color(0, 0, 0, 1.0)
    with pytest.raises(ValueError, match="no computed-value rule"):
        cascade_module._computed_value("width", Keyword("banana"), **kwargs)


def test_rem_is_defined_by_the_root_element_not_by_a_stray_orphan():
    """`root_font_px` must follow the document element, not "any element
    whose parent is not an Element".

    The tree builder never produces a second element child of the Document,
    but a hand-built tree can, and letting one redefine `rem` for everything
    after it would be a silent, document-wide wrong number.
    """
    from mayshay.dom.node import Element as DomElement

    doc = parse('<!DOCTYPE html><html><body></body></html>')
    stray = DomElement("div", {"style": "font-size: 40px"})
    inner = DomElement("span", {"style": "width: 1rem"})
    stray.append_child(inner)
    doc.append_child(stray)

    style_document(doc, ["html { font-size: 20px }"])
    assert find(doc, "html").computed_style.font_size == Length(20, "px")
    assert find(doc, "div").computed_style.font_size == Length(40, "px")
    # 1rem is the ROOT's 20px, not the stray parent's 40px.
    assert inner.computed_style.width == Length(20, "px")
