#!/usr/bin/env python3
"""Run per-dataset HSMM summaries for the public HF datasets shared with us.

This deliberately does *not* mix candidate datasets into one headline. Each
public dataset is pinned, hashed at object level, normalized independently, and
run through the current middens HSMM technique as its own cohort.

Raw/cache/normalized artifacts are written under gitignored experiments/.
The committed-facing output should be the aggregate markdown/JSON summaries only.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import shutil
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    from huggingface_hub import HfApi, snapshot_download
except ImportError as exc:  # pragma: no cover
    print(
        "Missing huggingface_hub. Install with: python3 -m pip install huggingface_hub",
        file=sys.stderr,
    )
    raise SystemExit(2) from exc

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from build_public_hf_hsmm_cohort import (  # noqa: E402
    DATA_ALLOW_PATTERNS,
    is_dataset_metadata_object,
    normalize_claude_trace_parquet,
    repo_slug,
    run_middens_parse,
    scan_raw_jsonl,
    session_metrics,
    sha256_file,
    storage_format,
    write_json,
)


@dataclass(frozen=True)
class Candidate:
    repo: str
    revision: str
    source: str
    note: str = ""


CANDIDATES: tuple[Candidate, ...] = (
    # User-supplied seed datasets.
    Candidate("cfahlgren1/agent-sessions-list", "10d6d295cb79a11194cfd93f0e9752b76889fbba", "seed", "mixed Claude/Codex/Pi sanity cohort"),
    Candidate("badlogicgames/pi-mono", "dac2a1d3ba12dda597b973a791a77618ccb5f413", "seed/pi-share-hf", "main public Pi cohort"),
    Candidate("armand0e/badlogicgames-pi-mono-opus-filtered", "32e67a8d04febcb38a2d28798a6d80fb41481a38", "seed", "filtered derivative/cross-check"),
    Candidate("archit11/claude-code-traces", "416248040ba2c706c475bba238782c3e334fd4d8", "seed/claude-code-search", "Parquet request/response traces"),
    # HF `other=pi-share-hf` candidates observed 2026-05-23.
    Candidate("LarsEckart/approvaltests-java-sessions", "8713a8d6eff46c759be66f1d37c306f30c8cdaa6", "other=pi-share-hf"),
    Candidate("thomasmustier/pi-for-excel-sessions", "1b7218d2acf621e52bb5208435b1f80154342e3f", "other=pi-share-hf"),
    Candidate("thomasmustier/pi-nes-sessions", "2189a4493f6760224f220cea1b5b2a965a528e5f", "other=pi-share-hf"),
    Candidate("JohnBeanerson/pi-mono-test", "3b386145073c5fb7974cd604559719059d5411a3", "other=pi-share-hf", "test-looking dataset; analyzed separately only"),
    Candidate("karkowww/pi-mono", "0fd28f883a880ad2b67084c5ccc36bcd53fb2bc2", "other=pi-share-hf"),
    Candidate("Prayagmatic/agent-traces", "91106233747240a83190fc1c4135be9d4d87c386", "other=pi-share-hf"),
    Candidate("julien-c/pi-sessions", "700416886204bcdbca133373daed3d2504c853cf", "other=pi-share-hf"),
    Candidate("invincible-jha/pi-mono", "d3438c8c224205dd3ac45cce08ceb174fbfe770b", "other=pi-share-hf"),
    Candidate("aaaaliou/pi-mono", "61eee21d662f8736ace59507fc30555e1bff5c6e", "other=pi-share-hf"),
    Candidate("aaaaliou/pi-playdate", "ac113723b9642274c1f4b8f0905438f090f14dda", "other=pi-share-hf"),
    Candidate("aaaaliou/playdate-games", "19d22b5be8a48d42e30bd44bca58d62c240f5171", "other=pi-share-hf"),
    Candidate("aaaaliou/pi-synthetic", "f962b816f0c1637ef23ffe11019fab0591ff1ad9", "other=pi-share-hf", "synthetic-looking dataset; analyzed separately only"),
    Candidate("assafvayner/pi-mono", "bf64b2a4fc16ce98cc76c842ce046b01b6c688c1", "other=pi-share-hf"),
    Candidate("kaofelix/video-scissors-sessions", "17a9da24e81fa15e6d0b271b77152c333d52d3ed", "other=pi-share-hf"),
    Candidate("aaaaliou/pi-sessions-viewer", "d13e1e9ba4a8b1310dd67c1d12b29d40c6705b5f", "other=pi-share-hf"),
    Candidate("thomasmustier/pi-mono-sessions", "b6e68ac0e8d9f53de96aa4a6f0ff630a53bb8cae", "other=pi-share-hf"),
    Candidate("thomasmustier/pi-extensions-sessions", "ae6f02c5fd581a49ac1e9bbedbb65c3300a985b7", "other=pi-share-hf"),
    Candidate("thomasmustier/economist-tui-sessions", "3ffcea7e16c44f83efd9fad42a4cdf73ce725f9f", "other=pi-share-hf"),
    Candidate("thomasmustier/clean-slides-sessions", "ccab758ba8f6ccc7bfa5ef6d628e531125a1e0a6", "other=pi-share-hf"),
    Candidate("deepflame-bot/pi-publish", "241968f75241fe8ecb29662e2ef0ceb7d1af4161", "other=pi-share-hf"),
    Candidate("Ev3lynx727/pi-cavelynx", "1478da03d0d8f2fa3fb3bc63f4fe4287e268fd12", "other=pi-share-hf"),
    Candidate("grfwings/pi-session-traces", "bdb8de4ea0affd5d1a1e4d69df2bebc473447602", "other=pi-share-hf"),
    Candidate("bhollmann/pi-mono", "9101a5388ff8234b05e9f7e934c4699ae407f603", "other=pi-share-hf"),
    # HF `search=claude code` candidates observed 2026-05-23.
    Candidate("armand0e/kimi-k2.6-claude-code-traces", "1f02263eb3c1d41f9d7b264baf56a09063a67963", "search=claude code", "Claude-Code-style JSONL traces"),
    Candidate("archit11/claude_code_traces_hs", "b47770a9ec552c82dddcf6b1d79acc5247c1e3d2", "search=claude code", "Parquet trace cohort"),
    Candidate("archit11/claude_code_traces_dirty", "fb7eaf68f1f2960101baa54b35d5369970ddde26", "search=claude code", "dirty Parquet trace cohort"),
    Candidate("nlile/misc-merged-claude-code-traces-v1", "ab456b000b13563156e84d75bfa4d20acccb4f88", "search=claude code", "large merged Parquet trace cohort"),
    Candidate("misterkerns/my-personal-claude-code-data", "e6aff5fa4941ef1cbfcbca7bf09ac04506d22691", "search=claude code", "public personal data; aggregate-only"),
    Candidate("REXX-NEW/my-personal-claude-code-data", "33780c77b955a844c9c1be2f00801def0d407c45", "search=claude code", "public personal data; aggregate-only"),
    Candidate("JohnBeanerson/claude-code-sessions-test", "3904ff701d06c18699ae167932c4cd02ce3647a0", "search=claude code", "test dataset; analyzed separately only"),
    Candidate("ultralazr/claude-code-traces", "afe3c108c148427625f7b2275791517f99f8115d", "search=claude code"),
    Candidate("gabegoodhart/traces.claude-code.mlx-lm-granitemoehybrid", "8717352ccbf29731901ed6f00282cb4ce64bffe0", "search=claude code", "model-specific trace derivative"),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("experiments/hsmm-public-hf-independent"))
    parser.add_argument("--middens-bin", type=Path, default=Path("middens/target/release/middens"))
    parser.add_argument("--hsmm-script", type=Path, default=Path("middens/python/techniques/hsmm.py"))
    parser.add_argument("--only", action="append", choices=[c.repo for c in CANDIDATES])
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--parse-timeout-seconds", type=int, default=120)
    parser.add_argument(
        "--max-parquet-mb",
        type=float,
        default=200.0,
        help="Mark larger Parquet objects unsupported for this non-streaming normalizer instead of risking a memory blow-up.",
    )
    return parser.parse_args()


def fail(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(2)


def reset_output(output_dir: Path, force: bool) -> None:
    if output_dir.exists() and not force:
        fail(f"{output_dir} already exists. Pass --force to overwrite generated independent summaries.")
    for child in ("manifest.jsonl", "summary.json", "summary.md", "normalized", "results"):
        path = output_dir / child
        if path.is_dir():
            shutil.rmtree(path)
        elif path.exists():
            path.unlink()
    (output_dir / "normalized").mkdir(parents=True, exist_ok=True)
    (output_dir / "results").mkdir(parents=True, exist_ok=True)
    (output_dir / "hf-cache").mkdir(parents=True, exist_ok=True)


def hf_size_bytes(candidate: Candidate) -> int | None:
    try:
        info = HfApi().dataset_info(candidate.repo, revision=candidate.revision, files_metadata=True)
    except Exception:
        return None
    total = 0
    for sibling in info.siblings:
        lfs = getattr(sibling, "lfs", None)
        total += sibling.size or (lfs.size if lfs else 0) or 0
    return total


def run_hsmm(hsmm_script: Path, sessions_path: Path, output_path: Path) -> tuple[dict[str, Any] | None, str | None]:
    completed = subprocess.run(
        [sys.executable, str(hsmm_script), str(sessions_path)],
        check=False,
        text=True,
        capture_output=True,
        timeout=900,
    )
    output_path.write_text(completed.stdout, encoding="utf-8")
    if completed.returncode != 0:
        return None, completed.stderr.strip() or f"hsmm exited {completed.returncode}"
    try:
        return json.loads(completed.stdout), None
    except json.JSONDecodeError as exc:
        return None, f"invalid HSMM JSON: {exc}; stderr={completed.stderr.strip()}"


def finding_value(result: dict[str, Any] | None, label: str) -> Any:
    if not result:
        return None
    for finding in result.get("findings", []):
        if finding.get("label") == label:
            return finding.get("value")
    return None


def markdown_summary(rows: list[dict[str, Any]]) -> str:
    lines = [
        "# Independent public HF HSMM dataset summaries",
        "",
        f"Built: {dt.datetime.now(tz=dt.timezone.utc).isoformat().replace('+00:00', 'Z')}",
        "",
        "Each dataset below is analyzed independently. These numbers are not mixed into a shared behavioural headline.",
        "Raw/cache/normalized artifacts stay under gitignored `experiments/hsmm-public-hf-independent/`.",
        "",
        "| Dataset | Source | Status | Sessions | Assistant turns | Corrections | Tool calls | HSMM lift | States | Notes |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for row in rows:
        lift = row.get("pre_correction_lift")
        lift_s = "" if lift is None else f"{float(lift):.2f}×"
        states = row.get("optimal_n_states")
        states_s = "" if states is None else str(states)
        note = row.get("note", "").replace("|", "\\|")
        if row.get("error"):
            note = (note + " " + row["error"]).strip().replace("|", "\\|")
        lines.append(
            "| {repo} | {source} | {status} | {sessions} | {assistant_turns} | {corrections} | {tool_calls} | {lift} | {states} | {note} |".format(
                repo=row["repo"],
                source=row["source"],
                status=row["status"],
                sessions=row.get("sessions", 0),
                assistant_turns=row.get("assistant_turns", 0),
                corrections=row.get("corrections", 0),
                tool_calls=row.get("tool_calls", 0),
                lift=lift_s,
                states=states_s,
                note=note,
            )
        )
    lines.extend([
        "",
        "## Caveats",
        "",
        "- `insufficient_data` is the HSMM technique refusing to fit rather than a finding of no effect.",
        "- Parquet trace datasets are API request/response traces where supported by the current normalizer; large Parquet objects may be marked unsupported until a streaming normalizer exists.",
        "- Public datasets are not treated as privacy-safe; no transcript snippets are included here.",
    ])
    return "\n".join(lines) + "\n"


def main() -> int:
    args = parse_args()
    if not args.middens_bin.exists():
        fail(f"middens binary not found at {args.middens_bin}; build with `cd middens && cargo build --release`")
    if not args.hsmm_script.exists():
        fail(f"HSMM script not found at {args.hsmm_script}")
    selected = [c for c in CANDIDATES if args.only is None or c.repo in set(args.only)]
    reset_output(args.output_dir, args.force)

    manifest_rows: list[dict[str, Any]] = []
    summary_rows: list[dict[str, Any]] = []

    for candidate in selected:
        print(f"\n== {candidate.repo}@{candidate.revision} ==", flush=True)
        repo_dir = args.output_dir / "normalized" / repo_slug(candidate.repo)
        repo_dir.mkdir(parents=True, exist_ok=True)
        repo_sessions: list[dict[str, Any]] = []
        object_statuses: Counter[str] = Counter()
        error: str | None = None
        total_size = hf_size_bytes(candidate)

        try:
            snapshot = Path(snapshot_download(
                repo_id=candidate.repo,
                repo_type="dataset",
                revision=candidate.revision,
                allow_patterns=list(DATA_ALLOW_PATTERNS) + ["*.metadata", "*.gitignore", "CACHEDIR.TAG"],
                cache_dir=args.output_dir / "hf-cache",
            ))
        except Exception as exc:  # noqa: BLE001
            error = f"snapshot_download failed: {exc}"
            summary_rows.append({
                "repo": candidate.repo,
                "source": candidate.source,
                "status": "download_error",
                "sessions": 0,
                "assistant_turns": 0,
                "corrections": 0,
                "tool_calls": 0,
                "note": candidate.note,
                "error": error,
                "size_bytes": total_size,
            })
            continue

        for path in sorted(p for p in snapshot.rglob("*") if p.is_file() and ".cache" not in p.parts):
            rel = path.relative_to(snapshot).as_posix()
            fmt = storage_format(path)
            digest = sha256_file(path)
            size = path.stat().st_size
            parsed_sessions: list[dict[str, Any]] = []
            raw_scan: dict[str, Any] = {}
            parser_status = "metadata_excluded" if is_dataset_metadata_object(rel) else "unsupported_schema"
            parser_error: str | None = None
            normalizer = None

            if not is_dataset_metadata_object(rel) and fmt == "jsonl":
                raw_scan = scan_raw_jsonl(path)
                parsed, parser_error = run_middens_parse(args.middens_bin, path, args.parse_timeout_seconds)
                if parsed is None:
                    parser_status = "parse_error"
                else:
                    parsed_sessions = parsed
                    parser_status = "parseable"
            elif not is_dataset_metadata_object(rel) and fmt == "parquet":
                if size > args.max_parquet_mb * 1_000_000:
                    parser_status = "unsupported_large_parquet"
                    parser_error = f"Parquet object is {size / 1_000_000:.1f} MB; current normalizer cap is {args.max_parquet_mb:.1f} MB"
                else:
                    parsed_sessions, parser_error = normalize_claude_trace_parquet(path)
                    normalizer = "claude_trace_parquet_request_response_row"
                    parser_status = "normalized_trace_rows" if parser_error is None else "unsupported_schema"

            metrics = session_metrics(parsed_sessions) if parsed_sessions else {}
            if parsed_sessions:
                repo_sessions.extend(parsed_sessions)
            object_statuses[parser_status] += 1
            manifest_rows.append({
                "dataset_repo": candidate.repo,
                "dataset_revision": candidate.revision,
                "candidate_source": candidate.source,
                "repo_path": rel,
                "storage_format": fmt,
                "sha256": digest,
                "size_bytes": size,
                "parser_status": parser_status,
                "parser_error": parser_error,
                "normalizer": normalizer,
                "session_count": metrics.get("session_count", 0),
                "assistant_turns": metrics.get("assistant_turns", 0),
                "tool_calls": metrics.get("tool_calls", 0),
                "corrections": metrics.get("corrections", 0),
                "source_tool": metrics.get("source_tool"),
                "session_types": metrics.get("session_types", []),
                "thinking_visibility": metrics.get("thinking_visibility", []),
                "raw_flags": {
                    "queue_operation": bool(raw_scan.get("queue_operation")),
                    "boucle_marker": bool(raw_scan.get("boucle_marker")),
                    "secret_screening": raw_scan.get("secret_screening"),
                },
            })

        sessions_path = repo_dir / "sessions.json"
        write_json(sessions_path, repo_sessions)
        metrics = session_metrics(repo_sessions) if repo_sessions else {}
        status = "normalized"
        hsmm_result = None
        hsmm_error = None
        if len(repo_sessions) == 0:
            status = "no_parseable_sessions"
        else:
            hsmm_path = args.output_dir / "results" / f"{repo_slug(candidate.repo)}.hsmm.json"
            hsmm_result, hsmm_error = run_hsmm(args.hsmm_script, sessions_path, hsmm_path)
            if hsmm_error:
                status = "hsmm_error"
                error = hsmm_error
            else:
                summary_text = (hsmm_result or {}).get("summary", "").lower()
                if "insufficient" in summary_text:
                    status = "insufficient_data"
                elif "could not fit" in summary_text or not (hsmm_result or {}).get("findings"):
                    status = "model_unstable"
                else:
                    status = "hsmm_complete"

        summary_row = {
            "repo": candidate.repo,
            "revision": candidate.revision,
            "source": candidate.source,
            "status": status,
            "sessions": len(repo_sessions),
            "assistant_turns": metrics.get("assistant_turns", 0),
            "corrections": metrics.get("corrections", 0),
            "tool_calls": metrics.get("tool_calls", 0),
            "pre_correction_lift": finding_value(hsmm_result, "pre_correction_lift"),
            "optimal_n_states": finding_value(hsmm_result, "optimal_n_states"),
            "dominant_pre_correction_state": finding_value(hsmm_result, "dominant_pre_correction_state"),
            "object_statuses": dict(sorted(object_statuses.items())),
            "size_bytes": total_size,
            "note": candidate.note,
            "error": error,
        }
        summary_rows.append(summary_row)
        print(f"{candidate.repo}: {status}, sessions={len(repo_sessions)}, lift={summary_row['pre_correction_lift']}", flush=True)

    with (args.output_dir / "manifest.jsonl").open("w", encoding="utf-8") as f:
        for row in manifest_rows:
            f.write(json.dumps(row, sort_keys=True) + "\n")
    write_json(args.output_dir / "summary.json", summary_rows)
    (args.output_dir / "summary.md").write_text(markdown_summary(summary_rows), encoding="utf-8")
    print(f"\nWrote {args.output_dir / 'summary.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
