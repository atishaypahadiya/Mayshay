"""Media query parsing and evaluation.

Phase 3 Task A. The measurement that motivated it: with at-rules skipped,
51% of the Hacker News page's CSS and 46% of Wikipedia's never reached the
cascade, and every `display` declaration in `news.css` sits inside a
`@media` block -- so the display census was describing the CSS we evaluate,
not the CSS the page ships.

Two things are tested separately on purpose:

* that a query parses into the right shape, and
* that it evaluates to the right answer *at a given viewport*.

A test that only checks one viewport cannot tell a working comparison from
a constant. Every width test here therefore asserts both sides of its
breakpoint.
"""

from __future__ import annotations

from collections import Counter

import pytest

from mayshay.cssparse.media import (
    Viewport,
    matches,
    parse_media_query_list,
)
from mayshay.cssparse.tokenizer import CssTokenizer

DESKTOP = Viewport(1280, 1024)
NARROW = Viewport(600, 900)


def evaluate(prelude: str, viewport: Viewport = DESKTOP) -> tuple[bool, Counter]:
    """Parse and evaluate a prelude as written in a stylesheet.

    Tokenizing here (rather than taking `AtRule.prelude`) is deliberate: it
    is the path a caller outside the parser takes, and it is the one that
    carries a trailing `EOFToken` -- which made every query malformed until
    `_significant` learned to drop it.
    """
    metrics: Counter[str] = Counter()
    queries = parse_media_query_list(list(CssTokenizer(prelude).tokenize()))
    return matches(queries, viewport, metrics), metrics


# --- media types --------------------------------------------------------


@pytest.mark.parametrize("prelude", ["all", "screen", "SCREEN", "only screen"])
def test_media_types_we_are_match(prelude):
    assert evaluate(prelude)[0] is True


def test_print_does_not_match_and_is_counted():
    result, metrics = evaluate("print")
    assert result is False
    assert metrics["media_types_skipped"] == 1
    assert metrics["media_type_print"] == 1


def test_unknown_media_type_does_not_match():
    assert evaluate("speech")[0] is False
    assert evaluate("tty")[0] is False


def test_not_inverts_a_media_type():
    # `not screen` is false because we are a screen; `not print` is true
    # because we are not. Both directions, or this passes on a constant.
    assert evaluate("not screen")[0] is False
    assert evaluate("not print")[0] is True


def test_only_is_accepted_and_does_not_negate():
    assert evaluate("only screen")[0] is True
    assert evaluate("only print")[0] is False


# --- width --------------------------------------------------------------


def test_min_width_compares_against_the_viewport():
    assert evaluate("(min-width: 1000px)", DESKTOP)[0] is True
    assert evaluate("(min-width: 1000px)", NARROW)[0] is False


def test_max_width_compares_against_the_viewport():
    assert evaluate("(max-width: 1000px)", DESKTOP)[0] is False
    assert evaluate("(max-width: 1000px)", NARROW)[0] is True


def test_width_bounds_are_inclusive():
    """`min-width: 600px` matches a 600px viewport. Off-by-one here would
    silently move every breakpoint by a pixel."""
    assert evaluate("(min-width: 600px)", NARROW)[0] is True
    assert evaluate("(max-width: 600px)", NARROW)[0] is True
    assert evaluate("(min-width: 601px)", NARROW)[0] is False
    assert evaluate("(max-width: 599px)", NARROW)[0] is False


def test_exact_width_requires_equality():
    assert evaluate("(width: 600px)", NARROW)[0] is True
    assert evaluate("(width: 601px)", NARROW)[0] is False


def test_boolean_width_form_is_true_for_a_real_viewport():
    assert evaluate("(width)", DESKTOP)[0] is True
    assert evaluate("(width)", Viewport(0, 500))[0] is False


def test_height_is_read_from_the_height_not_the_width():
    """A viewport whose width and height sit on OPPOSITE sides of the
    threshold. Testing 1280x1024 against 1000px cannot tell the two apart:
    both exceed it. This one can -- injection-tested by making
    `_match_feature` read the width for every feature, which the earlier
    version of this test passed.
    """
    tall = Viewport(500, 1500)
    assert evaluate("(min-height: 1000px)", tall)[0] is True
    assert evaluate("(min-width: 1000px)", tall)[0] is False
    wide = Viewport(1500, 500)
    assert evaluate("(min-height: 1000px)", wide)[0] is False
    assert evaluate("(min-width: 1000px)", wide)[0] is True


