"""
Mayshay CSS property-value parsing.

Task I of Phase 2. Parses a `Declaration.value` token list (Task F/E's flat
`list[CssToken]`, no tree) into typed values for nine properties: `display`,
`width`, `height`, `margin`, `padding`, `border`, `color`,
`background-color`, `font-size`.

**The load-bearing decision in this module**: computed values are not used
values. `width: 50%` and `margin: auto` cannot be resolved to a number
without a containing block, and no containing block exists until layout
(Phase 3). They are kept symbolic here -- `Percent(50)` and the `AUTO`
sentinel -- rather than collapsed to a float or to zero. Anything that
forces a premature resolution (treating `auto` as `0`, treating `50%` as
`0.5` of some guessed number) reintroduces exactly the bug this module
exists to prevent, and the mistake would not surface until layout produces
visibly wrong boxes.

Two entry points, matching the task brief (plus one added later --
`normalize_property_name`, below them):

    parse_declaration_value(name, tokens) -> dict[str, object] | None
        Parses one declaration's value. Returns `None` -- dropping the
        *declaration*, not the rule -- when the value's grammar is invalid
        for `name` (`width: banana`, `color: #gg0000`, ...). For a shorthand
        (`margin`, `padding`, `border`) the returned dict already has the
        expanded longhand keys; `parse_declaration_value("margin", ...)`
        never returns `{"margin": ...}`.

    expand_shorthand(name, parsed) -> dict[str, object]
        The expansion step above, exposed on its own so a caller that
        already has the shorthand's *parsed* components -- not raw tokens --
        can still get the longhand dict. `parsed` is always a
        `dict[str, object]`: `{"top"/"right"/"bottom"/"left": value}` for
        `margin`/`padding` (always all four keys), or any subset of
        `{"width"/"style"/"color": value}` for `border`. One shape across
        every shorthand, deliberately -- see `expand_shorthand`'s own
        docstring for why an earlier list-vs-dict split was replaced.

**Property names reaching this module are normalised, and that is part of
the interface, not an implementation detail.** `parse_declaration_value`
ASCII-lowercases its `name` argument before dispatching, so `BORDER` and
`border` parse identically. A caller that makes its own decision keyed on a
property name -- Task J's shorthand-reset table is the one that exists --
must apply the same normalisation, and `normalize_property_name` is exported
so it can do so from this module's rule rather than from a guess. Leaving
this implicit is what let `p { BORDER: solid blue }` parse correctly and
skip its reset; see deviation 12.

Deliberate deviations and omissions, documented so they don't surprise
Task J or Phase 3 later:

1. **Length units are a fixed allowlist**
   (px, em, rem, ex, ch, vw, vh, vmin, vmax, cm, mm, q, in, pt, pc).
   An unrecognized unit -- a typo, a future unit, `Q` vs `q` handled via
   lowercasing -- invalidates the value. No corpus case needed anything
   outside this set.
2. **Unitless nonzero lengths are invalid**, full stop. Quirks-mode
   unitless-length coercion is a layout-time concern (it depends on the
   document's rendering mode, which this module never sees) and is left to
   Phase 3, not smuggled in here as a silent `px` default. Unitless `0` is
   valid per spec (`<length>` permits a literal zero without a unit) and is
   normalized to `Length(0, "px")`.
3. **CSS-wide keywords (`inherit`, `initial`, `unset`, `revert`) are not
   recognized by any of the nine properties' grammars here.** They are
   cascade-time concepts -- Task J's problem, since resolving them requires
   the property's initial value and the parent's computed value, neither of
   which this module has access to. A declaration using one is invalid here
   and its declaration is dropped; if Task J needs them it will have to
   intercept the keyword before calling into this module, not expect this
   module to pass it through.
   (Task A2 reverses part of this -- see deviation 15.)
4. **The named-color table is the full CSS Color Level 4 extended-keyword
   list -- 148 entries** (the 147-keyword CSS3 SVG-derived list plus
   `rebeccapurple`), transcribed and verified against the spec's hex values
   (`test_color_keyword_table_is_complete` pins the count and spot-checks
   several non-famous entries: `rebeccapurple`, `papayawhip`,
   `mediumspringgreen`, `darkslategrey`, `cadetblue`). This table was
   originally shipped with only 22 entries -- correct as far as they went,
   but a missing keyword silently drops a declaration on a real page, which
   is the exact failure mode the "computed values are not used values"
   discipline elsewhere in this module exists to prevent; a merely-plausible
   subset was the wrong bar for a table like this. `transparent` and
   `currentcolor` are handled separately (deviation 5) and are not part of
   this 148-entry table, matching how the spec itself treats them as
   special keywords rather than named colors.
5. **`currentcolor` is preserved as `Keyword("currentcolor")`, not resolved
   to a `Color`.** It names *this element's `color` value*, which is a
   cascade-time fact this module does not have -- the same "computed value
   is not a used value" principle that keeps `Percent`/`AUTO` symbolic
   applies here too. `transparent`, by contrast, needs no such context (it
   is always `rgba(0,0,0,0)`) and is resolved eagerly to `Color(0,0,0,0.0)`.
6. **`rgb()`/`rgba()` support only the legacy comma syntax**
   (`rgb(255, 0, 0)`, `rgba(255, 0, 0, .5)`), with either `<number>` or
   `<percentage>` per channel. The CSS Color 4 space/slash syntax
   (`rgb(255 0 0 / 50%)`) and `hsl()`/`hwb()`/`lab()`/`lch()`/`color()` are
   not implemented; none appear in the nine-property corpus this phase
   targets. `rgb()` accepts 3 or 4 arguments (a trailing alpha is legal
   CSS4, `rgba()` is treated as a synonym requiring the alpha), matching
   what real stylesheets actually write.
7. **`border`'s components (`<width>`, `<style>`, `<color>`) may appear in
   any order, but at most one of each kind** -- two lengths in one `border`
   value is invalid, not "last one wins". **Missing components are simply
   absent from the result**; `border: solid` produces only the
   `border-*-style` keys, with no synthesized `medium`/`currentcolor`
   fallback for the omitted width/color. Manufacturing those initial values
   here would bake a cascade-independent guess into a value that Task J's
   cascade is the one place with enough information (inheritance, prior
   declarations) to fill in correctly.
8. **`border-width` accepts only `<length>`** -- not the spec's
   `thin | medium | thick` keyword trio, and not `<percentage>` (correctly;
   percentages are not valid CSS for border widths). The keyword trio is
   unused in the corpus this phase targets; flag it if that changes.
9. **`padding` does not accept `auto`** (spec-correct: only `margin` does).
   Both otherwise share the same one-to-four-value expansion.
10. **No `calc()`, `var()`, or custom-property support anywhere.** A
    property value containing either is invalid here and the declaration is
    dropped. Nothing in the nine-property set needs them this phase.
11. **Component splitting (`_split_top_level`) is a small hand-rolled
    top-level-whitespace splitter, not `cssparse.parser`'s
    `_consume_component_value`.** The parser's version is a private,
    underscore-prefixed helper of a different module; re-deriving the ~15
    lines needed here (split on top-level whitespace, keep a function's
    argument list together up to its matching `)`) is a smaller coupling
    than importing another module's internals. Bracket matching is by depth
    counting, not a nested tree -- sufficient here because the only bracketed
    construct any of these nine properties' values can contain is a
    `<color>` function's argument list.
12. **Property names and identifier keywords are matched
    ASCII-case-insensitively, via `_ascii_lower`, not `str.lower()`.** CSS
    defines its case-insensitivity as ASCII-only; `str.lower()` folds the
    full Unicode table, and this module used it at ten sites until this was
    caught. Executed before the fix: `display: bloc<U+212A KELVIN SIGN>`
    parsed as `Keyword("block")` and `color: pin<U+212A>` as
    `Color(255,192,203)`; a browser rejects both. Executed after: both
    return `None`, and the ASCII spellings still parse. The property-name
    normalisation is additionally exposed as `normalize_property_name` --
    see the note above the deviation list for the bug that made that
    necessary.
13. **The box-model longhands are supported, and `background` is not.**
    Through Phase 2 the table held three shorthands (`margin`, `padding`,
    `border`) and none of their longhands, so the only way to set
    `ComputedStyle.margin_top` was to write the shorthand. That was a
    consequence of the old `if name == ...` dispatch chain rather than a
    decision anyone made, and it was the largest slice of the corpus's
    dropped declarations no other deviation covered -- 395 declarations,
    with `margin-left: auto` centring unreachable. Phase 3 Task A2 added
    **27** property names: the eight `margin-`/`padding-` longhands, the
    twelve `border-{side}-{width,style,color}` longhands, the three
    `border-width`/`-style`/`-color` four-value shorthands and the four
    `border-{side}` shorthands. (27, not the 28 the Phase 3 plan quoted --
    that figure counted `background` alongside them. Executed:
    `len(SUPPORTED_PROPERTIES)` is 36, of which 9 predate Task A2.)

    None of the 27 needed a new component parser: a longhand is its
    shorthand's component grammar with the one-to-four rule removed, and
    `border-width`/`-style`/`-color` are that rule over one component kind.
    `_four_sided` is where the rule now lives, once.

    `background` is still outside the table and still dropped --
    `test_the_box_model_longhands_are_supported` asserts both halves so the
    new boundary cannot drift any more quietly than the old one did.
14. **Nine text and box-sizing properties were added by Phase 3 Task A2**:
    `white-space`, `line-height`, `font-family`, `font-weight`,
    `font-style`, `text-align`, `vertical-align`, `box-sizing` and
    `list-style-type`. Three carry their own decisions:

    * **`line-height: normal` stays `Keyword("normal")`**, not a number.
      Its used value is the font's own preferred spacing, which needs
      metrics that arrive with Task D; `1.2 x font-size` is what every
      engine happens to use and is not what the spec says, so resolving it
      here would bake a guess into a value nothing could later distinguish
      from a declared one. A `<number>` stays a number for the opposite
      reason -- CSS 2.1 10.8.1 says the computed value of a numeric
      line-height *is* the number, and the number is what inherits.
      A `<percentage>`, uniquely among this engine's percentages, is
      **not** left symbolic: it refers to the element's own font-size,
      which the cascade knows, so `cascade._PERCENT_OF_OWN_FONT_SIZE`
      resolves it to a length there and that length inherits. A percentage
      width refers to the containing block and must stay symbolic; same
      token type, opposite rule, and the reason is which quantity it names.
    * **`font-family` is a tuple of names, kept as parsed**, generics
      included and not distinguished. Nothing consumes the list this phase
      -- Phase 3 renders with one vendored font -- so a `serif`-vs-family
      distinction would be a decision with no consumer to be right for.
      Recording the list at all is what makes the eventual fallback chain
      implementable rather than a re-parse.
    * **`font-weight` resolves `normal`/`bold` to 400/700 here**, because
      their computed values *are* those numbers. `bolder` and `lighter` are
      not implemented: their computed value depends on the parent's weight
      through a lookup table, which is a cascade-time fact this module does
      not have. Neither appears anywhere in the corpus (executed).

    `list-style-type` is a closed list of CSS Counter Styles 3's predefined
    styles. The property also admits a `<custom-ident>` naming an
    `@counter-style` rule, which this engine does not parse, so an
    unrecognised identifier is `unsupported-value` rather than `invalid` --
    Wikipedia uses six such names.
15. **`inherit`, `initial` and `unset` are accepted; `revert` is not.**
    See `WideKeyword`. Deviation 3 above described the Phase 2 state.
16. **`display` is a closed keyword allow-list** (20 entries, above --
    counted by `len(_DISPLAY_KEYWORDS)`, not by eye). A `display` value
    outside it is invalid rather than passed through, for
    the same reason the color table had to be complete: a keyword this
    module does not know must not reach the cascade as an unresolved
    string. `flow-root` is the one such keyword in the corpus (1 drop on
    wikipedia, executed). Widening the list is a one-line change once a
    layout mode exists that can honour the new value.
"""

