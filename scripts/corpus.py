#!/usr/bin/env python3
"""Load pages collected by `scripts/collect.py`.

One place that knows the manifest layout, so a measurement script can say

    from corpus import load_pages
    for page in load_pages():
        document = TreeBuilder(page.html()).build()
        counters = style_document(document, [], viewport,
                                  external_css=page.external_css())

instead of re-deriving "which `.css` file belongs to this page, in what
order" every time. That derivation is exactly where two scripts drift apart
and start reporting two different numbers for the same page.

Use `external_css()`, not `author_css()`. It returns the href-to-source
mapping `style_document` needs to cascade each sheet **at the position its
`<link>` occupies**. `author_css()` returns the same sources as a flat list,
which cascades all of them before every in-document `<style>` -- wrong
whenever a page interleaves the two, as Wikipedia does with two links and 18
`<style>` blocks. Source order is the cascade's last tiebreak, and ties of
equal origin, importance and specificity are common in real CSS, so the
difference is a real one. `author_css()` is kept for callers that want the
raw sources (byte counts, parse sweeps), not for cascading.

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

# The one legal way to ask for a mixed population, and it announces itself.
ALL = "all"


@dataclass
class CorpusPage:
    """One `data/corpus/<slug>/` directory, as described by its manifest."""

    directory: Path
    collection: str
    source_url: str
    fetched_at: str
    stratum: str
    selection_reason: str
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

    def external_css(self) -> dict[str, str]:
        """`href` as written in the document -> that sheet's source.

        The key is the raw href, because that is what `style_document` reads
        off the `<link>` element; the manifest is what maps it to a local
        file. Two `<link>`s sharing an href share one entry, which is
        correct: the same URL is one sheet, and the collector already
        fetched it once.
        """
        return {
            sheet["href"]: (self.directory / sheet["file"]).read_text(
                "utf-8", "replace"
            )
            for sheet in self.sheets
        }

    @property
    def css_bytes(self) -> int:
        """Total bytes of external CSS actually on disk for this page.

        External, applied sheets only. In-document `<style>` blocks are
        inside `html_bytes` and are counted separately by `style_document`'s
        `style_elements`; alternates and duplicates are on
        `unapplied_sheets`.
        """
        return sum(sheet["bytes"] or 0 for sheet in self.sheets)


class Unfetched(Exception):
    """A page directory whose manifest says no HTML was ever written."""

    def __init__(self, directory: Path, status: str) -> None:
        super().__init__(f"{directory.name}: {status}")
        self.directory, self.status = directory, status


def load_page(directory: Path) -> CorpusPage:
    """One page. Raises `Unfetched` if the manifest records no HTML.

    Refusing is the point. A robots-disallowed page used to produce a
    manifest naming a `page.html` that was never written, so it loaded
    cleanly and raised `FileNotFoundError` later, from whichever report
    first asked for its text -- and because its byte count defaulted to 0
    and `load_pages` sorts smallest first, it sorted first and took out the
    report on its opening iteration. A page that was not fetched is not a
    page; it is a row in `collection.json`.
    """
    manifest = json.loads((directory / "manifest.json").read_text("utf-8"))
    html = manifest.get("html") or {}
    status = manifest.get("status", "ok")
    if not html.get("file") or not (directory / html["file"]).is_file():
        raise Unfetched(directory, status if status != "ok" else "no html on disk")
    sheets = manifest.get("stylesheets", [])
    imports = manifest.get("imports", {})

    def fetched(s: dict) -> bool:
        return s["status"] == "ok" and bool(s["file"])

    def applied(s: dict) -> bool:
        return not s.get("duplicate_of") and "alternate" not in (s.get("rel") or [])

    return CorpusPage(
        directory=directory,
        collection=directory.parent.name,
        source_url=manifest["source_url"],
        fetched_at=manifest["fetched_at"],
        stratum=manifest.get("stratum", ""),
        selection_reason=manifest.get("selection_reason", ""),
        html_file=html["file"],
        html_bytes=html["bytes"],
        sheets=[s for s in sheets if fetched(s) and applied(s)],
        unapplied_sheets=[s for s in sheets if fetched(s) and not applied(s)],
        missing_sheets=[s for s in sheets if not fetched(s)],
        imports_skipped=imports.get("skipped", []),
        imports_followed=bool(imports.get("followed")),
    )


@dataclass
class Collection:
    """One `data/corpus/<name>/` directory: its pages and its denominator."""

    name: str
    directory: Path
    pages: list[CorpusPage]
    unfetched: list[tuple[Path, str]]  # (directory, why)
    attempted: int  # URLs the collector was ASKED for, from collection.json
    collected_at: str = ""

    @property
    def denominator(self) -> str:
        """The line every report prints. Never just the page count."""
        return f"{len(self.pages)} of {self.attempted} attempted"


def load_collection(name: str, root: Path | None = None) -> Collection:
    """One collection by name, with the URLs that never became pages.

    `attempted` comes from `collection.json`, not from counting directories.
    Counting directories answers "how many pages are on disk", which is the
    question nobody asked: a 404 leaves nothing behind, so a directory count
    silently drops it from the denominator and every percentage computed
    against it is over "pages that happened to fetch".
    """
    if not isinstance(name, str):
        # `CORPUS / some_absolute_path` returns that path, so a caller who
        # passed a directory where a collection NAME belongs would get a
        # working result and never learn it had skipped the collection
        # layer entirely. Refuse instead of quietly obliging.
        raise TypeError(
            f"collection must be a name, not {type(name).__name__}; "
            f"pass root= for a different corpus root"
        )
    directory = (root or CORPUS) / name
    if not directory.is_dir():
        raise FileNotFoundError(f"no collection {name!r} under {root or CORPUS}")

    pages, unfetched = [], []
    for d in sorted(directory.iterdir()):
        if not (d.is_dir() and (d / "manifest.json").is_file()):
            continue
        try:
            pages.append(load_page(d))
        except Unfetched as exc:
            unfetched.append((exc.directory, exc.status))

    manifest_path = directory / "collection.json"
    attempted, collected_at = len(pages) + len(unfetched), ""
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text("utf-8"))
        attempted = manifest.get("attempted", attempted)
        collected_at = manifest.get("collected_at", "")

    return Collection(
        name=name,
        directory=directory,
        pages=sorted(pages, key=lambda p: p.html_bytes),
        unfetched=unfetched,
        attempted=attempted,
        collected_at=collected_at,
    )


def load_pages(collection: str, root: Path | None = None) -> list[CorpusPage]:
    """Every collected page in one collection, smallest HTML first.

    Smallest first so a failure on the 800 KB page is not the first thing
    that happens.

    **`collection` is required and has no default.** Two fetches on two
    dates are two populations, and every figure in `docs/` was computed
    against one of them; a default would let a caller merge an August 27
    corpus with an August 29 one and silently change what a published
    number means. Pass `"all"` to work over the union -- legal, and it
    prints what it merged.
    """
    if collection == ALL:
        return sorted(
            (p for c in load_all(root) for p in c.pages), key=lambda p: p.html_bytes
        )
    return load_collection(collection, root).pages


def collection_names(root: Path | None = None) -> list[str]:
    """Every collection on disk: a directory holding at least one page."""
    root = root or CORPUS
    if not root.is_dir():
        return []
    return sorted(
        d.name
        for d in root.iterdir()
        if d.is_dir() and any(c.is_dir() and (c / "manifest.json").is_file()
                              for c in d.iterdir())
    )


def load_all(root: Path | None = None) -> list[Collection]:
    """Every collection, for `--collection all`."""
    return [load_collection(n, root) for n in collection_names(root)]


def describe(collection: str, root: Path | None = None) -> str:
    """The banner a report prints above any figure.

    A number over a mixed population must SAY it is over a mixed
    population, at the point of use, or the mixing is exactly as silent as
    having no collections at all.
    """
    if collection == ALL:
        cols = load_all(root)
        parts = ", ".join(f"{c.name} ({c.denominator})" for c in cols)
        return f"collections: {parts}  -- MERGED, {sum(len(c.pages) for c in cols)} pages"
    c = load_collection(collection, root)
    return f"collection {c.name}: {c.denominator}" + (
        f", collected {c.collected_at}" if c.collected_at else ""
    )
