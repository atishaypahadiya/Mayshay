# Task C review: DOCTYPE identifiers and quirks mode

Reviewed diff `6b7a7c8..534e656` against `task-C-brief.md` and `task-C-report.md`.

## Spec Compliance

- ✅ **Spec compliant.** All eight steps present: token fields
  (`tokenizer.py`, `DoctypeToken.public_id/system_id`), the spec's DOCTYPE state
  family, the classification table and `classify_document_mode` (`treebuilder.py`),
  `Document.mode` + derived `quirks_mode` (`dom/node.py`), and
  `tests/htmlparse/test_doctype.py`. Two files outside the brief's list
  (`dom/node.py`, `test_html5lib_tokenizer.py`) are changed; both are load-bearing
  (the serializer had nowhere to put identifiers; the tokenizer harness hardcoded
  `None, None` for two columns) and neither is scope creep.
- ⚠️ Cannot verify from diff: the full-suite totals (5179 passed / 60 xfailed) —
  I ran only `tests/htmlparse/test_doctype.py` (60 passed, 1 xfail, no warnings).
  Everything else in the report I re-derived independently; see below.

### The prefix table — independently verified against the live spec

Fetched `https://html.spec.whatwg.org/multipage/parsing.html`, extracted the
"initial" insertion mode lists mechanically, and set-diffed them against the
implementation's tuples:

- spec "public identifier starts with" in the quirks clause: **57**, of which the
  two `4.01` entries live in their own `system identifier is missing or the empty
  string` sub-clause → **55** unconditional prefixes.
- `QUIRKS_PREFIXES`: 55, **0 missing, 0 extra, 0 duplicates, all lowercase**.
- `QUIRKS_EXACT`: the spec's three `is set to` public identifiers;
  `QUIRKS_SYSTEM_ID`: the spec's one `is set to` system identifier.
- `LIMITED_QUIRKS_PREFIXES`: the two XHTML 1.0 entries, unconditional, as in the
  spec's limited-quirks clause.
- **No bare `-//W3C//DTD HTML 4.0//` entry exists in the spec list.** The
  implementer's Finding 1 is correct and the plan's test expectation was wrong:
  `-//W3C//DTD HTML 4.0//EN` (HTML 4.0 Strict) is `no-quirks`. Had the plan been
  "matched", a 56th bogus prefix would have misclassified every HTML 4.0 Strict
  page. The contrasting `4.0 Transitional` case added beside it
  (`test_doctype.py`, classification params) pins the distinction.

### The rewritten 4.01 clause — correct, including ordering

Spec verbatim (quirks clause): *"The system identifier is missing **or the empty
string**, and the public identifier starts with: `-//W3C//DTD HTML 4.01
Frameset//`"* (and Transitional); limited-quirks clause: *"The system identifier
is **neither missing nor the empty string**, and the public identifier starts
with: …"*.

So `classify_document_mode`'s `return "limited-quirks" if system else "quirks"`
is **spec-correct**, and html5lib's `systemId is None` is the divergent one. Point
3 of the dispatch resolved: the implementation follows the spec, that is the right
choice, and **no corpus case discriminates** — `grep` over all 60 `.dat` files and
the tokenizer corpus finds no `4.01 Frameset`/`4.01 Transitional` DOCTYPE at all
(only bare `4.01//EN`), so nothing in the vendored corpus would have caught either
behavior.

Clause ordering is equivalent to the spec's: exact → system id → 55 prefixes →
4.01 pair → XHTML pair → no-quirks. The 4.01 strings are disjoint from every
`QUIRKS_PREFIXES` entry (`"…4.01 frameset//".startswith("…4.0 frameset//")` is
False), and `QUIRKS_EXACT` is checked before the prefixes, so no earlier clause can
shadow a later one. Behavior spot-checked end to end (11 cases, all as expected),
including `4.01 Transitional` with `""` → quirks, with a real URI → limited-quirks,
uppercased input → limited-quirks, IBM system id → quirks, `about:legacy-compat` →
no-quirks, `PUBLIC "html"` → quirks.

