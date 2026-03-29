#!/usr/bin/env python3
"""
Hidden Semi-Markov Model (HSMM) Behavioral State Analysis

Models agent behavior as hidden states (e.g. "exploring", "executing", "stuck",
"recovering") with duration distributions. Unlike a regular HMM, we analyze
how long the agent stays in each state.

Observable emissions: tool call types, message lengths, thinking block presence
Hidden states: 4-6 behavioral states (discovered via fitting)

Uses hmmlearn to fit a GaussianHMM, then decodes most likely state sequences
with Viterbi. Analyzes state transition matrix, mean state durations, and
which states precede corrections.

Source: Claude Code session JSONL files (full corpus)
"""

import json
import glob
import os
import re
import sys
import random
import warnings
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

try:
    from hmmlearn.hmm import GaussianHMM
except ImportError:
    print("Installing hmmlearn...")
    os.system("pip3 install hmmlearn")
    from hmmlearn.hmm import GaussianHMM

warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", category=RuntimeWarning)

# ============================================================
# Configuration
# ============================================================

SESSION_GLOB = os.environ.get("SESSION_GLOB", os.path.join(os.environ.get("MIDDENS_CORPUS", "corpus/"), "**/*.jsonl"))
OUTPUT_DIR = os.environ.get("OUTPUT_DIR", os.environ.get("MIDDENS_OUTPUT", "experiments/"))
MAX_SESSIONS = 200
MIN_TURNS_PER_SESSION = 15
RANDOM_SEED = 42

# Tool type categories for one-hot encoding
TOOL_CATEGORIES = {
    "read": {"Read", "Glob", "Grep"},
    "edit": {"Edit", "Write"},
    "bash": {"Bash"},
    "search": {"WebSearch", "WebFetch", "ToolSearch"},
    "skill": {"Skill"},
    "other_tool": set(),  # catch-all
}

# Correction patterns (from prior experiments)
CORRECTION_PATTERNS = [
    r"^no[,.\s!]",
    r"^wrong", r"^actually[,\s]", r"^why did you",
    r"^don'?t\s", r"^stop\b(?! hook)",
    r"^revert", r"^undo", r"^try again",
    r"^that'?s not", r"^that is not", r"^not what i",
    r"^i said", r"^i meant", r"^i asked",
    r"^wait[,.\s]", r"^hold on", r"^nope",
    r"^incorrect", r"^fix\s", r"^instead[,\s]",
    r"^you (should|need|forgot|missed|broke|didn)",
    r"^please (don|stop|revert|undo|fix)",
    r"^this (is wrong|isn't|doesn't|broke|failed)",
    r"^it (should|shouldn't|doesn't|didn't|broke|failed)",
    r"^that (broke|failed|isn't right|is incorrect)",
    r"\bwrong\b.*\bshould\b",
]
CORRECTION_RE = re.compile("|".join(CORRECTION_PATTERNS), re.IGNORECASE)

CORRECTION_EXCLUSIONS = [
    r"stop hook", r"^#\s", r"^```",
    r"deepen plan", r"power enhancement",
    r"this session is being continued",
    r"^you are \w+, an",
]
CORRECTION_EXCLUSION_RE = re.compile("|".join(CORRECTION_EXCLUSIONS), re.IGNORECASE)

os.makedirs(OUTPUT_DIR, exist_ok=True)


# ============================================================
# Data Loading (follows patterns from burstiness_hawkes.py)
# ============================================================

def extract_user_text(msg):
    """Extract text content from a user message."""
    content = msg.get("message", {}).get("content", "")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                return block["text"].strip()
    return ""


def is_correction(text):
    """Check if user text is a correction."""
    if not text:
        return False
    if text.startswith("[") or text.startswith("<"):
        return False
    if CORRECTION_EXCLUSION_RE.search(text):
        return False
    return bool(CORRECTION_RE.search(text))


def is_tool_result_message(msg):
    """Check if a user message is purely a tool_result."""
    content = msg.get("message", {}).get("content", "")
    if isinstance(content, list):
        has_tool_result = False
        has_human_text = False
        for block in content:
            if isinstance(block, dict):
                if block.get("type") == "tool_result":
                    has_tool_result = True
                elif block.get("type") == "text":
                    text = block.get("text", "").strip()
                    if text and not text.startswith("<") and not text.startswith("["):
                        has_human_text = True
        if has_tool_result and not has_human_text:
            return True
    return False


