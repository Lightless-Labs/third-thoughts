---
title: "Homebrew tap for middens"
status: done
priority: P1
tags: [distribution, homebrew, workstream-3]
source: user-direction-2026-04-10
---

## What

Create a Homebrew tap (`Lightless-Labs/homebrew-tap` or similar) with a formula for `middens`.

## Steps

1. ~~GitHub release workflow producing cross-platform binaries.~~ Done for the supported beta matrix: `darwin-arm64`, `linux-x86_64`, `linux-arm64`. Intel macOS was intentionally dropped after runner starvation.
2. ~~Create the tap repo with a formula that downloads the release binary + verifies SHA256.~~ Done: <https://github.com/Lightless-Labs/homebrew-tap>.
3. ~~`brew install lightless-labs/tap/middens` should Just Work.~~ Validated on Apple Silicon macOS via the public tap.
4. Full source-built vs brew-installed e2e comparison moved to Step D: `todos/distribution-validation-runs.md`.

## Validation

Completed 2026-04-27 on Apple Silicon macOS:

```bash
brew audit --strict --new --online lightless-labs/tap/middens
brew style lightless-labs/tap/middens
brew uninstall middens
brew untap lightless-labs/tap
brew tap lightless-labs/tap
brew install --formula lightless-labs/tap/middens --without-uv
brew test lightless-labs/tap/middens
brew uninstall middens
brew install --formula lightless-labs/tap/middens
brew test lightless-labs/tap/middens
brew deps --declared --formula lightless-labs/tap/middens --annotate  # uv [recommended]
```

`--without-uv` was used to verify that `uv` is recommended rather than required. The exact default install path was then validated separately; it installed Homebrew's `uv` bottle as a recommended dependency.

## Notes

- Homebrew is the primary distribution channel (target audience is researchers, not Rust devs).
- crates.io publish is secondary — can happen in parallel but isn't the critical path.
- The formula handles the Python bridge gracefully: `uv` is a recommended runtime dependency, not a hard dependency.
