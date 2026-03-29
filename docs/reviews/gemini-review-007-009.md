# Peer Review: Experiments 007-009

This report provides a rigorous peer review of Experiments 007, 008, and 009 within the `agentic-engineering-sawdust` project.

---

## 1. Experiment 007: Cross-Project Knowledge Flow Graph

**Doc**: `experiments/007-cross-project-graph.md`  
**Script**: `scripts/007-cross-project-graph.py`

### Methodology Soundness
The methodology is sound for the stated exploratory goal. Graph analysis (network science) is the correct tool for understanding "knowledge flow" and "inter-project dependencies". The use of Hub/Authority scoring (in-degree/out-degree) is appropriate for identifying central projects. The classification of reference types into categories like `implementation`, `context_import`, and `knowledge_sharing` adds valuable qualitative depth to the quantitative graph metrics.

### Implementation Quality
The Python script is well-structured and handles the complexities of project-name ambiguity (e.g., "converge") through targeted regex patterns and canonicalization mappings. The extraction of user message context is robust, including a fallback for missing timestamps. The script generates both a detailed markdown report and a Graphviz DOT file for visualization, which is excellent for reproducibility.

### Statistical Rigor
The experiment is primarily descriptive. While the documentation contains a boilerplate note about "statistical tests" and "p-values," the script itself implements no formal hypothesis testing or null models (e.g., it does not test if the observed hub-and-spoke topology is significantly different from a random graph with the same degree distribution). The "13.9x new-to-old" ratio is a simple, un-adjusted descriptive statistic. Given the exploratory nature, this is acceptable, but the boilerplate disclaimer about "p-values" is misleading as none are actually reported.

### Findings Validity
The findings are robust as a summary of the provided corpus. The dominance of `autonomous-sandbox` (91.6% of references) is correctly identified as a scale artifact and separated from the more "human-scale" knowledge graph. The finding that the "Human is the Router" (55% bare mentions) is a critical insight into the current state of agentic autonomy.

### Limitations
- **Boilerplate inaccuracy**: The doc refers to p-values and statistical tests not present in the script.
- **Regex limitations**: Classification depends on keyword heuristics which may miscategorize nuanced dialogue.
- **Single-user bias**: Acknowledged in the report; findings reflect the specific workflow of one developer.

**Overall Grade: B+**

---

## 2. Experiment 008: Brainstormed Approaches from Other Models

**Doc**: `experiments/008-brainstormed-approaches.md`  
**Script**: *Not provided (Command-line based)*

### Methodology Soundness
The use of high-performing "frontier" models (Codex/GPT-5.4 and Gemini) to generate novel analysis methodologies is an effective meta-research technique. It mitigates "methodological monoculture" by leveraging the broad training data of these models. The categorization into workflow, temporal, and structural lenses is logically sound.

### Implementation Quality
The prompt engineering is of high quality. It provides necessary context (corpus size, features, previous methods) and constraints (10 concrete, diverse approaches). The inclusion of specific execution commands (using `codex exec`) demonstrates a controlled, reproducible environment for the brainstorming session. The synthesis of a "Combined Priority List" shows good editorial judgment.

### Statistical Rigor
Not applicable (qualitative brainstorming).

### Findings Validity
The validity lies in the *utility* of the suggestions. Many of the suggested methods (Process Mining, Change-Point Detection, Survival Analysis) were subsequently implemented in the project, demonstrating that the brainstorming produced actionable and relevant research directions.

### Limitations
- **Absence of script**: No Python script was provided for review, though the `codex` command is documented.
- **Hallucination Risk**: Brainstorming models can suggest overly complex or non-existent tools/methods, though the ones selected here (pm4py, ruptures, lifelines) are real and appropriate.

**Overall Grade: A-**

---

## 3. Experiment 009: External Research via Perplexity & Linkup APIs

**Doc**: `experiments/009-perplexity-linkup-research.md`  
**Script**: *Not provided (API-based research)*

### Methodology Soundness
The methodology is excellent for identifying prior art in a rapidly evolving field (2024-2026). Grounding the research in web-search APIs (Perplexity/Linkup) ensures the project is not working in a vacuum. The focus on "novel academic approaches" and "reasoning trace analysis" targets the most relevant gaps in the project's current understanding.

### Implementation Quality
The search queries are specific and well-targeted. The report does a great job of distilling "What's Novel for Us" from each search result, translating academic findings (like "hashing ablation" or "Good-Turing estimation") into concrete project tasks. The inclusion of source URLs adds transparency and verifiability.

### Statistical Rigor
Not applicable.

### Findings Validity
The findings are highly valid as they identify real (or realistically projected) academic work and tools. The identification of Anthropic's "AI Fluency Index" as a benchmark is particularly valuable for calibrating the project's results against industry standards.

### Limitations
- **No implementation script**: The "script" mentioned in the prompt was not found; however, the research report is comprehensive.
- **Temporal Horizon**: The research refers to papers from 2026; while consistent with the session date, it limits external verification of the specific arXiv citations mentioned.

**Overall Grade: A-**
