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

# Inline-level outer display types. Everything else that generates a box is
# block-level for our purposes, including the internal table displays --
# Task E gives those their own handling; here they only need to not be
# mistaken for inline content.
INLINE_LEVEL: frozenset[str] = frozenset(
    {"inline", "inline-block", "inline-flex", "inline-table"}
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
    """
    out: dict[int, tuple[int, str]] = {}
    ordinal = 0
    stack: list[tuple[Node, str]] = [(document, "")]
    while stack:
        node, prefix = stack.pop()
        seen: Counter[str] = Counter()
        annotated: list[tuple[Node, str]] = []
        for child in node.children:
            if not isinstance(child, Element):
                annotated.append((child, prefix))
                continue
            seen[child.tag_name] += 1
            path = f"{prefix}/{child.tag_name}[{seen[child.tag_name]}]"
            annotated.append((child, path))
        for child, path in annotated:
            if isinstance(child, Element):
                out[id(child)] = (ordinal, path)
                ordinal += 1
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
    return isinstance(node, Text) and not node.data.strip()


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


def _split_inline_around_blocks(box: Box, metrics: Counter[str]) -> list[Box]:
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
    return pieces


def _build(node: Node, ids: dict[int, tuple[int, str]], metrics: Counter[str]) -> list[Box]:
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
        children.extend(_build(child, ids, metrics))

    if box.is_inline_level:
        box.children = children
        return _split_inline_around_blocks(box, metrics)

    box.children = _wrap_inline_runs(children, metrics)
    return [box]


def build_box_tree(document: Node) -> tuple[Box | None, Counter[str]]:
    """Build the box tree for a styled document.

    Returns `(root, metrics)`. Writing the metrics is a driver's job -- see
    `scripts/layout_report.py` and the note at the top of `mayshay/metrics.py`.

    The document must already have been through `style_document`: every
    element needs a `computed_style` to have a `display`. Elements without
    one are skipped and counted in `boxes_unstyled_skipped` rather than
    guessed at.
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
        roots.extend(_build(child, ids, metrics))

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
