# Task F Re-Review Round 2

## Stale Deviation Cross-References

**ADDRESSED.** All four references now resolve to their intended entries:
- Line 231: "representation note under deviation 1" — correctly points to the block-contents note in deviation 1's docstring.
- Line 254: "deviation 1 (component values as flat token lists...)" — correct already; reference to flat-token representation.
- Line 390: "deviation 2 (parse_declarations's list[Declaration]...)" — fixed from deviation 3; resolves to the correct entry about return type.
- Line 495: "deviation 5 (errors/metrics kept separate...)" — fixed from deviation 6; resolves to the only remaining entry about CssParser's separate errors/metrics.

**Grep confirms no fourth stale reference was missed:** searching for all "deviation" mentions yields exactly 6 (header, note under deviation 1, and the four cross-references above). Only the three reported (231, 390, 495) required fixing.

**Mitigation effectiveness:** The added parenthetical descriptions (e.g. "deviation 2 (parse_declarations's...)") make future renumbering fail visibly — a renumbered list will produce mismatched description+number pairs that a reader will notice, rather than silently wrong bare numbers. This is a good defensive practice, though it still relies on reader attention to the mismatch.

**Code integrity:** Only docstrings and comments changed (diff confirms 14 insertions, 5 deletions in `parser.py`, all in docstrings and inline comments). No logic changed.

**Tests:** All 27 cssparse tests pass. Full suite 6179 passed, 72 skipped (xfailed), 0 failed. Conformance unmoved. Venv and git clean.

## Verdict

**Fix round:** All findings addressed, no new breakage. The deviation cross-references are now correctly resolved and future renumbering failures will be visible.
