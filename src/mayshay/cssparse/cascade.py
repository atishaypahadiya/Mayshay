"""
Mayshay's cascade, inheritance and computed values.

Task J of Phase 2 -- the stage everything before it feeds. Tokenizer, parser,
selector parser, specificity, matcher and value parser all exist so that this
module can answer one question for every node in the tree: *what does it
actually look like?* The answer is a `ComputedStyle`, attached to
`Node.computed_style`.

    from mayshay.cssparse.cascade import style_document
    metrics = style_document(document, [css_text, ...])

`style_document` returns a `Counter` shaped for `metrics.emit`. It does not
write it: drivers own persistence (see `mayshay.metrics`), and a library that
writes files as a side effect of being called is a library people stop
calling. `scripts/style_report.py` is the caller that does the writing.


The one error this module exists to not make
--------------------------------------------

`em` resolves against a different base depending on which property it is in:

* On `font-size`, `1.5em` means 1.5x the **parent's** computed font-size.
* On every other property, `2em` means 2x the **element's own** computed
  font-size -- the one that was just computed on the line above.

Getting the pair backwards yields numbers that look entirely reasonable and
text that is quietly the wrong size, and it is invisible until Phase 3 draws
a box. So the two are not one function with a flag. They are two functions
with different parameter lists:

    _compute_font_size(declared, *, parent_font_px, root_font_px) -> Length
    _compute_rest(style, declared, *, own_font_px, root_font_px, own_color)

`_compute_font_size` is never given the element's own font-size, because that
is the thing it is computing. `_compute_rest` is never given the parent's,
because it must not use it -- there is no parameter to pass it through, so
the mistake cannot be made by editing one line inside the function. That is
also why the tree walk is top-down and in document order: an element's own
font-size has to exist before anything else on that element can resolve.

`rem` is the third base and is deliberately separate again -- the *root*
element's computed font-size, threaded through the walk rather than
recomputed, with the initial 16px standing in while the root element itself
is being computed (a `html { font-size: 2rem }` refers to the initial value,
per CSS Values 4).


Computed is not used
--------------------

`width: 50%` and `margin: auto` reach `ComputedStyle` as `Percent(50)` and
the `AUTO` sentinel, unchanged. Neither can be resolved without a containing
block, and no containing block exists until layout. Anything that collapses
them to a float here -- `auto` as `0`, `50%` as `0.5` -- bakes a guess into a
value three stages before the guess can be checked. `values.py` keeps them
symbolic on the way in; this module's job is to not undo that.

The same principle applies to the units this module cannot resolve either:
`vw`/`vh`/`vmin`/`vmax` need a viewport, which arrives with layout, so they
stay as `Length(60, "vw")` rather than being multiplied by a made-up 1280.
Absolute units (`in`, `pt`, `pc`, `cm`, `mm`, `q`) and font-relative units
(`em`, `rem`, `ex`, `ch`) *are* resolved to `px`, because they can be.


Cascade order
-------------

Sorted by `(rank, specificity, source_order)`, highest wins, where `rank` is:

    0  UA, normal
    1  author rule, normal
    2  `style=` attribute, normal
    3  author rule, `!important`
    4  `style=` attribute, `!important`
    5  UA, `!important`

That is CSS Cascade 4's origin/importance table, with the style attribute
occupying its own level either side of author rules rather than being given
a fake specificity of `(1, 0, 0)`. The fake-specificity trick is the common
shortcut and it is wrong in a way that shows up on real pages: an author
rule with two id selectors would beat `style=`, and it must not.

`source_order` is a *per-declaration* counter, not a per-rule one, so
`p { color: red; color: blue }` resolves the way it reads. Every selector in
a selector list shares its block's declaration numbers, which is correct --
they are the same source position -- and their differing specificities break
any tie that matters.


Deliberate deviations and omissions
-----------------------------------

1. **`inherit`, `initial`, `unset`, `revert` are not supported.** `values.py`
   rejects them (its deviation 3), so a declaration using one is dropped and
   counted in `declarations_dropped`. Implementing them means intercepting
   the keyword before the value parser sees it; it is a listed Phase 3 gap.
2. **`@media`, `@supports` and `@import` are counted and skipped**, not
   evaluated -- `at_rules_skipped`. Every rule inside a `@media` block is
   therefore absent from the cascade, not applied unconditionally. Applying
   them would be worse: `@media print` would repaint the screen.
3. **`<link rel=stylesheet>` is counted, never fetched** -- `net/` is Phase
   5. See `_count_link_stylesheets` for why the count is worth having.
4. **`:hover`, `:focus`, `:visited` and friends never match** (matching.py's
   own deviation): there is no interaction and no history. `:link` matches
   any `a[href]`, so link colouring is at least approximately right.
5. **Pseudo-element rules (`p::before`) are matched against nothing.**
   `matches()` returns False for a compound containing one, so the rule is
   parsed, indexed, and never applied. No boxes are generated for them.
6. **`display` and `border-*-style` are stored as plain `str`**, not as
   `values.Keyword`. They are keyword-valued properties whose computed value
   *is* the keyword; layout will compare them against string literals, and
   `Keyword("block") == "block"` is False, which is a trap not worth
   keeping. Every other property keeps its typed value.
7. **`currentcolor` is resolved here**, which is the earliest point it can
   be: on `color` itself it means the inherited colour, and on
   `background-color`/`border-*-color` it means this element's own computed
   `color`. `values.py` deliberately left it as `Keyword("currentcolor")`
   because it had no cascade to consult.
8. **The initial value of `border-*-width` is `Length(0, "px")`, not the
   spec's `medium`.** `values.py` does not parse the `thin|medium|thick`
   trio (its deviation 8), and a border whose style is the initial `none`
   has a used width of zero regardless, so zero is the honest default. If
   the keyword trio is ever added, this becomes 3px and `border-style: none`
   has to zero it at used-value time.
9. **Quirks mode is not consulted.** `Document.mode` is classified by Task C
   and acted on in layout: unitless lengths and the alternate box model are
   used-value concerns.
10. **The `author_css` argument is cascaded before the document's own
    `<style>` elements.** The two cannot be interleaved without knowing
    where the caller's sheets sat in the source, and the argument's real
    role is standing in for the external sheets a `<link>` in `<head>`
    would have pulled in -- which do precede in-document `<style>` on the
    overwhelming majority of pages. Within each group, source order holds.
"""

