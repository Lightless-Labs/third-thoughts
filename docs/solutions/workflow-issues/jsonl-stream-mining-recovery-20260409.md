---
title: Mine JSONL event streams to recover killed coding-agent CLI runs
date: 2026-04-09
category: docs/solutions/workflow-issues
module: tooling / coding-agent-clis
problem_type: workflow_issue
component: development_workflow
severity: medium
applies_when:
  - Delegating a task >2 min to codex, opencode, or similar streaming-event CLI
  - A run stalls, gets killed, or hits a wall-clock timeout
  - The final `-o` output file is empty but an event stream was captured
tags: [codex, cli, jsonl, streaming, delegation, recovery, diagnosis]
---

# Mine JSONL event streams to recover killed coding-agent CLI runs

## Context

The default instinct when a delegated coding-agent CLI run stalls and has to be killed is to treat the whole run as a loss and retry from scratch. That instinct is wrong — and expensively so. `codex exec -o out.md` only writes the final agent message when the run completes, so a kill means an empty file. But if you *also* captured `--json > events.jsonl`, the CLI has been streaming structured events the whole time: `thread.started`, `turn.started`, `item.started`, `item.completed`. Each `item.completed` whose `item.type == "agent_message"` carries text the agent had already produced. Partial runs are not empty — they are just hiding behind the wrong file.

This learning came out of a pass-3/pass-4 spec review where a Codex run was killed at 11 minutes with an empty `-o` target. Parsing the partial `events.jsonl` recovered two real, actionable findings that drove a full amendment pass on the spec. Eleven minutes of compute was about to be thrown away for no reason other than "the file is empty".

## Guidance

**Always capture the event stream when delegating a non-trivial task.** Use `--json > events.jsonl 2>stderr.log` in addition to (or instead of) `-o`. The `-o` flag is a convenience for the happy path; JSONL is the black box you want when the happy path doesn't happen.

When a run stalls or has to be killed, mine the partial stream *before* retrying:

```python
import json
with open('events.jsonl') as f:
    for line in f:
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if obj.get('type') == 'item.completed':
            item = obj.get('item', {})
            if item.get('type') == 'agent_message':
                print(item.get('text', ''))
```

Five lines of Python, no dependencies. If the agent produced any `agent_message` items before you killed it, they will print in order. Feed whatever you recover back into the retried task.

The same pattern generalises across any streaming-event CLI: `opencode run --format json` produces NDJSON with `{"type":"text","part":{"text":"..."}}` entries, Claude Code writes its own event log, and future agent CLIs almost certainly will too. Learn the event shape once per tool, then treat killed runs as partially-completed runs.

**As a diagnosis tool.** The same JSONL is how you figure out what the agent was *doing* when it stalled. Filter for `item.completed` entries whose `item.type == "command_execution"` and you get the actual shell/tool calls the agent issued. In the Codex stall that produced this learning, those entries revealed codex reading its own `~/.codex/skills/adversarial-document-reviewer/SKILL.md` before ever touching the target file — which is how the sibling solution doc on Codex skill auto-activation got diagnosed in the first place.

## Why This Matters

A killed run feels like a total loss, but "no final message" ≠ "no output". Treating them as losses means:

1. **Wasted compute.** Eleven minutes of reasoning discarded because you didn't know where to look.
2. **Blind retries.** Without the partial findings, the retry has no extra signal — so it's likely to stall the same way.
3. **Undiagnosed stalls.** The same JSONL that carries partial findings also carries the command trace that explains *why* the run stalled. Throw it away and you also throw away the only evidence of the root cause.

Capturing `--json` costs nothing. Not capturing it costs every killed run you ever do.

## When to Apply

- Any `codex exec` call expected to run longer than ~2 minutes — use `--json > events.jsonl` in addition to or instead of `-o`.
- Any `opencode run` dispatch — use `--format json` and redirect to a log file.
- Any long-running delegation via a CLI that documents a `--json`, `--stream`, or `--events` mode.
- Before retrying a killed run: always mine the JSONL first. The retry prompt should include whatever partial findings you recovered.
- When diagnosing a silent stall: filter for `command_execution` items in the first few `item.completed` events to see what the agent was actually doing.

## Examples

**Invocation pattern (codex):**

```bash
codex exec --skip-git-repo-check --full-auto \
  -c model_reasoning_effort=high \
  --json \
  "DIRECT TASK — ... <actual task>" \
  > events.jsonl 2>stderr.log
```

**Recovery after a kill:**

```bash
# Agent messages the run got out before being killed
python3 -c "
import json
for line in open('events.jsonl'):
    try: obj = json.loads(line)
    except: continue
    if obj.get('type') == 'item.completed':
        item = obj.get('item', {})
        if item.get('type') == 'agent_message':
            print(item.get('text', ''))
            print('---')
"
```

**Diagnosis — what was the agent doing when it stalled:**

```bash
python3 -c "
import json
for line in open('events.jsonl'):
    try: obj = json.loads(line)
    except: continue
    if obj.get('type') == 'item.completed':
        item = obj.get('item', {})
        if item.get('type') == 'command_execution':
            print(item.get('command', '')[:200])
" | head -30
```

If the first dozen commands are reads of `~/.codex/skills/*/SKILL.md` or similar meta-workflow files, a skill auto-activated — see the related doc below for the fix.

## Related

- `docs/solutions/workflow-issues/codex-skill-auto-activation-20260409.md` — the Codex-specific stall that produced this learning. That doc covers *why* the run stalled; this doc covers *how to not lose the work* when any streaming-event CLI stalls, regardless of cause.
- `middens/` research project sessions where long codex/opencode delegations are routine — this pattern should be the default for any adversarial red/green dispatch.
