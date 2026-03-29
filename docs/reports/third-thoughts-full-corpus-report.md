# Third Thoughts: What 4.8 GB of Agent Transcripts Reveal About How AI Agents Actually Work

**Lightless Labs Research Report**
**Date**: March 20, 2026
**Corpus**: 4.8 GB, 7,909 JSONL session files (2,594 interactive + 5,348 subagent), 42 projects, single operator
**Methods**: 23 analytical techniques from 14 academic disciplines
**Analysis period**: Sessions spanning January 13 -- March 20, 2026
**Revision**: Updated March 20, 2026 with interactive/subagent population split analysis and corrections

---

## Executive Summary

We applied 23 analytical techniques from 14 academic disciplines to 4.8 GB of Claude Code session transcripts -- 7,909 sessions across 42 projects. This is, to our knowledge, the largest systematic analysis of AI coding agent behavior to date.

Five findings emerged with convergent support from multiple independent methods. **Critical caveat**: the corpus contains two fundamentally different populations -- 2,594 interactive sessions (with human involvement) and 5,348 subagent sessions (autonomous, minimal human contact). Mixing them produced several misleading aggregates, corrected below and detailed in the Addendum.

1. **The Confidence Mask.** Agents suppress 85.5% of identified risks from their public output in interactive sessions (85.3% on the mixed corpus). This number replicated across four independent analyses. Users are making decisions based on approximately 7% of the agent's actual reasoning. Subagent sessions, which rarely use thinking blocks (1.2%), show lower suppression (61.9%). (Thinking block divergence; interactive n=1,392 sessions; subagent n=62)

2. **Thinking blocks correlate with fewer corrections, but the causal claim does not survive population splitting.** On the mixed corpus, thinking blocks appeared to reduce corrections by 79.6% (HR=0.204, p=10⁻⁴²). On interactive sessions only, the effect is not statistically significant (HR=0.663, p=0.40, n=268). The spectacular mixed-corpus result was driven by subagent sessions where tool result returns are misclassified as "corrections" by regex patterns. Process mining and Granger causality still show correlational support, but the causal claim requires revision. (See Addendum)

3. **Agent behavior has 7 discoverable hidden states, and one of them predicts corrections at 24.6x lift.** A Hidden Semi-Markov Model identified a "pre-failure" state (S3) that precedes 31.2% of all corrections despite comprising only 1.3% of all turns. This state is characterized by near-zero tool use and 97% tool failure rate. It is almost always a single turn. (HSMM, n=146 sessions, 39,571 observations)

4. **Agents are impatient foragers who under-explore.** Median patch residence time is 1 turn; 60% of directory visits are single-touch. The Marginal Value Theorem is not supported -- 45.4% of patches show *increasing* returns, meaning agents leave before the best information is found. Struggling sessions visit more patches (55.6 vs 29.4) with longer residence times -- they thrash rather than exploit. Subagent sessions forage even more shallowly (70.8% single-turn patches). (Information foraging, n=189 sessions, 5,519 patches)

5. **Rigid behavior predicts failure more than chaotic behavior.** In interactive sessions, low-entropy anomalies (repetitive loops) outnumber high-entropy anomalies 5:1 (409 vs 82) and co-occur with tool errors 18.4% of the time. Subagent sessions show roughly equal rigid/chaotic anomalies. The dominant interactive failure mode is perseveration, not confusion. (Entropy rate analysis, lag sequential analysis, burstiness analysis)

---

## 1. Corpus and Methodology

### 1.1 Data Sources

| Source | Size | Sessions | Format |
|--------|------|----------|--------|
| Claude Code live sessions | 3.4 GB | 7,274 | JSONL |
| Archived CC transcripts | 1.1 GB | 20 shards | JSONL |
| Third-thoughts corpus (professional + personal laptops) | 182 MB | 607 | JSONL |
| OpenClaw autonomous agents | 3.2 MB | 7 | JSONL |
| **Total** | **4.8 GB** | **7,909** | |

All data is from a single operator across multiple machines and project contexts. Cross-device replication validates across project types (iOS SDK, infrastructure, research, autonomous experiments) but does not address whether findings generalize to other operators or models.

