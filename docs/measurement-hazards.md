# The wrong answer arrives shaped like the right one

Three measurements on this project have been wrong in a way that was
invisible from the output. Not crashes, not obviously-bad numbers --
plausible values, of the right type, in the right range, internally
consistent. Each survived review by inspection. Each was caught only by a
**second measurement obtained a different way**.

This file records them together, because the pattern is more useful than
the three fixes.

## The three

### 1. The display census that was not measuring the pages

Through all of Phase 1 and Phase 2 the display distribution was computed
from the UA stylesheet plus in-document `<style>` blocks. No external
stylesheet had ever been fetched, and at-rules were counted and skipped.

The output looked complete: 7,778 elements, a sensible distribution,
`inline` dominant as it should be. Hacker News in particular reported a
plausible distribution -- which was entirely our own UA sheet, because that
page ships zero in-document CSS.

Even after the stylesheets were collected, Hacker News showed a display
delta of **exactly zero**, which reads as a finding ("external CSS does not
change this page's display") rather than a gap. It was a gap: all six
`display` declarations in `news.css` sit inside `@media` blocks the cascade
skipped. Measured afterwards, 51% of that page's CSS and 46% of Wikipedia's
was inside at-rules we never entered.

What it cost when fixed: Wikipedia's `flex` count went from 4 to 205.

**Caught by** treating the exactly-zero delta as a hypothesis to disprove
rather than a result -- injecting a probe stylesheet (`td { display: grid }`)
to prove the code path reached the cascade at all, then asking where the
real declarations had gone.

### 2. `PIL.ImageFont.getlength` returning integers

Pillow reports `"Hello world"` as `89.0` px at 16px. The font's own `hmtx`
metrics give `89.6953`.

`89.0` is a float, in the right range, and correct to within 1%. Nothing
about it looks like a rounding artifact. Setting
`layout_engine=ImageFont.Layout.BASIC` or `mode="L"` does not change it,
so the obvious "am I hitting a hinted path?" check returns the same number
and reads as confirmation.

The error compounds per glyph and per line, and it would have made a
Chrome comparison measure our rounding rather than our layout -- while
producing a believable error distribution.

**Caught by** computing the same advances from a second source
(`fontTools` reading `hmtx` directly) and finding they disagreed.

**The cause, found later** (7 Nov 2026, Pillow 12.3 and 13.0). The font
was DejaVu Sans, before Liberation Sans was vendored (`docs/fonts.md`).
Pillow uses Raqm layout when libraqm is installed and basic layout
otherwise, and `getlength`'s own docstring says the result "is a whole
number if using basic layout". Asking for basic layout and getting the
same `89.0` is what happens when libraqm is absent and basic is already
the default; that is the likely reading, not a re-run on that machine. With
Raqm the same call gives `89.75`: fractional, and still not the font's
`89.6953`. Reading `hmtx` stays the right call either way.

### 3. `DOM.getBoxModel` returning a union box for wrapping inlines

For an inline `<span>` spanning three lines, CDP's `getBoxModel` returns
one rectangle: x 0.00..194.80, y 89.00..154.00, 195 x 65. It is a
well-formed box with sensible coordinates. It is the **union** of the three
line fragments and matches none of them:

    fragment 0   78.25..184.09   x  89..106
    fragment 1    0.00..194.80   x 113..130
    fragment 2    0.00..188.53   x 137..154

Inline is 67.8% of the corpus. A comparison harness built on `getBoxModel`
would have compared our per-line fragments against a bounding box for two
thirds of every page, produced a large but plausible error distribution,
and validated nothing -- while looking like it worked.

**Caught by** asking a second CDP method (`getContentQuads`) the same
question and getting three answers where the first gave one.

## The sharper case: a diagnostic downstream of the defect

Instances 1 and 3 were wrong measurements. Instance 2 was worse, and the
difference is worth naming.

When a width came back as `89.0`, the natural next question is "am I on a
hinted path?" -- and there are two obvious ways to ask it:

    ImageFont.truetype(path, 16, layout_engine=ImageFont.Layout.BASIC)
    font.getlength(text, mode="L")

Both return `89.0`. The check that should have caught the rounding returns
the same number as the thing it was checking, so it reads as
**confirmation**: hinting is not the problem, the number is fine, move on.

That is a false green, and it is strictly worse than no check at all. No
check leaves uncertainty, which is a state that still prompts caution. A
passing check converts that uncertainty into confidence -- confidence
pointing in the wrong direction, held more firmly for having been
"verified".

The reason it fails is structural, not incidental: **both diagnostics are
downstream of the same rounding.** They vary an input to a pipeline whose
final step discards the fractional part. Nothing you can vary upstream of a
truncation will reveal the truncation. The diagnostic and the defect share
an implementation path, so the diagnostic inherits the defect's blind spot.

### The criterion

This is what decides when "ask a second method" is mandatory rather than
prudent. It has two parts, and the first alone is not usable:

> **A check can only detect defects that are not upstream of it.** If the
> candidate diagnostic shares the specific path that could be defective, it
> cannot fail when that path is wrong.
>
> **But sharing is not disqualifying on its own -- quiet sharing is.** The
> question is what a defect in the shared path would look like. One that
> produces a loud, uniform, obviously-broken failure is safe to share,
> because it cannot masquerade as a pass. One that could produce a
> plausible green is not.

The second part is what keeps this from regressing into
who-verifies-the-verifier. Almost every useful check shares *something*
with its subject, and a rule that forbids all sharing forbids all checking.

**Worked example, and a correction to an earlier draft of this file.** The
html5lib-tests comparison shares a great deal with the parser it validates:
the `.dat` fixture loader, `dom.serialize()`, and the pytest harness. An
earlier version of this section called it "shares only the input", which is
simply wrong.

It is still a good check, and the reason is the second part of the
criterion, not the first. A defect in `serialize()` does not produce a
plausible pass -- it produces hundreds of uniform failures across every
fixture at once, which is unmissable. The shared path is real but its
failure mode is loud. Compare `getlength`: the shared path there fails by
returning a *slightly different plausible number*, silently, on every call.
Same structure, opposite risk.

So the operative pair of questions before trusting a check:

1. Does it share the path that could actually be wrong -- not just any path?
2. If that path is wrong, does the check fail loudly or return a plausible
   green?

Only "yes, and quietly" makes an independent second derivation mandatory.

Concretely, in this project:

| check | shares | if the shared path is wrong | verdict |
|---|---|---|---|
| Pillow advances, diagnosed with Pillow's own options | the rasterizer, including its rounding | same plausible number, silently | **decorative** -- needed `fontTools` |
| our parser vs html5lib-tests | loader, serializer, harness | hundreds of uniform failures | fine -- loud |
| a cascade counter checked against another counter the same function emits | the function | both move together, silently | decorative -- count from the DOM instead |
| `getBoxModel` vs `getContentQuads` | Chrome's layout engine | both wrong the same way | acceptable for *fragmentation*, which is what they disagree about; not for absolute correctness |

That last row is worth stating plainly: asking Chrome twice cannot tell us
whether Chrome is right. It told us the two methods answer different
questions, which is what was needed. A check has a scope, and its scope is
the difference between the two things being compared.

### Corollary: agreeing measurements that share a generator

The criterion above was written for a single check. Task D2 produced the
same failure with confidence multiplied by seven.

Seven fixtures were measured in Chrome, all seven agreed with each other,
all seven contradicted CSS 2.1, and a rule was written that explained all
seven and no other. Every one came from the same probe page, which had no
doctype. One defect, reported seven times.

> **More agreeing measurements is not more evidence unless they are
> independently produced.** Coherence across many data points reads as
> strong confirmation and is worth nothing when they share a generator —
> they are one observation, repeated.

This inverts the usual heuristic, which is why it is worth stating. The
instinct that seven consistent results are hard to argue with is correct
*only* for seven independent results. A shared harness, a shared fixture
page, a shared fetch, a shared parse — each collapses N measurements into
one, silently, while leaving the count of them intact.

The tell is that the explanation is *too* clean. A rule that accounts for
every row and no other, derived from a handful of observations, is either a
real law or a description of the single defect generating them. Both look
identical from inside.

The practical form: before trusting a set of measurements, ask what they
**share** — not whether they agree. Vary the shared thing, not the input.
The strut case was settled by changing the doctype, which no fixture
varied, and not by adding an eighth fixture, which would have agreed with
the other seven.

### Corollary: when the reference implementation confirms your bug

The same case, at its worst point. The bad measurement said Chrome gave 9
for the headline fixture. This engine's own output was 9.2.

A comparison harness exists to catch our errors. This one produced a number
that **agreed with our error**, and that agreement was the reason to trust
it. The reference did not merely fail to catch the defect — it endorsed it.

> **A reference implementation confirming your defect is worse than having
> no reference**, because it is a false green with the maximum available
> confidence attached to it. "It matches Chrome" ends an investigation in a
> way that "I think this is right" does not.

The mitigation is not to scrutinise the reference's *output* — the output
was fine, and re-reading 9.00 more carefully reveals nothing. It is to
assert the reference's **preconditions**: that it rendered the document you
meant, in the mode you meant, with the stylesheet you meant.
`scripts/chrome_compare.py` now asserts `document.compatMode` before it
reports anything, and the corpus comparison is declined outright because
Chrome would fetch the live stylesheets while this engine applies the
collected copies — a precondition that cannot currently be met, recorded as
a limitation rather than papered over.

### The criterion applied before it was named

`scripts/collect.py` uses BeautifulSoup to find `<link rel=stylesheet>`
elements rather than `mayshay.htmlparse`, and the reason in its docstring is
exactly this: a parser defect would otherwise become a corpus defect, and
the corpus would then validate the parser that shaped it. **The corpus is
the measuring instrument; it must not be built with the tool under
measurement.**

That was reasoned to independently, months before any of this was written
down, in a context where nobody was thinking about verification at all --
the task was "collect some pages". That matters for how much weight the
criterion deserves: a rule derived only from the incidents that produced it
is a pattern fitted to three points. One that also explains a decision made
for its own reasons, before the rule existed, is describing something real.

## A different sub-shape: the unstated denominator

The three instances above were **wrong measurements**. There is a fourth
shape where every measurement is *correct* and the reader still cannot use
the number, because the population it counts is unnamed.

**The cleanest example is `boxes_inline_split`.** One counter reported
**34**, then **2**, then **0** for the same three pages, and every reading
was arithmetically correct for the population it was measuring:

| reading | population |
|---:|---|
| 34 | inline boxes with any block-level child |
| 2 | of those, the ones that actually produced fragments |
| 0 | of those, the ones that were `display: inline` rather than an atomic inline-level box |

No arithmetic error at any step, no ambiguity about what was intended, and
no way to tell from the number which of the three it was. That is the shape
in its purest form: each narrowing was a genuine correction, and each
correction changed the population without changing the name.

The var() case is the same shape with more noise. Asked "how many custom
properties does Wikipedia declare, and how many declarations consume them?",
this project produced three answers. All three reproduce on demand; all
three are right:

| population | custom | consuming |
|---|---:|---:|
| every declaration in every sheet, descending into all at-rules | 420 | 557 |
| cascade-visible after `@media` evaluation at 1280x1024 | 313 | 353 |
| raw textual occurrences in the sheet bytes | 486 | 565 |

The Task A2 brief cited 420/557 as though it were *the* number. The
implementer measured 313/353 and reported the brief's figures as
irreproducible -- correctly, because they are irreproducible *under the
definition the implementer was using*. Neither party was wrong about
arithmetic. The brief was wrong about specification.

This is the same defect as the display census being a UA-stylesheet census
(instance 1). There the number was also correct -- it accurately described
the distribution of `display` under the UA sheet -- and the failure was
that nothing said so, so it was read as describing the pages. **The value
carries no evidence of its own scope**, which is why no amount of
re-reading the number reveals the problem.

The mitigation is different from the other three. Those need an independent
second measurement. This one needs a **name**:

* State the population in the metric, not just the count.
  `custom_properties_declared` invites the ambiguity;
  `custom_properties_cascade_visible` does not.
* When a figure depends on a parameter -- a viewport, an origin, an
  inclusion rule -- record the parameter beside it. `scripts/style_report.py`
  writes the viewport into the metrics rows for exactly this reason: a
  `flex` count with no viewport beside it is not a reproducible number.
* A disagreement between two counts of "the same thing" is a specification
  question first and an arithmetic question second. Ask what each one
  counted before asking which is right; usually both are.

## The shape

In all three the output had the right type, a plausible magnitude, and no
internal inconsistency. None would fail a sanity check. Two of them were
*more* convincing than the truth: an exactly-zero delta reads as a clean
finding, and an integer pixel width reads as a measurement rather than a
rounding.

This is the same family as the two failure modes CLAUDE.md already names --
the nine assert-from-reading claims and the ten-plus non-discriminating
tests on the Phase 2 branch. In every case the artifact was shaped like a
correct one and the only reliable detector was an independent second
derivation. Reading harder does not work. Neither does checking that the
number is reasonable, because it always was.

## Instance ten, and what it says about these rules

`boxes_inline_split` counted 34 sites on the corpus and
`boxes_inline_fragments` counted 2.

**Those figures have since moved twice more, and the sequence is the
lesson.** Task C found that the box builder split *atomic* inline-level
boxes -- `inline-block`, `inline-flex`, `inline-table` -- around block
children, when CSS Display 3 section 2.1 says only `display: inline` does.
Three boxes took that path wrongly. The corrected corpus figures are **0
splits, 0 fragments, 31 dissolved**: there is no genuinely split inline
anywhere in the corpus. So the same counter has reported 34, then 2, then 0
for the same three pages, and each reading was arithmetically correct for
the population it was actually measuring. The split figure was not wrong
arithmetic -- it was a name covering two different things. 32 of the 34
were inlines whose children are *all* block-level
(`<span><table>...</table></span>`, which Hacker News does 30 times); those
are not split around anything, they dissolve and contribute no box. One
counter for both over-claimed, and the number read as "34 inlines were
split" when the truth was "2 were split and 32 vanished".

That is the unstated-population shape again, and it happened **four commits
after this file was written**, in code by the person who wrote it, while
the rule was fresh.

### Instance eleven, one message later

Planning Task C, the coordinator was told:

> A percentage margin resolving to zero is still a margin for adjoining
> purposes — it doesn't make a block "empty" for the collapse-through rule
> the way no margin at all would.

Measured against Chrome 151 before it went into a brief: false. No declared
margin, `margin: 0` and `margin: 0%` behave identically, because CSS 2.1
section 8.3.1's collapse-through condition names borders, padding, height
and line boxes and says nothing about the box's own margins. All three give
a 30px gap between siblings with `margin: 30px 0`.

Two things make this worth recording rather than quietly fixing.

It was asserted from **reading** section 8.3.1 rather than running it —
the exact defect CLAUDE.md's first rule names, from someone who knows the
rule well. And it arrived in the same message that argued for keeping the
checks mechanical rather than relying on vigilance. The message was right
and its own example proved it in the same breath.

The correction was also an improvement: the *non-zero* percentage margin on
an empty block is a better test than the zero case, because it requires the
percentage-against-width resolution and the collapse-through chain to be
correct simultaneously. Measuring did not just reject the claim, it
produced the fixture the plan actually needed. That is the usual pattern
here and it is worth expecting: the second derivation tends to pay for
itself twice.

### Instance twelve: the tooling participates

Writing the Task D1 brief, the coordinator put a literal U+00A0 into the
sentence warning against literal non-ASCII in test data. The rule and its
violation in the same clause.

The correction is the interesting half. The first fix searched for the
offending text typed with an **ordinary space** where the file held U+00A0.
`str.replace` found nothing, returned the string unchanged, `write_text`
succeeded, and nothing raised. The operation reported success and changed
nothing — and the two characters are identical on screen, which is the
entire reason the rule exists.

What caught it was an independent check printed alongside the edit: the set
of remaining non-ASCII codepoints, which still contained `\xa0`. Not the
edit's own success.

**This generalises the false-green criterion beyond measurement code.** An
edit that cannot fail is not evidence that it did anything, in exactly the
way `getlength`'s hinting options were not evidence about rounding. A
search-and-replace whose pattern does not match is indistinguishable, from
its return value, from one that matched and applied cleanly. Both are
"success".

So the criterion should be read as covering **any tool feedback**, not just
diagnostics:

> A tool reporting success is exactly as trustworthy as a diagnostic
> returning the expected number. Neither is evidence unless it could have
> reported otherwise.

The practical form: after an edit that matters, assert the **postcondition**
— the codepoint is gone, the count changed, the file differs — rather than
trusting that the edit ran. That is what worked here, and it is the same
move as the tree-hash check on the branch rewrite, which caught two
truncations that every intermediate command had reported as fine.

### A third shape: a default masquerading as a measurement

Distinct from the two above. Not a wrong measurement, and not a false
green: a count that is arithmetically correct, whose population is even
stated, and which still does not mean what its size suggests.

**Any count of a property's values includes elements that never set it.**
The initial value's count measures *absence*, not usage — and because the
initial value is the one most elements have, it is usually the largest
number in the table. A big number that looks like heavy coverage.

`vertical-align: baseline` at 7,533 is the clean case: `baseline` is the
initial value, so that count is mostly a census of boxes that never touched
the property. It is not evidence that baseline alignment is exercised.

The one that had already been used for a decision is `display: inline` at
67.8% of boxes, which was cited to justify Task D's scope. Split by the
origin of the winning declaration, over all 8,593 styled elements:

| computed `display` | author | UA sheet | initial |
|---|---:|---:|---:|
| inline | 1,120 | 4,696 | 13 |
| block | 80 | 1,162 | 0 |
| none | 263 | 256 | 0 |
| flex | 205 | 0 | 0 |
| inline-block | 90 | 0 | 0 |
| inline-flex | 28 | 0 | 0 |
| grid | 2 | 0 | 0 |
| **total** | **1,797** | **6,783** | **13** |

Of the 5,829 elements computing `inline`, **19.2% are because author CSS
said so and 80.6% are our own UA stylesheet's default.**

**What this does and does not change.** It does not overturn Task D's
scope: 5,829 boxes need inline layout whether an author asked for it or an
`<a>` simply is inline, and the workload claim survives intact. What it
overturns is any claim about *richness* — the corpus exercises the common
inline path heavily and the varied one barely, which is the same story
`vertical-align` (almost all `baseline`) and `white-space` (`nowrap` and
nothing else interesting) already told from two other directions. Three
independent measurements agreeing is worth more than any of them alone.

Note also which rows are 100% author: `flex`, `grid`, `inline-block`,
`inline-flex`. The values a page had to ask for are exactly the ones a UA
sheet never supplies, so **an author-declared count is the better measure
of what a page actually does**, and a UA-inclusive count is the better
measure of how much work the engine has to do. Neither is wrong; they
answer different questions, and the property name does not say which.

The mitigation is the same as for the unstated denominator, one level
deeper: name the population *and* say whether defaults are in it.

### Instance fourteen: a plausible number the spec appeared to endorse

Task D1's `min-content` width for `a<inline-block 40px>b` came out at
57.81px. Chrome gives **40.00**.

The implementation had no soft wrap opportunity on either side of an atomic
inline box, so the whole thing measured as one unbreakable unit. The number
was plausible — it is the sum of parts that really are adjacent — and
**reading CSS Text 3 supports the wrong answer**. The rule that settles it
is in UAX #14, where U+FFFC (the object replacement character an atomic
inline is treated as) is class CB and rule LB20 provides break
opportunities on both sides.

