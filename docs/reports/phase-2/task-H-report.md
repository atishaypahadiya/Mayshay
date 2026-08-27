# Task H report: selector matching and rule indexing

**Commit:** `a05a103` — *cssparse: right-to-left selector matching and rule indexing*
**Branch:** `phase-2-css-to-styled-tree`
**Files:** `src/mayshay/cssparse/matching.py` (new, 640 lines),
`tests/cssparse/test_matching.py` (new, 86 tests),
`tests/cssparse/test_matching_corpus.py` (new, 4 tests)

---

## 1. Changes per step

**Step 1 — read the contracts before writing anything.** The brief names two
interfaces and gives nine tests; it does not say how either works. The actual
requirements came from three places: Selectors 4 §4–§6, the numbered deviation
list at the top of `selectors.py` (which is that module's contract with this
one), and `dom/node.py`. Three things from those reading decided most of the
design:

- Deviation 2 of `selectors.py` ASCII-lowercases type and attribute *names* at
  parse time "so task H can compare with `==`", and leaves class/id/attribute
  *values* alone. That fixes the case-sensitivity asymmetry without a single
  fold in the hot loop.
- Deviation 10 makes every selector structure hashable with `pos` excluded
  from equality, including inside functional pseudo-class arguments. `RuleIndex`
  keys a dict on the rightmost compound, so that guarantee is load-bearing.
  **It holds.** I exercised it on the whole corpus indirectly (274 wikipedia
  selectors into one `RuleIndex`, no spurious bucket splits) and found no case
  where it fails.
- `Element.element_index` is `None` until `annotate_positions` runs, and the
  brief's own fixture calls it — which means a matcher that read it blindly
  would pass every brief test and silently treat every element as a first
  child anywhere else.

**Step 2 — the module.** `matching.py`, with a 13-entry deviation list in the
house style. Structure: tree navigation helpers, `matches` + the right-to-left
walk, attribute matching, pseudo-classes behind a dispatch table, the An+B
micro-grammar, then `RuleIndex`.

**Step 3 — the tests.** The brief's nine transcribed verbatim above a
`# -- additional discrimination tests --` marker, following the convention
`test_selectors.py` established, then 77 more.

