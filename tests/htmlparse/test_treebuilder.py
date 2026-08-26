import pytest

from mayshay.dom.node import serialize
from mayshay.htmlparse.treebuilder import parse


def tree(src):
    return serialize(parse(src))


def test_implicit_html_head_body():
    assert tree("<p>hi") == (
        "| <html>\n"
        "|   <head>\n"
        "|   <body>\n"
        "|     <p>\n"
        '|       "hi"'
    )


def test_empty_input_still_builds_the_skeleton():
    assert tree("") == "| <html>\n|   <head>\n|   <body>"


def test_title_goes_in_head():
    assert tree("<title>x</title>") == (
        "| <html>\n"
        "|   <head>\n"
        "|     <title>\n"
        '|       "x"\n'
        "|   <body>"
    )


def test_p_does_not_nest():
    assert tree("<p>a<p>b") == (
        "| <html>\n"
        "|   <head>\n"
        "|   <body>\n"
        "|     <p>\n"
        '|       "a"\n'
        "|     <p>\n"
        '|       "b"'
    )


def test_li_siblings_not_nested():
    result = parse("<ul><li>a<li>b</ul>")
    ul = result.document_element.children[1].children[0]
    assert [c.tag_name for c in ul.children] == ["li", "li"]


def test_void_element_has_no_children_and_leaves_no_stack_entry():
    result = parse("<img src=x><p>after")
    body = result.document_element.children[1]
    assert [c.tag_name for c in body.children] == ["img", "p"]
    assert body.children[0].children == []


def test_self_closing_br():
    result = parse("<br/>")
    body = result.document_element.children[1]
    assert [c.tag_name for c in body.children] == ["br"]


def test_unclosed_span_is_closed_by_parent_end_tag():
    result = parse("<div><span></div><p>x")
    body = result.document_element.children[1]
    assert [c.tag_name for c in body.children] == ["div", "p"]


def test_comment_before_html_attaches_to_document():
    from mayshay.dom.node import Comment

    result = parse("<!-- c --><p>x")
    assert isinstance(result.children[0], Comment)
    assert result.children[0].data == " c "


def test_doctype_becomes_a_node():
    assert tree("<!DOCTYPE html><p>x").startswith("| <!DOCTYPE html>\n| <html>")


def test_stray_end_p_inserts_an_empty_p():
    """Genuine spec behaviour, and a good canary for the in_body mode."""
    result = parse("</p>")
    body = result.document_element.children[1]
    assert [c.tag_name for c in body.children] == ["p"]


def test_raw_text_element_that_is_not_a_head_element_goes_in_body():
    """<textarea> is RCDATA but is not a head element.

    Regression: in_head used to dispatch on RCDATA_ELEMENTS before checking
    HEAD_ELEMENTS, which silently promoted textarea, xmp, iframe and noembed
    into <head>.
    """
    assert tree("<textarea>x</textarea>") == (
        "| <html>\n"
        "|   <head>\n"
        "|   <body>\n"
        "|     <textarea>\n"
        '|       "x"'
    )


def test_raw_text_start_tag_still_closes_an_open_p():
    """<xmp> closes an open <p> before the generic raw text algorithm runs.

    Regression: in_body used to dispatch on RAWTEXT_ELEMENTS before the
    CLOSES_P check, so the xmp nested inside the p instead of closing it.
    tests1.dat never reaches this, so the corpus cannot catch it.
    """
    result = parse("<p>a<xmp>b")
    body = result.document_element.children[1]
    assert [c.tag_name for c in body.children] == ["p", "xmp"]
    assert body.children[1].children[0].data == "b"


def test_raw_text_element_that_does_not_close_p_still_does_not():
    """The mirror of the above: iframe is raw text but has no p-closing rule,
    so a fix that closed <p> for every raw-text element would be wrong too."""
    result = parse("<p>a<iframe>b")
    body = result.document_element.children[1]
    assert [c.tag_name for c in body.children] == ["p"]
    assert [c.tag_name for c in body.children[0].children if hasattr(c, "tag_name")] == [
        "iframe"
    ]


def test_parse_time_metric_has_sub_millisecond_resolution():
    """int() truncation made this read 0.0 for essentially every parse."""
    from mayshay.htmlparse.treebuilder import TreeBuilder

    tb = TreeBuilder("<div><p>hi</p></div>" * 200)
    tb.build()
    assert tb.metrics["parse_time_ms"] > 0.0


def test_metrics_are_emitted():
    from mayshay.htmlparse.treebuilder import TreeBuilder

    tb = TreeBuilder("<div><p>hi</p></div>")
    tb.build()
    assert tb.metrics["elements"] == 5   # html, head, body, div, p
    assert tb.metrics["max_depth"] >= 4
    assert "parse_time_ms" in tb.metrics


@pytest.mark.xfail(reason="adoption agency not implemented; Task 7 + future work")
def test_misnested_formatting_tags():
    result = parse("<b><i></b></i>x")
    body = result.document_element.children[1]
    assert [c.tag_name for c in body.children] == ["b", "i"]


