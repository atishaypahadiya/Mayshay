# Task B report — parse-error honesty in the tree builder

Branch `phase-2-css-to-styled-tree`. Files touched:

- `src/mayshay/htmlparse/treebuilder.py` (the task)
- `src/mayshay/htmlparse/tokenizer.py` (two `pos` fields that were never populated — see "Deviations")
- `tests/htmlparse/test_parse_errors.py` (new)

Nothing under `.venv/` was read, written or moved. The editable-install pointer
`.venv/lib/python3.13/site-packages/__editable__.mayshay-0.1.0.pth` still reads
exactly `/Users/atishaypahadiya/projects/mayshay/src`.

---

## Changes per step

### Step 1 — the failing tests

`tests/htmlparse/test_parse_errors.py` created from the brief verbatim, with one
later change (Step 6, below): the four corpus cases that do not agree carry
`pytest.mark.xfail(strict=True)` with a per-case reason, so the suite stays green
and a future fix or regression fails loudly. The multiset comparison itself is
untouched — codes only, never positions.

### Step 2 — verified failing

`ImportError: cannot import name 'TREE_ERROR_CODES'`, as predicted.

### Step 3 — curated set and recorder

`TREE_ERROR_CODES` added as specified with **one substitution** (see Deviations):
`expected-doctype-but-got-comment` → `expected-doctype-but-got-end-tag`. The set
is still eleven codes; nothing was broadened.

`TreeBuilder.errors: list[tuple[int, str]]` and `_error(code, pos)` added as
specified. `_error` appends `(pos, code)` and increments
`self.metrics["parse_errors"]`.

### Step 4 — recording sites

The brief's sites, all applied:

| Site | Code |
|---|---|
| `_mode_initial` fall-through | `expected-doctype-but-got-{start-tag,chars,eof,end-tag}` |
| `_mode_before_html` / `_before_head` / `_in_head` / `_after_head` / `_after_body`, DOCTYPE | `unexpected-doctype` |
| `_in_body_end`, stray `</p>` | `unexpected-end-tag` |
| `_any_other_end_tag`, stack walk stopped by a special element | `unexpected-end-tag` |
| `_mode_in_body`, EOF with something still open | `expected-closing-tag-but-got-eof` |
| `_mode_text`, EOF | `expected-closing-tag-but-got-eof` |

Sites the brief did not list, added (each is spec text, each is corroborated by
the corpus — details in "Sites the brief missed"):

| Site | Code |
|---|---|
| "close a p element" algorithm, current node is not the p | `unexpected-end-tag` |
| `</li>` with no li in list-item scope | `unexpected-end-tag` |
| `</li>` in scope but not the current node | `end-tag-too-early` |
| `</dd>` / `</dt>` — same two shapes | `unexpected-end-tag` / `end-tag-too-early` |
| `</h1>`..`</h6>` — same two shapes | `unexpected-end-tag` / `end-tag-too-early` |
| `CLOSES_IN_SCOPE` end tag (`</div>`, `</marquee>`, …) whose element is not the current node | `end-tag-too-early` |
| `h1`..`h6` start tag while a heading is the current node | `unexpected-start-tag` |
| `<body>` start tag in "in body" | `unexpected-start-tag` |

`EOF_OK_OPEN` was added as a module constant — see "Sites the brief got wrong".

### Step 5 — the copied count

`build()` now writes `metrics["tokenizer_parse_errors"]` instead of overwriting
`metrics["parse_errors"]`. `grep -rn 'parse_errors' src/ tests/ scripts/` found
one other reader: `tests/htmlparse/test_html5lib_tree.py` writes a `parse_errors`
column into `data/metrics/conformance.csv`. It was **left reading
`metrics["parse_errors"]`** deliberately — the column is named "parse errors",
and for the first time it now actually contains them. No assertion depends on
it, and `scripts/conformance_report.py` does not read the CSV. Reviewers should
know the column's meaning changed from "tokenizer errors" to "tree errors";
if the tokenizer count is wanted there too it needs a second column.

