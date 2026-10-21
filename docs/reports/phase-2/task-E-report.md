# Task E report: CSS tokenizer (css-syntax-3 §4)

Status: **done**. Branch `phase-2-css-to-styled-tree`, commit `34d671f`.

---

## Changes per step

### Step 1 — remove `tinycss2`, record the rule

- `requirements.txt`: deleted line 100, `tinycss2==1.5.1`. Nothing else changed.
- `grep -rn 'tinycss2\|cssutils\|cssselect' src/ tests/ scripts/` found **no
  imports to clean** — the package was a dependency nobody had used yet, which
  is exactly why it was worth removing before writing any CSS code rather than
  after.
- `CLAUDE.md`: the rule from the brief added under `## Rules`, verbatim, placed
  directly above the BeautifulSoup rule so the three "hand-rolled" clauses read
  as one block.

**The package is still installed in `.venv/`.** I did not `pip uninstall` it:
the task instructions prohibit modifying anything under `.venv/` in absolute
terms, and I treated that as binding over the convenience of a cleaner
interpreter. Consequences to be aware of:

- A fresh environment built from `requirements.txt` will not have it. The
  dependency is genuinely gone from the project's declared surface.
- In *this* checkout's venv, `import tinycss2` still succeeds. The guard
  against that is now a test rather than the absence of the package (below).
- One command finishes the job whenever you want it done:
  `.venv/bin/pip uninstall -y tinycss2`.

