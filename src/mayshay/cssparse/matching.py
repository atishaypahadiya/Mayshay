"""
Mayshay selector matching and rule indexing.

The other half of Selectors Level 4 (https://www.w3.org/TR/selectors-4/):
`selectors.py` turns a token run into a `Complex`, and this module answers
"does this element match it?" over the sections 4 (structure), 5 (the type,
universal and attribute selectors) and 6 (pseudo-classes) feature set the
parser accepts.

**Matching runs right to left.** `matches` starts at the *rightmost* compound
-- the one that must describe the element itself -- and walks leftwards
through the combinators, following parent or sibling links. The obvious
left-to-right reading of `div p` is "find every div, then look inside", which
for a single element means searching a subtree to answer a question about one
node, and which backtracks badly: `a b c d` against a deep tree re-walks the
same descendants once per prefix. Right to left asks instead "is this a `p`?
if so, does it have a `div` ancestor?", which fails on the first compound for
almost every element and never enumerates a subtree. It is also what makes
`RuleIndex` possible at all: a rule can only match an element whose own
rightmost compound matches, so the rightmost compound's id / class / type is
a key that rules out most rules without running the matcher.

`RuleIndex` buckets rules by that key. `candidates(element)` returns the
universal bucket plus the buckets for the element's id, each of its classes,
and its tag name; everything else cannot match and is never tested. The
universal bucket is the catch-all for a rightmost compound with no usable key
(`*`, `[hidden]`, `:is(.a, .b)`) and is returned for *every* element --
dropping it would be a silent correctness bug rather than an optimisation.

Deliberate deviations and scope limits, documented so they don't surprise us
later:

1. **`matches()` accepts a `Simple`, a `Compound` or a `Complex`, and rejects
   a `SelectorList` with `TypeError`** -- the same call `specificity()` makes
   in deviation 8 of `selectors.py`, for the same reason. A boolean for a
   whole list would tell the cascade that *something* matched without saying
   which, and the cascade needs the matching selector to get a specificity.
   `RuleIndex` rejects a `SelectorList` rule for the same reason: expand
   `p, .a { ... }` into one entry per selector before indexing it.
2. **A non-`Element` node matches nothing**, rather than raising. Selectors
   select elements, so the answer for a `Text`, `Comment` or `Document` is
   genuinely "no", and a tree walk that asks about every node is the normal
   caller.
3. **Type matching compares `==` against `Element.tag_name` and does not
   case-fold either side.** That is the contract deviation 2 of
   `selectors.py` sets up: the parser ASCII-lowercases type and attribute
   *names* precisely so this comparison can be a bare `==`, and the tree
   builder lowercases both names it stores. Class and id values are compared
   as written, which is the asymmetry HTML actually has. The cost is that a
   hand-built `Element("DIV")` -- something no code path in this engine
   produces -- will not match `div`. Folding here instead would be a second
   fold on every comparison in the hot loop, and would still be wrong for
   the foreign-content case that motivates it, since a real fix needs
   namespaces on both sides.
4. **Attribute *values* are compared case-sensitively except for the
   attributes HTML names as case-insensitive.** The HTML Standard's
   "Case-sensitivity of selectors" section lists ~46 attributes (`type`,
   `rel`, `lang`, `dir`, ...) whose selector value comparison is ASCII
   case-insensitive for HTML elements in an HTML document, which is why
   `[type="TEXT"]` matches `<input type=text>` in every browser. The list is
   `_HTML_CASE_INSENSITIVE_ATTRS`. The Level 4 `i` and `s` modifiers
   override it in either direction. Since this engine has no foreign content
   and no XML mode, the "is it an HTML element in an HTML document"
   precondition is always true and is not tested for.
5. **`An+B` is parsed here, not in `selectors.py`.** Deviation 3 there keeps
   a functional pseudo-class's argument as a raw token run and validates
   nothing, so `_parse_an_b` is this module's job. **An argument that does
   not parse makes the pseudo-class never match, rather than invalidating
   the rule.** The spec says an invalid selector invalidates the style rule
   containing it; for a one-selector rule the two are indistinguishable, but
   for `p:nth-child(banana), a { ... }` the spec drops the whole rule and we
   keep the `a` half. Doing it properly means validating at parse time,
   which means teaching `selectors.py` `An+B` -- worth revisiting, and
   deliberately not done here, because "unknown or malformed things never
   match" is already the rule for pseudo-classes generally (deviation 5 of
   `selectors.py`) and this keeps one rule instead of two.
6. **`An+B` accepts one family of forms the spec rejects, because our
   `<number-token>` has no "sign character present" flag.** css-syntax's
   `<an+b>` grammar distinguishes `<signed-integer>` from
   `<signless-integer>`: `2n+1` and `2n +1` are both valid
   (`<n-dimension> <signed-integer>`, and whitespace between component
   values is allowed), while `2n 1` is not, since a signless integer may
   only follow an explicit `+`/`-` of its own. Tokenized against our own
   `CssTokenizer` rather than assumed, the three are **not** identical:

       2n+1   ->  Dimension(2, 'n'), Number(1)
       2n +1  ->  Dimension(2, 'n'), Whitespace, Number(1)
       2n 1   ->  Dimension(2, 'n'), Whitespace, Number(1)

   `2n+1` has no `Whitespace` at all (an earlier draft of this deviation
   claimed the three-token run for all three forms, which is wrong). What
   *is* true of all three, and is the thing the leniency rests on, is that
   the sign has already been folded into the number's value and its presence
   is not recorded -- `+1` and `1` both arrive as `Number(1)` -- so the only
   pair we could still tell apart (`2n+1` vs the other two) differs by a
   whitespace token that the grammar permits anyway. We accept all three.
   `2n + 1` is **valid** and is accepted for that reason rather than by
   leniency; an earlier draft of this deviation miscalled it invalid.

   The boundary is what the tokens can still tell us. A form whose
   invalidity survives tokenization is rejected: `2n + -1` (a signed
   integer where the grammar wants a signless one, visible as a negative
   `Number` after an explicit sign delim), `+ n` (whitespace across the
   `†` no-whitespace marker, visible as a `Whitespace` token) and `+-n`
   (two signs, visible as a `Delim` before a `-`-initial ident) all parse
   to None -- executed through `_parse_an_b`, not reasoned about. (So do
   the acceptances: `2n+1`, `2n +1`, `2n 1` and `2n + 1` all yield
   `(2, 1)`.) Only the sign-vs-no-sign distinction is unrecoverable, and the
   fix for that belongs in the tokenizer if it ever matters -- the failure
   mode is leniency on input no author writes.
7. **`:nth-child(... of S)` is not supported and never matches.** Selectors
   4 section 6.6.5.2 allows a selector argument that filters what gets
   counted; nothing downstream needs it, and accepting the `of` keyword
   while ignoring the filter would silently match the wrong elements.
8. **`:has()` never matches.** Deviation 3 of `selectors.py` keeps its
   argument as raw tokens because relative selectors (`:has(> p)`) are not
   parsed, so there is nothing here to run.
9. **A pseudo-element never matches an element.** `p::before` selects a box
   that this engine does not generate (Phase 2's known gap 4), and the `p`
   element itself is emphatically not what `p::before` selects -- matching
   it would apply `content`-less declarations to the wrong box. Returning
   False means such rules simply never apply, which is the correct
   behaviour until Phase 3 boxes them.
10. **The dynamic pseudo-classes never match, and so does any pseudo-class
   this module does not know.** `:hover`, `:focus`, `:active`, `:target`,
   `:checked` and friends need a browsing context, input state or a URL
   fragment that this engine has none of; `:visited` additionally must never
   match, since history-leaking through style is the reason the spec limits
   it. There is no allow-list: an unrecognised name falls through to False,
   which is what forward compatibility wants and what deviation 5 of
   `selectors.py` promises. `:link` and `:any-link` *do* match `a`/`area`/
   `link` with an `href`, since "unvisited" is a fact about our
   history-free engine rather than a guess.
11. **`:empty` treats whitespace-only text as empty**, following the Level 4
   definition (an element with no children other than white space and
   comments) rather than Level 3's, where a single space defeated it. Every
   engine ships the Level 4 behaviour.
12. **`:root` is "has no parent element"** rather than "is the document
   element". They differ only for a detached subtree, where the spec says
   nothing useful and the parent-free reading is the one a fragment matcher
   wants.
13. **`candidates()` returns rules in the order they were given to
   `RuleIndex`.** Bucket order would be an implementation detail leaking
   into the cascade's tie-breaking, and iteration over `class_list` -- a
   `frozenset` -- is not even stable between runs, so an order-dependent
   caller would be flaky rather than merely wrong. The cascade must still
   sort by its own explicit source index; this only makes that sort's input
   deterministic.
14. **The `An+B` parse is memoized as an attribute on the
   `PseudoClassSelector` itself** (`_an_b_memo`), rather than in a table
   here. `_nth` otherwise re-parses the argument once per element tested,
   which is per-element work inside the module that exists to avoid
   per-element work.

   A module-level dict keyed on the selector is the obvious alternative and
   is not cheaper: `PseudoClassSelector.__hash__` walks every argument token
   through `_token_key` (deviation 10 of `selectors.py`), which costs about
   what the parse costs. Keying on `id()` is unsafe -- ids are reused after
   a selector is freed, and a stale hit would silently answer with another
   selector's formula.

   Writing an attribute onto another module's dataclass is the cost, and it
   is safe in exactly the way that matters: `_an_b_memo` is a pure function
   of `name` and `argument`, and `PseudoClassSelector`'s equality and hash
   are computed from those fields alone, so a memoized selector still
   compares, hashes and keys a dict identically to a fresh one. It does mean
   deviation 10's "must not be mutated afterwards" now has one sanctioned
   exception. That exception is also recorded in `selectors.py` beside the
   rule it bends, because a reader of that module alone would otherwise
   have no way to know this one had been granted it.
"""

