#!/usr/bin/env python3
"""
T-Pattern Detection in Claude Code Sessions

Discovers recurring temporal patterns (T-patterns) in agent behavior --
sequences of events that occur at statistically consistent time intervals,
even when other events intervene.

Based on: Magnusson, M.S. (2000). "Discovering hidden time patterns in
behavior." Behavior Research Methods, 32(1), 93-110.

Method:
1. Code events from session data (tool calls, user messages, thinking blocks)
2. For each pair of event types (A, B), test whether B follows A within a
   critical interval more often than chance would predict
3. Build hierarchical T-patterns: if (A,B) is significant and (AB,C) also
   qualifies, that forms a level-2 pattern
4. Use permutation testing (shuffle timestamps within sessions) to establish
   significance thresholds

Output: discovered T-patterns with frequency, significance, and interpretation.
"""

import json
import os
import sys
import re
import random
import math
from collections import Counter, defaultdict
from pathlib import Path
from datetime import datetime

import numpy as np

# ──────────────────────────────────────────────────────────────────────
# Configuration
# ──────────────────────────────────────────────────────────────────────

CORPUS_DIR = os.environ.get("CORPUS_DIR", os.environ.get("MIDDENS_CORPUS", "corpus/"))
OUTPUT_DIR = os.environ.get("OUTPUT_DIR", os.environ.get("MIDDENS_OUTPUT", "experiments/"))
MAX_SESSIONS = 200
MIN_EVENTS_PER_SESSION = 20
N_PERMUTATIONS = 100  # For significance testing
SIGNIFICANCE_LEVEL = 0.01  # Strict: p < 0.01
MIN_PATTERN_OCCURRENCES = 10  # Pattern must occur at least this many times across sessions
MAX_TPATTERN_LEVEL = 3  # Build up to level-3 hierarchical patterns

# Event coding (reusing approach from lag sequential analysis)
READ_TOOLS = {"Read", "Glob", "Grep"}
EDIT_TOOLS = {"Edit", "Write", "NotebookEdit"}
BASH_TOOLS = {"Bash"}
SEARCH_TOOLS = {"WebSearch", "WebFetch"}
AGENT_TOOLS = {"Skill", "ToolSearch"}

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

STRONG_CORRECTION_PATTERNS = [
    r"^no[.,!]?\s", r"^wrong\b", r"^that'?s not", r"^not what i",
    r"^don'?t\b", r"^stop\b", r"^incorrect\b",
]
STRONG_CORRECTION_RE = re.compile("|".join(STRONG_CORRECTION_PATTERNS), re.IGNORECASE)

APPROVAL_PATTERNS = [
    r"\bgood\b", r"\bgreat\b", r"\byes\b", r"\bthanks\b",
    r"\bthank you\b", r"\bperfect\b", r"\bship\b", r"\bnice\b",
    r"\blgtm\b", r"\blooks good\b", r"\bawesome\b", r"\bexcellent\b",
]
APPROVAL_RE = re.compile("|".join(APPROVAL_PATTERNS), re.IGNORECASE)

MAX_SIGNAL_LENGTH = 500

# Event type labels
EVENT_LABELS = {
    "UR": "User request",
    "UC": "User correction",
    "UA": "User approval",
    "AR": "Agent reads (Read/Glob/Grep)",
    "AE": "Agent edits (Edit/Write)",
    "AB": "Agent bash",
    "AT": "Agent text output",
    "AK": "Agent thinks",
    "AF": "Agent fails (tool error)",
}


# ──────────────────────────────────────────────────────────────────────
# Event coding
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


def classify_user_message(msg):
    text = extract_user_text(msg)
    if not text or len(text.strip()) < 2:
        return None
    stripped = text.strip()
    for indicator in SYSTEM_INDICATORS:
        if stripped.startswith(indicator):
            return None
    if "Your ONLY job" in text or "Your task is" in text:
        return None
    text_len = len(stripped)
    if text_len < MAX_SIGNAL_LENGTH:
        if CORRECTION_RE.search(stripped):
            return "UC"
        if APPROVAL_RE.search(stripped):
            return "UA"
    else:
        if STRONG_CORRECTION_RE.search(stripped):
            return "UC"
    return "UR"


def parse_timestamp(ts_str):
    """Parse ISO timestamp to epoch seconds."""
    if not ts_str:
        return None
    try:
        # Handle both Z and +00:00 formats
        ts_str = ts_str.replace("Z", "+00:00")
        dt = datetime.fromisoformat(ts_str)
        return dt.timestamp()
    except (ValueError, TypeError):
        return None


