"""Box tree construction -- Phase 3 Task B.

The tree layout walks, built once from the styled DOM so no later stage
re-derives it. This module builds *structure only*: no positions, no sizes,
no line breaking. Tasks C through F add geometry.

Three things happen here that are cheaper to get right now than to retrofit.

**`display: none` prunes by non-descent.** A `none` element contributes no
box and neither does anything beneath it, whatever those descendants
computed, so the builder never walks into the subtree. Visiting and
skipping would be slower and would consult `display` on nodes that should
not be reached at all. On the corpus that is 342 pruning roots and 954
elements -- 11.1% of them -- removed before any layout runs.

**Anonymous boxes break DOM isomorphism.** A block container holding both
block-level and inline-level children wraps each run of inline children in
an anonymous block; an inline box containing a block-level box is split
around it (CSS 2.1 section 9.2.1.1). Neither anonymous box corresponds to a
DOM node, so the box tree is no longer isomorphic to the DOM -- which is
exactly what the Chrome comparison's node identity depends on. See
`BoxOrigin` below for how that is resolved.

**`grid` falls back to `block`** (and `inline-grid` to `inline-block`),
counted in `boxes_grid_fallback`. Two elements on the current corpus, so it
is nearly free; the counter is what says when it stops being.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Literal

from mayshay.dom.node import Comment, Document, DocumentType, Element, Node, Text
from mayshay.layout.text import is_white_space_only

# Inline-level outer display types. Everything else that generates a box is
# block-level for our purposes, including the internal table displays --
# Task E gives those their own handling; here they only need to not be
# mistaken for inline content.
INLINE_LEVEL: frozenset[str] = frozenset(
    {"inline", "inline-block", "inline-flex", "inline-table"}
)

# Inline-level on the outside, a block container on the inside (CSS Display
# 3 section 2.1). The distinction from `INLINE_LEVEL` is load-bearing in
# three places and using the wrong set was a real Task B defect: an atomic
# inline does **not** split around a block child, its width is
# shrink-to-fit rather than absent, and it is opaque to the white-space
# collapsing of the inline formatting context it sits in -- it establishes
# its own.
ATOMIC_INLINE_DISPLAYS: frozenset[str] = frozenset(
    {"inline-block", "inline-flex", "inline-table"}
)

# Grid is classified but not implemented. The fallback is deliberate and
# counted rather than silent: `display: grid` laid out as a block puts the
# children in the wrong place, and the counter is the only thing that says
# so.
GRID_FALLBACK: dict[str, str] = {"grid": "block", "inline-grid": "inline-block"}

BoxOrigin = Literal["element", "text", "anonymous"]


@dataclass
class Box:
    """One box.

    `origin` is an explicit discriminator rather than something a caller
    infers from `node is None`. The distinction is load-bearing for the
    Chrome comparison: `DOM.getBoxModel` and `DOM.getContentQuads` are keyed
    by DOM node and Chrome does not expose its anonymous boxes through CDP
    at all, so an anonymous box has no counterpart to compare against. It is
    excluded from the comparison and **counted**, so the exclusion is a
    number rather than a gap.

    `ordinal` and `path` are assigned from the DOM, not from the box tree,
    and cover every element including `display: none` ones. Both engines
    must derive identity the same way or the comparison is meaningless, and
    Chrome's DOM contains the hidden elements too.

    `fragment` exists now although Task B always emits 0. A wrapping inline
    produces one box per line in Task D, and Chrome returns one quad per
    fragment for the same node; the representation has to be able to say
    "fragment 2 of node N" before there are any fragments to say it about.
    """

    display: str
    origin: BoxOrigin
    node: Node | None = None
    children: list["Box"] = field(default_factory=list)
    ordinal: int | None = None
    path: str | None = None
    fragment: int = 0

    # Filled by Task C (`layout.block`) with a `BoxGeometry`: all four box
    # edges in absolute document coordinates, per the Phase 3 comparison
    # contract. Untyped here on purpose -- `layout.block` imports this
    # module, so naming its type would be a cycle, and this module builds
    # structure only. `None` means "not laid out", which is a real state:
    # out-of-flow boxes and everything inside an inline formatting context
    # are deferred to Task D and counted rather than given a guessed
    # rectangle.
    geometry: object | None = None

    # Filled by Task D1 (`layout.inline`) on a text box: the source text
    # after CSS Text 3 Phase I white-space collapsing, which is what
    # `measure()` is given and what line breaking will break. `None` means
    # "not processed" and is a real state -- it is what a box outside any
    # inline formatting context has -- so it is distinguishable from `""`,
    # a run that collapsed away entirely. 1,323 boxes on the corpus turn on
    # exactly that distinction.
    text: str | None = None

    # Filled by Task D2 (`layout.linebox`) on an inline-level box: one
    # `InlineFragment` per line box it appears on. Separate from `geometry`
    # and not summarised into it, because the summary is a trap:
    # `DOM.getBoxModel` answers a wrapping inline with the UNION of its
    # fragments, which matches none of them, and a comparison built on that
    # union would validate nothing while looking like it worked. See
    # `docs/measurement-hazards.md` instance 3. A block-level box has
    # `geometry` and no fragments; an inline box has fragments and no
    # `geometry`; an atomic inline has `geometry` and exactly one fragment,
    # because it is a block container that happens to sit on a line.
    fragments: list = field(default_factory=list)

    # Filled by Task D2 on a box that establishes an inline formatting
    # context: its `LineBox`es in order. Untyped for the same reason
    # `geometry` is -- `layout.linebox` imports this module.
    line_boxes: list | None = None

    # Filled by Task E (`layout.table`) on the two boxes it invents that
    # cannot take their style from a DOM node.
    #
    # `style` overrides what `layout.used.style_of` would read. It is needed
    # because CSS 2.1 section 17.4 **splits one element's style across two
    # boxes**: a table generates a table WRAPPER box carrying the element's
    # `margin-*`, `position` and `float`, and a table box inside it carrying
    # everything else -- the borders, the padding, the width. One
    # `computed_style` cannot serve both, and applying the margins twice
    # would indent every table by double its own margin.
    #
    # `table_wrapper` marks the outer of that pair. It is a discriminator
    # rather than something inferred from "a block box with one table
    # child", for the reason `origin` is: the inference is right until an
    # author writes a `display: table` element inside a plain `<div>` with
    # nothing else in it, and then it is silently wrong.
    style: object | None = None
    table_wrapper: bool = False

    # Filled by Task E on a `table` box: its `TablePlan` -- the grid, the
    # column widths and the border spacing, decided by CSS 2.1 section
    # 17.5.2 before any box in the table has geometry. It lives on the box
    # rather than in a parameter threaded through `_layout_block` because
    # the wrapper computes it and the table box one level down consumes it,
    # and rather than in a module-level map because a map keyed by `id()`
    # is not re-entrant: two layouts of one document would share it.
    # Untyped for the same reason `geometry` is -- `layout.table` imports
    # this module.
    table_plan: object | None = None

    # Filled by Task F (`layout.flex`) on a `flex` or `inline-flex` box:
    # its `FlexPlan` -- the lines, the resolved main sizes and what
    # `justify-content` spent. It lives on the box for the reason
    # `table_plan` does: the mechanical check runs after absolutization,
    # when the numbers that produced the rectangles are otherwise gone, and
    # a module-level map keyed by `id()` would not be re-entrant. Untyped
    # for the same reason `geometry` is -- `layout.flex` imports this
    # module.
    flex_plan: object | None = None

    # Filled by Task D1 (`layout.block`) on a box whose width is
    # shrink-to-fit: `inline-block` and its two siblings, floats, and
    # absolutely positioned boxes. Separate from `geometry` because the
    # *width* of a float resolves without the float being *placed*, and
    # placement is not implemented -- so a float has a number here and
    # `geometry is None`, which is the honest pair.
    shrink_to_fit_width: float | None = None

    @property
    def is_inline_level(self) -> bool:
        return self.display in INLINE_LEVEL

    @property
    def is_comparable(self) -> bool:
        """True when this box has a CDP counterpart to be compared against."""
        return self.origin != "anonymous"

    def identity(self) -> tuple[int, str, int] | None:
        """`(ordinal, path, fragment)`, or None for an anonymous box.

        Two identifiers rather than one, per CLAUDE.md: when the ordinals
        line up and the paths disagree, the DOM trees diverged, and that is
        an `htmlparse` finding rather than a layout one.
        """
        if not self.is_comparable or self.ordinal is None or self.path is None:
            return None
        return (self.ordinal, self.path, self.fragment)

    def walk(self):
        yield self
        for child in self.children:
            yield from child.walk()

    def __repr__(self) -> str:
        who = self.path if self.path else f"<{self.origin}>"
        return f"Box({self.display} {who} x{len(self.children)})"


def _tag_of(node: Node) -> str:
    return node.tag_name if isinstance(node, Element) else "#text"


def assign_dom_identity(document: Node) -> dict[int, tuple[int, str]]:
    """`id(element) -> (document-order ordinal, XPath-style path)`.

    Computed over the DOM, before any pruning, so a hidden element still
    consumes an ordinal. Chrome's DOM contains those elements too, and an
    identity scheme that skipped them here would drift out of step with CDP
    on any page that hides anything -- which is every page in the corpus.

    The path is 1-based among siblings *of the same tag name*, which is what
    XPath means and what `document.evaluate` reproduces on the other side.

    **The ordinal is assigned when a node is reached, not when its parent's
    child list is scanned**, and the difference is not cosmetic. The
    previous version numbered every child of a node before descending into
    any of them, which is a level-by-level order and not document order:
    in `<table><tbody><tr><td>a<td>b</tr><tr><td>c</tr>` it gave the two
    `tr`s 8 and 9 and only then gave the first row's cells 10 and 11, where
    `document.querySelectorAll('*')` -- which is what the other side of the
    Chrome comparison uses -- gives 8, 9, 10, 11, 12 in tree order.

    Latent since Task B and invisible until Task E, because it needs a
    subtree whose siblings have children of their own: every Task D2 fixture
    is one `<div>` deep and agrees under both orders. It surfaced as five
    table fixtures reporting TREE DIVERGENCE with **identical paths on both
    sides** -- the two-identifier scheme's own signature for "these are the
    same element and one of the two identifiers is computed wrongly".
    """
    out: dict[int, tuple[int, str]] = {}
    ordinal = 0
    stack: list[tuple[Node, str]] = [(document, "")]
    while stack:
        node, prefix = stack.pop()
        if isinstance(node, Element):
            out[id(node)] = (ordinal, prefix)
            ordinal += 1
        seen: Counter[str] = Counter()
        annotated: list[tuple[Node, str]] = []
        for child in node.children:
            if not isinstance(child, Element):
                annotated.append((child, prefix))
                continue
            seen[child.tag_name] += 1
            annotated.append(
                (child, f"{prefix}/{child.tag_name}[{seen[child.tag_name]}]")
            )
        stack.extend(reversed(annotated))
    return out


def _display_of(node: Node, metrics: Counter[str]) -> str | None:
    """The outer display for `node`, or None if it generates no box."""
    if isinstance(node, Text):
        return "inline"
    if not isinstance(node, Element):
        return None  # Comment, DocumentType, Document
    style = node.computed_style
    display = getattr(style, "display", None) if style is not None else None
    if display is None:
        # No computed style: the cascade never reached it. Counted rather
        # than guessed -- a default of "block" here would silently invent
        # boxes for a tree that was never styled.
        metrics["boxes_unstyled_skipped"] += 1
        return None
    if display == "none":
        return None
    fallback = GRID_FALLBACK.get(display)
    if fallback is not None:
        metrics["boxes_grid_fallback"] += 1
        return fallback
    return display


def _is_blank_text(node: Node) -> bool:
    """Is this a text node made only of CSS white space?

    `layout.text.is_white_space_only`, not `str.strip()`. The two disagree
    on U+00A0 NO-BREAK SPACE, U+000B, U+000C, U+2000-U+200A and U+3000,
    none of which CSS Text 3 treats as white space. NBSP is the one that
    occurs: 36 text boxes on the corpus contain nothing else, and
    `str.strip()` calls every one of them blank -- which would discard a
    `&nbsp;`-only run between two block siblings and give a block whose
    only content is `&nbsp;` no line box, so it would collapse through.

    Zero corpus occurrences of the disagreement reaching this function,
    measured by wrapping it: the 36 all sit inside inline formatting
    contexts, where this predicate is not consulted. Latent, not live --
    which is why it is a `docs/synthetic-only-coverage.md` row as well as a
    fix.
    """
    return isinstance(node, Text) and is_white_space_only(node.data)


def _wrap_inline_runs(children: list[Box], metrics: Counter[str]) -> list[Box]:
    """CSS 2.1 section 9.2.1.1: give a block container only block-level
    children by wrapping each run of inline-level ones in an anonymous block.

    Two ways to get this wrong, and over-generation is as bad as
    under-generation:

    * A container whose children are *all* inline-level needs no anonymous
      box at all -- it already establishes an inline formatting context.
    * A run that is entirely collapsible whitespace generates nothing. The
      spec is explicit: white space that would be collapsed away does not
      produce an anonymous inline box. Two adjacent `<div>`s separated by a
      newline in the source must not gain a box between them.

    Whitespace runs adjacent to real inline content are *kept*, because a
    text node between two inline elements is a real word separator. That
    distinction is why this cannot be done by discarding blank text at parse
    time.
    """
    if not any(not box.is_inline_level for box in children):
        return children  # no block-level child: nothing to force

    out: list[Box] = []
    run: list[Box] = []

    def flush() -> None:
        if not run:
            return
        if all(box.origin == "text" and _is_blank_text(box.node) for box in run):
            # Entirely collapsible whitespace between block-level siblings.
            metrics["boxes_blank_text_discarded"] += len(run)
            run.clear()
            return
        metrics["boxes_anonymous"] += 1
        out.append(Box(display="block", origin="anonymous", children=list(run)))
        run.clear()

    for box in children:
        if box.is_inline_level:
            run.append(box)
        else:
            flush()
            out.append(box)
    flush()
    return out


def _split_inline_around_blocks(
    box: Box, metrics: Counter[str], non_comparable: list | None = None
) -> list[Box]:
    """An inline box containing a block-level box is broken around it.

    Returns the boxes that replace `box` in its parent. The inline's own
    identity is carried by every fragment: they are the same element, split,
    which is exactly what `fragment` numbers.
    """
    if not any(not child.is_inline_level for child in box.children):
        return [box]

    pieces: list[Box] = []
    run: list[Box] = []
    index = 0

    def flush_inline() -> None:
        nonlocal index
        if not run:
            return
        if all(b.origin == "text" and _is_blank_text(b.node) for b in run):
            metrics["boxes_blank_text_discarded"] += len(run)
            run.clear()
            return
        pieces.append(
            Box(
                display=box.display,
                origin=box.origin,
                node=box.node,
                children=list(run),
                ordinal=box.ordinal,
                path=box.path,
                fragment=index,
            )
        )
        index += 1
        run.clear()

    for child in box.children:
        if child.is_inline_level:
            run.append(child)
        else:
            flush_inline()
            pieces.append(child)
    flush_inline()
    # Two different outcomes, counted separately because one name for both
    # over-claims. An inline with inline content either side of a block is
    # genuinely SPLIT and yields fragments. An inline whose children are all
    # block-level -- `<span><table>...</table></span>`, which Hacker News
    # does 30 times -- is not split around anything: it contributes no box
    # of its own and simply dissolves, leaving its children in the parent.
    #
    # That distinction matters for the Chrome comparison. A dissolved inline
    # has NO box on our side, while CDP will still answer `getBoxModel` for
    # that node, so it is a known non-comparable rather than a mismatch.
    if index:
        metrics["boxes_inline_split"] += 1
        metrics["boxes_inline_fragments"] += index
    else:
        metrics["boxes_inline_dissolved"] += 1
        # Recorded, not merely counted. The Chrome harness needs the
        # identities: CDP will happily answer getBoxModel for this node
        # while we have no box for it at all, so without this list it reads
        # as a layout failure instead of a question that does not apply.
        # Same shape as the two-identifier scheme -- distinguishing "we
        # differ" from "there is nothing to compare".
        if non_comparable is not None and box.ordinal is not None:
            non_comparable.append(
                {"ordinal": box.ordinal, "path": box.path, "reason": "inline-dissolved"}
            )
    return pieces


def _build(
    node: Node,
    ids: dict[int, tuple[int, str]],
    metrics: Counter[str],
    non_comparable: list | None = None,
) -> list[Box]:
    """Boxes for `node` itself. Returns a list because an inline may split."""
    display = _display_of(node, metrics)
    if display is None:
        return []

    if isinstance(node, Text):
        metrics["boxes_text"] += 1
        return [Box(display="inline", origin="text", node=node)]

    assert isinstance(node, Element)
    ordinal, path = ids.get(id(node), (None, None))
    metrics["boxes_element"] += 1
    box = Box(display=display, origin="element", node=node, ordinal=ordinal, path=path)

    children: list[Box] = []
    for child in node.children:
        children.extend(_build(child, ids, metrics, non_comparable))

    # `display: inline` splits around a block-level child; the *atomic*
    # inline-level boxes do not. `inline-block`, `inline-flex` and
    # `inline-table` are inline-level on the outside and block containers on
    # the inside (CSS Display 3 section 2.1) -- they establish their own
    # formatting context, so a block child stays inside rather than breaking
    # them in two. `INLINE_LEVEL` is the wrong test here and was the test
    # used: it answers "does this participate in an inline formatting
    # context?", not "is this an inline box?".
    #
    # Measured on the corpus by wrapping the split function: 3 boxes took
    # the splitting path that should not have -- 2 `inline-flex` and 1
    # `inline-block`, all on Wikipedia -- so one of the two boxes Task B
    # reported as `boxes_inline_split` and one of the two it reported as
    # `boxes_inline_dissolved` were neither.
    if box.display == "inline":
        box.children = children
        return _split_inline_around_blocks(box, metrics, non_comparable)

    box.children = _wrap_inline_runs(children, metrics)
    return [box]


def build_box_tree(
    document: Node, *, non_comparable: list | None = None
) -> tuple[Box | None, Counter[str]]:
    """Build the box tree for a styled document.

    Returns `(root, metrics)`. Writing the metrics is a driver's job -- see
    `scripts/layout_report.py` and the note at the top of `mayshay/metrics.py`.

    The document must already have been through `style_document`: every
    element needs a `computed_style` to have a `display`. Elements without
    one are skipped and counted in `boxes_unstyled_skipped` rather than
    guessed at.

    Pass a list as `non_comparable` to collect the DOM nodes that produce no
    box on our side but that CDP will still answer for -- currently the
    dissolved inlines. The Chrome comparison harness must exclude these by
    identity; 32 of them on the corpus would otherwise read as 32 layout
    failures. Derived rather than hard-coded, so it stays correct when the
    corpus is re-collected.
    """
    metrics: Counter[str] = Counter()
    # Seeded so absence and zero stay distinguishable in the CSV: a page
    # with no anonymous boxes must emit a row saying 0, not no row.
    for key in (
        "boxes_element",
        "boxes_text",
        "boxes_anonymous",
        "boxes_grid_fallback",
        "boxes_inline_split",
        "boxes_inline_fragments",
        "boxes_inline_dissolved",
        "boxes_blank_text_discarded",
        "boxes_pruned_roots",
        "boxes_pruned_total",
        "boxes_unstyled_skipped",
        "boxes_visited",
    ):
        metrics[key] = 0

    ids = assign_dom_identity(document)
    metrics["dom_elements"] = len(ids)
    _count_pruned(document, metrics)

    roots: list[Box] = []
    for child in document.children:
        roots.extend(_build(child, ids, metrics, non_comparable))

    # The document element is the single root when there is one; a stray
    # comment or doctype produces no box, so `roots` is usually length 1.
    root = roots[0] if len(roots) == 1 else None
    if len(roots) > 1:
        root = Box(display="block", origin="anonymous", children=roots)
        metrics["boxes_anonymous"] += 1
    return root, metrics


def _count_pruned(document: Node, metrics: Counter[str]) -> None:
    """Count what `display: none` removes, WITHOUT descending into it.

    Separate from `_build` because `_build` must never walk a pruned
    subtree, and counting what is inside one requires walking it. This runs
    once, deliberately, and is the only place that enters a hidden subtree.
    The distinction matters: three different correct populations live here,
    and the census figure is not the root count.
    """
    def descend(node: Node) -> int:
        total = 0
        for child in node.children:
            if isinstance(child, Element):
                total += 1
            total += descend(child)
        return total

    def scan(node: Node) -> None:
        for child in node.children:
            if isinstance(child, Element):
                style = child.computed_style
                if style is not None and getattr(style, "display", None) == "none":
                    metrics["boxes_pruned_roots"] += 1
                    metrics["boxes_pruned_total"] += 1 + descend(child)
                    continue  # do not scan inside: nested roots are not roots
            scan(child)

    scan(document)
