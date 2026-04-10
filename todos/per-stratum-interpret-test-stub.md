---
title: "Implement per-stratum interpret test assertions (currently a stub)"
status: todo
priority: P2
tags: [testing, cli-triad]
source: copilot-pr1-review-2026-04-10
---

## Problem

The per-stratum interpret scenario uses `--dry-run` which doesn't produce an interpretation manifest. The step asserting the output path/layout is a stub that doesn't verify anything. The per-stratum path contract isn't actually tested.

## Fix

Either use a mock runner (via MIDDENS_MOCK_RUNNER env var) to produce real output for the test, or restructure the scenario to test dry-run behavior explicitly and add a separate scenario with the mock runner for the real output layout.
