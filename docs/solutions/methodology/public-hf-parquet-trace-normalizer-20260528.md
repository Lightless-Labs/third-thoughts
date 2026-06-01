# Public-HF Parquet trace normalizer

**Created:** 2026-05-28  
**Status:** First corpus enabled in normal public-HF materialization / analyze path  
**Code:** `scripts/materialize_hf_analysis_corpus.py`, `docs/corpora/public-hf-analysis-corpora.json`, `.github/workflows/hf-corpus-analysis.yml`  
**Local artifacts:** `.tmp/hf-parquet-test/`, `.tmp/middens-parquet-full-test/`, `.tmp/middens-parquet-split-full-test/`, `.tmp/xdg-parquet-*`

## Summary

`archit11/claude-code-traces` is now a first-class public-HF corpus for the normal `middens analyze` path.

The registry entry `archit11-claude-code-traces-parquet` keeps `storage_format = "parquet_trace_rows"`. During materialization, `scripts/materialize_hf_analysis_corpus.py` downloads pinned Parquet files, validates the expected trace-row schema, and writes generated Claude-Code-compatible JSONL files under `sessions/`. From there, `middens analyze` sees ordinary JSONL and uses the normal parser/classifier/technique stack.

This is intentionally not a direct Rust Parquet parser yet. The project already has a materialization step for public-HF CI, so the lowest-risk promotion path is:

```text
HF Parquet trace rows → generated JSONL corpus → normal middens analyze/export/split
```

That keeps the analysis path boring, reproducible, and CI-friendly. A little inelegant, sure. But it avoids teaching the Rust CLI to speak every Hugging Face table dialect before we know which dialects are worth caring about.

## Supported schema

The first normalizer supports request/response trace rows with at least these columns:

| Column | Meaning |
| --- | --- |
| `timestamp` | Row/request timestamp fallback. |
| `request_id` | Stable generated session id. |
| `conversation_json` | JSON object containing `request` and `response` payloads. |

Expected `conversation_json` shape:

```json
{
  "request": {
    "model": "...",
    "messages": [
      {"role": "user", "content": "..."},
      {"role": "assistant", "content": [{"type": "tool_use", "id": "...", "name": "...", "input": {}}]}
    ]
  },
  "response": {
    "model": "...",
    "content": "... or content blocks"
  }
}
```

The script does **not** commit or print raw rows. It validates schema names and writes local gitignored generated JSONL artifacts.

Unsupported schemas fail loudly, for example:

```text
unsupported Parquet trace schema in data/foo.parquet: missing columns ['conversation_json']; expected at least ['conversation_json', 'request_id', 'timestamp']. Example supported schema: timestamp:string, request_id:string, conversation_json:string. Actual columns: [...]
```

## Streaming / memory behavior

The normalizer uses `pyarrow.parquet.ParquetFile.iter_batches(batch_size=256, columns=...)`. It does not load multi-GB Parquet objects into a Pandas dataframe. That was the main promotion criterion from the earlier HSMM-only exploratory adapter.

## Generated JSONL contract

Each Parquet row becomes one generated JSONL file:

```text
sessions/{request_id}.jsonl
```

Each generated line is a Claude-Code-compatible envelope with:

- `type`: `user` or `assistant`
- `sessionId`: the Parquet `request_id`
- `version`: `claude_trace_parquet_request_response_row_v1`
- `message.role`
- `message.content`
- `message.model` on assistant messages when available
- provenance fields `parquetTraceSource` and `parquetTraceRow`

Tool-use and tool-result content blocks are preserved when present, so the existing Claude Code parser can extract tool calls/results and the normal session classifier can assign `Interactive`, `Subagent`, or `Autonomous`.

## Registry / CI changes

`docs/corpora/public-hf-analysis-corpora.json` now enables:

```json
{
  "id": "archit11-claude-code-traces-parquet",
  "dataset_repo": "archit11/claude-code-traces",
  "dataset_revision": "416248040ba2c706c475bba238782c3e334fd4d8",
  "storage_format": "parquet_trace_rows",
  "analysis_enabled": true,
  "ci_tiers": ["full"],
  "expected_min_jsonl_files": 25,
  "expected_min_sessions": 25
}
```

The HF analysis workflow now installs `pyarrow` for materialization.

The corpus is in the `full` tier only. PR smoke stays small.

## Validation

Materialization:

```bash
python3 -m py_compile scripts/materialize_hf_analysis_corpus.py
python3 scripts/materialize_hf_analysis_corpus.py \
  --corpus archit11-claude-code-traces-parquet \
  --output .tmp/hf-parquet-test \
  --cache-dir .tmp/hf-cache \
  --force
```

Result:

```json
{"corpus_id": "archit11-claude-code-traces-parquet", "dataset_repo": "archit11/claude-code-traces", "dataset_revision": "416248040ba2c706c475bba238782c3e334fd4d8", "jsonl_files": 25, "storage_format": "parquet_trace_rows"}
```

Full analysis:

```bash
XDG_DATA_HOME=$PWD/.tmp/xdg-parquet-full-test \
  ./middens/target/release/middens analyze .tmp/hf-parquet-test \
    --all --timeout 1800 --force \
    --output .tmp/middens-parquet-full-test
```

Result:

| Metric | Value |
| --- | ---: |
| Sessions discovered | 25 |
| Sessions parsed | 25 |
| Parse errors | 0 |
| Techniques run | 23 |
| Technique errors | 0 |

Export:

```bash
./middens/target/release/middens export \
  --analysis-dir .tmp/xdg-parquet-full-test/com.lightless-labs.third-thoughts/analysis/<run-id> \
  --no-interpretation \
  --output .tmp/reports-parquet/archit11-claude-code-traces-parquet.ipynb \
  --force
```

Result: notebook export succeeded; manifest has 23 technique entries.

Split full battery:

```bash
XDG_DATA_HOME=$PWD/.tmp/xdg-parquet-split-full-test \
  ./middens/target/release/middens analyze .tmp/hf-parquet-test \
    --split --all --timeout 1800 --force \
    --output .tmp/middens-parquet-split-full-test
```

Result:

| Stratum | Sessions |
| --- | ---: |
| Interactive | 5 |
| Subagent | 19 |
| Autonomous | 1 |

All 69 split technique executions completed with zero technique errors.

Rust validation after the earlier split-cache fix remains:

```bash
cd middens && cargo test
cd middens && cargo build --release --locked
```

Result: `381/381` Cucumber scenarios, `2108/2108` steps, doctest passing; release build passing.

## Methodological caveat

This corrected an earlier tempting shortcut. The independent HSMM normalized artifact made `archit11__claude-code-traces` look like **25/25 autonomous candidates** because it inspected pre-normalized `Session[]` objects whose user-message classifications were still `Unclassified`.

Once the dataset goes through the normal generated-JSONL → parser → message classifier → session classifier path, it becomes:

```text
5 interactive / 19 subagent / 1 autonomous
```

So: good smoke test, not a real autonomous-loop cohort. The normal path did exactly what we wanted: it killed a too-easy headline before it escaped containment.

## Next work

- Add support for other Parquet trace variants from the survey:
  - `archit11/claude_code_traces_hs`
  - `archit11/claude_code_traces_dirty`
  - `nlile/misc-merged-claude-code-traces-v1`
- Decide whether any high-value schema should move from script materialization into a Rust parser.
- Add a larger non-empty autonomous corpus before making any autonomous-behavior claims.
