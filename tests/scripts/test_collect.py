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


COLLECTION = "2026-08-29-test"


@pytest.fixture
def collected(tmp_path):
    fetcher = _StubFetcher()
    root = tmp_path / COLLECTION
    page = collect.collect_page(PAGE_URL, root, fetcher, follow_imports=True)
    directory = root / page.slug
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
    stray = directory.parent / "hand-saved"
    stray.mkdir()
    (stray / "wikipedia.html").write_text("<p>")
    pages = corpus.load_pages(COLLECTION, root=directory.parent.parent)
    assert [p.slug for p in pages] == [directory.name]


# --------------------------------------------------------------------------
# The three defects the 2026-08-29 survey found, each invisible below four
# URLs and each confirmed by execution before it was fixed.
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "a, b, why",
    [
        ("https://e.com/a/b", "https://e.com/a/b/", "a trailing slash"),
        ("https://e.com/p?id=1", "https://e.com/p?id=2", "a query string"),
        ("https://e.com/p?a=1&b=2", "https://e.com/p?b=2&a=1", "query order"),
        ("https://e.com/x", "https://f.com/x", "a different host"),
    ],
)
def test_slugs_distinguish_urls_that_used_to_collide(a, b, why):
    """The query string was dropped entirely, so `?id=1` and `?id=2` produced
    one directory and the second fetch overwrote the first -- manifest
    included, so nothing on disk recorded the loss. Forums and e-commerce are
    exactly the query-bearing site types, and both are survey strata."""
    assert collect.slug_for(a) != collect.slug_for(b), why


def test_a_slug_is_capped_well_under_the_filesystem_limit():
    """A real Wikipedia-shaped path reached 185 characters, close enough to
    the 255-byte component limit on APFS and ext4 to matter once a collection
    directory sits above it."""
    monster = "https://e.com/" + "/".join(f"segment{i:03d}" for i in range(60))
    slug = collect.slug_for(monster)
    assert len(slug) <= collect._SLUG_READABLE_MAX + 8
    assert slug != collect.slug_for(monster + "/more")


def test_a_slug_is_a_pure_function_of_the_url():
    """The digest is appended ALWAYS, not only on a detected collision: a
    conditional digest would depend on what else happened to be on disk,
    which is not a property a directory name may have."""
    assert collect.slug_for(PAGE_URL) == collect.slug_for(PAGE_URL)


def test_a_robots_disallowed_page_is_not_a_page(tmp_path):
    """It used to write a manifest naming a `page.html` that was never
    written, so it loaded cleanly and raised FileNotFoundError later, from
    whichever report first asked for its text. And because its byte count
    defaulted to 0 while `load_pages` sorts smallest first, it sorted FIRST
    and took out the report on its opening iteration."""

    class _Refusing(_StubFetcher):
        def allowed(self, url):
            return False

    root = tmp_path / COLLECTION
    page = collect.collect_page(PAGE_URL, root, _Refusing(), follow_imports=True)
    assert page.status == "robots-disallowed"
    manifest = json.loads((root / page.slug / "manifest.json").read_text())
    assert manifest["html"]["file"] is None

    with pytest.raises(corpus.Unfetched):
        corpus.load_page(root / page.slug)

    loaded = corpus.load_collection(COLLECTION, root=tmp_path)
    assert loaded.pages == []
    assert [status for _, status in loaded.unfetched] == ["robots-disallowed"]


def test_a_failed_fetch_leaves_no_directory_behind(tmp_path):
    """`mkdir` used to run before `raise_for_status`, so a 404 left an empty
    directory and no manifest -- which `load_pages` skips, making the attempt
    invisible and every downstream percentage silently a percentage of "pages
    that happened to fetch"."""

    class _NotFound(_StubFetcher):
        def get(self, url):
            return _Response(404, b"")

    root = tmp_path / COLLECTION
    # AssertionError, not Exception: the stub's raise_for_status raises that,
    # and a bare `Exception` here passed while the test was constructing its
    # own _Response with the arguments in the wrong order -- green, and never
    # reaching the code under test.
    with pytest.raises(AssertionError, match="404"):
        collect.collect_page(PAGE_URL, root, _NotFound(), follow_imports=True)
    assert not root.exists() or list(root.iterdir()) == []


def test_the_denominator_is_urls_attempted_not_pages_on_disk(tmp_path):
    """The whole reason `collection.json` exists. A 404 leaves nothing behind,
    so counting directories drops it from the denominator silently."""
    root = tmp_path / COLLECTION
    rows = [
        {"url": "https://a/", "status": "ok"},
        {"url": "https://b/", "status": "http-404"},
        {"url": "https://c/", "status": "robots-disallowed"},
    ]
    collect.write_collection_manifest(root, COLLECTION, rows, None)
    manifest = json.loads((root / "collection.json").read_text())
    assert manifest["attempted"] == 3
    assert manifest["collected"] == 1


# --------------------------------------------------------------------------
# Two populations, never merged
# --------------------------------------------------------------------------


def test_load_pages_refuses_to_guess_a_collection():
    """No default. Two fetches on two dates are two populations, and every
    figure in docs/ was computed against one of them."""
    with pytest.raises(TypeError):
        corpus.load_pages()  # type: ignore[call-arg]


def test_a_directory_is_not_a_collection_name(tmp_path):
    """`CORPUS / some_absolute_path` returns that path, so a caller passing a
    directory where a NAME belongs would get a working result and never learn
    it had skipped the collection layer entirely."""
    with pytest.raises(TypeError):
        corpus.load_collection(tmp_path)  # type: ignore[arg-type]


def test_collections_do_not_see_each_others_pages(collected, tmp_path):
    """Three collections, one holding three pages and one holding a single
    page, so a per-collection path and a whole-corpus path cannot coincide --
    the nesting-depth rule applied to the corpus loader."""
    _, directory, _ = collected
    corpus_root = directory.parent.parent

    other = corpus_root / "2026-01-01-other"
    for n in range(3):
        d = other / f"page-{n}"
        d.mkdir(parents=True)
        (d / "page.html").write_text(f"<p>{n}")
        (d / "manifest.json").write_text(
            json.dumps(
                {
                    "source_url": f"https://other/{n}",
                    "fetched_at": "2026-01-01T00:00:00+00:00",
                    "status": "ok",
                    "html": {"file": "page.html", "bytes": 4},
                    "stylesheets": [],
                    "imports": {},
                }
            )
        )
    (corpus_root / "2026-01-01-empty").mkdir()

    assert corpus.collection_names(corpus_root) == [
        "2026-01-01-other",
        COLLECTION,
    ]
    assert len(corpus.load_pages(COLLECTION, root=corpus_root)) == 1
    assert len(corpus.load_pages("2026-01-01-other", root=corpus_root)) == 3
    assert len(corpus.load_pages(corpus.ALL, root=corpus_root)) == 4

    banner = corpus.describe(corpus.ALL, root=corpus_root)
    assert "MERGED" in banner and "2026-01-01-other" in banner and COLLECTION in banner
