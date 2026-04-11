Feature: Interpret

  Scenario: Default analysis discovery by name sort
    Given two valid runs under the XDG analysis dir
    When I run middens interpret with no --analysis-dir
    Then it picks the run whose directory name sorts descending first
    And touching the older run's directory does not change the selection

  Scenario: Invalid analysis runs are skipped during discovery
    Given two runs where the lexicographically-greater one has a corrupt manifest.json
    When I run middens interpret
    Then it picks the lexicographically-lesser valid run

  Scenario: No analysis runs results in clear error
    Given an empty XDG analysis dir
    When I run middens interpret
    Then it exits non-zero with a message containing "no analysis runs found"

  Scenario: Runner fallback picks first available
    Given mocked which resolving only claude-code
    When I run middens interpret
    Then it selects claude-code
    And when only gemini is available it selects gemini
    And when none are available it fails with a message listing all four supported runners

  Scenario: Explicit --model overrides fallback with runner prefix
    Given codex is absent from PATH
    When I run middens interpret with --model codex/gpt-5.4-codex
    Then it fails cleanly with a message naming codex

  Scenario: --model parses on first slash only
    Given a valid analysis run
    When I run middens interpret with --model opencode/kimi-for-coding/k2p5
    Then it resolves runner to opencode and model-id to kimi-for-coding/k2p5
    And the interpretation manifest captures runner as "opencode" and model_id as "kimi-for-coding/k2p5"

  Scenario: --model without a slash fails at parse time
    When I run middens interpret with --model claude-code
    Then it exits non-zero with a message showing the expected form and concrete examples
    And no runner auto-resolution occurs

  Scenario: Unknown runner prefix fails with helpful error
    When I run middens interpret with --model foo/bar
    Then it exits non-zero with a message listing the four supported runner slugs

  Scenario: Dry-run writes prompt, skips runner, lands in interpretation-dryruns
    When I run middens interpret with --dry-run
    Then it produces a prompt.md under interpretation-dryruns/<analysis-run-slug>/<interpretation-slug>/
    And it prints the dry-run path to stdout
    And it does not invoke any subprocess
    And it exits 0
    And the dry-run dir never appears under interpretation/ or interpretation-failures/

  Scenario: Interpretation output layout on success
    Given a successful interpretation
    Then the interpretation dir contains manifest.json, prompt.md, conclusions.md
    And it contains one <technique_slug>-conclusions.md per technique present in the analysis

  Scenario: Empty conclusions.md on leading marker
    Given a mocked runner emitting a response that starts immediately with a technique marker
    When I run middens interpret
    Then the successful interpretation dir contains an empty conclusions.md file

  Scenario: Interpretation manifest references analysis
    Given a successful interpretation
    Then the interpretation manifest.json carries analysis_run_id and analysis_run_path matching the analysis
    And it carries runner and model_id

  Scenario: Zero-marker response results in failure
    Given a mocked runner emitting output containing zero technique markers
    When I run middens interpret
    Then it fails non-zero
    And the temp dir is renamed to interpretation-failures/<analysis-run-slug>/<slug>/
    And it contains prompt.md, raw-response.txt, and error.txt
    And no directory appears under interpretation/<analysis-run-slug>/

  Scenario: Partial marker coverage is tolerated
    Given a mocked runner emitting markers for M less than N techniques
    When I run middens interpret
    Then it succeeds
    And it writes per-technique files for exactly those M techniques
    And it writes conclusions.md from any pre-marker content
    And it does not write files for the missing techniques
    And the interpretation manifest's conclusions.per_technique map has exactly M entries

  Scenario: Unknown slug marker passes through
    Given a mocked runner emitting a marker whose slug is not present in the analysis
    When I run middens interpret
    Then it succeeds
    And it writes the unknown slug conclusions file alongside the legitimate technique files

  Scenario: Atomic write on success
    When I run middens interpret
    Then no directory exists at the final destination path until after the temp dir is fully written and manifest.json is serialised

  Scenario: Interpretation slug format
    Given a successful interpretation
    Then the interpretation subdir matches the expected UUIDv7 and runner slug format

  Scenario: OpenCode without --model is an error
    Given runner auto-detected to opencode
    When I run middens interpret without --model
    Then it fails with "opencode requires an explicit --model"
