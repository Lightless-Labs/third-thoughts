---
status: pending
priority: P3
source: coderabbit-review-2026-04-06
tags: [batch3, docs, spec-clarity, design]
---

# Batch 3 CodeRabbit Deferred Findings

Findings from `coderabbit review --plain --base origin/main` on the Batch 3 PR that were intentionally deferred because they are spec/design clarifications rather than real bugs. P1s and targeted P2s were addressed inline in the PR.

## Batch 3 NLSpec refinements

Location: `middens/docs/nlspecs/2026-04-06-python-techniques-batch3-nlspec.md`

- [ ] **L57 — lag-sequential adjusted residual edge cases**: Add guidance for when the z-score denominator factor `(1 − row_i_total/grand_total) * (1 − col_j_total/grand_total)` approaches zero (dominant single event type), or when expected counts are too small (E < 5). Instruct implementers to mark those cells as invalid rather than emit NaN. Note: the current green team implementation already guards against division-by-zero and non-finite z-scores via the boilerplate sanitize, but the spec text should document the threshold policy explicitly.

- [ ] **L133 — NCD cluster label mapping table**: The spec says "inferred from dominant symbol (e.g., read-heavy, edit-heavy)" without the full mapping. Add the explicit table: `R/G → read-heavy`, `E/W → edit-heavy`, `B → bash-heavy`, `S → skill-heavy`, `T → thinking-heavy`, `u/U → dialogue-heavy`, `C → correction-heavy`, fallback `{symbol}-heavy`. The implementation (`ncd_clustering.py`) already has this mapping, but the spec text lags.

- [ ] **L157 — ENA mid-correction band and minimum group size**: Spec splits sessions into low (≤10%) and high (>25%) but leaves the (10%, 25%] band unhandled. Amend to state: "Sessions with correction rates in (10%, 25%] are excluded from group comparison to ensure separation. Require ≥2 sessions per group before computing discriminative edges; otherwise skip Phase 6 and populate the edge findings with `none`." The implementation already does this; the spec should reflect it.

## Conclusions v1 design clarifications

Location: `todos/conclusions-v1-manual.md`

- [ ] **Cell position insertion rule**: Define fallback behaviour when cell 0 doesn't exist or isn't a title/metadata cell. Proposed: if cell 0 exists and has notebook metadata or a level-1 heading, insert conclusions at position 1; otherwise insert at position 0.
- [ ] **Error policy for missing/invalid conclusions.md**:
  - Missing file → log warning, skip rendering conclusions (non-fatal)
  - Unreadable file (permissions/encoding) → log error, surface recoverable failure to caller
  - Path escapes run directory → reject with security error, refuse to load
- [ ] **HTML renderer XSS hardening**: Document that the HTML renderer must either (a) use a markdown library that escapes raw HTML by default (e.g., `pulldown-cmark` with default settings, `markdown-it` with html disabled) or (b) sanitize the HTML output via an allow-list before serving. Note that conclusions are freeform markdown authored by (usually) trusted analysts, but the rendered report may be shared publicly, so defense-in-depth is warranted.

## Conclusions v2 design clarifications

Location: `todos/conclusions-v2-synthesize.md`

- [ ] **Flag consistency (`-o` / `--output`)**: Command signature uses `-o conclusions.md` but the doc later references `--output conclusions.draft.md`. Pick one canonical long form and document both aliases: `[-o|--output <path>]`.
- [ ] **Token budgeting strategy**: Define (1) how total token budget is determined (tied to model context window via provider metadata, or fixed 50k default), (2) selection policy when tables exceed budget (top-N rows per table with N proportional to table's scalar-findings count, or just first-N), (3) allocation across multiple tables (proportional to `len(rows)` with a per-table floor of 5 rows and cap of 100), (4) truncation indicator (append "… (N more rows)" as a commented row).
- [ ] **`conclusions_ref` update rules**: Clarify behaviour when the field is already set. Rule proposal: if `conclusions_ref` exists and equals the target path, update `synthesis` metadata in place; if it exists and differs, refuse without `--force`; if a manual `conclusions.md` exists without a manifest entry, populate `conclusions_ref` pointing to it on first synthesize run (but only write synthesis metadata for LLM-generated content).
- [ ] **`prompt_hash` scope**: Document that `prompt_hash` is computed over the **fully expanded prompt** (template + all injected data + system instructions), not just the template. This makes it a content-addressable identifier suitable for `middens diff` to distinguish data-driven changes from template-driven changes. Consider also storing `template_id` + `template_version` separately for the latter.
- [ ] **Prompt logging strategy (A vs B)**: Pick one: (A) store the full expanded prompt text next to `conclusions.md` as `conclusions.prompt.txt`, or (B) store `prompt_hash` + maintained canonical template registry with recovery procedure. Recommendation: A for v2 simplicity; B can be added later if template drift becomes a problem.

## Red team step definitions

Location: `middens/tests/steps/python_batch1.rs`

All addressed inline in the PR (division-by-zero assert, stricter skipped-fallback wording). No deferred items.

## Python techniques

Location: `middens/python/techniques/{convention_epidemiology,ncd_clustering,ena_analysis}.py`

All P1 bugs addressed inline in the PR (numpy sanitize, O(n²) lookup, session id validation, ena regex double-escape). No deferred items.

## Process note

These deferred items are *doc/spec refinements*, not bugs. They should land alongside or before the storage/view reshape (`todos/output-contract.md`) since the conclusions v1/v2 work depends on those specs being tight. If the reshape is delayed, these items can stay deferred without blocking anything else.
