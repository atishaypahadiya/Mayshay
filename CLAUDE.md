# Mayshay

Educational browser engine written from scratch, plus a data analysis of
real-world web structure built on metrics the engine emits.

## Pipeline
net -> htmlparse -> cssparse -> layout -> paint

Package root is `src/mayshay/`. Imports look like:
    from mayshay.htmlparse import Tokenizer

## Rules
- No lxml, no html.parser, no browser libs for core parsing. Hand-rolled only.
- BeautifulSoup allowed ONLY in scripts/ for corpus collection, never in src/mayshay/.
- Every stage emits timing + size metrics to data/metrics/.
- Tests in tests/ mirror src/mayshay/. pytest.
- Follow the WHATWG HTML spec tokenizer state machine where practical.
- The `tests/html5lib-tests` submodule is pinned to `9329e64` on purpose.
  Upstream removed `tree-construction/` in `224991e`; that pin is the last
  commit that still has the fixtures. Never `git submodule update --remote`.
