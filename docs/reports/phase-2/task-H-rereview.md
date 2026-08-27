# Task H re-review — fix round 1 (a05a103..2b992c6)

## Finding Verdicts

1. **Blocker: vacuous `test_matching_a_real_page_does_not_raise` (`break` limited to `<html>`)** —
   ADDRESSED. Test deleted (`tests/cssparse/test_matching_corpus.py` diff, -12 lines at old
   L368-380). Its coverage now lives in
   `test_the_index_never_drops_a_rule_that_matches_a_real_page`
   (`tests/cssparse/test_matching_corpus.py:110-135`), whose double loop
   (`for element in elements: ... for selector in selectors: matches(...)`, no `break`)
   calls `matches()` on every element x selector pair, strictly more than the deleted
   test's one-element-per-selector sweep. Verified directly, not by re-trusting the
   report: injected `raise RuntimeError("injected")` into the `" "` (descendant)
   combinator branch of `_match_from` in a `PYTHONPATH` shadow
   (`/tmp/mayshay_shadow_review`, `__file__` confirmed resolving there) and reran only
   `test_matching_corpus.py` — `test_the_index_never_drops_a_rule_that_matches_a_real_page`
   failed with the injected error, unrun.

2. **`+-n` parsed to `(-1, 0)`, undisclosed leniency** — ADDRESSED, via the disclosed
   divergence (fixed instead of documented). `matching.py:159-165` now rejects any
   `Delim('+')` followed by a `-`-initial `Ident` before calling `_parse_n_ident`.
   Verified: reverted the guard in a shadow copy
   (`/tmp/mayshay_shadow2`) and reran `test_nth_child_formulas` — exactly one
   row failed, `+-n+2` (`[0,1]` vs expected `[]`); `+-n` alone still passed
   (matches the implementer's own disclosure in the row's comment, `test_matching.py:268-272`).

3. **Deviation 6 wrongly called `2n + 1` spec-invalid** — ADDRESSED for the specific
   claim: `matching.py:86-88` now states `2n + 1` is valid and says an earlier
   draft miscalled it. New prose issue introduced by the fix — see New Breakage.

4. **`_nth` re-parsed An+B per element** — ADDRESSED. `matching.py:127-130` memoizes
   onto `selector._an_b_memo`, checked via `try/except AttributeError`. Confirmed
   `PseudoClassSelector` (`selectors.py:301-333`) is a plain non-slotted, non-frozen
   `@dataclass(eq=False)` with hand-written `__eq__`/`__hash__` keyed only on
   `(name, _argument_key(argument), selectors)` — `_an_b_memo` cannot affect equality,
   hash, or dict-keying. Cache cannot collide across selectors (it's an instance
   attribute, not a shared table) and cannot go stale (pure function of fields that
   are never mutated post-construction). `test_the_an_b_memo_is_per_selector_and_invisible`
   (`test_matching.py:295-309`) pins both the no-leak and the equality/hash-invariance
   properties.

5. **Only `type` pinned from the 46-entry list** — ADDRESSED.
   `test_attribute_value_case_follows_the_html_list` (`test_matching.py:214-244`), 16
   cases, pins `type`/`lang`/`rel` as members and `name`/`href`/`id`/`class` as
   non-members plus both `i`/`s` overrides. `rel` present, `href` absent from
   `_HTML_CASE_INSENSITIVE_ATTRS` (`matching.py:183-191`) — confirmed both by
   inspection and by removing `rel` from a shadow copy's set, which fails exactly
   `test_attribute_value_case_follows_the_html_list[a-[rel="nofollow"]-True]`.

## Deliberate Divergence 1: deletion vs. de-`break`ing — subsumption claim

**Holds.** Read directly: `test_the_index_never_drops_a_rule_that_matches_a_real_page`
iterates every `element` in every page's `elements` against every `selector` in that
page's `selectors`, calling `matches(element, selector)` unconditionally inside the
inner loop with no early exit — a strict superset of what the deleted test exercised
(one element per selector, and specifically the first element in walk order). The
RuntimeError-in-descendant-branch probe (above) confirms the sweep actually reaches
and executes the code path the deleted test was meant to guard, not merely that the
loop shape looks sufficient on paper.

## Deliberate Divergence 2: bug vs. choice for `+-n` — does the distinction hold?

