#!/usr/bin/env python3
"""Change point detection using ruptures PELT on 4 per-user-message signals."""

import json
import math
import re
import sys
from typing import Any

import numpy as np
import ruptures as rpt


def _sanitize(obj: Any) -> Any:
    """Sanitize NaN/Infinity to None for JSON serialization."""
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize(v) for v in obj]
    return obj


def strip_patterns(text: str) -> str:
    """Strip system-reminder, command-name tags and [Request interrupted]."""
    # Remove <system-reminder>...</system-reminder>
    text = re.sub(r'<system-reminder>.*?</system-reminder>', '', text, flags=re.DOTALL)
    # Remove <command-name>...</command-name>
    text = re.sub(r'<command-name>.*?</command-name>', '', text, flags=re.DOTALL)
    # Remove [Request interrupted]
    text = text.replace('[Request interrupted]', '')
    return text


def build_signals(messages: list) -> tuple[dict, int]:
    """Build 4 time series from session messages."""
    signals = {
        'user_msg_length': [],
        'tool_call_rate': [],
        'correction_flag': [],
        'tool_diversity': []
    }
    
    preceding_assistant_tool_calls = None
    
    for msg in messages:
        role = msg.get('role')
        
        if role == 'Assistant':
            tool_calls = msg.get('tool_calls') or []
            preceding_assistant_tool_calls = tool_calls
        elif role == 'User':
            # user_msg_length: length of text after stripping
            text = msg.get('text', '')
            cleaned_text = strip_patterns(text)
            signals['user_msg_length'].append(len(cleaned_text))
            
            # tool_call_rate: number of tool calls in preceding assistant
            if preceding_assistant_tool_calls is not None:
                signals['tool_call_rate'].append(len(preceding_assistant_tool_calls))
            else:
                signals['tool_call_rate'].append(0)
            
            # correction_flag: 1 if HumanCorrection
            classification = msg.get('classification')
            signals['correction_flag'].append(1 if classification == 'HumanCorrection' else 0)
            
            # tool_diversity: distinct tool names in preceding assistant
            if preceding_assistant_tool_calls is not None:
                tool_names = set()
                for tc in preceding_assistant_tool_calls:
                    if isinstance(tc, dict):
                        name = tc.get('name')
                        if name:
                            tool_names.add(name)
                signals['tool_diversity'].append(len(tool_names))
            else:
                signals['tool_diversity'].append(0)

            # Consume the cached assistant context so back-to-back user
            # turns do not inherit stale tool counts/diversity from a
            # much earlier assistant turn.
            preceding_assistant_tool_calls = None

    return signals, len(signals['user_msg_length'])


def detect_change_points(signal_name: str, values: list, original_values: list) -> tuple[list, list]:
    """Detect change points using PELT with Binseg fallback."""
    x = np.array(values, dtype=float)
    original_x = np.array(original_values, dtype=float)
    
    # Skip if fewer than 10 non-zero values
    non_zero_count = np.count_nonzero(x)
    if non_zero_count < 10:
        return [], []
    
    # Normalize
    mean_val = np.mean(x)
    std_val = np.std(x)
    if std_val < 1e-10:
        return [], []
    
    z = (x - mean_val) / std_val
    
    # Subsample if needed
    factor = 1
    working = z
    if len(z) > 500:
        factor = math.ceil(len(z) / 500)
        working = z[::factor]
    
    # Apply ruptures
    try:
        algo = rpt.Pelt(model="rbf", min_size=8).fit(working.reshape(-1, 1))
        change_points = algo.predict(pen=1.5 * math.log(len(working)))
    except Exception:
        try:
            algo = rpt.Binseg(model="rbf", min_size=8).fit(working.reshape(-1, 1))
            change_points = algo.predict(pen=1.5 * math.log(len(working)))
        except Exception:
            return [], []
    
    # Strip final endpoint and map back to original scale
    if change_points:
        change_points = change_points[:-1]  # Remove final endpoint
    
    original_indices = [int(cp * factor) for cp in change_points]
    
    return original_indices, list(original_x)


