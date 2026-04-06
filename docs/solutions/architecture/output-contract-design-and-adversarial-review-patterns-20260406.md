---
title: "Design learnings: output-contract reshape, conclusions layering, and adversarial counter-analysis as publication gate"
date: 2026-04-06
category: architecture
module: middens-output
problem_type: design_decision
component: output_contract
severity: high
applies_when:
  - "Designing output formats for data-analysis pipelines"
  - "Choosing between notebook-as-primary vs notebook-as-view formats"
  - "Layering post-hoc narrative synthesis on top of deterministic analysis"
  - "Running adversarial review on sympathetic replication findings before publishing"
  - "Evolving NLSpecs mid-adversarial-review cycle"
tags: [output-contract, storage-view-split, notebooks, parquet, conclusions, figurespec, adversarial-review, counter-analysis, nlspec, design]
---

## Context

This session sat at the intersection of three things landing simultaneously: (1) the `middens` output format had outgrown its initial "markdown + json + ascii" trio and needed a redesign before more techniques were ported; (2) PR #4 (Batch 3 Python techniques — sequence alignment, NCD, motif discovery, repertoire) was deep in adversarial review with multiple reviewers (Codex, Copilot, CodeRabbit) surfacing findings that turned out to be NLSpec contradictions rather than implementation bugs; and (3) a sympathetic replication of GH#42796 (a Claude reasoning-performance regression claim) had come back "confirmed" and we were one keystroke from filing it upstream when an adversarial counter-analysis pass demolished the result. The architectural decisions made during the session — captured in `docs/design/output-contract.md`, `todos/output-contract.md`, the `conclusions-v1-manual` / `conclusions-v2-synthesize` split, the Batch 3 NLSpec amendments, and the decision NOT to file upstream — share a common thread: separating *what is canonical* from *what is rendered*, and separating *what is sympathetic* from *what is adversarially survivable*. The seven learnings below are the transferable principles.

## 1. "Notebook without the footguns" framing for analysis output

**Decision.** `middens analyze` writes a canonical store (`store/tables/*.parquet` + `store/manifest.json`) and a regeneratable views layer (`views/report.ipynb`, `views/report.md`, `views/report.html`, optionally `.pluto.jl`, `.qmd`). The Parquet store is the source of truth; every view is a pure function of the store. See `docs/design/output-contract.md` §"Storage vs. view split".

**Rationale.** Notebooks are the lingua franca of data-science communication — interactive, embed figures inline, run on every analyst's laptop. But notebooks-as-source-of-truth carry hidden state, terrible diffs, pip drift, and out-of-order cell execution. We wanted the *presentation* benefits without the *operational* baggage. Parquet is columnar, typed, diff-friendly via row-group hashes, and trivially re-readable from any view renderer.

**Alternatives considered.** (a) Notebook-as-primary (ipynb checked into the store) — rejected due to diff/state issues. (b) JSON-only — rejected because JSON isn't typed, doesn't handle large tables well, and needs custom viewers. (c) SQLite — considered, but Parquet wins on portability and pandas/polars/duckdb interop.

**Consequences.** View renderers become trivial functions. New view formats (Pluto, Quarto, Observable) can be added without touching the pipeline. Reproducibility collapses to "ship the store".

**Generalization.** When adopting a popular format as your output, decompose its benefits from its baggage and adopt only the benefits. Notebooks-as-output ≠ notebooks-as-source-of-truth. The same reasoning applies to PDFs, dashboards, and any format that mixes data with presentation.

## 2. Conclusions are post-hoc annotation, not pipeline output

**Decision.** Cross-technique narrative ("conclusions") lives outside `middens analyze`. Two write-paths land in the same `conclusions.md` slot under `views/`: `middens conclude` (manual, human-authored — see `todos/conclusions-v1-manual.md`) and `middens synthesize` (LLM-driven over the store — see `todos/conclusions-v2-synthesize.md`). View renderers pick up `conclusions.md` if present and overlay it.

**Rationale.** `analyze` must remain deterministic, cheap, and reproducible. Synthesis is none of those things — it's narrative, opinionated, and changes as understanding deepens. Baking it into the pipeline would couple "I changed my mind about what this means" to "I have to re-run analysis", which is wrong.

**Alternatives considered.** (a) Conclusions as a technique inside `analyze` — rejected, breaks determinism. (b) Conclusions only via LLM — rejected, sometimes a human just wants to write the paragraph. (c) Conclusions in a separate repo — rejected, locality matters for reading.

