"""
HTML tokenization and tree construction.

The documented entry points, per CLAUDE.md:

    from mayshay.htmlparse import Tokenizer, TreeBuilder, parse

Re-exports only; every name below is defined in `tokenizer.py`,
`treebuilder.py` or `entities.py`.
"""

from mayshay.htmlparse.entities import decode_reference
from mayshay.htmlparse.tokenizer import (
    CharacterToken,
    CommentToken,
    DoctypeToken,
    EndTagToken,
    EOFToken,
    StartTagToken,
    Token,
    Tokenizer,
)
from mayshay.htmlparse.treebuilder import TreeBuilder, parse

__all__ = [
    "CharacterToken",
    "CommentToken",
    "DoctypeToken",
    "EndTagToken",
    "EOFToken",
    "StartTagToken",
    "Token",
    "Tokenizer",
    "TreeBuilder",
    "decode_reference",
    "parse",
]
