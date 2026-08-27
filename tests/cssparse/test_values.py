import pytest

from mayshay.cssparse.values import (
    AUTO,
    Color,
    Keyword,
    Length,
    Percent,
    expand_shorthand,
    parse_declaration_value as pv,
)
from mayshay.cssparse.tokenizer import CssTokenizer


def val(name, src):
    return pv(name, [t for t in CssTokenizer(src).tokenize()])


# --------------------------------------------------------------------------
# Brief's verbatim tests (task-I-brief.md, Step 1)
# --------------------------------------------------------------------------


def test_length_units():
    assert val("width", "10px")["width"] == Length(10, "px")
    assert val("font-size", "1.5em")["font-size"] == Length(1.5, "em")


def test_percentage_stays_symbolic():
    """Cannot be resolved without a containing block. Phase 3's problem."""
    assert val("width", "50%")["width"] == Percent(50)


def test_auto_stays_symbolic():
    assert val("width", "auto")["width"] is AUTO


def test_color_keyword_hash_and_function():
    assert val("color", "red")["color"] == Color(255, 0, 0, 1.0)
    assert val("color", "#f00")["color"] == Color(255, 0, 0, 1.0)
    assert val("color", "#ff0000")["color"] == Color(255, 0, 0, 1.0)
    assert val("color", "rgb(255,0,0)")["color"] == Color(255, 0, 0, 1.0)


def test_display_keywords():
    """Strengthened in fix round 1: the brief's original body only ever
    checked 'block', which a hardcoded `return Keyword("block")`
    implementation would also pass. Checking a second, different keyword
    (and that it differs from the first) is what actually exercises
    keyword *recognition* rather than a single lucky constant.
    """
    assert val("display", "block")["display"] == Keyword("block")
    assert val("display", "inline")["display"] == Keyword("inline")
    assert val("display", "block")["display"] != val("display", "inline")["display"]


@pytest.mark.parametrize("src,expected", [
    ("1px", (1, 1, 1, 1)),
    ("1px 2px", (1, 2, 1, 2)),
    ("1px 2px 3px", (1, 2, 3, 2)),
    ("1px 2px 3px 4px", (1, 2, 3, 4)),
])
def test_margin_shorthand_expansion(src, expected):
    got = val("margin", src)
    sides = ("margin-top", "margin-right", "margin-bottom", "margin-left")
    assert tuple(got[s].value for s in sides) == expected


def test_border_shorthand_expands_to_width_style_color():
    got = val("border", "1px solid red")
    assert got["border-top-width"] == Length(1, "px")
    assert got["border-top-style"].name == "solid"
    assert got["border-top-color"] == Color(255, 0, 0, 1.0)


def test_invalid_value_drops_the_declaration():
    assert val("width", "banana") is None
    assert val("color", "#gg0000") is None


def test_unitless_nonzero_length_is_invalid():
    """Named without a mode: `parse_declaration_value` takes no mode parameter,
    and adding an unused one to justify a test name would be worse than the
    name. Quirks-mode unitless lengths are a Phase 3 layout concern.
    """
    assert val("width", "10") is None
    assert val("margin", "0")["margin-top"] == Length(0, "px")


# --------------------------------------------------------------------------
# Supplementary tests
# --------------------------------------------------------------------------


def test_green_is_not_lime():
    """The trap the brief calls out by name: CSS 'green' is #008000, not the
    bright green (#00ff00) most people picture -- that one is 'lime'.
    """
    assert val("color", "green")["color"] == Color(0, 128, 0, 1.0)
    assert val("color", "lime")["color"] == Color(0, 255, 0, 1.0)
    assert val("color", "green")["color"] != val("color", "lime")["color"]


def test_padding_does_not_accept_auto():
    """auto is margin-only; padding has no <length> | <percentage> | auto
    grammar in the real spec, and accepting it here would let a layout bug
    (auto padding) sail through undetected."""
    assert val("padding", "auto") is None
    assert val("padding", "1px auto") is None


def test_border_components_may_appear_in_any_order():
    forward = val("border", "1px solid red")
    backward = val("border", "red solid 1px")
    middle = val("border", "solid red 1px")
    assert forward == backward == middle


def test_border_rejects_duplicate_component_kind():
    """Two lengths (or two styles, or two colors) is not 'last one wins' --
    it is an invalid shorthand, and the whole declaration is dropped."""
    assert val("border", "1px 2px solid red") is None
    assert val("border", "solid dashed 1px red") is None


def test_border_partial_component_only_sets_that_kind():
    """`border: solid` alone sets only *-style; it does NOT synthesize the
    spec's initial width (medium) or color (currentcolor) -- see deviation 7.
    """
    got = val("border", "solid")
    assert got == {
        "border-top-style": Keyword("solid"),
        "border-right-style": Keyword("solid"),
        "border-bottom-style": Keyword("solid"),
        "border-left-style": Keyword("solid"),
    }


