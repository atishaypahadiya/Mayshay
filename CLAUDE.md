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
