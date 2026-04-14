import sys
import json
import os
from typing import List, Dict, Any, Optional, Tuple

try:
    from prefixspan import PrefixSpan
except ImportError:
    print("Error: prefixspan library not installed. Run: pip install prefixspan", file=sys.stderr)
    sys.exit(1)

def extract_tool_sequences(sessions: List[Dict[str, Any]]) -> List[List[str]]:
    """Extract sequences of tool-call names from assistant messages."""
    sequences = []
    for session in sessions:
        messages = session.get("messages", [])
        tool_sequence = []
        for msg in messages:
            if msg.get("role") == "Assistant":
                tool_calls = msg.get("tool_calls", [])
                if tool_calls:
                    for tc in tool_calls:
                        if isinstance(tc, dict):
                            tool_name = tc.get("name", "")
                            if tool_name:
                                tool_sequence.append(tool_name)
        if tool_sequence:
            sequences.append(tool_sequence)
    return sequences

def get_correction_rate(session: Dict[str, Any]) -> float:
    """Calculate correction rate for a session."""
    messages = session.get("messages", [])
    user_msgs = [m for m in messages if m.get("role") == "User"]
    total = len(user_msgs)
    if total == 0:
        return 0.0

    corrections = sum(1 for m in user_msgs if m.get("classification") == "HumanCorrection")
    return corrections / total



