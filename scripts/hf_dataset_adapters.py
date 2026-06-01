#!/usr/bin/env python3
"""Dataset-specific Hugging Face adapters for agent-session corpora.

These adapters capture dataset contracts that are not generic JSONL directory
semantics. Keep the knowledge here instead of scattering path guesses like
`transcripts/{session_id}.jsonl` through analysis scripts.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

try:
    import pandas as pd
    from huggingface_hub import HfApi, hf_hub_download
except ImportError as exc:  # pragma: no cover
    print("Missing dependencies. Install with: python3 -m pip install pandas pyarrow huggingface_hub")
    raise SystemExit(2) from exc


@dataclass(frozen=True)
class SweChatAdapter:
    """Adapter for `SALT-NLP/SWE-chat`.

    SWE-chat exposes per-session metadata in Parquet tables and raw transcripts
    under `transcripts/{session_id}.jsonl`. The `sessions.transcript_path`
    column may contain the original agent-local path (`.claude/projects/...`),
    which is useful provenance but not the primary HF repo object path.
    """

    repo_id: str
    revision: str
    cache_dir: Path
    token: str | None

    @property
    def pinned_revision(self) -> str:
        info = HfApi(token=self.token).dataset_info(self.repo_id, revision=self.revision)
        return info.sha or self.revision

    def transcript_repo_path(self, session_id: str) -> str:
        if not session_id or session_id == "nan":
            raise ValueError("SWE-chat transcript lookup requires a non-empty session_id")
        return f"transcripts/{session_id}.jsonl"

    def transcript_candidate_paths(self, session_id: str, transcript_path: str | None = None) -> list[str]:
        canonical = self.transcript_repo_path(session_id)
        candidates = [canonical]
        if transcript_path and transcript_path not in candidates:
            # Fallback for future schema variants only. In the current dataset,
            # this is commonly an agent-local path and may not exist on HF.
            candidates.append(transcript_path)
        return candidates

    def download_file(self, repo_path: str, revision: str | None = None) -> Path:
        return Path(
            hf_hub_download(
                self.repo_id,
                repo_path,
                repo_type="dataset",
                revision=revision or self.revision,
                cache_dir=self.cache_dir,
                token=self.token,
            )
        )

    def download_table(self, table_name: str, revision: str | None = None) -> Path:
        if not table_name.endswith(".parquet"):
            table_name = f"{table_name}.parquet"
        return self.download_file(table_name, revision=revision)

    def load_sessions(self, columns: Iterable[str] | None = None, revision: str | None = None) -> pd.DataFrame:
        sessions_path = self.download_table("sessions", revision=revision)
        return pd.read_parquet(sessions_path, columns=list(columns) if columns is not None else None)

    def load_repositories(self, columns: Iterable[str] | None = None, revision: str | None = None) -> pd.DataFrame:
        repositories_path = self.download_table("repositories", revision=revision)
        return pd.read_parquet(repositories_path, columns=list(columns) if columns is not None else None)

    def download_transcript(self, session_id: str, transcript_path: str | None = None, revision: str | None = None) -> Path:
        last_error: Exception | None = None
        for candidate in self.transcript_candidate_paths(session_id, transcript_path):
            try:
                return self.download_file(candidate, revision=revision)
            except Exception as exc:  # noqa: BLE001 - try fallback, then raise clear adapter error
                last_error = exc
        raise RuntimeError(f"could not download SWE-chat transcript for session {session_id}: {last_error}")


def stable_hash(value: Any, prefix: str) -> str:
    """Stable public-ish key for identifiers in sanitized outputs."""

    import hashlib

    if value is None or pd.isna(value):
        return f"missing_{prefix}"
    digest = hashlib.sha256(str(value).encode("utf-8")).hexdigest()[:16]
    return f"{prefix}_{digest}"
