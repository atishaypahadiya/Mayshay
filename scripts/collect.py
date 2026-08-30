#!/usr/bin/env python3
"""Collect corpus pages together with their stylesheets.

This is a corpus tool, not the Phase 5 crawler. It fetches a fixed list of
URLs once so the engine has real pages to measure against; it does not
discover links, does not recurse into a site, and has no scheduling,
politeness budget or caching beyond what is written here.

What it guarantees:

* **Nothing is rewritten.** The HTML is written to disk byte-identical to
  what the server sent. Local filenames live only in `manifest.json`, so a
  page can always be re-fetched and byte-compared against what we stored.
* **Every stylesheet is attributable.** The manifest records, per sheet, the
  href exactly as it appeared, the absolute URL it resolved to, the local
  filename, and how it was reached (a `<link>` or an `@import` from a named
  sheet). Without that map the `.css` files are anonymous blobs.
* **`@import` is followed one level deep, and anything deeper is recorded
  as skipped** with the sheet it came from. Silently dropping imports would
  understate a page's CSS while looking complete.

Resolution uses the URL the page was fetched from, recorded in the manifest
-- not a `<base>` or `<link rel=canonical>` in the document. Of the three
pages this corpus started with, only Wikipedia carried a canonical and none
carried a `<base>`, so trusting the document would silently fail on two of
three. Relative (`news.css?v=1`), root-relative (`/w/load.php?...`) and
protocol-relative (`//example.com/a.css`) hrefs all resolve correctly
against an absolute page URL via `urljoin`.

BeautifulSoup is used to find the `<link>` elements. That is permitted here
by CLAUDE.md -- this is `scripts/`, not engine code -- and it is also the
right call on the merits: the corpus must not be shaped by whatever bugs
`mayshay.htmlparse` currently has, or a parser defect would quietly become
a corpus defect and then validate itself.

Usage:

    scripts/collect.py https://example.com/ https://news.ycombinator.com/
    scripts/collect.py --out data/corpus --delay 2.0 URL [URL ...]
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
import time
import urllib.robotparser
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

USER_AGENT = (
    "mayshay-corpus/0.1 (educational browser engine; "
    "one-shot corpus collection, not a crawler)"
)

# `@import "a.css";` / `@import url(a.css);` / `@import url("a.css") screen;`
# The trailing media query is deliberately not parsed -- we fetch the sheet
# regardless of media, because the corpus is for structural measurement and a
# print-only sheet is still CSS the page ships.
_IMPORT_RE = re.compile(
    r"""@import\s+(?:url\(\s*)?["']?([^"')\s;]+)""", re.IGNORECASE
)


_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)


def imports_in(css: str) -> list[str]:
    """The `@import` targets in a stylesheet, comments removed first.

    Stripping comments matters: a commented-out `@import` is common in
    real sheets, and fetching one would put a stylesheet in the corpus that
    the page never loads. It is a lexical approximation -- an `@import`
    inside a string literal would still match -- but it errs toward the
    right side, and every fetch it makes is recorded in the manifest where
    an unexpected one is visible.
    """
    return _IMPORT_RE.findall(_COMMENT_RE.sub(" ", css))


@dataclass
class Sheet:
    """One stylesheet, and how we got to it."""

    href: str  # exactly as written in the document or @import
    resolved: str  # absolute URL actually requested
    file: str | None  # local filename, None if not fetched
    bytes: int | None
    via: str  # "link" or "@import from <file>"
    status: str  # "ok", "http-<code>", "robots-disallowed", "error-<type>"
    # The `rel` token list, lowercased. Recorded because `rel="stylesheet
    # alternate"` is CSS the page ships but that a browser does NOT apply
    # unless the user picks it. Collecting it is right; applying it is not,
    # and the consumer can only tell the difference if we write it down.
    rel: list[str] = field(default_factory=list)
    # Set when this href resolved to a URL already fetched for this page.
    # The file is shared rather than re-fetched, and a consumer must not
    # count its bytes twice.
    duplicate_of: str | None = None


