# Mayshay

Educational browser engine written from scratch, plus a data analysis of
real-world web structure built on metrics the engine emits.

## Pipeline
net -> htmlparse -> cssparse -> layout -> paint

Package root is `src/mayshay/`. Imports look like:
    from mayshay.htmlparse import Tokenizer

## Rules
- No lxml, no html.parser, no browser libs for core parsing. Hand-rolled only.
  EXCEPTION: `html.entities.html5` is used as the named character reference
  data table (2231 entries). It is data -- the WHATWG named reference list --
  not a parser. All matching logic (longest match, the legacy semicolon rule,
  numeric remapping) is hand-rolled in `htmlparse/entities.py`.
- CSS tokenization and parsing are hand-rolled. `tinycss2`, `cssutils` and
  `cssselect` are forbidden in `src/mayshay/`. The same rule as the HTML
  parser, for the same reason: the point is to write it.
- BeautifulSoup allowed ONLY in scripts/ for corpus collection, never in src/mayshay/.
- `fontTools` is permitted in `src/mayshay/layout/` for reading font metrics
  -- glyph advances from `hmtx`, vertical metrics from `hhea` and `OS/2`. It
  is a binary format reader over vendored data, in the same category as
  `html.entities.html5`. It must not make layout decisions: text measurement
  is the only thing it is asked for, behind a single `measure()` interface.
  Line breaking, white-space collapsing, baseline alignment and every box
  position stay hand-rolled. Pillow is permitted in `paint/` for
  rasterization only. Neither may be imported by `htmlparse` or `cssparse`.
  The font is pinned: Liberation Sans 2.1.5, vendored at
  `data/fonts/LiberationSans-Regular.ttf` with its SHA-256 and the exact
  derivation of every metric recorded in `docs/fonts.md`. Every layout
  number depends on that file; changing it changes them.

- Every stage emits timing + size metrics to data/metrics/. Stages populate
  `self.metrics`; `src/mayshay/metrics.py` writes them, and entry points call
  the writer — never a parse method. `htmlparse` emits TWO stage values,
  `tokenize` and `treebuild`: the five-box pipeline above is the conceptual
  shape, not the metrics schema, and their counters and error counts are
  separately meaningful.
- Tests in tests/ mirror src/mayshay/. pytest.
- Follow the WHATWG HTML spec tokenizer state machine where practical.
- The `tests/html5lib-tests` submodule is pinned to `9329e64` on purpose.
  Upstream removed `tree-construction/` in `224991e`; that pin is the last
  commit that still has the fixtures. Advancing it silently turns tests marked
  `requires_corpus` into skips rather than failures. Never `git submodule update --remote`.
- Any factual claim about the code — a count, a set membership, a "this is
  already handled" — is executed before it is written down. Nine instances of
  assert-from-reading reached review on the phase 2 branch, including one
  inside the fix for that same defect family. Reading is convincing and cheap;
  running is one line.
  This applies to decisions as well as claims: a test deferred as
  "correct by inspection" is an unexecuted claim wearing a decision's clothes.
- Never `git add -A` (or `git add .`) while a subagent is live. Always stage
  explicit paths. The working tree is shared: a blanket add sweeps an
  agent's in-progress work into whatever commit you are making, and three
  docs commits on the Phase 3 branch ended up carrying engine deliverables
  whose messages described none of it. Nothing was lost and the tests stayed
  green, which is what makes it easy to miss -- the damage is to bisect and
  to review, not to content. This sits beside the one-committing-agent rule
  from Phase 1 for the same reason: a shared tree needs one writer at a time
  or explicit boundaries.
- Every cross-stage comparison must distinguish wrong output from wrong
  input, and report upstream divergence separately from the thing being
  measured. Carry two identifiers, not one: when they agree the comparison
  is valid, and when they disagree the stage above diverged. Attributing an
  `htmlparse` defect to layout is the same failure as attributing a cascade
  defect to layout -- which is why Phase 3 repairs the cascade before it
  builds a box tree, at a 70% declaration drop rate a layout bug and a
  cascade bug are indistinguishable.
- A measurement is verified by a second measurement obtained a different
  way, never by inspection and never by internal consistency. Three
  figures on this project were wrong while looking right: the display
  census before `@media` evaluation, `PIL.getlength`'s integer advances,
  and `DOM.getBoxModel`'s union box for wrapping inlines. Each had the
  right type and a plausible magnitude. See `docs/measurement-hazards.md`.
  A suspiciously clean result -- exactly zero, exactly integral, exactly
  unchanged -- is a claim about the instrument until a probe proves
  otherwise.
- Any test touching tree traversal, ordering, or identity uses **at least
  three levels of nesting, with siblings at more than one level**. Task B
  numbered document ordinals level-by-level instead of in document order and
  7,058 tests did not notice, because every fixture that exercised the code
  was one `<div>` deep -- a shape where the two orders coincide. Nesting
  depth is a test-design axis in its own right: the corpus-cannot-
  discriminate problem appearing inside the synthetic tests, where the
  synthetic-only register does not look.
- Non-ASCII in test data is written as an escape (\u212a), never as a literal.
  Kelvin sign vs ASCII K, NBSP vs space, and combining marks all read
  identically in a terminal.

## Process, from Phase 4 onward

The verification discipline in this file earned its cost through layout --
the float denominator, the flex column path, `getBoxModel`'s union box --
because layout produces numbers whose wrongness is invisible. **Paint does
not.** It rasterizes a box tree that already has positions, and a wrong
result is visible by looking at the PNG.

So from Phase 4:

- **Normal TDD.** Write the test, write the code.
- **No hazard entries unless something actually breaks.**
  `docs/measurement-hazards.md` is closed to speculative entries; it stays
  open to anything that genuinely bites.
- **No shadow builds, no discriminating-power sweeps, no pre-registered
  thresholds.** Those exist to make an invisible wrongness visible. Where
  the output is an image, look at the image.
- **No second derivation** of anything checkable by eye in the output.

What stays, because it is cheap and it is what caught the last defect:

- **Every stage emits its counters.** Unchanged.
- **The corpus-wide smoke run**, and specifically the merge gate below.

### The merge gate

`tests/layout/test_corpus_lays_out.py`: every page in the current collection
must lay out without raising. Phase 3 shipped green against three pages and
the first 79-page run found 12 crashes across 7 of 9 strata, ten of them one
assertion in flex code reviewed a week earlier -- and the minimal synthetic
reproduction of the failing container *passes*, so no unit test would have
found it. Paint gets the equivalent gate: every collected page rasterizes
without raising.

This checks termination, not correctness. That is the floor, and the floor
is where the last defect was.