To make the rule enforceable rather than aspirational I added a fourteenth
test outside the brief's file, `tests/test_environment.py::
test_no_forbidden_css_libraries_in_the_engine`. It scans `src/mayshay/**/*.py`
for `import tinycss2 | cssutils | cssselect` and asserts none. It is a
statement-level regex, not a substring search: the first version I wrote was a
substring search and it **failed**, because the cssparse docstrings name
tinycss2 to explain why it is banned and where the tokenizer deliberately
disagrees with it. That false positive is the only evidence I have that the
guard discriminates at all, so it is worth recording.

### Step 2 — the tests

`tests/cssparse/__init__.py` (empty, matching `tests/htmlparse/__init__.py`)
and `tests/cssparse/test_tokenizer.py`, **42 tests**: the brief's 13 first,
under a heading, then 29 more.

Why more than 13. The brief's interface list names `AtKeyword`, `Colon`,
`Semicolon`, `Comma`, the three bracket pairs and `EOF`; not one of the 13
tests touches any of them, so eight named types would have shipped with zero
coverage. The extra tests cover those, plus the three areas the task flagged as
where this is harder than it looks — escapes (6 tests), `url()` (8), and error
recovery (3) — plus the metrics contract and a corpus test.

On the "would a plausible wrong implementation pass this?" check:

| Test | Wrong implementation it rejects |
| --- | --- |
| `test_url_unquoted_is_its_own_token` / `..._quoted_is_a_function_plus_string` | One that emits `Function` for both. The pair only passes if `url(` branches on the quote. |
| `test_url_with_internal_space_is_a_bad_url` | The brief's own `_consume_url` sketch — it returns `Url("a b")`. |
| `test_url_prefix_matching_is_ascii_case_insensitive` | One that compares `name == "url"`. |
| `test_url_like_function_name_is_not_a_url` | One that uses `startswith("url")`. |
| `test_escape_sequences`, `..._stops_at_six_hex_digits` | One that emits literal characters (`"\\26"`, `"26"`), and one with no digit cap (`\0000263` → U+263 `ɣ`). |
| `test_out_of_range_and_surrogate_escapes...` | One that lets `chr()` raise, or emits `chr(0)`. |
| `test_number_type_flag_tracks_integer_vs_number` | One that derives the flag from the value: `1e3` is integral but its flag is False. |
| `test_numbers_with_exponents` | One with no exponent handling — `Dimension(1, "e3")`, whose `.value` is 1. |
| `test_backslash_before_newline_is_not_a_valid_escape_outside_strings` | One where "valid escape" means "next char is a backslash". |
| `test_metrics_are_populated` | One that counts EOF (asserts `== len(tokens) - 1`, not `> 0`). |

### Step 3 — verified failing

`ModuleNotFoundError: No module named 'mayshay.cssparse.tokenizer'`, collection
error, as expected.

### Step 4 — the tokenizer

`src/mayshay/cssparse/tokenizer.py`, ~640 lines. House style followed: token
dataclasses each carrying `pos`, methods named and ordered by the spec's own
sub-algorithm numbers, an `errors` list of `(offset, message)` under the same
"the offset points AT the offending character" convention `htmlparse` uses, a
`metrics` Counter, and a module docstring whose numbered deviation list is the
first thing in the file.

`src/mayshay/cssparse/__init__.py` was a placeholder docstring; it is now a
re-export module in the shape of `htmlparse/__init__.py` and `dom/__init__.py`.

### Step 5 / 6 — tests, commit

Below.

---

## Test command and output

```
$ .venv/bin/pytest tests/cssparse/ -q
..........................................                               [100%]
42 passed in 0.30s
```

Full suite:

```
$ .venv/bin/pytest
6076 passed, 72 xfailed in 2.21s
```

Baseline was 6033 passed / 72 xfailed / 0 failed. 6033 + 42 + 1 = 6076. No test
that passed before fails now, and the xfail count is unmoved — nothing in the
htmlparse ledger became an XPASS.

Conformance, before and after, from `scripts/conformance_report.py`:

```
all files: 780/1592
tests1.dat: 64/112
```

Unmoved, as it must be: this task touches no HTML code.

Venv pointer, unchanged:

```
$ cat .venv/lib/python3.13/site-packages/__editable__.mayshay-0.1.0.pth
/Users/atishaypahadiya/projects/mayshay/src
```

`git status` after commit shows one modified file,
`docs/plans/2026-08-26-phase-2-css-to-styled-tree.md`. **That edit is not
mine** — it adds a row K to the phase-2 task table and was already uncommitted
in the working tree when I started (the session's opening snapshot was stale;
it reported branch `phase-1-html-to-dom` and a clean tree, but the checkout was
already on `phase-2-css-to-styled-tree` with that edit in place). I left it
alone rather than sweeping another agent's in-flight work into a commit
labelled "cssparse".

---

## What I implemented from css-syntax-3, and what I did not

**Implemented, all of §4.3 plus §3.3:**

| Spec | Method |
| --- | --- |
| 3.3 preprocessing | `CssTokenizer._preprocess` |
| 4.3.1 consume a token | `_consume_token` |
| 4.3.2 consume comments | `_consume_comments` |
| 4.3.3 consume a numeric token | `_consume_numeric` |
| 4.3.4 consume an ident-like token | `_consume_ident_like` |
| 4.3.5 consume a string token | `_consume_string` |
| 4.3.6 consume a url token | `_consume_url` |
| 4.3.7 consume an escaped code point | `_consume_escape` |
| 4.3.8 are two code points a valid escape | `_is_valid_escape` |
| 4.3.9 would three start an ident sequence | `_starts_ident_sequence` |
| 4.3.10 would three start a number | `_starts_number` |
| 4.3.11 consume an ident sequence | `_consume_ident_sequence` |
| 4.3.12 consume a number | `_consume_number` |
| 4.3.13 convert a string to a number | folded into `_consume_number` |
| 4.3.14 consume the remnants of a bad url | `_consume_bad_url_remnants` |

Every token type in §4 exists, including four the brief's interface list did
not name and which the spec's error handling requires: `BadString`, `BadUrl`,
`CDO`, `CDC`. A `<bad-string-token>` that is silently downgraded to a `String`
with partial content is exactly the bug the token type exists to prevent, so
adding them was not optional.

**Not implemented, deliberately:** nothing in §4.3 is missing. The two things a
reader might expect and not find are `<unicode-range-token>` (removed from
css-syntax-3; `U+0025-00FF` is meant to be reassembled by the *parser* via the
`<urange>` production, and nothing in the nine-property set needs it) and the
match operators — see deviation 7 below.

### Deviations recorded in the module docstring

1. **No `<unicode-range-token>`.** Spec-correct; noted because its absence
   looks like an omission.
2. **Ident code points classified by range (`>= U+0080`), not by the spec's
   exact non-ASCII list.** What css-syntax-3 itself said until 2021 and what
   shipping engines still do. Consequence: `a·b` is one ident here, three
   tokens per the current text.
3. **§4.3.13 delegated to Python's `int`/`float`.** `_consume_number` only ever
   builds strings matching the spec's number grammar, which is a strict subset
   of Python's float-literal grammar — no `inf`, `nan`, `1_0` or `0x`. The one
   place a hand-rolled version would be pure ceremony.
4. **Integer values stored as `int`, non-integers as `float`.** The spec's type
   flag is kept as `is_integer` and stays authoritative; `1e3` has an integral
   value and `is_integer is False`, because the flag records how it was
   *written*, which task I's `<integer>` parsing will need.
5. **The EOF token class is `EOFToken`, not `EOF`.** See "brief errors".
6. **`tokenize_time_ms` measures time inside the tokenizer, not wall time
   across the stream.** `tokenize()` is a generator, so wall time would
   include however long the consumer sat between `next()` calls — i.e. it
   would silently measure the CSS parser. Costs two `perf_counter()` calls per
   token, ~5%.
7. **`*=`, `~=`, `|=`, `^=`, `$=`, `||` are two delims, not one token.** The
   2014 CR had `<substring-match-token>` and friends; the current spec removed
   them. Task G's selector parser must join them.
8. **NULL and lone surrogates → U+FFFD in preprocessing**, unlike `htmlparse`,
   which deliberately passes NUL through (its deviation 5). CSS has no
   conformance corpus pinning the alternative and §4.3's algorithms assume the
   replacement has happened.

Metrics emitted: `css_tokens` (excludes the EOF sentinel), `css_parse_errors`,
`tokenize_time_ms`, plus `css_comments`, `css_functions`, `css_urls`,
`css_escapes`, `css_bad_strings`, `css_bad_urls` for the analysis half.

---

## What was wrong in the brief

**1. `test_escape_sequences` asserts the wrong value, and it is the kind of
wrong that drives a wrong implementation.** The brief has:

```python
assert toks(r"\000026 x")[0].value == "&"
```

The single space after six hex digits terminates the **escape**, not the
**ident sequence**. `x` is still an ident code point, so it joins the same
token: the correct answer is one `Ident` with value `"&x"`. An implementation
built to make the brief's assertion pass would have to stop the ident sequence
at the escape's trailing whitespace, which is wrong for every input of the form
`\<hex> <more-ident>`.

I kept the input and corrected the expectation to `"&x"`, with the reasoning in
the test body, and added `test_escape_consumes_exactly_one_trailing_whitespace`
using `"\\000026  x"` (two spaces) — which *does* give `"&"` followed by a
separate `Ident("x")`, and demonstrates the trailing-space rule the brief was
reaching for. Verified independently, see "verification" below.

**2. `test_style_element_body_round_trips` contains a tautology.**

```python
assert not CssTokenizer(src).errors or True
```

`or True` can never fail; and `errors` is empty at that point regardless,
because the tokenizer is lazy and nothing has driven `tokenize()`. The
assertion was vacuous twice over. Replaced with the check it was plainly
reaching for — drive the tokenizer, then assert `tk.errors == []`. The `len(...)
> 15` assertion is kept as written.

**3. `EOF` cannot be both the sentinel and the token class.** The interface
list names a token dataclass `EOF`; the brief's own `_consume_escape` in the
same document tests `if ch is EOF`, which requires `EOF` to be the
end-of-input sentinel (`None`, as in `htmlparse`). I kept the sentinel — the
brief's code depends on it and it matches house style — and named the token
`EOFToken`, exactly as `htmlparse` names `EOFToken`. No test imports `EOF`.

**4. The `_consume_url` sketch is not the spec algorithm, and accepts input the
spec rejects.** The brief's version is "read until `)`, decoding escapes". It
is missing the whitespace rule, the `"`/`'`/`(`/non-printable rule, and
therefore §4.3.14 and `<bad-url-token>` entirely. Concretely, `url(a b)` would
produce `Url("a b")` — a URL no browser produces, handed to every downstream
consumer as if it were valid. I implemented §4.3.6 as written. It still
satisfies the brief's own test (`url(a/b.png)` → `Url("a/b.png")`), which is
the point: the brief's test could not tell the two apart.

