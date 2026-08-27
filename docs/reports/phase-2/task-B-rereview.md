# Task B — scoped re-review of fix round 1 (d61d038..7b42fcf)

Scope: the six open items and the fix diff only. All measurements below were
re-derived independently with throwaway scripts in `/tmp` (read-only on the
repo; variants were produced by `exec`-ing a string-patched copy of
`treebuilder.py`, never by editing it).

## Finding verdicts

**1. `_mode_in_body` DOCTYPE guard — ADDRESSED.**
`src/mayshay/htmlparse/treebuilder.py:532-534`. Guard is the first statement of
the mode, matching the five modes above it. Behaviour-neutral: the pre-fix chain
(`treebuilder.py:534-549`) has no `else`, so a `DoctypeToken` already fell off
the end and was ignored silently; the only new thing is the record.

**2. Heading end tags reshaped to the block shape — ADDRESSED, and the
asymmetry argument is correct.**
`treebuilder.py:656-672`: the scope check now gates only the repair
(`in_scope` -> `generate_implied_end_tags`, `in_scope` -> pop loop), and
`end-tag-too-early` is reported unconditionally when the current node is not the
named element (`treebuilder.py:667-668`). Tree behaviour is unchanged in both
branches.

I verified the "resolved in favour of the vocabulary" claim empirically rather
than taking it on trust, since html5lib is not installed in this venv and its
source is not vendored. Over the 474 curated cases:

| variant | agreements |
|---|---|
| current (heading+block = one code, li/dd/dt = two) | **404/474** |
| heading flattened to the list-item shape | 403/474 |
| li/dd/dt flattened to the block shape | 403/474 |

Each flattening loses exactly one agreement and gains none: heading-flatten
loses `tests19.dat:22`, li/dd-flatten loses `tests1.dat:103`. So the corpus
positively discriminates in both directions — neither family is mis-mapped, and
the asymmetry really is in html5lib's vocabulary. (Strictly, the report's
"trades agreements one-for-one" is slightly generous: both flattenings are a net
loss of one, not a trade. The conclusion stands.)

