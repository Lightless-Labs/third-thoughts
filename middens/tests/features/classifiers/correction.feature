Feature: Message correction classifier
  The correction classifier categorizes user messages by intent using a
  priority-based pipeline: structural > system tags > lexical > positional > fallback.

  # --- Priority 1: Structural (tool_result blocks) ---
  Scenario: Structural tool_result block classifies as SystemMessage
    Given a user message "some output" with a tool_result content block
    When I classify the message at position "middle"
    Then the message should be classified as "SystemMessage"

  # --- Priority 2: System tags ---
  Scenario: System-reminder tag classifies as SystemMessage
    Given a user message "<system-reminder>You are an agent</system-reminder>"
    When I classify the message at position "middle"
    Then the message should be classified as "SystemMessage"

  # --- Priority 3: Lexical patterns (correction, approval, question) ---
  Scenario Outline: Correction patterns classify as HumanCorrection
    Given a user message "<text>"
    When I classify the message at position "middle"
    Then the message should be classified as "HumanCorrection"

    Examples:
      | text                                       |
      | No, that's wrong. Use the other function.  |
      | revert that last change                     |

  Scenario Outline: Approval patterns classify as HumanApproval
    Given a user message "<text>"
    When I classify the message at position "middle"
    Then the message should be classified as "HumanApproval"

    Examples:
      | text                    |
      | lgtm                    |
      | Looks good, ship it!    |

  Scenario Outline: Question patterns classify as HumanQuestion
    Given a user message "<text>"
    When I classify the message at position "middle"
    Then the message should be classified as "HumanQuestion"

    Examples:
      | text                    |
      | How does this work?     |
      | Did you run the tests?  |

  # --- Priority 4: Positional default ---
  Scenario: First message in session classifies as HumanDirective
    Given a user message "Implement the new feature for user auth"
    When I classify the message at position "first"
    Then the message should be classified as "HumanDirective"

  # --- Priority 5: Fallback by length ---
  Scenario: Short non-matching message defaults to HumanDirective
    Given a user message "add a test for the parser"
    When I classify the message at position "middle"
    Then the message should be classified as "HumanDirective"

  Scenario: Long non-matching message defaults to Other
    Given a user message of 1500 repeated "x" characters
    When I classify the message at position "middle"
    Then the message should be classified as "Other"

  # --- Non-user role ---
  Scenario: Assistant message classifies as Other
    Given an assistant message "Here is the code"
    When I classify the message at position "middle"
    Then the message should be classified as "Other"
