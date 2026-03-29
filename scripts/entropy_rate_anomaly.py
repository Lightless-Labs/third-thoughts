#!/usr/bin/env python3
"""
Entropy Rate Anomaly Detection in Claude Code Sessions

Measures the predictability of agent behavior over time within sessions.
Computes the entropy rate of tool-call sequences and detects anomalies --
sessions or segments where behavior becomes unusually unpredictable (high
entropy) or rigid (low entropy).

Method:
1. Encode tool calls as symbols
2. Compute sliding-window entropy rate using conditional entropy:
   H(X_n | X_{n-1}, ..., X_{n-k}) for k=1,2,3
3. Flag anomalous windows where entropy exceeds mean +/- 2 sigma
4. Correlate entropy anomalies with corrections, tool failures, and change points
5. Compare entropy profiles across projects and session types

Output: anomaly report with entropy profiles and correlations.
"""

import json
import os
import sys
import re
import random
import math
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

# ──────────────────────────────────────────────────────────────────────
# Configuration
# ──────────────────────────────────────────────────────────────────────

CORPUS_DIR = os.environ.get("MIDDENS_CORPUS", "corpus/")
OUTPUT_DIR = os.environ.get("MIDDENS_OUTPUT", "experiments/")
MAX_SESSIONS = 200
MIN_TOOL_CALLS = 30  # Minimum tool calls in a session to analyze
WINDOW_SIZE = 15  # Sliding window size for entropy computation
ANOMALY_SIGMA = 2.0  # Number of std deviations for anomaly threshold
K_VALUES = [1, 2, 3]  # Markov orders for conditional entropy

# Tool categories for symbol encoding
READ_TOOLS = {"Read", "Glob", "Grep"}
EDIT_TOOLS = {"Edit", "Write", "NotebookEdit"}
BASH_TOOLS = {"Bash"}
SEARCH_TOOLS = {"WebSearch", "WebFetch"}

# Symbol encoding for tool calls
TOOL_SYMBOLS = {
    "R": READ_TOOLS,    # Read operations
    "E": EDIT_TOOLS,    # Edit operations
    "B": BASH_TOOLS,    # Bash commands
    "S": SEARCH_TOOLS,  # Web search
    "O": None,          # Other tools (catch-all)
}

# System/automated message indicators
SYSTEM_INDICATORS = [
    "<command-", "<run_context", "<task-notification",
    "You are ", "## SECURITY", "# /", "<file-",
    "SYSTEM:", "Round:", "You are Boucle",
    "Stop hook", "Pre-tool", "Post-tool",
    "Hook ", "Permission",
    "<local-command-", "Unknown skill:",
    "[Request interrupted",
]

CORRECTION_PATTERNS = [
    r"\bno\b", r"\bwrong\b", r"\bnot that\b", r"\binstead\b",
    r"\bactually\b", r"\bwhy\b", r"\bdon'?t\b", r"\bstop\b",
    r"\bthat'?s not\b", r"\bnot what\b", r"\bincorrect\b",
    r"\bfix\b", r"\bredo\b",
]
CORRECTION_RE = re.compile("|".join(CORRECTION_PATTERNS), re.IGNORECASE)


# ──────────────────────────────────────────────────────────────────────
# Event extraction
# ──────────────────────────────────────────────────────────────────────

