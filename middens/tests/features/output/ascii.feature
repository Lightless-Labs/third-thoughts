Feature: ASCII renderers
  Verify sparkline, bar chart, and table ASCII rendering functions.

  # --- Sparkline ---

  Scenario: Sparkline maps values to 8 Unicode block levels
    Given sparkline values [0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0]
    When I render a sparkline with width 8
    Then the sparkline should contain all 8 block characters

  Scenario: Sparkline scales between min and max
    Given sparkline values [10.0, 20.0, 30.0, 40.0]
    When I render a sparkline with width 4
    Then the sparkline should have 4 characters
    And the first sparkline character should be the lowest block
    And the last sparkline character should be the highest block

  Scenario: Sparkline downsamples when values exceed width
    Given sparkline values [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]
    When I render a sparkline with width 5
    Then the sparkline should have 5 characters

  Scenario: Sparkline returns empty string for empty input
    Given sparkline values []
    When I render a sparkline with width 10
    Then the sparkline should be empty

  Scenario: Sparkline renders all-equal values as mid-level blocks
    Given sparkline values [5.0, 5.0, 5.0, 5.0]
    When I render a sparkline with width 4
    Then every sparkline character should be the same mid-level block

  Scenario: Sparkline handles single value
    Given sparkline values [42.0]
    When I render a sparkline with width 1
    Then the sparkline should have 1 characters

  Scenario: Sparkline handles negative values
    Given sparkline values [-10.0, -5.0, 0.0, 5.0, 10.0]
    When I render a sparkline with width 5
    Then the sparkline should have 5 characters
    And the first sparkline character should be the lowest block
    And the last sparkline character should be the highest block

  # --- Bar chart ---

  Scenario: Bar chart renders label, bar, and value
    Given a bar chart with label "Read" value 75.0 max 100.0 width 20
    When I render the bar chart
    Then the bar output should contain "Read"
    And the bar output should contain filled block characters
    And the bar output should contain empty block characters
    And the bar output should contain "75"

  Scenario: Bar chart handles max == 0
    Given a bar chart with label "Empty" value 0.0 max 0.0 width 20
    When I render the bar chart
    Then the bar output should contain "Empty"
    And the bar output should show value 0
    And the bar output should not contain filled block characters

  Scenario: Bar chart handles value > max (clamp to full bar)
    Given a bar chart with label "Over" value 150.0 max 100.0 width 10
    When I render the bar chart
    Then the bar output should contain "Over"
    And the bar should be completely filled

  Scenario: Bar chart with zero value and positive max
    Given a bar chart with label "None" value 0.0 max 100.0 width 10
    When I render the bar chart
    Then the bar output should not contain filled block characters

  Scenario: Bar chart respects configurable width
    Given a bar chart with label "X" value 50.0 max 100.0 width 40
    When I render the bar chart
    Then the bar portion should be approximately 40 characters wide

  # --- ASCII table ---

  Scenario: ASCII table renders header, separator, and data rows
    Given an ASCII data table "test" with columns "Name,Score,Grade" and 3 rows
    When I render the ASCII table with max column width 20
    Then the ASCII table output should have a header row with "Name", "Score", "Grade"
    And the ASCII table output should have a separator row
    And the ASCII table output should have 3 data rows

  Scenario: ASCII table truncates values to max_col_width
    Given an ASCII data table "trunc" with columns "data" and a row with a 100-character value
    When I render the ASCII table with max column width 15
    Then no cell in the ASCII table should exceed 15 characters

  Scenario: ASCII table caps at 30 rows with summary
    Given an ASCII data table "big" with columns "id,value" and 40 rows
    When I render the ASCII table with max column width 20
    Then the ASCII table should show the first 20 data rows
    And the ASCII table should have a summary row
    And the ASCII table should show the last 5 data rows
    And the ASCII table should have 26 visible data-like rows total

  Scenario: ASCII table with exactly 30 rows is not truncated
    Given an ASCII data table "exact" with columns "id,value" and 30 rows
    When I render the ASCII table with max column width 20
    Then the ASCII table should show all 30 data rows
    And the ASCII table should not have a summary row

  Scenario: ASCII table column alignment
    Given an ASCII data table "align" with columns "short,a_longer_column" and 2 rows
    When I render the ASCII table with max column width 30
    Then all ASCII table rows should have the same total width

  Scenario: ASCII table with single column
    Given an ASCII data table "single" with columns "only" and 2 rows
    When I render the ASCII table with max column width 20
    Then the ASCII table output should have a header row with "only"
    And the ASCII table output should have 2 data rows

  # --- Adversarial edge cases ---

  Scenario: Sparkline with width 0 returns empty string
    Given sparkline values [1.0, 2.0, 3.0]
    When I render a sparkline with width 0
    Then the sparkline should be empty

  Scenario: Sparkline with large dataset downsamples correctly
    Given sparkline values from 1.0 to 1000.0 in 1000 steps
    When I render a sparkline with width 10
    Then the sparkline should have 10 characters
    And the first sparkline character should be the lowest block
    And the last sparkline character should be the highest block

  Scenario: Sparkline with width larger than data repeats or pads
    Given sparkline values [1.0, 5.0, 10.0]
    When I render a sparkline with width 20
    Then the sparkline should have at most 20 characters

  Scenario: Sparkline with NaN-like extreme values
    Given sparkline values [0.0, 1000000.0]
    When I render a sparkline with width 2
    Then the sparkline should have 2 characters
    And the first sparkline character should be the lowest block
    And the last sparkline character should be the highest block

  Scenario: Bar chart with negative value
    Given a bar chart with label "Neg" value -5.0 max 100.0 width 10
    When I render the bar chart
    Then the bar output should contain "Neg"
    And the bar output should not contain filled block characters

  Scenario: Bar chart with very long label
    Given a bar chart with label "This is a very long label that should still render" value 50.0 max 100.0 width 10
    When I render the bar chart
    Then the bar output should contain "This is a very long label that should still render"

  Scenario: Bar chart with value equal to max
    Given a bar chart with label "Full" value 100.0 max 100.0 width 10
    When I render the bar chart
    Then the bar should be completely filled

  Scenario: ASCII table with 0 rows
    Given an ASCII data table "empty" with columns "a,b,c" and 0 rows
    When I render the ASCII table with max column width 20
    Then the ASCII table output should have a header row with "a"
    And the ASCII table output should have a separator row
    And the ASCII table output should have 0 data rows

  Scenario: ASCII table with 29 rows is not truncated
    Given an ASCII data table "under" with columns "id,value" and 29 rows
    When I render the ASCII table with max column width 20
    Then the ASCII table should show all 29 data rows
    And the ASCII table should not have a summary row

  Scenario: ASCII table with 31 rows triggers truncation
    Given an ASCII data table "over" with columns "id,value" and 31 rows
    When I render the ASCII table with max column width 20
    Then the ASCII table should show the first 20 data rows
    And the ASCII table should have a summary row
    And the ASCII table should show the last 5 data rows

  Scenario: ASCII table with max_col_width of 1 still renders
    Given an ASCII data table "tiny_width" with columns "data" and a row with a 100-character value
    When I render the ASCII table with max column width 1
    Then no cell in the ASCII table should exceed 1 characters
