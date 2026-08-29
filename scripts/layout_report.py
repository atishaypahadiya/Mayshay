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
    ("widths_shrink_to_fit_resolved", "inline-block/float/abs: 10.3.5 applied"),
    ("widths_shrink_to_fit_specified", "...of those, width was not auto"),
    ("widths_deferred_shrink_to_fit", "shrink-to-fit still deferred: must be 0"),
    ("widths_not_applicable_inline_level", "inline-level boxes: no own width"),
    ("widths_deferred_other", "boxes fitting none of the three: must be 0"),
    ("heights_from_children", "auto heights resolved from in-flow children"),
    ("heights_from_line_boxes", "auto heights resolved from line boxes"),
    ("heights_deferred_inline_content", "auto heights still waiting: must be 0"),
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
    ("layout_inner_fallback_block", "flex laid out as block flow"),
    ("layout_viewport_unit_unresolved", "vw/vh the cascade left symbolic"),
)

# Task E. Three populations again, and the first two are the ones a reader
# will confuse:
#
#   table_wrapper_boxes    every `display: table` box in the tree, INCLUDING
#                          the anonymous tables section 17.2.1 generates
#   tables_laid_out        of those, the ones that reached the width
#                          algorithm -- the rest are inside float or
#                          absolutely positioned subtrees this engine
#                          declines to lay out
#   table_cells_placed     cells inside those, which is smaller than the
#                          `table-cell` display census for the same reason
#
# The fixup block below is the one worth reading closely. Every rule of
# section 17.2.1 is at four or below on this corpus; the structure it has
# in bulk is `table_rows_directly_in_a_table`, which needs NO fixup at all
# and is listed here as the denominator those rules are small against.
TABLE_HEADLINE = (
    ("table_wrapper_boxes", "TABLE BOXES in the tree, anonymous ones included"),
    ("tables_laid_out", "...of those, laid out (the population below)"),
    ("table_columns", "columns across those tables"),
    ("table_cells_placed", "CELLS placed in a grid (a second population)"),
    ("table_cells_spanning_columns", "...with colspan > 1"),
    ("table_cells_spanning_rows", "...with rowspan > 1"),
    ("table_colspan_excess_distributed", "......that widened their columns"),
    ("table_colspan_absorbed_without_widening", "......that did not"),
    ("table_rows_laid_out", "rows"),
    ("table_row_groups_laid_out", "row groups"),
    ("table_captions_before", "captions above the table box (17.4)"),
    ("table_captions_after", "...and below it"),
    ("table_layout_automatic", "tables under 17.5.2.2's automatic algorithm"),
    ("table_layout_fixed", "...under 17.5.2.1's fixed algorithm"),
    ("table_layout_fixed_fallback_auto_width", "...fixed, but width: auto"),
    ("table_width_specified", "tables with a non-auto width"),
    ("table_width_percentage_of_containing_block", "...of those, a percentage"),
    ("table_width_auto_shrink_to_fit", "tables shrink-to-fit"),
    ("table_width_raised_to_min_content", "...raised to their min-content"),
    ("table_extra_width_distributed", "tables with extra width to share out"),
    ("table_width_remainder_to_margin_right", "...remainder to margin-right"),
    # Section 17.2.1, one row per rule, in the spec's own order.
    ("table_rows_directly_in_a_table", "rows parented by a table: NO fixup (17.2.1)"),
    ("table_fixup_removed_child_of_column", "removed: a column's children"),
    ("table_fixup_removed_non_column_in_column_group",
     "removed: a non-column in a column group"),
    ("table_fixup_removed_white_space_between_table_boxes",
     "removed: white space between table boxes (Task B takes it first)"),
    ("table_fixup_anonymous_row_in_table", "anonymous row in a table"),
    ("table_fixup_anonymous_row_in_row_group", "anonymous row in a row group"),
    ("table_fixup_anonymous_cell_in_row", "anonymous cell in a row"),
    ("table_fixup_anonymous_row_for_orphan_cell", "anonymous row for an orphan cell"),
    ("table_fixup_anonymous_table_for_misparented_row",
     "anonymous table for a misparented row"),
    ("table_fixup_anonymous_table_for_misparented_column", "...a column"),
    ("table_fixup_anonymous_table_for_misparented_row_group", "...a row group"),
    ("table_fixup_anonymous_table_for_misparented_column_group",
     "...a column group"),
    ("table_fixup_anonymous_table_for_misparented_caption", "...a caption"),
    ("table_fixup_anonymous_inline_table", "...as an inline-table"),
    # Counted, not implemented.
    ("table_border_collapse_requested", "border-collapse: collapse, not done"),
    ("table_column_box_width_ignored", "<col> widths ignored"),
    ("table_rowspan_height_not_distributed", "rowspan heights not distributed"),
    ("table_cell_vertical_align_top", "cells aligned top: no divergence"),
    ("table_cell_baseline_aligned_as_top", "...baseline, laid out as top"),
    ("table_cell_vertical_align_other_as_top",
     "...middle/bottom as top: must be 0"),
    ("table_cell_percentage_width_as_auto", "% cell widths treated as auto"),
    ("table_internal_margin_dropped", "non-zero margins dropped (17.5)"),
    ("table_internal_margin_declared_zero", "...margins declared but zero"),
    ("table_overlapping_grid_slot", "overlapping grid slots: undefined in 17.5"),
)

