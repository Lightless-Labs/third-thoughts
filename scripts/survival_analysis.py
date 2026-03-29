#!/usr/bin/env python3
"""
Survival analysis on Claude Code session data.

Analyses:
1. Time-to-first-correction Kaplan-Meier survival curves (by project)
2. Nelson-Aalen cumulative hazard (does agent degrade or warm up?)
3. Cox proportional hazards (what predicts longer survival?)
4. Competing risks: correction vs session abandonment
"""

import json
import os
import re
import glob
import warnings
from datetime import datetime
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from lifelines import (
    KaplanMeierFitter,
    NelsonAalenFitter,
    CoxPHFitter,
)
from lifelines.statistics import logrank_test, multivariate_logrank_test

warnings.filterwarnings('ignore')

# ── Configuration ────────────────────────────────────────────────────────

CORPUS_DIR = os.environ.get(
    "CORPUS_DIR",
    os.environ.get("MIDDENS_CORPUS", "corpus/"),
)
OUTPUT_DIR = os.environ.get(
    "OUTPUT_DIR",
    os.environ.get("MIDDENS_OUTPUT", "experiments/"),
)
FIGURE_DIR = os.path.join(OUTPUT_DIR, "figures")
os.makedirs(FIGURE_DIR, exist_ok=True)

# Correction markers -- phrases that signal the human is correcting the agent
CORRECTION_PATTERNS = [
    r"^no[,.\s!]",           # "no, that's wrong", "no don't"
    r"^wrong",               # "wrong approach"
    r"not that",             # "not that file"
    r"^instead[,\s]",        # "instead, do X"
    r"^actually[,\s]",       # "actually, I meant..."
    r"why did you",          # "why did you delete that?"
    r"^don'?t\s",            # "don't do that"
    r"^stop",                # "stop"
    r"^wait[,.\s!]",         # "wait, that's wrong"
    r"that'?s not",          # "that's not right"
    r"^undo",                # "undo that"
    r"^revert",              # "revert"
    r"^fix ",                # "fix the error you just made"
    r"you (broke|messed|screwed)",  # "you broke it"
    r"^try again",           # "try again"
    r"that was wrong",
    r"that'?s wrong",
    r"^nope",
    r"i said",               # "i said to do X not Y"
    r"^please (don'?t|stop|undo|revert)",
]
CORRECTION_RE = re.compile("|".join(CORRECTION_PATTERNS), re.IGNORECASE)

# Patterns for messages that are NOT real human input
AUTOMATED_PATTERNS = [
    r"^<task-notification",
    r"^<command-message>",
    r"^<command-name>",
    r"^Tool loaded\.",
    r"^\[Request interrupted",
    r"^<system-reminder>",
    r"^<run_context>",
]
AUTOMATED_RE = re.compile("|".join(AUTOMATED_PATTERNS))

# Context exhaustion markers
EXHAUSTION_MARKERS = [
    "context window",
    "context limit",
    "token limit",
    "out of context",
    "conversation too long",
    "start a new session",
    "start a new conversation",
    "fresh session",
    "new chat",
    "running out of space",
    "context is getting",
]


def is_human_message(content):
    """Return (is_human, text) for a user message content field."""
    if isinstance(content, str):
        text = content.strip()
        if not text or len(text) < 3:
            return False, ""
        if AUTOMATED_RE.match(text):
            return False, ""
        return True, text
    elif isinstance(content, list):
        texts = []
        has_tool_result = False
        for block in content:
            if isinstance(block, dict):
                if block.get("type") == "text":
                    texts.append(block.get("text", ""))
                elif block.get("type") == "tool_result":
                    has_tool_result = True
        combined = " ".join(texts).strip()
        if has_tool_result and not combined:
            return False, ""
        if not combined or len(combined) < 3:
            return False, ""
        if AUTOMATED_RE.match(combined):
            return False, ""
        return True, combined
    return False, ""