from __future__ import annotations

from dataclasses import dataclass

from mayshay.cssparse.tokenizer import (
    Comma,
    String,
    CssToken,
    Dimension,
    EOFToken,
    Function,
    Hash,
    Ident,
    Number,
    Percentage,
    RParen,
    Whitespace,
)


def _ascii_lower(text: str) -> str:
    """ASCII-only case fold. Duplicated from `tokenizer.py` for the reason
    that module's copy states: importing another module's private name is
    the worse coupling.

    `str.lower()` is wrong here for the same reason it is wrong there. CSS
    identifier and property-name matching is ASCII-case-insensitive, but
    Python's `str.lower()` folds the whole Unicode case table: U+212A KELVIN
    SIGN becomes `k`, so `display: bloc<U+212A>` would be accepted as
    `block` and `color: pin<U+212A>` as `pink`. A browser rejects both.
    Verified against this module before the fix -- both were accepted.
    """
    return "".join(chr(ord(ch) + 0x20) if "A" <= ch <= "Z" else ch for ch in text)


def normalize_property_name(name: str) -> str:
    """The canonical spelling of a CSS property name: ASCII-lowercased.

    **This is the module's normalisation contract, exposed rather than left
    implicit.** `parse_declaration_value` applies it to its own `name`
    argument, so a caller may pass `BORDER` and get correct longhands back.
    That was silently *not* enough for Task J's cascade, which keyed its
    shorthand-reset table on the raw `Declaration.name` and so skipped the
    reset for `BORDER` while accepting the value -- a wrong computed value
    with no error anywhere. A caller that makes its own decision from a
    property name must normalise it through this function first; that is
    what it exists to say.
    """
    return _ascii_lower(name)


# --------------------------------------------------------------------------
# Value types
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Length:
    value: int | float
    unit: str


@dataclass(frozen=True)
class Percent:
    """A `<percentage>`. Deliberately not a fraction of anything -- see the
    module docstring's load-bearing decision. `Percent(50)` means the token
    `50%`, not `0.5`.
    """

    value: int | float


@dataclass(frozen=True)
class Color:
    r: int
    g: int
    b: int
    a: float = 1.0


@dataclass(frozen=True)
class Keyword:
    """A property-specific keyword this module recognized but deliberately
    did not resolve further: a `display` value (`Keyword("block")`), a
    `font-size` absolute/relative size (`Keyword("larger")`), a
    `border-style` (`Keyword("solid")`), or `currentcolor` (deviation 5).
    """

    name: str


@dataclass(frozen=True)
class _Auto:
    """The sentinel type behind `AUTO`. A class (not just a bare object())
    so its repr is informative and so nothing else can accidentally produce
    an equal-but-distinct instance -- callers are expected to compare with
    `is AUTO`, exactly as the brief's own test does.
    """

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        return "AUTO"


AUTO = _Auto()


@dataclass(frozen=True)
class WideKeyword:
    """A CSS-wide keyword -- `inherit`, `initial` or `unset` -- surviving to
    the cascade unresolved.

    Deliberately *not* a `Keyword`. A `Keyword` is a property-specific value
    this module recognised and chose not to resolve further; a `WideKeyword`
    is valid on every property and cannot be resolved here at all, because
    `inherit` needs the parent's computed value and `initial` needs the
    property's initial-value table, neither of which this module has. A
    caller that treats one as the other would silently store the string
    `"inherit"` as a colour.

    `revert` is not among them: it needs origin-level rollback the cascade
    does not model, so it stays unsupported and counted rather than faked.
    """

    name: str


# `revert` is absent on purpose -- see `WideKeyword`.
_ACCEPTED_WIDE_KEYWORDS = frozenset({"inherit", "initial", "unset"})


# --------------------------------------------------------------------------
# Keyword / unit tables
# --------------------------------------------------------------------------

_LENGTH_UNITS = frozenset({
    "px", "em", "rem", "ex", "ch",
    "vw", "vh", "vmin", "vmax",
    "cm", "mm", "q", "in", "pt", "pc",
})

# The internal table display types are here because a UA stylesheet that
# gives `<table>` `display: table` and leaves `<tr>`/`<tbody>`/`<caption>`
# at the initial `inline` is worse than one that says nothing at all: the
# container establishes a formatting context its own children then ignore.
# See `ua.py`. `inline-table` is included for symmetry with the other
# `inline-*` pairs already present.
_DISPLAY_KEYWORDS = frozenset({
    "block", "inline", "inline-block", "none",
    "flex", "inline-flex", "grid", "inline-grid",
    "list-item", "contents",
    "table", "inline-table",
    "table-row", "table-cell",
    "table-row-group", "table-header-group", "table-footer-group",
    "table-column", "table-column-group", "table-caption",
})

_BORDER_STYLE_KEYWORDS = frozenset({
    "none", "hidden", "dotted", "dashed", "solid",
    "double", "groove", "ridge", "inset", "outset",
})

_FONT_SIZE_KEYWORDS = frozenset({
    "xx-small", "x-small", "small", "medium", "large",
    "x-large", "xx-large", "xxx-large", "smaller", "larger",
})

# See deviation 4: the full 148-entry CSS Color Level 4 extended-keyword
# list (the 147-keyword CSS3 SVG-derived table plus `rebeccapurple`).
# Deliberately includes the `green`/`lime` trap correctly: CSS `green` is
# #008000, not the bright green most people picture, which is `lime`.
# `transparent`/`currentcolor` are handled separately, not here.
_COLOR_KEYWORDS: dict[str, tuple[int, int, int]] = {
    "aliceblue": (240, 248, 255), "antiquewhite": (250, 235, 215),
    "aqua": (0, 255, 255), "aquamarine": (127, 255, 212),
    "azure": (240, 255, 255), "beige": (245, 245, 220),
    "bisque": (255, 228, 196), "black": (0, 0, 0),
    "blanchedalmond": (255, 235, 205), "blue": (0, 0, 255),
    "blueviolet": (138, 43, 226), "brown": (165, 42, 42),
    "burlywood": (222, 184, 135), "cadetblue": (95, 158, 160),
    "chartreuse": (127, 255, 0), "chocolate": (210, 105, 30),
    "coral": (255, 127, 80), "cornflowerblue": (100, 149, 237),
    "cornsilk": (255, 248, 220), "crimson": (220, 20, 60),
    "cyan": (0, 255, 255), "darkblue": (0, 0, 139),
    "darkcyan": (0, 139, 139), "darkgoldenrod": (184, 134, 11),
    "darkgray": (169, 169, 169), "darkgreen": (0, 100, 0),
    "darkgrey": (169, 169, 169), "darkkhaki": (189, 183, 107),
    "darkmagenta": (139, 0, 139), "darkolivegreen": (85, 107, 47),
    "darkorange": (255, 140, 0), "darkorchid": (153, 50, 204),
    "darkred": (139, 0, 0), "darksalmon": (233, 150, 122),
    "darkseagreen": (143, 188, 143), "darkslateblue": (72, 61, 139),
    "darkslategray": (47, 79, 79), "darkslategrey": (47, 79, 79),
    "darkturquoise": (0, 206, 209), "darkviolet": (148, 0, 211),
    "deeppink": (255, 20, 147), "deepskyblue": (0, 191, 255),
    "dimgray": (105, 105, 105), "dimgrey": (105, 105, 105),
    "dodgerblue": (30, 144, 255), "firebrick": (178, 34, 34),
    "floralwhite": (255, 250, 240), "forestgreen": (34, 139, 34),
    "fuchsia": (255, 0, 255), "gainsboro": (220, 220, 220),
    "ghostwhite": (248, 248, 255), "gold": (255, 215, 0),
    "goldenrod": (218, 165, 32), "gray": (128, 128, 128),
    "green": (0, 128, 0), "greenyellow": (173, 255, 47),
    "grey": (128, 128, 128), "honeydew": (240, 255, 240),
    "hotpink": (255, 105, 180), "indianred": (205, 92, 92),
    "indigo": (75, 0, 130), "ivory": (255, 255, 240),
    "khaki": (240, 230, 140), "lavender": (230, 230, 250),
    "lavenderblush": (255, 240, 245), "lawngreen": (124, 252, 0),
    "lemonchiffon": (255, 250, 205), "lightblue": (173, 216, 230),
    "lightcoral": (240, 128, 128), "lightcyan": (224, 255, 255),
    "lightgoldenrodyellow": (250, 250, 210), "lightgray": (211, 211, 211),
    "lightgreen": (144, 238, 144), "lightgrey": (211, 211, 211),
    "lightpink": (255, 182, 193), "lightsalmon": (255, 160, 122),
    "lightseagreen": (32, 178, 170), "lightskyblue": (135, 206, 250),
    "lightslategray": (119, 136, 153), "lightslategrey": (119, 136, 153),
    "lightsteelblue": (176, 196, 222), "lightyellow": (255, 255, 224),
    "lime": (0, 255, 0), "limegreen": (50, 205, 50),
    "linen": (250, 240, 230), "magenta": (255, 0, 255),
    "maroon": (128, 0, 0), "mediumaquamarine": (102, 205, 170),
    "mediumblue": (0, 0, 205), "mediumorchid": (186, 85, 211),
    "mediumpurple": (147, 112, 219), "mediumseagreen": (60, 179, 113),
    "mediumslateblue": (123, 104, 238), "mediumspringgreen": (0, 250, 154),
    "mediumturquoise": (72, 209, 204), "mediumvioletred": (199, 21, 133),
    "midnightblue": (25, 25, 112), "mintcream": (245, 255, 250),
    "mistyrose": (255, 228, 225), "moccasin": (255, 228, 181),
    "navajowhite": (255, 222, 173), "navy": (0, 0, 128),
    "oldlace": (253, 245, 230), "olive": (128, 128, 0),
    "olivedrab": (107, 142, 35), "orange": (255, 165, 0),
    "orangered": (255, 69, 0), "orchid": (218, 112, 214),
    "palegoldenrod": (238, 232, 170), "palegreen": (152, 251, 152),
    "paleturquoise": (175, 238, 238), "palevioletred": (219, 112, 147),
    "papayawhip": (255, 239, 213), "peachpuff": (255, 218, 185),
    "peru": (205, 133, 63), "pink": (255, 192, 203),
    "plum": (221, 160, 221), "powderblue": (176, 224, 230),
    "purple": (128, 0, 128), "rebeccapurple": (102, 51, 153),
    "red": (255, 0, 0), "rosybrown": (188, 143, 143),
    "royalblue": (65, 105, 225), "saddlebrown": (139, 69, 19),
    "salmon": (250, 128, 114), "sandybrown": (244, 164, 96),
    "seagreen": (46, 139, 87), "seashell": (255, 245, 238),
    "sienna": (160, 82, 45), "silver": (192, 192, 192),
    "skyblue": (135, 206, 235), "slateblue": (106, 90, 205),
    "slategray": (112, 128, 144), "slategrey": (112, 128, 144),
    "snow": (255, 250, 250), "springgreen": (0, 255, 127),
    "steelblue": (70, 130, 180), "tan": (210, 180, 140),
    "teal": (0, 128, 128), "thistle": (216, 191, 216),
    "tomato": (255, 99, 71), "turquoise": (64, 224, 208),
    "violet": (238, 130, 238), "wheat": (245, 222, 179),
    "white": (255, 255, 255), "whitesmoke": (245, 245, 245),
    "yellow": (255, 255, 0), "yellowgreen": (154, 205, 50),
}

