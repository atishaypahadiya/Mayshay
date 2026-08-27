"""Tests for the hand-rolled CSS tokenizer (css-syntax-3 section 4).

The first thirteen tests are the acceptance set from the task brief; the rest
cover the token types the brief names in the interface but does not exercise
(at-keywords, the four bracket pairs, colon/semicolon/comma, EOF), plus the
error-recovery paths the spec requires -- bad-string, bad-url, unterminated
url -- and the metrics contract.
"""

import pytest

from mayshay.cssparse.tokenizer import (
    CssTokenizer, Delim, Dimension, Function, Hash, Ident, Number,
    Percentage, String, Url, Whitespace,
)


def toks(src):
    return [t for t in CssTokenizer(src).tokenize() if not isinstance(t, Whitespace)]


# --------------------------------------------------------------------------
# The brief's acceptance set
# --------------------------------------------------------------------------

def test_simple_declaration():
    got = toks("color: red;")
    assert isinstance(got[0], Ident) and got[0].value == "color"
    assert isinstance(got[2], Ident) and got[2].value == "red"


def test_dimensions_and_percentages():
    got = toks("10px 50% 1.5em -3px")
    assert (got[0].value, got[0].unit) == (10, "px")
    assert isinstance(got[1], Percentage) and got[1].value == 50
    assert (got[2].value, got[2].unit) == (1.5, "em")
    assert got[3].value == -3


def test_numbers_with_exponents():
    assert toks("1e3")[0].value == 1000
    assert toks("1.5E-2")[0].value == pytest.approx(0.015)


def test_hash_and_id_selector():
    got = toks("#main")
    assert isinstance(got[0], Hash) and got[0].value == "main"


def test_strings_both_quote_styles():
    assert toks('"a b"')[0].value == "a b"
    assert toks("'a b'")[0].value == "a b"


def test_escape_sequences():
    assert toks(r"\26")[0].value == "&"
    # The brief expected "&" here. That is wrong, and wrong in a way that
    # would have driven a wrong implementation: the single space after six hex
    # digits terminates the *escape*, not the *ident sequence*, so the "x" is
    # still an ident code point and joins the same token. Cross-checked: this
    # is one token, IdentToken("&x"). To see "&" alone you need a second space
    # -- test_escape_consumes_exactly_one_trailing_whitespace below.
    assert toks(r"\000026 x")[0].value == "&x"
    assert toks(r"a\-b")[0].value == "a-b"


def test_url_unquoted_is_its_own_token():
    got = toks("url(a/b.png)")
    assert isinstance(got[0], Url) and got[0].value == "a/b.png"


def test_url_quoted_is_a_function_plus_string():
    got = toks('url("a.png")')
    assert isinstance(got[0], Function) and got[0].value == "url"
    assert isinstance(got[1], String)


def test_function_token():
    got = toks("rgb(1,2,3)")
    assert isinstance(got[0], Function) and got[0].value == "rgb"


def test_comments_are_skipped():
    assert [t.value for t in toks("a /* c */ b") if isinstance(t, Ident)] == ["a", "b"]


def test_unterminated_comment_is_an_error_not_a_crash():
    tk = CssTokenizer("a /* unterminated")
    list(tk.tokenize())
    assert tk.errors


def test_delim_for_combinators():
    assert [type(t).__name__ for t in toks("a > b")][1] == "Delim"


def test_style_element_body_round_trips():
    """A realistic <style> body tokenizes without loss.

    The brief wrote the first assertion as
    `assert not CssTokenizer(src).errors or True`, which is a tautology twice
    over -- `or True` can never fail, and `errors` is empty before `tokenize()`
    has run because the tokenizer is lazy. Replaced with the check it was
    plainly reaching for: a well-formed stylesheet produces no parse errors.
    """
    src = "p.lead, #main > a:hover { color: #f0f; margin: 0 auto }"
    tk = CssTokenizer(src)
    list(tk.tokenize())
    assert tk.errors == []
    assert len(toks(src)) > 15


# --------------------------------------------------------------------------
# Interface coverage the brief names but does not exercise
# --------------------------------------------------------------------------

def test_at_keyword_and_block_punctuation():
    from mayshay.cssparse.tokenizer import (
        AtKeyword, Colon, Comma, EOFToken, LBrace, LBracket, LParen, RBrace,
        RBracket, RParen, Semicolon,
    )

    got = toks("@media (x) { a[b]: c, d; }")
    kinds = [type(t) for t in got]
    assert isinstance(got[0], AtKeyword) and got[0].value == "media"
    for cls in (LParen, RParen, LBrace, LBracket, RBracket, Colon, Comma,
                Semicolon, RBrace):
        assert cls in kinds, cls.__name__
    assert isinstance(got[-1], EOFToken)


