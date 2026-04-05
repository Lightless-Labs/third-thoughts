import sys
import json
import os
from typing import List, Dict, Any, Optional
from collections import defaultdict

def classify_message(msg: Dict[str, Any]) -> str:
    """Classify a message into an activity type."""
    classification = msg.get("classification", "Unclassified")
    
    if classification == "HumanCorrection":
        return "user_correction"
    elif classification == "HumanDirective":
        return "user_request"
    elif classification == "HumanApproval":
        return "user_approval"
    elif classification == "HumanQuestion":
        return "user_question"
    elif classification == "SystemMessage":
        return "system_message"
    elif classification == "Other":
        return "other"
    elif classification == "Unclassified":
        return "unclassified"
    else:
        return "other"

def extract_tool_activities(msg: Dict[str, Any]) -> List[str]:
    """Extract tool-based activities from a message."""
    activities = []
    tool_calls = msg.get("tool_calls", [])
    
    for tool_call in tool_calls:
        tool_name = tool_call.get("tool", "").lower()
        
        if tool_name in ["read", "glob", "grep"]:
            activities.append("search_code")
        elif tool_name in ["edit", "write"]:
            activities.append("edit_file")
        elif tool_name in ["bash", "skill"]:
            activities.append("run_command")
        elif tool_name:
            activities.append("other_tool")
    
    return activities

def session_to_events(session: Dict[str, Any]) -> List[str]:
    """Convert a session to a sequence of event activities."""
    events = []
    messages = session.get("messages", [])
    
    for msg in messages:
        # Get the base activity from classification
        base_activity = classify_message(msg)
        
        # Extract tool activities
        tool_activities = extract_tool_activities(msg)
        
        if tool_activities:
            # Add tool activities
            events.extend(tool_activities)
        elif base_activity in ["user_request", "user_correction", "user_approval", 
                               "user_question", "system_message", "other", "unclassified"]:
            # For messages without tools, add the base activity
            # Skip assistant_text for now, but we could add it if needed
            if msg.get("role") == "assistant" and not tool_activities:
                events.append("assistant_text")
            else:
                events.append(base_activity)
        else:
            # Default to assistant_text for assistant messages without tools
            if msg.get("role") == "assistant":
                events.append("assistant_text")
            else:
                events.append(base_activity)
    
    return events

def build_dfg(event_logs: List[List[str]]) -> Dict[str, Dict[str, int]]:
    """Build a Directly-Follows Graph from event logs."""
    dfg = defaultdict(lambda: defaultdict(int))
    
    for log in event_logs:
        for i in range(len(log) - 1):
            current = log[i]
            next_activity = log[i + 1]
            dfg[current][next_activity] += 1
    
    return dict(dfg)

def calculate_activity_stats(event_logs: List[List[str]]) -> Dict[str, Any]:
    """Calculate statistics for each activity type."""
    activity_counts = defaultdict(int)
    activity_session_coverage = defaultdict(set)
    activity_dwell_times = defaultdict(list)
    
    for session_idx, log in enumerate(event_logs):
        current_run = []
        
        for i, activity in enumerate(log):
            activity_counts[activity] += 1
            activity_session_coverage[activity].add(session_idx)
            
            # Track consecutive same-activity runs
            if i == 0:
                current_run = [activity]
            elif activity == current_run[0]:
                current_run.append(activity)
            else:
                # Record dwell time for previous run
                if len(current_run) > 0:
                    activity_dwell_times[current_run[0]].append(len(current_run))
                current_run = [activity]
        
        # Don't forget the last run
        if current_run:
            activity_dwell_times[current_run[0]].append(len(current_run))
    
    # Calculate means
    activity_means = {}
    for activity, dwells in activity_dwell_times.items():
        activity_means[activity] = sum(dwells) / len(dwells) if dwells else 0.0
    
    # Calculate session coverage percentages
    total_sessions = len(event_logs)
    coverage_percentages = {}
    for activity, sessions in activity_session_coverage.items():
        coverage_percentages[activity] = (len(sessions) / total_sessions * 100) if total_sessions > 0 else 0.0
    
    return {
        "counts": dict(activity_counts),
        "coverage": coverage_percentages,
        "mean_dwell_time": activity_means
    }

def find_rework_loops(dfg: Dict[str, Dict[str, int]]) -> List[Dict[str, Any]]:
    """Find self-loops (rework) in the DFG."""
    rework = []
    for activity, transitions in dfg.items():
        if activity in transitions and transitions[activity] > 0:
            rework.append({
                "activity": activity,
                "count": transitions[activity]
            })
    
    # Sort by count descending
    rework.sort(key=lambda x: x["count"], reverse=True)
    return rework

def find_correction_predecessors(dfg: Dict[str, Dict[str, int]]) -> List[Dict[str, Any]]:
    """Find activities that most often precede user_correction."""
    predecessors = []
    
    for activity, transitions in dfg.items():
        if "user_correction" in transitions:
            predecessors.append({
                "activity": activity,
                "count": transitions["user_correction"]
            })
    
    # Sort by count descending
    predecessors.sort(key=lambda x: x["count"], reverse=True)
    return predecessors

def calculate_correction_rate(event_log: List[str]) -> float:
    """Calculate the correction rate for a session."""
    if not event_log:
        return 0.0
    
    correction_count = event_log.count("user_correction")
    return (correction_count / len(event_log)) * 100

