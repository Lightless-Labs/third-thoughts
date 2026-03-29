#!/usr/bin/env python3
"""
Experiment 016: Genomics-Inspired Sequence Analysis of Claude Code Sessions

Applies bioinformatics techniques to session transcripts:
  1. Smith-Waterman local alignment to find conserved subsequences
  2. Motif discovery with statistical significance testing
  3. Phylogenetic clustering from alignment-based distances

Uses the same symbol encoding as experiment 011 (NCD clustering).
"""

import json
import os
import sys
import random
from collections import Counter, defaultdict
from pathlib import Path
from itertools import combinations

import numpy as np
from scipy.cluster.hierarchy import linkage, fcluster, dendrogram
from scipy.spatial.distance import squareform
from scipy.stats import fisher_exact, chi2_contingency

random.seed(42)
np.random.seed(42)

# ─── Configuration ───────────────────────────────────────────────────────────

CORPUS_DIR = os.environ.get("MIDDENS_CORPUS", "corpus/")
MIN_EVENTS = 20  # need enough substance for alignment
TARGET_SESSIONS = 100  # sample ~100 sessions from full corpus
OUTPUT_DIR = os.environ.get("MIDDENS_OUTPUT", "experiments/")

# Smith-Waterman parameters
SW_MATCH = 2
SW_MISMATCH = -1
SW_GAP = -1

# Motif parameters
MOTIF_K_RANGE = range(3, 7)  # k=3 to k=6
CORRECTION_THRESHOLD_LOW = 0.05   # bottom quintile = "successful"
CORRECTION_THRESHOLD_HIGH = 0.20  # top quintile = "high correction"

# ─── Symbol Stream Encoding (same as 011) ────────────────────────────────────

TOOL_MAP = {
    "Read": "Tr", "Edit": "Te", "Write": "Tw", "Bash": "Tb",
    "Grep": "Tg", "Glob": "Tf", "Skill": "Ts",
    "WebSearch": "Tn", "WebFetch": "Tn", "NotebookEdit": "Tj",
    "StructuredOutput": "To", "ToolSearch": "Td",
}

# For alignment: map each symbol to a unique integer
SYMBOL_VOCAB = {}
SYMBOL_NAMES = []

def get_symbol_id(sym):
    if sym not in SYMBOL_VOCAB:
        SYMBOL_VOCAB[sym] = len(SYMBOL_VOCAB)
        SYMBOL_NAMES.append(sym)
    return SYMBOL_VOCAB[sym]


def classify_user_length(text_len):
    if text_len < 100:
        return "short"
    elif text_len < 500:
        return "medium"
    else:
        return "long"


def extract_symbol_stream(filepath):
    """Convert a JSONL session file into a symbol stream."""
    symbols = []

    with open(filepath) as f:
        for line in f:
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue

            msg_type = obj.get("type")

            if msg_type == "user":
                msg = obj.get("message", {})
                content = msg.get("content", "")

                if isinstance(content, list):
                    has_tool_result = any(
                        isinstance(b, dict) and b.get("type") == "tool_result"
                        for b in content
                    )
                    if has_tool_result:
                        symbols.append("R")
                        continue
                    text_parts = []
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "text":
                            text_parts.append(block.get("text", ""))
                        elif isinstance(block, str):
                            text_parts.append(block)
                    text = " ".join(text_parts)
                elif isinstance(content, str):
                    text = content
                else:
                    text = ""

                if obj.get("isMeta"):
                    continue

                bucket = classify_user_length(len(text))
                symbols.append(f"U{bucket[0]}")

            elif msg_type == "assistant":
                msg = obj.get("message", {})
                content = msg.get("content", [])

                if isinstance(content, list):
                    for block in content:
                        if not isinstance(block, dict):
                            continue
                        btype = block.get("type")
                        if btype == "text":
                            symbols.append("At")
                        elif btype == "thinking":
                            symbols.append("Ak")
                        elif btype == "tool_use":
                            tool_name = block.get("name", "X")
                            if tool_name.startswith("mcp__"):
                                symbols.append("Tm")
                            else:
                                symbols.append(TOOL_MAP.get(tool_name, "Tx"))
                elif isinstance(content, str) and content:
                    symbols.append("At")

    return symbols


