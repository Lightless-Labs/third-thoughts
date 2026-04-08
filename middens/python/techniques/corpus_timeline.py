#!/usr/bin/env python3
# corpus_timeline.py — provisional technique
#
# Exists so reports are reproducible without the source corpus.
# Will be deleted in favour of a view spec over sessions.parquet
# once the storage/view reshape lands. See todos/output-contract.md
# post-reshape-cleanup section.
"""Corpus timeline technique - generates activity timelines from session data."""

import json
import math
import sys
from datetime import datetime
from collections import defaultdict

def _sanitize(obj):
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize(v) for v in obj]
    return obj

def get_session_date(session):
    """Extract date from first non-null timestamp in session messages."""
    messages = session.get("messages", [])
    for msg in messages:
        timestamp = msg.get("timestamp")
        if timestamp:
            try:
                dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                return dt.strftime("%Y-%m-%d")
            except (ValueError, AttributeError):
                continue
    return None

def main():
    if len(sys.argv) < 2:
        print("Usage: python corpus_timeline.py <path_to_sessions.json>", file=sys.stderr)
        sys.exit(1)
    
    input_path = sys.argv[1]
    
    try:
        with open(input_path, "r", encoding="utf-8") as f:
            sessions = json.load(f)
    except FileNotFoundError:
        print(f"Error: File not found: {input_path}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: Could not read file: {e}", file=sys.stderr)
        sys.exit(1)
    
    total_sessions = len(sessions)
    undated_sessions = 0
    
    date_project_count = defaultdict(int)
    sessions_per_day = defaultdict(int)
    distinct_projects_per_day = defaultdict(set)
    sessions_per_project = defaultdict(int)
    first_seen = {}
    last_seen = {}
    
    for session in sessions:
        date = get_session_date(session)
        if date is None:
            undated_sessions += 1
            continue
        
        project = session.get("metadata", {}).get("project")
        if not project:
            project = "(unknown)"
        
        date_project_count[(date, project)] += 1
        sessions_per_day[date] += 1
        distinct_projects_per_day[date].add(project)
        sessions_per_project[project] += 1
        
        if project not in first_seen or date < first_seen[project]:
            first_seen[project] = date
        if project not in last_seen or date > last_seen[project]:
            last_seen[project] = date
    
    dated_sessions_exist = len(sessions_per_day) > 0
    
    if total_sessions == 0 or not dated_sessions_exist:
        result = {
            "name": "corpus-timeline",
            "summary": "insufficient dated sessions for corpus timeline",
            "findings": [
                {"label": "total_sessions", "value": total_sessions, "description": None},
                {"label": "undated_sessions", "value": undated_sessions, "description": None},
                {"label": "total_dates", "value": 0, "description": None},
                {"label": "total_projects", "value": 0, "description": None},
                {"label": "high_concurrency_day_count", "value": 0, "description": None},
                {"label": "date_range_min", "value": "", "description": None},
                {"label": "date_range_max", "value": "", "description": None},
                {"label": "peak_day", "value": "", "description": None}
            ],
            "tables": [
                {"name": "Daily Activity", "columns": ["date", "project", "session_count"], "rows": []},
                {"name": "Daily Totals", "columns": ["date", "session_count", "distinct_projects"], "rows": []},
                {"name": "Project Totals", "columns": ["project", "session_count", "first_seen", "last_seen"], "rows": []}
            ],
            "figures": []
        }
        print(json.dumps(_sanitize(result), indent=2))
        return
    
    high_concurrency_day_count = sum(
        1 for projects in distinct_projects_per_day.values()
        if len(projects) >= 3
    )
    
    sorted_dates = sorted(sessions_per_day.keys())
    date_range_min = sorted_dates[0]
    date_range_max = sorted_dates[-1]
    
    # Peak day = highest session count; ties broken by earliest date (ascending).
    peak_count = max(sessions_per_day.values())
    peak_day = min(d for d, c in sessions_per_day.items() if c == peak_count)
    
    total_dates = len(sessions_per_day)
    total_projects = len(sessions_per_project)
    
    daily_activity_rows = []
    for (date, project), count in sorted(date_project_count.items()):
        daily_activity_rows.append([date, project, count])
    
    daily_totals_rows = []
    for date in sorted_dates:
        daily_totals_rows.append([
            date,
            sessions_per_day[date],
            len(distinct_projects_per_day[date])
        ])
    
    project_totals_rows = []
    sorted_projects = sorted(
        sessions_per_project.items(),
        key=lambda x: (-x[1], x[0])
    )
    for project, count in sorted_projects:
        project_totals_rows.append([
            project,
            count,
            first_seen[project],
            last_seen[project]
        ])
    
    result = {
        "name": "corpus-timeline",
        "summary": "Corpus timeline analysis of session activity",
        "findings": [
            {"label": "total_sessions", "value": total_sessions, "description": None},
            {"label": "undated_sessions", "value": undated_sessions, "description": None},
            {"label": "total_dates", "value": total_dates, "description": None},
            {"label": "total_projects", "value": total_projects, "description": None},
            {"label": "high_concurrency_day_count", "value": high_concurrency_day_count, "description": None},
            {"label": "date_range_min", "value": date_range_min, "description": None},
            {"label": "date_range_max", "value": date_range_max, "description": None},
            {"label": "peak_day", "value": peak_day, "description": None}
        ],
        "tables": [
            {"name": "Daily Activity", "columns": ["date", "project", "session_count"], "rows": daily_activity_rows},
            {"name": "Daily Totals", "columns": ["date", "session_count", "distinct_projects"], "rows": daily_totals_rows},
            {"name": "Project Totals", "columns": ["project", "session_count", "first_seen", "last_seen"], "rows": project_totals_rows}
        ],
        "figures": []
    }
    
    print(json.dumps(_sanitize(result), indent=2))

if __name__ == "__main__":
    main()
