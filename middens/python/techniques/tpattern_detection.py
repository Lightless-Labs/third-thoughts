import sys
import json
import numpy as np
from collections import Counter
from typing import List, Dict, Tuple, Any, Optional

# Event encoding codes
CODE_MAP = {
    'UR': 'UR',  # User Request
    'UC': 'UC',  # User Correction
    'UA': 'UA',  # User Approval
    'AR': 'AR',  # Agent Read (Read/Glob/Grep)
    'AE': 'AE',  # Agent Edit (Edit/Write)
    'AB': 'AB',  # Agent Bash
    'AT': 'AT',  # Agent Text (no tools)
    'AK': 'AK',  # Agent Thinking (has thinking block)
    'AF': 'AF',  # Agent Failure (tool_result is_error=true)
}


def encode_session(session: Dict) -> List[str]:
    """Encode a session's messages into event codes."""
    events = []
    messages = session.get('messages', [])
    
    for msg in messages:
        role = msg.get('role', '')
        classification = msg.get('classification', 'Unclassified')
        
        if role == 'User':
            if classification == 'HumanCorrection':
                events.append('UC')
            elif classification == 'HumanApproval':
                events.append('UA')
            elif classification == 'HumanDirective':
                events.append('UR')
            else:
                events.append('UR')  # Default user request
                
        elif role == 'Assistant':
            tool_calls = msg.get('tool_calls', [])
            thinking = msg.get('thinking')
            
            # Check for failures in tool_results
            tool_results = msg.get('tool_results', [])
            has_failure = any(
                tr.get('is_error', False) or tr.get('error') is not None
                for tr in tool_results
            )
            
            if has_failure:
                events.append('AF')
                continue
            
            # Check for thinking block
            if thinking:
                events.append('AK')
                continue
            
            # Categorize tool calls
            if not tool_calls:
                events.append('AT')  # Text-only response
            else:
                for tc in tool_calls:
                    tool_name = tc.get('tool', '') if isinstance(tc, dict) else tc
                    if isinstance(tool_name, dict):
                        tool_name = tool_name.get('tool', '')
                    
                    tool_name_str = str(tool_name).lower()
                    
                    if tool_name_str in ['read', 'glob', 'grep']:
                        events.append('AR')
                    elif tool_name_str in ['edit', 'write']:
                        events.append('AE')
                    elif tool_name_str == 'bash':
                        events.append('AB')
                    else:
                        events.append('AT')
    
    return events


def count_pair_transitions(events: List[str], window_size: int = 5) -> Counter:
    """Count transitions from event A to event B within a window."""
    transitions = Counter()
    
    for i, event_a in enumerate(events):
        # Look at next events within window
        for j in range(i + 1, min(i + window_size + 1, len(events))):
            event_b = events[j]
            transitions[(event_a, event_b)] += 1
    
    return transitions


def permutation_test(events: List[str], observed: Counter, n_permutations: int = 100, window_size: int = 5) -> Dict[Tuple[str, str], Tuple[int, float, float, float]]:
    """
    Perform permutation test to find significant patterns.
    Returns dict mapping (A, B) to (observed_count, expected_mean, expected_std, z_score)
    """
    if not events:
        return {}
    
    # Get unique event codes present in the data
    unique_codes = list(set(events))
    
    # Generate permutation distribution for each pair
    permutation_counts = {pair: [] for pair in observed.keys()}
    
    events_array = np.array(events)
    
    for _ in range(n_permutations):
        # Shuffle events
        shuffled = events_array.copy()
        np.random.shuffle(shuffled)
        shuffled = shuffled.tolist()
        
        # Count transitions in shuffled sequence
        shuffled_transitions = count_pair_transitions(shuffled, window_size)
        
        for pair in observed.keys():
            permutation_counts[pair].append(shuffled_transitions.get(pair, 0))
    
    # Calculate statistics
    results = {}
    for pair, obs_count in observed.items():
        perm_counts = permutation_counts[pair]
        mean_count = np.mean(perm_counts)
        std_count = np.std(perm_counts) if len(perm_counts) > 1 else 0.0
        
        # Avoid division by zero
        if std_count > 0:
            z_score = (obs_count - mean_count) / std_count
        else:
            z_score = 0.0 if obs_count == mean_count else float('inf') if obs_count > mean_count else float('-inf')
        
        results[pair] = (obs_count, mean_count, std_count, z_score)
    
    return results


