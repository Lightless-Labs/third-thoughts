# NLSpec: Python Techniques — Batch 1

**Status:** Draft
**Batch:** HSMM, Information Foraging, Granger Causality, Survival Analysis

## Why

The Python bridge (`UvManager` + `PythonTechnique`) is merged but only has the `echo.py` test fixture. The research corpus analysis relies on 13 analytical techniques that use Python libraries (hmmlearn, statsmodels, lifelines, scipy). These need to be ported from the standalone scripts in `scripts/` to the bridge contract.

Batch 1 covers the four highest-value research techniques:
- HSMM (24.6x pre-failure lift — the headline finding)
- Information foraging (MVT violated — agents under-explore)
- Granger causality (thinking → correction causal chains)
- Survival analysis (time-to-correction curves, session degradation)

## What

Four Python technique scripts in `middens/python/techniques/` that:
1. Accept a JSON file path as `argv[1]` containing serialized `Session[]`
2. Perform their specific analysis on the session data
3. Print a single `TechniqueResult` JSON object to stdout
4. Exit 0 on success, 1 on error (with diagnostics to stderr)

Each is registered via `PythonTechnique::new()` in the pipeline.

## How

### Shared Contract

**Input:** JSON file containing an array of sessions. Each session has:
```json
{
  "id": "string",
  "source_tool": "ClaudeCode|CodexCli|GeminiCli|...",
  "session_type": "Interactive|Subagent|Unknown",
  "messages": [
    {
      "role": "User|Assistant|System",
      "timestamp": "ISO8601 or null",
      "text": "message content",
      "thinking": "thinking content or null",
      "tool_calls": [{"id": "...", "name": "Bash|Read|Edit|...", "input": {...}}],
      "tool_results": [{"id": "...", "content": "...", "is_error": false}],
      "classification": "HumanCorrection|HumanDirective|HumanApproval|HumanQuestion|Neutral"
    }
  ],
  "metadata": {"total_messages": N, "total_tool_calls": N, ...},
  "environment": {...}
}
```

**Output:** JSON to stdout matching `TechniqueResult`:
```json
{
  "name": "technique-name",
  "summary": "2-3 sentence summary of findings",
  "findings": [{"label": "metric_key", "value": <number|string>, "description": "..."}],
  "tables": [{"title": "...", "headers": ["col1", ...], "rows": [[val, ...], ...]}],
  "figures": []
}
```

Note: figures are not supported in the bridge (no filesystem access from the subprocess for image output). All visualization data should be in tables instead.

**Error handling:** If a technique receives fewer sessions than its minimum (e.g., HSMM needs ≥10), it should return a valid TechniqueResult with a summary explaining insufficient data and empty findings/tables, NOT exit with an error.

**Dependencies:** Added to `middens/python/requirements.txt` with pinned versions.

### 1. HSMM Behavioral States (`hsmm.py`)

**Reference:** `scripts/hsmm_behavioral_states.py`

**Algorithm:**
1. For each session, extract a feature vector per assistant turn:
   - Tool category one-hot: read (Read/Glob/Grep), edit (Edit/Write), bash (Bash), search (WebSearch/WebFetch), skill (Skill), other
   - Log-scaled message text length
   - Thinking block presence (0/1) and log-scaled thinking length
   - Number of tool calls in the turn
   - Correction lookahead: 1 if the next user message is `HumanCorrection`, else 0
2. Concatenate all session feature sequences with length array for per-session boundaries
3. Fit `GaussianHMM` from hmmlearn with BIC model selection across n_components=[3,4,5,6,7]
4. Decode with Viterbi to get state sequences
5. Compute: state transition matrix, mean state durations, pre-correction state distribution (which states appear in the turn before a correction)
6. Label states heuristically by examining emission means (highest read_proportion → "exploring", highest edit_proportion → "executing", etc.)

