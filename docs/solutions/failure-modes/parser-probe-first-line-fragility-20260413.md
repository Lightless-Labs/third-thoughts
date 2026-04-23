---
title: "Parser probes that read only the first line break silently on format evolution"
date: 2026-04-13
category: failure-modes
module: middens-parser
problem_type: silent_data_loss
component: corpus_ingestion
severity: high
applies_when:
  - "A parser's can_parse() probe reads only the first non-empty line"
  - "A tool vendor adds a new preamble record type to their log format"
  - "Zero-byte placeholder files exist in the corpus directory"
tags: [rust, parser, corpus, claude-code, jsonl, silent-drop, format-evolution, known-types]
---

# Parser Probes That Read Only the First Line Break Silently on Format Evolution

## Context

~130 session files from `corpus-full/claude-code-live/` silently disappeared from every corpus run with "no parser matched". No errors, no warnings at the file level — they just weren't there. Debugging revealed two separate causes.

Commit: `867f57b`. Files: `middens/src/parser/claude_code.rs`, `middens/src/parser/auto_detect.rs`.

## Root Cause 1: `KNOWN_TYPES` not kept current with upstream format

`can_parse()` reads the first non-empty line of the file, extracts its `type` field, and returns `false` if that type isn't in `KNOWN_TYPES`. Newer Claude Code versions write a `file-history-snapshot` preamble record as the very first line — before any actual session content. That type wasn't in `KNOWN_TYPES`, so the whole file was rejected.

The `parse()` loop already handled unknown record types gracefully (`_ => continue`). Only the probe was wrong.

Fix: add `"file-history-snapshot"` and `"summary"` to `KNOWN_TYPES`. The probe's job is to confirm "this looks like a Claude Code JSONL file", not to exhaustively enumerate every record type that might appear.

### Pattern to avoid

```rust
// Fragile: rejects any file whose first line has a type we haven't enumerated
const KNOWN_TYPES: &[&str] = &["human", "assistant", "system"];

fn can_parse(path: &Path) -> bool {
    let first_line = read_first_nonempty_line(path);
    let record_type = extract_type(&first_line);
    KNOWN_TYPES.contains(&record_type)  // fails on new preamble types
}
```

### Pattern to prefer

```rust
// Resilient: probe confirms format identity, not exhaustive type coverage
const KNOWN_TYPES: &[&str] = &[
    "human", "assistant", "system",
    "file-history-snapshot", "summary",  // preamble records added in newer versions
];

fn can_parse(path: &Path) -> bool {
    let first_line = read_first_nonempty_line(path);
    // If the first line parses as valid JSON with a "type" field, it's probably ours.
    // KNOWN_TYPES is a hint, not a contract — keep it current after upstream updates.
    KNOWN_TYPES.contains(&extract_type(&first_line))
}
```

Or, if the format is distinctive enough, probe on structure rather than type value:

```rust
fn can_parse(path: &Path) -> bool {
    // Just check it's JSONL with a "type" field — let parse() do the real filtering
    first_nonempty_line_has_field(path, "type")
}
```

## Root Cause 2: Zero-byte placeholder files produce spurious warnings

Claude Code creates a `.jsonl` file when a session is opened, before anything is written to it. These zero-byte files are valid filesystem entries but contain no parseable content. Every parser's `can_parse()` returned `false`, producing a "no parser matched" warning for each one.

Fix: early return in `parse_auto()` for zero-byte files — skip silently, no warning.

```rust
pub fn parse_auto(path: &Path) -> Result<Option<Session>> {
    if path.metadata().map(|m| m.len() == 0).unwrap_or(false) {
        return Ok(None);  // placeholder file, nothing to parse
    }
    // ... normal probe/parse logic
}
```

## Lesson

Parser probes that only look at the first line are fragile against format evolution. When the tool vendor adds a new preamble record type, every file with that preamble silently falls out of the corpus — no parse error, just absence. `KNOWN_TYPES` needs to be updated whenever the upstream tool (Claude Code, Codex, etc.) ships a format change. Consider adding a test fixture with a preamble-first file to catch this class of regression early.

The combination of silent dropping and no per-file error makes this especially nasty to diagnose: the corpus just gets smaller, and you only notice if you're tracking counts.
