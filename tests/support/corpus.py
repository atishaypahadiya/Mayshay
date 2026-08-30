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

**Pages moved under a collection directory on 2026-08-29** --
`data/corpus/<collection>/<slug>/` -- so that two fetches on two dates stay
two populations. This module's flat `root.iterdir()` found nothing after
that change, and once again it was the "not silently empty" guards in the
sweeps that said so rather than a quietly passing suite. That is twice, and
it is the argument for those guards on every corpus sweep.

These sweeps default to **every** collection, and that is right here where
it would be wrong in a report: they ask "does every selector in the corpus
parse", which is a conformance question over a pile of CSS. More CSS is
strictly better and no denominator is being claimed. A *measurement* names
its collection -- see `scripts/corpus.py`, where the parameter is required.

Deliberately pytest-free, like `tests/support/parse_errors.py`, so it can be
imported from a script or a REPL.
"""

from __future__ import annotations

import pathlib

CORPUS = pathlib.Path(__file__).resolve().parents[2] / "data" / "corpus"


def page_paths(
    root: pathlib.Path | None = None, collection: str | None = None
) -> list[pathlib.Path]:
    """Every collected page's HTML, sorted by collection then directory.

    A directory only counts if it carries a `manifest.json` -- an HTML file
    with no manifest has no recorded source URL and no stylesheet map, so
    nothing downstream can attribute it. `collection=None` means every
    collection; see the module docstring for why that is right for a parse
    sweep and wrong for a measurement.
    """
    root = root or CORPUS
    if not root.is_dir():
        return []
    roots = (
        [root / collection]
        if collection
        else [d for d in sorted(root.iterdir()) if d.is_dir()]
    )
    return [
        directory / "page.html"
        for collection_dir in roots
        if collection_dir.is_dir()
        for directory in sorted(collection_dir.iterdir())
        if directory.is_dir()
        and (directory / "manifest.json").is_file()
        and (directory / "page.html").is_file()
    ]
