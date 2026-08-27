import pytest

from mayshay.cssparse.values import (
    AUTO,
    DROP_INVALID,
    DROP_REASONS,
    DROP_UNSUPPORTED_PROPERTY,
    DROP_UNSUPPORTED_VALUE,
    DROP_VAR_UNRESOLVED,
    LONGHANDS_OF,
    SUPPORTED_PROPERTIES,
    Color,
    Keyword,
    Length,
    Percent,
    classify_drop,
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


# --------------------------------------------------------------------------
# The module's stated boundaries, pinned so they cannot drift silently.
# --------------------------------------------------------------------------


def test_longhands_of_the_supported_shorthands_are_not_supported():
    """Deviation 13. The nine properties include `margin`, `padding` and
    `border` but none of their longhands, so the *only* way to set
    `ComputedStyle.margin_top` is to write the shorthand.

    This is a consequence of the dispatch chain rather than a decision, and
    it was undocumented and untested until the deviation was written. It is
    the largest slice of the corpus's dropped declarations that no other
    deviation covers: executed over `data/corpus/wikipedia.html`, 85 of the
    313 dropped declarations are in this family. Widening the set is a
    deliberate act; this test is what makes it one.
    """
    for name, src in [
        ("margin-top", "5px"),
        ("margin-right", "5px"),
        ("margin-bottom", "5px"),
        ("margin-left", "5px"),
        ("padding-top", "5px"),
        ("padding-right", "5px"),
        ("border-top", "1px solid red"),
        ("border-top-width", "5px"),
        ("border-top-style", "solid"),
        ("border-top-color", "red"),
        ("border-width", "5px"),
        ("border-style", "solid"),
        ("border-color", "red"),
        ("background", "red"),
    ]:
        assert val(name, src) is None, f"{name} is now supported -- update deviation 13"

    # ...while the shorthands themselves still work, so this test fails for
    # the right reason if the dispatch table is broken outright.
    assert val("margin", "5px")["margin-top"] == Length(5, "px")
    assert val("border", "1px solid red")["border-top-width"] == Length(1, "px")


def test_display_is_a_closed_keyword_allow_list():
    """Deviation 14. A `display` value the module does not know is invalid
    rather than passed through as a string the cascade would have to guess
    at. `flow-root` is the one such keyword in the corpus (1 drop on
    wikipedia, executed).
    """
    from mayshay.cssparse.values import _DISPLAY_KEYWORDS

    assert len(_DISPLAY_KEYWORDS) == 20
    assert val("display", "flow-root") is None
    assert val("display", "ruby-text") is None
    assert val("display", "block")["display"] == Keyword("block")
    assert val("width", "5Q")["width"] == Length(5, "q")  # deviation 1's Q/q


def test_identifier_matching_is_ascii_case_insensitive_not_unicode():
    """Deviation 12. CSS case-insensitivity is ASCII-only. Python's
    `str.lower()` folds the whole Unicode table -- U+212A KELVIN SIGN goes
    to `k` -- and this module used `str.lower()` at ten sites, so
    `display: bloc\\u212a` parsed as `Keyword("block")` and
    `color: pin\\u212a` as pink. A browser rejects both. Executed before the
    fix: both were accepted; after: both are None.
    """
    kelvin = "\u212a"  # KELVIN SIGN, not ASCII K
    assert kelvin.lower() == "k"          # the trap, stated outright
    assert val("display", "bloc" + kelvin) is None
    assert val("color", "pin" + kelvin) is None
    assert val("border", "1px solid pin" + kelvin) is None

    # ASCII case-insensitivity itself is untouched.
    assert val("display", "BLOCK")["display"] == Keyword("block")
    assert val("color", "PINK") == val("color", "pink")
    assert val("width", "5PX")["width"] == Length(5, "px")
    assert val("color", "RGB(1, 2, 3)")["color"] == Color(1, 2, 3, 1.0)


def test_property_names_are_normalised_and_the_rule_is_exported():
    """The normalisation `parse_declaration_value` applies to its `name`
    argument is part of the interface, not an implementation detail: Task
    J's cascade keys its shorthand-reset table on a property name and has
    to fold it the same way. `normalize_property_name` exists so it can do
    that from this module's rule rather than from a guess.
    """
    from mayshay.cssparse.values import normalize_property_name

    assert normalize_property_name("BORDER") == "border"
    assert normalize_property_name("Margin-Top") == "margin-top"
    # ASCII only, here too.
    assert normalize_property_name("BORDER\u212a") == "border\u212a"

    assert val("BORDER", "1px solid red") == val("border", "1px solid red")
    assert val("Display", "block") == val("display", "block")


# --------------------------------------------------------------------------
# Drop reasons (Phase 3 Task A2, deliverable 1)
# --------------------------------------------------------------------------


def why(name, src):
    return classify_drop(name, list(CssTokenizer(src).tokenize()))


def test_the_property_table_and_its_derived_sets_agree():
    """`SUPPORTED_PROPERTIES` and `LONGHANDS_OF` are derived from the parser
    table, so a property in one is in all three. Injection: adding a name to
    `LONGHANDS_OF` alone trips the module-level assert; adding a parser
    without a `LONGHANDS_OF` entry trips it the other way.

    The second half is the one that discriminates: `LONGHANDS_OF[name]` must
    be exactly the keys `parse_declaration_value` produces, not a superset
    someone wrote out by hand.
    """
    assert SUPPORTED_PROPERTIES == set(LONGHANDS_OF)
    samples = {
        "display": "block", "width": "10px", "height": "10px",
        "font-size": "12px", "color": "red", "background-color": "red",
        "margin": "1px", "padding": "1px", "border": "1px solid red",
    }
    assert set(samples) == SUPPORTED_PROPERTIES, (
        "a property was added to the table without a sample here"
    )
    for name, src in samples.items():
        parsed = val(name, src)
        assert parsed is not None, name
        assert set(parsed) == set(LONGHANDS_OF[name]), name


def test_an_unknown_property_name_is_unsupported_property_not_invalid():
    """The value is impeccable CSS; only the name is outside the table.
    Both sides asserted: the same value under a known name parses."""
    assert why("mask-image", "none") == DROP_UNSUPPORTED_PROPERTY
    assert why("padding-right", "4px") == DROP_UNSUPPORTED_PROPERTY
    assert val("width", "4px") is not None


def test_valid_css_this_module_does_not_implement_is_unsupported_value():
    """`flow-root` and `max-content` are real CSS; `calc()` and `hsl()` are
    real functions; `thin` is a real border width. None of them is malformed,
    so none may land in `invalid`."""
    assert why("display", "flow-root") == DROP_UNSUPPORTED_VALUE
    assert why("width", "max-content") == DROP_UNSUPPORTED_VALUE
    assert why("width", "calc(100% - 4px)") == DROP_UNSUPPORTED_VALUE
    assert why("color", "hsl(0, 0%, 0%)") == DROP_UNSUPPORTED_VALUE
    assert why("border", "thin solid red") == DROP_UNSUPPORTED_VALUE
    # ...and the supported spellings of the same properties still parse, so
    # this is not a test of "everything is unsupported-value".
    assert val("display", "block") is not None
    assert val("width", "4px") is not None
    assert val("color", "rgb(0, 0, 0)") is not None
    assert val("border", "1px solid red") is not None


def test_a_wide_keyword_is_unsupported_value_on_every_property():
    for keyword in ("inherit", "initial", "unset", "revert"):
        for prop in ("color", "width", "display", "margin"):
            assert why(prop, keyword) == DROP_UNSUPPORTED_VALUE, (prop, keyword)


def test_a_var_reference_is_var_unresolved():
    assert why("color", "var(--accent)") == DROP_VAR_UNRESOLVED
    assert why("color", "var(--accent, #fff)") == DROP_VAR_UNRESOLVED
    assert why("width", "calc(var(--x) + 4px)") == DROP_VAR_UNRESOLVED
    # A `var()` on a property outside the table is still the property's
    # fault: it would be dropped even with substitution working, so calling
    # it `var-unresolved` would make the var() counter move for a reason
    # var() cannot fix.
    assert why("background", "var(--accent)") == DROP_UNSUPPORTED_PROPERTY


def test_a_malformed_var_is_invalid_not_var_unresolved():
    """`var(` must be followed by a `--` identifier. Anything else is a
    syntax error a browser drops too, and putting it in `var-unresolved`
    would credit the var() work with a case var() can never recover."""
    assert why("color", "var(5px)") == DROP_INVALID
    assert why("color", "var(accent)") == DROP_INVALID
    assert why("color", "var()") == DROP_INVALID


def test_genuinely_malformed_values_are_invalid():
    """The bucket that must never shrink. Each of these is something a
    browser drops too."""
    assert why("width", "banana") == DROP_INVALID
    assert why("color", "#gg0000") == DROP_INVALID
    assert why("font-size", "10foo") == DROP_INVALID
    assert why("margin", "1px 2px 3px 4px 5px") == DROP_INVALID
    assert why("width", "") == DROP_INVALID
    assert why("border", "1px 2px solid") == DROP_INVALID


def test_a_kelvin_sign_keyword_is_invalid_not_unsupported_value():
    """Deviation 12's pair, classified. `bloc<U+212A>` and `pin<U+212A>` are
    not CSS at all -- `str.lower()` would fold U+212A KELVIN SIGN to `k` and
    accept both -- so they are dropped, and the drop belongs in `invalid`
    rather than in a bucket that says "valid CSS we chose not to do".

    The sign is built from an escape, never written as a literal: U+212A and
    ASCII K are indistinguishable in a terminal, and a literal here would
    silently become the ASCII spelling on any copy-paste -- at which point
    `val(...)` would return a parsed value, `classify_drop` would be being
    called outside its contract, and both halves would still pass.
    """
    kelvin = "\u212a"
    assert kelvin != "K" and kelvin.lower() == "k"
    assert val("display", "bloc" + kelvin) is None
    assert val("color", "pin" + kelvin) is None
    assert why("display", "bloc" + kelvin) == DROP_INVALID
    assert why("color", "pin" + kelvin) == DROP_INVALID
    # The ASCII spellings parse, so this is a test of the fold and not of
    # `classify_drop` returning a constant.
    assert val("display", "block") is not None
    assert val("color", "pink") is not None


def test_every_reason_is_one_of_the_four_and_they_are_distinct():
    """A partition, not a label: `classify_drop` must return a member of
    `DROP_REASONS`, and the four must be distinguishable from one another on
    real inputs -- a classifier that returned the same constant for
    everything would pass a one-input test."""
    seen = {
        why(name, src)
        for name, src in [
            ("mask-image", "none"),
            ("display", "flow-root"),
            ("color", "var(--x)"),
            ("width", "banana"),
        ]
    }
    assert seen == set(DROP_REASONS)
    assert len(DROP_REASONS) == 4
