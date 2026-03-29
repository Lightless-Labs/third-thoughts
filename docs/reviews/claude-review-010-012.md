# Independent Methodology Review: Experiments 010-012

**Reviewer**: Claude Opus 4.6 (independent methodology review)
**Date**: 2026-03-20
**Scope**: Experiments 010, 011, and 012 from the agentic-engineering-sawdust project

---

## Experiment 010: Thinking Block Divergence

**Doc**: `experiments/010-thinking-block-divergence.md`
**Script**: `scripts/010_thinking_block_divergence.py`

### Methodology Soundness

The research question -- "What is the gap between what an agent thinks and what it says?" -- is well-formulated and genuinely novel. The corpus (Claude Code sessions with preserved thinking blocks) represents a rare opportunity; thinking blocks are typically stripped before they reach any analyst. The framing as a divergence analysis across four dimensions (volume, sentiment, plan, correction) is sensible.

However, the core methodological choice -- keyword-matching for sentiment/confidence classification -- is the experiment's weakest link and the authors partially acknowledge this. The approach treats the presence of any marker as a binary signal and counts distinct marker types, not occurrences. This conflates vocabulary breadth with uncertainty intensity. A turn containing "maybe" once scores the same as a turn containing five separate hedging expressions.

**Rating**: The question is excellent. The approach is reasonable for exploratory work but would not withstand scrutiny as confirmatory evidence.

### Implementation Quality

**Turn grouping logic (lines 192-300)**: Correctly handles the JSONL format where consecutive assistant messages form a single logical turn. This is a non-trivial parsing decision that is well-documented and correctly implemented.

**Marker counting (lines 140-146)**: The `count_markers()` function counts how many distinct markers appear (binary per marker), not total occurrences. This is a defensible choice for a "breadth of uncertainty signals" metric but is not documented as such. A turn with "maybe" appearing 10 times counts the same as one with "maybe" appearing once. This undercounts intensity.

**Critical issue -- "Let me" as a confidence marker**: "Let me" appears in 79.2% of public text turns and is classified as a confidence marker. This single marker dominates the confidence signal. The document's own methodology note (appended, lines 233) acknowledges this is likely a system prompt artifact, but the main analysis numbers are reported without adjustment. The 57% divergence rate is built on a foundation where the confidence detector fires on nearly every turn. Removing "Let me" from the confidence list would substantially reduce the divergence rate, and the document does not report what the adjusted figure would be.

**Correction detection (lines 277-290)**: Uses regex heuristics on the *next* user message. The correction markers include generic words like "wrong," "error," "broken," which could appear in legitimate technical discussion (e.g., "the error handling looks good" would be a false positive). There is no validation of false positive rates. The terse-negative detector (lines 286-290) catches short messages containing "no," "wrong," "stop," "fix," or "revert," which is aggressive -- "no worries" or "fix looks great" would both be false positives.

**Public text char counting (lines 253-254)**: `total_public_chars` is accumulated *only* for turns that have thinking blocks (`if has_thinking`). This means the "total public text chars" figure of 1,673,187 excludes all public text from turns without thinking. The 5.3x ratio is therefore the ratio of thinking text to public text *on turns that have thinking*, not a global ratio across all assistant output. The document describes it as a "Global ratio" (line 36), which is misleading. The actual ratio of thinking to *all* public text would be lower.

**Percentile computation (lines 387-391)**: Uses index-based percentile calculation (`per_turn_ratios[len(per_turn_ratios)//4]`) rather than interpolation. For large n (6,241), this is fine. For the session-level analysis (n=712), it is adequate but not ideal.

### Statistical Rigor

**No inferential statistics**: The analysis is entirely descriptive. No confidence intervals, no hypothesis tests, no effect sizes with uncertainty bounds. The "5.8x more often" correction rate difference (3.5% vs 0.6%) is presented without a chi-square test, Fisher's exact test, or confidence interval. With n=1,332 and n=4,529, this would likely be significant, but we cannot know.

**No multiple comparison corrections**: Acknowledged in limitations but still a gap. The document makes at least 6 distinct claims from the same dataset.

