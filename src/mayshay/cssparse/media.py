"""Media query parsing and evaluation -- Media Queries 4, narrowly.

Phase 3 Task A, and it comes before layout for a measured reason. With
at-rules skipped entirely, 51% of the Hacker News page's CSS and 46% of
Wikipedia's never reached the cascade, and every `display` declaration in
`news.css` sits inside a `@media` block. The display census was therefore
describing the CSS we evaluate, not the CSS the pages ship, and no question
about how much `flex` is really out there could be answered until this
existed.

Scope is deliberately small, and everything outside it is **recorded, not
silently dropped** -- the same discipline as `link_stylesheets_skipped`.

Evaluated:

* media types `all`, `screen`, and the `only` keyword
* `not`, `and`, and comma-separated query lists
* `width` / `min-width` / `max-width`, `height` / `min-height` /
  `max-height`, and `orientation`
* lengths in absolute units, plus `em`/`rem` against the initial 16px --
  which is what the spec says font-relative units in a media query resolve
  against, since there is no element yet

Not evaluated, and counted by name so the gap stays visible:

* `print` and every other media type -- a `@media print` block repainting
  the screen is worse than not evaluating it
* `hover`, `pointer`, `prefers-*`, `device-*`, resolution and anything else
  that needs device state this engine has no source for
* `calc()` and any other function inside a feature value
* MQ4 range syntax (`(400px <= width)`), `or`, and `<general-enclosed>`

Deviation from the spec, on purpose: a query naming a feature we do not
support evaluates to **false even under `not`**. The spec says an unknown
feature is false, so `not (unknown: 1)` is true -- but our "unsupported" is
not the spec's "unknown". `prefers-color-scheme` is a feature real browsers
do support, and inverting our ignorance of it would *apply* CSS the page
meant for a state we cannot observe. False in both directions never
over-applies, and `media_queries_unsupported` counts every time it happens.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from mayshay.cssparse.tokenizer import (
    Colon,
    Comma,
    CssToken,
    Dimension,
    EOFToken,
    Function,
    Ident,
    LParen,
    Number,
    RParen,
    Whitespace,
)

# The viewport this project measures against unless told otherwise. A real
# 1280x1024 desktop, chosen because it is above every `min-width` breakpoint
# in the corpus and below the largest, so it exercises both directions.
DEFAULT_VIEWPORT_WIDTH_PX = 1280.0
DEFAULT_VIEWPORT_HEIGHT_PX = 1024.0

# Font-relative units in a media query resolve against the initial font
# size: there is no element to inherit from.
_INITIAL_FONT_SIZE_PX = 16.0

_ABSOLUTE_PX = {
    "px": 1.0,
    "in": 96.0,
    "pc": 16.0,
    "pt": 96.0 / 72.0,
    "cm": 96.0 / 2.54,
    "mm": 96.0 / 25.4,
    "q": 96.0 / 25.4 / 4.0,
}
_FONT_RELATIVE = {"em": 1.0, "rem": 1.0, "ex": 0.5, "ch": 0.5}

# Media types we are. `all` matches by definition; `screen` is what this
# engine renders for. Everything else -- print, speech, tty -- is a type we
# are not, so its rules must not apply.
_MATCHING_TYPES = {"all", "screen"}

_RANGE_FEATURES = {"width", "height"}
_SUPPORTED_FEATURES = _RANGE_FEATURES | {"orientation"}


@dataclass(frozen=True)
class Viewport:
    """The size media queries resolve against.

    Layout needs this anyway -- percentage widths and `vw`/`vh` resolve
    against exactly these numbers -- so it lands here first rather than
    being invented twice.
    """

    width_px: float = DEFAULT_VIEWPORT_WIDTH_PX
    height_px: float = DEFAULT_VIEWPORT_HEIGHT_PX

    @property
    def orientation(self) -> str:
        # CSS Device Adaptation: square counts as landscape.
        return "portrait" if self.height_px > self.width_px else "landscape"


@dataclass(frozen=True)
class Feature:
    """One `(name: value)` test."""

    name: str  # already stripped of a min-/max- prefix, lowercased
    op: str  # "min", "max", "eq", or "boolean"
    value: object = None  # float px, str keyword, or None for boolean
    supported: bool = True
    raw_name: str = ""  # as written, for the counters


@dataclass
class MediaQuery:
    negated: bool = False
    media_type: str | None = None
    features: tuple[Feature, ...] = ()
    # Set when the query is syntactically broken. Per 5.4.1 a malformed
    # query is equivalent to `not all` -- it never matches, and it does not
    # invalidate its siblings in the comma list.
    malformed: bool = False

    @property
    def unsupported(self) -> tuple[str, ...]:
        return tuple(f.raw_name for f in self.features if not f.supported)


# --------------------------------------------------------------------------
# Parsing
# --------------------------------------------------------------------------


def _significant(tokens: list[CssToken]) -> list[CssToken]:
    """Whitespace and the EOF sentinel dropped.

    EOF matters: `CssTokenizer.tokenize()` ends every stream with an
    `EOFToken`, and a caller that tokenizes a prelude directly (rather than
    taking `AtRule.prelude`, which has none) would otherwise see a trailing
    token no grammar rule accepts and get `malformed` for every query.
    """
    return [t for t in tokens if not isinstance(t, (Whitespace, EOFToken))]


def _split_on_commas(tokens: list[CssToken]) -> list[list[CssToken]]:
    """Top-level comma split. Depth-aware so a comma inside `calc(a, b)` or
    a nested feature does not split a query in half."""
    out: list[list[CssToken]] = [[]]
    depth = 0
    for tok in tokens:
        if isinstance(tok, (LParen, Function)):
            depth += 1
        elif isinstance(tok, RParen):
            depth -= 1
        elif isinstance(tok, Comma) and depth == 0:
            out.append([])
            continue
        out[-1].append(tok)
    return out


def _to_px(tok: CssToken) -> float | None:
    """A length token in px, or None if it is not a length we can resolve."""
    if isinstance(tok, Number) and tok.value == 0:
        return 0.0  # unitless zero is a valid <length>
    if not isinstance(tok, Dimension):
        return None
    unit = tok.unit.lower()
    if unit in _ABSOLUTE_PX:
        return tok.value * _ABSOLUTE_PX[unit]
    if unit in _FONT_RELATIVE:
        return tok.value * _FONT_RELATIVE[unit] * _INITIAL_FONT_SIZE_PX
    return None


def _parse_feature(inner: list[CssToken]) -> Feature:
    """Parse the tokens between a feature's parentheses."""
    inner = _significant(inner)
    if not inner or not isinstance(inner[0], Ident):
        return Feature("", "boolean", None, supported=False, raw_name="<malformed>")

    raw = inner[0].value
    name = raw.lower()
    op = "eq"
    for prefix in ("min-", "max-"):
        if name.startswith(prefix):
            op, name = prefix[:-1], name[len(prefix) :]
            break

    if name not in _SUPPORTED_FEATURES:
        return Feature(name, op, None, supported=False, raw_name=raw)

    rest = inner[1:]
    if not rest:
        # Boolean form: `(width)`. A min-/max- prefix has no boolean form.
        if op != "eq":
            return Feature(name, op, None, supported=False, raw_name=raw)
        return Feature(name, "boolean", None, raw_name=raw)

    if not isinstance(rest[0], Colon) or len(rest) != 2:
        # `(400px <= width)` and `(width: calc(...))` both land here: more
        # or fewer tokens than one colon and one value.
        return Feature(name, op, None, supported=False, raw_name=raw)

    value_tok = rest[1]
    if name == "orientation":
        if isinstance(value_tok, Ident) and value_tok.value.lower() in (
            "portrait",
            "landscape",
        ):
            return Feature(name, op, value_tok.value.lower(), raw_name=raw)
        return Feature(name, op, None, supported=False, raw_name=raw)

    px = _to_px(value_tok)
    if px is None:
        return Feature(name, op, None, supported=False, raw_name=raw)
    return Feature(name, op, px, raw_name=raw)


