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

from tests.support.corpus import CORPUS, page_paths

# Floors, not exact counts: re-collecting the corpus should not break the
# build, but losing most of it must. Actuals, unchanged across the
# 2026-08-27 re-collection: 3 HTML files, 2 of them carrying <style> (the
# Hacker News page links its CSS instead and contributes nothing here), 19
# <style> elements, 193 style rules -- 156 top-level and 37 inside @media --
# and 279 selectors.
#
# This sweep sees in-document <style> only. The corpus now also carries 237
# KB of external CSS per docs/corpus.md, which would be far broader
# real-world coverage for "every selector parses" -- worth folding in, but a
# deliberate scope change, not a silent one.
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
    for path in page_paths():
        document = TreeBuilder(path.read_text(errors="replace")).build()
        for node in _walk(document):
            if isinstance(node, Element) and node.tag_name == "style":
                text = "".join(
                    c.data for c in node.children if isinstance(c, Text)
                )
                if text.strip():
                    # The slug, not path.name: every page's file is now
                    # `page.html`, so keying on the filename would count
                    # three pages as one.
                    yield path.parent.name, text


# At-rules whose block contains **style rules**, so a prelude inside one is a
# selector. Everything else is skipped, and the distinction is not cosmetic:
# `@keyframes` holds KEYFRAME selectors (`0%`, `from`, `50%`), `@page` holds
# margin at-rules (`@top-left`), and `@font-face`/`@property`/`@counter-style`
# hold only declarations. None of those is a selector.
#
# The three-page corpus had almost no `@keyframes`. The 79-page survey has
# many, and feeding their `0%` preludes to `parse_selector_list` produced
# **111 failures that looked exactly like a selector-parser gap** -- 1.05% of
# all preludes, on real pages, with plausible error messages. They were
# measurement defects: the sweep was asking the parser about a population
# that did not belong to it. `docs/measurement-hazards.md` instance nineteen
# is the same shape, and CLAUDE.md's rule is the general one -- a comparison
# must distinguish wrong output from wrong input.
CONDITIONAL_GROUP_RULES = frozenset({
    "media", "supports", "layer", "container", "scope", "document",
    "-moz-document",
})


def holds_style_rules(name: str) -> bool:
    """Does this at-rule's block contain style rules (so: selectors)?"""
    return name.lower().lstrip("-").removeprefix("webkit-").removeprefix(
        "moz-"
    ).removeprefix("o-").removeprefix("ms-") in CONDITIONAL_GROUP_RULES or (
        name.lower() in CONDITIONAL_GROUP_RULES
    )


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


def _sweep(prefix=""):
    """(files, style elements, preludes) across the whole corpus.

    `prefix` is prepended to every stylesheet before tokenizing. Whitespace
    at the start of a stylesheet cannot change how it tokenizes, but it
    shifts every token's `pos`, which is how the position-independence test
    below reaches real selectors instead of hand-written ones.
    """
    files, elements, preludes, empty = set(), 0, [], 0
    for name, css in _style_bodies():
        files.add(name)
        elements += 1
        for rule in parse_stylesheet(prefix + css):
            if isinstance(rule, QualifiedRule):
                # A qualified rule with an EMPTY prelude is what the Syntax
                # spec produces for `{ ... }` written with no selector at
                # all. It is a style rule a browser drops as invalid, not a
                # selector the parser failed on -- six of them ship on one
                # corpus page. Counted, not fed to the selector parser.
                if any(not isinstance(t, Whitespace) for t in rule.prelude):
                    preludes.append((name, rule.prelude))
                else:
                    empty += 1
            elif (
                isinstance(rule, AtRule)
                and rule.block is not None
                and holds_style_rules(rule.name)
            ):
                for prelude in _nested_preludes(rule.block):
                    preludes.append((name, prelude))
    return files, elements, preludes, empty


