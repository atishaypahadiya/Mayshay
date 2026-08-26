"""
DOM node types.

Deliberately minimal: parent/child links, no live NodeLists, no event
targets, no ranges. The names match the spec because we will be typing them
for the rest of the project; the tokenizer's token classes carry a `Token`
suffix precisely so they don't collide with these.
"""

from __future__ import annotations


class Node:
    def __init__(self) -> None:
        self.parent: Node | None = None
        self.children: list[Node] = []

    def append_child(self, node: Node) -> Node:
        if node.parent is not None:
            node.parent.remove_child(node)
        node.parent = self
        self.children.append(node)
        return node

    def insert_before(self, node: Node, ref: Node) -> Node:
        if ref not in self.children:
            raise ValueError("reference node is not a child of this node")
        if node.parent is not None:
            node.parent.remove_child(node)
        node.parent = self
        self.children.insert(self.children.index(ref), node)
        return node

    def remove_child(self, node: Node) -> Node:
        if node not in self.children:
            raise ValueError("node is not a child of this node")
        self.children.remove(node)
        node.parent = None
        return node


class Document(Node):
    def __init__(self) -> None:
        super().__init__()
        self.quirks_mode = False

    @property
    def document_element(self) -> Element | None:
        for child in self.children:
            if isinstance(child, Element) and child.tag_name == "html":
                return child
        return None


class DocumentType(Node):
    def __init__(self, name: str) -> None:
        super().__init__()
        self.name = name


class Element(Node):
    def __init__(self, tag_name: str, attrs: dict[str, str] | None = None) -> None:
        super().__init__()
        self.tag_name = tag_name
        self.attrs: dict[str, str] = dict(attrs or {})

    def __repr__(self) -> str:
        return f"<Element {self.tag_name} {self.attrs}>"


class Text(Node):
    def __init__(self, data: str = "") -> None:
        super().__init__()
        self.data = data

    def __repr__(self) -> str:
        return f"<Text {self.data!r}>"


class Comment(Node):
    def __init__(self, data: str = "") -> None:
        super().__init__()
        self.data = data


def _render(node: Node, depth: int, out: list[str]) -> None:
    pad = "| " + "  " * depth
    if isinstance(node, Element):
        out.append(f"{pad}<{node.tag_name}>")
        for name in sorted(node.attrs):
            out.append(f'| {"  " * (depth + 1)}{name}="{node.attrs[name]}"')
    elif isinstance(node, Text):
        out.append(f'{pad}"{node.data}"')
    elif isinstance(node, Comment):
        out.append(f"{pad}<!-- {node.data} -->")
    elif isinstance(node, DocumentType):
        out.append(f"{pad}<!DOCTYPE {node.name}>")


def serialize(document: Document) -> str:
    """Render a tree in the html5lib-tests `#document` format."""
    out: list[str] = []
    # Explicit stack; deep documents would overflow Python's recursion limit.
    stack: list[tuple[Node, int]] = [
        (child, 0) for child in reversed(document.children)
    ]
    while stack:
        node, depth = stack.pop()
        _render(node, depth, out)
        stack.extend((child, depth + 1) for child in reversed(node.children))
    return "\n".join(out)