### Step 6 — test run

Eight unit tests pass. Corpus results below.

### Step 7 — conformance

Unmoved. See the transcript below.

### Step 8 — committed.

---

## Exact commands and output

```
$ .venv/bin/pytest tests/htmlparse/test_parse_errors.py -k "not corpus" -v
======================= 8 passed, 52 deselected in 0.02s =======================
```

```
$ .venv/bin/pytest tests/htmlparse/test_parse_errors.py
56 passed, 4 xfailed in 0.05s
```

```
$ .venv/bin/pytest
5119 passed, 59 xfailed in 1.57s
```

Baseline was `5063 passed, 55 xfailed, 0 failed`. The delta is entirely the new
file: +56 passed (8 unit + 48 corpus) and +4 xfailed (the four documented
divergences). The 55 pre-existing xfails are all `strict=True` and all still
xfail, so no tree-construction behaviour flipped underneath them.

```
$ .venv/bin/python scripts/conformance_report.py
all files: 759/1592
tests1.dat: 64/112
```

Identical to the stated baseline. This matters more than usual here, because the
brief's DOCTYPE guards **are** a behaviour change — see "What a reviewer should
scrutinise hardest".

---

## Corpus results — the two counts, kept apart

`tests1.dat`, non-fragment, non-`script-on`, restricted to cases whose expected
`#errors` codes all fall inside `TREE_ERROR_CODES`: **52 curated cases, 48 agree
as a multiset.**

Of the four that do not:

### (1) Cases where we emit a code the corpus does not expect — **4 cases**

Extra codes across them: `end-tag-too-early` ×2, `expected-doctype-but-got-eof`
×1, `unexpected-end-tag` ×1, `expected-closing-tag-but-got-eof` ×1.

Representative example, `tests1.dat:98`:

```
input     <script></script></div><title></title><p><p>
expected  expected-doctype-but-got-start-tag, unexpected-end-tag
actual    expected-doctype-but-got-start-tag, end-tag-too-early
```

Root cause: `_mode_in_head` has no "any other end tag" rule. The spec (and
html5lib) report `unexpected-end-tag` there and ignore the token; we fall the
token through to `after_head` and then to `in_body`, where the block end-tag
rule quite correctly calls it `end-tag-too-early`. The recording site is right;
the insertion mode above it is missing a rule. Fixing that changes tree
construction and belongs to a different task.

### (2) Cases where the corpus expects a code we never emit — **3 cases**

Missing codes across them: `unexpected-end-tag` ×2,
`expected-closing-tag-but-got-eof` ×1, `expected-doctype-but-got-chars` ×1.

Representative example, `tests1.dat:37`:

```
input     </
expected  expected-closing-tag-but-got-eof, expected-doctype-but-got-chars
actual    expected-doctype-but-got-eof
```

Root cause is in the **tokenizer**, not the tree builder. The spec's
eof-before-tag-name step emits U+003C and U+002F as character tokens before the
EOF; ours records the error and drops both characters:

```
>>> t = Tokenizer('</'); list(t.tokenize()); t.errors
[EOFToken(pos=2)]
[(2, 'eof before tag name')]
```

So the initial insertion mode sees EOF where html5lib sees characters. Left
alone: fixing it changes tokenizer output and would have to be re-measured
against conformance.

Three of the four failing cases appear in both buckets, which is why the counts
are 4 and 3 rather than summing to four.

### Codes never emitted

A sweep of all 1592 non-fragment tree-construction cases emits **zero codes
outside `TREE_ERROR_CODES`** — the mapping has not drifted anywhere in the
corpus, not just in `tests1.dat`. Two curated codes are never emitted at all:

- `unexpected-end-tag-before-html` (22 corpus occurrences) — the "before html"
  end-tag rule is not implemented; ours falls through to `before_head`.
