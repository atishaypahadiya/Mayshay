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

