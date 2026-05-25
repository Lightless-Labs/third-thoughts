#!/usr/bin/env python3
"""Emit a GitHub Actions matrix from the public HF corpus registry."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, default=Path("docs/corpora/public-hf-analysis-corpora.json"))
    parser.add_argument("--tier", default=None, help="CI tier to select, e.g. smoke, representative, full. Defaults to registry default_ci_tier.")
    parser.add_argument("--corpus", default="all", help="Specific corpus id or 'all'.")
    return parser.parse_args()


def fail(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(2)


def load_registry(path: Path) -> dict[str, Any]:
    try:
        registry = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        fail(f"registry not found: {path}")
    except json.JSONDecodeError as exc:
        fail(f"registry is not valid JSON: {path}: {exc}")
    if registry.get("schema_version") != 1:
        fail(f"unsupported registry schema_version {registry.get('schema_version')!r}; expected 1")
    if not isinstance(registry.get("corpora"), list):
        fail("registry must contain a 'corpora' list")
    return registry


def main() -> int:
    args = parse_args()
    registry = load_registry(args.registry)
    tier = args.tier or registry.get("default_ci_tier") or "representative"

    selected = []
    for corpus in registry["corpora"]:
        if not corpus.get("analysis_enabled", False):
            continue
        if args.corpus != "all" and corpus.get("id") != args.corpus:
            continue
        if args.corpus == "all" and tier not in corpus.get("ci_tiers", []):
            continue
        selected.append(
            {
                "id": corpus["id"],
                "dataset_repo": corpus["dataset_repo"],
                "dataset_revision": corpus["dataset_revision"],
            }
        )

    if not selected:
        enabled_ids = [c.get("id") for c in registry["corpora"] if c.get("analysis_enabled", False)]
        fail(
            f"no corpora selected for tier={tier!r}, corpus={args.corpus!r}. "
            f"Enabled corpus ids: {', '.join(enabled_ids)}"
        )

    print(json.dumps({"include": selected}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
