# The layout font

Every layout number this project produces depends on one font file. Glyph
advances change between releases, so "Liberation Sans" is not a
specification and "Liberation Sans 2.1.5" is. This file is that
specification.

## The file

| | |
|---|---|
| Path | `data/fonts/LiberationSans-Regular.ttf` |
| Family / subfamily | Liberation Sans / Regular |
| Version | 2.1.5 (name ID 5: `Version 2.1.5`) |
| Source | `liberation-fonts-ttf-2.1.5.tar.gz`, liberationfonts/liberation-fonts, released 2021-09-30 |
| Licence | SIL Open Font License 1.1 — `data/fonts/LICENSE-Liberation.txt` |
| SHA-256 | `76d04c18ea243f426b7de1f3ad208e927008f961dc5945e5aad352d0dfde8ee8` |
| Size | 410,712 bytes |
| `unitsPerEm` | 2048 |
| OS/2 table version | 3 |

The file is committed rather than downloaded at build time. `data/fonts/`
is deliberately not in `.gitignore` — only `data/corpus/` and
`data/metrics/*.csv` are — because this is a dependency, not derived data,
and a layout figure has to be traceable to the exact bytes that produced
it.

Verify with:

    shasum -a 256 data/fonts/LiberationSans-Regular.ttf

## Why this font

Liberation Sans is **metric-compatible with Arial**: the same glyph
advances at the same `unitsPerEm`. That is the mechanism that makes
cross-engine numeric comparison work — a test stylesheet naming `Arial`
gets identical advances from Chrome and from this engine, so box positions
are directly comparable and "position error against a reference renderer"
becomes a measurable distribution rather than an aspiration.

Spot check of the canonical Arial advances, at 2048 units/em:

| glyph | `A` | `W` | `i` | `m` | `x` | `0` | space |
|---|---:|---:|---:|---:|---:|---:|---:|
| units | 1366 | 1933 | 455 | 1706 | 1024 | 1139 | 569 |

DejaVu Sans was the alternative and was rejected twice over: it has no
Arial counterpart, so the comparison would require Chrome to actually have
DejaVu installed; and it ships OS/2 version 1 with no `sxHeight`, which
would put a glyph-bounding-box fallback under every `ex` unit permanently
(see below).

## Where metrics come from

**Advances are read from the font's `hmtx` table via `fontTools`, not from
`PIL.ImageFont.getlength`.** Measured before deciding: Pillow returns
integer-rounded advances at 16px — `"Hello world"` in DejaVu Sans comes
back as `89.0` where the font's own metrics give `89.6953` — and neither
`layout_engine=ImageFont.Layout.BASIC` nor `mode="L"` changes it. That
error compounds per glyph and per line, and would make a Chrome comparison
measure our rounding rather than our layout.

Reading `hmtx` directly is exact, deterministic, involves no rasterizer,
and is linear in font size (one multiply). It is also what a browser does:
unhinted fractional advances for layout, hinted rendering for paint.
Pillow keeps rasterization in Phase 4, over this same file, so there is one
font and one metric definition.

### Kerning and ligatures are not applied

`hmtx` advances only: no `GPOS`, no `GSUB`, and the legacy `kern` table is
not consulted either. Chrome applies all of them, so this is a systematic
divergence rather than noise -- and it is **measured**, not merely named.
Liberation Sans 2.1.5 carries 908 pairs in its legacy `kern` table.

Kerning adjustments are almost always negative, so omitting them makes our
text **wider** than Chrome's, not narrower. Note the direction: it is the
opposite of what "we do less work" suggests. Measured over every visible
text run in the corpus, with `<script>`, `<style>` and `<noscript>`
excluded and whitespace collapsed:

| page | unkerned | kerned | our error |
|---|---:|---:|---:|
| example.com | 1,059.2px | 1,058.0px | +0.111% |
| news.ycombinator.com | 26,301.4px | 26,268.4px | +0.125% |
| en.wikipedia.org/wiki/HTML | 576,249.8px | 575,460.2px | +0.137% |
| **all** | **603,610.4px** | **602,786.6px** | **+0.137%** |

**5,181 visible text runs; 753 of them (14.5%) contain at least one kerned
pair.**

The aggregate correction is small -- our advances run about 0.14% wide --
but it is badly distributed, and per string it is far larger:

| string | unkerned | kerned | our error |
|---|---:|---:|---:|
| `To` | 18.6719px | 16.8984px | +9.50% |
| `Yo` | 19.5703px | 18.1016px | +7.51% |
| `AV` | 21.3438px | 20.1562px | +5.56% |
| `Wa` | 24.0000px | 23.4062px | +2.47% |
| `Hello world` | 79.1406px | 79.1406px | 0% |
| `The quick brown fox` | 143.1797px | 143.1797px | 0% |

