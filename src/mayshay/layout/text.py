"""Text measurement and white-space processing -- Phase 3 Task D1.

Two things live here and they are deliberately in one module: the **single
font seam**, and CSS Text 3's **Phase I white-space transformation**. Every
width this engine will ever produce for text passes through `measure()`,
and every character that reaches `measure()` has been through `collapse()`
first.

## The font seam

`measure(text, style) -> float` reads glyph advances from the vendored
font's `hmtx` table through `fontTools` and multiplies by the font size.
Not `PIL.ImageFont.getlength`, which returns integer-rounded advances --
`"Hello world"` comes back as `89.0` where `hmtx` gives `89.6953`, and
neither `layout_engine=BASIC` nor `mode="L"` changes it, so Pillow's own
diagnostics read as confirmation. See `docs/measurement-hazards.md`
instance 2 and `docs/fonts.md` for the derivation of every number below.

`docs/fonts.md` says three call sites would be three places for one metric
decision to drift, so there is one function. `hmtx` only: no `GPOS`, no
`GSUB`, and the legacy `kern` table is not consulted -- a **measured**
+0.137% systematic width error over the corpus, concentrated in capital
pairs (`To` is +9.50%) rather than spread evenly.

`fontTools` is permitted in `layout/` for exactly this, per CLAUDE.md, and
it makes no layout decision: it is asked for an integer per glyph.

## What counts as white space

CSS Text 3 is narrower than Python is, and the difference is the reason
this module owns the predicate rather than leaving it to `str.strip()`:

    space  U+0020   tab  U+0009   line feed  U+000A   carriage return  U+000D

and nothing else. `str.isspace()` is true for U+00A0 NO-BREAK SPACE,
U+000B, U+000C, U+2000-U+200A and U+3000, none of which CSS Text 3 treats
as white space -- section 4.1.1 says so in as many words ("Control
characters (Unicode class Cc) other than tab, line feed and carriage
return are not white space"). NBSP is the one that matters in practice: it
does **not** collapse, it has a real advance, it is not a soft wrap
opportunity, and it is indistinguishable from a space in a terminal. 36
text boxes on the corpus contain nothing but NBSP; under `str.strip()` all
36 are "blank".

## Phase I only

CSS Text 3 splits white-space processing in two. **Phase I** -- collapsing
and transformation -- depends only on the content of the inline formatting
context and is done here. **Phase II** -- trimming at each line's start and
end, hanging, and where the breaks actually fall -- depends on line boxes
and belongs to Task D2.

Two parts of Phase II are done here anyway because they are line-box
*independent*: the beginning of the first line of an IFC is the beginning
of the IFC, and the end of the last line is the end of the IFC, whatever
D2 decides about everything in between. They are counted under their own
names (`text_whitespace_trimmed_ifc_start` / `_ifc_end`) so D2 can see
exactly what was already done and what is left.

One deliberate simplification, stated because it is invisible: a collapsed
space is **removed** here, where the spec collapses it "to zero advance
width, retaining its soft wrap opportunity". With no line breaking in D1
the two are indistinguishable; when D2 arrives it needs the wrap
opportunity, which is derivable from the surviving space. Removing it
would be wrong only if two collapsible spaces could be separated by a
break opportunity that is not itself a space, and they cannot.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from mayshay.cssparse.cascade import ComputedStyle
from mayshay.cssparse.values import WHITE_SPACE_KEYWORDS

# --------------------------------------------------------------------------
# The font
# --------------------------------------------------------------------------

FONT_PATH = (
    Path(__file__).resolve().parents[3]
    / "data"
    / "fonts"
    / "LiberationSans-Regular.ttf"
)

# Liberation Sans 2.1.5, SHA-256 in docs/fonts.md. Recorded here so a
# swapped font file is a loud failure at import rather than a quiet 0.14%
# drift in every width on every page.
FONT_SHA256 = "76d04c18ea243f426b7de1f3ad208e927008f961dc5945e5aad352d0dfde8ee8"

# CSS Text 3 section 6.2: the initial `tab-size`, in space advances.
# `tab-size` is not parsed by `cssparse`, so this is the only value.
TAB_SIZE = 8


@dataclass(frozen=True)
class FontMetrics:
    """Everything read out of the font file, once.

    Advances are held in **font units** rather than pixels. A width is
    `units * font_size / units_per_em`: one integer sum and one multiply,
    exact and linear in font size, with no per-glyph float error to
    accumulate.
    """

    units_per_em: int
    advances: dict[int, int]
    notdef: int
    ascent: int
    descent: int
    line_gap: int
    x_height: int

    def advance(self, codepoint: int) -> tuple[int, bool]:
        """`(units, was_missing)` for one character."""
        units = self.advances.get(codepoint)
        if units is None:
            return self.notdef, True
        return units, False


_METRICS: FontMetrics | None = None


def font_metrics() -> FontMetrics:
    """The vendored font's metrics, loaded once.

    Lazy on purpose. `boxtree` imports this module for the white-space
    predicate and never measures anything, and pulling `fontTools` in at
    import time would put a binary-format reader behind every box-tree test.
    """
    global _METRICS
    if _METRICS is None:
        from fontTools.ttLib import TTFont  # noqa: PLC0415 -- lazy, see above

        font = TTFont(str(FONT_PATH), lazy=True)
        hmtx = font["hmtx"]
        cmap = font.getBestCmap()
        _METRICS = FontMetrics(
            units_per_em=font["head"].unitsPerEm,
            advances={cp: hmtx[glyph][0] for cp, glyph in cmap.items()},
            notdef=hmtx[".notdef"][0],
            ascent=font["hhea"].ascent,
            descent=font["hhea"].descent,
            line_gap=font["hhea"].lineGap,
            x_height=font["OS/2"].sxHeight,
        )
        font.close()
    return _METRICS


def advance_units(text: str, *, metrics: Counter[str] | None = None) -> int:
    """The advance of `text` in font units.

    Integers throughout, so `measure` is one multiply at the end and two
    strings of the same glyphs cannot disagree in the last bit.
    """
    font = font_metrics()
    total = 0
    for ch in text:
        if ch == LF:
            # A preserved segment break ends a line; it has no advance.
            continue
        if ch == TAB:
            # A preserved tab. CSS Text 3 section 6.2 puts the next
            # character at the next tab stop, which is a *position* and
            # therefore needs a line box -- Task D2's. Measured here as a
            # full tab stop's worth of advance, which is right only when
            # the tab starts on a stop. Counted, not silently approximated;
            # zero occurrences on the corpus, because `white-space: pre` is
            # zero on the corpus.
            if metrics is not None:
                metrics["text_preserved_tab_approximated"] += 1
            space, _ = font.advance(0x0020)
            total += TAB_SIZE * space
            continue
        units, missing = font.advance(ord(ch))
        if missing and metrics is not None:
            metrics["text_missing_glyph"] += 1
        total += units
    return total


def measure(
    text: str, style: ComputedStyle, *, metrics: Counter[str] | None = None
) -> float:
    """The advance width of `text` in CSS pixels, at `style`'s font size.

    The single font seam. `style` is read for `font-size` and for nothing
    else: this project ships one face, so `font-weight: bold` changes no
    advance and `font-family` selects nothing -- both are recorded in
    `docs/fonts.md` as known divergences from Chrome rather than handled.

    `text` is expected to have been through `collapse()` already. Passing
    raw source text is not an error and is not detectable here, which is
    why the IFC pass in this module is the only caller in the engine.
    """
    return advance_units(text, metrics=metrics) * style.font_size_px / (
        font_metrics().units_per_em
    )


# --------------------------------------------------------------------------
# CSS Text 3 white space
# --------------------------------------------------------------------------

SPACE = "\u0020"
TAB = "\u0009"
LF = "\u000a"
CR = "\u000d"

#: The four characters CSS Text 3 calls white space. Deliberately not
#: `str.isspace()` -- see the module docstring.
WHITE_SPACE_CHARS = frozenset({SPACE, TAB, LF, CR})

#: The two that are segment breaks rather than spaces.
SEGMENT_BREAK_CHARS = frozenset({LF, CR})


def is_white_space(ch: str) -> bool:
    return ch in WHITE_SPACE_CHARS


def is_white_space_only(text: str) -> bool:
    """True for a run that is entirely CSS white space.

    `""` is white-space-only vacuously, which matches how the box tree uses
    it: an empty text node contributes nothing either way.
    """
    return all(ch in WHITE_SPACE_CHARS for ch in text)


@dataclass(frozen=True)
class WhiteSpaceBehaviour:
    """One row of CSS Text 3 section 3's table, as three independent bits.

    The table is worth reproducing because the six values are *not* ordered
    by strength -- `pre-line` preserves breaks while collapsing spaces, and
    `nowrap` collapses everything while refusing to wrap:

        value          new lines   spaces/tabs   wrapping
        normal         collapse    collapse      wrap
        pre            preserve    preserve      no wrap
        nowrap         collapse    collapse      no wrap
        pre-wrap       preserve    preserve      wrap
        pre-line       preserve    collapse      wrap
        break-spaces   preserve    preserve      wrap

    `pre-wrap` and `break-spaces` differ only in Phase II -- whether a
    trailing space hangs past the line's end or takes a break opportunity
    of its own -- so they are identical here, and D2 is where they separate.
    That is recorded rather than merged: giving them one entry would make
    the difference impossible to see when D2 comes to add it.
    """

    collapse_segment_breaks: bool
    collapse_spaces: bool
    wraps: bool


WHITE_SPACE_BEHAVIOUR: dict[str, WhiteSpaceBehaviour] = {
    "normal": WhiteSpaceBehaviour(True, True, True),
    "pre": WhiteSpaceBehaviour(False, False, False),
    "nowrap": WhiteSpaceBehaviour(True, True, False),
    "pre-wrap": WhiteSpaceBehaviour(False, False, True),
    "pre-line": WhiteSpaceBehaviour(False, True, True),
    "break-spaces": WhiteSpaceBehaviour(False, False, True),
}

# MECHANICAL CHECK, in the shape of `cascade`'s LONGHANDS/ComputedStyle
# drift assert. A seventh `white-space` value added to the parser and
# forgotten here would otherwise reach `WHITE_SPACE_BEHAVIOUR[...]` as a
# KeyError on whichever page first used it -- or, worse, be given a
# `.get(..., normal)` default and silently collapse text the author asked
# to preserve. Import time, every run, no test needed.
assert set(WHITE_SPACE_BEHAVIOUR) == set(WHITE_SPACE_KEYWORDS), (
    "layout.text and cssparse.values disagree about the `white-space` "
    f"values: {set(WHITE_SPACE_BEHAVIOUR) ^ set(WHITE_SPACE_KEYWORDS)}"
)


def behaviour_of(white_space: str) -> WhiteSpaceBehaviour:
    return WHITE_SPACE_BEHAVIOUR[white_space]


# --------------------------------------------------------------------------
# Phase I: collapsing and transformation
# --------------------------------------------------------------------------

_CONTENT = "content"
_COLLAPSIBLE = "collapsible"
_FORCED_BREAK = "forced_break"


@dataclass
class CollapsedRun:
    """What Phase I did to one text box.

    `kept + transformed + removed == len(source)` and
    `len(text) == kept + transformed`, both asserted on every run. That is
    the character-conservation check: a rule that drops a character it
    meant to rewrite, or rewrites one it meant to drop, fails here rather
    than showing up as text that is quietly a few pixels narrow.
    """

    source: str
    text: str
    kept: int = 0
    transformed: int = 0
    removed: int = 0
    disposition: str = ""

    def check(self) -> None:
        total = self.kept + self.transformed + self.removed
        assert total == len(self.source), (
            "white-space collapsing lost track of characters: "
            f"kept {self.kept} + transformed {self.transformed} + removed "
            f"{self.removed} = {total}, input was {len(self.source)} "
            f"({self.source!r})"
        )
        assert len(self.text) == self.kept + self.transformed, (
            "white-space collapsing produced the wrong number of output "
            f"characters: {len(self.text)} != kept {self.kept} + transformed "
            f"{self.transformed} ({self.source!r} -> {self.text!r})"
        )


@dataclass
class _Record:
    run: int
    char: str
    kind: str


@dataclass
class _RunState:
    source: str
    behaviour: WhiteSpaceBehaviour
    out: list[str] = field(default_factory=list)
    kept: int = 0
    transformed: int = 0
    removed: int = 0


#: Every way a whitespace-only text box can end up. Seeded and partitioned
#: rather than counted ad hoc: `WHITESPACE_DISPOSITIONS` is what the
#: partition assert iterates, so adding an outcome and forgetting to count
#: it is a failing assert and not a missing row.
WHITESPACE_DISPOSITIONS: tuple[str, ...] = (
    "collapsed_away",
    "single_space",
    "preserved_verbatim",
    "preserved_break",
    "other",
)


def collapse_ifc(
    runs: list[tuple[str, str]], metrics: Counter[str]
) -> list[CollapsedRun]:
    """Phase I over one inline formatting context.

    `runs` is `(source_text, white_space_value)` in document order -- the
    whole IFC at once, not box by box, because CSS Text 3's collapsing rule
    is explicit that a collapsible space collapses into the previous one
    "even one outside the boundary of the inline containing that space,
    provided both spaces are within the same inline formatting context".
    `<span>a </span> <span>b</span>` has one space between the words, not
    two, and no per-box function can know that.
    """
    records: list[_Record] = []
    states: list[_RunState] = []
    for index, (source, white_space) in enumerate(runs):
        behaviour = behaviour_of(white_space)
        states.append(_RunState(source=source, behaviour=behaviour))
        skip_next_lf = False
        for position, ch in enumerate(source):
            if skip_next_lf:
                skip_next_lf = False
                if ch == LF:
                    # The LF half of a CRLF pair: the CR already stands for
                    # the segment break, so this one produces nothing.
                    records.append(_Record(index, ch, _COLLAPSIBLE))
                    continue
            if ch == CR:
                metrics["text_carriage_returns_normalised"] += 1
                skip_next_lf = source[position + 1 : position + 2] == LF
            records.append(_Record(index, ch, _kind_of(ch, behaviour)))

    _resolve(records, states, metrics)

    out: list[CollapsedRun] = []
    for state in states:
        run = CollapsedRun(
            source=state.source,
            text="".join(state.out),
            kept=state.kept,
            transformed=state.transformed,
            removed=state.removed,
        )
        run.check()
        out.append(run)
    return out


def _kind_of(ch: str, behaviour: WhiteSpaceBehaviour) -> str:
    if ch in SEGMENT_BREAK_CHARS:
        return _COLLAPSIBLE if behaviour.collapse_segment_breaks else _FORCED_BREAK
    if ch in (SPACE, TAB):
        return _COLLAPSIBLE if behaviour.collapse_spaces else _CONTENT
    return _CONTENT


def _resolve(
    records: list[_Record], states: list[_RunState], metrics: Counter[str]
) -> None:
    """Decide each character's fate, then write the output runs.

    Done as a second pass over the whole IFC because three of the four
    rules need to see what is on the *other* side of a collapsible run:
    whether it is at the start of the context, at its end, or up against a
    preserved segment break.
    """
    index = 0
    total = len(records)
    while index < total:
        record = records[index]
        if record.kind != _COLLAPSIBLE:
            _emit(states, record, kept=True)
            index += 1
            continue

        end = index
        while end < total and records[end].kind == _COLLAPSIBLE:
            end += 1
        run = records[index:end]
        before = records[index - 1] if index > 0 else None
        after = records[end] if end < total else None

        if before is None:
            # Phase II's "spaces at the start of a line are removed", but
            # for the first line only, where it needs no line box.
            reason = "text_whitespace_trimmed_ifc_start"
        elif after is None:
            reason = "text_whitespace_trimmed_ifc_end"
        elif before.kind == _FORCED_BREAK or after.kind == _FORCED_BREAK:
            # CSS Text 3 section 4.1.1 step 1: collapsible spaces
            # immediately preceding or following a segment break are
            # removed. Reachable only under `pre-line`, the one value that
            # preserves breaks while collapsing spaces.
            reason = "text_whitespace_removed_around_segment_break"
        else:
            reason = ""

        if reason:
            metrics[reason] += len(run)
            for dropped in run:
                _emit(states, dropped, kept=False)
        else:
            # One space survives the run. Step 2 transforms the segment
            # break into it where there is one, so the surviving character
            # is the first break rather than the first space -- which is
            # only observable in which box the space is attributed to when
            # the run straddles a boundary, and is free to get right.
            survivor = next(
                (r for r in run if r.char in SEGMENT_BREAK_CHARS), run[0]
            )
            for member in run:
                if member is survivor:
                    _emit(states, member, kept=True, replacement=SPACE)
                else:
                    _emit(states, member, kept=False)
                    metrics["text_whitespace_collapsed_into_previous"] += 1
        index = end


def _emit(
    states: list[_RunState],
    record: _Record,
    *,
    kept: bool,
    replacement: str | None = None,
) -> None:
    state = states[record.run]
    if not kept:
        state.removed += 1
        return
    char = record.char if replacement is None else replacement
    if record.char == CR and replacement is None:
        # A preserved lone carriage return is a segment break; the engine
        # writes every preserved break as LF so that everything downstream
        # has one break character to look for.
        char = LF
    state.out.append(char)
    if char == record.char:
        state.kept += 1
    else:
        state.transformed += 1


def collapse(
    text: str, white_space: str, metrics: Counter[str] | None = None
) -> CollapsedRun:
    """Phase I over a single text run treated as a whole IFC.

    A convenience for tests and for a one-text-node context. Real pages go
    through `collapse_ifc`, because a run that is alone in its context gets
    both its leading and its trailing white space trimmed and one that is
    not usually does not -- so this is **not** a per-box building block that
    `collapse_ifc` could be written in terms of.
    """
    return collapse_ifc(
        [(text, white_space)], metrics if metrics is not None else Counter()
    )[0]


def disposition_of(run: CollapsedRun, white_space: str) -> str:
    """Which of `WHITESPACE_DISPOSITIONS` a white-space-only run ended in.

    Order matters and the first test is the one that is easy to get wrong.
    Under `pre` a single space is **preserved**, not "collapsed to a
    separating space", and the two produce byte-identical output -- so the
    behaviour has to be consulted before the text is.

    `other` is the residual bucket, in the shape of Task C's
    `widths_deferred_other`: it should always read zero, and the partition
    assert is what says so rather than anybody checking.
    """
    behaviour = behaviour_of(white_space)
    if not behaviour.collapse_spaces:
        return "preserved_verbatim"
    if run.text == "":
        return "collapsed_away"
    if run.text == SPACE:
        return "single_space"
    if run.text and set(run.text) <= {LF}:
        return "preserved_break"
    return "other"


# --------------------------------------------------------------------------
# Soft wrap opportunities -- what intrinsic sizing breaks on
# --------------------------------------------------------------------------

RUN = "run"
BREAK_SPACE = "space"
FORCED_BREAK = "break"


def tokenize(text: str, white_space: str) -> list[tuple[str, str]]:
    """Split collapsed text into `(kind, piece)` for intrinsic sizing.

    Three kinds and each is treated differently by the two intrinsic sizes:

    * `run` -- unbreakable content. Counts toward both.
    * `space` -- a soft wrap opportunity. Counts toward max-content, where
      no break is taken, and not toward min-content, where every break is.
    * `break` -- a preserved segment break. Forced, so it ends the line for
      *both* sizes.

    Under `nowrap` and `pre` there are no `space` tokens at all: the spaces
    are inside the runs, because there is nothing to break at. That is the
    whole difference between a `nowrap` box's min-content width and a
    `normal` one's, and it is why this cannot be a plain `str.split()`.

    U+00A0 is never a `space` token under any value.
    """
    behaviour = behaviour_of(white_space)
    breakable = (SPACE, TAB) if behaviour.wraps else ()
    tokens: list[tuple[str, str]] = []
    buffer: list[str] = []

    def flush() -> None:
        if buffer:
            tokens.append((RUN, "".join(buffer)))
            buffer.clear()

    index = 0
    while index < len(text):
        ch = text[index]
        if ch == LF:
            flush()
            tokens.append((FORCED_BREAK, ch))
            index += 1
        elif ch in breakable:
            end = index
            while end < len(text) and text[end] in breakable:
                end += 1
            flush()
            tokens.append((BREAK_SPACE, text[index:end]))
            index = end
        else:
            buffer.append(ch)
            index += 1
    flush()
    return tokens
