#!/usr/bin/env python3
"""Build a pinned public Hugging Face cohort for HSMM replication.

This materializes public dataset snapshots under experiments/, records object
hashes, normalizes supported files to middens Session[] JSON, and writes legacy
JSONL symlink directories for scripts that still consume raw Claude/Pi/Codex
logs. It intentionally keeps raw transcripts and normalized transcript JSON out
of git; the repository .gitignore excludes experiments/.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

try:
    import pandas as pd
    from huggingface_hub import snapshot_download
except ImportError as exc:  # pragma: no cover - environment guard
    print(
        "Missing Python dependency. Expected huggingface_hub and pandas/pyarrow; "
        "install them before running this script. Example: "
        "python3 -m pip install huggingface_hub pandas pyarrow",
        file=sys.stderr,
    )
    raise SystemExit(2) from exc


@dataclass(frozen=True)
class DatasetSpec:
    repo: str
    revision: str
    purpose: str
    include_in_baseline: bool
    include_in_inference: bool
    notes: str


DATASETS: tuple[DatasetSpec, ...] = (
    DatasetSpec(
        repo="cfahlgren1/agent-sessions-list",
        revision="10d6d295cb79a11194cfd93f0e9752b76889fbba",
        purpose="small mixed-source sanity cohort: Claude, Codex, Pi",
        include_in_baseline=True,
        include_in_inference=True,
        notes="Primary small mixed-source cohort supplied by user.",
    ),
    DatasetSpec(
        repo="badlogicgames/pi-mono",
        revision="dac2a1d3ba12dda597b973a791a77618ccb5f413",
        purpose="main public Pi cohort",
        include_in_baseline=True,
        include_in_inference=True,
        notes="Primary Pi cohort published with pi-share-hf metadata.",
    ),
    DatasetSpec(
        repo="armand0e/badlogicgames-pi-mono-opus-filtered",
        revision="32e67a8d04febcb38a2d28798a6d80fb41481a38",
        purpose="filtered Pi cohort / cross-check",
        include_in_baseline=False,
        include_in_inference=False,
        notes="Derivative of badlogicgames/pi-mono; hashed and parsed as cross-check only to avoid duplicate inference rows.",
    ),
    DatasetSpec(
        repo="archit11/claude-code-traces",
        revision="416248040ba2c706c475bba238782c3e334fd4d8",
        purpose="Claude Code trace cohort; Parquet request/response rows",
        include_in_baseline=False,
        include_in_inference=False,
        notes="Parquet rows are API request/response traces, not durable session logs; normalized separately and excluded from HSMM inference.",
    ),
)

DATA_ALLOW_PATTERNS = ("*.jsonl", "*.json", "*.parquet", "README.md", ".gitattributes")
TIMESTAMP_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?")
SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("openai_api_key", re.compile(r"sk-[A-Za-z0-9_-]{20,}")),
    ("anthropic_api_key", re.compile(r"sk-ant-[A-Za-z0-9_-]{20,}")),
    ("aws_access_key_id", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("github_token", re.compile(r"gh[pousr]_[A-Za-z0-9_]{20,}")),
    ("private_key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("experiments/hsmm-public-hf-fixed"),
        help="Gitignored output directory for snapshots, manifests, and normalized cohorts.",
    )
    parser.add_argument(
        "--middens-bin",
        type=Path,
        default=Path("middens/target/release/middens"),
        help="middens binary used to parse JSONL session logs.",
    )
    parser.add_argument(
        "--only",
        action="append",
        choices=[spec.repo for spec in DATASETS],
        help="Restrict to one dataset repo. Repeatable. Default: all seed datasets.",
    )
    parser.add_argument(
        "--parse-timeout-seconds",
        type=int,
        default=120,
        help="Per-file middens parse timeout for JSONL files.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing normalized/legacy outputs and manifest files. Raw HF cache is reused.",
    )
    return parser.parse_args()


def fail(message: str, exit_code: int = 2) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(exit_code)


def ensure_safe_output_dir(path: Path, force: bool) -> None:
    path = path.resolve()
    cwd = Path.cwd().resolve()
    if path == cwd or path == cwd.parent:
        fail(f"Refusing unsafe output directory: {path}. Use a dedicated experiments/... child directory.")
    if path.exists() and not force:
        stale = [
            path / "manifest.jsonl",
            path / "summary.json",
            path / "normalized",
            path / "legacy",
        ]
        if any(p.exists() for p in stale):
            fail(
                f"{path} already contains cohort outputs. Pass --force to overwrite generated manifest/normalized/legacy files."
            )
    path.mkdir(parents=True, exist_ok=True)


def reset_generated_outputs(output_dir: Path) -> None:
    for child in ("manifest.jsonl", "summary.json"):
        path = output_dir / child
        if path.exists():
            path.unlink()
    for child in ("normalized", "legacy"):
        path = output_dir / child
        if path.exists():
            shutil.rmtree(path)
    (output_dir / "normalized").mkdir(parents=True, exist_ok=True)
    (output_dir / "legacy" / "public_hf_baseline_fixed").mkdir(parents=True, exist_ok=True)
    (output_dir / "legacy" / "public_hf_boucle_excluded_fixed").mkdir(parents=True, exist_ok=True)
    (output_dir / "legacy" / "crosscheck_filtered_pi").mkdir(parents=True, exist_ok=True)


def repo_slug(repo: str) -> str:
    return repo.replace("/", "__")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def storage_format(path: Path) -> str:
    suffix = path.suffix.lower().lstrip(".")
    if suffix in {"jsonl", "json", "parquet", "md"}:
        return "markdown" if suffix == "md" else suffix
    if path.name == ".gitattributes":
        return "gitattrs"
    return suffix or "other"


def load_json_lines(path: Path, max_lines: int | None = None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8", errors="replace") as f:
        for idx, line in enumerate(f):
            if max_lines is not None and idx >= max_lines:
                break
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict):
                rows.append(obj)
    return rows


def find_first_timestamp_in_text(text: str) -> str | None:
    match = TIMESTAMP_RE.search(text)
    return match.group(0) if match else None


def normalize_timestamp(ts: Any) -> str | None:
    if ts is None:
        return None
    if isinstance(ts, (int, float)):
        # Milliseconds since epoch is common in raw agent traces.
        value = float(ts) / 1000.0 if ts > 10_000_000_000 else float(ts)
        try:
            return dt.datetime.fromtimestamp(value, tz=dt.timezone.utc).isoformat().replace("+00:00", "Z")
        except (OSError, OverflowError, ValueError):
            return None
    if isinstance(ts, str):
        return ts
    return None


def iso_week(timestamp: str | None) -> str | None:
    if not timestamp:
        return None
    value = timestamp.replace("Z", "+00:00")
    try:
        parsed = dt.datetime.fromisoformat(value)
    except ValueError:
        return None
    year, week, _ = parsed.isocalendar()
    return f"{year}-W{week:02d}"


def scan_raw_jsonl(path: Path) -> dict[str, Any]:
    rows = load_json_lines(path)
    first_ts: str | None = None
    queue_operation = False
    boucle_marker = False
    raw_tool_use_count = 0
    raw_user_messages = 0
    raw_assistant_messages = 0
    secret_hits: set[str] = set()

    for obj in rows:
        obj_type = obj.get("type")
        if obj_type == "queue-operation":
            queue_operation = True
        message = obj.get("message") if isinstance(obj.get("message"), dict) else {}
        role = message.get("role") or obj.get("role") or obj_type
        if role == "user" or obj_type == "user":
            raw_user_messages += 1
        if role == "assistant" or obj_type == "assistant":
            raw_assistant_messages += 1
        if first_ts is None:
            first_ts = normalize_timestamp(obj.get("timestamp") or message.get("timestamp"))
        serialized = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
        lowered = serialized.lower()
        if "boucle" in lowered or "autonomous agent running in a loop" in lowered or "<run_context>" in lowered:
            boucle_marker = True
        raw_tool_use_count += lowered.count('"type":"tool_use"')
        raw_tool_use_count += lowered.count('"type":"tooluse"')
        raw_tool_use_count += lowered.count('"type":"toolcall"')
        for name, pattern in SECRET_PATTERNS:
            if pattern.search(serialized):
                secret_hits.add(name)

    if first_ts is None:
        with path.open("r", encoding="utf-8", errors="replace") as f:
            first_ts = find_first_timestamp_in_text(f.read(64 * 1024))

    return {
        "first_timestamp": first_ts,
        "iso_week": iso_week(first_ts),
        "queue_operation": queue_operation,
        "boucle_marker": boucle_marker,
        "raw_tool_use_count": raw_tool_use_count,
        "raw_user_messages": raw_user_messages,
        "raw_assistant_messages": raw_assistant_messages,
        "secret_screening": {
            "scanner": "regex-lightweight-not-trufflehog",
            "status": "hits" if secret_hits else "no_hits",
            "hits": sorted(secret_hits),
        },
    }


def run_middens_parse(middens_bin: Path, path: Path, timeout_seconds: int) -> tuple[list[dict[str, Any]] | None, str | None]:
    try:
        completed = subprocess.run(
            [str(middens_bin), "parse", str(path), "--format", "json"],
            check=False,
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired:
        return None, f"middens parse timed out after {timeout_seconds}s"

    if completed.returncode != 0:
        stderr = completed.stderr.strip().splitlines()
        return None, stderr[-1] if stderr else f"middens parse exited {completed.returncode}"

    try:
        parsed = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        return None, f"middens parse emitted invalid JSON: {exc}"
    if not isinstance(parsed, list):
        return None, "middens parse emitted non-list JSON"
    return parsed, None


def session_metrics(sessions: list[dict[str, Any]]) -> dict[str, Any]:
    assistant_turns = 0
    user_turns = 0
    tool_calls = 0
    corrections = 0
    thinking_visibility: set[str] = set()
    session_types: set[str] = set()
    source_tools: set[str] = set()
    first_ts: str | None = None

    for session in sessions:
        source_tools.add(str(session.get("source_tool", "Unknown")))
        session_types.add(str(session.get("session_type", "Unknown")))
        thinking_visibility.add(str(session.get("thinking_visibility", "Unknown")))
        for message in session.get("messages", []):
            role = message.get("role")
            if role == "Assistant":
                assistant_turns += 1
            elif role == "User":
                user_turns += 1
            tool_calls += len(message.get("tool_calls") or [])
            if message.get("classification") == "HumanCorrection":
                corrections += 1
            if first_ts is None:
                first_ts = normalize_timestamp(message.get("timestamp"))

    return {
        "session_count": len(sessions),
        "assistant_turns": assistant_turns,
        "user_turns": user_turns,
        "tool_calls": tool_calls,
        "corrections": corrections,
        "zero_tool_session": bool(sessions) and tool_calls == 0,
        "source_tool": ",".join(sorted(source_tools)) if source_tools else None,
        "session_types": sorted(session_types),
        "thinking_visibility": sorted(thinking_visibility),
        "first_timestamp": first_ts,
        "iso_week": iso_week(first_ts),
    }


def content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text", "")))
            elif isinstance(block, str):
                parts.append(block)
        return "\n".join(part for part in parts if part)
    return ""


def response_tool_calls(content: Any) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []
    if not isinstance(content, list):
        return calls
    for block in content:
        if isinstance(block, dict) and block.get("type") == "tool_use":
            calls.append(
                {
                    "id": str(block.get("id") or ""),
                    "name": str(block.get("name") or "unknown"),
                    "input": block.get("input") if isinstance(block.get("input"), dict) else {},
                }
            )
    return calls


def normalize_claude_trace_parquet(path: Path) -> tuple[list[dict[str, Any]], str | None]:
    try:
        df = pd.read_parquet(path)
    except Exception as exc:  # noqa: BLE001 - include schema/read failure in manifest
        return [], f"failed to read parquet: {exc}"

    required = {"timestamp", "request_id", "conversation_json"}
    if not required.issubset(set(df.columns)):
        return [], f"unsupported parquet schema: expected columns {sorted(required)}, got {list(df.columns)}"

    sessions: list[dict[str, Any]] = []
    for idx, row in df.iterrows():
        try:
            convo = json.loads(row["conversation_json"])
        except Exception as exc:  # noqa: BLE001
            return [], f"row {idx} conversation_json is not valid JSON: {exc}"
        request = convo.get("request") if isinstance(convo.get("request"), dict) else {}
        response = convo.get("response") if isinstance(convo.get("response"), dict) else {}
        messages: list[dict[str, Any]] = []
        req_ts = normalize_timestamp(request.get("timestamp") or row.get("timestamp"))
        for req_msg in request.get("messages", []):
            if not isinstance(req_msg, dict):
                continue
            role = "Assistant" if req_msg.get("role") == "assistant" else "User" if req_msg.get("role") == "user" else "System"
            messages.append(
                {
                    "role": role,
                    "timestamp": req_ts,
                    "text": content_to_text(req_msg.get("content")),
                    "thinking": None,
                    "reasoning_summary": None,
                    "reasoning_observability": "Absent",
                    "tool_calls": response_tool_calls(req_msg.get("content")),
                    "tool_results": [],
                    "classification": "Unclassified",
                    "raw_content": [],
                }
            )
        resp_ts = normalize_timestamp(convo.get("timestamp") or row.get("timestamp"))
        messages.append(
            {
                "role": "Assistant",
                "timestamp": resp_ts,
                "text": content_to_text(response.get("content")),
                "thinking": None,
                "reasoning_summary": None,
                "reasoning_observability": "Absent",
                "tool_calls": response_tool_calls(response.get("content")),
                "tool_results": [],
                "classification": "Unclassified",
                "raw_content": [],
            }
        )
        model = request.get("model") or response.get("model")
        sessions.append(
            {
                "id": str(row.get("request_id") or request.get("request_id") or idx),
                "source_path": str(path),
                "source_tool": "ClaudeCode",
                "session_type": "Unknown",
                "messages": messages,
                "metadata": {
                    "version": None,
                    "cwd": None,
                    "git_branch": None,
                    "model": model,
                    "project": None,
                    "permission_mode": None,
                    "extra": {"normalizer": "claude_trace_parquet_request_response_row"},
                },
                "environment": {
                    "tool_version": None,
                    "model_id": model,
                    "permission_mode": None,
                    "config_hash": None,
                    "mcp_servers": [],
                    "plugins": [],
                    "hooks": [],
                },
                "thinking_visibility": "Redacted",
                "reasoning_observability": "Absent",
            }
        )
    return sessions, None


def safe_link(src: Path, dst_dir: Path) -> None:
    dst = dst_dir / src.name
    counter = 1
    while dst.exists() or dst.is_symlink():
        dst = dst_dir / f"{src.stem}-{counter}{src.suffix}"
        counter += 1
    rel = os.path.relpath(src.resolve(), dst_dir.resolve())
    os.symlink(rel, dst)


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(value, f, indent=2, sort_keys=True)
        f.write("\n")


def iter_data_files(snapshot_dir: Path) -> Iterable[Path]:
    for path in sorted(snapshot_dir.rglob("*")):
        if path.is_file() and ".cache" not in path.parts:
            yield path


def is_dataset_metadata_object(rel_path: str) -> bool:
    """Return true for dataset-side indexes/manifests, not transcript logs."""
    basename = Path(rel_path).name
    return basename in {"README.md", ".gitattributes", "manifest.jsonl", "manifest.json"} or rel_path.startswith("indexes/")


def main() -> int:
    args = parse_args()
    selected = [spec for spec in DATASETS if args.only is None or spec.repo in set(args.only)]
    if not selected:
        fail("No datasets selected. Use --only with one of the configured dataset repos.")
    middens_bin = args.middens_bin
    if not middens_bin.exists():
        fail(f"middens binary not found at {middens_bin}. Build it with: cd middens && cargo build --release")
    if args.parse_timeout_seconds <= 0:
        fail("--parse-timeout-seconds must be positive, e.g. --parse-timeout-seconds 120")

    output_dir = args.output_dir
    ensure_safe_output_dir(output_dir, args.force)
    reset_generated_outputs(output_dir)

    raw_root = output_dir / "raw"
    cache_dir = output_dir / "hf-cache"
    raw_root.mkdir(parents=True, exist_ok=True)
    cache_dir.mkdir(parents=True, exist_ok=True)

    baseline_sessions: list[dict[str, Any]] = []
    boucle_excluded_sessions: list[dict[str, Any]] = []
    crosscheck_sessions: list[dict[str, Any]] = []
    parquet_trace_sessions: list[dict[str, Any]] = []
    manifest_rows: list[dict[str, Any]] = []
    seen_baseline_sha: set[str] = set()

    for spec in selected:
        print(f"Downloading/pinning {spec.repo}@{spec.revision} ...", flush=True)
        snapshot = Path(
            snapshot_download(
                repo_id=spec.repo,
                repo_type="dataset",
                revision=spec.revision,
                allow_patterns=list(DATA_ALLOW_PATTERNS),
                cache_dir=cache_dir,
            )
        )
        repo_raw_dir = raw_root / repo_slug(spec.repo)
        if repo_raw_dir.exists():
            shutil.rmtree(repo_raw_dir)
        shutil.copytree(snapshot, repo_raw_dir, symlinks=False)

        for path in iter_data_files(repo_raw_dir):
            rel = path.relative_to(repo_raw_dir).as_posix()
            fmt = storage_format(path)
            digest = sha256_file(path)
            size = path.stat().st_size
            duplicate_of_sha = digest if digest in seen_baseline_sha else None
            raw_scan: dict[str, Any] = {}
            parsed_sessions: list[dict[str, Any]] = []
            parser_status = "metadata_excluded"
            parser_error: str | None = None
            normalizer = None

            if is_dataset_metadata_object(rel):
                parser_status = "metadata_excluded"
            elif fmt == "jsonl":
                raw_scan = scan_raw_jsonl(path)
                parsed, parser_error = run_middens_parse(middens_bin, path, args.parse_timeout_seconds)
                if parsed is None:
                    parser_status = "parse_error"
                else:
                    parsed_sessions = parsed
                    parser_status = "parseable"
            elif fmt == "parquet":
                parsed_sessions, parser_error = normalize_claude_trace_parquet(path)
                normalizer = "claude_trace_parquet_request_response_row"
                parser_status = "normalized_trace_rows" if parser_error is None else "unsupported_schema"
            elif fmt == "json":
                parser_status = "unsupported_schema"
                parser_error = "JSON dataset objects are not yet normalized; expected JSONL session logs or known Parquet trace schema."

            metrics = session_metrics(parsed_sessions) if parsed_sessions else {}
            first_ts = metrics.get("first_timestamp") or raw_scan.get("first_timestamp")
            week = iso_week(first_ts) or metrics.get("iso_week") or raw_scan.get("iso_week")
            contamination = {
                "queue_operation": bool(raw_scan.get("queue_operation")),
                "boucle_marker": bool(raw_scan.get("boucle_marker")),
                "zero_tool_session": bool(metrics.get("zero_tool_session")) if parsed_sessions else None,
                "w10_w12": week in {"2026-W10", "2026-W11", "2026-W12"},
            }
            boucle_excluded = not (
                contamination["queue_operation"]
                or contamination["boucle_marker"]
                or (contamination["w10_w12"] and contamination["zero_tool_session"] is True)
            )
            baseline_eligible = (
                spec.include_in_baseline
                and spec.include_in_inference
                and parser_status == "parseable"
                and fmt == "jsonl"
                and bool(parsed_sessions)
                and duplicate_of_sha is None
            )
            boucle_eligible = baseline_eligible and boucle_excluded
            crosscheck_eligible = spec.repo == "armand0e/badlogicgames-pi-mono-opus-filtered" and parser_status == "parseable"

            if baseline_eligible:
                baseline_sessions.extend(parsed_sessions)
                seen_baseline_sha.add(digest)
                safe_link(path, output_dir / "legacy" / "public_hf_baseline_fixed")
            if boucle_eligible:
                boucle_excluded_sessions.extend(parsed_sessions)
                safe_link(path, output_dir / "legacy" / "public_hf_boucle_excluded_fixed")
            if crosscheck_eligible:
                crosscheck_sessions.extend(parsed_sessions)
                safe_link(path, output_dir / "legacy" / "crosscheck_filtered_pi")
            if fmt == "parquet" and parsed_sessions:
                parquet_trace_sessions.extend(parsed_sessions)

            row = {
                "dataset_repo": spec.repo,
                "dataset_revision": spec.revision,
                "dataset_purpose": spec.purpose,
                "dataset_notes": spec.notes,
                "repo_path": rel,
                "local_path": str(path),
                "storage_format": fmt,
                "sha256": digest,
                "duplicate_of_sha": duplicate_of_sha,
                "size_bytes": size,
                "source_tool": metrics.get("source_tool"),
                "first_timestamp": first_ts,
                "iso_week": week,
                "parser_status": parser_status,
                "parser_error": parser_error,
                "normalizer": normalizer,
                "session_count": metrics.get("session_count", 0),
                "assistant_turns": metrics.get("assistant_turns", 0),
                "user_turns": metrics.get("user_turns", 0),
                "tool_calls": metrics.get("tool_calls", 0),
                "corrections": metrics.get("corrections", 0),
                "session_types": metrics.get("session_types", []),
                "thinking_visibility": metrics.get("thinking_visibility", []),
                "contamination_flags": contamination,
                "secret_screening": raw_scan.get(
                    "secret_screening",
                    {"scanner": "not_applicable", "status": "not_scanned", "hits": []},
                ),
                "inclusion_flags": {
                    "public_hf_baseline_fixed": baseline_eligible,
                    "public_hf_boucle_excluded_fixed": boucle_eligible,
                    "crosscheck_filtered_pi": crosscheck_eligible,
                    "parquet_trace_normalized_not_inference": fmt == "parquet" and bool(parsed_sessions),
                },
            }
            manifest_rows.append(row)

    manifest_path = output_dir / "manifest.jsonl"
    with manifest_path.open("w", encoding="utf-8") as f:
        for row in manifest_rows:
            f.write(json.dumps(row, sort_keys=True) + "\n")

    normalized_dir = output_dir / "normalized"
    write_json(normalized_dir / "public_hf_baseline_fixed.sessions.json", baseline_sessions)
    write_json(normalized_dir / "public_hf_boucle_excluded_fixed.sessions.json", boucle_excluded_sessions)
    write_json(normalized_dir / "crosscheck_filtered_pi.sessions.json", crosscheck_sessions)
    write_json(normalized_dir / "parquet_trace_rows_not_inference.sessions.json", parquet_trace_sessions)

    summary = {
        "built_at": dt.datetime.now(tz=dt.timezone.utc).isoformat().replace("+00:00", "Z"),
        "datasets": [spec.__dict__ for spec in selected],
        "manifest_rows": len(manifest_rows),
        "objects_by_status": dict(sorted(Counter(row["parser_status"] for row in manifest_rows).items())),
        "objects_by_format": dict(sorted(Counter(row["storage_format"] for row in manifest_rows).items())),
        "cohorts": {
            "public_hf_baseline_fixed": {
                "sessions": len(baseline_sessions),
                "legacy_jsonl_files": len(list((output_dir / "legacy" / "public_hf_baseline_fixed").glob("*.jsonl"))),
            },
            "public_hf_boucle_excluded_fixed": {
                "sessions": len(boucle_excluded_sessions),
                "legacy_jsonl_files": len(list((output_dir / "legacy" / "public_hf_boucle_excluded_fixed").glob("*.jsonl"))),
            },
            "crosscheck_filtered_pi": {
                "sessions": len(crosscheck_sessions),
                "legacy_jsonl_files": len(list((output_dir / "legacy" / "crosscheck_filtered_pi").glob("*.jsonl"))),
            },
            "parquet_trace_rows_not_inference": {"sessions": len(parquet_trace_sessions)},
        },
        "privacy_note": "Public datasets are not assumed privacy-safe. Raw transcripts and normalized Session[] files stay under gitignored experiments/. secret_screening is lightweight regex provenance, not TruffleHog equivalence.",
    }
    write_json(output_dir / "summary.json", summary)

    print(json.dumps(summary, indent=2, sort_keys=True))
    print(f"\nWrote manifest: {manifest_path}")
    print(f"Wrote normalized sessions: {normalized_dir}")
    return 0


# Imported late so dependency failures above can emit a clearer message before
# Python evaluates all imports in constrained environments.
from collections import Counter  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
