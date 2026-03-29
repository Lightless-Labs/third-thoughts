#!/usr/bin/env python3
"""
Experiment 018: Change-Point Detection in Claude Code Sessions
Applies signal processing change-point detection (ruptures library)
to find regime shifts within sessions.
"""

import json
import os
import glob
import math
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

try:
    import ruptures as rpt
except ImportError:
    print("Installing ruptures...")
    os.system("pip3 install ruptures")
    import ruptures as rpt


# ============================================================
# 1. DATA LOADING
# ============================================================

def load_session(filepath, max_lines=30000):
    """Load a JSONL session file and return structured turns."""
    turns = []
    with open(filepath, 'r') as f:
        for i, line in enumerate(f):
            if i >= max_lines:
                break
            try:
                obj = json.loads(line)
                msg_type = obj.get('type')
                if msg_type in ('user', 'assistant'):
                    turns.append(obj)
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue
    return turns


def extract_turn_features(turns):
    """
    From raw turns, extract per-turn features:
    - turn_index
    - role (user/assistant)
    - text_length (of text content)
    - tool_names (list of tools used in this turn)
    - is_correction (heuristic: user message with correction signals)
    - is_interruption (user sent interrupt signal)
    """
    features = []
    for i, turn in enumerate(turns):
        role = turn.get('type', 'unknown')
        content = turn.get('message', {}).get('content', [])

        text_length = 0
        tool_names = []
        text_content = ""

        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict):
                    if block.get('type') == 'text':
                        t = block.get('text', '')
                        text_length += len(t)
                        text_content += t + " "
                    elif block.get('type') == 'tool_use':
                        tool_names.append(block.get('name', 'unknown'))
                elif isinstance(block, str):
                    text_length += len(block)
                    text_content += block + " "
        elif isinstance(content, str):
            text_length = len(content)
            text_content = content

        text_content = text_content.strip()

        # Detect corrections/redirections
        is_correction = False
        is_interruption = False
        if role == 'user':
            lower = text_content.lower()
            # Interrupt signals
            if text_content in ('.', '!', '>', 'n', 'no', '?', '️'):
                is_interruption = True
            if '[Request interrupted by user' in text_content:
                is_interruption = True
            # Correction signals
            correction_patterns = [
                r'\bno\b', r'\bwrong\b', r'\bincorrect\b', r'\bstop\b',
                r'\binstead\b', r'\bactually\b', r'\bnot what\b',
                r'\bdon\'t\b', r'\bdo not\b', r'\bshouldn\'t\b',
                r'\bretry\b', r'\btry again\b', r'\bundo\b', r'\brevert\b',
                r'\bfix\b', r'\bbroke\b', r'\bbroken\b', r'\bbug\b',
                r'\bwait\b', r'\bhang on\b', r'\bhold on\b',
                r'\bthat\'s not\b', r'\bthats not\b',
                r'\bnever mind\b', r'\bnevermind\b',
            ]
            if any(re.search(p, lower) for p in correction_patterns):
                is_correction = True
            if is_interruption:
                is_correction = True  # interrupts are a form of correction

        features.append({
            'turn_index': i,
            'role': role,
            'text_length': text_length,
            'tool_names': tool_names,
            'is_correction': is_correction,
            'is_interruption': is_interruption,
            'timestamp': turn.get('timestamp', ''),
        })

    return features


# ============================================================
# 2. TIME SERIES CONSTRUCTION
# ============================================================

def shannon_entropy(counts):
    """Compute Shannon entropy from a Counter."""
    total = sum(counts.values())
    if total == 0:
        return 0.0
    entropy = 0.0
    for c in counts.values():
        if c > 0:
            p = c / total
            entropy -= p * math.log2(p)
    return entropy


