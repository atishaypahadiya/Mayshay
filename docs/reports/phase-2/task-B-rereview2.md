# Task B — Re-review round 2 (scoped)

## Finding Verdicts

1. **Replace `_after_head_fallthrough` with a provenance parameter, keep behaviour identical** — ADDRESSED. `treebuilder.py:412-424` `dispatch(self, token, from_mode: str | None = None)` forwards to `getattr(self, f"_mode_{self.mode}")(token, from_mode)`. Instance attribute and its set/clear are gone (old lines 27-32, 175/179 deleted). `_frameset_in_body(from_mode)` at `treebuilder.py:658-661` checks `from_mode == "after_head"` instead of token identity. Traced both exemptions and the flagged case: `<frameset>` at top of an empty document reaches `_in_body_start` via `_mode_after_head`'s else-branch `dispatch(token, from_mode="after_head")` (line 532) → exempt. `<body><frameset>` has `<body>` handled by `_mode_after_head`'s explicit branch (no dispatch, no from_mode), so `<frameset>` arrives at `_mode_in_body` straight from `build()`'s loop (`treebuilder.py:398`, `dispatch(token)`, default `from_mode=None`) → `_frameset_in_body(None)` → not exempt → reports. Matches report's claim.

2. **`tokenizer_parse_errors` on the crash row should read `builder.tokenizer.metrics["parse_errors"]` directly** — ADDRESSED. `test_html5lib_tree.py:362-364` now reads `builder.tokenizer.metrics["parse_errors"]` in the except branch, with a comment explaining why (`build()`'s copy step never ran).

## Adjudication: the cross-document-leak dispute

**Prior review ("latent only") is correct; the implementer overstated the defect.** Every call site constructs a fresh `TreeBuilder` per document with no reuse across parses: `parse()` at `treebuilder.py:790` (`TreeBuilder(source).build()`), `test_html5lib_tree.py:214` (`builder = TreeBuilder(case.data)` per corpus case), `scripts/conformance_report.py:55`, and every unit test in `test_treebuilder.py`. `build()` (`treebuilder.py:395-410`) has no try/except of its own — an exception during dispatch propagates straight out and the instance is abandoned; nothing calls `build()` a second time on the same object. So even in the old code, a mid-fall-through exception leaving `_after_head_fallthrough` set could only affect *that same, now-dead* instance — never "the next document," which always got a fresh `__init__()` resetting the flag to `None`. There is no code path anywhere in this repo that reuses one `TreeBuilder` across documents. The parameter refactor is still a good change (no lifetime to manage, uniform provenance signal), but calling the old defect "a cross-document leak" is not supported by the actual call graph.

## `from_mode` threading — all 8 sites checked

Verified every re-dispatch site names the mode it's actually leaving, matching the enclosing method: `initial`(461)→`"initial"`, `before_html`(477)→`"before_html"`, `before_head`(493)→`"before_head"`, `in_head`(516)→`"in_head"`, `after_head`(532)→`"after_head"`, `in_body`'s `</html>` handoff(644)→`"in_body"`, `text` EOF(765)→`"text"`, `after_body`(786)→`"after_body"`. `_mode_in_body`→`_in_body_start` forwards its *received* `from_mode` unchanged (line 544) rather than hardcoding `"in_body"` — correct, since that's what preserves the after_head exemption when a frameset token bounces from after_head→in_body. Default `None` (line 412) is exercised only by `build()`'s top-level loop call (line 398, no `from_mode` arg) — correct default for genuine top-level entry, not merely convenient. No wrong or stale `from_mode` found.

## CSV asymmetry judgment

Holds. `tree_parse_errors` reads `builder.metrics["parse_errors"]`, incremented synchronously inside `_error()` as tree-construction errors are recorded (`treebuilder.py:37-39`), so it's a live, correct partial count even mid-crash. `tokenizer_parse_errors` was previously read from `builder.metrics["tokenizer_parse_errors"]`, populated only by a copy step at the very end of `build()` (line 409) — never reached if `build()` raised, leaving the `Counter` default `0` indistinguishable from a real zero. Reading `builder.tokenizer.metrics["parse_errors"]` directly (line 362) sidesteps the copy. The comment at the site (`test_html5lib_tree.py:356-361`) states both halves of the asymmetry explicitly ("The tree count above is safe because `_error` increments it as errors happen") — sufficient for a future reader not to "fix" it into symmetry.

## New Breakage in the Fix Diff

None found. Grepped for any direct callers of `_mode_*`, `_in_body_start`, `_frameset_in_body`, or `dispatch(` outside the class — none exist; all are internal, and the new parameters are all defaulted so no external caller could break. `_frameset_in_body`'s signature change from `token: StartTagToken` to `from_mode: str | None` is only called from the one site inside `_in_body_start`, updated in the same diff.

## Out-of-Scope Observations

None beyond what's already excluded (`CommentToken.pos`, `TREE_ERROR_CODES` membership, 404/474 whole-corpus figure).

## Environment check

`git status`: branch `phase-2-css-to-styled-tree`, working tree clean, nothing to commit. `.venv/lib/python3.13/site-packages/__editable__.mayshay-0.1.0.pth` reads exactly `/Users/atishaypahadiya/projects/mayshay/src` — untouched.

## Verdict

**Fix round: All findings addressed, no new Critical/Important breakage.** Both open items (provenance parameter, CSV crash-row fix) are correctly implemented. The implementer's "cross-document leak" claim about the missing `finally` is not supported by the codebase's actual instantiation pattern — the prior review's "latent only" stands — but this does not undermine the fix itself, which is behaviour-identical and correctly threaded.