def test_hex_color_short_and_long_with_alpha():
    assert val("color", "#f00f")["color"] == Color(255, 0, 0, 1.0)
    got = val("color", "#ff000080")["color"]
    assert (got.r, got.g, got.b) == (255, 0, 0)
    assert abs(got.a - 128 / 255) < 1e-9


def test_rgb_function_with_percentage_channels_and_alpha():
    got = val("color", "rgba(100%, 0%, 0%, 0.5)")["color"]
    assert (got.r, got.g, got.b) == (255, 0, 0)
    assert got.a == 0.5


def test_transparent_and_currentcolor():
    assert val("background-color", "transparent")["background-color"] == Color(0, 0, 0, 0.0)
    assert val("color", "currentcolor")["color"] == Keyword("currentcolor")


def test_unknown_color_keyword_is_invalid():
    assert val("color", "bloodorange") is None


def test_unknown_display_keyword_is_invalid():
    assert val("display", "flexbox") is None


def test_width_rejects_multiple_tokens():
    """`width: 10px 20px` is not a valid <length> -- there is exactly one
    component in width's grammar, unlike margin's 1-4 value list."""
    assert val("width", "10px 20px") is None


def test_expand_shorthand_is_dict_in_dict_out_for_every_shorthand():
    """Exercise expand_shorthand itself, not only through parse_declaration_value,
    since it is documented as a public entry point in its own right.

    Fix round 1: `parsed` used to be a `list` for margin/padding and a
    `dict` for border. Both are `dict[str, object]` now -- margin/padding
    keyed by side, border by component kind -- so this pins the unified
    input shape, not just the output.
    """
    one = expand_shorthand("margin", {
        "top": Length(1, "px"), "right": Length(1, "px"),
        "bottom": Length(1, "px"), "left": Length(1, "px"),
    })
    assert one == {
        "margin-top": Length(1, "px"),
        "margin-right": Length(1, "px"),
        "margin-bottom": Length(1, "px"),
        "margin-left": Length(1, "px"),
    }
    three = expand_shorthand("padding", {
        "top": Length(1, "px"), "right": Length(2, "px"),
        "bottom": Length(3, "px"), "left": Length(2, "px"),
    })
    assert three == {
        "padding-top": Length(1, "px"),
        "padding-right": Length(2, "px"),
        "padding-bottom": Length(3, "px"),
        "padding-left": Length(2, "px"),
    }
    border = expand_shorthand("border", {"style": Keyword("solid")})
    assert border == {
        "border-top-style": Keyword("solid"),
        "border-right-style": Keyword("solid"),
        "border-bottom-style": Keyword("solid"),
        "border-left-style": Keyword("solid"),
    }


def test_margin_percent_and_auto_mixed():
    got = val("margin", "10% auto")
    assert got["margin-top"] == Percent(10)
    assert got["margin-bottom"] == Percent(10)
    assert got["margin-right"] is AUTO
    assert got["margin-left"] is AUTO


# --------------------------------------------------------------------------
# Fix round 1: minor coverage gaps the review flagged as "correct by
# inspection" rather than tested -- exactly the shape of the four vacuous
# tests this file already had before that round.
# --------------------------------------------------------------------------


def test_padding_percent():
    got = val("padding", "10%")
    assert got["padding-top"] == Percent(10)
    assert got["padding-left"] == Percent(10)


def test_font_size_percent():
    assert val("font-size", "150%")["font-size"] == Percent(150)


def test_border_color_currentcolor():
    got = val("border", "1px solid currentcolor")
    assert got["border-top-color"] == Keyword("currentcolor")


def test_color_keyword_table_is_complete():
    """Fix round 1: the table shipped with 22 entries against the spec's
    148 (16 CSS1 keywords + a handful of common extras), which silently
    drops a declaration for any of the ~126 missing names on a real page --
    the exact failure mode the symbolic-value discipline elsewhere in this
    module exists to prevent. Pins the count and spot-checks several
    non-famous entries by full round trip through the public API, not just
    the private table, so a typo in the *lookup path* (not just the data)
    would also be caught.
    """
    from mayshay.cssparse.values import _COLOR_KEYWORDS

    assert len(_COLOR_KEYWORDS) == 148

    checks = {
        "rebeccapurple": Color(102, 51, 153, 1.0),
        "papayawhip": Color(255, 239, 213, 1.0),
        "mediumspringgreen": Color(0, 250, 154, 1.0),
        "darkslategrey": Color(47, 79, 79, 1.0),
        "cadetblue": Color(95, 158, 160, 1.0),
        "lightgoldenrodyellow": Color(250, 250, 210, 1.0),
    }
    for name, expected in checks.items():
        assert val("color", name)["color"] == expected
