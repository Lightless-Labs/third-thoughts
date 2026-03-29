#!/usr/bin/env python3
"""
NCD (Normalized Compression Distance) Session Clustering

Clusters Claude Code sessions by structural similarity using information-theoretic
distance, with zero hand-crafted features or LLM analysis.

Method:
  NCD(x,y) = (C(xy) - min(C(x), C(y))) / max(C(x), C(y))
  where C(x) = len(zlib.compress(x.encode()))

Two representations are compared:
  1. Raw symbol streams (captures temporal ordering)
  2. Windowed n-gram profiles (normalizes for length, captures rhythm)

The windowed approach divides each session into 10 equal windows and computes
the n-gram distribution per window, producing a fixed-size fingerprint regardless
of absolute session length.
"""

import json
import glob
import os
import re
import zlib
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from scipy.cluster.hierarchy import linkage, fcluster
from scipy.spatial.distance import squareform


def _strip_user_path(name):
    """Strip user-specific path components like -Users-<username>- from project names."""
    return re.sub(r'-Users-[^-]+-', '-', name)

# ─── Configuration ───────────────────────────────────────────────────────────

CORPUS_DIR = os.environ.get("MIDDENS_CORPUS", "corpus/")
TARGET_SESSIONS = 100  # sample ~100 sessions from full corpus
MIN_EVENTS = 8  # skip trivially short sessions
N_WINDOWS = 10  # windows for the fingerprint
NGRAM_N = 3  # trigrams
OUTPUT_DIR = os.environ.get("MIDDENS_OUTPUT", "experiments/")


# ─── Step 1: Canonicalize sessions into symbol streams ───────────────────────

def classify_user_length(text_len):
    """Bucket user message length."""
    if text_len < 100:
        return "short"
    elif text_len < 500:
        return "medium"
    else:
        return "long"


def extract_symbol_stream(filepath):
    """Convert a JSONL session file into a symbol stream."""
    symbols = []

    with open(filepath) as f:
        for line in f:
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue

            msg_type = obj.get("type")

            if msg_type == "user":
                msg = obj.get("message", {})
                content = msg.get("content", "")

                if isinstance(content, list):
                    has_tool_result = any(
                        isinstance(b, dict) and b.get("type") == "tool_result"
                        for b in content
                    )
                    if has_tool_result:
                        symbols.append("R")  # tool result return
                        continue
                    text_parts = []
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "text":
                            text_parts.append(block.get("text", ""))
                        elif isinstance(block, str):
                            text_parts.append(block)
                    text = " ".join(text_parts)
                elif isinstance(content, str):
                    text = content
                else:
                    text = ""

                if obj.get("isMeta"):
                    continue

                bucket = classify_user_length(len(text))
                symbols.append(f"U{bucket[0]}")  # Us, Um, Ul

            elif msg_type == "assistant":
                msg = obj.get("message", {})
                content = msg.get("content", [])

                if isinstance(content, list):
                    for block in content:
                        if not isinstance(block, dict):
                            continue
                        btype = block.get("type")
                        if btype == "text":
                            symbols.append("At")
                        elif btype == "thinking":
                            symbols.append("Ak")
                        elif btype == "tool_use":
                            tool_name = block.get("name", "X")
                            # Collapse to single-char tool codes for compression
                            tool_map = {
                                "Read": "Tr",
                                "Edit": "Te",
                                "Write": "Tw",
                                "Bash": "Tb",
                                "Grep": "Tg",
                                "Glob": "Tf",
                                "Skill": "Ts",
                                "WebSearch": "Tn",
                                "WebFetch": "Tn",
                                "NotebookEdit": "Tj",
                                "StructuredOutput": "To",
                                "ToolSearch": "Td",
                            }
                            if tool_name.startswith("mcp__"):
                                symbols.append("Tm")
                            else:
                                symbols.append(tool_map.get(tool_name, "Tx"))
                elif isinstance(content, str) and content:
                    symbols.append("At")

    return symbols


