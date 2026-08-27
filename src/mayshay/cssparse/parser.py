"""
Mayshay CSS generic grammar.

A hand-rolled implementation of CSS Syntax Level 3 section 5, "Parsing":
https://www.w3.org/TR/css-syntax-3/#parsing

This layer turns a `CssTokenizer` token stream into rules and declarations.
It deliberately knows nothing about selectors or property values -- a
qualified rule's prelude and a declaration's value both stay plain
`list[CssToken]`, for Task G (selectors) and Task I (value parsing) to
interpret later. The point of this layer is error recovery: the spec never
fails to parse a stylesheet, it recovers from malformed input one rule or
one declaration at a time, and that recovery is what `CssParser` implements.

Implemented, section 5's parser algorithms: consume a list of rules (5.5.1),
consume an at-rule (5.5.2), consume a qualified rule (5.5.3), consume a list
of declarations (5.5.4), consume a declaration (5.5.5), consume a component
value (5.5.6), consume a simple block (5.5.7), consume a function (5.5.8).
`parse_stylesheet` is the "parse a stylesheet" entry point (5.3.3); the
`parse_declarations` entry point corresponds to "parse a list of
declarations" (5.3.6), except it is handed an already-tokenized list rather
than a string, because its only caller in this codebase is code that already
has a rule's `block`.

Deliberate deviations from the spec, documented so they don't surprise us
later:

1. **Component values are represented as flat token lists, not the spec's
   tree of preserved-token / function / simple-block objects.** 5.5.6-5.5.8
   are collapsed into `_consume_component_value`, which still recurses to
   find the matching `)`/`]`/`}` for a function or bracketed group -- nested
   braces are matched correctly, not scanned past with a naive `find` -- but
   the result it returns is the flat run of tokens for that one component
   value, delimiters included. Nothing in this brief needs the tree: Task G
   and Task I can both re-derive nesting from the token stream, because the
   matching brackets are still present, verbatim, in the flat list.

   Note, not a further deviation: `AtRule.block` / `QualifiedRule.block`
   hold the block's contents only -- the tokens between, but not including,
   the outer `{`/`}`. That matches the spec as written: a simple block's
   `value` is defined as its *contents*, with the associated start/end
   tokens kept separately. The asymmetry with (1)'s nested groups, which do
   keep their own delimiters, is just `_consume_balanced`'s
   `include_closer` parameter serving two different fields' actual jobs --
   a rule's `block` is handed straight to a content-parser like
   `parse_declarations`, which has no reason to want its own outer braces
   back.
2. **`parse_declarations`'s declared return type is `list[Declaration]`.**
   An at-rule nested inside a declaration list (rare -- CSS Nesting allows
   e.g. `@media` inside a style rule's block) is still fully consumed by
   `consume_at_rule`, so it cannot corrupt the declarations that follow it,
   but it is not represented in the result; the generic grammar would
   otherwise need to return `list[Declaration | AtRule]`, which the brief's
   interface does not ask for. No test and no corpus `<style>` body observed
   exercises this. Flag it if CSS Nesting support is ever added.
3. **`!important` detection tolerates whitespace between `!` and
   `important`** (`red ! important`, not just `red !important`), and strips
   both tokens plus any whitespace introduced on either side. This is what
   5.5.5 actually says -- "the last two non-<whitespace-token>s" -- rather
   than "the last two tokens".
4. **`pos` on `QualifiedRule`/`AtRule` is the position of the rule's first
   token** (the prelude's first token, or the at-keyword); `Declaration.pos`
   is the name token's position. The spec does not assign rules a position
   at all; this follows the `pos`-on-everything convention the rest of the
   codebase uses.
5. **`CssParser` keeps its own `errors`/`metrics`, separate from the
   `CssTokenizer` it drives**, mirroring `htmlparse.TreeBuilder`'s split from
   `htmlparse.Tokenizer` so a driver can emit "tokenize" and "parse" as
   distinct `metrics.py` stages, the same split `htmlparse` uses for
   "tokenize"/"treebuild". `metrics["tokenizer_parse_errors"]`
   cross-references the tokenizer's own error count, exactly as
   `TreeBuilder.build()` does.
"""

