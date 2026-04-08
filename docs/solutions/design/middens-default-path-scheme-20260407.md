---
module: middens
date: 2026-04-07
problem_type: best_practice
component: tooling
severity: medium
tags: [cli-design, middens, paths, storage-layout, bundle-id]
applies_when:
  - choosing where Middens writes analyses and interpretations by default
  - reconciling XDG conventions with macOS bundle-ID conventions
  - designing on-disk layouts for multi-phase CLI tools
---

# Middens default path scheme: bundle-ID namespacing over bare XDG

## Context

Middens needs a default output location for analyses and
interpretations. The two obvious choices were bare XDG
(`~/.local/share/middens/...`) and macOS-style bundle-ID
namespacing (`~/.local/com.lightless-labs.third-thoughts/middens/...`).
XDG is the Linux-native default; bundle IDs are the macOS-native
default. Since Middens runs on both, neither is obviously right.

## Guidance

Middens uses bundle-ID namespacing under the XDG base directory:

    ~/.local/com.lightless-labs.third-thoughts/middens/analysis/<date>-<slug>/
    ~/.local/com.lightless-labs.third-thoughts/middens/interpretation/<date>-<slug>/

Structure:

- `~/.local/` — XDG base for user-local data.
- `com.lightless-labs.third-thoughts/` — reverse-DNS bundle ID for
  the umbrella project. All Third Thoughts tools share this prefix.
- `middens/` — tool name under the project umbrella.
- `analysis/` and `interpretation/` — the two canonical stores
  that correspond to the triad's first two phases. Exports are
  transient and default to the user's working directory.
- `<date>-<slug>/` — one directory per run, immutable once
  written. `<date>` is `YYYY-MM-DD`; `<slug>` is a short
  human-readable name the user provides or the CLI derives.

## Why This Matters

Bundle-ID namespacing solves three problems at once:

1. **Collision-proofing.** `middens/` as a bare directory collides
   with any other tool called Middens on the user's machine. The
   reverse-DNS prefix is the standard collision-prevention
   mechanism and costs nothing.
2. **Umbrella grouping.** Third Thoughts will ship more tools
   (classifier, corpus manager, report builder). All of them
   sharing one `com.lightless-labs.third-thoughts/` root means a
   single `rm -rf` cleans up the whole project's local state, and
   a single backup pattern covers everything.
3. **Cross-platform parity.** The same path works on macOS, Linux,
   and WSL without per-OS logic. Pure XDG would require a
   different path on macOS to follow Apple conventions; bundle-ID
   under XDG satisfies both cultures.

The `<date>-<slug>/` subdirectory pattern is load-bearing for the
triad: each run is a self-contained bundle that `interpret` and
`export` can reference by path. Immutability means old runs never
get corrupted by new runs, which is the precondition for
reproducibility.

## When to Apply

- Any new Middens command that writes persistent output.
- Any new Third Thoughts tool — adopt the same
  `com.lightless-labs.third-thoughts/<tool>/` prefix.
- Any script or experiment that needs a stable local cache
  location tied to this project.

## Examples

**Analysis run:**

    middens analyze corpus-split/interactive/ --slug batch5-interactive
    # writes to:
    # ~/.local/com.lightless-labs.third-thoughts/middens/analysis/2026-04-07-batch5-interactive/

**Interpretation over that analysis:**

    middens interpret 2026-04-07-batch5-interactive --provider claude-code
    # writes to:
    # ~/.local/com.lightless-labs.third-thoughts/middens/interpretation/2026-04-07-batch5-interactive-claude/

Related:
- `docs/solutions/design/middens-analyze-interpret-export-triad-20260407.md`
- `docs/solutions/design/middens-storage-view-split-20260407.md`
