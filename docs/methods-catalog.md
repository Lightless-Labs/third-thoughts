# Third Thoughts: Methods Catalog

A comprehensive reference of all analytical methods applied to the corpus of AI agent session transcripts. Methods span 14+ academic disciplines, adapted for the study of human-agent interaction at scale.

---

## 1. LLM-Based Extraction

### 1.1 Multi-Model Pattern Extraction
**Discipline**: Natural Language Processing / Qualitative Research
**Purpose**: Extract recurring patterns from session transcripts using multiple LLM families as independent extractors.
**Implementation**: Parallel Claude Code subagents processing transcript batches, with cross-validation passes from Codex/GPT-5.4 and Gemini 3.1 Pro Preview.
**Key assumption**: If multiple model families independently identify the same pattern, it is more likely to be a genuine structural feature rather than a single model's bias.
**Limitation**: LLMs share training-data overlap, producing methodological monoculture — cross-model validation validates but does not discover.

**References**:
- Brown, T. et al. (2020). "Language Models are Few-Shot Learners." *NeurIPS 2020*. arXiv:2005.14165
- Wei, J. et al. (2022). "Chain-of-Thought Prompting Elicits Reasoning in Large Language Models." *NeurIPS 2022*. arXiv:2201.11903

### 1.2 Multi-Model Consensus Engine (Refinery)
**Discipline**: Decision Science / Ensemble Methods
**Purpose**: Rank and prioritize extracted patterns using iterative cross-model evaluation with vote-threshold convergence.
**Implementation**: Three models independently score patterns on importance, novelty, and actionability. Each model peer-reviews the others' rankings. Convergence declared when the top-ranked answer holds position for 2 consecutive rounds above a threshold score of 8.0.
**Key distinction**: The refinery scores *answers* (complete syntheses), not individual patterns — it selects the best-argued synthesis, not a statistical aggregate.
**Limitation**: Rewards articulability over importance; susceptible to narrative drift in editorial applications.

**References**:
- Surowiecki, J. (2004). *The Wisdom of Crowds*. Doubleday.
- Dalkey, N. & Helmer, O. (1963). "An Experimental Application of the Delphi Method to the Use of Experts." *Management Science*, 9(3), 458–467.
- Wang, X. et al. (2023). "Self-Consistency Improves Chain of Thought Reasoning in Language Models." *ICLR 2023*. arXiv:2203.11171

---

## 2. Quantitative Text Analytics

### 2.1 Corpus Statistics and TF-IDF Analysis
**Discipline**: Computational Linguistics / Information Retrieval
**Purpose**: Characterize the corpus quantitatively — message lengths, token distributions, vocabulary diversity — and identify distinctive terms per session or project using Term Frequency–Inverse Document Frequency.
**Implementation**: Standard TF-IDF vectorization across session documents, with cosine similarity for session comparison.

**References**:
- Salton, G. & Buckley, C. (1988). "Term-Weighting Approaches in Automatic Text Retrieval." *Information Processing & Management*, 24(5), 513–523.
- Manning, C.D., Raghavan, P. & Schütze, H. (2008). *Introduction to Information Retrieval*. Cambridge University Press. Ch. 6.

### 2.2 Thinking Block Divergence Analysis
**Discipline**: Discourse Analysis / Cognitive Science
**Purpose**: Measure the gap between an agent's private reasoning (thinking blocks / chain-of-thought) and its public output. Quantify risk suppression, alternative suppression, and confidence masking.
**Implementation**: Parse JSONL for paired thinking/public content. Compute volume ratios (tokens private vs. public), classify private content for uncertainty/risk/alternatives, measure suppression rates.
**Key finding (original corpus)**: 5.3:1 private-to-public ratio per turn; 85.3% of identified risks suppressed; users correct opaque turns at only 0.6%.
**Limitation**: "Let me" artifacts from system prompts contaminate confidence classification; no inferential statistics applied.

**References**:
- Wei, J. et al. (2022). "Chain-of-Thought Prompting Elicits Reasoning in Large Language Models." arXiv:2201.11903
- Kadavath, S. et al. (2022). "Language Models (Mostly) Know What They Know." arXiv:2207.05221

---

## 3. Sequential Pattern Analysis