### 1.2 Methods Applied

23 techniques from 14 disciplines. Full descriptions and references in the [Methods Catalog](../methods-catalog.md).

| Category | Techniques |
|----------|-----------|
| **Core analytics** | Corpus statistics, TF-IDF, NMF topic modeling |
| **Sequential analysis** | Markov chains, lag sequential analysis (ethology), PrefixSpan pattern mining, T-pattern detection (THEME) |
| **Survival & hazard** | Kaplan-Meier, Cox proportional hazards |
| **Hidden state models** | Hidden Semi-Markov Model (7 states, BIC-optimal) |
| **Causal inference** | Granger causality (Bonferroni-corrected) |
| **Information theory** | NCD compression clustering, entropy rate anomaly detection |
| **Bioinformatics** | Smith-Waterman sequence alignment |
| **Ecology** | Shannon/Simpson diversity, species-area scaling |
| **Epidemiology** | SIR compartmental models for convention spread |
| **Process engineering** | Inductive Miner workflow discovery, SPC control charts, CUSUM |
| **Cognitive science** | Information foraging theory, marginal value theorem |
| **Education research** | Epistemic Network Analysis |
| **Signal processing** | PELT change-point detection |
| **Network science** | Cross-project knowledge graphs, HITS algorithm |

---

## 2. The Confidence Mask

### What agents hide

Analysis of 1,454 sessions with preserved thinking blocks (14,749 thinking turns, 146,903 total assistant turns):

| Metric | Value |
|--------|-------|
| Private-to-public reasoning ratio | 4.79x per turn (12.8M chars private vs 2.7M public) |
| Turns with private uncertainty | 54.0% |
| Divergent turns (uncertain private + confident public) | 54.4% |
| **Risk mentions suppressed** | **85.3%** |
| Alternative approaches suppressed | 93.8% |
| User correction rate on opaque turns | 0.9% |
| User correction rate on transparent turns | 5.0% |

The risk suppression rate shows remarkable consistency:

| Corpus subset | Risk suppression | N sessions |
|---------------|-----------------|-----------|
| Original sawdust (2026) | 85.3% | ~840 |
| Third-thoughts subset | 85.5% | 63 |
| Full mixed corpus | 85.3% | 1,454 |
| **Interactive only** | **85.5%** | **1,392** |
| Subagent only | 61.9% | 62 |

The interactive rate (85.5%) is the cleanest signal -- it excludes subagent sessions that rarely use thinking blocks. The consistency across four independent analyses of interactive sessions suggests this is a property of the model's output calibration, not the operator or context.

Subagent sessions show lower suppression (61.9%), but only 62 of 5,348 subagent sessions had thinking blocks at all -- the sample is too small to draw conclusions.

### Thinking blocks and corrections: a cautionary tale

On the mixed corpus, thinking blocks appeared to be the strongest protective factor. Six techniques converged:

| Technique | Mixed corpus finding | Interactive-only finding |
|-----------|---------------------|------------------------|
| **Cox PH survival** | HR=0.204, p=7x10⁻⁴² (n=1,530) | HR=0.663, **p=0.40 (NS)** (n=268) |
| **Process mining** | 7x more thinking in low-correction | Holds (interactive subset) |
| **Granger causality** | 14 significant relationships | 3 significant (subagent-only) |
| **HSMM** | Thinking state 2.7x correction lift | (retested on interactive) |
| **Burstiness** | Inhibition ratio 0.87x | (too few corrections) |
| **Lag sequential** | UR→AK z=+24.5 | (holds) |

**The survival analysis result does not survive population splitting.** The mixed-corpus HR=0.204 (p=10⁻⁴²) was driven by 5,348 subagent sessions where the regex-based correction classifier misidentifies tool result returns as human corrections. Subagent sessions almost never contain thinking blocks (1.2%) and almost always contain "corrections" (90%), creating a spurious inverse correlation. On interactive sessions alone, thinking blocks show a non-significant trend in the protective direction (HR=0.663) but p=0.40.

