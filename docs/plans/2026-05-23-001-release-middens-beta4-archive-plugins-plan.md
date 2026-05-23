# Release middens v0.0.1-beta.4 with archive plugin distribution notes

**Created:** 2026-05-23
**Completed:** 2026-05-23

## Why

`middens archive` and the self-contained Pi / Claude Code / Codex archive plugins are now implemented, reviewed by Codex 5.5 xhigh via Pi, hardened, and covered by regression tests. That is enough moving parts around raw transcripts that a named beta release is preferable to pointing users at a random `main` commit and hoping they enjoy archaeology in the bad way.

## What

Cut `v0.0.1-beta.4` as the first release that explicitly advertises session-log archiving and the three automation plugins.

Scope:

- Bump the Rust crate version from `0.0.1-beta.3` to `0.0.1-beta.4`.
- Refresh release-facing docs and examples from beta.3 to beta.4.
- Add concise archive-plugin install/distribution notes with privacy warnings.
- Run release validation gates.
- Tag and push `v0.0.1-beta.4` to trigger the existing GitHub release workflow.
- After artifacts exist, update the Homebrew tap formula to beta.4 and validate install/audit.

## How

1. Update docs and metadata:
   - `middens/Cargo.toml` / `middens/Cargo.lock` version.
   - root `README.md` release tarball examples.
   - `middens/README.md` status and release tarball examples.
   - archive plugin docs/links as needed.
2. Validate locally:
   - `cd middens && cargo test`.
   - `cd middens && cargo build --release --locked`.
   - `cd integrations/pi/middens-archive && npm test`.
   - `cd integrations/pi/middens-archive && npm run check`.
3. Commit docs/version updates.
4. Tag and push `v0.0.1-beta.4`.
5. Watch release workflow; if green, update `Lightless-Labs/homebrew-tap` checksums and validate.
6. Update `docs/HANDOFF.md` with release outcome and next action.

## Done

- [x] Version metadata says `0.0.1-beta.4`.
- [x] Release-facing README snippets point at `v0.0.1-beta.4`.
- [x] Archive plugin distribution notes are visible from the main docs.
- [x] Local validation gates pass.
- [x] `v0.0.1-beta.4` tag is pushed and GitHub release workflow succeeds.
- [x] Homebrew tap is updated and validated, or a clear blocker is documented.
- [x] `docs/HANDOFF.md` is updated.
