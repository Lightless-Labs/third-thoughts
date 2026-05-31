# Public corpus interpretation v1

You are writing a short public interpretation for one `middens` corpus result page.

Use **only** the curated evidence JSON below. Do not infer from raw transcripts, source paths, project names, session ids, or any outside corpus knowledge.

## Required structure

Write Markdown with these headings:

1. `## Summary`
2. `## What is actually measured`
3. `## Caveats before anyone gets excited`
4. `## Suggested public wording`

## Rules

- Cite exact metric values when making a claim.
- State total parsed sessions and split counts for `interactive`, `subagent`, and `autonomous`.
- Distinguish `0`, `undefined`, `redacted`, and missing values.
- If total sessions are fewer than 30, say this is smoke-test evidence only.
- If autonomous sessions are 0 or tiny, do not make autonomous-loop behaviour claims.
- Mention that language detection and full thinking-visibility stratification are not yet available unless the evidence says otherwise.
- Do not pool this corpus with duplicate-shaped corpora or call it an independent replication without deduplication evidence.
- Do not quote transcripts. Do not mention raw file paths, local paths, session ids, prompts, assistant messages, thinking text, or tool payloads.
- Prefer honest, plain language over grand claims. A little dry humour is fine; pompous fog machine is not.

## Evidence JSON

```json
{{EVIDENCE_JSON}}
```
