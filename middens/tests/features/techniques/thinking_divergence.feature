Feature: Thinking divergence
  Compare private thinking against public text to quantify suppression of risky
  tokens and overall reasoning-to-output divergence.

  Scenario: Session with thinking containing risk tokens suppressed from output
    Given a session with suppressed thinking risk tokens
    When I run the thinking divergence technique
    Then finding "suppression_rate" should be greater than 0.0

  Scenario: Session with no thinking blocks is skipped with zero analyzed counts
    Given a session with no thinking blocks
    When I run the thinking divergence technique
    Then the thinking divergence result should have zero analyzed counts
    And finding "suppression_rate" should be float 0.0

  Scenario: Session where all risk tokens appear in both thinking and text
    Given a session with mirrored thinking risk tokens in text
    When I run the thinking divergence technique
    Then finding "suppression_rate" should be float 0.0

  Scenario: Empty sessions produce zero counts
    Given no sessions
    When I run the thinking divergence technique
    Then the thinking divergence result should have zero analyzed counts
    And finding "suppression_rate" should be float 0.0

  Scenario: divergence_ratio equals thinking length divided by text length
    Given a session with thinking length 12 and text length 6
    When I run the thinking divergence technique
    Then finding "divergence_ratio" should be float 2.0

  Scenario: Technique is essential and appears in list-techniques
    When I list all registered techniques
    Then the technique list should contain "thinking-divergence"
    And the thinking divergence technique should be registered as essential
