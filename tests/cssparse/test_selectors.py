"""
Tests for `mayshay.cssparse.selectors`: Selectors 4 parsing and the (a, b, c)
specificity triple. Everything down to `# -- additional discrimination
tests --` is transcribed verbatim from the Task G brief; everything after it
was added because several of the brief's tests pass against a plausible
wrong implementation -- `test_attribute_operators` asserts only
`is not None`, so it passes against a parser that ignores the `=` half of
`~=` entirely, and nothing in the brief distinguishes `a b` from `ab` by
structure. See the task report for which of these were verified by injecting
the bug they are meant to catch.
"""

import pytest
from mayshay.cssparse.selectors import (
    AttributeSelector,
    ClassSelector,
    Compound,
    IdSelector,
    PseudoClassSelector,
    PseudoElementSelector,
    SelectorList,
    SelectorParseError,
    TypeSelector,
    UniversalSelector,
    parse_selector_list,
    specificity,
)
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


# -- additional discrimination tests --------------------------------------


def simples(src, index=0):
    """The simple selectors of one compound of the first selector."""
    return sel(src).selectors[0].compounds[index].simples


# Whitespace. The brief's two whitespace tests are satisfied by an
# implementation that strips whitespace and one that keeps too much of it, so
# each direction is pinned by structure and not only by a combinator list.


def test_whitespace_separated_idents_are_two_compounds():
    """`a b` is a descendant combinator; `ab` is one type selector.

    A parser that filters `Whitespace` before parsing cannot tell these
    apart -- it sees the same token sequence for both.
    """
    spaced = sel("a b").selectors[0]
    joined = sel("ab").selectors[0]
    assert [c.simples for c in spaced.compounds] == [
        [TypeSelector("a")], [TypeSelector("b")]
    ]
    assert spaced.combinators == [" "]
    assert [c.simples for c in joined.compounds] == [[TypeSelector("ab")]]
    assert joined.combinators == []


def test_whitespace_around_an_explicit_combinator_is_absorbed():
    """No spurious descendant combinator on either side of `>`.

    A parser that turns every whitespace run into a descendant combinator
    produces four compounds and `[' ', '>', ' ']` here.
    """
    spaced = sel("div > p").selectors[0]
    assert spaced.combinators == [">"]
    assert len(spaced.compounds) == 2
    assert sel("div > p") == sel("div>p") == sel("div\n\t>\n\tp")


def test_whitespace_around_commas_is_not_a_combinator():
    for src in ("a,b", "a , b", "a ,b\n, c"):
        for selector in sel(src).selectors:
            assert selector.combinators == []
            assert len(selector.compounds) == 1


def test_descendant_chain_length():
    s = sel("a b c d").selectors[0]
    assert s.combinators == [" ", " ", " "]
    assert [c.simples[0].name for c in s.compounds] == ["a", "b", "c", "d"]


def test_compound_keeps_its_simples_in_order():
    assert simples("p.c#i[href]:hover") == [
        TypeSelector("p"),
        ClassSelector("c"),
        IdSelector("i"),
        AttributeSelector("href"),
        PseudoClassSelector("hover"),
    ]


def test_class_and_id_keep_source_case_but_type_is_folded():
    """HTML folds element and attribute names, not class or id values."""
    assert simples("DIV.Box#Main[HREF]") == [
        TypeSelector("div"),
        ClassSelector("Box"),
        IdSelector("Main"),
        AttributeSelector("href"),
    ]


# Attribute selectors. The brief only asserts the parse produced *something*,
# which a parser that reads `~` as the operator and leaves `=` to be
# mis-parsed as part of the value also satisfies.


@pytest.mark.parametrize("op", ["=", "~=", "|=", "^=", "$=", "*="])
def test_attribute_operator_and_value_are_captured(op):
    assert simples(f'[a{op}"v"]') == [AttributeSelector("a", op, "v")]
    assert simples(f"[a{op}v]") == [AttributeSelector("a", op, "v")]


def test_attribute_presence_has_no_operator_or_value():
    assert simples("[href]") == [AttributeSelector("href", None, None, None)]


def test_whitespace_is_allowed_around_an_operator_but_not_inside_it():
    """`~=` was one token in the 2014 CR and behaves like one still: the two
    delims we join must be adjacent in the source.
    """
    assert simples('[a ~= "v"]') == [AttributeSelector("a", "~=", "v")]
    with pytest.raises(SelectorParseError):
        sel('[a ~ = "v"]')
    # A comment separates tokens exactly as whitespace does, and the
    # tokenizer has already dropped it -- so the two delims are adjacent in
    # the token list and only their source positions say otherwise.
    with pytest.raises(SelectorParseError):
        sel('[a~/**/="v"]')


