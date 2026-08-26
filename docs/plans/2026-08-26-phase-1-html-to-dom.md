# Phase 1: HTML Source to DOM Tree — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Take mayshay from a token stream to a real DOM tree — decode character references, tokenize script/style/title/textarea content per spec, and build a document tree with an open-elements stack.

**Architecture:** The tokenizer stays a lazy generator but gains a public `switch_to()` seam so the tree builder can drive it into RCDATA/RAWTEXT — this coupling is required by the spec and is not optional. The tree builder is a mode machine implementing 8 of the spec's 23 insertion modes (`initial`, `before_html`, `before_head`, `in_head`, `after_head`, `in_body`, `text`, `after_body`), sitting on an open-elements stack with a general `has_element_in_scope` predicate rather than per-tag special cases. Correctness is measured against the html5lib-tests fixture corpus, vendored as a git submodule.

**Tech Stack:** Python 3.13, pytest, `html.entities.html5` (data table only), html5lib-tests (fixture data only). No parsing libraries.

**Spec:** This plan is the spec. It was derived from a review of `src/mayshay/htmlparse/tokenizer.py` at commit `6d0df52` and the four-piece scope agreed in conversation on 2026-08-26.

## Global Constraints

- No lxml, no `html.parser`, no browser libraries for core parsing. Hand-rolled only.
- `html.entities.html5` is permitted as a **data table** (see Task 4, which amends `CLAUDE.md` to record this). All matching logic is hand-rolled.
- BeautifulSoup only in `scripts/`, never in `src/mayshay/`.
- Every stage emits timing + size metrics to `data/metrics/`.
- Tests in `tests/` mirror `src/mayshay/`. pytest.
- Follow the WHATWG tokenizer state machine where practical; document every deviation in the module docstring.
- Python >= 3.10 (`pyproject.toml`); the dev venv is 3.13.5.

## Execution Order

Commit one is the tokenizer fixes. Then the four pieces run **2 → 1 → 3 → 4** (script states before entities), because entity decoding needs the RCDATA/RAWTEXT distinction to exist before it can know where to decode.

| Task | Deliverable |
|------|-------------|
| 1 | Six tokenizer fixes + source offsets + test scaffolding |
| 2 | html5lib-tests submodule, `.dat` loader, tokenizer JSON loader |
| 3 | ScriptData / RCDATA / RAWTEXT state family (piece 2) |
| 4 | Named character references + `CLAUDE.md` amendment (piece 1) |
| 5 | `src/mayshay/dom/node.py` (piece 3) |
| 6 | Tree builder, 8 insertion modes (piece 4a) |
| 7 | Active formatting elements + reconstruction (piece 4b) |

## File Structure

**Created:**
- `tests/conftest.py` — pytest fixtures, adds fixture-corpus paths
- `tests/support/__init__.py`
- `tests/support/dat.py` — html5lib-tests `.dat` parser and JSON tokenizer-test loader
- `tests/htmlparse/test_tokenizer.py` — unit tests for the tokenizer
- `tests/htmlparse/test_rawtext.py` — script/style/title/textarea state family
- `tests/htmlparse/test_entities.py` — character reference decoding
- `tests/htmlparse/test_treebuilder.py` — tree construction
- `tests/htmlparse/test_html5lib_tree.py` — corpus-driven conformance run
- `tests/dom/test_node.py` — DOM node mechanics and serializer
- `src/mayshay/htmlparse/entities.py` — character reference decoding
- `src/mayshay/htmlparse/treebuilder.py` — tree builder
- `src/mayshay/dom/__init__.py`
- `src/mayshay/dom/node.py` — Node, Document, DocumentType, Element, Text, Comment
- `tests/html5lib-tests/` — git submodule

**Modified:**
- `src/mayshay/htmlparse/tokenizer.py` — fixes, offsets, new state family
- `pyproject.toml` — pytest configuration
- `CLAUDE.md` — record the `html.entities` exception (Task 4)
- `.gitmodules` — created by Task 2

---

### Task 1: Tokenizer fixes, source offsets, test scaffolding

Six confirmed defects plus source offsets, landing as one commit. Fixes 2 and 6 are groundwork that Task 3 builds on; fix 1 is a targeted repair that Task 3 later supersedes when the lookahead hack is deleted entirely.

**Files:**
- Modify: `src/mayshay/htmlparse/tokenizer.py`
- Modify: `pyproject.toml`
- Create: `tests/__init__.py`, `tests/htmlparse/__init__.py`, `tests/htmlparse/test_tokenizer.py`

**Interfaces:**
- Consumes: nothing (first task)
- Produces:
  - Token classes renamed: `DoctypeToken`, `StartTagToken`, `EndTagToken`, `CommentToken`, `CharacterToken`, `EOFToken`. Union stays `Token`.
  - Every token gains `pos: int = -1` (source offset where the token started).
  - `Tokenizer.switch_to(state: str, last_start_tag: str | None = None) -> None`
  - `Tokenizer._last_start_tag: str | None`
  - Module constants `RCDATA_ELEMENTS`, `RAWTEXT_ELEMENTS`, `SCRIPT_ELEMENTS` (all `frozenset[str]`)
  - Helper `_is_ascii_alpha(ch: str | None) -> bool`

- [ ] **Step 1: Add pytest configuration**

Append to `pyproject.toml`:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-q"
```

Create empty `tests/__init__.py` and `tests/htmlparse/__init__.py`.

- [ ] **Step 2: Write the failing tests for all six fixes**

Create `tests/htmlparse/test_tokenizer.py`:

```python
import pytest

from mayshay.htmlparse.tokenizer import (
    CharacterToken,
    EndTagToken,
    StartTagToken,
    Tokenizer,
)


def toks(src):
    return list(Tokenizer(src).tokenize())


def test_end_tag_with_space_exits_rawtext():
    """</script > must return to data state, not swallow the document."""
    result = toks("<script>x</script >after<p>hi</p>")
    assert any(isinstance(t, StartTagToken) and t.name == "p" for t in result)
    text = [t.data for t in result if isinstance(t, CharacterToken)]
    assert "after<p>hi</p>" not in text


def test_rcdata_and_rawtext_element_sets_are_distinct():
    from mayshay.htmlparse.tokenizer import RAWTEXT_ELEMENTS, RCDATA_ELEMENTS

    assert "title" in RCDATA_ELEMENTS
    assert "textarea" in RCDATA_ELEMENTS
    assert "style" in RAWTEXT_ELEMENTS
    assert not RCDATA_ELEMENTS & RAWTEXT_ELEMENTS


def test_non_ascii_after_lt_is_not_a_tag():
    """The spec means ASCII alpha; Python's isalpha() accepts 'é'."""
    result = toks("<élan>text")
    assert not any(isinstance(t, StartTagToken) for t in result)
    assert "".join(t.data for t in result if isinstance(t, CharacterToken)) == "<élan>text"


def test_crlf_is_normalised_to_lf():
    result = toks("a\r\nb\rc")
    assert "".join(t.data for t in result if isinstance(t, CharacterToken)) == "a\nb\nc"


def test_tokens_carry_source_offsets():
    result = toks("ab<p>cd")
    start = next(t for t in result if isinstance(t, StartTagToken))
    assert start.pos == 2
    first_text = next(t for t in result if isinstance(t, CharacterToken))
    assert first_text.pos == 0


def test_switch_to_is_public():
    tk = Tokenizer("<p>")
    tk.switch_to("rcdata", last_start_tag="title")
    assert tk.state == "rcdata"
    assert tk._last_start_tag == "title"
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `.venv/bin/pytest tests/htmlparse/test_tokenizer.py -v`
Expected: all six FAIL — import errors for the renamed tokens and the element-set constants, assertion failures for the rest.

- [ ] **Step 4: Rename the token dataclasses and add `pos`**

In `tokenizer.py`, rename all six classes and add the offset field. Each field carries a default so ordering stays valid:

```python
@dataclass
class DoctypeToken:
    name: str | None = None
    force_quirks: bool = False
    pos: int = -1


@dataclass
class StartTagToken:
    name: str
    attrs: dict[str, str] = field(default_factory=dict)
    self_closing: bool = False
    pos: int = -1


@dataclass
class EndTagToken:
    name: str
    attrs: dict[str, str] = field(default_factory=dict)
    pos: int = -1


@dataclass
class CommentToken:
    data: str = ""
    pos: int = -1


@dataclass
class CharacterToken:
    data: str
    pos: int = -1


@dataclass
class EOFToken:
    pos: int = -1


Token = (
    DoctypeToken | StartTagToken | EndTagToken
    | CommentToken | CharacterToken | EOFToken
)
```

Update the `__main__` block at the bottom of the file to use `CharacterToken`.

- [ ] **Step 5: Normalise CRLF and add the ASCII-alpha helper**

In `Tokenizer.__init__`, replace the `self.source = source` line. Order matters — CRLF first, then lone CR:

```python
        # Spec input preprocessing: normalise CRLF and lone CR to LF.
        self.source = source.replace("\r\n", "\n").replace("\r", "\n")
```

Add at module level, near `WHITESPACE`:

```python
def _is_ascii_alpha(ch: str | None) -> bool:
    """The spec means ASCII alpha. Python's str.isalpha() also accepts 'é'."""
    return ch is not None and ch.isascii() and ch.isalpha()
```

Replace `ch.isalpha()` with `_is_ascii_alpha(ch)` in `_state_tag_open` and `_state_end_tag_open`.

- [ ] **Step 6: Track token start offsets**

Add to `__init__`:

```python
        self._token_start = 0     # offset where the in-progress token began
        self._buffer_start = 0    # offset where the pending text run began
        self._last_start_tag: str | None = None
```

In `_state_data`, record where a text run begins — guard so it only fires on the first buffered character:

```python
        else:
            if not self._buffer:
                self._buffer_start = self.pos - 1
            self._buffer.append(ch)
```

Apply the same `if not self._buffer:` guard everywhere text is appended in `_state_data` and `_state_tag_open`.

In `_flush_text`, pass the offset through:

```python
    def _flush_text(self) -> Iterator[Token]:
        if self._buffer:
            text = "".join(self._buffer)
            self._buffer.clear()
            self.metrics["character_tokens"] += 1
            yield CharacterToken(text, pos=self._buffer_start)
```