- `expected-one-end-tag-but-got-another` (11 occurrences) — html5lib's code for a
  different shape of implied-end-tag mismatch than the one we record.

Both are unimplemented sites, not dead weight; they were left in the set.

Whole-corpus emission profile, for the metrics work downstream:

```
expected-closing-tag-but-got-eof   739
expected-doctype-but-got-start-tag 738
unexpected-end-tag                 489
expected-doctype-but-got-chars     140
end-tag-too-early                   77
expected-doctype-but-got-eof        24
unexpected-start-tag                13
expected-doctype-but-got-end-tag     9
unexpected-doctype                   8
```

---

## Sites the brief got wrong

**1. The "in body" EOF rule is not "anything still open is an error."**

The brief's snippet excludes only `html` and `body`:

```python
if element.tag_name not in ("html", "body"):
```

The spec names a list of elements that may legitimately still be open at EOF —
`dd dt li optgroup option p rb rp rt rtc tbody td tfoot th thead tr body html` —
and reports a parse error only for anything outside it. With the brief's version,
`<p>One<p>Two` reported `expected-closing-tag-but-got-eof` where html5lib reports
nothing; an unclosed `<p>` at EOF is normal markup. Replaced with a module
constant `EOF_OK_OPEN` carrying the spec's list. This alone moved the corpus from
39/51 to 44/51.

**2. `expected-doctype-but-got-comment` is not a real code and cannot be reached.**

In `_mode_initial`, DOCTYPE, comments, whitespace, start tags, non-whitespace
characters and EOF are all handled before the fall-through, so the `else` the
brief attaches that code to sees exactly one thing: an end tag. And a comment in
"initial" is *inserted*, not an error — the spec says so and the corpus agrees:
`expected-doctype-but-got-comment` appears **0 times** across the whole corpus,
while `expected-doctype-but-got-end-tag` appears 7 times. Substituted one for the
other. The set stayed at eleven codes; this is a correction, not a broadening,
and I flag it because it did make one more case curated (51 → 52 cases, and that
case passes).

## Sites the brief missed

All eight are listed in the Step 4 table above. The two worth arguing:

**"Close a p element" owns its parse error.** The spec puts "if the current node
is not a p element, then this is a parse error" *inside the algorithm*, not at the
`</p>` rule — which means an **implied** close reports it too. `<p><b><div>` is a
parse error at the `<div>`, and html5lib records it there
(`tests1.dat:25`, `(1,11)`). The check therefore moved into `close_p_element`,
which gained a required `pos` argument; all four call sites pass their token's
offset. The `</p>`-with-no-p-in-scope error is still reported separately at the
`</p>` rule and is not a duplicate: the empty `<p>` inserted just before makes the
algorithm's own check pass.

**The block end-tag family reports `end-tag-too-early`, never a not-in-scope code.**
`CLOSES_IN_SCOPE` end tags use one error covering both failure shapes: the current
node is not the named element, whether because something is still open inside it
or because it is not in scope at all. `tests1.dat:25`/`:97` pin this down —
`</div>` with the div blocked out of scope by an open `<marquee>` is reported as
`end-tag-too-early`, not `unexpected-end-tag`. My first version split it into two
codes and produced a mapping error; the single-error form is what the vocabulary
actually uses.

The three `end-tag-too-early` sites on `</li>`, `</dd>`/`</dt>` and `</h1>`..`</h6>`
follow the same spec sentence and are corroborated by the corpus sweep (77
emissions, all inside the set).

---

## What a reviewer should scrutinise hardest

**1. The DOCTYPE guards are the one behaviour change in this diff.** Everything
else is pure recording, but

```python
if isinstance(token, DoctypeToken):
    self._error("unexpected-doctype", token.pos)
    return
```

