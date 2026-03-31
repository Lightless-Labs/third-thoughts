Feature: OpenClaw Parser
  Parse OpenClaw JSONL session log files into structured sessions.

  Scenario: Detect OpenClaw fixture format
    Given a session file "tests/fixtures/openclaw_sample.jsonl"
    When I check if the OpenClaw parser can parse it
    Then it should be parseable

  Scenario: Parse OpenClaw fixture
    Given a session file "tests/fixtures/openclaw_sample.jsonl"
    When I parse the file with the OpenClaw parser
    Then there should be 1 session
    And the source tool should be "OpenClaw"
    And the session id should be "test-openclaw-session-001"
    And the metadata cwd should be "/tmp/openclaw-workspace"
    And the metadata model should be present
    And the session should have at least 1 user message
    And the session should have at least 1 assistant message
    And the metadata extra should contain key "provider"

  Scenario: Reject non-OpenClaw files
    Given a session file path "/tmp/random.jsonl"
    When I check if the OpenClaw parser can parse it
    Then it should not be parseable
    Given a session file path "/tmp/file.json"
    When I check if the OpenClaw parser can parse it
    Then it should not be parseable