**5. `WHITESPACE` and `HEX_DIGITS` must be sets, not strings** — a latent trap
rather than an error, since the brief never says which. The brief's code does
`self._peek(1) in HEX_DIGITS` and `self._peek(1) in WHITESPACE`, and `_peek(1)`
returns `""` at end of input. `"" in "0123456789abcdef"` is `True` for a
string; `"" in frozenset(...)` is `False`. As strings these would make every
escape at EOF consume a phantom digit and a phantom space. They are frozensets
here, with a comment saying why. `htmlparse` uses a plain string for its
`WHITESPACE`, which is safe there only because it is never tested against a
possibly-empty `_peek`.

---

## Verification beyond the test suite

Two checks I ran from `/tmp` (never from `src/` or `tests/`), using the
still-installed `tinycss2` as an oracle before it leaves the venv. Disclosed
because it is the same library the task bans: it was used to *check* the
hand-rolled tokenizer, never to build it, and nothing in the repo imports it.

1. **29 hand-picked cases**, including every input in the brief's 13 tests:
   token-for-token agreement on all of them, modulo tinycss2 returning nested
   component values where we return a flat stream.
2. **Every `<style>` body in `data/corpus/`** — 19 bodies, ~21KB of real
   Wikipedia and example CSS, flattened and compared element by element.
   **All 19 tokenize with zero parse errors.** Exactly two classes of
   divergence, over ~4,900 tokens:
   - 4 × `*=` — tinycss2 emits the withdrawn 2014-CR
     `<substring-match-token>`; we emit two delims, per the current spec.
     Deviation 7.
   - 16 × `1.0` vs `1` — deviation 4, int narrowing.

   Both are documented and intended. **No corpus input is mishandled**; there
   is nothing to report under the "say so rather than adjusting a test"
   instruction.

