Feature: Auto-detect Parser
  Automatically detect session log formats and dispatch to the correct parser.

  Scenario: Detect Claude Code from first line content
    Given a temporary JSONL file with content:
      """
      {"parentUuid":"root","type":"human","text":"hello"}
      """
    When I detect the format
    Then the detected format should be "ClaudeCode"

  Scenario: Detect Claude Code from path
    Given a session file path "/home/user/.claude/projects/foo/session.jsonl"
    When I detect the format from the path
    Then the detected format should be "ClaudeCode"

  Scenario: Detect Codex CLI from path
    Given a session file path "/home/user/.codex/sessions/abc.jsonl"
    When I detect the format from the path
    Then the detected format should be "CodexCli"

  Scenario: Detect Gemini CLI from path
    Given a session file path "/home/user/.gemini/history/session.jsonl"
    When I detect the format from the path
    Then the detected format should be "GeminiCli"

  Scenario: Detect OpenClaw from path
    Given a session file path "/home/user/openclaw-sessions/run.jsonl"
    When I detect the format from the path
    Then the detected format should be "OpenClaw"

  Scenario: Unknown path returns no format
    Given a session file path "/tmp/random/session.jsonl"
    When I detect the format from the path
    Then no format should be detected

  Scenario: parse_auto returns empty for unknown format
    Given a temporary JSONL file with content:
      """
      {"unknown":"format"}
      """
    When I auto-parse the file
    Then there should be 0 sessions
