#!/usr/bin/env python3
"""
Ecological diversity analysis of Claude Code session tool usage.

Treats each tool type as a "species" and each session as a "site",
then applies standard ecological diversity metrics.
"""

import json
import glob
import math
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

# ── Configuration ──────────────────────────────────────────────────────────

CORPUS_DIR = os.environ.get("MIDDENS_CORPUS", "corpus/")
OUTPUT_DIR = Path(os.environ.get("MIDDENS_OUTPUT", "experiments/"))
FIGURES_DIR = OUTPUT_DIR / "figures"
FIGURES_DIR.mkdir(parents=True, exist_ok=True)

# ── Data Extraction ────────────────────────────────────────────────────────

def extract_session_data(filepath):
    """Extract tool usage, corrections, and metadata from a JSONL session."""
    tools = Counter()
    user_msgs = 0
    assistant_msgs = 0
    corrections = 0  # user messages that follow an assistant message (proxy for correction)
    total_lines = 0
    last_was_assistant = False

    try:
        with open(filepath) as f:
            for line in f:
                total_lines += 1
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue

                msg_type = rec.get("type")

                if msg_type == "assistant":
                    assistant_msgs += 1
                    last_was_assistant = True
                    msg = rec.get("message", {})
                    for block in msg.get("content", []):
                        if block.get("type") == "tool_use":
                            tools[block.get("name", "unknown")] += 1
                elif msg_type == "user":
                    user_msgs += 1
                    if last_was_assistant and user_msgs > 1:
                        # Heuristic: multi-turn exchanges imply corrections/guidance
                        corrections += 1
                    last_was_assistant = False
                else:
                    last_was_assistant = False
    except Exception as e:
        return None

    if not tools:
        return None

    return {
        "file": filepath,
        "session_id": Path(filepath).stem,
        "tools": dict(tools),
        "total_tool_calls": sum(tools.values()),
        "distinct_tools": len(tools),
        "user_msgs": user_msgs,
        "assistant_msgs": assistant_msgs,
        "corrections": corrections,
        "correction_rate": corrections / max(user_msgs, 1),
        "session_length": user_msgs + assistant_msgs,
        "total_lines": total_lines,
    }


def find_all_session_files(corpus_dir):
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


def load_all_sessions(max_per_project=None, exclude_autonomous=False):
    """Load sessions from the Third Thoughts corpus."""
    found = find_all_session_files(CORPUS_DIR)
    sessions = []

    # Group by project
    project_files = defaultdict(list)
    for fpath, proj_name in found:
        project_files[proj_name].append(fpath)

    for proj_name, files in sorted(project_files.items()):
        files = sorted(files)
        if max_per_project:
            files = files[:max_per_project]

        for fpath in files:
            data = extract_session_data(fpath)
            if data:
                data["project"] = proj_name
                sessions.append(data)

    return sessions


# ── Diversity Metrics ──────────────────────────────────────────────────────

def shannon_diversity(counts):
    """Shannon diversity index H = -Σ(pi * ln(pi))"""
    total = sum(counts.values())
    if total == 0:
        return 0.0
    H = 0.0
    for count in counts.values():
        if count > 0:
            p = count / total
            H -= p * math.log(p)
    return H


def simpson_diversity(counts):
    """Simpson diversity index D = 1 - Σ(pi²)"""
    total = sum(counts.values())
    if total <= 1:
        return 0.0
    D = 0.0
    for count in counts.values():
        p = count / total
        D += p * p
    return 1.0 - D


def evenness(counts):
    """Pielou's evenness E = H / ln(S)"""
    S = len([c for c in counts.values() if c > 0])
    if S <= 1:
        return 1.0  # By convention
    H = shannon_diversity(counts)
    return H / math.log(S)


def dominance_ratio(counts):
    """Proportion of total calls made by the most-used tool."""
    total = sum(counts.values())
    if total == 0:
        return 0.0
    return max(counts.values()) / total


def dominant_tool(counts):
    """Name of the most-used tool."""
    if not counts:
        return "none"
    return max(counts, key=counts.get)


# ── Beta Diversity ─────────────────────────────────────────────────────────

def jaccard_similarity(set_a, set_b):
    """Jaccard similarity = |A ∩ B| / |A ∪ B|"""
    intersection = set_a & set_b
    union = set_a | set_b
    if not union:
        return 0.0
    return len(intersection) / len(union)