In `_start_tag`, record the tag's start (backing up over `<` and any `/`):

```python
    def _start_tag(self, is_end: bool, first_char: str) -> None:
        self._tag_name = [first_char.lower()]
        self._is_end_tag = is_end
        self._self_closing = False
        self._attrs = {}
        self._token_start = self.pos - (3 if is_end else 2)
```

In `_emit_tag`, pass `pos=self._token_start` to both `EndTagToken` and `StartTagToken`.

- [ ] **Step 7: Split the element sets and fix the RAWTEXT state leak**

Add at module level:

```python
# Elements whose content is tokenized as RCDATA: character references ARE
# decoded, but tags are not recognised.
RCDATA_ELEMENTS = frozenset({"title", "textarea"})

# Elements whose content is tokenized as RAWTEXT: neither references nor tags.
RAWTEXT_ELEMENTS = frozenset({"style", "xmp", "iframe", "noembed", "noframes"})

# <script> has its own state family because of the <!-- --> escape rules.
SCRIPT_ELEMENTS = frozenset({"script"})
```

Rewrite `_emit_tag` so the raw-text flag is cleared on **every** emission path, not just the one in `_state_tag_name`. This is the fix for the confirmed `</script >` bug:

```python
    def _emit_tag(self) -> Token:
        self._save_attr()
        name = "".join(self._tag_name)

        if self._is_end_tag:
            # Clear here, not in _state_tag_name: an end tag can also be
            # emitted from after_attribute_name (`</script >`), and missing
            # those paths leaves the tokenizer stuck in RAWTEXT forever.
            if name == self._rawtext_tag:
                self._rawtext_tag = None
            self.metrics["end_tags"] += 1
            return EndTagToken(name, self._attrs, pos=self._token_start)

        self._last_start_tag = name
        if name in RCDATA_ELEMENTS | RAWTEXT_ELEMENTS | SCRIPT_ELEMENTS:
            self._rawtext_tag = name
        self.metrics["start_tags"] += 1
        return StartTagToken(
            name, self._attrs, self._self_closing, pos=self._token_start
        )
```

Delete the now-redundant clearing block in `_state_tag_name` (the `if self._is_end_tag and ... == self._rawtext_tag` lines).

- [ ] **Step 8: Add the public state-switch API**

Add a method on `Tokenizer`:

```python
    def switch_to(self, state: str, last_start_tag: str | None = None) -> None:
        """
        Let the tree builder drive the tokenizer.

        The spec puts the RCDATA/RAWTEXT decision in the tree builder, not the
        tokenizer, because it is contextual. Task 6 uses this when it inserts
        a <title>, <style>, <script> or <textarea> element.
        """
        self.state = state
        if last_start_tag is not None:
            self._last_start_tag = last_start_tag
```

- [ ] **Step 9: Run the tests to verify they pass**

Run: `.venv/bin/pytest tests/htmlparse/test_tokenizer.py -v`
Expected: 6 passed.

- [ ] **Step 10: Commit**

```bash
git add pyproject.toml src/mayshay/htmlparse/tokenizer.py tests/
git commit -m "htmlparse: fix rawtext state leak, ascii-alpha, crlf; add token offsets"
```

---

### Task 2: html5lib-tests submodule and fixture loaders

Vendors the conformance corpus and gives later tasks a way to read it. The `.dat` files drive tree construction (Tasks 6–7); the `tokenizer/*.test` JSON files drive Tasks 3–4.

**Files:**
- Create: `tests/html5lib-tests/` (submodule), `.gitmodules`
- Create: `tests/support/__init__.py`, `tests/support/dat.py`, `tests/conftest.py`
- Create: `tests/support/test_dat.py`

**Interfaces:**
- Consumes: nothing from Task 1
- Produces:
  - `DatTest` dataclass with fields `data: str`, `errors: list[str]`, `document: str`, `fragment: str | None`, `script: str | None`, `path: str`, `index: int`, and property `id: str`
  - `parse_dat(text: str, path: str = "") -> list[DatTest]`
  - `load_tree_tests(*filenames: str) -> list[DatTest]` — no args means every `.dat` file
  - `load_tokenizer_tests(*filenames: str) -> list[TokenizerTest]`
  - `TokenizerTest` dataclass: `description: str`, `input: str`, `output: list`, `initial_states: list[str]`, `last_start_tag: str | None`

- [ ] **Step 1: Add the submodule**

```bash
git submodule add https://github.com/html5lib/html5lib-tests.git tests/html5lib-tests
git submodule update --init --recursive
```

Verify the corpus landed:

```bash
ls tests/html5lib-tests/tree-construction/*.dat | head
ls tests/html5lib-tests/tokenizer/*.test | head
```

Expected: `tests1.dat` … `tests26.dat`, `adoption01.dat`, `entities01.dat`, `tables01.dat`, etc.; and `test1.test`, `entities.test`, `namedEntities.test`, etc.

- [ ] **Step 2: Write the failing loader test**

Create `tests/support/__init__.py` (empty) and `tests/support/test_dat.py`:

```python
from tests.support.dat import load_tree_tests, parse_dat

SAMPLE = '''#data
<p>Hello
#errors
(1,3): expected-doctype-but-got-start-tag
#document
| <html>
|   <head>
|   <body>
|     <p>
|       "Hello"

#data
<b><i></b></i>
#errors
#document
| <html>
|   <head>
|   <body>
|     <b>
|       <i>
'''


def test_parses_two_tests():
    tests = parse_dat(SAMPLE, path="sample.dat")
    assert len(tests) == 2


def test_data_section_has_no_trailing_newline():
    tests = parse_dat(SAMPLE, path="sample.dat")
    assert tests[0].data == "<p>Hello"
    assert tests[1].data == "<b><i></b></i>"


def test_document_section_preserved_verbatim():
    tests = parse_dat(SAMPLE, path="sample.dat")
    assert tests[0].document.splitlines()[0] == "| <html>"
    assert tests[0].document.splitlines()[-1] == '|       "Hello"'


def test_errors_captured():
    tests = parse_dat(SAMPLE, path="sample.dat")
    assert len(tests[0].errors) == 1
    assert tests[1].errors == []


def test_test_id_is_stable():
    tests = parse_dat(SAMPLE, path="sample.dat")
    assert tests[0].id == "sample.dat:0"


def test_real_corpus_loads():
    tests = load_tree_tests("tests1.dat")
    assert len(tests) > 50
    assert all(t.document for t in tests)
```

- [ ] **Step 3: Run to verify it fails**

Run: `.venv/bin/pytest tests/support/test_dat.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'tests.support.dat'`

- [ ] **Step 4: Implement the loaders**

Create `tests/support/dat.py`:

```python
"""
Readers for the html5lib-tests corpus (vendored as a git submodule).

The .dat format is a sequence of tests separated by a blank line, each made
of #-prefixed sections:

    #data
    <p>Hello
    #errors
    (1,3): expected-doctype-but-got-start-tag
    #document
    | <html>
    |   <head>
    |   <body>
    |     <p>
    |       "Hello"

Only #data and #document are required for our purposes.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "html5lib-tests"
TREE_DIR = ROOT / "tree-construction"
TOKENIZER_DIR = ROOT / "tokenizer"

_HEADERS = (
    "#data",
    "#errors",
    "#new-errors",
    "#document-fragment",
    "#document",
    "#script-off",
    "#script-on",
)


@dataclass
class DatTest:
    data: str
    errors: list[str] = field(default_factory=list)
    document: str = ""
    fragment: str | None = None
    script: str | None = None
    path: str = ""
    index: int = 0

    @property
    def id(self) -> str:
        return f"{Path(self.path).name}:{self.index}"


def _split_sections(chunk: str) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {"data": []}
    current = "data"
    for line in chunk.split("\n"):
        if line in _HEADERS:
            current = line[1:]
            sections.setdefault(current, [])
        else:
            sections[current].append(line)
    return sections


def parse_dat(text: str, path: str = "") -> list[DatTest]:
    # Tests are separated by a blank line immediately followed by "#data".
    chunks = text.split("\n\n#data\n")
    if chunks and chunks[0].startswith("#data\n"):
        chunks[0] = chunks[0][len("#data\n") :]

    tests: list[DatTest] = []
    for index, chunk in enumerate(chunks):
        if not chunk.strip():
            continue
        sections = _split_sections(chunk)
        document = sections.get("document", [])
        # Drop trailing blank lines left by the separator.
        while document and not document[-1]:
            document.pop()
        script = None
        if "script-off" in sections:
            script = "off"
        elif "script-on" in sections:
            script = "on"
        fragment = sections.get("document-fragment")
        tests.append(
            DatTest(
                data="\n".join(sections["data"]),
                errors=[e for e in sections.get("errors", []) if e],
                document="\n".join(document),
                fragment="\n".join(fragment).strip() if fragment else None,
                script=script,
                path=path,
                index=index,
            )
        )
    return tests


def load_tree_tests(*filenames: str) -> list[DatTest]:
    paths = (
        [TREE_DIR / name for name in filenames]
        if filenames
        else sorted(TREE_DIR.glob("*.dat"))
    )
    tests: list[DatTest] = []
    for p in paths:
        tests.extend(parse_dat(p.read_text(encoding="utf-8"), path=str(p)))
    return tests


@dataclass
class TokenizerTest:
    description: str
    input: str
    output: list
    initial_states: list[str] = field(default_factory=lambda: ["Data state"])
    last_start_tag: str | None = None


def load_tokenizer_tests(*filenames: str) -> list[TokenizerTest]:
    paths = (
        [TOKENIZER_DIR / name for name in filenames]
        if filenames
        else sorted(TOKENIZER_DIR.glob("*.test"))
    )
    tests: list[TokenizerTest] = []
    for p in paths:
        blob = json.loads(p.read_text(encoding="utf-8"))
        for entry in blob.get("tests", []):
            if entry.get("doubleEscaped"):
                continue  # escaped-string form; skip until Task 3 handles it
            tests.append(
                TokenizerTest(
                    description=entry["description"],
                    input=entry["input"],
                    output=entry["output"],
                    initial_states=entry.get("initialStates", ["Data state"]),
                    last_start_tag=entry.get("lastStartTag"),
                )
            )
    return tests
```

