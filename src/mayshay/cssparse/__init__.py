"""
CSS tokenization and parsing.

The documented entry point, per CLAUDE.md:

    from mayshay.cssparse import CssTokenizer, CssParser, parse_stylesheet

Re-exports only; every name below is defined in `tokenizer.py`,
`parser.py`, `selectors.py`, `matching.py`, `values.py` or `cascade.py`.

The stage's own entry point is `style_document(document, author_css)`,
which runs the whole of it -- parse, match, cascade, compute -- and returns
this stage's metrics. It was missing from this file for as long as it
existed, which meant the module whose docstring advertises an import
surface did not expose the one function a driver actually calls.

Hand-rolled, and required to stay that way: `tinycss2`, `cssutils` and
`cssselect` are forbidden in `src/mayshay/`.
"""

from mayshay.cssparse.cascade import (
    INHERITED,
    LONGHANDS,
    ComputedStyle,
    style_document,
)
from mayshay.cssparse.matching import RuleIndex, matches
from mayshay.cssparse.parser import (
    AtRule,
    CssParser,
    Declaration,
    QualifiedRule,
    parse_declarations,
    parse_stylesheet,
)
from mayshay.cssparse.selectors import (
    AttributeSelector,
    ClassSelector,
    Complex,
    Compound,
    IdSelector,
    PseudoClassSelector,
    PseudoElementSelector,
    SelectorList,
    SelectorParseError,
    Simple,
    TypeSelector,
    UniversalSelector,
    parse_selector_list,
    specificity,
)
from mayshay.cssparse.tokenizer import (
    AtKeyword,
    BadString,
    BadUrl,
    CDC,
    CDO,
    Colon,
    Comma,
    CssToken,
    CssTokenizer,
    Delim,
    Dimension,
    EOFToken,
    Function,
    Hash,
    Ident,
    LBrace,
    LBracket,
    LParen,
    Number,
    Percentage,
    RBrace,
    RBracket,
    RParen,
    Semicolon,
    String,
    Url,
    Whitespace,
)
from mayshay.cssparse.values import (
    AUTO,
    Color,
    Keyword,
    Length,
    Percent,
    expand_shorthand,
    normalize_property_name,
    parse_declaration_value,
)

__all__ = [
    "AUTO",
    "AtKeyword",
    "AtRule",
    "AttributeSelector",
    "BadString",
    "BadUrl",
    "CDC",
    "CDO",
    "ClassSelector",
    "Colon",
    "Color",
    "Comma",
    "Complex",
    "Compound",
    "ComputedStyle",
    "CssParser",
    "CssToken",
    "CssTokenizer",
    "Declaration",
    "Delim",
    "Dimension",
    "EOFToken",
    "Function",
    "Hash",
    "INHERITED",
    "IdSelector",
    "Ident",
    "Keyword",
    "LBrace",
    "LBracket",
    "LONGHANDS",
    "LParen",
    "Length",
    "Number",
    "Percent",
    "Percentage",
    "PseudoClassSelector",
    "PseudoElementSelector",
    "QualifiedRule",
    "RBrace",
    "RBracket",
    "RParen",
    "RuleIndex",
    "SelectorList",
    "SelectorParseError",
    "Semicolon",
    "Simple",
    "String",
    "TypeSelector",
    "UniversalSelector",
    "Url",
    "Whitespace",
    "expand_shorthand",
    "matches",
    "normalize_property_name",
    "parse_declaration_value",
    "parse_declarations",
    "parse_selector_list",
    "parse_stylesheet",
    "specificity",
    "style_document",
]