in `_mode_before_html`, `_before_head`, `_in_head`, `_after_head` and
`_after_body` replaces a fall-through with an early return. Before, a DOCTYPE in
`before_html` walked all the way down to `in_body` creating `<html>`, `<head>`
and `<body>` on the way; now it is ignored where it stands. The spec says
"Parse error. Ignore the token." in every one of those modes, so the new
behaviour is the correct one — and conformance is unmoved at 759/1592 and
64/112, because the *next* token performs the same fall-through the DOCTYPE used
to trigger. But it is the change most likely to have a case nobody thought of,
and it is the one I would re-derive from the spec rather than take on trust.

**2. `close_p_element(pos)` is now a required argument.** Any future call site
that has no obvious token offset will be tempted to pass `-1`, which would break
`test_error_positions_are_within_the_source`'s invariant silently for that path.

**3. The `end-tag-too-early`-only decision for `CLOSES_IN_SCOPE`.** It is
corroborated by two corpus cases and contradicted by none, but it rests on
matching html5lib's vocabulary rather than on spec text (the spec names no error
codes). If Task C or later work adds the in-head end-tag rule, cases 26 and 98
should flip from xfail to pass — the strict xfails will say so.

**4. The four `KNOWN_ERROR_MISSES` xfails.** They are `strict=True` with named
root causes, deliberately mirroring `KNOWN_MISSES` in `test_html5lib_tree.py`.
This is the one place I departed from the brief's verbatim test file; the
alternative was leaving four hard failures in a previously-green suite, which
would mask the next regression. The assertion body is unchanged, and no case that
agrees today is marked.

**5. `conformance.csv`'s `parse_errors` column changed meaning** from tokenizer
errors to tree-construction errors. Any analysis already built on that column
will shift.

**6. Two tokenizer fields now carry real offsets.** `EOFToken.pos` and
`DoctypeToken.pos` defaulted to `-1` and nothing populated them, so every EOF and
DOCTYPE error would have been recorded at `-1`. `EOFToken` now carries
`self.pos`; `DoctypeToken` carries `self.pos - 9`, the offset of its own `<`,
matching the convention `_emit_tag` already used for start and end tags. Both are
one-line changes to existing dataclass fields. No test compares whole tokens for
equality, so nothing downstream shifted.

---

# Fix round 1

Six items from review. All addressed. Files touched this round:
`src/mayshay/htmlparse/treebuilder.py`, `tests/htmlparse/test_parse_errors.py`,
`tests/htmlparse/test_html5lib_tree.py`.

## Correction to my own report first

I described the DOCTYPE early return as "conformance-neutral". That undersells
what it does in `_mode_in_head`, where it is a genuine tree improvement: a stray
DOCTYPE no longer prematurely closes `<head>`. Measured against the pre-task
tree builder on `<head><!DOCTYPE html><title>t</title></head>`:

```
before                       after
| <html>                     | <html>
|   <head>                   |   <head>
|   <body>                   |     <title>
|     <title>                |       "t"
|       "t"                  |   <body>
```

The `<title>` used to land in `<body>` because the DOCTYPE fell through
`pop_until("head")` on its way to being ignored. It now stays in `<head>`, which
is what the spec's "ignore the token" gives you. Conformance did not move because
no corpus case exercises that shape, not because nothing changed.

## Important 1 — `_mode_in_body` DOCTYPE guard

Added; the sixth mode now matches the five above it.

```
>>> tb = TreeBuilder('<!DOCTYPE html><div><!DOCTYPE html></div>'); tb.build()
>>> tb.errors
[(20, 'unexpected-doctype')]
```

Behaviour is unchanged — `_mode_in_body` already ignored DOCTYPE tokens by
falling off the end of its `isinstance` chain; it just did so silently. All five
`unexpected-doctype` misses (`domjs-unsafe.dat:31,32,33,41,43`) are closed.

## Important 2 — heading end tags reshaped, and the asymmetry resolved

`</h1>`–`</h6>` now follow the block shape: the scope check gates only the
*repair*, and one code, `end-tag-too-early`, is reported whenever the current
node is not the element the tag names.