from __future__ import annotations

import time
from collections import Counter
from dataclasses import dataclass, field, fields

from mayshay.cssparse.matching import RuleIndex, matches
from mayshay.cssparse.parser import AtRule, CssParser, QualifiedRule
from mayshay.cssparse.selectors import (
    Complex,
    SelectorParseError,
    parse_selector_list,
    specificity,
)
from mayshay.cssparse.tokenizer import CssTokenizer
from mayshay.cssparse.ua import UA_CSS
from mayshay.cssparse.values import (
    AUTO,
    Color,
    Keyword,
    Length,
    Percent,
    parse_declaration_value,
)
from mayshay.dom.node import Element, Node, Text, annotate_positions

# --------------------------------------------------------------------------
# The property set
# --------------------------------------------------------------------------

# The nine properties of `values.py`, after shorthand expansion. `margin`,
# `padding` and `border` never appear as themselves in a ComputedStyle --
# `parse_declaration_value` has already expanded them.
LONGHANDS: tuple[str, ...] = (
    "display",
    "width",
    "height",
    "margin-top", "margin-right", "margin-bottom", "margin-left",
    "padding-top", "padding-right", "padding-bottom", "padding-left",
    "border-top-width", "border-right-width",
    "border-bottom-width", "border-left-width",
    "border-top-style", "border-right-style",
    "border-bottom-style", "border-left-style",
    "border-top-color", "border-right-color",
    "border-bottom-color", "border-left-color",
    "color",
    "background-color",
    "font-size",
)

