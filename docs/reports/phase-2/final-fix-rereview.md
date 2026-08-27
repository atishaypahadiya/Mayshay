# Phase 2 — scoped re-review of the final fix wave (`99d03ba..fd56f43`)

Read-only on the checkout. Every claim below was executed. Shadow copy at
`/tmp/shadow` (`__file__` confirmed `/tmp/shadow/mayshay/cssparse/cascade.py`),
deleted after. `.venv` untouched, nothing uninstalled, no oracle imported.

## Finding Verdicts

**I1 — shorthand reset no-ops on an uppercase property name.** **ADDRESSED.**
`cascade.py:322` — `_SHORTHAND_LONGHANDS.get(normalize_property_name(name))`.
The chokepoint claim is real, not rhetorical: `_SHORTHAND_LONGHANDS` is
referenced at exactly two lines in the module, its definition (`cascade.py:285`)
and that lookup, so the table cannot be consulted except through the
normalising function. Both call sites (`cascade.py:727`, `:762`) still pass the
raw `decl.name`, which is the point — they are now allowed to.

On the boundary export: `values.py:185-213` defines `_ascii_lower` and
`normalize_property_name`, `values.py:40-48` states the normalisation *above*
the deviation list rather than inside it, `values.py:807-816` exports it, and
`cssparse/__init__.py` re-exports it. It is a genuine improvement over the
status quo ante — the rule is now stateable, greppable and importable, and
`values.py:196-213`'s docstring names the exact bug the absence caused. It does
not *mechanically* prevent the next consumer inheriting the obligation: nothing
forces a caller to route a property name through it, and the only enforcement is
prose plus `test_property_names_are_normalised_and_the_rule_is_exported`. A
signature that returned the canonical name alongside the longhands would enforce
it; that is a larger change than this gate warrants. Judgment: the strongest fix
available without changing `parse_declaration_value`'s shape, and correctly the
larger half of the two.

**I2 — `declarations_applied` never counts `font-size`.** **ADDRESSED.**
`cascade.py:912/946-948`: `font_size_applied` is set only when
`_compute_font_size` returned a value, and `_compute_font_size` returns `None`
for `declared is None` (`cascade.py:517-518`), so an element with no declared
`font-size` cannot inflate the counter. The unresolvable branch still routes to
`font_size_unresolvable` and not to `applied`, pinned by
`test_an_unresolvable_font_size_counts_as_unresolvable_not_applied`. Executed on
the corpus: wikipedia `declarations_applied` 14850, example 31 — matching the
report's post-fix figures.

**I3 — `style=` parse errors unrecorded.** **ADDRESSED.** `cascade.py:753` reads
`tokenizer.metrics["parse_errors"]` off the tokenizer that actually ran, and
`cascade.py:769` adds `len(parser.errors)` — the same two lines `_parse_sheet`
uses at `cascade.py:705-706`, now with the object confusion removed. The parser
is freshly constructed per inline style, so no cumulative double count.

**I4 — the `!important` × shorthand-reset axis is uncovered.** **ADDRESSED, and
the tests discriminate.** Six orderings plus three case-folding tests at
`tests/cssparse/test_cascade.py:1180-1373`. Reproduced the report's injection,
normal-rank direction: giving reset-filled longhands `_NORMAL_RANK[origin]`
while declared longhands keep the declaration's rank yields **1 failed, 99
passed** on `tests/cssparse/test_cascade.py`, the single failure being
`test_specificity_still_breaks_ties_between_two_important_shorthands`
(`Length(5.0,'px') != Length(3,'px')`) and nothing pre-existing. Also reproduced
the I1 injection (reverting `cascade.py:322` to the raw lookup): **2 failed, 131
passed** across `test_cascade.py` + `test_values.py`, exactly
`test_the_shorthand_reset_fires_on_an_uppercase_property_name` and
`test_an_uppercase_shorthand_resets_at_important_rank_too` — with
`test_an_uppercase_margin_shorthand_expands_to_all_four_sides` green, precisely
as its own docstring discloses.

