"""The inline formatting context -- Phase 3 Task D1's half.

D1 owns everything about an IFC that does not need a line box: finding the
contexts, running CSS Text 3's Phase I white-space transformation over each
one *as a whole*, and storing the result on every text box. D2 owns line
breaking, line boxes, fragments and baseline alignment, and will build on
`Box.text` rather than re-derive it.

**Why the whole context at once.** CSS Text 3 section 4.1.1 step 4 says a
collapsible space collapses into the previous one "even one outside the
boundary of the inline containing that space, provided both spaces are
within the same inline formatting context". So

    <span>a </span> <span>b</span>

has one space between the words and not two, and there is no per-text-node
function that can know it. The three text nodes are collapsed together and
the surviving space is attributed to the run that contributed it.

**Where an IFC stops.** At an atomic inline. `inline-block`, `inline-flex`
and `inline-table` are inline-level on the outside and block containers on
the inside, so they establish their own context; in the outer one they are
opaque content that interrupts a whitespace run. They are passed to
`collapse_ifc` as a U+FFFC OBJECT REPLACEMENT CHARACTER under `pre` --
which is what that character is for -- rather than as a special case in the
collapser, and their own contents are processed as a separate context.

**What is deliberately not here.** No line boxes, no `<br>`, no replaced
content. `<br>` and `<img>` compute to `display: inline` with no children,
so they are transparent to this pass; for `<br>` that is simply Task D2's
job, but for `<img>` it is **wrong** -- a replaced element is content, and
white space either side of one must not collapse across it as though it
were an empty `<span>`. Counted in `text_ifc_replaced_transparent` rather
than left to be discovered, because it silently narrows text by one space
per image and would never show up as an error.
"""

from __future__ import annotations

from collections import Counter

from mayshay.layout import text as text_module
from mayshay.layout.boxtree import ATOMIC_INLINE_DISPLAYS, Box
from mayshay.layout.text import (
    WHITESPACE_DISPOSITIONS,
    collapse_ifc,
    disposition_of,
    is_white_space_only,
)
from mayshay.layout.used import text_style_of

#: Passed to the collapser in place of an atomic inline: content, under a
#: white-space value that preserves it, so it interrupts a collapsible run
#: exactly the way a letter would.
OBJECT_REPLACEMENT = "\ufffc"

#: Tag names that are replaced or line-breaking content but compute to
#: `display: inline` with no children, so this pass walks straight past
#: them. Named rather than inferred: "an inline element box with no
#: children" is also `<span></span>`, which genuinely *is* transparent.
_REPLACED_OR_BREAK_TAGS: frozenset[str] = frozenset(
    {"img", "br", "wbr", "input", "textarea", "select", "button",
     "iframe", "canvas", "video", "audio", "embed", "object", "svg"}
)

COUNTER_NAMES: tuple[str, ...] = (
    "text_ifc_contexts",
    "text_boxes_seen",
    "text_boxes_content",
    "text_boxes_whitespace_only",
    "text_chars_in",
    "text_chars_kept",
    "text_chars_transformed",
    "text_chars_removed",
    "text_whitespace_trimmed_ifc_start",
    "text_whitespace_trimmed_ifc_end",
    "text_whitespace_removed_around_segment_break",
    "text_whitespace_collapsed_into_previous",
    "text_carriage_returns_normalised",
    "text_missing_glyph",
    "text_preserved_tab_approximated",
    "text_ifc_replaced_transparent",
    "text_ifc_atomic_inlines",
) + tuple(f"text_whitespace_{name}" for name in WHITESPACE_DISPOSITIONS) + tuple(
    f"text_boxes_white_space_{value.replace('-', '_')}"
    for value in sorted(text_module.WHITE_SPACE_BEHAVIOUR)
)


def process_text(root: Box | None, metrics: Counter[str]) -> None:
    """Run Phase I over every inline formatting context under `root`.

    Called once, before block layout, so that intrinsic sizing and (in D2)
    line breaking both read the same collapsed text rather than each
    collapsing it again with its own idea of the rules.
    """
    for name in COUNTER_NAMES:
        metrics[name] += 0
    if root is not None:
        _process_box(root, metrics)
    assert_text_partitions(metrics)


def _process_box(box: Box, metrics: Counter[str]) -> None:
    if any(child.is_inline_level for child in box.children):
        _process_ifc(box, metrics)
    for child in box.children:
        if not child.is_inline_level:
            _process_box(child, metrics)


