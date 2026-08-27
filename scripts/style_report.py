#!/usr/bin/env python3
"""Run the whole pipeline over the saved corpus and write the metrics.

    .venv/bin/python scripts/style_report.py
    .venv/bin/python scripts/style_report.py --out /tmp/stages.csv
    .venv/bin/python scripts/style_report.py data/corpus/hn.html --dry-run

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
    cssparse   -- `style_document`'s counters, including cascade timing and
                  `link_stylesheets_skipped`

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

from mayshay import metrics as metrics_module  # noqa: E402
from mayshay.cssparse.cascade import style_document  # noqa: E402
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
    ("cssparse", "link_stylesheets_skipped"),
    ("cssparse", "cascade_time_ms"),
)


def corpus_pages() -> list[Path]:
    """Every saved page, smallest first, so a failure on the 791KB one is
    not the first thing that happens."""
    return sorted(CORPUS.glob("*.html"), key=lambda p: p.stat().st_size)


def run_page(path: Path) -> dict[str, dict]:
    """Parse and style one page. Returns {stage: counters}.

    Read with `errors="replace"`: a saved page can carry bytes that are not
    valid UTF-8, and the tokenizer's own U+FFFD handling is the right place
    for that to surface, not a traceback here.
    """
    source = path.read_text(encoding="utf-8", errors="replace")

    builder = TreeBuilder(source)
    document = builder.build()

    tokenize = builder.tokenizer.metrics.copy()
    # The size half of "timing + size". Bytes on disk, not len(source):
    # the two differ on any page with non-ASCII, and bytes is what a
    # network stage will eventually report.
    tokenize["source_bytes"] = path.stat().st_size
    tokenize["source_chars"] = len(source)

    cssparse = style_document(document, [])

    return {
        "tokenize": tokenize,
        "treebuild": builder.metrics.copy(),
        "cssparse": cssparse,
    }


def report(path: Path, stages: dict[str, dict]) -> str:
    lines = [f"{path.name}  ({path.stat().st_size:,} bytes)"]
    for stage, key in HEADLINE:
        lines.append(f"    {stage:<10} {key:<26} {stages[stage].get(key, 0)}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "pages", nargs="*", type=Path,
        help="pages to run; defaults to every .html in data/corpus/",
    )
    parser.add_argument(
        "--out", type=Path, default=DEFAULT_OUT,
        help=f"metrics CSV to append to (default: {DEFAULT_OUT})",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="print the report but write nothing",
    )
    args = parser.parse_args(argv)

    pages = args.pages or corpus_pages()
    if not pages:
        print(f"no pages found in {CORPUS}", file=sys.stderr)
        return 1

    # One run_id for the whole sweep: the rows for tokenize, treebuild and
    # cssparse across all three pages belong to one execution of the
    # pipeline, and joining them later is the point of having it.
    run_id = metrics_module.new_run_id()
    print(f"run_id {run_id}")

    rows = 0
    for path in pages:
        stages = run_page(path)
        print(report(path, stages))
        if args.dry_run:
            continue
        for stage, counters in stages.items():
            rows += metrics_module.emit(
                stage,
                counters,
                source=str(path.relative_to(ROOT)),
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
