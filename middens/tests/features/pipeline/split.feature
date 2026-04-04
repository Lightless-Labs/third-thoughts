Feature: Analyze pipeline split stratification
  The `middens analyze --split` mode should stratify outputs by interactive and
  subagent populations without changing the underlying technique artifacts.

  Scenario: --split flag partitions results into interactive and subagent subdirectories
    Given a temporary mixed interactive and subagent corpus
    And a temporary analyze output directory
    When I run middens analyze with split on the mixed corpus
    Then the exit code should be 0
    And the analyze output should be partitioned into interactive and subagent subdirectories

  Scenario: Without --split, output is flat with no population subdirectories
    Given a temporary mixed interactive and subagent corpus
    And a temporary analyze output directory
    When I run middens analyze without split on the mixed corpus
    Then the exit code should be 0
    And the analyze output should be flat with no population subdirectories
    And the flat analyze output should contain technique markdown and JSON files

  Scenario: Each split subdirectory contains technique markdown and JSON files
    Given a temporary mixed interactive and subagent corpus
    And a temporary analyze output directory
    When I run middens analyze with split on the mixed corpus
    Then the exit code should be 0
    And the "interactive" analyze subdirectory should contain technique markdown and JSON files
    And the "subagent" analyze subdirectory should contain technique markdown and JSON files

  Scenario: Split summary reports per-population counts
    Given a temporary mixed interactive and subagent corpus
    And a temporary analyze output directory
    When I run middens analyze with split on the mixed corpus
    Then the exit code should be 0
    And the split summary should report 2 interactive sessions and 1 subagent session
