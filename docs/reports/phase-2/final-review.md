# Phase 2 — final whole-branch review (`f252f96..113c1ba`)

Read-only pass. Repo state verified before and after: `git status` clean,
`.venv/.../__editable__.mayshay-0.1.0.pth` still `/Users/atishaypahadiya/projects/mayshay/src`,
`.venv/bin/pytest` = **6483 passed, 72 xfailed**. All four headline numbers reproduce
from the committed scripts: conformance **780/1592** and **64/112**, parse-error
agreement **404/474** (extra 49 / missing 27). The one modified-implementation
experiment was run against a `/tmp/shadow` copy on `PYTHONPATH`, `__file__` verified,
and deleted.

## Strengths

- **Cross-module value contracts genuinely agree.** `values._LENGTH_UNITS` (15 units)
  and `cascade`'s `_ABSOLUTE_PX | _EM_MULTIPLE | {rem} | _VIEWPORT_UNITS` are set-equal
  in both directions — checked by execution, not by reading. `_length_to_px` raises on
  anything outside, so a future unit added on one side fails loudly.
- **`RuleIndex`'s superset contract holds on real input.** I ran every element ×
  every rule on `wikipedia.html` (242 rules × 1500 elements = 363,000 pairs):
  **0 rules that `matches()` accepts were absent from `candidates()`**. That is the
  one direction where a bug is silent, and it is clean.
- **The `!important` × shorthand-reset axis is behaviourally correct.** Five orderings
  executed directly (important-then-normal, normal-then-important, important vs
  higher-specificity-important, important author vs normal inline, important inline vs
  important author, plus `currentcolor` propagation through an important reset) all
  match browser cascade semantics.
- **The two `em` bases are separated structurally, not carefully** — `_compute_font_size`
  has no own-font parameter, `_compute_rest` has no parent parameter. This is the right
  shape for the one error the module exists to avoid.
- **The nine-property scope is mostly honest, and the corpus proves it.** Of the
  313 declarations dropped on wikipedia, every drop inside the nine properties traces
  to a *documented* deviation: `inherit` (dev 3, 17), `var()` (dev 10, 4), unitless
  nonzero length (dev 2, 1), `display: flow-root` (1). No property is half-implemented
  within its own grammar.
- `tests/test_environment.py` enforcing the `tinycss2`/`cssutils`/`cssselect` ban and
  the editable-install pointer is the correct response to Phase 1's incident. Verified:
  no oracle library is imported anywhere in `src/`, `tests/` or `scripts/`.

---

## Issues

### Critical

None.

### Important

**1. Shorthand reset silently no-ops on an uppercase property name.**
`src/mayshay/cssparse/cascade.py:698` and `:720`

Both call sites pass the raw `decl.name` into `_reset_omitted_longhands`, which looks it
up in `_SHORTHAND_LONGHANDS` verbatim. `parse_declaration_value` lowercases its own
`name` argument (`values.py:689`), so the *value* parses fine — but the reset is skipped.
CSS property names are ASCII case-insensitive, so this is a silent wrong computed value.

Verified against the installed package:

```
p{border:5px solid red} p{border:solid blue}   -> border-top-width 3px   (correct)
p{border:5px solid red} p{BORDER:solid blue}   -> border-top-width 5px   (wrong)
```

This is the branch's headline feature failing on legal input, and it is exactly the
"the obligation was handed over but the two sides' case-folding contracts disagree"
shape that Task I → Task J already fell through once. Zero occurrences in the three
saved corpus pages, so it is not currently observable in the committed metrics — which
is what makes it worth fixing now rather than after it starts mattering.

Fix and verification: `_reset_omitted_longhands(decl.name.lower(), longhands)` at both
sites. Applied to a `/tmp/shadow` copy: the uppercase case yields 3px, and the suite is
**6482 passed, 72 xfailed** with the only failure being `test_engine_imports_from_this_repo`
correctly detecting the shadow. (Prefer `_ascii_lower` — see Minor 1.)

**2. `declarations_applied` never counts `font-size`.**
`src/mayshay/cssparse/cascade.py:534`

