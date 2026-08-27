# Task J re-review — fix round 1

## Finding Verdicts

1. **Shorthand reset delegated but never implemented** — ADDRESSED. `_reset_omitted_longhands` (cascade.py:152-178), called from both `_parse_block` (cascade.py:299) and `_parse_inline_style` (cascade.py:321), driven by `_SHORTHAND_LONGHANDS`/`INITIAL_SPECIFIED` (cascade.py:129-149). `p{border:5px solid red} p{border:solid blue}` now gives `border-top-width: Length(3,"px")`.
2. **UA sheet left `tr`/`td`/`th`/`tbody`/`caption` inline; false rationale** — ADDRESSED. `ua.py:508-523` adds the full table block (`caption`, `colgroup`, `col`, `thead`, `tbody`, `tfoot`, `tr`, `td, th`); the false "tree builder does not reliably build tables" claim is replaced with the correct distinction (elements exist; insertion-mode conformance on malformed markup is the real carried gap), `ua.py:477-486`.
3. **Deviation 8's false rationale (`border:solid red` → 0px)** — ADDRESSED. Two-initials model: `INITIAL_SPECIFIED` holds `Length(3,"px")` (specified `medium`, cascade.py:110/138), `_zero_widths_of_borderless_sides` zeros width only when style is `none`/`hidden` (cascade.py:371-384). Verified directly: `border: solid red` → 3px; `border: 5px red` (style omitted → `none`) → 0px. Docstring corrected, cascade.py:69-82.
4. **`_computed_value` unwrapped any Keyword** — ADDRESSED. Allow-list `_KEYWORD_VALUED = {"display"} | border-style props` (cascade.py:254); anything else raises `ValueError` (cascade.py:274-277), `currentcolor` still resolved first.
5. **Test asserting only private rank constants** — ADDRESSED. Replaced by `test_ua_important_outranks_every_author_declaration` (test_cascade.py:593-618), monkeypatches `UA_CSS` to an `!important` rule and asserts observable colour beats `#x#x !important` author and `!important` inline.
6. **`root_font_px` updated on any orphan** — ADDRESSED. `root_element` is now identified once by scanning for the first `Element` in document order (cascade.py:414), compared by identity (cascade.py:438), not by "parent is not an Element". New test `test_rem_is_defined_by_the_root_element_not_by_a_stray_orphan` drives a hand-built stray sibling through it.

## `!important` / inline-`style=` ordering (directly executed against the real package, read-only)

Ran four cases through `style_document` on the installed package (no source modified):
- important shorthand then later normal shorthand → important wins (medium/solid/red), correct.
- normal shorthand then later important shorthand → important wins (dotted), correct.
- inline (`style=`) normal shorthand vs. author `#x#x` normal shorthand → inline wins, correct (style attribute outranks any selector-based normal rule).
- author `!important` shorthand vs. inline normal shorthand → author-important wins, correct.

All four match browser semantics. Mechanism: `_parse_block`/`_parse_inline_style` compute `rank`/`index` once per source declaration and apply that same rank/index to every longhand the reset adds (cascade.py:300-304, cascade.py:322-327) — `!important` and source position propagate to the reset-produced longhands exactly as a real shorthand expansion would, not as a separate overwrite. No test in the diff exercises `!important` against the reset directly (a real gap in the fix's own suite), but the executed checks above close that gap independently and confirm the behaviour is correct, not merely untested.

## `display` keyword permissiveness

Not more permissive than intended. `_DISPLAY_KEYWORDS` (values.py:555-564) gained exactly the six missing internal table keywords plus `inline-table`, all genuine CSS values; `_parse_display` (values.py:511-515) is unchanged — still a single-ident membership check, so `display: table-cell` and friends parse, and `display: bogus`/`display: table-foo` still return `None` (dropped). No other property's grammar changed.

## Injection results

- Two closed gaps verified in the diff: `test_a_partial_shorthand_in_a_style_attribute_resets_too` (test_cascade.py:756-770) and the colour assertions added to `test_an_element_with_no_border_has_zero_width_borders` (test_cascade.py:740-753) — both are real, targeted assertions that would fail under the named mutations.
- Malformed-mutation replacement (`shorthand_reset_applied_outside_the_cascade` → `shorthand_reset_forced_to_a_high_rank`) is plausible and caught by the existing `test_the_shorthand_reset_respects_the_cascade_rather_than_overwriting`.
- "Semantically dead" label (`border_width_initial_collapsed_to_medium_everywhere`) — **accurate**, confirmed by tracing `values.py`: `parse_declaration_value` (values.py:681-724) recognizes only the `border` shorthand, never a standalone `border-*-style`/`border-*-width` longhand, so a non-`none` `border-*-style` can only arise via `border`, which always triggers `_reset_omitted_longhands` and populates width explicitly; and `_zero_widths_of_borderless_sides` runs unconditionally for every element, zeroing width whenever style is `none` regardless of the dataclass default. The `ComputedStyle` field default for border-width is genuinely unreachable — not a hidden miss.

## Table-fix metric perturbation

`declarations_dropped` unchanged is consistent with the code: `_parse_display` accepts all new keywords via the same membership check, so all 8 new UA declarations parse and land in `declarations_kept`, none in `declarations_dropped`. `rules_total +9` / `declarations_kept +8` reconciles correctly: 7 single-selector rules + one `td, th` rule (2 `_StyleRule`s, 1 shared declaration) = 8 declarations, 9 selectors — matches `RuleIndex`'s one-`_StyleRule`-per-selector design already documented for this module.

## New Breakage in the Fix Diff

None found.

## Out-of-Scope Observations

- No test in the fix's own diff exercises `!important` interacting with the shorthand reset, or an inline-`style=` shorthand against an author longhand of higher specificity — the fix report's injection table doesn't name this axis either. Closed independently above by direct execution, but the gap in the checked-in suite remains.

## Verdict

**Fix round: All six findings addressed, no new Critical/Important breakage.** `display` keyword set widened only by the intended legitimate table values. Suite 6483/72/0 (was 6468/72; +15) accepted as reported; git status clean; venv `.pth` unchanged (md5 `3717d729cbbfc50ae0f221f1d9b09cdd`).
