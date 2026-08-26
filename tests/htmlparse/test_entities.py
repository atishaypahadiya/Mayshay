import pytest

from mayshay.htmlparse.tokenizer import CharacterToken, Tokenizer


def text_of(src):
    return "".join(
        t.data for t in Tokenizer(src).tokenize() if isinstance(t, CharacterToken)
    )


def attr_of(src, name="href"):
    from mayshay.htmlparse.tokenizer import StartTagToken

    tag = next(t for t in Tokenizer(src).tokenize() if isinstance(t, StartTagToken))
    return tag.attrs[name]


@pytest.mark.parametrize(
    "src,expected",
    [
        ("&amp;", "&"),
        ("&AMP;", "&"),
        ("&nbsp;", "\xa0"),  # U+00A0 NO-BREAK SPACE
        ("&notin;", "∉"),
        ("&notit;", "¬it;"),   # longest match: 'not' wins, 'in' does not
        ("&acE;", "∾\u0333"),  # multi-codepoint: trailing combining mark
        ("&#65;", "A"),
        ("&#x41;", "A"),
        ("&#X41;", "A"),
        ("&#x80;", "\u20ac"),  # windows-1252 remap: U+20AC EURO SIGN
        ("&#0;", "\ufffd"),  # U+FFFD REPLACEMENT CHARACTER
        ("&#xD800;", "\ufffd"),
        ("&#x110000;", "\ufffd"),
        ("&#38;#38;", "&#38;"),     # decode once, not twice
        ("&", "&"),
        ("& ", "& "),
        ("&amp", "&"),              # missing semicolon, still decodes in text
    ],
)
def test_decoding(src, expected):
    assert text_of(src) == expected


def test_missing_semicolon_is_a_parse_error():
    tk = Tokenizer("&amp")
    list(tk.tokenize())
    assert tk.errors


def test_legacy_attribute_rule_blocks_decoding():
    assert attr_of('<a href="?a&copy=1">') == "?a&copy=1"


def test_semicolon_in_attribute_still_decodes():
    assert attr_of('<a href="?a&copy;=1">') == "?a©=1"


def test_attribute_followed_by_space_decodes():
    assert attr_of('<a href="?a&copy x">') == "?a© x"


def test_not_decoded_in_rawtext():
    assert text_of("<script>&amp;</script>") == "&amp;"


def test_decoded_in_rcdata():
    assert text_of("<title>a &amp; b</title>") == "a & b"


def test_not_decoded_in_comment():
    from mayshay.htmlparse.tokenizer import CommentToken

    c = next(
        t for t in Tokenizer("<!-- &amp; -->").tokenize()
        if isinstance(t, CommentToken)
    )
    assert c.data == " &amp; "


@pytest.mark.parametrize(
    "src,expected_count",
    [
        ("&amp;", 1),      # successful decode to "&" -- must still count
        ("&nbsp;", 1),     # successful decode to a non-"&" replacement
        ("&", 0),          # no match at all: literal "&", position unmoved
        ("&notit;", 1),    # partial match: decodes "&not", "it;" left as text
        ("&#38;", 1),      # numeric decode to "&" -- the numeric-path version
                           # of the same trap as the "&amp;" case above
    ],
)
def test_character_reference_metric_counts_successful_decodes(src, expected_count):
    tk = Tokenizer(src)
    list(tk.tokenize())
    assert tk.metrics["character_references"] == expected_count
