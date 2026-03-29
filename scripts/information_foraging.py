#!/usr/bin/env python3
"""
Information Foraging Theory Analysis of Claude Code Sessions.

Models agent behavior as information foraging -- treating code exploration
as analogous to animals foraging for food in patches.

Key concepts:
- Patch: a directory or file the agent reads/edits (a locus of information)
- Patch residence time: how many turns the agent spends in one patch before moving
- Diet breadth: how many file types the agent explores
- Marginal value theorem: does the agent leave patches when returns diminish?
- Giving-up time: how long the agent stays after the last "gain" (edit) in a patch

Reference: Pirolli, P. & Card, S. (1999). "Information Foraging."
Psychological Review, 106(4).
"""

import json
import math
import os
import re
import sys
import random
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

# ============================================================
# CONFIGURATION
# ============================================================

CORPUS_DIR = os.environ.get(
    "CORPUS_DIR",
    os.environ.get("MIDDENS_CORPUS", "corpus/"),
)
OUTPUT_DIR = Path(os.environ.get(
    "OUTPUT_DIR",
    os.environ.get("MIDDENS_OUTPUT", "experiments/"),
))
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

MAX_SESSIONS = 200

# ============================================================
# DATA LOADING (reused pattern from existing scripts)
# ============================================================

CORRECTION_PATTERNS = [
    (r"\bno,\s", 2), (r"\bno\.\s", 2), (r"^no$", 2),
    (r"\bwrong\b", 2), (r"\bnot what i\b", 3), (r"\bwhy did you\b", 3),
    (r"\binstead of\b", 1), (r"\bdon'?t do\b", 2), (r"\bstop\b", 1),
    (r"\bundo\b", 2), (r"\brevert\b", 2), (r"\bthat'?s not\b", 2),
    (r"\bincorrect\b", 2), (r"\bwhat are you doing\b", 3),
    (r"\bplease don'?t\b", 2), (r"\bi said\b", 1), (r"\bi asked for\b", 2),
    (r"\bnot that\b", 1), (r"\byou broke\b", 3), (r"\bbroken\b", 1),
    (r"\bthat'?s wrong\b", 3), (r"\byou'?re doing it wrong\b", 3),
    (r"\bnot right\b", 2), (r"\bi didn'?t ask\b", 3),
    (r"\byou missed\b", 2), (r"\byou forgot\b", 2),
]

POSITIVE_PATTERNS = [
    (r"\bthanks?\b", 1), (r"\bthank you\b", 2), (r"\bgreat\b", 1),
    (r"\bperfect\b", 2), (r"\bgood job\b", 2), (r"\bnice\b", 1),
    (r"\bexcellent\b", 2), (r"\bawesome\b", 2), (r"\blooks good\b", 2),
    (r"\bwell done\b", 2), (r"\blgtm\b", 3), (r"\bexactly\b", 1),
    (r"\bship it\b", 3), (r"\bnice work\b", 2),
]


def classify_user_message(text):
    text_lower = text.lower().strip()
    if len(text_lower) < 5 or len(text_lower) > 500:
        return "neutral"
    correction_score = sum(w for p, w in CORRECTION_PATTERNS if re.search(p, text_lower))
    positive_score = sum(w for p, w in POSITIVE_PATTERNS if re.search(p, text_lower))
    if correction_score >= 2 and correction_score > positive_score:
        return "correction"
    elif positive_score >= 2 and positive_score > correction_score:
        return "positive"
    return "neutral"


def _find_jsonl_files(root):
    results = []
    for dirpath, dirnames, filenames in os.walk(root, followlinks=True):
        if "subagents" in dirpath:
            continue
        for fn in filenames:
            if fn.endswith(".jsonl"):
                results.append(os.path.join(dirpath, fn))
    return sorted(results)


def shorten_project_name(name):
    """Shorten a project directory name by stripping user-specific path prefixes."""
    # Strip -Users-<username>-<optional-subdir>- prefixes generically
    shortened = re.sub(r'^-Users-[^-]+-(?:projects-|Projects-|workspaces-|[^-]+-)*', '', name)
    if shortened and shortened != name:
        return shortened
    # Also strip interior -Users-<username>- segments
    shortened = re.sub(r'-Users-[^-]+-', '-', name)
    return shortened if shortened else name


def parse_session(filepath):
    messages = []
    with open(filepath, "r") as f:
        for line_num, line in enumerate(f):
            try:
                obj = json.loads(line.strip())
                obj["_line_num"] = line_num
                messages.append(obj)
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue
    return messages


def extract_user_messages(messages):
    user_msgs = []
    for i, msg in enumerate(messages):
        if msg.get("type") not in ("human", "user"):
            continue
        content = msg.get("message", {}).get("content", "")
        if isinstance(content, list):
            block_types = [b.get("type", "") if isinstance(b, dict) else "str" for b in content]
            if "tool_result" in block_types:
                continue
            text_parts = []
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    text_parts.append(block.get("text", ""))
                elif isinstance(block, str):
                    text_parts.append(block)
            content = " ".join(text_parts)
        elif not isinstance(content, str):
            content = str(content)
        stripped = content.strip()
        if not stripped or len(stripped) < 10:
            continue
        if any(stripped.startswith(p) for p in [
            "<command-", "<local-command-", "<teammate-message",
            "Stop hook feedback", "[Request interrupted",
            "You are a security classifier", "You are Boucle", "# /",
        ]):
            continue
        if "continued from a previous conversation" in stripped.lower():
            continue
        user_msgs.append({"text": content, "index": i})
    return user_msgs


