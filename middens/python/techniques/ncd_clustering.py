#!/usr/bin/env python3
"""ncd_clustering — Batch 3 Python technique for middens."""
import json
import math
import random
import sys
import zlib
from collections import Counter, defaultdict

import numpy as np
from scipy.cluster.hierarchy import linkage, fcluster
from scipy.spatial.distance import squareform

NAME = "ncd_clustering"
MIN_SESSIONS = 5


def sanitize(obj):
    """Recursively replace NaN/Infinity with None for JSON safety. Handles numpy scalars/arrays."""
    import numpy as np
    if isinstance(obj, np.ndarray):
        return sanitize(obj.tolist())
    if isinstance(obj, (np.floating, np.integer)):
        obj = obj.item()
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


def build_symbol_stream(session):
    """Build a symbol stream for a session."""
    stream = []
    for msg in session.get("messages", []):
        role = msg.get("role", "")
        classification = msg.get("classification", "")
        
        if role == "System":
            continue
        
        if role == "User":
            text = msg.get("text", "")
            symbol = "U" if len(text) >= 200 else "u"
            stream.append(symbol)
            if classification == "HumanCorrection":
                stream.append("C")
        
        elif role == "Assistant":
            thinking = msg.get("thinking")
            has_thinking = thinking is not None and thinking != ""
            tool_calls = msg.get("tool_calls", []) or []
            tool_results = msg.get("tool_results", []) or []
            
            if has_thinking:
                stream.append("T")
            
            for tc in tool_calls:
                name = tc.get("name", "")
                if name == "Read":
                    stream.append("R")
                elif name in ("Glob", "Grep"):
                    stream.append("G")
                elif name == "Edit":
                    stream.append("E")
                elif name == "Write":
                    stream.append("W")
                elif name == "Bash":
                    stream.append("B")
                elif name == "Skill":
                    stream.append("S")
                else:
                    stream.append("X")
            
            has_error = any(tr.get("is_error", False) for tr in tool_results)
            if has_error:
                stream.append("F")
            
            if not tool_calls and not has_thinking:
                stream.append("A")
    
    return "".join(stream)


def compute_ncd_matrix(streams):
    """Compute NCD matrix for a list of symbol streams."""
    n = len(streams)
    ncd_matrix = np.zeros((n, n))
    
    compressed_lengths = []
    for s in streams:
        compressed = zlib.compress(s.encode("utf-8"), level=9)
        compressed_lengths.append(len(compressed))
    
    for i in range(n):
        for j in range(i, n):
            if i == j:
                ncd_matrix[i][j] = 0.0
            else:
                # zlib compression is order-dependent: C(xy) != C(yx) in general.
                # Naive mirroring would make the same pair of sessions get a
                # different distance depending on input order, which can change
                # linkage merges and the chosen optimal_k. Symmetrize by taking
                # the minimum of both concatenation orders — this is the
                # standard NCD fix (Cilibrasi & Vitányi) and matches the
                # information-theoretic interpretation (the best achievable
                # cross-compression).
                len_cxy = len(zlib.compress((streams[i] + streams[j]).encode("utf-8"), level=9))
                len_cyx = len(zlib.compress((streams[j] + streams[i]).encode("utf-8"), level=9))
                len_c_sym = min(len_cxy, len_cyx)

                min_len = min(compressed_lengths[i], compressed_lengths[j])
                max_len = max(compressed_lengths[i], compressed_lengths[j])

                if max_len == 0:
                    ncd = 0.0
                else:
                    ncd = (len_c_sym - min_len) / max_len

                ncd_matrix[i][j] = ncd
                ncd_matrix[j][i] = ncd

    return ncd_matrix


