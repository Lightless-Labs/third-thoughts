Feature: Burstiness and memory coefficients
  Verify Barabasi burstiness B and memory coefficient M for tool usage patterns.

  Scenario: Perfectly periodic sequence has B close to -1
    Given a session with tool sequence "A,B,C,A,B,C,A,B,C,A"
    When I run the burstiness technique
    Then tool "A" should have burstiness B close to -1.0 within 0.01

  Scenario: Clustered tools are bursty
    Given a session with tool sequence "A,A,A,A,B,B,B,B,B,B"
    When I run the burstiness technique
    Then tool "A" should have burstiness B greater than 0.5

  Scenario: Tool appearing twice has B but no M
    Given a session with tool sequence "X,A,A,A,A,X"
    When I run the burstiness technique
    Then tool "X" should have a numeric burstiness B
    And tool "X" should have null memory M

  Scenario: Tool appearing once is skipped
    Given a session with tool sequence "Y,A,A,A,A,A"
    When I run the burstiness technique
    Then tool "Y" should not appear in the burstiness table

  Scenario: Empty sessions produce zero tools analyzed
    Given no sessions
    When I run the burstiness technique
    Then finding "tools_analyzed" should be integer 0

  Scenario: Memory computed for four-plus occurrences
    Given a session with tool sequence "A,B,A,B,A,B,A"
    When I run the burstiness technique
    Then tool "A" should have a numeric memory M

  Scenario: Memory not computed for three occurrences
    Given a session with tool sequence "A,B,C,A,B,C,A"
    When I run the burstiness technique
    Then tool "A" should have null memory M

  Scenario: Mixed burstiness produces intermediate B
    Given a session with tool sequence "A,A,B,B,B,A,A"
    When I run the burstiness technique
    Then tool "A" should have burstiness B between 0.0 and 1.0

  Scenario: Aggregate burstiness is frequency-weighted
    Given a session with 10 periodic "A" tools interleaved with "X" and 3 clustered "B" tools
    When I run the burstiness technique
    Then finding "aggregate_burstiness" should be a negative number
