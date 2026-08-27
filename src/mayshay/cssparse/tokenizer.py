"""
Mayshay CSS tokenizer.

A hand-rolled implementation of the CSS Syntax Level 3 tokenizer:
https://www.w3.org/TR/css-syntax-3/#tokenization

Structurally this is easier than the HTML tokenizer -- there is no parser
feedback loop, so no state field and no `switch_to` seam -- but the algorithm
shape is the same one the spec names, and the two escape/url paths carry the
difficulty that entity decoding and raw text carry on the HTML side. The token
dataclasses, the `pos` on every token, the `errors` list and the `metrics`
Counter all mirror `htmlparse/tokenizer.py` on purpose.

Implemented, all of section 4.3: consume a token (4.3.1), consume comments
(4.3.2), consume a numeric token (4.3.3), consume an ident-like token (4.3.4),
consume a string token (4.3.5), consume a url token (4.3.6), consume an escaped
code point (4.3.7), check if two code points are a valid escape (4.3.8), check
if three code points would start an ident sequence (4.3.9), check if three code
points would start a number (4.3.10), consume an ident sequence (4.3.11),
consume a number (4.3.12), convert a string to a number (4.3.13), consume the
remnants of a bad url (4.3.14). Plus section 3.3 input preprocessing.

Deliberate deviations from the spec, documented so they don't surprise us later:

1. `<unicode-range-token>` does not exist -- correctly, since css-syntax-3
   removed it: `U+0025-00FF` tokenizes as Ident("U"), Delim("+"), ... and the
   *parser* is expected to reassemble it via the <urange> production. Nothing
   in the nine-property set needs urange, so no reassembly is planned; if
   @font-face ever lands, this is where to look.
2. **Ident code points are classified by code point range, not by the spec's
   exact "non-ASCII ident code point" list.** The spec enumerates specific
   ranges (U+00B7, U+200C, U+203F, ...) and excludes others below U+0080;
   we treat *every* code point >= U+0080 as an ident code point, which is
   what css-syntax-3 itself said until 2021 and what every shipping engine
   still does. Consequence: `a b` is one ident here, three tokens per the
   current spec text. No corpus case distinguishes them.
3. **`convert a string to a number` (4.3.13) is delegated to Python's `float`
   and `int`.** The spec writes out the sign/integer/fraction/exponent
   arithmetic explicitly; `float()` computes the same value for every string
   `_consume_number` can build, because `_consume_number` only ever builds
   strings that match the spec's number grammar, which is a strict subset of
   Python's float literal grammar (no "inf", "nan", "1_0" or leading "0x").
   This is the one place a hand-rolled implementation would be pure ceremony.
4. **Integer values are stored as `int`, non-integers as `float`.** The spec
   keeps a numeric value plus a type flag; we keep both, but also narrow the
   Python type, so `Number(3).value` is `3` and not `3.0`. The type flag
   (`is_integer`) remains authoritative: `1e3` has an integral value but its
   flag is False, because the spec's flag records *how it was written*, which
   is what `<integer>` parsing needs. The consumer is **task H**
   (`matching.py`, five sites, all in the `An+B` parser), not task I: none of
   the nine properties `values.py` handles has an `<integer>` grammar, and
   `values.py` reads the flag nowhere. An earlier draft of this deviation
   said task I; grepped, and it is task H.
5. **The EOF token class is `EOFToken`, not `EOF`.** `EOF` is the end-of-input
   sentinel (`None`), exactly as in `htmlparse/tokenizer.py`, and the two
   cannot share a name -- `_consume_escape`'s `ch is EOF` test needs the
   sentinel. The task brief's interface list named the token `EOF`; the brief's
   own code in the same file needs `EOF` to be the sentinel.
6. **`metrics["tokenize_time_ms"]` measures time spent inside the tokenizer,
   not wall time across the stream.** `tokenize()` returns a generator (it is
   a plain method wrapping the `_tokenize()` generator -- see its docstring
   for why the two are split), so wall time from the call to EOF would
   include however long the consumer took between `next()` calls. The cost
   is two `perf_counter()` calls per token (~5% on a token-dense
   stylesheet); the alternative is a timing metric that silently measures
   the tree builder.
7. **`*=`, `~=`, `|=`, `^=`, `$=` and `||` are NOT single tokens.** The 2014
   CR of css-syntax-3 had <substring-match-token> and friends; the current
   spec removed them, leaving the match operators to be reassembled by the
   selector parser from two delims. Worth knowing because it is one of
   exactly TWO places a spec-correct implementation disagrees with tinycss2,
   which still implements the 2014 CR, over the 21KB of real <style> bodies
   in data/corpus/: this one, the only *structural* divergence, and
   deviation 4's int-vs-float, which is a representation difference at the
   same token boundaries. Task G's selector parser has to join them.
8. **NULL and lone surrogates are replaced with U+FFFD during preprocessing**
   (spec 3.3), unlike `htmlparse`, which deliberately passes NUL through
   untouched (see deviation 5 there). CSS has no conformance corpus pinning
   the alternative, and the spec's own algorithms below assume the
   replacement has already happened.
"""

