Feature: Session type classifier
  The session type classifier determines whether a session is Interactive,
  Subagent, Autonomous, or Unknown based on path heuristics, structural
  subagent signals, and message classifications.

  # --- Subagent precedence ---
  Scenario: Path containing "subagent" classifies as Subagent
    Given a session from path "/home/user/.claude/projects/subagent-task/session.jsonl"
    And the session has a user message classified as "HumanDirective"
    When I classify the session type
    Then the session type should be "Subagent"

  Scenario: Path containing "agent-a" classifies as Subagent
    Given a session from path "/tmp/agent-a/run.jsonl"
    And the session has a user message classified as "HumanDirective"
    When I classify the session type
    Then the session type should be "Subagent"

  Scenario: Tool result user messages classify as Subagent
    Given a session from path "/home/user/.claude/projects/task/session.jsonl"
    And the session has a user message with a tool_result content block classified as "SystemMessage"
    When I classify the session type
    Then the session type should be "Subagent"

  Scenario: Tool result signal wins over human-looking classifications
    Given a session from path "/home/user/.claude/projects/task/session.jsonl"
    And the session has a user message classified as "HumanDirective"
    And the session has a user message with a tool_result content block classified as "HumanCorrection"
    When I classify the session type
    Then the session type should be "Subagent"

  # --- Interactive detection ---
  Scenario: Session with HumanDirective classifies as Interactive
    Given a session from path "/home/user/.claude/projects/task/session.jsonl"
    And the session has a user message classified as "HumanDirective"
    And the session has an assistant message classified as "Other"
    When I classify the session type
    Then the session type should be "Interactive"

  Scenario: Session with mixed HumanCorrection and HumanDirective classifies as Interactive
    Given a session from path "/home/user/.claude/projects/task/session.jsonl"
    And the session has a user message classified as "HumanCorrection"
    And the session has a user message classified as "HumanDirective"
    When I classify the session type
    Then the session type should be "Interactive"

  Scenario: Session with HumanQuestion classifies as Interactive
    Given a session from path "/home/user/.claude/projects/task/session.jsonl"
    And the session has a user message classified as "HumanQuestion"
    When I classify the session type
    Then the session type should be "Interactive"

  # --- Autonomous detection ---
  Scenario: Only unclassified user messages classify as Autonomous
    Given a session from path "/home/user/.claude/projects/task/session.jsonl"
    And the session has a user message classified as "Unclassified"
    When I classify the session type
    Then the session type should be "Autonomous"

  Scenario: All user messages being SystemMessage classifies as Autonomous
    Given a session from path "/home/user/.claude/projects/task/session.jsonl"
    And the session has a user message classified as "SystemMessage"
    And the session has an assistant message classified as "Other"
    And the session has a user message classified as "SystemMessage"
    When I classify the session type
    Then the session type should be "Autonomous"

  Scenario: Other non-human user messages classify as Autonomous
    Given a session from path "/home/user/.claude/projects/task/session.jsonl"
    And the session has a user message classified as "Other"
    When I classify the session type
    Then the session type should be "Autonomous"

  # --- Unknown fallback ---
  Scenario: Empty session classifies as Unknown
    Given a session from path "/tmp/session.jsonl"
    When I classify the session type
    Then the session type should be "Unknown"

  Scenario: Only assistant messages classifies as Unknown
    Given a session from path "/tmp/session.jsonl"
    And the session has an assistant message classified as "Other"
    When I classify the session type
    Then the session type should be "Unknown"
