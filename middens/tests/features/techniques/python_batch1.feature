# tests/features/techniques/python_batch1.feature
@python
Feature: Python Batch 1 Techniques
  As the RED TEAM, I want to validate the unseen Python analysis technique implementations
  against a strict definition of done, covering success, failure, and edge cases.

  Background:
    Given a set of Python techniques
    And a resolver for the Python executable

  Scenario: hsmm.py successfully analyzes sufficient session data
    Given a set of 15 sessions, each with 30-50 turns, including thinking and tool use
    When the "hsmm" technique is run
    Then the technique should succeed
    And the result summary should mention "HSMM"
    And the result should have a numeric finding with label "optimal_n_states"
    And the result should contain a table named "State Transition Matrix"
    And the result should contain a table named "State Characteristics"

  Scenario: hsmm.py gracefully handles insufficient data
    Given a set of 5 sessions, each with 30-50 turns, including thinking and tool use
    When the "hsmm" technique is run
    Then the technique should succeed
    And the result summary should contain "insufficient data"

  Scenario: information_foraging.py successfully analyzes patch-leaving behavior
    Given a set of 20 sessions with a mix of high and low correction rates, tool calls, and thinking
    When the "information_foraging" technique is run
    Then the technique should succeed
    And the result summary should mention "information foraging"
    And the result should have a numeric finding with label "mvt_compliance_rate"
    And the result should have findings for "low_correction_foraging_time" and "high_correction_foraging_time"
    And the result should contain a table named "Patch Analysis"

  Scenario: granger_causality.py successfully identifies causal relationships
    Given a set of 20 sessions, each with more than 25 turns
    When the "granger_causality" technique is run
    Then the technique should succeed
    And the result summary should mention "Granger causality"
    And the result should have a finding with label "significant_pairs"
    And the result summary should mention "Bonferroni correction"
    And the result should contain a table named "Granger Causality Results"

  Scenario: granger_causality.py gracefully handles sessions with too few turns
    Given a set of 10 sessions, 5 with less than 25 turns and 5 with more
    When the "granger_causality" technique is run
    Then the technique should succeed
    And the result summary should state that 5 sessions were skipped due to insufficient turns

  Scenario: survival_analysis.py successfully performs survival modeling
    Given a set of 30 varied sessions
    When the "survival_analysis" technique is run
    Then the technique should succeed
    And the result summary should mention "Kaplan-Meier" and "Cox Proportional Hazards"
    And the result should have a numeric finding with label "median_survival_turns"
    And the result should have a string finding with label "hazard_trend"
    And the result should contain a table named "Cox PH Model Covariates"
    And the result should contain a table named "Nelson-Aalen Hazard"

  Scenario Outline: All techniques handle an empty session array
    Given an empty array of sessions
    When the "<technique_name>" technique is run
    Then the technique should succeed
    And the result should contain 0 findings
    And the result summary should indicate that 0 sessions were analyzed

    Examples:
      | technique_name          |
      | hsmm                    |
      | information_foraging    |
      | granger_causality       |
      | survival_analysis       |

  Scenario Outline: All techniques exit successfully with valid JSON
    Given a set of 15 sessions, each with 30-50 turns, including thinking and tool use
    When the "<technique_name>" technique is run
    Then the technique should succeed
    And the result name should be "<technique_name>"

    Examples:
      | technique_name          |
      | hsmm                    |
      | information_foraging    |
      | granger_causality       |
      | survival_analysis       |

  Scenario Outline: All techniques handle unrecoverable errors
    Given an invalid session file path
    When I attempt to run the "<technique_name>" technique with the invalid path
    Then the technique should fail with a non-zero exit code
    And the captured stderr should not be empty

    Examples:
      | technique_name          |
      | hsmm                    |
      | information_foraging    |
      | granger_causality       |
      | survival_analysis       |

  Scenario: process_mining.py successfully builds directly-follows graph and identifies rework
    Given a set of 5 sessions with a mix of high and low correction rates, tool calls, and thinking
    When the "process_mining" technique is run
    Then the technique should succeed
    And the result should have a finding with label "total_events"
    And the result should have a finding with label "unique_activities"
    And the result should have a finding with label "most_common_activity"
    And the result should have a finding with label "top_rework_activity"
    And the result should have a finding with label "top_correction_predecessor"
    And the result should have a finding with label "dfg_edges"
    And the result should contain a table named "Activity Frequencies"
    And the result should contain a table named "Directly-Follows Graph"
    And the result should contain a table named "Correction Predecessors"

  Scenario: prefixspan_mining.py successfully finds frequent sequential patterns
    Given a set of 5 sessions, each with 30-50 turns, including thinking and tool use
    When the "prefixspan_mining" technique is run
    Then the technique should succeed
    And the result should have a finding with label "total_patterns"
    And the result should have a finding with label "patterns_length_3"
    And the result should have a finding with label "patterns_length_4"
    And the result should have a finding with label "success_patterns"
    And the result should have a finding with label "struggle_patterns"
    And the result should contain a table named "Frequent Sequential Patterns"
    And the result should contain a table named "Discriminative Patterns"

  Scenario: prefixspan_mining.py handles sessions with no tool calls gracefully
    Given a set of 5 sessions with no tool calls
    When the "prefixspan_mining" technique is run
    Then the technique should succeed

  Scenario: smith_waterman.py successfully computes local alignments and extracts motifs
    Given a set of 5 sessions with a mix of high and low correction rates, tool calls, and thinking
    When the "smith_waterman" technique is run
    Then the technique should succeed
    And the result should have a finding with label "mean_alignment_score"
    And the result should have a finding with label "conserved_motifs_count"
    And the result should have a finding with label "top_success_motif"
    And the result should have a finding with label "top_struggle_motif"
    And the result should have a finding with label "cluster_count"
    And the result should contain a table named "Conserved Motifs"
    And the result should contain a table named "Motif Enrichment"

  Scenario: tpattern_detection.py successfully detects significant temporal patterns
    Given a set of 3 sessions, each with 30-50 turns, including thinking and tool use
    When the "tpattern_detection" technique is run
    Then the technique should succeed
    And the result should have a finding with label "level_1_patterns"
    And the result should have a finding with label "level_2_patterns"
    And the result should have a finding with label "most_common_pattern"
    And the result should have a finding with label "total_events_analyzed"
    And the result should contain a table named "T-Patterns Level 1"
    And the result should contain a table named "T-Patterns Level 2"

  Scenario Outline: Batch 2 techniques handle an empty session array
    Given an empty array of sessions
    When the "<technique_name>" technique is run
    Then the technique should succeed
    And the result should contain 0 findings
    And the result summary should indicate that 0 sessions were analyzed

    Examples:
      | technique_name          |
      | process_mining          |
      | prefixspan_mining       |
      | smith_waterman          |
      | tpattern_detection      |

  Scenario Outline: Batch 2 techniques exit successfully with valid JSON
    Given a set of 5 sessions, each with 30-50 turns, including thinking and tool use
    When the "<technique_name>" technique is run
    Then the technique should succeed
    And the result name should be "<technique_name>"

    Examples:
      | technique_name          |
      | process_mining          |
      | prefixspan_mining       |
      | smith_waterman          |
      | tpattern_detection      |

  Scenario Outline: Batch 2 techniques handle unrecoverable errors
    Given an invalid session file path
    When I attempt to run the "<technique_name>" technique with the invalid path
    Then the technique should fail with a non-zero exit code
    And the captured stderr should not be empty

    Examples:
      | technique_name          |
      | process_mining          |
      | prefixspan_mining       |
      | smith_waterman          |
      | tpattern_detection      |
