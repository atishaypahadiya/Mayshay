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

### The metric-compatibility claim, actually tested (Task D1)

Everything above rests on "Liberation Sans is metric-compatible with
Arial", which had been asserted here since the font was chosen and never
measured. Task D1 measured it: Chrome 151 headless, macOS, a page whose
only font declaration is `font: 16px/1 Arial`, each string in its own
`inline-block` with `white-space: pre`, widths read from
`getBoundingClientRect()`.

| string | ours (`hmtx`) | Chrome 151 | delta |
|---|---:|---:|---:|
| `Hello world` | 79.1406 | 79.1406 | 0 |
| `Wikipedia` | 69.3594 | 69.3594 | 0 |
| `x` | 8.0000 | 8.0000 | 0 |
| `M` | 13.3281 | 13.3281 | 0 |
| `0` | 8.8984 | 8.9063 | +1/128 |
| space | 4.4453 | 4.4531 | +1/128 |
| U+00A0 | 4.4453 | 4.4531 | +1/128 |
| `AV` | 21.3438 | 20.1563 | **-1.1875, kerning** |

**Chrome quantises layout to 1/64 px** -- its `LayoutUnit` -- **per
separately shaped text run**, so exact equality is not the criterion and
its absence is not a finding. Every row above is either exact (where the
true value already lands on a 1/64 boundary) or one LayoutUnit away, except
`AV`, which is the kerning divergence measured in the next section: our
unkerned 21.3438 against the 20.1562 recorded there, and Chrome's 20.1563
is that same number quantised.

The practical consequence for any future comparison harness: the tolerance
is `runs / 64` px, where `runs` is the number of separately shaped text
runs, and it is **not** a round number chosen to make a test pass.
`<i>a</i> <i>b</i>` is three runs and legitimately differs by three
LayoutUnits; `<div>alpha beta gamma</div>` is one and agrees to the last
bit.

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

### The prediction was tested, and it held

Written weeks before anything could check it, this file predicted that our
advances would run **wide** on kerned pairs, and gave `AV` as +5.56%
(21.3438 unkerned against 20.1562 kerned).

Task D1 measured 25 fixtures against Chrome 151. **Twenty-four agree within
Chrome's own LayoutUnit quantisation. The one disagreement is `AV`, at
21.3438 against Chrome's 20.1563** — the predicted string, in the predicted
direction, at the predicted magnitude.

That is stronger evidence for the Arial metric-compatibility claim than
across-the-board agreement would have been. **Agreement is consistent with
both engines being wrong in the same way** — a shared font file, a shared
rounding, a comparison that is really measuring itself. A predicted
*disagreement*, at a magnitude derived independently from the font's `kern`
table before any comparison existed, is not: it requires our advances and
Chrome's to be right, and the one modelled difference between them to be
exactly the modelled size.

The whole cross-engine comparison rests on the metric-compatibility claim,
and until D1 this was the one load-bearing assumption in `docs/fonts.md`
with no measurement behind it.

When the Phase 6 comparison harness exists, the measurement to report is
**not** an average width error. A 0.137% aggregate alongside `To` at +9.50%
means the error is not smoothly distributed -- it is near-zero almost
everywhere and concentrated in exactly the strings where it changes an
outcome. Averaging it away would hide the finding.

Report it as a **break-point** measurement instead:

* the fraction of laid-out lines whose break point differs from Chrome's,
* and what share of those differences are attributable to kerning, by
  re-running the same comparison with kern adjustments applied and seeing
  which disagreements disappear.

That second half is what makes it a finding rather than an error bar: it
partitions our divergence into "caused by not kerning" and "caused by
something else", and the something-else is the part worth fixing. Kern
pairs cluster in headings -- capitals and `To`/`Yo`/`AV`-shaped pairs --
so the expectation to test is that heading lines carry most of the
kerning-attributable breaks while body text carries almost none.

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

### A fifth answer, and it is not a fifth table (Task D2)

The table above says a mismatch of 3%, 5% or 18% names which vertical
metrics the other engine used. Task D2 measured Chrome 151 on macOS and
found a mismatch of **2.2%** that is none of them: Chrome rounds each of
`hhea`'s three numbers to a whole pixel before adding them.

Measured by stacking ten `<br>`-separated lines in a `<div>` and dividing,
at three font sizes chosen so that the rounding cannot cancel:

| font-size | ours (exact) | Chrome 151 | ascent | descent | line gap |
|---:|---:|---:|---:|---:|---:|
| 16 | 18.3984 | **18** | 14.484 -> 14 | 3.391 -> 3 | 0.523 -> 1 |
| 17 | 19.5483 | **20** | 15.392 -> 15 | 3.603 -> 4 | 0.556 -> 1 |
| 32 | 36.7969 | **37** | 28.969 -> 29 | 6.781 -> 7 | 1.047 -> 1 |

