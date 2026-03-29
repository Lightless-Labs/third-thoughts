#!/usr/bin/env python3
"""
Granger Causality Analysis of Claude Code Sessions

Tests whether one time series (e.g. thinking block length) "Granger-causes"
another (e.g. correction probability) -- i.e., whether past values of X
improve prediction of Y beyond Y's own past.

Time series per session:
- thinking_ratio: fraction of assistant text that is thinking
- tool_diversity: Shannon entropy of tool types used (rolling window)
- message_length: log-scaled text length
- correction_indicator: binary, is this turn a user correction?
- tool_failure_indicator: binary, did a tool fail?

Tests all pairwise Granger causality at lags 1-5 with Bonferroni correction.

Source: Claude Code session JSONL files (full corpus)
"""

import json
import glob
import os
import re
import sys
import random
import warnings
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

try:
    from statsmodels.tsa.stattools import grangercausalitytests
except ImportError:
    print("Installing statsmodels...")
    os.system("pip3 install statsmodels")
    from statsmodels.tsa.stattools import grangercausalitytests

warnings.filterwarnings("ignore")

# ============================================================
# Configuration
# ============================================================

SESSION_GLOB = os.environ.get("SESSION_GLOB", os.path.join(os.environ.get("MIDDENS_CORPUS", "corpus/"), "**/*.jsonl"))
OUTPUT_DIR = os.environ.get("OUTPUT_DIR", os.environ.get("MIDDENS_OUTPUT", "experiments/"))
MAX_SESSIONS = 200
MIN_TURNS_PER_SESSION = 25  # Need enough for lag analysis
MAX_LAGS = 5
ALPHA = 0.05
RANDOM_SEED = 42

# Correction patterns (from prior experiments)
CORRECTION_PATTERNS = [
    r"^no[,.\s!]",
    r"^wrong", r"^actually[,\s]", r"^why did you",
    r"^don'?t\s", r"^stop\b(?! hook)",
    r"^revert", r"^undo", r"^try again",
    r"^that'?s not", r"^that is not", r"^not what i",
    r"^i said", r"^i meant", r"^i asked",
    r"^wait[,.\s]", r"^hold on", r"^nope",
    r"^incorrect", r"^fix\s", r"^instead[,\s]",
    r"^you (should|need|forgot|missed|broke|didn)",
    r"^please (don|stop|revert|undo|fix)",
    r"^this (is wrong|isn't|doesn't|broke|failed)",
    r"^it (should|shouldn't|doesn't|didn't|broke|failed)",
    r"^that (broke|failed|isn't right|is incorrect)",
    r"\bwrong\b.*\bshould\b",
]
CORRECTION_RE = re.compile("|".join(CORRECTION_PATTERNS), re.IGNORECASE)

CORRECTION_EXCLUSIONS = [
    r"stop hook", r"^#\s", r"^```",
    r"deepen plan", r"power enhancement",
    r"this session is being continued",
    r"^you are \w+, an",
]
CORRECTION_EXCLUSION_RE = re.compile("|".join(CORRECTION_EXCLUSIONS), re.IGNORECASE)

# Tool categories
READ_TOOLS = {"Read", "Glob", "Grep"}
EDIT_TOOLS = {"Edit", "Write"}
BASH_TOOLS = {"Bash"}
ALL_TOOL_TYPES = ["Read", "Glob", "Grep", "Edit", "Write", "Bash",
                  "WebSearch", "WebFetch", "Skill", "ToolSearch", "Other"]

os.makedirs(OUTPUT_DIR, exist_ok=True)


# ============================================================
# Data Loading (follows patterns from burstiness_hawkes.py)
# ============================================================

def extract_user_text(msg):
    """Extract text content from a user message."""
    content = msg.get("message", {}).get("content", "")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                return block["text"].strip()
    return ""


def is_correction(text):
    """Check if user text is a correction."""
    if not text:
        return False
    if text.startswith("[") or text.startswith("<"):
        return False
    if CORRECTION_EXCLUSION_RE.search(text):
        return False
    return bool(CORRECTION_RE.search(text))


def is_tool_result_message(msg):
    """Check if a user message is purely a tool_result."""
    content = msg.get("message", {}).get("content", "")
    if isinstance(content, list):
        has_tool_result = False
        has_human_text = False
        for block in content:
            if isinstance(block, dict):
                if block.get("type") == "tool_result":
                    has_tool_result = True
                elif block.get("type") == "text":
                    text = block.get("text", "").strip()
                    if text and not text.startswith("<") and not text.startswith("["):
                        has_human_text = True
        if has_tool_result and not has_human_text:
            return True
    return False


