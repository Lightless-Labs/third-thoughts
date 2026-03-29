#!/usr/bin/env python3
"""
Tool Sequence Mining - Quantitative analysis of Claude Code tool call patterns.

Analyzes JSONL session transcripts from Claude Code to extract:
1. Tool transition probability matrix
2. Tool sequences preceding errors/corrections
3. Session success heuristics
4. Tool call volume over session lifetime
"""

import json
import glob
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

# ============================================================
# DATA LOADING
# ============================================================

CORPUS_DIR = os.environ.get(
    "CORPUS_DIR",
    os.environ.get("MIDDENS_CORPUS", "corpus/"),
)


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
    """Extract ordered sequence of tool calls from session messages.

    Returns list of dicts: {tool_name, timestamp, message_index, assistant_msg_index}
    Also returns raw messages for context analysis.
    """
    tool_calls = []
    assistant_msg_idx = 0

    for msg in messages:
        if msg.get("type") == "assistant":
            content = msg.get("message", {}).get("content", [])
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "tool_use":
                        tool_calls.append({
                            "tool": block.get("name", "unknown"),
                            "timestamp": msg.get("timestamp", ""),
                            "assistant_msg_idx": assistant_msg_idx,
                            "id": block.get("id", ""),
                        })
            assistant_msg_idx += 1

    return tool_calls


def extract_user_messages(messages):
    """Extract genuine human-typed user messages (not tool results or continuations)."""
    user_msgs = []
    for i, msg in enumerate(messages):
        if msg.get("type") not in ("human", "user"):
            continue

        content = msg.get("message", {}).get("content", "")

        # Filter out tool_result blocks -- these are automatic, not human-typed
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

        # Skip empty messages
        if not content.strip():
            continue

        # Skip continuation markers (auto-generated)
        if "continued from a previous conversation" in content.lower():
            continue

        # Skip system/command messages and auto-generated content
        stripped = content.strip()
        if stripped.startswith("<command-"):
            continue
        if stripped.startswith("<local-command-"):
            continue
        if stripped.startswith("<teammate-message"):
            continue
        if stripped.startswith("Stop hook feedback"):
            continue
        if stripped.startswith("[Request interrupted"):
            continue
        if stripped.startswith("You are a security classifier"):
            continue
        if stripped.startswith("You are Boucle"):
            continue
        # Skip slash command invocations (system-injected prompt content)
        if stripped.startswith("# /") and len(stripped) > 3:
            continue
        # Skip very short messages (< 10 chars) -- too ambiguous to classify
        if len(stripped) < 10:
            continue

        user_msgs.append({
            "text": content,
            "index": i,
            "timestamp": msg.get("timestamp", ""),
        })
    return user_msgs


def _find_jsonl_files(root):
    """Find all .jsonl files under root, following symlinks."""
    results = []
    for dirpath, dirnames, filenames in os.walk(root, followlinks=True):
        for fn in filenames:
            if fn.endswith(".jsonl"):
                results.append(os.path.join(dirpath, fn))
    return sorted(results)


def load_all_sessions():
    """Load and parse all session files from the corpus."""
    files = _find_jsonl_files(CORPUS_DIR)
    sessions = []

    for f in files:
        messages = parse_session(f)
        tool_calls = extract_tool_sequence(messages)
        user_msgs = extract_user_messages(messages)

        if len(tool_calls) >= 2:  # Need at least 2 for transitions
            # Derive project name from directory structure
            rel = os.path.relpath(f, CORPUS_DIR)
            parts = rel.split(os.sep)
            # e.g. claude-code/projects/-Users-<operator>-.../UUID.jsonl
            # Use the project directory name as project identifier
            project_name = "unknown"
            if "projects" in parts:
                proj_idx = parts.index("projects")
                if proj_idx + 1 < len(parts):
                    project_name = parts[proj_idx + 1]
            sessions.append({
                "filepath": f,
                "session_id": os.path.basename(f).replace(".jsonl", ""),
                "project": project_name,
                "messages": messages,
                "tool_calls": tool_calls,
                "user_msgs": user_msgs,
                "num_tools": len(tool_calls),
            })

    return sessions


# ============================================================
# ANALYSIS 1: TOOL TRANSITION MATRIX
# ============================================================

