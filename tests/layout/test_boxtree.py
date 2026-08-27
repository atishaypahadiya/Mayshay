"""Box tree construction.

The corpus is nearly useless as a test here: 8,593 elements contain only 28
mixed block/inline containers and 34 inline-containing-block sites, so a
corpus run passes whatever is written. Every test below is therefore
synthetic and adversarial, and the corpus run in
`scripts/layout_report.py` is a smoke test rather than evidence.

Over-generation is as wrong as under-generation and only a negative test
catches it, so the anonymous-box cases come in pairs: one that must produce
a box and one that must not.
"""

from __future__ import annotations

import pytest

from mayshay.cssparse.cascade import style_document
from mayshay.dom.node import Element, Text
from mayshay.htmlparse.treebuilder import parse
from mayshay.layout.boxtree import (
    GRID_FALLBACK,
    INLINE_LEVEL,
    Box,
    assign_dom_identity,
    build_box_tree,
)


def built(html, css=""):
    document = parse(f"<style>{css}</style>{html}" if css else html)
    style_document(document, [])
    return build_box_tree(document)


def find(box, path_suffix):
    for b in box.walk():
        if b.path and b.path.endswith(path_suffix):
            return b
    raise AssertionError(f"no box at ...{path_suffix}")


def kids(box):
    return [(b.display, b.origin) for b in box.children]


# --- display: none prunes by non-descent --------------------------------


class _Exploding(Element):
    """An element that raises if anything asks for its computed style.

    This is the whole point of the non-descent test: an unvisited node and a
    discarded one are indistinguishable in the output tree, so asserting on
    the box count cannot tell them apart. Asserting that the node was never
    *touched* can.

    `_count_pruned` deliberately walks hidden subtrees to count them, but it
    only tests `isinstance(child, Element)` below a pruning root -- it never
    reads `computed_style` there. So this raises if and only if the box
    builder descended.
    """

    @property
    def computed_style(self):
        raise AssertionError("box builder descended into a display:none subtree")

    @computed_style.setter
    def computed_style(self, value):
        pass


def test_display_none_subtree_is_never_entered():
    document = parse("<div id=hide><span>x</span></div>")
    style_document(document, ["#hide { display: none }"])
    host = next(
        n for n in _walk(document) if isinstance(n, Element) and n.attrs.get("id") == "hide"
    )
    boom = _Exploding("b")
    boom.parent = host
    host.children.append(boom)
    # Raises via _Exploding if the builder walks in.
    root, metrics = build_box_tree(document)
    assert metrics["boxes_pruned_roots"] >= 1
    assert not any(b.node is boom for b in root.walk())


def _walk(node):
    yield node
    for child in node.children:
        yield from _walk(child)


def test_a_hidden_subtree_contributes_no_boxes_at_any_depth():
    root, metrics = built("<div id=h><p>a</p><p>b<span>c</span></p></div><p>after</p>",
                          "#h { display: none }")
    texts = [b for b in root.walk() if b.origin == "text"]
    assert [b.node.data for b in texts] == ["after"]


def test_pruned_roots_and_pruned_total_are_different_numbers():
    """The census figure, the root count and the total are three different
    populations. Conflating them is how '519 roots carrying 954' got into a
    planning document."""
    root, metrics = built("<div id=h><p>a</p><p>b</p></div>", "#h { display: none }")
    # <head> is display:none from the UA sheet, plus our #h.
    assert metrics["boxes_pruned_roots"] == 2
    # #h itself plus its two <p> children, plus <head> and its <style>.
    assert metrics["boxes_pruned_total"] == 5
    assert metrics["boxes_pruned_total"] > metrics["boxes_pruned_roots"]


def test_a_nested_hidden_element_is_not_counted_as_a_second_root():
    root, metrics = built("<div id=a><div id=b>x</div></div>",
                          "#a { display: none } #b { display: none }")
    roots_before = metrics["boxes_pruned_roots"]
    root2, m2 = built("<div id=a><div id=b>x</div></div>", "#a { display: none }")
    assert roots_before == m2["boxes_pruned_roots"], (
        "a hidden element inside a hidden subtree must not add a root"
    )


# --- anonymous blocks: positive and negative pairs -----------------------