def _process_ifc(root: Box, metrics: Counter[str]) -> None:
    metrics["text_ifc_contexts"] += 1
    boxes: list[Box | None] = []
    runs: list[tuple[str, str]] = []
    _collect(root, boxes, runs, metrics)

    collapsed = collapse_ifc(runs, metrics)
    for box, run in zip(boxes, collapsed, strict=True):
        if box is None:
            continue  # the atomic inline's placeholder
        white_space = text_style_of(box).white_space
        box.text = run.text
        metrics["text_boxes_seen"] += 1
        metrics[
            "text_boxes_white_space_" + white_space.replace("-", "_")
        ] += 1
        metrics["text_chars_in"] += len(run.source)
        metrics["text_chars_kept"] += run.kept
        metrics["text_chars_transformed"] += run.transformed
        metrics["text_chars_removed"] += run.removed
        if is_white_space_only(run.source):
            metrics["text_boxes_whitespace_only"] += 1
            metrics["text_whitespace_" + disposition_of(run, white_space)] += 1
        else:
            metrics["text_boxes_content"] += 1


def _collect(
    box: Box,
    boxes: list[Box | None],
    runs: list[tuple[str, str]],
    metrics: Counter[str],
) -> None:
    """Gather the IFC's text runs in document order.

    `boxes` and `runs` stay index-aligned; `None` in `boxes` marks the
    placeholder standing in for an atomic inline, whose collapse result is
    thrown away.
    """
    for child in box.children:
        if child.origin == "text":
            boxes.append(child)
            data = child.node.data if child.node is not None else ""
            runs.append((data, text_style_of(child).white_space))
        elif child.display in ATOMIC_INLINE_DISPLAYS:
            metrics["text_ifc_atomic_inlines"] += 1
            boxes.append(None)
            runs.append((OBJECT_REPLACEMENT, "pre"))
            _process_box(child, metrics)
        elif child.is_inline_level:
            if (
                child.origin == "element"
                and child.node is not None
                and getattr(child.node, "tag_name", None) in _REPLACED_OR_BREAK_TAGS
            ):
                metrics["text_ifc_replaced_transparent"] += 1
            _collect(child, boxes, runs, metrics)
        else:
            # A block-level box inside what this pass took for an inline
            # run. Task B's anonymous-box and inline-splitting rules mean
            # this should not happen; it is left as a recursion rather than
            # an assertion because a wrong tree should still lay out.
            _process_box(child, metrics)


# --------------------------------------------------------------------------
# Mechanical checks
# --------------------------------------------------------------------------


def assert_text_partitions(metrics: Counter[str]) -> None:
    """Three partitions, run on every layout rather than only under test.

    Same shape as Task C's `assert_layout_constraints`, and here for the
    same reason: vigilance has caught none of this class of defect on this
    project and mechanical checks have caught all of it.

    1. **Every text box is white-space-only or it is not.** A third state
       cannot appear without this failing.
    2. **Every white-space-only box ended in exactly one named
       disposition**, and the dispositions sum. `other` is the residual, in
       the shape of Task C's `widths_deferred_other`: a `white-space` value
       added to the parser and handled here without a disposition lands in
       it, and the report says so.
    3. **Every input character was kept, transformed, or removed.** This is
       the one that catches a collapsing rule that drops a character it
       meant to rewrite -- a defect whose only other symptom is text a few
       pixels narrow than it should be, on a page that renders fine.
    """
    boxes = metrics["text_boxes_content"] + metrics["text_boxes_whitespace_only"]
    assert metrics["text_boxes_seen"] == boxes, (
        "every text box is white-space-only or it is content: seen "
        f"{metrics['text_boxes_seen']} != {boxes}"
    )

    dispositions = sum(
        metrics["text_whitespace_" + name] for name in WHITESPACE_DISPOSITIONS
    )
    assert metrics["text_boxes_whitespace_only"] == dispositions, (
        "every white-space-only text box ends in exactly one named "
        f"disposition: {metrics['text_boxes_whitespace_only']} != "
        f"{dispositions}"
    )

    chars = (
        metrics["text_chars_kept"]
        + metrics["text_chars_transformed"]
        + metrics["text_chars_removed"]
    )
    assert metrics["text_chars_in"] == chars, (
        "every input character was kept, transformed or removed: in "
        f"{metrics['text_chars_in']} != {chars}"
    )

    ws_values = sum(
        metrics["text_boxes_white_space_" + value.replace("-", "_")]
        for value in text_module.WHITE_SPACE_BEHAVIOUR
    )
    assert metrics["text_boxes_seen"] == ws_values, (
        "every text box was measured under exactly one `white-space` value: "
        f"seen {metrics['text_boxes_seen']} != {ws_values} -- a value added "
        "to the parser and forgotten in the census"
    )
