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

