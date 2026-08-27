#!/usr/bin/env python3
"""Tree-construction parse-error agreement sweep over the html5lib-tests corpus.

Task B established that our tree-construction parse errors agree with
html5lib's #errors on 404 of 474 curated corpus cases. Tasks C, D and J each
had to re-derive that number from scratch in /tmp because nothing in the repo
computed it -- the same situation that produced scripts/conformance_report.py
in Phase 1. This is that script's counterpart for parse errors: same shape,
same flags, same --diff convention.

Compare sets of disagreeing ids, never bare totals -- equal totals routinely
hide an equal-sized swap.

    .venv/bin/python scripts/error_report.py --out before.txt
    ... make the change ...
    .venv/bin/python scripts/error_report.py --out after.txt
    .venv/bin/python scripts/error_report.py --diff before.txt after.txt

"Curated" cases and TREE_ERROR_CODES are not redefined here: both come from
tests/support/parse_errors.py, imported rather than reimplemented, so this
report can never select a different set of cases than the pytest suite
(tests/htmlparse/test_parse_errors.py, which imports the same module) actually
checks. That module is deliberately pytest-free -- importing a test_*.py file
here would drag in pytest and pay for that module's test-collection side
effects (building its parametrize list) just to run a measurement script.

Agreement is a multiset comparison of codes, positions never compared (see
test_corpus_error_codes_match_as_a_multiset for why). A disagreeing case is
classified into one or both of:
  - extra:   we emit a code the corpus does not expect (or too many of one)
  - missing: the corpus expects a code we never emit (or not enough of one)
Task B found these call for opposite responses -- stop emitting the wrong
thing, versus start emitting the missing thing -- so they are always reported
and diffed separately, never collapsed into one "wrong" bucket.

A TreeBuilder crash is treated as emitting no codes at all, which -- since a
curated case's expected codes are never empty -- always lands the case in
"missing" and never in "extra". This convention is a judgement call (there is
no surviving artifact of Task B's original throwaway script to confirm it
matches); note it here so a future reader does not have to guess at it the
way this task had to guess at Task B's.
"""

from __future__ import annotations

import argparse
import collections
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from mayshay.htmlparse.treebuilder import TreeBuilder  # noqa: E402
from tests.support.dat import TREE_DIR, load_tree_tests  # noqa: E402
from tests.support.parse_errors import curated_codes  # noqa: E402


def case_id(test) -> str:
    """Same convention as conformance_report.case_id: qualify by the parent
    directory so a future filename collision under tree-construction/ cannot
    silently merge two cases into one id."""
    path = Path(test.path)
    if path.parent.name == "tree-construction":
        return f"{path.name}:{test.index}"
    return f"{path.parent.name}/{path.name}:{test.index}"


def run(files: tuple[str, ...]) -> tuple[list[str], list[str], list[str]]:
    """Return (agreeing, extra, missing) case ids, across the given files (or
    the whole corpus if `files` is empty).

    extra and missing are not mutually exclusive: a single disagreeing case
    can both emit a code the corpus doesn't expect and fail to emit one it
    does, and would then show up in both lists.
    """
    agreeing, extra, missing = [], [], []
    for case in load_tree_tests(*files):
        expected = curated_codes(case)
        if expected is None:
            continue
        cid = case_id(case)
        try:
            tb = TreeBuilder(case.data)
            tb.build()
            actual = [code for _, code in tb.errors]
        except Exception:
            actual = []  # a crash agrees with nothing; see module docstring
        actual_c = collections.Counter(actual)
        expected_c = collections.Counter(expected)
        if actual_c == expected_c:
            agreeing.append(cid)
            continue
        if actual_c - expected_c:
            extra.append(cid)
        if expected_c - actual_c:
            missing.append(cid)
    return agreeing, extra, missing


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--out", type=Path, help="write the sorted disagreeing ids here")
    ap.add_argument(
        "--files", nargs="*", default=[], help="limit to these .dat file names"
    )
    ap.add_argument(
        "--diff",
        nargs=2,
        metavar=("BEFORE", "AFTER"),
        type=Path,
        help="difference two saved runs instead of parsing anything",
    )
    args = ap.parse_args()

    if args.diff:
        before = set(args.diff[0].read_text().split())
        after = set(args.diff[1].read_text().split())
        fixed, broken = sorted(before - after), sorted(after - before)
        print(f"newly agreeing ({len(fixed)}):")
        for i in fixed:
            print(f"  + {i}")
        print(f"newly disagreeing ({len(broken)}):")
        for i in broken:
            print(f"  - {i}")
        return 1 if broken else 0

    if not TREE_DIR.is_dir():
        print(
            "html5lib-tests submodule not checked out; run "
            "`git submodule update --init`",
            file=sys.stderr,
        )
        return 2

    agreeing, extra, missing = run(tuple(args.files))
    disagreeing = sorted(set(extra) | set(missing))
    total = len(agreeing) + len(disagreeing)
    print(f"parse-error agreement: {len(agreeing)}/{total}")
    print(f"  unexpected code emitted (extra):    {len(extra)}")
    print(f"  expected code never emitted (missing): {len(missing)}")
    if args.out:
        args.out.write_text("\n".join(disagreeing) + "\n")
        print(f"disagreeing ids -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
