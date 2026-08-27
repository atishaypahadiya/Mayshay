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

    stamp = f"{time.time():.6f}"

    # Build the whole row payload, then write once. Many small writes from
    # concurrent processes can interleave mid-row; a single append-mode write
    # of a small buffer will not in practice.
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=FIELDNAMES, lineterminator="\n")
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
    row_payload = buffer.getvalue()
    header_line = ",".join(FIELDNAMES) + "\n"

    # Whether a header is needed used to be decided by checking
    # `target.exists()` and then appending in a later, separate step -- a
    # classic time-of-check/time-of-use race. Two genuinely concurrent
    # first-writers can both observe "file absent" and each append its own
    # header; `csv.DictReader` reads the second one back as an ordinary data
    # row with `run_id == "run_id"`, silently corrupting the file. Close that
    # race for the common case -- file absent -- with an exclusive create:
    # `open("x")` raises for every caller but the one that actually creates
    # the file, so at most one process can ever win the header write.
    try:
        with target.open("x", encoding="utf-8", newline="") as handle:
            handle.write(header_line + row_payload)
        return rows
    except FileExistsError:
        pass

    # The file already existed -- created moments ago by us, by another
    # process, or as a pre-existing zero-byte placeholder. That last case can
    # still legitimately need a header, but deciding it from `stat()` here is
    # the same race as before, just narrower: it only matters if two writers
    # hit the *same already-existing empty file* at the same instant, which
    # this does not engineer away. `read()` defends the analysis side instead,
    # by discarding any row that is itself a stray duplicate header.
    is_new = target.stat().st_size == 0
    payload = (header_line if is_new else "") + row_payload
    with target.open("a", encoding="utf-8", newline="") as handle:
        handle.write(payload)
    return rows


def read(path: Path | None = None) -> list[dict[str, str]]:
    """Read rows back. Used by tests and by the analysis half of the project.

    Discards any row that is itself a stray duplicate header -- the residue
    of the narrow pre-existing-empty-file race documented in `emit` -- so a
    corrupt file cannot silently poison downstream analysis with a fake
    `run_id == "run_id"` row.
    """
    target = path or STAGES_CSV
    if not target.exists():
        return []
    with target.open(encoding="utf-8", newline="") as handle:
        return [row for row in csv.DictReader(handle) if row.get("run_id") != "run_id"]
