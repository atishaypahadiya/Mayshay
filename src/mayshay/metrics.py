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
