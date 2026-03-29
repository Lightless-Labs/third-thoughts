#!/usr/bin/env python3
"""
Cross-project knowledge flow graph analysis.
Adapted for Third Thoughts corpus at corpus/claude-code/ and corpus/claude-ai/.

Scans Claude Code session transcripts for cross-project references,
builds a directed graph, computes graph metrics, classifies reference
types, and performs temporal analysis.
"""

import json
import os
import re
import sys
from collections import defaultdict, Counter
from datetime import datetime
from pathlib import Path
import textwrap

# --- Configuration -----------------------------------------------------------

CORPUS_ROOT = Path(os.environ.get("MIDDENS_CORPUS", "corpus/"))
OUTPUT_DIR = Path(os.environ.get("MIDDENS_OUTPUT", "experiments/"))

# We'll dynamically discover projects from the corpus directory structure.


def discover_projects():
    """Discover all project directories and their JSONL files from the corpus.

    Uses os.walk(followlinks=True) to traverse symlinked source dirs.
    Groups JSONL files by project name derived from path.
    """
    projects = {}  # project_name -> list of jsonl paths

    for root, dirs, filenames in os.walk(str(CORPUS_ROOT), followlinks=True):
        jsonl_files = [f for f in filenames if f.endswith(".jsonl")]
        if not jsonl_files:
            continue

        root_path = Path(root)
        # Derive project name from the directory hierarchy
        parts = root.split("/")

        # Try to find project name from path
        project_name = root_path.name
        for i, p in enumerate(parts):
            if p == "projects" and i + 1 < len(parts):
                project_name = extract_project_name_cc(parts[i + 1])
                break

        # Canonicalize
        project_name = canonicalize(project_name)

        if project_name not in projects:
            projects[project_name] = []
        for fn in jsonl_files:
            projects[project_name].append(root_path / fn)

    return projects


def extract_project_name_cc(dirname):
    """Extract a readable project name from a Claude Code project dirname."""
    # Examples: -Users-<operator>-projects-Sources-App-iOS-Sources
    #           -Users-<operator>-projects-workspaces-fix-some-crash
    #           -private-tmp-Purchasely-iOS-Sources-Example

    # Remove leading dash
    name = dirname.lstrip("-")

    # Try to extract the meaningful suffix
    # Pattern: Users-<user>-projects-<rest>
    parts = name.split("-")

    # Find 'projects' keyword and take everything after
    for i, p in enumerate(parts):
        if p.lower() == "projects":
            rest = "-".join(parts[i + 1:])
            if rest:
                return rest

    # Pattern: private-tmp-<rest>
    if name.startswith("private-tmp-"):
        rest = name[len("private-tmp-"):]
        if rest:
            return rest

    # Pattern: Users-<user>-sandbox-<rest>
    for i, p in enumerate(parts):
        if p.lower() == "sandbox":
            rest = "-".join(parts[i + 1:])
            if rest:
                return f"sandbox-{rest}"

    return name


def extract_project_name_ai(dirname):
    """Extract a readable project name from a Claude AI project dirname."""
    name = dirname.lstrip("-")
    parts = name.split("-")
    for i, p in enumerate(parts):
        if p.lower() == "projects":
            rest = "-".join(parts[i + 1:])
            if rest:
                return rest
    return name


# Canonical name mapping (handle variants, normalize)
CANONICAL = {
    "Sources-Purchasely-Support": "Purchasely-Support",
    "Sources-Purchasely-develop": "Purchasely-develop",
    "Sources-Purchasely-iOS-Sources": "Purchasely-iOS",
    "Sources-Purchasely-iOS-Sources--claude-worktrees-keen-oak-ovfz": "Purchasely-iOS",
    "Sources-Purchasely-iOS-Sources-Example": "Purchasely-iOS-Example",
    "Sources-purchasely-console": "purchasely-console",
    "Sources-purchasely-console-packages-standalone-presentation-renderer": "purchasely-console",
    "Sources": "Sources-root",
    "workspaces-feat-app-bundle-id-and-api-key-in-mcp": "workspaces",
    "workspaces-feat-rename-sDeeplinkHandled-and-isReadyToOpenDeeplink": "workspaces",
    "workspaces-fix-sample-app-deeplinks": "workspaces",
    "workspaces-fix-sample-app-error-loop-Example": "workspaces",
    "workspaces-fix-surfshark-crash": "workspaces",
    "workspaces-gherkin-and-cucumber": "workspaces",
    "workspaces-iOS-feat-non-dismissable-flow-drawers": "workspaces",
    "workspaces-iOS-fix-bandlab-crash": "workspaces",
    "workspaces-iOS-nomadeducation": "workspaces",
    "workspaces-openclaw": "workspaces-openclaw",
    "Purchasely-iOS-Sources": "Purchasely-iOS",
    "Purchasely-iOS-Sources-Example": "Purchasely-iOS-Example",
    "demo": "demo",
    "feat-display-api": "workspaces",
    "feat-refactor-productvc": "workspaces",
    "feat-spm-migration-take-2-sandbox": "workspaces",
    "feat-spm-refactor-third-time-is-the-charm": "workspaces",
    "fix-infinite-layout-subviews": "workspaces",
    "fix-navigation-bar-color": "workspaces",
    "infrastructure": "infrastructure",
}


