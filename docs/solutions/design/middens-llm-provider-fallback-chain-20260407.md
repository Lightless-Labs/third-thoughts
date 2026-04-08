---
module: middens
date: 2026-04-07
problem_type: best_practice
component: tooling
severity: medium
tags: [cli-design, middens, interpret, llm-providers, fallback]
applies_when:
  - running middens interpret without an explicit provider flag
  - designing resilient LLM-dependent CLI commands
  - deciding provider preference order for interpretation
---

# Middens interpret: the Claude Code → Codex → Gemini fallback chain

## Context

`middens interpret` runs an LLM over a stored `TechniqueResult`
bundle to produce a narrative interpretation. The user almost
always wants it to "just work" without specifying a provider, but
any single provider can be down, rate-limited, unauthenticated on
this machine, or missing a required binary. Hard-coding one
provider turns a transient outage into a hard failure.

## Guidance

Default behavior when no `--provider` flag is given: try providers
in order, stop at the first one that succeeds.

    1. Claude Code   (claude subagent or CLI; native for this project)
    2. Codex CLI     (codex exec --skip-git-repo-check --full-auto)
    3. Gemini CLI    (gemini -y -s false --prompt ...)

A provider is considered available if its binary is on PATH and a
smoke-test invocation returns without an auth error. Failures at
the auth or binary-missing stage fall through silently to the
next provider. Failures during actual interpretation (timeout,
rate limit, non-zero exit) are surfaced once to the user, then
the chain advances.

The chosen provider is recorded in the interpretation bundle's
metadata so downstream consumers know which model produced the
narrative. The same analysis can be interpreted multiple times
with different providers for cross-model comparison — each run
writes its own `<date>-<slug>-<provider>/` bundle.

`--provider` overrides the chain entirely and fails fast if the
requested provider is unavailable.

## Why This Matters

Interpretation is the user-facing end of the pipeline. If it
fails, the analysis run looks like it failed, even though the
canonical store is intact and only the narrative layer is
missing. The fallback chain turns provider outages from
pipeline-breaking into user-invisible.

The order is deliberate:

- **Claude Code first** because it is the project's native
  environment, usually already authenticated, and produces the
  best results on this corpus (the interpretation prompts were
  tuned against it).
- **Codex second** because it is the next most reliable and
  produces broadly comparable output, with the caveat about the
  10-minute timeout documented in `CLAUDE.md`.
- **Gemini third** because it is the most reliably available
  on shared infrastructure but produces the most variable
  interpretation quality, so it earns the last-resort slot.

Recording the provider in metadata is non-negotiable: a future
reader comparing two interpretation bundles must be able to tell
which model produced which narrative, otherwise cross-bundle
comparisons silently mix providers the same way blended
denominators mix populations.

## When to Apply

- `middens interpret` with no `--provider` flag.
- Any future Middens command that depends on an external LLM.
- Cross-model comparison workflows — explicitly invoke each
  provider with `--provider` rather than relying on the chain.

## Examples

**Default (chain):**

    middens interpret 2026-04-07-batch5-interactive
    # tries claude-code, falls through to codex if unavailable,
    # falls through to gemini if codex also unavailable.

**Explicit (no fallback):**

    middens interpret 2026-04-07-batch5-interactive --provider gemini
    # fails fast if gemini is unavailable.

**Cross-model comparison:**

    for p in claude-code codex gemini; do
        middens interpret 2026-04-07-batch5-interactive --provider "$p"
    done
    # produces three sibling interpretation bundles.

Related:
- `docs/solutions/design/middens-analyze-interpret-export-triad-20260407.md`
- `docs/solutions/design/middens-default-path-scheme-20260407.md`
- `docs/solutions/methodology/multi-model-refinery-synthesis-20260320.md`
