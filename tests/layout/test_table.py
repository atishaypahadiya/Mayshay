"""Table layout -- Phase 3 Task E. CSS 2.1 chapter 17.

**Every fixture here is synthetic, and it has to be.** The corpus contains
29 tables, and measured against `src/mayshay/layout/table.py`'s own counters
*not one* of section 17.2.1's thirteen fixup rules fires more than four
times on it -- three anonymous rows, four anonymous cells, three anonymous
tables, and zero for the other ten. The structure the corpus has in bulk is
101 rows correctly parented by a table, which needs no fixup at all. So the
corpus can say a table renders; it cannot discriminate between two
implementations of this section, and `docs/synthetic-only-coverage.md`
carries a row per rule saying so.

Chrome 151 numbers, where they appear, came from `scripts/chrome_compare.py`
against a page that begins `<!doctype html>` and asserts
`document.compatMode == 'CSS1Compat'` before reporting anything --
`docs/measurement-hazards.md` instance fifteen. A table fixture without a
doctype is measured in quirks mode, where table layout genuinely differs.
"""

from __future__ import annotations

from collections import Counter

import pytest

from mayshay.cssparse.cascade import style_document
from mayshay.cssparse.media import Viewport
from mayshay.dom.node import Element
from mayshay.htmlparse.treebuilder import parse
from mayshay.layout import table as table_module
from mayshay.layout.boxtree import build_box_tree
from mayshay.layout.table import fix_up_tables

VIEWPORT = Viewport(1280, 1024)
RESET = "html,body{margin:0;padding:0}"


def fixed_up(body: str, css: str = "") -> tuple[object, Counter]:
    """`(root box, metrics)` after section 17.2.1 and 17.4 and nothing else.

    Deliberately stops before layout: this half of the module is a tree
    transformation, and asserting on geometry would let a structural defect
    hide behind a plausible rectangle.
    """
    document = parse(f"<!doctype html><style>{RESET}{css}</style>{body}")
    style_document(document, [], viewport=VIEWPORT)
    root, _ = build_box_tree(document)
    metrics: Counter = Counter()
    for name in table_module.COUNTER_NAMES:
        metrics[name] = 0
    fix_up_tables(root, metrics)
    return root, metrics


def shape(box, depth: int = 0) -> list[str]:
    """The box tree as `display@origin` lines, for asserting structure.

    Structure rather than geometry, and `origin` alongside `display`,
    because "an anonymous table-row" and "an element that computed
    `display: table-row`" are the same string otherwise -- and generating
    an anonymous box where one already exists is the exact failure mode
    stage two has.
    """
    out = [f"{'  ' * depth}{box.display}@{box.origin}"]
    for child in box.children:
        out.extend(shape(child, depth + 1))
    return out


def find(root, ident: str):
    for box in root.walk():
        if (
            box.origin == "element"
            and isinstance(box.node, Element)
            and box.node.attrs.get("id") == ident
        ):
            return box
    raise AssertionError(f"#{ident} produced no box")


def chain(root, *displays: str) -> bool:
    """Does a path of exactly these displays appear, parent to child?"""
    def walk(box, wanted):
        if not wanted:
            return True
        if box.display != wanted[0]:
            return False
        if len(wanted) == 1:
            return True
        return any(walk(child, wanted[1:]) for child in box.children)

    return any(walk(box, list(displays)) for box in root.walk())


# --------------------------------------------------------------------------
# Section 17.2.1, stage one: remove irrelevant boxes
# --------------------------------------------------------------------------


def test_a_table_column_discards_its_children():
    """Rule 1. A column box has no content -- its children are treated as
    if they had `display: none`.

    Written with `display: table-column` on a `<div>` rather than with
    `<col>`, and the difference is a measured one rather than a stylistic
    choice: `<col>` is a void element, so `<col><span>x</span></col>` parses
    with the span as the column's *sibling* and rule 1 has nothing to
    remove. Executed -- the HTML spelling produces a box tree in which this
    rule cannot fire at all.

    The text is asserted absent from the whole tree, not merely from the
    column: a rule that *moved* the child would satisfy the weaker check.
    """
    root, metrics = fixed_up(
        '<div style="display:table">'
        '<div style="display:table-column"><span>gone</span></div>'
        '<div style="display:table-row"><div style="display:table-cell">'
        "kept</div></div></div>"
    )
    assert metrics["table_fixup_removed_child_of_column"] == 1
    texts = [
        box.node.data
        for box in root.walk()
        if box.origin == "text" and box.node is not None
    ]
    assert "gone" not in texts
    assert "kept" in texts


def test_a_column_group_discards_everything_that_is_not_a_column():
    """Rule 2, and its negative half in the same fixture: the `<col>` stays
    and the `<div>` beside it goes. A rule that emptied the column group
    entirely would pass an assertion that only checked the `<div>`."""
    root, metrics = fixed_up(
        '<table><colgroup id=g><col><div>gone</div></colgroup>'
        "<tr><td>x</td></tr></table>"
    )
    assert metrics["table_fixup_removed_non_column_in_column_group"] == 1
    group = find(root, "g")
    assert [child.display for child in group.children] == ["table-column"]
    assert not any(
        box.origin == "text" and box.node is not None and box.node.data == "gone"
        for box in root.walk()
    )


def test_task_b_already_removed_the_white_space_rules_3_and_4_are_for():
    """**Rules 3 and 4 are unreachable in this engine**, and that is a
    finding rather than a gap.

    Task B's blank-run rule (CSS 2.1 section 9.2.1.1) discards a run of
    collapsible white space between block-level siblings, and every internal
    table box is block-level -- so the blank text between two `<td>`s is
    gone before `fix_up_tables` is called. Executed on the natural markup
    below: five runs discarded by Task B, zero removed here.

    This is the same shape Task D1 found for white-space collapsing, where
    "most collapse away entirely" turned out to be false because Task B had
    already taken that case. A rule reading zero because an earlier rule
    took its work is not the same as a rule reading zero because the input
    never occurs, and only the pairing says which.
    """
    document = parse(
        f"<!doctype html><style>{RESET}</style>"
        "<table>\n  <tr>\n    <td>a</td>\n    <td>b</td>\n  </tr>\n</table>"
    )
    style_document(document, [], viewport=VIEWPORT)
    root, boxtree_metrics = build_box_tree(document)
    assert boxtree_metrics["boxes_blank_text_discarded"] == 5

    metrics: Counter = Counter()
    fix_up_tables(root, metrics)
    assert metrics["table_fixup_removed_white_space_between_table_boxes"] == 0


