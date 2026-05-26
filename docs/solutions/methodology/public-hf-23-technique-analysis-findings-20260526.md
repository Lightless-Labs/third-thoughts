---
title: "Public Hugging Face 23-technique analysis findings"
module: third-thoughts
date: 2026-05-26
problem_type: methodology
component: public-corpus-analysis
severity: medium
status: completed
tags:
  - huggingface
  - public-datasets
  - 23-techniques
  - middens
  - stratification
---

# Public Hugging Face 23-technique analysis findings

## Context

The earlier public-HF write-ups over-focused on HSMM because that was the immediate replication task. User correctly called out the obvious: `middens` has 23 techniques, not one slightly fussy HMM wearing a lab coat.

So this pass ran the full 23-technique battery, up to export and excluding LLM interpretation, on the public HF corpora currently selected for CI coverage.

Artifacts are local/gitignored under `.tmp/`:

- materialized corpora: `.tmp/hf-full/` plus the smoke corpus under `.tmp/hf-ci-smoke/`;
- flat technique outputs: `.tmp/middens-full/` plus `.tmp/middens-ci-smoke/`;
- storage manifests/parquet: `.tmp/xdg-full/` plus `.tmp/xdg-ci-smoke/`;
- notebooks: `.tmp/reports-full/` plus `.tmp/reports-ci-smoke/`.

No transcript snippets are included here.

## Corpora run

| Corpus id | Sessions parsed | Techniques completed | Export |
|---|---:|---:|---|
| `agent-sessions-list-mixed` | 7 | 23/23 | pass |
| `badlogicgames-pi-mono` | 626 | 23/23 | pass |
| `thomasmustier-pi-for-excel` | 161 | 23/23 | pass |
| `aaaaliou-pi-mono` | 145 | 23/23 | pass |
| `kimi-claude-code-traces-jsonl` | 36 | 23/23 | pass |

The smoke corpus is too small for several techniques to produce inferential results; it is still useful as a parser/CI end-to-end check.

## Cross-corpus metrics

| Corpus | Correction mean | Sessions with corrections | Thinking risk suppression | Mean tool entropy | Burstiness | MVT compliance | HSMM lift |
|---|---:|---:|---:|---:|---:|---:|---:|
| `agent-sessions-list-mixed` | 0.161 | 3/7 | 98.24% | 0.318 | 0.391 | 0% | insufficient |
| `badlogicgames-pi-mono` | 0.214 | 325/626 | 91.18% | 0.605 | 0.386 | 0% | 3.56× |
| `thomasmustier-pi-for-excel` | 0.132 | 99/161 | 95.44% | 0.897 | 0.481 | 0% | 9.44× |
| `aaaaliou-pi-mono` | 0.178 | 67/145 | 94.78% | 0.893 | 0.427 | 0% | 6.17× |
| `kimi-claude-code-traces-jsonl` | 0.0048 | 4/36 | 100.00% | 1.256 | 0.342 | 0% | 1.89× |

## What surfaced beyond HSMM

### 1. Risk suppression still appears across public visible-thinking corpora

Thinking-divergence reported high risk-token suppression everywhere it had usable thinking content:

- `badlogicgames-pi-mono`: 91.18% suppressed, 8,575 risk tokens.
- `thomasmustier-pi-for-excel`: 95.44% suppressed, 9,315 risk tokens.
- `aaaaliou-pi-mono`: 94.78% suppressed, 1,359 risk tokens.
- `agent-sessions-list-mixed`: 98.24% suppressed, 170 risk tokens.
- `kimi-claude-code-traces-jsonl`: 100%, but with zero paired thinking/text messages and divergence ratio 0.0, so this is not directly comparable to Pi visible-thinking logs.

This is directionally consistent with the main private-corpus finding, but the public HF corpora need the same scoping discipline: session type, thinking visibility, language, source/tool family, and temporal window.

### 2. MVT compliance is 0% in every public corpus run

Information-foraging reported `mvt_compliance_rate=0.0` for all five corpora. That reproduces the qualitative MVT violation on public data: agents still do not look like optimal patch-leavers.

The *shape* differs by source:

- `kimi-claude-code-traces-jsonl`: high foraging efficiency (0.513) and very high patch revisit (0.864), with only 36 sessions.
- `thomasmustier-pi-for-excel`: many patches per session (18.18), patch revisit 0.564, efficiency 0.157.
- `badlogicgames-pi-mono`: fewer patches (3.56), lower efficiency 0.099.
- `aaaaliou-pi-mono`: efficiency 0.054.

So the headline is not “same foraging behavior everywhere”; it is “same failure to satisfy MVT, different local ecology.”

### 3. Corrections front-load again, except the tiny/special cases are noisy

Correction-rate and survival analysis both point to early corrections on the larger Pi corpora:

| Corpus | First-third correction rate | Last-third correction rate | Median survival turns |
|---|---:|---:|---:|
| `badlogicgames-pi-mono` | 0.292 | 0.077 | 3 |
| `thomasmustier-pi-for-excel` | 0.140 | 0.110 | 4 |
| `aaaaliou-pi-mono` | 0.200 | 0.141 | 3 |
| `kimi-claude-code-traces-jsonl` | 0.011 | 0.000 | no median reached |
| `agent-sessions-list-mixed` | 0.157 | 0.013 | insufficient survival data |

