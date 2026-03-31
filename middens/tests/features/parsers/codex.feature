Feature: Codex CLI Parser
  Parse Codex CLI JSONL session log files into structured sessions.

  Scenario: Detect Codex CLI fixture format
    Given a session file "tests/fixtures/codex_sample.jsonl"
    When I check if the Codex parser can parse it
    Then it should be parseable

  Scenario: Parse Codex CLI fixture
    Given a session file "tests/fixtures/codex_sample.jsonl"
    When I parse the file with the Codex parser
    Then there should be 1 session
    And the source tool should be "CodexCli"
    And the session id should be "test-codex-session-001"
    And the metadata cwd should be "/tmp/test-project"
    And the metadata version should be "0.112.0"
    And the metadata model should be "gpt-5.4"
    And the session should have at least 1 user message
    And the session should have at least 1 assistant message

  Scenario: Reject non-Codex files
    Given a session file path "/tmp/random.jsonl"
    When I check if the Codex parser can parse it
    Then it should not be parseable
    Given a session file path "/tmp/file.json"
    When I check if the Codex parser can parse it
    Then it should not be parseable
