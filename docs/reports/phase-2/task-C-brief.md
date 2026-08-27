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

