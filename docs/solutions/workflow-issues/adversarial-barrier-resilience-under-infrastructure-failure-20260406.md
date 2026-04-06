---
title: Preserving the adversarial information barrier through infrastructure failures
date: 2026-04-06
category: workflow-issues
module: middens
problem_type: workflow_issue
component: development_workflow
severity: high
applies_when:
  - Running adversarial red/green development with multiple model CLIs
  - A planned model becomes unavailable mid-phase (quota, outage, tool bug)
  - Subagent tool layers (OpenCode, Codex, Gemini CLI) fail on writes or large payloads
  - Green team gets stuck on environment-level issues vs implementation logic
tags: [adversarial, red-green, kimi, gemini, codex, opencode, information-barrier, middens]
---

# Preserving the adversarial information barrier through infrastructure failures

## Context

During Batch 1 and Batch 2 of the middens Python technique porting effort
(2026-04-05 / 2026-04-06), the adversarial red/green process was disrupted
multiple times by infrastructure failures: Codex ran out of quota mid-batch,
Kimi via OpenCode hit a tokenizer bug that corrupted its write tool, and the
wrong Gemini model was initially selected for the green team. Despite this,
the information barrier between red (test author) and green (implementer)
teams was preserved end-to-end, and 8 of 13 Python techniques shipped with
240 scenarios / 1242 steps passing.

The interesting result is not that the work got done — it's that the
adversarial process turned out to be far more resilient to model and tooling
failure than expected, because each subagent invocation is stateless and
the barrier lives in the orchestrator's prompt construction, not in any
particular model.

## Guidance

When running adversarial red/green development across heterogeneous model
CLIs, treat the information barrier as a property of the orchestrator's
prompt routing, not a property of any specific model or tool. This unlocks
several recovery patterns:

### 1. Mid-phase model swaps preserve the barrier

If the planned red- or green-team model becomes unavailable, swap it for
another model **within the same phase**. Each subagent invocation is
stateless, so the new model only sees what the orchestrator hands it. The
barrier holds as long as the orchestrator continues feeding the same
filtered context (DoD + Data Model for red; How section + PASS/FAIL
outcomes for green).

Validated in Batch 1: Codex (red) hit its usage limit partway through.
Switched red team to Gemini 2.5 Pro mid-process. Gemini received only the
DoD section, never the implementation. Barrier held.

### 2. Pick the "quality default" model for the green team

Model selection matters more than process discipline. For the same prompt
and the same barrier, Gemini 3.1 Pro Preview (`gemini-3.1-pro-preview`)
produced fewer green-team fix iterations than Gemini 2.5 Pro
(`gemini-2.5-pro`), despite Batch 2 containing more complex scripts than
Batch 1. The Gemini CLI skill flags 3.1 Pro Preview as the "quality
default" — trust that label.

### 3. Bash heredoc as a write-tool fallback for Kimi

Kimi via OpenCode has a tokenizer bug where `<|tool_call_begin|>` tokens
leak into the JSON payloads of structured tool calls, corrupting any call
that goes through the write/edit tool layer. Workaround: instruct Kimi to
write files via bash heredoc instead.

```bash
cat > path/to/file.py << 'EOF'
# file contents here
EOF
```

This bypasses the structured tool layer entirely and routes through
Kimi's bash tool, which is unaffected by the tokenizer bug.

### 4. One file per invocation when tool layers have payload limits

Even with bash heredoc, Kimi cannot reliably write multiple files in a
single invocation — payloads beyond ~1 file fail intermittently. Solution:
dispatch one file per `opencode run` invocation, in parallel.

For Batch 2's 4 Python scripts, the orchestrator launched 4 parallel
`opencode run --model kimi-for-coding/k2p5 --format json` calls, one per
file. This is faster than batching anyway, and avoids the payload limit.

### 5. Orchestrator escalation for environment-level bugs is not a barrier violation

When the green team gets stuck on the same failure for 3+ iterations, the
orchestrator (Claude) can directly fix environment-level bugs without
breaking the barrier. Examples that qualify as "environment, not
implementation":

- Library API mismatches (e.g., `_n_parameters()` not present in the
  installed `hmmlearn` version — the green team's code is correct against
  the API it was told to target)
- Python version compatibility (e.g., `str | None` syntax not supported on
  Python 3.9 — a syntax-level mismatch with the runtime, not a logic bug)
- Missing dependencies, path issues, environment variables

The test for "is this a barrier violation" is: would the fix tell the
green team something about the test assertions or expected outputs? If
no, it's infrastructure and the orchestrator can handle it.

### 6. Filter test outcomes to PASS/FAIL only

When feeding test results back to the green team for the next iteration,
emit only `test_name: PASS|FAIL` lines. Never include assertion text,
diff output, or expected-vs-actual values. When tests fail and a hint is
needed, derive the hint from the **test name** (which the green team is
allowed to see — names describe behavior, not assertions), not from the
test code or assertion output.