# Of the nine, exactly these two inherit. `display`, the box-model
# properties and `background-color` do not -- a `<p>` inside a bordered
# `<div>` does not get its own border, and that is not an oversight in the
# table, it is what the CSS property definitions say.
INHERITED: frozenset[str] = frozenset({"color", "font-size"})

# `medium`. The one number in this module that is a convention rather than a
# derivation; every `em`, `rem` and `%` font-size on a page with no explicit
# root font-size is ultimately a multiple of it.
INITIAL_FONT_SIZE_PX = 16.0

_ZERO_LENGTH = Length(0, "px")
_INITIAL_COLOR = Color(0, 0, 0, 1.0)
_TRANSPARENT = Color(0, 0, 0, 0.0)


def _field_name(prop: str) -> str:
    return prop.replace("-", "_")


@dataclass
class ComputedStyle:
    """One field per longhand, holding that property's *computed* value.

    Mutable, and mutated in place while an element is being computed --
    `font-size` first, then `color`, then everything else, each step reading
    what the previous one wrote. Copying between the steps would buy nothing
    but garbage; nothing outside this module holds a reference to a style
    while it is being built.

    Defaults are the CSS initial values (see deviation 8 for the one that
    is not).
    """

    display: str = "inline"
    width: object = AUTO
    height: object = AUTO

    margin_top: object = _ZERO_LENGTH
    margin_right: object = _ZERO_LENGTH
    margin_bottom: object = _ZERO_LENGTH
    margin_left: object = _ZERO_LENGTH

    padding_top: object = _ZERO_LENGTH
    padding_right: object = _ZERO_LENGTH
    padding_bottom: object = _ZERO_LENGTH
    padding_left: object = _ZERO_LENGTH

    border_top_width: object = _ZERO_LENGTH
    border_right_width: object = _ZERO_LENGTH
    border_bottom_width: object = _ZERO_LENGTH
    border_left_width: object = _ZERO_LENGTH

    border_top_style: str = "none"
    border_right_style: str = "none"
    border_bottom_style: str = "none"
    border_left_style: str = "none"

    border_top_color: object = _INITIAL_COLOR
    border_right_color: object = _INITIAL_COLOR
    border_bottom_color: object = _INITIAL_COLOR
    border_left_color: object = _INITIAL_COLOR

    color: object = _INITIAL_COLOR
    background_color: object = _TRANSPARENT

    font_size: object = Length(INITIAL_FONT_SIZE_PX, "px")

    def get(self, prop: str) -> object:
        return getattr(self, _field_name(prop))

    def set(self, prop: str, value: object) -> None:
        setattr(self, _field_name(prop), value)

    @property
    def font_size_px(self) -> float:
        """The computed font-size as a number, for resolving `em`.

        Always a `px` `Length` by construction -- `_compute_font_size`
        cannot return anything else, and a font-size it could not resolve
        leaves the inherited value in place rather than storing a unit
        nobody downstream could use.
        """
        value = self.font_size
        assert isinstance(value, Length) and value.unit == "px", value
        return float(value.value)


# A sanity check that the dataclass and the property list cannot drift: a
# longhand added to one and forgotten in the other is a property that
# silently never cascades.
_STYLE_FIELDS = {f.name for f in fields(ComputedStyle)}
assert _STYLE_FIELDS == {_field_name(p) for p in LONGHANDS}, (
    "ComputedStyle fields and LONGHANDS disagree: "
    f"{_STYLE_FIELDS ^ {_field_name(p) for p in LONGHANDS}}"
)


# --------------------------------------------------------------------------
# Unit resolution
# --------------------------------------------------------------------------

# CSS Values 4 section 6.2: the absolute lengths, in px. `1in == 96px` is the
# anchor and everything else is defined off it.
_ABSOLUTE_PX = {
    "px": 1.0,
    "in": 96.0,
    "pc": 16.0,          # 1pc == 1/6in
    "pt": 96.0 / 72.0,
    "cm": 96.0 / 2.54,
    "mm": 96.0 / 25.4,
    "q": 96.0 / 25.4 / 4.0,  # a quarter-millimetre
}