### 3.1 Markov Chain Tool Sequence Mining
**Discipline**: Stochastic Processes / Process Analytics
**Purpose**: Model tool usage as a first-order Markov chain. Compute transition probabilities between tool types (Bash→Edit, Read→Write, etc.) to identify workflow patterns.
**Implementation**: Extract ordered tool calls from session JSONL. Build transition matrix. Analyze self-loop rates, entry/exit tools, and position-dependent tool distributions.
**Key metric**: Bash self-chaining rate (78.5% in original corpus) as predictor of human corrections.

**References**:
- Norris, J.R. (1997). *Markov Chains*. Cambridge University Press.
- Agrawal, R. & Srikant, R. (1995). "Mining Sequential Patterns." *Proc. 11th IEEE ICDE*, 3–14.

### 3.2 Lag Sequential Analysis
**Discipline**: Behavioral Psychology / Ethology
**Purpose**: Test whether specific behavioral sequences occur more often than expected by chance. Originally developed for animal behavior coding, applied here to human-agent interaction sequences.
**Implementation**: Code each event (agent text, agent edit, user correction, tool call, thinking block) with behavioral codes. Compute transitional probabilities at lags 1–5. Test significance with z-scores against chance baseline.
**Key finding (original corpus)**: Thinking predicts text (z=+29.7) but not editing (z=−12.5); reading reliably predicts editing across all lags.

**References**:
- Bakeman, R. & Gottman, J.M. (1997). *Observing Interaction: An Introduction to Sequential Analysis* (2nd ed.). Cambridge University Press.
- Sackett, G.P. (1979). "The Lag Sequential Analysis of Contingency and Cyclicity in Behavioral Interaction Research." In *Handbook of Infant Development*, ed. J.D. Osofsky, 623–649. Wiley.
- Yoder, P.J. & Symons, F.J. (2010). *Observational Measurement of Behavior*. Springer.

### 3.3 Smith-Waterman Sequence Alignment
**Discipline**: Bioinformatics / Genomics
**Purpose**: Treat tool-call sequences as "genomic" sequences and apply local alignment algorithms to find conserved motifs across sessions. Identify structural signatures of successful vs. struggling sessions.
**Implementation**: Encode tool calls as single characters. Apply Smith-Waterman local alignment with custom substitution matrices. Cluster sessions by alignment score. Compute motif odds ratios.
**Key finding (original corpus)**: Successful sessions exhibit R-Ak-Tb (Read-Think-Bash) deliberation motif (OR=10.6x); struggling sessions show At-At-At verbosity failure (OR=4.1x).

**References**:
- Smith, T.F. & Waterman, M.S. (1981). "Identification of Common Molecular Subsequences." *Journal of Molecular Biology*, 147(1), 195–197.
- Altschul, S.F. et al. (1990). "Basic Local Alignment Search Tool." *Journal of Molecular Biology*, 215(3), 403–410.

---

## 4. Survival and Hazard Analysis

### 4.1 Kaplan-Meier Estimation and Cox Proportional Hazards
**Discipline**: Biostatistics / Epidemiology
**Purpose**: Model "time to first correction" as a survival problem. Estimate when sessions typically require human intervention, and identify covariates that accelerate or delay corrections.
**Implementation**: Define "event" as first user correction; "time" as number of turns. Kaplan-Meier estimator for survival curves. Nelson-Aalen cumulative hazard. Cox PH model with covariates: prompt length, thinking block presence, tool density.
**Key finding (original corpus)**: Median survival 34 turns; hazard ratio increases 7.24x from first third to last third of session; longer prompts protective (HR=0.54).
**Limitation**: Cox PH assumption of proportional hazards not tested; covariates and competing risks poorly modeled.

**References**:
- Kaplan, E.L. & Meier, P. (1958). "Nonparametric Estimation from Incomplete Observations." *JASA*, 53(282), 457–481.
- Cox, D.R. (1972). "Regression Models and Life-Tables." *Journal of the Royal Statistical Society B*, 34(2), 187–220.
- Kleinbaum, D.G. & Klein, M. (2012). *Survival Analysis: A Self-Learning Text* (3rd ed.). Springer.

---

## 5. Compression and Information Theory

