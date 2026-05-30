#!/usr/bin/env python3
"""Fixture tests for the public results static site generator."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "build_public_results_site.py"


def write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_bundle(site_data: Path, corpus_id: str, sessions: int, autonomous: int, unsafe_marker: str | None = None) -> None:
    bundle = site_data / "corpora" / corpus_id
    metrics = {
        "schema_version": 1,
        "corpus": {
            "id": corpus_id,
            "dataset_repo": f"example/{corpus_id}",
            "dataset_revision": "abc123",
            "source": "fixture",
            "storage_format": "jsonl",
            "normalizer": None,
        },
        "session_counts": {
            "analysis": sessions,
            "materialized_jsonl_files": sessions,
            "estimated_parse_errors": 0,
            "by_stratum": {"interactive": sessions - autonomous, "subagent": 0, "autonomous": autonomous},
        },
        "technique_status": {
            "counts": {"total": 2, "completed": 2, "errored": 0},
            "techniques": {
                "correction-rate": {"status": "completed", "version": "fixture", "error_count": 0, "table_row_count": sessions},
                "thinking-divergence": {"status": "completed", "version": "fixture", "error_count": 0, "table_row_count": sessions},
            },
        },
        "technique_status_by_stratum": {},
        "techniques": {
            "thinking-divergence": {
                "status": {"status": "completed"},
                "findings": {"suppression_rate": {"value": 0.95, "status": "defined"}},
            },
            "correction-rate": {
                "status": {"status": "completed"},
                "findings": {
                    "overall_mean_rate": {"value": 0.1, "status": "defined"},
                    "first_third_rate": {"value": 0.2, "status": "defined"},
                    "last_third_rate": {"value": None, "status": "undefined"},
                },
            },
            "information-foraging": {
                "status": {"status": "completed"},
                "findings": {"mvt_compliance_rate": {"value": 0.0, "status": "defined"}},
            },
            "hsmm": {
                "status": {"status": "completed"},
                "findings": {"pre_correction_lift": {"value": 3.5, "status": "defined"}},
            },
            "entropy": {"status": {"status": "completed"}, "findings": {"mean_entropy": {"value": 1.25, "status": "defined"}}},
            "ena-analysis": {"status": {"status": "completed"}, "findings": {"top_code": {"value": "TOOL_USE", "status": "defined"}}},
        },
    }
    write_json(bundle / "metrics.json", metrics)
    write_json(
        bundle / "corpus.json",
        {
            "id": corpus_id,
            "dataset_repo": f"example/{corpus_id}",
            "dataset_revision": "abc123",
            "storage_format": "jsonl",
            "description": "Fixture corpus" + (f" {unsafe_marker}" if unsafe_marker else ""),
            "materialization": {"available": True, "jsonl_files": sessions, "normalizer": None, "object_count": sessions},
        },
    )
    write_json(bundle / "status.json", {"schema_version": 1, "corpus_id": corpus_id, "status": "ok", "warnings": ["tiny_n"]})
    write_json(bundle / "analysis-manifest.json", {"run_id": "run-fixture", "techniques": []})
    write_json(bundle / "split-manifest.json", {"run_id": "run-split", "strata": []})


class BuildPublicResultsSiteTest(unittest.TestCase):
    def run_site(self) -> Path:
        temp = Path(tempfile.mkdtemp(prefix="public-results-site-"))
        site_data = temp / "site-data"
        write_bundle(site_data, "fixture-a", sessions=12, autonomous=0)
        write_bundle(site_data, "fixture-b", sessions=31, autonomous=1, unsafe_marker='<script>alert("nope")</script>')
        output = temp / "site-out"
        subprocess.run(
            [sys.executable, str(SCRIPT), "--site-data", str(site_data), "--output", str(output)],
            check=True,
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        return output

    def test_builds_required_pages_and_safe_downloads(self) -> None:
        output = self.run_site()
        required = [
            "index.html",
            "corpora/index.html",
            "corpora/fixture-a/index.html",
            "corpora/fixture-b/index.html",
            "comparative/index.html",
            "methodology/index.html",
            "downloads/index.html",
            "assets/style.css",
            "downloads/corpora/fixture-a/metrics.json",
            "downloads/corpora/fixture-a/corpus.json",
            "downloads/corpora/fixture-a/status.json",
        ]
        for relative in required:
            self.assertTrue((output / relative).exists(), relative)

        self.assertFalse((output / "downloads" / "corpora" / "fixture-a" / "raw.jsonl").exists())
        home = (output / "index.html").read_text(encoding="utf-8")
        self.assertIn('href="corpora/fixture-a/index.html"', home)
        self.assertIn("95.00%", (output / "corpora" / "fixture-a" / "index.html").read_text(encoding="utf-8"))
        self.assertIn("—", (output / "corpora" / "fixture-a" / "index.html").read_text(encoding="utf-8"))

    def test_html_escapes_data_values(self) -> None:
        output = self.run_site()
        page = (output / "corpora" / "fixture-b" / "index.html").read_text(encoding="utf-8")
        self.assertNotIn("<script>", page)
        self.assertIn("&lt;script&gt;", page)

    def test_rejects_empty_site_data(self) -> None:
        temp = Path(tempfile.mkdtemp(prefix="public-results-site-empty-"))
        site_data = temp / "site-data"
        (site_data / "corpora").mkdir(parents=True)
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--site-data", str(site_data), "--output", str(temp / "out")],
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("no corpus metric bundles", result.stderr)


if __name__ == "__main__":
    unittest.main()
