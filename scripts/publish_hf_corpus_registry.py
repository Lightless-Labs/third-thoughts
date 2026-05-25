#!/usr/bin/env python3
"""Publish the public corpus registry as a Hugging Face dataset.

Requires an authenticated HF token with write access. Use either `huggingface-cli
login` or `HF_TOKEN=...`.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

try:
    from huggingface_hub import HfApi, get_token
except ImportError as exc:  # pragma: no cover
    raise SystemExit(
        "ERROR: missing huggingface_hub. Install with: python3 -m pip install huggingface_hub"
    ) from exc

from build_hf_corpus_registry_dataset import DEFAULT_OUTPUT, DEFAULT_REGISTRY, main as build_main


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-id", required=True, help="Destination HF dataset repo id, e.g. Lightless-Labs/third-thoughts-public-corpora")
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--dataset-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--private", action="store_true", help="Create the HF dataset as private if it does not exist.")
    parser.add_argument("--revision", default="main", help="Branch/revision to upload to. Default: main.")
    return parser.parse_args()


def fail(message: str) -> None:
    raise SystemExit(f"ERROR: {message}")


def main() -> int:
    args = parse_args()
    token = get_token()
    if not token:
        fail(
            "no Hugging Face token found. Run `huggingface-cli login` or set `HF_TOKEN`; "
            "then retry, e.g. `HF_TOKEN=... python scripts/publish_hf_corpus_registry.py "
            "--repo-id Lightless-Labs/third-thoughts-public-corpora`."
        )

    # Rebuild the dataset folder with the requested paths by invoking the builder
    # logic through a tiny subprocess-compatible argv swap would be silly; just
    # import and call the underlying script as a process for clarity.
    import subprocess, sys

    subprocess.run(
        [sys.executable, "scripts/build_hf_corpus_registry_dataset.py", "--registry", str(args.registry), "--output", str(args.dataset_dir)],
        check=True,
    )

    api = HfApi(token=token)
    api.create_repo(repo_id=args.repo_id, repo_type="dataset", private=args.private, exist_ok=True)
    commit = api.upload_folder(
        repo_id=args.repo_id,
        repo_type="dataset",
        revision=args.revision,
        folder_path=str(args.dataset_dir),
        commit_message="Update Third Thoughts public corpus registry",
    )
    print(json.dumps({"repo_id": args.repo_id, "revision": args.revision, "commit_url": str(commit)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