from __future__ import annotations

from typing import Callable, Iterable, Iterator, Sequence

from mayshay.cssparse.selectors import (
    AttributeSelector,
    ClassSelector,
    Complex,
    Compound,
    IdSelector,
    PseudoClassSelector,
    PseudoElementSelector,
    SelectorList,
    Simple,
    TypeSelector,
    UniversalSelector,
)
from mayshay.cssparse.tokenizer import CssToken, Delim, Dimension, Ident, Number, Whitespace
from mayshay.dom.node import Element, Node, Text

# Attributes whose selector value comparison is ASCII case-insensitive for
# HTML elements in an HTML document -- the HTML Standard's
# "Case-sensitivity of selectors" list. See deviation 4.
_HTML_CASE_INSENSITIVE_ATTRS = frozenset({
    "accept", "accept-charset", "align", "alink", "axis", "bgcolor",
    "charset", "checked", "clear", "codetype", "color", "compact",
    "declare", "defer", "dir", "direction", "disabled", "enctype", "face",
    "frame", "hreflang", "http-equiv", "lang", "language", "link", "media",
    "method", "multiple", "nohref", "noresize", "noshade", "nowrap",
    "readonly", "rel", "rev", "rules", "scope", "scrolling", "selected",
    "shape", "target", "text", "type", "valign", "valuetype", "vlink",
})