def silhouette_score_custom(distance_matrix, labels):
    """Compute silhouette score manually without sklearn."""
    n = len(labels)
    if len(set(labels)) <= 1:
        return 0.0
    
    scores = []
    for i in range(n):
        cluster_i = labels[i]
        same_cluster = [j for j in range(n) if labels[j] == cluster_i and j != i]
        other_clusters = [j for j in range(n) if labels[j] != cluster_i]
        
        if len(same_cluster) == 0:
            scores.append(0.0)
            continue
        
        a_i = sum(distance_matrix[i][j] for j in same_cluster) / len(same_cluster)
        
        if len(other_clusters) == 0:
            scores.append(0.0)
            continue
        
        other_cluster_ids = set(labels[j] for j in other_clusters)
        b_vals = []
        for other_id in other_cluster_ids:
            other_points = [j for j in range(n) if labels[j] == other_id]
            if other_points:
                b_vals.append(sum(distance_matrix[i][j] for j in other_points) / len(other_points))
        
        if not b_vals:
            scores.append(0.0)
            continue
        
        b_i = min(b_vals)
        
        if max(a_i, b_i) == 0:
            scores.append(0.0)
        else:
            scores.append((b_i - a_i) / max(a_i, b_i))
    
    return sum(scores) / len(scores)


def infer_cluster_label(dominant_symbol):
    """Infer cluster label from dominant symbol."""
    # Map every symbol emitted by build_symbol_stream() to a stable label so
    # largest_cluster_label is deterministic and interpretable for every cluster.
    symbol_labels = {
        "R": "read-heavy",
        "G": "read-heavy",     # Glob/Grep group under read
        "E": "edit-heavy",
        "W": "edit-heavy",
        "B": "bash-heavy",
        "S": "skill-heavy",
        "X": "other-tool-heavy",
        "A": "text-heavy",     # assistant text without tools or thinking
        "T": "thinking-heavy",
        "u": "dialogue-heavy",
        "U": "dialogue-heavy",
        "C": "correction-heavy",
        "F": "failure-heavy",
    }
    return symbol_labels.get(dominant_symbol, f"{dominant_symbol}-heavy")


