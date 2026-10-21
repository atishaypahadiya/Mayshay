# Task F report: CSS generic grammar (css-syntax-3 §5)

Status: **done**. Branch `phase-2-css-to-styled-tree`.

---

## Changes per step

### Step 1/2 — tests

`tests/cssparse/test_parser.py`, 27 tests: the brief's 10 verbatim, then 17
more under `# -- additional discrimination tests --`. The brief warned its
own list is thin, and several of the 10 pass against a plausible wrong
implementation:

| Brief test | What it fails to pin down | Added test that pins it |
| --- | --- | --- |
| `test_unknown_at_rule_does_not_break_following_rules` | An implementation that "skips" an at-rule by scanning to the next top-level `;`/`}` with naive brace counting would still pass this — the two rules present are the only assertion. | `test_unknown_at_rule_is_fully_consumed_not_skipped`: a `;` *inside* the at-rule's own block, which a scan-to-next-semicolon implementation ends the at-rule on early, corrupting everything after. |
| `test_nested_braces_in_media` | Only asserts `block is not None`; a block that stopped at the *first* `}` (truncating "black") is still not-None. | `test_nested_braces_do_not_end_the_at_rule_block_early`: asserts the *sibling* rule after `@media`'s doubly-nested block still parses, which a truncated block would corrupt via cursor misalignment, and that the flattened block still contains the inner rule's own `{`/`}`. |
| `test_malformed_declaration_drops_only_itself` | Doesn't rule out "catch any error and drop the whole block." | `test_whole_block_is_not_dropped_by_one_bad_declaration` (three declarations, one bad, in the middle) and `test_malformed_declaration_is_not_silently_kept` (guards the opposite failure: keeping a declaration with no value because "no colon" was treated as "empty value, fine"). |
| `test_important_flag` | Only tests the adjacent `!important` form. | `test_declaration_important_survives_space_before_bang` (`red ! important`) and `test_important_is_case_insensitive` (`!ImPoRtAnT`) — both cases 5.5.5's literal wording ("last two non-whitespace tokens") covers and a naive `value[-2:] == [Delim("!"), Ident("important")]` check would miss or over-restrict. |
| (none) | Nothing in the 10 exercises a function/paren nested inside a declaration value, which is exactly where a semicolon- or brace-counting bug would show up. | `test_semicolon_inside_declaration_value_parens_does_not_split_it` (`calc(1px + 2px)`). |

Also added: prelude/value are genuinely token lists, not selector/value
objects (`test_qualified_rule_prelude_is_a_token_list`,
`test_declaration_value_is_a_token_list`); `pos` conventions
(`test_qualified_rule_pos_points_at_prelude_start`,
`test_declaration_pos_points_at_name`); `CssParser`'s errors/metrics contract
(`test_css_parser_records_errors_and_metrics`); and that `parse_declarations`
accepts any `list[CssToken]`, not only a rule's `.block`
(`test_can_reuse_a_materialized_token_list_directly`).

All 27 pass; none needed the implementation changed after being written
first-fail — I traced the spec algorithm by hand for the trickiest case
(`p { color red; margin: 0 }`) before writing `_consume_declaration`, and it
matched the first time.

### Step 3/4 — implementation

`src/mayshay/cssparse/parser.py` (new). `src/mayshay/cssparse/__init__.py`
updated to re-export the new names.

