---
date: 2026-03-20
problem_type: architecture_pattern
severity: medium
symptoms:
  - "Need to parse session logs from 6+ different AI agent tools with different JSONL schemas"
  - "Adding a new format should be a single-file PR"
tags: [parser, trait, pluggable, middens, rust]
---

# Pluggable Parser Trait Pattern for Multi-Tool Session Logs

## Pattern

Define a `SessionParser` trait that all format-specific parsers implement. Auto-detection sniffs the first JSONL line to dispatch to the correct parser. All parsers produce the same unified `Session` type.

## Implementation

```rust
pub trait SessionParser {
    fn source_tool(&self) -> SourceTool;
    fn can_parse(&self, path: &Path) -> bool;  // Cheap probe — first line only
    fn parse(&self, path: &Path) -> Result<Vec<Session>>;
}
```

Adding a new format:
1. Create `src/parser/<tool>.rs` implementing the trait
2. Register in `all_parsers()` in `src/parser/mod.rs`
3. Add detection logic in `src/parser/auto_detect.rs`
4. Add default discovery path in `src/corpus/discovery.rs`
5. Create test fixture at `tests/fixtures/<tool>_sample.jsonl`

## Key Schemas Documented

| Tool | Format | Key Differences |
|------|--------|----------------|
| Claude Code | JSONL (rich) | Thinking blocks with signatures, `sessionId`+`version` envelope |
| Codex CLI | JSONL | `session_meta`/`turn_context`/`message` types, encrypted reasoning |
| OpenClaw | JSONL | Multi-agent metadata, delivery-mirror pattern, per-agent files |
| Gemini CLI | Directory-based | NOT JSONL — needs fundamentally different approach |

## Gotchas

- `can_parse` must NOT read the entire file (P0 from code review — causes OOM on 200MB files)
- Auto-detect should call `detect_format` (one line read) then dispatch to `parse` (one full read) — not `can_parse` + `parse` (two reads)
- Path-based detection should check path components, not substrings (`.contains(".claude")` matches `.claude-tools`)
- Post-parse, run classifiers on the parsed sessions — parsers emit `Unclassified` messages

## Cross-References

- Implementation: `middens/src/parser/`
- Code review triage: `todos/middens-review-triage.md`
