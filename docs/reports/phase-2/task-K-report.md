# Task K: scripts/error_report.py

## What was built

`scripts/error_report.py` — a whole-corpus sweep that reports how many of the
curated html5lib-tests tree-construction cases have our tree builder's
recorded parse errors agree (as multisets) with the corpus's `#errors`
section. Modeled directly on `scripts/conformance_report.py`: same
`sys.path` bootstrap, same `case_id()` qualification convention, same
`--out` / `--diff` flags, same exit-code convention for `--diff` (0 if no
regressions, 1 if any case newly disagrees), same docstring style pointing at
"compare sets of ids, never bare totals."

To avoid a second copy of the curation rule, `tests/htmlparse/test_parse_errors.py`
was refactored (not behaviorally changed): the inline filtering logic inside
`_curated_cases()` (skip fragment/script-on cases, require every expected
error code to be in `TREE_ERROR_CODES`) was extracted into a new top-level
function `curated_codes(case) -> list[str] | None`, with the same docstring
content moved onto it. `_curated_cases()` now just calls `curated_codes()`
and wraps the result in `pytest.param`/xfail marks as before — its own
behavior and scope (still just `tests1.dat`, still driving the existing
parametrized test) is unchanged. `scripts/error_report.py` imports
`curated_codes` from `tests.htmlparse.test_parse_errors` and calls
`load_tree_tests()` with no args (all `.dat` files, same as
`conformance_report.py` does), so the two never define curation differently.
This is a clean import — `tests/` and its subpackages all have `__init__.py`,
and `conformance_report.py` already imports from `tests.support.dat`, so
there's precedent for scripts importing test-tree modules directly.

## Command and full output

```
$ .venv/bin/python scripts/error_report.py
parse-error agreement: 404/474
  unexpected code emitted (extra):    49
  expected code never emitted (missing): 27
```

