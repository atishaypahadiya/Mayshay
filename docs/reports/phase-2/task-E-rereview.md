# Task E fix-round re-review (81bc45f..39f772b)

## Finding Verdicts

1. **Spurious `_error` on `url(a b)` bad-url path** — ADDRESSED. Call removed at
   `src/mayshay/cssparse/tokenizer.py:265-274` (whitespace-branch, "otherwise"
   sub-case); `bad_urls` counting kept. Comment at the call site explains why.

2. **Drop `css_` prefix from metric keys** — ADDRESSED. All eight keys
   unprefixed (`tokenizer.py:82,142,165/169,192,199,222,245/250/258/263,346`).
   `tokenize_time_ms` was already bare. `metrics.py` and `tests/test_metrics.py`
   are key-agnostic (long format, no hardcoded key names) — no other reader
   anywhere expects `css_*`; the only remaining string "css_tokens" in the repo
   is prose inside a test docstring (`tests/cssparse/test_tokenizer.py:361`),
   not a live reference.

3. **Guard against second `tokenize()`** — ADDRESSED. `tokenizer.py:346`
   (`self._tokenized = False`), `:460-480` (`tokenize()` checks the flag,
   raises `RuntimeError`, sets it, returns `self._tokenize()`), `:482`
   (`_tokenize()` is the actual generator). No other in-repo caller of
   `CssTokenizer.tokenize()` exists yet (grep confirms only the test file uses
   it), so the wrapper introduces no regression for existing consumers.

4. **Deviation 7 miscount** — ADDRESSED. `tokenizer.py:61-68` now says "one of
   exactly TWO places," names deviation 4 as the second, distinguishes
   structural vs. representational divergence.

5. **`escapes` not incremented on U+FFFD paths** — ADDRESSED. Counter moved to
   the top of `_consume_escape` (`tokenizer.py:772`), before the EOF/hex/other
   branches, so all three replacement-character exits count.

6. **`test_dimensions_and_percentages` missing `isinstance`** — ADDRESSED.
   `tests/cssparse/test_tokenizer.py:36-45` now asserts `isinstance(..., Dimension)`
   on all three dimensions and `not hasattr(got[1], "unit")` on the percentage.

## §4.3.6 spec reading (independent)

Fetched the current W3C text directly. The whitespace branch reads: "...If the
next input code point is `)` or EOF, consume it and return the url-token (if
EOF was encountered, this is a parse error); otherwise, consume the remnants
of a bad url, create a bad-url-token, and return it." The parenthetical is
grammatically bound to the EOF sub-clause only. By contrast the quote/paren/
non-printable branch and the invalid-escape branch each open with "This is a
parse error" as a freestanding sentence before "Consume the remnants...". The
asymmetry is real in the spec text, not implementer invention. The fix is
spec-correct; the original brief's `_error` call was the bug.

## Replacement tests: do they discriminate?

Yes. `test_url_with_internal_space_is_a_bad_url` asserts `tk.errors == []` and
`bad_urls == 1` — restoring the deleted `_error` call breaks this immediately.
`test_bad_url_from_whitespace_is_not_a_parse_error_but_others_are` asserts
`errors == []` for the whitespace path and `errors` non-empty for three
distinct quote/paren inputs plus one invalid-escape input — it exercises all
four of the algorithm's non-EOF bad-url exits (quote, apostrophe and paren all
land in the same spec branch; invalid-escape is the fourth, distinct branch),
matching the four code points named in the fix report. Neither test would pass
against the pre-fix code.

## New Breakage in the Fix Diff

None Critical/Important. Minor: `tokenizer.py:56` ("`tokenize()` is a
generator...") is now stale prose left over from before this diff's split of
`tokenize()`/`_tokenize()` — `tokenize()` itself is no longer the generator,
`_tokenize()` is. Doesn't affect correctness, just a docstring accuracy nit
adjacent to (not introduced by) this diff's item-3 change.

## Out-of-Scope Observations

None.

## Verdict

**Fix round: All findings addressed, no new Critical/Important breakage.**
Venv untouched: `git status` clean, `.pth` still points at
`/Users/atishaypahadiya/projects/mayshay/src`.
