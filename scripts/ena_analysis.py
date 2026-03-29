#!/usr/bin/env python3
"""
Epistemic Network Analysis (ENA) of Claude Code agent sessions.
Adapted for Third Thoughts corpus.

Applies ENA methodology from education research to map knowledge element
co-occurrence in agent sessions. Identifies which epistemic codes cluster
together in successful vs struggling sessions.
"""

import json
import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
import itertools
import math

# --- Configuration ---

CORPUS_ROOT = Path(os.environ.get("MIDDENS_CORPUS", "corpus/"))
OUTPUT_DIR = Path(os.environ.get("MIDDENS_OUTPUT", "experiments/"))

# --- Epistemic Code Definitions (keyword-based) ---

EPISTEMIC_CODES = {
    "PLANNING": [
        r"\bplan\b", r"\bapproach\b", r"\bstrategy\b", r"\bconsider\b",
        r"\boption\b", r"\bstep\s*\d", r"\bfirst\b.*\bthen\b", r"\bphase\b",
        r"\broadmap\b", r"\bsequence\b", r"\bprioritiz", r"\bnext\s+step",
        r"\bbreak.*down\b", r"\btackle\b", r"\bworkflow\b",
    ],
    "DEBUGGING": [
        r"\berror\b", r"\bfix\b", r"\bbug\b", r"\bfail", r"\bwrong\b",
        r"\bissue\b", r"\bproblem\b", r"\btraceback\b", r"\bexception\b",
        r"\bcrash", r"\bbroken\b", r"\bregress", r"\bstack\s*trace",
        r"\bunexpect", r"\bnot\s+work", r"\bdoesn'?t\s+work",
    ],
    "ARCHITECTURE": [
        r"\bpattern\b", r"\bstructure\b", r"\bdesign\b", r"\bmodule\b",
        r"\bcomponent\b", r"\binterface\b", r"\babstract", r"\barchitect",
        r"\blayer\b", r"\bdecouple", r"\bseparation\b", r"\bencapsulat",
        r"\brefactor", r"\bdependenc", r"\binject", r"\bsingleton\b",
        r"\bfactory\b", r"\bmiddleware\b", r"\bschema\b",
    ],
    "VERIFICATION": [
        r"\btest\b", r"\bcheck\b", r"\bverif", r"\bconfirm\b", r"\bassert\b",
        r"\bvalidat", r"\bexpect\b", r"\bshould\b", r"\bpass(?:es|ed|ing)?\b",
        r"\bspec\b", r"\bcoverage\b", r"\bintegration\s+test",
        r"\bunit\s+test", r"\be2e\b", r"\bsanity\b",
    ],
    "TOOL_KNOWLEDGE": [
        r"\bgit\s+(status|diff|log|add|commit|push|pull|rebase|merge|stash|checkout|branch|reset)\b",
        r"\bnpm\b", r"\bpnpm\b", r"\byarn\b", r"\bcargo\b", r"\bpip\b",
        r"\b--[a-z][-a-z]+\b",
        r"\bAPI\b", r"\bREST\b", r"\bGraphQL\b", r"\bwebhook\b",
        r"\bcurl\b", r"\bfetch\b", r"\bgrep\b", r"\bsed\b", r"\bawk\b",
        r"\bdocker\b", r"\bkubernetes\b", r"\bk8s\b",
    ],
    "DOMAIN_KNOWLEDGE": [
        r"\bbusiness\s+logic\b", r"\brequirement\b", r"\buse\s*case\b",
        r"\buser\s+stor", r"\bfeature\b", r"\bspec(?:ification)?\b",
        r"\bendpoint\b", r"\broute\b", r"\bmodel\b", r"\bmigrat",
        r"\bdatabase\b", r"\bquery\b", r"\bORM\b", r"\brelation",
        r"\bpayload\b", r"\bresponse\b", r"\brequest\b",
    ],
    "META_COGNITION": [
        r"\bI think\b", r"\bI believe\b", r"\bnot sure\b", r"\buncertain\b",
        r"\balternative", r"\btrade-?off\b", r"\bpros?\s+and\s+cons?\b",
        r"\bactually\b", r"\bwait\b", r"\blet me reconsider\b",
        r"\bon second thought\b", r"\bmight be\b", r"\bcould be\b",
        r"\bpossib", r"\brethink", r"\brevisit", r"\bdilemma\b",
        r"\bhmmm?\b", r"\binteresting\b",
    ],
    "COLLABORATION": [
        r"\byou\b", r"\bwe\b", r"\blet'?s\b", r"\bshall\b", r"\bapproval\b",
        r"\bquestion\b", r"\bwhat do you think\b", r"\bwould you\b",
        r"\bshould I\b", r"\bdo you want\b", r"\bprefer\b", r"\bagree\b",
        r"\btogether\b", r"\bfeedback\b", r"\bsuggestion\b",
    ],
}

