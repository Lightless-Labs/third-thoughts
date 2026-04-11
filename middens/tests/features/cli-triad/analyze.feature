Feature: Analyze

  Scenario: Analyze writes the expected layout
    Given a fixture corpus
    When I run middens analyze
    Then it produces <run-dir>/manifest.json
    And it produces <run-dir>/sessions.parquet
    And it produces <run-dir>/data/*.parquet
    And it produces <run-dir>/default-view.md

  Scenario: Run ID format
    Given a fixture corpus
    When I run middens analyze
    Then the run dir matches "^run-[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"

  Scenario: UUIDv7 timestamp matches manifest created_at
    Given a fixture corpus
    When I run middens analyze
    Then the Unix millisecond timestamp embedded in the UUIDv7 run_id equals the timestamp of manifest.json created_at field

  Scenario: Monotonic back-to-back ordering
    Given a fixture corpus
    When I run middens analyze twice back-to-back within a single millisecond
    Then it produces two distinct run dirs
    And lexicographic sort descending on the run-dir names returns the second run first

  Scenario: --no-default-view suppresses default view
    Given a fixture corpus
    When I run middens analyze with --no-default-view
    Then default-view.md does not exist in the run dir

  Scenario: Default view is produced via the ViewRenderer path
    Given a fixture corpus
    When I run middens analyze
    Then the emitted default-view.md is byte-equal to MarkdownRenderer::render output

  Scenario: --default-view invalid-format fails at parse time
    Given a fixture corpus
    When I run middens analyze with --default-view json
    Then it exits non-zero with "invalid value for '--default-view'" error
    And no partial output is written

  Scenario: Technique errors do not abort the run
    Given a fixture corpus that causes one technique to fail
    When I run middens analyze
    Then manifest.json exists
    And the failing technique's errors field is non-empty
    And at least one other technique's output is present

  Scenario: Analyze default output dir is XDG
    Given a fixture corpus
    When I run middens analyze with no --output-dir
    Then the run lands under $XDG_DATA_HOME/com.lightless-labs.third-thoughts/analysis/

  Scenario: --split writes nested stratum subdirs
    Given a mixed interactive and subagent corpus
    When I run middens analyze with --split
    Then it produces a single run directory
    And the top-level directory contains manifest.json
    And the interactive subdirectory contains manifest.json, data/, sessions.parquet, and default-view.md
    And the subagent subdirectory contains manifest.json, data/, sessions.parquet, and default-view.md
    And there is no data/ at the top level
    And there is no sessions.parquet at the top level

  Scenario: --split top-level manifest references strata
    Given a mixed interactive and subagent corpus
    When I run middens analyze with --split
    Then the top-level manifest.json carries a strata field
    And the strata field is a list of name, session_count, and manifest_ref entries
    And the manifest_ref points at the per-stratum manifest.json by relative path

  Scenario: --split stratum manifests carry stratum name
    Given a mixed interactive and subagent corpus
    When I run middens analyze with --split
    Then each per-stratum manifest.json contains the correct stratum name
    And it inherits the same run_id as the top-level

  Scenario: Without --split, no stratum subdirs
    Given a mixed interactive and subagent corpus
    When I run middens analyze without --split
    Then it produces a flat layout with data/ and sessions.parquet at the top level
    And there are no interactive or subagent subdirectories
    And there is no strata field in the manifest