def compute_correction_rate(filepath):
    """
    Estimate correction rate using multiple signals:
    1. User corrections (short messages with correction keywords after assistant output)
    2. Agent self-correction (repeated Edit calls to same-ish target)
    3. Bash retry patterns (Bash following error-containing results)
    4. Read-after-Edit patterns (re-reading files just edited = verification/fix)

    Returns a composite score from 0 (smooth) to ~1 (heavy correction).
    """
    entries = []
    with open(filepath) as f:
        for line in f:
            try:
                entries.append(json.loads(line))
            except:
                continue

    user_msgs = 0
    corrections = 0
    edit_runs = 0
    total_edits = 0
    bash_retries = 0
    total_bash = 0
    read_after_edit = 0

    prev_was_assistant_text = False
    prev_was_edit = False
    prev_was_bash_error = False
    prev_tool = None

    for obj in entries:
        msg_type = obj.get("type")

        if msg_type == "user":
            msg = obj.get("message", {})
            content = msg.get("content", "")

            if isinstance(content, list):
                has_tool_result = any(
                    isinstance(b, dict) and b.get("type") == "tool_result"
                    for b in content
                )
                if has_tool_result:
                    # Check for error results (bash failures)
                    for b in content:
                        if isinstance(b, dict) and b.get("type") == "tool_result":
                            result_content = b.get("content", "")
                            if isinstance(result_content, str):
                                lower_r = result_content.lower()
                                if any(kw in lower_r for kw in [
                                    "error", "traceback", "failed", "not found",
                                    "permission denied", "command not found",
                                    "no such file", "syntax error"
                                ]):
                                    prev_was_bash_error = True
                    prev_was_assistant_text = False
                    prev_was_edit = False
                    continue
                text_parts = []
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        text_parts.append(block.get("text", ""))
                    elif isinstance(block, str):
                        text_parts.append(block)
                text = " ".join(text_parts)
            elif isinstance(content, str):
                text = content
            else:
                text = ""

            if obj.get("isMeta"):
                continue

            user_msgs += 1

            # Heuristic: short message after assistant output = likely correction/steering
            if prev_was_assistant_text and len(text) < 200:
                lower = text.lower()
                correction_words = [
                    "no", "wrong", "fix", "actually", "instead", "don't",
                    "that's not", "try again", "redo", "not what", "should be",
                    "change", "wait", "stop", "revert", "undo", "but",
                    "nope", "incorrect", "that broke", "doesn't work",
                    "still broken", "try", "hmm", "not right",
                ]
                if any(w in lower for w in correction_words):
                    corrections += 1

            prev_was_assistant_text = False
            prev_was_edit = False

        elif msg_type == "assistant":
            msg = obj.get("message", {})
            content = msg.get("content", [])
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict):
                        if block.get("type") == "text":
                            prev_was_assistant_text = True
                        if block.get("type") == "tool_use":
                            tool_name = block.get("name", "")
                            if tool_name == "Edit":
                                total_edits += 1
                                if prev_was_edit:
                                    edit_runs += 1
                                prev_was_edit = True
                            else:
                                prev_was_edit = False

                            if tool_name == "Bash":
                                total_bash += 1
                                if prev_was_bash_error:
                                    bash_retries += 1
                                prev_was_bash_error = False

                            if tool_name == "Read" and prev_tool == "Edit":
                                read_after_edit += 1

                            prev_tool = tool_name

    total_events = max(len(entries), 1)

    # Composite correction rate from multiple signals
    user_correction_rate = corrections / max(user_msgs, 1)
    edit_correction_rate = edit_runs / max(total_edits, 1) if total_edits > 3 else 0
    bash_retry_rate = bash_retries / max(total_bash, 1) if total_bash > 3 else 0

    # Weighted combination
    composite = (
        0.40 * user_correction_rate +
        0.30 * edit_correction_rate +
        0.30 * bash_retry_rate
    )

    return composite


# ─── Step 1: Load Sessions ──────────────────────────────────────────────────

def find_all_sessions(corpus_dir):
    """Walk the corpus directory tree and find all top-level JSONL session files."""
    results = []
    for dirpath, dirnames, filenames in os.walk(corpus_dir, followlinks=True):
        if "subagents" in dirpath:
            continue
        for fname in filenames:
            if fname.endswith(".jsonl"):
                filepath = os.path.join(dirpath, fname)
                project = os.path.basename(dirpath)
                results.append((filepath, project))
    return results


