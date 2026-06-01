# Autonomous stratum public-HF comparative analysis

**Created:** 2026-05-28  
**Status:** Public-HF pass complete; true autonomous analysis still blocked by missing supported autonomous corpus  
**Command family:** `middens analyze --split --all`  
**Local artifacts:** `experiments/autonomous-stratum-public-hf/`, `.tmp/middens-autonomous-split/`, `.tmp/xdg-autonomous-split/`, `.tmp/logs-autonomous-split/`

## Short version

I ran the full 23-technique battery over the current CI-selected public Hugging Face corpora with the new three-way session split:

- `interactive`
- `subagent`
- `autonomous`

The run completed cleanly: **5 corpora × 3 strata × 23 techniques = 345 technique executions, zero technique errors**.

The annoying-but-useful result: **none of the supported public-HF JSONL corpora currently contain `SessionType::Autonomous` sessions under the Phase 1 classifier.** The selected corpora are either fully interactive Pi coding-agent corpora, a tiny mixed sanity corpus, or mostly subagent-style Claude/Kimi traces. So the autonomous Phase 2 result is a negative/coverage finding, not a behavioral finding:

> With the supported public-HF JSONL corpora available today, `middens analyze --split --all` can validate that autonomous sessions do not contaminate these public analyses, but it cannot yet estimate autonomous-loop behavior.

Follow-up later the same day promoted the first Parquet trace normalizer into the public-HF materialization path. That changed this caveat: `archit11/claude-code-traces` is now analyzable through generated JSONL, and the normal middens classifier yields **5 interactive / 19 subagent / 1 autonomous**, not the earlier HSMM-only artifact's 25/25 apparent autonomous candidates. The original public JSONL conclusion still holds; the Parquet follow-up gives us a tiny non-empty autonomous smoke, not a real autonomous-loop cohort.

## Why this pass was needed

Phase 1 added `SessionType::Autonomous` and made `middens analyze --split` produce three strata. Phase 2 asked whether existing findings survive the new session-type axis, especially after the W10-W12 Boucle contamination episode showed that autonomous agent-loop sessions can masquerade as interactive sessions.

The old private `corpus-split/` cannot currently support this rerun: it is a stale absolute-symlink split over Claude Code live storage, and most targets have been pruned. So this pass used the durable public-HF corpora already wired into CI.

## Important implementation note found during this pass

Before running the public-HF split battery, I found and fixed a split-mode correctness bug in the Python technique cache.

The pipeline wrote a single shared Python session cache before splitting. That optimization is correct for unsplit analysis, but wrong for `--split --all`: every Python technique in every stratum would have received the full all-corpus session array while the Rust renderer reported the stratum's metadata size. In other words, the split output would look stratified but the 17 Python techniques would quietly be all-corpus results. Beautifully useless. Very on-brand.

Fix: disable the corpus-wide Python cache in split mode so each Python technique serializes and receives the actual stratum sessions.

Validation after the fix:

```bash
cd middens && cargo test
cd middens && cargo build --release --locked
```

Result: `381/381` scenarios, `2108/2108` steps, and doctest passing; release build passing. This includes a regression scenario that runs the Python `hsmm` technique in split mode and checks that each stratum receives only its own sessions.

## Commands

The smoke corpus was materialized because `.tmp/hf-full/` already contained the four larger public-HF corpora from the previous full-battery pass but not the smoke cohort:

```bash
python3 scripts/materialize_hf_analysis_corpus.py \
  --corpus agent-sessions-list-mixed \
  --output .tmp/hf-full/agent-sessions-list-mixed \
  --cache-dir .tmp/hf-cache-smoke \
  --force
```

Then each corpus was run through full split analysis:

```bash
for corpus in \
  agent-sessions-list-mixed \
  badlogicgames-pi-mono \
  thomasmustier-pi-for-excel \
  aaaaliou-pi-mono \
  kimi-claude-code-traces-jsonl
 do
  XDG_DATA_HOME="$PWD/.tmp/xdg-autonomous-split/$corpus" \
    ./middens/target/release/middens analyze ".tmp/hf-full/$corpus" \
      --split --all --timeout 1800 --force \
      --output ".tmp/middens-autonomous-split/$corpus" \
      > ".tmp/logs-autonomous-split/$corpus.stdout.log" \
      2> ".tmp/logs-autonomous-split/$corpus.stderr.log"
done
```

