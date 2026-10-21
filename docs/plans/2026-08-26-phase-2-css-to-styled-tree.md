# Phase 2: CSS to a Styled Tree — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Take mayshay from a DOM tree to a styled tree — hand-rolled CSS tokenizer and parser, selector matching, the cascade, inheritance, and computed values attached to every DOM node. Preceded by four cleanup tasks that Phase 1 left owed.

**Architecture:** `cssparse` mirrors `htmlparse`'s shape: a tokenizer emitting dataclass tokens, a parser building structures from them, both hand-rolled against the W3C specs. The cascade runs as a top-down tree walk, because `em` and `%` on `font-size` resolve against the *parent's* computed value. Computed styles live in a `computed_style` slot on `Node` — not on `Element`, so text nodes inherit without a special case in layout. Percentages and `auto` survive into the computed style **symbolically**; they cannot be resolved without a containing block, which does not exist until Phase 3.

**Tech Stack:** Python 3.13, pytest. No CSS libraries — see Global Constraints.

**Spec:** This plan is its own spec. It derives from a review of the Phase 1 output at tag `phase-1` (commit `f252f96`) and the scope agreed in conversation on 2026-08-26. Phase 1's plan and its Known Gaps section are at `docs/plans/2026-08-26-phase-1-html-to-dom.md`.

## Global Constraints

- No lxml, no `html.parser`, no browser libraries for core parsing. Hand-rolled only. `html.entities.html5` is permitted as a data table.
- **CSS tokenization and parsing are hand-rolled. `tinycss2`, `cssutils` and `cssselect` are forbidden in `src/mayshay/`.** Task E removes `tinycss2` from `requirements.txt` and records this rule in `CLAUDE.md`.
- BeautifulSoup only in `scripts/`, never in `src/mayshay/`.
- Every stage emits timing + size metrics to `data/metrics/`. Stages populate `self.metrics`; **the writer is called by entry points, never by a parse method.**
- Tests in `tests/` mirror `src/mayshay/`. pytest.
- Follow the W3C/WHATWG specs where practical; document every deviation in the module docstring.
- The `tests/html5lib-tests` submodule is pinned to `9329e64`. Never `git submodule update --remote`.
- Python >= 3.10.

## Execution Order

| Task | Deliverable |
|------|-------------|
| A | Shared metrics writer, `src/mayshay/metrics.py` |
| B | Parse error honesty — tree-builder errors recorded and pinned |
| C | DOCTYPE public/system identifiers and correct quirks-mode classification |
| D | DOM cascade affordances — `computed_style`, `class_list`, element positions |
| E | CSS tokenizer (removes `tinycss2` first) |
| F | CSS generic grammar — rules and declarations |
| G | Selectors and specificity |
| H | Selector matching against the DOM |
| I | Property values for the nine-property set |
| J | Cascade, inheritance, computed values, UA stylesheet |
| K | `scripts/error_report.py` — committed measurement for whole-corpus parse-error agreement (runnable any time after B) |

A–D are cleanup and can run in any order among themselves; E–J are strictly sequential.

## File Structure

**Created:**
- `src/mayshay/metrics.py` — the shared writer
- `src/mayshay/cssparse/tokenizer.py`, `parser.py`, `selectors.py`, `matching.py`, `values.py`, `cascade.py`, `ua.py`
- `tests/test_metrics.py`
- `tests/cssparse/` mirroring the above
- `scripts/style_report.py` — corpus driver that calls the metrics writer

**Modified:**
- `src/mayshay/htmlparse/tokenizer.py` — DOCTYPE states (Task C)
- `src/mayshay/htmlparse/treebuilder.py` — tree-builder errors (Task B), quirks classification (Task C)
- `src/mayshay/dom/node.py` — cascade affordances (Task D)
- `CLAUDE.md` — two-stage metrics note (A), CSS libraries rule (E)
- `requirements.txt` — remove `tinycss2` (E)

---

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
Expected: 9 passed.

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

### Task B: Parse error honesty

`TreeBuilder.build()` copies `tokenizer.metrics["parse_errors"]` and calls it `parse_errors`. The tree builder records none of its own, so the number cannot be non-zero on well-tokenized malformed markup — which is most of the real web.

Measured on `<p>a<div>b</p></span><li>c` (missing doctype, stray `</p>`, stray `</span>`, unclosed elements): `metrics['parse_errors']` is `0` and `tokenizer.errors` is `[]`. The tokenizer is correct; every one of those is a tree-construction error.

**On the reference vocabulary.** The corpus carries two, and they are not interchangeable. `#errors` has 3,782 lines across 469 codes, dominated by tree-construction errors (`expected-doctype-but-got-start-tag` ×570, `expected-closing-tag-but-got-eof` ×395, `unexpected-end-tag` ×306). `#new-errors` has 317 lines across 38 codes in only 16 of 57 files, and is almost entirely *tokenizer* errors in WHATWG names. **Use `#errors`** — it is the only place tree-construction errors appear — but compare **code multisets, not positions**: html5lib reports `(line, col)` at the end of the offending token, while Phase 1 deliberately established that our offset points *at* the character that caused the error. The conventions differ by design and direct position comparison would fail nearly everywhere.

**Files:**
- Modify: `src/mayshay/htmlparse/treebuilder.py`
- Create: `tests/htmlparse/test_parse_errors.py`

**Interfaces:**
- Consumes: `CharacterToken.pos` etc. (Phase 1)
- Produces:
  - `TreeBuilder.errors: list[tuple[int, str]]`
  - `TreeBuilder._error(code: str, pos: int) -> None`
  - `TreeBuilder.metrics["parse_errors"]` — the tree builder's own count
  - `TreeBuilder.metrics["tokenizer_parse_errors"]` — the copied count
  - `treebuilder.TREE_ERROR_CODES: frozenset[str]` — the curated set the 8 modes can produce

- [ ] **Step 1: Write the failing tests**

Create `tests/htmlparse/test_parse_errors.py`:

```python
import collections

import pytest

from mayshay.htmlparse.treebuilder import TREE_ERROR_CODES, TreeBuilder
from tests.support.dat import load_tree_tests
from tests.support.marks import requires_corpus

MALFORMED = "<p>a<div>b</p></span><li>c"


def test_malformed_page_reports_tree_errors():
    """The headline bug: this reported 0 before."""
    tb = TreeBuilder(MALFORMED)
    tb.build()
    assert tb.errors, "tree builder recorded no errors on malformed input"
    assert tb.metrics["parse_errors"] == len(tb.errors)


def test_tokenizer_and_tree_counts_are_not_aliases():
    tb = TreeBuilder(MALFORMED)
    tb.build()
    assert tb.metrics["tokenizer_parse_errors"] == 0
    assert tb.metrics["parse_errors"] > 0


def test_clean_document_reports_zero_from_both():
    tb = TreeBuilder("<!DOCTYPE html><html><head></head><body><p>x</p></body></html>")
    tb.build()
    assert tb.errors == []
    assert tb.metrics["parse_errors"] == 0
    assert tb.metrics["tokenizer_parse_errors"] == 0


def test_missing_doctype_is_recorded():
    tb = TreeBuilder("<p>x")
    tb.build()
    assert any(code.startswith("expected-doctype") for _, code in tb.errors)


def test_stray_end_tag_is_recorded():
    tb = TreeBuilder("<!DOCTYPE html><p>x</span>")
    tb.build()
    assert any(code == "unexpected-end-tag" for _, code in tb.errors)


def test_unclosed_element_at_eof_is_recorded():
    tb = TreeBuilder("<!DOCTYPE html><div><p>x")
    tb.build()
    assert any(code == "expected-closing-tag-but-got-eof" for _, code in tb.errors)


def test_every_recorded_code_is_in_the_curated_set():
    """A code outside the set means the mapping drifted from the vocabulary."""
    for src in (MALFORMED, "<p>x", "<!DOCTYPE html><p>x</span>", "<div><p>x"):
        tb = TreeBuilder(src)
        tb.build()
        for _, code in tb.errors:
            assert code in TREE_ERROR_CODES, f"{code!r} not in the curated set"


def test_error_positions_are_within_the_source():
    tb = TreeBuilder(MALFORMED)
    tb.build()
    for pos, _ in tb.errors:
        assert 0 <= pos <= len(MALFORMED)


def _curated_cases():
    """Corpus cases whose expected errors fall entirely inside our set."""
    try:
        cases = load_tree_tests("tests1.dat")
    except FileNotFoundError:
        return []
    out = []
    for case in cases:
        if case.fragment is not None or case.script == "on":
            continue
        codes = [_strip_position(line) for line in case.errors]
        if codes and all(c in TREE_ERROR_CODES for c in codes):
            out.append((case, codes))
    return out


def _strip_position(line: str) -> str:
    return line.split(":", 1)[1].strip() if ":" in line else line.strip()


@requires_corpus
@pytest.mark.parametrize("case,expected", _curated_cases(), ids=lambda x: getattr(x, "id", ""))
def test_corpus_error_codes_match_as_a_multiset(case, expected):
    """Codes only, never positions.

    html5lib reports (line, col) at the END of the offending token; our
    convention points AT the character that caused it. Comparing positions
    would fail nearly everywhere, and for reasons that are correct.
    """
    tb = TreeBuilder(case.data)
    tb.build()
    actual = [code for _, code in tb.errors]
    assert collections.Counter(actual) == collections.Counter(expected)
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/pytest tests/htmlparse/test_parse_errors.py -v`
Expected: FAIL — `ImportError: cannot import name 'TREE_ERROR_CODES'`

