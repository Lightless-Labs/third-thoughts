Findings ordered by severity:

1. **High — existing `.gitignore` can leave raw transcript archives commit-visible**
   - **Files:** all bundled copies:
     - `integrations/pi/middens-archive/scripts/archive.mjs:328-333`
     - `integrations/claude-code/middens-archive/scripts/archive.mjs:328-333`
     - `integrations/codex/middens-archive/scripts/archive.mjs:328-333`
   - **Evidence:** `writeGitignoreIfInsideWorktree()` only writes `*\n!.gitignore\n` when `.gitignore` does not already exist:
     ```js
     if (!(await exists(gitignore))) await writeFile(gitignore, "*\n!.gitignore\n", "utf8");
     ```
     If the archive root is inside a git worktree and already has a non-protective `.gitignore`, raw `objects/sha256/**/*.jsonl`, `manifest.json`, and `indexes/sessions.jsonl` may be git-visible.
   - **Fix:** If `.gitignore` exists, verify it contains an effective blanket ignore for the archive root; otherwise fail loudly or append a managed block atomically. Do not silently proceed for automatic hooks.

2. **High — Pi extension often never archives short sessions**
   - **File:** `integrations/pi/middens-archive/extensions/middens-archive.ts:106-112, 194-224`
   - **Evidence:** `session_start` only schedules a timer; it does not run an initial archive. `session_shutdown` is not forced and `shouldRunConfigured()` treats `sessionStartedAt` as recent activity:
     ```ts
     const lastActivityAt = Math.max(lastStartedAt, lastFinishedAt, trigger === "shutdown" ? sessionStartedAt : 0);
     return lastActivityAt === 0 || now - lastActivityAt >= config.intervalMs;
     ```
     With the default 60 minutes, a 10-minute Pi session with no manual command exits without any archive.
   - **Fix:** Run an initial debounced archive on `session_start`, and/or make shutdown force a bounded final archive unless another run is active. Do not let `sessionStartedAt` suppress the first archive.

3. **High — source/archive overlap check misses non-existent archive paths behind symlinked parents**
   - **Files:** all bundled `scripts/archive.mjs` copies, e.g. `integrations/pi/middens-archive/scripts/archive.mjs:313-326`; archive root is created later at `:52`.
   - **Evidence:** `checkOverlap()` only calls `realpath(archiveRoot)` directly. If `archiveRoot` does not exist yet, it falls back to the lexical path:
     ```js
     archiveVariants.add(await realpath(archiveRoot).catch(() => archiveRoot));
     ```
     Then `mkdir(archiveRoot)` can create the archive inside the source via a symlinked parent, causing later runs to discover archived `.jsonl` objects as source files.
   - **Fix:** Resolve the nearest existing ancestor and append remaining components, or create/resolve the archive root and re-run overlap validation before discovery. Also exclude the canonical archive root during source walking as a defense-in-depth guard.

4. **Medium — option parser can write archives to unintended paths when values are missing**
   - **Files:** all bundled `scripts/archive.mjs` copies, e.g. `integrations/pi/middens-archive/scripts/archive.mjs:154-160`
   - **Evidence:** options consume the next argv element without validation:
     ```js
     if (arg === "--source") out.source = argv[++i];
     else if (arg === "--to") out.archiveRoot = argv[++i];
     else if (arg === "--from") out.sourceRoot = argv[++i];
     ```
     `--to --quiet` is accepted as archive root `--quiet`, so raw logs can be written to an unintended relative directory.
   - **Fix:** Add a `readOptionValue("--to")` helper that rejects missing values and flag-looking values; fail with an example instead of coercing.

5. **Medium — Pi archive metadata is not compatible with `middens archive` session counts**
   - **Files:** all bundled `scripts/archive.mjs` copies; especially affects Pi source. Example:
     - `integrations/pi/middens-archive/scripts/archive.mjs:340-371`
   - **Evidence:** `collectSessionIds()` records any `id` field recursively, then uses the set size as `session_count`:
     ```js
     for (const key of [..., "id"]) ...
     session_count: ids.length || (parsed > 0 ? 1 : 0)
     ```
     Pi JSONL entries have an `id` on every session entry, while `middens`’ Pi parser uses only the session header ID and returns one `Session` per file (`middens/src/parser/pi.rs:135-136, 381-384`; enrichment uses `sessions.len()` in `middens/src/archive/parse.rs:103-104`).
   - **Fix:** Use source-specific enrichment. For Pi, read only the `type:"session"` header ID and set `session_count` to 1 for parseable files.

