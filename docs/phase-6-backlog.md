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

Even on one page the categories separate cleanly: **accessibility text,
responsive alternates, collapsed navigation, UI state**. Notably *absent*
from this sample: tracking pixels and analytics markup, which the
hypothesis expected.

**The question.** Across a real corpus: what fraction of shipped markup is
authored-hidden, how is it distributed across those categories, and does
the distribution differ by site type? A page that ships 12% hidden markup
for accessibility is a different finding from one that ships 12% for
responsive alternates it will never show at any viewport this user has.

**Why this project can answer it.** The engine already computes the
cascade, evaluates `@media`, and distinguishes author from UA origin —
which is exactly what separates "hidden by the browser's defaults" from
"hidden on purpose". A crawler with a regex cannot make that distinction,
and a headless browser can but will not tell you *which origin* won.

**What it needs.** A wider corpus (Phase 5), and a purpose taxonomy that is
more than class-name archaeology — probably `aria-hidden`, `role`, and
whether the element becomes visible at any of a set of viewports, since
`@media` evaluation makes that last one directly measurable.

**Caveat that must travel with it.** Three pages, 90% Wikipedia, and one
site's design system dominates the class histogram completely.
`.mw-linkback-text` alone is 115 of 202. This is a seed, not a finding.

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
