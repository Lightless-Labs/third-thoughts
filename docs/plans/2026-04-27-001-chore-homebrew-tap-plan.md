# Chore: Homebrew tap for middens

**Created:** 2026-04-27
**Status:** Completed
**Completed:** 2026-04-27

## Why

`middens` has a beta release and a working release matrix. Researchers should not need a Rust toolchain just to try it; Homebrew is the intended first install path.

## What

Create a `Lightless-Labs/homebrew-tap` repository containing a `middens` formula installable as:

```bash
brew install lightless-labs/tap/middens
```

The formula should install the existing `v0.0.1-beta.0` release artifacts for the supported binary targets:

- `aarch64-apple-darwin`
- `x86_64-unknown-linux-gnu`
- `aarch64-unknown-linux-gnu`

Intel macOS is intentionally not included in the initial tap because the release matrix dropped `macos-13` after runner starvation during the first tag cut.

## How

1. Confirm release asset URLs and SHA256 values from the published GitHub release.
2. Create the tap repository using the standard Homebrew naming convention: `homebrew-tap`.
3. Add `Formula/middens.rb` with:
   - binary URLs for the three supported targets,
   - hard SHA256 checksums,
   - `uv` as a recommended dependency, not a hard dependency,
   - an install step for the release binary,
   - a smoke test using `middens --version`.
4. Validate locally with Homebrew audit/install/test where possible.
5. Update distribution docs/todos/handoff with the result and any validation limits.

## Done

- `brew install lightless-labs/tap/middens` works on Apple Silicon macOS via the public tap.
- Unsupported Intel macOS fails clearly instead of falling through to a wrong artifact.
- The tap formula is committed and pushed to <https://github.com/Lightless-Labs/homebrew-tap>.
- This repository records the tap decision and next validation step.

## Validation

Completed 2026-04-27:

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
brew deps --declared --formula lightless-labs/tap/middens --annotate
```

`brew deps --declared --formula lightless-labs/tap/middens --annotate` reports `uv [recommended]`; installing with `--without-uv` succeeded, and the exact default install command succeeded after pulling Homebrew's `uv` bottle.
