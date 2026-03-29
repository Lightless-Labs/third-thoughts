#!/usr/bin/env python3
"""
Statistical Process Control (SPC) analysis of Claude Code session quality.

Applies manufacturing SPC techniques to AI agent sessions:
1. X-bar and R control charts for quality metrics
2. CUSUM charts for persistent drift detection
3. Process capability indices (Cp, Cpk)
4. Cross-project comparison

Source: All Banade-a-Bonnot project sessions with 20+ events.
"""

import json
import os
import glob
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
from scipy import stats

# ─── Configuration ──────────────────────────────────────────────────────────────

CORPUS_DIR = os.environ.get("CORPUS_DIR", os.environ.get("MIDDENS_CORPUS", "corpus/"))
OUTPUT_DIR = os.environ.get("OUTPUT_DIR", os.environ.get("MIDDENS_OUTPUT", "experiments/"))
FIGURES_DIR = os.path.join(OUTPUT_DIR, "figures")
MIN_EVENTS = 20

# Correction signal keywords/patterns
CORRECTION_PATTERNS = [
    r"\bno\b",
    r"\bwrong\b",
    r"\bincorrect\b",
    r"\bfix\b",
    r"\bactually\b",
    r"\binstead\b",
    r"\bdon'?t\b",
    r"\bstop\b",
    r"\bnot what\b",
    r"\bthat'?s not\b",
    r"\bundo\b",
    r"\brevert\b",
    r"\brollback\b",
    r"\btry again\b",
    r"\bwait\b",
    r"\bhold on\b",
    r"\bcancel\b",
    r"\bwhy did you\b",
    r"\bshouldn'?t\b",
    r"\bdidn'?t ask\b",
    r"\bnot right\b",
    r"\bmistake\b",
    r"\berror\b",
    r"\bplease don'?t\b",
    r"\bI said\b",
    r"\bnope\b",
]
CORRECTION_RE = re.compile("|".join(CORRECTION_PATTERNS), re.IGNORECASE)


# ─── Data Structures ────────────────────────────────────────────────────────────

@dataclass
class SessionMetrics:
    session_id: str
    project: str
    timestamp: Optional[datetime] = None
    total_events: int = 0
    user_turns: int = 0
    assistant_turns: int = 0
    corrections: int = 0
    tool_calls: int = 0
    tool_failures: int = 0
    user_chars: int = 0
    assistant_chars: int = 0
    edits: int = 0  # Edit/Write tool uses
    # Derived
    correction_rate: float = 0.0       # corrections per 100 user turns
    tool_failure_rate: float = 0.0     # failures per 100 tool calls
    amplification_ratio: float = 0.0   # assistant chars / user chars
    efficiency: float = 0.0            # edits per correction (higher = better)


# ─── Data Extraction ────────────────────────────────────────────────────────────

