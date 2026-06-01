#!/usr/bin/env python3
"""Fixture tests for public comparative interpretation."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "interpret_public_comparison.py"
PROMPT = ROOT / "docs" / "prompts" / "public-comparative-interpretation-v1.md"


def write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


class InterpretPublicComparisonTest(unittest.TestCase):
    def make_bundle(self) -> Path:
        temp = Path(tempfile.mkdtemp(prefix="interpret-public-comparison-"))
        comparative = temp / "site-data" / "comparative"
        write_json(
            comparative / "corpus-index.json",
            {
                "schema_version": 1,
                "corpus_count": 2,
                "total_sessions": 43,
                "stratum_totals": {"interactive": 40, "subagent": 3, "autonomous": 0},
                "duplicate_families": {"pi-mono-family": ["fixture-a", "fixture-b"]},
            },
        )
        write_json(
            comparative / "comparative-metrics.json",
            {
                "schema_version": 1,
                "metrics": {
                    "risk_suppression": {
                        "label": "Risk suppression",
                        "aggregate": {"defined_count": 2, "numeric": {"min": 0.91, "max": 0.95}},
                    }
                },
            },
        )
        write_json(comparative / "technique-status-matrix.json", {"schema_version": 1, "matrix": {}})
        write_json(
            comparative / "finding-replication-matrix.json",
            {
                "schema_version": 1,
                "axis_coverage": {
                    "session_type": {"autonomous_corpora": 0},
                    "language": {"available": False},
                    "thinking_visibility": {"available": False},
                },
                "findings": {"risk_suppression": {"classification": {"classification_input": "direction_consistent_high"}}},
            },
        )
        return comparative

    def run_script(self, comparative: Path, response: str) -> subprocess.CompletedProcess[str]:
        response_file = comparative.parent.parent / "response.md"
        response_file.write_text(response, encoding="utf-8")
        return subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--comparative-dir",
                str(comparative),
                "--prompt",
                str(PROMPT),
                "--model",
                "fixture/model",
                "--response-file",
                str(response_file),
            ],
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

    def good_response(self, word: str = "first") -> str:
        return (
            "## Cross-corpus summary\n"
            f"{word}: 2 corpora, 43 sessions, autonomous total 0.\n\n"
            "## Replicated or directionally consistent patterns\n"
            "Risk suppression ranges 0.91 to 0.95.\n\n"
            "## Variable, provisional, or not tested\n"
            "Duplicate family warning applies.\n\n"
            "## Coverage gaps\n"
            "Language and thinking-visibility axes unavailable.\n\n"
            "## Suggested public wording\n"
            "Directionally consistent, not pooled replication.\n"
        )

    def test_response_file_writes_interpretation_and_metadata(self) -> None:
        comparative = self.make_bundle()
        result = self.run_script(comparative, self.good_response())
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("43 sessions", (comparative / "interpretation.md").read_text(encoding="utf-8"))
        metadata = json.loads((comparative / "interpretation.json").read_text(encoding="utf-8"))
        self.assertEqual(metadata["status"], "completed")
        self.assertRegex(metadata["fingerprint"], r"^[0-9a-f]{64}$")

    def test_unchanged_fingerprint_skips(self) -> None:
        comparative = self.make_bundle()
        self.assertEqual(self.run_script(comparative, self.good_response("first")).returncode, 0)
        second = self.run_script(comparative, self.good_response("second"))
        self.assertEqual(second.returncode, 0, second.stderr)
        metadata = json.loads((comparative / "interpretation.json").read_text(encoding="utf-8"))
        self.assertEqual(metadata["status"], "skipped")
        self.assertIn("first", (comparative / "interpretation.md").read_text(encoding="utf-8"))
        self.assertNotIn("second", (comparative / "interpretation.md").read_text(encoding="utf-8"))

    def test_dry_run_writes_prompt(self) -> None:
        comparative = self.make_bundle()
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--comparative-dir", str(comparative), "--prompt", str(PROMPT), "--model", "fixture/model", "--dry-run"],
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('"total_sessions": 43', (comparative / "interpretation.prompt.md").read_text(encoding="utf-8"))
        self.assertFalse((comparative / "interpretation.md").exists())

    def test_rejects_unsafe_response(self) -> None:
        comparative = self.make_bundle()
        result = self.run_script(comparative, "## Cross-corpus summary\nSee /Users/thomas/raw.jsonl\n")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unsafe", result.stderr.lower())


if __name__ == "__main__":
    unittest.main()