def analyze_transitions(sessions):
    """Build transition probability matrix from tool sequences."""
    transitions = Counter()
    tool_counts = Counter()
    bigrams = Counter()
    trigrams = Counter()

    for session in sessions:
        tools = [tc["tool"] for tc in session["tool_calls"]]

        for tool in tools:
            tool_counts[tool] += 1

        for i in range(len(tools) - 1):
            transitions[(tools[i], tools[i + 1])] += 1
            bigrams[(tools[i], tools[i + 1])] += 1

        for i in range(len(tools) - 2):
            trigrams[(tools[i], tools[i + 1], tools[i + 2])] += 1

    # Compute probabilities
    from_counts = Counter()
    for (a, b), count in transitions.items():
        from_counts[a] += count

    transition_probs = {}
    for (a, b), count in transitions.items():
        transition_probs[(a, b)] = count / from_counts[a]

    # Self-transition rates
    self_transitions = {}
    for tool in tool_counts:
        if (tool, tool) in transitions:
            self_transitions[tool] = transitions[(tool, tool)] / from_counts.get(tool, 1)
        else:
            self_transitions[tool] = 0.0

    return {
        "transitions": transitions,
        "transition_probs": transition_probs,
        "tool_counts": tool_counts,
        "bigrams": bigrams,
        "trigrams": trigrams,
        "self_transitions": self_transitions,
        "from_counts": from_counts,
    }


def format_transition_analysis(result):
    """Format transition analysis as markdown."""
    lines = []
    lines.append("## Analysis 1: Tool Transition Matrix\n")

    # Overall tool frequency
    lines.append("### Tool Usage Frequency\n")
    lines.append("| Tool | Count | % of Total |")
    lines.append("|------|-------|-----------|")
    total = sum(result["tool_counts"].values())
    for tool, count in result["tool_counts"].most_common():
        pct = count / total * 100
        lines.append(f"| {tool} | {count:,} | {pct:.1f}% |")
    lines.append(f"\n**Total tool calls analyzed**: {total:,}\n")

    # Top transitions
    lines.append("### Top 30 Tool Transitions (bigrams)\n")
    lines.append("| From | To | Count | P(To|From) |")
    lines.append("|------|-----|-------|-----------|")
    for (a, b), count in result["bigrams"].most_common(30):
        prob = result["transition_probs"][(a, b)]
        lines.append(f"| {a} | {b} | {count:,} | {prob:.3f} |")

    # Self-transition rates
    lines.append("\n### Self-Transition Rates (tool followed by itself)\n")
    lines.append("High self-transition = agent uses tool repeatedly in sequence.\n")
    lines.append("| Tool | Self-Rate | Interpretation |")
    lines.append("|------|----------|---------------|")
    for tool, rate in sorted(result["self_transitions"].items(), key=lambda x: -x[1]):
        if result["tool_counts"][tool] >= 20:  # Only show tools with significant usage
            if rate > 0.5:
                interp = "Heavily chained"
            elif rate > 0.3:
                interp = "Often chained"
            elif rate > 0.1:
                interp = "Sometimes chained"
            else:
                interp = "Rarely chained"
            lines.append(f"| {tool} | {rate:.3f} | {interp} |")

    # Top trigrams
    lines.append("\n### Top 25 Tool Trigrams (3-step sequences)\n")
    lines.append("| Step 1 | Step 2 | Step 3 | Count |")
    lines.append("|--------|--------|--------|-------|")
    for (a, b, c), count in result["trigrams"].most_common(25):
        lines.append(f"| {a} | {b} | {c} | {count:,} |")

    # Canonical workflows - what tools tend to start and end sequences
    lines.append("\n### First and Last Tools in Sessions\n")
    first_tools = Counter()
    last_tools = Counter()
    for session in sessions:
        tools = [tc["tool"] for tc in session["tool_calls"]]
        if tools:
            first_tools[tools[0]] += 1
            last_tools[tools[-1]] += 1

    lines.append("#### First tool used in session\n")
    lines.append("| Tool | Count | % |")
    lines.append("|------|-------|---|")
    total_sessions = sum(first_tools.values())
    for tool, count in first_tools.most_common(10):
        lines.append(f"| {tool} | {count} | {count/total_sessions*100:.1f}% |")

    lines.append("\n#### Last tool used in session\n")
    lines.append("| Tool | Count | % |")
    lines.append("|------|-------|---|")
    for tool, count in last_tools.most_common(10):
        lines.append(f"| {tool} | {count} | {count/total_sessions*100:.1f}% |")

    # Strongest non-obvious transitions
    lines.append("\n### Strongest Non-Self Transitions (P > 0.15, count > 10)\n")
    lines.append("These are the most deterministic tool sequences -- when tool A fires, tool B is highly likely next.\n")
    lines.append("| From | To | P(To|From) | Count |")
    lines.append("|------|-----|-----------|-------|")
    strong = []
    for (a, b), prob in result["transition_probs"].items():
        if a != b and prob > 0.15 and result["bigrams"][(a, b)] > 10:
            strong.append((a, b, prob, result["bigrams"][(a, b)]))
    strong.sort(key=lambda x: -x[2])
    for a, b, prob, count in strong[:20]:
        lines.append(f"| {a} | {b} | {prob:.3f} | {count} |")

    return "\n".join(lines)