def main():
    if len(sys.argv) < 2:
        print("Usage: python prefixspan_mining.py <input_json_path>", file=sys.stderr)
        sys.exit(1)

    input_path = sys.argv[1]
    if not os.path.exists(input_path):
        print(f"Error: Input file not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    try:
        with open(input_path, 'r') as f:
            sessions = json.load(f)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in input file: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error reading file: {e}", file=sys.stderr)
        sys.exit(1)

    if not sessions:
        print(json.dumps({"name": "prefixspan_mining", "summary": "0 sessions were analyzed.", "findings": [], "tables": []}))
        sys.exit(0)

    if len(sessions) < 5:
        result = {
            "name": "prefixspan_mining",
            "summary": f"Insufficient sessions for pattern mining (found {len(sessions)}, need at least 5). 0 sessions were analyzed.",
            "findings": [],
            "tables": []
        }
        print(json.dumps(result))
        sys.exit(0)

    sequences = extract_tool_sequences(sessions)
    if not sequences:
        result = {
            "name": "prefixspan_mining",
            "summary": f"No tool call sequences found in {len(sessions)} sessions",
            "findings": [
                {"label": "total_sessions", "value": len(sessions), "description": "Total sessions analyzed"},
                {"label": "sequences_extracted", "value": 0, "description": "Sessions with tool call sequences"},
                {"label": "total_patterns", "value": 0, "description": "Total frequent patterns found"},
                {"label": "patterns_length_3", "value": 0, "description": "Patterns of length 3"},
                {"label": "patterns_length_4", "value": 0, "description": "Patterns of length 4"},
                {"label": "success_patterns", "value": 0, "description": "Patterns enriched in low-correction sessions"},
                {"label": "struggle_patterns", "value": 0, "description": "Patterns enriched in high-correction sessions"}
            ],
            "tables": [],
            "figures": []
        }
        print(json.dumps(result))
        sys.exit(0)

    min_support = max(2, int(0.15 * len(sequences)))

    ps = PrefixSpan(sequences)
    # Use topk to limit combinatorial explosion, then filter by length
    all_patterns = ps.topk(200)

    filtered_patterns = [(pattern, support) for support, pattern in all_patterns
                         if 3 <= len(pattern) <= 6 and support >= min_support]
    
    total_patterns = len(filtered_patterns)
    patterns_len_3 = sum(1 for p, _ in filtered_patterns if len(p) == 3)
    patterns_len_4 = sum(1 for p, _ in filtered_patterns if len(p) == 4)
    patterns_len_5 = sum(1 for p, _ in filtered_patterns if len(p) == 5)
    patterns_len_6 = sum(1 for p, _ in filtered_patterns if len(p) == 6)

    # Build correction-rate cohorts aligned with sequences.
    # extract_tool_sequences() skips sessions with no tool calls, so we cannot
    # use session indexes to index into sequences. Instead we build the cohorts
    # in a single pass over sessions, appending only for sessions that
    # contributed a sequence (same filter as extract_tool_sequences).
    low_corr_sequences = []
    high_corr_sequences = []
    seq_idx = 0
    for session in sessions:
        messages = session.get("messages", [])
        has_tools = any(
            isinstance(tc, dict) and tc.get("name")
            for msg in messages if msg.get("role") == "Assistant"
            for tc in msg.get("tool_calls", [])
        )
        if not has_tools:
            continue
        if seq_idx >= len(sequences):
            break
        rate = get_correction_rate(session)
        seq = sequences[seq_idx]
        if rate <= 0.10:
            low_corr_sequences.append(seq)
        elif rate > 0.25:
            high_corr_sequences.append(seq)
        seq_idx += 1

    def count_pattern_support(pattern: Tuple[str, ...], seq_list: List[List[str]]) -> int:
        count = 0
        for seq in seq_list:
            if len(pattern) > len(seq):
                continue
            for i in range(len(seq) - len(pattern) + 1):
                if tuple(seq[i:i+len(pattern)]) == pattern:
                    count += 1
                    break
        return count

    discriminative_patterns = []
    success_patterns = 0
    struggle_patterns = 0

    for pattern, total_support in filtered_patterns:
        low_support = count_pattern_support(tuple(pattern), low_corr_sequences)
        high_support = count_pattern_support(tuple(pattern), high_corr_sequences)
        
        low_pct = (low_support / len(low_corr_sequences) * 100) if low_corr_sequences else 0
        high_pct = (high_support / len(high_corr_sequences) * 100) if high_corr_sequences else 0
        
        if high_support > 0 and low_support / high_support > 2:
            discriminative_patterns.append([
                " -> ".join(pattern),
                "low-correction (success)",
                round(low_support / high_support, 2),
            ])
            success_patterns += 1
        elif low_support > 0 and high_support / low_support > 2:
            discriminative_patterns.append([
                " -> ".join(pattern),
                "high-correction (struggle)",
                round(high_support / low_support, 2),
            ])
            struggle_patterns += 1

    frequent_table = []
    for pattern, support in sorted(filtered_patterns, key=lambda x: -x[1])[:50]:
        support_pct = (support / len(sequences)) * 100
        frequent_table.append([
            " -> ".join(pattern),
            len(pattern),
            support,
            round(support_pct, 2),
        ])

    result = {
        "name": "prefixspan_mining",
        "summary": f"PrefixSpan pattern mining: found {total_patterns} frequent patterns (length 3-6) from {len(sequences)} sessions",
        "findings": [
            {"label": "total_sessions", "value": len(sessions), "description": "Total sessions analyzed"},
            {"label": "sequences_with_tools", "value": len(sequences), "description": "Sessions with tool call sequences"},
            {"label": "min_support_threshold", "value": min_support, "description": "Minimum support for pattern mining"},
            {"label": "total_patterns", "value": total_patterns, "description": "Total frequent patterns found"},
            {"label": "patterns_length_3", "value": patterns_len_3, "description": "Patterns of length 3"},
            {"label": "patterns_length_4", "value": patterns_len_4, "description": "Patterns of length 4"},
            {"label": "patterns_length_5", "value": patterns_len_5, "description": "Patterns of length 5"},
            {"label": "patterns_length_6", "value": patterns_len_6, "description": "Patterns of length 6"},
            {"label": "low_correction_sessions", "value": len(low_corr_sequences), "description": "Sessions with <=10% correction rate"},
            {"label": "high_correction_sessions", "value": len(high_corr_sequences), "description": "Sessions with >25% correction rate"},
            {"label": "success_patterns", "value": success_patterns, "description": "Patterns enriched in low-correction sessions (>2x)"},
            {"label": "struggle_patterns", "value": struggle_patterns, "description": "Patterns enriched in high-correction sessions (>2x)"}
        ],
        "tables": [
            {
                "name": "Frequent Sequential Patterns",
                "columns": ["pattern", "length", "support", "support_pct"],
                "rows": frequent_table
            },
            {
                "name": "Discriminative Patterns",
                "columns": ["pattern", "group", "support_ratio"],
                "rows": discriminative_patterns
            }
        ],
        "figures": []
    }

    print(json.dumps(result))
    sys.exit(0)

if __name__ == "__main__":
    main()
