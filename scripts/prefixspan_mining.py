#!/usr/bin/env python3
"""
PrefixSpan Sequential Pattern Mining on Claude Code Sessions.

Discovers frequent sequential patterns in tool usage -- ordered subsequences
that appear across many sessions. Unlike Markov chains (which only look at
adjacent transitions), PrefixSpan finds patterns like:
  Read -> [anything] -> Edit -> [anything] -> Bash -> [anything] -> Read
that span multiple steps with arbitrary gaps.

Reference: Pei, J. et al. (2004). "Mining Sequential Patterns by
Pattern-Growth." IEEE TKDE, 16(11).
"""

import json
import math
import os
import re
import sys
import random
from collections import Counter, defaultdict
from pathlib import Path

from prefixspan import PrefixSpan

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

MAX_SESSIONS = 200  # Sample cap
MIN_SUPPORT_FRACTION = 0.15  # 15% of sessions
MIN_PATTERN_LEN = 3
MAX_PATTERN_LEN = 6

# ============================================================
# DATA LOADING (reused pattern from tool_sequence_mining.py)
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
    """Classify user message as correction, positive, or neutral."""
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
    """Find all .jsonl files under root, following symlinks."""
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
    """Parse a single JSONL session file into structured messages."""
    messages = []
    with open(filepath, "r") as f:
        for line_num, line in enumerate(f):
            try:
                obj = json.loads(line.strip())
                obj["_line_num"] = line_num
                obj["_filepath"] = filepath
                messages.append(obj)
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue
    return messages


def extract_tool_sequence(messages):
    """Extract ordered sequence of tool call names from session messages."""
    tool_calls = []
    for msg in messages:
        if msg.get("type") == "assistant":
            content = msg.get("message", {}).get("content", [])
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "tool_use":
                        tool_calls.append(block.get("name", "unknown"))
    return tool_calls


def extract_user_messages(messages):
    """Extract genuine human-typed user messages."""
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


def compute_session_success(messages, tool_calls, user_msgs):
    """Compute a success score for the session."""
    if not user_msgs:
        return 0.0, "neutral"

    # Final sentiment
    final_sentiment = "neutral"
    for um in reversed(user_msgs):
        cls = classify_user_message(um["text"])
        if cls != "neutral":
            final_sentiment = cls
            break

    # Correction ratio
    corrections = sum(1 for um in user_msgs if classify_user_message(um["text"]) == "correction")
    correction_ratio = corrections / max(len(user_msgs), 1)

    # Git commits
    git_commits = 0
    for msg in messages:
        if msg.get("type") == "assistant":
            content = msg.get("message", {}).get("content", [])
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "tool_use":
                        if block.get("name") == "Bash":
                            inp = block.get("input", {})
                            cmd = inp.get("command", "") if isinstance(inp, dict) else ""
                            if "git commit" in cmd:
                                git_commits += 1

    score = 0.0
    if final_sentiment == "positive":
        score += 2
    elif final_sentiment == "correction":
        score -= 2
    score -= correction_ratio * 3
    if git_commits > 0:
        score += 1

    return score, final_sentiment


def load_all_sessions(max_sessions=MAX_SESSIONS):
    """Load and parse sessions, sampling if needed."""
    files = _find_jsonl_files(CORPUS_DIR)

    # Filter by size: skip tiny (<10KB) and huge (>50MB)
    sized = [(f, os.path.getsize(f)) for f in files]
    candidates = [(f, s) for f, s in sized if 10_000 < s < 50_000_000]
    print(f"  Found {len(candidates)} candidate files (10KB-50MB)", file=sys.stderr)

    # Sample with project diversity (same approach as other scripts)
    random.seed(42)
    by_project = defaultdict(list)
    for f, size in candidates:
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

    files_with_tools = []
    projects = list(by_project.keys())
    random.shuffle(projects)
    round_num = 0
    while len(files_with_tools) < max_sessions and projects:
        still_have = []
        for proj in projects:
            pfiles = by_project[proj]
            if round_num < len(pfiles):
                files_with_tools.append(pfiles[round_num])
                if len(files_with_tools) >= max_sessions:
                    break
            if round_num + 1 < len(pfiles):
                still_have.append(proj)
        projects = still_have
        round_num += 1

    print(f"  Sampled {len(files_with_tools)} files from {len(by_project)} projects", file=sys.stderr)

    sessions = []
    for fpath, fsize in files_with_tools:
        messages = parse_session(fpath)
        tool_seq = extract_tool_sequence(messages)
        user_msgs = extract_user_messages(messages)

        if len(tool_seq) < 3:
            continue

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

        success_score, final_sentiment = compute_session_success(messages, tool_seq, user_msgs)

        sessions.append({
            "filepath": fpath,
            "session_id": os.path.basename(fpath).replace(".jsonl", ""),
            "project": project_name,
            "messages": messages,
            "tool_sequence": tool_seq,
            "user_msgs": user_msgs,
            "num_tools": len(tool_seq),
            "success_score": success_score,
            "final_sentiment": final_sentiment,
        })

    return sessions