COMPILED_CODES = {
    code: [re.compile(p, re.IGNORECASE) for p in patterns]
    for code, patterns in EPISTEMIC_CODES.items()
}


def code_text(text):
    """Return set of epistemic codes present in a text."""
    present = set()
    text_lower = text.lower()
    for code, patterns in COMPILED_CODES.items():
        for pat in patterns:
            if pat.search(text_lower) or pat.search(text):
                present.add(code)
                break
    return present


# --- Data Loading ---

def extract_text_from_message(obj):
    """Extract text content from a JSONL message object."""
    msg = obj.get("message", {})
    if not isinstance(msg, dict):
        return ""
    content = msg.get("content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                if "text" in block:
                    parts.append(block["text"])
                elif block.get("type") == "tool_use":
                    parts.append(f"tool:{block.get('name', '')}")
                    inp = block.get("input", {})
                    if isinstance(inp, dict):
                        cmd = inp.get("command", "")
                        if cmd:
                            parts.append(cmd)
                elif block.get("type") == "tool_result":
                    parts.append("[tool_result]")
        return " ".join(parts)
    return ""


def load_session(filepath):
    """Load a session file and return list of (role, text, codes) turns."""
    turns = []
    try:
        with open(filepath, "r", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                msg_type = obj.get("type", "")
                if msg_type not in ("user", "assistant"):
                    continue
                text = extract_text_from_message(obj)
                if len(text) < 10:
                    continue
                role = msg_type
                codes = code_text(text)
                turns.append({
                    "role": role,
                    "text": text,
                    "codes": codes,
                    "text_len": len(text),
                })
    except Exception as e:
        print(f"  Error loading {filepath}: {e}", file=sys.stderr)
    return turns


def compute_session_metrics(turns):
    """Compute metrics for a session including correction rate."""
    if not turns:
        return {}

    user_turns = [t for t in turns if t["role"] == "user"]
    assistant_turns = [t for t in turns if t["role"] == "assistant"]

    correction_keywords = [
        re.compile(p, re.IGNORECASE) for p in [
            r"\bno\b,?\s*(that'?s|it'?s)?\s*(not|wrong)",
            r"\bactually\b", r"\binstead\b", r"\bretry\b",
            r"\btry again\b", r"\bnot what I", r"\bwrong\b",
            r"\bundo\b", r"\brevert\b", r"\bgo back\b",
            r"\bstop\b", r"\bwait\b,?\s*(no|don'?t|stop)",
            r"\byou (missed|forgot|overlooked|broke|ignored)\b",
            r"\bthat broke\b", r"\bdidn'?t work\b",
        ]
    ]
    corrections = 0
    for t in user_turns:
        for pat in correction_keywords:
            if pat.search(t["text"]):
                corrections += 1
                break

    correction_rate = corrections / max(len(user_turns), 1)

    code_freq = Counter()
    for t in turns:
        for c in t["codes"]:
            code_freq[c] += 1

    return {
        "total_turns": len(turns),
        "user_turns": len(user_turns),
        "assistant_turns": len(assistant_turns),
        "corrections": corrections,
        "correction_rate": correction_rate,
        "code_freq": dict(code_freq),
        "avg_text_len": sum(t["text_len"] for t in turns) / len(turns),
    }


# --- Co-occurrence Networks ---

ALL_CODES = sorted(EPISTEMIC_CODES.keys())
CODE_INDEX = {c: i for i, c in enumerate(ALL_CODES)}


def build_cooccurrence_matrix(turns, window_size=5):
    """Build adjacency matrix from sliding window co-occurrence."""
    n = len(ALL_CODES)
    matrix = [[0.0] * n for _ in range(n)]

    if len(turns) < 2:
        return matrix

    for start in range(len(turns) - window_size + 1):
        window = turns[start:start + window_size]
        codes_in_window = set()
        for t in window:
            codes_in_window |= t["codes"]
        codes_list = sorted(codes_in_window)
        for i, c1 in enumerate(codes_list):
            for c2 in codes_list[i + 1:]:
                idx1 = CODE_INDEX[c1]
                idx2 = CODE_INDEX[c2]
                matrix[idx1][idx2] += 1
                matrix[idx2][idx1] += 1

    num_windows = max(len(turns) - window_size + 1, 1)
    for i in range(n):
        for j in range(n):
            matrix[i][j] /= num_windows

    return matrix


def add_matrices(m1, m2):
    n = len(m1)
    return [[m1[i][j] + m2[i][j] for j in range(n)] for i in range(n)]


def scale_matrix(m, scalar):
    n = len(m)
    return [[m[i][j] * scalar for j in range(n)] for i in range(n)]


def subtract_matrices(m1, m2):
    n = len(m1)
    return [[m1[i][j] - m2[i][j] for j in range(n)] for i in range(n)]


def compute_centrality(matrix):
    n = len(matrix)
    centrality = {}
    for i in range(n):
        total_weight = sum(matrix[i][j] for j in range(n))
        centrality[ALL_CODES[i]] = total_weight
    max_val = max(centrality.values()) if centrality.values() else 1
    if max_val > 0:
        centrality = {k: v / max_val for k, v in centrality.items()}
    return centrality


def format_matrix(matrix, top_n=10):
    pairs = []
    n = len(matrix)
    for i in range(n):
        for j in range(i + 1, n):
            if matrix[i][j] > 0:
                pairs.append((ALL_CODES[i], ALL_CODES[j], matrix[i][j]))
    pairs.sort(key=lambda x: -x[2])
    lines = []
    for c1, c2, weight in pairs[:top_n]:
        lines.append(f"  {c1} <-> {c2}: {weight:.3f}")
    return "\n".join(lines)


# --- Session Discovery ---

def find_session_files():
    """Find all JSONL session files in the corpus (follows symlinks)."""
    sessions = []

    for root, dirs, fnames in os.walk(str(CORPUS_ROOT), followlinks=True):
        for fname in fnames:
            if not fname.endswith(".jsonl"):
                continue
            fn = Path(os.path.join(root, fname))
            size = fn.stat().st_size
            # Extract project from path
            parts = str(fn).split("/")
            project_name = fn.parent.name
            for i, p in enumerate(parts):
                if p == "projects" and i + 1 < len(parts):
                    project_name = parts[i + 1].lstrip("-")
                    # Simplify
                    pp = project_name.split("-")
                    for j, q in enumerate(pp):
                        if q.lower() == "projects":
                            project_name = "-".join(pp[j + 1:]) or project_name
                            break
                    break
            sessions.append({
                "path": str(fn),
                "project": project_name,
                "session_id": fn.stem,
                "size": size,
            })

    return sessions


def select_sample(sessions, n=40):
    """Select a diverse sample of sessions."""
    viable = [s for s in sessions if 5_000 < s["size"] < 50_000_000]
    viable.sort(key=lambda s: -s["size"])

    by_project = defaultdict(list)
    for s in viable:
        by_project[s["project"]].append(s)

    selected = []
    projects = sorted(by_project.keys())
    idx = {p: 0 for p in projects}
    while len(selected) < n:
        added = False
        for p in projects:
            if idx[p] < len(by_project[p]) and len(selected) < n:
                selected.append(by_project[p][idx[p]])
                idx[p] += 1
                added = True
        if not added:
            break

    return selected


def main():
    print("=" * 70)
    print("EPISTEMIC NETWORK ANALYSIS OF AGENT SESSIONS")
    print("(Third Thoughts Corpus)")
    print("=" * 70)

    # Find and sample sessions
    print("\n[1] Finding session files...")
    all_sessions = find_session_files()
    if not all_sessions:
        print("ERROR: No session files found! Check corpus path and symlinks.")
        sys.exit(1)
    print(f"  Found {len(all_sessions)} total sessions across "
          f"{len(set(s['project'] for s in all_sessions))} projects")

    sample = select_sample(all_sessions, n=200)
    if not sample:
        print("ERROR: No sessions passed filtering. Check file size constraints.")
        sys.exit(1)
    print(f"  Selected {len(sample)} sessions for analysis")
    print(f"  Projects represented: {sorted(set(s['project'] for s in sample))}")

    # Load and code all sessions
    print("\n[2] Loading and coding sessions...")
    session_data = []
    for i, sess_info in enumerate(sample):
        turns = load_session(sess_info["path"])
        if len(turns) < 4:
            continue
        metrics = compute_session_metrics(turns)
        cooc_matrix = build_cooccurrence_matrix(turns, window_size=5)

        session_data.append({
            **sess_info,
            "turns": turns,
            "metrics": metrics,
            "cooc_matrix": cooc_matrix,
        })
        if (i + 1) % 10 == 0:
            print(f"  Processed {i + 1}/{len(sample)} sessions...")

    print(f"  Successfully analyzed {len(session_data)} sessions "
          f"(dropped {len(sample) - len(session_data)} with <4 turns)")

    if not session_data:
        print("ERROR: No sessions survived filtering. Cannot proceed with analysis.")
        sys.exit(1)

    # Analysis 1: Code Distribution
    print("\n" + "=" * 70)
    print("ANALYSIS 1: EPISTEMIC CODE DISTRIBUTION")
    print("=" * 70)

    total_code_freq = Counter()
    total_turns = 0
    for sd in session_data:
        for code, count in sd["metrics"]["code_freq"].items():
            total_code_freq[code] += count
        total_turns += sd["metrics"]["total_turns"]

    print(f"\nTotal turns analyzed: {total_turns}")
    print(f"\nCode frequency (total occurrences across all turns):")
    for code, count in total_code_freq.most_common():
        pct = count / total_turns * 100
        bar = "#" * int(pct)
        print(f"  {code:<20s} {count:>5d} ({pct:5.1f}%) {bar}")

    # Analysis 2: Aggregate Co-occurrence
    print("\n" + "=" * 70)
    print("ANALYSIS 2: CO-OCCURRENCE NETWORKS")
    print("=" * 70)

    n = len(ALL_CODES)
    agg_matrix = [[0.0] * n for _ in range(n)]
    for sd in session_data:
        agg_matrix = add_matrices(agg_matrix, sd["cooc_matrix"])
    agg_matrix = scale_matrix(agg_matrix, 1.0 / len(session_data))

    print(f"\nTop co-occurring code pairs (averaged across {len(session_data)} sessions):")
    print(format_matrix(agg_matrix, top_n=15))

    # Analysis 3: Successful vs Struggling
    print("\n" + "=" * 70)
    print("ANALYSIS 3: SUCCESSFUL vs STRUGGLING SESSIONS")
    print("=" * 70)

    sorted_by_correction = sorted(session_data, key=lambda s: s["metrics"]["correction_rate"])
    split_point = len(sorted_by_correction) // 3

    successful = sorted_by_correction[:split_point]
    struggling = sorted_by_correction[-split_point:]

    print(f"\nSuccessful sessions (lowest correction rate): {len(successful)}")
    if successful:
        print(f"  Avg correction rate: {sum(s['metrics']['correction_rate'] for s in successful) / len(successful):.3f}")
        print(f"  Avg turns: {sum(s['metrics']['total_turns'] for s in successful) / len(successful):.0f}")

    print(f"\nStruggling sessions (highest correction rate): {len(struggling)}")
    if struggling:
        print(f"  Avg correction rate: {sum(s['metrics']['correction_rate'] for s in struggling) / len(struggling):.3f}")
        print(f"  Avg turns: {sum(s['metrics']['total_turns'] for s in struggling) / len(struggling):.0f}")

    succ_matrix = [[0.0] * n for _ in range(n)]
    for sd in successful:
        succ_matrix = add_matrices(succ_matrix, sd["cooc_matrix"])
    succ_matrix = scale_matrix(succ_matrix, 1.0 / max(len(successful), 1))

    strug_matrix = [[0.0] * n for _ in range(n)]
    for sd in struggling:
        strug_matrix = add_matrices(strug_matrix, sd["cooc_matrix"])
    strug_matrix = scale_matrix(strug_matrix, 1.0 / max(len(struggling), 1))

    print(f"\nTop co-occurrences in SUCCESSFUL sessions:")
    print(format_matrix(succ_matrix, top_n=10))

    print(f"\nTop co-occurrences in STRUGGLING sessions:")
    print(format_matrix(strug_matrix, top_n=10))

    diff_matrix = subtract_matrices(succ_matrix, strug_matrix)
    print(f"\nDIFFERENTIAL: Codes that co-occur MORE in successful sessions:")
    pairs_diff = []
    for i in range(n):
        for j in range(i + 1, n):
            pairs_diff.append((ALL_CODES[i], ALL_CODES[j], diff_matrix[i][j]))
    pairs_diff.sort(key=lambda x: -x[2])
    for c1, c2, w in pairs_diff[:8]:
        if w > 0:
            print(f"  {c1} <-> {c2}: +{w:.3f}")

    print(f"\nDIFFERENTIAL: Codes that co-occur MORE in struggling sessions:")
    pairs_diff.sort(key=lambda x: x[2])
    for c1, c2, w in pairs_diff[:8]:
        if w < 0:
            print(f"  {c1} <-> {c2}: {w:.3f}")

    # Code frequency comparison
    print(f"\nCode frequency per turn (successful vs struggling):")
    succ_freq = Counter()
    succ_turns = 0
    for sd in successful:
        for c, cnt in sd["metrics"]["code_freq"].items():
            succ_freq[c] += cnt
        succ_turns += sd["metrics"]["total_turns"]

    strug_freq = Counter()
    strug_turns = 0
    for sd in struggling:
        for c, cnt in sd["metrics"]["code_freq"].items():
            strug_freq[c] += cnt
        strug_turns += sd["metrics"]["total_turns"]

    print(f"  {'Code':<20s} {'Successful':>12s} {'Struggling':>12s} {'Delta':>8s}")
    print(f"  {'-'*52}")
    for code in ALL_CODES:
        s_rate = succ_freq.get(code, 0) / max(succ_turns, 1)
        r_rate = strug_freq.get(code, 0) / max(strug_turns, 1)
        delta = s_rate - r_rate
        sign = "+" if delta > 0 else ""
        print(f"  {code:<20s} {s_rate:>11.3f} {r_rate:>12.3f} {sign}{delta:>7.3f}")

    # Early vs Late sessions
    print("\n" + "-" * 70)
    print("EARLY vs LATE SESSIONS (by project timeline)")
    print("-" * 70)

    by_project = defaultdict(list)
    for sd in session_data:
        by_project[sd["project"]].append(sd)

    early_sessions = []
    late_sessions = []
    for proj, sds in by_project.items():
        if len(sds) < 3:
            continue
        sds_sorted = sorted(sds, key=lambda s: s["session_id"])
        split = len(sds_sorted) // 2
        early_sessions.extend(sds_sorted[:split])
        late_sessions.extend(sds_sorted[split:])

    if early_sessions and late_sessions:
        early_matrix = [[0.0] * n for _ in range(n)]
        for sd in early_sessions:
            early_matrix = add_matrices(early_matrix, sd["cooc_matrix"])
        early_matrix = scale_matrix(early_matrix, 1.0 / len(early_sessions))

        late_matrix = [[0.0] * n for _ in range(n)]
        for sd in late_sessions:
            late_matrix = add_matrices(late_matrix, sd["cooc_matrix"])
        late_matrix = scale_matrix(late_matrix, 1.0 / len(late_sessions))

        diff_el = subtract_matrices(late_matrix, early_matrix)

        print(f"\nEarly sessions: {len(early_sessions)}, Late sessions: {len(late_sessions)}")
        print(f"\nCo-occurrences that INCREASE from early to late:")
        pairs_el = []
        for i in range(n):
            for j in range(i + 1, n):
                pairs_el.append((ALL_CODES[i], ALL_CODES[j], diff_el[i][j]))
        pairs_el.sort(key=lambda x: -x[2])
        for c1, c2, w in pairs_el[:6]:
            if w > 0:
                print(f"  {c1} <-> {c2}: +{w:.3f}")

        print(f"\nCo-occurrences that DECREASE from early to late:")
        pairs_el.sort(key=lambda x: x[2])
        for c1, c2, w in pairs_el[:6]:
            if w < 0:
                print(f"  {c1} <-> {c2}: {w:.3f}")
    else:
        print("  Not enough multi-session projects for early/late comparison")

    # By project type
    print("\n" + "-" * 70)
    print("BY PROJECT TYPE")
    print("-" * 70)

    for proj in sorted(by_project.keys()):
        sds = by_project[proj]
        if len(sds) < 2:
            continue
        proj_matrix = [[0.0] * n for _ in range(n)]
        for sd in sds:
            proj_matrix = add_matrices(proj_matrix, sd["cooc_matrix"])
        proj_matrix = scale_matrix(proj_matrix, 1.0 / len(sds))
        centrality = compute_centrality(proj_matrix)
        top_codes = sorted(centrality.items(), key=lambda x: -x[1])[:3]
        avg_corr = sum(sd["metrics"]["correction_rate"] for sd in sds) / len(sds)
        print(f"\n  {proj} ({len(sds)} sessions, avg correction rate: {avg_corr:.3f})")
        print(f"    Top codes: {', '.join(f'{c}({v:.2f})' for c, v in top_codes)}")

    # Analysis 4: Centrality
    print("\n" + "=" * 70)
    print("ANALYSIS 4: CENTRALITY ANALYSIS")
    print("=" * 70)

    overall_centrality = compute_centrality(agg_matrix)
    print(f"\nOverall centrality (degree centrality, normalized):")
    for code, val in sorted(overall_centrality.items(), key=lambda x: -x[1]):
        bar = "#" * int(val * 40)
        print(f"  {code:<20s} {val:.3f} {bar}")

    succ_centrality = compute_centrality(succ_matrix)
    strug_centrality = compute_centrality(strug_matrix)

    print(f"\nCentrality comparison (Successful vs Struggling):")
    print(f"  {'Code':<20s} {'Successful':>12s} {'Struggling':>12s} {'Shift':>8s}")
    print(f"  {'-'*52}")
    for code in ALL_CODES:
        s_val = succ_centrality.get(code, 0)
        r_val = strug_centrality.get(code, 0)
        shift = s_val - r_val
        sign = "+" if shift > 0 else ""
        arrow = " ^^" if shift > 0.1 else (" vv" if shift < -0.1 else "   ")
        print(f"  {code:<20s} {s_val:>11.3f} {r_val:>12.3f} {sign}{shift:>7.3f}{arrow}")

    if early_sessions and late_sessions:
        early_centrality = compute_centrality(early_matrix)
        late_centrality = compute_centrality(late_matrix)

        print(f"\nCentrality shift (Early -> Late sessions):")
        print(f"  {'Code':<20s} {'Early':>12s} {'Late':>12s} {'Shift':>8s}")
        print(f"  {'-'*52}")
        for code in ALL_CODES:
            e_val = early_centrality.get(code, 0)
            l_val = late_centrality.get(code, 0)
            shift = l_val - e_val
            sign = "+" if shift > 0 else ""
            print(f"  {code:<20s} {e_val:>11.3f} {l_val:>12.3f} {sign}{shift:>7.3f}")

    # Summary Statistics
    print("\n" + "=" * 70)
    print("SUMMARY STATISTICS")
    print("=" * 70)

    print(f"\nSessions analyzed: {len(session_data)}")
    print(f"Total turns: {total_turns}")
    print(f"Projects: {len(by_project)}")

    corr_rates = [sd["metrics"]["correction_rate"] for sd in session_data]
    print(f"\nCorrection rate distribution:")
    print(f"  Min: {min(corr_rates):.3f}")
    print(f"  Max: {max(corr_rates):.3f}")
    print(f"  Mean: {sum(corr_rates)/len(corr_rates):.3f}")
    print(f"  Median: {sorted(corr_rates)[len(corr_rates)//2]:.3f}")

    print(f"\nSessions per project:")
    for proj in sorted(by_project.keys()):
        print(f"  {proj}: {len(by_project[proj])}")

    # Write full results to JSON
    results = {
        "metadata": {
            "sessions_analyzed": len(session_data),
            "total_turns": total_turns,
            "projects": list(by_project.keys()),
            "window_size": 5,
        },
        "code_frequency": dict(total_code_freq),
        "overall_centrality": overall_centrality,
        "successful_centrality": succ_centrality,
        "struggling_centrality": strug_centrality,
        "correction_rates": {
            sd["session_id"]: sd["metrics"]["correction_rate"]
            for sd in session_data
        },
        "aggregate_cooccurrence": {
            f"{ALL_CODES[i]}-{ALL_CODES[j]}": agg_matrix[i][j]
            for i in range(n) for j in range(i + 1, n) if agg_matrix[i][j] > 0
        },
        "successful_cooccurrence": {
            f"{ALL_CODES[i]}-{ALL_CODES[j]}": succ_matrix[i][j]
            for i in range(n) for j in range(i + 1, n) if succ_matrix[i][j] > 0
        },
        "struggling_cooccurrence": {
            f"{ALL_CODES[i]}-{ALL_CODES[j]}": strug_matrix[i][j]
            for i in range(n) for j in range(i + 1, n) if strug_matrix[i][j] > 0
        },
        "differential_cooccurrence": {
            f"{ALL_CODES[i]}-{ALL_CODES[j]}": diff_matrix[i][j]
            for i in range(n) for j in range(i + 1, n) if abs(diff_matrix[i][j]) > 0.001
        },
        "per_session": [
            {
                "session_id": sd["session_id"],
                "project": sd["project"],
                "correction_rate": sd["metrics"]["correction_rate"],
                "total_turns": sd["metrics"]["total_turns"],
                "code_freq": sd["metrics"]["code_freq"],
            }
            for sd in session_data
        ],
    }

    json_path = OUTPUT_DIR / "ena-epistemic-network-analysis.json"
    with open(json_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nFull results written to: {json_path}")

    return results, session_data, successful, struggling


if __name__ == "__main__":
    results, session_data, successful, struggling = main()