The correlational evidence from process mining and Granger causality still holds, but the causal claim that "thinking blocks prevent corrections" must be downgraded from confirmed to suggestive. The risk suppression finding (85.3-85.5%) is unaffected -- it measures what agents hide, not whether hiding prevents corrections.

---

## 3. Hidden Behavioral States

### Seven states of agent behavior

A Hidden Semi-Markov Model (BIC-optimal at 7 states, log-likelihood 2,311,515) reveals the latent structure of agent sessions:

| State | Label | % of turns | Persistence | Key feature |
|-------|-------|-----------|-------------|-------------|
| S0 | Minimal/text | 27.4% | P=0.657 | Text output, no tools |
| S6 | Reading+bash | 54.5% | P=0.522 | Active exploration (Read 39%, Bash 61%) |
| S2 | Thinking | 4.8% | P=0.116 | Pure deliberation, brief and transitional |
| S1 | Editing | 2.5% | P=0.350 | Focused code modification |
| S5 | Other-tool | 4.0% | P=0.613 | Catch-all tool usage |
| S4 | Searching | 5.6% | P=0.373 | WebSearch/Skill use, elevated failure |
| **S3** | **Pre-failure** | **1.3%** | **P=0.012** | **97% tool failure rate, 24.6x correction lift** |

**The pre-failure state (S3)** is the most diagnostically valuable discovery. It:
- Comprises only 1.3% of all turns but precedes 31.2% of corrections
- Is almost always a single turn (median duration: 1.0, max: 2)
- Transitions to reading+bash (S6) at 77.5% -- the agent recovers by exploring
- Has a 97.2% tool failure rate -- the agent's tools are failing

**Session trajectory**: Sessions start with exploration (S6: 36.1% at start) and transition toward text output (S0: 55.1% at end). Thinking (S2) peaks early (8.6% at start) and declines (5.5% at end). This matches the change-point finding that context degradation occurs early while human redirects occur late.

---

## 4. Agent Foraging Behavior

### Impatient foragers

Applying Pirolli & Card's information foraging theory to 189 sessions (5,519 patches, 31,277 foraging events):

| Metric | Value |
|--------|-------|
| Median patch residence | 1.0 turns |
| Mean patch residence | 2.86 turns |
| Patches with zero edits (exploration only) | 56.7% |
| Giving-up time (turns after last edit) | 0.27 (94.2% leave immediately) |
| Explore/exploit ratio | 2.11 reads per edit |

**The Marginal Value Theorem is not supported.** Only 14.9% of patches show diminishing returns; 45.4% show *increasing* returns. Agents leave patches before the best information is found. Residence time has near-zero correlation with gain rate (r=0.034).

**Struggling sessions forage differently:**

| Metric | Low success | High success | Delta |
|--------|-----------|-------------|-------|
| Patches per session | 55.6 | 29.4 | -26.2 |
| Residence time | 3.55 | 2.60 | -0.95 |
| Patch revisit rate | 0.455 | 0.404 | -0.05 |

Struggling sessions visit nearly twice as many patches with longer stays and higher revisit rates. This is thrashing -- re-visiting directories without extracting value -- not efficient exploration.

### Tool ecology

Ecological diversity differs dramatically between populations:

| Metric | Interactive | Subagent | Mixed |
|--------|-----------|----------|-------|
| Shannon H | **1.572** | 0.91 | 0.863 |
| Monoculture rate | **3.7%** | 18% | 46% |
| Distinct tools/session | **10.2** | varies | varies |

The mixed-corpus monoculture rate of 46% is misleading -- it is driven by subagent sessions dominated by StructuredOutput. Interactive sessions are highly diverse (3.7% monoculture, Shannon H=1.572). Species-area law holds in both populations. Tool diversity correlates with session success (PrefixSpan: sessions with `Read→Bash→Bash→Bash→Write` pattern have +39.1pp success bias).

---

## 5. Interaction Dynamics and Causal Structure

### Granger causality network

14 significant causal relationships (Bonferroni-corrected, confirmed in both Fisher aggregation and pooled analysis) across 106 sessions:

**Strongest causal arrows:**
- thinking_ratio → tool_diversity (p ≈ 0, 60-84% of sessions significant). More private reasoning *causes* more diverse tool usage.
- thinking_ratio → message_length (p ≈ 0, 78-87% significant). More thinking produces longer output.
- tool_failure → message_length (p = 7.85 x 10⁻¹¹⁰ pooled). Failures cause verbose compensation.
- correction → thinking_ratio (p = 6.55 x 10⁻¹⁵ Fisher, lag 4-5). Corrections cause *delayed* thinking increases -- the agent eventually thinks harder, but not immediately.

**8 bidirectional relationships** form tightly coupled feedback loops: thinking ↔ diversity, thinking ↔ message_length, thinking ↔ failures, diversity ↔ failures, diversity ↔ message_length, message_length ↔ failures, message_length ↔ corrections, thinking ↔ corrections.

### Temporal patterns (T-patterns)

125 sessions, 108,983 events. 280 statistically significant temporal patterns (p < 0.01 via permutation testing):

| Pattern | Occurrences | Median interval | Interpretation |
|---------|-------------|----------------|----------------|
| AB → AB (Bash self-chain) | 14,798 | 7.4s | Dominant execution loop |
| AK → AT (think → text) | 3,600 | 0.8s | Near-instantaneous |
| AF → AB (fail → bash) | 1,843 | 6.0s | Recovery via retry |
| UC → AT (correction → text) | 166 | 8.8s | Text response to correction |

### Behavioral perseveration

Lag sequential analysis (120 sessions, 10,070 events) confirms strong self-repetition:
- AR → AR: z = +41.64 (reading perseveration)
- AE → AE: z = +25.97 (editing perseveration)
- UR → AK: z = +24.54 (user requests always trigger thinking)

---

## 6. Process and Quality Control

### SPC analysis (4,046 sessions, 37 projects)

- 9.8% of sessions show at least one out-of-control violation
- **Zero process metrics achieve Cpk ≥ 1.0** -- the agent process is not capable by industrial standards
- CUSUM detects persistent upward drift in correction and tool failure rates over time
- All four metrics (correction rate, tool failure rate, amplification ratio, efficiency) fail capability assessment

### Process mining (189 sessions, 381,486 events)

The dominant rework loop is `agent_text → user_correction → agent_text` (100,030 occurrences). High-correction sessions collapse into this loop (91% of events), while low-correction sessions show balanced distribution across tool use, search, and editing.

---

## 7. Reversals, Corrections, and the Population Split

### What the split revealed

Separating the corpus into 2,594 interactive and 5,348 subagent sessions resolved three apparent contradictions and exposed two contaminated findings:

| Finding | Small corpus | Mixed full | Interactive only | Subagent only | Resolution |
|---------|-------------|-----------|-----------------|---------------|------------|
| Session degradation | 7.24x increasing | 0.51x decreasing | **Increasing** | Decreasing | Interactive confirms degradation; the mixed reversal was subagent dilution |
| Thinking block HR | HR=0.54 | HR=0.204 (p=10⁻⁴²) | HR=0.663 **(NS, p=0.40)** | N/A (inflated) | Mixed result was contaminated by correction misclassification in subagents |
| Monoculture rate | 36% | 46% | **3.7%** | 18% | Mixed rate inflated by StructuredOutput-dominated subagent sessions |
| Correction rate | 60.4% | 33.5% | (project-dependent) | 90% (artifact) | Subagent "corrections" are tool result returns, not human feedback |
| Risk suppression | 85.3% | 85.3% | **85.5%** | 61.9% | Interactive rate is the clean signal; subagent sample too small |
| Entropy (k=1) | -- | 0.715 bits | **0.731 bits** | 0.509 bits | Subagents are more predictable; mixing flattened the difference |
| Granger causal links | -- | 14 | **(from mixed)** | 3 | The rich causal network is primarily an interactive phenomenon |

### The lesson

The corpus contains two fundamentally different populations. Interactive sessions involve human steering, corrections, and the full range of agent behavioral states. Subagent sessions are autonomous tool-use loops with minimal human contact and a degenerate "correction" signal (tool results misclassified as corrections by regex patterns). Mixing them produced:

1. **Inflated statistical significance** (the survival analysis HR went from non-significant to p=10⁻⁴²)
2. **Reversed effect directions** (hazard trend flipped from increasing to decreasing)
3. **Diluted diversity metrics** (monoculture rate inflated from 3.7% to 46%)
4. **Spurious causal structure** (Granger relationships that exist only because of population confounding)

Any future analysis of this corpus must split or stratify by session type. The mixed-corpus results in the original version of this report have been corrected above.

---

## 8. Limitations

1. **Single operator.** All data is from one person across multiple machines. Findings may reflect this operator's interaction style, project types, and tool preferences rather than universal agent behavior.

2. **No frozen corpus.** Scripts read live session directories. Results drift on rerun as new sessions accumulate. No analysis used a snapshot.

3. **No multiple comparison corrections** in most analyses. With 23 techniques examining overlapping data, some significant results are expected by chance.

4. **Inconsistent "correction" definitions.** Each technique defines user corrections differently (regex patterns, message classification, behavioral coding). Cross-technique convergence may partly reflect shared definition artifacts.

5. **Self-review bias.** Claude Code analyzed its own session transcripts. Thinking block analysis, in particular, involves one Claude model interpreting another Claude model's private reasoning.

6. **Subagent contamination.** 5,348 of 7,909 sessions are subagent sessions with minimal human interaction. Mixing them with interactive sessions produced inflated significance levels, reversed effect directions, and spurious causal structure. All findings in this report have been verified against the interactive-only subset where they differ materially from the mixed corpus.

---

## 9. Conclusions

### What is robust

- **85.5% risk suppression is a model constant.** Four independent replications on interactive sessions. Same number every time (85.3%, 85.5%, 85.3%, 85.5%). Unaffected by population split.
- **Agent behavior has discoverable hidden states.** The pre-failure state (S3) at 24.6x correction lift is a potential real-time early warning system.
- **Agents under-explore.** The Marginal Value Theorem is violated -- agents leave patches too early. Both interactive and subagent populations show this.
- **Rigidity predicts failure.** In interactive sessions, perseveration (behavioral loops) outnumber chaotic episodes 5:1 and co-occur with errors 18.4% of the time.
- **Interactive and subagent sessions are fundamentally different populations.** Mixing them produces misleading aggregates. Any analysis of coding agent transcripts must stratify by session type.

### What was corrected by the population split

- **Thinking blocks as protective factor**: downgraded from confirmed (HR=0.204, p=10⁻⁴²) to suggestive (HR=0.663, p=0.40 on interactive-only). The mixed-corpus result was contaminated by subagent correction misclassification.
- **Session degradation**: restored. Interactive sessions show increasing hazard (agents get worse over time). The full-corpus reversal was subagent dilution.
- **Monoculture rate**: 3.7% on interactive sessions, not 46%. The headline number was inflated by StructuredOutput-dominated subagent sessions.

### What is suggestive

- **Thinking blocks correlate with fewer corrections** in multiple techniques (process mining, Granger), but the survival analysis effect is not significant on interactive sessions alone. The correlation may reflect task difficulty (easier tasks → more thinking → fewer corrections) rather than thinking preventing corrections.
- **Correction rate as maturity metric.** Declines with project age, but only in one operator's data.
- **The pre-failure state as a real-time detector.** 24.6x lift is compelling but based on 80 pre-correction observations.
- **Granger causal network.** The 14-relationship network from the mixed corpus needs retesting on interactive-only data; the subagent-only analysis found only 3 relationships.

### What requires further investigation

- **Multi-operator validation.** Every finding needs testing against data from other users.
- **Causal mechanisms.** Does thinking actually prevent errors, or do easier tasks naturally involve more thinking and fewer corrections? The population split weakened the causal case.
- **Intervention studies.** Can forcing thinking blocks (via system prompts) reduce corrections? The observational data is now ambiguous.
- **Real-time state detection.** Can the HSMM be run online to warn users when the agent enters a pre-failure state?
- **Better correction classifiers.** The regex-based correction detection misclassifies tool results in subagent sessions, contaminating multiple analyses. A validated classifier is a prerequisite for reliable cross-population comparison.

