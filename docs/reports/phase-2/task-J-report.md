# Task J report — cascade, inheritance and computed values

## Status

Done. Suite **6468 passed, 72 xfailed, 0 failed** (baseline 6395/72; +73 new).
Conformance unmoved at `780/1592` and `64/112`. `git status` clean apart from
the four new files. The venv editable pointer is byte-for-byte unchanged
(`.venv/lib/python3.13/site-packages/__editable__.mayshay-0.1.0.pth` →
`/Users/atishaypahadiya/projects/mayshay/src`, md5 `3717d729cbbfc50ae0f221f1d9b09cdd`).

## Changes per step

### Step 1–2: the failing tests

`tests/cssparse/test_cascade.py` was seeded with the brief's fifteen tests
*verbatim* (extracted from the brief's own fenced block, so no transcription
drift), and run to confirm the expected
`ModuleNotFoundError: No module named 'mayshay.cssparse.cascade'`.

### Step 3: `src/mayshay/cssparse/ua.py` (121 lines)

`UA_CSS` as a CSS **string**, not a table of defaults, so it goes through the
same tokenizer / parser / selector parser / value parser as author CSS and is
a standing end-to-end exercise of the whole `cssparse` stack on every
document. Contents:

- `display: none` — `head`, `style`, `script`, `link`, `title`, `meta`.
- `display: block` — `html`, `body`, `div`, `p`, `hr`, `pre`, `address`,
  `blockquote`, `h1`–`h6`, `hgroup`, `ul`, `ol`, `dl`, `dt`, `dd`, `li`,
  `menu`, `dir`, `article`, `aside`, `footer`, `header`, `main`, `nav`,
  `section`, `search`, `figure`, `figcaption`, `details`, `summary`,
  `dialog`, `fieldset`, `legend`, `form`, `center`, `optgroup`, `option`.
- `display: table` — `table`.
- `display: inline` — the 40-odd phrasing elements (`span`, `a`, `em`,
  `strong`, `code`, `img`, `br`, `label`, …). Redundant against the initial
  value, and included on purpose so the UA origin *states* the intent.
- Default margins — `body { margin: 8px }`, `p { margin: 1em 0 }`, and
  `h1`–`h6` at `0.67/0.83/1/1.33/1.67/2.33em 0`.
- **`h1`–`h6` font sizes** (`2em`, `1.5em`, `1.17em`, `1em`, `0.83em`,
  `0.67em`). Beyond what the brief asks for, and deliberate: those headings'
  margins are in `em`, and `em` on a non-`font-size` property resolves
  against the element's **own** font-size. Without the font sizes every
  heading margin would silently be `1em` of the inherited 16px — a
  plausible-looking wrong number of exactly the kind this task exists to
  prevent. It also plants the task's own trap inside the UA sheet, where
  `test_ua_heading_margins_use_the_headings_own_enlarged_font_size` pins
  `h1` at font-size 32px and margin-top 21.44px (not 10.72px).

Deliberately omitted, and documented in the module docstring as decisions
rather than gaps:

- **Every property outside `values.py`'s nine** — `font-weight: bold` on
  headings/`b`/`strong`, `font-style: italic` on `em`/`i`,
  `text-decoration: underline` on `a`, `list-style-type`, `white-space: pre`,
  `font-family: monospace`. `parse_declaration_value` returns `None` for all
  of them, so writing them here would produce silently dropped declarations
  and an inflated `declarations_dropped` that said nothing about the document
  being styled. `test_the_ua_stylesheet_parses_without_dropping_any_declaration`
  asserts `declarations_dropped == 0` on an empty document to keep this true.
- `display` for the replaced/embedded elements (`img`, `input`, `button`,
  `select`, `iframe`, `video`) — `inline` by initial value is right, and
  their real behaviour is `inline-block`-ish sizing only layout can express.
- `display: none` for `base`, `param`, `source`, `track`, `datalist`,
  `template`, `noscript` — empty elements with nothing to paint, plus
  `noscript`, which is genuinely *shown* when scripting is disabled, i.e.
  always, here.
- `padding-left` on `ul`/`ol`; margins on `blockquote`, `figure`, `dl`, `dd`,
  `ol`, `ul`, `pre`, `hr`. The brief scopes default margins to `body`, `p`,
  `h1`–`h6`; a partial list of the rest is a worse lie than none.
