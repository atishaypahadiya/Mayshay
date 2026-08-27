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

