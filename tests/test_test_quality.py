"""Tests about the tests: assertions that cannot fail for the right reason.

One test in this suite passed while never reaching the code it named. It
wrapped a `pytest.raises(Exception)` around a block whose FIRST statement
constructed a stub with its arguments in the wrong order; the resulting
`TypeError` satisfied the assertion, and the function under test was never
called. It was green, it was committed, and nothing downstream could tell.

That is the same shape as `docs/measurement-hazards.md` instance seventeen
-- a bucket that legitimately contains something can never be read as an
alarm -- applied to an exception assertion. A `raises` block that can be
satisfied by setup code is a residual bucket with something in it.

Two rules, checked mechanically rather than remembered:

* **One statement per `raises` block.** Anything else can be satisfied by a
  line that is not the subject. Hoist the setup above the block.
* **`AssertionError` needs a `match=`.** A failing bare `assert` inside the
  block raises `AssertionError` too, so without a pattern the block cannot
  distinguish the code under test failing from the test's own assertion
  failing.

Deliberately not a lint config: this is a claim about this suite, it fails
with the offending file and line, and it is executed on every run.
"""

from __future__ import annotations

import ast
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
TESTS = ROOT / "tests"

# Vendored upstream fixtures, not ours to restyle.
SKIP = ("html5lib-tests",)


def _raises_blocks():
    """(file, line, exception, statement count, has match=) for every block."""
    for path in sorted(TESTS.rglob("*.py")):
        if any(part in str(path) for part in SKIP):
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:  # pragma: no cover -- a broken test file fails elsewhere
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.With):
                continue
            for item in node.items:
                call = item.context_expr
                if not (
                    isinstance(call, ast.Call)
                    and ast.unparse(call.func).endswith("raises")
                ):
                    continue
                yield (
                    path.relative_to(ROOT),
                    node.lineno,
                    ast.unparse(call.args[0]) if call.args else "<none>",
                    len(node.body),
                    any(k.arg == "match" for k in call.keywords),
                )


def test_the_sweep_is_not_silently_empty():
    """The guard every corpus sweep in this repo carries, for the same reason:
    a rule that checks nothing is indistinguishable from a rule that passes."""
    assert sum(1 for _ in _raises_blocks()) >= 20


def test_no_raises_block_catches_a_bare_exception():
    """`pytest.raises(Exception)` cannot fail for the right reason. It is
    satisfied by a TypeError from a mistyped constructor, an AttributeError
    from a renamed method, or an ImportError -- none of which is the
    behaviour any test means to pin."""
    bad = [
        f"{f}:{line} raises({exc})"
        for f, line, exc, _, _ in _raises_blocks()
        if exc in ("Exception", "BaseException")
    ]
    assert not bad, "bare exception assertions:\n  " + "\n  ".join(bad)


def test_every_raises_block_wraps_exactly_one_statement():
    """Setup inside the block can satisfy the assertion. Hoist it out, so the
    only statement that can raise is the one the test is about."""
    bad = [
        f"{f}:{line} raises({exc}) wraps {n} statements"
        for f, line, exc, n, _ in _raises_blocks()
        if n > 1
    ]
    assert not bad, "raises blocks with setup inside them:\n  " + "\n  ".join(bad)


def test_an_assertion_error_expectation_pins_its_message():
    """A failing `assert` inside the block raises `AssertionError` too, so
    without `match=` the block cannot tell the code under test failing from
    the test's own assertion failing."""
    bad = [
        f"{f}:{line}"
        for f, line, exc, _, has_match in _raises_blocks()
        if exc == "AssertionError" and not has_match
    ]
    assert not bad, "raises(AssertionError) without match=:\n  " + "\n  ".join(bad)
