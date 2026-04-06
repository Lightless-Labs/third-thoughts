#!/usr/bin/env python3
"""lag_sequential — Batch 3 Python technique for middens."""
import json
import math
import sys
from collections import Counter, defaultdict

NAME = "lag_sequential"
MIN_SESSIONS = 3

def sanitize(obj):
    """Recursively replace NaN/Infinity with None for JSON safety."""
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    if isinstance(obj, dict):
        return {k: sanitize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [sanitize(v) for v in obj]
    return obj

def empty_result(summary):
    return {
        "name": NAME,
        "summary": summary,
        "findings": [],
        "tables": [],
        "figures": [],
    }

def code_event(message):
    """Convert a message to an event code."""
    role = message.get("role", "")
    classification = message.get("classification", "")
    thinking = message.get("thinking")
    tool_calls = message.get("tool_calls", []) or []
    tool_results = message.get("tool_results", []) or []
    
    if role == "System":
        return None
    
    if role == "User":
        if classification in ["HumanDirective", "Unclassified"]:
            return "UR"
        elif classification == "HumanCorrection":
            return "UC"
        elif classification == "HumanApproval":
            return "UA"
        elif classification == "HumanQuestion":
            return "UQ"
        else:
            return "UR"  # Default for unrecognized classifications
    
    if role == "Assistant":
        # Check for error tool results first
        has_error = any(tr.get("is_error", False) for tr in tool_results)
        if has_error:
            return "AF"
        
        # Check for thinking (wins over tool calls)
        if thinking and len(str(thinking)) > 0:
            return "AK"
        
        # Check tool calls in priority order
        tool_names = set()
        for tc in tool_calls:
            name = tc.get("name", "")
            if name:
                tool_names.add(name)
        
        if "Read" in tool_names or "Glob" in tool_names or "Grep" in tool_names:
            return "AR"
        if "Edit" in tool_names or "Write" in tool_names or "NotebookEdit" in tool_names:
            return "AE"
        if "Bash" in tool_names:
            return "AB"
        if "Skill" in tool_names:
            return "AS"
        
        # No tool calls, no thinking
        return "AT"
    
    return None

def analyze(sessions):
    """Perform lag-sequential analysis on sessions."""
    # Step 1: Code sessions into sequences
    coded_sessions = []
    skipped_sessions = 0
    
    for session in sessions:
        messages = session.get("messages", [])
        event_sequence = []
        
        for msg in messages:
            code = code_event(msg)
            if code is not None:
                event_sequence.append(code)
        
        if len(event_sequence) >= 20:
            coded_sessions.append(event_sequence)
        else:
            skipped_sessions += 1
    
    if not coded_sessions:
        return empty_result(
            "insufficient data: no sessions with at least 20 events after coding"
        )
    
    # Step 2: Build alphabet (set of all observed event codes)
    all_events = set()
    for seq in coded_sessions:
        all_events.update(seq)
    alphabet = sorted(list(all_events))
    event_to_idx = {e: i for i, e in enumerate(alphabet)}
    n_events = len(alphabet)
    
    # Step 3: For each lag, build transition matrices
    significant_counts = {}
    all_cells = []  # (lag, from_idx, to_idx, observed, expected, z_score)
    
    for lag in [1, 2, 3]:
        # Initialize count matrix
        counts = [[0] * n_events for _ in range(n_events)]
        
        # Count transitions at this lag
        for seq in coded_sessions:
            for i in range(len(seq) - lag):
                from_event = seq[i]
                to_event = seq[i + lag]
                from_idx = event_to_idx[from_event]
                to_idx = event_to_idx[to_event]
                counts[from_idx][to_idx] += 1
        
        # Compute row and column totals
        row_totals = [sum(counts[i]) for i in range(n_events)]
        col_totals = [sum(counts[i][j] for i in range(n_events)) for j in range(n_events)]
        grand_total = sum(row_totals)
        
        if grand_total == 0:
            significant_counts[lag] = 0
            continue
        
        # Compute expected counts and adjusted residuals
        sig_count = 0
        for i in range(n_events):
            for j in range(n_events):
                observed = counts[i][j]
                expected = (row_totals[i] * col_totals[j]) / grand_total if grand_total > 0 else 0
                
                # Adjusted residual calculation
                if expected > 0 and grand_total > 0:
                    denominator = math.sqrt(
                        expected * (1 - row_totals[i] / grand_total) * (1 - col_totals[j] / grand_total)
                    )
                    if denominator > 0 and math.isfinite(denominator):
                        z = (observed - expected) / denominator
                    else:
                        z = 0.0
                else:
                    z = 0.0
                
                if math.isnan(z) or math.isinf(z):
                    z = 0.0
                
                # Track significant cells
                if abs(z) >= 2.58:
                    sig_count += 1
                
                all_cells.append((lag, i, j, observed, expected, z))
        
        significant_counts[lag] = sig_count
    
    # Step 4: Collect top 20 positive and top 10 negative cells
    # Filter out cells with z=0 to avoid noise
    non_zero_cells = [c for c in all_cells if abs(c[5]) > 0.0001]
    
    sorted_by_z = sorted(non_zero_cells, key=lambda x: x[5], reverse=True)
    top_positive = sorted_by_z[:20]
    top_negative = sorted(sorted_by_z, key=lambda x: x[5])[:10]
    
    # Step 5: Compute event frequencies
    event_counter = Counter()
    total_events = 0
    for seq in coded_sessions:
        event_counter.update(seq)
        total_events += len(seq)
    
    event_freq_data = []
    for event in alphabet:
        count = event_counter[event]
        proportion = count / total_events if total_events > 0 else 0.0
        event_freq_data.append((event, count, proportion))
    
    event_freq_data.sort(key=lambda x: x[1], reverse=True)
    
    # Prepare findings
    total_significant = sum(significant_counts.values())
    
    # Top positive transition string
    if top_positive:
        cell = top_positive[0]
        from_code = alphabet[cell[1]]
        to_code = alphabet[cell[2]]
        lag = cell[0]
        z = cell[5]
        top_pos_str = f"{from_code}→{to_code} (lag={lag}, z={z:.1f})"
    else:
        top_pos_str = "none"
    
    # Top negative transition string
    if top_negative:
        cell = top_negative[0]
        from_code = alphabet[cell[1]]
        to_code = alphabet[cell[2]]
        lag = cell[0]
        z = cell[5]
        top_neg_str = f"{from_code}→{to_code} (lag={lag}, z={z:.1f})"
    else:
        top_neg_str = "none"
    
    findings = [
        {"label": "total_events", "value": total_events},
        {"label": "sessions_analyzed", "value": len(coded_sessions)},
        {"label": "significant_transitions_lag1", "value": significant_counts.get(1, 0)},
        {"label": "significant_transitions_lag2", "value": significant_counts.get(2, 0)},
        {"label": "significant_transitions_lag3", "value": significant_counts.get(3, 0)},
        {"label": "top_positive_transition", "value": top_pos_str},
        {"label": "top_negative_transition", "value": top_neg_str},
    ]
    
    # Prepare tables
    # Top Positive Transitions
    pos_table_rows = []
    for cell in top_positive:
        lag, from_idx, to_idx, observed, expected, z = cell
        pos_table_rows.append([
            alphabet[from_idx],
            alphabet[to_idx],
            lag,
            observed,
            round(expected, 2),
            round(z, 2)
        ])
    
    # Top Negative Transitions
    neg_table_rows = []
    for cell in top_negative:
        lag, from_idx, to_idx, observed, expected, z = cell
        neg_table_rows.append([
            alphabet[from_idx],
            alphabet[to_idx],
            lag,
            observed,
            round(expected, 2),
            round(z, 2)
        ])
    
    # Event Frequencies
    freq_table_rows = []
    for event, count, proportion in event_freq_data:
        freq_table_rows.append([event, count, round(proportion, 4)])
    
    tables = [
        {
            "name": "Top Positive Transitions",
            "columns": ["from", "to", "lag", "observed", "expected", "z_score"],
            "rows": pos_table_rows
        },
        {
            "name": "Top Negative Transitions",
            "columns": ["from", "to", "lag", "observed", "expected", "z_score"],
            "rows": neg_table_rows
        },
        {
            "name": "Event Frequencies",
            "columns": ["event", "count", "proportion"],
            "rows": freq_table_rows
        }
    ]
    
    # Summary
    summary = (
        f"Lag-sequential (lag sequential) analysis of {len(coded_sessions)} sessions ({total_events} events) "
        f"found {total_significant} significant transitions (|z|≥2.58) across lags 1-3. "
        f"Top forward association: {top_pos_str}."
    )
    
    return {
        "name": NAME,
        "summary": summary,
        "findings": findings,
        "tables": tables,
        "figures": []
    }

def main():
    if len(sys.argv) < 2:
        print("usage: lag_sequential.py <sessions.json>", file=sys.stderr)
        sys.exit(1)
    try:
        with open(sys.argv[1]) as f:
            sessions = json.load(f)
    except Exception as e:
        print(f"Failed to read sessions: {e}", file=sys.stderr)
        sys.exit(1)

    if not sessions:
        print(json.dumps(empty_result("No sessions to analyze")))
        return

    if len(sessions) < MIN_SESSIONS:
        print(json.dumps(empty_result(
            f"insufficient data: need at least {MIN_SESSIONS} sessions, got {len(sessions)}"
        )))
        return

    # --- technique-specific analysis ---
    result = analyze(sessions)
    print(json.dumps(sanitize(result), default=str))

if __name__ == "__main__":
    main()