def extract_user_text(content) -> str:
    """Extract plain text from user message content."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
        return " ".join(parts)
    return ""


def count_tool_results(content) -> tuple:
    """Count tool results and errors from user message content blocks."""
    total = 0
    errors = 0
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_result":
                total += 1
                if block.get("is_error", False):
                    errors += 1
    return total, errors


def extract_assistant_info(content) -> tuple:
    """Extract text length and tool call info from assistant content."""
    text_chars = 0
    tool_calls = []
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict):
                if block.get("type") == "text":
                    text_chars += len(block.get("text", ""))
                elif block.get("type") == "tool_use":
                    tool_calls.append(block.get("name", ""))
    return text_chars, tool_calls


def is_correction(text: str) -> bool:
    """Heuristic: does this user message look like a correction?"""
    text = text.strip()
    if len(text) < 3:
        return False
    # Very short messages with correction signals are strong signals
    if len(text) < 50 and CORRECTION_RE.search(text):
        return True
    # Longer messages: check for correction density
    if CORRECTION_RE.search(text):
        # Exclude messages that are clearly new tasks
        if len(text) > 300:
            return False
        return True
    return False


def parse_session(filepath: str) -> Optional[SessionMetrics]:
    """Parse a single session JSONL file into metrics."""
    session_id = Path(filepath).stem
    # Extract project name from corpus path
    parts = filepath.split("/")
    project = "unknown"
    for i, p in enumerate(parts):
        if p == "projects" and i + 1 < len(parts):
            project = parts[i + 1]
            break

    records = []
    try:
        with open(filepath) as f:
            for line in f:
                line = line.strip()
                if line:
                    records.append(json.loads(line))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None

    if len(records) < MIN_EVENTS:
        return None

    m = SessionMetrics(session_id=session_id, project=project, total_events=len(records))

    # Find earliest timestamp
    timestamps = []
    for rec in records:
        ts = rec.get("timestamp")
        if ts:
            try:
                timestamps.append(datetime.fromisoformat(ts.replace("Z", "+00:00")))
            except (ValueError, TypeError):
                pass
    if timestamps:
        m.timestamp = min(timestamps)

    for rec in records:
        rtype = rec.get("type")

        if rtype == "user":
            msg = rec.get("message", {})
            content = msg.get("content", "")

            # Extract text from user message
            user_text = extract_user_text(content)
            if user_text.strip():
                m.user_turns += 1
                m.user_chars += len(user_text)
                if is_correction(user_text):
                    m.corrections += 1

            # Count tool results (embedded in user messages)
            tr_total, tr_errors = count_tool_results(content)
            m.tool_calls += tr_total
            m.tool_failures += tr_errors

        elif rtype == "assistant":
            msg = rec.get("message", {})
            content = msg.get("content", [])
            m.assistant_turns += 1

            text_chars, tools = extract_assistant_info(content)
            m.assistant_chars += text_chars

            for tool in tools:
                m.tool_calls += 1  # Also count from assistant side
                if tool in ("Edit", "Write", "NotebookEdit"):
                    m.edits += 1

    # Skip sessions with no real interaction
    if m.user_turns < 1:
        return None

    # Compute derived metrics
    if m.user_turns > 0:
        m.correction_rate = (m.corrections / m.user_turns) * 100
    if m.tool_calls > 0:
        m.tool_failure_rate = (m.tool_failures / m.tool_calls) * 100
    if m.user_chars > 0:
        m.amplification_ratio = m.assistant_chars / m.user_chars
    if m.corrections > 0:
        m.efficiency = m.edits / m.corrections
    else:
        m.efficiency = m.edits if m.edits > 0 else float("nan")

    return m


def load_all_sessions() -> list:
    """Load and parse all qualifying sessions (follows symlinks)."""
    sessions = []
    jsonl_files = []
    for root, dirs, fnames in os.walk(CORPUS_DIR, followlinks=True):
        for fn in fnames:
            if fn.endswith(".jsonl"):
                jsonl_files.append(os.path.join(root, fn))

    for fpath in sorted(jsonl_files):
        m = parse_session(fpath)
        if m is not None:
            sessions.append(m)

    # Sort chronologically
    sessions_with_ts = [s for s in sessions if s.timestamp]
    sessions_without_ts = [s for s in sessions if not s.timestamp]
    sessions_with_ts.sort(key=lambda s: s.timestamp)
    return sessions_with_ts + sessions_without_ts


# ─── SPC Computations ───────────────────────────────────────────────────────────

def compute_control_limits(values: np.ndarray) -> dict:
    """Compute X-bar, UCL, LCL for individual measurements."""
    xbar = np.nanmean(values)
    sigma = np.nanstd(values, ddof=1)
    ucl = xbar + 3 * sigma
    lcl = max(0, xbar - 3 * sigma)  # Can't go below 0 for rates
    return {"xbar": xbar, "sigma": sigma, "ucl": ucl, "lcl": lcl}


def compute_moving_range_limits(values: np.ndarray) -> dict:
    """Compute moving range chart limits (individuals chart)."""
    clean = values[~np.isnan(values)]
    if len(clean) < 2:
        return {"mr_bar": 0, "ucl_r": 0}
    mr = np.abs(np.diff(clean))
    mr_bar = np.mean(mr)
    d2 = 1.128  # for subgroup size n=2 (moving range)
    ucl_r = 3.267 * mr_bar  # D4 * MR_bar for n=2
    return {"mr_bar": mr_bar, "ucl_r": ucl_r}


def compute_cusum(values: np.ndarray, target: float, k: float = 0.5,
                  h: float = 5.0) -> dict:
    """
    Compute CUSUM chart values.
    k = allowance (slack) in units of sigma
    h = decision interval in units of sigma
    """
    sigma = np.nanstd(values, ddof=1)
    if sigma == 0 or np.isnan(sigma):
        n = len(values)
        return {
            "c_plus": np.zeros(n), "c_minus": np.zeros(n),
            "h_value": 0, "signals_high": [], "signals_low": []
        }

    K = k * sigma
    H = h * sigma
    n = len(values)
    c_plus = np.zeros(n)
    c_minus = np.zeros(n)
    signals_high = []
    signals_low = []

    for i in range(n):
        if np.isnan(values[i]):
            c_plus[i] = c_plus[i - 1] if i > 0 else 0
            c_minus[i] = c_minus[i - 1] if i > 0 else 0
            continue
        prev_plus = c_plus[i - 1] if i > 0 else 0
        prev_minus = c_minus[i - 1] if i > 0 else 0
        c_plus[i] = max(0, prev_plus + (values[i] - target) - K)
        c_minus[i] = max(0, prev_minus - (values[i] - target) - K)

        if c_plus[i] > H:
            signals_high.append(i)
        if c_minus[i] > H:
            signals_low.append(i)

    return {
        "c_plus": c_plus, "c_minus": c_minus,
        "h_value": H, "signals_high": signals_high, "signals_low": signals_low
    }


def compute_capability(values: np.ndarray, usl: float, lsl: float = 0.0) -> dict:
    """Compute process capability indices Cp and Cpk."""
    clean = values[~np.isnan(values)]
    if len(clean) < 2:
        return {"cp": float("nan"), "cpk": float("nan"),
                "pct_out_of_spec": 0, "n_out_of_spec": 0}

    mean = np.mean(clean)
    sigma = np.std(clean, ddof=1)

    if sigma == 0:
        return {"cp": float("inf"), "cpk": float("inf"),
                "pct_out_of_spec": 0, "n_out_of_spec": 0}

    cp = (usl - lsl) / (6 * sigma)
    cpu = (usl - mean) / (3 * sigma)
    cpl = (mean - lsl) / (3 * sigma)
    cpk = min(cpu, cpl)

    n_out = np.sum((clean > usl) | (clean < lsl))
    pct_out = (n_out / len(clean)) * 100

    return {"cp": cp, "cpk": cpk, "pct_out_of_spec": pct_out,
            "n_out_of_spec": int(n_out), "n_total": len(clean),
            "mean": mean, "sigma": sigma, "usl": usl, "lsl": lsl}


# ─── Plotting ────────────────────────────────────────────────────────────────────

COLORS = {
    "in_control": "#2196F3",
    "out_of_control": "#F44336",
    "center_line": "#4CAF50",
    "control_limit": "#FF9800",
    "spec_limit": "#9C27B0",
    "cusum_plus": "#2196F3",
    "cusum_minus": "#F44336",
    "cusum_h": "#FF9800",
}

PROJECT_COLORS = {
    "autonomous-sandbox": "#E91E63",
    "converge-refinery": "#9C27B0",
    "openclaw": "#673AB7",
    "phil-connors": "#3F51B5",
    "kumbaya": "#2196F3",
    "infinidash": "#00BCD4",
    "weatherby": "#4CAF50",
    "ten-a-day": "#8BC34A",
    "agentic-linear-take-two": "#FF9800",
    "parsiweb-previews": "#FF5722",
    "(root)": "#795548",
    "ergon": "#607D8B",
    "JASONETTE-Reborn": "#F44336",
}


def plot_control_chart(ax, values, limits, title, ylabel, session_labels=None,
                       project_list=None):
    """Plot an X-bar control chart on given axes."""
    n = len(values)
    x = np.arange(n)

    # Color by control status
    ooc = (values > limits["ucl"]) | (values < limits["lcl"])
    ic = ~ooc & ~np.isnan(values)

    if project_list is not None:
        unique_projects = sorted(set(project_list))
        cmap = {p: PROJECT_COLORS.get(p, "#999999") for p in unique_projects}
        for i in range(n):
            if np.isnan(values[i]):
                continue
            c = cmap.get(project_list[i], "#999999")
            marker = "x" if ooc[i] else "o"
            ms = 8 if ooc[i] else 4
            ax.plot(x[i], values[i], marker, color=c, markersize=ms, alpha=0.7)
    else:
        ax.scatter(x[ic], values[ic], c=COLORS["in_control"], s=16, alpha=0.6,
                   zorder=3)
        ax.scatter(x[ooc], values[ooc], c=COLORS["out_of_control"], s=50,
                   marker="x", zorder=4, linewidths=2)

    # Control lines
    ax.axhline(limits["xbar"], color=COLORS["center_line"], linestyle="-",
               linewidth=1.5, label=f'x-bar = {limits["xbar"]:.2f}')
    ax.axhline(limits["ucl"], color=COLORS["control_limit"], linestyle="--",
               linewidth=1, label=f'UCL = {limits["ucl"]:.2f}')
    if limits["lcl"] > 0:
        ax.axhline(limits["lcl"], color=COLORS["control_limit"], linestyle="--",
                   linewidth=1, label=f'LCL = {limits["lcl"]:.2f}')

    n_ooc = int(np.sum(ooc))
    ax.set_title(f"{title}  ({n_ooc} out of {n} out of control)", fontsize=11)
    ax.set_ylabel(ylabel, fontsize=9)
    ax.legend(fontsize=7, loc="upper right")
    ax.grid(True, alpha=0.3)


def plot_cusum_chart(ax, cusum, title, n_sessions):
    """Plot CUSUM chart on given axes."""
    x = np.arange(n_sessions)
    ax.plot(x, cusum["c_plus"], color=COLORS["cusum_plus"], linewidth=1.2,
            label="C+ (upward shift)")
    ax.plot(x, cusum["c_minus"], color=COLORS["cusum_minus"], linewidth=1.2,
            label="C- (downward shift)")
    ax.axhline(cusum["h_value"], color=COLORS["cusum_h"], linestyle="--",
               linewidth=1, label=f'H = {cusum["h_value"]:.2f}')

    # Mark signal points
    if cusum["signals_high"]:
        ax.scatter(cusum["signals_high"],
                   cusum["c_plus"][cusum["signals_high"]],
                   c=COLORS["out_of_control"], s=40, marker="^", zorder=4)
    if cusum["signals_low"]:
        ax.scatter(cusum["signals_low"],
                   cusum["c_minus"][cusum["signals_low"]],
                   c=COLORS["out_of_control"], s=40, marker="v", zorder=4)

    ax.set_title(title, fontsize=11)
    ax.set_ylabel("CUSUM value", fontsize=9)
    ax.legend(fontsize=7, loc="upper left")
    ax.grid(True, alpha=0.3)


def plot_capability_histogram(ax, values, cap, metric_name, unit=""):
    """Plot process capability histogram."""
    clean = values[~np.isnan(values)]
    ax.hist(clean, bins=30, color=COLORS["in_control"], alpha=0.6, edgecolor="white",
            density=True)

    # Overlay normal curve
    x_range = np.linspace(clean.min() - cap["sigma"], clean.max() + cap["sigma"], 200)
    pdf = stats.norm.pdf(x_range, cap["mean"], cap["sigma"])
    ax.plot(x_range, pdf, color=COLORS["center_line"], linewidth=2)

    # Spec limits
    ax.axvline(cap["usl"], color=COLORS["spec_limit"], linestyle="--", linewidth=2,
               label=f'USL = {cap["usl"]:.1f}{unit}')
    if cap["lsl"] > 0:
        ax.axvline(cap["lsl"], color=COLORS["spec_limit"], linestyle=":",
                   linewidth=2, label=f'LSL = {cap["lsl"]:.1f}{unit}')

    ax.set_title(
        f'{metric_name}\nCp={cap["cp"]:.2f}  Cpk={cap["cpk"]:.2f}  '
        f'({cap["pct_out_of_spec"]:.1f}% out of spec)',
        fontsize=11
    )
    ax.set_xlabel(metric_name + (f" ({unit})" if unit else ""), fontsize=9)
    ax.set_ylabel("Density", fontsize=9)
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)


# ─── Main Analysis ──────────────────────────────────────────────────────────────

def main():
    os.makedirs(FIGURES_DIR, exist_ok=True)

    print("Loading sessions...")
    sessions = load_all_sessions()
    if not sessions:
        print("ERROR: No sessions loaded! Check corpus path and symlinks.")
        sys.exit(1)
    print(f"Loaded {len(sessions)} qualifying sessions from "
          f"{len(set(s.project for s in sessions))} projects")

    # Print distribution
    proj_counts = Counter(s.project for s in sessions)
    for p, c in proj_counts.most_common():
        print(f"  {p}: {c} sessions")

    # ═══════════════════════════════════════════════════════════════════════════
    # ANALYSIS 1: X-bar and R Control Charts
    # ═══════════════════════════════════════════════════════════════════════════
    print("\n" + "=" * 70)
    print("ANALYSIS 1: X-bar and R Control Charts")
    print("=" * 70)

    metrics = {
        "correction_rate": {
            "values": np.array([s.correction_rate for s in sessions]),
            "label": "Correction Rate",
            "unit": "corrections/100 turns",
        },
        "tool_failure_rate": {
            "values": np.array([s.tool_failure_rate for s in sessions]),
            "label": "Tool Failure Rate",
            "unit": "failures/100 calls",
        },
        "amplification_ratio": {
            "values": np.array([s.amplification_ratio for s in sessions]),
            "label": "Amplification Ratio",
            "unit": "assistant/user chars",
        },
        "efficiency": {
            "values": np.array([s.efficiency for s in sessions]),
            "label": "Session Efficiency",
            "unit": "edits/correction",
        },
    }

    projects = [s.project for s in sessions]

    # Compute control limits
    all_limits = {}
    for key, m in metrics.items():
        limits = compute_control_limits(m["values"])
        all_limits[key] = limits
        ooc = np.sum(
            (m["values"] > limits["ucl"]) | (m["values"] < limits["lcl"])
        )
        ooc_clean = np.sum(
            (~np.isnan(m["values"])) &
            ((m["values"] > limits["ucl"]) | (m["values"] < limits["lcl"]))
        )
        print(f"\n{m['label']}:")
        print(f"  Grand mean (x-bar): {limits['xbar']:.3f}")
        print(f"  Sigma: {limits['sigma']:.3f}")
        print(f"  UCL: {limits['ucl']:.3f}")
        print(f"  LCL: {limits['lcl']:.3f}")
        print(f"  Out of control: {ooc_clean}/{len(m['values'])} "
              f"({ooc_clean/len(m['values'])*100:.1f}%)")

    # Plot X-bar charts (2x2 grid)
    fig, axes = plt.subplots(2, 2, figsize=(16, 10))
    fig.suptitle("SPC X-bar Control Charts: Session Quality Metrics", fontsize=14,
                 fontweight="bold")

    for ax, (key, m) in zip(axes.flatten(), metrics.items()):
        plot_control_chart(ax, m["values"], all_limits[key],
                          m["label"], m["unit"], project_list=projects)
        ax.set_xlabel("Session (chronological order)", fontsize=9)

    # Add project legend
    unique_projects = sorted(set(projects))
    legend_patches = [
        mpatches.Patch(color=PROJECT_COLORS.get(p, "#999999"), label=p)
        for p in unique_projects if proj_counts[p] >= 3
    ]
    fig.legend(handles=legend_patches, loc="lower center", ncol=6, fontsize=8,
               bbox_to_anchor=(0.5, -0.02))

    plt.tight_layout(rect=[0, 0.04, 1, 0.96])
    fig.savefig(os.path.join(FIGURES_DIR, "spc_xbar_charts.png"), dpi=150,
                bbox_inches="tight")
    plt.close()
    print("\nSaved: spc_xbar_charts.png")

    # Moving Range charts
    fig, axes = plt.subplots(2, 2, figsize=(16, 10))
    fig.suptitle("SPC Moving Range Charts: Session-to-Session Variability",
                 fontsize=14, fontweight="bold")

    for ax, (key, m) in zip(axes.flatten(), metrics.items()):
        clean = m["values"][~np.isnan(m["values"])]
        mr = np.abs(np.diff(clean))
        mr_limits = compute_moving_range_limits(m["values"])
        n = len(mr)
        x = np.arange(n)

        ooc_mr = mr > mr_limits["ucl_r"]
        ic_mr = ~ooc_mr

        ax.scatter(x[ic_mr], mr[ic_mr], c=COLORS["in_control"], s=16, alpha=0.6)
        ax.scatter(x[ooc_mr], mr[ooc_mr], c=COLORS["out_of_control"], s=50,
                   marker="x", linewidths=2)
        ax.axhline(mr_limits["mr_bar"], color=COLORS["center_line"], linestyle="-",
                   linewidth=1.5, label=f'MR-bar = {mr_limits["mr_bar"]:.2f}')
        ax.axhline(mr_limits["ucl_r"], color=COLORS["control_limit"], linestyle="--",
                   linewidth=1, label=f'UCL = {mr_limits["ucl_r"]:.2f}')

        n_ooc = int(np.sum(ooc_mr))
        ax.set_title(f'Moving Range: {m["label"]}  ({n_ooc}/{n} out of control)',
                     fontsize=11)
        ax.set_ylabel(f'|MR| ({m["unit"]})', fontsize=9)
        ax.set_xlabel("Consecutive session pair", fontsize=9)
        ax.legend(fontsize=7, loc="upper right")
        ax.grid(True, alpha=0.3)

    plt.tight_layout()
    fig.savefig(os.path.join(FIGURES_DIR, "spc_mr_charts.png"), dpi=150,
                bbox_inches="tight")
    plt.close()
    print("Saved: spc_mr_charts.png")

    # Identify out-of-control sessions
    print("\n--- Out-of-Control Sessions ---")
    ooc_sessions = defaultdict(list)
    for i, s in enumerate(sessions):
        for key, m in metrics.items():
            v = m["values"][i]
            if np.isnan(v):
                continue
            lim = all_limits[key]
            if v > lim["ucl"] or v < lim["lcl"]:
                ooc_sessions[s.session_id].append(
                    f'{m["label"]}: {v:.1f} (UCL={lim["ucl"]:.1f})'
                )

    for sid, violations in sorted(ooc_sessions.items(),
                                   key=lambda x: -len(x[1])):
        proj = next(s.project for s in sessions if s.session_id == sid)
        print(f"  {sid[:12]}... [{proj}] ({len(violations)} violations):")
        for v in violations:
            print(f"    - {v}")

    # ═══════════════════════════════════════════════════════════════════════════
    # ANALYSIS 2: CUSUM Charts
    # ═══════════════════════════════════════════════════════════════════════════
    print("\n" + "=" * 70)
    print("ANALYSIS 2: CUSUM Charts")
    print("=" * 70)

    fig, axes = plt.subplots(2, 2, figsize=(16, 10))
    fig.suptitle("CUSUM Charts: Detecting Persistent Quality Shifts",
                 fontsize=14, fontweight="bold")

    cusum_results = {}
    for ax, (key, m) in zip(axes.flatten(), metrics.items()):
        target = all_limits[key]["xbar"]
        cusum = compute_cusum(m["values"], target, k=0.5, h=5.0)
        cusum_results[key] = cusum

        plot_cusum_chart(ax, cusum, f'CUSUM: {m["label"]}', len(m["values"]))
        ax.set_xlabel("Session (chronological order)", fontsize=9)

        n_signals = len(set(cusum["signals_high"] + cusum["signals_low"]))
        print(f"\n{m['label']} CUSUM:")
        print(f"  Target: {target:.3f}")
        print(f"  High shift signals: {len(cusum['signals_high'])} sessions")
        print(f"  Low shift signals: {len(cusum['signals_low'])} sessions")

        # Identify shift regions
        if cusum["signals_high"]:
            first = cusum["signals_high"][0]
            last = cusum["signals_high"][-1]
            if sessions[first].timestamp and sessions[last].timestamp:
                print(f"  Upward shift period: {sessions[first].timestamp.strftime('%Y-%m-%d')} "
                      f"to {sessions[last].timestamp.strftime('%Y-%m-%d')}")

    plt.tight_layout()
    fig.savefig(os.path.join(FIGURES_DIR, "spc_cusum_charts.png"), dpi=150,
                bbox_inches="tight")
    plt.close()
    print("\nSaved: spc_cusum_charts.png")

    # ═══════════════════════════════════════════════════════════════════════════
    # ANALYSIS 3: Process Capability
    # ═══════════════════════════════════════════════════════════════════════════
    print("\n" + "=" * 70)
    print("ANALYSIS 3: Process Capability")
    print("=" * 70)

    # Define specification limits (engineering targets)
    spec_limits = {
        "correction_rate": {"usl": 20.0, "lsl": 0.0,
                            "desc": "Correction rate < 20% is acceptable"},
        "tool_failure_rate": {"usl": 10.0, "lsl": 0.0,
                              "desc": "Tool failure rate < 10% is acceptable"},
        "amplification_ratio": {"usl": 50.0, "lsl": 1.0,
                                "desc": "Amplification 1-50x is useful range"},
        "efficiency": {"usl": 100.0, "lsl": 1.0,
                       "desc": "At least 1 edit per correction"},
    }

    fig, axes = plt.subplots(2, 2, figsize=(16, 10))
    fig.suptitle("Process Capability Analysis: Is the AI Agent Process Capable?",
                 fontsize=14, fontweight="bold")

    capability_results = {}
    for ax, (key, m) in zip(axes.flatten(), metrics.items()):
        sl = spec_limits[key]
        cap = compute_capability(m["values"], usl=sl["usl"], lsl=sl["lsl"])
        capability_results[key] = cap

        plot_capability_histogram(ax, m["values"], cap, m["label"], m["unit"])

        print(f"\n{m['label']}:")
        print(f"  Spec: {sl['desc']}")
        print(f"  USL={sl['usl']}, LSL={sl['lsl']}")
        print(f"  Process mean: {cap.get('mean', 0):.3f}")
        print(f"  Process sigma: {cap.get('sigma', 0):.3f}")
        print(f"  Cp  = {cap['cp']:.3f}  ({'capable' if cap['cp'] >= 1.0 else 'NOT capable'})")
        print(f"  Cpk = {cap['cpk']:.3f}  ({'capable' if cap['cpk'] >= 1.0 else 'NOT capable'})")
        print(f"  Out of spec: {cap['pct_out_of_spec']:.1f}% "
              f"({cap.get('n_out_of_spec', 0)}/{cap.get('n_total', 0)})")

        # Interpret
        if cap["cpk"] >= 1.33:
            print("  => EXCELLENT: Process is well-centered and capable")
        elif cap["cpk"] >= 1.0:
            print("  => ADEQUATE: Process is capable but could improve centering")
        elif cap["cpk"] >= 0.67:
            print("  => MARGINAL: Process needs improvement")
        else:
            print("  => INADEQUATE: Process is not capable, needs intervention")

    plt.tight_layout()
    fig.savefig(os.path.join(FIGURES_DIR, "spc_capability.png"), dpi=150,
                bbox_inches="tight")
    plt.close()
    print("\nSaved: spc_capability.png")

    # ═══════════════════════════════════════════════════════════════════════════
    # ANALYSIS 4: Cross-Project Comparison
    # ═══════════════════════════════════════════════════════════════════════════
    print("\n" + "=" * 70)
    print("ANALYSIS 4: Cross-Project Comparison")
    print("=" * 70)

    # Group sessions by project
    project_sessions = defaultdict(list)
    for s in sessions:
        project_sessions[s.project].append(s)

    # Only analyze projects with sufficient data
    min_project_sessions = 3
    active_projects = {p: ss for p, ss in project_sessions.items()
                       if len(ss) >= min_project_sessions}

    print(f"\nProjects with >= {min_project_sessions} sessions: {len(active_projects)}")

    # Compute per-project stats
    project_stats = {}
    for proj, ss in sorted(active_projects.items()):
        correction_rates = np.array([s.correction_rate for s in ss])
        tool_failure_rates = np.array([s.tool_failure_rate for s in ss])
        amp_ratios = np.array([s.amplification_ratio for s in ss])

        # Compute fraction in control (using global limits)
        cr_ooc = np.sum(
            (correction_rates > all_limits["correction_rate"]["ucl"]) |
            (correction_rates < all_limits["correction_rate"]["lcl"])
        )
        tfr_ooc = np.sum(
            (tool_failure_rates > all_limits["tool_failure_rate"]["ucl"]) |
            (tool_failure_rates < all_limits["tool_failure_rate"]["lcl"])
        )

        pct_in_control = 1.0 - (cr_ooc + tfr_ooc) / (2 * len(ss))

        project_stats[proj] = {
            "n_sessions": len(ss),
            "mean_correction_rate": np.mean(correction_rates),
            "std_correction_rate": np.std(correction_rates, ddof=1) if len(ss) > 1 else 0,
            "mean_tool_failure_rate": np.mean(tool_failure_rates),
            "mean_amplification": np.mean(amp_ratios),
            "pct_in_control": pct_in_control * 100,
            "cr_ooc": int(cr_ooc),
            "tfr_ooc": int(tfr_ooc),
        }

        print(f"\n  {proj} ({len(ss)} sessions):")
        print(f"    Correction rate: {np.mean(correction_rates):.1f} "
              f"+/- {np.std(correction_rates, ddof=1) if len(ss)>1 else 0:.1f}%")
        print(f"    Tool failure rate: {np.mean(tool_failure_rates):.1f}%")
        print(f"    Amplification: {np.mean(amp_ratios):.1f}x")
        print(f"    In control: {pct_in_control*100:.0f}% "
              f"(CR OOC: {cr_ooc}, TFR OOC: {tfr_ooc})")

    # Plot cross-project comparison
    fig, axes = plt.subplots(2, 2, figsize=(16, 12))
    fig.suptitle("Cross-Project SPC Comparison", fontsize=14, fontweight="bold")

    sorted_projects = sorted(active_projects.keys(),
                              key=lambda p: project_stats[p]["mean_correction_rate"])

    # 1. Correction rate by project (box plot)
    ax = axes[0, 0]
    data = [np.array([s.correction_rate for s in active_projects[p]])
            for p in sorted_projects]
    bp = ax.boxplot(data, tick_labels=[p[:15] for p in sorted_projects],
                    patch_artist=True, vert=True)
    for patch, proj in zip(bp["boxes"], sorted_projects):
        patch.set_facecolor(PROJECT_COLORS.get(proj, "#CCCCCC"))
        patch.set_alpha(0.6)
    ax.axhline(all_limits["correction_rate"]["ucl"],
               color=COLORS["control_limit"], linestyle="--", alpha=0.8,
               label=f'UCL = {all_limits["correction_rate"]["ucl"]:.1f}')
    ax.axhline(all_limits["correction_rate"]["xbar"],
               color=COLORS["center_line"], linestyle="-", alpha=0.8,
               label=f'x-bar = {all_limits["correction_rate"]["xbar"]:.1f}')
    ax.set_title("Correction Rate by Project", fontsize=11)
    ax.set_ylabel("Corrections / 100 turns", fontsize=9)
    ax.tick_params(axis="x", rotation=45, labelsize=7)
    ax.legend(fontsize=7)
    ax.grid(True, alpha=0.3)

    # 2. Tool failure rate by project
    ax = axes[0, 1]
    data = [np.array([s.tool_failure_rate for s in active_projects[p]])
            for p in sorted_projects]
    bp = ax.boxplot(data, tick_labels=[p[:15] for p in sorted_projects],
                    patch_artist=True, vert=True)
    for patch, proj in zip(bp["boxes"], sorted_projects):
        patch.set_facecolor(PROJECT_COLORS.get(proj, "#CCCCCC"))
        patch.set_alpha(0.6)
    ax.axhline(all_limits["tool_failure_rate"]["ucl"],
               color=COLORS["control_limit"], linestyle="--", alpha=0.8)
    ax.axhline(all_limits["tool_failure_rate"]["xbar"],
               color=COLORS["center_line"], linestyle="-", alpha=0.8)
    ax.set_title("Tool Failure Rate by Project", fontsize=11)
    ax.set_ylabel("Failures / 100 tool calls", fontsize=9)
    ax.tick_params(axis="x", rotation=45, labelsize=7)
    ax.grid(True, alpha=0.3)

    # 3. % sessions in control per project
    ax = axes[1, 0]
    pcts = [project_stats[p]["pct_in_control"] for p in sorted_projects]
    colors = [PROJECT_COLORS.get(p, "#CCCCCC") for p in sorted_projects]
    bars = ax.bar(range(len(sorted_projects)), pcts, color=colors, alpha=0.7,
                  edgecolor="white")
    ax.set_xticks(range(len(sorted_projects)))
    ax.set_xticklabels([p[:15] for p in sorted_projects], rotation=45,
                       fontsize=7, ha="right")
    ax.axhline(80, color=COLORS["center_line"], linestyle="--", alpha=0.5,
               label="80% target")
    ax.set_title("% Sessions In Control (global limits)", fontsize=11)
    ax.set_ylabel("% in control", fontsize=9)
    ax.set_ylim(0, 105)
    ax.legend(fontsize=7)
    ax.grid(True, alpha=0.3)

    # 4. Scatter: correction rate vs amplification ratio
    ax = axes[1, 1]
    for proj in sorted_projects:
        ss = active_projects[proj]
        cr = [s.correction_rate for s in ss]
        ar = [s.amplification_ratio for s in ss]
        ax.scatter(cr, ar, c=PROJECT_COLORS.get(proj, "#999999"),
                   label=proj[:15], alpha=0.6, s=30, edgecolors="white",
                   linewidth=0.5)
    ax.set_xlabel("Correction Rate (per 100 turns)", fontsize=9)
    ax.set_ylabel("Amplification Ratio", fontsize=9)
    ax.set_title("Correction Rate vs Amplification", fontsize=11)
    ax.legend(fontsize=6, loc="upper right", ncol=2)
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    fig.savefig(os.path.join(FIGURES_DIR, "spc_cross_project.png"), dpi=150,
                bbox_inches="tight")
    plt.close()
    print("\nSaved: spc_cross_project.png")

    # ═══════════════════════════════════════════════════════════════════════════
    # CLAUDE.md Maturity Assessment
    # ═══════════════════════════════════════════════════════════════════════════
    print("\n--- CLAUDE.md Maturity vs Control Status ---")

    # CLAUDE.md maturity check skipped (corpus projects not on local filesystem)
    claude_md_info = {p: {"exists": False, "size": 0, "lines": 0} for p in active_projects}
    print("\n  (CLAUDE.md maturity check skipped -- corpus projects not on local filesystem)")

    # ═══════════════════════════════════════════════════════════════════════════
    # Summary Statistics for Report
    # ═══════════════════════════════════════════════════════════════════════════
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)

    total_ooc = len(ooc_sessions)
    total_sessions = len(sessions)
    print(f"\nTotal sessions analyzed: {total_sessions}")
    print(f"Sessions with at least one OOC violation: {total_ooc} "
          f"({total_ooc/total_sessions*100:.1f}%)")

    # Most problematic metric
    for key, m in metrics.items():
        lim = all_limits[key]
        ooc_count = int(np.sum(
            (~np.isnan(m["values"])) &
            ((m["values"] > lim["ucl"]) | (m["values"] < lim["lcl"]))
        ))
        print(f"  {m['label']}: {ooc_count} OOC ({ooc_count/total_sessions*100:.1f}%)")

    # Process capability summary
    print("\nProcess Capability Summary:")
    for key in metrics:
        cap = capability_results[key]
        status = "CAPABLE" if cap["cpk"] >= 1.0 else "NOT CAPABLE"
        print(f"  {metrics[key]['label']}: Cpk={cap['cpk']:.2f} [{status}]")

    # CUSUM shift detection
    print("\nCUSUM Shift Detection:")
    for key in metrics:
        cs = cusum_results[key]
        n_high = len(cs["signals_high"])
        n_low = len(cs["signals_low"])
        if n_high > 0 or n_low > 0:
            print(f"  {metrics[key]['label']}: "
                  f"{n_high} upward + {n_low} downward shift signals")
        else:
            print(f"  {metrics[key]['label']}: No persistent shifts detected")

    # Return data for report generation
    return {
        "sessions": sessions,
        "metrics": metrics,
        "all_limits": all_limits,
        "cusum_results": cusum_results,
        "capability_results": capability_results,
        "project_stats": project_stats,
        "ooc_sessions": ooc_sessions,
        "claude_md_info": claude_md_info,
        "active_projects": active_projects,
    }


if __name__ == "__main__":
    results = main()
