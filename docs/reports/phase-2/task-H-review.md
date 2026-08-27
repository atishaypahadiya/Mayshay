# Task H review: selector matching and rule indexing

Reviewed: `review-69c095f..a05a103.diff` (3 new files, 1495 insertions) against
`task-H-brief.md` and `task-H-report.md`.

---

## Spec Compliance

**✅ Spec compliant.**

Both brief interfaces exist with the required semantics:

- `matches(element, complex_selector) -> bool` — `src/mayshay/cssparse/matching.py:249`.
- `RuleIndex(rules)` with `.candidates(element) -> list[Rule]` —
  `matching.py:648` / `matching.py:685`.
- Both required files created; both brief tests files transcribed verbatim
  above the `# -- additional discrimination tests --` marker
  (`tests/cssparse/test_matching.py:44-107` matches the brief line for line).

**Right-to-left matching: confirmed.** `_match_from(element, selector, index)`
(`matching.py:277`) starts at `len(compounds) - 1` (`matching.py:266`) and moves
one compound *left* per call, following `_parent_element` /
`_preceding_element_siblings`. There is no subtree enumeration anywhere in the
module. Recursion depth is bounded by compound count, as claimed.

**Indexing by rightmost id/class/tag: confirmed.** `_bucket_for`
(`matching.py:671`) reads `selector.compounds[-1].simples` and files under the
first id, then class, then type. I verified the "rightmost" claim by injection
(below), not by reading alone.

**⚠️ Cannot verify from diff:**

1. **Task J's rule shape.** `_default_selector_of` (`matching.py:617`) guesses
   `.selector`. Task J does not exist, so whether that guess is right cannot be
   checked here. The `selector_of=` escape hatch (`matching.py:653`, exercised
   at `test_matching.py:600`) makes this a non-issue in either direction — J can
   pass a lambda. See "Handoff" below for the one real constraint.
2. **19 of the 25 injections.** I reproduced 6 (see §Injections); the remaining
   19 I take on the report's word, calibrated by the 6 that all reproduced
   exactly as described.
3. **Suite / conformance numbers** (6340 passed, 780/1592) — controller states
   these were already verified mechanically; not re-run.

---

## The HTML case-sensitive-attribute list (the dispatch correction)

**The implementer's correction of the brief is right, and the list is exact.**

