#!/usr/bin/env python3
"""
Experiment 010: Thinking Block Divergence Analysis

Analyzes the gap between agent private reasoning (thinking blocks) and
public output (text blocks) in Claude Code session transcripts.

Key insight: In Claude Code JSONL, an "assistant turn" consists of
multiple consecutive assistant messages. Thinking blocks and text blocks
are typically in SEPARATE messages within the same turn. We group
consecutive assistant messages into turns before analyzing.
"""

import json
import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, List

# ============================================================
# Configuration
# ============================================================

CORPUS_DIR = Path(os.environ.get(
    "CORPUS_DIR",
    os.environ.get("MIDDENS_CORPUS", "corpus/"),
))

# Keyword sets for sentiment/confidence analysis
UNCERTAINTY_MARKERS = [
    "not sure", "might", "maybe", "could be", "i think", "unclear",
    "hmm", "wait", "perhaps", "possibly", "not certain", "unsure",
    "don't know", "need to check", "let me reconsider", "actually",
    "on second thought", "I wonder", "tricky", "complicated",
    "not obvious", "hard to tell", "risky", "careful",
    "shouldn't", "problem", "issue", "concern", "worry",
    "alternative", "or maybe", "another approach", "but what if",
    "not ideal", "might not work", "could fail", "edge case",
    "I need to think", "let me think", "reconsider",
]

CONFIDENCE_MARKERS = [
    "I'll", "Here's", "The solution is", "Let me", "I've",
    "Here is", "This will", "I can", "Done", "Successfully",
    "The fix is", "We need to", "The answer is", "I found",
    "The issue is", "The problem is", "This is because",
    "Now I'll", "Next,", "First,", "I've implemented",
    "I've fixed", "I've updated", "I've added", "I've created",
    "The correct", "Simply", "Just", "Straightforward",
    "Obviously", "Clearly",
]

CORRECTION_MARKERS = [
    "no,", "no.", "that's wrong", "that's not", "incorrect",
    "actually,", "you should", "instead,", "not what I", "wrong",
    "that doesn't", "please fix", "fix this", "try again",
    "that's not right", "not correct", "error", "broken",
    "doesn't work", "didn't work", "you missed", "you forgot",
    "I said", "I meant", "I asked for", "but I wanted",
    "stop", "wait,", "hold on", "not like that",
    "revert", "undo",
]

PLAN_MARKERS = [
    "option 1", "option 2", "option 3",
    "approach 1", "approach 2", "approach 3",
    "alternative", "could also", "another way",
    "first approach", "second approach",
    "one option", "another option",
    "plan a", "plan b",
    "either", "or we could", "versus",
    "trade-off", "tradeoff", "pros and cons",
]

RISK_MARKERS = [
    "risk", "dangerous", "careful", "might break", "could break",
    "side effect", "backwards compatible", "breaking change",
    "regression", "untested", "fragile", "brittle",
    "security", "vulnerability", "race condition",
    "edge case", "corner case", "overflow", "undefined behavior",
    "deadlock", "memory leak", "performance", "bottleneck",
]

DOUBT_ABOUT_TOOL_MARKERS = [
    "not sure if this", "wrong tool", "better tool",
    "should I use", "maybe I should read", "let me check first",
    "before running", "might not exist", "file might not",
    "path might", "could be wrong path", "not sure about the path",
    "this might fail", "if this fails",
]


# ============================================================
# Data structures
# ============================================================

@dataclass
class AssistantTurn:
    """A group of consecutive assistant messages forming one turn."""
    session_id: str
    project: str
    turn_index: int
    thinking_text: str  # All thinking blocks concatenated
    public_text: str    # All text blocks concatenated
    has_tool_use: bool
    tool_names: list = field(default_factory=list)
    # Derived metrics
    thinking_len: int = 0
    public_len: int = 0
    uncertainty_count: int = 0
    confidence_count: int = 0
    plan_alternatives: int = 0
    risk_mentions: int = 0
    doubt_about_tool: int = 0
    followed_by_correction: bool = False
    transparent_uncertainty: bool = False
    # For tracking public-side uncertainty markers
    public_uncertainty_count: int = 0