def test_attribute_case_sensitivity_flag():
    assert simples('[a="v" i]') == [AttributeSelector("a", "=", "v", "i")]
    assert simples('[a="v" S]') == [AttributeSelector("a", "=", "v", "s")]
    assert simples('[a="v"]').pop().case is None


def test_attribute_value_must_be_a_string_or_ident():
    for src in ("[a=1]", "[a=]", "[a==b]", "[a", "[a=b", "[=b]"):
        with pytest.raises(SelectorParseError):
            sel(src)


def test_attribute_selector_does_not_end_the_whole_compound():
    assert len(simples("[a][b]:hover")) == 3


# Pseudo-classes and pseudo-elements.


def test_pseudo_element_counts_in_c_not_b():
    assert specificity(sel("p::before").selectors[0]) == (0, 0, 2)
    assert simples("p::before")[1] == PseudoElementSelector("before")


def test_legacy_one_colon_pseudo_elements():
    """`:before` is a pseudo-element, not a pseudo-class: (0, 0, 1)."""
    for name in ("before", "after", "first-line", "first-letter"):
        assert simples(f":{name}") == [PseudoElementSelector(name)]
        assert specificity(sel(f":{name}").selectors[0]) == (0, 0, 1)
    # ...but an ordinary pseudo-class with one colon still is one.
    assert simples(":hover") == [PseudoClassSelector("hover")]
    assert specificity(sel(":hover").selectors[0]) == (0, 1, 0)


def test_functional_pseudo_class_keeps_its_raw_argument():
    simple = simples("li:nth-child(2n + 1)")[1]
    assert simple.name == "nth-child"
    assert simple.selectors is None
    # The raw run between the parens, delimiters excluded and whitespace kept.
    assert [type(t).__name__ for t in simple.argument] == [
        "Dimension", "Whitespace", "Delim", "Whitespace", "Number"
    ]


def test_pseudo_names_are_case_insensitive():
    assert simples(":HOVER") == [PseudoClassSelector("hover")]
    assert simples("::BEFORE") == [PseudoElementSelector("before")]


def test_not_parses_its_argument_as_a_selector_list():
    simple = simples("a:not(b, .c)")[1]
    assert isinstance(simple.selectors, SelectorList)
    assert len(simple.selectors.selectors) == 2


@pytest.mark.parametrize("src,expected", [
    (":not(.c)", (0, 1, 0)),
    (":not(#i, .c)", (1, 0, 0)),
    (":not(p)", (0, 0, 1)),
    (":is(#i, p)", (1, 0, 0)),
    (":where(#i, p)", (0, 0, 0)),
    ("p:where(#i)", (0, 0, 1)),
])
def test_specificity_of_selector_taking_pseudo_classes(src, expected):
    """Selectors 4 section 17: `:not()`/`:is()` take the specificity of their
    most specific argument; `:where()` contributes nothing.
    """
    assert specificity(sel(src).selectors[0]) == expected


def test_is_and_where_are_forgiving_but_not_is_not():
    """`:is()`/`:where()` take a <forgiving-selector-list>; `:not()` does
    not, so a bad argument invalidates the whole selector.
    """
    assert len(simples(":is(p, %%bad%%)")[0].selectors.selectors) == 1
    assert simples(":is(%%bad%%)")[0].selectors.selectors == []
    with pytest.raises(SelectorParseError):
        sel(":not(%%bad%%)")


def test_nested_pseudo_class_arguments():
    assert len(sel("a:not(b:not(.c))").selectors) == 1
    assert len(sel("a:not(b, c):hover, d").selectors) == 2


# Comma splitting.


def test_commas_inside_brackets_and_strings_do_not_split():
    assert len(sel('[title="a,b"]').selectors) == 1
    assert len(sel("a:nth-child(2), b").selectors) == 2
    assert len(sel("a:not(b, c), d, e").selectors) == 3


def test_every_selector_in_a_list_is_parsed_not_just_the_first():
    """A splitter that parses only the head would let `a, >b` through."""
    with pytest.raises(SelectorParseError):
        sel("a, >b")
    assert [s.compounds[0].simples for s in sel("a, .b, #c").selectors] == [
        [TypeSelector("a")], [ClassSelector("b")], [IdSelector("c")]
    ]


# Invalid selectors. The brief tests one; these are the neighbours of it.


