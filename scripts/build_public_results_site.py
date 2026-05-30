#!/usr/bin/env python3
"""Build the public corpus results static site from curated site-data.

The input must already be the Phase 1 public-safe bundle shape. This generator
never reads raw transcripts or middens technique outputs.
"""

from __future__ import annotations

import argparse
import html
import json
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SAFE_DOWNLOAD_FILES = (
    "corpus.json",
    "analysis-manifest.json",
    "split-manifest.json",
    "metrics.json",
    "status.json",
    "interpretation.md",
)
SAFE_COMPARATIVE_DOWNLOAD_FILES = (
    "corpus-index.json",
    "comparative-metrics.json",
    "technique-status-matrix.json",
    "finding-replication-matrix.json",
)

KEY_METRICS: tuple[tuple[str, str, str, str], ...] = (
    ("Risk suppression", "thinking-divergence", "suppression_rate", "percent"),
    ("Thinking/text divergence", "thinking-divergence", "divergence_ratio", "number"),
    ("Correction mean", "correction-rate", "overall_mean_rate", "percent"),
    ("First-third correction", "correction-rate", "first_third_rate", "percent"),
    ("Last-third correction", "correction-rate", "last_third_rate", "percent"),
    ("MVT compliance", "information-foraging", "mvt_compliance_rate", "percent"),
    ("HSMM pre-correction lift", "hsmm", "pre_correction_lift", "multiplier"),
    ("Tool entropy", "entropy", "mean_entropy", "number"),
    ("ENA top code", "ena-analysis", "top_code", "string"),
)


@dataclass(frozen=True)
class CorpusBundle:
    corpus_id: str
    path: Path
    metrics: dict[str, Any]
    corpus: dict[str, Any]
    status: dict[str, Any]
    interpretation: str | None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site-data", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def fail(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(2)


