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
- Non-ASCII in test data is written as an escape (\u212a), never as a literal.
  Kelvin sign vs ASCII K, NBSP vs space, and combining marks all read
  identically in a terminal.
