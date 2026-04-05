import sys
import json
import math
import os
import random
from collections import Counter
from typing import List, Dict, Any, Tuple

# Set random seed for reproducibility
random.seed(42)

def sanitize_for_json(obj):
    """Replace NaN/Infinity with None for valid JSON."""
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    if isinstance(obj, dict):
        return {k: sanitize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [sanitize_for_json(v) for v in obj]
    try:
        import numpy as np
        if isinstance(obj, (np.integer, np.floating, np.bool_)):
            return obj.item()
    except ImportError:
        pass
    return obj

def encode_session(session: Dict) -> str:
    """Encode session as symbol string."""
    symbols = []
    messages = session.get('messages', [])

    for msg in messages:
        role = msg.get('role', '')
        classification = msg.get('classification', '')

        if role == 'User':
            if classification == 'HumanCorrection':
                symbols.append('C')
            else:
                symbols.append('U')
        elif role == 'Assistant':
            if msg.get('thinking'):
                symbols.append('T')
            tool_calls = msg.get('tool_calls', [])
            if tool_calls:
                for tc in tool_calls:
                    tl = tc.get('name', '').lower()
                    if tl == 'read':
                        symbols.append('R')
                    elif tl in ('glob', 'grep'):
                        symbols.append('G')
                    elif tl == 'edit':
                        symbols.append('E')
                    elif tl == 'write':
                        symbols.append('W')
                    elif tl == 'bash':
                        symbols.append('B')
                    elif tl == 'skill':
                        symbols.append('S')
                    else:
                        symbols.append('X')
            else:
                symbols.append('U')

    return ''.join(symbols)

def smith_waterman(seq1: str, seq2: str, match: int = 2, mismatch: int = -1, gap: int = -1) -> int:
    """Smith-Waterman local alignment algorithm."""
    m, n = len(seq1), len(seq2)
    H = [[0] * (n + 1) for _ in range(m + 1)]
    
    max_score = 0
    
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if seq1[i-1] == seq2[j-1]:
                score = match
            else:
                score = mismatch
            
            H[i][j] = max(
                0,
                H[i-1][j-1] + score,
                H[i-1][j] + gap,
                H[i][j-1] + gap
            )
            max_score = max(max_score, H[i][j])
    
    return max_score

def find_kmers(sequences: List[str], k_min: int = 3, k_max: int = 5, threshold: float = 0.3) -> List[Tuple[str, int, float]]:
    """Find conserved k-mers appearing in >threshold fraction of sequences."""
    n = len(sequences)
    kmers = []
    
    for k in range(k_min, k_max + 1):
        kmer_counts = Counter()
        kmer_sessions = Counter()
        
        for seq in sequences:
            seen = set()
            for i in range(len(seq) - k + 1):
                kmer = seq[i:i+k]
                kmer_counts[kmer] += 1
                if kmer not in seen:
                    kmer_sessions[kmer] += 1
                    seen.add(kmer)
        
        for kmer, session_count in kmer_sessions.items():
            coverage = session_count / n
            if coverage > threshold:
                kmers.append((kmer, kmer_counts[kmer], coverage))
    
    return sorted(kmers, key=lambda x: (-x[2], -x[1]))

def analyze_motif_enrichment(sequences: List[str], corrections: List[int]) -> List[Tuple[str, float, float, float, str]]:
    """Analyze motif enrichment in low vs high correction sessions."""
    n = len(sequences)
    if n == 0:
        return []
    
    # Split into low and high correction groups
    sorted_indices = sorted(range(n), key=lambda i: corrections[i])
    split = n // 2
    low_indices = set(sorted_indices[:split])
    
    # Collect all k-mers
    all_kmers = set()
    for seq in sequences:
        for k in range(3, 6):
            for i in range(len(seq) - k + 1):
                all_kmers.add(seq[i:i+k])
    
    results = []
    low_total = sum(len(sequences[i]) for i in low_indices)
    high_total = sum(len(sequences[i]) for i in range(n) if i not in low_indices)
    
    if low_total == 0 or high_total == 0:
        return []
    
    for kmer in all_kmers:
        low_count = sum(sequences[i].count(kmer) for i in low_indices)
        high_count = sum(sequences[i].count(kmer) for i in range(n) if i not in low_indices)
        
        low_freq = low_count / low_total if low_total > 0 else 0
        high_freq = high_count / high_total if high_total > 0 else 0
        
        if low_freq > 0 and high_freq > 0:
            if low_freq > high_freq * 2:
                ratio = low_freq / high_freq
                results.append((kmer, low_freq, high_freq, ratio, 'low_correction'))
            elif high_freq > low_freq * 2:
                ratio = high_freq / low_freq
                results.append((kmer, low_freq, high_freq, ratio, 'high_correction'))
    
    return sorted(results, key=lambda x: -x[3])

def main():
    if len(sys.argv) < 2:
        print("Usage: python smith_waterman.py <input_json_path>", file=sys.stderr)
        sys.exit(1)

    input_path = sys.argv[1]
    if not os.path.exists(input_path):
        print(f"Error: Input file not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    try:
        with open(input_path, 'r') as f:
            sessions = json.load(f)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in input file: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error reading file: {e}", file=sys.stderr)
        sys.exit(1)

    # Check for empty sessions
    if len(sessions) == 0:
        result = {
            "name": "smith_waterman",
            "summary": "Smith-Waterman alignment analysis - no sessions provided",
            "findings": [],
            "tables": [],
            "figures": []
        }
        print(json.dumps(sanitize_for_json(result)))
        sys.exit(0)

    # Check for insufficient sessions (< 5)
    if len(sessions) < 5:
        result = {
            "name": "smith_waterman",
            "summary": f"Smith-Waterman alignment analysis - insufficient sessions ({len(sessions)} provided, minimum 5 required)",
            "findings": [
                {"label": "session_count", "value": len(sessions), "description": "Number of sessions provided"}
            ],
            "tables": [],
            "figures": []
        }
        print(json.dumps(sanitize_for_json(result)))
        sys.exit(0)

    # Encode sessions
    encoded_sessions = []
    correction_counts = []
    
    for session in sessions:
        encoded = encode_session(session)
        encoded_sessions.append(encoded)
        correction_counts.append(encoded.count('C'))

    # Sample if > 50 sessions
    if len(encoded_sessions) > 50:
        indices = random.sample(range(len(encoded_sessions)), 50)
        encoded_sessions = [encoded_sessions[i] for i in indices]
        correction_counts = [correction_counts[i] for i in indices]

    n = len(encoded_sessions)

    # Compute pairwise Smith-Waterman scores
    scores = []
    for i in range(n):
        for j in range(i + 1, n):
            sw_score = smith_waterman(encoded_sessions[i], encoded_sessions[j])
            min_len = min(len(encoded_sessions[i]), len(encoded_sessions[j]))
            normalized_score = sw_score / min_len if min_len > 0 else 0
            scores.append(normalized_score)

    mean_alignment_score = sum(scores) / len(scores) if scores else 0.0

    # Find conserved motifs
    conserved_motifs = find_kmers(encoded_sessions)
    conserved_motifs_count = len(conserved_motifs)

    # Analyze motif enrichment
    enrichment = analyze_motif_enrichment(encoded_sessions, correction_counts)
    
    top_success_motif = ""
    top_struggle_motif = ""
    
    for item in enrichment:
        if item[4] == 'low_correction' and not top_success_motif:
            top_success_motif = item[0]
        elif item[4] == 'high_correction' and not top_struggle_motif:
            top_struggle_motif = item[0]
        if top_success_motif and top_struggle_motif:
            break

    # Hierarchical clustering
    cluster_count = 1
    try:
        from scipy.cluster.hierarchy import linkage, fcluster
        from scipy.spatial.distance import squareform
        import numpy as np

        # Create distance matrix from alignment scores
        dist_matrix = np.zeros((n, n))
        idx = 0
        for i in range(n):
            for j in range(i + 1, n):
                # Convert similarity to distance
                sim = scores[idx] if idx < len(scores) else 0
                dist = 1.0 - min(sim, 1.0)
                dist_matrix[i, j] = dist
                dist_matrix[j, i] = dist
                idx += 1

        # Convert to condensed distance matrix
        condensed = squareform(dist_matrix, checks=False)
        
        if len(condensed) > 0 and np.any(condensed > 0):
            Z = linkage(condensed, method='average')
            clusters = fcluster(Z, t=0.5, criterion='distance')
            cluster_count = len(set(clusters))
    except Exception:
        cluster_count = 1

    # Build result
    findings = [
        {"label": "mean_alignment_score", "value": round(mean_alignment_score, 4), "description": "Mean normalized Smith-Waterman alignment score"},
        {"label": "conserved_motifs_count", "value": conserved_motifs_count, "description": "Number of conserved k-mer motifs found"},
        {"label": "top_success_motif", "value": top_success_motif or "None", "description": "Most enriched motif in low-correction sessions"},
        {"label": "top_struggle_motif", "value": top_struggle_motif or "None", "description": "Most enriched motif in high-correction sessions"},
        {"label": "cluster_count", "value": cluster_count, "description": "Number of behavior clusters identified"}
    ]

    tables = []

    # Conserved motifs table
    if conserved_motifs:
        motif_table = {
            "name": "Conserved Motifs",
            "columns": ["motif", "frequency", "session_coverage_pct"],
            "rows": [
                [m[0], m[1], round(m[2] * 100, 2)]
                for m in conserved_motifs[:20]  # Top 20
            ]
        }
        tables.append(motif_table)

    # Motif enrichment table
    if enrichment:
        enrichment_table = {
            "name": "Motif Enrichment",
            "columns": ["motif", "low_correction_freq", "high_correction_freq", "enrichment_ratio", "group"],
            "rows": [
                [e[0], round(e[1], 6), round(e[2], 6), round(e[3], 2), e[4]]
                for e in enrichment[:20]  # Top 20
            ]
        }
        tables.append(enrichment_table)

    result = {
        "name": "smith_waterman",
        "summary": f"Smith-Waterman alignment analysis on {n} sessions",
        "findings": findings,
        "tables": tables,
        "figures": []
    }

    print(json.dumps(sanitize_for_json(result)))

if __name__ == "__main__":
    main()