**Consequences.** Pipeline stays pure. Narrative is replaceable, versionable, and can be regenerated against an updated store without re-running techniques.

**Generalization.** Don't bake synthesis into the data pipeline. Keep the pipeline factual; let narrative happen as a later, optional, overlay-able layer that consumes the pipeline output. Synthesis ≠ analysis.

## 3. `FigureSpec` as data, not bitmap

**Decision.** The previously-stub `FigureSpec` slot resolved to `FigureKind { VegaLite(serde_json::Value), Png(Vec<u8>), TableRef { table_key: String, chart_type: ChartKind } }`. Vega-Lite is preferred. PNG is the escape hatch for techniques that can only emit raster (e.g. matplotlib in Python bridge). TableRef defers chart construction to the renderer entirely. See `docs/design/output-contract.md` §FigureSpec.

**Rationale.** Vega-Lite is interactive in JupyterLab and VS Code, embeds natively in `.ipynb` as a `application/vnd.vegalite.v5+json` MIME bundle, degrades to a JSON code block in plain markdown, and renders to PNG via `vl-convert` for the HTML/PDF view. A spec composes with view-format-specific rendering; a bitmap is frozen at one resolution and one theme.

**Alternatives considered.** (a) PNG-only — rejected, no interactivity, no theme adaptation. (b) Matplotlib pickles — rejected, not portable across language runtimes. (c) Plotly — considered, but Vega-Lite has cleaner JSON and better static-export tooling.

**Consequences.** Python techniques that already produce matplotlib must either translate to Vega-Lite (preferred) or fall through to PNG. The bridge interface gains a small Vega-Lite helper.

**Generalization.** Figures should be specs, not bitmaps, wherever the ecosystem supports it. A spec is `f(data, theme, viewport)`; a bitmap is the frozen output of one such evaluation. Specs travel; bitmaps don't.

## 4. NLSpec as living contract during adversarial review

**Decision.** During PR #4 review, three rounds of reviewer comments surfaced contradictions *inside* the NLSpec at `middens/docs/nlspecs/2026-04-06-python-techniques-batch3-nlspec.md`: Phase-1 vs Phase-3 filter placement disagreement, min-projects threshold listed as 2 in one place and 3 in another, NCD alphabet missing the `A` (assistant-text) symbol. The orchestrator amended the spec directly rather than re-dispatching red or green teams, and annotated the amendments inline in the NLSpec.

**Rationale.** Adversarial-process orthodoxy says "don't touch tests or implementation; route feedback to the correct team". But internal contradictions in the spec are neither a red-team bug nor a green-team bug — they're a *spec-clarity* bug. Routing them through either team produces noise (red writes a test for the wrong invariant; green implements one of two contradictory clauses arbitrarily). The spec is the orchestrator's surface, and the orchestrator owns it.

**Alternatives considered.** (a) Dispatch to red ("write a test that pins the right behavior") — rejected, red doesn't have authority to resolve contradictions. (b) Dispatch to green ("pick one and implement") — rejected, that hides the contradiction. (c) Open a meta-issue and pause — rejected, slows velocity for no gain.

**Consequences.** The foundry adversarial taxonomy needs a fourth bucket alongside "red bug / green bug / contract gap / improvement": **spec internal contradiction**, owned by the orchestrator, fixed at the spec level, with the spec amendment becoming the authoritative resolution that both teams will see on next dispatch.

**Generalization.** Adversarial red/green processes need explicit handling for spec-internal contradictions surfaced by review. The spec is a living contract, not a frozen artifact, and the orchestrator is its custodian. Amend in place; annotate the amendment; do not silently re-route to a team that lacks authority to resolve it.

## 5. Always run an adversarial counter-analysis before publishing a sympathetic finding

**Decision.** A sympathetic replication of GH#42796 had returned "C1, C2, C3 all confirmed; recommend filing upstream". Before filing, an adversarial counter-analysis was run (see `~/claude-reasoning-performance-counter-analysis/report.md`). The adversarial pass executed four attacks: C3 collapsed under reweighting (p=0.445, dead), C2 failed significance (p=0.20), C1 said nothing about the degraded tail the original claim emphasized, and the entire sympathetic story was confounded by a 45× session-count explosion between W10 and W11 with a simultaneous 64× collapse in tools-per-session — composition drift, not behavior drift. The upstream PR was not filed.

