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
13. **The nine supported properties include three shorthands
    (`margin`, `padding`, `border`) but none of their longhands.**
    `parse_declaration_value("margin-top", ...)`,
    `("padding-right", ...)`, `("border-top", ...)`,
    `("border-top-width", ...)`, `("border-width"/"-style"/"-color", ...)`
    and `("background", ...)` all return `None`, so the only way to set
    `ComputedStyle.margin_top` is to write the shorthand. This is a
    consequence of the dispatch chain rather than a decision anyone made,
    and it is recorded here because it is the largest slice of the corpus's
    dropped declarations that no other deviation covers: executed over
    `data/corpus/wikipedia.html`, 85 of the 313 dropped declarations are in
    this family (15 `padding-right`, 14 `margin-top`, 12 `background`,
    8 `margin-bottom`, 7 `border-left`, and a long tail). Adding them is
    mechanical -- the component parsers the shorthands already use are the
    same ones a longhand needs -- and is left to a phase that needs them.
    `test_longhands_of_the_supported_shorthands_are_not_supported` pins the
    current boundary so it cannot drift silently.
14. **`display` is a closed keyword allow-list** (20 entries, above --
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


def _parse_margin_or_padding(
    tokens: list[CssToken], *, allow_auto: bool
) -> dict[str, object] | None:
    """Returns a `{"top"/"right"/"bottom"/"left": value}` dict -- the same
    `dict[str, object]` shape `_parse_border` returns, so both shorthands
    hand `expand_shorthand` the same kind of thing. See `expand_shorthand`'s
    docstring for why that uniformity was made a deliberate decision here.
    """
    groups = _split_top_level(tokens)
    if not (1 <= len(groups) <= 4):
        return None
    values: list[object] = []
    for group in groups:
        if len(group) != 1:
            return None
        value = _parse_length_percentage(group[0], allow_auto=allow_auto)
        if value is None:
            return None
        values.append(value)
    return _sides_from_values(values)


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


def _expand_border(parsed: dict[str, object]) -> dict[str, object]:
    result: dict[str, object] = {}
    for kind in ("width", "style", "color"):
        value = parsed.get(kind)
        if value is None:
            continue
        for side in _SIDES:
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
    if name == "border":
        return _expand_border(parsed)
    raise ValueError(f"{name!r} is not a shorthand this module expands")


def parse_declaration_value(name: str, tokens: list[CssToken]) -> dict[str, object] | None:
    """Parse one declaration's value tokens for property `name`.

    Returns `None` when the value is invalid for `name` -- the caller (Task
    J's cascade) is expected to drop that one declaration and keep its
    siblings, exactly as an unsupported/malformed declaration behaves in a
    real browser.
    """
    name = normalize_property_name(name)
    # EOFToken only ever appears here because a caller (this module's own
    # tests, most obviously) drove a `CssTokenizer` straight through to
    # completion rather than going through `cssparse.parser`, whose
    # `Declaration.value` never contains one. Stripping it up front means
    # both call shapes parse identically.
    tokens = [tok for tok in tokens if not isinstance(tok, EOFToken)]

    if name == "display":
        value = _parse_display(tokens)
        return None if value is None else {"display": value}

    if name in ("width", "height"):
        value = _parse_width_height(tokens)
        return None if value is None else {name: value}

    if name == "font-size":
        value = _parse_font_size(tokens)
        return None if value is None else {"font-size": value}

    if name in ("color", "background-color"):
        value = _parse_color(tokens)
        return None if value is None else {name: value}

    if name == "margin":
        sides = _parse_margin_or_padding(tokens, allow_auto=True)
        return None if sides is None else expand_shorthand("margin", sides)

    if name == "padding":
        sides = _parse_margin_or_padding(tokens, allow_auto=False)
        return None if sides is None else expand_shorthand("padding", sides)

    if name == "border":
        parsed = _parse_border(tokens)
        return None if parsed is None else expand_shorthand("border", parsed)

    return None  # not one of the nine properties this module handles


__all__ = [
    "AUTO",
    "Color",
    "Keyword",
    "Length",
    "Percent",
    "expand_shorthand",
    "normalize_property_name",
    "parse_declaration_value",
]
