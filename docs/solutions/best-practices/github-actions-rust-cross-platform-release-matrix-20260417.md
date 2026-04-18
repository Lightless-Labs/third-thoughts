---
title: "Cross-platform Rust CLI releases with native GitHub-hosted runners"
date: 2026-04-17
category: best-practices
module: middens
problem_type: best_practice
component: tooling
severity: medium
applies_when:
  - "Shipping a Rust CLI binary to users via GitHub Releases"
  - "Targeting macOS (arm64 + x86_64) and Linux (arm64 + x86_64) without Windows"
  - "Wanting to avoid cross-compilation toolchains (cross, zig, custom containers)"
  - "Repository is public (so ubuntu-24.04-arm runners are free)"
  - "Downstream distribution is Homebrew / Scoop / curl-installer that needs stable URL + SHA256"
related_components:
  - development_workflow
  - documentation
tags: [distribution, ci, github-actions, rust, release-workflow, cross-platform]
---

# Cross-platform Rust CLI Releases with Native GitHub-Hosted Runners

## Context

The middens CLI needed a GitHub Actions release workflow to produce cross-platform tarballs on tag push, as a prerequisite for a Homebrew tap. The design question sitting in `docs/HANDOFF.md` was the classic one: use the `cross` crate (Docker-based cross-compilation from a single cheap Linux runner) versus native GitHub-hosted runners (one runner per OS/arch, native toolchains each). Both are defensible; the tradeoff is real; and picking wrong locks friction into every subsequent release.

The decision also needed to survive public-facing distribution — Homebrew formulas pin to a release URL and a SHA256, so whatever we picked had to produce a stable tarball layout with per-artifact checksums on every tag.

Commit: `49d896f`. File: `.github/workflows/release.yml`. Driving todo: `todos/distribution-release-workflow.md`.

## Guidance

**For public-repo Rust CLIs distributing cross-platform tarballs, prefer native GitHub-hosted runners over `cross`.** Use a 3-target matrix:

| Runner | Target triple | Notes |
|--------|---------------|-------|
| `macos-14` | `aarch64-apple-darwin` | Apple Silicon |
| `ubuntu-latest` | `x86_64-unknown-linux-gnu` | Standard Linux |
| `ubuntu-24.04-arm` | `aarch64-unknown-linux-gnu` | Free for public repos (Jan 2025+) |

> **2026-04-18 update — `x86_64-apple-darwin` removed.** The original matrix included a fourth row (`macos-13` → `x86_64-apple-darwin`). On the first real tag cut for `middens v0.0.1-beta.0`, that job sat in queue for 9 hours waiting for a free Intel runner that never arrived, while the other three targets built in ~5 minutes each. Free `macos-13` capacity for public repos has effectively dried up post-retirement. If you need an Intel-Mac binary, cross-compile from `macos-14` (`cargo build --target x86_64-apple-darwin` with `dtolnay/rust-toolchain@stable targets:` configured) on the same arm64 runner, or pay for `macos-13-large`. The `middens` project chose to drop the target entirely — Apple Silicon is dominant; Intel-Mac users can build from source.

### Matrix block

```yaml
strategy:
  fail-fast: false
  matrix:
    include:
      - target: aarch64-apple-darwin
        runner: macos-14
      - target: x86_64-unknown-linux-gnu
        runner: ubuntu-latest
      - target: aarch64-unknown-linux-gnu
        runner: ubuntu-24.04-arm
```

### Build step

`--locked` is non-negotiable for reproducibility, and the target-specific output path matters:

```yaml
- name: Build release binary
  working-directory: middens
  run: cargo build --release --locked --target ${{ matrix.target }}
```

### Package step

Stages the binary + LICENSE + README, tarballs the stage directory, emits a sidecar `.sha256`:

```yaml
- name: Package tarball
  id: package
  working-directory: middens
  run: |
    VERSION="${GITHUB_REF_NAME#v}"
    STAGE="middens-${VERSION}-${{ matrix.target }}"
    mkdir -p "dist/${STAGE}"
    cp "target/${{ matrix.target }}/release/middens" "dist/${STAGE}/"
    cp ../LICENSE "dist/${STAGE}/"
    cp README.md "dist/${STAGE}/" 2>/dev/null || true
    tar -C dist -czf "dist/${STAGE}.tar.gz" "${STAGE}"
    ( cd dist && shasum -a 256 "${STAGE}.tar.gz" > "${STAGE}.tar.gz.sha256" )
```

### Release job

Downloads all matrix artifacts, aggregates a combined `SHA256SUMS`, and publishes with `generate_release_notes` + `fail_on_unmatched_files`:

```yaml
release:
  needs: build
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v4
    - uses: actions/download-artifact@v4
      with:
        path: artifacts
    - name: Aggregate checksums
      run: |
        mkdir -p release
        find artifacts -name '*.tar.gz' -exec cp {} release/ \;
        ( cd release && shasum -a 256 *.tar.gz > SHA256SUMS )
    - uses: softprops/action-gh-release@v2
      with:
        files: |
          release/*.tar.gz
          release/SHA256SUMS
        generate_release_notes: true
        fail_on_unmatched_files: true
```

### Other essentials

- `permissions: contents: write` at workflow scope so `softprops/action-gh-release` can publish.
- `Swatinem/rust-cache@v2` with `workspaces: middens` because the Cargo workspace root is a subdirectory.
- `dtolnay/rust-toolchain@stable` with `targets: ${{ matrix.target }}` so rustup installs the cross-target stdlib even when running natively (no-op for matching host, but uniform syntax for all four targets).
- `strip = true, lto = "thin", codegen-units = 1` in `[profile.release]` — set in `middens/Cargo.toml` already, required for shippably-small tarballs.
- Trigger: tag push `v*`; `${GITHUB_REF_NAME#v}` strips the leading `v` so `v0.1.0` → `0.1.0` in the tarball name.

## Why This Matters

The `cross` approach is seductive — one `ubuntu-latest` runner, Docker images for each target, no multi-OS matrix. On paper it's cheaper and simpler. The Achilles heel is **darwin**: Apple's SDK licensing makes cross-compiling `*-apple-darwin` from Linux a grey area reputable projects avoid. Every serious cross-platform Rust project that uses `cross` ends up hybrid anyway — `cross` for Linux/Windows legs, native `macos-*` runners for darwin. Once you're booting `macos-14` regardless, the "one cheap runner" savings are gone and you're maintaining two build pathways instead of one.

Native runners give you:

- **One code path per target.** No "does this work with cross, or do we need the native fallback?" conditionals.
- **Homebrew-compatible output.** Stable URL, per-artifact SHA256, combined `SHA256SUMS` — all of which brew formulas consume directly.
- **Reproducibility via `--locked`.** The flag is the invariant; non-reproducible releases are how you end up with "it built differently this time" bugs nobody can debug.
- **Free linux-arm64** on public repos since January 2025 via `ubuntu-24.04-arm` — the one historically-painful target is now trivial.

The meta-reason aligns with CLAUDE.md's *"fail early, fail fast, fail clearly"* posture (and its 2026-04-09 *"day job for playing end-user psychic"* articulation): when two options are defensible, pick the one that doesn't require future-you or future-contributors to guess which path a given target took. Native runners = one path through the matrix, no conditional cross-compile fallbacks, no surprise when someone adds a 5th target and it takes a different route than the other four.

### Process note: handoff-docs earn their keep (session history)

`docs/HANDOFF.md` surfaced the open "cross vs native" question in its Step B section, which made session pickup <1 turn. Reading the handoff, answering the question, and committing the workflow took one conversation with zero backtracking. The handoff pattern earns its keep every time a session resumes on a decision point.