def code_session_with_timestamps(filepath):
    """Convert a session JSONL file to a sequence of (event_code, timestamp_seconds) tuples."""
    events = []
    try:
        with open(filepath, 'r') as f:
            lines = f.readlines()
    except Exception:
        return events

    # First pass: assign monotonically increasing pseudo-timestamps
    # if real timestamps are sparse. We use line index as fallback.
    for line_idx, line in enumerate(lines):
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue

        msg_type = msg.get("type", "")
        ts = parse_timestamp(msg.get("timestamp", ""))
        # Use line index as fallback timestamp (monotonic ordering)
        if ts is None:
            ts = float(line_idx)

        if msg_type == "user":
            if is_tool_result(msg):
                if has_error(msg):
                    events.append(("AF", ts))
                continue
            code = classify_user_message(msg)
            if code:
                events.append((code, ts))

        elif msg_type == "assistant":
            content = msg.get("message", {}).get("content", [])
            if isinstance(content, list):
                for block in content:
                    if not isinstance(block, dict):
                        continue
                    block_type = block.get("type", "")
                    if block_type == "thinking":
                        events.append(("AK", ts))
                    elif block_type == "text":
                        if block.get("text", "").strip():
                            events.append(("AT", ts))
                    elif block_type == "tool_use":
                        tool_name = block.get("name", "")
                        if tool_name in READ_TOOLS:
                            events.append(("AR", ts))
                        elif tool_name in EDIT_TOOLS:
                            events.append(("AE", ts))
                        elif tool_name in BASH_TOOLS:
                            events.append(("AB", ts))
                        else:
                            events.append(("AT", ts))

    return events


# ──────────────────────────────────────────────────────────────────────
# T-Pattern Detection Core
# ──────────────────────────────────────────────────────────────────────

def compute_critical_interval(event_a_times, event_b_times, session_duration):
    """
    For each occurrence of A, find the interval to the next B.
    The critical interval [d1, d2] is the range where B follows A
    significantly more often than chance.

    We use a simplified approach: compute the distribution of A->B intervals,
    and define the critical interval as the mode region (densest interval).
    """
    intervals = []
    b_times_sorted = sorted(event_b_times)

    for ta in event_a_times:
        # Find the next B after A using binary search
        import bisect
        idx = bisect.bisect_right(b_times_sorted, ta)
        if idx < len(b_times_sorted):
            dt = b_times_sorted[idx] - ta
            if dt > 0:
                intervals.append(dt)

    if len(intervals) < 3:
        return None, intervals

    intervals = np.array(intervals)

    # Use percentile-based critical interval: [25th, 75th] percentile
    # This captures the "typical" interval range
    d1 = np.percentile(intervals, 25)
    d2 = np.percentile(intervals, 75)

    # Ensure minimum window
    if d2 - d1 < 0.1:
        d2 = d1 + max(0.1, d1 * 0.5)

    return (d1, d2), intervals


def count_pattern_occurrences(events_a, events_b, critical_interval):
    """Count how many times B follows A within the critical interval."""
    if critical_interval is None:
        return 0

    d1, d2 = critical_interval
    import bisect
    b_times = sorted(events_b)
    count = 0

    for ta in events_a:
        target_start = ta + d1
        target_end = ta + d2
        # Find B occurrences in [ta+d1, ta+d2]
        idx_start = bisect.bisect_left(b_times, target_start)
        idx_end = bisect.bisect_right(b_times, target_end)
        if idx_end > idx_start:
            count += 1  # At least one B in the interval

    return count


def permutation_test(events_by_type, type_a, type_b, critical_interval,
                     observed_count, session_duration, n_perms):
    """
    Permutation test: shuffle B event timestamps within the session,
    recount occurrences, compute p-value.
    """
    if critical_interval is None or observed_count == 0:
        return 1.0

    a_times = events_by_type[type_a]
    b_times = list(events_by_type[type_b])

    if len(a_times) == 0 or len(b_times) == 0:
        return 1.0

    # Collect all timestamps from all event types to form the pool
    all_timestamps = []
    for etype, times in events_by_type.items():
        all_timestamps.extend(times)
    all_timestamps.sort()

    n_b = len(b_times)
    n_exceed = 0

    for _ in range(n_perms):
        # Shuffle: randomly assign n_b timestamps from the pool to B
        shuffled_b = sorted(random.sample(all_timestamps, min(n_b, len(all_timestamps))))
        perm_count = count_pattern_occurrences(a_times, shuffled_b, critical_interval)
        if perm_count >= observed_count:
            n_exceed += 1

    return (n_exceed + 1) / (n_perms + 1)  # +1 for continuity correction


