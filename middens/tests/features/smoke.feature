Feature: Smoke test
  Verify the cucumber harness is wired correctly.

  Scenario: Harness runs
    Given the test harness is initialized
    Then the harness should be operational
