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


# -- the four adoption-agency early exits ----------------------------------
#
# _in_body_end's formatting branch has four arms, and no single observable
# separates them. The formatting list is empty afterwards on three of the
# four; the open-elements stack ends as ['html', 'body'] on several; and the
# serialized tree is shared by others. An earlier version of these tests
# asserted `active_formatting == []` and so passed for two different arms at
# once -- it claimed to cover step 4.4 while actually exercising 4.7.
#
# _afe_probe therefore returns three observables at once, and
# test_formatting_end_tag_branches_are_distinguishable asserts the four
# inputs are pairwise distinct under it. That assertion is the real guard:
# without it, the per-step tests below are just four spellings of "nothing
# crashed".

# Inputs chosen so each one takes a different arm. Keep them in sync with the
# per-step tests; the distinctness test will fail loudly if they drift.
AFE_STEP_INPUTS = {
    # 4.3  no <b> on the list at all -> the "any other end tag" stack walk,
    #      which stops dead at the special <div> and drops the token.
    "4.3": "<div></b>x",
    # 4.4  </div> pops through the <b>, leaving it on the list but off the
    #      stack -> drop the entry. If the entry survived, "y" would be
    #      reconstructed into a second <b>.
    "4.4": "<div><b>text</div></b>y",
    # 4.5  <table> is a scope barrier, so the <b> is on the stack but out of
    #      scope -> parse error, KEEP the entry.
    "4.5": "<b><table></b>x",
    # 4.7  ordinary close: on the stack and in scope -> pop to it, drop the
    #      entry.
    "4.7": "<b><p>a</p></b>x",
}


def _afe_probe(src):
    """Observe *how* a formatting end tag was handled, not just the result.

    Returns (the "any other end tag" walk ran for </b>, the formatting list
    as tag names, the serialized tree). Step 4.3 is invisible in the tree
    today -- with no <b> on the open-elements stack the walk has nothing to
    pop -- so watching for the call is the only thing that separates it from
    4.4. Verified by mutation: swapping any one arm for its neighbour changes
    exactly this probe, for exactly the one input that takes that arm.
    """
    from mayshay.htmlparse.treebuilder import TreeBuilder

    builder = TreeBuilder(src)
    walked = []
    real = builder._any_other_end_tag

    def spy(token):
        walked.append(token.name)
        return real(token)

    builder._any_other_end_tag = spy
    document = builder.build()
    return (
        "b" in walked,
        [e.tag_name if e is not None else None for e in builder.active_formatting],
        serialize(document),
    )


def test_formatting_end_tag_branches_are_distinguishable():
    """No two of the four inputs may look alike under _afe_probe.

    This is the test that would have caught the earlier mislabelled case:
    its input and the 4.7 input were indistinguishable by the assertion used.
    """
    probes = {step: _afe_probe(src) for step, src in AFE_STEP_INPUTS.items()}
    for left in AFE_STEP_INPUTS:
        for right in AFE_STEP_INPUTS:
            if left < right:
                assert probes[left] != probes[right], (
                    f"steps {left} and {right} are indistinguishable; a test "
                    f"naming either one is not testing it"
                )


def test_formatting_end_tag_step_4_3_falls_to_any_other_end_tag():
    """No <b> on the list -> the "any other end tag" walk, which the special
    <div> stops. Only this arm calls that walk."""
    walked, formatting, document = _afe_probe(AFE_STEP_INPUTS["4.3"])
    assert walked is True
    assert formatting == []
    assert document == (
        "| <html>\n"
        "|   <head>\n"
        "|   <body>\n"
        "|     <div>\n"
        '|       "x"'
    )


def test_formatting_end_tag_step_4_4_drops_an_entry_that_left_the_stack():
    """</div> pops through the <b>; the </b> then drops the orphaned entry.

    The discriminating assertion is the bare "y": if the entry survived (the
    4.5 arm) it would be reconstructed into a second <b>.
    """
    walked, formatting, document = _afe_probe(AFE_STEP_INPUTS["4.4"])
    assert walked is False
    assert formatting == []
    assert document == (
        "| <html>\n"
        "|   <head>\n"
        "|   <body>\n"
        "|     <div>\n"
        "|       <b>\n"
        '|         "text"\n'
        '|     "y"'
    )


def test_formatting_end_tag_step_4_5_keeps_an_out_of_scope_entry():
    """<table> is a scope barrier, so </b> cannot close the <b> -- and, per
    the spec, must not remove its list entry either. The surviving entry is
    what separates this arm from all three others."""
    walked, formatting, _ = _afe_probe(AFE_STEP_INPUTS["4.5"])
    assert walked is False
    assert formatting == ["b"]


def test_formatting_end_tag_step_4_7_pops_to_the_element():
    """The ordinary close: on the stack and in scope -> pop to it and drop
    the entry. "x" lands in <body>, outside the closed <b>.

    Previously mislabelled as step 4.4: the </p> pops only the <p>, so the
    <b> is still on the stack when </b> arrives and this arm runs, not 4.4.
    """
    walked, formatting, document = _afe_probe(AFE_STEP_INPUTS["4.7"])
    assert walked is False
    assert formatting == []
    assert document == (
        "| <html>\n"
        "|   <head>\n"
        "|   <body>\n"
        "|     <b>\n"
        "|       <p>\n"
        '|         "a"\n'
        '|     "x"'
    )


def test_formatting_end_tag_over_pops_a_furthest_block():
    """Pins CURRENT behaviour, which the adoption agency will change.

    </b> here has a furthest block (<div>), so the spec reparents: the <div>
    keeps its place and a fresh <b> is created inside it to hold "x". We
    instead pop straight through the div and drop "x" into <body>. Routing
    formatting end tags through the scope check rather than the "any other
    end tag" stack walk is what makes this the failure mode; the test exists
    so that landing the adoption agency shows up as a deliberate diff.
    """
    assert tree("<b><div></b>x") == (
        "| <html>\n"
        "|   <head>\n"
        "|   <body>\n"
        "|     <b>\n"
        "|       <div>\n"
        '|     "x"'
    )


def test_search_closes_an_open_p_and_does_not_reconstruct():
    """<search> is in CLOSES_P, so it closes the <p> and, like every other
    p-closing block element, does not re-open <b> around itself."""
    assert tree("<p><b>a<search>b") == (
        "| <html>\n"
        "|   <head>\n"
        "|   <body>\n"
        "|     <p>\n"
        "|       <b>\n"
        '|         "a"\n'
        "|     <search>\n"
        "|       <b>\n"
        '|         "b"'
    )


def test_noscript_reconstructs_because_scripting_is_disabled():
    """This parser models scripting as disabled, so <noscript> is an ordinary
    element: it hits the "any other start tag" catch-all, which reconstructs."""
    result = parse("<p><b>a</p><noscript>b")
    body = result.document_element.children[1]
    # The second <b> is the reconstructed one, and the noscript sits inside it.
    assert [c.tag_name for c in body.children] == ["p", "b"]
    reopened = body.children[1]
    assert [c.tag_name for c in reopened.children] == ["noscript"]
    assert reopened.children[0].children[0].data == "b"
