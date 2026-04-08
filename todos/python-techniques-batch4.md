# Python Techniques — Batch 4

**Created:** 2026-04-06
**Status:** **DONE 2026-04-06**
**Completed:** 2026-04-06 (270/270 scenarios passing)
**Priority:** P2 (was — now done)
**Source:** Cross-reference of `scripts/*.py` against `middens/python/techniques/*.py` revealed 4 analytical scripts that were never ported.

## Background

`scripts/` holds 26 `.py` files. After accounting for:

- 6 originals already ported to Rust (burstiness_hawkes → burstiness, ecology_diversity → diversity, entropy_rate_anomaly → entropy, tool_sequence_mining → markov, 010_thinking_block_divergence → thinking-divergence, correction_classifier → correction-rate)
- 13 originals already ported as Python techniques (Batches 1+2+3)
- 3 utilities not eligible for porting (`extract_conversation.py`, `corpus_analytics.py`, `correction_classifier.py` as a labelling library)
- 1 v1/v2 pair where v2 supersedes v1 (`006_user_signal_analysis.py` → drop v1)

…there remain **4 analytical scripts that should become middens techniques**:

| # | Source script | Technique name | Notes |
|---|---|---|---|
| 1 | `006_user_signal_analysis_v2.py` | `user-signal-analysis` | **English-only** (see scoping below). Touches thinking blocks — must coordinate with the redact-thinking confound. |
| 2 | `007-cross-project-graph.py` | `cross-project-graph` | NetworkX directed graph + HITS-like centrality. Output shape: edge-list table + node-list table (NOT a single graph blob). |
| 3 | `018_change_point_detection.py` | `change-point-detection` | Ruptures PELT algorithm. **Adds `ruptures` to `python/requirements.txt`** — first new dep since Batch 1. Verify embedded reinstall works on a clean cache dir. |
| 4 | `cross_project_timeline.py` | `corpus-timeline` | **Promoted from utility** — see "corpus-timeline rationale" below. |

Total after Batch 4: **23 distinct analytical techniques** (6 Rust + 17 Python).

### corpus-timeline rationale (option A, with B as follow-up)

Original triage said "drop, defer to a view renderer over the manifest." That's wrong: **reports must be reproducible without the source corpus**, so the (date, project, session_count) tuples need to be written into Parquet at analyze-time. Two ways to land that:

- **Option A (now):** ship as a tiny technique. Emits one DataTable `corpus_timeline` with columns `[date, project, session_count]`. ~30 lines of Python. Stored like any other technique result, renderable by any future view layer. **This is what Batch 4 implements.**
- **Option B (later, after storage/view reshape lands):** the reshape will write a canonical `sessions.parquet` (session_id, project, started_at, ended_at, n_messages, …) as part of the manifest. At that point `corpus-timeline` becomes a pure GROUP BY over that table — zero collection cost — and the technique can be **deleted** in favour of a view spec. ~30-line cleanup, not a migration.

Track the option-B refactor in `todos/output-contract.md` under a new "post-reshape cleanup" subsection.

### user-signal-analysis scoping (English-only)

The v2 script uses ~80 literal English regex patterns across 5 categories (correction / redirect / directive / approval / frustration). A French/Spanish/Chinese/Japanese user's messages will classify as "minimal" on every category — silent false negatives. **The NLSpec MUST:**

1. State explicitly under "What" that the technique is English-only and that non-English sessions are skipped (not scored).
2. Add a `language` precondition on each session (read from `Session.language`, defaulting to `"unknown"`).
3. Emit a `skipped_non_english_sessions` finding alongside the regular results.
4. Link to `todos/multilingual-text-techniques.md` in the spec body and in code comments.
5. Defer the thinking-block-touching parts of v2 entirely (those parts are gated on the redact-thinking remediation in `todos/redact-thinking-header-correction.md`). Port only the user-message classification layer in this batch.

