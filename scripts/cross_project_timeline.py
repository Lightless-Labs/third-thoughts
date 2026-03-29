#!/usr/bin/env python3
"""
Build a timeline of cross-project activity from Claude Code JSONL session files.
Adapted for Third Thoughts corpus.

Lists all sessions grouped by date, showing how many projects were active
on the same day.
"""
import os
import json
import re
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

CORPUS_ROOT = Path(os.environ.get("MIDDENS_CORPUS", "corpus/"))
OUTPUT_DIR = Path(os.environ.get("MIDDENS_OUTPUT", "experiments/"))


def get_project_name(filepath: str) -> str:
    """Extract readable project name from file path."""
    parts = filepath.split("/")

    # Claude Code: .../projects/<proj_dir>/...
    # Claude AI:  .../projects/<proj_dir>/...
    for i, p in enumerate(parts):
        if p == "projects" and i + 1 < len(parts):
            dirname = parts[i + 1]
            # Clean up the directory name
            name = dirname.lstrip("-")
            # Try to extract meaningful suffix
            segments = name.split("-")
            for j, s in enumerate(segments):
                if s.lower() == "projects":
                    rest = "-".join(segments[j + 1:])
                    if rest:
                        return rest
            # Fallback
            if name.startswith("Users-"):
                # Remove Users-<username>- prefix
                user_removed = "-".join(segments[2:]) if len(segments) > 2 else name
                return user_removed or name
            return name
    return os.path.basename(os.path.dirname(filepath))


def get_session_timestamps(filepath: Path):
    """Get first and last timestamps from a JSONL session file."""
    first_ts = None
    last_ts = None
    try:
        with open(filepath) as f:
            for line in f:
                try:
                    record = json.loads(line)
                    ts = record.get("timestamp")
                    if ts:
                        if first_ts is None:
                            first_ts = ts
                        last_ts = ts
                except json.JSONDecodeError:
                    continue
    except Exception:
        pass
    return first_ts, last_ts


def find_all_sessions():
    """Find all JSONL files across the corpus (follows symlinks)."""
    sessions = []
    for root, dirs, fnames in os.walk(str(CORPUS_ROOT), followlinks=True):
        for fn in fnames:
            if fn.endswith(".jsonl"):
                sessions.append(Path(os.path.join(root, fn)))
    return sessions


def main():
    print("Finding session files in corpus...")
    all_files = find_all_sessions()
    print(f"Found {len(all_files)} JSONL files\n")

    # date -> project -> list of (session_file, first_ts, last_ts)
    daily_activity = defaultdict(lambda: defaultdict(list))
    all_sessions = []

    for jsonl in sorted(all_files):
        project = get_project_name(str(jsonl))
        first_ts, last_ts = get_session_timestamps(jsonl)
        if first_ts:
            try:
                dt = datetime.fromisoformat(first_ts.replace("Z", "+00:00"))
                date_str = dt.strftime("%Y-%m-%d")
                time_str = dt.strftime("%H:%M:%S")
                daily_activity[date_str][project].append({
                    "file": str(jsonl),
                    "first_ts": first_ts,
                    "last_ts": last_ts,
                    "time": time_str,
                })
                all_sessions.append({
                    "date": date_str,
                    "project": project,
                    "file": str(jsonl),
                    "first_ts": first_ts,
                    "last_ts": last_ts,
                    "time": time_str,
                })
            except (ValueError, AttributeError):
                pass

    # Print timeline
    output_lines = []

    def out(line=""):
        print(line)
        output_lines.append(line)

    out("=" * 90)
    out("CROSS-PROJECT ACTIVITY TIMELINE (Third Thoughts Corpus)")
    out("=" * 90)

    for date in sorted(daily_activity.keys()):
        projects = daily_activity[date]
        n_projects = len(projects)
        n_sessions = sum(len(s) for s in projects.values())
        marker = " *** HIGH CONCURRENCY ***" if n_projects >= 3 else ""
        out(f"\n{'='*70}")
        out(f"  {date}  |  {n_projects} projects  |  {n_sessions} sessions{marker}")
        out(f"{'='*70}")
        for proj in sorted(projects.keys()):
            sessions = projects[proj]
            out(f"  {proj:40s}  ({len(sessions)} sessions)")
            for s in sorted(sessions, key=lambda x: x["time"]):
                fname = os.path.basename(s["file"])
                out(f"    {s['time']}  {fname[:60]}")

    # Summary of high-concurrency days
    out("\n\n" + "=" * 90)
    out("DAYS WITH 3+ ACTIVE PROJECTS (for sampling)")
    out("=" * 90)
    high_days = []
    for date in sorted(daily_activity.keys()):
        projects = daily_activity[date]
        if len(projects) >= 3:
            n_sessions = sum(len(s) for s in projects.values())
            high_days.append((date, len(projects), n_sessions))
            out(f"  {date}:  {len(projects)} projects, {n_sessions} sessions")
            for proj in sorted(projects.keys()):
                out(f"    - {proj} ({len(projects[proj])} sessions)")

    # Summary stats
    out("\n\n" + "=" * 90)
    out("SUMMARY STATISTICS")
    out("=" * 90)
    all_projects = set()
    for date, projects in daily_activity.items():
        all_projects.update(projects.keys())

    out(f"  Total sessions with timestamps: {len(all_sessions)}")
    out(f"  Total active dates: {len(daily_activity)}")
    out(f"  Total distinct projects: {len(all_projects)}")
    if daily_activity:
        out(f"  Date range: {min(daily_activity.keys())} to {max(daily_activity.keys())}")
    else:
        out(f"  Date range: (no timestamped sessions found)")
    out(f"  High-concurrency days (3+ projects): {len(high_days)}")

    # Sessions per project
    project_counts = defaultdict(int)
    for s in all_sessions:
        project_counts[s["project"]] += 1

    out(f"\n  Sessions per project:")
    for proj, count in sorted(project_counts.items(), key=lambda x: -x[1]):
        out(f"    {proj}: {count}")

    # Operator activity (try to identify from path)
    operator_counts = defaultdict(int)
    for s in all_sessions:
        # Extract operator from -Users-<name>- path pattern
        m = re.search(r'-Users-([^-]+)-', s["file"])
        if m:
            operator_counts[m.group(1)] += 1
        else:
            operator_counts["unknown"] += 1

    out(f"\n  Sessions per operator:")
    for op, count in sorted(operator_counts.items(), key=lambda x: -x[1]):
        out(f"    {op}: {count}")

    # Write output to file
    output_path = OUTPUT_DIR / "cross-project-timeline.txt"
    with open(output_path, "w") as f:
        f.write("\n".join(output_lines))
    print(f"\n\nTimeline saved to {output_path}")


if __name__ == "__main__":
    main()
