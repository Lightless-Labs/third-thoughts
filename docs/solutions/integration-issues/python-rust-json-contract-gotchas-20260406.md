---
module: middens
date: 2026-04-06
problem_type: integration_issue
component: tooling
severity: high
symptoms:
  - "'Invalid JSON output from Python subprocess' from PythonTechnique bridge despite syntactically valid JSON"
  - "Serde deserialization errors on missing optional fields in TechniqueResult"
  - "NaN/Infinity literals emitted by json.dumps rejected by serde_json"
  - "Table rows rejected when emitted as list-of-dicts instead of list-of-arrays"
root_cause: wrong_api
resolution_type: code_fix
related_components:
  - testing_framework
  - documentation
tags:
  - middens
  - python-bridge
  - serde
  - json-contract
  - techniques
  - pyo3-alternative
---

# Python ↔ Rust JSON Contract Gotchas in the Middens PythonTechnique Bridge

## Problem

When porting Python analytical scripts (HSMM, foraging, Granger, survival, process mining, PrefixSpan, SW, T-pattern) to run under the middens `PythonTechnique` bridge, multiple distinct failures surfaced as a single generic error: `Invalid JSON output from Python subprocess`. The JSON was syntactically valid in most cases — the failures came from contract mismatches between Python's loose serialization and Rust's strict serde deserialization.

## Symptoms

- Python script runs cleanly, prints JSON, exits 0 — but the Rust bridge fails to deserialize.
- Generic error message hides which field or which contract issue caused the failure.
- Behavior varies per technique (one fails on rows, another on NaN, another on field omission).

## What Didn't Work

- Eyeballing the JSON output: it *looked* valid, masking that `NaN`/`Infinity` are non-standard.
- Adding fields to Python output one by one: addressed individual cases but missed the systemic issue (missing serde defaults on the Rust side).
- Assuming `serde_json::from_slice` would tolerate trailing whitespace from `print()`'s newline.

## Root Causes (Six Distinct Issues)

### 1. Missing serde defaults on optional fields

`TechniqueResult` and `Finding` did not have `#[serde(default)]` on optional collection/option fields. This forced Python to emit *every* field, even empties. Omitting `description: null` on a finding or `figures: []` on a result caused deserialization to fail.

**Fix:** Added `#[serde(default)]` on `findings`, `tables`, and `figures` of `TechniqueResult`, and on `description` of `Finding`.

**File:** `middens/src/techniques/mod.rs`

### 2. Table rows format mismatch (dicts vs arrays)

`DataTable.rows` is typed as `Vec<Vec<serde_json::Value>>` — an array of arrays. Python scripts initially emitted rows as lists of dicts:

```python
# WRONG
"rows": [{"motif": "ABC", "freq": 0.5}, {"motif": "XYZ", "freq": 0.3}]
```

Serde rejects dicts where it expects arrays.

**Fix:** Rows must be positional arrays whose order matches `columns`:

```python
# RIGHT
"columns": ["motif", "freq"],
"rows": [["ABC", 0.5], ["XYZ", 0.3]]
```

### 3. NaN / Infinity in numpy/scipy outputs

Numpy and scipy computations sometimes produce `NaN` or `Infinity`. Python's `json.dumps` happily emits these as the literal tokens `NaN` and `Infinity`, which are **not valid JSON** and which `serde_json` rejects.

**Fix:** Every Python technique must include a `sanitize_for_json` helper that walks the result tree and replaces non-finite floats with `None`:

```python
import math

def sanitize_for_json(obj):
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    if isinstance(obj, dict):
        return {k: sanitize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [sanitize_for_json(v) for v in obj]
    return obj
```

Apply this immediately before `json.dumps(...)`.

### 4. Trailing whitespace from print()

`serde_json::from_slice` does not tolerate trailing whitespace. Python's `print()` appends a newline, so the byte buffer ends in `\n`, which fails the slice parser even though `from_str` would succeed.

**Fix:** Trim trailing ASCII whitespace before deserializing.

**File:** `middens/src/bridge/technique.rs`

### 5. Field naming case mismatch (`User` vs `user`)

Rust serializes `MessageRole::User` as `"User"` (PascalCase, default serde behavior). The first port attempt checked for lowercase `"user"`/`"assistant"` and silently classified every message as the wrong role.

**Fix:** Python scripts must compare against the exact PascalCase strings `"User"` / `"Assistant"`.

### 6. `tool_calls[].input` is a dict, not a JSON string

Rust serializes `serde_json::Value` as a structured JSON value, not a string. The first port attempt called `json.loads(tc["input"])`, which raised `TypeError: the JSON object must be str, bytes or bytearray, not dict`.

**Fix:** Treat it as already-parsed:

```python
input_data = tc["input"] if isinstance(tc["input"], dict) else json.loads(tc["input"])
```

## Why This Works

The underlying problem is asymmetry: Python's `json.dumps` is permissive (emits `NaN`, accepts heterogeneous structures, tolerates trailing whitespace via consumers), while `serde_json` enforces strict RFC 8259 compliance plus structural type matching against Rust types. The fixes split into two categories:

1. **Make Rust more forgiving where appropriate** — `#[serde(default)]` for optional fields and trimming trailing whitespace are legitimate relaxations that don't lose information.
2. **Make Python conform to the strict contract** — sanitize non-finite floats, emit positional row arrays, match enum casing exactly, and treat `Value` fields as parsed.

## Prevention

When porting future Python techniques (Batch 3 has 5 more), follow this checklist:

1. **Copy the `sanitize_for_json` helper** into every new technique script and call it immediately before `json.dumps`.
2. **Emit table rows as positional arrays**, ordered to match `columns` exactly.
3. **Use PascalCase** when comparing `MessageRole` values: `"User"`, `"Assistant"`, `"System"`.
4. **Treat `tool_calls[].input` as a dict**, never call `json.loads` on it.
5. **Run the technique end-to-end through the bridge**, not just standalone — standalone runs hide all six issues.
6. **When the bridge reports `Invalid JSON output from Python subprocess`**, dump the raw stdout bytes and check (in order): trailing whitespace, NaN/Infinity literals, field casing, row format, missing-vs-default fields.

A future improvement would be a shared `middens.bridge` Python module exposing `sanitize_for_json`, role constants, and a typed `TechniqueResult` builder so scripts cannot get the contract wrong.

## Validation

All 8 ported techniques pass through the bridge end-to-end. Test suite green: **240 scenarios, 1242 steps**.

## Files Affected

- `middens/src/techniques/mod.rs` — added `#[serde(default)]` on `TechniqueResult.{findings,tables,figures}` and `Finding.description`
- `middens/src/bridge/technique.rs` — trim trailing ASCII whitespace before `serde_json::from_slice`
- `middens/python/techniques/*.py` — all 8 ported scripts adopt the contract rules above

## Related

- `docs/solutions/best-practices/output-engine-renderer-architecture-20260401.md` — downstream consumer of `TechniqueResult`
- `docs/solutions/architecture/pluggable-parser-trait-pattern-20260320.md` — sibling pluggability pattern (parsers, not techniques)
