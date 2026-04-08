---
module: middens
date: 2026-04-07
problem_type: developer_experience
component: tooling
severity: medium
tags: [cli, naming, conventions, rust, techniques]
applies_when:
  - A CLI exposes identifiers that map to source files or module names
  - The surface has both Rust and Python components with differing conventions
  - Users type the identifier on the command line (not just via config files)
---

# Kebab-Case on the CLI, Snake-Case in the Filesystem

## Context

`middens` exposes techniques via `--techniques name1,name2`. Rust modules use
`snake_case` by convention, Python files too. Early versions passed the names
through unchanged, so users had to type `change_point_detection` — easy to
mistype, inconsistent with the `middens` subcommands which already used kebab
case (`list-techniques`, `dry-run`).

## Guidance

Pick kebab-case as the canonical **user-facing** form and snake_case as the
canonical **filesystem/module** form. Normalise at the CLI boundary:

```rust
fn normalise(name: &str) -> String {
    name.replace('-', "_").to_lowercase()
}
```

Apply `normalise` to every incoming `--techniques` value and every
`TechniqueRegistry` lookup. Accept both spellings for at least one release to
avoid breaking existing scripts, but list only the kebab form in `--help` and
`list-techniques` output so the canonical surface is obvious.

## Why This Matters

- Kebab-case is the dominant CLI convention (git, cargo, rustc, gh). Consistency
  with the rest of the tool's surface (subcommands already kebab) reduces
  cognitive load.
- Keeping snake_case inside the codebase avoids fighting clippy
  (`non_snake_case`) and `rustfmt`, and keeps Rust-to-Python symmetry (Python
  filenames can't contain hyphens without import gymnastics).
- A single normalisation point at the CLI boundary means the rest of the code
  never needs to think about the user-facing form.

## When to Apply

- Technique lists, plugin names, feature flags passed via the command line.
- Subcommand names (always kebab in Rust CLIs via clap).
- Environment variable aliases should stay SCREAMING_SNAKE; the normaliser only
  covers the `--flag value` surface.

Do not apply to:
- Configuration file keys when the config format (YAML, TOML) has its own
  convention the project follows.
- Identifiers that will be rendered back to the user verbatim (error messages,
  logs) — render the kebab form there too for consistency.

## Examples

Before: `middens analyze --techniques change_point_detection,user_signal_analysis`

After: `middens analyze --techniques change-point-detection,user-signal-analysis`

Registry lookup (accepts both during transition):

```rust
pub fn get(&self, name: &str) -> Option<&dyn Technique> {
    let key = name.replace('-', "_").to_lowercase();
    self.by_name.get(key.as_str())
}
```

`list-techniques` output after the change:

```
change-point-detection    Detect behavioural change points in a session
cross-project-graph       Emit a project-co-occurrence graph
thinking-divergence       Compare thinking blocks against visible responses
user-signal-analysis      Escalation and sentiment runs over user turns
...
```

The file on disk is still `src/techniques/change_point_detection.rs`. The
normaliser is the only bridge between the two worlds.
