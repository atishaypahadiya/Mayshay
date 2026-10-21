# Task G review: selectors and specificity

Base `48be545` -> head `3c2f5b1`. Read-only review; working tree untouched
(`git status` empty at finish, HEAD still `3c2f5b1`), `.venv` not modified
(`__editable__.mayshay-0.1.0.pth` md5 `3717d729cbbfc50ae0f221f1d9b09cdd`,
content `/Users/atishaypahadiya/projects/mayshay/src` — matches the report's
recorded value). `/tmp/g_shadow` is gone, as the report claims.

I did not re-run the suite. I ran one focused read-only probe
(`.venv/bin/python -c ...`, importing from the repo, confirmed via
`selectors.__file__`) for four specific doubts named below.

---

## The spec ruling: `[a~/**/="v"]`

**The rule is over tokens, not over source characters. By the letter of the
current specs `[a~/**/="v"]` is valid, and this implementation wrongly
rejects it. But every shipping engine also rejects it, so the *behaviour* is
defensible — what is wrong is the docstring's claim that the behaviour
follows from the spec.**

The three pieces of spec text:

1. Selectors 4 §16 Grammar (https://drafts.csswg.org/selectors-4/#grammar)
   defines the operator out of separate delims and then constrains only
   *white space*:

   > `<attr-matcher> = [ '~' | '|' | '^' | '$' | '*' ]? '='`
   >
   > In interpreting the above grammar, the following rules apply:
   > White space is forbidden:
   > […] Between the components of an `<attr-matcher>`.

   "White space" in a token grammar is `<whitespace-token>`. A comment is
   not a `<whitespace-token>`.

2. css-syntax-3 §4.3.2 Consume comments: the algorithm "returns nothing",
   and it is invoked from the top of §4.3.1 Consume a token. §9:

   > The tokenizer described in this specification does not produce tokens
   > for comments, or otherwise preserve them in any way. Implementations may
   > preserve the contents of comments and their location in the token
   > stream. **If they do, this preserved information must have no effect on
   > the parsing step.**

   That last sentence is normative and is decisive on its own: `pos`
   arithmetic that recovers "a comment was here" and lets it change the parse
   is exactly the thing forbidden.

3. The clincher, css-syntax-3 §9's comment-insertion table. Serialization
   must round-trip, and a comment must be inserted between any token pair
   listed with a ✗. The row headings are `ident, at-keyword, hash, dimension,
   #, -, number, @, ., +, /` — there is **no `~`, `|`, `^`, `$` or `*` row**,
   and no `=` column. So per css-syntax, delim(`~`) followed by delim(`=`)
   round-trips with no comment needed, i.e. the spec asserts `~=` and
   `~/**/=` tokenize identically. The old `<include-match-token>` family is
   gone from §4 (I checked the token list; it is not there), which is why
   Selectors 4 had to spell `<attr-matcher>` out of delims in the first
   place.

So a spec-conformant parser cannot see the difference, and the docstring's
justification at `src/mayshay/cssparse/selectors.py:37-49` — "a comment is a
token separator exactly as whitespace is", "exactly as when it was one
token" — is reasoning from the 2014 CR, not from the spec this module cites.

**However, the premise "browsers accept it" is false.** Both engine families
still lex the operator at the character level, from a leftover of the old
token family:

- Blink, `third_party/blink/renderer/core/css/parser/css_tokenizer.cc`:
  `case '~': if (ConsumeIfNext('=')) return CSSParserToken(kIncludeMatchToken);`
  — `ConsumeIfNext` reads the code-point stream, and comment consumption
  happens earlier in `NextToken`, so `~/**/=` yields two `kDelimiterToken`s
  and `CSSSelectorParser`'s attribute-match switch rejects them.
- Gecko/Servo, `rust-cssparser/src/tokenizer.rs`:
  `if tokenizer.starts_with(b"~=") { advance(2); IncludeMatch }` — same
  byte-level check, same outcome.

Conclusion: **keep the behaviour, fix the documentation.** Deviation 1 should
say "this is a deliberate deviation from the current Selectors 4 / css-syntax
grammar, matching what Blink and Gecko actually do, because both still
tokenize the operator at the character level", not "this is what the spec
requires". Under CLAUDE.md's "document every deviation" rule, a deviation
documented as conformance is a documentation defect, not a nit.

Corollary for finding 2 below: the test
`tests/cssparse/test_selectors.py:220-232` is *not* pinning a bug — it pins
real-world engine behaviour — but its docstring and inline comment repeat the
same wrong justification and should be reworded the same way.

The whitespace-separated forms (`[a ~ = "v"]`, `[a~ ="v"]`) are correctly
rejected, and that one *is* straight spec: §16 forbids white space between
the components of an `<attr-matcher>`.

---

## Spec Compliance

✅ Spec compliant against the brief, with the documentation defect above and
two smaller ones below.

Brief checklist, file by file:

- `src/mayshay/cssparse/selectors.py` — created. `Simple` (`:245-253`),
  `Compound` (`:259-268`), `Complex` (`:271-282`), `SelectorList`
  (`:285-289`), `parse_selector_list` (`:400-409`), `specificity`
  (`:715-745`). All interfaces present with the requested shapes.
- `tests/cssparse/test_selectors.py` — created; the brief's 7 test functions
  are transcribed verbatim (I compared them line by line against the brief;
  they match, including the weak `is not None` assertion in
  `test_attribute_operators`), followed by 65 added cases.
- `src/mayshay/cssparse/__init__.py` — re-exports, alphabetically ordered,
  `__all__` updated. Not requested by the brief but consistent with how
  `tokenizer`/`parser` are surfaced; harmless.

Level-3 feature set: type, universal, class, id, attribute, pseudo-class, and
`descendant`/`>`/`+`/`~` — all present. Specificity is the (a,b,c) triple with
the universal selector contributing nothing (`:743`).

Extra beyond the brief, all defensible and all documented except one:
pseudo-elements and their `c`-column specificity, the Level 4 `i`/`s`
attribute modifier, Level 4 recursive specificity for `:not`/`:is`/`:where`,
and forgiving parsing. The undocumented one is `:matches()`
(`selectors.py:151`) — the module docstring's deviation 3 lists only
`:not()`, `:is()`, `:where()`. See Minor.

⚠️ Cannot verify from diff:
- The corpus sweep ("156 style rules, 0 rejected") is an ad-hoc script, not a
  committed test. Nothing in the repo re-runs it, so it cannot regress-guard
  the strictness decisions (compound ordering, `#0f0`, namespaces) that it
  was offered as evidence for.
- The claim that `htmlparse`'s tree builder lowercases element and attribute
  names, which deviation 2 leans on for Task H's `==` comparisons, is about
  unchanged code in another package. Worth the controller confirming before
  Task H, since deviation 2's whole cost/benefit argument rests on it.

---

## Strengths

- The whitespace design is the right one and it is genuinely single-site.
  I traced every `skip_whitespace()` call: `:445` (leading, correctly not a
  combinator), `:452` (the one interpreting site, whose boolean result is
  read), `:460` (absorbed after an explicit combinator), and `:585, :592,
  :599, :609, :615` — all five inside `_parse_attribute`, where Selectors 4
  §16 *permits* white space between the attribute selector's top-level
  components (WPT `selectors-attr-white-space-001.html` asserts
  `[ data-test-1]`, `[data-test-2 ]`, `[data-test-3 = x]` all match). Neither
  `_parse_compound` (`:472-554`) nor `_parse_pseudo` (`:651-679`) skips
  whitespace at all, which is what makes `: hover`, `:: before`, `. c` and
  `p 5` fail and what keeps `a b` structurally distinct from `ab`. **The
  single-site claim holds.**
- The tests discriminate. `test_whitespace_separated_idents_are_two_compounds`
  and `test_whitespace_around_an_explicit_combinator_is_absorbed`
  (`test_selectors.py:139-172`) compare *structure*, not just combinator
  lists, which is the one comparison a whitespace-stripping parser cannot
  fake. `shape()` (`:127-135`) is the right helper for the `pos`-in-`__eq__`
  problem.
- The injection disclosure is honest and the finding is real: with only
  `[a ~ = "v"]`, list adjacency alone rejects it (a `Whitespace` token sits
  between the delims), so `_adjacent` at `:635` is not exercised; only the
  comment case reaches it. I confirmed by inspection that
  `_parse_attribute_operator` consults `_adjacent` solely in the
  `peek(1) == '='` branch, and `_parse_attribute` does not `skip_whitespace`
  between the name and the operator lookahead — so with whitespace present,
  `peek(1)` is `Whitespace` and the branch is never entered. Reporting a test
  that failed to discriminate, rather than quietly fixing it, is the
  behaviour this process wants.
- Scope exclusions are genuinely deferred, not half-built. I checked each:
  namespaces raise from three sites (`:527-530` compound, `:571-577`
  `_reject_namespace`, `:640-643` inside `[]`), so `ns|div`, `*|div`, `|div`
  and `[ns|a]` all produce a named error rather than a misparse.
  `::part(x)`/`::slotted(x)` raise at `:667-672`. `An+B` is unvalidated and
  the raw token run is kept (`PseudoClassSelector.argument`), consistent with
  the docstring.
- `_split_top_level_commas` (`:363-397`) clamps depth at zero so an unbalanced
  closer cannot make a later comma look nested — a real edge case, handled,
  and commented.
- Error positions are real. I checked `p >> a`: the second `>` is at offset 3,
  `_parse_compound` raises at `start` = 3, matching
  `test_the_error_is_a_valueerror_carrying_a_position`.

---

## Issues

### Critical (Must Fix)

None.

### Important (Should Fix)

1. **`selectors.py:37-49` (deviation 1) documents a deviation as
   conformance.** The docstring asserts the source-adjacency rule follows
   from the spec. It does not — see the ruling above; css-syntax-3 §9 says
   preserved comment information "must have no effect on the parsing step",
   and the comment-insertion table has no `~`/`=` entry. The behaviour is
   right (browser parity) but the stated reason is wrong, and CLAUDE.md
   requires deviations to be documented *as* deviations. Rewrite deviation 1
   to name it a deliberate divergence from the current grammar in favour of
   what Blink and Gecko do, and cite `ConsumeIfNext('=')` /
   `starts_with(b"~=")` as the reason. Reword the same claim in
   `test_selectors.py:8-15` and `:220-232`.

2. **`selectors.py:38-44, 557-561` (deviation 7) cites the wrong grammar and
   is stricter than Selectors 4.** Deviation 7 says `::before::after` is
   rejected "per the `<compound-selector>` grammar in section 4.3". In
   Selectors 4 §16 pseudo-elements are not in `<compound-selector>` at all:
   `<complex-selector-unit> = [ <compound-selector>? <pseudo-compound-selector>* ]!`
   — several `<pseudo-compound-selector>`s *are* grammatical, with the spec's
   own note that "In some circumstances […] it can be followed by more
   `<pseudo-element-selector>`s […] but these are specified on a case-by-case
   basis". Blanket rejection is a reasonable scope limit (this engine has no
   `::slotted()` anyway) but it is a deviation, not the grammar. Fix the
   citation and label it a scope limit. The type/universal-must-lead half of
   deviation 7 *is* correct grammar (`[ <type-selector>? <subclass-selector>* ]!`)
   and needs no change.

