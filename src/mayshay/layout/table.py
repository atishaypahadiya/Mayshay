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
    "table_width_remainder_to_margin_right",
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


# --------------------------------------------------------------------------
# The grid: CSS 2.1 section 17.5's placement rules
# --------------------------------------------------------------------------

#: The displays whose inner layout is table layout rather than block flow.
TABLE_BOX_DISPLAYS: frozenset[str] = TABLE_DISPLAYS | ROW_GROUP_DISPLAYS | frozenset(
    {"table-row"}
)

#: HTML's own clamps on the two span attributes. `colspan` is 1..1000 and
#: `rowspan` is 0..65534, where 0 means "to the end of the row group". They
#: are HTML rules rather than CSS ones -- section 17.5 says outright that
#: "CSS 2.1 does not define how the number of spanned rows or columns is
#: determined" and that a UA may have special knowledge of the source
#: document. This is that knowledge, stated where it is used.
_MAX_COLSPAN = 1000
_MAX_ROWSPAN = 65534


@dataclass
class _PlacedCell:
    box: Box
    row: int
    column: int
    colspan: int
    rowspan: int
    #: `(min, max)` contribution, section 17.5.2.2's "minimum cell width"
    #: and "maximum cell width", including the cell's own border and
    #: padding and excluding margins.
    minimum: float = 0.0
    maximum: float = 0.0


@dataclass
class Grid:
    """The rectangular, irregular grid of section 17.5.

    `rows` is every `table-row` box in document order across every row
    group, because a row group "occupies the same grid cells as the rows it
    contains" -- the grid is a property of the table, not of the section.
    Numbering rows per group would put two cells in the same slot the first
    time a table had a `<thead>`.
    """

    rows: list[Box] = field(default_factory=list)
    cells: list[_PlacedCell] = field(default_factory=list)
    columns: int = 0
    column_boxes: list[Box] = field(default_factory=list)
    #: Row index by `id(row box)`, so a row laid out from inside a row group
    #: still knows which grid row it is.
    row_index: dict = field(default_factory=dict)


def _span_attribute(box: Box, name: str, maximum: int, *, zero_means: int) -> int:
    node = box.node
    raw = node.attrs.get(name) if node is not None and hasattr(node, "attrs") else None
    if raw is None:
        return 1
    try:
        value = int(raw.strip())
    except (TypeError, ValueError):
        # HTML's rules for a malformed span attribute are "use the default",
        # not "use zero". A cell that silently claimed no columns would be
        # placed on top of its neighbour.
        return 1
    if value <= 0:
        return zero_means
    return min(value, maximum)


def _rows_of(table: Box, grid: Grid) -> None:
    for child in table.children:
        if child.display == "table-row":
            grid.row_index[id(child)] = len(grid.rows)
            grid.rows.append(child)
        elif child.display in ROW_GROUP_DISPLAYS:
            for row in child.children:
                if row.display == "table-row":
                    grid.row_index[id(row)] = len(grid.rows)
                    grid.rows.append(row)
        elif child.display == "table-column":
            grid.column_boxes.append(child)
        elif child.display == "table-column-group":
            grid.column_boxes.extend(
                c for c in child.children if c.display == "table-column"
            )