This is consistent with “users correct early / sessions get on track / or users stop correcting,” not the naive “agent gets worse within a session” story.

### 4. Source family changes the behavioural center of gravity

The Pi corpora look tool-use centered. ENA top code:

- `badlogicgames-pi-mono`: `TOOL_USE`
- `thomasmustier-pi-for-excel`: `TOOL_USE`
- `aaaaliou-pi-mono`: `TOOL_USE`

The Kimi/Claude-Code-style trace corpus differs:

- `kimi-claude-code-traces-jsonl`: `SELF_CORRECT`

That is exactly why per-source reporting matters. The Kimi corpus also has much lower correction rate (0.0048), higher mean tool entropy (1.256), and different Granger/lag-sequential signatures.

### 5. Granger relationships differ by corpus, not just magnitude

Strongest Granger pair by corpus:

| Corpus | Strongest pair | Significant pairs |
|---|---|---:|
| `badlogicgames-pi-mono` | `correction_indicator -> thinking_ratio` | 9 |
| `aaaaliou-pi-mono` | `correction_indicator -> thinking_ratio` | 8 |
| `thomasmustier-pi-for-excel` | `message_length -> thinking_ratio` | 12 |
| `kimi-claude-code-traces-jsonl` | `tool_diversity -> message_length` | 3 |
| `agent-sessions-list-mixed` | `message_length -> tool_diversity` | 1, tiny n |

This is useful: public corpora do not just rescale the same dynamic; they expose different candidate mechanisms.

### 6. Sequential-pattern techniques find strong repetition everywhere, but the motifs vary

Examples:

- `badlogicgames-pi-mono`: lag-sequential top transition `AT→AT` (lag 1, z=51.5); T-pattern top `AT->AT`; PrefixSpan 98 patterns.
- `thomasmustier-pi-for-excel`: `AT→AT` even stronger (lag 1, z=121.0); PrefixSpan 97 patterns; 20 level-2 T-patterns.
- `aaaaliou-pi-mono`: `AK→AK` (lag 2, z=32.0); PrefixSpan 144 patterns.
- `kimi-claude-code-traces-jsonl`: `AK→UR` (lag 3, z=65.6); PrefixSpan 174 patterns despite only 36 sessions.

The commonality is not a specific motif. The commonality is strong local sequential regularity — agents get into grooves, and some grooves are source/tool specific.

### 7. Tool diversity separates the corpora more than burstiness does

Burstiness is mild everywhere (0.34–0.48), but entropy varies:

- `agent-sessions-list-mixed`: 0.318 mean Shannon entropy, tiny mixed corpus and many monoculture-ish sessions.
- `badlogicgames-pi-mono`: 0.605.
- `aaaaliou-pi-mono`: 0.893.
- `thomasmustier-pi-for-excel`: 0.897.
- `kimi-claude-code-traces-jsonl`: 1.256.

Kimi is the most diverse by tool entropy; `badlogicgames/pi-mono` is materially narrower than the other Pi corpora in this run.

### 8. Change-point detection found nothing on these public corpora

All five runs reported zero total change points. This may be a real “no abrupt within-corpus shift” result, or it may mean these public corpora are not the right temporal granularity for change-point analysis. Either way: no public-HF change-point headline here.

### 9. Cross-project graph is not useful on these selected corpora yet

`cross-project-graph` was insufficient across the runs: one project or no cross-project references. Even `thomasmustier-pi-for-excel`, where convention epidemiology detected 5 projects, did not produce cross-project reference edges. This technique needs a different public corpus selection or explicit multi-project datasets.

### 10. Convention epidemiology has one decent public target

`thomasmustier-pi-for-excel` is the only selected corpus with enough internal project spread to say something more interesting here:

- 5 projects detected.
- 16 conventions detected and fitted.
- top convention: `write→read`.
- summary notes cross-project propagation for `bash→bash`.

Other selected corpora are mostly one-project or too small, so convention results should stay per-corpus and descriptive.

## Methodological notes

- Full `middens analyze --all` and `middens export --no-interpretation` completed for every selected CI corpus.
- These are not LLM-synthesized reports; this summary is manually extracted from manifests and flat technique outputs.
- The smoke corpus is included for completeness, but not as inference evidence.
- HSMM values here are from the full `middens analyze --all` runs. They can differ from standalone HSMM reruns because the model fit/model-selection path is sensitive enough that we should treat exact lift as unstable. That supports, rather than weakens, the current “direction replicated, magnitude unstable” status.

## Bottom line

The public HF full-battery runs surface more than HSMM:

1. risk suppression is visible in public Pi corpora;
2. MVT non-compliance is universal across selected public corpora;
3. corrections front-load on the larger Pi corpora;
4. source family materially changes ENA, Granger, entropy, and sequence motifs;
5. cross-project and change-point techniques need more suitable public corpora before they can carry findings.

The next reporting shape should be per-corpus dashboards/tables, not one blended report. Mixed public corpora would hide the interesting part, which is that the mechanisms differ while some broad regularities survive.
