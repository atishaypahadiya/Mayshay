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
