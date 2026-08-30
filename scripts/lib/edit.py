#!/usr/bin/env python3
"""Text edits that cannot silently do nothing.

`str.replace` returns the string unchanged when its anchor is absent. It
does not raise, and it does not report. Every consequence of a missed edit
therefore shows up somewhere else, later, as an absence -- which is the
hardest kind of defect to see.

This module exists because of one afternoon's evidence. Ten scripted edits
were applied to this repo in a single session; nine carried an
`assert anchor in s` and one did not, and the one that did not was the one
that silently missed. It anchored on
`ap.add_argument("--no-follow-imports",` as a single line when the file
splits it across two. The file still parsed, the test suite still passed --
because the *branch* the flag controls had landed, and only the flag itself
was missing -- and the miss surfaced as an argparse error in a background
job several minutes later.

The rule was known. It had been applied nine times in the same hour. It was
skipped once, and that is where the defect landed.

**So the fix is not more vigilance.** A rule that must be remembered every
time has a per-use failure probability that does not go to zero, and ten
uses is enough for one miss. The fix is to make the checked path the
*shortest* path: `sub()` below does the replacement and the postcondition
in one call, so writing the careful version is less typing than writing the
careless one. There is no unchecked variant here to reach for.

    from lib.edit import sub, sub_all

    text = sub(text, old, new)              # raises if `old` is absent
    text = sub(text, old, new, count=2)     # raises unless found exactly twice
    text = sub_all(text, [(a, b), (c, d)])  # each pair checked in turn

See `docs/measurement-hazards.md`: this is the operation-that-succeeds-by-
ignoring-an-input shape, the same one `Path("/a") / "/b"` has.
"""

from __future__ import annotations


class EditMissed(Exception):
    """An anchor was absent, or present a different number of times."""


def _excerpt(anchor: str, width: int = 72) -> str:
    first = anchor.strip().splitlines()[0] if anchor.strip() else anchor
    return first[:width] + ("..." if len(first) > width else "")


def sub(text: str, old: str, new: str, *, count: int | None = 1) -> str:
    """Replace `old` with `new`, raising unless it occurred `count` times.

    `count=None` means "at least once, however many". An exact count is the
    default because "I expected one and there were three" is a real defect
    that a permissive replace turns into three silent edits.
    """
    found = text.count(old)
    if found == 0:
        raise EditMissed(f"anchor not found: {_excerpt(old)!r}")
    if count is not None and found != count:
        raise EditMissed(
            f"anchor found {found} times, expected {count}: {_excerpt(old)!r}"
        )
    return text.replace(old, new)


def sub_all(text: str, pairs, *, count: int | None = 1) -> str:
    """Apply `(old, new)` pairs in order, each one checked.

    Order matters and is preserved: a later pair may depend on an earlier
    one having run. Each is checked as it is applied, so the failure names
    the pair that missed rather than the batch.
    """
    for old, new in pairs:
        text = sub(text, old, new, count=count)
    return text