`_compute_rest` `continue`s on `font-size` without incrementing `applied`, and
`_compute_style`'s `applied + int("color" in declared)` adds back only `color`. So every
successfully applied `font-size` declaration is missing from the metric. Verified:

```
p{font-size:20px}                     -> declarations_applied 12  (baseline 12, +0)
p{color:red}                          -> 13  (+1)
p{width:10px}                         -> 13  (+1)
p{font-size:20px;color:red;width:10px}-> 14  (+2, font-size contributes 0)
```

Nothing documents this exclusion. It is a committed measurement that is systematically
low, in the module whose stated purpose is producing numbers for the analysis half of
the project. One-line fix (count it in the `font-size` branch of `_compute_style`, next
to `font_size_unresolvable`).

**3. CSS parse errors from `style=` attributes are never recorded.**
`src/mayshay/cssparse/cascade.py:705-731` (`_parse_inline_style`)

`_parse_sheet` propagates `tokenizer_parse_errors` and `css_parse_errors` into the
stage counters; `_parse_inline_style` does neither, and its `CssParser("")` is
constructed on the empty string so its tokenizer counters are meaningless anyway.
Verified — identical malformed CSS:

```
as <style> body     -> tokenizer_parse_errors 1, css_parse_errors 1
as style= attribute -> tokenizer_parse_errors 0, css_parse_errors 0
```

wikipedia.html has 237 inline `style=` attributes; any malformed CSS in them reads as
zero. Declaration counts *are* recorded for inline, so this is bounded to the error
metrics. ~3 lines.

**4. The `!important` shorthand-reset axis is uncovered by the suite.**
`tests/cssparse/test_cascade.py` — 18 `important` mentions, none on a shorthand.

*This is deferred minor J and I am ruling it merge-blocking.* Not on principle: Important 1
above is a live bug sitting in `_parse_block`/`_parse_inline_style`, one line away from the
reset path, that no existing test could catch. The reset has tests for the cascade-respect
axis (`test_the_shorthand_reset_respects_the_cascade_rather_than_overwriting`) and the
inline axis (`test_a_partial_shorthand_in_a_style_attribute_resets_too`) but nothing
that pins rank propagation. Add the five orderings above; they pass today, so this is
cheap.

### Minor

**1. `values.py` is the only `cssparse` module that uses `str.lower()`.** Ten sites
(`values.py:379, 392, 443, 485, 513, 514, 522, 523, 601, 689`). `tokenizer.py:121`,
`parser.py:202`, `selectors.py:229` and `matching.py:197` each define `_ascii_lower`
with a docstring stating precisely why `str.lower()` is wrong (U+212A KELVIN SIGN
folds to `k`, U+1E9E to `ß`). Reachable and confirmed: `display: bloc<U+212A>` is
accepted as `block`, `color: pin<U+212A>` as `pink`; a browser rejects both. No
author writes this — but it is a documented convention that one of seven modules
silently inverts, with no deviation recording the choice. Mechanical fix.

**2. `matching.py:83-84` states a tokenization fact that is wrong.** *Deferred minor H —
merge-blocking.* Confirmed against our own tokenizer: `2n+1` → `Dimension, Number`
(no `Whitespace`); only `2n +1` and `2n 1` produce the three-token run the paragraph
claims for all three. Behaviour is unaffected. Fix: say "`2n +1` and `2n 1` reach us
as … ; `2n+1` reaches us as `Dimension(2,'n'), Number(1)` — in every case the sign's
presence is not recorded, so we accept all three." See the process note below.

**3. `matching.py` deviations are numbered 12, 14, 13.** Deviation 14 (`_an_b_memo`) is
inserted at line 130, before deviation 13 (`candidates()` ordering) at line 151. Both
cross-references (`matching.py:519`, `:748`) point correctly; only the reading order is
wrong. Symptom of the same edit that introduced Minor 2.

**4. `selectors.py`'s deviation 10 was never amended for `matching.py`'s sanctioned
exception.** `selectors.py:152-154` says a selector "must not be mutated afterwards …
The parser builds each one once and never touches it again, and nothing else should
start." `matching.py:130-150` then writes `_an_b_memo` onto `PseudoClassSelector` and
says "which is why it is written down here" — but *here* is the other module. A reader
of `selectors.py` alone would file the memo as a bug. This is the cross-task obligation
that fell through this time: not a missing implementation, a one-directional contract
amendment. One sentence in `selectors.py`.