def detect_level1_patterns(session_events_list):
    """
    Detect level-1 T-patterns across all sessions.

    For each pair of event types (A, B), aggregate across sessions:
    1. Compute critical intervals per session
    2. Count occurrences within critical intervals
    3. Test significance via permutation
    """
    event_types = list(EVENT_LABELS.keys())
    print(f"\n  Testing {len(event_types)}^2 = {len(event_types)**2} event pairs...")

    # Aggregate events by type across all sessions
    # But we need per-session data for permutation testing
    pair_results = {}

    for type_a in event_types:
        for type_b in event_types:
            total_observed = 0
            total_expected_under_null = 0
            session_counts = []
            all_intervals = []

            for session_events in session_events_list:
                # Get events by type for this session
                events_by_type = defaultdict(list)
                for code, ts in session_events:
                    events_by_type[code].append(ts)

                a_times = events_by_type[type_a]
                b_times = events_by_type[type_b]

                if len(a_times) < 2 or len(b_times) < 2:
                    continue

                # Session duration
                all_ts = [ts for _, ts in session_events]
                session_duration = max(all_ts) - min(all_ts)
                if session_duration <= 0:
                    continue

                # Compute critical interval for this session
                ci, intervals = compute_critical_interval(a_times, b_times, session_duration)
                if ci is None:
                    continue

                all_intervals.extend(intervals)

                # Count occurrences
                obs = count_pattern_occurrences(a_times, b_times, ci)
                total_observed += obs
                session_counts.append(obs)

            if total_observed < MIN_PATTERN_OCCURRENCES or len(session_counts) < 3:
                continue

            # Compute aggregate critical interval from all intervals
            if len(all_intervals) < 5:
                continue

            all_intervals_arr = np.array(all_intervals)
            agg_ci = (np.percentile(all_intervals_arr, 25),
                      np.percentile(all_intervals_arr, 75))

            # Permutation test on aggregate
            # We pool events across sessions and test
            agg_pvalue = _aggregate_permutation_test(
                session_events_list, type_a, type_b, agg_ci,
                total_observed, N_PERMUTATIONS
            )

            if agg_pvalue < SIGNIFICANCE_LEVEL:
                pair_results[(type_a, type_b)] = {
                    'type_a': type_a,
                    'type_b': type_b,
                    'total_occurrences': total_observed,
                    'n_sessions': len(session_counts),
                    'mean_per_session': np.mean(session_counts),
                    'critical_interval': agg_ci,
                    'median_interval': float(np.median(all_intervals_arr)),
                    'p_value': agg_pvalue,
                    'effect_size': total_observed / max(1, len(session_counts)),
                }

    return pair_results


def _aggregate_permutation_test(session_events_list, type_a, type_b,
                                critical_interval, observed_total, n_perms):
    """Run permutation test aggregated across sessions."""
    # Subsample sessions for speed
    sessions_to_test = session_events_list
    if len(sessions_to_test) > 50:
        sessions_to_test = random.sample(sessions_to_test, 50)

    # Recount observed on subsample
    observed_sub = 0
    session_data = []
    for session_events in sessions_to_test:
        events_by_type = defaultdict(list)
        for code, ts in session_events:
            events_by_type[code].append(ts)

        a_times = events_by_type[type_a]
        b_times = events_by_type[type_b]

        if len(a_times) < 1 or len(b_times) < 1:
            continue

        obs = count_pattern_occurrences(a_times, b_times, critical_interval)
        observed_sub += obs
        session_data.append(events_by_type)

    if observed_sub == 0:
        return 1.0

    n_exceed = 0
    for _ in range(n_perms):
        perm_total = 0
        for events_by_type in session_data:
            a_times = events_by_type[type_a]
            # Collect all timestamps for shuffling
            all_ts = []
            for times in events_by_type.values():
                all_ts.extend(times)
            n_b = len(events_by_type[type_b])
            if n_b == 0 or len(all_ts) == 0:
                continue
            shuffled_b = sorted(random.sample(all_ts, min(n_b, len(all_ts))))
            perm_total += count_pattern_occurrences(a_times, shuffled_b, critical_interval)

        if perm_total >= observed_sub:
            n_exceed += 1

    return (n_exceed + 1) / (n_perms + 1)


