#!/usr/bin/env python3
"""Compare this engine's line boxes against Chrome 151, fragment by fragment.

    .venv/bin/python scripts/chrome_compare.py
    .venv/bin/python scripts/chrome_compare.py --list
    .venv/bin/python scripts/chrome_compare.py --only hyphen sub

Phase 3 Task D2's numeric comparison, made reproducible. Every Chrome number
quoted in `tests/layout/test_linebox.py`, `docs/fonts.md` and
`src/mayshay/layout/linebreak.py` came out of this script.

## What it compares, and why it is two suites and not one

**Chrome rounds this font's vertical metrics to whole pixels** -- ascent
14, descent 3, line gap 1 at 16px where the font's own numbers are
14.484375, 3.390625 and 0.523438 -- and it floors the half-leading. A
single comparison at 16px therefore measures Chrome's rounding as much as
it measures layout, and every row disagrees by a plausible fraction of a
pixel for a reason that has nothing to do with this engine.

So:

* the **horizontal** suite runs at 16px and compares `x` and `width`, with
  the tolerance `docs/fonts.md` derives -- `runs / 64` px, Chrome's
  LayoutUnit, and *not* a round number chosen to make a test pass;
* the **vertical** suite runs at `font-size: 2048px`, this font's
  `unitsPerEm`, where ascent 1854, descent 434 and line gap 67 are all
  whole pixels and there is nothing left to round. A disagreement there is
  a real one.

## Fragments, not boxes

`getClientRects()` on an inline element returns **one rectangle per line
fragment**, which is the same answer `DOM.getContentQuads` gives and is
*not* what `DOM.getBoxModel` gives: for a span across three lines that
returns their union, which matches none of them. See
`docs/measurement-hazards.md` instance 3. Chrome also returns a zero-width
rectangle at each `<br>`, which is the break and not a fragment, so those
are dropped.

## Standards mode, asserted

Every page this script writes begins `<!doctype html>`, and every result
carries `document.compatMode` back with it and is rejected unless it says
`CSS1Compat`.

That is not a formality. An earlier harness omitted the doctype, Chrome
rendered in quirks mode, and the line-height quirk suppressed the block
container's strut -- which produced seven plausible measurements, all
wrong in the same direction, and a behavioural decision in this engine
that fired 2,114 times on the corpus. The assertion is the mechanical
countermeasure: a check that fails a run rather than a rule someone has to
remember. `docs/measurement-hazards.md` instance fifteen.

## The startup assertion

Before anything is compared, a fixture with known geometry is measured and
every box-model edge relation is checked against it:

    content.width + padding.left + padding.right  == padding.width
    padding.width + border.left  + border.right   == border.width
    border.width  + margin.left  + margin.right   == margin.width

The Phase 3 plan asks for `model.width == border.width` as well, which pins
which edge CDP's `width` names. This script does not use CDP -- it reads
the four edges from `getBoundingClientRect()` and `getComputedStyle()` in
the page -- so the equivalent load-bearing assertion is that
`getBoundingClientRect()` is the **border** box, and that is what the
fixture's declared 420x66 border box checks. A Chrome release that changed
either convention fails here rather than shifting every number by a
constant.

## What this does not do

**It does not run over the corpus**, and the reason is a real obstacle
rather than a shortcut. `scripts/collect.py` stores each page's external
stylesheets beside it with a manifest, and this engine applies them from
there; Chrome opening the same `page.html` from disk would try to fetch
them from the network. An honest corpus comparison needs the HTML rewritten
to point at the local copies in the manifest's order, which is a change to
the collector's output rather than to this script. Until then a corpus
comparison would silently be "our engine with stylesheets against Chrome
without them", which is the shape of `docs/measurement-hazards.md`
instance 1 and would produce a large, plausible, meaningless error
distribution.

The identity scheme is here and exercised -- `(ordinal, path)` computed the
same way on both sides, so a tree divergence reports separately from a
position divergence -- because it is the part that has to be right before a
corpus run is worth building.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from mayshay.cssparse.cascade import style_document  # noqa: E402
from mayshay.cssparse.media import Viewport  # noqa: E402
from mayshay.dom.node import Element  # noqa: E402
from mayshay.htmlparse.treebuilder import parse  # noqa: E402
from mayshay.layout.block import layout_document  # noqa: E402
from mayshay.layout.boxtree import build_box_tree  # noqa: E402

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
VIEWPORT = Viewport(1280, 1024)

#: Chrome's LayoutUnit is 1/64px and it quantises per separately shaped run,
#: so three runs on a line legitimately differ by three of them.
#: `docs/fonts.md` derives this; it is not a fudge factor.
LAYOUT_UNIT = 1.0 / 64.0
HORIZONTAL_TOLERANCE = 3 * LAYOUT_UNIT

#: The vertical tolerance is **larger and derived, not chosen**. Even at
#: 2048px, where the `hhea` metrics are whole pixels, two of Chrome's own
#: roundings survive:
#:
#:   * it FLOORS the half-leading, so a 67px line gap is 33.5/33.5 here and
#:     33/34 there -- up to 0.5px;
#:   * a child at a different font size still has its ascent and descent
#:     rounded, since 2048px only makes the *block's* metrics integral --
#:     up to 0.5px more.
#:
#: 1.0px is those two added. Anything larger than that is this engine's, and
#: the harness prints the worst delta on every row so a residual inside the
#: tolerance is visible rather than hidden by it.
VERTICAL_TOLERANCE = 1.0


def stylesheet(size: int) -> str:
    """Arial named explicitly -- the whole reason this font was chosen.

    Applied to `html, body` only, so everything below inherits. Setting it
    on `div, span` as well silently breaks inheritance, which is how a
    `line-height` fixture can pass for the wrong reason.
    """
    return (
        "html,body{margin:0;padding:0}"
        f"html,body{{font-family:Arial;font-size:{size}px;line-height:normal}}"
    )


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------
#
# `data-h` marks the box both engines measure from, so a fixture's numbers
# do not depend on what is stacked above it. `data-m` marks the box under
# test.

WIDE = 'data-h="fx" style="width:99999px;white-space:nowrap"'

HORIZONTAL: dict[str, str] = {
    "wrap-3-lines": '<div data-h="fx" style="width:200px"><span data-m="s">Hello '
    "world this is a longer sentence that wraps onto several lines</span></div>",
    "wrap-nested": '<div data-h="fx" style="width:150px">alpha <span data-m="s">'
    "beta gamma delta epsilon</span> zeta</div>",
    "wrap-bold": '<div data-h="fx" style="width:150px">alpha <b data-m="s">beta '
    "gamma delta epsilon</b> zeta</div>",
    "wrap-padding": '<div data-h="fx" style="width:160px"><span data-m="s" '
    'style="padding:0 10px">aaaa bbbb cccc dddd eeee</span></div>',
    "wrap-border": '<div data-h="fx" style="width:160px"><span data-m="s" '
    'style="border-left:5px solid;border-right:7px solid">aaaa bbbb cccc dddd'
    "</span></div>",
    "hyphen": '<div data-h="fx" style="width:60px"><span data-m="s">'
    "alpha-beta-gamma</span></div>",
    "slash": '<div data-h="fx" style="width:60px"><span data-m="s">'
    "alpha/beta/gamma</span></div>",
    # `&#xa0;`, never a literal: U+00A0 and U+0020 are the same picture in
    # every terminal and do the opposite thing, and a probe written to
    # measure NBSP behaviour has already been corrupted once on this project
    # (`docs/measurement-hazards.md` instance sixteen).
    "nbsp": '<div data-h="fx" style="width:60px"><span data-m="s">'
    "alpha&#xa0;beta&#xa0;gamma</span></div>",
    "br": '<div data-h="fx" style="width:300px"><span data-m="s">one<br>two<br>'
    "three</span></div>",
    "nowrap": '<div data-h="fx" style="width:60px"><span data-m="s" '
    'style="white-space:nowrap">alpha beta gamma</span></div>',
    "pre-wrap": '<div data-h="fx" style="width:60px"><span data-m="s" '
    'style="white-space:pre-wrap">alpha   beta</span></div>',
    "break-spaces": '<div data-h="fx" style="width:45px"><span data-m="s" '
    'style="white-space:break-spaces">alpha   beta</span></div>',
    "align-center": '<div data-h="fx" style="width:200px;text-align:center">'
    '<span data-m="s">ab cd</span></div>',
    "align-right": '<div data-h="fx" style="width:200px;text-align:right">'
    '<span data-m="s">ab cd</span></div>',
    "atomic-both-sides": '<div data-h="fx" style="width:45px">a<span data-m="s" '
    'style="display:inline-block;width:40px;height:10px"></span>b</div>',
}

#: Block-container heights, which is where the strut lives.
#:
#: This family exists because the harness **did not have it** when the
#: strut rule was got wrong, and would not have caught the mistake: every
#: other fixture here puts the block's own text on the line, so the strut
#: is present either way and the two readings agree. A comparison that
#: cannot discriminate the rule under test is not evidence about it.
#:
#: Compared at 16px against Chrome's integer `hhea` rounding, so the
#: tolerance is 1.0px and the interesting rows differ from each other by 8
#: to 26px.
HEIGHTS: dict[str, str] = {
    "strut-small-child": '<div data-h="fx" data-m="s" style="width:300px">'
    '<span style="font-size:8px">x</span></div>',
    "strut-small-lh": '<div data-h="fx" data-m="s" style="width:300px">'
    '<span style="font-size:8px;line-height:8px">x</span></div>',
    "strut-atomic-only": '<div data-h="fx" data-m="s" style="width:300px">'
    '<span style="display:inline-block;width:10px;height:10px"></span></div>',
    "strut-atomic-tall": '<div data-h="fx" data-m="s" style="width:300px">'
    '<span style="display:inline-block;width:10px;height:40px"></span></div>',
    "strut-br": '<div data-h="fx" data-m="s" style="width:300px"><br></div>',
    "strut-nbsp": '<div data-h="fx" data-m="s" style="width:300px">&#xa0;</div>',
    "strut-big-child": '<div data-h="fx" data-m="s" style="width:300px">'
    '<span style="font-size:32px">Big</span></div>',
    "empty-span": '<div data-h="fx" data-m="s" style="width:300px">'
    "<span></span></div>",
    "empty-nested": '<div data-h="fx" data-m="s" style="width:300px">'
    "<span><span></span></span></div>",
    "empty-vertical-padding": '<div data-h="fx" data-m="s" style="width:300px">'
    '<span style="padding:5px 0"></span></div>',
    "empty-horizontal-padding": '<div data-h="fx" data-m="s" style="width:300px">'
    '<span style="padding:0 5px"></span></div>',
    "empty-border": '<div data-h="fx" data-m="s" style="width:300px">'
    '<span style="border-left:1px solid"></span></div>',
    "empty-line-height": '<div data-h="fx" data-m="s" style="width:300px">'
    '<span style="line-height:40px"></span></div>',
    "collapsed-spaces": '<div data-h="fx" data-m="s" style="width:300px">'
    "   </div>",
}

VERTICAL: dict[str, str] = {
    "baseline": f'<div {WIDE}>base <span data-m="s">mid</span> base</div>',
    "sub": f'<div {WIDE}>base <span data-m="s" style="vertical-align:sub">sub'
    "</span> base</div>",
    "super": f'<div {WIDE}>base <span data-m="s" style="vertical-align:super">'
    "sup</span> base</div>",
    "middle": f'<div {WIDE}>base <span data-m="s" style="vertical-align:middle">'
    "mid</span> base</div>",
    "text-top": f'<div {WIDE}>base <span data-m="s" style="vertical-align:'
    'text-top;font-size:8px">tt</span> base</div>',
    "text-bottom": f'<div {WIDE}>base <span data-m="s" style="vertical-align:'
    'text-bottom;font-size:8px">tb</span> base</div>',
    "va-top": f'<div {WIDE}>base <span data-m="s" style="vertical-align:top;'
    'font-size:8px">t</span> base</div>',
    "va-bottom": f'<div {WIDE}>base <span data-m="s" style="vertical-align:'
    'bottom;font-size:8px">b</span> base</div>',
    "va-length": f'<div {WIDE}>base <span data-m="s" style="vertical-align:'
    '10px">len</span> base</div>',
    "two-sizes": f'<div {WIDE}>base <span data-m="s" style="font-size:32px">Big'
    "</span> base</div>",
    "inline-block": f'<div {WIDE}>base <span data-m="s" style="display:'
    'inline-block;width:40px;height:30px"></span> base</div>',
    "ib-baseline": f'<div {WIDE}>base <span data-m="s" style="display:'
    'inline-block;width:60px">inner</span> base</div>',
}

#: CSS 2.1 chapter 17 -- Task E. Compared on `x` and `w` at 16px, like the
#: horizontal suite.
#:
#: **These fixtures deliberately disagree about their preconditions.** Most
#: zero `border-spacing` and cell padding; five do not, and two give the
#: table a border and padding as well. That is instance fifteen's first
#: corollary applied on purpose: an engine that gets the `(columns + 1)`
#: spacing term wrong is invisible in every zero-spacing fixture at once,
#: and three injections proved it -- they passed a suite of twenty-three
#: table tests that all shared `border-spacing: 0`.
#:
#: HTML's own UA stylesheet sets `border-spacing: 2px` on `table` and
#: `padding: 1px` on `td`; `cssparse/ua.py` carries neither, so every
#: fixture states what it wants rather than inheriting a difference.
#:
#: **Every `<tbody>` here is written out, and that is a finding rather than
#: a style.** Written without one, all sixteen column fixtures came back as
#: TREE DIVERGENCE and not as a layout result -- Chrome's parser inserts the
#: implied `tbody` that HTML's "in table" insertion mode requires and this
#: engine's tree builder does not, so `/table[1]/tr[1]/td[1]` here is
#: `/table[1]/tbody[1]/tr[1]/td[1]` there. That is Phase 1's carried gap
#: (the table insertion modes) surfacing in Phase 3, it is an `htmlparse`
#: defect and not a layout one, and the two-identifier scheme is what kept
#: the two apart instead of reporting sixteen table-layout failures.
TABLE_RESET = "table{border-spacing:0;border-collapse:separate}td,th{padding:0}"

TABLES: dict[str, str] = {
    # Column distribution. One `data-m` per column, because the thing under
    # test is how a width was divided.
    "colspan-proportional": f'<div data-h="fx"><style>{TABLE_RESET}</style>'
    "<table><tbody><tr><td data-m>WWWW</td><td data-m>WWWWWWWWWWWWWWWWWWWW</td></tr>"
    '<tr><td colspan=2 style="width:400px">x</td></tr></tbody></table></div>',
    "colspan-three": f'<div data-h="fx"><style>{TABLE_RESET}</style>'
    "<table><tbody><tr><td data-m>WW</td><td data-m>WWWW</td><td data-m>WWWWWWWW"
    '</td></tr><tr><td colspan=3 style="width:600px">x</td></tr></tbody></table></div>',
    "colspan-order": f'<div data-h="fx"><style>{TABLE_RESET}</style>'
    "<table><tbody><tr><td data-m>WW</td><td data-m>WW</td><td data-m>WW</td></tr>"
    '<tr><td colspan=2 style="width:200px">x</td><td>WW</td></tr>'
    '<tr><td colspan=3 style="width:400px">y</td></tr></tbody></table></div>',
    "colspan-absorbed": f'<div data-h="fx"><style>{TABLE_RESET}</style>'
    "<table><tbody><tr><td data-m>WWWWWWWWWW</td><td data-m>WWWWWWWWWW</td></tr>"
    "<tr><td colspan=2>x</td></tr></tbody></table></div>",
    # ...and the same rule WITH a spacing, which is the precondition the
    # four above share and this one breaks.
    "colspan-with-spacing": f'<div data-h="fx"><style>{TABLE_RESET}</style>'
    '<table style="border-spacing:12px"><tbody><tr><td data-m>WWWW</td>'
    "<td data-m>WWWWWWWWWWWWWWWWWWWW</td></tr>"
    '<tr><td colspan=2 style="width:400px">x</td></tr></tbody></table></div>',
    # The table's own width.
    "auto-shrink-to-fit": '<div data-h="fx" style="width:600px">'
    f"<style>{TABLE_RESET}</style>"
    "<table><tbody><tr><td data-m>ab</td></tr></tbody></table></div>",
    "auto-constrained": '<div data-h="fx" style="width:120px">'
    f"<style>{TABLE_RESET}</style>"
    "<table><tbody><tr><td data-m>alpha beta gamma delta</td></tr></tbody></table></div>",
    "between-min-and-max": f'<div data-h="fx"><style>{TABLE_RESET}</style>'
    '<table style="width:100px"><tbody><tr><td data-m>WWW</td>'
    "<td data-m>alpha beta gamma delta</td></tr></tbody></table></div>",
    "both-columns-flexible": f'<div data-h="fx"><style>{TABLE_RESET}</style>'
    '<table style="width:260px"><tbody><tr><td data-m>aa bb cc</td>'
    "<td data-m>alpha beta gamma delta epsilon</td></tr></tbody></table></div>",
    "past-max-content": f'<div data-h="fx"><style>{TABLE_RESET}</style>'
    '<table style="width:500px"><tbody><tr><td data-m>aa</td>'
    "<td data-m>a much longer cell</td></tr></tbody></table></div>",
    "cell-width-below-min": f'<div data-h="fx"><style>{TABLE_RESET}</style>'
    '<table><tbody><tr><td data-m style="width:10px">WWWWWWWWWW</td>'
    "<td data-m>WW</td></tr></tbody></table></div>",
    # Fixed layout: zero corpus coverage, so these fixtures are all there is.
    "fixed": f'<div data-h="fx"><style>{TABLE_RESET}</style>'
    '<table style="table-layout:fixed;width:400px"><tbody>'
    '<tr><td data-m style="width:100px">a</td><td data-m>b</td>'
    "<td data-m>c</td></tr></tbody></table></div>",
    "fixed-auto-width": '<div data-h="fx" style="width:500px">'
    f"<style>{TABLE_RESET}</style>"
    '<table style="table-layout:fixed"><tbody><tr><td data-m>a</td>'
    "<td data-m>b</td></tr></tbody></table></div>",
    "fixed-span-spacing": f'<div data-h="fx"><style>{TABLE_RESET}</style>'
    '<table style="table-layout:fixed;width:400px;border-spacing:20px"><tbody>'
    '<tr><td data-m colspan=2 style="width:200px">a</td><td data-m>b</td>'
    "</tr></tbody></table></div>",
    # Geometry: spacing outside as well as between, and a table that has a
    # border and padding in the separated model.
    "spacing-and-rows": f'<div data-h="fx"><style>{TABLE_RESET}</style>'
    '<table style="border-spacing:10px 20px"><tbody>'
    "<tr><td data-m>a</td><td data-m>b</td></tr>"
    "<tr><td data-m>c</td><td data-m>d</td></tr></tbody></table></div>",
    "table-border-and-padding": f'<div data-h="fx"><style>{TABLE_RESET}</style>'
    '<table style="border:5px solid;padding:7px;border-spacing:3px"><tbody>'
    "<tr><td data-m>aa</td><td data-m>bb</td></tr></tbody></table></div>",
    # Section 17.4 and 17.5, on the wrapper rather than on a cell.
    "caption-in-the-table-rect": '<div data-h="fx">'
    f"<style>{TABLE_RESET}</style>"
    '<table data-m><caption style="height:30px">c</caption>'
    '<tr><td style="height:20px">a</td></tr></tbody></table></div>',
    "auto-margins-centre": '<div data-h="fx" style="width:600px">'
    f"<style>{TABLE_RESET}</style>"
    '<table data-m style="margin:0 auto"><tr><td>ab</td></tr></tbody></table></div>',
    "internal-margins-dropped": '<div data-h="fx" style="width:400px">'
    f"<style>{TABLE_RESET}</style>"
    '<div data-m style="display:table-cell;margin-top:10px">'
    '<div style="height:20px;margin-top:40px;width:30px"></div></div></div>',
    "anonymous-table-for-orphan-cells": '<div data-h="fx" style="width:600px">'
    f"<style>{TABLE_RESET}</style>"
    '<div data-m style="display:table-cell">aa</div>'
    '<div data-m style="display:table-cell">a much longer one</div></div>',
}


#: A box whose four edges are all different and all declared, so the
#: startup assertion is against measured ground truth rather than against
#: itself. Content 400x50, padding 414x60, border 420x66, margin 460x86.
STARTUP = (
    '<div data-h="fx"><div data-m="s" style="margin:10px 20px;border:3px solid;'
    'padding:5px 7px;width:400px;height:50px"></div></div>'
)
STARTUP_EXPECTED = {
    "content": (400.0, 50.0),
    "padding": (414.0, 60.0),
    "border": (420.0, 66.0),
    "margin": (460.0, 86.0),
}


# --------------------------------------------------------------------------
# Chrome
# --------------------------------------------------------------------------

_PAGE_SCRIPT = """
function edges(el) {
  const s = getComputedStyle(el);
  const n = p => parseFloat(s.getPropertyValue(p)) || 0;
  return {
    ml: n('margin-left'), mr: n('margin-right'),
    mt: n('margin-top'), mb: n('margin-bottom'),
    bl: n('border-left-width'), br: n('border-right-width'),
    bt: n('border-top-width'), bb: n('border-bottom-width'),
    pl: n('padding-left'), pr: n('padding-right'),
    pt: n('padding-top'), pb: n('padding-bottom'),
  };
}
function rects(el, base) {
  // One rectangle per line fragment -- the same question
  // DOM.getContentQuads answers, and not DOM.getBoxModel's union.
  // A zero-width rect is the <br> itself, not a fragment.
  return [...el.getClientRects()]
    .filter(r => r.width !== 0 || r.height === 0)
    .map(r => [+(r.x - base.x).toFixed(4), +(r.y - base.y).toFixed(4),
               +r.width.toFixed(4), +r.height.toFixed(4)]);
}
const out = {};
for (const fx of document.querySelectorAll('[data-fx]')) {
  const anchor = fx.querySelector('[data-h]');
  const base = anchor.getBoundingClientRect();
  // ALL the marked boxes, not the first -- see measure_here(). A table
  // fixture marks one cell per column, because the thing under test is how
  // a width was DIVIDED and one column cannot show that.
  const marked = [...fx.querySelectorAll('[data-m]')];
  const el = marked[0];
  // The path RELATIVE to the anchor. Chrome's page stacks every fixture
  // in one document and this engine parses each one alone, so the absolute
  // paths differ for a reason that is about the harness and not about
  // either parser. Relative to the anchor they are the same question.
  out[fx.dataset.fx] = {rects: [].concat(...marked.map(m => rects(m, base))),
                        edges: edges(el),
                        path: xpath(el).slice(xpath(anchor).length),
                        ordinal: ordinal(el) - ordinal(anchor)};
}
function xpath(el) {
  const parts = [];
  for (let n = el; n && n.nodeType === 1 && n !== document.documentElement.parentNode;
       n = n.parentNode) {
    let i = 0;
    for (let s = n.parentNode ? n.parentNode.firstElementChild : null; s; s = s.nextElementSibling) {
      if (s.tagName === n.tagName) { i++; if (s === n) break; }
    }
    parts.unshift('/' + n.tagName.toLowerCase() + '[' + i + ']');
  }
  return parts.join('');
}
function ordinal(el) {
  let i = 0;
  for (const n of document.querySelectorAll('*')) { if (n === el) return i; i++; }
  return -1;
}
document.title = 'RESULT' + JSON.stringify(out) + '|' + document.compatMode +
                 'ENDRESULT';
