---
title: "Implementation patterns from Batch 3 Python techniques — 6 rounds of PR review fixes"
date: 2026-04-06
category: patterns
module: middens-python-techniques
problem_type: pattern_library
component: python_bridge
severity: medium
applies_when:
  - "Implementing statistical techniques that operate on bucketed time-series session data"
  - "Designing multi-phase analysis pipelines with phase-specific eligibility filters"
  - "Computing compression-based distances (NCD) for clustering"
  - "Deriving stable opaque identifiers from filesystem paths without filesystem access"
  - "Guarding SciPy hierarchical clustering against small sample sizes"
tags: [python, batch3, ncd, clustering, project-id, boundary-semantics, code-review]
---

## Context

Batch 3 of the Python technique ports (lag sequential, SPC control charts, NCD clustering, ENA, convention epidemiology) shipped through six rounds of automated PR review (Codex, Copilot, Gemini, CodeRabbit). The merged result (commit `9eca691`) is the squash of an iteration chain — `61f602b → 34f32d1 → 6ec82cd → 7a65047 → 19825bb → bdd2c3a → ad6ba24 → b590e4b`. Each round surfaced a class of bug that the unit tests and the NLSpec did not catch but that emerged from reviewers reading the code against the spec. The patterns below are the highest-signal failures: each is anchored to a specific technique and a specific commit, but the underlying lesson generalizes to any statistical/time-series/clustering technique that operates on session data.

## 1. The "_unknown" bucket contaminated cross-project origins

**Bug.** `convention_epidemiology.py` derives a `project_id` per session via path heuristics. Sessions without a `cwd` field fall through to `project_id = "_unknown"`. The NLSpec was explicit that `_unknown` must be excluded from cross-project analysis — and the *summary* step honoured that. But the Phase-2 `first_seen` loop iterated all sessions in chronological order and recorded whichever project first adopted a bigram. When a `cwd`-less session happened to be the first adopter, `_unknown` became the canonical origin, and every downstream metric (latency to second adopter, project reach, propagation pattern) was anchored to a bucket that was supposed to be invisible.

**Fix.** Explicit `if pid == "_unknown": continue` inside the `first_seen` loop, mirrored in the adopter enumeration. Landed in `34f32d1`.

**Generalization.** When a data category is "excluded" from an analysis, make the exclusion *structural* at every code site that iterates the data — not just in the final summary projection. A single missed iteration site is enough to anchor every derived statistic to the excluded bucket.

**Ref.** `middens/python/techniques/convention_epidemiology.py`, `_compute_propagation()`.

## 2. Boundary asymmetry in propagation classification

**Bug.** Reach (fraction of projects that ever adopted a bigram) was classified as `confined` if `reach < 0.2`, and the cross-project counter incremented if `reach >= 0.2`. At exactly `reach == 0.2`, the value fell into the *not-confined* fallback branch *and* was counted as cross-project — two inconsistent classifications for the same value, depending on which predicate the reader looked at.

**Fix.** Symmetric boundaries: `reach <= 0.2 → confined`, `reach > 0.2 → cross_project_count += 1`. Landed in `6ec82cd`.

**Generalization.** Any metric with a discrete cutoff needs explicit boundary semantics. `<`, `<=`, `>`, `>=` are not interchangeable, and paired predicates must agree on which side of the boundary the equality case lands. Treat the boundary value as a test input deserving its own assertion.

**Ref.** `convention_epidemiology.py`, `_classify_propagation()`.

## 3. Phase-1 session filter vs Phase-3 project filter must not be conflated

**Bug.** The first implementation enforced "candidate must appear in ≥2 distinct projects" inside Phase 1 (candidate selection). This dropped every single-project bigram before Phase 2 could fit it, zeroing out within-workflow conventions that were supposed to be reported as `confined`. **Three reviewers (Codex, CodeRabbit, Gemini) independently flagged it** in the same review round.

**Fix.** Phase 1 filters only on session count (`>= min_sessions`). Phase 3 — and only Phase 3 — applies the project-count filter when computing the cross-project subset. Landed in `7a65047`.

**Generalization.** When a multi-phase algorithm has phase-specific eligibility rules, filter boundaries must coincide with phase boundaries. "Eligible to be considered as a candidate" and "eligible to be included in cross-project analysis" are *different* predicates and live in different phases. Collapsing them silently rewrites the algorithm's domain.

**Ref.** `convention_epidemiology.py`, `_phase1_candidates()` vs `_phase3_propagation()`.

## 4. `int(0.1 * N)` truncates a lower-bound percentage threshold

**Bug.** The NLSpec required "appears in at least 10% of sessions". Implementation: `min_count = int(0.1 * total_sessions)`. At `N = 59`, `int(5.9) = 5`, so a bigram with 5 occurrences (8.5% support) passed the "≥10%" rule.

**Fix.** `min_count = math.ceil(0.1 * total_sessions)`. Landed in `19825bb`.

**Generalization.** Percentage thresholds from a spec must round in the direction that *preserves* the inequality. For lower bounds: `ceil`. For upper bounds: `floor`. `int()` truncates toward zero and does neither — it silently relaxes lower bounds and tightens upper bounds. Audit every `int(fraction * N)` in spec-derived code.