def build_grid(table: Box, metrics: Counter[str]) -> Grid:
    """Place every cell, honouring `colspan` and `rowspan`.

    Section 17.5's rule 5, stated as an algorithm: a cell's top row is its
    parent row; it goes as far left as it can without overlapping a cell
    that a previous row spans down into, and to the right of every earlier
    cell in its own row.

    `rowspan` occupancy is implemented even though the corpus contains
    **zero** cells with `rowspan > 1` (executed over all 401), because
    without it a `rowspan` cell's neighbours in later rows land in the wrong
    *columns* -- which is a width error, not a height one, and would be
    invisible until a page used it.
    """
    grid = Grid()
    _rows_of(table, grid)
    occupied: set[tuple[int, int]] = set()

    for index, row in enumerate(grid.rows):
        column = 0
        for child in row.children:
            if child.display != "table-cell":
                continue
            while (index, column) in occupied:
                column += 1
            colspan = _span_attribute(child, "colspan", _MAX_COLSPAN, zero_means=1)
            rowspan = _span_attribute(
                child, "rowspan", _MAX_ROWSPAN, zero_means=len(grid.rows) - index
            )
            rowspan = max(1, min(rowspan, len(grid.rows) - index))
            for down in range(rowspan):
                for across in range(colspan):
                    slot = (index + down, column + across)
                    if slot in occupied:
                        # Section 17.5 rule 5 leaves this undefined -- "may
                        # either overlap the cells or shift the later cell
                        # to the right". Overlapping is what HTML user
                        # agents do and what this does; counted so the
                        # undefined case is a number rather than a silence.
                        metrics["table_overlapping_grid_slot"] += 1
                    occupied.add(slot)
            grid.cells.append(
                _PlacedCell(child, index, column, colspan, rowspan)
            )
            metrics["table_cells_placed"] += 1
            if colspan > 1:
                metrics["table_cells_spanning_columns"] += 1
            if rowspan > 1:
                metrics["table_cells_spanning_rows"] += 1
                metrics["table_rowspan_height_not_distributed"] += 1
            column += colspan

    from_cells = max((c.column + c.colspan for c in grid.cells), default=0)
    grid.columns = max(from_cells, len(grid.column_boxes))
    metrics["table_columns"] += grid.columns
    metrics["table_column_box_width_ignored"] += sum(
        1
        for box in grid.column_boxes
        if getattr(box.node, "computed_style", None) is not None
        and box.node.computed_style.width is not AUTO
    )
    return grid


# --------------------------------------------------------------------------
# Sections 17.5.2.1 and 17.5.2.2: the two width algorithms
# --------------------------------------------------------------------------


@dataclass
class TablePlan:
    """Everything the geometry pass needs, decided before a box is placed.

    Separated from the layout pass on purpose. The table's used width is the
    *wrapper's* content width (section 17.4), and the wrapper is laid out
    before its children -- so the width algorithm has to run before any box
    in the table has geometry, and it does: it reads intrinsic sizes and
    computed styles and nothing else.
    """

    grid: Grid
    columns: list[float]
    #: The table box's content width. Equal, by construction, to
    #: `sum(columns) + (len(columns) + 1) * spacing_x` -- which is what
    #: `assert_table_constraints` checks rather than assumes.
    content_width: float
    #: ...plus the table box's own border and padding: the wrapper's
    #: content width, per section 17.4.
    border_width: float
    spacing_x: float
    spacing_y: float


def _cell_sizes(cell: _PlacedCell, metrics: Counter[str]) -> None:
    """Section 17.5.2.2's first two bullets, for one cell.

    "Calculate the minimum content width (MCW) of each cell... If the
    specified 'width' (W) of the cell is greater than MCW, W is the minimum
    cell width. A value of 'auto' means that MCW is the minimum cell width."

    Both sizes come from `layout.intrinsic`, which is the *only* place
    min-content is computed in this engine. What is composed here is
    17.5.2.2's rule about W, which CSS Sizing 3 does not share: for an
    ordinary box a definite width simply *is* the contribution, and for a
    cell it is a floor under a content-driven one.
    """
    from mayshay.layout import intrinsic as intrinsic_module
    from mayshay.layout.used import style_of

    style = style_of(cell.box)
    sizes = intrinsic_module.outer_sizes(
        cell.box, metrics, include_margins=False, ignore_specified_width=True
    )
    edges = intrinsic_module.horizontal_edges(style, metrics)
    minimum, maximum = sizes.min_content, sizes.max_content

    if isinstance(style.width, Percent):
        # "A percentage value for a column width is relative to the table
        # width" -- which is what this function is being called to help
        # decide, so it is not a number yet. Treated as `auto` and counted.
        # 103 of the corpus's 401 cells take this branch.
        metrics["table_cell_percentage_width_as_auto"] += 1
    else:
        specified = intrinsic_module.specified_content_width(style, metrics)
        if specified is not None:
            if style.box_sizing != "border-box":
                specified += edges.inside
            minimum = max(minimum, specified)
            maximum = max(maximum, specified)
    cell.minimum = minimum
    cell.maximum = maximum


