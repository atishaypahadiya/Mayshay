#!/usr/bin/env python3
"""Run the whole pipeline over the saved corpus and write the metrics.

    .venv/bin/python scripts/style_report.py
    .venv/bin/python scripts/style_report.py --out /tmp/stages.csv
    .venv/bin/python scripts/style_report.py news.ycombinator.com --dry-run

This is `mayshay.metrics`'s first real caller, and the thing that makes
CLAUDE.md's "every stage emits timing + size metrics to data/metrics/" true
engine-side rather than aspirationally. It is a *driver*: the library stages
build `Counter`s and hand them back, and this script is the one place that
turns them into rows on disk. `Tokenizer`, `TreeBuilder` and `style_document`
all deliberately refuse to write anything themselves -- see the note at the
top of `mayshay/metrics.py`.

Three stages are emitted per document, sharing one `run_id` so a later query
can join them:

    tokenize   -- the HTML tokenizer's own counters, plus the source size
    treebuild  -- the tree builder's counters, including its parse errors
    cssparse   -- `style_document`'s counters, including cascade timing,
                  plus the external CSS byte total from the manifest

Pages and their stylesheets come from `scripts/corpus.py`, which reads each
page's `manifest.json`. Before `scripts/collect.py` existed this script ran
on bare `.html` files with `author_css=[]`, so every external sheet was
missing; see docs/corpus.md for what changed and why the older figures must
not be mixed with these.

`--out` is passed through to `metrics.emit` explicitly. That is not
politeness: `metrics.METRICS_DIR` is derived from `__file__` and is only
repo-relative under an editable install, and Phase 1 lost a day to exactly
that pointer being repointed. A driver that knows where the repo is should
say so.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

sys.path.insert(0, str(ROOT / "scripts"))

from corpus import CorpusPage, load_pages  # noqa: E402
from mayshay import metrics as metrics_module  # noqa: E402
from mayshay.cssparse.cascade import style_document  # noqa: E402
from mayshay.cssparse.media import Viewport  # noqa: E402
from mayshay.htmlparse.treebuilder import TreeBuilder  # noqa: E402

CORPUS = ROOT / "data" / "corpus"
DEFAULT_OUT = ROOT / "data" / "metrics" / "stages.csv"

# The keys worth putting on stdout. The CSV keeps everything; a human
# reading a three-page report wants the headline, and
# `link_stylesheets_skipped` is the number this phase exists to produce.
HEADLINE = (
    ("treebuild", "elements"),
    ("treebuild", "parse_errors"),
    ("treebuild", "parse_time_ms"),
    ("cssparse", "nodes_styled"),
    ("cssparse", "rules_total"),
    ("cssparse", "declarations_kept"),
    ("cssparse", "declarations_dropped"),
    ("cssparse", "style_elements"),
    ("cssparse", "inline_style_attributes"),
    ("cssparse", "author_stylesheets"),
    ("cssparse", "link_stylesheets_skipped"),
    ("cssparse", "external_css_bytes"),
    ("cssparse", "at_rules_skipped"),
    ("cssparse", "media_blocks_matched"),
    ("cssparse", "media_queries_unsupported"),
    ("cssparse", "cascade_time_ms"),
)


def run_page(page: CorpusPage, viewport: Viewport | None) -> dict[str, dict]:
    """Parse and style one collected page. Returns {stage: counters}.

    The page's external stylesheets come from its manifest via
    `corpus.load_pages` and are passed in as `author_css`.

    `link_stylesheets_skipped` does NOT drop to zero as a result, and that
    is correct: it counts `<link rel=stylesheet>` elements that
    `style_document` itself did not fetch, and `style_document` still
    fetches nothing -- the driver supplies the sheets instead. Read it
    against `author_stylesheets`: when the two agree, every linked sheet
    was supplied from disk. When `author_stylesheets` is lower, something
    in `missing_sheets` says why.
    """
    source = page.html()

    builder = TreeBuilder(source)
    document = builder.build()

    tokenize = builder.tokenizer.metrics.copy()
    # The size half of "timing + size". Bytes on disk, not len(source):
    # the two differ on any page with non-ASCII, and bytes is what a
    # network stage will eventually report.
    tokenize["source_bytes"] = page.html_bytes
    tokenize["source_chars"] = len(source)

    cssparse = style_document(document, page.author_css(), viewport)
    # Recorded alongside the cascade's own counters because "how much CSS
    # does this page ship" is a headline number for the analysis half, and
    # it is not derivable from anything else in the row set.
    cssparse["external_css_bytes"] = page.css_bytes
    cssparse["external_stylesheets_missing"] = len(page.missing_sheets)
    # The viewport goes into the row set because `@media` evaluation makes
    # every cssparse counter viewport-dependent. A `flex` count with no
    # viewport beside it is not a reproducible number.
    cssparse["viewport_width_px"] = viewport.width_px if viewport else 0
    cssparse["viewport_height_px"] = viewport.height_px if viewport else 0

    return {
        "tokenize": tokenize,
        "treebuild": builder.metrics.copy(),
        "cssparse": cssparse,
    }


def report(page: CorpusPage, stages: dict[str, dict]) -> str:
    lines = [
        f"{page.slug}  ({page.html_bytes:,} bytes html, "
        f"{page.css_bytes:,} bytes css in {len(page.sheets)} sheet(s))"
    ]
    for sheet in page.missing_sheets:
        lines.append(f"    ! sheet not fetched ({sheet['status']}): {sheet['href'][:70]}")
    for stage, key in HEADLINE:
        lines.append(f"    {stage:<10} {key:<26} {stages[stage].get(key, 0)}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "pages", nargs="*",
        help="page slugs to run; defaults to every collected page",
    )
    parser.add_argument(
        "--out", type=Path, default=DEFAULT_OUT,
        help=f"metrics CSV to append to (default: {DEFAULT_OUT})",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="print the report but write nothing",
    )
    parser.add_argument(
        "--viewport", default="1280x1024",
        help="viewport for @media evaluation, or 'none' to skip at-rules "
             "the way Phase 2 did (default: 1280x1024)",
    )
    args = parser.parse_args(argv)

    if args.viewport.lower() == "none":
        viewport = None
    else:
        width, _, height = args.viewport.lower().partition("x")
        viewport = Viewport(float(width), float(height))

    pages = load_pages()
    if args.pages:
        wanted = set(args.pages)
        pages = [p for p in pages if p.slug in wanted]
    if not pages:
        print(
            f"no collected pages in {CORPUS} -- run scripts/collect.py first "
            f"(see docs/corpus.md)",
            file=sys.stderr,
        )
        return 1

    # One run_id for the whole sweep: the rows for tokenize, treebuild and
    # cssparse across all three pages belong to one execution of the
    # pipeline, and joining them later is the point of having it.
    run_id = metrics_module.new_run_id()
    print(f"run_id {run_id}   viewport "
          f"{args.viewport if viewport else 'none (at-rules skipped)'}")

    rows = 0
    for page in pages:
        stages = run_page(page, viewport)
        print(report(page, stages))
        if args.dry_run:
            continue
        for stage, counters in stages.items():
            rows += metrics_module.emit(
                stage,
                counters,
                source=str(page.html_path.relative_to(ROOT)),
                run_id=run_id,
                path=args.out,
            )

    if args.dry_run:
        print("\ndry run: nothing written")
    else:
        print(f"\n{rows} rows -> {args.out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