- [ ] **Step 5: Add a conftest that skips cleanly when the submodule is absent**

Create `tests/conftest.py`:

```python
import pytest

from tests.support.dat import ROOT

requires_corpus = pytest.mark.skipif(
    not (ROOT / "tree-construction").is_dir(),
    reason="html5lib-tests submodule not checked out; run "
    "`git submodule update --init`",
)
```

- [ ] **Step 6: Run to verify it passes**

Run: `.venv/bin/pytest tests/support/test_dat.py -v`
Expected: 6 passed.

- [ ] **Step 7: Commit**

```bash
git add .gitmodules tests/html5lib-tests tests/support tests/conftest.py
git commit -m "tests: vendor html5lib-tests, add .dat and tokenizer fixture loaders"
```

---

### Task 3: ScriptData / RCDATA / RAWTEXT state family (piece 2)

Deletes the lookahead hack in `_state_data` and replaces `_rawtext_tag` with the spec's real mechanism: the **appropriate end tag**. An end tag inside raw text only counts if its name matches the last start tag emitted; otherwise `</` plus what was accumulated is emitted as text and scanning resumes.

The three families are structurally identical, so they share one parameterised implementation rather than 26 near-duplicate methods.

**Files:**
- Modify: `src/mayshay/htmlparse/tokenizer.py`
- Create: `tests/htmlparse/test_rawtext.py`

**Interfaces:**
- Consumes: `RCDATA_ELEMENTS`, `RAWTEXT_ELEMENTS`, `SCRIPT_ELEMENTS`, `_last_start_tag`, `switch_to`, `_is_ascii_alpha` (Task 1)
- Produces:
  - States `rcdata`, `rawtext`, `script_data`, plus their `_less_than_sign`, `_end_tag_open`, `_end_tag_name` variants
  - Script escape states: `script_data_escape_start`, `script_data_escape_start_dash`, `script_data_escaped`, `script_data_escaped_dash`, `script_data_escaped_dash_dash`, `script_data_escaped_less_than_sign`, `script_data_escaped_end_tag_open`, `script_data_escaped_end_tag_name`
  - `Tokenizer._temp_buffer: list[str]`
  - `Tokenizer._is_appropriate_end_tag() -> bool`
  - `_rawtext_tag` is **removed**

- [ ] **Step 1: Write the failing tests**

Create `tests/htmlparse/test_rawtext.py`:

```python
import pytest

from mayshay.htmlparse.tokenizer import (
    CharacterToken,
    EndTagToken,
    StartTagToken,
    Tokenizer,
)


def text_of(src):
    return "".join(
        t.data for t in Tokenizer(src).tokenize() if isinstance(t, CharacterToken)
    )


def names(src):
    return [
        t.name
        for t in Tokenizer(src).tokenize()
        if isinstance(t, (StartTagToken, EndTagToken))
    ]


def pairs(src):
    """Full token sequence including ordering.

    text_of() and names() both aggregate and would happily pass while the
    tokenizer emitted a closing tag *before* the text it encloses. These
    assertions pin the order.
    """
    out = []
    for t in Tokenizer(src).tokenize():
        if isinstance(t, CharacterToken):
            out.append(("text", t.data))
        elif isinstance(t, StartTagToken):
            out.append(("start", t.name))
        elif isinstance(t, EndTagToken):
            out.append(("end", t.name))
    return out


def test_text_emitted_before_closing_tag():
    """Covers the '>' appropriate-end-tag branch."""
    assert pairs("<script>x</script>") == [
        ("start", "script"), ("text", "x"), ("end", "script"),
    ]


def test_text_emitted_before_spaced_closing_tag():
    """Covers the whitespace appropriate-end-tag branch."""
    assert pairs("<script>x</script >y") == [
        ("start", "script"), ("text", "x"), ("end", "script"), ("text", "y"),
    ]


def test_text_emitted_before_self_closing_end_tag():
    """Covers the '/' appropriate-end-tag branch."""
    assert pairs("<script>x</script/>") == [
        ("start", "script"), ("text", "x"), ("end", "script"),
    ]


def test_less_than_inside_script_is_text():
    assert text_of("<script>if (a<b) {}</script>") == "if (a<b) {}"


def test_close_tag_string_inside_script_is_text():
    assert text_of('<script>var s = "</div>";</script>') == 'var s = "</div>";'


def test_partial_end_tag_is_text():
    assert text_of("<script>x</scr ipt>y</script>") == "x</scr ipt>y"


def test_end_tag_is_case_insensitive():
    assert names("<script>x</SCRIPT>") == ["script", "script"]


def test_end_tag_with_trailing_space_exits():
    assert names("<script>x</script >p") == ["script", "script"]
    assert text_of("<script>x</script >p") == "xp"


def test_self_closing_solidus_on_end_tag_exits():
    assert names("<script>x</script/>") == ["script", "script"]


def test_style_rawtext():
    assert text_of('<style>a { content: "<b>" }</style>') == 'a { content: "<b>" }'


def test_textarea_content_is_not_tags():
    assert names("<textarea><b>x</b></textarea>") == ["textarea", "textarea"]
    assert text_of("<textarea><b>x</b></textarea>") == "<b>x</b>"


def test_script_comment_escape_states():
    assert text_of("<script><!-- <b> --></script>") == "<!-- <b> -->"


def test_eof_inside_script_emits_text_and_error():
    tk = Tokenizer("<script>abc")
    out = list(tk.tokenize())
    assert "".join(t.data for t in out if isinstance(t, CharacterToken)) == "abc"
    assert tk.errors


def test_returns_to_data_between_scripts():
    assert names("<script>a</script><p>b</p><script>c</script>") == [
        "script", "script", "p", "p", "script", "script",
    ]


@pytest.mark.xfail(reason="double-escaped script states deferred; see Task 3 notes")
def test_double_escaped_script():
    src = "<script><!--<script>foo</script>--></script>"
    assert text_of(src) == "<!--<script>foo</script>-->"
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/pytest tests/htmlparse/test_rawtext.py -v`
Expected: several FAIL (notably `test_partial_end_tag_is_text`, `test_script_comment_escape_states`, and all three `test_text_emitted_before_*` ordering tests); the xfail is reported as `xfail`.

- [ ] **Step 3: Strip the lookahead hack out of `_state_data`**

Replace `_state_data` entirely. It becomes plain spec — no raw-text awareness at all:

```python
    def _state_data(self) -> Iterator[Token]:
        ch = self._next()
        if ch is EOF:
            self.state = "eof"
        elif ch == "<":
            yield from self._flush_text()
            self.state = "tag_open"
        else:
            if not self._buffer:
                self._buffer_start = self.pos - 1
            self._buffer.append(ch)
```

Remove the `_rawtext_tag` attribute from `__init__` and the assignment in `_emit_tag`. Add in its place:

```python
        self._temp_buffer: list[str] = []
```

- [ ] **Step 4: Add the appropriate-end-tag helper and shared state bodies**

Add to `Tokenizer`:

```python
    def _is_appropriate_end_tag(self) -> bool:
        """An end tag in raw text only counts if it matches the last start tag."""
        return "".join(self._tag_name) == self._last_start_tag

    def _raw_text_state(self, name: str) -> Iterator[Token]:
        """Shared body for the rcdata / rawtext / script_data states."""
        ch = self._next()
        if ch is EOF:
            self._error(f"eof in {name}")
            self.state = "eof"
        elif ch == "<":
            self._temp_buffer = []
            self.state = f"{name}_less_than_sign"
        else:
            # No special case for '-' here. A dash in script data is ordinary
            # text; the escaped family is entered via '<!' in
            # _raw_less_than_sign_state, and the dash counting happens in
            # script_data_escape_start / _escape_start_dash.
            if not self._buffer:
                self._buffer_start = self.pos - 1
            self._buffer.append(ch)
        return
        yield

    def _raw_less_than_sign_state(self, name: str) -> Iterator[Token]:
        ch = self._next()
        if ch == "/":
            self._temp_buffer = []
            self.state = f"{name}_end_tag_open"
        elif name == "script_data" and ch == "!":
            self._buffer.append("<!")
            self.state = "script_data_escape_start"
        else:
            self._buffer.append("<")
            if ch is not EOF:
                self.pos -= 1
            self.state = name
        return
        yield

    def _raw_end_tag_open_state(self, name: str) -> Iterator[Token]:
        ch = self._next()
        if _is_ascii_alpha(ch):
            self._start_tag(is_end=True, first_char=ch)
            self._temp_buffer = [ch]
            self.state = f"{name}_end_tag_name"
        else:
            self._buffer.append("</")
            if ch is not EOF:
                self.pos -= 1
            self.state = name
        return
        yield

    def _raw_end_tag_name_state(self, name: str) -> Iterator[Token]:
        ch = self._next()
        # Each appropriate-end-tag branch MUST flush pending raw text first.
        # The buffer still holds the element's content at this point, and the
        # tag token is about to be emitted (here for '>', or shortly after via
        # before_attribute_name / self_closing_start_tag). Without the flush
        # the text token surfaces *after* its own closing tag.
        if ch in WHITESPACE and self._is_appropriate_end_tag():
            yield from self._flush_text()
            self.state = "before_attribute_name"
        elif ch == "/" and self._is_appropriate_end_tag():
            yield from self._flush_text()
            self.state = "self_closing_start_tag"
        elif ch == ">" and self._is_appropriate_end_tag():
            yield from self._flush_text()
            self.state = "data"
            yield self._emit_tag()
        elif _is_ascii_alpha(ch):
            self._tag_name.append(ch.lower())
            self._temp_buffer.append(ch)
        else:
            # Not the appropriate end tag: everything consumed becomes text.
            if not self._buffer:
                self._buffer_start = self.pos - len(self._temp_buffer) - 2
            self._buffer.append("</")
            self._buffer.extend(self._temp_buffer)
            if ch is not EOF:
                self.pos -= 1
            self.state = name
```

- [ ] **Step 5: Wire up the three families as thin wrappers**

