import pytest

from mayshay.dom.node import (
    Comment,
    Document,
    DocumentType,
    Element,
    Text,
    annotate_positions,
    serialize,
)
from tests.support.dat import load_tree_tests
from tests.support.marks import requires_corpus


def test_append_child_sets_parent():
    parent, child = Element("div"), Element("span")
    parent.append_child(child)
    assert child.parent is parent
    assert parent.children == [child]


def test_append_child_detaches_from_previous_parent():
    a, b, child = Element("a"), Element("b"), Element("span")
    a.append_child(child)
    b.append_child(child)
    assert child.parent is b
    assert a.children == []
    assert b.children == [child]


def test_insert_before_positions_correctly():
    parent = Element("div")
    first, second = Element("a"), Element("b")
    parent.append_child(second)
    parent.insert_before(first, second)
    assert parent.children == [first, second]


def test_insert_before_rejects_non_child():
    parent, node, stranger = Element("div"), Element("a"), Element("b")
    with pytest.raises(ValueError):
        parent.insert_before(node, stranger)


def test_remove_child_clears_parent():
    parent, child = Element("div"), Element("span")
    parent.append_child(child)
    parent.remove_child(child)
    assert child.parent is None
    assert parent.children == []


def test_remove_child_rejects_non_child():
    with pytest.raises(ValueError):
        Element("div").remove_child(Element("span"))


def test_serializer_matches_html5lib_format():
    doc = Document()
    doc.append_child(DocumentType("html"))
    html = doc.append_child(Element("html"))
    html.append_child(Element("head"))
    body = html.append_child(Element("body"))
    p = body.append_child(Element("p"))
    p.append_child(Text("Hello"))

    assert serialize(doc) == (
        "| <!DOCTYPE html>\n"
        "| <html>\n"
        "|   <head>\n"
        "|   <body>\n"
        "|     <p>\n"
        '|       "Hello"'
    )


def test_serializer_sorts_attributes_on_their_own_lines():
    doc = Document()
    el = doc.append_child(Element("div", {"id": "x", "class": "a"}))
    assert serialize(doc) == (
        "| <div>\n"
        '|   class="a"\n'
        '|   id="x"'
    )


def test_serializer_renders_comments():
    # NOTE: the brief's own hand-written expectation here was
    # `Comment(" hi ")` -> `"| <!-- hi -->"`, which contradicts the brief's
    # own step-4 serializer code: `f"{pad}<!-- {node.data} -->"` already
    # supplies the space on each side of the comment's data, so data that
    # itself starts/ends with a space (as real comment content typically
    # does) doubles up, e.g. `Comment(" hi ")` -> `"| <!--  hi  -->"`. This
    # is confirmed against the real corpus in
    # test_serializer_matches_corpus_comment below: comments01.dat's comment
    # data " BAR " serializes to "<!--  BAR  -->" (double space) in the
    # fixture's #document block. The corpus is ground truth, so this test
    # uses data with no surrounding whitespace to unambiguously exercise
    # single-spacing instead.
    doc = Document()
    doc.append_child(Comment("hi"))
    assert serialize(doc) == "| <!-- hi -->"


def test_deep_tree_does_not_blow_the_stack():
    doc = Document()
    node = doc.append_child(Element("div"))
    for _ in range(5000):
        node = node.append_child(Element("div"))
    assert serialize(doc).count("<div>") == 5001


# --- Corpus-grounded checks ---------------------------------------------
#
# The tests above assert against a hand-written expected string, which only
# checks the serializer against the plan author's memory of the html5lib
# `#document` format. These instead hand-build the tree each fixture's
# #document block describes and check serialize() byte-for-byte against the
# real corpus text, as an independent check on the format (not on a parser -
# no mayshay.htmlparse import happens here). Cases are chosen to cover the
# format's corners: a doctype, a comment (including its exact spacing), and
# an element with multiple attributes (ordering + quoting).


