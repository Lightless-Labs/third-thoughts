Feature: Integration

  Scenario: End-to-end triad
    Given a fixture corpus
    When I run middens analyze on the fixture corpus
    And I run middens interpret with a mocked runner
    And I run middens export
    Then it produces a notebook whose top cell names the analysis run ID
    And the middle cells contain per-technique summaries, tables, and interpretations
    And the bottom cells expose exploratory starters

  Scenario: Idempotent re-export
    Given an analysis and an interpretation
    When I run middens export twice in a row with the same analysis and interpretation
    Then it produces byte-equal .ipynb files