So this is not the usual "asserted from reading instead of running". The
reading was done, in the document a reasonable person would consult, and it
endorsed the defect. Only the second measurement disagreed.

The same task found the mirror-image error in its own first draft: nothing
said an atomic inline must be **opaque** to collapsing, and it is — the
spaces on both sides survive. Two opposite mistakes about the same
construct, both plausible, both caught by Chrome and neither by the spec
text.

The generalisation is wider than it first looks.

> **A specification that defers to another specification is a pointer, not
> a summary.** Reading the citing layer carefully produces a confident
> wrong answer, which is worse than reading it carelessly — carelessness
> leaves doubt, and care removes it.

The deferrals this project sits on, all of them load-bearing:

| citing layer | defers to | for |
|---|---|---|
| CSS Text 3 | UAX #14 | line break opportunities |
| CSS 2.1 | Unicode Bidi | reordering |
| HTML | CSS | element rendering and the UA sheet |
| CSS Values | the font's own tables | `ex`, `ch`, and vertical metrics |
| CSS Fonts | OpenType | which of three vertical-metric sets applies |

Every one has already produced a defect or a decision on this project. The
`ex`/`ch` values came from `OS/2` rather than the 0.5em fallback CSS Values
describes; the `hhea`-versus-`OS/2` line-box choice is a question CSS does
not answer at all; and the atomic-inline break opportunity is decided three
layers down from where a reader would stop.

