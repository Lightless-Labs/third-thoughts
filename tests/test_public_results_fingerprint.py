#!/usr/bin/env python3
"""Fixture tests for public results fingerprint helpers."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FINGERPRINT_SCRIPT = ROOT / "scripts" / "public_results_fingerprint.py"
CHANGED_SCRIPT = ROOT / "scripts" / "public_results_changed.py"


def write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


class PublicResultsFingerprintTest(unittest.TestCase):
    def make_fixture(self) -> tuple[Path, Path, Path, Path]:
        temp = Path(tempfile.mkdtemp(prefix="public-fingerprint-"))
        registry = temp / "registry.json"
        corpus_id = "fixture-corpus"
        write_json(
            registry,
            {
                "schema_version": 1,
                "corpora": [
                    {
                        "id": corpus_id,
                        "dataset_repo": "example/fixture-corpus",
                        "dataset_revision": "abc123",
                        "source": "fixture",
                        "storage_format": "jsonl",
                        "description": "public fixture",
                        "analysis_enabled": True,
                        "ci_tiers": ["smoke"],
                        "expected_min_jsonl_files": 2,
                        "expected_min_sessions": 2,
                    }
                ],
            },
        )
        materialized = temp / "materialized"
        write_json(
            materialized / "_hf_corpus_manifest.json",
            {
                "corpus_id": corpus_id,
                "dataset_repo": "example/fixture-corpus",
                "dataset_revision": "abc123",
                "storage_format": "jsonl",
                "normalizer": None,
                "jsonl_files": 2,
                "objects": [
                    {"repo_path": "private/raw-one.jsonl", "sha256": "a" * 64, "size_bytes": 10},
                    {"repo_path": "private/raw-two.jsonl", "sha256": "b" * 64, "size_bytes": 20},
                ],
            },
        )
        metrics = temp / "metrics.json"
        write_json(metrics, {"schema_version": 1, "corpus": {"id": corpus_id}, "session_counts": {"analysis": 2}})
        output = temp / "fingerprints.json"
        return registry, materialized, metrics, output

    def run_fingerprint(self, registry: Path, materialized: Path, metrics: Path, output: Path) -> dict:
        subprocess.run(
            [
                sys.executable,
                str(FINGERPRINT_SCRIPT),
                "--corpus-id",
                "fixture-corpus",
                "--registry",
                str(registry),
                "--materialized-corpus",
                str(materialized),
                "--metrics",
                str(metrics),
                "--model",
                "fixture/model",
                "--output",
                str(output),
            ],
            cwd=ROOT,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        return json.loads(output.read_text(encoding="utf-8"))

    def test_emits_stable_public_safe_fingerprints(self) -> None:
        registry, materialized, metrics, output = self.make_fixture()
        first = self.run_fingerprint(registry, materialized, metrics, output)
        second = self.run_fingerprint(registry, materialized, metrics, output)
        self.assertEqual(first, second)
        self.assertEqual(first["schema_version"], 1)
        self.assertEqual(set(first["fingerprints"]), {"corpus", "process", "interpretation"})
        self.assertRegex(first["fingerprints"]["corpus"]["fingerprint"], r"^[0-9a-f]{64}$")
        self.assertEqual(first["fingerprints"]["corpus"]["components"]["materialization"]["object_count"], 2)

        rendered = json.dumps(first, sort_keys=True)
        self.assertNotIn("private/raw-one.jsonl", rendered)
        self.assertNotIn("repo_path", rendered)
        self.assertNotIn("raw-two", rendered)

    def test_changed_helper_reports_reusable_and_mismatch(self) -> None:
        registry, materialized, metrics, current_path = self.make_fixture()
        current = self.run_fingerprint(registry, materialized, metrics, current_path)
        previous_path = current_path.with_name("previous.json")
        write_json(previous_path, current)

        result = subprocess.run(
            [sys.executable, str(CHANGED_SCRIPT), "--current", str(current_path), "--previous", str(previous_path), "--scope", "analysis"],
            cwd=ROOT,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self.assertEqual(json.loads(result.stdout)["reusable"], True)

        previous = json.loads(previous_path.read_text(encoding="utf-8"))
        previous["fingerprints"]["process"]["fingerprint"] = "0" * 64
        write_json(previous_path, previous)
        result = subprocess.run(
            [sys.executable, str(CHANGED_SCRIPT), "--current", str(current_path), "--previous", str(previous_path), "--scope", "analysis"],
            cwd=ROOT,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        parsed = json.loads(result.stdout)
        self.assertEqual(parsed["changed"], True)
        self.assertIn("process", parsed["reason"])


if __name__ == "__main__":
    unittest.main()
