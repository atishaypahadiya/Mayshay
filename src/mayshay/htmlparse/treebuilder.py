"""
Simplified HTML tree construction.

Implements 8 of the spec's 23 insertion modes: initial, before_html,
before_head, in_head, after_head, in_body, text, after_body. Deliberately
absent, in rough order of when they will start to hurt:

1. The adoption agency algorithm (misnested formatting tags).
2. The table insertion modes and foster parenting.
3. Foreign content (SVG, MathML).
4. Templates, frames, select.

The scope predicate is written generally rather than as p/li special cases,
because every auto-closing rule in the spec -- including the table family --
is expressed through it.
"""

from __future__ import annotations

import time
from collections import Counter

from mayshay.dom.node import Comment, Document, DocumentType, Element, Text
from mayshay.htmlparse.tokenizer import (
    CharacterToken,
    CommentToken,
    DoctypeToken,
    EndTagToken,
    EOFToken,
    StartTagToken,
    Tokenizer,
    RAWTEXT_ELEMENTS,
    RCDATA_ELEMENTS,
    SCRIPT_ELEMENTS,
)

VOID_ELEMENTS = frozenset({
    "area", "base", "basefont", "bgsound", "br", "col", "embed", "frame",
    "hr", "img", "input", "keygen", "link", "meta", "param", "source",
    "track", "wbr",
})

HEAD_ELEMENTS = frozenset({
    "base", "basefont", "bgsound", "link", "meta", "noframes", "script",
    "style", "template", "title",
})

# Barriers for "has an element in scope". The spec's list also includes
# MathML/SVG integration points, which we skip until foreign content lands.
SCOPE_BARRIERS = frozenset({
    "applet", "caption", "html", "table", "td", "th", "marquee", "object",
})
BUTTON_SCOPE = SCOPE_BARRIERS | {"button"}
LIST_ITEM_SCOPE = SCOPE_BARRIERS | {"ol", "ul"}

IMPLIED_END_TAGS = frozenset({
    "dd", "dt", "li", "optgroup", "option", "p", "rb", "rp", "rt", "rtc",
})

# Start tags that close an open <p> before being inserted.
CLOSES_P = frozenset({
    "address", "article", "aside", "blockquote", "center", "details",
    "dialog", "dir", "div", "dl", "fieldset", "figcaption", "figure",
    "footer", "form", "h1", "h2", "h3", "h4", "h5", "h6", "header",
    "hgroup", "hr", "listing", "main", "menu", "nav", "ol", "p", "plaintext",
    "pre", "section", "summary", "table", "ul",
})


