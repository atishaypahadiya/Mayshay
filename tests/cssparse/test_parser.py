"""
Tests for `mayshay.cssparse.parser`: the css-syntax-3 section 5 generic
grammar. The first ten tests are transcribed verbatim from the Task F brief;
everything after `# -- additional discrimination tests --` was added because
several of the brief's tests pass even against a plausible wrong
implementation (e.g. one that drops an entire malformed rule/at-rule, or one
that brace-matches naively) -- see the task report for which.
"""

from mayshay.cssparse.parser import (
    AtRule, CssParser, Declaration, QualifiedRule, parse_declarations,
    parse_stylesheet,
)
from mayshay.cssparse.tokenizer import CssTokenizer, EOFToken


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


# -- additional discrimination tests --------------------------------------


def test_qualified_rule_prelude_is_a_token_list():
    """This layer knows nothing about selectors: the prelude is exactly the
    prelude tokens, untouched, not a parsed selector object.
    """
    rule = parse_stylesheet("p.cls { color: red }")[0]
    assert [type(t).__name__ for t in rule.prelude] == [
        "Ident", "Delim", "Ident", "Whitespace",
    ]
    assert rule.prelude[0].value == "p" and rule.prelude[2].value == "cls"


def test_declaration_value_is_a_token_list():
    """Declaration values stay tokens too -- Task I's job, not this one."""
    decls = parse_declarations(parse_stylesheet("p { margin: 0 auto }")[0].block)
    assert [type(t).__name__ for t in decls[0].value] == [
        "Number", "Whitespace", "Ident",
    ]


def test_nested_braces_do_not_end_the_at_rule_block_early():
    """A naive block-consumer that stops at the *first* `}` (rather than
    tracking nesting depth) would end @media's block after `black }`,
    leaving a stray `}` that either becomes spurious content or a second,
    bogus top-level rule. The real spec algorithm recurses through the inner
    `{...}` as a single component value, so the block closes at the matching
    outer brace and nothing trails it.
    """
    rules = parse_stylesheet("@media print { p { color: black } } q { color: white }")
    assert len(rules) == 2
    assert isinstance(rules[0], AtRule)
    media_block_types = [type(t).__name__ for t in rules[0].block]
    # The inner rule's own braces must survive inside the flattened block --
    # a naive scanner that counts only *matched pairs of the outer brace
    # character* would still get this particular case right, but one that
    # used `str.find("}")`/regex up to the first close would truncate it.
    assert "LBrace" in media_block_types and "RBrace" in media_block_types
    assert isinstance(rules[1], QualifiedRule)
    assert rules[1].prelude and rules[1].prelude[0].value == "q"


def test_unknown_at_rule_is_fully_consumed_not_skipped():
    """If at-rules were "skipped" by scanning forward to the next `;` or the
    next top-level `}` without real brace tracking, a semicolon *inside* the
    at-rule's block would end the at-rule early. Guard against that here:
    the prelude and block must be captured, and the trailing rule (which a
    corrupted cursor position would swallow or misplace) must still appear.
    """
    rules = parse_stylesheet("@weird foo; bar { a: b } p { color: red }")
    assert len(rules) == 3
    assert isinstance(rules[0], AtRule)
    assert rules[0].name == "weird"
    assert rules[0].block is None
    assert isinstance(rules[1], QualifiedRule)
    assert rules[1].prelude and rules[1].prelude[0].value == "bar"
    assert isinstance(rules[2], QualifiedRule)
    assert rules[2].prelude and rules[2].prelude[0].value == "p"


def test_malformed_declaration_is_not_silently_kept():
    """Guards against a wrong `_consume_declaration` that treats "no colon"
    as "value is empty, name is fine" and keeps the declaration anyway.
    """
    rule = parse_stylesheet("p { color red; margin: 0 }")[0]
    decls = parse_declarations(rule.block)
    assert "color" not in [d.name for d in decls]


def test_whole_block_is_not_dropped_by_one_bad_declaration():
    """A plausible wrong implementation: catch any error while parsing a
    block's declarations and give up on the rest of the block. Three
    declarations, the middle one malformed, both good ones must survive.
    """
    rule = parse_stylesheet("p { color: red; nonsense here; margin: 0 }")[0]
    decls = parse_declarations(rule.block)
    assert [d.name for d in decls] == ["color", "margin"]


