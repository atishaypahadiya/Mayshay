"""Soft wrap opportunities -- UAX #14, Phase 3 Task D2.

**Every expected segmentation in this file was measured against Chrome
151.0.7922.174 before it was written down**, by putting the string in a 1px
`<div>` -- which forces a break at every opportunity -- and reading back
which characters landed on which line with a one-character `Range` per
character. Counting `getClientRects()` is *not* enough and was tried first:
a soft hyphen makes Chrome return three rects on one line, so rect count
and line count are different questions.

Two suites, and they must disagree with each other or neither means
anything:

* `tailored=True`, the default, is what this engine lays out with, and it
  is compared against Chrome.
* `tailored=False` is UAX #14 with nothing added, and it is compared
  against the rules as written.

On the 58-fixture battery the first agrees with Chrome on 57 and the second
on 51. The seven-fixture gap is the whole reason the tailoring table
exists, and the one remaining disagreement is U+00AD SOFT HYPHEN, which
occurs zero times on the corpus.

Non-ASCII is written as an escape throughout, per CLAUDE.md. `a\\u2010b` and
`a\\u2013b` differ by one hyphen-like glyph nobody can tell apart in a
terminal and they are the same class; `a\\u2014b` is a different class and
breaks on both sides.
"""

from __future__ import annotations

from collections import Counter

import pytest

from mayshay.layout import linebreak as LB

NBSP = "\u00a0"
ZWSP = "\u200b"
WORD_JOINER = "\u2060"
SOFT_HYPHEN = "\u00ad"
HYPHEN = "\u2010"
EN_DASH = "\u2013"
EM_DASH = "\u2014"
ELLIPSIS = "\u2026"
OBJECT_REPLACEMENT = "\ufffc"
CJK_ONE = "\u4e00"
CJK_TWO = "\u4e8c"
IDEOGRAPHIC_FULL_STOP = "\u3002"
HIRAGANA_A = "\u3042"
HIRAGANA_I = "\u3044"
ARABIC_ALEF = "\u0627"
DEVANAGARI_KA = "\u0915"
DEVANAGARI_KHA = "\u0916"
COMBINING_ACUTE = "\u0301"
GRINNING_FACE = "\U0001f600"
MULTIPLICATION = "\u00d7"
BULLET = "\u2022"
NON_BREAKING_HYPHEN = "\u2011"
DEGREE = "\u00b0"
SECTION = "\u00a7"
REGISTERED = "\u00ae"
TRADEMARK = "\u2122"
ASTERISM = "\u2042"


def segments(text: str, *, tailored: bool = True) -> list[str]:
    """The text cut at every break opportunity -- what a 1px line would do."""
    flags = LB.break_opportunities(text, tailored=tailored)
    out: list[str] = []
    start = 0
    for index in range(1, len(text)):
        if flags[index]:
            out.append(text[start:index])
            start = index
    out.append(text[start:])
    return out


# --------------------------------------------------------------------------
# The rules this engine and Chrome agree on
# --------------------------------------------------------------------------
#
# Every row was measured. Where UAX #14 and Chrome disagree the row is in
# the tailoring test below instead, so this table is not quietly doing two
# jobs.

AGREED = [
    ("ab", ["ab"]),
    ("a b", ["a ", "b"]),
    ("a-b", ["a-", "b"]),
    (f"a{HYPHEN}b", [f"a{HYPHEN}", "b"]),
    (f"a{EN_DASH}b", [f"a{EN_DASH}", "b"]),
    (f"a{EM_DASH}b", ["a", EM_DASH, "b"]),
    ("a,b", ["a,b"]),
    ("1,000", ["1,000"]),
    ("1,000.5", ["1,000.5"]),
    ("a.b", ["a.b"]),
    ("e.g.", ["e.g."]),
    ("a:b", ["a:b"]),
    ("a;b", ["a;b"]),
    ("a?b", ["a?", "b"]),
    ("a(b", ["a(b"]),
    ("a)b", ["a)b"]),
    ("(ab)c", ["(ab)c"]),
    ('a"b', ['a"b']),
    ("a'b", ["a'b"]),
    (f"a{ZWSP}b", [f"a{ZWSP}", "b"]),
    (f"a{NBSP}b", [f"a{NBSP}b"]),
    (f"a{WORD_JOINER}b", [f"a{WORD_JOINER}b"]),
    (f"a{NON_BREAKING_HYPHEN}b", [f"a{NON_BREAKING_HYPHEN}b"]),
    (f"{CJK_ONE}{CJK_TWO}", [CJK_ONE, CJK_TWO]),
    (f"a{CJK_ONE}", ["a", CJK_ONE]),
    (f"{HIRAGANA_A}{HIRAGANA_I}", [HIRAGANA_A, HIRAGANA_I]),
    (
        f"{CJK_ONE}{IDEOGRAPHIC_FULL_STOP}{CJK_TWO}",
        [f"{CJK_ONE}{IDEOGRAPHIC_FULL_STOP}", CJK_TWO],
    ),
    ("a=b", ["a=b"]),
    ("a+b", ["a+b"]),
    ("a@b", ["a@b"]),
    ("a_b", ["a_b"]),
    ("1a", ["1a"]),
    ("a1", ["a1"]),
    ("1%a", ["1%a"]),
    ("$1", ["$1"]),
    (f"a{MULTIPLICATION}b", [f"a{MULTIPLICATION}b"]),
    (f"a{ELLIPSIS}b", [f"a{ELLIPSIS}", "b"]),
    (f"a{BULLET}b", [f"a{BULLET}b"]),
    ("a-b-c", ["a-", "b-", "c"]),
    (f"co{HYPHEN}op", [f"co{HYPHEN}", "op"]),
    (f"{ARABIC_ALEF}{ARABIC_ALEF}", [f"{ARABIC_ALEF}{ARABIC_ALEF}"]),
    (f"{DEVANAGARI_KA}{DEVANAGARI_KHA}", [f"{DEVANAGARI_KA}{DEVANAGARI_KHA}"]),
    (f"a{COMBINING_ACUTE}b", [f"a{COMBINING_ACUTE}b"]),
    (f"a{GRINNING_FACE}b", ["a", GRINNING_FACE, "b"]),
    (f"a{OBJECT_REPLACEMENT}b", ["a", OBJECT_REPLACEMENT, "b"]),
    (f"10{DEGREE}C", [f"10{DEGREE}C"]),
    ("3+4", ["3+4"]),
]


