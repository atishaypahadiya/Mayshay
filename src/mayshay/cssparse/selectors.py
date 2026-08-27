"""
Mayshay selector parsing and specificity.

A hand-rolled implementation of the parsing half of Selectors Level 4
(https://www.w3.org/TR/selectors-4/), restricted to the Level 3 feature set
this engine matches against: type, universal, class, id, attribute and
pseudo-class simple selectors, and the descendant / `>` / `+` / `~`
combinators. Matching is task H's job; this module only turns the flat token
list a `QualifiedRule.prelude` carries into a `SelectorList`, and computes
the (a, b, c) specificity triple of section 17.

The input is `list[CssToken]` from `CssTokenizer`, with or without a trailing
`EOFToken`: `tokenize()` emits one, a rule's prelude slice does not, and both
must parse identically.

**Whitespace is significant here and is never stripped in advance.** The
descendant combinator *is* whitespace, so a parser that filters
`Whitespace` tokens up front cannot tell `a b` from `ab`, and one that
treats every whitespace run as a descendant combinator invents one on each
side of `>`. Instead the token stream is kept verbatim and whitespace is
resolved at exactly one place: `_parse_complex`'s loop, which consumes any
whitespace run *between* compounds and then looks at what follows. An
explicit combinator delim wins, absorbing the whitespace on both sides; a
non-combinator token after whitespace means the descendant combinator; the
same token with no whitespace before it is a parse error. Inside a compound
the question never arises -- `_parse_compound` is maximal-munch and stops at
the first token that cannot continue the compound, so it never sees
whitespace at all.

Errors are raised, not recovered from: `SelectorParseError` is a `ValueError`
subclass carrying the offending token's `pos`. That is the spec's rule at
css-syntax level -- an invalid selector invalidates the style rule that
contains it, and nothing more -- so the decision of what to do about it
belongs to the caller building the stylesheet, not here.

Deliberate deviations and scope limits, documented so they don't surprise us
later:

1. **The match operators `~=`, `|=`, `^=`, `$=` and `*=` are reassembled
   from two `Delim` tokens**, because the current css-syntax spec has no
   `<substring-match-token>` family -- see deviation 7 in
   `tokenizer.py`. The two delims must be *adjacent in the source*, which
   `_adjacent` checks by comparing `pos`, so `[a ~= v]` parses and
   `[a ~ = v]` does not: whitespace is allowed around the operator but not
   inside it, exactly as when it was one token. `pos` comparison rather
   than mere list adjacency also rejects `[a~/**/=v]`, whose comment the
   tokenizer has already dropped. Tokens with `pos == -1` (hand-built, not
   tokenized) are treated as adjacent, since there is nothing to check.
2. **Type and attribute names are ASCII-lowercased at parse time; class,
   id and attribute *values* are not.** In an HTML document element and
   attribute names match ASCII case-insensitively while class and id are
   case-sensitive, and `htmlparse`'s tree builder already lowercases both
   names it stores, so folding here lets task H compare with `==`. The cost
   is foreign-content camelCase (`clipPath`, `linearGradient`), which is
   case-sensitive per spec -- but this engine's tree builder has no foreign
   content and stores `clippath`, so the two are consistent. Revisit
   together if SVG namespaces ever land. Pseudo-class and pseudo-element
   names are ASCII case-insensitive unconditionally and are always folded.
3. **`:not()`, `:is()` and `:where()` parse their argument as a nested
   selector list** and carry it in `PseudoClassSelector.selectors`, which
   makes their Level 4 specificity rules (section 17: the most specific
   argument for `:not()`/`:is()`, zero for `:where()`) fall out of
   `specificity`. `:is()` and `:where()` take a `<forgiving-selector-list>`,
   so an argument that fails to parse is dropped rather than invalidating
   the rule; `:not()` does not, so it invalidates. Every other functional
   pseudo-class keeps its argument as the raw token run in
   `PseudoClassSelector.argument` and counts as a plain pseudo-class:
   nothing here interprets `An+B`, so `:nth-child(2)` is parsed but its
   argument is not validated. `:has()` is deliberately in that group --
   supporting it properly means relative selectors (`:has(> p)`), which
   `_parse_complex` does not accept, and a matcher that can run them.
4. **Namespaces are not supported.** `ns|div`, `*|div`, `|div` and
   `[ns|attr]` raise, rather than being silently misparsed as something
   else -- `ns|div` would otherwise read as a type selector followed by
   junk. They need an `@namespace` rule, which the generic grammar
   collects but nothing interprets.
5. **The legacy one-colon pseudo-elements `:before`, `:after`,
   `:first-line` and `:first-letter` produce `PseudoElementSelector`**, as
   Selectors 4 section 3.4 requires, so they count in `c` and not in `b`.
   Every other one-colon name is a pseudo-class, including names this
   engine will never match; unknown pseudo-classes parse fine and simply
   never match, which is what a matcher wants for forward compatibility.
6. **Functional pseudo-elements (`::part()`, `::slotted()`) raise.** They
   are the one construct where "parse it and never match it" is wrong: both
   change what the compound applies to, and neither is representable by
   `PseudoElementSelector`, which carries no argument.
7. **A compound's ordering rules are enforced**: a type or universal
   selector may only be the first simple in its compound, and a
   pseudo-element may only be followed by pseudo-classes (which also means
   only one pseudo-element per compound). `[a]div` and `::before.c` are
   parse errors, per the `<compound-selector>` grammar in section 4.3.
8. **`specificity()` accepts a `Simple`, a `Compound` or a `Complex`, and
   rejects a `SelectorList` with `TypeError`.** A selector list has no
   single specificity -- the cascade compares one *selector* at a time, and
   returning e.g. the maximum would silently give a rule the specificity of
   its most specific selector no matter which one matched.
9. **`_Cursor` is a fresh, smaller cursor than `parser._Cursor`** rather
   than an import of that module's private name -- the same call
   `parser.py` makes about `_ascii_lower`. It differs where it matters: it
   reports end of input as `None` (and treats `EOFToken` as end of input),
   because selector parsing has no error-recovery mode in which consuming a
   synthesized EOF token would be useful.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from mayshay.cssparse.tokenizer import (
    Colon,
    Comma,
    CssToken,
    Delim,
    EOFToken,
    Function,
    Hash,
    Ident,
    LBrace,
    LBracket,
    LParen,
    RBrace,
    RBracket,
    RParen,
    String,
    Whitespace,
)

# The combinators written as a single delim. Descendant is whitespace and so
# has no entry; `||` (column) and `>>` (an early Selectors 4 draft's explicit
# descendant combinator, since removed) are not combinators here.
_COMBINATOR_DELIMS = frozenset(">+~")

# Delims that can begin the second half of a match operator, `=` excluded.
_MATCH_PREFIXES = frozenset("~|^$*")

# Pseudo-elements that must also be recognized with a single colon (Selectors
# 4 section 3.4). The list is closed: no new pseudo-element gets one-colon
# syntax.
_LEGACY_PSEUDO_ELEMENTS = frozenset(
    {"before", "after", "first-line", "first-letter"}
)

# Functional pseudo-classes whose argument is a selector list. The value is
# whether that list is *forgiving* -- see deviation 3.
_SELECTOR_ARG_PSEUDOS: dict[str, bool] = {
    "not": False,
    "is": True,
    "where": True,
    # The pre-`:is()` name for the same thing, still shipped by every engine.
    "matches": True,
}

_OPENERS = (LParen, Function, LBracket, LBrace)
_CLOSERS = (RParen, RBracket, RBrace)


class SelectorParseError(ValueError):
    """An invalid selector. A `ValueError`, because the brief's contract with
    callers is `ValueError`; a subclass, so a caller that wants to tell a bad
    selector apart from any other `ValueError` can, and so the offending
    `pos` survives to whoever reports it.
    """

    def __init__(self, message: str, pos: int = -1) -> None:
        self.pos = pos
        super().__init__(message if pos < 0 else f"{message} (at {pos})")


def _ascii_lower(text: str) -> str:
    """ASCII-only case fold -- see `tokenizer._ascii_lower` for why
    `str.lower()` is the wrong tool. Duplicated for the reason `parser.py`
    duplicates it: importing another module's private name is the worse
    coupling.
    """
    return "".join(chr(ord(ch) + 0x20) if "A" <= ch <= "Z" else ch for ch in text)


# --------------------------------------------------------------------------
# Selector structures
# --------------------------------------------------------------------------


@dataclass
class TypeSelector:
    """`div`. ASCII-lowercased -- see deviation 2."""

    name: str


@dataclass
class UniversalSelector:
    """`*`. Contributes nothing to specificity."""


@dataclass
class ClassSelector:
    """`.warning`. Case-sensitive, so the name is kept as written."""

    name: str


@dataclass
class IdSelector:
    """`#main`. Case-sensitive, so the name is kept as written."""

    name: str


@dataclass
class AttributeSelector:
    """`[href]`, `[type="text"]`, `[class~="a" i]`.

    `operator` is None for a presence test, else one of `=`, `~=`, `|=`,
    `^=`, `$=`, `*=`. `case` is the Level 4 modifier: "i", "s", or None for
    the document language's default (which for HTML depends on the attribute
    -- task H's problem, not this module's).
    """

    name: str
    operator: str | None = None
    value: str | None = None
    case: str | None = None


@dataclass
class PseudoClassSelector:
    """`:hover`, `:nth-child(2n+1)`, `:not(.a, .b)`.

    `argument` is None for a non-functional pseudo-class, else the raw token
    run between the parens, whitespace included and delimiters excluded.
    `selectors` is set only for the pseudo-classes of `_SELECTOR_ARG_PSEUDOS`
    -- see deviation 3.
    """

    name: str
    argument: list[CssToken] | None = None
    selectors: SelectorList | None = None


@dataclass
class PseudoElementSelector:
    """`::before`, and the four legacy one-colon spellings."""

    name: str


Simple = (
    TypeSelector
    | UniversalSelector
    | ClassSelector
    | IdSelector
    | AttributeSelector
    | PseudoClassSelector
    | PseudoElementSelector
)


@dataclass
class Compound:
    """A run of simple selectors with no combinator between them: `p.c#i`.

    `pos` is the position of the compound's first token, following the
    `pos`-on-everything convention the rest of the codebase uses.
    """

    simples: list[Simple] = field(default_factory=list)
    pos: int = -1


@dataclass
class Complex:
    """Compounds joined by combinators: `div > p.c a`.

    `combinators[i]` joins `compounds[i]` to `compounds[i + 1]`, so
    `len(combinators) == len(compounds) - 1` always. Each is one of `" "`
    (descendant), `">"`, `"+"` or `"~"`.
    """

    compounds: list[Compound] = field(default_factory=list)
    combinators: list[str] = field(default_factory=list)
    pos: int = -1


@dataclass
class SelectorList:
    """The comma-separated list in a style rule's prelude."""

    selectors: list[Complex] = field(default_factory=list)