def _parse_query(tokens: list[CssToken]) -> MediaQuery:
    toks = _significant(tokens)
    if not toks:
        return MediaQuery(malformed=True)

    query = MediaQuery()
    i = 0

    # [ not | only ]? -- but only when a media *type* follows. A bare
    # `not (width: 5px)` is a media-condition, and `only` is meaningless
    # there, so the leading keyword is consumed only in type position.
    if isinstance(toks[i], Ident):
        word = toks[i].value.lower()
        if word in ("not", "only"):
            query.negated = word == "not"
            i += 1

    features: list[Feature] = []
    # When a media type is present, an `and` must separate it from the first
    # feature -- exactly as one must separate any two features. Setting the
    # flag here rather than checking for `and` inline is what keeps the two
    # cases from needing separate code, and `screen and (min-width:1px)`
    # from being rejected as malformed.
    expect_and = False
    dangling_and = False
    if i < len(toks) and isinstance(toks[i], Ident):
        query.media_type = toks[i].value.lower()
        i += 1
        expect_and = True
    while i < len(toks):
        if expect_and:
            if not (isinstance(toks[i], Ident) and toks[i].value.lower() == "and"):
                # `or` and anything else joining clauses is out of scope.
                return MediaQuery(malformed=True)
            i += 1
            expect_and = False
            # An `and` promises a feature after it. If the token run ends
            # here instead, the query is malformed -- without this,
            # `@media screen and` parses as a bare `screen` and matches.
            dangling_and = True
            continue
        tok = toks[i]
        if not isinstance(tok, LParen):
            return MediaQuery(malformed=True)
        depth, j = 1, i + 1
        while j < len(toks) and depth:
            if isinstance(toks[j], (LParen, Function)):
                depth += 1
            elif isinstance(toks[j], RParen):
                depth -= 1
            j += 1
        if depth:
            return MediaQuery(malformed=True)  # unclosed paren
        features.append(_parse_feature(toks[i + 1 : j - 1]))
        i = j
        expect_and = True
        dangling_and = False
        continue

    if dangling_and:
        return MediaQuery(malformed=True)
    if query.media_type is None and not features:
        return MediaQuery(malformed=True)

    query.features = tuple(features)
    return query