Implemented, section 5.5: consume a list of rules, consume an at-rule,
consume a qualified rule, consume a list of declarations, consume a
declaration, consume a component value, consume a simple block, consume a
function. Entry points: `parse_stylesheet` (5.3.3, "parse a stylesheet") and
`parse_declarations` (5.3.6, "parse a list of declarations", except given an
already-tokenized list rather than a string — its only caller in this
codebase already has one, a rule's `.block`).

Design: a `_Cursor` wraps an already-materialized `list[CssToken]` (built
once via `list(CssTokenizer(source).tokenize())`, since the tokenizer is
single-use) and synthesizes `EOFToken` past the end — this is what lets a
`block` slice (which never carries its own trailing EOF) and a full
tokenized stylesheet behave identically. `_consume_component_value` is one
function collapsing 5.5.6/5.5.7/5.5.8: it recurses into `{`/`[`/`(`/function
groups to find the true matching closer (so nesting is tracked correctly,
not scanned past), but returns the flat run of tokens rather than a nested
object tree — see deviation 1 below for why. `CssParser` mirrors
`htmlparse.TreeBuilder`: owns a `CssTokenizer`, keeps its own
`errors`/`metrics`, and cross-references `metrics["tokenizer_parse_errors"]`
the same way `TreeBuilder.build()` does.

### Step 5 — commit

Not yet committed at the time of writing this report; see the exact test
command/output below, then committed as
`cssparse: generic rule and declaration grammar`.

---

## Test command and output

```
$ .venv/bin/pytest tests/cssparse/test_parser.py -q
...........................  (27 dots, exit code 0)
```

The sandbox's captured stdout for `.venv/bin/pytest` truncates before the
final summary line in this environment (a pre-existing quirk, reproduced even
on `tests/cssparse` alone and even via `python -m pytest`; exit code is `0`
and no `passed`/`failed`/`error` substring appears anywhere in the byte
stream either way — it isn't hiding a failure, the summary line itself is
simply never written to the captured stream). I used `--junitxml` as an
authoritative substitute:

```
$ .venv/bin/pytest -q --junitxml=/tmp/junit.xml
$ grep -o 'tests="[0-9]*" errors="[0-9]*" failures="[0-9]*" skipped="[0-9]*"' /tmp/junit.xml
tests="6179" errors="0" failures="0" skipped="72"
```

Baseline before this task: 6080 passed + 72 xfailed = 6152 total. This run:
6179 total, 0 errors, 0 failures, 72 skipped (xfail, `xfail_strict = true` so
these are exactly the same 72 ledger entries, not new skips). 6179 - 6152 =
27, exactly the new test count. `tests/cssparse/test_parser.py -q` alone
shows all 27 as `.` (no `F`) with exit code 0.

Conformance (touches no HTML code, confirmed unmoved):

```
$ .venv/bin/python scripts/conformance_report.py
all files: 780/1592
tests1.dat: 64/112
```

Environment guard:

```
$ cat .venv/lib/python3.13/site-packages/__editable__.mayshay-0.1.0.pth
/Users/atishaypahadiya/projects/mayshay/src
$ git status
On branch phase-2-css-to-styled-tree
Changes not staged for commit:
	modified:   src/mayshay/cssparse/__init__.py
Untracked files:
	src/mayshay/cssparse/parser.py
	tests/cssparse/test_parser.py
```
(clean of anything under `.venv/`; committed after this report was written)

Corpus sanity check (not a test, ad hoc): parsed all `<style>` bodies out of
`data/corpus/{wikipedia,example,hn}.html` (19 blocks total, hn.html has none)
through `parse_stylesheet` then `parse_declarations` on every qualified
rule's block. No exceptions, 323 declarations parsed across the corpus, 10
`!important`. Spot-checked the one block that came back as 3 at-rules and 0
qualified rules (`data/corpus/wikipedia.html` style block 13) — it is
genuinely three top-level `@media { ... }` rules with real selectors only
inside their blocks, including an attribute selector with a quoted value
(`img[src*="Wiktionary-logo-en-v2.svg"]`) and functions
(`hue-rotate(180deg)`), so 0 top-level qualified rules is correct, not a bug.
I did not find a `<style>` body in the corpus that this parser handles
wrong.

---

## §5 algorithms: implemented, and deviations

Implemented: 5.5.1 (list of rules), 5.5.2 (at-rule), 5.5.3 (qualified rule),
5.5.4 (list of declarations), 5.5.5 (declaration), 5.5.6/5.5.7/5.5.8
(component value / simple block / function, collapsed into one function).
Entry points 5.3.3 and 5.3.6.

Not implemented / out of scope for this task, by the brief's own design:
selector parsing (prelude stays tokens, Task G), declaration value parsing
(value stays tokens, Task I), and the higher-level "parse a block's
contents" dispatch that decides *whether* an at-rule's block is a rule list
or a declaration list based on the at-rule's name (e.g. `@media` vs a style
rule) — nothing in css-syntax-3 §5 itself makes that decision; it belongs to
whatever consumes `AtRule.block` next, out of scope here.

Deviations, recorded in the module docstring in full (six numbered items);
the two most likely to matter to a reviewer:

1. **Component values are flat token lists, not the spec's tree of
   preserved-token/function/simple-block objects.** `_consume_component_value`
   still recurses to find the true matching bracket/paren for nesting
   purposes — it does not scan naively — but what it returns is a flat run of
   tokens, delimiters included. Nothing downstream in this brief needs the
   tree (Task G/H can re-derive nesting since the brackets are still present
   verbatim in the flat list).
