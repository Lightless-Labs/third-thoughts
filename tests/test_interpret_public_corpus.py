#!/usr/bin/env python3
"""Fixture tests for public per-corpus interpretation."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "interpret_public_corpus.py"
PROMPT = ROOT / "docs" / "prompts" / "public-corpus-interpretation-v1.md"


def write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


class InterpretPublicCorpusTest(unittest.TestCase):
    def make_bundle(self) -> Path:
        temp = Path(tempfile.mkdtemp(prefix="interpret-public-corpus-"))
        bundle = temp / "site-data" / "corpora" / "fixture-corpus"
        write_json(
            bundle / "metrics.json",
            {
                "schema_version": 1,
                "corpus": {"id": "fixture-corpus", "dataset_repo": "example/fixture", "storage_format": "jsonl"},
                "session_counts": {
                    "analysis": 12,
                    "by_stratum": {"interactive": 10, "subagent": 2, "autonomous": 0},
                },
                "techniques": {
                    "thinking-divergence": {
                        "findings": {"suppression_rate": {"status": "defined", "value": 0.95}}
                    },
                    "hsmm": {"findings": {"pre_correction_lift": {"status": "undefined", "value": None}}},
                },
            },
        )
        write_json(bundle / "analysis-manifest.json", {"run_id": "run-fixture", "techniques": []})
        write_json(bundle / "split-manifest.json", {"run_id": "run-split", "strata": []})
        write_json(
            bundle / "fingerprints.json",
            {
                "schema_version": 1,
                "corpus_id": "fixture-corpus",
                "fingerprints": {
                    "corpus": {"fingerprint": "a" * 64},
                    "process": {"fingerprint": "b" * 64},
                    "interpretation": {"fingerprint": "c" * 64, "components": {"enabled": False}},
                },
            },
        )
        return bundle

    def run_script(self, bundle: Path, response: str, extra: list[str] | None = None) -> subprocess.CompletedProcess[str]:
        response_file = bundle.parent.parent.parent / "response.md"
        response_file.write_text(response, encoding="utf-8")
        args = [
            sys.executable,
            str(SCRIPT),
            "--corpus-dir",
            str(bundle),
            "--prompt",
            str(PROMPT),
            "--model",
            "fixture/model",
            "--response-file",
            str(response_file),
        ]
        if extra:
            args.extend(extra)
        return subprocess.run(args, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    def test_response_file_writes_interpretation_metadata_and_fingerprint(self) -> None:
        bundle = self.make_bundle()
        result = self.run_script(
            bundle,
            "## Summary\n12 sessions; 10 interactive, 2 subagent, 0 autonomous. Suppression is 0.95.\n\n"
            "## What is actually measured\nOnly curated metrics.\n\n"
            "## Caveats before anyone gets excited\nTiny N; autonomous is zero.\n\n"
            "## Suggested public wording\nSmoke-test evidence only.\n",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        interpretation = (bundle / "interpretation.md").read_text(encoding="utf-8")
        metadata = json.loads((bundle / "interpretation.json").read_text(encoding="utf-8"))
        fingerprints = json.loads((bundle / "fingerprints.json").read_text(encoding="utf-8"))
        self.assertIn("Suppression is 0.95", interpretation)
        self.assertEqual(metadata["status"], "completed")
        self.assertRegex(metadata["fingerprint"], r"^[0-9a-f]{64}$")
        self.assertEqual(fingerprints["fingerprints"]["interpretation"]["fingerprint"], metadata["fingerprint"])
        self.assertNotIn("source_paths", json.dumps(metadata))

    def test_unchanged_fingerprint_skips_without_force(self) -> None:
        bundle = self.make_bundle()
        first = self.run_script(bundle, "## Summary\nfirst\n\n## What is actually measured\nmetrics\n\n## Caveats before anyone gets excited\ncaveats\n\n## Suggested public wording\nwording\n")
        self.assertEqual(first.returncode, 0, first.stderr)
        second = self.run_script(bundle, "## Summary\nsecond\n\n## What is actually measured\nmetrics\n\n## Caveats before anyone gets excited\ncaveats\n\n## Suggested public wording\nwording\n")
        self.assertEqual(second.returncode, 0, second.stderr)
        metadata = json.loads((bundle / "interpretation.json").read_text(encoding="utf-8"))
        self.assertEqual(metadata["status"], "skipped")
        self.assertIn("first", (bundle / "interpretation.md").read_text(encoding="utf-8"))
        self.assertNotIn("second", (bundle / "interpretation.md").read_text(encoding="utf-8"))

    def test_dry_run_writes_prompt_not_interpretation(self) -> None:
        bundle = self.make_bundle()
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--corpus-dir", str(bundle), "--prompt", str(PROMPT), "--model", "fixture/model", "--dry-run"],
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        prompt = (bundle / "interpretation.prompt.md").read_text(encoding="utf-8")
        self.assertIn('"analysis": 12', prompt)
        self.assertFalse((bundle / "interpretation.md").exists())

    def test_rejects_unsafe_response_markers(self) -> None:
        bundle = self.make_bundle()
        result = self.run_script(bundle, "## Summary\nSee /Users/thomas/private/raw-session.jsonl\n")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unsafe", result.stderr.lower())


if __name__ == "__main__":
    unittest.main()
