# Task K Review: scripts/error_report.py

## Spec Compliance

✅ Spec compliant, with one Important design finding (dependency direction) and one Minor gap.

- Extra/missing kept separate: `scripts/error_report.py:145-146` prints them as two distinct
  counts (`extra`, `missing`), never collapsed. Independently reproduced: `404/474`, extra 49,
  missing 27, matching the report exactly.
- `--diff` mode mirrors `conformance_report.py`'s exit convention: `error_report.py:131`
  `return 1 if broken else 0`, identical to `conformance_report.py:83`. Verified live (see below).
- Curation reused, not reimplemented: `curated_codes()` defined once at
  `tests/htmlparse/test_parse_errors.py:102-134`, imported at `scripts/error_report.py:62`.
- 404/474 reproduced independently via `.venv/bin/python scripts/error_report.py`, no drift.

## Strengths

- `case_id()` (`scripts/error_report.py:66-73`) is copy-identical in convention to
  `conformance_report.py`'s, including the same collision-safety comment.
- Docstring at `error_report.py:19-49` correctly explains the non-exclusive extra/missing
  buckets and why they don't sum to the disagreement count — matches Task B's stated
  requirement to keep the two responses separate rather than force a single "wrong" bucket.
- The `_curated_cases()` refactor (`tests/htmlparse/test_parse_errors.py:137-153`) is a pure
  extract-method: identical branch structure, identical short-circuit on empty `codes`
  (`if codes and all(...)` vs. new `curated_codes` returning `None` for the same case),
  same iteration order. Confirmed behavior-preserving by inspection line-for-line, and by
  independently running the full suite post-review: **6483 passed, 72 xfailed, 0 failed**,
  identical to the stated baseline.

## Issues

### Important (Should Fix)

- **`scripts/error_report.py:62` — `from tests.htmlparse.test_parse_errors import curated_codes`
  couples the script to a pytest test module's import-time side effects, not just its logic.**
  That module does `import pytest` (test_parse_errors.py:3) and, at *module import time* (not
  test-run time), executes `@pytest.mark.parametrize("case,expected", _curated_cases())`
  (test_parse_errors.py:157), which itself calls `load_tree_tests("tests1.dat")` and builds a
  full list of `pytest.param`/xfail objects — none of which `curated_codes()` itself needs.
  Contrast with `conformance_report.py:31`, which imports only `tests.support.dat`, a module
  with zero pytest dependency and no eager work at import time. `tests/support/` already exists
  precisely for logic multiple things need (`dat.py`, and `marks.py` for `requires_corpus`) —
  `curated_codes` and its private helper `_strip_position` (test_parse_errors.py:98-99) belong
  there, e.g. `tests/support/parse_errors.py`, since neither touches pytest. Then both
  `test_parse_errors.py` and `scripts/error_report.py` import from that shared, side-effect-free
  module, and the script never has to import a `test_*.py` file to get a pure function. This
  isn't hypothetical fragility: any future change that makes `_curated_cases()` (or module-level
  code above it) slower, or fail without the corpus present in a new way, silently taxes or
  breaks the script for reasons unrelated to what it needs. Not a correctness bug today —
  `FileNotFoundError` is caught and the parametrize list degrades to `[]` — but it's the wrong
  side of the dependency to lean on.

### Minor (Nice to Have)

- `error_report.py` has no `--files` option; `conformance_report.py:64-66` does. Not required by
  the brief (only `--diff` parity was asked for), and `error_report.py` always sweeping the full
  corpus is defensible, but it's one place the "move between them without relearning" promise
  has a small gap — a reader who reaches for `--files` on one script won't find it on the other.

## `--diff` Gate: Reproduced Independently

Backed up `src/mayshay/htmlparse/treebuilder.py`, captured baseline
(`error_report.py --out before.txt` → 404/474), then replaced the `self._error("unexpected-end-tag", pos)`
call inside `close_p_element` (treebuilder.py:417) with `pass`. Re-ran:

- `error_report.py --out after.txt` → **392/474** (extra 44, missing 44), exit 0 (bare run, no regression check).
- `error_report.py --diff before.txt after.txt` → **5 newly agreeing, 17 newly disagreeing**
  (ids listed, e.g. `adoption01.dat:16`, `tests1.dat:25`, `tests23.dat:0..4`), **exit code 1** —
  confirmed via `echo $?`.
- Reverted from backup, `diff` confirmed byte-identical, re-ran bare `error_report.py` → 404/474
  again. Full suite re-run post-revert: 6483 passed, 72 xfailed, 0 failed — clean.

This matches the implementer's reported injection numbers exactly. The gate demonstrably fires
on a real regression and passes clean on a non-regression.

## Curation Extraction: Behavior-Preserving

Confirmed by direct diff reading (test_parse_errors.py old vs. new `_curated_cases()`/`curated_codes()`):
same skip conditions (fragment/script-on), same code-extraction via `_strip_position`, same
`TREE_ERROR_CODES` membership check, same falsy-on-empty-`codes` short circuit, same xfail-mark
wiring in `_curated_cases()`. Suite counts unchanged (6483/72/0) both per the report and per my
own independent re-run above.

## Mirrors `conformance_report.py`?

Yes on the load-bearing points: same `sys.path` bootstrap (both scripts, lines ~27-28), same
`case_id()` convention, same `--out`/`--diff` flag names and semantics, same exit-code convention
(0 normal, 1 on `--diff` regression, 2 on missing submodule), same "compare sets, never bare
totals" docstring framing. Diverges only on `--files` (Minor, above) and necessarily on output
shape (two divergence buckets vs. one pass/fail split) — that divergence is required by the
spec's "keep the two counts separate," not a mirroring failure.

## Cannot Verify From Diff

- Whether Task B's original ad hoc script (no longer extant) also treated a `TreeBuilder`
  crash as landing in `missing` only (`error_report.py:93-94`) rather than in `extra` as well —
  the implementer flags this themselves as unverifiable; I have no artifact to check it against
  either. Judgment call, consistent with `conformance_report.py`'s "a crash is a failure" stance,
  and not contradicted by any stated requirement.

## Assessment

**Task quality:** Approved, with one Important finding recommended for a fast follow-up
(move `curated_codes`/`_strip_position` to `tests/support/`) rather than a blocking fix — the
current coupling works today and is caught by exception handling, but is the wrong direction
for a codebase that already has `tests/support/` as the answer to exactly this problem.

**Reasoning:** The script is a faithful, low-drift mirror of `conformance_report.py`, reproduces
404/474 exactly, and its `--diff` gate was verified end-to-end (not just trusted from the report)
to fire on a real injected regression and exit non-zero. The curation refactor is behavior-preserving
by inspection and by suite re-run. The one real defect is architectural: the script depends on a
test module for its import side effects rather than on shared, pytest-free logic — fixable without
touching the measured numbers.
