"""The html5lib-tests tokenizer corpus, restricted to the raw-text states and
(as of Task 4) the named/numeric character-reference corpus.

Task 3 replaced a lookahead hack with the spec's RCDATA / RAWTEXT / ScriptData
state families -- roughly 26 states. Hand-written tests under-constrain that:
most of them pass against the old hack too, because the hack was crude rather
than wrong on simple input. This module pins the rewrite against the corpus
instead, so the states are held to the behaviour the spec actually specifies.

The raw-text section's scope is deliberately narrow: only cases whose
`initialStates` name a state Task 3 owns. Task 4 adds a second section below
covering `entities.test` and `namedEntities.test` -- both pure Data-state
corpora -- for the same reason: hand-written entity tests under-constrain a
decoder that replaces "pass text through raw" with real decoding, since a
no-op decoder would still pass most hand-written cases that don't involve an
actual ampersand.
"""

from __future__ import annotations

import pytest

from mayshay.htmlparse.tokenizer import (
    CharacterToken,
    CommentToken,
    DoctypeToken,
    EndTagToken,
    StartTagToken,
    Tokenizer,
)
from tests.support.dat import TOKENIZER_DIR, load_tokenizer_tests
from tests.support.marks import requires_corpus

# html5lib's initialStates names -> this tokenizer's state strings. Only the
# three families Task 3 owns; "Data state", "PLAINTEXT state" and
# "CDATA section state" cases are out of scope here.
STATE_NAMES = {
    "RCDATA state": "rcdata",
    "RAWTEXT state": "rawtext",
    "Script data state": "script_data",
}
# "PLAINTEXT state" is deliberately absent, which silently drops the corpus's
# PLAINTEXT cases (~52) rather than xfailing them. There is no tokenizer state
# to map it to -- see tokenizer deviation #6 -- so there is nothing to pin.
# When PLAINTEXT lands, add it here and the cases start being enforced.

# Cases known to fail, each with the reason it is deferred. Keyed by
# (description, html5lib state name) -- verified unique across the subset.
#
# These are marked strict-xfail: if one starts passing, or if a case not
# listed here fails, the suite goes red. That is the point -- the set is a
# ledger of deferred work, not a mute button.
KNOWN_MISSES = {
    # -- double-escaped script data: deviation #3 ------------------------
    ("</script> in script HTML comment - double escaped", "Script data state"): (
        "script data double-escaped states not implemented; same gap as the "
        "xfail in test_rawtext.py::test_double_escaped_script"
    ),
    (
        "</script> in script HTML comment - double escaped with nested <script>",
        "Script data state",
    ): (
        "script data double-escaped states not implemented; same gap as the "
        "xfail in test_rawtext.py::test_double_escaped_script"
    ),
    # -- pre-existing comment-state gap, unrelated to the raw-text states --
    #
    # The raw-text half of this input is tokenized correctly; the divergence
    # is in `<!-->` *after* returning to the data state. Our comment states
    # lack the spec's comment start / comment end states, so "abrupt closing
    # of empty comment" is not implemented. Reproduces on the pre-Task-3
    # tokenizer: Tokenizer("<!-->baz") yields CommentToken(">baz") there too.
    (
        "End tag surrounded by bogus comment in RCDATA or RAWTEXT",
        "RCDATA state",
    ): "comment start / comment end states not implemented (pre-existing)",
    (
        "End tag surrounded by bogus comment in RCDATA or RAWTEXT",
        "RAWTEXT state",
    ): "comment start / comment end states not implemented (pre-existing)",
}


