#!/usr/bin/env python3
"""Fixture tests for public corpus metrics extraction."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "extract_public_corpus_metrics.py"


def write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


class ExtractPublicCorpusMetricsTest(unittest.TestCase):
    def run_fixture(self, corpus_id: str, storage_format: str, normalizer: str | None) -> tuple[Path, dict]:
        temp = Path(tempfile.mkdtemp(prefix=f"metrics-{corpus_id}-"))
        registry = temp / "registry.json"
        write_json(
            registry,
            {
                "schema_version": 1,
                "corpora": [
                    {
                        "id": corpus_id,
                        "dataset_repo": f"example/{corpus_id}",
                        "dataset_revision": "abc123",
                        "source": "fixture",
                        "storage_format": storage_format,
                        "description": "Fixture corpus",
                        "analysis_enabled": True,
                        "ci_tiers": ["smoke"],
                        "expected_min_jsonl_files": 2,
                        "expected_min_sessions": 2,
                        "notes": "This note should not be copied to corpus.json",
                    }
                ],
            },
        )

        analysis_output = temp / "analysis-output"
        write_json(
            analysis_output / "correction-rate.json",
            {
                "name": "correction-rate",
                "findings": [
                    {"label": "overall_mean_rate", "value": 0.25},
                    {"label": "sessions_with_corrections", "value": "1/2"},
                ],
                "tables": [
                    {
                        "name": "per_session",
                        "columns": ["session_id", "raw_text"],
                        "rows": [["raw-session-1", "please do the private thing"]],
                    }
                ],
            },
        )
        write_json(
            analysis_output / "change-point-detection.json",
            {
                "name": "change-point-detection",
                "findings": [
                    {"label": "total_change_points", "value": 3},
                    {"label": "most_volatile_session_id", "value": "raw-session-1"},
                ],
                "tables": [],
            },
        )

        analysis_dir = temp / "analysis-run"
        write_json(
            analysis_dir / "manifest.json",
            {
                "run_id": "run-fixture",
                "created_at": "2026-05-29T00:00:00Z",
                "analyzer_fingerprint": {"middens_version": "fixture"},
                "corpus_fingerprint": {
                    "manifest_hash": "deadbeef",
                    "short": "deadbeef",
                    "session_count": 2,
                    "source_paths": ["private/project/raw-session-1.jsonl", "private/project/raw-session-2.jsonl"],
                },
                "techniques": [
                    {
                        "name": "correction-rate",
                        "version": "fixture",
                        "summary": "contains summary",
                        "findings": [],
                        "table": {"name": "per_session", "parquet": "data/correction.parquet", "row_count": 2},
                        "errors": [],
                    },
                    {
                        "name": "change-point-detection",
                        "version": "fixture",
                        "table": {"name": "per_session", "parquet": "data/change.parquet", "row_count": 2},
                        "errors": [],
                    },
                    {
                        "name": "hsmm",
                        "version": "fixture",
                        "table": {"name": "states", "parquet": "data/hsmm.parquet", "row_count": 0},
                        "errors": [],
                    },
                ],
            },
        )

        split_output = temp / "split-output"
        split_output.mkdir()
        split_dir = temp / "split-run"
        write_json(
            split_dir / "manifest.json",
            {
                "run_id": "run-split-fixture",
                "created_at": "2026-05-29T00:00:00Z",
                "analyzer_fingerprint": {"middens_version": "fixture"},
                "corpus_fingerprint": {"manifest_hash": "feedface", "short": "feedface", "session_count": 2, "source_paths": ["private/path"]},
                "strata": [
                    {"name": "interactive", "session_count": 1, "manifest_ref": "interactive/manifest.json"},
                    {"name": "subagent", "session_count": 1, "manifest_ref": "subagent/manifest.json"},
                    {"name": "autonomous", "session_count": 0, "manifest_ref": "autonomous/manifest.json"},
                ],
                "techniques": [],
            },
        )
        for stratum, count in (("interactive", 1), ("subagent", 1), ("autonomous", 0)):
            write_json(
                split_dir / stratum / "manifest.json",
                {
                    "run_id": f"run-{stratum}",
                    "created_at": "2026-05-29T00:00:00Z",
                    "analyzer_fingerprint": {"middens_version": "fixture"},
                    "corpus_fingerprint": {"manifest_hash": stratum, "short": stratum[:8], "session_count": count, "source_paths": ["private/path"]},
                    "techniques": [
                        {"name": "correction-rate", "version": "fixture", "table": {"row_count": count}, "errors": []}
                    ],
                },
            )

        materialized = temp / "materialized"
        write_json(
            materialized / "_hf_corpus_manifest.json",
            {
                "corpus_id": corpus_id,
                "dataset_repo": f"example/{corpus_id}",
                "dataset_revision": "abc123",
                "jsonl_files": 2,
                **({"normalizer": normalizer} if normalizer else {}),
                "objects": [
                    {"repo_path": "private/raw-session-1.jsonl", "sha256": "a" * 64, "size_bytes": 10},
                    {"generated_path": "private/raw-session-2.jsonl", "source_sha256": "b" * 64, "source_size_bytes": 20},
                ],
            },
        )

        output = temp / "site-data" / "corpora" / corpus_id
        subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--corpus-id",
                corpus_id,
                "--registry",
                str(registry),
                "--analysis-output",
                str(analysis_output),
                "--split-output",
                str(split_output),
                "--analysis-dir",
                str(analysis_dir),
                "--split-analysis-dir",
                str(split_dir),
                "--materialized-corpus",
                str(materialized),
                "--output",
                str(output),
            ],
            check=True,
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        return output, json.loads((output / "metrics.json").read_text(encoding="utf-8"))

    def assert_public_safe(self, output: Path) -> None:
        rendered = "\n".join(path.read_text(encoding="utf-8") for path in sorted(output.glob("*.json")))
        self.assertNotIn("raw-session-1", rendered)
        self.assertNotIn("please do the private thing", rendered)
        self.assertNotIn("private/project", rendered)
        self.assertNotIn("source_paths", rendered)
        self.assertNotIn("per_session\",\n      \"rows", rendered)

    def test_jsonl_fixture_emits_safe_aggregate_metrics(self) -> None:
        output, metrics = self.run_fixture("fixture-jsonl", "jsonl", None)
        self.assertEqual(metrics["corpus"]["storage_format"], "jsonl")
        self.assertIsNone(metrics["corpus"]["normalizer"])
        self.assertEqual(metrics["session_counts"]["analysis"], 2)
        self.assertEqual(metrics["session_counts"]["estimated_parse_errors"], 0)
        self.assertEqual(metrics["session_counts"]["by_stratum"], {"interactive": 1, "subagent": 1, "autonomous": 0})
        self.assertEqual(metrics["techniques"]["correction-rate"]["findings"]["overall_mean_rate"]["value"], 0.25)
        self.assertEqual(metrics["techniques"]["hsmm"]["findings"]["pre_correction_lift"]["status"], "undefined")
        self.assert_public_safe(output)

    def test_parquet_fixture_records_normalizer_without_raw_objects(self) -> None:
        output, metrics = self.run_fixture("fixture-parquet", "parquet_trace_rows", "trace_row_v1")
        corpus = json.loads((output / "corpus.json").read_text(encoding="utf-8"))
        self.assertEqual(metrics["corpus"]["storage_format"], "parquet_trace_rows")
        self.assertEqual(metrics["corpus"]["normalizer"], "trace_row_v1")
        self.assertEqual(corpus["materialization"]["normalizer"], "trace_row_v1")
        self.assertEqual(corpus["materialization"]["object_count"], 2)
        self.assertIsNotNone(corpus["materialization"]["object_hash_fingerprint"])
        self.assertNotIn("notes", corpus)
        self.assert_public_safe(output)


if __name__ == "__main__":
    unittest.main()