def analyze(sessions):
    # Build symbol streams
    streams = []
    session_ids = []
    sessions_skipped = 0
    
    for session in sessions:
        stream = build_symbol_stream(session)
        if len(stream) < 8:
            sessions_skipped += 1
        else:
            streams.append(stream)
            session_ids.append(session.get("id", f"session_{len(session_ids)}"))
    
    if not streams:
        return empty_result("insufficient data: no sessions with symbol stream length >= 8")
    
    # Sample at most 50 sessions
    random.seed(42)
    sample_size = min(50, len(streams))
    if len(streams) > sample_size:
        indices = random.sample(range(len(streams)), sample_size)
        streams = [streams[i] for i in indices]
        session_ids = [session_ids[i] for i in indices]
    
    sessions_in_sample = len(streams)

    # Hierarchical clustering requires at least 2 observations; the condensed
    # distance matrix for a single point has zero entries and SciPy will error.
    # Return a valid insufficient-data result rather than crashing.
    if sessions_in_sample < 2:
        return empty_result(
            f"insufficient data: need at least 2 sessions with symbol stream length >= 8, "
            f"got {sessions_in_sample} (skipped {sessions_skipped})"
        )

    # Compute NCD matrix
    ncd_matrix = compute_ncd_matrix(streams)

    # Hierarchical clustering
    condensed = squareform(ncd_matrix)
    Z = linkage(condensed, method="average")
    
    # Choose optimal k
    k_candidates = [3, 4, 5, 6, 7, 8]
    k_candidates = [k for k in k_candidates if k < sessions_in_sample]
    
    if not k_candidates:
        # Fallback: try smaller k values
        k_candidates = [2] if sessions_in_sample >= 2 else [1]
    
    best_k = k_candidates[0]
    best_score = -1.0
    
    for k in k_candidates:
        labels = fcluster(Z, k, criterion="maxclust")
        score = silhouette_score_custom(ncd_matrix, labels)
        if score > best_score:
            best_score = score
            best_k = k
    
    optimal_k = best_k
    silhouette_score = round(best_score, 4)
    
    # Final clustering with optimal k
    final_labels = fcluster(Z, optimal_k, criterion="maxclust")
    
    # Compute cluster stats
    clusters = defaultdict(list)
    for i, label in enumerate(final_labels):
        clusters[label].append(i)
    
    cluster_summaries = []
    largest_cluster_size = 0
    largest_cluster_label = "mixed"
    
    for cluster_id in sorted(clusters.keys()):
        member_indices = clusters[cluster_id]
        size = len(member_indices)
        
        # Dominant symbol
        all_symbols = "".join(streams[i] for i in member_indices)
        symbol_counts = Counter(all_symbols)
        dominant_symbol = symbol_counts.most_common(1)[0][0] if symbol_counts else "?"
        
        # Mean length
        lengths = [len(streams[i]) for i in member_indices]
        mean_length = round(sum(lengths) / len(lengths), 2) if lengths else 0.0
        
        # Mean correction rate
        correction_rates = []
        for i in member_indices:
            stream = streams[i]
            c_count = stream.count("C")
            rate = c_count / len(stream) if stream else 0.0
            correction_rates.append(rate)
        mean_correction_rate = round(sum(correction_rates) / len(correction_rates), 4) if correction_rates else 0.0
        
        # Representative (closest to median length)
        median_length = np.median(lengths)
        closest_idx = member_indices[0]
        closest_dist = abs(lengths[0] - median_length)
        for idx, i in enumerate(member_indices):
            dist = abs(lengths[idx] - median_length)
            if dist < closest_dist:
                closest_dist = dist
                closest_idx = i
        representative = streams[closest_idx][:60]
        
        cluster_summaries.append({
            "cluster_id": int(cluster_id),
            "size": size,
            "dominant_symbol": dominant_symbol,
            "mean_length": mean_length,
            "mean_correction_rate": mean_correction_rate,
            "representative": representative,
        })
        
        if size > largest_cluster_size:
            largest_cluster_size = size
            largest_cluster_label = infer_cluster_label(dominant_symbol)
    
    # Build cluster summary table
    cluster_table = {
        "name": "Cluster Summary",
        "columns": ["cluster_id", "size", "dominant_symbol", "mean_length", "mean_correction_rate", "representative"],
        "rows": [
            [
                cs["cluster_id"],
                cs["size"],
                cs["dominant_symbol"],
                cs["mean_length"],
                cs["mean_correction_rate"],
                cs["representative"],
            ]
            for cs in cluster_summaries
        ],
    }
    
    # Build NCD matrix preview (first 10 sessions)
    preview_size = min(10, sessions_in_sample)
    preview_headers = ["session_id"] + [f"s{i+1}" for i in range(preview_size)]
    preview_rows = []
    
    for i in range(preview_size):
        row = [session_ids[i]] + [round(ncd_matrix[i][j], 3) for j in range(preview_size)]
        preview_rows.append(row)
    
    ncd_preview_table = {
        "name": "NCD Matrix Preview",
        "columns": preview_headers,
        "rows": preview_rows,
    }
    
    # Summary
    summary = f"NCD (normalized compression distance) clustering of {sessions_in_sample} sessions produced {optimal_k} clusters (silhouette={silhouette_score}). Largest cluster (n={largest_cluster_size}) is {largest_cluster_label}. {sessions_skipped} sessions skipped for insufficient length."
    
    findings = [
        {"label": "sessions_in_sample", "value": sessions_in_sample},
        {"label": "sessions_skipped", "value": sessions_skipped},
        {"label": "optimal_k", "value": optimal_k},
        {"label": "silhouette_score", "value": silhouette_score},
        {"label": "largest_cluster_size", "value": largest_cluster_size},
        {"label": "largest_cluster_label", "value": largest_cluster_label},
    ]
    
    return {
        "name": NAME,
        "summary": summary,
        "findings": findings,
        "tables": [cluster_table, ncd_preview_table],
        "figures": [],
    }


def main():
    if len(sys.argv) < 2:
        print("usage: ncd_clustering.py <sessions.json>", file=sys.stderr)
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

    result = analyze(sessions)
    print(json.dumps(sanitize(result), default=str))


if __name__ == "__main__":
    main()
