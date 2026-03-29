#!/usr/bin/env python3
"""
Burstiness & Hawkes Process Analysis of Claude Code Sessions

Analyzes temporal dynamics of corrections and errors using:
1. Burstiness coefficient (Barabási)
2. Memory coefficient (autocorrelation of inter-event times)
3. Simplified Hawkes process (excitation/inhibition kernels)
4. Correction cascade detection

Source: Claude Code session JSONL files
"""

import json
import os
import glob
import re
import sys
import math
import random
from collections import defaultdict, Counter
from pathlib import Path

import numpy as np

# ── Configuration ──────────────────────────────────────────────────────────

SESSION_GLOB = os.environ.get("SESSION_GLOB", os.path.join(os.environ.get("MIDDENS_CORPUS", "corpus/"), "**/*.jsonl"))
OUTPUT_DIR = os.environ.get("OUTPUT_DIR", os.environ.get("MIDDENS_OUTPUT", "experiments/"))
FIGURES_DIR = os.path.join(OUTPUT_DIR, "figures")
MAX_SESSIONS = 500  # increased for full corpus
MIN_EVENTS_PER_SESSION = 20
CASCADE_WINDOW = 10  # turns
CASCADE_MIN_LENGTH = 3

# Correction detection patterns (from prior work in experiment 013)
CORRECTION_PATTERNS = [
    r"^no[,.\s!]",
    r"^wrong",
    r"^actually[,\s]",
    r"^why did you",
    r"^don'?t\s",
    r"^stop\b(?! hook)",    # "stop" but not "stop hook feedback"
    r"^revert",
    r"^undo",
    r"^try again",
    r"^that'?s not",
    r"^that is not",
    r"^not what i",
    r"^i said",
    r"^i meant",
    r"^i asked",
    r"^wait[,.\s]",
    r"^hold on",
    r"^nope",
    r"^incorrect",
    r"^fix\s",
    r"^instead[,\s]",
    r"^you (should|need|forgot|missed|broke|didn)",
    r"^please (don|stop|revert|undo|fix)",
    r"^this (is wrong|isn't|doesn't|broke|failed)",
    r"^it (should|shouldn't|doesn't|didn't|broke|failed)",
    r"^that (broke|failed|isn't right|is incorrect)",
    r"\bwrong\b.*\bshould\b",
    r"^no need to\b",
]
CORRECTION_RE = re.compile("|".join(CORRECTION_PATTERNS), re.IGNORECASE)

# Patterns that look like corrections but are actually system/hook messages
CORRECTION_EXCLUSIONS = [
    r"stop hook",
    r"^#\s",                 # Markdown headings (task descriptions)
    r"^```",                 # Code blocks
    r"deepen plan",
    r"power enhancement",
    r"this session is being continued",
    r"^you are \w+, an",     # Agent role prompts
]
CORRECTION_EXCLUSION_RE = re.compile("|".join(CORRECTION_EXCLUSIONS), re.IGNORECASE)

os.makedirs(FIGURES_DIR, exist_ok=True)


# ── Data Loading ───────────────────────────────────────────────────────────

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
    # Filter out tool results and system messages
    if text.startswith("[tool_result]") or text.startswith("[Request"):
        return False
    if text.startswith("<"):  # XML/system messages
        return False
    # Check exclusions first
    if CORRECTION_EXCLUSION_RE.search(text):
        return False
    return bool(CORRECTION_RE.search(text))


def extract_tool_name(msg):
    """Extract tool name from an assistant message's tool_use blocks."""
    content = msg.get("message", {}).get("content", [])
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_use":
                return block.get("name", "unknown")
    return None


def has_thinking(msg):
    """Check if assistant message has a thinking block."""
    content = msg.get("message", {}).get("content", [])
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") == "thinking":
                return True
    return False


def is_tool_result_message(msg):
    """Check if a user message is purely a tool_result (not human-authored text)."""
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
                    # Filter out system-generated text
                    if text and not text.startswith("<") and not text.startswith("["):
                        has_human_text = True
        # If it has tool results and no human text, it's a tool result msg
        if has_tool_result and not has_human_text:
            return True
    return False


def detect_tool_failure(msg):
    """Check if a user message contains a tool_result with is_error=True only."""
    content = msg.get("message", {}).get("content", "")
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_result":
                # Only use the explicit is_error flag, not string matching
                if block.get("is_error"):
                    return True
    return False


def is_automated_session(session_path):
    """
    Check if a session is an automated agent loop (not human-agent interaction).
    These sessions have very few genuine human messages and are dominated by
    automated prompts like 'You are Boucle, an autonomous agent...'
    """
    with open(session_path) as f:
        for line in f:
            try:
                msg = json.loads(line)
                if msg.get("type") == "user":
                    text = extract_user_text(msg)
                    if text and "autonomous agent running in a loop" in text.lower():
                        return True
                    if text and "you are boucle" in text.lower():
                        return True
                    break  # Only check first user message
            except:
                continue
    return False


