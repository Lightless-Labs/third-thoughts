---
technique: thinking-divergence
corpus_size: 3
generated_at: "2026-04-10T05:54:03.369598+00:00"
middens_version: "0.1.0"
---

# thinking-divergence

Analyzed 2 sessions with thinking blocks. Average risk suppression rate: 0.00%. Overall thinking-to-text divergence ratio: 1.64. (analyzed 1 visible + 1 unknown-visibility sessions with thinking; 0 skipped as thinking-redacted)

## Findings

| Finding | Value | Description |
|---------|-------|-------------|
| suppression_rate | 0 | Ratio of risk tokens in thinking absent from text |
| divergence_ratio | 1.6447 | Total thinking characters / total text characters |
| sessions_with_thinking | 2 | Count of sessions containing at least one thinking block |
| messages_with_both | 2 | Assistant messages containing both thinking and text |
| total_risk_tokens | 0 | Total instances of risk tokens found in thinking blocks |
| suppressed_tokens | 0 | Total risk tokens found in thinking but absent from text |
| sessions_analyzed | 2 | Total sessions with thinking blocks analyzed |
| skipped_redacted_sessions | 0 | Sessions skipped because thinking was redacted from transcript (post redact-thinking-2026-02-12 header) |
| analyzed_visible_sessions | 1 | Analyzed sessions whose thinking_visibility is Visible |
| analyzed_unknown_sessions | 1 | Analyzed sessions whose thinking_visibility is Unknown (parser could not determine visibility; included in the analyzed cohort but not guaranteed to be pre-redaction) |

## per_session

| session_id | suppression_rate | divergence_ratio | thinking_length | text_length | risk_tokens | suppressed_tokens |
|------------|------------------|------------------|-----------------|-------------|-------------|-------------------|
| test-openclaw-session-001 | 0 | 1.0391 | 133 | 128 |  |  |
| test-session-001 | 0 | 2.7681 | 191 | 69 |  |  |

