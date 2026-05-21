---
date: 2026-05-20
topic: middens-session-archive
source_docs:
  - todos/session-log-backup-archive.md
status: draft
---

# NLSpec: `middens archive` — local session log backup

## 1. Why

Agent session logs are research material and, annoyingly, also perishable. Claude Code already clears session history after roughly a month; Codex and other local agent tools may do the same now or later. `middens` analyses raw transcripts, so losing the local JSONL files quietly damages the corpus.

This feature adds a deliberately boring archive path: discover local agent session stores, copy raw logs into a user-chosen archive directory, deduplicate by content hash, and write a manifest that makes later analysis reproducible.

Because the archived files are raw private transcripts, the command must bias toward explicit consent and loud failure over convenience. No implicit archive location. No source mutation. No silent manifest repair. No cute guesses. This is private-data plumbing; cute is how you end up explaining yourself to future you.

## 2. What

### 2.1 Command surface

```text
middens archive
    --to ARCHIVE_ROOT                  # required; no default for v1
    [--source SOURCE]                  # repeatable; default = all known source dirs
    [--from SOURCE_ROOT]               # explicit source root; requires exactly one --source
    [--dry-run]                        # discover + plan only; writes nothing
    [--yes]                            # required for non-dry-run copying
    [--require-parseable]              # fail if any discovered file cannot be parsed
```

`SOURCE` is a clap value enum with these v1 slugs:

- `claude-code` → default root `~/.claude/projects`
- `codex` → default root `~/.codex/sessions`
- `pi-coding-agent` → default root `~/.pi/agent/sessions`
- `openclaw` → default root `~/openclaw-sessions`
- `gemini` → default root `~/.gemini/history` *(archival supported; parser enrichment is best-effort and may record `parser_status = failed` until Gemini parsing graduates from stub-land)*

`--to` is required in v1. There is intentionally no XDG default archive location: copying raw private transcripts should only happen after the user names the destination.

`--manifest-only` is **not** part of v1. It is too easy to read as either "record what would be archived" or "rebuild an existing archive index". A future `middens archive verify` / `middens archive rebuild-index` can handle that with less ambiguity.

### 2.2 Discovery rules

1. With no `--source`, inspect all known default roots listed above.
2. Missing default roots are reported as `not present` and are not errors; people should not fail a backup because they never installed Gemini.
3. If a default root exists but cannot be read, fail non-zero. Existing-but-unreadable means "we may have skipped real logs", not "shrug".
4. With `--source SOURCE`, inspect only that source's default root.
5. If an explicitly requested source root is missing, fail clearly and show both the expected default and a concrete override example:

   ```text
   source 'claude-code' was requested, but /Users/alice/.claude/projects does not exist.
   Expected a readable directory of .jsonl session logs.
   Example: middens archive --source claude-code --from /path/to/projects --to /path/to/archive --dry-run
   ```

6. `--from SOURCE_ROOT` overrides the source root and requires exactly one `--source`; otherwise source attribution is ambiguous and the command fails at parse/config-validation time.
7. Only regular `.jsonl` files are archive candidates in v1.
8. Walks follow file and directory symlinks. The archived bytes are the target file bytes. Manifest observations record both the path encountered during discovery and the canonical path when canonicalisation succeeds. Symlink loops or broken symlinks fail with a clear path-specific error.
9. The archive root must not be equal to, inside, or above any source root being scanned. If source and destination overlap, fail before any write. Archiving the archive because it happened to be under `~/.claude/projects` would be impressive, but not helpful.

### 2.3 Privacy and consent UX

- Non-dry-run requires `--yes`. Without it, the command prints the privacy warning and exits non-zero before creating the archive directory.
- Dry-run never requires `--yes` and writes nothing: no archive root, no manifest, no lock file, no `.gitignore`.
- Every non-dry-run prints a visible stderr warning before copying:

  ```text
  WARNING: middens archive copies raw agent session transcripts, including prompts,
  tool outputs, paths, and possibly secrets, into <ARCHIVE_ROOT>.
  Keep this directory private. Re-run with --dry-run to inspect the plan first.
  ```

