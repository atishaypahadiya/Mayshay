# SDD ledger — plan: docs/plans/2026-08-26-phase-2-css-to-styled-tree.md

Spec: the plan is self-declared as its own spec. It argues from the Phase 1
output at tag `phase-1` (commit `f252f96`) and from `CLAUDE.md`'s Rules
section, which is the project-wide authority.

Branch: `phase-2-css-to-styled-tree`, created from `main` @ f252f96.
Plan committed at 1de1131.
Workspace: feature branch in place, NOT a worktree — same reasoning as Phase 1,
and now with direct evidence: the venv's editable install pins `mayshay` to
`/Users/atishaypahadiya/projects/mayshay/src`, and during Phase 1 a subagent
repointed that `.pth` at a /tmp copy and deleted the copy, taking the whole
suite down while `git status` reported clean. Every dispatch this phase carries
a warning against touching `.venv/`.

Baseline: `.venv/bin/pytest` → 5051 passed, 55 xfailed, 0 failed.
Corpus baseline: 759/1592 all files, 64/112 tests1.dat.

## Pre-flight conflict scan

### Cross-task pairs sharing a file or interface

| Pair | Produces → Consumes | Finding |
|------|--------------------|---------|
| A → J | `metrics.emit(stage, counters, *, source, run_id, path)`; J's `style_document` returns a `Counter` shaped to hand straight to it | Clean. Signatures agree at both ends. |
| A → all | `CLAUDE.md` metrics bullet rewritten to name the two `htmlparse` stages | Clean. Docs only. |
| **B → C** | Both modify `treebuilder.py`, and both edit `_mode_initial`'s fall-through branch | **CONFLICT P1** — see ruling |
| C → D | Both modify `dom/node.py` — C adds `Document.mode`, D adds `Node.computed_style` | Clean. Different classes, same file; sequential edits do not collide. |
| C → B | C converts `Document.quirks_mode` from an attribute to a read-only property | **CONFLICT P1** — same root, see ruling |
| B → (Phase 1 T2) | B's corpus test consumes `DatTest.errors` | Clean, and it retires a Phase 1 deferred minor: `DatTest.errors` was parsed but never read. |
| D → H | `annotate_positions`, `Element.class_list`, `Element.element_index` | Clean. Defined in D, consumed in H exactly as defined. |
| E → F | Token dataclasses and `CssTokenizer.tokenize()` | Clean. |
| F → G | `QualifiedRule.prelude` stays a token list for G to parse | Clean by design — F deliberately knows nothing about selectors. |
| G → H | `Complex`, `Compound`, `specificity()` | Clean. |
| I → J | `Length`, `Percent`, `Color`, `AUTO` | Clean. J's assertions use exactly these. |
| H → J | `matches()`, `RuleIndex` | Clean. |

### Per-task internal consistency

| Task | Tests vs. the code they specify | Finding |
|------|--------------------------------|---------|
| A | Tests reference `emit`, `read`, `new_run_id`, `STAGES_CSV`, all defined in Step 3. `tmp_path` used throughout so no test writes the real file. | Clean |
| B | `TREE_ERROR_CODES` used in tests, defined in Step 3. Corpus helper uses `load_tree_tests` / `requires_corpus` from Phase 1 Task 2. | Clean |
| C | Nine unit classifications plus all of `doctype01.dat`. Table is complete at 55 prefixes — verified by counting the plan's own literal. | Clean |
| D | `annotate_positions` used in the test and defined in Step 3; `element_index` asserted `None` pre-annotation and set post. | Clean |
| E–I | Each task's tests reference only names that task or an earlier one defines. | Clean |
| J | `style_document` returns `Counter`; the link test asserts `link_stylesheets_skipped` directly and discriminates 2 from 0. | Clean (corrected pre-execution — see below) |

### Plan vs. Global Constraints

| Constraint | Finding |
|------------|---------|
| "Every stage emits metrics to data/metrics/" | Satisfied engine-side for the first time: A provides the writer, J's `scripts/style_report.py` calls it. This closes Phase 1's ruling C4 and its Known Gap 7. |
| "CSS parsing hand-rolled; tinycss2/cssutils/cssselect forbidden" | E removes `tinycss2` at Step 1, before any CSS code exists. Rule recorded in CLAUDE.md in the same step. |
| "Tests mirror src/mayshay/" | `tests/cssparse/` mirrors `src/mayshay/cssparse/`; `tests/test_metrics.py` mirrors `src/mayshay/metrics.py`. |

## Rulings

Ruling P1 (B ↔ C, ordering and a stale snippet): Tasks A–D are declared
order-independent, but B and C are not independent of each other. Both edit
`_mode_initial`'s fall-through branch, and B's step-4 snippet contains
`self.document.quirks_mode = True` while C converts `quirks_mode` into a
read-only property derived from `Document.mode`. Run in the order C-then-B, B's
snippet would raise `AttributeError: can't set attribute`. Decided: **run B
before C**, and treat C's existing `grep -rn 'quirks_mode'` step as the
mechanism that finds and updates B's line — it is already in the plan for
exactly this class of problem. B's snippet stays as written because it is
correct at the time B runs. Carried into both dispatches. — Cost if wrong: an
`AttributeError` on the first document without a DOCTYPE, caught immediately by
C's own tests, which parse `<p>x` and `""`.

Ruling P2 (five plan corrections applied before execution, recorded so they are
not re-introduced): (a) `METRICS_DIR`'s `parents[2]` derivation is a fallback,
not a contract — drivers pass an explicit path, since that derivation holds
only under an editable install and Phase 1 saw exactly that pointer broken;
a test now pins that an explicit path wins. (b) Task C's quirks table shipped
with a `# ... transcribe the remainder` comment, which is precisely the
placeholder this plan format forbids, and it was the highest-risk line in the
document: an incomplete table misclassifies silently while only nine cases are
pinned. Now complete at 55 prefixes, with a Step 5 verification requiring the
count be checked against the spec and reported, plus all of `doctype01.dat`
added as the broad check. (c) `test_unitless_nonzero_length_is_invalid_in_
standards_mode` named a mode `parse_declaration_value` has no parameter for —
renamed rather than given an unused parameter. (d)
`test_link_stylesheets_are_counted_not_fetched` asserted only facts true of any
document and never touched the counter it named; rewritten to assert
`link_stylesheets_skipped` and discriminate 2 from 0. That is the same
decorative-test defect that cost a fix round in Phase 1 Task 3. (e)
`Color(0, 128, 0)` for CSS `green` is correct and now says so in the test — the
colour usually pictured as green, `#00FF00`, is `lime`. — Cost if wrong: (b) is
the one that mattered; the rest were caught before any code existed.

## Progress

Task briefs extracted by letter (A-J). The `task-brief` script matches numeric
task ids only; the plan uses the letters the work was named by, so the briefs
were extracted directly rather than renumbering the plan to suit the tool.

Task A: dispatched (sonnet — one new module, complete code in the brief,
  transcription plus testing). Base 1de1131. Dispatch carries: the venv
  warning; both design decisions as settled rather than open; the requirement
  that every test write to tmp_path, since a test touching the real
  data/metrics/stages.csv is the exact failure mode decision 2 exists to
  prevent.
Task A: implementer DONE, commit 67a6c38 (base 1de1131). 5060 passed, 55
  xfailed (5051 + 9 new). Verified by me: `data/metrics/stages.csv` does NOT
  exist, so no test wrote outside tmp_path — the exact failure mode the
  drivers-call-the-writer decision exists to prevent; path gitignored via
  `data/metrics/*.csv`; two stages round-trip under a shared run_id with keys
  sorted and int and float both surviving; venv `.pth` intact; git clean.
Task A: review returned spec ✅, quality approved. 0 Critical, 3 Important,
  1 Minor.
  The atomicity claim HOLDS and was verified rather than accepted: header and
  rows fold into one io.StringIO, exactly one `open("a")` and one `write()`,
  no csv.writer touches the real handle, and the header is not written
  separately so the first call is covered too. The long-format claim was
  falsification-tested with a cssparse/never_seen key — nothing needed editing.
  - Important 1: no test asserts the VALUE of `source`. csv.DictWriter fills a
    missing key with "", so a dropped or mis-wired column passes all nine
    tests. This is precisely the "would a plausible wrong implementation pass?"
    question I put to the reviewer, and for `source` the answer was yes.
    `timestamp` is not asserted at all either.
  - Important 2: `is_new` is a TOCTOU race. Two concurrent first-writers can
    both see True and each append a header; the second is then read back by
    csv.DictReader as a data row with run_id == "run_id", quietly corrupting
    the analysis the file exists to feed.
  - Important 3: the zero-length-existing-file branch of `is_new` is correct
    but untested.
  - Minor: the brief's stale "8 passed" vs 9 actual — the implementer flagged
    it rather than adjusting anything to match, which is the right instinct.
Task A: fix round 1/5 dispatched. On the race I gave the exclusive-create
  approach (`open("x")` for the header, append for the rows) as a suggestion to
  evaluate rather than adopt on my say-so, and required `read` be hardened
  against duplicate header rows regardless — a corrupt row reaching the
  analysis half is the actual harm, and the zero-length case keeps a narrow
  window open whatever shape the header write takes. Also folded in a plan
  correction: Task A Step 4 still says "Expected: 8 passed".
Task A: fix round 1/5 → commit 42a50f7. 5063 passed, 55 xfailed (12 metrics
  tests, was 9). Race: exclusive-create (`open("x")`) adopted for the header,
  closing the file-absent TOCTOU; the narrower pre-existing-empty-file case is
  left open and documented, with `read()` hardened to discard any stray-header
  row. Plan Step 4 corrected to "Expected: 9 passed".
  Verified by me, including the case that matters: injecting a duplicated
  header mid-file gives 4 raw lines but 2 rows from `read()` — stray header
  discarded, real rows intact. The corrupt row never reaches the analysis half,
  which was the actual harm. Full row round-trips with correct `source` and a
  numeric `timestamp`; header still lands on a pre-existing empty file; no
  stages.csv; venv and git clean.
Task A: scoped re-review dispatched (sonnet) over 67a6c38..42a50f7, directed at
  three things I could not settle myself: whether the documentation scopes the
  race claim to exactly what the code guarantees (an overstated comment there
  is worse than the race, since it is what a future reader trusts); whether
  `read()`'s `run_id == "run_id"` heuristic could silently drop a legitimate
  row, since `emit` does not validate the caller's run_id; and whether the new
  tests actually discriminate, or merely add one assertion per column — which
  would reproduce the original defect's shape at greater length.
