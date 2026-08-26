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