**Confounding in the transparency analysis**: The document correctly notes (line 194) that the transparent/opaque correction rate difference is "likely correlation, not causation" -- transparent turns involve harder problems. This is a genuine confound that makes the 5.8x figure largely uninterpretable. Credit for acknowledging it; debit for still headlining it as a "key finding."

**Sample non-independence**: All 64,626 turns come from one user. Turns within a session are serially correlated. Sessions within a project share context. No clustering or mixed-effects modeling is applied. This means all reported percentages have unknown true standard errors -- they could be much wider than naive computation suggests.

### Findings Validity

| Finding | Robustness | Notes |
|---------|-----------|-------|
| 5.3x thinking/public ratio | **Moderate** | Numerically correct on the selected turns, but the "global" framing is misleading since it only covers turns with thinking blocks. Still, the directional finding (much more thinking than public text) is robust. |
| 57% divergence rate | **Fragile** | Dominated by "Let me" as a confidence marker. Without "Let me," this drops substantially. The methodology note acknowledges this but the headline number stands uncorrected. |
| 85% risk suppression | **Moderate-to-Strong** | Uses more distinctive keyword sets. Less susceptible to the system prompt artifact problem. The directional finding (most risks identified in thinking are not shared publicly) is likely sound. |
| 88.5% plan suppression | **Moderate** | Based on only 199 turns (1.8% of corpus). The small base makes this fragile. The keywords used (e.g., "either," "versus," "trade-off") are reasonable. |
| Correction rate invariance to divergence | **Moderate** | The null finding (divergence does not predict correction) is interesting but could be a power issue -- correction is rare (1.0%) and the divergence measure is noisy. |
| 0.6% vs 3.5% correction rates (opaque vs transparent) | **Weak** | Confounded by problem difficulty. The document acknowledges this but still lists it as a key takeaway. |

### Limitations Acknowledged vs Unacknowledged

**Acknowledged**: Single-user corpus, unvalidated correction detection, no multiple comparison corrections, session non-independence. These are the right limitations to flag.

**Unacknowledged**:

1. **The "Let me" problem invalidates the headline divergence rate.** The methodology note (line 233) was added from an "external review" but the main findings are not revised. This is the single biggest validity threat.

2. **Selection bias in "paired turns."** Only 6,241 of 10,941 thinking turns have paired public text. The 4,700 thinking-only turns are excluded from divergence analysis. If these thinking-only turns are systematically different (they are -- they precede tool calls), then the divergence analysis applies to a non-representative subset.

3. **Keyword overlap between categories.** "problem" and "issue" appear in both UNCERTAINTY_MARKERS and (implicitly via context) in CONFIDENCE_MARKERS ("The problem is," "The issue is"). A turn saying "The problem is X" in both thinking and public text would score as both uncertain and confident. No deduplication or conflict resolution.

4. **No inter-rater reliability.** The keyword approach has no validated precision/recall against human-labeled ground truth. How often does "actually" in thinking text genuinely indicate uncertainty vs. a discourse connector? (e.g., "actually, this function handles that case correctly" is not uncertainty).

5. **Token estimation.** The ~4 chars/token approximation (lines 373-374) is crude. Actual tokenization would give different numbers. This is a minor issue but the document presents derived token counts as findings.

6. **The public_chars denominator issue** described above. The 5.3x ratio is not a global ratio as labeled.

### Overall Grade: B-

The experiment asks a genuinely interesting question and uses a unique dataset. The volume analysis (how much thinking vs. public text) is sound directionally. The risk and plan suppression findings are moderately well-supported. But the headline finding (57% divergence rate) is built on a flawed confidence detector, and the analysis lacks any inferential statistics. The document is honest about several limitations but leaves the most damaging one (the "Let me" problem) as a footnote rather than revising the main claims.

---

## Experiment 011: NCD Session Clustering

**Doc**: `experiments/011-ncd-session-clustering.md`
**Script**: `scripts/011_ncd_session_clustering.py`

### Methodology Soundness

Using Normalized Compression Distance for session clustering is a creative and methodologically interesting choice. NCD is a legitimate similarity metric grounded in Kolmogorov complexity theory and does not require hand-crafted features. The windowed n-gram fingerprint approach to address length dependence is a sensible engineering decision.

