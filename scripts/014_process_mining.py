#!/usr/bin/env python3
"""
014 - Process Mining on Claude Code Session Data
Adapted for Third Thoughts corpus.
Uses pm4py to discover workflow models, find bottlenecks, rework loops, and deviations.
"""

import json
import os
import re
import sys
from datetime import datetime, timezone
from collections import Counter, defaultdict
from pathlib import Path
import warnings
warnings.filterwarnings("ignore")

import pandas as pd
import pm4py
from pm4py.objects.log.importer.xes import importer as xes_importer
from pm4py.algo.discovery.inductive import algorithm as inductive_miner
from pm4py.algo.conformance.tokenreplay import algorithm as token_replay
from pm4py.algo.discovery.dfg import algorithm as dfg_discovery
from pm4py.statistics.traces.generic.log import case_statistics
from pm4py.objects.petri_net.utils import petri_utils
from pm4py.objects.conversion.log import converter as log_converter

# --- Configuration ---

CORPUS_ROOT = Path(os.environ.get("MIDDENS_CORPUS", "corpus/"))
OUTPUT_DIR = Path(os.environ.get("MIDDENS_OUTPUT", "experiments/"))

# ============================================================
# STEP 1: Convert sessions to event logs
# ============================================================

CORRECTION_SIGNALS = [
    r'\bno\b', r'\bwrong\b', r'\bincorrect\b', r'\bfix\b', r'\bundo\b',
    r'\brevert\b', r'\bdon\'t\b', r'\bstop\b', r'\bnot what\b',
    r'\bthat\'s not\b', r'\bactually\b', r'\binstead\b',
    r'request interrupted by user',
]
CORRECTION_RE = re.compile('|'.join(CORRECTION_SIGNALS), re.IGNORECASE)

TOOL_TO_ACTIVITY = {
    'Read': 'search_code',
    'Glob': 'search_code',
    'Grep': 'search_code',
    'Edit': 'edit_file',
    'Write': 'write_file',
    'Bash': 'run_command',
    'Agent': 'run_command',
    'Skill': 'run_command',
    'TaskCreate': 'run_command',
    'TaskList': 'run_command',
    'TaskOutput': 'run_command',
    'TaskStop': 'run_command',
    'TaskUpdate': 'run_command',
    'ToolSearch': 'search_code',
    'WebSearch': 'search_code',
    'WebFetch': 'search_code',
    'AskUserQuestion': 'user_approval',
    'NotebookEdit': 'edit_file',
}


def classify_user_message(content):
    """Classify a user message as correction or regular request."""
    if isinstance(content, list):
        texts = []
        has_tool_result = False
        for c in content:
            if isinstance(c, dict):
                if c.get('type') == 'text':
                    texts.append(c.get('text', ''))
                elif c.get('type') == 'tool_result':
                    has_tool_result = True
        if has_tool_result and not texts:
            return 'user_approval'
        text = ' '.join(texts)
    elif isinstance(content, str):
        text = content
    else:
        return 'user_request'

    if not text.strip():
        return 'user_approval'

    if CORRECTION_RE.search(text):
        return 'user_correction'

    return 'user_request'


