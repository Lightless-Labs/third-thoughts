---
title: "Technical learnings from Batch 3 Python techniques + GH#42796 replication"
date: 2026-04-06
category: best-practices
module: middens-python-techniques
problem_type: best_practice
component: python_bridge
severity: medium
applies_when:
  - "Writing Python techniques that target a Rust-defined TechniqueResult contract"
  - "Using numpy in a function that serializes to JSON"
  - "Computing NCD or other compression-based distances"
  - "Writing regex word boundaries in Python raw strings"
  - "Implementing percentage thresholds from a spec"
  - "Normalizing cwd paths into stable project identifiers"
tags: [python, rust, numpy, ncd, regex, compound-engineering, batch3]
---

# Technical learnings from Batch 3 Python techniques + GH#42796 replication

## Context

On 2026-04-06 we shipped Batch 3 of the Python technique ports (lag-sequential, SPC control charts, NCD clustering, ENA, convention epidemiology) via PR #4, closing out the port at 13/13 techniques and 261 passing Cucumber scenarios. The work was orchestrated through the adversarial red/green CLI workflow — Gemini 3.1 Pro on the red team, Kimi K2.5 (via OpenCode) and Codex on the green team — and went through six rounds of automated PR review iteration. In parallel we ran a counter-analysis replicating GH#42796's claims against the corpus. The technical learnings below all came from concrete failing rounds whose fixes are visible in commit `9eca691`.

## Learnings

### 1. The Rust `DataTable` schema is `{name, columns, rows}`, not `{title, headers, rows}`

**Symptom.** Round 1 of green-team output for Batch 3 deserialized cleanly as JSON but produced empty tables in the renderer. Cucumber scenarios that asserted on column headers failed across every technique that emitted a table.

**Root cause.** The shared green-team contract I distributed paraphrased the table schema in NLSpec prose (`title` / `headers` / `rows`) instead of pinning to the actual Rust struct definition in `middens/src/output/mod.rs`, which uses `name` / `columns` / `rows`. Every Python technique inherited the wrong field names from the contract. Serde silently accepted the unknown fields and dropped them.

**Fix.** Renamed across all five Batch 3 techniques in `middens/python/techniques/{lag_sequential,spc_control_charts,ncd_clustering,ena_analysis,convention_epidemiology}.py`. A full round of green-team rework was lost before the cause was spotted.

**Why it matters / transferability.** When a contract spans languages, the source of truth has to be the *target struct definition*, not the spec prose that describes it. For Rust-as-target work, the green-team brief should `cat` the relevant struct (or paste it verbatim) rather than re-describe it. The same rule applies in reverse for FFI: copy the header, don't paraphrase it. This is now documented in `docs/HANDOFF.md` under the Batch 3 process learnings.

### 2. Numpy scalars escape Python-only `isinstance` sanitizers

**Symptom.** `json.dumps(result)` succeeded locally but produced invalid JSON ("`NaN`", "`Infinity`") that the Rust bridge then refused to parse, surfacing as `serde_json::Error: expected value` from `PythonTechnique::run`.

**Root cause.** The first-pass sanitize functions only checked `isinstance(obj, float)`. `np.float64` and `np.int64` are not subclasses of Python `float` / `int` for this check, so numpy NaN, ±Infinity, and integer arrays passed through unchanged. `json.dumps` happily serializes them as bare `NaN`/`Infinity` tokens, which are not valid JSON.

**Fix (visible in `9eca691`):** explicit handling for the numpy type hierarchy *before* the Python `float` branch:

```python
if isinstance(obj, np.ndarray):
    return [sanitize(x) for x in obj.tolist()]
if isinstance(obj, (np.floating, np.integer)):
    v = obj.item()
    return v if math.isfinite(v) else None
if isinstance(obj, float):
    return obj if math.isfinite(obj) else None
```

Applied identically across `ncd_clustering.py`, `ena_analysis.py`, and `convention_epidemiology.py`.

**Why it matters / transferability.** Any Python boundary that crosses into a strict-JSON consumer (Rust serde, Postgres `jsonb`, browsers) needs a numpy-aware sanitizer. The trap is that local round-tripping through `json.loads(json.dumps(x))` *also* succeeds, because Python's `json` module reads back its own non-standard tokens. Test against a strict parser, not Python's own.

### 3. NCD is order-dependent under zlib; symmetrize before clustering

**Symptom.** `ncd_clustering.py` produced different cluster assignments on repeat runs of the same input when the session order was shuffled. The Cucumber scenario that asserted clustering stability under permutation failed intermittently.

**Root cause.** `C(x ⧺ y)` and `C(y ⧺ x)` are not equal in general for zlib (or any practical compressor) — the dictionary state at the join boundary depends on what came first. The initial implementation computed only one direction, so the distance matrix was asymmetric and the upper/lower triangles disagreed depending on iteration order.

