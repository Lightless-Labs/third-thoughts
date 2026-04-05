---
title: "Cross-project claim verification — check sibling projects before accepting capability claims"
date: "2026-04-04"
category: best-practices
module: multi-model-analysis
problem_type: documentation_gap
component: development_workflow
severity: medium
applies_when:
  - "Project docs claim a model or tool lacks a capability"
  - "A model invocation produces no output and no error (silent failure)"
  - "Onboarding a new model into the multi-model delegation workflow"
  - "Encountering 'model X cannot do Y' claims that haven't been recently validated"
tags:
  - cross-project
  - multi-model
  - delegation
  - silent-failure
  - documentation
  - knowledge-management
---

# Cross-project claim verification — check sibling projects before accepting capability claims

## Context

Third Thoughts documented that Kimi K2.5 "has tool-calling issues" and should be avoided for write-heavy tasks. This claim was based on early failed invocations during adversarial development and propagated into CLAUDE.md and the multi-model delegation gotchas solution file.

Meanwhile, the sibling A²D project (skunkworks/a2d-autopoietic-autocatalysis-deutero) independently debugged and solved the same problem. Kimi K2.5 was successfully used as a "coder enzyme" role with validated commits (a5ffb5b, feb5612, 3a0415c). The fix sat undiscovered in the sibling project until a cross-project review surfaced it.

Root causes were configuration errors, not capability limitations:
1. Wrong model ID (`kimi/kimi-k2.5` instead of `kimi-for-coding/k2p5`) — failed silently with no error output
2. Missing `--format json` flag — ANSI escape codes in raw output corrupted code extraction

## Guidance

**When project docs claim a tool or model "cannot" do something, verify against sibling projects before accepting the claim.**

The verification process:
1. Identify sibling projects that use the same tool/model (search the monorepo, check HANDOFF.md files)
2. Look at their session logs, git history, or CLAUDE.md for evidence of successful use
3. If a sibling project solved the problem, extract the exact invocation flags and configuration
4. Update the claiming project's docs with the correction and provenance

For OpenCode models specifically, silent failures from wrong model IDs are a recurring pattern. The model appears to lack capability when it's actually a configuration error. Always verify:
- Correct model ID (check OpenCode docs, not project memory)
- `--format json` for parseable output
- Adequate timeout for slow models

## Why This Matters

**Following this guidance:** Incorrect documentation is caught before it calcifies into institutional folklore. Capable models stay in the delegation roster. Cross-project solutions compound instead of being rediscovered independently.

**Ignoring this guidance:** Silent failures get documented as capability limitations. Each project that encounters the same problem debugs it from scratch. The delegation roster shrinks unnecessarily, forcing more expensive alternatives.

The Kimi claim persisted for multiple sessions. Each session that avoided Kimi for tool-dependent work was an unnecessary constraint based on a configuration error misdiagnosed as a capability gap.

## When to Apply

- When project docs claim a model lacks a capability (tool use, file writes, code generation)
- When a model invocation produces no output and no error — suspect silent model ID failure before concluding incapability
- When onboarding a new model — test with exact invocation flags from working projects, not assumptions from raw API behavior
- When multiple projects in a monorepo use the same external tools — periodically cross-pollinate findings

## Examples

**Wrong — accepting a cross-project claim at face value:**
```
# CLAUDE.md says "Kimi K2.5 has tool-calling issues — avoid for write-heavy tasks"
# -> Skip Kimi for all write-heavy adversarial tasks
# -> Use only Codex (expensive) and Gemini (rate-limited)
# -> Claim persists for weeks, unchallenged
```

**Correct — verifying against sibling projects:**
```
# CLAUDE.md says "Kimi K2.5 has tool-calling issues"
# -> Check: does any sibling project use Kimi successfully?
# -> A²D project (skunkworks/a2d) has 3 validated Kimi commits with tool use
# -> Root cause: wrong model ID + missing --format json
# -> Update docs with correction and A²D provenance
# -> Kimi back in the delegation roster
```

**The silent failure pattern (applies to any OpenCode model):**
```bash
# Looks like model can't do anything — actually wrong model ID
opencode run --model kimi/kimi-k2.5 "implement X"
# -> No output, no error, appears broken

# Correct — working invocation
opencode run --model kimi-for-coding/k2p5 --format json "implement X"
# -> Clean NDJSON output, tools work
```

## Related

- [Practical multi-model delegation gotchas](../workflow-issues/practical-multi-model-delegation-gotchas-20260404.md) — the Kimi-specific correction that prompted this learning
- [Multi-model refinery synthesis](../methodology/multi-model-refinery-synthesis-20260320.md) — earlier multi-model doc that predates the expanded model roster (auto memory [claude]: may need refresh of its Practical Notes section)
