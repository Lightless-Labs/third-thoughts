# NLSpec: Python Techniques — Batch 2

**Status:** Draft
**Batch:** Process Mining, PrefixSpan, Smith-Waterman, T-pattern Detection

## Why

Batch 1 (HSMM, foraging, Granger, survival) is merged. Batch 2 covers the pattern mining and sequence analysis techniques — techniques that discover structural patterns in agent tool-use sequences.

## What

Four Python technique scripts in `middens/python/techniques/` following the same bridge contract as Batch 1.

## How

### Shared Contract

Same as Batch 1 — see `2026-04-05-python-techniques-batch1-nlspec.md` for the full Session JSON and TechniqueResult JSON schemas. Key points:
- Input: JSON file path as `argv[1]` containing `Session[]`
- Output: `TechniqueResult` JSON to stdout
- Insufficient data: return valid result with summary, NOT error exit
- `tool_calls[].input` is a JSON object (dict), not a string — extract `path` key for file paths
- Classification values: `HumanCorrection`, `HumanDirective`, `HumanApproval`, `HumanQuestion`, `SystemMessage`, `Other`, `Unclassified`

### 1. Process Mining (`process_mining.py`)

**Reference:** `scripts/014_process_mining.py`

**Algorithm:**
1. Convert sessions to event logs. Map each message to an activity:
   - User messages: `user_request` (HumanDirective), `user_correction` (HumanCorrection), `user_approval` (HumanApproval), `user_question` (HumanQuestion)
   - Assistant messages with tool_calls: map tool name to activity (`search_code` for Read/Glob/Grep, `edit_file` for Edit/Write, `run_command` for Bash/Skill, `other_tool` for rest)
   - Assistant messages without tool_calls: `assistant_text`
2. Build a Directly-Follows Graph (DFG): for each consecutive pair of activities in a session, count transitions
3. Compute per-activity statistics: frequency across sessions, mean dwell time (consecutive same-activity count)
4. Identify rework loops: activities that follow themselves (self-loops in DFG)
5. Find correction predecessors: which activities most often precede `user_correction`
6. Compare low-correction (≤10%) vs high-correction (>25%) sessions by DFG edge frequencies

**Findings:**
- `total_events`: int — total events across all sessions
- `unique_activities`: int — distinct activity types observed
- `most_common_activity`: string
- `top_rework_activity`: string — activity with highest self-loop count
- `top_correction_predecessor`: string — activity most often preceding corrections
- `dfg_edges`: int — distinct edges in the DFG

**Tables:**
- "Activity Frequencies" — activity, count, session_coverage (fraction of sessions containing it)
- "Directly-Follows Graph" — from_activity, to_activity, count, frequency
- "Correction Predecessors" — activity, correction_follow_count, proportion

**Minimum sessions:** 3
**Dependencies:** No special libraries needed (pure Python + json + collections)

### 2. PrefixSpan Mining (`prefixspan_mining.py`)

**Reference:** `scripts/prefixspan_mining.py`

**Algorithm:**
1. Encode each session as a sequence of tool-call names (e.g., ["Read", "Read", "Edit", "Bash", "Read", "Edit"]). Only include assistant messages with tool_calls.
2. Run PrefixSpan with minimum support = max(2, 15% of sessions). Find patterns of length 3-6.
3. For each frequent pattern, compute:
   - Support (number of sessions containing it)
   - Support percentage
4. Classify patterns as success-associated or struggle-associated:
   - Split sessions into low-correction (≤10%) and high-correction (>25%)
   - Compute support in each group
   - A pattern is discriminative if support ratio > 2x between groups
5. Report universal patterns (present in both groups) vs group-specific patterns

**Findings:**
- `total_patterns`: int — number of frequent patterns found
- `patterns_length_3`: int — count of length-3 patterns
- `patterns_length_4`: int
- `success_patterns`: int — patterns enriched in low-correction sessions
- `struggle_patterns`: int — patterns enriched in high-correction sessions

**Tables:**
- "Frequent Sequential Patterns" — pattern, length, support, support_pct
- "Discriminative Patterns" — pattern, group (success/struggle), support_ratio

**Minimum sessions:** 5
**Dependencies:** `prefixspan` library

### 3. Smith-Waterman Alignment (`smith_waterman.py`)

**Reference:** `scripts/016_genomics_sequence_analysis.py`

