#!/usr/bin/env python3
"""Fixture tests for HF corpus matrix selection."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "hf_corpus_matrix.py"


def write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


class HfCorpusMatrixTest(unittest.TestCase):
    def make_registry(self) -> Path:
        temp = Path(tempfile.mkdtemp(prefix="hf-matrix-"))
        registry = temp / "corpora.json"
        write_json(
            registry,
            {
                "schema_version": 1,
                "default_ci_tier": "smoke",
                "corpora": [
                    {
                        "id": "publish-and-interpret",
                        "dataset_repo": "example/publish-and-interpret",
                        "dataset_revision": "abc123",
                        "analysis_enabled": True,
                        "publish_enabled": True,
                        "interpret_enabled": True,
                        "ci_tiers": ["smoke"],
                    },
                    {
                        "id": "publish-no-interpret",
                        "dataset_repo": "example/publish-no-interpret",
                        "dataset_revision": "def456",
                        "analysis_enabled": True,
                        "publish_enabled": True,
                        "interpret_enabled": False,
                        "ci_tiers": ["smoke"],
                    },
                    {
                        "id": "analysis-only",
                        "dataset_repo": "example/analysis-only",
                        "dataset_revision": "ghi789",
                        "analysis_enabled": True,
                        "publish_enabled": False,
                        "interpret_enabled": True,
                        "ci_tiers": ["smoke"],
                    },
                ],
            },
        )
        return registry

    def run_matrix(self, registry: Path, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--registry", str(registry), *args],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

    def test_matrix_includes_publish_and_interpret_controls(self) -> None:
        result = self.run_matrix(self.make_registry(), "--tier", "smoke")
        self.assertEqual(result.returncode, 0, result.stderr)
        matrix = json.loads(result.stdout)
        by_id = {entry["id"]: entry for entry in matrix["include"]}

        self.assertEqual(set(by_id), {"publish-and-interpret", "publish-no-interpret"})
        self.assertIs(by_id["publish-and-interpret"]["publish_enabled"], True)
        self.assertIs(by_id["publish-and-interpret"]["interpret_enabled"], True)
        self.assertIs(by_id["publish-no-interpret"]["publish_enabled"], True)
        self.assertIs(by_id["publish-no-interpret"]["interpret_enabled"], False)

    def test_explicit_analysis_only_corpus_fails_clearly(self) -> None:
        result = self.run_matrix(self.make_registry(), "--corpus", "analysis-only")
        self.assertEqual(result.returncode, 2)
        self.assertIn("no publishable corpora selected", result.stderr)
        self.assertIn("Analysis+publish enabled corpus ids", result.stderr)


if __name__ == "__main__":
    unittest.main()