def detect_tool_failure(msg):
    """Check if a user message contains a tool_result with is_error=True."""
    content = msg.get("message", {}).get("content", "")
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_result":
                if block.get("is_error"):
                    return True
    return False


def has_thinking(msg):
    """Check if assistant message has a thinking block."""
    content = msg.get("message", {}).get("content", [])
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") == "thinking":
                return True
    return False


def get_thinking_length(msg):
    """Get total length of thinking blocks in an assistant message."""
    content = msg.get("message", {}).get("content", [])
    total = 0
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") == "thinking":
                total += len(block.get("thinking", ""))
    return total


def get_text_length(msg):
    """Get total text content length."""
    content = msg.get("message", {}).get("content", [])
    total = 0
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict):
                if block.get("type") == "text":
                    total += len(block.get("text", ""))
            elif isinstance(block, str):
                total += len(block)
    elif isinstance(content, str):
        total = len(content)
    return total


def get_tool_names(msg):
    """Extract all tool names from an assistant message."""
    content = msg.get("message", {}).get("content", [])
    tools = []
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_use":
                tools.append(block.get("name", "unknown"))
    return tools


def categorize_tool(tool_name):
    """Map a tool name to a category index."""
    for i, (cat, names) in enumerate(TOOL_CATEGORIES.items()):
        if tool_name in names:
            return i
    return len(TOOL_CATEGORIES) - 1  # "other_tool"


def is_automated_session(session_path):
    """Check if a session is an automated agent loop."""
    try:
        with open(session_path) as f:
            for line in f:
                try:
                    msg = json.loads(line)
                    if msg.get("type") in ("user", "message"):
                        role = msg.get("message", {}).get("role", msg.get("type", ""))
                        if role == "user":
                            text = extract_user_text(msg)
                            if text and "autonomous agent running in a loop" in text.lower():
                                return True
                            if text and "you are boucle" in text.lower():
                                return True
                            break
                except (json.JSONDecodeError, UnicodeDecodeError):
                    continue
    except Exception:
        return False
    return False


def extract_turns(session_path, max_lines=30000):
    """
    Load a session and extract per-turn feature vectors.

    Each turn (assistant message) produces a feature vector:
    [tool_read, tool_edit, tool_bash, tool_search, tool_skill, tool_other,
     msg_length_bucket, has_thinking, has_correction_after, tool_failure_after,
     num_tools, thinking_length_bucket]
    """
    turns = []
    with open(session_path, 'r') as f:
        for i, line in enumerate(f):
            if i >= max_lines:
                break
            try:
                obj = json.loads(line)
                msg_type = obj.get("type")
                # Handle both formats: type="user"/"assistant" and type="message"
                if msg_type == "message":
                    role = obj.get("message", {}).get("role", "")
                    if role in ("user", "assistant"):
                        obj["type"] = role
                        turns.append(obj)
                elif msg_type in ("user", "assistant"):
                    turns.append(obj)
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue
    return turns


def encode_session(session_path):
    """
    Encode a session as a sequence of feature vectors for HMM fitting.

    Each feature vector represents one assistant "action turn":
    - tool category one-hot (6 dims: read, edit, bash, search, skill, other)
    - message text length (log-scaled, 1 dim)
    - thinking present (1 dim)
    - thinking length (log-scaled, 1 dim)
    - number of tools used (1 dim)
    - correction follows within 2 turns (1 dim)
    - tool failure follows within 2 turns (1 dim)
    Total: 12 features
    """
    raw_turns = extract_turns(session_path)
    if len(raw_turns) < MIN_TURNS_PER_SESSION:
        return None, None

    features = []
    correction_flags = []

    for idx, turn in enumerate(raw_turns):
        if turn.get("type") != "assistant":
            continue

        # Tool category one-hot
        tool_onehot = [0.0] * len(TOOL_CATEGORIES)
        tool_names = get_tool_names(turn)
        for tname in tool_names:
            cat_idx = categorize_tool(tname)
            tool_onehot[cat_idx] = 1.0

        # Message text length (log-scaled)
        text_len = get_text_length(turn)
        log_text_len = np.log1p(text_len)

        # Thinking
        think = 1.0 if has_thinking(turn) else 0.0
        think_len = get_thinking_length(turn)
        log_think_len = np.log1p(think_len)

        # Number of tools
        num_tools = float(len(tool_names))

        # Look ahead for correction/failure within next 2 user turns
        correction_ahead = 0.0
        failure_ahead = 0.0
        lookahead_count = 0
        for j in range(idx + 1, min(idx + 5, len(raw_turns))):
            future_turn = raw_turns[j]
            if future_turn.get("type") == "user":
                lookahead_count += 1
                if lookahead_count > 2:
                    break
                if is_tool_result_message(future_turn):
                    if detect_tool_failure(future_turn):
                        failure_ahead = 1.0
                else:
                    text = extract_user_text(future_turn)
                    if text and is_correction(text):
                        correction_ahead = 1.0

        feature_vec = tool_onehot + [
            log_text_len,
            think,
            log_think_len,
            num_tools,
            correction_ahead,
            failure_ahead,
        ]
        features.append(feature_vec)
        correction_flags.append(correction_ahead)

    if len(features) < 10:
        return None, None

    return np.array(features, dtype=np.float64), correction_flags