def test_white_space_between_two_cells_is_removed_and_content_is_not():
    """Rules 3 and 4, applied as the one deletion they are, on a tree Task B
    has not already cleaned.

    The blank box is put back by hand for exactly the reason the test above
    records: the rule is correct, and nothing in this engine reaches it. A
    test that only used natural markup would pass against an empty
    implementation.

    Both halves in one fixture. The blank run between the first two cells is
    removed; the `\u00a0` between the next two is **not**, because CSS Text
    3 does not call U+00A0 white space. `str.strip()` does, and would delete
    a real separator.

    Written as an escape, never as a literal -- `docs/measurement-hazards.md`
    instances twelve and sixteen are both a literal U+00A0 that silently
    became U+0020 between the keyboard and the file.
    """
    document = parse(
        f"<!doctype html><style>{RESET}</style>"
        '<div id=r style="display:table-row">'
        '<div style="display:table-cell">a</div>'
        '<div style="display:table-cell">b</div>'
        '<div style="display:table-cell">c</div>'
        "</div>"
    )
    style_document(document, [], viewport=VIEWPORT)
    root, _ = build_box_tree(document)
    row = find(root, "r")
    assert [c.display for c in row.children] == ["table-cell"] * 3, (
        "Task B was expected to have discarded the NBSP-free blank runs"
    )

    from mayshay.dom.node import Text
    from mayshay.layout.boxtree import Box

    blank = Box(display="inline", origin="text", node=Text("   "))
    nbsp = Box(display="inline", origin="text", node=Text("\u00a0"))
    row.children = [row.children[0], blank, row.children[1], nbsp, row.children[2]]

    metrics: Counter = Counter()
    fix_up_tables(root, metrics)
    assert metrics["table_fixup_removed_white_space_between_table_boxes"] == 1
    # The NBSP survived, and stage two gave it an anonymous cell of its own
    # rather than leaving it bare in the row.
    kinds = [c.display for c in row.children]
    assert kinds == ["table-cell"] * 4
    survivors = [
        box.node.data
        for box in row.walk()
        if box.origin == "text" and box.node is not None
    ]
    assert "\u00a0" in survivors
    assert "   " not in survivors


# --------------------------------------------------------------------------
# Section 17.2.1, stage two: generate missing child wrappers
# --------------------------------------------------------------------------


def test_a_block_child_of_a_table_gets_an_anonymous_row_and_cell():
    """Stage two rules 1 and 3 together, which is the *only* way rule 3
    fires on this corpus: 17.2.1's opening sentence promises "at least three
    nested objects", and one pass over the source tree generates two.

    This is the shape the three Wikipedia `<figure>` elements have -- a
    `display: table` whose children are an `<a>` and a `<figcaption>` -- so
    it is the one stage-two rule with any corpus exercise at all, at three
    occurrences.
    """
    root, metrics = fixed_up(
        '<div id=t style="display:table"><div id=inner>x</div></div>'
    )
    assert metrics["table_fixup_anonymous_row_in_table"] == 1
    assert metrics["table_fixup_anonymous_cell_in_row"] == 1
    assert chain(root, "table", "table-row", "table-cell", "block")


def test_consecutive_non_table_children_share_one_anonymous_row():
    """"...and all consecutive siblings of C that are not proper table
    children." Two anonymous rows here would put the two `<div>`s on
    separate rows, which is a different rendering and a plausible one.

    The `<tr>` after them proves the run *ends*: a rule that swallowed
    everything would put the real row inside the anonymous one.
    """
    root, metrics = fixed_up(
        '<div id=t style="display:table">'
        "<div>one</div><div>two</div>"
        '<div style="display:table-row"><div style="display:table-cell">r</div></div>'
        "</div>"
    )
    assert metrics["table_fixup_anonymous_row_in_table"] == 1
    table = next(b for b in root.walk() if b.display == "table")
    assert [child.origin for child in table.children] == ["anonymous", "element"]
    anonymous = table.children[0]
    assert len(anonymous.children) == 1                      # one anonymous cell
    assert len(anonymous.children[0].children) == 2          # holding both divs


def test_a_non_row_child_of_a_row_group_gets_an_anonymous_row():
    """Stage two rule 2. Zero corpus occurrences -- every one of the corpus's
    24 row groups contains only rows."""
    root, metrics = fixed_up(
        '<div id=g style="display:table-row-group"><div>x</div></div>'
    )
    assert metrics["table_fixup_anonymous_row_in_row_group"] == 1
    assert chain(root, "table-row-group", "table-row", "table-cell", "block")


def test_a_well_formed_table_generates_no_anonymous_box_at_all():
    """The negative case, and the one that catches over-generation.

    Every stage-two counter must be zero here. A rule quantified over the
    wrong set -- `INTERNAL_TABLE_BOX` where the spec says "proper table
    child" -- generates an anonymous row around every caption and still
    renders something table-shaped.
    """
    root, metrics = fixed_up(
        "<table><caption>c</caption><colgroup><col></colgroup>"
        "<tbody><tr><td>a</td><td>b</td></tr></tbody></table>"
    )
    for name in table_module.COUNTER_NAMES:
        if name.startswith("table_fixup_"):
            assert metrics[name] == 0, name
    assert chain(root, "table", "table-row-group", "table-row", "table-cell")
    assert chain(root, "table", "table-column-group", "table-column")


# --------------------------------------------------------------------------
# Section 17.2.1, stage three: generate missing parents
# --------------------------------------------------------------------------


