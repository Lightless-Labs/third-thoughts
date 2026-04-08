---
module: middens
date: 2026-04-07
problem_type: integration_issue
component: tooling
severity: high
symptoms:
  - Python technique requested by name silently skipped when uv is unavailable
  - Analyze pipeline emits partial results without warning
  - Exit code 0 despite missing technique output
root_cause: logic_error
resolution_type: code_fix
tags: [python-bridge, uv, failure-handling, pipeline, rust]
related_components: [bridge]
---

# Named Technique Requests Must Fail Loudly on Env Setup Failure

## Problem

`middens analyze` accepts `--techniques name1,name2` to run a specific subset.
When a requested name belongs to a Python technique and uv (the embedded
environment manager) fails to initialize, the pipeline logged a debug line and
dropped that technique from the run. The user saw a successful exit code with the
requested technique conspicuously missing from the report.

## Symptoms

- `middens analyze --techniques change_point_detection` produces a report with no
  change-point section, exit 0.
- Logs contain `WARN` or `DEBUG` lines about uv bootstrap but nothing louder.
- CI goldens pass because the golden was generated in an environment where uv was
  available.

## What Didn't Work

- Global "require python env" flag — too coarse; many runs legitimately don't
  touch Python techniques and shouldn't be blocked.
- Failing the whole pipeline whenever any Python technique fails env init — same
  over-reach, and breaks the "best effort" stance for default runs.

## Solution

Distinguish **requested** from **default** technique invocations at the pipeline
layer. A Python env failure is:

- **Fatal** when the user explicitly named a Python technique in `--techniques`.
  The user asked for it; silently dropping it is wrong.
- **Non-fatal** (warn and skip) when the technique was pulled in by the default
  set and the user didn't request it by name.

```rust
match python_bridge.ensure_env() {
    Ok(env) => run_python(env, tech),
    Err(e) if requested_by_name.contains(&tech.name) => {
        return Err(PipelineError::NamedTechniqueUnavailable {
            name: tech.name.clone(),
            source: e,
        });
    }
    Err(e) => {
        tracing::warn!(technique = tech.name, error = %e, "skipping python technique");
        continue;
    }
}
```

Carry the `requested_by_name` set through the pipeline from the CLI layer —
don't infer it from the presence of `--techniques`, because the user might have
passed only Rust technique names.

## Why This Works

- Honours the principal of least surprise: explicit requests fail loudly, implicit
  inclusions degrade gracefully.
- The error carries the technique name, making the failure diagnosable from a log
  line instead of requiring a re-run with `--verbose`.
- Keeps the default run robust in partial environments (e.g., release binaries on
  machines without Python).

## Prevention

- Every "best effort skip" branch should check whether the skipped item was
  explicitly requested. This is a general pattern, not specific to Python.
- Integration tests should cover `--techniques <python-name>` with a broken uv —
  the test can set `MIDDENS_DISABLE_PYTHON=1` (or equivalent) and assert non-zero
  exit plus the technique name in stderr.
- When adding a new technique kind (WASM, external binary, etc.), mirror the
  requested-vs-default distinction at the dispatch layer.