_HEX_DIGITS = frozenset("0123456789abcdefABCDEF")


# --------------------------------------------------------------------------
# Token-list helpers
# --------------------------------------------------------------------------


def _trim(tokens: list[CssToken]) -> list[CssToken]:
    """Strip leading/trailing `Whitespace` tokens. Interior whitespace is
    left alone -- it is what `_split_top_level` splits components on.
    """
    start, end = 0, len(tokens)
    while start < end and isinstance(tokens[start], Whitespace):
        start += 1
    while end > start and isinstance(tokens[end - 1], Whitespace):
        end -= 1
    return tokens[start:end]


def _split_top_level(tokens: list[CssToken]) -> list[list[CssToken]]:
    """Split on top-level `Whitespace`, keeping a `Function`'s argument list
    together as one component up to its matching `)`. See deviation 11.
    """
    groups: list[list[CssToken]] = []
    current: list[CssToken] = []
    depth = 0
    for tok in _trim(tokens):
        if isinstance(tok, Whitespace) and depth == 0:
            if current:
                groups.append(current)
                current = []
            continue
        current.append(tok)
        if isinstance(tok, Function):
            depth += 1
        elif isinstance(tok, RParen) and depth > 0:
            depth -= 1
    if current:
        groups.append(current)
    return groups


def _split_args(tokens: list[CssToken]) -> list[list[CssToken]]:
    """Split a function's inner tokens on top-level commas."""
    args: list[list[CssToken]] = []
    current: list[CssToken] = []
    depth = 0
    for tok in _trim(tokens):
        if isinstance(tok, Comma) and depth == 0:
            args.append(current)
            current = []
            continue
        if isinstance(tok, Function):
            depth += 1
        elif isinstance(tok, RParen) and depth > 0:
            depth -= 1
        current.append(tok)
    args.append(current)
    return args


# --------------------------------------------------------------------------
# Length / percentage / auto
# --------------------------------------------------------------------------


def _parse_length(tok: CssToken) -> Length | None:
    if isinstance(tok, Dimension):
        unit = _ascii_lower(tok.unit)
        if unit in _LENGTH_UNITS:
            return Length(tok.value, unit)
        return None
    if isinstance(tok, Number) and tok.value == 0:
        # Unitless zero is the one unitless <length> the spec allows.
        return Length(0, "px")
    return None


def _parse_length_percentage(tok: CssToken, *, allow_auto: bool) -> object | None:
    if isinstance(tok, Percentage):
        return Percent(tok.value)
    if allow_auto and isinstance(tok, Ident) and _ascii_lower(tok.value) == "auto":
        return AUTO
    return _parse_length(tok)


# --------------------------------------------------------------------------
# Color
# --------------------------------------------------------------------------


def _parse_hex_color(text: str) -> Color | None:
    if not text or any(ch not in _HEX_DIGITS for ch in text):
        return None
    if len(text) == 3:
        r, g, b = (int(ch * 2, 16) for ch in text)
        return Color(r, g, b, 1.0)
    if len(text) == 4:
        r, g, b, a = (int(ch * 2, 16) for ch in text)
        return Color(r, g, b, a / 255)
    if len(text) == 6:
        r, g, b = (int(text[i:i + 2], 16) for i in (0, 2, 4))
        return Color(r, g, b, 1.0)
    if len(text) == 8:
        r, g, b, a = (int(text[i:i + 2], 16) for i in (0, 2, 4, 6))
        return Color(r, g, b, a / 255)
    return None


def _channel(tok: CssToken) -> int | None:
    if isinstance(tok, Number):
        v = float(tok.value)
    elif isinstance(tok, Percentage):
        v = tok.value / 100 * 255
    else:
        return None
    return round(max(0.0, min(255.0, v)))


def _alpha(tok: CssToken) -> float | None:
    if isinstance(tok, Number):
        v = float(tok.value)
    elif isinstance(tok, Percentage):
        v = tok.value / 100
    else:
        return None
    return max(0.0, min(1.0, v))


def _parse_color_function(group: list[CssToken]) -> Color | None:
    if not group or not isinstance(group[0], Function):
        return None
    name = _ascii_lower(group[0].value)
    if name not in ("rgb", "rgba"):
        return None
    if not isinstance(group[-1], RParen):
        return None
    args = _split_args(group[1:-1])
    if name == "rgba" and len(args) != 4:
        return None
    if name == "rgb" and len(args) not in (3, 4):
        return None

    channel_toks = []
    for arg in args[:3]:
        arg = _trim(arg)
        if len(arg) != 1:
            return None
        channel_toks.append(arg[0])
    channels = [_channel(tok) for tok in channel_toks]
    if any(c is None for c in channels):
        return None

    alpha = 1.0
    if len(args) == 4:
        arg = _trim(args[3])
        if len(arg) != 1:
            return None
        alpha = _alpha(arg[0])
        if alpha is None:
            return None

    return Color(*channels, alpha)  # type: ignore[arg-type]


def _parse_color(tokens: list[CssToken]) -> object | None:
    groups = _split_top_level(tokens)
    if len(groups) != 1:
        return None
    group = groups[0]

    if len(group) == 1:
        tok = group[0]
        if isinstance(tok, Ident):
            name = _ascii_lower(tok.value)
            if name == "transparent":
                return Color(0, 0, 0, 0.0)
            if name == "currentcolor":
                return Keyword("currentcolor")
            rgb = _COLOR_KEYWORDS.get(name)
            return Color(*rgb, 1.0) if rgb is not None else None
        if isinstance(tok, Hash):
            return _parse_hex_color(tok.value)
        return None

    return _parse_color_function(group)


# --------------------------------------------------------------------------
# display / font-size
# --------------------------------------------------------------------------


def _single_token(tokens: list[CssToken]) -> CssToken | None:
    groups = _split_top_level(tokens)
    if len(groups) != 1 or len(groups[0]) != 1:
        return None
    return groups[0][0]


def _parse_display(tokens: list[CssToken]) -> Keyword | None:
    tok = _single_token(tokens)
    if isinstance(tok, Ident) and _ascii_lower(tok.value) in _DISPLAY_KEYWORDS:
        return Keyword(_ascii_lower(tok.value))
    return None


def _parse_font_size(tokens: list[CssToken]) -> object | None:
    tok = _single_token(tokens)
    if tok is None:
        return None
    if isinstance(tok, Ident) and _ascii_lower(tok.value) in _FONT_SIZE_KEYWORDS:
        return Keyword(_ascii_lower(tok.value))
    return _parse_length_percentage(tok, allow_auto=False)


def _parse_width_height(tokens: list[CssToken]) -> object | None:
    tok = _single_token(tokens)
    if tok is None:
        return None
    return _parse_length_percentage(tok, allow_auto=True)


# --------------------------------------------------------------------------
# margin / padding
# --------------------------------------------------------------------------


_SIDES = ("top", "right", "bottom", "left")


def _sides_from_values(values: list[object]) -> dict[str, object]:
    """The one-to-four-value rule, expressed as a `{side: value}` dict: 1 ->
    all sides; 2 -> vertical, horizontal; 3 -> top, horizontal, bottom;
    4 -> top, right, bottom, left. Always returns all four keys -- unlike
    border's components, a margin/padding shorthand can never leave a side
    unset.
    """
    n = len(values)
    if n == 1:
        top = right = bottom = left = values[0]
    elif n == 2:
        top = bottom = values[0]
        right = left = values[1]
    elif n == 3:
        top, right, bottom = values
        left = right
    elif n == 4:
        top, right, bottom, left = values
    else:
        raise ValueError(f"need 1-4 values, got {n}")
    return {"top": top, "right": right, "bottom": bottom, "left": left}


def _four_sided(tokens: list[CssToken], parse_component) -> dict[str, object] | None:
    """The one-to-four-value rule over any component parser.

    `margin`, `padding`, `border-width`, `border-style` and `border-color`
    are the same shorthand shape with five different component grammars, so
    the rule lives here once. `parse_component` takes a *component* -- a
    list of tokens, since a `<color>` component can be `rgb(0, 0, 0)` and is
    not one token -- and returns its value or None.
    """
    groups = _split_top_level(tokens)
    if not (1 <= len(groups) <= 4):
        return None
    values: list[object] = []
    for group in groups:
        value = parse_component(group)
        if value is None:
            return None
        values.append(value)
    return _sides_from_values(values)


def _one_token(parse_token):
    """Adapt a single-token parser to `_four_sided`'s component signature."""

    def parse_component(group: list[CssToken]) -> object | None:
        return parse_token(group[0]) if len(group) == 1 else None

    return parse_component


def _parse_border_style_component(group: list[CssToken]) -> Keyword | None:
    if len(group) != 1 or not isinstance(group[0], Ident):
        return None
    keyword = _ascii_lower(group[0].value)
    return Keyword(keyword) if keyword in _BORDER_STYLE_KEYWORDS else None


