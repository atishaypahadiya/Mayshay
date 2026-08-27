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