The rounded parts reproduce all three exactly and no other hypothesis does
-- note that Chrome is *larger* at 17px and *smaller* at 16px, so it is not
a floor, a ceiling or a different table.

**Chrome also floors the half-leading.** CSS 2.1 section 10.8.1 puts half
the leading above the content area and half below; with a 67-unit line gap
that is 33.5 either side, and Chrome puts 33 above and 34 below. Every
vertical-align comparison in `tests/layout/test_linebox.py` is off by
exactly 0.5px for this reason and no other.

This engine keeps the exact fractional metrics, because they are what the
font says and because a rounding that is right for one platform is wrong
for another -- Chrome on Linux does not round these. The practical
consequence is that a line-position comparison against Chrome on macOS
accumulates up to half a pixel per line, which is why Task D2's vertical
fixtures are stated at `font-size: 2048px`, where ascent 1854, descent 434
and line gap 67 are all whole pixels and there is nothing to round.

### `ex` measured against Chrome, and they disagree (Task D2)

`ex` is derived above from `OS/2.sxHeight` = 1082 units = 8.453125px at
16px, which is what CSS Values 4 section 5.1.2 asks for: the font's own
metric where one exists. It exists, and the `x` glyph's bounding box
agrees with it to the unit (`glyf` yMax for `x` is 1082).

**Chrome 151 on macOS reports `1ex` as 1062 units** -- 8.2969px at 16px and
2124px at 4096px, so it scales and is a metric rather than a rounding.
Measured directly by giving a `<div>` `width: 1ex` and reading its
`getBoundingClientRect()`, at three font sizes. `1ch` agrees exactly (1139
units, the advance of `0`), so this is specific to x-height and not a
general disagreement about units.

That is a **1.85% difference**, and the one place in this engine where it
is visible is `vertical-align: middle`, which aligns a box's midpoint at
the parent's baseline minus half the parent's x-height: 9px of divergence
at `font-size: 2048px` and 0.07px at 16px. Recorded rather than tuned away
-- the spec names the font's metric, this font has one, and matching a
platform's own idea of x-height would make the number depend on which
machine ran the comparison.

This is the `CSS Values -> the font's own tables` row of
`docs/measurement-hazards.md`'s deferral table producing a divergence for
the second time.

`hhea` matches `usWin` for ascent and descent here, differing only by the
67-unit line gap, and is what Chrome uses on macOS and Linux for this font.
A reader comparing line boxes against Chrome on Windows should expect the
`usWin` path instead.

### Baseline

The baseline sits `ascent` below the **content area** top: 14.484375px at
16px. Below the **line box** top it is `ascent + half the leading`, which
is 14.746094px at 16px under `line-height: normal`.
`vertical-align: baseline` aligns children on that line.

### `sub` and `super` are not font metrics (Task D2)

CSS 2.1 says only "the proper position for subscripts of the parent's box"
and leaves the offset to the user agent, so this file cannot derive it and
Task D2 measured it instead. Chrome 151:

    sub      lower by  font-size / 5 + 1
    super    raise by  font-size / 3 + 1

Confirmed at two sizes, which is what rules it out as a font metric: 4.1875
and 6.3281 at 16px, 410.5938 and 683.6563 at 2048px -- each `x/5 + 1` or
`x/3 + 1` quantised to Chrome's 1/64px LayoutUnit. This font's
`OS/2.ySubscriptYOffset` is 283 units (2.21px at 16px) and
`ySuperscriptYOffset` is 977 (7.63px), and **neither is what Chrome uses**.
So the OpenType subscript and superscript fields are recorded here as
present and unused, which is a smaller claim than "we follow the font" and
a true one.

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

### No font fallback, measured (Task D1)

"No font fallback" has a number now. Over the corpus, after white-space
collapsing, **198 characters in 143 distinct code points have no glyph in
Liberation Sans 2.1.5** -- Arabic, Devanagari, Burmese and CJK, essentially
all on the Wikipedia page. Population: 80,580 characters in 6,194 text
boxes at 1280x1024.

They are measured at the `.notdef` advance, 1536 units, 12.0px at a 16px
font size, and counted in `text_missing_glyph`. **Not zero**, which is the
point: a missing glyph that costs nothing makes a line look like it fits,
so the error would be invisible in exactly the direction that moves a break
point. Chrome falls back to a font that has the glyph, so this is a
per-character divergence rather than a rounding one, and on any string
containing one it is a far larger error than kerning.