"""


def measure_in_chrome(fixtures: dict[str, str], size: int) -> dict:
    """One Chrome run for every fixture. `--dump-dom` and a self-measuring
    page rather than a CDP client: it needs no websocket, no
    `--remote-allow-origins`, and no `Target.createTarget` dance, and it
    answers the same questions."""
    items = "".join(
        f'<div data-fx="{name}">{body}</div>' for name, body in fixtures.items()
    )
    # `<!doctype html>` is **not** decoration. Without it Chrome renders in
    # quirks mode, where the line-height quirk suppresses the block
    # container's strut -- and the numbers that come back are plausible,
    # in the right range, and wrong. That mistake produced a 2,114-site
    # behavioural decision in this engine before the coordinator
    # re-measured it. `document.compatMode` is asserted below so the page
    # cannot silently slip back.
    html = (
        f'<!doctype html><meta charset="utf-8"><style>{stylesheet(size)}</style>'
        f"{items}<script>{_PAGE_SCRIPT}</script>"
    )
    with tempfile.NamedTemporaryFile(
        "w", suffix=".html", delete=False, encoding="utf-8"
    ) as handle:
        handle.write(html)
        path = handle.name
    try:
        result = subprocess.run(
            [
                CHROME, "--headless", "--disable-gpu", "--hide-scrollbars",
                "--force-device-scale-factor=1", "--window-size=1280,1024",
                "--dump-dom", "file://" + path,
            ],
            capture_output=True, text=True, timeout=120,
        )
    finally:
        os.unlink(path)
    match = re.search(r"RESULT(.*?)ENDRESULT", result.stdout, re.S)
    if match is None:
        print(result.stdout[:2000], file=sys.stderr)
        print(result.stderr[:2000], file=sys.stderr)
        raise SystemExit("Chrome produced no result -- is it the pinned build?")
    payload, mode = match.group(1).rsplit("|", 1)
    if mode != "CSS1Compat":
        raise SystemExit(
            f"Chrome rendered this page in {mode}, not standards mode. Every "
            "number from a quirks-mode page is wrong in ways that look "
            "right -- the line-height quirk alone suppresses the strut. "
            "See docs/measurement-hazards.md instance fifteen."
        )
    return json.loads(payload)


# --------------------------------------------------------------------------
# This engine
# --------------------------------------------------------------------------


def measure_here(body: str, size: int) -> dict:
    """`{rects, path, ordinal}` for the `data-m` box in one fixture.

    An inline box has fragments and no `geometry`; a block-level box and an
    atomic inline have `geometry`. Both are reported as a list, so the
    comparison never has to know which it is looking at.
    """
    non_comparable: list = []
    document = parse(f"<style>{stylesheet(size)}</style>{body}")
    style_document(document, [], viewport=VIEWPORT)
    root, _ = build_box_tree(document, non_comparable=non_comparable)
    layout_document(root, VIEWPORT)

    anchor = None
    targets: list = []
    for box in root.walk():
        if box.origin != "element" or not isinstance(box.node, Element):
            continue
        if box.node.attrs.get("data-h") is not None and anchor is None:
            anchor = box
        if box.node.attrs.get("data-m") is not None:
            targets.append(box)
    if not targets or anchor is None or anchor.geometry is None:
        raise SystemExit(f"fixture has no data-h/data-m box: {body[:60]}")
    target = targets[0]

    base = anchor.geometry.border
    # ALL the marked boxes, concatenated, so a table fixture can mark one
    # cell per column -- the thing under test there is how a width was
    # DIVIDED, and one column cannot show that. A single marked box gives
    # exactly the previous behaviour.
    rectangles = []
    for marked in targets:
        if marked.fragments:
            rectangles.extend(f.geometry.border for f in marked.fragments)
        elif marked.geometry is not None:
            rectangles.append(marked.geometry.border)
    path = target.path or ""
    anchor_path = anchor.path or ""
    if path.startswith(anchor_path):
        path = path[len(anchor_path):]
    return {
        "rects": [
            (r.x - base.x, r.y - base.y, r.width, r.height) for r in rectangles
        ],
        "path": path,
        "ordinal": (target.ordinal or 0) - (anchor.ordinal or 0),
        "non_comparable": non_comparable,
    }


# --------------------------------------------------------------------------
# The startup assertion
# --------------------------------------------------------------------------


def assert_box_model(size: int) -> None:
    """Pin what a rectangle from Chrome means, before comparing anything.

    `getBoundingClientRect()` is the **border** box. Reading it as the
    content box is a silent 20px error on a 400px div -- the shape that
    produces a uniformly wrong comparison that still looks like a working
    comparison.
    """
    got = measure_in_chrome({"startup": STARTUP}, size)["startup"]
    rect = got["rects"][0]
    edges = got["edges"]
    border_width, border_height = rect[2], rect[3]
    content = (
        border_width - edges["bl"] - edges["br"] - edges["pl"] - edges["pr"],
        border_height - edges["bt"] - edges["bb"] - edges["pt"] - edges["pb"],
    )
    padding = (content[0] + edges["pl"] + edges["pr"],
               content[1] + edges["pt"] + edges["pb"])
    margin = (border_width + edges["ml"] + edges["mr"],
              border_height + edges["mt"] + edges["mb"])
    measured = {
        "content": content, "padding": padding,
        "border": (border_width, border_height), "margin": margin,
    }
    for name, expected in STARTUP_EXPECTED.items():
        assert measured[name] == expected, (
            f"Chrome's box model does not match the pinned fixture: {name} is "
            f"{measured[name]}, expected {expected}. getBoundingClientRect() "
            "is supposed to be the BORDER box -- if that convention moved, "
            "every number this script prints moved with it."
        )
    print(f"startup: box model pinned, border box {border_width}x{border_height}")


# --------------------------------------------------------------------------
# Comparison
# --------------------------------------------------------------------------


def run(fixtures: dict[str, str], size: int, axes: str, tolerance: float,
        title: str) -> tuple[int, int]:
    chrome = measure_in_chrome(fixtures, size)
    index = {"x": 0, "y": 1, "w": 2, "h": 3}
    agree = 0
    print(f"\n=== {title} ===")
    print(f"font-size {size}px, comparing {axes}, tolerance "
          f"{tolerance:.6f}px ({tolerance * 64:.0f} LayoutUnits)")
    for name, body in fixtures.items():
        ours = measure_here(body, size)
        theirs = chrome[name]
        if ours["path"] != theirs["path"] or ours["ordinal"] != theirs["ordinal"]:
            # The trees diverged, which is an `htmlparse` finding and not a
            # layout one. Reported separately on purpose: a parser defect
            # that read as thousands of layout errors is precisely the
            # confusion the two-identifier scheme exists to prevent.
            print(f"!! {name:20} TREE DIVERGENCE "
                  f"ours={ours['ordinal']}:{ours['path']} "
                  f"chrome={theirs['ordinal']}:{theirs['path']}")
            continue
        mine, yours = ours["rects"], theirs["rects"]
        deltas = [
            abs(a[index[axis]] - b[index[axis]])
            for a, b in zip(mine, yours)
            for axis in axes
        ]
        worst = max(deltas) if deltas else 0.0
        ok = len(mine) == len(yours) and worst <= tolerance
        agree += ok
        print(f"{'  ' if ok else '!!'} {name:20} fragments ours={len(mine)} "
              f"chrome={len(yours)}  worst delta {worst:.4f}px")
        if not ok:
            for position in range(max(len(mine), len(yours))):
                a = mine[position] if position < len(mine) else None
                b = yours[position] if position < len(yours) else None
                print(f"       [{position}] ours={_fmt(a)} chrome={_fmt(b)}")
    print(f"{agree}/{len(fixtures)} agree")
    return agree, len(fixtures)


def _fmt(rect) -> str:
    if rect is None:
        return "-"
    return "(" + ", ".join(f"{v:.4f}" for v in rect) + ")"


#: The three fixtures that do not agree, and why. Printed with the result
#: so a reader does not have to reconstruct them, and kept in one place so
#: that a FOURTH one appearing is visible rather than absorbed.
KNOWN_DIVERGENCES = """
Three fixtures disagree and all three are accounted for:

  wrap-bold   this engine ships one face, so <b> measures at the regular
              advances. 88.9375 against Chrome's 93.375. docs/fonts.md.
  pre-wrap    Chrome emits a THIRD rectangle for the run of preserved
              spaces hanging past the line end. Both engines put the two
              lines in the same places; we do not give the hung run a
              fragment of its own. A difference in what a fragment is.
  middle      Chrome's x-height for this font is 1062 units and
              OS/2.sxHeight says 1082, so a middle-aligned box lands 9.5px
              apart at 2048px and 0.074px at 16px. CSS Values 4 section
              5.1.2 says to use the font's metric, and we do.