# ============================================================
# ANALYSIS 2: TOOL SEQUENCES PRECEDING ERRORS/CORRECTIONS
# ============================================================

# Correction patterns: phrases that strongly indicate the user is correcting the agent.
# Each has a weight. We require a threshold to classify as correction.
CORRECTION_PATTERNS = [
    (r"\bno,\s", 2),                   # "no, that's wrong" - comma after no is strong signal
    (r"\bno\.\s", 2),                  # "no. do X instead"
    (r"^no$", 2),                      # just "no"
    (r"\bwrong\b", 2),
    (r"\bnot what i\b", 3),
    (r"\bwhy did you\b", 3),
    (r"\binstead of\b", 1),
    (r"\bdon'?t do\b", 2),
    (r"\bstop\b", 1),
    (r"\bundo\b", 2),
    (r"\brevert\b", 2),
    (r"\bthat'?s not\b", 2),
    (r"\bincorrect\b", 2),
    (r"\bwhat are you doing\b", 3),
    (r"\bplease don'?t\b", 2),
    (r"\bi said\b", 1),
    (r"\bi asked for\b", 2),
    (r"\bnot that\b", 1),
    (r"\byou broke\b", 3),
    (r"\bbroken\b", 1),
    (r"\bthat'?s wrong\b", 3),
    (r"\bwhat the\b", 2),
    (r"\byou'?re doing it wrong\b", 3),
    (r"\bnot right\b", 2),
    (r"\bi didn'?t ask\b", 3),
    (r"\brollback\b", 2),
    (r"\byou missed\b", 2),
    (r"\byou forgot\b", 2),
]

POSITIVE_PATTERNS = [
    (r"\bthanks?\b", 1),
    (r"\bthank you\b", 2),
    (r"\bgreat\b", 1),
    (r"\bperfect\b", 2),
    (r"\bgood job\b", 2),
    (r"\bnice\b", 1),
    (r"\bexcellent\b", 2),
    (r"\bawesome\b", 2),
    (r"\blooks good\b", 2),
    (r"\bwell done\b", 2),
    (r"\blgtm\b", 3),
    (r"\bexactly\b", 1),
    (r"\bship it\b", 3),
    (r"\bgo ahead\b", 1),
    (r"\bnice work\b", 2),
    (r"^yes$", 1),
    (r"\byes[!.]\b", 1),
]


def classify_user_message(text):
    """Classify user message as correction, positive, or neutral.

    Uses weighted pattern matching with threshold to avoid false positives.
    """
    text_lower = text.lower().strip()

    # Skip very short messages
    if len(text_lower) < 5:
        return "neutral"

    # Long messages (> 500 chars) are typically task descriptions, not feedback
    if len(text_lower) > 500:
        return "neutral"

    correction_score = sum(
        weight for pattern, weight in CORRECTION_PATTERNS
        if re.search(pattern, text_lower)
    )
    positive_score = sum(
        weight for pattern, weight in POSITIVE_PATTERNS
        if re.search(pattern, text_lower)
    )

    # Require a minimum threshold to classify
    if correction_score >= 2 and correction_score > positive_score:
        return "correction"
    elif positive_score >= 2 and positive_score > correction_score:
        return "positive"
    return "neutral"


def analyze_correction_sequences(sessions):
    """Find tool sequences that precede user corrections vs. positive feedback."""
    # Build interleaved sequences: tool calls between user messages
    pre_correction_sequences = []
    pre_positive_sequences = []
    pre_neutral_sequences = []

    correction_examples = []

    for session in sessions:
        messages = session["messages"]
        tool_calls = session["tool_calls"]
        user_msgs = session["user_msgs"]

        if not tool_calls or not user_msgs:
            continue

        # Build timeline: assign tool calls to the gap before each user message
        # We need message-level indices
        # Strategy: for each user message, find tool calls that occurred
        # since the previous user message

        # Get indices of user messages in the raw message list
        user_indices = [um["index"] for um in user_msgs]

        # For each user message (except first), collect tool calls between
        # previous user message and this one
        for u_idx in range(1, len(user_msgs)):
            prev_user_idx = user_msgs[u_idx - 1]["index"]
            curr_user_idx = user_msgs[u_idx]["index"]

            # Find assistant tool calls between these two user messages
            tools_between = []
            for msg in messages[prev_user_idx + 1 : curr_user_idx]:
                if msg.get("type") == "assistant":
                    content = msg.get("message", {}).get("content", [])
                    if isinstance(content, list):
                        for block in content:
                            if isinstance(block, dict) and block.get("type") == "tool_use":
                                tools_between.append(block.get("name", "unknown"))

            if not tools_between:
                continue

            classification = classify_user_message(user_msgs[u_idx]["text"])

            # Take last N tools before user message
            window = tools_between[-5:] if len(tools_between) > 5 else tools_between

            if classification == "correction":
                pre_correction_sequences.append(tuple(window))
                if len(correction_examples) < 20:
                    correction_examples.append({
                        "tools": window,
                        "user_text": user_msgs[u_idx]["text"][:200],
                        "session": session["session_id"],
                    })
            elif classification == "positive":
                pre_positive_sequences.append(tuple(window))
            else:
                pre_neutral_sequences.append(tuple(window))

    return {
        "pre_correction": pre_correction_sequences,
        "pre_positive": pre_positive_sequences,
        "pre_neutral": pre_neutral_sequences,
        "correction_examples": correction_examples,
    }