from __future__ import annotations

import time
from collections import Counter
from dataclasses import dataclass
from typing import Iterator

# Whitespace and hex digits are frozensets, not strings, and that is
# load-bearing: `_peek(1)` returns "" at end of input, and `"" in "\n\t "` is
# True for a string but False for a set. Every `... in WHITESPACE` test below
# would silently succeed at EOF if these were strings.
WHITESPACE = frozenset("\n\t ")
HEX_DIGITS = frozenset("0123456789abcdefABCDEF")
DIGITS = frozenset("0123456789")

EOF = None  # sentinel for end of input, as in htmlparse.tokenizer

REPLACEMENT = "�"

# The maximum code point; escapes above it are replaced (spec 4.3.7).
MAX_CODE_POINT = 0x10FFFF


def _is_ident_start(ch: str | None) -> bool:
    """Spec: letter, non-ASCII ident code point, or U+005F LOW LINE.

    `ch.isalpha()` alone would accept 'é' *and* 'µ' but reject '·'; we want
    the range test for everything >= U+0080 regardless -- see deviation 2.
    """
    if ch is None:
        return False
    return (
        ("a" <= ch <= "z")
        or ("A" <= ch <= "Z")
        or ch == "_"
        or ord(ch) >= 0x80
    )


def _is_ident(ch: str | None) -> bool:
    """Spec: ident-start code point, digit, or U+002D HYPHEN-MINUS."""
    return _is_ident_start(ch) or (ch is not None and (ch in DIGITS or ch == "-"))


def _ascii_lower(text: str) -> str:
    """ASCII-lowercase only, as the spec's "ASCII case-insensitive" means.

    `str.lower()` would also fold non-ASCII code points, and at least one of
    them folds *into* the ASCII range: U+1E9E LATIN CAPITAL SHARP S lowers to
    "ß", U+212A KELVIN SIGN to "k". Nothing folds to "url" today, but the
    `url(` special case is exactly the wrong place to rely on that.
    """
    return "".join(
        chr(ord(ch) + 0x20) if "A" <= ch <= "Z" else ch for ch in text
    )


def _is_non_printable(ch: str) -> bool:
    """Spec 4.2. Only ever consulted inside a url token."""
    point = ord(ch)
    return (
        point <= 0x08
        or point == 0x0B
        or 0x0E <= point <= 0x1F
        or point == 0x7F
    )


# --------------------------------------------------------------------------
# Tokens
# --------------------------------------------------------------------------
#
# One dataclass per spec token type. Every token carries `pos`, the offset of
# its first character in the *preprocessed* source -- preprocessing only ever
# collapses CRLF to LF, so an offset differs from the raw source only after a
# CRLF, and CSS embedded in HTML has already been through the HTML tokenizer's
# identical normalisation by the time it reaches here.


@dataclass
class Ident:
    value: str
    pos: int = -1


@dataclass
class Function:
    """`rgb(` -- the name and the opening paren, as one token."""
    value: str
    pos: int = -1


@dataclass
class AtKeyword:
    value: str          # without the '@'
    pos: int = -1


@dataclass
class Hash:
    value: str          # without the '#'
    # The spec's type flag. True when the value is a valid ident sequence, so
    # `#main` is an id selector and `#f0f` is not. Selector matching (task H)
    # needs this to reject `#0f0` as a selector without re-lexing the value.
    is_id: bool = False
    pos: int = -1


@dataclass
class String:
    value: str          # without the quotes, escapes decoded
    pos: int = -1


