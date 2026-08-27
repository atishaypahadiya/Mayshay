# Task G report: selectors and specificity

Status: **done**. Branch `phase-2-css-to-styled-tree`.

Files: `src/mayshay/cssparse/selectors.py` (new, 768 lines incl. docstrings),
`tests/cssparse/test_selectors.py` (new, 82 tests),
`src/mayshay/cssparse/__init__.py` (re-exports).

---

## Changes per step

### Step 1/2 — tests, run to fail

`tests/cssparse/test_selectors.py`. The brief's 7 test functions
(10 + 7 = 17 cases) transcribed verbatim, then 65 more under
`# -- additional discrimination tests --`. Run before the module existed:
collection error (`ModuleNotFoundError`), which is the honest "fail" for a
file that creates a module from nothing.

Where the brief's tests do not discriminate:

| Brief test | What it fails to pin down | Added test |
| --- | --- | --- |
| `test_attribute_operators` | Asserts only `selectors[0] is not None`. Passes against a parser that returns `"="` for every operator, i.e. one that loses which operator was written — the exact thing Task H will branch on. | `test_attribute_operator_and_value_are_captured` compares the whole `AttributeSelector`, for quoted and unquoted values. |
| `test_descendant_combinator_from_whitespace` | Asserts the combinator list only. A parser that produced two compounds *and also* mangled the compounds themselves passes. | `test_whitespace_separated_idents_are_two_compounds` asserts `a b` and `ab` differ *structurally*, which is the one comparison a whitespace-stripping parser cannot get right. |
| `test_combinators_parsed` | Uses only spaced combinators, so it cannot see the "whitespace absorbed into `>`" question directly. | `test_whitespace_around_an_explicit_combinator_is_absorbed` asserts `div > p`, `div>p` and `div\n\t>\n\tp` produce identical structure. |
| `test_selector_list_splits_on_top_level_commas_only` | Counts selectors. A splitter that parses only the *first* chunk and counts the rest would pass. | `test_every_selector_in_a_list_is_parsed_not_just_the_first` (`a, >b` must raise). |
| `test_invalid_selector_invalidates_only_its_own_rule` | One input. | 30-case parametrised `test_invalid_selectors_raise`, plus `test_the_error_is_a_valueerror_carrying_a_position`. |

### Step 3 — implement

`parse_selector_list(tokens) -> SelectorList` is recursive descent over
`_Cursor`, a small forward cursor that reports end of input (and `EOFToken`)
as `None`. Structures: `TypeSelector`, `UniversalSelector`, `ClassSelector`,
`IdSelector`, `AttributeSelector`, `PseudoClassSelector`,
`PseudoElementSelector`, unioned as `Simple` (the same idiom `CssToken` uses
in `tokenizer.py`); then `Compound(simples, pos)`,
`Complex(compounds, combinators, pos)`, `SelectorList(selectors)`.
Invariant: `len(combinators) == len(compounds) - 1`.
`specificity(selector)` returns the (a, b, c) triple.

### Step 4 — run to pass

```
$ .venv/bin/pytest tests/cssparse/test_selectors.py
...........................................................................
...........
82 passed in 0.03s

$ .venv/bin/pytest
6189 passed, 72 xfailed in 2.06s

$ .venv/bin/python scripts/conformance_report.py
all files: 780/1592
tests1.dat: 64/112
```

6107 -> 6189 is exactly the 82 new tests; 72 xfailed and 0 failed are
unchanged. Conformance is unmoved, as it must be — no HTML code was touched.
The venv pointer `.venv/lib/python3.13/site-packages/__editable__.mayshay-0.1.0.pth`
is byte-identical before and after (md5 `3717d729cbbfc50ae0f221f1d9b09cdd`,
content `/Users/atishaypahadiya/projects/mayshay/src`).

