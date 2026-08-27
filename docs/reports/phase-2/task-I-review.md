# Task I review: property values

## Spec Compliance

✅ Spec compliant for the nine properties' required grammars, shorthand
expansion, symbolic preservation of `auto`/`%`, and documented deviations.
All Step-1 brief tests present verbatim
(`tests/cssparse/test_values.py:674-729`). No forbidden libraries imported
(`src/mayshay/cssparse/values.py:131-143` imports only from
`mayshay.cssparse.tokenizer`).

⚠️ Cannot verify from diff: whether Task J actually needs to call
`expand_shorthand` directly with pre-parsed components (as opposed to only
consuming `parse_declaration_value`'s already-expanded output) — this
determines whether the list/dict shape split matters in practice. Task J's
brief is outside this diff.

## Findings by severity

**Important**
- Color keyword table covers ~22 of the CSS spec's ~148 extended keywords
  (`values.py:228-237`): the 16 CSS1 keywords + orange/pink/brown/cyan/
  magenta/grey + transparent/currentcolor handled separately. Spot-checked
  all 22 against spec hex values (black, silver, gray, white, maroon, red,
  purple, fuchsia, green #008000, lime #00ff00, olive, yellow, navy, blue,
  teal, aqua, orange #ffa500, pink #ffc0cb, brown #a52a2a, cyan=aqua,
  magenta=fuchsia, grey=gray) — all correct, no false members, gray/grey
  alias handled properly. But common real-world keywords (skyblue, coral,
  tomato, gold, crimson, indigo, chocolate, khaki, salmon, plum, …) are
  absent and will silently drop declarations on real pages — same failure
  mode the brief warns about, even though it is disclosed as deviation 4.
- `expand_shorthand`'s two incompatible argument shapes (`list[object]` for
  margin/padding at `values.py:573-586` vs `dict{width,style,color}` for
  border) is a real design smell: a third shorthand (e.g. `background`,
  `font`) won't cleanly fit either shape, and any caller of this "public"
  entry point (not just `parse_declaration_value` internally) must branch
  on shorthand name to know which shape to build. Worth normalizing before
  Task J locks in a calling convention, or at minimum flagging to Task J's
  author now rather than after the fact.
- A third non-discriminating brief test: `test_display_keywords`
  (`tests/cssparse/test_values.py:695-696`) only asserts `"block"` maps to
  `Keyword("block")`. An implementation that returns `Keyword("block")`
  unconditionally for any single `Ident` (ignoring `_DISPLAY_KEYWORDS`
  membership) passes this test. It is only caught by the implementer's own
  supplementary `test_unknown_display_keyword_is_invalid` (line 803-804) —
  which the report never identifies as fixing a vacuous brief test the way
  it explicitly does for the border-order and color-red cases (report
  lines 180-187, 213). The gap was patched but not recognized as the same
  class of defect the brief's own audit was supposed to be checking for.

**Minor**
- No direct test that `padding`'s percentage values stay symbolic (only
  `auto`-rejection is tested, `test_padding_does_not_accept_auto`,
  test_values.py:746-751) or that `font-size` percentages stay symbolic
  (only `1.5em` is tested, test_values.py:675-676). Traced both code paths
  by hand: `_parse_font_size` (values.py:447-453) and
  `_parse_margin_or_padding` with `allow_auto=False`
  (values.py:468-482) both route percentages through the shared
  `_parse_length_percentage`, which returns `Percent` untouched — correct,
  just untested directly.
- `currentcolor` inside `border` (e.g. `border: 1px solid currentcolor`)
  and duplicate-color rejection in border are not tested, though traced
  by hand to behave correctly (`_parse_color` returns `Keyword`, which
  `_parse_border`'s `color is not None` duplicate check treats like any
  other parsed color).
- `pyproject.toml:15`'s `addopts = "-q"` is not the cause of the missing
  summary line either report describes. Verified empirically: a bare
  invocation using only the ini's single `-q` prints the "N passed"
  summary fine, piped or interactive (`'.venv/bin/pytest tests/cssparse/test_values.py' | cat`
  → summary shown). The summary only disappears when `-q` is stacked to
  verbosity `-2` — i.e., when an agent *also* types `-q` on the command
  line on top of the ini's already-applied `-q`
  (`.venv/bin/pytest -q tests/cssparse/test_values.py` → dots only, no
  summary; confirmed the same suppression with a bare `-qq` and
  `addopts=""`). This is pytest's documented repeatable-verbosity
  behavior, not a 9.1.1 regression, not capture-dependent, and not a
  reason to remove `addopts = "-q"` — it only bites an agent who redundantly
  re-passes `-q` out of habit. Recommend telling future agents not to
  add `-q` again (the project already applies it), rather than changing
  `pyproject.toml`.

## Symbolic-value guarantee

Checked every percentage/auto-legal property: `width`/`height`
(`values.py:456-460`, shared function, `allow_auto=True`), `margin`
(`values.py:468-482`, `allow_auto=True`, tested by
`test_margin_percent_and_auto_mixed`), `padding` (same function,
`allow_auto=False`, percent still reachable since the `Percentage` branch
in `_parse_length_percentage` at line 319-320 is checked before the
`allow_auto` branch), `font-size` (`values.py:447-453`, percent reachable
via the same shared helper). None resolves eagerly to a float; all route
through `_parse_length_percentage`, which only ever returns `Percent`,
`AUTO`, or `Length` unchanged. Guarantee holds for all four properties,
though padding/font-size cases are untested (see Minor above).

## Environment check

`git status`: clean. `.venv/lib/python3.13/site-packages/__editable__.mayshay-0.1.0.pth`
still reads `/Users/atishaypahadiya/projects/mayshay/src`. `.venv/` untouched.

## Assessment

**Task quality:** Approved (fix Important items before Task J locks its
calling convention against `expand_shorthand`'s shape).

**Reasoning:** Core parsing logic is correct and unusually well-verified
(hand-run injection testing against a PYTHONPATH-shadowed copy, 7 bugs
confirmed caught). The two real risks are forward-looking, not present
bugs: an incomplete-but-documented color table that will bite on real
corpora, and an inconsistent `expand_shorthand` argument shape that Task J
should see clearly before committing to a calling convention.