def load_sessions(max_n=MAX_SESSIONS):
    """Load sessions with balanced project sampling."""
    files = glob.glob(SESSION_GLOB, recursive=True)
    random.seed(RANDOM_SEED)
    random.shuffle(files)

    # Group by source
    source_files = defaultdict(list)
    for fpath in files:
        parts = fpath.split("/")
        found = False
        for i, p in enumerate(parts):
            if p in ("corpus-full", "interactive", "subagent") and i + 1 < len(parts):
                source_files[parts[i + 1]].append(fpath)
                found = True
                break
        if not found:
            source_files["unknown"].append(fpath)

    sessions = {}
    correction_data = {}
    skipped_auto = 0
    skipped_small = 0

    # Round-robin across sources
    ordered_sources = sorted(source_files.keys(), key=lambda s: len(source_files[s]))
    source_idx = {s: 0 for s in ordered_sources}

    for pass_num in range(20):
        if len(sessions) >= max_n:
            break
        for source in ordered_sources:
            if len(sessions) >= max_n:
                break
            sfiles = source_files[source]
            start = source_idx[source]
            for fpath in sfiles[start:start + 5]:
                if len(sessions) >= max_n:
                    break
                source_idx[source] += 1

                try:
                    if is_automated_session(fpath):
                        skipped_auto += 1
                        continue
                    features, corr_flags = encode_session(fpath)
                except Exception:
                    continue

                if features is None:
                    skipped_small += 1
                    continue

                sid = os.path.basename(fpath).replace(".jsonl", "")
                sessions[sid] = features
                correction_data[sid] = corr_flags

    print(f"  Loaded: {len(sessions)} sessions")
    print(f"  Skipped (automated): {skipped_auto}")
    print(f"  Skipped (too small): {skipped_small}")
    return sessions, correction_data


# ============================================================
# HMM Fitting
# ============================================================

def fit_hmm(sessions, n_states=5, n_iter=100):
    """
    Fit a GaussianHMM to the concatenated session data.
    Returns the fitted model and the per-session state sequences.
    """
    # Concatenate all sessions
    all_features = []
    lengths = []
    session_ids = []

    for sid, features in sessions.items():
        all_features.append(features)
        lengths.append(len(features))
        session_ids.append(sid)

    X = np.vstack(all_features)
    print(f"  Total observation vectors: {X.shape[0]} (features: {X.shape[1]})")
    print(f"  Fitting GaussianHMM with {n_states} hidden states...")

    model = GaussianHMM(
        n_components=n_states,
        covariance_type="diag",
        n_iter=n_iter,
        random_state=RANDOM_SEED,
        verbose=False,
    )
    model.fit(X, lengths)

    print(f"  Converged: {model.monitor_.converged}")
    print(f"  Log-likelihood: {model.score(X, lengths):.1f}")

    # Decode state sequences
    state_sequences = {}
    offset = 0
    for sid, length in zip(session_ids, lengths):
        segment = X[offset:offset + length]
        _, states = model.decode(segment)
        state_sequences[sid] = states
        offset += length

    return model, state_sequences, session_ids


