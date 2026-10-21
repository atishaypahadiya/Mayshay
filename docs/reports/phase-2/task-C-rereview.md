# Task C fix-round re-review (93f2754..a99c742)

**Minor 1 — adopt ~850 DOCTYPE corpus cases as strict xfail** — ADDRESSED.
`tests/htmlparse/test_html5lib_tokenizer.py:210-331` adds the section,
`STATE_NAMES`/selection independent of it. Independently re-derived (glob over
`TOKENIZER_DIR`, `initial_states == ["Data state"]`, expected output contains a
`DOCTYPE` descriptor) from the live submodule: **855 cases, 12 failures**,
matching the report exactly. `test_doctype_corpus_is_not_empty` hard-asserts
`== 855` (line 314); `DOCTYPE_KNOWN_MISSES` has 12 entries, each `xfail(strict=True)`.

**Minor 2 — `QUIRKS_UNLESS_SYSTEM_ID` comment rationale** — ADDRESSED.
`src/mayshay/htmlparse/treebuilder.py:110-130`. Verified against the actual
spec source (`whatwg/html@main:source`, fetched live): the two clauses read
verbatim "The system identifier is missing or the empty string, and..."
(quirks) / "...is neither missing nor the empty string, and..." (limited-quirks),
and the trailing note — "A system identifier whose value is the empty string
is not considered missing for the purposes of the conditions above" — sits
directly under both `<ul>` lists, so "the conditions above" is both lists, not
just the parse-error clause. The rewritten comment's reading is correct.

**Minor 3 — `Document.mode` as `Literal`, undocumented gates** — ADDRESSED.
`src/mayshay/dom/node.py:16` (`DocumentMode = Literal[...]`), `:55`
(`self.mode: DocumentMode`); `classify_document_mode` return type at
`treebuilder.py:138`, docstring gates at `:146-159`. Spec text confirms both
gates exist verbatim ("if the document is not an iframe srcdoc document, and
the parser cannot change the mode flag is false, and...").

## Count reconciliation (855 vs 850)

Verified sound. Independently re-ran the exact selection rule against the
checked-out submodule: domjs.test=1, test1.test=5, test2.test=15,
test3.test=824, test4.test=10 → 855, with 12 failures all in test3.test — same
numbers, same failure set the implementer reports. All 855 selected cases
genuinely have `initialStates == ["Data state"]` and a `DOCTYPE` descriptor in
their expected output — the denominator is not inflated by out-of-scope cases.
The prior review's 850 remains unexplained on its own terms, but that's not
this diff's problem: what's in scope here checks out against ground truth.

## Selection rule and its hole

Confirmed. `_expects_doctype` (test_html5lib_tokenizer.py:278-281) keys on
`test.output`, not `test.input` — re-ran an input-keyed alternative selection
myself and it produces the identical 855-case set today, so the expected-side
keying isn't currently masking anything, and by construction it can't hide a
"we wrongly fail to emit a DOCTYPE" defect (such a case still has a DOCTYPE
descriptor in `output` and stays selected/failing). The claimed hole is exact:
grepped all Data-state cases with `<!d` in the input and no DOCTYPE in
expected output → exactly 6 (`test1.test` "Truncated doctype start",
`test4.test` × 5 "lookahead region" cases). Ran all six: 5 pass, the 6th
(`test4.test`, "U+0000 in lookahead region") fails on the same NUL deviation —
matches the report's claim precisely, and it is correctly left out of the
ledger (named in the section comment, `test_html5lib_tokenizer.py:230-234`)
since it's a comment-state case, not DOCTYPE.

## The twelve xfails

Confirmed. All 12 are in `test3.test`, all literal `\x00` in a DOCTYPE name or
quoted identifier where the spec wants U+FFFD, all `xfail(strict=True)` keyed
by `(file, description, input)` at `test_html5lib_tokenizer.py:250-263`. Ran
the corpus myself outside pytest — the 12 actual tokenizer-output mismatches
exactly match the 12 ledger keys, no more, no less. `test_doctype_ledger_is_...`
(line 322) asserts key uniqueness and no stale entries; independently confirmed
(855 keys, 855 unique, 0 stale) — a newly-passing case would break both that
assertion's premise and `strict=True`.

## New Breakage in the Fix Diff

None. `dom/node.py` and `treebuilder.py` changes are type annotations and
comment rewrites only — no logic in `classify_document_mode`'s body changed
beyond the type signature. The new test section is additive.

## Out-of-Scope Observations

None noted beyond what's already excluded by the brief.

## Verdict

**Fix round:** All findings addressed, no new Critical/Important breakage.
Venv `.pth` unchanged (single line, `/Users/atishaypahadiya/projects/mayshay/src`);
`git status` clean.