def code_events(session_path):
    """
    Load a session and produce a sequence of coded events with timestamps.

    Event types:
    - correction: user correction (genuine human text matching patterns)
    - tool_failure: tool result with explicit is_error flag
    - edit: Edit/Write tool use
    - bash: Bash tool use
    - read: Read/Glob/Grep tool use
    - thinking: assistant message with thinking block
    - user_request: user message that is not a correction
    """
    events = []

    with open(session_path) as f:
        for line in f:
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue

            ts = msg.get("timestamp")
            if not ts:
                continue

            msg_type = msg.get("type")

            if msg_type == "user":
                # First: is this purely a tool_result message? (not human text)
                if is_tool_result_message(msg):
                    # Check for tool failure (is_error flag only)
                    if detect_tool_failure(msg):
                        events.append(("tool_failure", ts, msg))
                    # Otherwise skip -- tool results are agent-internal, not events
                    continue

                text = extract_user_text(msg)
                if not text:
                    continue

                # Skip system/command messages
                if text.startswith("[") or text.startswith("<"):
                    continue

                # Skip very short messages that are just confirmations
                if text.lower().strip() in ("y", "yes", "ok", "okay", "continue", "go", "keep going", "proceed"):
                    events.append(("user_request", ts, msg))
                    continue

                # Skip system/hook messages that appear as user text
                if any(p in text.lower() for p in [
                    "stop hook feedback", "security classifier",
                    "autonomous agent running in a loop",
                    "task-notification", "security notice",
                ]):
                    continue

                # Deduplicate: skip if same text as previous event
                if events and events[-1][0] in ("correction", "user_request"):
                    prev_msg = events[-1][2]
                    prev_text = extract_user_text(prev_msg) if isinstance(prev_msg, dict) else ""
                    if prev_text and text == prev_text:
                        continue  # Skip duplicate

                if is_correction(text):
                    events.append(("correction", ts, msg))
                else:
                    events.append(("user_request", ts, msg))

            elif msg_type == "assistant":
                # Check for thinking
                if has_thinking(msg):
                    events.append(("thinking", ts, msg))

                # Collect ALL tool_use blocks from the message
                content = msg.get("message", {}).get("content", [])
                if isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "tool_use":
                            name = block.get("name", "")
                            if name in ("Edit", "Write"):
                                events.append(("edit", ts, name))
                            elif name == "Bash":
                                events.append(("bash", ts, name))
                            elif name in ("Read", "Glob", "Grep"):
                                events.append(("read", ts, name))

    return events


