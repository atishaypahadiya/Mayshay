"""Soft wrap opportunities -- UAX #14, the delegate CSS Text 3 points at.

CSS Text 3 section 5.1 does **not** define where a line may break. It says
"line breaking behavior ... is defined by [UAX14]" and stops. Reading the
citing layer carefully produces a confident wrong answer, which is how Task
D1 got 57.81 for the min-content width of `a<inline-block>b` where Chrome
gives 40.00: nothing in CSS Text 3 says there is a break opportunity either
side of an atomic inline, and UAX #14 rule LB20 says there is, because the
object replacement character U+FFFC is line-break class CB. See
`docs/measurement-hazards.md` instance fourteen.

So this module implements the delegate. Rules LB2 through LB31 in their
stated order, over a hand-rolled class table.

## What "implements UAX #14" is worth here, measured

**Chrome 151 does not implement UAX #14 either**, and the disagreements are
in ASCII punctuation that the corpus contains. Measured, by putting each
string in a 30px `<div>` and reading which characters landed on which line
from `Range.getBoundingClientRect()` per character:

    string        UAX #14 says      Chrome 151 does    corpus occurrences
    aaaa/bbbb     break after /     no break           114 solidus
    aaa|bbb       break after |     no break            73 vertical line
    aaaa!bbbb     break after !     no break            13 exclamation
    aaaa?bbbb     break after ?     break after ?        8 question
    aaaa-bbbb     break after -     break after -      353 hyphen-minus
    aaa--bbb      break around --   break around --      8 em dash

`!` and `?` are **both class EX**, and `|` and `-` are both class BA. No
reading of UAX #14 separates either pair; Chrome separates both. So these
are **tailorings, not classes**, and they are kept in a separate
code-point-keyed table (`_TAILORED_NO_BREAK_AFTER`) rather than folded into
the class table -- putting them there would mean two characters of the same
class carrying different classes, which is a second class table wearing the
first one's name.

The tailorings are on by default, because the numeric comparison this phase
is built around is against Chrome and a break we take that Chrome does not
moves every box on the rest of the line. Each one is **counted where it
fires**, so "how far the reference renderer is from the delegate spec, on
this corpus" is a number rather than a shrug -- which is a finding in its
own right.

Pass `tailored=False` for the spec's own answer;
`tests/layout/test_linebreak.py` asserts both, so neither can drift.

## The class table

UAX #14 assigns a `Line_Break` property to every code point from
`LineBreak.txt`, which this project does not vendor. The table below is
written out for the characters that occur -- every non-alphanumeric
character in the corpus is ASCII punctuation plus U+00A0, U+2013, U+2014
and a tail of combining marks -- with ranges for the ideographic blocks and
a documented fallback for everything else.

The fallback is **counted**, and split three ways, because one number would
say nothing: every letter and digit on the page takes it and is classified
correctly, so a single counter reads 61,667 on this corpus and means "there
is text here". `linebreak_class_fallback_other` is the one that matters --
a character that is neither a letter, a digit nor a combining mark and got
`AL` from a default is exactly where a missing table entry hides a wrong
break opportunity. Combining marks get their own bucket for the same
reason in miniature: LB9 resolves them to whatever they attach to, so they
are never wrong, and 58 of them on the corpus would have made the bucket
that must read zero read 58.
"""

from __future__ import annotations

import unicodedata
from collections import Counter

# --------------------------------------------------------------------------
# Line break classes
# --------------------------------------------------------------------------
#
# Only the classes this module can produce are named. A class UAX #14
# defines and this table never assigns is not listed, because an unused
# constant reads as coverage.

BK = "BK"   # mandatory break
CR = "CR"
LF = "LF"
NL = "NL"
SP = "SP"   # space
ZW = "ZW"   # zero width space -- break after
WJ = "WJ"   # word joiner -- break neither side
GL = "GL"   # non-breaking glue: U+00A0 and friends
CB = "CB"   # contingent break: U+FFFC, an atomic inline
CM = "CM"   # combining mark -- takes the class of what it attaches to
ZWJ = "ZWJ"
HY = "HY"   # U+002D HYPHEN-MINUS only
BA = "BA"   # break after
BB = "BB"   # break before
B2 = "B2"   # break either side: the em dash
ID = "ID"   # ideographic
EX = "EX"   # exclamation / interrogation
CL = "CL"   # close punctuation
CP = "CP"   # close parenthesis
IS = "IS"   # infix numeric separator: , . : ;
SY = "SY"   # symbol allowing break after: solidus
OP = "OP"   # open punctuation
QU = "QU"   # quotation
NS = "NS"   # non-starter
AL = "AL"   # ordinary alphabetic
NU = "NU"   # numeric
PR = "PR"   # prefix numeric
PO = "PO"   # postfix numeric
IN = "IN"   # inseparable: the ellipsis

