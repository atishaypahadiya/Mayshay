"""Tests for the corpus collector and its loader.

`tests/` mirrors `src/mayshay/`, and `scripts/` is not part of the package
-- but `collect.py` produces the manifest that every future measurement
number is computed from, and a silent defect there (an unfollowed import, a
double-counted sheet, an href resolved against the wrong base) would look
exactly like a finding about the web. That earns a test.

Everything here runs against a stub fetcher. No network: the point is to
pin the manifest's shape and the resolution rules, not to observe whichever
CSS a CDN served this morning.

Every assertion below has been injection-tested -- the depth-2 skip record,
page-URL resolution, comment stripping, URL dedupe and byte-identical HTML
were each deliberately broken in a shadowed copy, and each one failed a
test here.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import collect  # noqa: E402
import corpus  # noqa: E402

PAGE_URL = "https://ex.test/dir/page.html"

# One page exercising every resolution form and every skip rule at once.
# The `<link>` set is deliberately hostile: a relative href, a root-relative
# one, a protocol-relative one, an alternate, a repeat of an earlier URL, a
# 404, and a non-stylesheet `rel` that must not be fetched at all.
PAGE_HTML = b"""<!doctype html><html><head>
<link rel="stylesheet" href="rel.css">
<link rel="stylesheet" href="/root.css">
<link rel="stylesheet" href="//cdn.test/proto.css">
<link rel="Stylesheet Alternate" href="/alt.css">
<link rel="stylesheet" href="/root.css">
<link rel="stylesheet" href="/gone.css">
<link rel="preload" href="/nope.css">
</head><body></body></html>"""

SITE = {
    PAGE_URL: (200, PAGE_HTML),
    # A live @import, and a commented-out one that must not be fetched.
    "https://ex.test/dir/rel.css": (
        200,
        b'@import "deep1.css";\n/* @import "commented.css"; */\na{color:red}',
    ),
    # This one's @import is at depth 2: recorded, never fetched.
    "https://ex.test/dir/deep1.css": (200, b"@import url(deep2.css);\nb{color:blue}"),
    "https://ex.test/root.css": (200, b"c{color:green}"),
    "https://cdn.test/proto.css": (200, b"d{color:teal}"),
    "https://ex.test/alt.css": (200, b"e{color:gray}"),
    "https://ex.test/gone.css": (404, b"nope"),
}


class _Response:
    def __init__(self, status_code: int, content: bytes) -> None:
        self.status_code = status_code
        self.content = content
        self.encoding = "utf-8"

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise AssertionError(self.status_code)


class _StubFetcher(collect.Fetcher):
    """Serves SITE and records every URL asked for.

    A request for a URL not in SITE raises rather than 404s: the set of
    fetches is itself under test, and "we fetched something we shouldn't
    have" must be a failure, not a quiet miss.
    """

    def __init__(self) -> None:
        super().__init__(delay=0)
        self.log: list[str] = []

    def allowed(self, url: str) -> bool:
        return True

    def get(self, url: str) -> _Response:
        self.log.append(url)
        if url not in SITE:
            raise AssertionError(f"unexpected fetch: {url}")
        return _Response(*SITE[url])


@pytest.fixture
def collected(tmp_path):
    fetcher = _StubFetcher()
    page = collect.collect_page(PAGE_URL, tmp_path, fetcher, follow_imports=True)
    directory = tmp_path / page.slug
    manifest = json.loads((directory / "manifest.json").read_text("utf-8"))
    return fetcher, directory, manifest


def by_url(manifest: dict) -> dict[str, dict]:
    return {s["resolved"]: s for s in manifest["stylesheets"]}


def test_saved_html_is_byte_identical_to_what_was_served(collected):
    _, directory, _ = collected
    assert (directory / "page.html").read_bytes() == PAGE_HTML


def test_relative_href_resolves_against_the_page_url(collected):
    _, _, manifest = collected
    assert by_url(manifest)["https://ex.test/dir/rel.css"]["href"] == "rel.css"


def test_root_relative_href_resolves_against_the_origin(collected):
    _, _, manifest = collected
    assert by_url(manifest)["https://ex.test/root.css"]["href"] == "/root.css"


def test_protocol_relative_href_takes_the_pages_scheme(collected):
    _, _, manifest = collected
    sheet = by_url(manifest)["https://cdn.test/proto.css"]
    assert sheet["href"] == "//cdn.test/proto.css"
    assert sheet["resolved"].startswith("https://")


def test_href_map_names_a_local_file_for_every_fetched_sheet(collected):
    _, directory, manifest = collected
    fetched = [s for s in manifest["stylesheets"] if s["status"] == "ok"]
    assert fetched, "no sheets fetched at all"
    for sheet in fetched:
        assert sheet["file"], sheet
        local = directory / sheet["file"]
        assert local.is_file()
        assert local.read_bytes() == SITE[sheet["resolved"]][1]
        assert sheet["bytes"] == len(SITE[sheet["resolved"]][1])


def test_import_is_followed_one_level(collected):
    fetcher, _, manifest = collected
    assert "https://ex.test/dir/deep1.css" in fetcher.log
    assert by_url(manifest)["https://ex.test/dir/deep1.css"]["via"].startswith(
        "@import from"
    )


def test_depth_two_import_is_recorded_not_fetched(collected):
    fetcher, _, manifest = collected
    assert "https://ex.test/dir/deep2.css" not in fetcher.log
    skipped = manifest["imports"]["skipped"]
    assert [s["resolved"] for s in skipped] == ["https://ex.test/dir/deep2.css"]
    assert skipped[0]["from"], "a skipped import must name the sheet it came from"


def test_commented_out_import_is_not_fetched(collected):
    fetcher, _, _ = collected
    assert "https://ex.test/dir/commented.css" not in fetcher.log


def test_non_stylesheet_rel_is_not_fetched(collected):
    fetcher, _, _ = collected
    assert "https://ex.test/nope.css" not in fetcher.log


def test_repeated_href_is_fetched_once_and_marked_duplicate(collected):
    fetcher, _, manifest = collected
    assert fetcher.log.count("https://ex.test/root.css") == 1
    entries = [s for s in manifest["stylesheets"] if s["resolved"].endswith("/root.css")]
    assert len(entries) == 2, "both <link>s must still appear in the manifest"
    assert [bool(s["duplicate_of"]) for s in entries] == [False, True]
    assert entries[1]["file"] == entries[0]["file"]


def test_failed_sheet_is_recorded_with_its_status(collected):
    _, _, manifest = collected
    sheet = by_url(manifest)["https://ex.test/gone.css"]
    assert sheet["status"] == "http-404"
    assert sheet["file"] is None


def test_manifest_records_source_url_and_timestamp(collected):
    _, _, manifest = collected
    assert manifest["source_url"] == PAGE_URL
    assert manifest["fetched_at"].endswith("+00:00")
    assert manifest["html"]["bytes"] == len(PAGE_HTML)


def test_no_follow_imports_records_the_skip_instead_of_fetching(tmp_path):
    fetcher = _StubFetcher()
    collect.collect_page(PAGE_URL, tmp_path, fetcher, follow_imports=False)
    manifest = json.loads(
        (tmp_path / collect.slug_for(PAGE_URL) / "manifest.json").read_text("utf-8")
    )
    assert "https://ex.test/dir/deep1.css" not in fetcher.log
    assert manifest["imports"]["followed"] is False
    assert manifest["imports"]["depth"] == 0


# --- the loader ---------------------------------------------------------


def test_loader_applies_only_the_sheets_a_browser_would(collected):
    _, directory, _ = collected
    page = corpus.load_page(directory)
    assert [s["resolved"] for s in page.sheets] == [
        "https://ex.test/dir/rel.css",
        "https://ex.test/dir/deep1.css",
        "https://ex.test/root.css",
        "https://cdn.test/proto.css",
    ]
    # The alternate and the duplicate were collected, and are visible -- but
    # not applied. Dropping them from the manifest entirely would be the
    # silent version of this.
    assert {s["resolved"] for s in page.unapplied_sheets} == {
        "https://ex.test/alt.css",
        "https://ex.test/root.css",
    }
    assert [s["status"] for s in page.missing_sheets] == ["http-404"]


def test_author_css_returns_sheet_sources_in_document_order(collected):
    _, directory, _ = collected
    page = corpus.load_page(directory)
    assert page.author_css() == [
        SITE[s["resolved"]][1].decode() for s in page.sheets
    ]


def test_css_bytes_counts_each_applied_sheet_once(collected):
    _, directory, _ = collected
    page = corpus.load_page(directory)
    # Not sum(all fetched): the duplicate's 14 bytes and the alternate's 13
    # are excluded, so a regression in either rule moves this number.
    assert page.css_bytes == sum(
        len(SITE[url][1])
        for url in (
            "https://ex.test/dir/rel.css",
            "https://ex.test/dir/deep1.css",
            "https://ex.test/root.css",
            "https://cdn.test/proto.css",
        )
    )


def test_loader_exposes_the_source_url_and_html(collected):
    _, directory, _ = collected
    page = corpus.load_page(directory)
    assert page.source_url == PAGE_URL
    assert page.html() == PAGE_HTML.decode()
    assert page.html_bytes == len(PAGE_HTML)


def test_load_pages_ignores_directories_without_a_manifest(collected):
    _, directory, _ = collected
    (directory.parent / "2026-08-26-snapshot").mkdir()
    (directory.parent / "2026-08-26-snapshot" / "wikipedia.html").write_text("<p>")
    pages = corpus.load_pages(directory.parent)
    assert [p.slug for p in pages] == [directory.name]