def test_mixed_children_wrap_each_inline_run_separately():
    root, _ = built("<div>text<p>x</p>more</div>")
    div = find(root, "/div[1]")
    assert kids(div) == [
        ("block", "anonymous"),
        ("block", "element"),
        ("block", "anonymous"),
    ], "two runs must give two anonymous blocks, not one wrapping everything"


def test_consecutive_blocks_generate_no_anonymous_box():
    """The negative half. Over-generation is as wrong as under-generation."""
    root, metrics = built("<div><p>a</p><p>b</p></div>")
    div = find(root, "/div[1]")
    assert kids(div) == [("block", "element"), ("block", "element")]
    assert metrics["boxes_anonymous"] == 0


def test_an_all_inline_container_generates_no_anonymous_box():
    root, metrics = built("<div>a<span>b</span>c</div>")
    div = find(root, "/div[1]")
    assert all(b.origin != "anonymous" for b in div.children)
    assert metrics["boxes_anonymous"] == 0


def test_whitespace_only_text_between_blocks_generates_nothing():
    r"""CSS 2.1 9.2.1.1: white space that would be collapsed away does not
    produce an anonymous inline box. A newline between two `<div>`s is the
    single most common shape in real markup."""
    root, metrics = built("<div><p>a</p>\n  <p>b</p></div>")
    div = find(root, "/div[1]")
    assert kids(div) == [("block", "element"), ("block", "element")]
    assert metrics["boxes_anonymous"] == 0
    assert metrics["boxes_blank_text_discarded"] >= 1


def test_whitespace_beside_real_inline_content_is_kept():
    """The counterpart: a blank text node between two inlines is a real word
    separator, which is why blank text cannot simply be dropped at parse
    time."""
    root, _ = built("<div><span>a</span> <span>b</span><p>block</p></div>")
    div = find(root, "/div[1]")
    anon = [b for b in div.children if b.origin == "anonymous"]
    assert len(anon) == 1
    assert [b.origin for b in anon[0].children] == ["element", "text", "element"]
    assert anon[0].children[1].node.data == " "


# --- inline splitting ----------------------------------------------------


def test_an_inline_containing_a_block_is_split_around_it():
    root, metrics = built("<div><span>a<div>b</div>c</span></div>")
    outer = find(root, "/div[1]")
    displays = [(b.display, b.origin) for b in outer.children]
    assert metrics["boxes_inline_split"] == 1
    # The two inline fragments carry the SAME identity path, different
    # fragment numbers -- that is what makes them comparable against
    # Chrome's getContentQuads, which returns one quad per fragment.
    frags = [b for b in outer.walk() if b.path and b.path.endswith("/span[1]")]
    assert len(frags) == 2
    assert {f.fragment for f in frags} == {0, 1}
    assert len({f.path for f in frags}) == 1


def test_an_inline_containing_only_inlines_is_not_split():
    root, metrics = built("<div><span>a<em>b</em>c</span></div>")
    assert metrics["boxes_inline_split"] == 0
    assert metrics["boxes_inline_fragments"] == 0


# --- grid fallback -------------------------------------------------------


@pytest.mark.parametrize("declared,expected", sorted(GRID_FALLBACK.items()))
def test_grid_falls_back_and_is_counted(declared, expected):
    root, metrics = built(f"<div id=g>x</div>", f"#g {{ display: {declared} }}")
    box = find(root, "/div[1]")
    assert box.display == expected
    assert metrics["boxes_grid_fallback"] == 1


def test_a_page_with_no_grid_reports_zero_not_absent():
    _, metrics = built("<div>x</div>")
    assert metrics["boxes_grid_fallback"] == 0
    assert "boxes_grid_fallback" in metrics


# --- identity ------------------------------------------------------------


def test_identity_is_ordinal_plus_path_plus_fragment():
    root, _ = built("<div><p>a</p><p>b</p></div>")
    p1, p2 = [b for b in root.walk() if b.path and "/p[" in b.path]
    assert p1.path.endswith("/p[1]") and p2.path.endswith("/p[2]")
    assert p1.ordinal < p2.ordinal
    assert p1.identity() == (p1.ordinal, p1.path, 0)


