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

The generalisation is narrow but worth having: **when a spec is layered,
the layer you are reading may not be the one that decides.** CSS Text 3
defers segmentation to UAX #14 without restating it, so a confident answer
from the top layer is not evidence about the bottom one.

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