# Elements for which an `href` attribute makes a link. See deviation 10.
_LINK_ELEMENTS = frozenset({"a", "area", "link"})


def _ascii_lower(text: str) -> str:
    """ASCII-only case fold. Duplicated from `selectors.py` for the reason
    that module duplicates it from `tokenizer.py`: importing another module's
    private name is the worse coupling.
    """
    return "".join(chr(ord(ch) + 0x20) if "A" <= ch <= "Z" else ch for ch in text)


# --------------------------------------------------------------------------
# Tree navigation
# --------------------------------------------------------------------------


def _parent_element(node: Node) -> Element | None:
    """The parent, if it is an Element. `<html>`'s parent is the `Document`,
    which is not an element and so is not an ancestor any selector can name.
    """
    parent = node.parent
    return parent if isinstance(parent, Element) else None


def _element_siblings(element: Element) -> list[Element]:
    """Every element child of this element's parent, in tree order, including
    `element` itself. Built from `parent.children` rather than
    `parent.element_children` because the parent may be a `Document`.
    """
    parent = element.parent
    if parent is None:
        return [element]
    return [child for child in parent.children if isinstance(child, Element)]


def _preceding_element_siblings(element: Element) -> Iterator[Element]:
    """The element siblings before `element`, nearest first.

    Text and comment nodes are skipped, which is the whole point: `p + p`
    must still match across the newline in `<p>a</p>\\n<p>b</p>`.
    """
    parent = element.parent
    if parent is None:
        return
    before: list[Element] = []
    for child in parent.children:
        if child is element:
            break
        if isinstance(child, Element):
            before.append(child)
    yield from reversed(before)