@dataclass
class Page:
    source_url: str
    slug: str
    # "ok", "robots-disallowed", "http-<code>", "error-<Type>". Recorded on
    # the page AND in collection.json, so no consumer has to infer a page's
    # fate from whether a file happens to exist.
    status: str = "ok"
    stratum: str = ""
    selection_reason: str = ""
    html_bytes: int = 0
    sheets: list[Sheet] = field(default_factory=list)
    imports_skipped: list[dict] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


class Fetcher:
    """Rate-limited, robots-respecting fetcher.

    The delay is enforced between *all* requests, not per host: this tool
    fetches a handful of pages once, so the simpler rule is the safer one.
    """

    def __init__(self, delay: float = 1.0, timeout: float = 20.0) -> None:
        self.delay = delay
        self.timeout = timeout
        self._last = 0.0
        self._robots: dict[str, urllib.robotparser.RobotFileParser | None] = {}
        self.session = requests.Session()
        self.session.headers["User-Agent"] = USER_AGENT

    def _wait(self) -> None:
        elapsed = time.monotonic() - self._last
        if elapsed < self.delay:
            time.sleep(self.delay - elapsed)
        self._last = time.monotonic()

    def allowed(self, url: str) -> bool:
        """robots.txt check, cached per host.

        A robots.txt that cannot be fetched is treated as permissive, which
        is the conventional reading. That decision is recorded per page so it
        is visible rather than assumed.
        """
        parts = urlparse(url)
        host = f"{parts.scheme}://{parts.netloc}"
        if host not in self._robots:
            parser = urllib.robotparser.RobotFileParser()
            parser.set_url(urljoin(host, "/robots.txt"))
            try:
                self._wait()
                response = self.session.get(
                    urljoin(host, "/robots.txt"), timeout=self.timeout
                )
                if response.status_code == 200:
                    parser.parse(response.text.splitlines())
                    self._robots[host] = parser
                else:
                    self._robots[host] = None
            except requests.RequestException:
                self._robots[host] = None
        parser = self._robots[host]
        return True if parser is None else parser.can_fetch(USER_AGENT, url)

    def get(self, url: str) -> requests.Response:
        self._wait()
        return self.session.get(url, timeout=self.timeout)


# How much of the readable slug survives before the digest is appended.
# APFS and ext4 both cap a path component at 255 bytes, and a Wikipedia-style
# path already reached 185 in testing; 100 leaves room for the digest and for
# a long collection directory above it.
_SLUG_READABLE_MAX = 100


def slug_for(url: str) -> str:
    """A stable, filesystem-safe, **collision-free** directory name.

    Three things this must get right, and the first two were wrong until
    the 2026-08-29 survey found them:

    * **The query string is part of the identity of a page.** It was dropped
      entirely, so `?id=1` and `?id=2` produced one directory and the second
      fetch silently overwrote the first -- manifest included, so nothing on
      disk recorded the loss. Forums and e-commerce, two whole strata of the
      survey, are exactly the query-bearing site types.
    * **A trailing slash is not a different page**, but it did produce the
      same slug as its unslashed form, which is the same collision from the
      other direction.
    * A long path produced a 185-character component, close enough to the
      255-byte filesystem limit to matter.

    So: the digest is taken over the **whole** URL and appended *always*,
    not only when a collision is detected. Always is what makes the slug a
    pure function of the URL -- a conditional digest would depend on what
    else happened to be on disk, which is not a property a directory name
    should have.
    """
    parts = urlparse(url)
    tail = parts.path.strip("/").replace("/", "-")
    if parts.query:
        tail = f"{tail}-{parts.query}" if tail else parts.query
    slug = f"{parts.netloc}{'-' + tail if tail else ''}"
    slug = re.sub(r"[^A-Za-z0-9._-]", "-", slug).strip("-").lower()
    slug = re.sub(r"-{2,}", "-", slug)[:_SLUG_READABLE_MAX].strip("-")
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:7]
    return f"{slug}-{digest}" if slug else digest