3. **`selectors.py:259-282` — `pos` in `__eq__` combined with unhashable
   dataclasses is a real hazard for Task H/J.** `pos` participating in
   equality is documented and the tests work around it with `shape()`, so on
   its own it is Minor. What is not documented is the second half: these are
   plain `@dataclass`es with `eq=True` and no `frozen=True`, so `__hash__` is
   `None`. I confirmed: `hash(sel('a').selectors[0])` and
   `hash(ClassSelector('c'))` both raise `TypeError: unhashable type`. Task H
   is specified to "index rules by rightmost compound" — the obvious
   implementations (a `set` of simples, a `dict` keyed by a `ClassSelector`,
   memoising `matches()` on a compound) are all closed off. Either add
   `eq=True, frozen=True` (which also makes `pos`-in-`__eq__` less
   surprising, since the objects become value-like), or `field(compare=False)`
   on `pos` plus an explicit `__hash__`, or at minimum document the
   restriction so Task H keys by primitive strings instead of discovering
   this mid-task.

### Minor (Nice to Have)

4. **`selectors.py:151` — `:matches()` is handled in code but absent from the
   docstring's deviation 3**, which names only `:not()`, `:is()`, `:where()`.
   It is also an extra beyond the brief: a non-standard legacy alias given
   forgiving parsing and Level-4 specificity the spec never defined for it.
   Either document it in deviation 3 or drop it.