The brief's framing ("attribute values are case-sensitive") is a simplification.
The HTML Standard, *Case-sensitivity of selectors*
(https://html.spec.whatwg.org/multipage/semantics-other.html#case-sensitivity-of-selectors):

> "Attribute selectors on an HTML element in an HTML document must treat the
> *values* of attributes with the following names as ASCII case-insensitive:"

I fetched that section and diffed it name-by-name against
`_HTML_CASE_INSENSITIVE_ATTRS` (`matching.py:167-176`):

```
spec count 46, unique 46
impl count 46
missing from impl: []
extra in impl:     []
```

**46 in the spec, 46 implemented, zero omissions, zero false members.** I ran a
second fetch with the candidate list supplied in the prompt, asking for
name-by-name differences in both directions, and got "none" both ways. This is
the risk class the controller flagged (a quirks-mode-table-shaped silent
mismatch) and it is clean.

Two supporting details I checked because the list alone is not the whole rule:

- **The `i`/`s` modifier overrides in both directions**
  (`_attribute_is_case_insensitive`, `matching.py:400`), and the parser
  ASCII-lowercases the flag itself (`selectors.py:755`), so `[id="MAIN" I]`
  behaves as `i`. Without that lowercasing the `selector.case == "i"` comparison
  would silently fall through to case-sensitive; it is correct.
- **The "HTML element in an HTML document" precondition** is not tested for.
  Documented as deviation 4 and correct for an engine with no foreign content
  and no XML mode.

Test coverage of the list itself is thin: `type` is the only attribute pinned
(`test_matching.py:337`). That is acceptable — the failure mode of a wrong
*entry* is caught by the spec diff, not by a test — but a parametrized sample of
4-5 (`rel`, `lang`, `dir`, plus a non-member like `id`/`href`) would be cheap.
Minor.

---

## The An+B micro-grammar

**Judgement: correct, and the only leniencies are on the disclosed axis.**

`selectors.py` deliberately keeps functional arguments as raw tokens
(its deviation 3), so this grammar is entirely new here and is unreviewed
anywhere else. I swept it directly (`_parse_an_b`, `matching.py:503`) against
Selectors 4 §9.2 / css-syntax-3 §6.

**All 31 valid forms parse to the correct `(a, b)`** — including every form the
controller named and the ones that catch people:

| form | `(a,b)` | form | `(a,b)` |
|---|---|---|---|
| `odd` / `ODD` | (2,1) | `even` | (2,0) |
| `n` / `N` | (1,0) | `-n` | (-1,0) |
| `+n` | (1,0) | `2n` | (2,0) |
| `2n+1` | (2,1) | `2n-1` | (2,-1) |
| `-n+3` | (-1,3) | `+3` | (0,3) |
| `3` / `-3` | (0,±3) | `2n + 1` | (2,1) |
| `2n +1` | (2,1) | `2n - 1` | (2,-1) |
| `n+2` | (1,2) | `n-3` | (1,-3) |
| `-n-3` | (-1,-3) | `+n+1` | (1,1) |
| `-1n+6` | (-1,6) | `0n+5` | (0,5) |
| `n- 3` | (1,-3) | `-n- 3` | (-1,-3) |
| `+n - 1` | (1,-1) | `1n+0` | (1,0) |

The sign handling is right in all three places it is easy to get wrong: the
`-n` ident (`_parse_n_ident`, `matching.py:546`), the single-token
`Dimension(2,'n-1')` / `Ident('n-3')` forms (`_parse_n_unit`, `matching.py:555`),
and the split `Delim('+'|'-') <integer>` tail (`_parse_b`, `matching.py:582`).

**Invalid forms are rejected, not silently zeroed.** Of 30 invalid inputs
(`banana`, ``, `n+`, `+ n`, `n +`, `2n+`, `2.5n+1`, `2n+1.5`, `n-`, `-n-`,
`of .a`, `2 of .sel`, `2n of .a`, `n n`, `odd 2`, `--n`, `n--3`, `n-x`, `- 3`,
`+`, `*`, `n-٣`, `3 4`, …) **26 return `None`**, which `_nth` (`matching.py:495`)
turns into "never matches" — the documented deviation 5, not a zero.
Non-ASCII digits are explicitly guarded (`_is_ascii_digits`, `matching.py:575`),
which is a genuinely easy miss (`'٣'.isdigit()` is `True` and `int()` accepts it).

`_an_b_contains` (`matching.py:504`) is correct including the `n >= 0`
requirement and negative `a`; I checked 11 `(a,b)` pairs over indices 1-10,
covering `-n+3 → {1,2,3}`, `3n-1 → {2,5,8}`, `-2n+5 → {1,3,5}`,
`-n+0 → {}`. All correct.

**The 4 accepted-but-invalid forms:**

- `2n 1`, `2n++1`, `2n-+1`, `n+ +1` — all one root cause, and it is
  **disclosed as deviation 6**: `Number` carries no "sign character present"
  flag, so `<signed-integer>` and `<signless-integer>` are indistinguishable
  here. The fix genuinely belongs in the tokenizer. Accepted.
- `+-n` → `(-1, 0)` — the `Delim('+')` branch (`matching.py:527`) hands the
  following ident to `_parse_n_ident`, which honours its leading `-`. This one
  is **not** the signed/signless axis and is therefore **not covered by
  deviation 6's stated reason**. Minor, undisclosed. One-line fix: reject an
  ident starting with `-` in that branch.

**One docstring error, not a code error:** deviation 6 (`matching.py:104`) says
the module accepts `2n + 1` "where the spec wants the second half signless".
`2n + 1` *is* the signless form — `<n-dimension> ['+' | '-'] <signless-integer>`
— and is valid CSS. The implementation handles it correctly; only the prose is
wrong. The genuinely lenient members of that class are the four listed above.

---

## The `RuleIndex` catch-all and the disclosed corpus gap

**The catch-all is correct and the disclosed gap is real. I verified both.**

`candidates()` seeds `found = list(self._catch_all)` first (`matching.py:689`)
and every keyless rightmost compound lands there (`_bucket_for` falls through at
`matching.py:683`). `*`, `[hidden]`, `:hover`, `:is(.a,.b)` and `::before`-only
compounds all take that path.

**The disclosed gap is true.** I injected the dropped catch-all
(`found = []`) and ran the corpus file alone:

```
tests/cssparse/test_matching_corpus.py ....   [100%]     # 4 passed
```

All four corpus tests stay green with the catch-all bucket deleted, exactly as
the report claims. The report's explanation — none of the corpus's 279 selectors
has a keyless rightmost compound — is the right diagnosis, and it is recorded
where it belongs, in the corpus file's own module docstring
(`test_matching_corpus.py:29-38`), so nobody later assumes coverage that is not
there.

**Is the unit coverage adequate instead? Yes.** The same injection against the
fixture file fails four tests:

```
FAILED test_rule_index_returns_the_catch_all_bucket_for_every_element
FAILED test_rule_index_candidates_are_exactly_the_reachable_rules
FAILED test_rule_index_never_drops_a_rule_that_matches
FAILED test_rule_index_returns_rules_in_construction_order
```

`test_rule_index_returns_the_catch_all_bucket_for_every_element`
(`test_matching.py:546`) is the direct guard and asserts the property
element-by-element over the whole wide tree, not on one sample.
`test_rule_index_candidates_are_exactly_the_reachable_rules`
(`test_matching.py:557`) is the strongest test in the file: exact list equality
for two elements against a 16-rule index, so it pins bucket *choice*, catch-all
inclusion, ordering and absence simultaneously. That is more than adequate
compensation for the corpus's blind spot.

**A rule that cannot be keyed at all raises rather than vanishing: confirmed.**
The distinction is handled at the right layer:

- A rule whose *rightmost compound* has no usable key → catch-all
  (correct: it may still match anything).
- A rule whose *selector cannot be found* → `TypeError` with an actionable
  message (`_default_selector_of`, `matching.py:617-641`), separately for the
  `SelectorList` case (`matching.py:632`) and the unrecognised-shape case
  (`matching.py:638`). Both are pinned by `test_rule_index_rejects_a_selector_list`
  (`test_matching.py:611`), which covers `RuleIndex([listed])` *and*
  `RuleIndex(["not a selector"])`.

That is the right call, and the report's reasoning for it is sound: bucketing an
unidentifiable rule as universal would make it "correct" by never matching,
which hides a caller bug behind a silent no-op.

---

## Injections: 6 of 25 reproduced

Method: `cp -R src/mayshay /tmp/msh_review_$$/`, patch the shadow, run pytest
with `PYTHONPATH` pointed at it, asserting
`mayshay.cssparse.matching.__file__` resolved under `/tmp/...` before trusting
anything. Shadow deleted; repo, index and `.venv/` untouched throughout
(verified at the end — see §Environment).

| # | injected bug | claimed catcher | reproduced? |
|---|---|---|---|
| 3 | keys on the **leftmost** compound | `…files_a_rule_under_its_rightmost_compound` + 2 | ✅ 3 tests fail, exactly those named |
| 4 | drops the catch-all bucket | `…returns_the_catch_all_bucket_for_every_element` + 3 | ✅ 4 tests fail |
| 9 | `+` behaves like `~` | `test_adjacent_combinator_is_not_general_sibling` | ✅ that test, alone |
| 15 | **over-correction:** class matching folds case | `test_class_matching_is_case_sensitive` | ✅ that test, alone |
| 16 | **over-correction:** all attribute values fold | 4 tests | ✅ 3 tests fail |
| 17 | **under-correction:** no HTML attribute list | `test_html_case_insensitive_attributes_ignore_value_case` | ✅ that test, alone |

Plus one of my own: **attribute *presence* always true** (`return True` on the
`name not in element.attrs` branch) → caught by
`test_attribute_operators[[href]-False]`. This matters because the brief's own
`test_attribute_presence_and_value` (`test_matching.py:85`) asserts only
*positive* cases and passes under that bug; the parametrized replacement closes
it. That is a fourth non-discriminating brief test the report did not name,
though it is already covered.

**The over/under-correction pair (15/16 vs 17) is genuine and is the most
valuable thing in the sweep.** 17 (no list at all) and 16 (fold everything) fail
*different* assertions inside the same test plus different neighbours, so the
rule is pinned from both sides. A future "fix" cannot swing past correct without
a red test. Same for 22/23 on `:empty` (claimed, not reproduced by me). This is
the Task G practice applied correctly.

**The report's own two findings are both true**, and I verified both rather than
accepting them: the brief's `test_rule_index_narrows_candidates` stayed green
under injections 3 and 4 in my runs, and the corpus stayed green under 4.

---

## The fourth non-discriminating test

**Found: `test_matching_a_real_page_does_not_raise`
(`tests/cssparse/test_matching_corpus.py:141`).**

```python
for selector in selectors:
    for element in elements:
        assert matches(element, selector) in (True, False)
        seen += 1
        break
```

The `break` fires after the *first* element of the page — always `<html>`. So
each selector is tested against exactly one element, which fails its rightmost
compound immediately for nearly every corpus selector. The docstring's claim
("`:not(.notheme)`, `[dir="rtl"]`, stacked compounds reach the matcher here") is
therefore false for almost all of them: right-to-left matching short-circuits
before the combinator branches are ever entered.

Proven by injection: I planted `raise RuntimeError` in the descendant-combinator
branch (`matching.py:280`) and ran the corpus file. Result:

```
FAILED test_the_index_never_drops_a_rule_that_matches_a_real_page
```

— and `test_matching_a_real_page_does_not_raise` **passed**. It did not detect a
hard crash in the most common combinator in CSS. Its stated purpose is served
entirely by its neighbour two functions up, which sweeps every element against
every selector.

Fix: delete the `break` (making it a real sweep), or delete the test as
subsumed. The `seen >= MIN_SELECTORS` coverage floor is worth keeping either way.

---

## Strengths

- **The spec-list correction was the right call and executed exactly.** 46/46,
  no false members. Correcting a reviewer's dispatch and then transcribing a
  46-entry spec table without a single error is the single hardest thing in this
  diff.
- **`test_rule_index_candidates_are_exactly_the_reachable_rules`**
  (`test_matching.py:557`) — exact list equality over a 16-rule index pins four
  properties at once. This is the model for how to test an index.
- **`test_rule_index_never_drops_a_rule_that_matches`** (`test_matching.py:576`)
  cross-checks the index against the matcher over every (element, rule) pair,
  with a `total < len(rules) * len(elements) / 2` floor in the same test so
  "return everything" cannot pass it either. Superset *and* narrowing, pinned
  together — the brief's `<` alone was satisfiable by returning nothing.
- **`test_descendant_backtracks_past_the_first_matching_ancestor`**
  (`test_matching.py:225`) with the deliberately nested `.x` fixture. Committing
  to the nearest matching ancestor is *the* classic right-to-left bug and the
  brief's tree could not express it.
- **`test_nth_child_works_without_annotate_positions`** (`test_matching.py:388`)
  catches a bug the brief's fixture structurally cannot, since it always
  annotates. `_element_index0` (`matching.py:236`) computes the fallback rather
  than defaulting to 0.
- **Deliberate token-form verification over reasoning.** The surprising forms
  (`Dimension(2,'n-1')` as one token, `Ident('-n')` + `Number(3)`) are handled
  because they were checked empirically; I re-derived them from the tokenizer
  and they are as described.
- **13 deviations documented in the module docstring**, in the house style, each
  with its reasoning and its cost. Deviations 5, 6 and 7 disclose real
  divergences from browser behaviour rather than papering over them.
- **The report's §7 tells the reviewer where to look**, and both places it flags
  hardest (the attribute list, the An+B parser) are exactly where the risk was.
  That is honest self-assessment, not decoration.

---

## Issues

### Critical (Must Fix)

None.

### Important (Should Fix)

1. **`tests/cssparse/test_matching_corpus.py:141`** —
   `test_matching_a_real_page_does_not_raise` asserts essentially nothing. The
   `break` limits each selector to `elements[0]` (`<html>`); a planted
   `RuntimeError` in the descendant-combinator branch was caught by the
   neighbouring test and **not** by this one. It is fully subsumed by
   `test_the_index_never_drops_a_rule_that_matches_a_real_page`
   (`test_matching_corpus.py:113`). Remove the `break` so it becomes the sweep
   its docstring describes, or delete it.

### Minor (Nice to Have)

2. **`matching.py:495`** — `_nth` calls `_parse_an_b(selector.argument)` on
   *every* element it is asked about. In the one task whose stated purpose is
   not doing per-element work, `:nth-child(2n+1)` re-parses its formula once per
   candidate element. `PseudoClassSelector` is hashable (deviation 10 of
   `selectors.py`), so a module-level `dict` keyed on the selector, or a parse
   cached at first use, removes it. Not a correctness issue and not on the hot
   path for the current corpus (which has few `:nth-*`), but it is the kind of
   thing Task J's cascade will amplify across a whole document.

3. **`matching.py:527`** — the `Delim('+')` branch accepts `+-n` as `(-1, 0)`,
   because it hands the following ident to `_parse_n_ident`, which honours a
   leading `-`. The spec rejects it, and unlike the four forms deviation 6
   covers, this is not the signed/signless ambiguity — so it is an undisclosed
   leniency. Reject an ident beginning with `-` in that branch, or extend
   deviation 6 to name it.

4. **`matching.py:104` (deviation 6 prose)** — states `2n + 1` is a form "the
   spec rejects". It is not: `<n-dimension> ['+' | '-'] <signless-integer>` is
   valid, and the code handles it correctly. The genuinely lenient forms are
   `2n 1`, `2n++1`, `2n-+1`, `n+ +1`. The code is right; fix the sentence so a
   later reader does not "correct" working behaviour.

5. **`test_matching.py:337`** — only `type` is pinned from the 46-entry
   attribute list. A parametrized sample (`rel`, `lang`, `dir`, `media`, plus a
   deliberate non-member such as `href`) would cost three lines and would catch
   a future accidental edit to the frozenset.

6. **`test_matching.py:49`** — `test_class_selector_uses_the_precomputed_set`
   (brief-verbatim) asserts nothing about `class_list` being the source; any
   correct class implementation passes. Brief-verbatim, so leave it — noted only
   so the name is not trusted as coverage of the precomputed-set claim.

7. **`matching.py:249` vs `matching.py:617`** — `matches()` accepts a `Simple`,
   `Compound` or `Complex`, but `RuleIndex`'s default `selector_of` accepts only
   a `Complex`. Harmless today (`parse_selector_list` always yields `Complex`)
   but the two entry points advertise different input contracts.

---

## Focused checks outside the diff

Each was driven by a named risk, per the review protocol:

1. **Risk: `_matches_pseudo_class` (`matching.py:412`) branches on
   `selector.selectors is not None` *before* the dispatch table, so any
   pseudo-class the parser resolves into a nested selector list bypasses
   deviation 10 entirely — `:has(> p)` would silently behave as `:is()`.**
   Checked `selectors.py:205-211`: `_SELECTOR_ARG_PSEUDOS` is exactly
   `{not, is, where, matches}`. `:has` is not in it and keeps raw tokens, so it
   falls through to the dispatch-table miss and returns False. Confirmed
   behaviourally by `test_visited_and_dynamic_pseudo_classes_never_match`
   (`test_matching.py:1191`), which includes `":has(q)"`. **Clear.**

2. **Risk: `_attribute_is_case_insensitive` compares `selector.case == "i"`;
   if the parser preserved the flag's case, `[id="MAIN" I]` would silently fall
   through to case-sensitive.** Checked `selectors.py:751-756`: the flag is
   `_ascii_lower`ed at parse time. **Clear.**

3. **Risk: `_nth_last_child` (`matching.py:459`) mixes a computed
   `_element_siblings` length with a cached `element_index`; if
   `annotate_positions` counted anything other than element siblings, the two
   halves would disagree and `:nth-last-child` would be off by the number of
   text nodes.** Cross-checked `element_index` against
   `_index_of(_element_siblings(x), x)` for **every element of every corpus
   page: 8596 elements, 0 mismatches, 0 unannotated**. **Clear.**

---

## Handoff to Task J — assessment

`selector_of` is a workable shape for J. The hook was invented because the brief
named a `Rule` type that does not exist, and it resolves that correctly: J can
define `Rule(selector, declarations, order, specificity)` and pass
`selector_of=lambda r: r.selector` (or rely on the `.selector` default), and
`candidates()` returns *its* objects, so selector, specificity and source order
all travel together with the rule. `test_rule_index_accepts_a_selector_of_hook`
(`test_matching.py:600`) exercises both an attribute-carrying object and a plain
tuple, so both shapes are proven, not assumed.

Two constraints J genuinely inherits, both correctly documented:

- **A `SelectorList` is rejected by both entry points** (`matching.py:258`,
  `matching.py:632`). J must expand `p, .a { … }` into one entry per selector
  before indexing. This is right — each selector has its own specificity, and a
  bare boolean over a list could not tell J which one to use.
- **`candidates()` returns construction order, not cascade order**
  (deviation 13, `matching.py:696`). The docstring correctly tells J to sort by
  its own explicit source index anyway. The reason given — `class_list` is a
  `frozenset`, so bucket order is not stable *between runs* — is real, and the
  report's five-seed `PYTHONHASHSEED` check is the right way to have confirmed
  it.

The one thing J should not do is rename its field to match the `.selector`
guess; the report says so explicitly (§7.4), which is the correct advice.

---

## Environment

Verified after all injection work, per the standing warning:

```
$ git status --porcelain          # (empty)
$ git rev-parse --abbrev-ref HEAD
phase-2-css-to-styled-tree
$ cat .venv/lib/python3.13/site-packages/__editable__.mayshay-0.1.0.pth
/Users/atishaypahadiya/projects/mayshay/src
$ .venv/bin/python -c "import mayshay.cssparse.matching as m; print(m.__file__)"
/Users/atishaypahadiya/projects/mayshay/src/mayshay/cssparse/matching.py
$ ls /tmp | grep -c msh_review
0
```

Nothing under `.venv/` was modified, nothing was uninstalled, the working tree
is clean, and the shadow copy is gone.

---

## Assessment

**Spec compliance:** ✅ Spec compliant (with the ⚠️ items above).

**Task quality:** **Approved**, conditional on Issue 1 (the `break` in
`test_matching_a_real_page_does_not_raise`) — a one-line test fix, not an
implementation change.

**Reasoning:** The implementation is spec-correct at every point I could check
independently: the 46-attribute HTML list is exact in both directions, the An+B
grammar accepts all 31 valid forms and rejects 26 of 30 invalid ones with the
four exceptions traceable to a disclosed tokenizer limitation, matching is
genuinely right-to-left, and the `RuleIndex` superset invariant is pinned by
tests that I confirmed fail under the bugs they claim to catch. The implementer
correctly overrode the brief on attribute-value case-sensitivity and wrote a
grammar the brief never asked for, and disclosed the one place its own corpus
sweep is blind rather than letting the green ticks speak. The single Important
finding is a corpus test whose `break` makes it non-discriminating — the fourth
instance of the pattern this project keeps producing, and the reason to keep
looking for a fourth.
