"""
Mayshay HTML tokenizer.

A hand-rolled implementation of the WHATWG HTML tokenization state machine:
https://html.spec.whatwg.org/multipage/parsing.html#tokenization

Deliberate deviations from the spec, documented so they don't surprise us later:

1. The spec emits one character token per character. We coalesce runs of text
   into a single Character token. This is what real engines do too, and it cuts
   token count by ~50x on text-heavy pages.
2. Named and numeric character references (&amp;, &nbsp;, &#65;) are decoded
   in the data state, the RCDATA state, and the three attribute-value states
   -- see htmlparse/entities.py. RAWTEXT, script data and comments leave
   references untouched, per spec.
3. DOCTYPE parsing is simplified: we capture the name and discard public and
   system identifiers. The only thing downstream wants them for is quirks-mode
   detection, so quirks detection is name-based only -- the spec's long list of
   quirky public identifiers ("-//W3C//DTD HTML 4.01 Frameset//", "about:legacy-compat"
   as a *non*-quirky system id, and so on) cannot be evaluated here. See the
   force-quirks note on _state_doctype.
4. The double-escaped script data states (script data double escape start /
   double escaped / double escaped dash / dash dash / less-than sign / double
   escape end) are NOT implemented. `<script><!--<script>...</script>-->` is
   therefore tokenized as if the inner `</script>` closed the outer element.
   Real-world usage is rare and the eight-state cycle earns its own task;
   pinned by an xfail in tests/htmlparse/test_rawtext.py.
5. Reaching EOF in the rcdata / rawtext / script data states records a parse
   error. The spec calls for no error there -- it just emits the EOF token.
   We keep the error because an unterminated <script>/<style>/<textarea> is a
   truncation signal worth counting in the metrics.
6. U+0000 NULL is never replaced with U+FFFD, anywhere. The spec replaces NUL
   in the data, RCDATA, RAWTEXT, script-data, tag-name, attribute-name and
   attribute-value states (and the tree builder drops NUL character tokens in
   "in body"). We pass it through untouched: a NUL inside a tag name lands in
   Element.tag_name literally, and a NUL in text lands in a Text node.
   ~46 tree-construction corpus cases.
7. The PLAINTEXT state is NOT implemented, and neither is the <plaintext>
   start tag that switches into it. Everything after `<plaintext>` is therefore
   tokenized as ordinary data: `<plaintext>a<b>c` parses <b> as a real tag.
   Note that treebuilder.CLOSES_P and treebuilder.SPECIAL_ELEMENTS *do* list
   `plaintext`, because those sets are kept spec-correct -- the tree-builder
   half of the feature exists, the tokenizer half does not. ~52 corpus cases.
8. The comment states are collapsed into a single `_state_comment`: there is no
   comment-start, comment-start-dash, comment-less-than-sign, comment-end-dash,
   comment-end or comment-end-bang state. We scan for the first `-->` and take
   everything before it as the data. So `<!-- <!--` gives " <!--" where the spec
   gives " <!", and `<!--a--!>` gives "a--!>" where the spec gives "a".
   ~17 corpus cases; also named in the xfail ledgers of two test files.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Iterator

from mayshay.htmlparse.entities import decode_reference

# Characters the spec treats as whitespace during tokenization.
WHITESPACE = "\t\n\f\r "
EOF = None  # sentinel for end of input


def _is_ascii_alpha(ch: str | None) -> bool:
    """The spec means ASCII alpha. Python's str.isalpha() also accepts 'é'."""
    return ch is not None and ch.isascii() and ch.isalpha()


# --------------------------------------------------------------------------
# Tokens
# --------------------------------------------------------------------------

@dataclass
class DoctypeToken:
    name: str | None = None
    force_quirks: bool = False
    pos: int = -1


@dataclass
class StartTagToken:
    name: str
    attrs: dict[str, str] = field(default_factory=dict)
    self_closing: bool = False
    pos: int = -1