The dispatcher in `tokenize()` looks up `_state_<name>`, so each state needs a real method:

```python
    def _state_rcdata(self): return self._raw_text_state("rcdata")
    def _state_rcdata_less_than_sign(self): return self._raw_less_than_sign_state("rcdata")
    def _state_rcdata_end_tag_open(self): return self._raw_end_tag_open_state("rcdata")
    def _state_rcdata_end_tag_name(self): return self._raw_end_tag_name_state("rcdata")

    def _state_rawtext(self): return self._raw_text_state("rawtext")
    def _state_rawtext_less_than_sign(self): return self._raw_less_than_sign_state("rawtext")
    def _state_rawtext_end_tag_open(self): return self._raw_end_tag_open_state("rawtext")
    def _state_rawtext_end_tag_name(self): return self._raw_end_tag_name_state("rawtext")

    def _state_script_data(self): return self._raw_text_state("script_data")
    def _state_script_data_less_than_sign(self): return self._raw_less_than_sign_state("script_data")
    def _state_script_data_end_tag_open(self): return self._raw_end_tag_open_state("script_data")
    def _state_script_data_end_tag_name(self): return self._raw_end_tag_name_state("script_data")
```

- [ ] **Step 6: Add the script escape states**

```python
    def _state_script_data_escape_start(self) -> Iterator[Token]:
        ch = self._next()
        if ch == "-":
            self._buffer.append("-")
            self.state = "script_data_escape_start_dash"
        else:
            if ch is not EOF:
                self.pos -= 1
            self.state = "script_data"
        return
        yield

    def _state_script_data_escape_start_dash(self) -> Iterator[Token]:
        ch = self._next()
        if ch == "-":
            self._buffer.append("-")
            self.state = "script_data_escaped_dash_dash"
        else:
            if ch is not EOF:
                self.pos -= 1
            self.state = "script_data"
        return
        yield

    def _state_script_data_escaped(self) -> Iterator[Token]:
        ch = self._next()
        if ch is EOF:
            self._error("eof in script comment")
            self.state = "eof"
        elif ch == "-":
            self._buffer.append("-")
            self.state = "script_data_escaped_dash"
        elif ch == "<":
            self.state = "script_data_escaped_less_than_sign"
        else:
            self._buffer.append(ch)
        return
        yield

    def _state_script_data_escaped_dash(self) -> Iterator[Token]:
        ch = self._next()
        if ch is EOF:
            self._error("eof in script comment")
            self.state = "eof"
        elif ch == "-":
            self._buffer.append("-")
            self.state = "script_data_escaped_dash_dash"
        elif ch == "<":
            self.state = "script_data_escaped_less_than_sign"
        else:
            self._buffer.append(ch)
            self.state = "script_data_escaped"
        return
        yield

    def _state_script_data_escaped_dash_dash(self) -> Iterator[Token]:
        ch = self._next()
        if ch is EOF:
            self._error("eof in script comment")
            self.state = "eof"
        elif ch == "-":
            self._buffer.append("-")
        elif ch == "<":
            self.state = "script_data_escaped_less_than_sign"
        elif ch == ">":
            self._buffer.append(">")
            self.state = "script_data"
        else:
            self._buffer.append(ch)
            self.state = "script_data_escaped"
        return
        yield

    def _state_script_data_escaped_less_than_sign(self) -> Iterator[Token]:
        ch = self._next()
        if ch == "/":
            self._temp_buffer = []
            self.state = "script_data_escaped_end_tag_open"
        else:
            self._buffer.append("<")
            if ch is not EOF:
                self.pos -= 1
            self.state = "script_data_escaped"
        return
        yield

    def _state_script_data_escaped_end_tag_open(self):
        return self._raw_end_tag_open_state("script_data_escaped")

    def _state_script_data_escaped_end_tag_name(self):
        return self._raw_end_tag_name_state("script_data_escaped")
```

Note the escape-start transition lives in `_raw_less_than_sign_state` (Step 4) via the `ch == "!"` branch.

- [ ] **Step 7: Have `_emit_tag` choose the right state on a start tag**

Replace the `if name in RCDATA_ELEMENTS | ...` block written in Task 1 Step 7 with a real state transition:

```python
        self._last_start_tag = name
        if name in RCDATA_ELEMENTS:
            self.state = "rcdata"
        elif name in RAWTEXT_ELEMENTS:
            self.state = "rawtext"
        elif name in SCRIPT_ELEMENTS:
            self.state = "script_data"
```

Because `_emit_tag` is called before the calling state assigns `self.state = "data"`, reorder those call sites: in each of `_state_tag_name`, `_state_after_attribute_name`, `_state_before_attribute_value`, `_state_attribute_value_unquoted`, `_state_after_attribute_value_quoted`, and `_state_self_closing_start_tag`, change

```python
            token = self._emit_tag()
            self.state = "data"
            yield token
```

to

```python
            self.state = "data"
            token = self._emit_tag()   # may override state to rcdata/rawtext/script_data
            yield token
```

- [ ] **Step 8: Run the tests to verify they pass**

Run: `.venv/bin/pytest tests/htmlparse/test_rawtext.py tests/htmlparse/test_tokenizer.py -v`
Expected: 20 passed, 1 xfailed (14 in `test_rawtext.py`, 6 in `test_tokenizer.py`). Task 1's `test_end_tag_with_space_exits_rawtext` must still pass.

- [ ] **Step 9: Commit**

```bash
git add src/mayshay/htmlparse/tokenizer.py tests/htmlparse/test_rawtext.py
git commit -m "htmlparse: replace rawtext lookahead with spec script/rcdata state family"
```

---

### Task 4: Named character references (piece 1)

Decoding runs in exactly three places: the data state, the RCDATA state, and the three attribute-value states. Never in RAWTEXT, script data, or comments.

Two rules carry most of the difficulty. **Longest match** — `&notin;` is `∉` but `&notit;` is `¬it;`, because `not` matches without a semicolon. **The legacy attribute rule** — a semicolon-less match inside an attribute followed by `=` or an ASCII alphanumeric does not decode, which is what keeps `?a&copy=1` working.

**Files:**
- Create: `src/mayshay/htmlparse/entities.py`
- Modify: `src/mayshay/htmlparse/tokenizer.py`
- Modify: `CLAUDE.md`
- Create: `tests/htmlparse/test_entities.py`

**Interfaces:**
- Consumes: `Tokenizer._next`, `_peek`, `_error`, `pos`, `source` (Task 1); RCDATA state (Task 3)
- Produces:
  - `entities.decode_reference(source: str, start: int, in_attribute: bool) -> tuple[str, int, str | None]` — returns `(replacement_text, new_offset, error_or_none)`. `start` is the offset **just past** the `&`.
  - `entities.NAMED_REFS: dict[str, str]`, `entities.MAX_REF_LEN: int`
  - `Tokenizer._consume_character_reference(in_attribute: bool) -> str`

- [ ] **Step 1: Write the failing tests**

Create `tests/htmlparse/test_entities.py`:

```python
import pytest

from mayshay.htmlparse.tokenizer import CharacterToken, Tokenizer


def text_of(src):
    return "".join(
        t.data for t in Tokenizer(src).tokenize() if isinstance(t, CharacterToken)
    )


def attr_of(src, name="href"):
    from mayshay.htmlparse.tokenizer import StartTagToken

    tag = next(t for t in Tokenizer(src).tokenize() if isinstance(t, StartTagToken))
    return tag.attrs[name]


@pytest.mark.parametrize(
    "src,expected",
    [
        ("&amp;", "&"),
        ("&AMP;", "&"),
        ("&nbsp;", " "),
        ("&notin;", "∉"),
        ("&notit;", "¬it;"),   # longest match: 'not' wins, 'in' does not
        ("&acE;", "∾̳"),  # multi-codepoint replacement
        ("&#65;", "A"),
        ("&#x41;", "A"),
        ("&#X41;", "A"),
        ("&#x80;", "€"),       # windows-1252 remap
        ("&#0;", "�"),
        ("&#xD800;", "�"),
        ("&#x110000;", "�"),
        ("&#38;#38;", "&#38;"),     # decode once, not twice
        ("&", "&"),
        ("& ", "& "),
        ("&amp", "&"),              # missing semicolon, still decodes in text
    ],
)
def test_decoding(src, expected):
    assert text_of(src) == expected


def test_missing_semicolon_is_a_parse_error():
    tk = Tokenizer("&amp")
    list(tk.tokenize())
    assert tk.errors


def test_legacy_attribute_rule_blocks_decoding():
    assert attr_of('<a href="?a&copy=1">') == "?a&copy=1"


def test_semicolon_in_attribute_still_decodes():
    assert attr_of('<a href="?a&copy;=1">') == "?a©=1"


def test_attribute_followed_by_space_decodes():
    assert attr_of('<a href="?a&copy x">') == "?a© x"


def test_not_decoded_in_rawtext():
    assert text_of("<script>&amp;</script>") == "&amp;"


def test_decoded_in_rcdata():
    assert text_of("<title>a &amp; b</title>") == "a & b"


def test_not_decoded_in_comment():
    from mayshay.htmlparse.tokenizer import CommentToken

    c = next(
        t for t in Tokenizer("<!-- &amp; -->").tokenize()
        if isinstance(t, CommentToken)
    )
    assert c.data == " &amp; "
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/pytest tests/htmlparse/test_entities.py -v`
Expected: most FAIL — text passes through raw today.

- [ ] **Step 3: Implement the decoder**

Create `src/mayshay/htmlparse/entities.py`:

