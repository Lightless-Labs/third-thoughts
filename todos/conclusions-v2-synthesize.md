# Conclusions v2 — LLM-Authored via `middens synthesize`

**Status:** Deferred, no commitment
**Blocked by:** `todos/conclusions-v1-manual.md` (v2 writes the same file format v1 consumes)
**Related:** `docs/design/output-contract.md` § "Where findings, conclusions, and tables live"
**Created:** 2026-04-06

## Why

v1 (manual `conclusions.md`) works, but writing a cross-technique narrative by hand is tedious and often the value of middens is in letting a model do the first-draft synthesis over the storage. v2 adds an optional `middens synthesize` command that reads a run's storage, prompts an LLM with the manifest + selected tables, writes `conclusions.md`, and returns.

v2 is entirely optional. Users who don't want LLM-authored narrative never run it. It composes cleanly on top of v1 — they share the same file format, and the rendering side doesn't care which produced the file.

## What

- [ ] **`middens synthesize <run_id> [--model <name>] [--provider <name>] [-o conclusions.md]`** — new command, entirely separate from analyze/report.
- [ ] **Reads storage** — manifest + Parquet tables — via the same `AnalysisRun` reader the view layer uses.
- [ ] **Prompt construction** — templated prompt that includes:
  - Run metadata (corpus size, session stratification, analyzer fingerprint)
  - Per-technique summaries and scalar findings (the manifest is small enough to include verbatim)
  - Selected table extracts (e.g., top N rows per headline table) — with token budgeting
  - Explicit guidance: "Identify convergent findings across techniques. Flag contradictions. Stay grounded in the data. Don't invent."
- [ ] **Model selection** — provider-agnostic. Bootstrap with:
  - Anthropic via `anthropic` crate or API
  - OpenAI via `async-openai`
  - Local via Ollama HTTP
  - Default configurable via `~/.config/middens/config.toml` (see `todos/remaining-cli.md` config file item)
- [ ] **Write `conclusions.md`** into the run directory. Overwrite requires `--force` or a prompt.
- [ ] **Update manifest** — add `conclusions_ref` if it wasn't already set. Record synthesize metadata in a new manifest section: `synthesis: { model, provider, prompt_hash, generated_at }`. This lets `middens diff` distinguish "conclusions changed because the data changed" from "conclusions changed because the model did."
- [ ] **Determinism controls** — `--temperature`, `--seed` if the provider supports it. Default temperature low (0.2) to favor grounded summaries.
- [ ] **Dry-run mode** — `--dry-run` prints the prompt without calling the model. Essential for iterating on the prompt template.
- [ ] **Cost disclosure** — print estimated token count and cost before making the call. Require confirmation unless `--yes`.

## Design considerations

- **Storage stays immutable.** v2 writes *to* the run directory, but only `conclusions.md` and a manifest field. Parquet and the per-technique manifest entries are never touched.
- **Prompts are logged.** The exact prompt used for each synthesis should be recoverable (either via `prompt_hash` + a canonical template, or by writing the prompt itself next to `conclusions.md`). Critical for reproducibility.
- **No silent overwrites.** If `conclusions.md` already exists (manual or prior synthesis), require `--force`.
- **Composability with v1.** If an analyst has hand-written `conclusions.md`, `middens synthesize` should refuse to overwrite without `--force`. Mixed workflow (LLM draft → human edit) is fine; just iterate via `--output conclusions.draft.md` then copy.
- **No prompt injection defenses required yet.** Middens operates on trusted local corpora. Revisit if that assumption changes.

## What is explicitly *not* in v2

- No agentic multi-step synthesis (no tool use, no self-critique loops). A single prompt, a single response, write to disk. If you want more, chain invocations externally.
- No per-technique LLM annotation. Technique summaries are already computed by the techniques themselves.
- No LLM-authored figures or tables. v2 only writes prose.
- No streaming output. The file appears atomically when generation finishes.

## Effort estimate

Medium. The command itself is maybe 300 lines. The prompt template will need iteration — plan for several dry-run cycles on a real run before committing the template to the repo. Provider abstraction is the non-trivial piece; start with one provider and a trait, add others later.

## Open questions

- **Which provider to bootstrap with.** Anthropic (direct) or OpenAI (larger ecosystem) are the obvious first targets. Could also bootstrap with a subprocess call to `codex exec` / `gemini -p` / `opencode run` to piggyback on existing CLI tooling and skip the SDK dependency — this is attractive for a first version because it matches how this project already delegates model work.
- **Where the prompt template lives.** Embedded in the binary (`include_str!`) vs `~/.config/middens/prompts/synthesize.md` (user-editable). User-editable is nicer for iteration but complicates reproducibility. Probably embed a default and allow override.
- **Whether to version the template.** If the embedded template changes between middens versions, old `synthesis.prompt_hash` values become meaningless. Consider a `template_version` field in the manifest synthesis metadata.