def format_correction_analysis(result):
    """Format correction sequence analysis as markdown."""
    lines = []
    lines.append("## Analysis 2: Tool Sequences Preceding Corrections\n")

    pre_c = result["pre_correction"]
    pre_p = result["pre_positive"]
    pre_n = result["pre_neutral"]

    lines.append(f"- Sequences before **corrections**: {len(pre_c)}")
    lines.append(f"- Sequences before **positive feedback**: {len(pre_p)}")
    lines.append(f"- Sequences before **neutral messages**: {len(pre_n)}")
    lines.append("")

    # Tool frequency before corrections vs positive
    lines.append("### Tool Frequency Before Corrections vs. Positive Feedback\n")

    correction_tools = Counter()
    for seq in pre_c:
        for tool in seq:
            correction_tools[tool] += 1

    positive_tools = Counter()
    for seq in pre_p:
        for tool in seq:
            positive_tools[tool] += 1

    all_tools_in_both = set(correction_tools.keys()) | set(positive_tools.keys())

    total_c = sum(correction_tools.values()) or 1
    total_p = sum(positive_tools.values()) or 1

    lines.append("| Tool | % Before Corrections | % Before Positive | Correction Bias |")
    lines.append("|------|---------------------|-------------------|----------------|")

    tool_bias = []
    for tool in all_tools_in_both:
        pct_c = correction_tools[tool] / total_c * 100
        pct_p = positive_tools[tool] / total_p * 100
        bias = pct_c - pct_p
        tool_bias.append((tool, pct_c, pct_p, bias))

    tool_bias.sort(key=lambda x: -x[3])
    for tool, pct_c, pct_p, bias in tool_bias:
        if correction_tools[tool] + positive_tools[tool] >= 10:
            sign = "+" if bias > 0 else ""
            lines.append(f"| {tool} | {pct_c:.1f}% | {pct_p:.1f}% | {sign}{bias:.1f}pp |")

    # Last tool before correction vs positive
    lines.append("\n### Last Tool Before User Response\n")
    lines.append("What was the agent doing RIGHT before the user spoke?\n")

    last_before_c = Counter()
    for seq in pre_c:
        if seq:
            last_before_c[seq[-1]] += 1

    last_before_p = Counter()
    for seq in pre_p:
        if seq:
            last_before_p[seq[-1]] += 1

    total_lc = sum(last_before_c.values()) or 1
    total_lp = sum(last_before_p.values()) or 1

    lines.append("| Tool | % Last Before Correction | % Last Before Positive | Bias |")
    lines.append("|------|------------------------|----------------------|------|")

    all_last = set(last_before_c.keys()) | set(last_before_p.keys())
    last_bias = []
    for tool in all_last:
        pct_c = last_before_c[tool] / total_lc * 100
        pct_p = last_before_p[tool] / total_lp * 100
        bias = pct_c - pct_p
        last_bias.append((tool, pct_c, pct_p, bias))

    last_bias.sort(key=lambda x: -x[3])
    for tool, pct_c, pct_p, bias in last_bias:
        if last_before_c[tool] + last_before_p[tool] >= 5:
            sign = "+" if bias > 0 else ""
            lines.append(f"| {tool} | {pct_c:.1f}% | {pct_p:.1f}% | {sign}{bias:.1f}pp |")

    # Common sequences before corrections
    lines.append("\n### Most Common Sequences Before Corrections\n")
    lines.append("| Sequence | Count |")
    lines.append("|----------|-------|")
    seq_counts = Counter(pre_c)
    for seq, count in seq_counts.most_common(15):
        seq_str = " -> ".join(seq)
        lines.append(f"| {seq_str} | {count} |")

    # Common sequences before positive
    lines.append("\n### Most Common Sequences Before Positive Feedback\n")
    lines.append("| Sequence | Count |")
    lines.append("|----------|-------|")
    seq_counts_p = Counter(pre_p)
    for seq, count in seq_counts_p.most_common(15):
        seq_str = " -> ".join(seq)
        lines.append(f"| {seq_str} | {count} |")

    # Correction examples
    lines.append("\n### Sample Correction Examples\n")
    for ex in result["correction_examples"][:10]:
        lines.append(f"- **Tools**: {' -> '.join(ex['tools'])}")
        lines.append(f"  **User said**: \"{ex['user_text'][:150]}\"")
        lines.append(f"  **Session**: `{ex['session']}`")
        lines.append("")

    return "\n".join(lines)


