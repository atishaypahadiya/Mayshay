"""Text measurement and white-space collapsing -- Phase 3 Task D1.

Two independent sources are pinned here and they are not the same kind of
thing, which is the point.

**The font numbers come from `docs/fonts.md`**, which derives every one of
them from `data/fonts/LiberationSans-Regular.ttf` and records the file's
SHA-256. If a number here moves, the font moved, and `test_the_font_file_is_
the_pinned_one` says so before any width assertion has a chance to be
mysterious.

**They were also checked against Chrome 151**, headless, on a page using
`font-family: Arial` -- which is the whole reason this font was chosen, and
which had never actually been verified before Task D1. Chrome quantises
layout to 1/64 px per shaped run, so the criterion is agreement within that
and not equality:

    Hello world  79.1406  79.1406   exact
    Wikipedia    69.3594  69.3594   exact
    x             8.0000   8.0000   exact
    M            13.3281  13.3281   exact
    0             8.8984   8.9063   +1/128, Chrome's LayoutUnit
    space         4.4453   4.4531   +1/128, Chrome's LayoutUnit
    AV           21.3438  20.1563   -- KERNING, and only kerning

`AV` is in that list on purpose. It is the one comparison that fails, it
fails by 5.6%, and `docs/fonts.md` predicts the exact number: kerned
20.1562 against our unkerned 21.3438. A test suite that only used
kern-free strings would report a perfect match and would be hiding the one
real divergence this engine has.

**Non-ASCII is written as an escape**, per CLAUDE.md, and the module
constants below exist so that no test ever contains a literal NBSP. U+00A0
is indistinguishable from U+0020 in a terminal and does the opposite thing.
"""

from __future__ import annotations

import hashlib
from collections import Counter

import pytest

from mayshay.cssparse.cascade import ComputedStyle
from mayshay.cssparse.values import WHITE_SPACE_KEYWORDS
from mayshay.layout import text as T

SPACE = "\u0020"
TAB = "\u0009"
LF = "\u000a"
CR = "\u000d"
NBSP = "\u00a0"
IDEOGRAPHIC_SPACE = "\u3000"
ZWSP = "\u200b"
FORM_FEED = "\u000c"
VERTICAL_TAB = "\u000b"
EN_QUAD = "\u2000"
ARABIC_REH = "\u0631"


def style(**kwargs):
    return ComputedStyle(**kwargs)


# --------------------------------------------------------------------------
# The font
# --------------------------------------------------------------------------


def test_the_font_file_is_the_pinned_one():
    """Every layout number in this project depends on these exact bytes.

    First test in the file so that a swapped font is one obvious failure
    rather than a dozen puzzling ones a few pixels out.
    """
    digest = hashlib.sha256(T.FONT_PATH.read_bytes()).hexdigest()
    assert digest == T.FONT_SHA256, (
        "the vendored font changed; every advance below changes with it -- "
        "see docs/fonts.md"
    )


def test_the_font_metrics_match_the_recorded_derivations():
    """`docs/fonts.md` states the parts, not just the totals, so that a
    mismatch names which table an engine read rather than only that it
    disagreed."""
    metrics = T.font_metrics()
    assert metrics.units_per_em == 2048
    assert (metrics.ascent, metrics.descent, metrics.line_gap) == (1854, -434, 67)
    assert metrics.x_height == 1082


@pytest.mark.parametrize(
    ("text", "units", "px", "rounded"),
    [
        ("Hello world", 10130, 79.140625, "79.1406"),
        ("Wikipedia", 8878, 69.359375, "69.3594"),
        ("x", 1024, 8.0, "8.0000"),
        ("0", 1139, 8.8984375, "8.8984"),
        (SPACE, 569, 4.4453125, "4.4453"),
        ("M", 1706, 13.328125, "13.3281"),
    ],
)
def test_measure_matches_the_sample_advances_in_docs_fonts_md(text, units, px, rounded):
    """The fixture `docs/fonts.md` asks for: "if these move, the font
    changed".

    Asserted **exactly**, not approximately. Every one of these is a dyadic
    rational -- an integer number of font units times 16 over 2048 -- so it
    is representable in binary floating point without error, and a
    tolerance here would be a tolerance for the one class of defect this
    test exists to catch. The string column is the same number as
    `docs/fonts.md` prints it, so a reader can check the table by eye
    without converting anything.
    """
    assert T.advance_units(text) == units
    assert T.measure(text, style()) == px
    assert T.measure(text, style()) == units * 16 / 2048
    assert f"{T.measure(text, style()):.4f}" == rounded