Extra empirical check, not a test: every qualified rule in the three corpus
pages (`data/corpus/{example,hn,wikipedia}.html`) was fed through
`parse_selector_list` + `specificity` — **156 style rules, 0 rejected**.

### Step 5 — commit

One commit on `phase-2-css-to-styled-tree`. `git status` clean afterwards
(reports under `.superpowers/sdd/` are gitignored).

---

## Whitespace

**Whitespace tokens are never stripped, and they are interpreted at exactly
one place.** `_parse_complex`'s loop, between compounds, does:

```python
had_whitespace = cursor.skip_whitespace()
tok = cursor.peek()
if tok is None:                 break
if delim in ">+~":              consume it, skip whitespace after it, comb = delim
elif had_whitespace:            comb = " "
else:                           raise
```

So an explicit combinator absorbs the whitespace on *both* sides, a
non-combinator token preceded by whitespace is the descendant combinator, and
the same token not preceded by whitespace is a parse error (`p"x"`).

The reason the question never comes up anywhere else is that
`_parse_compound` is maximal-munch: it consumes simple selectors until it
meets a token that cannot continue the compound, and `Whitespace` is such a
token, so a compound never contains whitespace and never has to decide what
to do with it. That is why `a b` and `ab` are distinguishable at all — they
are *different token sequences*, and only a parser that filters `Whitespace`
before parsing (or one that lexes selectors from the source string) loses
that.

Two consequences worth stating:

- Leading/trailing whitespace of a selector, and whitespace either side of a
  top-level comma, are consumed without producing a combinator — the first by
  `_parse_complex`'s opening `skip_whitespace()`, the second because commas
  are removed by `_split_top_level_commas` before each chunk is parsed.
  `test_leading_and_trailing_whitespace_is_not_a_combinator` and
  `test_whitespace_around_commas_is_not_a_combinator` pin both.
- Whitespace is allowed *around* an attribute operator but not *inside* it
  (`[a ~= v]` yes, `[a ~ = v]` no) — see deviation 1 below.

I considered and rejected the alternative of normalizing the token list up
front (collapse runs, drop whitespace adjacent to combinators and commas)
before parsing. It is the same decision made in a place where it is harder to
test: a normalizer bug looks like a selector that silently means something
else, whereas the in-parser version fails loudly at the one site that reads
`had_whitespace`.

---

## Implemented / deliberately not implemented

All of this is in the module docstring's numbered deviation list, matching
`tokenizer.py` and `parser.py`; summarised here.

**Implemented**: type, universal, class, id, attribute (all six operators,
plus the Level 4 `i`/`s` case-sensitivity flag), pseudo-class (functional and
not), pseudo-element (`::x` and the four legacy one-colon spellings);
combinators descendant / `>` / `+` / `~`; top-level comma splitting;
compound ordering rules; `:not()`/`:is()`/`:where()`/`:matches()` argument
parsed as a nested selector list with Level 4 specificity.

**Deviations and scope limits** (numbering as in the docstring):

1. **`~=`, `|=`, `^=`, `$=`, `*=` are joined from two `Delim` tokens** (the
   inherited Task E adjudication — the current css-syntax spec has no
   `<substring-match-token>`; `tokenizer.py` deviation 7). The two delims must
   be adjacent *in the source*, checked by comparing `pos`, not merely
   adjacent in the token list. That distinction is load-bearing: the
   tokenizer drops comments, so `[a~/**/="v"]` has two list-adjacent delims
   whose positions are 5 apart, and CSS treats a comment exactly as
   whitespace, which the old single `<substring-match-token>` could not
   contain. Tokens with `pos == -1` (hand-built, never tokenized) are treated
   as adjacent.
2. **Type and attribute *names* are ASCII-lowercased; class, id and attribute
   *values* are not.** Matches HTML's rules, and `htmlparse`'s tree builder
   already stores both lowercased (verified: `<DIV CLASS=x>` -> `Element div
   {'class': 'x'}`), so Task H can compare with `==`. Cost: foreign-content
   camelCase (`clipPath`), which is case-sensitive per spec — but this engine
   has no foreign content and stores `clippath`, so the two halves agree.