### 5.1 Normalized Compression Distance (NCD) Session Clustering
**Discipline**: Information Theory / Algorithmic Complexity
**Purpose**: Cluster sessions by structural similarity without relying on semantic content. NCD measures how much two sequences share structure by comparing their compressed sizes.
**Implementation**: Reduce sessions to structural fingerprints (message lengths, thinking block sizes, tool call types). Compress with zlib. Compute pairwise NCD: `NCD(x,y) = (C(xy) - min(C(x),C(y))) / max(C(x),C(y))`. Hierarchical clustering on the NCD matrix.
**Key finding (original corpus)**: 9 archetypes from 48 sessions; most autonomous archetype averaged 43.7 tool calls per user message.
**Limitation**: Small sample (48 sessions); 3 singleton clusters; no stability analysis; fingerprint transformation weakly correlated with raw NCD (r=0.170).

**References**:
- Li, M. et al. (2004). "The Similarity Metric." *IEEE Transactions on Information Theory*, 50(12), 3250–3264.
- Cilibrasi, R. & Vitányi, P.M.B. (2005). "Clustering by Compression." *IEEE Transactions on Information Theory*, 51(4), 1523–1545.
- Bennett, C.H. et al. (1998). "Information Distance." *IEEE Transactions on Information Theory*, 44(4), 1407–1423.

---

## 6. Process Mining

### 6.1 Inductive Miner Workflow Discovery
**Discipline**: Business Process Management / Computer Science
**Purpose**: Discover process models from event logs — treating tool calls and user messages as process events to find the underlying workflow structure.
**Implementation**: Convert session JSONL to pm4py event logs. Apply Inductive Miner algorithm. Analyze directly-follows graphs, conformance checking, and loop detection.
**Key finding (original corpus)**: Correction-retry loop accounts for 19% of all transitions; post-correction agents retry from memory 89.3% vs. searching codebase 0.1%.
**Limitation**: Graded D in peer review — flower model (all activities interleave freely) provides little discriminatory power.

**References**:
- van der Aalst, W.M.P. (2016). *Process Mining: Data Science in Action* (2nd ed.). Springer.
- Leemans, S.J.J., Fahland, D. & van der Aalst, W.M.P. (2014). "Discovering Block-Structured Process Models from Event Logs Containing Infrequent Behaviour." *BPM 2013 Workshops*, LNBIP 171, 66–78.

---

## 7. Statistical Process Control

### 7.1 X-bar/R Control Charts and CUSUM
**Discipline**: Industrial Engineering / Quality Management
**Purpose**: Treat agent sessions as a manufacturing process. Apply control charts to detect out-of-control sessions and assess process capability.
**Implementation**: Compute per-session metrics (correction rate, tool failure rate, amplification ratio). Build X-bar and R charts with 3-sigma limits. CUSUM charts for drift detection. Process capability indices (Cp, Cpk).
**Key finding (original corpus)**: 94.1% in-control; zero metrics achieve Cpk≥1.0; tool failure rate 33.8% out of spec.
**Limitation**: Normality assumption violated by heavily skewed distributions; tool call double-counting bug found in implementation.

**References**:
- Montgomery, D.C. (2019). *Introduction to Statistical Quality Control* (8th ed.). Wiley.
- Page, E.S. (1954). "Continuous Inspection Schemes." *Biometrika*, 41(1/2), 100–115.
- Western Electric Company (1956). *Statistical Quality Control Handbook*. Western Electric.

---

## 8. Ecological Methods

### 8.1 Shannon-Simpson Diversity and Species-Area Laws
**Discipline**: Community Ecology / Macroecology
**Purpose**: Treat tool types as "species" and sessions as "ecosystems." Measure tool diversity using ecological indices. Test whether tool diversity follows species-area scaling laws.
**Implementation**: Compute Shannon H index, Simpson's D, species richness per session. Fit species-area curves (S = c · ln(Length) + d). Compute Jaccard beta diversity between projects.
**Key finding (original corpus)**: Monoculture sessions (low diversity) have higher correction rates; species-area law fits with R²=0.842.