def test_the_advance_is_linear_in_font_size_and_not_rounded():
    """The whole reason `hmtx` is read instead of `PIL.getlength`.

    Pillow returns integer-rounded advances -- `89.0` where the metrics say
    `89.6953` -- and neither of its own diagnostics reveals it (see
    `docs/measurement-hazards.md` instance 2). Two properties distinguish
    an exact implementation from a rounding one and a single font size
    cannot: the value at 13px is *not* an integer, and doubling the font
    size doubles the advance exactly.
    """
    small = T.measure("Hello world", style(font_size=_px(13)))
    large = T.measure("Hello world", style(font_size=_px(26)))
    assert large == pytest.approx(2 * small, abs=1e-9)
    assert small != round(small), "an exact advance at 13px is not an integer"
    assert small == pytest.approx(10130 * 13 / 2048, abs=1e-9)


def _px(value):
    from mayshay.cssparse.values import Length

    return Length(value, "px")


def test_the_kerning_divergence_is_the_documented_one():
    """Not a bug: `hmtx` advances only, no `GPOS` and no legacy `kern`.

    Chrome 151 gives `AV` as 20.1563 and `docs/fonts.md` records the kerned
    figure as 20.1562, against our 21.3438. Pinned as a test so that
    "adding kerning" is a deliberate change with a failing test attached,
    rather than something that quietly shifts every heading.
    """
    assert T.measure("AV", style()) == pytest.approx(21.34375, abs=1e-6)
    assert T.measure("To", style()) == pytest.approx(18.671875, abs=1e-6)
    # Kern-free, so these agree with Chrome exactly.
    assert T.measure("Hello world", style()) == pytest.approx(79.140625, abs=1e-6)


def test_a_character_with_no_glyph_falls_back_to_notdef_and_is_counted():
    """198 characters on the corpus -- Arabic, Devanagari, Burmese and CJK
    on the Wikipedia page -- have no glyph in Liberation Sans, because this
    project does no font fallback. They must not measure as zero: a missing
    glyph that costs nothing makes a line look like it fits."""
    metrics = Counter()
    width = T.measure(ARABIC_REH, style(), metrics=metrics)
    assert metrics["text_missing_glyph"] == 1
    assert width == pytest.approx(1536 * 16 / 2048, abs=1e-9)
    assert width > 0


def test_a_preserved_newline_has_no_advance():
    assert T.advance_units(LF) == 0
    assert T.advance_units("a" + LF + "b") == T.advance_units("ab")


def test_a_preserved_tab_is_measured_at_the_initial_tab_size_and_counted():
    """An approximation, and one that must be visible. A real tab advances
    to the next tab *stop*, which is a position and needs a line box, so
    this is right only where the tab starts on a stop."""
    metrics = Counter()
    assert T.advance_units(TAB, metrics=metrics) == 8 * 569
    assert metrics["text_preserved_tab_approximated"] == 1


# --------------------------------------------------------------------------
# What counts as white space
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("char", "is_white_space"),
    [
        (SPACE, True),
        (TAB, True),
        (LF, True),
        (CR, True),
        # Every one below is `str.isspace()` and is NOT CSS white space.
        (NBSP, False),
        (IDEOGRAPHIC_SPACE, False),
        (FORM_FEED, False),
        (VERTICAL_TAB, False),
        (EN_QUAD, False),
        # And one that is neither.
        (ZWSP, False),
        ("a", False),
    ],
)
def test_css_text_3_white_space_is_four_characters_and_not_str_isspace(
    char, is_white_space
):
    """CSS Text 3 section 4.1.1: control characters other than tab, line
    feed and carriage return are not white space, and neither is any of the
    Unicode space separators. Python disagrees about seven of them."""
    assert T.is_white_space(char) is is_white_space
    assert T.is_white_space_only(char) is is_white_space