**Task D2 sits directly on UAX #14** and will hit this repeatedly. The
practical form: when a rule turns out to be delegated, read the delegate or
measure — do not read the citing text more carefully.

### Instance fifteen: seven fixtures, one harness, one missing doctype

The largest single defect this project has produced, and the one that best
justifies everything else in this file.

Task D2 measured seven fixtures in Chrome 151 and concluded that Chrome does
**not** implement CSS 2.1 section 10.8's *strut* — the zero-width inline box
carrying the block container's own font and `line-height` that every line box
is supposed to contain. On those measurements
`<div><span style="font-size:8px">x</span></div>` was 9px where the spec says
18.40. A deliberate divergence was written, documented as "the single largest
behavioural decision in this module", and it suppressed the strut **2,114
times on the corpus** — 2,114 line boxes too short, and every block height
above them wrong.

Re-measured by the coordinator with two independent methods
(`getBoundingClientRect` via `--dump-dom`, and CDP `DOM.getBoxModel` on a
fresh instance), Chrome gave **18.00** for every content-bearing fixture.

Both parties measured correctly. **They measured different documents.**

    no doctype    document.compatMode = BackCompat   ->  9.00
    <!doctype html>   document.compatMode = CSS1Compat  -> 18.00

The probe page had no doctype, so Chrome rendered it in **quirks mode**,
where the line-height quirk really does suppress the strut. In standards mode
Chrome agrees with CSS 2.1 on all seven rows.