**3. `tests1.dat:37` xfail reason and the filter's premise — ADDRESSED.**
`tests/htmlparse/test_parse_errors.py:80-90` now names both causes and states
that emitting the `</` characters would still not make the expected code fire.
`tests/htmlparse/test_parse_errors.py:99-116` documents the limit concretely,
not by gesture: it names the offending code
(`expected-closing-tag-but-got-eof`), states the vocabulary is not partitioned
by producer, states the consequence ("can never agree, no matter how complete
the tree builder becomes"), quantifies it (1 of 474), and forbids the wrong fix.
Corroborated: of the five selected cases missing that code, only `tests1.dat:37`
has a non-empty `tokenizer.errors` (`[(2, 'eof before tag name')]`); the other
four (`tests18.dat:1`, `tests19.dat:82`, `tests2.dat:13`, `tests6.dat:23`) have
empty tokenizer errors and are genuine tree-side gaps.
The filter still selects what the task intends: `load_tree_tests("tests1.dat")`,
fragment and `script == "on"` excluded, `all(c in TREE_ERROR_CODES)`
(`test_parse_errors.py:118-134`); the only addition is the strict-xfail marking.

**4. `conformance.csv` column split — ADDRESSED.**
`tests/htmlparse/test_html5lib_tree.py:186-195` declares `tree_parse_errors` and
`tokenizer_parse_errors` as two unambiguously named columns; both row-writing
sites populate both (`:229-232`, `:249-250`). The header change makes pre- and
post-change files distinguishable rather than silently incomparable.

**5. The `unexpected-start-tag` gap — ADDRESSED and quantified.**
`treebuilder.py:562-573` records it for `<frameset>`. Re-derived across the
curated set: `unexpected-start-tag` extras = **0**, misses = **3**, and the three
are exactly the cases the report names (`tests6.dat:0`, `tests6.dat:12`,
`webkit01.dat:47`).

**6. Whole-corpus measurement — ADDRESSED and independently reproduced.**
My run: 474 selected, **404 agree**, 70 disagree, **49 cases with extras**,
**27 cases with misses**, **6 in both**. Per-code breakdown matches the report
exactly (its extras table counts *cases*, its misses table counts *emissions* —
both of my counts reproduce the corresponding table). `tests1.dat` alone is
**48/52** (92.3%) against 404/474 (85.2%): the 7-point gap is real, and it is
why the narrow set hid finding 2 — the case that discriminates the heading shape
(`tests19.dat:22`) is outside `tests1.dat`.
Two cosmetic inaccuracies: `load_tree_tests()` walks 60 `.dat` files, not 57
(the extra three are `tree-construction/scripted/`, which contribute 0 selected
cases), and the 474 selected cases span 33 files.

## `_after_head_fallthrough` — judgement

**It cannot affect tree construction, under any input.** The attribute
(`treebuilder.py:193`, set `:525`, cleared `:529`) has exactly one reader,
`_frameset_in_body` (`treebuilder.py:617-620`), which has exactly one caller: the
boolean guard at `treebuilder.py:573`, whose only consequence is
`self._error(...)`. `_error` (`treebuilder.py:198-200`) appends to `self.errors`
and increments `metrics["parse_errors"]` and does nothing else. There is no path
from the flag to the element stack, the insertion point, the mode, or the
tokenizer. This is a structural argument, not an appeal to conformance being
unmoved.

**Identity comparison is sound here.** The flag is set immediately before
`self.dispatch(token)` and cleared immediately after, and `dispatch`
(`treebuilder.py:418-419`) forwards the *same object*, so identity survives the
re-dispatch chain. A false positive (wrongly suppressing a real in-body frameset
error) would require the same object to be dispatched a second time as a genuine
in-body token while the flag is still set; that cannot happen, because no code
path sets `self.mode = "after_head"` from inside `in_body` (the only two
assignments are `treebuilder.py:507,510`, both in `_mode_in_head`), so
`_mode_after_head` cannot re-enter during its own fall-through and no
set/clear pair can be nested or clobbered.

**No leak between documents.** The attribute is initialised in `__init__` and a
`TreeBuilder` is one document; `parse()` constructs a fresh one.

**One real (Minor) hazard:** the clear at `:529` is not in a `finally`. If
`dispatch` raises inside the fall-through, the flag stays pointing at that token
for the life of the instance. Today nothing survives that exception
(`build()` propagates, and the conformance harness discards the builder), so it
is latent, not live. `try/finally` closes it.

**Both exemptions are load-bearing** — measured by patching
`_frameset_in_body`'s body:

| variant | agreements | invented `unexpected-start-tag` |
|---|---|---|
| both exemptions (current) | 404/474 | 0 |
| after-head exemption only | 403/474 | 1 |
| in-frameset exemption only | 398/474 | 6 |
| neither | 398/474 | 7 |

The report's "7 invented without them" is exact.

**Can the accounting be had without parser state?** Not by a structural test:
`<frameset>` reaching `in_body` via the after-head fall-through and
`<body><frameset>` (`tests19.dat:44`, which *does* expect the error) produce an
identical stack and an identical empty `<body>`, so nothing observable
distinguishes them. The distinguishing fact is genuinely "which mode the spec
would have been in", i.e. provenance. It can, however, be carried as a
*parameter* rather than as instance state: `dispatch(token, from_mode="after_head")`
threaded to `_in_body_start`. That removes the attribute, removes the
exception-leak hazard, and is the direction the implementer themselves names in
their item 7. I would not block on it, but it is strictly better and cheap.

## New breakage in the fix diff

- **Minor** — `tests/htmlparse/test_html5lib_tree.py:230-232`: on the exception
  row, `builder.metrics["tokenizer_parse_errors"]` is always `0`, because
  `build()` raised before `treebuilder.py:415` ever set the key (a `Counter`
  returns 0 rather than raising). `builder.tokenizer.metrics["parse_errors"]`
  would record the truth. Not a regression — the old single column had the same
  hole — but the new column advertises a producer it does not report for that
  row.
- **Minor** — `treebuilder.py:525-529`: the flag clear is not exception-safe
  (above).
- No Critical/Important breakage. Focused run of the covering file:
  `.venv/bin/pytest tests/htmlparse/test_parse_errors.py -q` -> 56 passed,
  4 xfailed (strict), the same four cases as before. `grep -rn parse_errors
  src tests scripts` finds no stale reader of the renamed key.

## Out-of-scope observations

- `_frameset_in_body`'s "in frameset" arm (`treebuilder.py:620`) suppresses the
  error for *any* later `<frameset>` while one is anywhere on the open-elements
  stack, not only a properly nested one. Correct for every corpus case today;
  it becomes wrong the moment `</frameset>` handling or the real "in frameset"
  mode lands. The implementer's own item 8 already says both exemptions must be
  deleted in that change.

## Verdict

**Fix round: all six findings addressed, no new Critical/Important breakage.**
Two Minor items (exception-safe clear; `tokenizer_parse_errors` on the error
row) are worth folding in but do not block.

Environment: `git status --porcelain` empty before and after this review;
`.venv/lib/python3.13/site-packages/__editable__.mayshay-0.1.0.pth` reads
`/Users/atishaypahadiya/projects/mayshay/src`, untouched. Nothing under `.venv/`
was written. All variant experiments ran from `/tmp` scripts against
`sys.path`-inserted sources.
