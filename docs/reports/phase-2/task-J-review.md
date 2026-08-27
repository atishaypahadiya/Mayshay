# Task J review — cascade, inheritance, computed values

**Diff:** `39ba6ae..d8ed477` (4 new files, 2073 insertions)
**Reviewer method:** full diff read in three passes; then targeted probes against the
installed tree (read-only) and 7 independent bug injections through a `/tmp/jrev/shadow`
`PYTHONPATH` shadow with a `__file__`-startswith guard. Shadow deleted; `git status`
clean; `.pth` md5 `3717d729cbbfc50ae0f221f1d9b09cdd` unchanged; `.venv` untouched.
Suite not re-run (implementer's evidence accepted per template).

---

## Spec Compliance

**❌ Issues found** — one genuine cascade defect (shorthand reset, explicitly delegated
to this task by Task I and neither implemented nor documented), plus one incorrect
deviation rationale. Everything else the brief asked for is present and correct.

Brief checklist, file by file:

| Brief item | Status |
|---|---|
| `src/mayshay/cssparse/cascade.py` | ✅ present, 878 lines |
| `src/mayshay/cssparse/ua.py` | ✅ present, 121 lines |
| `tests/cssparse/test_cascade.py` | ✅ present, brief's 15 verbatim + 56 added |
| `scripts/style_report.py` | ✅ present, 156 lines |
| `ComputedStyle` one field per longhand | ✅ cascade.py:26 fields + module-level `assert` cross-check |
| `INHERITED: frozenset[str]` = color, font-size | ✅ |
| `style_document(document, author_css) -> Counter[str]` | ✅ returns `Counter`, writes nothing |
| `nodes_styled`, `link_stylesheets_skipped`, `cascade_time_ms` | ✅ all three present; `link_stylesheets_skipped` seeded to 0 |
| `ua.UA_CSS: str` | ✅ a CSS string, run through the real parser stack |
| UA: `display:none` for head/style/script/link/title/meta | ✅ exactly the six named |
| UA: block set, inline set, margins for body/p/h1–h6 | ✅ (+ h1–h6 font-sizes, justified) |
| Origin order UA → author `<style>` → `style=` | ✅ with `author_css` placed ahead of `<style>` (deviation 10) |
| `(important, specificity, source_order)` sort | ✅ generalised to a 6-level rank; correct per CSS Cascade 4 |
| `link_stylesheets_skipped += 1`, not fetched | ✅ cascade.py `_count_link_stylesheets` |
| Percent / `auto` survive symbolically | ✅ verified on 5 properties |
| Driver calls `metrics.emit`, library does not | ✅ verified below |

### ⚠️ Cannot verify from diff
- `metrics.emit`'s row-count return and CSV schema are Task A code; I confirmed the
  signature matches `style_report.py`'s call (`stage, counters, *, source, run_id, path`)
  at `src/mayshay/metrics.py:55`, but not the 84-row claim (controller states it is verified).
- `RuleIndex(..., selector_of=)` is Task H code; confirmed the kwarg exists at
  `src/mayshay/cssparse/matching.py:718`.
- The `author_css`-before-`<style>` ordering (deviation 10) is untestable today by
  construction; it becomes load-bearing when Phase 5's `net/` supplies real sheets.

---

## Strengths

1. **The `em` separation is a genuine structural guarantee, not a comment.**
   `_compute_font_size(declared, *, parent_font_px, root_font_px)` (cascade.py, "The two em
   paths" section) has no own-font-size parameter; `_compute_rest(style, declared, *,
   own_font_px, root_font_px, own_color)` has no `parent_font_px`. `_compute_style` binds
   `own_font_px = style.font_size_px` *after* step 1 and passes only that onward. The
   mistake is not reachable by editing one line inside either body.

2. **The UA sheet plants the task's own trap inside itself.** `h1 { font-size: 2em }` +
   `h1 { margin: 0.67em 0 }` means every page exercises both `em` bases on one element,
   and `test_ua_heading_margins_use_the_headings_own_enlarged_font_size` pins 32px/21.44px
   (not the plausible-looking 10.72px). This is the best single design decision in the diff.

3. **Cascade rank table is correct CSS Cascade 4.** `0 UA-normal < 1 author-normal <
   2 inline-normal < 3 author-important < 4 inline-important < 5 UA-important`. The style
   attribute gets its own two levels rather than a forged `(1,0,0)` specificity — which
   would lose to `#a#b`, and must not. `test_important_inline_style_beats_important_author_rule`
   and `test_important_author_rule_beats_a_normal_inline_style` are a proper discriminating pair:
   a single-level `style=` implementation passes one and fails the other.

4. **Per-declaration source order**, threaded across every sheet by a shared `_Counter`,
   so `p { color: red; color: blue }` and later-sheet-wins both work. Verified by injection.

5. **One `_StyleRule` per selector, sharing `_Declaration` objects.** Correct: only a
   selector's own specificity may be compared, and the shared declarations correctly carry
   one source position. `test_a_selector_list_gives_each_selector_its_own_specificity` pins it.

6. **Error recovery matches CSS Syntax 3 §5.4.1** — an unparseable prelude invalidates the
   whole rule including its block, without abandoning the rest of the sheet; an invalid
   declaration drops only itself. Both directions tested.

7. **`currentcolor` resolved at the earliest correct point**, with `color` computed in
   step 2 *between* font-size and everything else, so `background-color: currentcolor`
   names this element's own colour and `color: currentcolor` names the inherited one.
   I scanned all three corpus pages for `Keyword` leaks into any computed field: **0**.

8. **Metrics separation is real** (see §6 below), and the test that pins it monkeypatches
   `metrics.emit` and asserts zero calls rather than asserting on a file.

---

## 1. Is the `em` separation airtight?

**Yes — I could not find a path that resolves a length against the wrong base or twice.**
Beyond reading the signatures I ran 11 adversarial probes against the real tree
(`/tmp/jrev/probe.py`, `cascade.__file__` confirmed to be the repo copy):

| probe | expected | got |
|---|---|---|
| `div{font-size:10px} p{font-size:20px; border:2em solid}` → border-top-width | 40px (own) | **40px** |
| same, `padding: 1em 2em` (shorthand → 4 longhands) | 20/40px | **20/40px** |
| `div{font-size:40px} p{width:2em}` — font-size **inherited**, not declared | 80px | **80px** |
| `p{width:2em; font-size:20px}` — width written *before* font-size in the block | 40px | **40px** |
| `style="width:2em;font-size:20px"` — inline attribute, parent 10px | 40px | **40px** |
| `h1{font-size:100px}` author + UA `margin:.67em` — **cross-origin** | 67px | **67px** |
| `style_document` run twice on the same tree (double-resolution) | 20/60px both | **20/60px both** |
| `p{font-size:20px; width:2ex; height:2ch}` | 20/20px (own) | **20/20px** |
| `p{font-size:2ex}` under a 10px parent | 10px (parent) | **10px** |
| `Keyword`/non-px-Length leak scan over all 3 corpus pages | 0 | **0** |

Why it holds structurally, not just empirically:
- **Inherited values cannot be re-resolved.** `_inherit_from` copies only `color` and
  `font-size`, both of which are already absolute (`Color`, px `Length`). There is no
  inherited relative length anywhere in `LONGHANDS`.
- **Shorthands cannot escape.** `parse_declaration_value` expands `margin`/`padding`/`border`
  *before* the cascade, so every expanded longhand arrives in the same `declared` dict and
  goes through the single `_compute_rest` loop with `own_font_px`. There is no second
  computation site. Confirmed: `border: 2em solid` → 40px, `padding: 1em 2em` → 20/40px.
- **`_compute_rest` is the only writer of non-font-size, non-color properties**, and it is
  called exactly once, from exactly one place (`_compute_style` step 3).
- **Values are immutable and stored computed.** `Length`/`Percent`/`Color` are
  `@dataclass(frozen=True)`; `_computed_value` returns new objects; the shared
  `_Declaration.value` (reused across every element a rule matches) is never mutated.
  Hence idempotence across repeated `style_document` calls, which I verified.
- **`rem` is a third, separately threaded base**, correctly using the initial 16px while the
  root element itself computes (CSS Values 4) and the root's computed size thereafter.

**The one residual risk is the one the implementer names and it is real:** the guarantee is
enforced by *call-site arity*, not by a type. A future edit that hoists one property out of
`_compute_rest` to compute it "early" reintroduces the confusion for that property alone.
Recommendation (Minor): make `_compute_style`'s `parent` parameter go out of scope before
step 3 — e.g. bind `parent_font_px = parent.font_size_px` at the top and `del parent` — so
even a hoisted line has nothing to reach for.

---

## 2. The five unspecified decisions, judged against the spec

### 2a. `display`'s stored type — **the implementer is right; `str` is correct, and the "inconsistency" is a stage boundary, not a disagreement.**

CSS distinguishes the *specified* value from the *computed* value. `values.py` produces a
specified value and is right to wrap it: `Keyword("block")` is type-distinguishable from the
string `"block"` a colour parser or an identifier might also produce, and that typing is what
lets `values.py` reject `display: red`. But for `display` and `border-*-style` the **computed
value *is* the keyword** — there is no further resolution step for a `Keyword` wrapper to
carry information into. At that point the wrapper buys nothing and costs a live trap:
`Keyword("block") == "block"` is `False`, so every layout-side comparison in Phase 3 would
be a silent no-match. Unwrapping at computed-value time (`_computed_value` → `value.name`)
is the right place, and the dataclass declares `display: str` / `border_*_style: str`
honestly. **The brief's `== "block"` assertion is correct and should not change; `values.py`
returning `Keyword` is also correct and should not change.**

Verified by injection: reverting the unwrap (`display_stored_as_keyword_object`) fails
8+ tests including all three corpus parametrisations.

*Sub-finding (Minor, below):* `_computed_value` unwraps **every** non-`currentcolor`
`Keyword` to a bare `str` with no allow-list.

### 2b. `author_css` before in-document `<style>` — **defensible, correctly flagged, but the stated rationale is the weaker half.**

The rationale ("stands in for external sheets a `<link>` in `<head>` would have pulled in")
is a claim about where `<link>` usually sits, and it is usually true — but it is not what
CSS says. CSS Cascade 4 orders author-origin sheets by their **position in the document**;
an external sheet linked *after* a `<style>` block loses to it. The honest framing is:
`author_css` has no document position, so any placement is a convention, and "first" is the
convention that most often matches reality. That is what the docstring should say. The
decision is **acceptable for Phase 2** and correctly named as needing revisiting when
`net/` supplies real sheets with real positions. No change required now.

### 2c. `style=` combined with `!important` — **correct, and better than the spec-minimum.**

CSS Style Attributes §3 puts style-attribute declarations in the author origin with a
specificity higher than any selector; CSS Cascade 4's importance flip then places important
inline declarations above important author rules. Ranks 2 and 4 encode exactly that.
Critically, the implementation **avoids** the common forged-`(1,0,0)` shortcut, which is
observably wrong: `#a#b { color: red }` would beat a `style="color: blue"`. ✅ Spec-correct.

### 2d. Viewport units — **correct, and the right call.**

CSS Values 4 makes `vw`/`vh`/`vmin`/`vmax` relative to the initial containing block, which
does not exist until layout. Keeping them symbolic is the identical argument the brief makes
for `%` and `auto`, and the brief's own "computed ≠ used" framing extends to them without
strain. The **font-size special case is the subtle part and is handled correctly**: a
font-size *must* end as a px `Length` because every descendant resolves `em` against it, so
an unresolvable one is dropped (inherited value retained) and counted in
`font_size_unresolvable` rather than stored. Both directions are injection-tested
(made-up 1280px viewport → 2 failures; storing the vw length anyway → 1 failure).
`example.html`'s `margin: 15vh auto` / `width: 60vw` makes this non-hypothetical. ✅

### 2e. `border-*-width`'s initial value — **❌ the decision is defensible but its stated rationale is factually wrong, and it exposes a real defect (see Important #1).**

Spec: the initial value is `medium`, which every engine renders as 3px. Deviation 8 argues
zero is harmless because "a border whose style is the initial `none` has a used width of
zero regardless." **That premise fails the moment a style is declared without a width**,
which is ordinary CSS:

```
p { border: solid red }   -> border_top_width = Length(0, 'px'), style = 'solid'
```
verified against the real tree. A browser paints a 3px red border here; mayshay will paint
nothing in Phase 3, and no test catches it. The zero default is *survivable* as a Phase 2
placeholder, but the docstring must stop claiming it is equivalent.

---

## 3. Under-asserting tests

### The two the implementer disclosed — the stronger siblings genuinely discriminate. Verified.

- `test_em_compounds_down_a_chain_of_ancestors` (32/64/128 over three nested `2em` divs) and
  `test_em_on_another_property_uses_this_elements_font_size_not_the_parents` (parent 10px,
  own 20px, `width: 2em` → 40px). I injected the defining error — `_compute_rest` handed
  `parent.font_size_px` — and got **3 failures**, one of which is the new sibling and one of
  which is the UA-heading test. The brief's own weak version alone would still have caught
  this particular bug, but *not* a non-compounding implementation; the chain test closes that.
- `test_source_order_breaks_ties_within_one_declaration_block` (`p { color: red; color: green }`).
  I injected a per-**rule** source counter and got **3 failures**, including this test and
  `test_later_stylesheet_beats_an_earlier_one_at_equal_specificity`. The brief's two-rule
  version passes under that injection. Confirmed genuinely stronger.

### The third — **found: `test_author_rule_beats_ua` (brief line 60-63 / test_cascade.py).**

```python
def test_author_rule_beats_ua():
    doc = styled("<!DOCTYPE html><body><div></div></body>", "div { display: inline }")
    assert find(doc, "div").computed_style.display == "inline"
```

`inline` is `display`'s **initial value**. The test therefore asserts "this div is not block",
not "the author rule beat the UA rule".

**Empirically demonstrated:** I injected a total no-op cascade (`_winning_declarations`
returns `{}` — *no declaration from any origin is ever applied*) into the shadow. Of the
brief's fifteen tests, `test_author_rule_beats_ua` is the **only** substantive one that still
passes. Every other value-asserting brief test fails, as does every corpus parametrisation.
A test whose name is "author rule beats UA" passing an implementation with no cascade at all
is the same defect class as the brief's own `test_link_stylesheets_are_counted_not_fetched`
warning.

It happens to be covered in practice by the added
`test_an_author_rule_overrides_the_ua_sheet_for_every_ua_property` (which also asserts
`margin: 3px` over the UA's `1em`, and `font-size: 9px`) — so this is a **Minor** finding,
not a coverage hole. But the brief's version should be strengthened to assert a value that is
not the initial value, e.g. `div { display: none }` or `p { display: inline }`.

**A fourth, among the *added* tests (Minor):** `test_author_normal_beats_ua_important_is_false`
asserts only on the private rank constants (`_RANK_UA_IMPORTANT > _RANK_INLINE_IMPORTANT`,
etc.). It is a restatement of five module constants — a change-detector that can never fail
for a behavioural reason. Its docstring is honest about why (no `!important` in `ua.py` to
drive it), which is fair, but the name promises a cascade outcome it never observes. It did
fire on my `inline_style_beats_everything` injection, so it is not worthless — just
mis-named. Consider `test_the_cascade_rank_table_is_ordered_as_css_cascade_4_says`.

---

## 4. The 65 (actually 66) injections

**The count is real work, not variations on one bug.** I re-ran 7 of them independently
through my own shadow harness, chosen to span six different axes, and every one was caught
with a distinct failure signature:

| injection | claimed | I measured |
|---|---|---|
| `rest_uses_parent_font_size` (the defining error) | 3 | **3** ✅ |
| `source_order_numbered_per_rule` | 4 | **3** (my patch differs slightly) ✅ |
| `inline_style_beats_everything` *(over-correction)* | 1 | **2** ✅ |
| `background_color_added_to_the_inherited_set` *(over-correction)* | 1 | **1** ✅ |
| `viewport_units_get_a_made_up_viewport` *(over-correction)* | 2 | **2** ✅ |
| `display_stored_as_a_keyword_object` | 8 | **8+** (incl. all 3 corpus cases) ✅ |
| `ua_table_is_a_block` | 1 | **1** ✅ |

Three of my seven are over-corrections and all three were caught — the suite constrains the
implementation from both sides, which is the property that distinguishes a real injection set
from a padded one. The 66 named bugs touch cascade order, matching, indexing, inheritance,
`currentcolor`, unit resolution, stylesheet collection, error recovery, the UA sheet, metrics,
and two upstream regressions in `values.py` — no two are the same bug renamed, and
`uniq -d` over the names finds no duplicates.

**Minor bookkeeping finding:** the report says "65 bugs injected, 65 caught" but its own
tables contain **66** rows. The prose presumably excludes the re-run
`ua_stylesheet_empty_properly`. Fix the number.

---

## 5. UA stylesheet omissions

The docstring's omission list is unusually good — it distinguishes decisions from oversights.
But I checked it against what the corpus actually contains, and one omission is materially
wrong. I styled all three pages and counted elements whose computed `display` is `inline`
where a browser's UA sheet gives them something else:

```
example.html   (nothing)
hn.html        td x159   tr x98    input x1
wikipedia.html td x157   tr x120   th x85   tbody x24
               button x16   input x12   source x2   noscript x1   caption x1
```

**Table internals are the finding (Important #2).** `table { display: table }` is present but
`tr`/`td`/`th`/`tbody`/`thead`/`tfoot`/`caption`/`col`/`colgroup` are absent, so they all fall
to the initial `inline`. **Hacker News is a table-based layout** — 98 rows and 159 cells — so
in Phase 3 `hn.html` renders as one undifferentiated inline run inside a single `display: table`
box. That is exactly the "visible garbage rather than a test failure" the review brief warns about.

The stated justification does not survive contact with the corpus: *"the tree builder's table
insertion modes are a Phase 1 carried gap, so styling a structure the parser does not reliably
build would be untestable."* The parser **did** build 98 `<tr>` and 159 `<td>` elements for
hn.html and 120/157/85 for wikipedia. The structure exists; it is simply unstyled. Even if
`display: table-row`/`table-cell` are not honoured by Phase 3's layout, `tr { display: block }`
and `td { display: inline-block }` would produce something legible instead of a wall of text.

Smaller gaps, ranked by real-page impact:
- **`noscript`** (wikipedia x1): the docstring argues it is "genuinely *shown* when scripting is
  disabled." That is right in principle, but this engine does not run scripts *and* the corpus
  pages were saved from scripting-enabled browsers, so the `<noscript>` content is a
  "please enable JavaScript" banner that will paint at the top of the article. Consider
  `display: none` with a comment, or leave it — it is one element and defensible either way.
- **`template`, `datalist`** — absent from all three corpus pages, so no impact today, but
  `<template>` in `<body>` will paint its entire contents whenever one appears. One-line fix.
- **`button`, `input`, `select`, `textarea`** (wikipedia x28) — `inline` is defensible per the
  docstring's replaced-elements argument.
- **`base`, `source`, `param`, `track`, `col`** — empty elements, genuinely nothing to paint. ✅
- **`li` as `block` rather than `list-item`** — correct choice with no marker rendering. ✅
- The six `display: none` elements the brief names are all present and tested. ✅
- `test_the_ua_stylesheet_parses_without_dropping_any_declaration` (asserting
  `declarations_dropped == 0` on an empty document) is a genuinely clever guard: it makes it
  impossible to add a UA rule outside the nine properties without a red test. ✅

---

## 6. Metrics separation

**Confirmed correct.**

- `grep -rn "metrics.emit\|import metrics" src/mayshay/` returns **only two docstring
  mentions** in `cascade.py` (lines 13 and 790) and **zero call sites** anywhere in `src/`.
  `style_document` builds a `Counter` and returns it; `cascade.py` does not import
  `mayshay.metrics` at all.
- `scripts/style_report.py` is the writer: `metrics_module.emit(stage, counters,
  source=..., run_id=..., path=args.out)`, once per stage per document, under a single
  `metrics_module.new_run_id()` for the sweep. Three stages × three pages.
- `--out` is passed **explicitly** rather than relying on `METRICS_DIR`'s `__file__`
  derivation — which is the correction the plan's Self-Review specifically recorded so it
  would not be re-introduced. ✅
- The signature matches Task A's (`src/mayshay/metrics.py:55`).
- `test_style_document_does_not_write_metrics_itself` monkeypatches `metrics_module.emit`
  and asserts zero calls, restoring in a `finally`. This is the right shape — it pins the
  *rule*, not a file's absence.
- `metrics["elements"] = annotate_positions(document)` uses assignment rather than `+=`,
  and `link_stylesheets_skipped` is seeded to 0 before counting so the key is present-at-zero
  rather than absent — both correct for a per-key CSV writer, and `test_restyling_a_document_is_idempotent`
  pins the no-accumulation property.

---

## Issues

### Critical (Must Fix)

*None.*

### Important (Should Fix)

**I1. Shorthand reset is not implemented, and `values.py` explicitly delegated it to this task.**
`src/mayshay/cssparse/values.py:88-97` (deviation 7) states: *"Missing components are simply
absent from the result; `border: solid` produces only the `border-*-style` keys… Manufacturing
those initial values here would bake a cascade-independent guess into a value that **Task J's
cascade is the one place with enough information** to fill in correctly."* Task J does not fill
it in, and does not list it as a gap. Two consequences, both verified against the real tree:

```
p { border: 5px solid red } p { border: solid blue }
  -> border_top_width = Length(5.0, 'px')      browser: medium (3px)
p { border: solid red }
  -> border_top_width = Length(0, 'px')        browser: 3px
```

CSS Cascade 4 §3: a shorthand sets **every** longhand it controls, including omitted ones,
to their initial values. Because `border`'s expansion emits only the keys that were written,
an earlier `border-width` **leaks through** a later `border` declaration that should have reset
it. `margin`/`padding` are unaffected (the one-to-four-value rule always yields all four sides);
`border` is the only affected shorthand today, but it is the one real stylesheets partially
specify most often.

*Fix:* in `_parse_block`/`_parse_inline_style`, when `parse_declaration_value` returns a
`border` expansion, emit `_Declaration`s for all twelve `border-*` longhands, filling omitted
components with the initial values (`medium`/`currentcolor`/`none`). That is the correct home
for it and is what values.py's deviation 7 asks for. If it is deferred instead, it must be
added to "Known Gaps Carried Into Phase 3" and values.py deviation 7 amended, because it
currently reads as *done by J*.

**I2. `tr`/`td`/`th`/`tbody`/`thead`/`tfoot`/`caption` have no UA `display`, so hn.html's
entire layout collapses to inline.** `src/mayshay/cssparse/ua.py` — see §5 for the corpus
counts (hn: 98 `tr` + 159 `td`; wikipedia: 120 + 157 + 85 `th` + 24 `tbody`). The docstring's
justification ("a structure the parser does not reliably build") is contradicted by the tree
builder having built exactly that structure on both pages. This will not fail a test; it will
produce a wall of text in Phase 3.
*Fix:* add `table-row`/`table-cell`/`table-row-group`/`table-caption` rules (values.py's
`_parse_display` accepts them — verified with `inline-block`), or, if Phase 3's layout will not
honour those, add `tr { display: block }` / `td, th { display: inline-block }` with a comment
saying it is an approximation. Either beats silence.

**I3. Deviation 8's rationale for `border-*-width: 0` is factually wrong.**
`src/mayshay/cssparse/cascade.py` module docstring, deviation 8: *"a border whose style is the
initial `none` has a used width of zero regardless, so zero is the honest default."* The premise
holds only when no style is declared. `p { border: solid red }` declares `border-style: solid`
and gets width 0 (verified). Whether or not I1 is fixed, this sentence must be corrected — a
wrong rationale in a docstring is worse than a flagged gap, because the next reader will trust it.

### Minor (Nice to Have)

**M1. `test_author_rule_beats_ua` asserts the initial value.** `tests/cssparse/test_cascade.py`
(brief line 60). Passes an implementation with **no cascade at all** — demonstrated by injection.
Covered in practice by `test_an_author_rule_overrides_the_ua_sheet_for_every_ua_property`.
Strengthen to a non-initial value (`div { display: none }`).

**M2. `test_author_normal_beats_ua_important_is_false` tests constants, not behaviour.**
Five asserts on private `_RANK_*` module constants — a restatement, not an observation. The
docstring explains why (no `!important` in `ua.py`), which is fair; the name is the problem.
Rename, or drive it by passing an `!important` UA sheet through a temporarily-patched `UA_CSS`.

**M3. `_computed_value` unwraps every non-`currentcolor` `Keyword` to a bare `str`, with no
allow-list.** `src/mayshay/cssparse/cascade.py`, `_computed_value`. Today only `display` and
`border-*-style` reach it as keywords, so the behaviour is right — but the *rule* is
"any keyword becomes a string", not "these two properties' keywords become strings". When the
property set grows (`font-weight: bold`? `overflow: hidden`? a future `<length>` keyword like
`thin`), a value that should have been resolved will silently become a string instead. Guard it
with a `_KEYWORD_VALUED` frozenset of property names, or pass the property name in.

**M4. The report says 65 injections; its tables list 66 rows.** Bookkeeping only.

**M5. `ComputedStyle.font_size_px`'s `assert` disappears under `python -O`.** The implementer
flags this themselves. It is the invariant the whole module rests on; a `raise TypeError` (or
letting the arithmetic fail loudly) would survive optimisation. Minor because nothing runs
optimised today.

**M6. `root_font_px` is updated by *any* element whose parent is not an `Element`.**
`style_document`'s walk. In a parsed document there is exactly one such element (`<html>`), so
this is correct today, but the code reads as "the root" while the condition is "any orphan
element". A comment or an explicit "first element only" guard would make the intent match the test.

**M7. Harden the `em` guarantee against future edits.** Bind `parent_font_px` at the top of
`_compute_style` and `del parent` before step 3, so that even a property hoisted out of
`_compute_rest` has no parent style in scope. Cheap, and it converts a convention into a
NameError. (See §1.)

**M8. Deviation 10's rationale overstates the case.** `author_css`-before-`<style>` is a
convention forced by the argument having no document position, not a consequence of where
`<link>` usually sits. Reword; the decision itself is fine.

**M9. `declarations_dropped` is not an error rate** — 43% on wikipedia is almost entirely
properties outside the nine. The implementer flags this and proposes splitting it into
`declarations_unsupported_property` / `declarations_invalid_value`. Agreed, and it matters for
the analysis half of the project, where this number would otherwise say something false about
the web. Worth doing in Phase 3.

---

## Assessment

**Spec compliance:** ❌ Issues found — I1 (shorthand reset delegated by Task I and not
implemented, causing an earlier `border-width` to leak through a later `border` declaration),
I3 (incorrect deviation rationale). Everything else in the brief is present and correct.

**Task quality:** **Needs fixes** — I1 and I3 are small, localised, and must be fixed or
explicitly re-scoped as documented gaps; I2 is a one-block addition to `ua.py`. None of them
touch the module's core, which is excellent.

**Reasoning:** The thing this task existed to get right — the `em` asymmetry — is right, and
right by construction rather than by care: two functions with disjoint parameter lists, a
fixed three-step order, and a UA sheet that plants the trap on every real page. I probed it
eleven ways including inherited font-sizes, shorthand-expanded longhands, cross-origin
declarations, `ex`/`ch`, and repeated styling, and found no path to the wrong base or to
double resolution. The 66-injection set is genuine and constrains the implementation from
both sides — 3 of the 7 I re-ran independently were over-corrections and all were caught.
The defects are at the edges: a shorthand-reset responsibility handed over by Task I and
dropped in the handoff, a UA sheet that leaves the corpus's most table-heavy page unstyled,
and one docstring rationale that is simply not true.