```
>>> tb = TreeBuilder('<!doctype html><p></h3>foo'); tb.build(); tb.errors
[(18, 'end-tag-too-early')]      # was [(18, 'unexpected-end-tag')]
```

On the asymmetry with `</li>`, `</dd>`, `</dt>`, which do still report
`unexpected-end-tag` when nothing is in scope: **the asymmetry is real and lives
in the vocabulary, not in this code.** html5lib's `endTagBlock` and
`endTagHeading` both put the "current node is not the named element" test
*outside* the scope branch and emit one code; `endTagListItem` branches on scope
and emits two. Flattening either family to match the other produces codes the
corpus does not expect — I tried it, and it trades agreements one-for-one. The
reasoning is now a comment at the `CLOSES_IN_SCOPE` site, which is where a reader
will hit the question.

My report defended the `CLOSES_IN_SCOPE` decision on `tests1.dat` evidence alone,
and this bug is exactly what that narrow denominator hid.

## Important 3 — the `tests1.dat:37` xfail reason, and the filter's premise

The old reason named a fix that would not work. Corrected: the reason now gives
both causes, and states that emitting the `</` characters would still not make
`expected-closing-tag-but-got-eof` fire, because only `html` and `body` are open
at EOF.

The deeper point is documented where the filter is defined, in `_curated_cases`'s
docstring: html5lib's `#errors` vocabulary is **not partitioned by producer**, so
the selection rule "every expected code is in `TREE_ERROR_CODES`" is a proxy for
"every expected error is one a tree builder could produce", and the proxy has a
hole. `expected-closing-tag-but-got-eof` is emitted by html5lib's *tokenizer*
(EOF in the tag-open and close-tag-open states) as well as by its tree builder. A
case whose only expected error is a tokenizer-origin instance of such a code is
selected by this filter and can never agree, however complete the tree builder
becomes.

Measured: **1 of the 474 selected cases across all 57 files is affected**
(`tests1.dat:37`). I checked the other four cases missing that code
(`tests18.dat:1`, `tests19.dat:82`, `tests2.dat:13`, `tests6.dat:23`) — all have
empty `tokenizer.errors`, so all four are genuine tree-side gaps. The docstring
says explicitly not to fix this by moving `TREE_ERROR_CODES`, since the set
answers a different question, and that a real fix needs a per-code producer
annotation the corpus does not carry.

## Upgraded item — `conformance.csv` no longer overloads one column

`tests/htmlparse/test_html5lib_tree.py` now writes **two** columns,
`tree_parse_errors` and `tokenizer_parse_errors`, replacing the single
`parse_errors` that used to hold the tokenizer's count and would silently have
started holding the tree builder's. Both names say which producer they come from,
and the header change makes pre- and post-change files distinguishable at a
glance instead of silently incomparable.

```
$ head -2 data/metrics/conformance.csv
case_id,outcome,input_chars,expected_lines,actual_lines,elements,max_depth,text_nodes,tree_parse_errors,tokenizer_parse_errors,parse_time_ms
tests1.dat:0,pass,4,4,4,3,2,1,1,0,0.054
```

The file is gitignored, so no committed data was affected; the local artifact has
been regenerated on the new schema. The long-format `data/metrics/*.csv` written
by `mayshay.metrics` needs nothing: it is `(run, stage, key, value)` rows, so
`tokenizer_parse_errors` arrives as a new key for free — which is the property
that schema was chosen for.

## The `unexpected-start-tag` gap — recorded, not just listed

It was 33 under-reports across 33 cases. 30 of them are one site: `<frameset>` in
"in body", where the spec's parse error is unconditional. Recorded, with two
exemptions, each naming an insertion mode we do not have:

- **"after head"** — a document that opens with `<frameset>` reaches `in_body`
  only via `_mode_after_head`'s fall-through. The spec handles it in "after head",
  where it is not an error. `_mode_after_head` now records which token triggered
  its fall-through so the in-body rule can skip it.
