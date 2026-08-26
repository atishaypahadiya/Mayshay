import pytest

from tests.support.dat import ROOT

requires_corpus = pytest.mark.skipif(
    not (ROOT / "tree-construction").is_dir(),
    reason="html5lib-tests submodule not checked out; run "
    "`git submodule update --init`",
)