from __future__ import annotations

import time
from collections import Counter
from dataclasses import dataclass, field

from mayshay.cssparse.tokenizer import (
    AtKeyword,
    CDC,
    CDO,
    Colon,
    CssToken,
    CssTokenizer,
    Delim,
    EOFToken,
    Function,
    Ident,
    LBrace,
    LBracket,
    LParen,
    RBrace,
    RBracket,
    RParen,
    Semicolon,
    Whitespace,
)

# Bracket-family openers, mapped to their mirror closer -- 4.3.9's "mirror
# variant" concept, reused here for block/group matching rather than escapes.
_MIRROR: dict[type, type] = {LBrace: RBrace, LBracket: RBracket, LParen: RParen}


# --------------------------------------------------------------------------
# Productions
# --------------------------------------------------------------------------


@dataclass
class QualifiedRule:
    prelude: list[CssToken] = field(default_factory=list)
    block: list[CssToken] | None = None
    pos: int = -1


@dataclass
class AtRule:
    name: str
    prelude: list[CssToken] = field(default_factory=list)
    block: list[CssToken] | None = None
    pos: int = -1


@dataclass
class Declaration:
    name: str
    value: list[CssToken] = field(default_factory=list)
    important: bool = False
    pos: int = -1


# --------------------------------------------------------------------------
# Token cursor
# --------------------------------------------------------------------------


class _Cursor:
    """A rewindable cursor over an already-tokenized list.

    The tokenizer's own `_next`/`_at`/`_reconsume` trio operates one code
    point at a time; this is the token-level analogue, needed because the
    parser algorithms are written in terms of "the next input token" and
    "reconsume the current input token" over a *token* stream, not a
    character stream. Past the end of `tokens`, `peek`/`next` synthesize an
    `EOFToken` rather than raising, so a `block` slice -- which never carries
    its own trailing EOFToken -- behaves the same as a full tokenized
    stylesheet, which does.
    """

    def __init__(self, tokens: list[CssToken]) -> None:
        self.tokens = tokens
        self.pos = 0

    def _eof(self) -> EOFToken:
        """Synthesize an EOF sentinel positioned past the end of `tokens`.

        `pos` approximates one past the *end* of the last token, not its
        start -- matching the tokenizer's own EOF convention
        (`CssTokenizer.pos == len(source)` once exhausted) as closely as
        possible from a token stream that only records each token's start
        offset. Exact for a token kind whose `.value` is its full serialized
        text (`Ident`, `Whitespace`, `Delim`, a `Number` written without an
        exponent, ...); an undercount for a kind whose source text is longer
        than `.value` (`AtKeyword`'s leading `@`, `Function`'s trailing `(`,
        a `String`'s quotes and any escapes). Reusing the last token's own
        *start* position here -- the previous version of this method --
        would make a synthetic EOF indistinguishable from a real error
        pointing at that token; this is a best-effort fix, not an exact one,
        since no `CssToken` carries its own source span.
        """
        if not self.tokens:
            return EOFToken(pos=-1)
        last = self.tokens[-1]
        value = getattr(last, "value", None)
        width = len(value) if isinstance(value, str) else 1
        return EOFToken(pos=last.pos + max(width, 1))

    def peek(self) -> CssToken:
        if self.pos >= len(self.tokens):
            return self._eof()
        return self.tokens[self.pos]

    def next(self) -> CssToken:
        tok = self.peek()
        if self.pos < len(self.tokens):
            self.pos += 1
        return tok

    def reconsume(self) -> None:
        if self.pos > 0:
            self.pos -= 1


def _skip_whitespace(cursor: _Cursor) -> None:
    while isinstance(cursor.peek(), Whitespace):
        cursor.next()


def _ascii_lower(text: str) -> str:
    """ASCII-only case fold -- see `tokenizer._ascii_lower` for why `str.lower()`
    is the wrong tool (U+1E9E and U+212A fold into the ASCII range under it).
    Duplicated rather than imported: it is three lines, and importing a
    leading-underscore name from another module is a worse coupling than
    repeating them.
    """
    return "".join(chr(ord(ch) + 0x20) if "A" <= ch <= "Z" else ch for ch in text)