def _distribute(
    widths: list[float], columns: range, excess: float, weights: list[float]
) -> None:
    """Widen a run of columns by `excess`, in proportion to `weights`.

    Section 17.5.2.2 says only "if possible, widen all spanned columns by
    approximately the same amount", which several different rules satisfy.
    **Measured against Chrome 151 rather than chosen**, with a fixture built
    to tell them apart: two columns holding one unbreakable word each so
    that min equals max, 4 and 20 `W` glyphs wide (60.41 and 302.03), under
    a `colspan=2` cell with `width: 400px`.

        equal shares      79.19 / 321.22
        proportional      66.66 / 333.34
        Chrome 151        66.6563 / 333.3438

    A three-column version and a two-span version agree to within a
    LayoutUnit, so the rule is proportional to what the columns already
    want. Equal shares would have been the more literal reading of
    "approximately the same amount", and it is wrong by 13px on the first
    column of a 400px table.

    So the weights are the caller's business and this function is
    arithmetic. A zero weight sum means no column has a preference, and
    then equal shares are the only defensible answer.
    """
    total = sum(weights)
    if excess <= 0 or not columns:
        return
    if total <= 0:
        share = excess / len(columns)
        for index in columns:
            widths[index] += share
        return
    given = 0.0
    indices = list(columns)
    for position, index in enumerate(indices):
        if position == len(indices) - 1:
            # The last column takes the remainder rather than its own
            # share, so the sum is exact. Floating-point drift of a
            # thousandth of a pixel per column is invisible on a page and
            # fails `assert_table_constraints`, which is the point of
            # having one.
            widths[index] += excess - given
        else:
            part = excess * weights[position] / total
            widths[index] += part
            given += part


def _automatic_columns(
    grid: Grid, spacing_x: float, metrics: Counter[str]
) -> tuple[list[float], list[float]]:
    """Section 17.5.2.2, bullets 3 to 5: `(column minimums, column maximums)`.

    **Spanning cells are considered after non-spanning ones**, and in
    increasing order of span, which is the ordering the section states and
    the one that makes the result independent of source order: a column's
    width from single-cell content is established first, and a span can only
    widen it.
    """
    minimums = [0.0] * grid.columns
    maximums = [0.0] * grid.columns
    for cell in grid.cells:
        _cell_sizes(cell, metrics)
        if cell.colspan == 1:
            minimums[cell.column] = max(minimums[cell.column], cell.minimum)
            maximums[cell.column] = max(maximums[cell.column], cell.maximum)

    for cell in sorted(
        (c for c in grid.cells if c.colspan > 1), key=lambda c: c.colspan
    ):
        span = range(cell.column, cell.column + cell.colspan)
        gaps = (cell.colspan - 1) * spacing_x
        widened = False
        for widths, wanted in ((minimums, cell.minimum), (maximums, cell.maximum)):
            current = sum(widths[i] for i in span) + gaps
            excess = wanted - current
            if excess <= 0:
                continue
            widened = True
            weights = [widths[i] for i in span]
            _distribute(widths, span, excess, weights)
        if widened:
            metrics["table_colspan_excess_distributed"] += 1
        else:
            # The spanned columns were already wide enough. This is the
            # common case and the reason a wrong distribution is invisible:
            # 54 corpus cells span two columns and most of them fall here.
            metrics["table_colspan_absorbed_without_widening"] += 1

    for index in range(grid.columns):
        maximums[index] = max(maximums[index], minimums[index])
    return minimums, maximums