# --------------------------------------------------------------------------
# Token cursor
# --------------------------------------------------------------------------


class _Cursor:
    """A forward cursor over a token list. See deviation 9."""

    def __init__(self, tokens: list[CssToken]) -> None:
        self.tokens = tokens
        self.i = 0

    def peek(self, offset: int = 0) -> CssToken | None:
        """The token `offset` ahead, or None at (or past) end of input.

        `EOFToken` reads as end of input, so a tokenized string and a
        prelude slice of the same tokens behave identically.
        """
        j = self.i + offset
        if j >= len(self.tokens):
            return None
        tok = self.tokens[j]
        return None if isinstance(tok, EOFToken) else tok

    def next(self) -> CssToken | None:
        tok = self.peek()
        if tok is not None:
            self.i += 1
        return tok

    def skip_whitespace(self) -> bool:
        """Consume a whitespace run; report whether there was one.

        The boolean is the whole reason whitespace survives to this layer:
        it is what distinguishes a descendant combinator from no combinator
        at all.
        """
        seen = False
        while isinstance(self.peek(), Whitespace):
            self.i += 1
            seen = True
        return seen

    def pos(self) -> int:
        """A source position to blame in an error message: the next token's,
        or -- at end of input -- one past the start of the last token
        consumed, which is as close to "where the selector ran out" as a
        stream of start offsets allows.
        """
        tok = self.peek()
        if tok is not None:
            return tok.pos
        if self.tokens:
            last = self.tokens[-1]
            return last.pos if last.pos < 0 else last.pos + 1
        return -1