This reproduces 404/474 exactly, no discrepancy. (49 + 27 > 70 disagreeing
cases because a case can appear in both buckets — it can simultaneously emit
a code the corpus doesn't expect and fail to emit one it does. That's called
out in the script's docstring and confirmed by construction: `70 =
|extra ∪ missing|`, verified via `--out`, which wrote exactly 70 ids.)

Conformance (unrelated tree-shape metric, run for comparison, unmoved):

```
$ .venv/bin/python scripts/conformance_report.py
all files: 780/1592
tests1.dat: 64/112
```

## `--diff` gating, verified by injection

1. Captured baseline: `error_report.py --out /tmp/errreport/before.txt` (70 ids).
2. Injected a real regression in `src/mayshay/htmlparse/treebuilder.py`:
   replaced the `self._error("unexpected-end-tag", pos)` call inside the p-end-tag
   handling helper with `pass  # INJECTED REGRESSION FOR TESTING`, so that
   helper stops recording an error it used to record.
3. Re-ran: `error_report.py --out /tmp/errreport/after.txt` →
   `parse-error agreement: 392/474` (down from 404; extra 44, missing 44).
4. `error_report.py --diff before.txt after.txt` printed `newly agreeing (5)`
   and `newly disagreeing (17)` (listing ids such as `tests1.dat:25`,
   `adoption01.dat:16`, `tests23.dat:0..4`, etc.), and **exited 1** —
   confirmed via `echo $?` immediately after.
5. Reverted the injected change from a pre-edit backup
   (`cp /tmp/errreport/treebuilder.py.bak src/mayshay/htmlparse/treebuilder.py`),
   diffed the restored file against the backup to confirm byte-identical
   restoration, then re-ran `error_report.py` bare and got `404/474` again.

## Verification of no collateral damage

- `.venv/bin/pytest` (no `-q`): **6483 passed, 72 xfailed, 0 failed** — same
  as the starting state, both before and after the injection-and-revert
  cycle.
- `scripts/conformance_report.py`: `780/1592`, `tests1.dat: 64/112` — unmoved.
- `git status`: clean after `git add` + commit of exactly the two intended
  files (`scripts/error_report.py` new, `tests/htmlparse/test_parse_errors.py`
  modified).
- `.venv/lib/python3.13/site-packages/__editable__.mayshay-0.1.0.pth`
  contents: `/Users/atishaypahadiya/projects/mayshay/src` — unchanged
  (checked before and after all work).

## What a reviewer should scrutinize hardest

1. **The extra/missing bucket overlap.** The two divergence counts are not
   mutually exclusive by design (a case can be both), so `extra + missing`
   does not equal the count of disagreeing cases, and the printed numbers
   (49, 27) sum to more than 70. This matches the task's request to keep the
   two counts separate rather than collapsed, but a reader expecting
   `extra + missing == disagreeing` will be surprised — the docstring and
   this report call it out explicitly, but it's worth a second look at
   whether that's the right contract or whether per-case exclusive
   classification would have been more useful for gating purposes.
2. **The refactor of `_curated_cases()`.** Confirm the extracted
   `curated_codes()` is byte-for-byte equivalent in behavior to the original
   inline logic (same skip conditions, same order, same truthiness check on
   `codes`) — I diffed by inspection and by re-running the full suite
   (identical pass/xfail counts), but a reviewer may want to diff the two
   function bodies directly.
3. **The crash-handling branch in `run()`**: a `TreeBuilder` exception is
   treated as `actual = []`, which always lands the case in `missing` (since
   `expected` is non-empty by construction) and never in `extra`. This
   mirrors `conformance_report.py`'s "a crash is a failure" stance but is a
   judgment call worth confirming matches what Task B's original ad hoc
   script did, since no baseline artifact of that script survived to compare
   against.

## Fix round (post-review)

Reviewer confirmed spec compliance and reproduced `--diff` independently, but
flagged one Important issue: `scripts/error_report.py` imported `curated_codes`
from `tests/htmlparse/test_parse_errors.py`, a `test_*.py` module, which pulls
in `pytest` and executes that module's `_curated_cases()` parametrize-building
as an import side effect — unnecessary cost and coupling for a measurement
script. (The `scripts/` -> `tests/` import direction itself is fine and has
precedent via `conformance_report.py` importing `tests.support.dat`; the
problem was specifically importing from a `test_*.py` file.)

Fix: created `tests/support/parse_errors.py` (pytest-free, same shape as
`tests/support/dat.py`) holding `strip_position` and `curated_codes`.
`tests/htmlparse/test_parse_errors.py` and `scripts/error_report.py` both now
import from there instead of one defining and the other reaching into a test
module. Verified by import: `sys.modules` after importing
`tests.support.parse_errors` contains no `pytest`.

Also addressed, as suggested rather than required:
- Added `--files` to `error_report.py`, matching `conformance_report.py`'s
  flag surface, so a reader moving between the two scripts doesn't hit an
  unexplained gap.
- Added an explicit note in `error_report.py`'s docstring about the
  crash-handling convention (a `TreeBuilder` exception counts as "missing",
  never "extra"), since the reviewer could not verify this against Task B's
  original script (no surviving artifact) — now it's at least documented for
  whoever needs to build on this measurement next.

Reverification after the move:
- `.venv/bin/python scripts/error_report.py` → `404/474`, `extra: 49`,
  `missing: 27` — unchanged.
- `.venv/bin/python scripts/error_report.py --files tests1.dat` → `48/52`
  (spot check that `--files` works).
- `--diff` gate re-verified with a fresh injection/revert cycle on
  `treebuilder.py` (same edit as the first round): dropped to `392/474`,
  `--diff` reported 5 newly agreeing / 17 newly disagreeing (identical ids to
  the first round) and exited 1; reverted, diffed byte-identical against the
  pre-edit backup, reran to confirm `404/474` again.
- `.venv/bin/pytest` (no `-q`): **6483 passed, 72 xfailed, 0 failed**.
- `scripts/conformance_report.py`: `780/1592`, `tests1.dat: 64/112` — unmoved.
- `git status`: clean after commit `99d03ba` (added
  `tests/support/parse_errors.py`, modified `scripts/error_report.py` and
  `tests/htmlparse/test_parse_errors.py`).
- venv `.pth` (`.venv/lib/python3.13/site-packages/__editable__.mayshay-0.1.0.pth`):
  still `/Users/atishaypahadiya/projects/mayshay/src`, unchanged.
