@middens/docs/nlspecs/2026-04-06-python-techniques-batch4-nlspec.md
Feature: Python Batch 4 Techniques
  As the RED TEAM, I want to validate the final batch of Python analysis techniques
  to ensure they meet the full Definition of Done, including findings, tables,
  and handling of insufficient data.

  Background:
    Given a set of Python techniques
    And a resolver for the Python executable

  # user_signal_analysis.py
  Scenario: user_signal_analysis.py successfully classifies user signals
    Given a set of 5 sessions, each with 10-20 turns, including thinking and tool use
    When the "user-signal-analysis" technique is run
    Then the technique should succeed
    And the result name should be "user-signal-analysis"
    And the result summary should mention "user signal analysis"
    And the result should have a numeric finding with label "total_user_messages"
    And the result should have a numeric finding with label "messages_classified"
    And the result should have a numeric finding with label "skipped_non_english_messages"
    And the result should have a numeric finding with label "boilerplate_messages"
    And the result should have a numeric finding with label "corrections"
    And the result should have a numeric finding with label "redirects"
    And the result should have a numeric finding with label "directives"
    And the result should have a numeric finding with label "approvals"
    And the result should have a numeric finding with label "questions"
    And the result should have a numeric finding with label "escalations_found"
    And the result should have a string finding with label "peak_frustration_session_id"
    And the result should contain a table named "Category Counts"
    And the result should contain a table named "Frustration Distribution"
    And the result should contain a table named "Escalation Sequences"
    And no table cell contains raw user or assistant text

  Scenario: user_signal_analysis.py handles insufficient data
    Given an empty array of sessions
    When the "user-signal-analysis" technique is run
    Then the technique should succeed
    And the result summary should contain "insufficient"

  # Language gate: finding must exist even when all fixtures are English
  Scenario: user_signal_analysis.py exposes non-English skip count even on English-only fixtures
    Given a set of 3 sessions, each with 5-10 turns, including thinking and tool use
    When the "user-signal-analysis" technique is run
    Then the technique should succeed
    And the result should have a numeric finding with label "skipped_non_english_messages"

  # cross_project_graph.py
  Scenario: cross_project_graph.py successfully builds a reference graph
    Given a set of 10 sessions across 3 projects spanning 5 days with timestamps, each with 5-10 turns
    When the "cross-project-graph" technique is run
    Then the technique should succeed
    And the result name should be "cross-project-graph"
    And the result summary should mention "cross-project graph"
    And the result should have a numeric finding with label "total_sessions"
    And the result should have a numeric finding with label "total_projects"
    And the result should have a numeric finding with label "total_edges"
    And the result should have a numeric finding with label "total_references"
    And the result should have a numeric finding with label "mutual_pair_count"
    And the result should have a numeric finding with label "cluster_count"
    And the result should have a string finding with label "largest_hub"
    And the result should have a string finding with label "largest_authority"
    And the result should contain a table named "Edges"
    And the result should contain a table named "Nodes"
    And the result should contain a table named "Clusters"
    And no table cell contains raw user or assistant text

  Scenario: cross_project_graph.py handles insufficient projects
    Given a set of 2 sessions, each with 10-20 turns, including thinking and tool use
    When the "cross-project-graph" technique is run
    Then the technique should succeed
    And the result summary should contain "insufficient"

  # change_point_detection.py
  Scenario: change_point_detection.py successfully detects signal shifts
    # Required: at least one session with >= 30 messages
    Given a set of 5 sessions, each with 35-40 turns, including thinking and tool use
    When the "change-point-detection" technique is run
    Then the technique should succeed
    And the result name should be "change-point-detection"
    And the result summary should mention "change point"
    And the result should have a numeric finding with label "sessions_analyzed"
    And the result should have a numeric finding with label "total_change_points"
    And the result should have a numeric finding with label "change_points_user_msg_length"
    And the result should have a numeric finding with label "change_points_tool_call_rate"
    And the result should have a numeric finding with label "change_points_correction_flag"
    And the result should have a numeric finding with label "change_points_tool_diversity"
    And the result should have a numeric finding with label "mean_change_points_per_session"
    And the result should have a string finding with label "most_volatile_session_id"
    And the result should contain a table named "Change Points"
    And the result should contain a table named "Regimes"
    And the result should contain a table named "Signal Summary"
    And no table cell contains raw user or assistant text

  Scenario: change_point_detection.py handles insufficient session count
    Given a set of 2 sessions, each with 35-40 turns, including thinking and tool use
    When the "change-point-detection" technique is run
    Then the technique should succeed
    And the result summary should contain "insufficient"

  # corpus_timeline.py
  Scenario: corpus_timeline.py successfully generates a temporal audit
    Given a set of 10 sessions across 3 projects spanning 5 days with timestamps, each with 5-10 turns
    When the "corpus-timeline" technique is run
    Then the technique should succeed
    And the result name should be "corpus-timeline"
    And the result summary should mention "corpus timeline"
    And the result should have a numeric finding with label "total_sessions"
    And the result should have a numeric finding with label "undated_sessions"
    And the result should have a numeric finding with label "total_dates"
    And the result should have a numeric finding with label "total_projects"
    And the result should have a numeric finding with label "high_concurrency_day_count"
    And the result should have a string finding with label "date_range_min"
    And the result should have a string finding with label "date_range_max"
    And the result should have a string finding with label "peak_day"
    And the result should contain a table named "Daily Activity"
    And the result should contain a table named "Daily Totals"
    And the result should contain a table named "Project Totals"
    And no table cell contains raw user or assistant text

  Scenario: corpus_timeline.py handles an empty corpus
    Given an empty array of sessions
    When the "corpus-timeline" technique is run
    Then the technique should succeed
    And the result summary should contain "insufficient"