def parsed_or_none(prelude):
    """Parse, or None for a feature this engine deliberately declines.

    `::part()` and `::view-transition-*()` are current CSS that `selectors.py`
    refuses **by name** -- five preludes on the 79-page survey use them. A
    sweep about hashing and position-independence has nothing to say about a
    selector that was never built, and letting the refusal propagate would
    turn "we decline this feature" into a red suite. The test that owns the
    unsupported/invalid distinction is
    `test_every_selector_in_the_corpus_parses`, and it is the only one that
    should fail when that distinction changes.
    """
    try:
        return parse_selector_list(prelude)
    except SelectorParseError as error:
        if "is not supported" in str(error):
            return None
        raise


SWEEP = _sweep()


def test_the_corpus_sweep_is_not_silently_empty():
    """The failure mode this project keeps hitting: a loader that finds
    nothing and reports success.
    """
    files, elements, preludes, _empty = SWEEP
    assert CORPUS.is_dir()
    # Corpus files and files that carry CSS are counted separately: a page
    # with no <style> is normal (the Hacker News page links its
    # stylesheet), a corpus
    # with no pages is the bug.
    assert len(page_paths()) >= MIN_HTML_FILES
    assert len(files) >= MIN_FILES_WITH_STYLE, files
    assert elements >= MIN_STYLE_ELEMENTS
    assert len(preludes) >= MIN_RULES


def test_every_selector_in_the_corpus_parses():
    """No real-world rule may be lost to a parse error."""
    _, _, preludes, _empty = SWEEP
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
    # **Not `failures == []`.** Five preludes on the 79-page survey use
    # `::part()` and `::view-transition-*()` -- real, current CSS this engine
    # deliberately declines and says so by name. Declining a named feature is
    # correct behaviour; failing to parse ordinary CSS is not, and the two
    # must not share a bucket or the assertion stops meaning anything.
    #
    # This assertion is what a wider corpus is FOR: it read 123 failures at
    # 1.05% of preludes when the survey landed, and 111 of those were
    # `@keyframes` selectors the sweep should never have collected. See
    # `holds_style_rules` above.
    unsupported = [f for f in failures if "is not supported" in f]
    assert failures == unsupported, "genuine selector parse failures:\n  " + (
        "\n  ".join(f for f in failures if f not in unsupported)
    )
    assert selectors >= MIN_SELECTORS


def test_corpus_selectors_are_hashable():
    """Task H keys rules by their rightmost compound. Every compound the
    corpus produces must survive being put in a dict.
    """
    _, _, preludes, _empty = SWEEP
    index = {}
    for name, prelude in preludes:
        parsed = parsed_or_none(prelude)
        if parsed is None:
            continue
        for selector in parsed.selectors:
            index.setdefault(selector.compounds[-1], []).append(name)
    assert index


def test_corpus_selectors_are_position_independent():
    """The whole corpus, parsed twice from sources offset against each
    other: every selector must compare and hash the same, and every
    rightmost compound must land in one dict entry.

    Hand-written pos-independence tests only reach the shapes someone
    thought to write. This reaches the 20 functional pseudo-classes the
    corpus actually ships -- `:not(.notheme)` and friends -- whose raw
    argument tokens carry a `pos` of their own, which is exactly the
    interaction that made the first version of deviation 10 false.
    """
    _, _, here, _ = SWEEP
    _, _, there, _ = _sweep("\n\n")
    assert len(here) == len(there) >= MIN_RULES
    pairs = 0
    for (name, a), (_, b) in zip(here, there):
        first, second = parsed_or_none(a), parsed_or_none(b)
        if first is None or second is None:
            # Both must decline, or the refusal itself is position-dependent.
            assert first is second, name
            continue
        assert first == second, name
        for x, y in zip(first.selectors, second.selectors):
            assert hash(x) == hash(y)
            assert len({x.compounds[-1]: 1, y.compounds[-1]: 2}) == 1
            pairs += 1
    assert pairs >= MIN_SELECTORS


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