# ============================================================
# ANALYSIS 3: SESSION SUCCESS HEURISTICS
# ============================================================

def analyze_session_success(sessions):
    """Classify sessions by success proxy metrics and compare tool patterns."""
    session_metrics = []

    for session in sessions:
        user_msgs = session["user_msgs"]
        tool_calls = session["tool_calls"]
        messages = session["messages"]

        if not user_msgs or not tool_calls:
            continue

        # Metric 1: Final user sentiment
        final_sentiment = "neutral"
        for um in reversed(user_msgs):
            cls = classify_user_message(um["text"])
            if cls != "neutral":
                final_sentiment = cls
                break

        # Metric 2: Correction ratio
        total_user = len(user_msgs)
        corrections = sum(1 for um in user_msgs if classify_user_message(um["text"]) == "correction")
        correction_ratio = corrections / max(total_user, 1)

        # Metric 3: Git commits made
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

        # Metric 4: Tool diversity
        unique_tools = set(tc["tool"] for tc in tool_calls)
        tool_diversity = len(unique_tools)

        # Tool usage distribution
        tool_dist = Counter(tc["tool"] for tc in tool_calls)

        # Composite success score
        # Higher = better: positive sentiment, low correction ratio, git commits
        success_score = 0
        if final_sentiment == "positive":
            success_score += 2
        elif final_sentiment == "correction":
            success_score -= 2
        success_score -= correction_ratio * 3
        if git_commits > 0:
            success_score += 1

        session_metrics.append({
            "session_id": session["session_id"],
            "project": session["project"],
            "num_tools": session["num_tools"],
            "num_user_msgs": total_user,
            "corrections": corrections,
            "correction_ratio": correction_ratio,
            "final_sentiment": final_sentiment,
            "git_commits": git_commits,
            "tool_diversity": tool_diversity,
            "tool_dist": tool_dist,
            "success_score": success_score,
            "unique_tools": unique_tools,
        })

    return session_metrics


