"""
Mayshay HTML tokenizer.

A hand-rolled implementation of the WHATWG HTML tokenization state machine:
https://html.spec.whatwg.org/multipage/parsing.html#tokenization

Deliberate deviations from the spec, documented so they don't surprise us later:

1. The spec emits one character token per character. We coalesce runs of text
   into a single Character token. This is what real engines do too, and it cuts
   token count by ~50x on text-heavy pages.
2. Named character references (&amp;, &nbsp;) are NOT decoded yet. That needs
   the 2200-entry named reference table plus the longest-match rules. Tracked
   as a TODO; text passes through raw for now.
3. DOCTYPE parsing is simplified: we capture the name and ignore public/system
   identifiers, since nothing downstream uses them except quirks-mode detection.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Iterator

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
    # Kept so the tree builder can warn about </div class="x">, which is a
    # parse error the spec ignores but which is a useful signal in our metrics.
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

        # The tag name whose RAWTEXT we're currently inside ("script", "style"),
        # or None when we're in normal Data state.
        self._rawtext_tag: str | None = None

        self._token_start = 0     # offset where the in-progress token began
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

    def _error(self, message: str) -> None:
        self.errors.append((self.pos, message))
        self.metrics["parse_errors"] += 1

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
            self._error(f"duplicate attribute {name!r}")
        self._attr_name.clear()
        self._attr_value.clear()

    def _emit_tag(self) -> Token:
        self._save_attr()
        name = "".join(self._tag_name)

        if self._is_end_tag:
            # Clear here, not in _state_tag_name: an end tag can also be
            # emitted from after_attribute_name (`</script >`), and missing
            # those paths leaves the tokenizer stuck in RAWTEXT forever.
            if name == self._rawtext_tag:
                self._rawtext_tag = None
            self.metrics["end_tags"] += 1
            return EndTagToken(name, self._attrs, pos=self._token_start)

        self._last_start_tag = name
        if name in RCDATA_ELEMENTS | RAWTEXT_ELEMENTS | SCRIPT_ELEMENTS:
            self._rawtext_tag = name
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
        Let the tree builder drive the tokenizer.

        The spec puts the RCDATA/RAWTEXT decision in the tree builder, not the
        tokenizer, because it is contextual. Task 6 uses this when it inserts
        a <title>, <style>, <script> or <textarea> element.
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
            # If we're inside <script>/<style>, only the matching close tag ends it.
            if self._rawtext_tag and self._peek(2 + len(self._rawtext_tag)).lower() \
                    != f"/{self._rawtext_tag}>"[:2 + len(self._rawtext_tag)]:
                if not self._peek(1 + len(self._rawtext_tag)).lower().startswith(
                        f"/{self._rawtext_tag}"):
                    self._buffer.append(ch)
                    return
            yield from self._flush_text()
            self.state = "tag_open"
        else:
            if not self._buffer:
                self._buffer_start = self.pos - 1
            self._buffer.append(ch)
        return
        yield  # makes this a generator even on paths that emit nothing

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
            self._error("unexpected ? instead of tag name")
            self._buffer_start = self.pos - 1
            self._buffer = [ch]
            self.state = "bogus_comment"
        else:
            # A bare '<' in text. Extremely common. Treat as literal.
            self._error("invalid first character of tag name")
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
            self._error("missing end tag name")
            self.state = "data"
        else:
            self._error("invalid first character of tag name")
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
            token = self._emit_tag()
            self.state = "data"
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
            self._error("unexpected = before attribute name")
            self._attr_name = [ch]
            self.state = "attribute_name"
        else:
            self._save_attr()
            self._attr_name = [ch.lower()]
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
            token = self._emit_tag()
            self.state = "data"
            yield token
        else:
            # Valueless attribute, e.g. <input disabled name="x">
            self._save_attr()
            self._attr_name = [ch.lower()]
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
            self._error("missing attribute value")
            token = self._emit_tag()
            self.state = "data"
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
            token = self._emit_tag()
            self.state = "data"
            yield token
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
            token = self._emit_tag()
            self.state = "data"
            yield token
        else:
            self._error("missing whitespace between attributes")
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
            token = self._emit_tag()
            self.state = "data"
            yield token
        else:
            self._error("unexpected solidus in tag")
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
        # Simplified: consume to '>', keep the first word as the name.
        chars: list[str] = []
        while True:
            ch = self._next()
            if ch is EOF:
                self._error("eof in doctype")
                self.state = "eof"
                break
            if ch == ">":
                self.state = "data"
                break
            chars.append(ch)
        raw = "".join(chars).strip()
        name = raw.split()[0].lower() if raw else None
        self.metrics["doctypes"] += 1
        yield DoctypeToken(name=name, force_quirks=(name != "html"))


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