3. **`:not()`, `:is()`, `:where()`, `:matches()` parse their argument as a
   nested selector list**, so their Level 4 §17 specificity (most specific
   argument; zero for `:where()`) falls out. `:is()`/`:where()` take a
   `<forgiving-selector-list>` and drop unparsable arguments; `:not()` does
   not and invalidates. Every other functional pseudo-class keeps the raw
   token run and counts as a plain pseudo-class — **`An+B` is not parsed or
   validated**, so `:nth-child(banana)` parses here (and will never match).
   **`:has()` is deliberately not in the set**: doing it properly needs
   relative selectors (`:has(> p)`), which `_parse_complex` rejects, and a
   matcher that can evaluate them.
4. **Namespaces are not supported** — `ns|div`, `*|div`, `|div`, `[ns|attr]`
   raise with a named error rather than being misparsed (`ns|div` would
   otherwise read as a type selector followed by junk). They need
   `@namespace`, which nothing interprets.
5. **Legacy one-colon pseudo-elements** `:before`, `:after`, `:first-line`,
   `:first-letter` become `PseudoElementSelector`, so they count in `c`, per
   Selectors 4 §3.4. Any other one-colon name is a pseudo-class; unknown
   pseudo-classes parse fine and will simply never match, which is the
   forward-compatible behaviour (`::-webkit-scrollbar` and `:lang(en)` both
   parse).
6. **Functional pseudo-elements (`::part()`, `::slotted()`) raise.** They
   change what the compound applies to and are not representable by
   `PseudoElementSelector`, which carries no argument; "parse and never match"
   would be wrong here.
7. **Compound ordering is enforced**: a type/universal selector may only lead
   its compound, and only pseudo-classes may follow a pseudo-element (so at
   most one pseudo-element per compound). `[a]div`, `.c*`, `::before.c`,
   `::before::after` all raise.
8. **`specificity()` takes a `Simple`, `Compound` or `Complex` and rejects a
   `SelectorList` with `TypeError`** — a list has no single specificity, and
   returning e.g. the max would silently give a rule the specificity of its
   most specific selector regardless of which one matched.
9. `_Cursor` is a new, smaller cursor rather than an import of
   `parser._Cursor` — the same call `parser.py` made about `_ascii_lower`.

Errors: `SelectorParseError(ValueError)` carrying `.pos`. Raised, never
recovered from — an invalid selector invalidates its own rule, and the
caller (Task J) decides that.

---

## Where the brief was underspecified or wrong

Nothing in the brief is **wrong**. The parametrised specificity table is
correct in all ten rows, including `li:nth-child(2) == (0, 1, 1)`
(pseudo-class in `b`, type in `c`).

Underspecified, and the choices I made:

1. **What a `Simple` *is*.** The brief names `Simple` but not its variants.
   Chosen: seven dataclasses unioned as `Simple`, mirroring `CssToken`, so
   Task H's matcher can dispatch by type rather than on a string tag.
