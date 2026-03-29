#!/usr/bin/env python3
"""
Experiment 006: User Signal Analysis (v2 - cleaned)
Filters out pasted logs/errors, continuation summaries, and tool result IDs
to focus on genuine human-authored steering signals.
"""

import json
import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

# ─── Configuration ──────────────────────────────────────────────────────
CORPUS_DIR = Path(os.environ.get("MIDDENS_CORPUS", "corpus/"))
MAX_PROJECTS = 50
FILES_PER_PROJECT = 20  # Increased since corpus is smaller per-project

# ─── Filters to detect non-human content ────────────────────────────────

def is_pasted_content(text: str) -> bool:
    """Detect log dumps, error pastes, continuation summaries, tool result IDs."""
    # Continuation summaries
    if text.startswith("This session is being continued from a previous"):
        return True
    # Tool result IDs (hex strings at start)
    if re.match(r'^[a-f0-9]{16,}', text.strip()):
        return True
    # Heavy log content (multiple lines with timestamps or log-like patterns)
    lines = text.strip().split('\n')
    if len(lines) > 3:
        log_line_count = sum(1 for l in lines if re.search(
            r'(^\d{4}-\d{2}-\d{2}|^\s*(com\.|WARN|ERROR|INFO|DEBUG|default\s+\d{2}:)|'
            r'InstallStatus|toolu_|completed\s*$|Agent\s+"[^"]+"\s+completed)', l))
        if log_line_count > len(lines) * 0.3:
            return True
    # Single line that looks like a hex ID
    if len(lines) == 1 and re.match(r'^[a-f0-9]{16,}\s*$', text.strip()):
        return True
    return False


def extract_human_text(text: str) -> str:
    """Extract the human-written portion from a message that might have pasted content."""
    # If it starts with "> " quote block followed by human text, get the human part
    lines = text.strip().split('\n')

    # Find the first non-quote, non-empty, non-log line
    human_lines = []
    in_code_block = False
    for line in lines:
        if line.strip().startswith('```'):
            in_code_block = not in_code_block
            continue
        if in_code_block:
            continue
        if line.strip().startswith('>'):
            continue
        # Skip hex IDs
        if re.match(r'^[a-f0-9]{16,}', line.strip()):
            continue
        # Skip tool result lines
        if re.match(r'^toolu_', line.strip()):
            continue
        # Skip agent completion lines
        if re.search(r'Agent "[^"]+" completed', line):
            continue
        # Skip obvious log lines
        if re.search(r'^\s*(com\.|WARN |ERROR |INFO |DEBUG |default\s+\d{2}:)', line):
            continue
        human_lines.append(line)

    return '\n'.join(human_lines).strip()


# ─── Message type classification ───────────────────────────────────────

def classify_message(text: str) -> list[str]:
    """Classify a user message into categories using regex/keyword."""
    text_lower = text.lower().strip()
    categories = []

    if len(text_lower) < 2:
        return ["minimal"]

    # Correction
    correction_patterns = [
        r'\bno[,.]?\s',
        r'^no$',
        r'\bwrong\b',
        r'\bnot that\b',
        r'\binstead\b',
        r'\bactually[,]?\s',
        r'\bi said\b',
        r'\bi meant\b',
        r'\bthat\'s not\b',
        r'\bnot what i\b',
        r'\bdon\'t do\b',
        r'\bdont do\b',
        r'\bshouldn\'t\b',
        r'\bnot right\b',
        r'\bincorrect\b',
        r'\bnope\b',
        r'\bundo\b',
        r'\brevert\b',
        r'\bwhy did you\b',
        r'\bwhy are you\b',
        r'\bi didn\'t\b',
        r'\bi never\b',
        r'\bstill wrong\b',
        r'\bstill not\b',
        r'\btry again\b',
        r'\bthat was wrong\b',
        r'\bi don\'t want\b',
        r'\bi dont want\b',
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
        r'\?[\s]*$',
        r'^what\b',
        r'^how\b',
        r'^why\b',
        r'^can you\b',
        r'^could you\b',
        r'^would you\b',
        r'^is there\b',
        r'^are there\b',
        r'^do you\b',
        r'^where\b',
        r'^which\b',
        r'^should\b',
    ]
    if any(re.search(p, text_lower, re.MULTILINE) for p in question_patterns):
        categories.append("question")

    # Directive
    directive_patterns = [
        r'^(implement|fix|create|run|build|add|remove|delete|update|change|modify|write|make|set|move|rename|install|deploy|test|check|ensure|verify|use|put|show|list|print|get|fetch|pull|push|merge|commit|read|parse|extract|generate|convert|refactor|clean|format|lint|debug|export|import|copy|clone|init|setup|configure|enable|disable|start|restart|open|send|execute|apply|reset|clear)\b',
        r'^please\s+(do|implement|fix|create|run|build|add|remove|delete|update|change|modify|write|make)\b',
    ]
    if any(re.search(p, text_lower) for p in directive_patterns):
        categories.append("directive")

    # Reference
    reference_patterns = [
        r'[/~][\w/.-]+\.\w+',
        r'https?://\S+',
        r'`[^`]+`',
        r'\b\w+\.(ts|js|py|rs|go|md|json|yaml|yml|toml|sh)\b',
    ]
    if any(re.search(p, text_lower) for p in reference_patterns):
        categories.append("reference")

    if not categories:
        categories.append("uncategorized")

    return categories