Three things make this the sharpest entry here.

**Seven fixtures were not seven pieces of evidence.** They shared one probe
harness, so they shared one defect. Seven agreeing measurements feel like
overwhelming confirmation and were a single observation repeated — the
"quiet sharing" criterion above, in its purest form: the shared path was the
one that could be wrong, and its failure was silent.

**The wrong number read as confirmation of the code it was checking.** The
bad measurement gave 9 for the headline fixture. This engine's own output was
9.2. A comparison harness built specifically to catch our errors produced a
number that agreed with our error, and the agreement was the reason to trust
it.

**A whole explanatory theory was built on it.** The divergence was not
recorded as a puzzle; it came with a rule that explained all seven rows and
no other, and that rule was written into a docstring as settled. Coherence
across seven data points was taken as evidence, when it was a property of
the single defect generating them.

`scripts/chrome_compare.py` now emits a doctype and asserts
`document.compatMode` before reporting anything. That is the mechanical form,
and it is the only form that would have caught this: no amount of care about
the *rule* would have prompted anyone to check the *mode*.

### Instance sixteen: the literal NBSP, again, in the fixture for itself

Instance twelve recorded a literal U+00A0 typed into the sentence warning
against literal non-ASCII. Task D2 did it again, in a Chrome probe written
to check the behaviour of `&nbsp;` -- and this time the character silently
became U+0020 somewhere between the keyboard and the file.