# ============================================================
# TOOL NAME ENCODING
# ============================================================

def build_tool_encoding(sessions):
    """Assign integer IDs to tool names for PrefixSpan."""
    tool_counter = Counter()
    for s in sessions:
        tool_counter.update(s["tool_sequence"])

    # Map tool names to ints (most common first)
    tool_to_id = {}
    id_to_tool = {}
    for idx, (tool, _) in enumerate(tool_counter.most_common()):
        tool_to_id[tool] = idx
        id_to_tool[idx] = tool

    return tool_to_id, id_to_tool, tool_counter


def encode_sequences(sessions, tool_to_id):
    """Convert tool name sequences to integer sequences."""
    encoded = []
    for s in sessions:
        seq = [tool_to_id[t] for t in s["tool_sequence"] if t in tool_to_id]
        if len(seq) >= MIN_PATTERN_LEN:
            encoded.append(seq)
    return encoded


# ============================================================
# PREFIXSPAN MINING
# ============================================================

def run_prefixspan(encoded_sequences, min_support_count):
    """Run PrefixSpan and return frequent patterns.

    Uses topk approach per pattern length to avoid combinatorial explosion.
    """
    print(f"  Running PrefixSpan (min_support={min_support_count}, "
          f"{len(encoded_sequences)} sequences)...", file=sys.stderr)

    ps = PrefixSpan(encoded_sequences)

    # Mine top-k patterns per length to keep output manageable
    all_patterns = []
    TOP_K_PER_LENGTH = 50

    for length in range(MIN_PATTERN_LEN, MAX_PATTERN_LEN + 1):
        ps.minlen = length
        ps.maxlen = length
        # Use topk to get the most frequent patterns of this length
        length_patterns = ps.topk(TOP_K_PER_LENGTH, filter=lambda patt, matches: len(patt) == length)
        # Also filter by minimum support
        length_patterns = [(sup, pat) for sup, pat in length_patterns if sup >= min_support_count]
        print(f"    Length {length}: {len(length_patterns)} patterns (top-{TOP_K_PER_LENGTH}, "
              f"min_support={min_support_count})", file=sys.stderr)
        all_patterns.extend(length_patterns)

    print(f"  Total patterns: {len(all_patterns)}", file=sys.stderr)
    return all_patterns


def decode_patterns(patterns, id_to_tool):
    """Convert integer patterns back to tool names."""
    decoded = []
    for support, pattern in patterns:
        tool_pattern = [id_to_tool[i] for i in pattern]
        decoded.append({
            "support": support,
            "pattern": tool_pattern,
            "length": len(tool_pattern),
            "pattern_str": " -> ".join(tool_pattern),
        })
    return decoded


# ============================================================
# PATTERN ANALYSIS
# ============================================================

def pattern_in_sequence(pattern_ids, sequence):
    """Check if pattern (as subsequence) appears in sequence."""
    idx = 0
    for item in sequence:
        if idx < len(pattern_ids) and item == pattern_ids[idx]:
            idx += 1
    return idx == len(pattern_ids)


