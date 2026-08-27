# The corpus

`data/corpus/` holds the real pages the engine is measured against. The
directory is gitignored -- it is hundreds of kilobytes of someone else's
copyrighted HTML, and it is reproducible -- so this file is the tracked
record of what is supposed to be in it and where the published numbers came
from.

Rebuild it with:

    .venv/bin/python scripts/collect.py \
        https://example.com/ \
        https://news.ycombinator.com/ \
        https://en.wikipedia.org/wiki/HTML

## Layout

One directory per page, named by a slug derived from the URL:

    data/corpus/
      en.wikipedia.org-wiki-html/
        manifest.json     source URL, fetch time, byte sizes, href -> file map
        page.html         byte-identical to what the server sent
        sheet-01.css      ... in document order, including @import children
      news.ycombinator.com/
      example.com/
      2026-08-26-snapshot/   <- see "The 2026-08-26 snapshot" below

Nothing is rewritten. `page.html` still contains the original hrefs, so it
can be re-fetched and byte-compared. The mapping from an href to the local
file lives only in `manifest.json`, which is why every consumer must go
through it -- `scripts/corpus.py` is that consumer, and measurement scripts
should use it rather than globbing for `*.css`.

## What the manifest records

Per stylesheet: the `href` exactly as written, the absolute URL it resolved
to, the local filename, byte size, the `rel` token list, how it was reached
(`link` or `@import from sheet-NN.css`), and a status. A sheet that failed
to fetch keeps its entry with `file: null` and a status saying why, so a
report can say "3 of 4 sheets" instead of quietly measuring three and
implying four.

`@import` is followed **one level deep**. Anything deeper is written to
`imports.skipped` with the sheet it came from. Silently missing an import
would understate a page's CSS while looking complete, which is the one
outcome worth engineering against.

Hrefs resolve against the URL the page was fetched from, recorded in the
manifest -- not against a `<base>` or `<link rel=canonical>` in the
document. Of the three pages here only Wikipedia carries a canonical and
none carries a `<base>`, so trusting the document would silently fail on
two of three.

Two kinds of collected sheet are **not applied** by `scripts/corpus.py`,
though both stay on disk and in the manifest:

* `rel="stylesheet alternate"` -- fetched by a browser, applied only if the
  user picks that alternate.
* a URL the page linked twice -- fetched once, second entry marked
  `duplicate_of`. Applying identical CSS twice changes no computed value,
  and counting its bytes twice would inflate a figure that gets cited.

## The 2026-08-26 snapshot

`data/corpus/2026-08-26-snapshot/` holds the three pages as they were saved
**by hand** during Phase 1, before `scripts/collect.py` existed. It has no
manifest and no stylesheets, so `corpus.load_pages()` skips it.

Every figure below came from that fetch and from a cascade that saw the UA
stylesheet plus in-document `<style>` blocks only:

| file             | elements | note                                        |
|------------------|---------:|---------------------------------------------|
| `wikipedia.html` |    7,778 | 36.3% whitespace (the Phase 1 headline)      |
| `hn.html`        |      806 | zero in-document CSS -- its entire display distribution was our UA sheet |
| `example.html`   |       12 |                                              |

`link_stylesheets_skipped` was 0 / 1 / 2 for example / hn / wikipedia.

**Do not mix these with numbers from a re-collected corpus.** A re-fetched
Wikipedia article is a different document -- different element count,
different whitespace ratio -- and two numbers from two snapshots presented
as one is the kind of error that survives into a writeup. Cite a figure
with the snapshot it came from, or recompute it.

The snapshot is kept for provenance, not for new measurements.

## Measuring against it

    .venv/bin/python scripts/display_report.py     # display census
    .venv/bin/python scripts/style_report.py       # metrics -> data/metrics/

Both go through `scripts/corpus.py`, which reads each manifest and hands
the external sheets to `style_document` via `page.external_css()` -- an
href-to-source mapping, so each sheet cascades **at the position its
`<link>` occupies**. Do not glob for `*.css`, and do not use
`page.author_css()` for cascading: that returns a flat list, which puts
every external sheet before every in-document `<style>`. All three pages
here happen to place their links first, so the two agree on this corpus --
but source order is the cascade's last tiebreak and the difference is real
on any page that interleaves them.

Both take `--viewport` (default `1280x1024`), because `@media` evaluation
makes every cascade figure viewport-dependent. `style_report.py` writes the
viewport into the metrics rows for that reason: a `flex` count with no
viewport beside it is not a reproducible number. Pass `--viewport none` to
reproduce the pre-Task-A behaviour, where every at-rule was skipped.

## Politeness

`scripts/collect.py` reads `robots.txt` per host and rate-limits between
every request (default 1s, `--delay` to change it). It is a corpus tool,
not the Phase 5 crawler: it takes an explicit URL list, follows no links,
and is expected to be run rarely. A robots.txt that cannot be fetched is
treated as permissive, and that decision is written into the page's
manifest `notes` so it is visible rather than assumed.