@pytest.mark.xfail(reason="table insertion modes out of scope for phase 1")
def test_table_structure():
    result = parse("<table><tr><td>x</table>")
    table = result.document_element.children[1].children[0]
    assert table.children[0].tag_name == "tbody"


# -- active formatting elements (Task 7) -----------------------------------


def test_formatting_reconstructed_across_block_boundary():
    """<b> must re-open inside the second <p>, or the bold silently vanishes."""
    result = parse("<p><b>one<p>two")
    body = result.document_element.children[1]
    first, second = body.children
    assert [c.tag_name for c in first.children] == ["b"]
    assert [c.tag_name for c in second.children] == ["b"]
    assert second.children[0].children[0].data == "two"


def test_noahs_ark_limits_identical_entries():
    from mayshay.htmlparse.treebuilder import TreeBuilder

    tb = TreeBuilder('<b><b><b><b>x')
    tb.build()
    # At most three identical formatting entries survive on the list.
    bolds = [e for e in tb.active_formatting if e is not None and e.tag_name == "b"]
    assert len(bolds) <= 3


def test_formatting_list_cleared_by_end_tag():
    from mayshay.htmlparse.treebuilder import TreeBuilder

    tb = TreeBuilder("<b>x</b>y")
    tb.build()
    assert all(e is None or e.tag_name != "b" for e in tb.active_formatting)


def test_reconstruction_is_idempotent():
    """Repeated reconstruction with nothing to do must not clone anything.

    reconstruct_formatting rewrites list entries as it clones them; if it
    failed to, every subsequent character token would re-open another <b>.
    """
    from mayshay.htmlparse.treebuilder import TreeBuilder

    tb = TreeBuilder("<p><b>one<p>two three four")
    tb.build()
    body = tb.document.document_element.children[1]
    second = body.children[1]
    assert [c.tag_name for c in second.children] == ["b"]
    assert second.children[0].children[0].data == "two three four"
    # And an explicit no-op call changes nothing.
    before = list(tb.active_formatting)
    depth = len(tb.open_elements)
    tb.reconstruct_formatting()
    tb.reconstruct_formatting()
    assert tb.active_formatting == before
    assert len(tb.open_elements) == depth


def test_marker_stops_reconstruction():
    """<object> pushes a marker, so <b> is not re-opened inside it."""
    result = parse("<b>one<object><p>two")
    body = result.document_element.children[1]
    b = body.children[0]
    assert b.tag_name == "b"
    obj = b.children[1]
    assert obj.tag_name == "object"
    # The <p> is a direct child of the object, not wrapped in a fresh <b>.
    assert [c.tag_name for c in obj.children] == ["p"]
    # "two" is a direct child of the <p>, not wrapped in a re-opened <b>.
    assert obj.children[0].children[0].data == "two"


def test_end_tag_clears_formatting_to_marker():
    from mayshay.htmlparse.treebuilder import TreeBuilder

    tb = TreeBuilder("<object><b>x</object>y")
    tb.build()
    # Both the marker and the <b> pushed after it are gone.
    assert tb.active_formatting == []


def test_noahs_ark_only_matches_identical_attributes():
    """The clause keys on tag name *and* attributes, so these all survive."""
    from mayshay.htmlparse.treebuilder import TreeBuilder

    tb = TreeBuilder('<b id=1><b id=2><b id=3><b id=4>x')
    tb.build()
    bolds = [e for e in tb.active_formatting if e is not None]
    assert [e.attrs["id"] for e in bolds] == ["1", "2", "3", "4"]


def test_noahs_ark_evicts_the_earliest_entry():
    """The spec removes the *earliest* of the three, not the latest."""
    from mayshay.htmlparse.treebuilder import TreeBuilder

    tb = TreeBuilder("<b><b><b><b>x")
    tb.build()
    bolds = [e for e in tb.active_formatting if e is not None]
    assert len(bolds) == 3
    body = tb.document.document_element.children[1]
    # The four <b> elements nest; the list keeps the last three of them.
    nested = []
    node = body
    while node.children and getattr(node.children[0], "tag_name", None) == "b":
        node = node.children[0]
        nested.append(node)
    assert len(nested) == 4
    assert [e is n for e, n in zip(bolds, nested[1:])] == [True, True, True]


def test_block_start_tag_does_not_reconstruct():
    """<div> must not re-open <b> around itself.

    Reconstruction belongs to the character/formatting/catch-all rules, not
    to the block elements that close an open <p>.
    """
    result = parse("<p><b>a<div>b")
    body = result.document_element.children[1]
    assert [c.tag_name for c in body.children] == ["p", "div"]
    # Inside the div the <b> *is* re-opened, by the character token.
    div = body.children[1]
    assert [c.tag_name for c in div.children] == ["b"]
    assert div.children[0].children[0].data == "b"


def test_whitespace_only_text_reconstructs():
    """The spec's in-body character rule reconstructs for every character
    token, whitespace included -- html5lib-tests tests15.dat:0 depends on the
    space landing inside the reconstructed <u>."""
    result = parse("<p><b><i><u></p> <p>X")
    body = result.document_element.children[1]
    u = body.children[1].children[0].children[0]
    assert u.tag_name == "u"
    assert u.children[0].data == " "
    assert u.children[1].tag_name == "p"