@dataclass
class BadString:
    """An unterminated string interrupted by a newline (spec 4.3.5).

    Carries no value: the spec's <bad-string-token> has none, and a parser
    that treats it as a string with partial content is exactly the bug the
    token exists to prevent.
    """
    pos: int = -1


@dataclass
class Url:
    """Only ever produced for UNQUOTED url(...) -- see `_consume_url`."""
    value: str
    pos: int = -1


@dataclass
class BadUrl:
    pos: int = -1


@dataclass
class Number:
    value: int | float
    # False when written with a decimal point or an exponent, per spec 4.3.12.
    # `1e3` has an integral value but is_integer is False.
    is_integer: bool = True
    pos: int = -1


@dataclass
class Percentage:
    value: int | float
    is_integer: bool = True
    pos: int = -1


@dataclass
class Dimension:
    value: int | float
    unit: str
    is_integer: bool = True
    pos: int = -1


@dataclass
class Whitespace:
    # The spec's <whitespace-token> carries nothing. We keep the run so the
    # stream can be serialized back to the source text, which the parser's
    # tests and the metrics half of the project both want.
    value: str = " "
    pos: int = -1


@dataclass
class Delim:
    value: str
    pos: int = -1


@dataclass
class Colon:
    pos: int = -1


@dataclass
class Semicolon:
    pos: int = -1


@dataclass
class Comma:
    pos: int = -1


@dataclass
class LBracket:
    pos: int = -1


@dataclass
class RBracket:
    pos: int = -1


@dataclass
class LParen:
    pos: int = -1


@dataclass
class RParen:
    pos: int = -1


@dataclass
class LBrace:
    pos: int = -1


@dataclass
class RBrace:
    pos: int = -1


@dataclass
class CDO:
    """`<!--`. Legacy HTML comment hiding; the parser ignores it at top level."""
    pos: int = -1


@dataclass
class CDC:
    """`-->`."""
    pos: int = -1


@dataclass
class EOFToken:
    pos: int = -1


CssToken = (
    Ident | Function | AtKeyword | Hash | String | BadString | Url | BadUrl
    | Number | Percentage | Dimension | Whitespace | Delim | Colon | Semicolon
    | Comma | LBracket | RBracket | LParen | RParen | LBrace | RBrace
    | CDO | CDC | EOFToken
)


# --------------------------------------------------------------------------
# Tokenizer
# --------------------------------------------------------------------------


