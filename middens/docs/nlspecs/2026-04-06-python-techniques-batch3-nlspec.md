# NLSpec: Python Techniques — Batch 3

**Status:** Draft
**Batch:** Lag-Sequential Analysis, SPC Control Charts, NCD Clustering, ENA, Convention Epidemiology

## Why

Batches 1 (HSMM, foraging, Granger, survival) and 2 (process mining, PrefixSpan, Smith-Waterman, T-pattern) are merged. Batch 3 covers the remaining five analytical techniques from the research battery, closing out the Python bridge port (13/13).

Batch 3 techniques cover:
- **Lag-Sequential Analysis** — transitional dependencies at multiple lags (sequential association beyond adjacency)
- **SPC Control Charts** — process stability / out-of-control signals on session-level metrics
- **NCD Clustering** — compression-distance-based unsupervised session taxonomy
- **ENA (Epistemic Network Analysis)** — co-occurrence networks of epistemic codes within sliding windows
- **Convention Epidemiology** — SIR/logistic modelling of behavior-pattern adoption across sessions over time

## What

Five Python technique scripts in `middens/python/techniques/` following the same bridge contract as Batches 1 and 2. All produce `TechniqueResult` JSON on stdout. No figures (tables only).

## How

### Shared Contract

Same as Batches 1 and 2 — see `2026-04-05-python-techniques-batch1-nlspec.md` for the full Session JSON and TechniqueResult JSON schemas. Key reminders:
- Input: JSON file path as `argv[1]` containing `Session[]`
- Output: `TechniqueResult` JSON to stdout (`name`, `summary`, `findings`, `tables`, `figures: []`)
- `tool_calls[].input` is a dict (not string) — extract `path` key for file paths
- Roles are `User`/`Assistant` (PascalCase), classifications like `HumanCorrection`, `HumanDirective`, `HumanApproval`, `HumanQuestion`, `Unclassified`
- Tables `rows` must be `List[List[Value]]` not `List[Dict]`
- Sanitize NaN/Infinity before `json.dumps` (replace with `None`)
- Stderr diagnostics on unrecoverable error, exit 1
- Empty/insufficient sessions: return valid TechniqueResult with explanatory summary, NOT error exit
- No filesystem writes — no plotting, no `plt.savefig`. All visualization data must be encoded as tables.

### 1. Lag-Sequential Analysis (`lag_sequential.py`)

**Reference:** `scripts/015_lag_sequential_analysis.py`

**Algorithm:**
1. Code each session into a sequence of event symbols. Event codes:
   - `UR` — user request (HumanDirective or Unclassified user)
   - `UC` — user correction (HumanCorrection)
   - `UA` — user approval (HumanApproval)
   - `UQ` — user question (HumanQuestion)
   - `AR` — assistant read (tool in Read/Glob/Grep)
   - `AE` — assistant edit (Edit/Write/NotebookEdit)
   - `AB` — assistant bash/shell (Bash)
   - `AS` — assistant skill (Skill)
   - `AT` — assistant text-only (no tool calls)
   - `AK` — assistant with thinking block (mutually exclusive with `AT`; if thinking present, code as `AK`)
   - `AF` — assistant tool failure (tool_results with any `is_error: true`)
2. Skip sessions with fewer than 20 events.
3. For each lag L in {1, 2, 3}:
   - Build an N×N frequency matrix M[i][j] = count of (event_i followed by event_j at lag L) across all sessions.
   - Compute row/column marginals, expected counts under independence (E[i][j] = row_i_total * col_j_total / grand_total).
   - Compute adjusted residuals z[i][j] = (O − E) / sqrt(E * (1 − row_i_total/grand_total) * (1 − col_j_total/grand_total)).
   - A cell is "significant" if |z| ≥ 2.58 (p ≈ 0.01 two-sided).
4. Across lags, collect the top 20 most positive z-scores (strongest forward associations) and top 10 most negative (strongest avoidances).

**Findings:**
- `total_events`: int — total coded events across all sessions
- `sessions_analyzed`: int
- `significant_transitions_lag1`: int
- `significant_transitions_lag2`: int
- `significant_transitions_lag3`: int
- `top_positive_transition`: string — e.g., `"AK→AE (lag=1, z=12.3)"`
- `top_negative_transition`: string — e.g., `"UC→AT (lag=1, z=-8.1)"`