def extract_events_from_session(filepath):
    """Extract process mining events from a JSONL session file."""
    session_id = os.path.splitext(os.path.basename(filepath))[0]
    events = []

    with open(filepath) as f:
        for line in f:
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue

            ts_str = rec.get('timestamp')
            if not ts_str:
                continue

            try:
                ts = datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
            except (ValueError, AttributeError):
                continue

            rec_type = rec.get('type', '')

            if rec_type in ('file-history-snapshot', 'last-prompt', 'pr-link',
                           'queue-operation', 'progress', 'system'):
                continue

            if rec_type == 'user':
                content = rec.get('message', {}).get('content', rec.get('content', ''))
                activity = classify_user_message(content)
                events.append({
                    'case:concept:name': session_id,
                    'concept:name': activity,
                    'time:timestamp': ts,
                    'org:resource': 'human',
                })

            elif rec_type == 'assistant':
                message = rec.get('message', {})
                content = message.get('content', [])
                if not isinstance(content, list):
                    continue

                for block in content:
                    if not isinstance(block, dict):
                        continue

                    block_type = block.get('type', '')

                    if block_type == 'thinking':
                        events.append({
                            'case:concept:name': session_id,
                            'concept:name': 'think',
                            'time:timestamp': ts,
                            'org:resource': 'agent',
                        })

                    elif block_type == 'text':
                        text = block.get('text', '')
                        if len(text.strip()) > 0:
                            events.append({
                                'case:concept:name': session_id,
                                'concept:name': 'agent_text',
                                'time:timestamp': ts,
                                'org:resource': 'agent',
                            })

                    elif block_type == 'tool_use':
                        tool_name = block.get('name', '')
                        if tool_name.startswith('mcp__'):
                            activity = 'run_command'
                        else:
                            activity = TOOL_TO_ACTIVITY.get(tool_name, 'run_command')

                        events.append({
                            'case:concept:name': session_id,
                            'concept:name': activity,
                            'time:timestamp': ts,
                            'org:resource': 'agent',
                        })

    return events


def deduplicate_consecutive(events):
    """Remove consecutive duplicate activities within a case."""
    if not events:
        return events
    deduped = [events[0]]
    for e in events[1:]:
        prev = deduped[-1]
        if (e['concept:name'] == prev['concept:name'] and
            e['case:concept:name'] == prev['case:concept:name'] and
            e['time:timestamp'] == prev['time:timestamp']):
            continue
        deduped.append(e)
    return deduped


def find_all_session_files():
    """Find all JSONL session files in the corpus (follows symlinks)."""
    files = []
    for root, dirs, filenames in os.walk(CORPUS_ROOT, followlinks=True):
        for fname in filenames:
            if fname.endswith('.jsonl'):
                files.append(os.path.join(root, fname))
    return files


def load_sessions(n_sessions=50):
    """Load and convert N sessions to event log."""
    files = find_all_session_files()

    # Sort by size descending
    files_with_size = [(f, os.path.getsize(f)) for f in files]
    files_with_size.sort(key=lambda x: x[1], reverse=True)

    # Skip mega-sessions (>100MB), take next N with decent size (>10KB)
    candidates = [f for f, s in files_with_size if 10_000 < s < 100_000_000]
    selected = candidates[:n_sessions]

    print(f"Processing {len(selected)} sessions (from {len(files)} total)...")

    all_events = []
    sessions_processed = 0
    for filepath in selected:
        events = extract_events_from_session(filepath)
        if len(events) >= 5:
            events = deduplicate_consecutive(events)
            all_events.extend(events)
            sessions_processed += 1

    print(f"  Sessions with >= 5 events: {sessions_processed}")
    print(f"  Total events: {len(all_events)}")

    df = pd.DataFrame(all_events)
    df['time:timestamp'] = pd.to_datetime(df['time:timestamp'], utc=True)
    df = df.sort_values(['case:concept:name', 'time:timestamp']).reset_index(drop=True)

    return df


# ============================================================
# STEP 2: Discover process model
# ============================================================

def discover_process_model(df):
    """Use inductive miner to discover the actual workflow model."""
    log = pm4py.convert_to_event_log(df)

    process_tree = pm4py.discover_process_tree_inductive(log, noise_threshold=0.2)
    net, im, fm = pm4py.convert_to_petri_net(process_tree)
    dfg, sa, ea = pm4py.discover_dfg(log)

    print("\n=== PROCESS MODEL (Inductive Miner) ===")
    print(f"Process tree: {process_tree}")
    print(f"Petri net places: {len(net.places)}, transitions: {len(net.transitions)}")

    print("\n=== TOP ACTIVITY TRANSITIONS (DFG) ===")
    sorted_dfg = sorted(dfg.items(), key=lambda x: x[1], reverse=True)
    for (a, b), count in sorted_dfg[:25]:
        print(f"  {a} -> {b}: {count}")

    print("\n=== START ACTIVITIES ===")
    for act, count in sorted(sa.items(), key=lambda x: x[1], reverse=True):
        print(f"  {act}: {count}")

    print("\n=== END ACTIVITIES ===")
    for act, count in sorted(ea.items(), key=lambda x: x[1], reverse=True):
        print(f"  {act}: {count}")

    return log, net, im, fm, dfg, sa, ea, process_tree