The probe reported that Chrome **collapsed an NBSP-only box through**,
contradicting an earlier measurement and reading as a genuine finding about
Chrome. It was a finding about the probe. Written as `\u00a0` the same
fixture gives the earlier answer.

What makes it worth a second entry is that the failure mode changed. In
instance twelve the tool reported success and did nothing. Here the tool
reported a **plausible different measurement**, which is the more dangerous
half of the same problem: an edit that silently does nothing leaves the
old value, and a fixture that silently changes gives a new one. The check
that caught it was the same one -- print the codepoints, not the string.

### Instance seventeen: a counter that must read zero, reading 58

`linebreak_class_fallback_other` was built to read zero: it counts
characters that are neither a letter, a digit nor a combining mark and got
line-break class `AL` from a general-category default, which is exactly
where a missing entry in a hand-written class table would hide.

It read **58**, and nothing was wrong. The 58 were Devanagari, Bengali,
Burmese and Khmer combining marks, which the fallback classifies **correctly**
as `CM` and which UAX #14's LB9 then resolves to whatever they attach to.
They were in the residual bucket because the bucket's definition had two
categories in it and its name claimed one.

Splitting the marks into a bucket of their own put it back to zero. The
generalisation belongs with the unstated-denominator family: a residual
bucket is only useful if everything *correct* has somewhere else to go.
A residual that legitimately contains something can never be read as an
alarm, which makes it decorative -- the same verdict this file gives a
diagnostic that shares the defective path.

The same pass found the mirror image: `linebreak_opportunities` had begun
counting the line breaker's opportunities *and* intrinsic sizing's, two
populations under one name, on text they both walk. That is instance four's
shape with the two counts summed instead of reported separately, which is
strictly worse -- a disagreement is visible and a sum is not.

### Instance eighteen: the same broken harness twice, both times a clean zero

Task E needed to answer one question the corpus could actually settle: does
getting `colspan` distribution wrong move real numbers on these pages? The
method was three shadow copies of `src/` -- the correct implementation, one
that puts a spanning cell's whole width on the column it starts in, and one
that ignores spanning cells entirely -- each run over the corpus, with the
column widths diffed.

It reported **0 of 27 tables move**, for both wrong implementations.

That is the shape this file's own rule says to disbelieve, and the probe
found it immediately: `layout.text` derives the vendored font path from its
own `__file__`, so a shadow tree without `data/fonts` raises
`FileNotFoundError` on the first text measurement. **All three processes had
died**, the runner only read the first line of stdout to check the shadow
proof, and the JSON left behind by an earlier run was diffed against itself.
Symlinking the font and asserting on the exit code gave the real answer: the
first-column bug moves **12 of 27** tables, one of them by 592px on a 1184px
table, and ignoring spans entirely moves 2.

The interesting part is what happened next. The **injection harness for the
test suite had exactly the same defect**, and it was not noticed while the
first one was being fixed. Twelve injections each reported "117 failed, 290
passed" -- every one of them the same 117 font-path failures, with the
injection contributing nothing. Uniform results across twelve different
injections read as a working harness rather than a broken one, in the same
way seven agreeing fixtures did in instance fifteen.

Three things generalise.

**A shadow tree is not a copy of the repository.** Anything a module locates
relative to its own `__file__` -- a vendored font, a data table, a fixture
directory -- silently leaves the shadow. The `module.__file__` proof that
CLAUDE.md requires confirms the *code* was shadowed and says nothing about
its data.

**"Did the tool run?" is a different question from "did the tool shadow?"**
and the second was being checked while the first was not. A returncode
assertion is one line and would have caught both.

