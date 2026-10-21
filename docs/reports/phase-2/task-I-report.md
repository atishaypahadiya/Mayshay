# Task I report: property values

## Steps taken

1. **Read the contract.** Read `src/mayshay/cssparse/tokenizer.py` and
   `src/mayshay/cssparse/parser.py` in full, including their numbered
   deviation lists, before writing any code. Key facts consumed:
   `Declaration.value` is a flat `list[CssToken]` with no tree, `!important`
   already stripped; token dataclasses carry `pos` (unused here); `Number`
   stores `int` for integer literals and `float` otherwise (so
   `Length(10, "px").value` is `10`, not `10.0`); `EOFToken` is a real class
   distinct from the `EOF` sentinel.
2. **Confirmed environment safety first**, before writing anything:
   `git status` clean on `phase-2-css-to-styled-tree`; `.pth` file already
   points at `/Users/atishaypahadiya/projects/mayshay/src`; baseline suite
   run gave `6366 passed, 72 xfailed`; `scripts/conformance_report.py` gave
   `780/1592`, `64/112`.
3. **Wrote `src/mayshay/cssparse/values.py`** (see contents for the full
   deviation list, documented in the module docstring numbered 1-11).
4. **Wrote `tests/cssparse/test_values.py`**: the brief's Step 1 tests
   verbatim, plus 16 supplementary tests (listed below under injection
   verification, since each was chosen specifically to catch a bug the
   brief's own tests would miss).
5. **Ran the new tests, then the full suite, then conformance**, confirmed
   nothing else moved.
6. **Verified test discriminating power by injection** against a
   `PYTHONPATH`-shadowed scratch copy (never touching the real `src/` or
   `.venv/`) — see the dedicated section below.
7. **Committed** on `phase-2-css-to-styled-tree`.

## Exact test command and output

```
$ .venv/bin/pytest -o addopts="" tests/cssparse/test_values.py -v
```

Note on `-o addopts=""`: this repo's `pyproject.toml` sets
`addopts = "-q"`, and under the installed pytest 9.1.1 that suppresses the
final summary line entirely (progress dots only, no `"N passed"` line) —
confirmed this is a pytest-version behavior, not a project misconfiguration,
by running the same file with plain `-v` (summary appears) vs. plain `-q`
(it doesn't). `-o addopts=""` clears the forced bare `-q` so the summary
prints; it changes no test's behavior, only reporting verbosity.

All 25 tests in the new file passed:

```
25 passed in 0.03s
```

Full suite:

```
$ .venv/bin/pytest -o addopts="" -q
6391 passed, 72 xfailed in 3.73s
```

(6366 baseline + 25 new = 6391; 0 failed; 72 xfailed unchanged.)

Conformance, unmoved:

```
$ .venv/bin/python scripts/conformance_report.py
all files: 780/1592
tests1.dat: 64/112
```

`git status`: clean except the two new files, now committed at
`fd15b3e`. `.venv/lib/python3.13/site-packages/__editable__.mayshay-0.1.0.pth`
still reads `/Users/atishaypahadiya/projects/mayshay/src`, and
`python -c "import mayshay; print(mayshay.__file__)"` resolves inside this
checkout.

## How percentages and auto are represented, and why it survives to Phase 3

`Percent(value)` and the singleton `AUTO` (an instance of `_Auto`, a frozen
dataclass) are returned as-is from `parse_declaration_value` — never
converted to a float, never coerced toward zero. `width: 50%` produces
`{"width": Percent(50)}`; `width: auto` produces `{"width": AUTO}` (checked
by identity, `is AUTO`, since it is a true singleton). Neither carries any
notion of "50% of what" — that computation needs a containing block, which
does not exist until Phase 3's layout stage runs the box tree. Any consumer
(Task J's cascade, later Phase 3 layout) that wants a resolved length must
explicitly branch on `isinstance(x, Percent)` / `x is AUTO` and supply the
containing-block dimension itself; there is no code path in this module
that can silently do that resolution early, because the module never has
the containing block to resolve against in the first place.

## Properties and value forms handled

- **display**: single `Ident` from a fixed keyword set (block, inline,
  inline-block, none, flex, inline-flex, grid, inline-grid, list-item,
  table, table-row, table-cell, contents) → `Keyword(name)`.
- **width / height**: `<length>` (fixed unit allowlist), `<percentage>`, or
  `auto` → `Length`, `Percent`, or `AUTO`. Exactly one token; unitless
  nonzero numbers are invalid; unitless `0` → `Length(0, "px")`.
- **font-size**: `<length>`, `<percentage>`, or an absolute/relative size
  keyword (xx-small … xxx-large, smaller, larger) kept as `Keyword(name)`
  — also symbolic, since resolving it needs a reference table Phase 3 owns.
  No `auto`.
- **margin**: 1-4 space-separated `<length> | <percentage> | auto`
  components, expanded via the one-to-four-value rule to
  `margin-{top,right,bottom,left}`.
- **padding**: same shorthand shape as margin, minus `auto` (spec-correct —
  padding has no `auto`).
- **border**: `<width> <style> <color>` in any order, at most one of each
  kind (two lengths, or a duplicate style, invalidates the whole
  declaration); expands to `border-{side}-{width,style,color}` for all four
  sides, but only for components actually present (`border: solid` sets
  only the four `*-style` keys — see deviation 7 below).
- **color / background-color**: named keyword, `#rgb`, `#rgba`, `#rrggbb`,
  `#rrggbbaa`, `rgb()`/`rgba()` (comma syntax, `<number>` or `<percentage>`
  per channel) → `Color(r, g, b, a)`; `transparent` → `Color(0,0,0,0.0)`;
  `currentcolor` → `Keyword("currentcolor")` (kept symbolic, same principle
  as `Percent`/`AUTO` — see deviation 5).

## Deviations (also in the module docstring, numbered 1-11)

1. Length units are a fixed allowlist (px, em, rem, ex, ch, vw, vh, vmin,
   vmax, cm, mm, q, in, pt, pc) — an unrecognized unit invalidates.
2. Unitless nonzero lengths are invalid, full stop; quirks-mode coercion is
   a Phase-3 layout concern, not smuggled in here.
3. CSS-wide keywords (`inherit`/`initial`/`unset`/`revert`) are not
   recognized by any of the nine grammars — cascade-time concepts requiring
   information (initial values, parent computed values) this module lacks.
4. The named-color table is the 16 original CSS1/HTML keywords (with the
   green/lime distinction correct) plus a handful of common extras
   (orange, pink, brown, cyan, magenta, grey) and `transparent`/
   `currentcolor` — not the full ~148-keyword CSS4 table.
5. `currentcolor` is preserved as `Keyword("currentcolor")`, not resolved —
   it names this element's cascaded `color`, information this module
   doesn't have. `transparent` is resolved eagerly since it needs no
   context.
6. `rgb()`/`rgba()` support only the legacy comma syntax with `<number>` or
   `<percentage>` channels — not CSS4 space/slash syntax, not
   `hsl()`/`hwb()`/`lab()`/`lch()`/`color()`.
7. Border's missing components are simply absent from the output — no
   synthesized `medium`/`currentcolor` initial-value fallback. Manufacturing
   those here would bake a cascade-independent guess into a value that
   Task J's cascade is better positioned to fill in (it has inheritance and
   prior declarations to consult).
8. `border-width` accepts only `<length>` — not `thin|medium|thick`, not
   `<percentage>` (correctly, per spec).
9. `padding` has no `auto` (spec-correct; only `margin` does).
10. No `calc()`, `var()`, or custom-property support anywhere — invalid,
    declaration dropped.
11. Component splitting (`_split_top_level`, `_split_args`) is a
    ~30-line hand-rolled top-level-whitespace/comma splitter, deliberately
    not an import of `cssparse.parser`'s private `_consume_component_value`
    — cross-module coupling to another module's underscore-prefixed
    internals seemed worse than re-deriving the small amount of logic this
    module actually needs (only one bracketed construct, a color function's
    argument list, ever appears in these nine properties' values).

## Where the brief was underspecified

- **`expand_shorthand`'s `parsed` argument shape is not spelled out.** The
  brief gives the signature `expand_shorthand(name, parsed) -> dict` but
  never says what `parsed` looks like. I designed it as: `list[object]` of
  1-4 values for margin/padding (mirroring the one-to-four-value rule
  directly), and `dict` with any subset of `{"width", "style", "color"}`
  keys for border. `parse_declaration_value` calls it internally after its
  own per-property component parsing; it's also exercised directly by
  `test_expand_shorthand_margin_one_to_four_value_rule_directly` since nothing
  in the brief's own tests calls it standalone despite it being a named
  public interface.
- **Whether `parse_declaration_value` returns the shorthand's raw name or
  the expanded longhands was implicit, not stated.** The brief's own test
  code (`got["margin-top"]` immediately after `val("margin", ...)`) makes
  clear the expansion happens *inside* `parse_declaration_value`, but the
  brief's prose never says so outright — worth flagging since a reasonable
  first reading of the interface list alone (`parse_declaration_value` and
  `expand_shorthand` as two separate, unconnected functions) would produce
  a `{"margin": [...]}` result that fails every shorthand test.
- **Partial/duplicate border components and CSS-wide keywords are entirely
  unaddressed** by the brief — the test list has exactly one border case
  (`"1px solid red"`, canonical order, all three components present). I
  made and documented explicit choices (deviations 3 and 7 above) rather
  than leaving the behavior accidental.
- **Border's "any order" claim is asserted in prose but not tested** by the
  brief's own test list — `test_border_shorthand_expands_to_width_style_color`
  only exercises canonical order. I added
  `test_border_components_may_appear_in_any_order` and
  `test_border_rejects_duplicate_component_kind` to actually pin the claim
  the brief makes; see the injection section, bug 4, where a
  fixed-positional-order implementation passes the brief's own test but
  fails these.

## Injection verification

Shadowed a scratch copy at `/tmp/shadow_mayshay/src`, confirmed resolution
with:
```
PYTHONPATH=/tmp/shadow_mayshay/src .venv/bin/python -c \
  "import mayshay.cssparse.values as v; print(v.__file__)"
# -> /tmp/shadow_mayshay/src/mayshay/cssparse/values.py
```
then injected each bug into the shadow only, ran
`PYTHONPATH=/tmp/shadow_mayshay/src .venv/bin/pytest -o addopts="" tests/cssparse/test_values.py`,
confirmed the expected test(s) failed, then restored the shadow from a
saved original (diffed identical afterward) before moving to the next bug.
The real `src/mayshay/cssparse/values.py` was never touched by any of this.
After all injections, `diff` confirmed the shadow and the real file were
byte-identical again, and `git status` on the real repo stayed clean
throughout.

| # | Bug injected | Wrong implementation this rules out | Test(s) that caught it |
|---|---|---|---|
| 1 | `Percentage` token collapsed to `Length(value/100, "px")` | Silently resolving a percentage against an assumed 100-unit reference instead of staying symbolic | `test_percentage_stays_symbolic`, `test_margin_percent_and_auto_mixed` |
| 2 | `auto` collapsed to `Length(0, "px")` | Treating `auto` as "zero" rather than a distinct sentinel | `test_auto_stays_symbolic`, `test_margin_percent_and_auto_mixed` |
| 3 | 3-value margin/padding rule miswired (`top,right,left = values; bottom = top`) | The classic off-by-one in the one-to-four-value expansion | brief's own `test_margin_shorthand_expansion[1px 2px 3px-...]`, plus `test_expand_shorthand_margin_one_to_four_value_rule_directly` |
| 4 | Border parsed as fixed positional `width, style, color` (zip against 3 slots) instead of any-order | An implementation that only ever handles the canonical order, contradicting the brief's explicit "any order" requirement | **not** caught by the brief's own `test_border_shorthand_expands_to_width_style_color` (canonical order, passes); caught by my `test_border_components_may_appear_in_any_order` and `test_border_partial_component_only_sets_that_kind` |
| 5 | `green`/`lime` RGB tuples swapped in the keyword table | The exact real-world color mistake the brief calls out by name | `test_green_is_not_lime` — **not** caught by the brief's own `test_color_keyword_hash_and_function`, which only checks `red` |
| 6 | Unitless-length guard widened to accept *any* unitless number as px (overcorrection of deviation 2) | A fix for "reject bad units" that overshoots into "accept all unitless numbers" | brief's own `test_unitless_nonzero_length_is_invalid` |
| 7 | Invalid `width`/`height` returns `{}` instead of `None` | Confusing "no value could be parsed" with "an empty-but-valid dict", which would make `"width" in result` checks lie | brief's own `test_invalid_value_drops_the_declaration`, plus my `test_width_rejects_multiple_tokens` |

For every hand-written test in the file (brief's and mine), I named a wrong
implementation before writing the assertion and confirmed at least one test
would fail against it; the table above lists the ones actually run through
injection. Tests not separately injected (e.g.
`test_padding_does_not_accept_auto`, `test_transparent_and_currentcolor`,
`test_hex_color_short_and_long_with_alpha`, `test_rgb_function_with_percentage_channels_and_alpha`,
`test_unknown_color_keyword_is_invalid`, `test_unknown_display_keyword_is_invalid`)
are each a single, direct grammar-branch check (one `if`/`elif` in the
implementation gates each), where the "wrong implementation" and "the code
that would need to be wrong for this to falsely pass" are the same three
lines — I judged the seven above to be the ones with a real chance of a
subtler, multi-line bug slipping through unnoticed, which is where the
injection exercise earns its keep.

## What a reviewer should scrutinise hardest

1. **The border "at most one of each kind" duplicate check** — a length
   that fails `_parse_length` falls through to being checked as a color,
   and vice versa is not possible (color check only trips on `Ident`/`Hash`/
   `Function`), but it's worth re-deriving by hand that `1px 2px solid red`
   really can't be misread as `width=1px, color=(somehow)2px`. It cannot
   (2px is a `Dimension`, not a valid color token), but this is the densest
   piece of branching in the file.
2. **`_split_top_level`'s depth tracking** — it increments on `Function` and
   decrements on `RParen` without also tracking `LParen`/`RParen` pairs that
   aren't part of a function (bare parens can't appear in any of these nine
   properties' values today, so this is untested territory that would need
   revisiting if `calc()` is ever added).
3. **The `expand_shorthand` public contract** — I inferred its argument
   shape (see "underspecified" section above); if Task J expects a
   different shape (e.g., a dict for margin/padding instead of a list),
   that's a compatibility gap worth catching before Task J is written
   against the shape I chose.
4. **Deviation 7's "no initial-value synthesis for partial border"** — this
   is a real design choice with consequences for Task J: a stylesheet with
   `border: solid` alone will produce a dict with *only* `border-*-style`
   keys, and Task J's cascade needs to already know it must consult CSS's
   real initial values (`medium`, `currentcolor`) for the omitted
   `border-*-width`/`border-*-color`, rather than assuming every border
   declaration always populates all twelve keys.

---

## Fix round 1

Four items from review, addressed in order:

### Important 1 — color keyword table completeness

The table shipped with 22 entries against the CSS Color Level 4 extended
list of 148 (147 CSS3 SVG-derived keywords + `rebeccapurple`). Transcribed
the full 148-entry table into `_COLOR_KEYWORDS`, then verified rather than
trusted:

- `len(_COLOR_KEYWORDS) == 148`, confirmed both by a standalone Python
  count of the dict literal's keys (148 unique, zero duplicates — a
  duplicate key in a Python dict literal silently keeps only the last
  value, which would have made a naive `len()` check pass even with a
  transcription collision) and by loading the real module.
- Spot-checked ten values against known-correct hex codes before writing
  the file (`rebeccapurple`→`#663399`, `papayawhip`→`#ffefd5`,
  `mediumspringgreen`→`#00fa9a`, `darkslategrey`→`#2f4f4f`,
  `cadetblue`→`#5f9ea0`, `cornflowerblue`→`#6495ed`,
  `lightgoldenrodyellow`→`#fafad2`, `yellowgreen`→`#9acd32`, plus
  `green`→`#008000` and `lime`→`#00ff00` to re-confirm the trap survived
  the rewrite) — all matched, no disagreement to report.
- The count landed exactly on 148, not "~148" — no finding to report
  there either; the transcription matches the spec's list as commonly
  published (147 keywords + `rebeccapurple` from CSS Color 4).
- Added `test_color_keyword_table_is_complete` (pins the count via the
  private table, then round-trips six non-famous keywords through the
  public `parse_declaration_value` API, not just the dict, so a bug in the
  *lookup* path would also be caught, not only a bug in the *data*).
  Verified by injection (see below).
- `transparent`/`currentcolor` remain outside this table, on purpose —
  they are the spec's own special keywords, not named colors, and are
  handled by dedicated branches already covered by
  `test_transparent_and_currentcolor`.

### Important 2 — unified `expand_shorthand` calling convention

Decided to **unify the input shape to `dict[str, object]` for every
shorthand**, rather than leave margin/padding on a positional `list` and
border on a `dict`. Concretely:

- `_parse_margin_or_padding` now returns `{"top"/"right"/"bottom"/"left": value}`
  (always all four keys — the one-to-four-value rule always resolves every
  side) instead of a bare `list`. The one-to-four expansion logic moved
  into a new `_sides_from_values` helper that produces this dict directly.
- `expand_shorthand(name, parsed)` now takes `dict[str, object]`
  unconditionally: `{"top"/"right"/"bottom"/"left": value}` for
  `margin`/`padding`, or any subset of `{"width"/"style"/"color": value}`
  for `border`.

What was **not** unified, deliberately: the *fan-out* still differs
per-shorthand (a margin key maps to exactly one longhand; a border key
maps to four, one per physical side) — documented in `expand_shorthand`'s
own docstring as a real difference in what the CSS properties mean, not
an accident of this module's design. Unifying the input shape gives
Task J (and any future shorthand) one predictable thing to construct — a
dict from the shorthand's own component names to parsed values — without
pretending margin and border expand the same way, which they don't in the
spec either.

Updated `test_expand_shorthand_margin_one_to_four_value_rule_directly`
(renamed `test_expand_shorthand_is_dict_in_dict_out_for_every_shorthand`)
to call `expand_shorthand` with dict arguments for all three shorthands,
including a border case. Verified by injection (see below).

### Important 3 — `test_display_keywords` now discriminates on its own

Rewrote the test to check two different keywords (`block` and `inline`)
and that they differ, rather than a single hardcoded value. Verified by
injection: a `_parse_display` returning `Keyword("block")` for any
recognized keyword now fails this test directly, without needing
`test_unknown_display_keyword_is_invalid` to catch it as a bystander.

### Minor — direct tests for padding-percent, font-size-percent, border currentcolor

Added `test_padding_percent`, `test_font_size_percent`, and
`test_border_color_currentcolor`. Each was previously "correct by
inspection" only (the code path is shared with already-tested cases, but
no test named it or exercised that specific combination directly).

## Fix round 1 — injection verification

Re-shadowed a fresh scratch copy at `/tmp/shadow_mayshay/src`
(re-verified `__file__` resolution before each run, as before), injected
one bug per fix item, confirmed the intended test failed, restored from a
saved original, and diffed the shadow back to identical before moving on.
The real repo was untouched throughout; `git status` and the `.pth`
checked clean/unchanged after the round, as before.

| # | Bug injected | Test(s) that caught it |
|---|---|---|
| A | `_parse_display` hardcoded to always return `Keyword("block")` for any recognized keyword | `test_display_keywords` alone (previously would have needed `test_unknown_display_keyword_is_invalid`, which does not exercise this path) |
| B | Removed `cadetblue`, `rebeccapurple`, `mediumspringgreen` from `_COLOR_KEYWORDS` (regression toward the old incomplete table) | `test_color_keyword_table_is_complete` — count assertion failed (`145 == 148`) before the spot-check loop even ran |
| C | `expand_shorthand("margin"/"padding", parsed)` reads `parsed["top"]` for every side instead of `parsed[side]` | `test_expand_shorthand_is_dict_in_dict_out_for_every_shorthand`, the brief's own `test_margin_shorthand_expansion` (3 of 4 parametrized cases), and `test_margin_percent_and_auto_mixed` |

## Fix round 1 — final verification

```
$ .venv/bin/pytest
6395 passed, 72 xfailed in 3.67s

$ .venv/bin/python scripts/conformance_report.py
all files: 780/1592
tests1.dat: 64/112
```

Confirmed (and corrected in this round): the ini's `addopts = "-q"` alone
prints the summary line fine, with plain `.venv/bin/pytest` and no extra
flags — the earlier report's `-o addopts=""` workaround was chasing a
self-inflicted problem (stacking a second `-q` on the command line on top
of the ini's own, which raises verbosity to -2 and suppresses the
summary). No project or pytest defect; nothing to work around.

`git status` clean after commit; `.venv/lib/python3.13/site-packages/__editable__.mayshay-0.1.0.pth`
unchanged (still `/Users/atishaypahadiya/projects/mayshay/src`); `import mayshay`
resolves inside this checkout.
