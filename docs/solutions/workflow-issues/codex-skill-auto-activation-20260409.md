---
date: 2026-04-09
module: tooling / codex-cli
tags: [codex, cli, skills, review, workflow, delegation]
problem_type: silent workflow hijack
related: [docs/nlspecs/2026-04-09-cli-triad-analyze-interpret-export-nlspec.md]
---

# Codex CLI silently hijacks review tasks via skill auto-activation

## The incident

During the pass-3 and pass-4 review of the CLI triad NLSpec, three Codex invocations stalled for 10+ minutes each with no visible output, forcing the user to kill each run. The pattern was:

```bash
codex exec --skip-git-repo-check --full-auto -o /tmp/review.md "Re-review the spec at ..."
```

Run 1: killed after 44 minutes. Run 2: killed after 11 minutes. Run 3: killed after 5 minutes. Every run produced zero output because `-o` only writes the final message, and Codex never reached the final message.

## Root cause

Codex inspects `~/.codex/skills/` at startup and selects skills whose descriptions match the current task. For tasks phrased as "review this document" or "find gaps in this spec", Codex auto-activates `adversarial-document-reviewer` — a heavyweight multi-persona document review workflow that runs ~10 review personas in sequence and takes 30+ minutes on its own, before the actual review even starts.

The auto-activation is **silent** at the agent-message level. Watching the normal stderr, you see nothing. You only notice by capturing the full JSONL event stream with `--json > events.jsonl` and inspecting the first few `item.completed` entries, which reveal paths like `/Users/thomas/.codex/skills/adversarial-document-reviewer/SKILL.md` being read before the target file.

There is a second contributing cause: `~/.codex/config.toml` sets `model_reasoning_effort = "xhigh"` as a global default. Combined with the heavyweight skill workflow, this amplifies the stall: xhigh-reasoning × multi-persona-skill × large-document-read = tens of minutes of silent grinding.

## Diagnosis

If a Codex run stalls with no `-o` output, inspect the JSONL event stream:

```bash
codex exec --skip-git-repo-check --full-auto --json "<task>" > events.jsonl 2>&1 &
# wait a minute
python3 -c "
import json
with open('events.jsonl') as f:
    for line in f:
        try:
            obj = json.loads(line)
            if obj.get('type') == 'item.completed':
                item = obj.get('item', {})
                if item.get('type') == 'command_execution':
                    print(item.get('command', '')[:150])
        except: pass
"
```

If you see paths under `~/.codex/skills/` or `~/.claude/skills/` being read before the target file, a skill has auto-activated.

## Solution

**Workaround 1 (verified, reliable):** include an explicit anti-skill directive at the start of the prompt.

```bash
codex exec --skip-git-repo-check --full-auto \
  -c model_reasoning_effort=medium \
  --json \
  "DIRECT TASK — DO NOT invoke any skills, agents, or meta-workflows. Just read the file and respond with your findings in one message. <actual task>" \
  > events.jsonl 2>stderr.log
```

Pass-4 retry of the Codex review returned in **90 seconds** with 7 usable findings using this exact pattern.

**Workaround 2 (partial):** always override `model_reasoning_effort` at invocation time. The `~/.codex/config.toml` default of `xhigh` amplifies every other problem; `medium` is sufficient for review tasks and completes in under 2 minutes even when a skill does activate.

**Workaround 3 (recommended for any long-running codex call):** always run codex in the background with a hard wall-clock timer. macOS has no `timeout` binary by default; use a bash-sidecar pattern:

```bash
( codex exec ... > out.log 2>err.log; touch /tmp/codex-done ) &
CPID=$!
for i in $(seq 1 60); do
  [ -f /tmp/codex-done ] && break
  sleep 5
done
[ ! -f /tmp/codex-done ] && { echo TIMEOUT; kill $CPID; pkill -f "codex exec"; }
rm -f /tmp/codex-done
```

5-minute wall-clock ceiling is enough for any non-pathological review task.

**Unverified workaround:** there may be a config flag like `-c experimental_use_exec_skill_autotrigger=false` that disables skill auto-activation entirely. The exact key is unknown — if someone finds it, update the `codex-cli` skill doc at `~/.claude/skills/codex-cli/SKILL.md`.

## Generalised lesson

Codex (like any coding-agent CLI with skill auto-activation) can silently switch into a long-running workflow without telling you. The observable symptom — "silent stall, no `-o` output" — looks indistinguishable from a model hang, a network problem, or a rate limit, and every instinct says "wait a bit longer". The actual cause is much more mundane and much more recoverable: **Codex is reading its own skill files instead of your target file**.

**General rule:** when delegating a simple, well-scoped task to codex (or gemini, or opencode), always:

1. Lead with an explicit anti-meta-workflow directive in the prompt ("DIRECT TASK — no skills, no agents, one message").
2. Override reasoning effort at invocation time rather than trusting the config default.
3. Wrap the call in a hard wall-clock timer.
4. Capture `--json` output so that when it does stall, you can diagnose what it was actually doing.

This is documented in `~/.claude/skills/codex-cli/SKILL.md` under "Gotchas" so future invocations catch it before burning an hour.

## Time lost

~70 minutes total across three killed runs in one session. The user noticed something was wrong ("Is codex gone to take a piss or something? Get a beer perhaps?") faster than the agent did, which is a clear sign this workflow needed a circuit breaker.
