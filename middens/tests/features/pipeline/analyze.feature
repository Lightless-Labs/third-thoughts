Feature: Analyze pipeline
  The `middens analyze` subcommand should discover session logs, run the
  selected technique battery, and write markdown and JSON results.

  Scenario: Pipeline discovers and parses fixture sessions from a directory
    Given a temporary analyze output directory
    When I run middens analyze on the fixtures directory
    Then the exit code should be 0
    And every analyze output file should report corpus_size 3

  Scenario: Empty directory returns zero counts
    Given an empty temporary directory for analyze input
    And a temporary analyze output directory
    When I run middens analyze on the temporary input directory
    Then the exit code should be 1
    And the analyze output directory should contain 0 markdown files
    And the analyze output directory should contain 0 JSON files

  Scenario: Essential techniques are the default analyze output set
    Given a temporary analyze output directory
    When I run middens analyze on the fixtures directory
    Then the exit code should be 0
    And the analyze output file basenames should match technique names "burstiness,correction-rate,diversity,entropy,markov,thinking-divergence"

  Scenario: All techniques can be requested explicitly
    Given a temporary analyze output directory
    When I run middens analyze on the fixtures directory with all techniques
    Then the exit code should be 0
    And the analyze output file basenames should match technique names "burstiness,correction-rate,diversity,entropy,markov,thinking-divergence"

  Scenario: Named technique subset limits the generated outputs
    Given a temporary analyze output directory
    When I run middens analyze on the fixtures directory with techniques "burstiness,markov"
    Then the exit code should be 0
    And the analyze output directory should contain 2 markdown files
    And the analyze output directory should contain 2 JSON files
    And the analyze output should contain markdown and JSON files for techniques "burstiness,markov"

  Scenario: Each technique produces markdown and JSON outputs
    Given a temporary analyze output directory
    When I run middens analyze on the fixtures directory
    Then the exit code should be 0
    And the analyze output should contain markdown and JSON files for techniques "burstiness,correction-rate,diversity,entropy,markov,thinking-divergence"

  Scenario: Pipeline creates the output directory if needed
    Given a missing analyze output directory
    When I run middens analyze on the fixtures directory
    Then the exit code should be 0
    And the analyze output directory should exist

  Scenario: End-to-end analyze on fixtures writes 6 markdown and 6 JSON files
    Given a temporary analyze output directory
    When I run middens analyze on the fixtures directory
    Then the exit code should be 0
    And the analyze output directory should contain 6 markdown files
    And the analyze output directory should contain 6 JSON files
