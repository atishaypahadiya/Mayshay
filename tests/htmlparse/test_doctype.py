"""DOCTYPE identifier capture and document-mode classification (Task C).

Phase 1 discarded public and system identifiers -- tokenizer deviation #3
as it was numbered then, now removed and the rest renumbered -- so
`Document.quirks_mode` was name-only. These tests pin the capture and the
spec's quirks-mode table.

The mode is *recorded*, not acted on: unitless lengths and the alternate box
model are layout concerns and belong to Phase 3.
"""

import pytest

from mayshay.dom.node import serialize
from mayshay.htmlparse.tokenizer import DoctypeToken, Tokenizer
from mayshay.htmlparse.treebuilder import (
    LIMITED_QUIRKS_PREFIXES,
    QUIRKS_EXACT,
    QUIRKS_PREFIXES,
    QUIRKS_SYSTEM_ID,
    QUIRKS_UNLESS_SYSTEM_ID,
    parse,
)
from tests.support.dat import load_tree_tests
from tests.support.marks import requires_corpus


def doctype(src):
    return next(t for t in Tokenizer(src).tokenize() if isinstance(t, DoctypeToken))


def test_public_identifier_captured():
    dt = doctype('<!DOCTYPE html PUBLIC "-//W3C//DTD HTML 4.01//EN">')
    assert dt.name == "html"
    assert dt.public_id == "-//W3C//DTD HTML 4.01//EN"
    assert dt.system_id is None


def test_system_identifier_captured():
    dt = doctype('<!DOCTYPE html SYSTEM "about:legacy-compat">')
    assert dt.public_id is None
    assert dt.system_id == "about:legacy-compat"


def test_both_identifiers_captured():
    dt = doctype(
        '<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Strict//EN" '
        '"http://www.w3.org/TR/xhtml1/DTD/xhtml1-strict.dtd">'
    )
    assert dt.public_id == "-//W3C//DTD XHTML 1.0 Strict//EN"
    assert dt.system_id.endswith("xhtml1-strict.dtd")


def test_single_quoted_identifiers():
    dt = doctype("<!DOCTYPE html PUBLIC '-//W3C//DTD HTML 4.01//EN'>")
    assert dt.public_id == "-//W3C//DTD HTML 4.01//EN"


def test_identifier_matching_is_case_insensitive_on_keywords():
    dt = doctype('<!DOCTYPE html public "-//W3C//DTD HTML 4.01//EN">')
    assert dt.public_id == "-//W3C//DTD HTML 4.01//EN"


@pytest.mark.parametrize(
    "src,expected",
    [
        ("<!DOCTYPE html>", "no-quirks"),
        ('<!DOCTYPE html SYSTEM "about:legacy-compat">', "no-quirks"),
        ("<!DOCTYPE foo>", "quirks"),
        ("", "quirks"),
        ("<p>x", "quirks"),
        ('<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.01 Transitional//EN">', "quirks"),
        # NOT quirks, and the task plan said otherwise. "-//W3C//DTD HTML
        # 4.0//EN" is HTML 4.0 *Strict*; the spec's list carries
        # "-//W3C//DTD HTML 4.0 Frameset//" and "-//W3C//DTD HTML 4.0
        # Transitional//" but no bare "-//W3C//DTD HTML 4.0//" entry, and
        # html5lib agrees. Verified against the spec list, all 55 of it.
        ('<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.0//EN">', "no-quirks"),
        # HTML 4.0 Transitional, which *is* on the list, for contrast.
        ('<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.0 Transitional//EN">', "quirks"),
        # The 4.01 hinge, all three ways. A missing system identifier and an
        # empty one are both quirks; the spec says "missing or the empty
        # string", where html5lib tests only for missing.
        (
            '<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.01 Transitional//EN" "">',
            "quirks",
        ),
        (
            '<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.01 Transitional//EN" '
            '"http://www.w3.org/TR/html4/loose.dtd">',
            "limited-quirks",
        ),
        # An empty PUBLIC identifier is present-but-empty, not missing, and
        # matches nothing.
        ('<!DOCTYPE html PUBLIC "">', "no-quirks"),
        # Case-insensitive on the identifier, not just on the keyword.
        ('<!DOCTYPE html PUBLIC "-//w3o//dtd w3 html strict 3.0//en//">', "quirks"),
        # An unnamed DOCTYPE has no name, so it is not "html".
        ("<!DOCTYPE>", "quirks"),
        (
            '<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.01 Frameset//EN" '
            '"http://www.w3.org/TR/html4/frameset.dtd">',
            "limited-quirks",
        ),
        (
            '<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Frameset//EN" '
            '"http://www.w3.org/TR/xhtml1/DTD/xhtml1-frameset.dtd">',
            "limited-quirks",
        ),
    ],
)
def test_document_mode_classification(src, expected):
    assert parse(src).mode == expected


