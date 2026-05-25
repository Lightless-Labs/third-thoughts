#!/usr/bin/env python3
"""Build a Hugging Face dataset folder for the public corpus registry.

The generated folder is suitable for `huggingface_hub.upload_folder`. It contains:
- README.md: dataset card
- corpora.json: canonical registry JSON
- corpora.jsonl: one corpus entry per row for HF dataset preview
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
from typing import Any


DEFAULT_REGISTRY = Path("docs/corpora/public-hf-analysis-corpora.json")
DEFAULT_OUTPUT = Path(".tmp/hf-corpus-registry-dataset")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def fail(message: str) -> None:
    raise SystemExit(f"ERROR: {message}")


def load_registry(path: Path) -> dict[str, Any]:
    try:
        registry = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        fail(f"registry not found: {path}")
    except json.JSONDecodeError as exc:
        fail(f"registry is not valid JSON: {path}: {exc}")
    if registry.get("schema_version") != 1:
        fail(f"unsupported schema_version {registry.get('schema_version')!r}; expected 1")
    corpora = registry.get("corpora")
    if not isinstance(corpora, list) or not corpora:
        fail("registry must contain a non-empty 'corpora' list")
    ids = [c.get("id") for c in corpora]
    duplicates = sorted({cid for cid in ids if ids.count(cid) > 1})
    if duplicates:
        fail(f"duplicate corpus id(s): {', '.join(duplicates)}")
    return registry


def dataset_card(registry: dict[str, Any]) -> str:
    corpora = registry["corpora"]
    enabled = [c for c in corpora if c.get("analysis_enabled")]
    disabled = [c for c in corpora if not c.get("analysis_enabled")]
    built = dt.datetime.now(tz=dt.timezone.utc).isoformat().replace("+00:00", "Z")

    lines = [
        "---",
        "license: agpl-3.0",
        "pretty_name: Third Thoughts Public HF Analysis Corpora",
        "tags:",
        "- ai-agents",
        "- coding-agents",
        "- session-logs",
        "- reproducibility",
        "- middens",
        "---",
        "",
        "# Third Thoughts Public HF Analysis Corpora",
        "",
        "This dataset is a registry of pinned public Hugging Face corpora used by",
        "Third Thoughts / `middens` CI. It does **not** contain raw transcript data;",
        "it contains pointers to public datasets, pinned revisions, expected object",
        "counts, and CI-tier metadata.",
        "",
        f"Generated: `{built}`",
        "",
        "## Files",
        "",
        "- `corpora.json` — canonical registry consumed by CI helpers.",
        "- `corpora.jsonl` — one corpus registry entry per row for easy preview.",
        "",
        "## Analysis-enabled corpora",
        "",
        "| Corpus id | Dataset repo | Revision | CI tiers |",
        "|---|---|---|---|",
    ]
    for corpus in enabled:
        lines.append(
            f"| `{corpus['id']}` | `{corpus['dataset_repo']}` | `{corpus['dataset_revision']}` | {', '.join(corpus.get('ci_tiers', []))} |"
        )
    if disabled:
        lines.extend([
            "",
            "## Tracked but not analysis-enabled yet",
            "",
            "| Corpus id | Dataset repo | Reason |",
            "|---|---|---|",
        ])
        for corpus in disabled:
            reason = corpus.get("notes") or corpus.get("description") or "not enabled"
            lines.append(f"| `{corpus['id']}` | `{corpus['dataset_repo']}` | {reason} |")
    lines.extend([
        "",
        "## Privacy note",
        "",
        "The upstream datasets are public, but public does not mean privacy-safe.",
        "This registry avoids transcript snippets and raw data. Downstream analysis",
        "artifacts should likewise stay aggregate-only unless explicitly reviewed.",
        "",
        "## Usage",
        "",
        "```bash",
        "python scripts/fetch_hf_corpus_registry.py \\",
        "  --repo-id <org-or-user>/third-thoughts-public-corpora \\",
        "  --revision main \\",
        "  --output .tmp/corpora.json",
        "python scripts/hf_corpus_matrix.py --registry .tmp/corpora.json --tier representative",
        "```",
        "",
    ])
    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    registry = load_registry(args.registry)
    args.output.mkdir(parents=True, exist_ok=True)

    (args.output / "corpora.json").write_text(
        json.dumps(registry, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    with (args.output / "corpora.jsonl").open("w", encoding="utf-8") as f:
        for corpus in registry["corpora"]:
            f.write(json.dumps(corpus, sort_keys=True) + "\n")
    (args.output / "README.md").write_text(dataset_card(registry), encoding="utf-8")

    print(json.dumps({"output": str(args.output), "corpora": len(registry["corpora"])}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