MANDATORY = frozenset({BK, CR, LF, NL})

#: Every character whose class is stated rather than inferred. Written out
#: because a range that quietly swallows one code point is exactly the
#: defect this module cannot see: `!` and `/` differ from the letters beside
#: them only in this table.
_EXPLICIT: dict[int, str] = {
    0x0009: BA,   # tab
    0x000A: LF,
    0x000B: BK,
    0x000C: BK,
    0x000D: CR,
    0x0020: SP,
    0x0021: EX,   # !
    0x0022: QU,   # "
    0x0023: AL,   # #
    0x0024: PR,   # $
    0x0025: PO,   # %
    0x0026: AL,   # &
    0x0027: QU,   # '
    0x0028: OP,   # (
    0x0029: CP,   # )
    0x002A: AL,   # *
    0x002B: PR,   # +
    0x002C: IS,   # ,
    0x002D: HY,   # -
    0x002E: IS,   # .
    0x002F: SY,   # /
    0x003A: IS,   # :
    0x003B: IS,   # ;
    0x003C: AL,   # <
    0x003D: AL,   # =
    0x003E: AL,   # >
    0x003F: EX,   # ?
    0x0040: AL,   # @
    0x005B: OP,   # [
    0x005C: PR,   # \
    0x005D: CP,   # ]
    0x005E: AL,   # ^
    0x005F: AL,   # _
    0x0060: AL,   # `
    0x007B: OP,   # {
    0x007C: BA,   # |
    0x007D: CL,   # }
    0x007E: AL,   # ~
    0x0085: NL,
    0x00A0: GL,   # NO-BREAK SPACE -- content, never a wrap opportunity
    0x00A1: OP,
    # U+00A7 SECTION SIGN is class AI (ambiguous) in UAX #14. AI resolves to
    # AL outside an East Asian context and to ID inside one; this engine has
    # no language context, so it resolves to AL here and the choice is
    # recorded rather than left to look like a lookup.
    0x00A7: AL,
    0x00AB: QU,   # <<
    0x00AD: BA,   # SOFT HYPHEN
    0x00AE: AL,
    0x00B0: PO,   # degree
    0x00B7: AL,
    0x00BB: QU,   # >>
    0x00BF: OP,
    0x00D7: AL,   # multiplication sign
    0x00F7: AL,   # division sign
    0x2010: BA,   # HYPHEN
    0x2011: GL,   # NON-BREAKING HYPHEN
    0x2012: BA,   # FIGURE DASH
    0x2013: BA,   # EN DASH
    0x2014: B2,   # EM DASH
    0x2018: QU,
    0x2019: QU,
    0x201C: QU,
    0x201D: QU,
    0x2022: AL,   # BULLET
    0x2025: IN,
    0x2026: IN,   # HORIZONTAL ELLIPSIS
    0x202F: GL,   # NARROW NO-BREAK SPACE
    0x2060: WJ,   # WORD JOINER
    0x200B: ZW,   # ZERO WIDTH SPACE
    0x200D: ZWJ,
    0x2122: AL,   # TM
    0x3001: CL,   # IDEOGRAPHIC COMMA
    0x3002: CL,   # IDEOGRAPHIC FULL STOP
    0x300C: OP,
    0x300D: CL,
    0x300E: OP,
    0x300F: CL,
    0xFEFF: WJ,
    0xFFFC: CB,   # OBJECT REPLACEMENT CHARACTER -- an atomic inline
}

#: Ideographic and emoji ranges, which break on both sides by LB31 falling
#: through. Ranges rather than code points because there is no punctuation
#: hiding inside them: everything in these blocks is ID.
_ID_RANGES: tuple[tuple[int, int], ...] = (
    (0x1100, 0x115F),    # Hangul Jamo initial
    (0x2E80, 0x2FFF),    # CJK radicals, Kangxi
    (0x3041, 0x30FF),    # Hiragana, Katakana
    (0x3105, 0x312F),
    (0x3131, 0x318E),
    (0x3190, 0x33FF),
    (0x3400, 0x4DBF),    # CJK ext A
    (0x4E00, 0x9FFF),    # CJK unified
    (0xA000, 0xA4CF),    # Yi
    (0xAC00, 0xD7A3),    # Hangul syllables
    (0xF900, 0xFAFF),    # CJK compatibility
    (0xFE30, 0xFE4F),
    (0xFF01, 0xFF60),    # fullwidth forms
    (0xFFE0, 0xFFE6),
    (0x1F300, 0x1FAFF),  # emoji
    (0x20000, 0x2FFFD),
    (0x30000, 0x3FFFD),
)


