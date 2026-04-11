---
title: "GitHub Actions release workflow for cross-platform binaries"
status: todo
priority: P1
tags: [distribution, ci, workstream-3]
source: user-direction-2026-04-10
---

## What

A GitHub Actions workflow triggered on tag push (`v*`) that builds release binaries and creates a GitHub Release with attached artifacts.

## Targets

- darwin-arm64 (Apple Silicon)
- darwin-x86_64 (Intel Mac)
- linux-x86_64
- linux-arm64
- windows-x86_64 (stretch goal)

## Workflow shape

1. Tag push triggers the workflow.
2. Matrix build across targets (cross-compilation via `cross` or native runners).
3. Each produces a tarball: `middens-<version>-<target>.tar.gz` containing the binary + LICENSE.
4. Create GitHub Release, attach all tarballs + SHA256SUMS file.
5. Homebrew formula references these release URLs (distribution-homebrew-tap.md).

## Build settings

Already configured in Cargo.toml: `strip = true, lto = "thin", codegen-units = 1`.

## Sequencing

This is a prerequisite for the Homebrew tap. Build it first.