def test_whitespace_runs_coalesce_into_one_token():
    got = list(CssTokenizer("a \n\t b").tokenize())
    assert [type(t).__name__ for t in got] == [
        "Ident", "Whitespace", "Ident", "EOFToken"
    ]
    assert got[1].value == " \n\t "


def test_ident_starting_with_two_dashes_is_a_custom_property():
    got = toks("--main-color")
    assert isinstance(got[0], Ident) and got[0].value == "--main-color"


def test_hash_id_flag_distinguishes_selectors_from_colours():
    got = toks("#main #0f0")
    assert got[0].is_id is True
    assert got[1].value == "0f0" and got[1].is_id is False


def test_number_type_flag_tracks_integer_vs_number():
    assert toks("3")[0].is_integer is True
    assert toks("3.0")[0].is_integer is False
    # 1e3 has an integral *value* but the spec's type flag is "number".
    assert toks("1e3")[0].is_integer is False


def test_an_exponent_needs_a_digit_or_it_is_a_unit():
    """`1em` / `1e` / `1e+` must not be read as scientific notation."""
    assert (toks("1em")[0].value, toks("1em")[0].unit) == (1, "em")
    assert (toks("1e")[0].value, toks("1e")[0].unit) == (1, "e")
    got = toks("1e+")
    assert isinstance(got[0], Dimension) and (got[0].value, got[0].unit) == (1, "e")
    assert isinstance(got[1], Delim) and got[1].value == "+"


def test_plus_and_dot_start_numbers_but_are_delims_alone():
    assert isinstance(toks("+1")[0], Number) and toks("+1")[0].value == 1
    assert isinstance(toks(".5")[0], Number) and toks(".5")[0].value == 0.5
    assert isinstance(toks("+ a")[0], Delim)
    assert isinstance(toks(". a")[0], Delim)


def test_cdo_and_cdc_are_their_own_tokens():
    got = toks("<!-- a -->")
    assert [type(t).__name__ for t in got[:1]] == ["CDO"]
    assert type(got[-2]).__name__ == "CDC"


def test_positions_point_at_the_first_character_of_the_token():
    got = toks("  color:red")
    assert got[0].pos == 2          # 'c'
    assert got[1].pos == 7          # ':'
    assert got[2].pos == 8          # 'r'


# --------------------------------------------------------------------------
# Escapes -- the analogue of HTML entity decoding
# --------------------------------------------------------------------------

def test_escape_consumes_exactly_one_trailing_whitespace():
    # The space after \000026 terminates the hex digits and is consumed; the
    # second space is a real whitespace token, so 'x' survives as an ident.
    got = toks("\\000026  x")
    assert got[0].value == "&"
    assert isinstance(got[1], Ident) and got[1].value == "x"


def test_escape_stops_at_six_hex_digits():
    # \0000263 is U+000026 followed by a literal '3', not U+263.
    assert toks(r"\0000263")[0].value == "&3"


def test_out_of_range_and_surrogate_escapes_become_replacement_char():
    assert toks(r"\110000 ")[0].value == "�"
    assert toks(r"\D800 ")[0].value == "�"
    assert toks(r"\0 ")[0].value == "�"


def test_backslash_before_newline_is_not_a_valid_escape_outside_strings():
    got = toks("a\\\nb")
    assert isinstance(got[0], Ident) and got[0].value == "a"
    assert isinstance(got[1], Delim) and got[1].value == "\\"


def test_backslash_newline_inside_a_string_is_a_line_continuation():
    assert toks('"a\\\nb"')[0].value == "ab"


def test_escaped_quote_inside_a_string():
    assert toks(r'"a\"b"')[0].value == 'a"b'


# --------------------------------------------------------------------------
# url() -- the genuine special case
# --------------------------------------------------------------------------

def test_url_with_whitespace_around_unquoted_body():
    got = toks("url(  a/b.png  )")
    assert isinstance(got[0], Url) and got[0].value == "a/b.png"


def test_url_with_internal_space_is_a_bad_url():
    from mayshay.cssparse.tokenizer import BadUrl

    tk = CssTokenizer("url(a b) x")
    got = [t for t in tk.tokenize() if not isinstance(t, Whitespace)]
    assert isinstance(got[0], BadUrl)
    assert tk.errors
    # Recovery: the bad-url remnants stop at the ')', so 'x' still tokenizes.
    assert isinstance(got[1], Ident) and got[1].value == "x"


def test_unquoted_url_may_contain_characters_no_other_token_permits():
    got = toks("url(http://a.example/b?c=d&e=1)")
    assert isinstance(got[0], Url)
    assert got[0].value == "http://a.example/b?c=d&e=1"


