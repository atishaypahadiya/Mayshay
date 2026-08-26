"""The html5lib-tests tokenizer corpus, restricted to the raw-text states.

Task 3 replaced a lookahead hack with the spec's RCDATA / RAWTEXT / ScriptData
state families -- roughly 26 states. Hand-written tests under-constrain that:
most of them pass against the old hack too, because the hack was crude rather
than wrong on simple input. This module pins the rewrite against the corpus
instead, so the states are held to the behaviour the spec actually specifies.

Scope is deliberately narrow: only cases whose `initialStates` name a state
this task owns. Data-state coverage of the whole corpus needs entity decoding
(Task 4) and belongs in its own module.
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
from tests.support.dat import load_tokenizer_tests
from tests.support.marks import requires_corpus

# html5lib's initialStates names -> this tokenizer's state strings. Only the
# three families Task 3 owns; "Data state", "PLAINTEXT state" and
# "CDATA section state" cases are out of scope here.
STATE_NAMES = {
    "RCDATA state": "rcdata",
    "RAWTEXT state": "rawtext",
    "Script data state": "script_data",
}

# Cases known to fail, each with the reason it is deferred. Keyed by
# (description, html5lib state name) -- verified unique across the subset.
#
# These are marked strict-xfail: if one starts passing, or if a case not
# listed here fails, the suite goes red. That is the point -- the set is a
# ledger of deferred work, not a mute button.
KNOWN_MISSES = {
    # -- entity decoding in RCDATA: deviation #2, Task 4 ------------------
    ("RCDATA w/ an entity", "RCDATA state"): (
        "named character references are not decoded yet (Task 4)"
    ),
    ("Non BMP-charref in RCDATA", "RCDATA state"): (
        "named character references are not decoded yet (Task 4)"
    ),
    ("Commented entities in RCDATA", "RCDATA state"): (
        "named character references are not decoded yet (Task 4)"
    ),
    # -- double-escaped script data: deviation #4 ------------------------
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
        # We don't parse public/system identifiers (deviation #3). The
        # corpus's fifth field is "correctness", the inverse of force-quirks.
        return ["DOCTYPE", token.name, None, None, not token.force_quirks]
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
