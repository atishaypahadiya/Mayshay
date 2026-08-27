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

Two entry points, matching the task brief:

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
        can still get the longhand dict. `parsed` is a `list[object]` of 1-4
        values for `margin`/`padding` (the one-to-four-value rule), or a
        `dict` with any subset of `"width"/"style"/"color"` for `border`.

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
4. **The named-color table is not the full ~148-keyword CSS Color Level 4
   list.** It has the 16 original CSS1/HTML keywords (deliberately including
   the `green`/`lime` trap: CSS `green` is `#008000`, not the bright green
   most people picture, which is `lime`) plus a handful of common extras
   (`orange`, `pink`, `brown`, `cyan`, `magenta`, `grey`) and the two special
   keywords `transparent` and `currentcolor`. A name outside this table is
   invalid, even if some browser would resolve it. Extending the table is a
   pure data change (`_COLOR_KEYWORDS`) whenever a corpus case needs it.
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

_DISPLAY_KEYWORDS = frozenset({
    "block", "inline", "inline-block", "none",
    "flex", "inline-flex", "grid", "inline-grid",
    "list-item", "table", "table-row", "table-cell", "contents",
})

_BORDER_STYLE_KEYWORDS = frozenset({
    "none", "hidden", "dotted", "dashed", "solid",
    "double", "groove", "ridge", "inset", "outset",
})

_FONT_SIZE_KEYWORDS = frozenset({
    "xx-small", "x-small", "small", "medium", "large",
    "x-large", "xx-large", "xxx-large", "smaller", "larger",
})

# See deviation 4: the 16 original CSS1/HTML keywords -- correctly, `green`
# is #008000 -- plus a handful of common extras. NOT the full CSS4 table.
_COLOR_KEYWORDS: dict[str, tuple[int, int, int]] = {
    "black": (0, 0, 0), "silver": (192, 192, 192), "gray": (128, 128, 128),
    "white": (255, 255, 255), "maroon": (128, 0, 0), "red": (255, 0, 0),
    "purple": (128, 0, 128), "fuchsia": (255, 0, 255), "green": (0, 128, 0),
    "lime": (0, 255, 0), "olive": (128, 128, 0), "yellow": (255, 255, 0),
    "navy": (0, 0, 128), "blue": (0, 0, 255), "teal": (0, 128, 128),
    "aqua": (0, 255, 255),
    "orange": (255, 165, 0), "pink": (255, 192, 203), "brown": (165, 42, 42),
    "cyan": (0, 255, 255), "magenta": (255, 0, 255), "grey": (128, 128, 128),
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
        unit = tok.unit.lower()
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
    if allow_auto and isinstance(tok, Ident) and tok.value.lower() == "auto":
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
    name = group[0].value.lower()
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
            name = tok.value.lower()
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
    if isinstance(tok, Ident) and tok.value.lower() in _DISPLAY_KEYWORDS:
        return Keyword(tok.value.lower())
    return None


def _parse_font_size(tokens: list[CssToken]) -> object | None:
    tok = _single_token(tokens)
    if tok is None:
        return None
    if isinstance(tok, Ident) and tok.value.lower() in _FONT_SIZE_KEYWORDS:
        return Keyword(tok.value.lower())
    return _parse_length_percentage(tok, allow_auto=False)


def _parse_width_height(tokens: list[CssToken]) -> object | None:
    tok = _single_token(tokens)
    if tok is None:
        return None
    return _parse_length_percentage(tok, allow_auto=True)


# --------------------------------------------------------------------------
# margin / padding
# --------------------------------------------------------------------------


def _parse_margin_or_padding(
    tokens: list[CssToken], *, allow_auto: bool
) -> list[object] | None:
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
    return values


def _expand_sides(prefix: str, values: list[object]) -> dict[str, object]:
    """The one-to-four-value rule: 1 -> all sides; 2 -> vertical, horizontal;
    3 -> top, horizontal, bottom; 4 -> top, right, bottom, left.
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
        raise ValueError(f"{prefix} shorthand needs 1-4 values, got {n}")
    return {
        f"{prefix}-top": top,
        f"{prefix}-right": right,
        f"{prefix}-bottom": bottom,
        f"{prefix}-left": left,
    }


# --------------------------------------------------------------------------
# border
# --------------------------------------------------------------------------

_BORDER_SIDES = ("top", "right", "bottom", "left")


def _parse_border(tokens: list[CssToken]) -> dict[str, object] | None:
    """Width, style and color, in any order, at most one of each kind."""
    groups = _split_top_level(tokens)
    if not groups:
        return None

    width = style = color = None
    for group in groups:
        if len(group) == 1 and isinstance(group[0], Ident):
            keyword = group[0].value.lower()
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
    for kind, key in (("width", "width"), ("style", "style"), ("color", "color")):
        value = parsed.get(kind)
        if value is None:
            continue
        for side in _BORDER_SIDES:
            result[f"border-{side}-{key}"] = value
    return result


# --------------------------------------------------------------------------
# Public API
# --------------------------------------------------------------------------

_SHORTHANDS = frozenset({"margin", "padding", "border"})


def expand_shorthand(name: str, parsed: object) -> dict[str, object]:
    """Expand a shorthand's already-*parsed* components into longhand keys.

    `parsed` for `"margin"`/`"padding"` is a `list[object]` of 1-4 values
    (the one-to-four-value rule). `parsed` for `"border"` is a `dict` with
    any subset of `"width"/"style"/"color"` keys.
    """
    if name == "margin":
        return _expand_sides("margin", parsed)  # type: ignore[arg-type]
    if name == "padding":
        return _expand_sides("padding", parsed)  # type: ignore[arg-type]
    if name == "border":
        return _expand_border(parsed)  # type: ignore[arg-type]
    raise ValueError(f"{name!r} is not a shorthand this module expands")


def parse_declaration_value(name: str, tokens: list[CssToken]) -> dict[str, object] | None:
    """Parse one declaration's value tokens for property `name`.

    Returns `None` when the value is invalid for `name` -- the caller (Task
    J's cascade) is expected to drop that one declaration and keep its
    siblings, exactly as an unsupported/malformed declaration behaves in a
    real browser.
    """
    name = name.lower()
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
        values = _parse_margin_or_padding(tokens, allow_auto=True)
        return None if values is None else expand_shorthand("margin", values)

    if name == "padding":
        values = _parse_margin_or_padding(tokens, allow_auto=False)
        return None if values is None else expand_shorthand("padding", values)

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
    "parse_declaration_value",
]