def detect_tool_failure(msg):
    """Check if a user message contains a tool_result with is_error=True."""
    content = msg.get("message", {}).get("content", "")
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_result":
                if block.get("is_error"):
                    return True
    return False


def has_thinking(msg):
    """Check if assistant message has a thinking block."""
    content = msg.get("message", {}).get("content", [])
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") == "thinking":
                return True
    return False


def get_thinking_length(msg):
    """Get total length of thinking blocks."""
    content = msg.get("message", {}).get("content", [])
    total = 0
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") == "thinking":
                total += len(block.get("thinking", ""))
    return total


def get_text_length(msg):
    """Get total text content length (non-thinking)."""
    content = msg.get("message", {}).get("content", [])
    total = 0
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict):
                if block.get("type") == "text":
                    total += len(block.get("text", ""))
            elif isinstance(block, str):
                total += len(block)
    elif isinstance(content, str):
        total = len(content)
    return total


def get_tool_names(msg):
    """Extract all tool names from an assistant message."""
    content = msg.get("message", {}).get("content", [])
    tools = []
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_use":
                tools.append(block.get("name", "unknown"))
    return tools


def is_automated_session(session_path):
    """Check if a session is an automated agent loop."""
    try:
        with open(session_path) as f:
            for line in f:
                try:
                    msg = json.loads(line)
                    if msg.get("type") in ("user", "message"):
                        role = msg.get("message", {}).get("role", msg.get("type", ""))
                        if role == "user":
                            text = extract_user_text(msg)
                            if text and "autonomous agent running in a loop" in text.lower():
                                return True
                            if text and "you are boucle" in text.lower():
                                return True
                            break
                except (json.JSONDecodeError, UnicodeDecodeError):
                    continue
    except Exception:
        return False
    return False


def shannon_entropy(counts):
    """Compute Shannon entropy from a Counter."""
    total = sum(counts.values())
    if total == 0:
        return 0.0
    entropy = 0.0
    for c in counts.values():
        if c > 0:
            p = c / total
            entropy -= p * np.log2(p)
    return entropy


def extract_session_timeseries(session_path, max_lines=30000):
    """
    Extract per-interaction-round time series from a session.

    An "interaction round" groups an assistant turn with its context:
    - thinking_ratio: thinking_length / (thinking_length + text_length)
    - tool_diversity: Shannon entropy of tool types in a rolling window of 5 rounds
    - message_length: log1p of assistant text length
    - correction_indicator: 1 if the next user message is a correction, 0 otherwise
    - tool_failure_indicator: 1 if a tool failure occurs in this round, 0 otherwise
    """
    turns = []
    with open(session_path, 'r') as f:
        for i, line in enumerate(f):
            if i >= max_lines:
                break
            try:
                obj = json.loads(line)
                msg_type = obj.get("type")
                if msg_type == "message":
                    role = obj.get("message", {}).get("role", "")
                    if role in ("user", "assistant"):
                        obj["type"] = role
                        turns.append(obj)
                elif msg_type in ("user", "assistant"):
                    turns.append(obj)
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue

    # Build per-assistant-turn records
    records = []
    for idx, turn in enumerate(turns):
        if turn.get("type") != "assistant":
            continue

        # Thinking ratio
        think_len = get_thinking_length(turn)
        text_len = get_text_length(turn)
        total_len = think_len + text_len
        thinking_ratio = think_len / total_len if total_len > 0 else 0.0

        # Message length (log-scaled)
        msg_length = np.log1p(text_len)

        # Tools used
        tool_names = get_tool_names(turn)

        # Look ahead for correction and failure
        correction = 0.0
        failure = 0.0
        for j in range(idx + 1, min(idx + 4, len(turns))):
            future = turns[j]
            if future.get("type") == "user":
                if is_tool_result_message(future):
                    if detect_tool_failure(future):
                        failure = 1.0
                else:
                    text = extract_user_text(future)
                    if text and is_correction(text):
                        correction = 1.0
                    break  # Only look at next real user message

        records.append({
            "thinking_ratio": thinking_ratio,
            "msg_length": msg_length,
            "tool_names": tool_names,
            "correction": correction,
            "failure": failure,
        })

    if len(records) < MIN_TURNS_PER_SESSION:
        return None

    # Compute rolling tool diversity (Shannon entropy over window of 5)
    window = 5
    diversities = []
    for i in range(len(records)):
        start = max(0, i - window + 1)
        tool_counter = Counter()
        for j in range(start, i + 1):
            for t in records[j]["tool_names"]:
                tool_counter[t] += 1
        diversities.append(shannon_entropy(tool_counter))

    # Build final time series arrays
    ts = {
        "thinking_ratio": np.array([r["thinking_ratio"] for r in records]),
        "tool_diversity": np.array(diversities),
        "message_length": np.array([r["msg_length"] for r in records]),
        "correction_indicator": np.array([r["correction"] for r in records]),
        "tool_failure_indicator": np.array([r["failure"] for r in records]),
    }

    return ts


