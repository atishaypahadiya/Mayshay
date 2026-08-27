# Task A: Shared metrics writer — report

## Changes per step

- **Step 1** — Created `tests/test_metrics.py` verbatim from the brief. It
  contains 9 test functions (the brief's code block, despite its Step 4
  saying "8 passed", actually lists 9: `test_emit_writes_one_row_per_key`,
  `test_header_written_once_across_appends`, `test_two_stages_share_a_run_id`,
  `test_new_key_needs_no_schema_change`, `test_floats_and_ints_both_survive`,
  `test_rows_are_sorted_by_key`, `test_empty_counter_writes_no_rows`,
  `test_explicit_path_wins_over_the_default`,
  `test_default_path_is_under_data_metrics`).

- **Step 2** — Ran `.venv/bin/pytest tests/test_metrics.py -v` before creating
  the module. Got a collection error:
  `ImportError: cannot import name 'metrics' from 'mayshay'` (Python 3.13
  reports this as ImportError rather than ModuleNotFoundError for a missing
  submodule under a package `__init__.py`, but it's the same failure mode the
  brief describes). Confirmed the tests fail for the right reason before
  writing any implementation.

- **Step 3** — Created `src/mayshay/metrics.py` verbatim from the brief:
  `new_run_id`, `emit`, `read`, `STAGES_CSV`, `METRICS_DIR`, `FIELDNAMES`.
  Docstring includes both design-decision rationales (long format vs. wide;
  entry-points-call-this vs. parse-methods-do-not) and the `METRICS_DIR`
  fallback warning referencing the Phase 1 `.pth` incident, all copied
  verbatim from the brief.