def classify_regimes(change_points: list, original_values: list) -> list:
    """Classify regimes between change points."""
    if not original_values:
        return []
    
    # Add start and end boundaries
    boundaries = [0] + sorted(change_points) + [len(original_values)]
    
    regimes = []
    for i in range(len(boundaries) - 1):
        start_idx = boundaries[i]
        end_idx = boundaries[i + 1]
        
        # Get slice values
        slice_values = original_values[start_idx:end_idx]
        mean_value = np.mean(slice_values) if slice_values else 0.0
        
        # Determine classification
        if i == 0:
            classification = 'flat'
        else:
            prev_mean = regimes[i - 1]['mean_value']
            std_val = np.std(original_values) if len(original_values) > 1 else 0.0
            
            if mean_value > prev_mean + 0.1 * std_val:
                classification = 'ascending'
            elif mean_value < prev_mean - 0.1 * std_val:
                classification = 'descending'
            else:
                classification = 'flat'
        
        regimes.append({
            'start_index': start_idx,
            'end_index': end_idx - 1,  # inclusive
            'mean_value': float(mean_value),
            'classification': classification
        })
    
    return regimes


def main():
    if len(sys.argv) < 2:
        print("Error: No input file provided", file=sys.stderr)
        sys.exit(1)
    
    input_path = sys.argv[1]
    
    try:
        with open(input_path, 'r') as f:
            sessions = json.load(f)
    except FileNotFoundError:
        print(f"Error: File not found: {input_path}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON: {e}", file=sys.stderr)
        sys.exit(1)
    
    if not isinstance(sessions, list):
        print("Error: Expected JSON array of sessions", file=sys.stderr)
        sys.exit(1)
    
    # Filter sessions with at least 30 messages
    valid_sessions = []
    sessions_skipped_short = 0
    
    for session in sessions:
        messages = session.get('messages', [])
        if len(messages) >= 30:
            valid_sessions.append(session)
        else:
            sessions_skipped_short += 1
    
    sessions_analyzed = len(valid_sessions)
    
    # Initialize counters
    signal_names = ['user_msg_length', 'tool_call_rate', 'correction_flag', 'tool_diversity']
    total_cps_per_signal = {name: 0 for name in signal_names}
    sessions_with_cp_per_signal = {name: 0 for name in signal_names}
    
    # Track all change points and regimes
    all_change_points = []
    all_regimes = []
    session_cp_counts = {}
    
    # Process each session
    for session in valid_sessions:
        session_id = session.get('id', '')
        messages = session.get('messages', [])
        
        signals, _ = build_signals(messages)
        session_total_cps = 0
        
        for signal_name in signal_names:
            values = signals[signal_name]
            
            # Skip if too few non-zero values
            non_zero_count = sum(1 for v in values if v != 0)
            if non_zero_count < 10:
                continue
            
            # Detect change points
            cp_indices, original_values = detect_change_points(signal_name, values, values)
            
            if cp_indices:
                sessions_with_cp_per_signal[signal_name] += 1
                total_cps_per_signal[signal_name] += len(cp_indices)
                session_total_cps += len(cp_indices)
                
                # Get regimes for classification
                regimes = classify_regimes(cp_indices, original_values)
                
                # Add change points to table
                for i, cp_idx in enumerate(cp_indices):
                    # Find regimes before and after
                    regime_before = 'flat'
                    regime_after = 'flat'
                    
                    for j, reg in enumerate(regimes):
                        if reg['start_index'] <= cp_idx <= reg['end_index']:
                            if j > 0:
                                regime_before = regimes[j - 1]['classification']
                            regime_after = reg['classification']
                            break
                    
                    all_change_points.append({
                        'session_id': session_id,
                        'signal': signal_name,
                        'index': cp_idx,
                        'regime_before': regime_before,
                        'regime_after': regime_after
                    })
                
                # Add regimes to table
                for i, reg in enumerate(regimes):
                    all_regimes.append({
                        'session_id': session_id,
                        'signal': signal_name,
                        'regime_num': i + 1,
                        'start_index': reg['start_index'],
                        'end_index': reg['end_index'],
                        'mean_value': reg['mean_value'],
                        'classification': reg['classification']
                    })
        
        session_cp_counts[session_id] = session_total_cps
    
    # Find most volatile session
    most_volatile_session_id = ''
    if session_cp_counts:
        max_cps = max(session_cp_counts.values())
        if max_cps > 0:
            # Sort by session id alphabetically for ties
            candidates = sorted([sid for sid, count in session_cp_counts.items() if count == max_cps])
            most_volatile_session_id = candidates[0]
    
    # Calculate totals
    total_change_points = sum(total_cps_per_signal.values())
    mean_change_points_per_session = total_change_points / sessions_analyzed if sessions_analyzed > 0 else 0.0
    
    # Build summary
    if sessions_analyzed < 3:
        summary = f"insufficient sessions for change point detection via ruptures PELT: need at least 3 sessions with >=30 messages (analyzed {sessions_analyzed})"
    else:
        summary = f"change point analysis via ruptures PELT on {sessions_analyzed} sessions, {total_change_points} total change points detected"
    
    # Build findings
    findings = [
        {"label": "sessions_analyzed", "value": sessions_analyzed, "description": None},
        {"label": "total_change_points", "value": total_change_points, "description": None},
        {"label": "change_points_user_msg_length", "value": total_cps_per_signal['user_msg_length'], "description": None},
        {"label": "change_points_tool_call_rate", "value": total_cps_per_signal['tool_call_rate'], "description": None},
        {"label": "change_points_correction_flag", "value": total_cps_per_signal['correction_flag'], "description": None},
        {"label": "change_points_tool_diversity", "value": total_cps_per_signal['tool_diversity'], "description": None},
        {"label": "mean_change_points_per_session", "value": mean_change_points_per_session, "description": None},
        {"label": "most_volatile_session_id", "value": most_volatile_session_id, "description": None}
    ]
    
    # Build tables
    # Sort and cap change points table
    all_change_points.sort(key=lambda x: (x['session_id'], x['signal'], x['index']))
    change_points_table_rows = [
        [cp['session_id'], cp['signal'], cp['index'], cp['regime_before'], cp['regime_after']]
        for cp in all_change_points[:500]
    ]
    
    # Sort and cap regimes table
    all_regimes.sort(key=lambda x: (x['session_id'], x['signal'], x['regime_num']))
    regimes_table_rows = [
        [r['session_id'], r['signal'], r['regime_num'], r['start_index'], r['end_index'], r['mean_value'], r['classification']]
        for r in all_regimes[:1000]
    ]
    
    # Signal summary table. mean_cps_per_session divides by the full analyzed
    # cohort so it is comparable to the top-level `mean_change_points_per_session`
    # finding; dividing by sessions_with_cp would inflate values whenever some
    # sessions had zero change points on that signal.
    signal_summary_rows = []
    for signal_name in signal_names:
        total_cps = total_cps_per_signal[signal_name]
        sessions_with = sessions_with_cp_per_signal[signal_name]
        mean_cps = total_cps / sessions_analyzed if sessions_analyzed > 0 else 0.0
        signal_summary_rows.append([signal_name, sessions_with, total_cps, mean_cps])
    
    tables = [
        {
            "name": "Change Points",
            "columns": ["session_id", "signal", "index", "regime_before", "regime_after"],
            "rows": change_points_table_rows
        },
        {
            "name": "Regimes",
            "columns": ["session_id", "signal", "regime_num", "start_index", "end_index", "mean_value", "classification"],
            "rows": regimes_table_rows
        },
        {
            "name": "Signal Summary",
            "columns": ["signal", "sessions_with_cp", "total_cps", "mean_cps_per_session"],
            "rows": signal_summary_rows
        }
    ]
    
    # Build result
    result = {
        "name": "change-point-detection",
        "summary": summary,
        "findings": _sanitize(findings),
        "tables": _sanitize(tables),
        "figures": []
    }
    
    print(json.dumps(result, indent=2))
    sys.exit(0)


if __name__ == '__main__':
    main()