def stylesheet_hrefs(html: bytes, encoding: str | None) -> list[tuple[str, list[str]]]:
    """Every `<link rel=stylesheet href>` in document order, with its `rel`.

    `rel` is a space-separated, case-insensitive token list
    (`rel="Stylesheet alternate"` is two tokens), so membership is tested
    against the split tokens rather than the raw string. The whole list is
    returned, not just the fact that it matched, because `alternate` changes
    whether a browser applies the sheet.
    """
    soup = BeautifulSoup(html.decode(encoding or "utf-8", "replace"), "html.parser")
    out = []
    for tag in soup.find_all("link"):
        rel = tag.get("rel") or []
        if isinstance(rel, str):
            rel = rel.split()
        rel = [token.lower() for token in rel]
        if "stylesheet" in rel:
            href = (tag.get("href") or "").strip()
            if href:
                out.append((href, rel))
    return out


def collect_page(
    url: str,
    out_root: Path,
    fetcher: Fetcher,
    follow_imports: bool,
    stratum: str = "",
    selection_reason: str = "",
) -> Page:
    page = Page(
        source_url=url,
        slug=slug_for(url),
        stratum=stratum,
        selection_reason=selection_reason,
    )
    page_dir = out_root / page.slug

    if not fetcher.allowed(url):
        # `html.file` stays None. It used to say `"page.html"` for a file
        # that was never written, and `corpus.load_page` believed it -- so
        # a robots-disallowed page loaded fine and raised FileNotFoundError
        # only when something asked for its HTML. Worse, `html_bytes`
        # defaulted to 0 and `load_pages` sorts smallest first, so the one
        # unloadable page sorted FIRST and took out every report script on
        # its opening iteration.
        page.status = "robots-disallowed"
        page.notes.append("robots.txt disallows this URL; nothing fetched")
        page_dir.mkdir(parents=True, exist_ok=True)
        _write_manifest(page_dir, page, follow_imports)
        return page

    # The fetch happens BEFORE the directory exists. `mkdir` used to run
    # first, so a 404 left an empty directory with no manifest -- which
    # `load_pages` skips, making the attempt invisible and every downstream
    # percentage silently a percentage of "pages that happened to fetch".
    response = fetcher.get(url)
    response.raise_for_status()
    page_dir.mkdir(parents=True, exist_ok=True)
    # Bytes, not text: the HTML must stay byte-identical to what was served.
    (page_dir / "page.html").write_bytes(response.content)
    page.html_bytes = len(response.content)
    page.notes.append(f"http {response.status_code}; encoding {response.encoding}")

    index = 0
    # resolved URL -> local filename, so a page that links the same sheet
    # twice is fetched once and cannot double-count its bytes.
    seen: dict[str, tuple[str, int]] = {}

    def fetch(href: str, resolved: str, via: str, rel: list[str]) -> Sheet:
        nonlocal index
        if resolved in seen:
            name, size = seen[resolved]
            return Sheet(href, resolved, name, size, via, "ok", rel, duplicate_of=name)
        index += 1
        sheet = _fetch_sheet(
            href, resolved, f"sheet-{index:02d}.css", via, page_dir, fetcher
        )
        sheet.rel = rel
        if sheet.file:
            seen[resolved] = (sheet.file, sheet.bytes or 0)
        return sheet

    for href, rel in stylesheet_hrefs(response.content, response.encoding):
        sheet = fetch(href, urljoin(url, href), "link", rel)
        page.sheets.append(sheet)

        if not (follow_imports and sheet.file and not sheet.duplicate_of):
            continue
        css = (page_dir / sheet.file).read_text("utf-8", "replace")
        for imported in imports_in(css):
            child = fetch(
                imported,
                urljoin(sheet.resolved, imported),
                f"@import from {sheet.file}",
                [],
            )
            page.sheets.append(child)
            # One level only. Anything the child imports is recorded, not
            # fetched -- an unrecorded skip would understate the page's CSS.
            if not (child.file and not child.duplicate_of):
                continue
            deeper = imports_in((page_dir / child.file).read_text("utf-8", "replace"))
            for grandchild in deeper:
                page.imports_skipped.append(
                    {
                        "href": grandchild,
                        "resolved": urljoin(child.resolved, grandchild),
                        "from": child.file,
                        "reason": "depth limit: @import is followed one level only",
                    }
                )

    _write_manifest(page_dir, page, follow_imports)
    return page


