"""The merge gate: every collected page lays out without raising.

Cheap, and it is the check that would have caught the defect Task H exists
to fix. Phase 3 shipped green against three pages; the first 79-page run
found **12 crashes across 7 of 9 strata**, ten of them one assertion in flex
code that had been reviewed a week earlier. No unit test could have found it
-- the minimal synthetic reproduction of the failing container *passes*.

This does not check that layout is CORRECT. It checks that it terminates,
which is the floor, and the floor is where the last defect was.

Task H fixed the twelve and this reads **79 of 79**. It was marked
`xfail(strict=True)` until it did: the mark came off in the diff that
earned it, which is what `xfail_strict` is for. A gate that has to be
remembered is not a gate.

The four causes behind the twelve are in `tests/layout/test_corpus_causes.py`,
one fixture each, every one derived from a named page in this collection.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "scripts")]

from tests.support.marks import requires_corpus  # noqa: E402

COLLECTION = "2026-08-29-survey"


def _pages():
    try:
        from corpus import load_collection

        return load_collection(COLLECTION).pages
    except (FileNotFoundError, ImportError):
        return []


@requires_corpus
def test_every_collected_page_lays_out():
    from mayshay.cssparse.cascade import style_document
    from mayshay.cssparse.media import Viewport
    from mayshay.htmlparse.treebuilder import TreeBuilder
    from mayshay.layout.block import layout_document
    from mayshay.layout.boxtree import build_box_tree

    pages = _pages()
    if not pages:
        pytest.skip(f"collection {COLLECTION} not on disk")

    viewport = Viewport(1280.0, 1024.0)
    failures = []
    for page in pages:
        try:
            document = TreeBuilder(page.html()).build()
            style_document(document, [], viewport, external_css=page.external_css())
            root, _ = build_box_tree(document)
            layout_document(root, viewport)
        except Exception as exc:  # noqa: BLE001 -- any raise is the failure
            failures.append(f"{page.slug}: {type(exc).__name__}: {str(exc)[:120]}")

    assert not failures, (
        f"{len(failures)} of {len(pages)} collected pages do not lay out:\n  "
        + "\n  ".join(failures)
    )