def is_correction(text):
    """Check if user message is a correction."""
    # Only check the first ~200 chars for correction patterns
    snippet = text[:200].strip()
    return bool(CORRECTION_RE.search(snippet))


def has_exhaustion_signal(text):
    """Check if a message signals context exhaustion."""
    lower = text.lower()
    return any(marker in lower for marker in EXHAUSTION_MARKERS)


def parse_session(filepath):
    """
    Parse a JSONL session file.

    Returns dict with:
      - human_turns: list of (turn_number, text, is_correction, is_exhaustion)
      - assistant_turns: list of (turn_number, has_thinking, num_tool_calls, text_length)
      - first_user_prompt_length: int
      - total_human_turns: int
      - first_correction_turn: int or None
      - timestamps: list of timestamps
    """
    human_turns = []
    assistant_turns = []
    timestamps = []
    human_turn_num = 0

    first_user_prompt_length = 0
    tool_calls_first_5 = 0
    thinking_present = False

    try:
        with open(filepath) as f:
            for line in f:
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue

                ts = obj.get("timestamp")
                if ts:
                    timestamps.append(ts)

                msg = obj.get("message", {})
                role = msg.get("role", "")
                content = msg.get("content", "")

                if role == "user":
                    is_human, text = is_human_message(content)
                    if not is_human:
                        continue
                    human_turn_num += 1

                    corr = is_correction(text)
                    exhaust = has_exhaustion_signal(text)
                    human_turns.append((human_turn_num, text, corr, exhaust))

                    if human_turn_num == 1:
                        first_user_prompt_length = len(text)

                elif role == "assistant":
                    has_thinking = False
                    num_tools = 0
                    text_len = 0

                    if isinstance(content, list):
                        for block in content:
                            if isinstance(block, dict):
                                btype = block.get("type", "")
                                if btype == "thinking":
                                    has_thinking = True
                                    thinking_present = True
                                elif btype == "tool_use":
                                    num_tools += 1
                                elif btype == "text":
                                    text_len += len(block.get("text", ""))
                    elif isinstance(content, str):
                        text_len = len(content)

                    assistant_turns.append((human_turn_num, has_thinking, num_tools, text_len))

                    # Count tool calls in first 5 human turns
                    if human_turn_num <= 5:
                        tool_calls_first_5 += num_tools
    except Exception as e:
        return None

    if human_turn_num < 2:
        return None  # Skip single-turn sessions

    # Find first correction
    first_correction_turn = None
    for turn_num, text, corr, exhaust in human_turns:
        if corr:
            first_correction_turn = turn_num
            break

    # Check for exhaustion signal in last few messages
    session_exhausted = False
    for turn_num, text, corr, exhaust in human_turns[-3:]:
        if exhaust:
            session_exhausted = True
    # Also check assistant messages for exhaustion
    # (We'd need the text, so approximate: very long sessions are more likely exhausted)

    return {
        "human_turns": human_turns,
        "assistant_turns": assistant_turns,
        "total_human_turns": human_turn_num,
        "first_correction_turn": first_correction_turn,
        "first_user_prompt_length": first_user_prompt_length,
        "tool_calls_first_5": tool_calls_first_5,
        "thinking_present": thinking_present,
        "timestamps": timestamps,
        "session_exhausted": session_exhausted,
    }


def compute_project_maturity(project_sessions):
    """Given a dict of project -> list of (filepath, parsed), compute maturity in days."""
    project_first_dates = {}
    for project, sessions in project_sessions.items():
        dates = []
        for filepath, parsed in sessions:
            if parsed["timestamps"]:
                try:
                    dt = datetime.fromisoformat(parsed["timestamps"][0].replace("Z", "+00:00"))
                    dates.append(dt)
                except:
                    pass
        if dates:
            project_first_dates[project] = min(dates)

    maturity = {}
    for project, sessions in project_sessions.items():
        if project not in project_first_dates:
            maturity[project] = 0
            continue
        first = project_first_dates[project]
        for filepath, parsed in sessions:
            if parsed["timestamps"]:
                try:
                    dt = datetime.fromisoformat(parsed["timestamps"][0].replace("Z", "+00:00"))
                    days = (dt - first).days
                    maturity[(project, filepath)] = max(0, days)
                except:
                    maturity[(project, filepath)] = 0
            else:
                maturity[(project, filepath)] = 0

    return maturity, project_first_dates


