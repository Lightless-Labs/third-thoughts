#!/usr/bin/env python3
"""Extract public-safe aggregate metrics for one public HF corpus.

This script intentionally emits a curated allowlist, not a copy of middens'
raw technique JSON. The website layer should get boring aggregate evidence, not
session ids, transcript text, tool payloads, or per-session tables.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import shutil
import sys
from pathlib import Path
from typing import Any

REGISTRY_SCHEMA_VERSION = 1
METRICS_SCHEMA_VERSION = 1
EXPECTED_STRATA = ("interactive", "subagent", "autonomous")

SAFE_FINDINGS: dict[str, tuple[str, ...]] = {
    "burstiness": ("aggregate_burstiness", "aggregate_memory", "tools_analyzed"),
    "change-point-detection": (
        "sessions_analyzed",
        "total_change_points",
        "change_points_user_msg_length",
        "change_points_tool_call_rate",
        "change_points_correction_flag",
        "change_points_tool_diversity",
        "mean_change_points_per_session",
    ),
    "convention-epidemiology": (
        "sessions_analyzed",
        "projects_detected",
        "sessions_without_cwd",
        "conventions_detected",
        "conventions_fitted",
        "top_convention_r2",
        "top_convention_r0",
        "epidemic_conventions",
        "cross_project_conventions",
        "ubiquitous_conventions",
        "radial_conventions",
        "sequential_conventions",
        "top_cross_project_reach",
        "mean_inter_project_latency_days",
    ),
    "corpus-timeline": (
        "total_sessions",
        "undated_sessions",
        "total_dates",
        "total_projects",
        "high_concurrency_day_count",
        "date_range_min",
        "date_range_max",
        "peak_day",
    ),
    "correction-rate": (
        "overall_mean_rate",
        "overall_median_rate",
        "sessions_with_corrections",
        "mean_degradation_ratio",
        "first_third_rate",
        "middle_third_rate",
        "last_third_rate",
    ),
    "cross-project-graph": (
        "total_sessions",
        "total_projects",
        "total_edges",
        "total_references",
        "mutual_pair_count",
        "cluster_count",
    ),
    "diversity": (
        "mean_shannon",
        "median_shannon",
        "mean_simpson",
        "mean_evenness",
        "species_area_z",
        "species_area_r_squared",
        "monoculture_count",
        "monoculture_fraction",
        "sessions_analyzed",
    ),
    "ena-analysis": (
        "sessions_analyzed",
        "top_code",
        "top_code_centrality",
        "strongest_low_correction_edge",
        "strongest_high_correction_edge",
    ),
    "entropy": (
        "mean_entropy",
        "anomaly_count",
        "low_entropy_anomalies",
        "high_entropy_anomalies",
        "low_high_ratio",
        "sessions_analyzed",
    ),
    "granger-causality": (
        "significant_pairs",
        "strongest_pair_p",
        "thinking_causes_correction",
        "sessions_analyzed",
    ),
    "hsmm": (
        "optimal_n_states",
        "pre_correction_lift",
        "dominant_pre_correction_state",
        "mean_state_duration_exploring",
        "mean_state_duration_executing",
    ),
    "information-foraging": (
        "mean_patches_per_session",
        "mean_residence_time",
        "mean_foraging_efficiency",
        "explore_exploit_ratio",
        "mvt_compliance_rate",
        "patch_revisit_rate",
        "low_correction_foraging_time",
        "high_correction_foraging_time",
    ),
    "lag-sequential": (
        "total_events",
        "sessions_analyzed",
        "significant_transitions_lag1",
        "significant_transitions_lag2",
        "significant_transitions_lag3",
        "top_positive_transition",
        "top_negative_transition",
    ),
    "markov": ("total_bigrams",),
    "ncd-clustering": (
        "sessions_in_sample",
        "sessions_skipped",
        "optimal_k",
        "silhouette_score",
        "largest_cluster_size",
    ),
    "prefixspan-mining": (
        "total_sessions",
        "sequences_with_tools",
        "min_support_threshold",
        "total_patterns",
        "patterns_length_3",
        "patterns_length_4",
        "patterns_length_5",
        "patterns_length_6",
        "low_correction_sessions",
        "high_correction_sessions",
        "success_patterns",
        "struggle_patterns",
    ),
    "process-mining": ("total_events", "unique_activities", "dfg_edges"),
    "smith-waterman": (
        "mean_alignment_score",
        "conserved_motifs_count",
        "top_success_motif",
        "top_struggle_motif",
        "cluster_count",
    ),
    "spc-control-charts": (
        "sessions_analyzed",
        "correction_rate_mean",
        "correction_rate_ucl",
        "correction_rate_ooc_count",
        "tool_error_rate_ooc_count",
        "assistant_len_ooc_count",
        "cusum_first_alarm_index",
        "rule2_violations",
    ),
    "survival-analysis": (
        "median_survival_turns",
        "survival_at_10",
        "survival_at_20",
        "hazard_trend",
        "cox_concordance",
        "sessions_with_correction",
        "sessions_censored",
    ),
    "thinking-divergence": (
        "suppression_rate",
        "divergence_ratio",
        "sessions_with_thinking",
        "messages_with_both",
        "total_risk_tokens",
        "suppressed_tokens",
        "sessions_analyzed",
        "skipped_redacted_sessions",
        "analyzed_visible_sessions",
        "analyzed_unknown_sessions",
    ),
    "tpattern-detection": ("level_1_patterns", "level_2_patterns", "most_common_pattern", "total_events_analyzed"),
    "user-signal-analysis": (
        "total_user_messages",
        "messages_classified",
        "skipped_non_english_messages",
        "boilerplate_messages",
        "corrections",
        "redirects",
        "directives",
        "approvals",
        "questions",
        "escalations_found",
    ),
}

STRING_RULES: dict[tuple[str, str], re.Pattern[str]] = {
    ("corpus-timeline", "date_range_min"): re.compile(r"^\d{4}-\d{2}-\d{2}$"),
    ("corpus-timeline", "date_range_max"): re.compile(r"^\d{4}-\d{2}-\d{2}$"),
    ("corpus-timeline", "peak_day"): re.compile(r"^\d{4}-\d{2}-\d{2}$"),
    ("correction-rate", "sessions_with_corrections"): re.compile(r"^\d+/\d+$"),
    ("ena-analysis", "top_code"): re.compile(r"^[A-Z_]+$"),
    ("ena-analysis", "strongest_low_correction_edge"): re.compile(r"^[A-Z_]+↔[A-Z_]+$"),
    ("ena-analysis", "strongest_high_correction_edge"): re.compile(r"^[A-Z_]+↔[A-Z_]+$"),
    ("lag-sequential", "top_positive_transition"): re.compile(r"^[A-Z]+→[A-Z]+ \(lag=\d+, z=-?\d+(\.\d+)?\)$"),
    ("lag-sequential", "top_negative_transition"): re.compile(r"^[A-Z]+→[A-Z]+ \(lag=\d+, z=-?\d+(\.\d+)?\)$"),
    ("smith-waterman", "top_success_motif"): re.compile(r"^[A-Z]+$"),
    ("smith-waterman", "top_struggle_motif"): re.compile(r"^[A-Z]+$"),
    ("survival-analysis", "hazard_trend"): re.compile(r"^(increasing|decreasing|flat|unknown)$"),
    ("tpattern-detection", "most_common_pattern"): re.compile(r"^[A-Z]+(->[A-Z]+)+$"),
}

PUBLIC_REGISTRY_KEYS = (
    "id",
    "dataset_repo",
    "dataset_revision",
    "source",
    "storage_format",
    "description",
    "analysis_enabled",
    "ci_tiers",
    "expected_min_jsonl_files",
    "expected_min_sessions",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus-id", required=True)
    parser.add_argument("--registry", type=Path, default=Path("docs/corpora/public-hf-analysis-corpora.json"))
    parser.add_argument("--analysis-output", type=Path, required=True, help="Directory containing flat middens technique JSON outputs")
    parser.add_argument("--split-output", type=Path, required=True, help="Directory containing split middens technique JSON outputs")
    parser.add_argument("--analysis-dir", type=Path, required=True, help="Middens flat run directory containing manifest.json")
    parser.add_argument("--split-analysis-dir", type=Path, required=True, help="Middens split run directory containing manifest.json")
    parser.add_argument("--materialized-corpus", type=Path, default=None, help="Optional materialized corpus directory or _hf_corpus_manifest.json")
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


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def require_dir(path: Path, label: str) -> None:
    if not path.exists():
        fail(f"{label} does not exist: {path}")
    if not path.is_dir():
        fail(f"{label} must be a directory: {path}")


def canonical_technique(name: str) -> str:
    return name.replace("_", "-")


def load_registry(path: Path) -> dict[str, Any]:
    registry = load_json(path, "registry")
    if registry.get("schema_version") != REGISTRY_SCHEMA_VERSION:
        fail(f"unsupported registry schema_version {registry.get('schema_version')!r}; expected {REGISTRY_SCHEMA_VERSION}")
    if not isinstance(registry.get("corpora"), list):
        fail("registry must contain a 'corpora' list")
    return registry


def find_corpus(registry: dict[str, Any], corpus_id: str) -> dict[str, Any]:
    for corpus in registry["corpora"]:
        if corpus.get("id") == corpus_id:
            return corpus
    enabled_ids = [str(c.get("id")) for c in registry["corpora"] if c.get("analysis_enabled", False)]
    fail(f"unknown corpus id {corpus_id!r}. Enabled corpus ids: {', '.join(enabled_ids)}")


def manifest_path(run_dir: Path, label: str) -> Path:
    require_dir(run_dir, label)
    path = run_dir / "manifest.json"
    if not path.exists():
        fail(f"{label} must contain manifest.json: {run_dir}")
    return path


def materialized_manifest_path(path: Path | None) -> Path | None:
    if path is None:
        return None
    if path.is_file():
        return path
    if path.is_dir():
        return path / "_hf_corpus_manifest.json"
    fail(f"materialized corpus path does not exist: {path}")


def load_materialization(path: Path | None) -> dict[str, Any] | None:
    resolved = materialized_manifest_path(path)
    if resolved is None:
        return None
    return load_json(resolved, "materialized corpus manifest")


def aggregate_object_hash(objects: list[Any]) -> str | None:
    hashes: list[str] = []
    for obj in objects:
        if not isinstance(obj, dict):
            continue
        value = obj.get("sha256") or obj.get("source_sha256")
        if isinstance(value, str):
            hashes.append(value)
    if not hashes:
        return None
    digest = hashlib.sha256("\n".join(sorted(hashes)).encode("utf-8")).hexdigest()
    return digest


def public_corpus_record(corpus: dict[str, Any], materialization: dict[str, Any] | None) -> dict[str, Any]:
    record = {key: corpus.get(key) for key in PUBLIC_REGISTRY_KEYS if key in corpus}
    mat_objects = materialization.get("objects", []) if isinstance(materialization, dict) else []
    record["materialization"] = {
        "available": materialization is not None,
        "jsonl_files": materialization.get("jsonl_files") if isinstance(materialization, dict) else None,
        "normalizer": materialization.get("normalizer") if isinstance(materialization, dict) else None,
        "object_count": len(mat_objects) if isinstance(mat_objects, list) else None,
        "object_hash_fingerprint": aggregate_object_hash(mat_objects) if isinstance(mat_objects, list) else None,
    }
    return record


def finite_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


def safe_scalar_value(technique: str, label: str, value: Any) -> tuple[bool, Any]:
    if value is None or isinstance(value, bool) or finite_number(value):
        return True, value
    if isinstance(value, str):
        pattern = STRING_RULES.get((technique, label))
        if pattern and pattern.match(value):
            return True, value
        return False, None
    return False, None


def finding_map(result: dict[str, Any]) -> dict[str, Any]:
    mapped: dict[str, Any] = {}
    for finding in result.get("findings", []):
        if not isinstance(finding, dict):
            continue
        label = finding.get("label")
        if isinstance(label, str):
            mapped[label] = finding.get("value")
    return mapped


def load_technique_results(output_dir: Path) -> dict[str, dict[str, Any]]:
    require_dir(output_dir, "analysis output")
    results: dict[str, dict[str, Any]] = {}
    for path in sorted(output_dir.glob("*.json")):
        data = load_json(path, f"technique result {path.name}")
        name = data.get("name") if isinstance(data, dict) else None
        key = canonical_technique(str(name or path.stem))
        if not isinstance(data, dict):
            fail(f"technique result must be a JSON object: {path}")
        results[key] = data
    return results


def technique_statuses(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    statuses: dict[str, dict[str, Any]] = {}
    for entry in manifest.get("techniques", []):
        if not isinstance(entry, dict):
            continue
        name = entry.get("name")
        if not isinstance(name, str):
            continue
        errors = entry.get("errors", [])
        error_count = len(errors) if isinstance(errors, list) else 1
        key = canonical_technique(name)
        statuses[key] = {
            "version": entry.get("version"),
            "status": "error" if error_count else "completed",
            "error_count": error_count,
            "table_row_count": (entry.get("table") or {}).get("row_count") if isinstance(entry.get("table"), dict) else None,
        }
    return statuses


def status_counts(statuses: dict[str, dict[str, Any]]) -> dict[str, int]:
    completed = sum(1 for status in statuses.values() if status.get("status") == "completed")
    errored = sum(1 for status in statuses.values() if status.get("status") == "error")
    return {"total": len(statuses), "completed": completed, "errored": errored}


def extract_safe_findings(
    results: dict[str, dict[str, Any]], statuses: dict[str, dict[str, Any]], warnings: list[str]
) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for technique in sorted(SAFE_FINDINGS):
        result = results.get(technique)
        values = finding_map(result or {})
        findings: dict[str, dict[str, Any]] = {}
        for label in SAFE_FINDINGS[technique]:
            if label not in values:
                findings[label] = {"value": None, "status": "undefined", "reason": "finding_absent"}
                continue
            ok, safe_value = safe_scalar_value(technique, label, values[label])
            if ok:
                findings[label] = {"value": safe_value, "status": "defined"}
            else:
                findings[label] = {"value": None, "status": "redacted", "reason": "non_allowlisted_value_shape"}
                warnings.append(f"redacted unsafe value shape for {technique}.{label}")
        output[technique] = {
            "status": statuses.get(technique, {"status": "not_run", "error_count": 0}),
            "findings": findings,
        }
    return output


def sanitized_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    corpus_fingerprint = dict(manifest.get("corpus_fingerprint") or {})
    corpus_fingerprint.pop("source_paths", None)
    sanitized: dict[str, Any] = {
        "run_id": manifest.get("run_id"),
        "created_at": manifest.get("created_at"),
        "analyzer_fingerprint": manifest.get("analyzer_fingerprint"),
        "corpus_fingerprint": corpus_fingerprint,
    }
    if "strata" in manifest:
        sanitized["strata"] = [
            {
                "name": stratum.get("name"),
                "session_count": stratum.get("session_count"),
                "manifest_ref": stratum.get("manifest_ref"),
            }
            for stratum in manifest.get("strata", [])
            if isinstance(stratum, dict)
        ]
    sanitized["techniques"] = [
        {
            "name": canonical_technique(entry.get("name", "")),
            "version": entry.get("version"),
            "status": "error" if entry.get("errors") else "completed",
            "error_count": len(entry.get("errors", [])) if isinstance(entry.get("errors", []), list) else 1,
            "table": {
                "name": (entry.get("table") or {}).get("name") if isinstance(entry.get("table"), dict) else None,
                "row_count": (entry.get("table") or {}).get("row_count") if isinstance(entry.get("table"), dict) else None,
            },
        }
        for entry in manifest.get("techniques", [])
        if isinstance(entry, dict)
    ]
    return sanitized


def split_counts(split_manifest: dict[str, Any]) -> dict[str, int | None]:
    counts: dict[str, int | None] = {name: None for name in EXPECTED_STRATA}
    for stratum in split_manifest.get("strata", []):
        if not isinstance(stratum, dict):
            continue
        name = stratum.get("name")
        if name in counts:
            counts[str(name)] = stratum.get("session_count")
    return counts


def load_stratum_statuses(split_analysis_dir: Path, split_manifest: dict[str, Any]) -> dict[str, Any]:
    by_stratum: dict[str, Any] = {}
    for stratum in split_manifest.get("strata", []):
        if not isinstance(stratum, dict):
            continue
        name = stratum.get("name")
        ref = stratum.get("manifest_ref")
        if not isinstance(name, str) or not isinstance(ref, str):
            continue
        path = split_analysis_dir / ref
        if not path.exists():
            by_stratum[name] = {"manifest_available": False, "counts": {"total": 0, "completed": 0, "errored": 0}, "techniques": {}}
            continue
        manifest = load_json(path, f"split stratum manifest {name}")
        statuses = technique_statuses(manifest)
        expected_count = stratum.get("session_count")
        manifest_count = manifest.get("corpus_fingerprint", {}).get("session_count")
        by_stratum[name] = {
            "manifest_available": True,
            "session_count": expected_count,
            "manifest_session_count": manifest_count,
            "session_count_matches_manifest": expected_count == manifest_count,
            "counts": status_counts(statuses),
            "techniques": statuses,
        }
    return by_stratum


def build_warnings(corpus: dict[str, Any], materialization: dict[str, Any] | None, metrics: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    total_sessions = metrics["session_counts"].get("analysis")
    if isinstance(total_sessions, int) and total_sessions < 30:
        warnings.append("tiny_n: fewer than 30 parsed sessions; aggregate findings are smoke-test evidence only")
    autonomous = metrics["session_counts"].get("by_stratum", {}).get("autonomous")
    if autonomous == 0:
        warnings.append("autonomous_axis_empty: no autonomous sessions in split output")
    elif isinstance(autonomous, int) and autonomous < 10:
        warnings.append("autonomous_axis_tiny: fewer than 10 autonomous sessions; do not make autonomous-loop behavior claims")
    warnings.append("language_axis_unavailable: current metrics are not gated by detected language")
    repo = str(corpus.get("dataset_repo", ""))
    corpus_id = str(corpus.get("id", ""))
    if "pi-mono" in repo or "pi-mono" in corpus_id:
        warnings.append("duplicate_shape_possible: pi-mono-family corpora need deduplication before independent-replication claims")
    if materialization is None:
        warnings.append("materialization_manifest_missing: normalizer/object fingerprint unavailable")
    parse_errors = metrics["session_counts"].get("estimated_parse_errors")
    if isinstance(parse_errors, int) and parse_errors > 0:
        warnings.append("parse_errors_present: materialized JSONL file count exceeds parsed session count")
    mismatched_strata = [
        name
        for name, status in metrics.get("technique_status_by_stratum", {}).items()
        if isinstance(status, dict) and status.get("session_count_matches_manifest") is False
    ]
    if mismatched_strata:
        warnings.append(
            "split_manifest_count_mismatch: stratum manifest session counts differ from top-level split counts for "
            + ",".join(sorted(mismatched_strata))
        )
    return warnings


def path_contains(parent: Path, child: Path) -> bool:
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


def ensure_output_does_not_overlap(output: Path, inputs: list[Path]) -> None:
    output_resolved = output.resolve(strict=False)
    for input_path in inputs:
        input_resolved = input_path.resolve(strict=False)
        if output_resolved == input_resolved or path_contains(output_resolved, input_resolved) or path_contains(input_resolved, output_resolved):
            fail(
                f"output path overlaps an input path: output={output}, input={input_path}. "
                "Use a separate directory, e.g. --output site-data/corpora/<id>."
            )


def remove_output_dir(path: Path) -> None:
    if path.exists():
        if not path.is_dir():
            fail(f"output path exists and is not a directory: {path}")
        shutil.rmtree(path)


def build_metrics(
    corpus: dict[str, Any],
    materialization: dict[str, Any] | None,
    analysis_manifest: dict[str, Any],
    split_manifest: dict[str, Any],
    analysis_results: dict[str, dict[str, Any]],
    split_stratum_statuses: dict[str, Any],
) -> tuple[dict[str, Any], list[str]]:
    warnings: list[str] = []
    analysis_session_count = analysis_manifest.get("corpus_fingerprint", {}).get("session_count")
    materialized_jsonl = materialization.get("jsonl_files") if isinstance(materialization, dict) else None
    estimated_parse_errors = None
    if isinstance(materialized_jsonl, int) and isinstance(analysis_session_count, int):
        estimated_parse_errors = max(materialized_jsonl - analysis_session_count, 0)

    statuses = technique_statuses(analysis_manifest)
    session_counts = {
        "analysis": analysis_session_count,
        "materialized_jsonl_files": materialized_jsonl,
        "estimated_parse_errors": estimated_parse_errors,
        "by_stratum": split_counts(split_manifest),
    }
    metrics: dict[str, Any] = {
        "schema_version": METRICS_SCHEMA_VERSION,
        "corpus": {
            "id": corpus.get("id"),
            "dataset_repo": corpus.get("dataset_repo"),
            "dataset_revision": corpus.get("dataset_revision"),
            "source": corpus.get("source"),
            "storage_format": corpus.get("storage_format"),
            "normalizer": materialization.get("normalizer") if isinstance(materialization, dict) else None,
        },
        "session_counts": session_counts,
        "technique_status": {"counts": status_counts(statuses), "techniques": statuses},
        "technique_status_by_stratum": split_stratum_statuses,
        "techniques": extract_safe_findings(analysis_results, statuses, warnings),
    }
    warnings.extend(build_warnings(corpus, materialization, metrics))
    return metrics, sorted(set(warnings))


def main() -> int:
    args = parse_args()
    registry = load_registry(args.registry)
    corpus = find_corpus(registry, args.corpus_id)
    if not corpus.get("analysis_enabled", False):
        fail(f"corpus {args.corpus_id!r} has analysis_enabled=false; enable it before extracting website metrics")

    require_dir(args.analysis_output, "analysis output")
    require_dir(args.split_output, "split output")
    analysis_manifest = load_json(manifest_path(args.analysis_dir, "analysis dir"), "analysis manifest")
    split_manifest = load_json(manifest_path(args.split_analysis_dir, "split analysis dir"), "split manifest")
    materialization = load_materialization(args.materialized_corpus)

    if materialization is not None and materialization.get("corpus_id") != args.corpus_id:
        fail(
            f"materialized corpus manifest corpus_id={materialization.get('corpus_id')!r} "
            f"does not match --corpus-id {args.corpus_id!r}"
        )

    ensure_output_does_not_overlap(
        args.output,
        [args.registry, args.analysis_output, args.split_output, args.analysis_dir, args.split_analysis_dir]
        + ([args.materialized_corpus] if args.materialized_corpus is not None else []),
    )

    analysis_results = load_technique_results(args.analysis_output)
    split_stratum_statuses = load_stratum_statuses(args.split_analysis_dir, split_manifest)
    metrics, warnings = build_metrics(corpus, materialization, analysis_manifest, split_manifest, analysis_results, split_stratum_statuses)

    status = {
        "schema_version": METRICS_SCHEMA_VERSION,
        "corpus_id": args.corpus_id,
        "status": "ok",
        "warnings": warnings,
        "outputs": ["corpus.json", "analysis-manifest.json", "split-manifest.json", "metrics.json", "status.json"],
    }

    remove_output_dir(args.output)
    args.output.mkdir(parents=True, exist_ok=True)
    write_json(args.output / "corpus.json", public_corpus_record(corpus, materialization))
    write_json(args.output / "analysis-manifest.json", sanitized_manifest(analysis_manifest))
    split_sanitized = sanitized_manifest(split_manifest)
    split_sanitized["stratum_statuses"] = split_stratum_statuses
    write_json(args.output / "split-manifest.json", split_sanitized)
    write_json(args.output / "metrics.json", metrics)
    write_json(args.output / "status.json", status)
    print(json.dumps({"status": "ok", "corpus_id": args.corpus_id, "output": str(args.output)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
