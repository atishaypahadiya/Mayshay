"""
Tests for `mayshay.cssparse.matching`: selector matching and rule indexing.

Everything down to `# -- additional discrimination tests --` is transcribed
verbatim from the Task H brief. Everything after it was added because several
of the brief's tests pass against a plausible wrong implementation -- most of
all `test_rule_index_narrows_candidates`, whose `<` holds for an index that
silently *drops* rules, including the ones it must never drop. See the task
report for which of these were verified by injecting the bug they exist to
catch.
"""

import pytest
from mayshay.cssparse.matching import RuleIndex, matches
from mayshay.cssparse.selectors import parse_selector_list
from mayshay.cssparse.tokenizer import CssTokenizer
from mayshay.dom.node import Comment, Element, Text, annotate_positions
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


# -- additional discrimination tests ---------------------------------------

# A wider tree than the brief's: sibling runs with whitespace between them,
# links with and without href, empty and not-quite-empty elements, and a
# nested pair of `.x` divs whose *outer* one is the one with a `div` parent.
WIDE_HTML = """<!DOCTYPE html><html lang="en-GB"><body>
<div id="Main" class="box  wide"><p>one</p><p class="lead">two</p><span>three</span></div>
<ul><li>a</li> <li class="sel">b</li> <li>c</li><li>d</li></ul>
<a href="/x">link</a><a name="anchor">plain</a>
<input type="TEXT"><em></em><em>  </em><em><b></b></em>
<div><div class="x"><section><div class="x"><q>deep</q></div></section></div></div>
</body></html>"""


def wide(annotate=True):
    doc = parse(WIDE_HTML)
    if annotate:
        annotate_positions(doc)
    return doc


def find_all(doc, tag):
    out = []
    stack = [doc]
    while stack:
        n = stack.pop()
        if getattr(n, "tag_name", None) == tag:
            out.append(n)
        stack.extend(reversed(n.children))
    return out


def all_elements(doc):
    out = []
    stack = [doc]
    while stack:
        n = stack.pop()
        if isinstance(n, Element):
            out.append(n)
        stack.extend(reversed(n.children))
    return out


# -- simple selectors --


def test_type_selector_does_not_match_another_element():
    doc = tree()
    assert not matches(find(doc, "span"), sel("p"))
    assert not matches(find(doc, "div"), sel("p"))


def test_class_matching_is_case_sensitive():
    """The other half of the asymmetry `test_type_matching_is_case_insensitive`
    only shows one side of: names fold, values do not.
    """
    doc = tree()
    assert matches(find(doc, "div"), sel(".box"))
    assert not matches(find(doc, "div"), sel(".BOX"))
    assert not matches(find(doc, "div"), sel(".Box"))


def test_class_list_splits_on_whitespace_runs():
    """`class="box  wide"` has two spaces. `.wide` must still match, and the
    empty string between them must not become a class.
    """
    doc = tree()
    assert matches(find(doc, "div"), sel(".wide"))
    assert not matches(find(doc, "div"), sel(".box\\ \\ wide"))


def test_id_selector_does_not_match_an_element_without_one():
    doc = tree()
    assert not matches(find(doc, "p"), sel("#Main"))


def test_universal_selector_matches_every_element():
    doc = wide()
    elements = all_elements(doc)
    assert len(elements) > 10
    assert all(matches(el, sel("*")) for el in elements)


def test_compound_requires_every_simple():
    doc = tree()
    div = find(doc, "div")
    assert matches(div, sel("div#Main.box.wide"))
    assert not matches(div, sel("div#Main.box.narrow"))
    assert not matches(div, sel("span#Main.box.wide"))
    assert not matches(find(doc, "p", 1), sel("p.lead#nope"))
    assert matches(find(doc, "p", 1), sel("p.lead"))
    assert not matches(find(doc, "p"), sel("p.lead"))


def test_non_element_nodes_match_nothing():
    doc = tree()
    text = find(doc, "p").children[0]
    assert isinstance(text, Text)
    assert not matches(text, sel("*"))
    assert not matches(doc, sel("*"))
    assert not matches(Comment("x"), sel("*"))