def _to_corpus_shape(token) -> list | None:
    """Adapt one of our token dataclasses to html5lib's list descriptor."""
    if isinstance(token, CharacterToken):
        return ["Character", token.data]
    if isinstance(token, StartTagToken):
        entry = ["StartTag", token.name, dict(token.attrs)]
        if token.self_closing:
            entry.append(True)
        return entry
    if isinstance(token, EndTagToken):
        return ["EndTag", token.name]
    if isinstance(token, CommentToken):
        return ["Comment", token.data]
    if isinstance(token, DoctypeToken):
        # The corpus's fifth field is "correctness", the inverse of
        # force-quirks. Fields three and four were hardcoded to None while the
        # tokenizer discarded the identifiers; Task C captures them, so they
        # are reported for real.
        return [
            "DOCTYPE",
            token.name,
            token.public_id,
            token.system_id,
            not token.force_quirks,
        ]
    # EOFToken: the corpus has no descriptor for it.
    return None


def _coalesce(tokens: list[list]) -> list[list]:
    """Merge adjacent Character descriptors into one.

    We coalesce text runs (deviation #1) and the corpus mostly does too, but
    its convention is not guaranteed, so normalise both sides rather than
    assume. As of the pinned submodule commit no expected output in this
    subset has adjacent Character tokens, so this is a no-op on the expected
    side today -- it exists so a corpus bump can't silently start failing.
    """
    out: list[list] = []
    for token in tokens:
        if token[0] == "Character" and out and out[-1][0] == "Character":
            out[-1] = ["Character", out[-1][1] + token[1]]
        else:
            out.append(list(token))
    return out


def _tokenize(source: str, state: str, last_start_tag: str | None) -> list[list]:
    tokenizer = Tokenizer(source)
    tokenizer.switch_to(state, last_start_tag=last_start_tag)
    shaped = [_to_corpus_shape(t) for t in tokenizer.tokenize()]
    return _coalesce([t for t in shaped if t is not None])


def _cases():
    """(id, source, state, last_start_tag, expected) for every raw-text case."""
    for test in load_tokenizer_tests():
        for state_name in test.initial_states:
            state = STATE_NAMES.get(state_name)
            if state is None:
                continue
            key = (test.description, state_name)
            param = (test.input, state, test.last_start_tag, test.output)
            marks = []
            if key in KNOWN_MISSES:
                marks.append(
                    pytest.mark.xfail(strict=True, reason=KNOWN_MISSES[key])
                )
            yield pytest.param(
                *param, marks=marks, id=f"{state_name}: {test.description}"
            )


@requires_corpus
@pytest.mark.parametrize("source,state,last_start_tag,expected", list(_cases()))
def test_html5lib_raw_text_case(source, state, last_start_tag, expected):
    assert _tokenize(source, state, last_start_tag) == _coalesce(expected)


@requires_corpus
def test_raw_text_corpus_is_not_empty():
    """A loader regression that silently yields nothing must not read green."""
    cases = list(_cases())
    assert len(cases) == 226, (
        f"expected 226 raw-text cases from the pinned corpus, got {len(cases)}; "
        "if the submodule moved, re-check KNOWN_MISSES before updating this"
    )


# --------------------------------------------------------------------------
# Character reference corpus: entities / namedEntities / numericEntities (Task 4)
# --------------------------------------------------------------------------
#
# All three files consist entirely of "Data state" cases -- no initialStates/
# lastStartTag plumbing needed, unlike the raw-text section above. Coverage
# includes the named-reference table end to end (namedEntities.test), the
# legacy-attribute-rule and numeric-reference edge cases (entities.test), and
# the numeric-reference boundaries -- surrogates, out-of-range, overflow, the
# Windows-1252 C1 remapping -- from numericEntities.test.
#
# numericEntities.test is the only Data-state file adopted so far beyond the
# two entity ones. The remaining ~2,400 Data-state corpus cases (domjs, test1
# through test4, unicodeChars, xmlViolation) are a phase-2 task: they exercise
# the tag / attribute / comment / DOCTYPE states, where roughly 500 cases fail
# against the tokenizer's documented deviations and need a written ledger
# before they can be adopted without muting anything.

ENTITY_FILES = ("entities.test", "namedEntities.test", "numericEntities.test")