The decision had been queued in the todo since 2026-04-10 (session `0ce615f5`, where the full workstream-3 structure was laid out), and resolved 2026-04-17 (session `57acaea9`) — a 7-day gap spanning other work, with no context reconstruction cost at resumption.

## When to Apply

- Rust CLIs targeting cross-platform tarball distribution.
- **Public repositories** — the free `ubuntu-24.04-arm` runner makes linux-arm64 free.
- Distribution channels needing stable URLs + SHA256 (Homebrew taps, Scoop, install scripts that `curl | tar`).
- Projects where reproducibility matters enough to require `--locked` in CI.
- Anywhere you'd otherwise end up maintaining a hybrid `cross` + native-darwin setup.

## When NOT to Apply

- **Private repos on the free tier.** `ubuntu-24.04-arm` costs money here; `cross` from `ubuntu-latest` becomes more attractive, or drop linux-arm64 entirely.
- **You need Windows today.** Add a 5th matrix entry (`windows-latest` → `x86_64-pc-windows-msvc`), but path separators, `.exe` suffix, and `shasum` vs `certutil` all need workflow adjustments. This session left Windows as a stretch goal.
- **You need musl / static Linux binaries.** That's a `cross` job (or a `rust-musl-builder` container) even inside an otherwise-native matrix — glibc native runners won't produce musl output.
- **Very large matrices** (many niche targets like `*-freebsd`, `*-illumos`). Native runner availability thins out fast; `cross` may be the only realistic path.

## Examples

The committed workflow at `.github/workflows/release.yml` is the exemplar in full. It implements the todo at `todos/distribution-release-workflow.md` and satisfies the Cargo.toml release profile at `middens/Cargo.toml`.

### Failure modes to avoid

1. **Wrong binary path.** When you pass `--target <triple>`, the binary lives at `target/<triple>/release/<name>`, not `target/release/<name>`. Cargo isolates target-specific output. Getting this wrong produces silent "file not found" failures in the package step.

2. **`fail-fast: true` (the default).** One broken target will cancel the other three mid-flight and you'll lose the signal. Always set `fail-fast: false` on release matrices — you want to see which targets broke, not just the first one.

3. **Skipping `--locked`.** Release CI without `--locked` means `Cargo.lock` can drift mid-build if the registry is refreshed between checkout and compile, producing non-reproducible releases.

4. **Forgetting `workspaces: middens` on rust-cache.** If the Cargo workspace isn't at the repo root, `Swatinem/rust-cache@v2` silently caches nothing useful. Set `workspaces:` to the directory containing `Cargo.toml`.

5. **Missing `permissions: contents: write`.** `softprops/action-gh-release@v2` needs it to publish; default `GITHUB_TOKEN` permissions don't include release write on most repos.

6. **Trusting the `macos-13` label on a free public repo.** The runner label still resolves, the job still queues — it just never gets picked up. Empirically observed on the `middens v0.0.1-beta.0` cut (2026-04-18): job sat 9 hours waiting for a free Intel runner that never arrived. There is no error, no warning, no "no capacity" signal — the only feedback is wall-clock time. If you absolutely need an Intel-Mac binary, cross-compile from `macos-14` (arm64 host, `--target x86_64-apple-darwin`); Apple's toolchain handles same-OS cross-arch builds without extra config.

## References

- Commit: `49d896f` — `ci(release): add GitHub Actions release workflow for v* tags`
- Driving todo: `todos/distribution-release-workflow.md`
- Downstream: `todos/distribution-homebrew-tap.md`, `todos/distribution-validation-runs.md`, `todos/distribution-github-pages.md`
- Session history: distribution workstream structure established 2026-04-10 (`0ce615f5`); native-runner decision 2026-04-17 (`57acaea9`)
- Related (low overlap, different topic): `docs/solutions/best-practices/cargo-invocation-from-repo-root-20260407.md`
