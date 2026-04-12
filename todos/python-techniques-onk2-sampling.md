---
title: "O(n²) Python techniques: add sampling for large corpora"
status: todo
priority: P1
tags: [python-bridge, scaling, techniques]
source: real-corpus-validation-2026-04-11
---

## Problem

Some Python techniques (HSMM, Smith-Waterman, process mining) are inherently O(n²) or worse on session count. Even with Parquet I/O (see python-bridge-parquet-handoff.md), they may not complete on 13k+ sessions in reasonable time.

## Fix

Add optional sampling: if session count exceeds a technique-specific threshold, sample down to a manageable size and note the sampling in the technique's output metadata. The threshold and strategy should be per-technique (HSMM might cap at 2000 sessions, Smith-Waterman at 500 pairs).

## Sequencing

After the Parquet bridge fix. Some techniques that timeout now may be fine once the I/O bottleneck is removed — measure first, then add sampling only where needed.