**References**:
- Shannon, C.E. (1948). "A Mathematical Theory of Communication." *Bell System Technical Journal*, 27(3), 379–423.
- Simpson, E.H. (1949). "Measurement of Diversity." *Nature*, 163, 688.
- Rosenzweig, M.L. (1995). *Species Diversity in Space and Time*. Cambridge University Press.
- Jaccard, P. (1912). "The Distribution of the Flora in the Alpine Zone." *New Phytologist*, 11(2), 37–50.

---

## 9. Change-Point Detection

### 9.1 PELT Algorithm (Pruned Exact Linear Time)
**Discipline**: Time Series Analysis / Signal Processing
**Purpose**: Detect structural breaks in session behavior — moments where the agent's tool usage, message length, or thinking patterns shift abruptly.
**Implementation**: Compute rolling metrics per session (tool entropy, message length variance, thinking ratio). Apply PELT algorithm with BIC penalty. Analyze change-point distribution and the explore-lock-stick cycle.
**Key finding (original corpus)**: Mean 2.8 change points per session; tool entropy most sensitive signal; bimodal distribution with peaks at 0–20% and 60–80% of session.

**References**:
- Killick, R., Fearnhead, P. & Eckley, I.A. (2012). "Optimal Detection of Changepoints with a Linear Computational Cost." *JASA*, 107(500), 1590–1598.
- Truong, C., Oudre, L. & Vayer, N. (2020). "Selective Review of Offline Change Point Detection Methods." *Signal Processing*, 167, 107299.

---

## 10. Epidemiological Modeling

### 10.1 SIR Compartmental Models for Convention Propagation
**Discipline**: Mathematical Epidemiology
**Purpose**: Model how coding conventions (naming patterns, architectural choices, configuration styles) spread across projects, using the SIR (Susceptible-Infected-Recovered) framework.
**Implementation**: Track convention adoption timestamps across projects. Fit logistic growth curves. Estimate basic reproduction number R₀. Classify transmission mechanisms (active copy-paste vs. independent emergence).
**Key finding (original corpus)**: SSH_AUTH_SOCK fastest adopter (R₀=1.56, 3.2 days to 50%); 75% active transmission, 25% independent emergence.
**Limitation**: 6–7 data points per convention — far too few for reliable parameter estimation; mass-action assumption violated when one human is the sole transmission vector.

**References**:
- Kermack, W.O. & McKendrick, A.G. (1927). "A Contribution to the Mathematical Theory of Epidemics." *Proceedings of the Royal Society A*, 115(772), 700–721.
- Anderson, R.M. & May, R.M. (1991). *Infectious Diseases of Humans: Dynamics and Control*. Oxford University Press.

---

## 11. Temporal Event Analysis

### 11.1 Burstiness and Hawkes-Inspired Excitation
**Discipline**: Statistical Physics / Point Process Theory
**Purpose**: Measure whether events (corrections, tool failures, edits) arrive in bursts or regularly, and whether one event type excites another.
**Implementation**: Compute Barabási burstiness coefficient B ∈ [-1, 1] (B>0 = bursty, B≈0 = Poisson, B<0 = regular). Memory coefficient M for autocorrelation. Hawkes-inspired excitation ratios at multiple lags.
**Key finding (original corpus)**: Edit burstiness highest (B=0.265); correction self-excitation 23.4x at lag 1; editing inhibits corrections ("safe zone").

**References**:
- Barabási, A.-L. (2005). "The Origin of Bursts and Heavy Tails in Human Dynamics." *Nature*, 435, 207–211.
- Goh, K.-I. & Barabási, A.-L. (2008). "Burstiness and Memory in Complex Systems." *EPL*, 81(4), 48002.
- Hawkes, A.G. (1971). "Spectra of Some Self-Exciting and Mutually Exciting Point Processes." *Biometrika*, 58(1), 83–90.

---

## 12. Network Analysis

### 12.1 Cross-Project Knowledge Graphs (HITS Algorithm)
**Discipline**: Network Science / Webometrics
**Purpose**: Map knowledge flows between projects. Identify which projects are "authorities" (knowledge sinks) and which are "hubs" (knowledge sources) using Kleinberg's HITS algorithm.
**Implementation**: Parse cross-project references from session content. Build directed graph. Compute HITS authority and hub scores. Analyze flow directionality.
**Key finding (original corpus)**: Knowledge flows new-to-old at 13.9:1 ratio; hub-and-spoke topology with boucle as primary authority.

