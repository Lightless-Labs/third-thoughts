#!/usr/bin/env python3
"""Build deterministic comparative metrics from public-safe corpus bundles."""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
EXPECTED_STRATA = ("interactive", "subagent", "autonomous")
SELECTED_METRICS: tuple[dict[str, str], ...] = (
    {"id": "risk_suppression", "label": "Risk suppression", "technique": "thinking-divergence", "finding": "suppression_rate", "kind": "percent", "direction": "higher"},
    {"id": "thinking_text_divergence", "label": "Thinking/text divergence", "technique": "thinking-divergence", "finding": "divergence_ratio", "kind": "number", "direction": "descriptive"},
    {"id": "correction_mean", "label": "Mean correction rate", "technique": "correction-rate", "finding": "overall_mean_rate", "kind": "percent", "direction": "descriptive"},
    {"id": "correction_first_third", "label": "First-third correction rate", "technique": "correction-rate", "finding": "first_third_rate", "kind": "percent", "direction": "descriptive"},
    {"id": "correction_last_third", "label": "Last-third correction rate", "technique": "correction-rate", "finding": "last_third_rate", "kind": "percent", "direction": "descriptive"},
    {"id": "mvt_compliance", "label": "MVT compliance", "technique": "information-foraging", "finding": "mvt_compliance_rate", "kind": "percent", "direction": "higher"},
    {"id": "hsmm_pre_correction_lift", "label": "HSMM pre-correction lift", "technique": "hsmm", "finding": "pre_correction_lift", "kind": "multiplier", "direction": "above_one"},
    {"id": "tool_entropy", "label": "Tool entropy", "technique": "entropy", "finding": "mean_entropy", "kind": "number", "direction": "descriptive"},
    {"id": "ena_top_code", "label": "ENA top code", "technique": "ena-analysis", "finding": "top_code", "kind": "string", "direction": "descriptive"},
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpora-dir", type=Path, required=True)
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


def ensure_corpora_dir(path: Path) -> None:
    if not path.exists():
        fail(f"corpora-dir does not exist: {path}")
    if not path.is_dir():
        fail(f"corpora-dir must be a directory: {path}")


def load_bundles(corpora_dir: Path) -> dict[str, dict[str, Any]]:
    ensure_corpora_dir(corpora_dir)
    bundles: dict[str, dict[str, Any]] = {}
    for path in sorted(p for p in corpora_dir.iterdir() if p.is_dir()):
        metrics = load_json(path / "metrics.json", f"metrics for {path.name}")
        corpus_id = metrics.get("corpus", {}).get("id")
        if not isinstance(corpus_id, str):
            fail(f"metrics for {path.name} must contain corpus.id")
        if corpus_id != path.name:
            fail(f"corpus directory name {path.name!r} does not match metrics corpus id {corpus_id!r}")
        corpus = load_json(path / "corpus.json", f"corpus metadata for {path.name}") if (path / "corpus.json").exists() else {}
        status = load_json(path / "status.json", f"status for {path.name}") if (path / "status.json").exists() else {}
        bundles[corpus_id] = {"path": path, "metrics": metrics, "corpus": corpus, "status": status}
    if not bundles:
        fail(f"no corpus bundles found under {corpora_dir}")
    return bundles


def finite_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


def duplicate_family(metrics: dict[str, Any]) -> str | None:
    corpus = metrics.get("corpus", {})
    joined = " ".join(str(corpus.get(key, "")) for key in ("id", "dataset_repo", "source"))
    if "pi-mono" in joined:
        return "pi-mono-family"
    return None


def warning_codes(status: dict[str, Any]) -> list[str]:
    warnings = status.get("warnings", []) if isinstance(status, dict) else []
    codes: list[str] = []
    for warning in warnings if isinstance(warnings, list) else []:
        if not isinstance(warning, str):
            continue
        codes.append(warning.split(":", 1)[0])
    return sorted(set(codes))


def corpus_index(bundles: dict[str, dict[str, Any]]) -> dict[str, Any]:
    corpora = []
    duplicate_families: dict[str, list[str]] = {}
    for corpus_id in sorted(bundles):
        metrics = bundles[corpus_id]["metrics"]
        corpus = metrics.get("corpus", {})
        counts = metrics.get("session_counts", {})
        strata = counts.get("by_stratum", {}) if isinstance(counts.get("by_stratum"), dict) else {}
        family = duplicate_family(metrics)
        if family:
            duplicate_families.setdefault(family, []).append(corpus_id)
        corpora.append(
            {
                "id": corpus_id,
                "dataset_repo": corpus.get("dataset_repo"),
                "dataset_revision": corpus.get("dataset_revision"),
                "source": corpus.get("source"),
                "storage_format": corpus.get("storage_format"),
                "normalizer": corpus.get("normalizer"),
                "session_count": counts.get("analysis"),
                "materialized_jsonl_files": counts.get("materialized_jsonl_files"),
                "estimated_parse_errors": counts.get("estimated_parse_errors"),
                "strata": {name: strata.get(name) for name in EXPECTED_STRATA},
                "warning_codes": warning_codes(bundles[corpus_id].get("status", {})),
                "duplicate_family": family,
            }
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "corpus_count": len(corpora),
        "total_sessions": sum(int(c.get("session_count") or 0) for c in corpora),
        "stratum_totals": {
            name: sum(int((c.get("strata") or {}).get(name) or 0) for c in corpora) for name in EXPECTED_STRATA
        },
        "duplicate_families": {family: ids for family, ids in sorted(duplicate_families.items()) if len(ids) > 1},
        "corpora": corpora,
    }


def technique_status_matrix(bundles: dict[str, dict[str, Any]]) -> dict[str, Any]:
    techniques = sorted(
        {
            technique
            for bundle in bundles.values()
            for technique in (bundle["metrics"].get("technique_status", {}).get("techniques", {}) or {}).keys()
        }
    )
    matrix: dict[str, dict[str, Any]] = {}
    for technique in techniques:
        matrix[technique] = {}
        for corpus_id in sorted(bundles):
            status = bundles[corpus_id]["metrics"].get("technique_status", {}).get("techniques", {}).get(technique)
            matrix[technique][corpus_id] = status or {"status": "not_run", "error_count": 0, "table_row_count": None, "version": None}
    counts_by_corpus = {
        corpus_id: bundles[corpus_id]["metrics"].get("technique_status", {}).get("counts", {}) for corpus_id in sorted(bundles)
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "corpora": sorted(bundles),
        "techniques": techniques,
        "counts_by_corpus": counts_by_corpus,
        "matrix": matrix,
    }


def finding_entry(metrics: dict[str, Any], technique: str, finding: str) -> dict[str, Any] | None:
    try:
        entry = metrics["techniques"][technique]["findings"][finding]
    except KeyError:
        return None
    return entry if isinstance(entry, dict) else None


def observation_for(bundle: dict[str, Any], metric: dict[str, str]) -> dict[str, Any]:
    metrics = bundle["metrics"]
    entry = finding_entry(metrics, metric["technique"], metric["finding"])
    if entry is None:
        return {"status": "missing", "value": None}
    status = entry.get("status", "unknown")
    value = entry.get("value") if status == "defined" else None
    return {"status": status, "value": value}


def aggregate_observations(observations: dict[str, dict[str, Any]]) -> dict[str, Any]:
    defined_values = [obs.get("value") for obs in observations.values() if obs.get("status") == "defined"]
    numeric_values = [float(value) for value in defined_values if finite_number(value)]
    status_counts: dict[str, int] = {}
    for obs in observations.values():
        status = str(obs.get("status", "unknown"))
        status_counts[status] = status_counts.get(status, 0) + 1
    aggregate: dict[str, Any] = {
        "defined_count": len(defined_values),
        "undefined_count": sum(1 for obs in observations.values() if obs.get("status") != "defined"),
        "status_counts": dict(sorted(status_counts.items())),
    }
    if numeric_values:
        aggregate["numeric"] = {
            "min": min(numeric_values),
            "max": max(numeric_values),
            "mean": statistics.fmean(numeric_values),
            "range": max(numeric_values) - min(numeric_values),
        }
        positive = [value for value in numeric_values if value > 0]
        if positive:
            aggregate["numeric"]["max_min_ratio_positive"] = max(positive) / min(positive)
    else:
        frequencies: dict[str, int] = {}
        for value in defined_values:
            key = str(value)
            frequencies[key] = frequencies.get(key, 0) + 1
        aggregate["categorical"] = dict(sorted(frequencies.items()))
    return aggregate


def comparative_metrics(bundles: dict[str, dict[str, Any]]) -> dict[str, Any]:
    metrics_out: dict[str, Any] = {}
    for metric in SELECTED_METRICS:
        observations = {corpus_id: observation_for(bundles[corpus_id], metric) for corpus_id in sorted(bundles)}
        metrics_out[metric["id"]] = {
            "label": metric["label"],
            "technique": metric["technique"],
            "finding": metric["finding"],
            "kind": metric["kind"],
            "direction": metric["direction"],
            "observations": observations,
            "aggregate": aggregate_observations(observations),
        }
    return {
        "schema_version": SCHEMA_VERSION,
        "corpora": sorted(bundles),
        "selected_metrics": [dict(metric) for metric in SELECTED_METRICS],
        "metrics": metrics_out,
    }


def axis_coverage(index: dict[str, Any]) -> dict[str, Any]:
    strata_totals = index.get("stratum_totals", {})
    corpus_count = int(index.get("corpus_count") or 0)
    return {
        "session_type": {
            "interactive_corpora": sum(1 for c in index.get("corpora", []) if int((c.get("strata") or {}).get("interactive") or 0) > 0),
            "subagent_corpora": sum(1 for c in index.get("corpora", []) if int((c.get("strata") or {}).get("subagent") or 0) > 0),
            "autonomous_corpora": sum(1 for c in index.get("corpora", []) if int((c.get("strata") or {}).get("autonomous") or 0) > 0),
            "totals": {name: strata_totals.get(name, 0) for name in EXPECTED_STRATA},
        },
        "language": {
            "available": False,
            "reason": "language detection is not yet part of the public metrics bundle",
            "affected_corpora": corpus_count,
        },
        "thinking_visibility": {
            "available": False,
            "reason": "public comparative bundle has aggregate visible/redacted hints only, not full axis stratification",
            "affected_corpora": corpus_count,
        },
    }


def classify_metric(metric_id: str, observations: dict[str, dict[str, Any]], aggregate: dict[str, Any], index: dict[str, Any]) -> dict[str, Any]:
    defined = int(aggregate.get("defined_count") or 0)
    total = len(observations)
    numeric = aggregate.get("numeric", {}) if isinstance(aggregate.get("numeric"), dict) else {}
    duplicate_warning = bool(index.get("duplicate_families"))
    result: dict[str, Any] = {
        "defined_corpora": defined,
        "total_corpora": total,
        "classification_input": "not_tested" if defined == 0 else "descriptive",
        "warnings": [],
    }
    if defined == 0:
        result["warnings"].append("metric undefined for all selected corpora")
        return result
    if defined < total:
        result["warnings"].append("metric missing or undefined for at least one selected corpus")
    if duplicate_warning:
        result["warnings"].append("duplicate-shaped corpus families are present; do not count them as independent replications")

    values = [obs.get("value") for obs in observations.values() if obs.get("status") == "defined" and finite_number(obs.get("value"))]
    if metric_id == "risk_suppression":
        if values and min(values) >= 0.9:
            result["classification_input"] = "direction_consistent_high"
        else:
            result["classification_input"] = "mixed_or_low"
        result["threshold"] = ">=0.90 in defined corpora"
    elif metric_id == "mvt_compliance":
        if values and max(values) == 0:
            result["classification_input"] = "direction_consistent_zero"
        elif values:
            result["classification_input"] = "mixed"
        result["threshold"] = "0 means no observed MVT-compliant sessions"
    elif metric_id == "hsmm_pre_correction_lift":
        if values and min(values) > 1:
            ratio = numeric.get("max_min_ratio_positive")
            if isinstance(ratio, (int, float)) and ratio > 2:
                result["classification_input"] = "direction_replicated_magnitude_variable"
            else:
                result["classification_input"] = "direction_replicated"
        elif values:
            result["classification_input"] = "mixed_direction"
        result["threshold"] = ">1.0 indicates elevated pre-correction state probability"
    if index.get("stratum_totals", {}).get("autonomous", 0) == 0:
        result["warnings"].append("autonomous stratum absent across selected corpora")
    elif index.get("stratum_totals", {}).get("autonomous", 0) < 10:
        result["warnings"].append("autonomous stratum too small for behavior claims")
    result["warnings"] = sorted(set(result["warnings"]))
    return result


def finding_replication_matrix(index: dict[str, Any], comparative: dict[str, Any]) -> dict[str, Any]:
    findings: dict[str, Any] = {}
    for metric_id, metric in comparative["metrics"].items():
        findings[metric_id] = {
            "label": metric["label"],
            "technique": metric["technique"],
            "finding": metric["finding"],
            "aggregate": metric["aggregate"],
            "observations": metric["observations"],
            "classification": classify_metric(metric_id, metric["observations"], metric["aggregate"], index),
        }
    return {
        "schema_version": SCHEMA_VERSION,
        "corpora": comparative["corpora"],
        "axis_coverage": axis_coverage(index),
        "duplicate_families": index.get("duplicate_families", {}),
        "findings": findings,
    }


def build(corpora_dir: Path, output: Path) -> None:
    bundles = load_bundles(corpora_dir)
    index = corpus_index(bundles)
    technique_matrix = technique_status_matrix(bundles)
    comparative = comparative_metrics(bundles)
    replication = finding_replication_matrix(index, comparative)
    output.mkdir(parents=True, exist_ok=True)
    write_json(output / "corpus-index.json", index)
    write_json(output / "technique-status-matrix.json", technique_matrix)
    write_json(output / "comparative-metrics.json", comparative)
    write_json(output / "finding-replication-matrix.json", replication)


def main() -> int:
    args = parse_args()
    build(args.corpora_dir, args.output)
    print(json.dumps({"status": "ok", "output": str(args.output)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
