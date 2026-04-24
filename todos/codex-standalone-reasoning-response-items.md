---
title: "Model standalone Codex reasoning response_items"
status: todo
priority: P3
tags: [middens, parser, codex, reasoning-observability, review-feedback]
source: pr-2-coderabbit-review-2026-04-24
---

## What

Codex logs can contain `response_item` entries whose payload `type` is not `message`, including standalone `reasoning` items. The current parser only reconstructs user/assistant/system messages and intentionally does not turn standalone non-message response items into synthetic messages.

## Why

PR #2 added observability for reasoning blocks embedded in message content (`thinkingSignature` summary/signature-only cases). CodeRabbit noted that standalone reasoning response items are still ignored by the message reconstruction path.

We should decide how these map into the session model instead of guessing:

- should a standalone encrypted reasoning item contribute `SignatureOnly` to session-level observability?
- should it become a synthetic assistant message with empty public text?
- should it be represented as metadata / an event stream separate from messages?
- what does the real Codex JSON shape look like across model/provider versions?

## Acceptance criteria

- Collect at least two real fixture examples of standalone Codex `response_item.payload.type = "reasoning"`.
- Add parser tests for the observed shapes.
- Preserve summaries separately from raw thinking, as in PR #2.
- Do not silently coerce encrypted/opaque reasoning into `Message::thinking`.
- If unsupported shapes are encountered, fail clearly or record a documented `Unknown`/opaque marker rather than pretending it is raw visible thinking.

## Priority

P3 for now: not part of the adaptive embedded-block feedback fixed in PR #2, but worth modelling before using Codex/pi reasoning observability for headline findings.
