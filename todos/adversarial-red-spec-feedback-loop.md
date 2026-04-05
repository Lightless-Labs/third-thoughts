---
title: "Foundry feedback: adversarial red team review should feed back to spec"
status: open
priority: p2
tags:
  - adversarial
  - foundry
  - process
source: "2026-04-05 Batch 1 adversarial run"
---

# Red team test review should feed back to spec

## What happened

During Batch 1 adversarial (Python techniques), the red team wrote a test expecting "State Emission Probabilities". The NLSpec specified "State Characteristics". The orchestrator classified this as a red bug and overwrote the test (commit `dbf64c8`).

This was wrong. The red team may have surfaced a legitimate spec gap — emission probabilities are useful HMM diagnostic output distinct from "State Characteristics". The correct flow:

1. Phase 1b review catches mismatch
2. Classify: spec gap vs red error
3. If spec gap → amend NLSpec, green implements
4. If red error → send red back

**The red team is the first consumer of the spec. Their misunderstandings are signal about spec quality.**

## Action needed

File left at `~/Projects/lightless-labs/public/foundry/todos/adversarial-red-spec-feedback-loop.md` (can't be committed — public/ is gitignored in parent monorepo). The foundry:adversarial skill's Phase 1b should add a spec feedback decision point.