def build_time_series(features, window=10):
    """
    Build rolling-window time series from turn features.
    Returns dict of numpy arrays, one value per assistant turn.
    """
    # Extract assistant turn indices (these are our "ticks")
    assistant_indices = [i for i, f in enumerate(features) if f['role'] == 'assistant']

    if len(assistant_indices) < window + 5:
        return None  # Too short

    tool_entropy = []
    user_msg_length = []
    correction_density = []
    tool_call_rate = []

    for idx in range(len(assistant_indices)):
        # Window: last `window` assistant turns ending at idx
        start = max(0, idx - window + 1)
        window_assistant = assistant_indices[start:idx + 1]

        # Get all turns in the span covered by this window
        if len(window_assistant) < 2:
            span_start = 0
        else:
            span_start = window_assistant[0]
        span_end = window_assistant[-1] + 1
        window_features = features[span_start:span_end]

        # Tool entropy: Shannon entropy of tool types in window
        tool_counter = Counter()
        total_tools = 0
        for f in window_features:
            if f['role'] == 'assistant':
                for t in f['tool_names']:
                    tool_counter[t] += 1
                    total_tools += 1
        tool_entropy.append(shannon_entropy(tool_counter))

        # User message length (average in window)
        user_lengths = [f['text_length'] for f in window_features if f['role'] == 'user' and f['text_length'] > 0]
        user_msg_length.append(np.mean(user_lengths) if user_lengths else 0.0)

        # Correction density (corrections per window)
        corrections = sum(1 for f in window_features if f.get('is_correction'))
        correction_density.append(corrections)

        # Tool call rate (tools per assistant turn in window)
        assistant_in_window = [f for f in window_features if f['role'] == 'assistant']
        if assistant_in_window:
            tool_call_rate.append(total_tools / len(assistant_in_window))
        else:
            tool_call_rate.append(0.0)

    return {
        'tool_entropy': np.array(tool_entropy, dtype=float),
        'user_msg_length': np.array(user_msg_length, dtype=float),
        'correction_density': np.array(correction_density, dtype=float),
        'tool_call_rate': np.array(tool_call_rate, dtype=float),
        'n_assistant_turns': len(assistant_indices),
        'n_total_turns': len(features),
    }


# ============================================================
# 3. CHANGE POINT DETECTION
# ============================================================

