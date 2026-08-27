"""Locating the collected corpus from a test.

`data/corpus/` used to be a flat directory of `.html` files saved by hand.
`scripts/collect.py` replaced that with one directory per page, each holding
`page.html`, its stylesheets and a `manifest.json` -- see docs/corpus.md.
Tests that swept the old layout with `CORPUS.glob("*.html")` found nothing
after the change, and their own "not silently empty" guards are what caught
it. This module exists so that path lives in one place and the next layout
change breaks one file instead of several.

`data/corpus/2026-08-26-snapshot/` is deliberately excluded: it is the
pre-collector, stylesheet-less fetch kept for provenance, and its numbers
must not be mixed with the current corpus. It has no `manifest.json`, which
is exactly what filters it out here.

Deliberately pytest-free, like `tests/support/parse_errors.py`, so it can be
imported from a script or a REPL.
"""

from __future__ import annotations

import pathlib

CORPUS = pathlib.Path(__file__).resolve().parents[2] / "data" / "corpus"


def page_paths(root: pathlib.Path | None = None) -> list[pathlib.Path]:
    """Every collected page's HTML, sorted by directory name.

    A directory only counts if it carries a `manifest.json` -- an HTML file
    with no manifest has no recorded source URL and no stylesheet map, so
    nothing downstream can attribute it.
    """
    root = root or CORPUS
    if not root.is_dir():
        return []
    return [
        directory / "page.html"
        for directory in sorted(root.iterdir())
        if (directory / "manifest.json").is_file()
        and (directory / "page.html").is_file()
    ]