**Findings to produce:**
- `optimal_n_states`: int — BIC-selected state count
- `pre_correction_lift`: float — max ratio of pre-correction-state-frequency to base-rate (the "24.6x" finding)
- `dominant_pre_correction_state`: string — label of the state most associated with corrections
- `mean_state_duration_exploring`: float — mean turns in exploring state
- `mean_state_duration_executing`: float — mean turns in executing state

**Tables:**
- "State Transition Matrix" — n×n with state labels
- "State Characteristics" — state label, emission means, mean duration, pre-correction frequency

**Minimum sessions:** 10 (need enough data for HMM fitting)

### 2. Information Foraging (`information_foraging.py`)

**Reference:** `scripts/information_foraging.py`

**Algorithm:**
1. Define a "patch" as a directory path extracted from tool call inputs (Read, Edit, Write, Glob, Grep targets). Group consecutive tool calls to the same directory as one patch visit.
2. Per session, compute:
   - Patches explored (count of distinct directories)
   - Residence time per patch (turns spent before moving to a different directory)
   - Diet breadth (distinct file extensions explored)
   - Foraging efficiency (edit operations / total tool calls)
   - Explore-exploit ratio (read ops / edit ops)
   - Patch revisit rate (revisits / total visits)
3. Test MVT (Marginal Value Theorem): for each patch visit, check if the agent leaves when the gain rate (edits per turn) drops below the session average. Compute MVT compliance rate.
4. Compare metrics between sessions with low correction rates (≤10%) vs high correction rates (>25%).

**Findings:**
- `mean_patches_per_session`: float
- `mean_residence_time`: float — turns per patch
- `mean_foraging_efficiency`: float
- `explore_exploit_ratio`: float
- `mvt_compliance_rate`: float — fraction of patch departures consistent with MVT
- `patch_revisit_rate`: float

**Tables:**
- "Foraging Metrics Summary" — metric, mean, median, std across sessions
- "Success vs Struggle Comparison" — metric, low-correction mean, high-correction mean, difference

**Minimum sessions:** 5

### 3. Granger Causality (`granger_causality.py`)

**Reference:** `scripts/granger_causality.py`

**Algorithm:**
1. Per session (min 25 assistant turns), compute 5 time series aligned to assistant turns:
   - `thinking_ratio`: len(thinking) / len(text) if thinking exists, else 0
   - `tool_diversity`: Shannon entropy of tool names in a 5-turn rolling window
   - `message_length`: log(len(text) + 1)
   - `correction_indicator`: 1 if the preceding user message was `HumanCorrection`, else 0
   - `tool_failure_indicator`: 1 if any tool_result has `is_error=true`, else 0
2. Test all 20 directed pairs (5 choose 2 × 2 directions) at lags 1-5 using `statsmodels.tsa.stattools.grangercausalitytests`
3. Aggregate per-session p-values via Fisher's combined probability test: χ² = -2 Σ ln(p_i), df=2k
4. Apply Bonferroni correction (100 tests = 20 pairs × 5 lags)
5. Report significant causal relationships

**Findings:**
- `significant_pairs`: int — count of significant causal relationships (Bonferroni-corrected)
- `strongest_pair`: string — "X → Y" with lowest p-value
- `strongest_pair_p`: float — Fisher-aggregated p-value
- `thinking_causes_correction`: bool — whether thinking_ratio → correction_indicator is significant
- `sessions_analyzed`: int

**Tables:**
- "Significant Granger-Causal Relationships" — x_series, y_series, best_lag, fisher_p, fraction_significant, direction

**Minimum sessions:** 5 (each with ≥25 assistant turns)

### 4. Survival Analysis (`survival_analysis.py`)

**Reference:** `scripts/survival_analysis.py`

**Algorithm:**
1. Per session, determine:
   - `duration`: total user turns (the "time" axis)
   - `event`: 1 if a `HumanCorrection` occurred, 0 if censored (session ended without correction)
   - `time_to_event`: turn number of first `HumanCorrection` (or total turns if censored)
   - Covariates: first_prompt_length (chars), tool_calls_first_5_turns, has_thinking (bool), session_type
