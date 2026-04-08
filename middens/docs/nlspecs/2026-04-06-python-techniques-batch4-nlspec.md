# NLSpec: Python Techniques — Batch 4

**Status:** Draft
**Created:** 2026-04-06
**Batch:** user-signal-analysis, cross-project-graph, change-point-detection, corpus-timeline

## 1. Why

Batches 1–3 ported 13 Python techniques. Cross-reference of `scripts/*.py` against the wired manifest revealed 4 remaining analytical scripts. Batch 4 closes out the port:

- **user-signal-analysis** — classify user messages into correction/redirect/directive/approval/question categories + frustration intensity (English-only, see section 3.1)
- **cross-project-graph** — directed reference graph between projects with simple centrality
- **change-point-detection** — ruptures PELT regime-shift detection on per-session numeric signals
- **corpus-timeline** — per-day per-project session counts for temporal composition audits

Post-Batch-4 total: **23 distinct techniques** (6 Rust + 17 Python).

## 2. What

Four Python technique scripts in `middens/python/techniques/` following the same bridge contract as Batches 1–3. All produce `TechniqueResult` JSON on stdout. No figures (tables only).

Scripts must be registered in both `PYTHON_TECHNIQUE_MANIFEST` (`middens/src/techniques/mod.rs`) and `TECHNIQUE_SCRIPTS` (`middens/src/bridge/embedded.rs`).

`python/requirements.txt` must add:
- `ruptures>=1.1,<2.0` (change-point-detection)
- `networkx>=3.0,<4.0` (cross-project-graph)

## 3. How

### Shared Contract

Same as Batches 1–3 — see `2026-04-05-python-techniques-batch1-nlspec.md` for the full Session/TechniqueResult schemas. Key reminders:

- Input: JSON file path as `argv[1]` containing `Session[]`
- Output: `TechniqueResult` JSON to stdout (`name`, `summary`, `findings`, `tables`, `figures: []`)
- `tool_calls[].input` is a dict (not string)
- Roles are `User`/`Assistant` (PascalCase); classifications include `HumanCorrection`, `HumanDirective`, `HumanApproval`, `HumanQuestion`, `Unclassified`
- Tables: `{"name": ..., "columns": [...], "rows": [[...]]}` — NOT `{"title", "headers"}`
- `rows` is `List[List[Value]]`, type-homogeneous per column (use `null` for missing, never `"N/A"`)
- Sanitize NaN/Infinity to `None` before `json.dumps`
- Stderr diagnostics on unrecoverable error, exit 1
- Empty/insufficient sessions: return valid `TechniqueResult` with explanatory summary containing `"insufficient"`, NOT error exit
- Summary assertions are literal substrings (case-insensitive but space-sensitive)
- No filesystem writes, no plotting, no model downloads
- No raw user or assistant text in any table cell (derived metrics only; tool-name symbols and stable session IDs are fine)
- Project name available at `session.metadata.project` (may be empty string)
- Session-level timestamp: first message's `timestamp` field; session id at `session.id`

### 3.1 user-signal-analysis (`user_signal_analysis.py`)

**Reference:** `scripts/006_user_signal_analysis_v2.py` — **port only the user-message classification layer**. Do NOT port thinking-block analysis or tool-preceding-frustration (deferred pending `todos/redact-thinking-header-correction.md`).

**Scope: English only.** The five category pattern sets and the frustration-intensity lexicon are all literal English regexes. Non-English user messages will classify as `minimal` on every category. See `todos/multilingual-text-techniques.md` for the remediation plan.

**Language gate:**
- Per user message, compute a cheap heuristic: `is_english = fraction of ASCII letters in non-whitespace chars >= 0.85`. Messages below the threshold count toward `skipped_non_english_messages` and are not classified.
- Do NOT import `langdetect` or any ML library. Keep it deterministic and dependency-free.