- **Step 4** — Ran `.venv/bin/pytest tests/test_metrics.py -v` again:
  **9 passed** in 0.02s (see full output below). Matches the task's stated
  definition of done (9, not the brief's stale "8").

- **Step 5** — Replaced the `CLAUDE.md` metrics bullet under `## Rules` with
  the exact text from the brief (mentions `self.metrics`, `entry points call
  the writer — never a parse method`, and the `tokenize`/`treebuild` two-stage
  split for `htmlparse`).

- **Step 6** — Committed `src/mayshay/metrics.py`, `tests/test_metrics.py`,
  and `CLAUDE.md` together.
  Commit: `cd19f4369696e6e33db05d48f9cd97247dd207f8`
  Message: `metrics: shared long-format writer for every pipeline stage`

## Exact test commands and full output

Before implementation (Step 2):
```
$ .venv/bin/pytest tests/test_metrics.py -v
...
ERROR collecting tests/test_metrics.py
ImportError: cannot import name 'metrics' from 'mayshay' (/Users/atishaypahadiya/projects/mayshay/src/mayshay/__init__.py)
=========================== short test summary info ===========================
ERROR tests/test_metrics.py
!!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!
1 error in 0.06s
```

After implementation (Step 4):
```
$ .venv/bin/pytest tests/test_metrics.py -v
collected 9 items
tests/test_metrics.py .........                                        [100%]
9 passed in 0.02s
```

Full suite after commit:
```
$ .venv/bin/pytest
5060 passed, 55 xfailed in 1.51s
```
5060 = 5051 (pre-existing) + 9 (new). 55 xfailed unchanged. 0 failed.

## Confirmation no test writes outside tmp_path

All 9 tests in `tests/test_metrics.py` construct their CSV target as
`tmp_path / "stages.csv"` (or `tmp_path / "elsewhere" / "stages.csv"` for the
explicit-path test) and pass it explicitly via `path=target` to `metrics.emit`
and `metrics.read`. The only test that touches the module-level default
(`metrics.STAGES_CSV`) is `test_default_path_is_under_data_metrics`, which
only inspects the `Path` object's `.parent.name` / `.parent.parent.name` —
it never calls `emit` or `read` against it, so it performs no I/O against the
real path.

Verified directly: `ls -la data/metrics/` before and after the full run shows
only the pre-existing `.gitkeep` and `conformance.csv` — no `stages.csv` was
created. `git status` is clean (the CSV files are gitignored per
`data/metrics/*.csv` in `.gitignore`, confirmed by grep, and in any case none
were created).

## Things in the brief that were wrong or ambiguous, and what I did

- **Step 4's "Expected: 8 passed" is stale/wrong.** The Step 1 code block it
  refers to actually contains 9 test functions, and the task instructions
  explicitly note this discrepancy ("the brief lists 8 tests plus the
  explicit-path test added in review"). I used the code block as given (9
  tests) and treated 9 passed as correct, matching the task's definition of
  done rather than the brief's inline comment. No code change was needed —
  only the expectation in the brief's own prose was outdated.
- Everything else in the brief (module docstring wording, function bodies,
  CLAUDE.md replacement bullet, gitignore assumption) matched actual repo
  state exactly; no other corrections were required.

## What a reviewer should scrutinise hardest

1. **The `METRICS_DIR`/`STAGES_CSV` fallback derivation** (`parents[2]` from
   `src/mayshay/metrics.py` file location) is exactly the code path that broke
   the whole suite in Phase 1 when the editable-install `.pth` was repointed.
   It is exercised by exactly one test (`test_default_path_is_under_data_metrics`)
   and only via `Path` attribute access, never by an actual write — that's
   intentional per the brief, but a reviewer should confirm no future caller
   is tempted to rely on the default path being correct rather than passing
   `path=` explicitly, since nothing enforces that at the type level.
2. **The single-buffered-write claim in the `emit` docstring/comment**
   ("many small writes ... can interleave mid-row; a single append-mode write
   ... will not in practice") is a concurrency safety argument that is not
   tested — there is no multi-process test exercising interleaved writers.
   It's asserted as a comment, not verified. Worth confirming this is
   considered acceptable for now (no concurrent-driver test exists yet) since
   cssparse/layout/paint will all call `emit` once those stages exist.
   Nothing in this task changes that; flagging it because the docstring makes
   a claim without a test backing it, and future reviewers on later Phase 2
   tasks should know that gap exists.
3. **`is_new = not target.exists() or target.stat().st_size == 0`** — correct
   per the brief's explicit callout of "an existing zero-byte file is a real
   case," and covered indirectly since `tmp_path` files never pre-exist as
   zero-byte before the first `emit` call in these tests. There's no test
   that pre-creates a zero-byte file and then calls `emit` to confirm the
   header still gets written in that specific case — the existing tests
   only exercise the "file doesn't exist yet" branch of `is_new`. Worth a
   reviewer's judgment call on whether that's sufficient coverage.

## Environment safety confirmation

- `.venv/lib/python3.13/site-packages/__editable__.mayshay-0.1.0.pth` was
  read but never modified. Its content before and after this task:
  `/Users/atishaypahadiya/projects/mayshay/src`.
- No file under `.venv/` was touched.
- `git status` is clean after the commit.

## Fix round 1

Coordinator review approved spec and quality, and raised three Important
findings plus one plan-doc correction. All four addressed in commit
`b9e4a72829f98a65329a26440b1aeeaf5aa1329a`.

**Important 1 — no test asserted `source`'s value.** Added
`test_row_matches_expected_dict_exactly`, which does a full-row round-trip:
asserts `timestamp` is present and non-empty, then compares every other
field against an exact expected dict. This is the general fix the
coordinator asked for (not just a `source` assertion) — it would fail if any
column, not just `source`, were dropped or wired to the wrong value, since
`csv.DictWriter` silently fills a missing key with `""` and a per-field
assertion could still pass by coincidence.

**Important 2 — `is_new` TOCTOU race.** Reworked `emit()`:
- Row payload (header-less) and the header line are now built as separate
  strings before any file I/O.
- First attempt: `target.open("x", ...)` — exclusive create. If this
  succeeds, this process is provably the only one that could have created
  the file, so it writes `header_line + row_payload` in one `write()` call
  and returns. This closes the race entirely for the file-absent case: two
  concurrent first-writers can no longer both believe they're new, because
  at most one `open("x")` call can ever succeed against the same path.
- On `FileExistsError` (file already existed, whether from a prior `emit`
  call, another process, or a pre-existing placeholder), falls back to the
  original `stat().st_size == 0` check and an append-mode write. I did not
  try to close this narrower race (two writers hitting the *same
  already-existing empty file* at the exact same instant) — doing so would
  need a lock file or similar, which felt like real complexity for a case
  that requires both a pre-existing empty file AND a concurrent second
  writer at that exact moment. Instead of leaving the old comment's
  unscoped safety claim in place, I documented the residual race explicitly
  in the code and pushed the actual defense to the read side, per the
  coordinator's "harden read() either way" instruction.
- **Chosen approach: the coordinator's suggested exclusive-create shape**,
  taken as the primary fix rather than merely "worth evaluating" — it fully
  closes the common case at zero added complexity (no lock file, no retry
  loop) and composes with the existing "build the whole payload, write once"
  design. I did not find a cleaner shape that also closes the narrower
  existing-empty-file case without adding a lock file, so I left that case
  open and compensated in `read()`.
- `read()` now filters out any row where `row.get("run_id") == "run_id"` —
  i.e., a stray duplicate header read back as data — regardless of how it
  got there. Covered by the new
  `test_read_discards_a_stray_duplicate_header_row`, which manually appends
  a second header line and confirms `read()` still returns only the real
  row.

**Important 3 — no zero-byte pre-existing file test.** Added
`test_header_written_for_preexisting_empty_file`: touches an empty file,
calls `emit`, and asserts the header appears exactly once and the row reads
back correctly.

**Plan correction.** `docs/plans/2026-08-26-phase-2-css-to-styled-tree.md`
line 297 said "Expected: 8 passed" for Task A Step 4; changed to "Expected: 9
passed" to match the Step 1 code block, which has always had 9 test
functions.

### Verification after fix round 1

```
$ .venv/bin/pytest tests/test_metrics.py -v
collected 12 items
tests/test_metrics.py ............                                     [100%]
12 passed in 0.03s

$ .venv/bin/pytest
5063 passed, 55 xfailed in 1.44s
```
5063 = 5051 (pre-existing baseline) + 12 (test_metrics.py, up from 9).
0 failed.

- `data/metrics/` after the full run still contains only the pre-existing
  `.gitkeep` and `conformance.csv` — no `stages.csv`, confirming no test in
  the file writes outside `tmp_path`.
- `.venv/lib/python3.13/site-packages/__editable__.mayshay-0.1.0.pth`
  re-checked: unchanged (`/Users/atishaypahadiya/projects/mayshay/src`).
- `git status --porcelain` was clean immediately before this commit (only
  the three intended files were modified) and clean again after it.

Commit: `b9e4a72829f98a65329a26440b1aeeaf5aa1329a`
Message: `metrics: close header TOCTOU race, harden read(), assert full rows`