@dataclass
class EndTagToken:
    name: str
    # Attributes on an end tag are a parse error the spec tells you to ignore,
    # and we do ignore them: the tokenizer runs the same attribute states for
    # end tags as for start tags, so they land here, and nothing reads them.
    # treebuilder.py contains zero references to EndTagToken.attrs. The field
    # is kept only so both tag tokens have the same shape; do not read it
    # expecting a warning surface that does not exist.
    attrs: dict[str, str] = field(default_factory=dict)
    pos: int = -1


@dataclass
class CommentToken:
    data: str = ""
    pos: int = -1


@dataclass
class CharacterToken:
    data: str
    pos: int = -1


@dataclass
class EOFToken:
    pos: int = -1


Token = (
    DoctypeToken | StartTagToken | EndTagToken
    | CommentToken | CharacterToken | EOFToken
)


# Elements whose content is tokenized as RCDATA: character references ARE
# decoded, but tags are not recognised.
RCDATA_ELEMENTS = frozenset({"title", "textarea"})

# Elements whose content is tokenized as RAWTEXT: neither references nor tags.
RAWTEXT_ELEMENTS = frozenset({"style", "xmp", "iframe", "noembed", "noframes"})

# <script> has its own state family because of the <!-- --> escape rules.
SCRIPT_ELEMENTS = frozenset({"script"})


# --------------------------------------------------------------------------
# Tokenizer
# --------------------------------------------------------------------------

