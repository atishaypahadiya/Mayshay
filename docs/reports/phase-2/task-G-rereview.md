# Task G fix round re-review (f647da8..717f839)

### Finding Verdicts

1. **Deviation 1 relabelled as browser parity, not conformance** — ADDRESSED.
   `src/mayshay/cssparse/selectors.py:42-57`: states plainly "a deliberate
   divergence from the spec, not conformance to it," cites Selectors 4 §16
   ("white space" only), css-syntax-3 §9 (comment "must have no effect"),
   names both Blink (`css_tokenizer.cc`, character-level `~=`) and
   Gecko/Servo (`cssparser/tokenizer.rs`, `starts_with(b"~=")`), and ends
   "Do not 'fix' this back to the spec letter... it is browser parity on
   purpose." An accurate reversal, not softened wording.

2. **Deviation 7's `::before::after` citation** — ADDRESSED.
   `selectors.py:99-111` splits the rule: type-leads-compound is genuinely
   `<compound-selector>` §4.3 grammar; pseudo-element stacking is now
   labelled "a scope limit we chose, not something the grammar forbids,"
   citing §16's `<pseudo-compound-selector>*`.

3. **Selector structures unhashable, blocking Task H** — ADDRESSED, with a
   residual gap (see below). `selectors.py:168-297`: every `Simple`
   variant, `Compound`, `Complex`, `SelectorList` defines `__hash__` in its
   own class body; `Compound.pos`/`Complex.pos` are `field(compare=False)`
   (`selectors.py:271-272`, `293-294`). Verified structurally hashable and
   dict-keyable (`tests/cssparse/test_selectors.py:533-553`, all pass).

4. **Bare `:where` returning `(0,0,0)`** — ADDRESSED.
   `selectors.py:817-830` (`_pseudo_class_specificity`): `selectors is not
   None` is checked before the name, so bare `:where`/`:not`/`:is` all fall
   through to `(0,1,0)`; only `:where()`/`:where(a)` hit `_ZERO`. Pinned by
   `test_bare_where_is_an_unknown_pseudo_class_not_the_functional_one`.

5. **`:matches()` undocumented; `::part(x` misreported** — ADDRESSED.
   `selectors.py:69-83` documents `:matches()` as `:is()`'s alias;
   `selectors.py:740-746` moves the double-colon raise before
   `_consume_function_argument`, so `::part(x)` and `::part(x` both report
   "functional pseudo-element ... is not supported," while `:not(a`
   (a real pseudo-*class*) still says "unterminated." Pinned by
   `test_unterminated_functional_pseudo_element_blames_the_right_thing`.

6. **Ad-hoc 156-rule sweep, not a committed test** — ADDRESSED.
   `tests/cssparse/test_selectors_corpus.py` (new, 207 lines): 193 rules /
   279 selectors / 0 rejected, floors at every level (`MIN_HTML_FILES=3`,
   `MIN_FILES_WITH_STYLE=2`, `MIN_STYLE_ELEMENTS=15`, `MIN_RULES=180`,
   `MIN_SELECTORS=260`), plus a 12-case strict-forms guard tagged by
   deviation. Confirmed passing (`pytest tests/cssparse/ -q`: 100 passed).

### `pos`/`__hash__` blast radius

Hash/eq agreement holds everywhere: `Compound.__hash__` hashes only
`simples` (matching its `compare=False` on `pos`), `Complex.__hash__` hashes
only `compounds`/`combinators`, and every `Simple` variant's `__hash__`
matches its full (default) `__eq__` field set. No case of equal objects
hashing apart.

**But the pos-exclusion is incomplete**, and this is a real inconsistency
the brief asked me to hunt for. `PseudoClassSelector.argument` (used for
every functional pseudo-class *not* in `_SELECTOR_ARG_PSEUDOS` — e.g.
`:nth-child()`, `:lang()`, `:dir()`) holds raw `CssToken`s, and
`tokenizer.py`'s tokens keep `pos` *inside* equality (confirmed:
`grep pos: src/mayshay/cssparse/tokenizer.py` — plain `@dataclass`, no
`compare=False`). So two syntactically identical selectors ending in such a
pseudo-class, written at different offsets, do NOT compare equal, defeating
deviation 10's stated purpose. Verified live:

```
sel(':nth-child(2n+1)') == sel('   :nth-child(2n+1)')   # -> False
hash(...) == hash(...)                                   # -> True (name-only hash, allowed)
```

Hash/eq contract isn't violated (unequal-but-same-hash is legal), but the
documented guarantee "two structurally identical selectors written at
different source offsets compare equal" (`selectors.py:349-351`) is false
whenever the rightmost compound carries a raw-argument pseudo-class. No test
catches this — `test_pos_is_excluded_from_equality_but_still_recorded` and
`test_equal_selectors_hash_equal_and_key_the_same_dict_entry` only use
plain/`.c`-style compounds, never a `:nth-child()`-style argument. This is
exactly the kind of Task-H trap deviation 10 exists to prevent (a dict keyed
by rightmost compound would silently split one selector into two buckets
across `<style>` blocks).

### Cross-references (item 2 in "Where I want your effort")

Every `deviation N` reference resolves and none renumbered: 1, 2, 3, 7, 8, 9
all still point to unchanged entries; 10 is appended after 9, not inserted.
`grep -n "deviation [0-9]"` across `selectors.py` + both test files shows no
reference to a number that shifted. Confirmed no renumbering repeat of
commit 1ff2448's defect.

### Empty-corpus guard (item 3)

Confirmed working, not just claimed. Independently reproduced: monkeypatched
`test_selectors_corpus.CORPUS` to an empty temp dir and called
`test_the_corpus_sweep_is_not_silently_empty()` directly — it raises
`AssertionError` (the `len(list(CORPUS.glob("*.html"))) >= MIN_HTML_FILES`
line fires first). The other floors (`MIN_RULES`, `MIN_SELECTORS`, etc.)
are plain `>=` comparisons against an empty list/set, so they fail
identically by construction; this is not fragile.

### New Breakage in the Fix Diff

None Critical. One Important gap: the pos/argument inconsistency above is a
latent correctness issue for Task H (not introduced by this diff exactly —
the underlying token-pos-in-eq behavior predates it — but this diff's fix
for deviation 10 is incomplete and its own docstring overclaims uniform
pos-independence). No regressions: full targeted run
(`tests/cssparse/test_selectors.py` + `test_selectors_corpus.py`) is 100/100
passed. `git status` clean; `.pth` file unmodified
(`/Users/atishaypahadiya/projects/mayshay/src`).

### Out-of-Scope Observations

- `_nested_preludes` in the corpus test duplicates a slice of grammar logic
  the public API doesn't expose (report's own item 8) — outside this diff's
  correctness, flagged for whoever adds a public rules-from-tokens entry
  point.
- `PseudoClassSelector.__hash__` name-only collision (documented, accepted)
  is fine as designed; not a defect.

### Verdict

**Fix round:** All six findings addressed. No Critical/Important breakage
introduced by the diff itself, but the `pos`/`__hash__` deep-dive requested
in this re-review surfaces one real, untested gap: deviation 10's equality
guarantee does not hold for selectors whose rightmost compound contains a
functional pseudo-class with a raw (non-selector-list) argument — e.g.
`:nth-child()` — because `PseudoClassSelector.argument` embeds `CssToken`s
whose `pos` still participates in equality. Recommend a follow-up (Task H
prerequisite): either strip `pos` from tokens before storing them in
`argument`, or normalize/compare `argument` by value, before Task H trusts
cross-occurrence equality of such selectors.