**Step 4 — a corpus test.** `test_matching_corpus.py` runs every `<style>`
selector in `data/corpus/` against every element of the page that shipped it.
It reuses `_walk` and `_nested_preludes` from `test_selectors_corpus.py` (the
`@media` descent matters — a quarter of the corpus's rules live inside one).

**Step 5 — 25 fault injections** (§6), all against a `PYTHONPATH` shadow copy.

**Step 6 — commit,** after confirming the venv pointer and `git status`.

---

## 2. Test command and output

```
$ .venv/bin/pytest --color=no
...
6340 passed, 72 xfailed in 3.72s

$ .venv/bin/pytest tests/cssparse/test_matching.py tests/cssparse/test_matching_corpus.py --color=no
90 passed in 1.50s

$ .venv/bin/python scripts/conformance_report.py
all files: 780/1592
tests1.dat: 64/112
```

Baseline before this task was `6250 passed, 72 xfailed`; this adds 90 tests and
no failures. Conformance is unmoved in both numbers, as it must be — nothing
here touches HTML parsing.

Determinism check, because `candidates()` iterates a `frozenset` internally:

```
$ for s in 0 1 2 7 12345; do PYTHONHASHSEED=$s .venv/bin/pytest tests/cssparse/test_matching.py --color=no | tail -1; done
86 passed (x5)
```

Real-page measurement, from the corpus test's own numbers:

| page | elements | selectors | matches | candidate tests vs brute force |
|---|---|---|---|---|
| example.html | 12 | 5 | 4 | 8.33% |
| hn.html | 806 | 0 | — | — (links its CSS, inlines none) |
| wikipedia.html | 7778 | 274 | 2151 | **2.89%** (56 200 vs 1 820 052) |

---

## 3. How `RuleIndex` buckets rules

`__init__` derives each rule's `Complex`, takes its **rightmost** compound, and
files the rule under the first key it finds, in the order **id → class →
type**. Four buckets: `_by_id`, `_by_class`, `_by_tag`, `_catch_all`.

`candidates(element)` returns `_catch_all` + the element's id bucket + one
bucket per class in `class_list` + the tag bucket, sorted back into construction
order.

Three properties worth stating explicitly:

- **The rightmost compound is the one the element itself must match**, which is
  what makes the key sound. Keying on the leftmost compound (the plausible
  wrong version) silently loses every descendant rule — injected and caught.
- **A rule is filed under exactly one key**, so `candidates` never returns
  duplicates and no dedup pass is needed. id before class before type puts each
  rule in the most selective bucket available.
- **The contract is one-directional**: `candidates` must be a *superset* of the
  rules that match. It never runs the matcher.

### Selectors with no useful key

A rightmost compound naming no id, class or type — `*`, `[hidden]`, `:hover`,
`:is(.a, .b)`, `::before` on its own — goes to `_catch_all`, which is
**returned for every element**, unconditionally. It is seeded first in
`candidates` precisely so that removing it is a visible edit rather than an
omission.

`:is(.a, .b)` deserves a note: it is *in principle* indexable (a rule could be
filed under both `a` and `b`), and Blink does exactly that. Here it falls into
the catch-all, which is conservative-correct and costs one bucket entry. Worth
revisiting only if a corpus ever shows enough of them to matter; this one shows
none at all.

A rule whose selector cannot be found *at all* raises `TypeError` rather than
landing in the catch-all. Bucketing it as universal would be silently "correct"
— it would simply never match — which is the worst of both.

---

## 4. What is matched, and what deliberately is not

Matched: type, universal, class, id; attribute presence and all six operators
(`=`, `~=`, `|=`, `^=`, `$=`, `*=`) with the Level 4 `i`/`s` modifiers and
HTML's own case-insensitive-attribute list; all four combinators; the
tree-structural pseudo-classes (`:root`, `:empty`, `:first/last/only-child`,
`:first/last/only-of-type`, `:nth-child`, `:nth-last-child`, `:nth-of-type`,
`:nth-last-of-type`) with a full An+B parser; `:link`/`:any-link`; and
`:not()`/`:is()`/`:where()`/`:matches()` over the nested selector lists the
parser already built.

The 13 deviations are documented in full in the module docstring. The ones a
reviewer should know about:

1. **`matches()` rejects a `SelectorList` with `TypeError`** — the same call
   `specificity()` makes in its deviation 8. A boolean for a whole list does not
   say *which* selector matched, and the cascade needs that to get a
   specificity. `RuleIndex` rejects one for the same reason, with a message
   telling the caller to expand `p, .a { ... }` into one entry per selector.
   **This is a direct constraint on Task J** and the main reason to read this
   section.
2. **A non-`Element` node matches nothing**, rather than raising. Selectors
   select elements; a tree walk asking about every node is the normal caller.
3. **Type matching is a bare `==`, folding neither side** — taking the contract
   deviation 2 of `selectors.py` set up. Cost: a hand-built `Element("DIV")`
   won't match `div`. No code path in this engine produces one.
4. **Attribute values are case-sensitive except for HTML's ~46-attribute
   list** (`type`, `rel`, `lang`, `dir`, …), which is why `[type="TEXT"]`
   matches `<input type=text>` in every browser. `i`/`s` override in both
   directions. **Not in the brief**, and the brief's stated rule ("values are
   case-sensitive") is a simplification — see §5.
5. **An+B is parsed here, not in `selectors.py`**, since deviation 3 there keeps
   functional arguments as raw tokens. A malformed argument makes the
   pseudo-class *never match* rather than invalidating the rule; the spec drops
   the whole rule, so `p:nth-child(banana), a {}` keeps its `a` half here and
   would not in a browser. Fixing it properly means teaching the parser An+B.
6. **Two forms the spec rejects are accepted**, because our `<number-token>`
   carries no "sign character present" flag: `2n 1` and `2n + 1` reach us
   identically to `2n+1`. Leniency on input nobody writes; the fix belongs in
   the tokenizer.
7. **`:nth-child(… of S)` never matches.** Accepting `of` while ignoring the
   filter would match the wrong elements.
8. **`:has()` never matches** — its argument is unparsed raw tokens, per
   deviation 3 of `selectors.py`.
9. **A pseudo-element never matches an element.** `p::before` selects a box this
   engine does not generate; matching the `p` itself would apply the
   declarations to the wrong box.
10. **Dynamic and unknown pseudo-classes never match**, via a dispatch-table
    miss rather than an allow-list — `:hover`, `:focus`, `:target`, `:checked`,
    and `:visited`, which must never match on principle.
11. **`:empty` uses the Level 4 definition** (whitespace-only text is still
    empty). Every engine ships this.
12. **`:root` is "has no parent element"** rather than "is the document
    element", which differs only for detached subtrees.
13. **`candidates()` returns construction order.** Bucket order would leak into
    the cascade's tie-breaking, and `class_list` is a `frozenset`, so bucket
    order is not stable *between runs*. Task J must still sort by its own
    explicit source index; this only makes that sort's input deterministic.

**Right-to-left, as instructed, with no divergence.** `_match_from(element,
selector, index)` checks the compound at `index` against the element, then
follows the combinator to its left. Recursion depth is bounded by the *number
of compounds*, not tree depth: each call moves one compound left, and the
ancestor/sibling scans are loops at a fixed depth.

---

## 5. Where the brief was underspecified or wrong

The brief is ~100 lines and names two functions. Everything below was a
decision, not a transcription.

1. **What a "rule" is, is never defined.** The interface says
   `.candidates(element) -> list[Rule]`, but the brief's own test passes bare
   `Complex` objects, and no `Rule` type exists anywhere in the codebase.
   Resolved with a `selector_of` hook whose default accepts a bare `Complex` or
   anything carrying one on `.selector`, and raises otherwise. Task J can pass
   whatever shape it likes.
2. **`test_rule_index_narrows_candidates` does not discriminate**, exactly as
   warned. `len(candidates) < len(rules)` is satisfied by an index that returns
   nothing, drops the catch-all bucket, or keys on the leftmost compound. I
   verified this by injection: **all three bugs leave the brief's test green**
   (§6). It is the added tests that catch them.
3. **"`id` and `class` value matching is case-sensitive" is right; "attribute
   value matching is case-sensitive" is not.** The task framing extends the
   id/class rule to attribute values, and HTML does not: the HTML Standard's
   "Case-sensitivity of selectors" section makes ~46 attribute names compare
   ASCII case-insensitively. Implemented per spec, with `test_html_case_
   insensitive_attributes_ignore_value_case` pinning both directions, and both
   the over- and under-correction injected (§6).
4. **An+B is not mentioned at all**, yet `:nth-child(1)` is in the brief's test
   list and `selectors.py` deliberately does not parse it. The whole
   micro-grammar (`odd`, `even`, `2n+1`, `-n+3`, `n-3`, `-n-`, the
   `<n-dimension>`/`<ndashdigit-ident>` token forms) had to be written here.
5. **Pseudo-elements are not mentioned.** `p::before` parses fine and had to be
   given a matching answer; "never matches an element" is the only safe one
   until Phase 3 boxes them.
6. **`element_index` being `None` before `annotate_positions`** is called out in
   the task framing but not in the brief, whose fixture always annotates — so
   the brief's tests cannot catch a matcher that reads it blindly.
   `test_nth_child_works_without_annotate_positions` does, and the injection
   confirms it.
7. **Nothing says what happens for a `SelectorList`, a `Text` node, or an
   empty rule set.** All three now have tests and documented answers.

One brief test is subtly weaker than it looks and I kept it as written:
`test_adjacent_and_general_sibling` checks `p ~ span`, where the span's
*adjacent* sibling is also a `p` — so `~` implemented as `+` passes it.
`test_general_sibling_reaches_past_the_adjacent_one` closes that.

---

## 6. Discriminating power verified by injection

Method: `cp -R src/mayshay /tmp/mayshay_shadow/`, patch the shadow's
`matching.py`, run pytest with `PYTHONPATH=/tmp/mayshay_shadow`. Every run
first asserted `mayshay.cssparse.matching.__file__` resolved under
`/tmp/mayshay_shadow` before trusting the result. **No repo file and nothing
under `.venv/` was touched at any point**; the shadow was deleted afterwards.

25 injections, **all 25 caught**:

| # | injected bug | caught by |
|---|---|---|
| 1 | `matches()` always True | 57 tests |
| 2 | compound matches if **any** simple matches | 22 tests |
| 3 | `RuleIndex` keys on the **leftmost** compound | `…files_a_rule_under_its_rightmost_compound`, `…never_drops_a_rule_that_matches`, `…candidates_are_exactly_the_reachable_rules`, + corpus |
| 4 | `RuleIndex` **drops the catch-all bucket** | `…returns_the_catch_all_bucket_for_every_element` + 3 |
| 5 | `RuleIndex` ignores the class bucket | corpus superset test |
| 6 | `candidates()` in bucket order, unsorted | `…returns_rules_in_construction_order` + 2 |
| 7 | descendant commits to the first matching ancestor | `test_descendant_backtracks_past_the_first_matching_ancestor` |
| 8 | `>` accepts any ancestor | 3 tests incl. the brief's `test_descendant_and_child` |
| 9 | `+` behaves like `~` | `test_adjacent_combinator_is_not_general_sibling` |
| 10 | `~` looks at following siblings too | `…only_look_backwards`, `…reaches_past_the_adjacent_one` |
| 11 | sibling combinators search the whole document | 3 tests |
| 12 | `element_index` read blindly (`or 0`) | `test_nth_child_works_without_annotate_positions` |
| 13 | `:nth-child` counts nodes, not elements | 12 tests |
| 14 | An+B drops the `n >= 0` requirement | `test_nth_child_formulas[-n+2]`, `[n+2]` |
| 15 | **over-correction:** class matching folds case | `test_class_matching_is_case_sensitive` |
| 16 | **over-correction:** every attribute value compared case-insensitively | 4 tests |
| 17 | **under-correction:** no HTML case-insensitive attribute list | `test_html_case_insensitive_attributes_ignore_value_case` |
| 18 | `~=` implemented as a substring test | `test_attribute_operators[[class~="box  wide"]]` |
| 19 | empty attribute value matches everything | 3 parametrized cases |
| 20 | pseudo-elements match their element | `test_pseudo_elements_never_match_an_element` |
| 21 | `:not()` does not negate | 2 tests |
| 22 | `:empty` ignores element children | `test_empty_ignores_whitespace_but_not_elements` |
| 23 | `:empty` defeated by whitespace (Level 3) | same test, other direction |
| 24 | `:link` ignores `href` | `test_link_needs_an_href` |
| 25 | of-type pseudo-classes ignore the tag name | `test_of_type_pseudo_classes_count_only_the_same_tag` |

Rows 15–17 and 22–23 are **over-correction pairs**, copying Task G's approach:
each pins a rule in *both* directions, so a later "fix" that swings past the
target fails as loudly as one that never reaches it.

**Two results that are findings rather than confirmations:**

- **The brief's `test_rule_index_narrows_candidates` appears in none of the 25
  rows.** Injections 3, 4 and 5 all leave it green. It was the test the brief
  offered for the entire optimisation.
- **The corpus test cannot cover the catch-all bucket, and I checked rather
  than assumed.** Injection 4 leaves all four corpus tests green, because **not
  one of the corpus's 279 selectors lands in the catch-all bucket** — every
  rightmost compound names an id, class or type. That is a fact about
  2000s-era inline stylesheets, not a gap in the sweep, and it is exactly why
  dropping that bucket is a quiet bug: invisible on real pages until someone
  writes `* { box-sizing: border-box }`. It is recorded in the corpus test's
  docstring so nobody later assumes the corpus guards it.

---

## 7. What a reviewer should scrutinise hardest

1. **The HTML case-insensitive attribute list** (`_HTML_CASE_INSENSITIVE_ATTRS`,
   46 entries). It was transcribed from the HTML Standard's "Case-sensitivity of
   selectors" section and may contain errors — the same rough edge Task C's
   quirks table has. A wrong entry is a silent mismatch on one attribute, and
   only `type` is currently pinned by a test. Worth diffing against the spec.
2. **The An+B parser.** It is the most intricate code here and it reconstructs a
   grammar from tokens that have already lost information (deviation 6). The
   token forms are genuinely surprising — `2n-1` arrives as a *single*
   `Dimension(2, 'n-1')`, `-n+3` as `Ident('-n')` + `Number(3)`, `+n+1` as
   `Delim('+')` + `Ident('n')` + `Number(1)` — and I verified all of them
   against the tokenizer empirically rather than reasoning about them. 13
   formulas are pinned in `test_nth_child_formulas`; the untested corners are
   the invalid ones.
3. **Deviation 5's "malformed argument never matches" choice.** This is the one
   place where the engine's behaviour differs from a browser in a way an author
   could observe: `p:nth-child(banana), a { color: red }` colours the `a` here
   and nothing in a browser. It is defensible (it matches the existing rule for
   unknown pseudo-classes) but it is a real divergence and the alternative —
   validating An+B at parse time — is a clean fix Task J or a later task could
   take.
4. **`RuleIndex`'s `_default_selector_of` guesses `.selector`.** That attribute
   name is speculative: Task J does not exist yet. If J's rule shape differs,
   it should pass `selector_of` rather than renaming its field to fit.
5. **Right-to-left worst case.** `matches` is worst-case exponential in the
   number of descendant combinators (`a b c d e` against a deep tree). Every
   engine has this and every engine lives with it; the corpus's 2.89% says it
   does not bite here, but a pathological selector would not be caught by any
   test in this repo.
6. **`:root` on a detached subtree** (deviation 12) and **`:last-child`/
   `:only-child` on an element with no parent** both answer `True`, which is
   right for a document root and arguable for a fragment. Nothing depends on it
   yet.

## 8. Handoff to Task J

- Expand `p, .a { … }` into one `(Complex, declarations)` entry per selector
  before indexing — `RuleIndex` and `matches` both reject a `SelectorList` by
  design, and each selector has its own specificity anyway.
- Pass `selector_of=` rather than shaping your rule type around this module.
- `candidates()` order is construction order, but sort by your own explicit
  source index regardless: source order is J's business, not the index's.
- `annotate_positions(document)` before styling. Matching works without it, but
  it turns every `:nth-child`/`:first-child` test from a sibling scan into an
  attribute read.
- No metrics are emitted here. Matching is not a pipeline stage; `cssparse`'s
  row is `style_document`'s to write, and `RuleIndex` deliberately keeps no
  counters of its own. If the analysis half wants a candidate-narrowing number,
  the cheapest source is `sum(len(index.candidates(e)) for e in elements)` at
  the call site, which is what the corpus test does.

---

# Fix round 1

**Commit:** `2b992c6` — *cssparse: fix round 1 for task H review*
**Tests:** `6366 passed, 72 xfailed, 0 failed` (was 6340; net +26 — one test
deleted, 27 added). **Conformance unmoved:** `780/1592`, `64/112`.

## 1. The blocker: the fourth vacuous test, and it was mine

`test_matching_a_real_page_does_not_raise` carried a `break` in its innermost
loop, so each selector ran against `<html>` and nothing else. The reviewer
proved it by planting `raise RuntimeError` in the descendant-combinator
branch: the neighbouring sweep caught it, this test did not.

**I deleted it rather than repairing it.** The brief offered both, and
deletion is right here because the test was *strictly* subsumed:
`test_the_index_never_drops_a_rule_that_matches_a_real_page` already evaluates
`matches(element, selector)` for every element × selector pair on every corpus
page. Dropping the `break` would have re-run that identical loop — doubling the
corpus file's runtime — to assert something weaker than the assertion sitting
next to it. I re-ran the reviewer's own probe against the corpus file to be
sure the coverage genuinely lands somewhere: the sweep fails, the other two
pass. The deleted test's rationale (the features only real pages exercise —
`:not(.notheme)`, `[dir="rtl"]`, stacked compounds) now lives in the sweep's
docstring, along with a note recording why the separate test went away, so
nobody re-adds it.