# --- units --------------------------------------------------------------


def test_em_resolves_against_the_initial_font_size():
    """40em is 640px at the initial 16px -- there is no element to inherit
    from inside a media query."""
    assert evaluate("(min-width: 40em)", Viewport(640, 480))[0] is True
    assert evaluate("(min-width: 40em)", Viewport(639, 480))[0] is False


def test_absolute_units_convert():
    # 1in == 96px, so a 96px viewport is exactly at the boundary.
    assert evaluate("(min-width: 1in)", Viewport(96, 100))[0] is True
    assert evaluate("(min-width: 1in)", Viewport(95, 100))[0] is False
    assert evaluate("(min-width: 72pt)", Viewport(96, 100))[0] is True


# --- orientation --------------------------------------------------------


def test_orientation():
    assert evaluate("(orientation: landscape)", DESKTOP)[0] is True
    assert evaluate("(orientation: portrait)", DESKTOP)[0] is False
    assert evaluate("(orientation: portrait)", NARROW)[0] is True
    assert evaluate("(orientation: landscape)", NARROW)[0] is False


def test_a_square_viewport_is_landscape():
    assert evaluate("(orientation: landscape)", Viewport(800, 800))[0] is True


# --- and / or / commas --------------------------------------------------


def test_media_type_and_feature():
    assert evaluate("screen and (min-width: 1000px)", DESKTOP)[0] is True
    assert evaluate("screen and (min-width: 1000px)", NARROW)[0] is False
    assert evaluate("print and (min-width: 1000px)", DESKTOP)[0] is False


def test_and_requires_every_feature():
    q = "screen and (min-width: 600px) and (max-width: 1000px)"
    assert evaluate(q, NARROW)[0] is True
    assert evaluate(q, DESKTOP)[0] is False  # too wide for the max


def test_comma_list_matches_if_any_query_matches():
    assert evaluate("print, screen and (min-width: 100px)", DESKTOP)[0] is True
    assert evaluate("print, speech")[0] is False


def test_a_false_query_does_not_veto_a_later_true_one():
    """The list is an OR. A first query that is evaluated and false -- not
    merely skipped like `print` -- must not stop a later one from matching.
    Injection-tested: returning False on the first falsy query passes
    `test_comma_list_matches_if_any_query_matches`, because `print` exits
    early and never reaches that code.
    """
    assert evaluate("(min-width: 9999px), screen", DESKTOP)[0] is True
    assert evaluate("screen, (min-width: 9999px)", DESKTOP)[0] is True
    assert evaluate("(min-width: 9999px), (min-height: 9999px)", DESKTOP)[0] is False


def test_a_malformed_query_does_not_take_its_siblings_down():
    """5.4.1: a bad query in a list is `not all`, and the rest still apply."""
    result, metrics = evaluate("(min-width, screen", DESKTOP)
    assert metrics["media_queries_malformed"] >= 1
    result, metrics = evaluate("screen or (min-width:1px), screen", DESKTOP)
    assert result is True
    assert metrics["media_queries_malformed"] == 1


# --- what we deliberately do not evaluate -------------------------------


@pytest.mark.parametrize(
    "prelude,feature",
    [
        ("(prefers-color-scheme: dark)", "prefers-color-scheme"),
        ("(prefers-reduced-motion: reduce)", "prefers-reduced-motion"),
        ("(hover: hover)", "hover"),
        ("(min-device-pixel-ratio: 2)", "min-device-pixel-ratio"),
        ("(min-resolution: 2dppx)", "min-resolution"),
    ],
)
def test_unsupported_features_are_false_and_named(prelude, feature):
    result, metrics = evaluate(prelude)
    assert result is False
    assert metrics["media_queries_unsupported"] == 1
    # Named, not just tallied: "we skipped 40 queries" is not actionable,
    # "we skipped 13 prefers-color-scheme" is.
    assert metrics[f"media_feature_{feature}"] == 1


# --- calc() -------------------------------------------------------------
#
# Only the additive length form, `calc(A + B - C)`. It appears in 25 of the
# corpus's 114 @media preludes, all breakpoints of the shape
# `calc(1120px - 1px)`; supporting it took the unevaluated-query count from
# 40 to 15 at 1280x1024. Everything else stays unsupported, because a wrong
# breakpoint silently applies or withholds a whole block of CSS.