```python
"""
Character reference decoding.

The named reference table is `html.entities.html5` from the standard library:
2231 entries, 106 of which have no trailing semicolon, longest key 32 chars.
That module is a data table (the WHATWG named character reference list), not
a parser — the longest-match and legacy-semicolon rules below are hand-rolled.
See the CLAUDE.md rules section.
"""

from __future__ import annotations

from html.entities import html5 as NAMED_REFS

MAX_REF_LEN = max(len(k) for k in NAMED_REFS)  # 32

# Numeric references in this range are remapped to Windows-1252, because a
# generation of authors emitted cp1252 bytes and called them code points.
C1_REPLACEMENTS = {
    0x80: "€", 0x82: "‚", 0x83: "ƒ", 0x84: "„",
    0x85: "…", 0x86: "†", 0x87: "‡", 0x88: "ˆ",
    0x89: "‰", 0x8A: "Š", 0x8B: "‹", 0x8C: "Œ",
    0x8E: "Ž", 0x91: "‘", 0x92: "’", 0x93: "“",
    0x94: "”", 0x95: "•", 0x96: "–", 0x97: "—",
    0x98: "˜", 0x99: "™", 0x9A: "š", 0x9B: "›",
    0x9C: "œ", 0x9E: "ž", 0x9F: "Ÿ",
}

REPLACEMENT = "�"


def _decode_numeric(source: str, start: int) -> tuple[str, int, str | None]:
    i = start + 1  # skip '#'
    hex_mode = i < len(source) and source[i] in "xX"
    if hex_mode:
        i += 1
    digits_start = i
    allowed = "0123456789abcdefABCDEF" if hex_mode else "0123456789"
    while i < len(source) and source[i] in allowed:
        i += 1
    if i == digits_start:
        return "&", start, "absence of digits in numeric character reference"

    value = int(source[digits_start:i], 16 if hex_mode else 10)
    error = None
    if i < len(source) and source[i] == ";":
        i += 1
    else:
        error = "missing semicolon after character reference"

    if value in C1_REPLACEMENTS:
        return C1_REPLACEMENTS[value], i, "control character reference"
    if value == 0 or value > 0x10FFFF or 0xD800 <= value <= 0xDFFF:
        return REPLACEMENT, i, "invalid numeric character reference"
    return chr(value), i, error


def decode_reference(
    source: str, start: int, in_attribute: bool
) -> tuple[str, int, str | None]:
    """
    Decode the reference beginning at `start`, which is the offset just past
    the '&'. Returns (replacement, new_offset, error_message_or_None).

    If nothing matches, returns ("&", start, ...) — the caller emits a literal
    ampersand and carries on from where it was.
    """
    if start >= len(source):
        return "&", start, None
    if source[start] == "#":
        return _decode_numeric(source, start)

    window = source[start : start + MAX_REF_LEN]
    match = None
    for length in range(len(window), 0, -1):
        if window[:length] in NAMED_REFS:
            match = window[:length]
            break
    if match is None:
        return "&", start, None

    end = start + len(match)
    if not match.endswith(";"):
        nxt = source[end : end + 1]
        # Legacy rule: inside an attribute, a semicolon-less reference
        # followed by '=' or an alphanumeric is left alone. This is what
        # keeps query strings like "?a&copy=1" intact.
        if in_attribute and (nxt == "=" or (nxt.isascii() and nxt.isalnum())):
            return "&", start, None
        return NAMED_REFS[match], end, "missing semicolon after character reference"
    return NAMED_REFS[match], end, None
```

- [ ] **Step 4: Call it from the tokenizer**

Add the import at the top of `tokenizer.py`:

```python
from mayshay.htmlparse.entities import decode_reference
```

Add the method to `Tokenizer`:

```python
    def _consume_character_reference(self, in_attribute: bool) -> str:
        """Called with self.pos just past the '&'."""
        text, new_pos, error = decode_reference(self.source, self.pos, in_attribute)
        self.pos = new_pos
        if error:
            self._error(error)
        if text != "&":
            self.metrics["character_references"] += 1
        return text
```

Add the `&` branch to `_state_data`:

```python
        elif ch == "&":
            if not self._buffer:
                self._buffer_start = self.pos - 1
            self._buffer.append(self._consume_character_reference(False))
```

Add the same branch to `_raw_text_state`, but **only** for RCDATA:

```python
        elif ch == "&" and name == "rcdata":
            if not self._buffer:
                self._buffer_start = self.pos - 1
            self._buffer.append(self._consume_character_reference(False))
```

Add it to all three attribute-value states (`_state_attribute_value_double`, `_state_attribute_value_single`, `_state_attribute_value_unquoted`), passing `True`:

```python
        elif ch == "&":
            self._attr_value.append(self._consume_character_reference(True))
```

- [ ] **Step 5: Amend the CLAUDE.md rule**

Replace the first bullet under `## Rules`:

```markdown
- No lxml, no html.parser, no browser libs for core parsing. Hand-rolled only.
  EXCEPTION: `html.entities.html5` is used as the named character reference
  data table (2231 entries). It is data — the WHATWG named reference list —
  not a parser. All matching logic (longest match, the legacy semicolon rule,
  numeric remapping) is hand-rolled in `htmlparse/entities.py`.
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `.venv/bin/pytest tests/htmlparse/ -v`
Expected: all pass, 1 xfailed (double-escaped script from Task 3).

- [ ] **Step 7: Run the corpus entity tests as a smoke check**

```bash
.venv/bin/python -c "
from tests.support.dat import load_tokenizer_tests
print(len(load_tokenizer_tests('namedEntities.test')), 'named entity cases available')
"
```

Expected: a few thousand cases listed. Wiring them into a parametrised run is optional here; Task 6 does the equivalent for tree construction.

- [ ] **Step 8: Commit**

```bash
git add src/mayshay/htmlparse/entities.py src/mayshay/htmlparse/tokenizer.py \
        tests/htmlparse/test_entities.py CLAUDE.md
git commit -m "htmlparse: decode named and numeric character references"
```

---

### Task 5: DOM node module (piece 3)

Plain tree nodes plus the serializer that makes Task 6 testable against the corpus. The serializer emitting html5lib's exact `#document` format is the load-bearing part — it turns "print a tree and squint" into a string equality assertion over thousands of fixtures.

**Files:**
- Create: `src/mayshay/dom/__init__.py`, `src/mayshay/dom/node.py`
- Create: `tests/dom/__init__.py`, `tests/dom/test_node.py`

**Interfaces:**
- Consumes: nothing
- Produces:
  - `Node` with `parent: Node | None`, `children: list[Node]`, `append_child(node) -> Node`, `insert_before(node, ref) -> Node`, `remove_child(node) -> Node`
  - `Document(Node)` with `quirks_mode: bool`, property `document_element -> Element | None`
  - `DocumentType(Node)` with `name: str`
  - `Element(Node)` with `tag_name: str`, `attrs: dict[str, str]`
  - `Text(Node)` with `data: str`
  - `Comment(Node)` with `data: str`
  - `serialize(document: Document) -> str` — html5lib `#document` format

- [ ] **Step 1: Write the failing tests**

Create `tests/dom/__init__.py` (empty) and `tests/dom/test_node.py`:

```python
import pytest

from mayshay.dom.node import (
    Comment,
    Document,
    DocumentType,
    Element,
    Text,
    serialize,
)


def test_append_child_sets_parent():
    parent, child = Element("div"), Element("span")
    parent.append_child(child)
    assert child.parent is parent
    assert parent.children == [child]


def test_append_child_detaches_from_previous_parent():
    a, b, child = Element("a"), Element("b"), Element("span")
    a.append_child(child)
    b.append_child(child)
    assert child.parent is b
    assert a.children == []
    assert b.children == [child]


def test_insert_before_positions_correctly():
    parent = Element("div")
    first, second = Element("a"), Element("b")
    parent.append_child(second)
    parent.insert_before(first, second)
    assert parent.children == [first, second]


def test_insert_before_rejects_non_child():
    parent, node, stranger = Element("div"), Element("a"), Element("b")
    with pytest.raises(ValueError):
        parent.insert_before(node, stranger)


def test_remove_child_clears_parent():
    parent, child = Element("div"), Element("span")
    parent.append_child(child)
    parent.remove_child(child)
    assert child.parent is None
    assert parent.children == []


def test_remove_child_rejects_non_child():
    with pytest.raises(ValueError):
        Element("div").remove_child(Element("span"))


def test_serializer_matches_html5lib_format():
    doc = Document()
    doc.append_child(DocumentType("html"))
    html = doc.append_child(Element("html"))
    html.append_child(Element("head"))
    body = html.append_child(Element("body"))
    p = body.append_child(Element("p"))
    p.append_child(Text("Hello"))

    assert serialize(doc) == (
        "| <!DOCTYPE html>\n"
        "| <html>\n"
        "|   <head>\n"
        "|   <body>\n"
        "|     <p>\n"
        '|       "Hello"'
    )


def test_serializer_sorts_attributes_on_their_own_lines():
    doc = Document()
    el = doc.append_child(Element("div", {"id": "x", "class": "a"}))
    assert serialize(doc) == (
        "| <div>\n"
        '|   class="a"\n'
        '|   id="x"'
    )


def test_serializer_renders_comments():
    doc = Document()
    doc.append_child(Comment(" hi "))
    assert serialize(doc) == "| <!-- hi -->"


def test_deep_tree_does_not_blow_the_stack():
    doc = Document()
    node = doc.append_child(Element("div"))
    for _ in range(5000):
        node = node.append_child(Element("div"))
    assert serialize(doc).count("<div>") == 5001
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/pytest tests/dom/test_node.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'mayshay.dom'`

- [ ] **Step 3: Implement the nodes**

Create `src/mayshay/dom/__init__.py` (empty) and `src/mayshay/dom/node.py`:

