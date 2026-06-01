#!/usr/bin/env python3
"""Run middens per-user over gated SALT-NLP/SWE-chat transcripts.

This is a resumable batch runner. It groups `sessions.parquet` by `user_id`,
materializes each group's raw transcript JSONL files under `.tmp/`, runs middens,
and deletes the raw materialization immediately after each group.

Only derived middens outputs and a batch summary are kept under `experiments/`.
Do not point `--work-dir` at a tracked directory. The script refuses to run if it
looks like the raw work directory is inside git without being under `.tmp/`.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import pandas as pd
except ImportError as exc:  # pragma: no cover
    print("Missing pandas. Install with: python3 -m pip install pandas pyarrow", file=sys.stderr)
    raise SystemExit(2) from exc

from hf_dataset_adapters import SweChatAdapter, stable_hash


DEFAULT_REPO = "SALT-NLP/SWE-chat"
DEFAULT_REVISION = "f66cca95b14caaa4177f7ed5eaa424608dadcffa"


@dataclass(frozen=True)
class UserGroup:
    user_key: str
    raw_user_id: Any
    sessions: pd.DataFrame


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-id", default=DEFAULT_REPO)
    parser.add_argument("--revision", default=DEFAULT_REVISION)
    parser.add_argument("--token-env", default="HF_TOKEN")
    parser.add_argument("--middens-bin", type=Path, default=Path("middens/target/release/middens"))
    parser.add_argument("--cache-dir", type=Path, default=Path(".tmp/hf-cache-swe-chat-per-user-middens"))
    parser.add_argument("--work-dir", type=Path, default=Path(".tmp/swe-chat-per-user-middens-raw"))
    parser.add_argument("--output-root", type=Path, default=Path("experiments/swe-chat-per-user-middens"))
    parser.add_argument("--force", action="store_true", help="Overwrite existing derived output root and batch state.")
    parser.add_argument("--resume", action="store_true", help="Resume from existing batch state; completed groups are skipped.")
    parser.add_argument("--include-missing-user", action="store_true", help="Include the huge missing_user bucket.")
    parser.add_argument("--only-missing-user", action="store_true", help="Only run the missing_user bucket.")
    parser.add_argument(
        "--agents",
        default=None,
        help="Comma-separated agent names to include before grouping (e.g. 'Claude Code,Codex'). Default: all agents.",
    )
    parser.add_argument(
        "--skip-missing-transcripts",
        action="store_true",
        help="Skip individual transcript 404s instead of failing the whole user group.",
    )
    parser.add_argument("--min-sessions", type=int, default=1, help="Skip user groups with fewer sessions after filters.")
    parser.add_argument("--limit-users", type=int, default=None, help="Run at most N selected user groups.")
    parser.add_argument("--timeout", type=int, default=1800, help="middens Python technique timeout seconds.")
    parser.add_argument("--command-timeout", type=int, default=2400, help="Wall-clock timeout per middens process.")
    parser.add_argument("--split-smoke", action="store_true", help="Also run --split --no-python after each full run.")
    parser.add_argument("--dry-run", action="store_true", help="Plan only; do not download transcripts or run middens.")
    return parser.parse_args()


def fail(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(2)


def safe_reset(path: Path, force: bool, resume: bool) -> None:
    if path.exists() and force and not resume:
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def guard_raw_work_dir(work_dir: Path) -> None:
    resolved = work_dir.resolve()
    cwd = Path.cwd().resolve()
    try:
        rel = resolved.relative_to(cwd)
    except ValueError:
        return
    if not rel.parts or rel.parts[0] != ".tmp":
        fail(f"raw work dir must be outside the repo or under .tmp/: {work_dir}")


def download_sessions_table(adapter: SweChatAdapter) -> tuple[pd.DataFrame, str]:
    pinned_revision = adapter.pinned_revision
    columns = ["session_id", "user_id", "transcript_path", "agent", "repo_id", "created_at"]
    sessions = adapter.load_sessions(columns=columns, revision=pinned_revision)
    sessions = sessions.dropna(subset=["session_id"])
    return sessions, pinned_revision


def select_groups(sessions: pd.DataFrame, args: argparse.Namespace) -> list[UserGroup]:
    sessions = sessions.copy()
    if args.agents:
        allowed_agents = {agent.strip() for agent in args.agents.split(",") if agent.strip()}
        sessions = sessions[sessions["agent"].isin(allowed_agents)].copy()
    sessions["user_key"] = sessions["user_id"].map(lambda value: stable_hash(value, "user"))
    groups: list[UserGroup] = []
    for user_key, group in sessions.groupby("user_key", dropna=False):
        if len(group) < args.min_sessions:
            continue
        if user_key == "missing_user" and not args.include_missing_user and not args.only_missing_user:
            continue
        if args.only_missing_user and user_key != "missing_user":
            continue
        raw_user_id = group["user_id"].iloc[0] if "user_id" in group else None
        groups.append(UserGroup(user_key=user_key, raw_user_id=raw_user_id, sessions=group.sort_values("session_id")))
    groups.sort(key=lambda item: (-len(item.sessions), item.user_key))
    if args.limit_users is not None:
        groups = groups[: args.limit_users]
    return groups


def load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"groups": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def save_state(path: Path, state: dict[str, Any]) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(path)


def materialize_group(
    adapter: SweChatAdapter,
    revision: str,
    group: UserGroup,
    dest: Path,
    skip_missing: bool,
) -> tuple[int, int]:
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True, exist_ok=True)
    copied = 0
    skipped = 0
    for _, row in group.sessions.iterrows():
        session_id = str(row["session_id"])
        transcript_path = str(row.get("transcript_path") or "")
        if not session_id or session_id == "nan":
            skipped += 1
            continue
        try:
            src = adapter.download_transcript(session_id, transcript_path, revision=revision)
        except Exception:
            if skip_missing:
                skipped += 1
                continue
            raise
        # Keep filenames deterministic but avoid raw IDs where possible.
        out_name = f"{stable_hash(session_id, 'session')}.jsonl"
        shutil.copyfile(src, dest / out_name)
        copied += 1
    return copied, skipped


def run_command(command: list[str], env: dict[str, str], log_path: Path, timeout: int) -> tuple[int | None, float]:
    start = time.time()
    with log_path.open("w", encoding="utf-8") as log:
        log.write("$ " + " ".join(command) + "\n\n")
        log.flush()
        try:
            proc = subprocess.run(
                command,
                stdout=log,
                stderr=subprocess.STDOUT,
                env=env,
                timeout=timeout,
                check=False,
            )
            return proc.returncode, time.time() - start
        except subprocess.TimeoutExpired:
            log.write(f"\nTIMEOUT after {timeout}s\n")
            return None, time.time() - start


def run_middens_for_group(args: argparse.Namespace, group: UserGroup, corpus_dir: Path, group_out: Path) -> dict[str, Any]:
    group_out.mkdir(parents=True, exist_ok=True)
    xdg = group_out / "xdg"
    env = os.environ.copy()
    env["XDG_DATA_HOME"] = str(xdg.resolve())
    full_output = group_out / "middens-results"
    command = [
        str(args.middens_bin),
        "analyze",
        str(corpus_dir),
        "--all",
        "--timeout",
        str(args.timeout),
        "--force",
        "--output",
        str(full_output),
    ]
    code, elapsed = run_command(command, env, group_out / "analyze.log", args.command_timeout)
    result: dict[str, Any] = {"exit_code": code, "elapsed_seconds": elapsed}
    analysis_root = xdg / "com.lightless-labs.third-thoughts" / "analysis"
    runs = sorted(analysis_root.glob("run-*")) if analysis_root.exists() else []
    if runs:
        result["analysis_dir"] = str(runs[-1])
        manifest_path = runs[-1] / "manifest.json"
        if manifest_path.exists():
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            result["technique_count"] = len(manifest.get("techniques", []))
            result["technique_errors"] = sum(1 for t in manifest.get("techniques", []) if t.get("errors"))
    if args.split_smoke:
        split_xdg = group_out / "xdg-split"
        split_env = os.environ.copy()
        split_env["XDG_DATA_HOME"] = str(split_xdg.resolve())
        split_command = [
            str(args.middens_bin),
            "analyze",
            str(corpus_dir),
            "--split",
            "--no-python",
            "--output",
            str(group_out / "split-results"),
        ]
        split_code, split_elapsed = run_command(split_command, split_env, group_out / "split.log", args.command_timeout)
        result["split_exit_code"] = split_code
        result["split_elapsed_seconds"] = split_elapsed
    return result


def main() -> int:
    args = parse_args()
    token = os.environ.get(args.token_env)
    if not token and not args.dry_run:
        fail(f"missing HF token in ${args.token_env}; SWE-chat is gated")
    if not args.middens_bin.exists() and not args.dry_run:
        fail(f"middens binary not found: {args.middens_bin}. Build with: cd middens && cargo build --release --locked")
    if args.force and args.resume:
        fail("--force and --resume are mutually exclusive")
    guard_raw_work_dir(args.work_dir)
    safe_reset(args.output_root, args.force, args.resume)
    args.cache_dir.mkdir(parents=True, exist_ok=True)
    args.work_dir.mkdir(parents=True, exist_ok=True)

    adapter = SweChatAdapter(args.repo_id, args.revision, args.cache_dir, token)
    sessions, revision = download_sessions_table(adapter)
    groups = select_groups(sessions, args)
    plan = {
        "repo_id": args.repo_id,
        "revision": revision,
        "selected_groups": len(groups),
        "selected_sessions": int(sum(len(g.sessions) for g in groups)),
        "include_missing_user": bool(args.include_missing_user),
        "only_missing_user": bool(args.only_missing_user),
        "min_sessions": args.min_sessions,
        "limit_users": args.limit_users,
        "agents": args.agents,
        "groups": [{"user_key": g.user_key, "session_count": int(len(g.sessions))} for g in groups],
    }
    (args.output_root / "plan.json").write_text(json.dumps(plan, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({k: v for k, v in plan.items() if k != "groups"}, sort_keys=True))
    if args.dry_run:
        return 0

    state_path = args.output_root / "batch_state.json"
    state = load_state(state_path) if args.resume else {"groups": {}}
    state.setdefault("groups", {})
    state.update({k: v for k, v in plan.items() if k != "groups"})
    save_state(state_path, state)

    for idx, group in enumerate(groups, 1):
        current = state["groups"].get(group.user_key, {})
        if args.resume and current.get("status") == "completed":
            print(f"[{idx}/{len(groups)}] skip completed {group.user_key} ({len(group.sessions)} sessions)")
            continue
        print(f"[{idx}/{len(groups)}] run {group.user_key} ({len(group.sessions)} sessions)", flush=True)
        group_out = args.output_root / "users" / group.user_key
        corpus_dir = args.work_dir / group.user_key
        started = time.time()
        record: dict[str, Any] = {
            "status": "running",
            "session_count": int(len(group.sessions)),
            "started_at_epoch": started,
        }
        state["groups"][group.user_key] = record
        save_state(state_path, state)
        try:
            copied, skipped = materialize_group(
                adapter,
                revision,
                group,
                corpus_dir,
                args.skip_missing_transcripts,
            )
            record["materialized_files"] = copied
            record["skipped_transcripts"] = skipped
            if copied == 0:
                record["status"] = "no_transcripts"
            else:
                result = run_middens_for_group(args, group, corpus_dir, group_out)
                record.update(result)
                record["status"] = "completed" if result.get("exit_code") == 0 else "failed"
        except Exception as exc:  # noqa: BLE001 - batch runner records and continues
            record["status"] = "error"
            record["error"] = f"{type(exc).__name__}: {exc}"
        finally:
            if corpus_dir.exists():
                shutil.rmtree(corpus_dir)
            record["finished_at_epoch"] = time.time()
            record["total_elapsed_seconds"] = record["finished_at_epoch"] - started
            state["groups"][group.user_key] = record
            save_state(state_path, state)
        print(f"[{idx}/{len(groups)}] {group.user_key}: {record['status']} in {record['total_elapsed_seconds']:.1f}s", flush=True)

    rows = []
    for user_key, record in sorted(state["groups"].items()):
        row = {"user_key": user_key}
        row.update(record)
        rows.append(row)
    pd.DataFrame(rows).to_csv(args.output_root / "batch_summary.csv", index=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