# ── Main data collection ──────────────────────────────────────────────

print("=" * 70)
print("SURVIVAL ANALYSIS OF CLAUDE CODE SESSIONS")
print("=" * 70)

# Collect all sessions by recursively finding JSONL files in the corpus
# Use os.walk with followlinks=True since Python 3.9 rglob doesn't follow symlinks
def _find_jsonl_files(root):
    results = []
    for dirpath, dirnames, filenames in os.walk(root, followlinks=True):
        for fn in filenames:
            if fn.endswith(".jsonl"):
                results.append(os.path.join(dirpath, fn))
    return sorted(results)

all_jsonl = _find_jsonl_files(CORPUS_DIR)
print(f"\nFound {len(all_jsonl)} JSONL files in corpus")

project_sessions = defaultdict(list)
all_sessions = []
skipped = 0

for jf in all_jsonl:
    # Derive project name from directory structure
    rel = os.path.relpath(jf, CORPUS_DIR)
    parts = rel.split(os.sep)
    project_name = "unknown"
    if "projects" in parts:
        proj_idx = parts.index("projects")
        if proj_idx + 1 < len(parts):
            project_name = parts[proj_idx + 1]

    parsed = parse_session(jf)
    if parsed is None:
        skipped += 1
        continue
    project_sessions[project_name].append((jf, parsed))
    all_sessions.append((project_name, jf, parsed))

print(f"Parsed {len(all_sessions)} multi-turn sessions (skipped {skipped} single-turn)")
print(f"Projects with sessions: {len(project_sessions)}")
for pname, sessions in sorted(project_sessions.items(), key=lambda x: -len(x[1])):
    print(f"  {pname}: {len(sessions)} sessions")


# ── Build DataFrame ──────────────────────────────────────────────────

maturity_map, first_dates = compute_project_maturity(project_sessions)

rows = []
for project_name, filepath, parsed in all_sessions:
    t = parsed["total_human_turns"]
    fc = parsed["first_correction_turn"]

    # For survival analysis: time = turn of first correction, or total turns if censored
    if fc is not None:
        duration = fc
        event_correction = 1
    else:
        duration = t
        event_correction = 0

    # Competing risk: correction vs exhaustion
    if fc is not None:
        failure_type = "correction"
    elif parsed["session_exhausted"]:
        failure_type = "exhaustion"
    else:
        failure_type = "censored"  # session ended normally

    mat_key = (project_name, filepath)
    maturity_days = maturity_map.get(mat_key, 0)

    rows.append({
        "project": project_name,
        "filepath": filepath,
        "total_turns": t,
        "first_correction_turn": fc,
        "duration": duration,
        "event_correction": event_correction,
        "failure_type": failure_type,
        "prompt_length": parsed["first_user_prompt_length"],
        "tool_calls_first_5": parsed["tool_calls_first_5"],
        "thinking_present": int(parsed["thinking_present"]),
        "maturity_days": maturity_days,
        "session_exhausted": int(parsed["session_exhausted"]),
        "num_corrections": sum(1 for _, _, c, _ in parsed["human_turns"] if c),
    })