def test_matches_rejects_a_selector_list():
    """A boolean for a whole list would not say which selector matched, and
    the cascade needs that to get a specificity. Deviation 1.
    """
    listed = parse_selector_list(list(CssTokenizer("p, .a").tokenize()))
    with pytest.raises(TypeError):
        matches(find(tree(), "p"), listed)


# -- combinators --


def test_descendant_matches_a_distant_ancestor():
    doc = wide()
    q = find_all(doc, "q")[0]
    assert matches(q, sel("body q"))
    assert matches(q, sel("html q"))
    assert matches(q, sel("section q"))
    assert not matches(q, sel("p q"))


def test_child_combinator_rejects_a_grandchild():
    doc = wide()
    q = find_all(doc, "q")[0]
    assert matches(q, sel("div > q"))
    assert not matches(q, sel("section > q"))
    assert not matches(q, sel("body > q"))


def test_descendant_backtracks_past_the_first_matching_ancestor():
    """`div > .x q` matches only if the walk keeps going after the *nearest*
    `.x` ancestor fails its own `div >` test.

    The tree is `div > div.x > section > div.x > q`. Walking up from `q`,
    the first ancestor matching `.x` is the inner one, whose parent is a
    `section` -- so that branch fails. The outer `.x`, two levels further
    up, does have a `div` parent. An implementation that commits to the
    first matching ancestor returns False here.
    """
    doc = wide()
    q = find_all(doc, "q")[0]
    assert matches(q, sel("div > .x q"))


def test_adjacent_combinator_skips_text_nodes():
    """`<li>a</li> <li>b</li>` has a text node between the two. `+` counts
    element siblings, so it must still match.
    """
    doc = wide()
    lis = find_all(doc, "li")
    assert [li.attrs.get("class") for li in lis] == [None, "sel", None, None]
    assert matches(lis[1], sel("li + li"))
    assert not matches(lis[0], sel("li + li"))


def test_adjacent_combinator_is_not_general_sibling():
    doc = wide()
    lis = find_all(doc, "li")
    assert matches(lis[2], sel(".sel + li"))
    assert not matches(lis[3], sel(".sel + li"))


def test_general_sibling_reaches_past_the_adjacent_one():
    doc = wide()
    lis = find_all(doc, "li")
    assert matches(lis[2], sel(".sel ~ li"))
    assert matches(lis[3], sel(".sel ~ li"))
    assert not matches(lis[0], sel(".sel ~ li"))
    assert not matches(lis[1], sel(".sel ~ li"))


def test_sibling_combinators_only_look_backwards():
    doc = tree()
    assert not matches(find(doc, "span"), sel("span ~ p"))
    assert not matches(find(doc, "p"), sel("span + p"))
    assert not matches(find(doc, "p"), sel("span ~ p"))


def test_combinators_do_not_cross_the_parent_boundary():
    """The first `li` and the `span` are not siblings, and neither `+` nor
    `~` may pretend otherwise by walking the whole document.
    """
    doc = wide()
    assert not matches(find_all(doc, "li")[0], sel("span + li"))
    assert not matches(find_all(doc, "li")[0], sel("span ~ li"))


def test_a_long_chain_of_combinators():
    doc = wide()
    assert matches(find_all(doc, "q")[0], sel("html > body div div.x section > div q"))
    assert not matches(find_all(doc, "q")[0], sel("html > body > div.x section > div q"))


# -- attribute selectors --


@pytest.mark.parametrize("src,expected", [
    ("[id]", True),
    ("[href]", False),
    ('[id="Main"]', True),
    ('[id="main"]', False),
    ('[class~="wide"]', True),
    ('[class~="box"]', True),
    ('[class~="box  wide"]', False),
    ('[class~=""]', False),
    ('[class^="box"]', True),
    ('[class^="wide"]', False),
    ('[class^=""]', False),
    ('[class$="wide"]', True),
    ('[class$=""]', False),
    ('[class*="  "]', True),
    ('[class*="zz"]', False),
    ('[class*=""]', False),
    ('[id|="Main"]', True),
    ('[id|="Ma"]', False),
    ('[id="MAIN" i]', True),
    ('[id="Main" s]', True),
    ('[id="MAIN" s]', False),
])
def test_attribute_operators(src, expected):
    assert matches(find(tree(), "div"), sel(src)) is expected