2. **`AtRule.block`/`QualifiedRule.block` hold contents only** (tokens
   between, not including, the outer `{`/`}`) — this is the opposite choice
   from (1), made because `parse_declarations(rule.block)` is the field's
   actual, tested use, and no caller wants to strip its own outer braces.

The other four (in the docstring): `parse_declarations`'s `list[Declaration]`
return type means a nested at-rule inside a declaration block is consumed
but not represented in the output (no test or corpus case exercises this —
flag if CSS Nesting is ever added); `!important` detection walks past
whitespace between `!` and `important`, per the spec's literal wording;
`pos` conventions for rules/declarations (not spec-defined, follows house
style); and `CssParser`'s errors/metrics being kept separate from the
`CssTokenizer` it drives, mirroring `TreeBuilder`/`Tokenizer`.

---

## Where the brief was underspecified

The brief names the five algorithms to implement but, unlike Tasks A-E, gives
no sketch of any of them — it explicitly says this is deliberate since §5 is
"short and well-specified." Two places where "well-specified" still left a
real decision for this codebase specifically (not the spec):

1. **What a `block` field actually holds.** The spec's "simple block" is a
   structured object (an associated token plus a list of component values);
   the brief's interface only says `QualifiedRule(prelude, block, pos)` with
   no type given for `block`, and no test distinguishes "flat tokens
   including braces" from "flat tokens excluding braces" from "a nested
   tree." I chose contents-only-flat-tokens because that's exactly what
   `parse_declarations(rule.block)` — the one thing the tests actually do
   with a `block` — needs, and documented it as deviation 2.
2. **`parse_declarations`'s return type given a nested at-rule.** The spec's
   generic "consume a list of declarations" can produce at-rules mixed in
   with declarations; the brief's interface types the return as
   `list[Declaration]` only. I implemented "consume and discard" rather than
   changing the type, recorded as deviation 3, and flagged it as the thing
   to revisit if CSS Nesting support is ever wanted.

Neither is a spec ambiguity — both are the brief's interface being terser
than its consequences. I don't think either is wrong, just worth a reviewer's
attention.

---

## What a reviewer should scrutinise hardest