**Kelvin sign — ten `str.lower()` → `_ascii_lower`.** **ADDRESSED, and every
conversion is correct.** Site-by-site: `values.py:458` a `<dimension>` unit,
`:471` the `auto` ident, `:522` a function name (`rgb`/`rgba`), `:564` a
`<color>` keyword ident, `:592`/`:593` a `display` ident, `:601`/`:602` a
`font-size` ident, `:680` a `<line-style>` ident, `:213` a property name via
`normalize_property_name`. All ten are CSS identifiers, units, function names or
property names — every one of them ASCII-case-insensitive by css-syntax-3 §3.
None handles user-authored text, and none is an HTML attribute *value*
comparison, which is the case that could legitimately want different folding.
Confirmed by grep that no `.lower()` call remains in `values.py`. No regression
wearing a fix's clothes here.

**Minor E — `tokenizer.py:56` self-contradiction.** **ADDRESSED.**
`tokenizer.py:55-56` now reads "`tokenize()` returns a generator (it is a plain
method wrapping the `_tokenize()` generator …)". Executed:
`inspect.isgeneratorfunction(CssTokenizer.tokenize)` is `False`,
`…(CssTokenizer._tokenize)` is `True`. Line 466/488 now agree with line 55.

**Minor H — `matching.py:83-84` wrong tokenization fact.** **ADDRESSED, and the
replacement is true.** `matching.py:78-105` now gives the three token streams
explicitly. Executed against `CssTokenizer`: `2n+1` → `Dimension, Number`;
`2n +1` and `2n 1` → `Dimension, Whitespace, Number`; `2n + 1` → five tokens
(`Dimension, Whitespace, Delim, Whitespace, Number`). Executed through
`_parse_an_b`: all four accepted forms yield `(2, 1)`; `2n + -1`, `+ n` and
`+-n` all yield `None`. Every sentence in the rewritten paragraph checks out.

**Consistency batch — cross-references.** **ADDRESSED.** `matching.py`
deviations now read 10, 11, 12, 13, 14 in file order (lines 124, 134, 138, 142,
149) with the numbers still attached to their original content, so both existing
cross-references survive: `matching.py:532` "see deviation 14" → the `_an_b_memo`
entry at :149; `matching.py:761` "see deviation 13" → the `candidates()` ordering
entry at :142. `selectors.py:152-162` now carries the sanctioned exception and
names the three fields correctly — verified `PseudoClassSelector._key()`
(`selectors.py:330-331`) returns `(name, _argument_key(argument), selectors)`.
`tokenizer.py:49-53` reassigns `is_integer` to task H; grepped, five consumers,
all in `matching.py` (`:604, :610, :638, :664, :672`), zero in `values.py`.
`ua.py:37-45`: grepped `UA_CSS`, none of `input`/`button`/`select`/`textarea`/
`iframe`/`canvas`/`video` appears in any selector, and `img`/`picture`/`map`/
`area` all do. `cssparse/__init__.py` — `set(__all__) - set(dir(module))` is
empty, `__all__` is sorted with no duplicates, and no import cycle is introduced
(`mayshay.dom` does not import `cssparse`).

## The implementer's self-disclosure