The core idea -- reduce sessions to symbol streams, then cluster on structural similarity -- is well-motivated. The symbol alphabet is reasonable: user message lengths, assistant text/thinking, and tool types capture the essential interaction structure.

However, the method has a fundamental tension: the fingerprint transformation discards so much information that it is unclear what the resulting NCD distances actually measure. A fingerprint consists of top-5 trigram frequencies per window, quantized to 10 levels. Two sessions could have identical fingerprints despite very different actual symbol sequences. The low correlation between raw NCD and fingerprint NCD (r=0.170) is presented as evidence that the fingerprint "captures different structure," but it could equally indicate that the fingerprint is too lossy to capture *any* coherent structure.

### Implementation Quality

**Symbol stream extraction (lines 56-136)**: Clean implementation. The tool name mapping is comprehensive. The handling of user messages correctly separates tool results (coded as "R") from genuine user inputs. The `isMeta` check (line 93) correctly skips system messages.

**Fingerprint construction (lines 139-179)**: The implementation has a subtle issue. The window boundaries are computed from the n-gram list length (`len(ngrams)`) rather than the symbol list length. For the last window (`w < n_windows - 1` check on line 161), all remaining n-grams are included, meaning the last window can be substantially larger than others. For a 100-event session producing 98 trigrams with 10 windows of size 9, the last window would contain 98 - 81 = 17 n-grams, nearly double the others. This asymmetry means the last window's trigram profile is computed over a different-sized sample than earlier windows.

**NCD computation (lines 246-256)**: Standard implementation using zlib. One concern: `zlib.compress` uses a default compression level (6), which is fine for comparison purposes but means the NCD values are compressor-dependent. The implementation correctly handles the edge case where `max(cx, cy) == 0`.

**Concatenation order in NCD**: The function computes `C(xy)` as `len(zlib.compress(xb + yb))`. NCD should be symmetric, but zlib compression is order-dependent (the compressor builds a dictionary from the first string that helps compress the second). In practice, the asymmetry is small for these string sizes, but a more robust implementation would compute both `C(xy)` and `C(yx)` and average them. This is a known limitation of practical NCD implementations and is minor.

**Clustering (lines 286-323)**: Uses average-linkage hierarchical clustering, which is appropriate for NCD. The silhouette-score-based k selection (searching k=5 to k=10) is reasonable. However, the silhouette computation is manual rather than using `sklearn.metrics.silhouette_score`, which would have been more standard and less error-prone. The manual implementation appears correct.

**Stratified sampling (lines 211-238)**: The sampling strategy selects up to 3 sessions per project, evenly spaced by size. This is reasonable for ensuring diversity but means the sample is not representative of the corpus -- small projects contribute proportionally more. This is acknowledged implicitly by reporting project distributions but not discussed as a limitation.

**Cluster labeling (lines 463-501)**: The automatic label generation is heuristic-based and does not affect the analysis. However, the labels in the report (e.g., "Autonomous / Bash-Dominant / Detailed-Prompts") are presented as findings when they are really just automatic descriptions of computed metrics. The labels do not tell us anything the metrics do not already say.

### Statistical Rigor

**No statistical validation of clusters**: The silhouette score is reported for selecting k but is not reported in the final output. There is no bootstrap stability analysis (e.g., running clustering 100 times on resampled data to see if clusters are stable). With n=48, clusters are likely unstable -- adding or removing a few sessions could change assignments substantially.

**Singleton clusters are not clusters**: Three of the nine "clusters" contain a single session (Clusters 2, 5, and 9). These are outliers, not clusters. Reporting them as structural archetypes is misleading. With n=48 and k=9, the average cluster size is 5.3; having singletons is expected but they should be labeled as ungrouped outliers.

**Cohesion of 0.000**: Singleton clusters report cohesion of 0.000, which is definitionally true but meaningless. It should not be reported as if it indicates tight clustering.

