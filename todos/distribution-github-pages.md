---
title: "GitHub Pages landing page on www branch"
status: todo
priority: P1
tags: [distribution, website, workstream-3]
source: user-direction-2026-04-10
---

## What

A GitHub Pages site at the root of a dedicated `www` branch (otherwise empty — no source code). The landing page for the project.

## Content

1. **What it is** — one-paragraph pitch, light register (not research-speak).
2. **Install instructions** — `brew install lightless-labs/tap/middens` front and center.
3. **Two embedded reports** — the exports from the source-built and homebrew-installed validation runs (distribution-validation-runs.md). Show that they match. Real findings from a real corpus.
4. **Key findings** — the headline numbers (100% risk suppression on visible-thinking, HSMM 24.6x lift, MVT violation). Linked to methodology docs.
5. **Current capabilities** — what middens can do today (23 techniques, 4 parsers, Parquet storage, Jupyter export, LLM interpretation).
6. **Known limits** — English-only for text techniques, no Windows, no GUI, Python techniques need uv, thinking-visibility caveat.
7. **Medium-term goals** — the v2/v3/v4 roadmap items (TUI, risk surfacer, federated learning). Frame as distributed effort.
8. **Where third-party help is welcome** — specific areas: new parsers (Cursor, Windsurf), non-English language support, new analytical techniques, federated protocol design.

## Copy review process

Landing page copy MUST be reviewed by:
- **Gemini 3.1 Pro** — grounding check, factual accuracy, superlative detection
- **Codex 5.4 (reasoning: high)** — same pass, independent

Both reviewers tasked with: strip em dashes, kill superlatives, flag ungrounded claims, enforce the light/self-deprecating register from CLAUDE.md conventions. The copy is done when both reviewers have zero P1/P2 findings.

## Technical

- `www` branch, no parent commit (orphan), contains only the site.
- GitHub Pages configured to serve from `www` branch root.
- Static HTML/CSS — no build step, no JS framework. Keep it simple.
- Reports embedded as HTML (rendered from the Jupyter exports via nbconvert or equivalent).
