# Task I re-review (fix round 1): scoped

Base fd15b3e -> head 91e2bfc. Diff: src/mayshay/cssparse/values.py,
tests/cssparse/test_values.py.

## Finding Verdicts

1. **Colour keyword table completeness (Important)** — ADDRESSED.
   `src/mayshay/cssparse/values.py:107-190` now holds 148 entries. Programmatically
   diffed the entire dict against two independent oracles already present in
   `.venv` (`webcolors.names('css3')` + `rebeccapurple`, and
   `matplotlib.colors.CSS4_COLORS`): 148/148 keys match, zero missing, zero
   extra, **zero value mismatches** against either oracle. No transcription
   errors anywhere in the table — full verification, not sampling.

2. **`expand_shorthand` unified calling convention (Important)** — ADDRESSED.
   `src/mayshay/cssparse/values.py:638` now takes `dict[str, object]`
   uniformly; `_parse_margin_or_padding` (line 555) returns a
   `{"top"/"right"/"bottom"/"left": value}` dict via `_sides_from_values`
   (line 532), matching `_parse_border`'s dict shape (line 582). `# type:
   ignore[arg-type]` casts removed — the signature is now honestly typed.

3. **`test_display_keywords` hardcode-proof (Important)** — ADDRESSED.
   `tests/cssparse/test_values.py:45-52` now checks `block` vs `inline` and
   asserts inequality; a `return Keyword("block")` stub fails immediately.

4. **Minor coverage gaps (padding-percent, font-size-percent,
   border/currentcolor)** — ADDRESSED. `test_padding_percent` (line 224),
   `test_font_size_percent` (line 230), `test_border_color_currentcolor`
   (line 234) each assert a real symbolic/keyword value, not just "did not
   raise" — each fails against a plausible wrong implementation (percent
   silently resolved, currentcolor coerced to a concrete `Color`, etc).

## Full-table value verification

Ran two independent oracle diffs (`webcolors` CSS3 list + rebeccapurple,
and matplotlib's `CSS4_COLORS`) against `_COLOR_KEYWORDS` — set difference
and per-key RGB comparison. **Result: all 148 entries agree with both
oracles, no disagreements found.** This is a complete check, not a sample;
nobody needs to re-verify this table's contents again.

## Are 4 new tests adequate for 126 new entries?

Reasonable shape, not airtight. `test_color_keyword_table_is_complete`
(`tests/cssparse/test_values.py:239`) pins `len == 148` and spot-checks 6
deliberately non-famous names (rebeccapurple, papayawhip,
mediumspringgreen, darkslategrey, cadetblue, lightgoldenrodyellow) spanning
c/d/l/m/p/r — well distributed, not clustered on memorable colors, and
round-tripped through the public API (catches lookup-path bugs, not just
data bugs). Residual gap the implementer's own report acknowledges: a
duplicate-key transcription error that both loses one entry and duplicates
another lands at exactly 148 unique keys, passing the count check, and
would only be caught if one of the 6 sampled names happened to be the
casualty. That's an inherent limit of count+sample tests on a 148-row
table, not something the fix round could reasonably close without adding a
webcolors/matplotlib dependency to the test suite — which is exactly what
my full-table diff above substitutes for. No action needed since the real
table is now proven correct.

## Shorthand shape, Task J's perspective

Sound. `expand_shorthand`'s docstring (`src/mayshay/cssparse/values.py:638-663`)
correctly frames the differing fan-out (margin/padding: 1 key -> 1
longhand; border: 1 key -> 4 longhands) as CSS semantics, not leftover
inconsistency — that's accurate: a single `border-width` genuinely applies
to all four sides, while margin's four values are independently four
longhands. Task J can call `expand_shorthand(name, parsed)` with one dict
construction pattern per property without branching on list-vs-dict; it
still must know each property's own component names, but that's
unavoidable given the properties have different grammars, not an artifact
of this module's design.

## New Breakage in the Fix Diff

Minor: `expand_shorthand("margin"/"padding", parsed)`
(`src/mayshay/cssparse/values.py:664`) does `parsed[side] for side in
_SIDES` with no key-presence check, so a caller passing a partial dict
(e.g. only `{"top": ...}`) now gets a bare `KeyError` instead of the old
list-based path's explicit `ValueError(f"{prefix} shorthand needs 1-4
values, got {n}")`. Every internal caller (`_parse_margin_or_padding`)
always supplies all four keys, so this is unreachable through
`parse_declaration_value` and untested/unexercised — a latent rough edge
in the public API's error messages, not a functional regression. Nothing
else new: `_expand_border` and `_parse_border` are mechanically unchanged
(rename of `_BORDER_SIDES` to `_SIDES`, `key`/`kind` variable cleanup).

## Out-of-Scope Observations

None beyond what the implementer's own report already flags (border's
"no initial-value synthesis" design choice, `_split_top_level`'s untested
bare-paren depth tracking) — both pre-date this fix diff and are unchanged
by it.

## Verdict

**Fix round:** All four findings addressed, no new Critical/Important
breakage. One Minor latent rough edge (KeyError instead of ValueError on
misuse of `expand_shorthand` with a partial margin/padding dict) — does not
block, unreachable via any current caller.