def _parse_margin_or_padding(
    tokens: list[CssToken], *, allow_auto: bool
) -> dict[str, object] | None:
    """Returns a `{"top"/"right"/"bottom"/"left": value}` dict -- the same
    `dict[str, object]` shape `_parse_border` returns, so both shorthands
    hand `expand_shorthand` the same kind of thing. See `expand_shorthand`'s
    docstring for why that uniformity was made a deliberate decision here.
    """
    return _four_sided(
        tokens,
        _one_token(lambda tok: _parse_length_percentage(tok, allow_auto=allow_auto)),
    )


# --------------------------------------------------------------------------
# border
# --------------------------------------------------------------------------


def _parse_border(tokens: list[CssToken]) -> dict[str, object] | None:
    """Width, style and color, in any order, at most one of each kind."""
    groups = _split_top_level(tokens)
    if not groups:
        return None

    width = style = color = None
    for group in groups:
        if len(group) == 1 and isinstance(group[0], Ident):
            keyword = _ascii_lower(group[0].value)
            if keyword in _BORDER_STYLE_KEYWORDS:
                if style is not None:
                    return None
                style = Keyword(keyword)
                continue

        if len(group) == 1:
            length = _parse_length(group[0])
            if length is not None:
                if width is not None:
                    return None
                width = length
                continue

        parsed_color = _parse_color(group)
        if parsed_color is not None:
            if color is not None:
                return None
            color = parsed_color
            continue

        return None  # a component that is none of the three kinds

    if width is None and style is None and color is None:
        return None
    return {"width": width, "style": style, "color": color}


def _expand_border(parsed: dict[str, object], sides: tuple[str, ...]) -> dict[str, object]:
    """`border`'s three components fanned out over `sides`.

    `sides` is all four for the `border` shorthand and exactly one for
    `border-top`/`-right`/`-bottom`/`-left`. Missing components stay missing
    -- deviation 7 -- and the cascade fills them from the initial-value
    table for *that side only*.
    """
    result: dict[str, object] = {}
    for kind in ("width", "style", "color"):
        value = parsed.get(kind)
        if value is None:
            continue
        for side in sides:
            result[f"border-{side}-{kind}"] = value
    return result


# --------------------------------------------------------------------------
# Public API
# --------------------------------------------------------------------------

_SHORTHANDS = frozenset({"margin", "padding", "border"})


def expand_shorthand(name: str, parsed: dict[str, object]) -> dict[str, object]:
    """Expand a shorthand's already-*parsed* components into longhand keys.

    `parsed` is always a `dict[str, object]` -- one uniform shape across
    every shorthand this module knows about, deliberately, rather than a
    positional `list` for margin/padding and a `dict` for border (an
    earlier version of this module had exactly that split, and it left no
    obvious home for a third shorthand). For `"margin"`/`"padding"`,
    `parsed` has all four of `"top"/"right"/"bottom"/"left"` -- a
    margin/padding shorthand can never leave a side unset, since the
    one-to-four-value rule always produces a value for every side. For
    `"border"`, `parsed` has any subset of `"width"/"style"/"color"` --
    border's components genuinely can be partially specified
    (`border: solid` sets only style).

    The two shorthands still fan out differently *within* that uniform
    input shape, and that difference is real, not accidental: a
    margin/padding key maps to exactly one longhand
    (`"top"` -> `margin-top`), while a border key maps to four
    (`"width"` -> `border-{top,right,bottom,left}-width`), because that is
    what the CSS properties themselves do -- one border-width applies
    uniformly to all sides, while margin's four values are independently
    four different longhands. Unifying the *dict-shaped* input was the
    fix; unifying the fan-out itself would paper over an actual difference
    in what the shorthands mean.
    """
    if name in ("margin", "padding"):
        return {f"{name}-{side}": parsed[side] for side in _SIDES}
    if name in ("border-width", "border-style", "border-color"):
        kind = name.split("-", 1)[1]
        return {f"border-{side}-{kind}": parsed[side] for side in _SIDES}
    if name == "border":
        return _expand_border(parsed, _SIDES)
    if name in _BORDER_SIDE_SHORTHANDS:
        return _expand_border(parsed, (name.split("-", 1)[1],))
    raise ValueError(f"{name!r} is not a shorthand this module expands")


# --------------------------------------------------------------------------
# Text and box-sizing properties (Phase 3 Task A2, deliverable 3)
# --------------------------------------------------------------------------

# Public, unlike its neighbours: `layout.text` asserts its own behaviour
# table against this set at import, so a seventh value added here and
# forgotten there fails loudly instead of collapsing text an author asked
# to preserve. The name is the link, so it cannot be private.
WHITE_SPACE_KEYWORDS = frozenset({
    "normal", "pre", "nowrap", "pre-wrap", "pre-line", "break-spaces",
})

_FONT_STYLE_KEYWORDS = frozenset({"normal", "italic", "oblique"})

_TEXT_ALIGN_KEYWORDS = frozenset({
    "start", "end", "left", "right", "center", "justify",
    "justify-all", "match-parent",
})

# Public for the same reason `WHITE_SPACE_KEYWORDS` is: `layout.linebox`
# asserts its own alignment rule table against this set at import time, so a
# ninth keyword added here and forgotten there fails the moment the module
# loads rather than on the first page that uses it.
VERTICAL_ALIGN_KEYWORDS = frozenset({
    "baseline", "sub", "super", "text-top", "text-bottom",
    "middle", "top", "bottom",
})
_VERTICAL_ALIGN_KEYWORDS = VERTICAL_ALIGN_KEYWORDS

_BOX_SIZING_KEYWORDS = frozenset({"content-box", "border-box"})

# Phase 3 Task C. These four are *not* implemented as layout behaviour --
# no float is placed, no positioned box is offset, no overflow is clipped or
# scrolled. They are parsed because block layout cannot be correct without
# reading them: CSS 2.1 section 8.3.1's margin-collapsing barriers are stated
# in terms of `overflow`, `float` and `position`, so an engine that cannot
# see the property collapses margins a browser keeps apart, and the page
# comes out plausibly and quietly too tight. Every one of them is counted
# where layout declines to act on it.
#
# `overflow` is treated as a single keyword rather than as the `overflow-x`
# / `overflow-y` shorthand CSS Overflow 3 makes it. Two-value `overflow` is
# rejected, and the rejection is a measured cost rather than a guessed one:
# of the 53 textual `overflow` declarations in the corpus's three pages'
# stylesheets and inline `<style>` blocks, 46 are `hidden`, 4 `auto`, 1
# `visible` and 2 are the two-value form `hidden auto` (executed with a
# word-boundary grep -- a naive one also matches `text-overflow`). Those 2
# are dropped as `unsupported-value`; both axes are non-`visible` there, so
# the barrier they would have raised is lost. Counted, not silent.
_OVERFLOW_KEYWORDS = frozenset({"visible", "hidden", "scroll", "auto", "clip"})

_FLOAT_KEYWORDS = frozenset({"none", "left", "right", "inline-start", "inline-end"})

_CLEAR_KEYWORDS = frozenset({
    "none", "left", "right", "both", "inline-start", "inline-end",
})

_POSITION_KEYWORDS = frozenset({
    "static", "relative", "absolute", "fixed", "sticky",
})

# Phase 3 Task E, CSS 2.1 chapter 17. Four properties, and only one of them
# is a feature this engine implements as behaviour:
#
# * `table-layout` selects section 17.5.2.1's fixed algorithm over
#   17.5.2.2's automatic one, and is implemented.
# * `border-spacing` appears in both algorithms' arithmetic -- the used
#   width of a table is the columns *plus* `(columns + 1)` spacings -- so a
#   table engine that cannot see it computes a width that is wrong by a
#   multiple of it. Implemented.
# * `caption-side` decides whether the caption box precedes or follows the
#   table box in the table wrapper box (section 17.4). Implemented.
# * `border-collapse` is **not** implemented: only the separated model is.
#   It is parsed so that "we used the separated model here and the author
#   asked for the collapsing one" is a number rather than an absence. Same
#   argument Task C made for `overflow`, `float`, `clear` and `position`,
#   and the corpus makes it concrete: 13 textual `border-collapse:collapse`
#   declarations across the three pages' stylesheets, against 0 textual
#   `table-layout` declarations of any value (executed with a grep over
#   `data/corpus`).
_TABLE_LAYOUT_KEYWORDS = frozenset({"auto", "fixed"})
_BORDER_COLLAPSE_KEYWORDS = frozenset({"separate", "collapse"})
_CAPTION_SIDE_KEYWORDS = frozenset({"top", "bottom"})

# Phase 3 Task F, CSS Flexible Box Layout 1 and CSS Box Alignment 3.
#
# **Twelve longhands and three shorthands, not eleven properties.** The task
# brief lists `gap` beside the eleven flex longhands; Box Alignment 3 makes
# it the shorthand for `row-gap` and `column-gap`, and this corpus writes
# the longhand directly -- `column-gap` appears 5 times against `gap`'s 5
# (executed over the three pages' sheets and `<style>` blocks, at-rules
# descended into). Modelling `gap` as a single property the way
# `border-spacing` is modelled would mean dropping those five, so the pair
# are the longhands and `gap` expands to them.
#
# The alignment keyword sets are Box Alignment 3's, not Flexbox 1's
# original ones, because that is what a browser computes today: `justify-
# content`'s and `align-items`' initial value is `normal`, not `flex-start`
# and `stretch`. `normal` behaves as those two *in a flex container*, which
# is a used-value fact and belongs in `layout.flex`, not here. The
# positional keywords Box Alignment adds (`start`, `end`, `left`, `right`,
# `self-start`, `self-end`) are accepted because the corpus writes one of
# them -- `justify-content: end` once -- and dropping it would be dropping
# real CSS this engine can act on.
_FLEX_DIRECTION_KEYWORDS = frozenset({
    "row", "row-reverse", "column", "column-reverse",
})
_FLEX_WRAP_KEYWORDS = frozenset({"nowrap", "wrap", "wrap-reverse"})
_JUSTIFY_CONTENT_KEYWORDS = frozenset({
    "normal", "flex-start", "flex-end", "center",
    "space-between", "space-around", "space-evenly",
    "start", "end", "left", "right", "stretch",
})
_ALIGN_ITEMS_KEYWORDS = frozenset({
    "normal", "stretch", "center", "flex-start", "flex-end",
    "start", "end", "self-start", "self-end", "baseline",
})
_ALIGN_SELF_KEYWORDS = _ALIGN_ITEMS_KEYWORDS | frozenset({"auto"})
_ALIGN_CONTENT_KEYWORDS = frozenset({
    "normal", "flex-start", "flex-end", "center",
    "space-between", "space-around", "space-evenly", "stretch",
    "start", "end", "baseline",
})