On the shape the reviewer named: four vacuous tests in one file, and every one
of them was found by injection rather than by reading. Mine and theirs failed
the same way — the test exercised less than its name implied, and looked
correct while doing it. The only defence that worked in either case was
planting the bug and watching.

## 2. `+-n`: fixed rather than disclosed

`+-n` parsed to `(-1, 0)`. The instruction was to add it to deviation 6's list
of accepted-but-invalid forms; **I fixed the code instead**, and want that
divergence visible rather than buried.

The reason is the boundary deviation 6 actually draws. Its other entries are
unfixable *here*: the tokenizer folds a number's sign into its value and does
not record that a sign was present, so `2n 1` and `2n+1` are the same tokens
and no amount of care in this module can separate them. `+-n` is not like
that — its invalidity survives tokenization intact, as a `Delim('+')` followed
by a `-`-initial `Ident`, and rejecting it is a two-line guard. Deviation lists
in this codebase are for choices; this was a bug that happened to look like
one. Filing it as a deviation would have made the list mean two things.

Deviation 6 now states the boundary explicitly and names the three forms whose
invalidity *is* recoverable (`2n + -1`, `+ n`, `+-n`), all of which reject, so
the distinction is written down rather than implied. Both directions are
injected (§5).

## 3. Deviation 6's prose was wrong where the code was right

