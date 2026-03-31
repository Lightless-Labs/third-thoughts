Feature: Claude Code Parser
  Parse Claude Code JSONL session log files into structured sessions.

  Scenario: Detect Claude Code JSONL format
    Given a session file "tests/fixtures/claude_code_sample.jsonl"
    When I check if the Claude Code parser can parse it
    Then it should be parseable

  Scenario: Reject non-JSONL files
    Given a session file path "README.md"
    When I check if the Claude Code parser can parse it
    Then it should not be parseable

  Scenario: Parse extracts a single session
    Given a session file "tests/fixtures/claude_code_sample.jsonl"
    When I parse the file with the Claude Code parser
    Then there should be 1 session
    And the session id should be "test-session-001"
    And the source tool should be "ClaudeCode"
    And the parsed session type should be "Interactive"

  Scenario: Parse extracts session metadata
    Given a session file "tests/fixtures/claude_code_sample.jsonl"
    When I parse the file with the Claude Code parser
    Then the metadata version should be "2.1.76"
    And the metadata cwd should be "/Users/test/project"
    And the metadata git branch should be "main"
    And the metadata permission mode should be "default"
    And the metadata model should be "claude-opus-4-6"

  Scenario: Parse extracts user and assistant messages
    Given a session file "tests/fixtures/claude_code_sample.jsonl"
    When I parse the file with the Claude Code parser
    Then the session should have at least 1 user message
    And the session should have at least 1 assistant message

  Scenario: Parse extracts thinking blocks
    Given a session file "tests/fixtures/claude_code_sample.jsonl"
    When I parse the file with the Claude Code parser
    Then the session should have at least 1 thinking block

  Scenario: Parse extracts tool calls
    Given a session file "tests/fixtures/claude_code_sample.jsonl"
    When I parse the file with the Claude Code parser
    Then the session should have at least 1 tool call
    And the tool sequence should contain "Read"

  Scenario: Parse extracts tool results
    Given a session file "tests/fixtures/claude_code_sample.jsonl"
    When I parse the file with the Claude Code parser
    Then at least one message should have tool results

  Scenario: Path with subagents component is detected as subagent
    Given a session file path "/tmp/project/subagents/agent-abc123.jsonl"
    Then the path should contain the "subagents" component

  Scenario: Non-message entries are skipped
    Given a session file "tests/fixtures/claude_code_sample.jsonl"
    When I parse the file with the Claude Code parser
    Then all messages should have role "User" or "Assistant"

  Scenario: Parse extracts environment fingerprint
    Given a session file "tests/fixtures/claude_code_sample.jsonl"
    When I parse the file with the Claude Code parser
    Then the environment tool version should be "2.1.76"
    And the environment model id should be "claude-opus-4-6"
    And the environment permission mode should be "default"