def _index_of(elements: Sequence[Element], element: Element) -> int:
    for i, candidate in enumerate(elements):
        if candidate is element:
            return i
    # Only reachable if `element` is not among its own parent's children,
    # which would mean the tree links disagree with each other.
    raise ValueError("element is not a child of its own parent")


def _element_index0(element: Element) -> int:
    """`element`'s 0-based position among its element siblings.

    Uses the value `dom.annotate_positions` cached if it is there, and
    computes it otherwise: `element_index` is `None` until that pass has run,
    and a matcher that assumed otherwise would silently treat every element
    as the first child.
    """
    if element.element_index is not None:
        return element.element_index
    return _index_of(_element_siblings(element), element)


# --------------------------------------------------------------------------
# Matching
# --------------------------------------------------------------------------


def matches(element: Node, selector: Simple | Compound | Complex) -> bool:
    """Does `element` match `selector`?

    Accepts a simple, compound or complex selector; a `SelectorList` is
    rejected -- see deviation 1. A non-`Element` node matches nothing --
    see deviation 2.
    """
    if isinstance(selector, SelectorList):
        raise TypeError(
            "matches() wants one selector, not a SelectorList: iterate it, "
            "so the caller knows which selector matched and what its "
            "specificity is"
        )
    if not isinstance(element, Element):
        return False
    if isinstance(selector, Complex):
        return _match_from(element, selector, len(selector.compounds) - 1)
    if isinstance(selector, Compound):
        return _matches_compound(element, selector)
    return _matches_simple(element, selector)


def _matches_any(element: Element, selectors: SelectorList) -> bool:
    return any(matches(element, s) for s in selectors.selectors)


def _match_from(element: Element, selector: Complex, index: int) -> bool:
    """Does `element` match `selector`'s compound at `index`, with everything
    to its left satisfied by `element`'s ancestors and preceding siblings?

    The right-to-left walk. Recursion depth is bounded by the number of
    compounds, not the depth of the tree: each call moves one compound left.
    """
    if not _matches_compound(element, selector.compounds[index]):
        return False
    if index == 0:
        return True
    combinator = selector.combinators[index - 1]
    if combinator == ">":
        parent = _parent_element(element)
        return parent is not None and _match_from(parent, selector, index - 1)
    if combinator == " ":
        ancestor = _parent_element(element)
        while ancestor is not None:
            if _match_from(ancestor, selector, index - 1):
                return True
            ancestor = _parent_element(ancestor)
        return False
    if combinator == "+":
        previous = next(_preceding_element_siblings(element), None)
        return previous is not None and _match_from(previous, selector, index - 1)
    if combinator == "~":
        return any(
            _match_from(sibling, selector, index - 1)
            for sibling in _preceding_element_siblings(element)
        )
    raise ValueError(f"unknown combinator {combinator!r}")