def compute_session_success(messages, user_msgs):
    if not user_msgs:
        return 0.0
    final_sentiment = "neutral"
    for um in reversed(user_msgs):
        cls = classify_user_message(um["text"])
        if cls != "neutral":
            final_sentiment = cls
            break
    corrections = sum(1 for um in user_msgs if classify_user_message(um["text"]) == "correction")
    correction_ratio = corrections / max(len(user_msgs), 1)
    score = 0.0
    if final_sentiment == "positive":
        score += 2
    elif final_sentiment == "correction":
        score -= 2
    score -= correction_ratio * 3
    return score


# ============================================================
# FORAGING EVENT EXTRACTION
# ============================================================

# Tools that involve reading/exploring a file path
READ_TOOLS = {"Read", "Glob", "Grep", "WebFetch", "WebSearch", "ToolSearch"}
# Tools that produce a "gain" (modification)
EDIT_TOOLS = {"Edit", "Write", "NotebookEdit"}
# Tools that represent between-patch activity
BETWEEN_TOOLS = {"Bash", "Agent", "Skill", "TaskCreate", "TaskList",
                 "TaskOutput", "TaskStop", "TaskUpdate", "AskUserQuestion"}


def extract_foraging_events(messages):
    """Extract a sequence of foraging events from session messages.

    Each event is:
      {turn, tool, path, directory, action_type (read/edit/between), file_ext}

    We determine the 'patch' (directory) from tool arguments.
    """
    events = []
    turn = 0

    for msg in messages:
        if msg.get("type") == "assistant":
            content = msg.get("message", {}).get("content", [])
            if not isinstance(content, list):
                continue
            for block in content:
                if not isinstance(block, dict) or block.get("type") != "tool_use":
                    continue

                tool_name = block.get("name", "unknown")
                inp = block.get("input", {})
                if not isinstance(inp, dict):
                    inp = {}

                # Extract file path from tool input
                file_path = None
                if tool_name in ("Read", "Edit", "Write", "NotebookEdit"):
                    file_path = inp.get("file_path", inp.get("path", ""))
                elif tool_name == "Glob":
                    file_path = inp.get("path", "")
                elif tool_name == "Grep":
                    file_path = inp.get("path", "")
                elif tool_name == "Bash":
                    # Try to extract path from command
                    cmd = inp.get("command", "")
                    # Common patterns: cd /path, cat /path, ls /path
                    path_match = re.search(r'(?:cd|cat|ls|head|tail)\s+["\']?(/[^\s"\';&|]+)', cmd)
                    if path_match:
                        file_path = path_match.group(1)

                # Normalize path
                if file_path and isinstance(file_path, str) and file_path.startswith("/"):
                    directory = os.path.dirname(file_path) if not os.path.basename(file_path) == "" else file_path
                    file_ext = os.path.splitext(file_path)[1].lower() if "." in os.path.basename(file_path) else ""
                else:
                    directory = None
                    file_ext = ""
                    file_path = None

                # Classify action type
                if tool_name in READ_TOOLS:
                    action_type = "read"
                elif tool_name in EDIT_TOOLS:
                    action_type = "edit"
                else:
                    action_type = "between"

                events.append({
                    "turn": turn,
                    "tool": tool_name,
                    "path": file_path,
                    "directory": directory,
                    "action_type": action_type,
                    "file_ext": file_ext,
                })
                turn += 1

    return events


# ============================================================
# PATCH ANALYSIS
# ============================================================

def identify_patches(events):
    """Identify patches (directory-based) and compute patch visits.

    A patch visit is a contiguous run of events in the same directory.
    Events without a directory are considered "between-patch" travel.
    """
    if not events:
        return []

    patches = []
    current_dir = None
    current_patch = None

    for event in events:
        d = event["directory"]

        if d is None:
            # Between-patch event (no directory info)
            if current_patch is not None:
                current_patch["between_after"] += 1
            continue

        if d != current_dir:
            # Switching to a new patch
            if current_patch is not None:
                patches.append(current_patch)

            current_dir = d
            current_patch = {
                "directory": d,
                "start_turn": event["turn"],
                "end_turn": event["turn"],
                "events": [event],
                "reads": 0,
                "edits": 0,
                "between_after": 0,
                "file_exts": set(),
                "files_touched": set(),
            }
        else:
            current_patch["end_turn"] = event["turn"]
            current_patch["events"].append(event)

        # Update patch stats
        if event["action_type"] == "read":
            current_patch["reads"] += 1
        elif event["action_type"] == "edit":
            current_patch["edits"] += 1
        if event["file_ext"]:
            current_patch["file_exts"].add(event["file_ext"])
        if event["path"]:
            current_patch["files_touched"].add(event["path"])

    if current_patch is not None:
        patches.append(current_patch)

    # Compute derived metrics for each patch
    for p in patches:
        p["residence_time"] = p["end_turn"] - p["start_turn"] + 1
        p["total_events"] = len(p["events"])
        p["gain"] = p["edits"]
        p["num_files"] = len(p["files_touched"])
        p["num_ext_types"] = len(p["file_exts"])

        # Giving-up time: turns after last edit in this patch
        last_edit_turn = None
        for e in p["events"]:
            if e["action_type"] == "edit":
                last_edit_turn = e["turn"]

        if last_edit_turn is not None and p["edits"] > 0:
            p["giving_up_time"] = p["end_turn"] - last_edit_turn
        else:
            p["giving_up_time"] = p["residence_time"]  # No edits: stayed but got nothing

        # Marginal gain: edits per turn in first half vs second half
        half = len(p["events"]) // 2
        if half > 0:
            first_half_edits = sum(1 for e in p["events"][:half] if e["action_type"] == "edit")
            second_half_edits = sum(1 for e in p["events"][half:] if e["action_type"] == "edit")
            p["first_half_gain_rate"] = first_half_edits / half
            p["second_half_gain_rate"] = second_half_edits / max(len(p["events"]) - half, 1)
        else:
            p["first_half_gain_rate"] = 0
            p["second_half_gain_rate"] = 0

        # Clean up non-serializable sets
        p["file_exts"] = list(p["file_exts"])
        p["files_touched"] = list(p["files_touched"])

    return patches