def test_dashmatch_matches_a_hyphenated_prefix():
    doc = wide()
    html = find_all(doc, "html")[0]
    assert matches(html, sel('[lang|="en"]'))
    assert matches(html, sel('[lang|="en-GB"]'))
    assert not matches(html, sel('[lang|="e"]'))


def test_html_case_insensitive_attributes_ignore_value_case():
    """`[type="text"]` matching `type="TEXT"` is not sloppiness: the HTML
    Standard lists `type` among the attributes whose selector comparison is
    ASCII case-insensitive, and every browser does this. `id` is not on that
    list. Deviation 4.
    """
    doc = wide()
    field = find_all(doc, "input")[0]
    assert matches(field, sel('[type="text"]'))
    assert matches(field, sel('[type="TEXT"]'))
    assert not matches(field, sel('[type="text" s]'))
    assert not matches(find(tree(), "div"), sel('[id="MAIN"]'))


def test_attribute_names_fold_but_values_do_not():
    doc = tree()
    assert matches(find(doc, "div"), sel("[ID]"))
    assert matches(find(doc, "div"), sel('[ID="Main"]'))
    assert not matches(find(doc, "div"), sel('[ID="MAIN"]'))


# -- structural pseudo-classes --


@pytest.mark.parametrize("formula,expected", [
    ("1", [0]),
    ("2", [1]),
    ("odd", [0, 2]),
    ("even", [1, 3]),
    ("2n", [1, 3]),
    ("2n+1", [0, 2]),
    ("n", [0, 1, 2, 3]),
    ("n+2", [1, 2, 3]),
    ("-n+2", [0, 1]),
    ("3n-1", [1]),
    ("0n+3", [2]),
    ("banana", []),
    ("2 of .sel", []),
])
def test_nth_child_formulas(formula, expected):
    doc = wide()
    lis = find_all(doc, "li")
    selector = sel(f"li:nth-child({formula})")
    assert [i for i, li in enumerate(lis) if matches(li, selector)] == expected


def test_nth_child_works_without_annotate_positions():
    """`element_index` is None until `annotate_positions` runs. A matcher
    that read it blindly would treat every element as the first child.
    """
    doc = wide(annotate=False)
    lis = find_all(doc, "li")
    assert all(li.element_index is None for li in lis)
    assert [i for i, li in enumerate(lis) if matches(li, sel("li:nth-child(2)"))] == [1]
    assert [i for i, li in enumerate(lis) if matches(li, sel("li:first-child"))] == [0]


def test_nth_child_counts_elements_not_nodes():
    """The `li`s have text nodes between them; `:nth-child(3)` is the third
    *element*, not the third node.
    """
    doc = wide()
    lis = find_all(doc, "li")
    assert matches(lis[2], sel("li:nth-child(3)"))
    assert not matches(lis[2], sel("li:nth-child(5)"))


def test_nth_last_child():
    doc = wide()
    lis = find_all(doc, "li")
    assert [i for i, li in enumerate(lis) if matches(li, sel("li:nth-last-child(1)"))] == [3]
    assert [i for i, li in enumerate(lis) if matches(li, sel("li:nth-last-child(2)"))] == [2]
    assert [i for i, li in enumerate(lis) if matches(li, sel("li:last-child"))] == [3]


def test_first_last_only_child():
    doc = wide()
    lis = find_all(doc, "li")
    assert [i for i, li in enumerate(lis) if matches(li, sel(":first-child"))] == [0]
    assert [i for i, li in enumerate(lis) if matches(li, sel(":last-child"))] == [3]
    assert not any(matches(li, sel(":only-child")) for li in lis)
    assert matches(find_all(doc, "q")[0], sel(":only-child"))


