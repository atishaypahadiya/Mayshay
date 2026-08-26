"""
Readers for the html5lib-tests corpus (vendored as a git submodule).

The .dat format is a sequence of tests separated by a blank line, each made
of #-prefixed sections:

    #data
    <p>Hello
    #errors
    (1,3): expected-doctype-but-got-start-tag
    #document
    | <html>
    |   <head>
    |   <body>
    |     <p>
    |       "Hello"

Only #data and #document are required for our purposes.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "html5lib-tests"
TREE_DIR = ROOT / "tree-construction"
TOKENIZER_DIR = ROOT / "tokenizer"

_HEADERS = (
    "#data",
    "#errors",
    "#new-errors",
    "#document-fragment",
    "#document",
    "#script-off",
    "#script-on",
)


@dataclass
class DatTest:
    data: str
    errors: list[str] = field(default_factory=list)
    document: str = ""
    fragment: str | None = None
    script: str | None = None
    path: str = ""
    index: int = 0

    @property
    def id(self) -> str:
        return f"{Path(self.path).name}:{self.index}"


def _split_sections(chunk: str) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {"data": []}
    current = "data"
    for line in chunk.split("\n"):
        if line in _HEADERS:
            current = line[1:]
            sections.setdefault(current, [])
        else:
            sections[current].append(line)
    return sections


def parse_dat(text: str, path: str = "") -> list[DatTest]:
    # Tests are separated by a blank line immediately followed by "#data".
    chunks = text.split("\n\n#data\n")
    if chunks and chunks[0].startswith("#data\n"):
        chunks[0] = chunks[0][len("#data\n") :]

    tests: list[DatTest] = []
    for index, chunk in enumerate(chunks):
        if not chunk.strip():
            continue
        sections = _split_sections(chunk)
        document = sections.get("document", [])
        # Drop trailing blank lines left by the separator.
        while document and not document[-1]:
            document.pop()
        script = None
        if "script-off" in sections:
            script = "off"
        elif "script-on" in sections:
            script = "on"
        fragment = sections.get("document-fragment")
        tests.append(
            DatTest(
                data="\n".join(sections["data"]),
                errors=[e for e in sections.get("errors", []) if e],
                document="\n".join(document),
                fragment="\n".join(fragment).strip() if fragment else None,
                script=script,
                path=path,
                index=index,
            )
        )
    return tests


def load_tree_tests(*filenames: str) -> list[DatTest]:
    paths = (
        [TREE_DIR / name for name in filenames]
        if filenames
        else sorted(TREE_DIR.glob("*.dat"))
    )
    tests: list[DatTest] = []
    for p in paths:
        tests.extend(parse_dat(p.read_text(encoding="utf-8"), path=str(p)))
    return tests


@dataclass
class TokenizerTest:
    description: str
    input: str
    output: list
    initial_states: list[str] = field(default_factory=lambda: ["Data state"])
    last_start_tag: str | None = None


def load_tokenizer_tests(*filenames: str) -> list[TokenizerTest]:
    paths = (
        [TOKENIZER_DIR / name for name in filenames]
        if filenames
        else sorted(TOKENIZER_DIR.glob("*.test"))
    )
    tests: list[TokenizerTest] = []
    for p in paths:
        blob = json.loads(p.read_text(encoding="utf-8"))
        for entry in blob.get("tests", []):
            if entry.get("doubleEscaped"):
                continue  # escaped-string form; skip until Task 3 handles it
            tests.append(
                TokenizerTest(
                    description=entry["description"],
                    input=entry["input"],
                    output=entry["output"],
                    initial_states=entry.get("initialStates", ["Data state"]),
                    last_start_tag=entry.get("lastStartTag"),
                )
            )
    return tests