```python
"""
DOM node types.

Deliberately minimal: parent/child links, no live NodeLists, no event
targets, no ranges. The names match the spec because we will be typing them
for the rest of the project; the tokenizer's token classes carry a `Token`
suffix precisely so they don't collide with these.
"""

from __future__ import annotations


class Node:
    def __init__(self) -> None:
        self.parent: Node | None = None
        self.children: list[Node] = []

    def append_child(self, node: Node) -> Node:
        if node.parent is not None:
            node.parent.remove_child(node)
        node.parent = self
        self.children.append(node)
        return node

    def insert_before(self, node: Node, ref: Node) -> Node:
        if ref not in self.children:
            raise ValueError("reference node is not a child of this node")
        if node.parent is not None:
            node.parent.remove_child(node)
        node.parent = self
        self.children.insert(self.children.index(ref), node)
        return node

    def remove_child(self, node: Node) -> Node:
        if node not in self.children:
            raise ValueError("node is not a child of this node")
        self.children.remove(node)
        node.parent = None
        return node


class Document(Node):
    def __init__(self) -> None:
        super().__init__()
        self.quirks_mode = False

    @property
    def document_element(self) -> Element | None:
        for child in self.children:
            if isinstance(child, Element) and child.tag_name == "html":
                return child
        return None


class DocumentType(Node):
    def __init__(self, name: str) -> None:
        super().__init__()
        self.name = name


class Element(Node):
    def __init__(self, tag_name: str, attrs: dict[str, str] | None = None) -> None:
        super().__init__()
        self.tag_name = tag_name
        self.attrs: dict[str, str] = dict(attrs or {})

    def __repr__(self) -> str:
        return f"<Element {self.tag_name} {self.attrs}>"


class Text(Node):
    def __init__(self, data: str = "") -> None:
        super().__init__()
        self.data = data

    def __repr__(self) -> str:
        return f"<Text {self.data!r}>"


class Comment(Node):
    def __init__(self, data: str = "") -> None:
        super().__init__()
        self.data = data
```

- [ ] **Step 4: Implement the serializer**

Append to `node.py`. It is iterative, not recursive — real pages nest deeply enough to matter, and the test asserts 5000 levels:

```python
def _render(node: Node, depth: int, out: list[str]) -> None:
    pad = "| " + "  " * depth
    if isinstance(node, Element):
        out.append(f"{pad}<{node.tag_name}>")
        for name in sorted(node.attrs):
            out.append(f'| {"  " * (depth + 1)}{name}="{node.attrs[name]}"')
    elif isinstance(node, Text):
        out.append(f'{pad}"{node.data}"')
    elif isinstance(node, Comment):
        out.append(f"{pad}<!-- {node.data} -->")
    elif isinstance(node, DocumentType):
        out.append(f"{pad}<!DOCTYPE {node.name}>")


def serialize(document: Document) -> str:
    """Render a tree in the html5lib-tests `#document` format."""
    out: list[str] = []
    # Explicit stack; deep documents would overflow Python's recursion limit.
    stack: list[tuple[Node, int]] = [
        (child, 0) for child in reversed(document.children)
    ]
    while stack:
        node, depth = stack.pop()
        _render(node, depth, out)
        stack.extend((child, depth + 1) for child in reversed(node.children))
    return "\n".join(out)
```

- [ ] **Step 5: Run to verify they pass**

Run: `.venv/bin/pytest tests/dom/test_node.py -v`
Expected: 10 passed.

- [ ] **Step 6: Commit**

```bash
git add src/mayshay/dom tests/dom
git commit -m "dom: add node types and html5lib-format serializer"
```

---

### Task 6: Tree builder — 8 insertion modes (piece 4a)

Eight of the spec's 23 modes, an open-elements stack, and a general scope predicate. No active formatting elements yet (Task 7), no adoption agency, no table modes.

The scope algorithm is written generally rather than as `p`/`li` special cases: `has_element_in_scope(target, barriers)` walks the stack downward and stops at a barrier set, which is how the spec expresses every auto-closing rule including the table family later.

**Files:**
- Create: `src/mayshay/htmlparse/treebuilder.py`
- Create: `tests/htmlparse/test_treebuilder.py`, `tests/htmlparse/test_html5lib_tree.py`

**Interfaces:**
- Consumes: all token classes and `Tokenizer.switch_to` (Tasks 1, 3, 4); all DOM types and `serialize` (Task 5); `load_tree_tests`, `requires_corpus` (Task 2)
- Produces:
  - `TreeBuilder(source: str)` with `build() -> Document`
  - `TreeBuilder.open_elements: list[Element]`
  - `TreeBuilder.metrics: Counter[str]`
  - `parse(source: str) -> Document` module-level convenience
  - Constants `VOID_ELEMENTS`, `SCOPE_BARRIERS`, `BUTTON_SCOPE`, `LIST_ITEM_SCOPE`, `IMPLIED_END_TAGS`, `CLOSES_P`

- [ ] **Step 1: Write the failing tests**

Create `tests/htmlparse/test_treebuilder.py`:

```python
import pytest

from mayshay.dom.node import serialize
from mayshay.htmlparse.treebuilder import parse


def tree(src):
    return serialize(parse(src))


def test_implicit_html_head_body():
    assert tree("<p>hi") == (
        "| <html>\n"
        "|   <head>\n"
        "|   <body>\n"
        "|     <p>\n"
        '|       "hi"'
    )


def test_empty_input_still_builds_the_skeleton():
    assert tree("") == "| <html>\n|   <head>\n|   <body>"


def test_title_goes_in_head():
    assert tree("<title>x</title>") == (
        "| <html>\n"
        "|   <head>\n"
        "|     <title>\n"
        '|       "x"\n'
        "|   <body>"
    )


def test_p_does_not_nest():
    assert tree("<p>a<p>b") == (
        "| <html>\n"
        "|   <head>\n"
        "|   <body>\n"
        "|     <p>\n"
        '|       "a"\n'
        "|     <p>\n"
        '|       "b"'
    )


def test_li_siblings_not_nested():
    result = parse("<ul><li>a<li>b</ul>")
    ul = result.document_element.children[1].children[0]
    assert [c.tag_name for c in ul.children] == ["li", "li"]


def test_void_element_has_no_children_and_leaves_no_stack_entry():
    result = parse("<img src=x><p>after")
    body = result.document_element.children[1]
    assert [c.tag_name for c in body.children] == ["img", "p"]
    assert body.children[0].children == []


def test_self_closing_br():
    result = parse("<br/>")
    body = result.document_element.children[1]
    assert [c.tag_name for c in body.children] == ["br"]


def test_unclosed_span_is_closed_by_parent_end_tag():
    result = parse("<div><span></div><p>x")
    body = result.document_element.children[1]
    assert [c.tag_name for c in body.children] == ["div", "p"]


def test_comment_before_html_attaches_to_document():
    from mayshay.dom.node import Comment

    result = parse("<!-- c --><p>x")
    assert isinstance(result.children[0], Comment)
    assert result.children[0].data == " c "


def test_doctype_becomes_a_node():
    assert tree("<!DOCTYPE html><p>x").startswith("| <!DOCTYPE html>\n| <html>")


def test_stray_end_p_inserts_an_empty_p():
    """Genuine spec behaviour, and a good canary for the in_body mode."""
    result = parse("</p>")
    body = result.document_element.children[1]
    assert [c.tag_name for c in body.children] == ["p"]


def test_metrics_are_emitted():
    from mayshay.htmlparse.treebuilder import TreeBuilder

    tb = TreeBuilder("<div><p>hi</p></div>")
    tb.build()
    assert tb.metrics["elements"] == 5   # html, head, body, div, p
    assert tb.metrics["max_depth"] >= 4
    assert "parse_time_ms" in tb.metrics


@pytest.mark.xfail(reason="adoption agency not implemented; Task 7 + future work")
def test_misnested_formatting_tags():
    result = parse("<b><i></b></i>x")
    body = result.document_element.children[1]
    assert [c.tag_name for c in body.children] == ["b", "i"]


@pytest.mark.xfail(reason="table insertion modes out of scope for phase 1")
def test_table_structure():
    result = parse("<table><tr><td>x</table>")
    table = result.document_element.children[1].children[0]
    assert table.children[0].tag_name == "tbody"
```

Create `tests/htmlparse/test_html5lib_tree.py`:

```python
import pytest

from mayshay.dom.node import serialize
from mayshay.htmlparse.treebuilder import parse
from tests.conftest import requires_corpus
from tests.support.dat import load_tree_tests

# Files whose features are in scope for phase 1. Everything else waits for
# the table modes, foreign content, and the adoption agency algorithm.
IN_SCOPE_FILES = ("tests1.dat",)


def _cases():
    try:
        return [t for t in load_tree_tests(*IN_SCOPE_FILES) if t.fragment is None]
    except FileNotFoundError:
        return []


@requires_corpus
@pytest.mark.parametrize("case", _cases(), ids=lambda c: c.id)
def test_tree_construction(case):
    assert serialize(parse(case.data)) == case.document
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/pytest tests/htmlparse/test_treebuilder.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'mayshay.htmlparse.treebuilder'`

- [ ] **Step 3: Implement the element tables and scope predicate**

Create `src/mayshay/htmlparse/treebuilder.py`:

```python
"""
Simplified HTML tree construction.

Implements 8 of the spec's 23 insertion modes: initial, before_html,
before_head, in_head, after_head, in_body, text, after_body. Deliberately
absent, in rough order of when they will start to hurt:

1. The adoption agency algorithm (misnested formatting tags).
2. The table insertion modes and foster parenting.
3. Foreign content (SVG, MathML).
4. Templates, frames, select.

The scope predicate is written generally rather than as p/li special cases,
because every auto-closing rule in the spec — including the table family —
is expressed through it.
"""

from __future__ import annotations

import time
from collections import Counter

from mayshay.dom.node import Comment, Document, DocumentType, Element, Text
from mayshay.htmlparse.tokenizer import (
    CharacterToken,
    CommentToken,
    DoctypeToken,
    EndTagToken,
    EOFToken,
    StartTagToken,
    Tokenizer,
    RAWTEXT_ELEMENTS,
    RCDATA_ELEMENTS,
    SCRIPT_ELEMENTS,
)

VOID_ELEMENTS = frozenset({
    "area", "base", "basefont", "bgsound", "br", "col", "embed", "frame",
    "hr", "img", "input", "keygen", "link", "meta", "param", "source",
    "track", "wbr",
})

HEAD_ELEMENTS = frozenset({
    "base", "basefont", "bgsound", "link", "meta", "noframes", "script",
    "style", "template", "title",
})

# Barriers for "has an element in scope". The spec's list also includes
# MathML/SVG integration points, which we skip until foreign content lands.
SCOPE_BARRIERS = frozenset({
    "applet", "caption", "html", "table", "td", "th", "marquee", "object",
})
BUTTON_SCOPE = SCOPE_BARRIERS | {"button"}
LIST_ITEM_SCOPE = SCOPE_BARRIERS | {"ol", "ul"}