def load_sessions(max_n=MAX_SESSIONS):
    """Load sessions with balanced source sampling."""
    files = glob.glob(SESSION_GLOB, recursive=True)
    random.seed(RANDOM_SEED)
    random.shuffle(files)

    # Group by source
    source_files = defaultdict(list)
    for fpath in files:
        parts = fpath.split("/")
        found = False
        for i, p in enumerate(parts):
            if p in ("corpus-full", "interactive", "subagent") and i + 1 < len(parts):
                source_files[parts[i + 1]].append(fpath)
                found = True
                break
        if not found:
            source_files["unknown"].append(fpath)

    sessions = {}
    skipped_auto = 0
    skipped_small = 0

    ordered_sources = sorted(source_files.keys(), key=lambda s: len(source_files[s]))
    source_idx = {s: 0 for s in ordered_sources}

    for pass_num in range(20):
        if len(sessions) >= max_n:
            break
        for source in ordered_sources:
            if len(sessions) >= max_n:
                break
            sfiles = source_files[source]
            start = source_idx[source]
            for fpath in sfiles[start:start + 5]:
                if len(sessions) >= max_n:
                    break
                source_idx[source] += 1

                try:
                    if is_automated_session(fpath):
                        skipped_auto += 1
                        continue
                    ts = extract_session_timeseries(fpath)
                except Exception:
                    continue

                if ts is None:
                    skipped_small += 1
                    continue

                sid = os.path.basename(fpath).replace(".jsonl", "")
                sessions[sid] = ts

    print(f"  Loaded: {len(sessions)} sessions")
    print(f"  Skipped (automated): {skipped_auto}")
    print(f"  Skipped (too small): {skipped_small}")
    return sessions


# ============================================================
# Granger Causality Testing
# ============================================================

SERIES_NAMES = [
    "thinking_ratio",
    "tool_diversity",
    "message_length",
    "correction_indicator",
    "tool_failure_indicator",
]


def test_granger_pair(x, y, max_lag=MAX_LAGS):
    """
    Test Granger causality: does X Granger-cause Y?
    Returns dict of {lag: min_p_value} across the 4 tests.
    """
    # Ensure no constant series
    if np.std(x) < 1e-10 or np.std(y) < 1e-10:
        return None

    data = np.column_stack([y, x])

    try:
        results = grangercausalitytests(data, maxlag=max_lag, verbose=False)
    except Exception:
        return None

    lag_results = {}
    for lag in range(1, max_lag + 1):
        if lag not in results:
            continue
        tests = results[lag][0]
        # Get minimum p-value across all 4 tests
        p_values = []
        for test_name in ["ssr_ftest", "ssr_chi2test", "lrtest", "params_ftest"]:
            if test_name in tests:
                p_values.append(tests[test_name][1])
        if p_values:
            lag_results[lag] = min(p_values)

    return lag_results if lag_results else None