# `ex` and `ch` are font *metrics* -- the x-height and the advance of "0" --
# which need a loaded font this engine does not have. The spec's own
# fallbacks when the metrics are unavailable are 0.5em and 0.5em
# respectively, which is what these are. They are approximations, flagged as
# such, not measurements.
_EM_MULTIPLE = {"em": 1.0, "ex": 0.5, "ch": 0.5}

# Need a viewport. Kept symbolic -- see the module docstring.
_VIEWPORT_UNITS = frozenset({"vw", "vh", "vmin", "vmax"})


def _length_to_px(
    length: Length, *, font_px: float, root_px: float
) -> float | None:
    """`length` in px, or None if it cannot be resolved without a viewport.

    `font_px` is whichever font-size this property resolves `em` against --
    the caller's choice, and the whole point of the caller being two
    different functions.
    """
    unit = length.unit
    factor = _ABSOLUTE_PX.get(unit)
    if factor is not None:
        return round(length.value * factor, 6)
    multiple = _EM_MULTIPLE.get(unit)
    if multiple is not None:
        return round(length.value * multiple * font_px, 6)
    if unit == "rem":
        return round(length.value * root_px, 6)
    if unit in _VIEWPORT_UNITS:
        return None
    raise ValueError(f"unhandled length unit {unit!r}")


# CSS Fonts 4 section 3.1's absolute-size keywords, as a multiple of the
# `medium` 16px: 3/5, 3/4, 8/9, 1, 6/5, 3/2, 2, 3.
_ABSOLUTE_FONT_SIZE_PX = {
    "xx-small": INITIAL_FONT_SIZE_PX * 3 / 5,
    "x-small": INITIAL_FONT_SIZE_PX * 3 / 4,
    "small": INITIAL_FONT_SIZE_PX * 8 / 9,
    "medium": INITIAL_FONT_SIZE_PX,
    "large": INITIAL_FONT_SIZE_PX * 6 / 5,
    "x-large": INITIAL_FONT_SIZE_PX * 3 / 2,
    "xx-large": INITIAL_FONT_SIZE_PX * 2,
    "xxx-large": INITIAL_FONT_SIZE_PX * 3,
}

# `smaller`/`larger` are relative to the parent, by a factor the spec leaves
# to the UA; 1.2 is what every engine uses.
_RELATIVE_FONT_SIZE_FACTOR = 1.2


# --------------------------------------------------------------------------
# The two em paths. Do not merge these.
# --------------------------------------------------------------------------


def _compute_font_size(
    declared: object | None, *, parent_font_px: float, root_font_px: float
) -> Length | None:
    """`font-size`'s computed value, or None if `declared` cannot resolve.

    **`em` and `%` here are relative to the PARENT's font-size.** This
    function is deliberately not given the element's own -- it is computing
    it, so there is nothing to be given. The absence of that parameter is
    the guarantee; a reviewer can confirm the rule holds by reading the
    signature rather than the body.

    Returns None for a viewport-relative font-size, which the caller treats
    as "declaration could not be computed" and leaves the inherited value
    alone -- rather than storing a `Length(4, "vw")` that
    `ComputedStyle.font_size_px` could not turn into a number for any of
    this element's children.
    """
    if declared is None:
        return None
    if isinstance(declared, Keyword):
        absolute = _ABSOLUTE_FONT_SIZE_PX.get(declared.name)
        if absolute is not None:
            return Length(round(absolute, 6), "px")
        if declared.name == "smaller":
            return Length(
                round(parent_font_px / _RELATIVE_FONT_SIZE_FACTOR, 6), "px"
            )
        if declared.name == "larger":
            return Length(
                round(parent_font_px * _RELATIVE_FONT_SIZE_FACTOR, 6), "px"
            )
        return None
    if isinstance(declared, Percent):
        return Length(round(parent_font_px * declared.value / 100.0, 6), "px")
    if isinstance(declared, Length):
        px = _length_to_px(
            declared, font_px=parent_font_px, root_px=root_font_px
        )
        return None if px is None else Length(px, "px")
    return None


