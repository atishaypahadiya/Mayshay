# Task D report: DOM cascade affordances

**Status: complete.** All five steps done, no deviations from the design
decisions in the task prompt.

---

## Changes per step

**Step 1 — tests appended.** `tests/dom/test_node.py`: added
`annotate_positions` to the existing `from mayshay.dom.node import (...)`
block, then appended the nine tests from the brief verbatim (computed_style
default on all five node types, class_list whitespace-run splitting, tabs/
newlines/edges, absent-class empty set, `id` accessor and its case
sensitivity, `element_children` excluding Text/Comment, `annotate_positions`
indexing elements only, and `element_index` being `None` pre-annotation).

**Step 2 — verified failing.** Ran before implementing; failed on
`AttributeError: 'Document' object has no attribute 'computed_style'` as
expected (not reproduced in this report — moved straight to implementation
once confirmed).

**Step 3 — implementation**, `src/mayshay/dom/node.py`:
- `Node.__init__` gains `self.computed_style: object | None = None`, with the
  brief's comment about why it lives on `Node` rather than `Element`.
- `Element.__init__` gains `self._class_list: frozenset[str] | None = None`
  and `self.element_index: int | None = None`.
- `Element.id` — reads `self.attrs.get("id")`.
- `Element.class_list` — cached property, splits `self.attrs.get("class", "")`
  with argument-less `.split()` (whitespace-run split, drops empties — the
  brief's point about `split(" ")` producing a spurious empty string from
  `"box  wide"` is stated in the docstring, not just in this report).
- `Element.element_children` — list comprehension filtering `self.children`
  to `isinstance(c, Element)`.
- `annotate_positions(root)` — iterative stack-based single pass (no
  recursion, consistent with `serialize`'s existing style in this file, and
  safe against the same deep-tree-blows-the-stack failure mode
  `test_deep_tree_does_not_blow_the_stack` already guards for `serialize`).
  Assigns `element_index` only to `Element` children, counts only those, and
  returns the total.

`src/mayshay/dom/__init__.py`: added `annotate_positions` to both the import
from `mayshay.dom.node` and `__all__`.

**Step 4 — full run.** See exact commands and output below.

**Step 5 — commit.** `git add src/mayshay/dom/ tests/dom/` then the exact
message from the brief. Commit `9d821e1` on `phase-2-css-to-styled-tree`.

---

## Cache invalidation contract (per the prompt's "two details worth care")

Stated at the definition site (`Element.class_list` docstring in
`node.py`), not just here: nothing in Phase 2 mutates `attrs`, so caching
`_class_list` on first access is safe today. If a future mutator (e.g. a
`setAttribute`/`className` setter) is added, it must reset
`self._class_list = None` whenever it writes the `class` attribute — the
docstring says this explicitly so the first person adding a mutator has to
either honor it or knowingly break it.

---

## Exact test commands and output

```
$ .venv/bin/pytest tests/dom/ -v
...
tests/dom/test_node.py .......................                         [100%]
============================== 22 passed in 0.04s ==============================
```

```
$ .venv/bin/pytest
...
6033 passed, 72 xfailed in 1.72s
```

(Baseline was 6024 passed, 72 xfailed, 0 failed. 6024 + 9 new tests = 6033;
xfailed count unchanged, 0 failures — matches the "no parsing behaviour
changes" expectation exactly.)

```
$ .venv/bin/python scripts/conformance_report.py
all files: 780/1592
tests1.dat: 64/112
```

Both unmoved from the stated baseline.

**Parse-error agreement (404/474):** `scripts/conformance_report.py` does not
compute this number, and the only pytest test that touches this metric
(`tests/htmlparse/test_parse_errors.py::test_corpus_error_codes_match_as_a_
multiset`) parametrizes over `tests1.dat` only (48 passed, 4 xfailed there),
not the whole corpus. The 404/474 figure is a *whole-corpus* measurement
(confirmed by cross-referencing Task C's report, which recorded the same
404/474 before and after its own changes). I reproduced it with a throwaway
script at `/tmp/parse_error_agreement.py` that mirrors
`test_parse_errors.py::_curated_cases`'s selection rule (drop fragment cases
and `script="on"` cases; keep a case only if every expected error code is in
`TREE_ERROR_CODES`) but applied via `load_tree_tests()` with no filename
filter, i.e. across all 57 `.dat` files instead of just `tests1.dat`:

