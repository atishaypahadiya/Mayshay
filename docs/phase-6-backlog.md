# Phase 6 backlog

Questions this project is positioned to answer but that need a wider corpus
than three pages to be worth asking. Each entry carries its three-page seed
numbers, so the work of re-measuring on a real corpus is arithmetic rather
than rediscovery.

Nothing here is acted on during Phase 3-5. Adding an entry is cheap;
discovering the question after the corpus is collected is not.

---

## 1. What fraction of a page is authored-hidden, and what is it for?

**Seed, 2026-08-27, three pages, 8,593 elements, viewport 1280x1024.**

`display: none` removes 954 elements — 11.1% of the corpus — from 342
pruning roots. Split by the origin of the winning `display` declaration:

| | roots |
|---|---:|
| author CSS hid it | **202** |
| our UA stylesheet hid it (`<head>`, `<script>`, `<style>`) | 140 |

So **roughly 60% of the hiding on these pages is authored**. That reframes
the 954: not markup the engine happens to skip, but content real pages
deliberately ship and then hide. Something shipped it, something paid to
serialise it, and it never renders.

The author-hidden roots by tag: `span` 171, `div` 13, `nav` 5, `button` 4,
`li` 2, `td` 2, `sup` 2, `img` 1.

By class, which is where the *purpose* becomes visible:

| count | class | apparent purpose |
|---:|---|---|
| 115 | `.mw-linkback-text` | screen-reader text for reference backlinks |
| 50 | `.mw-empty-elt` | empty-element suppression |
| 6 | `.emptyPortlet` | collapsed navigation |
| 5 | `.hide-when-compact` | responsive alternate |
| 5 | `.mw-portlet` | collapsed navigation |
| 4 | `.vector-pinnable-header-toggle-button` | UI state |
| 3 | `.noexcerpt` | content-variant suppression |
| 2 each | `.vector-pinnable-header-pin-button`, `.vector-dropdown`, … | UI state |

**The primary method is mechanical, not class-name archaeology.** `@media`
evaluation already works, so a page can be styled at several viewports and
its hidden elements classified by *whether they are ever visible*:

* **permanently hidden** — `display: none` at every viewport tested
* **conditionally hidden** — hidden at some, shown at others

That separates accessibility text and empty-element suppression from
responsive alternates without reading a single class name. Run over the
corpus at six widths (320, 640, 1000, 1280, 1680, 1920):

| page | permanently hidden | of those, author | conditionally hidden |
|---|---:|---:|---:|
| example.com | 5 | 0 | 0 |
| news.ycombinator.com | 8 | 0 | 0 |
| en.wikipedia.org | 494 | 251 | **19** |

**The surprise is how small the conditional bucket is: 19 of 513, about
3.7%.** Responsive alternates are the explanation one reaches for first,
and on these pages they are almost all of what hiding is *not*. Hacker News
has twelve `@media` blocks and zero conditionally hidden elements — its
responsive CSS changes `display` to `block`, never to `none`.

The 19 are exactly what the hypothesis predicted, and they name themselves:

    li    hidden at 320          .vector-menu-item--collapsible   (x6)
    li    hidden at 640..1920    .vector-menu-item--collapsible   (x7)
    div   hidden at 320..1000    .vector-typeahead-search-container
    span  hidden at 640..1920    .cdx-button__icon                (x3)
    div   hidden at 640..1920    .emptyPortlet .mw-portlet-cactions
    a     hidden at 1280..1920   .cdx-button--fake-button

Collapsible navigation, a search container swapped below 1280, and icon
variants of buttons. **The mechanical classification and the class names
agree**, which is what licenses using class names as a *fallback* taxonomy
for the permanently-hidden bucket — where no viewport sweep can help,
because nothing ever reveals them.

### The tracking-markup absence is a corrected hypothesis, not a null result

The seed expected tracking pixels and analytics markup among the hidden
elements. None appeared, and the reason is structural rather than a
property of this sample:

1. **Wikipedia runs no third-party analytics.** It is close to the
   least representative page on the web for this particular question.
2. **Tracking markup does not use `display: none`.** A `display: none`
   element does not load its image — which defeats the entire purpose of a
   tracking pixel. The idiom is a 1x1 box, or off-screen absolute
   positioning (`left: -9999px`), or `visibility: hidden`, all of which
   keep the resource load.

So the Phase 5 crawler should look for **off-screen positioning, 1px
dimensions, and `visibility: hidden`** as a *separate category*, not expect
them under `display: none`. Measuring the `none` bucket alone would have
reported "the web ships almost no tracking markup", which would be an
artifact of the measurement and a conspicuously wrong claim.

Note that this engine does not implement `visibility` or `position:
absolute` geometry, so two of the three signals are currently unreachable.
That is a Phase 5 dependency worth knowing before the crawler is designed.

**Caveat that must travel with all of it.** Three pages, 90% Wikipedia, and
one site's design system dominates the class histogram completely.
`.mw-linkback-text` alone is 115 of 202 author-hidden roots. A seed, not a
finding.

---

## 2. Spec-required versus web-used

`docs/synthetic-only-coverage.md` accumulates the paths this engine
implements that no corpus page exercises, and its inverse: `nowrap` on 24%
of element boxes against `pre` on none, where a suite written from CSS 2.1
would weight them exactly backwards.

That register is already the seed. The Phase 6 question is whether the
inversion holds at scale, and it is one of the better claims available
here: **which parts of the CSS specification does the web actually use?**

---

## 3. Author-declared versus UA-supplied, as a general lens

Of 5,829 elements computing `display: inline`, 19.2% are author-declared
and 80.6% come from our UA sheet. Meanwhile `flex`, `grid`, `inline-block`
and `inline-flex` are **100% author-declared** — a UA sheet has no reason
to supply them.

So the two counts diverge most on exactly the values that drive scoping
decisions, and the property name does not say which count is meant. An
author-declared census measures what pages *do*; a UA-inclusive census
measures what an engine must *handle*. Worth reporting as two columns
throughout Phase 6 rather than picking one.
