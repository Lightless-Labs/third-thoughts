---
technique: entropy
corpus_size: 3
generated_at: "2026-04-10T05:54:03.330278+00:00"
middens_version: "0.1.0"
---

# entropy

Analyzed 0 sessions. Mean conditional entropy: 0.0000. Total anomalies: 0 (low: 0, high: 0). Low:high ratio: 0.00.

## Findings

| Finding | Value | Description |
|---------|-------|-------------|
| mean_entropy | 0 | Overall mean conditional entropy H(X_t\|X_{t-1}) across sessions |
| anomaly_count | 0 | Total number of anomalous windows (>2 sigma) |
| low_entropy_anomalies | 0 | Windows with entropy >2 sigma below mean (rigidity) |
| high_entropy_anomalies | 0 | Windows with entropy >2 sigma above mean (chaos) |
| low_high_ratio | 0 | Ratio of low-entropy to high-entropy anomalies |
| sessions_analyzed | 0 | Number of sessions with enough tool calls for analysis |

## per_session_entropy

| session_id | mean_entropy | stddev | num_anomalies |
|------------|--------------|--------|---------------|