### DocumentType serialization — corpus-correct

Confirmed against real fixtures rather than the report:
- `doctype01.dat` `<!DOCTYPE potato SYSTEM "taco">` → `| <!DOCTYPE potato "" "taco">`
  — system-only renders with an empty public field, which is what `_render` does.
- `tests6.dat:604` `<!DOCTYPE html PUBLIC "-//W3C//DTD HTML 4.01//EN">` →
  `| <!DOCTYPE html "-//W3C//DTD HTML 4.01//EN" "">`.
- `quirks01.dat:1` `<!DOCTYPE html SYSTEM "http://www.ibm.com/…">` →
  `| <!DOCTYPE html "" "http://www.ibm.com/…">`.
- Both identifiers missing → `| <!DOCTYPE name>`; `<!DOCTYPE>` → `| <!DOCTYPE >`,
  which is what `DocumentType(token.name or "")` in `treebuilder.py` `_mode_initial`
  buys. `DocumentType.name` has no other consumer in `src/` or `scripts/` (grepped),
  so the empty name is safe.

### Conformance +21 — genuine, verified as a set

Extracted the base commit with `git archive 6b7a7c8` into `/tmp/baseC` (repo left
untouched; corpus symlinked read-only) and ran `scripts/conformance_report.py` on
both trees:

```
base 6b7a7c8 : all files 759/1592   head 534e656 : all files 780/1592
--diff       : newly passing (21), newly failing (0)
```

The 21 ids are exactly the ones the report lists (`doctype01.dat` ×18,
`quirks01.dat:0`, `tests6.dat:4`, `tests6.dat:46`). Not an equal-sized swap; not
attributable to anything else in the diff.

### Parse-error agreement — unregressed, same set

Re-implemented Task B's whole-corpus measurement (`/tmp/agree.py`: every case whose
expected codes all fall in `TREE_ERROR_CODES`, multiset comparison) and ran it on
both trees: **404/474 at base, 404/474 at head, and `diff` of the disagreeing id
lists is empty.**

### The DOCTYPE state family — EOF and force-quirks

All sixteen state strings assigned by the new code resolve to a real
`_state_*` method (checked by `hasattr` over the list — no f-string typos). Drove
EOF into each of the fifteen non-bogus states: every one emits exactly one
`DoctypeToken`, records `eof in doctype` once, sets `force_quirks=True`, and
preserves the partial name/identifier — matching the spec's "emit the current
DOCTYPE token" rule. `_state_bogus_doctype` at EOF emits without a second error and
without setting force-quirks, which is also the spec.

`force_quirks` remains the tokenizer's error flag only: `<!DOCTYPE foo>` →
`force_quirks=False` while the document is quirks (via the name rule), and
`<!DOCTYPE html SYSTEM "x" junk` → `force_quirks=False` (the one bogus route the
spec exempts, commented as such in `tokenizer.py`
`_state_after_doctype_system_identifier`). Phase 1's separation is intact and is
pinned by `test_force_quirks_still_means_tokenizer_error_only`.

