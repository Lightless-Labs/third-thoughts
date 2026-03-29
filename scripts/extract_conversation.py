#!/usr/bin/env python3
"""Extract readable conversation from Claude Code JSONL session files.

Usage: python3 extract_conversation.py <session.jsonl> [--max-chars 50000] [--include-tools]
"""
import json
import sys
import argparse

def extract(path, max_chars=50000, include_tools=False):
    lines = []
    total_chars = 0

    with open(path) as f:
        for raw_line in f:
            try:
                record = json.loads(raw_line)
            except json.JSONDecodeError:
                continue

            if record.get("type") not in ("user", "assistant"):
                continue

            msg = record.get("message", {})
            role = msg.get("role", record.get("type", "?"))
            content = msg.get("content", "")

            # Handle string content
            if isinstance(content, str):
                text = content.strip()
                if text:
                    lines.append(f"\n## {role.upper()}\n\n{text}")
                    total_chars += len(text)

            # Handle array content (assistant messages)
            elif isinstance(content, list):
                parts = []
                for block in content:
                    if block.get("type") == "text" and block.get("text", "").strip():
                        parts.append(block["text"].strip())
                    elif block.get("type") == "thinking" and block.get("thinking", "").strip():
                        # Truncate thinking to first 500 chars
                        thinking = block["thinking"].strip()
                        if len(thinking) > 500:
                            thinking = thinking[:500] + "... [truncated]"
                        parts.append(f"<thinking>{thinking}</thinking>")
                    elif block.get("type") == "tool_use" and include_tools:
                        name = block.get("name", "?")
                        inp = block.get("input", {})
                        # Summarize tool use
                        if name in ("Read", "Glob", "Grep"):
                            parts.append(f"[Tool: {name} — {inp.get('file_path', inp.get('pattern', '?'))}]")
                        elif name == "Bash":
                            cmd = inp.get("command", "?")
                            if len(cmd) > 200:
                                cmd = cmd[:200] + "..."
                            parts.append(f"[Tool: Bash — {cmd}]")
                        elif name == "Edit":
                            parts.append(f"[Tool: Edit — {inp.get('file_path', '?')}]")
                        elif name == "Write":
                            parts.append(f"[Tool: Write — {inp.get('file_path', '?')}]")
                        else:
                            parts.append(f"[Tool: {name}]")

                if parts:
                    text = "\n".join(parts)
                    lines.append(f"\n## {role.upper()}\n\n{text}")
                    total_chars += len(text)

            if total_chars >= max_chars:
                lines.append(f"\n\n--- [Truncated at {max_chars} chars] ---")
                break

    return "\n".join(lines)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("file", help="JSONL session file")
    parser.add_argument("--max-chars", type=int, default=50000)
    parser.add_argument("--include-tools", action="store_true")
    args = parser.parse_args()

    print(extract(args.file, args.max_chars, args.include_tools))
