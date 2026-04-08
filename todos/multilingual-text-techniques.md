# Multilingual Text Techniques — Audit + Remediation

**Created:** 2026-04-06
**Status:** Open
**Priority:** P2 (methodology — affects interpretability of headline findings, but not blocking)
**Source:** Batch 4 triage of `006_user_signal_analysis_v2.py` revealed it is English-only. An audit of existing techniques showed the same limitation in two production techniques.

## The issue

Three middens techniques use literal English regex / token lists to analyse user-emitted natural language. Sessions in any other language (French, Spanish, German, Chinese, Japanese, …) silently score zero or near-zero on these metrics, producing **false negatives that look like clean signal**.

## Audit

| Technique | Layer | English literals | Effect on non-English sessions |
|---|---|---|---|
| `thinking-divergence` (Rust) | `src/techniques/thinking_divergence.rs:17` | `RISK_TOKENS = ["risk","concern","worry","problem","issue","error","fail","wrong","careful"]` | Risk thinking is invisible. **Compounds with the redact-thinking-2026-02-12 confound** — the 85.5% suppression number is conditional on both `thinking_visibility=visible` AND `language=en`. |
| `correction-rate` (Rust, upstream classifier) | `src/classifier/correction.rs:35` | `correction_patterns` Priority-3 lexical layer (`"wrong"`, etc.) | Priority 1+2 (structural: tool_result blocks) still work — those are language-invariant. The Priority-3 lexical layer adds nothing for non-English sessions. Net: under-counts corrections in non-English sessions but doesn't go to zero. |
| `user-signal-analysis` (proposed Batch 4) | NLSpec under writing | ~80 English regex patterns across 5 categories | Non-English sessions classify as "minimal" on every category. **Will be scoped as English-only at port-time** (linked here). |

**Language-invariant by construction (no remediation needed):** markov, entropy, burstiness, diversity, hsmm, process_mining, prefixspan_mining, smith_waterman, tpattern_detection, lag_sequential, ncd_clustering, ena_analysis, spc_control_charts, granger_causality, survival_analysis, information_foraging, convention_epidemiology, cross-project-graph, change-point-detection, corpus-timeline. These operate on tool sequences, timestamps, or filesystem structure.

## The 85.5% headline finding under stratification

Already P1-pending re-validation under header stratification (see `todos/redact-thinking-header-correction.md`). This audit adds a **second** stratification axis: language. The honest restated finding is:

> "Among English-speaking, thinking-visible sessions in the corpus, 85.5% of risk tokens that appear in thinking blocks are absent from the user-facing text."

That number may still be robust — but the population scope is much narrower than the original report implies. Both gates need to land before re-asserting it.

## Remediation options

### A. Per-language pattern packs (lowest effort, partial fix)

Add `en.toml`, `fr.toml`, `es.toml`, etc. — each with the same category schema. Pre-classify sessions by language (`whatlang-rs` crate, ~1ms per session, no model download). At runtime each technique loads the matching pack.

- **Pro:** small, deterministic, no ML dependency.
- **Con:** requires writing patterns per language, which is the same brittleness as the English version, just N times. Coverage will lag.
- **Effort:** medium per technique. ~half a day per technique × 3 techniques × N languages.

### B. Small multilingual embedding classifier (highest fidelity)

Replace the regex layer entirely with a small embedding-based intent classifier (multilingual-MiniLM or similar) that scores each user message into the same 5 categories. Training data: hand-label ~500 messages per category, fine-tune.

- **Pro:** language-agnostic by construction, scales without per-language work.
- **Con:** ML dependency in middens (PyTorch in the `uv` venv), model weights to ship (~120MB minilm, or fetch on first run), labelling effort.
- **Effort:** ~1 week to bootstrap, then maintenance.

### C. Detect language and refuse (cheapest, hardest to misread)

Pre-classify sessions by language. Techniques in this audit refuse to score non-English sessions and emit a `skipped_non_english` count in their findings. Reports include the skipped fraction prominently.

- **Pro:** trivial to implement, zero risk of false-negative inflation, totally honest.
- **Con:** loses signal on the non-English share of the corpus.
- **Effort:** ~2 hours total.

### Recommendation

**Start with C. Add B as a follow-up if non-English share is large enough to matter.** Skip A.

Rationale:
- C is cheap and *correct* — it never produces a wrong number, only an absence
- It immediately makes the headline findings honest about scope
- Once C is in place, we can measure the non-English fraction empirically and decide whether B is worth it
- A is the worst of all worlds: more code, partial coverage, same brittleness

## Concrete tasks (when this todo is picked up)

- [ ] Add `whatlang` (or equivalent) crate to `middens/Cargo.toml`
- [ ] Add `Session::language: Option<String>` populated during parsing (BCP-47 tag, e.g. `"en"`, `"fr"`)
- [ ] Update `thinking-divergence` to skip sessions with `language != Some("en")` and emit `skipped_non_english_sessions` finding
- [ ] Update the Priority-3 lexical layer in `classifier/correction.rs` to short-circuit on non-English sessions
- [ ] Update `user-signal-analysis` (when ported in Batch 4) to do the same — its NLSpec already says English-only
- [ ] Re-run the 4 risk-suppression replications under `language=en + thinking_visibility=visible` stratification
- [ ] Update `docs/methods-catalog.md` for the affected techniques noting the language scope
- [ ] Update `docs/HANDOFF.md` Key Findings table to annotate the 85.5% row with "scope: en + visible thinking"
- [ ] Write `docs/solutions/methodology/multilingual-text-confound-2026-XX-XX.md` documenting the lesson

## Cross-references

- `todos/redact-thinking-header-correction.md` (P1 — orthogonal stratification axis on the same techniques)
- `docs/solutions/methodology/population-contamination-interactive-vs-subagent-20260320.md` (the prior precedent — third stratification axis on the same finding)
- `todos/python-techniques-batch4.md` (the trigger for this audit)