@pytest.mark.parametrize("src", [
    "p >> a",       # `>>` was dropped from Selectors 4 before CR
    "p > > a",
    "p >",
    "> p",
    "~ p",
    "p ~~ a",
    "a,,b",
    "a,",
    ",a",
    "",
    "   ",
    "p 5",
    'p"x"',
    "p||a",         # the column combinator is not supported
    "ns|div",       # nor are namespaces
    "*|div",
    "[ns|a]",
    "#0f0",         # a hash token, but not a valid id selector
    "[a]div",       # a type selector must lead its compound
    ".c*",
    "::before.c",   # only pseudo-classes may follow a pseudo-element
    "::before::after",
    "::part(x)",    # functional pseudo-elements are unsupported
    ": hover",
    ".",
    ".5",
    "p:",
    "p:(a)",
    "a:not(b",
])
def test_invalid_selectors_raise(src):
    with pytest.raises(SelectorParseError):
        sel(src)


def test_the_error_is_a_valueerror_carrying_a_position():
    with pytest.raises(ValueError) as excinfo:
        sel("p >> a")
    assert isinstance(excinfo.value, SelectorParseError)
    assert excinfo.value.pos == 3


# Input shapes and the `specificity` contract.


def test_a_prelude_without_a_trailing_eof_token_parses_identically():
    """`QualifiedRule.prelude` is a slice with no `EOFToken`; `tokenize()`
    ends with one. Both must produce the same selector list.
    """
    from mayshay.cssparse.parser import parse_stylesheet

    rule = parse_stylesheet("div > p, .c { color: red }")[0]
    assert parse_selector_list(rule.prelude) == sel("div > p, .c")


def test_leading_and_trailing_whitespace_is_not_a_combinator():
    assert sel("  div > p  ") == sel("div>p")
    assert sel("\n a , b \n") == sel("a,b")


def test_specificity_accepts_simple_and_compound_selectors():
    assert specificity(IdSelector("i")) == (1, 0, 0)
    assert specificity(UniversalSelector()) == (0, 0, 0)
    assert specificity(Compound([TypeSelector("p"), ClassSelector("c")])) == (0, 1, 1)


def test_specificity_rejects_a_selector_list():
    """A list has no single specificity -- the cascade compares one selector
    at a time.
    """
    with pytest.raises(TypeError):
        specificity(sel("a, b"))


def test_bare_where_is_an_unknown_pseudo_class_not_the_functional_one():
    """Only the *functional* `:where()` has zero specificity (Selectors 4
    section 17). A bare `:where`, with no argument, is just an unknown
    pseudo-class that will never match, and counts (0, 1, 0) like any
    other. `selectors is not None` -- not the name -- is the test for
    "written with an argument list".
    """
    assert specificity(sel(":where").selectors[0]) == (0, 1, 0)
    assert specificity(sel(":where()").selectors[0]) == (0, 0, 0)
    assert specificity(sel(":where(a)").selectors[0]) == (0, 0, 0)
    assert specificity(sel(":not").selectors[0]) == (0, 1, 0)
    assert specificity(sel(":is").selectors[0]) == (0, 1, 0)


def test_matches_is_an_alias_for_is():
    """The pre-`:is()` spelling, still shipped everywhere -- same nested
    parse, same specificity, same forgiving argument list.
    """
    assert specificity(sel(":matches(#i, p)").selectors[0]) == (1, 0, 0)
    assert len(simples(":matches(p, %%bad%%)")[0].selectors.selectors) == 1


def test_unterminated_functional_pseudo_element_blames_the_right_thing():
    """`::part(x` is rejected because `::part()` is unsupported, not
    because its argument is unterminated -- it is not a pseudo-class and
    its argument is not why we reject it.
    """
    for src in ("::part(x)", "::part(x"):
        with pytest.raises(SelectorParseError) as excinfo:
            sel(src)
        assert "functional pseudo-element" in str(excinfo.value)
    # ...but a real unterminated pseudo-*class* argument still says so.
    with pytest.raises(SelectorParseError) as excinfo:
        sel(":not(a")
    assert "unterminated" in str(excinfo.value)


# Equality and hashing -- deviation 10. Task H keys rules by their rightmost
# compound, so these are load-bearing, not cosmetic.


def test_pos_is_excluded_from_equality_but_still_recorded():
    assert sel("p") == sel("   p")
    assert sel("p").selectors[0].pos == 0
    assert sel("   p").selectors[0].pos == 3
    assert sel("p").selectors[0].compounds[0].pos == 0
    assert sel("   p").selectors[0].compounds[0].pos == 3