def test_an_orphan_cell_gets_a_row_and_then_a_table():
    """Stage three rules 1 and 2, in that order, and the order is the point:
    rule 1 gives the cell a row and rule 2 then gives the row a table. Run
    the other way round the cell ends up in a table with no row in it.

    **Zero corpus occurrences.** All 401 corpus cells already have a
    `table-row` parent, so the fixup rule every tutorial leads with is the
    one this corpus never exercises.
    """
    root, metrics = fixed_up(
        "<div>"
        '<div style="display:table-cell">a</div>'
        '<div style="display:table-cell">b</div>'
        "</div>"
    )
    assert metrics["table_fixup_anonymous_row_for_orphan_cell"] == 1
    assert metrics["table_fixup_anonymous_table_for_misparented_row"] == 1
    assert chain(root, "table", "table-row", "table-cell")
    row = next(b for b in root.walk() if b.display == "table-row")
    assert len(row.children) == 2, "both cells share one anonymous row"


@pytest.mark.parametrize(
    "display,counter",
    [
        ("table-row", "table_fixup_anonymous_table_for_misparented_row"),
        ("table-row-group", "table_fixup_anonymous_table_for_misparented_row_group"),
        ("table-column-group",
         "table_fixup_anonymous_table_for_misparented_column_group"),
        ("table-caption", "table_fixup_anonymous_table_for_misparented_caption"),
    ],
)
def test_each_misparented_proper_table_child_gets_an_anonymous_table(
    display, counter
):
    """Stage three rule 2's clauses, one test each rather than one test for
    the family. The clauses differ -- a `table-column` is legal inside a
    `table-column-group` and a row group is not legal anywhere but a table --
    so a single implementation of "is it misparented" that got one clause
    wrong would still pass a test that only checked a row.
    """
    root, metrics = fixed_up(f'<div><div id=x style="display:{display}">c</div></div>')
    assert metrics[counter] == 1
    assert metrics["table_wrapper_boxes"] == 1
    box = find(root, "x")
    assert box.display == display
    # ...and the generated table's WRAPPER is an ancestor of it. The wrapper
    # rather than the table box, because section 17.4 moves a caption out of
    # the table box and puts it beside one.
    wrapper = next(b for b in root.walk() if b.table_wrapper)
    assert any(b is box for b in wrapper.walk())


def test_a_table_column_inside_a_column_group_is_not_misparented():
    """The negative half of the `table-column` clause, which is the one that
    reads backwards: a `table-column` is misparented if its parent is
    neither a column group **nor a table**. Both legal parents asserted, so
    a clause that only allowed one of them fails."""
    root, metrics = fixed_up(
        "<table><colgroup><col></colgroup><col>"
        "<tr><td>x</td></tr></table>"
    )
    assert metrics["table_fixup_anonymous_table_for_misparented_column"] == 0


def test_a_row_whose_parent_is_a_table_is_not_misparented():
    """**Section 17.2.1 has no rule that generates an anonymous row group.**

    "A 'table-row' is misparented if its parent is neither a row group box
    nor a 'table' or 'inline-table' box." A row directly inside a table is
    correct, and this engine leaves it there -- as Chrome's box tree does
    for geometry purposes.

    This is the structure the corpus has 101 of, and it is worth its own
    test because it is the one a reader is most likely to think needs
    fixing: 96 of Hacker News's rows sit directly in a table, and an
    implementation that wrapped each of them in an anonymous row group
    would add 96 boxes no browser has and change nothing visible, which is
    the hardest kind of wrong to notice.
    """
    root, metrics = fixed_up(
        "<table><tr><td>a</td></tr><tr><td>b</td></tr></table>"
    )
    assert metrics["table_fixup_anonymous_table_for_misparented_row"] == 0
    assert metrics["table_rows_directly_in_a_table"] == 2
    table = next(b for b in root.walk() if b.display == "table")
    assert [c.display for c in table.children] == ["table-row", "table-row"]


def test_a_misparented_run_shares_one_anonymous_table():
    """"...and all consecutive siblings of C that are proper table
    children." Two row groups in a `<div>` are two sections of ONE table,
    not two tables -- which is a visible difference: two tables size their
    columns independently.
    """
    root, metrics = fixed_up(
        "<div>"
        '<div style="display:table-row-group"><div style="display:table-row">'
        '<div style="display:table-cell">a</div></div></div>'
        '<div style="display:table-row-group"><div style="display:table-row">'
        '<div style="display:table-cell">b</div></div></div>'
        "</div>"
    )
    assert metrics["table_fixup_anonymous_table_for_misparented_row_group"] == 1
    assert metrics["table_wrapper_boxes"] == 1
    tables = [b for b in root.walk() if b.display == "table"]
    assert len(tables) == 1
    assert len(tables[0].children) == 2


def test_a_misparented_child_of_an_inline_box_gets_an_inline_table():
    """"If C's parent is an 'inline' box, then T must be an 'inline-table'
    box; otherwise it must be a 'table' box."

    **The inline half is unreachable through `build_box_tree`**, measured
    rather than assumed: Task B's section 9.2.1.1 splitting runs first, and
    an inline box containing only block-level children *dissolves* --
    `<span><span style="display:table-cell">x</span></span>` reaches the
    fixup with the cell parented by `<body>`, and there is no inline box
    left to trigger the clause. The inline half is therefore driven on a
    box tree built by hand, which is what makes this a test of the rule
    rather than of Task B.

    The two halves are asserted against each other because an
    implementation that always generated `table` renders almost
    identically and differs only in whether the generated box sits on a
    line.
    """
    from mayshay.dom.node import Text
    from mayshay.layout.boxtree import Box

    natural, natural_metrics = fixed_up(
        '<span><span style="display:table-cell">x</span></span>'
    )
    assert natural_metrics["table_fixup_anonymous_inline_table"] == 0, (
        "Task B was expected to have dissolved the inline parent"
    )
    assert any(b.display == "table" for b in natural.walk())

    cell = Box(
        display="table-cell",
        origin="anonymous",
        children=[Box(display="inline", origin="text", node=Text("x"))],
    )
    inline_parent = Box(display="inline", origin="anonymous", children=[cell])
    root = Box(display="block", origin="anonymous", children=[inline_parent])
    metrics: Counter = Counter()
    fix_up_tables(root, metrics)
    assert metrics["table_fixup_anonymous_inline_table"] == 1
    assert any(b.display == "inline-table" for b in root.walk())
    assert not any(b.display == "table" for b in root.walk())