def test_nbsp_is_not_white_space_and_is_the_one_that_actually_occurs():
    """36 text boxes on the corpus contain nothing but NBSP. Under
    `str.strip()` all 36 are blank; under CSS Text 3 all 36 are content
    with a real advance."""
    assert not T.is_white_space_only(NBSP)
    assert NBSP.isspace()  # which is exactly the trap
    assert T.advance_units(NBSP) == 569


def test_the_white_space_behaviour_table_covers_every_parsed_value():
    """The mechanical check, restated as a test so its failure has a name.

    The assert itself lives at import in `layout.text`, so a seventh value
    added to `cssparse.values` and forgotten cannot even be imported. This
    test exists to say what that assert is for.
    """
    assert set(T.WHITE_SPACE_BEHAVIOUR) == set(WHITE_SPACE_KEYWORDS)
    assert len(WHITE_SPACE_KEYWORDS) == 6


@pytest.mark.parametrize(
    ("value", "breaks", "spaces", "wraps"),
    [
        ("normal", True, True, True),
        ("pre", False, False, False),
        ("nowrap", True, True, False),
        ("pre-wrap", False, False, True),
        ("pre-line", False, True, True),
        ("break-spaces", False, False, True),
    ],
)
def test_every_row_of_the_css_text_3_table(value, breaks, spaces, wraps):
    """All six, spelled out, because the values are not ordered by
    strength: `pre-line` preserves breaks while collapsing spaces and
    `nowrap` collapses everything while refusing to wrap. A table with one
    row wrong passes any test that only exercises `normal` and `pre`."""
    behaviour = T.behaviour_of(value)
    assert behaviour.collapse_segment_breaks is breaks
    assert behaviour.collapse_spaces is spaces
    assert behaviour.wraps is wraps


# --------------------------------------------------------------------------
# Phase I collapsing
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("source", "white_space", "expected"),
    [
        # normal: runs collapse, breaks become spaces, the context's own
        # leading and trailing white space goes.
        ("  a   b  ", "normal", "a b"),
        ("a" + LF + "b", "normal", "a b"),
        ("a" + TAB + TAB + "b", "normal", "a b"),
        ("a" + SPACE + LF + SPACE + "b", "normal", "a b"),
        # nowrap collapses exactly as normal does; it differs only in
        # wrapping, which is not a Phase I concern.
        ("a   b", "nowrap", "a b"),
        # pre preserves everything.
        ("  a   b  ", "pre", "  a   b  "),
        ("a" + LF + "b", "pre", "a" + LF + "b"),
        # pre-wrap and break-spaces preserve everything too, in Phase I.
        ("  a  ", "pre-wrap", "  a  "),
        ("  a  ", "break-spaces", "  a  "),
        # pre-line preserves the break and collapses the spaces, including
        # the ones on either side of the break.
        ("a  " + LF + "  b", "pre-line", "a" + LF + "b"),
        ("a   b", "pre-line", "a b"),
        # NBSP never collapses, under any value, and does not let its
        # neighbours collapse into it.
        ("a" + NBSP + NBSP + "b", "normal", "a" + NBSP + NBSP + "b"),
        ("a " + NBSP + " b", "normal", "a " + NBSP + " b"),
    ],
)
def test_phase_one_collapsing(source, white_space, expected):
    assert T.collapse(source, white_space).text == expected


def test_a_carriage_return_is_a_segment_break_and_crlf_is_one_break():
    metrics = Counter()
    assert T.collapse("a" + CR + LF + "b", "pre", metrics).text == "a" + LF + "b"
    assert T.collapse("a" + CR + "b", "pre", metrics).text == "a" + LF + "b"
    assert T.collapse("a" + CR + LF + "b", "normal", metrics).text == "a b"
    assert metrics["text_carriage_returns_normalised"] == 3