**Holds**, checked empirically against the project's own tokenizer for all five
disclosed/fixed forms:
- `2n+1` → `[Dimension(2,'n'), Number(1)]`, `2n +1` → `[Dimension(2,'n'), Whitespace,
  Number(1)]`, `2n 1` → `[Dimension(2,'n'), Whitespace, Number(1)]`. The latter two are
  token-identical — genuinely unrecoverable post-tokenization, correctly left as the
  one remaining disclosed leniency (`matching.py:77-98`).
- `2n + -1` → `..., Delim('+'), Whitespace, Number(-1)` — the negative `Number` is
  visible post-tokenization; `_parse_b` (`matching.py:654-661`) rejects it via
  `tail[0].value < 0`. Recoverable, correctly fixed not disclosed.
- `+ n` → `Delim('+'), Whitespace, Ident('n')` — the `Whitespace` token is visible;
  `matching.py:156-157` rejects via `not isinstance(rest[0], Ident)`. Recoverable.
- `+-n` → `Delim('+'), Ident('-n')` — the `-`-initial ident is visible;
  `matching.py:160-164` rejects via `ident.startswith("-")`. Recoverable.

All three fixed forms are distinguishable at the token level from their valid
neighbors; the one remaining disclosed leniency is not. The boundary the fix draws is
real, not just asserted.

## An+B Memoization (deviation 14)

Covered under finding 4. No staleness path found: `_an_b_memo` is set once via
`except AttributeError`, computed from `selector.argument`/`selector.name`, which are
dataclass fields nothing in this module or `selectors.py` mutates after construction.
No cross-selector collision: it's a per-instance attribute, not a shared cache keyed
by anything. Matching results unaffected: confirmed via the equality/hash test above,
and `_nth`'s return value is unchanged (same `_parse_an_b` call, just cached).

## Self-Disclosed Non-Discriminating Row

Confirmed accurate by injection: reverting the `+-n` rejection guard, `+-n` alone
still passes (`(-1,0)` → only indices `<=0` → `[]` either way), while `+-n+2` fails
loudly (`[0,1]` vs `[]`). Spot-checked two further new rows (`+ n` → `[]`, guarded by
the `Whitespace`-after-`Delim` check; `2n + -1` → `[]`, guarded by the sign check) —
both fail under a naive revert of their respective guards, so neither shares the
`+-n`-alone defect. No other new row found vacuous.

## Ten Fresh Injections — spot-check

Checked 2 (asked for) plus the reviewer's own probe (3 total, all reproduced):
descendant-branch `RuntimeError` caught by the corpus sweep (see Finding 1); `rel`
removed from the 46-list caught by
`test_attribute_value_case_follows_the_html_list[a-[rel="nofollow"]-True]`; `+-n`
un-fixed caught by `test_nth_child_formulas[+-n+2]`. All matched the report's claims
exactly.

## New Breakage in the Fix Diff

- **Minor** — `matching.py:83-84`: the rewritten deviation 6 prose claims "All three
  reach us as `Dimension(2, 'n')`, `Whitespace`, `Number(1)`" for `2n+1`, `2n +1`, and
  `2n 1`. Tokenizer output shows `2n+1` (no space before `+`) actually produces
  `[Dimension(2,'n'), Number(1)]` — **no `Whitespace` token** — while only `2n +1` and
  `2n 1` produce the three-token form. Confirmed directly:
  `CssTokenizer("2n+1").tokenize()` vs `CssTokenizer("2n +1").tokenize()` differ by
  the `Whitespace` token. Doesn't affect matching correctness (`_parse_b` strips
  whitespace before comparing regardless), but it's a factual inaccuracy in the exact
  paragraph finding 3 asked to be corrected for accuracy — ironic but non-blocking.

## Out-of-Scope Observations

None beyond what the report already self-flags (catch-all gap, `_default_selector_of`
speculation, right-to-left worst case) — all pre-existing and explicitly out of scope
per the task brief.

## Verdict

**Fix round: All five findings ADDRESSED, no new Critical/Important breakage.** One
Minor new issue: `matching.py:83-84`'s rewritten deviation-6 prose overstates token
identity for `2n+1` vs `2n +1`/`2n 1` (missing-`Whitespace`-token case). Both
deliberate divergences (deleting the vacuous test instead of de-`break`ing it; fixing
`+-n` instead of disclosing it) checked out under direct verification, not just
report-reading. Venv untouched (`__editable__.mayshay-0.1.0.pth` still points at
`/Users/atishaypahadiya/projects/mayshay/src`), git status clean, all shadow copies
under `/tmp` deleted after use.
