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
