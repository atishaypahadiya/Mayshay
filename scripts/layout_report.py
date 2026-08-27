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

from collections import Counter  # noqa: E402

from corpus import load_pages  # noqa: E402
from mayshay import metrics as metrics_module  # noqa: E402
from mayshay.cssparse.cascade import style_document  # noqa: E402
from mayshay.cssparse.media import Viewport  # noqa: E402
from mayshay.htmlparse.treebuilder import TreeBuilder  # noqa: E402
from mayshay.cssparse.values import Percent  # noqa: E402
from mayshay.layout.block import layout_document  # noqa: E402
from mayshay.layout.boxtree import build_box_tree  # noqa: E402

DEFAULT_OUT = ROOT / "data" / "metrics" / "stages.csv"


def collapse_census(root):
    """How many of each margin-collapsing shape the corpus actually contains.

    This exists because the synthetic tests cannot claim coverage of
    anything and the corpus cannot claim coverage of these rules. Task B
    measured 28 anonymous-box sites in 8,593 elements and would have passed
    any implementation; this puts the same kind of number on section
    8.3.1's cases so the gap is explicit rather than hoped over.

    **Populations, named.** Every count below is over the boxes this layout
    actually produced, after `display: none` pruning, at the viewport the
    caller passed. Two different denominators are in play and they are not
    interchangeable:

    * `census_sibling_pairs` -- *ordered pairs* of adjacent in-flow
      block-level siblings. This is the population for the sibling rule, and
      it is one smaller than the sibling count per parent.
    * `census_parent_child_sites` -- block boxes with at least one in-flow
      block-level child. This is the population for the parent/first-child
      and parent/last-child rules.

    The sign breakdown is over pairs where *both* margins are non-zero,
    because a pair with a zero operand cannot distinguish `max()` from
    `sum()` and counting it as a sign case would overstate the coverage.
    """
    census = Counter()
    for key in (
        "census_sibling_pairs",
        "census_sibling_pairs_both_margins_nonzero",
        "census_sibling_pairs_both_positive",
        "census_sibling_pairs_both_negative",
        "census_sibling_pairs_mixed_sign",
        "census_parent_child_sites",
        "census_collapse_through_boxes",
        "census_zero_height_but_not_collapsed_through",
        "census_collapse_through_chains_of_two_or_more",
        "census_percentage_vertical_margins",
        "census_negative_vertical_margins",
    ):
        census[key] = 0
    if root is None:
        return census

    for box in root.walk():
        geo = box.geometry
        if geo is None:
            continue
        if geo.used_margin.top < 0 or geo.used_margin.bottom < 0:
            census["census_negative_vertical_margins"] += 1
        style = box.node.computed_style if box.origin == "element" and box.node else None
        if style is not None and (
            isinstance(style.margin_top, Percent)
            or isinstance(style.margin_bottom, Percent)
        ):
            census["census_percentage_vertical_margins"] += 1

        laid_out_children = [c for c in box.children if c.geometry is not None]
        if laid_out_children:
            census["census_parent_child_sites"] += 1
        run = 0
        for index, child in enumerate(laid_out_children):
            if child.geometry.collapsed_through:
                census["census_collapse_through_boxes"] += 1
                run += 1
                if run == 2:
                    census["census_collapse_through_chains_of_two_or_more"] += 1
            else:
                run = 0
            if (
                child.geometry.border.height == 0.0
                and not child.children
                and not child.geometry.collapsed_through
            ):
                # Same shape from the outside, opposite meaning. Counted
                # separately because a census that inferred collapse-through
                # from "zero height and empty" reported 78 where the layout
                # had decided 58, and the 20 are boxes a barrier stopped.
                census["census_zero_height_but_not_collapsed_through"] += 1
            if index == 0:
                continue
            census["census_sibling_pairs"] += 1
            above = laid_out_children[index - 1].geometry.used_margin.bottom
            below = child.geometry.used_margin.top
            if above and below:
                census["census_sibling_pairs_both_margins_nonzero"] += 1
                if above > 0 and below > 0:
                    census["census_sibling_pairs_both_positive"] += 1
                elif above < 0 and below < 0:
                    census["census_sibling_pairs_both_negative"] += 1
                else:
                    census["census_sibling_pairs_mixed_sign"] += 1
    return census

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

