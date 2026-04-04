---
date: 2026-04-02
topic: middens-thinking-divergence-technique
status: draft
---

# Middens Thinking Block Divergence Technique

## 1. Why
The most robust finding in Third Thoughts: agents suppress risk-related content 85.5% of the time. Thinking blocks contain risk assessments, uncertainty, and alternative approaches that never appear in the public output. This technique measures the divergence.

## 2. What
A Rust-native technique that compares thinking block content to public output content for each assistant message, computing suppression rates.

## 3. How
Create `src/techniques/thinking_divergence.rs`:

### Data extraction
For each session, for each assistant message that has both thinking and text:
- Extract risk-related tokens from thinking: "risk", "concern", "worry", "problem", "issue", "error", "fail", "wrong", "careful", "uncertain", "maybe", "might", "however", "but", "although", "caveat", "warning", "danger", "tricky", "edge case"
- Check if any of those tokens appear in the public text output
- A token present in thinking but absent from text is "suppressed"

### Metrics
- `suppression_rate` = suppressed_tokens / total_risk_tokens_in_thinking (the 85.5% number)
- `divergence_ratio` = thinking_length / text_length (the hidden compute ratio)
- `sessions_with_thinking` = count of sessions that have any thinking blocks
- `messages_with_both` = count of messages with both thinking and text

### TechniqueResult
- Findings: suppression_rate, divergence_ratio, sessions_with_thinking, messages_with_both, total_risk_tokens, suppressed_tokens
- DataTable: per-session metrics (session_id, suppression_rate, divergence_ratio, thinking_length, text_length, risk_tokens, suppressed_tokens)

Register as essential technique in `all_techniques()`.

## 6. Definition of Done
- [ ] Technique extracts risk tokens from thinking blocks
- [ ] Technique checks which risk tokens are suppressed (absent from public text)
- [ ] suppression_rate computed correctly (suppressed / total risk tokens)
- [ ] divergence_ratio computed correctly (thinking length / text length)
- [ ] Sessions without thinking blocks are skipped
- [ ] Messages without both thinking and text are skipped
- [ ] Empty sessions return zero counts
- [ ] Registered as essential technique, appears in list-techniques
- [ ] Integration: produces correct output when run via `middens analyze`
