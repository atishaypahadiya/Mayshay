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
- BeautifulSoup allowed ONLY in scripts/ for corpus collection, never in src/mayshay/.
- Every stage emits timing + size metrics to data/metrics/.
- Tests in tests/ mirror src/mayshay/. pytest.
- Follow the WHATWG HTML spec tokenizer state machine where practical.
- The `tests/html5lib-tests` submodule is pinned to `9329e64` on purpose.
  Upstream removed `tree-construction/` in `224991e`; that pin is the last
  commit that still has the fixtures. Advancing it silently turns tests marked
  `requires_corpus` into skips rather than failures. Never `git submodule update --remote`.
