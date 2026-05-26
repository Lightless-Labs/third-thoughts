---
title: "Deduplicate duplicate-shaped public HF corpora before treating them as replication evidence"
status: todo
priority: P2
tags: [huggingface, corpus, deduplication, methodology, replication]
source: public-hf-independent-analysis-2026-05-25
---

## Why

Several public `*-pi-mono` Hugging Face datasets produced identical aggregate counts and identical HSMM/full-battery patterns. They are useful for parser/CI coverage, but they should not be counted as independent scientific replication evidence unless object/session overlap is quantified.

Clone armies are fine in CI. They are less fine in a methods section.

## What

Compute cross-dataset object/session overlap for public HF corpora and label duplicate/near-duplicate datasets in the registry and methodology docs.

Known duplicate-shaped examples:

- `badlogicgames/pi-mono`
- `JohnBeanerson/pi-mono-test`
- `karkowww/pi-mono`
- `invincible-jha/pi-mono`
- `assafvayner/pi-mono`
- `bhollmann/pi-mono`

## How

1. Reuse per-object SHA-256 manifests from the public HF materializers or regenerate them under `experiments/`.
2. Compute pairwise overlap by:
   - raw object SHA-256;
   - session id;
   - normalized session content hash, if needed.
3. Classify datasets as:
   - exact duplicate;
   - subset/superset;
   - partial overlap;
   - distinct.
4. Add registry metadata fields such as `duplicate_group`, `dedup_role`, or `replication_weight` if useful.
5. Update public-HF findings docs so duplicate-shaped corpora are not accidentally counted as independent evidence.

## Done

- [ ] Pairwise overlap table exists under gitignored `experiments/`.
- [ ] Duplicate groups are documented without transcript snippets.
- [ ] Registry entries carry duplicate/replication caveats.
- [ ] Public finding summaries distinguish CI coverage from independent replication evidence.