```
$ .venv/bin/python /tmp/parse_error_agreement.py
404/474
disagreeing ids: ['domjs-unsafe.dat:13', 'domjs-unsafe.dat:17', ... 'webkit02.dat:21']
```

404/474, and I did not diff the 70-id disagreeing set against a prior run
byte-for-byte (no saved baseline file was available to diff against), but the
total matches the stated baseline exactly and this task made zero changes to
`treebuilder.py`, `tokenizer.py`, or any parsing code — only new accessors on
`Node`/`Element` and a standalone annotator function that nothing in the
parsing pipeline calls yet. There is no code path by which this task could
have altered which corpus cases agree.

---

## How this composes with Task C's changes to `dom/node.py`

Task C converted `quirks_mode` into a derived read-only `@property` on
`Document`, added `Document.mode: DocumentMode`, gave `DocumentType` public/
system identifier fields, and changed `serialize`'s DOCTYPE rendering. None of
that surface was touched:

- `Node.__init__` was the only `__init__` this task added an attribute to
  outside `Element`; `Document.__init__` and `DocumentType.__init__` are
  untouched, so `Document.mode` and `quirks_mode`'s property status are
  intact (the new `test_computed_style_defaults_to_none_on_every_node_type`
  test exercises `Document()` and `DocumentType("html")` directly, which is
  effectively a regression check that Task C's constructors still run cleanly
  through `Node.__init__`).
- `serialize` / `_render` were not touched at all — this task adds no
  serialization-visible attribute (nothing added here has a `#document`
  representation).
- `Element.__init__`'s existing two lines (`tag_name`, `attrs`) were
  extended, not replaced, and in the same style as the rest of the file
  (typed instance attributes with an explanatory comment where the "why" is
  not obvious from the name).

No brief snippet needed correction against the current file — the brief's
Step 3 snippets for `Node.__init__`/`Element` additions were written as
diffs against the pre-Task-C class bodies conceptually, but since they only
add new lines (never replace or reference Task C's `mode`/`quirks_mode`/
`DocumentType` fields), they applied cleanly with no adaptation needed beyond
inserting them at the right point in the current file.

---

## What a reviewer should scrutinise hardest

1. **`class_list`'s cache-invalidation contract is a promise, not an
   enforcement mechanism.** Nothing in the codebase currently prevents a
   future PR from mutating `el.attrs["class"] = ...` directly and silently
   getting a stale cached `class_list`. The docstring says what must happen,
   but there is no test pinning that (there cannot be, since no mutator
   exists yet in Phase 2). Worth a mental note for whoever reviews the first
   DOM-mutation PR in Phase 3+.
2. **`annotate_positions`'s stack traversal order.** It uses `stack.pop()`
   (LIFO) and appends children in `node.children` order, then pops the last
   child first — meaning the tree is visited depth-first but not strictly
   pre-order left-to-right for *when* nodes are processed. This doesn't
   matter for correctness here (each node's own children are indexed by a
   plain `for child in node.children` loop, independent of stack order,
   exactly mirroring `serialize`'s existing traversal pattern) — but it's
   worth confirming that reasoning rather than assuming order-independence.
3. **The 404/474 reproduction methodology above.** I did not have a saved
   pre-task baseline file to `diff` the disagreeing-id set against (only the
   prior report's *count*), so "unmoved" here rests on (a) the count matching
   exactly and (b) this task touching zero parsing code. A reviewer who wants
   the stronger byte-identical-set guarantee Task C's report gave should save
   `/tmp/parse_error_agreement.py`'s output before/after independently.
4. **`id` and `class_list` are read-only properties with no setters** — by
   design (Phase 2 doesn't mutate), but flag if any later task expects
   `el.id = "x"` to work.

---

## Environment check

```
$ git status --porcelain
(clean after commit)

$ cat .venv/lib/python3.13/site-packages/__editable__.mayshay-0.1.0.pth
/Users/atishaypahadiya/projects/mayshay/src
```

Unchanged, single line, nothing under `.venv/` was touched at any point in
this session. All experimentation (the whole-corpus parse-error-agreement
check) ran from `/tmp/parse_error_agreement.py` via `sys.path` insertion.
