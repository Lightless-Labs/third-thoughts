---
status: deferred
priority: P3
tags: [middens, cleanup, technique, storage]
source: conversation 2026-04-09 (CLI triad milestone scoping)
blocked_by: [cli-triad-analyze-interpret-export]
---

# Delete `corpus-timeline` technique once `sessions.parquet` exists

## Why deferred

`corpus-timeline` was added in Batch 4 as a provisional Python technique (`middens/python/techniques/corpus_timeline.py`) with a header comment explicitly marking it for deletion once the storage/view reshape lands. It only exists because reports need to be reproducible without the source corpus, which currently forces `(date, project, session_count)` to be materialised into a stored DataTable.

Once the CLI triad milestone ships and there is a canonical `sessions.parquet` (written once per `analyze` run and referenced by every view) with columns like `(session_id, project, started_at, ended_at, n_messages, …)`, `corpus-timeline` becomes a trivial `GROUP BY date, project` at view-render time. The technique is then dead weight.

## What to do

- [ ] Confirm `sessions.parquet` (or equivalent canonical sessions table in the analysis storage layer) exists and carries per-session `started_at` + `project` fields.
- [ ] Delete `middens/python/techniques/corpus_timeline.py`.
- [ ] Remove its entry from `PYTHON_TECHNIQUE_MANIFEST` in `middens/src/techniques/mod.rs`.
- [ ] Remove the corresponding embedded asset (`bridge::embedded` content-hash list).
- [ ] Delete Cucumber scenario(s) tagged for `corpus-timeline` in `tests/features/python_batch4.feature`.
- [ ] Add a "per-project sessions over time" view snippet in the `.ipynb` renderer (or in an exploratory starter cell) that loads `sessions.parquet` and renders the same chart via Vega-Lite / altair.
- [ ] Update `docs/methods-catalog.md` to remove the entry.
- [ ] Update technique count in `CLAUDE.md` and `README.md` (23 → 22).

## Constraints

Don't delete until `sessions.parquet` is proven out on a real corpus run. The replacement view snippet must pass the same "reproducible without the source corpus" test — if loading `sessions.parquet` produces the same chart, the deletion is safe.

## Effort

~30 lines of deletion + ~20 lines of replacement view snippet. Small PR.
