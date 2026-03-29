# Additional Parsers

Session log parsers to implement for middens. The parser trait is defined, stubs exist for some.

## To Implement

- [ ] **OpenCode** — Check `~/.opencode/` for session log format. Schema unknown — need a user with OpenCode installed to provide sample files. Stub at `src/parser/opencode.rs`
- [ ] **Cursor** — Check `~/.cursor/` for session log format. Schema unknown — need a user with Cursor installed to provide sample files. Likely stores sessions differently (SQLite? proprietary format?). Stub at `src/parser/cursor.rs`
- [ ] **Gemini CLI** — Partial stub exists at `src/parser/gemini.rs`. Research found Gemini uses directory-based storage (`~/.gemini/history/{project}/`), NOT JSONL. Needs a fundamentally different parser approach — may need to read SQLite or other structured storage. `.project_root` marker files in each history folder
- [ ] **Aider** — Popular open-source coding assistant. Check for session log format
- [ ] **Continue.dev** — VS Code extension. May store conversation history
- [ ] **Windsurf / Codeium** — Check for session log format
- [ ] **Amazon Q Developer** — Check for session log format
- [ ] **GitHub Copilot Chat** — VS Code extension logs. May be in VS Code's internal storage

## Adding a New Parser

1. Create `src/parser/<tool>.rs`
2. Implement the `SessionParser` trait (see `src/parser/mod.rs`)
3. Register in `all_parsers()` in `src/parser/mod.rs`
4. Add detection logic in `src/parser/auto_detect.rs`
5. Add default discovery path in `src/corpus/discovery.rs`
6. Create test fixture at `tests/fixtures/<tool>_sample.jsonl`
7. Add tests