def canonicalize(name):
    """Return canonical project name."""
    if name in CANONICAL:
        return CANONICAL[name]
    return name


def build_reference_patterns(all_project_names):
    """Build regex patterns for detecting project references."""
    patterns = {}
    # Common words that are likely false positives
    SKIP = {"projects", "sources", "root", "tmp", "private", "users", "example", "demo",
            "sandbox", "test", "video", "feat", "fix"}

    for raw_name in all_project_names:
        canon = canonicalize(raw_name)
        if canon not in patterns:
            patterns[canon] = []

        # Generate search tokens from the project name
        tokens = set()
        # Use the full canonical name
        if len(canon) > 4 and canon.lower() not in SKIP:
            tokens.add(canon)
        # Also split on hyphens and use significant parts
        for part in canon.split("-"):
            if len(part) > 4 and part.lower() not in SKIP:
                tokens.add(part)

        for token in tokens:
            escaped = re.escape(token)
            pattern = re.compile(
                r'(?:^|[\s/\'"(,])' + escaped + r'(?:[\s/\'")\-.,;:!?]|$)',
                re.IGNORECASE
            )
            patterns[canon].append(pattern)

    return patterns


# --- Reference Type Classification -------------------------------------------

REFERENCE_TYPES = {
    "implementation": re.compile(
        r'(?:look at (?:how|what)|same (?:as|pattern|approach)|'
        r'follow(?:ing|s)? the .* pattern|like .* does|'
        r'similar to|copy from|based on|modeled (?:on|after)|'
        r'reuse|replicate|mirror)',
        re.IGNORECASE
    ),
    "context_import": re.compile(
        r'(?:CLAUDE\.md|claude\.md|README|\.claude/|'
        r'read .* (?:config|setup|instructions)|'
        r'check .* (?:docs?|documentation)|'
        r'look at .* (?:CLAUDE|readme|config))',
        re.IGNORECASE
    ),
    "knowledge_sharing": re.compile(
        r'(?:solution in|learned from|docs?/|'
        r'there(?:\'s| is) a .* in|'
        r'we (?:figured out|solved|found)|'
        r'pattern (?:from|in)|approach (?:from|in)|'
        r'technique (?:from|in)|already (?:solved|handled))',
        re.IGNORECASE
    ),
    "cross_project_action": re.compile(
        r'(?:push to|commit (?:to|in)|leave a note|'
        r'update .* in|create .* in|add .* to|'
        r'write .* (?:to|in)|deploy|merge (?:to|into)|'
        r'PR (?:to|in|for)|pull request)',
        re.IGNORECASE
    ),
}


def classify_reference(context: str) -> str:
    """Classify a reference by examining surrounding context."""
    for ref_type, pattern in REFERENCE_TYPES.items():
        if pattern.search(context):
            return ref_type
    return "mention"


# --- Core Analysis -----------------------------------------------------------