def test_calc_subtraction_is_evaluated():
    """`calc(1120px - 1px)` is 1119px. Both sides of that boundary, or this
    passes on any implementation that returns a constant."""
    assert evaluate("(max-width: calc(1120px - 1px))", Viewport(1119, 800))[0] is True
    assert evaluate("(max-width: calc(1120px - 1px))", Viewport(1120, 800))[0] is False


def test_calc_addition_is_evaluated():
    assert evaluate("(min-width: calc(1000px + 500px))", Viewport(1500, 800))[0] is True
    assert evaluate("(min-width: calc(1000px + 500px))", Viewport(1499, 800))[0] is False


def test_calc_chains_more_than_two_terms():
    # 2000 - 100 - 100 == 1800. A parser that applied one sign to the whole
    # tail would get 2000 - 0 == 2000 and pass a two-term test.
    assert evaluate("(min-width: calc(2000px - 100px - 100px))", Viewport(1800, 9))[0] is True
    assert evaluate("(min-width: calc(2000px - 100px - 100px))", Viewport(1799, 9))[0] is False


def test_calc_mixes_units():
    # 1in == 96px, so calc(1in + 4px) is 100px.
    assert evaluate("(min-width: calc(1in + 4px))", Viewport(100, 80))[0] is True
    assert evaluate("(min-width: calc(1in + 4px))", Viewport(99, 80))[0] is False


@pytest.mark.parametrize(
    "prelude",
    [
        "(width: calc(100px * 2))",      # multiplication
        "(width: calc(100px / 2))",      # division
        "(min-width: calc(50% - 1px))",  # percentage
        "(min-width: calc(calc(1px)))",  # nesting
        "(min-width: calc())",           # empty
        "(min-width: calc(- 5px))",      # leading operator
        "(min-width: calc(5px 6px))",    # no operator
        "(min-width: calc(5px -))",      # trailing operator
        "(min-width: calc(5px + + 6px))",  # doubled operator
    ],
)
def test_calc_forms_we_do_not_evaluate_are_unsupported(prelude):
    """Not merely wrong-but-quiet: recorded, so the gap stays countable."""
    result, metrics = evaluate(prelude)
    assert result is False
    assert metrics["media_queries_unsupported"] == 1


def test_calc_is_not_accepted_for_orientation():
    result, metrics = evaluate("(orientation: calc(1px))")
    assert result is False
    assert metrics["media_queries_unsupported"] == 1


def test_range_syntax_is_unsupported():
    result, metrics = evaluate("(400px <= width <= 700px)")
    assert result is False
    assert metrics["media_queries_unsupported"] == 1


def test_unsupported_feature_is_false_even_under_not():
    """Deliberate deviation. The spec says an unknown feature is false, so
    `not (unknown)` is true -- but ours is "unsupported", not "unknown".
    `prefers-color-scheme` is a feature browsers do support, and inverting
    our ignorance of it would APPLY CSS meant for a state we cannot see.
    """
    result, metrics = evaluate("not (prefers-color-scheme: dark)")
    assert result is False
    assert metrics["media_queries_unsupported"] == 1


def test_or_is_unsupported_and_recorded():
    result, metrics = evaluate("(min-width: 1px) or (min-width: 2px)")
    assert result is False
    assert metrics["media_queries_malformed"] == 1


# --- malformed input ----------------------------------------------------


@pytest.mark.parametrize(
    "prelude",
    [
        "",                        # empty list is `not all`
        "screen and",              # dangling `and`
        "screen and and",
        "(min-width:1px) and",
        "screen (min-width: 1px)", # missing `and`
        "(min-width: 1px",         # unclosed paren
    ],
)
def test_malformed_queries_never_match(prelude):
    result, metrics = evaluate(prelude)
    assert result is False
    assert metrics["media_queries_malformed"] >= 1


def test_metrics_count_evaluated_and_matched():
    _, metrics = evaluate("screen, print, (min-width: 1px)", DESKTOP)
    assert metrics["media_queries_matched"] == 2   # screen, (min-width:1px)
    assert metrics["media_types_skipped"] == 1     # print