### The bottom line

The agent produces an average of 5.08 tokens of private reasoning for every token you see in interactive sessions. It identifies risks and suppresses them 85.5% of the time. When it gets stuck in a loop, it is about to fail. When it explores your codebase, it leaves before finding the best information. And when you mix interactive sessions with autonomous subagent loops and analyze them together, you get spectacular statistics that do not survive stratification.

Build systems that surface the hidden reasoning. Detect the pre-failure state. Force exploration where the agent would skim. Separate your populations before you analyze them. And never trust a narrative when a diff is available.

---

---

## Addendum: How Mixing Populations Affects Results

### The problem

The corpus contains 2,594 interactive sessions (human-in-the-loop, real corrections and steering) and 5,348 subagent sessions (autonomous tool-use loops, typically spawned by a parent agent, with minimal or no human contact). These populations differ on every measured dimension:

| Dimension | Interactive | Subagent | Ratio |
|-----------|-----------|----------|-------|
| Thinking block prevalence | High | 1.2% | ~50x |
| Shannon diversity (H) | 1.572 | 0.91 | 1.7x |
| Conditional entropy (k=1) | 0.731 bits | 0.509 bits | 1.4x |
| Monoculture rate | 3.7% | 18% | 0.2x |
| Granger causal links | ~14 | 3 | ~5x |
| Rigid entropy anomalies | 409 | 43 | ~10x |
| Dominant tool | Read (31%) | Read (38%) | similar |
| Correction signal | Real human feedback | Tool result returns (misclassified) | qualitatively different |

### Mechanism of contamination

The core issue is the **correction classifier**. All scripts use regex patterns to identify user corrections (phrases like "no", "that's wrong", "fix", "don't"). In interactive sessions, these patterns correctly identify human corrections. In subagent sessions, the "user" messages are actually tool result returns from the parent agent or system messages. These frequently contain words that match correction patterns ("fix the path", "error: no such file"), producing a spurious "correction" signal.

Because subagent sessions outnumber interactive sessions 2:1 and almost always trigger the correction classifier (90% "correction rate" vs real rates of 5-30% in interactive sessions), any analysis that uses correction as a variable is dominated by the subagent signal.

### Which findings were affected

**Severely contaminated:**
- Survival analysis (HR, p-values, hazard trend all changed)
- SPC control charts (correction rate metric inflated)
- Process mining (correction-retry loop counts inflated)

**Moderately affected:**
- Ecology diversity (monoculture rate inflated by subagent StructuredOutput sessions)
- Granger causality (14 relationships on mixed, 3 on subagent-only -- unclear how many survive interactive-only)
- Entropy rate (mean shifted by 0.2 bits toward the subagent value)

**Unaffected:**
- Risk suppression (85.3-85.5% -- consistent across all subsets)
- HSMM states (run on mixed but interpretable regardless)
- T-patterns (temporal structure is real in both populations)
- Information foraging (MVT violation holds in both)
- PrefixSpan (sequential patterns are population-specific but valid)
- Tool sequence mining (Markov transitions are population-specific but valid)

### Recommendations

1. **Always stratify.** Report interactive and subagent results separately. Mixed-corpus results are only meaningful for metrics unaffected by the correction classifier.

2. **Build a validated correction classifier.** The regex approach is adequate for interactive sessions but fails catastrophically on subagent sessions. A labeled validation set of 200+ messages from each population is needed.

3. **Treat subagent sessions as a separate research question.** Subagent behavior (autonomous tool loops, no human steering, high predictability, low diversity) is interesting in its own right but answers different questions than interactive behavior.

4. **Report population sizes.** Any finding that uses correction, correction rate, or correction-derived metrics must state which population it was measured on and how many sessions were in that population.

---

*Lightless Labs "Third Thoughts" project. Full analysis scripts and data in this repository. Methods catalog: `docs/methods-catalog.md`. Peer reviews of individual techniques: `docs/reviews/`. Split analysis outputs: `experiments/interactive/` and `experiments/subagent/`.*
