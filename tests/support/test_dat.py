from tests.support.dat import load_tree_tests, parse_dat

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
