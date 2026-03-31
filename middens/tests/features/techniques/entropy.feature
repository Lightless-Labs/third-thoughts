Feature: Entropy rate and anomaly detection
  Verify the entropy technique computes conditional entropy over sliding
  windows and detects anomalies correctly.

  Scenario: Periodic sequence has low entropy
    Given a session "periodic" with 30 repetitions of tools "Read,Edit"
    When I run the entropy technique on the session
    Then the session entropy mean should be less than 0.0000000001

  Scenario: Random-ish sequence has higher entropy
    Given a session "random_ish" with an LCG tool sequence of length 60
    When I run the entropy technique on the session
    Then the session entropy mean should be greater than 0.5

  Scenario: Short session is skipped
    Given a session "short" with 10 copies of tool "Bash"
    When I run the entropy technique on the session
    Then the session entropy result should be none

  Scenario: Single tool sequence has zero entropy
    Given a session "mono" with 30 copies of tool "Bash"
    When I run the entropy technique on the session
    Then the session entropy mean should be less than 0.0000000001

  Scenario: Run on mixed sessions skips short ones
    Given a session "s1" with 20 repetitions of tools "A,B"
    And a session "s2" with 5 copies of tool "X"
    And a session "s3" with tools "Bash,Read,Edit,Bash,Grep,Read,Write,Edit,Bash,Read,Bash,Read,Edit,Bash,Grep,Read,Write,Edit,Bash,Read,Glob,Bash,Read,Edit,Write"
    When I run the entropy technique
    Then finding "sessions_analyzed" should be integer 2
    And the technique result should have a table "per_session_entropy" with 2 rows

  Scenario: Conditional entropy of deterministic sequence is zero
    Given a session "deterministic" with 20 repetitions of tools "A,B"
    When I run the entropy technique on the session
    Then the session entropy mean should be less than 0.0000000001

  Scenario: Anomaly detection with constant entropy produces zero anomalies
    Given a session "constant" with 40 copies of tool "Bash"
    When I run the entropy technique on the session
    Then the session entropy anomaly count should be 0
