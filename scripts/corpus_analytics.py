#!/usr/bin/env python3
"""Text analytics on the agentic engineering sawdust corpus.

Runs TF-IDF, topic modeling, cosine similarity for dedup detection,
and corpus statistics.
"""
import os
import re
import json
# yaml no longer needed for JSONL corpus
import glob
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.decomposition import NMF, LatentDirichletAllocation
from sklearn.cluster import DBSCAN

CORPUS_DIR = os.environ.get(
    "CORPUS_DIR",
    os.environ.get("MIDDENS_CORPUS", "corpus/"),
)


def _find_jsonl_files(root):
    """Find all .jsonl files under root, following symlinks."""
    results = []
    for dirpath, dirnames, filenames in os.walk(root, followlinks=True):
        for fn in filenames:
            if fn.endswith(".jsonl"):
                results.append(Path(dirpath) / fn)
    return sorted(results)


def load_corpus():
    """Load all JSONL session files and extract text content for analysis.

    Each session becomes one document. Text is extracted from assistant text blocks,
    user messages, and thinking blocks.
    """
    docs = []
    for filepath_p in _find_jsonl_files(CORPUS_DIR):
        filepath = str(filepath_p)
        texts = []
        tool_names = []
        user_texts = []
        thinking_texts = []
        msg_count = 0

        try:
            with open(filepath) as f:
                for line in f:
                    try:
                        obj = json.loads(line.strip())
                    except (json.JSONDecodeError, UnicodeDecodeError):
                        continue
                    msg = obj.get("message", {})
                    content = msg.get("content", "")
                    role = msg.get("role", "")
                    msg_count += 1

                    if isinstance(content, str) and content.strip():
                        if role == "user":
                            user_texts.append(content)
                        elif role == "assistant":
                            texts.append(content)
                    elif isinstance(content, list):
                        for block in content:
                            if not isinstance(block, dict):
                                continue
                            btype = block.get("type", "")
                            if btype == "text":
                                t = block.get("text", "")
                                if t.strip():
                                    if role == "user":
                                        user_texts.append(t)
                                    else:
                                        texts.append(t)
                            elif btype == "thinking":
                                t = block.get("thinking", "")
                                if t.strip():
                                    thinking_texts.append(t)
                            elif btype == "tool_use":
                                name = block.get("name", "unknown")
                                tool_names.append(name)
        except Exception:
            continue

        if msg_count < 2:
            continue

        body = " ".join(texts + user_texts)

        # Derive category (project name) from directory structure
        rel = os.path.relpath(filepath, CORPUS_DIR)
        parts = rel.split(os.sep)
        category = "unknown"
        if "projects" in parts:
            proj_idx = parts.index("projects")
            if proj_idx + 1 < len(parts):
                category = parts[proj_idx + 1]
        # Determine operator (claude-code vs claude-ai)
        operator = parts[0] if parts else "unknown"

        # Determine if subagent
        is_subagent = "subagent" in rel

        docs.append({
            "path": filepath,
            "filename": os.path.basename(filepath),
            "category": category,
            "operator": operator,
            "is_subagent": is_subagent,
            "title": "",
            "tags": tool_names[:10],  # Use tool names as pseudo-tags
            "severity": "",
            "symptoms": [],
            "body": body,
            "full_text": body,
            "word_count": len(body.split()),
            "msg_count": msg_count,
            "tool_count": len(tool_names),
            "thinking_word_count": len(" ".join(thinking_texts).split()),
        })
    return docs


def tfidf_analysis(docs):
    """TF-IDF analysis: find distinctive terms per category."""
    print("\n" + "=" * 60)
    print("TF-IDF: DISTINCTIVE TERMS PER CATEGORY")
    print("=" * 60)

    # Aggregate text by category
    cat_texts = defaultdict(list)
    for d in docs:
        cat_texts[d["category"]].append(d["full_text"])

    categories = sorted(cat_texts.keys())
    cat_combined = [" ".join(cat_texts[c]) for c in categories]

    if len(categories) < 2:
        print("\n  (Skipping TF-IDF: fewer than 2 categories)")
        return

    vectorizer = TfidfVectorizer(
        max_features=5000,
        stop_words="english",
        ngram_range=(1, 2),
        min_df=1,
        max_df=max(0.8, (len(categories) - 0.5) / len(categories)),
    )
    tfidf_matrix = vectorizer.fit_transform(cat_combined)
    feature_names = vectorizer.get_feature_names_out()

    for i, cat in enumerate(categories):
        scores = tfidf_matrix[i].toarray().flatten()
        top_indices = scores.argsort()[-10:][::-1]
        terms = [(feature_names[j], scores[j]) for j in top_indices if scores[j] > 0]
        print(f"\n  {cat} ({len(cat_texts[cat])} docs):")
        for term, score in terms:
            print(f"    {score:.3f}  {term}")