def _fetch_sheet(
    href: str, resolved: str, filename: str, via: str, page_dir: Path, fetcher: Fetcher
) -> Sheet:
    if not fetcher.allowed(resolved):
        return Sheet(href, resolved, None, None, via, "robots-disallowed")
    try:
        response = fetcher.get(resolved)
    except requests.RequestException as exc:
        return Sheet(href, resolved, None, None, via, f"error-{type(exc).__name__}")
    if response.status_code != 200:
        return Sheet(href, resolved, None, None, via, f"http-{response.status_code}")
    (page_dir / filename).write_bytes(response.content)
    return Sheet(href, resolved, filename, len(response.content), via, "ok")


def _write_manifest(page_dir: Path, page: Page, follow_imports: bool) -> None:
    manifest = {
        "source_url": page.source_url,
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "collector": USER_AGENT,
        "status": page.status,
        "stratum": page.stratum,
        "selection_reason": page.selection_reason,
        "html": {
            "file": "page.html" if page.status == "ok" else None,
            "bytes": page.html_bytes if page.status == "ok" else None,
        },
        "stylesheets": [
            {
                "href": s.href,
                "resolved": s.resolved,
                "file": s.file,
                "bytes": s.bytes,
                "via": s.via,
                "status": s.status,
                "rel": s.rel,
                "duplicate_of": s.duplicate_of,
            }
            for s in page.sheets
        ],
        "imports": {
            "followed": bool(follow_imports),
            "depth": 1 if follow_imports else 0,
            "skipped": page.imports_skipped,
        },
        "notes": page.notes,
    }
    (page_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )


@dataclass
class Candidate:
    """One row of a URL list: the page and why it is in the sample."""

    url: str
    stratum: str = ""
    risk: str = ""
    head: str = ""
    selection_reason: str = ""


def read_url_list(path: Path) -> list[Candidate]:
    """Parse a tab-separated URL list, `#` comments and blanks ignored.

    Tolerates 1 to 5 columns so a bare list of URLs still works. The metadata
    columns are carried through into `collection.json` rather than looked up
    later from a second file: a lookup table that can drift from the corpus
    it describes is the same defect as a manifest that can drift from the
    files it names.
    """
    out: list[Candidate] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        fields = line.split("\t")
        out.append(Candidate(*(fields + [""] * (5 - len(fields)))[:5]))
    return out


