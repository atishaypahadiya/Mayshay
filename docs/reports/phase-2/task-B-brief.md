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