def extract_messages(jsonl_path: Path):
    """Yield (timestamp, role, text) for each message in a JSONL file."""
    try:
        with open(jsonl_path, 'r', errors='replace') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                rec_type = obj.get("type", "")
                if rec_type not in ("user", "assistant"):
                    continue
                msg = obj.get("message", {})
                content = msg.get("content", "")
                if isinstance(content, list):
                    parts = []
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "text":
                            parts.append(block.get("text", ""))
                    content = " ".join(parts)
                if not isinstance(content, str) or not content.strip():
                    continue

                timestamp = obj.get("timestamp")
                ts = None
                if timestamp and isinstance(timestamp, str):
                    try:
                        ts = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                    except (ValueError, TypeError):
                        pass
                elif timestamp and isinstance(timestamp, (int, float)):
                    try:
                        ts = datetime.fromtimestamp(timestamp / 1000 if timestamp > 1e12 else timestamp)
                    except (ValueError, OSError):
                        pass
                if ts is None:
                    try:
                        ts = datetime.fromtimestamp(jsonl_path.stat().st_mtime)
                    except OSError:
                        ts = datetime(2025, 1, 1)

                yield ts, rec_type, content
    except (OSError, IOError) as e:
        print(f"  Warning: Could not read {jsonl_path}: {e}", file=sys.stderr)


def scan_projects(projects_dict):
    """Scan all project sessions and build the reference graph."""
    all_canonical = sorted(set(canonicalize(n) for n in projects_dict.keys()))
    ref_patterns = build_reference_patterns(list(projects_dict.keys()))

    edges = defaultdict(Counter)
    edge_types = defaultdict(lambda: defaultdict(Counter))
    temporal = defaultdict(list)
    reference_contexts = defaultdict(list)
    project_session_counts = Counter()
    project_message_counts = Counter()

    for raw_name, jsonl_files in sorted(projects_dict.items()):
        src_project = canonicalize(raw_name)
        if not jsonl_files:
            continue

        project_session_counts[src_project] += len(jsonl_files)
        print(f"  Scanning {src_project}: {len(jsonl_files)} sessions")

        for jsonl_file in jsonl_files:
            for ts, role, text in extract_messages(jsonl_file):
                project_message_counts[src_project] += 1

                for dst_project, pats in ref_patterns.items():
                    if dst_project == src_project:
                        continue
                    for pattern in pats:
                        matches = list(pattern.finditer(text))
                        for match in matches:
                            edges[src_project][dst_project] += 1

                            start = max(0, match.start() - 100)
                            end = min(len(text), match.end() + 100)
                            context = text[start:end].strip()

                            wider_start = max(0, match.start() - 200)
                            wider_end = min(len(text), match.end() + 200)
                            wider_context = text[wider_start:wider_end]
                            ref_type = classify_reference(wider_context)

                            edge_types[src_project][dst_project][ref_type] += 1
                            temporal[(src_project, dst_project)].append(ts)

                            if len(reference_contexts[(src_project, dst_project)]) < 5:
                                reference_contexts[(src_project, dst_project)].append(
                                    (context[:200], ref_type)
                                )
                            break

    return edges, edge_types, temporal, reference_contexts, project_session_counts, project_message_counts


def compute_graph_metrics(edges):
    """Compute hub/authority scores, degree centrality, clusters."""
    all_nodes = set()
    for src in edges:
        all_nodes.add(src)
        for dst in edges[src]:
            all_nodes.add(dst)

    out_degree = {}
    out_weight = {}
    for node in all_nodes:
        out_degree[node] = len(edges.get(node, {}))
        out_weight[node] = sum(edges.get(node, {}).values())

    in_degree = defaultdict(int)
    in_weight = defaultdict(int)
    for src in edges:
        for dst, weight in edges[src].items():
            in_degree[dst] += 1
            in_weight[dst] += weight

    hubs = sorted(all_nodes, key=lambda n: out_weight.get(n, 0), reverse=True)
    authorities = sorted(all_nodes, key=lambda n: in_weight.get(n, 0), reverse=True)

    clusters = []
    visited = set()

    def dfs(node, cluster):
        if node in visited:
            return
        visited.add(node)
        cluster.add(node)
        for dst in edges.get(node, {}):
            dfs(dst, cluster)
        for src in edges:
            if node in edges[src]:
                dfs(src, cluster)

    for node in all_nodes:
        if node not in visited:
            cluster = set()
            dfs(node, cluster)
            if len(cluster) > 1:
                clusters.append(cluster)

    mutual = []
    for src in edges:
        for dst in edges[src]:
            if src in edges.get(dst, {}):
                pair = tuple(sorted([src, dst]))
                if pair not in mutual:
                    mutual.append(pair)

    return {
        "out_degree": out_degree,
        "out_weight": out_weight,
        "in_degree": dict(in_degree),
        "in_weight": dict(in_weight),
        "hubs": hubs,
        "authorities": authorities,
        "clusters": clusters,
        "mutual_pairs": mutual,
        "all_nodes": all_nodes,
    }


