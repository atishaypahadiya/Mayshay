"""
The user-agent stylesheet.

Not optional, and not cosmetic. `display`'s initial value is `inline`, so a
document styled with author CSS alone lays out as one undifferentiated run of
inline text: no line boxes at paragraph boundaries, `<head>` rendered as
visible content, and `<script>` source printed into the page. The UA sheet is
what turns "the initial value of every property" into "what a browser
actually shows", and it is the lowest-priority origin in the cascade, so a
single author declaration overrides any of it.

Written as a CSS *string*, deliberately, rather than as a hand-built table of
`ComputedStyle` defaults. Two reasons:

1. It goes through the same tokenizer, parser, selector parser and value
   parser as author CSS, so it is a standing end-to-end exercise of the whole
   `cssparse` stack. A regression that breaks `h1, h2, h3 { ... }` selector
   lists or the one-to-four-value `margin` rule breaks *every* document, not
   just a test fixture.
2. A table of defaults would have to encode `display: block` per tag anyway,
   and would then need its own precedence story to sit under the author
   origin. The cascade already has one.

**Scope: the nine properties `values.py` parses.** Anything outside that set
(`font-weight: bold` on `h1`/`b`/`strong`, `font-style: italic` on `em`/`i`,
`text-decoration: underline` on `a`, `list-style-type` on `ul`/`ol`,
`white-space: pre` on `pre`/`textarea`, `font-family: monospace` on `code`)
is deliberately absent -- not forgotten. `parse_declaration_value` returns
`None` for every one of them, so writing them here would silently produce
dropped declarations and an inflated `declarations_dropped` metric that said
nothing about the document being styled. They come back when the property
set grows.

Deliberate omissions *inside* the nine properties, so a reviewer can tell a
decision from an oversight:

- **No `display` for the form and embedded-content elements** (`input`,
  `button`, `select`, `textarea`, `iframe`, `canvas`, `video`; grepped
  against `UA_CSS` -- none of the seven appears in any selector). They are
  `inline` by initial value, which is right, and their real behaviour is
  `inline-block`-ish sizing that only layout can express. `img`, `picture`,
  `map` and `area` *are* named, in the `display: inline` block, which
  changes nothing behaviourally -- the block exists to state intent against
  a future reset, as its own comment says -- but they are not omissions and
  an earlier version of this bullet wrongly listed `img` as one.
- **No `display: none` for `base`, `param`, `source`, `track`, `datalist`,
  `template`, `noscript`.** The brief names exactly six -- `head`, `style`,
  `script`, `link`, `title`, `meta` -- and those six are the ones that
  actually carry text a naive renderer would paint. The others are empty
  elements (nothing to paint) or, in `noscript`'s case, genuinely *shown*
  when scripting is disabled, which for this engine is always.
- **No `padding-left` on `ul`/`ol`** and no `margin` on `blockquote`,
  `figure`, `dl`, `dd`, `ol`, `ul`, `pre`, `hr`. The brief scopes default
  margins to `body`, `p` and `h1`-`h6`; adding a partial list of the rest
  would be a worse lie than the complete absence of one.
- **`li` is `display: block`, not the spec's `display: list-item`.** The
  keyword parses, but nothing generates a marker box, so `list-item` would
  today be a synonym for `block` that claimed more than it delivered. This
  one is a genuine gap rather than a decision, and it should be revisited
  the moment layout can draw a marker.
- **No `display` for the table elements' *presentational* fallbacks**
  (`table[role=presentation]`, `display: table` on non-table elements). The
  table display types themselves are all present -- see the Tables block
  below. An earlier draft of this file gave `<table>` `display: table` and
  left its children inline, and justified it on the grounds that the tree
  builder does not reliably build tables. That justification was false:
  Phase 1's carried gap is the *table insertion modes*' conformance
  behaviour on malformed markup, which is a different thing from the
  elements not existing -- `tr`, `td`, `th`, `tbody` and `caption` are all
  present in the corpus's parsed trees, in the hundreds.
- **Quirks-mode UA rules are absent entirely.** `Document.mode` is
  classified (Task C) but not acted on until layout.

The `h1`-`h6` font sizes are included even though the brief asks only for
margins, because those elements' margins are specified in `em` and `em` on a
non-`font-size` property resolves against the element's *own* computed
font-size. Leaving the font sizes out would silently make every heading
margin `1em` of the inherited 16px -- the exact class of plausible-looking
wrong number this phase exists to avoid -- and it exercises the cascade's
two `em` paths against each other on every real page.
"""

from __future__ import annotations

# Grouped and commented rather than minified: this is read far more often
# than it is edited, and a wall of selectors is unreviewable.
UA_CSS = """
/* --- Not rendered ------------------------------------------------------ */
head, style, script, link, title, meta { display: none }

/* --- Block-level ------------------------------------------------------- */
html, body, div, p, hr, pre, address, blockquote,
h1, h2, h3, h4, h5, h6, hgroup,
ul, ol, dl, dt, dd, li, menu, dir,
article, aside, footer, header, main, nav, section, search,
figure, figcaption, details, summary, dialog, fieldset, legend,
form, center, optgroup, option { display: block }

/* --- Tables ------------------------------------------------------------
   All of it or none of it. `display: table` on the container while `tr`,
   `td`, `tbody` and `caption` sit at the initial `inline` is worse than
   silence: the container establishes a formatting context its own children
   then ignore, and every row collapses into one inline run. The corpus
   makes that concrete -- hn.html has 4 tables, 98 `tr` and 159 `td`;
   wikipedia.html has 24, 120 and 159, plus 85 `th` and 24 `tbody`. */
table { display: table }
caption { display: table-caption }
colgroup { display: table-column-group }
col { display: table-column }
thead { display: table-header-group }
tbody { display: table-row-group }
tfoot { display: table-footer-group }
tr { display: table-row }
td, th { display: table-cell }

/* --- Inline ------------------------------------------------------------
   `inline` is already the initial value, so these rules change nothing on
   their own. They are here so the UA origin states the intent explicitly:
   a later `* { display: block }` in this sheet, or a reset that reaches
   these elements, must not turn `<em>` into a block. */
span, a, em, strong, b, i, u, s, small, big, tt, strike, font, nobr,
code, kbd, samp, var, cite, q, abbr, acronym, dfn,
sub, sup, mark, time, data, bdi, bdo, ruby, rt, rp,
ins, del, label, br, wbr, img, picture, map, area,
meter, progress, output, slot { display: inline }

/* --- Default margins ---------------------------------------------------
   `body`'s 8px is the one absolute default; every other margin below is in
   `em`, which the cascade resolves against the element's OWN computed
   font-size -- so the heading font-sizes on the next block are load-bearing
   for these numbers, not decoration. */
body { margin: 8px }
p { margin: 1em 0 }
h1 { margin: 0.67em 0 }
h2 { margin: 0.83em 0 }
h3 { margin: 1em 0 }
h4 { margin: 1.33em 0 }
h5 { margin: 1.67em 0 }
h6 { margin: 2.33em 0 }

/* --- Heading font sizes ------------------------------------------------
   `em` here resolves against the PARENT's computed font-size, unlike the
   `em` margins above. Same unit, two different bases, one element. */
h1 { font-size: 2em }
h2 { font-size: 1.5em }
h3 { font-size: 1.17em }
h4 { font-size: 1em }
h5 { font-size: 0.83em }
h6 { font-size: 0.67em }
"""

__all__ = ["UA_CSS"]
