# Task A Review: Shared metrics writer

## Spec Compliance

✅ Spec compliant. All brief-specified interfaces present and matching signatures:
`new_run_id() -> str` (metrics.py:172-174), `emit(stage, counters, *, source, run_id, path=None) -> int`
(metrics.py:177-224), `read(path=None) -> list[dict]` (metrics.py:227-233), `STAGES_CSV`/`METRICS_DIR`/`FIELDNAMES`
module constants (metrics.py:166-169). Long format confirmed: one row per `(run_id, timestamp, stage, source, key,
value)` (metrics.py:169, 211-219). Writer is not called from any parse method — `emit` is only invoked from
`tests/test_metrics.py`; no `TreeBuilder`/tokenizer changes in this diff. `conformance.csv` untouched.
CLAUDE.md bullet replaced verbatim as specified (CLAUDE.md:28-34 in diff). 9/9 tests pass per report; suite
delta (5051→5060) matches exactly 9 new tests, 0 regressions.

⚠️ Cannot verify from diff: whether any other pipeline stage (`htmlparse`, etc.) was expected to start calling
`emit` in this task — brief's file list is scoped to `metrics.py` + `test_metrics.py` + `CLAUDE.md` only, and the
diff matches that scope exactly, so this is not a gap, just noting the wiring-in is explicitly future work.

## Atomicity assessment (item 1)

Confirmed correct. `emit` builds the header (when `is_new`) and every row into one `io.StringIO` buffer via
`csv.DictWriter(buffer, ...)` (metrics.py:206-219), then performs exactly one `target.open("a", ...)` +
`handle.write(buffer.getvalue())` (metrics.py:222-223). No `csv.writer`/`DictWriter` is ever given the real file
handle, and there is no second `write` call. Critically, the header is folded into the *same* buffer as the row
data before that single write — so the atomicity argument does **not** fail on the first call, which is exactly
the failure mode the review was watching for.

## The `is_new` race (item 2)

`is_new = not target.exists() or target.stat().st_size == 0` (metrics.py:200) correctly covers both "file
absent" and "existing zero-length file" — matches the brief's explicit requirement.

Race: if two processes both call `emit` on a brand-new/empty target concurrently, both can observe `is_new`
True between the `exists()`/`stat()` check and their own append — this is a classic TOCTOU. Each still performs
its own single atomic append, so *rows* never interleave mid-line, but the file ends up with two header rows.
`csv.DictReader` treats only the first line as header, so the second header row is misread as a malformed data
row on subsequent `read()`. This is a real gap in the concurrency story the module's comment implies, though it
does not contradict what the comment actually claims (single-writer, single-append safety) — it's an omission,
not a false statement. No test exercises concurrent writers (none is expected to, per report).

## METRICS_DIR fallback (item 3)

Confirmed. Docstring explicitly frames `parents[2]` as fallback-only and narrates the Phase 1 `.pth` incident
(metrics.py:157-165). `emit`'s `path` parameter overrides the default via `target = path or STAGES_CSV`
(metrics.py:195), proven by `test_explicit_path_wins_over_the_default`. The only test touching the derived
default, `test_default_path_is_under_data_metrics`, inspects `.parent.name`/`.parent.parent.name` only — never
resolves or performs I/O against it, so no test depends on the derivation being correct.

## New-stage adoption (item 4)

Confirmed. `stage` and every `Counter` key are plain strings written into fixed columns (`FIELDNAMES`,
metrics.py:169); nothing in the module enumerates known stages or keys.
`test_new_key_needs_no_schema_change` exercises this with a `cssparse`/`"never_seen"` combination never used
elsewhere in the test file, and the module needs zero edits to support it.

## Test quality (item 5)

Strong on ordering, run_id, and the empty-counter path:
- `test_rows_are_sorted_by_key` (test_metrics.py:82-85) would fail if rows were emitted in Counter/insertion
  order instead of sorted — real discrimination.
- `test_emit_writes_one_row_per_key` / `test_two_stages_share_a_run_id` assert `run_id` per-row — would fail
  if `run_id` were ignored or hardcoded.
- `test_header_written_once_across_appends` would fail if the header were re-emitted per call.

Gap: no test anywhere reads back `r["source"]` and checks its value. `DictWriter.writerow` silently fills a
missing key with `restval` (empty string) rather than raising, so a bug that dropped or mis-wired the `source`
column (e.g. writing `""` or the wrong variable) would pass all 9 tests unnoticed. This is the one column in
the schema with zero behavioral coverage.

## Environment safety

Verified directly: `.venv/lib/python3.13/site-packages/__editable__.mayshay-0.1.0.pth` still reads
`/Users/atishaypahadiya/projects/mayshay/src`. `git status` on `phase-2-css-to-styled-tree` is clean. No
`data/metrics/stages.csv` exists (only pre-existing `.gitkeep` and `conformance.csv`).

## Strengths
- Long-format schema genuinely absorbs new stages/keys with zero code changes (verified directly).
- Single-buffer/single-write design is implemented correctly, including folding the header into the same
  write as the first call's rows.
- Docstring is honest about its own limitations (METRICS_DIR fallback, non-reentrant risk it avoids).
- `is_new` correctly handles both exists-false and zero-length branches per the brief's explicit callout.

## Issues

### Critical (Must Fix)
None.

### Important (Should Fix)
- test_metrics.py: no test asserts on `row["source"]`'s actual value anywhere — add an assertion (e.g. to
  `test_emit_writes_one_row_per_key`) checking `r["source"] == "a.html"` for all rows, so a dropped/mis-wired
  `source` column is caught.
- metrics.py:203-205: the concurrency comment claims single-append safety but doesn't acknowledge the
  `is_new` TOCTOU race that can duplicate header rows under two truly concurrent first-writers. Not a
  functional bug for the documented single-driver-at-a-time use case, but the comment should say so explicitly
  rather than implying blanket concurrency safety, given it's the exact claim item 1 was checking.
- test_metrics.py: no test pre-creates a zero-byte file before calling `emit` to confirm the header still
  gets written for that branch of `is_new` — the brief calls this out by name as "a real case" and only the
  file-absent branch is exercised. (Code is correct here per inspection; only the test is silent on it.)

### Minor (Nice to Have)
- Brief's Step 4 said "Expected: 8 passed" against 9 actual test functions; implementer correctly followed
  the actual code (9) and flagged the discrepancy in the report rather than silently "fixing" test count —
  good judgment call, no action needed.

## Assessment

**Task quality:** Approved

**Reasoning:** Implementation matches the brief exactly, the long-format/entry-point-only decisions are
correctly realized, and the headline atomicity/is_new/fallback claims all hold up under direct inspection.
The gaps are test-coverage gaps (untested `source` column, untested pre-existing-empty-file branch, and an
undocumented TOCTOU edge case) rather than functional defects — worth a quick follow-up but not blocking.