**The "length independence" claim is overstated**: Cluster 4 contains sessions ranging from 115 to 8,368 events and is cited as evidence that "structural shape is independent of duration." But Cluster 4 is also the largest cluster (n=27, 56% of all sessions). A cluster that contains everything is not evidence of length independence -- it is evidence of insufficient discrimination. Cluster 7 (all sessions 8-22 events) and Cluster 8 (all sessions 7,609-7,950 events) show clear length stratification.

**Project-cluster correlation**: The analysis reports that JASONETTE-Reborn and parsiweb-previews have "strong" project-cluster correlation (100% in cluster 4). But cluster 4 contains 27 of 48 sessions (56%). Three sessions landing in a cluster that contains 56% of all sessions is not impressive -- by chance alone, the probability of all 3 sessions landing in a cluster of this size is roughly 0.56^3 = 17.6%. No significance test is performed.

### Findings Validity

| Finding | Robustness | Notes |
|---------|-----------|-------|
| Structural archetypes exist | **Weak** | 9 clusters from 48 sessions, 3 of which are singletons. No stability analysis. The largest cluster absorbs 56% of sessions, suggesting poor discrimination. |
| Autonomy spectrum | **Moderate** | The autonomy metric (tools per user message) is well-defined and the variation across clusters is real. But this could be computed without NCD clustering -- a simple histogram of autonomy ratios would show the same thing. |
| Project-cluster correlation | **Weak** | No significance test. The dominant cluster absorbs most sessions, making correlation trivially easy to achieve by chance. |
| Length independence | **Mixed** | Some clusters show length independence (Cluster 4, 6). Others show clear length stratification (Cluster 7, 8). The claim is selectively supported. |
| Thinking pattern variation | **Moderate** | Descriptively true that thinking block usage varies across clusters. Not tested for significance. |

### Limitations Acknowledged vs Unacknowledged

**Acknowledged**: Same boilerplate as Experiment 010 (single-user, unvalidated classification, no multiple comparison corrections, session non-independence). The boilerplate is identical, suggesting copy-paste rather than experiment-specific reflection.

**Unacknowledged**:

1. **n=48 is very small for clustering into 9 groups.** Average cluster size is 5.3, and three clusters are singletons. The analysis is severely underpowered for the number of clusters sought. The k-range of 5-10 should have started lower (e.g., 2-6).

2. **No cluster stability analysis.** Bootstrap resampling or leave-one-out analysis would reveal whether these clusters are robust or artifacts of the specific sample.

3. **The fingerprint is a lossy transformation with no validation.** The low r=0.170 correlation with raw NCD is presented positively, but no evidence is given that the fingerprint captures *meaningful* structure rather than noise. A random permutation test (shuffle symbol streams, recompute fingerprints, check if NCD distances are distinguishable from real data) would validate the approach.

4. **No comparison to simpler baselines.** Would clustering on simple feature vectors (tool ratios, session length, user message count) produce equivalent or better clusters? Without this comparison, we cannot assess whether NCD adds value over feature engineering.

5. **Compression artifacts.** zlib compression has a minimum overhead (~11 bytes for header/checksum). For very short fingerprint strings, this overhead dominates the compressed size, biasing NCD toward 1.0. This may explain the high NCD mean (0.732).