def test_hidden_elements_still_consume_an_ordinal():
    """Chrome's DOM contains display:none elements, so an identity scheme
    that skipped them would drift out of step with CDP on any page that
    hides anything -- which is every page in the corpus."""
    document = parse("<div id=h>x</div><p>y</p>")
    style_document(document, ["#h { display: none }"])
    ids = assign_dom_identity(document)
    root, _ = build_box_tree(document)
    p = find(root, "/p[1]")
    hidden = next(
        n for n in _walk(document) if isinstance(n, Element) and n.attrs.get("id") == "h"
    )
    assert ids[id(hidden)][0] < ids[id(p.node)][0]
    assert p.ordinal == ids[id(p.node)][0]


def test_anonymous_boxes_are_excluded_from_comparison_but_counted():
    root, metrics = built("<div>text<p>x</p></div>")
    anon = [b for b in root.walk() if b.origin == "anonymous"]
    assert anon
    assert metrics["boxes_anonymous"] == len(anon)
    for b in anon:
        assert b.is_comparable is False
        assert b.identity() is None


def test_paths_use_per_tag_sibling_indices_like_xpath():
    root, _ = built("<div><span>a</span><em>b</em><span>c</span></div>")
    paths = sorted(b.path for b in root.walk() if b.path and b.path.count("/") == 4)
    assert paths == [
        "/html[1]/body[1]/div[1]/em[1]",
        "/html[1]/body[1]/div[1]/span[1]",
        "/html[1]/body[1]/div[1]/span[2]",
    ]


def test_every_element_box_has_an_identity_and_every_text_box_does_not():
    root, _ = built("<div>a<p>b</p></div>")
    for b in root.walk():
        if b.origin == "element":
            assert b.identity() is not None, b
        else:
            assert b.identity() is None, b


def test_an_inline_with_only_block_children_dissolves_rather_than_splits():
    """`<span><div>x</div></span>` is not split around anything -- there is
    no inline content to break. The span contributes no box at all.

    Counted separately from a real split because one name for both
    over-claims: the corpus has 34 of these shapes and only 2 of them
    produce a fragment. It matters for the Chrome comparison too -- a
    dissolved inline has no box on our side while CDP still answers
    getBoxModel for that node, so it is a known non-comparable rather than
    a mismatch.
    """
    root, metrics = built("<div><span><p>x</p></span></div>")
    assert metrics["boxes_inline_dissolved"] == 1
    assert metrics["boxes_inline_split"] == 0
    assert metrics["boxes_inline_fragments"] == 0
    assert not [b for b in root.walk() if b.path and b.path.endswith("/span[1]")]


def test_a_real_split_is_counted_as_a_split_and_not_as_dissolved():
    root, metrics = built("<div><span>a<p>x</p>b</span></div>")
    assert metrics["boxes_inline_split"] == 1
    assert metrics["boxes_inline_fragments"] == 2
    assert metrics["boxes_inline_dissolved"] == 0


def test_dissolved_inlines_are_recorded_as_known_non_comparables():
    """The Chrome harness must be able to EXCLUDE these by identity, not
    just know how many there are. CDP answers getBoxModel for a node we
    produce no box for, so an unrecorded dissolved inline reads as a layout
    failure rather than a question that does not apply.
    """
    seen = []
    root, metrics = built_recording("<div><span><p>x</p></span></div>", seen)
    assert metrics["boxes_inline_dissolved"] == 1
    assert len(seen) == 1
    assert seen[0]["path"].endswith("/span[1]")
    assert seen[0]["reason"] == "inline-dissolved"
    assert isinstance(seen[0]["ordinal"], int)


def test_a_real_split_is_not_recorded_as_non_comparable():
    """A split inline HAS boxes -- one per fragment -- so it is comparable
    and must not be excluded. Only the no-box case is."""
    seen = []
    _, metrics = built_recording("<div><span>a<p>x</p>b</span></div>", seen)
    assert metrics["boxes_inline_split"] == 1
    assert seen == []


def built_recording(html, sink, css=""):
    document = parse(f"<style>{css}</style>{html}" if css else html)
    style_document(document, [])
    return build_box_tree(document, non_comparable=sink)
