#!/usr/bin/env python3
"""Load pages collected by `scripts/collect.py`.

One place that knows the manifest layout, so a measurement script can say

    from corpus import load_pages
    for page in load_pages():
        document = TreeBuilder(page.html()).build()
        counters = style_document(document, page.author_css())

instead of re-deriving "which `.css` file belongs to this page, in what
order" every time. That derivation is exactly where two scripts drift apart
and start reporting two different numbers for the same page.

Ordering deviation, stated up front because it affects results:
`style_document` cascades everything in `author_css` *before* the
in-document `<style>` elements it finds itself. A browser interleaves
`<link>` and `<style>` by document position. The two differ only for
declarations of equal origin, importance and specificity -- where source
order is the tiebreak -- so it is a real difference, not a theoretical one,
and it is worth fixing at the `style_document` boundary when external sheets
stop being a corpus-only concern. Until then this loader hands sheets over
in document order among themselves and the deviation stays visible here.

Sheets that failed to fetch are not silently dropped: they stay on
`page.missing_sheets` with the status the collector recorded, so a caller
can report "3 of 4 sheets" rather than implying it measured all four.

Two kinds of collected sheet are deliberately NOT applied:

* `rel="stylesheet alternate"` -- a browser fetches it but does not apply it
  unless the user selects that alternate. It stays in the corpus and on
  `page.unapplied_sheets`; it is not in `author_css()` and its bytes are not
  in `css_bytes`.
* a sheet whose URL the page linked twice -- the collector fetched it once
  and marked the second entry `duplicate_of`. Applying identical CSS twice
  changes no computed value, and counting its bytes twice would inflate a
  figure that ends up cited.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "data" / "corpus"


@dataclass
class CorpusPage:
    """One `data/corpus/<slug>/` directory, as described by its manifest."""

    directory: Path
    source_url: str
    fetched_at: str
    html_file: str
    html_bytes: int
    sheets: list[dict]  # fetched AND applied, document order
    unapplied_sheets: list[dict]  # fetched but not applied (alternate, duplicate)
    missing_sheets: list[dict]  # not fetched, with the status that says why
    imports_skipped: list[dict]
    imports_followed: bool

    @property
    def slug(self) -> str:
        return self.directory.name

    @property
    def html_path(self) -> Path:
        return self.directory / self.html_file

    def html(self) -> str:
        """The saved HTML, decoded permissively.

        `errors="replace"` rather than a traceback: a real page can carry
        bytes that are not valid UTF-8, and the tokenizer's own U+FFFD
        handling is where that should surface.
        """
        return self.html_path.read_text(encoding="utf-8", errors="replace")

    def author_css(self) -> list[str]:
        """Every successfully fetched stylesheet's source, in document order.

        Ready to pass straight to `style_document(document, ...)`. `@charset`
        is not honoured; sheets are decoded as UTF-8 with replacement, which
        is what the CSS Syntax spec's fallback amounts to for the pages this
        corpus holds.
        """
        return [
            (self.directory / sheet["file"]).read_text("utf-8", "replace")
            for sheet in self.sheets
        ]

    @property
    def css_bytes(self) -> int:
        """Total bytes of external CSS actually on disk for this page.

        External, applied sheets only. In-document `<style>` blocks are
        inside `html_bytes` and are counted separately by `style_document`'s
        `style_elements`; alternates and duplicates are on
        `unapplied_sheets`.
        """
        return sum(sheet["bytes"] or 0 for sheet in self.sheets)


def load_page(directory: Path) -> CorpusPage:
    manifest = json.loads((directory / "manifest.json").read_text("utf-8"))
    sheets = manifest.get("stylesheets", [])
    imports = manifest.get("imports", {})

    def fetched(s: dict) -> bool:
        return s["status"] == "ok" and bool(s["file"])

    def applied(s: dict) -> bool:
        return not s.get("duplicate_of") and "alternate" not in (s.get("rel") or [])

    return CorpusPage(
        directory=directory,
        source_url=manifest["source_url"],
        fetched_at=manifest["fetched_at"],
        html_file=manifest["html"]["file"],
        html_bytes=manifest["html"]["bytes"],
        sheets=[s for s in sheets if fetched(s) and applied(s)],
        unapplied_sheets=[s for s in sheets if fetched(s) and not applied(s)],
        missing_sheets=[s for s in sheets if not fetched(s)],
        imports_skipped=imports.get("skipped", []),
        imports_followed=bool(imports.get("followed")),
    )


def load_pages(root: Path | None = None) -> list[CorpusPage]:
    """Every collected page, smallest HTML first.

    Smallest first so a failure on the 800 KB page is not the first thing
    that happens. Directories without a `manifest.json` are ignored, which
    is what keeps `data/corpus/2026-08-26-snapshot/` -- the hand-saved,
    stylesheet-less Phase 1/2 fetch -- out of new measurements. See
    `docs/corpus.md`.
    """
    root = root or CORPUS
    pages = [
        load_page(d)
        for d in sorted(root.iterdir())
        if d.is_dir() and (d / "manifest.json").is_file()
    ]
    return sorted(pages, key=lambda p: p.html_bytes)