def _compute_rest(
    style: ComputedStyle,
    declared: dict[str, object],
    *,
    own_font_px: float,
    root_font_px: float,
    own_color: object,
) -> int:
    """Compute every property except `font-size` onto `style`. Returns the
    number of declarations applied.

    **`em` here is relative to the ELEMENT'S OWN font-size**, which is
    `own_font_px` and which the caller has already computed. There is no
    `parent_font_px` parameter, and there must not be one: the parent's
    font-size is not an input to any property on this list, and the only
    reliable way to keep it from being used is for it not to be in scope.

    `%` is *not* resolved -- see the module docstring. Nor is `auto`.
    """
    applied = 0
    for prop, value in declared.items():
        if prop == "font-size":
            continue
        style.set(
            prop,
            _computed_value(
                value,
                font_px=own_font_px,
                root_px=root_font_px,
                own_color=own_color,
            ),
        )
        applied += 1
    return applied


def _computed_value(
    value: object, *, font_px: float, root_px: float, own_color: object
) -> object:
    """One specified value -> its computed value.

    `Percent` and `AUTO` fall through untouched, which is the point.
    """
    if isinstance(value, Keyword):
        if value.name == "currentcolor":
            return own_color
        # `display`, `border-*-style`: the computed value is the keyword,
        # stored as a plain string. See deviation 6.
        return value.name
    if isinstance(value, Length):
        px = _length_to_px(value, font_px=font_px, root_px=root_px)
        return value if px is None else Length(px, "px")
    return value


# --------------------------------------------------------------------------
# Rules
# --------------------------------------------------------------------------

# Cascade origin / importance levels; higher wins. See the module docstring
# for why `style=` gets its own two levels instead of a forged specificity.
_RANK_UA_NORMAL = 0
_RANK_AUTHOR_NORMAL = 1
_RANK_INLINE_NORMAL = 2
_RANK_AUTHOR_IMPORTANT = 3
_RANK_INLINE_IMPORTANT = 4
_RANK_UA_IMPORTANT = 5

_NORMAL_RANK = {"ua": _RANK_UA_NORMAL, "author": _RANK_AUTHOR_NORMAL}
_IMPORTANT_RANK = {"ua": _RANK_UA_IMPORTANT, "author": _RANK_AUTHOR_IMPORTANT}


@dataclass
class _Declaration:
    """One longhand from one source position."""

    prop: str
    value: object
    rank: int
    order: int


@dataclass
class _StyleRule:
    """One selector plus the declarations its block contributes.

    One `_StyleRule` per *selector*, not per rule: `p, #x { color: red }` is
    two, because they have different specificities and only their own
    specificity may be compared. They share the same `_Declaration` objects
    -- same source position, same order numbers -- which is exactly right.
    """

    selector: Complex
    specificity: tuple[int, int, int]
    declarations: list[_Declaration] = field(default_factory=list)


def _selector_of(rule: object) -> Complex:
    """The `selector_of` hook `RuleIndex` takes.

    Passed explicitly rather than leaning on `RuleIndex`'s default
    `.selector` sniffing: the index's bucketing is the thing that decides
    which rules a page ever considers, and it should not depend on an
    attribute name matching by luck.
    """
    assert isinstance(rule, _StyleRule)
    return rule.selector