It called `2n + 1` spec-invalid. It is valid: `<n-dimension> ['+' | '-']
<signless-integer>` permits whitespace between component values, and only the
`+`-before-`n` position carries the `†` no-whitespace marker. The code accepted
it correctly and for the correct reason. Fixed the sentence, not the code — and
rewrote the deviation to name exactly one accepted-but-invalid family (a
signless integer where `<signed-integer>` is required: `2n 1`, `n 3`, `-n 3`)
instead of the two it vaguely gestured at. The rewrite says outright that an
earlier draft miscalled `2n + 1`, since this codebase has now had documentation
wrong in both directions and a silent correction teaches nothing.

## 4. The An+B memo

`_nth` re-parsed the argument on every element it was asked about — per-element
work inside the one module whose purpose is avoiding per-element work. The
parse is now memoized as `_an_b_memo` on the `PseudoClassSelector`.

**Measured: 2.1x** on `li:nth-child(2n+1)` against 2000 `li`s (14 ms → 7 ms).
**Zero effect on the corpus**, and that is worth stating rather than hiding:
the corpus's 47 pseudo-classes are `first-child`, `last-child`, `link`, `not`,
`target` and `visited` — not one `:nth-*` among them. The win is real and
currently unexercised by real input.

Three implementations were considered and the choice is documented as
deviation 14. A module-level dict keyed on the selector is not cheaper —
`PseudoClassSelector.__hash__` walks every argument token through `_token_key`
(deviation 10 of `selectors.py`), which costs about what the parse costs.
Keying on `id()` is unsafe, since ids are reused after a selector is freed and
a stale hit would answer with another selector's formula. So the memo goes on
the object.

