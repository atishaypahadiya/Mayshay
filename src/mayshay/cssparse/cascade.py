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

A shorthand sets **every** longhand it governs, not only the ones it
mentions: the omitted ones are reset to their initial values before the
declaration enters the cascade. `values.py` deliberately leaves them out of
its parse result (its deviation 7) and hands the obligation here, because
filling them in needs the initial-value table. Without the reset,

    p { border: 5px solid red }
    p { border: solid blue }

leaves `border-top-width` at 5px -- the second declaration has no width key
for the first one to lose to -- where a browser resets it to `medium`. See
`_reset_omitted_longhands`.


Deliberate deviations and omissions
-----------------------------------

1. **`inherit`, `initial` and `unset` are supported; `revert` is not.**
   `values.py` intercepts the three before any per-property parser sees
   them and hands back a `WideKeyword`; `_resolve_wide_keywords` decides
   what each names, which is the earliest point either the parent's
   computed value or `INITIAL_SPECIFIED` exists. A shorthand's wide keyword
   sets every longhand it governs.

   `revert` needs origin-level rollback this cascade does not model -- it
   would have to re-run the cascade with the declaration's own origin and
   everything above it removed, and the cascade keeps no per-origin
   history. Faking it as `unset` is wrong in the common case (an author
   `revert` should fall back to the UA rule, not to the initial value), so
   it stays dropped, classified `unsupported-value`, and counted in
   `wide_keyword_revert`.
2. **`@media` is evaluated when a `viewport` is passed; every other at-rule
   is counted and skipped** -- `at_rules_skipped`, and `at_rule_<name>` per
   name. Rules inside a non-matching `@media` are absent from the cascade
   rather than applied unconditionally, which is the right direction to
   fail: applying `@media print` would repaint the screen.

   Passing no viewport keeps Phase 2's behaviour exactly -- every at-rule
   skipped -- so figures measured before `cssparse/media.py` existed stay
   reproducible instead of being silently restated. What evaluating `@media`
   recovered, measured on the corpus at 1280x1024: Wikipedia's `flex`
   element count went from 4 to 204, and `grid` from 0 to 2. Before it, 51%
   of the Hacker News page's CSS and 46% of Wikipedia's never reached the
   cascade at all.

   `@supports` is still skipped, and so is any `@media` whose query names a
   feature outside `media.py`'s scope; both are counted rather than dropped
   silently. See that module for the full list.
3. **`<link rel=stylesheet>` is counted, never fetched** -- `net/` is Phase
   5. The count turns "no styles applied" from a blank render into a
   number, and the fraction of real pages depending entirely on external
   CSS is itself a finding. Supply the sheets via `external_css` and the
   counter reports only what is still missing.
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
8. **`border-*-width` has two different "initial" values, and both are
   needed.** The *specified* initial value is `medium`, which
   `INITIAL_SPECIFIED` records as `Length(3, "px")`; the *computed* value is
   `0` whenever the corresponding `border-*-style` is `none` or `hidden`
   (CSS 2.1 section 8.5.1), which `_zero_widths_of_borderless_sides`
   enforces. Collapsing them into one constant gets one of the two cases
   wrong whichever constant is chosen: with a single `0`, `border: solid
   red` paints nothing, where a browser paints 3px, because that
   declaration *does* specify a style and leaves only the width to its
   initial value; with a single `3px`, every element on the page acquires
   a three-pixel border. `values.py` still does not parse the
   `thin|medium|thick` trio (its deviation 8), so the keyword itself never
   arrives from a stylesheet -- but the value it names is load-bearing all
   the same.
9. **Quirks mode is not consulted.** `Document.mode` is classified by Task C
   and acted on in layout: unitless lengths and the alternate box model are
   used-value concerns.
10. **The `author_css` argument is cascaded before the document's own
    `<style>` elements.** The two cannot be interleaved without knowing
    where the caller's sheets sat in the source, and the argument's real
    role is standing in for the external sheets a `<link>` in `<head>`
    would have pulled in -- which do precede in-document `<style>` on the
    overwhelming majority of pages. Within each group, source order holds.
11. **`declarations_applied` counts *longhands written onto a
    `ComputedStyle`*, not declarations parsed.** A shorthand contributes one
    per longhand it sets (four for `margin`, twelve for `border`), and the
    same longhand re-declared on the same element contributes once, because
    the cascade has already picked a winner by then. `font-size` counts one
    when it resolved and zero when it did not -- an unresolvable one is
    `font_size_unresolvable` instead. That last clause is a fix, not a
    description of how it always was: `font-size` contributed nothing at all
    until the counter was corrected, so any `declarations_applied` figure in
    a CSV written before this commit is low by the number of `font-size`
    declarations that page applied.