def _matches_compound(element: Element, compound: Compound) -> bool:
    return all(_matches_simple(element, simple) for simple in compound.simples)


def _matches_simple(element: Element, simple: Simple) -> bool:
    if isinstance(simple, TypeSelector):
        # `==`, deliberately: see deviation 3.
        return element.tag_name == simple.name
    if isinstance(simple, UniversalSelector):
        return True
    if isinstance(simple, ClassSelector):
        return simple.name in element.class_list
    if isinstance(simple, IdSelector):
        return element.id == simple.name
    if isinstance(simple, AttributeSelector):
        return _matches_attribute(element, simple)
    if isinstance(simple, PseudoClassSelector):
        return _matches_pseudo_class(element, simple)
    if isinstance(simple, PseudoElementSelector):
        # See deviation 9.
        return False
    raise TypeError(f"not a simple selector: {type(simple).__name__}")


# --------------------------------------------------------------------------
# Attribute selectors (Selectors 4 section 5.2)
# --------------------------------------------------------------------------


def _matches_attribute(element: Element, selector: AttributeSelector) -> bool:
    # Both sides of the *name* are already ASCII-lowercased -- the parser by
    # deviation 2 of `selectors.py`, the attribute keys by the tree builder.
    if selector.name not in element.attrs:
        return False
    if selector.operator is None:
        return True
    actual = element.attrs[selector.name]
    wanted = selector.value or ""
    if _attribute_is_case_insensitive(selector):
        actual = _ascii_lower(actual)
        wanted = _ascii_lower(wanted)
    operator = selector.operator
    if operator == "=":
        return actual == wanted
    # Every remaining operator is defined to match nothing when the value is
    # the empty string, rather than matching everything -- `[class^=""]` is
    # the trap, since "" is a prefix of every string.
    if wanted == "":
        return False
    if operator == "~=":
        # Whitespace-separated list membership. A value containing
        # whitespace can never be a member, and `str.split()` splitting on
        # runs is the same rule `Element.class_list` follows.
        return wanted in actual.split()
    if operator == "|=":
        return actual == wanted or actual.startswith(wanted + "-")
    if operator == "^=":
        return actual.startswith(wanted)
    if operator == "$=":
        return actual.endswith(wanted)
    if operator == "*=":
        return wanted in actual
    raise ValueError(f"unknown attribute operator {operator!r}")


def _attribute_is_case_insensitive(selector: AttributeSelector) -> bool:
    """The Level 4 `i` / `s` modifier if there is one, else HTML's own rule
    for this attribute name. See deviation 4.
    """
    if selector.case is not None:
        return selector.case == "i"
    return selector.name in _HTML_CASE_INSENSITIVE_ATTRS


# --------------------------------------------------------------------------
# Pseudo-classes (Selectors 4 section 6)
# --------------------------------------------------------------------------


def _matches_pseudo_class(element: Element, selector: PseudoClassSelector) -> bool:
    name = selector.name  # already ASCII-lowercased by the parser
    if selector.selectors is not None:
        # `:not()`, `:is()`, `:where()`, `:matches()` -- the parser resolved
        # the argument into a nested selector list.
        if name == "not":
            return not _matches_any(element, selector.selectors)
        return _matches_any(element, selector.selectors)

    handler = _PSEUDO_CLASSES.get(name)
    if handler is None:
        # Unknown, dynamic, or functional-but-unsupported: see deviation 10.
        return False
    return handler(element, selector)


def _is_root(element: Element, _selector: PseudoClassSelector) -> bool:
    return _parent_element(element) is None