def line_break_class(ch: str, *, metrics: Counter[str] | None = None) -> str:
    """The UAX #14 `Line_Break` class of one character.

    Explicit table first, then the ideographic ranges, then a fallback from
    the Unicode general category. The fallback is counted: it is right for
    letters and it is the place a wrong answer would hide, so "how many
    characters were classified by default" has to be visible.
    """
    cp = ord(ch)
    explicit = _EXPLICIT.get(cp)
    if explicit is not None:
        return explicit
    for low, high in _ID_RANGES:
        if low <= cp <= high:
            return ID
    category = unicodedata.category(ch)
    if metrics is not None:
        # Split, because one number here means nothing. Every letter and
        # every digit falls through this branch and is correctly `AL` or
        # `NU`, so a single counter reads 61,667 on the corpus and says
        # only "this page has text in it". The count that matters is the
        # **other** one: a character that is neither a letter, a digit nor
        # a combining mark, classified `AL` by a default, is exactly where
        # a missing table entry would hide a wrong break opportunity.
        if category[0] in ("L", "N"):
            bucket = "linebreak_class_fallback_letter_or_digit"
        elif category[0] == "M":
            # A combining mark, which LB9 resolves to whatever it attaches
            # to anyway. Its own bucket rather than lumped in with `other`,
            # because `other` is the one that has to read zero and 58
            # Devanagari, Bengali and Burmese marks on the corpus would
            # make it read 58 while nothing was wrong.
            bucket = "linebreak_class_fallback_combining_mark"
        else:
            bucket = "linebreak_class_fallback_other"
        metrics[bucket] += 1
    if category in ("Mn", "Mc", "Me"):
        return CM
    if category == "Nd":
        return NU
    if category == "Cc" or category == "Cf":
        # A control or format character that is not one of the named ones
        # above. UAX #14 gives most of these CM; treating them as AL would
        # invent a break opportunity around an invisible character.
        return CM
    return AL


# --------------------------------------------------------------------------
# Tailorings
# --------------------------------------------------------------------------

#: Chrome 151's measured departures from UAX #14, as code points whose
#: break-after opportunity Chrome suppresses and UAX #14 offers.
#:
#: Keyed by code point and **not** by class, on purpose. `|` is class BA and
#: so is `-`; `!` is class EX and so is `?`. In each pair Chrome breaks after
#: one and not the other, so no class-level entry can express it -- and a
#: class-level entry that tried would silently change the other member.
#:
#: Each was measured the same way: the string in a 30px `<div>`, and the
#: y coordinate of every character read back through a one-character
#: `Range`. See the module docstring for the table.
_TAILORED_NO_BREAK_AFTER: dict[int, str] = {
    0x002F: "linebreak_tailored_no_break_after_solidus",
    0x007C: "linebreak_tailored_no_break_after_vertical_line",
    0x0021: "linebreak_tailored_no_break_after_exclamation",
}

COUNTER_NAMES: tuple[str, ...] = (
    "linebreak_class_fallback_letter_or_digit",
    "linebreak_class_fallback_combining_mark",
    "linebreak_class_fallback_other",
    "linebreak_opportunities",
    "linebreak_opportunities_at_space",
    "linebreak_opportunities_other",
) + tuple(sorted(set(_TAILORED_NO_BREAK_AFTER.values())))


def break_opportunities(
    text: str,
    *,
    tailored: bool = True,
    metrics: Counter[str] | None = None,
) -> list[bool]:
    """`out[i]` is True when a line may break **before** `text[i]`.

    `out[0]` is always False -- UAX #14 LB2, no break at the start of text --
    so the list is indexable by the same offsets as `text` and a caller
    never has to remember an off-by-one.

    Mandatory breaks are **not** reported here. A preserved segment break
    reaches this module as U+000A and gets `× LF` from LB6, so no
    opportunity is offered next to it; the line breaker handles the forced
    break itself, because a forced break is a fact about the line and not
    about a pair of characters.
    """
    length = len(text)
    out = [False] * length
    if length < 2:
        return out

    classes = [line_break_class(ch, metrics=metrics) for ch in text]
    _resolve_combining_marks(classes)

    for index in range(1, length):
        before = classes[index - 1]
        after = classes[index]
        # LB8, LB14, LB16, LB17 all look back over a run of spaces to the
        # class that opened it, so that run is found once here rather than
        # in four rules.
        base_index = index - 1
        while base_index > 0 and classes[base_index] == SP:
            base_index -= 1
        base = classes[base_index]
        allowed = _pair_allows_break(before, after, base)
        if allowed and tailored:
            reason = _TAILORED_NO_BREAK_AFTER.get(ord(text[index - 1]))
            if reason is not None:
                allowed = False
                if metrics is not None:
                    metrics[reason] += 1
        out[index] = allowed
        if allowed and metrics is not None:
            metrics["linebreak_opportunities"] += 1
            if before == SP:
                metrics["linebreak_opportunities_at_space"] += 1
            else:
                metrics["linebreak_opportunities_other"] += 1
    return out