class Tokenizer:
    """
    Consumes an HTML string, yields Tokens lazily.

        for token in Tokenizer(html).tokenize():
            ...

    Laziness is load-bearing: it lets us time and count tokens as they stream
    rather than reconstructing that after the fact.
    """

    def __init__(self, source: str) -> None:
        # Spec input preprocessing: normalise CRLF and lone CR to LF.
        self.source = source.replace("\r\n", "\n").replace("\r", "\n")
        self.pos = 0
        self.state = "data"

        # Scratch space for the token currently under construction.
        self._buffer: list[str] = []       # accumulating text / comment data
        self._tag_name: list[str] = []
        self._is_end_tag = False
        self._self_closing = False
        self._attrs: dict[str, str] = {}
        self._attr_name: list[str] = []
        self._attr_value: list[str] = []
        # Offset of the first character of the attribute name being built, so
        # a duplicate-attribute error can point at the attribute rather than
        # at whatever character happened to finish it.
        self._attr_name_start = 0

        # Characters consumed while trying to match an "appropriate end tag"
        # inside raw text. Replayed as text when the match fails.
        self._temp_buffer: list[str] = []

        self._token_start = 0    # offset where the in-progress token began
        self._buffer_start = 0    # offset where the pending text run began
        self._last_start_tag: str | None = None

        self.errors: list[tuple[int, str]] = []
        self.metrics: Counter[str] = Counter()

    # -- input helpers -----------------------------------------------------

    def _next(self) -> str | None:
        if self.pos >= len(self.source):
            return EOF
        ch = self.source[self.pos]
        self.pos += 1
        return ch

    def _peek(self, n: int = 1) -> str:
        return self.source[self.pos:self.pos + n]

    def _error(self, message: str, pos: int | None = None) -> None:
        """Record a parse error.

        Convention, and it is load-bearing because nothing downstream has been
        written against this field yet: **the recorded offset points AT the
        character that caused the error**, never past it.

        `_next()` has already advanced `self.pos` past the character it
        returned, so a state that has just consumed the offender passes
        `self.pos - 1` (or further back when the offender is not the character
        just read, e.g. the solidus in `_state_self_closing_start_tag`).

        Omitting `pos` records `self.pos`. That is correct at exactly two
        kinds of site, and both are checked: the eighteen EOF errors, where
        there is no offending character at all and `self.pos` is
        `len(self.source)`, one past the last character; and
        `_state_markup_declaration_open`, which peeks rather than consuming, so
        `self.pos` is still sitting on the offender. Every other site passes an
        explicit offset.

        Two sub-conventions cover the cases where no character is literally at
        fault:

        - An error about an *absent* character is recorded at the position it
          should have occupied -- the missing semicolon after a character
          reference points at whatever is sitting where the ';' belonged.
        - The two character-reference *value* errors (control-character and
          invalid-numeric) are recorded at the opening '&'. Their offence is
          the code point the reference as a whole denotes, so no single
          character causes them and the convention has no unique answer; the
          '&' is chosen because it is the one character guaranteed to exist and
          to belong to the offending construct. See entities.decode_reference.
        """
        self.errors.append((self.pos if pos is None else pos, message))
        self.metrics["parse_errors"] += 1

    def _consume_character_reference(self, in_attribute: bool) -> str:
        """Called with self.pos just past the '&'."""
        start = self.pos
        text, new_pos, error = decode_reference(self.source, start, in_attribute)
        self.pos = new_pos
        if error:
            # decode_reference reports its own offset. Deriving one from
            # self.pos here would be wrong three ways: on the absence-of-digits
            # path new_pos has not moved off the '#' at all, and the two value
            # errors land past the reference entirely.
            self._error(error[1], error[0])
        # A reference was actually consumed iff decode_reference advanced the
        # position. Checking `text != "&"` instead is wrong: a *successful*
        # decode of "&amp;" also returns "&", which would undercount it as a
        # miss, and it's indistinguishable here from the no-match case, which
        # returns ("&", start, None) with the position left unmoved.
        if new_pos > start:
            self.metrics["character_references"] += 1
        return text

    # -- token construction ------------------------------------------------

    def _flush_text(self) -> Iterator[Token]:
        if self._buffer:
            text = "".join(self._buffer)
            self._buffer.clear()
            self.metrics["character_tokens"] += 1
            yield CharacterToken(text, pos=self._buffer_start)

    def _start_tag(self, is_end: bool, first_char: str) -> None:
        self._tag_name = [first_char.lower()]
        self._is_end_tag = is_end
        self._self_closing = False
        self._attrs = {}
        self._token_start = self.pos - (3 if is_end else 2)

    def _save_attr(self) -> None:
        if not self._attr_name:
            return
        name = "".join(self._attr_name)
        # The spec keeps the FIRST occurrence of a duplicate attribute.
        if name not in self._attrs:
            self._attrs[name] = "".join(self._attr_value)
        else:
            self._error(f"duplicate attribute {name!r}", self._attr_name_start)
        self._attr_name.clear()
        self._attr_value.clear()

    def _emit_tag(self) -> Token:
        self._save_attr()
        name = "".join(self._tag_name)

        if self._is_end_tag:
            self.metrics["end_tags"] += 1
            return EndTagToken(name, self._attrs, pos=self._token_start)

        # A raw-text start tag switches the tokenizer itself. Callers assign
        # self.state = "data" *before* calling _emit_tag, so this wins -- and
        # it also wins over TreeBuilder.insert_raw_text_element's switch_to,
        # which runs later and therefore never changes anything. See
        # Tokenizer.switch_to for why that duplication is deliberate for now.
        self._last_start_tag = name
        if name in RCDATA_ELEMENTS:
            self.state = "rcdata"
        elif name in RAWTEXT_ELEMENTS:
            self.state = "rawtext"
        elif name in SCRIPT_ELEMENTS:
            self.state = "script_data"
        self.metrics["start_tags"] += 1
        return StartTagToken(
            name, self._attrs, self._self_closing, pos=self._token_start
        )

    # -- main loop ---------------------------------------------------------

    def tokenize(self) -> Iterator[Token]:
        while True:
            if self.state == "eof":
                yield from self._flush_text()
                yield EOFToken()
                return
            yield from getattr(self, f"_state_{self.state}")()

    def switch_to(self, state: str, last_start_tag: str | None = None) -> None:
        """
        Seam for the tree builder to drive the tokenizer.

        **This does not currently drive anything.** `_emit_tag` above already
        switches to rcdata / rawtext / script_data on every start tag, from the
        same three frozensets the tree builder consults, and it does so before
        the token is dispatched. So by the time `TreeBuilder.
        insert_raw_text_element` calls this, the state and `_last_start_tag`
        are already what it is about to assign. Measured over all 1592
        tree-construction corpus cases: 354 calls, 0 that changed either field.
        Every one is a no-op re-assignment.

        It is kept, not deleted, for two reasons. The corpus harness uses it to
        set up raw-text tokenizer cases with an explicit initial state and
        last-start-tag. And it is the seam the spec's design requires: the
        RCDATA/RAWTEXT decision belongs to the tree builder *because it is
        contextual*, and the first contextual case -- foreign content, where
        `<svg><title>` must not be tokenized as RCDATA -- breaks the moment a
        tokenizer decides on its own. Retiring `_emit_tag`'s unilateral switch
        in favour of this method is a phase-2 task, and the measurement above
        is what makes it a safe refactor to do before foreign content lands
        rather than after.
        """
        self.state = state
        if last_start_tag is not None:
            self._last_start_tag = last_start_tag

    # -- states ------------------------------------------------------------

    def _state_data(self) -> Iterator[Token]:
        ch = self._next()
        if ch is EOF:
            self.state = "eof"
        elif ch == "<":
            yield from self._flush_text()
            self.state = "tag_open"
        elif ch == "&":
            if not self._buffer:
                self._buffer_start = self.pos - 1
            self._buffer.append(self._consume_character_reference(False))
        else:
            if not self._buffer:
                self._buffer_start = self.pos - 1
            self._buffer.append(ch)
        return
        yield  # makes this a generator even on paths that emit nothing

    # -- raw text: RCDATA / RAWTEXT / ScriptData --------------------------
    #
    # The three families are structurally identical, so they share one
    # parameterised body each rather than 26 near-duplicate methods. `name` is
    # the family's own state name, which is also the prefix of its
    # _less_than_sign / _end_tag_open / _end_tag_name states.

    def _is_appropriate_end_tag(self) -> bool:
        """An end tag in raw text only counts if it matches the last start tag."""
        return "".join(self._tag_name) == self._last_start_tag

    def _raw_text_state(self, name: str) -> Iterator[Token]:
        """Shared body for the rcdata / rawtext / script_data states."""
        ch = self._next()
        if ch is EOF:
            self._error(f"eof in {name}")
            self.state = "eof"
        elif ch == "<":
            self._temp_buffer = []
            self.state = f"{name}_less_than_sign"
        elif ch == "&" and name == "rcdata":
            if not self._buffer:
                self._buffer_start = self.pos - 1
            self._buffer.append(self._consume_character_reference(False))
        else:
            # No special case for '-' here. A dash in script data is ordinary
            # text; the escaped family is entered via '<!' in
            # _raw_less_than_sign_state, and the dash counting happens in
            # script_data_escape_start / _escape_start_dash.
            if not self._buffer:
                self._buffer_start = self.pos - 1
            self._buffer.append(ch)
        return
        yield

    def _raw_less_than_sign_state(self, name: str) -> Iterator[Token]:
        ch = self._next()
        if ch == "/":
            self._temp_buffer = []
            self.state = f"{name}_end_tag_open"
        elif name == "script_data" and ch == "!":
            # "<!" starts a new text run when the buffer is empty. pos is just
            # past the '!', so the run began two characters back.
            if not self._buffer:
                self._buffer_start = self.pos - 2
            self._buffer.append("<!")
            self.state = "script_data_escape_start"
        else:
            # Reconsume first: _buffer_start is derived from self.pos.
            if ch is not EOF:
                self.pos -= 1
            if not self._buffer:
                self._buffer_start = self.pos - 1
            self._buffer.append("<")
            self.state = name
        return
        yield

    def _raw_end_tag_open_state(self, name: str) -> Iterator[Token]:
        ch = self._next()
        if _is_ascii_alpha(ch):
            self._start_tag(is_end=True, first_char=ch)
            self._temp_buffer = [ch]
            self.state = f"{name}_end_tag_name"
        else:
            if ch is not EOF:
                self.pos -= 1
            if not self._buffer:
                self._buffer_start = self.pos - 2
            self._buffer.append("</")
            self.state = name
        return
        yield

    def _raw_end_tag_name_state(self, name: str) -> Iterator[Token]:
        ch = self._next()
        # Each appropriate-end-tag branch MUST flush pending raw text first.
        # The buffer still holds the element's content at this point, and the
        # tag token is about to be emitted (here for '>', or shortly after via
        # before_attribute_name / self_closing_start_tag). Without the flush
        # the text token surfaces *after* its own closing tag.
        #
        # `ch is not EOF` guards the membership test: `None in WHITESPACE`
        # raises TypeError, so EOF must fall through to the else branch.
        if ch is not EOF and ch in WHITESPACE and self._is_appropriate_end_tag():
            yield from self._flush_text()
            self.state = "before_attribute_name"
        elif ch == "/" and self._is_appropriate_end_tag():
            yield from self._flush_text()
            self.state = "self_closing_start_tag"
        elif ch == ">" and self._is_appropriate_end_tag():
            yield from self._flush_text()
            self.state = "data"
            yield self._emit_tag()
        elif _is_ascii_alpha(ch):
            self._tag_name.append(ch.lower())
            self._temp_buffer.append(ch)
        else:
            # Not the appropriate end tag: everything consumed becomes text.
            # Reconsume before computing _buffer_start -- the offset is
            # relative to self.pos, and _next() already advanced past ch.
            if ch is not EOF:
                self.pos -= 1
            if not self._buffer:
                self._buffer_start = self.pos - len(self._temp_buffer) - 2
            self._buffer.append("</")
            self._buffer.extend(self._temp_buffer)
            self.state = name

    def _state_rcdata(self): return self._raw_text_state("rcdata")
    def _state_rcdata_less_than_sign(self): return self._raw_less_than_sign_state("rcdata")
    def _state_rcdata_end_tag_open(self): return self._raw_end_tag_open_state("rcdata")
    def _state_rcdata_end_tag_name(self): return self._raw_end_tag_name_state("rcdata")

    def _state_rawtext(self): return self._raw_text_state("rawtext")
    def _state_rawtext_less_than_sign(self): return self._raw_less_than_sign_state("rawtext")
    def _state_rawtext_end_tag_open(self): return self._raw_end_tag_open_state("rawtext")
    def _state_rawtext_end_tag_name(self): return self._raw_end_tag_name_state("rawtext")

    def _state_script_data(self): return self._raw_text_state("script_data")
    def _state_script_data_less_than_sign(self): return self._raw_less_than_sign_state("script_data")
    def _state_script_data_end_tag_open(self): return self._raw_end_tag_open_state("script_data")
    def _state_script_data_end_tag_name(self): return self._raw_end_tag_name_state("script_data")

    # -- script data escaped ("<!-- ... -->" inside <script>) --------------

    def _state_script_data_escape_start(self) -> Iterator[Token]:
        ch = self._next()
        if ch == "-":
            self._buffer.append("-")
            self.state = "script_data_escape_start_dash"
        else:
            if ch is not EOF:
                self.pos -= 1
            self.state = "script_data"
        return
        yield

    def _state_script_data_escape_start_dash(self) -> Iterator[Token]:
        ch = self._next()
        if ch == "-":
            self._buffer.append("-")
            self.state = "script_data_escaped_dash_dash"
        else:
            if ch is not EOF:
                self.pos -= 1
            self.state = "script_data"
        return
        yield

    def _state_script_data_escaped(self) -> Iterator[Token]:
        ch = self._next()
        if ch is EOF:
            self._error("eof in script comment")
            self.state = "eof"
        elif ch == "-":
            self._buffer.append("-")
            self.state = "script_data_escaped_dash"
        elif ch == "<":
            self.state = "script_data_escaped_less_than_sign"
        else:
            self._buffer.append(ch)
        return
        yield

    def _state_script_data_escaped_dash(self) -> Iterator[Token]:
        ch = self._next()
        if ch is EOF:
            self._error("eof in script comment")
            self.state = "eof"
        elif ch == "-":
            self._buffer.append("-")
            self.state = "script_data_escaped_dash_dash"
        elif ch == "<":
            self.state = "script_data_escaped_less_than_sign"
        else:
            self._buffer.append(ch)
            self.state = "script_data_escaped"
        return
        yield

    def _state_script_data_escaped_dash_dash(self) -> Iterator[Token]:
        ch = self._next()
        if ch is EOF:
            self._error("eof in script comment")
            self.state = "eof"
        elif ch == "-":
            self._buffer.append("-")
        elif ch == "<":
            self.state = "script_data_escaped_less_than_sign"
        elif ch == ">":
            self._buffer.append(">")
            self.state = "script_data"
        else:
            self._buffer.append(ch)
            self.state = "script_data_escaped"
        return
        yield

    def _state_script_data_escaped_less_than_sign(self) -> Iterator[Token]:
        ch = self._next()
        if ch == "/":
            self._temp_buffer = []
            self.state = "script_data_escaped_end_tag_open"
        else:
            if ch is not EOF:
                self.pos -= 1
            # No `if not self._buffer: self._buffer_start = ...` guard, unlike
            # the sibling _raw_less_than_sign_state. Reaching the escaped
            # states requires having appended "<!--" to the buffer, so it is
            # never empty here; the guard would be dead code that reads like a
            # live one. Confirmed over all 1592 tree-construction corpus
            # cases: 119 arrivals at this branch, 0 with an empty buffer.
            self._buffer.append("<")
            self.state = "script_data_escaped"
        return
        yield

    def _state_script_data_escaped_end_tag_open(self):
        return self._raw_end_tag_open_state("script_data_escaped")

    def _state_script_data_escaped_end_tag_name(self):
        return self._raw_end_tag_name_state("script_data_escaped")

    # -- tags --------------------------------------------------------------

    def _state_tag_open(self) -> Iterator[Token]:
        ch = self._next()
        if ch is EOF:
            self._error("eof in tag")
            if not self._buffer:
                self._buffer_start = self.pos - 1
            self._buffer.append("<")
            self.state = "eof"
        elif ch == "!":
            self.state = "markup_declaration_open"
        elif ch == "/":
            self.state = "end_tag_open"
        elif _is_ascii_alpha(ch):
            self._start_tag(is_end=False, first_char=ch)
            self.state = "tag_name"
        elif ch == "?":
            self._error("unexpected ? instead of tag name", self.pos - 1)
            # No _buffer_start here: the buffer is about to become comment
            # data, and _state_bogus_comment emits a CommentToken, which
            # carries no pos. Nothing would ever read the offset.
            self._buffer = [ch]
            self.state = "bogus_comment"
        else:
            # A bare '<' in text. Extremely common. Treat as literal.
            self._error("invalid first character of tag name", self.pos - 1)
            if not self._buffer:
                self._buffer_start = self.pos - 2
            self._buffer.append("<")
            self.pos -= 1
            self.state = "data"
        return
        yield

    def _state_end_tag_open(self) -> Iterator[Token]:
        ch = self._next()
        if ch is EOF:
            self._error("eof before tag name")
            self.state = "eof"
        elif _is_ascii_alpha(ch):
            self._start_tag(is_end=True, first_char=ch)
            self.state = "tag_name"
        elif ch == ">":
            self._error("missing end tag name", self.pos - 1)
            self.state = "data"
        else:
            self._error("invalid first character of tag name", self.pos - 1)
            self._buffer = []
            self.pos -= 1
            self.state = "bogus_comment"
        return
        yield

    def _state_tag_name(self) -> Iterator[Token]:
        ch = self._next()
        if ch is EOF:
            self._error("eof in tag")
            self.state = "eof"
        elif ch in WHITESPACE:
            self.state = "before_attribute_name"
        elif ch == "/":
            self.state = "self_closing_start_tag"
        elif ch == ">":
            self.state = "data"
            token = self._emit_tag()   # may override state to rcdata/rawtext/script_data
            yield token
        else:
            self._tag_name.append(ch.lower())

    def _state_before_attribute_name(self) -> Iterator[Token]:
        ch = self._next()
        if ch is EOF:
            self._error("eof in tag")
            self.state = "eof"
        elif ch in WHITESPACE:
            pass
        elif ch in "/>":
            self.pos -= 1
            self.state = "after_attribute_name"
        elif ch == "=":
            self._error("unexpected = before attribute name", self.pos - 1)
            self._attr_name = [ch]
            self._attr_name_start = self.pos - 1
            self.state = "attribute_name"
        else:
            self._save_attr()
            self._attr_name = [ch.lower()]
            self._attr_name_start = self.pos - 1
            self.state = "attribute_name"
        return
        yield

    def _state_attribute_name(self) -> Iterator[Token]:
        ch = self._next()
        if ch is EOF:
            self._error("eof in tag")
            self.state = "eof"
        elif ch in WHITESPACE or ch in "/>":
            self.pos -= 1
            self.state = "after_attribute_name"
        elif ch == "=":
            self.state = "before_attribute_value"
        else:
            self._attr_name.append(ch.lower())
        return
        yield

    def _state_after_attribute_name(self) -> Iterator[Token]:
        ch = self._next()
        if ch is EOF:
            self._error("eof in tag")
            self.state = "eof"
        elif ch in WHITESPACE:
            pass
        elif ch == "/":
            self._save_attr()
            self.state = "self_closing_start_tag"
        elif ch == "=":
            self.state = "before_attribute_value"
        elif ch == ">":
            self.state = "data"
            token = self._emit_tag()   # may override state to rcdata/rawtext/script_data
            yield token
        else:
            # Valueless attribute, e.g. <input disabled name="x">
            self._save_attr()
            self._attr_name = [ch.lower()]
            self._attr_name_start = self.pos - 1
            self.state = "attribute_name"

    def _state_before_attribute_value(self) -> Iterator[Token]:
        ch = self._next()
        if ch is EOF:
            self._error("eof in tag")
            self.state = "eof"
        elif ch in WHITESPACE:
            pass
        elif ch == '"':
            self.state = "attribute_value_double"
        elif ch == "'":
            self.state = "attribute_value_single"
        elif ch == ">":
            self._error("missing attribute value", self.pos - 1)
            self.state = "data"
            token = self._emit_tag()   # may override state to rcdata/rawtext/script_data
            yield token
        else:
            self.pos -= 1
            self.state = "attribute_value_unquoted"

    def _state_attribute_value_double(self) -> Iterator[Token]:
        ch = self._next()
        if ch is EOF:
            self._error("eof in tag")
            self.state = "eof"
        elif ch == '"':
            self.state = "after_attribute_value_quoted"
        elif ch == "&":
            self._attr_value.append(self._consume_character_reference(True))
        else:
            self._attr_value.append(ch)
        return
        yield

    def _state_attribute_value_single(self) -> Iterator[Token]:
        ch = self._next()
        if ch is EOF:
            self._error("eof in tag")
            self.state = "eof"
        elif ch == "'":
            self.state = "after_attribute_value_quoted"
        elif ch == "&":
            self._attr_value.append(self._consume_character_reference(True))
        else:
            self._attr_value.append(ch)
        return
        yield

    def _state_attribute_value_unquoted(self) -> Iterator[Token]:
        ch = self._next()
        if ch is EOF:
            self._error("eof in tag")
            self.state = "eof"
        elif ch in WHITESPACE:
            self._save_attr()
            self.state = "before_attribute_name"
        elif ch == ">":
            self.state = "data"
            token = self._emit_tag()   # may override state to rcdata/rawtext/script_data
            yield token
        elif ch == "&":
            self._attr_value.append(self._consume_character_reference(True))
        else:
            self._attr_value.append(ch)

    def _state_after_attribute_value_quoted(self) -> Iterator[Token]:
        ch = self._next()
        if ch is EOF:
            self._error("eof in tag")
            self.state = "eof"
        elif ch in WHITESPACE:
            self._save_attr()
            self.state = "before_attribute_name"
        elif ch == "/":
            self._save_attr()
            self.state = "self_closing_start_tag"
        elif ch == ">":
            self.state = "data"
            token = self._emit_tag()   # may override state to rcdata/rawtext/script_data
            yield token
        else:
            self._error("missing whitespace between attributes", self.pos - 1)
            self._save_attr()
            self.pos -= 1
            self.state = "before_attribute_name"

    def _state_self_closing_start_tag(self) -> Iterator[Token]:
        ch = self._next()
        if ch is EOF:
            self._error("eof in tag")
            self.state = "eof"
        elif ch == ">":
            self._self_closing = True
            self.state = "data"
            token = self._emit_tag()   # may override state to rcdata/rawtext/script_data
            yield token
        else:
            # self.pos - 2, not - 1: the offender is the '/', and every state
            # that routes here consumed it as the character immediately before
            # the one _next() just returned.
            self._error("unexpected solidus in tag", self.pos - 2)
            self.pos -= 1
            self.state = "before_attribute_name"

    def _state_markup_declaration_open(self) -> Iterator[Token]:
        if self._peek(2) == "--":
            self.pos += 2
            self._buffer = []
            self.state = "comment"
        elif self._peek(7).upper() == "DOCTYPE":
            self.pos += 7
            self._buffer = []
            self.state = "doctype"
        else:
            # Nothing was consumed here (_peek, not _next), so self.pos
            # already points at the offending character after "<!".
            self._error("incorrectly opened comment")
            self._buffer = []
            self.state = "bogus_comment"
        return
        yield

    def _state_comment(self) -> Iterator[Token]:
        ch = self._next()
        if ch is EOF:
            self._error("eof in comment")
            self.metrics["comments"] += 1
            self.state = "eof"
            yield CommentToken("".join(self._buffer))
            self._buffer = []
        elif ch == "-" and self._peek(2) == "->":
            self.pos += 2
            data = "".join(self._buffer)
            self._buffer = []
            self.metrics["comments"] += 1
            self.state = "data"
            yield CommentToken(data)
        else:
            self._buffer.append(ch)

    def _state_bogus_comment(self) -> Iterator[Token]:
        ch = self._next()
        if ch is EOF or ch == ">":
            data = "".join(self._buffer)
            self._buffer = []
            self.metrics["comments"] += 1
            self.state = "eof" if ch is EOF else "data"
            yield CommentToken(data)
        else:
            self._buffer.append(ch)

    def _state_doctype(self) -> Iterator[Token]:
        """Simplified: consume to '>', keep the first word as the name.

        `force_quirks` is the *spec's* force-quirks flag, which is a tokenizer
        error flag and nothing else: it is set by eof-in-doctype, by a missing
        name, and by malformed public/system identifiers. It is NOT the quirks
        *mode* decision -- deciding that is the tree builder's "initial"
        insertion mode's job, and it also takes the name and the identifiers
        into account. See TreeBuilder._mode_initial.

        Because we discard public and system identifiers (deviation #3), the
        identifier-driven half of both the flag and the decision is a known
        gap: `<!DOCTYPE html PUBLIC "-//W3C//DTD HTML 4.0//EN">` should end up
        in quirks mode here and does not.
        """
        chars: list[str] = []
        force_quirks = False
        close_pos = -1
        while True:
            ch = self._next()
            if ch is EOF:
                self._error("eof in doctype")
                force_quirks = True   # spec: eof-in-doctype sets force-quirks
                self.state = "eof"
                break
            if ch == ">":
                close_pos = self.pos - 1
                self.state = "data"
                break
            chars.append(ch)
        raw = "".join(chars).strip()
        name = raw.split()[0].lower() if raw else None
        if name is None and not force_quirks:
            # `<!DOCTYPE>` / `<!DOCTYPE >`. At EOF the spec reports only
            # eof-in-doctype, so don't double-report; force-quirks is already
            # set on that path.
            self._error("missing doctype name", close_pos)
            force_quirks = True
        self.metrics["doctypes"] += 1
        yield DoctypeToken(name=name, force_quirks=force_quirks)


# --------------------------------------------------------------------------

if __name__ == "__main__":
    sample = """<!DOCTYPE html>
<html lang="en">
  <!-- a comment -->
  <body class=main data-x>
    <p>Hello <em>world</em> &amp; goodbye</p>
    <img src="a.png" alt="an image"/>
    <script>if (a < b) { console.log("<not a tag>"); }</script>
  </body>
</html>"""

    tk = Tokenizer(sample)
    for tok in tk.tokenize():
        if isinstance(tok, CharacterToken) and not tok.data.strip():
            continue  # skip whitespace-only text for readability
        print(tok)

    print("\nmetrics:", dict(tk.metrics))
    print("errors:", tk.errors)
