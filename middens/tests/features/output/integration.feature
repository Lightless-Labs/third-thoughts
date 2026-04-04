Feature: Output engine integration
  End-to-end tests verifying renderers work together with real technique output.

  Scenario: render_markdown output has valid YAML frontmatter and valid markdown
    Given a technique result named "integration_md" with a summary "Integration test"
    And a finding "sessions" with integer value 100 described as "Total sessions"
    And a data table "stats" with columns "metric,value" and 3 rows
    And a figure spec titled "Overview" with a vega-lite bar chart spec
    And default output metadata
    When I render markdown
    Then the markdown frontmatter should parse as valid YAML
    And the markdown body should be well-formed markdown

  Scenario: render_json output parses as valid JSON and round-trips
    Given a technique result named "integration_json" with a summary "JSON integration test"
    And a finding "count" with integer value 50 described as "Count"
    And a data table "data" with columns "a,b,c" and 5 rows
    And default output metadata
    When I render JSON
    Then the JSON output should be a valid JSON object
    And the JSON output should round-trip through serde_json deserialization

  Scenario: All renderers handle a real markov TechniqueResult
    Given sessions with tool sequences for markov analysis
    When I run the markov technique
    And I render the technique result as markdown with default metadata
    And I render the technique result as JSON with default metadata
    Then the markdown output should contain YAML frontmatter
    And the markdown output should contain "# markov"
    And the JSON output should be a valid JSON object
    And the JSON output should have a non-empty "findings" array

  Scenario: Markdown renderer handles all finding types simultaneously
    Given a technique result named "mixed_types" with a summary "All types"
    And a finding "null_val" with null value described as "Null finding"
    And a finding "bool_val" with boolean value true described as "Bool finding"
    And a finding "int_val" with integer value 42 described as "Int finding"
    And a finding "float_val" with float value 3.14159265 described as "Float finding"
    And a finding "str_val" with string value "hello" described as "String finding"
    And a finding "arr_val" with array value [1,2,3] described as "Array finding"
    And a finding "obj_val" with object value {"key":"val"} described as "Object finding"
    And default output metadata
    When I render markdown
    Then the findings table should contain the value "\u2014" for finding "null_val"
    And the findings table should contain the value "yes" for finding "bool_val"
    And the findings table should contain the value "42" for finding "int_val"
    And the findings table should contain the value "3.1416" for finding "float_val"
    And the findings table should contain the value "hello" for finding "str_val"
    And the findings table should contain the value "[1,2,3]" for finding "arr_val"
    And the findings table should contain the value "{\"key\":\"val\"}" for finding "obj_val"

  Scenario: Large corpus size in metadata is handled correctly
    Given a technique result named "large" with a summary "Large corpus"
    And output metadata with technique "large", corpus size 999999999, and version "1.0.0"
    When I render markdown
    And I render JSON
    Then the frontmatter should have key "corpus_size" with value "999999999"
    And the JSON metadata "corpus_size" should be 999999999

  # --- Adversarial edge cases ---

  Scenario: Full TechniqueResult with all field types renders to both formats
    Given a technique result named "kitchen_sink" with a summary "All the things"
    And a finding "null_f" with null value described as "Null"
    And a finding "bool_f" with boolean value false described as "Bool"
    And a finding "int_f" with integer value 0 described as "Zero int"
    And a finding "float_f" with float value -1.5 described as "Negative float"
    And a finding "str_f" with string value "" described as "Empty string"
    And a finding "arr_f" with array value [1,2,3] described as "Array"
    And a finding "obj_f" with object value {"a":1} described as "Object"
    And a data table "t1" with columns "x" and 1 rows
    And a data table "t2" with columns "a,b,c" and 60 rows
    And a figure spec titled "Fig1" with a vega-lite bar chart spec
    And default output metadata
    When I render markdown
    And I render JSON
    Then the markdown should contain YAML frontmatter
    And the markdown body should start with "# kitchen_sink"
    And the findings table should have 7 data rows
    And the markdown should contain "## t1"
    And the markdown should contain "## t2"
    And the markdown should contain "## Fig1"
    And the JSON output should be a valid JSON object
    And the JSON findings array should have 7 elements
    And the JSON output should round-trip through serde_json deserialization

  Scenario: Markdown and JSON produce consistent finding counts
    Given a technique result named "consistency" with a summary "Consistency test"
    And a finding "a" with integer value 1 described as "First"
    And a finding "b" with integer value 2 described as "Second"
    And a finding "c" with integer value 3 described as "Third"
    And default output metadata
    When I render markdown
    And I render JSON
    Then the findings table should have 3 data rows
    And the JSON findings array should have 3 elements

  Scenario: Renderers handle technique result with only tables (no findings, no figures)
    Given a technique result named "tables_only" with a summary ""
    And a data table "only_table" with columns "x,y" and 5 rows
    And default output metadata
    When I render markdown
    And I render JSON
    Then the markdown should not contain a findings pipe table
    And the markdown should contain "## only_table"
    And the JSON "findings" array should be empty
    And the JSON tables array should have 1 element

  Scenario: Renderers handle technique result with only figures (no findings, no tables)
    Given a technique result named "figures_only" with a summary ""
    And a figure spec titled "Lone Figure" with a vega-lite bar chart spec
    And default output metadata
    When I render markdown
    And I render JSON
    Then the markdown should not contain a findings pipe table
    And the markdown should contain "## Lone Figure"
    And the JSON "findings" array should be empty
    And the JSON "tables" array should be empty
    And the JSON figures array should have 1 element