def bray_curtis_dissimilarity(counts_a, counts_b):
    """Bray-Curtis dissimilarity between two abundance vectors."""
    all_tools = set(counts_a.keys()) | set(counts_b.keys())
    if not all_tools:
        return 0.0

    # Normalize to proportions
    total_a = sum(counts_a.values())
    total_b = sum(counts_b.values())
    if total_a == 0 or total_b == 0:
        return 1.0

    sum_min = 0
    sum_total = 0
    for tool in all_tools:
        pa = counts_a.get(tool, 0) / total_a
        pb = counts_b.get(tool, 0) / total_b
        sum_min += min(pa, pb)
        sum_total += pa + pb

    return 1.0 - (2 * sum_min / sum_total)


# ── Analysis Functions ─────────────────────────────────────────────────────

def analysis_1_diversity_indices(sessions):
    """Shannon and Simpson diversity indices per session."""
    results = []
    for s in sessions:
        counts = Counter(s["tools"])
        results.append({
            "session_id": s["session_id"][:12],
            "project": s["project"],
            "H": shannon_diversity(counts),
            "D": simpson_diversity(counts),
            "E": evenness(counts),
            "S": s["distinct_tools"],
            "N": s["total_tool_calls"],
            "correction_rate": s["correction_rate"],
            "session_length": s["session_length"],
            "dominant": dominant_tool(counts),
            "dominance": dominance_ratio(counts),
        })
    return results


def analysis_2_species_area(sessions):
    """Species-area relationship: tools vs session length."""
    points = []
    for s in sessions:
        if s["session_length"] > 0:
            points.append({
                "session_length": s["session_length"],
                "distinct_tools": s["distinct_tools"],
                "total_tool_calls": s["total_tool_calls"],
                "project": s["project"],
                "log_length": math.log(max(s["session_length"], 1)),
            })
    return points


def analysis_3_dominance(sessions):
    """Classify sessions as monoculture vs diverse ecosystem."""
    monocultures = []
    diverse = []

    for s in sessions:
        counts = Counter(s["tools"])
        dr = dominance_ratio(counts)
        info = {
            "session_id": s["session_id"][:12],
            "project": s["project"],
            "dominance": dr,
            "dominant_tool": dominant_tool(counts),
            "H": shannon_diversity(counts),
            "correction_rate": s["correction_rate"],
            "session_length": s["session_length"],
            "distinct_tools": s["distinct_tools"],
            "total_tool_calls": s["total_tool_calls"],
        }
        if dr > 0.80:
            monocultures.append(info)
        else:
            diverse.append(info)

    return monocultures, diverse


def analysis_4_beta_diversity(sessions):
    """Beta diversity across projects using Jaccard and Bray-Curtis."""
    # Aggregate tool usage per project
    project_tools = defaultdict(Counter)
    project_tool_sets = defaultdict(set)

    for s in sessions:
        proj = s["project"]
        project_tools[proj] += Counter(s["tools"])
        project_tool_sets[proj] |= set(s["tools"].keys())

    projects = sorted(project_tools.keys())
    n = len(projects)

    jaccard_matrix = np.zeros((n, n))
    bray_curtis_matrix = np.zeros((n, n))

    for i in range(n):
        for j in range(n):
            jaccard_matrix[i][j] = jaccard_similarity(
                project_tool_sets[projects[i]],
                project_tool_sets[projects[j]]
            )
            bray_curtis_matrix[i][j] = bray_curtis_dissimilarity(
                project_tools[projects[i]],
                project_tools[projects[j]]
            )

    return projects, jaccard_matrix, bray_curtis_matrix, project_tools


# ── Plotting ───────────────────────────────────────────────────────────────