def _parse_sheet(
    source: str, origin: str, order: object, metrics: Counter[str]
) -> list[_StyleRule]:
    """Parse one stylesheet into `_StyleRule`s.

    `order` is a shared counter (an `itertools.count`-alike; anything with
    `__next__`) so declaration numbers keep increasing across every sheet in
    the document, which is what makes later sheets win ties against earlier
    ones.
    """
    parser = CssParser(source)
    rules: list[_StyleRule] = []
    for rule in parser.parse_stylesheet():
        if isinstance(rule, AtRule):
            # Deviation 2: counted, not evaluated, and its block's rules are
            # therefore not in the cascade at all.
            metrics["at_rules_skipped"] += 1
            continue
        assert isinstance(rule, QualifiedRule)
        if rule.block is None:
            continue
        try:
            selector_list = parse_selector_list(rule.prelude)
        except SelectorParseError:
            # An unparseable prelude invalidates the whole rule, block
            # included -- CSS Syntax 3 section 5.4.1. Not the declarations
            # one at a time; the rule.
            metrics["selectors_invalid"] += 1
            continue
        declarations = _parse_block(parser, rule.block, origin, order, metrics)
        if not declarations:
            continue
        for selector in selector_list.selectors:
            rules.append(
                _StyleRule(
                    selector=selector,
                    specificity=specificity(selector),
                    declarations=declarations,
                )
            )
    metrics["tokenizer_parse_errors"] += parser.tokenizer.metrics["parse_errors"]
    metrics["css_parse_errors"] += len(parser.errors)
    return rules


def _parse_block(
    parser: CssParser,
    block: list,
    origin: str,
    order: object,
    metrics: Counter[str],
) -> list[_Declaration]:
    out: list[_Declaration] = []
    for decl in parser.parse_declarations(block):
        metrics["declarations_seen"] += 1
        longhands = parse_declaration_value(decl.name, decl.value)
        if longhands is None:
            # Either a property outside our nine, or a value whose grammar
            # is wrong. Both drop the declaration and keep its siblings,
            # which is what a browser does.
            metrics["declarations_dropped"] += 1
            continue
        rank = (_IMPORTANT_RANK if decl.important else _NORMAL_RANK)[origin]
        index = next(order)
        for prop, value in longhands.items():
            out.append(_Declaration(prop, value, rank, index))
        metrics["declarations_kept"] += 1
    return out


def _parse_inline_style(
    source: str, order: object, metrics: Counter[str]
) -> list[_Declaration]:
    """The `style=` attribute: a declaration list, no selector, own rank."""
    parser = CssParser("")
    tokens = list(CssTokenizer(source).tokenize())
    out: list[_Declaration] = []
    for decl in parser.parse_declarations(tokens):
        metrics["declarations_seen"] += 1
        longhands = parse_declaration_value(decl.name, decl.value)
        if longhands is None:
            metrics["declarations_dropped"] += 1
            continue
        rank = (
            _RANK_INLINE_IMPORTANT if decl.important else _RANK_INLINE_NORMAL
        )
        index = next(order)
        for prop, value in longhands.items():
            out.append(_Declaration(prop, value, rank, index))
        metrics["declarations_kept"] += 1
    return out


# --------------------------------------------------------------------------
# Document scanning
# --------------------------------------------------------------------------


def _iter_nodes(root: Node):
    """Pre-order, document order. Explicit stack: real pages nest deeply
    enough (wikipedia.html gets past 30) that recursion is a needless risk.
    """
    stack: list[Node] = [root]
    while stack:
        node = stack.pop()
        yield node
        stack.extend(reversed(node.children))


def _rel_tokens(element: Element) -> set[str]:
    """`rel` is a space-separated token list, ASCII case-insensitive."""
    return {token.lower() for token in element.attrs.get("rel", "").split()}


def _count_link_stylesheets(elements: list[Element], metrics: Counter[str]) -> None:
    """Count `<link rel=stylesheet>`, do not fetch it.

    `net/` arrives in Phase 5. Counting turns "no styles applied" from a
    blank render into a number, and the fraction of real pages that depend
    entirely on external CSS is itself a finding for the analysis half of
    this project -- hn.html has exactly one stylesheet link and no `<style>`
    element at all, so the count is the difference between "we styled it"
    and "we styled the UA sheet".

    `rel=icon`, `rel=preconnect`, `rel=canonical` and the rest do not count:
    they are not stylesheets. A `rel=stylesheet` with no `href` does not
    count either -- there is nothing that would have been fetched.
    `rel="alternate stylesheet"` does count; it is a stylesheet the user
    could select, and treating it as one over-counts by a rounding error on
    the corpus while under-counting would hide whole sheets.
    """
    for element in elements:
        if element.tag_name != "link":
            continue
        if "stylesheet" not in _rel_tokens(element):
            continue
        if not element.attrs.get("href", "").strip():
            continue
        metrics["link_stylesheets_skipped"] += 1