def detect_hierarchical_patterns(level1_patterns, session_events_list):
    """
    Build hierarchical T-patterns.
    If (A,B) is a level-1 T-pattern and (AB,C) also qualifies, that's level-2.
    """
    higher_patterns = {}
    level1_keys = list(level1_patterns.keys())

    # Level 2: combine level-1 patterns with individual events
    print(f"\n  Building level-2 patterns from {len(level1_keys)} level-1 patterns...")

    event_types = list(EVENT_LABELS.keys())
    level2_candidates = []

    for (a, b), pat_ab in level1_patterns.items():
        for c in event_types:
            level2_candidates.append((a, b, c, pat_ab))

    # Test each candidate
    level2_patterns = {}
    for a, b, c, pat_ab in level2_candidates:
        total_obs = 0
        n_sessions = 0

        for session_events in session_events_list:
            events_by_type = defaultdict(list)
            for code, ts in session_events:
                events_by_type[code].append(ts)

            a_times = events_by_type[a]
            b_times = events_by_type[b]
            c_times = events_by_type[c]

            if len(a_times) < 1 or len(b_times) < 1 or len(c_times) < 1:
                continue

            ci_ab = pat_ab['critical_interval']

            # Find AB pattern instances (timestamps of B in pattern)
            import bisect
            ab_instance_times = []
            b_sorted = sorted(b_times)
            for ta in a_times:
                t_start = ta + ci_ab[0]
                t_end = ta + ci_ab[1]
                idx_s = bisect.bisect_left(b_sorted, t_start)
                idx_e = bisect.bisect_right(b_sorted, t_end)
                if idx_e > idx_s:
                    ab_instance_times.append(b_sorted[idx_s])  # First matching B

            if len(ab_instance_times) < 2:
                continue

            # Now check if C follows AB within a critical interval
            ci_abc, _ = compute_critical_interval(ab_instance_times, c_times,
                                                   max(c_times) - min(c_times) if len(c_times) > 1 else 1.0)
            if ci_abc is None:
                continue

            obs = count_pattern_occurrences(ab_instance_times, c_times, ci_abc)
            total_obs += obs
            n_sessions += 1

        if total_obs >= MIN_PATTERN_OCCURRENCES and n_sessions >= 3:
            key = (a, b, c)
            level2_patterns[key] = {
                'components': [a, b, c],
                'total_occurrences': total_obs,
                'n_sessions': n_sessions,
                'mean_per_session': total_obs / n_sessions,
            }

    higher_patterns['level2'] = level2_patterns
    print(f"  Found {len(level2_patterns)} level-2 T-patterns")

    # Level 3: combine level-2 with individual events (limited search)
    if MAX_TPATTERN_LEVEL >= 3 and level2_patterns:
        print(f"\n  Building level-3 patterns from top {min(20, len(level2_patterns))} level-2 patterns...")
        # Only test top-20 level-2 patterns to keep runtime manageable
        top_l2 = sorted(level2_patterns.items(), key=lambda x: x[1]['total_occurrences'], reverse=True)[:20]
        level3_patterns = {}

        for (a, b, c), pat_abc in top_l2:
            for d in event_types:
                total_obs = 0
                n_sessions = 0

                for session_events in session_events_list:
                    events_by_type = defaultdict(list)
                    for code, ts in session_events:
                        events_by_type[code].append(ts)

                    if any(len(events_by_type[x]) < 1 for x in [a, b, c, d]):
                        continue

                    ci_ab = level1_patterns.get((a, b), {}).get('critical_interval')
                    if ci_ab is None:
                        continue

                    import bisect
                    # Find ABC instances
                    b_sorted = sorted(events_by_type[b])
                    c_sorted = sorted(events_by_type[c])
                    abc_times = []

                    for ta in events_by_type[a]:
                        t_start = ta + ci_ab[0]
                        t_end = ta + ci_ab[1]
                        idx_s = bisect.bisect_left(b_sorted, t_start)
                        idx_e = bisect.bisect_right(b_sorted, t_end)
                        if idx_e > idx_s:
                            tb = b_sorted[idx_s]
                            # Find C after B
                            for tc in c_sorted:
                                if tc > tb:
                                    abc_times.append(tc)
                                    break

                    if len(abc_times) < 2:
                        continue

                    d_times = events_by_type[d]
                    ci_abcd, _ = compute_critical_interval(
                        abc_times, d_times,
                        max(d_times) - min(d_times) if len(d_times) > 1 else 1.0
                    )
                    if ci_abcd is None:
                        continue

                    obs = count_pattern_occurrences(abc_times, d_times, ci_abcd)
                    total_obs += obs
                    n_sessions += 1

                if total_obs >= MIN_PATTERN_OCCURRENCES and n_sessions >= 3:
                    key = (a, b, c, d)
                    level3_patterns[key] = {
                        'components': [a, b, c, d],
                        'total_occurrences': total_obs,
                        'n_sessions': n_sessions,
                        'mean_per_session': total_obs / n_sessions,
                    }

        higher_patterns['level3'] = level3_patterns
        print(f"  Found {len(level3_patterns)} level-3 T-patterns")

    return higher_patterns


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
# Report generation
# ──────────────────────────────────────────────────────────────────────