**Tables:**
- "Top Positive Transitions" — from, to, lag, observed, expected, z_score (top 20)
- "Top Negative Transitions" — from, to, lag, observed, expected, z_score (top 10)
- "Event Frequencies" — event, count, proportion

**Minimum sessions:** 3
**Dependencies:** None (Python standard library only)

### 2. SPC Control Charts (`spc_control_charts.py`)

**Reference:** `scripts/021_spc_control_charts.py`

**Algorithm:**
1. For each session (min 20 events), compute three session-level metrics:
   - `correction_rate` — fraction of user messages classified HumanCorrection
   - `tool_error_rate` — fraction of tool_results with `is_error: true`
   - `mean_assistant_text_len` — mean character length of assistant text messages
2. Order sessions by timestamp of first message (sessions without timestamps go last, stable order).
3. For each metric series, compute Individuals (I) and Moving Range (MR) control limits:
   - Center line = mean
   - MR_bar = mean of |x_i − x_{i−1}|
   - UCL_I = mean + 2.66 * MR_bar; LCL_I = max(0, mean − 2.66 * MR_bar)
   - UCL_MR = 3.267 * MR_bar; LCL_MR = 0
4. Identify out-of-control points: any value outside I control limits. Note that the 2.66·MR_bar band is the 3σ-equivalent Individuals limit, so points beyond UCL_I / LCL_I ARE the Western Electric Rule 1 (single point beyond 3σ) signals — they are counted under `*_ooc_count` rather than as a separate rule.
5. Apply Western Electric **Rule 2** (2 of 3 consecutive points beyond 2σ on the same side). Compute `UCL_2sigma = mean + 2 * sigma_est`, `LCL_2sigma = mean - 2 * sigma_est`, slide a 3-wide window over `correction_rate`, and report violations. Rule 2 is reported separately as `rule2_violations`. Higher Western Electric rules (3, 4, …) are out of scope for this technique.
6. Compute a one-sided CUSUM on `correction_rate` with target = overall mean, k = 0.5 * sigma, h = 4 * sigma (sigma estimated as MR_bar / 1.128). Report index of first CUSUM alarm if any.

**Findings:**
- `sessions_analyzed`: int
- `correction_rate_mean`: float
- `correction_rate_ucl`: float
- `correction_rate_ooc_count`: int — out-of-control session count
- `tool_error_rate_ooc_count`: int
- `assistant_len_ooc_count`: int
- `cusum_first_alarm_index`: int | None
- `rule2_violations`: int — Western Electric rule 2 count on correction_rate

**Tables:**
- "Control Limits" — metric, mean, ucl, lcl, mr_bar
- "Out-of-Control Sessions" — session_id, metric, value, limit_violated (top 20)
- "Rule Violations" — rule, metric, session_index

**Minimum sessions:** 10
**Dependencies:** `numpy`

### 3. NCD Clustering (`ncd_clustering.py`)

**Reference:** `scripts/011_ncd_session_clustering.py`

**Algorithm:**
1. For each session, build a symbol stream. Symbol alphabet: `R`(Read), `G`(Glob/Grep), `E`(Edit), `W`(Write), `B`(Bash), `S`(Skill), `X`(other tool), `A`(assistant text-only — no tool calls AND no thinking), `T`(assistant thinking present), `u`(user message short, <200 chars), `U`(user message long, ≥200 chars), `C`(user correction — appended after `u`/`U` when the message is HumanCorrection), `F`(tool failure — appended when any tool_result has is_error=true). Join without separators.
2. Skip sessions whose stream length < 8.
3. Sample at most 50 sessions (random, seeded with `random.seed(42)`) for the NCD matrix to cap O(n²) cost.
4. Compute NCD(x, y) = (|C(xy)| − min(|C(x)|, |C(y)|)) / max(|C(x)|, |C(y)|) using `zlib.compress(level=9)` on UTF-8 bytes. Build symmetric NxN matrix.
5. Hierarchical clustering via `scipy.cluster.hierarchy.linkage` with `method='average'`. Choose `k` in {3..8} maximizing silhouette on the NCD matrix.
6. For each cluster, report: size, most common tool symbol, mean stream length, mean correction rate across member sessions, and a short "representative" symbol stream (shortest member within 20 chars of cluster median length).