def frustration_intensity(text: str) -> int:
    """Score frustration 0-5."""
    text_lower = text.lower().strip()
    score = 0

    mild = [r'\bnot that\b', r'\binstead\b', r'\bactually\b', r'\bhmm\b']
    if any(re.search(p, text_lower) for p in mild):
        score = max(score, 1)

    medium = [r'\bno[,.]?\s', r'^no$', r'\bwrong\b', r'\bnope\b', r'\btry again\b']
    if any(re.search(p, text_lower) for p in medium):
        score = max(score, 2)

    firm = [r'\bi said\b', r'\bi meant\b', r'\bnot what i\b', r'\bi told you\b',
            r'\bi already\b', r'\bstill wrong\b', r'\bstill not\b']
    if any(re.search(p, text_lower) for p in firm):
        score = max(score, 3)

    exasperated = [r'\bwhy did you\b', r'\bwhy are you\b', r'\bstop\b',
                   r'\bwhy is this\b', r'\bthis is wrong\b', r'\bcompletely wrong\b',
                   r'\bdon\'t (give|care)\b', r'\bgive a fuck\b', r'\bffs\b',
                   r'\bi don\'t (give|care)\b', r'\bi dont (give|care)\b']
    if any(re.search(p, text_lower) for p in exasperated):
        score = max(score, 4)

    # All caps amplifier
    if len(text) > 5 and text == text.upper():
        score = min(score + 1, 5)
    # Multiple exclamation marks
    if text.count('!') >= 2:
        score = min(score + 1, 5)

    return score


# ─── Data loading ───────────────────────────────────────────────────────

def get_project_files():
    """Find all JSONL files in the corpus, grouped by project."""
    import glob as globmod
    all_files = globmod.glob(str(CORPUS_DIR / "**" / "*.jsonl"), recursive=True)

    project_files = defaultdict(list)
    for fpath in all_files:
        parts = fpath.split("/")
        project = "unknown"
        for i, p in enumerate(parts):
            if p == "projects" and i + 1 < len(parts):
                project = parts[i + 1]
                break
        project_files[project].append(Path(fpath))

    # Sort files within each project by size (largest first)
    for proj in project_files:
        project_files[proj].sort(key=lambda f: f.stat().st_size, reverse=True)
        project_files[proj] = project_files[proj][:FILES_PER_PROJECT]

    # Return as list of (name, files) tuples
    result = sorted(project_files.items())[:MAX_PROJECTS]
    return result