5. **`selectors.py:749` — `:where` short-circuits on name alone.** A
   non-functional `:where` (no parens) parses as a `PseudoClassSelector` and
   gets `(0, 0, 0)`; I confirmed `:where` parses to
   `PseudoClassSelector(name='where', argument=None, selectors=None)`. As an
   unknown/invalid pseudo-class it should carry `(0, 1, 0)` like any other.
   Guard on `selector.selectors is not None` as well as the name. Negligible
   in practice — nothing matches it either way.

6. **`selectors.py:428-436` — `_parse_complex_tokens`'s trailing-token check
   is unreachable**, as the implementer disclosed. `_parse_complex` breaks
   only on end of input, and any leftover token is rejected earlier by the
   `else: raise` at `:465-468`. Keeping it as an invariant guard is
   defensible; it should say so in a comment, since as written it reads like
   live error handling.

7. **`selectors.py:667-672` — `::part(x` reports "unterminated pseudo-class
   argument", not "functional pseudo-element not supported"**, because
   `_consume_function_argument` runs before the `double_colon` check. Moving
   the `double_colon` raise above the argument consumption gives the better
   message.

8. **`:has()` gets `(0, 1, 0)` rather than its spec specificity** (most
   specific argument, like `:is()`). It is in the parse-and-never-match
   group by design and documented as such, but the specificity consequence
   is not called out. One sentence in deviation 3.