**Findings:**
- `sessions_in_sample`: int
- `sessions_skipped`: int — below minimum length
- `optimal_k`: int
- `silhouette_score`: float
- `largest_cluster_size`: int
- `largest_cluster_label`: string — deterministic mapping from the cluster's most common symbol: `R`/`G` → `"read-heavy"`, `E`/`W` → `"edit-heavy"`, `B` → `"bash-heavy"`, `S` → `"skill-heavy"`, `X` → `"other-tool-heavy"`, `A` → `"text-heavy"`, `T` → `"thinking-heavy"`, `u`/`U` → `"dialogue-heavy"`, `C` → `"correction-heavy"`, `F` → `"failure-heavy"`. Unknown symbols fall back to `"{symbol}-heavy"`.

**Tables:**
- "Cluster Summary" — cluster_id, size, dominant_symbol, mean_length, mean_correction_rate, representative
- "NCD Matrix Preview" — first 10 × 10 rounded to 3 decimals (columns: session_id + 10 values)

**Minimum sessions:** 5
**Dependencies:** `scipy`, `numpy` (already installed); `zlib` (stdlib)

### 4. ENA (`ena_analysis.py`)

**Reference:** `scripts/ena_analysis.py`

**Algorithm:**
1. Define epistemic codes (keyword-based, case-insensitive, word-boundary, checked on both user text and assistant text/thinking):
   - `PROBLEM_FRAMING` — problem, issue, error, bug, fail, broken, unexpected
   - `HYPOTHESIS` — maybe, perhaps, might, could be, suspect, likely, I think, I believe
   - `EVIDENCE_SEEK` — read, check, look, inspect, verify, confirm, examine
   - `TOOL_USE` — any message with ≥1 tool_call
   - `SELF_CORRECT` — wait, actually, sorry, mistake, revert, undo, let me
   - `PLAN` — plan, step, first, next, then, finally, approach, strategy
   - `RESULT_INTERP` — found, shows, indicates, means, suggests, confirms, because
2. For each session, code each turn with the set of codes that fire. A turn is one message.
3. Build a co-occurrence matrix per session using a sliding stanza window of size 5: for every pair of codes that appear in the same 5-turn window, increment C[i][j]. Normalize by session turn count.
4. Split sessions into low-correction (≤10%) and high-correction (>25%) groups; skip if either group is empty.
5. Compute mean co-occurrence matrices per group; subtract to get a difference matrix.
6. Compute code centrality (row sum / total) for the overall matrix.
7. Find top 10 differentiating edges by |difference|.

**Findings:**
- `sessions_analyzed`: int
- `top_code`: string — highest centrality code overall
- `top_code_centrality`: float
- `strongest_low_correction_edge`: string — e.g., `"EVIDENCE_SEEK↔PLAN"`
- `strongest_high_correction_edge`: string — e.g., `"SELF_CORRECT↔PROBLEM_FRAMING"`

**Tables:**
- "Code Centrality" — code, centrality, frequency
- "Discriminative Edges" — code_a, code_b, low_correction_weight, high_correction_weight, difference

**Minimum sessions:** 5
**Dependencies:** `numpy`

### 5. Convention Epidemiology (`convention_epidemiology.py`)

**Reference:** `scripts/019_convention_epidemiology.py`

**Note on adaptation:** The reference script runs on hardcoded convention-adoption timelines from prior research on how coding conventions propagate across repos. For the bridge we generalize it to two questions over `Session[]`:
1. **Within-workflow propagation over time** — do certain tool-use patterns spread through a user's sessions like an epidemic (cumulative adoption fits logistic/SIR)?
2. **Cross-project propagation and mechanism** — how do those patterns move between projects? Does a pattern debut in project A and then surface in B and C, and with what latency and shape (radial-from-source, diffuse, sequential chain)?

Both questions operate on tool-call *bigrams* as convention candidates. Project identity is derived from session metadata (see below).

**Algorithm:**

**Phase 0 — prepare inputs:**
1. Require all sessions to have a first-message timestamp; skip sessions without one.
2. Derive `project_id` per session from `environment.cwd` if present (fallback to `metadata.cwd`). Normalize: strip leading home-dir prefix, take the two trailing path components (e.g., `/Users/x/code/foo-api/src` → `code/foo-api`), and group sessions with equal normalized paths as the same project. Sessions without a cwd get `project_id = "_unknown"` and are excluded from cross-project analysis but kept for the within-workflow analysis.
3. Sort sessions globally by first-message timestamp. Also group sessions per `project_id` sorted by timestamp.