def load_sessions():
    """Load and encode sessions from the Third Thoughts corpus."""
    sessions = []

    found = find_all_sessions(CORPUS_DIR)
    project_dirs = set(proj for _, proj in found)
    print(f"Found {len(project_dirs)} project directories, {len(found)} session files")

    for filepath, proj_name in found:
        session_id = Path(filepath).stem

        symbols = extract_symbol_stream(filepath)

        if len(symbols) < MIN_EVENTS:
            continue

        correction_rate = compute_correction_rate(filepath)

        sessions.append({
            "id": session_id,
            "project": proj_name,
            "filepath": filepath,
            "symbols": symbols,
            "length": len(symbols),
            "correction_rate": correction_rate,
        })

    print(f"Loaded {len(sessions)} sessions with >= {MIN_EVENTS} events")

    # Sample if needed — balanced across projects
    if len(sessions) > TARGET_SESSIONS:
        by_project = defaultdict(list)
        for s in sessions:
            by_project[s["project"]].append(s)

        selected = []
        n_projects = len(by_project)

        # Cap per project: no more than ~25% of target from one project
        max_per_project = max(3, TARGET_SESSIONS // 4)

        # Round 1: give each project up to max_per_project sessions
        for proj, proj_sessions in sorted(by_project.items()):
            n_take = min(max_per_project, len(proj_sessions))
            # Stratify within project: pick diverse lengths
            proj_sessions.sort(key=lambda s: s["length"])
            if n_take >= len(proj_sessions):
                selected.extend(proj_sessions)
            else:
                # Evenly spaced selection for length diversity
                indices = np.linspace(0, len(proj_sessions) - 1, n_take, dtype=int)
                selected.extend([proj_sessions[i] for i in indices])

        # If still over target, trim the largest project contributions
        if len(selected) > TARGET_SESSIONS:
            # Randomly remove excess, preferring to keep project diversity
            selected_ids = set(s["id"] for s in selected)
            proj_counts = Counter(s["project"] for s in selected)
            while len(selected) > TARGET_SESSIONS:
                # Remove from most-represented project
                biggest_proj = proj_counts.most_common(1)[0][0]
                # Find and remove one random session from that project
                candidates = [i for i, s in enumerate(selected) if s["project"] == biggest_proj]
                if len(candidates) <= 1:
                    break
                idx = random.choice(candidates)
                selected.pop(idx)
                proj_counts[biggest_proj] -= 1

        # If under target, fill from remaining
        remaining = [s for s in sessions if s["id"] not in {ss["id"] for ss in selected}]
        random.shuffle(remaining)
        while len(selected) < TARGET_SESSIONS and remaining:
            selected.append(remaining.pop())

        sessions = selected[:TARGET_SESSIONS]

    print(f"Selected {len(sessions)} sessions for analysis")
    return sessions


# ─── Analysis 1: Smith-Waterman Local Alignment ─────────────────────────────

def smith_waterman(seq1, seq2, match=SW_MATCH, mismatch=SW_MISMATCH, gap=SW_GAP,
                   max_len=500):
    """
    Simplified Smith-Waterman local alignment.
    Returns (score, aligned_subseq1, aligned_subseq2, traceback_path).

    For efficiency, truncates long sequences to max_len from the middle
    (keeping start and end context).
    """
    def truncate(seq):
        if len(seq) <= max_len:
            return seq
        half = max_len // 2
        return seq[:half] + seq[-half:]

    s1 = truncate(seq1)
    s2 = truncate(seq2)

    n, m = len(s1), len(s2)

    # Score matrix
    H = np.zeros((n + 1, m + 1), dtype=np.int32)
    # Traceback: 0=stop, 1=diag, 2=up, 3=left
    trace = np.zeros((n + 1, m + 1), dtype=np.int8)

    max_score = 0
    max_pos = (0, 0)

    for i in range(1, n + 1):
        for j in range(1, m + 1):
            s = match if s1[i-1] == s2[j-1] else mismatch

            diag = H[i-1, j-1] + s
            up = H[i-1, j] + gap
            left = H[i, j-1] + gap

            H[i, j] = max(0, diag, up, left)

            if H[i, j] == 0:
                trace[i, j] = 0
            elif H[i, j] == diag:
                trace[i, j] = 1
            elif H[i, j] == up:
                trace[i, j] = 2
            else:
                trace[i, j] = 3

            if H[i, j] > max_score:
                max_score = H[i, j]
                max_pos = (i, j)

    # Traceback
    aligned1 = []
    aligned2 = []
    i, j = max_pos
    while i > 0 and j > 0 and H[i, j] > 0:
        if trace[i, j] == 1:  # diagonal
            aligned1.append(s1[i-1])
            aligned2.append(s2[j-1])
            i -= 1
            j -= 1
        elif trace[i, j] == 2:  # up
            aligned1.append(s1[i-1])
            aligned2.append("-")
            i -= 1
        elif trace[i, j] == 3:  # left
            aligned1.append("-")
            aligned2.append(s2[j-1])
            j -= 1
        else:
            break

    aligned1.reverse()
    aligned2.reverse()

    return max_score, aligned1, aligned2


def normalized_alignment_score(seq1, seq2, **kwargs):
    """
    Normalized alignment score: SW_score / max(len_shorter * match_score, 1).
    Ranges from 0 (no similarity) to ~1 (high local similarity).
    """
    score, _, _ = smith_waterman(seq1, seq2, **kwargs)
    max_possible = min(len(seq1), len(seq2)) * SW_MATCH
    if max_possible == 0:
        return 0.0
    return score / max_possible


def alignment_distance(seq1, seq2, **kwargs):
    """Convert normalized alignment score to distance: 1 - normalized_score."""
    return 1.0 - normalized_alignment_score(seq1, seq2, **kwargs)


def run_alignment_analysis(sessions):
    """Find conserved subsequences across session pairs."""
    print("\n" + "=" * 70)
    print("ANALYSIS 1: Smith-Waterman Local Alignment")
    print("=" * 70)

    n = len(sessions)
    # Compute pairwise alignment scores
    score_matrix = np.zeros((n, n))
    dist_matrix = np.zeros((n, n))

    # Also track best alignments for reporting
    best_alignments = []

    total_pairs = n * (n - 1) // 2
    pair_count = 0

    for i in range(n):
        for j in range(i + 1, n):
            pair_count += 1
            if pair_count % 100 == 0:
                print(f"  Aligning pair {pair_count}/{total_pairs}...", end="\r")

            score, a1, a2 = smith_waterman(sessions[i]["symbols"], sessions[j]["symbols"])
            max_possible = min(
                min(len(sessions[i]["symbols"]), 500),
                min(len(sessions[j]["symbols"]), 500)
            ) * SW_MATCH
            norm_score = score / max_possible if max_possible > 0 else 0

            score_matrix[i, j] = norm_score
            score_matrix[j, i] = norm_score
            dist_matrix[i, j] = 1 - norm_score
            dist_matrix[j, i] = 1 - norm_score

            if len(a1) >= 5:
                best_alignments.append({
                    "i": i, "j": j,
                    "score": score,
                    "norm_score": norm_score,
                    "aligned1": a1,
                    "aligned2": a2,
                    "len": len(a1),
                    "id_i": sessions[i]["id"][:12],
                    "id_j": sessions[j]["id"][:12],
                    "proj_i": sessions[i]["project"],
                    "proj_j": sessions[j]["project"],
                })

    print(f"\n  Completed {total_pairs} pairwise alignments")

    # Statistics
    upper_tri = score_matrix[np.triu_indices(n, k=1)]
    print(f"\n  Normalized alignment scores:")
    print(f"    Mean: {np.mean(upper_tri):.4f}")
    print(f"    Median: {np.median(upper_tri):.4f}")
    print(f"    Std: {np.std(upper_tri):.4f}")
    print(f"    Range: [{np.min(upper_tri):.4f}, {np.max(upper_tri):.4f}]")

    # Top conserved subsequences
    best_alignments.sort(key=lambda x: x["score"], reverse=True)

    print(f"\n  Top 15 highest-scoring local alignments:")
    seen_patterns = set()
    reported = 0
    for a in best_alignments:
        if reported >= 15:
            break
        # Deduplicate near-identical patterns
        pattern_key = " ".join(a["aligned1"][:10])
        if pattern_key in seen_patterns:
            continue
        seen_patterns.add(pattern_key)

        matches = sum(1 for x, y in zip(a["aligned1"], a["aligned2"]) if x == y)
        identity = matches / len(a["aligned1"]) if a["aligned1"] else 0

        print(f"\n    #{reported+1}: score={a['score']}, norm={a['norm_score']:.3f}, "
              f"len={a['len']}, identity={identity:.1%}")
        print(f"        {a['proj_i']} ({a['id_i']}) vs {a['proj_j']} ({a['id_j']})")
        # Show the conserved pattern (first 30 symbols)
        display_len = min(30, len(a["aligned1"]))
        seq_display = " ".join(a["aligned1"][:display_len])
        if display_len < len(a["aligned1"]):
            seq_display += "..."
        print(f"        Pattern: {seq_display}")
        reported += 1

    # Find the most common conserved motifs from alignments
    conserved_motifs = Counter()
    for a in best_alignments[:200]:
        # Extract matched (identical) regions
        matched = []
        for x, y in zip(a["aligned1"], a["aligned2"]):
            if x == y and x != "-":
                matched.append(x)
            else:
                if len(matched) >= 3:
                    for k in range(3, min(7, len(matched) + 1)):
                        for start in range(len(matched) - k + 1):
                            motif = tuple(matched[start:start+k])
                            conserved_motifs[motif] += 1
                matched = []
        if len(matched) >= 3:
            for k in range(3, min(7, len(matched) + 1)):
                for start in range(len(matched) - k + 1):
                    motif = tuple(matched[start:start+k])
                    conserved_motifs[motif] += 1

    print(f"\n  Most frequently conserved motifs (from alignment matches):")
    for motif, count in conserved_motifs.most_common(25):
        print(f"    {' '.join(motif)}: {count}")

    # Cross-project vs within-project alignment scores
    cross_scores = []
    within_scores = []
    for i in range(n):
        for j in range(i + 1, n):
            if sessions[i]["project"] == sessions[j]["project"]:
                within_scores.append(score_matrix[i, j])
            else:
                cross_scores.append(score_matrix[i, j])

    print(f"\n  Within-project alignment: mean={np.mean(within_scores):.4f}, "
          f"n={len(within_scores)}") if within_scores else None
    print(f"  Cross-project alignment:  mean={np.mean(cross_scores):.4f}, "
          f"n={len(cross_scores)}") if cross_scores else None

    return score_matrix, dist_matrix, best_alignments, conserved_motifs


# ─── Analysis 2: Motif Discovery ────────────────────────────────────────────

def extract_kmers(symbols, k):
    """Extract all k-mers from a symbol stream."""
    kmers = []
    for i in range(len(symbols) - k + 1):
        kmers.append(tuple(symbols[i:i+k]))
    return kmers


def run_motif_analysis(sessions):
    """Find over-represented motifs in low vs high correction sessions."""
    print("\n" + "=" * 70)
    print("ANALYSIS 2: Motif Discovery")
    print("=" * 70)

    # Split sessions by correction rate
    correction_rates = [s["correction_rate"] for s in sessions]
    p20 = np.percentile(correction_rates, 25)
    p80 = np.percentile(correction_rates, 75)

    low_correction = [s for s in sessions if s["correction_rate"] <= p20]
    high_correction = [s for s in sessions if s["correction_rate"] >= p80]
    # Make sure groups don't overlap when percentiles are equal
    if p20 == p80:
        sorted_sessions = sorted(sessions, key=lambda s: s["correction_rate"])
        n_quarter = len(sessions) // 4
        low_correction = sorted_sessions[:n_quarter]
        high_correction = sorted_sessions[-n_quarter:]

    print(f"\n  Correction rate distribution:")
    print(f"    Mean: {np.mean(correction_rates):.4f}")
    print(f"    Median: {np.median(correction_rates):.4f}")
    print(f"    P25: {p20:.4f}, P75: {p80:.4f}")
    print(f"    Low-correction group: {len(low_correction)} sessions (rate <= {p20:.4f})")
    print(f"    High-correction group: {len(high_correction)} sessions (rate >= {p80:.4f})")

    results_by_k = {}

    for k in MOTIF_K_RANGE:
        print(f"\n  --- k={k} ---")

        # Count motifs in each group (normalized per session)
        low_motif_counts = Counter()
        high_motif_counts = Counter()
        low_total = 0
        high_total = 0

        for s in low_correction:
            kmers = extract_kmers(s["symbols"], k)
            low_motif_counts.update(kmers)
            low_total += len(kmers)

        for s in high_correction:
            kmers = extract_kmers(s["symbols"], k)
            high_motif_counts.update(kmers)
            high_total += len(kmers)

        # All unique motifs
        all_motifs = set(low_motif_counts.keys()) | set(high_motif_counts.keys())

        # Statistical testing
        enriched_low = []
        enriched_high = []

        for motif in all_motifs:
            a = low_motif_counts.get(motif, 0)  # motif in low-correction
            b = low_total - a                    # non-motif in low-correction
            c = high_motif_counts.get(motif, 0)  # motif in high-correction
            d = high_total - c                   # non-motif in high-correction

            # Skip very rare motifs
            if a + c < 5:
                continue

            # Fisher's exact test
            try:
                odds_ratio, p_value = fisher_exact([[a, b], [c, d]])
            except:
                continue

            low_freq = a / low_total if low_total > 0 else 0
            high_freq = c / high_total if high_total > 0 else 0

            entry = {
                "motif": motif,
                "low_count": a,
                "high_count": c,
                "low_freq": low_freq,
                "high_freq": high_freq,
                "odds_ratio": odds_ratio,
                "p_value": p_value,
                "log2_fold_change": np.log2(low_freq / high_freq) if high_freq > 0 and low_freq > 0 else float('inf'),
            }

            if odds_ratio > 1 and p_value < 0.05:
                enriched_low.append(entry)
            elif odds_ratio < 1 and p_value < 0.05:
                enriched_high.append(entry)

        enriched_low.sort(key=lambda x: x["p_value"])
        enriched_high.sort(key=lambda x: x["p_value"])

        print(f"    Total unique {k}-mers: {len(all_motifs)}")
        print(f"    Enriched in low-correction (p<0.05): {len(enriched_low)}")
        print(f"    Enriched in high-correction (p<0.05): {len(enriched_high)}")

        if enriched_low:
            print(f"\n    Top motifs enriched in LOW-correction (successful) sessions:")
            for e in enriched_low[:10]:
                motif_str = " ".join(e["motif"])
                print(f"      {motif_str}: OR={e['odds_ratio']:.2f}, p={e['p_value']:.4f}, "
                      f"low={e['low_freq']:.4f}, high={e['high_freq']:.4f}")

        if enriched_high:
            print(f"\n    Top motifs enriched in HIGH-correction (struggling) sessions:")
            for e in enriched_high[:10]:
                motif_str = " ".join(e["motif"])
                print(f"      {motif_str}: OR={e['odds_ratio']:.2f}, p={e['p_value']:.4f}, "
                      f"low={e['low_freq']:.4f}, high={e['high_freq']:.4f}")

        results_by_k[k] = {
            "enriched_low": enriched_low,
            "enriched_high": enriched_high,
            "total_motifs": len(all_motifs),
            "low_total_kmers": low_total,
            "high_total_kmers": high_total,
        }

    return results_by_k, low_correction, high_correction


# ─── Analysis 3: Phylogenetic Clustering ─────────────────────────────────────

def run_phylogenetic_clustering(sessions, dist_matrix):
    """Build dendrogram from alignment distances."""
    print("\n" + "=" * 70)
    print("ANALYSIS 3: Phylogenetic Clustering")
    print("=" * 70)

    n = len(sessions)

    # Ensure distance matrix is valid
    np.fill_diagonal(dist_matrix, 0)
    # Symmetrize
    dist_matrix = (dist_matrix + dist_matrix.T) / 2
    # Clip to valid range
    dist_matrix = np.clip(dist_matrix, 0, 1)

    # Convert to condensed form
    condensed = squareform(dist_matrix)

    # Hierarchical clustering with different linkage methods
    results = {}
    for method in ["average", "complete", "ward"]:
        try:
            if method == "ward":
                # Ward needs the distance matrix differently
                Z = linkage(condensed, method="ward")
            else:
                Z = linkage(condensed, method=method)

            # Cut at different thresholds
            for n_clusters in [5, 7, 9]:
                labels = fcluster(Z, n_clusters, criterion="maxclust")
                results[f"{method}_k{n_clusters}"] = labels

            results[f"{method}_linkage"] = Z
        except Exception as e:
            print(f"  Warning: {method} linkage failed: {e}")

    # Use average linkage as primary
    primary_method = "average"
    Z = results.get(f"{primary_method}_linkage")

    if Z is None:
        print("  ERROR: Could not compute linkage")
        return {}

    # Determine optimal cluster count using silhouette-like metric
    best_k = 7
    primary_labels = fcluster(Z, best_k, criterion="maxclust")

    print(f"\n  Linkage method: {primary_method}")
    print(f"  Number of clusters: {best_k}")

    # Cluster summary
    cluster_members = defaultdict(list)
    for i, label in enumerate(primary_labels):
        cluster_members[label].append(i)

    print(f"\n  Cluster sizes:")
    for cl in sorted(cluster_members.keys()):
        members = cluster_members[cl]
        projects = [sessions[i]["project"] for i in members]
        proj_counts = Counter(projects)
        lengths = [sessions[i]["length"] for i in members]
        corr_rates = [sessions[i]["correction_rate"] for i in members]

        print(f"\n    Cluster {cl} ({len(members)} sessions):")
        print(f"      Length: mean={np.mean(lengths):.0f}, "
              f"range=[{min(lengths)}, {max(lengths)}]")
        print(f"      Correction rate: mean={np.mean(corr_rates):.4f}")
        print(f"      Projects: {dict(proj_counts.most_common(5))}")

        # Show structural profile
        all_symbols = []
        for i in members:
            all_symbols.extend(sessions[i]["symbols"])
        sym_counts = Counter(all_symbols)
        total = len(all_symbols)
        top_syms = sym_counts.most_common(6)
        sym_str = ", ".join(f"{s}:{c/total:.1%}" for s, c in top_syms)
        print(f"      Top symbols: {sym_str}")

    # Build text dendrogram
    print(f"\n  Dendrogram (text representation):")
    labels_short = [f"{s['project'][:8]}_{s['id'][:6]}" for s in sessions]

    # Compare with NCD clustering (experiment 011)
    # Cross-reference: which sessions were in which NCD clusters?
    print(f"\n  Session-cluster assignments:")
    print(f"    {'Session ID':<14s} {'Project':<20s} {'SW Cluster':>10s} {'Length':>7s} {'CorrRate':>8s}")
    for i in range(n):
        print(f"    {sessions[i]['id'][:12]:<14s} {sessions[i]['project'][:20]:<20s} "
              f"{primary_labels[i]:>10d} {sessions[i]['length']:>7d} "
              f"{sessions[i]['correction_rate']:>8.4f}")

    # Intra-cluster vs inter-cluster distances
    intra_dists = []
    inter_dists = []
    for i in range(n):
        for j in range(i + 1, n):
            if primary_labels[i] == primary_labels[j]:
                intra_dists.append(dist_matrix[i, j])
            else:
                inter_dists.append(dist_matrix[i, j])

    if intra_dists and inter_dists:
        print(f"\n  Cluster quality:")
        print(f"    Intra-cluster distance: mean={np.mean(intra_dists):.4f}, "
              f"std={np.std(intra_dists):.4f}")
        print(f"    Inter-cluster distance: mean={np.mean(inter_dists):.4f}, "
              f"std={np.std(inter_dists):.4f}")
        print(f"    Separation ratio: {np.mean(inter_dists)/np.mean(intra_dists):.2f}x")

    return {
        "linkage": Z,
        "labels": primary_labels,
        "cluster_members": dict(cluster_members),
        "dist_matrix": dist_matrix,
    }


# ─── Generate Report ────────────────────────────────────────────────────────

def generate_report(sessions, alignment_results, motif_results, phylo_results,
                    low_correction, high_correction):
    """Generate the experiment markdown report."""

    score_matrix, dist_matrix, best_alignments, conserved_motifs = alignment_results
    motif_data, _, _ = motif_results

    n = len(sessions)
    upper_tri = score_matrix[np.triu_indices(n, k=1)]

    report = []
    report.append("# Experiment 016: Genomics-Inspired Sequence Analysis")
    report.append("")
    report.append("**Date**: 2026-03-19")
    report.append("**Method**: Smith-Waterman alignment, motif discovery, phylogenetic clustering")
    report.append(f"**Sessions analyzed**: {len(sessions)}")
    report.append(f"**Projects covered**: {len(set(s['project'] for s in sessions))}")
    report.append("")

    # Method section
    report.append("## Method")
    report.append("")
    report.append("### Symbol Encoding")
    report.append("")
    report.append("Same encoding as experiment 011 (NCD clustering):")
    report.append("")
    report.append("| Symbol | Meaning |")
    report.append("|--------|---------|")
    report.append("| `Us`, `Um`, `Ul` | User message: short (<100 chars), medium, long (>500) |")
    report.append("| `At` | Assistant text output |")
    report.append("| `Ak` | Assistant thinking block |")
    report.append("| `Tb`, `Tr`, `Te`, `Tg`, `Tf` | Tool: Bash, Read, Edit, Grep, Glob |")
    report.append("| `Tw`, `Tm`, `To` | Tool: Write, MCP, StructuredOutput |")
    report.append("| `R` | Tool result returned to model |")
    report.append("")

    report.append("### Genomics Analogy")
    report.append("")
    report.append("| Genomics Concept | Session Analysis Equivalent |")
    report.append("|-----------------|---------------------------|")
    report.append("| DNA sequence | Symbol stream (temporal event sequence) |")
    report.append("| Local alignment (Smith-Waterman) | Finding conserved interaction patterns across sessions |")
    report.append("| Sequence motif | Recurring short behavioral patterns (k-mers) |")
    report.append("| Phylogenetic tree | Hierarchical clustering by structural similarity |")
    report.append("| Homologous region | Conserved subsequence appearing in unrelated sessions |")
    report.append("| Positive selection | Motifs enriched in successful sessions |")
    report.append("| Purifying selection | Motifs depleted in successful sessions |")
    report.append("")

    report.append("### Success Proxy")
    report.append("")
    report.append("Correction rate (combined user-correction and agent self-correction signals)")
    report.append("used as inverse success proxy:")
    report.append(f"- Low correction (successful): bottom quartile, rate <= {np.percentile([s['correction_rate'] for s in sessions], 25):.4f}")
    report.append(f"- High correction (struggling): top quartile, rate >= {np.percentile([s['correction_rate'] for s in sessions], 75):.4f}")
    report.append("")

    # Analysis 1: Alignment
    report.append("## Analysis 1: Local Sequence Alignment (Smith-Waterman)")
    report.append("")
    report.append(f"**Alignment parameters**: match={SW_MATCH}, mismatch={SW_MISMATCH}, gap={SW_GAP}")
    report.append(f"**Max sequence length**: 500 (center-truncated)")
    report.append("")

    report.append("### Global Statistics")
    report.append("")
    report.append(f"- **Normalized alignment scores**: mean={np.mean(upper_tri):.4f}, "
                  f"median={np.median(upper_tri):.4f}, range=[{np.min(upper_tri):.4f}, {np.max(upper_tri):.4f}]")
    report.append(f"- **Score std**: {np.std(upper_tri):.4f}")

    # Within vs cross project
    cross_scores = []
    within_scores = []
    for i in range(n):
        for j in range(i + 1, n):
            if sessions[i]["project"] == sessions[j]["project"]:
                within_scores.append(score_matrix[i, j])
            else:
                cross_scores.append(score_matrix[i, j])

    if within_scores:
        report.append(f"- **Within-project alignment**: mean={np.mean(within_scores):.4f} (n={len(within_scores)})")
    if cross_scores:
        report.append(f"- **Cross-project alignment**: mean={np.mean(cross_scores):.4f} (n={len(cross_scores)})")
    if within_scores and cross_scores:
        ratio = np.mean(within_scores) / np.mean(cross_scores) if np.mean(cross_scores) > 0 else float('inf')
        report.append(f"- **Within/cross ratio**: {ratio:.2f}x")
    report.append("")

    report.append("### Top Conserved Subsequences (Homologous Regions)")
    report.append("")
    report.append("These are the highest-scoring local alignments found across session pairs,")
    report.append("representing structural patterns conserved across different projects and tasks.")
    report.append("")

    seen_patterns = set()
    reported = 0
    for a in best_alignments:
        if reported >= 10:
            break
        pattern_key = " ".join(a["aligned1"][:8])
        if pattern_key in seen_patterns:
            continue
        seen_patterns.add(pattern_key)

        matches = sum(1 for x, y in zip(a["aligned1"], a["aligned2"]) if x == y)
        identity = matches / len(a["aligned1"]) if a["aligned1"] else 0

        report.append(f"#### Homologous Region #{reported+1}")
        report.append(f"- **Score**: {a['score']}, **Normalized**: {a['norm_score']:.3f}, "
                      f"**Length**: {a['len']}, **Identity**: {identity:.1%}")
        report.append(f"- **Sessions**: {a['proj_i']} vs {a['proj_j']}")

        display = " ".join(a["aligned1"][:40])
        if len(a["aligned1"]) > 40:
            display += "..."
        report.append(f"- **Pattern**: `{display}`")
        report.append("")
        reported += 1

    report.append("### Most Frequently Conserved Motifs (from alignments)")
    report.append("")
    report.append("Motifs that appear most often in the matched regions of high-scoring alignments:")
    report.append("")
    report.append("| Motif | Conservation Count | Interpretation |")
    report.append("|-------|-------------------|----------------|")
    for motif, count in conserved_motifs.most_common(20):
        motif_str = " ".join(motif)
        # Auto-interpret
        interp = interpret_motif(motif)
        report.append(f"| `{motif_str}` | {count} | {interp} |")
    report.append("")

    # Analysis 2: Motif Discovery
    report.append("## Analysis 2: Motif Discovery (Differential Enrichment)")
    report.append("")
    report.append(f"Comparing k-mer frequencies between {len(low_correction)} low-correction ")
    report.append(f"and {len(high_correction)} high-correction sessions using Fisher's exact test.")
    report.append("")

    for k in MOTIF_K_RANGE:
        data = motif_data[k]
        report.append(f"### k={k}")
        report.append("")
        report.append(f"- Total unique {k}-mers: {data['total_motifs']}")
        report.append(f"- Total k-mers in low-correction: {data['low_total_kmers']}")
        report.append(f"- Total k-mers in high-correction: {data['high_total_kmers']}")
        report.append(f"- Significantly enriched in low-correction: {len(data['enriched_low'])}")
        report.append(f"- Significantly enriched in high-correction: {len(data['enriched_high'])}")
        report.append("")

        if data["enriched_low"]:
            report.append(f"**Motifs enriched in SUCCESSFUL (low-correction) sessions:**")
            report.append("")
            report.append("| Motif | Odds Ratio | p-value | Freq (low) | Freq (high) | Interpretation |")
            report.append("|-------|-----------|---------|-----------|------------|----------------|")
            for e in data["enriched_low"][:8]:
                motif_str = " ".join(e["motif"])
                interp = interpret_motif(e["motif"])
                report.append(f"| `{motif_str}` | {e['odds_ratio']:.2f} | {e['p_value']:.4f} | "
                              f"{e['low_freq']:.4f} | {e['high_freq']:.4f} | {interp} |")
            report.append("")

        if data["enriched_high"]:
            report.append(f"**Motifs enriched in STRUGGLING (high-correction) sessions:**")
            report.append("")
            report.append("| Motif | Odds Ratio | p-value | Freq (low) | Freq (high) | Interpretation |")
            report.append("|-------|-----------|---------|-----------|------------|----------------|")
            for e in data["enriched_high"][:8]:
                motif_str = " ".join(e["motif"])
                interp = interpret_motif(e["motif"])
                report.append(f"| `{motif_str}` | {e['odds_ratio']:.2f} | {e['p_value']:.4f} | "
                              f"{e['low_freq']:.4f} | {e['high_freq']:.4f} | {interp} |")
            report.append("")

    # Analysis 3: Phylogenetic clustering
    report.append("## Analysis 3: Phylogenetic Clustering")
    report.append("")

    if phylo_results:
        labels = phylo_results["labels"]
        cluster_members = phylo_results["cluster_members"]

        report.append(f"**Method**: Average-linkage hierarchical clustering on Smith-Waterman distances")
        report.append(f"**Clusters**: {len(cluster_members)}")
        report.append("")

        # Intra vs inter cluster distances
        dm = phylo_results["dist_matrix"]
        intra = []
        inter = []
        for i in range(n):
            for j in range(i+1, n):
                if labels[i] == labels[j]:
                    intra.append(dm[i,j])
                else:
                    inter.append(dm[i,j])

        if intra and inter:
            report.append(f"- **Intra-cluster distance**: mean={np.mean(intra):.4f}")
            report.append(f"- **Inter-cluster distance**: mean={np.mean(inter):.4f}")
            report.append(f"- **Separation ratio**: {np.mean(inter)/np.mean(intra):.2f}x")
            report.append("")

        report.append("### Cluster Descriptions")
        report.append("")

        for cl in sorted(cluster_members.keys()):
            members = cluster_members[cl]
            projects = [sessions[i]["project"] for i in members]
            proj_counts = Counter(projects)
            lengths = [sessions[i]["length"] for i in members]
            corr_rates = [sessions[i]["correction_rate"] for i in members]

            # Structural profile
            all_symbols = []
            for i in members:
                all_symbols.extend(sessions[i]["symbols"])
            sym_counts = Counter(all_symbols)
            total_syms = len(all_symbols)

            # Dominant tool
            tool_syms = {k: v for k, v in sym_counts.items() if k.startswith("T")}
            dominant_tool = max(tool_syms, key=tool_syms.get) if tool_syms else "none"
            tool_name_map = {"Tb": "Bash", "Tr": "Read", "Te": "Edit", "Tw": "Write",
                            "Tg": "Grep", "Tf": "Glob", "Tm": "MCP", "Tx": "Other"}

            # User interaction level
            user_syms = sum(v for k, v in sym_counts.items() if k.startswith("U"))
            user_pct = user_syms / total_syms if total_syms > 0 else 0
            interactivity = "Highly-Autonomous" if user_pct < 0.02 else \
                           "Autonomous" if user_pct < 0.05 else "Interactive"

            label = f"{interactivity} / {tool_name_map.get(dominant_tool, dominant_tool)}-Dominant"

            report.append(f"#### Cluster {cl}: {label}")
            report.append(f"- **Size**: {len(members)} sessions")
            report.append(f"- **Length**: mean={np.mean(lengths):.0f}, range=[{min(lengths)}, {max(lengths)}]")
            report.append(f"- **Correction rate**: mean={np.mean(corr_rates):.4f}")
            report.append(f"- **Projects**: {dict(proj_counts.most_common(5))}")

            top_syms = sym_counts.most_common(6)
            sym_str = ", ".join(f"`{s}`: {c/total_syms:.1%}" for s, c in top_syms)
            report.append(f"- **Top symbols**: {sym_str}")

            # Sessions list
            report.append("")
            report.append("<details><summary>Sessions</summary>")
            report.append("")
            report.append("| Session | Project | Length | Correction |")
            report.append("|---------|---------|--------|------------|")
            for i in members:
                report.append(f"| `{sessions[i]['id'][:12]}...` | {sessions[i]['project']} | "
                            f"{sessions[i]['length']} | {sessions[i]['correction_rate']:.4f} |")
            report.append("")
            report.append("</details>")
            report.append("")

    # Comparison with NCD clustering
    report.append("## Comparison: SW Alignment vs NCD Clustering")
    report.append("")
    report.append("### Key Differences")
    report.append("")
    report.append("| Aspect | NCD (Experiment 011) | Smith-Waterman (This) |")
    report.append("|--------|---------------------|----------------------|")
    report.append("| Distance metric | Compression-based (global) | Alignment-based (local) |")
    report.append("| What it captures | Overall statistical similarity | Best matching subsequences |")
    report.append("| Length sensitivity | Normalized via fingerprinting | Truncation + normalization |")
    report.append("| Biological analogy | Whole-genome comparison | Gene-level homology |")
    report.append("")

    # Key findings
    report.append("## Key Findings")
    report.append("")

    # Finding 1: Conserved patterns
    report.append("### 1. Universal Interaction Motifs Exist")
    report.append("")
    top_conserved = conserved_motifs.most_common(5)
    if top_conserved:
        report.append("Local alignment reveals interaction patterns that are conserved across")
        report.append("unrelated projects, analogous to conserved genes across species:")
        report.append("")
        for motif, count in top_conserved:
            interp = interpret_motif(motif)
            report.append(f"- `{' '.join(motif)}`: conserved {count} times -- {interp}")
        report.append("")

    # Finding 2: Success motifs
    report.append("### 2. Success-Associated Motifs")
    report.append("")
    all_success_motifs = []
    for k in MOTIF_K_RANGE:
        all_success_motifs.extend(motif_data[k]["enriched_low"][:3])
    if all_success_motifs:
        report.append("Motifs significantly enriched in low-correction (successful) sessions:")
        report.append("")
        for e in all_success_motifs[:8]:
            motif_str = " ".join(e["motif"])
            interp = interpret_motif(e["motif"])
            report.append(f"- `{motif_str}` (OR={e['odds_ratio']:.2f}, p={e['p_value']:.4f}): {interp}")
        report.append("")

    # Finding 3: Failure motifs
    report.append("### 3. Struggle-Associated Motifs")
    report.append("")
    all_failure_motifs = []
    for k in MOTIF_K_RANGE:
        all_failure_motifs.extend(motif_data[k]["enriched_high"][:3])
    if all_failure_motifs:
        report.append("Motifs significantly enriched in high-correction (struggling) sessions:")
        report.append("")
        for e in all_failure_motifs[:8]:
            motif_str = " ".join(e["motif"])
            interp = interpret_motif(e["motif"])
            report.append(f"- `{motif_str}` (OR={e['odds_ratio']:.2f}, p={e['p_value']:.4f}): {interp}")
        report.append("")

    # Finding 4: Within vs cross project
    report.append("### 4. Cross-Project Conservation")
    report.append("")
    if within_scores and cross_scores:
        report.append(f"Within-project alignment (mean={np.mean(within_scores):.4f}) vs "
                      f"cross-project (mean={np.mean(cross_scores):.4f}).")
        if np.mean(within_scores) > np.mean(cross_scores):
            report.append("Sessions within the same project share more structural similarity,")
            report.append("but significant cross-project conservation exists, indicating")
            report.append("universal interaction patterns independent of task domain.")
        else:
            report.append("Cross-project alignment scores are comparable to within-project,")
            report.append("suggesting interaction patterns are largely task-independent.")
    report.append("")

    # Finding 5: Phylogenetic tree interpretation
    report.append("### 5. Phylogenetic Structure")
    report.append("")
    if phylo_results:
        report.append(f"The alignment-based dendrogram reveals {len(cluster_members)} distinct")
        report.append("session lineages. Unlike NCD clustering (which captures global statistical")
        report.append("properties), alignment clustering groups sessions that share specific")
        report.append("behavioral subsequences -- the equivalent of grouping organisms by")
        report.append("shared genes rather than overall genome composition.")
    report.append("")

    return "\n".join(report)


def interpret_motif(motif):
    """Auto-interpret a motif tuple into human-readable description."""
    syms = list(motif)

    # Common pattern descriptions
    if all(s == "At" for s in syms):
        return "Extended text generation without tools"
    if all(s == "R" for s in syms):
        return "Rapid tool result processing"

    has_think = "Ak" in syms
    has_text = "At" in syms
    has_result = "R" in syms

    tool_types = [s for s in syms if s.startswith("T")]

    if syms == ["R", "Tb", "R"]:
        return "Bash execution cycle"
    if syms == ["R", "Tr", "R"]:
        return "Read execution cycle"
    if syms == ["R", "Te", "R"]:
        return "Edit execution cycle"

    # Think-before-act patterns
    if len(syms) >= 2 and syms[0] == "Ak" and syms[1] == "At":
        rest = syms[2:]
        if rest and rest[0].startswith("T"):
            return f"Think-then-act: reason before {rest[0]}"
        return "Think-then-speak pattern"

    # Tool chains
    if all(s.startswith("T") or s == "R" for s in syms):
        tools = [s for s in syms if s.startswith("T")]
        if len(set(tools)) == 1:
            return f"Repeated {tools[0]} execution"
        return f"Tool chain: {' -> '.join(tools)}"

    # User interaction patterns
    if syms[0].startswith("U"):
        if len(syms) > 1 and syms[1] == "Ak":
            return "User prompt triggers deliberation"
        if len(syms) > 1 and syms[1] == "At":
            return "Direct user-to-response"

    # Result processing
    if syms[0] == "R" and has_think:
        return "Analyze tool results before acting"

    if has_text and has_result and tool_types:
        return f"Interleaved text and {', '.join(set(tool_types))}"

    return "Interaction pattern"


# ─── Main ────────────────────────────────────────────────────────────────────

def main():
    print("Experiment 016: Genomics-Inspired Sequence Analysis")
    print("=" * 70)

    # Load sessions
    sessions = load_sessions()

    if not sessions:
        print("ERROR: No sessions loaded")
        sys.exit(1)

    # Print session summary
    projects = Counter(s["project"] for s in sessions)
    print(f"\nProjects sampled:")
    for p, c in projects.most_common():
        print(f"  {p}: {c}")

    correction_rates = [s["correction_rate"] for s in sessions]
    print(f"\nCorrection rate: mean={np.mean(correction_rates):.4f}, "
          f"median={np.median(correction_rates):.4f}")

    lengths = [s["length"] for s in sessions]
    print(f"Session lengths: mean={np.mean(lengths):.0f}, "
          f"median={np.median(lengths):.0f}, range=[{min(lengths)}, {max(lengths)}]")

    # Analysis 1: Smith-Waterman alignment
    alignment_results = run_alignment_analysis(sessions)

    # Analysis 2: Motif discovery
    motif_results = run_motif_analysis(sessions)

    # Analysis 3: Phylogenetic clustering
    _, dist_matrix, _, _ = alignment_results
    phylo_results = run_phylogenetic_clustering(sessions, dist_matrix)

    # Generate report
    report = generate_report(
        sessions, alignment_results, motif_results, phylo_results,
        motif_results[1], motif_results[2]
    )

    output_path = os.path.join(OUTPUT_DIR, "016-genomics-sequence-analysis.md")
    with open(output_path, "w") as f:
        f.write(report)

    print(f"\nReport written to: {output_path}")

    # Return data for solution doc generation
    return sessions, alignment_results, motif_results, phylo_results


if __name__ == "__main__":
    main()