def _is_delim(tok: CssToken | None, value: str) -> bool:
    return isinstance(tok, Delim) and tok.value == value


def _adjacent(first: CssToken, second: CssToken) -> bool:
    """Whether two one-character delims were written with nothing between
    them. See deviation 1 for why this is `pos` arithmetic and not just list
    adjacency.
    """
    if first.pos < 0 or second.pos < 0:
        return True
    return second.pos == first.pos + 1


# --------------------------------------------------------------------------
# Selector list
# --------------------------------------------------------------------------


def _split_top_level_commas(tokens: list[CssToken]) -> list[list[CssToken]]:
    """Split on commas that are not inside `()`, `[]` or `{}`.

    A selector list splits on top-level commas only: the commas in
    `a:not(b, c)` belong to the pseudo-class's argument, and the ones in
    `[title="a,b"]` are not `Comma` tokens at all -- the tokenizer already
    put them inside a `String`. Returns `[]` for an empty or all-whitespace
    input, so an empty forgiving list (`:is()`) is distinguishable from a
    one-element list.
    """
    chunks: list[list[CssToken]] = []
    current: list[CssToken] = []
    depth = 0
    for tok in tokens:
        if isinstance(tok, EOFToken):
            break
        if isinstance(tok, _OPENERS):
            depth += 1
        elif isinstance(tok, _CLOSERS):
            # Clamped: an unbalanced closer must not drive depth negative and
            # make a later comma look nested.
            depth = max(0, depth - 1)
        elif isinstance(tok, Comma) and depth == 0:
            chunks.append(current)
            current = []
            continue
        current.append(tok)
    chunks.append(current)
    if len(chunks) == 1 and all(isinstance(t, Whitespace) for t in chunks[0]):
        return []
    return chunks


