---
title: "Release workflow generates `.sha256` sidecars but never publishes them"
status: todo
priority: P3
tags: [ci, release, supply-chain, codex-review]
source: codex-review-v0.0.1-beta.0-2026-04-17
---

## What

`.github/workflows/release.yml` computes a `.sha256` sidecar for each release tarball during the build matrix but does not upload it alongside the tarball in the `softprops/action-gh-release@v2` step. The sidecars are generated and then orphaned. End users who want to verify the download against a published checksum have nothing to verify against.

The aggregate `SHA256SUMS` file *is* published, which covers the verification use case for scripted installs, but the per-file sidecars are the convention most download instructions point people at ("curl ... && sha256sum -c foo.tar.gz.sha256"). Either publish the sidecars or stop generating them.

## Refs

- `.github/workflows/release.yml:54-57` — per-tarball sidecar generation
- `.github/workflows/release.yml:90-92` — release publish step (sidecars not in files list)

## Fix

Two options, pick one:

1. **Publish the sidecars**: add `*.tar.gz.sha256` to the `files:` list of the `softprops/action-gh-release` step. Zero compute cost; consistent with conventional sha256 verification flows.
2. **Stop generating them**: drop the sidecar compute step; keep only the aggregate `SHA256SUMS`. Simpler artifact set, but every Homebrew/Nix package author has to parse the aggregate file instead of grabbing a per-file sidecar.

Option 1 is the lighter-touch fix and matches what most projects ship. Option 2 is defensible if we don't want the per-file files cluttering the release page.

## Why

From the codex pre-release review: "generating unused artifacts is a minor tell that the workflow hasn't been end-to-end tested." True — the workflow was landed without a real tag cut, so the orphan sidecars never made it onto a release page where the asymmetry would be visible.

## Priority

P3 — nice-to-have polish. The aggregate `SHA256SUMS` is the load-bearing checksum file; the per-file sidecars are a convention convenience. Fix in 0.0.1-beta.1 or whenever the release workflow is next touched.