def extract_user_text(msg):
    content = msg.get("message", {}).get("content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        texts = []
        for c in content:
            if isinstance(c, dict) and c.get("type") == "text":
                texts.append(c.get("text", ""))
        return " ".join(texts)
    return ""


def is_tool_result(msg):
    if msg.get("toolUseResult"):
        return True
    content = msg.get("message", {}).get("content", [])
    if isinstance(content, list):
        return any(isinstance(c, dict) and c.get("type") == "tool_result" for c in content)
    return False


def has_error(msg):
    content = msg.get("message", {}).get("content", [])
    if isinstance(content, list):
        for c in content:
            if not isinstance(c, dict):
                continue
            if c.get("type") == "tool_result" and c.get("is_error"):
                return True
    return False


def is_correction(msg):
    text = extract_user_text(msg)
    if not text or len(text.strip()) < 2:
        return False
    stripped = text.strip()
    for indicator in SYSTEM_INDICATORS:
        if stripped.startswith(indicator):
            return False
    if len(stripped) < 500:
        return bool(CORRECTION_RE.search(stripped))
    return False


def encode_tool(tool_name):
    """Encode a tool name as a single symbol."""
    for symbol, tools in TOOL_SYMBOLS.items():
        if tools is None:
            continue
        if tool_name in tools:
            return symbol
    return "O"


def extract_session_data(filepath):
    """
    Extract tool call sequence, corrections, and errors from a session.
    Returns:
    - tool_sequence: list of (symbol, position_index)
    - corrections: list of position indices where corrections occur
    - errors: list of position indices where tool errors occur
    - all_tool_names: list of actual tool names (for detailed analysis)
    - project: inferred project name
    """
    tool_sequence = []
    corrections = []
    errors = []
    all_tool_names = []
    position = 0

    try:
        with open(filepath, 'r') as f:
            lines = f.readlines()
    except Exception:
        return [], [], [], [], "unknown"

    for line in lines:
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue

        msg_type = msg.get("type", "")

        if msg_type == "user":
            if is_tool_result(msg):
                if has_error(msg):
                    errors.append(position)
                continue
            if is_correction(msg):
                corrections.append(position)
            position += 1

        elif msg_type == "assistant":
            content = msg.get("message", {}).get("content", [])
            if isinstance(content, list):
                for block in content:
                    if not isinstance(block, dict):
                        continue
                    if block.get("type") == "tool_use":
                        tool_name = block.get("name", "unknown")
                        symbol = encode_tool(tool_name)
                        tool_sequence.append((symbol, position))
                        all_tool_names.append(tool_name)
                        position += 1

    # Extract project name
    parts = Path(filepath).parts
    project = "unknown"
    for i, p in enumerate(parts):
        if p in ("projects", "claude-code-live") and i + 1 < len(parts):
            project = parts[i + 1]
            break
        if p == "openclaw":
            project = "openclaw"
            break
        if p == "archived-cc":
            project = "archived-cc"
            break

    return tool_sequence, corrections, errors, all_tool_names, project


# ──────────────────────────────────────────────────────────────────────
# Entropy computation
# ──────────────────────────────────────────────────────────────────────

def compute_conditional_entropy(symbols, k):
    """
    Compute conditional entropy H(X_n | X_{n-1}, ..., X_{n-k}).

    Uses the chain rule: H(X_n | context) = H(context, X_n) - H(context)
    where context = (X_{n-1}, ..., X_{n-k}).
    """
    if len(symbols) <= k:
        return 0.0

    # Count k-grams and (k+1)-grams
    context_counts = Counter()
    joint_counts = Counter()

    for i in range(k, len(symbols)):
        context = tuple(symbols[i-k:i])
        joint = tuple(symbols[i-k:i+1])
        context_counts[context] += 1
        joint_counts[joint] += 1

    # H(context, X_n) - entropy of joint distribution
    total_joint = sum(joint_counts.values())
    h_joint = 0.0
    for count in joint_counts.values():
        if count > 0:
            p = count / total_joint
            h_joint -= p * math.log2(p)

    # H(context) - entropy of context distribution
    total_context = sum(context_counts.values())
    h_context = 0.0
    for count in context_counts.values():
        if count > 0:
            p = count / total_context
            h_context -= p * math.log2(p)

    return h_joint - h_context


def compute_sliding_entropy(symbols, k, window_size):
    """
    Compute sliding-window conditional entropy over the symbol sequence.
    Returns array of entropy values, one per window position.
    """
    if len(symbols) < window_size + k:
        return np.array([])

    entropy_values = []

    for start in range(len(symbols) - window_size + 1):
        window = symbols[start:start + window_size]
        h = compute_conditional_entropy(window, k)
        entropy_values.append(h)

    return np.array(entropy_values)


def compute_marginal_entropy(symbols, window_size):
    """Compute sliding-window marginal (zeroth-order) entropy."""
    if len(symbols) < window_size:
        return np.array([])

    entropy_values = []
    for start in range(len(symbols) - window_size + 1):
        window = symbols[start:start + window_size]
        counts = Counter(window)
        total = sum(counts.values())
        h = 0.0
        for count in counts.values():
            if count > 0:
                p = count / total
                h -= p * math.log2(p)
        entropy_values.append(h)

    return np.array(entropy_values)


# ──────────────────────────────────────────────────────────────────────
# Anomaly detection
# ──────────────────────────────────────────────────────────────────────

def detect_anomalies(entropy_values, sigma_threshold=ANOMALY_SIGMA):
    """
    Detect anomalous windows where entropy exceeds mean +/- sigma_threshold * std.
    Returns:
    - high_anomalies: list of (window_idx, entropy_value) for high-entropy windows
    - low_anomalies: list of (window_idx, entropy_value) for low-entropy windows
    - mean: global mean entropy
    - std: global std entropy
    """
    if len(entropy_values) < 5:
        return [], [], 0.0, 0.0

    mean = np.mean(entropy_values)
    std = np.std(entropy_values)

    if std < 1e-10:
        return [], [], mean, std

    high_threshold = mean + sigma_threshold * std
    low_threshold = mean - sigma_threshold * std

    high_anomalies = [(i, float(v)) for i, v in enumerate(entropy_values) if v > high_threshold]
    low_anomalies = [(i, float(v)) for i, v in enumerate(entropy_values) if v < low_threshold]

    return high_anomalies, low_anomalies, float(mean), float(std)


def correlate_with_events(anomaly_indices, event_positions, tool_count, window_size):
    """
    Check how many anomalous windows overlap with correction/error events.
    Returns correlation score (proportion of anomalies near events).
    """
    if not anomaly_indices or not event_positions:
        return 0.0

    # Map event positions to window indices
    # An event at position p falls in windows [p - window_size + 1, p]
    event_windows = set()
    for pos in event_positions:
        # Scale position to window index space
        # tool_sequence positions vs window indices
        w_idx = max(0, pos - window_size // 2)
        for offset in range(-2, 3):  # +/- 2 windows
            event_windows.add(w_idx + offset)

    n_near = sum(1 for idx, _ in anomaly_indices if idx in event_windows)
    return n_near / len(anomaly_indices)


# ──────────────────────────────────────────────────────────────────────
# Session discovery and sampling
# ──────────────────────────────────────────────────────────────────────

def find_session_files(base_dir):
    """Find JSONL session files, excluding subagent sessions."""
    session_files = []
    for dirpath, dirnames, filenames in os.walk(base_dir, followlinks=True):
        if 'subagents' in dirpath:
            continue
        for fname in filenames:
            if fname.endswith('.jsonl'):
                filepath = os.path.join(dirpath, fname)
                try:
                    size = os.path.getsize(filepath)
                    if 10_000 < size < 50_000_000:
                        session_files.append((filepath, size))
                except OSError:
                    continue
    return session_files


def sample_sessions(session_files, max_sessions):
    """Sample sessions with project diversity."""
    random.seed(42)
    by_project = defaultdict(list)
    for f, size in session_files:
        parts = Path(f).parts
        project = "unknown"
        for i, p in enumerate(parts):
            if p in ("projects", "claude-code-live") and i + 1 < len(parts):
                project = parts[i + 1]
                break
            if p == "openclaw":
                project = "openclaw"
                break
            if p == "archived-cc":
                project = "archived-cc"
                break
        by_project[project].append((f, size))

    sampled = []
    projects = list(by_project.keys())
    random.shuffle(projects)

    round_num = 0
    while len(sampled) < max_sessions and projects:
        still_have = []
        for proj in projects:
            files = by_project[proj]
            if round_num < len(files):
                sampled.append(files[round_num])
                if len(sampled) >= max_sessions:
                    break
            if round_num + 1 < len(files):
                still_have.append(proj)
        projects = still_have
        round_num += 1

    return sampled, by_project


# ──────────────────────────────────────────────────────────────────────
# Analysis
# ──────────────────────────────────────────────────────────────────────

def analyze_session(filepath):
    """Full entropy analysis for a single session."""
    tool_seq, corrections, errors, tool_names, project = extract_session_data(filepath)

    if len(tool_seq) < MIN_TOOL_CALLS:
        return None

    symbols = [s for s, _ in tool_seq]

    # Compute marginal entropy
    h0 = compute_marginal_entropy(symbols, WINDOW_SIZE)

    # Compute conditional entropies at different orders
    conditional_entropies = {}
    for k in K_VALUES:
        hk = compute_sliding_entropy(symbols, k, WINDOW_SIZE)
        if len(hk) > 0:
            conditional_entropies[k] = hk

    if not conditional_entropies:
        return None

    # Primary analysis uses k=1 (first-order Markov)
    primary_k = 1
    if primary_k not in conditional_entropies:
        primary_k = min(conditional_entropies.keys())

    h_primary = conditional_entropies[primary_k]

    # Detect anomalies
    high_anom, low_anom, mean_h, std_h = detect_anomalies(h_primary)

    # Correlate anomalies with corrections and errors
    corr_high = correlate_with_events(high_anom, corrections, len(tool_seq), WINDOW_SIZE)
    corr_low = correlate_with_events(low_anom, corrections, len(tool_seq), WINDOW_SIZE)
    err_high = correlate_with_events(high_anom, errors, len(tool_seq), WINDOW_SIZE)
    err_low = correlate_with_events(low_anom, errors, len(tool_seq), WINDOW_SIZE)

    # Tool distribution
    tool_counter = Counter(symbols)
    tool_name_counter = Counter(tool_names)

    # Entropy trajectory (divide session into thirds)
    n = len(h_primary)
    third = max(1, n // 3)
    early_h = float(np.mean(h_primary[:third]))
    mid_h = float(np.mean(h_primary[third:2*third]))
    late_h = float(np.mean(h_primary[2*third:]))

    # Entropy statistics at each k
    entropy_by_k = {}
    for k, hk in conditional_entropies.items():
        entropy_by_k[k] = {
            'mean': float(np.mean(hk)),
            'std': float(np.std(hk)),
            'min': float(np.min(hk)),
            'max': float(np.max(hk)),
        }

    return {
        'filepath': filepath,
        'project': project,
        'n_tool_calls': len(tool_seq),
        'n_corrections': len(corrections),
        'n_errors': len(errors),
        'tool_distribution': dict(tool_counter),
        'top_tools': tool_name_counter.most_common(5),
        'entropy_by_k': entropy_by_k,
        'mean_entropy': mean_h,
        'std_entropy': std_h,
        'n_high_anomalies': len(high_anom),
        'n_low_anomalies': len(low_anom),
        'high_anomaly_positions': high_anom[:10],  # Cap for output
        'low_anomaly_positions': low_anom[:10],
        'correction_correlation_high': corr_high,
        'correction_correlation_low': corr_low,
        'error_correlation_high': err_high,
        'error_correlation_low': err_low,
        'entropy_trajectory': {
            'early': early_h,
            'mid': mid_h,
            'late': late_h,
        },
        'h0_mean': float(np.mean(h0)) if len(h0) > 0 else 0.0,
        'h0_std': float(np.std(h0)) if len(h0) > 0 else 0.0,
    }


# ──────────────────────────────────────────────────────────────────────
# Report generation
# ──────────────────────────────────────────────────────────────────────

def generate_report(results, n_projects):
    """Generate markdown report from analysis results."""
    lines = []

    lines.append("# Entropy Rate Anomaly Detection in Claude Code Sessions\n")
    lines.append("## Method\n")
    lines.append("Measures the predictability of agent tool-call behavior over time.")
    lines.append("Uses conditional entropy H(X_n | X_{n-1},...,X_{n-k}) to quantify")
    lines.append("how much information each new tool call adds given recent history.\n")
    lines.append(f"- **Sessions analyzed**: {len(results)} (from {n_projects} projects)")
    lines.append(f"- **Window size**: {WINDOW_SIZE} tool calls")
    lines.append(f"- **Markov orders tested**: k={', '.join(str(k) for k in K_VALUES)}")
    lines.append(f"- **Anomaly threshold**: mean +/- {ANOMALY_SIGMA} sigma")
    lines.append(f"- **Min tool calls per session**: {MIN_TOOL_CALLS}\n")

    lines.append("### Symbol Encoding\n")
    lines.append("| Symbol | Tools | Description |")
    lines.append("|--------|-------|-------------|")
    lines.append("| R | Read, Glob, Grep | Read operations |")
    lines.append("| E | Edit, Write, NotebookEdit | Edit operations |")
    lines.append("| B | Bash | Shell commands |")
    lines.append("| S | WebSearch, WebFetch | Web search |")
    lines.append("| O | All others | Other tools |")

    # ── Aggregate statistics ──
    lines.append("\n## Aggregate Entropy Statistics\n")

    mean_entropies = [r['mean_entropy'] for r in results]
    std_entropies = [r['std_entropy'] for r in results]

    lines.append(f"### Overall Entropy Distribution (k=1)\n")
    lines.append(f"| Statistic | Value |")
    lines.append(f"|-----------|-------|")
    lines.append(f"| Mean of session means | {np.mean(mean_entropies):.4f} bits |")
    lines.append(f"| Std of session means | {np.std(mean_entropies):.4f} bits |")
    lines.append(f"| Min session mean | {np.min(mean_entropies):.4f} bits |")
    lines.append(f"| Max session mean | {np.max(mean_entropies):.4f} bits |")
    lines.append(f"| Median session mean | {np.median(mean_entropies):.4f} bits |")

    # By k
    lines.append(f"\n### Entropy by Markov Order\n")
    lines.append(f"| k | Mean H(X|context) | Std | Description |")
    lines.append(f"|---|-------------------|-----|-------------|")
    for k in K_VALUES:
        means_k = [r['entropy_by_k'][k]['mean'] for r in results if k in r['entropy_by_k']]
        if means_k:
            desc = {
                1: "How predictable given last tool",
                2: "How predictable given last 2 tools",
                3: "How predictable given last 3 tools",
            }.get(k, "")
            lines.append(f"| {k} | {np.mean(means_k):.4f} | {np.std(means_k):.4f} | {desc} |")

    # Marginal vs conditional
    h0_means = [r['h0_mean'] for r in results]
    h1_means = [r['entropy_by_k'].get(1, {}).get('mean', 0) for r in results]
    lines.append(f"\n### Predictability Gain from Context\n")
    lines.append(f"- **Marginal entropy H(X)**: {np.mean(h0_means):.4f} bits (no context)")
    lines.append(f"- **Conditional entropy H(X|X_{{n-1}})**: {np.mean(h1_means):.4f} bits (given last tool)")
    reduction = (1 - np.mean(h1_means) / np.mean(h0_means)) * 100 if np.mean(h0_means) > 0 else 0
    lines.append(f"- **Predictability gain**: {reduction:.1f}% reduction in uncertainty")
    lines.append(f"- Knowing the last tool call reduces uncertainty by ~{reduction:.0f}%\n")

    # ── Anomaly overview ──
    lines.append("\n## Anomaly Detection Results\n")

    total_high = sum(r['n_high_anomalies'] for r in results)
    total_low = sum(r['n_low_anomalies'] for r in results)
    sessions_with_high = sum(1 for r in results if r['n_high_anomalies'] > 0)
    sessions_with_low = sum(1 for r in results if r['n_low_anomalies'] > 0)

    lines.append(f"| Anomaly Type | Total Windows | Sessions Affected | % Sessions |")
    lines.append(f"|--------------|---------------|-------------------|------------|")
    lines.append(f"| High entropy (chaotic) | {total_high} | {sessions_with_high} | {sessions_with_high/len(results)*100:.1f}% |")
    lines.append(f"| Low entropy (rigid) | {total_low} | {sessions_with_low} | {sessions_with_low/len(results)*100:.1f}% |")

    # ── Correlation with corrections and errors ──
    lines.append(f"\n### Correlation: Anomalies vs. Corrections and Errors\n")
    lines.append("How often do entropy anomalies co-occur with user corrections and tool errors?\n")

    corr_high_vals = [r['correction_correlation_high'] for r in results if r['n_high_anomalies'] > 0]
    corr_low_vals = [r['correction_correlation_low'] for r in results if r['n_low_anomalies'] > 0]
    err_high_vals = [r['error_correlation_high'] for r in results if r['n_high_anomalies'] > 0]
    err_low_vals = [r['error_correlation_low'] for r in results if r['n_low_anomalies'] > 0]

    lines.append(f"| Anomaly Type | Near Corrections | Near Errors |")
    lines.append(f"|--------------|------------------|-------------|")
    if corr_high_vals:
        lines.append(f"| High entropy | {np.mean(corr_high_vals):.1%} | {np.mean(err_high_vals):.1%} |")
    else:
        lines.append(f"| High entropy | N/A | N/A |")
    if corr_low_vals:
        lines.append(f"| Low entropy | {np.mean(corr_low_vals):.1%} | {np.mean(err_low_vals):.1%} |")
    else:
        lines.append(f"| Low entropy | N/A | N/A |")

    lines.append("")
    if corr_high_vals and np.mean(corr_high_vals) > 0.3:
        lines.append("High-entropy anomalies show meaningful correlation with corrections,")
        lines.append("suggesting the agent becomes unpredictable when the user redirects.\n")
    if err_high_vals and np.mean(err_high_vals) > 0.3:
        lines.append("High-entropy anomalies correlate with tool errors, suggesting")
        lines.append("the agent's behavior becomes erratic during error recovery.\n")
    if corr_low_vals and np.mean(corr_low_vals) > 0.3:
        lines.append("Low-entropy anomalies near corrections suggest the agent gets stuck")
        lines.append("in rigid patterns that eventually trigger user intervention.\n")

    # ── Entropy trajectory ──
    lines.append("\n## Entropy Trajectory: How Predictability Evolves\n")
    lines.append("Does agent behavior become more or less predictable over a session?\n")

    early = [r['entropy_trajectory']['early'] for r in results]
    mid = [r['entropy_trajectory']['mid'] for r in results]
    late = [r['entropy_trajectory']['late'] for r in results]

    lines.append(f"| Phase | Mean Entropy | Std |")
    lines.append(f"|-------|-------------|-----|")
    lines.append(f"| Early (first third) | {np.mean(early):.4f} | {np.std(early):.4f} |")
    lines.append(f"| Middle (second third) | {np.mean(mid):.4f} | {np.std(mid):.4f} |")
    lines.append(f"| Late (final third) | {np.mean(late):.4f} | {np.std(late):.4f} |")

    # Trajectory classification
    increasing = sum(1 for r in results if r['entropy_trajectory']['late'] > r['entropy_trajectory']['early'] + 0.05)
    decreasing = sum(1 for r in results if r['entropy_trajectory']['late'] < r['entropy_trajectory']['early'] - 0.05)
    stable = len(results) - increasing - decreasing

    lines.append(f"\n### Trajectory Classification\n")
    lines.append(f"| Pattern | Sessions | % |")
    lines.append(f"|---------|----------|---|")
    lines.append(f"| Increasing entropy (diversifying) | {increasing} | {increasing/len(results)*100:.1f}% |")
    lines.append(f"| Decreasing entropy (specializing) | {decreasing} | {decreasing/len(results)*100:.1f}% |")
    lines.append(f"| Stable entropy | {stable} | {stable/len(results)*100:.1f}% |")

    if decreasing > increasing:
        lines.append(f"\nMost sessions show decreasing entropy: the agent starts by exploring")
        lines.append(f"(diverse tool use) and settles into a focused pattern.\n")
    elif increasing > decreasing:
        lines.append(f"\nMore sessions show increasing entropy: as sessions progress, the agent")
        lines.append(f"uses a wider variety of tools, possibly due to escalating complexity.\n")

    # ── Project comparison ──
    lines.append("\n## Cross-Project Entropy Comparison\n")
    lines.append("How does behavior predictability vary across projects?\n")

    by_project = defaultdict(list)
    for r in results:
        by_project[r['project']].append(r)

    proj_stats = []
    for proj, proj_results in by_project.items():
        if len(proj_results) < 2:
            continue
        proj_means = [r['mean_entropy'] for r in proj_results]
        proj_stats.append({
            'project': proj,
            'n_sessions': len(proj_results),
            'mean_entropy': np.mean(proj_means),
            'std_entropy': np.std(proj_means),
            'mean_anomalies': np.mean([r['n_high_anomalies'] + r['n_low_anomalies'] for r in proj_results]),
        })

    proj_stats.sort(key=lambda x: x['mean_entropy'])

    lines.append(f"| Project | Sessions | Mean Entropy | Std | Anomalies/Session |")
    lines.append(f"|---------|----------|-------------|-----|-------------------|")
    for ps in proj_stats[:20]:
        proj_name = ps['project'][:40]
        lines.append(
            f"| {proj_name} | {ps['n_sessions']} | "
            f"{ps['mean_entropy']:.4f} | {ps['std_entropy']:.4f} | "
            f"{ps['mean_anomalies']:.1f} |"
        )

    if proj_stats:
        lines.append(f"\n- **Most predictable project**: {proj_stats[0]['project'][:40]} "
                      f"(H={proj_stats[0]['mean_entropy']:.4f})")
        lines.append(f"- **Least predictable project**: {proj_stats[-1]['project'][:40]} "
                      f"(H={proj_stats[-1]['mean_entropy']:.4f})")
        spread = proj_stats[-1]['mean_entropy'] - proj_stats[0]['mean_entropy']
        lines.append(f"- **Cross-project entropy spread**: {spread:.4f} bits\n")

    # ── Tool distribution and entropy ──
    lines.append("\n## Tool Distribution vs. Entropy\n")

    # Correlate number of distinct tools with entropy
    tool_diversities = [len(r['tool_distribution']) for r in results]
    lines.append(f"| Distinct Symbols | Sessions | Mean Entropy |")
    lines.append(f"|------------------|----------|-------------|")
    for n_sym in sorted(set(tool_diversities)):
        subset = [r for r in results if len(r['tool_distribution']) == n_sym]
        if len(subset) >= 2:
            mean_h = np.mean([r['mean_entropy'] for r in subset])
            lines.append(f"| {n_sym} | {len(subset)} | {mean_h:.4f} |")

    # ── Notable sessions ──
    lines.append("\n## Notable Sessions\n")

    # Most anomalous sessions
    lines.append("### Sessions with Most High-Entropy Anomalies (Chaotic Behavior)\n")
    by_high = sorted(results, key=lambda r: r['n_high_anomalies'], reverse=True)
    lines.append(f"| Project | Tool Calls | High Anom. | Low Anom. | Mean H | Corrections | Errors |")
    lines.append(f"|---------|-----------|-----------|----------|--------|-------------|--------|")
    for r in by_high[:10]:
        if r['n_high_anomalies'] == 0:
            break
        lines.append(
            f"| {r['project'][:30]} | {r['n_tool_calls']} | "
            f"{r['n_high_anomalies']} | {r['n_low_anomalies']} | "
            f"{r['mean_entropy']:.4f} | {r['n_corrections']} | {r['n_errors']} |"
        )

    lines.append("\n### Sessions with Most Low-Entropy Anomalies (Rigid Behavior)\n")
    by_low = sorted(results, key=lambda r: r['n_low_anomalies'], reverse=True)
    lines.append(f"| Project | Tool Calls | High Anom. | Low Anom. | Mean H | Corrections | Errors |")
    lines.append(f"|---------|-----------|-----------|----------|--------|-------------|--------|")
    for r in by_low[:10]:
        if r['n_low_anomalies'] == 0:
            break
        lines.append(
            f"| {r['project'][:30]} | {r['n_tool_calls']} | "
            f"{r['n_high_anomalies']} | {r['n_low_anomalies']} | "
            f"{r['mean_entropy']:.4f} | {r['n_corrections']} | {r['n_errors']} |"
        )

    # ── Interpretation ──
    lines.append("\n## Interpretation\n")

    # 1. Overall predictability
    global_mean = np.mean(mean_entropies)
    max_possible = math.log2(len(TOOL_SYMBOLS))  # max entropy for uniform distribution
    predictability = (1 - global_mean / max_possible) * 100 if max_possible > 0 else 0

    lines.append(f"**1. Agent behavior is {predictability:.0f}% predictable.**")
    lines.append(f"With a mean conditional entropy of {global_mean:.4f} bits vs. "
                  f"a maximum of {max_possible:.4f} bits (uniform), "
                  f"knowing the last tool call makes the next one substantially predictable. "
                  f"The agent is not random -- it follows strong sequential patterns.\n")

    # 2. Context helps
    lines.append(f"**2. Context reduces uncertainty by ~{reduction:.0f}%.**")
    lines.append(f"Moving from H(X) = {np.mean(h0_means):.4f} to H(X|X_{{n-1}}) = {np.mean(h1_means):.4f} "
                  f"shows that the immediately preceding tool is a strong predictor of the next. "
                  f"This is consistent with the 'bursty' execution model: the agent works in runs "
                  f"of similar operations.\n")

    # 3. Anomaly patterns
    if total_high > total_low:
        lines.append(f"**3. Chaotic anomalies ({total_high}) outnumber rigid anomalies ({total_low}).**")
        lines.append(f"The agent is more likely to become erratically diverse than stuck in a rut. "
                      f"This may reflect exploration phases or error recovery scrambling.\n")
    elif total_low > total_high:
        lines.append(f"**3. Rigid anomalies ({total_low}) outnumber chaotic anomalies ({total_high}).**")
        lines.append(f"The agent is more likely to get locked into repetitive patterns than to "
                      f"become erratically diverse. This suggests perseverative loops.\n")
    else:
        lines.append(f"**3. Chaotic ({total_high}) and rigid ({total_low}) anomalies are balanced.**\n")

    # 4. Trajectory
    if decreasing > increasing:
        lines.append(f"**4. Sessions converge toward predictability.**")
        lines.append(f"{decreasing} of {len(results)} sessions show decreasing entropy over time. "
                      f"The agent explores early and narrows its approach. This is healthy behavior: "
                      f"investigation then focused execution.\n")
    elif increasing > decreasing:
        lines.append(f"**4. Sessions diverge toward unpredictability.**")
        lines.append(f"{increasing} of {len(results)} sessions show increasing entropy over time. "
                      f"The agent becomes less focused as sessions progress, possibly due to "
                      f"accumulating complexity or context degradation.\n")

    # 5. Error correlation
    if err_high_vals and np.mean(err_high_vals) > 0.2:
        lines.append(f"**5. Tool errors trigger chaotic behavior.**")
        lines.append(f"{np.mean(err_high_vals):.0%} of high-entropy windows are near tool errors. "
                      f"When tools fail, the agent scrambles to recover, producing unpredictable "
                      f"sequences of tool calls.\n")

    # Summary
    lines.append("## Summary Statistics\n")
    lines.append(f"| Metric | Value |")
    lines.append(f"|--------|-------|")
    lines.append(f"| Sessions analyzed | {len(results)} |")
    lines.append(f"| Mean entropy (k=1) | {global_mean:.4f} bits |")
    lines.append(f"| Predictability | {predictability:.0f}% |")
    lines.append(f"| Context reduction | {reduction:.0f}% |")
    lines.append(f"| Total high anomalies | {total_high} |")
    lines.append(f"| Total low anomalies | {total_low} |")
    lines.append(f"| Sessions with any anomaly | {sessions_with_high + sessions_with_low - sum(1 for r in results if r['n_high_anomalies'] > 0 and r['n_low_anomalies'] > 0)} |")
    lines.append(f"| Dominant trajectory | {'Convergent' if decreasing > increasing else 'Divergent' if increasing > decreasing else 'Stable'} |")

    return "\n".join(lines)


# ──────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────

def main():
    print("=" * 70)
    print("ENTROPY RATE ANOMALY DETECTION IN CLAUDE CODE SESSIONS")
    print("=" * 70)

    # Find session files
    print("\nDiscovering session files...")
    all_files = find_session_files(CORPUS_DIR)
    print(f"  Found {len(all_files)} JSONL session files")

    # Sample sessions
    sampled, by_project = sample_sessions(all_files, MAX_SESSIONS)
    n_projects = len(by_project)
    print(f"  Sampled {len(sampled)} sessions from {n_projects} projects")

    # Analyze each session
    print("\nAnalyzing sessions...")
    results = []
    skipped = 0

    for i, (filepath, size) in enumerate(sampled):
        if (i + 1) % 20 == 0:
            sys.stdout.write(f"\r  Processing {i+1}/{len(sampled)}...")
            sys.stdout.flush()

        result = analyze_session(filepath)
        if result is not None:
            results.append(result)
        else:
            skipped += 1

    print(f"\r  Analyzed: {len(results)}, Skipped: {skipped} (too few tool calls)")

    # Print summary to console
    print(f"\n{'=' * 70}")
    print(f"RESULTS SUMMARY")
    print(f"{'=' * 70}")

    mean_entropies = [r['mean_entropy'] for r in results]
    print(f"\n  Entropy (k=1):")
    print(f"    Mean: {np.mean(mean_entropies):.4f} bits")
    print(f"    Std:  {np.std(mean_entropies):.4f} bits")
    print(f"    Range: [{np.min(mean_entropies):.4f}, {np.max(mean_entropies):.4f}]")

    for k in K_VALUES:
        means_k = [r['entropy_by_k'][k]['mean'] for r in results if k in r['entropy_by_k']]
        if means_k:
            print(f"  Entropy (k={k}): mean={np.mean(means_k):.4f}, std={np.std(means_k):.4f}")

    total_high = sum(r['n_high_anomalies'] for r in results)
    total_low = sum(r['n_low_anomalies'] for r in results)
    print(f"\n  Anomalies:")
    print(f"    High entropy (chaotic): {total_high} windows in {sum(1 for r in results if r['n_high_anomalies'] > 0)} sessions")
    print(f"    Low entropy (rigid):    {total_low} windows in {sum(1 for r in results if r['n_low_anomalies'] > 0)} sessions")

    early = [r['entropy_trajectory']['early'] for r in results]
    late = [r['entropy_trajectory']['late'] for r in results]
    print(f"\n  Trajectory:")
    print(f"    Early mean: {np.mean(early):.4f}")
    print(f"    Late mean:  {np.mean(late):.4f}")
    print(f"    Direction:  {'Decreasing (converging)' if np.mean(late) < np.mean(early) else 'Increasing (diverging)'}")

    # Generate report
    print(f"\n{'=' * 70}")
    print("Generating report...")
    report = generate_report(results, n_projects)

    report_path = os.path.join(OUTPUT_DIR, "entropy_rate_anomaly.md")
    with open(report_path, 'w') as f:
        f.write(report)
    print(f"  Report written to: {report_path}")

    # Save raw results as JSON
    json_path = os.path.join(OUTPUT_DIR, "entropy_rate_anomaly_results.json")
    json_data = {
        'sessions_analyzed': len(results),
        'sessions_skipped': skipped,
        'aggregate': {
            'mean_entropy': float(np.mean(mean_entropies)),
            'std_entropy': float(np.std(mean_entropies)),
            'total_high_anomalies': total_high,
            'total_low_anomalies': total_low,
            'entropy_trajectory': {
                'early_mean': float(np.mean(early)),
                'mid_mean': float(np.mean([r['entropy_trajectory']['mid'] for r in results])),
                'late_mean': float(np.mean(late)),
            },
        },
        'entropy_by_k': {
            str(k): {
                'mean': float(np.mean([r['entropy_by_k'][k]['mean'] for r in results if k in r['entropy_by_k']])),
                'std': float(np.std([r['entropy_by_k'][k]['mean'] for r in results if k in r['entropy_by_k']])),
            }
            for k in K_VALUES
        },
        'per_session': [
            {
                'project': r['project'],
                'n_tool_calls': r['n_tool_calls'],
                'mean_entropy': r['mean_entropy'],
                'std_entropy': r['std_entropy'],
                'n_high_anomalies': r['n_high_anomalies'],
                'n_low_anomalies': r['n_low_anomalies'],
                'n_corrections': r['n_corrections'],
                'n_errors': r['n_errors'],
                'entropy_trajectory': r['entropy_trajectory'],
                'tool_distribution': r['tool_distribution'],
            }
            for r in results
        ],
    }

    with open(json_path, 'w') as f:
        json.dump(json_data, f, indent=2)
    print(f"  JSON results written to: {json_path}")

    print(f"\n{'=' * 70}")
    print(f"COMPLETE")
    print(f"{'=' * 70}")


if __name__ == "__main__":
    main()
