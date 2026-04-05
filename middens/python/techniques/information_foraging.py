
import sys
import json
import os
import numpy as np
import pandas as pd
from collections import defaultdict
import re
from typing import Optional

def sanitize_for_json(obj):
    if isinstance(obj, (np.integer, np.floating, np.bool_)):
        return obj.item()
    if isinstance(obj, dict):
        return {k: sanitize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [sanitize_for_json(elem) for elem in obj]
    if isinstance(obj, tuple):
        return tuple(sanitize_for_json(elem) for elem in obj)
    if isinstance(obj, float) and (np.isnan(obj) or np.isinf(obj)):
        return None
    return obj

def extract_dir_from_tool_input(tool_input) -> Optional[str]:
    # tool_input can be a dict (from serde_json::Value) or a string
    data = None
    if isinstance(tool_input, dict):
        data = tool_input
    elif isinstance(tool_input, str):
        try:
            data = json.loads(tool_input)
        except (json.JSONDecodeError, TypeError):
            # Try as raw path
            if '/' in tool_input:
                data = {'path': tool_input}

    if not data or not isinstance(data, dict):
        return None

    path = data.get('file_path') or data.get('path') or data.get('dir_path') or data.get('directory')
    if not path or not isinstance(path, str):
        return None

    try:
        path = os.path.normpath(path)
        # If it looks like a file (has extension), get the directory
        if os.path.basename(path) and '.' in os.path.basename(path):
            return os.path.dirname(path) or '.'
        return path
    except Exception:
            if os.path.basename(path) and '.' in os.path.basename(path):
                 return os.path.dirname(path)
            return path
            
    return None

def is_edit_tool(tool_name):
    return any(sub in tool_name.lower() for sub in ['edit', 'write'])

def analyze_session(session):
    patches = []
    tool_call_count = 0
    edit_tool_count = 0
    explore_calls = 0
    exploit_calls = 0
    
    assistant_messages = [m for m in session.get('messages', []) if m.get('role') == 'Assistant']

    for message in assistant_messages:
        tool_calls = message.get('tool_calls', [])
        if not tool_calls:
            patches.append(None) # A turn with no tool use
            continue
        
        turn_patches = set()
        for call in tool_calls:
            tool_call_count += 1
            tool_name = call.get('name', '').lower()
            if is_edit_tool(tool_name):
                edit_tool_count += 1
                exploit_calls += 1
            elif any(sub in tool_name for sub in ['read', 'glob', 'grep', 'websearch', 'webfetch']):
                explore_calls += 1
            else: 
                exploit_calls +=1
            
            dir_path = extract_dir_from_tool_input(call.get('input'))
            if dir_path:
                turn_patches.add(dir_path)
        
        patches.append(list(turn_patches)[0] if turn_patches else None)

    if not patches:
        return None

    patch_visits = []
    if patches[0] is not None:
        patch_visits.append({'patch': patches[0], 'duration': 1})
    
    for i in range(1, len(patches)):
        if patches[i] is None:
            continue
        # Use normpath to treat 'a/b' and 'a/b/' as the same patch
        current_patch = os.path.normpath(patches[i])
        prev_patch = os.path.normpath(patches[i-1]) if patches[i-1] else None
        
        if current_patch == prev_patch and patch_visits:
            patch_visits[-1]['duration'] += 1
        else:
            patch_visits.append({'patch': current_patch, 'duration': 1})

    if not patch_visits:
        return None

    residence_times = [v['duration'] for v in patch_visits]
    
    unique_patches = set(p['patch'] for p in patch_visits)
    total_visits = len(patch_visits)
    patch_revisit_rate = (total_visits - len(unique_patches)) / total_visits if total_visits > 0 else 0

    user_messages = [m for m in session.get('messages', []) if m.get('role') == 'User']
    num_user_turns = len(user_messages)
    num_corrections = sum(1 for m in user_messages if m.get('classification', '').startswith('Human'))
    correction_rate = num_corrections / num_user_turns if num_user_turns > 0 else 0

    return {
        'patches_explored': len(unique_patches),
        'mean_residence_time': np.mean(residence_times) if residence_times else 0,
        'foraging_efficiency': edit_tool_count / tool_call_count if tool_call_count > 0 else 0,
        'explore_exploit_ratio': explore_calls / exploit_calls if exploit_calls > 0 else 0,
        'patch_revisit_rate': patch_revisit_rate,
        'patch_visits': patch_visits,
        'correction_rate': correction_rate
    }

def main():
    if len(sys.argv) < 2:
        print(json.dumps({"name": "information_foraging", "summary": "Error: No input file path provided.", "findings": [], "tables": []}))
        sys.exit(1)

    input_path = sys.argv[1]
    try:
        with open(input_path, 'r') as f:
            sessions = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        print(f"Error: Cannot read or parse session file at {input_path}", file=sys.stderr)
        summary = f"Error: Cannot read or parse session file at {input_path}"
        print(json.dumps({"name": "information_foraging", "summary": summary, "findings": [], "tables": []}))
        sys.exit(1)

    if not sessions:
        summary = "No sessions found in the input file."
        print(json.dumps({"name": "information_foraging", "summary": summary, "findings": [], "tables": []}))
        return

    try:
        all_metrics = [analyze_session(s) for s in sessions]
        all_metrics = [m for m in all_metrics if m is not None]

        if not all_metrics:
            summary = "Could not extract any foraging data from the provided sessions."
            print(json.dumps({"name": "information_foraging", "summary": summary, "findings": [], "tables": []}))
            return

        mvt_compliance_rate = 0.0

        low_correction_sessions = [m for m in all_metrics if m['correction_rate'] is not None and m['correction_rate'] <= 0.10]
        high_correction_sessions = [m for m in all_metrics if m['correction_rate'] is not None and m['correction_rate'] > 0.25]
        
        low_corr_res_time = np.mean([m['mean_residence_time'] for m in low_correction_sessions]) if low_correction_sessions else 0
        high_corr_res_time = np.mean([m['mean_residence_time'] for m in high_correction_sessions]) if high_correction_sessions else 0

        findings = [
            {"label": "mean_patches_per_session", "value": np.mean([m['patches_explored'] for m in all_metrics])},
            {"label": "mean_residence_time", "value": np.mean([m['mean_residence_time'] for m in all_metrics])},
            {"label": "mean_foraging_efficiency", "value": np.mean([m['foraging_efficiency'] for m in all_metrics])},
            {"label": "explore_exploit_ratio", "value": np.mean([m['explore_exploit_ratio'] for m in all_metrics if m['explore_exploit_ratio'] is not None])},
            {"label": "mvt_compliance_rate", "value": mvt_compliance_rate},
            {"label": "patch_revisit_rate", "value": np.mean([m['patch_revisit_rate'] for m in all_metrics])},
            {"label": "low_correction_foraging_time", "value": low_corr_res_time},
            {"label": "high_correction_foraging_time", "value": high_corr_res_time}
        ]

        summary_table = {
            "name": "Foraging Metrics Summary",
            "columns": ["Metric", "Value"],
            "rows": [[f['label'], f['value']] for f in findings]
        }

        comparison_table = {
            "name": "Success vs Struggle Comparison",
            "columns": ["Metric", "Low Correction (<=10%)", "High Correction (>25%)"],
            "rows": [
                ["Mean Residence Time", low_corr_res_time, high_corr_res_time],
                ["Mean Foraging Efficiency", np.mean([m['foraging_efficiency'] for m in low_correction_sessions]) if low_correction_sessions else 0, np.mean([m['foraging_efficiency'] for m in high_correction_sessions]) if high_correction_sessions else 0],
                ["Mean Patches Explored", np.mean([m['patches_explored'] for m in low_correction_sessions]) if low_correction_sessions else 0, np.mean([m['patches_explored'] for m in high_correction_sessions]) if high_correction_sessions else 0],
            ]
        }

        patch_analysis = defaultdict(lambda: {'visits': 0, 'durations': []})
        for m in all_metrics:
            for v in m['patch_visits']:
                patch_analysis[v['patch']]['visits'] +=1
                patch_analysis[v['patch']]['durations'].append(v['duration'])

        patch_rows = sorted([[p, d['visits'], np.mean(d['durations'])] for p, d in patch_analysis.items()], key=lambda x: x[1], reverse=True) if patch_analysis else []
        patch_table = { "name": "Patch Analysis", "columns": ["Patch", "Total Visits", "Mean Residence Time"], "rows": patch_rows }

        result = {
            "name": "information_foraging",
            "summary": f"Information foraging analysis: analyzed foraging behavior across {len(all_metrics)} sessions.",
            "findings": findings,
            "tables": [summary_table, comparison_table, patch_table]
        }
        
        print(json.dumps(sanitize_for_json(result)))

    except Exception as e:
        summary = f"An unexpected error occurred during analysis: {e}"
        print(json.dumps({"name": "information_foraging", "summary": summary, "findings": [], "tables": []}))

if __name__ == "__main__":
    main()