- `table-row` / `table-cell`. Parseable, but the tree builder's table
  insertion modes are a Phase 1 carried gap, so styling a structure the
  parser does not reliably build would be untestable.
- Quirks-mode UA rules entirely. `Document.mode` is classified, not acted on.

### Step 4: `src/mayshay/cssparse/cascade.py` (878 lines)

Public surface: `ComputedStyle`, `INHERITED`, `LONGHANDS`,
`INITIAL_FONT_SIZE_PX`, `style_document`.

- **`ComputedStyle`** — a mutable dataclass with 26 fields, one per longhand
  after shorthand expansion (`display`, `width`, `height`, 4 × margin,
  4 × padding, 4 × border-width, 4 × border-style, 4 × border-color, `color`,
  `background-color`, `font-size`), defaults set to the CSS initial values.
  A module-level `assert` cross-checks the dataclass's field set against
  `LONGHANDS`, so a longhand added to one and forgotten in the other is an
  import-time error rather than a property that silently never cascades.
- **`INHERITED = frozenset({"color", "font-size"})`** — the two of the nine
  that inherit.
- **Cascade order** — `(rank, specificity, source_order)`, highest wins, with
  rank `0 UA-normal < 1 author-normal < 2 inline-normal < 3 author-important
  < 4 inline-important < 5 UA-important`. The style attribute gets its own
  two levels rather than a forged `(1, 0, 0)` specificity; the forgery is the
  common shortcut and it loses to an author rule with two id selectors, which
  it must not.
- **`source_order` is per *declaration*, not per rule**, so
  `p { color: red; color: blue }` resolves the way it reads, and the counter
  is threaded across every sheet in the document so a later sheet wins ties
  against an earlier one.
- **Winner selection** is a running max over `(rank, specificity, order)`
  rather than a full sort — same answer, one pass.
- **One `_StyleRule` per selector, not per rule.** `p, #x { … }` becomes two,
  because only a selector's own specificity may be compared; they share the
  same `_Declaration` objects (same source position, same order numbers),
  which is correct.
- **`RuleIndex` is constructed with an explicit `selector_of=` hook** rather
  than leaning on its default `.selector` sniffing — the index decides which
  rules a page ever considers, and that should not depend on an attribute
  name matching by luck.
- **`annotate_positions(document)` runs before any matching**, as Task D
  requires. Its return value becomes the `elements` metric.
- **Error recovery**: an unparseable prelude invalidates the whole rule,
  block included (CSS Syntax 3 §5.4.1) and increments `selectors_invalid`,
  without abandoning the rest of the sheet; an invalid *declaration* drops
  only itself and increments `declarations_dropped`; at-rules increment
  `at_rules_skipped` and their contents never reach the cascade.
- **`currentcolor` is resolved here** — the earliest point it can be. On
  `color` it means the inherited colour; on `background-color` and
  `border-*-color` it means this element's own computed `color`. Nothing
  downstream of the cascade ever sees a `values.Keyword`.
- **`display` and `border-*-style` are stored as plain `str`.** The brief's
  own `test_ua_stylesheet_makes_div_block` asserts `== "block"`, and
  `Keyword("block") == "block"` is False. Every other property keeps its
  typed value.
- **`style_document` returns a `Counter` and writes nothing.**

### Step 6: `scripts/style_report.py` (156 lines)