The cost is writing an attribute onto another module's dataclass, and it is
safe in the way that matters: `_an_b_memo` is a pure function of `name` and
`argument`, and that class's equality and hash are computed from those fields
alone, so a memoized selector still compares, hashes and keys a dict
identically to a fresh one. It does mean deviation 10's "must not be mutated
afterwards" now has one sanctioned exception, which deviation 14 says out loud.
`test_the_an_b_memo_is_per_selector_and_invisible` pins both halves: the memo
must not leak between selectors, and equality/hash/dict-keying must be
unchanged after matching.

## 5. The 46-entry list, pinned from both sides

`test_attribute_value_case_follows_the_html_list`, 16 parametrized cases:
`type`, `lang` and `rel` as members; `name`, `href`, `id` and `class` as
**non-members**; and both the `i` and `s` overrides. The non-members are the
point — a test containing only members passes against a matcher that folds
every attribute value, which was the previous state with `type` alone. A
`rel="NOFOLLOW"` attribute was added to an existing `<a>` in the wide fixture
to reach a second member; it changes no element count, class or sibling
relationship, so no other test's expectations move.

## 6. Injection round for the fixes

Same method as §6 above: `PYTHONPATH` shadow copy, `__file__` asserted under
`/tmp/mayshay_shadow` before every run, nothing in the repo or `.venv/`
touched, shadow deleted afterwards. **10 injections, all 10 caught.**