# The two-word and prefixed alignment forms -- `first baseline`, `last
# baseline`, `safe center`, `unsafe end`. Valid CSS this module declines, so
# they must classify as `unsupported-value` rather than `invalid`; see
# `_KNOWN_UNSUPPORTED_KEYWORDS`, which is where the separation is drawn.
_ALIGNMENT_MODIFIERS = frozenset({"first", "last", "safe", "unsafe"})

# CSS Counter Styles 3's predefined counter styles, plus `none`. A closed
# list, for the reason the colour table is closed: `list-style-type` also
# accepts a `<custom-ident>` naming an `@counter-style` rule, and this engine
# parses no `@counter-style` rules, so an identifier outside this list names
# something real that we cannot render. That is `unsupported-value`, not
# `invalid` -- see `_OPEN_IDENT_PROPERTIES`. Wikipedia alone uses six such
# names (`meetei`, `santali`, `myanmar_with_period` among them).
_LIST_STYLE_TYPE_KEYWORDS = frozenset({
    "none",
    "disc", "circle", "square",
    "decimal", "decimal-leading-zero",
    "lower-roman", "upper-roman",
    "lower-greek", "lower-alpha", "lower-latin", "upper-alpha", "upper-latin",
    "arabic-indic", "armenian", "bengali", "cambodian",
    "cjk-decimal", "cjk-earthly-branch", "cjk-heavenly-stem",
    "devanagari", "ethiopic-numeric", "georgian", "gujarati", "gurmukhi",
    "hebrew", "hiragana", "hiragana-iroha",
    "japanese-formal", "japanese-informal",
    "kannada", "katakana", "katakana-iroha", "khmer",
    "korean-hangul-formal", "korean-hanja-formal", "korean-hanja-informal",
    "lao", "lower-armenian", "malayalam", "mongolian", "myanmar", "oriya",
    "persian", "simp-chinese-formal", "simp-chinese-informal",
    "tamil", "telugu", "thai", "tibetan",
    "trad-chinese-formal", "trad-chinese-informal", "upper-armenian",
    "disclosure-open", "disclosure-closed",
})

# `normal` and `bold` are the two keyword weights CSS Fonts 4 keeps; their
# computed values are the numbers, so they are resolved here rather than
# reaching the cascade as keywords. `bolder`/`lighter` are deliberately not
# implemented -- their computed value depends on the *parent's* weight
# through a lookup table, which is a cascade-time fact this module does not
# have, and neither appears anywhere in the corpus (executed).
_FONT_WEIGHT_KEYWORDS = {"normal": 400, "bold": 700}


def _keyword_parser(keywords: frozenset[str]):
    """A property whose whole grammar is one identifier from a closed set."""

    def parse(tokens: list[CssToken]) -> Keyword | None:
        tok = _single_token(tokens)
        if isinstance(tok, Ident) and _ascii_lower(tok.value) in keywords:
            return Keyword(_ascii_lower(tok.value))
        return None

    return parse


def _parse_line_height(tokens: list[CssToken]) -> object | None:
    """`normal | <number> | <length> | <percentage>`.

    `normal` stays a `Keyword`, not a number. Its used value is the font's
    own preferred line spacing, which needs font metrics that do not exist
    until Task D; resolving it to `1.2 x font-size` here would be exactly
    the computed-vs-used mistake `Percent` and `AUTO` exist to avoid, and
    the wrong number would look entirely reasonable.

    A `<number>` is kept as a number, not multiplied by anything: CSS 2.1
    10.8.1 says the computed value of a numeric line-height *is* the number,
    and the number is what inherits -- the multiplication is per element at
    used-value time.

    A `<percentage>` reaches the cascade as a `Percent` and is resolved
    there, unlike every other percentage in this engine. See
    `cascade._PERCENT_OF_OWN_FONT_SIZE` for why the two are opposite: a
    percentage width refers to the containing block, which does not exist
    yet; a percentage line-height refers to the element's own font-size,
    which does.
    """
    tok = _single_token(tokens)
    if tok is None:
        return None
    if isinstance(tok, Ident) and _ascii_lower(tok.value) == "normal":
        return Keyword("normal")
    if isinstance(tok, Number):
        # A negative line-height is invalid CSS.
        return None if tok.value < 0 else float(tok.value)
    return _parse_length_percentage(tok, allow_auto=False)


def _parse_font_weight(tokens: list[CssToken]) -> int | None:
    tok = _single_token(tokens)
    if isinstance(tok, Ident):
        return _FONT_WEIGHT_KEYWORDS.get(_ascii_lower(tok.value))
    if isinstance(tok, Number):
        value = float(tok.value)
        # CSS Fonts 4 widened the range from 100-900 to 1-1000 and made it
        # continuous; anything outside it is invalid rather than clamped.
        return int(value) if 1 <= value <= 1000 else None
    return None


def _parse_font_family(tokens: list[CssToken]) -> tuple[str, ...] | None:
    """A comma-separated list of family names, kept as parsed.

    `<family-name>` is either a `<string>` or a run of identifiers
    (`Times New Roman` unquoted is three tokens and one family). Generic
    families (`serif`, `monospace`) are ordinary entries: nothing consumes
    the list this phase, so distinguishing them would be a decision with no
    consumer to be right for. Recording the list at all is what makes the
    eventual fallback chain implementable rather than a re-parse.
    """
    if not _trim(tokens):
        return None
    families: list[str] = []
    for arg in _split_args(tokens):
        arg = _trim(arg)
        if not arg:
            return None
        if len(arg) == 1 and isinstance(arg[0], String):
            families.append(arg[0].value)
            continue
        words = [tok.value for tok in arg if isinstance(tok, Ident)]
        if len(words) != len([t for t in arg if not isinstance(t, Whitespace)]):
            return None
        families.append(" ".join(words))
    return tuple(families)


def _parse_border_spacing(tokens: list[CssToken]) -> tuple | None:
    """`<length> <length>?` -- horizontal then vertical, per CSS 2.1 17.6.1.

    Returns a **two-tuple even when one value was written**, so no consumer
    ever has to ask which shape it got. A single value applies to both axes;
    that expansion happens here rather than in layout, because "one value
    means both" is a grammar fact and layout should not have to know it.

    Percentages are not allowed on `border-spacing` (the property's value
    grammar is `<length> <length>?` and nothing else), so a percentage is
    rejected here rather than reaching the cascade and resolving against
    something arbitrary.
    """
    groups = _split_top_level(tokens)
    if not (1 <= len(groups) <= 2):
        return None
    lengths: list[Length] = []
    for group in groups:
        if len(group) != 1:
            return None
        length = _parse_length(group[0])
        if length is None or length.value < 0:
            # A negative `border-spacing` is invalid, not merely unusual.
            return None
        lengths.append(length)
    return (lengths[0], lengths[-1])


# --------------------------------------------------------------------------
# Flexbox (Phase 3 Task F)
# --------------------------------------------------------------------------


def _parse_flex_factor(group: list[CssToken]) -> float | None:
    """`<number [0,inf]>` -- a `flex-grow` or `flex-shrink` factor.

    Negative is invalid rather than clamped, per Flexbox 1 section 7.2:
    "Negative numbers are invalid."
    """
    if len(group) != 1 or not isinstance(group[0], Number):
        return None
    value = float(group[0].value)
    return None if value < 0 else value


def _parse_order(tokens: list[CssToken]) -> int | None:
    """`<integer>`, and negative is legal -- `order: -1` is the idiom for
    "first". A fractional number is invalid; `1.0` is not an `<integer>`
    token in CSS even though it is an integral value."""
    tok = _single_token(tokens)
    if not isinstance(tok, Number):
        return None
    value = float(tok.value)
    return int(value) if value == int(value) else None


def _parse_flex_basis_component(group: list[CssToken]) -> object | None:
    """`content | <length-percentage [0,inf]> | auto`.

    `auto` becomes the same `AUTO` sentinel `width` uses, because it means
    the same thing here -- defer to the box's own main size property -- and
    a second spelling of `auto` would be a second thing for layout to
    check. `content` stays a `Keyword`: it is the "size me from my
    contents" value, which is a *different* deferral, and collapsing the
    two would lose the distinction Flexbox 1 section 7.2.3 draws.
    """
    if len(group) != 1:
        return None
    tok = group[0]
    if isinstance(tok, Ident):
        keyword = _ascii_lower(tok.value)
        if keyword == "auto":
            return AUTO
        if keyword == "content":
            return Keyword("content")
        return None
    value = _parse_length_percentage(tok, allow_auto=False)
    if value is None:
        return None
    return None if value.value < 0 else value


def _parse_flex_basis(tokens: list[CssToken]) -> object | None:
    groups = _split_top_level(tokens)
    if len(groups) != 1:
        return None
    return _parse_flex_basis_component(groups[0])


def _parse_gap_component(group: list[CssToken]) -> object | None:
    """`normal | <length-percentage [0,inf]>`.

    `normal` is kept as a `Keyword` rather than resolved to zero here, for
    the reason `line-height: normal` is: its used value is a fact about the
    formatting context (zero in a flex container, the font's own spacing
    for a multi-column one), and this module does not know which context the
    box will be in.
    """
    if len(group) != 1:
        return None
    tok = group[0]
    if isinstance(tok, Ident):
        return Keyword("normal") if _ascii_lower(tok.value) == "normal" else None
    value = _parse_length_percentage(tok, allow_auto=False)
    if value is None:
        return None
    return None if value.value < 0 else value


def _parse_gap(tokens: list[CssToken]) -> dict[str, object] | None:
    """`<'row-gap'> <'column-gap'>?` -- **row first**, then column.

    The order is the one thing worth stating: `gap: 10px 20px` puts 10px
    between rows and 20px between columns, which is the opposite of
    `border-spacing: 10px 20px`'s horizontal-then-vertical. Both are two
    lengths on a two-axis property and they read identically at a call
    site; getting this backwards moves every item in a wrapping flex
    container by the difference and nothing else disagrees.
    """
    groups = _split_top_level(tokens)
    if not (1 <= len(groups) <= 2):
        return None
    values = [_parse_gap_component(group) for group in groups]
    if any(value is None for value in values):
        return None
    return {"row-gap": values[0], "column-gap": values[-1]}


