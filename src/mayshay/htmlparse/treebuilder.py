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
    "pre", "search", "section", "summary", "table", "ul",
    # `plaintext` is listed because this set is kept spec-correct, but be aware
    # it cannot fire end to end: the tokenizer has no PLAINTEXT state and no
    # <plaintext> start tag switches into one (tokenizer deviation #7), so the
    # rest of the document after <plaintext> is still tokenized as data. The
    # p-closing half works; the feature does not. Same caveat in
    # SPECIAL_ELEMENTS below.
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
    # `plaintext` here has the same caveat as in CLOSES_P: spec-correct set,
    # no tokenizer support behind it (tokenizer deviation #7).
    "noscript", "object", "ol", "p", "param", "plaintext", "pre", "script",
    "search", "section", "select", "source", "style", "summary", "table",
    "tbody", "td", "template", "textarea", "tfoot", "th", "thead", "title",
    "tr", "track", "ul", "wbr", "xmp",
})

# The spec's "in body" EOF rule is not "anything still open is an error": it
# names the elements that may legitimately still be open at EOF and reports a
# parse error only for anything else. An unclosed <p> or <li> is normal; an
# unclosed <div> is not. Getting this wrong made <p>One<p>Two report an error
# html5lib does not.
EOF_OK_OPEN = frozenset({
    "dd", "dt", "li", "optgroup", "option", "p", "rb", "rp", "rt", "rtc",
    "tbody", "td", "tfoot", "th", "thead", "tr", "body", "html",
})

HEADINGS = frozenset({"h1", "h2", "h3", "h4", "h5", "h6"})

# The spec's formatting elements. These are the ones tracked on the list of
# active formatting elements and re-opened by reconstruction.
FORMATTING_ELEMENTS = frozenset({
    "a", "b", "big", "code", "em", "font", "i", "nobr", "s", "small",
    "strike", "strong", "tt", "u",
})

# Elements that push a scope marker onto the formatting list: reconstruction
# never crosses one, so <b><object>x</object> does not re-open the b inside.
FORMATTING_MARKER_ELEMENTS = frozenset({"applet", "marquee", "object"})

# In-body start tags whose spec rule does NOT begin by reconstructing the
# active formatting elements. Everything else -- the "any other start tag"
# catch-all included -- does. Reconstructing for a block element would be
# actively wrong: <p><b>a<p> must not re-open <b> around the second <p>.
NO_RECONSTRUCT_START = HEAD_ELEMENTS | frozenset({
    "html", "body", "head", "frame", "frameset",
    "caption", "col", "colgroup", "tbody", "tfoot", "thead", "td", "th", "tr",
    "param", "source", "track",
    # noscript is absent deliberately: this parser models scripting as
    # disabled, so <noscript> is an ordinary element that falls to the
    # "any other start tag" catch-all -- which reconstructs.
    "textarea", "iframe", "noembed",
    "rb", "rp", "rt", "rtc",
})

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

