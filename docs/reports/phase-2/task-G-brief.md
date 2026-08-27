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