class TreeBuilder:
    def __init__(self, source: str) -> None:
        self.source = source
        self.tokenizer = Tokenizer(source)
        self.document = Document()
        self.open_elements: list[Element] = []
        self.mode = "initial"
        self.original_mode = "in_body"
        self.head: Element | None = None
        self.metrics: Counter[str] = Counter()

    # -- stack helpers -----------------------------------------------------

    @property
    def current(self) -> Element | None:
        return self.open_elements[-1] if self.open_elements else None

    def _insertion_point(self):
        return self.current if self.open_elements else self.document

    def has_element_in_scope(self, target: str, barriers=SCOPE_BARRIERS) -> bool:
        for el in reversed(self.open_elements):
            if el.tag_name == target:
                return True
            if el.tag_name in barriers:
                return False
        return False

    def generate_implied_end_tags(self, *, excluding: str | None = None) -> None:
        while (
            self.current is not None
            and self.current.tag_name in IMPLIED_END_TAGS
            and self.current.tag_name != excluding
        ):
            self.open_elements.pop()

    def close_p_element(self) -> None:
        self.generate_implied_end_tags(excluding="p")
        while self.open_elements:
            if self.open_elements.pop().tag_name == "p":
                break

    def pop_until(self, name: str) -> None:
        while self.open_elements:
            if self.open_elements.pop().tag_name == name:
                break

    # -- insertion ---------------------------------------------------------

    def insert_element(self, token: StartTagToken) -> Element:
        el = Element(token.name, token.attrs)
        self._insertion_point().append_child(el)
        self.metrics["elements"] += 1
        if token.name not in VOID_ELEMENTS:
            self.open_elements.append(el)
            self.metrics["max_depth"] = max(
                self.metrics["max_depth"], len(self.open_elements)
            )
        return el

    def insert_text(self, data: str) -> None:
        point = self._insertion_point()
        # Merge with a trailing text node rather than fragmenting the tree.
        if point.children and isinstance(point.children[-1], Text):
            point.children[-1].data += data
        else:
            point.append_child(Text(data))
            self.metrics["text_nodes"] += 1

    def insert_raw_text_element(self, token: StartTagToken, state: str) -> None:
        """Generic RAWTEXT/RCDATA element parsing: the tree builder drives
        the tokenizer, which is why Tokenizer.switch_to exists."""
        self.insert_element(token)
        self.tokenizer.switch_to(state, last_start_tag=token.name)
        self.original_mode = self.mode
        self.mode = "text"

    # -- driver ------------------------------------------------------------

    def build(self) -> Document:
        started = time.perf_counter()
        for token in self.tokenizer.tokenize():
            self.dispatch(token)
            if isinstance(token, EOFToken):
                break
        self.metrics["parse_time_ms"] = int(
            (time.perf_counter() - started) * 1000
        )
        self.metrics["parse_errors"] = self.tokenizer.metrics["parse_errors"]
        return self.document

    def dispatch(self, token) -> None:
        getattr(self, f"_mode_{self.mode}")(token)

    def _is_space(self, token) -> bool:
        return isinstance(token, CharacterToken) and not token.data.strip()

    # -- insertion modes ---------------------------------------------------

    def _mode_initial(self, token) -> None:
        if isinstance(token, DoctypeToken):
            self.document.append_child(DocumentType(token.name or "html"))
            self.document.quirks_mode = token.force_quirks
            self.mode = "before_html"
        elif isinstance(token, CommentToken):
            self.document.append_child(Comment(token.data))
        elif self._is_space(token):
            pass
        else:
            self.document.quirks_mode = True
            self.mode = "before_html"
            self.dispatch(token)

    def _mode_before_html(self, token) -> None:
        if isinstance(token, CommentToken):
            self.document.append_child(Comment(token.data))
        elif self._is_space(token):
            pass
        elif isinstance(token, StartTagToken) and token.name == "html":
            self.insert_element(token)
            self.mode = "before_head"
        else:
            self.insert_element(StartTagToken("html"))
            self.mode = "before_head"
            self.dispatch(token)

    def _mode_before_head(self, token) -> None:
        if isinstance(token, CommentToken):
            self._insertion_point().append_child(Comment(token.data))
        elif self._is_space(token):
            pass
        elif isinstance(token, StartTagToken) and token.name == "head":
            self.head = self.insert_element(token)
            self.mode = "in_head"
        else:
            self.head = self.insert_element(StartTagToken("head"))
            self.mode = "in_head"
            self.dispatch(token)

    def _mode_in_head(self, token) -> None:
        if self._is_space(token):
            self.insert_text(token.data)
        elif isinstance(token, CommentToken):
            self._insertion_point().append_child(Comment(token.data))
        elif isinstance(token, StartTagToken) and token.name in RCDATA_ELEMENTS:
            self.insert_raw_text_element(token, "rcdata")
        elif isinstance(token, StartTagToken) and token.name in RAWTEXT_ELEMENTS:
            self.insert_raw_text_element(token, "rawtext")
        elif isinstance(token, StartTagToken) and token.name in SCRIPT_ELEMENTS:
            self.insert_raw_text_element(token, "script_data")
        elif isinstance(token, StartTagToken) and token.name in HEAD_ELEMENTS:
            self.insert_element(token)
        elif isinstance(token, EndTagToken) and token.name == "head":
            self.pop_until("head")
            self.mode = "after_head"
        else:
            self.pop_until("head")
            self.mode = "after_head"
            self.dispatch(token)

    def _mode_after_head(self, token) -> None:
        if self._is_space(token):
            self.insert_text(token.data)
        elif isinstance(token, CommentToken):
            self._insertion_point().append_child(Comment(token.data))
        elif isinstance(token, StartTagToken) and token.name == "body":
            self.insert_element(token)
            self.mode = "in_body"
        else:
            self.insert_element(StartTagToken("body"))
            self.mode = "in_body"
            self.dispatch(token)

    def _mode_in_body(self, token) -> None:
        if isinstance(token, CharacterToken):
            self.insert_text(token.data)
        elif isinstance(token, CommentToken):
            self._insertion_point().append_child(Comment(token.data))
        elif isinstance(token, StartTagToken):
            self._in_body_start(token)
        elif isinstance(token, EndTagToken):
            self._in_body_end(token)
        elif isinstance(token, EOFToken):
            self.mode = "after_body"

    def _in_body_start(self, token: StartTagToken) -> None:
        name = token.name
        if name in RCDATA_ELEMENTS:
            self.insert_raw_text_element(token, "rcdata")
        elif name in RAWTEXT_ELEMENTS:
            self.insert_raw_text_element(token, "rawtext")
        elif name in SCRIPT_ELEMENTS:
            self.insert_raw_text_element(token, "script_data")
        elif name == "li":
            if self.has_element_in_scope("li", LIST_ITEM_SCOPE):
                self.generate_implied_end_tags(excluding="li")
                self.pop_until("li")
            if self.has_element_in_scope("p", BUTTON_SCOPE):
                self.close_p_element()
            self.insert_element(token)
        elif name in ("dd", "dt"):
            for tag in ("dd", "dt"):
                if self.has_element_in_scope(tag):
                    self.generate_implied_end_tags(excluding=tag)
                    self.pop_until(tag)
                    break
            if self.has_element_in_scope("p", BUTTON_SCOPE):
                self.close_p_element()
            self.insert_element(token)
        elif name in CLOSES_P:
            if self.has_element_in_scope("p", BUTTON_SCOPE):
                self.close_p_element()
            self.insert_element(token)
        else:
            self.insert_element(token)

    def _in_body_end(self, token: EndTagToken) -> None:
        name = token.name
        if name == "p":
            if not self.has_element_in_scope("p", BUTTON_SCOPE):
                # Spec: parse error, then insert an empty <p> and close it.
                self.insert_element(StartTagToken("p"))
            self.close_p_element()
        elif name == "body":
            self.mode = "after_body"
        elif name == "html":
            self.mode = "after_body"
            self.dispatch(token)
        elif self.has_element_in_scope(name):
            self.generate_implied_end_tags(excluding=name)
            self.pop_until(name)
        # An end tag with nothing matching in scope is ignored.

    def _mode_text(self, token) -> None:
        if isinstance(token, CharacterToken):
            self.insert_text(token.data)
        elif isinstance(token, EndTagToken):
            self.open_elements.pop()
            self.mode = self.original_mode
        elif isinstance(token, EOFToken):
            self.open_elements.pop()
            self.mode = self.original_mode
            self.dispatch(token)

    def _mode_after_body(self, token) -> None:
        if isinstance(token, CommentToken):
            self.document.append_child(Comment(token.data))
        elif isinstance(token, EOFToken):
            pass
        elif self._is_space(token):
            pass
        elif isinstance(token, EndTagToken) and token.name == "html":
            # The spec switches to "after after body" here. We have no such
            # mode, and staying put is behaviourally identical for the token
            # kinds we handle. Reprocessing would bounce straight back to
            # _in_body_end, which routes </html> to after_body -- an infinite
            # recursion; 11 tests1.dat cases crashed on exactly that.
            pass
        else:
            self.mode = "in_body"
            self.dispatch(token)


def parse(source: str) -> Document:
    return TreeBuilder(source).build()