def _is_empty(element: Element, _selector: PseudoClassSelector) -> bool:
    for child in element.children:
        if isinstance(child, Element):
            return False
        if isinstance(child, Text) and child.data.strip() != "":
            return False
    return True


def _is_link(element: Element, _selector: PseudoClassSelector) -> bool:
    return element.tag_name in _LINK_ELEMENTS and "href" in element.attrs


def _same_type(element: Element) -> list[Element]:
    return [s for s in _element_siblings(element) if s.tag_name == element.tag_name]


def _is_first_child(element: Element, _selector: PseudoClassSelector) -> bool:
    return _element_index0(element) == 0


def _is_last_child(element: Element, _selector: PseudoClassSelector) -> bool:
    siblings = _element_siblings(element)
    return siblings[-1] is element


def _is_only_child(element: Element, _selector: PseudoClassSelector) -> bool:
    return len(_element_siblings(element)) == 1


def _is_first_of_type(element: Element, _selector: PseudoClassSelector) -> bool:
    return _same_type(element)[0] is element


def _is_last_of_type(element: Element, _selector: PseudoClassSelector) -> bool:
    return _same_type(element)[-1] is element


def _is_only_of_type(element: Element, _selector: PseudoClassSelector) -> bool:
    return len(_same_type(element)) == 1


def _nth_child(element: Element, selector: PseudoClassSelector) -> bool:
    return _nth(selector, _element_index0(element) + 1)


def _nth_last_child(element: Element, selector: PseudoClassSelector) -> bool:
    siblings = _element_siblings(element)
    return _nth(selector, len(siblings) - _element_index0(element))


def _nth_of_type(element: Element, selector: PseudoClassSelector) -> bool:
    same = _same_type(element)
    return _nth(selector, _index_of(same, element) + 1)


def _nth_last_of_type(element: Element, selector: PseudoClassSelector) -> bool:
    same = _same_type(element)
    return _nth(selector, len(same) - _index_of(same, element))


_PSEUDO_CLASSES: dict[str, Callable[[Element, PseudoClassSelector], bool]] = {
    "root": _is_root,
    "empty": _is_empty,
    "link": _is_link,
    "any-link": _is_link,
    "first-child": _is_first_child,
    "last-child": _is_last_child,
    "only-child": _is_only_child,
    "first-of-type": _is_first_of_type,
    "last-of-type": _is_last_of_type,
    "only-of-type": _is_only_of_type,
    "nth-child": _nth_child,
    "nth-last-child": _nth_last_child,
    "nth-of-type": _nth_of_type,
    "nth-last-of-type": _nth_last_of_type,
}


# --------------------------------------------------------------------------
# An+B (css-syntax-3 section 6, "The <an+b> type")
# --------------------------------------------------------------------------


def _nth(selector: PseudoClassSelector, index: int) -> bool:
    """Does the 1-based `index` satisfy this pseudo-class's An+B argument?

    The parse is memoized on the selector -- see deviation 14. Without it,
    `:nth-child(2n+1)` re-parses its own grammar once per element tested,
    inside the one module whose whole purpose is not doing per-element work.
    """
    try:
        parsed = selector._an_b_memo
    except AttributeError:
        parsed = selector._an_b_memo = _parse_an_b(selector.argument)
    if parsed is None:
        # Missing or malformed argument: never matches. See deviation 5.
        return False
    a, b = parsed
    return _an_b_contains(a, b, index)


def _an_b_contains(a: int, b: int, index: int) -> bool:
    """`index` matches An+B iff index == a*n + b for some integer n >= 0."""
    if a == 0:
        return index == b
    offset = index - b
    return offset % a == 0 and offset // a >= 0


def _strip_whitespace(tokens: Sequence[CssToken]) -> list[CssToken]:
    out = list(tokens)
    while out and isinstance(out[0], Whitespace):
        out.pop(0)
    while out and isinstance(out[-1], Whitespace):
        out.pop()
    return out


