### Task A: Shared metrics writer

The rule "every stage emits timing + size metrics to `data/metrics/`" is currently satisfied only by a pytest fixture writing `conformance.csv`. Nothing in `src/mayshay/` writes metrics at all.

**Schema is long, not wide** — `run_id, timestamp, stage, source, key, value`, one row per metric key. A wide table forces a schema migration every time a stage adds a counter, which is precisely the "adopt without changing the schema" requirement failing. `conformance.csv` is left alone: it is a per-case conformance artifact, and merging the two would force one into the wrong shape.

**The writer is called by entry points, never by a parse method.** File I/O inside `TreeBuilder.build()` would make the parser non-reentrant, add a syscall to a function measured in microseconds, and mutate a data file on every test run. Stages own the counters; drivers own the decision to persist. No environment-variable gate — explicit beats a hidden global.

**Files:**
- Create: `src/mayshay/metrics.py`, `tests/test_metrics.py`
- Modify: `CLAUDE.md`

**Interfaces:**
- Consumes: nothing
- Produces:
  - `metrics.new_run_id() -> str`
  - `metrics.emit(stage: str, counters: Counter[str], *, source: str, run_id: str, path: Path | None = None) -> int` — appends one row per key, returns rows written
  - `metrics.read(path: Path | None = None) -> list[dict[str, str]]`
  - `metrics.STAGES_CSV: Path`, `metrics.FIELDNAMES: tuple[str, ...]`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_metrics.py`:

```python
from collections import Counter

from mayshay import metrics


def test_emit_writes_one_row_per_key(tmp_path):
    target = tmp_path / "stages.csv"
    written = metrics.emit(
        "tokenize", Counter({"start_tags": 3, "parse_errors": 1}),
        source="a.html", run_id="r1", path=target,
    )
    assert written == 2
    rows = metrics.read(target)
    assert {r["key"] for r in rows} == {"start_tags", "parse_errors"}
    assert all(r["run_id"] == "r1" and r["stage"] == "tokenize" for r in rows)


def test_header_written_once_across_appends(tmp_path):
    target = tmp_path / "stages.csv"
    metrics.emit("tokenize", Counter({"a": 1}), source="x", run_id="r1", path=target)
    metrics.emit("treebuild", Counter({"b": 2}), source="x", run_id="r1", path=target)
    assert target.read_text().count("run_id,timestamp") == 1
    assert len(metrics.read(target)) == 2


def test_two_stages_share_a_run_id(tmp_path):
    target = tmp_path / "stages.csv"
    run = metrics.new_run_id()
    metrics.emit("tokenize", Counter({"a": 1}), source="x", run_id=run, path=target)
    metrics.emit("treebuild", Counter({"b": 2}), source="x", run_id=run, path=target)
    rows = metrics.read(target)
    assert {r["stage"] for r in rows} == {"tokenize", "treebuild"}
    assert {r["run_id"] for r in rows} == {run}


def test_new_key_needs_no_schema_change(tmp_path):
    """The whole point of the long format."""
    target = tmp_path / "stages.csv"
    metrics.emit("tokenize", Counter({"a": 1}), source="x", run_id="r1", path=target)
    before = target.read_text()
    metrics.emit("cssparse", Counter({"never_seen": 9}), source="x", run_id="r1", path=target)
    assert target.read_text().startswith(before)
    assert metrics.read(target)[-1]["key"] == "never_seen"


def test_floats_and_ints_both_survive(tmp_path):
    target = tmp_path / "stages.csv"
    metrics.emit(
        "treebuild", Counter({"elements": 12, "parse_time_ms": 0.048}),
        source="x", run_id="r1", path=target,
    )
    got = {r["key"]: r["value"] for r in metrics.read(target)}
    assert got["elements"] == "12"
    assert float(got["parse_time_ms"]) == 0.048


def test_rows_are_sorted_by_key(tmp_path):
    target = tmp_path / "stages.csv"
    metrics.emit("s", Counter({"z": 1, "a": 2, "m": 3}), source="x", run_id="r1", path=target)
    assert [r["key"] for r in metrics.read(target)] == ["a", "m", "z"]


def test_empty_counter_writes_no_rows(tmp_path):
    target = tmp_path / "stages.csv"
    assert metrics.emit("s", Counter(), source="x", run_id="r1", path=target) == 0
    assert metrics.read(target) == []


def test_explicit_path_wins_over_the_default(tmp_path):
    """Drivers pass a path; the repo-relative default is only a fallback.

    `parents[2]` reaches the repo root solely because the package is installed
    editable from inside the checkout, and Phase 1 saw that pointer broken by
    a subagent. Nothing that must be correct may depend on it.
    """
    target = tmp_path / "elsewhere" / "stages.csv"
    metrics.emit("s", Counter({"a": 1}), source="x", run_id="r1", path=target)
    assert target.exists()
    assert metrics.read(target)[0]["key"] == "a"