def load_sessions(max_n=MAX_SESSIONS):
    """Load and code sessions, filtering automated loops and balancing projects."""
    # Use os.walk with followlinks=True to traverse symlinked directories
    corpus_base = SESSION_GLOB.rsplit("/**", 1)[0]
    files = []
    for root, dirs, fnames in os.walk(corpus_base, followlinks=True):
        for fn in fnames:
            if fn.endswith(".jsonl"):
                files.append(os.path.join(root, fn))
    random.seed(42)
    random.shuffle(files)

    # Group by project for balanced sampling
    project_files = defaultdict(list)
    for fpath in files:
        # Extract project name from corpus path
        parts = fpath.split("/")
        project = "unknown"
        for i, p in enumerate(parts):
            if p == "projects" and i + 1 < len(parts):
                project = parts[i + 1]
                break
        project_files[project].append(fpath)

    sessions = {}
    projects = {}
    skipped_automated = 0
    skipped_small = 0

    # Round-robin across projects for balance
    max_per_project = max(5, max_n // max(1, len(project_files)))
    project_counts = Counter()

    # Sort projects by file count (ascending) so smaller projects get priority
    ordered_projects = sorted(project_files.keys(), key=lambda p: len(project_files[p]))

    # Multiple passes to fill up to max_n
    for pass_num in range(10):
        if len(sessions) >= max_n:
            break
        for project in ordered_projects:
            if len(sessions) >= max_n:
                break
            pfiles = project_files[project]
            # Get next unprocessed file for this project
            start_idx = project_counts[project]
            for fpath in pfiles[start_idx:start_idx + 3]:
                if len(sessions) >= max_n:
                    break

                project_counts[project] += 1

                try:
                    if is_automated_session(fpath):
                        skipped_automated += 1
                        continue
                    events = code_events(fpath)
                except Exception:
                    continue

                if len(events) < MIN_EVENTS_PER_SESSION:
                    skipped_small += 1
                    continue

                # Must have at least some human messages
                human_events = sum(1 for e in events if e[0] in ("correction", "user_request"))
                if human_events < 3:
                    skipped_small += 1
                    continue

                sid = os.path.basename(fpath).replace(".jsonl", "")
                sessions[sid] = events
                projects[sid] = project

    print(f"  Loaded: {len(sessions)} sessions")
    print(f"  Skipped (automated): {skipped_automated}")
    print(f"  Skipped (too small/few humans): {skipped_small}")
    return sessions, projects


# ── Analysis 1: Burstiness Coefficient ────────────────────────────────────

def compute_burstiness(inter_event_times):
    """
    Compute Barabási's burstiness coefficient.
    B = (sigma - mu) / (sigma + mu)
    B = 1: maximally bursty
    B = 0: Poisson (random)
    B = -1: periodic
    """
    if len(inter_event_times) < 2:
        return None

    arr = np.array(inter_event_times, dtype=float)
    mu = np.mean(arr)
    sigma = np.std(arr, ddof=1)

    if sigma + mu == 0:
        return 0.0

    return (sigma - mu) / (sigma + mu)


def get_event_positions(events, event_type):
    """Get positions (turn indices) of a specific event type."""
    return [i for i, (etype, ts, _) in enumerate(events) if etype == event_type]


def inter_event_times_from_positions(positions):
    """Compute inter-event times from position list."""
    if len(positions) < 2:
        return []
    return [positions[i+1] - positions[i] for i in range(len(positions) - 1)]


def analyze_burstiness(sessions, projects):
    """Compute burstiness for corrections across sessions."""
    print("\n" + "="*70)
    print("ANALYSIS 1: BURSTINESS COEFFICIENT (BARABÁSI)")
    print("="*70)

    results = {}
    event_types = ["correction", "tool_failure", "edit", "bash", "read"]

    # Per event type
    for etype in event_types:
        burstiness_values = []
        iet_all = []

        for sid, events in sessions.items():
            positions = get_event_positions(events, etype)
            iets = inter_event_times_from_positions(positions)
            if len(iets) >= 3:
                b = compute_burstiness(iets)
                if b is not None:
                    burstiness_values.append((sid, b, len(iets)))
                    iet_all.extend(iets)

        if burstiness_values:
            bs = [b for _, b, _ in burstiness_values]
            results[etype] = {
                "mean_B": np.mean(bs),
                "median_B": np.median(bs),
                "std_B": np.std(bs),
                "n_sessions": len(bs),
                "values": burstiness_values,
                "all_iets": iet_all,
            }
            print(f"\n  {etype.upper()}")
            print(f"    Sessions with >=3 inter-event times: {len(bs)}")
            print(f"    Mean B = {np.mean(bs):.3f}")
            print(f"    Median B = {np.median(bs):.3f}")
            print(f"    Std B = {np.std(bs):.3f}")
            print(f"    Range: [{min(bs):.3f}, {max(bs):.3f}]")
            print(f"    Mean IET = {np.mean(iet_all):.1f} events")
            print(f"    Std IET = {np.std(iet_all):.1f} events")
        else:
            print(f"\n  {etype.upper()}: insufficient data")

    # Per-project burstiness for corrections
    project_burstiness = defaultdict(list)
    if "correction" in results:
        for sid, b, n in results["correction"]["values"]:
            project_burstiness[projects[sid]].append(b)

    print("\n  CORRECTION BURSTINESS BY PROJECT:")
    for proj, bs in sorted(project_burstiness.items(), key=lambda x: -np.mean(x[1])):
        if len(bs) >= 2:
            print(f"    {proj}: mean B={np.mean(bs):.3f} (n={len(bs)})")

    return results


# ── Analysis 2: Memory Coefficient ────────────────────────────────────────

def compute_memory_coefficient(inter_event_times):
    """
    Compute memory coefficient as Pearson correlation between
    consecutive inter-event times.
    M > 0: long waits predict long waits (clustering)
    M < 0: long waits predict short waits (alternating)
    M ≈ 0: no memory (Poisson-like)
    """
    if len(inter_event_times) < 4:
        return None

    arr = np.array(inter_event_times, dtype=float)
    t1 = arr[:-1]
    t2 = arr[1:]

    # Pearson correlation
    if np.std(t1) == 0 or np.std(t2) == 0:
        return 0.0

    return np.corrcoef(t1, t2)[0, 1]


def analyze_memory(sessions, results_burstiness):
    """Compute memory coefficient for correction inter-event times."""
    print("\n" + "="*70)
    print("ANALYSIS 2: MEMORY COEFFICIENT")
    print("="*70)

    results = {}
    event_types = ["correction", "tool_failure", "edit", "bash", "read"]

    for etype in event_types:
        memory_values = []

        for sid, events in sessions.items():
            positions = get_event_positions(events, etype)
            iets = inter_event_times_from_positions(positions)
            m = compute_memory_coefficient(iets)
            if m is not None:
                memory_values.append((sid, m, len(iets)))

        if memory_values:
            ms = [m for _, m, _ in memory_values]
            results[etype] = {
                "mean_M": np.mean(ms),
                "median_M": np.median(ms),
                "std_M": np.std(ms),
                "n_sessions": len(ms),
                "values": memory_values,
            }
            print(f"\n  {etype.upper()}")
            print(f"    Sessions with >=4 IETs: {len(ms)}")
            print(f"    Mean M = {np.mean(ms):.3f}")
            print(f"    Median M = {np.median(ms):.3f}")
            print(f"    Std M = {np.std(ms):.3f}")

            # Significance: how many are significantly positive/negative?
            n_pos = sum(1 for m in ms if m > 0.2)
            n_neg = sum(1 for m in ms if m < -0.2)
            n_near_zero = len(ms) - n_pos - n_neg
            print(f"    M > 0.2 (positive memory): {n_pos} ({100*n_pos/len(ms):.0f}%)")
            print(f"    M < -0.2 (negative memory): {n_neg} ({100*n_neg/len(ms):.0f}%)")
            print(f"    |M| <= 0.2 (no memory): {n_near_zero} ({100*n_near_zero/len(ms):.0f}%)")
        else:
            print(f"\n  {etype.upper()}: insufficient data")

    return results


# ── Analysis 3: Hawkes Process (Simplified) ────────────────────────────────

def analyze_hawkes(sessions):
    """
    Simplified Hawkes process analysis.

    For each pair (A, B), measure rate of B in windows after A vs baseline.
    Excitation ratio > 1 means A excites B.
    Excitation ratio < 1 means A inhibits B.
    """
    print("\n" + "="*70)
    print("ANALYSIS 3: SIMPLIFIED HAWKES PROCESS (EXCITATION/INHIBITION)")
    print("="*70)

    event_types = ["correction", "tool_failure", "edit", "bash", "read", "thinking"]
    windows = [3, 5, 10]  # Look-ahead windows (in events)

    results = {}

    for window in windows:
        print(f"\n  ── Window = {window} events ──")
        excitation_matrix = {}

        for trigger in event_types:
            for response in event_types:
                # Count occurrences of response in window after trigger
                triggered_count = 0
                triggered_windows = 0

                # Baseline: count occurrences of response in random windows
                baseline_count = 0
                baseline_windows = 0

                for sid, events in sessions.items():
                    event_codes = [e[0] for e in events]
                    n = len(event_codes)

                    for i, code in enumerate(event_codes):
                        if code == trigger:
                            # Count response in window after trigger
                            w = event_codes[i+1:i+1+window]
                            triggered_count += w.count(response)
                            triggered_windows += 1

                        # Baseline: every position
                        w = event_codes[i+1:i+1+window]
                        if len(w) == window:
                            baseline_count += w.count(response)
                            baseline_windows += 1

                if triggered_windows > 5 and baseline_windows > 0:
                    triggered_rate = triggered_count / triggered_windows
                    baseline_rate = baseline_count / baseline_windows

                    if baseline_rate > 0:
                        excitation = triggered_rate / baseline_rate
                    else:
                        excitation = float('inf') if triggered_count > 0 else 1.0

                    excitation_matrix[(trigger, response)] = {
                        "excitation_ratio": excitation,
                        "triggered_rate": triggered_rate,
                        "baseline_rate": baseline_rate,
                        "triggered_windows": triggered_windows,
                    }

        results[window] = excitation_matrix

        # Print key findings
        print(f"\n    Key excitation/inhibition patterns (window={window}):")

        # Focus on the key questions
        key_pairs = [
            ("correction", "correction", "Correction → Correction (cascade?)"),
            ("correction", "edit", "Correction → Edit (triggers fix?)"),
            ("correction", "read", "Correction → Read (re-examination?)"),
            ("correction", "bash", "Correction → Bash"),
            ("correction", "thinking", "Correction → Thinking"),
            ("tool_failure", "correction", "Tool failure → Correction (error prop?)"),
            ("tool_failure", "tool_failure", "Tool failure → Tool failure (cascade?)"),
            ("thinking", "correction", "Thinking → Correction (prevention?)"),
            ("thinking", "tool_failure", "Thinking → Tool failure"),
            ("edit", "correction", "Edit → Correction"),
            ("edit", "tool_failure", "Edit → Tool failure"),
        ]

        for trigger, response, label in key_pairs:
            key = (trigger, response)
            if key in excitation_matrix:
                r = excitation_matrix[key]
                ratio = r["excitation_ratio"]
                symbol = "↑" if ratio > 1.1 else ("↓" if ratio < 0.9 else "≈")
                print(f"      {symbol} {label}: {ratio:.2f}x (n={r['triggered_windows']})")

    return results


# ── Analysis 4: Correction Cascades ────────────────────────────────────────

def analyze_cascades(sessions, projects):
    """
    Find sequences of 3+ corrections within 10 turns.
    Analyze triggers and characteristics.
    """
    print("\n" + "="*70)
    print("ANALYSIS 4: CORRECTION CASCADES")
    print("="*70)

    all_cascades = []
    sessions_with_cascades = set()

    for sid, events in sessions.items():
        event_codes = [e[0] for e in events]
        n = len(event_codes)

        # Find correction positions
        corr_positions = [i for i, c in enumerate(event_codes) if c == "correction"]

        if len(corr_positions) < CASCADE_MIN_LENGTH:
            continue

        # Find cascades: groups of corrections within CASCADE_WINDOW turns
        i = 0
        while i < len(corr_positions):
            cascade = [corr_positions[i]]
            j = i + 1
            while j < len(corr_positions):
                if corr_positions[j] - cascade[-1] <= CASCADE_WINDOW:
                    cascade.append(corr_positions[j])
                    j += 1
                else:
                    break

            if len(cascade) >= CASCADE_MIN_LENGTH:
                # Analyze trigger: what happened in the 5 events before the cascade?
                start = cascade[0]
                pre_events = event_codes[max(0, start-5):start]

                # Get correction texts
                corr_texts = []
                for pos in cascade:
                    msg = events[pos][2]
                    text = extract_user_text(msg) if isinstance(msg, dict) else ""
                    corr_texts.append(text[:100])

                # Events between corrections in the cascade
                inter_events = []
                for k in range(len(cascade) - 1):
                    inter = event_codes[cascade[k]+1:cascade[k+1]]
                    inter_events.append(inter)

                cascade_info = {
                    "session": sid,
                    "project": projects[sid],
                    "length": len(cascade),
                    "span": cascade[-1] - cascade[0],
                    "positions": cascade,
                    "pre_events": pre_events,
                    "correction_texts": corr_texts,
                    "inter_events": inter_events,
                }
                all_cascades.append(cascade_info)
                sessions_with_cascades.add(sid)

            i = j

    print(f"\n  Total cascades found: {len(all_cascades)}")
    print(f"  Sessions with cascades: {len(sessions_with_cascades)} / {len(sessions)}")

    if all_cascades:
        lengths = [c["length"] for c in all_cascades]
        spans = [c["span"] for c in all_cascades]
        print(f"  Cascade lengths: mean={np.mean(lengths):.1f}, max={max(lengths)}")
        print(f"  Cascade spans: mean={np.mean(spans):.1f} events, max={max(spans)} events")

        # Trigger analysis
        print("\n  Trigger analysis (events in 5 positions before cascade):")
        pre_counts = Counter()
        for c in all_cascades:
            for e in c["pre_events"]:
                pre_counts[e] += 1
        total_pre = sum(pre_counts.values())
        if total_pre > 0:
            for event, count in pre_counts.most_common():
                print(f"    {event}: {count} ({100*count/total_pre:.0f}%)")

        # Inter-cascade events
        print("\n  Events between corrections within cascades:")
        inter_counts = Counter()
        for c in all_cascades:
            for inter in c["inter_events"]:
                for e in inter:
                    inter_counts[e] += 1
        total_inter = sum(inter_counts.values())
        if total_inter > 0:
            for event, count in inter_counts.most_common():
                print(f"    {event}: {count} ({100*count/total_inter:.0f}%)")

        # By project
        print("\n  Cascades by project:")
        proj_cascades = defaultdict(list)
        for c in all_cascades:
            proj_cascades[c["project"]].append(c)
        for proj, cs in sorted(proj_cascades.items(), key=lambda x: -len(x[1])):
            print(f"    {proj}: {len(cs)} cascades")

        # Example cascades
        print("\n  Example cascades:")
        for c in all_cascades[:5]:
            print(f"\n    Session: {c['session'][:12]}... ({c['project']})")
            print(f"    Length: {c['length']} corrections over {c['span']} events")
            print(f"    Pre-events: {c['pre_events']}")
            for i, text in enumerate(c["correction_texts"]):
                print(f"    Correction {i+1}: \"{text}\"")

    return all_cascades


# ── Temporal Decay Analysis ───────────────────────────────────────────────

def analyze_temporal_decay(sessions):
    """
    Analyze the excitation kernel shape: how does the rate of corrections
    decay with distance from a triggering event?
    """
    print("\n" + "="*70)
    print("ANALYSIS 5: TEMPORAL DECAY OF EXCITATION")
    print("="*70)

    triggers = ["correction", "tool_failure"]
    response = "correction"
    max_lag = 20

    results = {}

    for trigger in triggers:
        lag_counts = np.zeros(max_lag)
        lag_opportunities = np.zeros(max_lag)

        for sid, events in sessions.items():
            event_codes = [e[0] for e in events]
            n = len(event_codes)

            for i, code in enumerate(event_codes):
                if code == trigger:
                    for lag in range(1, max_lag + 1):
                        if i + lag < n:
                            lag_opportunities[lag - 1] += 1
                            if event_codes[i + lag] == response:
                                lag_counts[lag - 1] += 1

        # Baseline rate
        total_events = sum(len(events) for events in sessions.values())
        total_corrections = sum(
            sum(1 for e in events if e[0] == response)
            for events in sessions.values()
        )
        baseline_rate = total_corrections / total_events if total_events > 0 else 0

        rates = np.zeros(max_lag)
        for lag in range(max_lag):
            if lag_opportunities[lag] > 0:
                rates[lag] = lag_counts[lag] / lag_opportunities[lag]

        excitation_ratios = rates / baseline_rate if baseline_rate > 0 else rates

        results[trigger] = {
            "rates": rates,
            "baseline": baseline_rate,
            "excitation_ratios": excitation_ratios,
            "counts": lag_counts,
            "opportunities": lag_opportunities,
        }

        print(f"\n  {trigger.upper()} → {response.upper()} decay:")
        print(f"    Baseline correction rate: {baseline_rate:.4f}")
        print(f"    Lag | Rate    | Excitation | Count")
        print(f"    ----|---------|------------|------")
        for lag in range(min(15, max_lag)):
            r = rates[lag]
            ex = excitation_ratios[lag]
            c = int(lag_counts[lag])
            print(f"    {lag+1:3d} | {r:.4f} | {ex:.2f}x      | {c}")

    return results


# ── Plotting ──────────────────────────────────────────────────────────────

def create_plots(burstiness_results, memory_results, hawkes_results,
                 decay_results, cascades):
    """Generate analysis plots using matplotlib."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.patches as mpatches
    except ImportError:
        print("\nWARNING: matplotlib not available, skipping plots")
        return

    # ── Plot 1: Burstiness distribution ──
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))

    event_types = ["correction", "tool_failure", "edit", "bash", "read"]
    colors = ["#e74c3c", "#e67e22", "#3498db", "#2ecc71", "#9b59b6"]

    # Box plot
    ax = axes[0]
    data_for_box = []
    labels_for_box = []
    for etype, color in zip(event_types, colors):
        if etype in burstiness_results:
            vals = [b for _, b, _ in burstiness_results[etype]["values"]]
            data_for_box.append(vals)
            labels_for_box.append(etype)

    if data_for_box:
        bp = ax.boxplot(data_for_box, tick_labels=labels_for_box, patch_artist=True)
        for patch, color in zip(bp["boxes"], colors[:len(data_for_box)]):
            patch.set_facecolor(color)
            patch.set_alpha(0.5)
        ax.axhline(y=0, color="gray", linestyle="--", alpha=0.5, label="Poisson (random)")
        ax.axhline(y=1, color="red", linestyle=":", alpha=0.3, label="Max bursty")
        ax.axhline(y=-1, color="blue", linestyle=":", alpha=0.3, label="Periodic")
        ax.set_ylabel("Burstiness Coefficient B")
        ax.set_title("Burstiness by Event Type")
        ax.legend(fontsize=8)
        ax.set_ylim(-1.1, 1.1)

    # IET distribution for corrections
    ax = axes[1]
    if "correction" in burstiness_results:
        iets = burstiness_results["correction"]["all_iets"]
        ax.hist(iets, bins=30, color="#e74c3c", alpha=0.7, edgecolor="black")
        ax.set_xlabel("Inter-Correction Time (events)")
        ax.set_ylabel("Frequency")
        ax.set_title("Inter-Correction Time Distribution")
        ax.axvline(np.mean(iets), color="red", linestyle="--", label=f"Mean={np.mean(iets):.1f}")
        ax.axvline(np.median(iets), color="blue", linestyle="--", label=f"Median={np.median(iets):.1f}")
        ax.legend()

    plt.tight_layout()
    plt.savefig(os.path.join(FIGURES_DIR, "burstiness_distribution.png"), dpi=150)
    plt.close()
    print(f"  Saved: {FIGURES_DIR}/burstiness_distribution.png")

    # ── Plot 2: Memory scatter ──
    fig, ax = plt.subplots(figsize=(8, 6))
    for etype, color in zip(event_types, colors):
        if etype in burstiness_results and etype in memory_results:
            bs = [b for _, b, _ in burstiness_results[etype]["values"]]
            ms = [m for _, m, _ in memory_results[etype]["values"]]
            # Match by session
            b_dict = {sid: b for sid, b, _ in burstiness_results[etype]["values"]}
            m_dict = {sid: m for sid, m, _ in memory_results[etype]["values"]}
            common = set(b_dict.keys()) & set(m_dict.keys())
            if common:
                bvals = [b_dict[s] for s in common]
                mvals = [m_dict[s] for s in common]
                ax.scatter(bvals, mvals, c=color, label=etype, alpha=0.6, s=40)

    ax.set_xlabel("Burstiness B")
    ax.set_ylabel("Memory M")
    ax.set_title("Burstiness vs Memory (B-M plane)")
    ax.axhline(y=0, color="gray", linestyle="--", alpha=0.3)
    ax.axvline(x=0, color="gray", linestyle="--", alpha=0.3)
    ax.legend()
    ax.set_xlim(-1.1, 1.1)
    ax.set_ylim(-1.1, 1.1)

    # Add quadrant labels
    ax.text(0.5, 0.5, "Bursty +\nMemory", ha="center", fontsize=8, alpha=0.4, transform=ax.transAxes)
    ax.text(-0.0, 0.5, "Regular +\nMemory", ha="center", fontsize=8, alpha=0.4, transform=ax.transAxes)
    ax.text(0.5, -0.0, "Bursty +\nNo memory", ha="center", fontsize=8, alpha=0.4, transform=ax.transAxes)

    plt.tight_layout()
    plt.savefig(os.path.join(FIGURES_DIR, "burstiness_memory_plane.png"), dpi=150)
    plt.close()
    print(f"  Saved: {FIGURES_DIR}/burstiness_memory_plane.png")

    # ── Plot 3: Excitation heatmap (window=5) ──
    if 5 in hawkes_results:
        matrix = hawkes_results[5]
        types_for_heatmap = ["correction", "tool_failure", "edit", "bash", "read", "thinking"]
        n = len(types_for_heatmap)

        heatmap = np.ones((n, n))
        for i, trigger in enumerate(types_for_heatmap):
            for j, response in enumerate(types_for_heatmap):
                key = (trigger, response)
                if key in matrix:
                    heatmap[i, j] = matrix[key]["excitation_ratio"]

        fig, ax = plt.subplots(figsize=(8, 7))

        # Log scale for better visualization
        log_heatmap = np.log2(np.clip(heatmap, 0.1, 10))

        im = ax.imshow(log_heatmap, cmap="RdBu_r", aspect="auto", vmin=-2, vmax=2)
        ax.set_xticks(range(n))
        ax.set_xticklabels(types_for_heatmap, rotation=45, ha="right")
        ax.set_yticks(range(n))
        ax.set_yticklabels(types_for_heatmap)
        ax.set_xlabel("Response event")
        ax.set_ylabel("Trigger event")
        ax.set_title("Excitation/Inhibition Matrix (window=5)\nlog₂(rate ratio), red=excites, blue=inhibits")

        # Add values
        for i in range(n):
            for j in range(n):
                val = heatmap[i, j]
                color = "white" if abs(log_heatmap[i, j]) > 1 else "black"
                ax.text(j, i, f"{val:.2f}", ha="center", va="center", fontsize=8, color=color)

        plt.colorbar(im, label="log₂(excitation ratio)")
        plt.tight_layout()
        plt.savefig(os.path.join(FIGURES_DIR, "excitation_heatmap.png"), dpi=150)
        plt.close()
        print(f"  Saved: {FIGURES_DIR}/excitation_heatmap.png")

    # ── Plot 4: Temporal decay ──
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))

    for idx, trigger in enumerate(["correction", "tool_failure"]):
        if trigger in decay_results:
            ax = axes[idx]
            r = decay_results[trigger]
            lags = range(1, len(r["excitation_ratios"]) + 1)
            ax.bar(lags, r["excitation_ratios"], color=colors[idx], alpha=0.7, edgecolor="black")
            ax.axhline(y=1.0, color="gray", linestyle="--", alpha=0.5, label="Baseline")
            ax.set_xlabel("Lag (events after trigger)")
            ax.set_ylabel("Excitation ratio")
            ax.set_title(f"Excitation Decay: {trigger} → correction")
            ax.legend()

    plt.tight_layout()
    plt.savefig(os.path.join(FIGURES_DIR, "excitation_decay.png"), dpi=150)
    plt.close()
    print(f"  Saved: {FIGURES_DIR}/excitation_decay.png")

    # ── Plot 5: Cascade length distribution ──
    if cascades:
        fig, axes = plt.subplots(1, 2, figsize=(14, 5))

        lengths = [c["length"] for c in cascades]
        ax = axes[0]
        ax.hist(lengths, bins=range(min(lengths), max(lengths) + 2),
                color="#e74c3c", alpha=0.7, edgecolor="black", align="left")
        ax.set_xlabel("Cascade Length (# corrections)")
        ax.set_ylabel("Frequency")
        ax.set_title("Correction Cascade Length Distribution")

        spans = [c["span"] for c in cascades]
        ax = axes[1]
        ax.hist(spans, bins=15, color="#e67e22", alpha=0.7, edgecolor="black")
        ax.set_xlabel("Cascade Span (events)")
        ax.set_ylabel("Frequency")
        ax.set_title("Correction Cascade Span Distribution")

        plt.tight_layout()
        plt.savefig(os.path.join(FIGURES_DIR, "cascade_distribution.png"), dpi=150)
        plt.close()
        print(f"  Saved: {FIGURES_DIR}/cascade_distribution.png")


# ── Summary Statistics ────────────────────────────────────────────────────

def print_summary(sessions, projects):
    """Print overall dataset summary."""
    print("="*70)
    print("DATASET SUMMARY")
    print("="*70)

    total_events = 0
    event_counts = Counter()
    project_counts = Counter()

    for sid, events in sessions.items():
        total_events += len(events)
        for etype, _, _ in events:
            event_counts[etype] += 1
        project_counts[projects[sid]] += 1

    print(f"  Sessions: {len(sessions)}")
    print(f"  Projects: {len(project_counts)}")
    print(f"  Total coded events: {total_events}")
    print(f"\n  Event counts:")
    for etype, count in event_counts.most_common():
        print(f"    {etype}: {count} ({100*count/total_events:.1f}%)")
    print(f"\n  Sessions per project:")
    for proj, count in project_counts.most_common():
        print(f"    {proj}: {count}")


# ── JSON Export ───────────────────────────────────────────────────────────

def export_results(burstiness, memory, hawkes, decay, cascades, sessions, projects):
    """Export machine-readable results."""

    def safe_float(x):
        if isinstance(x, (np.floating, float)):
            if np.isnan(x) or np.isinf(x):
                return None
            return float(x)
        return x

    output = {
        "metadata": {
            "sessions_analyzed": len(sessions),
            "projects": len(set(projects.values())),
        },
        "burstiness": {},
        "memory": {},
        "hawkes_window5": {},
        "decay": {},
        "cascades": {
            "total": len(cascades),
            "sessions_with_cascades": len(set(c["session"] for c in cascades)) if cascades else 0,
        }
    }

    for etype in burstiness:
        output["burstiness"][etype] = {
            "mean_B": safe_float(burstiness[etype]["mean_B"]),
            "median_B": safe_float(burstiness[etype]["median_B"]),
            "n_sessions": burstiness[etype]["n_sessions"],
        }

    for etype in memory:
        output["memory"][etype] = {
            "mean_M": safe_float(memory[etype]["mean_M"]),
            "median_M": safe_float(memory[etype]["median_M"]),
            "n_sessions": memory[etype]["n_sessions"],
        }

    if 5 in hawkes:
        for (trigger, response), data in hawkes[5].items():
            key = f"{trigger}→{response}"
            output["hawkes_window5"][key] = {
                "excitation_ratio": safe_float(data["excitation_ratio"]),
                "triggered_windows": data["triggered_windows"],
            }

    for trigger in decay:
        output["decay"][trigger] = {
            "baseline_rate": safe_float(decay[trigger]["baseline"]),
            "excitation_by_lag": [safe_float(x) for x in decay[trigger]["excitation_ratios"][:10]],
        }

    out_path = os.path.join(OUTPUT_DIR, "burstiness-hawkes-results.json")
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\n  Results exported to: {out_path}")

    return output


# ── Main ──────────────────────────────────────────────────────────────────

def main():
    print("Loading sessions...")
    sessions, projects = load_sessions(MAX_SESSIONS)

    if not sessions:
        print("ERROR: No sessions loaded!")
        sys.exit(1)

    print_summary(sessions, projects)

    burstiness = analyze_burstiness(sessions, projects)
    memory = analyze_memory(sessions, burstiness)
    hawkes = analyze_hawkes(sessions)
    decay = analyze_temporal_decay(sessions)
    cascades = analyze_cascades(sessions, projects)

    print("\n" + "="*70)
    print("GENERATING PLOTS")
    print("="*70)
    create_plots(burstiness, memory, hawkes, decay, cascades)

    export_results(burstiness, memory, hawkes, decay, cascades, sessions, projects)

    print("\nDone.")


if __name__ == "__main__":
    main()
