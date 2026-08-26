import pytest

from mayshay.htmlparse.tokenizer import (
    CharacterToken,
    EndTagToken,
    StartTagToken,
    Tokenizer,
)


def toks(src):
    return list(Tokenizer(src).tokenize())


def test_end_tag_with_space_exits_rawtext():
    """</script > must return to data state, not swallow the document."""
    result = toks("<script>x</script >after<p>hi</p>")
    assert any(isinstance(t, StartTagToken) and t.name == "p" for t in result)
    text = [t.data for t in result if isinstance(t, CharacterToken)]
    assert "after<p>hi</p>" not in text


def test_rcdata_and_rawtext_element_sets_are_distinct():
    from mayshay.htmlparse.tokenizer import RAWTEXT_ELEMENTS, RCDATA_ELEMENTS

    assert "title" in RCDATA_ELEMENTS
    assert "textarea" in RCDATA_ELEMENTS
    assert "style" in RAWTEXT_ELEMENTS
    assert not RCDATA_ELEMENTS & RAWTEXT_ELEMENTS


def test_non_ascii_after_lt_is_not_a_tag():
    """The spec means ASCII alpha; Python's isalpha() accepts 'é'."""
    result = toks("<élan>text")
    assert not any(isinstance(t, StartTagToken) for t in result)
    assert "".join(t.data for t in result if isinstance(t, CharacterToken)) == "<élan>text"


def test_crlf_is_normalised_to_lf():
    result = toks("a\r\nb\rc")
    assert "".join(t.data for t in result if isinstance(t, CharacterToken)) == "a\nb\nc"


def test_tokens_carry_source_offsets():
    result = toks("ab<p>cd")
    start = next(t for t in result if isinstance(t, StartTagToken))
    assert start.pos == 2
    first_text = next(t for t in result if isinstance(t, CharacterToken))
    assert first_text.pos == 0


def test_switch_to_is_public():
    tk = Tokenizer("<p>")
    tk.switch_to("rcdata", last_start_tag="title")
    assert tk.state == "rcdata"
    assert tk._last_start_tag == "title"


def test_rawtext_literal_lt_text_run_has_correct_offset():
    """A text run inside rawtext that starts with an unmatched '<' must not
    inherit a stale _buffer_start from an earlier flushed run."""
    result = toks("PREFIX<script><x>foo</script>")
    texts = [t for t in result if isinstance(t, CharacterToken)]
    rawtext_run = next(t for t in texts if t.data == "<x>foo")
    assert rawtext_run.pos == 14


# -- parse-error offsets ----------------------------------------------------
#
# Tokenizer.errors is list[tuple[int, str]] and the int has one job: point at
# the character that caused the error. _next() has already moved self.pos past
# the character it returned, so every non-EOF call site has to pass an explicit
# offset; before this was pinned the recorded positions were between +1 and +4
# past the offence, varying by call site. These cases span five different
# states so a regression in any one of them is visible.


@pytest.mark.parametrize(
    "src,expected",
    [
        # tag open state: the '@' is the offending character, not the '<'.
        ("ab<@", [(3, "invalid first character of tag name")]),
        # self-closing start tag state: the offender is the '/', which is two
        # back from self.pos because 'x' was consumed to get here.
        ("<p/x>", [(2, "unexpected solidus in tag")]),
        # attribute name state: point at the start of the duplicate attribute,
        # not at the '>' that happened to finish it.
        ("<p a=1 a=2>", [(7, "duplicate attribute 'a'")]),
        # before attribute value state.
        ("<p a=>", [(5, "missing attribute value")]),
        # before attribute name state.
        ("<p =x>", [(3, "unexpected = before attribute name")]),
        # end tag open state.
        ("</>", [(2, "missing end tag name")]),
        # doctype state: the '>' is where the absent name should have been.
        ("<!DOCTYPE>", [(9, "missing doctype name")]),
    ],
)
def test_parse_error_offsets_point_at_the_offending_character(src, expected):
    tk = Tokenizer(src)
    list(tk.tokenize())
    assert tk.errors == expected


@pytest.mark.parametrize("src", ["<div", "<div ", "<div a", '<div a="b'])
def test_eof_errors_are_recorded_at_end_of_input(src):
    """There is no offending character at EOF, so the offset is len(source) --
    one past the last character, i.e. where input stopped."""
    tk = Tokenizer(src)
    list(tk.tokenize())
    assert tk.errors == [(len(src), "eof in tag")]


@pytest.mark.parametrize(
    "src,expected",
    [
        # Absence of digits: the offender is the non-digit after '#'. Note the
        # decoder consumes nothing on this path, so an offset derived from the
        # post-decode position would point at the '#' instead.
        ("&#qX", [(2, "absence of digits in numeric character reference")]),
        ("&#xZ", [(3, "absence of digits in numeric character reference")]),
        # No character is at fault for the two value errors -- the offence is
        # the code point the whole reference denotes -- so both are recorded at
        # the opening '&'. See Tokenizer._error's convention note.
        ("&#0;A", [(0, "invalid numeric character reference")]),
        ("&#153;Z", [(0, "control character reference")]),
        # ...and the '&', not a hard-coded 0: the offset is the reference's own.
        ("x&#0;", [(1, "invalid numeric character reference")]),
        # Absent character: the offset is where the ';' should have been.
        ("&#65A", [(4, "missing semicolon after character reference")]),
    ],
)
def test_character_reference_error_offsets(src, expected):
    """The character-reference family follows the same convention as every
    other _error call site; decode_reference reports its own offset rather than
    letting the tokenizer derive one from the post-decode position."""
    tk = Tokenizer(src)
    list(tk.tokenize())
    assert tk.errors == expected