def similarity_analysis(docs, max_docs=2000):
    """Cosine similarity: find potential duplicates.

    For large corpora, samples max_docs documents to keep O(n^2) manageable.
    """
    print("\n" + "=" * 60)
    print("COSINE SIMILARITY: POTENTIAL DUPLICATES")
    print("=" * 60)

    sample = docs
    if len(docs) > max_docs:
        rng = np.random.RandomState(42)
        indices = rng.choice(len(docs), max_docs, replace=False)
        sample = [docs[i] for i in sorted(indices)]
        print(f"\n  (Sampled {max_docs} of {len(docs)} docs for O(n^2) similarity)")

    vectorizer = TfidfVectorizer(
        max_features=3000,
        stop_words="english",
        ngram_range=(1, 2),
    )
    tfidf_matrix = vectorizer.fit_transform([d["full_text"] for d in sample])
    sim_matrix = cosine_similarity(tfidf_matrix)

    # Find pairs with high similarity
    pairs = []
    n = len(sample)
    for i in range(n):
        for j in range(i + 1, n):
            if sim_matrix[i][j] > 0.4:
                pairs.append((sim_matrix[i][j], i, j))

    pairs.sort(reverse=True)

    print(f"\n  Found {len(pairs)} pairs with similarity > 0.4")
    print(f"\n  TOP 25 MOST SIMILAR PAIRS:")
    for score, i, j in pairs[:25]:
        print(f"\n    {score:.3f}")
        print(f"      [{sample[i]['category']}] {sample[i]['filename']}")
        print(f"      [{sample[j]['category']}] {sample[j]['filename']}")

    return sim_matrix


def topic_modeling(docs, n_topics=12):
    """NMF topic modeling to discover latent themes."""
    print("\n" + "=" * 60)
    print(f"TOPIC MODELING: {n_topics} LATENT THEMES (NMF)")
    print("=" * 60)

    vectorizer = TfidfVectorizer(
        max_features=3000,
        stop_words="english",
        ngram_range=(1, 2),
        min_df=2,
        max_df=0.8,
    )
    tfidf_matrix = vectorizer.fit_transform([d["full_text"] for d in docs])
    feature_names = vectorizer.get_feature_names_out()

    nmf = NMF(n_components=n_topics, random_state=42, max_iter=500)
    doc_topics = nmf.fit_transform(tfidf_matrix)

    for topic_idx, topic in enumerate(nmf.components_):
        top_words = [feature_names[i] for i in topic.argsort()[-8:][::-1]]
        # Find docs most associated with this topic
        top_docs = doc_topics[:, topic_idx].argsort()[-3:][::-1]
        print(f"\n  Topic {topic_idx}: {', '.join(top_words)}")
        for di in top_docs:
            if doc_topics[di, topic_idx] > 0.1:
                print(f"    [{docs[di]['category']}] {docs[di]['title'][:60]}")

    return doc_topics


def cluster_analysis(docs, max_docs=2000):
    """DBSCAN clustering on TF-IDF vectors to find natural groupings.

    For large corpora, samples max_docs documents to keep O(n^2) manageable.
    """
    print("\n" + "=" * 60)
    print("DBSCAN CLUSTERING: NATURAL DOCUMENT GROUPS")
    print("=" * 60)

    sample = docs
    if len(docs) > max_docs:
        rng = np.random.RandomState(42)
        indices = rng.choice(len(docs), max_docs, replace=False)
        sample = [docs[i] for i in sorted(indices)]
        print(f"\n  (Sampled {max_docs} of {len(docs)} docs for O(n^2) clustering)")

    vectorizer = TfidfVectorizer(
        max_features=2000,
        stop_words="english",
        ngram_range=(1, 2),
    )
    tfidf_matrix = vectorizer.fit_transform([d["full_text"] for d in sample])

    # Use cosine distance, clip to avoid negative values from float imprecision
    dist_matrix = np.clip(1 - cosine_similarity(tfidf_matrix), 0, 2)

    clustering = DBSCAN(eps=0.6, min_samples=2, metric="precomputed")
    labels = clustering.fit_predict(dist_matrix)

    clusters = defaultdict(list)
    noise = 0
    for i, label in enumerate(labels):
        if label == -1:
            noise += 1
        else:
            clusters[label].append(i)

    print(f"\n  {len(clusters)} clusters found, {noise} unclustered docs")

    for cluster_id, indices in sorted(clusters.items(), key=lambda x: -len(x[1])):
        print(f"\n  Cluster {cluster_id} ({len(indices)} docs):")
        for i in indices:
            print(f"    [{sample[i]['category']}] {sample[i]['title'][:65]}")