**Phase 1 — candidate conventions:**
4. For each session, collect the set of tool-call bigrams (pairs of consecutive tool calls within the same assistant turn and across adjacent assistant turns). A bigram is a candidate if it appears in **≥10% of sessions AND ≥5 sessions total**. No project-count filter is applied in Phase 1 — cross-project requirements are enforced strictly in Phase 3. Phase 2 (within-workflow fits) accepts all candidates passing the session-count thresholds regardless of how many projects they span. When `projects_detected < 3` Phase 3 is skipped entirely (see "Minimum projects for cross-project analysis" below); when `projects_detected ≥ 3` a candidate that appears in only one project is classified as `confined` in Phase 3 output.

**Phase 2 — within-workflow propagation (existing adapted logic):**
5. For each candidate, build a global cumulative-adoption curve: y[i] = number of distinct sessions with index ≤ i (in global time order) whose session contains the bigram. Series length = number of sessions with timestamps.
6. Fit a three-parameter logistic `y(t) = L / (1 + exp(-k*(t − t0)))` with `scipy.optimize.curve_fit`, bounds `L ∈ [1, N]`, `k ∈ [0, 5]`, `t0 ∈ [0, N]`. Record `L`, `k`, `t0`, `r2 = 1 − SSE/SST`.
7. Attempt an SIR fit using `scipy.integrate.odeint` with population N = total sessions, parameters β, γ ∈ (0, 5]. Compute `R0 = β/γ` and the peak index. Keep whichever of {logistic, SIR} has higher R².
8. Classify temporal trajectory: `early-saturated` (t0 < N/3 and L/N > 0.7), `late-emergent` (t0 > 2N/3), `plateaued` (k < 0.05), `epidemic` (R0 > 1.5 if SIR wins), `other`.

**Phase 3 — cross-project propagation:**
9. For each candidate, find `first_seen[project_id]` — the earliest session timestamp in that project containing the bigram. Drop projects where the candidate is absent.
10. Determine the **origin project** = project with minimum `first_seen` time for this candidate.
11. Compute **propagation latencies** from the origin: for each other adopting project, `latency_days = (first_seen[project] − first_seen[origin]).total_seconds() / 86400`.
12. Compute **project reach** = `number_of_projects_where_candidate_appears / total_number_of_projects_with_any_session` (denominator is all projects, not just adopters). `projects_with_any_session` excludes the `_unknown` bucket.
13. Classify **propagation pattern** (check in this order for mutual exclusivity):
    1. `ubiquitous` — reach > 0.8 (nearly every project)
    2. `confined` — reach ≤ 0.2 (stays in origin + at most one other project)
    3. `radial` — ≥3 projects adopt within a window of 30 days after origin's first_seen (burst spread from a single hub)
    4. `sequential` — ≥3 adopters and latencies (sorted ascending) are non-decreasing with each step ∈ [prev_latency, prev_latency + 60 days] — a chain
    5. `diffuse` — ≥3 adopters but neither radial nor sequential (scattered)
    6. else `confined` (fewer than 3 adopters, reach between 0.2 and 0.8)
14. Compute **inter-project interval stats**: mean/median/std of latencies across adopters.
15. Optional: flag candidates whose *origin project is the most recent* among top adopters — suggests the pattern may have been learned elsewhere and is now bubbling back (indirect evidence of cross-session knowledge transfer).

**Phase 4 — reporting:**
16. Rank candidates by `r2` (within-workflow fit quality) and separately by `reach` (cross-project spread). Report the top 10 of each, plus the union.

**Findings:**
- `sessions_analyzed`: int
- `projects_detected`: int — distinct normalized project_ids with ≥1 session
- `sessions_without_cwd`: int — excluded from cross-project analysis
- `conventions_detected`: int — candidates passing support threshold
- `conventions_fitted`: int — candidates with logistic/SIR R² > 0.7
- `top_convention`: string — highest-R² bigram, e.g., `"Read→Edit"`
- `top_convention_r2`: float
- `top_convention_r0`: float | None — reproduction number if SIR won
- `epidemic_conventions`: int — classified `epidemic` in Phase 2
- `cross_project_conventions`: int — candidates with reach ≥ 0.2
- `ubiquitous_conventions`: int — candidates with reach > 0.8
- `radial_conventions`: int
- `sequential_conventions`: int
- `top_cross_project_convention`: string — highest reach
- `top_cross_project_reach`: float — fraction of projects
- `mean_inter_project_latency_days`: float — averaged across candidates with ≥2 adopters

