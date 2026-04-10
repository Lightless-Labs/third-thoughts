---
title: "PII blocklist: split camelCase column names before matching"
status: todo
priority: P3
tags: [storage, pii, cli-triad]
source: coderabbit-pr1-review-2026-04-10
---

## Problem

The PII tokenizer in `storage/mod.rs:105-111` splits on non-alphanumeric characters only. camelCase columns like `rawData` tokenize to `["rawdata"]` which doesn't match the blocklist entry `"raw"`. Similarly, `messageBody` → `["messagebody"]` doesn't match `"body"`.

## Fix

Split on uppercase transitions in addition to non-alphanumeric separators. `rawData` → `["raw", "data"]` → matches `"raw"` → blocked.

## Why it's P3

Technique authors control column names. The overblock-is-acceptable principle means false positives are cheap (rename the column). No current technique uses camelCase column names. The risk is low for v1.
