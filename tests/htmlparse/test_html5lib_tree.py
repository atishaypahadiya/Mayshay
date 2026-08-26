"""Tree-construction conformance run against the vendored html5lib-tests.

Phase 1 implements 8 of the spec's 23 insertion modes, so this file is a
*baseline recorder*, not a green suite: cases needing the adoption agency
algorithm, the table insertion modes or foreign content are expected to
fail. Every case still runs and every outcome is written to
data/metrics/conformance.csv so the next task's improvement is measurable.
"""

import csv
import sys
import time
from pathlib import Path

import pytest

from mayshay.dom.node import serialize
from mayshay.htmlparse.treebuilder import TreeBuilder
from tests.support.dat import load_tree_tests
from tests.support.marks import requires_corpus

# Files whose features are in scope for phase 1. Everything else waits for
# the table modes, foreign content, and the adoption agency algorithm.
IN_SCOPE_FILES = ("tests1.dat",)

METRICS_DIR = Path(__file__).resolve().parents[2] / "data" / "metrics"
CONFORMANCE_CSV = METRICS_DIR / "conformance.csv"


def _cases():
    try:
        loaded = load_tree_tests(*IN_SCOPE_FILES)
    except FileNotFoundError:
        return []
    # Fragment cases need parse-fragment entry points (not built yet) and
    # script-on cases need a JS runtime; both would fail for reasons that say
    # nothing about the tree builder, so they are excluded rather than
    # silently counted as misses.
    fragments = [t for t in loaded if t.fragment is not None]
    scripted = [t for t in loaded if t.fragment is None and t.script == "on"]
    kept = [t for t in loaded if t.fragment is None and t.script != "on"]
    print(
        f"[conformance] {IN_SCOPE_FILES}: {len(loaded)} cases loaded, "
        f"{len(fragments)} excluded as fragment, "
        f"{len(scripted)} excluded as script-dependent, "
        f"{len(kept)} in scope",
        file=sys.stderr,
    )
    return kept


CASES = _cases()

# One row per case, flushed to conformance.csv when the session ends.
_ROWS: list[dict] = []


@pytest.fixture(scope="session", autouse=True)
def _conformance_metrics():
    yield
    if not _ROWS:
        return
    METRICS_DIR.mkdir(parents=True, exist_ok=True)
    fields = [
        "case_id",
        "outcome",
        "input_chars",
        "expected_lines",
        "actual_lines",
        "elements",
        "max_depth",
        "text_nodes",
        "parse_errors",
        "parse_time_ms",
    ]
    with CONFORMANCE_CSV.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        writer.writerows(_ROWS)


@requires_corpus
@pytest.mark.parametrize("case", CASES, ids=lambda c: c.id)
def test_tree_construction(case):
    builder = TreeBuilder(case.data)
    started = time.perf_counter()
    try:
        actual = serialize(builder.build())
    except Exception as exc:  # a crash is an outcome worth recording too
        _ROWS.append(
            {
                "case_id": case.id,
                "outcome": f"error:{type(exc).__name__}",
                "input_chars": len(case.data),
                "expected_lines": case.document.count("\n") + 1,
                "actual_lines": 0,
                "elements": builder.metrics["elements"],
                "max_depth": builder.metrics["max_depth"],
                "text_nodes": builder.metrics["text_nodes"],
                "parse_errors": builder.metrics["parse_errors"],
                "parse_time_ms": round(
                    (time.perf_counter() - started) * 1000, 3
                ),
            }
        )
        raise
    _ROWS.append(
        {
            "case_id": case.id,
            "outcome": "pass" if actual == case.document else "fail",
            "input_chars": len(case.data),
            "expected_lines": case.document.count("\n") + 1,
            "actual_lines": actual.count("\n") + 1,
            "elements": builder.metrics["elements"],
            "max_depth": builder.metrics["max_depth"],
            "text_nodes": builder.metrics["text_nodes"],
            "parse_errors": builder.metrics["parse_errors"],
            "parse_time_ms": round((time.perf_counter() - started) * 1000, 3),
        }
    )
    assert actual == case.document
