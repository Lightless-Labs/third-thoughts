---
title: "Pin GitHub Actions and Rust toolchain to immutable SHAs / exact versions"
status: todo
priority: P2
tags: [ci, release, supply-chain, codex-review]
source: codex-review-v0.0.1-beta.0-2026-04-17
---

## What

The release workflow at `.github/workflows/release.yml` currently depends on mutable GitHub Action tags (`actions/checkout@v4`, `softprops/action-gh-release@v2`, etc.) and a floating Rust toolchain (`dtolnay/rust-toolchain@stable`). That is the main supply-chain weak point of an otherwise reasonable release pipeline: a compromised or retagged action could ship poisoned release artifacts under our tag.

## Refs

- `.github/workflows/release.yml:28-36` — checkout + toolchain actions
- `.github/workflows/release.yml:60-76` — build + tarball steps
- `.github/workflows/release.yml:87-94` — release publish step

## Fix

1. Pin every `uses:` line to a full commit SHA, with a comment noting the version tag it corresponds to:

   ```yaml
   uses: actions/checkout@b4ffde65f46336ab88eb53be808477a3936bae11  # v4.1.1
   uses: softprops/action-gh-release@69320dbe05506a9a39fc8ae11030b214ec2d1f87  # v2.0.5
   ```

2. Pin the Rust toolchain:

   ```yaml
   uses: dtolnay/rust-toolchain@88a1ea3d5a6d3b3d6a7f4bf3f2ff9f9e... # 1.88.0
   with:
     toolchain: 1.88.0
   ```

3. Add dependabot coverage for `github-actions` so SHAs get bumped with visible PRs instead of silent `@stable` drift.

## Why

From the codex pre-release review: "the main supply-chain weak point in an otherwise reasonable release pipeline." Cheap to fix; meaningful hardening for a tag that signs binaries other people install.

## Priority

P2 — worth doing before the next release, but the first-beta tag can ship on floating versions if we accept the risk for one cut.