def test_a_nested_table_is_content_of_a_cell_not_a_row_of_the_outer_one():
    """The fixup runs bottom-up, and this is what depends on it.

    A `<table>` becomes a `block` wrapper (17.4). A `table` box is a proper
    table child; a `block` is not. So the inner table has to be *finished*
    before the outer one classifies it, or it stays a direct child of the
    outer table and is placed into the grid as though it were a row.
    """
    root, _ = fixed_up(
        '<div id=t style="display:table">'
        '<table id=inner><tr><td>x</td></tr></table>'
        "</div>"
    )
    outer = next(b for b in root.walk() if b.display == "table")
    assert [c.display for c in outer.children] == ["table-row"]
    assert chain(root, "table", "table-row", "table-cell", "block", "table")


# --------------------------------------------------------------------------
# Section 17.4: the table wrapper box
# --------------------------------------------------------------------------


def test_the_wrapper_takes_the_margins_and_the_table_box_takes_the_borders():
    """Section 17.4's split, asserted on both boxes at once.

    This is the one that would be invisible if it were half done: applying
    the margins to both boxes indents the table by twice its own margin,
    and applying the border to both draws it twice. The wrapper keeps the
    element's **identity** as well, because `DOM.getBoxModel` for a
    `<table>` answers with the box the margins are on.
    """
    root, metrics = fixed_up(
        '<table id=t style="margin:10px 20px;border:3px solid;padding:5px">'
        "<tr><td>x</td></tr></table>"
    )
    assert metrics["table_wrapper_boxes"] == 1
    wrapper = find(root, "t")
    assert wrapper.table_wrapper and wrapper.display == "block"

    inner = next(c for c in wrapper.children if c.display == "table")
    assert inner.origin == "anonymous" and inner.identity() is None

    from mayshay.layout.used import style_of

    outer_style, inner_style = style_of(wrapper), style_of(inner)
    assert outer_style.margin_left.value == 20
    assert outer_style.border_left_width.value == 0
    assert outer_style.padding_left.value == 0
    assert inner_style.margin_left.value == 0
    assert inner_style.border_left_width.value == 3
    assert inner_style.padding_left.value == 5


def test_the_split_does_not_mutate_the_elements_computed_style():
    """Two layouts of one document must agree. `_split_style` builds two new
    styles rather than editing the DOM's, and the DOM's is shared with the
    cascade -- so a mutating implementation would zero the table's margin on
    the first pass and lay it out differently on the second."""
    document = parse(
        f"<!doctype html><style>{RESET}</style>"
        '<table id=t style="margin-left:20px"><tr><td>x</td></tr></table>'
    )
    style_document(document, [], viewport=VIEWPORT)
    element = next(
        node
        for node in _walk_dom(document)
        if isinstance(node, Element) and node.tag_name == "table"
    )
    for _ in range(2):
        root, _unused = build_box_tree(document)
        fix_up_tables(root, Counter())
        assert element.computed_style.margin_left.value == 20
        assert element.computed_style.border_left_width.value == 0


def _walk_dom(node):
    yield node
    for child in node.children:
        yield from _walk_dom(child)


def test_a_caption_sits_before_or_after_the_table_box_per_caption_side():
    """Section 17.4, and the corpus's own shape: three of the four corpus
    captions compute `caption-side: bottom`, so both branches are real here
    rather than one being decorative.

    The caption's **own** `caption-side` decides, not the table's. The
    property inherits, so a caption that declares nothing agrees with its
    table anyway -- and one that declares `bottom` moves on its own.
    """
    top_root, _ = fixed_up("<table><caption id=c>x</caption><tr><td>a</td></tr></table>")
    top_wrapper = next(b for b in top_root.walk() if b.table_wrapper)
    assert [c.display for c in top_wrapper.children] == ["table-caption", "table"]

    bottom_root, _ = fixed_up(
        "<table><caption id=c>x</caption><tr><td>a</td></tr></table>",
        css="caption{caption-side:bottom}",
    )
    bottom_wrapper = next(b for b in bottom_root.walk() if b.table_wrapper)
    assert [c.display for c in bottom_wrapper.children] == ["table", "table-caption"]


def test_the_fixup_asserts_rather_than_looping_when_the_rules_disagree():
    """The convergence cap, driven from a tree no rule set can settle.

    With section 17.2.1's five sets as the spec defines them the recursion
    always terminates, because every box a stage generates makes its own
    children well-parented. Get one membership wrong and it does not:
    dropping `table-caption` from `PROPER_TABLE_CHILD` makes stage two wrap
    a caption in a row, stage three wrap that row's cell's caption in a
    table, and stage two wrap it again -- forever.

    That injection was run, and without the cap it **hung the test run**
    rather than failing it, which is the one outcome worse than a wrong
    answer. The cap is asserted here directly by handing the fixup a box
    already nested past the bound, so the check is exercised on every run
    rather than only when someone reintroduces the defect.
    """
    from mayshay.layout.boxtree import Box
    from mayshay.layout.table import _MAX_FIXUP_DEPTH, _fixup_own

    box = Box(display="table-row", origin="anonymous", children=[
        Box(display="block", origin="anonymous")
    ])
    with pytest.raises(AssertionError, match="did not converge"):
        _fixup_own(box, Counter(), _MAX_FIXUP_DEPTH + 1)


# --------------------------------------------------------------------------
# Sections 17.5.2.1 and 17.5.2.2: the width algorithms
# --------------------------------------------------------------------------
#
# Every expected number below was measured against **Chrome 151** with
# `scripts/chrome_compare.py`'s table suite before it was written here. The
# tolerance is three of Chrome's LayoutUnits (3/64 px), which is what
# `docs/fonts.md` derives for a horizontal comparison and is not a figure
# chosen to make a row pass -- the rows these fixtures discriminate between
# differ from each other by tens of pixels, not by hundredths.
#
# The stylesheet zeroes `border-spacing` and cell padding on most fixtures
# because HTML's UA sheet sets `border-spacing: 2px` and `td { padding:
# 1px }` in a browser and this engine's UA sheet carries neither. Two
# fixtures deliberately do NOT zero them, so that the harness cannot be
# agreeing with itself about a shared precondition -- which is
# `docs/measurement-hazards.md` instance fifteen's first corollary: vary
# what the fixtures share, not only what they contain.

TABLE_RESET = RESET + "table{border-spacing:0}td,th{padding:0}"

