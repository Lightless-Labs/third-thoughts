---
title: Distinguish unknown Codex content block types before reasoning observability rollup
status: open
priority: medium
issue_id: PR-2
tags: [middens, codex, parser, reasoning-observability]
source: PR #2 review follow-up
---

# Distinguish unknown Codex content block types before reasoning observability rollup

## Context

PR #2 made `RawContentBlock::Unknown` force message-level `ReasoningObservability::Unknown` so unsupported Codex content shapes do not get silently labelled as confidently absent/visible/summary/signature.

That is conservative, but the current serde `#[serde(other)]` catch-all discards the original `type` string. If Codex later introduces unrelated non-reasoning content block types, the parser cannot distinguish those from future reasoning-bearing block types.

## Follow-up

Replace the catch-all enum arm with a representation that preserves the raw `type` value and enough raw payload metadata to classify unknown blocks deliberately:

- known non-reasoning future types can avoid forcing reasoning observability to `Unknown`;
- unknown or reasoning-like future types should keep forcing `Unknown` or fail clearly;
- tests should cover both an unrelated unknown type and a reasoning-like unknown type.

## Done when

- Codex parser preserves the unknown content block type string.
- Unknown-block reasoning observability behavior is intentional by type category, not a blanket catch-all.
- Existing conservative behavior remains for reasoning-like/indeterminate future types.
