import pytest

from mayshay.htmlparse.tokenizer import (
    CharacterToken,
    EndTagToken,
    StartTagToken,
    Tokenizer,
)


def text_of(src):
    return "".join(
        t.data for t in Tokenizer(src).tokenize() if isinstance(t, CharacterToken)
    )


def names(src):
    return [
        t.name
        for t in Tokenizer(src).tokenize()
        if isinstance(t, (StartTagToken, EndTagToken))
    ]


def pairs(src):
    """Full token sequence including ordering.

    text_of() and names() both aggregate and would happily pass while the
    tokenizer emitted a closing tag *before* the text it encloses. These
    assertions pin the order.
    """
    out = []
    for t in Tokenizer(src).tokenize():
        if isinstance(t, CharacterToken):
            out.append(("text", t.data))
        elif isinstance(t, StartTagToken):
            out.append(("start", t.name))
        elif isinstance(t, EndTagToken):
            out.append(("end", t.name))
    return out


def test_text_emitted_before_closing_tag():
    """Covers the '>' appropriate-end-tag branch."""
    assert pairs("<script>x</script>") == [
        ("start", "script"), ("text", "x"), ("end", "script"),
    ]


def test_text_emitted_before_spaced_closing_tag():
    """Covers the whitespace appropriate-end-tag branch."""
    assert pairs("<script>x</script >y") == [
        ("start", "script"), ("text", "x"), ("end", "script"), ("text", "y"),
    ]


def test_text_emitted_before_self_closing_end_tag():
    """Covers the '/' appropriate-end-tag branch."""
    assert pairs("<script>x</script/>") == [
        ("start", "script"), ("text", "x"), ("end", "script"),
    ]


def test_less_than_inside_script_is_text():
    assert text_of("<script>if (a<b) {}</script>") == "if (a<b) {}"


def test_close_tag_string_inside_script_is_text():
    assert text_of('<script>var s = "</div>";</script>') == 'var s = "</div>";'


def test_partial_end_tag_is_text():
    assert text_of("<script>x</scr ipt>y</script>") == "x</scr ipt>y"


def test_end_tag_is_case_insensitive():
    assert names("<script>x</SCRIPT>") == ["script", "script"]


def test_end_tag_with_trailing_space_exits():
    assert names("<script>x</script >p") == ["script", "script"]
    assert text_of("<script>x</script >p") == "xp"


def test_self_closing_solidus_on_end_tag_exits():
    assert names("<script>x</script/>") == ["script", "script"]


def test_style_rawtext():
    assert text_of('<style>a { content: "<b>" }</style>') == 'a { content: "<b>" }'


def test_textarea_content_is_not_tags():
    assert names("<textarea><b>x</b></textarea>") == ["textarea", "textarea"]
    assert text_of("<textarea><b>x</b></textarea>") == "<b>x</b>"


def test_script_comment_escape_states():
    assert text_of("<script><!-- <b> --></script>") == "<!-- <b> -->"


def test_eof_inside_script_emits_text_and_error():
    tk = Tokenizer("<script>abc")
    out = list(tk.tokenize())
    assert "".join(t.data for t in out if isinstance(t, CharacterToken)) == "abc"
    assert tk.errors


def test_returns_to_data_between_scripts():
    assert names("<script>a</script><p>b</p><script>c</script>") == [
        "script", "script", "p", "p", "script", "script",
    ]


@pytest.mark.xfail(reason="double-escaped script states deferred; see Task 3 notes")
def test_double_escaped_script():
    src = "<script><!--<script>foo</script>--></script>"
    assert text_of(src) == "<!--<script>foo</script>-->"


# -- offset / EOF regressions added while implementing Task 3 ---------------

def test_failed_end_tag_starting_a_text_run_carries_source_offset():
    """A failed end tag that *opens* a text run must report the '<' offset.

    _raw_end_tag_name_state only sets _buffer_start when the buffer is empty,
    so this needs `</scr` to come immediately after the start tag. It computes
    the offset from self.pos, so the reconsume (pos -= 1) has to happen
    *before* the arithmetic or every non-EOF exit is one byte too high.
    """
    src = "PREFIX<script></scr ipt>y</script>"
    assert src.index("</scr") == 14
    texts = [t for t in Tokenizer(src).tokenize() if isinstance(t, CharacterToken)]
    run = next(t for t in texts if t.data.startswith("</scr"))
    assert run.pos == 14


def test_failed_end_tag_continuing_a_text_run_keeps_run_offset():
    """When text precedes it, the failed end tag joins the existing run."""
    src = "<script>x</scr ipt>y</script>"
    texts = [t for t in Tokenizer(src).tokenize() if isinstance(t, CharacterToken)]
    run = next(t for t in texts if t.data == "x</scr ipt>y")
    assert run.pos == 8


def test_unmatched_lt_run_in_rawtext_carries_source_offset():
    """The '<' pushed back by _raw_less_than_sign_state starts a fresh run."""
    src = "PREFIX<script><x>foo</script>"
    assert src.index("<x>") == 14
    texts = [t for t in Tokenizer(src).tokenize() if isinstance(t, CharacterToken)]
    run = next(t for t in texts if t.data == "<x>foo")
    assert run.pos == 14


def test_script_comment_run_carries_source_offset():
    """The "<!" pushed back by _raw_less_than_sign_state starts a fresh run.

    `<!--` right after `<script>` is common input, and the '<!' branch is the
    fourth replay path into _buffer -- it needs the same `if not self._buffer`
    guard as the other three or the run inherits the previous run's offset.
    """
    src = "PREFIX<script><!-- x --></script>"
    assert src.index("<!--") == 14
    texts = [t for t in Tokenizer(src).tokenize() if isinstance(t, CharacterToken)]
    run = next(t for t in texts if t.data == "<!-- x -->")
    assert run.pos == 14


def test_non_alpha_after_end_tag_open_carries_source_offset():
    """`</` followed by a non-letter is literal text starting at the '<'."""
    src = "PREFIX<script></1</script>"
    assert src.index("</1") == 14
    texts = [t for t in Tokenizer(src).tokenize() if isinstance(t, CharacterToken)]
    run = next(t for t in texts if t.data == "</1")
    assert run.pos == 14


def test_eof_partway_through_end_tag_name():
    """EOF inside a raw-text end tag name must not crash and must emit text."""
    tk = Tokenizer("<script>x</scr")
    out = list(tk.tokenize())
    assert "".join(t.data for t in out if isinstance(t, CharacterToken)) == "x</scr"
    assert not any(isinstance(t, EndTagToken) for t in out)


def test_eof_partway_through_matching_end_tag_name():
    """Same, but where the partial name is a prefix of the appropriate tag."""
    tk = Tokenizer("<style>x</style")
    out = list(tk.tokenize())
    assert "".join(t.data for t in out if isinstance(t, CharacterToken)) == "x</style"


def test_no_rawtext_tag_attribute_remains():
    assert not hasattr(Tokenizer("x"), "_rawtext_tag")