**Ref.** `convention_epidemiology.py`, candidate filter; same pattern repaired in `lag_sequential.py` minimum-cell-count.

## 5. NCD is asymmetric under zlib and must be symmetrized before clustering

**Bug.** `ncd_clustering.py` computed `NCD(x, y) = (C(x+y) - min(C(x), C(y))) / max(C(x), C(y))` in a single direction. zlib's sliding window finds different match patterns depending on byte order, so `C(x+y) != C(y+x)` in general. The resulting distance matrix was non-symmetric; `scipy.spatial.distance.squareform` accepted it (it only checks the upper triangle), and `linkage` produced a tree that depended on the input session ordering. The same corpus produced different `optimal_k` values across reshuffles.

**Fix.** Compute both concatenations and take `min(C(x+y), C(y+x))` in the numerator. Landed in `bdd2c3a`.

**Generalization.** Any distance built on a directional operation — compression, convolution, RNN encoding, autoregressive scoring — must be explicitly symmetrized before being fed to a clustering algorithm that assumes a metric. "Looks symmetric in the formula" is not the same as "is symmetric under the implementation".

**Ref.** `ncd_clustering.py`, `_ncd_pair()`.

## 6. Project-id path heuristic took three iterations to converge

**Bug.** With no filesystem access at analysis time, `project_id` had to be derived from the `cwd` string alone. Three iterations:

- **v1** (`61f602b`): take last 2 path components. `/repo/src` and `/repo/tests` hashed differently — same project split into sibling buckets.
- **v2** (`ad6ba24`): strip a blocklist of known subtree names (`src`, `tests`, `lib`, `api`, `service`, `backend`, `web`, …) and take the last component. `/team-a/service` and `/team-b/service` collided on `service` — different repos merged into one bucket.
- **v3** (`b590e4b`): narrow the blocklist (remove repo-name-like entries: `api`, `service`, `backend`, `web`) and take the last 2 *post-strip* components. Survives the cases that broke v1 and v2.

**Generalization.** When a heuristic has no authoritative ground truth (we can't walk to find `.git`), expect 3-5 iterations to converge. Each failing case is free test data for the next iteration — preserve the failing inputs as fixtures, not just the fix.

**Ref.** `convention_epidemiology.py`, `_derive_project_id()`.

## 7. SciPy hierarchical clustering needs ≥2 observations, not ≥1

**Bug.** `ncd_clustering.py` guarded against the empty case with `if not streams: return insufficient_data`. At exactly *one* stream surviving the length filter, it fell through, built a 1×1 distance matrix, and `scipy.cluster.hierarchy.linkage` raised `ValueError: The number of observations cannot be determined on an empty distance matrix` — except the matrix wasn't empty, it was degenerate.

**Fix.** Guard is `if len(streams) < 2`. Landed in `bdd2c3a`.

**Generalization.** Library minimum-input requirements are often "≥2", not "≥1". Off-by-one guards are silent in normal operation and only crash on the smallest non-empty corpus — exactly the case unit tests are least likely to construct. Audit every clustering/regression/correlation call for its true minimum.

**Ref.** `ncd_clustering.py`, `_cluster()`.

## 8. Match by positional index, not by content-derived session id

**Bug.** Phase 3 of `convention_epidemiology.py` built a set of session ids from the session objects and used it to filter adopters. Parser-assigned session ids fall back to the file stem when no id field is present (Codex sessions, some OpenClaw exports), and file stems are not guaranteed unique across merged corpora — `corpus-split/interactive/` and `corpus-split/subagent/` can produce stem collisions. The result: two distinct sessions counted as one adopter, deflating reach.

**Fix.** Iterate `bigram_sessions[bg]` directly. That structure already holds the int positional indices from an earlier `enumerate()` over the corpus — guaranteed unique per run. Landed in `ad6ba24`.

**Generalization.** When matching items for "identity *in this run*", use the positional index from `enumerate()`, not a content-derived key. Content-derived keys are only safe if you've audited their uniqueness guarantees across every corpus source you'll ever merge. Positional indices have a uniqueness guarantee from Python itself.

**Ref.** `convention_epidemiology.py`, Phase 3 adopter loop.

## References

Commits in iteration order (squashed into `9eca691` on merge):

- `61f602b` — initial Batch 3 implementation
- `34f32d1` — `_unknown` bucket exclusion in propagation
- `6ec82cd` — symmetric boundary semantics for reach classification
- `7a65047` — Phase-1/Phase-3 filter separation
- `19825bb` — `math.ceil` for lower-bound percentage thresholds
- `bdd2c3a` — NCD symmetrization + `< 2` clustering guard
- `ad6ba24` — project-id heuristic v2 + positional-index adopter matching
- `b590e4b` — project-id heuristic v3 (narrowed blocklist)
- `9eca691` — squash merge to `main`

Spec: `middens/docs/nlspecs/2026-04-06-python-techniques-batch3-nlspec.md`.
Tests: `middens/tests/features/techniques/python_batch3.feature`, `middens/tests/steps/python_batch1.rs`.
