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
    # xmp belongs here even though it is a raw-text element: the spec's in-body
    # xmp rule closes an open p *before* the generic raw text algorithm runs.
    # textarea, iframe and noembed deliberately do NOT close a p.
    "xmp",
})

# The spec's "special" category. Its only job here is the "any other end tag"
# algorithm: that stack walk must stop dead at a special element instead of
# popping through it, which is why </span> cannot escape an open <button>.
# The MathML/SVG members are omitted along with the rest of foreign content.
SPECIAL_ELEMENTS = frozenset({
    "address", "applet", "area", "article", "aside", "base", "basefont",
    "bgsound", "blockquote", "body", "br", "button", "caption", "center",
    "col", "colgroup", "dd", "details", "dir", "div", "dl", "dt", "embed",
    "fieldset", "figcaption", "figure", "footer", "form", "frame", "frameset",
    "h1", "h2", "h3", "h4", "h5", "h6", "head", "header", "hgroup", "hr",
    "html", "iframe", "img", "input", "keygen", "li", "link", "listing",
    "main", "marquee", "menu", "meta", "nav", "noembed", "noframes",
    "noscript", "object", "ol", "p", "param", "plaintext", "pre", "script",
    "search", "section", "select", "source", "style", "summary", "table",
    "tbody", "td", "template", "textarea", "tfoot", "th", "thead", "title",
    "tr", "track", "ul", "wbr", "xmp",
})

HEADINGS = frozenset({"h1", "h2", "h3", "h4", "h5", "h6"})

# End tags the spec closes with an explicit scope check rather than with the
# "any other end tag" stack walk. Keeping them separate is load-bearing: the
# stack walk aborts on a special element, so routing </div> through it would
# make <div><p>x</div> ignore the </div> instead of closing the div.
CLOSES_IN_SCOPE = frozenset({
    "address", "applet", "article", "aside", "blockquote", "button", "center",
    "details", "dialog", "dir", "div", "dl", "fieldset", "figcaption",
    "figure", "footer", "form", "header", "hgroup", "listing", "main",
    "marquee", "menu", "nav", "object", "ol", "pre", "search", "section",
    "summary", "ul",
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

    def has_any_element_in_scope(self, targets, barriers=SCOPE_BARRIERS) -> bool:
        """Scope predicate over a set of names -- the h1..h6 family needs it."""
        for el in reversed(self.open_elements):
            if el.tag_name in targets:
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

    @staticmethod
    def raw_text_state(name: str) -> str | None:
        """The tokenizer state `name` demands, or None if it is not raw text."""
        if name in RCDATA_ELEMENTS:
            return "rcdata"
        if name in RAWTEXT_ELEMENTS:
            return "rawtext"
        if name in SCRIPT_ELEMENTS:
            return "script_data"
        return None

    def insert_raw_text_element(self, token: StartTagToken, state: str) -> None:
        """Generic RAWTEXT/RCDATA element parsing: the tree builder drives
        the tokenizer, which is why Tokenizer.switch_to exists."""
        self.insert_element(token)
        self.tokenizer.switch_to(state, last_start_tag=token.name)
        self.original_mode = self.mode
        self.mode = "text"

    def insert_element_maybe_raw_text(self, token: StartTagToken) -> None:
        """Insert `token`, then apply raw-text tokenization if it needs it.

        Needing RCDATA/RAWTEXT/ScriptData tokenization is a *consequence* of
        inserting an element, never a precondition that lets it skip the
        insertion mode's own rules. Dispatching on it first is what used to
        promote <textarea> into <head> and stop <xmp> closing an open <p>.
        """
        state = self.raw_text_state(token.name)
        if state is None:
            self.insert_element(token)
        else:
            self.insert_raw_text_element(token, state)

    # -- driver ------------------------------------------------------------

    def build(self) -> Document:
        started = time.perf_counter()
        for token in self.tokenizer.tokenize():
            self.dispatch(token)
            if isinstance(token, EOFToken):
                break
        # Not int(): almost every parse we do finishes in well under a
        # millisecond, and a timing metric that always reads 0 is not a
        # timing metric. Microsecond resolution, still expressed in ms.
        self.metrics["parse_time_ms"] = round(
            (time.perf_counter() - started) * 1000, 3
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
        elif isinstance(token, StartTagToken) and token.name in HEAD_ELEMENTS:
            # title/style/script/noframes get raw-text tokenization *because*
            # they are head elements, not instead of being checked against the
            # head element list. textarea, xmp, iframe and noembed are raw text
            # but are NOT head elements, so they fall through to the else branch
            # below, close <head>, and are handled in body where they belong.
            self.insert_element_maybe_raw_text(token)
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
        """Auto-closing rules first, then one insertion for every path.

        The raw-text elements used to be dispatched ahead of all of this, which
        meant <xmp> never closed an open <p>. Raw-text tokenization is applied
        by insert_element_maybe_raw_text at the end, after the mode has had its
        say -- which is the order the spec uses.
        """
        name = token.name
        if name == "li":
            if self.has_element_in_scope("li", LIST_ITEM_SCOPE):
                self.generate_implied_end_tags(excluding="li")
                self.pop_until("li")
            if self.has_element_in_scope("p", BUTTON_SCOPE):
                self.close_p_element()
        elif name in ("dd", "dt"):
            for tag in ("dd", "dt"):
                if self.has_element_in_scope(tag):
                    self.generate_implied_end_tags(excluding=tag)
                    self.pop_until(tag)
                    break
            if self.has_element_in_scope("p", BUTTON_SCOPE):
                self.close_p_element()
        elif name in CLOSES_P:
            if self.has_element_in_scope("p", BUTTON_SCOPE):
                self.close_p_element()
        self.insert_element_maybe_raw_text(token)

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
        elif name == "li":
            # List-item scope, not the default barriers: inside a nested <ul>
            # a stray </li> must NOT reach out and close the enclosing <li>.
            if self.has_element_in_scope("li", LIST_ITEM_SCOPE):
                self.generate_implied_end_tags(excluding="li")
                self.pop_until("li")
        elif name in ("dd", "dt"):
            if self.has_element_in_scope(name):
                self.generate_implied_end_tags(excluding=name)
                self.pop_until(name)
        elif name in HEADINGS:
            # Any open heading closes any other: </h2> closes an open <h1>.
            if self.has_any_element_in_scope(HEADINGS):
                self.generate_implied_end_tags()
                while self.open_elements:
                    if self.open_elements.pop().tag_name in HEADINGS:
                        break
        elif name in CLOSES_IN_SCOPE:
            if self.has_element_in_scope(name):
                self.generate_implied_end_tags(excluding=name)
                self.pop_until(name)
        else:
            self._any_other_end_tag(token)
        # An end tag with nothing matching in scope is ignored.

    def _any_other_end_tag(self, token: EndTagToken) -> None:
        """The spec's "any other end tag" step.

        Walk the stack from the top. A matching element closes normally; a
        *special* element met first is a hard stop and the token is dropped.
        This is deliberately not a scope check -- the barrier is the whole
        special category, which is what keeps "bar" inside the button in
        <span><button>foo</span>bar.
        """
        for index in range(len(self.open_elements) - 1, -1, -1):
            node = self.open_elements[index]
            if node.tag_name == token.name:
                self.generate_implied_end_tags(excluding=token.name)
                # generate_implied_end_tags stops at node (it is excluded), so
                # the stack is still at least index + 1 deep here.
                while len(self.open_elements) > index:
                    self.open_elements.pop()
                return
            if node.tag_name in SPECIAL_ELEMENTS:
                return  # parse error; ignore the token

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