6. **The "user_ratio" includes tool results ("R" symbols) counted under the user role.** In the structural profile, "User messages" percentage includes tool result returns, which are not genuine user messages. This conflates two very different event types. (Looking at the code at lines 413-414, `user_ratio` counts symbols starting with "U" -- and "R" does not start with "U", so this is actually handled correctly. However, "U:result" in the report tables *is* the "R" symbol after expansion, so the report's "User message sizes" tables include tool results, which is confusing.)

7. **Sampling bias.** The stratified sampling ensures exactly 3 sessions per project (where available), which overrepresents small projects. A project with 1 session gets 1 representative; a project with 100 sessions also gets 3. This distorts the cluster composition.

### Overall Grade: C+

The NCD approach is creative and the implementation is competent, but the analysis is underpowered (n=48 for 9 clusters), lacks statistical validation (no stability analysis, no significance tests, no comparison to baselines), and overstates its findings. Three singleton "clusters" are reported as archetypes. The largest cluster absorbs 56% of sessions, suggesting the method does not discriminate well. The windowed fingerprint transformation is an interesting idea but is not validated against alternatives. The identical boilerplate limitations section suggests insufficient methodological self-reflection.

---

## Experiment 012: Cross-Domain Corpus Pattern Extraction Research

**Doc**: `experiments/012-cross-domain-corpus-research.md`
**Script**: No script exists. This is a literature review, not a computational experiment.

### Methodology Soundness

This is not an experiment in the traditional sense -- it is a structured literature review conducted via API queries to Perplexity (sonar-pro) and Linkup (deep search). As a literature review, the relevant question is: does it accurately represent the cited methods, and does it make sound recommendations for transferability?

**Strengths of the approach**: The breadth is impressive. Eight research queries surfaced 31 distinct techniques from 12+ fields. The technique descriptions are generally accurate and the "application to human-agent corpus" sections demonstrate genuine understanding of how each method would transfer. The tiered recommendation system (Tier 1/2/3) is practical and defensible.

**Weakness of the approach**: Using LLM-based search tools (Perplexity, Linkup) for a literature review introduces a systematic bias toward highly-cited, well-known methods. Niche but potentially valuable techniques are likely underrepresented. There is no systematic search protocol (no PRISMA-style inclusion/exclusion criteria, no search term documentation beyond the 8 query topics). The review cannot claim comprehensiveness.

### Implementation Quality

No script to evaluate. The "implementation" is the research process itself.

**Citation quality**: Most key references are real and correctly attributed (Bakeman & Quera 2011, Fournier-Viger et al. 2017, Magnusson 2000, Therneau & Grambsch 2000, Shaffer et al. 2016, Roberts et al. 2014, Gabadinho et al. 2011). The references to specific tools (GSEQ, SPMF, TraMineR, lifelines, ELAN) are accurate.

**One factual concern**: The document references "Ruckdeschel, Baumann & Wiedemann (2024)" for argument mining with SPM at a venue called "RATIO 2024, LNCS 14638." This is specific enough to be either correct or a plausible LLM hallucination. The level of detail (LNCS volume number) warrants verification.

**Tool recommendations**: Generally sound. The recommendation of `lifelines` for survival analysis, TraMineR for sequence analysis, SPMF for pattern mining, and PM4Py for process mining reflects current best practices.

**Missing methods**: Some notable omissions:

1. **Hidden Markov Models (HMMs)** receive only a passing mention under dialog act tagging. HMMs are one of the most natural methods for modeling sequential state transitions in conversation data and deserve their own entry.
2. **Recurrence Quantification Analysis (RQA)** -- a nonlinear dynamics method for finding deterministic structure in sequences -- is absent despite being directly relevant.
3. **Change Point Detection** -- methods for identifying regime changes in sequential data -- is not discussed, despite being implemented in experiment 018 of this same project.
4. **Information-theoretic measures** (transfer entropy, mutual information over time series) are absent despite being directly relevant to measuring information flow between human and agent.

### Statistical Rigor

Not applicable in the traditional sense, as this is a literature review. However, the document makes implicit claims about technique ranking ("most promising," "Tier 1") without any formal comparison criteria. The ranking appears based on the author's judgment of transferability and ease of implementation, which is reasonable but subjective.

The "42+ distinct techniques from 12+ fields" claim in the summary is inflated. Several entries are tools rather than techniques (ELAN, PRAAT, Noldus Observer XT, SALT), and some techniques are listed twice (T-Pattern Detection appears as both entry 3 and entry 12). A more honest count would be approximately 20-25 distinct methodological approaches.

### Findings Validity

As a literature review, the "findings" are the technique catalog itself.

| Aspect | Assessment |
|--------|-----------|
| Accuracy of method descriptions | **Strong** -- descriptions are generally correct and show understanding beyond surface-level summaries |
| Transferability assessments | **Moderate-to-Strong** -- the "Application to human-agent corpus" sections are thoughtful and specific |
| Completeness | **Moderate** -- broad coverage but with notable omissions (HMMs, RQA, change point detection, information-theoretic measures) |
| Tool recommendations | **Strong** -- practical, current, and correctly differentiated by complexity |
| Tier ranking | **Moderate** -- reasonable but subjective; no formal criteria stated |

### Limitations Acknowledged vs Unacknowledged

**Acknowledged**: None explicitly. The document has no limitations section, which is a significant omission for a research document.

**Unacknowledged**:

1. **Search methodology not documented.** The 8 queries are partially documented in the "Raw Research Results" section, but the exact query strings, search parameters, and date of queries are not recorded. This makes the review non-reproducible.

2. **LLM-mediated search bias.** Perplexity and Linkup are LLM-based tools that may hallucinate references, conflate methods, or omit less-cited work. No manual verification protocol is described.

3. **No systematic inclusion/exclusion criteria.** The 31 techniques appear to be everything the search returned, with no filtering for relevance, quality of evidence, or maturity of the method.

4. **Duplicate entries.** T-Pattern Detection appears twice (entries 3 and 12). Entry 12 is labeled "elaboration" but largely repeats entry 3.

5. **Several entries are tools, not methods.** ELAN (entry 14), Praat (entry 15), Noldus Observer XT (entry 13), and SALT (entry 10) are software tools. Their inclusion inflates the technique count.

6. **No assessment of evidence quality.** Methods backed by decades of methodological research (survival analysis, HMMs, process mining) are presented alongside methods with thin empirical support (GP-HSMM, frequent interaction tree mining) without differentiation.

7. **The "Application to human-agent corpus" sections are speculative.** None have been validated. Some applications are plausible but others are stretches -- e.g., Praat (entry 15), which is for acoustic speech analysis, is included with the caveat "not directly applicable to text-only corpora." If it is not applicable, it should not be included.

### Overall Grade: B

As a literature review and technique catalog, this is genuinely useful work. The breadth of coverage is impressive, the technique descriptions are mostly accurate, and the transferability assessments show real thought. The tiered recommendation system is practical. However, the document lacks a limitations section, uses inflated counts, includes duplicates and non-methods, applies no systematic search methodology, and provides no evidence quality assessment. The absence of a script is not a limitation -- this is correctly identified as a research document rather than a computational experiment.

---

## Cross-Experiment Observations

### The Boilerplate Limitations Problem

Experiments 010 and 011 share identical limitations sections (word-for-word). This suggests the limitations were written once and copy-pasted rather than derived from experiment-specific methodological reflection. Each experiment has distinct validity threats that deserve specific discussion:

- Experiment 010's biggest threat is the "Let me" confidence marker problem, which is mentioned only in a methodology note appended after the limitations section.
- Experiment 011's biggest threat is the sample size (n=48) relative to the number of clusters (k=9), which is not mentioned at all.

### Exploratory vs. Confirmatory Framing

All three experiments include a disclaimer that "findings are descriptive associations from a convenience sample." This is appropriate. However, the findings sections of experiments 010 and 011 use language that implies stronger conclusions than exploratory analysis supports ("The confidence mask works," "Structural archetypes exist"). The tension between the disclaimer and the rhetoric weakens credibility.

### What Is Missing Across All Three

1. **Reproducibility information.** No random seeds, no exact software versions, no environment specifications. The scripts would produce different results if run on a different day (the corpus grows over time as new sessions are created).
2. **Data availability.** The corpus is one user's private session data, making independent replication impossible. This is inherent to the project but should be stated explicitly as a fundamental limitation.
3. **Pre-registration.** None of these analyses were pre-registered. All findings should be treated as hypothesis-generating, not hypothesis-confirming. The disclaimers acknowledge this but the findings sections do not consistently maintain this framing.

---

## Summary Grades

| Experiment | Grade | Key Strength | Key Weakness |
|-----------|-------|-------------|-------------|
| 010: Thinking Block Divergence | **B-** | Novel dataset exploiting thinking blocks; genuine insight into hidden reasoning | "Let me" confidence marker inflates headline finding; no inferential statistics |
| 011: NCD Session Clustering | **C+** | Creative use of information-theoretic distance; good engineering | n=48 for 9 clusters; no stability analysis; largest cluster absorbs 56% of data |
| 012: Cross-Domain Corpus Research | **B** | Impressive breadth; accurate technique descriptions; practical recommendations | No search methodology; inflated counts; no limitations section; speculative applications |
