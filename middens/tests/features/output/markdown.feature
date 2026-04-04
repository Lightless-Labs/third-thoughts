Feature: Markdown renderer
  Verify that render_markdown produces valid YAML frontmatter and well-structured
  markdown output from TechniqueResults.

  # --- Frontmatter ---

  Scenario: Frontmatter contains required metadata fields
    Given a technique result named "entropy_rate" with a summary "Test summary"
    And output metadata with technique "entropy_rate", corpus size 500, and version "0.1.0"
    When I render markdown
    Then the markdown should contain YAML frontmatter
    And the frontmatter should have key "technique" with value "entropy_rate"
    And the frontmatter should have key "corpus_size" with value "500"
    And the frontmatter should have key "middens_version" with value "0.1.0"
    And the frontmatter should have key "generated_at"

  Scenario: Frontmatter includes parameters map when non-empty
    Given a technique result named "markov" with a summary "Summary"
    And output metadata with parameters "min_sessions=10,window_size=5"
    When I render markdown
    Then the frontmatter should contain a "parameters" map
    And the frontmatter parameter "min_sessions" should be "10"
    And the frontmatter parameter "window_size" should be "5"

  Scenario: Frontmatter omits parameters when empty
    Given a technique result named "markov" with a summary "Summary"
    And output metadata with no parameters
    When I render markdown
    Then the frontmatter should not contain "parameters"

  # --- Title ---

  Scenario: Title is the technique name as H1
    Given a technique result named "burstiness_analysis" with a summary "Some summary"
    And default output metadata
    When I render markdown
    Then the markdown body should start with "# burstiness_analysis"

  # --- Summary ---

  Scenario: Summary rendered as paragraph after title
    Given a technique result named "test" with a summary "This is the summary paragraph."
    And default output metadata
    When I render markdown
    Then the markdown body should contain "This is the summary paragraph."
    And the summary should appear after the title

  Scenario: Summary omitted when empty
    Given a technique result named "test" with a summary ""
    And default output metadata
    When I render markdown
    Then the markdown body after the title should not contain a summary paragraph

  # --- Findings table ---

  Scenario: Findings rendered as pipe table with correct columns
    Given a technique result named "test" with a summary ""
    And a finding "total_sessions" with integer value 42 described as "Total sessions analyzed"
    And a finding "p_value" with float value 0.00123 described as "Statistical significance"
    And default output metadata
    When I render markdown
    Then the markdown should contain a pipe table with columns "Finding", "Value", "Description"
    And the findings table should have 2 data rows

  Scenario: Findings table omitted when no findings
    Given a technique result named "test" with a summary ""
    And default output metadata
    When I render markdown
    Then the markdown should not contain a findings pipe table

  # --- format_value ---

  Scenario: Null value rendered as em dash
    Given a technique result named "test" with a summary ""
    And a finding "missing" with null value described as "A null"
    And default output metadata
    When I render markdown
    Then the findings table should contain the value "\u2014" for finding "missing"

  Scenario: Boolean true rendered as "yes"
    Given a technique result named "test" with a summary ""
    And a finding "flag" with boolean value true described as "A flag"
    And default output metadata
    When I render markdown
    Then the findings table should contain the value "yes" for finding "flag"

  Scenario: Boolean false rendered as "no"
    Given a technique result named "test" with a summary ""
    And a finding "flag" with boolean value false described as "A flag"
    And default output metadata
    When I render markdown
    Then the findings table should contain the value "no" for finding "flag"

  Scenario: Integer rendered without decimals
    Given a technique result named "test" with a summary ""
    And a finding "count" with integer value 1234 described as "A count"
    And default output metadata
    When I render markdown
    Then the findings table should contain the value "1234" for finding "count"

  Scenario: Float rendered with 4 decimal places
    Given a technique result named "test" with a summary ""
    And a finding "ratio" with float value 3.14159265 described as "Pi"
    And default output metadata
    When I render markdown
    Then the findings table should contain the value "3.1416" for finding "ratio"

  Scenario: String value rendered as-is
    Given a technique result named "test" with a summary ""
    And a finding "label" with string value "hello world" described as "A label"
    And default output metadata
    When I render markdown
    Then the findings table should contain the value "hello world" for finding "label"

  Scenario: Array value rendered as compact JSON
    Given a technique result named "test" with a summary ""
    And a finding "items" with array value [1,2,3] described as "An array"
    And default output metadata
    When I render markdown
    Then the findings table should contain the value "[1,2,3]" for finding "items"

  Scenario: Object value rendered as compact JSON
    Given a technique result named "test" with a summary ""
    And a finding "config" with object value {"a":1} described as "An object"
    And default output metadata
    When I render markdown
    Then the findings table should contain the value "{\"a\":1}" for finding "config"

  # --- DataTables ---

  Scenario: DataTable rendered as markdown section
    Given a technique result named "test" with a summary ""
    And a data table "transition_matrix" with columns "from,to,probability" and 3 rows
    And default output metadata
    When I render markdown
    Then the markdown should contain "## transition_matrix"
    And the section "transition_matrix" should contain a pipe table

  Scenario: DataTable rows capped at 50 with ellipsis
    Given a technique result named "test" with a summary ""
    And a data table "big_table" with columns "id,value" and 60 rows
    And default output metadata
    When I render markdown
    Then the "big_table" section should show the first 25 rows
    And the "big_table" section should contain an ellipsis row "..."
    And the "big_table" section should show the last 5 rows

  Scenario: DataTable with exactly 50 rows is not truncated
    Given a technique result named "test" with a summary ""
    And a data table "exact_table" with columns "id,value" and 50 rows
    And default output metadata
    When I render markdown
    Then the "exact_table" section should show all 50 data rows
    And the "exact_table" section should not contain an ellipsis row

  # --- FigureSpecs ---

  Scenario: FigureSpec rendered with title and JSON code block
    Given a technique result named "test" with a summary ""
    And a figure spec titled "Tool Usage Distribution" with a vega-lite bar chart spec
    And default output metadata
    When I render markdown
    Then the markdown should contain "## Tool Usage Distribution"
    And the markdown should contain a JSON code block with the figure spec

  # --- Edge cases ---

  Scenario: Empty TechniqueResult produces valid markdown with just frontmatter and title
    Given an empty technique result named "empty_test"
    And default output metadata
    When I render markdown
    Then the markdown should contain YAML frontmatter
    And the markdown body should start with "# empty_test"
    And the markdown should not contain a findings pipe table
    And the markdown should have no data table sections
    And the markdown should have no figure sections

  Scenario: Special characters in finding descriptions are not corrupted
    Given a technique result named "test" with a summary ""
    And a finding "weird" with string value "pipe|char" described as "Has a | pipe and *bold* chars"
    And default output metadata
    When I render markdown
    Then the findings table row for "weird" should contain "pipe\|char"

  # --- Adversarial edge cases ---

  Scenario: Summary with markdown injection does not break structure
    Given a technique result named "test" with a summary "## Injected heading\n| fake | table |"
    And default output metadata
    When I render markdown
    Then the markdown should contain YAML frontmatter
    And the markdown body should start with "# test"

  Scenario: Finding description is None (omitted)
    Given a technique result named "test" with a summary ""
    And a finding "no_desc" with integer value 7 and no description
    And default output metadata
    When I render markdown
    Then the findings table should have 1 data rows
    And the findings table row for "no_desc" should contain "7"

  Scenario: Multiple DataTables rendered as separate sections
    Given a technique result named "test" with a summary ""
    And a data table "table_alpha" with columns "a,b" and 2 rows
    And a data table "table_beta" with columns "x,y,z" and 3 rows
    And default output metadata
    When I render markdown
    Then the markdown should contain "## table_alpha"
    And the markdown should contain "## table_beta"
    And the section "table_alpha" should contain a pipe table
    And the section "table_beta" should contain a pipe table

  Scenario: Very large integer does not corrupt formatting
    Given a technique result named "test" with a summary ""
    And a finding "huge" with integer value 9999999999999 described as "Very large number"
    And default output metadata
    When I render markdown
    Then the findings table should contain the value "9999999999999" for finding "huge"

  Scenario: Float value 0.0 rendered with 4 decimal places
    Given a technique result named "test" with a summary ""
    And a finding "zero" with float value 0.0 described as "Zero float"
    And default output metadata
    When I render markdown
    Then the findings table should contain the value "0.0000" for finding "zero"

  Scenario: Technique name with underscores preserved in title
    Given a technique result named "my_complex_technique_v2" with a summary ""
    And default output metadata
    When I render markdown
    Then the markdown body should start with "# my_complex_technique_v2"

  Scenario: DataTable with 51 rows triggers truncation
    Given a technique result named "test" with a summary ""
    And a data table "boundary_table" with columns "id,value" and 51 rows
    And default output metadata
    When I render markdown
    Then the "boundary_table" section should show the first 25 rows
    And the "boundary_table" section should contain an ellipsis row "..."
    And the "boundary_table" section should show the last 5 rows

  Scenario: DataTable with 1 row is not truncated
    Given a technique result named "test" with a summary ""
    And a data table "tiny_table" with columns "col" and 1 rows
    And default output metadata
    When I render markdown
    Then the "tiny_table" section should show all 1 data rows
    And the "tiny_table" section should not contain an ellipsis row

  Scenario: Multiple FigureSpecs each get their own section
    Given a technique result named "test" with a summary ""
    And a figure spec titled "Chart A" with a vega-lite bar chart spec
    And a figure spec titled "Chart B" with a vega-lite bar chart spec
    And default output metadata
    When I render markdown
    Then the markdown should contain "## Chart A"
    And the markdown should contain "## Chart B"

  Scenario: Finding with empty string value
    Given a technique result named "test" with a summary ""
    And a finding "blank" with string value "" described as "Empty string"
    And default output metadata
    When I render markdown
    Then the findings table should have 1 data rows