**Algorithm:**
1. For each session, iterate `messages` where `role == "User"` and text is non-empty.
2. Strip `<system-reminder>`, `<command-name>`, and `[Request interrupted]` blocks from text before classification. Filter messages that are entirely boilerplate — count toward `boilerplate_messages`, skip classification.
3. Apply the language gate. If `is_english == False`, increment `skipped_non_english_messages`, continue.
4. For each surviving message, run the five category regex sets (patterns below). Each category is a boolean (text may fall into multiple categories).
5. Compute `frustration` intensity 0–5:
   - +1 if matches mild lexicon (`\bhmm\b`, `\bsigh\b`, `\bugh\b`, `\bmeh\b`)
   - +2 if matches medium lexicon (`\bno\b`, `\bnope\b`, `\bwrong\b`, `\bstop\b`)
   - +3 if matches firm lexicon (`\bi said\b`, `\bstill wrong\b`, `\blisten\b`)
   - +4 if matches exasperated lexicon (`\bwhy did you\b`, `\bwhy are you\b`, `\bfor the (last|nth) time\b`)
   - +1 bonus if `len(text) > 20` AND fraction-of-uppercase-letters `>= 0.5`
   - Clamp to max 5
6. Escalation detection: within a session, find maximal runs of ≥2 consecutive classified user messages where `max(frustration) >= 2` and intensities are non-decreasing. Record start index, length, peak.

**Pattern sets (all case-insensitive, word-boundary where shown):**
- `correction`: `\bno[,.]?\s`, `^no$`, `\bwrong\b`, `\bnot that\b`, `\binstead\b`, `\bactually[,]?\s`, `\bi said\b`, `\bi meant\b`, `\bnope\b`, `\bundo\b`, `\brevert\b`, `\btry again\b`, `\bincorrect\b`
- `redirect`: `^stop\b`, `^wait\b`, `\bhold on\b`, `^let\'s\b`, `\bforget\b`, `\bskip\b`, `\bignore\b`, `\bnever\s?mind\b`, `\bnvm\b`
- `directive`: starts with imperative verb — `^(make|create|add|remove|delete|write|implement|build|run|fix|update|change|refactor|rename|move|test|check|verify|show|explain|list)\b`
- `approval`: `^(good|great|perfect|excellent|nice|yes|yep|yeah|ok|okay|sure|thanks|thank you)\b`, `\blooks good\b`, `\blgtm\b`, `\bwell done\b`
- `question`: trailing `\?`, or `^(what|how|why|when|where|which|who|can you|could you|would you|should)\b`

**Findings:**
- `total_user_messages`: int
- `messages_classified`: int
- `skipped_non_english_messages`: int
- `boilerplate_messages`: int
- `corrections`: int (messages matching correction)
- `redirects`: int
- `directives`: int
- `approvals`: int
- `questions`: int
- `escalations_found`: int
- `peak_frustration_session_id`: string — id of the session with the highest single-message frustration (empty string if none)

**Tables:**
- `"Category Counts"` — columns `[category, count, pct_of_classified]`, rows: one per category including an `unclassified` row
- `"Frustration Distribution"` — columns `[intensity, count]`, rows 0..5
- `"Escalation Sequences"` — columns `[session_id, start_index, length, peak_intensity]`, rows: up to 20 highest-peak escalations (no message text!)

**Minimum sessions:** 1 (no floor — if there are zero classified messages, emit "insufficient" summary)
**Summary must contain:** `"user signal analysis"`
**Dependencies:** stdlib only (re, json, sys, collections)

### 3.2 cross-project-graph (`cross_project_graph.py`)

**Reference:** `scripts/007-cross-project-graph.py`

**Algorithm:**
1. Extract source project per session from `session.metadata.project`. Skip sessions with empty project name.
2. Build the set of known projects as the union of all source project names across the input session array.
3. For each session, for each message with `role == "User"` or `"Assistant"`, scan `text` for mentions of OTHER project names (exact case-insensitive substring match, whole-word bounded with `\b` via regex). A mention of `P` in a session belonging to `Q` contributes a directed edge `Q → P` with weight +1.
4. Reference-type classification per mention using ±100 chars of context around the match:
   - `implementation`: `look at how`, `same pattern`, `like .* does`, `based on`
   - `context_import`: any of `CLAUDE.md`, `README`, `config`, `.claude/`
   - `knowledge_sharing`: `learned from`, `solution in`, `already solved`
   - `cross_project_action`: `push`, `commit`, `deploy`, `pr`, `merge`
   - fallback: `other`
5. Accumulate `edge_weights[(src, dst)]` and `edge_types[(src, dst)][type]`.
6. Build `networkx.DiGraph` from edge weights. Compute:
   - `out_degree`, `in_degree`, `out_weight`, `in_weight` per node
   - `hubs`: top 10 nodes by `out_weight`
   - `authorities`: top 10 nodes by `in_weight`
   - weakly connected components; retain components with >1 node as clusters
   - mutual pairs: edges `(a,b)` where `(b,a)` also exists