@dataclass
class SessionStats:
    session_id: str
    project: str
    total_turns: int = 0
    turns_with_thinking: int = 0
    turns_with_text: int = 0
    turns_with_both: int = 0
    total_thinking_chars: int = 0
    total_public_chars: int = 0
    total_user_messages: int = 0
    turns: list = field(default_factory=list)


# ============================================================
# Parsing
# ============================================================

def count_markers(text: str, markers: list) -> int:
    text_lower = text.lower()
    count = 0
    for marker in markers:
        if marker.lower() in text_lower:
            count += 1
    return count


def extract_user_text(msg: dict) -> str:
    content = msg.get("content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if block.get("type") == "text":
                parts.append(block.get("text", ""))
        return " ".join(parts)
    return ""


def process_session(filepath: Path) -> Optional[SessionStats]:
    """Process a single JSONL session file, grouping assistant messages into turns."""
    session_id = filepath.stem
    project = filepath.parent.name

    stats = SessionStats(session_id=session_id, project=project)

    # Read all messages in order, keeping only assistant/user
    events = []
    try:
        with open(filepath) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    t = obj.get("type")
                    if t in ("assistant", "user"):
                        events.append(obj)
                except json.JSONDecodeError:
                    continue
    except Exception:
        return None

    if not events:
        return None

    # Group into turns: consecutive assistant messages form one turn,
    # user messages are standalone
    turns = []  # list of (type, data)
    current_assistant_group = []

    for evt in events:
        t = evt.get("type")
        if t == "assistant":
            current_assistant_group.append(evt)
        else:
            # Flush assistant group
            if current_assistant_group:
                turns.append(("assistant", current_assistant_group))
                current_assistant_group = []
            turns.append(("user", evt))

    if current_assistant_group:
        turns.append(("assistant", current_assistant_group))

    # Now process turns
    assistant_turns = []

    for idx, (turn_type, turn_data) in enumerate(turns):
        if turn_type == "assistant":
            messages = turn_data
            thinking_parts = []
            text_parts = []
            has_tool_use = False
            tool_names = []

            for msg in messages:
                content = msg.get("message", {}).get("content", [])
                if not isinstance(content, list):
                    continue
                for block in content:
                    bt = block.get("type")
                    if bt == "thinking":
                        t_text = block.get("thinking", "")
                        if t_text.strip():
                            thinking_parts.append(t_text)
                    elif bt == "text":
                        t_text = block.get("text", "")
                        if t_text.strip():
                            text_parts.append(t_text)
                    elif bt == "tool_use":
                        has_tool_use = True
                        tool_names.append(block.get("name", ""))

            thinking_text = "\n".join(thinking_parts)
            public_text = "\n".join(text_parts)

            stats.total_turns += 1
            has_thinking = bool(thinking_text.strip())
            has_text = bool(public_text.strip())

            if has_thinking:
                stats.turns_with_thinking += 1
            if has_text:
                stats.turns_with_text += 1
            if has_thinking and has_text:
                stats.turns_with_both += 1

            if has_thinking:
                stats.total_thinking_chars += len(thinking_text)
                stats.total_public_chars += len(public_text)

                pub_unc = count_markers(public_text, UNCERTAINTY_MARKERS)
                turn_obj = AssistantTurn(
                    session_id=session_id,
                    project=project,
                    turn_index=idx,
                    thinking_text=thinking_text,
                    public_text=public_text,
                    has_tool_use=has_tool_use,
                    tool_names=tool_names,
                    thinking_len=len(thinking_text),
                    public_len=len(public_text),
                    uncertainty_count=count_markers(thinking_text, UNCERTAINTY_MARKERS),
                    confidence_count=count_markers(public_text, CONFIDENCE_MARKERS),
                    plan_alternatives=count_markers(thinking_text, PLAN_MARKERS),
                    risk_mentions=count_markers(thinking_text, RISK_MARKERS),
                    doubt_about_tool=count_markers(thinking_text, DOUBT_ABOUT_TOOL_MARKERS),
                    transparent_uncertainty=pub_unc > 0,
                    public_uncertainty_count=pub_unc,
                )
                assistant_turns.append(turn_obj)

                # Check next turn for user correction
                if idx + 1 < len(turns):
                    next_type, next_data = turns[idx + 1]
                    if next_type == "user":
                        user_text = extract_user_text(next_data.get("message", {}))
                        if user_text.strip() and "[Request interrupted" not in user_text:
                            is_correction = count_markers(user_text, CORRECTION_MARKERS) > 0
                            # Short terse negatives
                            words = user_text.strip().split()
                            is_terse_negative = (
                                len(words) <= 6 and
                                any(w in user_text.lower() for w in ["no", "wrong", "stop", "fix", "revert"])
                            )
                            turn_obj.followed_by_correction = is_correction or is_terse_negative

        elif turn_type == "user":
            stats.total_user_messages += 1

    stats.turns = assistant_turns

    if not assistant_turns:
        return None

    return stats


# ============================================================
# Analysis
# ============================================================

def _find_jsonl_files(root):
    """Find all .jsonl files under root, following symlinks."""
    results = []
    for dirpath, dirnames, filenames in os.walk(root, followlinks=True):
        for fn in filenames:
            if fn.endswith(".jsonl"):
                results.append(Path(dirpath) / fn)
    return sorted(results)


def run_analysis():
    """Main analysis function."""
    session_files = _find_jsonl_files(CORPUS_DIR)

    print(f"Found {len(session_files)} session files across third-thoughts corpus")
    print("Processing...", file=sys.stderr)

    all_stats = []
    all_turns = []
    processed = 0
    skipped = 0

    for sf in session_files:
        stats = process_session(sf)
        if stats:
            all_stats.append(stats)
            all_turns.extend(stats.turns)
            processed += 1
        else:
            skipped += 1
        if (processed + skipped) % 200 == 0:
            print(f"  Processed {processed + skipped}/{len(session_files)}...", file=sys.stderr)

    print(f"\nProcessed {processed} sessions with thinking, skipped {skipped}", file=sys.stderr)

    # Filter to turns that have BOTH thinking and text (the interesting cases)
    paired_turns = [t for t in all_turns if t.thinking_len > 0 and t.public_len > 0]
    thinking_only_turns = [t for t in all_turns if t.thinking_len > 0 and t.public_len == 0]

    # ============================================================
    # ANALYSIS 1: PRESENCE AND VOLUME
    # ============================================================
    print("\n" + "=" * 70)
    print("ANALYSIS 1: PRESENCE AND VOLUME")
    print("=" * 70)

    total_turns = sum(s.total_turns for s in all_stats)
    total_with_thinking = sum(s.turns_with_thinking for s in all_stats)
    total_with_text = sum(s.turns_with_text for s in all_stats)
    total_with_both = sum(s.turns_with_both for s in all_stats)

    pct_thinking = (total_with_thinking / total_turns * 100) if total_turns else 0
    pct_text = (total_with_text / total_turns * 100) if total_turns else 0
    pct_both = (total_with_both / total_turns * 100) if total_turns else 0

    total_thinking_chars = sum(s.total_thinking_chars for s in all_stats)
    total_public_chars = sum(s.total_public_chars for s in all_stats)

    print(f"\nTotal sessions analyzed: {len(all_stats)}")
    print(f"Total assistant turns: {total_turns}")
    print(f"  Turns with thinking: {total_with_thinking} ({pct_thinking:.1f}%)")
    print(f"  Turns with public text: {total_with_text} ({pct_text:.1f}%)")
    print(f"  Turns with BOTH thinking+text: {total_with_both} ({pct_both:.1f}%)")
    print(f"  Turns with thinking only (no text): {len(thinking_only_turns)}")

    print(f"\nVolume (for turns with thinking):")
    print(f"  Total thinking chars: {total_thinking_chars:,}")
    print(f"  Total public text chars: {total_public_chars:,}")
    if total_public_chars:
        print(f"  Global ratio (thinking/public): {total_thinking_chars / total_public_chars:.2f}x")
    print(f"  ~Thinking tokens: {total_thinking_chars // 4:,}")
    print(f"  ~Public tokens: {total_public_chars // 4:,}")

    if paired_turns:
        avg_thinking = sum(t.thinking_len for t in paired_turns) / len(paired_turns)
        avg_public = sum(t.public_len for t in paired_turns) / len(paired_turns)
        per_turn_ratios = [t.thinking_len / t.public_len for t in paired_turns if t.public_len > 0]
        per_turn_ratios.sort()
        print(f"\nPer-turn averages (turns with both thinking+text, n={len(paired_turns)}):")
        print(f"  Avg thinking length: {avg_thinking:,.0f} chars ({avg_thinking/4:,.0f} ~tokens)")
        print(f"  Avg public text length: {avg_public:,.0f} chars ({avg_public/4:,.0f} ~tokens)")
        if per_turn_ratios:
            print(f"  Thinking/public ratio:")
            print(f"    Min: {per_turn_ratios[0]:.2f}x")
            print(f"    P25: {per_turn_ratios[len(per_turn_ratios)//4]:.2f}x")
            print(f"    Median: {per_turn_ratios[len(per_turn_ratios)//2]:.2f}x")
            print(f"    P75: {per_turn_ratios[3*len(per_turn_ratios)//4]:.2f}x")
            print(f"    P95: {per_turn_ratios[int(len(per_turn_ratios)*0.95)]:.2f}x")
            print(f"    Max: {per_turn_ratios[-1]:.2f}x")
            print(f"    Mean: {sum(per_turn_ratios)/len(per_turn_ratios):.2f}x")

    # Thinking block size distribution
    thinking_lens = sorted([t.thinking_len for t in all_turns])
    if thinking_lens:
        print(f"\nThinking block size distribution (all {len(thinking_lens)} turns):")
        print(f"  Min: {thinking_lens[0]:,} chars")
        print(f"  P25: {thinking_lens[len(thinking_lens)//4]:,} chars")
        print(f"  Median: {thinking_lens[len(thinking_lens)//2]:,} chars")
        print(f"  P75: {thinking_lens[3*len(thinking_lens)//4]:,} chars")
        print(f"  P95: {thinking_lens[int(len(thinking_lens)*0.95)]:,} chars")
        print(f"  Max: {thinking_lens[-1]:,} chars")

    # Session-level ratio
    session_ratios = []
    for s in all_stats:
        if s.total_public_chars > 100:  # Only sessions with meaningful text
            ratio = s.total_thinking_chars / s.total_public_chars
            session_ratios.append((s.session_id, s.project, ratio))
    session_ratios.sort(key=lambda x: x[2])
    if session_ratios:
        ratios_only = [r[2] for r in session_ratios]
        print(f"\nSession-level thinking/public ratio (sessions with >100 chars public text, n={len(session_ratios)}):")
        print(f"  Min: {ratios_only[0]:.2f}x")
        print(f"  Median: {ratios_only[len(ratios_only)//2]:.2f}x")
        print(f"  Mean: {sum(ratios_only)/len(ratios_only):.2f}x")
        print(f"  Max: {ratios_only[-1]:.2f}x")

    # ============================================================
    # ANALYSIS 2: SENTIMENT/CONFIDENCE DIVERGENCE
    # ============================================================
    print("\n" + "=" * 70)
    print("ANALYSIS 2: SENTIMENT/CONFIDENCE DIVERGENCE")
    print("=" * 70)

    # Use paired_turns (have both thinking and text) for divergence analysis
    analysis_set = paired_turns
    print(f"\nAnalyzing {len(analysis_set)} turns with both thinking and public text")

    uncertain_thinking = [t for t in analysis_set if t.uncertainty_count > 0]
    confident_public = [t for t in analysis_set if t.confidence_count > 0]
    divergent = [t for t in analysis_set if t.uncertainty_count > 0 and t.confidence_count > 0]
    highly_divergent = [t for t in analysis_set if t.uncertainty_count >= 3 and t.confidence_count >= 2]

    print(f"\n  Thinking contains uncertainty: {len(uncertain_thinking)} ({len(uncertain_thinking)/len(analysis_set)*100:.1f}%)" if analysis_set else "")
    print(f"  Public text contains confidence markers: {len(confident_public)} ({len(confident_public)/len(analysis_set)*100:.1f}%)" if analysis_set else "")
    print(f"  DIVERGENT (uncertain thinking + confident output): {len(divergent)} ({len(divergent)/len(analysis_set)*100:.1f}%)" if analysis_set else "")
    print(f"  HIGHLY DIVERGENT (uncertainty>=3, confidence>=2): {len(highly_divergent)} ({len(highly_divergent)/len(analysis_set)*100:.1f}%)" if analysis_set else "")

    # Also analyze ALL turns with thinking (including thinking-only)
    all_uncertain = [t for t in all_turns if t.uncertainty_count > 0]
    print(f"\n  For context: all turns with uncertainty in thinking: {len(all_uncertain)}/{len(all_turns)} ({len(all_uncertain)/len(all_turns)*100:.1f}%)" if all_turns else "")

    # Top uncertainty markers
    unc_counter = Counter()
    for t in all_turns:
        text_lower = t.thinking_text.lower()
        for marker in UNCERTAINTY_MARKERS:
            if marker.lower() in text_lower:
                unc_counter[marker] += 1

    print(f"\nTop uncertainty markers in thinking (across all {len(all_turns)} turns):")
    for marker, count in unc_counter.most_common(15):
        pct = count / len(all_turns) * 100
        print(f"  '{marker}': {count} ({pct:.1f}% of turns)")

    # Top confidence markers (only in paired turns)
    conf_counter = Counter()
    for t in analysis_set:
        text_lower = t.public_text.lower()
        for marker in CONFIDENCE_MARKERS:
            if marker.lower() in text_lower:
                conf_counter[marker] += 1

    print(f"\nTop confidence markers in public text (n={len(analysis_set)} paired turns):")
    for marker, count in conf_counter.most_common(15):
        pct = count / len(analysis_set) * 100 if analysis_set else 0
        print(f"  '{marker}': {count} ({pct:.1f}%)")

    # Show top divergent examples
    print(f"\n--- Top 5 most divergent messages (uncertain thinking + confident output) ---")
    divergent_scored = [(t, t.uncertainty_count * t.confidence_count) for t in divergent]
    divergent_scored.sort(key=lambda x: -x[1])
    for turn, score in divergent_scored[:5]:
        print(f"\n  Project: {turn.project}")
        print(f"  Session: {turn.session_id}")
        print(f"  Divergence score: {score} (unc={turn.uncertainty_count}, conf={turn.confidence_count})")
        print(f"  THINKING ({turn.thinking_len}c): {turn.thinking_text[:400]}...")
        print(f"  PUBLIC ({turn.public_len}c): {turn.public_text[:400]}...")

    # ============================================================
    # ANALYSIS 3: PLAN DIVERGENCE
    # ============================================================
    print("\n" + "=" * 70)
    print("ANALYSIS 3: PLAN DIVERGENCE")
    print("=" * 70)

    # Use all turns with thinking for plan analysis
    multi_approach = [t for t in all_turns if t.plan_alternatives >= 2]
    multi_approach_paired = [t for t in paired_turns if t.plan_alternatives >= 2]

    print(f"\nTurns where thinking considers multiple approaches: {len(multi_approach)} ({len(multi_approach)/len(all_turns)*100:.1f}%)")
    if multi_approach_paired:
        suppressed_plans = [t for t in multi_approach_paired if count_markers(t.public_text, PLAN_MARKERS) == 0]
        print(f"  Of those with public text: {len(multi_approach_paired)}")
        print(f"  Alternatives NOT mentioned in public: {len(suppressed_plans)} ({len(suppressed_plans)/len(multi_approach_paired)*100:.1f}%)")

    # Risk mentions
    risk_in_thinking = [t for t in all_turns if t.risk_mentions > 0]
    risk_paired = [t for t in paired_turns if t.risk_mentions > 0]
    risk_suppressed = [t for t in risk_paired if count_markers(t.public_text, RISK_MARKERS) == 0]

    print(f"\nTurns with risk mentions in thinking: {len(risk_in_thinking)} ({len(risk_in_thinking)/len(all_turns)*100:.1f}%)")
    if risk_paired:
        print(f"  Of those with public text: {len(risk_paired)}")
        print(f"  Risk NOT mentioned in public: {len(risk_suppressed)} ({len(risk_suppressed)/len(risk_paired)*100:.1f}% suppressed)")

    # Tool doubt
    tool_doubt = [t for t in all_turns if t.doubt_about_tool > 0 and t.has_tool_use]
    print(f"\nTurns with tool doubt in thinking but proceeds: {len(tool_doubt)} ({len(tool_doubt)/len(all_turns)*100:.1f}%)")

    # Examples
    print(f"\n--- Examples of plan suppression (multi-approach thinking, single-approach output) ---")
    shown = 0
    for t in multi_approach_paired:
        pub_alt = count_markers(t.public_text, PLAN_MARKERS)
        if pub_alt == 0 and shown < 5:
            print(f"\n  Project: {t.project}")
            print(f"  Session: {t.session_id}")
            print(f"  Alternatives in thinking: {t.plan_alternatives}")
            print(f"  THINKING: {t.thinking_text[:500]}...")
            print(f"  PUBLIC: {t.public_text[:300]}...")
            shown += 1

    print(f"\n--- Examples of risk suppression ---")
    shown = 0
    for t in risk_suppressed:
        if t.risk_mentions >= 2 and shown < 5:
            print(f"\n  Project: {t.project}")
            print(f"  Risk markers in thinking: {t.risk_mentions}")
            # Extract risk contexts
            text_lower = t.thinking_text.lower()
            for marker in RISK_MARKERS:
                if marker in text_lower:
                    idx = text_lower.find(marker)
                    start = max(0, idx - 60)
                    end = min(len(t.thinking_text), idx + len(marker) + 120)
                    print(f"    Risk: '...{t.thinking_text[start:end]}...'")
                    break
            print(f"  PUBLIC (no risk): {t.public_text[:200]}...")
            shown += 1

    # ============================================================
    # ANALYSIS 4: CORRELATION WITH CORRECTIONS
    # ============================================================
    print("\n" + "=" * 70)
    print("ANALYSIS 4: CORRELATION WITH CORRECTIONS")
    print("=" * 70)

    # Use all turns with thinking
    corrected = [t for t in all_turns if t.followed_by_correction]
    not_corrected = [t for t in all_turns if not t.followed_by_correction]

    print(f"\nTotal turns with thinking: {len(all_turns)}")
    print(f"  Followed by user correction: {len(corrected)} ({len(corrected)/len(all_turns)*100:.1f}%)")
    print(f"  NOT followed by correction: {len(not_corrected)} ({len(not_corrected)/len(all_turns)*100:.1f}%)")

    def avg_metric(turns, attr):
        if not turns:
            return 0.0
        return sum(getattr(t, attr) for t in turns) / len(turns)

    if corrected:
        print(f"\nMetrics comparison (corrected vs not corrected):")
        print(f"  Avg uncertainty in thinking:")
        print(f"    Corrected: {avg_metric(corrected, 'uncertainty_count'):.2f}")
        print(f"    Not corrected: {avg_metric(not_corrected, 'uncertainty_count'):.2f}")
        print(f"  Avg confidence in public:")
        print(f"    Corrected: {avg_metric(corrected, 'confidence_count'):.2f}")
        print(f"    Not corrected: {avg_metric(not_corrected, 'confidence_count'):.2f}")
        print(f"  Avg thinking length:")
        print(f"    Corrected: {avg_metric(corrected, 'thinking_len'):,.0f} chars")
        print(f"    Not corrected: {avg_metric(not_corrected, 'thinking_len'):,.0f} chars")
        print(f"  Avg public text length:")
        print(f"    Corrected: {avg_metric(corrected, 'public_len'):,.0f} chars")
        print(f"    Not corrected: {avg_metric(not_corrected, 'public_len'):,.0f} chars")
        print(f"  Avg risk mentions:")
        print(f"    Corrected: {avg_metric(corrected, 'risk_mentions'):.2f}")
        print(f"    Not corrected: {avg_metric(not_corrected, 'risk_mentions'):.2f}")

    # High-divergence vs low-divergence correction rate
    high_div = [t for t in paired_turns if t.uncertainty_count >= 3 and t.confidence_count >= 2]
    low_div = [t for t in paired_turns if t.uncertainty_count == 0 and t.confidence_count >= 1]
    med_div = [t for t in paired_turns if t.uncertainty_count >= 1 and t.confidence_count >= 1 and not (t.uncertainty_count >= 3 and t.confidence_count >= 2)]

    def correction_rate(turns):
        if not turns:
            return 0.0
        return sum(1 for t in turns if t.followed_by_correction) / len(turns) * 100

    print(f"\nCorrection rate by divergence level (paired turns only):")
    if high_div:
        print(f"  High divergence (unc>=3, conf>=2): n={len(high_div)}, corrected={correction_rate(high_div):.1f}%")
    if med_div:
        print(f"  Medium divergence: n={len(med_div)}, corrected={correction_rate(med_div):.1f}%")
    if low_div:
        print(f"  Low divergence (unc=0, conf>=1): n={len(low_div)}, corrected={correction_rate(low_div):.1f}%")

    # Transparency effect
    transparent = [t for t in paired_turns if t.transparent_uncertainty and t.uncertainty_count > 0]
    opaque = [t for t in paired_turns if not t.transparent_uncertainty and t.uncertainty_count > 0]

    print(f"\nTransparency effect (paired turns with uncertainty in thinking):")
    if transparent:
        print(f"  Transparent (uncertainty shared in public): n={len(transparent)}, corrected={correction_rate(transparent):.1f}%")
    else:
        print(f"  Transparent: none found")
    if opaque:
        print(f"  Opaque (uncertainty hidden from public): n={len(opaque)}, corrected={correction_rate(opaque):.1f}%")
    else:
        print(f"  Opaque: none found")

    # Also check across ALL turns
    all_transparent = [t for t in all_turns if t.transparent_uncertainty and t.uncertainty_count > 0]
    all_opaque = [t for t in all_turns if not t.transparent_uncertainty and t.uncertainty_count > 0]

    print(f"\nTransparency across ALL turns with uncertainty:")
    if all_transparent:
        print(f"  Transparent: n={len(all_transparent)}, corrected={correction_rate(all_transparent):.1f}%")
    if all_opaque:
        print(f"  Opaque: n={len(all_opaque)}, corrected={correction_rate(all_opaque):.1f}%")

    # Correction examples
    print(f"\n--- Examples of corrected turns ---")
    shown = 0
    for t in corrected:
        if t.public_len > 50 and shown < 5:
            print(f"\n  Project: {t.project}")
            print(f"  Session: {t.session_id}")
            print(f"  Uncertainty: {t.uncertainty_count}, Confidence: {t.confidence_count}")
            print(f"  THINKING: {t.thinking_text[:300]}...")
            print(f"  PUBLIC: {t.public_text[:300]}...")
            shown += 1

    # ============================================================
    # SUMMARY
    # ============================================================
    print("\n" + "=" * 70)
    print("SUMMARY: KEY PATTERNS")
    print("=" * 70)

    # Per-project stats
    project_data = defaultdict(lambda: {"turns": 0, "uncertainty": 0, "paired": 0, "corrected": 0})
    for t in all_turns:
        pd = project_data[t.project]
        pd["turns"] += 1
        pd["uncertainty"] += t.uncertainty_count
        if t.public_len > 0:
            pd["paired"] += 1
        if t.followed_by_correction:
            pd["corrected"] += 1

    print(f"\nPer-project breakdown (sorted by avg uncertainty):")
    proj_list = [(p, d) for p, d in project_data.items() if d["turns"] >= 5]
    proj_list.sort(key=lambda x: -x[1]["uncertainty"]/x[1]["turns"])
    for proj, d in proj_list[:15]:
        avg_unc = d["uncertainty"] / d["turns"]
        corr_rate = d["corrected"] / d["turns"] * 100 if d["turns"] else 0
        print(f"  {proj}: {d['turns']} turns, avg_unc={avg_unc:.2f}, paired={d['paired']}, corrected={corr_rate:.1f}%")

    # Thinking-only turns analysis
    print(f"\nThinking-only turns (thinking without public text): {len(thinking_only_turns)}")
    if thinking_only_turns:
        to_with_tools = sum(1 for t in thinking_only_turns if t.has_tool_use)
        print(f"  With tool use: {to_with_tools} ({to_with_tools/len(thinking_only_turns)*100:.1f}%)")
        print(f"  Pure thinking (no tools, no text): {len(thinking_only_turns) - to_with_tools}")
        avg_to_len = sum(t.thinking_len for t in thinking_only_turns) / len(thinking_only_turns)
        print(f"  Avg thinking length: {avg_to_len:,.0f} chars")

    # Compression analysis
    highly_compressed = [t for t in paired_turns if t.thinking_len > 500 and t.public_len > 0 and t.thinking_len / t.public_len > 5]
    print(f"\nHighly compressed turns (thinking > 5x public text, both >0): {len(highly_compressed)}")
    if highly_compressed:
        for t in highly_compressed[:3]:
            ratio = t.thinking_len / t.public_len
            print(f"  Ratio {ratio:.1f}x: Thinking {t.thinking_len}c -> Public {t.public_len}c")
            print(f"    THINKING: {t.thinking_text[:200]}...")
            print(f"    PUBLIC: {t.public_text[:200]}...")

    print("\n" + "=" * 70)
    print("RAW DATA FOR REPORT")
    print("=" * 70)

    # Collect all key metrics as a summary dict
    results = {
        "total_sessions": len(all_stats),
        "total_turns": total_turns,
        "total_with_thinking": total_with_thinking,
        "pct_with_thinking": pct_thinking,
        "total_with_both": total_with_both,
        "pct_with_both": pct_both,
        "total_thinking_chars": total_thinking_chars,
        "total_public_chars": total_public_chars,
        "thinking_public_ratio": total_thinking_chars / total_public_chars if total_public_chars else float('inf'),
        "n_paired": len(paired_turns),
        "n_thinking_only": len(thinking_only_turns),
        "n_uncertain_thinking": len(uncertain_thinking),
        "pct_uncertain": len(uncertain_thinking) / len(analysis_set) * 100 if analysis_set else 0,
        "n_confident_public": len(confident_public),
        "pct_confident": len(confident_public) / len(analysis_set) * 100 if analysis_set else 0,
        "n_divergent": len(divergent),
        "pct_divergent": len(divergent) / len(analysis_set) * 100 if analysis_set else 0,
        "n_highly_divergent": len(highly_divergent),
        "n_multi_approach": len(multi_approach),
        "pct_multi_approach": len(multi_approach) / len(all_turns) * 100 if all_turns else 0,
        "n_risk_in_thinking": len(risk_in_thinking),
        "pct_risk": len(risk_in_thinking) / len(all_turns) * 100 if all_turns else 0,
        "n_risk_suppressed": len(risk_suppressed),
        "pct_risk_suppressed": len(risk_suppressed) / len(risk_paired) * 100 if risk_paired else 0,
        "n_corrected": len(corrected),
        "pct_corrected": len(corrected) / len(all_turns) * 100 if all_turns else 0,
        "n_transparent": len(all_transparent),
        "n_opaque": len(all_opaque),
        "trans_correction_rate": correction_rate(all_transparent),
        "opaque_correction_rate": correction_rate(all_opaque),
        "avg_corrected_uncertainty": avg_metric(corrected, 'uncertainty_count') if corrected else 0,
        "avg_not_corrected_uncertainty": avg_metric(not_corrected, 'uncertainty_count'),
        "avg_corrected_thinking_len": avg_metric(corrected, 'thinking_len') if corrected else 0,
        "avg_not_corrected_thinking_len": avg_metric(not_corrected, 'thinking_len'),
    }

    for k, v in results.items():
        if isinstance(v, float):
            print(f"  {k}: {v:.2f}")
        else:
            print(f"  {k}: {v}")

    return results


if __name__ == "__main__":
    results = run_analysis()