def corpus_stats(docs):
    """Basic corpus statistics for JSONL session corpus."""
    print("=" * 60)
    print("CORPUS STATISTICS")
    print("=" * 60)

    print(f"\n  Total sessions: {len(docs)}")

    # By operator
    op_counts = Counter(d["operator"] for d in docs)
    print(f"\n  By operator:")
    for op, count in op_counts.most_common():
        print(f"    {count:3d}  {op}")

    # By project (category)
    cat_counts = Counter(d["category"] for d in docs)
    print(f"\n  By project ({len(cat_counts)} projects):")
    for cat, count in cat_counts.most_common():
        print(f"    {count:3d}  {cat}")

    # Subagent vs top-level
    sub_count = sum(1 for d in docs if d["is_subagent"])
    top_count = len(docs) - sub_count
    print(f"\n  Top-level sessions: {top_count}")
    print(f"  Subagent sessions: {sub_count}")

    # Word count stats
    word_counts = [d["word_count"] for d in docs]
    print(f"\n  Word counts (extracted text):")
    print(f"    Mean:   {np.mean(word_counts):.0f}")
    print(f"    Median: {np.median(word_counts):.0f}")
    print(f"    Min:    {min(word_counts)} ({docs[np.argmin(word_counts)]['filename']})")
    print(f"    Max:    {max(word_counts)} ({docs[np.argmax(word_counts)]['filename']})")
    print(f"    Total:  {sum(word_counts):,}")

    # Message count stats
    msg_counts = [d["msg_count"] for d in docs]
    print(f"\n  Message counts:")
    print(f"    Mean:   {np.mean(msg_counts):.0f}")
    print(f"    Median: {np.median(msg_counts):.0f}")
    print(f"    Max:    {max(msg_counts)}")

    # Tool usage frequency
    all_tools = []
    for d in docs:
        all_tools.extend(d["tags"] if isinstance(d["tags"], list) else [])
    tool_counts = Counter(all_tools)
    print(f"\n  Top 20 tools used:")
    for tool, count in tool_counts.most_common(20):
        print(f"    {count:3d}  {tool}")

    # Tool call counts
    tc_counts = [d["tool_count"] for d in docs]
    print(f"\n  Tool calls per session:")
    print(f"    Mean:   {np.mean(tc_counts):.0f}")
    print(f"    Median: {np.median(tc_counts):.0f}")
    print(f"    Total:  {sum(tc_counts):,}")

    # Thinking block stats
    thinking_wc = [d["thinking_word_count"] for d in docs]
    sessions_with_thinking = sum(1 for w in thinking_wc if w > 0)
    print(f"\n  Thinking blocks:")
    print(f"    Sessions with thinking: {sessions_with_thinking} ({sessions_with_thinking/len(docs)*100:.1f}%)")
    if sessions_with_thinking > 0:
        thinking_only = [w for w in thinking_wc if w > 0]
        print(f"    Mean thinking words (when present): {np.mean(thinking_only):.0f}")
        print(f"    Total thinking words: {sum(thinking_wc):,}")


def gap_analysis(docs):
    """Identify thematic coverage across the agentic coding corpus."""
    print("\n" + "=" * 60)
    print("THEMATIC COVERAGE ANALYSIS")
    print("=" * 60)

    # Themes relevant to agentic coding sessions
    expected_themes = [
        "error", "bug", "fix", "test", "refactor",
        "build", "compile", "deploy", "ci", "lint",
        "git", "commit", "merge", "branch", "revert",
        "api", "endpoint", "request", "response", "authentication",
        "database", "migration", "schema", "query",
        "config", "environment", "docker", "kubernetes",
        "performance", "optimization", "cache", "memory",
        "security", "vulnerability", "permission",
        "documentation", "readme", "comment",
        "dependency", "package", "version", "upgrade",
        "swift", "rust", "typescript", "python", "kotlin",
        "ios", "android", "mobile", "sdk",
        "worktree", "subagent", "delegation", "parallel",
    ]

    all_text = " ".join(d["full_text"].lower() for d in docs)

    print("\n  Theme coverage (mentions across corpus):")
    theme_counts = []
    for theme in expected_themes:
        count = all_text.count(theme)
        theme_counts.append((theme, count))

    theme_counts.sort(key=lambda x: x[1])
    for theme, count in theme_counts:
        bar = "#" * min(count // 50, 40)
        indicator = " *** THIN ***" if count < 10 else ""
        print(f"    {count:6d}  {theme:25s} {bar}{indicator}")


if __name__ == "__main__":
    print("Loading corpus...")
    docs = load_corpus()

    corpus_stats(docs)
    gap_analysis(docs)
    tfidf_analysis(docs)
    similarity_analysis(docs)
    topic_modeling(docs)
    cluster_analysis(docs)