def _fixed_columns(
    grid: Grid, used_content: float, spacing_x: float, metrics: Counter[str]
) -> list[float]:
    """Section 17.5.2.1's fixed table layout.

    "the horizontal layout of the table does not depend on the contents of
    the cells; it only depends on the table's width, the width of the
    columns, and borders or cell spacing." Three rules, in order: a column
    element's `width` wins, then a **first-row** cell's `width` (divided
    over the columns it spans), then the remaining columns share what is
    left equally.

    **Zero corpus coverage.** Not one of the three pages' stylesheets
    contains a `table-layout` declaration of any value -- executed with a
    grep over `data/corpus` -- so every column width this function has ever
    produced came from a synthetic fixture. It is a
    `docs/synthetic-only-coverage.md` row, and the rest of this module is
    where the corpus actually goes.
    """
    from mayshay.layout.used import style_of

    widths: list[float | None] = [None] * grid.columns
    for index, column_box in enumerate(grid.column_boxes[: grid.columns]):
        specified = _definite_width(style_of(column_box), used_content)
        if specified is not None:
            widths[index] = specified

    for cell in grid.cells:
        if cell.row != 0:
            continue
        specified = _definite_width(style_of(cell.box), used_content)
        if specified is None:
            continue
        # "If the cell spans more than one column, the width is divided over
        # the columns." Divided, not repeated: the spacings between the
        # spanned columns are inside the cell's width and come off first.
        share = (specified - (cell.colspan - 1) * spacing_x) / cell.colspan
        for offset in range(cell.colspan):
            index = cell.column + offset
            if index < grid.columns and widths[index] is None:
                widths[index] = max(0.0, share)

    remaining_indices = [i for i, w in enumerate(widths) if w is None]
    assigned = sum(w for w in widths if w is not None)
    spare = used_content - (grid.columns + 1) * spacing_x - assigned
    if remaining_indices:
        share = max(0.0, spare) / len(remaining_indices)
        for index in remaining_indices:
            widths[index] = share
    resolved = [w or 0.0 for w in widths]

    # "The width of the table is then the greater of the value of 'width'
    # ... and the sum of the column widths (plus cell spacing or borders).
    # If the table is wider than the columns, the extra space should be
    # distributed over the columns." With every column assigned above, the
    # only way to be short is for the specified widths to under-fill.
    shortfall = used_content - (sum(resolved) + (grid.columns + 1) * spacing_x)
    if shortfall > 1e-9 and resolved:
        _distribute(resolved, range(grid.columns), shortfall, list(resolved))
        metrics["table_extra_width_distributed"] += 1
    return resolved


def _definite_width(style: ComputedStyle, basis: float) -> float | None:
    """A `width` in pixels, resolving a percentage against `basis`.

    Used only by fixed table layout, where the table's own width is known
    before the columns are -- which is the whole point of the algorithm and
    the reason a percentage column width IS resolvable here and is not in
    section 17.5.2.2.
    """
    if style.width is AUTO:
        return None
    if isinstance(style.width, Percent):
        return max(0.0, float(style.width.value) / 100.0 * basis)
    if isinstance(style.width, Length) and style.width.unit == "px":
        return max(0.0, float(style.width.value))
    return None


def _caption_minimum(wrapper: Box, metrics: Counter[str]) -> float:
    """CAPMIN: "the MCW of a hypothetical table cell that contains the
    caption formatted as `display: block`", greatest over the captions.

    Zero when there are no captions, which is 25 of the corpus's 29 tables.
    """
    from mayshay.layout import intrinsic as intrinsic_module

    return max(
        (
            intrinsic_module.outer_sizes(child, metrics).min_content
            for child in wrapper.children
            if child.display == "table-caption"
        ),
        default=0.0,
    )


