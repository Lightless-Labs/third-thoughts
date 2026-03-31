Feature: Parse CLI command
  The `middens parse` subcommand parses a single session log file and dumps
  the parsed sessions as JSON to stdout.

  Scenario: Parse a Claude Code fixture produces valid JSON with 1 session
    When I run middens parse on the "claude_code_sample.jsonl" fixture
    Then the exit code should be 0
    And stdout should be valid JSON
    And the parsed output should contain 1 session

  Scenario: Parse a Codex CLI fixture produces valid JSON
    When I run middens parse on the "codex_sample.jsonl" fixture
    Then the exit code should be 0
    And stdout should be valid JSON

  Scenario: Parse an unrecognized file produces an empty array
    When I run middens parse on a temporary empty file
    Then the exit code should be 0
    And the parsed output should contain 0 sessions

  Scenario: Parse with unsupported format flag returns an error
    When I run middens parse on the "claude_code_sample.jsonl" fixture with format "yaml"
    Then the exit code should not be 0
    And stderr should contain "unsupported format"
