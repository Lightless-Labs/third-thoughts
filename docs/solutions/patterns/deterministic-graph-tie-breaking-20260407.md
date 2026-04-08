---
module: middens
date: 2026-04-07
problem_type: best_practice
component: tooling
severity: high
tags: [determinism, graph, sorting, reproducibility, rust]
applies_when:
  - Technique output feeds into reports or goldens expected to byte-match across runs
  - Data is collected into HashMap/HashSet before being emitted
  - Multiple nodes or edges share the same scoring key
related_components: [cross_project_graph, corpus_timeline, user_signal_analysis]
---

# Deterministic Tie-Breaking for Graph and Ranking Output

## Context

Rust's `HashMap` iteration order is randomized per process. Any technique that
collects nodes/edges/rows into a hash container and then emits them in iteration
order will produce byte-different output on every run. The `cross_project_graph`
technique hit this: adjacency lists rendered in a different order each run, and the
top-N project ranking flipped whenever two projects tied on edge count. Reviewers
flagged it as non-reproducible.

## Guidance

Treat determinism as a two-step discipline at every emission boundary:

1. **Sort before emit.** Convert the hash container into a `Vec` and sort by the
   primary key the output is ranked on.
2. **Add a stable tie-breaker.** When the primary key can collide, append a
   secondary key that uniquely orders the remaining ambiguity — usually the node's
   string id or its position in a canonical input order.

```rust
let mut projects: Vec<_> = graph.nodes.iter().collect();
projects.sort_by(|a, b| {
    b.1.edge_count.cmp(&a.1.edge_count)   // primary: descending score
        .then_with(|| a.0.cmp(b.0))       // tiebreaker: ascending id
});
```

For adjacency lists, sort neighbours the same way before rendering them. For
edge-weighted output, the primary key is the weight and the tiebreaker is the
`(src, dst)` lexicographic pair.

## Why This Matters

- Goldens stop flaking on CI.
- Reviewers can diff two runs to verify an intentional change instead of hunting
  for a real signal through hash-order noise.
- Downstream tools (reports, plots, diffs in PRs) become cache-friendly.
- Ties stop being a hidden source of non-determinism — the tie-breaker makes the
  collision resolution explicit and auditable.

## When to Apply

- Every time a technique crosses the output boundary (stdout, JSON, markdown).
- Every time HashMap/HashSet iteration drives a user-visible ordering.
- Any ranking where the top-N is truncated — ties at the cutoff are where
  non-determinism bites hardest.

## Examples

Non-deterministic (bug):

```rust
for (project, stats) in &graph.nodes {
    writeln!(out, "- {project}: {}", stats.edge_count)?;
}
```

Deterministic with tie-break:

```rust
let mut rows: Vec<_> = graph.nodes.iter().collect();
rows.sort_by(|a, b| b.1.edge_count.cmp(&a.1.edge_count).then_with(|| a.0.cmp(b.0)));
for (project, stats) in rows {
    writeln!(out, "- {project}: {}", stats.edge_count)?;
}
```

Prefer `BTreeMap` at the data-structure level when the entire technique benefits
from sorted iteration — it removes the need to remember the sort step.
