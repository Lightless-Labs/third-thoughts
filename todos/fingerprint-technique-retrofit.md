---
status: deferred
priority: P2
tags: [middens, refactor, technique, storage, fingerprint]
source: conversation 2026-04-09 (CLI triad milestone scoping)
blocks: []
blocked_by: [cli-triad-analyze-interpret-export]
---

# Fingerprint retrofit — reframe as a technique

## Why deferred

Originally designed as part of the storage/view reshape (see `docs/design/output-contract.md` § "Side-effect: `middens fingerprint`"). Pulled out of the CLI triad milestone (2026-04-09) to keep that milestone shippable. Do this once the triad has landed and the storage layer is stable on a real corpus.

## What

The `middens fingerprint` command currently exists as a stub with two conceptual layers:

1. **Analyzer fingerprint** — middens version, git SHA, technique versions, Python bridge versions, corpus hash. **This already lives in `manifest.json` under the triad design**, so there's nothing to do here; the standalone command is redundant.
2. **Subject fingerprint** — per-session environment metadata: model, cwd, MCP servers present, CLAUDE.md hash, tool allowlist, etc. Harvested from session logs. Currently homeless.

The retrofit:

- [ ] Implement **`subject_fingerprint`** as a new technique (Rust, since it operates on `Session` structs directly). Writes a table with one row per session and columns for the harvested fields. Stored in `data/subject_fingerprint.parquet` like any other technique.
- [ ] Implement **`fingerprint_evolution`** as a second technique that reads the fingerprint table and reports drift across time-ordered sessions (new MCP server appears, CLAUDE.md hash changes, model version bumps, etc.). One row per drift event.
- [ ] **Remove the standalone `middens fingerprint` command** — or keep it as a thin alias that runs the fingerprint technique(s) and renders only that slice via `export`.
- [ ] Update `PYTHON_TECHNIQUE_MANIFEST` / `techniques::all_techniques_with_python()` wiring to include the new techniques.
- [ ] Cucumber scenarios for both techniques.

## Constraints

- Subject fingerprint must respect the PII rules in `docs/design/output-contract.md` § "Table schema constraints". `cwd` is explicitly on the forbidden list — store a hash, not the raw path. MCP server names are fine; MCP server configs are not. CLAUDE.md hash is fine; CLAUDE.md content is not.
- `fingerprint_evolution` must produce stable output across runs (no timestamps-as-findings that make `middens diff` noisy).

## Effort

Small-to-medium. ~300–500 lines across the two techniques + wiring + tests. No new dependencies.