**Every injection harness needs a control.** A run with *no* injection that
must come back green costs one pass and makes "the injection did nothing"
distinguishable from "the harness does nothing". Both harnesses have one
now. Without it, twelve green-looking injection reports were evidence of
nothing at all -- and three of those twelve turned out, once the control was
in place, to be genuine no-ops that needed new fixtures.

### Instance nineteen: a diff that could not see the boxes it moved

Task F measured discriminating power the way Task E did -- implement a rule
wrongly, run the corpus, diff every box rectangle. Seven variants, and one
of them reported **exactly zero**: treating `align-items: baseline` as
`flex-start` moved nothing.

It was checked rather than believed, because an exact zero is a claim about
the instrument. The check was an independent prediction: the layout's own
plan says the corpus's two baseline-aligned items have ascents of 16.321
and 21.105, so the smaller one must move by 4.784px, and a rule that moves
a box by 4.784px cannot also move nothing.

**The diff keyed its rectangles by DOM path, and skipped every box that has
none.** The corpus's two baseline-aligned flex items are anonymous boxes
wrapping text runs; so are their children. Nothing the variant moved was
ever recorded. Re-keyed by walk index -- which is stable across variants
because the tree fixups run before any of them -- the same variant moves
**1 box by 4.78px**, exactly the predicted number.

Three of the seven variants still report zero afterwards, and all three are
now explained by a counter rather than by an absence:
`flex_lines_wrapped` is 0, `flex_items_clamped_to_min_content` is 0, and no
laid-out item carries a non-`auto` `flex-basis`.

What generalises is not "include anonymous boxes". It is that the harness
had a **silent domain restriction**: it answered "how many *identifiable*
boxes moved" while its name, its output and its use all said "how many
boxes moved". That is the unstated-denominator shape (instance four) inside
a measuring instrument rather than inside a metric -- and it was caught
only because a *second, independent* prediction of the same quantity
existed. A zero with nothing to check it against would have been written
down as a finding about the corpus.

### Instance twenty: a counter that counted calls

In the same task, `flex_items_baseline_synthesized` read **4** on a
two-item fixture.

Nothing was wrong with the alignment. The ascent of a baseline-aligned item
is asked for twice -- once for the line's maximum and once for the item's
own offset -- and the counter sat inside the function that answers, so it
counted questions rather than items. The number was of the right type, in
the right range, and exactly double.

It was caught by a test that asserted `== 2` from the fixture's own shape,
which is the cheap general form: **a counter over a population a test can
state independently is worth more than a counter nothing pins.** The fix
moved the increment to the one place that visits each item once.

The same task shipped one deliberately in the other direction:
`intrinsic_flex_row_summed` really is a count of calls -- intrinsic sizing
recurses, and 700 calls over 29 containers is not 700 containers -- so the
report labels it `(CALLS, not boxes)` rather than pretending otherwise.
Both are the same rule: the population belongs in the name.

### Instance twenty-one: two derived values, one malformed field

The corpus survey's substitution had to be **mechanical** -- take the
lowest-numbered live reserve in the stratum -- precisely so that a
replacement could not be chosen with knowledge of what the survivors had
shown. The tooling that implemented it read the rank as `rank[1:]` if
`rank.startswith("R")`, defaulting to 99 otherwise. The field was written
`1`, not `R1`. **Every reserve defaulted to 99 and the pool sorted
alphabetically.**

It promoted `blog.codinghorror.com` (rank 2) over `ciechanow.ski` (rank 1),
and `mk.co.kr` (rank 3) over `sanook.com` (rank 2). Two of nineteen
substitutions were wrong.

What made it survive review is the shape worth recording. The output was
labelled from the same field: the row that "b" had sorted to the front was
printed as `sub-1`, because the raw field really did say `1`. **The label
and the ordering were two derived values agreeing with each other, and they
agreed because they shared a malformed source.** Reading the labels back
confirmed nothing; the ordering had to be checked against the ranked list
it claimed to follow, which is a genuinely independent second source.

This is the quiet-sharing criterion -- two measurements only corroborate if
they fail independently -- appearing inside a **data field** rather than a
code path, where this document has recorded it four times before. A parse
and a label reading one malformed field are as coupled as two functions
calling one broken helper, and look far more like agreement.

The general form: **a label derived from the same field as the behaviour it
describes cannot audit that behaviour.** It can only report the field.

### Instance twenty-two: an operation that succeeds by ignoring an input

`corpus.load_pages` took a corpus root. It was changed to take a collection
*name*, and one existing test kept passing while calling it the old way --
handing it an absolute `Path` where a name now belonged.

    CORPUS / Path("/tmp/pytest-xyz/corpus")   ->   /tmp/pytest-xyz/corpus

`pathlib` discards the left operand entirely when the right one is
absolute. That is documented, deliberate, and the same rule `os.path.join`
has had for decades -- and it means the call **succeeded by ignoring one of
its arguments**. The test passed. It had skipped the entire collection
layer the change existed to introduce, and reported that the layer worked.

The shape is worth a name of its own because it is not a wrong answer and
not an exception: it is a *silently narrowed operation*. Related but
distinct from the two instruments already in this document --

* instance four's unstated denominator answers a narrower question than its
  name claims;
* instance nineteen's diff answered "how many *identifiable* boxes moved";
* **this one answers a question that uses only some of the inputs it was
  given, and cannot report which.**

Anywhere a path is composed from configuration, a CLI argument, an
environment variable or test fixture data, one absolute component silently
discards everything to its left. The generalisation past `pathlib`: an API
where a valid input can make earlier inputs irrelevant needs a **type**
guard, not a value check, because every value is legal.

