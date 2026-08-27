# Task B — box tree construction

Phase 3, after Task A2 (cascade repair, merged). Read `CLAUDE.md` in full,
then `docs/plans/2026-08-27-phase-3-layout.md` (Task B and "The Chrome
comparison contract"), then `docs/measurement-hazards.md`.

You are building `src/mayshay/layout/`. It does not exist yet. Task B builds
the **box tree only** — no positions, no sizes, no layout. Tasks C–F do
that. If you find yourself computing a width, you have left the task.

## 1. `display: none` is a subtree operation

The single cheapest correctness win in the phase, and it must be done as
**non-descent**, not per-node skipping. A `none` element contributes no box
and neither does anything beneath it, whatever those descendants computed.
The builder must not walk into the subtree at all: descending and skipping
is slower, and it consults `display` on nodes that should never have been
reached.

Measured on the corpus at 1280x1024, and **name the population when you
report these** — three different correct answers exist here and the brief
that produced this task got them confused once already:

    elements whose computed display is `none`     519   (the census figure)
       of those, pruning ROOTS                    342
       of those, nested inside another none tree  177
    descendants pruned with a NON-none display    435
    TOTAL elements producing no box               954   (11.1% of 8,593)

So: **342 roots, 954 elements pruned, 612 of them never visited.** The
plan and an earlier message both said "519 roots carrying 954" — that is
wrong twice over; 519 is neither the roots nor the total. Use the numbers
above and re-derive them yourself before quoting them.

Counters, seeded at zero: `boxes_pruned_roots`, `boxes_pruned_total`.

Test that the subtree is **not visited**, not merely that it produces no
boxes. An unvisited node and a discarded one are indistinguishable in the
output tree, so assert on a visit counter or an instrumented accessor. A
test that only checks the box count passes under the slow implementation
this rule exists to forbid.

## 2. Anonymous boxes, and what they do to node identity

This is the real difficulty, and it has a downstream consequence that must
be decided **here**, not retrofitted in Task D.

Two fixups, per CSS 2.1 section 9.2:

* A block container with **both** block-level and inline-level children
  wraps each contiguous run of inline children in an **anonymous block
  box**.
* An inline box containing a block-level box is **split**, producing
  anonymous blocks around the parts.

Neither anonymous box corresponds to a DOM node. **The box tree therefore
stops being isomorphic to the DOM**, and that breaks the node-identity half
of the Chrome comparison contract, which keys on a document-order element
ordinal plus a structural path.

### What to do about it

Chrome has the same problem and resolves it the same way: `DOM.getBoxModel`
and `DOM.getContentQuads` are keyed by **DOM node**, and Chrome does not
expose its anonymous boxes through CDP at all. So:

* Every box carries an **origin**: the `Node` it came from, or `None`.
  Give it an explicit discriminator — `element`, `text`, or `anonymous` —
  rather than leaving callers to infer it from `node is None`.
* A box with a DOM origin is **comparable**; its identity is
  `(element ordinal, structural path, fragment index)`.
* An **anonymous box has no counterpart in CDP and is excluded from the
  comparison** — but it must be *counted*, not silently absent, so the
  exclusion is a number rather than a gap. `boxes_anonymous` seeded at
  zero.
* Fragment index exists now even though Task D produces the fragments.
  Chrome returns one quad per line fragment for a wrapping inline; our
  representation must be able to say "fragment 2 of node N" from the start.
  Task B emits index 0 for every box; Task D makes it meaningful.

Design the structure so a box can be asked for its identity without
knowing whether Task D has run.

### The corpus will not exercise this

Measured, and it matters for how you test:

    block containers with mixed block+inline children     28
    inline boxes containing a block-level box             34
    mixed containers with bare text needing an anon wrap  16

28 sites in 8,593 elements. The corpus is nearly useless as a test for
anonymous boxes — it will pass whatever you write. **Tests here must be
synthetic and adversarial**, and the corpus run is a smoke test, not
evidence. Say so in your report rather than citing "runs clean on three
real pages" as if it demonstrated correctness.

Cases worth constructing: `<div>text<p>x</p>text</div>` (two anonymous
blocks, not one); `<span>a<div>b</div>c</span>` (inline split);
consecutive blocks with no inline between them (**no** anonymous box —
over-generation is as wrong as under-generation); whitespace-only text
between two blocks (no anonymous box); an inline containing only inlines
(unchanged).

## 3. `grid` falls back to `block`, with a counter

`grid` -> `block`, `inline-grid` -> `inline-block`, incrementing
`boxes_grid_fallback` (seeded at zero). Two elements on the corpus, so it
is nearly free — and the counter is the thing that tells us when it stops
being free. Do not implement grid layout.

## 4. Box tree shape

Block containers, inline boxes, and the table/flex containers classified
but not laid out. Text nodes become text boxes. Keep it minimal: Task C
and D will add geometry fields, and a structure that already carries
`width`/`height` invites someone to fill them in before the algorithm
exists.

Emit a `layout` stage into `data/metrics/stages.csv` via `metrics.emit`,
called from a **driver** — `scripts/layout_report.py`, in the shape of
`display_report.py`. The library builds `Counter`s and returns them; it
never writes. See CLAUDE.md.

## Discipline (same as A2)

* **Injection testing is mandatory.** Shadow the source onto `PYTHONPATH`,
  verify `__file__` resolves to the shadow, inject a real defect, confirm a
  test fails. A no-op injection is not evidence — discard it and find a
  real one. Report the full table.
* **Execute every factual claim** before writing it down.
* **Every counter seeded at zero** so absence and zero are distinguishable.
* **Name the population** for every number you report.
* Non-ASCII in test data as escapes, never literals.
* Do NOT modify `.venv/`. Do NOT uninstall anything. Never import
  `tinycss2`, `webcolors`, `cssutils`, `cssselect`, `matplotlib` from
  `src/` or a committed test. `fontTools` is permitted in `layout/` for
  font metrics only — Task D's concern, not yours; you need no font.
* Run `.venv/bin/pytest` with **no** `-q`.
* Never `git submodule update --remote`.
* Scratch files in `/Users/atishaypahadiya/.claude/jobs/604b9f51/tmp`.
* **Stage explicit paths. Never `git add -A`** — the coordinator may be
  editing docs in this tree at the same time.
* Baseline: **6641 passed, 7 skipped, 72 xfailed**. Verify it yourself
  first.

## Done when

* `display:none` prunes by non-descent, proven by a visit counter.
* Anonymous box generation and inline splitting work, tested synthetically.
* Every box can report its identity, and anonymous boxes are counted and
  excluded rather than absent.
* `grid` falls back and is counted.
* `scripts/layout_report.py` runs over the corpus and emits the `layout`
  stage.
* Full suite green. Report includes the injection table, the box census
  with populations named, and every defect you find in this brief — the
  author's briefs have produced defects that reached implementation in
  every phase so far, and finding one is a success.