def analyze_pattern_session_correlation(decoded_patterns, sessions, encoded_sequences, tool_to_id):
    """Correlate patterns with session success/failure."""
    results = []

    # Split sessions into success tiers
    scores = [s["success_score"] for s in sessions]
    scores_sorted = sorted(scores)
    n = len(scores_sorted)
    q1_threshold = scores_sorted[n // 4] if n > 4 else 0
    q3_threshold = scores_sorted[3 * n // 4] if n > 4 else 0

    # Map sessions to encoded sequences (they should align but we track indices)
    session_encoded_pairs = []
    enc_idx = 0
    for s in sessions:
        seq = [tool_to_id.get(t) for t in s["tool_sequence"] if t in tool_to_id]
        seq = [x for x in seq if x is not None]
        if len(seq) >= MIN_PATTERN_LEN:
            session_encoded_pairs.append((s, seq))

    for dp in decoded_patterns[:100]:  # Top 100 patterns by support
        pattern_ids = [tool_to_id[t] for t in dp["pattern"]]

        sessions_with = []
        sessions_without = []

        for s, seq in session_encoded_pairs:
            if pattern_in_sequence(pattern_ids, seq):
                sessions_with.append(s)
            else:
                sessions_without.append(s)

        if not sessions_with or not sessions_without:
            continue

        avg_score_with = sum(s["success_score"] for s in sessions_with) / len(sessions_with)
        avg_score_without = sum(s["success_score"] for s in sessions_without) / len(sessions_without)
        score_delta = avg_score_with - avg_score_without

        # Count how many high/low success sessions contain the pattern
        high_with = sum(1 for s in sessions_with if s["success_score"] >= q3_threshold)
        low_with = sum(1 for s in sessions_with if s["success_score"] <= q1_threshold)
        high_total = sum(1 for s, _ in session_encoded_pairs if s["success_score"] >= q3_threshold)
        low_total = sum(1 for s, _ in session_encoded_pairs if s["success_score"] <= q1_threshold)

        results.append({
            **dp,
            "sessions_with": len(sessions_with),
            "sessions_without": len(sessions_without),
            "avg_score_with": avg_score_with,
            "avg_score_without": avg_score_without,
            "score_delta": score_delta,
            "pct_high_success": high_with / max(high_total, 1) * 100,
            "pct_low_success": low_with / max(low_total, 1) * 100,
        })

    return results


def analyze_patterns_by_project(decoded_patterns, sessions, tool_to_id):
    """Compare pattern frequency across projects."""
    # Group sessions by project
    project_sessions = defaultdict(list)
    for s in sessions:
        seq = [tool_to_id.get(t) for t in s["tool_sequence"] if t in tool_to_id]
        seq = [x for x in seq if x is not None]
        if len(seq) >= MIN_PATTERN_LEN:
            project_sessions[s["project"]].append((s, seq))

    # Only keep projects with >= 5 sessions
    project_sessions = {p: ss for p, ss in project_sessions.items() if len(ss) >= 5}

    if not project_sessions:
        return {}

    # For top patterns, compute per-project frequency
    results = {}
    for dp in decoded_patterns[:30]:
        pattern_ids = [tool_to_id[t] for t in dp["pattern"]]
        project_freq = {}
        for proj, sess_list in project_sessions.items():
            matches = sum(1 for _, seq in sess_list if pattern_in_sequence(pattern_ids, seq))
            project_freq[proj] = {
                "count": matches,
                "total": len(sess_list),
                "pct": matches / len(sess_list) * 100,
            }
        results[dp["pattern_str"]] = project_freq

    return results


def find_discriminative_patterns(decoded_patterns, sessions, tool_to_id):
    """Find patterns unique to successful or struggling sessions."""
    scores = [s["success_score"] for s in sessions]
    scores_sorted = sorted(scores)
    n = len(scores_sorted)
    median_score = scores_sorted[n // 2]

    success_seqs = []
    struggle_seqs = []

    for s in sessions:
        seq = [tool_to_id.get(t) for t in s["tool_sequence"] if t in tool_to_id]
        seq = [x for x in seq if x is not None]
        if len(seq) < MIN_PATTERN_LEN:
            continue
        if s["success_score"] > median_score:
            success_seqs.append(seq)
        else:
            struggle_seqs.append(seq)

    discriminative = []
    for dp in decoded_patterns:
        pattern_ids = [tool_to_id[t] for t in dp["pattern"]]

        in_success = sum(1 for seq in success_seqs if pattern_in_sequence(pattern_ids, seq))
        in_struggle = sum(1 for seq in struggle_seqs if pattern_in_sequence(pattern_ids, seq))

        pct_success = in_success / max(len(success_seqs), 1) * 100
        pct_struggle = in_struggle / max(len(struggle_seqs), 1) * 100
        bias = pct_success - pct_struggle

        if abs(bias) > 5:  # At least 5pp difference
            discriminative.append({
                **dp,
                "in_success": in_success,
                "in_struggle": in_struggle,
                "pct_success": pct_success,
                "pct_struggle": pct_struggle,
                "bias": bias,
                "favors": "success" if bias > 0 else "struggle",
            })

    discriminative.sort(key=lambda x: abs(x["bias"]), reverse=True)
    return discriminative


# ============================================================
# REPORT GENERATION
# ============================================================

def generate_report(sessions, decoded_patterns, correlation_results,
                    project_patterns, discriminative, tool_counter,
                    id_to_tool, encoded_sequences):
    lines = []
    lines.append("# PrefixSpan Sequential Pattern Mining")
    lines.append("")
    lines.append("**Date**: 2026-03-20")
    lines.append("**Method**: PrefixSpan pattern-growth algorithm on tool call sequences")
    lines.append(f"**Corpus**: {len(sessions)} sessions sampled from third-thoughts corpus")
    lines.append(f"**Total tool calls**: {sum(s['num_tools'] for s in sessions):,}")
    lines.append(f"**Min support**: {MIN_SUPPORT_FRACTION*100:.0f}% of sessions "
                 f"({int(len(encoded_sequences) * MIN_SUPPORT_FRACTION)} sessions)")
    lines.append(f"**Pattern length range**: {MIN_PATTERN_LEN}-{MAX_PATTERN_LEN}")
    lines.append("")
    lines.append("**Reference**: Pei, J. et al. (2004). \"Mining Sequential Patterns by "
                 "Pattern-Growth.\" IEEE TKDE, 16(11).")
    lines.append("")
    lines.append("---")
    lines.append("")

    # Overview
    lines.append("## Dataset Overview")
    lines.append("")
    lines.append(f"- Sessions analyzed: {len(sessions)}")
    lines.append(f"- Encoded sequences (>= {MIN_PATTERN_LEN} tools): {len(encoded_sequences)}")
    lines.append(f"- Distinct tool types: {len(tool_counter)}")
    lines.append(f"- Median sequence length: {sorted(len(s) for s in encoded_sequences)[len(encoded_sequences)//2]}")
    lines.append(f"- Mean sequence length: {sum(len(s) for s in encoded_sequences)/max(len(encoded_sequences),1):.1f}")
    lines.append("")

    # Tool frequency
    lines.append("### Tool Frequency")
    lines.append("")
    lines.append("| Tool | Count | % |")
    lines.append("|------|-------|---|")
    total_tools = sum(tool_counter.values())
    for tool, count in tool_counter.most_common(15):
        lines.append(f"| {tool} | {count:,} | {count/total_tools*100:.1f}% |")
    lines.append("")

    # ── Frequent Patterns ──
    lines.append("---")
    lines.append("")
    lines.append("## Frequent Sequential Patterns")
    lines.append("")
    lines.append("These are ordered subsequences (with gaps allowed) that appear in many sessions.")
    lines.append("A pattern like `Read -> Edit -> Bash` means the agent used Read at some point,")
    lines.append("then later used Edit, then later used Bash -- with potentially other tools in between.")
    lines.append("")

    # Group by length
    by_length = defaultdict(list)
    for dp in decoded_patterns:
        by_length[dp["length"]].append(dp)

    for length in sorted(by_length.keys()):
        pats = by_length[length]
        pats.sort(key=lambda x: -x["support"])
        lines.append(f"### Length-{length} Patterns (top 20)")
        lines.append("")
        lines.append("| Pattern | Support | % Sessions |")
        lines.append("|---------|---------|------------|")
        for dp in pats[:20]:
            pct = dp["support"] / len(encoded_sequences) * 100
            lines.append(f"| {dp['pattern_str']} | {dp['support']} | {pct:.1f}% |")
        lines.append("")

    # ── Success Correlation ──
    lines.append("---")
    lines.append("")
    lines.append("## Pattern-Success Correlation")
    lines.append("")
    lines.append("Do certain sequential patterns correlate with successful vs. struggling sessions?")
    lines.append("Success score combines final user sentiment, correction ratio, and git commits.")
    lines.append("")

    if correlation_results:
        # Top patterns correlated with success
        success_corr = sorted(correlation_results, key=lambda x: -x["score_delta"])
        lines.append("### Patterns Most Associated with Success")
        lines.append("")
        lines.append("| Pattern | Support | Avg Score (with) | Avg Score (without) | Delta |")
        lines.append("|---------|---------|-----------------|--------------------|---------| ")
        for cr in success_corr[:15]:
            lines.append(f"| {cr['pattern_str']} | {cr['sessions_with']} | "
                         f"{cr['avg_score_with']:+.2f} | {cr['avg_score_without']:+.2f} | "
                         f"{cr['score_delta']:+.2f} |")
        lines.append("")

        # Top patterns correlated with struggle
        struggle_corr = sorted(correlation_results, key=lambda x: x["score_delta"])
        lines.append("### Patterns Most Associated with Struggle")
        lines.append("")
        lines.append("| Pattern | Support | Avg Score (with) | Avg Score (without) | Delta |")
        lines.append("|---------|---------|-----------------|--------------------|---------| ")
        for cr in struggle_corr[:15]:
            lines.append(f"| {cr['pattern_str']} | {cr['sessions_with']} | "
                         f"{cr['avg_score_with']:+.2f} | {cr['avg_score_without']:+.2f} | "
                         f"{cr['score_delta']:+.2f} |")
        lines.append("")

    # ── Discriminative Patterns ──
    lines.append("---")
    lines.append("")
    lines.append("## Discriminative Patterns")
    lines.append("")
    lines.append("Patterns that appear disproportionately in successful vs. struggling sessions.")
    lines.append("")

    if discriminative:
        success_disc = [d for d in discriminative if d["favors"] == "success"]
        struggle_disc = [d for d in discriminative if d["favors"] == "struggle"]

        if success_disc:
            lines.append("### Patterns Favoring Success")
            lines.append("")
            lines.append("| Pattern | % in Success | % in Struggle | Bias |")
            lines.append("|---------|-------------|--------------|------|")
            for d in success_disc[:15]:
                lines.append(f"| {d['pattern_str']} | {d['pct_success']:.1f}% | "
                             f"{d['pct_struggle']:.1f}% | +{d['bias']:.1f}pp |")
            lines.append("")

        if struggle_disc:
            lines.append("### Patterns Favoring Struggle")
            lines.append("")
            lines.append("| Pattern | % in Success | % in Struggle | Bias |")
            lines.append("|---------|-------------|--------------|------|")
            for d in struggle_disc[:15]:
                lines.append(f"| {d['pattern_str']} | {d['pct_success']:.1f}% | "
                             f"{d['pct_struggle']:.1f}% | {d['bias']:.1f}pp |")
            lines.append("")

    # ── Cross-Project Patterns ──
    lines.append("---")
    lines.append("")
    lines.append("## Cross-Project Pattern Comparison")
    lines.append("")

    if project_patterns:
        # Find patterns with highest variance across projects
        pattern_variances = []
        for pat_str, proj_freq in project_patterns.items():
            pcts = [v["pct"] for v in proj_freq.values()]
            if len(pcts) >= 2:
                variance = sum((p - sum(pcts)/len(pcts))**2 for p in pcts) / len(pcts)
                pattern_variances.append((pat_str, variance, proj_freq))

        pattern_variances.sort(key=lambda x: -x[1])

        lines.append("### Most Variable Patterns Across Projects")
        lines.append("")
        lines.append("These patterns show the greatest variation in frequency across projects,")
        lines.append("suggesting project-specific workflows.")
        lines.append("")

        for pat_str, var, proj_freq in pattern_variances[:10]:
            lines.append(f"**{pat_str}** (variance: {var:.1f})")
            lines.append("")
            lines.append("| Project | Sessions with Pattern | Total | % |")
            lines.append("|---------|----------------------|-------|---|")
            for proj in sorted(proj_freq.keys()):
                pf = proj_freq[proj]
                lines.append(f"| {proj[:30]} | {pf['count']} | {pf['total']} | {pf['pct']:.0f}% |")
            lines.append("")

        # Universal patterns (high frequency everywhere)
        lines.append("### Universal Patterns (high frequency in all projects)")
        lines.append("")
        universal = []
        for pat_str, proj_freq in project_patterns.items():
            pcts = [v["pct"] for v in proj_freq.values()]
            if pcts and min(pcts) > 30:  # Present in >30% of sessions in every project
                universal.append((pat_str, min(pcts), sum(pcts)/len(pcts)))

        universal.sort(key=lambda x: -x[2])
        if universal:
            lines.append("| Pattern | Min % | Mean % |")
            lines.append("|---------|-------|--------|")
            for pat_str, min_pct, mean_pct in universal[:15]:
                lines.append(f"| {pat_str} | {min_pct:.0f}% | {mean_pct:.0f}% |")
        else:
            lines.append("No patterns found with >30% frequency in all projects.")
        lines.append("")

    # ── Summary ──
    lines.append("---")
    lines.append("")
    lines.append("## Summary of Key Findings")
    lines.append("")

    lines.append(f"1. **Total frequent patterns discovered**: {len(decoded_patterns)}")
    by_len_counts = Counter(dp["length"] for dp in decoded_patterns)
    lines.append(f"2. **Patterns by length**: " + ", ".join(
        f"len-{l}: {c}" for l, c in sorted(by_len_counts.items())))

    # Most supported pattern
    if decoded_patterns:
        top = max(decoded_patterns, key=lambda x: x["support"])
        lines.append(f"3. **Most frequent pattern**: `{top['pattern_str']}` "
                     f"(support: {top['support']}, {top['support']/len(encoded_sequences)*100:.1f}%)")

    # Longest pattern with decent support
    long_pats = [dp for dp in decoded_patterns if dp["length"] >= 6]
    if long_pats:
        longest = max(long_pats, key=lambda x: x["support"])
        lines.append(f"4. **Most frequent long pattern (len>={longest['length']})**: "
                     f"`{longest['pattern_str']}` (support: {longest['support']})")

    if discriminative:
        top_disc = discriminative[0]
        lines.append(f"5. **Most discriminative pattern**: `{top_disc['pattern_str']}` "
                     f"(bias: {top_disc['bias']:+.1f}pp toward {top_disc['favors']})")

    lines.append("")

    return "\n".join(lines)


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    print("Loading sessions...", file=sys.stderr)
    sessions = load_all_sessions(max_sessions=MAX_SESSIONS)
    print(f"Loaded {len(sessions)} sessions", file=sys.stderr)

    print("Encoding tool sequences...", file=sys.stderr)
    tool_to_id, id_to_tool, tool_counter = build_tool_encoding(sessions)
    encoded_sequences = encode_sequences(sessions, tool_to_id)
    print(f"Encoded {len(encoded_sequences)} sequences, {len(tool_to_id)} tool types", file=sys.stderr)

    min_support_count = max(int(len(encoded_sequences) * MIN_SUPPORT_FRACTION), 2)
    print(f"Min support count: {min_support_count}", file=sys.stderr)

    print("Running PrefixSpan...", file=sys.stderr)
    raw_patterns = run_prefixspan(encoded_sequences, min_support_count)
    decoded_patterns = decode_patterns(raw_patterns, id_to_tool)
    decoded_patterns.sort(key=lambda x: (-x["length"], -x["support"]))
    print(f"Decoded {len(decoded_patterns)} patterns", file=sys.stderr)

    print("Analyzing pattern-success correlation...", file=sys.stderr)
    correlation_results = analyze_pattern_session_correlation(
        decoded_patterns, sessions, encoded_sequences, tool_to_id)

    print("Analyzing cross-project patterns...", file=sys.stderr)
    project_patterns = analyze_patterns_by_project(decoded_patterns, sessions, tool_to_id)

    print("Finding discriminative patterns...", file=sys.stderr)
    discriminative = find_discriminative_patterns(decoded_patterns, sessions, tool_to_id)

    print("Generating report...", file=sys.stderr)
    report = generate_report(
        sessions, decoded_patterns, correlation_results,
        project_patterns, discriminative, tool_counter,
        id_to_tool, encoded_sequences,
    )

    # Write markdown report
    report_path = OUTPUT_DIR / "prefixspan-mining.md"
    with open(report_path, "w") as f:
        f.write(report)
    print(f"Report written to {report_path}", file=sys.stderr)

    # Write JSON data
    json_output = {
        "sessions_analyzed": len(sessions),
        "encoded_sequences": len(encoded_sequences),
        "total_patterns": len(decoded_patterns),
        "min_support_fraction": MIN_SUPPORT_FRACTION,
        "min_support_count": min_support_count,
        "patterns_by_length": dict(Counter(dp["length"] for dp in decoded_patterns)),
        "top_patterns": [
            {"pattern": dp["pattern"], "support": dp["support"], "length": dp["length"]}
            for dp in sorted(decoded_patterns, key=lambda x: -x["support"])[:50]
        ],
        "discriminative_patterns": [
            {"pattern": d["pattern"], "bias": d["bias"], "favors": d["favors"],
             "pct_success": d["pct_success"], "pct_struggle": d["pct_struggle"]}
            for d in discriminative[:20]
        ],
        "tool_counts": dict(tool_counter.most_common()),
    }

    json_path = OUTPUT_DIR / "prefixspan-mining.json"
    with open(json_path, "w") as f:
        json.dump(json_output, f, indent=2, default=str)
    print(f"JSON data written to {json_path}", file=sys.stderr)
