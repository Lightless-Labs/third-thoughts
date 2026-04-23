---
title: Python scientific library API quirks blocking middens technique ports
date: 2026-04-06
last_updated: 2026-04-13
category: integration-issues
module: middens/python/techniques
problem_type: integration_issue
component: tooling
symptoms:
  - "AttributeError: 'GaussianHMM' object has no attribute '_n_parameters'"
  - "PrefixSpan.frequent() runs >30s and times out the bridge subprocess"
  - "InfeasibleTestError raised by grangercausalitytests bypasses except handler"
  - "SyntaxError / TypeError on `str | None` under Python 3.9"
root_cause: wrong_api
resolution_type: code_fix
severity: medium
related_components:
  - testing_framework
tags: [python, hmmlearn, prefixspan, statsmodels, middens, python-bridge, api-quirks, scientific-libraries]
---

# Python scientific library API quirks blocking middens technique ports

## Problem
While porting Batch 1+2 of the Python analytical techniques to run under the
middens Python bridge, four independent library/version quirks caused green-team
implementations to fail at runtime. Each is simple to fix once known, but each
cost iterations to discover.

## Symptoms
- `hmmlearn` BIC computation raised `AttributeError` on `_n_parameters()`
- `prefixspan.PrefixSpan(...).frequent(min_support)` timed out the bridge
  subprocess (>30s) on 5 sessions x ~35 tool calls
- `statsmodels.tsa.stattools.grangercausalitytests` raised `InfeasibleTestError`
  on constant (zero-variance) columns and bypassed the script's narrow
  except clause
- Type hints written as `str | None` failed under Python 3.9 (PEP 604 union
  syntax requires 3.10+)

## What Didn't Work
- Catching `(ValueError, np.linalg.LinAlgError, IndexError)` around the Granger
  call — `InfeasibleTestError` lives in `statsmodels.tools.sm_exceptions` and
  is not a subclass of those, so it propagates out
- Passing `maxlag=[max_lags]` (list) to `grangercausalitytests` — must be int
- Calling `model._n_parameters()` on `GaussianHMM` — the private method is gone
  in newer hmmlearn versions
- Calling `PrefixSpan.frequent(min_support)` and post-filtering — returns the
  full set of frequent subsequences, exponential in sequence length

## Solution

### Quirk 1: hmmlearn `_n_parameters()` removed
File: `middens/python/techniques/hsmm.py`

Compute the parameter count manually for a diagonal-covariance `GaussianHMM`:

```python
# Before (fails with AttributeError):
log_likelihood = model.score(features, lengths)
n_params = model._n_parameters()
bic = n_params * np.log(features.shape[0]) - 2 * log_likelihood

# After:
log_likelihood = model.score(features, lengths)
n = n_components
d = features.shape[1]
n_params = n * (n - 1) + 2 * n * d  # transitions + means + diag covars
bic = n_params * np.log(features.shape[0]) - 2 * log_likelihood
```

### Quirk 2: PrefixSpan combinatorial explosion
File: `middens/python/techniques/prefixspan_mining.py`

Use `topk` to bound the search, and note the tuple order flips between APIs
(`frequent` returns `(pattern, support)`, `topk` returns `(support, pattern)`):

```python
# Before (times out):
ps = PrefixSpan(sequences)
patterns = ps.frequent(min_support)  # returns ALL frequent subsequences

# After:
ps = PrefixSpan(sequences)
all_patterns = ps.topk(200)  # top 200 patterns by support
filtered_patterns = [
    (pattern, support)
    for support, pattern in all_patterns
    if 3 <= len(pattern) <= 6 and support >= min_support
]
```

> **Note (2026-04-13):** An earlier version of this fix used `topk(200, closed=True)`.
> The `closed=True` flag turned out to trigger O(n²) closed-pattern filtering
> across the full candidate set, which timed out on corpora with ~13k sequences.
> Drop `closed=True`. See
> `docs/solutions/performance-issues/prefixspan-closed-flag-quadratic-timeout-20260413.md`
> for the full investigation, including two collateral bugs (row-shape mismatch,
> off-by-index cohort building) that were unmasked when output resumed.

### Quirk 3: statsmodels `InfeasibleTestError` on constant columns
File: `middens/python/techniques/granger_causality.py`

Use a broad `except Exception` (the failure modes are many and we just want
to skip degenerate pairs), and pass `maxlag` as an int:

```python
# Before:
try:
    test_result = grangercausalitytests(
        df[[effect, cause]], maxlag=[max_lags], verbose=False
    )
    # ...
except (ValueError, np.linalg.LinAlgError, IndexError):
    continue

# After:
try:
    test_result = grangercausalitytests(
        df[[effect, cause]], maxlag=max_lags, verbose=False
    )
    # ...
except Exception:
    continue
```

### Quirk 4: Python 3.9 type hint syntax
Target environment is Python 3.9; PEP 604 union syntax requires 3.10+.
Use `Optional[T]` from `typing`:

```python
# Before (SyntaxError under 3.9):
def foo(name: str | None) -> dict | None: ...

# After:
from typing import Optional
def foo(name: Optional[str]) -> Optional[dict]: ...
```

## Why This Works
- **hmmlearn**: `_n_parameters()` was a private helper; the formula
  `n*(n-1) + 2*n*d` is the standard count for a diagonal-covariance Gaussian
  HMM (transition rows minus the row-stochastic constraint, plus means and
  diagonal variances per state). Computing it directly removes the dependency
  on a private API that has churned across versions.
- **PrefixSpan**: `frequent()` enumerates the full lattice of frequent
  subsequences, which is exponential. `topk(k)` bounds the result to the
  top-k by support, which is far cheaper and usually what you actually want.
  Do not add `closed=True` — it triggers a post-mining O(n²) closed-pattern
  filter that re-times-out on large corpora.
- **statsmodels**: `InfeasibleTestError` is a custom exception in
  `statsmodels.tools.sm_exceptions` and is not a subclass of the numerical
  errors the original handler caught. Constant columns produce zero-variance
  regressors that the F-test cannot evaluate. A broad `except Exception` is
  appropriate here because the script's policy is "skip degenerate pairs",
  not "diagnose them".
- **Type hints**: PEP 604 (`X | Y`) is purely syntactic and requires the
  3.10+ parser. `typing.Optional` is the 3.9-compatible spelling.

## Prevention
- Pin scientific Python deps in the bridge environment and document the
  minimum versions tested. When upgrading hmmlearn/prefixspan/statsmodels,
  re-run the full middens scenario suite.
- For Python technique scripts, default the exception policy for "skip
  degenerate inputs" code paths to a broad `except Exception` with a logged
  reason, rather than enumerating numerical exceptions.
- Constrain combinatorial mining APIs with explicit bounds (`topk`, max pattern
  length) instead of post-filtering — the cost is in the search, not the
  filter. Avoid `closed=True` on large corpora — it adds an O(n²) post-filter.
- Lint Python technique scripts under the target interpreter version
  (currently 3.9) before merging. A simple `python3.9 -c "import ast;
  ast.parse(open('script.py').read())"` catches PEP 604 regressions.
- For each new ported technique, add a smoke-test scenario that runs the
  script end-to-end through the bridge against a small fixture, so
  library-API breakage surfaces in CI rather than in the next batch.

## Related Issues
- `docs/HANDOFF.md` — Phase 4 Python bridge infrastructure (commit 52638bd)
- `middens/python/techniques/echo.py` — bridge smoke-test fixture
- `middens/tests/features/` — Cucumber scenarios validating the bridge
  (240 scenarios, 1242 steps green after these fixes)
