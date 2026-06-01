# Public comparative interpretation v1

You are writing a public cross-corpus interpretation for selected `middens` public results.

Use **only** the curated comparative evidence JSON below. Do not use raw transcripts, per-session rows, source paths, project names, session ids, or outside knowledge.

## Required structure

Write Markdown with these headings:

1. `## Cross-corpus summary`
2. `## Replicated or directionally consistent patterns`
3. `## Variable, provisional, or not tested`
4. `## Coverage gaps`
5. `## Suggested public wording`

## Rules

- Cite exact corpus counts, per-corpus session totals, per-corpus split counts (`interactive`, `subagent`, `autonomous`), metric ranges, and classification inputs when making claims.
- Treat duplicate-shaped corpus families as warnings, not independent replications.
- Do not pool corpora into one scientific headline unless the evidence explicitly supports it.
- Call out missing axes: autonomous session coverage, language detection, and thinking-visibility stratification.
- Distinguish robust, directionally consistent, magnitude-variable, contradicted, `0`, `undefined`, `redacted`, missing, and not-tested cases.
- Do not make autonomous-loop behavior claims from empty or tiny autonomous strata.
- Do not quote transcripts or mention raw paths, session ids, prompts, assistant messages, thinking text, or tool payloads.
- Prefer plain, slightly wry language over research fog-machine prose.

## Comparative evidence JSON

```json
{{EVIDENCE_JSON}}
```