7. Minimum projects: at least 2 distinct projects with at least 1 edge between them. Below that, emit "insufficient" summary.

**Findings:**
- `total_sessions`: int
- `total_projects`: int
- `total_edges`: int
- `total_references`: int (sum of edge weights)
- `mutual_pair_count`: int
- `cluster_count`: int
- `largest_hub`: string — node name with highest out_weight (empty string if none)
- `largest_authority`: string — node name with highest in_weight (empty string if none)

**Tables:**
- `"Edges"` — columns `[source, target, weight, dominant_type]`, rows: all edges sorted by weight descending
- `"Nodes"` — columns `[project, out_degree, in_degree, out_weight, in_weight]`, rows: all projects
- `"Clusters"` — columns `[cluster_id, size, members]`, rows: one per cluster. `members` is a comma-joined project list (this is the ONE allowed non-atomic cell, because a fixed-column schema can't represent variable-size sets cleanly — it is tool-name symbols only, no user text).

**Minimum sessions:** 2 (also requires ≥2 distinct projects and ≥1 edge)
**Summary must contain:** `"cross-project graph"`
**Dependencies:** `networkx`

**NL scope:** Reference-type classification uses English context phrases. Project name matching is language-agnostic. If the reference classifier can't identify a type, fall back to `other` — this is safe for non-English contexts because it doesn't drop the edge, just loses type detail.

### 3.3 change-point-detection (`change_point_detection.py`)

**Reference:** `scripts/018_change_point_detection.py`

**Algorithm:**
1. For each session with ≥30 messages, build per-user-message time series (one value per User message, ordered by array index):
   - `user_msg_length`: `len(message.text)` (after stripping boilerplate as in 3.1)
   - `tool_call_rate`: count of `tool_calls` on the preceding Assistant message (0 if none)
   - `correction_flag`: 1 if the message's `classification` is `HumanCorrection`, else 0
   - `tool_diversity`: number of distinct tool names in the preceding Assistant message (0 if none)
2. For each of the 4 signals:
   a. Drop sessions where the signal has <10 non-zero values (insufficient dynamic range).
   b. Normalize: `(signal - mean) / std`; if `std < 1e-10`, skip that signal for that session.
   c. If length > 500, subsample by `factor = ceil(len / 500)` and record factor for index mapping.
   d. Apply `ruptures.Pelt(model="rbf", min_size=8).fit(normalized).predict(pen=1.5 * log(len))`.
   e. If PELT raises, fall back to `ruptures.Binseg(model="rbf")` with same penalty.
   f. Strip the trailing endpoint (PELT always returns `n` as the last index).
   g. Map indices back to original scale if subsampled.
   h. Classify each regime between consecutive change points by slope sign (`ascending`, `descending`, `flat`).
3. Aggregate: number of change points per signal per session; distribution of regime classifications.

**Findings:**
- `sessions_analyzed`: int
- `total_change_points`: int (across all sessions, all signals)
- `change_points_user_msg_length`: int
- `change_points_tool_call_rate`: int
- `change_points_correction_flag`: int
- `change_points_tool_diversity`: int
- `mean_change_points_per_session`: float
- `most_volatile_session_id`: string (session with most change points across all 4 signals)

**Tables:**
- `"Change Points"` — columns `[session_id, signal, index, regime_before, regime_after]`, rows: all detected change points (cap at 500 rows, sorted by session then signal then index)
- `"Regimes"` — columns `[session_id, signal, regime_num, start_index, end_index, mean_value, classification]`, rows: all regimes (cap at 1000 rows)
- `"Signal Summary"` — columns `[signal, sessions_with_cp, total_cps, mean_cps_per_session]`, rows: one per signal

**Minimum sessions:** 3 sessions with ≥30 messages each (sessions are filtered by message count before the minimum is checked)
**Summary must contain:** `"change point"` (and either `"PELT"` or `"ruptures"`)
**Dependencies:** `numpy`, `ruptures`

### 3.4 corpus-timeline (`corpus_timeline.py`)

**Reference:** `scripts/cross_project_timeline.py`

**Note:** This technique is **provisional** — it is a stop-gap so that reports are reproducible without the source corpus. Once the storage/view reshape lands (`todos/output-contract.md`), `corpus-timeline` will be deleted in favour of a view spec over the canonical `sessions.parquet`. Add a header comment in the script noting this.

**Algorithm:**
1. For each session, extract `date = first non-null message timestamp parsed as ISO 8601, truncated to YYYY-MM-DD`. If no timestamps, skip (count as `undated_sessions`).
2. Extract `project = session.metadata.project` (empty string → `"(unknown)"`).
3. Count `(date, project) → session_count`.
4. Compute daily totals: `sessions_per_day[date]` and `distinct_projects_per_day[date]`.
5. Flag high-concurrency days as `distinct_projects >= 3`.
6. Compute project totals: `sessions_per_project[project]`.

**Findings:**
- `total_sessions`: int
- `undated_sessions`: int
- `total_dates`: int
- `total_projects`: int
- `date_range_min`: string (YYYY-MM-DD, empty if no dated sessions)
- `date_range_max`: string (YYYY-MM-DD, empty if no dated sessions)
- `high_concurrency_day_count`: int
- `peak_day`: string (YYYY-MM-DD with the highest session_count, empty if none)

**Tables:**
- `"Daily Activity"` — columns `[date, project, session_count]`, rows: one per (date, project) pair, sorted by date then project
- `"Daily Totals"` — columns `[date, session_count, distinct_projects]`, rows: one per date
- `"Project Totals"` — columns `[project, session_count, first_seen, last_seen]`, rows: one per project sorted by session_count descending

**Minimum sessions:** 1 (no floor — empty corpus emits "insufficient" summary)
**Summary must contain:** `"corpus timeline"`
**Dependencies:** stdlib only (datetime, json, sys, collections)

## 4. Red team notes

- Feature file: `middens/tests/features/techniques/python_batch4.feature`
- Tag: `@python`
- Use existing step definitions from `tests/steps/python_batch1.rs` — DO NOT create new step definitions. If a scenario needs a step that doesn't exist, flag it as a contract gap.
- Fixture sessions come from `a set of {int} sessions, each with {int}-{int} turns, including thinking and tool use` or `a set of {int} sessions across {int} projects, each with {int}-{int} turns, including thinking and tool use`.
- Each technique needs at minimum 2 scenarios: success + insufficient-data.
- Assert technique name, summary substring, all documented findings, all documented table names, and `no table cell contains raw user or assistant text`.

## 5. Green team notes

- Write one `.py` per technique under `middens/python/techniques/`. Filenames: `user_signal_analysis.py`, `cross_project_graph.py`, `change_point_detection.py`, `corpus_timeline.py`.
- Do NOT read the feature file. Do NOT read other techniques' test files. Implement from this spec only.
- Use the existing Batch 3 scripts as contract reference (e.g. `convention_epidemiology.py` for the output shape + sanitization helper).
- NaN/Infinity sanitization is mandatory — `json.dumps` will raise otherwise.

## 6. Definition of Done

- [ ] 4 Python scripts land under `middens/python/techniques/`
- [ ] `python/requirements.txt` updated with `ruptures` and `networkx`
- [ ] Both embedded asset lists (`TECHNIQUE_SCRIPTS` in `embedded.rs`, `PYTHON_TECHNIQUE_MANIFEST` in `techniques/mod.rs`) updated and in sync
- [ ] `python_batch4.feature` exists with success + insufficient-data scenarios per technique, covering every documented finding and table
- [ ] `list-techniques` shows 23 total (currently 19) — cucumber row count assertion updated 19 → 23
- [ ] `user-signal-analysis` emits `skipped_non_english_messages` finding and never scores non-English content
- [ ] `change-point-detection` falls back to Binseg if PELT raises; neither path can exit non-zero on valid input
- [ ] `cross-project-graph` skips sessions with empty project name and emits `"insufficient"` summary on <2 projects
- [ ] `corpus-timeline` has a header comment linking to `todos/output-contract.md` marking it for post-reshape deletion
- [ ] All 261+ existing cucumber scenarios still pass
- [ ] New scenarios in `python_batch4.feature` all pass
- [ ] Clean-cache reinstall test: `rm -rf $XDG_CONFIG_HOME/middens/python $XDG_CONFIG_HOME/middens/python-assets`, then `./target/debug/middens list-techniques` and an `analyze` run — verify uv reinstalls ruptures + networkx without error
- [ ] New techniques NOT marked essential