def make_ngram_fingerprint(symbols, n=NGRAM_N, n_windows=N_WINDOWS):
    """
    Create a length-normalized fingerprint from a symbol stream.

    Divides the stream into n_windows equal segments, computes n-gram
    frequencies within each, and serializes as a fixed-format string.
    This produces comparable strings regardless of absolute session length.
    """
    if len(symbols) < n:
        return " ".join(symbols)

    # Compute global n-grams
    ngrams = []
    for i in range(len(symbols) - n + 1):
        ngrams.append("".join(symbols[i:i + n]))

    # Divide into windows
    window_size = max(1, len(ngrams) // n_windows)
    fingerprint_parts = []

    for w in range(n_windows):
        start = w * window_size
        end = start + window_size if w < n_windows - 1 else len(ngrams)
        window_ngrams = ngrams[start:end]

        if not window_ngrams:
            fingerprint_parts.append(f"W{w}:")
            continue

        # Count and normalize
        counts = Counter(window_ngrams)
        total = sum(counts.values())
        # Top-5 n-grams with relative frequency (quantized to 10 levels)
        top = counts.most_common(5)
        parts = []
        for gram, count in top:
            freq = min(9, int(10 * count / total))
            parts.append(f"{gram}{freq}")
        fingerprint_parts.append(f"W{w}:{','.join(parts)}")

    return "|".join(fingerprint_parts)


def find_all_sessions(corpus_dir):
    """Walk the corpus directory tree and find all top-level JSONL session files."""
    results = []
    for dirpath, dirnames, filenames in os.walk(corpus_dir, followlinks=True):
        # Skip subagent directories
        if "subagents" in dirpath:
            continue
        for fname in filenames:
            if fname.endswith(".jsonl"):
                filepath = os.path.join(dirpath, fname)
                # Derive project name from parent directory
                project = os.path.basename(dirpath)
                results.append((filepath, project))
    return results


def collect_sessions():
    """Collect and sample sessions across projects."""
    found = find_all_sessions(CORPUS_DIR)
    files = [fp for fp, _ in found]

    project_sessions = defaultdict(list)
    for fp, project in found:
        project_sessions[project].append(fp)

    print(f"Found {len(files)} total session files across {len(project_sessions)} projects")

    candidates = []
    for project, session_files in project_sessions.items():
        for sf in session_files:
            symbols = extract_symbol_stream(sf)
            if len(symbols) >= MIN_EVENTS:
                candidates.append({
                    "file": sf,
                    "project": project,
                    "session_id": os.path.basename(sf).replace(".jsonl", ""),
                    "symbols": symbols,
                    "stream": " ".join(symbols),
                    "fingerprint": make_ngram_fingerprint(symbols),
                    "n_events": len(symbols),
                })

    print(f"Found {len(candidates)} sessions with >= {MIN_EVENTS} events")

    # Stratified sampling across projects
    if len(candidates) <= TARGET_SESSIONS:
        selected = candidates
    else:
        selected = []
        project_candidates = defaultdict(list)
        for c in candidates:
            project_candidates[c["project"]].append(c)

        # Count projects with candidates
        active_projects = {p: cs for p, cs in project_candidates.items() if cs}
        per_project = max(3, TARGET_SESSIONS // len(active_projects))

        for proj, pcands in active_projects.items():
            pcands.sort(key=lambda x: x["n_events"])
            if len(pcands) <= per_project:
                selected.extend(pcands)
            else:
                # Evenly spaced by size
                indices = np.linspace(0, len(pcands) - 1, per_project, dtype=int)
                for idx in np.unique(indices):
                    selected.append(pcands[idx])

        # Trim to target
        if len(selected) > TARGET_SESSIONS:
            selected.sort(key=lambda x: x["n_events"])
            indices = np.linspace(0, len(selected) - 1, TARGET_SESSIONS, dtype=int)
            selected = [selected[i] for i in np.unique(indices)]

    print(f"Selected {len(selected)} sessions for analysis")
    return selected


# ─── Step 2: Compute NCD matrix ─────────────────────────────────────────────

def ncd(x, y):
    """Normalized Compression Distance between two strings."""
    xb = x.encode("utf-8")
    yb = y.encode("utf-8")
    cx = len(zlib.compress(xb))
    cy = len(zlib.compress(yb))
    cxy = len(zlib.compress(xb + yb))
    denominator = max(cx, cy)
    if denominator == 0:
        return 1.0
    return (cxy - min(cx, cy)) / denominator


def compute_ncd_matrix(sessions, use_fingerprint=True):
    """Build pairwise NCD distance matrix."""
    n = len(sessions)
    matrix = np.zeros((n, n))

    if use_fingerprint:
        streams = [s["fingerprint"] for s in sessions]
    else:
        streams = [s["stream"] for s in sessions]

    total = n * (n - 1) // 2
    done = 0

    for i in range(n):
        for j in range(i + 1, n):
            d = ncd(streams[i], streams[j])
            matrix[i][j] = d
            matrix[j][i] = d
            done += 1
            if done % 200 == 0:
                print(f"  NCD computation: {done}/{total} ({100*done/total:.0f}%)")

    print(f"  NCD computation: {total}/{total} (100%)")
    return matrix


# ─── Step 3: Cluster ────────────────────────────────────────────────────────

def cluster_sessions(ncd_matrix, n_clusters_range=(5, 10)):
    """Hierarchical clustering on NCD matrix."""
    condensed = squareform(ncd_matrix)
    Z = linkage(condensed, method="average")

    best_k = 6
    best_score = -1

    for k in range(n_clusters_range[0], n_clusters_range[1] + 1):
        labels = fcluster(Z, k, criterion="maxclust")

        # Silhouette-like score
        score = 0
        valid = 0
        for i in range(len(labels)):
            same = [j for j in range(len(labels)) if labels[j] == labels[i] and j != i]
            diff = [j for j in range(len(labels)) if labels[j] != labels[i]]

            if not same or not diff:
                continue

            a = np.mean([ncd_matrix[i][j] for j in same])
            b = np.mean([ncd_matrix[i][j] for j in diff])
            if max(a, b) > 0:
                score += (b - a) / max(a, b)
                valid += 1

        if valid > 0:
            score /= valid

        if score > best_score:
            best_score = score
            best_k = k

    print(f"Best cluster count: {best_k} (silhouette score: {best_score:.3f})")

    labels = fcluster(Z, best_k, criterion="maxclust")
    return labels, Z, best_k


# ─── Step 4: Characterize clusters ──────────────────────────────────────────

def expand_symbol(s):
    """Expand compressed symbol back to readable form."""
    symbol_map = {
        "Us": "U:short", "Um": "U:medium", "Ul": "U:long",
        "At": "A:text", "Ak": "A:think",
        "Tr": "T:Read", "Te": "T:Edit", "Tw": "T:Write",
        "Tb": "T:Bash", "Tg": "T:Grep", "Tf": "T:Glob",
        "Ts": "T:Skill", "Tm": "T:MCP", "To": "T:StructuredOutput",
        "Tn": "T:Web", "Tj": "T:Notebook", "Td": "T:ToolSearch",
        "Tx": "T:Other", "R": "U:result",
    }
    return symbol_map.get(s, s)


def characterize_clusters(sessions, labels, ncd_matrix):
    """Analyze each cluster's characteristics."""
    clusters = defaultdict(list)
    for i, label in enumerate(labels):
        clusters[label].append(i)

    results = {}

    for cluster_id, member_indices in sorted(clusters.items()):
        members = [sessions[i] for i in member_indices]

        projects = Counter(
            _strip_user_path(m["project"])
            for m in members
        )

        lengths = [m["n_events"] for m in members]

        # Symbol frequency (expanded)
        all_symbols = []
        for m in members:
            all_symbols.extend(m["symbols"])
        symbol_counts = Counter(expand_symbol(s) for s in all_symbols)

        # Tool mix
        tool_counts = Counter(
            k for k in symbol_counts if k.startswith("T:")
        )
        for k in tool_counts:
            tool_counts[k] = symbol_counts[k]

        # User pattern
        user_counts = Counter(
            k for k in symbol_counts if k.startswith("U:")
        )
        for k in user_counts:
            user_counts[k] = symbol_counts[k]

        # N-gram analysis on expanded symbols
        bigrams = Counter()
        trigrams = Counter()
        for m in members:
            syms = [expand_symbol(s) for s in m["symbols"]]
            for k in range(len(syms) - 1):
                bigrams[f"{syms[k]} {syms[k+1]}"] += 1
            for k in range(len(syms) - 2):
                trigrams[f"{syms[k]} {syms[k+1]} {syms[k+2]}"] += 1

        # Archetype
        if len(member_indices) > 1:
            avg_ncds = []
            for i in member_indices:
                avg_d = np.mean([ncd_matrix[i][j] for j in member_indices if j != i])
                avg_ncds.append((avg_d, i))
            avg_ncds.sort()
            archetype_idx = avg_ncds[0][1]
            archetype_ncd = avg_ncds[0][0]
        else:
            archetype_idx = member_indices[0]
            archetype_ncd = 0.0

        # Cohesion
        if len(member_indices) > 1:
            intra = [ncd_matrix[i][j]
                     for i in member_indices for j in member_indices if i < j]
            cohesion = np.mean(intra)
        else:
            cohesion = 0.0

        # Compute ratios for characterization
        total_syms = len(all_symbols)
        tool_ratio = sum(1 for s in all_symbols if s.startswith("T")) / max(1, total_syms)
        user_ratio = sum(1 for s in all_symbols if s.startswith("U")) / max(1, total_syms)
        result_ratio = sum(1 for s in all_symbols if s == "R") / max(1, total_syms)
        think_ratio = sum(1 for s in all_symbols if s == "Ak") / max(1, total_syms)
        text_ratio = sum(1 for s in all_symbols if s == "At") / max(1, total_syms)

        # Compute "autonomy ratio" = tool calls per user message
        n_user_msgs = sum(1 for s in all_symbols if s.startswith("U") and s != "R")
        n_tool_calls = sum(1 for s in all_symbols if s.startswith("T"))
        autonomy = n_tool_calls / max(1, n_user_msgs)

        # Compute "turn density" = events per user message
        turn_density = total_syms / max(1, n_user_msgs)

        results[cluster_id] = {
            "size": len(members),
            "projects": dict(projects.most_common()),
            "avg_length": np.mean(lengths),
            "min_length": min(lengths),
            "max_length": max(lengths),
            "median_length": np.median(lengths),
            "top_symbols": dict(Counter(expand_symbol(s) for s in all_symbols).most_common(15)),
            "tool_mix": dict(sorted(tool_counts.items(), key=lambda x: -x[1])[:10]),
            "user_pattern": dict(sorted(user_counts.items(), key=lambda x: -x[1])),
            "top_bigrams": dict(bigrams.most_common(5)),
            "top_trigrams": dict(trigrams.most_common(5)),
            "archetype_idx": archetype_idx,
            "archetype_session": sessions[archetype_idx],
            "archetype_ncd": archetype_ncd,
            "cohesion": cohesion,
            "tool_ratio": tool_ratio,
            "user_ratio": user_ratio,
            "result_ratio": result_ratio,
            "think_ratio": think_ratio,
            "text_ratio": text_ratio,
            "autonomy": autonomy,
            "turn_density": turn_density,
            "member_sessions": [
                (sessions[i]["session_id"],
                 _strip_user_path(sessions[i]["project"]),
                 sessions[i]["n_events"])
                for i in member_indices
            ],
        }

    return results


# ─── Cluster labeling ───────────────────────────────────────────────────────

def infer_cluster_label(info):
    """Infer a descriptive label for a cluster based on its structural patterns."""
    labels = []

    # Autonomy level
    if info["autonomy"] > 15:
        labels.append("Highly-Autonomous")
    elif info["autonomy"] > 8:
        labels.append("Autonomous")
    elif info["autonomy"] > 4:
        labels.append("Semi-Autonomous")
    else:
        labels.append("Interactive")

    # Dominant tool pattern
    tool_mix = info.get("tool_mix", {})
    if tool_mix:
        dominant = max(tool_mix, key=tool_mix.get)
        total_tools = sum(tool_mix.values())
        dom_pct = tool_mix[dominant] / max(1, total_tools)
        if dom_pct > 0.4:
            labels.append(dominant.replace("T:", "") + "-Dominant")
        elif info["tool_ratio"] > 0.5:
            labels.append("Multi-Tool")

    # Thinking pattern
    if info["think_ratio"] > 0.1:
        labels.append("Reasoning-Heavy")

    # User prompt style
    user_pattern = info.get("user_pattern", {})
    long_msgs = user_pattern.get("U:long", 0)
    short_msgs = user_pattern.get("U:short", 0)
    if long_msgs > short_msgs and long_msgs > 0:
        labels.append("Detailed-Prompts")
    elif short_msgs > long_msgs * 3 and short_msgs > 0:
        labels.append("Terse-Steering")

    return " / ".join(labels) if labels else "Mixed"


# ─── Report generation ──────────────────────────────────────────────────────

def generate_report(sessions, labels, ncd_fp, ncd_raw, cluster_info, linkage_matrix):
    """Generate comprehensive markdown report."""
    lines = []
    lines.append("# Experiment 011: NCD Session Clustering")
    lines.append("")
    lines.append("**Date**: 2026-03-19")
    lines.append("**Method**: Normalized Compression Distance + hierarchical clustering")
    lines.append("**Sessions analyzed**: {}".format(len(sessions)))
    lines.append("**Clusters found**: {}".format(len(cluster_info)))
    lines.append("")

    lines.append("## Method")
    lines.append("")
    lines.append("### Symbol Stream Encoding")
    lines.append("")
    lines.append("Each session is reduced to a sequence of structural symbols:")
    lines.append("")
    lines.append("| Symbol | Meaning |")
    lines.append("|--------|---------|")
    lines.append("| `Us`, `Um`, `Ul` | User message: short (<100 chars), medium, long (>500) |")
    lines.append("| `At` | Assistant text output |")
    lines.append("| `Ak` | Assistant thinking block |")
    lines.append("| `Tb`, `Tr`, `Te`, `Tg`, `Tf` | Tool: Bash, Read, Edit, Grep, Glob |")
    lines.append("| `Tw`, `Tm`, `To` | Tool: Write, MCP, StructuredOutput |")
    lines.append("| `R` | Tool result returned to model |")
    lines.append("")
    lines.append("### NCD with Windowed N-gram Fingerprints")
    lines.append("")
    lines.append("Raw NCD is length-dominated: a 50-event session will always appear distant")
    lines.append("from a 5000-event session regardless of structural similarity. To normalize:")
    lines.append("")
    lines.append("1. Extract trigram sequences from the symbol stream")
    lines.append("2. Divide into 10 equal windows (normalizing for length)")
    lines.append("3. Compute top-5 trigram frequencies per window (quantized to 10 levels)")
    lines.append("4. Serialize as a fixed-format fingerprint string")
    lines.append("5. Apply NCD to these fingerprints")
    lines.append("")
    lines.append("This captures the *rhythm* of interaction -- whether tool-heavy bursts")
    lines.append("happen early, middle, or late, whether thinking precedes tools, etc. --")
    lines.append("while being invariant to absolute session length.")
    lines.append("")
    lines.append("```")
    lines.append("NCD(x,y) = (C(xy) - min(C(x), C(y))) / max(C(x), C(y))")
    lines.append("```")
    lines.append("")

    # Global stats
    lines.append("## Global Statistics")
    lines.append("")
    all_lengths = [s["n_events"] for s in sessions]
    lines.append(f"- **Sessions**: {len(sessions)} across {len(set(s['project'] for s in sessions))} projects")
    lines.append(f"- **Session lengths**: min={min(all_lengths)}, median={int(np.median(all_lengths))}, max={max(all_lengths)}")

    upper_fp = ncd_fp[np.triu_indices_from(ncd_fp, k=1)]
    upper_raw = ncd_raw[np.triu_indices_from(ncd_raw, k=1)]

    lines.append(f"- **NCD (fingerprint)**: mean={np.mean(upper_fp):.3f}, median={np.median(upper_fp):.3f}, range=[{np.min(upper_fp):.3f}, {np.max(upper_fp):.3f}]")
    lines.append(f"- **NCD (raw stream)**: mean={np.mean(upper_raw):.3f}, median={np.median(upper_raw):.3f}, range=[{np.min(upper_raw):.3f}, {np.max(upper_raw):.3f}]")
    lines.append("")

    # Correlation between raw and fingerprint NCD
    corr = np.corrcoef(upper_fp, upper_raw)[0, 1]
    lines.append(f"- **Correlation between raw and fingerprint NCD**: r={corr:.3f}")
    lines.append("  - r < 0.7 indicates the fingerprint captures different structure than raw length")
    lines.append("")

    projects = Counter(
        _strip_user_path(s["project"])
        for s in sessions
    )
    lines.append("**Projects sampled**:")
    for proj, count in projects.most_common():
        lines.append(f"- {proj}: {count} sessions")
    lines.append("")

    # NCD distribution
    lines.append("## NCD Distance Distribution")
    lines.append("")
    lines.append("### Fingerprint NCD (used for clustering)")
    lines.append("")
    for pct in [10, 25, 50, 75, 90]:
        lines.append(f"- P{pct}: {np.percentile(upper_fp, pct):.3f}")
    lines.append("")

    # ─── Cluster details ─────────────────────────────────────────────
    lines.append("## Clusters")
    lines.append("")

    for cid, info in sorted(cluster_info.items()):
        label = infer_cluster_label(info)
        lines.append(f"### Cluster {cid}: {label}")
        lines.append("")
        lines.append(f"**Size**: {info['size']} sessions | "
                     f"**Cohesion**: {info['cohesion']:.3f} | "
                     f"**Autonomy**: {info['autonomy']:.1f} tools/user-msg")
        lines.append(f"**Length**: avg={info['avg_length']:.0f}, "
                     f"median={info['median_length']:.0f}, "
                     f"range=[{info['min_length']}, {info['max_length']}]")
        lines.append("")

        # Structural profile
        lines.append("**Structural profile**:")
        lines.append(f"- Tool calls: {info['tool_ratio']:.0%} of events")
        lines.append(f"- Text output: {info['text_ratio']:.0%} of events")
        lines.append(f"- Thinking: {info['think_ratio']:.0%} of events")
        lines.append(f"- User messages: {info['user_ratio']:.0%} of events")
        lines.append(f"- Tool results: {info['result_ratio']:.0%} of events")
        lines.append(f"- Turn density: {info['turn_density']:.1f} events per user message")
        lines.append("")

        # Projects
        lines.append("**Projects**:")
        for proj, count in info["projects"].items():
            lines.append(f"- {proj}: {count}")
        lines.append("")

        # Tool mix
        if info["tool_mix"]:
            lines.append("**Tool frequency**:")
            total_tools = sum(info["tool_mix"].values())
            for tool, count in list(info["tool_mix"].items())[:7]:
                pct = count / max(1, total_tools) * 100
                lines.append(f"- {tool}: {count} ({pct:.0f}%)")
            lines.append("")

        # User prompt pattern
        if info["user_pattern"]:
            lines.append("**User message sizes**:")
            for bucket, count in info["user_pattern"].items():
                lines.append(f"- {bucket}: {count}")
            lines.append("")

        # Structural patterns
        lines.append("**Dominant structural patterns** (trigrams):")
        for gram, count in list(info["top_trigrams"].items())[:5]:
            lines.append(f"- `{gram}`: {count}")
        lines.append("")

        # Archetype
        arch = info["archetype_session"]
        arch_proj = _strip_user_path(arch["project"])
        lines.append(f"**Archetype**: `{arch['session_id']}`")
        lines.append(f"- Project: {arch_proj}")
        lines.append(f"- Avg NCD to cluster: {info['archetype_ncd']:.3f}")
        lines.append(f"- Length: {arch['n_events']} events")
        stream_expanded = " ".join(expand_symbol(s) for s in arch["symbols"][:30])
        if len(arch["symbols"]) > 30:
            stream_expanded += " ..."
        lines.append(f"- Stream prefix: `{stream_expanded}`")
        lines.append("")

        # Members table
        lines.append("<details><summary>All sessions in cluster ({} total)</summary>".format(info["size"]))
        lines.append("")
        lines.append("| Session ID | Project | Events |")
        lines.append("|---|---|---|")
        for sid, proj, n_ev in info["member_sessions"]:
            lines.append(f"| `{sid[:16]}...` | {proj} | {n_ev} |")
        lines.append("")
        lines.append("</details>")
        lines.append("")

    # ─── Archetype summary ───────────────────────────────────────────
    lines.append("## Session Archetypes")
    lines.append("")
    lines.append("The most representative session per cluster (lowest average NCD to members):")
    lines.append("")
    lines.append("| Cluster | Label | Archetype | Project | Events | Autonomy | Avg NCD |")
    lines.append("|---------|-------|-----------|---------|--------|----------|---------|")
    for cid, info in sorted(cluster_info.items()):
        label = infer_cluster_label(info)
        arch = info["archetype_session"]
        proj = _strip_user_path(arch["project"])
        lines.append(f"| {cid} | {label} | `{arch['session_id'][:12]}...` | "
                     f"{proj} | {arch['n_events']} | {info['autonomy']:.1f} | "
                     f"{info['archetype_ncd']:.3f} |")
    lines.append("")

    # ─── Key findings ────────────────────────────────────────────────
    lines.append("## Key Findings")
    lines.append("")

    sorted_clusters = sorted(cluster_info.items(), key=lambda x: x[1]["size"], reverse=True)
    multi_clusters = [(cid, info) for cid, info in cluster_info.items() if info["size"] > 1]

    lines.append("### 1. Structural Archetypes Exist")
    lines.append("")
    lines.append(f"NCD clustering found {len(cluster_info)} distinct structural archetypes,")
    lines.append(f"with {len(multi_clusters)} clusters containing multiple sessions.")
    lines.append(f"The largest cluster (n={sorted_clusters[0][1]['size']}) is labeled")
    lines.append(f'"{infer_cluster_label(sorted_clusters[0][1])}".')
    lines.append("")

    if multi_clusters:
        most_cohesive = min(multi_clusters, key=lambda x: x[1]["cohesion"])
        least_cohesive = max(multi_clusters, key=lambda x: x[1]["cohesion"])
        lines.append(f"Most cohesive: Cluster {most_cohesive[0]} "
                     f"(NCD={most_cohesive[1]['cohesion']:.3f}) -- sessions are nearly identical in shape.")
        lines.append(f"Least cohesive: Cluster {least_cohesive[0]} "
                     f"(NCD={least_cohesive[1]['cohesion']:.3f}) -- more internal variation.")
        lines.append("")

    lines.append("### 2. Autonomy Spectrum")
    lines.append("")
    autonomies = [(cid, info["autonomy"]) for cid, info in cluster_info.items()]
    autonomies.sort(key=lambda x: x[1], reverse=True)
    lines.append("Clusters span a wide autonomy range (tools per user message):")
    lines.append("")
    for cid, aut in autonomies:
        label = infer_cluster_label(cluster_info[cid])
        lines.append(f"- Cluster {cid} ({label}): {aut:.1f} tools/msg")
    lines.append("")

    lines.append("### 3. Project-Cluster Correlation")
    lines.append("")
    lines.append("Do projects cluster together (suggesting project-specific styles)?")
    lines.append("")

    project_cluster_map = defaultdict(Counter)
    for i, s in enumerate(sessions):
        proj = _strip_user_path(s["project"])
        project_cluster_map[proj][labels[i]] += 1

    strong_patterns = []
    for proj, cluster_dist in sorted(project_cluster_map.items()):
        total = sum(cluster_dist.values())
        if total > 1:
            dominant = cluster_dist.most_common(1)[0]
            concentration = dominant[1] / total
            marker = " **<-- strong**" if concentration > 0.7 else ""
            lines.append(f"- **{proj}** ({total} sessions): "
                         f"{concentration:.0%} in cluster {dominant[0]}{marker}")
            if concentration > 0.7:
                strong_patterns.append(proj)
    lines.append("")

    if strong_patterns:
        lines.append(f"Strong project-cluster correlation: {', '.join(strong_patterns)}.")
        lines.append("These projects have a consistent interaction shape across sessions.")
    else:
        lines.append("No strong project-cluster correlation. Interaction style varies within projects.")
    lines.append("")

    lines.append("### 4. Length Independence")
    lines.append("")
    lines.append("The fingerprint-based NCD normalizes for length. Do clusters still separate by length?")
    lines.append("")
    for cid, info in sorted(cluster_info.items()):
        spread = info["max_length"] - info["min_length"]
        lines.append(f"- Cluster {cid}: [{info['min_length']}, {info['max_length']}] (spread={spread})")
    lines.append("")

    # Check length correlation
    cluster_means = [cluster_info[cid]["avg_length"] for cid in sorted(cluster_info.keys())]
    if len(cluster_means) > 2:
        # Check if clusters with wide length spread exist
        wide_spread = [int(cid) for cid, info in cluster_info.items()
                       if info["max_length"] > info["min_length"] * 3 and info["size"] > 1]
        if wide_spread:
            lines.append(f"Clusters {wide_spread} contain sessions of very different lengths --")
            lines.append("confirming that structural shape is independent of duration.")
        else:
            lines.append("Clusters are somewhat length-stratified, suggesting session duration")
            lines.append("does influence structural rhythm.")
    lines.append("")

    lines.append("### 5. Thinking Patterns")
    lines.append("")
    think_clusters = [(cid, info["think_ratio"]) for cid, info in cluster_info.items()]
    think_clusters.sort(key=lambda x: x[1], reverse=True)
    lines.append("Thinking block usage varies across clusters:")
    lines.append("")
    for cid, tr in think_clusters:
        lines.append(f"- Cluster {cid}: {tr:.0%} thinking")
    lines.append("")

    return "\n".join(lines)


# ─── Main ───────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("NCD Session Clustering (v2 - windowed fingerprints)")
    print("=" * 60)

    # Step 1: Collect and canonicalize
    print("\n--- Step 1: Collecting and canonicalizing sessions ---")
    sessions = collect_sessions()

    if len(sessions) < 3:
        print("ERROR: Not enough sessions to cluster")
        sys.exit(1)

    # Print sample streams and fingerprints
    print("\nSample symbol streams:")
    for s in sessions[:3]:
        proj = _strip_user_path(s["project"])
        expanded = " ".join(expand_symbol(sym) for sym in s["symbols"][:15])
        print(f"  [{proj}] ({s['n_events']} events): {expanded}...")
    print("\nSample fingerprints:")
    for s in sessions[:2]:
        print(f"  ({s['n_events']} events): {s['fingerprint'][:120]}...")

    # Step 2: NCD matrices
    print(f"\n--- Step 2a: Computing fingerprint NCD matrix ({len(sessions)}x{len(sessions)}) ---")
    ncd_fp = compute_ncd_matrix(sessions, use_fingerprint=True)

    upper_fp = ncd_fp[np.triu_indices_from(ncd_fp, k=1)]
    print(f"  Fingerprint NCD: mean={np.mean(upper_fp):.3f}, median={np.median(upper_fp):.3f}")

    print(f"\n--- Step 2b: Computing raw stream NCD matrix ({len(sessions)}x{len(sessions)}) ---")
    ncd_raw = compute_ncd_matrix(sessions, use_fingerprint=False)

    upper_raw = ncd_raw[np.triu_indices_from(ncd_raw, k=1)]
    print(f"  Raw NCD: mean={np.mean(upper_raw):.3f}, median={np.median(upper_raw):.3f}")

    corr = np.corrcoef(upper_fp, upper_raw)[0, 1]
    print(f"  Correlation: {corr:.3f}")

    # Step 3: Cluster on fingerprint NCD
    print("\n--- Step 3: Hierarchical clustering ---")
    labels, linkage_matrix, best_k = cluster_sessions(ncd_fp)

    cluster_sizes = Counter(labels)
    for cid, size in sorted(cluster_sizes.items()):
        print(f"  Cluster {cid}: {size} sessions")

    # Step 4: Characterize
    print("\n--- Step 4: Characterizing clusters ---")
    cluster_info = characterize_clusters(sessions, labels, ncd_fp)

    for cid, info in sorted(cluster_info.items()):
        label = infer_cluster_label(info)
        print(f"  Cluster {cid} ({label}): {info['size']} sessions, "
              f"avg_len={info['avg_length']:.0f}, autonomy={info['autonomy']:.1f}, "
              f"cohesion={info['cohesion']:.3f}")

    # Step 5: Generate report
    print("\n--- Step 5: Generating report ---")
    report = generate_report(sessions, labels, ncd_fp, ncd_raw, cluster_info, linkage_matrix)

    output_path = os.path.join(OUTPUT_DIR, "011-ncd-session-clustering.md")
    with open(output_path, "w") as f:
        f.write(report)
    print(f"  Report written to {output_path}")

    return sessions, labels, ncd_fp, ncd_raw, cluster_info


if __name__ == "__main__":
    sessions, labels, ncd_fp, ncd_raw, cluster_info = main()
