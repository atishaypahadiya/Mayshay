"""Guard against the editable-install pointer being repointed.

.venv/ is gitignored, so `git status` stays clean while every test in the
repo silently runs against a different copy of the code, or none at all.
"""
from pathlib import Path


def test_engine_imports_from_this_repo():
    import mayshay

    expected = Path(__file__).resolve().parents[1] / "src" / "mayshay"
    assert Path(mayshay.__file__).resolve().parent == expected