def write_collection_manifest(
    out_root: Path, collection: str, rows: list[dict], list_path: Path | None
) -> Path:
    """One row per URL **attempted**, whatever became of it.

    This is the denominator. Without it a report counts the directories that
    happen to exist and calls the result "the corpus" -- and a page that
    404'd, timed out or was refused by robots.txt is not distinguishable
    from a page nobody ever asked for. Every consumer reads `attempted`
    from here and prints "N of M".
    """
    out_root.mkdir(parents=True, exist_ok=True)
    path = out_root / "collection.json"
    ok = [r for r in rows if r["status"] == "ok"]
    path.write_text(
        json.dumps(
            {
                "collection": collection,
                "collected_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "collector": USER_AGENT,
                "url_list": str(list_path) if list_path else None,
                "attempted": len(rows),
                "collected": len(ok),
                "pages": rows,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("urls", nargs="*", help="absolute page URLs to collect")
    ap.add_argument("--urls-from", type=Path, help="tab-separated URL list file")
    ap.add_argument(
        "--collection",
        required=True,
        help="collection name; pages land in <out>/<collection>/. REQUIRED: "
        "two fetches on two dates are two populations and merging them "
        "silently changes what every published figure means",
    )
    ap.add_argument("--out", default="data/corpus", help="corpus root (default: data/corpus)")
    ap.add_argument("--delay", type=float, default=1.0, help="seconds between requests")
    ap.add_argument(
        "--no-follow-imports",
        action="store_true",
        help="record @import targets as skipped instead of fetching them",
    )
    args = ap.parse_args(argv)

    out_root = Path(args.out) / args.collection
    fetcher = Fetcher(delay=args.delay)
    failures = 0

    candidates = [Candidate(u) for u in args.urls]
    if args.urls_from:
        candidates += read_url_list(args.urls_from)
    if not candidates:
        print("no URLs: pass them as arguments or with --urls-from", file=sys.stderr)
        return 1

    rows: list[dict] = []

    def book(cand: Candidate, status: str, page: Page | None) -> None:
        rows.append(
            {
                "url": cand.url,
                "stratum": cand.stratum,
                "risk_predicted": cand.risk,
                "head_check": cand.head,
                "selection_reason": cand.selection_reason,
                "status": status,
                "slug": page.slug if page else slug_for(cand.url),
                "html_bytes": page.html_bytes if page and status == "ok" else None,
                "sheets_ok": (
                    sum(1 for x in page.sheets if x.status == "ok") if page else 0
                ),
                "sheets_total": len(page.sheets) if page else 0,
            }
        )

    for n, cand in enumerate(candidates, 1):
        url = cand.url
        if not urlparse(url).scheme:
            print(f"! {url}: not an absolute URL, skipped", file=sys.stderr)
            book(cand, "not-absolute", None)
            failures += 1
            continue
        try:
            page = collect_page(
                url,
                out_root,
                fetcher,
                not args.no_follow_imports,
                stratum=cand.stratum,
                selection_reason=cand.selection_reason,
            )
        except requests.RequestException as exc:
            status = (
                f"http-{exc.response.status_code}"
                if getattr(exc, "response", None) is not None
                else f"error-{type(exc).__name__}"
            )
            print(f"! [{n}/{len(candidates)}] {url}: {status}", file=sys.stderr)
            book(cand, status, None)
            failures += 1
            continue
        book(cand, page.status, page)
        if page.status != "ok":
            print(f"! [{n}/{len(candidates)}] {url}: {page.status}", file=sys.stderr)
            failures += 1
            continue
        print(f"[{n}/{len(candidates)}] ", end="")
        ok = [s for s in page.sheets if s.status == "ok"]
        css_bytes = sum(s.bytes or 0 for s in ok if not s.duplicate_of)
        print(
            f"{page.slug}: {page.html_bytes:,} B html, "
            f"{len(ok)}/{len(page.sheets)} sheets, {css_bytes:,} B css"
            + (f", {len(page.imports_skipped)} import(s) skipped" if page.imports_skipped else "")
        )
        for sheet in page.sheets:
            if sheet.status != "ok":
                print(f"    ! {sheet.status}: {sheet.resolved[:90]}")

    path = write_collection_manifest(out_root, args.collection, rows, args.urls_from)
    collected = sum(1 for r in rows if r["status"] == "ok")
    print(f"\n{collected} of {len(rows)} attempted -> {path}")
    if failures:
        print(f"{failures} did not collect; every one is a row in collection.json")
    # A failure is BOOKED, not fatal: the whole point of the manifest is that
    # a partial collection is a documented population rather than a broken one.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
