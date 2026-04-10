---
title: "Add e2e verb (middens run) that chains analyze → interpret → export"
status: todo
priority: P1
tags: [distribution, cli, workstream-3]
source: user-direction-2026-04-10
---

## Problem

There's no single command to run the full pipeline: `analyze` → `interpret` → `export`. Users (and the landing page demo) need a one-shot invocation.

## Proposal

`middens run <corpus> [--provider <p>] [--format jupyter] [-o <path>]` that chains:
1. `analyze <corpus> --output-dir <auto>`
2. `interpret --analysis-dir <from-step-1> --provider <p>`
3. `export --analysis-dir <from-step-1> --interpretation-dir <from-step-2> --format <fmt> -o <path>`

Each step's output feeds the next. If `--provider` is omitted, skip interpret and export from analysis only.

## Open questions

- Name: `run`, `full`, `pipeline`, `go`? User said "we don't have a verb for that" — pick something short.
- Should `run` also accept `--techniques` to narrow the analysis?
- Error semantics: if interpret fails (no runner on PATH), should it fall through to export-without-interpretation, or hard-fail?