6. **Low/Medium — manual archive-root docs are misleading**
   - **Files:**
     - `integrations/claude-code/middens-archive/commands/middens-archive-now.md:3,9,14`
     - `integrations/claude-code/middens-archive/README.md:45`
     - `integrations/codex/middens-archive/skills/middens-archive-now/SKILL.md:8,13`
   - **Evidence:** Claude advertises `/middens-archive-now [archive-root]`, but the shell snippet reads a shell variable `ARGUMENTS`, not a safely supplied command argument. Codex says “If the user supplies an archive root, use that,” but the exact shell pattern only reads `MIDDENS_ARCHIVE_ROOT`.
   - **Fix:** Either remove positional archive-root support from docs, or implement it using the agent’s actual argument API with safe quoting. Prefer requiring `MIDDENS_ARCHIVE_ROOT` to avoid injection-prone path interpolation.

7. **Low — Codex install docs omit the hook feature flag used by validation**
   - **File:** `integrations/codex/middens-archive/README.md:28-32`
   - **Evidence:** README says:
     ```bash
     codex plugin marketplace add ./integrations/codex
     ```
     but the recorded validation path used `--enable plugin_hooks`. Users following the README may install skills without active hooks, depending on Codex version/feature gates.
   - **Fix:** Document the required Codex version and include `--enable plugin_hooks` where needed.

8. **Low — no committed regression tests for the bundled archiver/plugin safety cases**
   - **Files:** `integrations/pi/middens-archive/`, `integrations/claude-code/middens-archive/`, `integrations/codex/middens-archive/`
   - **Evidence:** no `*.test.*`, `*.spec.*`, or `test*` files are present under `integrations/`.
   - **Fix:** Add shared fixture tests for missing option values, existing non-protective `.gitignore`, symlinked overlap, drift/collision handling, Pi session-count enrichment, and no-`middens`-on-`PATH` execution.

No confirmed accidental dependency on the `middens` binary was found; the runtime paths invoke bundled `scripts/archive.mjs` rather than `middens archive`. No concrete defect was confirmed in the Claude or Codex marketplace JSON files themselves.

---

## Triage and resolution (2026-05-21)

| # | Severity | Decision | Resolution |
|---|----------|----------|------------|
| 1 | High | Confirmed P1 | Fixed: bundled archiver now appends an atomic managed `.gitignore` block inside git worktrees even when `.gitignore` already exists. |
| 2 | High | Confirmed P1 | Fixed: Pi extension now starts an immediate automatic run on session start and forces a bounded shutdown run. |
| 3 | High | Confirmed P1 | Fixed: overlap checks canonicalize the nearest existing ancestor, then re-run after archive-root creation. |
| 4 | Medium | Confirmed P2 | Fixed opportunistically: option values now reject missing or flag-looking values with a clear example. |
| 5 | Medium | Confirmed P2 | Fixed opportunistically: Pi enrichment reads only the Pi session header ID for `session_count`/`session_ids`. |
| 6 | Low/Medium | Confirmed P2 | Fixed opportunistically: Claude/Codex manual docs now require `MIDDENS_ARCHIVE_ROOT` instead of ambiguous positional roots. |
| 7 | Low | Confirmed P3 | Fixed opportunistically: Codex README includes `--enable plugin_hooks`. |
| 8 | Low | Confirmed P2 follow-up | Filed `todos/archive-plugin-regression-tests.md`; manual smokes were run for the fixed cases in-session. |

Validation after fixes:

- `cd integrations/pi/middens-archive && npm run check` — pass.
- Manual Node smoke: missing `--to` value fails clearly without a stack trace.
- Manual Node smoke: existing `.gitignore` inside a git worktree receives a protective managed block.
- Manual Node smoke: Pi fixture with one session header and multiple entry IDs archives as `session_count: 1` with the header ID.
- Manual Node smoke: symlinked-parent source/archive overlap is rejected.
- `claude plugin validate integrations/claude-code/middens-archive` — pass.
- `claude plugin validate integrations/claude-code` — pass.
- Temp-home `codex plugin marketplace add ./integrations/codex --enable plugin_hooks` — pass.
- Pi extension `/middens-archive-status` smoke with temp `HOME`/`PI_CODING_AGENT_DIR` and unset archive root — pass.