- If `ARCHIVE_ROOT` is inside a Git worktree, non-dry-run ensures `ARCHIVE_ROOT/.gitignore` exists with deny-all contents:

  ```gitignore
  *
  !.gitignore
  ```

  If `.gitignore` already exists, leave it untouched and warn if it does not contain a blanket ignore rule. Do not edit user-authored ignore files silently.

### 2.4 Archive layout

Archive layout is deterministic and collision-resistant:

```text
archive-root/
  .gitignore                         # created only when archive is inside a git worktree
  manifest.json
  objects/
    sha256/
      ab/
        abcd...fullsha256....jsonl   # raw bytes, exactly one copy per content hash
  indexes/
    sessions.jsonl                   # derived convenience index; rebuildable from manifest
```

Rationale: the initial sketch used `by-tool/<tool>/yyyy/mm/<short-hash>-<basename>.jsonl`. That is pleasant to browse, but global deduplication by hash is simpler and safer when the same bytes appear under multiple tools or paths. The manifest provides the by-tool and original-path views. A future `archive browse` can build friendlier indexes without risking duplicate raw files.

Destination object path:

```text
objects/sha256/<sha256[0..2]>/<sha256>.jsonl
```

If that destination exists and its bytes hash to the same SHA-256, it is reused. If it exists and hashes differently, fail loudly with `destination collision` and do not update the manifest. A real SHA-256 collision is not the threat model; partial/corrupt files and hand-edited archives are.

### 2.5 Manifest schema

`manifest.json` is canonical. `indexes/sessions.jsonl` is derived and may be regenerated from the manifest.

```text
RECORD ArchiveManifest:
  archive_manifest_version: 1
  created_at: Timestamp
  updated_at: Timestamp
  middens_version: String
  archive_root: String                 # absolute path at write time
  objects: Map<Sha256Hex, ArchivedObject>
  observations: List<SourceObservation>

RECORD ArchivedObject:
  sha256: String                        # full lowercase hex
  size_bytes: UInt64
  archive_path: String                  # relative to archive_root
  first_archived_at: Timestamp
  parser_status: ParserStatus
  parser_error: Option<String>          # short diagnostic; no raw transcript text
  source_tool: String                   # tool of first observation for this object
  session_count: UInt64
  session_ids: List<String>
  first_timestamp: Option<Timestamp>
  last_timestamp: Option<Timestamp>

RECORD SourceObservation:
  observation_id: String                # sha256(original_path + canonical_path + source_tool + sha256)
  source_tool: String
  original_path: String                 # path encountered during discovery
  canonical_path: Option<String>
  original_basename: String
  archive_path: String                  # same as ArchivedObject.archive_path
  sha256: String
  size_bytes: UInt64
  source_mtime: Timestamp
  observed_at: Timestamp

ENUM ParserStatus:
  parsed
  unparseable
  empty_placeholder
  parser_error
```

Manifest invariants:

- `objects` has one entry per unique content hash.
- `observations` has one entry per discovered source-file occurrence.
- Re-running the same archive command does not append duplicate observations.
- Same source path with changed content is recorded as a new observation pointing at a new object; the old object remains.
- Parser metadata is best-effort unless `--require-parseable` is set.
- Parser errors must not include raw transcript content. File paths and parser names are okay; line payloads are not.

### 2.6 Copy and update semantics

1. Acquire an archive lock before any write by creating `archive-root/.archive.lock` with `create_new`. If it already exists, fail with a message saying another archive run may be active and showing the lock path. Remove the lock on normal exit. If a stale lock is suspected, the user deletes it; v1 does not guess.
2. Load existing `manifest.json` if present. If it is corrupt or schema-invalid, fail before copying. Do not repair, overwrite, or quarantine it silently.
3. Validate manifest drift before copying: every `ArchivedObject.archive_path` in the manifest must exist and hash to its recorded SHA-256. If not, fail with `archive drift detected` and name the missing/corrupt object. Do not continue into a half-trusted archive.
4. Discover candidate `.jsonl` files, sorted lexicographically by `(source_tool_slug, original_path)` for deterministic planning.
5. For each candidate:
   - Record source metadata before reading: size and mtime.
   - Compute SHA-256 by streaming bytes.
   - Copy only if the object hash is not already present.
   - Copy to a temp file in the destination object directory, then atomically rename to the final object path.
   - Re-read source metadata after hashing/copying. If size or mtime changed during the operation, fail with `source changed while archiving; retry` and do not update the manifest for that file.
   - Parse/enrich metadata using the existing parser stack. Parse failure records `parser_status = parser_error` or `unparseable` unless `--require-parseable` is set, in which case the whole command fails before manifest update.