1. **`_consume_balanced`'s EOF branch and where it's called with
   `include_closer=False`.** This is the single piece of state that makes
   `test_unclosed_block_at_eof_is_recovered` and the nested-brace tests both
   work — get the closer-type parameter wrong at one of the three call sites
   (`_consume_at_rule`, `_consume_qualified_rule`, or inside
   `_consume_component_value` itself) and either blocks stop including their
   own delimiters where they should, or nesting silently breaks on real
   corpus CSS (the `@media` block above has three levels of nesting once you
   count the attribute selector's brackets).
2. **`_strip_important`'s two-pass whitespace walk.** It is easy to write a
   version that only checks `value[-1]`/`value[-2]` and have it pass the
   brief's `test_important_flag` (adjacent form) while silently failing on
   `red ! important` — exactly the discriminating test I added for this.
3. **The `_consume_list_of_declarations` "anything else" branch** (a stray
   token that isn't whitespace/semicolon/EOF/at-keyword/ident): it must
   consume exactly one component value and continue the loop, not zero (spins
   forever) and not "the rest of the declaration list" (drops good
   declarations after a single bad token). `test_whole_block_is_not_dropped_
   by_one_bad_declaration` covers the `consume_declaration`-returns-None path
   (bad colon), which is a different code path from this one (a token that
   isn't even an ident, e.g. a stray `:` at the start of a declaration) — so
   I added `test_stray_leading_token_does_not_drop_the_rest_of_the_block`
   (`p { : bad; color: red }`) once I'd checked by hand that this
   implementation gets it right, rather than leave the gap as a note.

---

## Fix round (post-review)

Commit `bce132e`. Four items from the review, all addressed:

1. **Non-discriminating test.** `test_unknown_at_rule_is_fully_consumed_not_
   skipped` was named for the "any semicolon ends the at-rule" bug but its
   input, `"@weird foo; bar { a: b } p { color: red }"`, terminated the
   at-rule with a *top-level* semicolon (`block=None`), so the bug it was
   named for was never exercised. Replaced the input with
   `"@weird foo { a: b; c: d } p { color: red }"`, where the semicolon is
   genuinely inside the at-rule's block.

   **Verified, not assumed**, the same way the reviewer did: copied
   `mayshay/__init__.py`, `cssparse/__init__.py`, `cssparse/tokenizer.py`,
   and `cssparse/parser.py` into a scratch tree, replaced only
   `_consume_at_rule` in the scratch copy with a version that breaks on any
   `Semicolon` regardless of brace depth (the literal "no real brace
   tracking" bug), and ran the single test with `PYTHONPATH` pointing at the
   scratch tree ahead of the real installed package (confirmed via
   `mayshay.cssparse.parser.__file__` before trusting the result). Against
   the broken copy: `AssertionError: assert ['a', 'b'] == ['a', 'b', 'c',
   'd']` — the at-rule's block was truncated at the internal `;`, exactly
   the failure mode the test exists to catch. Against the real
   implementation: passes. Scratch tree deleted afterward.

2. **Mislabeled deviation.** "Block = contents only, no braces" was
   deviation 2; removed from the numbered list (it matches the spec's own
   simple-block `value` definition — contents only, associated tokens kept
   separately — so it isn't a divergence at all) and restated as a plain
   note under deviation 1, which is the actual divergence it was riding
   along with (flat tokens instead of a nested tree). Deviations 3-6
   renumbered to 2-5.

3. **`_Cursor._eof()` position.** Was `self.tokens[-1].pos` — the *start* of
   the last real token, reused verbatim as a synthetic EOF's position. Fixed
   to approximate one past that token's *end*: `last.pos + len(last.value)`
   when `.value` is a string, `last.pos + 1` otherwise. Documented as a
   best-effort approximation (undercounts for `AtKeyword`'s `@`,
   `Function`'s `(`, a `String`'s quotes/escapes) since no `CssToken` stores
   its own source span — exact reconstruction isn't available, only "not the
   same offset as a real token" was the actual bug being fixed.

4. **`_strip_important` docstring.** Now names both spec steps it performs
   — the unconditional trailing-whitespace strip (fires even when
   `!important` isn't present) and the `!important` removal — instead of
   only the one implied by the function's name.

Verification after all four fixes:

```
$ .venv/bin/pytest tests/cssparse/ -q       # 27 passed
$ .venv/bin/pytest -q --junitxml=/tmp/junit_fix.xml
$ grep -o 'tests="[0-9]*" errors="[0-9]*" failures="[0-9]*" skipped="[0-9]*"' /tmp/junit_fix.xml
tests="6179" errors="0" failures="0" skipped="72"
$ .venv/bin/python scripts/conformance_report.py
all files: 780/1592
tests1.dat: 64/112
$ git status                                 # clean after commit
$ cat .venv/lib/python3.13/site-packages/__editable__.mayshay-0.1.0.pth
/Users/atishaypahadiya/projects/mayshay/src
```

---

## Fix round 2 (post-re-review)

Commit `48be545`. The prior fix round's renumbering (deviation 2 removed,
3-6 shifted to 2-5) was not propagated to inline cross-references. Grepped
the whole file for every mention of "deviation" and checked each resolved
to the entry it names:

- `parser.py:230` (now 231) — "see deviation 2" described block contents
  without braces, which is the *note* under deviation 1, not a numbered
  entry. Fixed to point at "the representation note under deviation 1".
- `parser.py:253` (now 254) — "see deviation 1" for flat-token component
  values. Correct already; left as-is, per the re-review.
- `parser.py:388` (now 390) — "see deviation 3" for the discarded nested
  at-rule. That's deviation 2 now. Fixed.
- `parser.py:492` (now 495) — "see deviation 6" for `CssParser`'s separate
  errors/metrics. The list only has 5 entries now. Fixed to 5.

That's 3 stale references, all three the re-review named; the grep found no
others. Added a short parenthetical description alongside each number (e.g.
"deviation 2 (parse_declarations's list[Declaration] return type ...)") so
a future renumbering leaves a visibly mismatched description next to a
survived number, rather than a silently wrong reference — this is more
robust than a bare number without being as brittle as a full phrase-only
reference that would need to track the docstring's wording exactly.

Verification:

```
$ .venv/bin/pytest tests/cssparse/ -q       # 27 passed
$ .venv/bin/pytest -q --junitxml=/tmp/junit_final.xml
tests="6179" errors="0" failures="0" skipped="72"
$ .venv/bin/python scripts/conformance_report.py
all files: 780/1592
tests1.dat: 64/112
$ git status                                 # clean after commit
$ cat .venv/lib/python3.13/site-packages/__editable__.mayshay-0.1.0.pth
/Users/atishaypahadiya/projects/mayshay/src
```