9. **Untested strictness.** `#f0f` is a valid id selector (I confirmed it
   parses to `IdSelector('f0f')`) while `#0f0` is rejected — the interesting
   pair, but only the rejection is tested. Add `#f0f` to
   `test_invalid_selectors_raise`'s positive counterpart. (Related, and
   outside this diff: the comment at `tokenizer.py:179` says "`#main` is an
   id selector and `#f0f` is not", which is backwards — `#f0f` is a valid
   ident sequence. The code is right; the comment is wrong.)

---

## What Task H inherits

Confirmed adequate for `matches(element, complex_selector)` and for indexing
by rightmost compound:

- `Complex.compounds[-1]` is the rightmost compound; `Complex.combinators[i]`
  joins `compounds[i]` to `compounds[i+1]`, invariant
  `len(combinators) == len(compounds) - 1`, values `" "`, `">"`, `"+"`, `"~"`
  (`:271-282`). Right-to-left evaluation has everything it needs.
- `Compound.simples` is a list of seven distinct dataclasses, so the matcher
  dispatches by `isinstance` rather than on a string tag (`:186-253`).
- `AttributeSelector` carries `name`, `operator`, `value`, `case` separately
  (`:206-222`), so H can branch on the operator — this is exactly what the
  brief's weak `test_attribute_operators` failed to protect and the added
  test now does.
- `PseudoClassSelector.selectors` is a nested `SelectorList` for
  `:not`/`:is`/`:where`/`:matches`, so H recurses; every other functional
  pseudo-class keeps `argument` as raw tokens for H to ignore or interpret
  later.
- Names: type and attribute names are pre-lowercased, class/id keep source
  case, so H compares with `==` (deviation 2) — subject to the ⚠️ above about
  the tree builder.

The one gap is issue 3: the structures are unhashable, which constrains how H
can build its index.

---

## Assessment

**Spec compliance: ✅ compliant** with the brief and with Selectors 4 for
everything the brief asked for; three documentation defects where deviations
are recorded as conformance (issues 1, 2, 4).

**Task quality: Approved with fixes** — issues 1–3 should land before Task H
starts. Issue 3 is the only one that changes code behaviour Task H depends
on; 1 and 2 are documentation, but in a codebase whose rule is "document every
deviation", a deviation labelled as spec conformance is the failure mode that
rule exists to prevent, and this project has already been bitten by
deviation lists that were wrong in both directions.

**Reasoning:** The parser is well-factored, the whitespace design is correct
and verifiably single-site, the scope exclusions are genuinely deferred with
named errors rather than half-implemented, and the test suite discriminates
where the brief's did not. The one contested behaviour — rejecting
`[a~/**/="v"]` — is wrong against the letter of the current specs but right
against every shipping engine, so it should stay and be relabelled honestly.