def plan_table(
    wrapper: Box, table: Box, *, cb_width: float, metrics: Counter[str]
) -> TablePlan:
    """Decide every column width, before any box in the table has geometry.

    `cb_width` is the **wrapper's** containing block width, not the
    wrapper's own content width -- section 17.4 says percentages on the
    table's `width` are "relative to the table wrapper box's containing
    block, not the table wrapper box itself", and the wrapper's width is
    about to be derived from the answer.
    """
    from mayshay.layout.used import px_or_zero, style_of

    style = style_of(table)
    metrics["tables_laid_out"] += 1
    if style.border_collapse == "collapse":
        # Not implemented: only the separated model exists here. The
        # divergence is one border width per cell edge, which reads as a
        # table a few pixels too wide rather than as a broken one.
        metrics["table_border_collapse_requested"] += 1

    spacing = style.border_spacing
    spacing_x = float(getattr(spacing[0], "value", 0.0))
    spacing_y = float(getattr(spacing[1], "value", 0.0))

    edges = (
        px_or_zero(style.border_left_width, basis=cb_width, metrics=metrics)
        + px_or_zero(style.border_right_width, basis=cb_width, metrics=metrics)
        + px_or_zero(style.padding_left, basis=cb_width, metrics=metrics)
        + px_or_zero(style.padding_right, basis=cb_width, metrics=metrics)
    )
    margins = px_or_zero(
        style_of(wrapper).margin_left, basis=cb_width, metrics=metrics
    ) + px_or_zero(style_of(wrapper).margin_right, basis=cb_width, metrics=metrics)

    grid = build_grid(table, metrics)
    gaps = (grid.columns + 1) * spacing_x
    minimums, maximums = _automatic_columns(grid, spacing_x, metrics)
    smallest = sum(minimums) + gaps
    largest = sum(maximums) + gaps
    capmin = _caption_minimum(wrapper, metrics)

    specified = _table_width(style, cb_width, edges, metrics)
    fixed = style.table_layout == "fixed"
    if fixed and specified is None:
        # "A value of 'auto' (for both 'display: table' and 'display:
        # inline-table') means use the automatic table layout algorithm."
        # CSS 2.1 allows a UA to apply fixed layout to an auto-width
        # block-level table anyway; Chrome 151 does not -- measured, a
        # `table-layout: fixed` table with no width in a 500px block came
        # out 17.8125 wide, which is its content, not its containing block.
        metrics["table_layout_fixed_fallback_auto_width"] += 1
        fixed = False
    metrics["table_layout_fixed" if fixed else "table_layout_automatic"] += 1

    if specified is not None:
        content_width = max(specified, capmin, smallest)
    else:
        available = max(0.0, cb_width - edges - margins)
        content_width = max(smallest, capmin, min(largest, available))
        metrics["table_width_auto_shrink_to_fit"] += 1
    if content_width > smallest + 1e-9 and content_width > (specified or 0.0):
        metrics["table_width_raised_to_min_content"] += 1

    if fixed:
        columns = _fixed_columns(grid, content_width, spacing_x, metrics)
    else:
        columns = _extra_width_over_columns(
            minimums, maximums, content_width - gaps, metrics
        )
    # The content width is the columns, exactly. Recomputing it from them
    # rather than trusting the target is what keeps
    # `assert_table_constraints` an independent check of the distribution
    # instead of a restatement of it.
    content_width = sum(columns) + gaps
    return TablePlan(
        grid=grid,
        columns=columns,
        content_width=content_width,
        border_width=content_width + edges,
        spacing_x=spacing_x,
        spacing_y=spacing_y,
    )


