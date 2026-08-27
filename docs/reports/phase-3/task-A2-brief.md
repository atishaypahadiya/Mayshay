# Task A2 — cascade repair

Phase 3's first task. Read `CLAUDE.md`, then
`docs/plans/2026-08-27-phase-3-layout.md` (Task A2 section and the
"What Phase 2's output makes harder" section).

## Why this is first

67% of declarations that reach the cascade are dropped: example.com 9%,
Hacker News 32%, Wikipedia 70% (2,296 of 3,299). Layout cannot be more
correct than its input, and at that rate a layout bug and a cascade bug are
indistinguishable. Phase 3 would spend its budget telling them apart.

## Deliverables, in this order

### 1. Drop-reason instrumentation — do this FIRST

Before changing any behaviour, make the current drop rate explainable. You
cannot tell whether the rest of this task helped otherwise.

Classify every dropped declaration into exactly one of:

    unsupported-property     the name is not in values.py's table
    unsupported-value        the name IS known, the value grammar is not
    var-unresolved           contains var() we chose not to substitute
    invalid                  genuinely malformed; a browser drops it too

Emit as `declarations_dropped_<reason>` counters alongside the existing
`declarations_dropped`, which keeps its meaning as the total.

**There are TWO call sites**, and both must be covered: `_parse_block`
(cascade.py, around line 825) and `_parse_inline_style` (around line 861).
They are near-identical and were the site of a Phase 2 defect where one was
fixed and the other silently was not. Prefer extracting the shared body to
one function over editing both — a chokepoint, not two parallel edits.

Report the breakdown per page, before your changes and after. Put both
tables in your report.

**`invalid` must not shrink.** A drop rate falls when the parser improves
and also when validation loosens; those are opposite outcomes. If `invalid`
goes down, something that should be rejected is now being accepted — say so
loudly rather than reporting an improved rate.

### 2. Box-model longhands

`parse_declaration_value` (values.py, ~line 760) is a chain of
`if name == ...` ending in `return None`. It handles `margin`, `padding`
and `border` shorthands and none of their longhands. Add all 28:

    margin-top/right/bottom/left          (auto allowed)
    padding-top/right/bottom/left         (auto NOT allowed)
    border-{side}-width / -style / -color
    border-width / -style / -color        (the 4-value shorthands)
    border-{side}                         (width||style||color, one side)

`ComputedStyle` already carries every one of these fields, and `LONGHANDS`
already lists them — the gap is only the property table. Reuse
`_parse_margin_or_padding`, `_parse_border` and `_parse_length_percentage`
rather than writing new parsers.

Mind `_reset_omitted_longhands`: `border-left` sets three longhands and
must reset only that side's omitted ones, not all twelve. Phase 2 shipped a
bug here (`p{border:5px solid red} p{border:solid blue}` left the 5px) and
its fix keys on the property name — check what that function does with the
names you add before assuming it generalises. 395 declarations in the
corpus depend on this.

### 3. `ComputedStyle` additions

Add, with correct initial values from the CSS specs:

    white-space (normal), line-height (normal), font-family (a list),
    font-weight (normal/400), font-style (normal), text-align (start),
    vertical-align (baseline), box-sizing (content-box)

`line-height: normal` must stay symbolic — a `Keyword("normal")`, not a
number. Its used value depends on font metrics that arrive in Task D, and
resolving it to a guess now is exactly the "computed vs used" mistake
Phase 2 deliberately avoided for `%` and `auto`.

`font-family` is a list of names, kept as parsed. Phase 3 uses one font, so
nothing consumes the list yet; recording it is what makes the eventual
fallback chain implementable.

### 4. `INHERITED` expansion

From 2 entries to 9: `color`, `font-size`, `font-family`, `font-weight`,
`font-style`, `line-height`, `white-space`, `text-align`,
`list-style-type`.

**One test per property**, each asserting a child WITHOUT its own
declaration receives the parent's value AND that a child WITH its own
declaration overrides it. A property that silently fails to inherit
produces plausible-looking wrong output, which is the hardest kind to
notice — that is why this is one deliberate change with nine tests rather
than nine incidental ones.

Verify `_inherit_from` actually copies each new field; it is easy to add a
name to the frozenset and not to the copy.

### 5. `inherit` / `initial` / `unset`

Currently rejected outright (values.py deviation 3), so every use is
dropped. Accept all three:

    initial   the property's initial value
    inherit   the parent's computed value
    unset     inherit for an inherited property, initial otherwise