def detect_change_points(signal, min_size=8, pen=1.5, max_length=500):
    """
    Detect change points using PELT algorithm with RBF kernel.
    For long signals, subsample to max_length then map CPs back.
    Returns list of change point indices.
    """
    if len(signal) < min_size * 2:
        return []

    # Normalize signal
    std = np.std(signal)
    if std < 1e-10:
        return []
    signal_norm = (signal - np.mean(signal)) / std

    # Subsample if too long (RBF PELT is O(n^2))
    subsample_factor = 1
    working_signal = signal_norm
    if len(signal_norm) > max_length:
        subsample_factor = len(signal_norm) // max_length + 1
        working_signal = signal_norm[::subsample_factor]
        min_size = max(5, min_size // subsample_factor)

    try:
        algo = rpt.Pelt(model="rbf", min_size=min_size).fit(working_signal)
        # Penalty scales with signal length
        penalty = pen * math.log(len(working_signal))
        result = algo.predict(pen=penalty)
        # Remove the last element (always = len(working_signal))
        if result and result[-1] == len(working_signal):
            result = result[:-1]
        # Map back to original indices
        if subsample_factor > 1:
            result = [min(cp * subsample_factor, len(signal) - 1) for cp in result]
        return result
    except Exception as e:
        # Fallback to Binseg if PELT fails
        try:
            algo = rpt.Binseg(model="rbf", min_size=min_size, n_bkps=10).fit(working_signal)
            result = algo.predict(pen=penalty)
            if result and result[-1] == len(working_signal):
                result = result[:-1]
            if subsample_factor > 1:
                result = [min(cp * subsample_factor, len(signal) - 1) for cp in result]
            return result
        except:
            return []


def detect_all_change_points(ts):
    """Detect change points across all time series for a session."""
    results = {}
    for key in ['tool_entropy', 'user_msg_length', 'correction_density', 'tool_call_rate']:
        signal = ts[key]
        cps = detect_change_points(signal)
        results[key] = cps
    return results


# ============================================================
# 4. REGIME CLASSIFICATION
# ============================================================

def classify_transition(ts, cp_idx, signal_name, window=5):
    """
    Classify a regime transition at cp_idx.
    Returns a classification string and confidence.
    """
    n = len(ts['tool_entropy'])
    before_start = max(0, cp_idx - window)
    after_end = min(n, cp_idx + window)

    # Get before/after values for each signal
    def before_after(signal):
        before = np.mean(signal[before_start:cp_idx]) if cp_idx > before_start else 0
        after = np.mean(signal[cp_idx:after_end]) if after_end > cp_idx else 0
        return before, after

    ent_before, ent_after = before_after(ts['tool_entropy'])
    corr_before, corr_after = before_after(ts['correction_density'])
    rate_before, rate_after = before_after(ts['tool_call_rate'])
    msg_before, msg_after = before_after(ts['user_msg_length'])

    ent_delta = ent_after - ent_before
    corr_delta = corr_after - corr_before
    rate_delta = rate_after - rate_before
    msg_delta = msg_after - msg_before

    # Classification rules (relaxed thresholds to reduce unclassified)
    classifications = []

    # "Got stuck": entropy drops, same tools repeat
    if ent_delta < -0.15 and rate_delta < 0:
        classifications.append(('got_stuck', abs(ent_delta) + abs(rate_delta)))

    # "Human redirected": correction spike, then new regime
    if corr_delta > 0.3:
        classifications.append(('human_redirected', corr_delta))

    # "Found the approach": entropy drops but productivity (tool rate) rises
    if ent_delta < -0.1 and rate_delta > 0:
        classifications.append(('found_approach', abs(ent_delta) + rate_delta))

    # "Context degradation": tool rate drops, message length increases
    if rate_delta < -0.15 and msg_delta > 20:
        classifications.append(('context_degradation', abs(rate_delta) + msg_delta / 100))

    # "Exploration burst": entropy increases, tool rate increases
    if ent_delta > 0.15 and rate_delta > 0:
        classifications.append(('exploration_burst', ent_delta + rate_delta))

    # "Settling down": entropy drops (general)
    if ent_delta < -0.15 and not classifications:
        classifications.append(('settling_down', abs(ent_delta)))

    # "Acceleration": tool rate jumps up significantly
    if rate_delta > 0.2 and not classifications:
        classifications.append(('acceleration', rate_delta))

    # "Deceleration": tool rate drops significantly
    if rate_delta < -0.2 and not classifications:
        classifications.append(('deceleration', abs(rate_delta)))

    # "Tool shift": entropy changes significantly but other signals flat
    if abs(ent_delta) > 0.15 and not classifications:
        if ent_delta > 0:
            classifications.append(('tool_diversification', ent_delta))
        else:
            classifications.append(('tool_specialization', abs(ent_delta)))

    if not classifications:
        classifications.append(('unclassified', 0.0))

    # Return highest confidence
    classifications.sort(key=lambda x: x[1], reverse=True)
    return classifications[0]


# ============================================================
# 5. MAIN ANALYSIS
# ============================================================

def find_session_files(base_dir, pattern=None):
    """Find JSONL session files, excluding subagent sessions."""
    session_files = []
    for dirpath, dirnames, filenames in os.walk(base_dir, followlinks=True):
        if 'subagents' in dirpath:
            continue
        for fname in filenames:
            if fname.endswith('.jsonl'):
                filepath = os.path.join(dirpath, fname)
                size = os.path.getsize(filepath)
                if size > 10000:  # Skip tiny sessions
                    session_files.append((filepath, size))

    session_files.sort(key=lambda x: x[1], reverse=True)
    return session_files


def main():
    base_dir = os.environ.get("MIDDENS_CORPUS", "corpus/")

    print("=" * 70)
    print("EXPERIMENT 018: CHANGE-POINT DETECTION IN CLAUDE CODE SESSIONS")
    print("=" * 70)
    print()

    # Find sessions
    all_sessions = find_session_files(base_dir)
    print(f"Found {len(all_sessions)} sessions with >10KB data")

    # Filter to sessions with at least 100KB (to ensure enough turns for analysis)
    qualifying = [s for s in all_sessions if s[1] >= 100_000]
    print(f"Sessions >= 100KB: {len(qualifying)}")

    # Sample ~35 sessions with project diversity
    # Group by project, take up to 3 per project, prioritize larger sessions
    from collections import OrderedDict
    project_groups = OrderedDict()
    for filepath, size in qualifying:
        proj = re.sub(r'-Users-[^-]+-', '-', Path(filepath).parent.name)
        if proj not in project_groups:
            project_groups[proj] = []
        project_groups[proj].append((filepath, size))

    sample = []
    max_per_project = 4
    # First pass: take up to max_per_project from each project
    for proj, sessions in project_groups.items():
        # Sort by size descending, take mix of sizes
        sessions.sort(key=lambda x: x[1], reverse=True)
        n = len(sessions)
        if n <= max_per_project:
            sample.extend(sessions)
        else:
            # Take largest, middle, and a smaller one
            indices = [0, n//3, 2*n//3, n-1][:max_per_project]
            for idx in indices:
                sample.append(sessions[idx])

    # Cap at 40
    if len(sample) > 40:
        sample.sort(key=lambda x: x[1], reverse=True)
        sample = sample[:40]

    print(f"Projects represented: {len(project_groups)}")
    project_counts = Counter(re.sub(r'-Users-[^-]+-', '-', Path(fp).parent.name) for fp, _ in sample)
    for proj, count in sorted(project_counts.items()):
        print(f"  {proj}: {count} sessions")

    print(f"Sampling {len(sample)} sessions")
    print()

    # Process each session
    all_results = []
    all_transitions = []
    all_cp_positions = []  # normalized 0-1 position

    sessions_processed = 0
    sessions_skipped = 0

    for si, (filepath, size) in enumerate(sample):
        session_id = Path(filepath).stem
        project = re.sub(r'-Users-[^-]+-', '-', Path(filepath).parent.name)

        sys.stdout.write(f"\r  Processing {si+1}/{len(sample)}: {project[:30]:<30s} ({size//1024}KB)")
        sys.stdout.flush()

        turns = load_session(filepath)
        if len(turns) < 30:
            sessions_skipped += 1
            continue

        features = extract_turn_features(turns)
        ts = build_time_series(features, window=10)

        if ts is None or ts['n_assistant_turns'] < 25:
            sessions_skipped += 1
            continue

        change_points = detect_all_change_points(ts)

        # Collect unique change points across all signals
        all_cps_for_session = set()
        for signal_name, cps in change_points.items():
            for cp in cps:
                all_cps_for_session.add(cp)

        # Classify each transition
        session_transitions = []
        for cp in sorted(all_cps_for_session):
            # Find which signals detected this CP (or near it)
            detecting_signals = []
            for sig_name, cps_list in change_points.items():
                for c in cps_list:
                    if abs(c - cp) <= 3:
                        detecting_signals.append(sig_name)
                        break

            classification, confidence = classify_transition(ts, cp, detecting_signals[0] if detecting_signals else 'tool_entropy')

            normalized_pos = cp / ts['n_assistant_turns']
            all_cp_positions.append(normalized_pos)

            session_transitions.append({
                'cp_index': cp,
                'normalized_position': normalized_pos,
                'classification': classification,
                'confidence': confidence,
                'detecting_signals': detecting_signals,
            })
            all_transitions.append({
                'session_id': session_id,
                'project': project,
                'classification': classification,
                'normalized_position': normalized_pos,
                'detecting_signals': detecting_signals,
            })

        result = {
            'session_id': session_id,
            'project': project,
            'size_bytes': size,
            'n_turns': len(turns),
            'n_assistant_turns': ts['n_assistant_turns'],
            'change_points': change_points,
            'transitions': session_transitions,
            'n_total_cps': len(all_cps_for_session),
            'ts_stats': {
                'tool_entropy_mean': float(np.mean(ts['tool_entropy'])),
                'tool_entropy_std': float(np.std(ts['tool_entropy'])),
                'tool_call_rate_mean': float(np.mean(ts['tool_call_rate'])),
                'correction_density_mean': float(np.mean(ts['correction_density'])),
                'user_msg_length_mean': float(np.mean(ts['user_msg_length'])),
            },
        }
        all_results.append(result)
        sessions_processed += 1

    print(f"\nProcessed: {sessions_processed}, Skipped (too short): {sessions_skipped}")
    print()

    # ================================================================
    # ANALYSIS 2 & 3: AGGREGATE RESULTS
    # ================================================================

    print("=" * 70)
    print("ANALYSIS 2: CHANGE POINT DETECTION SUMMARY")
    print("=" * 70)
    print()

    total_cps = sum(r['n_total_cps'] for r in all_results)
    cps_per_session = [r['n_total_cps'] for r in all_results]
    cps_per_100_turns = [r['n_total_cps'] / r['n_assistant_turns'] * 100 for r in all_results if r['n_assistant_turns'] > 0]

    print(f"Total change points detected: {total_cps}")
    print(f"Mean CPs per session: {np.mean(cps_per_session):.1f} (std: {np.std(cps_per_session):.1f})")
    print(f"Median CPs per session: {np.median(cps_per_session):.1f}")
    print(f"Range: {min(cps_per_session)} - {max(cps_per_session)}")
    print(f"Mean CPs per 100 assistant turns: {np.mean(cps_per_100_turns):.1f}")
    print()

    # Per-signal breakdown
    print("Change points by signal type:")
    signal_cp_counts = defaultdict(list)
    for r in all_results:
        for sig, cps in r['change_points'].items():
            signal_cp_counts[sig].append(len(cps))

    for sig in ['tool_entropy', 'user_msg_length', 'correction_density', 'tool_call_rate']:
        counts = signal_cp_counts[sig]
        print(f"  {sig:25s}: total={sum(counts):4d}, mean/session={np.mean(counts):.1f}, "
              f"sessions_with_cps={sum(1 for c in counts if c > 0)}/{len(counts)}")
    print()

    # ================================================================
    # ANALYSIS 3: REGIME TRANSITION CLASSIFICATION
    # ================================================================

    print("=" * 70)
    print("ANALYSIS 3: REGIME TRANSITION CLASSIFICATION")
    print("=" * 70)
    print()

    transition_counts = Counter(t['classification'] for t in all_transitions)
    total_transitions = len(all_transitions)

    print(f"Total classified transitions: {total_transitions}")
    print()
    print(f"{'Transition Type':<25s} {'Count':>6s} {'Pct':>7s}  Description")
    print("-" * 85)

    descriptions = {
        'got_stuck': 'Entropy drops, same tools repeat - agent in a rut',
        'human_redirected': 'Correction spike, then new regime emerges',
        'found_approach': 'Entropy drops + productivity rises - locked in',
        'context_degradation': 'Tool rate drops, message length increases',
        'exploration_burst': 'Entropy + tool rate both increase - searching',
        'settling_down': 'Entropy decreases after exploration phase',
        'acceleration': 'Tool call rate jumps up significantly',
        'deceleration': 'Tool call rate drops significantly',
        'tool_diversification': 'Entropy rises - agent starts using more tool types',
        'tool_specialization': 'Entropy drops - agent focuses on fewer tools',
        'unclassified': 'Signal change not matching known patterns',
    }

    for label, count in transition_counts.most_common():
        pct = count / total_transitions * 100 if total_transitions > 0 else 0
        desc = descriptions.get(label, '')
        print(f"  {label:<23s} {count:>6d} {pct:>6.1f}%  {desc}")
    print()

    # Co-occurrence: which signals fire together
    print("Signal co-occurrence at change points:")
    signal_cooccurrence = Counter()
    for t in all_transitions:
        key = tuple(sorted(t['detecting_signals']))
        signal_cooccurrence[key] += 1

    for combo, count in signal_cooccurrence.most_common(10):
        print(f"  {' + '.join(combo):50s} {count:>4d} ({count/total_transitions*100:.1f}%)")
    print()

    # ================================================================
    # ANALYSIS 4: TEMPORAL DISTRIBUTION
    # ================================================================

    print("=" * 70)
    print("ANALYSIS 4: WHEN DO TRANSITIONS HAPPEN?")
    print("=" * 70)
    print()

    if all_cp_positions:
        positions = np.array(all_cp_positions)

        # Divide into quintiles
        bins = [0, 0.2, 0.4, 0.6, 0.8, 1.0]
        bin_labels = ['0-20% (Early)', '20-40%', '40-60% (Middle)', '60-80%', '80-100% (Late)']

        print("Change point distribution across session lifetime:")
        print()
        total = len(positions)
        for i in range(len(bins) - 1):
            count = np.sum((positions >= bins[i]) & (positions < bins[i+1]))
            pct = count / total * 100
            bar = '#' * int(pct / 2)
            print(f"  {bin_labels[i]:20s}: {count:4d} ({pct:5.1f}%) {bar}")
        print()

        print(f"  Mean position: {np.mean(positions):.3f}")
        print(f"  Median position: {np.median(positions):.3f}")
        print(f"  Std deviation: {np.std(positions):.3f}")
        print()

        # By transition type
        print("Temporal distribution by transition type:")
        print()
        print(f"  {'Type':<25s} {'Mean Pos':>10s} {'Median':>10s} {'Count':>6s}")
        print("  " + "-" * 55)

        type_positions = defaultdict(list)
        for t in all_transitions:
            type_positions[t['classification']].append(t['normalized_position'])

        for label in sorted(type_positions.keys(), key=lambda x: np.mean(type_positions[x])):
            pos = type_positions[label]
            if len(pos) >= 2:
                print(f"  {label:<25s} {np.mean(pos):>10.3f} {np.median(pos):>10.3f} {len(pos):>6d}")
        print()

        # Phase analysis
        early = [t for t in all_transitions if t['normalized_position'] < 0.25]
        middle = [t for t in all_transitions if 0.25 <= t['normalized_position'] < 0.75]
        late = [t for t in all_transitions if t['normalized_position'] >= 0.75]

        print("Dominant transition types by phase:")
        for phase_name, phase_transitions in [('EARLY (0-25%)', early), ('MIDDLE (25-75%)', middle), ('LATE (75-100%)', late)]:
            print(f"\n  {phase_name}:")
            phase_counts = Counter(t['classification'] for t in phase_transitions)
            for label, count in phase_counts.most_common(4):
                pct = count / len(phase_transitions) * 100 if phase_transitions else 0
                print(f"    {label:<23s} {count:>4d} ({pct:5.1f}%)")

    print()

    # ================================================================
    # PER-SESSION DETAILS (top sessions by CP count)
    # ================================================================

    print("=" * 70)
    print("TOP SESSIONS BY CHANGE POINT DENSITY")
    print("=" * 70)
    print()

    sorted_results = sorted(all_results, key=lambda r: r['n_total_cps'] / max(r['n_assistant_turns'], 1), reverse=True)

    for r in sorted_results[:10]:
        density = r['n_total_cps'] / r['n_assistant_turns'] * 100
        print(f"  {r['project'][:30]:<30s} | {r['session_id'][:12]}... | "
              f"turns={r['n_assistant_turns']:>4d} | CPs={r['n_total_cps']:>3d} | "
              f"density={density:.1f}/100turns")
        for t in r['transitions']:
            print(f"    @{t['normalized_position']:.2f}: {t['classification']} "
                  f"(signals: {', '.join(t['detecting_signals'])})")
        print()

    # ================================================================
    # SESSION TIME SERIES STATS
    # ================================================================

    print("=" * 70)
    print("SESSION-LEVEL TIME SERIES STATISTICS")
    print("=" * 70)
    print()

    stats_keys = ['tool_entropy_mean', 'tool_entropy_std', 'tool_call_rate_mean',
                  'correction_density_mean', 'user_msg_length_mean']

    for key in stats_keys:
        values = [r['ts_stats'][key] for r in all_results]
        print(f"  {key:30s}: mean={np.mean(values):.3f}, std={np.std(values):.3f}, "
              f"min={np.min(values):.3f}, max={np.max(values):.3f}")
    print()

    # ================================================================
    # RETURN STRUCTURED DATA FOR REPORT GENERATION
    # ================================================================

    return {
        'sessions_processed': sessions_processed,
        'sessions_skipped': sessions_skipped,
        'total_cps': total_cps,
        'cps_per_session_mean': float(np.mean(cps_per_session)),
        'cps_per_session_median': float(np.median(cps_per_session)),
        'cps_per_100_turns_mean': float(np.mean(cps_per_100_turns)),
        'transition_counts': dict(transition_counts),
        'total_transitions': total_transitions,
        'position_mean': float(np.mean(all_cp_positions)) if all_cp_positions else 0,
        'position_median': float(np.median(all_cp_positions)) if all_cp_positions else 0,
        'position_std': float(np.std(all_cp_positions)) if all_cp_positions else 0,
        'signal_cp_totals': {k: sum(v) for k, v in signal_cp_counts.items()},
        'per_session': all_results,
        'all_transitions': all_transitions,
        'type_positions': {k: {'mean': float(np.mean(v)), 'median': float(np.median(v)), 'count': len(v)}
                          for k, v in type_positions.items() if len(v) >= 2},
    }


if __name__ == '__main__':
    results = main()

    # Save raw results
    output_path = os.path.join(os.environ.get("MIDDENS_OUTPUT", "experiments/"), '018-change-point-results.json')

    # Make JSON-serializable
    serializable = {
        'sessions_processed': results['sessions_processed'],
        'total_cps': results['total_cps'],
        'cps_per_session_mean': results['cps_per_session_mean'],
        'cps_per_session_median': results['cps_per_session_median'],
        'cps_per_100_turns_mean': results['cps_per_100_turns_mean'],
        'transition_counts': results['transition_counts'],
        'total_transitions': results['total_transitions'],
        'position_stats': {
            'mean': results['position_mean'],
            'median': results['position_median'],
            'std': results['position_std'],
        },
        'signal_cp_totals': results['signal_cp_totals'],
        'type_positions': results['type_positions'],
    }

    with open(output_path, 'w') as f:
        json.dump(serializable, f, indent=2)

    print(f"\nResults saved to {output_path}")
