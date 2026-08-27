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

- **No `display` for the replaced/embedded elements** (`img`, `input`,
  `button`, `select`, `textarea`, `iframe`, `canvas`, `video`). They are
  `inline` by initial value, which is right, and their real behaviour is
  `inline-block`-ish sizing that only layout can express.
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
- **No `table` display types beyond `display: table` on `<table>` itself.**
  `table-row`/`table-cell` are parseable values, but the tree builder's
  table insertion modes are a Phase 1 carried gap, so styling for a table
  structure the parser does not reliably build would be untestable.
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

table { display: table }

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