def _parse_flex_flow(tokens: list[CssToken]) -> dict[str, object] | None:
    """`<'flex-direction'> || <'flex-wrap'>` -- either, both, in any order.

    The omitted one goes to its initial value, which `_reset_omitted_
    longhands` in the cascade would also do. It is filled in *here* anyway,
    so that this parser's result and `flex`'s have the same shape: `flex`
    cannot rely on that reset (see `_parse_flex`), and one shorthand that
    does and one that does not is exactly the asymmetry that gets edited
    into a bug later.
    """
    groups = _split_top_level(tokens)
    if not (1 <= len(groups) <= 2):
        return None
    direction = wrap = None
    for group in groups:
        if len(group) != 1 or not isinstance(group[0], Ident):
            return None
        keyword = _ascii_lower(group[0].value)
        if keyword in _FLEX_DIRECTION_KEYWORDS and direction is None:
            direction = Keyword(keyword)
        elif keyword in _FLEX_WRAP_KEYWORDS and wrap is None:
            wrap = Keyword(keyword)
        else:
            return None
    return {
        "flex-direction": direction if direction is not None else Keyword("row"),
        "flex-wrap": wrap if wrap is not None else Keyword("nowrap"),
    }


def _parse_flex(tokens: list[CssToken]) -> dict[str, object] | None:
    """`none | [ <'flex-grow'> <'flex-shrink'>? || <'flex-basis'> ]`.

    **The defaults inside this shorthand are not the properties' initial
    values, and that is the whole difficulty.** Flexbox 1 section 7.1.1:

        flex: 1        ->  1 1 0%     NOT 1 1 auto
        flex: auto     ->  1 1 auto
        flex: none     ->  0 0 auto
        flex: 30px     ->  1 1 30px
        (initial)      ->  0 1 auto

    An omitted `flex-basis` inside the shorthand is **0%**, while the
    property's own initial value is `auto`. So this parser must return all
    three longhands itself and can never lean on the cascade's
    `_reset_omitted_longhands`, which fills omissions from
    `INITIAL_SPECIFIED` and would hand back `auto` -- an item that sizes
    itself from its content where the author asked for an equal share.
    That is a plausible-looking layout with every item the wrong width, and
    it is the single easiest thing to get wrong in this property.

    The `||` in the grammar means the basis may come before the factors as
    well as after (`flex: 30px 2` is `2 1 30px`), so the two orders are both
    accepted rather than only the common one.
    """
    groups = _split_top_level(tokens)
    if not (1 <= len(groups) <= 3):
        return None
    if len(groups) == 1 and len(groups[0]) == 1:
        tok = groups[0][0]
        if isinstance(tok, Ident) and _ascii_lower(tok.value) == "none":
            return _flex_longhands(0.0, 0.0, AUTO)

    factors: list[float] = []
    basis: object | None = None
    factors_done = False
    for group in groups:
        factor = _parse_flex_factor(group)
        if factor is not None and not factors_done and len(factors) < 2:
            # A unitless zero is both a `<number>` and a `<length>`, and the
            # grammar resolves it as the number: `flex: 0` is `0 1 0%`, not
            # `1 1 0px`. Trying the factor first is what implements that.
            factors.append(factor)
            continue
        if factors:
            factors_done = True
        value = _parse_flex_basis_component(group)
        if value is None or basis is not None:
            return None
        basis = value
    if not factors and basis is None:
        return None
    grow = factors[0] if factors else 1.0
    shrink = factors[1] if len(factors) > 1 else 1.0
    return _flex_longhands(
        grow, shrink, basis if basis is not None else Percent(0)
    )


def _flex_longhands(grow: float, shrink: float, basis: object) -> dict[str, object]:
    return {"flex-grow": grow, "flex-shrink": shrink, "flex-basis": basis}


def _parse_vertical_align(tokens: list[CssToken]) -> object | None:
    tok = _single_token(tokens)
    if tok is None:
        return None
    if isinstance(tok, Ident) and _ascii_lower(tok.value) in _VERTICAL_ALIGN_KEYWORDS:
        return Keyword(_ascii_lower(tok.value))
    return _parse_length_percentage(tok, allow_auto=False)


# --------------------------------------------------------------------------
# The property table
# --------------------------------------------------------------------------
#
# One entry per property this module accepts, each mapping a token list to
# the longhand dict it sets (or None). Deliberately a table rather than the
# `if name == ...` chain this used to be: `SUPPORTED_PROPERTIES` and
# `LONGHANDS_OF` are both *derived* from it below, so a property added here
# cannot be missing from either, and `classify_drop` cannot disagree with
# `parse_declaration_value` about what "supported" means. The chain made
# that agreement a matter of remembering.


def _one(prop: str, parse):
    """A property whose parser yields a single value for a single longhand."""

    def parse_one(tokens: list[CssToken]) -> dict[str, object] | None:
        value = parse(tokens)
        return None if value is None else {prop: value}

    return parse_one


def _sides(name: str, *, allow_auto: bool):
    """A `margin`/`padding` shorthand: the one-to-four-value rule."""

    def parse_sides(tokens: list[CssToken]) -> dict[str, object] | None:
        parsed = _parse_margin_or_padding(tokens, allow_auto=allow_auto)
        return None if parsed is None else expand_shorthand(name, parsed)

    return parse_sides


def _border_shorthand(tokens: list[CssToken]) -> dict[str, object] | None:
    parsed = _parse_border(tokens)
    return None if parsed is None else expand_shorthand("border", parsed)


def _border_side(side: str):
    """`border-top` and friends: `<width> || <style> || <color>`, one side."""

    def parse_side(tokens: list[CssToken]) -> dict[str, object] | None:
        parsed = _parse_border(tokens)
        return None if parsed is None else expand_shorthand(f"border-{side}", parsed)

    return parse_side


def _four(name: str, parse_component):
    """`border-width`/`-style`/`-color`: the one-to-four rule over one kind."""

    def parse_four(tokens: list[CssToken]) -> dict[str, object] | None:
        parsed = _four_sided(tokens, parse_component)
        return None if parsed is None else expand_shorthand(name, parsed)

    return parse_four


_BORDER_SIDE_SHORTHANDS: frozenset[str] = frozenset(f"border-{s}" for s in _SIDES)

_PROPERTY_PARSERS: dict[str, object] = {
    "display": _one("display", _parse_display),
    "width": _one("width", _parse_width_height),
    "height": _one("height", _parse_width_height),
    "font-size": _one("font-size", _parse_font_size),
    "color": _one("color", _parse_color),
    "background-color": _one("background-color", _parse_color),
    "margin": _sides("margin", allow_auto=True),
    "padding": _sides("padding", allow_auto=False),
    "border": _border_shorthand,
    # The box-model longhands. Every one of them reuses the component parser
    # its shorthand already used -- `margin-left` is `margin`'s component
    # grammar with the one-to-four rule removed, not a second implementation
    # of `<length-percentage> | auto`. Deviation 13 recorded their absence as
    # a consequence of the old dispatch chain rather than a decision; 395
    # declarations across the corpus depended on it, so the decision is now
    # made the other way.
    **{
        f"margin-{side}": _one(
            f"margin-{side}",
            lambda tokens: (
                None
                if (tok := _single_token(tokens)) is None
                else _parse_length_percentage(tok, allow_auto=True)
            ),
        )
        for side in _SIDES
    },
    # `padding` does not take `auto`; `margin` does. Deviation 9, and the one
    # asymmetry between the two families.
    **{
        f"padding-{side}": _one(
            f"padding-{side}",
            lambda tokens: (
                None
                if (tok := _single_token(tokens)) is None
                else _parse_length_percentage(tok, allow_auto=False)
            ),
        )
        for side in _SIDES
    },
    **{
        f"border-{side}-width": _one(
            f"border-{side}-width",
            lambda tokens: (
                None
                if (tok := _single_token(tokens)) is None
                else _parse_length(tok)
            ),
        )
        for side in _SIDES
    },
    **{
        f"border-{side}-style": _one(
            f"border-{side}-style",
            lambda tokens: _parse_border_style_component(_split_top_level(tokens)[0])
            if len(_split_top_level(tokens)) == 1
            else None,
        )
        for side in _SIDES
    },
    **{
        f"border-{side}-color": _one(f"border-{side}-color", _parse_color)
        for side in _SIDES
    },
    "border-width": _four("border-width", _one_token(_parse_length)),
    "border-style": _four("border-style", _parse_border_style_component),
    "border-color": _four("border-color", _parse_color),
    **{f"border-{side}": _border_side(side) for side in _SIDES},
    # Deliverable 3: the properties Task D cannot start without. Nothing in
    # Phase 3 consumes `font-family` or `vertical-align` yet; they are
    # parsed and recorded because a `ComputedStyle` with no `white-space`
    # is not something line-box code can be written against, and because
    # retrofitting `box-sizing` after Task C would mean revisiting every
    # width in it.
    "white-space": _one("white-space", _keyword_parser(WHITE_SPACE_KEYWORDS)),
    "font-style": _one("font-style", _keyword_parser(_FONT_STYLE_KEYWORDS)),
    "text-align": _one("text-align", _keyword_parser(_TEXT_ALIGN_KEYWORDS)),
    "box-sizing": _one("box-sizing", _keyword_parser(_BOX_SIZING_KEYWORDS)),
    "list-style-type": _one(
        "list-style-type", _keyword_parser(_LIST_STYLE_TYPE_KEYWORDS)
    ),
    "line-height": _one("line-height", _parse_line_height),
    "font-weight": _one("font-weight", _parse_font_weight),
    "font-family": _one("font-family", _parse_font_family),
    "vertical-align": _one("vertical-align", _parse_vertical_align),
    # Phase 3 Task C: read by block layout only to decide whether a margin
    # may collapse and whether a box is in flow. See the keyword sets above.
    "overflow": _one("overflow", _keyword_parser(_OVERFLOW_KEYWORDS)),
    "float": _one("float", _keyword_parser(_FLOAT_KEYWORDS)),
    "clear": _one("clear", _keyword_parser(_CLEAR_KEYWORDS)),
    "position": _one("position", _keyword_parser(_POSITION_KEYWORDS)),
    # Phase 3 Task E: CSS 2.1 chapter 17. See the keyword sets above for
    # which of the four are implemented as behaviour and which are parsed so
    # that the divergence can be counted.
    "table-layout": _one("table-layout", _keyword_parser(_TABLE_LAYOUT_KEYWORDS)),
    "border-collapse": _one(
        "border-collapse", _keyword_parser(_BORDER_COLLAPSE_KEYWORDS)
    ),
    "border-spacing": _one("border-spacing", _parse_border_spacing),
    "caption-side": _one("caption-side", _keyword_parser(_CAPTION_SIDE_KEYWORDS)),
    # Phase 3 Task F: CSS Flexible Box Layout 1 and CSS Box Alignment 3.
    # Twelve longhands and three shorthands. `flex` is the one that cannot
    # use the cascade's omitted-longhand reset -- see `_parse_flex`.
    "flex-direction": _one(
        "flex-direction", _keyword_parser(_FLEX_DIRECTION_KEYWORDS)
    ),
    "flex-wrap": _one("flex-wrap", _keyword_parser(_FLEX_WRAP_KEYWORDS)),
    "justify-content": _one(
        "justify-content", _keyword_parser(_JUSTIFY_CONTENT_KEYWORDS)
    ),
    "align-items": _one("align-items", _keyword_parser(_ALIGN_ITEMS_KEYWORDS)),
    "align-self": _one("align-self", _keyword_parser(_ALIGN_SELF_KEYWORDS)),
    "align-content": _one(
        "align-content", _keyword_parser(_ALIGN_CONTENT_KEYWORDS)
    ),
    "flex-grow": _one(
        "flex-grow",
        lambda tokens: (
            None
            if len(groups := _split_top_level(tokens)) != 1
            else _parse_flex_factor(groups[0])
        ),
    ),
    "flex-shrink": _one(
        "flex-shrink",
        lambda tokens: (
            None
            if len(groups := _split_top_level(tokens)) != 1
            else _parse_flex_factor(groups[0])
        ),
    ),
    "flex-basis": _one("flex-basis", _parse_flex_basis),
    "order": _one("order", _parse_order),
    "row-gap": _one(
        "row-gap",
        lambda tokens: (
            None
            if len(groups := _split_top_level(tokens)) != 1
            else _parse_gap_component(groups[0])
        ),
    ),
    "column-gap": _one(
        "column-gap",
        lambda tokens: (
            None
            if len(groups := _split_top_level(tokens)) != 1
            else _parse_gap_component(groups[0])
        ),
    ),
    "flex": _parse_flex,
    "flex-flow": _parse_flex_flow,
    "gap": _parse_gap,
}

