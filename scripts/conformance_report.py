#!/usr/bin/env python3
"""Tree-construction conformance sweep over the whole html5lib-tests corpus.

The pytest run in tests/htmlparse/test_html5lib_tree.py only covers the
in-scope files and reports pass/fail through xfail bookkeeping. This script
answers the question that actually matters when a tree-builder change lands:
*which* cases changed, across all of the corpus.

Compare sets of failing ids, never totals -- equal totals routinely hide an
equal-sized swap.

    .venv/bin/python scripts/conformance_report.py --out before.txt
    ... make the change ...
    .venv/bin/python scripts/conformance_report.py --out after.txt
    .venv/bin/python scripts/conformance_report.py --diff before.txt after.txt

Fragment cases and script-on cases are excluded, matching the pytest
harness: they would fail for reasons that say nothing about the tree builder
(no parse-fragment entry point, no JS runtime).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from mayshay.dom.node import serialize  # noqa: E402
from mayshay.htmlparse.treebuilder import TreeBuilder  # noqa: E402
from tests.support.dat import TREE_DIR, load_tree_tests  # noqa: E402


def case_id(test) -> str:
    """Unique across the corpus: tree-construction/scripted/ shares no file
    name with the top level today, but qualifying the subdirectory means a
    future collision cannot silently merge two cases into one id."""
    path = Path(test.path)
    if path.parent.name == "tree-construction":
        return f"{path.name}:{test.index}"
    return f"{path.parent.name}/{path.name}:{test.index}"


def run(files: tuple[str, ...]) -> tuple[list[str], list[str]]:
    cases = [
        t
        for t in load_tree_tests(*files)
        if t.fragment is None and t.script != "on"
    ]
    passing, failing = [], []
    for test in cases:
        try:
            ok = serialize(TreeBuilder(test.data).build()) == test.document
        except Exception:
            ok = False  # a crash is a failure, not a reason to stop the sweep
        (passing if ok else failing).append(case_id(test))
    return passing, failing


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, help="write the sorted failing ids here")
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
        print(f"newly passing ({len(fixed)}):")
        for i in fixed:
            print(f"  + {i}")
        print(f"newly failing ({len(broken)}):")
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

    passing, failing = run(tuple(args.files))
    total = len(passing) + len(failing)
    print(f"all files: {len(passing)}/{total}")
    for name in ("tests1.dat",):
        subset = [i for i in passing + failing if i.startswith(name + ":")]
        if subset:
            hit = sum(1 for i in passing if i.startswith(name + ":"))
            print(f"{name}: {hit}/{len(subset)}")
    if args.out:
        args.out.write_text("\n".join(sorted(failing)) + "\n")
        print(f"failing ids -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