def _table_width(
    style: ComputedStyle, cb_width: float, edges: float, metrics: Counter[str]
) -> float | None:
    """The table's specified content width, or None for `auto`."""
    if style.width is AUTO:
        return None
    if isinstance(style.width, Percent):
        metrics["table_width_percentage_of_containing_block"] += 1
        width = float(style.width.value) / 100.0 * cb_width
    elif isinstance(style.width, Length) and style.width.unit == "px":
        width = float(style.width.value)
    else:
        return None
    metrics["table_width_specified"] += 1
    if style.box_sizing == "border-box":
        width -= edges
    return max(0.0, width)


def _extra_width_over_columns(
    minimums: list[float],
    maximums: list[float],
    target: float,
    metrics: Counter[str],
) -> list[float]:
    """Widen the columns from their minimums until they add up to `target`.

    **Two phases, and the second is not the first repeated.** Measured
    against Chrome 151 on two fixtures built so that the phases disagree:

    * a 100px table over columns with MIN 98.66 and MAX 216.98, where one
      column's min already equals its max. Chrome gives 45.3125 / 54.6875 --
      every one of the 1.34px of slack went to the column that could use it.
      Distributing in proportion to `max` would have given the first column
      20.9px, which is below its own minimum.
    * a 260px table over MIN 71.14 and MAX 287.31 with both columns able to
      grow. Chrome gives 55.0781 / 204.9219; in proportion to remaining
      capacity that is 55.090 / 204.910, inside one LayoutUnit.

    So phase one distributes in proportion to `max - min` and stops there if
    that is enough. Phase two -- a table wider than its own max-content --
    has nothing left to be proportional to and uses `max`, which is what
    the 500px fixture measures.
    """
    widths = list(minimums)
    extra = target - sum(widths)
    if extra <= 1e-9:
        return widths
    metrics["table_extra_width_distributed"] += 1
    capacity = [maximums[i] - minimums[i] for i in range(len(widths))]
    total_capacity = sum(capacity)
    span = range(len(widths))
    if extra <= total_capacity:
        _distribute(widths, span, extra, capacity)
        return widths
    _distribute(widths, span, total_capacity, capacity)
    _distribute(widths, span, extra - total_capacity, list(maximums))
    return widths


# --------------------------------------------------------------------------
# Sections 17.5 and 17.5.3: placing the boxes
# --------------------------------------------------------------------------