# Which longhands each supported property sets -- *all* of them, including
# the ones a given declaration happens not to mention. A longhand maps to
# itself. This is what the cascade's shorthand-reset needs, and it lives
# here rather than there so it is derived from the same table the parser
# dispatches on. (`values.py` still does not know what the *initial values*
# are; that stays the cascade's, which is the half of the split
# `expand_shorthand`'s deviation 7 describes.)
LONGHANDS_OF: dict[str, tuple[str, ...]] = {
    "display": ("display",),
    "width": ("width",),
    "height": ("height",),
    "font-size": ("font-size",),
    "color": ("color",),
    "background-color": ("background-color",),
    "margin": tuple(f"margin-{side}" for side in _SIDES),
    "padding": tuple(f"padding-{side}" for side in _SIDES),
    "border": tuple(
        f"border-{side}-{kind}"
        for kind in ("width", "style", "color")
        for side in _SIDES
    ),
    # A longhand governs itself.
    **{f"margin-{side}": (f"margin-{side}",) for side in _SIDES},
    **{f"padding-{side}": (f"padding-{side}",) for side in _SIDES},
    **{
        f"border-{side}-{kind}": (f"border-{side}-{kind}",)
        for side in _SIDES
        for kind in ("width", "style", "color")
    },
    # The four-value shorthands: one kind, every side.
    **{
        f"border-{kind}": tuple(f"border-{side}-{kind}" for side in _SIDES)
        for kind in ("width", "style", "color")
    },
    # `border-left` governs three longhands and **only its own side's**. The
    # cascade's shorthand reset reads this table, and giving `border-left`
    # all twelve here would make `p { border: 5px solid red }
    # p { border-left: solid blue }` reset the *top* border's width too --
    # the same family of bug as the one `_reset_omitted_longhands` was
    # written to fix, arriving through the table instead of through the
    # lookup.
    **{
        f"border-{side}": tuple(
            f"border-{side}-{kind}" for kind in ("width", "style", "color")
        )
        for side in _SIDES
    },
    **{
        prop: (prop,)
        for prop in (
            "white-space", "line-height", "font-family", "font-weight",
            "font-style", "text-align", "vertical-align", "box-sizing",
            "list-style-type",
            # Task C's four. `overflow` is a shorthand in CSS Overflow 3 and
            # a longhand here; see the keyword-set comment above for the
            # measured cost of that simplification.
            "overflow", "float", "clear", "position",
            # Task E's four. `border-spacing` is a single longhand whose
            # value is a PAIR, not two longhands: CSS 2.1 defines no
            # `border-spacing-horizontal`, and inventing one would put a
            # property name in `LONGHANDS` that no stylesheet can ever
            # write.
            "table-layout", "border-collapse", "border-spacing",
            "caption-side",
            # Task F's twelve. `row-gap` and `column-gap` are two longhands
            # and not one pair-valued property the way `border-spacing` is,
            # because Box Alignment 3 defines them that way and this corpus
            # writes `column-gap` on its own five times -- a pair-valued
            # `gap` would have to drop those.
            "flex-direction", "flex-wrap", "justify-content",
            "align-items", "align-self", "align-content",
            "flex-grow", "flex-shrink", "flex-basis", "order",
            "row-gap", "column-gap",
        )
    },
    "flex": ("flex-grow", "flex-shrink", "flex-basis"),
    "flex-flow": ("flex-direction", "flex-wrap"),
    "gap": ("row-gap", "column-gap"),
}

# Every property `parse_declaration_value` can accept. Derived, never
# written out twice.
SUPPORTED_PROPERTIES: frozenset[str] = frozenset(_PROPERTY_PARSERS)

assert set(LONGHANDS_OF) == SUPPORTED_PROPERTIES, (
    "LONGHANDS_OF and the parser table disagree: "
    f"{set(LONGHANDS_OF) ^ SUPPORTED_PROPERTIES}"
)


def bare_wide_keyword(tokens: list[CssToken]) -> str | None:
    """The CSS-wide keyword this value consists of, or None.

    All four are recognised, `revert` included, because a caller counting
    what it refused needs to name it. `parse_declaration_value` accepts only
    the three in `_ACCEPTED_WIDE_KEYWORDS`.
    """
    tok = _single_token([t for t in tokens if not isinstance(t, EOFToken)])
    if isinstance(tok, Ident) and _ascii_lower(tok.value) in _WIDE_KEYWORDS:
        return _ascii_lower(tok.value)
    return None


def parse_declaration_value(name: str, tokens: list[CssToken]) -> dict[str, object] | None:
    """Parse one declaration's value tokens for property `name`.

    Returns `None` when the value is invalid for `name` -- the caller (Task
    J's cascade) is expected to drop that one declaration and keep its
    siblings, exactly as an unsupported/malformed declaration behaves in a
    real browser. `classify_drop` says *why*, for the same arguments.
    """
    name = normalize_property_name(name)
    parse = _PROPERTY_PARSERS.get(name)
    if parse is None:
        return None
    # **The wide keywords are intercepted before the per-property parser
    # sees them.** They are valid on every property, so no property's
    # grammar should have to know about them, and none of them can be
    # resolved without the cascade -- `inherit` needs the parent's computed
    # value and `initial` needs the initial-value table. A shorthand's wide
    # keyword sets every longhand it governs, which is why this reads
    # `LONGHANDS_OF` rather than calling `expand_shorthand`: there are no
    # components to expand.
    keyword = bare_wide_keyword(tokens)
    if keyword is not None:
        if keyword not in _ACCEPTED_WIDE_KEYWORDS:
            return None  # `revert`, deliberately
        return {prop: WideKeyword(keyword) for prop in LONGHANDS_OF[name]}
    # EOFToken only ever appears here because a caller (this module's own
    # tests, most obviously) drove a `CssTokenizer` straight through to
    # completion rather than going through `cssparse.parser`, whose
    # `Declaration.value` never contains one. Stripping it up front means
    # both call shapes parse identically.
    return parse([tok for tok in tokens if not isinstance(tok, EOFToken)])


# --------------------------------------------------------------------------
# Why a declaration was dropped
# --------------------------------------------------------------------------
#
# A drop *rate* is ambiguous: it falls when the parser improves and it also
# falls when validation loosens, and those are opposite outcomes. These four
# reasons partition every drop so the two can be told apart. `invalid` is the
# one that must never shrink -- everything in it is something a browser drops
# too, so a smaller `invalid` means this module started accepting garbage.

DROP_UNSUPPORTED_PROPERTY = "unsupported-property"
DROP_UNSUPPORTED_VALUE = "unsupported-value"
DROP_VAR_UNRESOLVED = "var-unresolved"
DROP_INVALID = "invalid"

DROP_REASONS: tuple[str, ...] = (
    DROP_UNSUPPORTED_PROPERTY,
    DROP_UNSUPPORTED_VALUE,
    DROP_VAR_UNRESOLVED,
    DROP_INVALID,
)

# The only functions any supported property's grammar accepts. `var()` is
# excluded on purpose -- it is not a value function, it is a substitution,
# and `classify_drop` reaches it before this set is consulted.
_SUPPORTED_FUNCTIONS = frozenset({"rgb", "rgba"})

# The CSS-wide keywords. All four are valid CSS on every property, so a
# declaration this module rejects because of one is `unsupported-value`,
# never `invalid`. After the cascade learned `inherit`/`initial`/`unset`,
# only `revert` still reaches here in the bare single-keyword form -- it
# needs origin-level rollback the cascade does not model.
_WIDE_KEYWORDS = frozenset({"inherit", "initial", "unset", "revert"})

# Valid CSS keywords this module deliberately does not implement, per
# property. Membership here is what separates `unsupported-value` from
# `invalid`: `display: flow-root` is real CSS we do not do, while
# `display: bloc<U+212A>` is not real CSS at all and a browser drops it too.
_KNOWN_UNSUPPORTED_KEYWORDS: dict[str, frozenset[str]] = {
    # Real `display` values outside `_DISPLAY_KEYWORDS`.
    "display": frozenset({
        "flow", "flow-root", "run-in", "math",
        "ruby", "ruby-base", "ruby-text",
        "ruby-base-container", "ruby-text-container",
    }),
    # The intrinsic sizing keywords (CSS Sizing 3), which need a layout pass
    # to mean anything.
    "width": frozenset({
        "min-content", "max-content", "fit-content", "stretch", "content",
    }),
    "height": frozenset({
        "min-content", "max-content", "fit-content", "stretch", "content",
    }),
    # Deviation 8: border widths take only `<length>` here, not the spec's
    # `thin | medium | thick` trio -- on every property that can carry one.
    **{
        prop: frozenset({"thin", "medium", "thick"})
        for prop in (
            ("border", "border-width")
            + tuple(f"border-{side}" for side in _SIDES)
            + tuple(f"border-{side}-width" for side in _SIDES)
        )
    },
    # Box Alignment 3's two-word and prefixed forms -- `first baseline`,
    # `last baseline`, `safe center`, `unsafe flex-end`. Real CSS this
    # module declines, so it is `unsupported-value` and not `invalid`, on
    # the same argument the two-value `overflow` is. Zero occurrences on
    # this corpus (executed over the three pages' sheets); the entry is
    # here so the classification is decided rather than accidental.
    **{
        prop: _ALIGNMENT_MODIFIERS
        for prop in (
            "align-items", "align-self", "align-content", "justify-content",
        )
    },
}