12. **Every dropped declaration is classified into exactly one of four
    reasons**, emitted as `declarations_dropped_<reason>` alongside the
    total: `unsupported_property` (the name is not in `values.py`'s table),
    `unsupported_value` (the name is known, the value grammar is not),
    `var_unresolved` (a `var()` reference this module did not substitute)
    and `invalid` (genuinely malformed; a browser drops it too). They sum
    to `declarations_dropped`, which keeps its Phase 2 meaning.

    The reason a rate alone is not enough: it falls when the parser
    improves and it also falls when validation loosens, and those are
    opposite outcomes. `invalid` is the tripwire -- everything in it is
    something a browser drops too, so a shrinking `invalid` means this
    engine started accepting garbage. `values.classify_drop` decides;
    `_cascade_declarations` is the single place that calls it, for both
    `<style>` bodies and `style=` attributes.
13. **`var()` resolves per element, at computed-value time, and every
    refusal is a counter.** Custom properties cascade and inherit like any
    other declaration but keep their value as raw tokens; a declaration
    containing a `var()` on a supported property is *deferred* rather than
    dropped (`declarations_pending_var`) and resolved once per element
    against that element's custom-property map.

    Substituting at sheet-parse time would be wrong and would look right:
    declarations are parsed once per sheet and shared by every element the
    rule matches, so one `color: var(--accent)` would give every matching
    element the same colour -- entirely plausible output, and correct on any
    test page with one element. `_PendingValue` is what keeps the decision
    where it belongs.

    Out of scope, each a number: `var_nested_fallback_skipped` (a `var()`
    inside another's fallback, on the branch actually taken),
    `var_depth_exceeded` (an eight-deep substitution cap standing in for
    real cycle detection -- O(1), and wrong only in the safe direction),
    `var_unknown_no_fallback`, `var_malformed`, and
    `var_substituted_value_invalid` for a substitution that succeeded and
    produced a value the property does not accept.
    `var_declarations_attempted` / `_resolved` / `_refused` bridge back to
    the parse-time `declarations_pending_var`, and `_unmatched` accounts
    for the rest. The split is not cosmetic: measured as one number,
    Wikipedia's 353 deferred declarations reported 288 unresolved, of which
    281 had simply never been asked for by any element -- their rules match
    nothing on that page, which is ordinary for a large sheet. Seven were
    attempted and refused.
14. **Every declaration and error counter is a whole-document total** --
    `<style>` bodies, `style=` attributes and the UA sheet summed
    together. `tokenizer_parse_errors`
    and `css_parse_errors` include the inline path -- which they did not
    until this commit; malformed CSS in a `style=` attribute read as zero
    errors, and wikipedia.html carries 237 non-empty `style=` attributes (of
    340 present; the other 103 are empty). There is no
    per-origin breakdown; if the analysis half needs one, it is a new key,
    not a reinterpretation of these.
"""

from __future__ import annotations

import time
from collections import Counter
from dataclasses import dataclass, field, fields

from mayshay.cssparse.matching import RuleIndex, matches
from mayshay.cssparse.parser import AtRule, CssParser, QualifiedRule
from mayshay.cssparse.media import (
    Viewport,
    matches as media_matches,
    parse_media_query_list,
)
from mayshay.cssparse.selectors import (
    Complex,
    SelectorParseError,
    parse_selector_list,
    specificity,
)
from mayshay.cssparse.tokenizer import CssTokenizer, EOFToken
from mayshay.cssparse.ua import UA_CSS
from mayshay.cssparse.values import (
    AUTO,
    DROP_REASONS,
    LONGHANDS_OF,
    Color,
    Keyword,
    Length,
    Percent,
    SUPPORTED_PROPERTIES,
    WideKeyword,
    bare_wide_keyword,
    classify_drop,
    contains_var_reference,
    is_custom_property,
    substitute_var,
    normalize_property_name,
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
    # Phase 3 Task A2, deliverable 3. Task D cannot be written against a
    # `ComputedStyle` with no `white-space` or `line-height`, and
    # `box-sizing` changes what every width in Task C means -- cheaper to
    # add now than to retrofit. `font-family` and `vertical-align` have no
    # consumer this phase and are recorded anyway: a value nobody reads is
    # a smaller problem than a value nobody recorded.
    "white-space",
    "line-height",
    "font-family",
    "font-weight",
    "font-style",
    "text-align",
    "vertical-align",
    "box-sizing",
    "list-style-type",
    # Phase 3 Task C. Read by block layout to decide what is in flow and
    # where a margin may not collapse; none of the four is implemented as
    # behaviour, and layout counts every place it declines to act. Task A2
    # added the properties Task D needed and stopped there -- these four are
    # the ones Task C needs, and section 8.3.1's barriers are unstatable
    # without them.
    "overflow",
    "float",
    "clear",
    "position",
    # Phase 3 Task E. `table-layout`, `border-spacing` and `caption-side`
    # are read and acted on by `layout.table`; `border-collapse` is read
    # only so that the separated-model divergence is a counter rather than
    # an absence. Task C added the four properties block layout could not
    # be correct without and stopped there; these are the four table layout
    # cannot be correct without.
    "table-layout",
    "border-collapse",
    "border-spacing",
    "caption-side",
)

# The inherited properties, per the CSS property definitions. `display`, the
# box-model properties and `background-color` do not inherit -- a `<p>`
# inside a bordered `<div>` does not get its own border, and that is not an
# oversight in the table, it is what the specs say. Neither do
# `vertical-align` or `box-sizing`, which is why deliverable 3 added nine
# fields and this set gained only seven of them.
#
# This went from two entries to nine in one deliberate change, with a test
# per property, rather than one at a time as each was needed. A property
# that silently fails to inherit produces plausible-looking wrong output --
# the whole page renders, every box is where a box could be, and only the
# text is the wrong size or the wrong weight. That is the hardest kind of
# defect to notice and the reason for the batch.
INHERITED: frozenset[str] = frozenset({
    "color",
    "font-size",
    "font-family",
    "font-weight",
    "font-style",
    "line-height",
    "white-space",
    "text-align",
    "list-style-type",
    # Task E. Three of the four table properties inherit and one does not,
    # and the split is not arbitrary: `border-collapse`, `border-spacing`
    # and `caption-side` are set on the `<table>` and consulted on its
    # *descendants* (a cell asks for the spacing around it, a caption asks
    # which side it is on), so CSS 2.1 makes them inherited. `table-layout`
    # is consulted only on the table box itself and does not.
    "border-collapse",
    "border-spacing",
    "caption-side",
})

# `medium`. The one number in this module that is a convention rather than a
# derivation; every `em`, `rem` and `%` font-size on a page with no explicit
# root font-size is ultimately a multiple of it.
INITIAL_FONT_SIZE_PX = 16.0

_ZERO_LENGTH = Length(0, "px")
_INITIAL_COLOR = Color(0, 0, 0, 1.0)
_TRANSPARENT = Color(0, 0, 0, 0.0)

# `border-width`'s initial value is the keyword `medium`, which every engine
# renders as 3px. `values.py` does not parse the `thin|medium|thick` trio
# (its deviation 8), so the keyword never arrives from a stylesheet -- but
# the *initial* value still has to be right, because `border: solid red`
# specifies a style and a colour and leaves the width to it. See
# `_zero_widths_of_borderless_sides` for the other half of the rule.
_MEDIUM_BORDER_WIDTH = Length(3, "px")

# `font-family`'s initial value is UA-defined. Empty means "unspecified",
# not "no fonts": Phase 3 renders with one vendored font whatever this says,
# and recording a concrete family would put a guess where a declaration
# would later be read.
_INITIAL_FONT_FAMILY: tuple[str, ...] = ()

_SIDES = ("top", "right", "bottom", "left")
_BORDER_STYLE_PROPS = tuple(f"border-{side}-style" for side in _SIDES)
_BORDER_COLOR_PROPS = tuple(f"border-{side}-color" for side in _SIDES)
_BORDER_WIDTH_PROPS = tuple(f"border-{side}-width" for side in _SIDES)

# A border whose style is `none` or `hidden` has a computed width of zero
# whatever the width says -- CSS 2.1 section 8.5.1's "Computed value:
# absolute length; `0` if the border style is `none` or `hidden`".
_BORDERLESS_STYLES = frozenset({"none", "hidden"})

# The *specified* initial value of every longhand: what a property falls
# back to when a shorthand does not mention it. Deliberately not read off
# `ComputedStyle`'s field defaults, because two of them differ: a computed
# `border-*-color` is a resolved `Color`, while its initial value is the
# keyword `currentcolor`, and a computed `border-*-width` is zeroed when the
# style is `none` while its initial value is `medium`. Running these through
# `_computed_value` is what turns the specified form into the computed one.
INITIAL_SPECIFIED: dict[str, object] = {
    "display": Keyword("inline"),
    "width": AUTO,
    "height": AUTO,
    "color": _INITIAL_COLOR,
    "background-color": _TRANSPARENT,
    "font-size": Length(INITIAL_FONT_SIZE_PX, "px"),
    **{f"margin-{side}": _ZERO_LENGTH for side in _SIDES},
    **{f"padding-{side}": _ZERO_LENGTH for side in _SIDES},
    **{prop: _MEDIUM_BORDER_WIDTH for prop in _BORDER_WIDTH_PROPS},
    **{prop: Keyword("none") for prop in _BORDER_STYLE_PROPS},
    **{prop: Keyword("currentcolor") for prop in _BORDER_COLOR_PROPS},
    "white-space": Keyword("normal"),
    # Symbolic, deliberately: see `values._parse_line_height`. The used value
    # of `normal` is the font's own preferred spacing, which arrives with
    # Task D's metrics.
    "line-height": Keyword("normal"),
    # The spec's initial value is "depends on user agent". The empty tuple
    # says *no family was specified* rather than naming one, which is the
    # honest encoding while this engine ships exactly one font: a concrete
    # default here would be a guess that later reads as a declaration.
    "font-family": _INITIAL_FONT_FAMILY,
    "font-weight": 400,
    "font-style": Keyword("normal"),
    "text-align": Keyword("start"),
    "vertical-align": Keyword("baseline"),
    "box-sizing": Keyword("content-box"),
    "list-style-type": Keyword("disc"),
    "overflow": Keyword("visible"),
    "float": Keyword("none"),
    "clear": Keyword("none"),
    "position": Keyword("static"),
    "table-layout": Keyword("auto"),
    "border-collapse": Keyword("separate"),
    # CSS 2.1's initial value is `0`, on both axes. HTML's own UA stylesheet
    # then sets `border-spacing: 2px` on `<table>`, which is why a browser's
    # default table has 2px gaps and this engine's does not -- see
    # `cssparse/ua.py`, which does not carry that rule.
    "border-spacing": (_ZERO_LENGTH, _ZERO_LENGTH),
    "caption-side": Keyword("top"),
}

# Which longhands each property governs -- *all* of them, not just the ones
# a given declaration happened to mention -- comes from `values.LONGHANDS_OF`,
# which is derived from the same table the value parser dispatches on. It used
# to be a second hand-written table here (`_SHORTHAND_LONGHANDS`), listing only
# `margin`, `padding` and `border`; a shorthand added to `values.py` and
# forgotten here silently skipped its reset. See `_reset_omitted_longhands`.


def _reset_omitted_longhands(name: str, longhands: dict[str, object]) -> dict[str, object]:
    """A shorthand sets *every* longhand it governs, including the ones it
    does not mention -- those go to their initial values.

    This is the obligation `values.py`'s deviation 7 hands to this module,
    and it is the difference between CSS and a merge. Without it:

        p { border: 5px solid red }
        p { border: solid blue }

    leaves `border-top-width` at 5px, because the second declaration's
    parsed result simply has no width key for the first one to lose to. A
    browser resets it to `medium`. The leak is invisible on any page that
    writes its shorthands in full, and silently wrong on any page that does
    not -- which is most of them.

    `margin` and `padding` can never leave a side unset (the one-to-four
    value rule always produces all four), so in practice only `border` is
    affected; they are in the table so a future shorthand cannot be added
    without a decision, and so the invariant is stated rather than assumed.

    **`name` is normalised here, not by the caller.** CSS property names are
    ASCII-case-insensitive, and `parse_declaration_value` lowercases its own
    copy, so `p { BORDER: solid blue }` used to parse into correct longhands
    and then miss this table entirely -- the reset silently no-opped and the
    earlier `border: 5px solid red` kept its 5px width. Executed before the
    fix: `border`/`BORDER` gave 3px/5px for `border-top-width`; after, both
    give 3px. Normalising inside the function rather than at the two call
    sites is deliberate: a third call site cannot reintroduce the bug.
    """
    governed = LONGHANDS_OF.get(normalize_property_name(name))
    if governed is None:
        return longhands
    for prop in governed:
        longhands.setdefault(prop, INITIAL_SPECIFIED[prop])
    return longhands


# `float` is a builtin and a `ComputedStyle` annotation would shadow it
# inside the class body, so its field is `float_`. The override is explicit
# rather than a rule ("append an underscore to reserved names") because one
# exception is cheaper to read than a rule with one member, and the drift
# assert below fails loudly if a property ever loses its field.
_FIELD_NAME_OVERRIDES: dict[str, str] = {"float": "float_"}


def _field_name(prop: str) -> str:
    override = _FIELD_NAME_OVERRIDES.get(prop)
    return override if override is not None else prop.replace("-", "_")


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

    # Zero, not the `medium` initial value: the initial `border-style` is
    # `none`, and a border with no style has a computed width of zero. The
    # *specified* initial value lives in `INITIAL_SPECIFIED`, and
    # `_zero_widths_of_borderless_sides` keeps the two consistent for every
    # element that does declare a border.
    #
    # These four defaults are in fact unobservable, and deliberately kept
    # anyway: the only parsed source of a non-`none` `border-*-style` is the
    # `border` shorthand, which always resets the width alongside it, so
    # `_zero_widths_of_borderless_sides` overwrites whatever is here on
    # every element that could tell the difference. Changing them to `3px`
    # therefore fails no test -- which is a fact about the invariant, not a
    # gap in the suite. They stay at zero because that is the value the
    # invariant would produce, and a default that contradicted it would be
    # a trap for the next person to weaken the zeroing step.
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

    white_space: str = "normal"
    # A `Keyword`, a `float`, a `Length` or a `Percent` -- see deviation 14
    # for why `normal` is not collapsed to a number here.
    line_height: object = Keyword("normal")
    font_family: tuple[str, ...] = _INITIAL_FONT_FAMILY
    font_weight: object = 400
    font_style: str = "normal"
    text_align: str = "start"
    vertical_align: object = "baseline"
    box_sizing: str = "content-box"
    list_style_type: str = "disc"

    # Phase 3 Task C. None of the four is *implemented* -- no float is
    # placed, no positioned box is offset, nothing is clipped -- and each is
    # counted where layout declines to act. They are cascaded because CSS
    # 2.1 section 8.3.1 states its margin-collapsing barriers in terms of
    # them: without `overflow` an engine collapses a margin across a new
    # block formatting context, and the page comes out quietly too tight
    # rather than visibly broken.
    overflow: str = "visible"
    float_: str = "none"
    clear: str = "none"
    position: str = "static"

    # Phase 3 Task E. `table_layout` and `caption_side` steer
    # `layout.table`; `border_spacing` is a two-tuple `(horizontal,
    # vertical)` of computed `Length`s, never a single value, so no consumer
    # has to ask which shape it got. `border_collapse` is read only to be
    # counted -- this engine implements the separated model alone.
    table_layout: str = "auto"
    border_collapse: str = "separate"
    border_spacing: object = (_ZERO_LENGTH, _ZERO_LENGTH)
    caption_side: str = "top"

    # This element's custom properties, name -> raw token tuple. Not a
    # longhand and deliberately exempted from the drift assert below: it is
    # a *map* of properties rather than one, its keys are open-ended, and it
    # is never parsed until substituted. It inherits, which is what makes
    # `var()` resolve per element rather than per rule; the dict is shared
    # with the parent whenever the child declares none of its own, so an
    # inheriting subtree costs one reference per node and not one dict.
    custom_properties: dict = field(default_factory=dict)

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
_STYLE_FIELDS = {f.name for f in fields(ComputedStyle)} - {"custom_properties"}
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
# Public: layout has to recognise the units the cascade could not
# resolve, and a second copy of the set in `layout/block.py` is exactly the
# kind of quiet duplication that drifts.
VIEWPORT_UNITS = frozenset({"vw", "vh", "vmin", "vmax"})


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
    if unit in VIEWPORT_UNITS:
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
                prop,
                value,
                font_px=own_font_px,
                root_px=root_font_px,
                own_color=own_color,
            ),
        )
        applied += 1
    return applied


# The properties whose *computed* value is the keyword itself, and which
# therefore store a plain `str`. An allow-list rather than "unwrap any
# Keyword": a keyword on any other property means either a value type that
# needs resolving (`currentcolor`, handled above it) or a property added to
# `values.py` without a computed-value decision being made here, and
# stringifying that silently is how a property ends up half-implemented.
_KEYWORD_VALUED = frozenset({
    "display",
    "white-space",
    "font-style",
    "text-align",
    "vertical-align",
    "box-sizing",
    "list-style-type",
    "overflow",
    "float",
    "clear",
    "position",
    "table-layout",
    "border-collapse",
    "caption-side",
}) | frozenset(_BORDER_STYLE_PROPS)

# Properties whose computed value is a **pair** of lengths, each computed
# the way a lone length would be. Exactly one, and it is spelled out rather
# than handled by "map over any tuple": `font-family`'s computed value is
# also a tuple and must be left alone, so a structural rule would resolve
# font names as if they were lengths. See `_computed_value`.
_LENGTH_PAIR_VALUED = frozenset({"border-spacing"})

# Properties whose computed value keeps the `Keyword` wrapper rather than
# being unwrapped to a `str`. Exactly one, and it is not an oversight:
# `line-height` is a union of `normal`, a number, a length and a
# percentage, so its consumer must type-check the value anyway, and a bare
# `"normal"` string would be indistinguishable from a font-family entry if
# the two were ever confused. Keeping `Keyword("normal")` also makes the
# "still symbolic" decision visible in a `repr` rather than inferable.
_KEYWORD_PRESERVED = frozenset({"line-height"})


# The percentages that resolve here rather than staying symbolic. The full
# three-category rule is `docs/percentage-resolution.md`; the short form:
#
#   * `width: 50%` resolves against the CONTAINING BLOCK, which does not
#     exist until layout. It stays `Percent(50)`.
#   * `line-height: 150%` resolves against the element's OWN font-size
#     (CSS 2.1 10.8.1), which is known right here -- and it is the resulting
#     *length* that inherits, not the percentage.
#
# Same token type, opposite handling, and the reason is which quantity the
# percentage refers to. Leaving it symbolic is not a conservative choice: a
# child with a smaller font-size would resolve the inherited `Percent(150)`
# against its own size and get a correctly-proportioned, subtly wrong number
# that nothing downstream could distinguish from the right one.
#
# A `<number>` line-height is the opposite case and is correctly left alone:
# CSS 2.1 10.8.1 says its computed value *is* the number, and the number is
# what inherits -- the multiplication happens per element at used-value time,
# which is Task D's.
#
# `vertical-align: <percentage>` is a third case and is NOT in this set: it
# resolves against the element's own *used* line-height, which is known when
# `line-height` is a number or a px length and unknown when it is `normal`.
# It is handled after `_compute_rest`, by
# `_resolve_vertical_align_percentage`, because it needs a value this
# function does not have.
_PERCENT_OF_OWN_FONT_SIZE = frozenset({"line-height"})


def _computed_value(
    prop: str, value: object, *, font_px: float, root_px: float, own_color: object
) -> object:
    """One specified value -> its computed value.

    `AUTO` falls through untouched, and so does `Percent` on every property
    but the one in `_PERCENT_OF_OWN_FONT_SIZE` -- which is the point, and
    the exception is the point too.
    """
    if isinstance(value, Keyword):
        if value.name == "currentcolor":
            return own_color
        if prop in _KEYWORD_VALUED:
            # See deviation 6: the computed value *is* the keyword.
            return value.name
        if prop in _KEYWORD_PRESERVED:
            return value
        raise ValueError(
            f"no computed-value rule for keyword {value.name!r} on {prop!r}; "
            f"add it to _KEYWORD_VALUED or resolve it explicitly"
        )
    if prop in _LENGTH_PAIR_VALUED and isinstance(value, tuple):
        # Each half computes exactly as a lone `<length>` does -- `em`
        # against this element's own font-size, `rem` against the root's --
        # so the resolution is delegated rather than restated. A restatement
        # is where a unit gets handled on one axis and not the other.
        return tuple(
            _computed_value(
                "border-spacing-component", item,
                font_px=font_px, root_px=root_px, own_color=own_color,
            )
            for item in value
        )
    if isinstance(value, Length):
        px = _length_to_px(value, font_px=font_px, root_px=root_px)
        return value if px is None else Length(px, "px")
    if isinstance(value, Percent) and prop in _PERCENT_OF_OWN_FONT_SIZE:
        return Length(round(value.value / 100.0 * font_px, 6), "px")
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
class _PendingValue:
    """A declaration whose value contains `var()`, kept unparsed.

    **The architectural point of Task A2's largest item.** Declarations are
    parsed once per sheet and the resulting objects are shared by every
    element the rule matches; `color: var(--accent)` computes to a different
    value per element, because `--accent` is itself cascaded and inherited.
    So the value cannot be parsed at sheet time at all, and this object is
    what a `_Declaration` carries instead: the property name and the raw
    tokens, resolved per element in `_compute_style`.

    One `_PendingValue` is shared by every longhand its property governs
    (`border: 1px solid var(--x)` produces twelve `_Declaration`s and one of
    these), so the cascade can pick a winner per longhand as usual while the
    substitution still runs once per element rather than twelve times.

    `attempted` and `resolved` are what turn "353 declarations were
    deferred" into three numbers instead of one. The single number was
    measured first and was wrong in the usual way -- 288 of 353 "never
    resolved" alongside a `var_unknown_no_fallback` of zero, which is
    internally inconsistent and reads as a catastrophic failure rate. A
    second derivation (instrumenting `_resolve_pending` from outside)
    found 281 of the 288 had never been *attempted*: their rules match no
    element on that page, which is an ordinary property of a real
    stylesheet and not a var() failure at all. Only 7 were attempted and
    refused.

    Hence two flags, not one: `var_declarations_refused` is the number that
    means something went wrong, and `var_declarations_unmatched` is the
    number that does not.
    """

    prop_name: str
    tokens: tuple
    attempted: bool = False
    resolved: bool = False


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
    source: str,
    origin: str,
    order: object,
    metrics: Counter[str],
    viewport: object | None = None,
) -> list[_StyleRule]:
    """Parse one stylesheet into `_StyleRule`s.

    `order` is a shared counter (an `itertools.count`-alike; anything with
    `__next__`) so declaration numbers keep increasing across every sheet in
    the document, which is what makes later sheets win ties against earlier
    ones.

    `viewport` is optional. Without one, at-rules are counted and skipped
    (Phase 2 deviation 2). With one, `@media` preludes are evaluated against
    it and matching blocks contribute their rules.
    """
    parser = CssParser(source)
    rules: list[_StyleRule] = []
    _collect_rules(parser, parser.parse_stylesheet(), origin, order, metrics,
                   rules, viewport, depth=0)
    metrics["tokenizer_parse_errors"] += parser.tokenizer.metrics["parse_errors"]
    metrics["css_parse_errors"] += len(parser.errors)
    return rules


def _ascii_lower(text: str) -> str:
    """ASCII-only case fold, for at-rule names.

    A third copy, for the reason `tokenizer.py` and `values.py` each state
    for theirs: importing another module's private name is the worse
    coupling. `str.lower()` is wrong here too -- it folds U+212A KELVIN SIGN
    to `k`, so `@\u212aeyframes` would be taken for `@keyframes` and its
    block descended into.
    """
    return "".join(chr(ord(ch) + 0x20) if "A" <= ch <= "Z" else ch for ch in text)


# How deep to descend through nested at-rules. `@media` inside `@media` is
# common; five levels is far past anything real, and the cap is here so a
# pathological sheet cannot turn parsing into a recursion.
_MAX_AT_RULE_DEPTH = 5


def _collect_rules(
    parser: CssParser,
    rule_list: list,
    origin: str,
    order: object,
    metrics: Counter[str],
    out: list[_StyleRule],
    viewport: object | None,
    depth: int,
) -> None:
    """Flatten a rule list into `out`, descending into matching `@media`.

    With no viewport this is Phase 2's behaviour exactly: every at-rule is
    counted and skipped, and nothing inside one reaches the cascade. With a
    viewport, `@media` preludes are evaluated and the rules inside a
    matching block are spliced in at the point the block appeared -- which
    is what preserves source order between a `@media` block and the rules
    around it.
    """
    for rule in rule_list:
        if isinstance(rule, AtRule):
            name = _ascii_lower(rule.name)
            metrics[f"at_rule_{name}"] += 1
            if viewport is None or name != "media" or rule.block is None:
                # Deviation 2: counted, not evaluated, and its block's rules
                # are therefore not in the cascade at all.
                metrics["at_rules_skipped"] += 1
                continue
            if depth >= _MAX_AT_RULE_DEPTH:
                metrics["at_rules_too_deep"] += 1
                metrics["at_rules_skipped"] += 1
                continue
            queries = parse_media_query_list(rule.prelude)
            if not media_matches(queries, viewport, metrics):
                metrics["media_blocks_not_matched"] += 1
                continue
            metrics["media_blocks_matched"] += 1
            _collect_rules(
                parser, parser.parse_rules(rule.block), origin, order,
                metrics, out, viewport, depth + 1,
            )
            continue
        _append_qualified_rule(rule, parser, origin, order, metrics, out)


def _append_qualified_rule(
    rule: object,
    parser: CssParser,
    origin: str,
    order: object,
    metrics: Counter[str],
    out: list[_StyleRule],
) -> None:
    """Turn one QualifiedRule into zero or more `_StyleRule`s on `out`."""
    assert isinstance(rule, QualifiedRule)
    if rule.block is None:
        return
    try:
        selector_list = parse_selector_list(rule.prelude)
    except SelectorParseError:
        # An unparseable prelude invalidates the whole rule, block
        # included -- CSS Syntax 3 section 5.4.1. Not the declarations
        # one at a time; the rule.
        metrics["selectors_invalid"] += 1
        return
    declarations = _parse_block(parser, rule.block, origin, order, metrics)
    if not declarations:
        return
    for selector in selector_list.selectors:
        out.append(
            _StyleRule(
                selector=selector,
                specificity=specificity(selector),
                declarations=declarations,
            )
        )


def _cascade_declarations(
    declarations: list,
    *,
    normal_rank: int,
    important_rank: int,
    order: object,
    metrics: Counter[str],
) -> list[_Declaration]:
    """Turn parsed declarations into `_Declaration`s, counting what is kept
    and *why* anything dropped was dropped.

    **The one place a declaration enters or fails to enter the cascade.**
    This body used to exist twice -- once in `_parse_block` for `<style>`
    bodies and again in `_parse_inline_style` for `style=` attributes -- and
    the two drifted: a Phase 2 fix landed in one and silently not the other,
    so identical malformed CSS was counted differently depending on where it
    was written. The only difference between the two call sites is which
    cascade ranks the declarations get, so that is the only thing they still
    pass in.

    `declarations_dropped` keeps its Phase 2 meaning -- the total -- and the
    four `declarations_dropped_<reason>` counters partition it exactly. That
    exactness is the point: a total alone cannot say whether the parser
    improved or validation loosened. See `values.classify_drop`.
    """
    out: list[_Declaration] = []
    for decl in declarations:
        metrics["declarations_seen"] += 1
        rank = important_rank if decl.important else normal_rank

        if is_custom_property(decl.name):
            # A custom property is an ordinary declaration that cascades and
            # inherits like any other -- but its value is almost-anything and
            # is not parsed until it is substituted, so it is kept as raw
            # tokens. The name is NOT normalised: custom property names are
            # case-sensitive.
            metrics["custom_properties_declared"] += 1
            metrics["declarations_kept"] += 1
            out.append(_Declaration(
                decl.name,
                tuple(tok for tok in decl.value if not isinstance(tok, EOFToken)),
                rank,
                next(order),
            ))
            continue

        longhands = parse_declaration_value(decl.name, decl.value)
        if longhands is None and contains_var_reference(decl.value):
            name = normalize_property_name(decl.name)
            if name in SUPPORTED_PROPERTIES:
                # Deferred, not dropped: the value has no grammar to check
                # until it is substituted, and substitution is per element.
                # The longhands it *will* set are known from the property
                # name alone, which is what lets the cascade pick a winner
                # per longhand without knowing the value yet.
                pending = _PendingValue(name, tuple(
                    tok for tok in decl.value if not isinstance(tok, EOFToken)
                ))
                metrics["declarations_pending_var"] += 1
                metrics["declarations_kept"] += 1
                index = next(order)
                for prop in LONGHANDS_OF[name]:
                    out.append(_Declaration(prop, pending, rank, index))
                continue

        if longhands is None:
            # Either a property outside our table, or a value whose grammar
            # is wrong. Both drop the declaration and keep its siblings,
            # which is what a browser does.
            metrics["declarations_dropped"] += 1
            reason = classify_drop(decl.name, decl.value)
            metrics[f"declarations_dropped_{reason.replace('-', '_')}"] += 1
            if bare_wide_keyword(decl.value) == "revert":
                # Named rather than merely counted: `revert` is the one
                # wide keyword this cascade refuses, and it refuses it for a
                # reason (origin-level rollback it does not model) rather
                # than for want of a branch. A number is how that stays a
                # decision instead of becoming an absence.
                metrics["wide_keyword_revert"] += 1
            continue
        longhands = _reset_omitted_longhands(decl.name, longhands)
        index = next(order)
        for prop, value in longhands.items():
            out.append(_Declaration(prop, value, rank, index))
        metrics["declarations_kept"] += 1
    return out


def _parse_block(
    parser: CssParser,
    block: list,
    origin: str,
    order: object,
    metrics: Counter[str],
) -> list[_Declaration]:
    return _cascade_declarations(
        parser.parse_declarations(block),
        normal_rank=_NORMAL_RANK[origin],
        important_rank=_IMPORTANT_RANK[origin],
        order=order,
        metrics=metrics,
    )


def _parse_inline_style(
    source: str, order: object, metrics: Counter[str]
) -> list[_Declaration]:
    """The `style=` attribute: a declaration list, no selector, own rank.

    The tokenizer is constructed on `source` and the parser on `""` -- the
    parser is only ever handed the token list, never asked to tokenize --
    so the two error counters come from *different objects* here, unlike
    `_parse_sheet` where `parser.tokenizer` is the one that ran. Reading
    them off `parser.tokenizer` (which tokenized the empty string) was the
    bug: identical malformed CSS recorded 1 tokenizer error and 1 parse
    error as a `<style>` body and 0/0 as a `style=` attribute. Executed
    both ways before and after; wikipedia.html carries 237 non-empty `style=`
    attributes (of 340 present), so this was a real hole in a real measurement.
    Both figures executed, not counted by eye.
    """
    parser = CssParser("")
    tokenizer = CssTokenizer(source)
    tokens = list(tokenizer.tokenize())
    metrics["tokenizer_parse_errors"] += tokenizer.metrics["parse_errors"]
    out = _cascade_declarations(
        parser.parse_declarations(tokens),
        normal_rank=_RANK_INLINE_NORMAL,
        important_rank=_RANK_INLINE_IMPORTANT,
        order=order,
        metrics=metrics,
    )
    metrics["css_parse_errors"] += len(parser.errors)
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

    # 0. Custom properties, before anything that could reference one. They
    #    cascade like ordinary declarations and inherit, so this element's
    #    map is the parent's with its own winners layered on top -- and the
    #    parent's dict is reused unchanged when there are none, so an
    #    inheriting subtree does not allocate a dict per node.
    own_custom = {k: v for k, v in declared.items() if is_custom_property(k)}
    if own_custom:
        style.custom_properties = {**parent.custom_properties, **own_custom}
        declared = {
            k: v for k, v in declared.items() if not is_custom_property(k)
        }
    else:
        style.custom_properties = parent.custom_properties

    # 0b. `var()` substitution, now that this element's custom properties
    #     are known and before the value parser or the wide keywords see
    #     anything. This is the whole reason `_PendingValue` exists: the
    #     same `_Declaration` object is shared by every element the rule
    #     matched, and the answer differs per element.
    declared = _resolve_pending_values(declared, style.custom_properties, metrics)
    declared = _resolve_wide_keywords(declared, parent)

    # 1. font-size, against the PARENT's. Nothing else may be computed
    #    first, because everything else needs the answer.
    font_size = _compute_font_size(
        declared.get("font-size"),
        parent_font_px=parent.font_size_px,
        root_font_px=root_font_px,
    )
    font_size_applied = 0
    if font_size is not None:
        style.font_size = font_size
        # Counted here because `_compute_rest` `continue`s past `font-size`
        # and so never sees it. Until this line existed, every successfully
        # applied `font-size` was missing from `declarations_applied` --
        # an emitted metric that was systematically low with nothing
        # saying so. Verified: `p{font-size:20px}` moved 12 -> 13, matching
        # what `color` and `width` each contribute.
        font_size_applied = 1
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
            "color",
            declared["color"],
            font_px=own_font_px,
            root_px=root_font_px,
            own_color=style.color,
        )

    # 2b. `border-*-color`'s initial value is `currentcolor`, so an element
    #     that declares no border colour gets its own. Seeded before step 3
    #     so a declared border colour still wins.
    for prop in _BORDER_COLOR_PROPS:
        style.set(prop, style.color)

    # 3. Everything else, against the element's OWN font-size and colour.
    applied = _compute_rest(
        style,
        {k: v for k, v in declared.items() if k != "color"},
        own_font_px=own_font_px,
        root_font_px=root_font_px,
        own_color=style.color,
    )
    metrics["declarations_applied"] += (
        applied + int("color" in declared) + font_size_applied
    )

    # 4. A border with no style has no width, whatever the width said.
    _zero_widths_of_borderless_sides(style)

    # 5. `vertical-align: <percentage>`, which needs the computed
    #    `line-height` step 3 just wrote. See
    #    `_resolve_vertical_align_percentage`.
    _resolve_vertical_align_percentage(style, metrics, own_font_px)
    return style


def _used_line_height_px(line_height: object, own_font_px: float) -> float | None:
    """This element's used `line-height` in px, or None if it is not known
    until Task D.

    * a `<number>` is the number times the element's OWN font-size, which
      is why the number and not a product is what inherits;
    * a computed `<length>` is itself, when it is in px -- a viewport-unit
      line-height is still symbolic and is as unknown here as `normal`;
    * `normal` is the font's own preferred spacing, from `hhea`/`OS/2`
      metrics that arrive with Task D.
    """
    if isinstance(line_height, Length):
        return float(line_height.value) if line_height.unit == "px" else None
    if isinstance(line_height, (int, float)) and not isinstance(line_height, bool):
        return float(line_height) * own_font_px
    return None


def _resolve_vertical_align_percentage(
    style: ComputedStyle, metrics: Counter[str], own_font_px: float
) -> None:
    """`vertical-align: <percentage>` against the element's own *used*
    `line-height` -- the third percentage category, and the honest one.

    See `docs/percentage-resolution.md`. A percentage width resolves against
    the containing block and cannot be known here; a percentage line-height
    resolves against the element's own font-size and always can. This one is
    neither: it is known when `line-height` is a number or a px length and
    not when `line-height` is `normal`, so it is resolved in the first two
    cases and left symbolic in the third.

    Deferring it wholesale would throw away two thirds of the answers;
    resolving the third case against a guessed `1.2 x font-size` would
    produce a plausible number nothing downstream could distinguish from a
    real one. `vertical_align_percent_deferred` is what makes the remainder
    a figure Task D can look for rather than an absence -- the same
    discipline as `link_stylesheets_skipped`.

    Runs after `_compute_rest`, because it needs this element's computed
    `line-height`, which `_compute_rest` is what writes.
    """
    value = style.vertical_align
    if not isinstance(value, Percent):
        return
    used = _used_line_height_px(style.line_height, own_font_px)
    if used is None:
        metrics["vertical_align_percent_deferred"] += 1
        return
    style.vertical_align = Length(round(value.value / 100.0 * used, 6), "px")


def _zero_widths_of_borderless_sides(style: ComputedStyle) -> None:
    """CSS 2.1 section 8.5.1: `border-*-width` computes to `0` when the
    corresponding `border-*-style` is `none` or `hidden`.

    This is why the *computed* default is 0 while the *specified* initial
    value is `medium`: with no border declared at all the style is `none`
    and the width is zero, but `border: solid red` specifies a style, so the
    omitted width falls back to `medium` and is painted at 3px. Collapsing
    those two into one constant gets one of the two cases wrong whichever
    constant is chosen.
    """
    for style_prop, width_prop in zip(_BORDER_STYLE_PROPS, _BORDER_WIDTH_PROPS):
        if style.get(style_prop) in _BORDERLESS_STYLES:
            style.set(width_prop, _ZERO_LENGTH)


def _resolve_pending(
    pending: _PendingValue,
    custom_properties: dict,
    metrics: Counter[str],
) -> dict[str, object] | None:
    """Substitute one deferred declaration's `var()`s and parse the result.

    Every refusal is a counter, never a silence: `var_substitutions` for the
    ones that worked, one of the four `VAR_*` reasons for a substitution
    this engine declined, and `var_substituted_value_invalid` when the
    substitution succeeded and the *result* was not valid for the property
    (`width: var(--x)` with `--x: red` -- a declaration a browser also
    discards at computed-value time).
    """
    if not pending.attempted:
        pending.attempted = True
        metrics["var_declarations_attempted"] += 1
    substituted, reason = substitute_var(list(pending.tokens), custom_properties)
    if substituted is None:
        metrics[reason] += 1
        return None
    longhands = parse_declaration_value(pending.prop_name, substituted)
    if longhands is None:
        metrics["var_substituted_value_invalid"] += 1
        return None
    metrics["var_substitutions"] += 1
    if not pending.resolved:
        # Once per declaration, not once per element: this is the
        # declaration-level counterpart of `declarations_pending_var`.
        metrics["var_declarations_resolved"] += 1
        pending.resolved = True
    return _reset_omitted_longhands(pending.prop_name, longhands)


def _resolve_pending_values(
    declared: dict[str, object],
    custom_properties: dict,
    metrics: Counter[str],
) -> dict[str, object]:
    """Replace every winning `_PendingValue` with the longhand it produced.

    One substitution per `_PendingValue` per element, not one per longhand:
    `border: 1px solid var(--x)` won twelve longhands with the same object,
    and substituting twelve times would multiply every `var_*` counter by
    twelve while changing no value.
    """
    if not any(isinstance(v, _PendingValue) for v in declared.values()):
        return declared
    cache: dict[int, dict[str, object] | None] = {}
    out: dict[str, object] = {}
    for prop, value in declared.items():
        if not isinstance(value, _PendingValue):
            out[prop] = value
            continue
        key = id(value)
        if key not in cache:
            cache[key] = _resolve_pending(value, custom_properties, metrics)
        longhands = cache[key]
        if longhands is not None and prop in longhands:
            out[prop] = longhands[prop]
        # Otherwise the longhand is simply not declared on this element and
        # falls back to inheritance or its initial value -- which is what a
        # browser does with a declaration that is invalid at computed-value
        # time.
    return out


def _resolve_wide_keywords(
    declared: dict[str, object], parent: ComputedStyle
) -> dict[str, object]:
    """Replace every `WideKeyword` with the value it names.

    `values.py` cannot do this -- `inherit` needs the parent's computed
    value and `initial` needs `INITIAL_SPECIFIED`, and it has neither -- so
    it hands the keyword through and this is where the three are decided:

        initial   the property's initial *specified* value, which then
                  computes normally (`border-*-color: initial` is
                  `currentcolor`, and resolves to this element's colour).
        inherit   the parent's *computed* value, taken as-is.
        unset     `inherit` for an inherited property, `initial` otherwise.

    Running the parent's already-computed value back through
    `_computed_value` is harmless -- a px `Length` resolves to itself, and
    every other computed shape falls through untouched -- so the two paths
    do not need to be kept apart the way the two `em` bases do.
    """
    if not any(isinstance(v, WideKeyword) for v in declared.values()):
        return declared
    out: dict[str, object] = {}
    for prop, value in declared.items():
        if not isinstance(value, WideKeyword):
            out[prop] = value
        elif value.name == "inherit" or (
            value.name == "unset" and prop in INHERITED
        ):
            out[prop] = parent.get(prop)
        else:
            out[prop] = INITIAL_SPECIFIED[prop]
    return out


def _inherit_from(parent: ComputedStyle) -> ComputedStyle:
    """A fresh style: initial everywhere, inherited where INHERITED says."""
    style = ComputedStyle()
    for prop in INHERITED:
        style.set(prop, parent.get(prop))
    return style


def style_document(
    document: Node,
    author_css: list[str],
    viewport: Viewport | None = None,
    external_css: dict[str, str] | None = None,
) -> Counter[str]:
    """Attach a `ComputedStyle` to every node of `document`.

    `author_css` is a list of stylesheet sources -- what a driver got from
    somewhere other than the document itself. In-document `<style>` elements
    are found and cascaded automatically; `<link rel=stylesheet>` is counted
    and not fetched.

    `external_css` maps a `<link rel=stylesheet>`'s `href` -- exactly as
    written in the document -- to that sheet's source. Supplying it is how
    an external sheet enters the cascade *at the position its `<link>`
    occupies*, which is what source order requires; `author_css` is for
    sheets with no position in the document and still cascades before it.
    A `<link>` with no entry here is counted in `link_stylesheets_skipped`
    exactly as it was before external sheets could be supplied at all.
    `scripts/corpus.py` builds this mapping from a page's manifest.

    `viewport` is optional and opt-in. Without one, at-rules are counted and
    skipped exactly as they were through Phase 2 -- which keeps every figure
    measured before `@media` support reproducible, so the two can be
    compared rather than conflated. With one, `@media` blocks whose queries
    match contribute their rules to the cascade; see `cssparse/media.py` for
    what is evaluated and what is merely recorded.

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
    # Seeded so the key is present at zero rather than absent: a driver
    # writing one CSV row per key would otherwise emit no row at all for a
    # page with no external stylesheets, and "no row" and "zero" are
    # different findings for the analysis half. The counting itself happens
    # in the document-order walk below, which is the only place that knows
    # whether a given link was supplied.
    metrics["link_stylesheets_skipped"] = 0
    metrics["link_stylesheets_total"] = 0
    # Same reason: the four drop reasons partition `declarations_dropped`,
    # and a partition with a missing part is not one. A page that drops
    # nothing for a given reason must say `0`, not say nothing.
    for reason in DROP_REASONS:
        metrics[f"declarations_dropped_{reason.replace('-', '_')}"] = 0
    # Seeded for the same reason: Task D goes looking for this number, and
    # "no row" and "zero" are different findings.
    metrics["vertical_align_percent_deferred"] = 0

    order = _Counter()
    rules = _parse_sheet(UA_CSS, "ua", order, metrics, viewport)
    metrics["ua_rules"] = len(rules)

    # Sheets with no position in the document -- a UA-supplied user sheet, or
    # a caller passing raw CSS -- cascade before it. Anything attributable to
    # a `<link>` belongs in `external_css` instead, so it lands in the right
    # place in source order.
    for source in author_css:
        metrics["author_stylesheets"] += 1
        rules.extend(_parse_sheet(source, "author", order, metrics, viewport))

    # ONE pass, in document order, over both `<style>` and `<link>`.
    #
    # These used to be two passes: every external sheet cascaded before every
    # in-document `<style>`, whatever the markup said. Source order is the
    # last tiebreak in the cascade, so that silently changed the winner for
    # any two declarations of equal origin, importance and specificity --
    # which in real CSS is common, not a corner case. Wikipedia links two
    # sheets and then ships 18 `<style>` blocks; under the old order every
    # one of those blocks won ties it should sometimes have lost.
    external = external_css or {}
    for element in elements:
        if element.tag_name == "style":
            source = _style_element_source(element)
            if source is None:
                metrics["style_elements_skipped"] += 1
                continue
            metrics["style_elements"] += 1
            rules.extend(_parse_sheet(source, "author", order, metrics, viewport))
            continue

        if element.tag_name != "link" or "stylesheet" not in _rel_tokens(element):
            continue
        href = element.attrs.get("href", "").strip()
        if not href:
            # Nothing that would have been fetched; not a skipped sheet.
            continue
        # `rel=icon`, `rel=preconnect`, `rel=canonical` and the rest are not
        # stylesheets and never reach here. `rel="alternate stylesheet"`
        # does: it IS a stylesheet, just one the user would have to select,
        # so it is counted. It is not applied unless a caller puts it in
        # `external_css`, and `scripts/corpus.py` deliberately does not.
        metrics["link_stylesheets_total"] += 1
        source = external.get(href)
        if source is None:
            # Still the Phase 2 meaning: a linked sheet the cascade did not
            # get. With no `external_css` that is every link, so the counter
            # is unchanged for every caller that supplies nothing.
            metrics["link_stylesheets_skipped"] += 1
            continue
        metrics["link_stylesheets_supplied"] += 1
        metrics["author_stylesheets"] += 1
        rules.extend(_parse_sheet(source, "author", order, metrics, viewport))

    metrics["rules_total"] = len(rules)
    index = RuleIndex(rules, selector_of=_selector_of)

    root_font_px = INITIAL_FONT_SIZE_PX
    initial = ComputedStyle()
    # The root element is the first element in document order, and it is the
    # only one whose font-size `rem` refers to. Identified up front rather
    # than inferred from "my parent is not an Element", which is also true
    # of any stray element the tree builder left hanging off the Document --
    # and letting one of those redefine `rem` for the rest of the page would
    # be a silent, document-wide wrong number.
    root_element = next((n for n in nodes if isinstance(n, Element)), None)

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
            if node is root_element:
                # Its own `rem` resolved against the initial 16px (CSS
                # Values 4: `rem` on the root element refers to the
                # property's initial value); every descendant resolves
                # `rem` against what it just computed.
                root_font_px = node.computed_style.font_size_px
        else:
            # Text, Comment, DocumentType, Document. No declarations can
            # target them -- `matches()` returns False for a non-Element --
            # so their style is pure inheritance. Text nodes need it: layout
            # asks a text run for its colour and font-size directly rather
            # than carrying a special case up to its parent element.
            node.computed_style = _inherit_from(parent_style)
        metrics["nodes_styled"] += 1

    # The bridge between the parse-time count and the runtime one, in three
    # parts rather than one. `refused` is the residue of the old
    # `var-unresolved` drop bucket -- declarations an element asked for and
    # this engine could not produce. `unmatched` is not a failure of any
    # kind: the rule matched no element on this page, which is true of most
    # of a large stylesheet's rules and would be equally true of the same
    # declarations without any `var()` in them. Reporting the two as one
    # number said 288 where the real figure is 7.
    metrics["var_declarations_refused"] = (
        metrics["var_declarations_attempted"] - metrics["var_declarations_resolved"]
    )
    metrics["var_declarations_unmatched"] = (
        metrics["declarations_pending_var"] - metrics["var_declarations_attempted"]
    )

    metrics["cascade_time_ms"] = round((time.perf_counter() - started) * 1000, 3)
    return metrics


__all__ = [
    "INHERITED",
    "INITIAL_FONT_SIZE_PX",
    "LONGHANDS",
    "ComputedStyle",
    "style_document",
]
