---
title: "Multi-model adversarial process scales to 6-group feature implementation"
date: "2026-04-10"
category: workflow-issues
module: middens-cli
problem_type: workflow_issue
component: development_workflow
severity: medium
applies_when:
  - Implementing non-trivial features that benefit from adversarial red/green team split
  - Orchestrating multiple AI coding agents across different model providers
  - NLSpec has been reviewed and has numbered acceptance scenarios
tags:
  - adversarial-process
  - multi-model
  - red-green-team
  - orchestration
  - gemini
  - glm
  - opencode
  - nlspec
---

## Context

The middens CLI triad (analyze/interpret/export) was implemented as a 6-group feature using the full adversarial process from the foundry methodology. The feature was large enough to require wave-based dispatch of green team agents across work groups A through F.

**Red team:** Gemini 3.1 Pro Preview, dispatched via `/gemini-cli`. Given NLSpec sections 1+2+4 (Why/What/Done) — deliberately NOT section 3 (How). Produced 59 Cucumber scenarios in ~15 minutes. Found 1 contract gap (scenario 53 cross-reference), which is notable given the NLSpec had already been through 4 review passes.

**Green team:** GLM 5.1 via OpenCode (`opencode run --model zai-coding-plan/glm-5.1`). Dispatched in dependency-ordered waves: Group A first (dependency root), then B+C+E in parallel, then D+F in parallel. Total wall time ~90 minutes. Produced compiling code on first try for 4 of 6 groups.

**Orchestrator:** Claude Opus managed dispatch, monitoring, issue fixing, and merging. A Claude subagent wrote the 2,952-line step definition bridge connecting all 59 scenarios.

**Result:** 332 scenarios (273 existing + 59 new), 1,804 steps, zero failures. The information barrier held throughout — red team never saw How, green team never saw Done or tests.

## Guidance

**Model selection for red team should be evidence-based.** Gemini 3.1 Pro was chosen because it caught the most substantive P1 issues in prior review passes. This paid off — even against a heavily-reviewed NLSpec, it found a contract gap that four prior review rounds missed.

**Dispatch green team agents in dependency-ordered waves, not all at once.** Three agents writing to the same working tree simultaneously caused a race condition where one process reverted an orchestrator edit. Sequence: dependency root first, then parallel batches of independent groups, then dependent groups last.

**Prefix dispatch prompts with "DIRECT TASK — no skills, no meta-workflows."** Without this, CLI tools like Codex auto-activate their skill/workflow systems instead of executing the implementation task. This is especially important for OpenCode dispatches where the prompt is the only steering mechanism.

**Budget for orchestrator fixups.** Even with clean green-team output, the orchestrator needed to fix 2 issues: a PII blocklist that was too broad (blocking legitimate test assertions) and a FigureSpec JSON assertion in existing tests that green team couldn't see. Plan for 10-20% orchestrator intervention on edge cases the isolated teams can't diagnose.

**NLSpec review investment compounds.** Four review passes before red team dispatch meant only 1 contract gap in 59 scenarios. The upfront cost (reviewer time) is recovered many times over by avoiding red-team-discovered ambiguities that would require NLSpec amendments and green team rework.

## Why This Matters

The adversarial process — red team writes tests from the spec's "what" without seeing "how", green team implements from "how" without seeing tests — catches specification gaps that no amount of single-model review finds. Scaling it to 6 work groups with wave-based dispatch proves the pattern works beyond toy-sized features. The information barrier is the load-bearing wall: if it breaks, both teams converge on the same blind spots.

The multi-model aspect matters too. Different models have different failure modes and attention patterns. Gemini's strength at catching contract gaps complements GLM's ability to produce compiling Rust from a spec. Using both, each in their strength zone, produces better outcomes than using either alone for both roles.

## When to Apply

- The feature is large enough to decompose into 3+ work groups with dependency relationships between them.
- An NLSpec exists and has been through at least 2 review passes (otherwise red team will drown in spec ambiguities rather than finding genuine contract gaps).
- The acceptance criteria can be expressed as Cucumber scenarios (behavioral, observable, no implementation coupling).
- You have access to at least 2 different model providers for the red/green split.

Do NOT apply when:
- The change is a surgical fix to 1-2 files — the overhead of dispatch and monitoring exceeds the benefit.
- The NLSpec is still in draft — red team will produce scenarios against a moving target.
- The feature has deep internal coupling between groups that prevents parallel dispatch.

## Examples

**Wave dispatch for 6 groups with dependencies:**

```
Wave 1: Group A (parser foundations — everything depends on this)
Wave 2: Groups B + C + E (independent of each other, depend only on A)
Wave 3: Groups D + F (depend on B and/or C)
```

**Red team dispatch (Gemini):**

```bash
gemini -y -s false --prompt "DIRECT TASK — no skills, no meta-workflows.

You are the RED TEAM. Your job: write Cucumber scenarios from this NLSpec.
You see sections 1 (Why), 2 (What), and 4 (Done). You do NOT see section 3 (How).

[NLSpec sections 1, 2, 4 pasted here]

Write .feature files with Given/When/Then scenarios covering every acceptance criterion.
Focus on observable behavior and edge cases. Do not assume implementation details."
```

**Green team dispatch (GLM via OpenCode):**

```bash
opencode run --model zai-coding-plan/glm-5.1 --format json \
  "DIRECT TASK — no skills, no meta-workflows.

Implement Group B from this NLSpec section 3 (How). You do NOT see the test scenarios.

[NLSpec section 3, Group B excerpt pasted here]

Write Rust code in the specified modules. Run cargo check before finishing." \
  > group-b.log 2>&1 &
```

**Orchestrator fixup pattern:** When green team output breaks existing tests the green team can't see, diagnose whether the issue is (a) green team code that's genuinely wrong (route PASS/FAIL back without showing test code) or (b) a test-environment issue the orchestrator should fix directly (e.g., PII blocklist too broad). Only fix (b) directly; always route (a) back through the barrier.