# ============================================================
# STEP 3: Conformance checking
# ============================================================

def conformance_checking(log, net, im, fm):
    """Check conformance against the ideal process."""
    print("\n=== CONFORMANCE CHECKING ===")

    replayed = token_replay.apply(log, net, im, fm)

    fitting = sum(1 for r in replayed if r['trace_is_fit'])
    total = len(replayed)
    fitness_values = [r['trace_fitness'] for r in replayed]
    avg_fitness = sum(fitness_values) / len(fitness_values) if fitness_values else 0

    print(f"  Traces fitting discovered model: {fitting}/{total} ({100*fitting/total:.1f}%)")
    print(f"  Average trace fitness: {avg_fitness:.3f}")

    ideal_sequence = ['user_request', 'think', 'search_code', 'think', 'edit_file', 'run_command', 'user_approval']

    contains_ideal = 0
    partial_matches = Counter()

    for trace in log:
        activities = [e['concept:name'] for e in trace]

        idx = 0
        matched = 0
        for act in activities:
            if idx < len(ideal_sequence) and act == ideal_sequence[idx]:
                idx += 1
                matched += 1

        if idx == len(ideal_sequence):
            contains_ideal += 1

        for i in range(len(ideal_sequence)):
            subseq = tuple(ideal_sequence[:i+1])
            sidx = 0
            for act in activities:
                if sidx < len(subseq) and act == subseq[sidx]:
                    sidx += 1
            if sidx == len(subseq):
                partial_matches[i+1] += 1

    print(f"\n=== IDEAL PROCESS CONFORMANCE ===")
    print(f"  Sessions containing full ideal sequence: {contains_ideal}/{total} ({100*contains_ideal/total:.1f}%)")
    print(f"  Partial ideal matches:")
    for length in sorted(partial_matches.keys()):
        seq = ' -> '.join(ideal_sequence[:length])
        count = partial_matches[length]
        print(f"    {seq}: {count}/{total} ({100*count/total:.1f}%)")

    # Variant analysis
    print("\n=== TOP PROCESS VARIANTS ===")
    variants = pm4py.get_variants(log)
    sorted_variants = sorted(variants.items(), key=lambda x: len(x[1]), reverse=True)

    for variant_key, traces in sorted_variants[:10]:
        if isinstance(variant_key, tuple):
            acts = list(variant_key)
        else:
            acts = variant_key.split(',')

        if len(acts) > 12:
            display = ' -> '.join(acts[:6]) + f' ... ({len(acts)} steps) ... ' + ' -> '.join(acts[-3:])
        else:
            display = ' -> '.join(acts)
        print(f"  [{len(traces)} cases] {display}")

    return replayed, fitness_values


# ============================================================
# STEP 4: Bottlenecks and rework loops
# ============================================================

