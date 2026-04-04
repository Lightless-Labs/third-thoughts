Feature: List-techniques CLI command
  The `middens list-techniques` subcommand displays all registered analytical
  techniques in a tabular format.

  Scenario: List all techniques shows 6 techniques
    When I run middens list-techniques
    Then the exit code should be 0
    And stdout should contain "burstiness"
    And stdout should contain "correction-rate"
    And stdout should contain "diversity"
    And stdout should contain "entropy"
    And stdout should contain "markov"
    And stdout should list 6 technique rows

  Scenario: List essential techniques shows the same 6 techniques
    When I run middens list-techniques with the essential flag
    Then the exit code should be 0
    And stdout should list 6 technique rows
