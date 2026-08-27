#!/usr/bin/env python3
"""Census of computed `display` values across the collected corpus.

    .venv/bin/python scripts/display_report.py
    .venv/bin/python scripts/display_report.py --viewport 375x812

This is the measurement that decides Phase 3's scope. If `flex` and `grid`
turn out to carry most of the boxes on real pages, a block-and-inline layout
engine will not render them, and that is worth knowing before the phase is
planned rather than after.

Three columns are printed per page, and the differences between them are
the point:

    ua      what the UA stylesheet alone computes -- what this project
            measured for all of Phase 1 and Phase 2, because no external
            stylesheet had ever been fetched
    ext     the same page with its `<link>`ed sheets supplied from the
            manifest, plus its `<style>` blocks and `style=` attributes,
            but with every at-rule still skipped
    media   the same again, with `@media` evaluated at the viewport

A value that appears only in a later column is a layout mode the engine
would never have known it needed. The `ua -> ext` step is what
`scripts/collect.py` bought; the `ext -> media` step is what Phase 3 Task A
bought.

**The `media` column is still a lower bound.** `@supports` is counted and
skipped, as is any `@media` whose query names a feature outside
`cssparse/media.py`'s scope. Both are printed per page rather than left
implicit.

Counts are over Elements only -- one row per element, not per node -- so
they are comparable with `treebuild.elements`.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src"), str(ROOT / "scripts")]

from corpus import CorpusPage, load_pages  # noqa: E402
from mayshay.cssparse.cascade import style_document  # noqa: E402
from mayshay.cssparse.media import Viewport  # noqa: E402
from mayshay.dom.node import Element  # noqa: E402
from mayshay.htmlparse.treebuilder import TreeBuilder  # noqa: E402


def display_counts(
    page: CorpusPage, author_css: list[str], viewport=None
) -> tuple[Counter, int, Counter]:
    """Returns (display -> element count, total elements, cascade metrics).

    The document is rebuilt for each run rather than restyled in place:
    `style_document` writes `computed_style` onto every node, and reusing a
    tree would silently measure the second cascade against the first one's
    leftovers.
    """
    document = TreeBuilder(page.html()).build()
    metrics = style_document(document, author_css, viewport)

    counts: Counter[str] = Counter()
    total = 0
    stack = list(document.children)
    while stack:
        node = stack.pop()
        stack.extend(node.children)
        if not isinstance(node, Element):
            continue
        total += 1
        style = node.computed_style
        counts[getattr(style, "display", "?") if style else "?"] += 1
    return counts, total, metrics


def render(
    page: CorpusPage,
    ua: Counter,
    ext: Counter,
    med: Counter,
    total: int,
    metrics: Counter,
) -> str:
    lines = [
        f"{page.slug}",
        f"  {page.source_url}  fetched {page.fetched_at}",
        f"  {page.html_bytes:,} B html   "
        f"{page.css_bytes:,} B external css in {len(page.sheets)} sheet(s)",
    ]
    for sheet in page.missing_sheets:
        lines.append(f"  ! not fetched ({sheet['status']}): {sheet['href'][:64]}")
    for sheet in page.unapplied_sheets:
        why = "duplicate" if sheet["duplicate_of"] else "alternate"
        lines.append(f"  - collected but not applied ({why}): {sheet['href'][:56]}")
    if page.imports_skipped:
        lines.append(f"  - @import beyond depth 1, not fetched: {len(page.imports_skipped)}")

    skipped = metrics.get("at_rules_skipped", 0)
    if skipped:
        lines.append(
            f"  ! {skipped} at-rules still skipped (mostly @supports) -- the "
            f"counts below remain a lower bound"
        )
    unsupported = metrics.get("media_queries_unsupported", 0)
    if unsupported:
        names = sorted(
            (k[len("media_feature_"):], v)
            for k, v in metrics.items()
            if k.startswith("media_feature_")
        )
        detail = ", ".join(f"{n} x{v}" for n, v in names)
        lines.append(f"  ! {unsupported} @media queries not evaluated: {detail}")
    if metrics.get("media_types_skipped"):
        types = sorted(
            k[len("media_type_"):] for k in metrics if k.startswith("media_type_")
        )
        lines.append(
            f"  - {metrics['media_types_skipped']} queries for other media "
            f"types: {', '.join(types)}"
        )
    lines.append(
        f"  @media blocks: {metrics.get('media_blocks_matched', 0)} matched, "
        f"{metrics.get('media_blocks_not_matched', 0)} did not match at this viewport"
    )
    lines.append(
        f"  {total:,} elements   {metrics.get('style_elements', 0)} <style>   "
        f"{metrics.get('inline_style_attributes', 0)} style=   "
        f"{metrics.get('rules_total', 0)} rules cascaded"
    )
    lines.append(f"    {'display':<16}{'ua':>8}{'ext':>8}{'media':>8}{'share':>9}")
    for value in sorted(set(ua) | set(ext) | set(med), key=lambda v: -med.get(v, 0)):
        a, b, c = ua.get(value, 0), ext.get(value, 0), med.get(value, 0)
        mark = ""
        if a == 0 and b == 0 and c:
            mark = "  <- @media only"
        elif a == 0 and b:
            mark = "  <- author CSS only"
        share = 100 * c / total if total else 0
        lines.append(f"    {value:<16}{a:>8}{b:>8}{c:>8}{share:>8.1f}%{mark}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("pages", nargs="*", help="page slugs; default all")
    parser.add_argument(
        "--viewport", default="1280x1024",
        help="viewport for @media evaluation (default: 1280x1024)",
    )
    args = parser.parse_args(argv)
    width, _, height = args.viewport.lower().partition("x")
    viewport = Viewport(float(width), float(height))

    pages = load_pages()
    if args.pages:
        wanted = set(args.pages)
        pages = [p for p in pages if p.slug in wanted]
    if not pages:
        print("no collected pages -- run scripts/collect.py (see docs/corpus.md)",
              file=sys.stderr)
        return 1

    totals_ua: Counter[str] = Counter()
    totals_ext: Counter[str] = Counter()
    totals_med: Counter[str] = Counter()
    grand = 0
    css_total = 0

    print(f"viewport {viewport.width_px:.0f}x{viewport.height_px:.0f} "
          f"({viewport.orientation})\n")

    for page in pages:
        ua, total, _ = display_counts(page, [])
        ext, _, _ = display_counts(page, page.author_css())
        med, _, metrics = display_counts(page, page.author_css(), viewport)
        print(render(page, ua, ext, med, total, metrics))
        print()
        totals_ua += ua
        totals_ext += ext
        totals_med += med
        grand += total
        css_total += page.css_bytes

    print(f"all pages: {grand:,} elements, {css_total:,} B external css")
    print(f"  {'display':<16}{'ua':>8}{'ext':>8}{'media':>8}{'share':>9}")
    for value, count in totals_med.most_common():
        print(f"  {value:<16}{totals_ua.get(value, 0):>8}{totals_ext.get(value, 0):>8}"
              f"{count:>8}{100 * count / grand:>8.1f}%")
    flex = sum(c for v, c in totals_med.items() if "flex" in v)
    grid = sum(c for v, c in totals_med.items() if "grid" in v)
    print(f"\n  flex family: {flex} ({100*flex/grand:.2f}%)   "
          f"grid family: {grid} ({100*grid/grand:.2f}%)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
