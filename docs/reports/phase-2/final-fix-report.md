# Phase 2 — final fix wave

Applying the merge-blocking findings from `final-review.md`. One commit, no
subagents. Suite **6499 passed, 72 xfailed, 0 failed** (was 6483/72; +16 tests).
All four baselines hold: conformance **780/1592** and **64/112**, parse-error
agreement **404/474** (extra 49 / missing 27), `link_stylesheets_skipped`
**0/1/2**. `.venv/.../__editable__.mayshay-0.1.0.pth` still reads
`/Users/atishaypahadiya/projects/mayshay/src`; `git status` clean apart from
the ten files of this change.

## The rule I worked under

Every deviation claim I touched, I executed. **Twenty-two** distinct factual
claims were run rather than reasoned about, and one of them — my own — was
wrong: I wrote "`display` is a closed keyword allow-list (21 entries)" from
counting the literal by eye, then ran `len(_DISPLAY_KEYWORDS)` and got **20**.
The deviation now says "counted by `len(_DISPLAY_KEYWORDS)`, not by eye". That
is the meta-finding reproducing itself inside the fix for the meta-finding,
caught only because the check was mandatory.

Executed claims, by item:

| Claim | How checked |
|---|---|
| `border` vs `BORDER` gives 3px vs 5px | `style_document` on both, before and after |
| `font-size` moves `declarations_applied` by 0 (before) / 1 (after) | four CSS bodies against a baseline |
| shorthand contributes 4 for `margin`/`padding`, 12 for `border`; a re-declared longhand contributes once | five CSS bodies against a baseline — `margin` deltas 0 because the UA sheet already sets `p { margin: 1em 0 }` |
| inline `style=` errors read 0/0 vs a `<style>` body's 1/1 | same malformed CSS both ways, before and after; parity is exact after |
| wikipedia has 237 inline `style=` attributes | counted over the corpus |
| 313 declarations dropped on wikipedia; 85 of them in the longhand family; 15 `padding-right`, 14 `margin-top`, 12 `background`, 8 `margin-bottom`, 7 `border-left` | per-property `Counter` over the corpus |
| `flow-root` is the sole dropped `display` value | same sweep, filtered to `display` |
| `len(_DISPLAY_KEYWORDS)` | executed — **found the review's-shape error in my own draft** |
| `2n+1` → `Dimension, Number` (no `Whitespace`); `2n +1` and `2n 1` → three tokens; `2n + 1` → five | `CssTokenizer` on all four |
| `2n + -1`, `+ n`, `+-n` parse to `None`; the four accepted forms all yield `(2, 1)` | `_parse_an_b` on all seven |
| `is_integer` has five consumers, all in `matching.py`; none in `values.py` | grepped `src/` |
| `_an_b_memo` is written, and `==`/`hash()`/dict-key are unchanged by it | matched a selector against a tree, then compared |
| `PseudoClassSelector._key()` reads `name`, `argument`, `selectors` | read the code — corrected my first draft, which said two fields |
| `input`/`button`/`select`/`textarea`/`iframe`/`canvas`/`video` appear in no `UA_CSS` selector; `img`/`picture`/`map`/`area` do | grepped `UA_CSS` |
| `tokenize()` wraps `_tokenize()`; the wrapper is not itself a generator | read both |
| seven `_ascii_lower` implementations, two shapes | grepped `src/` |
| `style_document` was never in `cssparse/__init__.py` | `git log -p --follow`, 0 hits |
| U+212A is accepted before the fix, rejected after; ASCII folding still works | `parse_declaration_value` on `blocK`, `pinK`, `BLOCK`, `PINK`, `5PX`, `RGB(1,2,3)` |

## Fixes

**I1 — shorthand reset no-ops on an uppercase property name.** Fixed *inside*
`_reset_omitted_longhands` rather than at its two call sites, so a third call
site cannot reintroduce it. The boundary fix is the larger half: `values.py`
now exports `normalize_property_name`, states the normalisation above its
deviation list, and records it as deviation 12. `cascade.py` imports it — a
public name, not a private one.

**I2 — `font-size` never counted.** `_compute_style` now carries
`font_size_applied`. Moves the metric legitimately: wikipedia
`declarations_applied` 14776 → 14850, example 30 → 31, hn unchanged (it applies
no `font-size`). The CSV is gitignored, so nothing committed moves. Documented
as cascade deviation 11, including that older CSVs are low.

**I3 — inline `style=` parse errors unrecorded.** `_parse_inline_style` now
counts off the tokenizer that actually ran and off `parser.errors`. Does *not*
move any baseline: all three corpus pages still read 0/0, because none of their
237+37 inline styles is malformed. Documented as cascade deviation 12.

**I4 / minor J — the `!important` × shorthand-reset axis.** Six tests, all five
orderings plus `currentcolor` through an important reset, values executed
first. Verified by injection against a `/tmp/shadow` copy (`__file__` confirmed,
deleted after): giving reset-filled longhands the *normal* rank fails exactly
`test_specificity_still_breaks_ties_between_two_important_shorthands` and
nothing that existed before — the precise gap the review named. Giving them the
*important* rank fails `test_a_normal_shorthand_after_an_important_one_resets_nothing`.

**Kelvin sign.** Ten `str.lower()` sites in `values.py` → `_ascii_lower`.
Deviation 12. Injecting `return text.lower()` fails the new test.

**Minors E, H, and the consistency batch.** `tokenizer.py:56` self-contradiction;
`matching.py`'s An+B tokenization paragraph rewritten around the real token
streams; `matching.py` deviations reordered to 12, 13, 14; `selectors.py`
deviation 10 amended with the sanctioned `_an_b_memo` exception; `tokenizer.py`
deviation 4 reassigned to task H; `ua.py`'s omission bullet corrected;
`cssparse/__init__.py` now exports `style_document` and the rest of the six
modules' public surface.

**Scope honesty.** The nine-property boundary is now `values.py` deviations 13
and 14, with `test_longhands_of_the_supported_shorthands_are_not_supported` and
`test_display_is_a_closed_keyword_allow_list` pinning both.

## Consciously not done

Per the dispatch: Phase 3 minors A (`metrics.read`'s `run_id` heuristic), D
(`annotate_positions` docstring), I (`expand_shorthand`'s bare `KeyError`);
minor G (gitignored report); and the `_ascii_lower` consolidation. All five are
now written into the plan's **Known Gaps Carried Into Phase 3** as items 8–13,
where item 10 records that the count is seven, not six, because this wave added
`values.py`'s.

I did not re-scope `error_report.py` to gate the ~70 disagreements outside
`tests1.dat` — the review calls that deliberate, and it is a Task K decision,
not a merge gate.