**Rationale.** Sympathetic analysis seeks evidence *for* a hypothesis; it is structurally biased toward confirmation. Without an adversarial pass, the analyst is one motivated-reasoning step away from a false positive. The cost of an adversarial pass is hours; the cost of filing a false claim upstream is reputation.

**Alternatives considered.** (a) Trust the sympathetic result — rejected, this is the second time in Third Thoughts that population contamination has flipped a finding (the first being "thinking blocks prevent corrections", retracted in `experiments/interactive/survival-results.json`). (b) File with caveats — rejected, caveats don't undo the headline.

**Consequences.** A near-miss false positive was caught. The counter-analysis report itself becomes a reusable template for future replications.

**Generalization.** A single sympathetic confirmation is not sufficient evidence for publication. Always run an adversarial pass, and weight asymmetrically: when sympathetic says "confirmed" and adversarial says "the corpus cannot support the claim", the honest verdict is the more restrictive one. This is the data-analysis analogue of falsificationism.

## 6. Corpus composition as a first-class analysis artifact

**Decision.** The counter-analysis surfaced that the W10→W11 session population changed character at scales (45× session count, 64× tools/session) that cannot be model-behavior signals. Going forward, "composition drift over time" becomes a metric monitored continuously and surfaced *before* any comparative analysis runs. This is the second composition-contamination retraction in Third Thoughts (see `docs/solutions/methodology/population-contamination-interactive-vs-subagent-20260320.md` for the first).

**Rationale.** When the underlying population changes, none of your per-window metrics can be trusted as behavior signals — they're confounded by who/what is in the sample. Composition checks are cheap (counts, distributions, KL divergence between window populations) and catch a class of errors that would otherwise survive to the report.

**Alternatives considered.** (a) Stratify after the fact when a finding looks weird — rejected, that's how the first contamination got published. (b) Trust upstream collection to keep populations stable — rejected, populations drift naturally with adoption curves and tooling changes.

**Consequences.** A `middens corpus drift` (or equivalent) check should run as a pre-flight before any temporal or comparative technique. Findings reports should include a composition-drift section by default.

**Generalization.** For any temporal dataset, treat composition drift as a first-class metric, not an afterthought. Surface it before, not after, the comparative analysis. If composition has shifted materially between windows, no comparative claim across those windows is safe without explicit reweighting or stratification.

## 7. Deferred-todos are first-class work products

**Decision.** During PR #4 review, low-priority CodeRabbit findings were captured to `todos/batch3-coderabbit-deferred.md` with explicit "Fix" / "Don't fix" rationale per item, rather than silently deferred or dismissed. Each deferred item carries a one-line justification.

**Rationale.** A code review comment is not a binary accept/reject. It's a three-state decision: (1) fix inline now, (2) fix as a tracked follow-up with the rationale captured, (3) dismiss with an explicit justification. Conflating (2) and (3) is how technical debt becomes invisible; conflating (1) and (2) is how PRs stall forever. Explicit capture of state (2) is the trick that makes review conversations productive without sacrificing merge velocity.

**Alternatives considered.** (a) Fix everything inline — rejected, kills velocity. (b) Dismiss low-priority items — rejected, loses information. (c) Open GitHub issues — rejected, friction too high for findings that are 1-line todos.

**Consequences.** The `todos/` directory becomes the persistent backlog of "things review surfaced that we chose not to fix in this PR and here's why". Future work can grep it.

**Generalization.** Make the three-state nature of review-comment triage explicit. Every comment gets one of {fix-inline, fix-as-followup-with-rationale, dismiss-with-justification}. State (2) requires a written artifact, not a verbal "we'll get to it". Quality drift and reviewer frustration both come from leaving (2) implicit.

## References

- `docs/design/output-contract.md` — full storage/view split design
- `todos/output-contract.md` — work breakdown for the reshape
- `todos/conclusions-v1-manual.md`, `todos/conclusions-v2-synthesize.md` — layered conclusions design
- `middens/docs/nlspecs/2026-04-06-python-techniques-batch3-nlspec.md` — Batch 3 NLSpec including mid-review amendments
- `~/claude-reasoning-performance-counter-analysis/report.md` — adversarial counter-analysis that killed the upstream PR
- `todos/batch3-coderabbit-deferred.md` — three-state review triage in practice
- `docs/solutions/methodology/population-contamination-interactive-vs-subagent-20260320.md` — first composition-contamination retraction
- `experiments/interactive/survival-results.json` — retracted "thinking blocks prevent corrections" finding
- `docs/HANDOFF.md` — session summary
- PR #4 (Batch 3 Python techniques) — adversarial review log