# Keyed by (filename, description, input) rather than just (filename,
# description): entities.test alone has three descriptions reused across
# several inputs (e.g. "Windows-1252 REPLACEMENT CHAR numeric entity." covers
# five different code points), so description isn't unique within a file.
ENTITY_KNOWN_MISSES: dict[tuple[str, str, str], str] = {}


def _tokenize_data(source: str) -> list[list]:
    shaped = [_to_corpus_shape(t) for t in Tokenizer(source).tokenize()]
    return _coalesce([t for t in shaped if t is not None])


def _entity_cases():
    """(id, source, expected) for every entities.test / namedEntities.test case."""
    for filename in ENTITY_FILES:
        for test in load_tokenizer_tests(filename):
            key = (filename, test.description, test.input)
            marks = []
            if key in ENTITY_KNOWN_MISSES:
                marks.append(
                    pytest.mark.xfail(strict=True, reason=ENTITY_KNOWN_MISSES[key])
                )
            yield pytest.param(
                test.input,
                test.output,
                marks=marks,
                id=f"{filename}: {test.description}",
            )


@requires_corpus
@pytest.mark.parametrize("source,expected", list(_entity_cases()))
def test_html5lib_entity_case(source, expected):
    assert _tokenize_data(source) == _coalesce(expected)


@requires_corpus
def test_entity_corpus_is_not_empty():
    """A loader regression that silently yields nothing must not read green."""
    cases = list(_entity_cases())
    assert len(cases) == 4626, (
        f"expected 4626 entity cases from the pinned corpus, got {len(cases)}; "
        "if the submodule moved, re-check ENTITY_KNOWN_MISSES before updating this"
    )


# --------------------------------------------------------------------------
# DOCTYPE corpus: every Data-state case that expects a DOCTYPE token (Task C)
# --------------------------------------------------------------------------
#
# Task C replaced the phase-1 scan-to-'>' DOCTYPE hack with the spec's sixteen
# DOCTYPE states. Hand-written tests under-constrain that for exactly the
# reason Task 3's raw-text rewrite needed a corpus: most of them pass against
# the old hack too, which was crude rather than wrong on well-formed input. The
# interesting behaviour is all in the malformed cases -- a missing quote, an
# abrupt '>' inside an identifier, a keyword run together with its identifier,
# EOF in each of the fifteen non-bogus states -- and there are 855 of those
# here against roughly a dozen written by hand.
#
# SELECTION RULE: initialStates is exactly ["Data state"] and the EXPECTED
# output contains a DOCTYPE descriptor. Keying on the expected side rather than
# on the input text keeps the filter independent of what our tokenizer happens
# to do, so a case we wrongly fail to produce a DOCTYPE for is still selected
# and still fails.
#
# The rule has one hole, measured rather than assumed: six Data-state cases
# whose input mentions "<!d" expect something other than a DOCTYPE -- bogus
# comments, `<!doc...`. Five pass. The sixth (test4.test, "<!doc" + NUL) fails
# on the NUL deviation, and it is a comment-state case rather than a DOCTYPE
# one, so it belongs to whichever task adopts the comment corpus and is
# deliberately not laundered through the ledger below.
#
# This section does NOT adopt the remaining ~1,550 Data-state cases (tags,
# attributes, comments, PLAINTEXT); those still need the written ledger the
# note above ENTITY_FILES describes.

_NUL = (
    "NUL is passed through rather than replaced with U+FFFD (tokenizer "
    "deviation #5), so the name or identifier keeps a literal U+0000. Nothing "
    "DOCTYPE-specific is wrong -- the same deviation fails the equivalent "
    "cases in the tag-name and attribute states, which are not adopted yet."
)

