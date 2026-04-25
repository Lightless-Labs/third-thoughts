---
title: "Codex/pi reasoning observability is turn-level, not just visible vs redacted"
date: 2026-04-25
category: methodology
module: middens/parser/codex
problem_type: best_practice
component: tooling
severity: high
applies_when:
  - "A provider emits encrypted reasoning plus optional plaintext summaries"
  - "Parser output feeds thinking-dependent methodology or risk-suppression analysis"
  - "Reviewers suggest warning-and-continue behavior for ambiguous reasoning payloads"
  - "A session can contain summary-visible, signature-only, full-text, absent, and unknown reasoning evidence"
tags: [middens, codex, pi, reasoning-observability, parser, methodology, review-process]
related_components: [thinking-divergence, session-model, codex-parser, pr-review]
---

# Codex/pi reasoning observability is turn-level, not just visible vs redacted

## Context

PR #2 (`4afbc19`) implemented adaptive reasoning observability for Codex/pi-style logs in `middens`. The motivating trace shape was not the older Claude Code binary of "raw thinking block visible" versus "thinking structurally redacted". Codex/pi can emit reasoning records where the private reasoning remains encrypted, while a provider-selected summary is optionally exposed on some turns and absent on others.

That makes observability a **message-level / turn-level property**. A single session can be mixed:

- `FullTextVisible` — raw plaintext thinking is present.
- `SummaryVisible` — a plaintext provider summary is present, but raw reasoning is opaque.
- `SignatureOnly` — a reasoning/signature marker exists, but no plaintext summary is present.
- `Absent` — no reasoning evidence exists in the parsed message.
- `Unknown` — the parser saw a shape it cannot confidently classify.

The durable lesson is methodological as much as technical: a provider summary is not raw chain-of-thought. Treating it as `Message::thinking` silently turns raw-thinking analyses into summary/public analyses and contaminates the denominator. Which is very on-brand for this repo, but still bad.

## Guidance

### Keep raw thinking, reasoning summaries, and signatures separate

Codex/pi summaries should be stored separately from raw thinking:

```rust
Message {
    thinking: None,                         // raw private reasoning only
    reasoning_summary: Some(summary_text),  // provider-selected summary
    reasoning_observability: SummaryVisible,
    raw_content: vec![ContentBlock::ReasoningSummary { text: summary_text }],
    // ...
}
```

Do **not** populate `Message::thinking` from `thinkingSignature.summary`, `summary`, or any other provider-selected summary field. Downstream techniques such as `thinking-divergence` should only operate on raw thinking text unless they explicitly declare that they are measuring summary/public divergence.

### Roll up from message-level evidence to session-level labels

Derive session observability from message observability instead of guessing at the session boundary:

- multiple concrete modes in one session become `Mixed`;
- all absent becomes `Absent`;
- unknown evidence remains conservative instead of being reported as a confident concrete mode;
- absent user/system messages do not force an otherwise reasoning-bearing session to `Mixed`.

This mirrors the compound scoping rule: population labels should be explicit, conservative, and hard to accidentally over-claim.

### Fail clearly on ambiguous Codex reasoning shapes

PR #2 intentionally rejected several tempting warning-and-continue paths:

- standalone `response_item.payload.type = "reasoning"` is not silently skipped;
- `thinkingSignature` plus plaintext `thinking` without an explicit summary fails clearly;
- signed plaintext whose summary differs from the extracted summary fails clearly;
- unsigned plaintext plus a mismatched explicit summary also fails clearly;
- degenerate empty unsigned thinking blocks with no signature/text/summary are `Absent`, not fabricated signatures.

The principle: if the parser cannot tell whether a field is raw reasoning, a summary, a signature, or future provider metadata, it should not choose a convenient label. It should reject the shape with an error that says what was wrong, what shape is supported, and an example.

```rust
anyhow::bail!(
    "unsupported Codex response_item.payload.type=\"reasoning\"; \
     expected payload.type=\"message\" until standalone reasoning items are modelled. \
     Example supported item: ..."
);
```

That is stricter than some reviewers preferred, but it preserves corpus semantics. A partial parse that drops opaque reasoning would make a reasoning-bearing session look `Absent`, which is the exact silent data loss this change is trying not to do.

### Treat unrecognized Codex content as indeterminate until the raw type is preserved

`RawContentBlock::Unknown` currently comes from a serde catch-all that discards the original `type` string. Because the parser cannot prove the unknown block is unrelated to reasoning, PR #2 makes `Unknown` dominate the message-level merge.

That is conservative and sometimes blunt. The better future shape is tracked in `todos/codex-typed-unknown-content-blocks.md`: preserve the unknown block type, classify known-unrelated future types separately, and keep reasoning-like or indeterminate future types as `Unknown` or fail-fast.

### Test parser semantics at the block level

Cucumber steps that say "thinking blocks" or "reasoning summary blocks" should count `ContentBlock` variants in `raw_content`, not messages with `thinking.is_some()` or `reasoning_summary.is_some()`. A single assistant message can carry multiple blocks; message-count assertions drift as soon as fixtures grow past 0/1.

PR #2 added/updated scenarios for:

- summary-visible + signature-only mixed sessions;
- degenerate empty unsigned thinking blocks;
- standalone reasoning response item rejection;
- ambiguous signature plaintext without summary;
- signed plaintext/summary mismatch;
- unsigned plaintext/summary mismatch;
- non-consecutive summary deduplication;
- unknown block forcing `Unknown` even beside a known thinking block.

## Why This Matters

### Methodology: summaries are a different observational layer

A `SummaryVisible` Codex/pi turn is not equivalent to `thinking_visibility=Visible`. It means:

1. reasoning probably happened;
2. raw reasoning is opaque;
3. the provider chose to expose some summary text;
4. downstream analysis sees the provider summary, not the private reasoning.

Reporting those turns as raw visible thinking would corrupt findings like risk suppression and thinking/text divergence. The right scope is explicit:

```text
reasoning_observability=FullTextVisible      # raw thinking analysis eligible
reasoning_observability=SummaryVisible       # summary/public analysis only
reasoning_observability=SignatureOnly        # reasoning present, plaintext absent
session_reasoning_observability=Mixed        # session has multiple modes
```

### Implementation: unknown is safer than falsely absent

`Absent` is a positive claim: the parser found no reasoning evidence. `Unknown` is an epistemic claim: the parser saw something it cannot classify. Confusing the two makes later corpus statistics look cleaner than they are.

That is why unrecognized Codex blocks currently force `Unknown` even when a known concrete block is also present. It may be over-conservative for unrelated future block types, but it does not silently erase potential reasoning evidence.

### Process: bot review is useful when the invariant is explicit

PR #2 went through repeated Codex, Gemini, and CodeRabbit passes. The useful pattern was not "accept every suggestion"; it was "state the invariant, then fix or decline against that invariant."

Examples from the review loop:

- **Accepted:** CodeRabbit found standalone `reasoning` response items were silently dropped. The fix made them fail clearly and added regression coverage.
- **Accepted:** Codex found signed plaintext and summaries could disagree. The fix validates equality against both raw and deduplicated summary forms.
- **Accepted:** Gemini found recursive summary traversal could be made iterative. The fix removed recursion without changing traversal order.
- **Declined:** Gemini suggested warning-and-continue for ambiguous signed shapes and standalone reasoning. That would preserve robustness but weaken corpus semantics, so the comments were answered with rationale instead.
- **Deferred:** standalone reasoning modelling and typed unknown-block handling became explicit todos instead of speculative in-PR design.

The process lesson reinforces existing review docs: every comment gets a response (`fixed`, `deferred`, or `declined with rationale`), and every deferred design gap gets a durable todo.

## When to Apply

Apply this pattern when:

- a provider emits reasoning metadata that is not raw thinking text;
- a parser needs to distinguish visible content from opaque/signature metadata;
- downstream findings depend on thinking visibility or reasoning observability;
- review feedback asks for graceful degradation that would silently pick a methodological label;
- an unsupported shape is real but the model has no representation for it yet.

Do not apply it blindly to user-facing import tools where partial ingestion is preferable and metrics are not involved. This is a research-corpus parser rule: correctness of labels beats best-effort ingestion.

## Examples

### Bad: silently treating a provider summary as raw thinking

```rust
// Wrong: provider summary is not raw chain-of-thought.
message.thinking = extract_summary(block);
message.reasoning_observability = FullTextVisible;
```

### Good: separate summary from raw thinking

```rust
message.thinking = None;
message.reasoning_summary = extract_summary(block);
message.reasoning_observability = ReasoningObservability::SummaryVisible;
message.raw_content.push(ContentBlock::ReasoningSummary { text: summary });
```

### Bad: silently skipping standalone reasoning events

```rust
if item_type != "message" {
    continue; // makes reasoning-bearing sessions look absent
}
```

### Good: fail clearly until the model can represent the event

```rust
if item_type == "reasoning" {
    anyhow::bail!(
        "unsupported Codex response_item.payload.type=\"reasoning\"; \
         expected payload.type=\"message\" until standalone reasoning items are modelled. \
         Example supported item: ..."
    );
}
```

### Good: test block counts, not message counts

```rust
let actual = session
    .messages
    .iter()
    .flat_map(|message| &message.raw_content)
    .filter(|block| matches!(block, ContentBlock::ReasoningSummary { .. }))
    .count();
```

## Key Findings From PR #2 Review

- Adaptive disclosure is itself behavioral data: summary-visible turns and signature-only turns can alternate within one session.
- `thinking_visibility` remains useful for raw thinking, but Codex/pi requires a separate `reasoning_observability` axis.
- `Unknown` should be a first-class observability result, not a temporary nuisance to collapse away.
- Clear parser failures are preferable to clean-looking but semantically false corpus rows.
- Automated reviewers are strongest when they attack invariants from different angles: CodeRabbit caught schema/workflow gaps, Codex caught semantic edge cases, Gemini caught traversal/dedup/robustness questions.
- Conflicting reviewer advice should be resolved against the project invariant, not by majority vote. Here, the invariant was denominator hygiene and no silent coercion of ambiguous reasoning data.

## Related

- `docs/feedback/adaptive-reasoning-observability-20260423.md` — original feedback and implementation note.
- `docs/solutions/methodology/thinking-visibility-inference-heuristic-20260407.md` — raw thinking visibility heuristic; this doc extends the distinction to Codex/pi reasoning observability.
- `docs/solutions/methodology/redact-thinking-stratification-20260406.md` — prior denominator hygiene lesson for redacted thinking.
- `docs/solutions/best-practices/stratification-is-multi-axis-and-findings-compound-20260406.md` — compound scoping rule.
- `docs/solutions/architecture/pluggable-parser-trait-pattern-20260320.md` — parser architecture background.
- `docs/solutions/best-practices/pr-review-reply-discipline-and-declining-false-positives-20260407.md` — review reply discipline used during PR #2.
- `docs/solutions/workflow-issues/multi-round-bot-review-convergence-20260407.md` — multi-round bot review workflow reinforced by PR #2.
- `todos/codex-standalone-reasoning-response-items.md` — follow-up to model standalone reasoning events.
- `todos/codex-typed-unknown-content-blocks.md` — follow-up to preserve unknown Codex block types.