# Task D1. Three populations sit in this block and they are NOT the same
# denominator, which is the whole point of naming each one:
#
#   text_boxes_seen              text boxes surviving Task B's pruning and
#                                blank-run discarding  -- 6,194
#   text_boxes_whitespace_only   of those, the ones made only of CSS Text 3
#                                white space           -- 1,287
#   text_chars_in                characters in those boxes -- 80,580
#
# The DOM figures are larger and different: 7,985 text nodes and 117,378
# characters, of which 2,781 nodes are blank under `str.strip()`. 1,458 of
# those never reach a box at all, so the disposition below decides the fate
# of 1,287, not of 2,781.
TEXT_HEADLINE = (
    ("text_ifc_contexts", "inline formatting contexts"),
    ("text_boxes_seen", "TEXT BOXES processed (the population below)"),
    ("text_boxes_content", "...with at least one non-white-space character"),
    ("text_boxes_whitespace_only", "...made only of CSS white space"),
    ("text_whitespace_collapsed_away", "......collapsed away entirely"),
    ("text_whitespace_single_space", "......kept as one separating space"),
    ("text_whitespace_preserved_verbatim", "......preserved verbatim (pre*)"),
    ("text_whitespace_preserved_break", "......kept as a forced break"),
    ("text_whitespace_other", "......none of the above: must be 0"),
    ("text_chars_in", "CHARACTERS in those boxes (a second population)"),
    ("text_chars_kept", "...copied through unchanged"),
    ("text_chars_transformed", "...rewritten (tab/newline -> space)"),
    ("text_chars_removed", "...removed"),
    ("text_whitespace_trimmed_ifc_start", "......at the start of a context"),
    ("text_whitespace_trimmed_ifc_end", "......at the end of a context"),
    ("text_whitespace_collapsed_into_previous", "......into a previous space"),
    ("text_whitespace_removed_around_segment_break", "......around a break"),
    ("text_boxes_white_space_normal", "text boxes under white-space: normal"),
    ("text_boxes_white_space_nowrap", "...nowrap"),
    ("text_boxes_white_space_pre_wrap", "...pre-wrap"),
    ("text_boxes_white_space_pre", "...pre"),
    ("text_boxes_white_space_pre_line", "...pre-line"),
    ("text_boxes_white_space_break_spaces", "...break-spaces"),
    ("text_ifc_atomic_inlines", "atomic inlines opaque to collapsing"),
    ("text_ifc_replaced_transparent", "replaced/br walked through: a known gap"),
    ("text_missing_glyph", "characters with no glyph in the font"),
    ("text_preserved_tab_approximated", "preserved tabs measured at tab-size"),
    ("text_carriage_returns_normalised", "CR or CRLF normalised to LF"),
    ("intrinsic_sizes_computed", "intrinsic size computations"),
    ("intrinsic_specified_width_used", "...where a definite width short-cut it"),
    ("intrinsic_percentage_width_as_auto", "...% width treated as auto (Sizing 3)"),
    ("intrinsic_percentage_edge_as_zero", "...% margin/padding taken as zero"),
    ("intrinsic_text_collapsed_on_demand", "text not pre-collapsed: must be 0"),
    ("intrinsic_uax14_break_inside_a_run", "min-content breaks inside a word"),
)

