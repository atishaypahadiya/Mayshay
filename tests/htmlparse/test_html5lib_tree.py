"""Tree-construction conformance run against the vendored html5lib-tests.

Phase 1 implements 8 of the spec's 23 insertion modes, so a chunk of this
corpus cannot pass yet. Rather than leave the suite red -- which would stop
it detecting regressions -- every currently-failing case is listed in
KNOWN_MISSES below with the specific feature it is waiting on, and marked
strict-xfail. Same discipline as test_html5lib_tokenizer.py.

Nothing is hidden by that. Every case still runs, still gets compared
byte-for-byte against the fixture, and still records its real outcome
(`pass`/`fail`) to data/metrics/conformance.csv -- the metrics are computed
in the test body before the assertion, so they are independent of pytest's
xfail bookkeeping. `strict=True` means a case Task 7 fixes turns the suite
red as an XPASS until someone deletes its entry, so the ledger cannot drift
into a mute button.
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

# ---------------------------------------------------------------------------
# Ledger of deferred work: case id -> why it cannot pass yet.
#
# Derived from a hand-diagnosed reading of all 53 post-fix failures; there is
# no "misc" bucket and no case is listed without a named cause. Categories:
#
#   AFE      list of active formatting elements + adoption agency (Task 7)
#   TABLE    in_table / in_table_body / in_row / in_cell + foster parenting
#   SELECT   in_select / in_select_in_table
#   FRAMESET in_frameset / after_frameset
#   MODE     a missing rule inside one of the 8 modes this phase does own
#   TOKEN    a tokenizer-level gap, outside treebuilder.py entirely
# ---------------------------------------------------------------------------
_AFE = (
    "AFE: needs the list of active formatting elements and the adoption "
    "agency algorithm (Task 7)"
)
_TABLE = (
    "TABLE: needs the table insertion modes and foster parenting (out of "
    "phase 1)"
)
_SELECT = "SELECT: needs the in_select / in_select_in_table modes"
_FRAMESET = "FRAMESET: needs the in_frameset / after_frameset modes"

KNOWN_MISSES: dict[str, str] = {}
KNOWN_MISSES.update({
    f"tests1.dat:{i}": _AFE
    for i in (22, 23, 25, 31, 51, 53, 56, 60, 70, 71, 72, 73, 74, 75, 81,
              95, 96, 97)
})
KNOWN_MISSES.update({
    f"tests1.dat:{i}": _TABLE
    for i in (19, 20, 30, 32, 77, 78, 79, 86, 90, 93, 101, 105, 106, 107, 108)
})
KNOWN_MISSES.update({f"tests1.dat:{i}": _SELECT for i in (29, 34, 99)})
KNOWN_MISSES.update({f"tests1.dat:{i}": _FRAMESET for i in (104, 111)})
KNOWN_MISSES.update({
    # Two causes at once; both must land before this one goes green.
    "tests1.dat:110": _TABLE + "; also needs the MODE </br> rule below",

    # -- TOKEN: gaps in tokenizer.py, not the tree builder -----------------
    "tests1.dat:27": (
        "TOKEN: comment start / comment end states not implemented, so the "
        "abrupt-closing comment <!--> is not recognised; same gap already "
        "pinned in test_html5lib_tokenizer.py::KNOWN_MISSES"
    ),
    "tests1.dat:37": (
        "TOKEN: end-tag-open at EOF should emit the characters '</'; we emit "
        "nothing"
    ),

    # -- MODE: missing rules inside the 8 modes this phase owns. This is the
    # punch list for Task 7 and the only category that is arguably in scope.
    "tests1.dat:26": (
        "MODE in_head: 'any other end tag -> parse error, ignore' is not "
        "implemented, so a stray </div> pops <head> and moves <title> to body"
    ),
    "tests1.dat:91": "MODE in_head: 'any other end tag -> ignore' (see :26)",
    "tests1.dat:98": "MODE in_head: 'any other end tag -> ignore' (see :26)",
    "tests1.dat:21": (
        "MODE in_body: an h1-h6 START tag must pop a current h1-h6; we nest "
        "<h2> inside <h1>"
    ),
    "tests1.dat:94": "MODE in_body: h1-h6 start tag must pop a heading (see :21)",
    "tests1.dat:85": (
        "MODE after_head: a head-element start tag must be processed with the "
        "in_head rules, pushing <head> back on the stack"
    ),
    "tests1.dat:87": (
        "MODE in_body: a <body> start tag is a parse error to be ignored "
        "(attributes merged); we insert a nested <body> element"
    ),
    "tests1.dat:89": "MODE in_body: an <image> start tag must be renamed to img",
    "tests1.dat:33": (
        "MODE after_body: a comment must be inserted as the last child of the "
        "<html> element, not appended to the Document. TRAP: do NOT fix this "
        "by simply retargeting after_body's comment insertion point -- that "
        "breaks webkit01.dat:21, which passes today and needs the comment on "
        "the Document. The two cases differ by insertion mode, so Task 7 must "
        "split out a real 'after after body' mode rather than move the target."
    ),
    "tests1.dat:109": (
        "MODE in_body: a </br> end tag must be treated as a <br> start tag"
    ),
    "tests1.dat:50": (
        "MODE in_head: leading whitespace must be split off a character token "
        "and reprocessed; tokenizer deviation #1 coalesces ' -->  EOF' into "
        "one token and _is_space is all-or-nothing"
    ),
})

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
    # A partial run (-k, a single-case selection, -x) must not overwrite the
    # artifact with a truncated file that still looks complete. Leaving the
    # previous full-corpus file in place is strictly better than replacing it
    # with a quietly partial one.
    recorded = {row["case_id"] for row in _ROWS}
    expected = {case.id for case in CASES}
    if recorded != expected:
        print(
            f"[conformance] partial run ({len(recorded)}/{len(expected)} cases); "
            f"leaving {CONFORMANCE_CSV.name} untouched",
            file=sys.stderr,
        )
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


def _params():
    for case in CASES:
        marks = []
        if case.id in KNOWN_MISSES:
            marks.append(pytest.mark.xfail(strict=True, reason=KNOWN_MISSES[case.id]))
        yield pytest.param(case, marks=marks, id=case.id)


@requires_corpus
@pytest.mark.parametrize("case", list(_params()))
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


@requires_corpus
def test_tree_corpus_is_not_empty():
    """A loader regression that silently yields nothing must not read green."""
    assert len(CASES) == 112, (
        f"expected 112 in-scope cases from the pinned corpus, got {len(CASES)}; "
        "if the submodule moved, re-check KNOWN_MISSES before updating this"
    )


@requires_corpus
def test_known_misses_reference_real_cases():
    """Guard against the ledger rotting into entries that match nothing."""
    ids = {c.id for c in CASES}
    stale = sorted(set(KNOWN_MISSES) - ids)
    assert not stale, f"KNOWN_MISSES entries match no collected case: {stale}"