**References**:
- Kleinberg, J.M. (1999). "Authoritative Sources in a Hyperlinked Environment." *JACM*, 46(5), 604–632.
- Newman, M.E.J. (2018). *Networks* (2nd ed.). Oxford University Press.

### 12.2 Epistemic Network Analysis (ENA)
**Discipline**: Learning Sciences / Education Research
**Purpose**: Model co-occurrence of epistemic codes (planning, debugging, verification, collaboration) within sliding windows. Compare network structures between successful and struggling sessions.
**Implementation**: Code events with epistemic categories. Build co-occurrence matrices within sliding windows. Compute network centrality and density. Compare session types via network topology.
**Key finding (original corpus)**: VERIFICATION is universal hub; struggling sessions show 12x more COLLABORATION per turn.
**Limitation**: Keyword-based coding is noisy; COLLABORATION triggered by "you"/"we" in every turn, making the 12x finding likely tautological.

**References**:
- Shaffer, D.W. et al. (2016). "A Tutorial on Epistemic Network Analysis: Analyzing the Structure of Connections in Cognitive, Social, and Interaction Data." *Journal of Learning Analytics*, 3(3), 9–45.
- Shaffer, D.W. (2017). *Quantitative Ethnography*. Cathcart Press.

---

## 13. User Behavior Classification

### 13.1 User Signal Analysis
**Discipline**: Conversation Analysis / Human-Computer Interaction
**Purpose**: Classify user messages into semantic categories (correction, approval, scope constraint, frustration, delegation) to characterize interaction dynamics.
**Implementation**: Regex-based and heuristic classification of user messages. Compute per-project and per-session correction rates, frustration prevalence, steering behavior taxonomy.
**Key metric**: Correction rate as maturity indicator — drops from 48% (early projects) to 0.4% (mature projects).
**Limitation**: No labeled validation set; sampling biased toward largest files per project; doc/script mismatches in implementation.

**References**:
- Schegloff, E.A. (2007). *Sequence Organization in Interaction*. Cambridge University Press.
- Bunt, H. (2011). "Multifunctionality in Dialogue." *Computer Speech & Language*, 25(2), 222–245.

---

## 14. Meta-Analytical Methods

### 14.1 Multi-Model Peer Review (Refinery Synthesis)
**Discipline**: Meta-Analysis / Systematic Review
**Purpose**: Have multiple AI models independently analyze the same corpus, then cross-evaluate each other's reports to identify contradictions, unique contributions, and the strongest composite.
**Implementation**: Three model families (Claude, Codex, Gemini) produce independent reports. Each evaluates the others on analytical depth, factual accuracy, novelty, and actionability. Contradictions adjudicated against raw evidence. Borda-style rank aggregation for composite rankings.
**Key contribution**: Separates "winning answer narrative" from "underlying cross-model agreement" — these are related but not identical.

**References**:
- Borenstein, M. et al. (2009). *Introduction to Meta-Analysis*. Wiley.
- Higgins, J.P.T. & Green, S. (eds.) (2011). *Cochrane Handbook for Systematic Reviews of Interventions*. The Cochrane Collaboration.

### 14.2 Methodology Peer Review
**Discipline**: Research Methodology / Philosophy of Science
**Purpose**: Independent evaluation of each analytical method's soundness, implementation quality, statistical rigor, and findings validity.
**Implementation**: Distribute experiments across three model families for blind review. Each reviewer reads both the experiment documentation and the implementation script. Grades A–F with specific findings on bugs, assumption violations, and doc/script mismatches.
**Key cross-cutting finding**: No experiment used frozen corpus snapshots (results drift on rerun); each experiment defines "correction" differently, making cross-experiment claims invalid; no experiment applies multiple comparison corrections.

**References**:
- Ioannidis, J.P.A. (2005). "Why Most Published Research Findings Are False." *PLoS Medicine*, 2(8), e124.
- Gelman, A. & Loken, E. (2014). "The Statistical Crisis in Science." *American Scientist*, 102(6), 460–465.

---

---

## 15. Hidden State Models