# Task C. Each line names the population it counts, because more than one
# correct denominator exists for most of them -- see `collapse_census`.
LAYOUT_HEADLINE = (
    ("widths_resolved", "block-level boxes laid out"),
    ("widths_deferred_shrink_to_fit", "inline-block/float/abs: needs Task D"),
    ("widths_not_applicable_inline_level", "inline-level boxes: no own width"),
    ("widths_deferred_other", "boxes fitting none of the three: must be 0"),
    ("heights_from_children", "auto heights resolved from in-flow children"),
    ("heights_deferred_inline_content", "auto heights waiting on line boxes"),
    ("heights_percentage_fallback_auto", "% heights against an auto parent"),
    ("margins_collapsed", "collapse events between adjoining groups"),
    ("margins_collapsed_through_empty", "boxes that collapsed through"),
    ("margin_collapse_blocked_padding_top", "blocked: padding-top"),
    ("margin_collapse_blocked_border_top", "blocked: border-top"),
    ("margin_collapse_blocked_padding_bottom", "blocked: padding-bottom"),
    ("margin_collapse_blocked_border_bottom", "blocked: border-bottom"),
    ("margin_collapse_blocked_parent_height", "blocked: non-auto height"),
    ("margin_collapse_blocked_new_formatting_context", "blocked: new BFC"),
    ("margin_collapse_blocked_line_box", "blocked: in-flow line boxes"),
    ("margin_collapse_blocked_out_of_flow", "blocked: float or absolute"),
    ("margin_collapse_blocked_root", "blocked: the root element"),
    ("width_margins_centred", "margin: auto on both sides"),
    ("width_margin_left_auto", "one auto margin, on the left"),
    ("width_margin_right_auto", "one auto margin, on the right"),
    ("width_over_constrained_margin_right_ignored", "over-constrained"),
    ("width_clamped_to_zero", "widths that could not be honoured"),
    ("box_sizing_border_box", "border-box widths"),
    ("layout_float_skipped", "floats: not implemented"),
    ("layout_absolute_skipped", "absolute/fixed: not implemented"),
    ("layout_position_relative_unoffset", "relative: laid out unoffset"),
    ("layout_inner_fallback_block", "flex/table laid out as block flow"),
    ("layout_table_box_margins_applied", "margins a browser drops (17.6)"),
    ("layout_viewport_unit_unresolved", "vw/vh the cascade left symbolic"),
)

CENSUS = (
    ("census_sibling_pairs", "adjacent in-flow block sibling PAIRS"),
    ("census_sibling_pairs_both_margins_nonzero", "...with both margins non-zero"),
    ("census_sibling_pairs_both_positive", "...both positive"),
    ("census_sibling_pairs_both_negative", "...both negative"),
    ("census_sibling_pairs_mixed_sign", "...mixed sign (the sum case)"),
    ("census_parent_child_sites", "boxes with an in-flow block child"),
    ("census_collapse_through_boxes", "boxes that collapsed through"),
    ("census_zero_height_but_not_collapsed_through",
     "zero-height and empty, but a barrier stopped it"),
    ("census_collapse_through_chains_of_two_or_more", "chains of two or more"),
    ("census_percentage_vertical_margins", "boxes with a % vertical margin"),
    ("census_negative_vertical_margins", "boxes with a negative vertical margin"),
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
        counters.update(layout_document(root, viewport))
        counters.update(collapse_census(root))

        boxes = sum(1 for _ in root.walk()) if root else 0
        counters["boxes_total"] = boxes
        print(f"{page.slug}   {boxes:,} boxes")
        for key, population in HEADLINE:
            print(f"    {counters.get(key, 0):>7}  {population}")
        hidden = counters["boxes_pruned_total"]
        dom = counters["dom_elements"]
        print(f"    {100 * hidden / dom:>6.1f}%  of DOM elements produce no box")
        print("  block layout")
        for key, population in LAYOUT_HEADLINE:
            print(f"    {counters.get(key, 0):>7}  {population}")
        print("  margin-collapsing census")
        for key, population in CENSUS:
            print(f"    {counters.get(key, 0):>7}  {population}")
        print()

        for key, value in counters.items():
            totals[key] = totals.get(key, 0) + value
        if not args.dry_run:
            rows += metrics_module.emit(
                "layout", counters,
                source=str(page.html_path.relative_to(ROOT)),
                run_id=run_id, path=args.out,
            )

    print("all pages")
    for key, population in HEADLINE + LAYOUT_HEADLINE + CENSUS:
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