- **"in frameset"** — a nested `<frameset>` is legitimate; recognisable by one
  already being on the open-elements stack.

Without both exemptions the site invents 7 errors html5lib does not report
(including one in `tests1.dat:104`, which would have cost an agreement). With
them: `unexpected-start-tag` extras are **zero** and its misses drop 33 → 3.

The residual 3 are listed explicitly, each an unimplemented rule:

| Case | Input | Missing site |
|---|---|---|
| `tests6.dat:0` | `<!doctype html></head> <head>` | `<head>` start tag outside "in head" |
| `tests6.dat:12` | `<form><form>` | the form element pointer |
| `webkit01.dat:47` | `<table><tr><td><svg><desc><td></desc><circle>` | foreign content |

## Whole-corpus measurement

Across **all 57 files**, non-fragment and non-`script-on`, same curation filter:

**404 of 474 curated cases agree as a multiset.** (The reviewer's unmeasured
estimate was 388/474; the difference is this round's fixes.) `tests1.dat` alone is
48/52 — unchanged in count, but no longer the number I would quote.

The two counts, whole corpus: **49 cases emit a code the corpus does not expect**;
**27 cases expect a code we never emit**; 6 cases are in both.

Extras (49 cases), by code — all three roots already named:

| Code | Cases | Root |
|---|---|---|
| `expected-closing-tag-but-got-eof` | 27 | table/foreign/select modes leave elements open that the spec would have closed |
| `unexpected-end-tag` | 23 | same, plus `_mode_in_head`'s missing "any other end tag" rule |
| `end-tag-too-early` | 2 | `_mode_in_head` fall-through (`tests1.dat:26`, `:98`) |
| `expected-doctype-but-got-eof` | 1 | the `</`-at-EOF tokenizer deviation |

Misses (27 cases), by code:

| Code | Count | Root |
|---|---|---|
| `unexpected-end-tag` | 16 | ruby, table and foreign-content rules |
| `expected-closing-tag-but-got-eof` | 5 | plaintext, MathML, table modes (+1 tokenizer-origin, above) |
| `expected-one-end-tag-but-got-another` | 5 | `</body>`/`</html>` with elements still open — no site yet |
| `end-tag-too-early` | 3 | dd/dt interactions with unimplemented modes |
| `unexpected-start-tag` | 3 | the three rows in the table above |
| `unexpected-end-tag-before-html` | 1 | "before html" end-tag rule not implemented |
| `expected-doctype-but-got-chars` | 1 | the `</`-at-EOF tokenizer deviation |

`expected-one-end-tag-but-got-another` and `unexpected-end-tag-before-html`, which
I reported last round as never emitted, are now quantified: 5 and 1 curated cases
respectively want them. Both remain unimplemented sites.

## Verification

```
$ .venv/bin/pytest
5119 passed, 59 xfailed in 1.63s

$ .venv/bin/python scripts/conformance_report.py
all files: 759/1592
tests1.dat: 64/112
```

Unmoved. In particular the `_mode_in_body` DOCTYPE guard did not move it, as
expected: that mode already ignored DOCTYPE tokens, so only the recording is new.
The four `tests1.dat` xfails are the same four cases as before this round.

## What a reviewer should still scrutinise hardest

Carried forward from last round, plus:

**7. `_after_head_fallthrough` is state, and state on a parser is a liability.**
It is set immediately before a re-dispatch and cleared immediately after, so it
cannot outlive the token it describes, and `_frameset_in_body` is the only reader.
But it is the one piece of this task that is not a pure function of the token and
the stack, and if a second mode ever needs the same trick the right answer is
probably to pass the previous mode into `dispatch` rather than to add a second
flag.

**8. The frameset exemptions are load-bearing and only corpus-justified.** Both
encode "the spec would have been in a mode we do not have". If either the "after
head" or "in frameset" mode ever lands, both exemptions must be deleted in the
same change, or `<frameset>` errors will go quietly missing.

---

# Fix round 2

Two items. Both taken.

## 1 — `_after_head_fallthrough` replaced by a `dispatch` parameter

**Taken, in the uniform shape.** `dispatch` is now
`dispatch(self, token, from_mode: str | None = None)` and forwards `from_mode`
to the mode handler; all eight `_mode_*` methods accept it; `_mode_in_body`
forwards it to `_in_body_start`; and `_frameset_in_body` takes `from_mode`
instead of reading parser state. The instance attribute, its set, and its clear
are gone — `grep -rn '_after_head_fallthrough' src/ tests/` returns nothing.

`from_mode` is populated at **every** re-dispatch site, not only after_head's:
`initial`, `before_html`, `before_head`, `in_head`, `after_head`, `in_body`
(the `</html>` hand-off), `text` and `after_body`. It names the mode that handed
the token on, and is `None` for a token arriving straight from the tokenizer in
`build()`'s loop. Populating only the one site the frameset rule reads would have
left a parameter whose value is arbitrary everywhere else — a worse thing to hand
the next reader than seven consistent ones.

**On whether the shape costs more than the state it removes: it does not.** The
honest accounting is eight signatures gaining a defaulted keyword and eight call
sites gaining an argument, against three lines of state plus a clear step that
was **not** in a `finally` — so an exception raised mid-fall-through left the flag
set and would have suppressed the next document's frameset error. That is a real
defect the parameter cannot have, not a stylistic preference, and the parameter
also gives the mode handlers a fact the spec keeps referring to ("reprocess the
token") that they previously had no way to see.

Behaviour is identical. Both exemptions verified individually:

```
'<!doctype html><body><frameset>'          -> ['unexpected-start-tag', ...]   # still reported
'<!doctype html><p>a<frameset>'            -> ['unexpected-start-tag', ...]   # still reported
'<frameset></frameset><!DOCTYPE html>'     -> [...]                           # after-head exempt
'<frameset><frame><frameset>...'           -> [...]                           # in-frameset exempt
```

`tests19.dat:44` (`<!doctype html><body><frameset>`) is the case the review
flagged as structurally identical to the exempt one — it still reports, because
provenance is now the only thing separating them, explicitly and by parameter.

## 2 — `tokenizer_parse_errors` on the exception row

`test_html5lib_tree.py`'s crash branch now reads
`builder.tokenizer.metrics["parse_errors"]` directly. `build()` copies the count
across as its last act, so on a path where `build()` raised, the copy never
happened and the `Counter` returned a default `0` that nothing downstream could
distinguish from a real one. Demonstrated on a builder forced to raise mid-parse:

```
metrics[tokenizer_parse_errors] = 0   (the stale default)
tokenizer.metrics[parse_errors] = 1   (the truth)
```

The `tree_parse_errors` column on the same row needs no equivalent fix and is
left alone: `_error` increments it as errors happen, so a partial parse yields a
partial-but-real count rather than a fabricated zero. That asymmetry is now a
comment at the site, since the two lines look parallel and are not.

## Verification

```
$ .venv/bin/pytest
5119 passed, 59 xfailed in 1.63s

$ .venv/bin/python scripts/conformance_report.py
all files: 759/1592
tests1.dat: 64/112
```

Whole-corpus agreement unchanged at **404/474** (49 cases emit a code the corpus
does not expect, 27 expect a code we never emit, 6 in both). `tests1.dat` 48/52,
same four xfails.

## Reviewer note superseded

Item 7 from the previous round ("`_after_head_fallthrough` is state, and state on
a parser is a liability") is resolved and no longer applies. Item 8 stands
unchanged: both frameset exemptions are load-bearing and corpus-justified, and if
the "after head" or "in frameset" insertion mode ever lands, both must be deleted
in the same change or `<frameset>` errors will go quietly missing. The exemption
now keyed on `from_mode == "after_head"` makes that coupling easier to find.