def compute_switching_cost(patches):
    """Compute switching cost between consecutive patches.

    Switching cost = number of between-patch tool calls between leaving one
    patch and entering the next.
    """
    costs = []
    for i in range(len(patches) - 1):
        cost = patches[i]["between_after"]
        costs.append(cost)
    return costs


# ============================================================
# DIET BREADTH ANALYSIS
# ============================================================

def compute_diet_breadth(events):
    """Compute diet breadth: how many file types the agent explores.

    Uses file extensions as "prey types" and applies Shannon diversity.
    """
    ext_counter = Counter()
    for e in events:
        if e["file_ext"]:
            ext_counter[e["file_ext"]] += 1

    if not ext_counter:
        return {
            "distinct_types": 0,
            "shannon_h": 0.0,
            "simpson_d": 0.0,
            "dominant_type": None,
            "dominance_ratio": 0.0,
            "ext_counts": {},
        }

    total = sum(ext_counter.values())
    H = 0.0
    D = 0.0
    for count in ext_counter.values():
        if count > 0:
            p = count / total
            H -= p * math.log(p)
            D += p * p

    return {
        "distinct_types": len(ext_counter),
        "shannon_h": H,
        "simpson_d": 1.0 - D,
        "dominant_type": ext_counter.most_common(1)[0][0],
        "dominance_ratio": ext_counter.most_common(1)[0][1] / total,
        "ext_counts": dict(ext_counter.most_common()),
    }


# ============================================================
# MARGINAL VALUE THEOREM TEST
# ============================================================

def test_marginal_value_theorem(patches, all_patches_across_sessions=None):
    """Test whether the agent follows the marginal value theorem.

    MVT predicts: the agent should leave a patch when the marginal gain rate
    in that patch drops below the average gain rate across all patches.

    We test this by checking if patches where the agent stayed longer have
    diminishing returns (lower gain rate in the second half).
    """
    results = {
        "total_patches": len(patches),
        "patches_with_edits": 0,
        "patches_diminishing": 0,  # second half gain rate < first half
        "patches_increasing": 0,
        "patches_flat": 0,
        "mean_residence_time": 0,
        "mean_giving_up_time": 0,
        "mvt_support_ratio": 0,
    }

    if not patches:
        return results

    residence_times = [p["residence_time"] for p in patches]
    giving_up_times = [p["giving_up_time"] for p in patches]

    results["mean_residence_time"] = np.mean(residence_times)
    results["median_residence_time"] = float(np.median(residence_times))
    results["mean_giving_up_time"] = np.mean(giving_up_times)
    results["median_giving_up_time"] = float(np.median(giving_up_times))

    for p in patches:
        if p["edits"] > 0:
            results["patches_with_edits"] += 1

        if p["total_events"] >= 4:
            if p["second_half_gain_rate"] < p["first_half_gain_rate"]:
                results["patches_diminishing"] += 1
            elif p["second_half_gain_rate"] > p["first_half_gain_rate"]:
                results["patches_increasing"] += 1
            else:
                results["patches_flat"] += 1

    testable = results["patches_diminishing"] + results["patches_increasing"] + results["patches_flat"]
    if testable > 0:
        results["mvt_support_ratio"] = results["patches_diminishing"] / testable

    # Correlation: do patches with longer residence time have lower gain rate?
    if len(patches) > 5:
        rts = []
        gain_rates = []
        for p in patches:
            if p["residence_time"] > 0:
                rts.append(p["residence_time"])
                gain_rates.append(p["gain"] / p["residence_time"])

        if len(rts) > 5 and np.std(rts) > 0 and np.std(gain_rates) > 0:
            correlation = np.corrcoef(rts, gain_rates)[0, 1]
            results["residence_gainrate_correlation"] = float(correlation)

    return results


# ============================================================
# SESSION-LEVEL FORAGING METRICS
# ============================================================

def compute_session_foraging_metrics(events, patches):
    """Compute session-level foraging metrics."""
    if not events:
        return {}

    diet = compute_diet_breadth(events)
    switching_costs = compute_switching_cost(patches)
    mvt = test_marginal_value_theorem(patches)

    # Patch revisit rate: how often the agent returns to a previously visited directory
    visited_dirs = []
    revisits = 0
    seen = set()
    for p in patches:
        if p["directory"] in seen:
            revisits += 1
        else:
            seen.add(p["directory"])
        visited_dirs.append(p["directory"])

    revisit_rate = revisits / max(len(patches), 1)

    # Foraging efficiency: total edits / total turns
    total_edits = sum(p["edits"] for p in patches)
    total_turns = len(events)
    efficiency = total_edits / max(total_turns, 1)

    # Exploration vs exploitation ratio
    read_events = sum(1 for e in events if e["action_type"] == "read")
    edit_events = sum(1 for e in events if e["action_type"] == "edit")
    explore_exploit_ratio = read_events / max(edit_events, 1)

    return {
        "num_patches": len(patches),
        "num_unique_dirs": len(seen),
        "patch_revisit_rate": revisit_rate,
        "total_edits": total_edits,
        "total_reads": read_events,
        "total_turns": total_turns,
        "foraging_efficiency": efficiency,
        "explore_exploit_ratio": explore_exploit_ratio,
        "diet_breadth": diet,
        "switching_costs": switching_costs,
        "mean_switching_cost": np.mean(switching_costs) if switching_costs else 0,
        "mvt_results": mvt,
        "mean_residence_time": mvt["mean_residence_time"],
        "mean_giving_up_time": mvt["mean_giving_up_time"],
    }


