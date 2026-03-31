Feature: Technique registry
  Verify all techniques are registered and discoverable.

  Scenario: All techniques returns without error
    When I list all registered techniques
    Then the technique list should not be empty
    And the technique list should contain "entropy"