`tests/cssparse/test_tokenizer.py::
test_real_style_bodies_from_the_corpus_tokenize_without_error` keeps the corpus
half of that check in the suite permanently. It walks the DOM for `<style>`
elements via the project's own HTML parser, so it also exercises the
htmlparse → cssparse seam that task F will need. Note `data/corpus/` is
gitignored: the test skips cleanly on a checkout without it, which is the same
`requires_corpus` shape the htmlparse tests use.

---

## What a reviewer should scrutinise hardest

1. **`_consume_ident_like`'s quote lookahead.** The whole `url(` distinction
   turns on four lines:
   ```python
   while len(self._peek(2)) == 2 and set(self._peek(2)) <= WHITESPACE:
       self._next()
   first, second = self._at(0), self._at(1)
   if first in ('"', "'") or (first is not EOF and first in WHITESPACE
                              and second in ('"', "'")):
   ```
   The spec's "*while the next two are whitespace, consume one*" leaves at most
   one whitespace character in place, which is precisely what lets the quote
   test see past it. Off by one in either direction and `url( "a.png")` goes
   down the unquoted path. Covered by `test_url_quoted_is_a_function_plus_string`
   and `test_url_with_whitespace_around_unquoted_body`, but only for the
   zero-and-two-space cases — `url( "a.png")` with exactly one space is the
   input to reason about.

2. **Negative offsets into `_at`.** Four sites call the spec predicates with
   `offset=-1` to ask about the character `_next()` just returned, instead of
   rewinding first. `_at` now returns EOF for `index < 0`; without that guard a
   negative index would wrap to the *end* of the source. The guard is
   unreachable today (`pos >= 1` at all four sites) — which means no test
   covers it, and it is there against a future fifth caller.

3. **`_reconsume`'s EOF guard.** `_next()` does not advance at end of input, so
   `self.pos -= 1` unconditionally would rewind onto the last real character
   and re-tokenize it — an infinite loop in `_consume_ident_sequence`. The
   guard is one line and load-bearing.

4. **`is_integer` vs `value`.** `Number(1000.0, is_integer=False)` for `1e3` is
   correct and looks wrong. Anything downstream that wants "is this an
   `<integer>`" must read the flag, not `isinstance(value, int)` — and note
   deviation 4 makes `isinstance` *usually* agree, which is what will make the
   eventual bug hard to find.

5. **The exponent lookahead in `_consume_number`.** `1em` must stay
   `Dimension(1, "em")`, `1e3` must become `Number(1000)`, and `1e+` must stay
   `Dimension(1, "e")` followed by a delim. The three-character check
   (`e`, optional sign, *required* digit) is what separates them; all three,
   plus bare `1e`, are pinned by
   `test_an_exponent_needs_a_digit_or_it_is_a_unit`.

6. **Whether `Whitespace` should carry its text at all.** The spec's token
   carries nothing. I kept the run so the stream can be serialized back to
   source, which the metrics half of the project wants — but it is the one
   token field here that exists for our convenience rather than for the spec,
   and if task F never uses it, it should go.

---

# Fix round 1 of 5

Six items from review, all in `src/mayshay/cssparse/tokenizer.py` and its test
file. Commit `f3e3d9e`.

## 1. The spurious parse error on the bad-url path — dropped

**Conclusion: the spec does not designate a parse error there, so the `_error`
call is gone.** §4.3.6's whitespace branch reads:

> Consume as much whitespace as possible. If the next input code point is
> U+0029 RIGHT PARENTHESIS ()) or EOF, consume it and return the `<url-token>`
> (**if EOF was encountered, this is a parse error**); otherwise, consume the
> remnants of a bad url, create a `<bad-url-token>`, and return it.