@pytest.mark.parametrize("text,expected", AGREED, ids=[repr(t) for t, _ in AGREED])
def test_break_opportunities_match_chrome(text, expected):
    assert segments(text) == expected


def test_the_atomic_inline_placeholder_breaks_on_both_sides():
    """`docs/measurement-hazards.md` instance fourteen, as a test.

    D1's min-content for `a<inline-block>b` came out 57.81 where Chrome
    gives 40.00, because reading CSS Text 3 says there is no break
    opportunity beside an atomic inline and UAX #14's LB20 says there is:
    U+FFFC is class CB and LB20 breaks before and after it.

    Asserted here on the character rather than only through the intrinsic
    size, so the rule is tested where it lives.
    """
    assert LB.line_break_class(OBJECT_REPLACEMENT) == LB.CB
    assert segments(f"a{OBJECT_REPLACEMENT}b") == ["a", OBJECT_REPLACEMENT, "b"]
    # ...and under a tailoring-free reading too: this one is the spec's.
    assert segments(f"a{OBJECT_REPLACEMENT}b", tailored=False) == [
        "a", OBJECT_REPLACEMENT, "b"
    ]


# --------------------------------------------------------------------------
# Where Chrome and UAX #14 disagree
# --------------------------------------------------------------------------

TAILORED = [
    # text, what Chrome does, what UAX #14 says
    ("a/b", ["a/b"], ["a/", "b"]),
    # `["http://", "x.co/", "a"]` and not `["http:/", "/x.co/", ...]`:
    # LB13's `x SY` forbids a break *before* a solidus, so the second `/`
    # stays with the first. Written down wrong on the first draft and
    # corrected by running it.
    ("http://x.co/a", ["http://x.co/a"], ["http://", "x.co/", "a"]),
    ("wiki/HTML#History", ["wiki/HTML#History"], ["wiki/", "HTML#History"]),
    ("a|b", ["a|b"], ["a|", "b"]),
    ("a!b", ["a!b"], ["a!", "b"]),
    ("x!y!z", ["x!y!z"], ["x!", "y!", "z"]),
]


@pytest.mark.parametrize(
    "text,chrome,spec", TAILORED, ids=[repr(t) for t, _, _ in TAILORED]
)
def test_the_tailorings_are_the_difference_from_the_spec(text, chrome, spec):
    """The two readings must **disagree** on every row here.

    A tailoring that changed nothing would pass a test that only checked
    the tailored answer, so both are asserted and the assertion that they
    differ is what makes the row worth having.
    """
    assert segments(text, tailored=True) == chrome
    assert segments(text, tailored=False) == spec
    assert chrome != spec


def test_exclamation_and_question_are_the_same_class_and_behave_differently():
    """The row that proves the tailorings cannot live in the class table.

    `!` and `?` are both `EX` in UAX #14 -- no reading separates them --
    and Chrome 151 breaks after one and not the other. Measured:
    `aaaa!bbbb` stays on one line in a 30px div and `aaaa?bbbb` breaks.
    A class-level "no break after EX" entry would have silently changed
    `?` as well, which is why the table is keyed by code point.
    """
    assert LB.line_break_class("!") == LB.line_break_class("?") == LB.EX
    assert segments("a!b") == ["a!b"]
    assert segments("a?b") == ["a?", "b"]
    assert segments("a!b", tailored=False) == ["a!", "b"]
    assert segments("a?b", tailored=False) == ["a?", "b"]