df = pd.DataFrame(rows)
print(f"\nDataFrame shape: {df.shape}")
print(f"Sessions with corrections: {df['event_correction'].sum()} ({100*df['event_correction'].mean():.1f}%)")
print(f"Sessions censored (no correction): {(df['event_correction']==0).sum()}")
print(f"Median session length: {df['total_turns'].median():.0f} human turns")
print(f"Mean session length: {df['total_turns'].mean():.1f} human turns")
print(f"Median time to first correction (uncensored): {df[df['event_correction']==1]['duration'].median():.0f}")


# ══════════════════════════════════════════════════════════════════════
# ANALYSIS 1: Kaplan-Meier Survival Curves
# ══════════════════════════════════════════════════════════════════════

print("\n" + "=" * 70)
print("ANALYSIS 1: KAPLAN-MEIER SURVIVAL CURVES")
print("=" * 70)

# Overall KM curve
kmf = KaplanMeierFitter()
kmf.fit(df["duration"], event_observed=df["event_correction"], label="All Sessions")

print(f"\nOverall survival estimates:")
for t_val in [5, 10, 20, 50, 100]:
    if t_val <= df["duration"].max():
        surv = kmf.predict(t_val)
        print(f"  S({t_val}) = {surv:.3f}  (probability of no correction by turn {t_val})")

median_survival = kmf.median_survival_time_
print(f"\nMedian survival time: {median_survival}")

# Plot overall KM
fig, ax = plt.subplots(figsize=(10, 6))
kmf.plot_survival_function(ax=ax)
ax.set_xlabel("Turn Number")
ax.set_ylabel("Survival Probability (No Correction)")
ax.set_title("Kaplan-Meier: Time to First Human Correction")
ax.set_xlim(0, min(200, df["duration"].quantile(0.95)))
ax.grid(True, alpha=0.3)
fig.savefig(os.path.join(FIGURE_DIR, "km_overall.png"), dpi=150, bbox_inches="tight")
plt.close(fig)
print(f"  Saved: {FIGURE_DIR}/km_overall.png")

# KM by project (top projects by session count)
top_projects = df["project"].value_counts().head(8).index.tolist()
df_top = df[df["project"].isin(top_projects)]

fig, ax = plt.subplots(figsize=(12, 7))
for project in top_projects:
    mask = df_top["project"] == project
    sub = df_top[mask]
    if len(sub) < 5:
        continue
    kmf_p = KaplanMeierFitter()
    kmf_p.fit(sub["duration"], event_observed=sub["event_correction"], label=project)
    kmf_p.plot_survival_function(ax=ax)

ax.set_xlabel("Turn Number")
ax.set_ylabel("Survival Probability (No Correction)")
ax.set_title("Kaplan-Meier Survival by Project")
ax.set_xlim(0, min(150, df_top["duration"].quantile(0.95)))
ax.legend(fontsize=8)
ax.grid(True, alpha=0.3)
fig.savefig(os.path.join(FIGURE_DIR, "km_by_project.png"), dpi=150, bbox_inches="tight")
plt.close(fig)
print(f"  Saved: {FIGURE_DIR}/km_by_project.png")

# Log-rank test: do projects differ significantly?
print("\nLog-rank tests (project comparison):")
projects_for_test = [p for p in top_projects if len(df[df["project"] == p]) >= 5]
if len(projects_for_test) >= 2:
    df_test = df[df["project"].isin(projects_for_test)]
    try:
        result = multivariate_logrank_test(
            df_test["duration"],
            df_test["project"],
            df_test["event_correction"]
        )
        print(f"  Multivariate log-rank test statistic: {result.test_statistic:.3f}")
        print(f"  p-value: {result.p_value:.6f}")
        if result.p_value < 0.05:
            print("  => Significant difference in survival across projects")
        else:
            print("  => No significant difference in survival across projects")
    except Exception as e:
        print(f"  Log-rank test failed: {e}")

# Compare high-maturity vs low-maturity sessions
med_maturity = df["maturity_days"].median()
df["maturity_group"] = np.where(df["maturity_days"] > med_maturity, "Mature (>{:.0f}d)".format(med_maturity), "Early (<={:.0f}d)".format(med_maturity))