#: Chrome's LayoutUnit is 1/64px, and it quantises per column.
LAYOUT_UNIT = 1.0 / 64.0
TOLERANCE = 3 * LAYOUT_UNIT


def laid_out(body: str, css: str = "", viewport: Viewport = VIEWPORT):
    from mayshay.layout.block import layout_document

    document = parse(f"<!doctype html><style>{TABLE_RESET}{css}</style>{body}")
    style_document(document, [], viewport=viewport)
    root, _ = build_box_tree(document)
    metrics = layout_document(root, viewport)
    return root, metrics


def columns(root) -> list[float]:
    plan = next(b.table_plan for b in root.walk() if b.table_plan is not None)
    return list(plan.columns)


def close(got, expected, note: str = "") -> None:
    assert len(got) == len(expected), f"{note}: {got} vs {expected}"
    for index, (a, b) in enumerate(zip(got, expected)):
        assert abs(a - b) <= TOLERANCE, (
            f"{note}column {index}: {a} != {b} (delta {abs(a - b):.6f}px, "
            f"tolerance {TOLERANCE:.6f})"
        )


def test_a_colspan_cell_widens_the_columns_it_spans_in_proportion():
    """Section 17.5.2.2: "For each cell that spans more than one column,
    increase the minimum widths of the columns it spans so that together,
    they are at least as wide as the cell."

    Built so the candidate rules disagree. Both columns hold one unbreakable
    word, so min equals max and the only thing that can move them is the
    span. Equal shares give 79.19 / 321.22 and proportional gives
    66.66 / 333.34; **Chrome 151 gives 66.6563 / 333.3438**, so the spec's
    "approximately the same amount" is not the equal reading.

    An implementation that put the span's whole width on the column it
    starts in gives 400 / 0, which is what 12 of the corpus's 27 laid-out
    tables would have got.
    """
    root, metrics = laid_out(
        "<table><tr><td>WWWW</td><td>WWWWWWWWWWWWWWWWWWWW</td></tr>"
        '<tr><td colspan=2 style="width:400px">x</td></tr></table>'
    )
    close(columns(root), [66.6563, 333.3438], "colspan over two: ")
    assert metrics["table_cells_spanning_columns"] == 1
    assert metrics["table_colspan_excess_distributed"] == 1


def test_a_colspan_over_three_columns_keeps_their_proportions():
    """The same rule over three columns wanting 2, 4 and 8 glyph-widths.
    Chrome 151: 85.7031 / 171.4219 / 342.875, which is 1 : 2 : 4 -- the
    proportions the columns started with, preserved exactly.

    Two columns cannot tell "proportional" from several other rules that
    happen to agree on a 2-way split; three can.
    """
    root, _ = laid_out(
        "<table><tr><td>WW</td><td>WWWW</td><td>WWWWWWWW</td></tr>"
        '<tr><td colspan=3 style="width:600px">x</td></tr></table>'
    )
    close(columns(root), [85.7031, 171.4219, 342.875], "colspan over three: ")


def test_spanning_cells_are_considered_after_the_others_and_in_span_order():
    """Section 17.5.2.2 considers spanning cells after non-spanning ones, and
    this fixture makes the *order among spans* observable: a `colspan=2`
    wanting 200 and a `colspan=3` wanting 400 over three equal columns.

    Narrow-first gives 173.75 / 173.75 / 52.5 -- the two-column span widens
    columns 0 and 1 to 100 each, and the three-column span then divides
    proportionally over 100 / 100 / 30.2. **Chrome 151 gives exactly that.**
    Widest-first would give three equal columns of 133.3, which is a
    different and entirely plausible-looking table.
    """
    root, _ = laid_out(
        "<table><tr><td>WW</td><td>WW</td><td>WW</td></tr>"
        '<tr><td colspan=2 style="width:200px">x</td><td>WW</td></tr>'
        '<tr><td colspan=3 style="width:400px">y</td></tr></table>'
    )
    close(columns(root), [173.75, 173.75, 52.5], "two spans: ")


def test_a_colspan_cell_narrower_than_its_columns_moves_nothing():
    """The negative case, and the reason a wrong distribution is invisible:
    40 of the corpus's 52 laid-out spanning cells fall here. Both counters
    asserted, so "we widened nothing" and "we never looked" stay apart.

    Chrome 151: two columns of 151.0156, table 302.0313."""
    root, metrics = laid_out(
        "<table><tr><td>WWWWWWWWWW</td><td>WWWWWWWWWW</td></tr>"
        "<tr><td colspan=2>x</td></tr></table>"
    )
    close(columns(root), [151.0156, 151.0156], "unwidened: ")
    assert metrics["table_colspan_excess_distributed"] == 0
    assert metrics["table_colspan_absorbed_without_widening"] == 1


def test_an_auto_width_table_shrinks_to_fit_and_does_not_fill():
    """Section 17.5.2's own warning: "if the margins of a table are set to
    '0' and the width to 'auto', the table will not automatically size to
    fill its containing block."

    Both directions in one test. In a 600px block a one-cell table is
    17.7969 wide -- its content -- and in a 120px block a table whose
    max-content is wider takes the whole 120. Chrome 151 gives both.
    A table that filled its containing block passes the second and fails
    the first, which is why the first is here.
    """
    wide, _ = laid_out(
        '<div style="width:600px"><table><tr><td>ab</td></tr></table></div>'
    )
    close(columns(wide), [17.7969], "auto width, room to spare: ")

    narrow, _ = laid_out(
        '<div style="width:120px"><table><tr>'
        "<td>alpha beta gamma delta</td></tr></table></div>"
    )
    close(columns(narrow), [120.0], "auto width, constrained: ")


def test_extra_width_fills_each_columns_headroom_before_anything_else():
    """The table's own `width` distributed over the columns, at a width
    **between MIN and MAX** -- which is where the candidate rules disagree.

    Column 1 is one unbreakable word, so its min equals its max and it has
    no headroom at all. A 100px table over MIN 98.66 and MAX 216.98 must
    therefore put all 1.34px of slack on column 2. Chrome 151: 45.3125 /
    54.6875. Distributing in proportion to `max` instead would give column 1
    20.9px, which is below its own minimum -- a rule that cannot be right
    and that a fixture with two flexible columns would never have caught.
    """
    root, _ = laid_out(
        '<table style="width:100px"><tr><td>WWW</td>'
        "<td>alpha beta gamma delta</td></tr></table>"
    )
    close(columns(root), [45.3125, 54.6875], "one rigid column: ")