## Corpus split counts

| Corpus | Sessions parsed | Interactive | Subagent | Autonomous | Technique errors |
| --- | ---: | ---: | ---: | ---: | ---: |
| `agent-sessions-list-mixed` | 7 | 5 | 2 | 0 | 0 |
| `badlogicgames-pi-mono` | 626 | 626 | 0 | 0 | 0 |
| `thomasmustier-pi-for-excel` | 161 | 161 | 0 | 0 | 0 |
| `aaaaliou-pi-mono` | 145 | 145 | 0 | 0 | 0 |
| `kimi-claude-code-traces-jsonl` | 36 | 2 | 34 | 0 | 0 |
| **Total** | **975** | **939** | **36** | **0** | **0** |

Each split run reported `techniques run: 69` because it executed 23 techniques for each of the three strata.

## Main comparative metrics

`—` means the technique reported insufficient/undefined data for that stratum.

| corpus | stratum | sessions | risk suppression | risk tokens | thinking sessions | correction mean | sessions w/ corrections | first-third corr. | last-third corr. | tool Shannon | cond. entropy | burstiness | memory | MVT compliance | HSMM lift | median survival | change points | median user msgs | max user msgs |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `agent-sessions-list-mixed` | interactive | 5 | 0.9824 | 170 | 2 | 0.2258 | 3/5 | 0.2200 | 0.0182 | 0.2535 | 0.9493 | 0.3842 | 0.0368 | 0.0000 | — | — | 0 | 2 | 62 |
| `agent-sessions-list-mixed` | subagent | 2 | 0.0000 | 0 | 2 | 0.0000 | 0/2 | 0.0000 | 0.0000 | 0.4809 | 0.0000 | 0.4516 | -0.0417 | — | — | — | 0 | 16.5 | 19 |
| `agent-sessions-list-mixed` | autonomous | 0 | 0.0000 | 0 | 0 | 0.0000 | 0/0 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | — | — | — | — | — | 0 | — | — |
| `badlogicgames-pi-mono` | interactive | 626 | 0.9118 | 8,575 | 555 | 0.2140 | 325/626 | 0.2916 | 0.0770 | 0.6050 | 0.9000 | 0.3860 | 0.0725 | 0.0000 | 3.5584 | 3 | 0 | 3 | 49 |
| `badlogicgames-pi-mono` | autonomous | 0 | 0.0000 | 0 | 0 | 0.0000 | 0/0 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | — | — | — | — | — | 0 | — | — |
| `thomasmustier-pi-for-excel` | interactive | 161 | 0.9544 | 9,315 | 158 | 0.1323 | 99/161 | 0.1398 | 0.1097 | 0.8967 | 0.7845 | 0.4814 | 0.1350 | 0.0000 | 9.4429 | 4 | 0 | 7 | 99 |
| `thomasmustier-pi-for-excel` | autonomous | 0 | 0.0000 | 0 | 0 | 0.0000 | 0/0 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | — | — | — | — | — | 0 | — | — |
| `aaaaliou-pi-mono` | interactive | 145 | 0.9478 | 1,359 | 122 | 0.1777 | 67/145 | 0.1997 | 0.1412 | 0.8935 | 1.0109 | 0.4265 | 0.0559 | 0.0000 | 6.1689 | 3 | 0 | 3 | 31 |
| `aaaaliou-pi-mono` | autonomous | 0 | 0.0000 | 0 | 0 | 0.0000 | 0/0 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | — | — | — | — | — | 0 | — | — |
| `kimi-claude-code-traces-jsonl` | interactive | 2 | 1.0000 | 15 | 2 | 0.0000 | 0/2 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | — | — | — | — | — | 0 | 3 | 3 |
| `kimi-claude-code-traces-jsonl` | subagent | 34 | 1.0000 | 1,345 | 34 | 0.0051 | 4/34 | 0.0121 | 0.0000 | 1.3301 | 1.0447 | 0.3422 | 0.0301 | 0.0000 | 2.4205 | -1 | 0 | 38 | 140 |
| `kimi-claude-code-traces-jsonl` | autonomous | 0 | 0.0000 | 0 | 0 | 0.0000 | 0/0 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | — | — | — | — | — | 0 | — | — |

