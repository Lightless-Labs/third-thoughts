---
date: 2026-04-23
source: pi-gpt-5.5-session
problem_type: methodology
severity: high
status: addressed
module: middens/parser/codex
component: reasoning-observability
tags: [thinking-blocks, reasoning, observability, codex, pi, stratification, adaptive-disclosure]
---

# Adaptive reasoning observability in Codex/pi transcripts

## Observation

A live pi session using `provider=openai-codex`, `model=gpt-5.5` produced a
mixed reasoning-observability pattern inside a single session transcript.

The transcript contained `thinking` content blocks, but their plaintext payloads
were not consistently populated:

- total `thinking` blocks observed: **15**
- blocks with non-empty plaintext `thinking`: **2**
- blocks with empty `thinking` and only an encrypted `thinkingSignature`: **13**

One plaintext block contained a summary-style reasoning note beginning:

> **Understanding user feedback**
>
> I need to clarify the user's point. They responded with "That's not why" ...

The same text was also present inside `thinkingSignature.summary[0].text`. Most
other reasoning blocks had `thinking: ""`, an encrypted payload, and an empty
`summary: []`.

This suggests the relevant state is not simply `Visible` vs `Redacted`. For this
provider path, reasoning disclosure appears to be **turn-level and adaptive**:
some turns expose summary text, while adjacent turns expose only an opaque
signature.

## Why it matters

`third-thoughts` currently treats thinking visibility as a session-level axis:

```text
thinking_visibility ∈ {Visible, Redacted, Unknown}
```

That was adequate for the Claude Code redaction rollout: either thinking blocks
were present in the local transcript, or the transcript was structurally missing
them after a known cutoff.

Codex/pi-style traces introduce a different condition:

- reasoning exists;
- the transcript records a reasoning block;
- the full reasoning remains encrypted/opaque;
- an optional plaintext summary may or may not be emitted per turn.

A summary-visible block is not equivalent to a raw visible thinking block. It is
a provider/model-selected abstraction layer. Any `thinking-divergence` result
computed over such summaries would measure **summary/public divergence**, not
raw-private/public divergence.

## Suggested stratification extension

Promote observability to a message-level label, then derive session-level labels
from the distribution of message labels.

Possible message-level axis:

```text
reasoning_observability ∈ {
  FullTextVisible,      # raw thinking text is present
  SummaryVisible,       # plaintext summary is present, raw reasoning opaque
  SignatureOnly,        # reasoning/signature exists, no plaintext
  Absent,               # no reasoning block recorded
  Unknown
}
```

Possible derived session-level axis:

```text
session_reasoning_observability ∈ {
  FullTextVisible,
  SummaryVisible,
  SignatureOnly,
  Mixed,
  Absent,
  Unknown
}
```

The observed pi session would be `Mixed(SummaryVisible + SignatureOnly)`.

## Parser implication

`middens/src/parser/codex.rs` currently notes:

```rust
// "reasoning" items are encrypted in Codex; skip them.
```

That remains mostly true, but is now incomplete. The parser should distinguish:

1. encrypted/signature-only reasoning blocks;
2. reasoning blocks with plaintext summaries;
3. any future blocks with full plaintext reasoning.

The parser should preserve summary text separately from raw thinking text so
techniques cannot accidentally compare provider summaries against public output
as if they were raw chain-of-thought.

## Research questions unlocked

Adaptive disclosure may itself be behavioral data:

- Which prompts or turn types trigger plaintext reasoning summaries?
- Are summaries more likely after user disagreement, correction, or ambiguity?
- Are tool-call turns more likely to be `SignatureOnly`?
- Are risk/security topics less likely to receive plaintext summaries?
- Do summary-visible turns suppress risk tokens before the transcript layer?
- Does observability vary by model, provider, effort level, or pi setting?

## Methodological guardrail

Do not merge summary-visible Codex/pi traces into the existing
`thinking_visibility=Visible` cohort. They should be scoped separately until a
technique explicitly declares it is operating on summaries rather than raw
thinking text.

Recommended reporting scope examples:

```text
reasoning_observability=FullTextVisible
reasoning_observability=SummaryVisible
reasoning_observability=SignatureOnly
session_reasoning_observability=Mixed
```

The key claim: reasoning visibility is no longer just a static transcript
property. It can be conditional behavior.

## Implementation note

**Addressed:** 2026-04-23 — `middens` now carries message-level
`reasoning_observability`, session-level `reasoning_observability`, and a
separate `reasoning_summary` field. The Codex parser labels embedded reasoning
blocks as `SummaryVisible` or `SignatureOnly` when `thinkingSignature` is
present, and deliberately does **not** populate `Message::thinking` from Codex
summary-visible blocks. This keeps `thinking-divergence` on raw thinking text
rather than accidentally turning it into summary/public divergence.
