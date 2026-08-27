# The wrong answer arrives shaped like the right one

Three measurements on this project have been wrong in a way that was
invisible from the output. Not crashes, not obviously-bad numbers --
plausible values, of the right type, in the right range, internally
consistent. Each survived review by inspection. Each was caught only by a
**second measurement obtained a different way**.

This file records them together, because the pattern is more useful than
the three fixes.

## The three

### 1. The display census that was not measuring the pages

Through all of Phase 1 and Phase 2 the display distribution was computed
from the UA stylesheet plus in-document `<style>` blocks. No external
stylesheet had ever been fetched, and at-rules were counted and skipped.

The output looked complete: 7,778 elements, a sensible distribution,
`inline` dominant as it should be. Hacker News in particular reported a
plausible distribution -- which was entirely our own UA sheet, because that
page ships zero in-document CSS.

Even after the stylesheets were collected, Hacker News showed a display
delta of **exactly zero**, which reads as a finding ("external CSS does not
change this page's display") rather than a gap. It was a gap: all six
`display` declarations in `news.css` sit inside `@media` blocks the cascade
skipped. Measured afterwards, 51% of that page's CSS and 46% of Wikipedia's
was inside at-rules we never entered.

What it cost when fixed: Wikipedia's `flex` count went from 4 to 205.

**Caught by** treating the exactly-zero delta as a hypothesis to disprove
rather than a result -- injecting a probe stylesheet (`td { display: grid }`)
to prove the code path reached the cascade at all, then asking where the
real declarations had gone.

### 2. `PIL.ImageFont.getlength` returning integers

Pillow reports `"Hello world"` as `89.0` px at 16px. The font's own `hmtx`
metrics give `89.6953`.

`89.0` is a float, in the right range, and correct to within 1%. Nothing
about it looks like a rounding artifact. Setting
`layout_engine=ImageFont.Layout.BASIC` or `mode="L"` does not change it,
so the obvious "am I hitting a hinted path?" check returns the same number
and reads as confirmation.

The error compounds per glyph and per line, and it would have made a
Chrome comparison measure our rounding rather than our layout -- while
producing a believable error distribution.

**Caught by** computing the same advances from a second source
(`fontTools` reading `hmtx` directly) and finding they disagreed.

### 3. `DOM.getBoxModel` returning a union box for wrapping inlines

For an inline `<span>` spanning three lines, CDP's `getBoxModel` returns
one rectangle: x 0.00..194.80, y 89.00..154.00, 195 x 65. It is a
well-formed box with sensible coordinates. It is the **union** of the three
line fragments and matches none of them:

    fragment 0   78.25..184.09   x  89..106
    fragment 1    0.00..194.80   x 113..130
    fragment 2    0.00..188.53   x 137..154

Inline is 67.8% of the corpus. A comparison harness built on `getBoxModel`
would have compared our per-line fragments against a bounding box for two
thirds of every page, produced a large but plausible error distribution,
and validated nothing -- while looking like it worked.

**Caught by** asking a second CDP method (`getContentQuads`) the same
question and getting three answers where the first gave one.

## The shape

In all three the output had the right type, a plausible magnitude, and no
internal inconsistency. None would fail a sanity check. Two of them were
*more* convincing than the truth: an exactly-zero delta reads as a clean
finding, and an integer pixel width reads as a measurement rather than a
rounding.

This is the same family as the two failure modes CLAUDE.md already names --
the nine assert-from-reading claims and the ten-plus non-discriminating
tests on the Phase 2 branch. In every case the artifact was shaped like a
correct one and the only reliable detector was an independent second
derivation. Reading harder does not work. Neither does checking that the
number is reasonable, because it always was.

## What to do about it

* **A measurement is verified by a second measurement obtained a different
  way, not by inspection and not by internal consistency.** Two sources
  that agree is evidence. One source that looks right is not.
* **Treat a suspiciously clean result as a hypothesis to disprove.** Exactly
  zero, exactly integral, exactly unchanged -- each of those is a claim
  about the world that is usually a claim about the instrument. Probe the
  path before believing the number: inject a value you know should move it
  and confirm it moves.
* **When two methods can answer the same question, ask both once** before
  building on either. It is one throwaway script at design time and a
  rebuilt harness afterwards.
* **Prefer the source closest to the data.** `hmtx` over a rasterizer's
  convenience wrapper; the manifest over a directory glob; the token stream
  over a regex. Each layer of convenience is a place a value can be
  quietly reshaped.
* **Write the countermeasure down with the number.** Every figure in
  `docs/fonts.md` and `docs/corpus.md` carries its derivation for this
  reason: a value with its provenance can be rechecked, a value alone
  can only be believed.
