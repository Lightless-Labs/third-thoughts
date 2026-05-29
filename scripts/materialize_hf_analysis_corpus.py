#!/usr/bin/env python3
"""Materialize one pinned public HF corpus for `middens analyze`.

The script reads docs/corpora/public-hf-analysis-corpora.json, downloads the
selected pinned Hugging Face dataset revision, materializes supported corpus
formats into an analyze-compatible JSONL directory, and writes a small manifest.
It fails early if the registry entry is ambiguous, disabled, or uses an
unsupported storage format/schema.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
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
SUPPORTED_STORAGE_FORMATS = {"jsonl", "parquet_trace_rows"}
PARQUET_TRACE_REQUIRED_COLUMNS = {"timestamp", "request_id", "conversation_json"}
PARQUET_TRACE_NORMALIZER = "claude_trace_parquet_request_response_row_v1"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--registry",
        type=Path,
        default=Path("docs/corpora/public-hf-analysis-corpora.json"),
    )
    parser.add_argument("--corpus", required=True, help="Corpus id from the registry.")
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Output directory for analyze-compatible JSONL session logs.",
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=Path(".tmp/hf-cache"),
        help="HF snapshot cache directory.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite output directory if it already exists.",
    )
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
            f"Expected analysis_enabled=true and storage_format in {sorted(SUPPORTED_STORAGE_FORMATS)}."
        )
    storage_format = corpus.get("storage_format")
    if storage_format not in SUPPORTED_STORAGE_FORMATS:
        fail(
            f"corpus {corpus_id!r} has storage_format={storage_format!r}; "
            f"supported formats are {sorted(SUPPORTED_STORAGE_FORMATS)}. "
            "Example registry entry: storage_format=\"jsonl\" or storage_format=\"parquet_trace_rows\"."
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


def normalize_timestamp(ts: Any) -> str | None:
    if ts is None:
        return None
    if isinstance(ts, (int, float)):
        value = float(ts) / 1000.0 if ts > 10_000_000_000 else float(ts)
        try:
            return (
            dt.datetime.fromtimestamp(value, tz=dt.timezone.utc)
            .isoformat()
            .replace("+00:00", "Z")
        )
        except (OSError, OverflowError, ValueError):
            return None
    if isinstance(ts, str):
        return ts
    return None


def safe_filename(value: Any, fallback: str) -> str:
    raw = str(value).strip() if value is not None else ""
    if not raw or raw == "nan":
        raw = fallback
    safe = re.sub(r"[^A-Za-z0-9._-]+", "-", raw).strip(".-")
    return safe[:120] or fallback


def json_compatible(value: Any) -> Any:
    """Convert Arrow/Pandas-ish scalar containers into JSON-serializable values."""

    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, list):
        return [json_compatible(item) for item in value]
    if isinstance(value, tuple):
        return [json_compatible(item) for item in value]
    if isinstance(value, dict):
        return {str(key): json_compatible(item) for key, item in value.items()}
    return str(value)


def claude_trace_entry(
    *,
    entry_type: str,
    session_id: str,
    timestamp: str | None,
    role: str,
    content: Any,
    model: str | None,
    source_parquet: str,
    row_index: int,
) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "type": entry_type,
        "sessionId": session_id,
        "version": PARQUET_TRACE_NORMALIZER,
        "message": {"role": role, "content": json_compatible(content)},
        "parquetTraceSource": source_parquet,
        "parquetTraceRow": row_index,
    }
    if timestamp:
        entry["timestamp"] = timestamp
    if model and role == "assistant":
        entry["message"]["model"] = model
    return entry


def materialize_parquet_trace_rows(snapshot: Path, output: Path) -> tuple[int, list[dict[str, Any]]]:
    try:
        import pyarrow.parquet as pq
    except ImportError as exc:  # pragma: no cover - depends on local Python env
        fail(
            "Missing pyarrow for storage_format='parquet_trace_rows'. "
            "Install with: python3 -m pip install pyarrow"
        )
        raise AssertionError("unreachable") from exc

    parquet_files = sorted(path for path in snapshot.rglob("*.parquet") if path.is_file())
    if not parquet_files:
        fail("Parquet trace corpus contained no .parquet files at the pinned revision")

    sessions_dir = output / "sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)
    manifest_rows: list[dict[str, Any]] = []
    generated = 0

    for parquet_path in parquet_files:
        rel = parquet_path.relative_to(snapshot)
        try:
            parquet = pq.ParquetFile(parquet_path)
        except Exception as exc:  # noqa: BLE001 - fail with path/schema context
            fail(f"failed to read Parquet object {rel}: {exc}")

        columns = set(parquet.schema_arrow.names)
        missing = sorted(PARQUET_TRACE_REQUIRED_COLUMNS - columns)
        if missing:
            fail(
                f"unsupported Parquet trace schema in {rel}: missing columns {missing}; "
                f"expected at least {sorted(PARQUET_TRACE_REQUIRED_COLUMNS)}. "
                "Example supported schema: timestamp:string, request_id:string, conversation_json:string. "
                f"Actual columns: {parquet.schema_arrow.names}"
            )

        source_sha = sha256_file(parquet_path)
        row_offset = 0
        for batch in parquet.iter_batches(
            batch_size=256,
            columns=sorted(PARQUET_TRACE_REQUIRED_COLUMNS),
        ):
            for batch_row_index, row in enumerate(batch.to_pylist()):
                row_index = row_offset + batch_row_index
                try:
                    conversation = json.loads(row["conversation_json"])
                except Exception as exc:  # noqa: BLE001 - include row context
                    fail(f"row {row_index} in {rel} has non-JSON conversation_json: {exc}")
                if not isinstance(conversation, dict):
                    fail(f"row {row_index} in {rel} conversation_json must decode to an object")

                request = conversation.get("request") if isinstance(conversation.get("request"), dict) else {}
                response = conversation.get("response") if isinstance(conversation.get("response"), dict) else {}
                request_messages = request.get("messages") if isinstance(request.get("messages"), list) else []
                session_id = str(row.get("request_id") or request.get("request_id") or f"row-{row_index}")
                model = request.get("model") or response.get("model")
                request_ts = normalize_timestamp(request.get("timestamp") or row.get("timestamp"))
                response_ts = normalize_timestamp(
                    conversation.get("timestamp")
                    or response.get("timestamp")
                    or row.get("timestamp")
                )

                entries: list[dict[str, Any]] = []
                for request_message in request_messages:
                    if not isinstance(request_message, dict):
                        continue
                    role = request_message.get("role")
                    if role not in {"user", "assistant"}:
                        continue
                    entries.append(
                        claude_trace_entry(
                            entry_type=role,
                            session_id=session_id,
                            timestamp=request_ts,
                            role=role,
                            content=request_message.get("content", ""),
                            model=model if role == "assistant" else None,
                            source_parquet=rel.as_posix(),
                            row_index=row_index,
                        )
                    )

                entries.append(
                    claude_trace_entry(
                        entry_type="assistant",
                        session_id=session_id,
                        timestamp=response_ts,
                        role="assistant",
                        content=response.get("content", ""),
                        model=model,
                        source_parquet=rel.as_posix(),
                        row_index=row_index,
                    )
                )

                name = safe_filename(session_id, f"row-{row_index}")
                destination = sessions_dir / f"{name}.jsonl"
                if destination.exists():
                    destination = sessions_dir / f"{name}-{row_index}.jsonl"
                destination.write_text(
                    "\n".join(json.dumps(entry, ensure_ascii=False) for entry in entries) + "\n",
                    encoding="utf-8",
                )
                generated += 1
                manifest_rows.append(
                    {
                        "repo_path": rel.as_posix(),
                        "generated_path": destination.relative_to(output).as_posix(),
                        "source_sha256": source_sha,
                        "source_size_bytes": parquet_path.stat().st_size,
                        "row_index": row_index,
                        "request_id": session_id,
                        "normalizer": PARQUET_TRACE_NORMALIZER,
                    }
                )
            row_offset += batch.num_rows

    return generated, manifest_rows


def materialize_jsonl(snapshot: Path, output: Path) -> tuple[int, list[dict[str, Any]]]:
    manifest_rows: list[dict[str, Any]] = []
    copied = 0
    for src in sorted(
        path for path in snapshot.rglob("*.jsonl") if path.is_file() and is_session_jsonl(path)
    ):
        rel = src.relative_to(snapshot)
        dst = output / rel
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
    return copied, manifest_rows


def main() -> int:
    args = parse_args()
    registry = load_registry(args.registry)
    corpus = select_corpus(registry, args.corpus)
    reset_output(args.output, args.force)
    args.cache_dir.mkdir(parents=True, exist_ok=True)

    storage_format = corpus["storage_format"]
    allow_patterns = (
        ["*.jsonl", "README.md", ".gitattributes"]
        if storage_format == "jsonl"
        else ["*.parquet", "README.md", ".gitattributes"]
    )
    snapshot = Path(
        snapshot_download(
            repo_id=corpus["dataset_repo"],
            repo_type="dataset",
            revision=corpus["dataset_revision"],
            allow_patterns=allow_patterns,
            cache_dir=args.cache_dir,
        )
    )

    if storage_format == "jsonl":
        materialized_files, manifest_rows = materialize_jsonl(snapshot, args.output)
    elif storage_format == "parquet_trace_rows":
        materialized_files, manifest_rows = materialize_parquet_trace_rows(snapshot, args.output)
    else:  # select_corpus already rejects this; keep mypy/linters honest.
        fail(f"unsupported storage_format={storage_format!r}")

    min_files = int(corpus.get("expected_min_jsonl_files", 1))
    if materialized_files < min_files:
        fail(
            f"corpus {args.corpus!r} materialized only {materialized_files} JSONL file(s), "
            f"below expected_min_jsonl_files={min_files}. Check the pinned revision or registry entry."
        )

    manifest = {
        "corpus_id": corpus["id"],
        "dataset_repo": corpus["dataset_repo"],
        "dataset_revision": corpus["dataset_revision"],
        "description": corpus.get("description"),
        "storage_format": storage_format,
        "normalizer": PARQUET_TRACE_NORMALIZER if storage_format == "parquet_trace_rows" else None,
        "jsonl_files": materialized_files,
        "objects": manifest_rows,
    }
    (args.output / "_hf_corpus_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    print(
        json.dumps(
            {
                k: manifest[k]
                for k in (
                    "corpus_id",
                    "dataset_repo",
                    "dataset_revision",
                    "storage_format",
                    "jsonl_files",
                )
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