def _parse_an_b(argument: Iterable[CssToken] | None) -> tuple[int, int] | None:
    """The An+B micro-grammar, over the raw token run the parser kept.

    Returns `(a, b)`, or None for anything that does not parse -- including
    the `of S` form, which parses per spec but is not supported here (see
    deviations 5 and 7).
    """
    if argument is None:
        return None
    tokens = _strip_whitespace(argument)
    if not tokens:
        return None

    first = tokens[0]
    rest = tokens[1:]

    if isinstance(first, Ident):
        keyword = _ascii_lower(first.value)
        if keyword == "odd":
            return (2, 1) if not rest else None
        if keyword == "even":
            return (2, 0) if not rest else None
        return _parse_n_ident(keyword, rest)

    if isinstance(first, Delim) and first.value == "+":
        # `+n`, `+n+1`, ... The spec forbids whitespace between the `+` and
        # the `n`, which is why this is a delim and not part of the ident;
        # a `Whitespace` here fails the `Ident` test below, which is how
        # `+ n` is rejected.
        if not rest or not isinstance(rest[0], Ident):
            return None
        ident = _ascii_lower(rest[0].value)
        if ident.startswith("-"):
            # `'+'? n`, not `'+'? -n`: `+-n` carries two signs and is not a
            # production. Found in review; see deviation 6 for why this one
            # is rejected where the signless forms are not.
            return None
        return _parse_n_ident(ident, rest[1:])

    if isinstance(first, Dimension):
        if not first.is_integer:
            return None
        return _parse_n_unit(_ascii_lower(first.unit), int(first.value), rest)

    if isinstance(first, Number):
        # A bare `<integer>`: A is zero.
        if not first.is_integer or rest:
            return None
        return (0, int(first.value))

    return None


def _parse_n_ident(ident: str, rest: list[CssToken]) -> tuple[int, int] | None:
    """`n`, `-n`, `n-3`, `-n-3`, `n-`, `-n-` and the B that may follow."""
    if ident.startswith("-"):
        sign, tail = -1, ident[1:]
    else:
        sign, tail = 1, ident
    return _parse_n_unit(tail, sign, rest)


def _parse_n_unit(unit: str, a: int, rest: list[CssToken]) -> tuple[int, int] | None:
    """`unit` is the part from the `n` onwards -- `n`, `n-` or `n-<digits>`
    -- and `a` is the multiplier already read from in front of it.
    """
    if unit == "n":
        b = _parse_b(rest)
        return None if b is None else (a, b)
    if unit == "n-":
        # `n- 3` means n-3: a signless integer follows, negated.
        digits = _strip_whitespace(rest)
        if len(digits) != 1 or not isinstance(digits[0], Number):
            return None
        if not digits[0].is_integer or digits[0].value < 0:
            return None
        return (a, -int(digits[0].value))
    if unit.startswith("n-") and _is_ascii_digits(unit[2:]):
        # `n-3` arrived as one token: `2n-1` tokenizes as
        # Dimension(2, 'n-1'), and `n-1` as Ident('n-1').
        return (a, -int(unit[2:])) if not rest else None
    return None


def _is_ascii_digits(text: str) -> bool:
    """`str.isdigit()` says yes to non-ASCII digits, which `int()` then
    happily converts -- `n-\u0663` is not `n-3`.
    """
    return text != "" and all("0" <= ch <= "9" for ch in text)


def _parse_b(rest: list[CssToken]) -> int | None:
    """The optional B half, after an `n` that ended a token."""
    tokens = _strip_whitespace(rest)
    if not tokens:
        return 0
    first = tokens[0]
    if isinstance(first, Number):
        # `2n+1` (sign inside the number token) or `2n 1` (invalid per spec,
        # indistinguishable here -- see deviation 6).
        if not first.is_integer or len(tokens) != 1:
            return None
        return int(first.value)
    if isinstance(first, Delim) and first.value in ("+", "-"):
        sign = 1 if first.value == "+" else -1
        tail = _strip_whitespace(tokens[1:])
        if len(tail) != 1 or not isinstance(tail[0], Number):
            return None
        if not tail[0].is_integer or tail[0].value < 0:
            return None
        return sign * int(tail[0].value)
    # Anything else -- `of .a`, junk -- does not parse.
    return None


