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

## 4. The crawlable web is smaller than the visible web, and biased

**Seeded 2026-08-29 by the corpus survey's HEAD check.** Not a collection
detail: a constraint on what any structural survey of the web can say, and
the reason it belongs here rather than in `docs/corpus.md`.

Eighty URLs were checked with HEAD before collection, honouring `robots.txt`
exactly as the collector does. **Six were disallowed. One had been
predicted.**

| stratum | checked | robots-disallowed | rate |
|---|---:|---:|---:|
| `news` | 10 | 1 | 10% |
| `docs` | 10 | 1 | 10% |
| `ecommerce` | 10 | 1 | 10% |
| `spa` | 8 | 1 | 12% |
| `gov` | 10 | 0 | 0% |
| `personal` | 10 | 0 | 0% |
| `forum` | 8 | 2 | 25% |
| `marketing` | 8 | 0 | 0% |
| `nonlatin` | 6 | 0 | 0% |
| **all** | **80** | **6** | **8%** |

The six:

* `https://text.npr.org/`
* `https://www.w3.org/TR/CSS22/visuren.html`
* `https://www.lulu.com/search`
* `https://www.tldraw.com/`
* `https://lobste.rs/t/css`
* `https://lore.kernel.org/lkml/`

**The composition is the finding, not the rate.** These are not commercial
properties protecting inventory. `w3.org/TR/` is the standards corpus this
engine is written from. `lore.kernel.org` is a public mailing-list archive
whose entire purpose is durable public availability. `text.npr.org` is a
news organisation's deliberately accessible edition. `lobste.rs` is a small
community site. Every one of them exists to be read, and every one of them
is closed to an identified, rate-limited, one-shot fetcher that obeys the
protocol.

So the crawlable web is **biased against exactly the sites a structural
survey most wants**: reference, archival, standards and small-community
pages -- the hand-authored, long-lived, low-JavaScript end of the
distribution. The pages that remain skew commercial and framework-built.
Any claim of the form "N% of the web does X" that rests on a polite crawl
is really "N% of the web that permits polite crawling", and those two
populations differ in precisely the dimension a markup survey measures.

Three things to do with this in Phase 6:

1. **Report the disallow rate beside every corpus figure**, per stratum. It
   is a property of the sample, not an incident during collection.
2. **Measure whether it moved.** Six of eighty is a 2026-08-29 number from
   a nine-stratum sample; whether the rate is rising is a better question
   than what it is, and the seed above is what makes the comparison
   possible later.
3. **Name the counterfactual.** For each disallowed URL, what would it have
   contributed? `w3.org/TR/` and `lore.kernel.org` were the two lowest-CSS
   documents in the whole sample -- so their exclusion does not merely
   shrink the corpus, it truncates one tail of the distribution being
   measured.

Related: `docs/corpus.md` records the mechanics; this entry records what the
mechanics imply about the population.