def run_pairwise_granger(sessions):
    """
    Run pairwise Granger causality tests across all sessions.
    Aggregate p-values using Fisher's method.
    """
    n_pairs = len(SERIES_NAMES) * (len(SERIES_NAMES) - 1)
    n_tests = n_pairs * MAX_LAGS
    bonferroni_alpha = ALPHA / n_tests

    print(f"  Testing {n_pairs} directed pairs at {MAX_LAGS} lags each")
    print(f"  Total tests: {n_tests}")
    print(f"  Bonferroni-corrected alpha: {bonferroni_alpha:.6f}")

    # Collect per-session results for each pair
    pair_results = {}
    for x_name in SERIES_NAMES:
        for y_name in SERIES_NAMES:
            if x_name == y_name:
                continue
            pair_results[(x_name, y_name)] = {lag: [] for lag in range(1, MAX_LAGS + 1)}

    n_sessions_used = 0
    for sid, ts in sessions.items():
        has_data = False
        for x_name in SERIES_NAMES:
            for y_name in SERIES_NAMES:
                if x_name == y_name:
                    continue
                x = ts[x_name]
                y = ts[y_name]
                result = test_granger_pair(x, y, MAX_LAGS)
                if result:
                    has_data = True
                    for lag, p in result.items():
                        pair_results[(x_name, y_name)][lag].append(p)
        if has_data:
            n_sessions_used += 1

    print(f"  Sessions with valid Granger tests: {n_sessions_used}")

    # Aggregate: Fisher's combined probability test
    # chi2 = -2 * sum(log(p_i)), df = 2*k, under H0
    from scipy.stats import chi2 as chi2_dist

    aggregated = {}
    for (x_name, y_name), lag_pvals in pair_results.items():
        for lag, pvals in lag_pvals.items():
            if len(pvals) < 5:
                continue

            # Filter out NaN and exact 0/1 p-values (numerical issues)
            valid_pvals = [p for p in pvals if 0 < p < 1 and np.isfinite(p)]
            if len(valid_pvals) < 5:
                continue

            # Fisher's method
            fisher_stat = -2.0 * sum(np.log(p) for p in valid_pvals)
            df = 2 * len(valid_pvals)
            combined_p = 1.0 - chi2_dist.cdf(fisher_stat, df)

            # Also compute fraction of sessions where p < 0.05
            frac_sig = sum(1 for p in valid_pvals if p < 0.05) / len(valid_pvals)

            # Median p-value
            median_p = np.median(valid_pvals)

            aggregated[(x_name, y_name, lag)] = {
                "fisher_p": combined_p,
                "median_p": median_p,
                "frac_significant": frac_sig,
                "n_sessions": len(valid_pvals),
                "significant_bonferroni": combined_p < bonferroni_alpha,
            }

    return aggregated, bonferroni_alpha, n_sessions_used


# ============================================================
# Pooled Analysis
# ============================================================

def run_pooled_granger(sessions):
    """
    Pool all sessions into long time series (with breaks) and run
    Granger causality on the pooled data for additional statistical power.
    """
    # Concatenate all sessions (with NaN separators to break autocorrelation)
    pooled = {name: [] for name in SERIES_NAMES}
    for sid, ts in sessions.items():
        for name in SERIES_NAMES:
            pooled[name].extend(ts[name].tolist())
            # Add NaN separator between sessions (will be interpolated)
            pooled[name].append(np.nan)

    # Remove trailing NaN and interpolate internal NaNs
    for name in SERIES_NAMES:
        arr = np.array(pooled[name][:-1])  # drop last NaN
        # Linear interpolation of NaN separators
        nans = np.isnan(arr)
        if nans.any():
            not_nan = ~nans
            indices = np.arange(len(arr))
            arr[nans] = np.interp(indices[nans], indices[not_nan], arr[not_nan])
        pooled[name] = arr

    print(f"  Pooled time series length: {len(pooled[SERIES_NAMES[0]])}")

    results = {}
    for x_name in SERIES_NAMES:
        for y_name in SERIES_NAMES:
            if x_name == y_name:
                continue
            x = pooled[x_name]
            y = pooled[y_name]

            result = test_granger_pair(x, y, MAX_LAGS)
            if result:
                for lag, p in result.items():
                    results[(x_name, y_name, lag)] = p

    return results


# ============================================================
# Main
# ============================================================

