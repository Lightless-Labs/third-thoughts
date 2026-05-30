#!/usr/bin/env python3
"""Fixture tests for deterministic public comparative metrics."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "build_public_comparative_metrics.py"


def write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def metric(value: object, status: str = "defined") -> dict[str, object]:
    return {"value": value if status == "defined" else None, "status": status}


def write_bundle(corpora_dir: Path, corpus_id: str, repo: str, sessions: int, strata: dict[str, int], hsmm: float | None) -> None:
    bundle = corpora_dir / corpus_id
    metrics = {
        "schema_version": 1,
        "corpus": {
            "id": corpus_id,
            "dataset_repo": repo,
            "dataset_revision": "abc123",
            "source": "fixture",
            "storage_format": "jsonl",
            "normalizer": None,
        },
        "session_counts": {
            "analysis": sessions,
            "materialized_jsonl_files": sessions,
            "estimated_parse_errors": 0,
            "by_stratum": strata,
        },
        "technique_status": {
            "counts": {"total": 3, "completed": 3, "errored": 0},
            "techniques": {
                "thinking-divergence": {"status": "completed", "version": "fixture", "error_count": 0, "table_row_count": sessions},
                "information-foraging": {"status": "completed", "version": "fixture", "error_count": 0, "table_row_count": sessions},
                "hsmm": {"status": "completed", "version": "fixture", "error_count": 0, "table_row_count": sessions},
            },
        },
        "techniques": {
            "thinking-divergence": {
                "findings": {
                    "suppression_rate": metric(0.95),
                    "divergence_ratio": metric(1.5),
                }
            },
            "information-foraging": {"findings": {"mvt_compliance_rate": metric(0.0)}},
            "hsmm": {"findings": {"pre_correction_lift": metric(hsmm) if hsmm is not None else metric(None, "undefined")}},
            "correction-rate": {"findings": {"overall_mean_rate": metric(0.1), "first_third_rate": metric(0.2), "last_third_rate": metric(None, "undefined")}},
            "entropy": {"findings": {"mean_entropy": metric(1.25)}},
            "ena-analysis": {"findings": {"top_code": metric("TOOL_USE")}},
        },
    }
    write_json(bundle / "metrics.json", metrics)
    write_json(bundle / "corpus.json", {"id": corpus_id, "dataset_repo": repo})
    write_json(bundle / "status.json", {"status": "ok", "warnings": ["language_axis_unavailable: fixture"]})


class BuildPublicComparativeMetricsTest(unittest.TestCase):
    def run_fixture(self) -> Path:
        temp = Path(tempfile.mkdtemp(prefix="public-comparative-"))
        corpora_dir = temp / "site-data" / "corpora"
        write_bundle(corpora_dir, "alpha-pi-mono", "example/pi-mono", 20, {"interactive": 20, "subagent": 0, "autonomous": 0}, 2.0)
        write_bundle(corpora_dir, "beta-pi-mono", "example/pi-mono-copy", 30, {"interactive": 29, "subagent": 0, "autonomous": 1}, 6.0)
        write_bundle(corpora_dir, "gamma-traces", "example/traces", 10, {"interactive": 2, "subagent": 8, "autonomous": 0}, None)
        output = temp / "site-data" / "comparative"
        subprocess.run(
            [sys.executable, str(SCRIPT), "--corpora-dir", str(corpora_dir), "--output", str(output)],
            cwd=ROOT,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        return output

    def test_outputs_required_files_and_corpus_index(self) -> None:
        output = self.run_fixture()
        for name in ["corpus-index.json", "comparative-metrics.json", "technique-status-matrix.json", "finding-replication-matrix.json"]:
            self.assertTrue((output / name).exists(), name)
        index = json.loads((output / "corpus-index.json").read_text(encoding="utf-8"))
        self.assertEqual(index["corpus_count"], 3)
        self.assertEqual(index["total_sessions"], 60)
        self.assertEqual(index["stratum_totals"], {"interactive": 51, "subagent": 8, "autonomous": 1})
        self.assertEqual(index["duplicate_families"], {"pi-mono-family": ["alpha-pi-mono", "beta-pi-mono"]})

    def test_metric_aggregation_keeps_undefined_distinct(self) -> None:
        output = self.run_fixture()
        comparative = json.loads((output / "comparative-metrics.json").read_text(encoding="utf-8"))
        hsmm = comparative["metrics"]["hsmm_pre_correction_lift"]
        self.assertEqual(hsmm["aggregate"]["defined_count"], 2)
        self.assertEqual(hsmm["aggregate"]["undefined_count"], 1)
        self.assertEqual(hsmm["observations"]["gamma-traces"]["status"], "undefined")
        self.assertEqual(hsmm["aggregate"]["numeric"]["min"], 2.0)
        self.assertEqual(hsmm["aggregate"]["numeric"]["max"], 6.0)

    def test_replication_matrix_flags_axes_and_duplicate_families(self) -> None:
        output = self.run_fixture()
        replication = json.loads((output / "finding-replication-matrix.json").read_text(encoding="utf-8"))
        self.assertFalse(replication["axis_coverage"]["language"]["available"])
        self.assertEqual(replication["axis_coverage"]["session_type"]["autonomous_corpora"], 1)
        hsmm_class = replication["findings"]["hsmm_pre_correction_lift"]["classification"]
        self.assertEqual(hsmm_class["classification_input"], "direction_replicated_magnitude_variable")
        self.assertIn("duplicate-shaped corpus families are present; do not count them as independent replications", hsmm_class["warnings"])
        self.assertIn("autonomous stratum too small for behavior claims", hsmm_class["warnings"])


if __name__ == "__main__":
    unittest.main()
