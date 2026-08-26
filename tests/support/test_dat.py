from tests.support.dat import (
    TOKENIZER_DIR,
    TREE_DIR,
    load_tokenizer_tests,
    load_tree_tests,
    parse_dat,
)
from tests.support.marks import requires_corpus

SAMPLE = '''#data
<p>Hello
#errors
(1,3): expected-doctype-but-got-start-tag
#document
| <html>
|   <head>
|   <body>
|     <p>
|       "Hello"

#data
<b><i></b></i>
#errors
#document
| <html>
|   <head>
|   <body>
|     <b>
|       <i>
'''


def test_parses_two_tests():
    tests = parse_dat(SAMPLE, path="sample.dat")
    assert len(tests) == 2


def test_data_section_has_no_trailing_newline():
    tests = parse_dat(SAMPLE, path="sample.dat")
    assert tests[0].data == "<p>Hello"
    assert tests[1].data == "<b><i></b></i>"


def test_document_section_preserved_verbatim():
    tests = parse_dat(SAMPLE, path="sample.dat")
    assert tests[0].document.splitlines()[0] == "| <html>"
    assert tests[0].document.splitlines()[-1] == '|       "Hello"'


def test_errors_captured():
    tests = parse_dat(SAMPLE, path="sample.dat")
    assert len(tests[0].errors) == 1
    assert tests[1].errors == []


def test_test_id_is_stable():
    tests = parse_dat(SAMPLE, path="sample.dat")
    assert tests[0].id == "sample.dat:0"


def test_real_corpus_loads():
    tests = load_tree_tests("tests1.dat")
    assert len(tests) > 50
    assert all(t.document for t in tests)


# --- Coverage-pinning tests -------------------------------------------------
#
# These assert exact counts measured against the corpus at the pinned
# submodule commit (9329e64) so that a future silent drop in a loader (e.g.
# a glob that stops recursing, or a JSON key that stops being read) shows up
# as a failing assertion instead of quietly smaller coverage. The numbers
# are literal, not recomputed from the loader under test, so they can't pass
# by tautology.


@requires_corpus
def test_tree_dat_file_count_includes_scripted_subdir():
    # tree-construction/scripted/ has no top-level duplicates (e.g. ark.dat
    # only exists there), so a non-recursive glob would silently drop it.
    dat_files = sorted(TREE_DIR.rglob("*.dat"))
    assert len(dat_files) == 60
    assert TREE_DIR / "scripted" / "ark.dat" in dat_files


@requires_corpus
def test_load_tree_tests_default_count():
    tests = load_tree_tests()
    assert len(tests) == 1796


@requires_corpus
def test_load_tree_tests_reaches_scripted_dat_files():
    tests = load_tree_tests()
    scripted_paths = {t.path for t in tests if "/scripted/" in t.path}
    assert scripted_paths, "no tests loaded from tree-construction/scripted/"


@requires_corpus
def test_tokenizer_test_file_count():
    test_files = sorted(TOKENIZER_DIR.glob("*.test"))
    assert len(test_files) == 14


@requires_corpus
def test_load_tokenizer_tests_default_count():
    tests = load_tokenizer_tests()
    assert len(tests) == 6800


@requires_corpus
def test_load_tokenizer_tests_reads_xml_violation_tests_key():
    # xmlViolation.test stores its cases under "xmlViolationTests", not
    # "tests"; reading only "tests" silently drops all 4 of them.
    tests = load_tokenizer_tests("xmlViolation.test")
    assert len(tests) == 4
