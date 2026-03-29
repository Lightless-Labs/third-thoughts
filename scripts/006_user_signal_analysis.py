#!/usr/bin/env python3
"""
Experiment 006: User Signal Analysis
Classifies user messages by regex/keyword into directive, question, correction,
approval, nudge, redirect, reference. Analyzes frustration escalation,
message length patterns, and steering vocabulary.
"""

import json
import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Optional

# ─── Configuration ──────────────────────────────────────────────────────
CORPUS_ROOT = Path(os.environ.get("CORPUS_DIR", os.environ.get("MIDDENS_CORPUS", "corpus/")))
OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", os.environ.get("MIDDENS_OUTPUT", "experiments/")))
MAX_PROJECTS = 50
FILES_PER_PROJECT = 5  # top 5 largest per project

# ─── Message type classification (regex/keyword only) ───────────────────

def classify_message(text: str) -> list[str]:
    """Classify a user message into one or more categories using regex/keyword."""
    text_lower = text.lower().strip()
    categories = []

    # Skip empty or very short non-meaningful
    if len(text_lower) < 2:
        return ["minimal"]

    # Correction — check first, these are high-signal
    correction_patterns = [
        r'\bno[,.]?\s',          # "no, " "no. "
        r'^no$',                 # just "no"
        r'\bwrong\b',
        r'\bnot that\b',
        r'\binstead\b',
        r'\bactually[,]?\s',
        r'\bi said\b',
        r'\bi meant\b',
        r'\bthat\'s not\b',
        r'\bthats not\b',
        r'\bnot what i\b',
        r'\bdon\'t do\b',
        r'\bdont do\b',
        r'\bshouldn\'t\b',
        r'\bshouldnt\b',
        r'\bnot right\b',
        r'\bincorrect\b',
        r'\bnope\b',
        r'\bundo\b',
        r'\brevert\b',
        r'\broll back\b',
        r'\brollback\b',
        r'\bwhy did you\b',
        r'\bwhy are you\b',
        r'\bi didn\'t\b',
        r'\bi didnt\b',
        r'\bi never\b',
        r'\bthat was wrong\b',
        r'\bstill wrong\b',
        r'\bstill not\b',
        r'\btry again\b',
    ]
    if any(re.search(p, text_lower) for p in correction_patterns):
        categories.append("correction")

    # Redirect
    redirect_patterns = [
        r'^stop\b',
        r'^wait\b',
        r'\bhold on\b',
        r'^let\'s\b',
        r'^lets\b',
        r'\bdifferent\b',
        r'\bback to\b',
        r'\bforget\b',
        r'\bskip\b',
        r'\bignore\b',
        r'\bnever\s?mind\b',
        r'\bnvm\b',
        r'\bswitch to\b',
        r'\bfocus on\b',
        r'\bscrap\b',
        r'\babort\b',
        r'\bcancel\b',
        r'\bpivot\b',
    ]
    if any(re.search(p, text_lower) for p in redirect_patterns):
        categories.append("redirect")

    # Approval
    approval_patterns = [
        r'\bgood\b',
        r'\bgreat\b',
        r'\bperfect\b',
        r'\bthanks\b',
        r'\bthank you\b',
        r'\bthx\b',
        r'\bty\b',
        r'^yes\b',
        r'^y$',
        r'^yep\b',
        r'^yeah\b',
        r'^yup\b',
        r'\blgtm\b',
        r'\bship it\b',
        r'\bnice\b',
        r'\bawesome\b',
        r'\bexcellent\b',
        r'\blooks good\b',
        r'\bwell done\b',
        r'\bthat\'s right\b',
        r'\bcorrect\b',
        r'\bexactly\b',
        r'\b(?:👍|✅|🎉)\b',
    ]
    if any(re.search(p, text_lower) for p in approval_patterns):
        categories.append("approval")

    # Nudge
    nudge_patterns = [
        r'\bgo ahead\b',
        r'^continue\b',
        r'\bkeep going\b',
        r'\byou figure\b',
        r'\byour call\b',
        r'\bup to you\b',
        r'\bwhatever you\b',
        r'\bproceed\b',
        r'\bcarry on\b',
        r'\bdo it\b',
        r'\bgo for it\b',
        r'\bjust do\b',
        r'^k$',
        r'^ok$',
        r'^okay\b',
        r'^sure\b',
        r'^go$',
    ]
    if any(re.search(p, text_lower) for p in nudge_patterns):
        categories.append("nudge")

    # Question
    question_patterns = [
        r'\?$',
        r'\?[\s\n]*$',
        r'^what\b',
        r'^how\b',
        r'^why\b',
        r'^can you\b',
        r'^could you\b',
        r'^would you\b',
        r'^is there\b',
        r'^are there\b',
        r'^do you\b',
        r'^does\b',
        r'^where\b',
        r'^which\b',
        r'^when\b',
        r'^who\b',
        r'^should\b',
    ]
    if any(re.search(p, text_lower, re.MULTILINE) for p in question_patterns):
        categories.append("question")

    # Directive
    directive_patterns = [
        r'^(do|implement|fix|create|run|build|add|remove|delete|update|change|modify|write|make|set|move|rename|install|deploy|test|check|ensure|verify|use|put|show|list|print|get|fetch|pull|push|merge|commit|read|parse|extract|generate|convert|transform|refactor|clean|format|lint|debug|trace|log|dump|export|import|copy|clone|init|setup|configure|enable|disable|start|stop|restart|kill|open|close|send|call|invoke|trigger|execute|apply|reset|clear|flush|drop|load|save|store|cache|queue|schedule|wire|hook|connect|mount|unmount|attach|detach|wrap|unwrap|map|filter|sort|group|split|join|concat|replace|insert|append|prepend)\b',
        r'^please\s+(do|implement|fix|create|run|build|add|remove|delete|update|change|modify|write|make)\b',
    ]
    if any(re.search(p, text_lower) for p in directive_patterns):
        categories.append("directive")

    # Reference (file paths, URLs, project names)
    reference_patterns = [
        r'[/~][\w/.-]+\.\w+',          # file paths
        r'https?://\S+',                # URLs
        r'`[^`]+`',                     # backtick references
        r'\b\w+\.(ts|js|py|rs|go|md|json|yaml|yml|toml|sh)\b',  # file references
    ]
    if any(re.search(p, text_lower) for p in reference_patterns):
        categories.append("reference")

    if not categories:
        categories.append("uncategorized")

    return categories