def format_success_analysis(session_metrics):
    """Format session success analysis as markdown."""
    lines = []
    lines.append("## Analysis 3: Session Success Heuristics\n")

    # Split into high/low success
    sorted_sessions = sorted(session_metrics, key=lambda x: x["success_score"])
    n = len(sorted_sessions)

    # Use quartiles
    q1 = n // 4
    q3 = 3 * n // 4

    low_success = sorted_sessions[:q1]
    high_success = sorted_sessions[q3:]

    lines.append(f"**Total sessions with tool calls**: {n}")
    lines.append(f"**Bottom quartile (low success)**: {len(low_success)} sessions")
    lines.append(f"**Top quartile (high success)**: {len(high_success)} sessions\n")

    # Score distribution
    scores = [s["success_score"] for s in sorted_sessions]
    lines.append(f"**Score range**: {min(scores):.1f} to {max(scores):.1f}")
    lines.append(f"**Median score**: {scores[n//2]:.1f}\n")

    # Compare metrics between high/low
    lines.append("### High vs. Low Success Session Comparison\n")
    lines.append("| Metric | Low Success (Q1) | High Success (Q4) |")
    lines.append("|--------|-----------------|------------------|")

    def avg(lst, key):
        vals = [s[key] for s in lst]
        return sum(vals) / max(len(vals), 1)

    lines.append(f"| Avg tool calls | {avg(low_success, 'num_tools'):.1f} | {avg(high_success, 'num_tools'):.1f} |")
    lines.append(f"| Avg user messages | {avg(low_success, 'num_user_msgs'):.1f} | {avg(high_success, 'num_user_msgs'):.1f} |")
    lines.append(f"| Avg correction ratio | {avg(low_success, 'correction_ratio'):.3f} | {avg(high_success, 'correction_ratio'):.3f} |")
    lines.append(f"| Avg tool diversity | {avg(low_success, 'tool_diversity'):.1f} | {avg(high_success, 'tool_diversity'):.1f} |")
    lines.append(f"| Avg git commits | {avg(low_success, 'git_commits'):.1f} | {avg(high_success, 'git_commits'):.1f} |")

    # Tool usage comparison
    lines.append("\n### Tool Usage: High vs Low Success Sessions\n")

    low_tools = Counter()
    high_tools = Counter()
    for s in low_success:
        for tool, count in s["tool_dist"].items():
            low_tools[tool] += count
    for s in high_success:
        for tool, count in s["tool_dist"].items():
            high_tools[tool] += count

    total_low = sum(low_tools.values()) or 1
    total_high = sum(high_tools.values()) or 1

    all_tools_sh = set(low_tools.keys()) | set(high_tools.keys())

    lines.append("| Tool | % in Low Success | % in High Success | Delta |")
    lines.append("|------|-----------------|------------------|-------|")

    tool_deltas = []
    for tool in all_tools_sh:
        pct_low = low_tools[tool] / total_low * 100
        pct_high = high_tools[tool] / total_high * 100
        delta = pct_high - pct_low
        tool_deltas.append((tool, pct_low, pct_high, delta))

    tool_deltas.sort(key=lambda x: -abs(x[3]))
    for tool, pct_low, pct_high, delta in tool_deltas:
        if low_tools[tool] + high_tools[tool] >= 10:
            sign = "+" if delta > 0 else ""
            lines.append(f"| {tool} | {pct_low:.1f}% | {pct_high:.1f}% | {sign}{delta:.1f}pp |")

    # Final sentiment distribution
    lines.append("\n### Final Sentiment Distribution\n")
    sentiments = Counter(s["final_sentiment"] for s in session_metrics)
    lines.append("| Sentiment | Count | % |")
    lines.append("|-----------|-------|---|")
    for sent, count in sentiments.most_common():
        lines.append(f"| {sent} | {count} | {count/n*100:.1f}% |")

    # Correction ratio distribution
    lines.append("\n### Correction Ratio Distribution\n")
    lines.append("| Range | Count | % |")
    lines.append("|-------|-------|---|")
    brackets = [(0, 0.05, "0-5%"), (0.05, 0.15, "5-15%"), (0.15, 0.30, "15-30%"), (0.30, 0.50, "30-50%"), (0.50, 1.01, "50%+")]
    for lo, hi, label in brackets:
        count = sum(1 for s in session_metrics if lo <= s["correction_ratio"] < hi)
        lines.append(f"| {label} | {count} | {count/n*100:.1f}% |")

    # Tools unique to high-success or low-success
    lines.append("\n### Tool Presence in Sessions\n")
    lines.append("How often does each tool appear in high vs low success sessions?\n")
    lines.append("| Tool | Present in Low % | Present in High % |")
    lines.append("|------|-----------------|------------------|")

    for tool in all_tools_sh:
        in_low = sum(1 for s in low_success if tool in s["unique_tools"])
        in_high = sum(1 for s in high_success if tool in s["unique_tools"])
        pct_low = in_low / max(len(low_success), 1) * 100
        pct_high = in_high / max(len(high_success), 1) * 100
        if in_low + in_high >= 3:
            lines.append(f"| {tool} | {pct_low:.0f}% | {pct_high:.0f}% |")

    return "\n".join(lines)


# ============================================================
# ANALYSIS 4: TOOL CALL VOLUME OVER SESSION LIFETIME
# ============================================================

def analyze_session_lifetime(sessions):
    """Analyze how tool call density changes over session lifetime."""
    # Normalize each session to 10 deciles
    NUM_BINS = 10

    # Per-bin aggregates across all sessions
    bin_counts = defaultdict(list)  # bin_index -> [count per session]
    bin_tool_types = defaultdict(Counter)  # bin_index -> Counter of tools

    session_lengths = []

    for session in sessions:
        tool_calls = session["tool_calls"]
        n = len(tool_calls)
        if n < NUM_BINS:
            continue

        session_lengths.append(n)

        # Divide into bins
        bin_size = n / NUM_BINS
        for bin_idx in range(NUM_BINS):
            start = int(bin_idx * bin_size)
            end = int((bin_idx + 1) * bin_size)
            bin_tools = tool_calls[start:end]
            bin_counts[bin_idx].append(len(bin_tools))
            for tc in bin_tools:
                bin_tool_types[bin_idx][tc["tool"]] += 1

    # Also analyze by absolute position (first N, last N)
    first_5_tools = Counter()
    last_5_tools = Counter()
    for session in sessions:
        tools = [tc["tool"] for tc in session["tool_calls"]]
        for t in tools[:5]:
            first_5_tools[t] += 1
        for t in tools[-5:]:
            last_5_tools[t] += 1

    return {
        "bin_counts": bin_counts,
        "bin_tool_types": bin_tool_types,
        "session_lengths": session_lengths,
        "first_5_tools": first_5_tools,
        "last_5_tools": last_5_tools,
        "num_bins": NUM_BINS,
    }