def analyze_bottlenecks_and_loops(df, log, dfg):
    """Find bottlenecks and rework loops."""
    print("\n=== BOTTLENECK ANALYSIS: DWELL TIMES ===")

    df_sorted = df.sort_values(['case:concept:name', 'time:timestamp'])
    df_sorted['next_time'] = df_sorted.groupby('case:concept:name')['time:timestamp'].shift(-1)
    df_sorted['dwell_seconds'] = (df_sorted['next_time'] - df_sorted['time:timestamp']).dt.total_seconds()

    dwell_stats = df_sorted.groupby('concept:name')['dwell_seconds'].agg(['mean', 'median', 'std', 'count'])
    dwell_stats = dwell_stats.sort_values('median', ascending=False)

    print(f"  {'Activity':<20} {'Median(s)':<12} {'Mean(s)':<12} {'Std(s)':<12} {'Count':<8}")
    print(f"  {'-'*64}")
    for act, row in dwell_stats.iterrows():
        print(f"  {act:<20} {row['median']:<12.1f} {row['mean']:<12.1f} {row['std']:<12.1f} {int(row['count']):<8}")

    print("\n=== REWORK LOOPS (A -> B -> A patterns) ===")
    loop_counter = Counter()

    for trace in log:
        activities = [e['concept:name'] for e in trace]
        for i in range(len(activities) - 2):
            if activities[i] == activities[i+2] and activities[i] != activities[i+1]:
                loop = f"{activities[i]} -> {activities[i+1]} -> {activities[i]}"
                loop_counter[loop] += 1

    for loop, count in loop_counter.most_common(15):
        print(f"  {loop}: {count}")

    print("\n=== EXTENDED REWORK PATTERNS (activity recurrence) ===")
    recurrence = Counter()
    for trace in log:
        activities = [e['concept:name'] for e in trace]
        seen_positions = defaultdict(list)
        for i, act in enumerate(activities):
            seen_positions[act].append(i)
        for act, positions in seen_positions.items():
            if len(positions) > 1:
                recurrence[act] += 1

    total_traces = len(log)
    for act, count in recurrence.most_common():
        print(f"  {act}: recurs in {count}/{total_traces} sessions ({100*count/total_traces:.1f}%)")

    print("\n=== CORRECTION CLUSTERING ===")
    correction_predecessors = Counter()
    correction_successors = Counter()

    for trace in log:
        activities = [e['concept:name'] for e in trace]
        for i, act in enumerate(activities):
            if act == 'user_correction':
                if i > 0:
                    correction_predecessors[activities[i-1]] += 1
                if i < len(activities) - 1:
                    correction_successors[activities[i+1]] += 1

    print("  Activities BEFORE corrections:")
    for act, count in correction_predecessors.most_common(10):
        print(f"    {act}: {count}")

    print("  Activities AFTER corrections:")
    for act, count in correction_successors.most_common(10):
        print(f"    {act}: {count}")

    return dwell_stats, loop_counter, recurrence


# ============================================================
# STEP 5: Compare successful vs failed sessions
# ============================================================