6. Build the new manifest in memory.
7. Write `manifest.json.tmp-<uuid>` in `archive-root/`, flush it, then atomically rename over `manifest.json`.
8. Write `indexes/sessions.jsonl` from the same in-memory manifest via the same temp-file-then-rename pattern. If index writing fails after manifest success, fail loudly; the manifest remains canonical and the next run may regenerate the index after passing drift checks.

Source logs are never opened for writing, deleted, truncated, renamed, chmodded, or rewritten. Reading may update filesystem access time on systems that still track atime; that is not considered source mutation for this contract.

### 2.7 Parser coupling

Archiving raw bytes does **not** require parsing to succeed.

- Parseable files get session metadata enrichment: session IDs and first/last timestamps.
- Empty files are archived with `parser_status = empty_placeholder`.
- Files with no matching parser are archived with `parser_status = unparseable`.
- Files where a parser matches but errors are archived with `parser_status = parser_error` and a short diagnostic.
- `--require-parseable` turns `unparseable`, `empty_placeholder`, and `parser_error` into hard failures before any manifest update.

The implementation may use `parser::detect_format`, `parser::parse_auto`, and the existing `Session` model, but must preserve the distinction between "no parser matched" and "parser matched but failed" in the archive manifest. If current parser helpers collapse those cases, add a small archive-specific probe rather than weakening the manifest.

## 3. How

### 3.1 Code areas inspected

Relevant existing code before drafting:

- `middens/src/corpus/discovery.rs` — default roots and recursive `.jsonl` discovery; currently returns an empty set for missing explicit paths, which is too quiet for archive.
- `middens/src/parser/auto_detect.rs` — cheap source detection and `parse_auto` dispatch; useful but currently collapses no-parser cases into `Ok(vec![])`.
- `middens/src/corpus/manifest.rs` — SHA-256 streaming helper and older freeze manifest shape.
- `middens/src/storage/mod.rs` and `middens/src/storage/discovery.rs` — manifest models, XDG helpers, but no reusable atomic JSON writer yet.
- `middens/src/main.rs` / `middens/src/commands/` — command wiring pattern for `interpret` and `export`.

Local default roots were present on the drafting machine for all five known tools (`~/.claude/projects`, `~/.codex/sessions`, `~/.gemini/history`, `~/.pi/agent/sessions`, `~/openclaw-sessions`). This confirms the paths are real enough to spec, not just vibes in a trench coat.

### 3.2 Suggested module structure

```text
middens/src/archive/
  mod.rs
  discover.rs        # source enum, default roots, candidate discovery, symlink policy
  manifest.rs        # ArchiveManifest structs + load/validate/write
  copy.rs            # hash/copy/temp-rename primitives
  parse.rs           # parser enrichment wrapper preserving status distinctions
  plan.rs            # dry-run and execution plan structs
middens/src/commands/archive.rs
middens/src/main.rs  # Commands::Archive wiring
```

Keep `archive` separate from `corpus::discovery`: analysis discovery is allowed to be forgiving and skip unknowns; backup discovery must be more paranoid.

### 3.3 Implementation notes

