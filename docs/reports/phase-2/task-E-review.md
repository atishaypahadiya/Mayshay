# Task E review — CSS tokenizer (css-syntax-3 §4)

Diff reviewed: `review-9d821e1..34d671f.diff` (1411 lines, read in full, one pass).
Repo state at review time: `git status` clean, HEAD `64332a5` (a later docs-only
commit by another agent, on top of the reviewed `34d671f`), `.pth` reads
`/Users/atishaypahadiya/projects/mayshay/src`. Nothing under `.venv/` was
modified; the two files I read there (`tinycss2/tokenizer.py`) were read-only.

---

## Spec Compliance

**✅ Spec compliant.**

All six brief steps are present and each is genuinely done, not merely claimed:

- Step 1: `requirements.txt:100` deletion of `tinycss2==1.5.1` is the only
  change to that file. `CLAUDE.md` gains the rule verbatim, placed above the
  BeautifulSoup rule. No `src/` or `tests/` import of the three banned
  libraries — enforced going forward by
  `tests/test_environment.py:23-37`.
- Step 2/3/5: `tests/cssparse/__init__.py` (empty, mirrors
  `tests/htmlparse/__init__.py`), `tests/cssparse/test_tokenizer.py` with 42
  test functions (counted: `grep -c '^def test_'` → 42), the brief's 13 first
  under their own heading.
- Step 4: `src/mayshay/cssparse/tokenizer.py`, 835 lines, plus
  `src/mayshay/cssparse/__init__.py` turned from a placeholder docstring into
  a re-export module.
- Interface: every token class the brief named exists, with `EOF` renamed
  `EOFToken` for the reason given below. `CssTokenizer(source).tokenize()`
  returns an `Iterator[CssToken]`; `.errors` and `.metrics` are public
  attributes set in `__init__` (`tokenizer.py:341-345`).
- Metrics: `css_tokens`, `css_parse_errors`, `tokenize_time_ms` all recorded
  (`tokenizer.py:460-475`, `tokenizer.py:395`).

### The four brief errors the implementer pushed back on

All four corrections are right, and right for the reason given — I checked each
against css-syntax-3, not against the fact that a correction happened.

1. **`\000026 x` → `Ident("&x")`, not `Ident("&")`.** Correct. §4.3.7 consumes
   *one* trailing whitespace as part of the escape; `x` is then still an ident
   code point and §4.3.11's loop has not terminated, so it joins the same
   token. The brief's expectation could only be met by aborting the ident
   sequence at the escape's trailing space, which is wrong for every
   `\<hex> <more-ident>` input. `test_escape_sequences`
   (`test_tokenizer.py:63-72`) carries the corrected value with the reasoning
   inline, and `test_escape_consumes_exactly_one_trailing_whitespace`
   (`test_tokenizer.py:229-234`) pins the two-space case that does give `"&"`
   plus a separate `Ident("x")`. That pair is the right way to preserve the
   rule the brief was reaching for.

2. **The tautology is genuinely gone.**
   `test_style_element_body_round_trips` (`test_tokenizer.py:113-127`) now
   reads `tk = CssTokenizer(src); list(tk.tokenize()); assert tk.errors == []`.
   That asserts something: it drives the generator first (without which
   `.errors` is empty by construction) and compares to `[]` rather than
   truth-testing. It would fail on any implementation that emits a spurious
   parse error for `#f0f`, `a:hover` or the unterminated-looking `0 auto`.

3. **`EOF` sentinel vs `EOFToken` class.** Correct and unavoidable — the
   brief's own `_consume_escape` sketch tests `if ch is EOF`, which requires
   the sentinel. `EOF = None` at `tokenizer.py:91` matches
   `htmlparse/tokenizer.py:58` exactly, and `EOFToken` matches
   `htmlparse/tokenizer.py:124`. No test imports `EOF`; deviation 5 records it.