def parse_selector_list(tokens: list[CssToken]) -> SelectorList:
    """Parse a style rule's prelude into a `SelectorList`.

    Raises `SelectorParseError` (a `ValueError`) if any selector in the list
    is invalid: per css-syntax, that invalidates the rule this prelude came
    from, and nothing else in the stylesheet.
    """
    return _parse_selector_list(tokens, forgiving=False)


def _parse_selector_list(
    tokens: list[CssToken], *, forgiving: bool
) -> SelectorList:
    chunks = _split_top_level_commas(tokens)
    if not chunks and not forgiving:
        raise SelectorParseError("empty selector")
    selectors: list[Complex] = []
    for chunk in chunks:
        try:
            selectors.append(_parse_complex_tokens(chunk))
        except SelectorParseError:
            if not forgiving:
                raise
    return SelectorList(selectors)


def _parse_complex_tokens(tokens: list[CssToken]) -> Complex:
    cursor = _Cursor(tokens)
    selector = _parse_complex(cursor)
    trailing = cursor.peek()
    if trailing is not None:
        raise SelectorParseError(
            f"unexpected {type(trailing).__name__} after selector", trailing.pos
        )
    return selector


# --------------------------------------------------------------------------
# Complex selector -- the one place whitespace is interpreted
# --------------------------------------------------------------------------


def _parse_complex(cursor: _Cursor) -> Complex:
    cursor.skip_whitespace()
    start = cursor.pos()
    compounds = [_parse_compound(cursor)]
    combinators: list[str] = []
    while True:
        # Consume whatever separates this compound from the next, remembering
        # whether any of it was whitespace.
        had_whitespace = cursor.skip_whitespace()
        tok = cursor.peek()
        if tok is None:
            break
        if isinstance(tok, Delim) and tok.value in _COMBINATOR_DELIMS:
            cursor.next()
            # Whitespace on either side of an explicit combinator is part of
            # the combinator, not a descendant combinator of its own.
            cursor.skip_whitespace()
            combinators.append(tok.value)
        elif had_whitespace:
            combinators.append(" ")
        else:
            raise SelectorParseError(
                f"unexpected {type(tok).__name__} in selector", tok.pos
            )
        compounds.append(_parse_compound(cursor))
    return Complex(compounds, combinators, start)