def test_of_type_pseudo_classes_count_only_the_same_tag():
    """The `div#Main` children are p, p, span. `span:first-of-type` matches
    even though the span is the third child, which is what separates
    `-of-type` from `-child`.
    """
    doc = tree()
    span = find(doc, "span")
    assert matches(span, sel("span:first-of-type"))
    assert matches(span, sel("span:last-of-type"))
    assert matches(span, sel("span:only-of-type"))
    assert not matches(span, sel("span:first-child"))
    assert matches(find(doc, "p"), sel("p:first-of-type"))
    assert not matches(find(doc, "p"), sel("p:last-of-type"))
    assert matches(find(doc, "p", 1), sel("p:nth-of-type(2)"))
    assert matches(find(doc, "p"), sel("p:nth-last-of-type(2)"))
    assert not matches(find(doc, "p", 1), sel("p:only-of-type"))


def test_root_is_the_html_element_only():
    doc = wide()
    roots = [el for el in all_elements(doc) if matches(el, sel(":root"))]
    assert [el.tag_name for el in roots] == ["html"]


def test_empty_ignores_whitespace_but_not_elements():
    """Level 4's `:empty`: whitespace-only text does not defeat it, an
    element child does. Deviation 11.
    """
    doc = wide()
    ems = find_all(doc, "em")
    assert [matches(em, sel("em:empty")) for em in ems] == [True, True, False]
    assert not matches(find(tree(), "p"), sel("p:empty"))


def test_link_needs_an_href():
    doc = wide()
    anchors = find_all(doc, "a")
    assert [matches(a, sel(":link")) for a in anchors] == [True, False]
    assert [matches(a, sel(":any-link")) for a in anchors] == [True, False]
    assert not matches(find(tree(), "p"), sel(":link"))


def test_visited_and_dynamic_pseudo_classes_never_match():
    """Deviation 10. `:visited` matching would leak history through style;
    the rest need a browsing context this engine has none of.
    """
    doc = wide()
    for src in (":visited", ":hover", ":focus", ":active", ":target",
                ":checked", ":unheard-of", ":has(q)"):
        assert not any(matches(el, sel(src)) for el in all_elements(doc)), src


def test_pseudo_elements_never_match_an_element():
    """`p::before` selects a box, not the `p`. Deviation 9."""
    doc = tree()
    assert not matches(find(doc, "p"), sel("p::before"))
    assert not matches(find(doc, "p"), sel("p:before"))
    assert matches(find(doc, "p"), sel("p"))


# -- logical combination --


def test_not_is_and_where():
    doc = tree()
    first, second = find(doc, "p"), find(doc, "p", 1)
    assert matches(first, sel("p:not(.lead)"))
    assert not matches(second, sel("p:not(.lead)"))
    assert matches(second, sel(":is(.lead, .missing)"))
    assert not matches(first, sel(":is(.lead, .missing)"))
    assert matches(second, sel(":where(.lead)"))
    assert matches(first, sel(":not(.lead, #nope)"))
    assert not matches(second, sel(":not(.lead, #nope)"))


def test_not_takes_a_complex_argument():
    doc = tree()
    assert not matches(find(doc, "p"), sel(":not(div p)"))
    assert matches(find(doc, "div"), sel(":not(div p)"))


# -- RuleIndex --

INDEX_RULES = (
    "#Main", "#other", ".lead", ".box", ".missing", "span", "p", "a", "b",
    "i", "div p", "*", "[id]", ":is(.lead, span)", "p::before", "div.box",
)


def index_over(sources=INDEX_RULES):
    rules = [sel(s) for s in sources]
    return rules, RuleIndex(rules)


def test_rule_index_returns_the_catch_all_bucket_for_every_element():
    """A rightmost compound with no id, class or type -- `*`, `[id]`,
    `:is(...)` -- has no usable key and must be considered for every
    element. Dropping those is a correctness bug that
    `test_rule_index_narrows_candidates` would happily reward.
    """
    rules, index = index_over()
    catch_all = [sel("*"), sel("[id]"), sel(":is(.lead, span)")]
    for element in all_elements(wide()):
        got = index.candidates(element)
        for rule in catch_all:
            assert rule in got, (element.tag_name, rule)