def test_extra_width_is_shared_in_proportion_to_headroom():
    """The same rule with both columns able to grow: a 260px table over MIN
    71.14 and MAX 287.31. Chrome 151: 55.0781 / 204.9219, which is the
    minimums plus the slack shared in proportion to `max - min`."""
    root, metrics = laid_out(
        '<table style="width:260px"><tr><td>aa bb cc</td>'
        "<td>alpha beta gamma delta epsilon</td></tr></table>"
    )
    close(columns(root), [55.0781, 204.9219], "two flexible columns: ")
    assert metrics["table_extra_width_distributed"] == 1


def test_a_table_wider_than_its_max_content_shares_the_rest_by_max():
    """Phase two: past every column's max there is no headroom left to be
    proportional to, so `max` decides. Chrome 151 for a 500px table over
    columns wanting 17.80 and about 130: 60.2656 / 439.7344."""
    root, _ = laid_out(
        '<table style="width:500px"><tr><td>aa</td>'
        "<td>a much longer cell</td></tr></table>"
    )
    close(columns(root), [60.2656, 439.7344], "past max-content: ")


def test_fixed_layout_takes_the_first_row_and_ignores_the_rest():
    """Section 17.5.2.1: a first-row cell's `width` sets its column and the
    remaining columns divide what is left equally. Chrome 151 for a 400px
    table whose first cell is 100px wide: 100 / 150 / 150.

    **Zero corpus coverage.** Not one of the three corpus pages' stylesheets
    contains a `table-layout` declaration of any value, so this is a
    `docs/synthetic-only-coverage.md` row.

    The second row is deliberately wider in content than the first: fixed
    layout must ignore it, and an implementation that fell through to the
    automatic algorithm would not.
    """
    root, metrics = laid_out(
        '<table style="table-layout:fixed;width:400px">'
        '<tr><td style="width:100px">a</td><td>b</td><td>c</td></tr>'
        "<tr><td>WWWWWWWWWWWWWWWWWWWWWWWW</td><td>W</td><td>W</td></tr></table>"
    )
    close(columns(root), [100.0, 150.0, 150.0], "fixed: ")
    assert metrics["table_layout_fixed"] == 1
    assert metrics["table_layout_automatic"] == 0


def test_fixed_layout_with_an_auto_width_falls_back_and_says_so():
    """Section 17.5.2.1: "A value of 'auto' ... means use the automatic
    table layout algorithm." CSS 2.1 then *permits* a UA to apply fixed
    layout to an auto-width block-level table anyway; Chrome 151 does not --
    measured, such a table in a 500px block came out 17.8125 wide, which is
    its content and not its containing block.

    Counted rather than silent, because the two algorithms disagree on every
    table they are both given.
    """
    root, metrics = laid_out(
        '<div style="width:500px"><table style="table-layout:fixed">'
        "<tr><td>a</td><td>b</td></tr></table></div>"
    )
    close(columns(root), [8.9063, 8.9063], "fixed with auto width: ")
    assert metrics["table_layout_fixed_fallback_auto_width"] == 1
    assert metrics["table_layout_fixed"] == 0
    assert metrics["table_layout_automatic"] == 1


def test_a_percentage_cell_width_is_treated_as_auto_and_counted():
    """Section 17.5.2.2: "A percentage value for a column width is relative
    to the table width" -- which is the number the algorithm is running to
    find. Treated as `auto` and counted; 103 of the corpus's 401 cells take
    this branch, so it is the best-exercised deliberate approximation in
    this module.

    The negative half matters as much: an explicit *length* on the same
    cell must still be honoured, or this test would pass against an
    implementation that ignored `width` on cells entirely.
    """
    percentage, metrics = laid_out(
        '<table style="width:400px"><tr><td style="width:90%">a</td>'
        "<td>b</td></tr></table>"
    )
    assert metrics["table_cell_percentage_width_as_auto"] == 1
    assert abs(columns(percentage)[0] - 360.0) > 1.0, (
        "a percentage cell width must not have resolved against the table"
    )

    length, length_metrics = laid_out(
        '<table style="width:400px"><tr><td style="width:300px">a</td>'
        "<td>b</td></tr></table>"
    )
    assert length_metrics["table_cell_percentage_width_as_auto"] == 0
    assert columns(length)[0] >= 300.0


# --------------------------------------------------------------------------
# Sections 17.4, 17.5 and 17.5.3: where the boxes end up
# --------------------------------------------------------------------------


def rect(root, tag: str, nth: int = 0):
    """The border rectangle of the box that carries this element.

    For `<table>` that is the section 17.4 **wrapper**, whose display is
    `block` -- it is the box the element's identity is on and the box CDP
    answers for. The table box inside it is anonymous and has no
    `tag_name`, so it never matches here, which is the distinction this
    helper exists to keep straight.
    """
    found = [
        box.geometry.border
        for box in root.walk()
        if box.geometry is not None
        and getattr(box.node, "tag_name", None) == tag
    ]
    return found[nth]


def test_border_spacing_sits_outside_the_columns_as_well_as_between_them():
    """**This fixture does not share the harness's zeroed `border-spacing`,
    on purpose.**

    Every other table fixture here sets `border-spacing: 0`, which makes
    them agree about a precondition rather than about a result -- and a
    `(columns + 1)` spacing term that had been written as `(columns - 1)`
    would be invisible in all of them at once.
    `docs/measurement-hazards.md` instance fifteen: seven agreeing fixtures
    through one harness are one observation.

    Chrome 151 with `border-spacing: 10px 20px` over two 8.9063px columns:
    table 47.8125 wide and 96 tall, rows at y=20 and y=58, each row x=10 and
    27.8125 wide, cells at x=10 and x=28.9063. Every one of those numbers
    contains the spacing in a different arrangement.
    """
    root, _ = laid_out(
        '<table style="border-spacing:10px 20px">'
        "<tr><td>a</td><td>b</td></tr><tr><td>c</td><td>d</td></tr></table>"
    )
    table = rect(root, "table")
    # 2 columns x 8.8984 + 3 x 10 spacing.
    assert abs(table.width - 47.7969) <= TOLERANCE
    rows = [
        box.geometry.border
        for box in root.walk()
        if box.display == "table-row" and box.geometry is not None
    ]
    assert [round(r.x, 4) for r in rows] == [10.0, 10.0]
    assert abs(rows[0].y - 20.0) <= TOLERANCE
    assert abs(rows[1].y - 58.3984) <= TOLERANCE      # Chrome 58, hhea rounding
    assert abs(rows[0].width - 27.7969) <= TOLERANCE
    cells = [
        box.geometry.border
        for box in root.walk()
        if box.display == "table-cell" and box.geometry is not None
    ]
    assert abs(cells[0].x - 10.0) <= TOLERANCE
    assert abs(cells[1].x - 28.8984) <= TOLERANCE     # Chrome 28.9063
    assert abs(cells[0].y - 20.0) <= TOLERANCE


