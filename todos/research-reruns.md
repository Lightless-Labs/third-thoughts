# Research Reruns

Rerun contaminated analyses with the validated correction classifier on interactive-only sessions.

## Context
The structural correction classifier (`scripts/correction_classifier.py`, 98% accuracy) was built to replace the regex approach (90% false positive rate on subagent sessions). These three analyses were run before the classifier existed and need re-validation.

## Tasks
- [ ] **Granger causality on interactive-only.** Modify `scripts/granger_causality.py` to use the structural classifier. Run on `corpus-split/interactive/`. Resolves whether thinking actually Granger-causes fewer corrections
- [ ] **Survival analysis on interactive-only.** Modify `scripts/survival_analysis.py` to use the structural classifier. Determines if the thinking-block protective effect is real (HR=0.663, p=0.40 on first run) or an artifact
- [ ] **Process mining on interactive-only.** Modify `scripts/014_process_mining.py` to use the structural classifier. Validates "7x more thinking in low-correction sessions"

## Expected Outcomes
- If findings hold on interactive-only with corrected classifier → upgrade from "retracted" to "validated on interactive"
- If findings don't hold → confirm retraction, update report
- Either way, update `docs/reports/third-thoughts-full-corpus-report.md` with results