# Properties whose grammar admits an open-ended `<custom-ident>` or
# `<string>`, so an identifier this module does not recognise names
# something real (an `@counter-style` rule, a font on the user's machine)
# rather than being malformed.
_OPEN_IDENT_PROPERTIES: frozenset[str] = frozenset({"list-style-type"})

# Properties this module models as a single keyword that the spec makes a
# two-value shorthand. A two-value `overflow` is valid CSS we decline, not
# malformed CSS, so it must classify as `unsupported-value`. Getting this
# wrong is not cosmetic: `invalid` is the drop bucket the Phase 3 plan says
# must never shrink, and a declaration wrongly counted there makes that
# alarm mean nothing. Executed on the corpus: `overflow: hidden auto` twice
# in Wikipedia's sheets, which is what moved `invalid` from 0 to 2 before
# this existed.
_DECLINED_TWO_VALUE_SHORTHANDS: dict[str, frozenset[str]] = {
    "overflow": _OVERFLOW_KEYWORDS,
}


def _has_unsupported_construct(name: str, tokens: list[CssToken]) -> bool:
    """Does this value use valid CSS that this module documents as out of
    scope? See `_KNOWN_UNSUPPORTED_KEYWORDS` for the separation this draws.
    """
    allowed_pair = _DECLINED_TWO_VALUE_SHORTHANDS.get(name)
    if allowed_pair is not None:
        idents = [tok for tok in tokens if isinstance(tok, Ident)]
        if len(idents) > 1 and all(
            _ascii_lower(tok.value) in allowed_pair for tok in idents
        ):
            return True

    known = _KNOWN_UNSUPPORTED_KEYWORDS.get(name, frozenset())
    for tok in tokens:
        if isinstance(tok, Function):
            fn = _ascii_lower(tok.value)
            # `var` is the caller's business, checked before this function
            # runs; a malformed one belongs in `invalid`.
            if fn != "var" and fn not in _SUPPORTED_FUNCTIONS:
                return True
        elif isinstance(tok, Ident):
            keyword = _ascii_lower(tok.value)
            if keyword in _WIDE_KEYWORDS or keyword in known:
                return True
            if name in _OPEN_IDENT_PROPERTIES:
                return True
    return False


# --------------------------------------------------------------------------
# Custom properties and var() substitution
# --------------------------------------------------------------------------
#
# The trap this shape exists to avoid: declarations are parsed **once per
# sheet** and the resulting objects are shared by every element the rule
# matches, but `color: var(--accent)` computes to a different value per
# element, because `--accent` is itself cascaded and inherited. Substituting
# at sheet-parse time is wrong and would produce entirely plausible output
# on a test page with one element. So this module supplies only the textual
# substitution; *when* to run it is the cascade's decision, and the cascade
# runs it per element after that element's custom properties are known.

# Depth cap rather than real cycle detection, deliberately. Custom Properties
# 1 section 3 defines cycle detection over the whole dependency graph, which
# is a phase and not a task. A cap is O(1) and cannot be wrong in the
# dangerous direction: the worst it does is refuse a legal eight-deep chain,
# which is a counted refusal rather than a hang or a wrong value.
VAR_SUBSTITUTION_DEPTH_CAP = 8

# Why a substitution was refused. Each is a counter name in the cascade, so
# every out-of-scope case is a number rather than an absence.
VAR_UNKNOWN_NO_FALLBACK = "var_unknown_no_fallback"
VAR_NESTED_FALLBACK_SKIPPED = "var_nested_fallback_skipped"
VAR_DEPTH_EXCEEDED = "var_depth_exceeded"
VAR_MALFORMED = "var_malformed"


def is_custom_property(name: str) -> bool:
    """Is this declaration a custom property?

    **Not normalised.** Custom property names are case-*sensitive*
    (Custom Properties 1 section 2), unlike every other property name this
    module sees, so `--Accent` and `--accent` are two different properties.
    Running `normalize_property_name` over one would silently merge them.
    """
    return name.startswith("--")


def contains_var_reference(tokens: list[CssToken]) -> bool:
    """Does this value contain a well-formed `var()` reference?

    Well-formed means `var(` followed by an identifier starting with `--`.
    A `var()` with anything else first is a syntax error a browser drops
    too, so it deliberately does not count here: crediting the `var()` work
    with a case `var()` can never recover would make its counter move for
    the wrong reason.
    """
    for i, tok in enumerate(tokens):
        if not isinstance(tok, Function) or _ascii_lower(tok.value) != "var":
            continue
        rest = _trim(tokens[i + 1:])
        if rest and isinstance(rest[0], Ident) and rest[0].value.startswith("--"):
            return True
    return False


def _matching_rparen(tokens: list[CssToken], start: int) -> int | None:
    """Index of the `)` closing the `Function` at `start`, or None."""
    depth = 0
    for i in range(start, len(tokens)):
        tok = tokens[i]
        if isinstance(tok, Function):
            depth += 1
        elif isinstance(tok, RParen):
            depth -= 1
            if depth == 0:
                return i
    return None


def _split_var_arguments(
    inner: list[CssToken],
) -> tuple[list[CssToken], list[CssToken] | None]:
    """`var()`'s inner tokens as (name, fallback-or-None).

    Split at the **first** top-level comma, not on every comma: the fallback
    is an arbitrary declaration value and may contain commas of its own
    (`var(--font, Georgia, serif)` has one fallback, not two).
    """
    depth = 0
    for i, tok in enumerate(inner):
        if isinstance(tok, Function):
            depth += 1
        elif isinstance(tok, RParen):
            depth -= 1
        elif isinstance(tok, Comma) and depth == 0:
            return inner[:i], inner[i + 1:]
    return inner, None


def substitute_var(
    tokens: list[CssToken],
    custom_properties: dict[str, tuple[CssToken, ...]],
    _depth: int = 0,
) -> tuple[list[CssToken] | None, str | None]:
    """Replace every `var()` in `tokens` with what it names.

    Returns `(substituted_tokens, None)` or `(None, reason)`, where `reason`
    is one of the `VAR_*` constants above. Returning the reason rather than
    incrementing a counter keeps this module free of the metrics object; the
    cascade owns counting, as it owns every other counter.

    Substitution is textual at the token level, which is what the spec says
    it is: the `var()` function is replaced by the custom property's token
    list and the result is then parsed as if it had been written that way.
    That is also why an invalid result is a *drop* and not an error --
    `width: var(--x)` with `--x: red` is a declaration a browser discards at
    computed-value time.

    Deliberately out of scope, each with its own reason so it is a number:

    * `var()` inside another `var()`'s fallback, when the fallback is the
      branch actually taken -- `VAR_NESTED_FALLBACK_SKIPPED`. When the
      custom property *is* set the fallback is never looked at, matching the
      spec (a fallback need not even be valid), so `var(--x, var(--y))` with
      `--x` set resolves normally rather than being refused.
    * a chain deeper than `VAR_SUBSTITUTION_DEPTH_CAP` -- `VAR_DEPTH_EXCEEDED`.
    * an unset custom property with no fallback -- `VAR_UNKNOWN_NO_FALLBACK`.
      (Per spec this makes the declaration invalid at computed-value time,
      which is what dropping it amounts to.)
    * the guaranteed-invalid-value rules of Custom Properties 1 section 3,
      in their generality.
    """
    if _depth > VAR_SUBSTITUTION_DEPTH_CAP:
        return None, VAR_DEPTH_EXCEEDED
    out: list[CssToken] = []
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if not (isinstance(tok, Function) and _ascii_lower(tok.value) == "var"):
            out.append(tok)
            i += 1
            continue
        end = _matching_rparen(tokens, i)
        if end is None:
            return None, VAR_MALFORMED
        name_tokens, fallback = _split_var_arguments(tokens[i + 1:end])
        name_tokens = _trim(name_tokens)
        if (
            len(name_tokens) != 1
            or not isinstance(name_tokens[0], Ident)
            or not name_tokens[0].value.startswith("--")
        ):
            return None, VAR_MALFORMED
        declared = custom_properties.get(name_tokens[0].value)
        if declared is not None:
            replacement, reason = substitute_var(
                list(declared), custom_properties, _depth + 1
            )
            if replacement is None:
                return None, reason
        elif fallback is not None:
            if contains_var_reference(fallback):
                return None, VAR_NESTED_FALLBACK_SKIPPED
            replacement = _trim(fallback)
        else:
            return None, VAR_UNKNOWN_NO_FALLBACK
        out.extend(replacement)
        i = end + 1
    return out, None


def classify_drop(name: str, tokens: list[CssToken]) -> str:
    """Why `parse_declaration_value(name, tokens)` returned `None`.

    Call only when it did; the result is meaningless otherwise. The order of
    the four tests is itself a decision:

    * **property before value.** `background: var(--x)` is
      `unsupported-property` whether or not `var()` is substituted, because
      `background` is not a property this module has. Testing `var()` first
      would move that declaration between two buckets when `var()` landed
      and say nothing about either.
    * **`var()` before the value grammar**, because a value containing one
      has no grammar to check until it is substituted.
    * **`invalid` last**, and only for values that survived every "we know
      this and chose not to" test. That is what makes a shrinking `invalid`
      a signal rather than noise.
    """
    name = normalize_property_name(name)
    if name not in SUPPORTED_PROPERTIES:
        return DROP_UNSUPPORTED_PROPERTY
    tokens = [tok for tok in tokens if not isinstance(tok, EOFToken)]
    if contains_var_reference(tokens):
        return DROP_VAR_UNRESOLVED
    if _has_unsupported_construct(name, tokens):
        return DROP_UNSUPPORTED_VALUE
    return DROP_INVALID


__all__ = [
    "AUTO",
    "DROP_INVALID",
    "DROP_REASONS",
    "DROP_UNSUPPORTED_PROPERTY",
    "DROP_UNSUPPORTED_VALUE",
    "DROP_VAR_UNRESOLVED",
    "LONGHANDS_OF",
    "SUPPORTED_PROPERTIES",
    "Color",
    "Keyword",
    "Length",
    "Percent",
    "VAR_DEPTH_EXCEEDED",
    "VAR_MALFORMED",
    "VAR_NESTED_FALLBACK_SKIPPED",
    "VAR_SUBSTITUTION_DEPTH_CAP",
    "VAR_UNKNOWN_NO_FALLBACK",
    "WideKeyword",
    "bare_wide_keyword",
    "contains_var_reference",
    "is_custom_property",
    "substitute_var",
    "classify_drop",
    "expand_shorthand",
    "normalize_property_name",
    "parse_declaration_value",
]