def layout_table_contents(
    table: Box, plan: TablePlan, *, metrics: Counter[str], layout_cell, account
) -> float:
    """Place every row, row group and cell. Returns the table's content
    height.

    Two callbacks rather than an import, for the reason `layout.linebox`
    takes a `layout_atomic`: `layout.block` imports this module, so this
    module cannot call back into it by name.

    * `layout_cell(cell, content_width)` lays a cell out as the block
      container it is and returns its border height. That is ordinary block
      layout and this module does not reimplement it.
    * `account(box)` books the counters `_layout_block` would have kept for
      a row or row-group box. Those two boxes are sized by the grid rather
      than by the constraint equation, so they do not go through
      `_layout_block` at all -- and a box that no counter saw would fail
      `layout.block`'s own box partition, which is what that partition is
      for.

    Heights, per section 17.5.3: "the height of a cell box is the minimum
    height required by the content", and the row's height is the maximum
    over its cells. The cell box is then **stretched to the row height**,
    which section 17.5.3 does not say and Chrome 151 does -- measured, a
    one-line cell beside an 80px sibling reports an 80px border box. This
    engine follows the browser here because the browser is what the
    comparison harness is.
    """
    from mayshay.layout.geometry import BoxGeometry, Edges, Rect
    from mayshay.layout.used import px_or_zero, style_of

    grid = plan.grid
    starts = _column_starts(plan)
    natural = [0.0] * len(grid.rows)

    # --- pass one: lay every cell out at its column width -----------------
    for cell in grid.cells:
        width = _spanned_width(plan, cell)
        style = style_of(cell.box)
        inside = (
            px_or_zero(style.border_left_width, basis=width, metrics=metrics)
            + px_or_zero(style.border_right_width, basis=width, metrics=metrics)
            + px_or_zero(style.padding_left, basis=width, metrics=metrics)
            + px_or_zero(style.padding_right, basis=width, metrics=metrics)
        )
        height = layout_cell(cell.box, max(0.0, width - inside))
        if cell.rowspan == 1:
            natural[cell.row] = max(natural[cell.row], height)
        if style.vertical_align != "top":
            # Section 17.5.3 aligns a cell's content within the row by its
            # baseline unless told otherwise, and the initial value IS
            # `baseline`. This engine puts every cell's content at the top,
            # which agrees with `baseline` exactly when every cell in the
            # row has the same first-baseline offset -- one line of one font
            # with equal padding, which is the common case and every case on
            # this corpus. Counted, not silent: 371 of the corpus's 401
            # cells compute `baseline` and 30 compute `top`, and `middle`
            # occurs zero times.
            metrics["table_cell_vertical_align_as_top"] += 1

    # --- row heights: section 17.5.3 --------------------------------------
    heights = list(natural)
    for index, row in enumerate(grid.rows):
        declared = style_of(row).height
        if isinstance(declared, Length) and declared.unit == "px":
            heights[index] = max(heights[index], float(declared.value))

    # --- pass two: position everything ------------------------------------
    tops: list[float] = []
    y = plan.spacing_y
    for index in range(len(grid.rows)):
        tops.append(y)
        y += heights[index] + plan.spacing_y
    content_height = y

    inner_x = plan.spacing_x
    inner_width = max(0.0, plan.content_width - 2 * plan.spacing_x)
    for index, row in enumerate(grid.rows):
        account(row)
        metrics["table_rows_laid_out"] += 1
        _rectangles(row, inner_x, tops[index], inner_width, heights[index])

    for group in table.children:
        if group.display not in ROW_GROUP_DISPLAYS:
            continue
        rows = [r for r in group.children if r.display == "table-row"]
        account(group)
        metrics["table_row_groups_laid_out"] += 1
        if not rows:
            _rectangles(group, inner_x, plan.spacing_y, inner_width, 0.0)
            continue
        first = grid.row_index[id(rows[0])]
        last = grid.row_index[id(rows[-1])]
        _rectangles(
            group,
            inner_x,
            tops[first],
            inner_width,
            tops[last] + heights[last] - tops[first],
        )

    for cell in grid.cells:
        geometry = cell.box.geometry
        if geometry is None:
            continue
        spanned = sum(heights[cell.row : cell.row + cell.rowspan])
        spanned += (cell.rowspan - 1) * plan.spacing_y
        _stretch(geometry, starts[cell.column], tops[cell.row], spanned)

    return content_height


def _column_starts(plan: TablePlan) -> list[float]:
    """The x of each column's left border edge, from the table's content
    origin. `spacing_x` before the first column and between every pair --
    which is the same `(columns + 1)` count the width formula uses, read
    the other way round."""
    starts: list[float] = []
    x = plan.spacing_x
    for width in plan.columns:
        starts.append(x)
        x += width + plan.spacing_x
    return starts


def _spanned_width(plan: TablePlan, cell: _PlacedCell) -> float:
    """A cell's border-box width: its columns, plus the spacings *between*
    them. Not `(colspan + 1)` spacings -- the ones outside the cell belong
    to its neighbours, and counting them is how a spanning cell ends up one
    spacing too wide with nothing else disagreeing."""
    span = range(cell.column, min(cell.column + cell.colspan, len(plan.columns)))
    return sum(plan.columns[i] for i in span) + max(0, len(span) - 1) * plan.spacing_x