def _style_element_source(element: Element) -> str | None:
    """A `<style>` element's CSS text, or None if it is not CSS.

    `type` absent or `text/css` means CSS; anything else (`text/less`,
    `text/template`) is content this engine must not try to parse as a
    stylesheet.
    """
    declared_type = element.attrs.get("type", "").strip().lower()
    if declared_type not in ("", "text/css"):
        return None
    return "".join(
        child.data for child in element.children if isinstance(child, Text)
    )


# --------------------------------------------------------------------------
# The walk
# --------------------------------------------------------------------------


class _Counter:
    """A monotonically increasing declaration counter.

    A three-line class instead of `itertools.count` only so the type in the
    signatures above reads as what it is.
    """

    def __init__(self) -> None:
        self._n = 0

    def __next__(self) -> int:
        self._n += 1
        return self._n


def _winning_declarations(
    element: Element,
    index: RuleIndex,
    inline: list[_Declaration],
    metrics: Counter[str],
) -> dict[str, object]:
    """The cascade, for one element: every matching declaration, with the
    winner kept per property.

    Sorting the whole list would be tidier and slower; a running max over
    `(rank, specificity, order)` is the same answer in one pass.
    """
    best: dict[str, tuple[int, tuple[int, int, int], int]] = {}
    winner: dict[str, object] = {}

    def offer(decl: _Declaration, spec: tuple[int, int, int]) -> None:
        key = (decl.rank, spec, decl.order)
        current = best.get(decl.prop)
        if current is None or key > current:
            best[decl.prop] = key
            winner[decl.prop] = decl.value

    for rule in index.candidates(element):
        assert isinstance(rule, _StyleRule)
        metrics["rules_considered"] += 1
        if not matches(element, rule.selector):
            continue
        metrics["rules_matched"] += 1
        for decl in rule.declarations:
            offer(decl, rule.specificity)

    for decl in inline:
        # The style attribute has no selector, so no specificity to compare;
        # its rank already separates it from every author rule.
        offer(decl, (0, 0, 0))

    return winner


def _compute_style(
    parent: ComputedStyle,
    declared: dict[str, object],
    root_font_px: float,
    metrics: Counter[str],
) -> ComputedStyle:
    """Compute one element's style. The order of the three steps below is
    the whole subject of this module."""
    style = _inherit_from(parent)

    # 1. font-size, against the PARENT's. Nothing else may be computed
    #    first, because everything else needs the answer.
    font_size = _compute_font_size(
        declared.get("font-size"),
        parent_font_px=parent.font_size_px,
        root_font_px=root_font_px,
    )
    if font_size is not None:
        style.font_size = font_size
    elif "font-size" in declared:
        # Declared but not computable -- a viewport-relative font-size. Keep
        # the inherited value rather than store a length no child could
        # resolve `em` against.
        metrics["font_size_unresolvable"] += 1
    own_font_px = style.font_size_px

    # 2. `color`, because `currentcolor` on any other property names it.
    #    `color: currentcolor` is the inherited colour, which is what
    #    `style.color` already holds.
    if "color" in declared:
        style.color = _computed_value(
            declared["color"],
            font_px=own_font_px,
            root_px=root_font_px,
            own_color=style.color,
        )

    # 3. Everything else, against the element's OWN font-size and colour.
    applied = _compute_rest(
        style,
        {k: v for k, v in declared.items() if k != "color"},
        own_font_px=own_font_px,
        root_font_px=root_font_px,
        own_color=style.color,
    )
    metrics["declarations_applied"] += applied + int("color" in declared)
    return style