Empty subagent rows for the all-interactive Pi corpora are omitted from the table except where useful; they were still executed and produced valid empty/insufficient results.

## Phase 2 questions answered

### 1. Risk suppression across strata

On the public-HF supported JSONL corpora, risk suppression is measurable for interactive Pi corpora and for the Kimi/Claude-style subagent corpus, but not for autonomous sessions because no autonomous sessions were present.

Observed public-HF rates:

- Interactive Pi corpora: `91.18%`, `95.44%`, and `94.78%` suppression.
- Mixed tiny interactive sanity cohort: `98.24%`, but N is tiny.
- Kimi/Claude-style subagent traces: `100%` suppression over 1,345 observed risk tokens.
- Autonomous: undefined in these corpora (`N=0`).

Conclusion: public-HF split analysis does **not** show autonomous contamination in the current public risk-suppression replications. It does not prove anything about actual autonomous loops.

### 2. Session-length distributions

Using user-message counts from `correction-rate` as the lightweight length proxy:

- `badlogicgames-pi-mono` interactive: median 3 user messages, max 49.
- `thomasmustier-pi-for-excel` interactive: median 7, max 99.
- `aaaaliou-pi-mono` interactive: median 3, max 31.
- `kimi-claude-code-traces-jsonl` subagent: median 38, max 140.
- Autonomous: undefined (`N=0`).

The old Boucle sample's tight 5-19 message band cannot be tested on these supported public-HF JSONL corpora.

### 3. Tool diversity and entropy

Public-HF interactive Pi corpora differ substantially among themselves:

- Mean tool Shannon: `0.6050` (`badlogicgames`) vs `0.8967` (`pi-for-excel`) vs `0.8935` (`aaaaliou`).
- Mean conditional entropy: `0.9000`, `0.7845`, `1.0109` respectively.

The Kimi/Claude subagent stratum is higher-diversity than the Pi interactive strata in this pass:

- Mean tool Shannon: `1.3301`.
- Mean conditional entropy: `1.0447`.

Autonomous tool diversity remains unknown here.

### 4. Correction patterns

Human correction rates are zero/near-zero outside the interactive Pi corpora, as expected:

- `badlogicgames-pi-mono`: mean correction rate `0.2140`, `325/626` sessions with corrections.
- `thomasmustier-pi-for-excel`: `0.1323`, `99/161`.
- `aaaaliou-pi-mono`: `0.1777`, `67/145`.
- `kimi-claude-code-traces-jsonl` subagent: `0.0051`, `4/34`.
- Autonomous: undefined (`N=0`).

Correction front-loading still appears in the larger interactive corpora, though strength varies:

- `badlogicgames`: first-third `0.2916` → last-third `0.0770`.
- `pi-for-excel`: `0.1398` → `0.1097`.
- `aaaaliou`: `0.1997` → `0.1412`.
- `kimi` subagent: `0.0121` → `0.0000`.

Structural correction in autonomous loops remains an open analysis item. We need an actual autonomous cohort and probably a tool-error-followed-by-different-tool metric, not the human-message correction classifier.

### 5. Survival and change-point detection

Survival metrics were meaningful only for the larger interactive corpora and the Kimi subagent stratum:

- `badlogicgames`: median survival to correction = 3 turns.
- `pi-for-excel`: 4 turns.
- `aaaaliou`: 3 turns.
- `kimi` subagent reports `-1`, which should be read as no conventional median event under that script's current encoding rather than a real negative time.

Change-point detection found **zero** total change points in every selected public-HF stratum.