def test_default_path_is_under_data_metrics():
    """The fallback still has to be sane when it IS used."""
    assert metrics.STAGES_CSV.parent.name == "metrics"
    assert metrics.STAGES_CSV.parent.parent.name == "data"
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/pytest tests/test_metrics.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'mayshay.metrics'`

- [ ] **Step 3: Implement the writer**

Create `src/mayshay/metrics.py`:

```python
"""
Shared metrics writer.

CLAUDE.md requires every pipeline stage to emit timing and size metrics to
`data/metrics/`. Stages populate a `Counter` as they run; this module turns
one into rows.

Two decisions worth not re-litigating:

1. **Long format**, not wide: one row per (run, stage, key). A wide table —
   a column per metric — forces a schema migration every time a stage adds a
   counter, so cssparse, layout and paint could not adopt it without changing
   the schema. Long absorbs new keys for free, and pivots on the way out.

2. **Entry points call this, parse methods do not.** Writing a file as a side
   effect of `TreeBuilder.build()` would make the parser non-reentrant, add a
   syscall to a function measured in microseconds, and mutate a data file on
   every test run. Stages own the counters; drivers own persistence. A library
   that writes files as a side effect of being called is a library people
   stop calling.

`data/metrics/conformance.csv` is a separate, per-case conformance artifact and
is deliberately not merged into this schema.
"""

from __future__ import annotations

import csv
import io
import time
import uuid
from collections import Counter
from pathlib import Path

# FALLBACK DEFAULT ONLY -- drivers pass an explicit path.
#
# `parents[2]` reaches the repo root only because the package is installed
# editable from inside this checkout. A wheel install, a relocated package, or
# a repointed `.pth` all break it. That is not hypothetical: during Phase 1 a
# subagent repointed this project's editable-install `.pth` at a /tmp copy and
# deleted the copy, taking the entire suite down while `git status` reported
# clean, because `.venv/` is gitignored. Nothing that must be correct may
# depend on this derivation.
METRICS_DIR = Path(__file__).resolve().parents[2] / "data" / "metrics"
STAGES_CSV = METRICS_DIR / "stages.csv"

FIELDNAMES = ("run_id", "timestamp", "stage", "source", "key", "value")


def new_run_id() -> str:
    """Group rows emitted by different stages of one pipeline run."""
    return uuid.uuid4().hex[:12]


def emit(
    stage: str,
    counters: Counter[str],
    *,
    source: str,
    run_id: str,
    path: Path | None = None,
) -> int:
    """Append one row per metric key. Returns the number of rows written.

    `stage` is a pipeline stage name — `htmlparse` emits two, `tokenize` and
    `treebuild`, because their counters and their error counts are separately
    meaningful. `source` identifies the document (a path or URL).

    `path` SHOULD be passed explicitly by drivers. The module-level default is
    a convenience for interactive use and is derived from `__file__`, which is
    only repo-relative under an editable install — see the note on METRICS_DIR.
    """
    target = path or STAGES_CSV
    target.parent.mkdir(parents=True, exist_ok=True)
    if not counters:
        return 0

    is_new = not target.exists() or target.stat().st_size == 0
    stamp = f"{time.time():.6f}"

    # Build the whole payload, then write once. Many small writes from
    # concurrent processes can interleave mid-row; a single append-mode write
    # of a small buffer will not in practice.
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=FIELDNAMES, lineterminator="\n")
    if is_new:
        writer.writeheader()
    rows = 0
    for key in sorted(counters):
        writer.writerow({
            "run_id": run_id,
            "timestamp": stamp,
            "stage": stage,
            "source": source,
            "key": key,
            "value": counters[key],
        })
        rows += 1

    with target.open("a", encoding="utf-8", newline="") as handle:
        handle.write(buffer.getvalue())
    return rows


def read(path: Path | None = None) -> list[dict[str, str]]:
    """Read rows back. Used by tests and by the analysis half of the project."""
    target = path or STAGES_CSV
    if not target.exists():
        return []
    with target.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))
```

- [ ] **Step 4: Run to verify they pass**

Run: `.venv/bin/pytest tests/test_metrics.py -v`
Expected: 8 passed.

- [ ] **Step 5: Record the two-stage decision in CLAUDE.md**

Replace the metrics bullet under `## Rules`:

```markdown
- Every stage emits timing + size metrics to data/metrics/. Stages populate
  `self.metrics`; `src/mayshay/metrics.py` writes them, and entry points call
  the writer — never a parse method. `htmlparse` emits TWO stage values,
  `tokenize` and `treebuild`: the five-box pipeline above is the conceptual
  shape, not the metrics schema, and their counters and error counts are
  separately meaningful.
```

- [ ] **Step 6: Commit**

```bash
git add src/mayshay/metrics.py tests/test_metrics.py CLAUDE.md
git commit -m "metrics: shared long-format writer for every pipeline stage"
```

---