def _inherit_from(parent: ComputedStyle) -> ComputedStyle:
    """A fresh style: initial everywhere, inherited where INHERITED says."""
    style = ComputedStyle()
    for prop in INHERITED:
        style.set(prop, parent.get(prop))
    return style


def style_document(document: Node, author_css: list[str]) -> Counter[str]:
    """Attach a `ComputedStyle` to every node of `document`.

    `author_css` is a list of stylesheet sources -- what a driver got from
    somewhere other than the document itself. In-document `<style>` elements
    are found and cascaded automatically; `<link rel=stylesheet>` is counted
    and not fetched.

    Returns this stage's metrics, ready for `metrics.emit("cssparse", ...)`.
    Writing them is the driver's job, not this function's.
    """
    started = time.perf_counter()
    metrics: Counter[str] = Counter()

    # Must precede any matching: `element_index` is None until this runs, and
    # a matcher that read it anyway would treat every element as a first
    # child. `matching.py` falls back to computing the index, so the failure
    # would be slow rather than wrong -- which is worse, because it is
    # invisible.
    metrics["elements"] = annotate_positions(document)

    nodes = list(_iter_nodes(document))
    elements = [node for node in nodes if isinstance(node, Element)]
    # Seeded so the key is present at zero rather than absent: a driver
    # writing one CSV row per key would otherwise emit no row at all for a
    # page with no external stylesheets, and "no row" and "zero" are
    # different findings for the analysis half.
    metrics["link_stylesheets_skipped"] = 0
    _count_link_stylesheets(elements, metrics)

    order = _Counter()
    rules = _parse_sheet(UA_CSS, "ua", order, metrics)
    metrics["ua_rules"] = len(rules)

    for source in author_css:
        metrics["author_stylesheets"] += 1
        rules.extend(_parse_sheet(source, "author", order, metrics))

    for element in elements:
        if element.tag_name != "style":
            continue
        source = _style_element_source(element)
        if source is None:
            metrics["style_elements_skipped"] += 1
            continue
        metrics["style_elements"] += 1
        rules.extend(_parse_sheet(source, "author", order, metrics))

    metrics["rules_total"] = len(rules)
    index = RuleIndex(rules, selector_of=_selector_of)

    root_font_px = INITIAL_FONT_SIZE_PX
    initial = ComputedStyle()

    for node in nodes:
        parent = node.parent
        parent_style = parent.computed_style if parent is not None else None
        if not isinstance(parent_style, ComputedStyle):
            parent_style = initial

        if isinstance(node, Element):
            inline_source = node.attrs.get("style")
            if inline_source:
                metrics["inline_style_attributes"] += 1
                inline = _parse_inline_style(inline_source, order, metrics)
            else:
                inline = []
            declared = _winning_declarations(node, index, inline, metrics)
            node.computed_style = _compute_style(
                parent_style, declared, root_font_px, metrics
            )
            if not isinstance(parent, Element):
                # The root element. Its own `rem` resolved against the
                # initial 16px (CSS Values 4: `rem` on the root element
                # refers to the property's initial value); every descendant
                # resolves `rem` against what it just computed.
                root_font_px = node.computed_style.font_size_px
        else:
            # Text, Comment, DocumentType, Document. No declarations can
            # target them -- `matches()` returns False for a non-Element --
            # so their style is pure inheritance. Text nodes need it: layout
            # asks a text run for its colour and font-size directly rather
            # than carrying a special case up to its parent element.
            node.computed_style = _inherit_from(parent_style)
        metrics["nodes_styled"] += 1

    metrics["cascade_time_ms"] = round((time.perf_counter() - started) * 1000, 3)
    return metrics


__all__ = [
    "INHERITED",
    "INITIAL_FONT_SIZE_PX",
    "LONGHANDS",
    "ComputedStyle",
    "style_document",
]
