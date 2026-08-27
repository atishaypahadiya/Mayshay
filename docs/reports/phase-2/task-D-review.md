# Task D review: DOM cascade affordances

## Spec Compliance

✅ Spec compliant. All five interfaces from the brief are present exactly as specified:
`Node.computed_style` (node.py:60), `Element.id` (:91-92), `Element.class_list`
(:94-110), `Element.element_children` (:112-114), `Element.element_index`
(:85), `annotate_positions` (:137-155, exported via `dom/__init__.py`). Nine
tests appended verbatim from the brief. No files outside the brief's list
touched.

⚠️ Cannot verify from diff: the whole-corpus 404/474 parse-error-agreement
figure — no committed script computes it; the report's `/tmp` reproduction is
plausible (zero parsing code touched) but not independently checked by me
beyond confirming the diff touches only `dom/`.

## Strengths

- `class_list`'s docstring (node.py:96-107) states the cache's safety
  condition and the exact obligation on the first future mutator — a written
  contract, not just a code comment claiming one.
- `annotate_positions` uses the file's existing iterative-stack idiom
  (matches `serialize`'s pattern), avoiding a second recursion-depth risk
  class in the same file.
- Tests are behaviorally sharp, not just shape checks (see discrimination
  check below).

## Cache contract and per-instance isolation

Confirmed at the definition site, node.py:96-107: states nothing mutates
`attrs` in Phase 2, and that a future mutator "must reset `self._class_list =
None`". `_class_list` is set in `Element.__init__` (node.py:82) — a genuine
per-instance field, not a class-level or `id()`-keyed structure — so no
cross-element leakage is possible. Contract is adequate: written where a
future implementer will actually be looking (the property they're about to
break), not just in the report.

## `annotate_positions` re-run behavior

Idempotent: each call fully overwrites `element_index` for every `Element`
reachable from `root` (node.py:144-155 loops `node.children` fresh each
time, no read-before-write), so a second call on an unchanged tree reproduces
identical results.

A node inserted after annotation and before some later call again over the
same root gets caught correctly, since the stack walks the whole tree from
`root` on every invocation. But a node inserted and used *without* a re-run
carries `element_index = None` (its `__init__` default, node.py:85) — that is
the same "obvious" failure the brief's own
`test_element_index_is_none_before_annotation` pins for the pre-annotation
case, so the None-vs-int discipline is real and typed (`int | None`), not a
silent 0 or stale value. What's missing: unlike `class_list`, the function's
docstring (node.py:139-143) says nothing about needing a re-run after DOM
mutation — no equivalent "if X changes, call this again" note. Minor, not a
defect, since Phase 2 never mutates the tree after parse.

## Composition with Task C

Verified directly in `src/mayshay/dom/node.py` (outside the diff's shown
hunks, since Task C's `Document` class doesn't appear in this diff at all):
`Document.mode: DocumentMode` (line 59) and `quirks_mode` as a derived
`@property` returning `self.mode == "quirks"` (lines 61-70), `DocumentType`'s
`public_id`/`system_id` fields (lines 84-85, 93-94), and `serialize`'s DOCTYPE
branch (lines 163-167) are all byte-identical to Task C's shape — this task's
diff never touches `Document` or `DocumentType`'s bodies, and `_render`'s only
change is the new `annotate_positions` function inserted before it, not a
modification. Composition is clean.

## Test discrimination

Checked each against the plausible-wrong-implementation the controller named:

- `class_list` with `split(" ")`: `test_class_list_splits_on_whitespace_runs`
  (test_node.py:212-215) uses `"box  wide"` (two spaces) — `split(" ")` yields
  `{"box", "", "wide"}` ≠ `{"box", "wide"}`. Fails correctly.
- `annotate_positions` counting all children instead of elements only:
  `test_annotate_positions_indexes_elements_only` (test_node.py:248-261)
  interleaves `Text` nodes between the two `<p>`s and asserts both
  `element_index` values (0, 1) and `count == 3`. A children-counting
  implementation would assign `first.element_index = 1` and `second = 3`
  (Text nodes occupying slots 0 and 2) and `count` would be 5 (or 4, depending
  on whether the root is counted) — both assertions fail. Discriminates.

All nine tests earn their place; none is a shape-only assertion.

## Issues

#### Critical (Must Fix)
None.

#### Important (Should Fix)
None.

#### Minor (Nice to Have)
- node.py:139-143 — `annotate_positions`'s docstring could note that callers
  must re-run it after any tree mutation, mirroring `class_list`'s explicit
  contract, so the obligation isn't left implicit for Phase 3+.

## Scoping call: missing whole-corpus parse-error-agreement script

Three tasks running have now reproduced 404/474 via a throwaway `/tmp`
script — the same uncommitted-measurement gap Phase 1 hit before
`conformance_report.py` was created to close it. This task made zero changes
to parsing code, so it is the wrong place to fix it: writing a
`scripts/parse_error_report.py` (or extending `conformance_report.py`) is
unrelated to DOM cascade affordances and would be scope creep on this diff.
It should go on Phase 2's deferred/backlog list now, to be picked up as a
short, standalone task before or alongside the next task that needs to
re-verify this number — the same pattern that produced
`conformance_report.py` justifies committing its parse-error twin once, not
re-deriving it ad hoc a fourth time.

## Assessment

**Task quality:** Approved

**Reasoning:** Small, correctly scoped diff; matches the brief's interfaces
exactly; the two design-sensitive points (cache safety, annotation
idempotency) are handled correctly and the cache one is documented in the
code itself, not just the report. Composition with Task C's DOM changes is
verified clean via direct read of the untouched surface.