# ============================================================
# LOAD AND PROCESS
# ============================================================

def load_and_process_sessions(max_sessions=MAX_SESSIONS):
    files = _find_jsonl_files(CORPUS_DIR)

    # Filter by size
    sized = [(f, os.path.getsize(f)) for f in files]
    candidates = [(f, s) for f, s in sized if 1_000 < s < 100_000_000]

    # Quick-scan: only keep files with tool_use blocks (Claude Code sessions)
    files_with_tools = []
    for fpath, fsize in candidates:
        tc = 0
        try:
            with open(fpath) as fh:
                for line in fh:
                    if '"tool_use"' in line:
                        tc += 1
                    if tc >= 5:
                        break
        except Exception:
            continue
        if tc >= 5:
            files_with_tools.append((fpath, fsize))

    print(f"  Found {len(files_with_tools)} files with >= 5 tool_use blocks "
          f"(from {len(candidates)} candidates)", file=sys.stderr)

    if len(files_with_tools) > max_sessions:
        random.seed(42)
        files_with_tools = random.sample(files_with_tools, max_sessions)

    candidates = files_with_tools

    sessions = []
    all_patches = []

    for fpath, fsize in candidates:
        messages = parse_session(fpath)
        events = extract_foraging_events(messages)

        if len(events) < 5:
            continue

        user_msgs = extract_user_messages(messages)
        success_score = compute_session_success(messages, user_msgs)

        patches = identify_patches(events)
        if not patches:
            continue

        metrics = compute_session_foraging_metrics(events, patches)

        # Derive project name from directory structure
        parts = Path(fpath).parts
        project_name = "unknown"
        for i, p in enumerate(parts):
            if p in ("projects", "claude-code-live") and i + 1 < len(parts):
                project_name = parts[i + 1]
                break
            if p == "openclaw":
                project_name = "openclaw"
                break
            if p == "archived-cc":
                project_name = "archived-cc"
                break
        project_name = shorten_project_name(project_name)

        sessions.append({
            "filepath": fpath,
            "session_id": os.path.basename(fpath).replace(".jsonl", ""),
            "project": project_name,
            "success_score": success_score,
            "events": events,
            "patches": patches,
            "metrics": metrics,
        })
        all_patches.extend(patches)

    return sessions, all_patches


# ============================================================
# REPORT GENERATION
# ============================================================

