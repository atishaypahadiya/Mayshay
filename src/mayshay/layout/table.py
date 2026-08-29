"""Table layout -- Phase 3 Task E. CSS 2.1 chapter 17.

Three things live here, in the order the box tree meets them:

1. **Section 17.2.1's anonymous table fixup**, which turns whatever the
   author wrote into a structure the rest of the chapter is stated over.
2. **Section 17.4's table wrapper box**, which splits one element's style
   across two boxes.
3. **Sections 17.5.2.1 and 17.5.2.2's width algorithms**, fixed and
   automatic, and the grid the cells are placed into.

## The intrinsic sizes come from `layout.intrinsic`, not from here

Automatic table layout needs the min-content and max-content width of every
cell, which is exactly what `layout.intrinsic` computes and what Task D1
verified against Chrome 151. There is no second min-content in this file
and there must not be: `intrinsic.py` exists because Task C's
shrink-to-fit, this module's column widths and Task F's `flex-basis: auto`
are one computation reached by three routes, and three implementations
would disagree on the same page with no single place to fix it.

The one thing this module needed and `intrinsic` did not have is a
contribution **without margins**, because section 17.5 says internal table
elements do not have margins at all. That was added there
(`outer_sizes(..., include_margins=False)`) rather than recomputed here.

## What is implemented and what is counted

Implemented: both width algorithms, `colspan` distribution, `rowspan` grid
occupancy, the wrapper box, captions on both sides, row and row-group
geometry, and the separated border model.

Counted, not implemented -- each with a name so the divergence is a number:

* `border-collapse: collapse`. Only the separated model exists.
  `table_border_collapse_requested`.
* `<col>` / `<colgroup>` width contributions. The boxes are recognised and
  occupy grid columns; their `width` does not constrain anything.
  `table_column_box_width_ignored`.
* Row heights distributed across a `rowspan` cell.
  `table_rowspan_height_not_distributed`.
* `vertical-align` on a cell other than `top`. Section 17.5.3 aligns cell
  content within the row by baseline (the initial value), and this engine
  puts every cell's content at the top of its box.
  `table_cell_vertical_align_as_top`.

## The mechanical check

`assert_table_constraints` runs on every layout, not only under test, and
states the one equation this module could get wrong in a way nothing else
would notice:

    sum(column widths) + (columns + 1) * horizontal border-spacing
        == the table box's content width

and, per row, that the cells tile it -- each cell's border box starts where
the previous one's ended plus a spacing, and the last ends at the content
edge. A distribution that lost or duplicated a pixel while still producing
plausible column widths fails here and nowhere else. Verified by injection:
distributing a `colspan` cell's excess over the wrong number of columns,
and dropping the spacing term, are both caught by this and by nothing else
in the suite.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field, replace

from mayshay.cssparse.cascade import ComputedStyle
from mayshay.cssparse.values import AUTO, Length, Percent
from mayshay.layout.boxtree import Box
from mayshay.layout.text import is_white_space_only

# --------------------------------------------------------------------------
# Section 17.2.1's vocabulary, stated once
# --------------------------------------------------------------------------
#
# These five sets are the spec's own defined terms. They are spelled out
# rather than derived from each other because the spec's rules quantify over
# them by name, and a reader checking a rule against the text should find
# the same words. Getting one wrong is the whole failure mode of this
# section: `PROPER_TABLE_CHILD` includes `table-caption` and
# `INTERNAL_TABLE_BOX` does not, and a single set doing both jobs generates
# an anonymous row around every caption.

ROW_GROUP_DISPLAYS: frozenset[str] = frozenset({
    "table-row-group", "table-header-group", "table-footer-group",
})

#: A 'table-row' box, row group box, 'table-column' box,
#: 'table-column-group' box, or 'table-caption' box.
PROPER_TABLE_CHILD: frozenset[str] = ROW_GROUP_DISPLAYS | frozenset({
    "table-row", "table-column", "table-column-group", "table-caption",
})

#: A 'table-cell' box, 'table-row' box, row group box, 'table-column' box,
#: or 'table-column-group' box. Note: **not** 'table-caption'.
INTERNAL_TABLE_BOX: frozenset[str] = ROW_GROUP_DISPLAYS | frozenset({
    "table-cell", "table-row", "table-column", "table-column-group",
})

#: A 'table' or 'inline-table' box or row group box.
PROPER_TABLE_ROW_PARENT: frozenset[str] = ROW_GROUP_DISPLAYS | frozenset({
    "table", "inline-table",
})

#: A 'table-row' box or proper table row parent.
TABULAR_CONTAINER: frozenset[str] = PROPER_TABLE_ROW_PARENT | frozenset({
    "table-row",
})

TABLE_DISPLAYS: frozenset[str] = frozenset({"table", "inline-table"})

#: The wrapper box's display, by the table's. Section 17.4: "The table
#: wrapper box is a 'block' box if the table is block-level, and an
#: 'inline-block' box if the table is inline-level."
WRAPPER_DISPLAY: dict[str, str] = {"table": "block", "inline-table": "inline-block"}


COUNTER_NAMES: tuple[str, ...] = (
    # --- section 17.2.1, one counter per rule ---------------------------
    "table_fixup_removed_child_of_column",
    "table_fixup_removed_non_column_in_column_group",
    "table_fixup_removed_white_space_between_table_boxes",
    "table_fixup_anonymous_row_in_table",
    "table_fixup_anonymous_row_in_row_group",
    "table_fixup_anonymous_cell_in_row",
    "table_fixup_anonymous_row_for_orphan_cell",
    "table_fixup_anonymous_table_for_misparented_row",
    "table_fixup_anonymous_table_for_misparented_column",
    "table_fixup_anonymous_table_for_misparented_row_group",
    "table_fixup_anonymous_table_for_misparented_column_group",
    "table_fixup_anonymous_table_for_misparented_caption",
    "table_fixup_anonymous_inline_table",
    # A structure that needs no fixup at all, counted so the rules above
    # can be read against a denominator. Section 17.2.1 does NOT generate
    # an anonymous row group: a row whose parent is a table is correct.
    "table_rows_directly_in_a_table",
    # --- section 17.4 ---------------------------------------------------
    "table_wrapper_boxes",
    "table_captions_before",
    "table_captions_after",
    # --- sections 17.5.2.1 / 17.5.2.2 -----------------------------------
    "tables_laid_out",
    "table_layout_automatic",
    "table_layout_fixed",
    "table_layout_fixed_fallback_auto_width",
    "table_columns",
    "table_cells_placed",
    "table_cells_spanning_columns",
    "table_cells_spanning_rows",
    "table_colspan_excess_distributed",
    "table_colspan_absorbed_without_widening",
    "table_width_auto_shrink_to_fit",
    "table_width_specified",
    "table_width_percentage_of_containing_block",
    "table_width_raised_to_min_content",
    "table_extra_width_distributed",
    "table_rows_laid_out",
    "table_row_groups_laid_out",
    # --- counted, not implemented ---------------------------------------
    "table_border_collapse_requested",
    "table_column_box_width_ignored",
    "table_rowspan_height_not_distributed",
    "table_cell_vertical_align_as_top",
    "table_cell_percentage_width_as_auto",
    "table_internal_margin_dropped",
    "table_internal_margin_declared_zero",
    "table_overlapping_grid_slot",
)


# --------------------------------------------------------------------------
# Section 17.2.1: anonymous table objects
# --------------------------------------------------------------------------


def _is_anonymous_white_space(box: Box) -> bool:
    """Section 17.2.1's "anonymous inline box that contains only white
    space", as it reaches this module.

    Task B has already wrapped runs of inline content in anonymous blocks,
    so the shape that arrives here is either a bare text box or an anonymous
    block whose every descendant is blank text. Both are tested, because the
    two shapes occur for the same source markup depending only on whether a
    block-level sibling was present -- and treating one as white space while
    treating the other as content is how a table gains an anonymous row that
    a browser does not put there.

    `layout.text.is_white_space_only`, never `str.strip()`: they disagree on
    U+00A0 and six other Unicode spaces, and CSS Text 3 sides with the
    former. A `&nbsp;` between two `<td>`s is content.
    """
    if box.origin == "text":
        return box.node is not None and is_white_space_only(box.node.data)
    if box.origin == "anonymous" and box.display == "block":
        return bool(box.children) and all(
            _is_anonymous_white_space(child) for child in box.children
        )
    return False


def _anonymous(display: str, children: list[Box]) -> Box:
    return Box(display=display, origin="anonymous", children=children)


def _remove_irrelevant(box: Box, metrics: Counter[str]) -> list[Box]:
    """Stage one of section 17.2.1. Three rules, all of them deletions.

    The spec's rules 3 and 4 are two statements of one deletion -- white
    space between table boxes -- differing only in whether the parent is a
    tabular container. They are applied as one rule and counted under one
    name, because two counters for one deletion would double-count every
    occurrence and make the register lie about coverage.
    """
    if box.display == "table-column":
        # Rule 1: all child boxes of a 'table-column' parent are treated as
        # if they had `display: none`. A `<col>` has no content.
        metrics["table_fixup_removed_child_of_column"] += len(box.children)
        return []
    if box.display == "table-column-group":
        # Rule 2: a child that is not a 'table-column' is treated as if it
        # had `display: none`.
        kept = [child for child in box.children if child.display == "table-column"]
        metrics["table_fixup_removed_non_column_in_column_group"] += (
            len(box.children) - len(kept)
        )
        return kept

    children = box.children
    if box.display not in TABULAR_CONTAINER and not any(
        child.display in INTERNAL_TABLE_BOX or child.display == "table-caption"
        for child in children
    ):
        return list(children)

    def relevant(index: int) -> bool:
        child = children[index]
        if not _is_anonymous_white_space(child):
            return True
        before = children[index - 1] if index > 0 else None
        after = children[index + 1] if index + 1 < len(children) else None
        neighbours = [n for n in (before, after) if n is not None]
        if not neighbours:
            # Both rules require a neighbour that is a table box. White
            # space alone inside a table is content, and stage two gives it
            # the anonymous row and cell that make it one.
            return True
        return not all(
            n.display in INTERNAL_TABLE_BOX or n.display == "table-caption"
            for n in neighbours
        )

    kept = [children[i] for i in range(len(children)) if relevant(i)]
    metrics["table_fixup_removed_white_space_between_table_boxes"] += (
        len(children) - len(kept)
    )
    return kept


def _consecutive_run(
    children: list[Box], start: int, belongs
) -> int:
    """The end index of the run beginning at `start`, per the spec's
    definition of *consecutive*: intervening anonymous white space does not
    break a run, but it is not itself the reason a run continues.

    Returned as an index rather than a slice so the caller can decide
    whether the trailing white space is inside the generated wrapper. It is:
    a space between two cells belongs to the row, not to the box after it.

    **The run always contains at least `children[start]`**, which is what
    the spec's own phrasing says -- "C and all consecutive siblings of C
    that..." -- and what makes every caller's `while` loop terminate. Found
    by injection, not by reading: an injected set membership made
    `_misparent_reason` say "misparented" for a box `belongs` rejected, the
    run came back empty, `index` never advanced, and the whole test run
    hung instead of failing. A hang is the one outcome worse than a wrong
    answer, and `max(...)` here is what makes the depth assert below
    reachable at all.
    """
    end = start
    index = start
    while index < len(children):
        if belongs(children[index]):
            index += 1
            end = index
            continue
        if _is_anonymous_white_space(children[index]):
            index += 1
            continue
        break
    return max(end, start + 1)


def _generate_child_wrappers(
    box: Box, metrics: Counter[str], depth: int
) -> list[Box]:
    """Stage two of section 17.2.1: a container's children, wrapped.

    Three rules, distinguished by the *parent's* display:

    * a `table` child that is not a proper table child -> anonymous row;
    * a row group child that is not a `table-row` -> anonymous row;
    * a `table-row` child that is not a `table-cell` -> anonymous cell.

    An anonymous row generated by the first two rules then has this same
    function applied to **it**, which is what adds the anonymous cell inside
    it. That is not an optimisation: section 17.2.1's opening sentence says
    a table element generates "at least three nested objects", and one pass
    over the original tree generates two.
    """
    if box.display in TABLE_DISPLAYS:
        wrapper, counter = "table-row", "table_fixup_anonymous_row_in_table"
        def belongs(child: Box) -> bool:
            return child.display not in PROPER_TABLE_CHILD
    elif box.display in ROW_GROUP_DISPLAYS:
        wrapper, counter = "table-row", "table_fixup_anonymous_row_in_row_group"
        def belongs(child: Box) -> bool:
            return child.display != "table-row"
    elif box.display == "table-row":
        wrapper, counter = "table-cell", "table_fixup_anonymous_cell_in_row"
        def belongs(child: Box) -> bool:
            return child.display != "table-cell"
    else:
        return list(box.children)

    children = box.children
    out: list[Box] = []
    index = 0
    while index < len(children):
        child = children[index]
        if not belongs(child):
            out.append(child)
            index += 1
            continue
        end = _consecutive_run(children, index, belongs)
        anonymous = _anonymous(wrapper, children[index:end])
        metrics[counter] += 1
        out.extend(_fixup_own(anonymous, metrics, depth + 1))
        index = end
    return out


def _misparent_reason(child: Box, parent_display: str) -> str | None:
    """Section 17.2.1 stage three, rule 2's three sub-clauses, verbatim.

    Written as one function returning the *reason* rather than a boolean so
    each clause gets its own counter. "We generated an anonymous table" and
    "we generated one because a row group was in a `<div>`" are different
    facts, and only the second says which rule has corpus coverage.

    The clause that is easy to get wrong is the first: a `table-row` whose
    parent is a **table** is not misparented. Section 17.2.1 contains no
    rule that generates an anonymous row group, and inventing one here
    would put a box in the tree that no browser has.
    """
    if child.display == "table-row":
        if parent_display in PROPER_TABLE_ROW_PARENT:
            return None
        return "row"
    if child.display == "table-column":
        if parent_display in TABLE_DISPLAYS or parent_display == "table-column-group":
            return None
        return "column"
    if child.display in ROW_GROUP_DISPLAYS:
        return None if parent_display in TABLE_DISPLAYS else "row_group"
    if child.display == "table-column-group":
        return None if parent_display in TABLE_DISPLAYS else "column_group"
    if child.display == "table-caption":
        return None if parent_display in TABLE_DISPLAYS else "caption"
    return None


def _generate_missing_parents(
    box: Box, metrics: Counter[str], depth: int
) -> list[Box]:
    """Stage three of section 17.2.1: an orphan cell gets a row, and a
    misparented proper table child gets a table.

    Rule 1 runs first and rule 2 then sees its output, which is why a
    `table-cell` in a `<div>` ends up inside a table and not merely inside a
    row: rule 1 gives it the row, rule 2 gives the row the table. Running
    them in the other order leaves the cell in a table with no row.
    """
    children = _wrap_orphan_cells(box, metrics)
    out: list[Box] = []
    index = 0
    while index < len(children):
        child = children[index]
        reason = _misparent_reason(child, box.display)
        if reason is None:
            out.append(child)
            index += 1
            continue

        def belongs(candidate: Box) -> bool:
            return candidate.display in PROPER_TABLE_CHILD

        end = _consecutive_run(children, index, belongs)
        # "If C's parent is an 'inline' box, then T must be an
        # 'inline-table' box; otherwise it must be a 'table' box."
        inline_parent = box.display == "inline"
        anonymous = _anonymous(
            "inline-table" if inline_parent else "table", children[index:end]
        )
        metrics[f"table_fixup_anonymous_table_for_misparented_{reason}"] += 1
        if inline_parent:
            metrics["table_fixup_anonymous_inline_table"] += 1
        out.extend(_fixup_own(anonymous, metrics, depth + 1))
        index = end
    return out


def _wrap_orphan_cells(box: Box, metrics: Counter[str]) -> list[Box]:
    """Stage three, rule 1: a `table-cell` whose parent is not a
    `table-row`."""
    if box.display == "table-row":
        return list(box.children)
    children = box.children
    if not any(child.display == "table-cell" for child in children):
        return list(children)

    def belongs(candidate: Box) -> bool:
        return candidate.display == "table-cell"

    out: list[Box] = []
    index = 0
    while index < len(children):
        if children[index].display != "table-cell":
            out.append(children[index])
            index += 1
            continue
        end = _consecutive_run(children, index, belongs)
        metrics["table_fixup_anonymous_row_for_orphan_cell"] += 1
        out.append(_anonymous("table-row", children[index:end]))
        index = end
    return out


# --------------------------------------------------------------------------
# Section 17.4: the table wrapper box
# --------------------------------------------------------------------------

#: The properties section 17.4 assigns to the WRAPPER, and therefore the
#: ones that must be neutralised on the table box inside it. Everything not
#: named here stays on the table box.
#:
#: `top`/`right`/`bottom`/`left` are in the spec's list and absent here for
#: one reason: `ComputedStyle` has no such fields, so there is nothing to
#: move. Recorded rather than silently omitted -- when Task C's successor
#: adds offsets, they belong on the wrapper.
_WRAPPER_PROPERTIES: tuple[str, ...] = (
    "margin_top", "margin_right", "margin_bottom", "margin_left",
    "position", "float_",
)

_INITIAL = ComputedStyle()


def _split_style(style: ComputedStyle, wrapper_display: str) -> tuple[
    ComputedStyle, ComputedStyle
]:
    """One element's computed style, as section 17.4 divides it.

    The wrapper keeps the margins, `position` and `float` and gives up
    everything that draws or sizes; the table box keeps the borders,
    padding, width, height and every table property and gives up the
    margins. `width` in particular must stay on the table box -- 17.5.2's
    algorithms are stated over it -- while the wrapper's width is then
    *derived* from the table box's border-edge width.

    Two styles are built rather than one mutated, because the element's
    `computed_style` is shared with the DOM and with the cascade's own
    tests. Mutating it here would make a second layout of the same document
    disagree with the first.
    """
    wrapper = replace(
        style,
        display=wrapper_display,
        width=AUTO,
        height=AUTO,
        padding_top=_INITIAL.padding_top,
        padding_right=_INITIAL.padding_right,
        padding_bottom=_INITIAL.padding_bottom,
        padding_left=_INITIAL.padding_left,
        border_top_width=_INITIAL.border_top_width,
        border_right_width=_INITIAL.border_right_width,
        border_bottom_width=_INITIAL.border_bottom_width,
        border_left_width=_INITIAL.border_left_width,
        # The wrapper is not a new block formatting context by virtue of
        # `overflow`; it is one by virtue of being a table wrapper, which
        # `Box.table_wrapper` says. Leaving a declared `overflow: hidden`
        # here as well would be harmless and is left alone for that reason.
    )
    inner = replace(
        style,
        margin_top=_INITIAL.margin_top,
        margin_right=_INITIAL.margin_right,
        margin_bottom=_INITIAL.margin_bottom,
        margin_left=_INITIAL.margin_left,
        position=_INITIAL.position,
        float_=_INITIAL.float_,
    )
    return wrapper, inner


def _build_wrapper(table: Box, metrics: Counter[str], style: ComputedStyle) -> Box:
    """Turn a table box into a wrapper box containing a table box.

    **The element's identity stays on the wrapper**, not on the table box.
    That is the half a reader would guess wrong: `DOM.getBoxModel` for a
    `<table>` answers with the box the margins are on, and section 17.4 puts
    the margins on the wrapper. Giving the identity to the inner box would
    make every Chrome comparison of a table with a caption compare two
    different rectangles and call the difference a layout error.
    """
    wrapper_display = WRAPPER_DISPLAY[table.display]
    wrapper_style, inner_style = _split_style(style, wrapper_display)

    inner = Box(
        display=table.display,
        origin="anonymous",
        children=[c for c in table.children if c.display != "table-caption"],
        style=inner_style,
    )
    captions = [c for c in table.children if c.display == "table-caption"]

    wrapper = Box(
        display=wrapper_display,
        origin=table.origin,
        node=table.node,
        ordinal=table.ordinal,
        path=table.path,
        style=wrapper_style,
        table_wrapper=True,
    )
    # Section 17.4: the caption boxes are block-level boxes inside the
    # wrapper, before or after the table box per `caption-side`. Their own
    # `caption-side` is what decides, not the table's -- the property
    # inherits, so a caption that declares nothing agrees with the table
    # anyway, and one that declares `bottom` moves on its own.
    before = [c for c in captions if _caption_side(c) == "top"]
    after = [c for c in captions if _caption_side(c) != "top"]
    metrics["table_captions_before"] += len(before)
    metrics["table_captions_after"] += len(after)
    metrics["table_wrapper_boxes"] += 1
    wrapper.children = [*before, inner, *after]
    return wrapper


def _caption_side(caption: Box) -> str:
    style = caption.node.computed_style if caption.node is not None else None
    return "top" if style is None else style.caption_side


# --------------------------------------------------------------------------
# The pass
# --------------------------------------------------------------------------


#: How many boxes section 17.2.1 may nest around one child before the rule
#: set is declared non-convergent. Its opening sentence promises "at least
#: three nested objects" (table, row, cell) and stage three can add a table
#: above them, so four is the real depth and eight is generous.
#:
#: This is a cap on a *rule set*, not on input: with the sets as the spec
#: defines them the recursion always terminates, because every generated box
#: makes its children well-parented. The cap exists because getting one set
#: membership wrong does NOT terminate -- dropping `table-caption` from
#: `PROPER_TABLE_CHILD` makes stage two wrap the caption in a row, stage
#: three wrap the row's cell's caption in a table, and stage two wrap it
#: again, forever. Found by injecting exactly that: without this assert the
#: injection hangs the test run instead of failing it, which is the one
#: outcome worse than a wrong answer.
_MAX_FIXUP_DEPTH = 8


def _fixup_own(box: Box, metrics: Counter[str], depth: int = 0) -> list[Box]:
    """The three stages over one box's own children, plus 17.4's wrapper.

    Returns the boxes that replace `box` in its parent -- a list rather than
    a box because a table becomes a wrapper, and because a future rule could
    dissolve a box entirely.
    """
    assert depth <= _MAX_FIXUP_DEPTH, (
        "section 17.2.1's rules did not converge: "
        f"{depth} generated boxes nested around {box!r}. One of the five "
        "defined sets at the top of this module disagrees with the spec"
    )
    box.children = _remove_irrelevant(box, metrics)
    box.children = _generate_child_wrappers(box, metrics, depth)
    box.children = _generate_missing_parents(box, metrics, depth)
    if box.display in TABLE_DISPLAYS:
        metrics["table_rows_directly_in_a_table"] += sum(
            1 for child in box.children if child.display == "table-row"
        )
        style = box.style
        if style is None:
            style = (
                box.node.computed_style
                if box.origin == "element" and box.node is not None
                else None
            )
        return [_build_wrapper(box, metrics, style or ComputedStyle())]
    return [box]


def fix_up_tables(root: Box | None, metrics: Counter[str]) -> None:
    """Section 17.2.1 and 17.4 over the whole box tree, in place.

    **Bottom-up.** A nested table has to be finished -- and turned into a
    wrapper -- before its ancestor classifies it, because an ancestor table
    must see a nested table as ordinary content to be wrapped in an
    anonymous cell, and a `table` box is a proper table child while the
    `block` wrapper it becomes is not. Top-down leaves the inner table as a
    direct child of the outer one, which puts a whole table into the grid as
    though it were a row.
    """
    if root is None:
        return
    # The root element is `<html>`, which is never a table in any document
    # this engine parses. Asserted rather than assumed: section 17.4's
    # wrapper box would have to *replace* the root of the box tree, and
    # `layout_document` holds the root by reference.
    assert root.display not in TABLE_DISPLAYS, (
        "the root element computes `display: table`; section 17.4's wrapper "
        "box would have to replace the root of the box tree"
    )
    replacements = _fixup(root, metrics)
    assert replacements == [root], "the root box was replaced by the fixup"


def _fixup(box: Box, metrics: Counter[str]) -> list[Box]:
    box.children = [
        replacement
        for child in box.children
        for replacement in _fixup(child, metrics)
    ]
    return _fixup_own(box, metrics)