| injected bug | caught by |
|---|---|
| the reviewer's probe: descendant branch raises | 7 fixture tests **+ the corpus sweep** (verified separately) |
| `+-n` accepted again (the finding, un-fixed) | `test_nth_child_formulas[+-n+2]` |
| `+ n` accepted (whitespace across the `†` marker) | `test_nth_child_formulas[+ n]` |
| `2n + -1` accepted (signed where signless required) | `test_nth_child_formulas[2n + -1]` |
| An+B memo shared across all selectors | 25 tests, incl. the new memo test |
| over-correction: every attribute value case-insensitive | 6 cases of the new parametrized test |
| under-correction: no HTML list at all | 3 cases |
| the `i`/`s` modifier ignored | 4 cases |
| **`rel` dropped from the 46-entry list** | `[a-[rel="nofollow"]-True]` |
| **`href` added to the list (a false member)** | `[a-[href="/X"]-False]` |

The last two are the ones worth having: they test *membership* of the list, in
both directions, rather than testing that the case-folding mechanism fires.

**One case in the new parametrization does not discriminate on its own, and
says so in a comment.** `+-n` un-fixed parses to `(-1, 0)`, whose only
solutions are indices `<= 0`, so the broken matcher also returns `[]` and the
`("+-n", [])` row passes either way. `("+-n+2", [])` is the row that catches
it. Both are kept — one documents the form, the other does the work — and the
comment names which is which, because an unlabelled passing row is exactly the
thing this review round was about.

## 7. What still stands from the original report

Nothing in §§1–7 above the fix round is retracted. The catch-all gap is
unchanged and remains carried by fixture tests (`found = []` still leaves all
three corpus tests green, now that there are three); `_default_selector_of`'s
`.selector` guess is still speculative and still the thing Task J should
override with `selector_of=` rather than rename around; and the right-to-left
worst case is still untested and still shared with every shipping engine.