def find_significant_patterns(events: List[str], window_size: int = 5, n_permutations: int = 100, threshold: float = 2.5) -> List[Tuple[Tuple[str, str], int, float, float, float]]:
    """
    Find significant level-1 patterns using permutation test.
    Returns list of (pair, observed, expected_mean, expected_std, z_score)
    """
    if len(events) < 2:
        return []
    
    observed = count_pair_transitions(events, window_size)
    stats = permutation_test(events, observed, n_permutations, window_size)
    
    significant = []
    for pair, (obs, mean, std, z) in stats.items():
        # Significant if observed > mean + threshold * std (and observed > 0)
        if obs > 0 and obs > mean + threshold * std:
            significant.append((pair, obs, mean, std, z))
    
    # Sort by z-score descending
    significant.sort(key=lambda x: x[4], reverse=True)
    
    return significant


def build_hierarchical_patterns(level1_patterns: List[Tuple[Tuple[str, str], int, float, float, float]], events: List[str], window_size: int = 5) -> List[Tuple[Tuple[str, str, str], int, float]]:
    """
    Build level-2 patterns: if (A,B) and (B,C) are significant, report (A,B,C).
    Returns list of (triple, observed_count, z_score)
    """
    if len(events) < 3:
        return []
    
    # Create set of significant pairs for quick lookup
    significant_pairs = set(pair for pair, _, _, _, _ in level1_patterns)
    pair_z_scores = {pair: z for pair, _, _, _, z in level1_patterns}
    
    # Find potential level-2 patterns
    level2_candidates = []
    for (a, b), _, _, _, z1 in level1_patterns:
        for (b2, c), _, _, _, z2 in level1_patterns:
            if b == b2:
                # Found A->B->C chain
                level2_candidates.append(((a, b, c), min(z1, z2)))  # Use minimum z-score
    
    # Count actual occurrences of triples in data
    triple_counts = Counter()
    for i in range(len(events) - 2):
        a, b, c = events[i], events[i + 1], events[i + 2]
        if (a, b) in significant_pairs and (b, c) in significant_pairs:
            # Check if they're within reasonable distance
            triple_counts[(a, b, c)] += 1
    
    # Build results
    level2_patterns = []
    seen = set()
    for (triple, min_z) in level2_candidates:
        if triple not in seen and triple in triple_counts:
            seen.add(triple)
            count = triple_counts[triple]
            level2_patterns.append((triple, count, min_z))
    
    # Sort by count descending
    level2_patterns.sort(key=lambda x: x[1], reverse=True)
    
    return level2_patterns