def extract_all_messages(filepath):
    """Extract all messages (user + assistant) with context."""
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

            tool_names = []
            text = ""

            if isinstance(content, str):
                if "<command-name>" in content or "<local-command-" in content:
                    continue
                text = re.sub(r'<[^>]+>', '', content).strip()
            elif isinstance(content, list):
                text_parts = []
                for part in content:
                    if isinstance(part, dict):
                        if part.get("type") == "text":
                            text_parts.append(part.get("text", ""))
                        elif part.get("type") == "tool_use":
                            tool_names.append(part.get("name", "unknown"))
                        elif part.get("type") == "tool_result":
                            pass  # skip tool results
                combined = "\n".join(text_parts).strip()
                if "<command-name>" in combined or "<local-command-" in combined:
                    continue
                text = re.sub(r'<[^>]+>', '', combined).strip()

            if msg_type == "user" and text:
                # Check if this is pasted content
                if is_pasted_content(text):
                    # Try to extract human portion
                    human = extract_human_text(text)
                    if len(human) < 3:
                        continue
                    text = human

            if not text and not tool_names:
                continue

            messages.append({
                "type": msg_type,
                "text": text,
                "tools": tool_names,
                "timestamp": obj.get("timestamp", ""),
                "session_id": obj.get("sessionId", ""),
                "uuid": obj.get("uuid", ""),
            })

    return messages


# ─── Main analysis ──────────────────────────────────────────────────────