def test_semicolon_inside_declaration_value_parens_does_not_split_it():
    """A declaration value can legally contain a function call, and commas
    or semicolons cannot appear unescaped inside url()/calc() parens in a
    way that would confuse a naive semicolon-splitter, but nested parens in
    general must still be tracked so the value-collection loop doesn't stop
    partway through a function argument list.
    """
    decls = parse_declarations(parse_stylesheet("p { width: calc(1px + 2px) }")[0].block)
    assert decls[0].name == "width"
    names = [type(t).__name__ for t in decls[0].value]
    assert names[0] == "Function" and names[-1] == "RParen"


def test_declaration_important_survives_space_before_bang():
    """5.5.5 says "the last two non-whitespace tokens", not "the last two
    tokens" -- `red ! important` (space before the bang) must still count.
    """
    decls = parse_declarations(parse_stylesheet("p { color: red ! important }")[0].block)
    assert decls[0].important is True


def test_important_is_case_insensitive():
    decls = parse_declarations(parse_stylesheet("p { color: red !ImPoRtAnT }")[0].block)
    assert decls[0].important is True


def test_at_rule_prelude_token_list():
    rules = parse_stylesheet("@import url(a.css) screen;")
    assert rules[0].name == "import"
    non_ws = [t for t in rules[0].prelude if type(t).__name__ != "Whitespace"]
    assert [type(t).__name__ for t in non_ws] == ["Url", "Ident"]


def test_qualified_rule_pos_points_at_prelude_start():
    rules = parse_stylesheet("  p { color: red }")
    assert rules[0].pos == 2


def test_declaration_pos_points_at_name():
    decls = parse_declarations(parse_stylesheet("p { color: red }")[0].block)
    assert decls[0].pos == 4  # offset of "color" inside "p { color: red }"


def test_multiple_qualified_rules():
    rules = parse_stylesheet("p { color: red } div { color: blue }")
    assert len(rules) == 2
    assert all(isinstance(r, QualifiedRule) for r in rules)


def test_css_parser_records_errors_and_metrics():
    parser = CssParser("p { color red; margin: 0 }")
    parser.parse_stylesheet()
    assert parser.errors == []  # error surfaces from parse_declarations, not here
    assert parser.metrics["rules"] == 1
    assert parser.metrics["qualified_rules"] == 1

    decl_parser = CssParser("")
    decls = decl_parser.parse_declarations(
        parse_stylesheet("p { color red; margin: 0 }")[0].block
    )
    assert len(decls) == 1
    assert decl_parser.errors, "the dropped declaration should record an error"
    assert decl_parser.metrics["malformed_declarations"] == 1


def test_parse_declarations_return_type_matches_interface():
    decls = parse_declarations(parse_stylesheet("p { color: red }")[0].block)
    assert isinstance(decls, list)
    assert all(isinstance(d, Declaration) for d in decls)


def test_stray_leading_token_does_not_drop_the_rest_of_the_block():
    """The "anything else" branch of consume-a-list-of-declarations (a token
    that starts neither an ident-declaration nor an at-rule) must consume
    exactly one component value and keep going -- not the rest of the block.
    """
    rule = parse_stylesheet("p { : bad; color: red }")[0]
    assert [d.name for d in parse_declarations(rule.block)] == ["color"]


def test_can_reuse_a_materialized_token_list_directly():
    """`parse_declarations` accepts any `list[CssToken]`, not only a rule's
    `block` -- e.g. one built directly from `CssTokenizer`, as long as the
    caller strips (or never adds) a trailing EOFToken/braces themselves.
    """
    # Drop the trailing EOFToken -- parse_declarations treats "off the end
    # of the list" as EOF already, so this should behave identically to a
    # block slice.
    tokens = [
        t for t in CssTokenizer("color: red").tokenize()
        if not isinstance(t, EOFToken)
    ]
    decls = parse_declarations(tokens)
    assert decls[0].name == "color"