def generate_report(level1, higher, event_counts, total_events, n_sessions, n_projects):
    """Generate markdown report."""
    lines = []

    lines.append("# T-Pattern Detection in Claude Code Sessions\n")
    lines.append("## Method\n")
    lines.append("Applied Magnusson's T-pattern detection algorithm to discover recurring")
    lines.append("temporal patterns in agent behavior -- sequences of events that occur at")
    lines.append("statistically consistent time intervals, even when other events intervene.\n")
    lines.append(f"- **Sessions analyzed**: {n_sessions} (from {n_projects} projects)")
    lines.append(f"- **Total coded events**: {total_events}")
    lines.append(f"- **Significance**: p < {SIGNIFICANCE_LEVEL} (permutation test, {N_PERMUTATIONS} permutations)")
    lines.append(f"- **Minimum occurrences**: {MIN_PATTERN_OCCURRENCES}")
    lines.append(f"- **Max hierarchy depth**: {MAX_TPATTERN_LEVEL}\n")

    lines.append("### Event Distribution\n")
    lines.append("| Code | Label | Count | % |")
    lines.append("|------|-------|-------|---|")
    for code in sorted(EVENT_LABELS.keys()):
        count = event_counts.get(code, 0)
        pct = count / total_events * 100 if total_events > 0 else 0
        lines.append(f"| {code} | {EVENT_LABELS[code]} | {count} | {pct:.1f}% |")

    # Level-1 T-patterns
    lines.append("\n## Level-1 T-Patterns (Event Pairs)\n")
    lines.append("These are statistically significant temporal relationships: event B follows")
    lines.append("event A within a critical time interval more often than chance.\n")

    sorted_l1 = sorted(level1.values(), key=lambda x: x['total_occurrences'], reverse=True)

    lines.append("| Rank | A | B | Occurrences | Sessions | Median Interval | p-value |")
    lines.append("|------|---|---|-------------|----------|-----------------|---------|")
    for rank, pat in enumerate(sorted_l1, 1):
        ci = pat['critical_interval']
        lines.append(
            f"| {rank} | {pat['type_a']} | {pat['type_b']} | "
            f"{pat['total_occurrences']} | {pat['n_sessions']} | "
            f"{pat['median_interval']:.1f}s | {pat['p_value']:.4f} |"
        )

    # Self-transitions
    self_patterns = [p for p in sorted_l1 if p['type_a'] == p['type_b']]
    cross_patterns = [p for p in sorted_l1 if p['type_a'] != p['type_b']]

    lines.append(f"\n### Self-Transition Patterns ({len(self_patterns)} found)\n")
    lines.append("Events that recur in temporal bursts (same event type repeats at consistent intervals).\n")
    for pat in self_patterns:
        ci = pat['critical_interval']
        lines.append(
            f"- **{pat['type_a']}->{pat['type_b']}**: {pat['total_occurrences']} occurrences "
            f"across {pat['n_sessions']} sessions, "
            f"critical interval [{ci[0]:.1f}s, {ci[1]:.1f}s], "
            f"median {pat['median_interval']:.1f}s (p={pat['p_value']:.4f})"
        )

    lines.append(f"\n### Cross-Event Patterns ({len(cross_patterns)} found)\n")
    lines.append("Temporal relationships between different event types.\n")
    for pat in cross_patterns:
        ci = pat['critical_interval']
        lines.append(
            f"- **{pat['type_a']}->{pat['type_b']}**: {pat['total_occurrences']} occurrences "
            f"across {pat['n_sessions']} sessions, "
            f"critical interval [{ci[0]:.1f}s, {ci[1]:.1f}s], "
            f"median {pat['median_interval']:.1f}s (p={pat['p_value']:.4f})"
        )

    # Level-2 T-patterns
    level2 = higher.get('level2', {})
    if level2:
        lines.append(f"\n## Level-2 T-Patterns (Event Triples)\n")
        lines.append("Hierarchical patterns: (A,B) is a T-pattern, and C follows (A,B) at a consistent interval.\n")

        sorted_l2 = sorted(level2.values(), key=lambda x: x['total_occurrences'], reverse=True)
        lines.append("| Rank | Pattern | Occurrences | Sessions | Mean/Session |")
        lines.append("|------|---------|-------------|----------|--------------|")
        for rank, pat in enumerate(sorted_l2[:30], 1):
            pattern_str = " -> ".join(pat['components'])
            lines.append(
                f"| {rank} | {pattern_str} | {pat['total_occurrences']} | "
                f"{pat['n_sessions']} | {pat['mean_per_session']:.1f} |"
            )

    # Level-3 T-patterns
    level3 = higher.get('level3', {})
    if level3:
        lines.append(f"\n## Level-3 T-Patterns (Event Quadruples)\n")
        lines.append("Deep hierarchical patterns: four-event sequences with consistent temporal structure.\n")

        sorted_l3 = sorted(level3.values(), key=lambda x: x['total_occurrences'], reverse=True)
        lines.append("| Rank | Pattern | Occurrences | Sessions | Mean/Session |")
        lines.append("|------|---------|-------------|----------|--------------|")
        for rank, pat in enumerate(sorted_l3[:20], 1):
            pattern_str = " -> ".join(pat['components'])
            lines.append(
                f"| {rank} | {pattern_str} | {pat['total_occurrences']} | "
                f"{pat['n_sessions']} | {pat['mean_per_session']:.1f} |"
            )

    # Interpretation
    lines.append("\n## Interpretation\n")

    # Group patterns by behavioral meaning
    lines.append("### Behavioral Signatures\n")

    # 1. Agent execution rhythm
    read_edit = level1.get(("AR", "AE"))
    think_text = level1.get(("AK", "AT"))
    think_read = level1.get(("AK", "AR"))

    if read_edit or think_text or think_read:
        lines.append("**1. Agent Execution Rhythm**\n")
        if think_read:
            lines.append(
                f"- Think-then-Read: AK->AR occurs {think_read['total_occurrences']} times "
                f"(median interval: {think_read['median_interval']:.1f}s). "
                f"The agent deliberates, then investigates."
            )
        if think_text:
            lines.append(
                f"- Think-then-Speak: AK->AT occurs {think_text['total_occurrences']} times "
                f"(median interval: {think_text['median_interval']:.1f}s). "
                f"Thinking produces narration before action."
            )
        if read_edit:
            lines.append(
                f"- Read-then-Edit: AR->AE occurs {read_edit['total_occurrences']} times "
                f"(median interval: {read_edit['median_interval']:.1f}s). "
                f"The agent reads context before modifying code."
            )
        lines.append("")

    # 2. Error-correction dynamics
    fail_patterns = [(k, v) for k, v in level1.items()
                     if k[0] == "AF" or k[1] == "AF"]
    correction_patterns = [(k, v) for k, v in level1.items()
                           if k[0] == "UC" or k[1] == "UC"]

    if fail_patterns:
        lines.append("**2. Error Dynamics**\n")
        for (a, b), pat in fail_patterns:
            lines.append(
                f"- {a}->{b}: {pat['total_occurrences']} occurrences "
                f"(median interval: {pat['median_interval']:.1f}s, p={pat['p_value']:.4f})"
            )
        lines.append("")

    if correction_patterns:
        lines.append("**3. User Correction Dynamics**\n")
        for (a, b), pat in correction_patterns:
            lines.append(
                f"- {a}->{b}: {pat['total_occurrences']} occurrences "
                f"(median interval: {pat['median_interval']:.1f}s, p={pat['p_value']:.4f})"
            )
        lines.append("")

    # 3. Burstiness
    self_p = [(k, v) for k, v in level1.items() if k[0] == k[1]]
    if self_p:
        lines.append("**4. Bursty Behavior (Self-Repetition Patterns)**\n")
        lines.append("Events that cluster in temporal bursts rather than being uniformly distributed:\n")
        for (a, b), pat in sorted(self_p, key=lambda x: x[1]['total_occurrences'], reverse=True):
            ci = pat['critical_interval']
            lines.append(
                f"- **{a}** repeats at [{ci[0]:.1f}s, {ci[1]:.1f}s] intervals "
                f"({pat['total_occurrences']} burst occurrences across {pat['n_sessions']} sessions)"
            )
        lines.append("")

    # 4. Notable level-2 patterns with interpretation
    if level2:
        lines.append("**5. Multi-Step Behavioral Sequences**\n")
        lines.append("Level-2+ T-patterns reveal stereotyped behavioral sequences:\n")

        # Identify notable patterns
        for key, pat in sorted(level2.items(), key=lambda x: x[1]['total_occurrences'], reverse=True)[:10]:
            seq = " -> ".join(pat['components'])
            lines.append(
                f"- **{seq}**: {pat['total_occurrences']} occurrences "
                f"in {pat['n_sessions']} sessions "
                f"({pat['mean_per_session']:.1f}/session)"
            )

            # Add interpretation for known patterns
            comps = pat['components']
            if comps == ['AK', 'AT', 'AR']:
                lines.append("  *Think, explain intent, then investigate -- the deliberative agent.*")
            elif comps == ['AK', 'AR', 'AE']:
                lines.append("  *Think, read context, then edit -- the careful worker.*")
            elif comps == ['AR', 'AR', 'AE']:
                lines.append("  *Multiple reads before editing -- thorough context gathering.*")
            elif comps == ['AK', 'AT', 'AE']:
                lines.append("  *Think, narrate, edit -- the full execution cycle.*")
            elif 'AF' in comps and 'AB' in comps:
                lines.append("  *Bash-failure loop -- the agent struggles with shell commands.*")
            elif comps == ['UR', 'AK', 'AT']:
                lines.append("  *User request triggers thinking and explanation -- the standard response pattern.*")
            elif 'UC' in comps:
                lines.append("  *Pattern involves user correction -- a repair sequence.*")

        lines.append("")

    # Summary statistics
    lines.append("## Summary Statistics\n")
    lines.append(f"| Metric | Value |")
    lines.append(f"|--------|-------|")
    lines.append(f"| Level-1 T-patterns | {len(level1)} |")
    lines.append(f"| Level-2 T-patterns | {len(level2)} |")
    lines.append(f"| Level-3 T-patterns | {len(higher.get('level3', {}))} |")
    lines.append(f"| Self-transition patterns | {len(self_patterns)} |")
    lines.append(f"| Cross-event patterns | {len(cross_patterns)} |")
    lines.append(f"| Most frequent L1 pattern | {sorted_l1[0]['type_a']}->{sorted_l1[0]['type_b']} ({sorted_l1[0]['total_occurrences']}x) |" if sorted_l1 else "| Most frequent L1 pattern | N/A |")
    lines.append("")

    return "\n".join(lines)