**5. `tokenizer.py:56` contradicts `tokenizer.py:469` in the same file.** *Deferred
minor E.* Line 56: "`tokenize()` is a generator". Line 469: "Not a generator itself,
deliberately". Stale after the `tokenize()`/`_tokenize()` split. One line.

**6. `tokenizer.py:49` hands `is_integer` to the wrong task.** "…which is what
`<integer>` value parsing will need in task I." Task I (`values.py`) never reads
`is_integer`; Task H (`matching.py:591, 597, 625, 651`) does, for `An+B`. Harmless —
none of the nine properties has an `<integer>` grammar — but it is a stale forward
reference of the same family as Task I's deviation 7.

**7. `ua.py`'s omission list contradicts the sheet.** `ua.py:37` says "**No `display`
for the replaced/embedded elements** (`img`, `input`, …)"; `ua.py:119` gives `img`
(and `area`, `map`, `picture`) `display: inline`. Behaviourally identical to the
initial value, so nothing is wrong — the bullet is.

**8. The nine-property boundary excludes the longhands of its own shorthands, and this
is neither documented nor tested.** `margin-top`, `padding-right`, `border-top-width`,
`border-width`, `border-color`, `border-style`, `border-top` and `background` all return
`None`. On wikipedia that is 14 `margin-top`, 15 `padding-right`, 8 `margin-bottom`,
7 `border-left` — the largest *undocumented* slice of the 313 drops. `values.py`'s
deviation list has eleven entries and none says "the shorthands are supported, their
longhands are not"; the plan's Known Gaps list does not carry it either; no test pins it.
`ComputedStyle` has a `margin_top` field that only a shorthand can ever set. Not wrong,
but the scope is bounded by accident of the dispatch chain rather than by a stated
decision. Add a deviation and a `parse_declaration_value("margin-top", …) is None` test.
Similarly `_DISPLAY_KEYWORDS` is a closed allow-list (rejects `flow-root`, present in
the corpus) with no deviation naming it.

**9. `cssparse/__init__.py` re-exports three of six modules.** `matching`, `values` and
`cascade` are absent, so `style_document` — the stage's actual entry point — is not
reachable from the documented import surface the file's own docstring advertises.

**10. `_ascii_lower` now has six implementations** (`cssparse/tokenizer.py:121`,
`cssparse/parser.py:202`, `cssparse/selectors.py:229`, `cssparse/matching.py:197`,
`htmlparse/treebuilder.py:197` as a `str.maketrans` table, `htmlparse/tokenizer.py:64`
with a *different signature* — one char, not a string). Each duplication is individually
justified in a docstring, and the argument ("importing a leading-underscore name is the
worse coupling") is sound at N=2. At N=6, with two divergent shapes and a same-named
function that takes a different type, `mayshay/_text.py` — the precedent `metrics.py`
already sets for shared, non-stage code — is the smaller coupling. Phase 3.

**11. `read()`'s `run_id == "run_id"` heuristic.** *Deferred minor A.* `metrics.py:141`
would drop a legitimate row if a caller passed that literal string; `emit` does not
validate it. `read`'s docstring does now explain the discard (the ledger entry is
slightly stale on that), so the residual gap is one caveat on `emit`. Defer.

**12. `expand_shorthand("margin"|"padding", partial_dict)` raises a bare `KeyError`.**
*Deferred minor I.* `values.py:676`. Unreachable via `parse_declaration_value`, but the
function is in `__all__`, so a bare `KeyError` is a public-API rough edge. Defer.

**13. `annotate_positions` lacks the re-run-after-mutation note** that `class_list` has.
*Deferred minor D.* `dom/node.py:163`. The failure mode is a typed, tested `None` and
`matching._element_index0` falls back correctly (verified). Defer.

---

## Triage of the seven deferred minors