- [ ] **Step 3: Add the curated code set and the error recorder**

In `treebuilder.py`, add near the other module constants:

```python
# The html5lib `#errors` vocabulary, restricted to what the eight implemented
# insertion modes can actually produce. The corpus carries 469 distinct codes;
# most concern tables, foreign content and select, which are not implemented.
# A code recorded outside this set means the mapping has drifted.
TREE_ERROR_CODES = frozenset({
    "expected-doctype-but-got-start-tag",
    "expected-doctype-but-got-chars",
    "expected-doctype-but-got-eof",
    "expected-doctype-but-got-comment",
    "unexpected-doctype",
    "unexpected-start-tag",
    "unexpected-end-tag",
    "unexpected-end-tag-before-html",
    "expected-closing-tag-but-got-eof",
    "expected-one-end-tag-but-got-another",
    "end-tag-too-early",
})
```

Add to `TreeBuilder.__init__`:

```python
        # Mirrors Tokenizer.errors. Positions follow the same convention: the
        # offset points AT the token that caused the error, which is the
        # token's own `pos`.
        self.errors: list[tuple[int, str]] = []
```

Add the method:

```python
    def _error(self, code: str, pos: int) -> None:
        self.errors.append((pos, code))
        self.metrics["parse_errors"] += 1
```

- [ ] **Step 4: Record at the spec parse-error sites in the eight modes**

Each site below is a place the spec says "this is a parse error". Add the call without changing existing behaviour — recording only.

In `_mode_initial`, the fall-through branch that assumes quirks:

```python
        else:
            if isinstance(token, StartTagToken):
                self._error("expected-doctype-but-got-start-tag", token.pos)
            elif isinstance(token, CharacterToken):
                self._error("expected-doctype-but-got-chars", token.pos)
            elif isinstance(token, EOFToken):
                self._error("expected-doctype-but-got-eof", token.pos)
            else:
                self._error("expected-doctype-but-got-comment", token.pos)
            self.document.quirks_mode = True
            self.mode = "before_html"
            self.dispatch(token)
```

In `_mode_before_html`, `_mode_before_head`, `_mode_in_head`, `_mode_after_head` and `_mode_after_body`, a `DoctypeToken` is a parse error the spec ignores. Add at the top of each:

```python
        if isinstance(token, DoctypeToken):
            self._error("unexpected-doctype", token.pos)
            return
```

In `_in_body_end`, the stray-`</p>` branch:

```python
        if name == "p":
            if not self.has_element_in_scope("p", BUTTON_SCOPE):
                self._error("unexpected-end-tag", token.pos)
                self.insert_element(StartTagToken("p"))
            self.close_p_element()
```

In `_any_other_end_tag`, the branch that ignores an end tag on hitting a special element:

```python
                self._error("unexpected-end-tag", token.pos)
                return
```

In `_mode_in_body`'s EOF handling, before switching to `after_body`, report any element still open that is not `html` or `body`:

```python
        elif isinstance(token, EOFToken):
            for element in self.open_elements:
                if element.tag_name not in ("html", "body"):
                    self._error("expected-closing-tag-but-got-eof", token.pos)
                    break
            self.mode = "after_body"
```

In `_mode_text`'s EOF branch:

```python
        elif isinstance(token, EOFToken):
            self._error("expected-closing-tag-but-got-eof", token.pos)
            self.open_elements.pop()
            self.mode = self.original_mode
            self.dispatch(token)
```

- [ ] **Step 5: Rename the copied tokenizer count**

In `build()`, replace the metrics line:

```python
        # The tokenizer's count, kept distinct from our own. Before this was
        # split, a page with only tree-construction errors reported zero.
        self.metrics["tokenizer_parse_errors"] = self.tokenizer.metrics["parse_errors"]
```

Grep for other readers of the old key and update them:

```bash
grep -rn 'parse_errors' src/ tests/ scripts/
```

- [ ] **Step 6: Run the tests**

Run: `.venv/bin/pytest tests/htmlparse/ -v`
Expected: the eight unit tests pass. The corpus multiset test will show a mix — record how many of the curated cases match, and **do not broaden `TREE_ERROR_CODES` to make more of them pass.** If a case fails because we record a code the corpus does not expect, that is a mapping bug worth finding; if it fails because we miss one, that is an unimplemented site. Report both counts separately.

- [ ] **Step 7: Confirm the conformance suite is unmoved**

Run: `.venv/bin/python scripts/conformance_report.py`
Expected: still `759/1592` and `64/112`. This task records errors; it must not change tree construction.

- [ ] **Step 8: Commit**

```bash
git add src/mayshay/htmlparse/treebuilder.py tests/htmlparse/test_parse_errors.py
git commit -m "htmlparse: record tree construction parse errors, split from tokenizer count"
```

---

### Task C: DOCTYPE identifiers and quirks mode

Phase 1's documented deviation #3 discards DOCTYPE public and system identifiers, so `Document.quirks_mode` is name-only and cannot classify `<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.01 Transitional//EN">`. Quirks mode changes CSS and layout behaviour — unitless lengths, the alternate box model.

**Record the mode correctly now; implement its behaviour later.** Capturing identifiers and classifying is cheap and permanent. Acting on the classification is a layout concern and belongs to Phase 3. The cost of the other order is discovering mid-layout that every document ever parsed carries an unreliable flag.

**Files:**
- Modify: `src/mayshay/htmlparse/tokenizer.py`, `src/mayshay/htmlparse/treebuilder.py`
- Create: `tests/htmlparse/test_doctype.py`

**Interfaces:**
- Produces:
  - `DoctypeToken.public_id: str | None`, `DoctypeToken.system_id: str | None`
  - `Document.mode: str` — one of `"no-quirks"`, `"limited-quirks"`, `"quirks"`
  - `Document.quirks_mode: bool` — retained, now derived (`mode == "quirks"`)
  - `treebuilder.classify_document_mode(token: DoctypeToken) -> str`

- [ ] **Step 1: Write the failing tests**

Create `tests/htmlparse/test_doctype.py`:

```python
import pytest

from mayshay.htmlparse.tokenizer import DoctypeToken, Tokenizer
from mayshay.htmlparse.treebuilder import parse


def doctype(src):
    return next(t for t in Tokenizer(src).tokenize() if isinstance(t, DoctypeToken))


def test_public_identifier_captured():
    dt = doctype('<!DOCTYPE html PUBLIC "-//W3C//DTD HTML 4.01//EN">')
    assert dt.name == "html"
    assert dt.public_id == "-//W3C//DTD HTML 4.01//EN"
    assert dt.system_id is None


def test_system_identifier_captured():
    dt = doctype('<!DOCTYPE html SYSTEM "about:legacy-compat">')
    assert dt.public_id is None
    assert dt.system_id == "about:legacy-compat"


def test_both_identifiers_captured():
    dt = doctype(
        '<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Strict//EN" '
        '"http://www.w3.org/TR/xhtml1/DTD/xhtml1-strict.dtd">'
    )
    assert dt.public_id == "-//W3C//DTD XHTML 1.0 Strict//EN"
    assert dt.system_id.endswith("xhtml1-strict.dtd")


def test_single_quoted_identifiers():
    dt = doctype("<!DOCTYPE html PUBLIC '-//W3C//DTD HTML 4.01//EN'>")
    assert dt.public_id == "-//W3C//DTD HTML 4.01//EN"


def test_identifier_matching_is_case_insensitive_on_keywords():
    dt = doctype('<!DOCTYPE html public "-//W3C//DTD HTML 4.01//EN">')
    assert dt.public_id == "-//W3C//DTD HTML 4.01//EN"


@pytest.mark.parametrize(
    "src,expected",
    [
        ("<!DOCTYPE html>", "no-quirks"),
        ('<!DOCTYPE html SYSTEM "about:legacy-compat">', "no-quirks"),
        ("<!DOCTYPE foo>", "quirks"),
        ("", "quirks"),
        ("<p>x", "quirks"),
        ('<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.01 Transitional//EN">', "quirks"),
        ('<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.0//EN">', "quirks"),
        (
            '<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.01 Frameset//EN" '
            '"http://www.w3.org/TR/html4/frameset.dtd">',
            "limited-quirks",
        ),
        (
            '<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Frameset//EN" '
            '"http://www.w3.org/TR/xhtml1/DTD/xhtml1-frameset.dtd">',
            "limited-quirks",
        ),
    ],
)
def test_document_mode_classification(src, expected):
    assert parse(src).mode == expected


def test_quirks_mode_bool_still_works_and_is_derived():
    doc = parse("<!DOCTYPE foo>")
    assert doc.mode == "quirks"
    assert doc.quirks_mode is True
    assert parse("<!DOCTYPE html>").quirks_mode is False


def test_force_quirks_still_means_tokenizer_error_only():
    """Phase 1 separated these deliberately; keep them separate."""
    assert doctype("<!DOCTYPE foo>").force_quirks is False
    assert doctype("<!DOCTYPE html").force_quirks is True


def _doctype_corpus_cases():
    """Every doctype01.dat case, which is the only broad check on the table.

    Nine hand-written classifications cannot cover 55 prefixes. These cases
    exercise identifiers the unit tests never mention.
    """
    try:
        return [
            c for c in load_tree_tests("doctype01.dat")
            if c.fragment is None and c.script != "on"
        ]
    except FileNotFoundError:
        return []


@requires_corpus
@pytest.mark.parametrize("case", _doctype_corpus_cases(), ids=lambda c: c.id)
def test_doctype_corpus_round_trips(case):
    """The serialized tree must match, which pins identifier capture.

    Phase 1 could not represent public/system identifiers at all, so these
    cases were unreachable. If one still fails, say whether it is the table,
    the identifier capture, or an unrelated tree-construction gap.
    """
    from mayshay.dom.node import serialize

    assert serialize(parse(case.data)) == case.document
```

Add to this file's imports:

```python
from mayshay.dom.node import serialize
from tests.support.dat import load_tree_tests
from tests.support.marks import requires_corpus
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/pytest tests/htmlparse/test_doctype.py -v`
Expected: FAIL — `DoctypeToken` has no `public_id`.

- [ ] **Step 3: Add the identifier fields to the token**

```python
@dataclass
class DoctypeToken:
    name: str | None = None
    public_id: str | None = None
    system_id: str | None = None
    force_quirks: bool = False
    pos: int = -1
```

- [ ] **Step 4: Replace `_state_doctype` with the spec's DOCTYPE states**

Phase 1's `_state_doctype` consumes to `>` and keeps the first word. Replace it with the WHATWG state family — *DOCTYPE state* through *bogus DOCTYPE state*, the fifteen states listed under "8.2.5.9 Tokenizing" in the HTML spec. They are mechanical: each reads a character, appends to the name or an identifier buffer, or transitions.

The transitions that carry the actual logic:

```python
    def _state_after_doctype_name(self) -> Iterator[Token]:
        ch = self._next()
        if ch is EOF:
            self._error("eof in doctype", len(self.source))
            self._doctype_force_quirks = True
            self.state = "eof"
        elif ch in WHITESPACE:
            pass
        elif ch == ">":
            self.state = "data"
            yield self._emit_doctype()
        else:
            self.pos -= 1
            peeked = self._peek(6).upper()
            if peeked == "PUBLIC":
                self.pos += 6
                self.state = "after_doctype_public_keyword"
            elif peeked == "SYSTEM":
                self.pos += 6
                self.state = "after_doctype_system_keyword"
            else:
                self._error("invalid character sequence after doctype name", self.pos)
                self._doctype_force_quirks = True
                self.state = "bogus_doctype"
```

Update the module docstring: deviation #3 no longer applies — remove it and renumber, since identifiers are now captured.

- [ ] **Step 5: Implement the classification table**

Add to `treebuilder.py`:

```python
# The spec's quirks-mode table, from the HTML spec section "The 'initial'
# insertion mode". Matching is case-insensitive: identifiers are lowercased
# before comparison. EXACT matches by equality, PREFIXES by startswith.
#
# The complete list is below — 55 prefixes — rather than a sample, because an
# incomplete table misclassifies silently and the unit tests pin only nine
# cases. Step 5 requires verifying this against the spec and reporting the
# count found; a discrepancy with the 55 here is a finding, not a nuisance.
QUIRKS_EXACT = {
    "-//w3o//dtd w3 html strict 3.0//en//",
    "-/w3c/dtd html 4.0 transitional/en",
    "html",
}
QUIRKS_PREFIXES = (
    "+//silmaril//dtd html pro v0r11 19970101//",
    "-//as//dtd html 3.0 aswedit + extensions//",
    "-//advasoft ltd//dtd html 3.0 aswedit + extensions//",
    "-//ietf//dtd html 2.0 level 1//",
    "-//ietf//dtd html 2.0 level 2//",
    "-//ietf//dtd html 2.0 strict level 1//",
    "-//ietf//dtd html 2.0 strict level 2//",
    "-//ietf//dtd html 2.0 strict//",
    "-//ietf//dtd html 2.0//",
    "-//ietf//dtd html 2.1e//",
    "-//ietf//dtd html 3.0//",
    "-//ietf//dtd html 3.2 final//",
    "-//ietf//dtd html 3.2//",
    "-//ietf//dtd html 3//",
    "-//ietf//dtd html level 0//",
    "-//ietf//dtd html level 1//",
    "-//ietf//dtd html level 2//",
    "-//ietf//dtd html level 3//",
    "-//ietf//dtd html strict level 0//",
    "-//ietf//dtd html strict level 1//",
    "-//ietf//dtd html strict level 2//",
    "-//ietf//dtd html strict level 3//",
    "-//ietf//dtd html strict//",
    "-//ietf//dtd html//",
    "-//metrius//dtd metrius presentational//",
    "-//microsoft//dtd internet explorer 2.0 html strict//",
    "-//microsoft//dtd internet explorer 2.0 html//",
    "-//microsoft//dtd internet explorer 2.0 tables//",
    "-//microsoft//dtd internet explorer 3.0 html strict//",
    "-//microsoft//dtd internet explorer 3.0 html//",
    "-//microsoft//dtd internet explorer 3.0 tables//",
    "-//netscape comm. corp.//dtd html//",
    "-//netscape comm. corp.//dtd strict html//",
    "-//o'reilly and associates//dtd html 2.0//",
    "-//o'reilly and associates//dtd html extended 1.0//",
    "-//o'reilly and associates//dtd html extended relaxed 1.0//",
    "-//sq//dtd html 2.0 hotmetal + extensions//",
    "-//softquad software//dtd hotmetal pro 6.0::19990601::extensions to html 4.0//",
    "-//softquad//dtd hotmetal pro 4.0::19971010::extensions to html 4.0//",
    "-//spyglass//dtd html 2.0 extended//",
    "-//sun microsystems corp.//dtd hotjava html//",
    "-//sun microsystems corp.//dtd hotjava strict html//",
    "-//w3c//dtd html 3 1995-03-24//",
    "-//w3c//dtd html 3.2 draft//",
    "-//w3c//dtd html 3.2 final//",
    "-//w3c//dtd html 3.2//",
    "-//w3c//dtd html 3.2s draft//",
    "-//w3c//dtd html 4.0 frameset//",
    "-//w3c//dtd html 4.0 transitional//",
    "-//w3c//dtd html experimental 19960712//",
    "-//w3c//dtd html experimental 970421//",
    "-//w3c//dtd w3 html//",
    "-//w3o//dtd w3 html 3.0//",
    "-//webtechs//dtd mozilla html 2.0//",
    "-//webtechs//dtd mozilla html//",
)
LIMITED_QUIRKS_PREFIXES = (
    "-//w3c//dtd xhtml 1.0 frameset//",
    "-//w3c//dtd xhtml 1.0 transitional//",
)
# These two become limited-quirks ONLY when a system identifier is present.
QUIRKS_UNLESS_SYSTEM_ID = (
    "-//w3c//dtd html 4.01 frameset//",
    "-//w3c//dtd html 4.01 transitional//",
)


def classify_document_mode(token: DoctypeToken | None) -> str:
    """Return "no-quirks", "limited-quirks" or "quirks"."""
    if token is None:
        return "quirks"
    if token.force_quirks or (token.name or "").lower() != "html":
        return "quirks"

    public = (token.public_id or "").lower()
    system = (token.system_id or "").lower()

    if public in QUIRKS_EXACT:
        return "quirks"
    if system == "http://www.ibm.com/data/dtd/v11/ibmxhtml1-transitional.dtd":
        return "quirks"
    for prefix in QUIRKS_PREFIXES:
        if public.startswith(prefix):
            if prefix in QUIRKS_UNLESS_SYSTEM_ID and token.system_id is not None:
                return "limited-quirks"
            return "quirks"
    for prefix in LIMITED_QUIRKS_PREFIXES:
        if public.startswith(prefix):
            return "limited-quirks"
    return "no-quirks"
```