- Reuse existing dependencies: `sha2`, `walkdir`, `chrono`, `serde`, `serde_json`, `anyhow`, `tempfile`, `uuid7` if a temp suffix is needed.
- Add `ArchiveSource` as a clap `ValueEnum` in command code or an archive module; map to `SourceTool` for parser enrichment.
- Use absolute archive root paths in command output and manifest metadata.
- Make dry-run produce an execution plan with counts: candidates discovered, objects to copy, duplicates, observations to add, parseable/unparseable counts if parser probing is performed during dry-run.
- Dry-run may read source files to hash and parse them, because "exact planned actions" requires knowing duplicates. It must not write.
- Keep terminal output summary-oriented by default. Full per-file plans are acceptable for dry-run because the contract says exact planned actions; avoid printing raw transcript content.
- Add unit tests for manifest validation and path-overlap rejection; add Cucumber coverage for user-visible CLI behaviour.

### 3.4 Adversarial process

This feature touches raw private transcripts, so use the full split process:

1. Orchestrator drafts this NLSpec and pauses for review.
2. Review/deepen the NLSpec before dispatch.
3. **Red team** writes Cucumber feature files from sections 1, 2, 4, 5, and 6 only. Red does not see section 3 (`How`).
4. Orchestrator resolves contract gaps by amending the NLSpec, not by editing tests to match an implementation.
5. **Green team** implements from section 3 plus the public command contract, without seeing test source.
6. Orchestrator routes failures back as behavioural feedback only: what failed and what the expected user-visible behaviour is, not the exact assertion code.
7. Iterate until all archive scenarios pass, then run full `cd middens && cargo test`.

Natural PR boundary: first PR can add `archive` with manifest + copy + dry-run. Parser enrichment is part of v1, but `--require-parseable` can be the last slice inside the same PR.

## 4. Done

Acceptance criteria below are intentionally testable. Red team should convert these into Cucumber scenarios and lower-level tests as appropriate.