Parses each page in `data/corpus/` smallest-first, styles it, and calls
`metrics.emit` three times per document — `tokenize` (the HTML tokenizer's
counters plus `source_bytes`/`source_chars`), `treebuild` (the tree builder's
counters, parse errors included) and `cssparse` (`style_document`'s counter)
— all under one `run_id` for the sweep. `--out` is passed to `emit`
explicitly, never relying on `METRICS_DIR`'s `__file__` derivation.
`--dry-run` prints without writing; positional args override the corpus.

## Exact test command and output

```
$ .venv/bin/pytest
...
6468 passed, 72 xfailed in 4.82s

$ .venv/bin/pytest tests/cssparse/test_cascade.py
73 passed in 0.93s

$ .venv/bin/python scripts/conformance_report.py
all files: 780/1592
tests1.dat: 64/112
```

(73 test *cases* from 71 `def test_` functions — one is parametrised over the
three corpus pages.)

## How the two `em` resolution paths are kept distinct

Not by a flag, and not by a comment. By **two functions with different
parameter lists**:

```python
_compute_font_size(declared, *, parent_font_px, root_font_px) -> Length | None
_compute_rest(style, declared, *, own_font_px, root_font_px, own_color) -> int
```

`_compute_font_size` is never given the element's own font-size — it is
computing it, so there is nothing to be given. `_compute_rest` **has no
`parent_font_px` parameter at all**, so the parent's font-size is not in
scope inside it and the classic mistake cannot be made by editing one line in
the body; it would take changing the signature and every call site. A
reviewer can confirm the rule from the signatures without reading either body.

`_compute_style` runs the three steps in a fixed order — font-size (against
the parent), then `color` (because `currentcolor` on any other property names
it), then everything else (against the element's own font-size and colour) —
and the walk is pre-order/document order via an explicit stack so a parent's
style always exists before its children are computed.

`rem` is a third base, threaded separately: `root_font_px` starts at the
initial 16px, is used as-is while the root element itself is computed (CSS
Values 4: `rem` on the root refers to the property's *initial* value), and is
then replaced by the root element's computed font-size for every descendant.

Results the tests pin:

| case | CSS | result |
|---|---|---|
| `font-size: 1.5em` under `div { font-size: 20px }` | parent base | `Length(30, "px")` |
| `width: 2em` on `p { font-size: 20px }` | own base | `Length(40, "px")` |

Both brief tests pass. Two of the brief's own tests are weaker than their
names, and I added stronger versions rather than relying on them (see
"where the brief was underspecified").

## `style_report.py` over all three corpus pages

```
run_id 5f0fc578ad2e
example.html  (559 bytes)
    treebuild  elements                   12
    treebuild  parse_errors               0
    treebuild  parse_time_ms              0.253
    cssparse   nodes_styled               19
    cssparse   rules_total                113
    cssparse   declarations_kept          22
    cssparse   declarations_dropped       3
    cssparse   style_elements             1
    cssparse   inline_style_attributes    0
    cssparse   link_stylesheets_skipped   0
    cssparse   cascade_time_ms            1.748
hn.html  (34,537 bytes)
    treebuild  elements                   806
    treebuild  parse_errors               3
    treebuild  parse_time_ms              13.416
    cssparse   nodes_styled               1285
    cssparse   rules_total                109
    cssparse   declarations_kept          55
    cssparse   declarations_dropped       4
    cssparse   style_elements             0
    cssparse   inline_style_attributes    37
    cssparse   link_stylesheets_skipped   1
    cssparse   cascade_time_ms            5.057
wikipedia.html  (791,208 bytes)
    treebuild  elements                   7778
    treebuild  parse_errors               14
    treebuild  parse_time_ms              235.8
    cssparse   nodes_styled               15296
    cssparse   rules_total                233
    cssparse   declarations_kept          408
    cssparse   declarations_dropped       313
    cssparse   style_elements             18
    cssparse   inline_style_attributes    237
    cssparse   link_stylesheets_skipped   2
    cssparse   cascade_time_ms            141.684

84 rows -> data/metrics/stages.csv
```

**`link_stylesheets_skipped`: example 0, hn 1, wikipedia 2** — exactly the
shape the brief predicted. `data/metrics/stages.csv` now holds 84 rows across
`tokenize`, `treebuild` and `cssparse` sharing one `run_id` over three
sources (verified through `metrics.read()`). The file is covered by
`.gitignore`'s `data/metrics/*.csv`, same as `conformance.csv`, so it is not
committed.

The three findings worth carrying into the analysis half:

1. **hn.html has one external stylesheet and *zero* `<style>` elements.**
   Its entire visual design is in `news.css`, which this engine cannot fetch
   until Phase 5 — so today it renders as the UA sheet plus 37 inline `style=`
   attributes. That is the single clearest illustration of why the counter
   exists.
2. **wikipedia.html drops 313 of 721 declarations (43%)** — almost all of
   them properties outside our nine (`font-family`, `line-height`,
   `position`, `overflow`, …), not malformed values. `declarations_dropped`
   is currently a measure of *our* property coverage, not of the page's
   quality, and should be read that way until the property set grows.
3. **25 at-rules skipped on wikipedia** (`@media` overwhelmingly), so a
   quarter of its style rules are simply absent from the cascade.

## Where the brief was underspecified or wrong

Nothing in the brief was *wrong*. Five things were underspecified, decided
here and documented in the module docstring:

1. **`display`'s stored type.** The brief specifies `ComputedStyle` as "a
   dataclass with one field per longhand" and its test asserts
   `computed_style.display == "block"`, but `values.py` returns
   `Keyword("block")` and `Keyword("block") == "block"` is False. Resolved by
   unwrapping keyword-valued properties (`display`, `border-*-style`) to
   `str` at computed-value time. The brief does not say this anywhere; it is
   only discoverable by running its own test.
2. **Where `author_css` sits relative to in-document `<style>`.** The brief
   lists the origin order as "UA, then author `<style>` elements in document
   order, then the `style=` attribute" and never places the `author_css`
   argument in it. Decided: `author_css` before in-document `<style>`, on the
   grounds that the argument stands in for the external sheets a `<link>` in
   `<head>` would have pulled in, which precede in-document `<style>` on
   almost every real page.
3. **The `style=` attribute's cascade level.** The brief says only "then the
   `style=` attribute", which is silent on `!important`. Implemented as two
   dedicated levels either side of author rules rather than a forged
   specificity — see the docstring.
4. **`vw`/`vh`/`vmin`/`vmax`.** The brief's "computed ≠ used" rule names
   percentages and `auto`; viewport units are the same problem and are not
   mentioned. Kept symbolic on ordinary properties. On `font-size` they
   cannot be kept symbolic (every child resolves `em` against it), so an
   unresolvable font-size leaves the inherited value in place and increments
   `font_size_unresolvable`. `example.html`'s `margin: 15vh auto` and
   `width: 60vw` are real instances of this, so it is not hypothetical.
5. **`border-*-width`'s initial value.** The spec says `medium` (3px);
   `values.py` (its deviation 8) does not parse the `thin|medium|thick`
   trio. Set to `Length(0, "px")`, which is what the used value is anyway
   while `border-style` is the initial `none`.

**Two of the brief's own fifteen tests assert less than their names imply** —
the same defect the brief itself warns about, in the brief's own test list:

- `test_em_on_other_properties_resolves_against_the_element_itself` sets
  `p { font-size: 20px; width: 2em }` on a `<p>` whose parent `<body>` is at
  the inherited 16px… but reaches 40px only via the element's own 20px, so
  it *does* discriminate. Its weaker sibling is
  `test_em_font_size_resolves_against_the_parent`: `div { font-size: 20px }
  p { font-size: 1.5em }` — correct, but a single level, so an implementation
  that resolved font-size `em` against the *root* rather than the parent
  passes at 1.5 × 16 = 24 ≠ 30 (caught), while one that never *compounds*
  down a chain is not tested at all. Added
  `test_em_compounds_down_a_chain_of_ancestors` (three nested `2em` divs →
  32/64/128) and `test_em_on_another_property_uses_this_elements_font_size_not_the_parents`
  (parent 10px, own 20px, `width: 2em` → 40px, so exactly one of the two
  bases is right).
- `test_source_order_breaks_specificity_ties` uses two *separate rules*
  (`p { color: red } p { color: green }`), which a per-**rule** source
  counter passes. Added `test_source_order_breaks_ties_within_one_declaration_block`
  (`p { color: red; color: green }`), which only a per-declaration counter
  gets right, plus `test_later_stylesheet_beats_an_earlier_one_at_equal_specificity`.

The `green`/`lime` assertion is correct and was left alone; a
`css_green_is_lime` injection into `values.py` confirms three tests fail on it.

## Verification by injection

Method: `src/mayshay` copied to `/tmp/inject_j/shadow/mayshay`, one named bug
applied per run, `PYTHONPATH` shadowing, and a **guard step that asserts
`mayshay.cssparse.cascade.__file__` and `mayshay.cssparse.values.__file__`
both start with `/tmp/inject_j/shadow` before pytest is allowed to run** — a
mutation whose pattern did not apply, or whose shadow did not take, is
reported as SKIPPED/GUARD-FAILED, never as CAUGHT. Only
`tests/cssparse/test_cascade.py` is run under the shadow (running the whole
suite would trip `tests/test_environment.py`, correctly). Harness:
`/tmp/inject_j/harness.py`. The shadow tree was deleted afterwards.

**65 bugs injected, 65 caught.** (One first-pass mutation, `ua_stylesheet_empty`,
was itself malformed — a `/*` that the sheet's own `*/` closed early — and
survived; re-run correctly as `ua_stylesheet_empty_properly` it is caught by
9 tests. It is counted here as the malformed mutation it was, not as a test gap.)

### The `em` axis

| injected bug | caught by |
|---|---|
| `em_in_font_size_uses_root` — font-size `em` against the root | 2 |
| `rest_uses_parent_font_size` — **the task's defining error**: `_compute_rest` handed `parent.font_size_px` | 3 |
| `rest_recomputes_font_size_against_the_element_itself` (over-correction: drop `_compute_rest`'s `font-size` guard) | 8 |
| `walk_is_bottom_up` — children styled before parents | 10 |
| `rem_treated_as_em` | 1 |
| `root_font_size_never_updated` — `rem` always 16px | 1 |
| `percent_font_size_uses_initial` instead of the parent | 1 |
| `pt_is_one_px` | 1 |
| `viewport_units_get_a_made_up_viewport` (over-correction: resolve `vw` at an assumed 1280px) | 2 |
| `unresolvable_font_size_is_stored_anyway` (over-correction the other way) | 1 |

### Computed ≠ used

| injected bug | caught by |
|---|---|
| `auto_collapsed_to_zero` | 1 |
| `percent_resolved_against_font_size` | 2 |

### Cascade ordering

| injected bug | caught by |
|---|---|
| `source_order_numbered_per_rule_not_per_declaration` | 4 |
| `source_order_restarts_per_stylesheet` | 2 |
| `specificity_flattened_to_one_number` (`a*100+b*10+c`) | 1 |
| `important_ignored` | 2 |
| `inline_style_faked_as_an_id_specificity` | 1 |
| `inline_style_beats_everything` (over-correction) | 1 |
| `ua_origin_above_author` | 5 |
| `declaration_winner_uses_min_not_max` | 16 |

### Matching and indexing

| injected bug | caught by |
|---|---|
| `candidates_applied_without_matching` | 3 |
| `pseudo_elements_match_their_originating_element` (in `matching.py`) | 1 |
| `positions_not_annotated_before_matching` | 2 |
| `rule_index_catch_all_bucket_dropped` (in `matching.py`) | 1 |
| `selector_list_shares_its_maximum_specificity` | 1 |
| `only_the_first_selector_of_a_list_is_kept` | 6 |

### UA stylesheet

| injected bug | caught by |
|---|---|
| `ua_stylesheet_empty_properly` | 9 |
| `ua_display_none_rule_removed` | 1 |
| `ua_body_margin_zero` | 1 |
| `ua_heading_font_sizes_removed` | 2 |
| `ua_contains_a_property_values_cannot_parse` (`a { text-decoration: underline }`) | 1 |
| `ua_table_is_a_block` | 1 |
| `ua_inline_set_made_block` | 3 |

### Inheritance

| injected bug | caught by |
|---|---|
| `everything_inherits` (copy the parent style) | 3 |
| `nothing_inherits` | 7 |
| `background_color_added_to_the_inherited_set` (over-correction) | 1 |
| `one_shared_style_object_for_every_node` | 15 |
| `non_element_nodes_left_unstyled` | 6 |
| `inherit_from_the_root_element_instead_of_the_parent` | 10 |

### `currentcolor` and keyword handling

| injected bug | caught by |
|---|---|
| `currentcolor_resolved_against_the_parent` | 1 |
| `currentcolor_left_as_a_keyword` | 2 |
| `display_stored_as_a_keyword_object` | 8 |
| `every_value_stringified` (over-correction of deviation 6) | 28 |
| `color_computed_after_the_other_properties` | 28 |

### Stylesheet collection and `link_stylesheets_skipped`

| injected bug | caught by |
|---|---|
| `every_link_element_counted` (drops the `rel` test → 3 not 2) | 3 |
| `rel_matched_as_a_substring` (`stylesheetish` counts) | 1 |
| `rel_matched_as_an_exact_string` (`alternate stylesheet` lost) | 1 |
| `href_not_required` | 1 |
| `link_stylesheets_never_counted` | 4 |
| `style_elements_also_counted_as_skipped_stylesheets` (over-correction) | 1 |
| `style_elements_not_collected` | 4 |
| `style_elements_collected_in_reverse_order` | 1 |
| `style_type_attribute_ignored` | 1 |

### Error recovery

| injected bug | caught by |
|---|---|
| `at_rule_contents_hoisted_into_the_cascade` (`@media print` applied) | 1 |
| `at_rules_not_counted` | 1 |
| `invalid_selector_falls_back_to_universal` | 1 |
| `invalid_selector_abandons_the_rest_of_the_sheet` | 1 |
| `invalid_declaration_drops_the_whole_rule` | 1 |

### Upstream regressions this stage depends on

| injected bug | caught by |
|---|---|
| `css_green_is_lime` (`values.py`) — the named trap | 3 |
| `four_value_margin_uses_only_the_first` (`values.py`) | 1 |

### Metrics

| injected bug | caught by |
|---|---|
| `style_document_writes_the_metrics_itself` | 1 |
| `nodes_styled_counts_elements_only` | 3 |
| `cascade_time_not_reported` | 1 |
| `metrics_returns_a_plain_dict_missing_keys` | 69 |

## What a reviewer should scrutinise hardest

1. **`_compute_style`'s three-step order, and that nothing later re-enters
   step 1.** The whole correctness of the module is the claim that
   `own_font_px` is bound *after* font-size is computed and *before*
   everything else. It is the one thing no injected bug can protect against
   forever — a future edit that hoists a property out of `_compute_rest` and
   computes it "early" would reintroduce the parent/own confusion for that
   property alone, and only that property's own test would catch it.
2. **The `author_css`-before-`<style>` ordering decision** (deviation 10).
   It is a judgement call with no test that could distinguish it from the
   opposite choice on any real page, because nothing today passes both.
   The moment Phase 5's `net/` starts handing fetched sheets to
   `style_document`, this becomes load-bearing and should be revisited with
   the `<link>`'s actual document position in hand.
3. **`rel="alternate stylesheet"` counting as a stylesheet.** Real browsers
   treat alternates as not-applied-by-default. I count them, on the grounds
   that under-counting hides whole sheets while over-counting is a rounding
   error — but it *is* a deliberate over-count, and the corpus numbers above
   depend on it (it does not change any of the three: none of the three
   pages has an alternate stylesheet).
4. **`ex` and `ch` at 0.5em.** These are the spec's no-font-metrics
   fallbacks, not measurements. Any page that sizes something in `ch` will
   be visibly wrong in Phase 3, and there is no metric counting how often
   they appear. Worth adding one if the layout output looks off.
5. **`declarations_dropped` is not an error rate.** 43% on wikipedia is
   almost entirely properties outside our nine. If anyone builds an analysis
   on this number without that caveat it will say something false about the
   web rather than about our coverage. Consider splitting it into
   `declarations_unsupported_property` and `declarations_invalid_value` in
   Phase 3.
6. **`_winning_declarations` allocates two dicts and a closure per element**,
   and `_compute_rest` builds a filtered dict per element. wikipedia takes
   ~140ms to cascade 15,296 nodes, which is fine now; it is the first place
   to look if Phase 3 makes styling hot.
7. **The `assert` in `ComputedStyle.font_size_px`.** It is the invariant that
   font-size is always a resolvable px `Length`, and it disappears under
   `python -O`. If the engine is ever run optimised, an unresolvable
   font-size would silently produce a `TypeError` further away instead.

## Known gaps carried into Phase 3 (unchanged from the brief, confirmed)

`@media`/`@supports`/`@import` counted not evaluated; external stylesheets
counted not fetched; quirks mode classified not acted on; pseudo-elements
parsed not boxed; `inherit`/`initial`/`unset`/`revert` unsupported;
shorthands expanded never re-serialised. New from this task: viewport units
unresolved (`font_size_unresolvable` counts the font-size cases); `ex`/`ch`
approximated at 0.5em; `border-width`'s `thin|medium|thick` trio absent.

---

# Fix round 1 of 5

Six items from review. All six addressed; nothing deferred was touched.

## Important 1 — the shorthand reset (cross-task handoff)

`values.py`'s deviation 7 states that Task J fills in a shorthand's omitted
components; nothing did. Confirmed exactly as reported: `p{border:5px solid red}`
followed by `p{border:solid blue}` left `border_top_width` at `5px`.

Fixed with `_reset_omitted_longhands(name, longhands)`, called at **both**
declaration sources (`_parse_block` for stylesheets and `_parse_inline_style`
for `style=` attributes), driven by two new module-level tables:

- `_SHORTHAND_LONGHANDS` — every longhand each shorthand governs. `margin` and
  `padding` are in it even though the one-to-four-value rule means they can
  never leave a side unset, so a future shorthand cannot be added without a
  decision and the invariant is stated rather than assumed.
- `INITIAL_SPECIFIED` — the *specified* initial value of all 26 longhands.
  Deliberately **not** read off `ComputedStyle`'s field defaults, because two
  of them differ (see Important 3).

The reset values enter the cascade carrying the **same rank, specificity and
source order** as the shorthand that produced them, so
`#x { border: 5px solid red } p { border: solid blue }` still keeps `#x`'s 5px
— the reset is a cascade participant, not a post-cascade overwrite.

`border:5px solid red` then `border:solid blue` now gives
**`border-top-width: Length(3, "px")` (medium), `border-top-style: "solid"`,
`border-top-color: Color(0, 0, 255, 1.0)`** — matching a browser.

## Important 2 — table displays, and the false rationale

The UA sheet's Tables block is now complete, and its rationale corrected. The
old note claimed the tree builder does not reliably build tables; that was
false, and I have said so in the file rather than quietly deleting it —
Phase 1's carried gap is the table *insertion modes*' conformance behaviour on
malformed markup, which is a different thing from the elements not existing.

Required extending `values.py`'s `_DISPLAY_KEYWORDS` with the internal table
display types (`table-row-group`, `table-header-group`, `table-footer-group`,
`table-column`, `table-column-group`, `table-caption`, plus `inline-table` for
symmetry); `table-row`/`table-cell` were already there. No test pins that set's
size, so the addition is safe. Resulting displays:

| element | display | | element | display |
|---|---|---|---|---|
| `table` | `table` | | `tbody` | `table-row-group` |
| `caption` | `table-caption` | | `tfoot` | `table-footer-group` |
| `colgroup` | `table-column-group` | | `tr` | `table-row` |
| `col` | `table-column` | | `td`, `th` | `table-cell` |
| `thead` | `table-header-group` | | | |

I also recorded `li { display: block }` (rather than `list-item`) in the
omissions as a **genuine gap rather than a decision** — the keyword parses,
but nothing generates a marker box yet.

## Important 3 — deviation 8's false rationale

Confirmed: `p{border:solid red}` gave width `0px` where a browser paints 3px,
because the style *is* specified. The real rule is that `border-*-width` has
**two** initial values and both are needed:

- *specified* initial `medium` → `INITIAL_SPECIFIED` holds `Length(3, "px")`;
- *computed* value `0` whenever the matching `border-*-style` is `none` or
  `hidden` (CSS 2.1 §8.5.1) → new `_zero_widths_of_borderless_sides` step.

Collapsing them into one constant gets one case wrong whichever is chosen: a
single `0` makes `border: solid red` paint nothing; a single `3px` gives every
element on the page a three-pixel border. Deviation 8's text now says this.

Two adjacent corrections fell out of the same table and were taken:
`border-*-color`'s initial value is `currentcolor`, so the four border colours
are now seeded from the element's own computed `color` (step 2b, before
declarations apply) instead of defaulting to black.

## Minors

- **Keyword allow-list.** `_computed_value` now takes the property name and
  unwraps a `Keyword` to `str` only for `display` and `border-*-style`
  (`_KEYWORD_VALUED`). `currentcolor` is still resolved above the check; any
  other keyword raises `ValueError` naming the property. Nothing a stylesheet
  can contain reaches it — it can only fire on a code change, which is the
  point.
- **`test_author_normal_beats_ua_important_is_false`** replaced by
  `test_ua_important_outranks_every_author_declaration`, which monkeypatches
  `UA_CSS` to a sheet with an `!important` rule and beats a `#x#x !important`
  author rule *and* an `!important` inline style through observable colour.
  Every other rung of the ladder was already pinned observably; that was the
  only one that was not, and it no longer touches a private constant.
- **`root_font_px`** now follows the root element by identity (the first
  element in document order, computed once before the walk) rather than
  "my parent is not an Element", so a stray element hanging off the Document
  cannot redefine `rem` for everything after it.

## Verification

**20 further bugs injected, 19 caught**, same shadowed-`PYTHONPATH` harness
with the `__file__` guard. Two of the five first-pass survivors were **real
test gaps and are now closed**:

- `shorthand_reset_removed_for_inline_style` — no test drove a partial
  shorthand through a `style=` attribute, the half of the fix most likely to
  be forgotten since the two call sites are 40 lines apart. Added
  `test_a_partial_shorthand_in_a_style_attribute_resets_too`. Now caught.
- `border_colour_seeded_from_the_parent` / `border_colour_left_at_black` — an
  element that declares no border never goes through the reset, so the
  seeding step had no test at all. Added the colour assertions to
  `test_an_element_with_no_border_has_zero_width_borders`. Both now caught.

One survivor was a **malformed mutation** (`shorthand_reset_applied_outside_the_cascade`
was a no-op as written); replaced by `shorthand_reset_forced_to_a_high_rank`,
the realistic form of that bug ("make sure the reset takes" by giving it a
forged rank), which is caught.

One survivor is **semantically dead, not a test gap**:
`border_width_initial_collapsed_to_medium_everywhere` changes
`ComputedStyle`'s border-width field defaults, which are unobservable — the
only parsed source of a non-`none` border-style is the `border` shorthand,
which always resets the width alongside it, so the zeroing step overwrites
them on every element that could tell the difference. That reasoning is now a
comment on the fields themselves rather than a claim of coverage.

Caught, by axis: shorthand reset 4 (`shorthand_reset_removed`,
`..._for_inline_style`, `..._overwrites_declared_components`,
`..._forced_to_a_high_rank`); border widths 2
(`border_width_initial_collapsed_to_zero`, `border_width_zeroing_step_dropped`);
border colours 2; UA tables 4 (`tr`, `td, th`, `tbody`, `caption` rules each
removed in turn); keyword allow-list 1; root identity 1; UA-important rank 1.

## Results after the fix

```
$ .venv/bin/pytest
6483 passed, 72 xfailed in 5.26s          (was 6468; +15 new tests, 88 in test_cascade.py)

$ .venv/bin/python scripts/conformance_report.py
all files: 780/1592
tests1.dat: 64/112                        (unmoved)
```

### Does the table fix change anything visible in the metrics?

Yes, and exactly as much as it should — the UA sheet gained 8 declarations
across 9 rules (`td, th` is one declaration with two selectors):

| metric | example | hn | wikipedia |
|---|---|---|---|
| `rules_total` | 113 → **122** | 109 → **118** | 233 → **242** |
| `declarations_kept` | 22 → **30** | 55 → **63** | 408 → **416** |
| `declarations_dropped` | 3 → **3** | 4 → **4** | 313 → **313** |
| `link_stylesheets_skipped` | **0** | **1** | **2** |
| `cascade_time_ms` | 1.75 → 2.13 | 5.06 → 6.89 | 136.5 → 151.3 |

`declarations_dropped` is unchanged on all three, which is the check that the
new UA rules all parse. `link_stylesheets_skipped` is unchanged at 0/1/2.
`cascade_time_ms` is up ~10% from nine more rules to consider per element.

The elements themselves, styled from the real corpus:

- **hn.html** — 4 `table`, 98 `tr`, 159 `td`, all now `table`/`table-row`/
  `table-cell`. All 261 were `inline` before this fix; hn.html's entire layout
  is a table.
- **wikipedia.html** — 24 `table`, 120 `tr`, 157 `td`, 85 `th`, 24 `tbody`,
  1 `caption`, all carrying their table displays.

Two incidental findings worth recording, both of which are the cascade working
rather than failing: **2 of wikipedia's 24 tables compute to `display: block`**
and **2 of its `td`s to `display: none`**, because the page's own author CSS
overrides the UA sheet. That is the author-over-UA origin rule visible on a
real page for the first time, and it is a useful negative control — a UA sheet
that could not be overridden would show 24 and 0.

`git status` clean; venv `.pth` unchanged (md5 `3717d729cbbfc50ae0f221f1d9b09cdd`).
