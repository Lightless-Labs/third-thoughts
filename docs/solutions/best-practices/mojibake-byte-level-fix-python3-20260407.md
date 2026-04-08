---
module: corpus-hygiene
date: 2026-04-07
problem_type: best_practice
component: tooling
severity: medium
tags: [encoding, mojibake, python, utf-8, unicode]
applies_when:
  - a file contains mojibake sequences like `â€™`, `Ã©`, `â€œ`
  - the file was decoded as latin-1 and re-encoded as utf-8 somewhere upstream
  - `sed` refuses to touch multi-byte sequences correctly
---

# Fix mojibake with a byte-level Python3 replace, not sed

## Context

Mojibake happens when UTF-8 bytes are interpreted as Latin-1 (or cp1252), then re-encoded as UTF-8 — the original `'` (`E2 80 99`) becomes `â€™` (`C3 A2 E2 82 AC E2 84 A2`). `sed` operates on text and gets confused by the multi-byte sequences; `iconv` only works if the whole file is consistently mis-encoded; `ftfy` handles it but isn't always available.

The cleanest minimal fix is a byte-level Python3 one-liner using the known mojibake sequence as bytes.

## Guidance

```bash
python3 -c '
import sys
p = sys.argv[1]
data = open(p, "rb").read()
# Map each mojibake byte sequence to its intended UTF-8 byte sequence.
fixes = {
    b"\xc3\xa2\xe2\x82\xac\xe2\x84\xa2": b"\xe2\x80\x99",  # ’
    b"\xc3\xa2\xe2\x82\xac\xc5\x93":     b"\xe2\x80\x9c",  # “
    b"\xc3\xa2\xe2\x82\xac\xc2\x9d":     b"\xe2\x80\x9d",  # ”
    b"\xc3\xa9":                          b"\xc3\xa9",     # é (already ok — sentinel)
}
for bad, good in fixes.items():
    data = data.replace(bad, good)
open(p, "wb").write(data)
' path/to/file.md
```

If the whole file is uniformly double-encoded, the single-shot fix is:

```python
# decode as utf-8, re-encode to latin-1, decode again as utf-8
open(p, "wb").write(open(p, "rb").read().decode("utf-8").encode("latin-1").decode("utf-8").encode("utf-8"))
```

## Why This Matters

- `sed -i 's/â€™/'"'"'/g'` relies on your terminal locale matching the file's encoding — it fails silently on mixed files.
- Byte-level replace is deterministic and reviewable in a diff.
- Explicit byte sequences in the fix table make the intent auditable — a reviewer can see exactly which mojibake forms you're correcting.
- Using `ftfy` is better when available, but requires a dependency. The Python3 stdlib approach is hermetic.

## When to Apply

- After pasting content from a source that double-encoded UTF-8 (some email clients, old forum exports, CSVs from Excel)
- When a file has only a handful of known mojibake forms
- When `sed` is producing wrong output or refusing to match

## Examples

Single-file fix used during this session on a corpus handoff doc:

```bash
python3 -c 'import sys; p=sys.argv[1]; d=open(p,"rb").read().replace(b"\xc3\xa2\xe2\x82\xac\xe2\x84\xa2", b"\xe2\x80\x99"); open(p,"wb").write(d)' docs/HANDOFF.md
```

Verify with `file` and a round-trip read:

```bash
file docs/HANDOFF.md   # should report: UTF-8 Unicode text
python3 -c 'open("docs/HANDOFF.md").read()'  # must not raise UnicodeDecodeError
```