# ─── Frustration intensity scoring ──────────────────────────────────────

def frustration_intensity(text: str) -> int:
    """Score frustration 0-5 based on linguistic signals."""
    text_lower = text.lower().strip()
    score = 0

    # Mild correction (1)
    mild = [r'\bnot that\b', r'\binstead\b', r'\bactually\b', r'\bhmm\b']
    if any(re.search(p, text_lower) for p in mild):
        score = max(score, 1)

    # Medium correction (2)
    medium = [r'\bno[,.]?\s', r'^no$', r'\bwrong\b', r'\bnope\b', r'\btry again\b']
    if any(re.search(p, text_lower) for p in medium):
        score = max(score, 2)

    # Firm correction (3)
    firm = [r'\bi said\b', r'\bi meant\b', r'\bnot what i\b', r'\bi told you\b',
            r'\bi already\b', r'\bstill wrong\b', r'\bstill not\b']
    if any(re.search(p, text_lower) for p in firm):
        score = max(score, 3)

    # Exasperated (4)
    exasperated = [r'\bwhy did you\b', r'\bwhy are you\b', r'\bstop\b',
                   r'\bwhy is this\b', r'\bthis is wrong\b', r'\bcompletely wrong\b']
    if any(re.search(p, text_lower) for p in exasperated):
        score = max(score, 4)

    # Giving up / terse (5) — signaled by very short messages after corrections
    # (handled in sequence analysis)

    # Caps amplifier
    if len(text) > 5 and text == text.upper():
        score = min(score + 1, 5)

    # Exclamation amplifier
    if text.count('!') >= 2:
        score = min(score + 1, 5)

    return score


# ─── Data loading ───────────────────────────────────────────────────────