# --------------------------------------------------------------------------
# Rule indexing
# --------------------------------------------------------------------------


def _default_selector_of(rule: object) -> Complex:
    """How `RuleIndex` finds a rule's selector when it was not told.

    Handles the two shapes worth guessing: a bare `Complex` (which is its own
    rule, and is what the tests index), and anything carrying one on a
    `.selector` attribute. Everything else raises rather than being dropped
    into the catch-all bucket -- a rule whose selector cannot be found is a
    caller error, and bucketing it as universal would hide that behind a
    rule that merely never matches.
    """
    if isinstance(rule, Complex):
        return rule
    selector = getattr(rule, "selector", None)
    if isinstance(selector, Complex):
        return selector
    if isinstance(rule, SelectorList) or isinstance(selector, SelectorList):
        raise TypeError(
            "RuleIndex wants one Complex selector per rule, not a "
            "SelectorList: expand `p, .a { ... }` into one entry per "
            "selector, since each has its own specificity"
        )
    raise TypeError(
        f"cannot find a selector on {type(rule).__name__}; pass "
        f"selector_of= to tell RuleIndex where it is"
    )


class RuleIndex:
    """Rules bucketed by the id, class or type in their rightmost compound.

    `candidates(element)` returns the rules that *could* match `element`,
    which is a superset of the rules that do: it never runs the matcher, it
    only rules out rules whose rightmost compound names an id, class or type
    the element does not have. That superset property is the whole contract
    -- a rule missing from `candidates` can never be applied, so it must be
    conservative in exactly one direction.

    A rule is filed under at most one key, id before class before type, and
    the rightmost compound is the one the element itself must match, so a
    rule appears in `candidates` at most once. A rightmost compound naming
    none of the three (`*`, `[hidden]`, `:hover`, `:is(.a, .b)`) goes to the
    catch-all bucket, which every element gets.
    """

    def __init__(
        self,
        rules: Iterable[object],
        selector_of: Callable[[object], Complex] | None = None,
    ) -> None:
        self._selector_of = selector_of or _default_selector_of
        self._by_id: dict[str, list[tuple[int, object]]] = {}
        self._by_class: dict[str, list[tuple[int, object]]] = {}
        self._by_tag: dict[str, list[tuple[int, object]]] = {}
        self._catch_all: list[tuple[int, object]] = []
        self._count = 0
        for order, rule in enumerate(rules):
            self._bucket_for(self._selector_of(rule)).append((order, rule))
            self._count = order + 1

    def __len__(self) -> int:
        return self._count

    def _bucket_for(self, selector: Complex) -> list[tuple[int, object]]:
        simples = selector.compounds[-1].simples
        for simple in simples:
            if isinstance(simple, IdSelector):
                return self._by_id.setdefault(simple.name, [])
        for simple in simples:
            if isinstance(simple, ClassSelector):
                return self._by_class.setdefault(simple.name, [])
        for simple in simples:
            if isinstance(simple, TypeSelector):
                return self._by_tag.setdefault(simple.name, [])
        return self._catch_all

    def candidates(self, element: Node) -> list[object]:
        """The rules worth testing against `element`, in the order they were
        given to the constructor -- see deviation 13.
        """
        if not isinstance(element, Element):
            return []
        found = list(self._catch_all)
        element_id = element.id
        if element_id is not None:
            found.extend(self._by_id.get(element_id, ()))
        for name in element.class_list:
            found.extend(self._by_class.get(name, ()))
        found.extend(self._by_tag.get(element.tag_name, ()))
        found.sort(key=lambda pair: pair[0])
        return [rule for _, rule in found]
