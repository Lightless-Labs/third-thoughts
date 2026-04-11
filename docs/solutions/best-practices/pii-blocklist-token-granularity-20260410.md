---
title: "PII blocklist tokens must be unambiguous — polysemous words block legitimate columns"
date: "2026-04-10"
category: best-practices
module: middens-cli
problem_type: best_practice
component: tooling
severity: medium
applies_when:
  - Designing column-name or field-name blocklists for data pipelines
  - Using tokenized matching on compound names (snake_case, camelCase)
  - Analytical outputs use derived/aggregate columns alongside raw content columns
tags:
  - pii-blocklist
  - data-validation
  - column-naming
  - false-positives
  - parquet
  - storage-layer
---

## Context

The middens CLI storage layer uses a PII blocklist to prevent raw personal content from being persisted to Parquet tables. Column names are split on non-alphanumeric characters (tokenized exact-match), and each token is checked against the blocklist. The original vocabulary contained 16 tokens including `text`, `message`, `messages`, `source`, `path`, and `filename`.

When the analyze-reshape pipeline wired techniques into the storage layer, two existing techniques broke immediately:

- `correction-rate`: column `user_messages` → token `messages` matched the blocklist.
- `thinking-divergence`: column `text_length` → token `text` matched the blocklist.

Both columns hold aggregate statistics (counts, string lengths), not raw PII content.

## Guidance

**Blocklist tokens must be words that appear exclusively in raw-content column names, never in derived or aggregate metric names.** Before adding a token, mentally test it against common analytical patterns: `{token}_count`, `{token}_length`, `total_{token}s`, `user_{token}s`. If any of those are plausible non-PII column names, the token is too polysemous for the blocklist.

The safe vocabulary after trimming (8 tokens): `body`, `content`, `cwd`, `excerpt`, `filepath`, `prompt`, `raw`, `snippet`. These words almost never appear as components of aggregate metric names.

The removed vocabulary (8 tokens): `path`, `paths`, `filename`, `filenames`, `text`, `message`, `messages`, `source`. All of these are common building blocks in analytical column names (`source_type`, `text_length`, `message_count`).

When in doubt, prefer a narrower blocklist with a separate integration test that asserts known technique output columns pass validation.

## Why This Matters

A false-positive blocklist rejection is worse than a false-negative for two reasons. First, it causes a runtime failure in an otherwise-correct pipeline — the technique produces valid output, but the storage layer refuses to write it. Second, the error message ("column blocked by PII filter") sends the developer on a PII investigation when the real issue is vocabulary curation. Debugging time compounds when multiple techniques fail for different blocked tokens.

The NLSpec's architectural decision (tokenized exact-match) was sound. The failure was purely in vocabulary selection — a data-curation problem, not an algorithm problem.

## When to Apply

- Designing any deny-list that operates on tokenized compound identifiers (snake_case, camelCase, kebab-case).
- Reviewing PII or sensitive-data filters in ETL pipelines, especially when the schema evolves as new analytical techniques are added.
- Writing NLSpecs that prescribe blocklist-based validation — the spec should require a polysemy test for each proposed token.

## Examples

**Bad — polysemous token blocks legitimate column:**

```
Blocklist: [..., "text", "message", ...]
Column: "text_length"  → tokenized to ["text", "length"]
Result: BLOCKED (false positive — this is a string length metric)
```

**Good — unambiguous token catches raw content:**

```
Blocklist: [..., "body", "prompt", ...]
Column: "response_body" → tokenized to ["response", "body"]
Result: BLOCKED (true positive — likely contains raw response content)

Column: "user_messages" → tokenized to ["user", "messages"]
Result: PASSED ("messages" not in trimmed blocklist)
```

**Polysemy test before adding a token:**

> Would `{token}_count`, `{token}_length`, `total_{token}s`, or `{token}_type` be a reasonable analytical column name? If yes, do not add the token.