def main():
    print("=" * 70)
    print("GRANGER CAUSALITY ANALYSIS OF CLAUDE CODE SESSIONS")
    print("=" * 70)

    # Step 1: Load sessions
    print("\n[1/4] Loading sessions...")
    sessions = load_sessions(MAX_SESSIONS)
    if len(sessions) < 10:
        print("ERROR: Too few sessions loaded. Aborting.")
        sys.exit(1)

    # Session statistics
    total_turns = sum(len(ts[SERIES_NAMES[0]]) for ts in sessions.values())
    print(f"  Total assistant turns across sessions: {total_turns}")

    # Step 2: Descriptive statistics
    print("\n[2/4] Computing descriptive statistics...")
    desc_stats = {}
    for name in SERIES_NAMES:
        all_vals = np.concatenate([ts[name] for ts in sessions.values()])
        desc_stats[name] = {
            "mean": np.mean(all_vals),
            "std": np.std(all_vals),
            "median": np.median(all_vals),
            "min": np.min(all_vals),
            "max": np.max(all_vals),
            "nonzero_frac": np.mean(all_vals > 0),
        }
        print(f"  {name}: mean={desc_stats[name]['mean']:.3f}, "
              f"std={desc_stats[name]['std']:.3f}, "
              f"nonzero={desc_stats[name]['nonzero_frac']:.1%}")

    # Step 3: Pairwise Granger causality (per-session, Fisher aggregation)
    print("\n[3/4] Running pairwise Granger causality tests (per-session, Fisher aggregation)...")
    aggregated, bonferroni_alpha, n_used = run_pairwise_granger(sessions)

    # Step 4: Pooled Granger causality
    print("\n[4/4] Running pooled Granger causality tests...")
    pooled_results = run_pooled_granger(sessions)

    # ── Output ──────────────────────────────────────────────────────
    output_lines = []
    output_lines.append("=" * 70)
    output_lines.append("GRANGER CAUSALITY ANALYSIS OF CLAUDE CODE SESSIONS")
    output_lines.append("=" * 70)
    output_lines.append(f"\nSessions analyzed: {len(sessions)}")
    output_lines.append(f"Sessions with valid tests: {n_used}")
    output_lines.append(f"Total assistant turns: {total_turns}")
    output_lines.append(f"Max lags tested: {MAX_LAGS}")
    output_lines.append(f"Bonferroni-corrected alpha: {bonferroni_alpha:.6f}")

    # Descriptive stats
    output_lines.append("\n--- Descriptive Statistics ---")
    output_lines.append(f"{'Series':<28} {'Mean':<10} {'Std':<10} {'Median':<10} {'Nonzero%'}")
    for name in SERIES_NAMES:
        s = desc_stats[name]
        output_lines.append(
            f"  {name:<26} {s['mean']:<10.4f} {s['std']:<10.4f} "
            f"{s['median']:<10.4f} {s['nonzero_frac']:.1%}"
        )

    # Significant results (Fisher aggregation)
    output_lines.append("\n--- Significant Granger Causal Relationships (Fisher Aggregation) ---")
    output_lines.append(f"{'X -> Y':<55} {'Lag':<5} {'Fisher p':<12} {'Median p':<12} {'Frac Sig':<10} {'N'}")

    sig_results = [(k, v) for k, v in aggregated.items() if v["significant_bonferroni"]]
    sig_results.sort(key=lambda x: x[1]["fisher_p"])

    if sig_results:
        for (x_name, y_name, lag), v in sig_results:
            label = f"{x_name} -> {y_name}"
            output_lines.append(
                f"  {label:<53} {lag:<5} {v['fisher_p']:<12.2e} "
                f"{v['median_p']:<12.4f} {v['frac_significant']:<10.1%} {v['n_sessions']}"
            )
    else:
        output_lines.append("  No relationships survived Bonferroni correction.")

    # All results table (sorted by Fisher p-value)
    output_lines.append("\n--- All Pairwise Results (Best Lag Only, Sorted by Fisher p) ---")
    output_lines.append(f"{'X -> Y':<55} {'Best Lag':<10} {'Fisher p':<12} {'Median p':<12} {'Frac Sig':<10} {'Sig?'}")

    # For each pair, find best lag
    best_per_pair = {}
    for (x_name, y_name, lag), v in aggregated.items():
        key = (x_name, y_name)
        if key not in best_per_pair or v["fisher_p"] < best_per_pair[key][1]["fisher_p"]:
            best_per_pair[key] = ((x_name, y_name, lag), v)

    sorted_pairs = sorted(best_per_pair.values(), key=lambda x: x[1]["fisher_p"])
    for (x_name, y_name, lag), v in sorted_pairs:
        label = f"{x_name} -> {y_name}"
        sig_marker = "***" if v["significant_bonferroni"] else ""
        output_lines.append(
            f"  {label:<53} {lag:<10} {v['fisher_p']:<12.2e} "
            f"{v['median_p']:<12.4f} {v['frac_significant']:<10.1%} {sig_marker}"
        )

    # Pooled results
    output_lines.append("\n--- Pooled Granger Causality (All Sessions Concatenated) ---")
    output_lines.append(f"{'X -> Y':<55} {'Lag':<5} {'p-value':<12} {'Significant?'}")

    n_pooled_tests = len(pooled_results)
    pooled_alpha = ALPHA / max(n_pooled_tests, 1)
    sorted_pooled = sorted(pooled_results.items(), key=lambda x: x[1])
    for (x_name, y_name, lag), p in sorted_pooled:
        label = f"{x_name} -> {y_name}"
        sig = "***" if p < pooled_alpha else ""
        output_lines.append(f"  {label:<53} {lag:<5} {p:<12.2e} {sig}")

    # Causal summary
    output_lines.append("\n--- Causal Relationship Summary ---")
    output_lines.append("(Relationships significant in BOTH Fisher aggregation AND pooled analysis)")

    pooled_sig_pairs = set()
    for (x_name, y_name, lag), p in pooled_results.items():
        if p < pooled_alpha:
            pooled_sig_pairs.add((x_name, y_name))

    fisher_sig_pairs = set()
    for (x_name, y_name, lag), v in aggregated.items():
        if v["significant_bonferroni"]:
            fisher_sig_pairs.add((x_name, y_name))

    both_sig = fisher_sig_pairs & pooled_sig_pairs
    if both_sig:
        for x_name, y_name in sorted(both_sig):
            output_lines.append(f"  {x_name} -> {y_name}")
            # Find best lag from Fisher
            best_lag = None
            best_p = 1.0
            for (xn, yn, lag), v in aggregated.items():
                if xn == x_name and yn == y_name and v["fisher_p"] < best_p:
                    best_p = v["fisher_p"]
                    best_lag = lag
            output_lines.append(f"    Best lag: {best_lag}, Fisher p: {best_p:.2e}")
            # Find best pooled lag
            pooled_best_lag = None
            pooled_best_p = 1.0
            for (xn, yn, lag), p in pooled_results.items():
                if xn == x_name and yn == y_name and p < pooled_best_p:
                    pooled_best_p = p
                    pooled_best_lag = lag
            output_lines.append(f"    Pooled best lag: {pooled_best_lag}, p: {pooled_best_p:.2e}")
    else:
        output_lines.append("  No relationships significant in both analyses.")
        # Fall back: show relationships significant in either
        either_sig = fisher_sig_pairs | pooled_sig_pairs
        if either_sig:
            output_lines.append("\n  Relationships significant in at least one analysis:")
            for x_name, y_name in sorted(either_sig):
                in_fisher = (x_name, y_name) in fisher_sig_pairs
                in_pooled = (x_name, y_name) in pooled_sig_pairs
                methods = []
                if in_fisher:
                    methods.append("Fisher")
                if in_pooled:
                    methods.append("Pooled")
                output_lines.append(f"    {x_name} -> {y_name} ({', '.join(methods)})")

    # Bidirectional relationships
    output_lines.append("\n--- Bidirectional Causal Relationships ---")
    output_lines.append("(Pairs where X->Y and Y->X are both significant)")
    found_bidir = False
    checked = set()
    for (x_name, y_name, lag), v in aggregated.items():
        pair = tuple(sorted([x_name, y_name]))
        if pair in checked:
            continue
        checked.add(pair)
        # Check both directions
        fwd_sig = any(
            aggregated.get((x_name, y_name, l), {}).get("significant_bonferroni", False)
            for l in range(1, MAX_LAGS + 1)
        )
        bwd_sig = any(
            aggregated.get((y_name, x_name, l), {}).get("significant_bonferroni", False)
            for l in range(1, MAX_LAGS + 1)
        )
        if fwd_sig and bwd_sig:
            found_bidir = True
            output_lines.append(f"  {x_name} <-> {y_name}")
    if not found_bidir:
        output_lines.append("  No bidirectional relationships found.")

    # Write output
    report = "\n".join(output_lines)
    print("\n" + report)

    output_path = os.path.join(OUTPUT_DIR, "granger_causality.txt")
    with open(output_path, "w") as f:
        f.write(report)
    print(f"\nResults written to: {output_path}")

    # Save detailed CSV
    csv_path = os.path.join(OUTPUT_DIR, "granger_causality_all_pairs.csv")
    with open(csv_path, "w") as f:
        f.write("x_series,y_series,lag,fisher_p,median_p,frac_significant,n_sessions,significant_bonferroni\n")
        for (x_name, y_name, lag), v in sorted(aggregated.items()):
            f.write(
                f"{x_name},{y_name},{lag},{v['fisher_p']:.6e},{v['median_p']:.6f},"
                f"{v['frac_significant']:.4f},{v['n_sessions']},{v['significant_bonferroni']}\n"
            )
    print(f"Detailed CSV: {csv_path}")


if __name__ == "__main__":
    main()