def test_a_table_in_the_separated_model_has_border_and_padding():
    """The second fixture that varies a shared precondition: this one gives
    the table a border and padding as well as a spacing, so the three are
    composed rather than each checked alone.

    Chrome 151 with `border:5px; padding:7px; border-spacing:3px` over two
    17.7969px columns: table 68.5938 x 48, row at x=15 y=15 and 38.5938
    wide, cells at x=15 and x=35.7969.

    CSS 2.1 section 17.6.1 says a table "does not have padding" -- in the
    **collapsing** model, which is what that sentence is about. In the
    separated model it does, and Chrome agrees; a reader who took the
    sentence at face value would have subtracted 14px from every number
    here.
    """
    root, _ = laid_out(
        '<table style="border:5px solid;padding:7px;border-spacing:3px">'
        "<tr><td>aa</td><td>bb</td></tr></table>"
    )
    table = rect(root, "table")
    assert abs(table.width - 68.5938) <= TOLERANCE
    cells = [
        box.geometry.border
        for box in root.walk()
        if box.display == "table-cell" and box.geometry is not None
    ]
    assert abs(cells[0].x - 15.0) <= TOLERANCE
    assert abs(cells[1].x - 35.7969) <= TOLERANCE


def test_a_cell_stretches_to_the_row_height():
    """Section 17.5.3 says "the height of a cell box is the minimum height
    required by the content", and Chrome does not do that: a one-line cell
    beside an 80px sibling reports an 80px border box.

    This engine follows the browser, because the browser is what the
    comparison harness is and a cell that stopped at its content height
    would disagree with every table on every page. Stated here rather than
    left as a silent choice.
    """
    root, _ = laid_out(
        "<table><tr><td>one</td>"
        '<td style="height:80px">tall</td></tr></table>'
    )
    cells = [
        box.geometry.border
        for box in root.walk()
        if box.display == "table-cell" and box.geometry is not None
    ]
    assert [c.height for c in cells] == [80.0, 80.0]


def test_a_shrink_wrapped_table_still_centres_with_auto_margins():
    """Section 17.5.2: "once the calculated value of 'width' for the table
    is found ... then the other parts of section 10.3 do apply. Therefore a
    table can be centered using left and right 'auto' margins."

    Which is why the wrapper's width is fed through the constraint equation
    as though it had been declared rather than through the bypass an atomic
    inline uses. Chrome 151 puts a 17.7969px table with `margin: 0 auto` at
    x=291.0938 in a 600px block; the exact half is 291.1016, and the 0.0078
    between them is one and a quarter LayoutUnits of Chrome's own rounding.
    """
    # A 600px viewport and no wrapping `<div>`: a 600px div inside a 1280px
    # body is itself over-constrained, and its own counter would be read as
    # the table's. Same reasoning as `test_block.py`'s `NARROW`.
    root, metrics = laid_out(
        '<table style="margin:0 auto"><tr><td>ab</td></tr></table>',
        viewport=Viewport(600, 800),
    )
    table = rect(root, "table")
    assert abs(table.x - 291.0938) <= TOLERANCE
    assert metrics["width_margins_centred"] == 1
    # ...and the table's own over-constraint is NOT reported as an author
    # error, which is what a shared counter would have said 32 times.
    assert metrics["width_over_constrained_margin_right_ignored"] == 0
    assert metrics["table_width_remainder_to_margin_right"] == 0


def test_the_table_elements_rectangle_includes_its_caption():
    """Section 17.4's wrapper box, measured rather than assumed.

    Chrome 151 for a table with a 30px caption above a 20px row: the
    `<table>` element's rect is 50px tall and starts at the caption. So the
    box CDP answers for a `<table>` is the wrapper, which is why the wrapper
    carries the element identity and the table box inside it is anonymous.
    Had it been the other way round, every Chrome comparison of a captioned
    table would have compared two different rectangles and called the
    difference a layout error.
    """
    root, _ = laid_out(
        '<table><caption style="height:30px">c</caption>'
        '<tr><td style="height:20px">a</td></tr></table>'
    )
    wrapper = next(b for b in root.walk() if b.table_wrapper)
    assert wrapper.geometry.border.height == 50.0
    assert wrapper.geometry.border.y == 0.0
    inner = next(c for c in wrapper.children if c.display == "table")
    assert inner.geometry.border.y == 30.0


def test_a_row_group_spans_its_rows_and_rows_nest_inside_it():
    """A `<thead>` and a `<tbody>` share one grid, and each group's box
    covers exactly its own rows. Row indices are global to the table, not
    per group -- numbering them per group would put two cells in one slot
    the first time a table had a header.
    """
    root, metrics = laid_out(
        "<table><thead><tr><td>h</td></tr></thead>"
        "<tbody><tr><td>a</td></tr><tr><td>b</td></tr></tbody></table>"
    )
    assert metrics["table_row_groups_laid_out"] == 2
    assert metrics["table_rows_laid_out"] == 3
    head = rect(root, "thead")
    body = rect(root, "tbody")
    assert head.y == 0.0
    assert body.y == head.height
    assert abs(body.height - 2 * head.height) <= TOLERANCE