# --------------------------------------------------------------------------
# 5.5.6 / 5.5.7 / 5.5.8 -- consume a component value / simple block / function
# --------------------------------------------------------------------------


def _consume_balanced(
    cursor: _Cursor,
    closer: type,
    errors: list[tuple[int, str]],
    metrics: Counter[str],
    *,
    include_closer: bool = True,
) -> list[CssToken]:
    """Consume component values up to and including a matching `closer`.

    Shared body for 5.5.7 (simple block, closer is `}`/`]`/`)`) and 5.5.8
    (function, closer is always `)`). `include_closer` is False only for the
    outermost `{...}` of a rule's block, whose contents the caller wants
    without the surrounding braces -- see the representation note under
    deviation 1 in the module docstring (this is not itself a deviation).
    """
    out: list[CssToken] = []
    while True:
        tok = cursor.peek()
        if isinstance(tok, EOFToken):
            errors.append((tok.pos, "eof in block"))
            metrics["parse_errors"] += 1
            return out
        if isinstance(tok, closer):
            cursor.next()
            if include_closer:
                out.append(tok)
            return out
        out.extend(_consume_component_value(cursor, errors, metrics))


def _consume_component_value(
    cursor: _Cursor, errors: list[tuple[int, str]], metrics: Counter[str]
) -> list[CssToken]:
    """5.5.6. Returns the flat tokens of exactly one component value.

    A plain token returns itself. A bracket opener or a function token
    returns itself plus every token of its matching group -- see deviation 1
    (component values as flat token lists, not a nested tree) for why that
    group is a flat list rather than a nested object.
    """
    tok = cursor.next()
    if isinstance(tok, Function):
        metrics["functions_consumed"] += 1
        return [tok] + _consume_balanced(cursor, RParen, errors, metrics)
    closer = _MIRROR.get(type(tok))
    if closer is not None:
        return [tok] + _consume_balanced(cursor, closer, errors, metrics)
    return [tok]


# --------------------------------------------------------------------------
# 5.5.1 consume a list of rules
# --------------------------------------------------------------------------


def _consume_list_of_rules(
    cursor: _Cursor,
    errors: list[tuple[int, str]],
    metrics: Counter[str],
    *,
    top_level: bool,
) -> list[QualifiedRule | AtRule]:
    rules: list[QualifiedRule | AtRule] = []
    while True:
        tok = cursor.next()
        if isinstance(tok, Whitespace):
            continue
        if isinstance(tok, EOFToken):
            return rules
        if isinstance(tok, (CDO, CDC)):
            # Top level: CDO/CDC hide a stylesheet from pre-<script> browsers
            # and are simply dropped. Nested (e.g. inside an at-rule's
            # block): the spec folds them into an ordinary qualified rule.
            if top_level:
                continue
            cursor.reconsume()
            rule = _consume_qualified_rule(cursor, errors, metrics)
            if rule is not None:
                rules.append(rule)
            continue
        if isinstance(tok, AtKeyword):
            rules.append(_consume_at_rule(cursor, tok, errors, metrics))
            continue
        cursor.reconsume()
        rule = _consume_qualified_rule(cursor, errors, metrics)
        if rule is not None:
            rules.append(rule)


# --------------------------------------------------------------------------
# 5.5.2 consume an at-rule
# --------------------------------------------------------------------------


def _consume_at_rule(
    cursor: _Cursor,
    at_tok: AtKeyword,
    errors: list[tuple[int, str]],
    metrics: Counter[str],
) -> AtRule:
    """The at-keyword token has already been consumed by the caller."""
    prelude: list[CssToken] = []
    block: list[CssToken] | None = None
    while True:
        tok = cursor.next()
        if isinstance(tok, Semicolon):
            break
        if isinstance(tok, EOFToken):
            errors.append((tok.pos, "eof in at-rule"))
            metrics["parse_errors"] += 1
            break
        if isinstance(tok, LBrace):
            block = _consume_balanced(
                cursor, RBrace, errors, metrics, include_closer=False
            )
            break
        cursor.reconsume()
        prelude.extend(_consume_component_value(cursor, errors, metrics))
    metrics["at_rules"] += 1
    return AtRule(name=at_tok.value, prelude=prelude, block=block, pos=at_tok.pos)


