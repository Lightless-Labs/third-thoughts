Feature: Session type classifier
  The session type classifier determines whether a session is Interactive,
  Subagent, or Unknown based on path heuristics and message classifications.

  # --- Path-based subagent detection ---
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

  # --- All-system-message subagent detection ---
  Scenario: All user messages being SystemMessage classifies as Subagent
    Given a session from path "/home/user/.claude/projects/task/session.jsonl"
    And the session has a user message classified as "SystemMessage"
    And the session has an assistant message classified as "Other"
    And the session has a user message classified as "SystemMessage"
    When I classify the session type
    Then the session type should be "Subagent"

  # --- Interactive detection ---
  Scenario: Session with HumanDirective classifies as Interactive
    Given a session from path "/home/user/.claude/projects/task/session.jsonl"
    And the session has a user message classified as "HumanDirective"
    And the session has an assistant message classified as "Other"
    When I classify the session type
    Then the session type should be "Interactive"

  Scenario: Session with HumanCorrection classifies as Interactive
    Given a session from path "/home/user/.claude/projects/task/session.jsonl"
    And the session has a user message classified as "SystemMessage"
    And the session has a user message classified as "HumanCorrection"
    When I classify the session type
    Then the session type should be "Interactive"

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
