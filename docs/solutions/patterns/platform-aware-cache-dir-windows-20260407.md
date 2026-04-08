---
module: middens
date: 2026-04-07
problem_type: best_practice
component: tooling
severity: medium
tags: [cross-platform, windows, cache-dir, rust, cfg-attributes]
applies_when:
  - Code needs a user-scoped cache or data directory
  - The project targets at least one non-Unix platform
  - Hardcoded XDG paths would break on Windows
related_components: [bridge]
---

# Platform-Aware Cache Directories with `cfg!(windows)`

## Context

`middens` ships an embedded Python runtime via uv. The original `bridge/embedded.rs`
hardcoded `$XDG_CACHE_HOME` / `~/.cache/middens` for the venv cache. Windows has
neither `XDG_CACHE_HOME` nor a `~/.cache` convention; the equivalent is
`%LOCALAPPDATA%\middens\cache`. Reviewers flagged the path construction as
non-portable.

## Guidance

Prefer the `dirs` or `directories` crate for the common case — they do the platform
routing correctly in one call (`dirs::cache_dir()` returns
`%LOCALAPPDATA%` on Windows, `~/Library/Caches` on macOS, `$XDG_CACHE_HOME` on
Linux). When a direct crate dependency is undesirable, branch explicitly on
`cfg!(windows)` at the boundary:

```rust
fn cache_root() -> PathBuf {
    if cfg!(windows) {
        std::env::var_os("LOCALAPPDATA")
            .map(PathBuf::from)
            .unwrap_or_else(|| PathBuf::from(r"C:\Temp"))
            .join("middens")
    } else {
        std::env::var_os("XDG_CACHE_HOME")
            .map(PathBuf::from)
            .unwrap_or_else(|| {
                dirs_home()
                    .unwrap_or_else(|| PathBuf::from("/tmp"))
                    .join(".cache")
            })
            .join("middens")
    }
}
```

Keep the branch narrow — only the directory selection logic, not the rest of the
bootstrap — so platform-specific code stays auditable.

## Why This Matters

- Windows paths fail silently when XDG assumptions leak through (the venv lands
  under whatever `~` expands to, often the wrong drive).
- `cfg!(windows)` is a runtime-cheap compile-time check — the non-taken branch is
  optimized out, so there is no overhead for Unix users.
- Using the same function at every cache access point centralises the platform
  branch; future macOS- or Linux-specific tweaks have one edit site.

## When to Apply

- Any `PathBuf` rooted at a user-scoped cache, config, data, or state directory.
- Temp file naming conventions that embed the username or `$HOME`.
- Lock-file or IPC socket paths (Windows uses named pipes, not filesystem
  sockets — that's a bigger refactor but the detection point is the same).

## Examples

Avoid:

```rust
let cache = PathBuf::from(env::var("HOME")?).join(".cache/middens");
```

Prefer:

```rust
let cache = dirs::cache_dir()
    .ok_or("no cache dir")?
    .join("middens");
```

Or, with explicit branching when the crate dep is unwanted, use the
`cfg!(windows)` pattern above. Document which dir the code expects on each
platform in a module-level comment — it's the first thing a reader needs when
debugging a "file not found" on a platform they don't develop on.