def parse_media_query_list(tokens: list[CssToken]) -> tuple[MediaQuery, ...]:
    """Parse an `@media` prelude into its comma-separated queries.

    Never raises. A query that will not parse comes back `malformed`, which
    evaluates false without taking its siblings down with it -- an empty
    prelude (`@media {}`) is the one case that yields a single malformed
    query, matching the spec's "an empty query list is `not all`".
    """
    return tuple(_parse_query(part) for part in _split_on_commas(tokens))


# --------------------------------------------------------------------------
# Evaluation
# --------------------------------------------------------------------------


def _match_feature(feature: Feature, viewport: Viewport) -> bool:
    if feature.name == "orientation":
        return viewport.orientation == feature.value
    actual = viewport.width_px if feature.name == "width" else viewport.height_px
    if feature.op == "boolean":
        return actual != 0
    if feature.op == "min":
        return actual >= feature.value
    if feature.op == "max":
        return actual <= feature.value
    return actual == feature.value


def matches(
    queries: tuple[MediaQuery, ...],
    viewport: Viewport,
    metrics: Counter[str] | None = None,
) -> bool:
    """True when any query in the list matches `viewport`.

    `metrics` collects what was skipped and why:
      `media_queries_evaluated`     -- queries we could decide
      `media_queries_matched`       -- of those, how many were true
      `media_queries_malformed`     -- would not parse
      `media_queries_unsupported`   -- named a feature outside our scope
      `media_types_skipped`         -- `print` and friends
      `media_feature_<name>`        -- per unsupported feature name
    """
    metrics = Counter() if metrics is None else metrics
    result = False

    for query in queries:
        if query.malformed:
            metrics["media_queries_malformed"] += 1
            continue

        unsupported = query.unsupported
        if unsupported:
            # False regardless of `not` -- see the module docstring.
            metrics["media_queries_unsupported"] += 1
            for name in unsupported:
                metrics[f"media_feature_{name.lower()}"] += 1
            continue

        type_ok = query.media_type is None or query.media_type in _MATCHING_TYPES
        if not type_ok:
            metrics["media_types_skipped"] += 1
            metrics[f"media_type_{query.media_type}"] += 1
            # A media type we are not is a decided answer, not a gap: it is
            # false, and `not print` is legitimately true.
            if not query.negated:
                metrics["media_queries_evaluated"] += 1
                continue

        value = type_ok and all(_match_feature(f, viewport) for f in query.features)
        if query.negated:
            value = not value

        metrics["media_queries_evaluated"] += 1
        if value:
            metrics["media_queries_matched"] += 1
            result = True

    return result