def run_analysis():
    project_file_groups = get_project_files()
    print(f"Found {len(project_file_groups)} projects (capped at {MAX_PROJECTS})")

    # Storage
    all_project_data = {}
    all_user_messages = []
    session_user_msgs = defaultdict(list)
    session_all_msgs = defaultdict(list)

    total_files = 0
    total_user_msgs = 0

    for proj_name, files in project_file_groups:
        if not files:
            continue
        print(f"  {proj_name}: {len(files)} files", end="")

        proj_messages = []
        for f in files:
            total_files += 1
            all_msgs = extract_all_messages(f)

            for m in all_msgs:
                m["project"] = proj_name
                session_all_msgs[m["session_id"]].append(m)

                if m["type"] == "user":
                    m["categories"] = classify_message(m["text"])
                    m["frustration"] = frustration_intensity(m["text"])
                    m["length"] = len(m["text"])
                    proj_messages.append(m)
                    all_user_messages.append(m)
                    session_user_msgs[m["session_id"]].append(m)
                    total_user_msgs += 1

        all_project_data[proj_name] = proj_messages
        print(f" -> {len(proj_messages)} human msgs")

    print(f"\nTotal: {total_files} files, {total_user_msgs} user messages, {len(session_user_msgs)} sessions\n")

    results = {}  # store for report

    # ════════════════════════════════════════════════════════════════
    # ANALYSIS 1: Message Classification Distribution
    # ════════════════════════════════════════════════════════════════
    print("=" * 70)
    print("ANALYSIS 1: USER MESSAGE CLASSIFICATION")
    print("=" * 70)

    global_counts = Counter()
    for m in all_user_messages:
        for cat in m["categories"]:
            global_counts[cat] += 1

    print("\n--- Global Distribution ---")
    for cat, count in global_counts.most_common():
        pct = count / total_user_msgs * 100
        bar = "#" * min(int(pct), 60)
        print(f"  {cat:20s}: {count:5d} ({pct:5.1f}%) {bar}")

    # Per-project with correction:approval ratio
    print("\n--- Correction-to-Approval Ratio (min 10 msgs) ---")
    ratios = []
    for proj_name, msgs in all_project_data.items():
        if len(msgs) < 10:
            continue
        counts = Counter()
        for m in msgs:
            for cat in m["categories"]:
                counts[cat] += 1
        corr = counts.get("correction", 0)
        appr = counts.get("approval", 0)
        ratio = corr / max(appr, 1)
        ratios.append((proj_name, ratio, corr, appr, len(msgs), counts))

    ratios.sort(key=lambda x: x[1], reverse=True)
    for proj, ratio, corr, appr, total, counts in ratios:
        dir_c = counts.get("directive", 0)
        q_c = counts.get("question", 0)
        nudge_c = counts.get("nudge", 0)
        redir_c = counts.get("redirect", 0)
        print(f"  {proj:35s}: ratio={ratio:5.2f} (C={corr:3d} A={appr:3d}) "
              f"| D={dir_c:2d} Q={q_c:3d} N={nudge_c:2d} R={redir_c:2d} | n={total}")

    results["global_counts"] = global_counts
    results["ratios"] = ratios

    # ════════════════════════════════════════════════════════════════
    # ANALYSIS 2: Message Length Patterns
    # ════════════════════════════════════════════════════════════════
    print("\n" + "=" * 70)
    print("ANALYSIS 2: MESSAGE LENGTH PATTERNS")
    print("=" * 70)

    # Length by category
    print("\n--- Average Message Length by Category ---")
    cat_lengths = defaultdict(list)
    for m in all_user_messages:
        for cat in m["categories"]:
            cat_lengths[cat].append(m["length"])

    length_by_cat = {}
    for cat in global_counts:
        lengths = cat_lengths[cat]
        avg = sum(lengths) / len(lengths)
        med = sorted(lengths)[len(lengths) // 2]
        length_by_cat[cat] = {"avg": avg, "median": med, "n": len(lengths)}
        print(f"  {cat:20s}: avg={avg:7.1f}  median={med:6d}  n={len(lengths)}")

    # Message length over session lifetime (quintiles)
    print("\n--- Message Length Over Session Lifetime ---")
    quintile_lengths = defaultdict(list)
    labels = ["0-20%", "20-40%", "40-60%", "60-80%", "80-100%"]
    for sid, msgs in session_user_msgs.items():
        if len(msgs) < 5:
            continue
        n = len(msgs)
        for i, m in enumerate(msgs):
            q = min(int(i / n * 5), 4)
            quintile_lengths[q].append(m["length"])

    session_progression = {}
    for q in range(5):
        lengths = quintile_lengths[q]
        if lengths:
            avg = sum(lengths) / len(lengths)
            med = sorted(lengths)[len(lengths) // 2]
            session_progression[labels[q]] = {"avg": avg, "median": med, "n": len(lengths)}
            print(f"  {labels[q]:8s}: avg={avg:7.1f}  median={med:5d}  n={len(lengths)}")

    # Short message analysis
    print("\n--- Short Messages (< 30 chars) Position + Category ---")
    short_pos_cat = defaultdict(Counter)
    for sid, msgs in session_user_msgs.items():
        if len(msgs) < 5:
            continue
        n = len(msgs)
        for i, m in enumerate(msgs):
            if m["length"] < 30:
                q = min(int(i / n * 5), 4)
                for cat in m["categories"]:
                    short_pos_cat[q][cat] += 1

    for q in range(5):
        cats = short_pos_cat[q]
        total = sum(cats.values())
        if total:
            top = ", ".join(f"{c}={n}" for c, n in cats.most_common(4))
            print(f"  {labels[q]:8s}: {total:4d} short msgs -> {top}")

    # Examples of short messages
    print("\n--- Sample Short Messages (<30 chars) ---")
    short_samples = defaultdict(list)
    for m in all_user_messages:
        if m["length"] < 30 and m["length"] > 1:
            for cat in m["categories"]:
                if len(short_samples[cat]) < 8:
                    short_samples[cat].append(m["text"].strip()[:40])
    for cat in ["correction", "nudge", "approval", "redirect", "question"]:
        if short_samples.get(cat):
            print(f"  [{cat}]:")
            for s in short_samples[cat]:
                print(f"    \"{s}\"")

    results["length_by_cat"] = length_by_cat
    results["session_progression"] = session_progression

    # ════════════════════════════════════════════════════════════════
    # ANALYSIS 3: Frustration Escalation
    # ════════════════════════════════════════════════════════════════
    print("\n" + "=" * 70)
    print("ANALYSIS 3: FRUSTRATION ESCALATION SEQUENCES")
    print("=" * 70)

    # Find escalation: consecutive user messages with corrections where
    # intensity rises or stays high
    escalations = []
    for sid, msgs in session_user_msgs.items():
        window = []
        for i, m in enumerate(msgs):
            if m["frustration"] >= 1:
                window.append(m)
            else:
                if len(window) >= 2 and max(w["frustration"] for w in window) >= 2:
                    # Check if intensity rises at some point
                    intensities = [w["frustration"] for w in window]
                    peak = max(intensities)
                    escalations.append({
                        "session_id": sid,
                        "project": window[0]["project"],
                        "messages": [(w["text"][:150], w["frustration"]) for w in window],
                        "peak": peak,
                        "length": len(window),
                    })
                window = []
        # Check tail
        if len(window) >= 2 and max(w["frustration"] for w in window) >= 2:
            intensities = [w["frustration"] for w in window]
            peak = max(intensities)
            escalations.append({
                "session_id": sid,
                "project": window[0]["project"],
                "messages": [(w["text"][:150], w["frustration"]) for w in window],
                "peak": peak,
                "length": len(window),
            })

    escalations.sort(key=lambda x: x["peak"], reverse=True)
    print(f"\nFound {len(escalations)} escalation sequences")

    # Show top 20
    print("\n--- Top 20 Escalation Sequences (genuine human messages) ---")
    shown = 0
    for seq in escalations:
        # Skip sequences where all messages look like pasted data
        human_msgs = [t for t, f in seq["messages"] if len(t) < 300 and not re.match(r'^[a-f0-9]{16}', t)]
        if not human_msgs:
            continue
        shown += 1
        if shown > 20:
            break
        print(f"\n  [{seq['project']}] session={seq['session_id'][:12]}... peak={seq['peak']}")
        for text, intensity in seq["messages"]:
            if len(text) > 200:
                text = text[:200] + "..."
            marker = "!" * intensity
            print(f"    [{intensity}]{marker} \"{text}\"")

    # What tools preceded frustration?
    print("\n--- Tools Preceding Frustration (intensity >= 3) ---")
    tool_before_frustration = Counter()
    topic_before_frustration = Counter()
    for sid, all_msgs in session_all_msgs.items():
        for i, m in enumerate(all_msgs):
            if m["type"] == "user" and m.get("frustration", 0) >= 3:
                # Look backward for the most recent assistant message
                for j in range(i - 1, max(i - 5, -1), -1):
                    prev = all_msgs[j]
                    if prev["type"] == "assistant":
                        for tool in prev.get("tools", []):
                            tool_before_frustration[tool] += 1
                        # Extract topic keywords from assistant text
                        if prev.get("text"):
                            words = re.findall(r'\b[a-z]{4,}\b', prev["text"].lower()[:500])
                            for w in set(words):
                                if w not in ("this", "that", "with", "from", "have", "been",
                                             "will", "would", "could", "should", "here", "there",
                                             "then", "than", "what", "when", "where", "which",
                                             "your", "they", "their", "them", "into", "some",
                                             "each", "more", "also", "very", "just", "only",
                                             "need", "make", "like", "does", "done"):
                                    topic_before_frustration[w] += 1
                        break

    # Classify high-frustration messages to find them in user msgs too
    for m in all_user_messages:
        m_cats = m.get("categories", [])

    print(f"  Tools before high-frustration messages:")
    for tool, count in tool_before_frustration.most_common(15):
        print(f"    {tool:40s}: {count}")

    # Frustration distribution
    print("\n--- Frustration Score Distribution ---")
    frust_dist = Counter(m["frustration"] for m in all_user_messages)
    for score in range(6):
        count = frust_dist.get(score, 0)
        pct = count / max(total_user_msgs, 1) * 100
        bar = "#" * min(int(pct * 2), 60)
        print(f"  Level {score}: {count:5d} ({pct:5.1f}%) {bar}")

    # Per-project frustration
    print("\n--- Average Frustration by Project ---")
    proj_frust = defaultdict(list)
    for m in all_user_messages:
        proj_frust[m["project"]].append(m["frustration"])
    for proj in sorted(proj_frust.keys(), key=lambda p: -sum(proj_frust[p]) / len(proj_frust[p])):
        scores = proj_frust[proj]
        avg = sum(scores) / len(scores)
        high_pct = sum(1 for s in scores if s >= 3) / len(scores) * 100
        print(f"  {proj:35s}: avg={avg:.2f}  high(>=3)={high_pct:.1f}%  n={len(scores)}")

    results["escalations"] = escalations
    results["tool_before_frustration"] = tool_before_frustration
    results["frust_dist"] = frust_dist

    # ════════════════════════════════════════════════════════════════
    # ANALYSIS 4: Steering Vocabulary
    # ════════════════════════════════════════════════════════════════
    print("\n" + "=" * 70)
    print("ANALYSIS 4: STEERING VOCABULARY")
    print("=" * 70)

    # Focus on genuine correction/redirect messages, extract key phrases
    steering_msgs = [m for m in all_user_messages
                     if ("correction" in m["categories"] or "redirect" in m["categories"])
                     and m["length"] < 500]  # only short-ish human messages

    # Extract the core steering phrases
    phrase_counter = Counter()
    project_phrases = defaultdict(Counter)

    # Pattern: match the key correction/redirect phrase
    extraction_patterns = [
        (r'(no,\s+[^.!?\n]{3,40})', "no-clause"),
        (r'(not\s+(?:that|this|what|how|right|correct|it)[^.!?\n]{0,30})', "not-X"),
        (r'(instead[,]?\s+[^.!?\n]{3,40})', "instead-clause"),
        (r'(actually[,]?\s+[^.!?\n]{3,40})', "actually-clause"),
        (r'(i (?:said|meant|asked|wanted|told)[^.!?\n]{3,50})', "i-said"),
        (r'(why (?:did|are|is) you[^.!?\n]{3,50})', "why-you"),
        (r'(don\'?t\s+[^.!?\n]{3,30})', "dont-X"),
        (r'(stop\s+[^.!?\n]{3,30})', "stop-X"),
        (r'(wrong[^.!?\n]{0,30})', "wrong-X"),
        (r'(still\s+(?:not|wrong|broken|failing|missing|the same)[^.!?\n]{0,30})', "still-problem"),
        (r'(try\s+again[^.!?\n]{0,20})', "try-again"),
        (r'(revert[^.!?\n]{0,30})', "revert"),
        (r'(undo[^.!?\n]{0,30})', "undo"),
        (r'(forget[^.!?\n]{0,30})', "forget-X"),
        (r'(skip[^.!?\n]{0,30})', "skip-X"),
        (r'(ignore[^.!?\n]{0,30})', "ignore-X"),
        (r'(back to[^.!?\n]{3,30})', "back-to"),
        (r'(focus on[^.!?\n]{3,30})', "focus-on"),
        (r'(let\'?s\s+[^.!?\n]{3,40})', "lets-X"),
        (r'(nope[^.!?\n]{0,20})', "nope"),
    ]

    for m in steering_msgs:
        text_lower = m["text"].lower()
        for pattern, cluster in extraction_patterns:
            matches = re.findall(pattern, text_lower)
            for match in matches:
                phrase = match.strip()[:60]
                if len(phrase) >= 3:
                    phrase_counter[(cluster, phrase)] += 1
                    project_phrases[m["project"]][(cluster, phrase)] += 1

    # Show by cluster
    print(f"\n{len(steering_msgs)} steering messages analyzed")
    clusters = defaultdict(list)
    for (cluster, phrase), count in phrase_counter.most_common(200):
        clusters[cluster].append((phrase, count))

    print("\n--- Steering Phrase Clusters ---")
    for cluster in sorted(clusters.keys(), key=lambda c: -sum(n for _, n in clusters[c])):
        total = sum(n for _, n in clusters[cluster])
        phrases = clusters[cluster]
        print(f"\n  [{cluster}] ({total} occurrences)")
        for phrase, count in phrases[:8]:
            # Check universality
            proj_count = sum(1 for proj, pcounts in project_phrases.items()
                            if pcounts.get((cluster, phrase), 0) > 0)
            scope = "universal" if proj_count >= 3 else f"{proj_count} projects"
            print(f"    {count:3d}x \"{phrase}\"  [{scope}]")

    # Most common across projects (universal steering vocabulary)
    print("\n--- Universal Steering Phrases (appear in 3+ projects) ---")
    universal = []
    for (cluster, phrase), count in phrase_counter.most_common(200):
        proj_count = sum(1 for proj, pcounts in project_phrases.items()
                         if pcounts.get((cluster, phrase), 0) > 0)
        if proj_count >= 3 and count >= 3:
            universal.append((phrase, count, proj_count, cluster))
    universal.sort(key=lambda x: -x[1])
    for phrase, count, proj_count, cluster in universal[:25]:
        print(f"    {count:3d}x [{cluster:15s}] \"{phrase}\" ({proj_count} projects)")

    # Project-specific vocabulary
    print("\n--- Project-Specific Steering Phrases ---")
    for proj in sorted(project_phrases.keys()):
        unique = []
        for (cluster, phrase), count in project_phrases[proj].most_common(30):
            other = sum(project_phrases[p].get((cluster, phrase), 0)
                        for p in project_phrases if p != proj)
            if other == 0 and count >= 2:
                unique.append((phrase, count, cluster))
        if unique:
            print(f"\n  {proj}:")
            for phrase, count, cluster in unique[:5]:
                print(f"    {count:3d}x [{cluster}] \"{phrase}\"")

    results["steering_msgs_count"] = len(steering_msgs)
    results["clusters"] = dict(clusters)
    results["universal"] = universal

    # ════════════════════════════════════════════════════════════════
    # BONUS: Message examples for each high-frustration level
    # ════════════════════════════════════════════════════════════════
    print("\n" + "=" * 70)
    print("BONUS: HIGH-FRUSTRATION EXAMPLES (level >= 3)")
    print("=" * 70)

    for level in [3, 4, 5]:
        examples = [m for m in all_user_messages
                    if m["frustration"] == level and m["length"] < 300 and m["length"] > 10]
        print(f"\n  --- Level {level} ({len(examples)} messages) ---")
        for m in examples[:8]:
            print(f"    [{m['project']}] \"{m['text'][:120]}\"")

    # ════════════════════════════════════════════════════════════════
    # Summary
    # ════════════════════════════════════════════════════════════════
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)

    correction_rate = sum(1 for m in all_user_messages if "correction" in m["categories"]) / total_user_msgs * 100
    approval_rate = sum(1 for m in all_user_messages if "approval" in m["categories"]) / total_user_msgs * 100
    redirect_rate = sum(1 for m in all_user_messages if "redirect" in m["categories"]) / total_user_msgs * 100
    nudge_rate = sum(1 for m in all_user_messages if "nudge" in m["categories"]) / total_user_msgs * 100
    directive_rate = sum(1 for m in all_user_messages if "directive" in m["categories"]) / total_user_msgs * 100
    question_rate = sum(1 for m in all_user_messages if "question" in m["categories"]) / total_user_msgs * 100
    avg_len = sum(m["length"] for m in all_user_messages) / total_user_msgs

    print(f"\nProjects: {len(all_project_data)}")
    print(f"Files: {total_files}")
    print(f"User messages: {total_user_msgs}")
    print(f"Sessions: {len(session_user_msgs)}")
    print(f"Escalation sequences: {len(escalations)}")
    print(f"\nCorrection rate: {correction_rate:.1f}%")
    print(f"Approval rate: {approval_rate:.1f}%")
    print(f"Redirect rate: {redirect_rate:.1f}%")
    print(f"Nudge rate: {nudge_rate:.1f}%")
    print(f"Directive rate: {directive_rate:.1f}%")
    print(f"Question rate: {question_rate:.1f}%")
    print(f"Average message length: {avg_len:.0f} chars")
    print(f"Global correction:approval ratio: {correction_rate / max(approval_rate, 0.1):.2f}")

    results["total_user_msgs"] = total_user_msgs
    results["total_files"] = total_files
    results["correction_rate"] = correction_rate
    results["approval_rate"] = approval_rate
    results["redirect_rate"] = redirect_rate
    results["nudge_rate"] = nudge_rate
    results["directive_rate"] = directive_rate
    results["question_rate"] = question_rate
    results["avg_len"] = avg_len

    return results


if __name__ == "__main__":
    results = run_analysis()
