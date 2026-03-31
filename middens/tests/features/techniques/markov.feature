Feature: Markov chain tool transition analysis
  Verify the Markov chain technique computes correct transition matrices,
  self-loop rates, stationary distributions, and entry tool frequencies.

  Scenario: Known sequence produces correct transition matrix
    Given a session with tools "Read,Edit,Read,Bash"
    When I run the markov technique
    Then the technique result should have a table "transition_matrix"
    And the transition matrix should have 4 columns
    And the transition from "Bash" to "Bash" should be 0.0
    And the transition from "Bash" to "Edit" should be 0.0
    And the transition from "Bash" to "Read" should be 0.0
    And the transition from "Edit" to "Read" should be 1.0
    And the transition from "Edit" to "Bash" should be 0.0
    And the transition from "Edit" to "Edit" should be 0.0
    And the transition from "Read" to "Bash" should be 0.5
    And the transition from "Read" to "Edit" should be 0.5
    And the transition from "Read" to "Read" should be 0.0
    And finding "total_bigrams" should be integer 3

  Scenario: Single tool session has full self-loop
    Given a session with tools "Bash,Bash,Bash,Bash"
    When I run the markov technique
    Then finding "self_loop_Bash" should be float 1.0

  Scenario: Empty session returns trivial result
    Given a session with tools ""
    When I run the markov technique
    Then finding "total_bigrams" should be integer 0
    And the technique result should have 0 tables

  Scenario: Empty sessions slice returns trivial result
    Given no sessions
    When I run the markov technique
    Then finding "total_bigrams" should be integer 0

  Scenario: Stationary distribution sums to one
    Given a session with tools "Read,Edit,Read,Bash,Read,Edit,Bash"
    When I run the markov technique
    Then the stationary distribution should sum to approximately 1.0

  Scenario: Single tool call session returns trivial
    Given a session with tools "Read"
    When I run the markov technique
    Then finding "total_bigrams" should be integer 0