def test_collapsing_crosses_text_node_boundaries_within_one_context():
    """CSS Text 3 section 4.1.1 step 4 is explicit that a collapsible space
    collapses into the previous one even across an inline boundary.
    `<span>a </span> <span>b</span>` has ONE space between the words, and
    no per-node function can know that -- which is why `collapse_ifc` takes
    the whole context."""
    runs = T.collapse_ifc(
        [("a ", "normal"), (" ", "normal"), (" b", "normal")], Counter()
    )
    assert [run.text for run in runs] == ["a ", "", "b"]
    assert "".join(run.text for run in runs) == "a b"


def test_a_whitespace_only_run_between_inlines_survives_as_the_separator():
    """The distinction the whole disposition report turns on. The same
    three characters are a word separator here and nothing at all in the
    next test."""
    runs = T.collapse_ifc(
        [("a", "normal"), (" " + LF + " ", "normal"), ("b", "normal")], Counter()
    )
    assert [run.text for run in runs] == ["a", SPACE, "b"]


def test_the_same_run_at_the_edge_of_the_context_collapses_away():
    metrics = Counter()
    runs = T.collapse_ifc(
        [(" " + LF + " ", "normal"), ("a", "normal"), ("  ", "normal")], metrics
    )
    assert [run.text for run in runs] == ["", "a", ""]
    assert metrics["text_whitespace_trimmed_ifc_start"] == 3
    assert metrics["text_whitespace_trimmed_ifc_end"] == 2


def test_two_adjacent_whitespace_runs_yield_one_space_between_them():
    runs = T.collapse_ifc(
        [("a", "normal"), ("  ", "normal"), ("  ", "normal"), ("b", "normal")],
        Counter(),
    )
    assert "".join(run.text for run in runs) == "a b"
    assert [run.text for run in runs] == ["a", SPACE, "", "b"]


def test_the_surviving_character_of_a_run_containing_a_break_is_the_break():
    """CSS Text 3 does step 1 (remove spaces around the break) before step
    2 (transform the break into a space), so the space that survives comes
    from the newline. Only observable in which run it is attributed to."""
    runs = T.collapse_ifc(
        [("a ", "normal"), (LF, "normal"), (" b", "normal")], Counter()
    )
    assert [run.text for run in runs] == ["a", SPACE, "b"]


def test_a_preserving_run_is_not_a_collapse_barrier_for_its_neighbours():
    """A preserved space is content, so a collapsible space beside it
    stays: step 4 collapses a space into a previous *collapsible* one."""
    runs = T.collapse_ifc([("a ", "normal"), (" b", "pre")], Counter())
    assert [run.text for run in runs] == ["a ", " b"]


# --------------------------------------------------------------------------
# Character conservation -- the mechanical check
# --------------------------------------------------------------------------


@pytest.mark.parametrize("white_space", sorted(WHITE_SPACE_KEYWORDS))
@pytest.mark.parametrize(
    "source",
    [
        "",
        " ",
        "   ",
        "a b",
        "  a  b  ",
        "a" + LF + LF + "b",
        TAB + "a" + TAB,
        NBSP + " " + NBSP,
        "a" + CR + LF + "b",
        " " + LF + TAB + " ",
    ],
)
def test_every_input_character_is_kept_transformed_or_removed(source, white_space):
    """`CollapsedRun.check()` asserts this on every call in the engine; the
    parametrisation here is what makes it a *test* rather than a hope that
    the assert is reached with interesting input."""
    run = T.collapse(source, white_space)
    assert run.kept + run.transformed + run.removed == len(source)
    assert len(run.text) == run.kept + run.transformed


def test_the_conservation_check_fails_when_a_character_goes_missing():
    """The check has to be shown to fire. A `CollapsedRun` built by hand
    with one character unaccounted for must not validate."""
    run = T.CollapsedRun(source="abc", text="ab", kept=2, transformed=0, removed=0)
    with pytest.raises(AssertionError, match="lost track of characters"):
        run.check()


