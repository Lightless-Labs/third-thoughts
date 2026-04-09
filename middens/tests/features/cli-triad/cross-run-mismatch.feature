Feature: Cross-run mismatch metadata preservation

  Scenario: Mismatched --interpretation-dir preserves both IDs verbatim
    Given an analysis A1
    And an interpretation I2 whose manifest references a different analysis A2
    When I run middens export with --analysis-dir A1 and --interpretation-dir I2
    Then it succeeds
    And the resulting notebook's metadata.middens.analysis_run_id is A1's ID
    And the metadata.middens.analysis_run_path is A1's path
    And the metadata.middens.interpretation_id is I2's ID
    And the metadata.middens.interpretation_path is I2's path