A fourth would be a finding.
"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--only", nargs="*", help="fixture names to run")
    parser.add_argument("--list", action="store_true", help="name the fixtures")
    parser.add_argument("--chrome", default=CHROME)
    arguments = parser.parse_args(argv)

    if arguments.list:
        for name in HORIZONTAL:
            print(f"horizontal  {name}")
        for name in HEIGHTS:
            print(f"heights     {name}")
        for name in VERTICAL:
            print(f"vertical    {name}")
        for name in TABLES:
            print(f"tables      {name}")
        return 0

    if not Path(arguments.chrome).exists():
        print(f"no Chrome at {arguments.chrome}", file=sys.stderr)
        return 1
    globals()["CHROME"] = arguments.chrome

    horizontal = HORIZONTAL
    vertical = VERTICAL
    heights = HEIGHTS
    tables = TABLES
    if arguments.only:
        wanted = set(arguments.only)
        horizontal = {k: v for k, v in HORIZONTAL.items() if k in wanted}
        vertical = {k: v for k, v in VERTICAL.items() if k in wanted}
        heights = {k: v for k, v in HEIGHTS.items() if k in wanted}
        tables = {k: v for k, v in TABLES.items() if k in wanted}

    assert_box_model(16)
    total_agree = total = 0
    if horizontal:
        agree, count = run(
            horizontal, 16, "xw", HORIZONTAL_TOLERANCE,
            "line breaking and fragment extents",
        )
        total_agree += agree
        total += count
    if heights:
        # 1.0px: Chrome rounds this font's hhea metrics to whole pixels, so
        # 18.3984 comes back as 18. The rows differ from each other by 8 to
        # 26px, so the tolerance cannot hide the rule under test.
        agree, count = run(
            heights, 16, "h", 1.0,
            "the strut and the empty line box (CSS 2.1 10.8 and 9.4.2)",
        )
        total_agree += agree
        total += count
    if vertical:
        # 2048px: this font's unitsPerEm, where every hhea metric is a whole
        # pixel and Chrome's integer rounding of them cannot hide a rule.
        agree, count = run(
            vertical, 2048, "yh", VERTICAL_TOLERANCE,
            "baseline alignment, with Chrome's metric rounding removed",
        )
        total_agree += agree
        total += count
    if tables:
        # `xw` at 16px, the same axes and tolerance as the horizontal suite:
        # table layout is a width algorithm, and the heights in these
        # fixtures are line boxes the strut suite already covers.
        agree, count = run(
            tables, 16, "xw", HORIZONTAL_TOLERANCE,
            "table column widths (CSS 2.1 17.5.2)",
        )
        total_agree += agree
        total += count
    print(f"\n{total_agree}/{total} fixtures agree on every fragment")
    print(KNOWN_DIVERGENCES)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
