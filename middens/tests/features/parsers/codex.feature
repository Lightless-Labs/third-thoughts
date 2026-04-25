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

  Scenario: Preserve adaptive reasoning observability without treating summaries as thinking
    Given a temporary JSONL file with content:
      """
      {"timestamp":"2026-04-23T10:00:00.000Z","type":"session_meta","payload":{"id":"codex-adaptive-reasoning","cwd":"/tmp/test-project","cli_version":"0.120.0","model_provider":"openai"}}
      {"timestamp":"2026-04-23T10:00:00.001Z","type":"turn_context","payload":{"model":"gpt-5.5","approval_policy":"auto-edit","effort":"high"}}
      {"timestamp":"2026-04-23T10:00:01.000Z","type":"response_item","payload":{"type":"message","role":"assistant","content":[{"type":"thinking","thinking":"Understanding user feedback\n\nI need to clarify the user's point.","thinkingSignature":{"encrypted":"opaque","summary":[{"text":"Understanding user feedback\n\nI need to clarify the user's point."}]}},{"type":"output_text","text":"Could you say more about which part is off?"}]}}
      {"timestamp":"2026-04-23T10:00:02.000Z","type":"response_item","payload":{"type":"message","role":"assistant","content":[{"type":"thinking","thinking":"","thinkingSignature":{"encrypted":"opaque","summary":[]}},{"type":"output_text","text":"I'll wait for the detail before changing course."}]}}
      """
    When I parse the file with the Codex parser
    Then there should be 1 session
    And the session reasoning observability should be "Mixed"
    And at least one message should have reasoning observability "SummaryVisible"
    And at least one message should have reasoning observability "SignatureOnly"
    And the session reasoning summary block count should be 1
    And the session should have exactly 0 thinking blocks

  Scenario: Treat degenerate empty thinking blocks without signatures as absent
    Given a temporary JSONL file with content:
      """
      {"timestamp":"2026-04-23T10:00:00.000Z","type":"session_meta","payload":{"id":"codex-empty-thinking","cwd":"/tmp/test-project","cli_version":"0.120.0","model_provider":"openai"}}
      {"timestamp":"2026-04-23T10:00:00.001Z","type":"turn_context","payload":{"model":"gpt-5.5","approval_policy":"auto-edit","effort":"high"}}
      {"timestamp":"2026-04-23T10:00:01.000Z","type":"response_item","payload":{"type":"message","role":"assistant","content":[{"type":"thinking","thinking":""},{"type":"output_text","text":"No private reasoning is visible here."}]}}
      """
    When I parse the file with the Codex parser
    Then there should be 1 session
    And the session reasoning observability should be "Absent"
    And the session reasoning signature block count should be 0
    And the session reasoning summary block count should be 0
    And the session should have exactly 0 thinking blocks

  Scenario: Reject standalone reasoning response items clearly
    Given a temporary JSONL file with content:
      """
      {"timestamp":"2026-04-23T10:00:00.000Z","type":"session_meta","payload":{"id":"codex-standalone-reasoning","cwd":"/tmp/test-project","cli_version":"0.120.0","model_provider":"openai"}}
      {"timestamp":"2026-04-23T10:00:01.000Z","type":"response_item","payload":{"type":"reasoning","content":[]}}
      """
    When I parse the file with the Codex parser
    Then parsing should fail with error containing "unsupported Codex response_item.payload.type"
    And parsing should fail with error containing "expected payload.type"
    And parsing should fail with error containing "Example supported item"

  Scenario: Reject ambiguous signature plaintext without explicit summary
    Given a temporary JSONL file with content:
      """
      {"timestamp":"2026-04-23T10:00:00.000Z","type":"session_meta","payload":{"id":"codex-ambiguous-signature","cwd":"/tmp/test-project","cli_version":"0.120.0","model_provider":"openai"}}
      {"timestamp":"2026-04-23T10:00:01.000Z","type":"response_item","payload":{"type":"message","role":"assistant","content":[{"type":"thinking","thinking":"Visible text, but no explicit summary field.","thinkingSignature":{"encrypted":"opaque"}}]}}
      """
    When I parse the file with the Codex parser
    Then parsing should fail with error containing "unsupported Codex thinking block"
    And parsing should fail with error containing "expected summary in payload.summary or thinkingSignature.summary"
    And parsing should fail with error containing "Example supported summary block"

  Scenario: Reject mismatched signature plaintext and summary
    Given a temporary JSONL file with content:
      """
      {"timestamp":"2026-04-23T10:00:00.000Z","type":"session_meta","payload":{"id":"codex-mismatched-signature","cwd":"/tmp/test-project","cli_version":"0.120.0","model_provider":"openai"}}
      {"timestamp":"2026-04-23T10:00:01.000Z","type":"response_item","payload":{"type":"message","role":"assistant","content":[{"type":"thinking","thinking":"Raw visible reasoning text.","thinkingSignature":{"encrypted":"opaque","summary":[{"text":"Provider summary text."}]}}]}}
      """
    When I parse the file with the Codex parser
    Then parsing should fail with error containing "unsupported Codex thinking block"
    And parsing should fail with error containing "thinkingSignature summary and plaintext thinking differ"
    And parsing should fail with error containing "Example supported summary block"

  Scenario: Deduplicate repeated reasoning summary parts while preserving order
    Given a temporary JSONL file with content:
      """
      {"timestamp":"2026-04-23T10:00:00.000Z","type":"session_meta","payload":{"id":"codex-dedup-summary","cwd":"/tmp/test-project","cli_version":"0.120.0","model_provider":"openai"}}
      {"timestamp":"2026-04-23T10:00:01.000Z","type":"response_item","payload":{"type":"message","role":"assistant","content":[{"type":"thinking","thinking":"Repeated\nUnique\nRepeated\nUnique","summary":[{"text":"Repeated"},{"text":"Unique"},{"text":"Repeated"}],"thinkingSignature":{"encrypted":"opaque","summary":[{"text":"Unique"}]}},{"type":"output_text","text":"Done."}]}}
      """
    When I parse the file with the Codex parser
    Then there should be 1 session
    And the session reasoning summary block count should be 1
    And the first reasoning summary block should be:
      """
      Repeated
      Unique
      """

  Scenario: Treat unrecognized Codex message blocks as unknown observability
    Given a temporary JSONL file with content:
      """
      {"timestamp":"2026-04-23T10:00:00.000Z","type":"session_meta","payload":{"id":"codex-unknown-block","cwd":"/tmp/test-project","cli_version":"0.120.0","model_provider":"openai"}}
      {"timestamp":"2026-04-23T10:00:01.000Z","type":"response_item","payload":{"type":"message","role":"assistant","content":[{"type":"thinking","thinking":"Known visible reasoning."},{"type":"future_reasoning","payload":{"opaque":true}},{"type":"output_text","text":"Done."}]}}
      """
    When I parse the file with the Codex parser
    Then there should be 1 session
    And the session reasoning observability should be "Unknown"
    And the session should have exactly 1 thinking blocks

  Scenario: Reject non-Codex files
    Given a session file path "/tmp/random.jsonl"
    When I check if the Codex parser can parse it
    Then it should not be parseable
    Given a session file path "/tmp/file.json"
    When I check if the Codex parser can parse it
    Then it should not be parseable