def test_rule_index_candidates_are_exactly_the_reachable_rules():
    rules, index = index_over()
    span = find(tree(), "span")
    assert index.candidates(span) == [
        sel("span"), sel("*"), sel("[id]"), sel(":is(.lead, span)"),
    ]
    div = find(tree(), "div")
    assert index.candidates(div) == [
        sel("#Main"), sel(".box"), sel("*"), sel("[id]"),
        sel(":is(.lead, span)"), sel("div.box"),
    ]


def test_rule_index_files_a_rule_under_its_rightmost_compound():
    """`div p` is a `p` rule, not a `div` rule. Keying on the *leftmost*
    compound is the plausible wrong implementation, and it silently loses
    every descendant rule.
    """
    rules, index = index_over()
    assert sel("div p") in index.candidates(find(tree(), "p"))
    assert sel("div p") not in index.candidates(find(tree(), "div"))


def test_rule_index_never_drops_a_rule_that_matches():
    """The invariant the whole optimisation rests on: `candidates` is a
    superset of the rules that actually match. Checked over every element of
    the wider tree against every rule, so a bucketing mistake anywhere shows
    up here rather than in whichever single case a hand-written test picked.
    """
    rules, index = index_over()
    elements = all_elements(wide())
    assert len(elements) > 15
    total = 0
    for element in elements:
        got = index.candidates(element)
        total += len(got)
        for rule in rules:
            if matches(element, rule):
                assert rule in got, (element.tag_name, rule)
    # And it is still an optimisation: far fewer tests than the product.
    assert total < len(rules) * len(elements) / 2


def test_rule_index_returns_rules_in_construction_order():
    """`class_list` is a frozenset, so a candidates list assembled bucket by
    bucket is not even stable between runs. Deviation 13.
    """
    sources = ("p", ".box", "#Main", "*", "div", ".wide", "[id]")
    rules, index = index_over(sources)
    div = find(tree(), "div")
    got = index.candidates(div)
    assert got == [rules[i] for i in sorted(rules.index(r) for r in got)]
    assert got == [sel(".box"), sel("#Main"), sel("*"), sel("div"),
                   sel(".wide"), sel("[id]")]


def test_rule_index_prefers_the_id_key_over_class_and_type():
    """Filing `div#Main.box` under `div` would work but would put it in the
    largest bucket. It goes under the id, and is still found.
    """
    rules, index = index_over(("div#Main.box",))
    assert index.candidates(find(tree(), "div")) == rules
    assert index.candidates(find(tree(), "p")) == []
    assert index.candidates(find(tree(), "span")) == []


def test_rule_index_handles_duplicate_and_repeated_keys():
    rules, index = index_over(("p", "p", "p.lead", ".lead"))
    assert index.candidates(find(tree(), "p", 1)) == rules
    # The first `p` has no class, so the two `.lead`-keyed rules -- including
    # the compound `p.lead`, filed under its class and not its type -- are
    # correctly absent.
    assert index.candidates(find(tree(), "p")) == rules[:2]


def test_rule_index_accepts_a_selector_of_hook():
    class Rule:
        def __init__(self, selector):
            self.selector = selector

    payloads = [Rule(sel("p")), Rule(sel("span"))]
    index = RuleIndex(payloads)
    assert index.candidates(find(tree(), "p")) == [payloads[0]]

    pairs = [(sel("p"), "one"), (sel("span"), "two")]
    index = RuleIndex(pairs, selector_of=lambda pair: pair[0])
    assert index.candidates(find(tree(), "span")) == [pairs[1]]


def test_rule_index_rejects_a_selector_list():
    listed = parse_selector_list(list(CssTokenizer("p, .a").tokenize()))
    with pytest.raises(TypeError):
        RuleIndex([listed])
    with pytest.raises(TypeError):
        RuleIndex(["not a selector"])


def test_rule_index_of_nothing():
    index = RuleIndex([])
    assert len(index) == 0
    assert index.candidates(find(tree(), "p")) == []


def test_rule_index_candidates_of_a_non_element_is_empty():
    index = RuleIndex([sel("*")])
    assert index.candidates(Text("x")) == []