def plot_all(sessions, diversity_results, species_area_points, monocultures, diverse,
             projects, jaccard_matrix, bray_curtis_matrix, project_tools):
    """Generate all figures."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import Normalize
    import matplotlib.cm as cm

    # ── Figure 1: Shannon vs Simpson scatter ──
    fig, axes = plt.subplots(1, 3, figsize=(18, 5))

    Hs = [r["H"] for r in diversity_results]
    Ds = [r["D"] for r in diversity_results]
    Es = [r["E"] for r in diversity_results]
    corr_rates = [r["correction_rate"] for r in diversity_results]
    lengths = [r["session_length"] for r in diversity_results]

    ax = axes[0]
    sc = ax.scatter(Hs, Ds, c=corr_rates, cmap="RdYlGn_r", alpha=0.7, edgecolors="k", linewidth=0.5)
    plt.colorbar(sc, ax=ax, label="Correction Rate")
    ax.set_xlabel("Shannon H")
    ax.set_ylabel("Simpson D")
    ax.set_title("Shannon vs Simpson Diversity\n(color = correction rate)")

    ax = axes[1]
    sc = ax.scatter(Hs, corr_rates, c=lengths, cmap="viridis", alpha=0.7, edgecolors="k", linewidth=0.5)
    plt.colorbar(sc, ax=ax, label="Session Length")
    ax.set_xlabel("Shannon H")
    ax.set_ylabel("Correction Rate")
    ax.set_title("Diversity vs Correction Rate\n(color = session length)")

    ax = axes[2]
    sc = ax.scatter(Es, corr_rates, c=[r["S"] for r in diversity_results], cmap="plasma", alpha=0.7, edgecolors="k", linewidth=0.5)
    plt.colorbar(sc, ax=ax, label="# Distinct Tools (S)")
    ax.set_xlabel("Evenness E")
    ax.set_ylabel("Correction Rate")
    ax.set_title("Evenness vs Correction Rate\n(color = tool richness)")

    plt.tight_layout()
    fig.savefig(FIGURES_DIR / "eco_diversity_indices.png", dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved: eco_diversity_indices.png")

    # ── Figure 2: Species-Area Relationship ──
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))

    sa_lengths = [p["session_length"] for p in species_area_points]
    sa_tools = [p["distinct_tools"] for p in species_area_points]
    sa_log_lengths = [p["log_length"] for p in species_area_points]

    ax = axes[0]
    ax.scatter(sa_lengths, sa_tools, alpha=0.5, edgecolors="k", linewidth=0.3)
    ax.set_xlabel("Session Length (messages)")
    ax.set_ylabel("Distinct Tools Used (S)")
    ax.set_title("Species-Area: Tools vs Session Length")

    # Fit log curve
    if len(sa_log_lengths) > 2:
        coeffs = np.polyfit(sa_log_lengths, sa_tools, 1)
        x_fit = np.linspace(min(sa_log_lengths), max(sa_log_lengths), 100)
        y_fit = np.polyval(coeffs, x_fit)
        ax_log = axes[1]
        ax_log.scatter(sa_log_lengths, sa_tools, alpha=0.5, edgecolors="k", linewidth=0.3)
        ax_log.plot(x_fit, y_fit, "r-", linewidth=2, label=f"S = {coeffs[0]:.2f} * ln(L) + {coeffs[1]:.2f}")
        ax_log.set_xlabel("ln(Session Length)")
        ax_log.set_ylabel("Distinct Tools Used (S)")
        ax_log.set_title("Log-Linear Species-Area Fit")
        ax_log.legend()

        # R-squared
        ss_res = sum((t - np.polyval(coeffs, l))**2 for t, l in zip(sa_tools, sa_log_lengths))
        ss_tot = sum((t - np.mean(sa_tools))**2 for t in sa_tools)
        r_squared = 1 - ss_res / ss_tot if ss_tot > 0 else 0
        ax_log.annotate(f"R² = {r_squared:.3f}", xy=(0.05, 0.95), xycoords="axes fraction",
                       fontsize=12, verticalalignment="top",
                       bbox=dict(boxstyle="round", facecolor="wheat", alpha=0.5))

    plt.tight_layout()
    fig.savefig(FIGURES_DIR / "eco_species_area.png", dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved: eco_species_area.png")

    # ── Figure 3: Monoculture vs Diverse comparison ──
    fig, axes = plt.subplots(1, 3, figsize=(16, 5))

    mono_corrections = [m["correction_rate"] for m in monocultures]
    div_corrections = [d["correction_rate"] for d in diverse]
    mono_lengths = [m["session_length"] for m in monocultures]
    div_lengths = [d["session_length"] for d in diverse]

    ax = axes[0]
    ax.boxplot([mono_corrections, div_corrections], labels=["Monoculture\n(>80% one tool)", "Diverse\nEcosystem"])
    ax.set_ylabel("Correction Rate")
    ax.set_title("Correction Rate by Session Type")

    ax = axes[1]
    ax.boxplot([mono_lengths, div_lengths], labels=["Monoculture", "Diverse"])
    ax.set_ylabel("Session Length (messages)")
    ax.set_title("Session Length by Type")

    # Dominant tool distribution in monocultures
    ax = axes[2]
    mono_tools = Counter(m["dominant_tool"] for m in monocultures)
    if mono_tools:
        tools_sorted = sorted(mono_tools.items(), key=lambda x: -x[1])
        ax.barh([t[0] for t in tools_sorted], [t[1] for t in tools_sorted], color="salmon")
        ax.set_xlabel("# Monoculture Sessions")
        ax.set_title("Dominant Tool in Monocultures")

    plt.tight_layout()
    fig.savefig(FIGURES_DIR / "eco_dominance.png", dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved: eco_dominance.png")

    # ── Figure 4: Beta Diversity Heatmaps ──
    n_proj = len(projects)
    if n_proj > 2:
        # Shorten project names for display
        short_names = [p[:16] for p in projects]

        fig, axes = plt.subplots(1, 2, figsize=(max(12, n_proj * 0.8), max(8, n_proj * 0.5)))

        ax = axes[0]
        im = ax.imshow(jaccard_matrix, cmap="YlGnBu", vmin=0, vmax=1)
        ax.set_xticks(range(n_proj))
        ax.set_xticklabels(short_names, rotation=45, ha="right", fontsize=7)
        ax.set_yticks(range(n_proj))
        ax.set_yticklabels(short_names, fontsize=7)
        ax.set_title("Jaccard Similarity\n(tool presence/absence)")
        plt.colorbar(im, ax=ax)

        ax = axes[1]
        im = ax.imshow(bray_curtis_matrix, cmap="YlOrRd", vmin=0, vmax=1)
        ax.set_xticks(range(n_proj))
        ax.set_xticklabels(short_names, rotation=45, ha="right", fontsize=7)
        ax.set_yticks(range(n_proj))
        ax.set_yticklabels(short_names, fontsize=7)
        ax.set_title("Bray-Curtis Dissimilarity\n(tool usage proportions)")
        plt.colorbar(im, ax=ax)

        plt.tight_layout()
        fig.savefig(FIGURES_DIR / "eco_beta_diversity.png", dpi=150, bbox_inches="tight")
        plt.close()
        print(f"  Saved: eco_beta_diversity.png")

    # ── Figure 5: Per-project tool profiles (stacked bar) ──
    # Only show projects with enough data
    proj_names = [p for p in projects if sum(project_tools[p].values()) >= 10]
    if proj_names:
        all_tool_names = sorted(set(t for p in proj_names for t in project_tools[p]))

        fig, ax = plt.subplots(figsize=(max(10, len(proj_names) * 0.7), 6))

        # Normalize to proportions
        bottoms = np.zeros(len(proj_names))
        colors = plt.cm.tab20(np.linspace(0, 1, len(all_tool_names)))

        for i, tool in enumerate(all_tool_names):
            proportions = []
            for p in proj_names:
                total = sum(project_tools[p].values())
                proportions.append(project_tools[p].get(tool, 0) / total if total > 0 else 0)
            ax.bar(range(len(proj_names)), proportions, bottom=bottoms, label=tool, color=colors[i])
            bottoms += proportions

        ax.set_xticks(range(len(proj_names)))
        ax.set_xticklabels([p[:16] for p in proj_names], rotation=45, ha="right", fontsize=8)
        ax.set_ylabel("Proportion of Tool Calls")
        ax.set_title("Tool Ecosystem Profiles by Project")
        ax.legend(bbox_to_anchor=(1.05, 1), loc="upper left", fontsize=7)

        plt.tight_layout()
        fig.savefig(FIGURES_DIR / "eco_project_profiles.png", dpi=150, bbox_inches="tight")
        plt.close()
        print(f"  Saved: eco_project_profiles.png")


# ── Report Generation ──────────────────────────────────────────────────────

def generate_report(sessions, diversity_results, species_area_points,
                    monocultures, diverse, projects, jaccard_matrix,
                    bray_curtis_matrix, project_tools, sa_coeffs, sa_r2):
    """Generate the experiment markdown report."""

    lines = []
    lines.append("# Experiment 017: Ecological Diversity Analysis of Tool Usage")
    lines.append("")
    lines.append("**Date**: 2026-03-19")
    lines.append("**Method**: Apply ecological diversity indices to Claude Code session tool usage")
    lines.append(f"**Sample**: {len(sessions)} sessions across {len(set(s['project'] for s in sessions))} projects")
    lines.append("")

    # ── Summary statistics ──
    lines.append("## Dataset Overview")
    lines.append("")
    lines.append(f"- **Total sessions analyzed**: {len(sessions)}")
    lines.append(f"- **Total tool calls**: {sum(s['total_tool_calls'] for s in sessions):,}")
    lines.append(f"- **Distinct tool types observed**: {len(set(t for s in sessions for t in s['tools']))}")
    all_tools = Counter()
    for s in sessions:
        all_tools += Counter(s["tools"])
    lines.append(f"- **Most common tools**: {', '.join(f'{t} ({c:,})' for t, c in all_tools.most_common(5))}")
    lines.append("")

    # ── Analysis 1 ──
    lines.append("## Analysis 1: Shannon and Simpson Diversity Indices")
    lines.append("")
    lines.append("![Diversity Indices](figures/eco_diversity_indices.png)")
    lines.append("")

    Hs = [r["H"] for r in diversity_results]
    Ds = [r["D"] for r in diversity_results]
    Es = [r["E"] for r in diversity_results]

    lines.append(f"| Metric | Mean | Median | Min | Max | Std |")
    lines.append(f"|--------|------|--------|-----|-----|-----|")
    for name, vals in [("Shannon H", Hs), ("Simpson D", Ds), ("Evenness E", Es)]:
        arr = np.array(vals)
        lines.append(f"| {name} | {arr.mean():.3f} | {np.median(arr):.3f} | {arr.min():.3f} | {arr.max():.3f} | {arr.std():.3f} |")
    lines.append("")

    # Correlation with correction rate
    corr_rates = np.array([r["correction_rate"] for r in diversity_results])
    h_arr = np.array(Hs)

    if len(h_arr) > 2 and np.std(h_arr) > 0 and np.std(corr_rates) > 0:
        h_corr = np.corrcoef(h_arr, corr_rates)[0, 1]
        d_corr = np.corrcoef(np.array(Ds), corr_rates)[0, 1]
        e_corr = np.corrcoef(np.array(Es), corr_rates)[0, 1]
        lines.append("### Correlation with Correction Rate")
        lines.append("")
        lines.append(f"| Metric | Pearson r |")
        lines.append(f"|--------|-----------|")
        lines.append(f"| Shannon H vs Correction Rate | {h_corr:.3f} |")
        lines.append(f"| Simpson D vs Correction Rate | {d_corr:.3f} |")
        lines.append(f"| Evenness E vs Correction Rate | {e_corr:.3f} |")
        lines.append("")

        if abs(h_corr) < 0.1:
            interp = "No meaningful correlation between tool diversity and correction rate."
        elif h_corr > 0.2:
            interp = "Positive correlation: more diverse tool usage associates with higher correction rates, suggesting complex tasks require more tools but also more human guidance."
        elif h_corr < -0.2:
            interp = "Negative correlation: more diverse tool usage associates with lower correction rates, suggesting well-adapted tool ecosystems need less human intervention."
        else:
            interp = f"Weak correlation (r = {h_corr:.3f}): tool diversity has limited relationship with correction rate."
        lines.append(f"**Interpretation**: {interp}")
        lines.append("")

    # Per-project diversity
    proj_diversity = defaultdict(list)
    for r in diversity_results:
        proj_diversity[r["project"]].append(r)

    lines.append("### Per-Project Diversity")
    lines.append("")
    lines.append("| Project | Sessions | Mean H | Mean D | Mean E | Mean S |")
    lines.append("|---------|----------|--------|--------|--------|--------|")
    for proj in sorted(proj_diversity.keys()):
        rs = proj_diversity[proj]
        lines.append(f"| {proj[:24]} | {len(rs)} | {np.mean([r['H'] for r in rs]):.3f} | {np.mean([r['D'] for r in rs]):.3f} | {np.mean([r['E'] for r in rs]):.3f} | {np.mean([r['S'] for r in rs]):.1f} |")
    lines.append("")

    # ── Analysis 2 ──
    lines.append("## Analysis 2: Species-Area Relationship")
    lines.append("")
    lines.append("![Species-Area](figures/eco_species_area.png)")
    lines.append("")
    lines.append("The species-area relationship in ecology describes how the number of species")
    lines.append("increases with habitat area. Here we test whether session length (the 'area')")
    lines.append("predicts the number of distinct tools used (the 'species').")
    lines.append("")
    if sa_coeffs is not None:
        lines.append(f"**Model**: S = {sa_coeffs[0]:.2f} * ln(Length) + {sa_coeffs[1]:.2f}")
        lines.append(f"**R² = {sa_r2:.3f}**")
        lines.append("")
        if sa_r2 > 0.4:
            lines.append("The log-linear model shows a strong fit, confirming a species-area relationship:")
            lines.append("tool diversity increases logarithmically with session length, meaning early messages")
            lines.append("introduce tools rapidly, then diversity saturates.")
        elif sa_r2 > 0.2:
            lines.append("Moderate fit: there is a species-area tendency, but session length alone does not")
            lines.append("fully predict tool diversity. Task type likely matters more.")
        else:
            lines.append("Weak fit: session length is a poor predictor of tool diversity. The 'habitat'")
            lines.append("metaphor does not hold strongly — tool selection is driven more by task requirements")
            lines.append("than by session duration.")
        lines.append("")

    # Saturation analysis
    short = [p for p in species_area_points if p["session_length"] <= 20]
    medium = [p for p in species_area_points if 20 < p["session_length"] <= 100]
    long_ = [p for p in species_area_points if p["session_length"] > 100]

    if short and medium:
        lines.append("### Tool Acquisition by Session Phase")
        lines.append("")
        lines.append("| Phase | Sessions | Mean Tools | Mean Length |")
        lines.append("|-------|----------|------------|------------|")
        for label, group in [("Short (≤20 msgs)", short), ("Medium (21-100)", medium), ("Long (>100)", long_)]:
            if group:
                lines.append(f"| {label} | {len(group)} | {np.mean([g['distinct_tools'] for g in group]):.1f} | {np.mean([g['session_length'] for g in group]):.0f} |")
        lines.append("")

    # ── Analysis 3 ──
    lines.append("## Analysis 3: Dominance Analysis")
    lines.append("")
    lines.append("![Dominance](figures/eco_dominance.png)")
    lines.append("")
    lines.append(f"- **Monoculture sessions** (one tool >80% of calls): {len(monocultures)} ({100*len(monocultures)/max(len(sessions),1):.1f}%)")
    lines.append(f"- **Diverse ecosystem sessions**: {len(diverse)} ({100*len(diverse)/max(len(sessions),1):.1f}%)")
    lines.append("")

    if monocultures and diverse:
        mono_cr = np.array([m["correction_rate"] for m in monocultures])
        div_cr = np.array([d["correction_rate"] for d in diverse])
        mono_len = np.array([m["session_length"] for m in monocultures])
        div_len = np.array([d["session_length"] for d in diverse])

        lines.append("| Metric | Monoculture | Diverse | Difference |")
        lines.append("|--------|-------------|---------|------------|")
        lines.append(f"| Mean Correction Rate | {mono_cr.mean():.3f} | {div_cr.mean():.3f} | {mono_cr.mean() - div_cr.mean():+.3f} |")
        lines.append(f"| Mean Session Length | {mono_len.mean():.1f} | {div_len.mean():.1f} | {mono_len.mean() - div_len.mean():+.1f} |")
        lines.append(f"| Mean Tool Calls | {np.mean([m['total_tool_calls'] for m in monocultures]):.1f} | {np.mean([d['total_tool_calls'] for d in diverse]):.1f} | |")
        lines.append("")

        # What tools dominate in monocultures?
        mono_dominant = Counter(m["dominant_tool"] for m in monocultures)
        lines.append("### Monoculture Dominant Tools")
        lines.append("")
        for tool, count in mono_dominant.most_common():
            pct = 100 * count / len(monocultures)
            lines.append(f"- **{tool}**: {count} sessions ({pct:.1f}%)")
        lines.append("")

        # Interpretation
        if mono_cr.mean() > div_cr.mean() + 0.05:
            lines.append("**Finding**: Monoculture sessions show higher correction rates, suggesting that")
            lines.append("over-reliance on a single tool leads to more human intervention needed.")
        elif div_cr.mean() > mono_cr.mean() + 0.05:
            lines.append("**Finding**: Diverse sessions show higher correction rates, possibly because")
            lines.append("complex tasks requiring diverse tools also require more human guidance.")
        else:
            lines.append("**Finding**: Correction rates are similar between monocultures and diverse sessions,")
            lines.append("suggesting tool diversity alone does not predict session quality.")
        lines.append("")

    # ── Analysis 4 ──
    lines.append("## Analysis 4: Beta Diversity Across Projects")
    lines.append("")
    lines.append("![Beta Diversity](figures/eco_beta_diversity.png)")
    lines.append("![Project Profiles](figures/eco_project_profiles.png)")
    lines.append("")
    lines.append("Beta diversity measures how different projects' tool usage 'ecosystems' are from each other.")
    lines.append("")

    # Find most similar and most different pairs
    n = len(projects)
    if n > 2:
        pairs = []
        for i in range(n):
            for j in range(i+1, n):
                pairs.append((projects[i], projects[j], jaccard_matrix[i][j], bray_curtis_matrix[i][j]))

        pairs_jac = sorted(pairs, key=lambda x: -x[2])
        pairs_bc = sorted(pairs, key=lambda x: x[3])

        lines.append("### Most Similar Project Pairs (Jaccard)")
        lines.append("")
        lines.append("| Project A | Project B | Jaccard | Bray-Curtis |")
        lines.append("|-----------|-----------|---------|-------------|")
        for a, b, j, bc in pairs_jac[:5]:
            lines.append(f"| {a[:20]} | {b[:20]} | {j:.3f} | {bc:.3f} |")
        lines.append("")

        lines.append("### Most Different Project Pairs (Bray-Curtis)")
        lines.append("")
        lines.append("| Project A | Project B | Bray-Curtis | Jaccard |")
        lines.append("|-----------|-----------|-------------|---------|")
        bc_sorted = sorted(pairs, key=lambda x: -x[3])
        for a, b, j, bc in bc_sorted[:5]:
            lines.append(f"| {a[:20]} | {b[:20]} | {bc:.3f} | {j:.3f} |")
        lines.append("")

        # Identify clusters
        lines.append("### Project Tool Profiles")
        lines.append("")
        for proj in sorted(project_tools.keys()):
            total = sum(project_tools[proj].values())
            if total >= 10:
                top3 = project_tools[proj].most_common(3)
                profile = ", ".join(f"{t} ({100*c/total:.0f}%)" for t, c in top3)
                lines.append(f"- **{proj}**: {profile} (n={total})")
        lines.append("")

    # ── Key Findings ──
    lines.append("## Key Findings")
    lines.append("")

    # Compute overall stats for findings
    all_H = np.array([r["H"] for r in diversity_results])
    all_E = np.array([r["E"] for r in diversity_results])
    all_dom = np.array([r["dominance"] for r in diversity_results])

    lines.append(f"1. **Tool ecosystem diversity**: Mean Shannon H = {all_H.mean():.2f} (range {all_H.min():.2f}-{all_H.max():.2f}). "
                f"Sessions use on average {np.mean([r['S'] for r in diversity_results]):.1f} distinct tools.")
    lines.append("")
    lines.append(f"2. **Evenness**: Mean Pielou's E = {all_E.mean():.2f}. "
                f"{'High evenness indicates balanced tool usage.' if all_E.mean() > 0.6 else 'Low evenness indicates tool usage is dominated by a few tools.'}")
    lines.append("")
    lines.append(f"3. **Monoculture prevalence**: {100*len(monocultures)/max(len(sessions),1):.0f}% of sessions are monocultures. "
                f"The most common monoculture tool is **{Counter(m['dominant_tool'] for m in monocultures).most_common(1)[0][0] if monocultures else 'N/A'}**.")
    lines.append("")
    if sa_r2 is not None:
        lines.append(f"4. **Species-area relationship**: R² = {sa_r2:.3f}. "
                    f"{'Strong' if sa_r2 > 0.4 else 'Moderate' if sa_r2 > 0.2 else 'Weak'} log-linear fit, "
                    f"{'confirming' if sa_r2 > 0.3 else 'weakly suggesting'} that tool diversity saturates with session length.")
        lines.append("")
    lines.append(f"5. **Cross-project diversity**: Projects show "
                f"{'high' if np.mean(bray_curtis_matrix[np.triu_indices(n, k=1)]) < 0.3 else 'moderate' if np.mean(bray_curtis_matrix[np.triu_indices(n, k=1)]) < 0.5 else 'substantial'} "
                f"variation in tool ecosystems (mean Bray-Curtis dissimilarity = {np.mean(bray_curtis_matrix[np.triu_indices(n, k=1)]):.3f}).")
    lines.append("")

    # ── Methodology Notes ──
    lines.append("## Methodology")
    lines.append("")
    lines.append("### Ecological Metrics Applied")
    lines.append("")
    lines.append("| Metric | Ecological Meaning | Tool Usage Interpretation |")
    lines.append("|--------|--------------------|---------------------------|")
    lines.append("| Shannon H | Species diversity | How varied the tool usage is |")
    lines.append("| Simpson D | Probability two random individuals differ | Probability two random tool calls are different tools |")
    lines.append("| Pielou's E | Species evenness | How evenly distributed tool usage is |")
    lines.append("| Jaccard | Shared species between habitats | Shared tool types between projects |")
    lines.append("| Bray-Curtis | Community composition difference | Difference in tool usage proportions |")
    lines.append("| Species-Area | Species richness vs habitat size | Tool richness vs session length |")
    lines.append("| Dominance | Single-species dominance | Single-tool dominance (monoculture) |")
    lines.append("")
    lines.append("### Correction Rate Proxy")
    lines.append("")
    lines.append("Correction rate is computed as the proportion of user messages that follow an assistant message")
    lines.append("(excluding the first user message). This is a rough proxy — not all follow-up messages are corrections,")
    lines.append("but the ratio captures how much human intervention a session requires.")
    lines.append("")
    lines.append("### Limitations")
    lines.append("")
    lines.append("- Correction rate is a noisy proxy for session quality")
    lines.append("- Session length confounds many metrics (longer sessions naturally use more tools)")
    lines.append("- Autonomous-sandbox sessions (n=1502) dominate and may skew aggregates")
    lines.append("- Tool names vary across Claude Code versions")
    lines.append("")

    return "\n".join(lines)


# ── Main ───────────────────────────────────────────────────────────────────

def main():
    print("Loading sessions...")
    # Sample broadly: all from small projects, cap large ones
    sessions = load_all_sessions(max_per_project=50)
    print(f"  Loaded {len(sessions)} sessions from {len(set(s['project'] for s in sessions))} projects")

    if len(sessions) < 10:
        print("ERROR: Too few sessions with tool data. Aborting.")
        sys.exit(1)

    print("\nAnalysis 1: Diversity Indices...")
    diversity_results = analysis_1_diversity_indices(sessions)

    print("Analysis 2: Species-Area Relationship...")
    species_area_points = analysis_2_species_area(sessions)

    # Fit model
    sa_coeffs = None
    sa_r2 = None
    if len(species_area_points) > 2:
        log_lengths = [p["log_length"] for p in species_area_points]
        tools = [p["distinct_tools"] for p in species_area_points]
        sa_coeffs = np.polyfit(log_lengths, tools, 1)
        ss_res = sum((t - np.polyval(sa_coeffs, l))**2 for t, l in zip(tools, log_lengths))
        ss_tot = sum((t - np.mean(tools))**2 for t in tools)
        sa_r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0
        print(f"  S = {sa_coeffs[0]:.2f} * ln(L) + {sa_coeffs[1]:.2f}, R² = {sa_r2:.3f}")

    print("Analysis 3: Dominance Analysis...")
    monocultures, diverse = analysis_3_dominance(sessions)
    print(f"  Monocultures: {len(monocultures)}, Diverse: {len(diverse)}")

    print("Analysis 4: Beta Diversity...")
    projects, jaccard_matrix, bray_curtis_matrix, project_tools = analysis_4_beta_diversity(sessions)
    print(f"  {len(projects)} projects compared")

    print("\nGenerating plots...")
    plot_all(sessions, diversity_results, species_area_points, monocultures, diverse,
             projects, jaccard_matrix, bray_curtis_matrix, project_tools)

    print("\nGenerating report...")
    report = generate_report(sessions, diversity_results, species_area_points,
                            monocultures, diverse, projects, jaccard_matrix,
                            bray_curtis_matrix, project_tools, sa_coeffs, sa_r2)

    report_path = OUTPUT_DIR / "017-ecology-diversity.md"
    with open(report_path, "w") as f:
        f.write(report)
    print(f"  Report: {report_path}")

    # Return data for solution doc generation
    return {
        "sessions": sessions,
        "diversity_results": diversity_results,
        "monocultures": monocultures,
        "diverse": diverse,
        "sa_r2": sa_r2,
        "sa_coeffs": sa_coeffs,
        "projects": projects,
        "jaccard_matrix": jaccard_matrix,
        "bray_curtis_matrix": bray_curtis_matrix,
        "project_tools": project_tools,
    }


if __name__ == "__main__":
    data = main()

    # Print summary for downstream use
    print("\n" + "="*60)
    print("SUMMARY DATA FOR SOLUTION DOCS")
    print("="*60)

    # Key stats
    mono = data["monocultures"]
    div = data["diverse"]
    dr = data["diversity_results"]

    print(f"\nSessions: {len(dr)}")
    print(f"Mean Shannon H: {np.mean([r['H'] for r in dr]):.3f}")
    print(f"Mean Simpson D: {np.mean([r['D'] for r in dr]):.3f}")
    print(f"Mean Evenness E: {np.mean([r['E'] for r in dr]):.3f}")
    print(f"Mean Distinct Tools: {np.mean([r['S'] for r in dr]):.1f}")
    print(f"Species-Area R²: {data['sa_r2']:.3f}")
    print(f"Monocultures: {len(mono)} ({100*len(mono)/len(dr):.1f}%)")
    print(f"Diverse: {len(div)} ({100*len(div)/len(dr):.1f}%)")

    if mono and div:
        print(f"Mono mean correction rate: {np.mean([m['correction_rate'] for m in mono]):.3f}")
        print(f"Diverse mean correction rate: {np.mean([d['correction_rate'] for d in div]):.3f}")

    # Per-project diversity for top projects
    from collections import defaultdict
    proj_div = defaultdict(list)
    for r in dr:
        proj_div[r["project"]].append(r)

    print("\nPer-project:")
    for p in sorted(proj_div.keys()):
        rs = proj_div[p]
        if len(rs) >= 3:
            print(f"  {p}: n={len(rs)}, H={np.mean([r['H'] for r in rs]):.2f}, E={np.mean([r['E'] for r in rs]):.2f}, S={np.mean([r['S'] for r in rs]):.1f}")

    # Most common monoculture tools
    from collections import Counter
    if mono:
        mt = Counter(m["dominant_tool"] for m in mono)
        print(f"\nMonoculture dominant tools: {dict(mt.most_common(5))}")

    # Beta diversity summary
    bc = data["bray_curtis_matrix"]
    n = len(data["projects"])
    if n > 2:
        triu = bc[np.triu_indices(n, k=1)]
        print(f"\nBray-Curtis: mean={triu.mean():.3f}, min={triu.min():.3f}, max={triu.max():.3f}")
