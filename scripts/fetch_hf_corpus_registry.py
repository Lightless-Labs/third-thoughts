#!/usr/bin/env python3
"""Fetch a published public corpus registry from a Hugging Face dataset repo."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

try:
    from huggingface_hub import hf_hub_download
except ImportError as exc:  # pragma: no cover
    raise SystemExit(
        "ERROR: missing huggingface_hub. Install with: python3 -m pip install huggingface_hub"
    ) from exc


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-id", required=True, help="HF dataset repo id, e.g. Lightless-Labs/third-thoughts-public-corpora")
    parser.add_argument("--revision", default="main", help="Pinned registry dataset revision or branch.")
    parser.add_argument("--filename", default="corpora.json", help="Registry filename inside the HF dataset repo.")
    parser.add_argument("--output", type=Path, required=True, help="Where to write the fetched registry JSON.")
    parser.add_argument("--cache-dir", type=Path, default=Path(".tmp/hf-registry-cache"))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    downloaded = Path(
        hf_hub_download(
            repo_id=args.repo_id,
            repo_type="dataset",
            revision=args.revision,
            filename=args.filename,
            cache_dir=args.cache_dir,
        )
    )
    try:
        registry = json.loads(downloaded.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"ERROR: fetched registry is not valid JSON: {exc}") from exc
    if registry.get("schema_version") != 1 or not isinstance(registry.get("corpora"), list):
        raise SystemExit("ERROR: fetched registry must have schema_version=1 and a corpora list")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(downloaded, args.output)
    print(json.dumps({"repo_id": args.repo_id, "revision": args.revision, "output": str(args.output), "corpora": len(registry["corpora"])}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