## Why This Matters

Adversarial development is widely perceived as fragile: it depends on
multiple model CLIs being simultaneously available, on tool layers
behaving correctly, and on strict information hygiene. Any one of those
breaking is supposed to compromise the experiment.

In practice, the process is much more resilient than that, because:

1. **Subagent invocations are stateless.** The barrier is reconstructed
   from scratch on every call. A model that joins mid-phase inherits the
   same filtered view as the model it replaced.
2. **Tool failures have known workarounds.** Bash heredoc is a universal
   escape hatch when structured tool layers misbehave.
3. **The orchestrator is allowed to fix infrastructure.** Distinguishing
   "implementation logic" (barrier-protected) from "environment
   compatibility" (free to fix) preserves the experiment's validity
   without forcing the green team into unproductive iteration loops.
4. **Per-file dispatch beats batch dispatch.** When tool layers have
   payload limits, parallelizing one-file-per-invocation is both faster
   and more reliable than fighting the limit.

The bigger lesson: **the "right model" matters more than process
discipline**. Gemini 3.1 Pro Preview required materially fewer green-team
iterations than 2.5 Pro for harder scripts. Before tightening the
process, try the better model.

## When to Apply

- Running any multi-model adversarial workflow (red/green, attacker/
  defender, prover/verifier)
- A planned model hits quota, an outage, or a tool-layer bug mid-phase
- Kimi via OpenCode is the green team and write tool calls fail with JSON
  parsing errors
- Green team has been stuck on the same failure for 3+ iterations and
  the failure smells like environment, not logic
- Choosing default models for a new adversarial workflow — pick the
  CLI's flagged "quality default", not the cheaper/faster tier

## Examples

**Mid-phase model swap (Batch 1):**

```
Phase: Batch 1 red team (test authoring)
Planned:    codex exec --skip-git-repo-check --full-auto "<DoD + Data Model>"
After quota exhaustion:
            gemini -y -s false --model gemini-2.5-pro \
                   --prompt "<DoD + Data Model>"
Barrier check: Gemini received the same filtered prompt Codex received.
               No implementation, no test code, no assertion text. Pass.
```

**Kimi heredoc workaround (Batch 2):**

```
# Failing path (write tool corrupted by tokenizer bug):
opencode run --model kimi-for-coding/k2p5 --format json \
    "Implement middens/python/techniques/foo.py: <How section>"
# -> JSON parse error from leaked <|tool_call_begin|> tokens

# Working path (bash heredoc, parallel per-file dispatch):
opencode run --model kimi-for-coding/k2p5 --format json \
    "Use a bash heredoc (cat > file << 'EOF') to write
     middens/python/techniques/foo.py with: <How section>" &
opencode run --model kimi-for-coding/k2p5 --format json \
    "Use a bash heredoc to write middens/python/techniques/bar.py
     with: <How section>" &
opencode run --model kimi-for-coding/k2p5 --format json \
    "Use a bash heredoc to write middens/python/techniques/baz.py
     with: <How section>" &
opencode run --model kimi-for-coding/k2p5 --format json \
    "Use a bash heredoc to write middens/python/techniques/qux.py
     with: <How section>" &
wait
```

**Orchestrator escalation (not a barrier violation):**

```
Iteration 3 of green team: same hmmlearn._n_parameters AttributeError.
Diagnosis: _n_parameters() removed in installed hmmlearn version.
Action:    Orchestrator patches the call site to use the supported API.
Reason:    The green team's code is correct against the API it was told
           to target. The mismatch is between "what hmmlearn used to
           expose" and "what's installed". This is environment, not
           implementation logic. Barrier preserved.
```

## Outcome

- 8 of 13 Python techniques ported across Batch 1 and Batch 2
- 240 Cucumber scenarios, 1242 steps passing
- All 4 Batch 2 scripts written by Kimi via bash heredoc with per-file
  parallel dispatch
- Zero documented barrier violations across both batches
- Batch 2 (Gemini 3.1 Pro Preview green team) required fewer fix
  iterations than Batch 1 (Gemini 2.5 Pro green team) despite more
  complex scripts

## Related

- `~/Projects/lightless-labs/foundry/docs/solutions/workflow-issues/adversarial-orchestration-playbook-20260404.md`
  — base playbook for the adversarial process
- `docs/HANDOFF.md` — current middens implementation status
- `docs/plans/2026-03-20-003-feat-middens-cli-session-log-analyzer-plan.md`
  — original middens plan
- Gemini CLI skill — flags `gemini-3.1-pro-preview` as quality default
- OpenCode model ID notes in project `CLAUDE.md` — Kimi K2.5 ID and
  `--format json` requirement
