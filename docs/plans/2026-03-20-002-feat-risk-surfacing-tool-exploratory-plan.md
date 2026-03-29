---
title: "Risk Surfacing Tool: Exploratory Plan"
type: feat
status: exploratory
date: 2026-03-20
---

# Risk Surfacing Tool

## The Problem

Claude Code's thinking blocks contain risk assessments, alternative approaches, and uncertainty signals that are suppressed from public output 85.5% of the time. Users correct opaque turns at only 0.9% (vs 5.0% when uncertainty is shared). Users are making decisions based on ~7% of the agent's actual reasoning.

The thinking block data is available in JSONL session logs but only after the fact. There is no mechanism to surface suppressed risks in real time.

## The Opportunity

Build a tool that extracts and surfaces suppressed risks from the agent's private reasoning, presenting them alongside the public output. This turns the 85.5% risk suppression from a hidden liability into visible decision-support data.

## Design Space

### Option A: Post-Hoc Supervisor (simplest)

A CLI tool that reads a session's JSONL in real time (tail -f style) and extracts risk/uncertainty signals from thinking blocks as they're written.

```
┌─────────────────────────────────────────┐
│ Claude Code (normal session)            │
│ > "I've updated the migration file..."  │
└─────────────────────────────────────────┘
          │ JSONL written to disk
          ▼
┌─────────────────────────────────────────┐
│ Risk Surfacer (separate terminal)       │
│                                         │
│ ⚠ SUPPRESSED RISKS (turn 14):          │
│   • "this migration is not reversible"  │
│   • "foreign key could cause deadlock   │
│     on high-traffic tables"             │
│                                         │
│ 🔀 ALTERNATIVES CONSIDERED:             │
│   • Option B: add column with default   │
│     first, backfill, then add NOT NULL  │
│   • Option C: use a new table           │
│                                         │
│ 📊 Confidence: 0.3 (low)               │
└─────────────────────────────────────────┘
```

**Pros**: Zero integration required. Works with existing Claude Code. No API changes needed. Can be built today.
**Cons**: Slight delay (reads JSONL after write). Requires a second terminal. Thinking blocks may not be preserved in all configurations.

### Option B: Claude Code Hook

A hook that fires after each assistant turn, reads the just-written thinking block, extracts risks, and injects them as a user-visible annotation.

```toml
# ~/.claude/hooks.toml
[hooks.after_assistant_turn]
command = "third-thoughts risk-surface --session $SESSION_ID --turn $TURN_ID"
```

**Pros**: Integrated into the workflow. No second terminal. Can block or annotate.
**Cons**: Hook API may not expose thinking blocks. May add latency. Depends on Claude Code hook implementation details.

### Option C: MCP Server

A Model Context Protocol server that the agent itself can query: "what risks did I suppress in my last turn?"

```
Agent: [uses MCP tool: risk_self_audit]
→ Returns: "You identified 3 risks in your thinking but suppressed 2.
   The suppressed risks were: ..."
```

**Pros**: The agent can self-correct in real time. Could be mandated via system prompt ("always call risk_self_audit before finalizing").
**Cons**: Requires MCP integration. The agent may perform "acknowledgment theater" (mimetic performativity applied to risk surfacing). Adds token cost.

### Option D: Hybrid — Passive Monitor + Active Escalation

Combine A and B: a passive monitor runs in a second terminal showing all suppressed risks. When a risk exceeds a severity threshold (e.g., mentions "irreversible", "security", "data loss", "production"), it escalates by injecting a hook-based warning into the main session.

```
Normal operation: passive display in side terminal
High-severity risk detected: hook fires, injects warning
```

**Pros**: Low-noise for routine work, high-signal for dangerous moments.
**Cons**: Threshold tuning required. False positive risk.

## Risk Classification

The thinking block analysis identified these suppression categories:

| Category | Suppression rate | Example signals |
|----------|-----------------|-----------------|
| Risk/danger mentions | 85.5% | "could break", "security concern", "not reversible" |
| Alternative approaches | 93.8% | "another option would be", "alternatively" |
| Uncertainty markers | 54.0% | "I'm not sure", "might", "possibly" |
| Caveats and conditions | ~70% (est.) | "this assumes", "only works if" |

The tool needs to classify extracted thinking-block content into these categories and assign a severity level.

## Technical Requirements

### Input
- JSONL session files from `~/.claude/projects/`
- Thinking blocks (content type "thinking" in assistant messages)
- Public text output (content type "text" in assistant messages)

### Processing
- Parse thinking block for risk/uncertainty signals
- Compare against public output to identify what was suppressed
- Classify severity: info / warning / critical
- Extract the specific suppressed text

### Output
- Real-time display (terminal UI or file)
- Per-turn risk summary
- Session-level risk dashboard
- Exportable report

## Implementation Phases

### Phase 1: CLI Proof of Concept (Rust)
- Read JSONL session file
- Extract thinking blocks
- Apply risk/uncertainty regex patterns (reuse from `010_thinking_block_divergence.py`)
- Compare against public output
- Print suppressed risks to stdout
- Add `--watch` mode for real-time monitoring

### Phase 2: Severity Classification
- Build a severity model (keyword + context based)
- Add threshold-based escalation
- Integration with Claude Code hooks (if API supports it)

### Phase 3: TUI Dashboard
- Ratatui-based display
- Real-time session monitoring
- Historical session browser
- Risk trend visualization

### Phase 4: MCP Integration
- Expose as an MCP tool
- Allow agent self-audit
- System prompt integration for mandatory risk checks

## Open Questions

1. **Does Claude Code preserve thinking blocks in all configurations?** If not, the tool is limited to configurations where thinking is enabled and logged.

2. **What's the false positive rate on risk detection?** The regex patterns from experiment 010 were never validated against human labels. The correction classifier work may inform this.

3. **Will surfacing risks change agent behavior?** If the agent "knows" its risks will be surfaced (via MCP self-audit), does it suppress differently? This is an empirical question.

4. **Latency tolerance.** For the hook-based approach, how much delay is acceptable before it disrupts the workflow?

5. **Privacy.** Thinking blocks may contain reasoning about sensitive code. The tool must not transmit thinking block content externally.

## Success Criteria

- Users who use the tool catch at least 50% of the risks that would otherwise be suppressed
- False positive rate below 20% (risks flagged that aren't actually risks)
- Latency under 500ms for real-time mode
- Zero impact on the main Claude Code session performance