def _find(filename: str, data: str):
    for test in load_tree_tests(filename):
        if test.data == data:
            return test
    raise AssertionError(f"no test with data={data!r} found in {filename}")


@requires_corpus
def test_serializer_matches_corpus_doctype():
    # doctype01.dat: "<!DOCTYPE html>Hello" - simplest possible doctype case.
    fixture = _find("doctype01.dat", "<!DOCTYPE html>Hello")

    doc = Document()
    doc.append_child(DocumentType("html"))
    html = doc.append_child(Element("html"))
    html.append_child(Element("head"))
    body = html.append_child(Element("body"))
    body.append_child(Text("Hello"))

    assert serialize(doc) == fixture.document


@requires_corpus
def test_serializer_matches_corpus_comment():
    # comments01.dat: "FOO<!-- BAR -->BAZ" - exercises the comment's exact
    # leading/trailing space rendering (data " BAR " -> "<!--  BAR  -->").
    fixture = _find("comments01.dat", "FOO<!-- BAR -->BAZ")

    doc = Document()
    html = doc.append_child(Element("html"))
    html.append_child(Element("head"))
    body = html.append_child(Element("body"))
    body.append_child(Text("FOO"))
    body.append_child(Comment(" BAR "))
    body.append_child(Text("BAZ"))

    assert serialize(doc) == fixture.document


@requires_corpus
def test_serializer_matches_corpus_multiple_attributes():
    # isindex.dat: attributes given out of order in the source
    # (name, action, prompt, foo) come out alphabetically sorted in the
    # fixture's #document block - checks both ordering and quoting.
    fixture = _find(
        "isindex.dat",
        '<isindex name="A" action="B" prompt="C" foo="D">',
    )

    doc = Document()
    html = doc.append_child(Element("html"))
    html.append_child(Element("head"))
    body = html.append_child(Element("body"))
    body.append_child(
        Element(
            "isindex",
            {"name": "A", "action": "B", "prompt": "C", "foo": "D"},
        )
    )

    assert serialize(doc) == fixture.document


def test_computed_style_defaults_to_none_on_every_node_type():
    from mayshay.dom.node import Comment, Document, DocumentType, Element, Text

    for node in (Document(), DocumentType("html"), Element("p"), Text("x"), Comment("c")):
        assert node.computed_style is None


def test_class_list_splits_on_whitespace_runs():
    """Real markup: `class="box  wide"` -- two spaces."""
    el = Element("div", {"class": "box  wide"})
    assert el.class_list == frozenset({"box", "wide"})


def test_class_list_handles_tabs_newlines_and_edges():
    el = Element("div", {"class": "  a\tb\nc  "})
    assert el.class_list == frozenset({"a", "b", "c"})


def test_class_list_absent_is_empty():
    assert Element("div").class_list == frozenset()


def test_id_accessor():
    assert Element("div", {"id": "Main"}).id == "Main"
    assert Element("div").id is None


def test_id_case_is_preserved():
    """Attribute names fold; values do not. CSS id matching is case-sensitive."""
    assert Element("div", {"id": "Main"}).id != "main"


def test_element_children_excludes_text_and_comments():
    from mayshay.dom.node import Comment, Text

    div = Element("div")
    div.append_child(Text("\n"))
    a = div.append_child(Element("a"))
    div.append_child(Comment("c"))
    b = div.append_child(Element("b"))
    assert div.element_children == [a, b]


def test_annotate_positions_indexes_elements_only():
    from mayshay.dom.node import Document, Text

    doc = Document()
    div = doc.append_child(Element("div"))
    div.append_child(Text("\n"))
    first = div.append_child(Element("p"))
    div.append_child(Text("\n"))
    second = div.append_child(Element("p"))

    count = annotate_positions(doc)
    assert first.element_index == 0
    assert second.element_index == 1
    assert count == 3


def test_element_index_is_none_before_annotation():
    assert Element("p").element_index is None