# ──────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────

def main():
    print("=" * 70)
    print("T-PATTERN DETECTION IN CLAUDE CODE SESSIONS")
    print("Magnusson (2000) method")
    print("=" * 70)

    # Find session files
    print("\nDiscovering session files...")
    all_files = find_session_files(CORPUS_DIR)
    print(f"  Found {len(all_files)} JSONL session files (10KB-50MB, excluding subagents)")

    # Sample sessions
    sampled, by_project = sample_sessions(all_files, MAX_SESSIONS)
    n_projects = len(by_project)
    print(f"  Sampled {len(sampled)} sessions from {n_projects} projects")

    # Code events
    print("\nCoding events with timestamps...")
    all_session_events = []
    event_counts = Counter()
    sessions_used = 0
    sessions_skipped = 0

    for i, (filepath, size) in enumerate(sampled):
        if (i + 1) % 20 == 0:
            sys.stdout.write(f"\r  Processing {i+1}/{len(sampled)}...")
            sys.stdout.flush()

        events = code_session_with_timestamps(filepath)
        if len(events) >= MIN_EVENTS_PER_SESSION:
            all_session_events.append(events)
            for code, ts in events:
                event_counts[code] += 1
            sessions_used += 1
        else:
            sessions_skipped += 1

    total_events = sum(event_counts.values())
    print(f"\r  Sessions coded: {sessions_used} (skipped {sessions_skipped})")
    print(f"  Total events: {total_events}")
    print(f"\n  Event distribution:")
    for code in sorted(EVENT_LABELS.keys()):
        count = event_counts.get(code, 0)
        pct = count / total_events * 100 if total_events > 0 else 0
        bar = "#" * int(pct * 2)
        print(f"    {code}: {count:>7d} ({pct:5.1f}%) {bar}")

    # Level-1 T-pattern detection
    print("\n" + "=" * 70)
    print("PHASE 1: Level-1 T-Pattern Detection")
    print("=" * 70)
    level1_patterns = detect_level1_patterns(all_session_events)
    print(f"\n  Found {len(level1_patterns)} significant level-1 T-patterns")

    # Print level-1 results
    sorted_l1 = sorted(level1_patterns.values(), key=lambda x: x['total_occurrences'], reverse=True)
    print(f"\n  Top level-1 T-patterns:")
    for pat in sorted_l1[:15]:
        ci = pat['critical_interval']
        print(f"    {pat['type_a']}->{pat['type_b']}: "
              f"n={pat['total_occurrences']}, "
              f"sessions={pat['n_sessions']}, "
              f"CI=[{ci[0]:.1f}s,{ci[1]:.1f}s], "
              f"median={pat['median_interval']:.1f}s, "
              f"p={pat['p_value']:.4f}")

    # Hierarchical T-pattern detection
    print("\n" + "=" * 70)
    print("PHASE 2: Hierarchical T-Pattern Detection")
    print("=" * 70)
    higher_patterns = detect_hierarchical_patterns(level1_patterns, all_session_events)

    # Print level-2 results
    level2 = higher_patterns.get('level2', {})
    if level2:
        sorted_l2 = sorted(level2.values(), key=lambda x: x['total_occurrences'], reverse=True)
        print(f"\n  Top level-2 T-patterns:")
        for pat in sorted_l2[:10]:
            seq = " -> ".join(pat['components'])
            print(f"    {seq}: n={pat['total_occurrences']}, sessions={pat['n_sessions']}")

    # Print level-3 results
    level3 = higher_patterns.get('level3', {})
    if level3:
        sorted_l3 = sorted(level3.values(), key=lambda x: x['total_occurrences'], reverse=True)
        print(f"\n  Top level-3 T-patterns:")
        for pat in sorted_l3[:10]:
            seq = " -> ".join(pat['components'])
            print(f"    {seq}: n={pat['total_occurrences']}, sessions={pat['n_sessions']}")

    # Generate report
    print("\n" + "=" * 70)
    print("Generating report...")
    report = generate_report(level1_patterns, higher_patterns, event_counts,
                             total_events, sessions_used, n_projects)

    report_path = os.path.join(OUTPUT_DIR, "tpattern_detection.md")
    with open(report_path, 'w') as f:
        f.write(report)
    print(f"  Report written to: {report_path}")

    # Save raw results as JSON
    json_path = os.path.join(OUTPUT_DIR, "tpattern_detection_results.json")
    json_data = {
        'sessions_analyzed': sessions_used,
        'total_events': total_events,
        'event_counts': dict(event_counts),
        'level1_patterns': {
            f"{k[0]}->{k[1]}": {
                'type_a': v['type_a'],
                'type_b': v['type_b'],
                'total_occurrences': v['total_occurrences'],
                'n_sessions': v['n_sessions'],
                'mean_per_session': v['mean_per_session'],
                'critical_interval': list(v['critical_interval']),
                'median_interval': v['median_interval'],
                'p_value': v['p_value'],
            }
            for k, v in level1_patterns.items()
        },
        'level2_patterns': {
            "->".join(k): {
                'components': v['components'],
                'total_occurrences': v['total_occurrences'],
                'n_sessions': v['n_sessions'],
                'mean_per_session': v['mean_per_session'],
            }
            for k, v in level2.items()
        },
        'level3_patterns': {
            "->".join(k): {
                'components': v['components'],
                'total_occurrences': v['total_occurrences'],
                'n_sessions': v['n_sessions'],
                'mean_per_session': v['mean_per_session'],
            }
            for k, v in level3.items()
        } if level3 else {},
    }

    with open(json_path, 'w') as f:
        json.dump(json_data, f, indent=2)
    print(f"  JSON results written to: {json_path}")

    print(f"\n{'=' * 70}")
    print(f"COMPLETE: {len(level1_patterns)} L1, {len(level2)} L2, {len(level3)} L3 T-patterns")
    print(f"{'=' * 70}")


if __name__ == "__main__":
    main()
