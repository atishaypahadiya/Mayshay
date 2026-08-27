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


def slug_for(url: str) -> str:
    """A stable, filesystem-safe directory name derived from the URL."""
    parts = urlparse(url)
    tail = parts.path.strip("/").replace("/", "-")
    slug = f"{parts.netloc}{'-' + tail if tail else ''}"
    return re.sub(r"[^A-Za-z0-9._-]", "-", slug).strip("-").lower()


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


def collect_page(url: str, out_root: Path, fetcher: Fetcher, follow_imports: bool) -> Page:
    page = Page(source_url=url, slug=slug_for(url))
    page_dir = out_root / page.slug
    page_dir.mkdir(parents=True, exist_ok=True)

    if not fetcher.allowed(url):
        page.notes.append("robots.txt disallows this URL; nothing fetched")
        _write_manifest(page_dir, page, follow_imports)
        return page

    response = fetcher.get(url)
    response.raise_for_status()
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
        "html": {"file": "page.html", "bytes": page.html_bytes},
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


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("urls", nargs="+", help="absolute page URLs to collect")
    ap.add_argument("--out", default="data/corpus", help="corpus root (default: data/corpus)")
    ap.add_argument("--delay", type=float, default=1.0, help="seconds between requests")
    ap.add_argument(
        "--no-follow-imports",
        action="store_true",
        help="record @import targets as skipped instead of fetching them",
    )
    args = ap.parse_args(argv)

    out_root = Path(args.out)
    fetcher = Fetcher(delay=args.delay)
    failures = 0

    for url in args.urls:
        if not urlparse(url).scheme:
            print(f"! {url}: not an absolute URL, skipped", file=sys.stderr)
            failures += 1
            continue
        try:
            page = collect_page(url, out_root, fetcher, not args.no_follow_imports)
        except requests.RequestException as exc:
            print(f"! {url}: {type(exc).__name__}: {exc}", file=sys.stderr)
            failures += 1
            continue
        ok = [s for s in page.sheets if s.status == "ok"]
        css_bytes = sum(s.bytes or 0 for s in ok if not s.duplicate_of)
        print(
            f"{page.slug}: {page.html_bytes:,} B html, "
            f"{len(ok)}/{len(page.sheets)} sheets, {css_bytes:,} B css"
            + (f", {len(page.imports_skipped)} import(s) skipped" if page.imports_skipped else "")
        )
        for s in page.sheets:
            if s.status != "ok":
                print(f"    ! {s.status}: {s.resolved[:90]}")

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