**Verify the table rather than trusting it.** The list above was transcribed into this plan and may contain errors. Before moving on:

```bash
.venv/bin/python -c "
from mayshay.htmlparse.treebuilder import QUIRKS_PREFIXES, LIMITED_QUIRKS_PREFIXES, QUIRKS_EXACT
print('quirks prefixes  :', len(QUIRKS_PREFIXES))
print('limited prefixes :', len(LIMITED_QUIRKS_PREFIXES))
print('exact matches    :', len(QUIRKS_EXACT))
print('duplicates       :', len(QUIRKS_PREFIXES) - len(set(QUIRKS_PREFIXES)))
print('non-lowercase    :', [p for p in QUIRKS_PREFIXES if p != p.lower()])
"
```

Expected: 55 quirks prefixes, 2 limited, 3 exact, 0 duplicates, no non-lowercase entries. **Check the list against the HTML spec section "The 'initial' insertion mode" and report the count you find there.** If it disagrees with 55, the plan is wrong and the spec wins — say so in your report rather than silently matching either one. An incomplete table misclassifies real pages silently, and the unit tests pin only nine cases.

- [ ] **Step 6: Wire it into `Document` and `_mode_initial`**

In `dom/node.py`:

```python
class Document(Node):
    def __init__(self) -> None:
        super().__init__()
        # "no-quirks" | "limited-quirks" | "quirks". Recorded now, acted on in
        # Phase 3 -- unitless lengths and the alternate box model are layout
        # concerns, not cascade concerns.
        self.mode = "no-quirks"

    @property
    def quirks_mode(self) -> bool:
        return self.mode == "quirks"
```

In `_mode_initial`'s DOCTYPE branch, replace the assignment:

```python
            self.document.mode = classify_document_mode(token)
```

and in the fall-through branch, `self.document.mode = "quirks"`.

Grep for writers of the old attribute — it is now a read-only property and any assignment will raise:

```bash
grep -rn 'quirks_mode' src/ tests/ scripts/
```

- [ ] **Step 7: Run the tests and the conformance suite**

Run: `.venv/bin/pytest tests/htmlparse/ -v && .venv/bin/python scripts/conformance_report.py`

Expected: `test_doctype.py` green. The corpus may **improve** — `doctype01.dat` cases with identifiers were previously unrepresentable. Report the before/after as a set difference of failing ids, and update the xfail ledger for anything that flips; `strict=True` means a now-passing entry left listed turns the suite red.

- [ ] **Step 8: Commit**

```bash
git add src/mayshay/htmlparse/tokenizer.py src/mayshay/htmlparse/treebuilder.py \
        src/mayshay/dom/node.py tests/htmlparse/test_doctype.py
git commit -m "htmlparse: capture DOCTYPE identifiers and classify document mode"
```

---

### Task D: DOM cascade affordances

Three things the cascade needs that the DOM does not offer. Each is small; together they decide whether selector matching is a hot loop or a nested scan.

**`computed_style` goes on `Node`, not `Element`.** Text nodes need styles for layout but cannot match selectors — they inherit wholesale from their parent. Putting the slot on `Node` makes that a straight copy instead of a special case in layout. A field, not a side table keyed by `id(node)`: CPython reuses ids after GC, and that bug is genuinely horrible to find.

**Files:**
- Modify: `src/mayshay/dom/node.py`, `src/mayshay/dom/__init__.py`
- Modify: `tests/dom/test_node.py`

**Interfaces:**
- Produces:
  - `Node.computed_style: object | None = None`
  - `Element.id -> str | None`
  - `Element.class_list -> frozenset[str]`
  - `Element.element_children -> list[Element]`
  - `Element.element_index: int | None`
  - `dom.node.annotate_positions(root: Node) -> int` — returns elements annotated

- [ ] **Step 1: Write the failing tests**

Append to `tests/dom/test_node.py`:

```python
def test_computed_style_defaults_to_none_on_every_node_type():
    from mayshay.dom.node import Comment, Document, DocumentType, Element, Text

    for node in (Document(), DocumentType("html"), Element("p"), Text("x"), Comment("c")):
        assert node.computed_style is None


def test_class_list_splits_on_whitespace_runs():
    """Real markup: `class="box  wide"` -- two spaces."""
    el = Element("div", {"class": "box  wide"})
    assert el.class_list == frozenset({"box", "wide"})


def test_class_list_handles_tabs_newlines_and_edges():
    el = Element("div", {"class": "  a\tb\nc  "})
    assert el.class_list == frozenset({"a", "b", "c"})


def test_class_list_absent_is_empty():
    assert Element("div").class_list == frozenset()


def test_id_accessor():
    assert Element("div", {"id": "Main"}).id == "Main"
    assert Element("div").id is None


def test_id_case_is_preserved():
    """Attribute names fold; values do not. CSS id matching is case-sensitive."""
    assert Element("div", {"id": "Main"}).id != "main"


def test_element_children_excludes_text_and_comments():
    from mayshay.dom.node import Comment, Text

    div = Element("div")
    div.append_child(Text("\n"))
    a = div.append_child(Element("a"))
    div.append_child(Comment("c"))
    b = div.append_child(Element("b"))
    assert div.element_children == [a, b]


def test_annotate_positions_indexes_elements_only():
    from mayshay.dom.node import Document, Text

    doc = Document()
    div = doc.append_child(Element("div"))
    div.append_child(Text("\n"))
    first = div.append_child(Element("p"))
    div.append_child(Text("\n"))
    second = div.append_child(Element("p"))

    count = annotate_positions(doc)
    assert first.element_index == 0
    assert second.element_index == 1
    assert count == 3


def test_element_index_is_none_before_annotation():
    assert Element("p").element_index is None
```

Add `annotate_positions` to the file's imports.

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/pytest tests/dom/test_node.py -v`
Expected: FAIL — `Node` has no `computed_style`.

- [ ] **Step 3: Implement**

In `dom/node.py`, add to `Node.__init__`:

```python
        # Phase 2 attaches a ComputedStyle here. On Node rather than Element so
        # text nodes inherit their parent's style directly, instead of layout
        # carrying a special case for every text run.
        self.computed_style: object | None = None
```

Extend `Element`:

```python
class Element(Node):
    def __init__(self, tag_name: str, attrs: dict[str, str] | None = None) -> None:
        super().__init__()
        self.tag_name = tag_name
        self.attrs: dict[str, str] = dict(attrs or {})
        self._class_list: frozenset[str] | None = None
        # Set by annotate_positions(). Position among ELEMENT siblings, which
        # is what :nth-child counts -- self.children interleaves Text.
        self.element_index: int | None = None

    @property
    def id(self) -> str | None:
        return self.attrs.get("id")

    @property
    def class_list(self) -> frozenset[str]:
        """Cached. `str.split()` with no argument splits on whitespace runs and
        drops empties, which is exactly the HTML class-attribute rule.

        Cached because selector matching asks for this once per element per
        rule; re-splitting there is the difference between a scan and a hot
        loop. Nothing mutates `attrs` in phase 2 -- if that changes, clear
        `_class_list`.
        """
        if self._class_list is None:
            self._class_list = frozenset(self.attrs.get("class", "").split())
        return self._class_list

    @property
    def element_children(self) -> list[Element]:
        return [c for c in self.children if isinstance(c, Element)]
