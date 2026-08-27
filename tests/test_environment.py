"""Guard against the editable-install pointer being repointed.

.venv/ is gitignored, so `git status` stays clean while every test in the
repo silently runs against a different copy of the code, or none at all.
"""
import re
from pathlib import Path


def test_engine_imports_from_this_repo():
    import mayshay

    expected = Path(__file__).resolve().parents[1] / "src" / "mayshay"
    assert Path(mayshay.__file__).resolve().parent == expected


FORBIDDEN_CSS_IMPORT = re.compile(
    r"^\s*(?:import|from)\s+(tinycss2|cssutils|cssselect)\b", re.MULTILINE
)


def test_no_forbidden_css_libraries_in_the_engine():
    """CLAUDE.md forbids tinycss2 / cssutils / cssselect in src/mayshay/.

    Matches import statements, not the bare name: the cssparse docstrings
    name tinycss2 to explain why it is banned and where the tokenizer
    deliberately disagrees with it, and a plain substring search flags those.
    An import is the thing the rule is actually about -- including an unused
    one, which is exactly how a hand-rolled parser stops being hand-rolled.
    """
    root = Path(__file__).resolve().parents[1] / "src" / "mayshay"
    offenders = [
        f"{path.relative_to(root)}: {match.group(1)}"
        for path in sorted(root.rglob("*.py"))
        for match in FORBIDDEN_CSS_IMPORT.finditer(path.read_text(encoding="utf-8"))
    ]
    assert offenders == []