def compare_correction_groups(event_logs: List[List[str]]) -> Dict[str, Any]:
    """Compare low-correction vs high-correction sessions."""
    low_correction = []
    high_correction = []
    
    for log in event_logs:
        rate = calculate_correction_rate(log)
        if rate <= 10.0:
            low_correction.append(log)
        elif rate > 25.0:
            high_correction.append(log)
    
    return {
        "low_correction_count": len(low_correction),
        "high_correction_count": len(high_correction),
        "low_correction_dfg": build_dfg(low_correction),
        "high_correction_dfg": build_dfg(high_correction)
    }

def main():
    if len(sys.argv) < 2:
        error_result = {
            "name": "process_mining",
            "summary": "Error: No input file provided",
            "findings": [],
            "tables": []
        }
        print("Error: No input file provided", file=sys.stderr)
        print(json.dumps(error_result))
        sys.exit(1)

    input_path = sys.argv[1]
    
    if not os.path.exists(input_path):
        error_result = {
            "name": "process_mining",
            "summary": f"Error: Input file not found: {input_path}",
            "findings": [],
            "tables": []
        }
        print(f"Error: Input file not found: {input_path}", file=sys.stderr)
        print(json.dumps(error_result))
        sys.exit(1)

    try:
        with open(input_path, 'r') as f:
            sessions = json.load(f)
    except json.JSONDecodeError as e:
        error_result = {
            "name": "process_mining",
            "summary": f"Error: Invalid JSON in input file: {e}",
            "findings": [],
            "tables": []
        }
        print(f"Error: Invalid JSON in input file: {e}", file=sys.stderr)
        print(json.dumps(error_result))
        sys.exit(1)
    except Exception as e:
        error_result = {
            "name": "process_mining",
            "summary": f"Error reading file: {e}",
            "findings": [],
            "tables": []
        }
        print(f"Error reading file: {e}", file=sys.stderr)
        print(json.dumps(error_result))
        sys.exit(1)

    # Check minimum sessions requirement
    if len(sessions) < 3:
        result = {
            "name": "process_mining",
            "summary": f"Insufficient data: only {len(sessions)} session(s) provided, minimum 3 required",
            "findings": [],
            "tables": []
        }
        print(json.dumps(result))
        sys.exit(0)

    # Convert sessions to event logs
    event_logs = []
    for session in sessions:
        events = session_to_events(session)
        if events:  # Only add non-empty logs
            event_logs.append(events)

    if not event_logs:
        result = {
            "name": "process_mining",
            "summary": "No valid events extracted from sessions",
            "findings": [],
            "tables": []
        }
        print(json.dumps(result))
        sys.exit(0)

    # Build DFG
    dfg = build_dfg(event_logs)

    # Calculate activity stats
    stats = calculate_activity_stats(event_logs)

    # Find rework loops
    rework_loops = find_rework_loops(dfg)

    # Find correction predecessors
    correction_predecessors = find_correction_predecessors(dfg)

    # Compare correction groups
    correction_comparison = compare_correction_groups(event_logs)

    # Calculate total events
    total_events = sum(len(log) for log in event_logs)

    # Calculate unique activities
    all_activities = set()
    for log in event_logs:
        all_activities.update(log)
    unique_activities = len(all_activities)

    # Find most common activity
    most_common_activity = "N/A"
    if stats["counts"]:
        most_common_activity = max(stats["counts"].items(), key=lambda x: x[1])[0]

    # Find top rework activity
    top_rework_activity = "N/A"
    if rework_loops:
        top_rework_activity = rework_loops[0]["activity"]

    # Find top correction predecessor
    top_correction_predecessor = "N/A"
    if correction_predecessors:
        top_correction_predecessor = correction_predecessors[0]["activity"]

    # Count DFG edges
    dfg_edges = sum(len(transitions) for transitions in dfg.values())

    # Build Activity Frequencies table
    activity_freq_rows = []
    for activity in sorted(stats["counts"].keys()):
        activity_freq_rows.append([
            activity,
            stats["counts"][activity],
            round(stats["coverage"].get(activity, 0.0), 2),
            round(stats["mean_dwell_time"].get(activity, 0.0), 2)
        ])

    # Build DFG table
    dfg_rows = []
    for source in sorted(dfg.keys()):
        for target, count in sorted(dfg[source].items()):
            dfg_rows.append([source, target, count])

    # Build Correction Predecessors table
    correction_pred_rows = []
    for pred in correction_predecessors:
        correction_pred_rows.append([pred["activity"], pred["count"]])

    result = {
        "name": "process_mining",
        "summary": f"Process mining analysis of {len(event_logs)} sessions with {total_events} total events",
        "findings": [
            {"label": "total_events", "value": total_events},
            {"label": "unique_activities", "value": unique_activities},
            {"label": "most_common_activity", "value": most_common_activity},
            {"label": "top_rework_activity", "value": top_rework_activity},
            {"label": "top_correction_predecessor", "value": top_correction_predecessor},
            {"label": "dfg_edges", "value": dfg_edges}
        ],
        "tables": [
            {
                "name": "Activity Frequencies",
                "columns": ["Activity", "Frequency", "Session Coverage (%)", "Mean Dwell Time"],
                "rows": activity_freq_rows
            },
            {
                "name": "Directly-Follows Graph",
                "columns": ["Source", "Target", "Count"],
                "rows": dfg_rows
            },
            {
                "name": "Correction Predecessors",
                "columns": ["Activity", "Count"],
                "rows": correction_pred_rows
            }
        ]
    }

    print(json.dumps(result))

if __name__ == "__main__":
    main()
