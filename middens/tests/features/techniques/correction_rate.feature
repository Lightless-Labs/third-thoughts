Feature: Correction rate metrics
  Verify correction rate computation per session, project, and session position.

  Scenario: Session with 2 corrections in 10 user messages
    Given a session "s1" in project "proj-a" with 2 corrections and 8 directives
    When I run the correction rate technique
    Then finding "overall_mean_rate" should be approximately 0.2
    And the per-session table should have 1 row
    And per-session row 0 should have correction_rate approximately 0.2
    And per-session row 0 should have 2 corrections
    And per-session row 0 should have 10 user messages

  Scenario: Session with corrections only in last third
    Given a session "s2" with 6 directives then 3 corrections
    When I run the correction rate technique
    Then per-session row 0 should have first_third_rate 0.0
    And per-session row 0 should have last_third_rate 1.0
    And per-session row 0 should have null degradation_ratio

  Scenario: Session with zero user messages
    Given an empty session "empty"
    When I run the correction rate technique
    Then finding "overall_mean_rate" should be approximately 0.0

  Scenario: Session with no corrections
    Given a session "s3" in project "proj-b" with 0 corrections and 6 directives
    When I run the correction rate technique
    Then finding "overall_mean_rate" should be approximately 0.0
    And per-session row 0 should have degradation_ratio 0.0

  Scenario: Multiple sessions same project aggregate correctly
    Given a session "sa" in project "alpha" with 1 corrections and 3 directives
    And a session "sb" in project "alpha" with 3 corrections and 3 directives
    When I run the correction rate technique
    Then the per-project table should have 1 row for project "alpha"
    And the per-project row for "alpha" should have correction_rate approximately 0.4
    And the per-project row for "alpha" should have 4 total corrections
    And the per-project row for "alpha" should have 10 total user messages
    And the per-project row for "alpha" should have 2 sessions
    And finding "overall_mean_rate" should be approximately 0.375

  Scenario: Unknown project when none specified
    Given a session "s4" with no project and 3 directives
    When I run the correction rate technique
    Then the per-project table should have 1 row for project "unknown"

  Scenario: Median with even number of sessions
    Given a session "sa" in project "p" with 0 corrections and 4 directives
    And a session "sb" in project "p" with 2 corrections and 2 directives
    When I run the correction rate technique
    Then finding "overall_median_rate" should be approximately 0.25

  Scenario: Empty sessions slice
    Given no sessions
    When I run the correction rate technique
    Then finding "overall_mean_rate" should be approximately 0.0
    And the per-session table should have 0 rows
    And the per-project table should have 0 rows
