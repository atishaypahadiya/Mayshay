"""
DOM node types.

    from mayshay.dom import Document, Element, Text

Re-exports only; every name below is defined in `node.py`.
"""

from mayshay.dom.node import (
    Comment,
    Document,
    DocumentType,
    Element,
    Node,
    Text,
    serialize,
)

__all__ = [
    "Comment",
    "Document",
    "DocumentType",
    "Element",
    "Node",
    "Text",
    "serialize",
]
