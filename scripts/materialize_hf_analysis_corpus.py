#!/usr/bin/env python3
"""Materialize one pinned public HF corpus for `middens analyze`.

The script reads docs/corpora/public-hf-analysis-corpora.json, downloads the
selected pinned Hugging Face dataset revision, copies supported JSONL session
logs into an output directory, and writes a small manifest. It fails early if the
registry entry is ambiguous or not analysis-enabled.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path
from typing import Any

try:
    from huggingface_hub import snapshot_download
except ImportError as exc:  # pragma: no cover
    print(
        "Missing huggingface_hub. Install with: python3 -m pip install huggingface_hub",
        file=sys.stderr,
    )
    raise SystemExit(2) from exc


METADATA_JSONL_NAMES = {"manifest.jsonl", "sessions.jsonl"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, default=Path("docs/corpora/public-hf-analysis-corpora.json"))
    parser.add_argument("--corpus", required=True, help="Corpus id from the registry.")
    parser.add_argument("--output", type=Path, required=True, help="Output directory for raw JSONL session logs.")
    parser.add_argument("--cache-dir", type=Path, default=Path(".tmp/hf-cache"), help="HF snapshot cache directory.")
    parser.add_argument("--force", action="store_true", help="Overwrite output directory if it already exists.")
    return parser.parse_args()


def fail(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(2)


def sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def load_registry(path: Path) -> dict[str, Any]:
    try:
        registry = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        fail(f"registry not found: {path}")
    except json.JSONDecodeError as exc:
        fail(f"registry is not valid JSON: {path}: {exc}")
    if registry.get("schema_version") != 1:
        fail(f"unsupported registry schema_version {registry.get('schema_version')!r}; expected 1")
    return registry


def select_corpus(registry: dict[str, Any], corpus_id: str) -> dict[str, Any]:
    matches = [c for c in registry.get("corpora", []) if c.get("id") == corpus_id]
    if not matches:
        available = ", ".join(c.get("id", "<missing>") for c in registry.get("corpora", []))
        fail(f"unknown corpus id {corpus_id!r}. Available ids: {available}")
    if len(matches) > 1:
        fail(f"registry has duplicate corpus id {corpus_id!r}; ids must be unique")
    corpus = matches[0]
    if not corpus.get("analysis_enabled", False):
        fail(
            f"corpus {corpus_id!r} is not analysis-enabled. "
            "Expected analysis_enabled=true and storage_format=jsonl."
        )
    if corpus.get("storage_format") != "jsonl":
        fail(
            f"corpus {corpus_id!r} has storage_format={corpus.get('storage_format')!r}; "
            "middens analyze CI currently expects raw JSONL session logs."
        )
    return corpus


def is_session_jsonl(path: Path) -> bool:
    if path.suffix != ".jsonl":
        return False
    if path.name in METADATA_JSONL_NAMES:
        return False
    if any(part in {"indexes", ".cache"} for part in path.parts):
        return False
    return True


def reset_output(path: Path, force: bool) -> None:
    if path.exists():
        if not force:
            fail(f"output directory already exists: {path}. Pass --force to overwrite it.")
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def main() -> int:
    args = parse_args()
    registry = load_registry(args.registry)
    corpus = select_corpus(registry, args.corpus)
    reset_output(args.output, args.force)
    args.cache_dir.mkdir(parents=True, exist_ok=True)

    snapshot = Path(
        snapshot_download(
            repo_id=corpus["dataset_repo"],
            repo_type="dataset",
            revision=corpus["dataset_revision"],
            allow_patterns=["*.jsonl", "README.md", ".gitattributes"],
            cache_dir=args.cache_dir,
        )
    )

    manifest_rows: list[dict[str, Any]] = []
    copied = 0
    for src in sorted(path for path in snapshot.rglob("*.jsonl") if path.is_file() and is_session_jsonl(path)):
        rel = src.relative_to(snapshot)
        dst = args.output / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        copied += 1
        manifest_rows.append(
            {
                "repo_path": rel.as_posix(),
                "sha256": sha256_file(src),
                "size_bytes": src.stat().st_size,
            }
        )

    min_files = int(corpus.get("expected_min_jsonl_files", 1))
    if copied < min_files:
        fail(
            f"corpus {args.corpus!r} materialized only {copied} JSONL file(s), "
            f"below expected_min_jsonl_files={min_files}. Check the pinned revision or registry entry."
        )

    manifest = {
        "corpus_id": corpus["id"],
        "dataset_repo": corpus["dataset_repo"],
        "dataset_revision": corpus["dataset_revision"],
        "description": corpus.get("description"),
        "jsonl_files": copied,
        "objects": manifest_rows,
    }
    (args.output / "_hf_corpus_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    print(json.dumps({k: manifest[k] for k in ("corpus_id", "dataset_repo", "dataset_revision", "jsonl_files")}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
