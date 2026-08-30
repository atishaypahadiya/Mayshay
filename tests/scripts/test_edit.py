"""`lib.edit` -- the helper that makes a missed edit loud.

Written because `str.replace` returns the string unchanged when its anchor
is absent, and a scripted edit to `scripts/collect.py` did exactly that:
the file parsed, the suite passed, and the missing `--resume` flag surfaced
as an argparse error minutes later in a background job.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path[:0] = [str(Path(__file__).resolve().parents[2] / "scripts")]

from lib.edit import EditMissed, sub, sub_all  # noqa: E402


def test_a_missing_anchor_raises_instead_of_returning_the_input():
    """The whole point. `"abc".replace("z", "y")` is `"abc"` and says nothing."""
    with pytest.raises(EditMissed, match="not found"):
        sub("abc", "z", "y")


def test_the_real_anchor_that_missed_is_caught():
    """The actual text: the edit anchored on a single-line `add_argument(` in
    a file that splits it across two lines."""
    source = '    ap.add_argument(\n        "--no-follow-imports",\n'
    with pytest.raises(EditMissed, match="not found"):
        sub(source, '    ap.add_argument("--no-follow-imports",', "X")
    assert sub(source, '    ap.add_argument(\n        "--no-follow-imports",', "X") == "X\n"


def test_an_unexpected_second_occurrence_is_a_defect_not_a_bonus():
    """"I expected one and there were three" is a real defect that a
    permissive replace turns into three silent edits."""
    with pytest.raises(EditMissed, match="found 2 times"):
        sub("a x a", "a", "b")
    assert sub("a x a", "a", "b", count=2) == "b x b"
    assert sub("a x a", "a", "b", count=None) == "b x b"


def test_sub_all_names_the_pair_that_missed():
    """A batch failure that does not say which pair failed is a batch failure
    you have to bisect by hand."""
    with pytest.raises(EditMissed, match="ccc"):
        sub_all("aaa bbb", [("aaa", "1"), ("ccc", "2")])


def test_sub_all_applies_pairs_in_order():
    """Order is preserved because a later pair may depend on an earlier one."""
    assert sub_all("a", [("a", "b"), ("b", "c")]) == "c"
