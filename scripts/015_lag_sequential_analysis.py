#!/usr/bin/env python3
"""
Lag Sequential Analysis (Bakeman & Quera) on Claude Code session data.

Converts sessions to coded event sequences, builds transitional frequency
matrices at lags 1-5, and tests statistical significance via z-scores.

Event codes:
  UR = user request (no correction signal)
  UC = user correction ("no", "wrong", "not that", "instead", "actually", "why")
  UA = user approval ("good", "great", "yes", "thanks", "perfect", "ship")
  AR = agent reads (Read, Glob, Grep tool calls)
  AE = agent edits (Edit, Write)
  AB = agent bash (Bash)
  AT = agent text (text output)
  AK = agent thinks (thinking block)
  AF = agent fails (tool_result with error)
"""

import json
import glob
import os
import re
import sys
import math
import random
from collections import Counter, defaultdict
from pathlib import Path

# ──────────────────────────────────────────────────────────────────────
# Configuration
# ──────────────────────────────────────────────────────────────────────

SESSION_GLOB = os.environ.get("SESSION_GLOB", os.path.join(os.environ.get("MIDDENS_CORPUS", "corpus/"), "**/*.jsonl"))
MAX_SESSIONS = 200
MIN_EVENTS_PER_SESSION = 20  # Skip tiny sessions
MAX_LAGS = 5
ALPHA = 0.05
Z_CRITICAL = 1.96  # two-tailed

EVENT_CODES = ["UR", "UC", "UA", "AR", "AE", "AB", "AT", "AK", "AF"]

# Max message length for correction/approval classification.
# Long messages are instructions/requests, not short reactive signals.
MAX_SIGNAL_LENGTH = 500

# Correction keywords (case-insensitive, word-boundary matched)
# These are checked ONLY on short messages (< MAX_SIGNAL_LENGTH)
CORRECTION_PATTERNS = [
    r"\bno\b", r"\bwrong\b", r"\bnot that\b", r"\binstead\b",
    r"\bactually\b", r"\bwhy\b", r"\bdon'?t\b", r"\bstop\b",
    r"\bthat'?s not\b", r"\bnot what\b", r"\bincorrect\b",
    r"\bfix\b", r"\bredo\b",
]
CORRECTION_RE = re.compile("|".join(CORRECTION_PATTERNS), re.IGNORECASE)

# Stronger correction patterns that work even on longer messages
STRONG_CORRECTION_PATTERNS = [
    r"^no[.,!]?\s",  # Message starts with "no"
    r"^wrong\b", r"^that'?s not", r"^not what i",
    r"^don'?t\b", r"^stop\b", r"^incorrect\b",
]
STRONG_CORRECTION_RE = re.compile("|".join(STRONG_CORRECTION_PATTERNS), re.IGNORECASE)

# Approval keywords
APPROVAL_PATTERNS = [
    r"\bgood\b", r"\bgreat\b", r"\byes\b", r"\bthanks\b",
    r"\bthank you\b", r"\bperfect\b", r"\bship\b", r"\bnice\b",
    r"\blgtm\b", r"\blooks good\b", r"\bawesome\b", r"\bexcellent\b",
    r"\bwell done\b", r"\bcorrect\b",
]
APPROVAL_RE = re.compile("|".join(APPROVAL_PATTERNS), re.IGNORECASE)

# System/automated message indicators (prefix match on stripped text)
SYSTEM_INDICATORS = [
    "<command-", "<run_context", "<task-notification",
    "You are ", "## SECURITY", "# /", "<file-",
    "SYSTEM:", "Round:", "You are Boucle",
    "Stop hook", "Pre-tool", "Post-tool",  # Hook feedback messages
    "Hook ", "Permission",
    "<local-command-", "Unknown skill:",  # CLI feedback messages
    "[Request interrupted",  # User interruptions (not real messages)
]

