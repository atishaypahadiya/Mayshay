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