def compute_state_durations(state_sequences):
    """
    Compute duration distributions for each state.
    A 'duration' = number of consecutive turns in the same state.
    This is what makes it semi-Markov: we analyze how long the agent
    stays in each state, not just transition probabilities.
    """
    durations = defaultdict(list)

    for sid, states in state_sequences.items():
        if len(states) == 0:
            continue
        current_state = states[0]
        current_duration = 1
        for i in range(1, len(states)):
            if states[i] == current_state:
                current_duration += 1
            else:
                durations[current_state].append(current_duration)
                current_state = states[i]
                current_duration = 1
        durations[current_state].append(current_duration)

    return durations


def analyze_pre_correction_states(state_sequences, correction_data, sessions, window=3):
    """
    Which hidden states tend to precede user corrections?
    Look at the `window` states immediately before a correction.
    """
    pre_correction_states = Counter()
    all_states = Counter()

    for sid in state_sequences:
        states = state_sequences[sid]
        corr_flags = correction_data.get(sid, [])

        for i, s in enumerate(states):
            all_states[s] += 1

        for i, flag in enumerate(corr_flags):
            if flag > 0.5 and i < len(states):
                # Look at states in the window before this turn
                start = max(0, i - window)
                for j in range(start, i + 1):
                    if j < len(states):
                        pre_correction_states[states[j]] += 1

    return pre_correction_states, all_states


# ============================================================
# BIC Model Selection
# ============================================================

def select_n_states(sessions, candidates=(3, 4, 5, 6, 7)):
    """Use BIC to select optimal number of hidden states."""
    all_features = []
    lengths = []
    for sid, features in sessions.items():
        all_features.append(features)
        lengths.append(len(features))
    X = np.vstack(all_features)

    results = []
    for n in candidates:
        try:
            model = GaussianHMM(
                n_components=n,
                covariance_type="diag",
                n_iter=80,
                random_state=RANDOM_SEED,
                verbose=False,
            )
            model.fit(X, lengths)
            log_likelihood = model.score(X, lengths)
            n_params = n * n + n * X.shape[1] * 2 + n - 1  # transitions + means + vars + start
            bic = -2 * log_likelihood + n_params * np.log(X.shape[0])
            results.append((n, log_likelihood, bic, model.monitor_.converged))
            print(f"    n_states={n}: LL={log_likelihood:.1f}, BIC={bic:.1f}, converged={model.monitor_.converged}")
        except Exception as e:
            print(f"    n_states={n}: FAILED ({e})")
            results.append((n, float("-inf"), float("inf"), False))

    best = min(results, key=lambda x: x[2])
    return best[0], results


# ============================================================
# State Labeling
# ============================================================

FEATURE_NAMES = [
    "tool_read", "tool_edit", "tool_bash", "tool_search", "tool_skill", "tool_other",
    "log_text_len", "has_thinking", "log_thinking_len", "num_tools",
    "correction_ahead", "failure_ahead",
]


def label_states(model, n_states):
    """
    Attempt to assign meaningful labels to discovered states
    based on their emission means.
    """
    means = model.means_
    labels = {}
    for s in range(n_states):
        m = means[s]
        dominant_features = []
        # Check tool usage
        if m[0] > 0.3:
            dominant_features.append("reading")
        if m[1] > 0.3:
            dominant_features.append("editing")
        if m[2] > 0.3:
            dominant_features.append("bash")
        if m[3] > 0.1 or m[4] > 0.1:
            dominant_features.append("searching")
        if m[7] > 0.5:
            dominant_features.append("thinking")
        if m[10] > 0.3:
            dominant_features.append("pre-correction")
        if m[11] > 0.3:
            dominant_features.append("pre-failure")
        if m[9] > 2.0:
            dominant_features.append("multi-tool")
        if m[6] > 6.0:
            dominant_features.append("verbose")

        if not dominant_features:
            dominant_features.append("minimal")

        labels[s] = "+".join(dominant_features)
    return labels


# ============================================================
# Main Analysis
# ============================================================