def format_lifetime_analysis(result):
    """Format session lifetime analysis as markdown."""
    lines = []
    lines.append("## Analysis 4: Tool Call Volume Over Session Lifetime\n")

    session_lengths = result["session_lengths"]
    if not session_lengths:
        lines.append("Insufficient data for lifetime analysis.")
        return "\n".join(lines)

    lines.append(f"**Sessions analyzed** (>= 10 tool calls): {len(session_lengths)}")
    lines.append(f"**Median session length**: {sorted(session_lengths)[len(session_lengths)//2]} tool calls")
    lines.append(f"**Mean session length**: {sum(session_lengths)/len(session_lengths):.0f} tool calls")
    lines.append(f"**Max session length**: {max(session_lengths)} tool calls\n")

    # Text-based density chart
    lines.append("### Tool Call Density by Session Decile\n")
    lines.append("Each decile represents 10% of the session's tool calls. The avg count shows")
    lines.append("how many tool calls fall in that decile on average.\n")

    NUM_BINS = result["num_bins"]
    bin_avgs = []
    for i in range(NUM_BINS):
        counts = result["bin_counts"][i]
        avg = sum(counts) / max(len(counts), 1)
        bin_avgs.append(avg)

    max_avg = max(bin_avgs) if bin_avgs else 1

    lines.append("```")
    lines.append("Decile  Avg Count  Distribution")
    lines.append("------  ---------  " + "-" * 50)
    for i in range(NUM_BINS):
        bar_len = int(bin_avgs[i] / max_avg * 45)
        bar = "#" * bar_len
        pct_label = f"{i*10}-{(i+1)*10}%"
        lines.append(f"{pct_label:>7}  {bin_avgs[i]:>8.1f}  |{bar}")
    lines.append("```\n")

    # Since tool calls are divided evenly, the counts should be roughly equal.
    # What's MORE interesting is the tool TYPE distribution per decile.
    lines.append("### Tool Type Distribution by Session Decile\n")
    lines.append("What tools dominate each phase of a session?\n")

    # Get top tools overall
    overall_tools = Counter()
    for i in range(NUM_BINS):
        overall_tools.update(result["bin_tool_types"][i])
    top_tools = [t for t, _ in overall_tools.most_common(8)]

    header = "| Decile | " + " | ".join(top_tools) + " |"
    separator = "|--------|" + "|".join(["-----"] * len(top_tools)) + "|"
    lines.append(header)
    lines.append(separator)

    for i in range(NUM_BINS):
        total_in_bin = sum(result["bin_tool_types"][i].values()) or 1
        row = f"| {i*10}-{(i+1)*10}% |"
        for tool in top_tools:
            pct = result["bin_tool_types"][i][tool] / total_in_bin * 100
            row += f" {pct:.0f}% |"
        lines.append(row)

    # First vs last tools
    lines.append("\n### First 5 vs Last 5 Tool Calls\n")
    lines.append("| Tool | In First 5 | In Last 5 | Shift |")
    lines.append("|------|-----------|----------|-------|")

    all_fl = set(result["first_5_tools"].keys()) | set(result["last_5_tools"].keys())
    total_f = sum(result["first_5_tools"].values()) or 1
    total_l = sum(result["last_5_tools"].values()) or 1

    fl_data = []
    for tool in all_fl:
        pct_f = result["first_5_tools"][tool] / total_f * 100
        pct_l = result["last_5_tools"][tool] / total_l * 100
        fl_data.append((tool, pct_f, pct_l, pct_l - pct_f))

    fl_data.sort(key=lambda x: -abs(x[3]))
    for tool, pct_f, pct_l, delta in fl_data:
        if result["first_5_tools"][tool] + result["last_5_tools"][tool] >= 10:
            sign = "+" if delta > 0 else ""
            lines.append(f"| {tool} | {pct_f:.1f}% | {pct_l:.1f}% | {sign}{delta:.1f}pp |")

    return "\n".join(lines)


# ============================================================
# PATTERN EXTRACTION
# ============================================================