2. **What `Compound`/`Complex` carry besides their lists.** Added `pos`
   (first token's position) to both, per the `pos`-on-everything convention
   established in `tokenizer.py` and `parser.py` deviation 4. Note this makes
   `pos` part of dataclass equality, so two selectors written at different
   offsets are unequal even when structurally identical — the tests use a
   `shape()` helper where that matters.
3. **`specificity`'s domain** — Simple/Compound/Complex accepted, SelectorList
   rejected (deviation 8).
4. **Which pseudo-classes get their argument parsed** (deviation 3), and
   whether `:where()`/`:is()` get their Level 4 specificity. The brief is
   silent; matching the spec is strictly more useful to Task H than treating
   them as opaque.
5. **`p >> a` must raise.** Worth recording *why* the brief is right, since a
   reader may remember otherwise: `>>` was proposed as an explicit descendant
   combinator in an early Selectors 4 draft and was **removed** before CR.
   Current Selectors 4 has no `>>` and no `||`-in-selectors outside the column
   combinator (which needs `@column` grammar we do not have). Rejecting both
   matches Level 3 *and* current Level 4.
6. **Whether the parser sees `EOFToken`.** The brief's own `sel()` helper
   passes `list(CssTokenizer(src).tokenize())`, which ends with one; a
   `QualifiedRule.prelude` does not. Both must parse identically —
   `_Cursor.peek` treats `EOFToken` as end of input, and
   `test_a_prelude_without_a_trailing_eof_token_parses_identically` pins it by
   parsing the same selector both ways and comparing.

---

## Discriminating power verified by injection

Method: `cp -R src/mayshay /tmp/g_shadow/mayshay`, run with
`PYTHONPATH=/tmp/g_shadow`. Shadow confirmed active two ways before drawing
any conclusion — `mayshay.cssparse.selectors.__file__` resolves to
`/tmp/g_shadow/mayshay/cssparse/selectors.py`, and as a positive control
`tests/test_environment.py::test_engine_imports_from_this_repo` **fails**
under that env (it asserts the import comes from the repo), proving pytest
itself — not just a bare `python -c` — picked up the shadow. Each bug was
injected into the shadow one at a time from a pristine copy of the real file;
`/tmp/g_shadow` was deleted afterwards. `src/` was never modified.

| Injected bug | Result | First test to fail |
| --- | --- | --- |
| A. Strip all `Whitespace` tokens at the top of `_parse_selector_list` | **caught** | `test_specificity[p a-expected2]` (the brief's own row, because a second type selector in a compound is rejected) — and `test_whitespace_separated_idents_are_two_compounds` |
| B. `had_whitespace` checked *before* the explicit-combinator branch (every whitespace run becomes a descendant combinator) | **caught** | `test_combinators_parsed` (the brief's) |
| C. Match operators collapse to `"="` (`return "="` instead of `first.value + "="`) | **caught only by the added test** — the brief's `test_attribute_operators` passes, and runs first in file order, so this is a direct demonstration of the gap | `test_attribute_operator_and_value_are_captured[~=]` |
| D. Drop the `_adjacent` source-position check on the two delims | **caught** — but only after I added the test: the first version of this suite did *not* catch it, because `[a ~ = v]` is already rejected by list adjacency (a `Whitespace` token sits between the delims). I added the comment case `[a~/**/="v"]`, where the tokenizer has already removed the comment and only `pos` can tell | `test_whitespace_is_allowed_around_an_operator_but_not_inside_it` |
| E. `_consume_function_argument` returns at the first `)` regardless of nesting | **caught** | `test_nested_pseudo_class_arguments` |

D is the one that matters: I asserted the test discriminated, it did not, and
the injection is what showed it. That is the third time on this project.

---

## What a reviewer should scrutinise hardest

1. **The `_adjacent` / `pos`-arithmetic rule (deviation 1).** It is the only
   place a *source position* — not a token — decides whether input is valid,
   and it is the inherited Task E adjudication's consequence. Is
   `[a~/**/="v"]` genuinely invalid? I argue yes (a comment is a token
   separator exactly as whitespace is, and `~=` was one token when the rule
   was written), but it is the judgement call most worth a second opinion.
   The `pos < 0` escape hatch is also a soft spot: a caller that hand-builds
   tokens gets no adjacency checking at all.
2. **Compound ordering enforcement (deviation 7) and `#0f0` rejection.**
   These make selectors *invalid* that a laxer parser would accept, and per
   css-syntax an invalid selector kills its whole rule. If any of them is
   wrong, real stylesheets silently lose rules. The corpus sweep (156/156
   rules parsed) is evidence but three pages is a small corpus.
3. **`:is()`/`:where()` forgiving parsing vs `:not()` strict.** The asymmetry
   is real spec but easy to get backwards, and the failure mode is quiet:
   forgiving `:not()` would make `p:not(!!)` match every `p`.
4. **Specificity of the recursive pseudo-classes.** `max()` over tuples is
   the right comparison for (a, b, c) (lexicographic, as the cascade
   compares them), and the empty-list default is `(0, 0, 0)` — but check
   `:where()` short-circuits *before* the recursion, since
   `:where(#i)`'s argument is non-empty.
5. **`_parse_complex_tokens`'s trailing-token check is currently
   unreachable** — `_parse_complex` only breaks on end of input, so nothing
   is ever left over. It is kept as a guard on that invariant (a future
   `break` in that loop would otherwise silently truncate a selector), but a
   reviewer is entitled to call it dead code.
6. **`Compound.pos`/`Complex.pos` participating in `__eq__`.** Convenient for
   errors, mildly surprising in comparisons; the tests work around it with
   `shape()`. If Task H or J wants structural equality, that is where it
   bites.

---

# Fix round 1/5

All six review items addressed. `.venv/bin/pytest` → **6222 passed, 72
xfailed, 0 failed** (6189 + 18 new selector tests + 15 new corpus tests).
Conformance unmoved at `780/1592`, `64/112`. Venv `.pth` md5 still
`3717d729cbbfc50ae0f221f1d9b09cdd`.

## 1. Deviation 1 relabelled (Important)

Rewritten to say what it is: **browser parity, deliberately against the
letter of the spec.** It now records that Selectors 4 §16 forbids only
"white space" (a comment is not a `<whitespace-token>`), that css-syntax-3
§9 says a preserved comment's location "must have no effect on the parsing
step", and that §9's comment-insertion table has no `~`/`|`/`^`/`$`/`*` row
— so the spec asserts `~=` and `~/**/=` tokenize identically — and then
that Blink (`css_tokenizer.cc`, `case '~': if (ConsumeIfNext('='))`) and
Gecko/Servo (`cssparser/tokenizer.rs`, `starts_with(b"~=")`) both still lex
at the character level and reject it. Ends with "Do not 'fix' this back to
the spec letter without also changing the test that pins it — it is browser
parity on purpose." The behaviour and the test are unchanged; only the label
was wrong.

I accept the correction to my own report: I had written that rejecting
`[a~/**/=v]` was spec-correct, and it is not.

## 2. Deviation 7 cites the right grammar (Important)

Split into its two halves, because only one of them is grammar. Type/universal
must lead its compound — that *is* `<compound-selector>` §4.3, so `[a]div`
and `.c*` are genuinely invalid. The pseudo-element rule is now labelled a
scope limit we chose: §16's `<pseudo-compound-selector>*` allows stacked
pseudo-elements, so `::before::after` and `::before.c` are rejected here and
accepted by the spec, because nothing downstream can represent or paint a
stacked pseudo-element and failing loudly beats parsing one into a shape
Task H would silently ignore.

## 3. Structures are hashable; `pos` is out of `__eq__` (Important)

Every structure now defines `__hash__` in its own class body (verified that
an explicit `__hash__` survives `@dataclass`, which otherwise sets it to
None). `Compound.pos` and `Complex.pos` became `field(default=-1,
compare=False)`.

**`pos` excluded from equality — why.** These objects are *values*, not
stream artifacts. Task H keys rules by their rightmost compound and Task J
compares selectors during the cascade; in both, `div>p` written at offset 0
and the same selector written at offset 40 are the same selector, and having
them compare unequal is a bug waiting to be written. `pos` was only ever for
error messages, and it still is — `sel("   p").selectors[0].pos == 3` is
asserted, so it is excluded from comparison, not dropped. This is a
deliberate departure from `parser.py`, where `pos` *does* participate: a
`QualifiedRule`'s position is part of what a test asserts about it, whereas
nothing will ever want two structurally identical selectors to be distinct.
Documented as deviation 10, appended rather than inserted so no existing
cross-reference renumbers (the failure mode of commit 1ff2448).

Two hazards documented in the same deviation: these are mutable objects
carrying a value hash (`unsafe_hash` territory), so a structure used as a
dict key must not be mutated — the parser builds each once and never touches
it again; and `PseudoClassSelector.__hash__` covers the name only, because
`argument` holds `CssToken`s, which are unhashable dataclasses, so
`:nth-child(1)` and `:nth-child(2)` may collide in a dict while still
comparing unequal. `test_different_selectors_are_not_conflated_by_the_hash`
pins that they do not merge.

Side benefit: the `shape()` helper the tests used to compare selectors
across source positions is gone, and those assertions are now direct
structural equality — strictly stronger than what they replaced.

## 4. Bare `:where` specificity (real bug — confirmed and fixed)

Was `if selector.name == "where": return _ZERO`, which zeroed a bare
`:where` too. Now the argument test comes first: `selectors is not None` is
exactly "was written with an argument list", and only then does the name
matter. `:where` → `(0, 1, 0)`, `:where()` and `:where(a)` → `(0, 0, 0)`.
`:not` and `:is` bare likewise → `(0, 1, 0)`.

## 5. Two documentation items

`:matches()` is now named in deviation 3 as the pre-`:is()` spelling and
alias, including that it inherits `:is()`'s forgiving argument list.
`::part(x` reported "unterminated pseudo-class argument"; the `double_colon`
check now runs *before* the argument is consumed, so both `::part(x)` and
`::part(x` report the unsupported pseudo-element. A genuinely unterminated
pseudo-*class* argument (`:not(a`) still says "unterminated".

## 6. The corpus sweep is now a committed test

`tests/cssparse/test_selectors_corpus.py`, 15 tests. Finds `<style>`
elements with this engine's own `TreeBuilder` rather than a regex, parses
each body with `parse_stylesheet`, and sweeps every prelude.

It reaches **more** than the ad-hoc script did. `parse_stylesheet` does not
descend into `@media`, and the generic grammar exposes no rules-from-tokens
entry point, so the sweep grew a small local `_nested_preludes` that yields
the token run before each top-level `{` inside an at-rule block (skipping
runs that start with an `<at-keyword-token>`, which are nested at-rules, not
selectors). That is the one place the test does its own token walking, and
it is confined to the part the public API cannot reach.

Coverage now: 3 HTML files, 2 carrying `<style>` (hn.html links its CSS and
contributes nothing), 19 `<style>` elements, **193 style rules — 156
top-level and 37 inside `@media` — and 279 selectors, 0 rejected.** Every
level has a floor asserted (`MIN_HTML_FILES`, `MIN_FILES_WITH_STYLE`,
`MIN_STYLE_ELEMENTS`, `MIN_RULES`, `MIN_SELECTORS`), because this project
has twice shipped a corpus loader that silently walked zero cases.

Alongside it, `test_strict_forms_the_corpus_licenses_are_still_rejected`
parametrises the twelve forms we reject on purpose, each tagged with the
deviation it guards — so the divergence and the evidence that it costs
nothing on real pages live in the same file.

## Injection round 2

Same method as before: `cp -R src/mayshay /tmp/g2/mayshay`, run under
`PYTHONPATH=/tmp/g2`, shadow confirmed by `__file__` before each conclusion,
one bug at a time from a pristine copy, `/tmp/g2` deleted afterwards.

| Injected bug | Caught by |
| --- | --- |
| F. Restore the reported `:where` bug (name checked before argument) | `test_bare_where_is_an_unknown_pseudo_class_not_the_functional_one` |
| G. `pos` back inside equality | `test_pos_is_excluded_from_equality_but_still_recorded` + 4 others |
| H. `Compound.__hash__ = None` | `test_every_selector_structure_is_hashable` (all 12 cases) |
| I. Pseudo-element check moved back after the argument is consumed | `test_unterminated_functional_pseudo_element_blames_the_right_thing` (sole failure, clean isolation) |
| J. Drop the match-operator source-adjacency check | `test_whitespace_is_allowed_around_an_operator_but_not_inside_it` **and** the corpus file's strict-form guard for `[a~/**/="v"]` — the divergence now has two independent guards |
| K. Corpus sweep pointed at an empty directory (scratch copy of the test file, not the committed one) | `test_the_corpus_sweep_is_not_silently_empty` + 2 others — the coverage floor works |

## What a reviewer should still scrutinise

Items 1–4 and 6 of the original list stand. Added by this round:

7. **Value hashing on mutable dataclasses.** Nothing mutates a selector
   today. If Task H or J ever rewrites a `Compound.simples` in place — to
   sort or normalize it, say — every dict keyed on it silently breaks. The
   deviation says so; nothing enforces it.
8. **`_nested_preludes` in the corpus test is parser logic living in a
   test.** It is 20 lines and only handles what `parse_stylesheet` cannot
   reach, but it is the kind of thing that drifts from the parser it
   shadows. If the generic grammar ever grows a public rules-from-tokens
   entry point, this should be the first caller deleted.

---

# Fix round 2/5

One item: deviation 10's guarantee was false for functional pseudo-classes
with raw arguments. Confirmed before touching anything — `:nth-child(2n+1)`,
`:lang(en)` and `p:nth-of-type(3)` at two offsets compared unequal with equal
hashes, and put two entries in a dict where one belongs. **`:not(.a)` is
affected too, which the review's list did not include**: its parsed
`selectors` is position-independent, but the raw `argument` it keeps
alongside is not, and that is the field equality reaches.

`.venv/bin/pytest` → **6250 passed, 72 xfailed, 0 failed** (6222 + 28).
Conformance `780/1592`, `64/112`. Venv `.pth` md5 unchanged.

## Which approach, and what I ruled out

**Took option 2: a hand-written `__eq__`/`__hash__` on
`PseudoClassSelector`**, comparing its argument through a new `_token_key`
helper — all of a token's fields except `pos`, built from
`dataclasses.fields` so a token type added to `tokenizer.py` later needs no
edit here. `PseudoClassSelector` became `@dataclass(eq=False)` so the
generated `__eq__` cannot shadow the explicit one.

The framing that decided it: this is not adding a second equality convention
to the module, it is **removing** one. `selectors.py` already declared that a
selector's identity excludes its source offset; the inconsistency was that
one field embedded foreign objects which disagree. Adapting at the single
boundary where a token is embedded in a selector restores one convention
inside the module and leaves the tokenizer's — which is right for a token
stream — alone.

**Ruled out, option 1 (`CssToken.pos` `compare=False` tokenizer-wide).** I
checked the blast radius first, and it is empty *today*: no code in
`src/mayshay/` and no test anywhere compares token objects with `==` — the
tokenizer tests assert `isinstance` plus attributes, and construct no token
instances at all. So it would have worked. I rejected it anyway, for the
reason it would matter tomorrow: a future test written as
`assert toks("a b") == [Ident("a", 0), Ident("b", 2)]` would then pass while
silently checking nothing about the positions it names. That is precisely the
"assertion is not evidence" failure this project has been bitten by three
times, and it would be installed repo-wide to fix a one-field problem in one
module. It also splits the two tokenizers' conventions — `htmlparse` keeps
`pos` in token equality — which the codebase deliberately keeps mirrored.

**Ruled out, option 3 (normalise the argument at parse time).** Storing
pos-stripped token copies would make the plain dataclass `__eq__` correct
with no custom method, but it throws away the argument's source positions
permanently. Those are what a later `An+B` or `:has()` implementation would
report parse errors with, and `_adjacent` needs real positions if an argument
is ever re-parsed (`:not([a~=b])`). It would also make
`PseudoClassSelector.argument` quietly stop being "the raw token run" its
docstring promises.

Bonus from option 2: the argument now participates in the hash, so
`:nth-child(1)` and `:nth-child(2)` no longer collide in a dict. Deviation
10's second caveat is retired rather than reworded.

## Deviation 10 corrected

Rewritten to state the guarantee at the level it has to hold: that
`PseudoClassSelector.argument` holds `CssToken`s whose own equality includes
`pos`, that a plain dataclass `__eq__` therefore makes the same selector at
two offsets unequal-with-equal-hashes — "precisely the shape that puts two
entries in a dict where one belongs" — and that this is why one structure
has a custom `__eq__`. It records why fixing it in `tokenizer.py` was
rejected, so the next reader does not re-litigate it.

## Tests that actually reach the interaction

The gap was real: every pre-existing pos-independence test used type, class
or attribute compounds, which are pos-free by construction. Added:

- `POSITION_INDEPENDENT`, 13 sources parametrising two tests —
  `test_the_same_selector_at_a_different_offset_is_the_same_selector` and
  `test_a_dict_keyed_on_a_compound_does_not_split_by_offset` (asserts
  `len({here: "a", there: "b"}) == 1`). The list deliberately spans bare
  `:where`, empty `:where()`, one-token `:lang(en)`, a five-token
  whitespace-carrying `:nth-child(2n + 1)`, a raw argument in a compound
  with a type selector, both parsed-argument forms, and a compound mixing a
  pseudo-class argument with an attribute selector.
- `test_a_functional_pseudo_class_still_compares_its_argument` — the guard
  against overshooting into argument-blindness, which is the worse
  direction.
- `test_corpus_selectors_are_position_independent` — the whole corpus parsed
  twice from sources offset against each other (a whitespace prefix cannot
  change tokenization but shifts every `pos`), asserting selector equality,
  hash equality and single-dict-entry for all 193 rules / 279 selectors.
  This reaches the **20 functional pseudo-classes the corpus actually
  ships** (`:not(.notheme)` and friends) rather than only the shapes I
  thought to write down — which is the general answer to how this gap
  happened.

## Injection round 3

| Injected bug | Result |
| --- | --- |
| L. The reported bug restored (token `pos` back inside argument identity) | **caught**, 15 failing cases — and *only* in the three tests added this round (`test_the_same_selector_at_a_different_offset_is_the_same_selector` ×7, `test_a_dict_keyed_on_a_compound_does_not_split_by_offset` ×7, `test_corpus_selectors_are_position_independent`). Direct confirmation that every pre-existing test passed against the bug. |
| M. Overshoot — `_argument_key` returns None always, so arguments are ignored in eq/hash | **caught** by `test_a_functional_pseudo_class_still_compares_its_argument` and `test_different_selectors_are_not_conflated_by_the_hash` |

Same protocol: `/tmp/g3` shadow, `__file__` verified, one bug at a time from a
pristine copy, shadow deleted after.

## What a reviewer should still scrutinise

Items 1–4, 6, 7 and 8 stand. Added:

9. **`_token_key` reads every token field generically.** It assumes token
   fields are hashable — true for all fifteen token types today, all of
   which hold `str`/`int`/`float`/`bool`. A token type added later with a
   list or dict field would raise `TypeError` at hash time rather than
   degrade. The corpus test would catch it; nothing else would.
10. **`PseudoClassSelector.__hash__` omits `selectors`** on the grounds that
    it is derived from `argument` and so can never distinguish two
    pseudo-classes whose arguments agree. That holds as long as
    `_parse_selector_list` stays deterministic and `selectors` is never set
    independently of `argument` — worth a glance if either changes.
