# Task C report: DOCTYPE identifiers and quirks mode

**Status: complete.** All eight steps done. Two of the plan's own values were
wrong against the spec; both are documented below with the spec text that
settles them.

---

## Headline numbers

| Measure | Before | After |
| --- | --- | --- |
| `pytest` | 5119 passed, 59 xfailed, 0 failed | **5179 passed, 60 xfailed, 0 failed** |
| Conformance, all files | 759/1592 | **780/1592** (+21, 0 regressions) |
| Conformance, tests1.dat | 64/112 | 64/112 (unchanged) |
| `doctype01.dat` | 18/37 | **36/37** |
| Whole-corpus parse-error agreement | 404/474 | 404/474 (**identical set**, not merely an equal total) |

---

## Two findings, both spec-vs-plan

### Finding 1 — the 55-prefix table is correct; the plan's "4.0" test case is not

The task brief asked for the prefix count found in the spec. **The spec's list
holds exactly 55 prefixes, matching the plan's 55.** Verified twice, in two
independent ways:

* Against the WHATWG spec source (`whatwg/html@main:source`, the `<ul
  class="brief">` under `id="quirks-mode-doctypes"` in "The 'initial' insertion
  mode"): 55 `The public identifier starts with:` items, plus 3 `is set to:`
  exact matches, 1 quirks system identifier, and a *separate* two-item clause
  for HTML 4.01.
* Against html5lib's `html5parser.py::InitialPhase.processDoctype`, whose tuple
  was diffed set-wise against ours: **0 missing, 0 extra, 0 duplicates, 0
  non-lowercase entries.**

So the transcription in the plan was clean. What was *not* clean is the unit
test the plan shipped alongside it:

```python
('<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.0//EN">', "quirks"),   # plan
```

`-//W3C//DTD HTML 4.0//EN` is HTML 4.0 **Strict**. The spec list carries
`-//W3C//DTD HTML 4.0 Frameset//` and `-//W3C//DTD HTML 4.0 Transitional//`
but **no bare `-//W3C//DTD HTML 4.0//` entry**, and html5lib agrees. HTML 4.0
Strict is a standards-mode DOCTYPE in every real browser. The spec wins: the
case now expects `no-quirks`, with a comment saying why, and a contrasting
`-//W3C//DTD HTML 4.0 Transitional//EN` case expecting `quirks` was added right
beside it so the distinction is pinned rather than merely asserted.

Had I "matched the plan" here, the fix would have been to add a bogus 56th
prefix to the table and misclassify every HTML 4.0 Strict page on the web.

### Finding 2 — the 4.01 clause turns on empty-string, not just on missing

The brief said the two HTML 4.01 prefixes "appear in `QUIRKS_PREFIXES` *and* in
`QUIRKS_UNLESS_SYSTEM_ID`". They do not, in the plan's own table — the plan's
`QUIRKS_PREFIXES` lists `4.0`, never `4.01`. That matters, because the plan's
`classify_document_mode` reaches the 4.01 rule only from *inside* the
`QUIRKS_PREFIXES` loop:

```python
    for prefix in QUIRKS_PREFIXES:                       # plan
        if public.startswith(prefix):
            if prefix in QUIRKS_UNLESS_SYSTEM_ID and token.system_id is not None:
                return "limited-quirks"
            return "quirks"
```

Since no 4.01 prefix is in `QUIRKS_PREFIXES`, that inner branch is dead code and
both 4.01 DOCTYPEs would classify as `no-quirks` — failing two of the plan's own
nine cases. The 4.01 pair is checked in its own clause now, after the long list
and before the XHTML limited-quirks list, mirroring the spec's structure.

While correcting that, the spec's actual wording turned out to be narrower than
the brief's "unless a system identifier is present":

> The system identifier is **missing or the empty string**, and the public
> identifier starts with: `-//W3C//DTD HTML 4.01 Frameset//` → *quirks*
>
> The system identifier is **neither missing nor the empty string**, and the
> public identifier starts with … → *limited-quirks*

So `PUBLIC "-//W3C//DTD HTML 4.01 Transitional//EN" ""` is **quirks**, not
limited-quirks. html5lib tests `systemId is None` and gets this wrong; we follow
the spec, and there is a test for it. The spec's trailing note — "a system
identifier whose value is the empty string is not considered missing" — governs
the *parse-error* condition at the top of the DOCTYPE rules, not these two
clauses, and the comment on `QUIRKS_UNLESS_SYSTEM_ID` says so, because that note
reads like a contradiction if you meet it cold.

---

## Changes, per step

### Step 1–2: failing tests
Created `tests/htmlparse/test_doctype.py`. Ran it: 34 failed / 19 passed,
failing on `DoctypeToken` having no `public_id`, as predicted.

### Step 3: token fields
`DoctypeToken` gains `public_id: str | None` and `system_id: str | None`.
`None` means **missing**, which is distinct from the empty string — the quirks
table and the html5lib serialization both depend on the distinction.

### Step 4: the spec's DOCTYPE state family
`_state_doctype` — Phase 1's "consume to `>`, keep the first word" — is
replaced by the spec's sixteen states, DOCTYPE state through bogus DOCTYPE
state. (The plan says fifteen; counting the spec's own state headings inclusive
of both endpoints gives sixteen. Cosmetic.)

Three shared bodies rather than sixteen transcriptions, because four pairs of
states differ only in *which* identifier they concern:

* `_after_doctype_keyword(kind)` — the two "after PUBLIC/SYSTEM keyword" states
* `_before_doctype_identifier(kind)` — the two "before identifier" states
* `_read_identifier(kind, quote)` — the four quoted-identifier states

Each still has its own thin `_state_*` method, so the dispatcher's
`getattr(self, f"_state_{self.state}")` contract is untouched and every spec
state name still exists as a real state string.

Also in this step:
* `_ascii_lower(ch)` for DOCTYPE names. `str.lower()` would fold `É`→`é` and
  expand `İ` to two code points; the spec lowercases ASCII A–Z only.
* Token scratch (`_doctype_name/_public/_system/_force_quirks`) is reset in
  `_state_markup_declaration_open`, along with `_token_start`, because the
  DOCTYPE state now runs once per character and can no longer compute its own
  start offset.
* Module docstring: deviation #3 removed, #4–#8 renumbered to #3–#7. Every
  cross-reference chased (`treebuilder.py` ×2, `test_html5lib_tokenizer.py` ×2).

Error offsets follow the existing house convention (point *at* the offending
character) and were spot-checked against `doctype01.dat`'s `#new-errors`
columns: `<!DOCTYPEhtml>` → 9 (col 10 ✓), `<!DOCTYPE potato taco>` → 17 (col 18
✓), missing-whitespace-between-identifiers → 49 (col 50 ✓).

One asymmetry worth not "tidying": `after DOCTYPE system identifier` is the only
route into the bogus state that does **not** set force-quirks. Both identifiers
parsed cleanly there, so the DOCTYPE is still usable for the quirks table; only
the trailing junk is wrong. There's a comment saying so.

### Step 5: the table
`QUIRKS_EXACT` (3), `QUIRKS_SYSTEM_ID` (1), `QUIRKS_PREFIXES` (55),
`LIMITED_QUIRKS_PREFIXES` (2), `QUIRKS_UNLESS_SYSTEM_ID` (2), and
`classify_document_mode` in `treebuilder.py`.

Deviations from the plan's code, all deliberate:
* the dead 4.01 branch is replaced by a real clause (Finding 2);
* `startswith` is called once per tuple rather than in a Python loop — CPython
  handles a tuple argument natively;
* `_ascii_lower` for the identifiers too, for the same reason as the name.

### Step 6: `Document` and `_mode_initial`
`Document.mode` is a plain attribute defaulting to `"no-quirks"`;
`Document.quirks_mode` is now a read-only `@property` returning
`mode == "quirks"`. Assignment raises `AttributeError`, which is the point.

`DocumentType` gains `public_id`/`system_id`, and `_render` in `dom/node.py`
emits the html5lib form `<!DOCTYPE name "pub" "sys">` when either is present.
This was not in the plan's file list but the corpus round-trip test cannot pass
without it — Phase 1 had nowhere to *put* the identifiers, so the serializer had
nothing to render.

`_mode_initial` also changes `DocumentType(token.name or "html")` to
`... or ""`. `<!DOCTYPE>` must serialize as `<!DOCTYPE >`; substituting `"html"`
both misrendered it and would have classified it as no-quirks.

### `quirks_mode` sites converted (the grep)

```
$ grep -rn 'quirks_mode' src/ tests/ scripts/     # before
src/mayshay/dom/node.py:45:        self.quirks_mode = False
src/mayshay/htmlparse/treebuilder.py:442: self.document.quirks_mode = token.force_quirks or token.name != "html"
src/mayshay/htmlparse/treebuilder.py:459: self.document.quirks_mode = True
```

Three sites, all writers, all converted:

1. `dom/node.py:45` — the attribute itself → `self.mode = "no-quirks"` plus the
   derived property.
2. `treebuilder.py:442` (DOCTYPE branch) → `self.document.mode =
   classify_document_mode(token)`.
3. `treebuilder.py:459` (fall-through branch, **added by Task B**) →
   `self.document.mode = "quirks"`.

Site 3 is the one the pre-flight ruling ordered Task B before Task C for. Left
alone it would have raised `AttributeError` on the first document without a
DOCTYPE — i.e. on most of the corpus. No fourth site exists; after the change
the only remaining occurrences are the property definition, one comment, and
test assertions.

### Step 7: results

`doctype01.dat`: **36 of 37 in-scope cases pass** (was 18). The one failure is
attributed and pinned as a strict xfail in `KNOWN_MISSES` in the new test file:

* **`doctype01.dat:30`** — *neither the table nor identifier capture.* The
  DOCTYPE parses correctly to `<!DOCTYPE root-element>`. The input embeds a
  comment inside the internal subset, so the bogus-DOCTYPE scan ends at the `>`
  of `-->` and leaves `"\n]>"` as body text. The leading newline should be split
  off and ignored by "before head"; tokenizer deviation #1 coalesces the run
  into one character token and `TreeBuilder._is_space` is all-or-nothing. This
  is the identical gap already pinned as `tests1.dat:50` in
  `test_html5lib_tree.py`. Fixing it is a character-token-splitting change,
  unrelated to this task.

**Conformance set difference (21 newly passing, 0 newly failing):**

```
+ doctype01.dat:3,4,13,14,15,22,23,24,25,26,28,29,31,32,33,34,35,36
+ quirks01.dat:0
+ tests6.dat:4
+ tests6.dat:46
```

All 21 were previously unrepresentable: each needs either an identifier in the
serialized DOCTYPE or the empty-name rendering. `quirks01.dat:0` and the two
`tests6.dat` cases are the incidental pickups outside `doctype01.dat`.

**xfail ledger:** nothing to retire. No entry in `test_html5lib_tree.py`,
`test_html5lib_tokenizer.py` or `test_parse_errors.py` flipped — the suite is
`xfail_strict = true` project-wide, so a silent XPASS is impossible, and the run
reports 0 failures. `tests1.dat` conformance is unchanged at 64/112, which is
expected: `tests1.dat` has no DOCTYPE-with-identifier cases. The one new ledger
entry is `doctype01.dat:30`, in the new file.

**Error agreement:** 404/474, and the *set* of disagreeing ids is byte-identical
to the baseline (`diff` of before/after is empty), not merely the same total.
Task B's `expected-doctype-but-got-*` codes are untouched.

`tests/htmlparse/test_html5lib_tokenizer.py::_to_corpus_shape` was updated in
passing: it hardcoded `None, None` for the identifier columns with a comment
citing deviation #3. It now reports the real values. No case changed outcome —
that harness covers only the raw-text and entity corpora — but leaving it would
have been a lie that silently stops checking two columns.

### Step 8: commit
One commit on `phase-2-css-to-styled-tree`. `git status` clean afterwards.
`.venv/.../__editable__.mayshay-0.1.0.pth` verified unchanged, still the single
line `/Users/atishaypahadiya/projects/mayshay/src`; nothing under `.venv/` was
touched. All experiments ran from `/tmp` scripts via `sys.path`.

---

## What a reviewer should scrutinise hardest

1. **Finding 1, above all.** I changed a test expectation the plan supplied.
   That is the single highest-leverage thing to double-check: if
   `-//W3C//DTD HTML 4.0//EN` really is quirks, then my table is missing an
   entry and every HTML 4.0 Strict page classifies wrong. The evidence is the
   spec's `<ul>` (no bare `4.0//` item) and html5lib's tuple (likewise). Both
   are quoted above and both are one command away.

2. **The empty-system-identifier rule** (Finding 2). We deliberately diverge
   from html5lib here. If a future corpus bump adds a case that pins html5lib's
   behaviour instead of the spec's, this is where it will surface.

3. **The three shared state bodies** in the tokenizer. Collapsing eight spec
   states into three parameterised bodies is where a transcription error would
   hide, because the collapse makes the two halves *look* symmetric. They are
   not perfectly symmetric: `_after_doctype_keyword` reports
   `missing whitespace after doctype {kind} keyword` where
   `_before_doctype_identifier` reports nothing, and
   `_state_after_doctype_public_identifier` reports
   `missing whitespace between doctype public and system identifiers` where its
   `between_*` sibling reports nothing. Those asymmetries are the spec's.

4. **`_state_after_doctype_system_identifier` not setting force-quirks** while
   its four sibling error paths do. Deliberate, spec-mandated, and exactly the
   sort of thing a tidying pass would flatten.

5. **`DocumentType(token.name or "")`.** The change from `or "html"` is what
   flipped `doctype01.dat:3` and `:4`. Worth confirming nothing elsewhere
   assumed a DOCTYPE node always has a non-empty name.

6. **Scope discipline.** `Document.mode` is written and asserted; nothing reads
   it to change behaviour. Quirks *behaviour* — unitless lengths, the alternate
   box model — is Phase 3. There is no `if mode == "quirks"` anywhere in
   `src/`, and there should not be one until then.

---

# Review round 1 — three Minors addressed

All three done. Suite **6024 passed, 72 xfailed, 0 failed** (was 5179/60).
Conformance still **780/1592** and **64/112**, failing-id set byte-identical to
the pre-review run. Parse-error agreement still **404/474**, set byte-identical
to the task baseline. `git status` clean; venv `.pth` unchanged.

## Minor 1 — DOCTYPE tokenizer corpus adopted (855 cases)

New third section in `tests/htmlparse/test_html5lib_tokenizer.py`, alongside the
existing raw-text and character-reference sections.

**Result: 843 / 855 pass. 12 failures, and the count not attributable to the
NUL deviation is ZERO.** All twelve are the same shape — a literal U+0000 in a
DOCTYPE name or a quoted identifier where the spec wants U+FFFD — and all
twelve live in `test3.test`. Each is a `xfail(strict=True)` entry in
`DOCTYPE_KNOWN_MISSES` keyed by `(filename, description, input)`, with the
deviation named. No assertion was weakened and no case was dropped to reach a
number; the comparison is the same `_tokenize_data(...) == _coalesce(expected)`
the entity section already uses.

**Nothing new surfaced.** The widened denominator did not find a bug in the
fifteen states. That is a genuine result rather than a filter artifact, and the
two audits that back it are worth stating because the coordinator was right that
this is where a number gets quietly manufactured:

* **The selection rule keys on the *expected* output, not the input.** A case
  is in scope when `initialStates == ["Data state"]` and the fixture's expected
  output contains a DOCTYPE descriptor. So a case where we *wrongly fail to
  produce* a DOCTYPE is still selected and still fails — the filter cannot be
  satisfied by our own misbehaviour.
* **The rule's one hole was measured, not assumed.** Six Data-state cases whose
  input mentions `<!d` expect something other than a DOCTYPE (bogus comments,
  `<!doc…`). I ran all six: five pass, and the sixth (`test4.test`, `<!doc` +
  NUL) fails — on the NUL deviation again. It is a comment-state case, so it
  belongs to whichever task adopts the comment corpus. It is named in the
  section's comment rather than laundered into this ledger.

**Count discrepancy, stated rather than reconciled away:** the coordinator
reported 850 cases / 838 passing; I measure **855 / 843**. The difference is 5
cases in the denominator and 5 in the numerator — i.e. five extra *passing*
cases — so the two readings agree exactly on the failure set. My denominator is
every fixture file globbed (`test1`–`test4` contribute 854, `domjs.test` 1), so
the likeliest explanation is a slightly narrower file list on the reviewer's
side. Nothing turns on it: the failure count, 12, and its attribution, all NUL,
are identical either way.

Guard tests, following house discipline:
* `test_doctype_corpus_is_not_empty` — hard `== 855`, so a loader regression
  that silently collects nothing cannot read green.
* `test_doctype_ledger_is_keyed_uniquely_and_has_no_stale_entries` — asserts the
  `(file, description, input)` key really is unique (a duplicate would let one
  entry mask another case) and that no ledger entry matches nothing.
* `_doctype_corpus_files()` globs the fixture directory rather than hardcoding
  the five files that carry DOCTYPE cases, so a corpus bump that adds a sixth
  moves the collection count — loudly — instead of being skipped.

## Minor 2 — the `QUIRKS_UNLESS_SYSTEM_ID` rationale was wrong

The reviewer is correct and my comment was not. I had written that the spec's
note — "a system identifier whose value is the empty string is not considered
missing" — governs the parse-error condition at the top of the DOCTYPE rules
*and not* these two clauses. It governs all of them; that is what "for the
purposes of the conditions above" means.

The code was right for a reason I had stated wrongly, which is exactly the
shape the coordinator flagged: a correct implementation carrying a rationale
that invites a future "fix". The two spec sentences do not conflict, they
compose. The note says "missing" never quietly widens to "missing or empty", so
any clause that wants to cover the empty string must say so — and these two do,
verbatim: quirks when the system identifier is *"missing or the empty string"*,
limited-quirks when it is *"neither missing nor the empty string"*. That
explicit wording, not an exemption from the note, is what the truthiness test in
the code rests on. Comment rewritten to say so, including the corollary that
the same note is why `PUBLIC "..." ""` still trips the parse error.

## Minor 3 — typing and the missing gates

* `dom/node.py` exports `DocumentMode = Literal["no-quirks", "limited-quirks",
  "quirks"]`; `Document.mode` is annotated with it and
  `classify_document_mode` returns it. A misspelled mode is now a type error
  rather than a value that silently matches no comparison.
* `classify_document_mode`'s docstring now names the two spec gates that are
  deliberately absent — "if the document is not an iframe srcdoc document" and
  "the parser cannot change the mode flag is false" — with why each is
  unrepresentable today (no browsing-context plumbing; no fragment parsing
  entry point), the note that both gate the whole computation so adding them
  later means wrapping the call site rather than editing the table, and the
  measurement that neither affects any corpus case.