def generate_report(sessions, all_patches):
    lines = []
    lines.append("# Information Foraging Theory Analysis")
    lines.append("")
    lines.append("**Date**: 2026-03-20")
    lines.append("**Method**: Model agent behavior as information foraging (Pirolli & Card, 1999)")
    lines.append(f"**Corpus**: {len(sessions)} sessions from third-thoughts corpus")
    lines.append(f"**Total foraging events**: {sum(len(s['events']) for s in sessions):,}")
    lines.append(f"**Total patches identified**: {len(all_patches):,}")
    lines.append("")
    lines.append("**Reference**: Pirolli, P. & Card, S. (1999). \"Information Foraging.\" "
                 "Psychological Review, 106(4).")
    lines.append("")
    lines.append("---")
    lines.append("")

    # ── Patch Residence Time ──
    lines.append("## 1. Patch Residence Time Distribution")
    lines.append("")
    lines.append("A 'patch' is a directory the agent explores. Residence time = number of")
    lines.append("consecutive tool calls in that directory before switching.")
    lines.append("")

    residence_times = [p["residence_time"] for p in all_patches]
    rt_arr = np.array(residence_times)

    lines.append(f"| Metric | Value |")
    lines.append(f"|--------|-------|")
    lines.append(f"| Total patches | {len(all_patches):,} |")
    lines.append(f"| Mean residence time | {rt_arr.mean():.2f} turns |")
    lines.append(f"| Median residence time | {np.median(rt_arr):.1f} turns |")
    lines.append(f"| Std deviation | {rt_arr.std():.2f} |")
    lines.append(f"| Min | {rt_arr.min()} |")
    lines.append(f"| Max | {rt_arr.max()} |")
    lines.append(f"| 25th percentile | {np.percentile(rt_arr, 25):.1f} |")
    lines.append(f"| 75th percentile | {np.percentile(rt_arr, 75):.1f} |")
    lines.append(f"| 90th percentile | {np.percentile(rt_arr, 90):.1f} |")
    lines.append("")

    # Histogram (text-based)
    lines.append("### Residence Time Histogram")
    lines.append("")
    bins = [(1, 1), (2, 2), (3, 3), (4, 5), (6, 10), (11, 20), (21, 50), (51, 100), (101, 999)]
    lines.append("```")
    lines.append(f"{'Range':>10}  {'Count':>6}  {'%':>5}  Distribution")
    lines.append(f"{'-'*10}  {'-'*6}  {'-'*5}  {'-'*40}")
    max_count = max(sum(1 for r in residence_times if lo <= r <= hi) for lo, hi in bins)
    for lo, hi in bins:
        count = sum(1 for r in residence_times if lo <= r <= hi)
        if count == 0:
            continue
        pct = count / len(residence_times) * 100
        bar = "#" * int(count / max(max_count, 1) * 35)
        label = f"{lo}" if lo == hi else f"{lo}-{hi}"
        lines.append(f"{label:>10}  {count:>6}  {pct:>4.1f}%  |{bar}")
    lines.append("```")
    lines.append("")

    # Patches with vs without edits
    patches_with_edits = [p for p in all_patches if p["edits"] > 0]
    patches_without_edits = [p for p in all_patches if p["edits"] == 0]

    lines.append("### Patches With vs Without Edits")
    lines.append("")
    lines.append("| Type | Count | % | Mean Residence | Mean Reads |")
    lines.append("|------|-------|---|----------------|------------|")
    if patches_with_edits:
        lines.append(f"| With edits | {len(patches_with_edits)} | "
                     f"{len(patches_with_edits)/len(all_patches)*100:.1f}% | "
                     f"{np.mean([p['residence_time'] for p in patches_with_edits]):.2f} | "
                     f"{np.mean([p['reads'] for p in patches_with_edits]):.2f} |")
    if patches_without_edits:
        lines.append(f"| Without edits (exploration only) | {len(patches_without_edits)} | "
                     f"{len(patches_without_edits)/len(all_patches)*100:.1f}% | "
                     f"{np.mean([p['residence_time'] for p in patches_without_edits]):.2f} | "
                     f"{np.mean([p['reads'] for p in patches_without_edits]):.2f} |")
    lines.append("")

    # ── Giving-Up Time ──
    lines.append("---")
    lines.append("")
    lines.append("## 2. Giving-Up Time")
    lines.append("")
    lines.append("How many turns does the agent stay in a patch after its last edit?")
    lines.append("In foraging theory, a short giving-up time indicates an efficient forager")
    lines.append("that quickly moves on when returns diminish.")
    lines.append("")

    gut_values = [p["giving_up_time"] for p in patches_with_edits] if patches_with_edits else []
    if gut_values:
        gut_arr = np.array(gut_values)
        lines.append(f"| Metric | Value |")
        lines.append(f"|--------|-------|")
        lines.append(f"| Mean giving-up time | {gut_arr.mean():.2f} turns |")
        lines.append(f"| Median giving-up time | {np.median(gut_arr):.1f} turns |")
        lines.append(f"| Patches where agent left immediately after last edit | "
                     f"{sum(1 for g in gut_values if g == 0)} ({sum(1 for g in gut_values if g == 0)/len(gut_values)*100:.1f}%) |")
        lines.append(f"| Patches where agent lingered 1-3 turns | "
                     f"{sum(1 for g in gut_values if 1 <= g <= 3)} ({sum(1 for g in gut_values if 1 <= g <= 3)/len(gut_values)*100:.1f}%) |")
        lines.append(f"| Patches where agent lingered >5 turns | "
                     f"{sum(1 for g in gut_values if g > 5)} ({sum(1 for g in gut_values if g > 5)/len(gut_values)*100:.1f}%) |")
        lines.append("")
    else:
        lines.append("No patches with edits found for giving-up time analysis.")
        lines.append("")

    # ── Marginal Value Theorem ──
    lines.append("---")
    lines.append("")
    lines.append("## 3. Marginal Value Theorem Test")
    lines.append("")
    lines.append("The MVT predicts that an optimal forager leaves a patch when the marginal")
    lines.append("gain rate drops below the average gain rate across all patches.")
    lines.append("")
    lines.append("We test this by checking whether the gain rate (edits/turn) in the second")
    lines.append("half of a patch visit is lower than in the first half (diminishing returns).")
    lines.append("")

    # Aggregate MVT results
    all_mvt = defaultdict(list)
    for s in sessions:
        mvt = s["metrics"].get("mvt_results", {})
        for k, v in mvt.items():
            if isinstance(v, (int, float)):
                all_mvt[k].append(v)

    testable_patches = sum(1 for p in all_patches if p["total_events"] >= 4)
    diminishing_patches = sum(1 for p in all_patches
                              if p["total_events"] >= 4
                              and p["second_half_gain_rate"] < p["first_half_gain_rate"])
    increasing_patches = sum(1 for p in all_patches
                             if p["total_events"] >= 4
                             and p["second_half_gain_rate"] > p["first_half_gain_rate"])
    flat_patches = sum(1 for p in all_patches
                       if p["total_events"] >= 4
                       and p["second_half_gain_rate"] == p["first_half_gain_rate"])

    lines.append(f"| Metric | Value |")
    lines.append(f"|--------|-------|")
    lines.append(f"| Testable patches (>= 4 events) | {testable_patches} |")
    lines.append(f"| Diminishing returns (supports MVT) | {diminishing_patches} ({diminishing_patches/max(testable_patches,1)*100:.1f}%) |")
    lines.append(f"| Increasing returns (contradicts MVT) | {increasing_patches} ({increasing_patches/max(testable_patches,1)*100:.1f}%) |")
    lines.append(f"| Flat (no change) | {flat_patches} ({flat_patches/max(testable_patches,1)*100:.1f}%) |")
    lines.append("")

    if testable_patches > 0:
        support_ratio = diminishing_patches / max(diminishing_patches + increasing_patches, 1)
        if support_ratio > 0.6:
            lines.append(f"**Conclusion**: MVT is **supported** (ratio: {support_ratio:.2f}). "
                         "The agent tends to experience diminishing returns within patches "
                         "and typically moves on, consistent with optimal foraging behavior.")
        elif support_ratio > 0.4:
            lines.append(f"**Conclusion**: MVT is **weakly supported** (ratio: {support_ratio:.2f}). "
                         "The agent shows mixed behavior -- sometimes diminishing, sometimes "
                         "increasing returns within patches.")
        else:
            lines.append(f"**Conclusion**: MVT is **not supported** (ratio: {support_ratio:.2f}). "
                         "The agent often finds increasing returns later in patches, "
                         "suggesting it may be under-exploring initially.")
        lines.append("")

    # Correlation between residence time and gain rate
    rts = []
    gain_rates = []
    for p in all_patches:
        if p["residence_time"] > 0:
            rts.append(p["residence_time"])
            gain_rates.append(p["gain"] / p["residence_time"])
    if len(rts) > 10:
        corr = np.corrcoef(rts, gain_rates)[0, 1]
        lines.append(f"### Residence Time vs Gain Rate Correlation")
        lines.append("")
        lines.append(f"Pearson r = {corr:.3f}")
        lines.append("")
        if corr < -0.2:
            lines.append("Negative correlation: longer stays produce diminishing per-turn gains, "
                         "consistent with MVT expectations.")
        elif corr > 0.2:
            lines.append("Positive correlation: longer stays produce HIGHER per-turn gains, "
                         "suggesting the agent benefits from deeper exploration.")
        else:
            lines.append("Near-zero correlation: residence time is largely independent of gain rate.")
        lines.append("")

    # ── Diet Breadth ──
    lines.append("---")
    lines.append("")
    lines.append("## 4. Diet Breadth (File Type Diversity)")
    lines.append("")
    lines.append("In foraging theory, diet breadth is the range of prey types a forager exploits.")
    lines.append("Here, each file extension represents a 'prey type'.")
    lines.append("")

    diet_breadths = [s["metrics"]["diet_breadth"] for s in sessions]
    distinct_types = [d["distinct_types"] for d in diet_breadths]
    shannon_hs = [d["shannon_h"] for d in diet_breadths if d["distinct_types"] > 0]

    if distinct_types:
        lines.append(f"| Metric | Value |")
        lines.append(f"|--------|-------|")
        lines.append(f"| Mean distinct file types per session | {np.mean(distinct_types):.2f} |")
        lines.append(f"| Median distinct file types | {np.median(distinct_types):.1f} |")
        lines.append(f"| Max distinct file types | {max(distinct_types)} |")
        if shannon_hs:
            lines.append(f"| Mean Shannon H (diet diversity) | {np.mean(shannon_hs):.3f} |")
        lines.append("")

    # Aggregate file extension frequency
    all_ext_counts = Counter()
    for d in diet_breadths:
        all_ext_counts.update(d.get("ext_counts", {}))

    if all_ext_counts:
        lines.append("### Most Common File Types (Prey)")
        lines.append("")
        lines.append("| File Type | Count | % |")
        lines.append("|-----------|-------|---|")
        total_ext = sum(all_ext_counts.values())
        for ext, count in all_ext_counts.most_common(15):
            lines.append(f"| {ext} | {count:,} | {count/total_ext*100:.1f}% |")
        lines.append("")

    # Diet breadth vs success
    if len(sessions) > 10:
        scores = [s["success_score"] for s in sessions]
        dtypes = [s["metrics"]["diet_breadth"]["distinct_types"] for s in sessions]
        if np.std(scores) > 0 and np.std(dtypes) > 0:
            corr = np.corrcoef(scores, dtypes)[0, 1]
            lines.append(f"### Diet Breadth vs Success Score")
            lines.append("")
            lines.append(f"Pearson r = {corr:.3f}")
            lines.append("")
            if abs(corr) > 0.15:
                direction = "broader" if corr > 0 else "narrower"
                lines.append(f"Sessions with {direction} diet breadth tend to have "
                             f"{'higher' if corr > 0 else 'lower'} success scores.")
            else:
                lines.append("Diet breadth shows minimal correlation with session success.")
            lines.append("")

    # ── Switching Cost ──
    lines.append("---")
    lines.append("")
    lines.append("## 5. Switching Cost Between Patches")
    lines.append("")
    lines.append("How many 'between-patch' tool calls (Bash, etc.) occur between patch visits?")
    lines.append("High switching cost indicates expensive context changes.")
    lines.append("")

    all_switch_costs = []
    for s in sessions:
        all_switch_costs.extend(s["metrics"].get("switching_costs", []))

    if all_switch_costs:
        sc_arr = np.array(all_switch_costs)
        lines.append(f"| Metric | Value |")
        lines.append(f"|--------|-------|")
        lines.append(f"| Mean switching cost | {sc_arr.mean():.2f} tool calls |")
        lines.append(f"| Median switching cost | {np.median(sc_arr):.1f} |")
        lines.append(f"| Zero-cost switches (immediate) | {sum(1 for c in all_switch_costs if c == 0)} ({sum(1 for c in all_switch_costs if c == 0)/len(all_switch_costs)*100:.1f}%) |")
        lines.append(f"| High-cost switches (>5) | {sum(1 for c in all_switch_costs if c > 5)} ({sum(1 for c in all_switch_costs if c > 5)/len(all_switch_costs)*100:.1f}%) |")
        lines.append("")

    # ── Exploration vs Exploitation ──
    lines.append("---")
    lines.append("")
    lines.append("## 6. Exploration vs Exploitation")
    lines.append("")
    lines.append("Foraging theory distinguishes between exploration (searching for new patches)")
    lines.append("and exploitation (extracting value from a known patch).")
    lines.append("")

    ee_ratios = [s["metrics"]["explore_exploit_ratio"] for s in sessions if s["metrics"].get("explore_exploit_ratio")]
    efficiencies = [s["metrics"]["foraging_efficiency"] for s in sessions]
    revisit_rates = [s["metrics"]["patch_revisit_rate"] for s in sessions]

    if ee_ratios:
        lines.append(f"| Metric | Mean | Median | Std |")
        lines.append(f"|--------|------|--------|-----|")
        lines.append(f"| Explore/Exploit ratio (reads/edits) | {np.mean(ee_ratios):.2f} | {np.median(ee_ratios):.2f} | {np.std(ee_ratios):.2f} |")
        lines.append(f"| Foraging efficiency (edits/turn) | {np.mean(efficiencies):.3f} | {np.median(efficiencies):.3f} | {np.std(efficiencies):.3f} |")
        lines.append(f"| Patch revisit rate | {np.mean(revisit_rates):.3f} | {np.median(revisit_rates):.3f} | {np.std(revisit_rates):.3f} |")
        lines.append("")

    # Efficiency vs success
    if len(sessions) > 10:
        scores = [s["success_score"] for s in sessions]
        effs = [s["metrics"]["foraging_efficiency"] for s in sessions]
        if np.std(scores) > 0 and np.std(effs) > 0:
            corr = np.corrcoef(scores, effs)[0, 1]
            lines.append(f"### Foraging Efficiency vs Success")
            lines.append("")
            lines.append(f"Pearson r = {corr:.3f}")
            lines.append("")
            if corr > 0.15:
                lines.append("More efficient foragers (higher edit rate per turn) tend to have "
                             "more successful sessions.")
            elif corr < -0.15:
                lines.append("Higher efficiency correlates with lower success -- possibly because "
                             "editing too quickly without sufficient exploration leads to errors.")
            else:
                lines.append("Foraging efficiency shows minimal correlation with success score.")
            lines.append("")

    # ── Cross-Project Comparison ──
    lines.append("---")
    lines.append("")
    lines.append("## 7. Cross-Project Foraging Comparison")
    lines.append("")

    project_metrics = defaultdict(list)
    for s in sessions:
        project_metrics[s["project"]].append(s["metrics"])

    # Only projects with >= 3 sessions
    project_metrics = {p: ms for p, ms in project_metrics.items() if len(ms) >= 3}

    if project_metrics:
        lines.append("| Project | Sessions | Mean Patches | Mean Residence | Mean Efficiency | Mean Diet Breadth | Mean Revisit Rate |")
        lines.append("|---------|----------|-------------|----------------|-----------------|-------------------|-------------------|")

        for proj in sorted(project_metrics.keys()):
            ms = project_metrics[proj]
            lines.append(
                f"| {proj[:25]} | {len(ms)} | "
                f"{np.mean([m['num_patches'] for m in ms]):.1f} | "
                f"{np.mean([m['mean_residence_time'] for m in ms]):.2f} | "
                f"{np.mean([m['foraging_efficiency'] for m in ms]):.3f} | "
                f"{np.mean([m['diet_breadth']['distinct_types'] for m in ms]):.1f} | "
                f"{np.mean([m['patch_revisit_rate'] for m in ms]):.3f} |"
            )
        lines.append("")

        # Most efficient vs least efficient projects
        proj_efficiency = {
            p: np.mean([m["foraging_efficiency"] for m in ms])
            for p, ms in project_metrics.items()
        }
        sorted_projs = sorted(proj_efficiency.items(), key=lambda x: -x[1])

        lines.append("### Projects Ranked by Foraging Efficiency")
        lines.append("")
        lines.append("| Rank | Project | Efficiency | Interpretation |")
        lines.append("|------|---------|-----------|----------------|")
        for i, (proj, eff) in enumerate(sorted_projs):
            if eff > 0.15:
                interp = "High exploitation (edit-heavy)"
            elif eff > 0.05:
                interp = "Balanced foraging"
            else:
                interp = "Heavy exploration"
            lines.append(f"| {i+1} | {proj[:25]} | {eff:.3f} | {interp} |")
        lines.append("")

    # ── Success Quartile Comparison ──
    lines.append("---")
    lines.append("")
    lines.append("## 8. Foraging Metrics by Session Success")
    lines.append("")

    scores_sorted = sorted(sessions, key=lambda x: x["success_score"])
    n = len(scores_sorted)
    q1_sessions = scores_sorted[:n//4]
    q4_sessions = scores_sorted[3*n//4:]

    if q1_sessions and q4_sessions:
        lines.append("| Metric | Low Success (Q1) | High Success (Q4) | Delta |")
        lines.append("|--------|-----------------|-------------------|-------|")

        metrics_to_compare = [
            ("Mean patches per session", "num_patches"),
            ("Mean residence time", "mean_residence_time"),
            ("Foraging efficiency", "foraging_efficiency"),
            ("Explore/exploit ratio", "explore_exploit_ratio"),
            ("Patch revisit rate", "patch_revisit_rate"),
            ("Mean switching cost", "mean_switching_cost"),
        ]

        for label, key in metrics_to_compare:
            q1_vals = [s["metrics"].get(key, 0) for s in q1_sessions]
            q4_vals = [s["metrics"].get(key, 0) for s in q4_sessions]
            q1_mean = np.mean(q1_vals) if q1_vals else 0
            q4_mean = np.mean(q4_vals) if q4_vals else 0
            delta = q4_mean - q1_mean
            lines.append(f"| {label} | {q1_mean:.3f} | {q4_mean:.3f} | {delta:+.3f} |")

        # Diet breadth comparison
        q1_diet = [s["metrics"]["diet_breadth"]["distinct_types"] for s in q1_sessions]
        q4_diet = [s["metrics"]["diet_breadth"]["distinct_types"] for s in q4_sessions]
        lines.append(f"| Diet breadth (distinct types) | {np.mean(q1_diet):.1f} | "
                     f"{np.mean(q4_diet):.1f} | {np.mean(q4_diet)-np.mean(q1_diet):+.1f} |")

        lines.append("")

        # Interpretation
        lines.append("### Interpretation")
        lines.append("")
        eff_q1 = np.mean([s["metrics"]["foraging_efficiency"] for s in q1_sessions])
        eff_q4 = np.mean([s["metrics"]["foraging_efficiency"] for s in q4_sessions])
        if eff_q4 > eff_q1 * 1.2:
            lines.append("Successful sessions show **higher foraging efficiency** -- the agent ")
            lines.append("makes more edits per tool call, suggesting more targeted exploration.")
        elif eff_q1 > eff_q4 * 1.2:
            lines.append("Struggling sessions show higher raw efficiency, likely because they ")
            lines.append("involve more repetitive edits (corrections, reverts) without purposeful exploration.")
        else:
            lines.append("Foraging efficiency is similar across success quartiles.")
        lines.append("")

        rt_q1 = np.mean([s["metrics"]["mean_residence_time"] for s in q1_sessions])
        rt_q4 = np.mean([s["metrics"]["mean_residence_time"] for s in q4_sessions])
        if rt_q4 > rt_q1 * 1.2:
            lines.append("Successful sessions have **longer patch residence** -- the agent explores ")
            lines.append("patches more thoroughly before moving on.")
        elif rt_q1 > rt_q4 * 1.2:
            lines.append("Struggling sessions have **longer patch residence** -- the agent may be ")
            lines.append("getting stuck in patches, failing to find what it needs and continuing to search.")
        else:
            lines.append("Patch residence times are similar across success quartiles.")
        lines.append("")

    # ── Summary ──
    lines.append("---")
    lines.append("")
    lines.append("## Summary of Key Findings")
    lines.append("")

    lines.append(f"1. **Patch statistics**: {len(all_patches):,} patches identified across "
                 f"{len(sessions)} sessions. Mean residence time: {np.mean([p['residence_time'] for p in all_patches]):.2f} turns.")
    lines.append("")

    if patches_with_edits:
        lines.append(f"2. **Productive patches**: {len(patches_with_edits)/len(all_patches)*100:.1f}% of patches "
                     f"result in edits. The remaining {len(patches_without_edits)/len(all_patches)*100:.1f}% are "
                     f"exploration-only visits.")
        lines.append("")

    if gut_values:
        lines.append(f"3. **Giving-up time**: Mean {np.mean(gut_values):.2f} turns after last edit. "
                     f"{sum(1 for g in gut_values if g == 0)/len(gut_values)*100:.0f}% of the time the agent "
                     f"leaves immediately after editing.")
        lines.append("")

    if testable_patches > 0:
        lines.append(f"4. **Marginal Value Theorem**: "
                     f"{'Supported' if diminishing_patches / max(diminishing_patches + increasing_patches, 1) > 0.5 else 'Not supported'} "
                     f"({diminishing_patches}/{testable_patches} patches show diminishing returns).")
        lines.append("")

    if ee_ratios:
        lines.append(f"5. **Explore/exploit balance**: Mean ratio {np.mean(ee_ratios):.2f} "
                     f"(reads per edit). "
                     f"{'The agent reads significantly more than it edits.' if np.mean(ee_ratios) > 3 else 'Relatively balanced reading and editing.' if np.mean(ee_ratios) < 2 else 'Moderate exploration before exploitation.'}")
        lines.append("")

    lines.append(f"6. **Foraging efficiency**: Mean {np.mean(efficiencies):.3f} edits per tool call. "
                 f"Sessions are predominantly exploratory with targeted edits.")
    lines.append("")

    return "\n".join(lines)


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    print("Loading and processing sessions...", file=sys.stderr)
    sessions, all_patches = load_and_process_sessions(max_sessions=MAX_SESSIONS)
    print(f"Processed {len(sessions)} sessions, {len(all_patches)} patches", file=sys.stderr)

    print("Generating report...", file=sys.stderr)
    report = generate_report(sessions, all_patches)

    # Write markdown report
    report_path = OUTPUT_DIR / "information-foraging.md"
    with open(report_path, "w") as f:
        f.write(report)
    print(f"Report written to {report_path}", file=sys.stderr)

    # Write JSON data
    json_output = {
        "sessions_analyzed": len(sessions),
        "total_patches": len(all_patches),
        "total_events": sum(len(s["events"]) for s in sessions),
        "aggregate_metrics": {
            "mean_residence_time": float(np.mean([p["residence_time"] for p in all_patches])),
            "mean_giving_up_time": float(np.mean([p["giving_up_time"] for p in all_patches])),
            "mean_foraging_efficiency": float(np.mean([s["metrics"]["foraging_efficiency"] for s in sessions])),
            "mean_explore_exploit_ratio": float(np.mean([s["metrics"]["explore_exploit_ratio"] for s in sessions])),
            "mean_diet_breadth": float(np.mean([s["metrics"]["diet_breadth"]["distinct_types"] for s in sessions])),
            "mean_patch_revisit_rate": float(np.mean([s["metrics"]["patch_revisit_rate"] for s in sessions])),
            "pct_patches_with_edits": float(sum(1 for p in all_patches if p["edits"] > 0) / max(len(all_patches), 1) * 100),
        },
        "per_session": [
            {
                "session_id": s["session_id"],
                "project": s["project"],
                "success_score": s["success_score"],
                "num_patches": s["metrics"]["num_patches"],
                "foraging_efficiency": s["metrics"]["foraging_efficiency"],
                "explore_exploit_ratio": s["metrics"]["explore_exploit_ratio"],
                "diet_breadth": s["metrics"]["diet_breadth"]["distinct_types"],
                "mean_residence_time": s["metrics"]["mean_residence_time"],
                "patch_revisit_rate": s["metrics"]["patch_revisit_rate"],
            }
            for s in sessions
        ],
    }

    json_path = OUTPUT_DIR / "information-foraging.json"
    with open(json_path, "w") as f:
        json.dump(json_output, f, indent=2, default=str)
    print(f"JSON data written to {json_path}", file=sys.stderr)
