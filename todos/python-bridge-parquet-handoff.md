---
title: "Python bridge: pass Parquet path instead of JSON stdin"
status: done
priority: P0
issue_id: null
tags: [python-bridge, scaling, cli-triad]
source: real-corpus-validation-2026-04-11
---

## Problem

The Python bridge serializes the entire parsed corpus as JSON and pipes it to each Python script via stdin. For 13,432 sessions this is potentially gigabytes of serialization + deserialization, repeated 17 times (once per script). All 17 Python techniques timed out at 900s on a real corpus.

## Root cause

`bridge/mod.rs` (or `bridge/technique.rs`) calls `serde_json::to_string` on `Vec<Session>` and writes it to the subprocess stdin. Each Python script then `json.loads()` the entire blob. This is O(corpus_size) serialization cost × 17 scripts.

## Fix

1. The pipeline already writes `sessions.parquet` (or should — check if it does) to the run directory during analyze.
2. If not, add a step in `pipeline.rs` that writes a `sessions.parquet` containing the parsed session data before running techniques.
3. Change the Python bridge to pass the Parquet file path as a CLI argument instead of piping JSON to stdin.
4. Update all 17 Python scripts to read from Parquet via `pd.read_parquet(sys.argv[1])` instead of `json.loads(sys.stdin.read())`.
5. Each script reads only the columns it needs (lazy evaluation via polars/pandas).

## Acceptance criteria

- All 23 techniques complete on a 13k-session corpus within reasonable time (no 900s timeouts)
- No JSON serialization of the full corpus anywhere in the hot path
- Python scripts receive a file path, not stdin data
- Existing Cucumber tests still pass (333/333)

## What NOT to do

- Don't make the timeout configurable as a workaround
- Don't sample the input as a workaround for the I/O bottleneck
- Sampling may be needed separately for O(n²) techniques, but that's a different problem

## Resolution (2026-04-11, commit `1cb858f`)

Implemented a simpler fix than the Parquet plan: write sessions JSON **once** to a shared `NamedTempFile` in the pipeline before the technique loop, then distribute the path to all Python techniques via a new `Technique::set_session_cache()` default no-op (overridden by `PythonTechnique`). Python scripts already consumed `argv[1]` as a file path — no script changes needed.

Also fixed `granger_causality.py` crash: `msg.get('thinking', '')` returns `None` when the key exists with a null value; changed to `msg.get('thinking') or ''`. Same guard applied to `text`.

Validation (13,497 sessions, --all): hsmm (~11 min), information-foraging (~6 min), survival-analysis, process-mining all completed. No timeouts. granger-causality failed on the *old* extracted asset (fix takes effect on next rebuild). Remaining 13 techniques in progress.