### 15.1 Hidden Semi-Markov Model (HSMM) for Behavioral States
**Discipline**: Machine Learning / Stochastic Processes
**Purpose**: Model agent behavior as transitions between hidden states (e.g. "exploring", "executing", "stuck", "recovering") with explicit duration distributions. Unlike standard HMMs, HSMMs capture how long the agent stays in each state, not just which state follows which.
**Implementation**: Encode each turn as a feature vector: tool type (one-hot), message length bucket, thinking block presence, correction indicator. Fit GaussianHMM via `hmmlearn`. Decode most likely state sequences with Viterbi algorithm. Analyze state transition matrices, mean state durations, and which states precede corrections.
**Novel contribution**: First application of duration-aware hidden state modeling to coding agent interaction data.

**References**:
- Rabiner, L.R. (1989). "A Tutorial on Hidden Markov Models and Selected Applications in Speech Recognition." *Proceedings of the IEEE*, 77(2), 257–286.
- Yu, S.-Z. (2010). "Hidden Semi-Markov Models." *Artificial Intelligence*, 174(2), 215–243.
- Pedregosa, F. et al. (2011). "Scikit-learn: Machine Learning in Python." *JMLR*, 12, 2825–2830.

---

## 16. Causal Inference

### 16.1 Granger Causality Analysis
**Discipline**: Econometrics / Time Series Analysis
**Purpose**: Test whether one behavioral time series (e.g. thinking block length) "Granger-causes" another (e.g. correction probability) — i.e., whether past values of X improve prediction of Y beyond Y's own history. Establishes temporal precedence, not true causation, but identifies directional predictive relationships.
**Implementation**: Create per-session time series: thinking ratio, tool diversity, message length, correction indicator, tool failure indicator. Apply `statsmodels.tsa.stattools.grangercausalitytests` at lags 1–5. Bonferroni correction for multiple comparisons across all pairwise tests.
**Key question**: Does thinking block activity predict (and potentially prevent) corrections? Does tool failure predict human frustration?

**References**:
- Granger, C.W.J. (1969). "Investigating Causal Relations by Econometric Models and Cross-Spectral Methods." *Econometrica*, 37(3), 424–438.
- Toda, H.Y. & Yamamoto, T. (1995). "Statistical Inference in Vector Autoregressions with Possibly Integrated Processes." *Journal of Econometrics*, 66(1–2), 225–250.
- Shojaie, A. & Fox, E.B. (2022). "Granger Causality: A Review and Recent Advances." *Annual Review of Statistics and Its Application*, 9, 289–319.

---

## 17. Temporal Pattern Detection

### 17.1 T-Pattern Detection (THEME Algorithm)
**Discipline**: Ethology / Behavioral Science
**Purpose**: Detect temporal patterns (T-patterns) — recurring sequences of events that happen at statistically consistent time intervals, even with other events interspersed. Originally developed by Magnus Magnusson for animal behavior, applied here to human-agent interaction sequences.
**Implementation**: Code events by type (tool calls, user messages by category, thinking blocks). For each pair (A, B), test whether B follows A within a critical interval more often than chance. Build hierarchical T-patterns: if (A,B) is significant and (AB,C) also qualifies, that forms a level-2 T-pattern. Significance via permutation testing (shuffle timestamps within sessions).
**Novel contribution**: First application of T-pattern detection to AI agent session transcripts.

**References**:
- Magnusson, M.S. (2000). "Discovering Hidden Time Patterns in Behavior: T-Patterns and Their Detection." *Behavior Research Methods, Instruments, & Computers*, 32(1), 93–110.
- Casarrubea, M. et al. (2015). "T-Pattern Analysis for the Study of Temporal Structure of Animal and Human Behavior: A Comprehensive Review." *Journal of Neuroscience Methods*, 239, 34–46.
- Magnusson, M.S. (2020). "T-Pattern Detection and Analysis (TPA) With THEME: A Mixed Methods Approach." *Frontiers in Psychology*, 10, 2663.

---

## 18. Information-Theoretic Anomaly Detection