# --------------------------------------------------------------------------
# 5.5.3 consume a qualified rule
# --------------------------------------------------------------------------


def _consume_qualified_rule(
    cursor: _Cursor, errors: list[tuple[int, str]], metrics: Counter[str]
) -> QualifiedRule | None:
    """Returns None on the EOF-before-any-block parse error -- the spec's
    "return nothing", which drops the whole rule (there is nothing sane to
    render a selector against with no declaration block).
    """
    start_pos = cursor.peek().pos
    prelude: list[CssToken] = []
    while True:
        tok = cursor.peek()
        if isinstance(tok, EOFToken):
            cursor.next()
            errors.append((tok.pos, "eof in qualified rule prelude"))
            metrics["parse_errors"] += 1
            return None
        if isinstance(tok, LBrace):
            cursor.next()
            block = _consume_balanced(
                cursor, RBrace, errors, metrics, include_closer=False
            )
            metrics["qualified_rules"] += 1
            return QualifiedRule(prelude=prelude, block=block, pos=start_pos)
        prelude.extend(_consume_component_value(cursor, errors, metrics))


# --------------------------------------------------------------------------
# 5.5.4 consume a list of declarations
# --------------------------------------------------------------------------


def _consume_list_of_declarations(
    cursor: _Cursor, errors: list[tuple[int, str]], metrics: Counter[str]
) -> list[Declaration]:
    decls: list[Declaration] = []
    while True:
        tok = cursor.peek()
        if isinstance(tok, (Whitespace, Semicolon)):
            cursor.next()
            continue
        if isinstance(tok, EOFToken):
            return decls
        if isinstance(tok, AtKeyword):
            cursor.next()
            # Consumed for its side effect on the cursor only -- see
            # deviation 2 (parse_declarations's list[Declaration] return type
            # has no room for a nested at-rule). A malformed or unknown
            # at-rule here still cannot break the declarations before or after it.
            _consume_at_rule(cursor, tok, errors, metrics)
            continue
        if isinstance(tok, Ident):
            # Spec: build a temporary component-value list starting with the
            # name, up to (not including) the next semicolon/EOF, then hand
            # that whole run to "consume a declaration".
            temp = [cursor.next()]
            while not isinstance(cursor.peek(), (Semicolon, EOFToken)):
                temp.extend(_consume_component_value(cursor, errors, metrics))
            decl = _consume_declaration(temp, errors, metrics)
            if decl is not None:
                decls.append(decl)
            continue
        # Anything else starting a "declaration": parse error. Drop exactly
        # one component value and retry -- not the rest of the block, and
        # not nothing: a single stray token must not spin the loop forever.
        errors.append((tok.pos, "unexpected token in declaration list"))
        metrics["parse_errors"] += 1
        metrics["malformed_declarations"] += 1
        _consume_component_value(cursor, errors, metrics)


# --------------------------------------------------------------------------
# 5.5.5 consume a declaration
# --------------------------------------------------------------------------


def _consume_declaration(
    tokens: list[CssToken], errors: list[tuple[int, str]], metrics: Counter[str]
) -> Declaration | None:
    """`tokens[0]` is the declaration's name (an Ident); the caller verified
    that before building this run. Returns None -- spec's "return nothing"
    -- when no colon follows the name, which is how a malformed declaration
    like `color red` is dropped without touching its siblings.
    """
    cursor = _Cursor(tokens)
    name_tok = cursor.next()
    _skip_whitespace(cursor)
    if not isinstance(cursor.peek(), Colon):
        tok = cursor.peek()
        errors.append((tok.pos, "declaration without colon"))
        metrics["parse_errors"] += 1
        metrics["malformed_declarations"] += 1
        return None
    cursor.next()  # the colon
    _skip_whitespace(cursor)

    value: list[CssToken] = []
    while not isinstance(cursor.peek(), EOFToken):
        value.extend(_consume_component_value(cursor, errors, metrics))

    important = _strip_important(value)
    metrics["declarations"] += 1
    return Declaration(name=name_tok.value, value=value, important=important, pos=name_tok.pos)


