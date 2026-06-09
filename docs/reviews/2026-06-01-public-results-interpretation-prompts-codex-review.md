# Public results interpretation prompts — Codex review

**Date:** 2026-06-01
**Reviewer:** Codex CLI (`codex exec --skip-git-repo-check --full-auto`), local trusted prompt-only review
**Scope:**

- `docs/prompts/public-corpus-interpretation-v1.md`
- `docs/prompts/public-comparative-interpretation-v1.md`

## Review checklist

The review checked P1/P2 issues only against the public-results interpretation requirements:

- use only curated evidence JSON;
- cite exact metrics;
- state per-corpus session/split counts;
- distinguish `0`, `undefined`, missing, and `redacted`;
- avoid tiny-N/autonomous behaviour claims;
- mention language and thinking-visibility gaps;
- avoid treating duplicate-shaped corpora as independent replications;
- avoid raw transcripts, paths, session ids, prompts, assistant messages, thinking text, or tool payloads;
- keep the voice plain/slightly wry;
- for comparative interpretation, avoid pooling duplicate-shaped corpora and classify robust/directional/magnitude-variable/contradicted/undefined/not-tested cases.

## Initial findings

Codex found two comparative-prompt issues:

1. **P1:** the comparative prompt required exact corpus counts and session totals, but did not explicitly require per-corpus `interactive` / `subagent` / `autonomous` split counts.
2. **P2:** the comparative prompt asked the model to distinguish `undefined` and `not-tested`, but did not explicitly require `0`, missing, and `redacted` to stay distinct.

No P1/P2 issues were found in the per-corpus prompt.

## Fix applied

`docs/prompts/public-comparative-interpretation-v1.md` now requires:

- exact corpus counts, per-corpus session totals, and per-corpus split counts for `interactive`, `subagent`, and `autonomous`;
- distinct handling of robust, directionally consistent, magnitude-variable, contradicted, `0`, `undefined`, `redacted`, missing, and not-tested cases.

## Re-review result

Codex re-reviewed both prompts after the fix and returned:

> APPROVE
>
> No P1/P2 blockers against the checklist in `docs/prompts/public-corpus-interpretation-v1.md` and `docs/prompts/public-comparative-interpretation-v1.md`. The prompts now cover curated-evidence-only sourcing, exact metrics, per-corpus session/split counts, `0`/`undefined`/`redacted`/missing distinctions, tiny-autonomous caution, language and thinking-visibility gaps, duplicate-shaped-corpus caveats, privacy boundaries, and the plain/slightly wry voice constraint.
>
> Residual non-blocker: the comparative template asks the model to distinguish the status classes in prose rather than forcing a rigid label-per-finding schema, so output QA is still worth doing, but that does not rise to P2.

## Validation

```bash
python3 -m unittest tests.test_interpret_public_corpus tests.test_interpret_public_comparison
```

Result: 8 tests passed.
