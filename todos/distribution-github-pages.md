---
title: "GitHub Pages landing page on www branch"
status: in-progress
priority: P2
tags: [distribution, website, workstream-3]
source: user-direction-2026-04-10
---

## Status

**Initial cut shipped 2026-04-18.** Live at <https://lightless-labs.github.io/third-thoughts/>.

- `www` orphan branch created, Pages configured to serve from branch root.
- Three pages: `index.html` (pitch), `findings.html` (six scoped findings with tags), `report.html` (long-form distilled report).
- Copy drafted by codex 5.4 xhigh, revised by Claude. Gemini 3.1 Pro review **skipped** (Gemini retired from our review loop mid-project).
- Numbers cited as measured: 99.99% risk suppression (N=4,518), HSMM 2.15x (down from provisional 24.6x), MVT 0% compliance. One finding (thinking-blocks-prevent-corrections) explicitly retracted.

## Follow-ups (not blocking)

1. **Install story for homebrew** — `brew install lightless-labs/tap/middens` not yet live. The index currently points at the Releases tarball. Update once the tap ships.
2. **Embedded validation reports** — the source-built vs homebrew-installed run comparison (distribution-validation-runs.md) is still deferred. Fold in when the tap lands.
3. **Third-party contribution surface** — no "where help is welcome" section yet. Add once we're actually set up to absorb PRs from outside contributors (parsers, non-English support).
4. **Second reviewer for copy** — with Gemini out of the loop, consider a Kimi K2.5 pass via OpenCode if we want independent copy review before the next big rewrite.
5. **Roadmap teaser** — v2/v3/v4 roadmap items (TUI, risk surfacer, federated learning) are not yet on the site. Add when they're closer to real.

## Technical (as shipped)

- `www` branch, orphan, contains only site files (no source code).
- Lives in a sibling worktree at `../third-thoughts-www/`.
- GitHub Pages serves from `www` branch root. `.nojekyll` present to disable Jekyll processing.
- Static HTML/CSS, no build step, no JS framework. One `style.css` shared across pages.