def test_quirks_mode_bool_still_works_and_is_derived():
    doc = parse("<!DOCTYPE foo>")
    assert doc.mode == "quirks"
    assert doc.quirks_mode is True
    assert parse("<!DOCTYPE html>").quirks_mode is False


def test_force_quirks_still_means_tokenizer_error_only():
    """Phase 1 separated these deliberately; keep them separate."""
    assert doctype("<!DOCTYPE foo>").force_quirks is False
    assert doctype("<!DOCTYPE html").force_quirks is True


def test_quirks_table_matches_the_spec_shape():
    """The table is the highest-risk thing here: an entry dropped in a future
    edit misclassifies silently -- nothing crashes, a page just lays out in the
    wrong mode. Counted against the HTML spec section "The 'initial' insertion
    mode": 55 quirks prefixes, 3 exact matches, 2 limited-quirks prefixes, and
    the 2 HTML 4.01 prefixes that switch on the system identifier.
    """
    assert len(QUIRKS_PREFIXES) == 55
    assert len(set(QUIRKS_PREFIXES)) == 55, "duplicate entry"
    assert len(QUIRKS_EXACT) == 3
    assert len(LIMITED_QUIRKS_PREFIXES) == 2
    assert len(QUIRKS_UNLESS_SYSTEM_ID) == 2
    # Comparison lowercases the identifier, so a non-lowercase entry can never
    # match.
    every = (
        QUIRKS_PREFIXES
        + LIMITED_QUIRKS_PREFIXES
        + QUIRKS_UNLESS_SYSTEM_ID
        + tuple(QUIRKS_EXACT)
        + (QUIRKS_SYSTEM_ID,)
    )
    assert [e for e in every if e != e.lower()] == []
    # The 4.01 pair is deliberately NOT in the long list: it lives in its own
    # spec clause and folding it in would lose limited-quirks entirely.
    assert not set(QUIRKS_UNLESS_SYSTEM_ID) & set(QUIRKS_PREFIXES)


def test_every_quirks_prefix_actually_classifies_as_quirks():
    """Cheap end-to-end sweep of all 55, which the nine cases above cannot do."""
    for prefix in QUIRKS_PREFIXES:
        src = f'<!DOCTYPE html PUBLIC "{prefix.upper()}EN">'
        assert parse(src).mode == "quirks", prefix


# Deferred, with the cause named. Same ledger discipline as KNOWN_MISSES in
# test_html5lib_tree.py, and strict so it cannot rot into a mute button.
KNOWN_MISSES = {
    "doctype01.dat:30": (
        "not the quirks table and not identifier capture: the DOCTYPE itself "
        "is parsed correctly (`<!DOCTYPE root-element>`). The bogus-DOCTYPE "
        "scan ends at the '>' of an internal `-->`, leaving '\n]>' as body "
        "text, and the leading newline should be split off and ignored by "
        "'before head'. Tokenizer deviation #1 coalesces it into one character "
        "token and TreeBuilder._is_space is all-or-nothing -- the same gap "
        "already pinned as tests1.dat:50 in test_html5lib_tree.py"
    ),
}


def _doctype_corpus_cases():
    """Every doctype01.dat case, which is the only broad check on the table.

    Nine hand-written classifications cannot cover 55 prefixes. These cases
    exercise identifiers the unit tests never mention.
    """
    try:
        return [
            c for c in load_tree_tests("doctype01.dat")
            if c.fragment is None and c.script != "on"
        ]
    except FileNotFoundError:
        return []


def _doctype_corpus_params():
    for case in _doctype_corpus_cases():
        marks = []
        if case.id in KNOWN_MISSES:
            marks.append(pytest.mark.xfail(strict=True, reason=KNOWN_MISSES[case.id]))
        yield pytest.param(case, marks=marks, id=case.id)


@requires_corpus
@pytest.mark.parametrize("case", list(_doctype_corpus_params()))
def test_doctype_corpus_round_trips(case):
    """The serialized tree must match, which pins identifier capture.

    Phase 1 could not represent public/system identifiers at all, so these
    cases were unreachable. If one still fails, say whether it is the table,
    the identifier capture, or an unrelated tree-construction gap.
    """
    assert serialize(parse(case.data)) == case.document
