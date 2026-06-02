#!/usr/bin/env python3
"""Compute public-safe fingerprints for public results corpus bundles.

The fingerprints are designed for invalidation/reuse decisions. They deliberately
hash raw-ish materialization details instead of copying them into site-data:
public corpus object paths and session ids are useful for debugging, but not for
a public website bundle.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
REGISTRY_SCHEMA_VERSION = 1
DEFAULT_ANALYSIS_FLAGS: dict[str, Any] = {
    "flat": {"techniques": "all", "timeout_seconds": 1800, "force": True},
    "split": {"split": True, "no_python": True},
}
PROCESS_SOURCE_GLOBS: tuple[str, ...] = (
    "middens/Cargo.toml",
    "middens/Cargo.lock",
    "middens/src/**/*.rs",
    "middens/python/techniques/*.py",
    "scripts/materialize_hf_analysis_corpus.py",
    "scripts/extract_public_corpus_metrics.py",
    "scripts/build_public_comparative_metrics.py",
    "scripts/build_public_results_site.py",
    "scripts/public_results_fingerprint.py",
    ".github/workflows/hf-corpus-analysis.yml",
)
PUBLIC_REGISTRY_KEYS: tuple[str, ...] = (
    "id",
    "dataset_repo",
    "dataset_revision",
    "source",
    "storage_format",
    "analysis_enabled",
    "publish_enabled",
    "interpret_enabled",
    "ci_tiers",
    "expected_min_jsonl_files",
    "expected_min_sessions",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus-id", required=True)
    parser.add_argument("--registry", type=Path, default=Path("docs/corpora/public-hf-analysis-corpora.json"))
    parser.add_argument(
        "--materialized-corpus",
        type=Path,
        default=None,
        help="Materialized corpus directory or _hf_corpus_manifest.json. If omitted, corpus fingerprint records that materialization is unavailable.",
    )
    parser.add_argument("--metrics", type=Path, default=None, help="Optional public-safe metrics.json for interpretation fingerprinting.")
    parser.add_argument("--analysis-flags", type=Path, default=None, help="Optional JSON object overriding default analysis flags.")
    parser.add_argument("--model", default=None, help="Optional interpretation model/provider id.")
    parser.add_argument("--prompt-template", type=Path, default=None, help="Optional interpretation prompt template file.")
    parser.add_argument("--temperature", default=None, help="Optional interpretation temperature/settings value.")
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def fail(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(2)


def canonical_json(data: Any) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def hash_json(data: Any) -> str:
    return hashlib.sha256(canonical_json(data).encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


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


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def load_registry(path: Path) -> dict[str, Any]:
    registry = load_json(path, "registry")
    if not isinstance(registry, dict):
        fail("registry must be a JSON object")
    if registry.get("schema_version") != REGISTRY_SCHEMA_VERSION:
        fail(f"unsupported registry schema_version {registry.get('schema_version')!r}; expected {REGISTRY_SCHEMA_VERSION}")
    if not isinstance(registry.get("corpora"), list):
        fail("registry must contain a corpora list")
    return registry


def find_corpus(registry: dict[str, Any], corpus_id: str) -> dict[str, Any]:
    matches = [corpus for corpus in registry.get("corpora", []) if isinstance(corpus, dict) and corpus.get("id") == corpus_id]
    if not matches:
        enabled = ", ".join(str(c.get("id")) for c in registry.get("corpora", []) if isinstance(c, dict) and c.get("analysis_enabled"))
        fail(f"unknown corpus id {corpus_id!r}. Enabled corpus ids: {enabled}")
    if len(matches) > 1:
        fail(f"registry has duplicate corpus id {corpus_id!r}; ids must be unique")
    return matches[0]


def materialized_manifest_path(path: Path | None) -> Path | None:
    if path is None:
        return None
    if path.is_file():
        return path
    if path.is_dir():
        return path / "_hf_corpus_manifest.json"
    fail(f"materialized corpus path does not exist: {path}")


def load_materialization(path: Path | None, corpus_id: str) -> dict[str, Any] | None:
    manifest_path = materialized_manifest_path(path)
    if manifest_path is None:
        return None
    materialization = load_json(manifest_path, "materialized corpus manifest")
    if not isinstance(materialization, dict):
        fail("materialized corpus manifest must be a JSON object")
    if materialization.get("corpus_id") != corpus_id:
        fail(
            f"materialized corpus manifest corpus_id={materialization.get('corpus_id')!r} "
            f"does not match --corpus-id {corpus_id!r}"
        )
    return materialization


def registry_fingerprint_entry(corpus: dict[str, Any]) -> dict[str, Any]:
    return {key: corpus.get(key) for key in PUBLIC_REGISTRY_KEYS if key in corpus}


def object_fingerprint_rows(objects: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not isinstance(objects, list):
        return rows
    for index, obj in enumerate(objects):
        if not isinstance(obj, dict):
            continue
        content_hash = obj.get("sha256") or obj.get("source_sha256")
        if not isinstance(content_hash, str):
            continue
        row: dict[str, Any] = {
            "index": index,
            "content_sha256": content_hash,
            "size_bytes": obj.get("size_bytes") or obj.get("source_size_bytes"),
        }
        if "row_index" in obj:
            row["row_index"] = obj.get("row_index")
        if "normalizer" in obj:
            row["normalizer"] = obj.get("normalizer")
        rows.append(row)
    return rows


def corpus_fingerprint(corpus: dict[str, Any], materialization: dict[str, Any] | None) -> dict[str, Any]:
    registry_entry = registry_fingerprint_entry(corpus)
    objects = materialization.get("objects") if isinstance(materialization, dict) else None
    object_rows = object_fingerprint_rows(objects)
    materialization_summary = {
        "available": materialization is not None,
        "dataset_repo": materialization.get("dataset_repo") if isinstance(materialization, dict) else None,
        "dataset_revision": materialization.get("dataset_revision") if isinstance(materialization, dict) else None,
        "storage_format": materialization.get("storage_format") if isinstance(materialization, dict) else None,
        "normalizer": materialization.get("normalizer") if isinstance(materialization, dict) else None,
        "jsonl_files": materialization.get("jsonl_files") if isinstance(materialization, dict) else None,
        "object_count": len(objects) if isinstance(objects, list) else None,
        "object_hash_count": len(object_rows) if isinstance(materialization, dict) else None,
        "object_hash_fingerprint": hash_json(object_rows) if object_rows else None,
    }
    components = {"registry_entry": registry_entry, "materialization": materialization_summary}
    return {"fingerprint": hash_json(components), "components": components}


def git_sha(root: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except Exception:
        return None
    value = result.stdout.strip()
    return value or None


def middens_version(root: Path) -> str | None:
    cargo_toml = root / "middens" / "Cargo.toml"
    if not cargo_toml.exists():
        return None
    in_package = False
    for line in cargo_toml.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped == "[package]":
            in_package = True
            continue
        if stripped.startswith("[") and stripped.endswith("]"):
            in_package = False
            continue
        if in_package:
            match = re.match(r'^version\s*=\s*"([^"]+)"\s*$', stripped)
            if match:
                return match.group(1)
    return None


def matched_process_files(root: Path) -> list[Path]:
    files: set[Path] = set()
    for pattern in PROCESS_SOURCE_GLOBS:
        for path in root.glob(pattern):
            if path.is_file():
                files.add(path)
    return sorted(files, key=lambda p: p.relative_to(root).as_posix())


def source_hashes(root: Path) -> dict[str, str]:
    return {path.relative_to(root).as_posix(): sha256_file(path) for path in matched_process_files(root)}


def load_analysis_flags(path: Path | None) -> dict[str, Any]:
    if path is None:
        return DEFAULT_ANALYSIS_FLAGS
    data = load_json(path, "analysis flags")
    if not isinstance(data, dict):
        fail(f"analysis flags must be a JSON object: {path}")
    return data


def process_fingerprint(root: Path, analysis_flags: dict[str, Any]) -> dict[str, Any]:
    sources = source_hashes(root)
    components = {
        "repo_git_sha": git_sha(root),
        "middens_version": middens_version(root),
        "analysis_flags": analysis_flags,
        "source_hashes": sources,
        "source_tree_hash": hash_json(sources),
    }
    return {"fingerprint": hash_json(components), "components": components}


def interpretation_fingerprint(
    *,
    metrics_path: Path | None,
    model: str | None,
    prompt_template: Path | None,
    temperature: str | None,
) -> dict[str, Any]:
    metrics_hash = None
    if metrics_path is not None:
        metrics_hash = hash_json(load_json(metrics_path, "metrics"))
    prompt_hash = None
    prompt_name = None
    if prompt_template is not None:
        if not prompt_template.is_file():
            fail(f"prompt template not found: {prompt_template}")
        prompt_hash = sha256_file(prompt_template)
        prompt_name = prompt_template.name
    enabled = any(value is not None for value in (metrics_path, model, prompt_template, temperature))
    components = {
        "enabled": enabled,
        "metrics_input_hash": metrics_hash,
        "model": model,
        "prompt_template": prompt_name,
        "prompt_template_hash": prompt_hash,
        "temperature": temperature,
        "script_hash": sha256_file(repo_root() / "scripts" / "public_results_fingerprint.py"),
    }
    return {"fingerprint": hash_json(components), "components": components}


def build_fingerprints(
    *,
    corpus_id: str,
    registry_path: Path,
    materialized_corpus: Path | None = None,
    metrics_path: Path | None = None,
    analysis_flags_path: Path | None = None,
    model: str | None = None,
    prompt_template: Path | None = None,
    temperature: str | None = None,
) -> dict[str, Any]:
    registry = load_registry(registry_path)
    corpus = find_corpus(registry, corpus_id)
    materialization = load_materialization(materialized_corpus, corpus_id)
    root = repo_root()
    fingerprints = {
        "corpus": corpus_fingerprint(corpus, materialization),
        "process": process_fingerprint(root, load_analysis_flags(analysis_flags_path)),
        "interpretation": interpretation_fingerprint(
            metrics_path=metrics_path,
            model=model,
            prompt_template=prompt_template,
            temperature=temperature,
        ),
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "corpus_id": corpus_id,
        "fingerprints": fingerprints,
    }


def main() -> int:
    args = parse_args()
    data = build_fingerprints(
        corpus_id=args.corpus_id,
        registry_path=args.registry,
        materialized_corpus=args.materialized_corpus,
        metrics_path=args.metrics,
        analysis_flags_path=args.analysis_flags,
        model=args.model,
        prompt_template=args.prompt_template,
        temperature=args.temperature,
    )
    write_json(args.output, data)
    print(json.dumps({"status": "ok", "corpus_id": args.corpus_id, "output": str(args.output)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
