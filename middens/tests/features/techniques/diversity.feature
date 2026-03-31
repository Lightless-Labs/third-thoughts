Feature: Tool usage diversity indices
  Verify Shannon/Simpson diversity, evenness, and species-area analysis.

  Scenario: Single tool has zero diversity
    Given a session "mono" with tools "Bash,Bash,Bash,Bash"
    When I compute diversity metrics for the session
    Then the session richness should be 1
    And the session abundance should be 4
    And the session shannon should be approximately 0.0
    And the session simpson should be approximately 0.0
    And the session evenness should be approximately 0.0

  Scenario: Equal four tools have maximum diversity
    Given a session "even4" with 3 copies each of tools "Bash,Read,Edit,Write"
    When I compute diversity metrics for the session
    Then the session richness should be 4
    And the session abundance should be 12
    And the session shannon should be approximately ln4
    And the session simpson should be approximately 0.75
    And the session evenness should be approximately 1.0

  Scenario: Species-area curve with synthetic data
    Given a species-area session "s1" with 10 tools and 3 unique
    And a species-area session "s2" with 100 tools and 7 unique
    And a species-area session "s3" with 1000 tools and 15 unique
    When I compute the species-area curve
    Then the species-area z should be approximately 0.35 within 0.05
    And the species-area r-squared should be greater than 0.95

  Scenario: Empty session returns zeroes
    Given a session "empty" with tools ""
    When I compute diversity metrics for the session
    Then the session richness should be 0
    And the session abundance should be 0
    And the session shannon should be approximately 0.0
    And the session simpson should be approximately 0.0
    And the session evenness should be approximately 0.0

  Scenario: Run produces complete result
    Given a session "s1" with tools "Bash,Bash,Read"
    And a session "s2" with tools "Edit,Edit,Edit,Edit"
    When I run the diversity technique
    Then the technique result name should be "diversity"
    And the technique result should have findings "mean_shannon,median_shannon,mean_simpson,mean_evenness,species_area_z,species_area_r_squared,monoculture_count,monoculture_fraction,sessions_analyzed"
    And finding "sessions_analyzed" should be integer 2
    And the technique result should have a table "per_session_diversity" with 2 rows

  Scenario: Monoculture detection
    Given a session "mono1" with 10 copies of tool "Bash"
    And a session "mono2" with 99 copies of tool "Bash" and 1 copy of tool "Read"
    And a session "diverse" with tools "Bash,Read,Edit,Write,Bash,Read,Edit,Write"
    When I run the diversity technique
    Then finding "monoculture_count" should be integer 2

  Scenario: Empty sessions slice
    Given no sessions
    When I run the diversity technique
    Then finding "sessions_analyzed" should be integer 0