2. Fit Kaplan-Meier estimator for overall survival curve
3. Fit Nelson-Aalen for cumulative hazard (increasing hazard = agent degrades over time)
4. Fit Cox Proportional Hazards with covariates: first_prompt_length, tool_calls_first_5, has_thinking, session_type_interactive
5. Compute median survival time, survival probabilities at key turns (5, 10, 20, 50)

**Findings:**
- `median_survival_turns`: float — turns until 50% of sessions have a correction
- `survival_at_10`: float — P(no correction by turn 10)
- `survival_at_20`: float
- `hazard_trend`: string — "increasing", "decreasing", or "flat"
- `cox_concordance`: float — model concordance index
- `sessions_with_correction`: int
- `sessions_censored`: int

**Tables:**
- "Survival Probabilities" — turn, survival_probability, cumulative_hazard, at_risk
- "Cox PH Covariates" — covariate, hazard_ratio, p_value, ci_lower, ci_upper

**Minimum sessions:** 10

### Requirements

Add to `middens/python/requirements.txt`:
```
hmmlearn>=0.3,<1.0
statsmodels>=0.14,<1.0
lifelines>=0.29,<1.0
scipy>=1.11,<2.0
numpy>=1.24,<3.0
pandas>=2.0,<3.0
```

### Pipeline Registration

Register all 4 techniques in the pipeline (exact registration mechanism depends on current pipeline architecture — check `src/pipeline.rs` and `src/techniques/mod.rs` for how techniques are registered).

## Done (Definition of Done)

- [ ] `hsmm.py` accepts session JSON, fits HSMM, returns TechniqueResult with state analysis findings and tables
- [ ] `hsmm.py` handles <10 sessions gracefully (returns summary explaining insufficient data)
- [ ] `information_foraging.py` extracts patches from tool calls, computes foraging metrics, returns TechniqueResult
- [ ] `information_foraging.py` computes MVT compliance rate
- [ ] `information_foraging.py` compares low-correction vs high-correction sessions
- [ ] `granger_causality.py` computes 5 time series, tests all pairwise Granger causality, returns significant pairs
- [ ] `granger_causality.py` applies Fisher aggregation and Bonferroni correction
- [ ] `granger_causality.py` handles sessions with <25 turns (skips them, reports count)
- [ ] `survival_analysis.py` fits KM, Nelson-Aalen, and Cox PH models
- [ ] `survival_analysis.py` returns median survival, hazard trend, and Cox covariates
- [ ] All 4 scripts exit 0 on success and print valid TechniqueResult JSON to stdout
- [ ] All 4 scripts exit 1 with stderr diagnostics on unrecoverable errors (e.g., missing dependency)
- [ ] All 4 scripts handle empty session arrays (return valid result with "no sessions" summary)
- [ ] Requirements added to `middens/python/requirements.txt`
- [ ] All 4 techniques registered in the pipeline and filtered by `--no-python`

## Integration Smoke Test

```bash
# From middens/
cargo build
# Create minimal test fixture
echo '[{"id":"test1","source_tool":"ClaudeCode","session_type":"Interactive","messages":[{"role":"User","text":"hello","thinking":null,"tool_calls":[],"tool_results":[],"classification":"HumanDirective"},{"role":"Assistant","text":"hi","thinking":"let me think","tool_calls":[{"id":"1","name":"Read","input":{"path":"src/main.rs"}}],"tool_results":[{"id":"1","content":"fn main()","is_error":false}],"classification":"Neutral"}],"metadata":{"total_messages":2,"total_tool_calls":1},"environment":{}}]' > /tmp/test-sessions.json
# Each script should produce valid JSON
uv run python/techniques/hsmm.py /tmp/test-sessions.json
uv run python/techniques/information_foraging.py /tmp/test-sessions.json
uv run python/techniques/granger_causality.py /tmp/test-sessions.json
uv run python/techniques/survival_analysis.py /tmp/test-sessions.json
```