fig, ax = plt.subplots(figsize=(10, 6))
for label in df["maturity_group"].unique():
    mask = df["maturity_group"] == label
    sub = df[mask]
    if len(sub) < 5:
        continue
    kmf_m = KaplanMeierFitter()
    kmf_m.fit(sub["duration"], event_observed=sub["event_correction"], label=label)
    kmf_m.plot_survival_function(ax=ax)

ax.set_xlabel("Turn Number")
ax.set_ylabel("Survival Probability (No Correction)")
ax.set_title("Kaplan-Meier: Mature vs Early Projects")
ax.set_xlim(0, min(150, df["duration"].quantile(0.95)))
ax.grid(True, alpha=0.3)
fig.savefig(os.path.join(FIGURE_DIR, "km_maturity.png"), dpi=150, bbox_inches="tight")
plt.close(fig)
print(f"  Saved: {FIGURE_DIR}/km_maturity.png")

# Log-rank for maturity groups
early = df[df["maturity_days"] <= med_maturity]
mature = df[df["maturity_days"] > med_maturity]
if len(early) >= 5 and len(mature) >= 5:
    try:
        lr = logrank_test(early["duration"], mature["duration"],
                         event_observed_A=early["event_correction"],
                         event_observed_B=mature["event_correction"])
        print(f"\nMaturity log-rank test: statistic={lr.test_statistic:.3f}, p={lr.p_value:.6f}")
        if lr.p_value < 0.05:
            print("  => Mature projects have significantly different survival")
        else:
            print("  => No significant difference by maturity")
    except Exception as e:
        print(f"  Maturity log-rank failed: {e}")


# ══════════════════════════════════════════════════════════════════════
# ANALYSIS 2: Nelson-Aalen Cumulative Hazard
# ══════════════════════════════════════════════════════════════════════

print("\n" + "=" * 70)
print("ANALYSIS 2: NELSON-AALEN CUMULATIVE HAZARD")
print("=" * 70)

naf = NelsonAalenFitter()
naf.fit(df["duration"], event_observed=df["event_correction"], label="All Sessions")

fig, axes = plt.subplots(1, 2, figsize=(14, 6))

# Cumulative hazard
naf.plot_cumulative_hazard(ax=axes[0])
axes[0].set_xlabel("Turn Number")
axes[0].set_ylabel("Cumulative Hazard")
axes[0].set_title("Nelson-Aalen Cumulative Hazard")
axes[0].set_xlim(0, min(150, df["duration"].quantile(0.95)))
axes[0].grid(True, alpha=0.3)