def main():
    print("=" * 70)
    print("HIDDEN SEMI-MARKOV MODEL: BEHAVIORAL STATE ANALYSIS")
    print("=" * 70)

    # Step 1: Load sessions
    print("\n[1/5] Loading sessions...")
    sessions, correction_data = load_sessions(MAX_SESSIONS)
    if len(sessions) < 10:
        print("ERROR: Too few sessions loaded. Aborting.")
        sys.exit(1)

    # Step 2: Model selection via BIC
    print("\n[2/5] Selecting optimal number of hidden states (BIC)...")
    best_n, bic_results = select_n_states(sessions, candidates=(3, 4, 5, 6, 7))
    print(f"\n  Best number of states: {best_n}")

    # Step 3: Fit final model
    print(f"\n[3/5] Fitting final model with {best_n} states...")
    model, state_sequences, session_ids = fit_hmm(sessions, n_states=best_n)

    # Step 4: Analyze states
    print("\n[4/5] Analyzing behavioral states...")

    # Transition matrix
    transmat = model.transmat_
    state_labels = label_states(model, best_n)

    # Duration distributions (the "semi-Markov" part)
    durations = compute_state_durations(state_sequences)

    # Pre-correction state analysis
    pre_corr, all_states = analyze_pre_correction_states(
        state_sequences, correction_data, sessions
    )

    # Step 5: Output results
    print("\n[5/5] Writing results...")

    output_lines = []
    output_lines.append("=" * 70)
    output_lines.append("HIDDEN SEMI-MARKOV MODEL: BEHAVIORAL STATE ANALYSIS")
    output_lines.append("=" * 70)
    output_lines.append(f"\nSessions analyzed: {len(sessions)}")
    output_lines.append(f"Total observation vectors: {sum(len(f) for f in sessions.values())}")
    output_lines.append(f"Optimal hidden states (BIC): {best_n}")
    output_lines.append(f"Model converged: {model.monitor_.converged}")
    output_lines.append(f"Log-likelihood: {model.score(np.vstack([sessions[s] for s in session_ids]), [len(sessions[s]) for s in session_ids]):.1f}")

    # BIC table
    output_lines.append("\n--- BIC Model Selection ---")
    output_lines.append(f"{'States':<10} {'Log-Likelihood':<18} {'BIC':<15} {'Converged'}")
    for n, ll, bic, conv in bic_results:
        output_lines.append(f"{n:<10} {ll:<18.1f} {bic:<15.1f} {conv}")

    # State descriptions
    output_lines.append("\n--- Hidden State Descriptions ---")
    for s in range(best_n):
        m = model.means_[s]
        label = state_labels[s]
        output_lines.append(f"\nState {s} [{label}]:")
        output_lines.append(f"  Emission means:")
        for j, fname in enumerate(FEATURE_NAMES):
            output_lines.append(f"    {fname:<22s}: {m[j]:.3f}")

    # Transition matrix
    output_lines.append("\n--- State Transition Matrix ---")
    header = "From\\To  " + "  ".join(f"S{s}" for s in range(best_n))
    output_lines.append(header)
    for s_from in range(best_n):
        row = f"  S{s_from}     " + "  ".join(
            f"{transmat[s_from][s_to]:.3f}" for s_to in range(best_n)
        )
        output_lines.append(row)

    # Self-transition probabilities (persistence)
    output_lines.append("\n--- State Self-Transition (Persistence) ---")
    for s in range(best_n):
        output_lines.append(f"  State {s} [{state_labels[s]}]: P(stay) = {transmat[s][s]:.3f}")

    # Duration distributions (HSMM key output)
    output_lines.append("\n--- State Duration Distributions (Semi-Markov) ---")
    for s in sorted(durations.keys()):
        durs = durations[s]
        if not durs:
            continue
        arr = np.array(durs)
        output_lines.append(f"\nState {s} [{state_labels[s]}]:")
        output_lines.append(f"  Count of runs: {len(durs)}")
        output_lines.append(f"  Mean duration: {arr.mean():.2f} turns")
        output_lines.append(f"  Median duration: {np.median(arr):.1f} turns")
        output_lines.append(f"  Std duration: {arr.std():.2f} turns")
        output_lines.append(f"  Max duration: {arr.max()} turns")
        # Distribution of durations
        dur_counts = Counter(durs)
        sorted_durs = sorted(dur_counts.items())
        dist_str = ", ".join(f"{d}:{c}" for d, c in sorted_durs[:15])
        output_lines.append(f"  Distribution (dur:count): {dist_str}")

    # Pre-correction states
    output_lines.append("\n--- States Preceding Corrections ---")
    total_corr_states = sum(pre_corr.values())
    total_all_states = sum(all_states.values())
    if total_corr_states > 0 and total_all_states > 0:
        output_lines.append(f"Total pre-correction state observations: {total_corr_states}")
        output_lines.append(f"{'State':<8} {'Label':<30} {'Pre-Corr %':<12} {'Base %':<12} {'Lift'}")
        for s in range(best_n):
            pre_pct = pre_corr.get(s, 0) / total_corr_states * 100
            base_pct = all_states.get(s, 0) / total_all_states * 100
            lift = pre_pct / base_pct if base_pct > 0 else 0
            output_lines.append(
                f"  S{s:<5} {state_labels[s]:<30} {pre_pct:<12.1f} {base_pct:<12.1f} {lift:.2f}x"
            )
    else:
        output_lines.append("  Insufficient correction data for analysis.")

    # Starting state distribution
    output_lines.append("\n--- Starting State Distribution ---")
    startprob = model.startprob_
    for s in range(best_n):
        output_lines.append(f"  State {s} [{state_labels[s]}]: P(start) = {startprob[s]:.3f}")

    # Most common state transition paths (bigrams)
    output_lines.append("\n--- Most Common State Transition Bigrams ---")
    bigram_counts = Counter()
    for sid, states in state_sequences.items():
        for i in range(len(states) - 1):
            bigram_counts[(states[i], states[i + 1])] += 1
    for (s1, s2), count in bigram_counts.most_common(15):
        output_lines.append(
            f"  S{s1} [{state_labels[s1]}] -> S{s2} [{state_labels[s2]}]: {count}"
        )

    # Session-level state composition
    output_lines.append("\n--- Average Session State Composition ---")
    session_compositions = []
    for sid, states in state_sequences.items():
        comp = Counter(states)
        total = len(states)
        pcts = {s: comp.get(s, 0) / total for s in range(best_n)}
        session_compositions.append(pcts)

    for s in range(best_n):
        pcts = [sc.get(s, 0) for sc in session_compositions]
        arr = np.array(pcts)
        output_lines.append(
            f"  State {s} [{state_labels[s]}]: "
            f"mean={arr.mean():.1%}, median={np.median(arr):.1%}, "
            f"std={arr.std():.1%}"
        )

    # State sequences at session boundaries
    output_lines.append("\n--- State Distribution by Session Position ---")
    n_buckets = 5
    bucket_names = ["Start (0-20%)", "Early (20-40%)", "Middle (40-60%)", "Late (60-80%)", "End (80-100%)"]
    bucket_counts = [Counter() for _ in range(n_buckets)]
    for sid, states in state_sequences.items():
        n = len(states)
        for i, s in enumerate(states):
            bucket = min(int(i / n * n_buckets), n_buckets - 1)
            bucket_counts[bucket][s] += 1

    for b in range(n_buckets):
        total_b = sum(bucket_counts[b].values())
        if total_b == 0:
            continue
        output_lines.append(f"\n  {bucket_names[b]}:")
        for s in range(best_n):
            pct = bucket_counts[b].get(s, 0) / total_b * 100
            bar = "#" * int(pct / 2)
            output_lines.append(f"    S{s} [{state_labels[s]:<25s}]: {pct:5.1f}% {bar}")

    # Write output
    report = "\n".join(output_lines)
    print(report)

    output_path = os.path.join(OUTPUT_DIR, "hsmm_behavioral_states.txt")
    with open(output_path, "w") as f:
        f.write(report)
    print(f"\nResults written to: {output_path}")

    # Save transition matrix as CSV
    csv_path = os.path.join(OUTPUT_DIR, "hsmm_transition_matrix.csv")
    with open(csv_path, "w") as f:
        f.write("," + ",".join(f"S{s}_{state_labels[s]}" for s in range(best_n)) + "\n")
        for s_from in range(best_n):
            f.write(f"S{s_from}_{state_labels[s_from]}," +
                    ",".join(f"{transmat[s_from][s_to]:.4f}" for s_to in range(best_n)) + "\n")
    print(f"Transition matrix: {csv_path}")

    # Save duration distributions as CSV
    dur_csv_path = os.path.join(OUTPUT_DIR, "hsmm_state_durations.csv")
    with open(dur_csv_path, "w") as f:
        f.write("state,label,duration\n")
        for s in sorted(durations.keys()):
            for d in durations[s]:
                f.write(f"{s},{state_labels[s]},{d}\n")
    print(f"Duration data: {dur_csv_path}")


if __name__ == "__main__":
    main()
