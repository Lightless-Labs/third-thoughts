Feature: JSON renderer
  Verify that render_json produces a valid JSON object with correct structure
  and faithful serialization of TechniqueResult data.

  Scenario: Output is a valid JSON object with metadata and result fields
    Given a technique result named "entropy_rate" with a summary "Test summary"
    And a finding "total_sessions" with integer value 100 described as "Sessions"
    And output metadata with technique "entropy_rate", corpus size 500, and version "0.1.0"
    When I render JSON
    Then the JSON output should be a valid JSON object
    And the JSON should have a "metadata" object
    And the JSON should have a "findings" array
    And the JSON should have a "tables" array
    And the JSON should have a "figures" array

  Scenario: Metadata contains all required fields
    Given a technique result named "markov" with a summary "Markov analysis"
    And output metadata with technique "markov", corpus size 1000, and version "0.2.0"
    And output metadata with parameters "window=5,threshold=0.1"
    When I render JSON
    Then the JSON metadata "technique" should be "markov"
    And the JSON metadata "corpus_size" should be 1000
    And the JSON metadata "middens_version" should be "0.2.0"
    And the JSON metadata should have "generated_at"
    And the JSON metadata "parameters" should have key "window" with value "5"

  Scenario: Findings serialized directly from TechniqueResult
    Given a technique result named "test" with a summary ""
    And a finding "count" with integer value 42 described as "Count"
    And a finding "flag" with boolean value true described as "Flag"
    And a finding "ratio" with float value 0.5 described as "Ratio"
    And a finding "empty" with null value described as "Null"
    And default output metadata
    When I render JSON
    Then the JSON findings array should have 4 elements
    And JSON finding "count" should have value 42
    And JSON finding "flag" should have value true
    And JSON finding "ratio" should have value 0.5
    And JSON finding "empty" should have null value

  Scenario: Tables serialized directly from TechniqueResult
    Given a technique result named "test" with a summary ""
    And a data table "my_table" with columns "a,b" and 3 rows
    And default output metadata
    When I render JSON
    Then the JSON tables array should have 1 element
    And JSON table "my_table" should have 2 columns
    And JSON table "my_table" should have 3 rows

  Scenario: Figures serialized directly from TechniqueResult
    Given a technique result named "test" with a summary ""
    And a figure spec titled "Chart" with a vega-lite bar chart spec
    And default output metadata
    When I render JSON
    Then the JSON figures array should have 1 element
    And JSON figure "Chart" should have a "spec" object

  Scenario: Empty TechniqueResult produces valid JSON with empty arrays
    Given an empty technique result named "empty"
    And default output metadata
    When I render JSON
    Then the JSON output should be a valid JSON object
    And the JSON should have a "metadata" object
    And the JSON "findings" array should be empty
    And the JSON "tables" array should be empty
    And the JSON "figures" array should be empty

  Scenario: JSON output round-trips through serde
    Given a technique result named "roundtrip" with a summary "Roundtrip test"
    And a finding "val" with integer value 99 described as "A value"
    And a data table "tbl" with columns "x,y" and 2 rows
    And default output metadata
    When I render JSON
    Then the JSON output should round-trip through serde_json deserialization

  # --- Adversarial edge cases ---

  Scenario: Empty parameters map is present in JSON metadata
    Given a technique result named "test" with a summary ""
    And output metadata with technique "test", corpus size 10, and version "0.1.0"
    When I render JSON
    Then the JSON metadata should have "parameters"

  Scenario: JSON preserves null finding description
    Given a technique result named "test" with a summary ""
    And a finding "no_desc" with integer value 1 and no description
    And default output metadata
    When I render JSON
    Then the JSON findings array should have 1 elements
    And JSON finding "no_desc" should have value 1

  Scenario: JSON handles summary with special characters
    Given a technique result named "test" with a summary "Line 1\nLine 2 with \"quotes\" and <html>"
    And default output metadata
    When I render JSON
    Then the JSON output should be a valid JSON object
    And the JSON output should round-trip through serde_json deserialization

  Scenario: JSON handles large DataTable without truncation
    Given a technique result named "test" with a summary ""
    And a data table "big" with columns "a,b" and 100 rows
    And default output metadata
    When I render JSON
    Then JSON table "big" should have 100 rows

  Scenario: JSON metadata corpus_size is a number not a string
    Given a technique result named "test" with a summary ""
    And output metadata with technique "test", corpus size 42, and version "1.0.0"
    When I render JSON
    Then the JSON metadata "corpus_size" should be 42

  Scenario: JSON includes summary field
    Given a technique result named "test" with a summary "My summary text"
    And default output metadata
    When I render JSON
    Then the JSON output should be a valid JSON object
    And the JSON should contain summary "My summary text"

  Scenario: JSON with multiple tables preserves all tables
    Given a technique result named "test" with a summary ""
    And a data table "first" with columns "a" and 2 rows
    And a data table "second" with columns "b,c" and 3 rows
    And default output metadata
    When I render JSON
    Then the JSON tables array should have 2 elements
