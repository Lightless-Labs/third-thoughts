#!/usr/bin/env python3
"""Interpret public-safe comparative corpus metrics."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
DEFAULT_PROMPT = Path("docs/prompts/public-comparative-interpretation-v1.md")
CURATED_INPUTS = (
    "corpus-index.json",
    "comparative-metrics.json",
    "technique-status-matrix.json",
    "finding-replication-matrix.json",
)
FORBIDDEN_KEYS = {
    "session_id",
    "sessionId",
    "source_paths",
    "source_path",
    "repo_path",
    "generated_path",
    "request_id",
    "tool_result",
    "tool_results",
    "tool_payload",
    "prompt",
    "thinking",
    "raw_text",
}
FORBIDDEN_TEXT_MARKERS = (
    "/Users/",
    "source_paths",
    "tool_result",
    "tool_results",
    "raw-session",
    "sessionId",
    "session_id",
    "repo_path",
    "generated_path",
    "request_id",
)
REQUIRED_HEADINGS = (
    "## Cross-corpus summary",
    "## Replicated or directionally consistent patterns",
    "## Variable, provisional, or not tested",
    "## Coverage gaps",
    "## Suggested public wording",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--comparative-dir", type=Path, required=True, help="site-data/comparative directory")
    parser.add_argument("--prompt", type=Path, default=DEFAULT_PROMPT)
    parser.add_argument("--model", required=True, help="Model/provider identifier recorded in metadata")
    parser.add_argument("--temperature", default="default", help="Model temperature/settings label recorded in metadata")
    parser.add_argument("--runner-command", default=None, help="Trusted command that reads prompt from stdin and writes Markdown to stdout")
    parser.add_argument("--response-file", type=Path, default=None, help="Read Markdown response from file; intended for tests/review fixtures")
    parser.add_argument("--dry-run", action="store_true", help="Write the rendered prompt and do not call a model")
    parser.add_argument("--force", action="store_true", help="Regenerate even when interpretation fingerprint is unchanged")
    parser.add_argument("--output", type=Path, default=None, help="Output Markdown path; defaults to <comparative-dir>/interpretation.md")
    parser.add_argument("--metadata-output", type=Path, default=None, help="Metadata path; defaults to <comparative-dir>/interpretation.json")
    parser.add_argument("--prompt-output", type=Path, default=None, help="Dry-run prompt path; defaults to <comparative-dir>/interpretation.prompt.md")
    return parser.parse_args()


def fail(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(2)


def canonical_json(data: Any) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def hash_json(data: Any) -> str:
    return hashlib.sha256(canonical_json(data).encode("utf-8")).hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def load_json(path: Path, label: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        fail(f"{label} not found: {path}")
    except json.JSONDecodeError as exc:
        fail(f"{label} is not valid JSON: {path}: {exc}")


def require_comparative_dir(path: Path) -> None:
    if not path.exists():
        fail(f"comparative-dir does not exist: {path}")
    if not path.is_dir():
        fail(f"comparative-dir must be a directory: {path}")


def check_safe_json(value: Any, label: str, path: str = "$") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if str(key) in FORBIDDEN_KEYS:
                fail(f"unsafe key {path}.{key} in {label}; interpreter inputs must be curated public-safe bundles")
            check_safe_json(child, label, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            check_safe_json(child, label, f"{path}[{index}]")
    elif isinstance(value, str):
        for marker in FORBIDDEN_TEXT_MARKERS:
            if marker in value:
                fail(f"unsafe text marker {marker!r} in {label} at {path}")


def load_evidence(comparative_dir: Path) -> dict[str, Any]:
    evidence: dict[str, Any] = {}
    for filename in CURATED_INPUTS:
        data = load_json(comparative_dir / filename, filename)
        check_safe_json(data, filename)
        evidence[filename.removesuffix(".json").replace("-", "_")] = data
    return evidence


def render_prompt(template_path: Path, evidence: dict[str, Any]) -> str:
    if not template_path.is_file():
        fail(f"prompt template not found: {template_path}")
    template = template_path.read_text(encoding="utf-8")
    if "{{EVIDENCE_JSON}}" not in template:
        fail(f"prompt template must contain {{EVIDENCE_JSON}} placeholder: {template_path}")
    evidence_json = json.dumps(evidence, indent=2, sort_keys=True, ensure_ascii=False)
    return template.replace("{{EVIDENCE_JSON}}", evidence_json)


def script_hash() -> str:
    return sha256_file(Path(__file__).resolve())


def interpretation_components(
    *,
    evidence: dict[str, Any],
    prompt_template: Path,
    rendered_prompt: str,
    model: str,
    temperature: str,
) -> dict[str, Any]:
    return {
        "enabled": True,
        "input_hashes": {key: hash_json(value) for key, value in sorted(evidence.items())},
        "comparative_input_hash": hash_json(evidence),
        "prompt_template": prompt_template.name,
        "prompt_template_hash": sha256_file(prompt_template),
        "rendered_prompt_hash": sha256_text(rendered_prompt),
        "model": model,
        "temperature": temperature,
        "script": "scripts/interpret_public_comparison.py",
        "script_hash": script_hash(),
    }


def output_paths(args: argparse.Namespace) -> tuple[Path, Path, Path]:
    return (
        args.output or (args.comparative_dir / "interpretation.md"),
        args.metadata_output or (args.comparative_dir / "interpretation.json"),
        args.prompt_output or (args.comparative_dir / "interpretation.prompt.md"),
    )


def prior_metadata(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    data = load_json(path, "comparative interpretation metadata")
    if not isinstance(data, dict):
        fail(f"comparative interpretation metadata must be a JSON object: {path}")
    return data


def run_model(args: argparse.Namespace, prompt: str) -> str:
    modes = [args.dry_run, args.response_file is not None, args.runner_command is not None]
    if sum(1 for mode in modes if mode) != 1:
        fail("choose exactly one of --dry-run, --response-file, or --runner-command")
    if args.response_file is not None:
        try:
            return args.response_file.read_text(encoding="utf-8")
        except FileNotFoundError:
            fail(f"response file not found: {args.response_file}")
    if args.runner_command is not None:
        command = shlex.split(args.runner_command)
        if not command:
            fail("runner-command must not be empty; expected a command that reads prompt on stdin")
        env = dict(os.environ)
        env["PUBLIC_RESULTS_MODEL"] = args.model
        result = subprocess.run(
            command,
            input=prompt,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
            timeout=1800,
            check=False,
        )
        if result.returncode != 0:
            fail(f"runner-command failed with exit code {result.returncode}: {result.stderr.strip()}")
        return result.stdout
    raise AssertionError("dry-run should be handled before run_model")


def validate_response(text: str) -> None:
    if not text.strip():
        fail("model response was empty")
    for marker in FORBIDDEN_TEXT_MARKERS:
        if marker in text:
            fail(f"unsafe text marker {marker!r} in comparative interpretation output")
    missing = [heading for heading in REQUIRED_HEADINGS if heading not in text]
    if missing:
        fail(f"comparative interpretation output missing required headings: {', '.join(missing)}")


def metadata_record(
    *,
    status: str,
    fingerprint: str,
    components: dict[str, Any],
    output: Path,
    output_sha256: str | None,
    reason: str | None = None,
) -> dict[str, Any]:
    record: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "fingerprint": fingerprint,
        "components": components,
        "output": output.name,
        "output_sha256": output_sha256,
        "created_at": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    if reason:
        record["reason"] = reason
    return record


def main() -> int:
    args = parse_args()
    require_comparative_dir(args.comparative_dir)
    output, metadata_output, prompt_output = output_paths(args)
    evidence = load_evidence(args.comparative_dir)
    prompt = render_prompt(args.prompt, evidence)
    components = interpretation_components(
        evidence=evidence,
        prompt_template=args.prompt,
        rendered_prompt=prompt,
        model=args.model,
        temperature=args.temperature,
    )
    fingerprint = hash_json(components)

    if args.dry_run:
        write_text(prompt_output, prompt)
        write_json(
            metadata_output,
            metadata_record(
                status="dry_run",
                fingerprint=fingerprint,
                components=components,
                output=output,
                output_sha256=None,
                reason="prompt_written_without_model_call",
            ),
        )
        print(json.dumps({"status": "dry_run", "prompt": str(prompt_output)}, sort_keys=True))
        return 0

    previous = prior_metadata(metadata_output)
    if not args.force and previous is not None and previous.get("fingerprint") == fingerprint and output.exists():
        write_json(
            metadata_output,
            metadata_record(
                status="skipped",
                fingerprint=fingerprint,
                components=components,
                output=output,
                output_sha256=sha256_file(output),
                reason="interpretation_fingerprint_unchanged",
            ),
        )
        print(json.dumps({"status": "skipped", "output": str(output)}, sort_keys=True))
        return 0

    response = run_model(args, prompt)
    validate_response(response)
    write_text(output, response.rstrip() + "\n")
    write_json(
        metadata_output,
        metadata_record(
            status="completed",
            fingerprint=fingerprint,
            components=components,
            output=output,
            output_sha256=sha256_file(output),
        ),
    )
    print(json.dumps({"status": "completed", "output": str(output)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