Strongest independent evidence for the transcription: I ran the **unused
html5lib tokenizer corpus** against the new states — 850 "Data state" cases whose
output is a single DOCTYPE descriptor. **838 match exactly** on
`[name, public_id, system_id, correctness]`; all 12 mismatches are the documented
NUL→U+FFFD deviation (#5) and nothing else. Fifteen hand-written states with a
12/850 error surface, all of it pre-existing and documented, is a clean transcription.

### The new xfail — attribution confirmed

`doctype01.dat:30` (`<!DOCTYPE root-element [SYSTEM OR PUBLIC FPI] "uri" [ \n<!--
… -->\n]>`): the DOCTYPE node itself serializes correctly as
`| <!DOCTYPE root-element>`; the sole diff is a leading `"\n"` retained on the body
text node (`"\n]>"` vs `"]>"`). Not the table, not identifier capture. The case is
in the **base** failing set too (it is absent from the newly-passing 21), so it is a
pre-existing failure newly *pinned* because `doctype01.dat` had no pytest harness
before — not a defect parked under someone else's cause. Same coalescing/`_is_space`
family as `tests1.dat:50`, which I reproduced for comparison.

## Strengths

- Correcting the plan against the spec twice, with the spec text quoted, rather
  than matching the plan. The 4.0-Strict fix in particular would have been a silent
  real-world misclassification.
- The three shared bodies (`_after_doctype_keyword`, `_before_doctype_identifier`,
  `_read_identifier`) collapse eight states without hiding the asymmetries; each
  spec state still exists as a real state string and a thin `_state_*` method, so
  the dispatcher contract and the corpus's state names are preserved.
- `_ascii_lower` in both modules, with the `İ`/`É` reasoning written down — a
  genuine `str.lower()` trap for a `startswith` table.
- `quirks_mode` as a read-only property is the right shape: it makes the third
  writer site (added by Task B) impossible to miss instead of silently wrong.
- `test_html5lib_tokenizer._to_corpus_shape` de-hardcoded rather than left as two
  columns that quietly assert nothing.
- Scope discipline held: no `if mode == "quirks"` anywhere in `src/` — grepped.

## Issues

### Critical (Must Fix)
None.

### Important (Should Fix)
None.

### Minor (Nice to Have)

1. **`treebuilder.py`, the comment block above `QUIRKS_UNLESS_SYSTEM_ID`** — the
   rationale is wrong even though the code is right. It claims the spec's trailing
   note ("a system identifier whose value is the empty string is not considered
   missing") "governs the *parse error* condition at the top of the DOCTYPE rules,
   not these two clauses". The note's own words are "…not considered missing **for
   the purposes of the conditions above**", i.e. it applies to these very lists; it
   is simply redundant now that the bullets spell out "missing or the empty string".
   A future reader who checks the spec will find the comment contradicted and may
   "fix" the working code. Replace with: the bullets are explicit, and the note
   agrees with them.
2. **`tests/htmlparse/test_html5lib_tokenizer.py:38` `STATE_NAMES`** — the 850
   DOCTYPE cases in the tokenizer corpus remain unenforced because "Data state" is
   deliberately absent (a Task-3 scoping decision). The new states currently score
   838/850 against them with only NUL-deviation misses, so wiring them in (or a
   doctype-scoped variant in `test_doctype.py`) would pin name/public/system/
   correctness for 838 cases at near-zero cost. Today the only automated check on
   the fifteen new states is the tree-shaped `doctype01.dat` output; the new error
   messages and offsets rest on the report's manual spot-check alone.
3. **`dom/node.py` `Document.mode`** — a bare `str`. `Literal["no-quirks",
   "limited-quirks", "quirks"]` would make a typo'd assignment a type error rather
   than a value that silently reads as no-quirks.
4. **`classify_document_mode` docstring** — the spec also gates both lists on "not
   an iframe srcdoc document" and "the parser cannot change the mode flag is false".
   Neither exists here, correctly, but a one-line note would keep the next reader
   from thinking the transcription is incomplete.

## Assessment

**Spec compliance:** ✅ Spec compliant.

**Task quality:** Approved.

**Reasoning:** Every load-bearing claim in the report reproduced independently —
the 55-prefix table against the live spec, the 4.01 clause against the spec's
"missing or the empty string" wording, the serialization format against three
corpus fixtures, +21/−0 against a base-commit conformance run, 404/474 with a
byte-identical disagreeing set, and 838/850 on the tokenizer corpus the harness
does not yet run. The only findings are a comment whose rationale contradicts the
spec it cites and unclaimed free test coverage.

## Environment

`git status` clean, `HEAD` at `534e656`,
`.venv/…/__editable__.mayshay-0.1.0.pth` intact
(`/Users/atishaypahadiya/projects/mayshay/src`). Nothing under `.venv/` touched;
all experiments ran from `/tmp` (`/tmp/baseC` is a `git archive` extract of the
base commit, with the corpus symlinked read-only).
