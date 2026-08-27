# Task K Re-Review

## Finding Verdicts

1. **Important — pytest-free module move** — ADDRESSED. `tests/support/parse_errors.py` defines `curated_codes` and `strip_position` once each (no duplicates). `tests/htmlparse/test_parse_errors.py` imports from it at line 8; `scripts/error_report.py` imports from it at line 68 in diff. Script reproduces 404/474 exactly. `tests/support/parse_errors.py:1–52`.

2. **`--files` flag semantics** — ADDRESSED. Matches `conformance_report.py` identically: `nargs="*"`, `default=[]`, unpacked with `*files` to `load_tree_tests()`. Verified: `--files tests1.dat` returns 48/52 (correct subset). `scripts/error_report.py:122–124`.

3. **Crash convention documented** — ADDRESSED. Docstring added explaining TreeBuilder exception → empty codes → "missing" classification (never "extra"). Marked as judgement call with note on missing Task B artifact. `scripts/error_report.py:47–52`.

## Duplicate Definitions

None. Only `tests/support/parse_errors.py:16` (strip_position) and `:20` (curated_codes).

## `--files` Semantics Match

Yes. Argument shape, defaults, help text, unpack pattern, and interaction with `load_tree_tests()` all identical to `conformance_report.py:65–67`.

## New Breakage

None. `tests/htmlparse/test_parse_errors.py` passes 56/60 (4 xfailed, expected). Module imports cleanly without pytest. Git clean. venv `.pth` intact.

## Verdict

**Fix round:** All findings addressed, no new breakage.