def sanitize_for_json(obj):
    """Sanitize numpy types for JSON serialization."""
    if isinstance(obj, (np.integer, np.floating, np.bool_)):
        return obj.item()
    if isinstance(obj, dict):
        return {k: sanitize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [sanitize_for_json(elem) for elem in obj]
    if isinstance(obj, tuple):
        return [sanitize_for_json(elem) for elem in obj]
    if isinstance(obj, float) and (np.isnan(obj) or np.isinf(obj)):
        return None
    return obj


def main():
    if len(sys.argv) < 2:
        error_msg = "Usage: python tpattern_detection.py <input_json_path>"
        print(error_msg, file=sys.stderr)
        result = {
            "name": "tpattern_detection",
            "summary": "Error: No input file path provided.",
            "findings": [],
            "tables": [],
            "figures": []
        }
        print(json.dumps(result))
        sys.exit(1)

    input_path = sys.argv[1]
    
    try:
        with open(input_path, 'r') as f:
            sessions = json.load(f)
    except FileNotFoundError:
        error_msg = f"Error: Input file not found: {input_path}"
        print(error_msg, file=sys.stderr)
        result = {
            "name": "tpattern_detection",
            "summary": error_msg,
            "findings": [],
            "tables": [],
            "figures": []
        }
        print(json.dumps(result))
        sys.exit(1)
    except json.JSONDecodeError as e:
        error_msg = f"Error: Invalid JSON in input file: {e}"
        print(error_msg, file=sys.stderr)
        result = {
            "name": "tpattern_detection",
            "summary": error_msg,
            "findings": [],
            "tables": [],
            "figures": []
        }
        print(json.dumps(result))
        sys.exit(1)

    # Check for empty sessions
    if not sessions:
        result = {
            "name": "tpattern_detection",
            "summary": "No sessions provided. Analysis requires at least 3 sessions.",
            "findings": [],
            "tables": [],
            "figures": []
        }
        print(json.dumps(result))
        sys.exit(0)

    # Check minimum sessions
    if len(sessions) < 3:
        result = {
            "name": "tpattern_detection",
            "summary": f"Insufficient data: at least 3 sessions are required, found {len(sessions)}.",
            "findings": [
                {"label": "level_1_patterns", "value": 0},
                {"label": "level_2_patterns", "value": 0},
                {"label": "most_common_pattern", "value": "N/A"},
                {"label": "total_events_analyzed", "value": 0}
            ],
            "tables": [],
            "figures": []
        }
        print(json.dumps(result))
        sys.exit(0)

    # Encode all sessions into event sequences
    all_events = []
    session_event_counts = []
    
    for session in sessions:
        events = encode_session(session)
        all_events.extend(events)
        session_event_counts.append(len(events))

    # Check if we have enough events
    if len(all_events) < 10:
        result = {
            "name": "tpattern_detection",
            "summary": f"Insufficient events: at least 10 events are required, found {len(all_events)}.",
            "findings": [
                {"label": "level_1_patterns", "value": 0},
                {"label": "level_2_patterns", "value": 0},
                {"label": "most_common_pattern", "value": "N/A"},
                {"label": "total_events_analyzed", "value": len(all_events)}
            ],
            "tables": [],
            "figures": []
        }
        print(json.dumps(result))
        sys.exit(0)

    # Find significant level-1 patterns
    level1_patterns = find_significant_patterns(all_events, window_size=5, n_permutations=100, threshold=2.5)

    # Build level-2 patterns
    level2_patterns = build_hierarchical_patterns(level1_patterns, all_events, window_size=5)

    # Prepare findings
    most_common = "N/A"
    if level1_patterns:
        most_common_pair = level1_patterns[0][0]
        most_common = f"{most_common_pair[0]}->{most_common_pair[1]}"

    findings = [
        {"label": "level_1_patterns", "value": len(level1_patterns)},
        {"label": "level_2_patterns", "value": len(level2_patterns)},
        {"label": "most_common_pattern", "value": most_common},
        {"label": "total_events_analyzed", "value": len(all_events)}
    ]

    # Prepare tables
    level1_rows = []
    for (a, b), obs, mean, std, z in level1_patterns:
        level1_rows.append([f"{a}->{b}", int(obs), round(float(mean), 2), round(float(z), 2)])
    
    level1_table = {
        "name": "T-Patterns Level 1",
        "columns": ["pattern", "observed_count", "expected_count", "z_score"],
        "rows": level1_rows
    }

    level2_rows = []
    for (a, b, c), count, z in level2_patterns:
        level2_rows.append([f"{a}->{b}->{c}", int(count), round(float(z), 2)])
    
    level2_table = {
        "name": "T-Patterns Level 2",
        "columns": ["pattern", "observed_count", "z_score"],
        "rows": level2_rows
    }

    summary = (
        f"Detected {len(level1_patterns)} significant level-1 patterns and "
        f"{len(level2_patterns)} level-2 patterns from {len(all_events)} events "
        f"across {len(sessions)} sessions."
    )

    result = {
        "name": "tpattern_detection",
        "summary": summary,
        "findings": findings,
        "tables": [level1_table, level2_table],
        "figures": []
    }

    print(json.dumps(sanitize_for_json(result)))


if __name__ == "__main__":
    main()