Autonomous failure shape is still unmeasured.

### 6. HSMM behavioural states

HSMM pre-correction lift is present in the larger public-HF interactive corpora and in the Kimi subagent stratum, but magnitudes remain implementation/dataset-sensitive:

- `badlogicgames-pi-mono` interactive: `3.56×`.
- `thomasmustier-pi-for-excel` interactive: `9.44×`.
- `aaaaliou-pi-mono` interactive: `6.17×`.
- `kimi-claude-code-traces-jsonl` subagent: `2.42×`.
- Autonomous: undefined (`N=0`).

This supports the existing downgrade: direction often appears, magnitude varies, and there is still no autonomous-loop estimate.

### 7. Burstiness / Hawkes-style timing proxy

The burstiness technique reports tool-call burstiness/memory rather than wall-clock human pause structure, but the public strata show these values:

- `badlogicgames` interactive: B=`0.3860`, M=`0.0725`.
- `pi-for-excel` interactive: B=`0.4814`, M=`0.1350`.
- `aaaaliou` interactive: B=`0.4265`, M=`0.0559`.
- `kimi` subagent: B=`0.3422`, M=`0.0301`.

No autonomous timing fingerprint can be estimated from this public-HF pass.

### 8. Information foraging / MVT

MVT compliance remains `0.0` in every selected public stratum where the technique had enough data:

- `badlogicgames` interactive: `0.0`.
- `pi-for-excel` interactive: `0.0`.
- `aaaaliou` interactive: `0.0`.
- `kimi` subagent: `0.0`.

Autonomous MVT remains untested.

## Parquet follow-up corrected the unsupported-candidate caveat

The initial public-HF Phase 2 pass noted a metadata-only candidate from the independent-HSMM normalized artifacts:

| Normalized dataset | Sessions | Interactive | Subagent | Autonomous candidates | Unknown |
| --- | ---: | ---: | ---: | ---: | ---: |
| `archit11__claude-code-traces` | 25 | 0 | 0 | 25 | 0 |

That was based on pre-normalized `Session[]` objects whose user-message classifications had not gone through the normal middens parse/classify path. After promoting the Parquet trace-row materializer, the same dataset now runs as generated Claude-Code-compatible JSONL and classifies as:

| Corpus | Sessions | Interactive | Subagent | Autonomous |
| --- | ---: | ---: | ---: | ---: |
| `archit11-claude-code-traces-parquet` | 25 | 5 | 19 | 1 |

So the useful correction is: the Parquet dataset gives us a **tiny non-empty autonomous smoke**, but not 25 autonomous sessions and not enough data to characterize autonomous-loop behavior.

## Effect on current findings

| Finding | Effect of this pass |
| --- | --- |
| Risk suppression | Public-HF supported JSONL replications are not autonomous-contaminated; autonomous remains unmeasured. |
| HSMM pre-correction state | Still provisional. Direction appears across public interactive/subagent strata, magnitude varies. No autonomous estimate. |
| MVT violation | Still robust on supported public strata that have enough data; autonomous remains untested. |
| Session degradation / correction front-loading | Correction front-loading appears in public interactive strata; no autonomous estimate. |
| W10-W12 Boucle contamination | Not reproduced in the supported public-HF JSONL corpora. This pass neither weakens nor reruns the old private-corpus Boucle finding because that corpus split is currently unavailable. |

## Next step

The next concrete move is **not** another run over the same JSONL CI corpora. They have zero autonomous sessions. The next useful move is one of:

1. recover a durable raw/archive copy of the old private W10-W12 Boucle corpus and rerun `middens analyze --split --all`; or
2. expand Parquet trace normalizer coverage beyond the tiny `archit11/claude-code-traces` smoke cohort; or
3. add a deliberately curated public autonomous-loop JSONL corpus to `docs/corpora/public-hf-analysis-corpora.json`.

Until then, the honest Phase 2 conclusion is: **the public supported corpora validate the split machinery, and the first Parquet trace cohort gives one autonomous smoke session, but they still do not contain the autonomous population we need to characterize autonomous behavior.**
