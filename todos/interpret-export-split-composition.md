---
status: deferred
priority: P2
tags: [middens, interpret, export, split, stratification, composition]
source: NLSpec review pass 4 (Codex finding 3)
blocked_by: [cli-triad-analyze-interpret-export]
---

# Cross-stratum composition for `interpret` / `export` on split runs

## Why deferred

The CLI triad NLSpec (pass 4) deliberately refuses to operate on top-level split runs: `middens interpret --analysis-dir <run>` and `middens export --analysis-dir <run>` both exit non-zero and direct the caller to pass `<run>/interactive` or `<run>/subagent`. This is a fail-fast shortcut that unblocks the milestone without answering hard composition questions:

1. **Per-technique naming under composition.** Each stratum produces the same technique slugs (e.g. `hsmm`, `information_foraging`). If a single interpretation covers both strata, do the per-technique files become `interactive-hsmm-conclusions.md` / `subagent-hsmm-conclusions.md`? Do they nest under `interactive/` / `subagent/` sub-directories inside the interpretation dir? Does the interpretation manifest's `per_technique` map become `Map<(stratum, slug), path>`?
2. **Prompt composition.** Does the LLM get one prompt with both strata's data (doubled token budget)? Two separate prompts (one call per stratum, results stitched)? A summary-of-summaries pass?
3. **Cross-stratum narrative.** The whole point of `--split` is to surface interactive-vs-subagent differences. A good cross-stratum interpretation ought to compare the two strata, not just describe each independently. But "compare" requires a second pass after the per-stratum passes complete. That's a multi-step agentic workflow, which conflicts with the NLSpec's "single prompt, single response" design for `interpret`.
4. **Notebook layout for split exports.** Does `export` produce one notebook with two top-level sections (`## Interactive` + `## Subagent`) and a third `## Comparison` section? Or two notebooks? If one notebook, how does it present the shared techniques — side-by-side tables, stacked sections, tabs?

None of these have obvious right answers, and picking one silently is worse than a loud refusal. Revisit after the per-stratum path is shipped and a real user has complained about having to run the commands twice.

## What

- [ ] Revisit the questions above against real user feedback.
- [ ] Decide on a data-model shape for cross-stratum interpretations (probably `ConclusionsIndex.per_stratum_per_technique: Map<String, Map<String, String>>` or equivalent, but wait for a concrete use case before committing).
- [ ] Decide whether `interpret` grows a `--compose-strata` flag or a new `middens compose` command.
- [ ] Decide on the prompt strategy (single-prompt-both-strata vs two-prompt-stitch vs multi-step-agentic).
- [ ] Decide on the notebook layout for composed split exports.
- [ ] Write scenarios covering at least: stratum-A-only interpretation, stratum-B-only interpretation, composed interpretation, and the "export a composed interpretation" case.

## Workaround until this lands

Callers with split runs invoke `interpret` twice (once per stratum) and `export` twice. The two resulting notebooks are independent. This is fine for the headline comparison case (risk-token suppression by stratum) because the two notebooks are opened side-by-side by the reader.

## Effort

Medium-to-large. Depends on how agentic the composition ends up being. Single-prompt composition is maybe 200 lines of code + prompt template surgery. Multi-step composition is a redesign of how `interpret` talks to runners and probably wants its own NLSpec.
