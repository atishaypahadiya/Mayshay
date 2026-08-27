"""
Selector matching over the real pages in `data/corpus/`.

`test_matching.py` proves the matcher and the index on trees built to order.
This file runs both against pages nobody wrote for them: every `<style>`
selector in the corpus, against every element of the document that shipped
it. Two jobs.

First, the invariant `RuleIndex` exists to preserve. `candidates(element)`
must be a *superset* of the rules that match -- a rule it drops is a rule the
cascade can never apply, and the shape of that bug (a rightmost compound
whose key nobody thought of) is exactly the shape a hand-written fixture
misses. Checking every element against every selector is the brute-force
answer the index is an optimisation *of*, so it is the one check that cannot
share the index's blind spots.

Second, the optimisation, measured on real input rather than on six rules and
one element. The brief's `test_rule_index_narrows_candidates` asserts a `<`
that a `RuleIndex` returning nothing at all would also satisfy; the floor
here is a ratio against the brute-force product, and it is checked next to
the superset assertion that stops "return nothing" from being a way to pass
it.

Coverage is asserted, not assumed, for the reason `test_selectors_corpus.py`
gives: this project has twice shipped a corpus loader that silently walked
zero cases.

One thing this file measurably does *not* cover, recorded because it was
checked rather than assumed: **not one of the corpus's 279 selectors lands in
the catch-all bucket** -- every rightmost compound names an id, a class or a
type. Deleting the catch-all bucket entirely leaves every test here green.
That is a fact about 2000s-era inline stylesheets, not a defect in the sweep,
and it is exactly why dropping that bucket is such a quiet bug: it is
invisible on real pages until someone writes `* { box-sizing: border-box }`.
`test_rule_index_returns_the_catch_all_bucket_for_every_element` in
`test_matching.py` is the guard, and it has to be a fixture test.
"""

import pathlib

from mayshay.cssparse.matching import RuleIndex, matches
from mayshay.cssparse.parser import AtRule, QualifiedRule, parse_stylesheet
from mayshay.cssparse.selectors import SelectorParseError, parse_selector_list
from mayshay.dom.node import Element, Text, annotate_positions
from mayshay.htmlparse.treebuilder import TreeBuilder

from .test_selectors_corpus import _nested_preludes, _walk

CORPUS = pathlib.Path(__file__).resolve().parents[2] / "data" / "corpus"

# Floors, not exact counts. Actuals when written: 3 pages, 8596 elements,
# 279 selectors, 2155 matches, and 2.89% of the brute-force product tested
# (wikipedia.html alone: 7778 elements x 274 selectors, 2.89%; hn.html links
# its stylesheet and contributes elements but no selectors).
MIN_PAGES = 3
MIN_ELEMENTS = 5000
MIN_SELECTORS = 260
MIN_MATCHES = 500
MAX_CANDIDATE_FRACTION = 0.10


def _pages():
    """(name, document, elements, selectors) for every corpus page.

    The document and the selectors come from the same file: a page's own
    `<style>` rules are the ones written to match it, so this measures
    matching on the pairing that actually occurs.
    """
    for path in sorted(CORPUS.glob("*.html")):
        document = TreeBuilder(path.read_text(errors="replace")).build()
        annotate_positions(document)
        elements, selectors = [], []
        for node in _walk(document):
            if not isinstance(node, Element):
                continue
            elements.append(node)
            if node.tag_name != "style":
                continue
            css = "".join(c.data for c in node.children if isinstance(c, Text))
            if not css.strip():
                continue
            preludes = []
            for rule in parse_stylesheet(css):
                if isinstance(rule, QualifiedRule):
                    preludes.append(rule.prelude)
                elif isinstance(rule, AtRule) and rule.block is not None:
                    preludes.extend(_nested_preludes(rule.block))
            for prelude in preludes:
                try:
                    parsed = parse_selector_list(prelude)
                except SelectorParseError:
                    # Parse strictness is `test_selectors_corpus.py`'s
                    # subject, and it asserts there are none. Skipping here
                    # keeps one failure per cause.
                    continue
                selectors.extend(parsed.selectors)
        yield path.name, elements, selectors


PAGES = list(_pages())


def test_the_corpus_sweep_is_not_silently_empty():
    assert CORPUS.is_dir()
    assert len(PAGES) >= MIN_PAGES
    assert sum(len(e) for _, e, _ in PAGES) >= MIN_ELEMENTS
    assert sum(len(s) for _, _, s in PAGES) >= MIN_SELECTORS


def test_the_index_never_drops_a_rule_that_matches_a_real_page():
    """Every element of every corpus page against every selector that page
    ships -- the brute force the index replaces, used to check it.
    """
    matched = 0
    for name, elements, selectors in PAGES:
        if not selectors:
            # hn.html links its stylesheet instead of inlining it, which is
            # normal and is not this test's failure.
            continue
        index = RuleIndex(selectors)
        for element in elements:
            candidates = index.candidates(element)
            for selector in selectors:
                if matches(element, selector):
                    matched += 1
                    assert selector in candidates, (name, element.tag_name)
    assert matched >= MIN_MATCHES


def test_the_index_narrows_real_pages_by_an_order_of_magnitude():
    tested = brute = 0
    for _, elements, selectors in PAGES:
        if not selectors:
            continue
        index = RuleIndex(selectors)
        tested += sum(len(index.candidates(e)) for e in elements)
        brute += len(selectors) * len(elements)
    assert brute > 0
    assert tested / brute < MAX_CANDIDATE_FRACTION, tested / brute


def test_matching_a_real_page_does_not_raise():
    """Selector features the fixtures never exercise -- `:not(.notheme)`,
    `[dir="rtl"]`, stacked compounds -- reach the matcher here. Any of them
    hitting an unhandled branch is a crash, not a False.
    """
    seen = 0
    for _, elements, selectors in PAGES:
        for selector in selectors:
            for element in elements:
                assert matches(element, selector) in (True, False)
                seen += 1
                break
    assert seen >= MIN_SELECTORS