IMPLIED_END_TAGS = frozenset({
    "dd", "dt", "li", "optgroup", "option", "p", "rb", "rp", "rt", "rtc",
})

# Start tags that close an open <p> before being inserted.
CLOSES_P = frozenset({
    "address", "article", "aside", "blockquote", "center", "details",
    "dialog", "dir", "div", "dl", "fieldset", "figcaption", "figure",
    "footer", "form", "h1", "h2", "h3", "h4", "h5", "h6", "header",
    "hgroup", "hr", "listing", "main", "menu", "nav", "ol", "p", "plaintext",
    "pre", "section", "summary", "table", "ul",
})
```

- [ ] **Step 4: Implement the builder core**

Append to `treebuilder.py`:

```python
class TreeBuilder:
    def __init__(self, source: str) -> None:
        self.source = source
        self.tokenizer = Tokenizer(source)
        self.document = Document()
        self.open_elements: list[Element] = []
        self.mode = "initial"
        self.original_mode = "in_body"
        self.head: Element | None = None
        self.metrics: Counter[str] = Counter()

    # -- stack helpers -----------------------------------------------------

    @property
    def current(self) -> Element | None:
        return self.open_elements[-1] if self.open_elements else None

    def _insertion_point(self):
        return self.current if self.open_elements else self.document

    def has_element_in_scope(self, target: str, barriers=SCOPE_BARRIERS) -> bool:
        for el in reversed(self.open_elements):
            if el.tag_name == target:
                return True
            if el.tag_name in barriers:
                return False
        return False

    def generate_implied_end_tags(self, *, excluding: str | None = None) -> None:
        while (
            self.current is not None
            and self.current.tag_name in IMPLIED_END_TAGS
            and self.current.tag_name != excluding
        ):
            self.open_elements.pop()

    def close_p_element(self) -> None:
        self.generate_implied_end_tags(excluding="p")
        while self.open_elements:
            if self.open_elements.pop().tag_name == "p":
                break

    def pop_until(self, name: str) -> None:
        while self.open_elements:
            if self.open_elements.pop().tag_name == name:
                break

    # -- insertion ---------------------------------------------------------

    def insert_element(self, token: StartTagToken) -> Element:
        el = Element(token.name, token.attrs)
        self._insertion_point().append_child(el)
        self.metrics["elements"] += 1
        if token.name not in VOID_ELEMENTS:
            self.open_elements.append(el)
            self.metrics["max_depth"] = max(
                self.metrics["max_depth"], len(self.open_elements)
            )
        return el

    def insert_text(self, data: str) -> None:
        point = self._insertion_point()
        # Merge with a trailing text node rather than fragmenting the tree.
        if point.children and isinstance(point.children[-1], Text):
            point.children[-1].data += data
        else:
            point.append_child(Text(data))
            self.metrics["text_nodes"] += 1

    def insert_raw_text_element(self, token: StartTagToken, state: str) -> None:
        """Generic RAWTEXT/RCDATA element parsing: the tree builder drives
        the tokenizer, which is why Tokenizer.switch_to exists."""
        self.insert_element(token)
        self.tokenizer.switch_to(state, last_start_tag=token.name)
        self.original_mode = self.mode
        self.mode = "text"
```

- [ ] **Step 5: Implement the mode dispatch and the eight modes**

Append to `treebuilder.py`:

```python
    def build(self) -> Document:
        started = time.perf_counter()
        for token in self.tokenizer.tokenize():
            self.dispatch(token)
            if isinstance(token, EOFToken):
                break
        self.metrics["parse_time_ms"] = int(
            (time.perf_counter() - started) * 1000
        )
        self.metrics["parse_errors"] = self.tokenizer.metrics["parse_errors"]
        return self.document

    def dispatch(self, token) -> None:
        getattr(self, f"_mode_{self.mode}")(token)

    def _is_space(self, token) -> bool:
        return isinstance(token, CharacterToken) and not token.data.strip()

    def _mode_initial(self, token) -> None:
        if isinstance(token, DoctypeToken):
            self.document.append_child(DocumentType(token.name or "html"))
            self.document.quirks_mode = token.force_quirks
            self.mode = "before_html"
        elif isinstance(token, CommentToken):
            self.document.append_child(Comment(token.data))
        elif self._is_space(token):
            pass
        else:
            self.document.quirks_mode = True
            self.mode = "before_html"
            self.dispatch(token)

    def _mode_before_html(self, token) -> None:
        if isinstance(token, CommentToken):
            self.document.append_child(Comment(token.data))
        elif self._is_space(token):
            pass
        elif isinstance(token, StartTagToken) and token.name == "html":
            self.insert_element(token)
            self.mode = "before_head"
        else:
            self.insert_element(StartTagToken("html"))
            self.mode = "before_head"
            self.dispatch(token)

    def _mode_before_head(self, token) -> None:
        if isinstance(token, CommentToken):
            self._insertion_point().append_child(Comment(token.data))
        elif self._is_space(token):
            pass
        elif isinstance(token, StartTagToken) and token.name == "head":
            self.head = self.insert_element(token)
            self.mode = "in_head"
        else:
            self.head = self.insert_element(StartTagToken("head"))
            self.mode = "in_head"
            self.dispatch(token)

    def _mode_in_head(self, token) -> None:
        if self._is_space(token):
            self.insert_text(token.data)
        elif isinstance(token, CommentToken):
            self._insertion_point().append_child(Comment(token.data))
        elif isinstance(token, StartTagToken) and token.name in RCDATA_ELEMENTS:
            self.insert_raw_text_element(token, "rcdata")
        elif isinstance(token, StartTagToken) and token.name in RAWTEXT_ELEMENTS:
            self.insert_raw_text_element(token, "rawtext")
        elif isinstance(token, StartTagToken) and token.name in SCRIPT_ELEMENTS:
            self.insert_raw_text_element(token, "script_data")
        elif isinstance(token, StartTagToken) and token.name in HEAD_ELEMENTS:
            self.insert_element(token)
        elif isinstance(token, EndTagToken) and token.name == "head":
            self.pop_until("head")
            self.mode = "after_head"
        else:
            self.pop_until("head")
            self.mode = "after_head"
            self.dispatch(token)

    def _mode_after_head(self, token) -> None:
        if self._is_space(token):
            self.insert_text(token.data)
        elif isinstance(token, CommentToken):
            self._insertion_point().append_child(Comment(token.data))
        elif isinstance(token, StartTagToken) and token.name == "body":
            self.insert_element(token)
            self.mode = "in_body"
        else:
            self.insert_element(StartTagToken("body"))
            self.mode = "in_body"
            self.dispatch(token)

    def _mode_in_body(self, token) -> None:
        if isinstance(token, CharacterToken):
            self.insert_text(token.data)
        elif isinstance(token, CommentToken):
            self._insertion_point().append_child(Comment(token.data))
        elif isinstance(token, StartTagToken):
            self._in_body_start(token)
        elif isinstance(token, EndTagToken):
            self._in_body_end(token)
        elif isinstance(token, EOFToken):
            self.mode = "after_body"

    def _in_body_start(self, token: StartTagToken) -> None:
        name = token.name
        if name in RCDATA_ELEMENTS:
            self.insert_raw_text_element(token, "rcdata")
        elif name in RAWTEXT_ELEMENTS:
            self.insert_raw_text_element(token, "rawtext")
        elif name in SCRIPT_ELEMENTS:
            self.insert_raw_text_element(token, "script_data")
        elif name == "li":
            if self.has_element_in_scope("li", LIST_ITEM_SCOPE):
                self.generate_implied_end_tags(excluding="li")
                self.pop_until("li")
            if self.has_element_in_scope("p", BUTTON_SCOPE):
                self.close_p_element()
            self.insert_element(token)
        elif name in ("dd", "dt"):
            for tag in ("dd", "dt"):
                if self.has_element_in_scope(tag):
                    self.generate_implied_end_tags(excluding=tag)
                    self.pop_until(tag)
                    break
            if self.has_element_in_scope("p", BUTTON_SCOPE):
                self.close_p_element()
            self.insert_element(token)
        elif name in CLOSES_P:
            if self.has_element_in_scope("p", BUTTON_SCOPE):
                self.close_p_element()
            self.insert_element(token)
        else:
            self.insert_element(token)

    def _in_body_end(self, token: EndTagToken) -> None:
        name = token.name
        if name == "p":
            if not self.has_element_in_scope("p", BUTTON_SCOPE):
                # Spec: parse error, then insert an empty <p> and close it.
                self.insert_element(StartTagToken("p"))
            self.close_p_element()
        elif name == "body":
            self.mode = "after_body"
        elif name == "html":
            self.mode = "after_body"
            self.dispatch(token)
        elif self.has_element_in_scope(name):
            self.generate_implied_end_tags(excluding=name)
            self.pop_until(name)
        # An end tag with nothing matching in scope is ignored.

    def _mode_text(self, token) -> None:
        if isinstance(token, CharacterToken):
            self.insert_text(token.data)
        elif isinstance(token, EndTagToken):
            self.open_elements.pop()
            self.mode = self.original_mode
        elif isinstance(token, EOFToken):
            self.open_elements.pop()
            self.mode = self.original_mode
            self.dispatch(token)

    def _mode_after_body(self, token) -> None:
        if isinstance(token, CommentToken):
            self.document.append_child(Comment(token.data))
        elif isinstance(token, EOFToken):
            pass
        elif self._is_space(token):
            pass
        else:
            self.mode = "in_body"
            self.dispatch(token)


def parse(source: str) -> Document:
    return TreeBuilder(source).build()
```

- [ ] **Step 6: Run the unit tests**

Run: `.venv/bin/pytest tests/htmlparse/test_treebuilder.py -v`
Expected: 12 passed, 2 xfailed.

- [ ] **Step 7: Run the corpus tests and record the baseline**

Run: `.venv/bin/pytest tests/htmlparse/test_html5lib_tree.py -q`

Expected: a mix of pass and fail. `tests1.dat` includes cases needing the adoption agency and the table modes, which are out of scope — **do not chase them to green.** Record the pass rate in the commit message so Task 7's improvement is measurable:

```bash
.venv/bin/pytest tests/htmlparse/test_html5lib_tree.py -q 2>&1 | tail -1
```

If the failure list is dominated by categories outside phase 1, narrow `IN_SCOPE_FILES` or add an explicit skip-list with a comment naming the missing feature. Do not weaken the assertion.

- [ ] **Step 8: Commit**

```bash
git add src/mayshay/htmlparse/treebuilder.py tests/htmlparse/test_treebuilder.py \
        tests/htmlparse/test_html5lib_tree.py