**Fix (in `ncd_clustering.py`):** compute both directions and take the minimum, the standard Cilibrasi & Vitányi symmetrization:

```python
len_c_sym = min(len_cxy, len_cyx)
min_len   = min(compressed_lengths[i], compressed_lengths[j])
ncd       = (len_c_sym - min_len) / max(compressed_lengths[i], compressed_lengths[j])
```

**Why it matters / transferability.** Any compression-based distance (NCD, NID, normalized Lempel–Ziv) has this property because compressors are stateful left-to-right. If you skip symmetrization you get non-determinism that *looks* like a clustering bug but is actually a metric bug. The same applies to BWT and LZMA — only run-length and dictionary-free coders are immune, and those are too weak to give useful NCDs.

### 4. `r"\\b"` is a literal backslash-b, not a regex word boundary

**Symptom.** Every epistemic-code keyword in `ena_analysis.py` matched zero sessions in Round 1, producing an all-zero co-occurrence matrix. The Cucumber scenario asserted at least one non-zero entry on the fixture and failed cleanly.

**Root cause.** The first version used `r"\\b" + re.escape(kw) + r"\\b"`. The double backslash *looks* correct because `\\` is the standard escape for a literal backslash in non-raw strings — but inside a raw string the backslashes are already literal, so `r"\\b"` is two characters (`\` and `b`) and the regex engine reads it as a literal backslash followed by a `b`, not as the `\b` word-boundary metachar.

**Fix:** drop one backslash. The correct form is `r"\b" + re.escape(kw) + r"\b"`.

**Why it matters / transferability.** This is the canonical raw-string-meets-regex Python gotcha and it specifically fails *silently and uniformly* — the regex compiles, it just never matches anything word-boundary-adjacent. Add a unit test that asserts a known keyword in a known string matches, not just that the pattern compiles.

### 5. `int(0.1 * N)` floors a "≥10%" threshold

**Symptom.** `convention_epidemiology.py` accepted projects below the spec'd 10% diffusion threshold. At N=59 sessions the threshold became 5 (8.5% of N), letting through 4 projects that the NLSpec said should be filtered.

**Root cause.** `int(x)` truncates toward zero. For a ≥10% rule the correct primitive is `math.ceil`. The implementation also needs a sensible floor for tiny corpora.

**Fix (commented inline in the patched file):**

```python
# The 10% threshold uses math.ceil, not int(), so the "≥10% of sessions"
# rule is faithful. For N=59, int(0.1*59)=5 (8.5%) passes, but ceil(5.9)=6
min_sessions_threshold = max(5, math.ceil(0.1 * len(session_data)))
```

**Why it matters / transferability.** When a spec says "≥ X%", the implementation should be `ceil(X * N / 100)` (with a min-floor for very small N), never `int()`. Whenever you see `int(fraction * N)` in code that derives a threshold from a percentage in an NLSpec, it is almost always wrong by one in the rounding-down direction. Worth a lint rule.

### 6. Path basename collision when hashing project IDs

**Symptom.** `convention_epidemiology.py` collapsed sessions from `/workspace/team-a/service` and `/workspace/team-b/service` into the same project, producing fake "cross-project diffusion" between two unrelated repos. Caught during the GH#42796 counter-analysis when we noticed implausibly fast diffusion latencies.

**Root cause.** The first version derived project IDs from the deepest path component only (`os.path.basename`). Any two repos that happened to have the same leaf folder name collided.

**Fix.** Take the last *two* components after stripping a narrow blocklist of known source-tree subdirs (`src`, `tests`, `docs`, `lib`). The blocklist is deliberately narrow: words like `api`, `service`, `backend`, `web`, `server` are frequent *repo* names and must NOT be in the blocklist or the same collision returns.

**Why it matters / transferability.** Any analysis that joins sessions on a derived project key needs to be tested against a corpus with name collisions, not just synthetic single-tree fixtures. The compound version of this lesson: anywhere you turn a path into an identifier, write down the equivalence class explicitly and add a test with two different paths that should map to *different* IDs.

## References

- Commit `9eca691` — Batch 3 merge (red + green squashed). All six fixes above are visible in this diff.
- Commit `3bff886` — HANDOFF update with the round-by-round process learnings (table schema, ToolResult `tool_use_id`, OpenCode SQLite WAL conflict, `/tmp/*` rejection, `-s false` working-dir contamination, Codex `py_compile` sandbox blocker).
- Files: `middens/python/techniques/{lag_sequential,spc_control_charts,ncd_clustering,ena_analysis,convention_epidemiology}.py`
- Rust contract: `middens/src/output/mod.rs` (`DataTable` struct — the source of truth for learning #1)
- Counter-analysis: `~/claude-reasoning-performance-counter-analysis/report.md` (the GH#42796 replication that surfaced learning #6)
- Prior batch learnings: `docs/solutions/best-practices/pattern-mining-fixtures-need-variation-20260406.md`