# All twelve failures among the 855, and every one is the NUL deviation.
# Keyed by (filename, description, input) for the same reason as
# ENTITY_KNOWN_MISSES; uniqueness is asserted below rather than assumed.
DOCTYPE_KNOWN_MISSES: dict[tuple[str, str, str], str] = {
    ("test3.test", "<!DOCTYPE\\u0000", "<!DOCTYPE\x00"): _NUL,
    ("test3.test", "<!DOCTYPE \\u0000", "<!DOCTYPE \x00"): _NUL,
    ("test3.test", "<!DOCTYPE a\\u0000", "<!DOCTYPE a\x00"): _NUL,
    ("test3.test", '<!DOCTYPE a PUBLIC"\\u0000', '<!DOCTYPE a PUBLIC"\x00'): _NUL,
    ("test3.test", "<!DOCTYPE a PUBLIC'\\u0000", "<!DOCTYPE a PUBLIC'\x00"): _NUL,
    ("test3.test", '<!DOCTYPE a SYSTEM"\\u0000', '<!DOCTYPE a SYSTEM"\x00'): _NUL,
    ("test3.test", "<!DOCTYPE a SYSTEM'\\u0000", "<!DOCTYPE a SYSTEM'\x00"): _NUL,
    ("test3.test", "<!DOCTYPEa\\u0000", "<!DOCTYPEa\x00"): _NUL,
    ("test3.test", '<!DOCTYPEa PUBLIC"\\u0000', '<!DOCTYPEa PUBLIC"\x00'): _NUL,
    ("test3.test", "<!DOCTYPEa PUBLIC'\\u0000", "<!DOCTYPEa PUBLIC'\x00"): _NUL,
    ("test3.test", '<!DOCTYPEa SYSTEM"\\u0000', '<!DOCTYPEa SYSTEM"\x00'): _NUL,
    ("test3.test", "<!DOCTYPEa SYSTEM'\\u0000", "<!DOCTYPEa SYSTEM'\x00"): _NUL,
}


def _doctype_corpus_files() -> list[str]:
    """Every fixture file, globbed rather than listed.

    Five files carry DOCTYPE cases today. Hardcoding those five would let a
    corpus bump that adds a sixth pass silently; globbing means the collection
    count below moves instead, which is the loud failure we want.
    """
    if not TOKENIZER_DIR.is_dir():
        return []
    return sorted(p.name for p in TOKENIZER_DIR.glob("*.test"))


def _expects_doctype(test) -> bool:
    return any(
        descriptor and descriptor[0] == "DOCTYPE" for descriptor in test.output
    )


def _doctype_keys_and_tests():
    for filename in _doctype_corpus_files():
        for test in load_tokenizer_tests(filename):
            if test.initial_states != ["Data state"] or not _expects_doctype(test):
                continue
            yield (filename, test.description, test.input), test


def _doctype_cases():
    for key, test in _doctype_keys_and_tests():
        marks = []
        if key in DOCTYPE_KNOWN_MISSES:
            marks.append(
                pytest.mark.xfail(strict=True, reason=DOCTYPE_KNOWN_MISSES[key])
            )
        yield pytest.param(
            test.input, test.output, marks=marks, id=f"{key[0]}: {test.description}"
        )


@requires_corpus
@pytest.mark.parametrize("source,expected", list(_doctype_cases()))
def test_html5lib_doctype_case(source, expected):
    assert _tokenize_data(source) == _coalesce(expected)


@requires_corpus
def test_doctype_corpus_is_not_empty():
    """A loader regression that silently yields nothing must not read green."""
    cases = list(_doctype_cases())
    assert len(cases) == 855, (
        f"expected 855 DOCTYPE cases from the pinned corpus, got {len(cases)}; "
        "if the submodule moved, re-check DOCTYPE_KNOWN_MISSES before updating "
        "this"
    )


@requires_corpus
def test_doctype_ledger_is_keyed_uniquely_and_has_no_stale_entries():
    """Two ways this ledger could quietly stop meaning anything.

    A duplicate key would let one entry mask another case; a stale key would
    xfail nothing at all while still reading as deferred work.
    """
    keys = [key for key, _ in _doctype_keys_and_tests()]
    assert len(keys) == len(set(keys)), "(file, description, input) is not unique"
    stale = sorted(set(DOCTYPE_KNOWN_MISSES) - set(keys))
    assert not stale, f"DOCTYPE_KNOWN_MISSES entries match no case: {stale}"