def temporal_analysis(temporal_data):
    """Analyze temporal patterns in cross-project references."""
    if not temporal_data:
        return {}

    monthly = defaultdict(Counter)
    for (src, dst), timestamps in temporal_data.items():
        for ts in timestamps:
            month_key = ts.strftime("%Y-%m")
            monthly[month_key][(src, dst)] += 1

    monthly_totals = {}
    for month, pairs in sorted(monthly.items()):
        monthly_totals[month] = sum(pairs.values())

    first_referenced = {}
    for (src, dst), timestamps in temporal_data.items():
        if timestamps:
            earliest = min(timestamps)
            if dst not in first_referenced or earliest < first_referenced[dst]:
                first_referenced[dst] = earliest

    first_active = {}
    for (src, dst), timestamps in temporal_data.items():
        if timestamps:
            earliest = min(timestamps)
            if src not in first_active or earliest < first_active[src]:
                first_active[src] = earliest

    return {
        "monthly_totals": monthly_totals,
        "first_referenced": first_referenced,
        "first_active": first_active,
    }


def generate_dot(edges, metrics):
    """Generate Graphviz DOT format."""
    lines = [
        'digraph cross_project_knowledge_flow {',
        '  rankdir=LR;',
        '  node [shape=box, style="rounded,filled", fontname="Helvetica"];',
        '  edge [fontname="Helvetica", fontsize=9];',
        '',
    ]

    max_in = max(metrics["in_weight"].values()) if metrics["in_weight"] else 1
    max_out = max(metrics["out_weight"].values()) if metrics["out_weight"] else 1

    for node in sorted(metrics["all_nodes"]):
        in_w = metrics["in_weight"].get(node, 0)
        out_w = metrics["out_weight"].get(node, 0)
        total = in_w + out_w
        fontsize = 10 + min(total // 5, 10)

        if in_w > out_w and in_w > 0:
            intensity = min(int(200 * in_w / max_in) + 55, 255)
            color = f'"#{255 - intensity:02x}{255 - intensity // 2:02x}FF"'
        elif out_w > 0:
            intensity = min(int(200 * out_w / max_out) + 55, 255)
            color = f'"#FF{255 - intensity // 2:02x}{255 - intensity:02x}"'
        else:
            color = '"#EEEEEE"'

        label = f'{node}\\nin:{in_w} out:{out_w}'
        lines.append(f'  "{node}" [label="{label}", fillcolor={color}, fontsize={fontsize}];')

    lines.append('')

    max_weight = max(
        (w for src in edges for w in edges[src].values()),
        default=1
    )

    for src in sorted(edges):
        for dst in sorted(edges[src]):
            weight = edges[src][dst]
            penwidth = 1 + 3 * weight / max_weight
            lines.append(
                f'  "{src}" -> "{dst}" [label="{weight}", penwidth={penwidth:.1f}];'
            )

    lines.append('}')
    return '\n'.join(lines)


def generate_adjacency_matrix(edges, metrics):
    """Generate an adjacency matrix in text format."""
    nodes = sorted(metrics["all_nodes"])
    if not nodes:
        return "No nodes found."

    abbrev = {}
    for n in nodes:
        if len(n) > 10:
            abbrev[n] = n[:9] + "."
        else:
            abbrev[n] = n

    col_width = 6
    header = " " * 14 + "".join(f"{abbrev[n]:>{col_width}}" for n in nodes)
    lines = [header, " " * 14 + "-" * (col_width * len(nodes))]

    for src in nodes:
        row = f"{abbrev[src]:>13} |"
        for dst in nodes:
            val = edges.get(src, {}).get(dst, 0)
            if val == 0:
                row += f"{'·':>{col_width}}"
            else:
                row += f"{val:>{col_width}}"
        lines.append(row)

    return '\n'.join(lines)


def generate_report(edges, edge_types, temporal_data, reference_contexts,
                    session_counts, message_counts, metrics, temp_analysis):
    """Generate the full markdown report."""

    report = []
    report.append("# Cross-Project Knowledge Flow Graph (Third Thoughts Corpus)")
    report.append("")
    report.append(f"**Date**: {datetime.now().strftime('%Y-%m-%d')}")
    report.append("**Method**: Graph/network analysis of cross-project references in Claude Code session transcripts")
    report.append(f"**Scope**: {sum(session_counts.values())} sessions across {len(session_counts)} projects, {sum(message_counts.values())} messages")
    report.append("")

    report.append("## Overview")
    report.append("")
    total_edges = sum(w for src in edges for w in edges[src].values())
    unique_edges = sum(len(edges[src]) for src in edges)
    report.append(f"- **Total cross-project references**: {total_edges}")
    report.append(f"- **Unique directed edges**: {unique_edges}")
    report.append(f"- **Projects involved**: {len(metrics['all_nodes'])}")
    report.append(f"- **Mutual reference pairs**: {len(metrics['mutual_pairs'])}")
    report.append("")

    report.append("## Hubs and Authorities")
    report.append("")
    report.append("### Authorities (most referenced by other projects)")
    report.append("")
    report.append("| Rank | Project | In-degree | In-weight | Referenced by |")
    report.append("|------|---------|-----------|-----------|---------------|")
    for i, node in enumerate(metrics["authorities"][:15]):
        in_d = metrics["in_degree"].get(node, 0)
        in_w = metrics["in_weight"].get(node, 0)
        if in_w == 0:
            continue
        referrers = [src for src in edges if node in edges[src]]
        report.append(f"| {i+1} | **{node}** | {in_d} | {in_w} | {', '.join(sorted(referrers))} |")
    report.append("")

    report.append("### Hubs (reference the most other projects)")
    report.append("")
    report.append("| Rank | Project | Out-degree | Out-weight | References |")
    report.append("|------|---------|------------|------------|------------|")
    for i, node in enumerate(metrics["hubs"][:15]):
        out_d = metrics["out_degree"].get(node, 0)
        out_w = metrics["out_weight"].get(node, 0)
        if out_w == 0:
            continue
        targets = list(edges.get(node, {}).keys())
        report.append(f"| {i+1} | **{node}** | {out_d} | {out_w} | {', '.join(sorted(targets))} |")
    report.append("")

    if metrics["mutual_pairs"]:
        report.append("### Mutual Reference Pairs (bidirectional knowledge flow)")
        report.append("")
        for a, b in sorted(metrics["mutual_pairs"]):
            w_ab = edges.get(a, {}).get(b, 0)
            w_ba = edges.get(b, {}).get(a, 0)
            report.append(f"- **{a}** <-> **{b}** ({a}->{b}: {w_ab}, {b}->{a}: {w_ba})")
        report.append("")

    if metrics["clusters"]:
        report.append("### Clusters (connected components)")
        report.append("")
        for i, cluster in enumerate(sorted(metrics["clusters"], key=len, reverse=True)):
            report.append(f"- **Cluster {i+1}** ({len(cluster)} projects): {', '.join(sorted(cluster))}")
        report.append("")

    report.append("## Reference Type Classification")
    report.append("")
    type_totals = Counter()
    for src in edge_types:
        for dst in edge_types[src]:
            for ref_type, count in edge_types[src][dst].items():
                type_totals[ref_type] += count

    report.append("| Type | Count | Percentage |")
    report.append("|------|-------|------------|")
    total_typed = sum(type_totals.values())
    for ref_type, count in type_totals.most_common():
        pct = 100 * count / total_typed if total_typed else 0
        report.append(f"| {ref_type} | {count} | {pct:.1f}% |")
    report.append("")

    report.append("### Sample Reference Contexts")
    report.append("")
    shown = 0
    for (src, dst), contexts in sorted(reference_contexts.items(),
                                        key=lambda x: edges.get(x[0][0], {}).get(x[0][1], 0),
                                        reverse=True):
        if shown >= 10:
            break
        weight = edges.get(src, {}).get(dst, 0)
        report.append(f"**{src} -> {dst}** (weight: {weight}):")
        for ctx, rtype in contexts[:2]:
            clean = ctx.replace('\n', ' ').replace('`', "'")
            report.append(f"- [{rtype}] `{clean[:150]}`")
        report.append("")
        shown += 1

    report.append("## Temporal Analysis")
    report.append("")
    if temp_analysis.get("monthly_totals"):
        report.append("### Monthly Reference Volume")
        report.append("")
        report.append("| Month | References |")
        report.append("|-------|------------|")
        for month, count in sorted(temp_analysis["monthly_totals"].items()):
            bar = "#" * min(count, 50)
            report.append(f"| {month} | {count} {bar} |")
        report.append("")

    if temp_analysis.get("first_referenced"):
        report.append("### Project Timeline (first referenced by others)")
        report.append("")
        for proj, ts in sorted(temp_analysis["first_referenced"].items(), key=lambda x: x[1]):
            report.append(f"- **{proj}**: first referenced {ts.strftime('%Y-%m-%d')}")
        report.append("")

    report.append("## Graph Visualization")
    report.append("")
    report.append("```dot")
    report.append(generate_dot(edges, metrics))
    report.append("```")
    report.append("")

    report.append("### Adjacency Matrix")
    report.append("")
    report.append("```")
    report.append(generate_adjacency_matrix(edges, metrics))
    report.append("```")
    report.append("")

    report.append("## Complete Edge List")
    report.append("")
    report.append("| Source | Target | Weight | Types |")
    report.append("|--------|--------|--------|-------|")
    all_edges = []
    for src in edges:
        for dst, weight in edges[src].items():
            types = dict(edge_types.get(src, {}).get(dst, {}))
            all_edges.append((src, dst, weight, types))
    all_edges.sort(key=lambda x: x[2], reverse=True)
    for src, dst, weight, types in all_edges:
        type_str = ", ".join(f"{t}:{c}" for t, c in sorted(types.items(), key=lambda x: -x[1]))
        report.append(f"| {src} | {dst} | {weight} | {type_str} |")
    report.append("")

    report.append("## Project Statistics")
    report.append("")
    report.append("| Project | Sessions | Messages | Out-refs | In-refs |")
    report.append("|---------|----------|----------|----------|---------|")
    all_projects = sorted(set(list(session_counts.keys()) + list(metrics["all_nodes"])))
    for proj in all_projects:
        sessions = session_counts.get(proj, 0)
        messages = message_counts.get(proj, 0)
        out_w = metrics["out_weight"].get(proj, 0)
        in_w = metrics["in_weight"].get(proj, 0)
        report.append(f"| {proj} | {sessions} | {messages} | {out_w} | {in_w} |")
    report.append("")

    return '\n'.join(report)


def main():
    print("=" * 60)
    print("Cross-Project Knowledge Flow Graph Analysis")
    print("(Third Thoughts Corpus)")
    print("=" * 60)
    print()

    print("Step 1: Discovering projects from corpus...")
    projects = discover_projects()
    total_files = sum(len(v) for v in projects.values())
    print(f"  Found {len(projects)} projects with {total_files} total JSONL files")
    print()

    print("Step 2: Scanning sessions for cross-project references...")
    edges, edge_types, temporal_data, reference_contexts, session_counts, message_counts = scan_projects(projects)
    print(f"\nFound {sum(w for s in edges for w in edges[s].values())} total references across {sum(len(edges[s]) for s in edges)} unique edges")
    print()

    print("Step 3: Computing graph metrics...")
    metrics = compute_graph_metrics(edges)
    print(f"  Nodes: {len(metrics['all_nodes'])}")
    if metrics['hubs']:
        print(f"  Hubs: {', '.join(metrics['hubs'][:5])}")
    if metrics['authorities']:
        print(f"  Authorities: {', '.join(metrics['authorities'][:5])}")
    print(f"  Clusters: {len(metrics['clusters'])}")
    print()

    print("Step 4: Temporal analysis...")
    temp_analysis = temporal_analysis(temporal_data)
    if temp_analysis.get("monthly_totals"):
        for month, count in sorted(temp_analysis["monthly_totals"].items()):
            print(f"  {month}: {count}")
    print()

    print("Step 5: Generating report...")
    report = generate_report(edges, edge_types, temporal_data, reference_contexts,
                            session_counts, message_counts, metrics, temp_analysis)

    output_path = OUTPUT_DIR / "007-cross-project-graph.md"
    output_path.write_text(report)
    print(f"  Report written to {output_path}")

    dot_path = OUTPUT_DIR / "007-cross-project-flow.dot"
    dot_path.write_text(generate_dot(edges, metrics))
    print(f"  DOT file written to {dot_path}")

    print()
    print("Done!")


if __name__ == "__main__":
    main()