def _parse_compound(cursor: _Cursor) -> Compound:
    start = cursor.pos()
    simples: list[Simple] = []
    pseudo_element_seen = False

    while True:
        tok = cursor.peek()
        if tok is None:
            break

        if isinstance(tok, Ident):
            _require_first_in_compound(simples, tok)
            cursor.next()
            _reject_namespace(cursor)
            simples.append(TypeSelector(_ascii_lower(tok.value)))
            continue

        if isinstance(tok, Hash):
            if not tok.is_id:
                # `#0f0` is a hash token but not an id selector: the spec's
                # type flag is exactly this distinction.
                raise SelectorParseError(
                    f"'#{tok.value}' is not a valid id selector", tok.pos
                )
            _require_no_pseudo_element(pseudo_element_seen, tok)
            cursor.next()
            simples.append(IdSelector(tok.value))
            continue

        if isinstance(tok, LBracket):
            _require_no_pseudo_element(pseudo_element_seen, tok)
            simples.append(_parse_attribute(cursor))
            continue

        if isinstance(tok, Colon):
            simple = _parse_pseudo(cursor)
            if isinstance(simple, PseudoElementSelector):
                _require_no_pseudo_element(pseudo_element_seen, tok)
                pseudo_element_seen = True
            simples.append(simple)
            continue

        if isinstance(tok, Delim):
            if tok.value == "*":
                _require_first_in_compound(simples, tok)
                cursor.next()
                _reject_namespace(cursor)
                simples.append(UniversalSelector())
                continue
            if tok.value == ".":
                _require_no_pseudo_element(pseudo_element_seen, tok)
                cursor.next()
                name = cursor.peek()
                if not isinstance(name, Ident):
                    raise SelectorParseError(
                        "expected a class name after '.'", cursor.pos()
                    )
                cursor.next()
                simples.append(ClassSelector(name.value))
                continue
            if tok.value == "|":
                raise SelectorParseError(
                    "namespace prefixes are not supported", tok.pos
                )

        break

    if not simples:
        raise SelectorParseError("expected a compound selector", start)
    return Compound(simples, start)


def _require_first_in_compound(simples: list[Simple], tok: CssToken) -> None:
    """A type or universal selector may only lead its compound (section 4.3).

    This is what makes `[a]div` and `.c*` errors rather than silently
    accepted compounds.
    """
    if simples:
        raise SelectorParseError(
            "a type or universal selector must be first in its compound",
            tok.pos,
        )


def _require_no_pseudo_element(seen: bool, tok: CssToken) -> None:
    """Only pseudo-classes may follow a pseudo-element -- deviation 7."""
    if seen:
        raise SelectorParseError(
            "only pseudo-classes may follow a pseudo-element", tok.pos
        )


def _reject_namespace(cursor: _Cursor) -> None:
    """Reject `ns|div` / `*|div` right after the prefix was read as a type or
    universal selector. Deviation 4: better a clear error than a type
    selector plus unexplained junk.

    An adjacent `|=` cannot occur here -- that only follows an attribute
    name, inside brackets, which `_parse_attribute` handles on its own.
    """
    tok = cursor.peek()
    if _is_delim(tok, "|"):
        raise SelectorParseError("namespace prefixes are not supported", tok.pos)


# --------------------------------------------------------------------------
# Attribute selectors
# --------------------------------------------------------------------------


def _parse_attribute(cursor: _Cursor) -> AttributeSelector:
    opener = cursor.next()  # '['
    cursor.skip_whitespace()
    name_tok = cursor.peek()
    if not isinstance(name_tok, Ident):
        raise SelectorParseError("expected an attribute name", cursor.pos())
    cursor.next()
    name = _ascii_lower(name_tok.value)

    cursor.skip_whitespace()
    if isinstance(cursor.peek(), RBracket):
        cursor.next()
        return AttributeSelector(name)

    operator = _parse_attribute_operator(cursor)

    cursor.skip_whitespace()
    value_tok = cursor.peek()
    if not isinstance(value_tok, (Ident, String)):
        # The grammar admits <string-token> and <ident-token> only; `[a=1]`
        # is invalid CSS, however common it looks.
        raise SelectorParseError(
            "expected a string or ident attribute value", cursor.pos()
        )
    cursor.next()

    cursor.skip_whitespace()
    case = None
    flag = cursor.peek()
    if isinstance(flag, Ident) and _ascii_lower(flag.value) in ("i", "s"):
        cursor.next()
        case = _ascii_lower(flag.value)
        cursor.skip_whitespace()

    if not isinstance(cursor.peek(), RBracket):
        raise SelectorParseError(
            "expected ']' to close the attribute selector",
            cursor.pos() if cursor.peek() is not None else opener.pos,
        )
    cursor.next()
    return AttributeSelector(name, operator, value_tok.value, case)


def _parse_attribute_operator(cursor: _Cursor) -> str:
    """Read `=`, or one of the two-delim match operators -- deviation 1."""
    first = cursor.peek()
    if isinstance(first, Delim):
        if first.value == "=":
            cursor.next()
            return "="
        if first.value in _MATCH_PREFIXES:
            second = cursor.peek(1)
            if _is_delim(second, "=") and _adjacent(first, second):
                cursor.next()
                cursor.next()
                return first.value + "="
            if first.value == "|":
                raise SelectorParseError(
                    "namespace prefixes are not supported", first.pos
                )
    raise SelectorParseError("expected an attribute operator", cursor.pos())