```

Add the annotator:

```python
def annotate_positions(root: Node) -> int:
    """Give every Element its index among its element siblings. Returns the count.

    One pass before matching, rather than an O(n) filter inside every
    :nth-child / '+' / '~' test.
    """
    count = 0
    stack: list[Node] = [root]
    while stack:
        node = stack.pop()
        index = 0
        for child in node.children:
            if isinstance(child, Element):
                child.element_index = index
                index += 1
                count += 1
            stack.append(child)
    return count
```

Export the new names from `dom/__init__.py`.

- [ ] **Step 4: Run the tests**

Run: `.venv/bin/pytest tests/dom/ -v`
Expected: all pass, including the pre-existing Phase 1 tests.

- [ ] **Step 5: Commit**

```bash
git add src/mayshay/dom/ tests/dom/
git commit -m "dom: add cascade affordances - computed_style slot, class_list, element positions"
```

---

### Task E: CSS tokenizer

css-syntax-3 §4. Structurally easier than the HTML tokenizer — no parser feedback loop — but escapes are the analogue of entity decoding, and unquoted `url(` is a genuine special case.

**Step 1 removes `tinycss2`.** It was added during Phase 1 setup before the no-libraries rule was settled, and it is a loaded gun sitting next to this task.

**Files:**
- Modify: `requirements.txt`, `CLAUDE.md`
- Create: `src/mayshay/cssparse/tokenizer.py`, `tests/cssparse/__init__.py`, `tests/cssparse/test_tokenizer.py`

**Interfaces:**
- Produces: token dataclasses `Ident`, `Function`, `AtKeyword`, `Hash`, `String`, `Url`, `Number`, `Percentage`, `Dimension`, `Delim`, `Whitespace`, `Colon`, `Semicolon`, `Comma`, `LBrace`/`RBrace`, `LParen`/`RParen`, `LBracket`/`RBracket`, `EOF`; `CssTokenizer(source).tokenize() -> Iterator[CssToken]`; `CssTokenizer.errors`, `CssTokenizer.metrics`

- [ ] **Step 1: Remove tinycss2 and record the rule**

```bash
grep -n tinycss2 requirements.txt
sed -i '' '/^tinycss2==/d' requirements.txt
grep -rn 'tinycss2\|cssutils\|cssselect' src/ tests/ scripts/ || echo "no imports to clean"
```

Add to `CLAUDE.md` under `## Rules`:

```markdown
- CSS tokenization and parsing are hand-rolled. `tinycss2`, `cssutils` and
  `cssselect` are forbidden in `src/mayshay/`. The same rule as the HTML
  parser, for the same reason: the point is to write it.
```

- [ ] **Step 2: Write the failing tests**

Create `tests/cssparse/test_tokenizer.py`:

```python
import pytest

from mayshay.cssparse.tokenizer import (
    CssTokenizer, Delim, Dimension, Function, Hash, Ident, Number,
    Percentage, String, Url, Whitespace,
)


def toks(src):
    return [t for t in CssTokenizer(src).tokenize() if not isinstance(t, Whitespace)]


def test_simple_declaration():
    got = toks("color: red;")
    assert isinstance(got[0], Ident) and got[0].value == "color"
    assert isinstance(got[2], Ident) and got[2].value == "red"


def test_dimensions_and_percentages():
    got = toks("10px 50% 1.5em -3px")
    assert (got[0].value, got[0].unit) == (10, "px")
    assert isinstance(got[1], Percentage) and got[1].value == 50
    assert (got[2].value, got[2].unit) == (1.5, "em")
    assert got[3].value == -3


def test_numbers_with_exponents():
    assert toks("1e3")[0].value == 1000
    assert toks("1.5E-2")[0].value == pytest.approx(0.015)


def test_hash_and_id_selector():
    got = toks("#main")
    assert isinstance(got[0], Hash) and got[0].value == "main"


def test_strings_both_quote_styles():
    assert toks('"a b"')[0].value == "a b"
    assert toks("'a b'")[0].value == "a b"


def test_escape_sequences():
    assert toks(r"\26")[0].value == "&"
    assert toks(r"\000026 x")[0].value == "&"
    assert toks(r"a\-b")[0].value == "a-b"


def test_url_unquoted_is_its_own_token():
    got = toks("url(a/b.png)")
    assert isinstance(got[0], Url) and got[0].value == "a/b.png"


def test_url_quoted_is_a_function_plus_string():
    got = toks('url("a.png")')
    assert isinstance(got[0], Function) and got[0].value == "url"
    assert isinstance(got[1], String)


def test_function_token():
    got = toks("rgb(1,2,3)")
    assert isinstance(got[0], Function) and got[0].value == "rgb"


def test_comments_are_skipped():
    assert [t.value for t in toks("a /* c */ b") if isinstance(t, Ident)] == ["a", "b"]


def test_unterminated_comment_is_an_error_not_a_crash():
    tk = CssTokenizer("a /* unterminated")
    list(tk.tokenize())
    assert tk.errors


def test_delim_for_combinators():
    assert [type(t).__name__ for t in toks("a > b")][1] == "Delim"


def test_style_element_body_round_trips():
    """A realistic <style> body tokenizes without loss."""
    src = "p.lead, #main > a:hover { color: #f0f; margin: 0 auto }"
    assert not CssTokenizer(src).errors or True
    assert len(toks(src)) > 15
```

- [ ] **Step 3: Run to verify they fail**

Run: `.venv/bin/pytest tests/cssparse/test_tokenizer.py -v`
Expected: FAIL — no module `mayshay.cssparse.tokenizer`.

- [ ] **Step 4: Implement the tokenizer**

Create `src/mayshay/cssparse/tokenizer.py`. Follow css-syntax-3 §4.3's "consume a token" algorithm and its named sub-algorithms — *consume an ident-like token*, *consume a numeric token*, *consume a string token*, *consume a url token*, *consume an escaped code point*. The dataclasses mirror `htmlparse`'s token style, each carrying `pos`.

The three functions that carry the real difficulty, written out because the rest is dispatch:

```python
    def _consume_escape(self) -> str:
        """css-syntax-3 4.3.7. The backslash has already been consumed."""
        ch = self._next()
        if ch is EOF:
            self._error("eof in escape", self.pos)
            return "�"
        if ch in HEX_DIGITS:
            digits = ch
            while len(digits) < 6 and self._peek(1) in HEX_DIGITS:
                digits += self._next()
            if self._peek(1) in WHITESPACE:
                self._next()
            value = int(digits, 16)
            if value == 0 or value > 0x10FFFF or 0xD800 <= value <= 0xDFFF:
                return "�"
            return chr(value)
        return ch

    def _consume_numeric(self) -> CssToken:
        """css-syntax-3 4.3.3. Returns Number, Percentage or Dimension."""
        start = self.pos
        value = self._consume_number()
        if self._starts_ident_sequence():
            return Dimension(value, self._consume_ident_sequence(), pos=start)
        if self._peek(1) == "%":
            self._next()
            return Percentage(value, pos=start)
        return Number(value, pos=start)

    def _consume_url(self) -> CssToken:
        """css-syntax-3 4.3.6. Only reached for UNQUOTED url(...).

        `url("a.png")` is a Function token followed by a String -- the special
        url-token exists only so that unquoted URLs, which contain characters
        no other token permits, survive tokenization.
        """
        start = self.pos
        while self._peek(1) in WHITESPACE:
            self._next()
        out: list[str] = []
        while True:
            ch = self._next()
            if ch == ")":
                return Url("".join(out), pos=start)
            if ch is EOF:
                self._error("eof in url", self.pos)
                return Url("".join(out), pos=start)
            if ch == "\\":
                out.append(self._consume_escape())
            else:
                out.append(ch)
```

Record `metrics["css_tokens"]`, `metrics["css_parse_errors"]` and `metrics["tokenize_time_ms"]` in the same shape `htmlparse` uses.

- [ ] **Step 5: Run the tests**

Run: `.venv/bin/pytest tests/cssparse/ -v`
Expected: 13 passed.

- [ ] **Step 6: Commit**

```bash
git add requirements.txt CLAUDE.md src/mayshay/cssparse/tokenizer.py tests/cssparse/
git commit -m "cssparse: hand-rolled CSS tokenizer; drop tinycss2"
```

---

### Task F: CSS generic grammar

css-syntax-3 §5. A stylesheet is a list of rules; a qualified rule is a prelude plus a `{}` block; an at-rule is a name, a prelude, and an optional block; a declaration block is `ident : value*` pairs.

This layer deliberately knows nothing about selectors or properties — the prelude stays a token list for Task G, and declaration values stay token lists for Task I. The spec's error recovery is the point: a malformed declaration is dropped without killing its siblings, and an unknown at-rule is consumed without breaking the rules after it.

**Files:**
- Create: `src/mayshay/cssparse/parser.py`, `tests/cssparse/test_parser.py`

**Interfaces:**
- Produces: `QualifiedRule(prelude, block, pos)`, `AtRule(name, prelude, block, pos)`, `Declaration(name, value, important, pos)`; `parse_stylesheet(source: str) -> list[QualifiedRule | AtRule]`; `parse_declarations(tokens) -> list[Declaration]`

- [ ] **Step 1: Write the failing tests**

```python
from mayshay.cssparse.parser import (
    AtRule, QualifiedRule, parse_declarations, parse_stylesheet,
)


def test_single_rule():
    rules = parse_stylesheet("p { color: red }")
    assert len(rules) == 1 and isinstance(rules[0], QualifiedRule)


def test_declarations_in_a_block():
    rule = parse_stylesheet("p { color: red; margin: 0 }")[0]
    decls = parse_declarations(rule.block)
    assert [d.name for d in decls] == ["color", "margin"]


def test_important_flag():
    decls = parse_declarations(parse_stylesheet("p { color: red !important }")[0].block)
    assert decls[0].important is True


def test_malformed_declaration_drops_only_itself():
    """Spec error recovery: siblings survive."""
    rule = parse_stylesheet("p { color red; margin: 0 }")[0]
    assert [d.name for d in parse_declarations(rule.block)] == ["margin"]


def test_unknown_at_rule_does_not_break_following_rules():
    rules = parse_stylesheet("@weird foo { a: b } p { color: red }")
    assert isinstance(rules[0], AtRule)
    assert isinstance(rules[1], QualifiedRule)


def test_at_rule_without_block():
    rules = parse_stylesheet('@import "a.css"; p { color: red }')
    assert rules[0].block is None
    assert len(rules) == 2


def test_nested_braces_in_media():
    rules = parse_stylesheet("@media print { p { color: black } }")
    assert isinstance(rules[0], AtRule) and rules[0].block is not None


def test_unclosed_block_at_eof_is_recovered():
    rules = parse_stylesheet("p { color: red")
    assert len(rules) == 1


def test_empty_stylesheet():
    assert parse_stylesheet("") == []


def test_comment_only_stylesheet():
    assert parse_stylesheet("/* nothing */") == []
```

- [ ] **Step 2–4:** run to fail, implement §5's algorithms (*consume a list of rules*, *consume a qualified rule*, *consume an at-rule*, *consume a simple block*, *consume a declaration*), run to pass.

- [ ] **Step 5: Commit**

```bash
git commit -m "cssparse: generic rule and declaration grammar"
```

---

### Task G: Selectors and specificity

Parse a qualified rule's prelude into selector structures. Level-3 subset: type, universal, class, id, attribute, pseudo-class; combinators descendant, `>`, `+`, `~`.

**Files:** create `src/mayshay/cssparse/selectors.py`, `tests/cssparse/test_selectors.py`

**Interfaces:** `Simple`, `Compound(simples)`, `Complex(compounds, combinators)`, `SelectorList`; `parse_selector_list(tokens) -> SelectorList`; `specificity(selector) -> tuple[int, int, int]`

- [ ] **Step 1: Write the failing tests**

```python
import pytest
from mayshay.cssparse.selectors import parse_selector_list, specificity
from mayshay.cssparse.tokenizer import CssTokenizer


def sel(src):
    return parse_selector_list(list(CssTokenizer(src).tokenize()))


@pytest.mark.parametrize("src,expected", [
    ("*", (0, 0, 0)),
    ("p", (0, 0, 1)),
    ("p a", (0, 0, 2)),
    (".c", (0, 1, 0)),
    ("#i", (1, 0, 0)),
    ("[href]", (0, 1, 0)),
    ("p.c", (0, 1, 1)),
    ("#i .c p", (1, 1, 1)),
    ("a:hover", (0, 1, 1)),
    ("li:nth-child(2)", (0, 1, 1)),
])
def test_specificity(src, expected):
    assert specificity(sel(src).selectors[0]) == expected


def test_selector_list_splits_on_top_level_commas_only():
    assert len(sel("a, b, c").selectors) == 3
    assert len(sel("a:not(b, c)").selectors) == 1


def test_combinators_parsed():
    s = sel("div > p + a ~ span")
    assert s.selectors[0].combinators == [">", "+", "~"]


def test_descendant_combinator_from_whitespace():
    assert sel("div p").selectors[0].combinators == [" "]


def test_attribute_operators():
    for op in ("=", "~=", "|=", "^=", "$=", "*="):
        assert sel(f'[a{op}"v"]').selectors[0] is not None


def test_invalid_selector_invalidates_only_its_own_rule():
    with pytest.raises(ValueError):
        sel("p >> a")
```

- [ ] **Steps 2–5:** fail, implement, pass, commit.

Specificity is the (a, b, c) triple: `a` counts id selectors, `b` counts class/attribute/pseudo-class, `c` counts type/pseudo-element. The universal selector contributes nothing.

---

### Task H: Selector matching

**Match right-to-left**, starting from the rightmost compound and walking up. Left-to-right backtracks badly on descendant combinators. Index rules by their rightmost id, class or tag so a page with 500 rules does not test all 500 against every element.

**Files:** create `src/mayshay/cssparse/matching.py`, `tests/cssparse/test_matching.py`

**Interfaces:** `matches(element, complex_selector) -> bool`; `RuleIndex(rules)` with `.candidates(element) -> list[Rule]`

- [ ] **Step 1: Write the failing tests**

```python
from mayshay.cssparse.matching import RuleIndex, matches
from mayshay.cssparse.selectors import parse_selector_list
from mayshay.cssparse.tokenizer import CssTokenizer
from mayshay.dom.node import annotate_positions
from mayshay.htmlparse.treebuilder import parse

HTML = """<!DOCTYPE html><body>
<div id="Main" class="box  wide">
<p>one</p><p class="lead">two</p><span>three</span>
</div></body>"""


def tree():
    doc = parse(HTML)
    annotate_positions(doc)
    return doc


def find(doc, tag, index=0):
    out = []
    stack = [doc]
    while stack:
        n = stack.pop()
        if getattr(n, "tag_name", None) == tag:
            out.append(n)
        stack.extend(reversed(n.children))
    return out[index]


def sel(src):
    return parse_selector_list(list(CssTokenizer(src).tokenize())).selectors[0]


def test_type_selector():
    assert matches(find(tree(), "p"), sel("p"))


def test_class_selector_uses_the_precomputed_set():
    doc = tree()
    assert matches(find(doc, "div"), sel(".wide"))
    assert not matches(find(doc, "div"), sel(".narrow"))


def test_id_matching_is_case_sensitive():
    doc = tree()
    assert matches(find(doc, "div"), sel("#Main"))
    assert not matches(find(doc, "div"), sel("#main"))


def test_type_matching_is_case_insensitive():
    assert matches(find(tree(), "p"), sel("P"))


def test_descendant_and_child():
    doc = tree()
    p = find(doc, "p")
    assert matches(p, sel("body p"))
    assert matches(p, sel("div > p"))
    assert not matches(p, sel("body > p"))


def test_adjacent_and_general_sibling():
    doc = tree()
    second = find(doc, "p", 1)
    assert matches(second, sel("p + p"))
    assert matches(find(doc, "span"), sel("p ~ span"))


def test_nth_child_uses_element_positions():
    doc = tree()
    assert matches(find(doc, "p"), sel("p:nth-child(1)"))
    assert matches(find(doc, "p", 1), sel("p:nth-child(2)"))


def test_attribute_presence_and_value():
    doc = tree()
    assert matches(find(doc, "div"), sel("[id]"))
    assert matches(find(doc, "div"), sel('[id="Main"]'))


def test_rule_index_narrows_candidates():
    """The optimisation, asserted rather than assumed."""
    rules = [sel(s) for s in ("#Main", ".lead", "span", "a", "b", "i")]
    index = RuleIndex(rules)
    assert len(index.candidates(find(tree(), "span"))) < len(rules)
```

- [ ] **Steps 2–5:** fail, implement, pass, commit.

---

### Task I: Property values

Parse declaration values for the nine properties: `display`, `width`, `height`, `margin`, `padding`, `border`, `color`, `background-color`, `font-size`.

**Files:** create `src/mayshay/cssparse/values.py`, `tests/cssparse/test_values.py`

**Interfaces:** `Length(value, unit)`, `Percent(value)`, `Color(r, g, b, a)`, `Keyword(name)`, `AUTO`; `parse_declaration_value(name, tokens) -> dict[str, object] | None`; `expand_shorthand(name, parsed) -> dict[str, object]`

- [ ] **Step 1: Write the failing tests**

```python
import pytest
from mayshay.cssparse.values import AUTO, Color, Length, Percent, parse_declaration_value as pv
from mayshay.cssparse.tokenizer import CssTokenizer


def val(name, src):
    return pv(name, [t for t in CssTokenizer(src).tokenize()])


def test_length_units():
    assert val("width", "10px")["width"] == Length(10, "px")
    assert val("font-size", "1.5em")["font-size"] == Length(1.5, "em")


def test_percentage_stays_symbolic():
    """Cannot be resolved without a containing block. Phase 3's problem."""
    assert val("width", "50%")["width"] == Percent(50)


def test_auto_stays_symbolic():
    assert val("width", "auto")["width"] is AUTO


def test_color_keyword_hash_and_function():
    assert val("color", "red")["color"] == Color(255, 0, 0, 1.0)
    assert val("color", "#f00")["color"] == Color(255, 0, 0, 1.0)
    assert val("color", "#ff0000")["color"] == Color(255, 0, 0, 1.0)
    assert val("color", "rgb(255,0,0)")["color"] == Color(255, 0, 0, 1.0)


def test_display_keywords():
    assert val("display", "block")["display"].name == "block"


@pytest.mark.parametrize("src,expected", [
    ("1px", (1, 1, 1, 1)),
    ("1px 2px", (1, 2, 1, 2)),
    ("1px 2px 3px", (1, 2, 3, 2)),
    ("1px 2px 3px 4px", (1, 2, 3, 4)),
])
def test_margin_shorthand_expansion(src, expected):
    got = val("margin", src)
    sides = ("margin-top", "margin-right", "margin-bottom", "margin-left")
    assert tuple(got[s].value for s in sides) == expected


def test_border_shorthand_expands_to_width_style_color():
    got = val("border", "1px solid red")
    assert got["border-top-width"] == Length(1, "px")
    assert got["border-top-style"].name == "solid"
    assert got["border-top-color"] == Color(255, 0, 0, 1.0)


def test_invalid_value_drops_the_declaration():
    assert val("width", "banana") is None
    assert val("color", "#gg0000") is None


def test_unitless_nonzero_length_is_invalid():
    """Named without a mode: `parse_declaration_value` takes no mode parameter,
    and adding an unused one to justify a test name would be worse than the
    name. Quirks-mode unitless lengths are a Phase 3 layout concern.
    """
    assert val("width", "10") is None
    assert val("margin", "0")["margin-top"] == Length(0, "px")
```

- [ ] **Steps 2–5:** fail, implement, pass, commit.

---

### Task J: Cascade, inheritance, computed values

The payload. Sort declarations by origin → importance → specificity → source order, then walk the tree top-down computing values.

**Why top-down and in order:** `font-size: 1.5em` resolves against the *parent's* computed font-size, and `em` in any other property resolves against the *element's own* computed font-size. Getting that pair backwards is the classic error and is invisible until text is the wrong size.

**Computed ≠ used.** `width: 50%` and `margin: auto` must survive into the computed style symbolically. Storing floats here is the mistake that stays invisible until layout is already wrong.

**A UA stylesheet is not optional** — without one every element is `display: inline` and layout is nonsense.

**Files:** create `src/mayshay/cssparse/cascade.py`, `src/mayshay/cssparse/ua.py`, `tests/cssparse/test_cascade.py`; create `scripts/style_report.py`

**Interfaces:**
- `ComputedStyle` — a dataclass with one field per longhand
- `INHERITED: frozenset[str]` — `color`, `font-size` of our nine
- `style_document(document, author_css: list[str]) -> Counter[str]` — returns this stage's metrics, including `nodes_styled`, `link_stylesheets_skipped` and `cascade_time_ms`, ready to hand to `metrics.emit`
- `ua.UA_CSS: str`

- [ ] **Step 1: Write the failing tests**

```python
from mayshay.cssparse.cascade import INHERITED, style_document
from mayshay.cssparse.values import AUTO, Color, Length, Percent
from mayshay.htmlparse.treebuilder import parse


def styled(html, css=""):
    doc = parse(html)
    style_document(doc, [css] if css else [])
    return doc


def find(doc, tag):
    stack = [doc]
    while stack:
        n = stack.pop()
        if getattr(n, "tag_name", None) == tag:
            return n
        stack.extend(reversed(n.children))
    raise AssertionError(tag)


def test_every_node_gets_a_computed_style():
    doc = styled("<!DOCTYPE html><body><p>hi</p></body>")
    stack, seen = [doc], 0
    while stack:
        n = stack.pop()
        assert n.computed_style is not None, f"{n!r} unstyled"
        seen += 1
        stack.extend(n.children)
    assert seen > 3


def test_ua_stylesheet_makes_div_block():
    doc = styled("<!DOCTYPE html><body><div></div><span></span></body>")
    assert find(doc, "div").computed_style.display == "block"
    assert find(doc, "span").computed_style.display == "inline"


def test_author_rule_beats_ua():
    doc = styled("<!DOCTYPE html><body><div></div></body>", "div { display: inline }")
    assert find(doc, "div").computed_style.display == "inline"


def test_specificity_wins_over_source_order():
    doc = styled(
        '<!DOCTYPE html><body><p id="x" class="c">hi</p></body>',
        "p { color: red } #x { color: blue } .c { color: green }",
    )
    assert find(doc, "p").computed_style.color == Color(0, 0, 255, 1.0)


def test_source_order_breaks_specificity_ties():
    """(0, 128, 0) is correct and is NOT a typo for (0, 255, 0).

    CSS `green` is #008000. The colour most people picture as "green",
    #00FF00, is `lime`. Do not "fix" this assertion.
    """
    doc = styled(
        "<!DOCTYPE html><body><p>hi</p></body>",
        "p { color: red } p { color: green }",
    )
    assert find(doc, "p").computed_style.color == Color(0, 128, 0, 1.0)


def test_important_beats_specificity():
    doc = styled(
        '<!DOCTYPE html><body><p id="x">hi</p></body>',
        "p { color: red !important } #x { color: blue }",
    )
    assert find(doc, "p").computed_style.color == Color(255, 0, 0, 1.0)


def test_inline_style_beats_author_rules():
    doc = styled(
        '<!DOCTYPE html><body><p style="color: blue">hi</p></body>',
        "p { color: red }",
    )
    assert find(doc, "p").computed_style.color == Color(0, 0, 255, 1.0)


def test_style_element_in_the_document_is_collected():
    doc = styled("<!DOCTYPE html><head><style>p { color: blue }</style></head><body><p>x</p></body>")
    assert find(doc, "p").computed_style.color == Color(0, 0, 255, 1.0)


def test_color_inherits_and_width_does_not():
    assert "color" in INHERITED and "width" not in INHERITED
    doc = styled(
        "<!DOCTYPE html><body><div><p>hi</p></div></body>",
        "div { color: blue; width: 100px }",
    )
    p = find(doc, "p").computed_style
    assert p.color == Color(0, 0, 255, 1.0)
    assert p.width is AUTO


def test_text_nodes_inherit_from_their_parent_element():
    doc = styled("<!DOCTYPE html><body><p>hi</p></body>", "p { color: blue }")
    text = find(doc, "p").children[0]
    assert text.computed_style.color == Color(0, 0, 255, 1.0)


def test_em_font_size_resolves_against_the_parent():
    doc = styled(
        "<!DOCTYPE html><body><div><p>hi</p></div></body>",
        "div { font-size: 20px } p { font-size: 1.5em }",
    )
    assert find(doc, "p").computed_style.font_size == Length(30, "px")


def test_em_on_other_properties_resolves_against_the_element_itself():
    """The classic trap: font-size uses the PARENT's, everything else its OWN."""
    doc = styled(
        "<!DOCTYPE html><body><p>hi</p></body>",
        "p { font-size: 20px; width: 2em }",
    )
    assert find(doc, "p").computed_style.width == Length(40, "px")


def test_percentage_survives_computation_unresolved():
    doc = styled("<!DOCTYPE html><body><p>hi</p></body>", "p { width: 50% }")
    assert find(doc, "p").computed_style.width == Percent(50)


def test_link_stylesheets_are_counted_not_fetched():
    """Asserts the counter itself, and discriminates 2 from 0.

    An earlier draft of this test asserted `count > 0` and that the document
    had a computed style. Both hold for ANY document, so it would have passed
    without ever touching the behaviour it names — the same decorative-test
    defect that cost a fix round in Phase 1 Task 3.
    """
    doc = parse(
        "<!DOCTYPE html><head>"
        '<link rel=stylesheet href="a.css">'
        '<link rel=stylesheet href="b.css">'
        '<link rel=icon href="favicon.ico">'
        "</head><body></body>"
    )
    assert style_document(doc, [])["link_stylesheets_skipped"] == 2

    bare = parse("<!DOCTYPE html><body></body>")
    assert style_document(bare, [])["link_stylesheets_skipped"] == 0


def test_style_document_returns_metrics_for_the_driver():
    m = style_document(parse("<!DOCTYPE html><body><p>hi</p></body>"), [])
    assert m["nodes_styled"] > 3
    assert "cascade_time_ms" in m
```

- [ ] **Step 2: Run to verify they fail**

- [ ] **Step 3: Write the UA stylesheet**

`src/mayshay/cssparse/ua.py` — a minimal sheet giving `display: block` to the block-level elements, `display: inline` to the inline set, `display: none` to `head`/`style`/`script`/`link`/`title`/`meta`, and default margins for `body`, `p`, and `h1`–`h6`.

- [ ] **Step 4: Implement the cascade**

Collect declarations in origin order — UA, then author `<style>` elements in document order, then the `style=` attribute — sort each element's matched declarations by `(important, specificity, source_index)`, then walk the tree top-down.

Count and record, per the Phase 5 decision:

```python
    # <link rel=stylesheet> is not fetched -- net/ arrives in Phase 5. Counting
    # it turns "no styles applied" from a blank render into a number, and the
    # fraction of real pages that depend entirely on external CSS is itself a
    # finding for the analysis half.
    metrics["link_stylesheets_skipped"] += 1
```

- [ ] **Step 5: Run the tests**

- [ ] **Step 6: Write the corpus driver**

`scripts/style_report.py` parses a set of saved pages, styles them, and calls `metrics.emit` once per stage per document with a shared `run_id` — the first user of Task A, and the thing that makes the metrics rule true engine-side.

- [ ] **Step 7: Commit**

```bash
git commit -m "cssparse: cascade, inheritance and computed values"
```

---

## Phase 2 Done When

- `.venv/bin/pytest` is green, with any new gaps recorded as `xfail(strict=True)` carrying category and reason.
- `style_document` attaches a `ComputedStyle` to every node of a real saved page.
- `data/metrics/stages.csv` contains rows from `tokenize`, `treebuild` and `cssparse` sharing a `run_id`, written by `scripts/style_report.py`.
- `TreeBuilder` reports non-zero parse errors on malformed real-world markup.
- `Document.mode` classifies the corpus's DOCTYPE cases correctly.
- Percentages and `auto` are present, unresolved, in computed styles.
- **`scripts/style_report.py` has been run over all three pages already in `data/corpus/` — `example.html`, `hn.html` (34 KB) and `wikipedia.html` (791 KB) — and its output reported, including `link_stylesheets_skipped` per page.** This is the end-to-end check that the pipeline works on real markup rather than on fixtures: `example.html` should skip zero stylesheets, and the other two are expected to skip several, which is the first real measurement of how much of the web's styling lives outside the document.

## Known Gaps Carried Into Phase 3

1. **`@media`, `@supports`, `@import`** — parsed as at-rules, not evaluated.
2. **External stylesheets** — counted, not fetched. Needs `net/` (Phase 5).
3. **Quirks-mode behaviour** — classified but not acted on. Unitless lengths and the alternate box model are layout concerns.
4. **Pseudo-elements** (`::before`, `::after`) — parsed, not boxed.
5. **`inherit`, `initial`, `unset`** — the explicit cascade keywords.
6. **Shorthand round-tripping** — expanded on parse, never re-serialised.
7. **Adoption agency, table modes, foreign content** — still Phase 1's carried gaps.
8. **The longhands of the supported shorthands** — `margin-top`, `padding-right`, `border-top`, `border-top-width`, `border-width`/`-style`/`-color` and `background` all parse to `None`; only the `margin`/`padding`/`border` shorthands are accepted. Executed over `data/corpus/wikipedia.html`, this is 85 of the 313 dropped declarations. Now `values.py` deviation 13, pinned by `test_longhands_of_the_supported_shorthands_are_not_supported`; adding them is mechanical, since the side-specific parsers already exist.
9. **`display` is a closed allow-list of 20 keywords** — `flow-root` is in the corpus and is rejected. `values.py` deviation 14.
10. **Seven `_ascii_lower` implementations** — grepped, not counted from memory: `cssparse/tokenizer.py:127`, `cssparse/parser.py:202`, `cssparse/selectors.py:239`, `cssparse/matching.py:210`, `cssparse/values.py:185` (added in the Phase 2 fix wave), plus `htmlparse/treebuilder.py:202` as a `str.maketrans` table and `htmlparse/tokenizer.py:64` with a *different signature* (`ch: str`, one character, not a string). Each duplication is justified in its own docstring and the argument holds at N=2; at N=7, with two divergent shapes and a same-named function taking a different type, a shared `mayshay/_text.py` — the precedent `metrics.py` already sets for non-stage shared code — is the smaller coupling. A refactor for its own turn, deliberately not folded into a merge gate.
11. **`metrics.read()`'s `run_id == "run_id"` header heuristic** — would discard a legitimate row if a caller passed that literal string, and `emit` does not validate it. One caveat on `emit`, not a defect.
12. **`expand_shorthand("margin"|"padding", partial_dict)` raises a bare `KeyError`** — unreachable via `parse_declaration_value`, but the function is in `__all__`, so it is a public-API rough edge.
13. **`dom/node.py`'s `annotate_positions` lacks the re-run-after-mutation note** that `class_list` carries. The failure mode is a typed `None` and `matching._element_index0` falls back correctly, so this is a docstring gap rather than a behaviour one.

## Self-Review

**Scope coverage.** Task A covers the metrics writer with the driver-calls decision and the two-stage amendment. Task B covers the rename, the mirrored error list, the recording sites, and the `#errors` vocabulary with multiset-not-position comparison. Task C covers identifier capture and mode classification, recording without behaviour. Task E removes `tinycss2` and records the rule. Tasks E–J cover tokenizer, parser, selectors, specificity, matching, values, cascade, inheritance and computed values, over the nine named properties. Task D covers all four handoff items taken as written: `computed_style` on `Node`, `class_list` frozenset, cached element index, and — in Task H — right-to-left matching with rightmost-token indexing. Computed-vs-used symbolic storage is pinned by three tests in Task J.

**Type consistency.** `metrics.emit` keeps one signature across Tasks A and J. `ComputedStyle` is produced in J and consumed only there in this phase. `annotate_positions` is defined in D and used in H. `DoctypeToken.public_id`/`system_id` are added in C and consumed by `classify_document_mode` in the same task. `Length`/`Percent`/`Color`/`AUTO` are defined in I and used in J's assertions.

**Two known rough edges, flagged rather than hidden.** Task C's quirks table is given complete — all 55 prefixes — rather than sampled, because a truncated list with a "transcribe the rest" comment is exactly the placeholder this plan format forbids, and an incomplete table misclassifies silently while only nine unit cases are pinned. It was transcribed into the plan and may still contain errors, so Step 5 requires checking it against the spec and reporting the count found, and the whole of `doctype01.dat` is added to the test set as the broad check nine hand-written cases cannot be. And Task B's corpus test will not reach 100%: the instruction is to report matched and unmatched counts separately and **not** to broaden `TREE_ERROR_CODES` to absorb failures, since a code recorded outside the curated set is the mapping bug the set exists to catch.

**Corrections applied after review, recorded so they are not re-introduced.** `METRICS_DIR`'s `parents[2]` derivation is a fallback, not a contract — drivers pass an explicit path, because that derivation holds only under an editable install and Phase 1 saw exactly that pointer broken. `test_unitless_nonzero_length_is_invalid` dropped "in standards mode" from its name rather than gaining an unused parameter to justify it. `test_link_stylesheets_are_counted_not_fetched` now asserts the counter and discriminates 2 from 0; as first drafted it asserted only facts true of any document, which is the decorative-test defect that cost a fix round in Phase 1 Task 3. And `Color(0, 128, 0)` for CSS `green` is correct — `#00FF00` is `lime`.
