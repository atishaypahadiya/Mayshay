"""
Selector parsing over the real stylesheets in `data/corpus/`.

Two jobs, and the second is the reason this is a committed test rather than
the throwaway script it started as. First: every selector real pages
actually ship must parse -- `parse_selector_list` raises rather than
recovering, so a rule it rejects is a rule the engine will never apply, and
a strictness decision that looks principled in isolation can quietly delete
a tenth of a stylesheet. Second: several of this module's strict forms are
*deliberate* divergences (the source-adjacency rule of deviation 1 is
browser parity against the letter of the spec; the pseudo-element stacking
limit of deviation 7 is stricter than the grammar). Those need a regression
guard next to the evidence that licenses them, or the next reader "fixes"
one back and nothing fails.

Coverage is asserted, not assumed. This project has twice shipped a corpus
loader that silently walked zero cases, so every level of the sweep --
files, `<style>` elements, rules, selectors -- has a floor.
"""

import pathlib

import pytest
from mayshay.cssparse.parser import AtRule, QualifiedRule, parse_stylesheet
from mayshay.cssparse.selectors import (
    Complex,
    SelectorParseError,
    parse_selector_list,
    specificity,
)
from mayshay.cssparse.tokenizer import (
    AtKeyword,
    CssToken,
    CssTokenizer,
    LBrace,
    RBrace,
    Whitespace,
)
from mayshay.dom.node import Element, Text
from mayshay.htmlparse.treebuilder import TreeBuilder

CORPUS = pathlib.Path(__file__).resolve().parents[2] / "data" / "corpus"

# Floors, not exact counts: re-collecting the corpus should not break the
# build, but losing most of it must. Actuals when written: 3 HTML files, 2
# of them carrying <style> (hn.html links its CSS instead and contributes
# nothing), 19 <style> elements, 193 style rules -- 156 top-level and 37
# inside @media -- and 279 selectors.
MIN_HTML_FILES = 3
MIN_FILES_WITH_STYLE = 2
MIN_STYLE_ELEMENTS = 15
MIN_RULES = 180
MIN_SELECTORS = 260


def _walk(node):
    yield node
    for child in getattr(node, "children", []):
        yield from _walk(child)


def _style_bodies():
    """The text of every `<style>` element in the corpus, found with this
    engine's own tree builder rather than a regex.
    """
    for path in sorted(CORPUS.glob("*.html")):
        document = TreeBuilder(path.read_text(errors="replace")).build()
        for node in _walk(document):
            if isinstance(node, Element) and node.tag_name == "style":
                text = "".join(
                    c.data for c in node.children if isinstance(c, Text)
                )
                if text.strip():
                    yield path.name, text


def _nested_preludes(block: list[CssToken]):
    """The preludes of the style rules directly inside an at-rule's block.

    `parse_stylesheet` does not descend into `@media`, and the generic
    grammar exposes no rules-from-tokens entry point (see `parser.py`) --
    but a quarter of this corpus's style rules live inside one, and a sweep
    that skipped them would be measuring the easy half. A prelude is the
    token run before a top-level `{`, which is exactly what 5.5.3 collects;
    runs beginning with an `<at-keyword-token>` are a nested at-rule's
    prelude, not a selector, and are skipped.
    """
    prelude: list[CssToken] = []
    depth = 0
    for tok in block:
        if isinstance(tok, LBrace):
            if depth == 0:
                head = next(
                    (t for t in prelude if not isinstance(t, Whitespace)), None
                )
                if prelude and not isinstance(head, AtKeyword):
                    yield prelude
                prelude = []
            depth += 1
            continue
        if isinstance(tok, RBrace):
            depth = max(0, depth - 1)
            continue
        if depth == 0:
            prelude.append(tok)


def _sweep():
    """(files, style elements, preludes) across the whole corpus."""
    files, elements, preludes = set(), 0, []
    for name, css in _style_bodies():
        files.add(name)
        elements += 1
        for rule in parse_stylesheet(css):
            if isinstance(rule, QualifiedRule):
                preludes.append((name, rule.prelude))
            elif isinstance(rule, AtRule) and rule.block is not None:
                for prelude in _nested_preludes(rule.block):
                    preludes.append((name, prelude))
    return files, elements, preludes


