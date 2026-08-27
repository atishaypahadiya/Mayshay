import collections

import pytest

from mayshay.htmlparse.treebuilder import TREE_ERROR_CODES, TreeBuilder
from tests.support.dat import load_tree_tests
from tests.support.marks import requires_corpus

MALFORMED = "<p>a<div>b</p></span><li>c"


def test_malformed_page_reports_tree_errors():
    """The headline bug: this reported 0 before."""
    tb = TreeBuilder(MALFORMED)
    tb.build()
    assert tb.errors, "tree builder recorded no errors on malformed input"
    assert tb.metrics["parse_errors"] == len(tb.errors)


def test_tokenizer_and_tree_counts_are_not_aliases():
    tb = TreeBuilder(MALFORMED)
    tb.build()
    assert tb.metrics["tokenizer_parse_errors"] == 0
    assert tb.metrics["parse_errors"] > 0


def test_clean_document_reports_zero_from_both():
    tb = TreeBuilder("<!DOCTYPE html><html><head></head><body><p>x</p></body></html>")
    tb.build()
    assert tb.errors == []
    assert tb.metrics["parse_errors"] == 0
    assert tb.metrics["tokenizer_parse_errors"] == 0


def test_missing_doctype_is_recorded():
    tb = TreeBuilder("<p>x")
    tb.build()
    assert any(code.startswith("expected-doctype") for _, code in tb.errors)


def test_stray_end_tag_is_recorded():
    tb = TreeBuilder("<!DOCTYPE html><p>x</span>")
    tb.build()
    assert any(code == "unexpected-end-tag" for _, code in tb.errors)


def test_unclosed_element_at_eof_is_recorded():
    tb = TreeBuilder("<!DOCTYPE html><div><p>x")
    tb.build()
    assert any(code == "expected-closing-tag-but-got-eof" for _, code in tb.errors)


def test_every_recorded_code_is_in_the_curated_set():
    """A code outside the set means the mapping drifted from the vocabulary."""
    for src in (MALFORMED, "<p>x", "<!DOCTYPE html><p>x</span>", "<div><p>x"):
        tb = TreeBuilder(src)
        tb.build()
        for _, code in tb.errors:
            assert code in TREE_ERROR_CODES, f"{code!r} not in the curated set"


def test_error_positions_are_within_the_source():
    tb = TreeBuilder(MALFORMED)
    tb.build()
    for pos, _ in tb.errors:
        assert 0 <= pos <= len(MALFORMED)


# Curated cases that do not agree, each with the single root cause behind it.
# Marked strict so that fixing one of these -- or breaking a case that agrees
# today -- fails loudly instead of drifting. Same convention as KNOWN_MISSES in
# test_html5lib_tree.py. None of these is a mapping bug in the recording sites;
# each is an unimplemented or divergent piece of the parser upstream of them.
KNOWN_ERROR_MISSES = {
    "tests1.dat:26": (
        "_mode_in_head falls an unmatched end tag through to in_body instead "
        "of reporting unexpected-end-tag and ignoring it, so </div> is "
        "diagnosed by the in-body block rule as end-tag-too-early"
    ),
    "tests1.dat:37": (
        "two independent causes, neither of them a tree-builder mapping bug. "
        "(a) The tokenizer drops the two characters of a bare `</` at EOF "
        "instead of emitting them (spec eof-before-tag-name emits U+003C and "
        "U+002F), so the initial mode sees EOF where html5lib sees chars. "
        "(b) The expected expected-closing-tag-but-got-eof is html5lib's "
        "TOKENIZER error for EOF in the close-tag-open state, not a tree "
        "error -- emitting the characters would not make it fire, since only "
        "html and body are open at EOF. See the note on _curated_cases"
    ),
    "tests1.dat:98": "same _mode_in_head fall-through as tests1.dat:26",
    "tests1.dat:106": (
        "the table insertion modes are not implemented, so </table> reaches "
        "the in-body stack walk and the table is still open at EOF"
    ),
}


def _strip_position(line: str) -> str:
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
    exactly that case and is xfailed for it.

    Measured across all 57 files: 1 of the 474 selected cases is affected. Do
    not "fix" this by widening or narrowing TREE_ERROR_CODES -- the set
    describes what the eight modes can produce, which is a different question.
    Splitting the vocabulary by producer would need a per-code annotation the
    corpus does not carry.

    Shared with scripts/error_report.py so the whole-corpus sweep can never
    drift from what this test file actually selects and checks.
    """
    if case.fragment is not None or case.script == "on":
        return None
    codes = [_strip_position(line) for line in case.errors]
    if codes and all(c in TREE_ERROR_CODES for c in codes):
        return codes
    return None


def _curated_cases():
    try:
        cases = load_tree_tests("tests1.dat")
    except FileNotFoundError:
        return []
    out = []
    for case in cases:
        codes = curated_codes(case)
        if codes is None:
            continue
        marks = []
        if case.id in KNOWN_ERROR_MISSES:
            marks.append(
                pytest.mark.xfail(strict=True, reason=KNOWN_ERROR_MISSES[case.id])
            )
        out.append(pytest.param(case, codes, marks=marks, id=case.id))
    return out


@requires_corpus
@pytest.mark.parametrize("case,expected", _curated_cases())
def test_corpus_error_codes_match_as_a_multiset(case, expected):
    """Codes only, never positions.

    html5lib reports (line, col) at the END of the offending token; our
    convention points AT the character that caused it. Comparing positions
    would fail nearly everywhere, and for reasons that are correct.
    """
    tb = TreeBuilder(case.data)
    tb.build()
    actual = [code for _, code in tb.errors]
    assert collections.Counter(actual) == collections.Counter(expected)
