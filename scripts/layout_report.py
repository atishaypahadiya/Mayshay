#!/usr/bin/env python3
"""Build the box tree over the corpus and emit the `layout` stage.

    .venv/bin/python scripts/layout_report.py
    .venv/bin/python scripts/layout_report.py --viewport 375x812 --dry-run

A driver, in the shape of `display_report.py`: `build_box_tree` returns a
`Counter` and this script is the only thing that turns it into rows. See the
note at the top of `mayshay/metrics.py`.

**The corpus is a smoke test here, not evidence.** It contains 28 mixed
block/inline containers and 34 inline-containing-block sites across 8,593
elements, so it exercises almost none of the anonymous-box machinery. The
tests in `tests/layout/test_boxtree.py` are synthetic for that reason. What
this script is good for is the census, the pruning figures, and catching a
crash on real markup.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src"), str(ROOT / "scripts")]

from corpus import load_pages  # noqa: E402
from mayshay import metrics as metrics_module  # noqa: E402
from mayshay.cssparse.cascade import style_document  # noqa: E402
from mayshay.cssparse.media import Viewport  # noqa: E402
from mayshay.htmlparse.treebuilder import TreeBuilder  # noqa: E402
from mayshay.layout.boxtree import build_box_tree  # noqa: E402

DEFAULT_OUT = ROOT / "data" / "metrics" / "stages.csv"

# Every number here needs its population named, which is why these are
# spelled out rather than printed as a bare dict. Three different correct
# answers exist for "how many elements are hidden", and the census figure is
# not the root count.
HEADLINE = (
    ("dom_elements", "elements in the DOM, including hidden ones"),
    ("boxes_element", "elements that produced a box"),
    ("boxes_pruned_roots", "display:none pruning roots"),
    ("boxes_pruned_total", "elements below a pruning root, inclusive"),
    ("boxes_text", "text nodes that produced a box"),
    ("boxes_blank_text_discarded", "blank text runs between blocks, dropped"),
    ("boxes_anonymous", "anonymous blocks generated"),
    ("boxes_inline_split", "inlines split around a block, yielding fragments"),
    ("boxes_inline_fragments", "fragments those splits produced"),
    ("boxes_inline_dissolved", "inlines with only block children: no box at all"),
    ("boxes_grid_fallback", "grid laid out as block"),
    ("boxes_unstyled_skipped", "elements with no computed style"),
)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("pages", nargs="*", help="page slugs; default all")
    ap.add_argument("--viewport", default="1280x1024")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    width, _, height = args.viewport.lower().partition("x")
    viewport = Viewport(float(width), float(height))

    pages = load_pages()
    if args.pages:
        pages = [p for p in pages if p.slug in set(args.pages)]
    if not pages:
        print("no collected pages -- run scripts/collect.py (see docs/corpus.md)",
              file=sys.stderr)
        return 1

    run_id = metrics_module.new_run_id()
    print(f"run_id {run_id}   viewport {args.viewport}\n")
    rows = 0
    totals: dict[str, int] = {}

    for page in pages:
        document = TreeBuilder(page.html()).build()
        style_document(document, [], viewport, external_css=page.external_css())
        root, counters = build_box_tree(document)

        boxes = sum(1 for _ in root.walk()) if root else 0
        counters["boxes_total"] = boxes
        print(f"{page.slug}   {boxes:,} boxes")
        for key, population in HEADLINE:
            print(f"    {counters.get(key, 0):>7}  {population}")
        hidden = counters["boxes_pruned_total"]
        dom = counters["dom_elements"]
        print(f"    {100 * hidden / dom:>6.1f}%  of DOM elements produce no box\n")

        for key, value in counters.items():
            totals[key] = totals.get(key, 0) + value
        if not args.dry_run:
            rows += metrics_module.emit(
                "layout", counters,
                source=str(page.html_path.relative_to(ROOT)),
                run_id=run_id, path=args.out,
            )

    print("all pages")
    for key, population in HEADLINE:
        print(f"    {totals.get(key, 0):>7}  {population}")
    print(f"    {100 * totals['boxes_pruned_total'] / totals['dom_elements']:>6.1f}%  "
          f"of DOM elements produce no box")

    if args.dry_run:
        print("\ndry run: nothing written")
    else:
        print(f"\n{rows} rows -> {args.out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