`revert` stays **unsupported and counted** — it needs origin-level rollback
the cascade does not model. Do not fake it.

These are wide keywords: valid for every property, and they must be
intercepted before the per-property value parser sees them.

### 6. `var()` — the common case only

This is the largest item and the one with a real architectural trap.

**The trap.** Declarations are parsed once per sheet, in `_parse_block`,
and the resulting `_Declaration` objects are shared by every element the
rule matches. `var()` breaks that: `color: var(--accent)` computes to a
different value per element, because `--accent` is itself cascaded and
inherited. Substituting at sheet-parse time is wrong and will produce
plausible output on a test page with one element.

**The shape that works.** Custom properties are ordinary declarations that
cascade and inherit; substitution happens per element, at computed-value
time, after the winning custom properties for that element are known:

* A declaration whose name starts with `--` is a custom property. Cascade
  it like any other declaration, but keep its value as **raw tokens** — a
  custom property's value is almost-anything and is not parsed until
  substituted. Custom properties **inherit**.
* A declaration whose value contains a `var()` function cannot be parsed at
  sheet time. Keep its raw tokens too, and resolve them per element.
* Per element: resolve that element's custom-property map (its own winners,
  falling back to the parent's map), then substitute into any pending
  declaration, then run `parse_declaration_value` on the result.
* Substitution is textual at the token level: replace the `var()` function
  with the custom property's token list. `var(--x, fallback)` uses the
  fallback tokens when `--x` is not set.

**Deliberately out of scope, each with a counter:**

    var_nested_fallback_skipped   var() inside another var()'s fallback
    var_depth_exceeded            substitution depth cap hit
    var_unknown_no_fallback       --x not set and no fallback given

Use a **substitution depth cap** (8 is plenty) rather than real cycle
detection. A cap is O(1) and cannot be wrong in the dangerous direction;
full cycle detection per Custom Properties 1 is a phase, not a task. Do not
implement the guaranteed-invalid-value rules of section 3 in their
generality.

Corpus target: Wikipedia defines 420 custom properties and has 557
declarations consuming them, 15.4% of its declarations. 233 of the 257
dropped `color`/`background-color` declarations are plain `var()`.

## Rules for this task

**Verification.** Every factual claim you write — a count, a set
membership, a "this is already handled" — must be executed before it is
written down. Nine instances of assert-from-reading reached review on the
Phase 2 branch. Reading is convincing and cheap; running is one line. This
applies to decisions too: a test deferred as "correct by inspection" is an
unexecuted claim wearing a decision's clothes.

**Injection testing is mandatory, not optional.** For every non-trivial
test you write, shadow the source into a scratch copy on `PYTHONPATH`,
**verify `__file__` resolves to the shadow**, inject a deliberate bug, and
confirm the test fails. At least ten of the Phase 2 tests asserted less
than their names implied, and injection is the only thing that found them.
Report your injection table: what you broke, which test caught it. An
injection that is a no-op (the code behaves identically) is not evidence —
find a real one.

**Tests must discriminate.** A test with one input cannot tell a working
comparison from a constant. Assert both sides of every boundary.

**Non-ASCII in test data is written as an escape** (`K`), never as a
literal. Kelvin sign vs ASCII K and NBSP vs space read identically in a
terminal.

**Environment, non-negotiable:**

* Do NOT modify anything under `.venv/`. A Phase 1 subagent repointed the
  editable-install `.pth` file and broke every test invisibly, because
  `.venv/` is gitignored.
* Do NOT uninstall anything. `tinycss2`, `webcolors` and `matplotlib` are
  deliberately installed as read-only oracles. Never import them from
  `src/` or from a committed test.
* Run tests as `.venv/bin/pytest` with **no** `-q`. `pyproject.toml`
  already sets `addopts = "-q"`; a second `-q` gives verbosity -2 and
  suppresses the summary line. Two Phase 2 agents lost time to this.
* Never `git submodule update --remote`. `tests/html5lib-tests` is pinned
  to `9329e64` on purpose.
* Baseline before you start: 6,570 passed, 7 skipped, 72 xfailed. Any test
  you break, you fix or explain.

## Done when

* The four drop-reason counters exist, are emitted from a single
  chokepoint, and are reported per page before and after.
* Wikipedia's 70% drop rate has moved, and the breakdown says why.
* `invalid` has not shrunk.
* The full suite is green.
* Your report includes the injection table and both drop-reason tables.