# The html5lib `#errors` vocabulary, restricted to what the eight implemented
# insertion modes can actually produce. The corpus carries 469 distinct codes;
# most concern tables, foreign content and select, which are not implemented.
# A code recorded outside this set means the mapping has drifted.
TREE_ERROR_CODES = frozenset({
    "expected-doctype-but-got-start-tag",
    "expected-doctype-but-got-chars",
    "expected-doctype-but-got-eof",
    # Not "...-but-got-comment": a comment in "initial" is inserted, not an
    # error, and that code does not occur anywhere in the corpus. The only
    # token that reaches the fall-through is an end tag.
    "expected-doctype-but-got-end-tag",
    "unexpected-doctype",
    "unexpected-start-tag",
    "unexpected-end-tag",
    "unexpected-end-tag-before-html",
    "expected-closing-tag-but-got-eof",
    "expected-one-end-tag-but-got-another",
    "end-tag-too-early",
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
        # None entries are scope markers (inserted by applet/object/marquee
        # and, once they exist, the table modes). Reconstruction never
        # crosses one.
        self.active_formatting: list[Element | None] = []
        # Mirrors Tokenizer.errors. Positions follow the same convention: the
        # offset points AT the token that caused the error, which is the
        # token's own `pos`.
        self.errors: list[tuple[int, str]] = []
        # Set by _mode_after_head to the token whose fall-through synthesised
        # the <body>. That token is one the spec would have handled in "after
        # head", so in-body parse-error rules the spec does not apply there
        # must not fire for it. Today only <frameset> is affected: it is
        # legitimate in "after head" and a parse error in "in body".
        self._after_head_fallthrough: object | None = None
        self.metrics: Counter[str] = Counter()

    # -- parse errors ------------------------------------------------------

    def _error(self, code: str, pos: int) -> None:
        self.errors.append((pos, code))
        self.metrics["parse_errors"] += 1

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

    def close_p_element(self, pos: int) -> None:
        """The spec's "close a p element" algorithm.

        The parse error lives *in the algorithm*, not at the </p> rule, which
        is why an implied close -- <p><b><div> -- reports it too. `pos` is the
        offset of the token that triggered the close.
        """
        self.generate_implied_end_tags(excluding="p")
        if self.current is None or self.current.tag_name != "p":
            self._error("unexpected-end-tag", pos)
        while self.open_elements:
            if self.open_elements.pop().tag_name == "p":
                break

    def pop_until(self, name: str) -> None:
        while self.open_elements:
            if self.open_elements.pop().tag_name == name:
                break

    # -- active formatting elements ---------------------------------------

    def push_formatting(self, el: Element) -> None:
        """Add `el` to the list, honouring the Noah's Ark clause."""
        # Noah's Ark: at most three entries with the same tag name and the
        # same attributes may appear after the last marker. The fourth
        # evicts the *earliest* of the three, not the latest.
        matches: list[Element] = []
        for entry in reversed(self.active_formatting):
            if entry is None:
                break
            if entry.tag_name == el.tag_name and entry.attrs == el.attrs:
                matches.append(entry)
        if len(matches) >= 3:
            self.active_formatting.remove(matches[-1])
        self.active_formatting.append(el)

    def push_formatting_marker(self) -> None:
        self.active_formatting.append(None)

    def clear_formatting_to_marker(self) -> None:
        while self.active_formatting:
            if self.active_formatting.pop() is None:
                break

    def remove_formatting(self, el: Element) -> None:
        """Drop `el` from the list if it is on it (identity, not equality)."""
        for index, entry in enumerate(self.active_formatting):
            if entry is el:
                del self.active_formatting[index]
                return

    def last_formatting(self, name: str) -> Element | None:
        """The most recent entry named `name` after the last marker."""
        for entry in reversed(self.active_formatting):
            if entry is None:
                return None
            if entry.tag_name == name:
                return entry
        return None

    def reconstruct_formatting(self) -> None:
        """
        Re-open formatting elements that are on the list but no longer on the
        open-elements stack. This is what makes <p><b>one<p>two render `two`
        in bold. It is NOT the adoption agency algorithm.
        """
        if not self.active_formatting:
            return
        last = self.active_formatting[-1]
        if last is None or any(el is last for el in self.open_elements):
            return

        index = len(self.active_formatting) - 1
        while index > 0:
            candidate = self.active_formatting[index - 1]
            if candidate is None or any(
                el is candidate for el in self.open_elements
            ):
                break
            index -= 1

        while index < len(self.active_formatting):
            entry = self.active_formatting[index]
            clone = Element(entry.tag_name, entry.attrs)
            self._insertion_point().append_child(clone)
            self.open_elements.append(clone)
            self.metrics["elements"] += 1
            self.metrics["max_depth"] = max(
                self.metrics["max_depth"], len(self.open_elements)
            )
            # Rewriting the entry in place is what stops the next call
            # re-cloning the same element forever: the list now points at a
            # node that is on the stack.
            self.active_formatting[index] = clone
            index += 1

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
        """Generic RAWTEXT/RCDATA element parsing.

        Only `self.mode = "text"` does any work today. The `switch_to` call is
        currently inert: `Tokenizer._emit_tag` already set the same state and
        the same last-start-tag from the same three frozensets before this
        token was ever dispatched. Measured over all 1592 tree-construction
        corpus cases: 354 calls from here, 0 that changed either field.

        The call stays because the spec puts this decision in the tree builder
        precisely because it is contextual, and the first contextual case --
        foreign content, where <svg><title> must NOT become RCDATA -- will need
        the tokenizer to stop deciding for itself. Retiring `_emit_tag`'s
        unilateral switch is the phase-2 half of that; see Tokenizer.switch_to.
        """
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
        # The tokenizer's count, kept distinct from our own. Before this was
        # split, a page with only tree-construction errors reported zero.
        self.metrics["tokenizer_parse_errors"] = self.tokenizer.metrics["parse_errors"]
        return self.document

    def dispatch(self, token) -> None:
        getattr(self, f"_mode_{self.mode}")(token)

    def _is_space(self, token) -> bool:
        return isinstance(token, CharacterToken) and not token.data.strip()

    # -- insertion modes ---------------------------------------------------

    def _mode_initial(self, token) -> None:
        if isinstance(token, DoctypeToken):
            self.document.append_child(DocumentType(token.name or "html"))
            # The quirks-mode *decision* lives here, not in the tokenizer.
            # DoctypeToken.force_quirks is only the spec's force-quirks error
            # flag (eof-in-doctype, missing name); the "initial" insertion mode
            # additionally puts the document in quirks mode when the name is
            # anything but "html", or when the public/system identifier matches
            # one of the spec's quirky lists. That last clause is unimplemented:
            # the tokenizer discards the identifiers (tokenizer deviation #3),
            # so identifier-driven quirks is a documented gap, not an oversight.
            self.document.quirks_mode = token.force_quirks or token.name != "html"
            self.mode = "before_html"
        elif isinstance(token, CommentToken):
            self.document.append_child(Comment(token.data))
        elif self._is_space(token):
            pass
        else:
            if isinstance(token, StartTagToken):
                self._error("expected-doctype-but-got-start-tag", token.pos)
            elif isinstance(token, CharacterToken):
                self._error("expected-doctype-but-got-chars", token.pos)
            elif isinstance(token, EOFToken):
                self._error("expected-doctype-but-got-eof", token.pos)
            else:
                # Doctype, comment, whitespace, start tag, characters and EOF
                # are all handled above, so this is an end tag and nothing else.
                self._error("expected-doctype-but-got-end-tag", token.pos)
            self.document.quirks_mode = True
            self.mode = "before_html"
            self.dispatch(token)

    def _mode_before_html(self, token) -> None:
        if isinstance(token, DoctypeToken):
            self._error("unexpected-doctype", token.pos)
            return
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
        if isinstance(token, DoctypeToken):
            self._error("unexpected-doctype", token.pos)
            return
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
        if isinstance(token, DoctypeToken):
            self._error("unexpected-doctype", token.pos)
            return
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
        if isinstance(token, DoctypeToken):
            self._error("unexpected-doctype", token.pos)
            return
        if self._is_space(token):
            self.insert_text(token.data)
        elif isinstance(token, CommentToken):
            self._insertion_point().append_child(Comment(token.data))
        elif isinstance(token, StartTagToken) and token.name == "body":
            self.insert_element(token)
            self.mode = "in_body"
        else:
            self._after_head_fallthrough = token
            self.insert_element(StartTagToken("body"))
            self.mode = "in_body"
            self.dispatch(token)
            self._after_head_fallthrough = None

    def _mode_in_body(self, token) -> None:
        if isinstance(token, DoctypeToken):
            self._error("unexpected-doctype", token.pos)
            return
        if isinstance(token, CharacterToken):
            self.reconstruct_formatting()
            self.insert_text(token.data)
        elif isinstance(token, CommentToken):
            self._insertion_point().append_child(Comment(token.data))
        elif isinstance(token, StartTagToken):
            self._in_body_start(token)
        elif isinstance(token, EndTagToken):
            self._in_body_end(token)
        elif isinstance(token, EOFToken):
            for element in self.open_elements:
                if element.tag_name not in EOF_OK_OPEN:
                    self._error("expected-closing-tag-but-got-eof", token.pos)
                    break
            self.mode = "after_body"

    def _in_body_start(self, token: StartTagToken) -> None:
        """Auto-closing rules first, then one insertion for every path.

        The raw-text elements used to be dispatched ahead of all of this, which
        meant <xmp> never closed an open <p>. Raw-text tokenization is applied
        by insert_element_maybe_raw_text at the end, after the mode has had its
        say -- which is the order the spec uses.
        """
        name = token.name
        # Spec: <body> and <frameset> start tags in "in body" are parse errors
        # (the spec then merges body's attributes, or replaces the body with
        # the frameset). Only the errors are recorded here; the repairs, and
        # the other in-body start-tag parse errors -- html, head, form with the
        # form pointer set -- wait on rules this parser does not implement.
        #
        # <frameset> is only an error when the spec would really be in "in
        # body" for it. Two of its own modes, both unimplemented here, would
        # have taken the token first and neither treats it as an error:
        # "after head" (a document that opens with <frameset>, which reaches
        # us via _mode_after_head's fall-through) and "in frameset" (a nested
        # <frameset>, recognisable by one already being on the stack).
        # Reporting those would invent errors html5lib does not report.
        if name == "body" or (name == "frameset" and self._frameset_in_body(token)):
            self._error("unexpected-start-tag", token.pos)
        reconstruct = name not in NO_RECONSTRUCT_START
        if name == "li":
            if self.has_element_in_scope("li", LIST_ITEM_SCOPE):
                self.generate_implied_end_tags(excluding="li")
                self.pop_until("li")
            if self.has_element_in_scope("p", BUTTON_SCOPE):
                self.close_p_element(token.pos)
            reconstruct = False
        elif name in ("dd", "dt"):
            for tag in ("dd", "dt"):
                if self.has_element_in_scope(tag):
                    self.generate_implied_end_tags(excluding=tag)
                    self.pop_until(tag)
                    break
            if self.has_element_in_scope("p", BUTTON_SCOPE):
                self.close_p_element(token.pos)
            reconstruct = False
        elif name in CLOSES_P:
            if self.has_element_in_scope("p", BUTTON_SCOPE):
                self.close_p_element(token.pos)
            # Spec: a heading start tag while a heading is the current node is
            # a parse error (and the spec pops it -- we do not, which is the
            # nesting bug test_html5lib_tree already tracks). Recording it is
            # the honest half; the repair belongs to a tree-construction task.
            if name in HEADINGS and self.current is not None:
                if self.current.tag_name in HEADINGS:
                    self._error("unexpected-start-tag", token.pos)
            # xmp is the one p-closing element whose rule reconstructs; the
            # rest (div, table, h1..h6, hr, form, pre, ...) do not.
            reconstruct = name == "xmp"

        if reconstruct:
            self.reconstruct_formatting()

        if name in FORMATTING_ELEMENTS:
            self.push_formatting(self.insert_element(token))
        elif name in FORMATTING_MARKER_ELEMENTS:
            self.insert_element(token)
            self.push_formatting_marker()
        else:
            self.insert_element_maybe_raw_text(token)

    def _frameset_in_body(self, token: StartTagToken) -> bool:
        """True when a <frameset> start tag really is an in-body parse error."""
        if token is self._after_head_fallthrough:
            return False  # the spec's "after head" frameset case
        return not any(el.tag_name == "frameset" for el in self.open_elements)

    def _in_body_end(self, token: EndTagToken) -> None:
        name = token.name
        if name == "p":
            if not self.has_element_in_scope("p", BUTTON_SCOPE):
                # Spec: parse error, then insert an empty <p> and close it.
                # (The inserted p makes close_p_element's own check pass, so
                # this error is not a duplicate of that one.)
                self._error("unexpected-end-tag", token.pos)
                self.insert_element(StartTagToken("p"))
            self.close_p_element(token.pos)
        elif name == "body":
            self.mode = "after_body"
        elif name == "html":
            self.mode = "after_body"
            self.dispatch(token)
        elif name == "li":
            # List-item scope, not the default barriers: inside a nested <ul>
            # a stray </li> must NOT reach out and close the enclosing <li>.
            if not self.has_element_in_scope("li", LIST_ITEM_SCOPE):
                self._error("unexpected-end-tag", token.pos)
            else:
                self.generate_implied_end_tags(excluding="li")
                if self.current is not None and self.current.tag_name != "li":
                    self._error("end-tag-too-early", token.pos)
                self.pop_until("li")
        elif name in ("dd", "dt"):
            if not self.has_element_in_scope(name):
                self._error("unexpected-end-tag", token.pos)
            else:
                self.generate_implied_end_tags(excluding=name)
                if self.current is not None and self.current.tag_name != name:
                    self._error("end-tag-too-early", token.pos)
                self.pop_until(name)
        elif name in HEADINGS:
            # Any open heading closes any other: </h2> closes an open <h1>.
            #
            # This is the block shape, not the list-item shape: one error,
            # `end-tag-too-early`, reported whenever the current node is not
            # the element named by the tag -- including when no heading is in
            # scope at all. See the note on CLOSES_IN_SCOPE below for why the
            # two families genuinely differ rather than one being wrong.
            in_scope = self.has_any_element_in_scope(HEADINGS)
            if in_scope:
                self.generate_implied_end_tags()
            if self.current is None or self.current.tag_name != name:
                self._error("end-tag-too-early", token.pos)
            if in_scope:
                while self.open_elements:
                    if self.open_elements.pop().tag_name in HEADINGS:
                        break
        elif name in FORMATTING_ELEMENTS:
            # The adoption agency algorithm minus the repair itself. Its
            # early-exit steps are all here, in spec order, so landing the
            # real thing later is an insertion rather than a rewrite:
            #
            #   4.3  not on the list          -> "any other end tag"
            #   4.4  on the list, off the stack -> drop the entry
            #   4.5  on the stack, out of scope -> parse error, KEEP the entry
            #   4.7  no furthest block        -> pop to it, drop the entry
            #
            # Step 4.5 keeping the entry is load-bearing: <b><table></b>x
            # must still reconstruct the <b> around "x". What is missing is
            # only the furthest-block case, where we over-pop instead of
            # reparenting -- see test_misnested_formatting_tags.
            entry = self.last_formatting(name)
            if entry is None:
                self._any_other_end_tag(token)
            elif not any(el is entry for el in self.open_elements):
                self.remove_formatting(entry)
            elif not self.has_element_in_scope(name):
                pass
            else:
                self.remove_formatting(entry)
                self.generate_implied_end_tags(excluding=name)
                self.pop_until(name)
        elif name in CLOSES_IN_SCOPE:
            # One parse error covers both failure shapes here, which is the
            # vocabulary's own shape: `end-tag-too-early` is reported whenever
            # the current node is not the element being closed, whether that
            # is because something is still open inside it or because it is
            # not in scope at all. There is no separate not-in-scope code for
            # this family.
            #
            # This looks asymmetric next to </li>, </dd> and </dt> above, which
            # DO report `unexpected-end-tag` when nothing is in scope. The
            # asymmetry is in the vocabulary, not here: the block family and
            # the heading family gate only the *repair* on the scope check and
            # report one code unconditionally, while the list-item family
            # branches on scope and reports two. Flattening either family to
            # match the other produces codes the corpus does not expect.
            in_scope = self.has_element_in_scope(name)
            if in_scope:
                self.generate_implied_end_tags(excluding=name)
            if self.current is None or self.current.tag_name != name:
                self._error("end-tag-too-early", token.pos)
            if in_scope:
                self.pop_until(name)
                if name in FORMATTING_MARKER_ELEMENTS:
                    self.clear_formatting_to_marker()
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
                self._error("unexpected-end-tag", token.pos)
                return  # parse error; ignore the token

    def _mode_text(self, token) -> None:
        if isinstance(token, CharacterToken):
            self.insert_text(token.data)
        elif isinstance(token, EndTagToken):
            self.open_elements.pop()
            self.mode = self.original_mode
        elif isinstance(token, EOFToken):
            self._error("expected-closing-tag-but-got-eof", token.pos)
            self.open_elements.pop()
            self.mode = self.original_mode
            self.dispatch(token)

    def _mode_after_body(self, token) -> None:
        if isinstance(token, DoctypeToken):
            self._error("unexpected-doctype", token.pos)
            return
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