def test_the_one_fixture_chrome_and_the_spec_both_lose():
    """U+00AD SOFT HYPHEN: class BA, so UAX #14 breaks after it and Chrome
    does not.

    Left as a divergence rather than tailored away, because it is a
    *conditional* hyphen -- a break there is supposed to insert a visible
    hyphen glyph, which this engine cannot do -- and because the corpus
    contains **zero** of them. A tailoring for a character that never
    occurs would be an untestable rule pretending to be coverage.
    """
    assert segments(f"a{SOFT_HYPHEN}b") == [f"a{SOFT_HYPHEN}", "b"]


# --------------------------------------------------------------------------
# Structure
# --------------------------------------------------------------------------


def test_no_break_at_the_start_of_the_text():
    """LB2. `out[0]` is always False, so the list indexes like the string
    and no caller has to remember an off-by-one."""
    assert LB.break_opportunities("a b")[0] is False
    assert LB.break_opportunities(" ab")[0] is False
    assert LB.break_opportunities("") == []
    assert LB.break_opportunities("a") == [False]


def test_a_run_of_spaces_offers_one_opportunity_after_all_of_them():
    """LB7 forbids a break *before* a space and LB18 allows one after, so
    three spaces are one opportunity and not three. Under `pre-wrap` that
    is what keeps a run of preserved spaces on one line."""
    assert segments("a   b") == ["a   ", "b"]


def test_a_segment_break_takes_no_opportunity_beside_it():
    """LB6 forbids a break before a mandatory one. A preserved newline is
    handled by the line breaker, not here, and offering an opportunity in
    front of it would put an empty line box before every one."""
    flags = LB.break_opportunities("a\u000ab")
    assert flags[1] is False


def test_the_class_table_covers_every_punctuation_character_in_the_corpus():
    """The fallback counter, as a test rather than as a report line.

    Every letter and digit falls through the general-category fallback and
    is classified correctly, and so does every combining mark, which LB9
    resolves to its base's class anyway. The number that matters is the
    third bucket: a character that is none of those and got `AL` by
    default. On the corpus that is **zero** -- 61,667 letters and digits
    and 58 combining marks took the fallback and nothing else did.

    Asserted on the characters the corpus actually contains rather than on
    the corpus itself, so it does not need the pages present.
    """
    metrics: Counter[str] = Counter()
    corpus_punctuation = (
        " .,-\"()<>[]/:|;&'#=+!?$_"
        + EN_DASH + EM_DASH + NBSP + SECTION + REGISTERED + TRADEMARK
    )
    for char in corpus_punctuation:
        LB.line_break_class(char, metrics=metrics)
    assert metrics["linebreak_class_fallback_other"] == 0
    assert metrics["linebreak_class_fallback_letter_or_digit"] == 0


def test_the_fallback_counter_splits_letters_from_everything_else():
    metrics: Counter[str] = Counter()
    for char in "aZ9":
        LB.line_break_class(char, metrics=metrics)
    LB.line_break_class(ASTERISM, metrics=metrics)  # not in the table
    LB.line_break_class(COMBINING_ACUTE, metrics=metrics)
    assert metrics["linebreak_class_fallback_letter_or_digit"] == 3
    assert metrics["linebreak_class_fallback_combining_mark"] == 1
    assert metrics["linebreak_class_fallback_other"] == 1


def test_opportunities_are_counted_and_partitioned():
    metrics: Counter[str] = Counter()
    LB.break_opportunities("alpha beta-gamma", metrics=metrics)
    assert metrics["linebreak_opportunities"] == 2
    assert metrics["linebreak_opportunities_at_space"] == 1
    assert metrics["linebreak_opportunities_other"] == 1


def test_the_tailorings_are_counted_where_they_fire():
    metrics: Counter[str] = Counter()
    LB.break_opportunities("a/b|c!d", metrics=metrics)
    assert metrics["linebreak_tailored_no_break_after_solidus"] == 1
    assert metrics["linebreak_tailored_no_break_after_vertical_line"] == 1
    assert metrics["linebreak_tailored_no_break_after_exclamation"] == 1
    # ...and not when the untailored reading is asked for.
    spec: Counter[str] = Counter()
    LB.break_opportunities("a/b|c!d", tailored=False, metrics=spec)
    assert spec["linebreak_tailored_no_break_after_solidus"] == 0


def test_a_combining_mark_takes_the_class_of_what_it_attaches_to():
    """LB9. A mark that kept its own class would offer a break between a
    letter and its own accent, which is the kind of defect that shows up as
    one page in one language looking wrong."""
    assert LB.line_break_class(COMBINING_ACUTE) == LB.CM
    assert segments(f"a{COMBINING_ACUTE}b") == [f"a{COMBINING_ACUTE}b"]
    # LB10: a mark with nothing in front of it is `AL`.
    assert segments(f"{COMBINING_ACUTE}b") == [f"{COMBINING_ACUTE}b"]