1. **`--to` is required.** `middens archive --dry-run` exits non-zero with a clear message that archive destination is required and an example: `middens archive --to ~/agent-session-archive --dry-run`.
2. **Dry-run writes nothing.** Given fixture source roots and a nonexistent archive root, `middens archive --to <archive> --source claude-code --from <fixture> --dry-run` discovers fixture files, prints the planned copies/dedupes, exits 0, and leaves `<archive>` nonexistent.
3. **Non-dry-run requires consent.** Without `--yes`, `middens archive --to <archive> --source claude-code --from <fixture>` prints the raw-transcript privacy warning, exits non-zero, and writes nothing.
4. **Privacy warning is visible when copying.** With `--yes`, the same command prints the warning to stderr before copying and exits 0.
5. **Archive run copies bytes exactly.** A fixture `.jsonl` is copied to `objects/sha256/<prefix>/<full-sha>.jsonl`; the archived object hash and byte contents match the source exactly.
6. **Manifest contains required fields.** After a successful run, `manifest.json` parses and contains `archive_manifest_version`, `created_at`, `updated_at`, `middens_version`, `archive_root`, one `objects` entry, and one `observations` entry with source tool, original path, basename, archive path, SHA-256, size, mtime, archived/observed timestamps, parser status, session count, session IDs, and first/last timestamps when parseable.
7. **Index is derived.** `indexes/sessions.jsonl` exists after a successful run and contains one line per archived observation or parsed session according to the final implementation choice documented in the manifest module. Its records reference manifest object hashes, not independent raw paths.
8. **Re-running is idempotent.** Running the same archive command twice reports `0 copied` on the second run, does not duplicate manifest observations, and leaves the object file unchanged.
9. **Same-content duplicate is deduped.** Two fixture source files with identical bytes but different paths produce one object and two observations pointing at the same archive path.
10. **Changed source path records a new object.** If a source path is archived, then its contents change, a later run records a new observation and object for the new hash without overwriting or deleting the old object.
11. **Destination collision fails clearly.** If the computed object destination already exists but its bytes hash differently from its filename/manifest hash, the command exits non-zero with `destination collision`, does not update the manifest, and does not overwrite the existing file.
12. **Source files are not mutated.** Before/after hashes of all fixture source files are identical after a successful archive run. The command never deletes, truncates, renames, or rewrites source files.
13. **Corrupt existing manifest fails.** If `manifest.json` exists but is invalid JSON or schema-invalid, archive exits non-zero naming the corrupt manifest and copies no files.
14. **Archive drift fails.** If the manifest references an archived object that is missing or hashes differently, archive exits non-zero with `archive drift detected` before copying new files.
15. **Unparseable files are still archived by default.** A syntactically valid `.jsonl` file with no matching parser is copied, appears in the manifest with `parser_status = unparseable`, and the command exits 0.
16. **Parser errors do not leak content.** A parser-matched-but-invalid fixture records `parser_status = parser_error` and a diagnostic that names the parser/file but does not include raw line payload text.
17. **`--require-parseable` is strict.** With an unparseable fixture, `middens archive --require-parseable --yes ...` exits non-zero before manifest update and copies no files.
18. **`--source` limits discovery.** With Claude and Codex fixture roots present, `--source codex` archives only Codex candidates and reports zero Claude candidates.
19. **`--from` requires one source.** `--from <dir>` without `--source`, or with multiple `--source` flags, fails at config validation with the expected form and an example.
20. **Explicit missing source fails helpfully.** `--source claude-code --from <missing>` fails with a message saying the path does not exist, that a readable directory of `.jsonl` logs was expected, and showing a corrected example.
21. **Unreadable source fails helpfully.** An existing but unreadable source directory fails non-zero and names the unreadable directory. On platforms where permissions cannot be made unreadable in tests, this scenario may be marked Unix-only.
22. **Symlinked files archive target bytes.** A symlinked `.jsonl` fixture is archived by hashing/copying the target bytes, while the observation records both original symlink path and canonical target path.
23. **Symlink loops fail clearly.** A source tree containing a symlink loop exits non-zero naming the loop path and writes no manifest update.
24. **Overlapping source and archive roots are rejected.** If `--to` is inside `--from`, equal to `--from`, or an ancestor of `--from`, archive fails before any writes with a message explaining that source and archive roots must not overlap.
25. **Manifest writes are atomic.** A test hook that interrupts before final manifest rename leaves either the previous valid `manifest.json` or no manifest at all, never a truncated final manifest.
26. **Object writes are atomic.** A test hook that interrupts during object copy leaves no final object path with partial bytes; temporary files may remain and are ignored or cleaned on the next run.
27. **Lock prevents concurrent writers.** If `.archive.lock` already exists, archive exits non-zero naming the lock and performs no writes.
28. **Git worktree safety.** When archive root is inside a git worktree and no archive `.gitignore` exists, non-dry-run creates a deny-all `.gitignore`. If one exists, it is not overwritten.
29. **Default discovery tolerates absent tools.** With only one known default source root present, `middens archive --to <archive> --yes` archives that source and reports other roots as not present; absence of uninstalled tools is not an error.
30. **Existing unreadable default root is an error.** With no explicit source, if a known default root exists but is unreadable, archive fails rather than silently skipping it.

## 5. Non-goals

- No cloud upload, sync, encryption, compression, or remote backup integration in v1.
- No deletion, pruning, or retention policy for the archive.
- No automatic archive location.
- No `--manifest-only` / rebuild-index mode in v1.
- No attempt to redact, transform, or normalise raw transcripts during archive. The raw object is a byte-for-byte copy.
- No guarantee that parser enrichment succeeds for every supported source. Archival is primary; parsing is metadata enrichment.
- No Windows-specific default roots in v1. The code should avoid gratuitous Unix assumptions where easy, but the supported/tested release targets are macOS and Linux.

## 6. Open questions

1. Should `indexes/sessions.jsonl` be one line per source observation or one line per parsed session? The manifest is clear either way; implementation should pick one before red-team tests are finalised. Recommendation: one line per parsed session when parseable, plus one fallback line per unparseable observation.
2. Should archive support a future `--encrypt` flag or explicitly delegate encryption to the user's filesystem/backups? Recommendation for v1: delegate and document.
3. Should source defaults include OpenCode if/when a parser lands? Not in v1 unless a parser-backed source root is confirmed.
4. Should stale lock detection include lock age? Recommendation for v1: no. Stale lock auto-break logic is how two writers become one exciting bug.
5. Should terminal output redact home directories by default? Current spec prints exact paths for dry-run/actionability. If this becomes too noisy or risky in shared logs, add `--redact-paths` later.