def test_a_rowspan_cell_occupies_its_slots_so_neighbours_land_correctly():
    """`rowspan` grid occupancy, which is a **width** rule and not a height
    one: without it, the cell in the second row starts at column 0 instead
    of column 1 and the whole table's column widths are wrong.

    **Zero corpus coverage** -- executed over all 401 corpus cells, not one
    has `rowspan > 1`. Distributing a spanning cell's height across the rows
    it covers is not implemented and is counted.
    """
    root, metrics = laid_out(
        "<table>"
        '<tr><td rowspan=2>WWWWWWWWWW</td><td>a</td></tr>'
        "<tr><td>b</td></tr></table>"
    )
    assert metrics["table_cells_spanning_rows"] == 1
    assert metrics["table_rowspan_height_not_distributed"] == 1
    assert metrics["table_columns"] == 2
    cells = [
        box
        for box in root.walk()
        if box.display == "table-cell" and box.geometry is not None
    ]
    # The second row's only cell is in COLUMN 1, beside the spanning cell,
    # not underneath it at column 0.
    assert cells[2].geometry.border.x == cells[1].geometry.border.x


def test_the_column_widths_add_up_to_the_table_width_on_every_fixture():
    """The mechanical check, exercised directly rather than only as a side
    effect. `assert_table_constraints` already runs on every layout in this
    file; this asserts that it is checking something -- that the equation
    holds for a table with spacing, spans, groups and a caption at once.
    """
    from mayshay.layout.table import assert_table_constraints

    root, _ = laid_out(
        '<table style="border-spacing:4px 6px;width:500px">'
        "<caption>c</caption>"
        "<thead><tr><td>a</td><td>b</td><td>c</td></tr></thead>"
        '<tbody><tr><td colspan=2>wide</td><td>d</td></tr></tbody></table>'
    )
    box = next(b for b in root.walk() if b.table_plan is not None)
    plan = box.table_plan
    assert_table_constraints(box, plan)
    assert abs(
        sum(plan.columns) + 4 * plan.spacing_x - plan.content_width
    ) < 1e-9
    assert abs(box.geometry.content.width - plan.content_width) < 1e-9


# --------------------------------------------------------------------------
# The three fixtures that exist because an injection was a no-op
# --------------------------------------------------------------------------
#
# All three were added after an injection ran green, and all three failed for
# the same reason: every fixture above sets `border-spacing: 0`, so a bug in
# the spacing arithmetic of a *spanning* cell was invisible in all of them at
# once. `docs/measurement-hazards.md` instance fifteen's first corollary is
# exactly this -- the fixtures varied their input and shared their
# precondition, and the shared thing was the one that could be wrong.


def test_a_spanning_cell_is_as_wide_as_its_columns_plus_the_gaps_between():
    """A `colspan=2` cell's border box covers two columns and the **one**
    spacing between them -- not the ones outside it, which belong to its
    neighbours.

    Chrome 151 with `border-spacing: 12px`: columns 64.6563 and 323.3438,
    which sum to 388, and the spanning cell is 400 wide -- 388 plus one
    12px gap, exactly its declared width. The table is 424: 388 plus three
    gaps.

    Injection `w3` -- `+ len(span) * spacing` instead of
    `+ (len(span) - 1) * spacing` -- passed the entire suite before this
    existed.
    """
    root, _ = laid_out(
        '<table style="border-spacing:12px">'
        "<tr><td>WWWW</td><td>WWWWWWWWWWWWWWWWWWWW</td></tr>"
        '<tr><td colspan=2 style="width:400px">x</td></tr></table>'
    )
    close(columns(root), [64.6563, 323.3438], "colspan with spacing: ")
    cells = [
        box.geometry.border
        for box in root.walk()
        if box.display == "table-cell" and box.geometry is not None
    ]
    assert abs(cells[2].width - 400.0) <= TOLERANCE, "the spanning cell"
    assert abs(rect(root, "table").width - 424.0) <= TOLERANCE


def test_a_specified_cell_width_is_a_floor_under_its_min_content_not_a_swap():
    """Section 17.5.2.2: "If the specified 'width' (W) of the cell is
    greater than MCW, W is the minimum cell width." Greater than -- so a W
    *smaller* than the content changes nothing, and the content may not
    overflow the cell.

    Chrome 151 for `<td style="width:10px">` around ten `W` glyphs: the
    column is 151.0156, not 10. This is the one place where CSS Sizing 3's
    rule for an ordinary box and CSS 2.1's rule for a cell genuinely
    disagree, which is why `intrinsic.outer_sizes` grew
    `ignore_specified_width` rather than this being read off its default.

    Injection `w10` -- assigning W instead of taking the maximum -- passed
    the entire suite before this existed.
    """
    root, _ = laid_out(
        '<table><tr><td style="width:10px">WWWWWWWWWW</td>'
        "<td>WW</td></tr></table>"
    )
    close(columns(root), [151.0156, 30.2031], "width below min-content: ")


def test_fixed_layout_takes_the_spacing_out_of_a_spanning_cells_share():
    """Section 17.5.2.1: "If the cell spans more than one column, the width
    is divided over the columns." The spacings *inside* the cell come off
    before the division, or each column gets a share that is too large and
    the cell ends up wider than it asked for.

    Chrome 151 for a 400px fixed table with `border-spacing: 20px` and a
    first-row `colspan=2` cell of 200px: the spanning cell is 200 wide
    (90 + 20 + 90) and the third column takes the remaining 140.
    Dividing 200 by 2 without the gap gives 100 each, a 220px cell and a
    120px third column -- all three numbers wrong and all three plausible.

    Injection `w12` passed the entire suite before this existed. Fixed
    layout has zero corpus coverage, so this fixture is the only thing
    between that rule and nobody noticing.
    """
    root, metrics = laid_out(
        '<table style="table-layout:fixed;width:400px;border-spacing:20px">'
        '<tr><td colspan=2 style="width:200px">a</td><td>b</td></tr></table>'
    )
    assert metrics["table_layout_fixed"] == 1
    close(columns(root), [90.0, 90.0, 140.0], "fixed with a span: ")
    cells = [
        box.geometry.border
        for box in root.walk()
        if box.display == "table-cell" and box.geometry is not None
    ]
    assert abs(cells[0].width - 200.0) <= TOLERANCE
    assert abs(cells[1].width - 140.0) <= TOLERANCE