A short heading of capitals can be 5-10% too wide while a body paragraph is
exact. That matters for line breaking rather than just for width: a line
whose measured width lands within 0.14% of its container may break where
Chrome does not, and a heading may wrap a word early.

Reproduce from `data/fonts/LiberationSans-Regular.ttf` with `fontTools`;
flatten `tt["kern"].kernTables` into `{(glyphA, glyphB): adjustment}` in
font units and add the adjustment between consecutive glyph pairs.

When the Phase 6 comparison harness exists this is the correction factor to
apply, and the number to report alongside the error distribution -- a
residual with a known systematic component rather than an unexplained one.

## Derivations

All of these are `units x font-size / unitsPerEm`, with `unitsPerEm =
2048`. Values shown at a 16px font size.

### `ex` — CSS Values 4 §5.1.2

The spec says `ex` is the used x-height, and that a UA should use the
font's own metric where one exists.

    ex = OS/2.sxHeight / unitsPerEm x font-size
       = 1082 / 2048 x 16
       = 8.453125px

`sxHeight` is present because this font ships **OS/2 version 3**; the field
was added in version 2. Where a font ships an older OS/2 table the spec's
fallback is the bounding-box height of the `x` glyph, and where there is no
`x` either, 0.5em. This project does not implement either fallback: it uses
one font, that font has `sxHeight`, and an unreachable fallback is an
untested one. If a second font is ever added, the fallback chain has to be
written and tested then.

Phase 2 used a flat `0.5em` = 8.0px, a 5.4% underestimate.

### `ch` — CSS Values 4 §5.1.3

Defined as the advance of U+0030 DIGIT ZERO — the *advance*, not the glyph
width, and not an average character width.

    ch = advance(U+0030) / unitsPerEm x font-size
       = 1139 / 2048 x 16
       = 8.898438px

Phase 2 used `0.5em` = 8.0px, an 11.2% underestimate.

### Line box height for `line-height: normal`

    normal = (hhea.ascent - hhea.descent + hhea.lineGap) / unitsPerEm
           = (1854 - (-434) + 67) / 2048
           = 1.1499023 em
           = 18.398438px

with the parts, at 16px:

| part | units | px |
|---|---:|---:|
| ascent | 1854 | 14.484375 |
| descent | 434 | 3.390625 |
| line gap | 67 | 0.523438 |

`hhea` is used. The font ships three sets of vertical metrics and they
disagree; which one an engine picks is platform-dependent, and this is one
of the larger sources of cross-engine line-height difference in practice.

**All four candidate answers, written down so a mismatch is a lookup rather
than an investigation.** If a Chrome comparison comes back off by a
consistent factor, this table is the first thing to check.

| source | ascent | descent | line gap | sum | em | px @16 | vs `hhea` |
|---|---:|---:|---:|---:|---:|---:|---:|
| **`hhea`** (used) | 1854 | 434 | 67 | 2355 | 1.149902 | **18.3984** | --- |
| `OS/2` usWin | 1854 | 434 | 0 | 2288 | 1.117188 | 17.8750 | -2.85% |
| `OS/2` typo, with `sTypoLineGap` | 1491 | 431 | 307 | 2229 | 1.088379 | 17.4141 | -5.35% |
| `OS/2` typo, without line gap | 1491 | 431 | -- | 1922 | 0.938477 | 15.0156 | -18.39% |

The typo row appears twice on purpose: engines differ on whether
`sTypoLineGap` counts toward `normal`, and the two conventions sit 5.35%
and 18.39% from our number. A line-height discrepancy of roughly 3%, 5% or
18% is therefore diagnostic -- it names which table and which convention
the other engine used.

`hhea` matches `usWin` for ascent and descent here, differing only by the
67-unit line gap, and is what Chrome uses on macOS and Linux for this font.
A reader comparing line boxes against Chrome on Windows should expect the
`usWin` path instead.

### Baseline

The baseline sits `ascent` below the line box top: 14.484375px at 16px.
`vertical-align: baseline` aligns children on that line.

## Sample advances

Exact, unhinted, at 16px. Useful as a fixture: if these move, the font
changed.

| text | units | px |
|---|---:|---:|
| `Hello world` | 10130 | 79.1406 |
| `Wikipedia` | 8878 | 69.3594 |
| `x` | 1024 | 8.0000 |
| `0` | 1139 | 8.8984 |
| space | 569 | 4.4453 |
| `M` | 1706 | 13.3281 |

## Scope

One face: Regular. No bold, italic, or bold-italic, and no font fallback —
`font-family` lists are parsed and recorded but every text run measures in
Liberation Sans Regular. `font-weight: bold` therefore changes no advance,
which will make bold text measurably narrow against Chrome. Counted, not
silently ignored; adding the other three faces is a later task, and they
are in the same release tarball.