This matches the scope of the existing English-only techniques (`thinking-divergence`, `correction-rate`'s lexical layer) — see the audit in `todos/multilingual-text-techniques.md`. The remediation plan (option C: detect language + refuse) will land as a separate piece of work and will retrofit all three techniques uniformly.

## Per-script triage — DONE 2026-04-06

Triage already completed by an Explore subagent + manual review. See the table above for verdicts. No further triage needed before writing NLSpecs.

## Adversarial port pattern (per technique)

Same flow as Batches 1–3. Lessons from Batch 3 codified in `docs/HANDOFF.md` apply directly:

1. **NLSpec** (Why / What / How / Done). One spec per technique. Include the shared contract block (table shape `{name, columns, rows}`, role casing, NaN sanitisation, empty-input behaviour).
2. **Red team** — Gemini 3.1 Pro Preview via `/gemini-cli` skill. Writes `tests/features/techniques/python_batch4.feature` from the **DoD only**. Must produce step definitions in `tests/steps/python_batch4.rs` that exercise the technique through `PythonTechnique::new` (mirror `python_batch3.rs` structure).
3. **Green team** — different model from red team. Default: **Kimi K2.5 via `/opencode-cli` skill** (`kimi-for-coding/k2p5`, `--format json`, bash heredoc for file writes, one file per invocation). Prompts include only the **How** section + shared contract attached via `-f`.
4. **Information barrier** — orchestrator never edits step definitions or implementation directly. PASS/FAIL only is forwarded between teams. When tests fail, classify (contract gap / red bug / green bug / improvement) and route appropriately.
5. **Wire into the embedded manifest** — add to `middens/src/techniques/mod.rs::PYTHON_TECHNIQUE_MANIFEST` AND to `middens/src/bridge/embedded.rs::TECHNIQUE_SCRIPTS`. Both lists must stay in sync. Update the count assertion in `tests/features/cli/list_techniques.feature` (currently `19` → would become `23`).
6. **PR review** — run `coderabbit review --plain --base origin/main` locally first; expect 3–6 rounds of Codex review on the remote PR.

## Stop / parking criteria

- `change-point-detection` adds `ruptures` to `python/requirements.txt`. The PR **must** include a clean-cache reinstall test: blow away `$XDG_CONFIG_HOME/middens/python/`, run `middens analyze --techniques change-point-detection`, verify `uv pip install` succeeds and the technique runs.
- `cross-project-graph` output shape MUST be flat tables (`edges` + `nodes`), not a graph blob. Batch 3 lost a round to exactly this kind of shape ambiguity — pin it in the NLSpec before red team writes anything.
- `user-signal-analysis` MUST NOT silently score non-English sessions. If the green team's first cut omits the language gate, route as a contract gap, not a green bug — re-confirm the gate is in the spec and re-dispatch.

## Done definition

- All 4 techniques ported as PythonTechniques (`user-signal-analysis`, `cross-project-graph`, `change-point-detection`, `corpus-timeline`)
- All 4 wired into `PYTHON_TECHNIQUE_MANIFEST` (in `middens/src/techniques/mod.rs`) AND `TECHNIQUE_SCRIPTS` (in `middens/src/bridge/embedded.rs`) — both lists must stay in sync
- `list-techniques` shows 23 (currently 19) → cucumber row count assertion updated 19 → 23
- All NLSpecs in `middens/docs/nlspecs/2026-XX-XX-python-techniques-batch4-nlspec.md`
- Each technique has a feature file under `tests/features/techniques/python_batch4.feature` with shared contract scenarios + technique-specific assertions
- `python/requirements.txt` updated with `ruptures` and the embedded reinstall verified on a clean cache dir
- `user-signal-analysis` has the English-only language gate AND a `skipped_non_english_sessions` finding
- `corpus-timeline` is documented as "to be deleted post-reshape" — add a comment in the script and a line under the post-reshape-cleanup subsection of `todos/output-contract.md`
- All 261+ existing scenarios still pass
- New techniques are NOT marked essential (Python techniques default to non-essential — see manifest)