### 18.1 Entropy Rate Anomaly Detection
**Discipline**: Information Theory / Anomaly Detection
**Purpose**: Measure the predictability of agent behavior over time. Compute the entropy rate of tool-call sequences and detect anomalous segments where behavior becomes unusually unpredictable (high entropy = thrashing) or rigid (low entropy = stuck in a loop).
**Implementation**: Encode tool calls as symbols. Compute sliding-window conditional entropy: H(X_n | X_{n-1}, ..., X_{n-k}) for k=1,2,3. Flag anomalous windows exceeding mean ± 2σ. Correlate entropy anomalies with corrections, tool failures, and change points. Compare entropy profiles across projects and session types.
**Key question**: Can entropy spikes predict imminent corrections before they happen?

**References**:
- Cover, T.M. & Thomas, J.A. (2006). *Elements of Information Theory* (2nd ed.). Wiley. Ch. 4 (Entropy Rates).
- Chandola, V., Banerjee, A. & Kumar, V. (2009). "Anomaly Detection: A Survey." *ACM Computing Surveys*, 41(3), 1–58.
- Kontoyiannis, I. et al. (1998). "Nonparametric Entropy Estimation for Stationary Processes and Random Fields." *IEEE Transactions on Information Theory*, 44(3), 1319–1327.

---

## 19. Sequential Pattern Mining

### 19.1 PrefixSpan Frequent Subsequence Mining
**Discipline**: Data Mining / Knowledge Discovery
**Purpose**: Discover frequent sequential patterns in tool usage — ordered subsequences that appear across many sessions, allowing gaps. Unlike Markov chains (adjacent transitions only), PrefixSpan finds patterns like "Read → [gap] → Edit → [gap] → Bash → [gap] → Read" spanning multiple steps.
**Implementation**: Encode each session as a sequence of tool-call types. Run PrefixSpan with minimum support threshold (e.g. 10% of sessions). Filter for patterns of length 3–8. Correlate pattern presence with session success/correction rates. Compare pattern frequency across projects.
**Advantage over Markov analysis**: Captures long-range dependencies and tolerates intervening events.

**References**:
- Pei, J. et al. (2004). "Mining Sequential Patterns by Pattern-Growth: The PrefixSpan Approach." *IEEE TKDE*, 16(11), 1424–1440.
- Han, J., Pei, J. & Yin, Y. (2000). "Mining Frequent Patterns without Candidate Generation." *ACM SIGMOD Record*, 29(2), 1–12.
- Fournier-Viger, P. et al. (2017). "A Survey of Sequential Pattern Mining." *Data Science and Pattern Recognition*, 1(1), 54–77.

---

## 20. Optimal Foraging Theory

### 20.1 Information Foraging Analysis
**Discipline**: Cognitive Science / Human-Computer Interaction
**Purpose**: Model agent behavior as information foraging — treating code exploration as analogous to animals foraging for food. Test whether agents follow the marginal value theorem: leaving a "patch" (file/directory) when returns diminish below the environment average.
**Implementation**: Define "patches" as directories or files the agent reads/edits. Measure patch residence time (turns), gain from patch (edits made), switching cost (tools between patches). Test marginal value theorem: does the agent leave when marginal gain drops below average? Compute diet breadth index, giving-up time distribution.
**Key question**: Are agents efficient foragers, or do they over-stay in familiar patches and under-explore?

**References**:
- Pirolli, P. & Card, S. (1999). "Information Foraging." *Psychological Review*, 106(4), 643–675.
- Charnov, E.L. (1976). "Optimal Foraging, the Marginal Value Theorem." *Theoretical Population Biology*, 9(2), 129–136.
- Pirolli, P. (2007). *Information Foraging Theory: Adaptive Interaction with Information*. Oxford University Press.
- Fu, W.-T. & Pirolli, P. (2007). "SNIF-ACT: A Cognitive Model of User Navigation on the World Wide Web." *Human-Computer Interaction*, 22(4), 355–412.

---

*Catalog compiled for the Lightless Labs "Third Thoughts" project. 20 method families, 28 implementations, spanning computational linguistics, biostatistics, behavioral psychology, epidemiology, ecology, bioinformatics, information theory, network science, process mining, industrial engineering, learning sciences, meta-analysis, stochastic processes, econometrics, ethology, anomaly detection, data mining, and cognitive science.*