# Task D2. Three populations again, and again they are not interchangeable:
#
#   line_ifc_contexts_laid_out   inline formatting contexts that produced at
#                                least one line box
#   line_boxes                   the line boxes themselves
#   line_fragments               one per inline box per line it appears on
#
# The `vertical_align_applied_*` rows count boxes ALIGNED ON A LINE BOX,
# which is a different and much smaller population than the element boxes
# with a computed `vertical-align` -- 30 boxes compute `top` on this corpus
# and none of them is inline-level, so the rule fires zero times. Both
# numbers are correct and a bare "vertical-align: top, 30" says neither.
LINE_HEADLINE = (
    ("line_ifc_contexts_laid_out", "inline formatting contexts laid out"),
    ("line_boxes", "LINE BOXES produced"),
    ("line_boxes_empty_zero_height", "...empty, so zero height (9.4.2)"),
    ("line_breaks_soft", "breaks taken at a soft wrap opportunity"),
    ("line_breaks_forced_segment", "breaks forced by a preserved newline"),
    ("line_breaks_forced_br", "breaks forced by <br>"),
    ("line_overflow_unbreakable", "lines overflowing: nothing to break at"),
    ("line_chars_in_fragments", "characters that reached a line box"),
    ("line_chars_not_laid_out", "...and those in a float or abs subtree"),
    ("line_subtrees_not_laid_out", "out-of-flow subtrees skipped"),
    ("line_out_of_flow_skipped", "...of those, taken off a line box"),
    ("line_fragments", "INLINE FRAGMENTS (a second population)"),
    ("line_fragments_text", "...text runs"),
    ("line_fragments_inline_box", "...inline element boxes"),
    ("line_fragments_atomic", "...atomic inlines"),
    ("line_inline_boxes_fragmented", "boxes that crossed a line break"),
    ("line_empty_inline_boxes", "inline boxes with no content of their own"),
    ("line_replaced_zero_size", "replaced elements sized zero: a known gap"),
    ("line_strut_suppressed_no_direct_text",
     "strut suppressed: a measured divergence from CSS 2.1 10.8"),
    ("line_break_opportunities_masked_nowrap", "opportunities masked by nowrap"),
    ("line_break_spaces_extra_opportunity", "extra opportunities: break-spaces"),
    ("linebreak_opportunities", "SOFT WRAP OPPORTUNITIES (a third population)"),
    ("linebreak_opportunities_at_space", "...at a space"),
    ("linebreak_opportunities_other", "...anywhere else UAX #14 allows"),
    ("linebreak_tailored_no_break_after_solidus", "Chrome tailoring: after /"),
    ("linebreak_tailored_no_break_after_exclamation", "...after !"),
    ("linebreak_tailored_no_break_after_vertical_line", "...after |"),
    ("linebreak_class_fallback_combining_mark", "combining marks (LB9)"),
    ("linebreak_class_fallback_other",
     "characters classified AL by default: must be 0"),
    ("text_line_trailing_space_trimmed", "line-end spaces trimmed (Phase II)"),
    ("text_line_trailing_space_hung", "...hung instead, under pre-wrap"),
    ("text_line_leading_space_trimmed", "line-start spaces trimmed: must be 0"),
    ("text_align_start", "lines aligned: start"),
    ("text_align_left", "...left"),
    ("text_align_center", "...center"),
    ("text_align_right", "...right"),
    ("text_align_justify_as_start", "...justify, laid out as start"),
    ("vertical_align_boxes_aligned", "BOXES ALIGNED ON A LINE (a fourth)"),
    ("vertical_align_applied_baseline", "...baseline (the initial value)"),
    ("vertical_align_applied_middle", "...middle"),
    ("vertical_align_applied_top", "...top"),
    ("vertical_align_applied_bottom", "...bottom"),
    ("vertical_align_applied_text_top", "...text-top"),
    ("vertical_align_applied_text_bottom", "...text-bottom"),
    ("vertical_align_applied_sub", "...sub"),
    ("vertical_align_applied_super", "...super"),
    ("vertical_align_applied_length", "...a <length>"),
    ("vertical_align_applied_percentage", "...a <percentage>"),
    ("vertical_align_percent_resolved_in_layout",
     "...of those, resolved here because line-height was normal"),
    ("vertical_align_top_bottom_extended_line", "top/bottom grew the line"),
    ("vertical_align_text_edge_against_empty_parent",
     "text-top/-bottom against a parent with nothing on the line"),
    ("vertical_align_atomic_baseline_from_last_line",
     "atomic inline baseline from its last line box"),
    ("vertical_align_atomic_baseline_from_margin_edge",
     "...from its bottom margin edge instead"),
    ("line_height_unit_unresolved", "vw/vh line-height the cascade left symbolic"),
)

