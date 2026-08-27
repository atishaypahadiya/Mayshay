# Task F fix round re-review (c24f2b4..208c112)

### Finding Verdicts

1. **Non-discriminating test** — ADDRESSED. `tests/cssparse/test_parser.py:112-125`
   now uses `"@weird foo { a: b; c: d } p { color: red }"` with the `;` inside
   the at-rule's own block, asserting `block_names == ["a","b","c","d"]` and
   `rules[1].prelude[0].value == "p"`. Independently reproduced the injection:
   patched a scratch shadow's `_consume_at_rule` (any-Semicolon-ends-rule, no
   brace tracking) and ran the real test via `PYTHONPATH` with
   `mayshay.cssparse.parser.__file__` confirmed pointing at the shadow —
   failure was `AssertionError: assert ['a', 'b'] == ['a', 'b', 'c', 'd']`,
   matching the report exactly. Against the real implementation (confirmed
   `__file__` resolves to `src/mayshay/...`), it passes.

2. **Deviation 2 mislabeled** — ADDRESSED. `src/mayshay/cssparse/parser.py:38-45`
   restates it as "Note, not a further deviation" nested under item 1, citing
   the spec's simple-block `value` definition (contents only). Deviation list
   correctly renumbered 3-6 → 2-5 in the module docstring.

3. **`_Cursor._eof()` position** — ADDRESSED. `src/mayshay/cssparse/parser.py:157-179`:
   now `last.pos + max(width, 1)` where `width = len(last.value)` for a
   string value, else 1 — one past the last token's end, not its start.
   Docstring is honest about being exact only when `.value` is the full
   source text and undercounting for `AtKeyword`/`Function`/`String`. No test
   asserts EOF-error `pos` values (checked all of
   `tests/cssparse/test_parser.py`), so nothing depended on the old
   start-based convention.

### New Breakage in the Fix Diff

**Important** — the deviation-list renumbering (finding 2's fix) was not
propagated to its own inline cross-references, leaving three stale/dangling
`# see deviation N` pointers:
- `src/mayshay/cssparse/parser.py:230` — `"see deviation 2"` (in
  `_consume_balanced`'s docstring, re: `include_closer=False` for a block's
  own braces). Old deviation 2 (block=contents-only) no longer exists as a
  numbered item — it's now a note under item 1. This pointer is dangling.
- `src/mayshay/cssparse/parser.py:388` — `"see deviation 3"` (in
  `_consume_list_of_declarations`, re: nested at-rule discard). That item is
  now deviation **2**, not 3 — points at `!important` whitespace handling
  instead, the wrong item.
- `src/mayshay/cssparse/parser.py:492` — `"see deviation 6"` (in
  `CssParser`'s docstring, re: separate errors/metrics). Only 5 numbered
  deviations remain — this points past the end of the list.

Confirmed pre-fix these three numbers were correct (`git show
c24f2b4:src/mayshay/cssparse/parser.py` had matching deviation 2/3/6 content
at the old line numbers); the fix diff touched the numbered list but missed
these three call sites. This is exactly the failure mode item 4 (deviation
list accuracy) was scoped to check — the list itself now reads correctly top
to bottom, but three in-code pointers into it are wrong, which is the same
kind of misdirection for a reader following a "see deviation N" breadcrumb.

### Over-fitting check (item 1, extra diligence)

Tested a second, differently-wrong `_consume_at_rule` (correct brace-depth
counting, but forgets to `break` once the block closes — silently consumes
trailing tokens until the next semicolon/EOF). The replacement test still
fails against it (`assert 1 == 2`, at-rule and `p` rule merged into one).
Not over-fitted to the specific "any-semicolon" bug.

### Out-of-Scope Observations

None beyond the above (which is in-scope: it's damage from this diff's own
renumbering edit).

### Verdict

**Fix round:** Findings 1 and 3 fully addressed and independently
reproduced/verified; finding 2 addressed. **One Important issue remains
open**: the renumbering that fixed finding 2 left three inline `# see
deviation N` references stale (parser.py:230, :388, :492) — not new
functional breakage (nothing depends on these comments at runtime), but a
docstring-accuracy regression in the exact file/convention this task's docs
are supposed to protect. Recommend one more small fix pass. Venv/`.pth`
untouched (`/Users/atishaypahadiya/projects/mayshay/src` in the `.pth`), git
status clean throughout.
