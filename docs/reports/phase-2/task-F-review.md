# Task F Review: CSS generic grammar (css-syntax-3 §5)

## Spec Compliance

✅ Spec compliant, with one Important-severity test-quality gap (below). All
five named algorithms (5.5.1–5.5.5, plus 5.5.6–5.5.8 collapsed) implemented;
entry points 5.3.3/5.3.6 present; error recovery never raises. Verified by
hand-tracing plus injected-bug empirical runs (see Issues).

## Strengths

- `src/mayshay/cssparse/parser.py:386-411` (`_consume_at_rule`) correctly
  implements the spec's asymmetry that a qualified rule returns `None` on
  EOF (`parser.py:429-434`) but an at-rule *always* returns an `AtRule` even
  on EOF (`parser.py:399-402` just records the error and breaks) — a subtle
  spec detail many implementations flatten incorrectly.
- Deviation 2 (`block` holds contents only, no braces) is not actually a
  deviation — it's exactly what the spec's "simple block" `value` field
  already excludes (open token is the block's separate "associated token";
  close token is consumed and discarded, never stored). Functionally
  correct either way; just mislabeled in the docstring as a design choice
  rather than a match. Not a defect.
- `_strip_important` (`parser.py:522-547`) correctly implements *two*
  spec steps merged into one function: the "!important" removal (5.5.5
  step using "last two non-whitespace tokens") and the separate,
  unconditional "strip trailing whitespace from value" step that runs
  regardless of whether `!important` was found. Confirmed by test
  `test_declaration_value_is_a_token_list` expecting no trailing
  whitespace token in `margin: 0 auto `'s value.
- House style match confirmed: dataclasses with `pos`, `CssParser` with
  its own `errors`/`metrics: Counter[str]`, `metrics["tokenizer_parse_errors"]`
  cross-referencing the tokenizer exactly as `TreeBuilder.build()` does,
  numbered deviation list in the docstring. This reads as the same
  codebase as `htmlparse/tokenizer.py` and `cssparse/tokenizer.py`.
- Stray `}` at top level, `;` inside a qualified-rule prelude, a value
  containing a nested block, and at-rule-terminated-by-`;` all traced by
  hand against the diff and confirmed non-raising and spec-consistent.

## Issues

### Important (Should Fix)

- **The claimed discriminator for "naive at-rule skipping" does not
  discriminate it.** I empirically verified this: I built an isolated bug
  (`_consume_at_rule` correctly brace-matches `{`/`}` but wrongly treats a
  `;` seen directly inside the at-rule's own block as ending the at-rule —
  precisely the "scan-to-next-semicolon" bug both the report's table and
  `test_unknown_at_rule_is_fully_consumed_not_skipped`'s docstring
  (`tests/cssparse/test_parser.py:731-736`) name) and ran the full 27-test
  file against it: **all 27 pass, 0 failed.** The test's actual input,
  `"@weird foo; bar { a: b } p { color: red }"` (`test_parser.py:738`), has
  no `;` inside a block at all — `@weird foo;` is legitimately
  semicolon-terminated with no block, so the buggy code path is never
  exercised by this test. No other test in the file covers this scenario
  either. This is a genuine gap: a real "naive at-rule skip" bug of the
  exact kind the report says it guards against would ship undetected.
  Fix: add a case like `@weird foo { a: b; c: d } p { color: red }` and
  assert the trailing `p` rule and its full prelude/content survive.

### Minor (Nice to Have)

- `_Cursor._eof()` (`parser.py:254-255`) synthesizes `EOFToken(pos=tokens[-1].pos)`
  when called on a braces-stripped `block` list (which carries no trailing
  EOF marker per deviation 2) — this points the synthesized EOF at the
  *start* of the last content token, not past its end. Cosmetic only
  (pos is not spec-mandated here and errors still land near the right
  place); worth a one-line comment if it's ever load-bearing for precise
  error columns.
- `_strip_important`'s docstring documents only the "!important" removal;
  the unconditional trailing-whitespace strip it also performs (spec step
  9, confirmed correct — see Strengths) isn't called out, so a future
  reader following the name/docstring alone could miss that this function
  does two spec steps, not one.

## Verified Empirically (bug-injection, not just reading)

Copied `src/` to a scratch dir, shadowed the editable install via
`PYTHONPATH` (never touched `.venv/`), injected each of the three named
wrong implementations one at a time, ran `tests/cssparse/test_parser.py`:

- **Naive at-rule skipping** (semicolon inside the at-rule's own block ends
  it early, braces still correctly nested): **0 failures / 27 passed** —
  does not discriminate (see Important finding above).
- **First-`}` block truncation** (no recursion into nested brace groups):
  caught by `test_nested_braces_do_not_end_the_at_rule_block_early`
  (1 failure, as claimed) — discriminates correctly.
- **Adjacent-only `!important`** (`value[-1]`/`value[-2]` only, no
  whitespace-skipping): caught by 5 tests including both targeted ones,
  `test_declaration_important_survives_space_before_bang` and
  `test_important_is_case_insensitive`, plus even the brief's own
  `test_important_flag` (trailing space before `}` alone breaks the naive
  version) — discriminates correctly, more broadly than claimed.

So 2 of 3 named wrong implementations are genuinely caught; the third
(naive at-rule skipping) is not, despite a test purpose-written and named
for exactly that case.

## Cannot Verify From Diff

- Whether Task G/I actually consume `prelude`/`value`/`block` the way this
  interface assumes (flat token list, brace-inclusive nesting) — those
  tasks don't exist yet in this diff; my judgment that nothing in §5's own
  algorithms needs the tree structure is based on spec reading, not a
  downstream consumer.

## Assessment

**Task quality:** Needs fixes (one Important item: add the missing
at-rule-block-internal-semicolon test before this task is trusted as
"17 tests discriminate 3 known-wrong implementations" — currently 2 of 3).

**Reasoning:** The implementation itself is spec-correct on every path I
traced and empirically stress-tested (including the EOF/at-rule asymmetry
most implementations miss), and matches house style closely. The one real
defect is in the test suite, not the parser: the specific test built to
prove "naive at-rule skipping" is caught passes against that exact bug,
which is the "worst outcome" the task explicitly asked me to guard against.