Task A: fix round 1/5 (3 addressed, 0 open; commits 67a6c38..42a50f7).
  Re-reviewer confirmed the source/timestamp fix is a genuine whole-row dict
  comparison rather than one assertion per column — the original defect was the
  test SHAPE, and per-column assertions would have reproduced it at greater
  length. It also checked my boundary concern rather than assuming: header and
  row go out as ONE `write()` in BOTH branches, so there is no two-operation
  window that could leave a headerless file. That worry was unfounded. And the
  zero-byte test was confirmed to fail against an implementation dropping the
  `size == 0` check.
  Documentation was judged to scope the residual race honestly ("does not
  engineer away") with no overclaim — which was the thing I most wanted
  checked, since an overstated comment there is worse than the race itself.
Task A: minor (deferred): `read()`'s `run_id == "run_id"` heuristic
  (metrics.py:141) would silently drop a legitimate row if a caller passed that
  literal string as run_id; `emit()` does not validate it and neither docstring
  mentions it. Low likelihood, undocumented — worth a one-line caveat at some
  later pass.
Task A: complete (commits 1de1131..42a50f7, review clean). 5063 passed,
  55 xfailed.

Task B: implementer DONE, commit 9d71ebb (base 42a50f7). 5119 passed,
  59 xfailed (+8 unit, +48 corpus, +4 documented strict xfails); all 55
  pre-existing strict xfails still xfail. Conformance UNMOVED at 759/1592 and
  64/112, which this task required — it records errors, it must not alter tree
  construction.
  Corpus, the two counts kept separate as required: 52 curated tests1.dat
  cases, 48 agree; 4 emit a code the corpus does not expect (root: _mode_in_head
  has no "any other end tag" rule, plus tables); 3 expect a code we never emit
  (root: the tokenizer drops the characters of a bare `</` at EOF); 3 are in
  both. ZERO codes outside TREE_ERROR_CODES across all 1592 cases — no mapping
  drift, which is what the curated set exists to detect.
  Verified by me: `<p>a<div>b</p></span><li>c` now reports 4 tree errors and 0
  tokenizer errors at the right offsets, so the two fields are genuinely
  distinct rather than aliases; a clean document reports 0 from both.

ANOTHER DEFECT IN MY BRIEF, caught and corrected by the implementer: I wrote
that any open element other than `html` or `body` at EOF is a parse error. The
spec's "in body" EOF rule excludes eighteen elements, not two — dd, dt, li,
optgroup, option, p, rb, rp, rt, rtc, tbody, td, tfoot, th, thead, tr, body,
html. My version reported an error on `<p>One<p>Two`, which html5lib does not.
Fixed via EOF_OK_OPEN; I confirmed the list matches the spec and that the input
now reports only the missing-doctype error. This is the fourth phase in a row
where a brief I wrote contained a defect that reached implementation and was
caught by the person implementing it.

Task B: three disclosures routed to review rather than accepted on my say-so —
  (a) the EOF_OK_OPEN list, since being short an entry over-reports and being
  long an entry under-reports and neither surfaces as a test failure; (b) the
  substitution of the unreachable `expected-doctype-but-got-comment` for
  `expected-doctype-but-got-end-tag`, which kept the set at 11 and so is a swap
  rather than a broadening, but needs the replacement confirmed as html5lib's
  actual code for that situation; (c) the DOCTYPE guards turning a fall-through
  into an early return, which is the ONLY place this task changes what the
  parser does rather than what it records.
  Also routed: the diff touches tokenizer.py (+11 lines), which Task B's brief
  never asked for. In scope or not, an undisclosed tokenizer change inside a
  tree-builder task is worth knowing about.
Task B: review dispatched (opus) over 42a50f7..9d71ebb.
Task B: review returned spec ✅ (on everything the brief specified), quality
  needs fixes. 0 Critical, 3 Important, 4 Minor, 2 ⚠️.
  The reviewer validated rather than accepted: re-derived both corpus buckets
  independently and found the attribution and per-code tallies exact; confirmed
  EOF_OK_OPEN is precisely the spec's eighteen names, neither short nor long;
  confirmed all four xfails are strict and genuinely deferred with none masking
  a case that agrees today; and judged the tokenizer edit in scope by necessity
  (the brief's own position test fails with the -1 defaults), correct, and
  disclosed. It also found the report UNDERSTATED the DOCTYPE early return: in
  `_mode_in_head` it is a genuine tree improvement, since a stray DOCTYPE no
  longer prematurely closes <head>.
  - Important 1: `_mode_in_body` has no DOCTYPE guard. MY BRIEF LISTED FIVE
    MODES AND OMITTED THE SIXTH. Confirmed:
    `<!DOCTYPE html><div><!DOCTYPE html></div>` records nothing; the five
    guards sit at exactly the five modes I named. Accounts for all five corpus
    `unexpected-doctype` misses.
  - Important 2: heading end tags use the li/dd/dt shape where html5lib uses
    the endTagBlock shape. Confirmed: `<p></h3>foo` emits `unexpected-end-tag`,
    tests19.dat:22 expects `end-tag-too-early`. Escaped only because the
    curated set is tests1.dat alone — which is itself the lesson.
  - Important 3: the tests1.dat:37 xfail reason names a fix that would not make
    it pass, AND that code is also a tokenizer error in html5lib — so the
    curation filter's premise ("all codes in the set ⇒ tree errors") is unsound
    for it. A selection rule that is subtly wrong keeps selecting the wrong
    cases silently.

Ruling (Task B, upgrading a Minor to the fix round): The reviewer scored
`conformance.csv`'s `parse_errors` column changing meaning as Minor. Decided:
upgrade it and fix now. The column is now fed from the tree-builder count where
it previously held the tokenizer's — same name, different semantics, no second
column — so every row written before today is incomparable with every row
written after. For a project whose stated purpose is a data analysis built on
emitted metrics, a longitudinal dataset silently changing what a column means
is not a Minor; it is the dataset quietly becoming wrong. Fix: a separate
column for each count, named unambiguously. — Cost if wrong: one extra column
in a gitignored generated artifact.

Task B: fix round 1/5 dispatched — the three Importants, the upgraded CSV
  column, the unlisted `unexpected-start-tag` gap (under-reported 33x and
  absent from the report's accounting; an unlisted gap is the one nobody
  returns to), and a measurement: whole-corpus agreement across all 57 files,
  which the reviewer estimated at 388/474 without measuring. tests1.dat alone
  is what let Important 2 hide, so the honest denominator matters.
Task B: fix round 1/5 → commit 85b914e. All six items addressed. 5119 passed,
  59 xfailed. Conformance UNMOVED at 759/1592, 64/112 — the in_body DOCTYPE
  guard did not shift it because that mode already ignored DOCTYPE tokens,
  only silently.
  WHOLE-CORPUS MEASUREMENT (the number I asked for): all 57 files, 474 curated
  cases — 404 agree, 49 emit a code the corpus does not expect, 27 expect a
  code we never emit, 6 in both. tests1.dat alone reads 48/52. So the narrow
  set was flattering by roughly seven points, which is precisely why it hid the
  heading mapping bug. 85% whole-corpus is the honest denominator for this task.
  Verified by me: in-body DOCTYPE recorded; `<p></h3>foo` emits
  `end-tag-too-early`; frameset inputs invent no errors; CSV now carries
  `tree_parse_errors` and `tokenizer_parse_errors` as separate named columns.
  The tree improvement is real and now stated accurately:
  `<head><!DOCTYPE html><title>t</title></head>` used to put <title> in <body>
  and now keeps it in <head>.
  Residual `unexpected-start-tag` gap is 3, listed by case (<head> outside "in
  head", the form element pointer, foreign content) rather than left as a
  number.

Task B: scoped re-review dispatched (opus) over 9d71ebb..85b914e. Directed
  hardest at the implementer's own flagged concern, which I share: `<frameset>`
  needed two exemptions and that required new parser state,
  `_after_head_fallthrough` — a token-identity marker compared with `is`. THIS
  IS A TASK ABOUT RECORDING ERRORS THAT HAS ADDED STATE TO THE PARSER. Asked
  whether it can affect tree construction under ANY input rather than merely
  whether conformance happens to be unmoved; whether identity comparison is
  sound when tokens are re-dispatched across modes; whether it leaks between
  documents; and whether the same accounting is reachable without parser state.
Task B: re-review — all 6 ADDRESSED, no Critical/Important breakage.
  `_after_head_fallthrough` CANNOT affect tree construction: the reviewer
  traced one reader, one caller, whose only consequence is `_error` appending
  to a list and bumping a counter — no path to the stack, insertion point, mode
  or tokenizer. Identity comparison sound (`dispatch` forwards the same object;
  nothing re-enters `_mode_after_head` from inside `in_body`, so no set/clear
  pair can nest). No cross-document leak. Both frameset exemptions measured
  load-bearing: neither → 398/474 with 7 invented errors; after-head only →
  403; in-frameset only → 398.
  The heading-asymmetry argument was settled BY MEASUREMENT rather than by
  reading html5lib, which is not installed: flattening the heading family loses
  tests19.dat:22, flattening li/dd/dt loses tests1.dat:103 — each loses one and
  gains none, so the corpus discriminates both ways and neither family is
  mis-mapped. The implementer's reasoning was right.
  Correction to a number I had been repeating: the corpus is 60 `.dat` files,
  not 57. The extra three are under `scripted/` and contribute zero curated
  cases, so no figure changes — but "all 57 files" was imprecise.
  New Minors, both folded into round 2: `tokenizer_parse_errors` is always 0 on
  the CSV's exception row (Counter default; `build()` raised before the line
  that populates it) — same defect class as the column-meaning issue I upgraded
  last round, since a wrong number in a dataset is worse than an absent one;
  and the flag clear is not in a `finally`.

Ruling (Task B, taking the reviewer's refactor suggestion): The reviewer
established the instance state is safe, then proposed replacing it with a
parameter (`dispatch(token, from_mode=...)`) as "strictly better and cheap".
Decided: take it. State that exists only to carry a fact one level down has a
lifetime, a leak surface and a clear-on-exception obligation; a parameter has
none of those, and it makes the missing-`finally` Minor moot rather than
requiring a second fix. Behaviour must stay identical — both exemptions remain
and `<body><frameset>` must still report, since it is structurally identical to
the exempt case and provenance is the only thing separating them. Instruction
includes: if the parameter costs more than the state it removes, say so and
leave it — I want the simplification, not a refactor for its own sake.
— Cost if wrong: one round late in a task that is otherwise finished.

Task B: fix round 2/5 dispatched (within the 5-round cap; no rule bent).
Task B: fix round 2/5 → commit 61b84d6. Both items taken. 5119 passed,
  59 xfailed; whole corpus still 404/474; conformance unmoved.
  Parameter shape adopted: `dispatch(token, from_mode=None)` at eight
  re-dispatch sites, read by `_frameset_in_body`. Instance state now has ZERO
  occurrences. Verified by me: both exempt frameset inputs report nothing,
  `<body><frameset>` still reports `unexpected-start-tag`.
  The implementer says the prior review UNDER-classed the missing `finally`.
  The reviewer called it "latent only" and concluded there was no
  cross-document leak; the implementer reports an exception mid-fall-through
  left the flag set and would have suppressed the NEXT document's frameset
  error — a cross-document leak on the exception path specifically. If that is
  right, the parameter was a genuine bug fix rather than tidying. Routed to the
  re-reviewer to adjudicate, in both directions: an implementer overstating the
  severity of a defect it fixed is also worth catching.
  Crash row now reads `builder.tokenizer.metrics["parse_errors"]` directly;
  demonstrated on a forced-raise builder (stale 0 vs true 1). `tree_parse_errors`
  deliberately left alone with reasoning commented at the site: `_error`
  increments it as errors happen, so it degrades to a partial-but-real count
  rather than a stale zero. That distinction is worth preserving and worth a
  reviewer's eye, since a future reader may "fix" the asymmetry.
Task B: round-2 scoped re-review dispatched (sonnet), directed at the leak
  dispute, at whether all eight `from_mode` sites pass the mode they actually
  came from (a wrong value would change error reporting on inputs no test
  covers), and at whether the CSV asymmetry is documented well enough to
  survive.
Task B: round-2 re-review — both items ADDRESSED, no new breakage. All eight
  `from_mode` sites checked individually: each names the mode it actually left,
  `_in_body_start` correctly FORWARDS a received `from_mode` rather than
  hardcoding "in_body" (which is what preserves the after-head exemption), and
  the `None` default is used only by true top-level entry. The CSV asymmetry
  holds and is documented at the site.

Ruling (Task B, adjudicating the leak dispute AGAINST the implementer): The
implementer claimed the missing `finally` was a cross-document leak — an
exception mid-fall-through leaving the flag set and suppressing the NEXT
document's frameset error. The re-reviewer adjudicated against it and I
verified independently: every construction site builds a fresh TreeBuilder per
document (`parse()` is literally `TreeBuilder(source).build()`, plus
conformance_report.py:55 and each test), and `build()` contains no try/except,
so an exception propagates and takes the instance with it. A stuck flag could
never reach a second document, because the second document always gets a fresh
`__init__`. Decided: the prior review's "latent only" stands, the correct
framing is "latent design smell", and the record says so. The parameter
refactor remains worth having — it removes a clear-on-exception obligation —
but it was tidying, not a bug fix, and the report's framing is corrected.
— Cost if wrong: the record would credit a refactor with fixing a bug that
never existed, which is exactly the kind of thing that later gets cited as
precedent. Verified three ways before deciding.

Note on the adjudication itself: I asked for this to be checked in BOTH
directions — an implementer overstating the severity of a defect it fixed is
as worth catching as a reviewer underrating one. It went the second way. Had I
only asked "was the reviewer too lenient?", the overstatement would have stood.

Task B: complete (commits 42a50f7..61b84d6, review clean). 5119 passed,
  59 xfailed. Whole-corpus error agreement 404/474 (85%); tests1.dat 48/52.
  Conformance unmoved at 759/1592, 64/112 throughout — this task changed what
  the parser RECORDS, not what it builds, with one deliberate exception: the
  in_head DOCTYPE guard, which is a spec-correct tree improvement.

Task C: implementer DONE, commit 93f2754 (base 61b84d6). 5179 passed, 60
  xfailed (+60 tests, +1 xfail, no existing ledger entry flipped).
  CONFORMANCE 759/1592 -> 780/1592, set difference +21 / -0 (18 doctype01,
  quirks01.dat:0, tests6.dat:4, tests6.dat:46). doctype01.dat 18/37 -> 36/37.
  tests1.dat unchanged at 64/112. Whole-corpus error agreement still 404/474
  with a byte-identical disagreeing set, so Task B's work is undisturbed.
  Three `quirks_mode` writers converted, INCLUDING the fall-through Task B
  added — the one that would have raised AttributeError. Ruling P1 (run B
  before C, let C's grep find it) is validated: the mechanism worked exactly as
  the ruling predicted.
  Prefix count: 55, matching the plan, verified against whatwg/html source AND
  html5lib's tuple — 0 missing, 0 extra. My transcription was right.

TWO ERRORS IN MY PLAN AND ONE FALSE CLAIM IN MY DISPATCH, all caught here:
  (a) The plan's test expected `-//W3C//DTD HTML 4.0//EN` -> quirks. That is
      HTML 4.0 STRICT, absent from the spec list, so `no-quirks`. My test was
      wrong; corrected.
  (b) MY DISPATCH ASSERTED that the 4.01 Frameset/Transitional pair appears in
      both QUIRKS_PREFIXES and QUIRKS_UNLESS_SYSTEM_ID, and called the ordering
      "load-bearing". False: the plan's table lists `4.0`, never `4.01`. The
      inner branch was therefore unreachable dead code, and BOTH 4.01 unit
      cases would have classified as no-quirks. The implementer rewrote it as
      its own clause. Verified: `4.01` now sits at treebuilder.py:282-283 in a
      separate block commented as "the hinge of the whole table", and all four
      classifications come out right.
      I have now been wrong about this table twice — once in the plan, once in
      the dispatch that was supposed to guard the plan. Routed to review with
      that stated, so the reviewer checks the rewrite rather than trusting my
      description of what needed rewriting.
  (c) Spec nuance the implementer surfaced: the spec keys the system-identifier
      condition on "missing OR the empty string", where html5lib tests
      `is None`. Routed for a judgement on which we follow and whether any
      corpus case discriminates.

Task C: review dispatched (opus) over 61b84d6..93f2754. Also directed at the
  DocumentType serialization change — every conformance number flows through
  `serialize()`, so a wrong format moves the score for the wrong reason — and
  at verifying the +21 as a set difference rather than a total, since an
  equal-sized swap shows the same delta.
Task C: review returned spec ✅, quality APPROVED. 0 Critical, 0 Important,
  3 Minor. The strongest verification of the run: the reviewer fetched the LIVE
  SPEC and extracted the lists mechanically — 57 "starts with" bullets, the two
  4.01 entries in their own "missing or the empty string" sub-clause, leaving
  exactly 55 unconditional, matching QUIRKS_PREFIXES with 0 missing, 0 extra,
  0 dupes. Confirmed no bare `-//W3C//DTD HTML 4.0//` entry exists, so the
  4.0-Strict correction is right, and that the rewritten 4.01 clause ordering
  is equivalent to the spec's since the 4.01 strings are disjoint from every
  prefix in the 55-list.
  It validated +21 by running conformance_report.py against a `git archive`
  extract of 61b84d6 in /tmp (repo untouched): 21 newly passing, 0 newly
  failing, exactly the reported ids — a set difference, not a total, so an
  equal-sized swap could not have produced it. Parse-error agreement
  re-measured on BOTH trees: 404/474 either side, disagreeing-id lists
  byte-identical.
  Serialization checked against real fixtures rather than the report:
  system-only, public-only, the IBM system id, and the empty name.
  On the spec-vs-html5lib divergence: our implementation follows the SPEC
  (`if system:`), html5lib's `is None` is the divergent one, that is the right
  call, and no corpus case discriminates — no 4.01 Frameset/Transitional
  DOCTYPE exists anywhere in the vendored corpus.
  doctype01.dat:30 confirmed to be in the BASE failing set, differing only by a
  retained leading "\n" — attribution to the pre-existing character-token
  splitting gap is correct, not a Task C defect parked under someone else's
  cause.

Ruling (Task C, two Minors into a fix round against process default): The
review found nothing Critical or Important, so the default is to complete the
task and defer all three Minors to the final review. Decided: do two now.
  (a) 850 DOCTYPE tokenizer-corpus cases are unenforced, and the fifteen new
      states already score 838/850 against them with all 12 misses being the
      known NUL deviation. Those states' error text currently rests on a manual
      spot-check. EVERY time this project has widened a test denominator it has
      found a real bug — Phase 1's <xmp> defect was invisible to tests1.dat, and
      so was Task B's heading mapping bug, which only surfaced once the whole
      corpus was measured. The marginal cost now is one STATE_NAMES entry plus
      an expected-failure list; deferred, it costs re-acquiring all this
      context, and coverage nobody comes back to is coverage that never happens.
  (b) The comment above QUIRKS_UNLESS_SYSTEM_ID contradicts the spec it cites —
      the note DOES apply to those clauses. Code right, rationale wrong. That
      is precisely the shape that bit us repeatedly in Phase 1: a correct
      implementation with a comment inviting a future "fix".
— Cost if wrong: one extra round on a task that was already approved.

Task C: fix round 1/5 dispatched (also folding in a one-line `Literal` for
  Document.mode and a docstring note that the iframe-srcdoc and
  cannot-change-mode gates are deliberately absent).
Task C: fix round 1/5 → commit a99c742. All three Minors done. Suite 5179 →
  6024 passed, 60 → 72 xfailed. Conformance unmoved at 780/1592, 64/112 with a
  byte-identical failing set; parse-error agreement unmoved at 404/474, also
  byte-identical.
  DOCTYPE corpus adopted: 843/855 pass, 12 failures, and the count NOT
  attributable to the NUL deviation is ZERO — all twelve are literal U+0000
  where the spec wants U+FFFD, all in test3.test, each xfail(strict=True) with
  the cause named. Nothing new surfaced, which is itself the finding: the
  fifteen new DOCTYPE states hold up against 855 cases they had never seen.
  Two things the implementer did that are better than what I asked for:
  (a) It reconciled a count discrepancy rather than papering over it — it
      measures 855/843 where the reviewer said 850/838, and traced the 5-case
      gap entirely to the PASSING denominator (it globs all fixture files).
      Both readings agree exactly on the 12 failures.
  (b) It reports the selection rule keys on the EXPECTED output rather than the
      input, so a case where we wrongly fail to emit a DOCTYPE is still
      selected and still fails — the rule cannot hide our own defects. And it
      measured the rule's one hole (six `<!d` bogus-comment cases; five pass,
      the sixth fails on the same NUL deviation) and named it in a section
      comment rather than absorbing it into the ledger.
  On Minor 2 it said plainly "you were right and my comment was not", then
  produced a better rationale than either of us had: the spec's note forbids
  "missing" from widening to "missing or empty", which is WHY those two clauses
  say "or the empty string" explicitly and why the code tests truthiness.
Task C: scoped re-review dispatched (sonnet) over 93f2754..a99c742, directed at
  the count reconciliation (an inflated denominator would flatter the pass
  rate) and hardest at whether the selection rule can hide our own failures —
  this project was already bitten by an unsound selection premise in Task B,
  and a rule that quietly excludes our defects is the worst outcome available.
Task C: re-review — all three ADDRESSED, no new breakage. The re-reviewer
  reproduced 855/12 from scratch with a per-file breakdown (domjs=1, test1=5,
  test2=15, test3=824, test4=10) and confirmed every selected case genuinely
  qualifies, so the denominator is not inflated. It fetched the WHATWG spec
  source and confirmed the rewritten rationale VERBATIM: the two 4.01 clauses
  literally say "missing or the empty string", and the trailing note sits under
  both lists. And on the question I cared most about, it did a real cross-check
  rather than an assertion: an INPUT-keyed selection alternative yields the
  identical 855 today, so the expected-output rule cannot currently be hiding
  our own failures. The 6-case `<!d` hole confirmed exact; the 12 xfail keys
  all unique with 0 stale.
Task C: complete (commits 61b84d6..a99c742, review clean). 6024 passed,
  72 xfailed. Conformance 780/1592 (up from 759 at task start), error
  agreement 404/474.

Phase 2 cleanup block: A, B, C done. D (DOM cascade affordances) is the last
before the CSS chain E-J begins.

Task D: implementer DONE, commit 9d821e1 (base a99c742). 6033 passed,
  72 xfailed. Conformance unmoved 780/1592, 64/112; error agreement unmoved
  404/474.
Task D: review returned spec ✅, quality APPROVED. 0 Critical, 0 Important,
  1 Minor. Verified: the cache contract IS written at the site with both the
  safety condition and the first future mutator's obligation; `_class_list` is
  per-instance so no cross-element leak; `annotate_positions` is idempotent and
  a node inserted after annotation carries `element_index = None` — the typed,
  tested default rather than a silent stale int; Task C's work is byte-identical
  outside this diff's hunks; and both wrong-implementations I named do fail
  (`split(" ")` breaks the two-space case, counting all children breaks both
  the indices and the count assertion).
Task D: minor (deferred): `annotate_positions`'s docstring lacks the
  re-run-after-mutation note that `class_list`'s docstring has. Genuinely
  deferrable — the failure mode is a typed, tested `None`, not a silent wrong
  value — so this one goes to the final review rather than a fix round. I have
  ruled several Minors INTO fix rounds this phase; this is what the other side
  of that judgement looks like.
Task D: complete (commits a99c742..9d821e1, review clean).

Ruling (new Task K, taking the reviewer's scoping call but not its filing): The
reviewer judged the missing whole-corpus parse-error script a standalone
follow-up — not Task D (which touched zero parsing code, so fixing it there is
scope creep) and not forced into Task E. I accept that scoping entirely. But it
filed the item as "deferred/backlog", and I am instead adding it to the plan as
**Task K**, runnable any time after B. Reason: three consecutive tasks have had
to reproduce 404/474 with throwaway /tmp scripts, and this is the identical
situation Phase 1 hit — a measurement sitting uncommitted, its numbers flagged
unverifiable, which is the whole reason `scripts/conformance_report.py` exists.
Deferred lists work for defects someone trips over; they do not work for
infrastructure nobody hits organically. A number that guards regressions with
no committed tool stops being checked the first time someone is in a hurry.
— Cost if wrong: one small task nobody strictly needed this phase.

Phase 2 cleanup block COMPLETE: A, B, C, D. Conformance 759 → 780 across it;
suite 5051 → 6033 passed. The CSS chain E-J begins now.

Task E: implementer DONE, commit 34d671f (base 9d821e1). 6076 passed,
  72 xfailed (+42 cssparse, +1 environment guard). Conformance unmoved.
  `tinycss2` gone from requirements.txt, absent from src/ except as docstring
  statements of the rule, and — better than asked — ENFORCED by
  `tests/test_environment.py::test_no_forbidden_css_libraries_in_the_engine`.
  An enforced rule beats a documented one.
  It correctly did NOT uninstall the package from `.venv/`, noting my
  prohibition on touching the venv covers uninstalls too. Right call: the rule
  is about what `src/` imports, not what happens to be present.
  It also spotted an uncommitted `docs/plans/...` modification that was MINE
  (the Task K row) and left it alone rather than folding it into a cssparse
  commit. Committed separately at 64332a5.

FOUR MORE ERRORS IN MY BRIEF, all caught and argued:
  1. `\000026 x` is `Ident("&x")`, not `"&"` — the six-digit escape consumes
     the trailing space and the ident continues. Verified.
  2. My round-trip test's first assertion was
     `assert not CssTokenizer(src).errors or True` — a tautology TWICE over:
     `X or True` is always true, and `.errors` is empty before `tokenize()`
     runs anyway. I wrote a test that could not fail, in a plan whose own
     self-review section warns about exactly that.
  3. `EOF` cannot be both the sentinel and a token class, as my brief had it.
  4. My `_consume_url` sketch was not §4.3.6 and accepted `url(a b)`. The
     implementation produces `BadUrl` plus a recorded error, which is
     spec-correct. Verified.

Task E: review dispatched (opus) over 9d821e1..34d671f. Two things routed
  specifically: (a) `tokenizer.py:65` documents a place where a spec-correct
  implementation DISAGREES with tinycss2 — asked which is actually right, since
  a wrong call there is invisible today and becomes load-bearing the moment the
  parser is built on it; (b) the report claims token-for-token verification
  "against an independent implementation" — asked what that reference was. If
  it was tinycss2 from the venv, that is legitimate (verify against a
  reference, do not ship it) but must not have leaked into src/ or the
  committed tests, and it colours how (a) should be read.
Task E: review returned spec ✅ (all of §4.3 plus §3.3, in spec order,
  branch-for-branch), quality APPROVED. 0 Critical, 1 Important, 6 Minor.
  - Important: a spurious `_error("whitespace inside unquoted url")` on the
    `url(a b)` bad-url path. §4.3.6 designates a parse error only for the EOF
    sub-case, so `css_parse_errors` counts a non-error — and the deviation is
    absent from the numbered docstring list. This directly poisons TASK K,
    which I added last task to commit a whole-corpus parse-error measurement: a
    wrong baseline is worse than no baseline.
  - All three of my discrimination probes came back "the tests would fail" —
    `Url` vs `Function` is asserted by isinstance on both url tests plus three
    more, `\26` rejects literal characters, and `1e3` rejects both
    `Dimension(1, "e3")` and deriving the integer flag from the value.

ADJUDICATED: the tinycss2 divergence is OURS-CORRECT. Verified both halves
independently — §4's enumerated token list has no
`<substring-match-token>`/`<column-token>` family, and tinycss2's
tokenizer.py:188-196 emits `LiteralToken` for them, verbatim 2014-CR behaviour
it never updated. CONSEQUENCE FOR TASK G: it must join two delims to parse
`~=`, `^=`, `$=`, `*=`, `|=`. Carry that into G's dispatch.
The reviewer also spot-checked the two neighbouring claims most likely to be
wrong and both held, including that deviation 2's example genuinely uses U+00A0
— had it been U+00B7 the claim would have been false.

ADJUDICATED: using tinycss2 as an oracle from /tmp was SOUND. Consulting a
reference is not shipping one; nothing leaked; `tests/test_environment.py`'s
regex is anchored `^\s*(?:import|from)\s+` precisely so the rule-stating
docstrings do not trip it. The decisive point, in the reviewer's words: the
divergences it surfaced were adjudicated against the spec rather than absorbed.

OPERATIONAL NOTE — DO NOT `pip uninstall tinycss2`. It is still installed and
is the oracle Tasks F-I can check themselves against. Removing it closes that
door for the rest of the CSS chain. The rule forbids it in `src/mayshay/`,
which is enforced by test; it says nothing about what may exist in the venv for
verification.

Task E: fix round 1/5 dispatched — the Important plus five cheap items bundled
  because they are all in one file and three get more expensive once Task F
  builds on it: drop the `css_` metric-key prefix (brief-mandated by me, and
  redundant given metrics.py's `stage` column — htmlparse emits bare
  `start_tags`), guard against a second `tokenize()` (Task F is about to
  consume this class and a silent double-iteration would produce nonsense),
  correct deviation 7's "the one place" count, increment `css_escapes` on the
  U+FFFD paths, and add the missing `isinstance(..., Dimension)` assertion my
  brief omitted.
Task E: fix round 1/5 → commit f3e3d9e. All six items addressed. 6080 passed,
  72 xfailed; conformance unmoved.
  On the Important, the implementer concluded it was a BUG, not an undocumented
  deviation, and removed the call. Its reading: §4.3.6's parenthetical
  "(if EOF was encountered, this is a parse error)" attaches to the EOF
  sub-case only, and the asymmetry is deliberate — the quote/paren/
  non-printable branch and the invalid-escape branch each say "this is a parse
  error" explicitly, while the whitespace→bad-url path conspicuously does not.
  Verified by me across all four exits: `url(a b)` → BadUrl with 0 errors,
  while `url(a"b)`, `url(a\<newline>b)` and `url(abc` each record 1. The signal
  is not lost — `bad_urls` still counts it.
  It also disclosed that THE TEST COVERING THAT PATH WAS PINNING THE BUG: it
  asserted `tk.errors`, i.e. it defended the wrong behaviour. Now asserts the
  absence, with a new test walking all four exits. A test that asserts wrong
  behaviour is worse than no test, because it converts a defect into a
  requirement — routed to the re-reviewer to confirm the replacement genuinely
  discriminates.
  Single-use guard: `tokenize()` is no longer a generator function, so the
  guard fires at CALL time rather than at first `next()` — the right shape,
  since a generator body does not run until iteration and a guard inside would
  raise too late. Raises RuntimeError with a message saying what to do instead.
  Metric keys unprefixed: `parse_errors` now matches htmlparse exactly.
Task E: scoped re-review dispatched (sonnet) over 64332a5..f3e3d9e (excluding
  my intervening docs commit). Directed at an independent reading of §4.3.6 —
  if the implementer is wrong we have just deleted a real error signal AND
  Task K's baseline would be built on the deletion — and at whether making
  `tokenize()` non-generator changed iteration semantics, since laziness was
  load-bearing in the HTML tokenizer for streaming metrics.
Task E: re-review — all six ADDRESSED, no Critical/Important new breakage.
  The reviewer FETCHED the current W3C css-syntax-3 §4.3.6 text and confirmed
  the grammatical binding: the parenthetical "(if EOF was encountered, this is
  a parse error)" is bound only to the EOF sub-clause of the whitespace branch,
  while the quote/paren/non-printable and invalid-escape branches each open
  with a freestanding "This is a parse error." sentence. The implementer's
  reading is right and MY BRIEF'S `_error` CALL WAS THE BUG. Task K's baseline
  is therefore safe to build on.
  My laziness concern was resolved rather than traded away: `tokenize()` is now
  a plain method that checks/sets `_tokenized` and returns the still-lazy
  `_tokenize()` generator — guard at call time, streaming intact.
  Replacement tests confirmed to discriminate: both fail if the deleted
  `_error` call is restored. Metric rename has no blast radius.
Task E: minor (deferred): tokenizer.py:56's docstring still calls `tokenize()`
  "a generator", stale after the `tokenize()`/`_tokenize()` split. Cosmetic.
Task E: complete (commits 9d821e1..f3e3d9e, review clean). 6080 passed,
  72 xfailed. The CSS tokenizer is in: 835 lines, all of §4.3 plus §3.3,
  46 tests, tinycss2 removed from requirements and the ban enforced by test.

CARRY INTO TASK G: `~=`, `^=`, `$=`, `*=`, `|=` arrive as TWO delim tokens.
The current spec has no <substring-match-token>/<column-token> family — that is
2014-CR behaviour tinycss2 never updated — so the attribute-selector parser
must join them itself.

Task F: implementer DONE, commit be569df (base f3e3d9e). 6107 passed,
  72 xfailed (+27 parser tests). Conformance unmoved. Env clean.
  Accounting note, not a discrepancy: its report says "6179 total" counting
  xfails; I count passes. 6107 + 72 = 6179. It also reports its sandbox
  truncates pytest's summary line and used --junitxml instead — that is
  specific to its capture, not the repo; my runs show the summary fine.
  THREE OF MY TEN BRIEF TESTS PASSED AGAINST WRONG IMPLEMENTATIONS — naive
  at-rule skipping, first-`}` block truncation, and adjacent-only
  `!important`. It found this by running the discrimination check I asked for,
  and added 17 tests to pin them. Verified by me: at-rules are consumed with
  their block retained, nested braces survive, `! important` with a space
  still parses as important, and a malformed declaration drops only itself.
  This is the same failure mode as Phase 1 Task 3 and Task E — my hand-written
  tests keep asserting things a wrong implementation also satisfies.
  Brief underspecified in two places, both now documented as deviations: no
  type given for a block's representation (chose a contents-only flat token
  list) and no behaviour given for a nested at-rule inside a declaration list
  (chose consume-and-discard). Both routed to review for a spec judgement —
  the flat list loses bracket structure, and Tasks G and I are the ones who
  would discover that mattered.
Task F: review dispatched (sonnet) over f3e3d9e..be569df, directed at those two
  decisions, at whether the 17 new tests actually discriminate (a test added to
  close a discrimination gap that itself fails to discriminate is the worst
  outcome available), and at the recovery paths the tests may not reach — an
  unclosed block at EOF, a stray `}`, a declaration value containing a block,
  a `;` in a block prelude, an at-rule terminated by `;`. §5 never fails to
  parse, so any input that raises is a defect.
Task F: review returned spec COMPLIANT (all §5 algorithms, empirically
  stress-tested against stray `}`, unclosed block at EOF, the
  at-rule-vs-qualified-rule EOF asymmetry, nested brackets, `;` in prelude and
  value — none raise), quality needs one fix. 0 Critical, 1 Important, 2 Minor.

THE FINDING I ASKED IT TO HUNT FOR, AND IT FOUND IT: the test added to close a
discrimination gap does not itself discriminate.
`test_unknown_at_rule_is_fully_consumed_not_skipped` is named and documented
for the naive-at-rule-skipping bug, but its input
`"@weird foo; bar { a: b } p { color: red }"` never puts a `;` inside an
at-rule's BLOCK — the at-rule terminates at top level and comes back with
`block=None`, so the buggy path is never exercised. Verified by me: that input
yields AtRule(block=False) + 2 QualifiedRules, while
`"@weird foo { a: b; c: d } p { color: red }"` yields AtRule(block=True) + 1,
which is where naive skipping actually breaks.
The reviewer proved it by INJECTION, not inspection: it shadowed a scratch copy
via PYTHONPATH (never touching .venv/) and ran the suite against each of the
three named wrong implementations. First-`}` truncation caught; adjacent-only
`!important` caught by five tests; naive at-rule skipping caught by NONE — all
27 passed.
That technique is now the standard for this project when a test's
discriminating power is in question. "Does this test fail against the bug it
names?" is answerable by experiment and has been answered wrongly by assertion
three times now.

Also adjudicated: the flat-token-list block is a reasonable, harmless
simplification (nothing in §5 needs the tree; structure survives verbatim for
G and I). Discarding a nested at-rule in a declaration list IS a genuine
deviation, correctly flagged. But deviation 2 is MISLABELLED — "block =
contents only, no braces" is exactly what the spec's simple-block `value` field
already excludes, so calling it a deviation would mislead the next reader into
thinking we diverge where we do not. Fix routed.

Task F: fix round 1/5 dispatched — the non-discriminating test (with an
  instruction to CONFIRM the replacement fails against naive skipping rather
  than assume it), the deviation-2 mislabel, and two Minors: `_Cursor._eof()`
  taking position from the last token's start rather than its end on a
  brace-stripped block (positions are a convention this project has been
  careful about), and `_strip_important`'s docstring underselling that it also
  does the spec's unconditional trailing-whitespace strip.
Task F: fix round 1/5 → commit bce132e. All four items done. 6107 passed,
  72 xfailed (unchanged — the fix replaced a test's INPUT rather than adding
  tests). Conformance unmoved; env clean.
  The discrimination was CONFIRMED BY INJECTION, not assumed: a scratch shadow
  of `_consume_at_rule` patched to break on any Semicolon regardless of brace
  depth, run via PYTHONPATH with `__file__` VERIFIED to resolve to the shadow
  first — the test failed `['a','b'] == ['a','b','c','d']` against the bug and
  passes against the real implementation. That `__file__` check is the step
  that makes the experiment trustworthy; without it you may be testing the real
  code and drawing the opposite conclusion.
  The replacement test's docstring now explains its own discriminating power —
  why a naive implementation would end the at-rule at the internal `;` — which
  is a better artifact than the assertion alone, because the next person to
  edit the input can see what it is for.
  Deviation 2 restated as "Note, not a further deviation".
Task F: scoped re-review dispatched (sonnet) over be569df..bce132e. Asked for
  an INDEPENDENT reproduction of the injection — this is the second attempt at
  a discriminating test, the first looked correct and was not, and the whole
  finding is that assertion is not evidence here. Also asked whether the
  replacement is now OVER-FITTED: does it fail against a differently-wrong
  at-rule implementation, or only against this specific one? And whether the
  deviation list is accurate as a whole, since it has now been wrong in BOTH
  directions in this single file — one real divergence undocumented, one
  non-divergence documented as a deviation.
Task F: re-review — items 1-3 ADDRESSED, item 4 NOT clean.
  The reviewer independently reproduced the injection (patched shadow,
  `__file__` confirmed, identical failure) and answered my over-fitting
  question by trying a SECOND, differently-wrong implementation — correct depth
  counting but failing to stop after the block closes. The replacement test
  fails against that too, so it is not tuned to the single injected bug. That
  is a stronger result than the round required.
  Item 4 is NEW BREAKAGE FROM THE FIX DIFF ITSELF: the renumbering that
  correctly demoted deviation 2 to a note was not propagated to three inline
  cross-references. Verified by me, including that all three were correct at
  be569df before this round: parser.py:230 "see deviation 2" now dangles (what
  it describes is the Note under deviation 1); :388 "see deviation 3" should be
  2; :492 "see deviation 6" when the list no longer has six entries. :253's
  "see deviation 1" is still right.
  Naming this plainly because it is the point, not a nuisance: THE FIX THAT
  CORRECTED A DOCUMENTATION-ACCURACY DEFECT INTRODUCED THREE NEW ONES, in the
  file whose numbered-deviation convention exists to prevent exactly that. A
  reference resolving to the wrong entry is worse than no reference — a reader
  follows it and comes away confidently wrong. This one file has now had the
  list wrong in every available direction: a real divergence undocumented, a
  non-divergence documented as a deviation, and references pointing at the
  wrong entries.
Task F: fix round 2/5 dispatched (within cap). Asked it to grep for cross-
  references I did NOT name rather than fixing only the three, and to say so if
  a reference would be more robust as a phrase than a number — renumbering has
  now broken references once and will again.
Task F: fix round 2/5 → commit 48be545. All three stale references fixed; grep
  found exactly six "deviation" mentions and no fourth stale one. Each fixed
  reference now carries the NUMBER PLUS a short parenthetical description —
  answering my "phrase or number?" question with "both", so a future
  renumbering leaves a visibly mismatched label rather than a silently wrong
  one. Re-reviewer confirmed by INSPECTION (each reference resolves to the
  entry its surrounding code actually discusses) rather than by grep, which is
  the check the original defect would have passed.
Task F: complete (commits f3e3d9e..48be545, review clean). 6107 passed,
  72 xfailed. The CSS generic grammar is in: §5's rule and declaration
  algorithms with error recovery, 27 tests, three documented deviations.

Accounting note for the record: several agents report suite totals INCLUDING
xfails (6179) where I count passes (6107). 6107 + 72 = 6179. Same reality; no
discrepancy has ever been chased on this.

Task G: implementer DONE, commit 3c2f5b1 (base 48be545). 6189 passed,
  72 xfailed (+82 selector tests: the brief's 7 verbatim, 65 added).
  Conformance unmoved; env clean.
  FIRST BRIEF OF THIS PHASE WITH NO ERRORS IN IT. The implementer checked all
  ten specificity rows and found them correct, and confirmed `p >> a` rightly
  raises since `>>` was removed from Selectors 4 before CR.
  Whitespace: never stripped, interpreted at exactly ONE site in
  `_parse_complex`'s between-compounds loop. Verified by me: `a b` yields a
  descendant combinator, `ab` is one compound, `a>b` and `a > b` both yield `>`.
  Injection: five bugs shadowed, all five caught — and it DISCLOSED that the
  source-adjacency check did not discriminate until it added the
  `[a~/**/="v"]` comment case, because list adjacency alone already handles
  `[a ~ = "v"]`. That is the injection standard doing its job on the
  implementer's own work rather than on mine.

OPEN QUESTION ROUTED TO REVIEW — the implementer made a choice that was never
settled. It uses SOURCE adjacency (token `pos`) to join the two delims of an
attribute operator, so `[a~/**/="v"]` is REJECTED. Comments are stripped at
tokenization, so those two delims are TOKEN-adjacent but not SOURCE-adjacent,
and the two readings give opposite answers for exactly this input. If
Selectors' adjacency requirement is over the token stream, we are wrongly
rejecting valid CSS that browsers accept — and the test added to pin the check
would be pinning a bug. If it is over source characters, we are right. Asked
for a ruling with the spec text. The whitespace-separated forms are a separate,
easier question and almost certainly invalid.
Also routed: that `Compound`/`Complex` carry `pos` AND it participates in
`__eq__`, so two structurally identical selectors from different source
positions compare unequal — plausible but surprising, and Task H will be
comparing selectors.
Task G: review dispatched (opus) over 48be545..3c2f5b1.
Task G: review returned spec ✅ compliant, quality "approved with fixes".
  0 Critical, 3 Important, 6 Minor, 2 ⚠️.

THE ADJACENCY RULING, and it corrected MY framing rather than the code's.
I asked whether we were wrongly rejecting CSS that browsers accept. The
reviewer read both the spec and two engines and found:
  - By the letter of the spec the rule is over TOKENS. Selectors 4 §16 forbids
    "white space", and a comment is not a `<whitespace-token>`; css-syntax-3 §9
    says preserved comment locations "must have no effect on the parsing step",
    which is exactly what `pos` arithmetic does; and §9's comment-insertion
    table has no `~`/`|`/`^`/`$`/`*` row, so the spec asserts `~=` and `~/**/=`
    tokenize identically.
  - BUT Blink (`css_tokenizer.cc`: `case '~': if (ConsumeIfNext('='))`) and
    Gecko/Servo (`cssparser/tokenizer.rs`: `starts_with(b"~=")`) both lex at
    the CHARACTER level and reject it.
  So the behaviour is BROWSER PARITY, NOT SPEC CONFORMANCE, and my premise
  ("browsers accept it") was false. Decision: keep the behaviour, relabel the
  deviation. The implementer's test pins engine reality, not a bug.
  This is the most valuable single piece of review work in either phase: it
  answered a question I posed badly, checked two independent sources, and
  reached a conclusion neither the implementer nor I had considered.

  - Important 3 BLOCKS TASK H: the selector structures are unhashable
    (`eq=True` without `frozen=True` sets `__hash__ = None`). Confirmed by me:
    `hash(sel("div > p"))` raises TypeError. Task H indexes rules by rightmost
    compound and a dict keyed on compounds is the obvious shape.
  - A real specificity bug found among the Minors: bare `:where` returns
    (0,0,0) where only the FUNCTIONAL `:where()` is zero-specificity. Confirmed.
  - ⚠️ resolved by me: deviation 2's dependency on htmlparse lowercasing holds —
    tag and attribute names come back lowercased, values preserved.
  - ⚠️ routed into the fix: the 156-rule corpus sweep is ad-hoc, so nothing
    guards the strictness divergence we have just decided to KEEP. Asked for it
    committed as a test. Twice this project has had a measurement live in a
    throwaway script and twice had to rebuild it.
Task G: fix round 1/5 dispatched. Also asked it to decide explicitly whether
  `pos` belongs in `__eq__` — it currently does, so structurally identical
  selectors from different positions compare unequal, and Task H is about to
  compare and key on these.
Task G: fix round 1/5 → commit 95919ee. All six items addressed. 6222 passed,
  72 xfailed (+18 selector, +15 corpus tests). Conformance unmoved; env clean.
  `pos` EXCLUDED from `__eq__` via `field(compare=False)`, with `__hash__`
  defined in each class body. The implementer's reasoning, which I endorse and
  which anticipates Task J as well as H: these are VALUES, not stream
  artifacts — `div>p` at offset 0 and at offset 40 are the same selector, and
  having them compare unequal or hash apart is a bug waiting to be written.
  `pos` is still recorded and still drives error messages; it just no longer
  decides identity. Verified: same selector at offsets 0 and 39 now compares
  equal and hashes identically. Side benefit it noted — the tests' `shape()`
  workaround is gone, replaced by direct structural equality.
  Deviation 10 was APPENDED rather than inserted, explicitly so no
  cross-reference renumbers. That is Task F's renumbering breakage becoming
  institutional memory without my prompting.
  Corpus sweep committed as tests/cssparse/test_selectors_corpus.py, extended
  to walk @media blocks: 193 rules (156 top-level, 37 nested), 279 selectors,
  0 rejected, floors at every level. Six injected bugs confirm discrimination —
  INCLUDING an empty-corpus run against a scratch copy, i.e. it tested that the
  test fails when the corpus is empty. That is the Phase 1 lesson
  (`test_tree_corpus_is_not_empty`) applied without being asked.
  It also accepted the adjacency correction plainly: "my report had claimed
  rejecting `[a~/**/=v]` was spec-correct, and it is not."
Task G: scoped re-review dispatched (sonnet) over 3c2f5b1..95919ee, directed at
  the blast radius of the `pos`/`__hash__` change (equal objects must not hash
  apart; simples and compounds must not disagree about whether pos counts), at
  whether every deviation cross-reference still resolves after appending
  deviation 10 — Task F's defect passed a grep while failing inspection — and
  at whether the empty-corpus guard actually works.
Task G: re-review — all six ADDRESSED. Deviation 1's relabel judged an accurate
  REVERSAL rather than softer wording; every cross-reference resolves with no
  renumbering, so appending deviation 10 worked; the empty-corpus guard was
  independently reproduced and fails correctly; hash/eq agree everywhere with
  no equal-but-different-hash cases.
  RESIDUAL FOUND BY THE DEEP-DIVE, and it sits in Task H's path: deviation 10's
  central claim is FALSE for functional pseudo-classes with raw arguments. The
  fix made Compound.pos/Complex.pos compare=False but stopped one level short —
  `PseudoClassSelector.argument` embeds CssTokens, and tokenizer tokens keep
  `pos` in their equality. Confirmed by me:
    'div > p'          equal=True  hash_eq=True   <- claim holds
    ':nth-child(2n+1)' equal=False hash_eq=True   <- it does not
    ':lang(en)'        equal=False hash_eq=True
  Equal-hash-but-unequal is not the catastrophic direction, but it is the one
  that bites a dict: inserting both spellings gives len 2 where it should be 1.
  Task H keys rules by rightmost compound, so the same selector at two offsets
  would occupy two index entries and count as two rules.
  No existing test catches it because every pos-independence test uses plain or
  class compounds, never a raw-argument pseudo-class — the same shape of gap
  the implementer itself found for `[a~/**/=]`: the test covered the feature
  but not the interaction.
Task G: fix round 2/5 dispatched (within cap). Offered three approaches —
  tokenizer-wide `CssToken.pos` compare=False, a custom `__eq__`/`__hash__` on
  PseudoClassSelector, or normalising the argument at parse time — and asked
  for its judgement plus what it ruled out, rather than stating a preference.
  Required: correct deviation 10's text, since it currently states a guarantee
  the code does not provide; and add tests that actually reach the case,
  including a dict-insertion assertion, because the existing tests pass against
  the bug and so are not evidence.
Task G: fix round 2/5 → commit e3ba0a0. 6250 passed, 72 xfailed (+28).
  Conformance unmoved; env clean.
  Took option 2 (`PseudoClassSelector` with explicit `__eq__`/`__hash__` via a
  `_token_key` built from `dataclasses.fields` minus `pos`), and reframed my
  objection correctly: this REMOVES an equality convention rather than adding
  one, because selectors.py had already declared identity excludes offset and
  the inconsistency was one field embedding foreign objects that disagreed.
  Ruled out option 1 on a FORWARD-looking basis, not just present blast radius:
  it checked that nothing compares token objects with `==` today, then rejected
  it anyway because a future `assert toks(...) == [Ident("a", 0), ...]` would
  pass while checking nothing about the positions it names, and because it
  splits cssparse's convention from htmlparse's. Ruled out option 3 because it
  discards positions a later An+B/`:has()` implementation needs and makes
  `argument` stop being the raw token run it promises.
  It found a case the review's list MISSED: `:not(.a)` was affected too — its
  parsed `selectors` is position-independent but the raw `argument` alongside
  it is what equality reaches.
  Bonus beyond the fix: the argument now participates in the hash, so
  `:nth-child(1)` and `(2)` no longer collide — retiring deviation 10's other
  caveat rather than leaving it stale.
  Injection in BOTH directions: restoring the bug fails 15 cases, all in the
  three tests added this round (direct proof the pre-existing tests passed
  against it); and a second injection ignoring arguments entirely is caught by
  two tests, so the fix cannot swing past correct. Testing that a fix does not
  OVERcorrect is a step this project had not taken before.
  Verified by me: all five forms pos-independent, dict len 1 (was 2),
  `:nth-child(1)` vs `(2)` differ in both equality and hash.
Task G: round-2 scoped re-review dispatched (sonnet) over 95919ee..e3ba0a0.
Task G: round-2 re-review — ADDRESSED, no new breakage. `_token_key` verified
  general across ALL 25 token types (the report said fifteen — stale count,
  cosmetic), including Function/LParen/RParen which do appear in raw arguments,
  and confirmed to fail LOUDLY not silently: a hypothetical list-field token
  builds an eq-key fine but raises TypeError on hash(), i.e. a crash rather
  than a wrong answer. Overcorrection check reproduced directly. `__eq__`
  returns NotImplemented for foreign types. "Removes rather than adds a
  convention" confirmed: no Simple leaf carries pos at all; only
  Compound/Complex do, both compare=False. Deviation 10 now states the precise
  token-level guarantee and its stale collision caveat is gone.
Task G: minor (deferred): the report's "fifteen token types" is a stale count;
  there are 25. Cosmetic, in a gitignored report.
Task G: complete (commits 48be545..e3ba0a0, review clean). 6250 passed,
  72 xfailed. Selectors and specificity are in: 768 lines, ~118 tests, a
  committed corpus sweep over 193 real rules, and ten documented deviations.

Phase 2 status: A B C D E F G done. H, I, J remain, plus K.

Task H: implementer DONE, commit 931e741 (base e3ba0a0). 6340 passed,
  72 xfailed (+90: 86 unit, 4 corpus). Conformance unmoved; env clean.
  RuleIndex catch-all: keyless rightmost compounds (`*`, `[hidden]`, `:hover`,
  `:is(.a,.b)`) go to a `_catch_all` bucket seeded FIRST in every
  `candidates()` call, so it is returned unconditionally. A rule whose selector
  cannot be derived at all RAISES rather than landing there silently. Verified.

THREE NON-DISCRIMINATING TESTS IN MY BRIEF, each proven by injection rather
than asserted:
  - `test_rule_index_narrows_candidates` stays green under THREE separate bugs:
    dropping the catch-all bucket, keying on the leftmost compound, and
    ignoring the class bucket. I had warned this test might pass trivially; the
    implementer proved it does, three ways.
  - `test_adjacent_and_general_sibling`'s `p ~ span` also passes if `~` is
    implemented as `+`.
  - "Rule" is never defined in my brief — its own test passes a bare `Complex`
    and no `Rule` type exists. Solved with a `selector_of` hook.

MY DISPATCH WAS WRONG ABOUT CASE SENSITIVITY. I said attribute NAMES fold
while id/class VALUES do not, implying attribute values were case-sensitive.
HTML has a "Case-sensitivity of selectors" list of ~46 attributes (`type`,
`rel`, `lang`, …) whose VALUES compare ASCII case-insensitively in selectors.
Verified by me: `[type="text"]` matches `TEXT`, `[rel="nofollow"]` matches
`NoFollow`, while `[class~="box"]` correctly does NOT match `Box`. Implemented
per spec with both over- and under-correction injected.

Also: An+B is required by `:nth-child(1)` but unmentioned in my brief, and
`selectors.py` deliberately does not parse it — so the entire micro-grammar is
new in this task and reviewed nowhere. Routed to review against §9.2.

Injection: 25 bugs into a PYTHONPATH shadow with `__file__` asserted each run;
all 25 caught, including FIVE over/under-correction pairs. Task G's
both-directions technique adopted and scaled up without being asked.
Honest disclosure worth recording: the corpus test CANNOT guard the catch-all
bucket — not one of the corpus's 279 selectors lands in it — and that limit is
written into the test file's docstring rather than left implicit.
Task H: review dispatched (opus) over e3ba0a0..931e741. Asked for the ~46-attr
  list to be checked against the spec for completeness AND false members (same
  risk class as the quirks table: a missing entry silently mismatches on real
  pages), for the An+B grammar to be checked against §9.2, and — given the
  implementer found three non-discriminating tests — for a fourth.
Task H: review returned spec ✅ compliant, quality APPROVED conditional on one
  test fix. 0 Critical, 1 blocker-grade test defect, 4 Minor.
  ATTRIBUTE LIST EXACT: the reviewer fetched HTML's "Case-sensitivity of
  selectors" and diffed name-by-name — 46 in the spec, 46 implemented, zero
  omissions and zero false members. My dispatch was wrong; the implementer's
  correction is complete. Same risk class as the quirks table, and this time
  the table is right.
  An+B verified: all 31 valid forms correct, 26 of 30 invalid reject to None
  ("never matches", never zero), `_an_b_contains` right on 11 pairs including
  negative `a` and the n>=0 bound.
  Catch-all gap confirmed EXACTLY as disclosed — injecting `found = []` leaves
  all four corpus tests green and fails four fixture tests, so unit coverage
  carries it. An unfindable selector raises with an actionable message.
  Six of 25 injections reproduced, all matching, including a pair that pins
  from both directions.
  Independent validation of TASK D outside this diff: `element_index` agrees
  with a computed sibling index across 8,596 corpus elements, 0 mismatches.

FOURTH VACUOUS TEST FOUND, and this one is the implementer's, not mine:
  `test_matching_corpus.py:141` has a `break` limiting each selector to
  `<html>`. Proven by planting `raise RuntimeError` in the descendant branch —
  the neighbouring sweep caught it, this test passed.
  That is four in one file: three of mine, one of the implementer's. The shape
  is always identical — a test that exercises less than its name implies — and
  it has been caught by injection every time and by reading never.
Task H: fix round 1/5 dispatched — the `break` test, an undisclosed fifth An+B
  leniency (`+-n` → (-1,0)), deviation 6's prose wrongly calling `2n + 1`
  spec-invalid (code right, sentence wrong), `_nth` re-parsing An+B per element
  (pointed: this is the one task whose purpose is avoiding per-element work),
  and pinning more of the 46-entry list including one NON-member so the test
  discriminates membership rather than just confirming the mechanism fires.
Task H: fix round 1/5 → commit 53d6cd4. 6366 passed, 72 xfailed (one test
  deleted, 27 added). Conformance unmoved; env clean.
  TWO DELIBERATE DIVERGENCES FROM MY INSTRUCTIONS, both better than what I
  asked for:
  (a) It DELETED the vacuous test rather than de-`break`ing it, arguing it was
      strictly subsumed by the neighbouring sweep which already calls
      `matches()` on every element × selector pair — and that de-`break`ing
      would re-run an identical loop, doubling corpus runtime, to assert LESS
      than the test beside it. The deleted test's rationale now lives in that
      neighbour's docstring rather than vanishing with it.
  (b) It FIXED `+-n` rather than disclosing it, on a distinction I had not
      drawn: its invalidity survives tokenization (`Delim('+')` then a
      `-`-initial `Ident`), so it was a BUG, not a choice — "and deviation
      lists here are for choices". I asked for a disclosure; it identified that
      the item did not belong in a disclosure list at all. Deviation 6 now
      states that boundary explicitly and names three recoverable-invalid forms
      that all reject.
  Also: deviation 6's `2n + 1` sentence corrected (prose only); An+B memoized
  as deviation 14 at 2.1x on 2000 elements — with the honest caveat that it has
  ZERO corpus effect because the corpus ships no `:nth-*` at all, so the corpus
  cannot regress-guard it; the 46-entry list now pinned from BOTH sides with
  `name`/`href`/`id`/`class` as non-members; ten fresh injections all caught,
  including dropping `rel` from the list and adding `href` as a false member.
  It ALSO self-disclosed that one new parametrized row (`+-n` alone) is
  non-discriminating, marked it so in a comment, and had `+-n+2` carry the
  weight. Disclosing a fifth vacuous test in the file it just cleaned four from
  is the pattern being internalised rather than merely obeyed.
  Verified by me: `+-n`/`+-n+2` never match, `2n + 1` correct, and the 46-list
  discriminates in both directions.
Task H: scoped re-review dispatched (sonnet) over 931e741..53d6cd4. Asked it to
  verify the SUBSUMPTION claim directly — deleting a test because another
  covers it is exactly the reasoning that leaves a gap when wrong — and to
  check the bug-versus-choice distinction holds for ALL FIVE leniencies, since
  if any of the other four are also post-tokenization-distinguishable they are
  bugs too and the list is newly wrong in a different direction.
Task H: re-review — all five ADDRESSED, no Critical/Important breakage.
  SUBSUMPTION CLAIM HOLDS, verified by injection rather than reading: a
  RuntimeError planted in `_match_from`'s descendant branch is caught by the
  surviving sweep, which calls `matches()` on every element × selector pair.
  BUG-VS-CHOICE DISTINCTION HOLDS, and the reviewer checked all five forms
  empirically rather than accepting the principle: `2n + -1`, `+ n` and `+-n`
  each tokenize distinguishably from their valid neighbours (visible negative
  Number, Whitespace, `-`-initial Ident) and were rightly FIXED; `2n 1` and
  `2n +1` are token-identical to each other and rightly remain the ONE
  disclosed leniency. So the implementer's principle was right AND it applied
  it correctly across all five, converting three of the four "leniencies" into
  fixed bugs.
  Memoization verified safe: keyed on `selector._an_b_memo`, and
  `PseudoClassSelector.__eq__`/`__hash__` ignore it, so no collision, staleness
  or behaviour change. The 46-list test now has 16 cases both directions, and
  removing `rel` in a shadow fails exactly the expected row.

Task H: minor (DEFERRED, deliberately): `matching.py:83-84` claims `2n+1`,
  `2n +1` and `2n 1` all tokenize to `Dimension, Whitespace, Number`, but
  `2n+1` with no space produces NO Whitespace token. Confirmed by the reviewer
  against our own tokenizer. Behaviour unaffected — whitespace is stripped
  before comparison — but it is a factual slip IN THE VERY PARAGRAPH the
  previous round was asked to correct.
  That is the THIRD time in this project a documentation fix has introduced a
  documentation error: Task F's renumbering broke three cross-references, Task
  F's deviation list was wrong in both directions, and now this. Recording the
  pattern for the final review rather than fixing it here — I have ruled
  Minors into fix rounds liberally this phase and the discipline is worth
  exercising in the other direction on an otherwise-approved task.
Task H: complete (commits e3ba0a0..53d6cd4, review clean). 6366 passed,
  72 xfailed. Matching is in: 709 lines, ~113 tests, a rule index with a
  catch-all bucket, HTML's 46-attribute case-insensitivity list verified exact,
  and an An+B micro-grammar that never appeared in my brief.

Phase 2 status: A B C D E F G H done. I, J remain, plus K.

Task I: implementer DONE, commit fd15b3e (base 53d6cd4). 6391 passed,
  72 xfailed (+25). Conformance unmoved; env clean.
  THE CRITICAL REQUIREMENT IS MET: `50%` → `Percent(50)`, `auto` → the `AUTO`
  singleton checked by identity, both returned untouched. Verified by me. This
  is the thing that would have stayed invisible until Phase 3 layout was
  already producing wrong boxes.
  Verified by me: `green` = (0,128,0) and `lime` = (0,255,0); border parses in
  all three component orders; shorthand 1-4 correct; invalid values return None
  without taking the rule with them.

TWO MORE NON-DISCRIMINATING TESTS IN MY BRIEF, both proven by injection:
  - the border test exercises only canonical order despite the prose claiming
    "any order" — a fixed-order parser passes it;
  - the colour test checks only `red` despite MY BRIEF NAMING THE GREEN/LIME
    TRAP BY NAME — a swapped green/lime table passes it.
  The second is the sharpest illustration yet of the pattern: I identified the
  exact trap, wrote it into the brief as a warning, and then wrote a test that
  could not catch it. Knowing about a failure mode and testing for it are
  entirely different acts, and this project keeps demonstrating the gap.
  Both gaps closed with supplementary tests, each verified by injection.

  Also: `expand_shorthand`'s `parsed` argument shape was never specified in my
  brief. Inferred list-of-1-4 for margin/padding, dict-of-3 for border — two
  different shapes for two shorthand families, routed to review for a judgement
  on whether that will cause trouble when a third shorthand arrives.
Task I: review dispatched (sonnet) over 53d6cd4..fd15b3e. Directed at the
  COLOUR KEYWORD TABLE as the headline — same risk class as the quirks table
  and the 46-attribute list, one of which was wrong — asking for the spec count
  versus implemented and spot-checks beyond the famous names. Also asked
  whether EVERY percentage/auto-legal property stays symbolic (I only verified
  `width`), and to hunt for a third vacuous test.
  Also routed: `pyproject.toml:15` sets `addopts = "-q"` and TWO separate
  agents have now reported pytest 9.1.1 suppressing the summary line in
  captured output, each spending effort working around it. My interactive runs
  show it fine. Asked whether it is real and capture-dependent and whether `-q`
  is worth keeping, since every future agent will hit it.
Task I: review returned spec ✅ compliant, quality approved with fixes.
  0 Critical, 3 Important, 1 Minor, 1 ⚠️.
  SYMBOLIC GUARANTEE VERIFIED COMPLETELY: width, height, margin, padding and
  font-size all route percentages and auto through `_parse_length_percentage`
  and none resolves eagerly. I had only checked `width`; the reviewer checked
  every property where a percentage or auto is legal.
  - Important 1: the colour keyword table is 22 entries against the spec's
    ~148. All 22 correct with no false members, but skyblue, coral, tomato,
    gold, crimson, indigo and the rest are absent and each absence SILENTLY
    DROPS A DECLARATION on a real page. Unlike the quirks table and the
    46-attribute list — both of which were verified complete — this one is
    genuinely incomplete.
  - Important 2: `expand_shorthand` takes a list of 1-4 for margin/padding and
    a dict of 3 for border. A third shorthand has no home, and Task J is next
    and will lock a convention around whatever is left.
  - Important 3: a THIRD non-discriminating test in my brief —
    `test_display_keywords` checks only "block", so a hardcoded
    always-return-Keyword("block") passes it. The implementer had already
    covered it incidentally via `test_unknown_display_keyword_is_invalid` but
    never credited it as such, unlike the border and colour cases it did call
    out.

RESOLVED — the `addopts` mystery was SELF-INFLICTED and cost two agents effort.
`pyproject.toml`'s single `-q` prints the summary fine, piped or interactive.
It only vanishes when `-q` is STACKED — the ini's plus one typed on the command
line — giving verbosity -2. Normal pytest repeatable-verbosity behaviour, not a
9.1.1 bug, not capture-dependent. That is why my runs always showed it: I never
pass `-q`. Keep the ini setting; the fix is telling agents not to re-pass it.
ADDED TO ALL FUTURE DISPATCHES: run `.venv/bin/pytest` with no `-q`.

Task I: fix round 1/5 dispatched — the full ~148-colour table with a
  transcribe-then-verify-the-count discipline (treat disagreement as a finding,
  not something to quietly match), a decision on the shorthand shape split
  before Task J locks a convention around it, a discriminating
  `test_display_keywords`, and direct tests for padding-percent,
  font-size-percent and currentcolor — all three "correct by inspection", which
  is precisely what the last four vacuous tests also were.
Task I: fix round 1/5 → commit 91e2bfc. 6395 passed, 72 xfailed. Conformance
  unmoved; env clean.
  COLOUR TABLE: full 148 entries transcribed (147 CSS3 + rebeccapurple),
  replacing 22. Verified by me: exactly 148, and every previously-dropping name
  resolves correctly — skyblue (135,206,235), coral (255,127,80), tomato
  (255,99,71), gold (255,215,0), crimson (220,20,60), indigo (75,0,130),
  rebeccapurple (102,51,153), papayawhip (255,239,213). green/lime still right.
  SHORTHAND SHAPES UNIFIED to `dict[str, object]` for every shorthand, with the
  remaining difference — border maps one component to four sides while
  margin/padding map one key to one longhand — documented as a GENUINE CSS
  SEMANTIC DIFFERENCE rather than forced into false uniformity. That is the
  right resolution: unify the container, keep the semantics honest.
  Both fixes carry docstrings explaining WHY they changed and citing the defect
  they replaced, so the next reader sees the reasoning rather than just the
  result.
Task I: scoped re-review dispatched (sonnet) over fd15b3e..91e2bfc. Directed at
  the one thing sampling cannot settle: I checked 8 entries and the implementer
  checked 10, leaving ~130 unverified, and a transcribed table can have the
  right LENGTH and wrong CONTENTS — a single transposed hex digit is invisible
  to every test we have. Asked for programmatic verification of the whole table
  against an authoritative source. Also asked whether the count assertion would
  survive a DUPLICATE KEY, which in a dict literal leaves the length unchanged
  while silently losing an entry.
Task I: re-review — all four ADDRESSED, no Critical/Important breakage.
  FULL-TABLE VERIFICATION, the thing sampling could not settle: the reviewer
  diffed `_COLOR_KEYWORDS` against TWO independent oracles already present in
  `.venv` — `webcolors.names('css3')` plus rebeccapurple, and
  `matplotlib.colors.CSS4_COLORS` — giving 148/148 keys, zero missing, zero
  extra, ZERO value mismatches against either. The table is definitively
  correct and needs no re-checking. Nice extension of the read-only-oracle
  technique to packages installed for unrelated reasons.
  It was also honest about what the TESTS can and cannot guarantee: a
  duplicate-key transcription would land at exactly 148 and slip past
  count-plus-sample unless it hit a sampled name. That limit is closed by the
  oracle diff, NOT by the test — so the guarantee lives in this ledger entry
  rather than in the suite.
  Shorthand shape judged sound from Task J's perspective: J can call
  `expand_shorthand` uniformly without branching on list-vs-dict.
Task I: minor (deferred): `expand_shorthand("margin"/"padding", parsed)` now
  raises a bare KeyError rather than a descriptive ValueError if called
  directly with a partial dict. Unreachable via `parse_declaration_value` and
  no internal caller triggers it. Deferred, consistent with the Task H call.
Task I: complete (commits 53d6cd4..91e2bfc, review clean). 6395 passed,
  72 xfailed. Property values are in: 627 lines, the full 148-colour table
  verified against two oracles, shorthand expansion with a uniform shape, and
  the computed-vs-used guarantee holding across every percentage/auto-legal
  property.

Phase 2 status: A B C D E F G H I done. J remains (the payload), plus K.

Task J: implementer DONE, commit 51b1301 (base 91e2bfc). 6468 passed,
  72 xfailed (+73). Conformance unmoved; env clean.
  THE DEFINING ASYMMETRY IS SOLVED STRUCTURALLY, not carefully:
  `_compute_font_size(…, parent_font_px=…)` has NO own-font-size parameter and
  `_compute_rest(…, own_font_px=…)` has NO parent parameter, so the wrong base
  is not in scope to be used by mistake. Verified: 1.5em under a 20px parent →
  30px; width 2em on a 20px element → 40px.
  Verified by me end to end: specificity beats source order; source order
  breaks ties (green = 0,128,0); !important beats specificity; inline beats
  author rules; color inherits while width does not; text nodes inherit from
  their parent element; UA sheet gives div block and span inline; 50% survives
  as Percent(50) through the whole pipeline.
  METRICS ARE NOW TRUE ENGINE-SIDE FOR THE FIRST TIME: stages.csv holds 84 rows
  across tokenize/treebuild/cssparse under a single run_id, written by
  scripts/style_report.py. That closes Phase 1's ruling C4 and its Known Gap 7,
  which have been open since the first phase.
  THE PHASE 6 MEASUREMENT THE USER ASKED FOR: link_stylesheets_skipped is
  example.html 0, hn.html 1, wikipedia.html 2 — "no styles applied" is now a
  number per page rather than a blank render.
  Second brief this phase with nothing wrong in it. Five items underspecified
  and disclosed, including a REAL inconsistency: `display`'s stored type — my
  own test wants `str` while values.py returns `Keyword`.
  TWO MORE OF MY TESTS ASSERT LESS THAN THEIR NAMES:
  `test_em_font_size_resolves_against_the_parent` uses a single level so
  nothing checks compounding, and `test_source_order_breaks_specificity_ties`
  uses two rules so a per-RULE counter would pass it. Stronger siblings added.
  That is at least ten such tests I have written across this plan.
  Injection: 65 bugs, 65 caught, including over-corrections — up from Task H's
  35 and the largest set in the project.
Task J: review dispatched (opus) over 91e2bfc..51b1301. Directed hardest at
  whether the `em` separation is AIRTIGHT — any path, including inherited
  values, border-width, or a shorthand's expanded longhands, where a length
  could resolve against the wrong base or resolve twice — since that is the
  error the whole task was designed around and it is invisible until Phase 3.
Task J: review returned spec ❌ (edges only), quality "needs fixes; the core is
  excellent". 0 Critical, 3 Important, 9 Minor.
  THE EM SEPARATION IS AIRTIGHT, and the reviewer established it by experiment
  rather than by reading the signatures: 11 adversarial probes covering
  shorthand-expanded longhands, INHERITED font-size, `width` written before
  `font-size` in the same block, inline `style=`, cross-origin author/UA
  mixing, `ex`/`ch`, a double `style_document` call, and a zero-leak sweep
  across all three corpus pages. Injecting the defining error gives 3 failures.
  It also re-ran 7 of the 65 injections across 6 axes — all caught with
  distinct signatures, 3 of them over-corrections — and confirmed ZERO `emit`
  call sites anywhere in src/, with style_report.py passing `--out` explicitly
  rather than leaning on METRICS_DIR's `__file__` derivation. Task A's
  fallback-not-contract design is being honoured by its first real caller.

  `display`'s stored type RESOLVED IN THE IMPLEMENTER'S FAVOUR, and it was
  never an inconsistency: `Keyword` is the SPECIFIED value, typed so
  `display: red` can be rejected; for `display` and `border-*-style` the
  COMPUTED value IS the keyword, so the wrapper adds nothing and costs a live
  trap (`Keyword("block") == "block"` is False). Two stages, both correct.

  - Important 1: SHORTHAND RESET FELL THROUGH A CROSS-TASK GAP. values.py:88-97
    (deviation 7) explicitly delegates it to Task J; Task J's brief never
    mentioned it; nothing implements it. Confirmed:
    `p{border:5px solid red} p{border:solid blue}` leaves border_top_width at
    5px where a browser resets to medium. Task I documented an obligation into
    a void — worth noting as a hazard of documenting handoffs in the SOURCE
    rather than in the receiving task's brief.
  - Important 2: the UA sheet is HALF-APPLIED for tables — `table` gets
    `display: table` while tr/td/th/tbody/caption are all `inline`, which is
    arguably worse than none since the container establishes a context its
    children ignore. Confirmed, and the corpus makes it concrete: hn.html has
    4 tables / 98 tr / 159 td; wikipedia 24 / 120 / 159 / 85 th / 24 tbody.
    The recorded justification (parser does not reliably build tables) is
    CONTRADICTED by the tree — the elements are there. Phase 1's table
    INSERTION MODES are xfailed; that is a different claim from the elements
    not existing, and the reviewer caught the conflation.
  - Important 3: deviation 8's rationale is false — `p{border:solid red}` gives
    0px where browsers paint 3px, because the style IS specified.
  - THIRD under-asserting brief test found: `test_author_rule_beats_ua` passes
    under a TOTAL NO-OP CASCADE, because `inline` is display's initial value.
    It is the only substantive brief test that survives that injection.
Task J: fix round 1/5 dispatched — the three Importants plus three Minors with
  correctness implications (`_computed_value` unwrapping ANY Keyword with no
  allow-list; a test asserting only private rank constants; `root_font_px`
  updating on any orphan element). Four cosmetic Minors explicitly deferred.
Task J: fix round 1/5 → commit 28e067f. All six addressed. 6483 passed,
  72 xfailed (+15). Conformance unmoved; env clean.
  SHORTHAND RESET DONE WITH THE RIGHT SEMANTICS: it participates in the cascade
  at the shorthand's OWN rank, specificity and source order rather than blindly
  overwriting. Verified by me: a later partial `border:solid blue` gives
  3px/solid/blue, while a higher-specificity `#x{border:5px solid red}` KEEPS
  its 5px. A blunt reset would have lost that.
  Full table display set added (table-caption, table-header-group,
  table-row-group, table-row, table-cell, table-column-group, table-column,
  table-footer-group) with the six internal keywords added to values.py, and
  the false "parser doesn't build tables" rationale corrected in place.
  border medium = 3px.
  THE BEST VALIDATION IN THE PHASE, and it is on real input: wikipedia computes
  22 tables to `table` and 2 to `block`, 157 `td` to `table-cell` and 2 to
  `none` — author CSS overriding the UA sheet on a real document. No fixture
  demonstrates a working cascade as convincingly.
  Metrics effect measured rather than assumed: rules_total +9 and
  declarations_kept +8 per page, declarations_dropped UNCHANGED at 3/4/313
  (confirming the new UA rules all parse), link_stylesheets_skipped still
  0/1/2.
  Injection honesty worth recording: 20 more bugs, 19 caught. Two first-pass
  SURVIVORS were real test gaps and were closed; one was a malformed mutation,
  replaced and then caught; one is documented as SEMANTICALLY DEAD rather than
  counted as coverage. Reporting survivors and refusing to pad the count is the
  behaviour this whole review discipline is trying to produce.
Task J: scoped re-review dispatched (sonnet) over 51b1301..28e067f. Directed at
  the shorthand reset's rank in orderings I did NOT test — `!important`
  shorthand vs normal longhand and the reverse, inline `style=` vs author, UA
  vs author, and same-specificity ordering — since getting the simple case
  right and `!important` wrong is exactly the shape that survives a fix round.
  Also: whether adding six keywords made `display` MORE PERMISSIVE as a side
  effect, and whether the "semantically dead" mutation label is accurate — a
  mutation that cannot change behaviour is legitimately uncatchable, but that
  label is also the obvious place to hide one that simply was not caught.
Task J: re-review — all six ADDRESSED, no new breakage. The reviewer executed
  four `!important`/inline-vs-author shorthand-reset orderings directly against
  the installed package and all matched browser cascade semantics — CONFIRMING
  the rank/index propagation is sound EVEN THOUGH the fix's own suite does not
  cover the `!important` axis. It confirmed `display` widened only by the six
  legitimate internal table values plus `inline-table`, with `_parse_display`'s
  validation untouched so invalid keywords are still rejected. And it traced
  `values.py` to establish the "semantically dead" mutation label is ACCURATE:
  `border-*-style` can only become non-`none` via the `border` shorthand, which
  always forces the width reset, and `_zero_widths_of_borderless_sides` runs
  unconditionally, so that field default is genuinely unreachable. The metric
  arithmetic reconciles against the one-rule-per-selector design.
Task J: minor (deferred): the `!important` shorthand-reset axis is CORRECT but
  UNCOVERED by the suite — verified once by a reviewer, not pinned by a test.
  Behaviour that is right by inspection and untested is exactly what this
  project has repeatedly found to rot; flagging for the final review.
Task J: complete (commits 91e2bfc..28e067f, review clean). 6483 passed,
  72 xfailed. The cascade is in: 878 lines, a UA stylesheet, 88 cascade tests,
  85 injections across two rounds, and computed styles on every node of a real
  page.

Phase 2 status: A B C D E F G H I J done. K remains, then the final
whole-branch review.

NOTE on Task K's requirements: I added K to the plan's execution table but
never wrote it a full task section, so there is no brief to extract. Its
requirements live in the dispatch instead. That is a deviation from this
project's plan-is-the-spec discipline, recorded here rather than glossed —
proportionate for a ~100-line script mirroring one that already exists, but
worth knowing if K's scope is ever disputed.

Task K: implementer DONE, commit fa8bd23 (base 28e067f). Suite unchanged at
  6483 passed, 72 xfailed; conformance unmoved; env clean.
  `scripts/error_report.py` reproduces 404/474 EXACTLY, with the two divergence
  counts kept separate as Task B required: 49 emitting a code the corpus does
  not expect, 27 where the corpus expects one we never emit.
  `--diff` gating verified BY INJECTION rather than by reading: it disabled one
  `_error` call in treebuilder.py, agreement dropped to 392/474, `--diff`
  reported 17 newly-disagreeing cases and exited 1 (confirmed via `$?`), then
  reverted and confirmed byte-identical restoration and 404/474 again. A gate
  tested only in its passing direction is not a gate, and this one was tested
  in both.
  Curation logic NOT duplicated: `curated_codes()` extracted once into
  tests/htmlparse/test_parse_errors.py:102 and imported by the script, so the
  measurement and the pytest test cannot drift apart. That was the priority
  requirement — a second copy producing an authoritative-looking number that
  disagrees with the tests would have been worse than no script.
  This closes a gap open since Task B: three tasks reproduced 404/474 in
  throwaway /tmp scripts, and Phase 1 hit the identical situation, which is why
  scripts/conformance_report.py exists at all.
Task K: review dispatched (sonnet) over 28e067f..fa8bd23. Flagged one design
  point I noticed myself: `scripts/` now imports from `tests/`
  (error_report.py:45), which avoids duplication but inverts the usual
  dependency direction and couples a script to a test module's import side
  effects. Asked for a ruling either way — move `curated_codes` to
  tests/support/, or say plainly the coupling is fine so nobody churns it
  later. Also asked for the `--diff` failure direction to be REPRODUCED, and
  for confirmation the 45-line extraction is behaviour-preserving: a curation
  predicate that shifted would silently change which cases are measured while
  the headline number stayed plausible.
Task K: review returned spec ✅ compliant, quality approved with one Important
  fast-follow. `--diff` gate REPRODUCED INDEPENDENTLY (same regression, 392/474,
  5 newly agreeing / 17 newly disagreeing, exit 1, byte-identical revert, suite
  green). Curation extraction confirmed behaviour-preserving by branch-by-branch
  comparison. 404/474 reproduced from scratch.
  DEPENDENCY RULING, more precise than my flag: `scripts/` importing `tests/`
  is NOT wrong — conformance_report.py already imports tests.support.dat, so
  that direction has precedent. What is wrong is importing from a `test_*.py`
  file specifically, which drags in `import pytest` and that module's eager
  `_curated_cases()` parametrize-building as import side effects. A measurement
  script should not need pytest installed or pay for test collection to run.
  `tests/support/` is the right home. That is the distinction I could not make
  from here and it is the correct one.
Task K: ⚠️ that cannot be resolved, and it makes the case for the task better
  than I did: the reviewer could not confirm whether Task B's original
  throwaway script treated a TreeBuilder crash as landing only in the "missing"
  bucket, because THERE IS NO SURVIVING ARTIFACT to compare against. The
  earlier measurement is gone, so its conventions are unknowable. That is
  precisely the cost of leaving a measurement uncommitted — asked for the new
  script's crash-handling convention to be stated in its docstring so the next
  person does not have to guess at ours the way we now guess at Task B's.
Task K: fix round 1/5 dispatched — move `curated_codes`/`_strip_position` into
  a pytest-free `tests/support/parse_errors.py` imported by both, keeping the
  single-definition property while dropping the coupling; add the missing
  `--files` flag; document the crash-handling convention.
Task K: fix round 1/5 → commit 113c1ba. Suite unchanged at 6483 passed.
  `curated_codes`/`strip_position` moved into a pytest-free
  `tests/support/parse_errors.py`; script still reports 404/474 (49 extra,
  27 missing); `--diff` re-verified by a FRESH injection (392/474, exit 1,
  byte-identical revert); `--files` added.
  Verified by me: the module imports cleanly with `pytest` POISONED in
  sys.modules, so its five "pytest" mentions are docstring text explaining why
  it is pytest-free rather than an actual dependency.
  The crash-handling convention is documented AND honestly labelled: "This
  convention is a judgement call (there is no surviving artifact of Task B's
  original throwaway script to confirm it...)". Recording the uncertainty
  rather than presenting a guess as fact is the right shape for a convention
  nobody can now verify.
Task K: scoped re-review dispatched (haiku — module move, flag, docstring).
  Asked it to confirm NO SECOND DEFINITION of curated_codes survives anywhere,
  since two definitions that currently agree is the exact failure this task
  existed to prevent; that the module is importable without pytest rather than
  merely free of a top-level import (a function-level import or an annotation
  would defeat it while passing a naive grep); and that `--files` matches
  conformance_report.py's SEMANTICS rather than just its name — a flag sharing
  a name and differing in behaviour is worse than an absent one.
Task K: re-review — all three ADDRESSED. Sole definitions of `curated_codes`
  and `strip_position` now live in tests/support/parse_errors.py with both
  consumers importing them; NO duplicate definition survives, which was the
  drift this task existed to prevent. Module imports with pytest poisoned.
  `--files` matches conformance_report.py in argument shape, defaults and
  unpack semantics (`--files tests1.dat` → 48/52).
Task K: complete (commits 28e067f..113c1ba, review clean).

ALL ELEVEN TASKS COMPLETE. Final whole-branch review next.

FINAL WHOLE-BRANCH REVIEW (opus) over f252f96..113c1ba, 26 commits.
Verdict: MERGE WITH FIXES. 0 Critical, 4 Important, 13 Minor.
Validated under execution: the rule index's superset contract held clean over
363,000 real element×rule pairs; the two-em-paths design and computed-vs-used
discipline both survived; all four headline numbers reproduce from the
committed scripts.
  - Important 1 IS THE CLASS I ASKED IT TO HUNT FOR, one turn later: the
    shorthand reset silently no-ops on an uppercase property name.
    `values.py` lowercases internally and never says so at its boundary;
    `cascade.py` inherits the reset obligation and keys on the raw name.
    Confirmed: `p{BORDER:solid blue}` left 5px where lowercase gave 3px. Same
    shape as Task I's deviation 7 — a pattern in how seams are documented,
    not an isolated slip.
  - Important 2: `declarations_applied` never counted font-size (12 vs 13).
  - Important 3: `style=` CSS parse errors never recorded; 237 inline styles
    on wikipedia.
  - Important 4: no test pins the `!important` × shorthand-reset axis.

MY DEFERRAL WAS WRONG, and the review demonstrated it rather than asserting
it. I deferred Task J's missing `!important` test as correct-by-inspection.
Important 1 is a silent bug IN THE SAME THREE LINES that test would have
exercised. "Right by inspection" was the wrong standard and the counterexample
was already in the code when I said it.

THE META-FINDING, worth more than any single item: the review counted SEVEN
instances on this branch of a prose edit asserting an unverified fact, finding
four beyond the three known. Its conclusion — "the fix that matters is the
check, not the sentence" — became a standing requirement in the fix wave:
execute every deviation claim you touch; label anything unexecuted as
unverified.

Final fix wave → commit 50752ca. 6499 passed (+16); ALL FOUR BASELINES
UNCHANGED. Verified by me: border/BORDER/BoRdEr all reset to 3px;
declarations_applied 13 across color/width/font-size; ASCII `blocK` accepted
while `blocK` REJECTED.
  I1 fixed at the chokepoint (`_reset_omitted_longhands`) so a third call site
  cannot reintroduce it, plus `values.py` now exports `normalize_property_name`
  and states the normalisation at its public surface — fixing the seam, not
  just the symptom.
  22 DEVIATION CLAIMS EXECUTED RATHER THAN ASSUMED. One was the implementer's
  own and was WRONG: it wrote "`display` is a closed allow-list (21 entries)"
  by counting by eye, ran `len(_DISPLAY_KEYWORDS)`, and got 20. THE
  META-FINDING REPRODUCED INSIDE THE FIX FOR THE META-FINDING, caught only by
  the mandatory check. That is the strongest possible validation of the
  requirement — the discipline caught an instance of the very defect it was
  written to prevent, in real time, in the work fixing it.
  Two corrections to the review: data/metrics/*.csv is gitignored so I2 was
  emitted-but-wrong rather than committed-but-wrong; and I3 moves no baseline
  because none of the corpus's 274 inline styles is actually malformed.
  Five items consciously deferred, now plan Known Gaps 8-13.

MY OWN PROBE WAS WRONG TOO, in the same family: verifying the Kelvin fix I
typed an ASCII "K" rather than U+212A, and read the correct acceptance of
`blocK` as a failed fix. Retested with an explicit `K` escape: ASCII K
accepted, Kelvin rejected, fix correct. Eight instances of this family on this
branch now, one of them mine, one inside the fix for the family.

Final fix wave re-review dispatched (opus) over 113c1ba..50752ca — the last
gate.