def test_url_prefix_matching_is_ascii_case_insensitive():
    assert isinstance(toks("URL(a.png)")[0], Url)
    assert isinstance(toks('URL("a.png")')[0], Function)


def test_one_space_before_a_quote_still_takes_the_quoted_path():
    """`url( "a.png")` -- the off-by-one the whole url branch turns on.

    The spec consumes whitespace only *while the next two are whitespace*,
    leaving at most one in place, which is exactly what lets the quote test
    see past it. One space too many consumed and this is an unquoted url whose
    body starts with a double quote; one too few and `url(  "a.png")` is.
    """
    for src in ('url( "a.png")', 'url(  "a.png")', 'url("a.png" )'):
        got = toks(src)
        assert isinstance(got[0], Function) and got[0].value == "url", src
        assert isinstance(got[1], String) and got[1].value == "a.png", src


def test_url_like_function_name_is_not_a_url():
    got = toks("url-prefix(a.png)")
    assert isinstance(got[0], Function) and got[0].value == "url-prefix"


def test_escapes_work_inside_an_unquoted_url():
    assert toks(r"url(a\29 b)")[0].value == "a)b"


def test_unterminated_url_is_an_error_not_a_crash():
    tk = CssTokenizer("url(a/b.png")
    got = [t for t in tk.tokenize() if not isinstance(t, Whitespace)]
    assert isinstance(got[0], Url) and got[0].value == "a/b.png"
    assert tk.errors


# --------------------------------------------------------------------------
# Error recovery -- the spec never fails to tokenize
# --------------------------------------------------------------------------

def test_unterminated_string_is_an_error_not_a_crash():
    tk = CssTokenizer('"abc')
    got = [t for t in tk.tokenize() if not isinstance(t, Whitespace)]
    assert isinstance(got[0], String) and got[0].value == "abc"
    assert tk.errors


def test_newline_in_string_yields_bad_string_and_recovers():
    from mayshay.cssparse.tokenizer import BadString

    tk = CssTokenizer('"a\nb" c')
    got = [t for t in tk.tokenize() if not isinstance(t, Whitespace)]
    assert isinstance(got[0], BadString)
    assert tk.errors
    # The newline is reconsumed, so what follows keeps tokenizing.
    assert any(isinstance(t, Ident) and t.value == "b" for t in got)


def test_errors_record_an_offset_and_a_message():
    tk = CssTokenizer("a /* unterminated")
    list(tk.tokenize())
    pos, message = tk.errors[0]
    assert isinstance(pos, int) and 0 <= pos <= len("a /* unterminated")
    assert isinstance(message, str) and message


# --------------------------------------------------------------------------
# Metrics
# --------------------------------------------------------------------------

def test_metrics_are_populated():
    tk = CssTokenizer("a { color: red }")
    tokens = list(tk.tokenize())
    assert tk.metrics["css_tokens"] == len(tokens) - 1   # EOF excluded
    assert tk.metrics["tokenize_time_ms"] > 0.0
    assert tk.metrics["css_parse_errors"] == 0


def test_parse_error_metric_counts_errors():
    tk = CssTokenizer("a /* unterminated")
    list(tk.tokenize())
    assert tk.metrics["css_parse_errors"] == len(tk.errors) > 0


# --------------------------------------------------------------------------
# Real corpus input
# --------------------------------------------------------------------------

def test_real_style_bodies_from_the_corpus_tokenize_without_error():
    """Every <style> body in data/corpus/ must tokenize cleanly.

    Not a smoke test: a real stylesheet is the only input that exercises the
    tokenizer at the density it will actually see -- comments, url()s, hex
    colours, at-rules and vendor idents interleaved.
    """
    from pathlib import Path

    from mayshay.htmlparse import parse

    corpus = Path(__file__).resolve().parents[2] / "data" / "corpus"
    bodies = []
    for path in sorted(corpus.glob("*.html")):
        document = parse(path.read_text(encoding="utf-8", errors="replace"))
        stack = [document]
        while stack:
            node = stack.pop()
            children = getattr(node, "children", [])
            stack.extend(children)
            if getattr(node, "tag_name", None) == "style":
                text = "".join(
                    getattr(c, "data", "") for c in children
                )
                if text.strip():
                    bodies.append((path.name, text))

    if not bodies:
        pytest.skip("no <style> bodies in data/corpus/")

    for name, css in bodies:
        tk = CssTokenizer(css)
        tokens = list(tk.tokenize())
        assert tokens, name
        assert tk.errors == [], f"{name}: {tk.errors[:3]}"