The fix here was to refuse: `load_collection` raises `TypeError` if handed
anything but a `str`. Not because a `Path` cannot be turned into a name,
but because a caller who passed one was doing something other than what
they thought, and the only useful response is to say so.

### Instance twenty-three: the rule was known, applied nine times, skipped once

Ten scripted edits in one session. Nine carried `assert anchor in s`. One
did not, and that is the one that silently missed: it anchored on
`ap.add_argument("--no-follow-imports",` as a single line where the file
splits it across two. `str.replace` returned the string unchanged, wrote it
back, and reported nothing.

It survived every check that existed. `ast.parse` passed -- nothing was
malformed. The full suite passed -- because the *branch* the flag controls
had landed correctly, and only the flag that reaches it was missing, so no
test could see the gap. It surfaced as an argparse error in a background
job several minutes later.

**This is the strongest efficacy datum in this document, and it does not
argue for vigilance.** The author knew the rule, had applied it nine times
in the same hour, and skipped it once. A rule that must be remembered at
every use has a per-use failure rate that does not reach zero, and ten uses
was enough to find it. The heading below -- "writing a rule down does not
install it" -- is here demonstrated against a rule that *was* installed, in
the same session, by the same author, and still missed.

So the response was structural rather than exhortative. `scripts/lib/edit.py`
provides `sub(text, old, new)`, which performs the replacement **and** the
postcondition in one call and raises `EditMissed` otherwise. There is no
unchecked variant to reach for, and the checked call is shorter than
`text.replace(...)` plus an assert. The disciplined path is now also the
lazy path, which is the only kind of discipline that survives a tenth
repetition.

The same move, applied to the same problem elsewhere in this repo:
`tests/test_test_quality.py` does not ask anyone to remember that
`pytest.raises(Exception)` is worthless -- it fails the suite, with the file
and line, when one appears.

### Instance twenty-four: a small sample is not just noisy, it is biased toward "done"

Every Phase 3 scoping decision was made against three pages. The 79-page
survey put a number on what that cost, and the number is not what "small
sample" usually means.

Share of a page's boxes that sit inside a float or absolutely-positioned
subtree and are therefore never laid out:

| population | median |
|---|---:|
| the three Phase 3 pages | **0.0%** |
| the 79-page survey, pooled | 6.5% |
| government stratum | 30.3% |
| non-Latin stratum | 31.0% |

The three pages sat at the **extreme low end of the distribution they were
standing in for**. Not near the middle with wide error bars -- at the floor.
And the direction matters more than the distance: floats were deferred out
of Phase 3 partly because the corpus made them look like they gated almost
nothing, and the corpus made them look that way because it contained no page
that used them heavily.

**A small sample does not merely add variance around the right answer. It
can be systematically biased toward the conclusion that no further work is
needed**, because the features a small corpus fails to exercise are exactly
the features it reports as unexercised -- and "unexercised" reads as
"unimportant" unless something forces the distinction. This document's
existing framing (a feature with zero occurrences on three pages is an
absence of evidence) was right and was not enough: the register said the
corpus could not discriminate floats, and the *scoping decision* still used
the corpus's silence as permission to defer.

Worse, the misreading was double. Wikipedia's "172 of 201 flex boxes are
behind a float or an absolute" was quoted for weeks as evidence that
Wikipedia *over*-represented floats. It is a flex-specific ratio. As a share
of the whole page it is 0.0%, so the one page thought to be exaggerating the
problem was in fact hiding it.

The generalisable move is not "collect more pages" -- it is: **when a small
corpus reports that a deferred feature is unused, that is the corpus's
weakest claim, not its strongest.** Treat a zero from an underpowered sample
as a reason to widen before deciding, never as the decision.

### Instance twenty-five: one counter, two readings, opposite phase decisions

The float-versus-paint decision had a threshold written down before any
number existed: below 3% of a median page's boxes gated, paint goes next;
at or above 10%, floats are the remaining work.

Two counters could answer it. `layout_float_skipped` increments once per
**skipped subtree root**. `layout_boxes_deferred_subtree` increments once
per **box inside** one.

| metric | median page | mean | pages >= 10% | ruling |
|---|---:|---:|---:|---|
| skipped roots | 0.7% | 1.9% | 1 of 67 | paint goes next |
| boxes deferred | **6.5%** | **22.8%** | **32 of 67** | floats are the work |

Same corpus, same commit, same pre-registered rule, opposite phases. The
first reading was computed, tabulated per stratum, and about to be applied.

It was caught by reading the counter's increment site before applying the
rule -- and it was *pre-registration that made that check happen*. The plan
had committed to a specific sentence, "the share of element boxes that are
inside a float or an absolutely-positioned subtree", and the tabulated
number had to be checked against that sentence rather than against a
plausible name. A rule invented after seeing the data would have accepted
0.7% without a second thought, because 0.7% is a perfectly plausible number
for something called "float skipped".

So this is the unstated-denominator hazard (instance four) in its highest
stakes form so far, and the countermeasure that worked was not vigilance
about denominators in general. It was **having written down, in advance,
which population the decision was about** -- precisely enough that two
candidate counters could not both satisfy it.

### Writing a rule down does not install it

Every instance in this document was caught by **measurement**:

