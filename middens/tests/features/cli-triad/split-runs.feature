Feature: Split runs

  Scenario: interpret refuses top-level split runs
    Given a split analysis run
    When I run middens interpret with --analysis-dir pointing to the top-level run directory
    Then it exits non-zero with a message directing the user to pass <run>/interactive or <run>/subagent
    And there is no temp dir, no dry-run artifacts, and no partial output

  Scenario: export refuses top-level split runs
    Given a split analysis run
    When I run middens export with --analysis-dir pointing to the top-level run directory
    Then it exits non-zero with a message directing the user to pass <run>/interactive or <run>/subagent

  Scenario: Per-stratum interpret succeeds
    Given a split analysis run
    When I run middens interpret with --analysis-dir <run>/interactive
    Then it succeeds
    And it writes into interpretation/run-<uuidv7>/interactive/<interpretation-slug>/
    And the interpretation manifest's analysis_run_id matches the top-level run's ID

  Scenario: Per-stratum export succeeds
    Given a split analysis run
    And a per-stratum interpretation for the interactive stratum
    When I run middens export with --analysis-dir <run>/interactive and --interpretation-dir <matching-interpretation>
    Then it produces a valid notebook containing only the interactive stratum's data

  Scenario: Cross-stratum composition is not attempted
    Given a split analysis run
    And an interactive analysis and a subagent interpretation for the same run
    When I run middens export with --analysis-dir <run>/interactive and --interpretation-dir <subagent-interpretation>
    Then it does not validate the cross-stratum mismatch
    And it produces a notebook with the interactive analysis and subagent interpretation
    And it records both paths verbatim in metadata.middens
