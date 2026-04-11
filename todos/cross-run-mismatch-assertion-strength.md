---
title: "Strengthen cross-run mismatch metadata assertions in step definitions"
status: todo
priority: P3
tags: [testing, cli-triad]
source: copilot-pr1-review-2026-04-10
---

## Problem

Several step definitions for the cross-run mismatch metadata scenario check that fields exist but don't verify they equal the expected fixture values (A1/I2 IDs and paths). Regressions could slip through.

## Fix

Compare notebook metadata values against the known fixture values captured in the world state during Given steps.
