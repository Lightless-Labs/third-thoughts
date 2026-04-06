@python
Feature: Python Batch 3 Techniques
  As the RED TEAM, I want to validate the unseen Python analysis technique implementations
  against a strict definition of done, covering success, failure, and edge cases.

  Background:
    Given a set of Python techniques
    And a resolver for the Python executable

  # lag_sequential.py
  Scenario: lag_sequential.py successfully analyzes sequence data
    Given a set of 5 sessions, each with 30-50 turns, including thinking and tool use
    When the "lag_sequential" technique is run
    Then the technique should succeed
    And the result name should be "lag_sequential"
    And the result summary should mention "lag sequential"
    And the result should have a numeric finding with label "total_events"
    And the result should have a numeric finding with label "sessions_analyzed"
    And the result should have a numeric finding with label "significant_transitions_lag1"
    And the result should have a numeric finding with label "significant_transitions_lag2"
    And the result should have a numeric finding with label "significant_transitions_lag3"
    And the result should have a string finding with label "top_positive_transition"
    And the result should have a string finding with label "top_negative_transition"
    And the result should contain a table named "Top Positive Transitions"
    And the result should contain a table named "Top Negative Transitions"
    And the result should contain a table named "Event Frequencies"
    And no table cell contains raw user or assistant text

  Scenario: lag_sequential.py gracefully handles insufficient data
    Given a set of 2 sessions, each with 30-50 turns, including thinking and tool use
    When the "lag_sequential" technique is run
    Then the technique should succeed
    And the result summary should contain "insufficient"

  # spc_control_charts.py
  Scenario: spc_control_charts.py successfully analyzes variations over time
    Given a set of 15 sessions, each with 30-50 turns, including thinking and tool use
    When the "spc_control_charts" technique is run
    Then the technique should succeed
    And the result name should be "spc_control_charts"
    And the result summary should mention "control chart"
    And the result should have a numeric finding with label "sessions_analyzed"
    And the result should have a numeric finding with label "correction_rate_mean"
    And the result should have a numeric finding with label "correction_rate_ucl"
    And the result should have a numeric finding with label "correction_rate_ooc_count"
    And the result should have a numeric finding with label "tool_error_rate_ooc_count"
    And the result should have a numeric finding with label "assistant_len_ooc_count"
    And the result should have a numeric finding with label "rule2_violations"
    And the result should contain a table named "Control Limits"
    And the result should contain a table named "Out-of-Control Sessions"
    And the result should contain a table named "Rule Violations"
    And the result should contain a table named "Correction Rate Series"
    And the result should contain a table named "Tool Error Rate Series"
    And the result should contain a table named "Assistant Text Length Series"
    And the result should contain a table named "CUSUM Series"
    And no table cell contains raw user or assistant text

  Scenario: spc_control_charts.py gracefully handles insufficient data
    Given a set of 5 sessions, each with 30-50 turns, including thinking and tool use
    When the "spc_control_charts" technique is run
    Then the technique should succeed
    And the result summary should contain "insufficient"

  # ncd_clustering.py
  Scenario: ncd_clustering.py successfully clusters sessions
    Given a set of 6 sessions, each with 30-50 turns, including thinking and tool use
    When the "ncd_clustering" technique is run
    Then the technique should succeed
    And the result name should be "ncd_clustering"
    And the result summary should mention "normalized compression distance"
    And the result should have a numeric finding with label "sessions_in_sample"
    And the result should have a numeric finding with label "optimal_k"
    And the result should have a numeric finding with label "largest_cluster_size"
    And the result should have a string finding with label "largest_cluster_label"
    And the result should contain a table named "Cluster Summary"
    And the result should contain a table named "NCD Matrix Preview"
    And no table cell contains raw user or assistant text

  Scenario: ncd_clustering.py gracefully handles insufficient data
    Given a set of 3 sessions, each with 30-50 turns, including thinking and tool use
    When the "ncd_clustering" technique is run
    Then the technique should succeed
    And the result summary should contain "insufficient"

  # ena_analysis.py
  Scenario: ena_analysis.py successfully extracts epistemic networks
    Given a set of 6 sessions, each with 30-50 turns, including thinking and tool use
    When the "ena_analysis" technique is run
    Then the technique should succeed
    And the result name should be "ena_analysis"
    And the result summary should mention "epistemic network"
    And the result should have a numeric finding with label "sessions_analyzed"
    And the result should have a string finding with label "top_code"
    And the result should have a numeric finding with label "top_code_centrality"
    And the result should have a string finding with label "strongest_low_correction_edge"
    And the result should have a string finding with label "strongest_high_correction_edge"
    And the result should contain a table named "Code Centrality"
    And the result should contain a table named "Discriminative Edges"
    And no table cell contains raw user or assistant text

  Scenario: ena_analysis.py gracefully handles insufficient data
    Given a set of 3 sessions, each with 30-50 turns, including thinking and tool use
    When the "ena_analysis" technique is run
    Then the technique should succeed
    And the result summary should contain "insufficient"

  # convention_epidemiology.py
  Scenario: convention_epidemiology.py successfully analyzes within-workflow conventions
    Given a set of 20 sessions across 2 projects, each with 30-50 turns, including thinking and tool use
    When the "convention_epidemiology" technique is run
    Then the technique should succeed
    And the result name should be "convention_epidemiology"
    And the result summary should mention "convention"
    And the result should have a numeric finding with label "sessions_analyzed"
    And the result should have a numeric finding with label "projects_detected"
    And the result should have a numeric finding with label "conventions_detected"
    And the result should have a string finding with label "top_convention"
    And the result should contain a table named "Within-Workflow Fits"
    And no table cell contains raw user or assistant text
    And the result summary should state that insufficient projects were found for cross-project analysis

  Scenario: convention_epidemiology.py successfully analyzes cross-project propagation
    Given a set of 30 sessions across 4 projects, each with 30-50 turns, including thinking and tool use
    When the "convention_epidemiology" technique is run
    Then the technique should succeed
    And the result name should be "convention_epidemiology"
    And the result summary should mention "cross-project"
    And the result should have a numeric finding with label "projects_detected"
    And the result should have a string finding with label "top_cross_project_convention"
    And the result should contain a table named "Within-Workflow Fits"
    And the result should contain a table named "Cross-Project Propagation"
    And the result should contain a table named "Convention × Project Matrix"
    And no table cell contains raw user or assistant text

  Scenario: convention_epidemiology.py gracefully handles insufficient sessions overall
    Given a set of 10 sessions, each with 30-50 turns, including thinking and tool use
    When the "convention_epidemiology" technique is run
    Then the technique should succeed
    And the result summary should contain "insufficient"

  # Edge and failure cases for all
  Scenario Outline: All techniques handle an empty session array
    Given an empty array of sessions
    When the "<technique_name>" technique is run
    Then the technique should succeed
    And the result should contain 0 findings
    And the result summary should indicate that 0 sessions were analyzed

    Examples:
      | technique_name          |
      | lag_sequential          |
      | spc_control_charts      |
      | ncd_clustering          |
      | ena_analysis            |
      | convention_epidemiology |

  Scenario Outline: All techniques handle unrecoverable errors
    Given an invalid session file path
    When I attempt to run the "<technique_name>" technique with the invalid path
    Then the technique should fail with a non-zero exit code
    And the captured stderr should not be empty

    Examples:
      | technique_name          |
      | lag_sequential          |
      | spc_control_charts      |
      | ncd_clustering          |
      | ena_analysis            |
      | convention_epidemiology |