# Read tools
READ_TOOLS = {"Read", "Glob", "Grep"}
EDIT_TOOLS = {"Edit", "Write"}
BASH_TOOLS = {"Bash"}

# ──────────────────────────────────────────────────────────────────────
# Step 1: Code events
# ──────────────────────────────────────────────────────────────────────

def extract_user_text(msg):
    """Extract text content from a user message."""
    content = msg.get("message", {}).get("content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        texts = []
        for c in content:
            if c.get("type") == "text":
                texts.append(c.get("text", ""))
        return " ".join(texts)
    return ""


def is_tool_result(msg):
    """Check if this user message is a tool result (automated, not human)."""
    if msg.get("toolUseResult"):
        return True
    content = msg.get("message", {}).get("content", [])
    if isinstance(content, list):
        return any(c.get("type") == "tool_result" for c in content)
    return False


def has_error(msg):
    """Check if a tool_result message contains an error."""
    content = msg.get("message", {}).get("content", [])
    if isinstance(content, list):
        for c in content:
            if c.get("type") == "tool_result" and c.get("is_error"):
                return True
            # Also check nested content for error markers
            sub = c.get("content", "")
            if isinstance(sub, str) and ("error" in sub.lower()[:50] or "Error" in sub[:50]):
                if c.get("is_error"):
                    return True
    return False


def classify_user_message(msg):
    """Classify a user message as UR, UC, or UA.

    Key insight: correction and approval are SHORT reactive signals.
    Long messages (>500 chars) are instructions/requests, not corrections,
    unless they start with a strong correction keyword.
    System prompts and automated messages are filtered out entirely.
    """
    text = extract_user_text(msg)
    if not text or len(text.strip()) < 2:
        return None

    stripped = text.strip()

    # Skip system/automated messages
    for indicator in SYSTEM_INDICATORS:
        if stripped.startswith(indicator):
            return None

    # Skip messages that look like prompts (contain role instructions)
    if "Your ONLY job" in text or "Your task is" in text:
        return None

    text_len = len(stripped)

    # For short messages, use standard keyword matching
    if text_len < MAX_SIGNAL_LENGTH:
        # Check for correction signals first (they take priority)
        if CORRECTION_RE.search(stripped):
            return "UC"
        # Check for approval signals
        if APPROVAL_RE.search(stripped):
            return "UA"
    else:
        # For long messages, only match if it STARTS with a correction keyword
        if STRONG_CORRECTION_RE.search(stripped):
            return "UC"

    # Default: user request
    return "UR"


def classify_assistant_content(content_block):
    """Classify an assistant content block into event code(s)."""
    events = []
    block_type = content_block.get("type", "")

    if block_type == "thinking":
        events.append("AK")
    elif block_type == "text":
        text = content_block.get("text", "")
        if text.strip():
            events.append("AT")
    elif block_type == "tool_use":
        tool_name = content_block.get("name", "")
        if tool_name in READ_TOOLS:
            events.append("AR")
        elif tool_name in EDIT_TOOLS:
            events.append("AE")
        elif tool_name in BASH_TOOLS:
            events.append("AB")
        else:
            # Other tools (TaskCreate, etc.) - classify as agent action
            events.append("AT")

    return events


def code_session(filepath):
    """Convert a session JSONL file to a sequence of coded events."""
    events = []

    try:
        with open(filepath, 'r') as f:
            lines = f.readlines()
    except Exception:
        return events

    for line in lines:
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue

        msg_type = msg.get("type", "")

        if msg_type == "user":
            # Check if it's a tool result (automated response)
            if is_tool_result(msg):
                # Check for errors in tool results
                if has_error(msg):
                    events.append("AF")
                # Otherwise skip - tool results aren't human events
                continue

            # Human user message
            code = classify_user_message(msg)
            if code:
                events.append(code)

        elif msg_type == "assistant":
            content = msg.get("message", {}).get("content", [])
            if isinstance(content, list):
                for block in content:
                    codes = classify_assistant_content(block)
                    events.extend(codes)

    return events


# ──────────────────────────────────────────────────────────────────────
# Step 2: Build transitional frequency matrices
# ──────────────────────────────────────────────────────────────────────

def build_frequency_matrix(sequences, lag):
    """
    Build a transitional frequency matrix at a given lag.

    For each pair of events (i, j), count how many times event j
    occurs exactly `lag` steps after event i.
    """
    n = len(EVENT_CODES)
    code_to_idx = {c: i for i, c in enumerate(EVENT_CODES)}
    matrix = [[0] * n for _ in range(n)]

    for seq in sequences:
        for t in range(len(seq) - lag):
            i_code = seq[t]
            j_code = seq[t + lag]
            if i_code in code_to_idx and j_code in code_to_idx:
                i = code_to_idx[i_code]
                j = code_to_idx[j_code]
                matrix[i][j] += 1

    return matrix


# ──────────────────────────────────────────────────────────────────────
# Step 3: Statistical significance testing
# ──────────────────────────────────────────────────────────────────────

def compute_significance(matrix):
    """
    Compute z-scores for each cell in the transitional frequency matrix.

    Z = (observed - expected) / sqrt(expected * (1 - p_row) * (1 - p_col))

    where:
        expected = row_total * col_total / grand_total
        p_row = row_total / grand_total
        p_col = col_total / grand_total
    """
    n = len(matrix)
    grand_total = sum(sum(row) for row in matrix)

    if grand_total == 0:
        return [[0.0] * n for _ in range(n)], matrix, [[0.0] * n for _ in range(n)]

    row_totals = [sum(row) for row in matrix]
    col_totals = [sum(matrix[r][c] for r in range(n)) for c in range(n)]

    expected = [[0.0] * n for _ in range(n)]
    z_scores = [[0.0] * n for _ in range(n)]

    for i in range(n):
        for j in range(n):
            if grand_total > 0:
                exp = (row_totals[i] * col_totals[j]) / grand_total
                expected[i][j] = exp

                p_row = row_totals[i] / grand_total
                p_col = col_totals[j] / grand_total

                denom = exp * (1 - p_row) * (1 - p_col)
                if denom > 0:
                    z_scores[i][j] = (matrix[i][j] - exp) / math.sqrt(denom)

    return z_scores, matrix, expected


# ──────────────────────────────────────────────────────────────────────
# Reporting
# ──────────────────────────────────────────────────────────────────────

def format_matrix(matrix, label, decimals=0):
    """Format a matrix as a markdown table."""
    lines = []
    lines.append(f"\n### {label}\n")

    # Header
    header = "| |" + "|".join(f" **{c}** " for c in EVENT_CODES) + "|"
    sep = "|---|" + "|".join("---:" for _ in EVENT_CODES) + "|"
    lines.append(header)
    lines.append(sep)

    for i, code in enumerate(EVENT_CODES):
        if decimals == 0:
            cells = "|".join(f" {matrix[i][j]:>6d} " for j in range(len(EVENT_CODES)))
        else:
            cells = "|".join(f" {matrix[i][j]:>6.{decimals}f} " for j in range(len(EVENT_CODES)))
        lines.append(f"| **{code}** |{cells}|")

    return "\n".join(lines)


def format_significant_cells(z_scores, matrix, expected, lag):
    """Format significant cells for a given lag."""
    lines = []
    significant = []

    for i, code_i in enumerate(EVENT_CODES):
        for j, code_j in enumerate(EVENT_CODES):
            z = z_scores[i][j]
            if abs(z) > Z_CRITICAL and matrix[i][j] >= 5:  # min 5 observations
                direction = "excitatory" if z > 0 else "inhibitory"
                significant.append({
                    "given": code_i,
                    "target": code_j,
                    "lag": lag,
                    "observed": matrix[i][j],
                    "expected": expected[i][j],
                    "z": z,
                    "direction": direction,
                })

    # Sort by absolute z-score descending
    significant.sort(key=lambda x: abs(x["z"]), reverse=True)

    if significant:
        lines.append(f"\n#### Significant transitions at lag {lag} (|z| > {Z_CRITICAL}, n >= 5)\n")
        lines.append("| Given | Target | Observed | Expected | z-score | Direction |")
        lines.append("|-------|--------|----------|----------|---------|-----------|")
        for s in significant:
            lines.append(
                f"| {s['given']} | {s['target']} | {s['observed']} | "
                f"{s['expected']:.1f} | {s['z']:+.2f} | {s['direction']} |"
            )
    else:
        lines.append(f"\nNo significant transitions at lag {lag}.")

    return "\n".join(lines), significant


def answer_key_questions(all_significant):
    """Answer the specific research questions."""
    lines = []
    lines.append("\n## Key Research Questions\n")

    # Index significant findings
    by_pair_lag = {}
    for s in all_significant:
        key = (s["given"], s["target"], s["lag"])
        by_pair_lag[key] = s

    # Q1: Does AF predict UC at lag 1? At lag 2?
    lines.append("### Q1: Does AF (agent failure) predict UC (user correction)?")
    for lag in [1, 2, 3]:
        key = ("AF", "UC", lag)
        if key in by_pair_lag:
            s = by_pair_lag[key]
            lines.append(
                f"- **Lag {lag}: YES** (z={s['z']:+.2f}, obs={s['observed']}, "
                f"exp={s['expected']:.1f}, {s['direction']})"
            )
        else:
            lines.append(f"- Lag {lag}: Not significant")
    lines.append("")

    # Q2: Does AB predict AF at lag 1?
    lines.append("### Q2: Does AB (bash) predict AF (failure) at lag 1?")
    for lag in [1, 2]:
        key = ("AB", "AF", lag)
        if key in by_pair_lag:
            s = by_pair_lag[key]
            lines.append(
                f"- **Lag {lag}: YES** (z={s['z']:+.2f}, obs={s['observed']}, "
                f"exp={s['expected']:.1f}, {s['direction']})"
            )
        else:
            lines.append(f"- Lag {lag}: Not significant")
    lines.append("")

    # Q3: Does UC suppress AB at lags 1-3?
    lines.append("### Q3: Does UC (correction) suppress AB (bash) at lags 1-3? (learned caution)")
    for lag in [1, 2, 3]:
        key = ("UC", "AB", lag)
        if key in by_pair_lag:
            s = by_pair_lag[key]
            word = "YES (suppressed)" if s["direction"] == "inhibitory" else "YES (increased!)"
            lines.append(
                f"- **Lag {lag}: {word}** (z={s['z']:+.2f}, obs={s['observed']}, "
                f"exp={s['expected']:.1f})"
            )
        else:
            lines.append(f"- Lag {lag}: Not significant")
    lines.append("")

    # Q4: Does AK predict AE at lag 1?
    lines.append("### Q4: Does AK (thinking) predict AE (edit) at lag 1? (think before editing)")
    for lag in [1, 2]:
        key = ("AK", "AE", lag)
        if key in by_pair_lag:
            s = by_pair_lag[key]
            lines.append(
                f"- **Lag {lag}: YES** (z={s['z']:+.2f}, obs={s['observed']}, "
                f"exp={s['expected']:.1f}, {s['direction']})"
            )
        else:
            lines.append(f"- Lag {lag}: Not significant")
    lines.append("")

    # Q5: Does AR predict AE without subsequent UC?
    lines.append("### Q5: Does AR (reading) predict AE (edit) at lag 1-2?")
    for lag in [1, 2, 3]:
        key = ("AR", "AE", lag)
        if key in by_pair_lag:
            s = by_pair_lag[key]
            lines.append(
                f"- **Lag {lag}: YES** (z={s['z']:+.2f}, obs={s['observed']}, "
                f"exp={s['expected']:.1f}, {s['direction']})"
            )
        else:
            lines.append(f"- Lag {lag}: Not significant")
    # Also check if AE predicts UC (error-prone editing)
    lines.append("\n  *Related: Does AE (edit) predict UC (correction)?*")
    for lag in [1, 2, 3]:
        key = ("AE", "UC", lag)
        if key in by_pair_lag:
            s = by_pair_lag[key]
            lines.append(
                f"  - **Lag {lag}: YES** (z={s['z']:+.2f}, obs={s['observed']}, "
                f"exp={s['expected']:.1f}, {s['direction']})"
            )
        else:
            lines.append(f"  - Lag {lag}: Not significant")
    lines.append("")

    return "\n".join(lines)


def find_top_patterns(all_significant):
    """Find the most interesting behavioral patterns across all lags."""
    lines = []
    lines.append("\n## Top Behavioral Patterns (by effect size)\n")

    # Sort by absolute z-score
    top = sorted(all_significant, key=lambda x: abs(x["z"]), reverse=True)[:25]

    lines.append("| Rank | Given | Target | Lag | z-score | Direction | Obs | Exp |")
    lines.append("|------|-------|--------|-----|---------|-----------|-----|-----|")
    for rank, s in enumerate(top, 1):
        lines.append(
            f"| {rank} | {s['given']} | {s['target']} | {s['lag']} | "
            f"{s['z']:+.2f} | {s['direction']} | {s['observed']} | {s['expected']:.1f} |"
        )

    return "\n".join(lines)


# ──────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("Lag Sequential Analysis — Bakeman & Quera method")
    print("=" * 60)

    # Collect session files
    all_files = glob.glob(SESSION_GLOB, recursive=True)
    print(f"\nFound {len(all_files)} JSONL session files")

    # Filter to reasonable-size sessions (> 10KB, < 50MB)
    sized_files = []
    for f in all_files:
        size = os.path.getsize(f)
        if 10_000 < size < 50_000_000:
            sized_files.append((f, size))

    print(f"After size filter (10KB-50MB): {len(sized_files)} files")

    # Sample sessions — stratified by project for diversity
    random.seed(42)
    by_project = defaultdict(list)
    for f, size in sized_files:
        # Extract project name from corpus path
        # e.g. .../projects/-Users-<operator>-projects-Sources/uuid/subagents/file.jsonl
        parts = f.split("/")
        project = "unknown"
        for i, p in enumerate(parts):
            if p == "projects" and i + 1 < len(parts):
                project = parts[i + 1]
                break
        by_project[project].append((f, size))

    sampled = []
    projects = list(by_project.keys())
    random.shuffle(projects)

    # Take up to 3 sessions per project, round-robin
    round_num = 0
    while len(sampled) < MAX_SESSIONS and projects:
        still_have = []
        for proj in projects:
            files = by_project[proj]
            if round_num < len(files):
                sampled.append(files[round_num])
                if len(sampled) >= MAX_SESSIONS:
                    break
            if round_num + 1 < len(files):
                still_have.append(proj)
        projects = still_have
        round_num += 1

    print(f"Sampled {len(sampled)} sessions from {len(by_project)} projects")

    # Code events
    print("\nCoding events...")
    all_sequences = []
    event_counts = Counter()
    sessions_used = 0
    sessions_skipped = 0

    for filepath, size in sampled:
        events = code_session(filepath)
        if len(events) >= MIN_EVENTS_PER_SESSION:
            all_sequences.append(events)
            for e in events:
                event_counts[e] += 1
            sessions_used += 1
        else:
            sessions_skipped += 1

    total_events = sum(event_counts.values())
    print(f"Sessions coded: {sessions_used} (skipped {sessions_skipped} with < {MIN_EVENTS_PER_SESSION} events)")
    print(f"Total events: {total_events}")
    print(f"\nEvent distribution:")
    for code in EVENT_CODES:
        count = event_counts[code]
        pct = (count / total_events * 100) if total_events > 0 else 0
        bar = "#" * int(pct * 2)
        print(f"  {code}: {count:>7d} ({pct:5.1f}%) {bar}")

    # Build matrices and compute significance
    print("\nBuilding transitional frequency matrices...")
    report_parts = []

    report_parts.append("---")
    report_parts.append('title: "Lag Sequential Analysis of Claude Code Sessions"')
    report_parts.append(f"created: 2026-03-19")
    report_parts.append('category: "meta-patterns"')
    report_parts.append("tags: [lag-sequential-analysis, behavioral-psychology, bakeman-quera, transition-matrices]")
    report_parts.append("symptoms:")
    report_parts.append('  - "Need to understand temporal dependencies between agent events"')
    report_parts.append('  - "Want to predict agent failures from preceding event patterns"')
    report_parts.append('severity: high')
    report_parts.append("source_sessions: []")
    report_parts.append("---\n")

    report_parts.append("# Lag Sequential Analysis of Claude Code Sessions\n")
    report_parts.append("## Method\n")
    report_parts.append("Applied Bakeman & Quera's lag sequential analysis to Claude Code session data.")
    report_parts.append(f"- **Sessions analyzed**: {sessions_used} (from {len(by_project)} projects)")
    report_parts.append(f"- **Total coded events**: {total_events}")
    report_parts.append(f"- **Lags tested**: 1 through {MAX_LAGS}")
    report_parts.append(f"- **Significance threshold**: |z| > {Z_CRITICAL} (p < {ALPHA}), minimum 5 observations\n")

    report_parts.append("### Event Codes\n")
    report_parts.append("| Code | Meaning | Count | % |")
    report_parts.append("|------|---------|-------|---|")
    for code in EVENT_CODES:
        count = event_counts[code]
        pct = (count / total_events * 100) if total_events > 0 else 0
        labels = {
            "UR": "User request", "UC": "User correction", "UA": "User approval",
            "AR": "Agent reads", "AE": "Agent edits", "AB": "Agent bash",
            "AT": "Agent text", "AK": "Agent thinks", "AF": "Agent fails",
        }
        report_parts.append(f"| {code} | {labels[code]} | {count} | {pct:.1f}% |")

    all_significant = []

    for lag in range(1, MAX_LAGS + 1):
        print(f"\n--- Lag {lag} ---")
        matrix = build_frequency_matrix(all_sequences, lag)
        z_scores, obs, expected = compute_significance(matrix)

        report_parts.append(f"\n## Lag {lag} Analysis\n")
        report_parts.append(format_matrix(obs, f"Observed Frequencies (Lag {lag})"))
        report_parts.append(format_matrix(z_scores, f"Z-Scores (Lag {lag})", decimals=2))

        sig_text, sig_list = format_significant_cells(z_scores, obs, expected, lag)
        report_parts.append(sig_text)
        all_significant.extend(sig_list)

        # Print summary
        n_sig = len(sig_list)
        n_excit = sum(1 for s in sig_list if s["direction"] == "excitatory")
        n_inhib = sum(1 for s in sig_list if s["direction"] == "inhibitory")
        print(f"  Significant cells: {n_sig} ({n_excit} excitatory, {n_inhib} inhibitory)")
        if sig_list:
            top3 = sorted(sig_list, key=lambda x: abs(x["z"]), reverse=True)[:3]
            for s in top3:
                print(f"    {s['given']}->{s['target']}: z={s['z']:+.2f} ({s['direction']})")

    # Key questions
    report_parts.append(answer_key_questions(all_significant))

    # Top patterns
    report_parts.append(find_top_patterns(all_significant))

    # Interpretation
    report_parts.append("\n## Interpretation\n")

    # Build lookup for easy access
    sig_lookup = {}
    for s in all_significant:
        key = (s["given"], s["target"], s["lag"])
        sig_lookup[key] = s

    interpretations = []

    # 1. Behavioral perseveration (self-transitions)
    self_trans = [s for s in all_significant
                 if s["given"] == s["target"] and s["direction"] == "excitatory"]
    if self_trans:
        codes = sorted(set(s["given"] for s in self_trans))
        top_self = sorted(self_trans, key=lambda x: x["z"], reverse=True)[:3]
        top_desc = ", ".join(f"{s['given']}->{s['target']} (z={s['z']:+.1f}, lag {s['lag']})" for s in top_self)
        interpretations.append(
            f"**1. Behavioral perseveration is the dominant pattern.** "
            f"Events {', '.join(codes)} all show highly significant self-transitions "
            f"(same event following itself). The strongest: {top_desc}. "
            f"This means the agent works in 'runs' -- reading multiple files in sequence, "
            f"then writing multiple edits, then running multiple bash commands. "
            f"The event stream is not interleaved; it is chunked by action type."
        )

    # 2. Think-then-speak, not think-then-edit
    ak_ae_lag1 = sig_lookup.get(("AK", "AE", 1))
    ak_at_lag1 = sig_lookup.get(("AK", "AT", 1))
    if ak_ae_lag1 or ak_at_lag1:
        parts = []
        if ak_at_lag1 and ak_at_lag1["direction"] == "excitatory":
            parts.append(f"AK->AT is excitatory at lag 1 (z={ak_at_lag1['z']:+.1f})")
        if ak_ae_lag1 and ak_ae_lag1["direction"] == "inhibitory":
            parts.append(f"AK->AE is inhibitory at lag 1 (z={ak_ae_lag1['z']:+.1f})")
        if parts:
            interpretations.append(
                f"**2. Thinking predicts text output, NOT immediate editing.** "
                f"{'; '.join(parts)}. "
                f"The agent does not think then edit -- it thinks then *explains*. "
                f"Editing comes later, after text narration of intent. This matches the "
                f"'narrate-then-act' pattern observed in agent behavior studies."
            )

    # 3. Read-edit pipeline
    read_edit = [s for s in all_significant
                 if s["given"] == "AR" and s["target"] == "AE" and s["direction"] == "excitatory"]
    if read_edit:
        lags = sorted(s["lag"] for s in read_edit)
        z_vals = [f"lag {s['lag']}: z={s['z']:+.1f}" for s in sorted(read_edit, key=lambda x: x["lag"])]
        interpretations.append(
            f"**3. Reading reliably predicts editing.** "
            f"AR->AE is excitatory at lags {', '.join(str(l) for l in lags)} "
            f"({'; '.join(z_vals)}). "
            f"This is the healthiest pattern in the data: the agent reads context "
            f"before modifying code. The effect persists across multiple lags, "
            f"suggesting reads done 2-3 steps earlier still influence subsequent edits."
        )

    # 4. Bash-failure link
    bash_fail = sig_lookup.get(("AB", "AF", 1))
    fail_bash = sig_lookup.get(("AF", "AB", 1))
    if bash_fail:
        parts = [f"AB->AF at lag 1: z={bash_fail['z']:+.1f} (obs={bash_fail['observed']}, exp={bash_fail['expected']:.0f})"]
        if fail_bash and fail_bash["direction"] == "excitatory":
            parts.append(f"AF->AB at lag 1: z={fail_bash['z']:+.1f}")
        interpretations.append(
            f"**4. Bash is the riskiest tool call.** "
            f"{'; '.join(parts)}. "
            f"Bash commands are followed by failures at ~3x the expected rate. "
            f"{'The AF->AB excitatory link suggests retry loops: the agent fails, then tries another bash command. ' if fail_bash and fail_bash['direction'] == 'excitatory' else ''}"
            f"This is consistent with bash being the only tool where the agent "
            f"must compose arbitrary shell commands with unpredictable environments."
        )

    # 5. Failure cascades
    af_af = [s for s in all_significant
             if s["given"] == "AF" and s["target"] == "AF" and s["direction"] == "excitatory"]
    if af_af:
        top_ff = max(af_af, key=lambda x: x["z"])
        interpretations.append(
            f"**5. Failures cluster (cascade effect).** "
            f"AF->AF self-transition is excitatory (z={top_ff['z']:+.1f} at lag {top_ff['lag']}). "
            f"When the agent fails once, it is significantly more likely to fail again. "
            f"This may indicate the agent retries the same failing approach, or that "
            f"environmental conditions causing one failure also cause the next."
        )

    # 6. User request triggers thinking
    ur_ak = sig_lookup.get(("UR", "AK", 1))
    if ur_ak and ur_ak["direction"] == "excitatory":
        interpretations.append(
            f"**6. User requests trigger thinking blocks.** "
            f"UR->AK at lag 1: z={ur_ak['z']:+.1f} (obs={ur_ak['observed']}, exp={ur_ak['expected']:.0f}). "
            f"This is expected and healthy: the agent thinks before acting on a new request. "
            f"The very high z-score confirms this is near-deterministic behavior."
        )

    # 7. Correction effects (if we have enough data)
    correction_inhib = [s for s in all_significant
                        if s["given"] == "UC" and s["direction"] == "inhibitory"]
    correction_excit = [s for s in all_significant
                        if s["given"] == "UC" and s["direction"] == "excitatory"]
    if correction_inhib or correction_excit:
        parts = []
        if correction_inhib:
            suppressed = sorted(set(s["target"] for s in correction_inhib))
            parts.append(f"suppresses {', '.join(suppressed)}")
        if correction_excit:
            boosted = sorted(set(s["target"] for s in correction_excit))
            parts.append(f"increases {', '.join(boosted)}")
        interpretations.append(
            f"**7. User corrections alter agent behavior.** "
            f"UC {'; '.join(parts)}. "
            f"Note: with only {event_counts.get('UC', 0)} UC events in the corpus, "
            f"these effects should be interpreted with caution. "
            f"The low UC rate ({event_counts.get('UC', 0)/total_events*100:.1f}%) itself "
            f"is a finding: users rarely correct the agent with short reactive signals."
        )

    # 8. Cross-type inhibition (AT suppresses non-AT at lag 1)
    at_inhib = [s for s in all_significant
                if s["given"] == "AT" and s["target"] != "AT"
                and s["direction"] == "inhibitory" and s["lag"] == 1]
    if len(at_inhib) >= 3:
        suppressed = sorted(set(s["target"] for s in at_inhib))
        interpretations.append(
            f"**8. Text output suppresses tool use at lag 1.** "
            f"AT is inhibitory toward {', '.join(suppressed)} at lag 1. "
            f"When the agent is producing text, it is significantly less likely to "
            f"immediately switch to tool use. The text 'run' must complete before "
            f"a tool-use 'run' can begin. This reinforces the chunked/bursty execution model."
        )

    for interp in interpretations:
        report_parts.append(interp + "\n")

    # Write report
    report = "\n".join(report_parts)

    output_path = os.environ.get("OUTPUT_DIR", os.environ.get("MIDDENS_OUTPUT", "experiments/")) + "/015-lag-sequential-analysis.md"
    with open(output_path, 'w') as f:
        f.write(report)

    print(f"\n{'=' * 60}")
    print(f"Report written to: {output_path}")
    print(f"Total significant transitions found: {len(all_significant)}")
    print(f"{'=' * 60}")

    return all_significant, all_sequences, event_counts


if __name__ == "__main__":
    all_significant, all_sequences, event_counts = main()
