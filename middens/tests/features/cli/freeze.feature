Feature: Freeze CLI command
  The `middens freeze` subcommand creates a corpus manifest for reproducibility,
  recording each .jsonl file's path, size, and SHA-256 hash.

  Scenario: Freeze test fixtures directory produces a manifest with 3 entries
    When I run middens freeze on the test fixtures directory
    Then the exit code should be 0
    And the manifest file should exist
    And the manifest should contain 3 entries

  Scenario: Freeze a non-existent directory returns an error
    When I run middens freeze on a non-existent directory
    Then the exit code should not be 0