def compare_sessions(df, log):
    """Split sessions by correction rate and compare process models."""
    print("\n=== SESSION COMPARISON: LOW vs HIGH CORRECTION RATE ===")

    session_stats = {}
    for trace in log:
        case_id = trace.attributes['concept:name']
        activities = [e['concept:name'] for e in trace]
        total = len(activities)
        corrections = activities.count('user_correction')
        session_stats[case_id] = {
            'total_events': total,
            'corrections': corrections,
            'correction_rate': corrections / total if total > 0 else 0,
            'activities': activities,
        }

    rates = [s['correction_rate'] for s in session_stats.values()]
    if not rates:
        print("  No sessions to compare.")
        return

    median_rate = sorted(rates)[len(rates)//2]

    low_correction = {k: v for k, v in session_stats.items() if v['correction_rate'] <= median_rate}
    high_correction = {k: v for k, v in session_stats.items() if v['correction_rate'] > median_rate}

    print(f"  Median correction rate: {median_rate:.3f}")
    print(f"  Low-correction sessions: {len(low_correction)} (rate <= {median_rate:.3f})")
    print(f"  High-correction sessions: {len(high_correction)} (rate > {median_rate:.3f})")

    for label, group in [("LOW-CORRECTION (smooth)", low_correction),
                         ("HIGH-CORRECTION (rough)", high_correction)]:
        print(f"\n  --- {label} ---")
        all_acts = []
        for s in group.values():
            all_acts.extend(s['activities'])
        act_counts = Counter(all_acts)
        total = sum(act_counts.values())
        print(f"  Total events: {total}")
        for act, count in act_counts.most_common():
            print(f"    {act}: {count} ({100*count/total:.1f}%)")

        lengths = [s['total_events'] for s in group.values()]
        avg_len = sum(lengths) / len(lengths) if lengths else 0
        print(f"  Avg session length: {avg_len:.1f} events")

        transitions = Counter()
        for s in group.values():
            acts = s['activities']
            for i in range(len(acts)-1):
                transitions[(acts[i], acts[i+1])] += 1

        print(f"  Top transitions:")
        for (a, b), count in transitions.most_common(8):
            print(f"    {a} -> {b}: {count}")

    # Discover separate models
    print("\n  --- STRUCTURAL DIFFERENCES ---")

    for label, group in [("low_correction", low_correction),
                         ("high_correction", high_correction)]:
        case_ids = set(group.keys())
        subset_df = df[df['case:concept:name'].isin(case_ids)].copy()
        if len(subset_df) < 10:
            print(f"  {label}: too few events for model discovery")
            continue

        sub_log = pm4py.convert_to_event_log(subset_df)
        sub_dfg, sub_sa, sub_ea = pm4py.discover_dfg(sub_log)

        print(f"\n  {label.upper()} model:")
        print(f"    Start activities: {dict(sorted(sub_sa.items(), key=lambda x: x[1], reverse=True))}")
        print(f"    End activities: {dict(sorted(sub_ea.items(), key=lambda x: x[1], reverse=True))}")

        sorted_dfg = sorted(sub_dfg.items(), key=lambda x: x[1], reverse=True)
        print(f"    Top DFG edges:")
        for (a, b), count in sorted_dfg[:10]:
            print(f"      {a} -> {b}: {count}")

    # Key differences
    print("\n  --- KEY DIFFERENCES ---")

    for label, group in [("low_correction", low_correction), ("high_correction", high_correction)]:
        all_acts = []
        for s in group.values():
            all_acts.extend(s['activities'])
        total = len(all_acts) if all_acts else 1
        think_ratio = all_acts.count('think') / total
        search_ratio = all_acts.count('search_code') / total
        edit_ratio = all_acts.count('edit_file') / total
        text_ratio = all_acts.count('agent_text') / total
        print(f"  {label}: think={think_ratio:.3f}, search={search_ratio:.3f}, edit={edit_ratio:.3f}, text={text_ratio:.3f}")

    return session_stats


# ============================================================
# MAIN
# ============================================================

def main():
    class Tee:
        def __init__(self):
            self.lines = []
        def write(self, text):
            sys.__stdout__.write(text)
            self.lines.append(text)
        def flush(self):
            sys.__stdout__.flush()

    tee = Tee()
    old_stdout = sys.stdout
    sys.stdout = tee

    try:
        print("=" * 70)
        print("PROCESS MINING ON CLAUDE CODE SESSION DATA")
        print("(Third Thoughts Corpus)")
        print("=" * 70)

        print("\n### STEP 1: Convert sessions to event logs ###")
        df = load_sessions(n_sessions=200)

        activity_counts = df['concept:name'].value_counts()
        print(f"\n  Activity distribution:")
        for act, count in activity_counts.items():
            print(f"    {act}: {count}")

        n_cases = df['case:concept:name'].nunique()
        print(f"\n  Unique sessions (cases): {n_cases}")

        print("\n### STEP 2: Discover process model ###")
        log, net, im, fm, dfg, sa, ea, process_tree = discover_process_model(df)

        print("\n### STEP 3: Conformance checking ###")
        replayed, fitness_values = conformance_checking(log, net, im, fm)

        print("\n### STEP 4: Bottlenecks and rework loops ###")
        dwell_stats, loop_counter, recurrence = analyze_bottlenecks_and_loops(df, log, dfg)

        print("\n### STEP 5: Compare successful vs failed sessions ###")
        session_stats = compare_sessions(df, log)

        print("\n" + "=" * 70)
        print("PROCESS MINING COMPLETE")
        print("=" * 70)

    finally:
        sys.stdout = old_stdout

    return ''.join(tee.lines), df, log, net, im, fm, dfg, dwell_stats, loop_counter, session_stats


if __name__ == '__main__':
    output, df, log, net, im, fm, dfg, dwell_stats, loop_counter, session_stats = main()

    # Save raw output
    output_path = OUTPUT_DIR / "014-process-mining-raw.txt"
    with open(output_path, 'w') as f:
        f.write(output)

    print(f"\nRaw output saved to {output_path}")