def get_project_dirs() -> list[tuple[str, Path]]:
    """Discover project directories from the full corpus (follows symlinks).

    Groups JSONL files by project name derived from their path.
    Returns (project_name, directory_path) tuples.
    """
    # First collect all JSONL files, then group by containing directory
    project_dirs = {}  # name -> path
    for root, dirnames, filenames in os.walk(str(CORPUS_ROOT), followlinks=True):
        jsonl_files = [f for f in filenames if f.endswith(".jsonl")]
        if not jsonl_files:
            continue
        proj_dir = Path(root)
        # Derive project name from directory
        name = proj_dir.name.lstrip("-")
        parts = name.split("-")
        for i, p in enumerate(parts):
            if p.lower() == "projects" and i + 1 < len(parts):
                name = "-".join(parts[i + 1:]) or name
                break
        if name.startswith("Users-"):
            segments = name.split("-")
            name = "-".join(segments[2:]) if len(segments) > 2 else name

        if name not in project_dirs:
            project_dirs[name] = proj_dir

    dirs = list(project_dirs.items())[:MAX_PROJECTS]
    return dirs


def get_top_files(project_dir: Path, n: int = FILES_PER_PROJECT) -> list[Path]:
    """Get top N largest JSONL files in a project directory (follows symlinks)."""
    jsonl_files = []
    for root, dirnames, filenames in os.walk(str(project_dir), followlinks=True):
        for fn in filenames:
            if fn.endswith(".jsonl"):
                jsonl_files.append(Path(os.path.join(root, fn)))
    jsonl_files.sort(key=lambda f: f.stat().st_size, reverse=True)
    return jsonl_files[:n]


def extract_user_messages(filepath: Path) -> list[dict]:
    """Extract user messages from a JSONL session file."""
    messages = []
    with open(filepath, 'r', errors='replace') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue

            if obj.get("type") != "user":
                continue
            if obj.get("isMeta"):
                continue

            msg = obj.get("message", {})
            content = msg.get("content", "")

            # Skip system-generated content
            if isinstance(content, str):
                # Skip command messages, local-command-stdout, etc
                if "<command-name>" in content:
                    continue
                if "<local-command-" in content:
                    continue
                if "<system-reminder>" in content and len(content) < 200:
                    continue
                # Strip XML tags for analysis but keep the text
                clean = re.sub(r'<[^>]+>', '', content).strip()
                if len(clean) < 1:
                    continue
                messages.append({
                    "text": clean,
                    "raw": content,
                    "timestamp": obj.get("timestamp", ""),
                    "session_id": obj.get("sessionId", ""),
                    "uuid": obj.get("uuid", ""),
                })
            elif isinstance(content, list):
                # Multi-part messages
                text_parts = []
                for part in content:
                    if isinstance(part, dict) and part.get("type") == "text":
                        text_parts.append(part.get("text", ""))
                combined = "\n".join(text_parts).strip()
                if combined and "<command-name>" not in combined and "<local-command-" not in combined:
                    clean = re.sub(r'<[^>]+>', '', combined).strip()
                    if len(clean) >= 1:
                        messages.append({
                            "text": clean,
                            "raw": combined,
                            "timestamp": obj.get("timestamp", ""),
                            "session_id": obj.get("sessionId", ""),
                            "uuid": obj.get("uuid", ""),
                        })
    return messages


# Also extract assistant tool use to understand what preceded frustration
def extract_messages_with_context(filepath: Path) -> list[dict]:
    """Extract all messages with type info for context analysis."""
    messages = []
    with open(filepath, 'r', errors='replace') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue

            msg_type = obj.get("type")
            if msg_type not in ("user", "assistant"):
                continue
            if obj.get("isMeta"):
                continue

            msg = obj.get("message", {})
            content = msg.get("content", "")

            # For assistant messages, extract tool names
            tool_names = []
            if msg_type == "assistant" and isinstance(content, list):
                for part in content:
                    if isinstance(part, dict) and part.get("type") == "tool_use":
                        tool_names.append(part.get("name", "unknown"))

            text = ""
            if isinstance(content, str):
                if "<command-name>" in content or "<local-command-" in content:
                    continue
                text = re.sub(r'<[^>]+>', '', content).strip()
            elif isinstance(content, list):
                text_parts = []
                for part in content:
                    if isinstance(part, dict) and part.get("type") == "text":
                        text_parts.append(part.get("text", ""))
                text = "\n".join(text_parts).strip()
                if "<command-name>" in text or "<local-command-" in text:
                    continue
                text = re.sub(r'<[^>]+>', '', text).strip()

            if not text and not tool_names:
                continue

            messages.append({
                "type": msg_type,
                "text": text,
                "tools": tool_names,
                "timestamp": obj.get("timestamp", ""),
                "session_id": obj.get("sessionId", ""),
            })

    return messages


