Feature: List-techniques CLI command
  The `middens list-techniques` subcommand displays all registered analytical
  techniques in a tabular format.

  Scenario: List all techniques shows 6 Rust + 17 Python techniques
    When I run middens list-techniques
    Then the exit code should be 0
    And stdout should contain "burstiness"
    And stdout should contain "correction-rate"
    And stdout should contain "diversity"
    And stdout should contain "entropy"
    And stdout should contain "markov"
    And stdout should contain "hsmm"
    And stdout should contain "survival-analysis"
    And stdout should contain "convention-epidemiology"
    And stdout should contain "user-signal-analysis"
    And stdout should contain "cross-project-graph"
    And stdout should contain "change-point-detection"
    And stdout should contain "corpus-timeline"
    And stdout should list 23 technique rows

  Scenario: List essential techniques shows only the 6 Rust techniques
    When I run middens list-techniques with the essential flag
    Then the exit code should be 0
    And stdout should list 6 technique rows
