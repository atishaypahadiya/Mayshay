# Task B review — parse-error honesty in the tree builder

Base `42a50f7` → head `9d71ebb`. Read-only review; working tree untouched
(`git status --porcelain` empty), `.venv/.../__editable__.mayshay-0.1.0.pth`
still reads `/Users/atishaypahadiya/projects/mayshay/src`. Nothing under
`.venv/` was written.

## Spec Compliance

✅ **Spec compliant with two defects** (both under-reporting, both invisible to
the suite). Every interface the brief specified exists and behaves as specified:
`TreeBuilder.errors` (treebuilder.py:163), `_error` (treebuilder.py:192-194),
`metrics["parse_errors"]` incremented per error, `metrics["tokenizer_parse_errors"]`
written at treebuilder.py:409, `TREE_ERROR_CODES` at treebuilder.py:148-166
(11 entries). All eight brief-listed recording sites are present. The eight
brief-verbatim unit tests are present unmodified; the corpus test's assertion
body is unmodified and still compares code multisets only, never positions.

Deviations from the brief, all disclosed in the report:
- `expected-doctype-but-got-comment` → `expected-doctype-but-got-end-tag` (correct, see below)
- `EOF_OK_OPEN` replaces the brief's `("html","body")` exclusion (correct, see below)
- Eight extra recording sites the brief did not list (all spec text; seven correct, one wrong — see Important #2)
- `src/mayshay/htmlparse/tokenizer.py` touched (in scope by necessity, see below)
- Four `strict=True` xfails added to the corpus test (justified; one reason is wrong)

### The three disclosed items, re-derived

**1. `EOF_OK_OPEN` — correct, and the brief was wrong.** WHATWG HTML, "in body"
insertion mode, end-of-file token, step 1: "If there is a node in the stack of
open elements that is not either a dd element, a dt element, an li element, an
optgroup element, an option element, a p element, an rb element, an rp element,
an rt element, an rtc element, a tbody element, a td element, a tfoot element,
a th element, a thead element, a tr element, the body element, or the html
element, then this is a parse error." That is exactly eighteen names, and
treebuilder.py:99-108 carries exactly those eighteen — not one short, not one
long. The brief's two-name version does over-report: `<p>One<p>Two` leaves `p`
open, which the spec explicitly permits. Correction accepted.

Residual risk I could not close: html5lib's own `InBodyPhase.processEOF` allowed
set is (from memory) shorter than the spec's, omitting `optgroup option rb rp rt
rtc`. If so, `<!doctype html><option>` — which we now report as clean (verified:
0 errors) — would carry `expected-closing-tag-but-got-eof` in `#errors`. html5lib
is not installed in this venv so I could not read the source, and I swept every
`tree-construction/*.dat` file for a case whose only non-`html`/`body` open
element at EOF is one of those six: none exists. The list is right against the
spec, which is what the global constraints bind us to, and no corpus case
contradicts it. Worth a comment noting the divergence if it is later confirmed.

**2. The code substitution — correct, and the original really is unreachable.**
`_mode_initial` (treebuilder.py:420-448) dispatches `DoctypeToken` first,
`CommentToken` second, whitespace `CharacterToken` third; the `else` therefore
receives only `StartTagToken`, non-whitespace `CharacterToken`, `EOFToken` and
`EndTagToken`, and the first three have their own branches. A `CommentToken`
cannot reach the final `else` — unreachable, not merely untested, so the fix is
substitution rather than a new test. `expected-doctype-but-got-end-tag` is the
right substitute: `tests1.dat:109` opens with `'(1,9): expected-doctype-but-got-end-tag'`
for input beginning `</strong>`, which is precisely this situation, and the code
appears 7 times in the corpus against 0 for `...-but-got-comment`. Set size held
at 11. Not a broadening.

**3. The DOCTYPE early return — spec-correct, and it is a real behaviour change,
not a theoretical one.** All five modes say the same thing in the spec: "A
DOCTYPE token: Parse error. Ignore the token." — "before html", "before head",
"in head", "after head", "after body". The guards at treebuilder.py:451, 466,
481, 512 and 707 implement exactly that.

Re-derived rather than taken on trust. Old behaviour for a stray DOCTYPE in
`before_html`: fall to `else` → insert `html` → `before_head` → redispatch →
insert `head` → `in_head` → redispatch → pop head → `after_head` → redispatch →
insert `body` → `in_body`, where a `DoctypeToken` matches no branch and is
dropped. New behaviour: recorded and ignored where it stands; the *next* token
walks that same chain, and if no token follows, the EOF token walks it. Final
tree identical in both cases — which is why conformance is unmoved.

The one case where the trees genuinely differ is `in_head`, and there the change
is an improvement: `<!DOCTYPE html><head><!DOCTYPE html><title>x</title>`
previously had the stray DOCTYPE close `<head>` via the anything-else rule, so
`<title>` landed in `<body>`; it now stays in `<head>`. That is the spec
behaviour. Conformance neutrality here is a statement about corpus coverage, not
about the change being inert — the report slightly overstates it by calling the
whole thing conformance-neutral. Net: keep the change.

### The tokenizer edit — in scope, correct, disclosed

`tokenizer.py:311` (`EOFToken(pos=self.pos)`) and `tokenizer.py:912`
(`DoctypeToken(..., pos=start)`, `start = self.pos - 9`). The brief's file list
does not mention the tokenizer, but the brief's own
`test_error_positions_are_within_the_source` asserts `0 <= pos <= len(source)`,
and both fields defaulted to `-1` with nothing populating them, so every EOF and
DOCTYPE error would have been filed at `-1`. The edit is required by the brief's
tests, not incidental to them.

Correctness checked: `_state_markup_declaration_open` (tokenizer.py:822-830) is
entered with `self.pos` two past `<` and does `self.pos += 7`, so on entry to
`_state_doctype` the token's `<` is nine back — `self.pos - 9` is right.
`_state_doctype` runs its `while True` to completion and always emits, so `start`
is computed exactly once per DOCTYPE. Verified empirically: `<!DOCTYPE html>x`
→ `DoctypeToken(pos=0)`, `EOFToken(pos=16)` for a 16-char source; `abc` →
`EOFToken(pos=3)`. `grep -rn 'DoctypeToken(\|EOFToken(' src/ tests/ scripts/`
finds no other construction site, so no test compares these tokens for equality
and nothing downstream shifted. Disclosed in the report's file list and in item 6
of "What a reviewer should scrutinise hardest". In scope, correct, disclosed.

### The two corpus buckets — attribution verified, counts exact

I re-derived both buckets independently over `tests1.dat` and then over the whole
corpus. The report's numbers are exact:

- Bucket 1 (we emit, corpus does not expect) = {26, 37, 98, 106} — 4 cases.
  Extras: `end-tag-too-early` ×2 (26, 98), `expected-doctype-but-got-eof` ×1 (37),
  `expected-closing-tag-but-got-eof` ×1 and `unexpected-end-tag` ×1 (both 106).
- Bucket 2 (corpus expects, we never emit) = {26, 37, 98} — 3 cases.
  Missing: `unexpected-end-tag` ×2 (26, 98), `expected-closing-tag-but-got-eof`
  ×1 and `expected-doctype-but-got-chars` ×1 (both 37).
- Overlap 3, so 4 ∪ 3 = 4 failing cases. Consistent, and the two categories are
  kept apart as the brief required.

Root-cause attribution for 26, 98 and 106 is correct. `_mode_in_head` has no
"any other end tag" rule; the spec does have one ("An end tag whose tag name is
one of: body, html, br → act as described in the anything else entry" / "Any
other end tag: Parse error. Ignore the token."), and the corpus expected trees
for both cases put `<title>` in `<head>`, confirming the token must be ignored
rather than fallen through. 106 is the unimplemented table modes. See Important
#3 for case 37.

## Strengths

- The `EOF_OK_OPEN` correction is the right call made for the right reason, and
  the constant carries a comment that explains the failure the brief's version
  produced rather than just asserting the list.
- `close_p_element(pos)` moving the parse error *into* the algorithm
  (treebuilder.py:228-241) is a genuinely subtle read of the spec and matches
  html5lib's `startTagCloseP` → `endTagP` routing exactly. The comment at
  treebuilder.py:698-701 correctly explains why the `</p>`-not-in-scope error is
  not a duplicate of it (the empty `<p>` inserted first makes the algorithm's own
  check pass) — I verified that reasoning holds.
- The `CLOSES_IN_SCOPE` single-error decision (treebuilder.py:660-673) is right,
  and the code shape — compute `in_scope`, generate implied end tags if in scope,
  check `current != name` *unconditionally*, then pop if in scope — is a faithful
  reproduction of html5lib's `endTagBlock`. Corroborated by `tests19.dat:22-23`.
- The `li` / `dd` / `dt` mapping (treebuilder.py:620-640) matches html5lib's
  `endTagListItem` exactly, including the not-in-scope/in-scope split.
- The whole-corpus sweep for codes outside `TREE_ERROR_CODES` (zero hits) is the
  right check to have run, and it is the check that makes the curated-set
  invariant meaningful rather than decorative.
- Refusing to broaden `TREE_ERROR_CODES` to buy passing cases, as the brief
  demanded, and keeping the two failure categories apart.

## Issues

### Critical (Must Fix)

None.

### Important (Should Fix)

**1. `_mode_in_body` has no DOCTYPE guard — 5 corpus occurrences under-reported.**
treebuilder.py:521-536. The brief listed five modes and the implementer added
exactly five, but the spec's "in body" mode also says "A DOCTYPE token: Parse
error. Ignore the token." A `DoctypeToken` reaching `_mode_in_body` matches none
of the `isinstance` branches and is silently dropped — behaviourally correct,
diagnostically silent. Verified directly:

    TreeBuilder('<!DOCTYPE html><div><!DOCTYPE html></div>').build() → errors == []

This is the exact failure mode the task exists to eliminate. It costs
`unexpected-doctype` on `domjs-unsafe.dat:31`, `:32`, `:33`, `:41` and `:43` —
all five of the corpus's missing `unexpected-doctype` instances, and four of the
five reach our `in_body` (tables and select being unimplemented, the DOCTYPE
arrives there under our parser). Fix: add the same three-line guard at the top of
`_mode_in_body`.

**2. Heading end tags report the wrong code when no heading is in scope.**
treebuilder.py:641-651. The implementer wrote the `li`/`dd`/`dt` shape
(`unexpected-end-tag` when not in scope, `end-tag-too-early` when in scope but
not current), but html5lib's `endTagHeading` uses the `endTagBlock` shape — the
`end-tag-too-early` check is unconditional and there is no not-in-scope code.
The corpus is unambiguous: `tests19.dat:22`, input `<!doctype html><p></h3>foo`,
with no heading open anywhere, expects a single `end-tag-too-early`. Verified:

    TreeBuilder('<!DOCTYPE html><p>x</h3>y').build() → [(19, 'unexpected-end-tag')]

This is a mapping bug in a recording site — the category the brief said was
"worth finding" — and it is asymmetric with the `CLOSES_IN_SCOPE` decision the
report defends at length two paragraphs earlier. It escaped detection because the
curated set is `tests1.dat` only and no `tests1.dat` case exercises a heading end
tag with nothing in scope. Fix: hoist the `current != name` check out of the
`else`, mirroring `CLOSES_IN_SCOPE`, and drop the `unexpected-end-tag` branch.
(The in-scope cases `tests19.dat:21` and `:23` already agree and stay agreeing.)

**3. The `tests1.dat:37` xfail reason names a root cause that would not fix it.**
tests/htmlparse/test_parse_errors.py:71-75. The stated cause — the tokenizer
dropping the `<` and `/` of a bare `</` at EOF — is real and correctly diagnosed
(spec: end tag open state at EOF emits U+003C, U+002F and EOF; ours emits EOF
alone, and `a<` does emit its `<`, so the asymmetry is genuine). But it is only
half the story. Suppose it were fixed: the initial mode would see `CharacterToken("</")`
→ `expected-doctype-but-got-chars` ✓, the text would land in `<body>`, and at EOF
the open elements would be `html` and `body` — both in `EOF_OK_OPEN` — so the
tree builder would still emit no `expected-closing-tag-but-got-eof`, and the
multiset would still not match. The corpus's expected document confirms only
`html` and `body` are open. The reason: in html5lib, `expected-closing-tag-but-got-eof`
is *also* a tokenizer error, emitted by the close-tag-open state at EOF — the same
string names both a tokenizer and a tree-construction error in `#errors`. That
undermines the curation filter's premise for this one code: a case can qualify as
"curated" while expecting a tokenizer-origin instance the tree builder can never
produce. Fix: correct the xfail reason to name both causes, and note the
overloaded code in the comment above `TREE_ERROR_CODES` or in `_curated_cases`.

### Minor (Nice to Have)

**4. `conformance.csv`'s `parse_errors` column changed meaning without a second
column.** tests/htmlparse/test_html5lib_tree.py:187, 222, 239 still read
`builder.metrics["parse_errors"]`, which now holds tree errors where it held
tokenizer errors. Disclosed in the report, and I confirmed `grep -rn parse_errors
src/ tests/ scripts/` finds no other consumer and that `scripts/conformance_report.py`
does not read the CSV. Still: the global constraint says every stage emits metrics
to `data/metrics/`, and a column that silently changes meaning between commits is
a trap for the Phase 3 analysis. Add `tokenizer_parse_errors` as a second column
so both are recoverable.

**5. `CommentToken.pos` is still `-1`.** The tokenizer edit populated `EOFToken`
and `DoctypeToken` but not `CommentToken`. No current recording site takes a
comment's position (a comment in "initial" is inserted, not an error), so nothing
leaks today — but this is the same latent trap the report flags for
`close_p_element(pos)` at item 2, and it is one line to close.

**6. Whole-corpus multiset agreement is 388/474, not measured.** The brief only
asked for `tests1.dat`, so this is not a missed requirement — but the sweep is
three lines on top of the one already run, and it is what surfaced Important #2.
Worth adding as a reported number so the next task has a baseline.

**7. `unexpected-start-tag` is under-reported 33 times across the corpus.** The
report lists `unexpected-end-tag-before-html` and `expected-one-end-tag-but-got-another`
as the two curated-but-unemitted codes; `unexpected-start-tag` is emitted (13
times) but from only two of its many spec sites. Not a defect — the other sites
are unimplemented rules — but the report's "codes never emitted" section reads as
if coverage were complete outside those two, and it is not.

## Tests

The four xfails are genuinely deferred scope, not parked defects:
`tests1.dat:26` and `:98` need the "in head" any-other-end-tag rule, which
changes tree construction and would move conformance — explicitly out of bounds
for a task whose Step 7 requires conformance to be unmoved. `:106` needs the
table insertion modes. `:37` needs a tokenizer output change (plus the correction
in Important #3). All four carry `strict=True` (test_parse_errors.py:96-98), so a
case that starts passing turns the suite red rather than drifting silently —
which is what makes the in-head fix in a later task self-announcing. The
convention mirrors `KNOWN_MISSES` in `test_html5lib_tree.py`. No case that agrees
today is marked. Reported test output is clean (no warnings).

The tests verify real behaviour — every one builds a real `TreeBuilder` over real
source and inspects real output; there are no mocks and no assertion-free tests.
Edge cases from the brief are covered. The gap is coverage breadth, not test
quality: nothing pins the `unexpected-doctype` sites (Important #1 would have been
caught by one), nothing pins the heading family (Important #2, likewise), and
`test_error_positions_are_within_the_source` runs on one input only.

## Structure

`treebuilder.py` grew by ~128 lines to ~800; the growth is distributed across
existing methods as recording calls rather than concentrated in new abstractions,
and `_error` is the single recording seam. `EOF_OK_OPEN` and `TREE_ERROR_CODES`
sit with the other module constants. `close_p_element` gaining a required `pos`
is the only interface change, and all four call sites pass a real token offset.
No new file is oversized (`test_parse_errors.py` is 130 lines). The file layout
follows the plan.

## Assessment

**Spec compliance:** ✅ compliant on everything the brief specified, with two
spec sites missed inside the implemented modes (in-body DOCTYPE; heading end tag
code) — both under-reporting, both invisible to the current suite.

**Task quality:** Needs fixes

**Reasoning:** The three disclosed judgement calls are all correct and better
reasoned than the brief they replace — `EOF_OK_OPEN` matches the spec's eighteen
names exactly, the code substitution fixes a genuinely unreachable branch, and
the DOCTYPE early return is spec-correct in all five modes (and in `in_head` is a
real, correct tree change that the corpus happens not to cover). What the task
missed is one more DOCTYPE site and one mapping code, both of which the corpus
already contains the evidence for and neither of which any test would catch —
which is precisely the class of silence this task exists to end.