# ─── Analysis ───────────────────────────────────────────────────────────

def run_analysis():
    projects = get_project_dirs()
    print(f"Found {len(projects)} projects (capped at {MAX_PROJECTS})")

    # Storage
    all_project_data = {}  # project_name -> list of classified messages
    all_messages_flat = []  # for global analysis
    session_messages = defaultdict(list)  # session_id -> ordered messages
    session_contexts = defaultdict(list)  # session_id -> messages with context
    project_sessions = defaultdict(set)  # project -> set of session_ids

    total_files = 0
    total_messages = 0

    for proj_name, proj_dir in projects:
        files = get_top_files(proj_dir)
        if not files:
            continue
        print(f"  {proj_name}: {len(files)} files")

        proj_messages = []
        for f in files:
            total_files += 1
            msgs = extract_user_messages(f)
            ctx_msgs = extract_messages_with_context(f)

            for m in msgs:
                m["project"] = proj_name
                m["categories"] = classify_message(m["text"])
                m["frustration"] = frustration_intensity(m["text"])
                m["length"] = len(m["text"])
                proj_messages.append(m)
                all_messages_flat.append(m)
                session_messages[m["session_id"]].append(m)
                project_sessions[proj_name].add(m["session_id"])
                total_messages += 1

            for m in ctx_msgs:
                m["project"] = proj_name
                session_contexts[m["session_id"]].append(m)

        all_project_data[proj_name] = proj_messages

    print(f"\nTotal: {total_files} files, {total_messages} user messages\n")

    # ════════════════════════════════════════════════════════════════════
    # Analysis 1: Message classification distribution
    # ════════════════════════════════════════════════════════════════════
    print("=" * 70)
    print("ANALYSIS 1: USER MESSAGE CLASSIFICATION")
    print("=" * 70)

    # Global distribution
    global_counts = Counter()
    for m in all_messages_flat:
        for cat in m["categories"]:
            global_counts[cat] += 1

    print("\n--- Global Distribution ---")
    total_cat = sum(global_counts.values())
    for cat, count in global_counts.most_common():
        pct = count / total_messages * 100
        print(f"  {cat:20s}: {count:6d} ({pct:5.1f}%)")

    # Per-project distribution
    print("\n--- Per-Project Distribution ---")
    project_dists = {}
    for proj_name, msgs in sorted(all_project_data.items()):
        if not msgs:
            continue
        counts = Counter()
        for m in msgs:
            for cat in m["categories"]:
                counts[cat] += 1
        project_dists[proj_name] = counts
        n = len(msgs)
        corr = counts.get("correction", 0)
        appr = counts.get("approval", 0)
        ratio = corr / max(appr, 1)
        print(f"  {proj_name:35s}: {n:5d} msgs | "
              f"corr={corr:3d} appr={appr:3d} ratio={ratio:.2f} | "
              f"dir={counts.get('directive',0):3d} "
              f"q={counts.get('question',0):3d} "
              f"nudge={counts.get('nudge',0):3d} "
              f"redir={counts.get('redirect',0):3d}")

    # Correction-to-approval ratio ranking
    print("\n--- Correction-to-Approval Ratio (highest first) ---")
    ratios = []
    for proj_name, counts in project_dists.items():
        corr = counts.get("correction", 0)
        appr = counts.get("approval", 0)
        total = sum(1 for m in all_project_data[proj_name])
        if total >= 10:  # minimum threshold
            ratio = corr / max(appr, 1)
            ratios.append((proj_name, ratio, corr, appr, total))
    ratios.sort(key=lambda x: x[1], reverse=True)
    for proj, ratio, corr, appr, total in ratios:
        bar = "#" * min(int(ratio * 10), 50)
        print(f"  {proj:35s}: {ratio:5.2f} (corr={corr}, appr={appr}, n={total}) {bar}")

    # ════════════════════════════════════════════════════════════════════
    # Analysis 2: Message length patterns
    # ════════════════════════════════════════════════════════════════════
    print("\n" + "=" * 70)
    print("ANALYSIS 2: MESSAGE LENGTH PATTERNS")
    print("=" * 70)

    # Length by category
    print("\n--- Average Message Length by Category ---")
    cat_lengths = defaultdict(list)
    for m in all_messages_flat:
        for cat in m["categories"]:
            cat_lengths[cat].append(m["length"])

    cat_avg = {}
    for cat in global_counts:
        lengths = cat_lengths[cat]
        avg = sum(lengths) / len(lengths)
        med = sorted(lengths)[len(lengths) // 2]
        cat_avg[cat] = avg
        print(f"  {cat:20s}: avg={avg:7.1f} chars, median={med:6d}, n={len(lengths)}")

    # Message length over session lifetime
    print("\n--- Message Length Over Session Lifetime ---")
    session_length_progression = defaultdict(list)  # quintile -> lengths
    for sid, msgs in session_messages.items():
        if len(msgs) < 5:
            continue
        n = len(msgs)
        for i, m in enumerate(msgs):
            quintile = int(i / n * 5)  # 0-4
            session_length_progression[quintile].append(m["length"])

    if session_length_progression:
        labels = ["0-20%", "20-40%", "40-60%", "60-80%", "80-100%"]
        for q in range(5):
            lengths = session_length_progression[q]
            if lengths:
                avg = sum(lengths) / len(lengths)
                med = sorted(lengths)[len(lengths) // 2]
                print(f"  Session {labels[q]:8s}: avg={avg:7.1f}, median={med:5d}, n={len(lengths)}")

    # Short message clustering
    print("\n--- Short Messages (< 20 chars) by Session Position ---")
    short_by_position = defaultdict(int)
    total_by_position = defaultdict(int)
    for sid, msgs in session_messages.items():
        if len(msgs) < 5:
            continue
        n = len(msgs)
        for i, m in enumerate(msgs):
            quintile = int(i / n * 5)
            total_by_position[quintile] += 1
            if m["length"] < 20:
                short_by_position[quintile] += 1

    for q in range(5):
        total = total_by_position[q]
        short = short_by_position[q]
        pct = short / max(total, 1) * 100
        print(f"  Session {labels[q]:8s}: {short:5d}/{total:5d} ({pct:5.1f}%)")

    # Short message category breakdown
    print("\n--- Short Messages (< 20 chars) Category Breakdown ---")
    short_cats = Counter()
    for m in all_messages_flat:
        if m["length"] < 20:
            for cat in m["categories"]:
                short_cats[cat] += 1
    total_short = sum(1 for m in all_messages_flat if m["length"] < 20)
    for cat, count in short_cats.most_common():
        pct = count / max(total_short, 1) * 100
        print(f"  {cat:20s}: {count:5d} ({pct:5.1f}%)")

    # ════════════════════════════════════════════════════════════════════
    # Analysis 3: Frustration escalation
    # ════════════════════════════════════════════════════════════════════
    print("\n" + "=" * 70)
    print("ANALYSIS 3: FRUSTRATION ESCALATION SEQUENCES")
    print("=" * 70)

    # Find escalation sequences: 2+ consecutive corrections with rising intensity
    escalation_sequences = []
    for sid, msgs in session_messages.items():
        corrections_in_a_row = []
        for i, m in enumerate(msgs):
            if "correction" in m["categories"] or "redirect" in m["categories"]:
                corrections_in_a_row.append((i, m))
            else:
                if len(corrections_in_a_row) >= 2:
                    intensities = [msg["frustration"] for _, msg in corrections_in_a_row]
                    if max(intensities) >= 2:  # at least one medium+ frustration
                        escalation_sequences.append({
                            "session_id": sid,
                            "project": corrections_in_a_row[0][1]["project"],
                            "messages": [(idx, msg["text"][:120], msg["frustration"])
                                         for idx, msg in corrections_in_a_row],
                            "max_intensity": max(intensities),
                            "length": len(corrections_in_a_row),
                        })
                corrections_in_a_row = []

        # Check tail
        if len(corrections_in_a_row) >= 2:
            intensities = [msg["frustration"] for _, msg in corrections_in_a_row]
            if max(intensities) >= 2:
                escalation_sequences.append({
                    "session_id": sid,
                    "project": corrections_in_a_row[0][1]["project"],
                    "messages": [(idx, msg["text"][:120], msg["frustration"])
                                 for idx, msg in corrections_in_a_row],
                    "max_intensity": max(intensities),
                    "length": len(corrections_in_a_row),
                })

    escalation_sequences.sort(key=lambda x: x["max_intensity"], reverse=True)
    print(f"\nFound {len(escalation_sequences)} escalation sequences")

    # Show top 15
    print("\n--- Top 15 Escalation Sequences ---")
    for seq in escalation_sequences[:15]:
        print(f"\n  Project: {seq['project']}, Session: {seq['session_id'][:12]}...")
        print(f"  Max intensity: {seq['max_intensity']}, Length: {seq['length']} corrections")
        for idx, text, intensity in seq["messages"]:
            marker = "!" * intensity
            print(f"    [{intensity}]{marker} msg#{idx}: {text}")

    # What preceded escalation? Look at assistant tool use before the sequence
    print("\n--- Tools/Topics Preceding Escalation ---")
    tool_before_escalation = Counter()
    for seq in escalation_sequences:
        sid = seq["session_id"]
        ctx = session_contexts.get(sid, [])
        if not ctx:
            continue
        first_msg_idx = seq["messages"][0][0]
        # Look at the last few assistant messages before the escalation
        assistant_msgs_before = []
        user_count = 0
        for cm in ctx:
            if cm["type"] == "user":
                user_count += 1
                if user_count >= first_msg_idx:
                    break
            elif cm["type"] == "assistant" and cm.get("tools"):
                assistant_msgs_before = cm["tools"]  # keep overwriting to get most recent

        for tool in assistant_msgs_before:
            tool_before_escalation[tool] += 1

    print(f"  Tools seen before escalation sequences:")
    for tool, count in tool_before_escalation.most_common(15):
        print(f"    {tool:40s}: {count}")

    # Frustration distribution
    print("\n--- Frustration Score Distribution ---")
    frust_dist = Counter()
    for m in all_messages_flat:
        frust_dist[m["frustration"]] += 1
    for score in range(6):
        count = frust_dist.get(score, 0)
        pct = count / max(total_messages, 1) * 100
        bar = "#" * min(int(pct * 2), 60)
        print(f"  Level {score}: {count:6d} ({pct:5.1f}%) {bar}")

    # ════════════════════════════════════════════════════════════════════
    # Analysis 4: Steering vocabulary
    # ════════════════════════════════════════════════════════════════════
    print("\n" + "=" * 70)
    print("ANALYSIS 4: STEERING VOCABULARY")
    print("=" * 70)

    # Extract correction/steering phrases
    steering_phrases = Counter()
    project_steering = defaultdict(Counter)

    steering_extractors = [
        (r'\b(no[,.]?\s+\w+[\w\s]{0,30})', "negation"),
        (r'\b(not\s+\w+[\w\s]{0,20})', "not-phrase"),
        (r'\b(instead[,]?\s+\w+[\w\s]{0,30})', "instead"),
        (r'\b(actually[,]?\s+\w+[\w\s]{0,30})', "actually"),
        (r'\b(i said\s+[\w\s]{0,30})', "i-said"),
        (r'\b(i meant?\s+[\w\s]{0,30})', "i-meant"),
        (r'\b(why did you\s+[\w\s]{0,30})', "why-did-you"),
        (r'\b(why are you\s+[\w\s]{0,30})', "why-are-you"),
        (r'\b(don\'?t\s+\w+[\w\s]{0,20})', "dont"),
        (r'\b(stop\s+\w+[\w\s]{0,20})', "stop"),
        (r'\b(wrong\s+[\w\s]{0,20})', "wrong"),
        (r'\b(still\s+(?:not|wrong|broken|failing)[\w\s]{0,20})', "still-problem"),
        (r'\b(try\s+again[\w\s]{0,20})', "try-again"),
        (r'\b(revert[\w\s]{0,20})', "revert"),
        (r'\b(undo[\w\s]{0,20})', "undo"),
        (r'\b(go back[\w\s]{0,20})', "go-back"),
        (r'\b(forget[\w\s]{0,20})', "forget"),
        (r'\b(skip[\w\s]{0,20})', "skip"),
        (r'\b(ignore[\w\s]{0,20})', "ignore"),
    ]

    for m in all_messages_flat:
        if "correction" not in m["categories"] and "redirect" not in m["categories"]:
            continue
        text_lower = m["text"].lower()
        for pattern, cluster in steering_extractors:
            matches = re.findall(pattern, text_lower)
            for match in matches:
                phrase = match.strip()[:50]
                if len(phrase) >= 3:
                    steering_phrases[phrase] += 1
                    project_steering[m["project"]][phrase] += 1

    print("\n--- Top 40 Steering Phrases ---")
    for phrase, count in steering_phrases.most_common(40):
        # Which projects use this phrase?
        proj_list = []
        for proj, pcounts in project_steering.items():
            if pcounts[phrase] > 0:
                proj_list.append(proj)
        scope = "UNIVERSAL" if len(proj_list) >= 3 else f"specific({','.join(proj_list[:3])})"
        print(f"  {count:4d}x \"{phrase}\"  [{scope}]")

    # Cluster steering phrases by type
    print("\n--- Steering Phrase Clusters ---")
    clusters = defaultdict(list)
    for phrase, count in steering_phrases.most_common(100):
        for _, cluster_name in steering_extractors:
            pattern = [p for p, c in steering_extractors if c == cluster_name][0]
            if re.search(pattern, phrase):
                clusters[cluster_name].append((phrase, count))
                break

    for cluster_name, phrases in sorted(clusters.items(), key=lambda x: -sum(c for _, c in x[1])):
        total = sum(c for _, c in phrases)
        print(f"\n  [{cluster_name}] total={total}")
        for phrase, count in phrases[:5]:
            print(f"    {count:4d}x \"{phrase}\"")

    # Project-specific vs universal phrases
    print("\n--- Project-Specific Steering Vocabulary ---")
    for proj in sorted(project_steering.keys()):
        unique_phrases = []
        for phrase, count in project_steering[proj].most_common(20):
            # Check if this phrase appears only in this project
            other_count = sum(project_steering[p][phrase] for p in project_steering if p != proj)
            if other_count == 0 and count >= 2:
                unique_phrases.append((phrase, count))
        if unique_phrases:
            print(f"\n  {proj}:")
            for phrase, count in unique_phrases[:5]:
                print(f"    {count:4d}x \"{phrase}\"")

    # ════════════════════════════════════════════════════════════════════
    # Summary statistics for report
    # ════════════════════════════════════════════════════════════════════
    print("\n" + "=" * 70)
    print("SUMMARY STATISTICS")
    print("=" * 70)

    print(f"\nProjects analyzed: {len(all_project_data)}")
    print(f"Files processed: {total_files}")
    print(f"User messages: {total_messages}")
    print(f"Unique sessions: {len(session_messages)}")
    print(f"Escalation sequences found: {len(escalation_sequences)}")

    correction_rate = sum(1 for m in all_messages_flat if "correction" in m["categories"]) / max(total_messages, 1) * 100
    approval_rate = sum(1 for m in all_messages_flat if "approval" in m["categories"]) / max(total_messages, 1) * 100
    redirect_rate = sum(1 for m in all_messages_flat if "redirect" in m["categories"]) / max(total_messages, 1) * 100

    print(f"\nGlobal correction rate: {correction_rate:.1f}%")
    print(f"Global approval rate: {approval_rate:.1f}%")
    print(f"Global redirect rate: {redirect_rate:.1f}%")

    avg_len = sum(m["length"] for m in all_messages_flat) / max(total_messages, 1)
    print(f"Average message length: {avg_len:.0f} chars")

    # Return data for report generation
    return {
        "projects": all_project_data,
        "global_counts": global_counts,
        "total_messages": total_messages,
        "total_files": total_files,
        "project_dists": project_dists,
        "ratios": ratios,
        "cat_avg": cat_avg,
        "session_length_progression": dict(session_length_progression),
        "short_by_position": dict(short_by_position),
        "total_by_position": dict(total_by_position),
        "short_cats": short_cats,
        "escalation_sequences": escalation_sequences,
        "tool_before_escalation": tool_before_escalation,
        "frust_dist": frust_dist,
        "steering_phrases": steering_phrases,
        "clusters": dict(clusters),
        "project_steering": dict(project_steering),
        "correction_rate": correction_rate,
        "approval_rate": approval_rate,
        "redirect_rate": redirect_rate,
        "avg_len": avg_len,
        "all_messages_flat": all_messages_flat,
        "labels": ["0-20%", "20-40%", "40-60%", "60-80%", "80-100%"],
    }


if __name__ == "__main__":
    data = run_analysis()
    # Pickle for report generation
    import pickle
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    out = OUTPUT_DIR / "006_analysis_data.pkl"
    with open(out, "wb") as f:
        pickle.dump(data, f)
    print(f"\nData saved to {out}")