| # | Item | Verdict |
|---|---|---|
| A | `metrics.read()` `run_id == "run_id"` heuristic | **Phase 3.** Undocumented caveat on `emit`, not a defect. |
| D | `annotate_positions` docstring re-run note | **Phase 3.** Fallback verified; failure mode is typed `None`. |
| E | `tokenizer.py:56` "tokenize() is a generator" | **Fix before merge.** It is not stale, it is a self-contradiction inside one file — line 469 says the opposite. One line. |
| G | report's "fifteen token types" (should be 25) | **No action.** Gitignored report, not a repo artifact. |
| H | `matching.py:83-84` wrong tokenization fact | **Fix before merge.** See below. |
| I | `expand_shorthand` bare `KeyError` | **Phase 3.** Unreachable internally. |
| J | `!important` shorthand-reset uncovered | **Fix before merge.** See Important 4. |

**On H specifically.** The item is presented as harmless-to-behaviour, and it is. It is
still merge-blocking, for a reason that has nothing to do with `2n+1`. This is the third
documentation fix in this project to introduce a documentation error — after Task F's
renumbering breaking three cross-references and Task F's deviation list being wrong in
both directions. This review found four more of the same shape independently
(Minors 3, 4, 5, 7), two of them in edits from the same rounds. That is no longer a run
of coincidences; it is the review process's blind spot: prose changes are re-read for
whether they *sound* corrected, and not executed against the thing they describe. The
`2n+1` fix is one sentence. What has to go with it is the check: **when a deviation
states a fact about token streams, computed values or spec text, verify it by running
it, the same way a code change is verified.** I verified all four of the tokenization
claims in that paragraph in one command; the round that wrote it could have.

**On J specifically.** I confirmed the ledger's claim — all five orderings I executed are
correct, including two the earlier reviewer did not run (important-shorthand→normal-shorthand,
and `currentcolor` propagating through an important reset). Right-by-inspection would
normally justify deferral. It does not here: Important 1 is a real, silent, currently-
undetectable bug **in the same three lines** the deferred test would exercise. The suite
has no assertion anywhere that ties a shorthand reset to the rank of the declaration that
caused it, and that gap is what let the uppercase-name path ship. The tests pass today;
write them today.

## Another cross-task obligation that fell through?

**Yes — one, and it is not documentation.** Important 1 is the same failure mode as
Task I's deviation 7, one turn later: `values.py` lowercases the property name inside
`parse_declaration_value` and never says so at the boundary; `cascade.py` takes over the
shorthand-reset obligation and keys its table on the *un*-lowercased name. Both sides
are individually reasonable, both passed their scoped review, and the seam is silent.

Two further hand-offs are stale rather than broken: `selectors.py`'s deviation 10 was
never amended for the exception `matching.py` grants itself (Minor 4), and
`tokenizer.py`'s deviation 4 assigns `is_integer` to Task I, which never consumes it
(Minor 6). No other deviation in `cssparse` assigns work that nothing does — I traced
all of them (values 3/5/7/8, tokenizer 4/7, selectors 1/3, matching 5/9/14, cascade
1/2/3/5/9) and the rest land where they say they land.

## What the xfail ledger hides

Nothing that is a defect rather than deferred scope. All 72 xfails carry a category and
a named cause; the corpus ones are `strict=True`, so a fix cannot rot into a mute button.
One structural note, not a defect: `test_parse_errors.py` pins only `tests1.dat`'s curated
subset, while the 404/474 headline comes from `scripts/error_report.py` sweeping all 57
files with no assertion. The ~70 disagreements outside `tests1.dat` are measured but not
tracked — deliberate (Task K is a report, not a gate), and worth knowing before someone
reads 404/474 as regression-guarded.

## Assessment

**Ready to merge: with fixes.**

Four Important items (one silent correctness bug, two wrong-by-construction metrics, one
test gap), plus deferred minors E, H and J promoted. All six are small and mechanical;
the shorthand-reset fix is already verified green against a shadow copy. Nothing in the
architecture needs rework — the module boundaries, the two-`em`-paths design, the rule
index and the computed-vs-used discipline all hold up under execution, and the index's
superset contract survives 363,000 real element×rule pairs. The defects that remain are
all at seams between modules that were reviewed correctly one at a time, which is exactly
what this pass was for.