@pytest.mark.parametrize("src", [
    "*", "p", ".c", "#i", "[a]", '[a~="v" i]', ":hover", ":nth-child(2n+1)",
    ":not(.a, #b)", "::before", "div > p .c + a", "a, b, c",
])
def test_every_selector_structure_is_hashable(src):
    """A plain `@dataclass` with `eq=True` sets `__hash__` to None; each
    structure defines its own.
    """
    parsed = sel(src)
    hash(parsed)
    for selector in parsed.selectors:
        hash(selector)
        for compound in selector.compounds:
            hash(compound)
            for simple in compound.simples:
                hash(simple)


def test_equal_selectors_hash_equal_and_key_the_same_dict_entry():
    a, b = sel("  div > p.c  ").selectors[0], sel("div>p.c").selectors[0]
    assert a == b and hash(a) == hash(b)
    assert len({a, b}) == 1
    assert {a: "rule"}[b] == "rule"
    # The rightmost compound is what task H will index on.
    assert {a.compounds[-1]: 1}[sel("span p.c").selectors[0].compounds[-1]] == 1


def test_different_selectors_are_not_conflated_by_the_hash():
    """The hash is allowed to collide; equality is not allowed to."""
    distinct = [sel(s).selectors[0] for s in
                ("a b", "ab", "a > b", "a + b", "a.b", "a#b", "[a]", "[a=b]",
                 ":nth-child(1)", ":nth-child(2)", ":lang(en)", ":lang(fr)",
                 ":hover", ":where", ":where()", ":not(.a)", ":not(.b)")]
    assert len(set(distinct)) == len(distinct)


# The interaction that the pos-independence tests above do NOT reach: a
# functional pseudo-class stores its argument as raw `CssToken`s, and a
# token's own equality includes `pos`. Every test before this one uses type,
# class or attribute compounds, all of which are pos-free by construction --
# so they pass against a parser for which the deviation-10 guarantee is
# false. See the task report's fix round 2.


POSITION_INDEPENDENT = [
    "p",
    "p.c#i",
    "div > p",
    ":hover",                    # non-functional pseudo-class
    ":where",                    # bare, argument is None
    ":where()",                  # functional, argument is empty
    ":lang(en)",                 # raw argument, one token
    ":nth-child(2n + 1)",        # raw argument, five tokens incl. whitespace
    "p:nth-of-type(3)",          # ...in a compound with a type selector
    "li:nth-child(2)",
    ":not(.a)",                  # parsed argument *and* raw tokens
    ":is(#i, p)",
    'div > p:nth-child(2n+1)[a~="v"]',
]


@pytest.mark.parametrize("src", POSITION_INDEPENDENT)
def test_the_same_selector_at_a_different_offset_is_the_same_selector(src):
    """Deviation 10's guarantee, stated at the level it has to hold: not
    just `Compound.pos`, but anything a compound transitively contains.
    """
    here, there = sel(src).selectors[0], sel(f"   {src}").selectors[0]
    assert here == there
    assert hash(here) == hash(there)


@pytest.mark.parametrize("src", POSITION_INDEPENDENT)
def test_a_dict_keyed_on_a_compound_does_not_split_by_offset(src):
    """Task H indexes rules by their rightmost compound. Two stylesheets
    that write the same rule at different offsets must land in one entry,
    or the same rule is applied twice.
    """
    here = sel(src).selectors[0].compounds[-1]
    there = sel(f"   {src}").selectors[0].compounds[-1]
    assert len({here: "a", there: "b"}) == 1
    assert {here: "a"}[there] == "a"
    assert len({sel(src), sel(f"   {src}")}) == 1


def test_a_functional_pseudo_class_still_compares_its_argument():
    """Position-independent must not mean argument-blind: the fix must not
    swing past correct into `:nth-child(1) == :nth-child(2)`.
    """
    assert sel(":nth-child(1)") != sel(":nth-child(2)")
    assert sel(":lang(en)") != sel(":lang(fr)")
    assert sel(":nth-child(2n+1)") != sel(":nth-child(2n + 1)")  # whitespace
    assert sel(":where") != sel(":where()")  # None argument vs empty one
    assert sel(":not(.a)") != sel(":not(.b)")
    assert simples(":hover")[0] != TypeSelector("hover")
    assert simples(":hover")[0] != PseudoElementSelector("hover")


def test_specificity_never_carries_between_columns():
    """Eleven classes are (0, 11, 0), not (1, 1, 0)."""
    assert specificity(sel(".c" * 11).selectors[0]) == (0, 11, 0)