**Verified: `len(_DISPLAY_KEYWORDS)` is 20.** Executed against the installed
package. `values.py:159` ("20 entries, above -- counted by
`len(_DISPLAY_KEYWORDS)`, not by eye"), the plan's Known Gap 9 and
`test_display_is_a_closed_keyword_allow_list`'s `assert len(...) == 20` all
agree with the code.

Spot-checked four further executed claims, all reproduced exactly:
- **85 of wikipedia's 313 dropped declarations are longhands of the three
  supported shorthands.** Instrumented `parse_declaration_value` over
  `data/corpus/wikipedia.html`: 313 total drops, matching the metric, and the
  longhand family sums to exactly 85 — with all five itemized counts right
  (15 `padding-right`, 14 `margin-top`, 12 `background`, 8 `margin-bottom`,
  7 `border-left`). The 85th is `border-left-style`, which I initially missed.
- **`flow-root` is the sole dropped `display` value.** 1 drop, value `flow-root`.
- **`tokenize()` wraps `_tokenize()` and is not itself a generator.** Confirmed
  by `inspect`.
- **`style_document` was never in `cssparse/__init__.py`.**
  `git log --all -S"style_document" -- src/mayshay/cssparse/__init__.py` returns
  one commit, `fd56f43` — this one.

The discipline was applied, not merely reported.

## The two corrections to the previous review

**"`data/metrics/*.csv` is gitignored, so I2 was emitted-but-wrong, not
committed-but-wrong."** **Confirmed.** `.gitignore:12` is `data/metrics/*.csv`;
`git ls-files data/metrics` returns only `.gitkeep`; `git check-ignore -v` names
that rule for `data/metrics/cssparse.csv`. The correction stands and the review's
"committed measurement" wording was the looser of the two.

**"I3 moves no baseline; none of the corpus's inline styles is malformed."**
**Confirmed.** Ran `_parse_inline_style` over every `style=` attribute in all
three corpus pages: 0 tokenizer errors and 0 CSS parse errors, on 340 attributes
in wikipedia and 37 in hn (example has none). Both premises hold.

One detail inside the second: the "237 inline `style=` attributes" figure,
inherited from the review and now written into `cascade.py:161-163` and
`_parse_inline_style`'s docstring, is the count of *non-empty* style attributes.
wikipedia.html has **340** `style=` attributes, of which 237 carry any CSS.
The number is the right one to quote for this purpose; the sentence around it is
not precise about which number it is.

## New Breakage in the Fix Diff

**None Critical or Important.**

- **Minor** — `cascade.py:161-163` and `cascade.py:740-748`: "wikipedia.html has
  237 inline styles" / "237 of those attributes". Executed: 340 `style=`
  attributes, 237 of them non-empty. Add "non-empty" or quote 340.
- **Minor** — `docs/plans/2026-08-26-phase-2-css-to-styled-tree.md`, Known Gaps
  item 10: two of the seven cited line numbers are stale.
  `cssparse/tokenizer.py:126` is actually `:127`; `cssparse/values.py:183` is
  actually `:185`. The other five (`parser.py:202`, `selectors.py:239`,
  `matching.py:210`, `treebuilder.py:202`, `htmlparse/tokenizer.py:64`) are
  exact, and the count of seven is right. This is the documentation-fix wave
  producing a small new inaccuracy in the same batch that corrects several —
  the pattern the review flagged, at its least harmful magnitude.
- **Minor, in the report rather than the repo** — the report says "All five are
  now written into the plan's **Known Gaps** as items 8–13." Items 8–13 are six
  entries, two of which (the longhand boundary and the `display` allow-list) are
  scope items rather than deferred minors, and minor G is correctly absent
  because its triage verdict was "no action". The list itself is right; the
  sentence describing it is not.

## Out-of-Scope Observations

- `cascade.py:792` (`rel` tokens) and `cascade.py:829` (the `type` attribute)
  still use `str.lower()`. Both are HTML attribute values compared ASCII-case-
  insensitively per the HTML spec, so `_ascii_lower` is the correct tool there
  too. Unreachable in practice — neither `stylesheet` nor `text/css` contains a
  character with a non-ASCII fold — and outside the fix diff. It does mean the
  review's Minor 1 premise ("`values.py` is the only `cssparse` module that uses
  `str.lower()`") was itself wrong by two sites. Fold into Known Gap 10's
  `_text.py` refactor.
- The working tree has an **uncommitted** modification to `CLAUDE.md` adding two
  process rules (execute-every-factual-claim; write non-ASCII test data as
  escapes). Not mine — I made no edits. It is not in `fd56f43` and not in the fix
  diff, so the report's "`git status` clean apart from the ten files of this
  change" is inaccurate by one file, and this content does not reach `main`
  unless it is committed. The first added bullet is also indented one level too
  deep, nesting it under the submodule bullet.

## Verdict

**Fix round: all findings addressed, no new Critical or Important breakage.**

Every item in scope — I1 through I4, the Kelvin sign, minors E and H, the scope
boundary and the consistency batch — is addressed in the specific sense that the
defect no longer exists, verified by execution rather than by reading. The two
tests the round turns on discriminate in both injected directions, failing
exactly the intended test and nothing else. The self-disclosed miscount is
corrected everywhere it appears. Three Minors remain, all documentation-precision
and none merge-blocking; the uncommitted `CLAUDE.md` should be committed or
dropped deliberately before the branch is finished.

Repo state after this review: `git status` shows only the pre-existing
`CLAUDE.md` modification, branch `phase-2-css-to-styled-tree`,
`.venv/lib/python3.13/site-packages/__editable__.mayshay-0.1.0.pth` reads
`/Users/atishaypahadiya/projects/mayshay/src`, `/tmp/shadow` removed.

**Merge-ready: yes.**