# Hazard rate (smoothed derivative)
# Use bandwidth for kernel smoothing
try:
    naf_smooth = NelsonAalenFitter()
    naf_smooth.fit(df["duration"], event_observed=df["event_correction"])
    hazard = naf_smooth.smoothed_hazard_(bandwidth=3)
    axes[1].plot(hazard.index, hazard.values, label="Smoothed hazard (bw=3)")
    axes[1].set_xlabel("Turn Number")
    axes[1].set_ylabel("Hazard Rate")
    axes[1].set_title("Smoothed Hazard Rate Over Session Lifetime")
    axes[1].set_xlim(0, min(150, df["duration"].quantile(0.95)))
    axes[1].grid(True, alpha=0.3)
    axes[1].legend()

    # Determine trend
    if len(hazard) > 10:
        early_hazard = hazard.iloc[:len(hazard)//3].mean().values[0] if hasattr(hazard.iloc[:len(hazard)//3].mean(), 'values') else hazard.iloc[:len(hazard)//3].mean()
        late_hazard = hazard.iloc[2*len(hazard)//3:].mean().values[0] if hasattr(hazard.iloc[2*len(hazard)//3:].mean(), 'values') else hazard.iloc[2*len(hazard)//3:].mean()

        if isinstance(early_hazard, pd.Series):
            early_hazard = early_hazard.iloc[0]
        if isinstance(late_hazard, pd.Series):
            late_hazard = late_hazard.iloc[0]

        ratio = late_hazard / early_hazard if early_hazard > 0 else 1.0
        print(f"\nHazard rate analysis:")
        print(f"  Early-session hazard (first third): {early_hazard:.4f}")
        print(f"  Late-session hazard (last third): {late_hazard:.4f}")
        print(f"  Ratio (late/early): {ratio:.2f}")
        if ratio > 1.3:
            print("  => INCREASING hazard: agent degrades over time")
            hazard_trend = "increasing"
        elif ratio < 0.7:
            print("  => DECREASING hazard: agent warms up / stabilizes")
            hazard_trend = "decreasing"
        else:
            print("  => FLAT hazard: correction risk stays roughly constant")
            hazard_trend = "flat"
except Exception as e:
    print(f"  Smoothed hazard computation error: {e}")
    hazard_trend = "unknown"

fig.savefig(os.path.join(FIGURE_DIR, "hazard_analysis.png"), dpi=150, bbox_inches="tight")
plt.close(fig)
print(f"  Saved: {FIGURE_DIR}/hazard_analysis.png")

# Hazard by project
fig, ax = plt.subplots(figsize=(12, 7))
for project in top_projects[:5]:
    mask = df["project"] == project
    sub = df[mask]
    if len(sub) < 10:
        continue
    naf_p = NelsonAalenFitter()
    naf_p.fit(sub["duration"], event_observed=sub["event_correction"], label=project)
    try:
        h = naf_p.smoothed_hazard_(bandwidth=3)
        ax.plot(h.index, h.values, label=project)
    except:
        pass

ax.set_xlabel("Turn Number")
ax.set_ylabel("Hazard Rate")
ax.set_title("Smoothed Hazard Rate by Project")
ax.set_xlim(0, min(100, df["duration"].quantile(0.90)))
ax.legend(fontsize=8)
ax.grid(True, alpha=0.3)
fig.savefig(os.path.join(FIGURE_DIR, "hazard_by_project.png"), dpi=150, bbox_inches="tight")
plt.close(fig)
print(f"  Saved: {FIGURE_DIR}/hazard_by_project.png")


# ══════════════════════════════════════════════════════════════════════
# ANALYSIS 3: Cox Proportional Hazards
# ══════════════════════════════════════════════════════════════════════

print("\n" + "=" * 70)
print("ANALYSIS 3: COX PROPORTIONAL HAZARDS")
print("=" * 70)

# Prepare covariates
cox_df = df[["duration", "event_correction", "maturity_days", "prompt_length",
             "tool_calls_first_5", "thinking_present"]].copy()

# Log-transform skewed features
cox_df["log_prompt_length"] = np.log1p(cox_df["prompt_length"])
cox_df["log_maturity"] = np.log1p(cox_df["maturity_days"])
cox_df["log_tool_calls"] = np.log1p(cox_df["tool_calls_first_5"])

# Drop original skewed columns, keep log versions
cox_fit_df = cox_df[["duration", "event_correction", "log_maturity",
                      "log_prompt_length", "log_tool_calls", "thinking_present"]].copy()

# Remove zero-duration rows
cox_fit_df = cox_fit_df[cox_fit_df["duration"] > 0]

# Standardize for coefficient comparison
for col in ["log_maturity", "log_prompt_length", "log_tool_calls"]:
    mean = cox_fit_df[col].mean()
    std = cox_fit_df[col].std()
    if std > 0:
        cox_fit_df[col] = (cox_fit_df[col] - mean) / std

print(f"\nCox PH model with {len(cox_fit_df)} sessions")
print(f"Covariates: log_maturity, log_prompt_length, log_tool_calls, thinking_present")

cph = CoxPHFitter()
try:
    cph.fit(cox_fit_df, duration_col="duration", event_col="event_correction")
    cph.print_summary()

    # Extract key findings
    summary = cph.summary
    print("\nInterpretation of hazard ratios (exp(coef)):")
    for idx in summary.index:
        hr = summary.loc[idx, "exp(coef)"]
        p = summary.loc[idx, "p"]
        sig = "***" if p < 0.001 else "**" if p < 0.01 else "*" if p < 0.05 else ""
        direction = "increases" if hr > 1 else "decreases"
        print(f"  {idx}: HR={hr:.3f} (p={p:.4f}) {sig}")
        print(f"    => 1 SD increase in {idx} {direction} correction hazard by {abs(hr-1)*100:.1f}%")

    # Plot coefficients
    fig, ax = plt.subplots(figsize=(10, 5))
    cph.plot(ax=ax)
    ax.set_title("Cox PH: Hazard Ratios for Correction Risk")
    ax.axvline(x=0, color='grey', linestyle='--', alpha=0.5)
    fig.savefig(os.path.join(FIGURE_DIR, "cox_coefficients.png"), dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"\n  Saved: {FIGURE_DIR}/cox_coefficients.png")

    # Concordance index
    print(f"\nConcordance index: {cph.concordance_index_:.3f}")
    print(f"  (0.5 = random, 1.0 = perfect prediction)")

    cox_success = True
except Exception as e:
    print(f"Cox PH fitting failed: {e}")
    cox_success = False


# ══════════════════════════════════════════════════════════════════════
# ANALYSIS 4: Competing Risks
# ══════════════════════════════════════════════════════════════════════

print("\n" + "=" * 70)
print("ANALYSIS 4: COMPETING RISKS")
print("=" * 70)

# Failure type breakdown
failure_counts = df["failure_type"].value_counts()
print(f"\nFailure type distribution:")
for ft, count in failure_counts.items():
    print(f"  {ft}: {count} ({100*count/len(df):.1f}%)")

# For sessions with corrections, was it also near exhaustion?
corrected = df[df["failure_type"] == "correction"]
exhausted = df[df["failure_type"] == "exhaustion"]
censored = df[df["failure_type"] == "censored"]

print(f"\nSessions ending in correction: {len(corrected)}")
if len(corrected) > 0:
    print(f"  Median turn of first correction: {corrected['first_correction_turn'].median():.0f}")
    print(f"  Mean total turns in corrected sessions: {corrected['total_turns'].mean():.1f}")

print(f"\nSessions ending in exhaustion (no correction): {len(exhausted)}")
if len(exhausted) > 0:
    print(f"  Mean total turns: {exhausted['total_turns'].mean():.1f}")

print(f"\nSessions ending normally (censored): {len(censored)}")
if len(censored) > 0:
    print(f"  Mean total turns: {censored['total_turns'].mean():.1f}")

# Cumulative incidence functions (approximation)
# Treat correction and exhaustion as competing events
fig, ax = plt.subplots(figsize=(10, 6))

# For correction events
df_corr = df.copy()
df_corr["event"] = (df_corr["failure_type"] == "correction").astype(int)
kmf_corr = KaplanMeierFitter()
kmf_corr.fit(df_corr["duration"], event_observed=df_corr["event"], label="Correction")

# For exhaustion events
df_exh = df.copy()
df_exh["event"] = (df_exh["failure_type"] == "exhaustion").astype(int)
kmf_exh = KaplanMeierFitter()
kmf_exh.fit(df_exh["total_turns"], event_observed=df_exh["event"], label="Exhaustion")

# Plot 1-S(t) = cumulative incidence
ci_corr = 1 - kmf_corr.survival_function_
ci_exh = 1 - kmf_exh.survival_function_

ax.plot(ci_corr.index, ci_corr.values, label="Correction (cumulative incidence)", color="red")
ax.plot(ci_exh.index, ci_exh.values, label="Exhaustion (cumulative incidence)", color="blue")
ax.set_xlabel("Turn Number")
ax.set_ylabel("Cumulative Incidence")
ax.set_title("Competing Risks: Correction vs Context Exhaustion")
ax.set_xlim(0, min(200, df["total_turns"].quantile(0.95)))
ax.legend()
ax.grid(True, alpha=0.3)
fig.savefig(os.path.join(FIGURE_DIR, "competing_risks.png"), dpi=150, bbox_inches="tight")
plt.close(fig)
print(f"\n  Saved: {FIGURE_DIR}/competing_risks.png")

# Density of corrections by turn
if len(corrected) > 0:
    fig, ax = plt.subplots(figsize=(10, 5))
    bins = min(50, max(10, len(corrected) // 3))
    ax.hist(corrected["first_correction_turn"], bins=bins, edgecolor="black", alpha=0.7, color="salmon")
    ax.set_xlabel("Turn Number of First Correction")
    ax.set_ylabel("Count")
    ax.set_title("Distribution of First Correction Timing")
    ax.axvline(corrected["first_correction_turn"].median(), color="red", linestyle="--",
               label=f"Median: turn {corrected['first_correction_turn'].median():.0f}")
    ax.legend()
    ax.grid(True, alpha=0.3)
    fig.savefig(os.path.join(FIGURE_DIR, "correction_distribution.png"), dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved: {FIGURE_DIR}/correction_distribution.png")


# ══════════════════════════════════════════════════════════════════════
# SUMMARY
# ══════════════════════════════════════════════════════════════════════

print("\n" + "=" * 70)
print("SUMMARY OF KEY FINDINGS")
print("=" * 70)

print(f"""
Dataset:
  - {len(all_sessions)} multi-turn sessions across {len(project_sessions)} projects
  - {df['event_correction'].sum()} sessions ({100*df['event_correction'].mean():.1f}%) contained a human correction
  - Median session: {df['total_turns'].median():.0f} human turns

Kaplan-Meier:
  - Median survival (time to first correction): {median_survival}
  - S(5) = {kmf.predict(5):.3f} (prob. of no correction by turn 5)
  - S(10) = {kmf.predict(10):.3f} (prob. of no correction by turn 10)
  - S(20) = {kmf.predict(min(20, df['duration'].max())):.3f} (prob. of no correction by turn 20)

Hazard Rate:
  - Trend: {hazard_trend}

Competing Risks:
  - Correction: {failure_counts.get('correction', 0)} ({100*failure_counts.get('correction', 0)/len(df):.1f}%)
  - Exhaustion: {failure_counts.get('exhaustion', 0)} ({100*failure_counts.get('exhaustion', 0)/len(df):.1f}%)
  - Normal end: {failure_counts.get('censored', 0)} ({100*failure_counts.get('censored', 0)/len(df):.1f}%)
""")

# Save numeric results for the report
results = {
    "n_sessions": len(all_sessions),
    "n_projects": len(project_sessions),
    "pct_with_correction": float(100 * df["event_correction"].mean()),
    "median_turns": float(df["total_turns"].median()),
    "median_survival": str(median_survival),
    "hazard_trend": hazard_trend,
    "failure_correction_pct": float(100 * failure_counts.get("correction", 0) / len(df)),
    "failure_exhaustion_pct": float(100 * failure_counts.get("exhaustion", 0) / len(df)),
    "failure_censored_pct": float(100 * failure_counts.get("censored", 0) / len(df)),
}
if cox_success:
    results["concordance_index"] = float(cph.concordance_index_)
    results["cox_summary"] = cph.summary.to_dict()

with open(os.path.join(OUTPUT_DIR, "survival-results.json"), "w") as f:
    json.dump(results, f, indent=2, default=str)
print(f"Results saved to {OUTPUT_DIR}/survival-results.json")

print("\nDone.")