# Task F. Three populations again, and the first two are the ones a reader
# will confuse -- the same shape as the table block above:
#
#   flex elements       233 across the corpus compute `flex` or
#                       `inline-flex`; 201 of them produce a box. Neither
#                       number is here, because neither is a layout figure.
#   flex_containers_laid_out
#                       29 -- the boxes that reached this algorithm. The
#                       other 172 sit inside a float or absolutely
#                       positioned subtree that is never laid out.
#   flex_items_placed   44 items inside those 29, which is the population
#                       every per-item row below counts against.
#
# Fifteen of the 29 hold a single item, so **14 containers on this corpus
# can discriminate anything about the main axis** -- see
# `docs/synthetic-only-coverage.md`, which carries a row per rule.
FLEX_HEADLINE = (
    ("flex_containers_laid_out", "FLEX CONTAINERS laid out (a population)"),
    ("flex_containers_row", "...row direction"),
    ("flex_containers_column", "...column direction"),
    ("flex_lines", "flex lines"),
    ("flex_lines_wrapped", "...line breaks under flex-wrap: wrap"),
    ("flex_items_placed", "FLEX ITEMS placed (a second population)"),
    ("flex_items_blockified", "...inline-level children blockified (Display 3)"),
    ("flex_anonymous_items", "anonymous items for a text run (section 4)"),
    ("flex_blank_runs_not_rendered", "...blank runs producing no item"),
    ("flex_basis_from_content", "base size from the content (intrinsic.py)"),
    ("flex_basis_from_main_size_property", "...from the width/height property"),
    ("flex_basis_definite", "...from a definite flex-basis"),
    ("flex_basis_content_keyword", "...from flex-basis: content"),
    ("flex_items_grown", "items grown by section 9.7"),
    ("flex_items_shrunk", "...shrunk"),
    ("flex_items_frozen_inflexible", "...frozen before the loop"),
    ("flex_items_clamped_to_min_content", "...stopped at their min-content (4.5)"),
    ("flex_free_space_positive", "lines with free space to distribute"),
    ("flex_free_space_negative", "...with items overflowing"),
    ("flex_free_space_exhausted", "...ending with none left"),
    ("flex_items_stretched", "items stretched to the line's cross size"),
    ("flex_items_aligned_baseline", "...aligned by baseline"),
    ("flex_items_baseline_synthesized", "......with a synthesized baseline"),
    ("flex_main_gap_applied", "gaps applied on the main axis"),
    ("flex_cross_gap_applied", "...between lines"),
    ("flex_percentage_gap_as_zero", "% gaps against an indefinite size"),
    # A count of *computations*, not of boxes: intrinsic sizing is asked
    # for repeatedly as it recurses, so 700 over 29 containers is 700
    # calls. Named here rather than left to look like a box census --
    # the unstated-denominator hazard, in the row most likely to be
    # read as one.
    ("intrinsic_flex_row_summed",
     "row containers summed for an intrinsic size (CALLS, not boxes)"),
    # Counted, not implemented. Every one of these is 0 on this corpus,
    # which is the point of printing them: the divergence is a number.
    ("flex_order_ignored", "order ignored: items in document order"),
    ("flex_align_content_ignored", "align-content ignored where it could act"),
    ("flex_direction_reverse_as_forward", "row/column-reverse laid out forwards"),
    ("flex_wrap_reverse_as_wrap", "wrap-reverse stacked forwards"),
    ("flex_wrap_without_definite_main_size", "wrap with no definite main size"),
    ("flex_item_auto_margin_zeroed", "auto margins on an item, taken as 0 (9.6)"),
    ("flex_item_float_ignored", "float ignored on an item, which IS an item"),
    ("flex_baseline_in_column_as_start", "baseline in a column, as flex-start"),
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
        print("  text and intrinsic sizing")
        for key, population in TEXT_HEADLINE:
            print(f"    {counters.get(key, 0):>7}  {population}")
        print("  line boxes and inline layout")
        for key, population in LINE_HEADLINE:
            print(f"    {counters.get(key, 0):>7}  {population}")
        print("  tables")
        for key, population in TABLE_HEADLINE:
            print(f"    {counters.get(key, 0):>7}  {population}")
        print("  flex")
        for key, population in FLEX_HEADLINE:
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
    for key, population in (
        HEADLINE + LAYOUT_HEADLINE + TEXT_HEADLINE + LINE_HEADLINE
        + TABLE_HEADLINE + FLEX_HEADLINE + CENSUS
    ):
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