# --------------------------------------------------------------------------
# Pseudo-classes and pseudo-elements
# --------------------------------------------------------------------------


def _parse_pseudo(cursor: _Cursor) -> Simple:
    colon = cursor.next()  # ':'
    double_colon = isinstance(cursor.peek(), Colon)
    if double_colon:
        cursor.next()

    tok = cursor.peek()
    if isinstance(tok, Ident):
        cursor.next()
        name = _ascii_lower(tok.value)
        if double_colon or name in _LEGACY_PSEUDO_ELEMENTS:
            return PseudoElementSelector(name)
        return PseudoClassSelector(name)

    if isinstance(tok, Function):
        cursor.next()
        name = _ascii_lower(tok.value)
        argument = _consume_function_argument(cursor, tok)
        if double_colon:
            # Deviation 6.
            raise SelectorParseError(
                f"functional pseudo-element '::{name}()' is not supported",
                tok.pos,
            )
        forgiving = _SELECTOR_ARG_PSEUDOS.get(name)
        if forgiving is None:
            return PseudoClassSelector(name, argument)
        nested = _parse_selector_list(argument, forgiving=forgiving)
        return PseudoClassSelector(name, argument, nested)

    raise SelectorParseError("expected a pseudo-class or pseudo-element name",
                             cursor.pos() if tok is not None else colon.pos)


def _consume_function_argument(
    cursor: _Cursor, opener: CssToken
) -> list[CssToken]:
    """The tokens up to the function's matching `)`, exclusive.

    Only paren depth is tracked: a `)` written inside a string or a url is
    already part of that token, and one written inside `[]` is still an
    `RParen` that belongs to this function as far as the token stream is
    concerned.
    """
    argument: list[CssToken] = []
    depth = 0
    while True:
        tok = cursor.peek()
        if tok is None:
            raise SelectorParseError(
                "unterminated pseudo-class argument", opener.pos
            )
        cursor.next()
        if isinstance(tok, (LParen, Function)):
            depth += 1
        elif isinstance(tok, RParen):
            if depth == 0:
                return argument
            depth -= 1
        argument.append(tok)


# --------------------------------------------------------------------------
# Specificity (Selectors 4 section 17)
# --------------------------------------------------------------------------

_ZERO = (0, 0, 0)


def specificity(selector: Simple | Compound | Complex) -> tuple[int, int, int]:
    """The (a, b, c) triple: `a` counts id selectors, `b` counts class,
    attribute and pseudo-class selectors, `c` counts type and pseudo-element
    selectors. The universal selector and combinators contribute nothing.

    Accepts a simple, compound or complex selector. A `SelectorList` is
    rejected -- see deviation 8.
    """
    if isinstance(selector, Complex):
        return _sum(specificity(c) for c in selector.compounds)
    if isinstance(selector, Compound):
        return _sum(specificity(s) for s in selector.simples)
    if isinstance(selector, IdSelector):
        return (1, 0, 0)
    if isinstance(selector, (ClassSelector, AttributeSelector)):
        return (0, 1, 0)
    if isinstance(selector, PseudoClassSelector):
        return _pseudo_class_specificity(selector)
    if isinstance(selector, (TypeSelector, PseudoElementSelector)):
        return (0, 0, 1)
    if isinstance(selector, UniversalSelector):
        return _ZERO
    raise TypeError(
        f"specificity() wants a simple, compound or complex selector, "
        f"not {type(selector).__name__}"
    )


def _pseudo_class_specificity(selector: PseudoClassSelector) -> tuple[int, int, int]:
    if selector.name == "where":
        # `:where()` is the whole point of `:where()`.
        return _ZERO
    if selector.selectors is not None:
        # `:not()` / `:is()`: the specificity of the most specific argument,
        # and zero for an empty (forgiving) list.
        return max(
            (specificity(s) for s in selector.selectors.selectors),
            default=_ZERO,
        )
    return (0, 1, 0)


def _sum(triples: Iterable[tuple[int, int, int]]) -> tuple[int, int, int]:
    a = b = c = 0
    for triple in triples:
        a += triple[0]
        b += triple[1]
        c += triple[2]
    return (a, b, c)