SWEEP = _sweep()


def test_the_corpus_sweep_is_not_silently_empty():
    """The failure mode this project keeps hitting: a loader that finds
    nothing and reports success.
    """
    files, elements, preludes = SWEEP
    assert CORPUS.is_dir()
    # Corpus files and files that carry CSS are counted separately: a page
    # with no <style> is normal (hn.html links its stylesheet), a corpus
    # with no pages is the bug.
    assert len(list(CORPUS.glob("*.html"))) >= MIN_HTML_FILES
    assert len(files) >= MIN_FILES_WITH_STYLE, files
    assert elements >= MIN_STYLE_ELEMENTS
    assert len(preludes) >= MIN_RULES


def test_every_selector_in_the_corpus_parses():
    """No real-world rule may be lost to a parse error."""
    _, _, preludes = SWEEP
    failures, selectors = [], 0
    for name, prelude in preludes:
        source = "".join(str(getattr(t, "value", "")) for t in prelude)
        try:
            parsed = parse_selector_list(prelude)
        except SelectorParseError as error:
            failures.append(f"{name}: {source.strip()[:60]!r} -- {error}")
            continue
        for selector in parsed.selectors:
            assert isinstance(selector, Complex)
            # Every triple is non-negative and finite; the point is that
            # specificity runs over real input at all.
            assert all(n >= 0 for n in specificity(selector))
            selectors += 1
    assert failures == []
    assert selectors >= MIN_SELECTORS


def test_corpus_selectors_are_hashable_and_position_independent():
    """Task H keys rules by their rightmost compound. Every compound the
    corpus produces must survive being put in a dict, and two identical
    selectors from different offsets must land in the same bucket.
    """
    _, _, preludes = SWEEP
    index = {}
    for name, prelude in preludes:
        for selector in parse_selector_list(prelude).selectors:
            index.setdefault(selector.compounds[-1], []).append(name)
    assert index
    a = parse_selector_list(list(CssTokenizer("div > p").tokenize()))
    b = parse_selector_list(list(CssTokenizer("   div>p   ").tokenize()))
    assert a == b and hash(a.selectors[0]) == hash(b.selectors[0])


@pytest.mark.parametrize("src,why", [
    # Deviation 1 -- browser parity against the letter of the spec. Blink
    # and Gecko both lex `~=` at the character level; the spec says a
    # comment here has no effect on parsing. We follow the engines.
    ('[a~/**/="v"]', "comment inside a match operator"),
    ('[a ~ = "v"]', "whitespace inside a match operator"),
    # Deviation 4 -- namespaces need @namespace, which nothing interprets.
    ("ns|div", "namespace prefix"),
    ("*|div", "namespace prefix on the universal selector"),
    ("[ns|a]", "namespace prefix on an attribute name"),
    ("p||a", "column combinator"),
    # Deviation 7 -- stricter than the grammar, deliberately.
    ("::before::after", "stacked pseudo-elements"),
    ("::before.c", "a class after a pseudo-element"),
    # Deviation 6, and the compound grammar of section 4.3.
    ("::part(x)", "functional pseudo-element"),
    ("[a]div", "a type selector that does not lead its compound"),
    # `>>` was removed from Selectors 4 before CR.
    ("p >> a", "the dropped >> combinator"),
    # A hash token whose value is not an ident is not an id selector.
    ("#0f0", "a non-ident hash"),
])
def test_strict_forms_the_corpus_licenses_are_still_rejected(src, why):
    """Each of these is a decision to be stricter than something -- the
    spec, or a plausible reading of it. The corpus sweep above is the
    evidence that being this strict costs nothing on real pages; this is
    the guard that keeps the two facts together.
    """
    with pytest.raises(SelectorParseError):
        parse_selector_list(list(CssTokenizer(src).tokenize()))
