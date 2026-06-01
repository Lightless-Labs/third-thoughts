#!/usr/bin/env python3
"""Compare public results fingerprints and decide whether work is reusable."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
SCOPES = ("analysis", "interpretation", "all")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--current", type=Path, required=True, help="Current fingerprints.json")
    parser.add_argument("--previous", type=Path, required=True, help="Previous fingerprints.json from a published bundle")
    parser.add_argument("--scope", choices=SCOPES, default="analysis")
    parser.add_argument("--github-output", type=Path, default=None, help="Optional path to append changed/reusable outputs, usually $GITHUB_OUTPUT")
    return parser.parse_args()


def fail(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(2)


def load_json(path: Path, label: str, *, missing_ok: bool = False) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        if missing_ok:
            return None
        fail(f"{label} not found: {path}")
    except json.JSONDecodeError as exc:
        fail(f"{label} is not valid JSON: {path}: {exc}")


def fingerprint_value(data: dict[str, Any], key: str) -> str | None:
    section = data.get("fingerprints", {}).get(key)
    if not isinstance(section, dict):
        return None
    value = section.get("fingerprint")
    return value if isinstance(value, str) else None


def compare(current: dict[str, Any], previous: dict[str, Any] | None, scope: str) -> dict[str, Any]:
    if previous is None:
        return {"changed": True, "reusable": False, "reason": "previous_missing", "scope": scope}
    if current.get("schema_version") != SCHEMA_VERSION:
        fail(f"current fingerprints schema_version={current.get('schema_version')!r}; expected {SCHEMA_VERSION}")
    if previous.get("schema_version") != SCHEMA_VERSION:
        return {"changed": True, "reusable": False, "reason": "previous_schema_mismatch", "scope": scope}
    if current.get("corpus_id") != previous.get("corpus_id"):
        return {"changed": True, "reusable": False, "reason": "corpus_id_mismatch", "scope": scope}

    keys = ["corpus", "process"] if scope == "analysis" else ["interpretation"] if scope == "interpretation" else ["corpus", "process", "interpretation"]
    mismatches: list[str] = []
    missing: list[str] = []
    for key in keys:
        current_value = fingerprint_value(current, key)
        previous_value = fingerprint_value(previous, key)
        if current_value is None or previous_value is None:
            missing.append(key)
        elif current_value != previous_value:
            mismatches.append(key)
    if missing:
        return {"changed": True, "reusable": False, "reason": "missing_fingerprint:" + ",".join(missing), "scope": scope}
    if mismatches:
        return {"changed": True, "reusable": False, "reason": "fingerprint_mismatch:" + ",".join(mismatches), "scope": scope}
    return {"changed": False, "reusable": True, "reason": "fingerprints_match", "scope": scope}


def append_github_output(path: Path, result: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as fh:
        print(f"changed={str(bool(result['changed'])).lower()}", file=fh)
        print(f"reusable={str(bool(result['reusable'])).lower()}", file=fh)
        print(f"reason={result['reason']}", file=fh)


def main() -> int:
    args = parse_args()
    current = load_json(args.current, "current fingerprints")
    previous = load_json(args.previous, "previous fingerprints", missing_ok=True)
    if not isinstance(current, dict):
        fail("current fingerprints must be a JSON object")
    if previous is not None and not isinstance(previous, dict):
        fail("previous fingerprints must be a JSON object")
    result = compare(current, previous, args.scope)
    output_path = args.github_output or (Path(os.environ["GITHUB_OUTPUT"]) if os.environ.get("GITHUB_OUTPUT") else None)
    if output_path is not None:
        append_github_output(output_path, result)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
