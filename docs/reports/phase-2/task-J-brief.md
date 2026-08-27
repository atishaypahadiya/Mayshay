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

## Self-Review

**Scope coverage.** Task A covers the metrics writer with the driver-calls decision and the two-stage amendment. Task B covers the rename, the mirrored error list, the recording sites, and the `#errors` vocabulary with multiset-not-position comparison. Task C covers identifier capture and mode classification, recording without behaviour. Task E removes `tinycss2` and records the rule. Tasks E–J cover tokenizer, parser, selectors, specificity, matching, values, cascade, inheritance and computed values, over the nine named properties. Task D covers all four handoff items taken as written: `computed_style` on `Node`, `class_list` frozenset, cached element index, and — in Task H — right-to-left matching with rightmost-token indexing. Computed-vs-used symbolic storage is pinned by three tests in Task J.

**Type consistency.** `metrics.emit` keeps one signature across Tasks A and J. `ComputedStyle` is produced in J and consumed only there in this phase. `annotate_positions` is defined in D and used in H. `DoctypeToken.public_id`/`system_id` are added in C and consumed by `classify_document_mode` in the same task. `Length`/`Percent`/`Color`/`AUTO` are defined in I and used in J's assertions.

**Two known rough edges, flagged rather than hidden.** Task C's quirks table is given complete — all 55 prefixes — rather than sampled, because a truncated list with a "transcribe the rest" comment is exactly the placeholder this plan format forbids, and an incomplete table misclassifies silently while only nine unit cases are pinned. It was transcribed into the plan and may still contain errors, so Step 5 requires checking it against the spec and reporting the count found, and the whole of `doctype01.dat` is added to the test set as the broad check nine hand-written cases cannot be. And Task B's corpus test will not reach 100%: the instruction is to report matched and unmatched counts separately and **not** to broaden `TREE_ERROR_CODES` to absorb failures, since a code recorded outside the curated set is the mapping bug the set exists to catch.

**Corrections applied after review, recorded so they are not re-introduced.** `METRICS_DIR`'s `parents[2]` derivation is a fallback, not a contract — drivers pass an explicit path, because that derivation holds only under an editable install and Phase 1 saw exactly that pointer broken. `test_unitless_nonzero_length_is_invalid` dropped "in standards mode" from its name rather than gaining an unused parameter to justify it. `test_link_stylesheets_are_counted_not_fetched` now asserts the counter and discriminates 2 from 0; as first drafted it asserted only facts true of any document, which is the decorative-test defect that cost a fix round in Phase 1 Task 3. And `Color(0, 128, 0)` for CSS `green` is correct — `#00FF00` is `lime`.