4. **`_consume_url` is now §4.3.6, including the bad-url recovery.**
   `tokenizer.py:~640-690`. Checked branch by branch against the spec text:
   - leading whitespace skipped before the loop ✓
   - `)` → `Url` ✓; EOF → parse error + `Url` (the spec returns the url-token,
     it does not discard) ✓
   - whitespace → consume the run, then `)` → return url; EOF → parse error +
     return url; **otherwise → `_consume_bad_url_remnants`** ✓
   - `"`, `'`, `(`, non-printable → parse error + bad-url remnants ✓
   - `\` with no valid escape → parse error + bad-url remnants ✓; with a valid
     escape → append the decoded code point ✓
   - anything else → append ✓

   And §4.3.14 itself (`tokenizer.py:~968-982`) is correct on the point that
   matters: it consumes *through* the closing `)` and consumes escapes rather
   than scanning past them, so `\)` inside the junk does not end the bad url
   early. That is what makes `test_url_with_internal_space_is_a_bad_url`'s
   third assertion — that `x` after `url(a b)` still tokenizes — a real
   recovery test rather than a smoke test.

### ⚠️ Cannot verify from this diff

- **The out-of-tree oracle run.** The 29 hand-picked cases and the 19 corpus
  bodies were compared in `/tmp` scripts that are not in the diff and no longer
  exist. The corpus half is now permanently in the suite
  (`test_tokenizer.py:344-371`), so it re-verifies itself; the 29-case
  token-for-token comparison is unreproducible from the repo. Not a defect —
  it is the correct place for a throwaway oracle — but the controller should
  know the claim rests on the implementer's word.
- **`data/corpus/` is gitignored**, so I cannot confirm the "19 bodies, ~21KB,
  zero parse errors" figure. The report's `42 passed` (not `41 passed, 1
  skipped`) is indirect evidence the corpus test actually ran on their
  checkout.
- **`pip uninstall tinycss2` was deliberately not run**, per the environment
  prohibition. The package is still importable in this venv; only
  `requirements.txt` and the new guard test stand between it and a future
  agent. Correct call under the constraint, but it is a loose end for the
  controller: one command finishes it.

---

## 1. The documented tinycss2 divergence (deviation 7) — verdict: ours is right

`tokenizer.py:60-67` claims `*=`, `~=`, `|=`, `^=`, `$=` and `||` are two
delims per the current spec, and that tinycss2 is the one implementing the
withdrawn 2014 CR. **Confirmed on both halves.**

- The spec: fetched §4 and §4.3.6. The enumerated output token list is
  `<ident-token>, <function-token>, <at-keyword-token>, <hash-token>,
  <string-token>, <bad-string-token>, <url-token>, <bad-url-token>,
  <delim-token>, <number-token>, <percentage-token>, <dimension-token>,
  <whitespace-token>, <CDO-token>, <CDC-token>, <colon-token>,
  <semicolon-token>, <comma-token>, <[-token>, <]-token>, <(-token>,
  <)-token>, <{-token>, <}-token>`. `<substring-match-token>`,
  `<include-match-token>`, `<dash-match-token>`, `<prefix-match-token>`,
  `<suffix-match-token>` and `<column-token>` are absent — they were dropped
  when the match operators moved into Selectors' own grammar.
- tinycss2: `.venv/lib/python3.13/site-packages/tinycss2/tokenizer.py:188-196`
  emits `LiteralToken(..., '||')` and, for `c in '~|^$*'` followed by `=`,
  `LiteralToken(..., c + '=')`. That is verbatim 2014-CR behaviour.

So the direction of the divergence is stated correctly: **the implementation is
spec-conformant and tinycss2 is the deviation.** The consequence recorded —
that task G's selector parser must join two delims into `[a*=b]` — is the right
consequence, and it is the load-bearing half of the note.

One imprecision worth fixing, since this docstring is what a future reader will
trust: the note calls this "the one place a spec-correct implementation
*disagrees* with tinycss2". Deviation 4 (int narrowing) is another, and the
docstring itself admits it parenthetically; deviation 2's ident-range shortcut
is a third in principle (tinycss2 happens to agree there). "The only
*structural* divergence observed over the corpus" would be accurate; "the one
place" is not.

I also checked the two neighbouring deviation claims that are easy to get
wrong and found both accurate:

- Deviation 2's example is `a\xa0b` (U+00A0 NO-BREAK SPACE — the diff renders
  it as a space; I read the file bytes to confirm). U+00A0 is **not** in the
  spec's non-ASCII-ident-code-point list, so the current spec really does give
  three tokens there while this implementation gives one. The example is
  correctly chosen — had they written `a·b` (U+00B7) the claim would have been
  wrong, since U+00B7 *is* in the list.
- `_is_ident_start`'s docstring (`tokenizer.py:100-104`) says `isalpha()`
  "would accept 'é' *and* 'µ' but reject '·'". Both halves check out: U+00B5
  MICRO SIGN is alphabetic but is not a spec ident code point, and U+00B7 is a
  spec ident code point but is not alphabetic. This is unusually careful.

---

## 2. The verification reference — tinycss2 from the venv; sound, with a caveat

The report discloses it directly, and the evidence supports the disclosure:

- The oracle was `tinycss2` 1.5.1, still installed in `.venv/`, driven from
  `/tmp` scripts. Deviation 7's text ("the only structural divergence over the
  21KB of real `<style>` bodies in data/corpus/") is only writable by someone
  who actually ran that comparison, and the two divergence classes reported
  (4 × `*=`, 16 × int-vs-float) are exactly the two that follow from
  deviations 7 and 4. The claim is internally consistent with code I verified
  independently.
- **No leak.** `tinycss2` appears nowhere in `src/` or `tests/` as an import.
  The only occurrences are the two docstrings that name it to explain the ban
  and the divergence — and the report's account of the guard test's evolution
  is corroborated by the code: `FORBIDDEN_CSS_IMPORT`
  (`tests/test_environment.py:16-18`) is anchored `^\s*(?:import|from)\s+`
  precisely so those docstrings do not trip it. A substring search would
  indeed have failed; that false positive is real evidence the guard
  discriminates.

**This was the right method.** Verifying a hand-rolled implementation against a
reference implementation is not the same as building on one, and the rule
forbids shipping the library, not consulting it. The divergences it surfaced
were *investigated against the spec* rather than absorbed — which is the test
of whether an oracle is being used well, and this passes it: the implementation
did not chase tinycss2's `*=` behaviour, it documented why tinycss2 is wrong.

Caveat for the controller: the oracle's continued availability is now the only
reason this level of verification was possible, and the brief's Step 1 intent
was to remove it. Whoever runs `pip uninstall tinycss2` closes that door for
tasks F–I. Worth doing deliberately rather than by accident.

---

## 3. Do the 42 tests discriminate? Yes — including the three named cases

Answering the three specifically asked:

- **Would the `url()` tests pass if both forms produced `Function`?** No.
  `test_url_unquoted_is_its_own_token` (`test_tokenizer.py:74-77`) asserts
  `isinstance(got[0], Url)`, which a `Function` fails outright; its partner
  `test_url_quoted_is_a_function_plus_string` (`:80-83`) asserts `Function`
  **and** that `got[1]` is a `String`. The pair can only both pass if `url(`
  branches on the quote. Three further tests attack the branch from other
  angles: `test_url_prefix_matching_is_ascii_case_insensitive` (`:299-302`)
  kills `name == "url"`; `test_url_like_function_name_is_not_a_url` (`:318-321`)
  kills `startswith("url")`; and `test_one_space_before_a_quote_still_takes_the_quoted_path`
  (`:305-316`) pins the exact off-by-one in the "while the next two are
  whitespace" loop across zero, one and two spaces. That last one is the test
  the implementer's own "scrutinise hardest" note asked for, and they wrote it.
- **Would the escape tests pass if `\26` produced the literal characters?** No.
  `test_escape_sequences` asserts `toks(r"\26")[0].value == "&"` — an
  implementation emitting `"\\26"` or `"26"` fails on the first line.
  `test_escape_stops_at_six_hex_digits` (`:237-239`) additionally kills the
  no-digit-cap variant (`\0000263` → `"&3"`, not `ɣ`), and
  `test_out_of_range_and_surrogate_escapes_become_replacement_char` (`:242-245`)
  kills both the `chr()`-raises variant and the `chr(0)` variant.
- **Would the number tests pass if `1e3` parsed as `1`?** No.
  `test_numbers_with_exponents` asserts `toks("1e3")[0].value == 1000`; the
  no-exponent implementation yields `Dimension(1, "e3")` whose `.value` is 1.
  `test_number_type_flag_tracks_integer_vs_number` (`:196-201`) then kills the
  opposite error — deriving `is_integer` from the value, under which `1e3`
  would report `True`. And `test_an_exponent_needs_a_digit_or_it_is_a_unit`
  (`:204-211`) pins `1em`/`1e`/`1e+`, the inputs an over-eager exponent
  scanner breaks.

Beyond the three: `test_positions_point_at_the_first_character_of_the_token`
(`:222-226`) is the only test in the file pinning the `pos` contract that every
dataclass carries, and it checks three distinct offsets rather than one.
`test_metrics_are_populated` (`:329-334`) asserts `css_tokens == len(tokens) - 1`,
which fails an implementation that counts the EOF sentinel — a stricter
assertion than `> 0` and the correct one.

Two weak spots, both Minor: `test_dimensions_and_percentages` (inherited from
the brief) checks `.value`/`.unit` without asserting `isinstance(got[0],
Dimension)`, and `test_style_element_body_round_trips`'s surviving `len(...) >
15` is a threshold nobody will ever tighten.

---

## 4. Spec coverage and the honesty of the deviation list

Every §4.3 algorithm is implemented, and each has a method named and ordered
after its spec number with the number in a section comment — 4.3.1 `_consume_token`,
4.3.2 `_consume_comments`, 4.3.3 `_consume_numeric`, 4.3.4 `_consume_ident_like`,
4.3.5 `_consume_string`, 4.3.6 `_consume_url`, 4.3.7 `_consume_escape`,
4.3.8 `_is_valid_escape`, 4.3.9 `_starts_ident_sequence`, 4.3.10 `_starts_number`,
4.3.11 `_consume_ident_sequence`, 4.3.12/4.3.13 `_consume_number`,
4.3.14 `_consume_bad_url_remnants`, plus §3.3 `_preprocess`. I walked 4.3.1's
dispatch branch by branch against the spec (`#`, `(`/`)`/`[`/`]`/`{`/`}`, `,`,
`:`, `;`, `+`, `-` with its three-way number/CDC/ident ordering, `.`, `<!--`,
`@`, `\`, digit, ident-start, delim fallback) and found no missing or
misordered branch.

Four token types beyond the brief's list — `BadString`, `BadUrl`, `CDO`, `CDC` —
are additions, but not scope creep: §4.3.5 and §4.3.6 *return* the first two,
and a `<bad-string-token>` downgraded to a `String` with partial content is
precisely the failure the type exists to prevent. `Hash.is_id` and the
`is_integer` flag are likewise spec fields, not inventions.

The numbered deviation list is accurate as far as it goes — I checked each of
the eight against the code and found no false entry. One deviation is
**undocumented**, see Important below.

---

## 5. House style — one codebase, not two

A reader moving between `htmlparse/tokenizer.py` and `cssparse/tokenizer.py`
finds the same file. Concretely:

| Convention | htmlparse | cssparse |
| --- | --- | --- |
| Module docstring opens with a numbered deviation list | `:1-43` | `:1-72` |
| `EOF = None` sentinel | `:58` | `:91` |
| `WHITESPACE` module constant | `:57` | `:87` |
| Dataclass tokens, `pos: int = -1` last | `:77-126` | `:180-470` |
| `EOFToken` | `:124` | `:462` |
| `Token = A \| B \| ...` union alias | `:128` | `:472` |
| `metrics: Counter[str]` | ✓ | `:345` |
| `_error(message, pos=None)`, offset points AT the offender | `:210-218` | `:~400` |
| Timing as `round(x * 1000, 3)` | `treebuilder.py:582` | `:469` |

Two intentional differences, both justified in place: `WHITESPACE` is a
`frozenset` here rather than a string (`tokenizer.py:83-89`), because CSS
lookaheads test a possibly-empty `_peek(1)` and `"" in "\n\t "` is `True` —
this is a real trap and the comment explains it; and the set omits `\f`/`\r`
because §3.3 preprocessing has already folded them to `\n`. Timing lives in the
tokenizer rather than the driver because `tokenize()` is a generator
(deviation 6) — htmlparse times in `TreeBuilder.build()`, which drives its
tokenizer eagerly, so the same placement was not available.

Metric key naming diverges: htmlparse uses bare `parse_errors`,
`character_tokens`, `comments`; cssparse prefixes everything with `css_`. The
brief mandated `css_tokens`/`css_parse_errors`, so this is not the
implementer's choice, but note that `metrics.py`'s long-format schema already
carries a `stage` column (`metrics.py:47`), making the prefix redundant and the
two stages inconsistent when pivoted together.

---

## Strengths

- **The `url(` quote lookahead** (`tokenizer.py:~600-625`) implements the
  spec's "while the next *two* are whitespace, consume one" precisely, and the
  accompanying comment explains *why* leaving one whitespace in place is what
  lets the quote test see past it. Most implementations get this wrong; this
  one has a test for all three spacings.
- **`_ascii_lower`** (`tokenizer.py:107-118`) instead of `str.lower()`, with a
  comment naming U+1E9E and U+212A as the reason. Nothing folds to `"url"`
  today; the point is that `url(` is the wrong place to depend on that.
- **`_at()`'s `index < 0` guard** (`tokenizer.py:~370-385`) — unreachable from
  today's four callers and documented as such, because without it a negative
  index silently wraps to the end of the source. Defensive in the one way
  defensive code is worth writing: against a wrong answer rather than a crash.
- **`_reconsume`'s EOF guard** (`tokenizer.py:~390`) is genuinely load-bearing:
  `_next()` does not advance at EOF, so an unconditional `pos -= 1` would
  rewind onto the last real character and loop forever in
  `_consume_ident_sequence`.
- **The report volunteers its own weak points** (the `is_integer`/`value`
  trap, the unreachable `_at` guard, the question of whether `Whitespace`
  should carry text at all) instead of only its successes. The `Whitespace`
  question in particular is the right one to ask — it is the single field in
  the file that exists for us rather than for the spec.
- **The brief's four errors were caught and argued from the spec**, not
  worked around. Two of them (the `url(a b)` sketch, the tautology) would have
  shipped a wrong tokenizer that its own tests approved of.

## Issues

### Critical (Must Fix)

None.

### Important (Should Fix)

**1. `tokenizer.py:~660` — an undocumented deviation, in the file whose
docstring convention exists to prevent exactly that.**

```python
self._error("whitespace inside unquoted url", self.pos)
return self._consume_bad_url_remnants(start)
```

§4.3.6's whitespace branch reads (verbatim from the spec): "Consume as much
whitespace as possible. If the next input code point is U+0029 or EOF, consume
it and return the `<url-token>` (**if EOF was encountered, this is a parse
error**); otherwise, consume the remnants of a bad url, create a
`<bad-url-token>`, and return it." The parse-error designation attaches only to
the EOF sub-case. The `otherwise` path — `url(a b)` — is **not** a parse error
in the spec, yet this line records one and increments `css_parse_errors`.

Compare the sibling branches at `tokenizer.py:~665` and `~670`, which record
errors the spec *does* mandate. Nothing distinguishes them to a reader.

Why it matters beyond pedantry: `css_parse_errors` is a metric this project
intends to *analyse*, and the phase-2 plan now carries a task K on "parse-error
agreement measurement". A counter that fires on a non-error inflates every
error rate computed from real-world CSS, and `url(a b)` is not a rare input.
This is also the kind of thing that is invisible until someone builds a number
on it — the same failure mode as a wrong divergence call.

Fix: either drop the `_error` call, or keep it and add deviation 9 saying
plainly that this implementation records a parse error the spec does not,
with the metrics rationale. Either is defensible; silence is not. If kept,
`test_url_with_internal_space_is_a_bad_url`'s `assert tk.errors` becomes a
test of a house extension rather than of the spec, and should say so.

### Minor (Nice to Have)

**2. `tokenizer.py:60-67` — "the one place a spec-correct implementation
disagrees with tinycss2" overstates it.** Deviation 4 is a second
disagreement, as the same sentence's parenthetical admits. Reword to "the only
*structural* divergence observed across `data/corpus/`". The divergence call
itself is correct (see §1 above); only the superlative is loose.

**3. `tokenizer.py:~900-908` — `css_escapes` is not incremented on the
replacement-character paths.** An escape that resolves to U+FFFD (null,
surrogate, out of range) returns before the counter. `css_escapes` therefore
means "escapes that decoded to something valid", which is not what the name
says. One-line fix; matters only because these counters feed the analysis half.

**4. `test_tokenizer.py:53-59` — `test_dimensions_and_percentages` never
asserts `isinstance(got[0], Dimension)`.** Inherited verbatim from the brief.
It reads `.unit`, so a non-Dimension raises `AttributeError` rather than
failing cleanly, and `got[3].value == -3` alone would pass for `Number(-3)`
followed by a stray `Ident("px")`. Adding the two isinstance checks costs
nothing.

**5. `CssTokenizer` is single-use with no guard.** A second `tokenize()` call
on the same instance finds `pos == len(source)`, yields a bare `EOFToken`, and
silently overwrites `tokenize_time_ms` with a near-zero value. Harmless today —
`toks()` builds a fresh tokenizer per call — but task F will hold a tokenizer
instance, and this is the shape of bug that presents as "the parser sees an
empty stylesheet". Either raise on re-entry or document the contract in the
class docstring, which currently explains laziness but not exhaustion.

**6. `tokenizer.py:460-475` — two `perf_counter()` calls per token for a
metric.** Documented as deviation 6 with a measured ~5% cost, and the reasoning
(a generator's wall time would silently measure the consumer) is sound. Flagging
only so the controller knows the tradeoff was made deliberately and is
reversible: timing the whole of `tokenize()` from the driver, as
`treebuilder.py:574-583` does, becomes correct again the moment there is an
eager driver.

**7. Metric-name prefixing is inconsistent with `htmlparse`** (`css_tokens` vs
`character_tokens`) while `metrics.py`'s schema already carries a `stage`
column. Brief-mandated, so not the implementer's finding to fix, but the
controller should decide before layout and paint inherit the convention.

---

## Assessment

**Spec compliance:** ✅ compliant. All of §4.3 plus §3.3 implemented, correctly
and in spec order; the four brief errors were caught, corrected, and argued
from the spec text rather than from convenience.

**Task quality:** **Approved** (address Important #1 before task F builds on
the error counter).

**Reasoning:** This is the strongest work I have reviewed in this repo. The
tokenizer is spec-faithful branch for branch, the deviation list is honest and
unusually precise (its U+00A0 example would be wrong with almost any other
character the author might have reached for), the 42 tests discriminate against
the specific wrong implementations that would otherwise pass, and the house
style is close enough to `htmlparse/tokenizer.py` that the two read as one
codebase. The tinycss2 divergence call is correct in the direction stated —
verified against both the spec's token list and tinycss2's source. The one
substantive defect is a parse error recorded where the spec designates none,
undocumented; it is small, but it lands directly in a counter the project
plans to analyse.