def test_the_conservation_check_fails_when_the_output_length_disagrees():
    run = T.CollapsedRun(source="abc", text="ab", kept=3, transformed=0, removed=0)
    with pytest.raises(AssertionError, match="wrong number of output characters"):
        run.check()


# --------------------------------------------------------------------------
# Dispositions
# --------------------------------------------------------------------------


def test_the_three_dispositions_a_whitespace_only_box_can_reach():
    metrics = Counter()
    runs = T.collapse_ifc(
        [
            ("  ", "normal"),       # leading: collapses away
            ("a", "normal"),
            (" " + LF, "normal"),   # between content: one separating space
            ("b", "normal"),
            ("  ", "pre-wrap"),     # preserved verbatim
            ("c", "normal"),
        ],
        metrics,
    )
    values = ["normal", "normal", "normal", "normal", "pre-wrap", "normal"]
    got = [
        T.disposition_of(run, ws)
        for run, ws in zip(runs, values, strict=True)
        if T.is_white_space_only(run.source)
    ]
    assert got == ["collapsed_away", "single_space", "preserved_verbatim"]


def test_a_pre_line_whitespace_run_containing_a_break_is_a_forced_break():
    """The fourth disposition, and the one that only exists because
    `pre-line` splits the table's two collapsing columns. Zero corpus
    occurrences -- see `docs/synthetic-only-coverage.md`."""
    run = T.collapse_ifc(
        [("a", "pre-line"), ("  " + LF + "  ", "pre-line"), ("b", "pre-line")],
        Counter(),
    )[1]
    assert run.text == LF
    assert T.disposition_of(run, "pre-line") == "preserved_break"


def test_a_single_space_under_pre_is_preserved_and_not_a_separator():
    """Byte-identical output, opposite meaning. `disposition_of` has to
    consult the behaviour before the text, and this is the test that says
    so: swap the order of its first two checks and this fails while every
    other disposition test still passes."""
    run = T.collapse(SPACE, "pre")
    assert run.text == SPACE
    assert T.disposition_of(run, "pre") == "preserved_verbatim"
    assert T.disposition_of(T.collapse_ifc(
        [("a", "normal"), (SPACE, "normal"), ("b", "normal")], Counter()
    )[1], "normal") == "single_space"


# --------------------------------------------------------------------------
# Soft wrap opportunities
# --------------------------------------------------------------------------


def test_tokenize_marks_collapsed_spaces_as_wrap_opportunities():
    assert T.tokenize("a b c", "normal") == [
        (T.RUN, "a"), (T.BREAK_SPACE, " "), (T.RUN, "b"),
        (T.BREAK_SPACE, " "), (T.RUN, "c"),
    ]


def test_nowrap_and_pre_have_no_soft_wrap_opportunities_at_all():
    """The difference that matters most on this corpus: `nowrap` is on 24%
    of element boxes. A tokenizer that split on spaces regardless would
    give a `nowrap` box the min-content width of its widest word instead of
    its whole run."""
    assert T.tokenize("a b c", "nowrap") == [(T.RUN, "a b c")]
    assert T.tokenize("a  b", "pre") == [(T.RUN, "a  b")]


def test_a_preserved_break_is_forced_under_every_preserving_value():
    for value in ("pre", "pre-wrap", "pre-line", "break-spaces"):
        tokens = T.tokenize("a" + LF + "b", value)
        assert (T.FORCED_BREAK, LF) in tokens, value


def test_a_run_of_preserved_spaces_is_one_wrap_opportunity():
    assert T.tokenize("a  b", "pre-wrap") == [
        (T.RUN, "a"), (T.BREAK_SPACE, "  "), (T.RUN, "b"),
    ]


def test_nbsp_is_never_a_wrap_opportunity():
    """The property that makes NBSP worth its own tests. It looks like a
    space, measures like a space, and must never break like one."""
    for value in sorted(WHITE_SPACE_KEYWORDS):
        assert T.tokenize("a" + NBSP + "b", value) == [(T.RUN, "a" + NBSP + "b")], value