class CssTokenizer:
    """
    Consumes a CSS string, yields CssTokens lazily.

        for token in CssTokenizer(css).tokenize():
            ...

    Laziness is load-bearing for the same reason it is in `htmlparse`: it lets
    us count and time tokens as they stream. It is also why `errors` is empty
    until `tokenize()` has actually been driven -- constructing a tokenizer
    parses nothing.
    """

    def __init__(self, source: str) -> None:
        self.source = self._preprocess(source)
        self.pos = 0
        self.errors: list[tuple[int, str]] = []
        self.metrics: Counter[str] = Counter()
        self._tokenized = False

    @staticmethod
    def _preprocess(source: str) -> str:
        """Spec 3.3. CRLF/CR/FF -> LF; NULL and lone surrogates -> U+FFFD."""
        source = source.replace("\r\n", "\n").replace("\r", "\n").replace("\f", "\n")
        if "\x00" in source:
            source = source.replace("\x00", REPLACEMENT)
        # Lone surrogates cannot appear in text read from a file, but they can
        # appear in a str built in Python, and every later `ord()` test would
        # then be operating on a code point the spec says cannot be there.
        if any("\ud800" <= ch <= "\udfff" for ch in source):
            source = "".join(
                REPLACEMENT if "\ud800" <= ch <= "\udfff" else ch for ch in source
            )
        return source

    # -- input helpers -----------------------------------------------------

    def _next(self) -> str | None:
        if self.pos >= len(self.source):
            return EOF
        ch = self.source[self.pos]
        self.pos += 1
        return ch

    def _peek(self, n: int = 1) -> str:
        """The next `n` characters as a string; shorter than `n` near EOF."""
        return self.source[self.pos:self.pos + n]

    def _at(self, offset: int = 0) -> str | None:
        """The single character `offset` ahead of the cursor, or EOF.

        `offset` is negative at the four sites that reconsume -- they have
        already consumed a character and ask the spec predicates about it. The
        `index < 0` guard is not reachable from those (pos is at least 1 there)
        but is not optional either: without it a negative index would silently
        wrap to the *end* of the source, which is the worst possible failure
        mode for a lookahead helper.
        """
        index = self.pos + offset
        if index < 0 or index >= len(self.source):
            return EOF
        return self.source[index]

    def _reconsume(self, ch: str | None) -> None:
        """Push back the character `_next()` just returned.

        Guarded on the sentinel: `_next()` does not advance the cursor at end
        of input, so decrementing unconditionally would rewind past the last
        real character and re-tokenize it.
        """
        if ch is not EOF:
            self.pos -= 1

    def _error(self, message: str, pos: int | None = None) -> None:
        """Record a parse error.

        Same convention as `htmlparse.Tokenizer._error`: **the recorded offset
        points AT the character that caused the error**, never past it. A site
        that has just consumed the offender passes `self.pos - 1`. Omitting
        `pos` records `self.pos`, which is correct only where there is no
        offending character at all -- the EOF errors, where `self.pos` is
        `len(self.source)`.

        The CSS spec never *fails* to tokenize. Every call site here recovers
        and emits a token; nothing raises.
        """
        self.errors.append((self.pos if pos is None else pos, message))
        self.metrics["parse_errors"] += 1

    # -- spec predicates ---------------------------------------------------

    def _is_valid_escape(self, offset: int = 0) -> bool:
        """Spec 4.3.8, reading the two code points at `offset`.

        Note this is *not* "the next character is a backslash": a backslash
        followed by a newline is not a valid escape, which is why
        `a\\<newline>b` is three tokens and not one ident.
        """
        if self._at(offset) != "\\":
            return False
        second = self._at(offset + 1)
        return second is not EOF and second != "\n"

    def _starts_ident_sequence(self, offset: int = 0) -> bool:
        """Spec 4.3.9, reading the three code points at `offset`."""
        first = self._at(offset)
        if first == "-":
            second = self._at(offset + 1)
            if _is_ident_start(second) or second == "-":
                return True
            return self._is_valid_escape(offset + 1)
        if _is_ident_start(first):
            return True
        if first == "\\":
            return self._is_valid_escape(offset)
        return False

    def _starts_number(self, offset: int = 0) -> bool:
        """Spec 4.3.10, reading the three code points at `offset`."""
        first = self._at(offset)
        if first in ("+", "-"):
            second = self._at(offset + 1)
            if second is not EOF and second in DIGITS:
                return True
            return second == "." and (self._at(offset + 2) or "") in DIGITS
        if first == ".":
            second = self._at(offset + 1)
            return second is not EOF and second in DIGITS
        return first is not EOF and first in DIGITS

    # -- main loop ---------------------------------------------------------

    def tokenize(self) -> Iterator[CssToken]:
        """Yield tokens until and including EOFToken.

        **Single use.** A tokenizer owns a cursor, an error list and a metrics
        Counter, and all three are consumed by one pass: a second call would
        resume from `pos == len(source)`, yield nothing but EOF, and overwrite
        `tokenize_time_ms` with the time that took. Raise instead. Construct a
        new tokenizer, or `list()` the first pass if you need to re-read it.

        Not a generator itself, deliberately: a generator's body does not run
        until it is first advanced, so the guard would fire at iteration
        rather than at the offending call, which is the wrong place to be
        told about it.
        """
        if self._tokenized:
            raise RuntimeError(
                "CssTokenizer.tokenize() is single-use; construct a new "
                "CssTokenizer to tokenize the same source again"
            )
        self._tokenized = True
        return self._tokenize()

    def _tokenize(self) -> Iterator[CssToken]:
        elapsed = 0.0
        while True:
            started = time.perf_counter()
            token = self._consume_token()
            elapsed += time.perf_counter() - started
            if isinstance(token, EOFToken):
                # Not int(): a stylesheet the size of the ones in data/corpus/
                # tokenizes in well under a millisecond, and a timing metric
                # that always reads 0 is not a timing metric.
                self.metrics["tokenize_time_ms"] = round(elapsed * 1000, 3)
                yield token
                return
            # EOF is a sentinel, not a token of the source: counting it would
            # put every "tokens per byte" ratio off by one.
            self.metrics["tokens"] += 1
            yield token

    # -- 4.3.1 consume a token ---------------------------------------------

    def _consume_token(self) -> CssToken:
        self._consume_comments()
        start = self.pos
        ch = self._next()

        if ch is EOF:
            return EOFToken(pos=start)

        if ch in WHITESPACE:
            run = [ch]
            while (nxt := self._at()) is not EOF and nxt in WHITESPACE:
                run.append(self._next())
            return Whitespace("".join(run), pos=start)

        if ch in ('"', "'"):
            return self._consume_string(ch, start)

        if ch == "#":
            # A hash token needs an ident code point or a valid escape after
            # the '#'; `#` alone, or `# `, is a Delim.
            if _is_ident(self._at()) or self._is_valid_escape():
                is_id = self._starts_ident_sequence()
                return Hash(self._consume_ident_sequence(), is_id, pos=start)
            return Delim("#", pos=start)

        if ch == "(":
            return LParen(pos=start)
        if ch == ")":
            return RParen(pos=start)
        if ch == "[":
            return LBracket(pos=start)
        if ch == "]":
            return RBracket(pos=start)
        if ch == "{":
            return LBrace(pos=start)
        if ch == "}":
            return RBrace(pos=start)
        if ch == ",":
            return Comma(pos=start)
        if ch == ":":
            return Colon(pos=start)
        if ch == ";":
            return Semicolon(pos=start)

        if ch == "+":
            if self._starts_number(-1):
                self._reconsume(ch)
                return self._consume_numeric()
            return Delim("+", pos=start)

        if ch == "-":
            if self._starts_number(-1):
                self._reconsume(ch)
                return self._consume_numeric()
            if self._peek(2) == "->":
                self.pos += 2
                return CDC(pos=start)
            if self._starts_ident_sequence(-1):
                self._reconsume(ch)
                return self._consume_ident_like()
            return Delim("-", pos=start)

        if ch == ".":
            if self._starts_number(-1):
                self._reconsume(ch)
                return self._consume_numeric()
            return Delim(".", pos=start)

        if ch == "<":
            if self._peek(3) == "!--":
                self.pos += 3
                return CDO(pos=start)
            return Delim("<", pos=start)

        if ch == "@":
            if self._starts_ident_sequence():
                return AtKeyword(self._consume_ident_sequence(), pos=start)
            return Delim("@", pos=start)

        if ch == "\\":
            if self._is_valid_escape(-1):
                self._reconsume(ch)
                return self._consume_ident_like()
            # A backslash that cannot start an escape -- at EOF, or before a
            # newline. The spec says parse error, emit a delim.
            self._error("invalid escape", start)
            return Delim("\\", pos=start)

        if ch in DIGITS:
            self._reconsume(ch)
            return self._consume_numeric()

        if _is_ident_start(ch):
            self._reconsume(ch)
            return self._consume_ident_like()

        return Delim(ch, pos=start)

    # -- 4.3.2 consume comments --------------------------------------------

    def _consume_comments(self) -> None:
        """Consume any run of `/* ... */`. Comments are not tokens.

        Called at the top of every `_consume_token`, which is where the spec
        puts it. A `/` not followed by `*` falls through to the delim branch.
        """
        while self._peek(2) == "/*":
            start = self.pos
            end = self.source.find("*/", self.pos + 2)
            if end == -1:
                self.pos = len(self.source)
                self._error("unterminated comment", start)
                self.metrics["comments"] += 1
                return
            self.pos = end + 2
            self.metrics["comments"] += 1

    # -- 4.3.3 consume a numeric token -------------------------------------

    def _consume_numeric(self) -> CssToken:
        """Spec 4.3.3. Returns Number, Percentage or Dimension."""
        start = self.pos
        value, is_integer = self._consume_number()
        if self._starts_ident_sequence():
            return Dimension(
                value, self._consume_ident_sequence(), is_integer, pos=start
            )
        if self._peek(1) == "%":
            self._next()
            return Percentage(value, is_integer, pos=start)
        return Number(value, is_integer, pos=start)

    # -- 4.3.4 consume an ident-like token ---------------------------------

    def _consume_ident_like(self) -> CssToken:
        """Spec 4.3.4. Ident, Function, or -- only here -- Url."""
        start = self.pos
        name = self._consume_ident_sequence()

        if _ascii_lower(name) == "url" and self._peek(1) == "(":
            self._next()
            # "While the next two input code points are whitespace, consume
            # one." Leaves at most one whitespace character in place, which is
            # what makes the quote test below able to see past it.
            while len(self._peek(2)) == 2 and set(self._peek(2)) <= WHITESPACE:
                self._next()
            first, second = self._at(0), self._at(1)
            if first in ('"', "'") or (
                first is not EOF and first in WHITESPACE and second in ('"', "'")
            ):
                # `url("a.png")` is a Function token followed by a String. The
                # url-token below exists only for the unquoted form.
                self.metrics["functions"] += 1
                return Function(name, pos=start)
            return self._consume_url(start)

        if self._peek(1) == "(":
            self._next()
            self.metrics["functions"] += 1
            return Function(name, pos=start)

        return Ident(name, pos=start)

    # -- 4.3.5 consume a string token --------------------------------------

    def _consume_string(self, ending: str, start: int) -> CssToken:
        """Spec 4.3.5. The opening quote has already been consumed.

        `start` is the offset of that quote, so the token points at it rather
        than at the first character of the content.
        """
        out: list[str] = []
        while True:
            ch = self._next()
            if ch is EOF:
                self._error("eof in string")
                return String("".join(out), pos=start)
            if ch == ending:
                return String("".join(out), pos=start)
            if ch == "\n":
                # Reconsume: the newline belongs to whatever follows, so the
                # stream recovers instead of swallowing the rest of the file.
                self._reconsume(ch)
                self._error("newline in string", self.pos)
                self.metrics["bad_strings"] += 1
                return BadString(pos=start)
            if ch == "\\":
                nxt = self._at()
                if nxt is EOF:
                    continue          # spec: do nothing
                if nxt == "\n":
                    self._next()      # line continuation; contributes nothing
                    continue
                out.append(self._consume_escape())
                continue
            out.append(ch)

    # -- 4.3.6 consume a url token -----------------------------------------

    def _consume_url(self, start: int) -> CssToken:
        """Spec 4.3.6. Only reached for UNQUOTED url(...).

        `url("a.png")` is a Function token followed by a String -- the special
        url-token exists only so that unquoted URLs, which contain characters
        no other token permits (`/`, `?`, `&`, `:`), survive tokenization.

        The brief sketched this as a plain "read until ')'" loop. That is not
        the spec algorithm and it silently accepts input the spec rejects:
        `url(a b)` would become Url("a b") rather than a BadUrl, and every
        later consumer would inherit a URL that no browser produces.
        """
        out: list[str] = []
        while (ch := self._at()) is not EOF and ch in WHITESPACE:
            self._next()
        while True:
            ch = self._next()
            if ch == ")":
                self.metrics["urls"] += 1
                return Url("".join(out), pos=start)
            if ch is EOF:
                self._error("eof in url")
                self.metrics["urls"] += 1
                return Url("".join(out), pos=start)
            if ch in WHITESPACE:
                while (nxt := self._at()) is not EOF and nxt in WHITESPACE:
                    self._next()
                if self._at() == ")":
                    self._next()
                    self.metrics["urls"] += 1
                    return Url("".join(out), pos=start)
                if self._at() is EOF:
                    self._error("eof in url")
                    self.metrics["urls"] += 1
                    return Url("".join(out), pos=start)
                # NO parse error here, deliberately. 4.3.6's whitespace branch
                # designates one for the EOF sub-case above and for nothing
                # else -- unlike the quote/paren/non-printable and invalid-
                # escape branches below, which each say "this is a parse
                # error" in so many words. `url(a b)` is malformed and yields
                # a <bad-url-token>, but the spec does not count it, so
                # neither do we: `parse_errors` is a conformance signal and
                # inflating it would corrupt the corpus-wide baseline. The
                # bad url is still counted, as `bad_urls`.
                return self._consume_bad_url_remnants(start)
            if ch in ('"', "'", "(") or _is_non_printable(ch):
                self._error(f"unexpected {ch!r} inside unquoted url", self.pos - 1)
                return self._consume_bad_url_remnants(start)
            if ch == "\\":
                if self._is_valid_escape(-1):
                    out.append(self._consume_escape())
                    continue
                self._error("invalid escape inside url", self.pos - 1)
                return self._consume_bad_url_remnants(start)
            out.append(ch)

    # -- 4.3.7 consume an escaped code point -------------------------------

    def _consume_escape(self) -> str:
        """Spec 4.3.7. The backslash has already been consumed.

        This is the CSS analogue of `htmlparse.entities.decode_reference`, and
        the same three traps apply: the digit run has a maximum length, one
        trailing whitespace character is part of the escape rather than a
        separator that survives, and out-of-range values do not raise.
        """
        # Counted on every path, including the three that yield U+FFFD. The
        # counter answers "how many escapes were in this stylesheet", which is
        # a property of the input; an escape that resolves to the replacement
        # character was still written, and dropping it would make `escapes`
        # disagree with `parse_errors` on exactly the inputs worth looking at.
        self.metrics["escapes"] += 1
        ch = self._next()
        if ch is EOF:
            # Unreachable today: all four call sites check `_is_valid_escape`
            # first, and a backslash at EOF fails that test, so the caller
            # emits a Delim and never gets here. Kept because 4.3.7 has the
            # branch and a fifth caller would need it.
            self._error("eof in escape")
            return REPLACEMENT
        if ch in HEX_DIGITS:
            digits = ch
            while len(digits) < 6 and self._peek(1) in HEX_DIGITS:
                digits += self._next()
            # Exactly one whitespace character after the digits is consumed as
            # part of the escape. `\26  x` is "&" then a real space then "x".
            if self._peek(1) in WHITESPACE:
                self._next()
            value = int(digits, 16)
            if value == 0 or value > MAX_CODE_POINT or 0xD800 <= value <= 0xDFFF:
                return REPLACEMENT
            return chr(value)
        return ch

    # -- 4.3.11 consume an ident sequence ----------------------------------

    def _consume_ident_sequence(self) -> str:
        """Spec 4.3.11. Never returns a parse error; may return ""."""
        out: list[str] = []
        while True:
            ch = self._next()
            if _is_ident(ch):
                out.append(ch)
                continue
            if ch == "\\" and self._is_valid_escape(-1):
                out.append(self._consume_escape())
                continue
            self._reconsume(ch)
            return "".join(out)

    # -- 4.3.12 / 4.3.13 consume a number, convert it ----------------------

    def _consume_number(self) -> tuple[int | float, bool]:
        """Spec 4.3.12. Returns (value, is_integer).

        `is_integer` is the spec's type flag and records how the number was
        *written*: `1e3` is a "number" even though its value is 1000.
        """
        out: list[str] = []
        is_integer = True

        if (ch := self._at()) in ("+", "-"):
            out.append(self._next())
        while (ch := self._at()) is not EOF and ch in DIGITS:
            out.append(self._next())

        if self._at() == "." and (self._at(1) or "") in DIGITS:
            out.append(self._next())
            out.append(self._next())
            is_integer = False
            while (ch := self._at()) is not EOF and ch in DIGITS:
                out.append(self._next())

        # Exponent: e/E, an optional sign, then at least one digit. Anything
        # short of that is not an exponent -- `1em` must stay Dimension(1,"em").
        if self._at() in ("e", "E"):
            after_sign = 1 + (1 if self._at(1) in ("+", "-") else 0)
            if (self._at(after_sign) or "") in DIGITS:
                out.append(self._next())            # e/E
                if self._at() in ("+", "-"):
                    out.append(self._next())
                is_integer = False
                while (ch := self._at()) is not EOF and ch in DIGITS:
                    out.append(self._next())

        text = "".join(out)
        # 4.3.13. See deviation 3: `_consume_number` only builds strings that
        # match the spec's number grammar, a strict subset of Python's.
        value: int | float = int(text) if is_integer else float(text)
        return value, is_integer

    # -- 4.3.14 consume the remnants of a bad url --------------------------

    def _consume_bad_url_remnants(self, start: int) -> BadUrl:
        """Spec 4.3.14. Discard input up to and including the closing ')'.

        Escapes are consumed rather than scanned past, so a `\\)` inside the
        junk does not end the bad url early.
        """
        while True:
            ch = self._next()
            if ch == ")" or ch is EOF:
                self.metrics["bad_urls"] += 1
                return BadUrl(pos=start)
            if ch == "\\" and self._is_valid_escape(-1):
                self._consume_escape()


__all__ = [
    "AtKeyword", "BadString", "BadUrl", "CDC", "CDO", "Colon", "Comma",
    "CssToken", "CssTokenizer", "Delim", "Dimension", "EOFToken", "Function",
    "Hash", "Ident", "LBrace", "LBracket", "LParen", "Number", "Percentage",
    "RBrace", "RBracket", "RParen", "Semicolon", "String", "Url", "Whitespace",
]
