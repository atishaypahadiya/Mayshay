"""Curation rule for parse-error corpus cases, shared by the pytest suite and
scripts/error_report.py.

Deliberately pytest-free (unlike tests/htmlparse/test_parse_errors.py, which
wraps this in pytest.param/xfail marks) so a measurement script can import it
without pulling in pytest or paying for test collection as an import side
effect. Same shape as tests/support/dat.py: plain data and predicates, no
test framework.
"""

from __future__ import annotations

from mayshay.htmlparse.treebuilder import TREE_ERROR_CODES


def strip_position(line: str) -> str:
    return line.split(":", 1)[1].strip() if ":" in line else line.strip()


def curated_codes(case) -> list[str] | None:
    """The expected codes for `case` if it is curated, else None.

    A case is curated when its expected errors fall entirely inside our set:
    it isn't a fragment or script-on case, and every expected code is in
    TREE_ERROR_CODES.

    The selection rule -- "every expected code is in TREE_ERROR_CODES" -- is a
    proxy for "every expected error is one a tree builder could produce", and
    the proxy has a known hole. html5lib's `#errors` vocabulary is not
    partitioned by producer: at least one member of our set,
    `expected-closing-tag-but-got-eof`, is emitted by html5lib's *tokenizer*
    too (EOF in the tag-open and close-tag-open states) as well as by its tree
    builder. A case whose only expected error is a tokenizer-origin instance
    of such a code is therefore selected by this filter and can never agree,
    no matter how complete the tree builder becomes. `tests1.dat:37` (`</`) is
    exactly that case and is xfailed for it in test_parse_errors.py.

    Measured across all 57 files: 1 of the 474 selected cases is affected. Do
    not "fix" this by widening or narrowing TREE_ERROR_CODES -- the set
    describes what the eight modes can produce, which is a different question.
    Splitting the vocabulary by producer would need a per-code annotation the
    corpus does not carry.

    Shared by tests/htmlparse/test_parse_errors.py and scripts/error_report.py
    so the whole-corpus sweep can never select a different set of cases than
    the pytest suite actually checks.
    """
    if case.fragment is not None or case.script == "on":
        return None
    codes = [strip_position(line) for line in case.errors]
    if codes and all(c in TREE_ERROR_CODES for c in codes):
        return codes
    return None