git commit -m "htmlparse: tree builder with 8 insertion modes and scope predicate"
```

---

### Task 7: Active formatting elements and reconstruction (piece 4b)

Sequenced after the modes pass, as agreed. This adds the **list of active formatting elements** and the **reconstruct** algorithm — which is what re-opens `<b>` after a block boundary — while still stubbing the adoption agency algorithm itself.

Reconstruction and adoption agency are different algorithms. Reconstruction is short and fixes visible breakage on ordinary pages; adoption agency is the repair algorithm for misnesting and stays out.

**Files:**
- Modify: `src/mayshay/htmlparse/treebuilder.py`
- Modify: `tests/htmlparse/test_treebuilder.py`

**Interfaces:**
- Consumes: everything from Task 6
- Produces:
  - `FORMATTING_ELEMENTS: frozenset[str]`
  - `TreeBuilder.active_formatting: list[Element | None]` (`None` is the scope marker)
  - `TreeBuilder.push_formatting(el: Element) -> None` — includes the Noah's Ark clause
  - `TreeBuilder.reconstruct_formatting() -> None`
  - `TreeBuilder.clear_formatting_to_marker() -> None`

- [ ] **Step 1: Write the failing tests**

Append to `tests/htmlparse/test_treebuilder.py`:

```python
def test_formatting_reconstructed_across_block_boundary():
    """<b> must re-open inside the second <p>, or the bold silently vanishes."""
    result = parse("<p><b>one<p>two")
    body = result.document_element.children[1]
    first, second = body.children
    assert [c.tag_name for c in first.children] == ["b"]
    assert [c.tag_name for c in second.children] == ["b"]
    assert second.children[0].children[0].data == "two"


def test_noahs_ark_limits_identical_entries():
    from mayshay.htmlparse.treebuilder import TreeBuilder

    tb = TreeBuilder('<b><b><b><b>x')
    tb.build()
    # At most three identical formatting entries survive on the list.
    bolds = [e for e in tb.active_formatting if e is not None and e.tag_name == "b"]
    assert len(bolds) <= 3


def test_formatting_list_cleared_by_end_tag():
    from mayshay.htmlparse.treebuilder import TreeBuilder

    tb = TreeBuilder("<b>x</b>y")
    tb.build()
    assert all(e is None or e.tag_name != "b" for e in tb.active_formatting)
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/pytest tests/htmlparse/test_treebuilder.py -v -k "formatting or noah"`
Expected: FAIL — `AttributeError: 'TreeBuilder' object has no attribute 'active_formatting'`

- [ ] **Step 3: Implement the list**

Add the constant near the other tables in `treebuilder.py`:

```python
FORMATTING_ELEMENTS = frozenset({
    "a", "b", "big", "code", "em", "font", "i", "nobr", "s", "small",
    "strike", "strong", "tt", "u",
})
```

Add to `TreeBuilder.__init__`:

```python
        # None entries are scope markers (inserted by applet/object/marquee
        # and the table modes). Reconstruction never crosses one.
        self.active_formatting: list[Element | None] = []
```

Add the methods:

```python
    def push_formatting(self, el: Element) -> None:
        # Noah's Ark clause: at most three entries with the same tag name and
        # attributes may appear after the last marker.
        matches = 0
        for entry in reversed(self.active_formatting):
            if entry is None:
                break
            if entry.tag_name == el.tag_name and entry.attrs == el.attrs:
                matches += 1
                if matches == 3:
                    self.active_formatting.remove(entry)
                    break
        self.active_formatting.append(el)

    def clear_formatting_to_marker(self) -> None:
        while self.active_formatting:
            if self.active_formatting.pop() is None:
                break

    def reconstruct_formatting(self) -> None:
        """
        Re-open formatting elements that are on the list but no longer on the
        open-elements stack. This is what makes <p><b>one<p>two render `two`
        in bold. It is NOT the adoption agency algorithm.
        """
        if not self.active_formatting:
            return
        last = self.active_formatting[-1]
        if last is None or last in self.open_elements:
            return

        index = len(self.active_formatting) - 1
        while index > 0:
            candidate = self.active_formatting[index - 1]
            if candidate is None or candidate in self.open_elements:
                break
            index -= 1

        while index < len(self.active_formatting):
            entry = self.active_formatting[index]
            clone = Element(entry.tag_name, entry.attrs)
            self._insertion_point().append_child(clone)
            self.open_elements.append(clone)
            self.metrics["elements"] += 1
            self.active_formatting[index] = clone
            index += 1
```

- [ ] **Step 4: Hook reconstruction into `in_body`**

In `_mode_in_body`, reconstruct before inserting text:

```python
        if isinstance(token, CharacterToken):
            if token.data.strip():
                self.reconstruct_formatting()
            self.insert_text(token.data)
```

In `_in_body_start`, add a formatting branch before the generic `else`:

```python
        elif name in FORMATTING_ELEMENTS:
            self.reconstruct_formatting()
            el = self.insert_element(token)
            self.push_formatting(el)
```

And reconstruct before ordinary elements too — replace the final `else` with:

```python
        else:
            self.reconstruct_formatting()
            self.insert_element(token)
```

In `_in_body_end`, remove the element from the list when its end tag arrives. Add before the `elif self.has_element_in_scope(name):` branch:

```python
        elif name in FORMATTING_ELEMENTS:
            # Without the adoption agency algorithm this is the simple case:
            # pop to the element and drop it from the formatting list.
            # Misnested cases (<b><i></b></i>) still come out wrong — see the
            # xfail in tests/htmlparse/test_treebuilder.py.
            for entry in reversed(self.active_formatting):
                if entry is not None and entry.tag_name == name:
                    self.active_formatting.remove(entry)
                    break
            if self.has_element_in_scope(name):
                self.generate_implied_end_tags(excluding=name)
                self.pop_until(name)
```

- [ ] **Step 5: Run the tests**

Run: `.venv/bin/pytest tests/htmlparse/ tests/dom/ -v`
Expected: all pass, 3 xfailed (double-escaped script, adoption agency, tables).

- [ ] **Step 6: Re-run the corpus and compare to the Task 6 baseline**

```bash
.venv/bin/pytest tests/htmlparse/test_html5lib_tree.py -q 2>&1 | tail -1
```

Expected: pass count strictly higher than the baseline recorded in Task 6 Step 7. If it dropped, reconstruction is firing where it should not — check that it is not called for whitespace-only text.

- [ ] **Step 7: Commit**

```bash
git add src/mayshay/htmlparse/treebuilder.py tests/htmlparse/test_treebuilder.py
git commit -m "htmlparse: add active formatting elements list and reconstruction"
```

---

## Phase 1 Done When

- `.venv/bin/pytest` is green, with exactly three documented xfails: double-escaped script data, adoption agency, table modes.
- `parse()` turns a saved real-world page into a tree without raising.
- The html5lib-tests pass rate on the in-scope files is recorded in the Task 7 commit message, and is higher than the Task 6 baseline.
- `CLAUDE.md` records the `html.entities` exception.

## Known Gaps Carried Into Phase 2

1. **Adoption agency algorithm** — misnested formatting tags come out wrong. Expect this to bite early; unclosed `<a>` and `<b>` spanning block boundaries are everywhere.
2. **Table insertion modes and foster parenting** — 7 more modes.
3. **Foreign content** — SVG and MathML, including the integration points currently missing from `SCOPE_BARRIERS`.
4. **Double-escaped script data** — `<!--<script>` nested in script text.
5. **NULL handling** — U+0000 is not replaced with U+FFFD.
6. **DOCTYPE public/system identifiers** — discarded, so quirks-mode detection is name-only.
7. **Metrics are not yet written to `data/metrics/`** — `TreeBuilder.metrics` is populated but never persisted, so the `CLAUDE.md` rule is only half satisfied.

## Self-Review

**Spec coverage.** All four agreed pieces have tasks: entities (4), script states (3), DOM (5), tree builder (6). All amendments are covered: six fixes plus offsets as commit one (1), order 2→1→3→4 (Tasks 3→4→5→6), `html.entities.html5` with the `CLAUDE.md` amendment (4, Step 5), AFE sequenced after the modes pass (7), html5lib-tests submodule with a `.dat` loader (2), plans in `docs/plans/` (this file).

**Type consistency.** Token names are `*Token` throughout Tasks 1, 3, 4, 6. `serialize(document)` is defined in Task 5 and used in Task 6. `switch_to(state, last_start_tag)` is defined in Task 1, used in Task 6's `insert_raw_text_element`. `has_element_in_scope(target, barriers)` keeps one signature in Tasks 6 and 7. `decode_reference` returns a 3-tuple in both its definition and its call site.

**Known rough edges, flagged rather than hidden.** Task 3 Step 7 reorders `self.state = "data"` and `self._emit_tag()` at six call sites — if any is missed, raw-text elements will silently fail to switch state, and `test_returns_to_data_between_scripts` is the test that catches it. Task 6 Step 7 will not reach 100% on `tests1.dat`, and that is expected, not a defect; the instruction there is explicitly not to chase it green by weakening assertions.

**Amended 2026-08-26 after review.** Three defects were caught in `_raw_end_tag_name_state` and `_raw_text_state` before execution began: the appropriate-end-tag branches did not flush pending raw text, so a closing tag would surface before the text it encloses; a vestigial `-` branch in `_raw_text_state` duplicated the `else` case while skipping `_buffer_start` initialisation. Both are fixed above. The ordering defect was invisible to the original test set because `text_of()` and `names()` each aggregate one token kind — hence the `pairs()` helper and the three `test_text_emitted_before_*` tests, one per branch. General lesson for the remaining tasks: assertions that aggregate can pass while ordering is wrong.
