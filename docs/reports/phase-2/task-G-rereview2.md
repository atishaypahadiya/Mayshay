# Task G re-review 2: pseudo-class argument position-independence fix

## Finding Verdict

**`PseudoClassSelector.argument` embedding `pos`-sensitive `CssToken`s broke deviation 10's equality guarantee.** ADDRESSED.
- `src/mayshay/cssparse/selectors.py:301-333`: `PseudoClassSelector` is `@dataclass(eq=False)` with hand-written `__eq__`/`__hash__` routed through `_key()`/`_argument_key()`.
- `src/mayshay/cssparse/selectors.py:463-492`: `_token_key`/`_argument_key` strip `pos` from every embedded token before comparing.
- Verified live (unmodified `src/`, no shadow needed since no code was mutated): `:nth-child(2n+1)` and `:not(.a)` at offset 0 vs. offset-shifted compare equal and hash equal; `:nth-child(1)` vs `:nth-child(2)` compare unequal **and** hash unequal (previously only unequal, colliding in hash — now cleanly distinct).
- `tests/cssparse/test_selectors.py:226-276` (`POSITION_INDEPENDENT`, 13 sources) and `tests/cssparse/test_selectors_corpus.py:352-374` (whole corpus, 193 rules/279 selectors, parsed twice at offset) both pass (`.venv/bin/pytest tests/cssparse/test_selectors.py tests/cssparse/test_selectors_corpus.py -q` → all green, matches report's 6250/72/0).

## 1. `_token_key`'s generality

Genuinely general for every token type that exists today. All 25 dataclasses in `tokenizer.py:156-315` (report says "fifteen" — stale/wrong count, cosmetic only) have only `str`/`int`/`float`/`bool` fields besides `pos`; none are hashable-unsafe. `Function`, `LParen`/`RParen` (nested-paren tokens) do appear in raw arguments per `_consume_function_argument` (`selectors.py:830-855`, depth-tracked but appended regardless), and `_token_key` handles them with no special-casing, as claimed. Confirmed it fails loudly, not silently: hand-built a token type with a `list` field and ran `_token_key`'s logic — building the key tuple succeeds (lists compare fine for `__eq__`), but `hash()` on the containing tuple raises `TypeError: unhashable type: 'list'` — a crash at dict-insertion time, not a wrong answer. Matches item 9 of the implementer's own scrutiny list.

## 2. Overcorrection check — reproduced

Confirmed `test_a_functional_pseudo_class_still_compares_its_argument` (`test_selectors.py:266-276`) and the injection-M row are real: manually verified `sel(":nth-child(1)") != sel(":nth-child(2)")` is `True` under the actual code (both `==` and `hash()` differ). The fix does not swing into argument-blindness.

## 3. `eq=False` + hand-written `__eq__`/`__hash__`

- Equal ⇒ same hash: `_key()` = `(name, _argument_key, selectors)`, hash uses `(name, _argument_key)` — a strict subset, and `selectors` is deterministic given `(name, argument)` (`_SELECTOR_ARG_PSEUDOS` lookup + forgiving/strict parse is a pure function of both), so no way for two equal objects to hash differently. Consistent.
- `__eq__` returns `NotImplemented` for non-`PseudoClassSelector` (`selectors.py:323-326`), verified live: `p == 5` → `False` via fallback, correctly asymmetric-safe (reflected comparison still works).
- No other file in `src/` or `tests/` compares `PseudoClassSelector` instances or relies on its old generated `__eq__` — it's only re-exported in `__init__.py:29,98`, not yet consumed (Task H doesn't exist yet).

## 4. "Removes a convention" claim

Confirmed accurate. No `Simple` leaf type (`TypeSelector`, `UniversalSelector`, `ClassSelector`, `IdSelector`, `AttributeSelector`, `PseudoElementSelector`) carries a `pos` field at all; only `Compound`/`Complex` do, both `compare=False` (`selectors.py:367,385`). The only place offset could leak into identity was the embedded raw `CssToken`s inside `PseudoClassSelector.argument` — now neutralized. The module is internally consistent: everywhere, identity excludes source offset. No third behavior introduced.

## 5. Deviation 10 text

`selectors.py:126-161`: rewritten to state the token-level nuance precisely (`p:nth-child(2)` at two offsets, unequal-with-equal-hash under a plain dataclass `__eq__`, "precisely the shape that puts two entries in a dict where one belongs"), names the fix (`_token_key`), and records why fixing `tokenizer.py` instead was rejected. The stale caveat ("`:nth-child(1)` and `:nth-child(2)` collide in a dict while still comparing unequal") is gone — retired, not left stale, and it's now false anyway since they no longer collide.

## New Breakage in the Fix Diff

None found.

## Out-of-Scope Observations

- Report's "fifteen token types" (fix-round-2 scrutiny item 9) undercounts; actual count in `tokenizer.py` is 25. Cosmetic, doesn't affect the fix's correctness.

## Verdict

**Fix round: All findings addressed, no new Critical/Important breakage.** `git status` clean, `.venv/lib/python3.13/site-packages/__editable__.mayshay-0.1.0.pth` unchanged (`/Users/atishaypahadiya/projects/mayshay/src`), venv untouched.