**Algorithm:**
1. Encode each session as a symbol string. Tool calls → single characters: R(Read), G(Glob/Grep), E(Edit), W(Write), B(Bash), S(Skill), X(other). User messages → U. Corrections → C. Thinking → T.
2. Implement Smith-Waterman local alignment with scoring: match=+2, mismatch=-1, gap=-1
3. For each pair of sessions (sample if >50 sessions: random 50), compute the SW alignment score normalized by min sequence length
4. Extract conserved motifs: k-mers (k=3 to 5) that appear in >30% of sessions
5. Test motif enrichment: for each motif, compute frequency in low-correction vs high-correction sessions. Use a simple ratio test (>2x enrichment = significant)
6. Cluster sessions by alignment-score distance matrix using hierarchical clustering (scipy linkage, average method)

**Findings:**
- `mean_alignment_score`: float — mean normalized SW score across all pairs
- `conserved_motifs_count`: int — motifs appearing in >30% of sessions
- `top_success_motif`: string — most enriched motif in low-correction sessions
- `top_struggle_motif`: string — most enriched motif in high-correction sessions
- `cluster_count`: int — number of clusters at distance threshold 0.5

**Tables:**
- "Conserved Motifs" — motif, frequency, session_coverage_pct
- "Motif Enrichment" — motif, low_correction_freq, high_correction_freq, enrichment_ratio, group

**Minimum sessions:** 5
**Dependencies:** `scipy` (already installed from Batch 1), `numpy`

### 4. T-Pattern Detection (`tpattern_detection.py`)

**Reference:** `scripts/tpattern_detection.py`

**Algorithm:**
1. Encode session events with codes: UR (user request), UC (user correction), UA (user approval), AR (agent reads: Read/Glob/Grep), AE (agent edits: Edit/Write), AB (agent bash: Bash), AT (agent text: no tools), AK (agent thinking: has thinking block), AF (agent failure: tool_result with is_error=true)
2. For each event pair (A, B), test whether B follows A within a critical interval more often than chance:
   - Compute observed count of A→B within window of 5 events
   - Compute expected count under permutation (shuffle event codes 100 times, recount)
   - Significance: observed > mean + 2.5 * std of permutation counts (approx p < 0.01)
3. Build hierarchical patterns: if (A,B) is significant and (AB,C) is also significant, report (A,B,C) as a level-2 pattern
4. Report patterns by level with frequencies

**Findings:**
- `level_1_patterns`: int — number of significant event pairs
- `level_2_patterns`: int — number of significant triples
- `most_common_pattern`: string — most frequent level-1 pattern (e.g., "AR→AE")
- `total_events_analyzed`: int

**Tables:**
- "T-Patterns Level 1" — pattern, observed_count, expected_count, z_score
- "T-Patterns Level 2" — pattern, observed_count, z_score

**Minimum sessions:** 3
**Dependencies:** `numpy`

### Requirements

Add to `middens/python/requirements.txt`:
```
prefixspan>=0.5,<1.0
pm4py>=2.7,<3.0
```

Note: pm4py is optional — process_mining.py should work without it using pure Python DFG construction. Only import pm4py if advanced features are needed.

Actually, process_mining.py should be implemented in pure Python (DFG is just a counter of consecutive pairs). No pm4py dependency needed — keeps the install lighter.

## Done (Definition of Done)

- [ ] `process_mining.py` converts sessions to event logs and builds a DFG
- [ ] `process_mining.py` identifies rework loops and correction predecessors
- [ ] `process_mining.py` compares low vs high correction sessions
- [ ] `prefixspan_mining.py` finds frequent sequential patterns (length 3-6) with PrefixSpan
- [ ] `prefixspan_mining.py` classifies patterns as success-associated or struggle-associated
- [ ] `prefixspan_mining.py` handles sessions with no tool calls gracefully
- [ ] `smith_waterman.py` computes local alignment scores between session pairs
- [ ] `smith_waterman.py` extracts conserved motifs (k-mers in >30% of sessions)
- [ ] `smith_waterman.py` tests motif enrichment between low/high correction groups
- [ ] `tpattern_detection.py` detects significant temporal patterns via permutation testing
- [ ] `tpattern_detection.py` builds hierarchical patterns (level 1 and level 2)
- [ ] All 4 scripts exit 0 on success and print valid TechniqueResult JSON to stdout
- [ ] All 4 scripts handle empty session arrays gracefully
- [ ] All 4 scripts print diagnostics to stderr on unrecoverable errors and exit 1
- [ ] Dependencies added to `middens/python/requirements.txt`
