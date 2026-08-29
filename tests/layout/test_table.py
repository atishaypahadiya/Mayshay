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
