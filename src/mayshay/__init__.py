"""
Mayshay: an educational browser engine written from scratch.

Pipeline: net -> htmlparse -> cssparse -> layout -> paint.

Sub-packages are imported explicitly rather than re-exported here, so that
`import mayshay` stays cheap:

    from mayshay.htmlparse import Tokenizer, parse
    from mayshay.dom import Document, Element
"""

__version__ = "0.1.0"

__all__ = ["__version__"]
