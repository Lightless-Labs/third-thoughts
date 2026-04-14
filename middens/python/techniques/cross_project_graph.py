#!/usr/bin/env python3
"""cross_project_graph technique for middens analytical CLI."""

import json
import math
import re
import sys
from collections import defaultdict

import networkx as nx


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


def classify_reference(context):
    """Classify reference type based on context window."""
    context_lower = context.lower()
    
    impl_patterns = [
        r'look at how',
        r'same pattern',
        r'like .* does',
        r'based on'
    ]
    for pattern in impl_patterns:
        if re.search(pattern, context_lower):
            return "implementation"
    
    context_patterns = [r'CLAUDE\.md', r'README', r'config', r'\.claude/']
    for pattern in context_patterns:
        if re.search(pattern, context, re.IGNORECASE):
            return "context_import"
    
    knowledge_patterns = [r'learned from', r'solution in', r'already solved']
    for pattern in knowledge_patterns:
        if re.search(pattern, context_lower):
            return "knowledge_sharing"
    
    action_patterns = [r'\bpush\b', r'\bcommit\b', r'\bdeploy\b', r'\bpr\b', r'\bmerge\b']
    for pattern in action_patterns:
        if re.search(pattern, context_lower):
            return "cross_project_action"
    
    return "other"


def main():
    if len(sys.argv) < 2:
        print("Usage: python cross_project_graph.py <path_to_sessions.json>", file=sys.stderr)
        sys.exit(1)
    
    input_path = sys.argv[1]
    
    try:
        with open(input_path, 'r', encoding='utf-8') as f:
            sessions = json.load(f)
    except FileNotFoundError:
        print(f"Error: File not found: {input_path}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON: {e}", file=sys.stderr)
        sys.exit(1)
    
    if not isinstance(sessions, list):
        print("Error: Expected JSON array of sessions", file=sys.stderr)
        sys.exit(1)
    
    # Step 1: Extract source projects
    sessions_with_project = []
    sessions_skipped_no_project = 0
    
    for session in sessions:
        project = session.get("metadata", {}).get("project", "") or ""
        if project and project.strip():
            sessions_with_project.append((project.strip(), session))
        else:
            sessions_skipped_no_project += 1
    
    # Step 2: Build set of known projects
    known_projects = set(proj for proj, _ in sessions_with_project)

    # Step 3 & 4: Scan for mentions and classify.
    # Build a single combined alternation pattern from all project names (sorted
    # longest-first so the regex engine prefers longer matches on ambiguous input).
    # This scans each message text once instead of once per project, reducing the
    # inner loop from O(sessions × messages × projects) to O(sessions × messages).
    edge_weights = defaultdict(int)
    edge_types = defaultdict(lambda: defaultdict(int))

    if known_projects:
        # Sort longest-first so longer project names take priority over shorter
        # prefixes in the alternation, with alphabetical tie-breaking for a
        # fully deterministic pattern regardless of set hash-ordering.
        sorted_projects = sorted(known_projects, key=lambda p: (-len(p), p.lower()))
        # Build lookup with deterministic collision resolution: among projects
        # that share the same lowercase form, the alphabetically-first original
        # name wins (reverse-iterate so first write is the winner).
        project_lookup = {p.lower(): p for p in reversed(sorted_projects)}
        combined_pattern = re.compile(
            r'\b(' + '|'.join(re.escape(p) for p in sorted_projects) + r')\b',
            re.IGNORECASE,
        )

        for src_project, session in sessions_with_project:
            messages = session.get("messages", [])
            for msg in messages:
                role = msg.get("role", "")
                text = msg.get("text", "")

                if role not in ("User", "Assistant") or not text:
                    continue

                for match in combined_pattern.finditer(text):
                    dst_project = project_lookup.get(match.group(1).lower())
                    if dst_project is None or dst_project == src_project:
                        continue

                    start = max(0, match.start() - 100)
                    end = min(len(text), match.end() + 100)
                    context = text[start:end]

                    ref_type = classify_reference(context)
                    edge_weights[(src_project, dst_project)] += 1
                    edge_types[(src_project, dst_project)][ref_type] += 1
    
    # Step 6: Build graph and compute metrics
    total_sessions = len(sessions_with_project)
    total_projects = len(known_projects)
    total_edges = len(edge_weights)
    total_references = sum(edge_weights.values())
    
    # Default findings
    mutual_pair_count = 0
    cluster_count = 0
    largest_hub = ""
    largest_authority = ""
    
    # Build graph (runs for all cases — used for degrees, weights, clusters, tables).
    G = nx.DiGraph()
    for proj in known_projects:
        G.add_node(proj)
    for (src, dst), weight in edge_weights.items():
        G.add_edge(src, dst, weight=weight)

    out_degree = {n: G.out_degree(n) for n in G.nodes()}
    in_degree = {n: G.in_degree(n) for n in G.nodes()}

    out_weight = defaultdict(int)
    in_weight = defaultdict(int)
    for (src, dst), weight in edge_weights.items():
        out_weight[src] += weight
        in_weight[dst] += weight

    # Hubs and authorities (by total weight; ties broken by ascending project name).
    if out_weight:
        max_out = max(out_weight.values())
        hubs = sorted(n for n, w in out_weight.items() if w == max_out)
        if hubs:
            largest_hub = hubs[0]
    if in_weight:
        max_in = max(in_weight.values())
        authorities = sorted(n for n, w in in_weight.items() if w == max_in)
        if authorities:
            largest_authority = authorities[0]

    # Weakly connected components / clusters.
    components = list(nx.weakly_connected_components(G))
    clusters = [c for c in components if len(c) > 1]
    cluster_count = len(clusters)

    # Mutual pairs.
    mutual_pairs = set()
    for (src, dst) in edge_weights:
        if (dst, src) in edge_weights:
            mutual_pairs.add(tuple(sorted([src, dst])))
    mutual_pair_count = len(mutual_pairs)

    # Edges table — dominant type by highest count, ties broken by ascending name.
    edges_rows = []
    for (src, dst), weight in edge_weights.items():
        types_dict = edge_types[(src, dst)]
        dominant = min(types_dict.keys(), key=lambda t: (-types_dict[t], t))
        edges_rows.append((weight, src, dst, dominant))
    edges_rows.sort(key=lambda x: (-x[0], x[1], x[2]))
    edges_table = [[src, dst, weight, dom_type] for weight, src, dst, dom_type in edges_rows]

    # Nodes table — sorted by out_weight desc, then in_weight desc.
    nodes_rows = []
    for proj in known_projects:
        nodes_rows.append((
            out_weight.get(proj, 0),
            in_weight.get(proj, 0),
            proj,
            out_degree.get(proj, 0),
            in_degree.get(proj, 0),
        ))
    # Tie-break on ascending project name so equal-weight rows are stable
    # across runs (known_projects is a set, so insertion order is
    # hash-seed dependent without an explicit final key).
    nodes_rows.sort(key=lambda x: (-x[0], -x[1], x[2]))
    nodes_table = [[proj, od, ind, ow, iw] for ow, iw, proj, od, ind in nodes_rows]

    # Clusters table — sort clusters deterministically before assigning IDs
    # so that cluster_id is stable across runs for identical input (graph
    # component iteration order follows unsorted set order otherwise).
    clusters_sorted = sorted(clusters, key=lambda c: (-len(c), sorted(c)))
    clusters_table = []
    for i, cluster in enumerate(clusters_sorted):
        members = ','.join(sorted(cluster))
        clusters_table.append([i, len(cluster), members])
    
    # Build result
    if total_projects < 2 or total_edges < 1:
        summary = f"insufficient cross-project references: need at least 2 projects with an edge (found {total_projects} projects, {total_edges} edges)"
    else:
        summary = f"cross-project graph analysis: {total_projects} projects, {total_edges} edges, {cluster_count} clusters"
    
    result = {
        "name": "cross-project-graph",
        "summary": summary,
        "findings": [
            {"label": "total_sessions", "value": total_sessions, "description": None},
            {"label": "total_projects", "value": total_projects, "description": None},
            {"label": "total_edges", "value": total_edges, "description": None},
            {"label": "total_references", "value": total_references, "description": None},
            {"label": "mutual_pair_count", "value": mutual_pair_count, "description": None},
            {"label": "cluster_count", "value": cluster_count, "description": None},
            {"label": "largest_hub", "value": largest_hub, "description": None},
            {"label": "largest_authority", "value": largest_authority, "description": None}
        ],
        "tables": [
            {"name": "Edges", "columns": ["source", "target", "weight", "dominant_type"], "rows": edges_table},
            {"name": "Nodes", "columns": ["project", "out_degree", "in_degree", "out_weight", "in_weight"], "rows": nodes_table},
            {"name": "Clusters", "columns": ["cluster_id", "size", "members"], "rows": clusters_table}
        ],
        "figures": []
    }
    
    result = _sanitize(result)
    print(json.dumps(result, indent=2))
    sys.exit(0)


if __name__ == "__main__":
    main()