def _rectangles(box: Box, x: float, y: float, width: float, height: float) -> None:
    """Give a row or row-group box its four boxes.

    All four coincide: section 17.5 says internal table elements have no
    margins, and rows and row groups have no padding either -- only cells
    do. A row *can* carry a border, which the separated model draws around
    the row's own edges; that border is not implemented and the geometry
    says so by leaving `used_border` at zero rather than by inventing an
    inset.
    """
    from mayshay.layout.geometry import BoxGeometry, Edges, Rect

    rect = Rect(x, y, width, height)
    zero = Edges(0.0, 0.0, 0.0, 0.0)
    box.geometry = BoxGeometry(
        content=rect,
        padding=rect,
        border=rect,
        margin=rect,
        used_margin=zero,
        used_padding=zero,
        used_border=zero,
        containing_block_width=width,
    )


def _stretch(geometry, x: float, y: float, border_height: float) -> None:
    """Move a laid-out cell to its grid position and grow it to the row.

    The cell was laid out at (0, 0) with its natural height; here it gets
    the column's x, the row's y, and the row's height. Growing the box
    means growing the **content** box downward and leaving the content
    itself where it is, which is `vertical-align: top`.
    """
    from dataclasses import replace as _replace

    extra = border_height - geometry.border.height
    geometry.border = _replace(geometry.border, x=x, y=y, height=border_height)
    geometry.margin = _replace(
        geometry.margin, x=x, y=y, height=border_height
    )
    geometry.padding = _replace(
        geometry.padding,
        x=x + geometry.used_border.left,
        y=y + geometry.used_border.top,
        height=geometry.padding.height + extra,
    )
    geometry.content = _replace(
        geometry.content,
        x=geometry.padding.x + geometry.used_padding.left,
        y=geometry.padding.y + geometry.used_padding.top,
        height=max(0.0, geometry.content.height + extra),
    )


# --------------------------------------------------------------------------
# The mechanical check
# --------------------------------------------------------------------------


def assert_table_constraints(box: Box, plan: TablePlan) -> None:
    """The one equation this module could get wrong unnoticed.

        sum(columns) + (columns + 1) * border-spacing == content width

    ...and, per row, that the cells tile it: each cell's border box starts
    at its column's left edge and is exactly as wide as the columns it
    spans plus the spacings between them.

    Read off the **rectangles**, not off the numbers the distribution
    produced, for the reason `layout.block`'s section 10.3.3 tiling is:
    a distribution that satisfies its own arithmetic while placing the cells
    against the wrong offsets passes a check that re-reads its own scalars,
    and fails this one. Verified by injection -- distributing a `colspan`
    cell's excess over `colspan + 1` columns, and dropping the spacing term
    from `_spanned_width`, are each caught here and nowhere else.
    """
    from mayshay.layout.geometry import EPSILON

    total = sum(plan.columns) + (len(plan.columns) + 1) * plan.spacing_x
    assert abs(total - plan.content_width) <= EPSILON * max(1.0, plan.content_width), (
        "the columns do not add up to the table's content width: "
        f"{total} != {plan.content_width} "
        f"({len(plan.columns)} columns, spacing {plan.spacing_x})"
    )
    if box.geometry is not None:
        assert abs(box.geometry.content.width - plan.content_width) <= EPSILON, (
            "the table box's content rectangle disagrees with its plan: "
            f"{box.geometry.content.width} != {plan.content_width}"
        )

    starts = _column_starts(plan)
    origin = box.geometry.content.x if box.geometry is not None else 0.0
    for cell in plan.grid.cells:
        geometry = cell.box.geometry
        if geometry is None:
            continue
        expected_x = origin + starts[cell.column]
        expected_width = _spanned_width(plan, cell)
        assert abs(geometry.border.x - expected_x) <= EPSILON, (
            f"cell at row {cell.row} column {cell.column} starts at "
            f"{geometry.border.x}, its column starts at {expected_x}"
        )
        assert abs(geometry.border.width - expected_width) <= EPSILON, (
            f"cell at row {cell.row} column {cell.column} is "
            f"{geometry.border.width} wide, its {cell.colspan} column(s) plus "
            f"spacing are {expected_width}"
        )