The parenthetical attaches to the EOF sub-case and to nothing else. The
asymmetry is deliberate and visible when the four bad-url exits are read
together: the quote / paren / non-printable branch and the invalid-escape
branch each say "this is a parse error" in so many words, and the whitespace
branch conspicuously does not. `url(a b)` is malformed and yields a
`<bad-url-token>`; the spec simply does not count it as a parse error.

So this was a plain bug, not an undocumented deviation, and it is fixed rather
than documented — there is no deviation 9. The signal is not lost: the
malformed url is still counted as `bad_urls`. The reasoning is in a comment at
the call site so nobody "fixes" it back.

Task K's baseline was the thing at risk. Over `data/corpus/` the effect is
nil — all 19 `<style>` bodies produce zero parse errors either way — but the
whole point of that measurement is the corpus where it isn't nil.

Two tests pin it, and the second is the one that matters:
`test_url_with_internal_space_is_a_bad_url` now asserts `tk.errors == []`
(it previously asserted `tk.errors`, i.e. it was pinning the bug), and
`test_bad_url_from_whitespace_is_not_a_parse_error_but_others_are` walks all
four exits and asserts the asymmetry directly — quiet for whitespace, loud for
`'`, `"`, `(` and an invalid escape.

## 2. `css_` prefix dropped from every metric key

`tokens`, `parse_errors`, `comments`, `functions`, `urls`, `escapes`,
`bad_strings`, `bad_urls`. `tokenize_time_ms` was already unprefixed.
`parse_errors` now matches htmlparse's key exactly, which is the right
outcome: the same measurement under the same name, separated by the `stage`
column that exists for that purpose.

`test_metric_keys_are_unprefixed_like_htmlparse` asserts no key starts with
`css_` and that five of them are actually non-zero on a stylesheet that
exercises each — so the guard cannot pass by emitting nothing.

## 3. Second `tokenize()` now raises

`tokenize()` is no longer a generator function. It checks a `_tokenized` flag,
raises `RuntimeError`, and returns `self._tokenize()`, which is the generator.
The split is the point: a generator's body does not run until it is first
advanced, so keeping the guard inside would have raised at iteration rather
than at the offending call. `test_tokenize_is_single_use` asserts both the
raise and that it happens at call time.

## 4. Deviation 7's count corrected

"the one place a spec-correct implementation disagrees with tinycss2" → one of
exactly **two**, this being the only *structural* one, the other being
deviation 4's int-vs-float, which is a representation difference at identical
token boundaries.

## 5. `escapes` now counts the U+FFFD paths

Moved to the top of `_consume_escape`, so out-of-range, surrogate and NUL
escapes count. The counter answers "how many escapes were written", which is a
property of the input; an escape that resolves to U+FFFD was still written.

`test_escapes_are_counted_even_when_they_yield_the_replacement_char` covers all
three, and turned out to demonstrate the brief's trailing-space bug a second
time: `\110000 \D800 \0 ` is **one** ident of three replacement characters,
because U+FFFD is an ident code point under deviation 2 and each escape eats
its own trailing space. The two-spaced form gives three idents. Both are
asserted.

While there I marked `_consume_escape`'s EOF branch unreachable — all four call
sites check `_is_valid_escape` first, so a backslash at EOF yields a Delim and
never reaches it. Kept, because §4.3.7 has the branch.

## 6. `test_dimensions_and_percentages` now asserts types

The brief's version checked only `.value` and `.unit`, which any token type
carrying those two attributes would satisfy. Now asserts `isinstance(...,
Dimension)` on all three dimensions, `-3px` as `(-3, "px")` rather than just
`-3`, and `not hasattr(got[1], "unit")` on the percentage — so `50%` coming
back as `Dimension(50, "%")` fails, which was the plausible wrong
implementation the test was blind to.

## Verification

```
$ .venv/bin/pytest tests/cssparse
46 passed

$ .venv/bin/pytest
6080 passed, 72 xfailed in 2.18s
```

Was 6076 before this round; +4 net new tests, no test lost. Conformance
unmoved at `780/1592` and `64/112`. Venv `.pth` still
`/Users/atishaypahadiya/projects/mayshay/src`. `git status` clean after commit
— and note `docs/plans/...` is no longer showing as modified, so the plan edit
that was not mine has since been committed elsewhere.

**Left alone as instructed:** the two `perf_counter()` calls per token.