| # | caught by |
|---|---|
| 1 display census | probing an injected sheet after an exactly-zero delta |
| 2 `getlength` | computing the same advances from `fontTools` |
| 3 `getBoxModel` | asking `getContentQuads` the same question |
| 4 var() denominator | an implementer reproducing the figure and disagreeing |
| 10 `boxes_inline_split` | noticing 34 splits produced 2 fragments, and looking |
| 11 zero-margin collapse-through | probing Chrome before writing the claim into a brief |
| 12 literal NBSP, and a silent no-op edit | printing the remaining non-ASCII set, not the edit's success |
| 13 defaults counted as usage | splitting `display` counts by the origin of the winning declaration |
| 14 atomic-inline min-content | Chrome disagreeing with a number CSS Text 3 appeared to endorse |
| 15 the line box strut | re-measuring in a second harness, then diffing `document.compatMode` |
| 16 the literal NBSP, again | printing the probe's codepoints after it produced a surprising result |
| 17 a residual bucket reading 58 | the bucket being defined to read zero, and not reading zero |
| 18 a colspan delta of exactly zero | probing a suspiciously clean result, then checking the exit code |
| 19 a baseline delta of exactly zero | predicting the delta from the layout's own ascents, and getting a number the diff called impossible |
| 20 a counter reading 4 for 2 items | a test that stated the population from the fixture's own shape |
| 21 a substitution labelled `sub-1` that was not rank 1 | checking the ordering against the ranked list, not against its own labels |
| 22 a loader that skipped the whole collection layer | a type guard, after `CORPUS / abs_path` silently discarded `CORPUS` |
| 23 a scripted edit that changed nothing | making the postcondition part of the operation, not a thing to remember |
| 24 three pages reporting floats gate nothing | widening the corpus, and finding the old sample at the floor of the distribution |
| 25 a float share of 0.7% that was really 6.5% | reading the counter's increment site before applying a pre-registered rule |

**None was caught by remembering the rule.** Not one. In every case the
author knew the principle, had recently written or read it, and produced
the defect anyway; the detector was always a number that did not add up.
The 342-vs-519 pruning-root error is the same story -- it went into a
planning document days after the denominator hazard was documented, and was
found by re-measuring for a brief rather than by recall.

The honest conclusion is that these rules are worth very little as things
to remember and quite a lot as things to *run*. Vigilance is not a control.
So the countermeasures that have actually worked here are all mechanical:

* injection testing, which fails a build rather than asking anyone to be
  careful;
* seeded counters, so absence and zero are distinguishable without anyone
  checking;
* partition assertions (`sum(reasons) == dropped`, `seen == kept + dropped`)
  that fail loudly the moment a category is added and forgotten;
* the tree-hash check on the branch rewrite, which caught two truncations
  no amount of reading the script would have;
* a second derivation, run once at design time, rather than a resolution to
  be suspicious later.

Where a rule cannot be made mechanical, expect it to be violated and plan
for the violation to be *loud* -- which is the whole content of the
"quiet sharing" criterion above.

## The positive case: a check that caught a fault in itself

This document is almost entirely failures, so the one clear payout belongs
in it too.

The Chrome comparison carries **two identifiers** per box — a document-order
ordinal and a structural path — for a stated reason: when the ordinals line
up and the paths disagree, the DOM trees diverged, and that is an
`htmlparse` finding rather than a layout one. It was designed to separate a
defect in the *subject* from a defect in the *stage above it*.

During Task E it reported five fixtures as **tree divergence with identical
paths on both sides**. That combination is impossible under the failure the
scheme was built for: if the trees really had diverged, the paths would
differ. It is the signature of *one identifier being wrong about an element
both sides agree on* — and the ordinal was. Task B had been numbering
level-by-level rather than in document order since it was written,
contradicting its own docstring and the Phase 3 comparison contract, and
7,058 tests had not noticed.

The generalisation:

> **Any check that derives one quantity two independent ways can catch a
> defect in either derivation, not only in the subject.** A disagreement
> localises to "one of these three things is wrong", and the *pattern* of
> the disagreement usually says which.

That is a stronger property than redundancy. A second derivation added for
confidence turns out to be an instrument for debugging itself, because its
failure modes are distinguishable: paths differ and ordinals agree means one
thing, ordinals differ and paths agree means another, and both differing
means a third. A single identifier would have reported "mismatch" and
pointed nowhere.

Worth designing for deliberately: when adding a check, prefer two
derivations whose *disagreement patterns* are distinct over one derivation
that is merely more careful.

## What to do about it

* **A measurement is verified by a second measurement obtained a different
  way, not by inspection and not by internal consistency.** Two sources
  that agree is evidence. One source that looks right is not.
* **Treat a suspiciously clean result as a hypothesis to disprove.** Exactly
  zero, exactly integral, exactly unchanged -- each of those is a claim
  about the world that is usually a claim about the instrument. Probe the
  path before believing the number: inject a value you know should move it
  and confirm it moves.
* **When two methods can answer the same question, ask both once** before
  building on either. It is one throwaway script at design time and a
  rebuilt harness afterwards. This is mandatory, not prudent, whenever the
  first method's own diagnostics share the possibly-defective path AND a
  defect there would return a plausible green rather than failing loudly --
  see the criterion above. Shared paths that fail loudly are fine to rely
  on; most good checks have one.
* **Prefer the source closest to the data.** `hmtx` over a rasterizer's
  convenience wrapper; the manifest over a directory glob; the token stream
  over a regex. Each layer of convenience is a place a value can be
  quietly reshaped.
* **Write the countermeasure down with the number.** Every figure in
  `docs/fonts.md` and `docs/corpus.md` carries its derivation for this
  reason: a value with its provenance can be rechecked, a value alone
  can only be believed.