def load_json(path: Path, label: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        fail(f"{label} not found: {path}")
    except json.JSONDecodeError as exc:
        fail(f"{label} is not valid JSON: {path}: {exc}")


def ensure_site_data(path: Path) -> Path:
    if not path.exists():
        fail(f"site-data directory does not exist: {path}")
    if not path.is_dir():
        fail(f"site-data must be a directory: {path}")
    corpora = path / "corpora"
    if not corpora.is_dir():
        fail(f"site-data must contain a corpora/ directory: {path}")
    return corpora


def load_bundles(site_data: Path) -> list[CorpusBundle]:
    corpora_dir = ensure_site_data(site_data)
    bundles: list[CorpusBundle] = []
    for path in sorted(p for p in corpora_dir.iterdir() if p.is_dir()):
        metrics = load_json(path / "metrics.json", f"metrics for {path.name}")
        corpus = load_json(path / "corpus.json", f"corpus metadata for {path.name}")
        status = load_json(path / "status.json", f"status for {path.name}")
        corpus_id = str(metrics.get("corpus", {}).get("id") or path.name)
        if corpus_id != path.name:
            fail(f"corpus directory name {path.name!r} does not match metrics corpus id {corpus_id!r}")
        interpretation_path = path / "interpretation.md"
        interpretation = interpretation_path.read_text(encoding="utf-8") if interpretation_path.exists() else None
        bundles.append(CorpusBundle(corpus_id, path, metrics, corpus, status, interpretation))
    if not bundles:
        fail(f"no corpus metric bundles found under {corpora_dir}")
    return bundles


def load_comparative(site_data: Path) -> dict[str, Any] | None:
    comparative_dir = site_data / "comparative"
    if not comparative_dir.exists():
        return None
    if not comparative_dir.is_dir():
        fail(f"site-data comparative path exists but is not a directory: {comparative_dir}")
    files = {
        "corpus_index": comparative_dir / "corpus-index.json",
        "comparative_metrics": comparative_dir / "comparative-metrics.json",
        "technique_status_matrix": comparative_dir / "technique-status-matrix.json",
        "finding_replication_matrix": comparative_dir / "finding-replication-matrix.json",
    }
    return {key: load_json(path, key.replace("_", " ")) for key, path in files.items()}


def e(value: Any) -> str:
    return html.escape(str(value), quote=True)


def rel_from(page_dir: str, target: str) -> str:
    depth = 0 if page_dir == "." else len([part for part in page_dir.split("/") if part])
    return "../" * depth + target


def fmt_value(value: Any, kind: str = "auto") -> str:
    if value is None:
        return "—"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        numeric = float(value)
        if kind == "percent":
            return f"{numeric * 100:.2f}%"
        if kind == "multiplier":
            return f"{numeric:.2f}×"
        if numeric.is_integer():
            return str(int(numeric))
        return f"{numeric:.4g}"
    return str(value)


def metric_entry(bundle: CorpusBundle, technique: str, label: str) -> dict[str, Any] | None:
    try:
        entry = bundle.metrics["techniques"][technique]["findings"][label]
    except KeyError:
        return None
    return entry if isinstance(entry, dict) else None


def metric_value(bundle: CorpusBundle, technique: str, label: str) -> Any:
    entry = metric_entry(bundle, technique, label)
    if not entry or entry.get("status") != "defined":
        return None
    return entry.get("value")


def page_shell(title: str, description: str, current: str, page_dir: str, body: str) -> str:
    nav = [
        ("Home", "index.html", "home"),
        ("Corpora", "corpora/index.html", "corpora"),
        ("Comparative", "comparative/index.html", "comparative"),
        ("Methodology", "methodology/index.html", "methodology"),
        ("Downloads", "downloads/index.html", "downloads"),
        ("GitHub", "https://github.com/Lightless-Labs/third-thoughts", "github"),
    ]
    nav_html = "\n".join(
        f'<a href="{e(href if href.startswith("https://") else rel_from(page_dir, href))}"'
        + (" aria-current=\"page\"" if key == current else "")
        + f">{e(label)}</a>"
        for label, href, key in nav
    )
    css_href = rel_from(page_dir, "assets/style.css")
    home_href = rel_from(page_dir, "index.html")
    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{e(title)}</title>
    <meta name="description" content="{e(description)}">
    <link rel="stylesheet" href="{e(css_href)}">
  </head>
  <body>
    <main class="page">
      <header class="topbar" aria-label="Site header">
        <a class="wordmark" href="{e(home_href)}">Third Thoughts</a>
        <nav class="nav" aria-label="Primary">
          {nav_html}
        </nav>
      </header>
      {body}
    </main>
  </body>
</html>
"""


def render_warning_list(warnings: list[Any]) -> str:
    if not warnings:
        return '<p class="muted">No extraction warnings recorded.</p>'
    items = "".join(f"<li>{e(warning)}</li>" for warning in warnings)
    return f'<ul class="warnings">{items}</ul>'


def corpus_card(bundle: CorpusBundle, page_dir: str) -> str:
    counts = bundle.metrics.get("session_counts", {})
    strata = counts.get("by_stratum", {}) if isinstance(counts.get("by_stratum"), dict) else {}
    technique_counts = bundle.metrics.get("technique_status", {}).get("counts", {})
    risk = fmt_value(metric_value(bundle, "thinking-divergence", "suppression_rate"), "percent")
    mvt = fmt_value(metric_value(bundle, "information-foraging", "mvt_compliance_rate"), "percent")
    lift = fmt_value(metric_value(bundle, "hsmm", "pre_correction_lift"), "multiplier")
    return f"""
      <article class="card corpus-card">
        <div class="card-eyebrow">{e(bundle.metrics.get('corpus', {}).get('storage_format', 'unknown'))}</div>
        <h3><a href="{e(rel_from(page_dir, f'corpora/{bundle.corpus_id}/index.html'))}">{e(bundle.corpus_id)}</a></h3>
        <p>{e(bundle.corpus.get('description', 'Public corpus'))}</p>
        <dl class="mini-metrics">
          <div><dt>Sessions</dt><dd>{e(fmt_value(counts.get('analysis')))}</dd></div>
          <div><dt>Split</dt><dd>{e(fmt_value(strata.get('interactive')))} / {e(fmt_value(strata.get('subagent')))} / {e(fmt_value(strata.get('autonomous')))}</dd></div>
          <div><dt>Techniques</dt><dd>{e(fmt_value(technique_counts.get('completed')))} / {e(fmt_value(technique_counts.get('total')))}</dd></div>
          <div><dt>Risk suppression</dt><dd>{e(risk)}</dd></div>
          <div><dt>MVT compliance</dt><dd>{e(mvt)}</dd></div>
          <div><dt>HSMM lift</dt><dd>{e(lift)}</dd></div>
        </dl>
      </article>
    """


def render_index(bundles: list[CorpusBundle]) -> str:
    total_sessions = sum(int(b.metrics.get("session_counts", {}).get("analysis") or 0) for b in bundles)
    total_autonomous = sum(int((b.metrics.get("session_counts", {}).get("by_stratum") or {}).get("autonomous") or 0) for b in bundles)
    cards = "\n".join(corpus_card(bundle, ".") for bundle in bundles[:6])
    body = f"""
      <section class="hero">
        <div class="eyebrow">Public corpus results · generated from curated metrics</div>
        <h1>What the public logs say, without publishing the logs.</h1>
        <p class="lede">These pages summarize selected public Hugging Face corpora using public-safe aggregate `middens` metrics. Raw transcripts, tool payloads, per-session tables, and local paths stay out of the website, because we enjoy sleeping occasionally.</p>
        <div class="actions">
          <a class="button primary" href="corpora/index.html">Browse corpora</a>
          <a class="button secondary" href="methodology/index.html">Read the caveats</a>
        </div>
      </section>
      <section class="section">
        <div class="stats-row">
          <div class="stat"><span>{len(bundles)}</span><small>published corpora</small></div>
          <div class="stat"><span>{total_sessions}</span><small>parsed sessions</small></div>
          <div class="stat"><span>{total_autonomous}</span><small>autonomous sessions</small></div>
        </div>
      </section>
      <section class="section">
        <div class="section-head"><h2>Corpus cards</h2><p>Flat analysis plus split counts. Treat small cohorts and empty strata as smoke, not science.</p></div>
        <div class="cards-grid">{cards}</div>
      </section>
    """
    return page_shell(
        "Third Thoughts — public corpus results",
        "Public-safe aggregate metrics for selected AI coding-agent transcript corpora.",
        "home",
        ".",
        body,
    )


def render_corpora_index(bundles: list[CorpusBundle]) -> str:
    cards = "\n".join(corpus_card(bundle, "corpora") for bundle in bundles)
    body = f"""
      <section class="hero compact">
        <div class="eyebrow">Corpora</div>
        <h1>Selected public corpora.</h1>
        <p class="lede">Each card links to a per-corpus aggregate page. Pinned revisions are shown because mutable datasets are how you get haunted.</p>
      </section>
      <section class="section"><div class="cards-grid">{cards}</div></section>
    """
    return page_shell("Corpora — Third Thoughts", "Selected public corpus result cards.", "corpora", "corpora", body)


def render_key_metric_table(bundle: CorpusBundle) -> str:
    rows = []
    for label, technique, finding, kind in KEY_METRICS:
        entry = metric_entry(bundle, technique, finding)
        value = entry.get("value") if entry and entry.get("status") == "defined" else None
        status = entry.get("status") if entry else "missing"
        rows.append(f"<tr><th>{e(label)}</th><td>{e(fmt_value(value, kind))}</td><td>{e(status)}</td></tr>")
    return '<table class="metric-table"><thead><tr><th>Metric</th><th>Value</th><th>Status</th></tr></thead><tbody>' + "".join(rows) + "</tbody></table>"


def render_technique_matrix(bundle: CorpusBundle) -> str:
    techniques = bundle.metrics.get("technique_status", {}).get("techniques", {})
    rows = []
    for name in sorted(techniques):
        status = techniques[name]
        rows.append(
            f"<tr><th>{e(name)}</th><td>{e(status.get('status'))}</td><td>{e(fmt_value(status.get('table_row_count')))}</td><td>{e(status.get('version'))}</td></tr>"
        )
    return '<table class="metric-table compact-table"><thead><tr><th>Technique</th><th>Status</th><th>Rows</th><th>Version</th></tr></thead><tbody>' + "".join(rows) + "</tbody></table>"


def render_corpus_page(bundle: CorpusBundle) -> str:
    counts = bundle.metrics.get("session_counts", {})
    strata = counts.get("by_stratum", {}) if isinstance(counts.get("by_stratum"), dict) else {}
    corpus = bundle.metrics.get("corpus", {})
    warnings = bundle.status.get("warnings", []) if isinstance(bundle.status.get("warnings"), list) else []
    interpretation = ""
    if bundle.interpretation:
        interpretation = f"<section class=\"section\"><h2>Interpretation</h2><div class=\"prose\"><pre>{e(bundle.interpretation)}</pre></div></section>"
    body = f"""
      <section class="hero compact">
        <div class="eyebrow">Corpus · {e(corpus.get('storage_format', 'unknown'))}</div>
        <h1>{e(bundle.corpus_id)}</h1>
        <p class="lede">{e(bundle.corpus.get('description', 'Public corpus'))}</p>
      </section>
      <section class="section">
        <div class="stats-row">
          <div class="stat"><span>{e(fmt_value(counts.get('analysis')))}</span><small>parsed sessions</small></div>
          <div class="stat"><span>{e(fmt_value(strata.get('interactive')))}</span><small>interactive</small></div>
          <div class="stat"><span>{e(fmt_value(strata.get('subagent')))}</span><small>subagent</small></div>
          <div class="stat"><span>{e(fmt_value(strata.get('autonomous')))}</span><small>autonomous</small></div>
        </div>
      </section>
      <section class="section two-col">
        <article class="panel">
          <h2>Provenance</h2>
          <dl class="kv">
            <div><dt>Dataset</dt><dd>{e(corpus.get('dataset_repo'))}</dd></div>
            <div><dt>Revision</dt><dd><code>{e(corpus.get('dataset_revision'))}</code></dd></div>
            <div><dt>Source</dt><dd>{e(corpus.get('source'))}</dd></div>
            <div><dt>Normalizer</dt><dd>{e(fmt_value(corpus.get('normalizer')))}</dd></div>
            <div><dt>Estimated parse errors</dt><dd>{e(fmt_value(counts.get('estimated_parse_errors')))}</dd></div>
          </dl>
        </article>
        <article class="panel">
          <h2>Caveats</h2>
          {render_warning_list(warnings)}
        </article>
      </section>
      <section class="section">
        <h2>Key metrics</h2>
        {render_key_metric_table(bundle)}
      </section>
      <section class="section">
        <h2>Technique status</h2>
        {render_technique_matrix(bundle)}
      </section>
      {interpretation}
      <section class="section"><p><a href="../../downloads/corpora/{e(bundle.corpus_id)}/metrics.json">Download the public-safe metrics JSON</a></p></section>
    """
    return page_shell(f"{bundle.corpus_id} — Third Thoughts", f"Public-safe metrics for {bundle.corpus_id}.", "corpora", f"corpora/{bundle.corpus_id}", body)


def render_axis_coverage(comparative: dict[str, Any] | None) -> str:
    if not comparative:
        return ""
    replication = comparative.get("finding_replication_matrix", {})
    coverage = replication.get("axis_coverage", {}) if isinstance(replication, dict) else {}
    session_type = coverage.get("session_type", {}) if isinstance(coverage, dict) else {}
    language = coverage.get("language", {}) if isinstance(coverage, dict) else {}
    thinking = coverage.get("thinking_visibility", {}) if isinstance(coverage, dict) else {}
    duplicate_families = replication.get("duplicate_families", {}) if isinstance(replication, dict) else {}
    duplicate_text = "none flagged"
    if duplicate_families:
        duplicate_text = "; ".join(f"{family}: {', '.join(ids)}" for family, ids in sorted(duplicate_families.items()))
    return f"""
      <section class="section two-col">
        <article class="panel">
          <h2>Axis coverage</h2>
          <dl class="kv">
            <div><dt>Interactive corpora</dt><dd>{e(fmt_value(session_type.get('interactive_corpora')))}</dd></div>
            <div><dt>Subagent corpora</dt><dd>{e(fmt_value(session_type.get('subagent_corpora')))}</dd></div>
            <div><dt>Autonomous corpora</dt><dd>{e(fmt_value(session_type.get('autonomous_corpora')))}</dd></div>
            <div><dt>Language axis</dt><dd>{e('available' if language.get('available') else language.get('reason', 'unavailable'))}</dd></div>
            <div><dt>Thinking visibility axis</dt><dd>{e('available' if thinking.get('available') else thinking.get('reason', 'unavailable'))}</dd></div>
          </dl>
        </article>
        <article class="panel">
          <h2>Duplicate-family warnings</h2>
          <p>{e(duplicate_text)}</p>
        </article>
      </section>
    """


def render_comparative_metric_matrix(comparative: dict[str, Any] | None) -> str:
    if not comparative:
        return ""
    metrics_doc = comparative.get("comparative_metrics", {})
    metrics = metrics_doc.get("metrics", {}) if isinstance(metrics_doc, dict) else {}
    rows = []
    for metric_id in sorted(metrics):
        metric = metrics[metric_id]
        aggregate = metric.get("aggregate", {}) if isinstance(metric, dict) else {}
        numeric = aggregate.get("numeric", {}) if isinstance(aggregate, dict) else {}
        classification = (
            comparative.get("finding_replication_matrix", {})
            .get("findings", {})
            .get(metric_id, {})
            .get("classification", {})
        )
        rows.append(
            "<tr>"
            f"<th>{e(metric.get('label', metric_id))}</th>"
            f"<td>{e(fmt_value(aggregate.get('defined_count')))}</td>"
            f"<td>{e(fmt_value(aggregate.get('undefined_count')))}</td>"
            f"<td>{e(fmt_value(numeric.get('min'), metric.get('kind', 'auto')))}</td>"
            f"<td>{e(fmt_value(numeric.get('max'), metric.get('kind', 'auto')))}</td>"
            f"<td>{e(classification.get('classification_input', 'descriptive'))}</td>"
            "</tr>"
        )
    return f"""
      <section class="section table-wrap">
        <h2>Finding replication inputs</h2>
        <table class="metric-table">
          <thead><tr><th>Metric</th><th>Defined corpora</th><th>Undefined corpora</th><th>Min</th><th>Max</th><th>Classification input</th></tr></thead>
          <tbody>{''.join(rows)}</tbody>
        </table>
      </section>
    """


def render_comparative(bundles: list[CorpusBundle], comparative: dict[str, Any] | None = None) -> str:
    rows = []
    for bundle in bundles:
        counts = bundle.metrics.get("session_counts", {})
        strata = counts.get("by_stratum", {}) if isinstance(counts.get("by_stratum"), dict) else {}
        rows.append(
            "<tr>"
            f"<th><a href=\"../corpora/{e(bundle.corpus_id)}/index.html\">{e(bundle.corpus_id)}</a></th>"
            f"<td>{e(fmt_value(counts.get('analysis')))}</td>"
            f"<td>{e(fmt_value(strata.get('interactive')))}</td>"
            f"<td>{e(fmt_value(strata.get('subagent')))}</td>"
            f"<td>{e(fmt_value(strata.get('autonomous')))}</td>"
            f"<td>{e(fmt_value(metric_value(bundle, 'thinking-divergence', 'suppression_rate'), 'percent'))}</td>"
            f"<td>{e(fmt_value(metric_value(bundle, 'information-foraging', 'mvt_compliance_rate'), 'percent'))}</td>"
            f"<td>{e(fmt_value(metric_value(bundle, 'hsmm', 'pre_correction_lift'), 'multiplier'))}</td>"
            "</tr>"
        )
    comparative_note = "Comparative JSON is present and rendered below." if comparative else "Comparative JSON is not present; showing the per-corpus fallback table."
    body = f"""
      <section class="hero compact">
        <div class="eyebrow">Comparative metrics</div>
        <h1>Side-by-side, with several warning labels attached.</h1>
        <p class="lede">This table compares deterministic aggregate metrics. It does not deduplicate duplicate-shaped corpora, pool them into a headline, or pretend empty autonomous strata mean anything deep. {e(comparative_note)}</p>
      </section>
      <section class="section table-wrap">
        <table class="metric-table">
          <thead><tr><th>Corpus</th><th>Sessions</th><th>Interactive</th><th>Subagent</th><th>Autonomous</th><th>Risk suppression</th><th>MVT compliance</th><th>HSMM lift</th></tr></thead>
          <tbody>{''.join(rows)}</tbody>
        </table>
      </section>
      {render_axis_coverage(comparative)}
      {render_comparative_metric_matrix(comparative)}
    """
    return page_shell("Comparative metrics — Third Thoughts", "Comparative public-safe metrics across selected corpora.", "comparative", "comparative", body)


def render_methodology(bundles: list[CorpusBundle]) -> str:
    technique_count = max((int(b.metrics.get("technique_status", {}).get("counts", {}).get("total") or 0) for b in bundles), default=0)
    body = f"""
      <section class="hero compact">
        <div class="eyebrow">Methodology</div>
        <h1>Curated aggregates in, static HTML out.</h1>
        <p class="lede">The site is generated from Phase 1 `site-data` bundles, not from raw transcripts or arbitrary technique tables.</p>
      </section>
      <section class="section two-col">
        <article class="panel">
          <h2>What gets published</h2>
          <ul>
            <li>Public corpus provenance and pinned dataset revisions.</li>
            <li>Session and split-stratum counts.</li>
            <li>Technique completion/error status for up to {technique_count} techniques.</li>
            <li>A fixed allowlist of aggregate findings.</li>
            <li>Warnings for tiny cohorts, empty autonomous axes, language-axis gaps, and duplicate-shaped corpus families.</li>
          </ul>
        </article>
        <article class="panel">
          <h2>What does not</h2>
          <ul>
            <li>Raw transcripts, prompts, assistant messages, thinking text, or tool payloads.</li>
            <li>Raw per-session tables, session ids, project names, or source paths.</li>
            <li>Notebook artifacts unless a later phase explicitly allowlists them.</li>
          </ul>
        </article>
      </section>
      <section class="section panel">
        <h2>Current caveats</h2>
        <p>The compound scoping rule still applies: findings should be scoped by session type, thinking visibility, language, and time window. This first generated site shows deterministic corpus-level metrics; it is not yet the LLM interpretation layer and it is not a substitute for methodology review.</p>
      </section>
    """
    return page_shell("Methodology — Third Thoughts", "How the public corpus results site is generated safely.", "methodology", "methodology", body)


def render_downloads(bundles: list[CorpusBundle], comparative: dict[str, Any] | None = None) -> str:
    rows = []
    for bundle in bundles:
        links = []
        for filename in SAFE_DOWNLOAD_FILES:
            if (bundle.path / filename).exists():
                links.append(f'<a href="corpora/{e(bundle.corpus_id)}/{e(filename)}">{e(filename)}</a>')
        rows.append(f"<tr><th>{e(bundle.corpus_id)}</th><td>{' · '.join(links)}</td></tr>")
    comparative_links = ""
    if comparative:
        links = [f'<a href="comparative/{e(filename)}">{e(filename)}</a>' for filename in SAFE_COMPARATIVE_DOWNLOAD_FILES]
        comparative_links = f"""
      <section class="section table-wrap">
        <h2>Comparative bundles</h2>
        <table class="metric-table"><thead><tr><th>Bundle</th><th>Files</th></tr></thead><tbody><tr><th>comparative</th><td>{' · '.join(links)}</td></tr></tbody></table>
      </section>
        """
    body = f"""
      <section class="hero compact">
        <div class="eyebrow">Downloads</div>
        <h1>Public-safe JSON bundles.</h1>
        <p class="lede">These are the curated site-data files used to build the pages. Raw transcript artifacts are not copied here.</p>
      </section>
      <section class="section table-wrap">
        <h2>Per-corpus bundles</h2>
        <table class="metric-table"><thead><tr><th>Corpus</th><th>Files</th></tr></thead><tbody>{''.join(rows)}</tbody></table>
      </section>
      {comparative_links}
    """
    return page_shell("Downloads — Third Thoughts", "Download public-safe corpus metrics bundles.", "downloads", "downloads", body)


def stylesheet() -> str:
    return """:root {
  color-scheme: light;
  --bg: #fbf7ef;
  --ink: #241f1a;
  --muted: #6d6257;
  --panel: #fffdf8;
  --line: #e4d8c8;
  --accent: #8f4f2a;
  --accent-2: #244f58;
  --warn: #7a4b00;
}
* { box-sizing: border-box; }
body { margin: 0; font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: var(--bg); color: var(--ink); line-height: 1.55; }
a { color: var(--accent-2); }
code, pre { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }
.page { width: min(1120px, calc(100% - 32px)); margin: 0 auto; }
.topbar { display: flex; justify-content: space-between; align-items: center; gap: 20px; padding: 24px 0; }
.wordmark { font-weight: 800; color: var(--ink); text-decoration: none; }
.nav { display: flex; flex-wrap: wrap; gap: 12px; }
.nav a { color: var(--muted); text-decoration: none; font-size: 0.95rem; }
.nav a[aria-current="page"] { color: var(--ink); font-weight: 700; }
.hero { padding: 72px 0 40px; }
.hero.compact { padding: 46px 0 24px; }
.eyebrow, .card-eyebrow { color: var(--accent); font-weight: 800; text-transform: uppercase; letter-spacing: .08em; font-size: .78rem; }
h1 { font-size: clamp(2.4rem, 7vw, 5.8rem); line-height: .95; max-width: 980px; margin: 10px 0 20px; letter-spacing: -0.06em; }
h2 { font-size: clamp(1.4rem, 3vw, 2.1rem); margin: 0 0 12px; letter-spacing: -0.03em; }
h3 { margin: 6px 0 10px; font-size: 1.3rem; }
.lede { font-size: clamp(1.1rem, 2vw, 1.35rem); max-width: 850px; color: var(--muted); }
.actions { display: flex; flex-wrap: wrap; gap: 12px; margin-top: 24px; }
.button { display: inline-block; padding: 12px 16px; border-radius: 999px; text-decoration: none; font-weight: 750; border: 1px solid var(--line); }
.button.primary { background: var(--ink); color: var(--bg); }
.button.secondary { background: var(--panel); color: var(--ink); }
.section { padding: 28px 0; }
.section-head { display: flex; justify-content: space-between; align-items: end; gap: 20px; margin-bottom: 18px; }
.cards-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 18px; }
.card, .panel { background: var(--panel); border: 1px solid var(--line); border-radius: 22px; padding: 20px; box-shadow: 0 1px 0 rgba(0,0,0,.03); }
.stats-row { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 14px; }
.stat { background: var(--ink); color: var(--bg); border-radius: 20px; padding: 20px; }
.stat span { display: block; font-size: 2rem; font-weight: 850; }
.stat small { color: #e9ddcd; }
.mini-metrics, .kv { display: grid; gap: 8px; margin: 14px 0 0; }
.mini-metrics div, .kv div { display: grid; grid-template-columns: 1fr 1.2fr; gap: 10px; border-top: 1px solid var(--line); padding-top: 8px; }
dt { color: var(--muted); } dd { margin: 0; font-weight: 700; min-width: 0; overflow-wrap: anywhere; }
.two-col { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 18px; }
.metric-table { width: 100%; border-collapse: collapse; background: var(--panel); border: 1px solid var(--line); border-radius: 16px; overflow: hidden; }
.metric-table th, .metric-table td { text-align: left; border-bottom: 1px solid var(--line); padding: 10px 12px; vertical-align: top; }
.metric-table thead th { background: #f1e7d8; }
.compact-table { font-size: .92rem; }
.table-wrap { overflow-x: auto; }
.warnings { color: var(--warn); padding-left: 20px; }
.muted { color: var(--muted); }
.prose pre { white-space: pre-wrap; overflow-wrap: anywhere; background: #f6efe4; padding: 16px; border-radius: 14px; }
@media (max-width: 760px) {
  .topbar { align-items: flex-start; flex-direction: column; }
  .section-head { display: block; }
  .metric-table { min-width: 720px; }
}
"""


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def remove_output(path: Path, site_data: Path) -> None:
    output = path.resolve(strict=False)
    input_path = site_data.resolve(strict=False)
    try:
        input_path.relative_to(output)
        fail(f"output path {path} would contain site-data input {site_data}; choose a separate output directory")
    except ValueError:
        pass
    try:
        output.relative_to(input_path)
        fail(f"output path {path} is inside site-data input {site_data}; choose a separate output directory")
    except ValueError:
        pass
    if path.exists():
        if not path.is_dir():
            fail(f"output path exists and is not a directory: {path}")
        shutil.rmtree(path)


def copy_downloads(bundles: list[CorpusBundle], output: Path, site_data: Path, comparative: dict[str, Any] | None = None) -> None:
    for bundle in bundles:
        target_dir = output / "downloads" / "corpora" / bundle.corpus_id
        target_dir.mkdir(parents=True, exist_ok=True)
        for filename in SAFE_DOWNLOAD_FILES:
            source = bundle.path / filename
            if source.exists():
                shutil.copyfile(source, target_dir / filename)
    if comparative:
        target_dir = output / "downloads" / "comparative"
        target_dir.mkdir(parents=True, exist_ok=True)
        for filename in SAFE_COMPARATIVE_DOWNLOAD_FILES:
            source = site_data / "comparative" / filename
            if source.exists():
                shutil.copyfile(source, target_dir / filename)


def build(site_data: Path, output: Path) -> None:
    bundles = load_bundles(site_data)
    comparative = load_comparative(site_data)
    remove_output(output, site_data)
    output.mkdir(parents=True, exist_ok=True)
    write(output / "assets" / "style.css", stylesheet())
    write(output / "index.html", render_index(bundles))
    write(output / "corpora" / "index.html", render_corpora_index(bundles))
    for bundle in bundles:
        write(output / "corpora" / bundle.corpus_id / "index.html", render_corpus_page(bundle))
    write(output / "comparative" / "index.html", render_comparative(bundles, comparative))
    write(output / "methodology" / "index.html", render_methodology(bundles))
    write(output / "downloads" / "index.html", render_downloads(bundles, comparative))
    copy_downloads(bundles, output, site_data, comparative)


def main() -> int:
    args = parse_args()
    build(args.site_data, args.output)
    print(json.dumps({"status": "ok", "output": str(args.output)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