def extract_patterns(transition_result, correction_result, session_metrics, lifetime_result):
    """Extract actionable patterns from all analyses."""
    patterns = []

    # Pattern 1: Dominant tool chains
    for (a, b), prob in sorted(transition_result["transition_probs"].items(), key=lambda x: -x[1]):
        if prob > 0.4 and transition_result["bigrams"][(a, b)] > 50 and a != b:
            patterns.append({
                "type": "strong_chain",
                "from": a,
                "to": b,
                "probability": prob,
                "count": transition_result["bigrams"][(a, b)],
            })

    # Pattern 2: Correction-prone tools
    correction_tools = Counter()
    for seq in correction_result["pre_correction"]:
        for tool in seq:
            correction_tools[tool] += 1
    positive_tools = Counter()
    for seq in correction_result["pre_positive"]:
        for tool in seq:
            positive_tools[tool] += 1

    total_c = sum(correction_tools.values()) or 1
    total_p = sum(positive_tools.values()) or 1

    for tool in set(correction_tools.keys()) | set(positive_tools.keys()):
        bias = correction_tools[tool] / total_c - positive_tools[tool] / total_p
        if bias > 0.05 and correction_tools[tool] >= 20:
            patterns.append({
                "type": "correction_prone",
                "tool": tool,
                "bias": bias,
                "correction_count": correction_tools[tool],
            })

    # Pattern 3: Success-associated tool profiles
    sorted_sessions = sorted(session_metrics, key=lambda x: x["success_score"])
    n = len(sorted_sessions)
    high_success = sorted_sessions[3 * n // 4:]
    low_success = sorted_sessions[:n // 4]

    high_diversity = sum(s["tool_diversity"] for s in high_success) / max(len(high_success), 1)
    low_diversity = sum(s["tool_diversity"] for s in low_success) / max(len(low_success), 1)

    if high_diversity != low_diversity:
        patterns.append({
            "type": "diversity_signal",
            "high_success_diversity": high_diversity,
            "low_success_diversity": low_diversity,
        })

    return patterns


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    print("Loading sessions...", file=sys.stderr)
    sessions = load_all_sessions()
    print(f"Loaded {len(sessions)} sessions with tool calls", file=sys.stderr)

    print("Analysis 1: Transition matrix...", file=sys.stderr)
    transition_result = analyze_transitions(sessions)
    transition_md = format_transition_analysis(transition_result)

    print("Analysis 2: Correction sequences...", file=sys.stderr)
    correction_result = analyze_correction_sequences(sessions)
    correction_md = format_correction_analysis(correction_result)

    print("Analysis 3: Session success...", file=sys.stderr)
    session_metrics = analyze_session_success(sessions)
    success_md = format_success_analysis(session_metrics)

    print("Analysis 4: Session lifetime...", file=sys.stderr)
    lifetime_result = analyze_session_lifetime(sessions)
    lifetime_md = format_lifetime_analysis(lifetime_result)

    print("Extracting patterns...", file=sys.stderr)
    patterns = extract_patterns(transition_result, correction_result, session_metrics, lifetime_result)

    # Build full report
    report = []
    report.append("# Tool Sequence Mining (Third Thoughts Corpus)\n")
    report.append(f"**Date**: 2026-03-20")
    report.append(f"**Method**: Quantitative analysis of JSONL session transcripts (no LLM extraction)")
    report.append(f"**Corpus**: {len(sessions)} sessions with >= 2 tool calls from third-thoughts corpus (2 operators, 16 projects)")
    report.append(f"**Total tool calls analyzed**: {sum(r['num_tools'] for r in sessions):,}\n")
    report.append("---\n")
    report.append(transition_md)
    report.append("\n---\n")
    report.append(correction_md)
    report.append("\n---\n")
    report.append(success_md)
    report.append("\n---\n")
    report.append(lifetime_md)
    report.append("\n---\n")

    # Summary of extracted patterns
    report.append("## Extracted Patterns Summary\n")
    for i, p in enumerate(patterns):
        if p["type"] == "strong_chain":
            report.append(f"{i+1}. **Strong chain**: {p['from']} -> {p['to']} (P={p['probability']:.3f}, n={p['count']})")
        elif p["type"] == "correction_prone":
            report.append(f"{i+1}. **Correction-prone tool**: {p['tool']} (bias={p['bias']:+.3f}, n={p['correction_count']})")
        elif p["type"] == "diversity_signal":
            report.append(f"{i+1}. **Tool diversity signal**: High-success avg={p['high_success_diversity']:.1f}, Low-success avg={p['low_success_diversity']:.1f}")

    full_report = "\n".join(report)

    # Write report
    output_path = os.environ.get(
        "OUTPUT_DIR",
        os.environ.get("MIDDENS_OUTPUT", "experiments/"),
    ) + "/tool-sequence-mining.md"
    with open(output_path, "w") as f:
        f.write(full_report)

    print(f"\nReport written to {output_path}", file=sys.stderr)
    print(f"Patterns found: {len(patterns)}", file=sys.stderr)

    # Also output as JSON for downstream use
    json_output = {
        "sessions_analyzed": len(sessions),
        "total_tool_calls": sum(r["num_tools"] for r in sessions),
        "patterns": patterns,
        "top_transitions": [(list(k), v) for k, v in transition_result["bigrams"].most_common(20)],
        "tool_counts": dict(transition_result["tool_counts"].most_common()),
        "self_transitions": transition_result["self_transitions"],
    }

    json_path = os.environ.get(
        "OUTPUT_DIR",
        os.environ.get("MIDDENS_OUTPUT", "experiments/"),
    ) + "/tool-sequence-mining.json"
    with open(json_path, "w") as f:
        json.dump(json_output, f, indent=2, default=str)

    print(f"JSON data written to {json_path}", file=sys.stderr)
