Feature: Pi parser
  Parse pi coding-agent JSONL sessions shared through pi-share-hf / Hugging Face.

  Scenario: Pi parser recognizes pi session JSONL
    Given a session file "tests/fixtures/pi_sample.jsonl"
    When I check if the Pi parser can parse it
    Then it should be parseable

  Scenario: Pi parser extracts messages, thinking, tools, and metadata
    Given a session file "tests/fixtures/pi_sample.jsonl"
    When I parse the file with the Pi parser
    Then there should be 1 session
    And the session id should be "test-pi-session-001"
    And the source tool should be "PiCodingAgent"
    And the metadata cwd should be "/work/pi-mono"
    And the metadata model should be "claude-opus-4-5"
    And the metadata extra should contain key "provider"
    And the metadata extra should contain key "thinking_level"
    And the session should have at least 1 user message
    And the session should have at least 2 assistant messages
    And the session should have at least 1 thinking block
    And the session reasoning observability should be "FullTextVisible"
    And the session should have at least 1 tool call
    And the tool sequence should contain "bash"
    And at least one message should have tool results

  Scenario: Auto-detect routes generic pi session files to the Pi parser
    Given a session file "tests/fixtures/pi_sample.jsonl"
    When I detect the format
    Then the detected format should be "PiCodingAgent"

  Scenario: Auto-parse handles pi session files
    Given a session file "tests/fixtures/pi_sample.jsonl"
    When I auto-parse the file
    Then there should be 1 session
    And the source tool should be "PiCodingAgent"
    And the session should have at least 1 tool call