**Tables:**
- "Within-Workflow Fits" — bigram, n_adopters, best_model, r2, k_or_beta, inflection_or_peak, trajectory_class (top 10 by r2)
- "Cross-Project Propagation" — bigram, origin_project, reach, n_projects_adopted, median_latency_days, propagation_pattern (top 10 by reach)
- "Convention × Project Matrix" — bigram, project_id, first_seen_timestamp, latency_days_from_origin (long format; include only top 10 bigrams by reach × their adopting projects, capped at 100 rows)

**Minimum sessions:** 15 (needs temporal depth for curve fitting)
**Minimum projects for cross-project analysis:** 3 (if fewer, Phase 3 is skipped and its findings/tables report "insufficient projects" — Phase 2 still runs)
**Dependencies:** `scipy` (already installed), `numpy`

### Requirements

No new pinned dependencies needed — `scipy`, `numpy`, `zlib` (stdlib) are sufficient. Add to `middens/python/requirements.txt` only if scipy/numpy are not already present:

```
# Already present from Batch 1:
# scipy>=1.11,<2.0
# numpy>=1.24,<2.0
```

### Registration

Each technique is wired in `middens/src/pipeline.rs` (or the technique registry module) via `PythonTechnique::new("lag-sequential", "python/techniques/lag_sequential.py", ...)`. Minimum-session guards are enforced by the script itself; the Rust side just passes sessions through.

## Done (Definition of Done)

- [ ] `lag_sequential.py` codes events, builds lag-{1,2,3} transition matrices, flags significant cells (|z|≥2.58)
- [ ] `lag_sequential.py` reports top positive and top negative transitions across lags
- [ ] `spc_control_charts.py` computes I/MR limits for correction_rate, tool_error_rate, assistant_text_len
- [ ] `spc_control_charts.py` reports out-of-control session counts and Western Electric rule-2 violations
- [ ] `spc_control_charts.py` computes CUSUM on correction_rate and reports first alarm index
- [ ] `ncd_clustering.py` compresses session symbol streams with zlib and builds an NCD matrix (sample ≤50)
- [ ] `ncd_clustering.py` clusters via scipy average linkage and selects k by silhouette
- [ ] `ncd_clustering.py` reports cluster sizes, dominant symbols, representative streams
- [ ] `ena_analysis.py` codes turns with keyword-based epistemic codes
- [ ] `ena_analysis.py` builds stanza-5 co-occurrence networks and reports centrality + discriminative edges
- [ ] `convention_epidemiology.py` extracts tool bigrams as convention candidates with ≥10% session support AND ≥5 sessions total (no project-count filter in Phase 1; the cross-project requirement is enforced only in Phase 3)
- [ ] `convention_epidemiology.py` derives project_id from cwd and groups sessions per project
- [ ] `convention_epidemiology.py` fits logistic and SIR curves to global cumulative adoption and classifies temporal trajectory
- [ ] `convention_epidemiology.py` computes per-project first_seen, origin project, propagation latencies, and project reach
- [ ] `convention_epidemiology.py` classifies propagation pattern (confined/radial/sequential/diffuse/ubiquitous)
- [ ] `convention_epidemiology.py` reports top conventions by R² (within-workflow) and by reach (cross-project)
- [ ] `convention_epidemiology.py` skips Phase 3 gracefully if fewer than 3 projects detected
- [ ] All 5 scripts accept `argv[1]` session JSON path, print valid TechniqueResult JSON to stdout
- [ ] All 5 scripts handle empty/insufficient session arrays gracefully (valid result, not error exit)
- [ ] All 5 scripts sanitize NaN/Infinity before `json.dumps`
- [ ] All 5 scripts print diagnostics to stderr and exit 1 on unrecoverable errors
- [ ] No script performs filesystem writes or plotting
- [ ] `middens/python/requirements.txt` unchanged unless a new dep is genuinely needed