def _strip_important(value: list[CssToken]) -> bool:
    """Mutates `value` in place; returns whether `!important` was found.

    Performs two separate 5.5.5 steps, not just the one the name suggests:
    first, the spec's own unconditional "while the last item in decl's
    value is a whitespace token, remove it" -- which fires whether or not
    `!important` is present, since a bare `color: red   ` should not keep
    its trailing whitespace either. Then: "If the last two
    non-<whitespace-token>s in decl's value are a <delim-token> with the
    value '!' followed by an <ident-token> ... equal to 'important' ...
    remove them" -- which, on a match, strips both tokens and repeats the
    trailing-whitespace removal once more. Deviation 3 explains why the
    match walks past intervening whitespace on both sides instead of only
    checking `value[-1]`/`value[-2]` directly.
    """
    while value and isinstance(value[-1], Whitespace):
        value.pop()
    if not (
        value
        and isinstance(value[-1], Ident)
        and _ascii_lower(value[-1].value) == "important"
    ):
        return False
    j = len(value) - 2
    while j >= 0 and isinstance(value[j], Whitespace):
        j -= 1
    if j < 0 or not (isinstance(value[j], Delim) and value[j].value == "!"):
        return False
    del value[j:]
    while value and isinstance(value[-1], Whitespace):
        value.pop()
    return True


# --------------------------------------------------------------------------
# Driver
# --------------------------------------------------------------------------


class CssParser:
    """
    Consumes CSS source into a flat list of top-level rules.

        rules = CssParser(source).parse_stylesheet()

    Mirrors `htmlparse.TreeBuilder`: owns a `CssTokenizer` (`self.tokenizer`)
    but keeps its own `errors`/`metrics` -- see deviation 5 (errors/metrics
    kept separate from the `CssTokenizer` it drives).
    """

    def __init__(self, source: str) -> None:
        self.source = source
        self.tokenizer = CssTokenizer(source)
        self.errors: list[tuple[int, str]] = []
        self.metrics: Counter[str] = Counter()

    def parse_stylesheet(self) -> list[QualifiedRule | AtRule]:
        """The "parse a stylesheet" entry point (5.3.3): tokenize `source`,
        then consume a list of rules with the top-level flag set.
        """
        started = time.perf_counter()
        tokens = list(self.tokenizer.tokenize())
        cursor = _Cursor(tokens)
        rules = _consume_list_of_rules(cursor, self.errors, self.metrics, top_level=True)
        self.metrics["parse_time_ms"] = round((time.perf_counter() - started) * 1000, 3)
        self.metrics["rules"] = len(rules)
        # Kept distinct from our own errors, same rationale as
        # `TreeBuilder.build()`: a stylesheet with only tokenizer-level
        # errors (e.g. an unterminated string) would otherwise report zero.
        self.metrics["tokenizer_parse_errors"] = self.tokenizer.metrics["parse_errors"]
        return rules

    def parse_declarations(self, tokens: list[CssToken]) -> list[Declaration]:
        """The "parse a list of declarations" entry point (5.3.6), given an
        already-tokenized run rather than a string -- see the module
        docstring for why.
        """
        cursor = _Cursor(list(tokens))
        decls = _consume_list_of_declarations(cursor, self.errors, self.metrics)
        self.metrics["parsed_declarations"] = len(decls)
        return decls


def parse_stylesheet(source: str) -> list[QualifiedRule | AtRule]:
    return CssParser(source).parse_stylesheet()


def parse_declarations(tokens: list[CssToken]) -> list[Declaration]:
    return CssParser("").parse_declarations(tokens)


__all__ = [
    "AtRule",
    "CssParser",
    "Declaration",
    "QualifiedRule",
    "parse_declarations",
    "parse_stylesheet",
]