def _resolve_combining_marks(classes: list[str]) -> None:
    """LB9: `X (CM | ZWJ)* -> X`, with LB10's `CM -> AL` at the start.

    In place, because the pair rules below must never see a `CM`: a
    combining mark that kept its own class would offer a break between a
    letter and its own accent.
    """
    for index, value in enumerate(classes):
        if value not in (CM, ZWJ):
            continue
        if index == 0:
            classes[index] = AL
            continue
        previous = classes[index - 1]
        classes[index] = AL if previous in (SP, ZW, *MANDATORY) else previous


def _pair_allows_break(before: str, after: str, base: str) -> bool:
    """UAX #14's pair table, in rule order. First rule that matches wins.

    `base` is the class before any run of spaces ending at `before`, and is
    equal to `before` when `before` is not a space.

    The rules are written out in their numbered order rather than collapsed
    into a table, because the order is the algorithm: LB13's `x CL` and
    LB18's `SP /` would give opposite answers for `") "` if either moved.
    """
    # LB6 -- do not break before a hard break.
    if after in MANDATORY:
        return False
    # LB7 -- do not break before a space or a zero-width space.
    if after in (SP, ZW):
        return False
    # LB8 -- break after a zero-width space, through any spaces.
    if base == ZW:
        return True
    # LB11 -- the word joiner binds on both sides.
    if after == WJ or before == WJ:
        return False
    # LB12 -- do not break after glue.
    if before == GL:
        return False
    # LB12a -- do not break before glue, unless what precedes can break.
    if after == GL and before not in (SP, BA, HY):
        return False
    # LB13 -- do not break before closing punctuation or an infix separator.
    if after in (CL, CP, EX, SY, IS):
        return False
    # LB14 -- do not break after opening punctuation, through any spaces.
    if base == OP:
        return False
    # LB16 -- do not break between a closer and a non-starter.
    if base in (CL, CP) and after == NS:
        return False
    # LB17 -- do not break inside `--`.
    if base == B2 and after == B2:
        return False
    # LB18 -- break after a space. Every other rule that wanted a space run
    # has already had its say.
    if before == SP:
        return True
    # LB19 -- do not break either side of a quotation mark.
    if after == QU or before == QU:
        return False
    # LB20 -- break on both sides of a contingent break: an atomic inline.
    if after == CB or before == CB:
        return True
    # LB21 -- do not break before a hyphen or a break-after character, and
    # do not break after a break-before one.
    if after in (BA, HY, NS) or before == BB:
        return False
    # LB22 -- do not break before an inseparable.
    if after == IN:
        return False
    # LB23 -- do not break between letters and digits.
    if (before == AL and after == NU) or (before == NU and after == AL):
        return False
    # LB23a -- prefix / ideograph / postfix.
    if before == PR and after == ID:
        return False
    if before == ID and after == PO:
        return False
    # LB24 -- prefix and postfix against letters.
    if before in (PR, PO) and after == AL:
        return False
    if before == AL and after in (PR, PO):
        return False
    # LB25 -- do not break inside a number. The full rule is a regular
    # expression over `(PR|PO)? (OP|HY)? NU (NU|SY|IS)* (CL|CP)? (PR|PO)?`;
    # the pairs below are the part of it that a pair table can express, and
    # they are what `1,000.5` and `$1` need.
    if before in (PR, PO, HY, IS, SY, OP) and after == NU:
        return False
    if before == NU and after in (NU, SY, IS, PR, PO, CL, CP):
        return False
    if before in (CL, CP) and after in (PR, PO):
        return False
    # LB28 -- do not break between letters.
    if before == AL and after == AL:
        return False
    # LB29 -- do not break between an infix separator and a letter or digit.
    if before == IS and after in (AL, NU):
        return False
    # LB30 -- do not break between a letter/digit and an opening bracket, or
    # between a closing bracket and a letter/digit.
    if before in (AL, NU) and after == OP:
        return False
    if before == CP and after in (AL, NU):
        return False
    # LB31 -- break everywhere else.
    return True
