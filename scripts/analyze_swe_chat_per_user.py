#!/usr/bin/env python3
"""Sanitized per-user aggregate analysis for SALT-NLP/SWE-chat.

This intentionally uses the dataset's Parquet metadata tables rather than raw
transcript text. User/repo/owner identifiers are hashed before output so the
result can be inspected locally without spraying raw IDs around. Raw rows and
transcript snippets are never written.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from collections import Counter
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-id", default=DEFAULT_REPO)
    parser.add_argument("--revision", default=DEFAULT_REVISION)
    parser.add_argument("--token-env", default="HF_TOKEN", help="Environment variable containing the HF token.")
    parser.add_argument("--cache-dir", type=Path, default=Path(".tmp/hf-cache-swe-chat-per-user"))
    parser.add_argument("--output", type=Path, default=Path("experiments/swe-chat-per-user"))
    parser.add_argument("--force", action="store_true", help="Overwrite output directory if it exists.")
    return parser.parse_args()


def fail(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(2)


def top_counts(values: pd.Series, limit: int = 5) -> list[dict[str, Any]]:
    counts = Counter(v for v in values.dropna().astype(str) if v)
    return [{"value": value, "count": int(count)} for value, count in counts.most_common(limit)]


def numeric_summary(frame: pd.DataFrame, column: str) -> dict[str, float | int | None]:
    series = pd.to_numeric(frame[column], errors="coerce").dropna()
    if series.empty:
        return {"sum": 0, "mean": None, "median": None, "max": None}
    return {
        "sum": float(series.sum()),
        "mean": float(series.mean()),
        "median": float(series.median()),
        "max": float(series.max()),
    }


def reset_output(path: Path, force: bool) -> None:
    if path.exists():
        if not force:
            fail(f"output directory already exists: {path}. Pass --force to overwrite it.")
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def main() -> int:
    args = parse_args()
    token = os.environ.get(args.token_env)
    if not token:
        fail(
            f"missing HF token in ${args.token_env}. SWE-chat is gated; export {args.token_env}=<token> "
            "after accepting dataset access."
        )

    reset_output(args.output, args.force)
    args.cache_dir.mkdir(parents=True, exist_ok=True)

    adapter = SweChatAdapter(args.repo_id, args.revision, args.cache_dir, token)
    revision = adapter.pinned_revision

    session_columns = [
        "session_id",
        "repo_id",
        "owner_id",
        "user_id",
        "agent",
        "strategy",
        "created_at",
        "cli_version",
        "files_touched_count",
        "checkpoints_count",
        "input_tokens",
        "output_tokens",
        "cache_creation_tokens",
        "cache_read_tokens",
        "api_call_count",
        "agent_lines",
        "human_added",
        "human_modified",
        "human_removed",
        "total_committed",
        "agent_percentage",
        "tool_call_count",
        "unique_tools_count",
        "research_count",
        "action_count",
        "duration_seconds",
        "turn_count",
        "prompt_count",
        "user_persona",
        "session_success",
        "transcript_path",
    ]
    sessions = adapter.load_sessions(columns=session_columns, revision=revision)
    repos = adapter.load_repositories(
        columns=["repo_id", "repo_type_domain", "repo_type_audience", "license_type"],
        revision=revision,
    )
    sessions = sessions.merge(repos, on="repo_id", how="left")
    sessions["user_key"] = sessions["user_id"].map(lambda value: stable_hash(value, "user"))
    sessions["repo_key"] = sessions["repo_id"].map(lambda value: stable_hash(value, "repo"))
    sessions["owner_key"] = sessions["owner_id"].map(lambda value: stable_hash(value, "owner"))

    per_user: list[dict[str, Any]] = []
    numeric_columns = [
        "prompt_count",
        "turn_count",
        "tool_call_count",
        "unique_tools_count",
        "duration_seconds",
        "input_tokens",
        "output_tokens",
        "api_call_count",
        "files_touched_count",
        "agent_percentage",
        "total_committed",
        "agent_lines",
        "human_added",
        "human_modified",
        "human_removed",
    ]

    for user_key, group in sessions.groupby("user_key", dropna=False):
        row: dict[str, Any] = {
            "user_key": user_key,
            "session_count": int(len(group)),
            "repo_count": int(group["repo_key"].nunique(dropna=True)),
            "owner_count": int(group["owner_key"].nunique(dropna=True)),
            "first_session_at": group["created_at"].min().isoformat() if pd.notna(group["created_at"].min()) else None,
            "last_session_at": group["created_at"].max().isoformat() if pd.notna(group["created_at"].max()) else None,
            "agents": top_counts(group["agent"], 8),
            "strategies": top_counts(group["strategy"], 8),
            "personas": top_counts(group["user_persona"], 8),
            "session_success": top_counts(group["session_success"], 8),
            "repo_domains": top_counts(group["repo_type_domain"], 8),
            "repo_audiences": top_counts(group["repo_type_audience"], 8),
        }
        for column in numeric_columns:
            summary = numeric_summary(group, column)
            row[f"{column}_sum"] = summary["sum"]
            row[f"{column}_mean"] = summary["mean"]
            row[f"{column}_median"] = summary["median"]
            row[f"{column}_max"] = summary["max"]
        per_user.append(row)

    per_user.sort(key=lambda row: (-row["session_count"], row["user_key"]))

    summary = {
        "repo_id": args.repo_id,
        "revision": revision,
        "gated": "auto",
        "sessions": int(len(sessions)),
        "users": int(len(per_user)),
        "users_with_missing_user_id": int((sessions["user_key"] == "missing_user").any()),
        "sessions_with_missing_user_id": int((sessions["user_key"] == "missing_user").sum()),
        "repos": int(sessions["repo_key"].nunique(dropna=True)),
        "owners": int(sessions["owner_key"].nunique(dropna=True)),
        "agents": top_counts(sessions["agent"], 20),
        "session_count_distribution": {
            "min": int(pd.Series([u["session_count"] for u in per_user]).min()),
            "median": float(pd.Series([u["session_count"] for u in per_user]).median()),
            "mean": float(pd.Series([u["session_count"] for u in per_user]).mean()),
            "max": int(pd.Series([u["session_count"] for u in per_user]).max()),
        },
    }

    csv_rows = []
    for row in per_user:
        flat = {k: v for k, v in row.items() if not isinstance(v, list)}
        flat["top_agent"] = row["agents"][0]["value"] if row["agents"] else None
        flat["top_agent_count"] = row["agents"][0]["count"] if row["agents"] else 0
        flat["top_persona"] = row["personas"][0]["value"] if row["personas"] else None
        flat["top_success_label"] = row["session_success"][0]["value"] if row["session_success"] else None
        csv_rows.append(flat)

    (args.output / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    (args.output / "per_user.json").write_text(json.dumps(per_user, indent=2, sort_keys=True), encoding="utf-8")
    pd.DataFrame(csv_rows).to_csv(args.output / "per_user_summary.csv", index=False)

    top_rows = per_user[:20]
    report_lines = [
        "# SWE-chat per-user aggregate analysis",
        "",
        "Source: `SALT-NLP/SWE-chat` metadata tables only (`sessions.parquet` + `repositories.parquet`).",
        "No raw transcript text, prompts, tool results, diffs, or unhashed user/repo IDs are written.",
        "",
        "## Corpus summary",
        "",
        f"- Revision: `{revision}`",
        f"- Sessions: {summary['sessions']:,}",
        f"- User groups: {summary['users']:,} (including `missing_user` if present)",
        f"- Sessions with missing `user_id`: {summary['sessions_with_missing_user_id']:,}",
        f"- Repositories: {summary['repos']:,}",
        f"- Owners: {summary['owners']:,}",
        "",
        "## Agent mix",
        "",
        "| Agent | Sessions |",
        "|---|---:|",
    ]
    for item in summary["agents"]:
        report_lines.append(f"| {item['value']} | {item['count']:,} |")
    report_lines.extend([
        "",
        "## Top user groups by session count",
        "",
        "| User key | Sessions | Repos | Top agent | Prompt count sum | Tool calls sum | Agent % mean |",
        "|---|---:|---:|---|---:|---:|---:|",
    ])
    for row in top_rows:
        top_agent = row["agents"][0]["value"] if row["agents"] else ""
        agent_pct = row.get("agent_percentage_mean")
        agent_pct_s = "" if agent_pct is None else f"{agent_pct:.1f}"
        report_lines.append(
            "| {user_key} | {session_count:,} | {repo_count:,} | {top_agent} | {prompts:,.0f} | {tools:,.0f} | {agent_pct} |".format(
                user_key=row["user_key"],
                session_count=row["session_count"],
                repo_count=row["repo_count"],
                top_agent=top_agent,
                prompts=row.get("prompt_count_sum") or 0,
                tools=row.get("tool_call_count_sum") or 0,
                agent_pct=agent_pct_s,
            )
        )
    report_lines.extend([
        "",
        "## Middens per-user battery feasibility",
        "",
        "The metadata table gives `transcript_path` per session, so a full per-user middens run is mechanically possible:",
        "materialize transcripts grouped by `user_id` (or `missing_user`), then run `middens analyze --all` for each group.",
        "That is intentionally not performed by this metadata script because it would download/write raw gated transcripts per user.",
    ])
    (args.output / "report.md").write_text("\n".join(report_lines) + "\n", encoding="utf-8")

    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
